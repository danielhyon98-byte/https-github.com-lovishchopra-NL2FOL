"""ST-STEP-001 (stem_invalid_step): the operation the answer states for a step ('adding 4 to both sides') does not turn the
equation before it into the equation after it, although the step's result may be right; decided by the engine (an ``op``
check, Form B: a witness that tells the sides apart). ST-STEP-002 (info): a step divides both sides by an expression of
the unknown that no stated condition keeps from being zero.
"""
from __future__ import annotations

from epinoic_logic.named import NAMED_CODES

from .argdiag_hub import decided, deliver, failed_checks, findings, plan, stem_flags

SOLVE = "Solve x/4 = 2, showing each step."


def test_a_stated_operation_that_does_not_give_the_next_equation_is_st_step_001():
    rc = deliver("s05_invalid_step_correct_answer")
    [f] = findings(rc, "INT-SUBJ-004")
    assert f.severity == "warning" and f.defect == "stem_invalid_step" and "ST-STEP-001" in f.message
    assert [c.constraint_id for c in failed_checks(rc)] == ["stem-op-1"]
    assert NAMED_CODES["ST-STEP-001"].defect == "stem_invalid_step"


def test_control_the_operation_that_gives_the_next_equation_is_clean():
    assert stem_flags(deliver("s05c_control_valid_step")) == []
    checks = decided("Starting from x/4 = 2, multiplying both sides by 4 gives x = 4 × 2 = 8. Therefore x = 8.", SOLVE, "mathematics_aa")
    assert "stem-op-1" in checks and checks["stem-op-1"][1] is True


def test_the_result_is_still_checked_beside_the_operation():
    # the op check names the stated operation; the step itself (x/4 = 2 to x = 8) holds and is checked on its own
    checks = decided("Starting from x/4 = 2, adding 4 to both sides gives x = 4 + 4 = 8. Therefore x = 8.", SOLVE, "mathematics_aa")
    assert checks["stem-op-1"][1] is False and checks["stem-op-1"][0].defect == "stem_invalid_step"
    assert all(ok is True for cid, (_pc, ok) in checks.items() if cid != "stem-op-1")


def test_an_unguarded_division_by_the_unknown_is_st_step_002_at_info():
    doc, p = plan("x² = 3x\nDividing both sides by x: x = 3", None, "mathematics_aa")
    notes = [f for f in list(doc.findings) + list(p.findings) if f.code == "ST-STEP-002"]
    assert notes and all(f.severity == "info" for f in notes) and "divides by x" in notes[0].message
    assert NAMED_CODES["ST-STEP-002"].max_severity == "info"


def test_control_a_division_with_its_condition_stated_gives_no_note():
    doc, p = plan("x² = 3x\nDividing both sides by x (x ≠ 0): x = 3", None, "mathematics_aa")
    assert not [f for f in list(doc.findings) + list(p.findings) if f.code == "ST-STEP-002"]
