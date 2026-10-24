"""Safety of the checks stage (docs/STEM_DESIGN.md, sections 7, 13 and 14).

* An undefined expression gives ST-UNDEF-001 and no problem is built.
* No Form S problem has a free symbol: every symbol is pinned, interval-bounded or an auxiliary
  defined by a premise, so nothing is vacuously satisfiable.
* Every literal of every built problem has at most 40 digits, and every problem validates.
* Failures are contained: an internal error, or an enclosure that fails its cross-check, is
  ST-INTERNAL-001 for that check alone.
* A relation whose operand was cut from a longer expression is withheld, never decided.
* The stage's modules evaluate nothing and import only the allowlist.
* Adversarial input (malformed LaTeX, unbalanced brackets, 10^10^10, 10,000-digit numbers,
  nesting depth 500, Unicode confusables, control characters, relation storms) never raises,
  stays within its time bound, and builds only valid problems.
"""
from __future__ import annotations

import ast
import glob
import json
import time
from pathlib import Path

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem import checks as checks_module
from epinoic_logic.stem import to_ir as to_ir_module
from epinoic_logic.stem.checks import CheckPlan, build_checks
from epinoic_logic.stem.scaling import digit_count

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "epinoic_logic" / "stem"
CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "stem" / "corpus"
STAGE_MODULES = ("constants", "enclosures", "scaling", "tolerance", "to_ir", "checks")


def plan_of(text: str, request: str | None = None, profile: str = "physics", **kw) -> CheckPlan:
    return build_checks(build_document(text, request, profile), report_id="r1", request_id="q1", **kw)


def _walk(expr: dict):
    stack = [expr]
    while stack:
        node = stack.pop()
        yield node
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            if isinstance(node.get(key), dict):
                stack.append(node[key])
        stack.extend(a for a in node.get("args", []) if isinstance(a, dict))


def _vars(expr: dict) -> set[str]:
    return {n["name"] for n in _walk(expr) if n.get("op") == "var"}


# --------------------------------------------------------------------------- undefined expressions


@pytest.mark.parametrize("text,profile", [
    ("x = (7 − 3)/(2 − 2) = 4", "physics"),
    ("y = √(3 − 5) = 1", "physics"),
    ("The pH is −log(0) = 7.", "chemistry"),
    ("tan 90° = 1", "mathematics_aa"),
    ("arcsin(1.5) = 0.5", "mathematics_aa"),
    ("z = 0^0 = 1", "mathematics_aa"),
    ("q = 5/0 = 2", "mathematics_aa"),
])
def test_undefined_expressions_build_no_problem(text, profile):
    plan = plan_of(text, profile=profile)
    assert not plan.checks
    f = plan.finding_for("stem-eq-1")
    assert f is not None and f.code == "ST-UNDEF-001" and f.severity == "warning" and f.statement_ids


# --------------------------------------------------------------------------- built problems


def _all_plans() -> list[tuple[str, CheckPlan]]:
    out = []
    for fn in sorted(glob.glob(str(CORPUS / "*.json"))):
        d = json.loads(Path(fn).read_text(encoding="utf-8"))
        subj = d["subject"]
        prof = {"Physics": "physics", "Chemistry": "chemistry", "Biology": "biology", "Environmental Systems and Societies": "ess"}.get(subj) or (
            "mathematics_ai" if "Applications" in subj else "mathematics_aa")
        out.append((d["id"], plan_of(d["response_text"], d["question"], prof)))
    extra = [
        ("enc", "The component is 10 × sin 25° = 4.23 N.", "physics"),
        ("booklet", "E = hf = 3.3 × 10⁻¹⁹ J with f = 5.0 × 10¹⁴ Hz.", "physics"),
        ("carried", "a = 9.7/2.0 = 4.85 m s⁻² ≈ 5 m s⁻². So F = ma = 3.0 × 5 = 14.6 N.", "physics"),
        ("roots", "x² − 3x + 1 = 0 gives x = 2.62.", "mathematics_aa"),
        ("constants", "n = N/N_A = 1.204 × 10²⁴ / 6.02 × 10²³ = 2.00 mol", "chemistry"),
    ]
    for name, text, prof in extra:
        out.append((name, plan_of(text, profile=prof)))
    return out


