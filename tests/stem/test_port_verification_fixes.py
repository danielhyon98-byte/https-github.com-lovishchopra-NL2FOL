"""Port of the argument diagnostics onto the integrated translator: the findings of its verification
(docs/ARGUMENT_DIAGNOSTICS.md, section 20.10). Each case is decided through the channel, as the corpora decide it.

* A value the working substitutes inline that repeats the request's own value plans no check (the integrated translator
  checks only the arithmetic of 'v = d / t = 120 km / 2 h = 60 km/h'); one that contradicts the request is still checked
  and named stem_contradictory_givens.
* A stated operation on a line of working names its numeral in its own words ("Subtracting 4 from both sides then gives
  x = 8 − 4"), where the integrated reader keeps no prose value: the wrong operation is named stem_invalid_step.
* A root line whose stated step divides by an expression of the unknown, with no guard, carries ST-STEP-002 (info).
* A check decided in SI alone whose numbers hold as written names its failure stem_unit_error (a unit not converted),
  with no companion check; a slip that is wrong as written too stays an arithmetic slip, and correct working is clean."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"argdiag-port-verification-key-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
AGENTS = {"Chemistry": "chemistry-specialist", "Physics": "physics-specialist", "Mathematics: Analysis and Approaches": "maths-specialist"}
MAA = "Mathematics: Analysis and Approaches"


def _receipt(subject: str, request: str, answer: str):
    agent = AGENTS[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rq = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _failed(rc) -> list:
    return [(c.constraint_id, c.formal_status) for c in rc.formal_checks if c.satisfied is False]


def _subj_defects(rc) -> list:
    return [f.defect for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]


# ------------------------------------------------------------------------------------------- inline givens

TROLLEY = "A resultant force accelerates a 5.0 kg trolley at 3.0 m s⁻². Calculate the force. [2 marks]"
CAR = "A car travels 120 km in 2 hours. Find its average speed in km/h."


@pytest.mark.parametrize("request_text,answer,subject", [
    (TROLLEY, "F = ma = 5.0 kg × 3.0 m s⁻² = 15 N.", "Physics"),
    (CAR, "Average speed is distance divided by time.\nv = d / t = 120 km / 2 h = 60 km/h\nThe average speed is 60 km/h.", "Physics"),
], ids=["trolley", "car"])
def test_control_the_requests_own_value_inline_plans_no_given_check(request_text, answer, subject):
    rc = _receipt(subject, request_text, answer)
    assert not [c for c in rc.formal_checks if c.constraint_id.startswith("stem-giv")]
    assert _failed(rc) == []


def test_an_inline_value_that_contradicts_the_request_is_still_checked_and_named():
    rc = _receipt("Physics", TROLLEY, "F = ma = 4.0 kg × 3.0 m s⁻² = 12 N.")
    assert any(cid.startswith("stem-giv") for cid, _s in _failed(rc))
    assert "stem_contradictory_givens" in _subj_defects(rc)


# ------------------------------------------------------------------------------------------- stated operations

STEPS = "Solve 2x + 3 = 11, showing each step. [2 marks]"


def test_a_wrong_operation_stated_on_a_line_of_working_is_an_invalid_step():
    rc = _receipt(MAA, STEPS, "Starting from 2x + 3 = 11, subtracting 3 from both sides gives 2x = 8. "
                              "Subtracting 4 from both sides then gives x = 8 − 4 = 4. Therefore x = 4.")
    assert [cid for cid, _s in _failed(rc)] == ["stem-op-2"]
    assert _subj_defects(rc) == ["stem_invalid_step"]


def test_control_the_right_operation_stated_on_a_line_of_working_is_clean():
    rc = _receipt(MAA, STEPS, "Starting from 2x + 3 = 11, subtracting 3 from both sides gives 2x = 8. "
                              "Dividing both sides by 2 then gives x = 8/2 = 4. Therefore x = 4.")
    assert _failed(rc) == []
    assert "stem-op-2" in [c.constraint_id for c in rc.formal_checks]


# ------------------------------------------------------------------------------------------- a division by the unknown

QUAD = "Solve the equation 3x² = 12x. [2 marks]"


def test_a_root_line_that_divides_by_the_unknown_carries_st_step_002():
    rc = _receipt(MAA, QUAD, "3x² = 12x. Dividing both sides by 3x gives x = 4. So the solution is x = 4.")
    assert [(f.code, f.severity) for f in rc.structural_findings if f.code == "ST-STEP-002"] == [("ST-STEP-002", "info")]
    assert _failed(rc)  # the root check still decides that x = 0 is lost


def test_control_a_stated_guard_leaves_no_st_step_002():
    rc = _receipt(MAA, QUAD, "3x² = 12x. Since x ≠ 0, dividing both sides by 3x gives x = 4.")
    assert not [f for f in rc.structural_findings if f.code == "ST-STEP-002"]


# ------------------------------------------------------------------------------------------- unit errors on the integrated check

RUNNER = "A runner covers 2.5 km in 10 min. Calculate the runner's average speed in m s⁻¹. [2 marks]"
NAOH = "Calculate the amount of sodium hydroxide in 25.0 cm³ of a 0.100 mol dm⁻³ solution. [1 mark]"


@pytest.mark.parametrize("subject,request_text,answer", [
    ("Physics", RUNNER, "Using v = d/t, v = 2.5 km / 10 min = 0.25 m s⁻¹."),
    ("Physics", RUNNER, "Given d = 2.5 km and t = 10 min. The average speed is v = d/t = 0.25 m s⁻¹."),
    ("Physics", "A heater transfers 1200 J of energy in 2.0 min. Calculate its power in W. [2 marks]",
     "Using P = E/t, P = 1200 J / 2.0 min = 600 W."),
    ("Chemistry", NAOH, "n = cV = 0.100 mol dm⁻³ × 25.0 cm³ = 2.50 mol."),
], ids=["written arithmetic", "substitution", "minutes", "cubic centimetres"])
def test_numbers_that_hold_only_as_written_name_a_unit_error_on_the_one_check(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    failed = _failed(rc)
    assert len(failed) == 1 and not failed[0][0].endswith("u")  # no companion check: the integrated check alone
    assert _subj_defects(rc) == ["stem_unit_error"]


def test_a_slip_that_is_wrong_as_written_too_stays_an_arithmetic_slip():
    rc = _receipt("Physics", RUNNER, "Using v = d/t, v = 2.5 km / 10 min = 0.35 m s⁻¹.")
    assert _subj_defects(rc) == ["stem_arithmetic_slip"]


@pytest.mark.parametrize("subject,request_text,answer", [
    ("Physics", RUNNER, "Using v = d/t, v = 2500 m / 600 s = 4.2 m s⁻¹."),
    ("Chemistry", NAOH, "n = cV = 0.100 mol dm⁻³ × 0.0250 dm³ = 0.00250 mol."),
], ids=["converted", "converted volume"])
def test_control_converted_working_is_clean(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    assert _failed(rc) == [] and _subj_defects(rc) == []
