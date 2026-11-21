"""Round-10 leftover R10-COMB-H3-SET-QUESTIONS (combinator H3, parsers H9 extension): the generic and STEM parsers roled the questions
an answer sets the student ('To test your design, answer these from your own plan:' and three numbered questions) ``other``, so they
were read as notes and a synthesis that dropped them was named by nothing. A question the answer sets the student is content on every
branch (combinator pack 1.4 rule 6): after a lead that tells the student to answer the questions after it
(``markdown.opens_set_questions``, the lead the English parsers read), each question is a material claim, never ``other``. A
question back to the student ('Would you like me to say more about the reparations?') stays a note on every branch (control)."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import opens_set_questions

from tests.channel.c3_core_support import _deliver

SUBJECTS = [("History", "history-specialist"), ("Psychology", "psychology-specialist"), ("Economics", "economics-specialist"),
            ("Biology", "biology-specialist"), ("Physics", "physics-specialist"), ("Geography", "geography-specialist"),
            ("English A: Language and Literature", "english-a-lang-lit-specialist"), ("English A: Literature", "english-a-literature-specialist")]
SET = ("Your topic is allowed, but your aim needs a direction.\n\nTo test your design, answer these from your own plan:\n"
       "1. Your plan uses two groups of students. Why an experiment rather than a survey for this aim?\n"
       "2. Your plan times the reading. What does the time limit add to the stress of the task?\n"
       "3. Does one measure work for both groups, or only one?\n\nNext, write your aim as one sentence.")
QUESTIONS = ("Why an experiment rather than a survey", "What does the time limit add", "Does one measure work for both groups")


def _claims(subject: str, agent: str, text: str) -> list[dict]:
    item = {"task_id": "probe-set", "subject": subject, "agent_id": agent, "task_type": "short_answer",
            "question": "Give me feedback on my research aim and design.", "supplied_texts": [], "response_text": text}
    hub, _ch, reply, _rc = _deliver(item, None, None)
    hub.close()
    return reply.payload["claims"]


@pytest.mark.parametrize("subject, agent", SUBJECTS, ids=[s for s, _a in SUBJECTS])
def test_the_questions_an_answer_sets_the_student_are_content_on_every_branch(subject, agent):
    claims = _claims(subject, agent, SET)
    for q in QUESTIONS:
        found = [c for c in claims if q in c["claim_text"]]
        assert found, (q, [c["claim_text"][:80] for c in claims])
        assert all(c["claim_role"] != "other" for c in found), (subject, q, [(c["claim_role"], c["materiality"]) for c in found])
        if subject not in ("History",):  # the History parser's roles are its own (analysis, supporting): content all the same
            assert any(c["materiality"] == "material" for c in found), (subject, q, [(c["claim_role"], c["materiality"]) for c in found])


@pytest.mark.parametrize("subject, agent", SUBJECTS, ids=[s for s, _a in SUBJECTS])
def test_control_a_question_back_to_the_student_stays_a_note(subject, agent):
    text = ("The treaty weakened the economy because the reparations drained the budget for years.\n\n"
            "Would you like me to say more about the reparations?")
    claims = _claims(subject, agent, text)
    back = [c for c in claims if c["claim_text"].startswith("Would you like me")]
    assert back and all(c["claim_role"] == "other" for c in back), [(c["claim_role"], c["claim_text"][:60]) for c in claims]


def test_the_lead_reader_is_shared_and_bounded():
    assert opens_set_questions("To test your design, answer these from your own plan:")
    assert opens_set_questions("Ask yourself these questions:")
    assert not opens_set_questions("Answer the question in one paragraph.")
    assert not opens_set_questions("x" * 10_000 + " answer these:")