PLANS = _all_plans()
_ANCHORS = ("C_DEF", "R", "X_LO", "X_HI", "ENC_LO", "ENC_HI", "B_", "Q_DEF", "S_SQ", "P_DEF", "W", "L_DEF", "R_DEF", "EQ", "K_", "ROW_", "NEG")


def test_no_free_symbol_in_a_satisfiability_problem():
    seen = 0
    for name, plan in PLANS:
        for pc in plan.checks:
            if pc.form != "S":
                continue
            seen += 1
            prob = pc.problem
            anchored: set[str] = set()
            for p in prob["premises"]:
                if p["id"].startswith(_ANCHORS):
                    anchored |= _vars(p["expr"])
            for s in prob["symbols"]:
                assert s["name"] in anchored, (name, pc.check_id, s["name"])
            # every interval or enclosure symbol has both bounds
            for s in prob["symbols"]:
                n = s["name"]
                if n.startswith(("x_", "enc_", "root_")):
                    ids = {p["id"] for p in prob["premises"] if n in _vars(p["expr"])}
                    assert any(i.startswith(("X_LO", "ENC_LO")) for i in ids) and any(i.startswith(("X_HI", "ENC_HI")) for i in ids), (name, n)
    assert seen > 30


def test_every_problem_validates_and_every_literal_is_bounded():
    for name, plan in PLANS:
        for pc in plan.checks:
            Problem.model_validate(pc.problem)
            exprs = [p["expr"] for p in pc.problem["premises"]] + ([pc.problem["conclusion"]["expr"]] if pc.problem.get("conclusion") else [])
            for e in exprs:
                for node in _walk(e):
                    if node.get("op") in ("real", "int"):
                        assert digit_count(node["value"]) <= 40, (name, pc.check_id, node["value"])
            assert pc.inconsistent_is_failure is False
            assert pc.expected_if_sound in ("ENTAILED", "SATISFIABLE", "UNSATISFIABLE")
            assert len(pc.description) <= 1200


def test_findings_are_never_errors():
    for _name, plan in PLANS:
        for f in plan.findings:
            assert f.severity in ("warning", "info") and f.code.startswith("ST-") and f.check_id


# --------------------------------------------------------------------------- contained failures


def test_an_internal_failure_is_st_internal_001_for_that_check_alone(monkeypatch):
    def boom(ctx):
        raise RuntimeError("injected")

    monkeypatch.setitem(checks_module._BUILDERS, "eq", boom)
    plan = plan_of("Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J.")
    f = plan.finding_for("stem-eq-1")
    assert f is not None and f.code == "ST-INTERNAL-001" and "RuntimeError" in f.message
    assert plan.check("stem-sub-1") is not None


def test_an_enclosure_that_fails_its_cross_check_builds_no_check(monkeypatch):
    clear_document_cache()
    monkeypatch.setattr(to_ir_module, "cross_check", lambda *a, **k: False)
    plan = plan_of("The component is 10 × sin 25° = 4.23 N.")
    f = plan.finding_for("stem-eq-1")
    assert f is not None and f.code == "ST-INTERNAL-001" and "cross-check" in f.message
    assert plan.check("stem-eq-1") is None


def test_too_many_readings_is_st_parse_002():
    plan = plan_of("F = 2.0 × sin(30) × 20 ms⁻¹ = 20 m s⁻¹")
    f = plan.finding_for("stem-eq-1")
    assert f is not None and f.code == "ST-PARSE-002"


