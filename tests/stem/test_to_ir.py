"""AST to IR 1.0 (docs/STEM_DESIGN.md, section 7): every row of the encoding table, one-to-one
symbol naming, the grounding of every premise, ``Problem.model_validate`` on every built
problem, and the nonlinear policy chosen exactly when the engine's validator needs it."""
from __future__ import annotations

import glob
import json
import re
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.engine.policies import required_policy
from epinoic_logic.ir.schema import IDENT_RE, Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.lexer import lex
from epinoic_logic.stem.limits import PROFILES
from epinoic_logic.stem.normalize import reading_view
from epinoic_logic.stem.parser import ParseContext, parse_math
from epinoic_logic.stem.scaling import Term
from epinoic_logic.stem.to_ir import EncodeError, Encoder, ProblemBuilder, Reading, grounding, inspect_ir, ir_name

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "stem" / "corpus"
_PROFILE = {"Physics": "physics", "Chemistry": "chemistry", "Biology": "biology", "Environmental Systems and Societies": "ess"}


def node(expr: str, profile: str = "physics", names: tuple[str, ...] = ()):
    rv = reading_view(expr)
    toks = lex(rv, mode="plain", orig=expr, cs=PROFILES[profile].computer_science).tokens
    pm = parse_math(toks, ParseContext(s=rv, names=frozenset(names), profile=PROFILES[profile]))
    assert pm.chains, expr
    n = pm.chains[0].operands[0].readings[0]
    return n


def value(expr: dict) -> Fraction:
    op = expr["op"]
    if op == "real":
        return Fraction(expr["value"])
    if op == "add":
        return sum((value(a) for a in expr["args"]), Fraction(0))
    if op == "mul":
        out = Fraction(1)
        for a in expr["args"]:
            out *= value(a)
        return out
    if op == "sub":
        return value(expr["left"]) - value(expr["right"])
    if op == "neg":
        return -value(expr["arg"])
    if op == "div":
        return value(expr["left"]) / value(expr["right"])
    if op == "ite":
        c = expr["cond"]
        assert c["op"] == "ge"
        return value(expr["then"]) if value(c["left"]) >= value(c["right"]) else value(expr["otherwise"])
    raise AssertionError(op)


def encode(expr: str, *, si: bool = False, sign: int = 1, angle: str = "rad", profile: str = "physics"):
    b = ProblemBuilder("p", "q", "r:s1.1")
    enc = Encoder(b, Reading(si=si, sign=sign, angle=angle, label="SI" if si else "as written"))
    t = enc.term(node(expr, profile))
    return t, b, enc


def closed_value(t: Term) -> Fraction:
    return value(t.expr) * Fraction(10) ** t.k


def premise_ids(b: ProblemBuilder) -> list[str]:
    return [p["id"] for p in b.premises]


# --------------------------------------------------------------------------- symbol names


def test_symbol_names_follow_the_design_examples():
    assert ir_name("v") == "s_v"
    assert ir_name("V") == "s_cap_v"
    assert ir_name("v_0") == "s_v_0"
    assert ir_name("Δv") == "s_delta_v"
    assert ir_name("θ") == "s_theta"
    assert ir_name("f'") == "s_f_prime"


def test_symbol_naming_is_injective_and_valid():
    originals = ["v", "V", "v_0", "v_1", "Δv", "ΔV", "θ", "Θ", "f'", "f''", "n(H₂O)", "n(H₂O₂)", "[H⁺]", "[OH⁻]", "E_k", "E_K", "μ", "m_e", "a_b", "a__b",
                 "ΔH_c(H₂)", "λ", "Λ", "x" * 80, "x" * 81, "ε_0", "ϵ", "T½", "W∥", "W⊥"]
    b = ProblemBuilder("p", "q", "r")
    names = [b.user_symbol(o) for o in originals]
    assert len(set(names)) == len(originals)
    for n in names:
        assert IDENT_RE.match(n) and len(n) <= 64
    assert b.user_symbol("v") == names[0]  # stable within a problem
    assert b.user_symbol("v", tag="r2") != names[0]


