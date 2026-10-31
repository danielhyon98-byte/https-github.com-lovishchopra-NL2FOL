"""STEM repair 12 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 43, decision 72).

* rule ``arithmetic-restatement`` (the fourth problem, medium): a writer's-own premise that restates a conjunct of the conclusion with its
  terms moved across or both sides scaled ('contrib − 2.00 = 0', '2 × contrib = 4.00', '2 × pct = 200', 'pd − 60.4 = 0') restated nothing to
  the overseer's readings, every arithmetic term being opaque to them, so a circular translation in that form carried its result with no
  OVS-TRN-006 and a correct ``translation_circular`` accusation of it was REFUTED (OVS-AGENT-001), against the pack's own I77. The arithmetic
  reading reads the arithmetic of the conjunct's own symbols exactly; arithmetic of numbers alone, the working the engine checks, stays
  opaque;
* rule ``identity-statement`` (the first problem's receipt rule): an identity check whose held problem gives its variable a value, signed as
  the success the check expects, is OVS-FORM-005 (formal_status_wrong). The re-derivation runs the pack as shipped, so a pack that binds the
  variable again gives no digest or statement difference: the problem the engine decided names it;
* the STEM probes of repair 12 (the twelfth independent test's plants and the class, each with its clean control: the two false failures of
  rule prose-base on correct working among the controls) and the tamper cases T23bq to T23bt and T22ag to T22ai with the control T22-working;
* the pack beside the code: I77, I97, I98, K6, the kinds table, D31's new readings, the master prompt and the mistakes rows, every new
  statement executed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import stem_probes as SP  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.engine.runner import circular_premises as translator_circular_premises  # noqa: E402
from epinoic_logic.ir.schema import Problem  # noqa: E402
from epinoic_logic.overseer import KIND_CHECKS, OVS_CODES  # noqa: E402
from epinoic_logic.overseer.checks.formal import IDENTITY_RULE, identity_bindings, identity_variables  # noqa: E402
from epinoic_logic.overseer.checks.translation import RESTATEMENT_WAYS, SEMANTIC_WAYS, restatement  # noqa: E402
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir  # noqa: E402
from epinoic_logic.stem import build_document, clear_document_cache  # noqa: E402
from epinoic_logic.stem.checks import build_checks  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
MA_REQ = R7["maa-t13"]["question"]
INFER = {"kind": "specialist_inference"}


def _pack_text(name: str) -> str:
    return (installed_pack_dir(PACK_VERSION) / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _V(name: str) -> dict:
    return {"op": "var", "name": name}


def _n(v: str, op: str = "real") -> dict:
    return {"op": op, "value": v}


def _problem(premise: dict, conclusion: dict, symbols: dict[str, str], grounding: dict = INFER) -> Problem:
    return Problem.model_validate({"problem_id": "p-arith", "request_id": "req-ovs", "claim_id": "en-point", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s} for n, s in symbols.items()],
                                   "premises": [{"id": "P", "expr": premise, "grounding": grounding}],
                                   "conclusion": {"id": "C", "expr": conclusion}})


def _report():
    return T.english_report()


# ============================================================================================ rule arithmetic-restatement
_C2 = {"op": "eq", "left": _V("contrib"), "right": _n("2.00")}
_P100 = {"op": "eq", "left": _V("pct"), "right": _n("100")}
_PD = {"op": "eq", "left": _V("pd"), "right": _n("60.4")}


@pytest.mark.parametrize("premise, conclusion, symbols", [
    # the tester's forms
    ({"op": "eq", "left": {"op": "sub", "left": _V("contrib"), "right": _n("2.00")}, "right": _n("0")}, _C2, {"contrib": "Real"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("contrib")]}, "right": _n("4.00")}, _C2, {"contrib": "Real"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("pct")]}, "right": _n("200")}, _P100, {"pct": "Real"}),
    ({"op": "eq", "left": {"op": "sub", "left": _V("pd"), "right": _n("60.4")}, "right": _n("0")}, _PD, {"pd": "Real"}),
    # the class: scaled and shifted, divided, reversed, the conjunct itself in another form, an Int symbol, a conjunct of a conjunction
    ({"op": "eq", "left": {"op": "sub", "left": {"op": "mul", "args": [_n("2"), _V("v")]}, "right": _n("4.0")}, "right": _n("15.8")},
     {"op": "eq", "left": _V("v"), "right": _n("9.9")}, {"v": "Real"}),
    ({"op": "eq", "left": {"op": "div", "left": _V("contrib"), "right": _n("4")}, "right": _n("0.50")}, _C2, {"contrib": "Real"}),
    ({"op": "eq", "left": _n("0"), "right": {"op": "sub", "left": _V("contrib"), "right": _n("2.00")}}, _C2, {"contrib": "Real"}),
    (_C2, {"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("contrib")]}, "right": _n("4.00")}, {"contrib": "Real"}),
    ({"op": "eq", "left": {"op": "add", "args": [{"op": "mul", "args": [_n("3", "int"), _V("n")]}, _n("20", "int")]}, "right": _n("260", "int")},
     {"op": "eq", "left": _V("n"), "right": _n("80", "int")}, {"n": "Int"}),
    ({"op": "and", "args": [{"op": "eq", "left": {"op": "sub", "left": _V("contrib"), "right": _n("2.00")}, "right": _n("0")}, {"op": "bool", "value": True}]},
     _C2, {"contrib": "Real"}),
])
def test_a_premise_that_is_the_conjunct_rewritten_by_the_arithmetic_of_its_own_symbols_restates_it(premise, conclusion, symbols):
    """The translator's rule reads a restatement as written only, so it delivers each; the overseer's arithmetic reading reads it as the
    conjunct restated (before: no reading did, every arithmetic term opaque)."""
    prob = _problem(premise, conclusion, symbols)
    assert translator_circular_premises(prob) == []
    rs = restatement(prob, _report(), [])
    assert rs.holds and rs.own == ("P",) and dict(rs.how)["P"] == ("arithmetic",), rs
    assert "arithmetic" in SEMANTIC_WAYS and "terms moved across, both sides scaled" in RESTATEMENT_WAYS["arithmetic"]


@pytest.mark.parametrize("premise, conclusion, symbols", [
    # a line of working on numbers alone: the derivation the engine checks (the probe control's)
    ({"op": "eq", "left": _V("pct"), "right": {"op": "mul", "args": [{"op": "div", "left": {"op": "sub", "left": _n("80"), "right": _n("40")}, "right": _n("40")},
                                                                     _n("100")]}}, _P100, {"pct": "Real"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("contrib")]}, "right": {"op": "mul", "args": [_n("2"), _n("2.00")]}}, _C2, {"contrib": "Real"}),
    ({"op": "eq", "left": _V("contrib"), "right": {"op": "div", "left": _n("4.00"), "right": _n("2")}}, _C2, {"contrib": "Real"}),
    # not equivalent to the conjunct: another value, a bound, a product of two symbols, another symbol
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("contrib")]}, "right": _n("4.20")}, _C2, {"contrib": "Real"}),
    ({"op": "ge", "left": {"op": "mul", "args": [_n("2"), _V("contrib")]}, "right": _n("4.00")}, _C2, {"contrib": "Real"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_V("contrib"), _V("k")]}, "right": _n("4.00")}, _C2, {"contrib": "Real", "k": "Real"}),
    ({"op": "eq", "left": {"op": "sub", "left": _V("other"), "right": _n("2.00")}, "right": _n("0")}, _C2, {"contrib": "Real", "other": "Real"}),
])
def test_arithmetic_of_numbers_alone_and_a_premise_not_equivalent_restate_nothing(premise, conclusion, symbols):
    rs = restatement(_problem(premise, conclusion, symbols), _report(), [])
    assert not rs.holds and rs.own == () and rs.how == (), rs


# ============================================================================================ rule identity-statement (OVS-FORM-005)
def _identity_check(line: str, *, bound: bool):
    """The check the STEM pack plans for ``line`` appended to maa-t13's recorded answer, with rule identity-variable as shipped or undone
    (the tamper case T23bq's patch): ``(problem, description)``."""
    import epinoic_logic.stem.checks as stem_checks
    text = R7["maa-t13"]["response_text"].replace("Marks shown are a provisional allocation.", line + "\nMarks shown are a provisional allocation.")
    step = T._identity_bound(stem_checks._step) if bound else stem_checks._step
    with H.patched((stem_checks, "_step", step), (stem_checks, "_BUILDERS", {**stem_checks._BUILDERS, "alg": step})):
        clear_document_cache()
        plan = build_checks(build_document(text, MA_REQ, "mathematics_aa"), report_id="r", request_id="q")
    clear_document_cache()
    (pc,) = [pc for pc in plan.checks if line.split(" is ", 1)[-1].rstrip(".").replace("Also ", "") in pc.description]
    return pc.problem, pc.description


@pytest.mark.parametrize("line", ["The rate of change of a is d/dt (6 − 6t) = −6t.", "Also ∫4t dt = 4t.", "Also ∫₀¹ 4t dt = [4t]₀¹."])
def test_rule_identity_statement_reads_the_bindings_of_an_identity_s_variable(line):
    """As shipped, the identity's problem holds no binding of its variable, so the rule names nothing; with rule identity-variable undone,
    the request's 't = 1' is bound again and the rule names it, the variable read from the check's own statement ('for every value of t',
    which the derivative, the antiderivative and the definite integral's bracket each state)."""
    problem, description = _identity_check(line, bound=False)
    assert "for every value of t" in description and identity_variables(description) == ["t"]
    assert identity_bindings(problem, description) == []
    problem, description = _identity_check(line, bound=True)
    assert identity_bindings(problem, description) == ["B_s_t"]  # the report's symbol t, as the builder declares it


def test_rule_identity_statement_names_no_constant_the_identity_does_not_quantify_and_no_other_step():
    """A constant the answer gives a value may be bound in an identity (its variable is t, not a); a step from a stated relation binds the
    values it substitutes; a statement naming no variable, and malformed data, name nothing."""
    prev = {"id": "PREV", "expr": {"op": "eq", "left": _V("l"), "right": _V("l")}, "label": "the preceding relation"}
    symbols = [{"name": "s_t", "sort": "Real", "meaning": "the symbol 't' as written in the report"},
               {"name": "s_a", "sort": "Real", "meaning": "the symbol 'a' as written in the report"}]
    bind_a = {"id": "B_s_a", "expr": {"op": "eq", "left": _V("s_a"), "right": _n("3")}, "label": "a = 3 (statement, s1.1)"}
    bind_t = {"id": "B_s_t", "expr": {"op": "eq", "left": _V("s_t"), "right": _n("1")}, "label": "t = 1 (request, s1.3)"}
    formula_t = {"id": "FORMULA", "expr": {"op": "eq", "left": _V("s_t"), "right": _n("1")}, "label": "the formula t = 2·u stated in s1.2"}
    stated = "compared: a derivative: … against the stated expression, for every value of t (rule derivative)"
    assert identity_bindings({"symbols": symbols, "premises": [bind_a, prev]}, stated) == []
    assert identity_bindings({"symbols": symbols, "premises": [bind_a, bind_t, prev]}, stated) == ["B_s_t"]
    assert identity_bindings({"symbols": symbols, "premises": [formula_t, prev]}, stated) == ["FORMULA"]
    assert identity_bindings({"symbols": symbols, "premises": [bind_t, prev]}, "the algebraic step: 'x'; readings: as written") == []
    assert identity_variables("an identity, stated for every value of t, x: no binding; holds for every value of the variable") == ["t", "x"]
    clear_document_cache()
    plan = build_checks(build_document(R7["ph-t13"]["response_text"], R7["ph-t13"]["question"], "physics"), report_id="r", request_id="q")
    step = [pc for pc in plan.checks if "'1/R = 1/4.0 Ω + 1/6.0 Ω'" in pc.description]
    assert len(step) == 1 and [p["id"] for p in step[0].problem["premises"] if p["id"].startswith("B_")]
    assert identity_bindings(step[0].problem, step[0].description) == []
    for bad in (None, "x", {"premises": "x"}, {"premises": [{"id": "PREV", "expr": {"op": "eq", "left": 1, "right": 1}}, {"id": "B_t"}]}):
        assert identity_bindings(bad, stated) == []
    assert IDENTITY_RULE == "identity-statement"


def test_ovs_form_005_is_a_formal_status_error_its_kind_s_check_confirms():
    sev, area, text = OVS_CODES["OVS-FORM-005"]
    assert sev == "error" and area == "formal" and "rule identity-statement" in text and "for every value of its variable" in text
    assert "OVS-FORM-005" in KIND_CHECKS["formal_status_wrong"]


# ============================================================================================ the probes and the tamper cases
#: each plant of the twelfth independent test, and of the shapes of its classes found closing them, with the code that must name it
REPAIR12_PROBES = {
    "maths-derivative-request-value": ("INT-SUBJ-001",), "maths-derivative-linear": ("INT-SUBJ-001",), "maths-antiderivative-request-value": ("INT-SUBJ-001",),
    "maths-definite-bracket-request-value": ("INT-SUBJ-001",), "givens-function-request-value": ("INT-SUBJ-004",),
    "boolean-hex-opening": ("INT-SUBJ-001",), "boolean-hex-subscript": ("INT-SUBJ-001",), "boolean-hex-base16": ("INT-SUBJ-001",),
    "boolean-hex-words": ("INT-SUBJ-001",), "boolean-hex-before": ("INT-SUBJ-001",), "boolean-hex-letters": ("INT-SUBJ-001",),
    "boolean-hex-equals": ("INT-SUBJ-001",), "boolean-base-no-comma": ("INT-SUBJ-001",),
    "rounding-approx-which-is": ("INT-SUBJ-001",), "rounding-approx-stated": ("INT-SUBJ-001",), "rounding-approx-percent": ("INT-SUBJ-001",),
}
#: the translation plants of rule arithmetic-restatement (OVS-TRN-006, the pack's translation_circular confirmed)
REPAIR12_TRANSLATIONS = ("equations-translation-restated-affine", "maths-translation-restated-scaled", "physics-translation-restated-linear",
                         "boolean-translation-restated-affine")
#: the correct writing of each, which must stay clean (the two false failures on correct working of rule prose-base among them)
REPAIR12_CONTROLS = ("maths-derivative-request-value-control", "maths-derivative-linear-control", "maths-antiderivative-request-value-control",
                     "maths-definite-bracket-request-value-control", "givens-function-request-value-control", "boolean-hex-opening-control",
                     "boolean-hex-subscript-control", "boolean-hex-before-control", "boolean-hex-letters-control", "boolean-hex-unnamed-control",
                     "boolean-hex-equals-control", "boolean-base-no-comma-control", "rounding-approx-which-is-control", "rounding-approx-stated-control",
                     "rounding-approx-percent-control", "maths-translation-working-control")
FALSE_FAILURES_BEFORE = ("boolean-hex-equals-control", "boolean-base-no-comma-control")
#: STEM repair 12's receipt cases, their classes, the plant each runs on and the codes it must raise
REPAIR12_CASES = {
    "T23bq": ("formal_status_wrong", "maths", "r7/maa-t13", "maths-derivative-request-value", ["OVS-FORM-005"]),
    "T23br": ("receipt_altered", "maths", "r7/maa-t13", "maths-antiderivative-request-value", ["OVS-RCPT-007"]),
    "T23bs": ("finding_missing", "boolean", "r7/cs-t13", "boolean-hex-letters", ["OVS-RCPT-004"]),
    "T23bt": ("formal_status_wrong", "rounding", "r7/ph-t13", "rounding-approx-which-is", ["OVS-FORM-001", "OVS-FORM-002"]),
}


def test_every_plant_of_the_twelfth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR12_PROBES) == len(REPAIR12_PROBES) + len(REPAIR12_TRANSLATIONS) + len(REPAIR12_CONTROLS) == 36
    assert {p.probe_id for p in SP.REPAIR12_PROBES} == set(REPAIR12_PROBES) | set(REPAIR12_TRANSLATIONS) | set(REPAIR12_CONTROLS)
    for pid, expected in REPAIR12_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES and not p.translator_gap, pid
    for pid in REPAIR12_TRANSLATIONS:
        p = SP.probe(pid)
        assert p.kind == "translation" and p.expected == ("OVS-TRN-006",) and p.agent_kind == "translation_circular" and p.agent_outcome == "confirmed", pid
        assert p.translation[2].startswith("restate:"), pid
    for pid in REPAIR12_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert set(FALSE_FAILURES_BEFORE) <= set(REPAIR12_CONTROLS)
    for cls in ("maths", "givens", "boolean", "rounding"):
        assert {p.kind for p in SP.REPAIR12_PROBES if p.fault_class == cls} >= {"answer", "control"}, cls
    assert SP.PROBES[641:] == SP.REPAIR12_PROBES and len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677
    # the second translator merge closed the one translator gap (maths-finance-value: the closed powers): none remains (stricter)
    assert [p.probe_id for p in SP.PROBES if p.translator_gap] == []


