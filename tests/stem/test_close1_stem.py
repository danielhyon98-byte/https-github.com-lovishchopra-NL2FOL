"""Close round 1 of the argument-diagnosis regression review, the STEM readings (ADV6-02, ADV6-07):

* ADV6-02: a prose value of the other sign than its own statement's chain ("= −4.0 m s⁻², so the deceleration is 4.0
  m s⁻²") states the magnitude, in the words of a direction; it was checked against the signed value and failed as a
  stem_result error. It is no restatement now. A restatement of the same sign is checked as before, so a wrong one fails.
* ADV6-07: a value in prose is where a model is evaluated only when the prose gives it as the input ("at 90 °C"); a rate
  ("rises by 0.05 °C per year"), a step and a result ("= 13.4 A, which is ...") were read as the input and a correct
  interpolation, or a plain sum, was named an extrapolation. An extrapolation given at its input is still named.

Wording of this round's own; each positive was checked to fail on the tree before the round."""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"argdiag-stem-test-key-close1-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
AGENTS = {"Physics": "physics-specialist", "Chemistry": "chemistry-specialist", "Biology": "biology-specialist",
          "Environmental Systems and Societies": "ess-specialist"}


def _receipt(subject: str, request: str, answer: str):
    agent = AGENTS[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rq = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _errors(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


def _failed(rc, prefix: str) -> list:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is False and c.constraint_id.startswith(prefix)]


def _range(rc) -> list:
    return [f for f in rc.structural_findings if f.code == "ST-RANGE-001"]


# ------------------------------------------------------------------------------------------- ADV6-02: a magnitude in words

def test_a_magnitude_stated_after_its_own_signed_chain_is_no_restatement_error():
    rc = _receipt("Physics", "A van slows from 16 m s⁻¹ to rest in 4.0 s. Calculate its deceleration. [2 marks]",
                  "a = (v − u)/t = (0 − 16)/4.0 = −4.0 m s⁻², so the deceleration is 4.0 m s⁻².")
    assert _errors(rc) == [] and _failed(rc, "stem-res") == []


def test_a_magnitude_of_work_against_a_force_is_no_restatement_error():
    rc = _receipt("Physics", "A 4.0 kg crate slides to rest from 2.0 m s⁻¹. Calculate the work done by friction. [2 marks]",
                  "W = ΔE_k = 0 − ½ × 4.0 × 2.0² = −8.0 J, so friction does 8.0 J of work against the motion.")
    assert _errors(rc) == [] and _failed(rc, "stem-res") == []


# ------------------------------------------------------------------------------------------- ADV6-07: the model's input

POND = ("A pond's mean summer temperature was 16.0 °C in 2000, 16.5 °C in 2010 and 17.0 °C in 2020. Use the trend to estimate the "
        "temperature in 2014. [2 marks]")


def test_a_rate_in_an_interpolation_is_no_extrapolation():
    rc = _receipt("Environmental Systems and Societies", POND,
                  "The temperature rises by 0.05 °C per year, so in 2014 it is about 16.5 + 0.05 × 4 = 16.7 °C.")
    assert _range(rc) == []


def test_a_sum_and_its_result_evaluate_no_model():
    rc = _receipt("Physics", "A fuse is rated at 13 A. A kettle draws 6.2 A, a toaster 4.1 A and a lamp 3.1 A. Calculate the total current. [2 marks]",
                  "I = 6.2 + 4.1 + 3.1 = 13.4 A, which is 13 A to 2 s.f.")
    assert _range(rc) == []   # the sum's result restated in prose is no input of a model (its rounding is another reading)


def test_control_a_model_evaluated_at_an_input_beyond_the_data_is_still_named():
    rc = _receipt("Biology", "The rate of an enzyme reaction was 3.0, 6.0 and 9.0 units at 10, 20 and 30 °C. Predict the rate at 90 °C. [2 marks]",
                  "The rate rises by 3.0 units for every 10 °C, so rate = 0.30T. At 90 °C, rate = 0.30 × 90 = 27 units.")
    [f] = _range(rc)
    assert f.defect == "stem_extrapolation" and "90" in f.message