# --------------------------------------------------------------------------- rows of section 7.4


def test_quantity_is_folded_with_its_exact_si_factor():
    t, _b, _e = encode("2.5 km", si=True)
    assert closed_value(t) == 2500
    t, _b, _e = encode("2.5 km", si=False)
    assert closed_value(t) == Fraction(5, 2)
    t, _b, _e = encode("6.62607015 × 10⁻³⁴ J s", si=True)
    assert closed_value(t) == Fraction(662607015, 10 ** 42) and t.k == -34


def test_sums_differences_and_negation():
    t, b, _e = encode("1 + 2 + 3 − 4")
    assert closed_value(t) == 2 and not b.premises
    t, _b, _e = encode("−(2.5 − 4)")
    assert closed_value(t) == Fraction(3, 2)
    long = " + ".join(str(i) for i in range(1, 60))
    t, _b, _e = encode(long)
    assert closed_value(t) == sum(range(1, 60))
    assert len(t.expr["args"]) <= 32


def test_products_are_linear_when_at_most_one_factor_is_open():
    t, b, _e = encode("2.0 × 3.0 × 4")
    assert closed_value(t) == 24 and not b.nonlinear


def test_division_by_a_literal_is_a_div():
    t, b, _e = encode("(20 − 0)/4.0")
    assert t.expr["op"] == "div" and closed_value(t) == 5 and not b.premises


def test_division_by_a_compound_closed_divisor_uses_an_auxiliary_with_a_guard():
    t, b, _e = encode("1/(1/4.0 + 1/6.0)")
    ids = premise_ids(b)
    assert any(i.startswith("Q_DEF_q_") for i in ids) and any(i.startswith("GUARD_q_") for i in ids)
    q_def = next(p for p in b.premises if p["id"].startswith("Q_DEF"))
    assert q_def["grounding"]["kind"] == "arithmetic_fact"
    guard = next(p for p in b.premises if p["id"].startswith("GUARD"))
    assert guard["grounding"]["kind"] == "assumption"
    assert not b.nonlinear  # q times a closed divisor is linear


@pytest.mark.parametrize("expr", ["(7 − 3)/(4 − 4)", "5/0", "1/(2.0 − 2.0)"])
def test_division_by_an_exact_zero_is_undefined(expr):
    with pytest.raises(EncodeError) as e:
        encode(expr)
    assert e.value.code == "ST-UNDEF-001"


def test_symbolic_divisor_is_never_a_div_by_a_variable():
    b = ProblemBuilder("p", "q", "r")
    env = {"x": Term({"op": "var", "name": b.user_symbol("x")}, 0, False), "y": Term({"op": "var", "name": b.user_symbol("y")}, 0, False)}
    enc = Encoder(b, Reading(), env=env)
    t = enc.term(node("x/y", names=("x", "y")))
    assert t.expr == {"op": "var", "name": "q_1"}
    assert b.nonlinear
    assert '"op": "div"' not in json.dumps([p["expr"] for p in b.premises])


def test_powers():
    t, b, _e = encode("3.0²")
    assert closed_value(t) == 9 and not b.nonlinear
    t, b, _e = encode("(1 + 3.5/100)^3")
    assert closed_value(t) == Fraction(1035, 1000) ** 3 and not b.nonlinear
    t, b, _e = encode("2^0")
    assert closed_value(t) == 1
    t, b, _e = encode("4.0^-2")
    assert any(i.startswith("Q_DEF") for i in premise_ids(b)) and any(i.startswith("GUARD") for i in premise_ids(b))
    with pytest.raises(EncodeError) as e:
        encode("0^0")
    assert e.value.code == "ST-UNDEF-001"


def test_square_roots_are_exact_auxiliaries():
    t, b, _e = encode("√8")
    s = next(p for p in b.premises if p["id"].startswith("S_SQ"))
    assert s["expr"]["op"] == "and" and b.nonlinear
    t, b, _e = encode("√(1.0 × 10⁻⁵)")      # an odd decimal exponent moves into the radicand
    assert b.premises
    with pytest.raises(EncodeError) as e:
        encode("√(3 − 5)")
    assert e.value.code == "ST-UNDEF-001"


