"""Repair round 4, ADV4-13: an argument in one sentence whose conclusion has a pronoun subject ("The organism is a
vertebrate, so it is a mammal") states its own reason: the pronoun names what the reason is about, so it counts as a word
of the conclusion. The claim is then eligible in every subject (it was "standalone analysis" in Biology, so the affirming
the consequent it writes was never diagnosed), as the same shape with a named subject already was in Economics. Controls:
a conclusion that says nothing ("so it is."), a sentence that opens with "So", and a question after "so" state no reason."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import states_own_reason
from epinoic_logic.translate.contracts import ClaimRecord
from epinoic_logic.translate.eligibility import decide_eligibility


def _claim(text: str, subject: str = "Biology", role: str = "analysis") -> ClaimRecord:
    return ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="biology-specialist", subject=subject, task_type="short_answer",
                       claim_id="s1.2", claim_text=text, claim_role=role, proposed_claim_kind="unknown")


@pytest.mark.parametrize("text", ["The organism is a vertebrate, so it is a mammal.", "The cells lack a nucleus, so they are prokaryotes.",
                                  "Firm X earns supernormal profit in the long run, so Firm X is a monopoly."])
def test_a_conclusion_with_a_pronoun_subject_states_its_own_reason(text):
    assert states_own_reason(text) == "so"


@pytest.mark.parametrize("subject", ["Biology", "Chemistry", "Economics", "Geography"])
def test_such_a_claim_is_eligible_in_every_subject(subject):
    decision = decide_eligibility(_claim("The organism is a vertebrate, so it is a mammal.", subject))
    assert decision.eligible and decision.eligibility_class.value == "PROPOSITIONAL_ARGUMENT"


@pytest.mark.parametrize("text", ["The organism is a vertebrate, so it is.", "So it goes.", "Prices rose, so what?", "It rained, so it."])
def test_control_a_conclusion_that_says_nothing_states_no_reason(text):
    assert states_own_reason(text) is None


def test_control_an_analysis_claim_with_no_reason_of_its_own_stays_not_eligible():
    decision = decide_eligibility(_claim("The organism is a vertebrate."))
    assert not decision.eligible
