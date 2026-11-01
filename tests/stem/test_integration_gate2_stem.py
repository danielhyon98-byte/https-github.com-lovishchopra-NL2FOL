"""Integration gate 2 (before arena round 8): the STEM findings of the independent lenses, each reproduced through the hub and fixed
at its cause, with clean controls (correct working that must hold and wrong working that must still fail).

* an inline chain of symbolic identities is decided link by link, each an identity in its variables (rule identity-chain);
* a root set of the request's equation written 'x = a or x = b', 'x = a, x = b', 'x = a and x = b' checks every root (rule root-set);
* a result restated after ', so the <quantity> is', after 'So/Therefore/Answer:' for the chain's own symbol, after 'Final answer:', or in a
  sentence naming the chain's quantity is set against the chain (rules inline-restatement, restated-result, named-restatement);
* a symbol the request binds no longer abandons the request substitution of the others (rule request-substitution);
* an inequality step of an answer to a request to solve is decided both ways (rule solution-set);
* the roots of an equation reached by squaring are checked against the equation before the squaring (rule radical-roots);
* an equation joined by 'and' after a step cue is the next step (rule and-step);
* a bare volume in chemistry is read in dm³, and 'c' is the concentration where the request states one (rule request-substitution);
* a bare side of a data conversion is read in every unit of data its statement writes, and data counts are exact (rule data-count);
* a magnification written '×N' or 'xN' after a relation sign is the value N (rule magnification-prefix);
* truth tables written without Markdown borders are read, and a letter output column takes the request's expression (rules
  plain-table, request-output);
* rational identities and index laws under a simplify, expand, prove or show request are identities (rule rational-identity);
* a length's square root is its principal root by its meaning (rule length-root).
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"integration-gate-2-stem-key-0123456789"
SUBJECTS = {"physics": "Physics", "chemistry": "Chemistry", "biology": "Biology", "ess": "Environmental Systems and Societies",
            "mathematics_aa": "Mathematics: Analysis and Approaches", "mathematics_ai": "Mathematics: Applications and Interpretation",
            "computer_science": "Computer Science"}
AA, AI, CS = "mathematics_aa", "mathematics_ai", "computer_science"


def receive(profile: str, answer: str, request: str = "Answer the question."):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def failed(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is False}


def held(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is True}


def codes(rc) -> list[tuple[str, str]]:
    return [(f.code, f.severity) for f in rc.findings]


def no_stem_fault(rc) -> bool:
    """No failed check, no INT-SUBJ finding and no warning ST code beyond the undecided and parse ones."""
    return (not failed(rc) and not any(f.code.startswith("INT-SUBJ") for f in rc.findings)
            and not [f for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")
                     and not f.code.startswith(("ST-UNDEC", "ST-PARSE"))])


def fails_with(rc, prefix: str, code: str = "INT-SUBJ-001") -> bool:
    return any(c.startswith(prefix) for c in failed(rc)) and code in [c for c, _s in codes(rc)]


# ============================================================================================ blocker 1: rule identity-chain
@pytest.mark.parametrize("request_, answer", [
    ("Expand and simplify (2x − 1)² − 4x².", "(2x − 1)² − 4x² = 4x² − 2x + 1 − 4x² = 1 − 2x"),
    ("Expand (x + 2)(x + 3).", "(x + 2)(x + 3) = x² + 6 = x² + 5x + 6"),
    ("Factorise x² + 7x + 12.", "x² + 7x + 12 = x² + 2x + 4x + 12 = (x + 3)(x + 4)"),
    ("Show that (x + 3)² − 9 = x(x + 6).", "(x + 3)² − 9 = x² + 3x + 9 − 9 = x² + 6x = x(x + 6)"),
])
def test_a_false_first_link_of_an_inline_identity_chain_fails(request_, answer):
    rc = receive(AA, answer, request_)
    assert "stem-alg-1" in failed(rc) and fails_with(rc, "stem-alg"), (answer, failed(rc))


def test_a_false_link_with_no_solution_is_a_failure_not_undecided():
    rc = receive(AI, "2(3a + 4) − 3(a − 2) = 6a + 8 − 3a − 6 = 3a + 2", "Simplify 2(3a + 4) − 3(a − 2).")
    assert "stem-alg-1" in failed(rc) and not [c for c in rc.formal_checks if c.satisfied is None]


@pytest.mark.parametrize("request_, answer", [
    ("Expand and simplify (2x − 1)² − 4x².", "(2x − 1)² − 4x² = 4x² − 4x + 1 − 4x² = 1 − 4x"),
    ("Expand (x + 2)(x + 3).", "(x + 2)(x + 3) = x² + 3x + 2x + 6 = x² + 5x + 6"),
    ("Factorise x² + 7x + 12.", "x² + 7x + 12 = x² + 3x + 4x + 12 = (x + 3)(x + 4)"),
    ("Show that (x + 3)² − 9 = x(x + 6).", "(x + 3)² − 9 = x² + 6x + 9 − 9 = x² + 6x = x(x + 6)"),
    ("Simplify 2(3a + 4) − 3(a − 2).", "2(3a + 4) − 3(a − 2) = 6a + 8 − 3a + 6 = 3a + 14"),
    ("Expand (x + 2)(x + 3).", "(x + 2)(x + 3)\n= x² + 3x + 2x + 6\n= x² + 5x + 6"),
])
def test_clean_control_correct_identity_chains_hold(request_, answer):
    rc = receive(AA, answer, request_)
    assert no_stem_fault(rc) and held(rc), (answer, failed(rc), codes(rc))


def test_control_the_line_per_link_form_still_fails():
    rc = receive(AA, "(x + 2)(x + 3)\n= x² + 6\n= x² + 5x + 6", "Expand (x + 2)(x + 3).")
    assert fails_with(rc, "stem-alg")


def test_each_link_of_an_identity_chain_is_decided_alone():
    d = build_document("(x + 2)(x + 3) = x² + 6 = x² + 5x + 6", "Expand (x + 2)(x + 3).", AA)
    algs = [r for r in d.relations if r.kind == "alg"]
    assert len(algs) == 2 and all(r.identity == ("x",) and "(rule identity-chain)" in r.reason for r in algs)
    assert all(r.premise_left is r.premise_right or r.premise_left == r.premise_right for r in algs)  # the trivially true premise


# ============================================================================================ blocker 2: rule root-set
@pytest.mark.parametrize("profile, request_, answer", [
    (AA, "Solve x² − 5x + 6 = 0.", "x = 2 or x = 4"), (AA, "Solve x² − 5x + 6 = 0.", "x = 2, x = 4"),
    (AA, "Solve x² − 5x + 6 = 0.", "x = 2 and x = 4"), (AA, "Solve x² − 5x + 6 = 0.", "So x = 2 or x = 4"),
    (AI, "Solve x² − 9 = 0.", "x = 3 or x = 4"),
    (AA, "Solve x² − 5x + 6 = 0.", "x = 4 or x = 2"), (AA, "Solve x² − 5x + 6 = 0.", "x = 2 or 4"),
    (AA, "Solve x² − 5x + 6 = 0.", "The solutions are x = 2 or x = 4."), (AA, "Solve x² − 5x + 6 = 0.", "x² − 5x + 6 = 0 ⇒ x = 2 or x = 4"),
])
def test_a_wrong_second_root_of_the_requests_equation_fails(profile, request_, answer):
    assert fails_with(receive(profile, answer, request_), "stem-sol"), answer


@pytest.mark.parametrize("profile, request_, answer", [
    (AA, "Solve x² − 5x + 6 = 0.", "x = 2 or x = 3"), (AA, "Solve x² − 5x + 6 = 0.", "x = 2, x = 3"),
    (AA, "Solve x² − 5x + 6 = 0.", "x = 2 and x = 3"), (AA, "Solve x² − 5x + 6 = 0.", "So x = 2 or x = 3"),
    (AI, "Solve x² − 9 = 0.", "x = 3 or x = −3"), (AA, "Solve x² − 5x + 6 = 0.", "x = 3 or x = 2"),
])
def test_clean_control_a_correct_root_set_holds_and_is_no_rebinding(profile, request_, answer):
    rc = receive(profile, answer, request_)
    assert no_stem_fault(rc) and held(rc), answer
    d = build_document(answer, request_, profile)
    sols = [r for r in d.relations if r.kind == "sol"]
    assert len(sols) == 1 and len(sols[0].roots) == 2
    assert not [f for f in d.findings if f.code == "ST-SCOPE-001"]


# ============================================================================================ major 3: restatements
TROLLEY = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."


@pytest.mark.parametrize("profile, request_, answer, severity", [
    ("physics", TROLLEY, "a = (20 − 0)/4.0 = 5.0 m s⁻², so the acceleration is 6.0 m s⁻².", "error"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻².\nSo a = 6.0 m s⁻².", "error"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻². Therefore a = 6.0 m s⁻².", "error"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nAnswer: a = 6.0 m s⁻²", "error"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nFinal answer: 6.0 m s⁻²", "error"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nThe acceleration is 6.0 m s⁻².", "warning"),
    ("chemistry", "Calculate the amount of NaOH in 4.0 g.", "n = 4.0/40 = 0.10 mol\nThe amount of NaOH is 1.0 mol.", "warning"),
    ("chemistry", "Calculate the amount of NaOH in 4.0 g.", "n = 4.0/40 = 0.10 mol\nSo n = 1.0 mol.", "error"),
    ("biology", "An image is 5.0 cm long and the cell is 25 μm long. Calculate the magnification.",
     "M = 5.0 cm / 25 μm = 2000\nThe magnification is ×200.", "warning"),
    ("biology", "The image of a cell is 12 mm long at a magnification of 400. Calculate the actual size.",
     "A = 12 mm / 400 = 30 μm.\nSo A = 0.030 μm.", "error"),
    ("ess", "Calculate the efficiency of energy transfer from 1500 kJ to 150 kJ.", "efficiency = 150/1500 × 100 = 10%\nThe efficiency is 1%.", "warning"),
    (AI, "Calculate the mean of 2, 4 and 6.", "mean = (2 + 4 + 6)/3 = 4\nThe mean is 5.", "warning"),
])
def test_a_wrong_restated_result_fails(profile, request_, answer, severity):
    rc = receive(profile, answer, request_)
    code = "INT-SUBJ-001" if severity == "error" else "INT-SUBJ-004"
    assert fails_with(rc, "stem-res", code), (answer, failed(rc), codes(rc))


@pytest.mark.parametrize("profile, request_, answer", [
    ("physics", TROLLEY, "a = (20 − 0)/4.0 = 5.0 m s⁻², so the acceleration is 5.0 m s⁻²."),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻².\nSo a = 5.0 m s⁻²."),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nAnswer: a = 5.0 m s⁻²"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nFinal answer: 5.0 m s⁻²"),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nThe acceleration is 5.0 m s⁻²."),
    ("physics", TROLLEY, "a = (20 - 0)/4.0 = 5.0 m s⁻²\nSo a = 5 m s⁻²."),
    ("chemistry", "Calculate the amount of NaOH in 4.0 g.", "n = 4.0/40 = 0.10 mol\nThe amount of NaOH is 0.10 mol."),
    ("biology", "An image is 5.0 cm long and the cell is 25 μm long. Calculate the magnification.", "M = 5.0 cm / 25 μm = 2000\nThe magnification is ×2000."),
    ("biology", "The image of a cell is 12 mm long at a magnification of 400. Calculate the actual size.", "A = 12 mm / 400 = 30 μm.\nSo A = 0.030 mm."),
    ("ess", "Calculate the efficiency of energy transfer from 1500 kJ to 150 kJ.", "efficiency = 150/1500 × 100 = 10%\nThe efficiency is 10%."),
    (AI, "Calculate the mean of 2, 4 and 6.", "mean = (2 + 4 + 6)/3 = 4\nThe mean is 4."),
    # stem-precision-1: a value whose words name another quantity is no restatement, nor one of another dimension
    ("ess", "Calculate the efficiency of energy transfer from 1500 kJ to 150 kJ.", "efficiency = 150/1500 × 100 = 10%, so the energy wasted is 90%."),
    ("physics", "A 2.0 kg trolley accelerates at 3.0 m s⁻². Calculate the resultant force.", "F = ma = 2.0 × 3.0 = 6.0 N\nThe weight is 20 N."),
    ("physics", "A van slows from 16 m s⁻¹ to rest in 4.0 s. Calculate its deceleration.",
     "a = (v − u)/t = (0 − 16)/4.0 = −4.0 m s⁻², so the deceleration is 4.0 m s⁻²."),
    # a second root stated after a root the working computed restates nothing; a quantity only the request names is no restatement
    (AA, "Solve x² − 5x + 6 = 0.", "x² − 5x + 6 = 0\nx = (5 + 1)/2 = 3\nx = 2"),
    (AA, "Solve x² − 5x + 6 = 0.", "x = (5 + √1)/2 = 3\nx = 2"),
    ("physics", "A 2.0 kg trolley accelerates at 3.0 m s⁻². Calculate the force and the tension.", "F = ma = 2.0 × 3.0 = 6.0 N\nThe tension is 4.0 N."),
])
def test_clean_control_a_correct_or_unrelated_restatement_is_no_fault(profile, request_, answer):
    rc = receive(profile, answer, request_)
    assert no_stem_fault(rc), (answer, failed(rc), codes(rc))


# ============================================================================================ major 4: a symbol the request binds
@pytest.mark.parametrize("request_, answer", [
    ("Calculate the energy to heat 2.0 kg of water by 10 K (c = 4200 J kg⁻¹ K⁻¹).", "Q = mcΔT = 2.0 × 4200 × 100 = 840000 J"),
    ("A 2.0 kg mass is raised 5.0 m (g = 9.8 m s⁻²). Calculate the gain in potential energy.", "ΔEp = mgΔh = 2.0 × 9.8 × 50 = 980 J"),
    ("Calculate the energy to heat 2.0 kg of water by 10 K (c = 4200 J kg⁻¹ K⁻¹).", "m = 2.0 kg\nQ = mcΔT = 2.0 × 4200 × 100 = 840000 J"),
])
def test_a_miscopied_value_is_named_when_the_request_binds_another_symbol(request_, answer):
    assert fails_with(receive("physics", answer, request_), "stem-giv", "INT-SUBJ-004"), answer


@pytest.mark.parametrize("request_, answer", [
    ("Calculate the energy to heat 2.0 kg of water by 10 K (c = 4200 J kg⁻¹ K⁻¹).", "Q = mcΔT = 2.0 × 4200 × 10 = 84000 J"),
    ("A 2.0 kg mass is raised 5.0 m (g = 9.8 m s⁻²). Calculate the gain in potential energy.", "ΔEp = mgΔh = 2.0 × 9.8 × 5.0 = 98 J"),
    ("Calculate the energy to heat 2.0 kg of water by 10 K (c = 4200 J kg⁻¹ K⁻¹).", "m = 2.0 kg\nQ = mcΔT = 2.0 × 4200 × 10 = 84000 J"),
])
def test_clean_control_the_requests_values_substituted(request_, answer):
    assert no_stem_fault(receive("physics", answer, request_)), answer


# ============================================================================================ major 5: rule solution-set
@pytest.mark.parametrize("profile, request_, answer", [
    (AA, "Solve 2x − 4 > 6.", "2x − 4 > 6 ⇒ 2x > 10 ⇒ x > 4"), (AA, "Solve 3x + 1 ≥ 7.", "3x + 1 ≥ 7 ⇒ 3x ≥ 6 ⇒ x ≥ 1"),
    (AI, "Solve 5 − x < 2.", "5 − x < 2 ⇒ x > 2"), (AA, "Solve 3x + 1 ≥ 7.", "3x ≥ 6\nx > 2"), (AA, "Solve −2x > 6.", "−2x > 6 ⇒ x > −3"),
    (AA, "Solve 7x > 5.", "7x > 5 ⇒ x > 0.72"), (AA, "Solve 2x > 5.", "2x > 5 ⇒ x > 2.4"),
])
def test_an_inequality_step_that_weakens_the_solution_set_fails(profile, request_, answer):
    assert fails_with(receive(profile, answer, request_), "stem-cmp"), answer


@pytest.mark.parametrize("profile, request_, answer", [
    (AA, "Solve 2x − 4 > 6.", "2x − 4 > 6 ⇒ 2x > 10 ⇒ x > 5"), (AA, "Solve 3x + 1 ≥ 7.", "3x + 1 ≥ 7 ⇒ 3x ≥ 6 ⇒ x ≥ 2"),
    (AI, "Solve 5 − x < 2.", "5 − x < 2 ⇒ x > 3"), (AA, "Solve −2x > 6.", "−2x > 6 ⇒ x < −3"), (AA, "Solve 7x > 5.", "7x > 5 ⇒ x > 0.71"),
    (AA, "Solve 4 − 2x ≥ 10.", "4 − 2x ≥ 10 ⇒ −2x ≥ 6 ⇒ x ≤ −3"),
    # a chain that only bounds a quantity keeps the implication
    (AA, "Show that if x > 5 then 3x + 1 > 6.", "x > 5 ⇒ 3x > 15 ⇒ 3x + 1 > 16 > 6"),
])
def test_clean_control_an_equivalent_or_bounding_step_holds(profile, request_, answer):
    rc = receive(profile, answer, request_)
    assert not failed(rc) and not any(f.code.startswith("INT-SUBJ") for f in rc.findings), answer


# ============================================================================================ major 6: rule radical-roots
@pytest.mark.parametrize("answer", [
    "√(x + 2) = x ⇒ x + 2 = x² ⇒ x = 2 or x = −1",
    "√(x + 2) = x\nx + 2 = x²\nx² − x − 2 = 0\n(x − 2)(x + 1) = 0\nx = 2 or x = −1",
    "x + 2 = x² ⇒ x = 2 or x = −1",
])
def test_an_extraneous_root_from_squaring_fails(answer):
    assert fails_with(receive(AA, answer, "Solve √(x + 2) = x."), "stem-sol"), answer


@pytest.mark.parametrize("answer", [
    "√(x + 2) = x ⇒ x + 2 = x² ⇒ x = 2 (x = −1 is rejected since √(x + 2) ≥ 0)",
    "√(x + 2) = x ⇒ x + 2 = x² ⇒ x = 2 or x = −1; reject x = −1 since √(x + 2) ≥ 0, so x = 2.",
    "√(x + 2) = x ⇒ x + 2 = x² ⇒ (x − 2)(x + 1) = 0 ⇒ x = 2",
    "x + 2 = x² ⇒ x = 2 or x = −1, but x = −1 is extraneous, so x = 2.",
])
def test_clean_control_a_rejected_extraneous_root_is_no_fault(answer):
    assert no_stem_fault(receive(AA, answer, "Solve √(x + 2) = x.")), answer


# ============================================================================================ major 7: rule and-step
@pytest.mark.parametrize("profile, request_, answer", [
    (AI, "Solve 3x − 7 = 8.", "3x − 7 = 8, so 3x = 15 and x = 3"), (AA, "Solve 2x + 3 = 11.", "2x + 3 = 11, so 2x = 8 and x = 5"),
    (AA, "Solve 2x = 8.", "2x = 8, so x = 4 and x = 5"),
])
def test_a_wrong_last_step_joined_by_and_fails(profile, request_, answer):
    assert fails_with(receive(profile, answer, request_), "stem-alg"), answer


@pytest.mark.parametrize("profile, request_, answer", [
    (AI, "Solve 3x − 7 = 8.", "3x − 7 = 8, so 3x = 15 and x = 5"), (AA, "Solve 2x + 3 = 11.", "2x + 3 = 11, so 2x = 8 and x = 4"),
])
def test_clean_control_a_right_last_step_joined_by_and_holds(profile, request_, answer):
    rc = receive(profile, answer, request_)
    assert no_stem_fault(rc) and {"stem-alg-1", "stem-alg-2"} <= held(rc), answer


# ============================================================================================ major 8: volumes in dm³ in chemistry
@pytest.mark.parametrize("request_, answer", [
    ("0.020 mol is dissolved to make 500 cm³ of solution. Calculate the concentration.", "c = n/V = 0.020/0.500 = 0.040 mol dm⁻³"),
    ("0.0100 mol of HCl is in 50.0 cm³ of solution. Calculate the concentration.", "c = n/V = 0.0100/0.0500 = 0.200 mol dm⁻³"),
    ("0.10 mol of solute is in 25 cm³ of solution. Calculate the concentration.", "c = n/V = 0.10/0.025 = 4.0 mol dm⁻³"),
    ("25.0 cm³ of 0.100 mol dm⁻³ NaOH is used. Calculate the amount of NaOH.", "n = cV = 0.100 × 0.0250 = 2.50 × 10⁻³ mol"),
    # a bare mass in chemistry is read in g, the unit of the molar mass it is divided by (the request binding M no longer abandons m)
    ("A 250 mg tablet of aspirin (M = 180 g mol⁻¹) is used. Calculate the amount.", "n = m/M = 0.250/180 = 1.39 × 10⁻³ mol"),
    ("A 2.5 kg sample of NaCl (M = 58.5 g mol⁻¹) is dissolved. Calculate the amount.", "n = m/M = 2500/58.5 = 42.7 mol"),
])
def test_a_correct_volume_in_dm3_is_no_miscopy(request_, answer):
    assert no_stem_fault(receive("chemistry", answer, request_)), answer


@pytest.mark.parametrize("request_, answer", [
    ("50.0 cm³ of 0.200 mol dm⁻³ HCl is used. Calculate the amount of HCl.", "n = cV = 0.200 × 0.500 = 0.100 mol"),
    ("50.0 cm³ of 0.200 mol dm⁻³ HCl is used. Calculate the amount of HCl.", "n = cV = 0.200 × 0.00500 = 0.00100 mol"),
    ("25.0 cm³ of 0.100 mol dm⁻³ NaOH is used. Calculate the amount of NaOH.", "n = cV = 0.100 × 0.250 = 2.50 × 10⁻² mol"),
    ("0.020 mol is dissolved to make 500 cm³ of solution. Calculate the concentration.", "c = n/V = 0.020/5.00 = 0.0040 mol dm⁻³"),
    ("A 250 mg tablet of aspirin (M = 180 g mol⁻¹) is used. Calculate the amount.", "n = m/M = 2.50/180 = 1.39 × 10⁻² mol"),
    ("A 2.5 kg sample of NaCl (M = 58.5 g mol⁻¹) is dissolved. Calculate the amount.", "n = m/M = 250/58.5 = 4.27 mol"),
])
def test_a_volume_a_power_of_ten_off_is_named(request_, answer):
    assert fails_with(receive("chemistry", answer, request_), "stem-giv", "INT-SUBJ-004"), answer


# ============================================================================================ major 9: data conversions
@pytest.mark.parametrize("request_, answer", [
    ("Calculate the file size in KiB of 8192 bytes.", "8192 bytes = 8192/1024 = 8 KiB"), ("Convert 3 MiB to KiB.", "3 MiB = 3 × 1024 = 3072 KiB"),
    ("Convert 4 KB to bytes.", "4 KB = 4 × 1000 = 4000 bytes"), ("Calculate the file size in KiB of 8192 bytes.", "size = 8192/1024 = 8 KiB"),
    ("Convert 2048 bits to bytes.", "2048 bits = 2048/8 = 256 bytes"), ("Convert 2 KiB to bytes.", "2 KiB = 2 × 1024 = 2048 bytes"),
    ("Convert 5 GB to MB.", "5 GB = 5 × 1000 = 5000 MB"),
])
def test_a_correct_data_conversion_holds(request_, answer):
    rc = receive(CS, answer, request_)
    assert not failed(rc) and not any(f.code.startswith("INT-SUBJ") for f in rc.findings), answer


@pytest.mark.parametrize("request_, answer", [
    ("Convert 3 MiB to KiB.", "3 MiB = 3 × 1024 = 3000 KiB"), ("Calculate the file size in KiB of 8192 bytes.", "8192 bytes = 8192/1024 = 9 KiB"),
    ("Convert 4 KB to bytes.", "4 KB = 4 × 1000 = 5000 bytes"), ("Convert 2 KiB to bytes.", "2 KiB = 2 × 1024 = 2000 bytes"),
])
def test_a_wrong_data_conversion_fails(request_, answer):
    assert fails_with(receive(CS, answer, request_), "stem-eq"), answer


# ============================================================================================ major 10: magnification prefix
MAG = "An image of a cell is 6.0 mm long and the actual cell is 20 μm long. Calculate the magnification."


@pytest.mark.parametrize("answer", ["M = I/A = 6.0 mm / 20 μm = ×3000", "M = 6.0 mm / 20 μm = × 3000", "M = 6000/20 = ×3000",
                                    "M = 6.0 mm / 20 μm = x3000", "The magnification is 6000 μm / 20 μm = ×3000."])
def test_a_wrong_magnification_written_with_its_sign_fails(answer):
    assert fails_with(receive("biology", answer, MAG), "stem-eq"), answer


@pytest.mark.parametrize("answer", ["M = I/A = 6.0 mm / 20 μm = ×300", "M = 6000/20 = ×300", "M = 6.0 mm / 20 μm = x300",
                                    "The magnification is 6000 μm / 20 μm = ×300."])
def test_clean_control_a_right_magnification_written_with_its_sign_holds(answer):
    rc = receive("biology", answer, MAG)
    assert no_stem_fault(rc) and held(rc), answer


def test_a_letter_x_before_a_number_in_mathematics_stays_a_symbol():
    d = build_document("y = x3", None, AA)
    assert not [r for r in d.relations if r.kind == "eq"]


# ============================================================================================ major 11: plain truth tables
@pytest.mark.parametrize("request_, answer, code", [
    ("Complete the truth table for A NAND B.", "A B | A NAND B\n0 0 | 1\n0 1 | 0\n1 0 | 1\n1 1 | 0", "INT-SUBJ-001"),
    ("Complete the truth table for A AND B.", "A | B | A AND B\n--|---|--------\n0 | 0 | 0\n0 | 1 | 1\n1 | 0 | 0\n1 | 1 | 1", "INT-SUBJ-001"),
    ("Complete the truth table for A AND B.", "A B Q\n0 0 0\n0 1 1\n1 0 0\n1 1 1", "INT-SUBJ-004"),
    ("Complete the truth table for A AND B.", "A\tB\tQ\n0\t0\t0\n0\t1\t1\n1\t0\t0\n1\t1\t1", "INT-SUBJ-004"),
    ("Complete the truth table for A AND B.", "A,B,Q\n0,0,0\n0,1,1\n1,0,0\n1,1,1", "INT-SUBJ-004"),
])
def test_a_wrong_row_of_a_plain_truth_table_fails(request_, answer, code):
    assert fails_with(receive(CS, answer, request_), "stem-tt", code), answer


@pytest.mark.parametrize("request_, answer", [
    ("Complete the truth table for A NAND B.", "A B | A NAND B\n0 0 | 1\n0 1 | 1\n1 0 | 1\n1 1 | 0"),
    ("Complete the truth table for A AND B.", "A | B | A AND B\n--|---|--------\n0 | 0 | 0\n0 | 1 | 0\n1 | 0 | 0\n1 | 1 | 1"),
    ("Complete the truth table for A AND B.", "A B Q\n0 0 0\n0 1 0\n1 0 0\n1 1 1"),
    ("Complete the truth table for A AND B.", "A\tB\tQ\n0\t0\t0\n0\t1\t0\n1\t0\t0\n1\t1\t1"),
    ("Complete the truth table for A AND B.", "A,B,Q\n0,0,0\n0,1,0\n1,0,0\n1,1,1"),
    ("Complete the truth table for A AND B.", "| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |"),
])
def test_clean_control_a_right_plain_truth_table_holds(request_, answer):
    rc = receive(CS, answer, request_)
    assert held(rc) and not failed(rc) and not any(f.code.startswith("INT-SUBJ") for f in rc.findings), answer


def test_a_grid_of_letters_only_without_a_request_expression_is_named_not_checked():
    d = build_document("A B Q\n0 0 0\n0 1 1\n1 0 0\n1 1 1", "Fill in the table.", CS)
    tts = [r for r in d.relations if r.kind == "tt"]
    assert tts and not any(expr is not None for t in tts for _h, expr in t.table.outputs)


# ============================================================================================ major 12: rule rational-identity
@pytest.mark.parametrize("request_, answer", [
    ("Simplify (x² − 1)/(x − 1).", "We cancel the common factor, so (x² − 1)/(x − 1) = x − 1 for x ≠ 1."),
    ("Simplify (x² + 2x)/x.", "(x² + 2x)/x = x + 3"), ("Simplify (x² + 5x + 6)/(x + 2).", "(x² + 5x + 6)/(x + 2) = x + 2"),
    ("Simplify (2x³)(3x²).", "(2x³)(3x²) = 6x⁶"), ("Simplify x³ ÷ x.", "x³ ÷ x = x³"), ("Simplify x⁻² × x⁵.", "x⁻² × x⁵ = x⁷"),
    ("Show that (x + 3)² − 9 = x(x + 6).", "(x + 3)² − 9 = x² + 9x"),
    ("Simplify (x² − 1)/(x − 1).", "(x² − 1)/(x − 1) = (x − 1)(x + 1)/(x − 1) = x − 1"),
])
def test_a_wrong_rational_identity_or_index_law_fails(request_, answer):
    assert fails_with(receive(AA, answer, request_), "stem-alg"), answer


@pytest.mark.parametrize("request_, answer", [
    ("Simplify (x² − 1)/(x − 1).", "We cancel the common factor, so (x² − 1)/(x − 1) = x + 1 for x ≠ 1."),
    ("Simplify (x² + 2x)/x.", "(x² + 2x)/x = x + 2"), ("Simplify (x² + 5x + 6)/(x + 2).", "(x² + 5x + 6)/(x + 2) = x + 3"),
    ("Simplify (2x³)(3x²).", "(2x³)(3x²) = 6x⁵"), ("Simplify x³ ÷ x.", "x³ ÷ x = x²"), ("Simplify x⁻² × x⁵.", "x⁻² × x⁵ = x³"),
    ("Show that (x + 3)² − 9 = x(x + 6).", "(x + 3)² − 9 = x² + 6x"),
    ("Simplify (x² − 1)/(x − 1).", "(x² − 1)/(x − 1) = (x − 1)(x + 1)/(x − 1) = x + 1"),
])
def test_clean_control_a_right_rational_identity_or_index_law_holds(request_, answer):
    rc = receive(AA, answer, request_)
    assert no_stem_fault(rc) and held(rc), answer


def test_an_equation_under_a_show_request_that_states_no_identity_is_no_identity():
    rc = receive(AA, "x² + 2 = 2x + 1\nx² − 2x + 1 = 0\n(x − 1)² = 0, so x = 1",
                 "Show that the line y = 2x + 1 meets the curve y = x² + 2 at one point.")
    assert no_stem_fault(rc)


@pytest.mark.parametrize("request_, answer, code", [
    ("Prove that sin 2x = 2 sin x cos x.", "sin 2x = sin x cos x + cos x sin x = sin x cos x", "ST-UNDEC-001"),
])
def test_a_function_identity_is_named_never_silent(request_, answer, code):
    d = build_document(answer, request_, AA)
    assert code in [f.code for f in d.findings]


# ============================================================================================ major 13: rule length-root
@pytest.mark.parametrize("profile, request_, answer", [
    (AA, "A right-angled triangle has legs 3 cm and 4 cm. Find the hypotenuse.", "c² = 3² + 4² = 25, so c = 5"),
    (AI, "Use the cosine rule: a = 5, b = 7, C = 60°. Find c.", "c² = 5² + 7² − 2 × 5 × 7 × cos 60° = 39, so c = 6.24"),
    (AI, "A circle has area 25π cm². Find its radius.", "r² = 25, so r = 5 cm"),
])
def test_a_length_takes_its_principal_root_without_a_finding(profile, request_, answer):
    rc = receive(profile, answer, request_)
    assert no_stem_fault(rc) and "ST-ALG-001" not in [f.code for f in rc.structural_findings], answer


def test_control_the_principal_root_of_an_unknown_is_still_named():
    rc = receive(AA, "x² = 25, so x = 5", "Solve x² = 25.")
    assert "ST-ALG-001" in [f.code for f in rc.structural_findings]


def test_control_a_wrong_hypotenuse_still_fails():
    rc = receive(AA, "c² = 3² + 4² = 25, so c = 6", "A right-angled triangle has legs 3 cm and 4 cm. Find the hypotenuse.")
    assert fails_with(rc, "stem-sol")
