"""Repair round 4, rerun-parser-safety-13 variant: the general figure reader of the prose branches reads one figure in two
notations as one value, so a direction it decides compares the whole values. Thousands grouped by a space ("45 000") are
one figure beside a plain or a scientific figure; a scale word multiplies its own figure only, so "2.5 million" is read
against "1.8 × 10⁶" or "1 800 000 tonnes" as 2 500 000. A correct "rose" holds and a wrong one fails, never the reverse;
a scale word against a figure whose unit word the reader does not know ("4 lakh") is still not compared."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"stem-channel-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
AGENTS = {"Economics": "economics-specialist", "Geography": "geography-specialist", "History": "history-specialist"}


def _quant_checks(subject: str, answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    agent = AGENTS[subject]
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _rq = hub.dispatch("t", agent, "Describe the change in exports.", [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc, [c for c in rc.formal_checks if c.constraint_id.startswith("core-quant")]


CORRECT = ["Exports rose from 30000 tonnes to 45 000 tonnes between 2010 and 2015.",
           "Exports rose from 3.0 × 10⁴ tonnes to 45 000 tonnes between 2010 and 2015.",
           "Exports rose from 2.5 million tonnes to 3 100 000 tonnes between 2010 and 2015.",
           "Exports rose from 2.5 million tonnes to 3.1 × 10⁶ tonnes between 2010 and 2015."]
WRONG = ["Exports rose from 2.5 million tonnes to 1.8 × 10⁶ tonnes between 2010 and 2015.",
         "Exports rose from 2.5 million tonnes to 1 800 000 tonnes between 2010 and 2015.",
         "Exports rose from 2.5 million tonnes to 1,800,000 tonnes between 2010 and 2015.",
         "Exports rose from 45 000 tonnes to 3.0 × 10⁴ tonnes between 2010 and 2015."]


@pytest.mark.parametrize("subject", sorted(AGENTS))
@pytest.mark.parametrize("answer", CORRECT)
def test_a_correct_direction_in_two_notations_holds(subject, answer):
    rc, checks = _quant_checks(subject, answer)
    assert checks and all(c.satisfied is True for c in checks)
    assert "INT-SUBJ-001" not in {f.code for f in rc.findings}


@pytest.mark.parametrize("subject", sorted(AGENTS))
@pytest.mark.parametrize("answer", WRONG)
def test_a_wrong_direction_in_two_notations_fails(subject, answer):
    rc, checks = _quant_checks(subject, answer)
    assert checks and any(c.satisfied is False for c in checks)
    assert "INT-SUBJ-001" in {f.code for f in rc.findings}


def test_control_a_scale_word_against_an_unknown_unit_word_is_not_compared():
    rc, checks = _quant_checks("Economics", "Exports rose from 4 billion rupees to 4 lakh rupees between 2010 and 2015.")
    assert checks == [] and "INT-SUBJ-001" not in {f.code for f in rc.findings}
