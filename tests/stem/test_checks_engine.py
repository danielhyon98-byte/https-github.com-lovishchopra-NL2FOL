"""Every check kind of docs/STEM_DESIGN.md section 8.1, correct and wrong, through ``verify``: the
expected status, the failure severity, the claim ids and the description bounds. Then the labelled
corpus: every check of a correct answer holds, and every fault this stage decides is caught on the
claim that holds it, with the expected severity."""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Optional

import pytest

from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import CHECK_KIND_NAMES, PlannedCheck, build_checks

CFG = SolverConfig(timeout_ms=10000, memory_max_mb=None)
CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "stem" / "corpus"
_DEFINITIVE = {"ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE"}


def satisfied(pc: PlannedCheck, res) -> Optional[bool]:
    """The hub's mapping (section 11.2): True iff the expected status without E108; False iff a definitive
    other status (INCONSISTENT_PREMISES only when the check says so); None otherwise."""
    status = res.status.value
    if status == pc.expected_if_sound and not any(d.code == "E108" for d in res.diagnostics):
        return True
    if status in _DEFINITIVE and status != pc.expected_if_sound:
        if status == "INCONSISTENT_PREMISES" and not pc.inconsistent_is_failure:
            return None
        return False
    return None


def run(text: str, request: Optional[str] = None, profile: str = "physics"):
    doc = build_document(text, request, profile)
    plan = build_checks(doc, report_id="r1", request_id="q1")
    out = {}
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
        out[pc.check_id] = (pc, res, satisfied(pc, res))
    return doc, plan, out


def check(text: str, check_id: str, *, request: Optional[str] = None, profile: str = "physics"):
    doc, plan, out = run(text, request, profile)
    assert check_id in out, (check_id, sorted(out), plan.findings)
    pc, res, sat = out[check_id]
    # invariants of every planned check
    assert pc.kind == CHECK_KIND_NAMES[pc.relation_kind]
    assert pc.inconsistent_is_failure is False
    assert pc.policy in ("linear", "nonlinear")
    assert pc.failure_severity in ("error", "warning")
    assert len(pc.description) <= 1200 and pc.claim_ids
    assert set(pc.claim_ids) <= {st.id for st in doc.statements}
    assert all(f"[claims {', '.join(pc.claim_ids)}]" in pc.description for _ in (0,))
    return pc, res, sat


# --------------------------------------------------------------------------- one case per kind, correct and wrong

