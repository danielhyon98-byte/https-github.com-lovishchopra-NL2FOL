"""Repair round 4, rerun-stem-precision-11 variant: in a branch with no word-count view of its own (Economics, Business
Management, Geography, Psychology), an answer that is a worked calculation ("12 500 + 7 500 = 20 000") has an answer
proper, one word per calculation, as a STEM branch counts a maths span: it is never INT-REQ-012 ("the response carries
no answer"), in any notation of its figures. The controls: a response that is only a note, and a calculation inside
quotation marks (someone else's), still carry no answer of their own."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"stem-channel-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
SUBJECTS = {"Economics": "economics-specialist", "Business Management": "business-management-specialist",
            "Geography": "geography-specialist", "Psychology": "psychology-specialist"}


def _codes(subject: str, answer: str) -> set[str]:
    agent = SUBJECTS[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _rq = hub.dispatch("t", agent, "Calculate total revenue.", [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return {f.code for f in rc.findings}


@pytest.mark.parametrize("subject", sorted(SUBJECTS))
@pytest.mark.parametrize("answer", ["12 500 + 7 500 = 20 000", "12500 + 7500 = 20000", "12,500 + 7,500 = 20,000"])
def test_a_worked_calculation_is_an_answer_in_every_subject(subject, answer):
    assert "INT-REQ-012" not in _codes(subject, answer)


@pytest.mark.parametrize("subject", sorted(SUBJECTS))
@pytest.mark.parametrize("answer", ["Note: I have not been given enough information to answer this.", '"12 500 + 7 500 = 20 000"'])
def test_control_a_note_alone_or_a_quoted_calculation_carries_no_answer(subject, answer):
    assert "INT-REQ-012" in _codes(subject, answer)
