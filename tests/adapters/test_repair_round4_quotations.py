"""Repair round 4: quotation roles are read in the task (INV-Q1, INV-Q2), the corrected forms of marking feedback in more
words (ADV4-04), and words the writer says the text does not use (ADV4-03).

* A correction or a suggestion is read only in a marking or feedback task (the plan's task type, set by the channel). In a
  literary or a source analysis an arrow, a "Model:" label, an imperative "use" or "try", 'Not "x" but "y"' or '"x"
  should be "y"' leaves the span a quotation, so an altered quotation written that way is still named (INT-REQ-003) and the
  response gate withholds the answer instead of labelling it verified.
* In a feedback task the corrected form is read in more frames: "becomes", a "Model:" or "Corrected:" label after a
  sentence of the line, "it should read", "the corrected sentence is", "a better version would be", "rewrite it as", and
  ", giving" after a correction. A prescribed quotation of a text ('the quotation should read "..."') stays a quotation.
* A word the writer says the text avoids, leaves out or could have used is a mention in any task.

Each class has its positive and its clean control; the texts are this round's own."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import corrections_apply, find_quotation_spans, quotation_role, quotation_task
from epinoic_logic.channel.gate import assess_response

from ..evidence_support import deliver

_POEM = ("Evening on the Estuary\n\nThe river keeps its silver counsel,\nand the patient willows bend\n"
         "to read what the slow water writes\nbefore the dark comes in.")


def _case(cid: str, answer: str, *, subject: str, task_type: str, agent: str, request: str, texts: list[dict]) -> dict:
    return {
        "case_format": "argdiag-corpus/1", "id": cid, "family": "evidence", "expected_label": "none", "acceptable_labels": [],
        "title": cid, "subject": subject, "task_type": task_type, "agent_id": agent, "request": request, "answer": answer,
        "supplied_texts": texts, "ids": {"task_id": f"task-{cid}", "request_id": f"req-{cid}", "report_id": "rep-1", "plan_id": f"plan-{cid}"},
        "report_claims": [], "translations": [], "fidelity_review": "faithful",
    }


def _poem_case(answer: str, task_type: str = "analytical_paragraph") -> dict:
    return _case("r4-poem", answer, subject="English A: Literature", task_type=task_type, agent="english-specialist",
                 request="How does the poet present the willows in this extract? [4 marks]",
                 texts=[{"document_id": "poem-r4", "title": "Evening on the Estuary", "author": "A. Poet", "text": _POEM}])


_SOURCE = ("Source B: from a letter by a mill owner, 1842. 'The new law is an act of betrayal by the government, and we will "
           "obey it only because we must.'")


def _source_case(answer: str) -> dict:
    return _case("r4-source", answer, subject="History", task_type="source_analysis", agent="history-specialist",
                 request="What does Source B suggest about attitudes to the new law? [3 marks]",
                 texts=[{"document_id": "source-b", "title": "Source B", "text": _SOURCE}])


def _spanish_case(answer: str) -> dict:
    return _case("r4-es", answer, subject="Language B: Spanish", task_type="marking_feedback", agent="language-b-spanish-specialist",
                 request='Give feedback on the student\'s sentence: "Mis amigos es muy divertido y vamos a la playa ayer." [4 marks]', texts=[])


def _codes(rc) -> set[str]:
    return {f.code for f in rc.findings} | {f.code for f in rc.structural_findings}


def _altered_named(rc, changed_word: str) -> bool:
    """An INT-REQ-003 error that names the word the quotation changed."""
    return any(f.code == "INT-REQ-003" and f.severity == "error" and f"'{changed_word}'" in f.message for f in rc.findings)


# ------------------------------------------------------------------------------------------- INV-Q1: frames outside feedback

_ALTERED = '"the silent willows bend"'      # the poem has "the patient willows bend"
_GENUINE = '"the patient willows bend"'


@pytest.mark.parametrize("frame", [
    "The image → {q} gives the trees a human calm.",
    "Look at the image; use {q} to show their calm.",
    "Model: {q} gives the trees a human calm.",
    'Not "the patient willows" but {q} gives the trees a human calm.',
    'The words "the patient willows" should be {q} here, giving the trees a human calm.',
    "Try {q} as evidence of their calm.",
])
def test_an_altered_quotation_in_a_correction_frame_is_named_in_a_literary_analysis(frame):
    answer = "The poet presents the willows as wise. " + frame.format(q=_ALTERED) + " They seem to listen to the river."
    _case_, rc = deliver(_poem_case(answer), "text")
    assert _altered_named(rc, "silent"), sorted(_codes(rc))


@pytest.mark.parametrize("frame", [
    "The image → {q} gives the trees a human calm.",
    "Model: {q} gives the trees a human calm.",
    "Look at the image; use {q} to show their calm.",
])
def test_control_a_genuine_quotation_in_the_same_frames_is_found(frame):
    answer = "The poet presents the willows as wise. " + frame.format(q=_GENUINE) + " They seem to listen to the river."
    _case_, rc = deliver(_poem_case(answer), "text")
    assert "INT-REQ-003" not in _codes(rc) and "ES-SRC-001" not in _codes(rc)


@pytest.mark.parametrize("frame", [
    'The owner calls the law → "an act of treason by the government", so he resents it.',
    'Not "an act of betrayal by the government" but "an act of treason by the government", so he resents it.',
    'Consider the letter; try "an act of treason by the government" as the evidence of resentment.',
])
def test_an_altered_quotation_of_a_source_is_named_and_the_gate_withholds_it(frame):
    answer = "Source B suggests that some owners resented the law. " + frame + " He will obey it \"only because we must\"."
    _case_, rc = deliver(_source_case(answer), "text")
    assert _altered_named(rc, "treason"), sorted(_codes(rc))
    decision = assess_response([rc], synthesis_required=False)
    assert decision.display_status != "VERIFIED"


def test_control_the_genuine_source_quotation_is_delivered_without_a_quotation_finding():
    answer = ('Source B suggests that some owners resented the law. The owner calls it "an act of betrayal by the government", '
              'and he will obey it "only because we must", which shows resentment rather than support.')
    _case_, rc = deliver(_source_case(answer), "text")
    assert "INT-REQ-003" not in _codes(rc)


def test_a_report_cannot_widen_the_roles_by_naming_a_feedback_task_type_of_its_own():
    """The channel reads the roles in the plan's task type for the agent: the parser's or the report's own task type only
    applies where no enclosing call set one."""
    with quotation_task("analytical_paragraph", authoritative=True):
        with quotation_task("marking_feedback"):
            text = 'The image → "the silent willows bend".'
            s, e, _inner = find_quotation_spans(text)[0]
            assert quotation_role(text, s, e) == "quotation"
    assert corrections_apply("marking_feedback") and corrections_apply("proofreading") and corrections_apply("essay_feedback")
    assert not any(corrections_apply(t) for t in ("analytical_paragraph", "source_analysis", "essay", "short_answer", "credit_check", None, ""))


# ------------------------------------------------------------------------------------------- ADV4-04: corrected forms

@pytest.mark.parametrize("answer", [
    'Two errors: "es" becomes "son", and "divertido" becomes "divertidos".',
    'Two errors in agreement and tense. Model: "Mis amigos son muy divertidos y fuimos a la playa ayer."',
    'Two errors: it should read "Mis amigos son muy divertidos y fuimos a la playa ayer."',
    'Two errors. The corrected sentence is "Mis amigos son muy divertidos y fuimos a la playa ayer."',
    'Two errors in agreement and tense. Corrected: "Mis amigos son muy divertidos y fuimos a la playa ayer."',
    'Two errors. A better version would be "Mis amigos son muy divertidos y fuimos a la playa ayer."',
    'Two errors; rewrite it as "Mis amigos son muy divertidos y fuimos a la playa ayer."',
    'Two errors: change "vamos" to "fuimos", giving "Mis amigos son muy divertidos y fuimos a la playa ayer."',
])
def test_the_corrected_forms_of_marking_feedback_raise_no_quotation_finding(answer):
    _case_, rc = deliver(_spanish_case(answer), "text")
    assert not [f for f in [*rc.findings, *rc.structural_findings]
                if f.code in ("CORE-SRC-003", "INT-REQ-003", "CORE-SRC-001") and f.severity in ("warning", "error")], sorted(_codes(rc))


def test_control_a_misquotation_of_the_students_words_is_still_named_in_feedback():
    _case_, rc = deliver(_spanish_case('You wrote "Mis amigos es muy divertidos", which should be "Mis amigos son muy divertidos".'), "text")
    assert [f for f in [*rc.findings, *rc.structural_findings] if f.code in ("INT-REQ-003", "CORE-SRC-003") and "Mis amigos es muy divertidos" in f.message]


def test_control_a_prescribed_quotation_of_a_text_stays_a_quotation_in_feedback():
    text = 'Quote exactly: the last quotation should read "the patient willows bend", not "the willows bend".'
    with quotation_task("marking_feedback"):
        roles = [quotation_role(text, s, e) for s, e, _i in find_quotation_spans(text)]
    assert roles == ["quotation", "quotation"]
    with quotation_task("marking_feedback"):
        text2 = 'Your sentence should read "Mis amigos son divertidos".'
        assert [quotation_role(text2, s, e) for s, e, _i in find_quotation_spans(text2)] == ["correction"]


# ------------------------------------------------------------------------------------------- ADV4-03: mentions

@pytest.mark.parametrize("sentence", [
    'The willows "bend", and the poet avoids "very" or any intensifier, so the calm is unforced.',
    'The poet could have used "lean", but "bend" makes the trees seem to bow.',
    'The poet leaves out "and" between the last two lines, so the dark arrives abruptly.',
])
def test_a_word_the_text_does_not_use_is_a_mention_not_an_invented_quotation(sentence):
    answer = 'The poet presents the willows as wise: they are "patient", and they "read what the slow water writes". ' + sentence
    _case_, rc = deliver(_poem_case(answer), "text")
    assert not ({"INT-REQ-003", "ES-SRC-001", "INT-LEDGER-025"} & _codes(rc)), sorted(_codes(rc))


def test_control_an_invented_word_credited_to_the_poem_is_still_named():
    answer = ('The poet presents the willows as wise: they are "patient", and they "read what the slow water writes". '
              'The poet calls them "ancient", so they seem to remember.')
    _case_, rc = deliver(_poem_case(answer), "text")
    assert {"INT-REQ-003", "ES-SRC-001"} & _codes(rc)


def test_a_mention_frame_is_read_in_every_task_and_a_correction_frame_only_in_feedback():
    text = 'The writer avoids "very", and → "the silent willows bend".'
    for task, expected in (("analytical_paragraph", ["mention", "quotation"]), ("marking_feedback", ["mention", "correction"])):
        with quotation_task(task):
            assert [quotation_role(text, s, e) for s, e, _i in find_quotation_spans(text)] == expected