CASES = [
    # kind, check id, correct text, wrong text, profile, request, expected status, failure severity
    ("eq", "stem-eq-1", "a = (20 - 0)/4.0 = 5.0 m s⁻²", "a = (20 - 0)/4.0 = 6.0 m s⁻²", "physics", None, "ENTAILED", "error"),
    ("sub", "stem-sub-1", "Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J.",
     "Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 4.0² = 16 J.", "physics", None, "ENTAILED", "error"),
    ("sub", "stem-sub-1", "u = 5.0 m s⁻¹, a = 2.0 m s⁻² and t = 3.0 s.\ns = ut + ½at² = 15 m + 9.0 m = 24 m",
     "u = 5.0 m s⁻¹, a = 2.0 m s⁻² and t = 3.0 s.\ns = ut + ½at² = 5.0 m + 9.0 m = 14 m", "physics", None, None, "error"),
    ("alg", "stem-alg-1", "v² = u² + 2as ⇒ s = (v² − u²)/(2a)", "v² = u² + 2as ⇒ s = (v² − u²)/a", "physics", None, "ENTAILED", "error"),
    ("sol", "stem-sol-1", "x² − 5x + 6 = 0 ⇒ x = 2 or x = 3", "x² − 5x + 6 = 0 ⇒ x = 2 or x = −3", "mathematics_aa", None, "ENTAILED", "error"),
    ("sol", "stem-sol-1", "x² = 2 ⇒ x = 1.41 or x = −1.41", "x² = 2 ⇒ x = 1.47 or x = −1.41", "mathematics_aa", None, "ENTAILED", "error"),
    ("sol", "stem-sol-1", "x² − 3x + 1 = 0 gives x = 2.62.", "x² − 3x + 1 = 0 gives x = 2.72.", "mathematics_aa", None, "SATISFIABLE", "error"),
    ("cnv", "stem-cnv-1", "d = 2.5 km = 2500 m", "d = 2.5 km = 250 m", "physics", None, "ENTAILED", "error"),
    ("cmp", "stem-cmp-1", "The amount of Al is 0.25 mol < 0.30 mol.", "The amount of Al is 0.35 mol < 0.30 mol.", "chemistry", None, "ENTAILED", "error"),
    ("cmp", "stem-cmp-2", "3 − 2x > 7\n−2x > 4\nx < −2", "3 − 2x > 7\n−2x > 4\nx > −2", "mathematics_aa", None, "ENTAILED", "error"),
    ("res", "stem-res-1", "I = V/R = 12/2.4 = 5.0 A. The current is therefore 5.0 A.", "I = V/R = 12/2.4 = 5.0 A. The current is therefore 0.50 A.",
     "physics", None, "ENTAILED", "error"),
    ("giv", "stem-giv-1", "Given: m = 2.0 kg.\nW = mg = 2.0 × 9.81 = 19.6 N.", "Given: m = 2.5 kg.\nW = mg = 2.5 × 9.81 = 24.5 N.", "physics",
     "A 2.0 kg mass hangs at rest. Take g = 9.81 m s⁻².", "ENTAILED", "warning"),
    ("tgt", "stem-tgt-1", "KE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J.", "KE = ½mv² = ½ × 2.0 × 3.5² = 12 J.", "physics",
     "A 2.0 kg ball moves at 3.0 m s⁻¹. Show that its kinetic energy is about 9 J.", "ENTAILED", "warning"),
    ("chem", "stem-chem-1", "2H₂ + O₂ → 2H₂O", "H₂ + O₂ → H₂O", "chemistry", None, "ENTAILED", "error"),
    ("chem", "stem-chem-1", "H₂ + ½O₂ → H₂O", "H₂ + ½O₂ → 2H₂O", "chemistry", None, "ENTAILED", "error"),
    ("chem", "stem-chem-1", "Cu²⁺ + 2e⁻ → Cu", "Cu²⁺ + e⁻ → Cu", "chemistry", None, "ENTAILED", "error"),
    ("bool", "stem-bool-1", "¬(A ∧ B) = ¬A ∨ ¬B", "¬(A ∧ B) = ¬A ∧ ¬B", "computer_science", None, "UNSATISFIABLE", "error"),
    ("tt", "stem-tt-1", "| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |",
     "| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 1 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |", "computer_science", None, "ENTAILED", "error"),
    ("base", "stem-base-1", "FF₁₆ = 255", "FF₁₆ = 256", "computer_science", None, "ENTAILED", "error"),
]