def test_absolute_value_and_percent():
    t, _b, _e = encode("|2.0 − 5.0|")
    assert closed_value(t) == 3
    t, _b, _e = encode("75 %", si=True)
    assert closed_value(t) == Fraction(3, 4)
    t, _b, _e = encode("75 %", si=False)
    assert closed_value(t) == 75


def test_plus_minus_follows_the_reading_sign():
    tp, _b, _e = encode("3 ± 2", sign=1)
    tm, _b, _e = encode("3 ± 2", sign=-1)
    assert closed_value(tp) == 5 and closed_value(tm) == 1


def test_exact_table_functions():
    t, b, enc = encode("sin 30°")
    assert closed_value(t) == Fraction(1, 2) and not b.premises and enc.exact_used
    t, b, _e = encode("cos 30°")
    assert any(p["id"].startswith("S_SQ") for p in b.premises)  # √3/2 through an exact root of 3
    t, b, _e = encode("log 1000", profile="mathematics_aa")
    assert closed_value(t) == 3
    t, b, _e = encode("sin(π/6)", profile="mathematics_aa")
    assert closed_value(t) == Fraction(1, 2)


def test_other_functions_and_pi_are_enclosures():
    t, b, enc = encode("sin 25°")
    assert enc.uses_intervals and t.expr["op"] == "var" and t.expr["name"].startswith("enc_")
    lo = next(p for p in b.premises if p["id"].startswith("ENC_LO"))
    assert lo["grounding"]["kind"] == "arithmetic_fact" and "enclosure" in lo["grounding"]["note"]
    t, b, enc = encode("2π")
    assert enc.uses_intervals
    _t, b, enc = encode("ln 50", profile="mathematics_aa")
    assert enc.enclosures


def test_a_function_of_an_unknown_is_undecided():
    b = ProblemBuilder("p", "q", "r")
    enc = Encoder(b, Reading(), env={"x": Term({"op": "var", "name": b.user_symbol("x")}, 0, False)})
    with pytest.raises(EncodeError) as e:
        enc.term(node("sin x", names=("x",)))
    assert e.value.code == "ST-UNDEC-001"


def test_unsupported_nodes_name_their_reason():
    with pytest.raises(EncodeError) as e:
        encode("5!")
    assert e.value.code == "ST-UNDEC-001" and "factorial" in e.value.reason


def test_an_unknown_unit_has_no_si_reading():
    with pytest.raises(EncodeError) as e:
        encode("150 kJ m⁻² yr⁻¹", si=True)
    assert e.value.code == "ST-UNIT-001"
    t, _b, _e = encode("150 kJ m⁻² yr⁻¹", si=False)
    assert closed_value(t) == 150


def test_inspect_ir_reads_the_validator_rule():
    lin = {"premises": [{"expr": {"op": "eq", "left": {"op": "var", "name": "c"}, "right": {"op": "mul", "args": [{"op": "real", "value": "2"},
                                                                                                                   {"op": "var", "name": "x"}]}}}],
           "symbols": [1, 2]}
    rep = inspect_ir(lin)
    assert not rep.nonlinear and rep.degree == 1 and rep.symbols == 2
    nl = {"premises": [{"expr": {"op": "eq", "left": {"op": "var", "name": "c"}, "right": {"op": "mul", "args": [{"op": "var", "name": "x"},
                                                                                                                  {"op": "var", "name": "y"}]}}}]}
    assert inspect_ir(nl).nonlinear and inspect_ir(nl).degree == 2


def test_grounding_kinds():
    assert grounding("figure")["kind"] == "supplied_text" and grounding("figure")["verified"] is True
    assert grounding("request")["kind"] == "task_setting" and grounding("request")["verified"] is True
    assert grounding("device")["kind"] == "arithmetic_fact"
    assert grounding("law")["kind"] == "specialist_inference"
    for k in ("guard", "side", "booklet"):
        assert grounding(k)["kind"] == "assumption"
    with pytest.raises(ValueError):
        grounding("nonsense")


# --------------------------------------------------------------------------- built problems


