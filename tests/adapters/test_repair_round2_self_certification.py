"""Repair round 2 (combinator-faults-3 variant): verification-status language is read as a class, not as listed phrases.
A status line ("Verification: passed."), the infrastructure as the agent of a certifying verb with a complement ("confirmed
correct by the verification engine") or as what the answer's items passed ("each step passed the automated checker"), and
the answer proven or certified correct ("has been mathematically proven correct") are self-certifications, in a specialist's
answer (INT-HANDOFF-006) and in a synthesis (the ledger's self-report reader, INT-LEDGER-029). The controls are arguments
and descriptions that use the same words about something else."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import is_self_certification
from epinoic_logic.integrity.ledger import _self_report_sentences

from ..evidence_support import deliver

SELF_REPORTS = [
    "All of the calculations above were confirmed correct by the verification engine.",
    "Each step passed the automated checker, so the answer is certified.",
    "Each step passed the automated checker.",
    "This answer has been mathematically proven correct.",
    "These calculations have been proven correct.",
    "Every calculation in this answer has been formally verified.",
    "The working above was checked by the solver.",
    "Verification: passed.",
    "Checks: OK.",
    "Self-check — complete.",
]

ARGUMENTS = [
    "The theorem was proven by Euler in 1736.",
    "Pythagoras' theorem can be proven using similar triangles.",
    "This proves that the function is continuous.",
    "The doctor certified the death on 3 May.",
    "Shakespeare's sonnet is certified as authentic by later scholars.",
    "The result is certified by the examiner.",
    "The algorithm passes the input to the checker, which verifies the syntax.",
    "The spell checker flags every misspelt word.",
    "In the student's working, the first step is correct but the second is not.",
    "The candidate's derivation is shown to be correct in the mark scheme.",
    "The scientist's calculations were checked by a colleague.",
    "Mendel's results were confirmed by later experiments.",
    "Each step of mitosis is described in the textbook.",
    "Results: positive in 3 of 5 trials.",
    "Conclusion: the hypothesis is supported.",
    "The checks: passport, visa and ticket.",
    "If all checks pass, the record is saved.",
    "Verification of the claim requires the 1851 census.",
    "A proof check of the derivation needs the second law.",
    "We can verify this: substituting x = 2 gives 4 = 4.",
]


@pytest.mark.parametrize("sentence", SELF_REPORTS)
def test_verification_status_language_is_a_self_certification(sentence):
    assert is_self_certification(sentence)
    assert _self_report_sentences(sentence) == [sentence]


@pytest.mark.parametrize("sentence", ARGUMENTS)
def test_the_same_words_about_something_else_are_no_self_certification(sentence):
    assert not is_self_certification(sentence)
    assert _self_report_sentences(sentence) == []


def _answer(extra: str) -> dict:
    return {"case_format": "argdiag-corpus/1", "id": "self-report", "family": "evidence", "expected_label": "none", "acceptable_labels": [],
            "title": "self-report", "subject": "Business Management", "task_type": "short_answer", "agent_id": "business-management-specialist",
            "request": "Calculate the firm's contribution per unit if the price is $12 and the unit variable cost is $7. [2 marks]",
            "answer": f"The contribution per unit is $12 − $7 = $5. {extra}".strip(), "supplied_texts": [],
            "ids": {"task_id": "task-sr", "request_id": "req-sr", "report_id": "rep-sr", "plan_id": "plan-sr"},
            "modes": [{"name": "text", "delivery": "text", "synthesis": "none"}], "report_claims": [], "translations": [], "fidelity_review": "faithful"}


@pytest.mark.parametrize("sentence", SELF_REPORTS[:4] + SELF_REPORTS[7:8])
def test_a_specialist_answer_that_certifies_itself_is_named(sentence):
    _case, rc = deliver(_answer(sentence), "text")
    assert "INT-HANDOFF-006" in {f.code for f in rc.findings}


def test_the_same_answer_without_the_status_sentence_is_clean():
    _case, rc = deliver(_answer(""), "text")
    assert "INT-HANDOFF-006" not in {f.code for f in rc.findings}