@pytest.mark.parametrize("kind,cid,good,bad,profile,req,expected,severity", CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_every_kind_correct_and_wrong(kind, cid, good, bad, profile, req, expected, severity):
    pc, res, sat = check(good, cid, request=req, profile=profile)
    assert pc.relation_kind == kind
    if expected is not None:
        assert pc.expected_if_sound == expected
    assert sat is True, (res.status, pc.description)
    assert pc.failure_severity == severity
    pc2, res2, sat2 = check(bad, cid, request=req, profile=profile)
    assert sat2 is False, (res2.status, pc2.description)
    assert pc2.failure_severity == severity
    assert res2.status.value in ("COUNTEREXAMPLE", "UNSATISFIABLE", "SATISFIABLE")


def test_a_counterexample_shows_the_computed_value_beside_the_stated_one():
    _pc, res, sat = check("a = (20 - 0)/4.0 = 6.0 m s⁻²", "stem-eq-1")
    assert sat is False
    model = {a.symbol: a.value for a in res.counterexample.assignments}
    assert (model["c"], model["r"]) == ("5", "6")


def test_an_unbalanced_equation_shows_the_tallies():
    _pc, res, sat = check("C₃H₈ + 4O₂ → 3CO₂ + 4H₂O", "stem-chem-1", profile="chemistry")
    assert sat is False
    model = {a.symbol: a.value for a in res.counterexample.assignments}
    assert model["t_o_l"] == "8" and model["t_o_r"] == "10"


def test_a_failed_boolean_identity_gives_a_distinguishing_assignment():
    _pc, res, sat = check("A ⊕ B = A ∨ B", "stem-bool-1", profile="computer_science")
    assert sat is False and res.witness_model
    w = {a.symbol: a.value for a in res.witness_model}
    assert w["s_cap_a"] == "true" and w["s_cap_b"] == "true"


def test_a_completeness_failure_names_the_lost_root():
    _pc, res, sat = check("x² − 2x − 8 = 0, so the only solution is x = 4.", "stem-sol-1", profile="mathematics_aa")
    assert sat is False
    model = {a.symbol: a.value for a in res.counterexample.assignments}
    assert model["s_x"] == "-2"


def test_an_algebra_step_with_an_unconnected_symbol_fails_only_as_a_warning():
    pc, _res, sat = check("x + y = 5 ⇒ x = 5 − y − z", "stem-alg-1", profile="mathematics_aa")
    assert pc.failure_severity == "warning" and sat is False
    pc, _res, sat = check("x + y = 5 ⇒ x = 5 − y", "stem-alg-1", profile="mathematics_aa")
    assert pc.failure_severity == "error" and sat is True


def test_a_step_with_a_rounded_value_is_compared_within_its_band():
    assert check("x ln 2 = ln 50\nx = 5.64", "stem-alg-1", profile="mathematics_aa")[2] is True
    assert check("x ln 2 = ln 50\nx = 6.64", "stem-alg-1", profile="mathematics_aa")[2] is False


def test_physics_principal_root_side_condition():
    pc, _res, sat = check("s = ½gt² so t² = 2s/g, giving t = √(2s/g).", "stem-alg-2")
    assert sat is True and "principal root" in pc.description
    assert any(p["id"] == "SIDE_ROOT" and p["grounding"]["kind"] == "assumption" for p in pc.problem["premises"])


def test_descriptions_stay_bounded_for_long_statements():
    long_sum = " + ".join(["1.5"] * 40)
    pc, _res, sat = check(f"P = {long_sum} = 60.0 W", "stem-eq-1")
    assert sat is True and len(pc.description) <= 1200


# --------------------------------------------------------------------------- the labelled corpus

_PROFILE = {"Physics": "physics", "Chemistry": "chemistry", "Biology": "biology", "Environmental Systems and Societies": "ess"}
#: faults the branch stage decides (prose relations read by CorePack in SI reading), not this stage
_BRANCH_STAGE = {"stem-phys-009", "stem-phys-026"}


def _corpus():
    for fn in sorted(glob.glob(str(CORPUS / "*.json"))):
        yield json.loads(Path(fn).read_text(encoding="utf-8"))


def _profile(d) -> str:
    subj = d["subject"]
    return _PROFILE.get(subj) or ("mathematics_ai" if "Applications" in subj else "mathematics_aa")


def _covering(doc, step: str) -> set[str]:
    a = doc.text.index(step)
    b = a + len(step)
    return {st.id for st in doc.statements if st.start < b and st.end > a}


def test_the_corpus():
    correct_checks = failed_correct = 0
    caught: dict[str, str] = {}
    for d in _corpus():
        doc, plan, out = run(d["response_text"], d["question"], _profile(d))
        faults = d["gold"]["faults"]
        if not faults:
            for cid, (pc, res, sat) in out.items():
                correct_checks += 1
                if sat is False:
                    failed_correct += 1
                assert sat is not False, (d["id"], cid, res.status, pc.description)
            continue
        if d["id"] in _BRANCH_STAGE:
            continue
        fault = faults[0]
        covering = _covering(doc, fault["step"])
        codes = fault["expected_codes"]
        hit = None
        for cid, (pc, res, sat) in out.items():
            if sat is False and set(pc.claim_ids) & covering:
                if ("INT-SUBJ-001" in codes and pc.failure_severity == "error") or ("INT-SUBJ-004" in codes and pc.failure_severity == "warning"):
                    hit = cid
                    break
        if hit is None:
            st_codes = {f.code for f in doc.findings if set(f.statement_ids) & covering} | {f.code for f in plan.findings if set(f.statement_ids) & covering}
            if st_codes & set(codes):
                hit = sorted(st_codes & set(codes))[0]
        assert hit is not None, (d["id"], fault, {cid: (pc.claim_ids, res.status.value) for cid, (pc, res, _s) in out.items()})
        caught[d["id"]] = hit
    assert correct_checks > 200 and failed_correct == 0
    assert len(caught) >= 34