def test_a_cut_operand_is_withheld():
    plan = plan_of("y(x + 1) = 3x − 2\nxy + y = 3x − 2\nxy − 3x = −2 − y", profile="mathematics_aa")
    codes = {f.check_id: f.code for f in plan.findings}
    assert codes.get("stem-alg-1") == "ST-PARSE-001" and codes.get("stem-alg-2") == "ST-PARSE-001"
    assert not any(pc.relation_kind == "alg" for pc in plan.checks)
    # a signed operand after a prose word or a relation sign is whole
    whole = plan_of("Then −2x > 4 so −x > 2", profile="mathematics_aa")
    assert not any(f.code == "ST-PARSE-001" for f in whole.findings)


@pytest.mark.parametrize("text,profile", [
    ("с = 3.0 × 10⁸ and x = 1Ο + 2 = 3 and ａ = 5 and ℎ = 6.63 × 10⁻³⁴", "physics"),   # confusable and fullwidth letters break the chain
    ("x = 1\x00 + 2 = 3 and y = 2\u202e + 3 = 5", "physics"),                       # control characters split an expression
    ("y(x + 1) = 3x − 2\nxy + y = 3x − 2\nxy − 3x = −2 − y\nx(y − 3) = −2 − y", "mathematics_aa"),  # 'xy' dropped by the span finder
])
def test_misread_correct_input_is_withheld_never_failed(text, profile):
    from epinoic_logic.engine.policies import policy_config, policy_limits
    from epinoic_logic.engine.results import SolverConfig
    from epinoic_logic.engine.runner import verify

    plan = plan_of(text, profile=profile)
    cfg = SolverConfig(timeout_ms=10000, memory_max_mb=None)
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, cfg), limits=policy_limits(pc.policy))
        assert res.status.value == pc.expected_if_sound, (pc.check_id, res.status.value, pc.description)
    assert any(f.code == "ST-PARSE-001" for f in plan.findings)


def test_a_prose_bridge_between_two_sides_is_withheld_but_verbal_arithmetic_is_read():
    plan = plan_of("The mass is 3 and ａ = 5.", profile="physics")
    assert not any(pc.relation_kind == "eq" for pc in plan.checks)
    verbal = plan_of("2.0 times 3.0 is equal to 6.0.", profile="physics")
    assert verbal.check("stem-eq-1") is not None


def test_relay_builds_no_given_or_target_check():
    text = "Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J."
    req = "A 2.0 kg ball moves at 3.0 m s⁻¹. Show that its kinetic energy is about 9 J."
    full = plan_of(text, req)
    assert {pc.relation_kind for pc in full.checks} >= {"giv", "tgt"}
    relay = plan_of(text, req, relay=True)
    assert not {pc.relation_kind for pc in relay.checks} & {"giv", "tgt"}


# --------------------------------------------------------------------------- no evaluation, import allowlist