def test_the_restatement_plants_write_the_conclusion_in_another_form_with_each_number_one_numeral():
    """The planter is data only: the derivation premise removed and the conclusion 'x = v' restated, terms moved across, both sides scaled,
    or both, each number written as one numeral of the conclusion's sort."""
    real = {"premises": [{"id": "d", "expr": {"op": "var", "name": "q"}}], "conclusion": {"expr": {"op": "eq", "left": _V("x"), "right": _n("2.5")}}}
    whole = {"premises": [{"id": "d", "expr": {"op": "var", "name": "q"}}], "conclusion": {"expr": {"op": "eq", "left": _V("n"), "right": _n("80", "int")}}}
    got = SP._plant(real, "restate:affine:d", "c")
    assert [p["id"] for p in got["premises"]] == ["P_restated"] and got["premises"][0]["grounding"]["kind"] == "specialist_inference"
    assert got["premises"][0]["expr"] == {"op": "eq", "left": {"op": "sub", "left": _V("x"), "right": _n("2.5")}, "right": _n("0")}
    assert SP._plant(real, "restate:scaled:d:2", "c")["premises"][0]["expr"] == {"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("x")]}, "right": _n("5")}
    assert SP._plant(whole, "restate:linear:d:3:20", "c")["premises"][0]["expr"] == {
        "op": "eq", "left": {"op": "sub", "left": {"op": "mul", "args": [_n("3", "int"), _V("n")]}, "right": _n("20", "int")}, "right": _n("220", "int")}
    with pytest.raises(H.HarnessError):
        SP._plant(real, "restate:affine:missing", "c")


def test_the_repair_12_tamper_cases_are_registered_on_their_targets():
    by_name = {c.name: c for c in T.CASES}
    for case, (cls, probe_class, _target, plant, _codes) in REPAIR12_CASES.items():
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
        assert case in SP.TAMPER_CASES[probe_class] and SP.probe(plant).fault_class == probe_class, case
    assert SP.TAMPER_CASES["maths"][-2:] == ("T23bq", "T23br") and SP.TAMPER_CASES["boolean"][-1] == "T23bs"
    assert SP.TAMPER_CASES["rounding"][-1] == "T23bt"
    # the synthetic restatement cases and their control
    for name in ("T22ag", "T22ah", "T22ai"):
        assert T.TRN_CASES[name][:3] == ("translation_circular", "OVS-TRN-006", "P_assumed") and name in T.ARITH_FORM_CASES
    assert "T22-working" in T.WORKING_CONTROLS


def test_the_rewrite_t23br_uses_drops_the_identity_clause_alone():
    detail = ("the algebraic step: '∫4t dt = 4t'; Form E; readings: as written; an identity, stated for every value of t: no binding or formula of "
              "it is included, so it is decided for every value (rule identity-variable); solver COUNTEREXAMPLE")
    out = T._without_clause("identity-variable")(detail)
    assert "rule identity-variable" not in out and "readings: as written" in out and out.endswith("; solver ENTAILED")


@pytest.mark.timeout(2400)
def test_the_repair_12_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the two false failures among them), no forbidden code. The translation plant on the
    recorded translation the material keeps (cs-t13's) is named OVS-TRN-006 and an agent built from the exported pack accusing it as
    translation_circular is CONFIRMED (before: REFUTED)."""
    rnd = material_round(tmp_path / "rounds")
    pack = H.export_and_load_pack(tmp_path / "pack")[0]
    chosen = tuple(p for p in SP.REPAIR12_PROBES if p.translation is None) + (SP.probe("boolean-translation-restated-affine"),)
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, pack=pack, probes=chosen)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid, expected in REPAIR12_PROBES.items():
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
        assert set(expected) & set(r["named_by"]), (pid, r["named_by"])
    for pid in [c for c in REPAIR12_CONTROLS if c != "maths-translation-working-control"]:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    r = rows["boolean-translation-restated-affine"]
    assert r["outcome"] == "named" and "OVS-TRN-006" in r["named_by"] and r["agent"]["outcome"] == "confirmed" and SP.probe_ok(r), r
    assert doc["gate"]["failing"] == [] and doc["gate"]["translator_gaps"] == []


# ============================================================================================ the pack beside the code
def test_i77_k6_and_the_kinds_table_state_the_arithmetic_reading_and_its_examples_hold():
    i77 = _section(_pack_text("03-inspection.md"), "**I77 ", "\n- **I78")
    k6 = _section(_pack_text("06-kinds-and-codes.md"), "**K6 ", "\n- **K7")
    kinds = _pack_text("06-kinds-and-codes.md")
    assert ("Or the premise is the conjunct rewritten by arithmetic on its own symbols, true for exactly the same values: its terms moved across, "
            "or both sides multiplied or divided by the same number, `x - 2.00 eq 0` and `2 * x eq 4.00` restate `x eq 2.00`, and `2 * x + 3 eq 7` "
            "restates `x eq 2` (rule arithmetic-restatement).") in i77
    assert "Arithmetic on numbers is no restatement: a premise that gives the conjunct only by the arithmetic it writes on numbers alone" in i77
    assert "the conjunct rewritten by arithmetic on its own symbols, `x - 2.00 eq 0` or `2 * x eq 4.00` for `x eq 2.00`" in k6
    assert "its terms moved across or both sides scaled), by a premise that is the writer's own" in kinds
    x2 = {"op": "eq", "left": _V("x"), "right": _n("2.00")}
    for premise, conclusion in (({"op": "eq", "left": {"op": "sub", "left": _V("x"), "right": _n("2.00")}, "right": _n("0")}, x2),
                                ({"op": "eq", "left": {"op": "mul", "args": [_n("2"), _V("x")]}, "right": _n("4.00")}, x2),
                                ({"op": "eq", "left": {"op": "add", "args": [{"op": "mul", "args": [_n("2", "int"), _V("x")]}, _n("3", "int")]}, "right": _n("7", "int")},
                                 {"op": "eq", "left": _V("x"), "right": _n("2", "int")})):
        sort = "Int" if conclusion["right"]["op"] == "int" else "Real"
        rs = restatement(_problem(premise, conclusion, {"x": sort}), _report(), [])
        assert rs.holds and dict(rs.how)["P"] == ("arithmetic",), premise
    a = {"op": "eq", "left": _V("a"), "right": {"op": "div", "left": {"op": "sub", "left": _n("20"), "right": _n("0")}, "right": _n("4.0")}}
    assert not restatement(_problem(a, {"op": "eq", "left": _V("a"), "right": _n("5.0")}, {"a": "Real"}), _report(), []).holds


def test_d31_i97_i98_the_master_prompt_and_the_mistakes_rows_name_the_new_rules():
    d31 = _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")
    i97 = _section(_pack_text("03-inspection.md"), "**I97 ", "\n- **I98")
    i98 = _section(_pack_text("03-inspection.md"), "**I98 ", "\n<!-- end module: stem -->")
    prompt, dossier, kinds = _pack_text("master_prompt.txt"), _pack_text("02-dossier.md"), _pack_text("06-kinds-and-codes.md")
    for words in ('"d/dt (6 − 6t) = −6t", "∫6t dt = 6t" and "∫₀¹ 6t dt = [6t]₀¹" fail (INT-SUBJ-001) and "Given: v(t) = 3." fails (INT-SUBJ-004)',
                  'the `detail` saying "rule identity-variable"', "holds no binding (`B_…`) or `FORMULA` premise of that variable (rule identity-statement",
                  '"= 2.67 A, which is about 2.6 A", "= 2.67 A, about 2.6 A to 2 s.f." and "= 37.7%, about 37%" fail',
                  '"In hexadecimal, 255 is FE." fail, "In hexadecimal, 255 is FF." holds', '("255 is FF." is not read)',
                  '("In binary 1000 is 1111101000." and "In octal 64 is 100." hold, "In hexadecimal, the number 1000 is 3E9." fails)',
                  '("1000 = 3E8 in hexadecimal.", "1000 = 1111101000 in binary." and "255 = FF in hexadecimal." hold, "1000 = 3E9 in hexadecimal." fails)',
                  "A restated result is the one exception"):
        assert words in d31, words
    for rule in ("identity-variable", "prose-base", "inline-restatement"):
        assert f"rule {rule}" in i97, rule
    assert "An identity check whose `problem` gives its variable a value is no such check (I98)" in i97
    assert "kind `formal_status_wrong` (the checks report OVS-FORM-005, rule identity-statement" in i98
    for rule in ("identity-variable", "identity-statement", "prose-base", "inline-restatement"):
        assert f"rule {rule}" in prompt, rule
    assert "OVS-FORM-004, OVS-FORM-005 |" in kinds
    assert ('| Reading an identity as holding because its two sides agree at the request\'s value of its variable ("d/dt (6 − 6t) = −6t" where the request '
            'gives t = 1)') in dossier


@pytest.mark.parametrize("text, profile, req, holds", [
    # D31's examples of this repair, each decided as it says
    ("d/dt (6 − 6t) = −6t", "mathematics_aa", MA_REQ, False), ("∫6t dt = 6t", "mathematics_aa", MA_REQ, False),
    ("∫₀¹ 6t dt = [6t]₀¹", "mathematics_aa", MA_REQ, False), ("Given: v(t) = 3.", "mathematics_aa", MA_REQ, False),
    ("In hexadecimal, 1000 is 3E9.", "computer_science", None, False), ("In base 16, 1000 is 3E9.", "computer_science", None, False),
    ("1000 in denary is 3E9 in hexadecimal.", "computer_science", None, False), ("The hexadecimal number 3E9 is 1000 in denary.", "computer_science", None, False),
    ("In hexadecimal, 255 is FE.", "computer_science", None, False), ("In hexadecimal, 255 is FF.", "computer_science", None, True),
    ("In hexadecimal, 1000 is 3E9₁₆.", "computer_science", None, False), ("In binary 1000 is 1111101000.", "computer_science", None, True),
    ("In octal 64 is 100.", "computer_science", None, True), ("In hexadecimal, the number 1000 is 3E9.", "computer_science", None, False),
    ("1000 = 3E8 in hexadecimal.", "computer_science", None, True), ("1000 = 1111101000 in binary.", "computer_science", None, True),
    ("255 = FF in hexadecimal.", "computer_science", None, True), ("1000 = 3E9 in hexadecimal.", "computer_science", None, False),
])
def test_d31_s_examples_alone_are_decided_as_it_says(text, profile, req, holds):
    from tests.stem.test_stem_repair5 import decide, failing
    from tests.stem.test_stem_repair5 import holds as check_holds
    checks, _f = decide(text, req, profile)
    assert len(checks) == 1 and check_holds(checks[0]) is holds, (text, checks)
    assert failing(checks) == ([] if holds else checks), (text, checks)
    if "d/dt" in text or "∫" in text or "Given" in text:
        assert "(rule identity-variable)" in checks[0][3], checks
    else:
        assert "(rule prose-base)" in checks[0][3], checks


def test_d31_s_numeral_no_word_names_the_base_of_is_not_read():
    from tests.stem.test_stem_repair5 import decide
    assert '("255 is FF." is not read)' in _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")
    assert decide("255 is FF.", None, "computer_science")[0] == [] and decide("The largest byte value, 255, is FE.", None, "computer_science")[0] == []