def _corpus_plans():
    out = []
    for fn in sorted(glob.glob(str(CORPUS / "*.json"))):
        d = json.loads(Path(fn).read_text(encoding="utf-8"))
        subj = d["subject"]
        prof = _PROFILE.get(subj) or ("mathematics_ai" if "Applications" in subj else "mathematics_aa")
        doc = build_document(d["response_text"], d["question"], prof)
        out.append((d["id"], build_checks(doc, report_id=d["id"], request_id="req-" + d["id"])))
    return out


PLANS = _corpus_plans()


def test_every_corpus_problem_validates_and_its_policy_is_exactly_what_the_validator_needs():
    n = 0
    for item, plan in PLANS:
        for pc in plan.checks:
            prob = Problem.model_validate(pc.problem)
            assert required_policy(prob) == pc.policy, (item, pc.check_id)
            assert ("policy: nonlinear" in (prob.notes or "")) == (pc.policy == "nonlinear")
            assert prob.notes and prob.notes.startswith("STEM check: proves a property of its encoding only")
            assert len(prob.problem_id) <= 128 and len(prob.claim_id) <= 128
            assert prob.claim_id.startswith(item + ":")
            n += 1
    assert n > 300


_GROUND = {
    "C_DEF": {"supplied_text"}, "R": {"supplied_text", "task_setting"}, "W": {"supplied_text"}, "Q_DEF": {"arithmetic_fact"}, "S_SQ": {"arithmetic_fact"},
    "P_DEF": {"arithmetic_fact"}, "GUARD": {"assumption"}, "ENC_LO": {"arithmetic_fact"}, "ENC_HI": {"arithmetic_fact"}, "PREV": {"specialist_inference"},
    "FORMULA": {"specialist_inference"}, "SIDE_ROOT": {"assumption"}, "L_DEF": {"supplied_text", "arithmetic_fact"},
    "R_DEF": {"supplied_text", "arithmetic_fact"}, "K": {"supplied_text"}, "T": {"arithmetic_fact"}, "BAND": {"supplied_text"},
}


def test_every_premise_is_grounded_by_its_role():
    for item, plan in PLANS:
        for pc in plan.checks:
            for p in pc.problem["premises"]:
                g = p.get("grounding")
                assert g is not None and g["kind"], (item, pc.check_id, p["id"])
                head = re.match(r"[A-Z]+(?:_[A-Z]+)?", p["id"]).group(0)
                for prefix, kinds in _GROUND.items():
                    if head == prefix or (head.startswith(prefix + "_") and prefix in ("Q_DEF", "S_SQ", "P_DEF", "ENC_LO", "ENC_HI", "L_DEF", "R_DEF")):
                        assert g["kind"] in kinds, (item, pc.check_id, p["id"], g["kind"])
                if p["id"].startswith("B_") and "did not state it" in g.get("note", ""):
                    assert g["kind"] == "assumption"


def test_si_figures_name_the_unit_conversion_and_enclosures_are_not_engine_results():
    doc = build_document("v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹ and the component is 10 × sin 25° = 4.23 N", None, "physics")
    plan = build_checks(doc, report_id="r", request_id="q")
    notes = [p["grounding"].get("note", "") for pc in plan.checks for p in pc.problem["premises"] if p["id"].startswith("C_DEF")]
    assert any("converted to SI by exact unit-table factors" in n for n in notes)
    enc = [pc for pc in plan.checks if "enclosure" in pc.description]
    assert enc and all("not engine results" in pc.description for pc in enc)


def test_request_values_are_task_setting_and_verified():
    doc = build_document("Given: g = 9.81 m s⁻².\nW = mg = 5.0 × 9.81 = 49 N.", "A 5.0 kg box. Take g = 9.81 m s⁻².", "physics")
    plan = build_checks(doc, report_id="r", request_id="q")
    giv = [pc for pc in plan.checks if pc.relation_kind == "giv"]
    assert giv
    kinds = {p["grounding"]["kind"] for p in giv[0].problem["premises"] if p["id"].startswith("B_")}
    assert kinds == {"task_setting"}