_FORBIDDEN_NAMES = frozenset({"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "open", "input", "breakpoint", "setattr", "delattr"})
_FORBIDDEN_ATTRS = frozenset({"eval", "exec", "sympify", "parse_expr", "literal_eval", "loads", "load", "system", "popen", "import_module", "__subclasses__",
                              "__globals__", "__builtins__", "__code__", "run_path", "run_module"})
_STDLIB = frozenset({"__future__", "re", "fractions", "dataclasses", "functools", "typing", "hashlib", "unicodedata", "math", "enum", "types"})


@pytest.mark.parametrize("module", STAGE_MODULES)
def test_stage_modules_evaluate_nothing(module):
    path = PACKAGE / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    stem_modules = {p.stem for p in PACKAGE.glob("*.py")}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in _FORBIDDEN_NAMES, (module, node.lineno, node.id)
        elif isinstance(node, ast.Attribute):
            assert node.attr not in _FORBIDDEN_ATTRS, (module, node.lineno, node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in _STDLIB, (module, alias.name)
                if alias.name == "math":
                    assert module == "enclosures", "math is used for the enclosure routines and their cross-check only"
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert (node.module or "").split(".")[0] in _STDLIB, (module, node.module)
            else:
                assert node.level == 1 and (node.module or "").split(".")[0] in stem_modules, (module, node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Fraction":
            for arg in node.args:
                assert not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)), (module, node.lineno, "Fraction built from text")


# --------------------------------------------------------------------------- adversarial input

ADVERSARIAL = [
    ("latex-unclosed-frac", "$\\frac{1}{2 = 3$ and $\\sqrt{2 = 1.41$", "physics"),
    ("latex-nested", "$$" + "\\frac{" * 200 + "1" + "}{2}" * 200 + " = 0.5$$", "mathematics_aa"),
    ("latex-left-right", "\\[ \\left( 1 + 2 = 3 \\]", "mathematics_aa"),
    ("latex-unknown", "$\\foo{x} = 3$ and $\\int_0^1 x\\,dx = 0.5$", "mathematics_aa"),
    ("unbalanced-open", "((((1 + 2 = 3", "physics"),
    ("unbalanced-close", "1 + 2)))) = 3", "physics"),
    ("unbalanced-mixed", "x = [(1 + 2] = 3)", "physics"),
    ("tower", "v = 10^10^10 = 5 m", "physics"),
    ("huge-exponent", "x = 1.0 × 10⁹⁹⁹⁹ = 1 and y = 2^999 = 1 and z = 1e999 = 5", "physics"),
    ("near-bound-exponents", "y = 1.0 × 10⁹⁹ × 1.0 × 10⁹⁹ = 1.0 × 10¹⁹⁸ and w = 1.0 × 10⁻⁹⁹ + 1.0 × 10⁹⁹ = 1.0 × 10⁹⁹", "physics"),
    ("10000-digits", "n = " + "9" * 10000 + " = 1 and m = 0." + "3" * 10000 + " = 0.3", "physics"),
    ("depth-500", "x = " + "(" * 500 + "1" + ")" * 500 + " = 1", "mathematics_aa"),
    ("depth-500-roots", "x = " + "√(" * 500 + "2" + ")" * 500 + " = 1", "mathematics_aa"),
    ("confusables", "с = 3.0 × 10⁸ and x = 1Ο + 2 = 3 and ａ = 5 and ℎ = 6.63 × 10⁻³⁴", "physics"),
    ("control", "x = 1\x00 + 2 = 3 and y = 2‮ + 3 = 5", "physics"),
    ("relation-storm", " = ".join(["1.0"] * 200), "physics"),
    ("long-sum", "P = " + " + ".join(["1.5 W"] * 300) + " = 450 W", "physics"),
    ("e-storm", "x = 1e1e1e = 2 and y = 1E-99999 = 0", "physics"),
    ("functions-out-of-range", "sin(10^9) = 0.5, exp(1000) = 1, ln(10^200) = 460, tan(90°) = 1, arccos(2) = 0", "mathematics_aa"),
    ("roots-storm", "x² = 2 ⇒ " + " or ".join(f"x = {k}.{k}" for k in range(1, 40)), "mathematics_aa"),
    ("chem-storm", " + ".join(["H₂"] * 40) + " → " + " + ".join(["H₂"] * 40), "chemistry"),
    ("bool-storm", " ∧ ".join(["A"] * 200) + " = A", "computer_science"),
    ("percent-storm", " = ".join(["50%"] * 50), "physics"),
    ("units-storm", "x = " + " ".join(["m"] * 200) + " = 1 m", "physics"),
]


@pytest.mark.parametrize("name,text,profile", ADVERSARIAL, ids=[a[0] for a in ADVERSARIAL])
def test_adversarial_input_is_handled_within_bounds(name, text, profile):
    t0 = time.perf_counter()
    plan = plan_of(text, profile=profile)
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0, (name, elapsed)
    for pc in plan.checks:
        prob = Problem.model_validate(pc.problem)
        assert len(prob.symbols) <= 48 and len(prob.premises) <= 128
        exprs = [p.expr for p in prob.premises] + ([prob.conclusion.expr] if prob.conclusion else [])
        for e in exprs:
            for node in _walk(e.model_dump()):
                if node.get("op") in ("real", "int"):
                    assert digit_count(node["value"]) <= 40
    for f in plan.findings:
        assert f.severity != "error"
