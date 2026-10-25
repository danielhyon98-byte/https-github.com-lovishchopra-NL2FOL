"""Repair round 4, two readings of the generic parser and the core pack that charged correct end-to-end answers:

* E2E-HI-MENTION-READ-AS-OWN-ARITHMETIC: an equation whose relation sign stands inside quotation marks is a mention of
  another report's line, even when the phrase the equation reader finds opens on the words before the quotation ('... flag
  its written line "ln 2.5 + 3 ln 10 = 4.9" as not holding'): it is not the answer's own arithmetic, so no INT-SUBJ-001
  is raised on it (CORE-QNT-001 still says it was not decided). The same equation written as the answer's own line is
  still checked and fails.
* E2E-CS-FALSE-BARE-ASSERTION: a check tip ("To check your method, binary_search(scores, 41) should print (8, 4).", "As a
  check, the frequencies should add up to 1000.") states the result a check expects; its "should" is no judgement, so the
  sentence is not read as the section's judgement (which ARG-BARE-001 then found unsupported). A recommendation with
  "should" stays a judgement."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"argdiag-branch-test-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
REQUEST = "To what extent did the economic crisis explain the rise of the Nazi vote between 1928 and 1932? [8 marks]"


def _receipt(answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="essay", selected_agent_ids=["history-specialist"]))
    m, _req, _rq = hub.dispatch("t", "history-specialist", REQUEST, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="history-specialist", report_id="r1")
    return rc


def test_an_equation_quoted_from_another_report_is_a_mention_not_the_answers_arithmetic():
    rc = _receipt('The Mathematics report\'s own checks flag its written line "ln 2.5 + 3 ln 10 = 4.9" as not holding, so its doubling '
                  'time cannot be used here.')
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert [f for f in rc.structural_findings if f.code == "CORE-QNT-001"]


def test_control_the_same_equation_as_the_answers_own_line_is_checked_and_fails():
    rc = _receipt("Its written line ln 2.5 + 3 ln 10 = 4.9 shows the doubling time.")
    assert [f.severity for f in rc.findings if f.code == "INT-SUBJ-001"] == ["error"]


def _roles(subject: str, text: str) -> list[tuple[str, str]]:
    branch, _profile = default_registry().for_subject(subject)
    report = branch.parser().parse_response(text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type="short_answer",
                                            supplied_texts=[], agent_id="cs-specialist")
    return [(c.claim_role, c.materiality) for c in report.claims]


POINT = "(c) The search halves the range each pass, so it needs at most 4 passes for 9 items.\n"


@pytest.mark.parametrize("tip", ["To check your method, binary_search(scores, 41) should print (8, 4).",
                                 "As a check, the frequencies should add up to 1000.",
                                 "If your trace is right, the last pass should return index 8."])
def test_a_check_tip_is_no_judgement(tip):
    assert _roles("Computer Science", POINT + tip)[1] != ("judgement", "material")


def test_control_a_recommendation_with_should_stays_a_judgement():
    assert _roles("Computer Science", POINT + "The method should be rewritten as a loop.")[1] == ("judgement", "material")
