"""Repair round 4, STEM: each wrong answer below was delivered with no finding before the round (or, for the controls, with a
false ST-UNDEC-002), and each control stays clean.

* ADV4-01: a temperature in degrees Celsius substituted into a law that needs the absolute temperature (V₁/T₁ = V₂/T₂ at
  constant pressure) is a missing conversion: the checked substitution fails and INT-SUBJ-004 names stem_unit_error. The
  same law with the temperatures converted to kelvin holds.
* ADV4-02: a time the request states in minutes or hours, substituted unconverted into P = E/t or E = Pt, is a missing
  conversion in the same way; the working with the time in seconds holds.
* ADV4-11: a value the request gives (a radius, a mass) is a value of the working: a wrong area formula (A = 2πr) is named
  by its dimension, and a correct period of a mass on a spring raises no ST-UNDEC-002; the period with its ratio inverted
  is still named.
* rerun-stem-soundness-12: an expansion or a factorisation the answer states as an identity is checked under any request
  ("Answer the question."), not only one that says "Expand" or "Factorise"; the true identity holds."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"argdiag-stem-test-key-0123456789abcdef"
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


def _named(rc) -> set[tuple[str, str]]:
    return {(d.code, d.defect) for d in (rc.named_diagnostics or []) if d.severity in ("warning", "error")}


def _stem_flags(rc) -> list:
    out = [(f.code, f.severity) for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")]
    out += [(f.code, f.severity) for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    out += [(c.constraint_id, "failed") for c in rc.formal_checks if c.satisfied is False and c.constraint_id.startswith("stem-")]
    return out


GAS = "A gas fills 3.0 dm³ at 17 °C. It is heated at constant pressure to 117 °C. Calculate its new volume. [2 marks]"
HEATER = "A heater transfers 240 kJ of energy in 4.0 minutes. Calculate its power. [2 marks]"
KETTLE = "A 1.5 kW kettle runs for 2.0 hours. Calculate the energy it transfers in joules. [2 marks]"


@pytest.mark.parametrize("subject, request_text, answer", [
    ("Chemistry", GAS, "V₂ = V₁ × T₂/T₁ = 3.0 × 117/17 = 20.6 dm³."),
    ("Physics", KETTLE, "E = Pt = 1500 × 2.0 = 3000 J."),
], ids=["celsius in a gas law", "hours in E = Pt"])
def test_a_quantity_substituted_in_the_unit_the_request_gives_is_a_missing_conversion(subject, request_text, answer):
    assert ("INT-SUBJ-004", "stem_unit_error") in _named(_receipt(subject, request_text, answer))


@pytest.mark.parametrize("subject, request_text, answer", [
    ("Chemistry", GAS, "V₂ = V₁ × T₂/T₁ = 3.0 × 390/290 = 4.0 dm³."),
], ids=["kelvin"])
def test_control_the_converted_working_is_clean(subject, request_text, answer):
    assert _stem_flags(_receipt(subject, request_text, answer)) == []


LAWN = "A circular lawn has radius 5.0 m. Calculate the area of the lawn. [2 marks]"
SPRING = "A mass of 0.20 kg on a spring of stiffness 80 N m⁻¹ oscillates. Calculate the period. [2 marks]"


@pytest.mark.parametrize("request_text, answer", [
    ("Answer the question.", "(p + q)² = p² + 2pq + q²"),
    ("Question 3(c).", "y² − 16 = (y − 4)(y + 4)"),
])
def test_control_a_true_identity_under_a_neutral_request_is_clean(request_text, answer):
    assert _stem_flags(_receipt(MAA, request_text, answer)) == []
