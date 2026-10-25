"""Quotation roles (B5, B6; ``adapters.markdown.quotation_role``): only closed frames give a quoted span a role other than
``quotation``. A correction (the right-hand side of an arrow, "should be", "change ... to", a "Model:" or "Corrected:"
label governing the span), a suggestion ("you could write", an imperative "try" or "add") or a mention (a quoted function
word, a short span after a negating frame) is the writer's own words: it is never checked or attributed as a quotation.
Everything else stays a quotation and is checked, so an invented or altered quotation is still named, and every span,
whatever its role, stays masked.

Rewritten in repair round 4 (INV-Q1) to a stricter rule: a correction or a suggestion is read only in a marking or feedback
task (``markdown.quotation_task``), so every feedback frame below is evaluated in the task type it belongs to, and the same
frames in an analysis task leave the span a quotation (``test_feedback_frames_are_quotations_in_an_analysis_task``). A
mention is read in every task."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import (cited_quotation_spans, find_quotation_spans, mask_quotations, quotation_role, quotation_task,
                                             uncited_quotation_spans)
from epinoic_logic.adapters.sources import check_excerpt, unwrap_emphasis
from epinoic_logic.translate.contracts import SuppliedText

from .. import argdiag_cases as C
from ..evidence_support import deliver


FEEDBACK = "marking_feedback"
ANALYSIS = "analytical_paragraph"


def _roles(text: str, task_type: str | None = None) -> list[tuple[str, str]]:
    """The roles of every span of ``text`` read in a task of type ``task_type`` (none: no task known)."""
    with quotation_task(task_type):
        return [(inner, quotation_role(text, s, e)) for s, e, inner in find_quotation_spans(text)]


def _codes(rc) -> set[str]:
    return {f.code for f in rc.findings} | {f.code for f in rc.structural_findings}


# ------------------------------------------------------------------------------------------------------- B5 and B6

def test_e2e_b5_the_corrected_forms_are_corrections_and_the_students_words_are_checked_and_found():
    _case, rc = deliver("e2e-B5-sp", "text")
    assert "INT-REQ-003" not in _codes(rc)                  # the 7 corrected forms after the arrows were read as altered quotations
    assert not [f for f in rc.structural_findings if f.code == "CORE-SRC-003" and f.severity == "warning"]
    answer = C.load_case("e2e-B5-sp")["answer"]
    roles = dict(_roles(answer, FEEDBACK))
    assert roles["*una mujer muy simpática*"] == "correction" and roles["*una mujer muy simpático*"] == "quotation"
    assert roles["*para ayudar*"] == "correction" and roles["*por ayudar*"] == "quotation"   # 'Suggestion, not an error: "x" → "y"'
    # the same answer read in an analysis task, or with no task known: no span is the writer's own correction
    for task in (ANALYSIS, None):
        assert not {r for _inner, r in _roles(answer, task)} & {"correction", "suggestion"}


def test_e2e_b6_a_function_word_after_a_negating_frame_is_a_mention():
    _case, rc = deliver("e2e-B6-en", "text")
    assert not ({"INT-REQ-003", "ES-SRC-001"} & _codes(rc))
    text = 'The image "each one a closed fist" is a metaphor, since the bulbs are named as fists without "like" or "as".'
    assert _roles(text) == [("each one a closed fist", "quotation"), ("like", "mention"), ("as", "mention")]
    assert [inner for _s, _e, inner in cited_quotation_spans(text)] == ["each one a closed fist"]
    assert [(inner, role) for _s, _e, inner, role in uncited_quotation_spans(text)] == [("like", "mention"), ("as", "mention")]


# ------------------------------------------------------------------------------------------------------- controls

def _english(extra_sentence: str) -> dict:
    case = C.load_case("e2e-B6-en")
    case["id"] = "roles-control"
    case["answer"] = case["answer"].rstrip() + "\n\n" + extra_sentence
    case["translations"] = []
    return case


def test_an_invented_content_word_quoted_after_the_word_is_still_an_invented_quotation():
    case = _english('The poet chooses the word "glittering" for the soil, which makes the work feel rewarding.')
    assert "glittering" not in case["supplied_texts"][0]["text"]
    _case, rc = deliver(case, "text")
    assert "INT-REQ-003" in {f.code for f in rc.findings}
    assert [f for f in rc.structural_findings if f.code == "ES-SRC-001" and "'glittering'" in f.message]


def test_an_altered_quotation_is_still_named():
    case = _english('The poet calls the bulbs "each one a clenched fist", which suggests effort.')
    _case, rc = deliver(case, "text")
    assert [f for f in rc.findings if f.code == "INT-REQ-003" and "clenched" in f.message]
    _case, rc = deliver("e03_altered_quotation", "text")
    assert "INT-REQ-003" in _codes(rc)


def test_masking_still_covers_every_span_whatever_its_role():
    text = '"*Fue muy cansado*" → "*Fue muy agotador*", without "like" or "as".'
    masked = mask_quotations(text)
    for s, e, inner in find_quotation_spans(text):
        assert inner not in masked and set(masked[s:e]) <= {"x", " "}


@pytest.mark.parametrize("text, expected", [
    ('The poet writes "the night was cold".', [("the night was cold", "quotation")]),                     # an attribution keeps a quotation
    ('The "rose" becomes a "canker" in the second stanza.', [("rose", "quotation"), ("canker", "quotation")]),  # "becomes" is no correction frame
    ('The speaker departs without "a backward glance at the burning town".', [("a backward glance at the burning town", "quotation")]),
    ('Model: Her unease shows when she "rehearsed three different first sentences".', [("rehearsed three different first sentences", "quotation")]),
    ('In the last line the speaker goes on to add "the night was cold".', [("the night was cold", "quotation")]),
    ('The verb "smashed" is stronger than "hit".', [("smashed", "quotation"), ("hit", "quotation")]),
    ('**Model:** "Os recomiendo que participéis."', [("Os recomiendo que participéis.", "correction")]),
    ('The phrase "he trabajado" should be "trabajé" here.', [("he trabajado", "quotation"), ("trabajé", "correction")]),
    ('Change "era" to "estaba".', [("era", "quotation"), ("estaba", "correction")]),
    ('Try "sin embargo" to link the ideas.', [("sin embargo", "suggestion")]),
    ('The poem never uses "the first person plural".', [("the first person plural", "mention")]),
    ('It is a simile because of its "as".', [("as", "mention")]),
])
def test_only_closed_frames_change_a_role(text, expected):
    """Each row in a feedback task; a row with no correction or suggestion reads the same in an analysis task."""
    assert _roles(text, FEEDBACK) == expected
    if not {r for _i, r in expected} & {"correction", "suggestion"}:
        assert _roles(text, ANALYSIS) == expected


def test_emphasis_wrapped_inside_the_marks_is_markup_and_the_words_must_still_match():
    doc = {"d": SuppliedText(document_id="d", title=None, author=None, text="la coordinadora, una mujer muy simpático que se llama Rosa")}
    assert check_excerpt("*una mujer muy simpático*", "d", doc).located
    assert check_excerpt("**una mujer muy simpático**", "d", doc).status == "found"
    assert not check_excerpt("*una mujer muy simpática*", "d", doc).located      # a changed word is still not found
    assert unwrap_emphasis("***x y***") == "x y" and unwrap_emphasis("*x") == "*x" and unwrap_emphasis("a *b* c") == "a *b* c"


# ------------------------------------------------------------------------------------------- repair round 1 (ADV-07, A-FA-MENTION)

_PARAGRAPH = "Yesterday me and my freind went to the libary. There was alot of people their. We was very tired, however we stayed until it closed. And then we goes home."


def _feedback(answer: str) -> dict:
    """A marking-feedback case on the student's paragraph (supplied text), delivered as raw text."""
    return {
        "case_format": "argdiag-corpus/1", "id": "roles-feedback", "family": "evidence", "expected_label": "none", "acceptable_labels": [],
        "title": "roles-feedback", "subject": "English A: Language and Literature", "task_type": "marking_feedback",
        "agent_id": "english-a-lang-lit-specialist",
        "request": "Mark my paragraph and list my mistakes with the corrections. Quote my exact words.",
        "answer": answer,
        "supplied_texts": [{"document_id": "doc-essay", "title": "The student's paragraph (supplied text)", "author": "The student", "text": _PARAGRAPH}],
        "ids": {"task_id": "task-roles-feedback", "request_id": "req-roles-feedback", "report_id": "rep-1", "plan_id": "plan-roles-feedback"},
        "report_claims": [], "translations": [], "fidelity_review": "faithful",
    }


@pytest.mark.parametrize("text, expected", [
    # ADV-07: corrections and suggestions in other words
    ('1. "me and my freind" — write "my friend and I" instead of "me and my freind".',
     [("me and my freind", "quotation"), ("my friend and I", "suggestion"), ("me and my freind", "quotation")]),
    ('4. Not "We was" but "We were".', [("We was", "quotation"), ("We were", "correction")]),
    ('5. "we goes" is wrong: use "we went".', [("we goes", "quotation"), ("we went", "suggestion")]),
    ('Use the connective "however" only between two full clauses; the word "although" also works here.',
     [("however", "mention"), ("although", "mention")]),
    # A-FA-MENTION: the writer's word for a claim the text does not make
    ('It does not say that the plan has "failed".', [("failed", "mention")]),
    ('The source never calls it "a success".', [("a success", "mention")]),
])
def test_feedback_frames_give_the_writers_own_words_their_roles(text, expected):
    assert _roles(text, FEEDBACK) == expected


@pytest.mark.parametrize("text", [
    '**Model:** "Os recomiendo que participéis."', 'The phrase "he trabajado" should be "trabajé" here.', 'Change "era" to "estaba".',
    'Try "sin embargo" to link the ideas.', '4. Not "We was" but "We were".', '5. "we goes" is wrong: use "we went".',
    'The phrase → "the cold indifferent sea" personifies it.', 'Two agreement errors. Model: "Ella es muy simpática."',
])
def test_feedback_frames_are_quotations_in_an_analysis_task(text):
    """Repair round 4 (INV-Q1): outside a marking or feedback task no correction or suggestion frame takes a span out of the
    quotations, so an altered quotation written after an arrow, a "Model:" label, an imperative, 'Not "x" but "y"' or '"x"
    should be "y"' in a literary or source analysis is still checked; with no task known the same holds."""
    for task in (ANALYSIS, "source_analysis", "essay", None):
        assert {r for _i, r in _roles(text, task)} == {"quotation"}, (task, _roles(text, task))


@pytest.mark.parametrize("text, expected", [
    # a bare quoted connective may cite the text: it is still checked
    ('The unfinished "although" that ends the stanza shows a speaker who does not complete his argument.', [("although", "quotation")]),
    ('The evidence follows the order of the text, linked by "Also" and "When".', [("Also", "quotation"), ("When", "quotation")]),
    # a content word under "the word" is still a quotation; a reporting verb with a subject attributes
    ('The word "canker" suggests decay.', [("canker", "quotation")]),
    ('The narrator says "we went home".', [("we went home", "quotation")]),
    # a negated report confined to its clause: after the comma the quotation is the text's own and is checked
    ('The poem never mentions the war, so its "dates and figures" stand alone.', [("dates and figures", "quotation")]),
    # "not" with no "but" correction after it: both quotations are checked
    ('The text says "We was", not "We were".', [("We was", "quotation"), ("We were", "quotation")]),
])
def test_clean_controls_outside_the_frames_stay_quotations(text, expected):
    for task in (FEEDBACK, ANALYSIS):
        assert _roles(text, task) == expected


def test_feedback_in_other_words_raises_no_invented_quotation():
    answer = ("Your paragraph tells a clear sequence of events, but the grammar needs work.\n\n"
              '1. "me and my freind" — write "my friend and I" instead of "me and my freind".\n2. Replace "libary" with "library".\n'
              '3. "alot of people their" should be "a lot of people there".\n4. Not "We was" but "We were".\n5. "we goes" is wrong: use "we went".\n\n'
              'Avoid starting a sentence with "And", and use the connective "however" only between two full clauses; the word "although" also works here.')
    _case, rc = deliver(_feedback(answer), "text")
    errors = [f for f in [*rc.findings, *rc.structural_findings] if f.severity == "error" and f.code in ("INT-REQ-003", "ES-SRC-001", "CORE-SRC-001")]
    assert not errors, [(f.code, f.message) for f in errors]


def test_an_invented_quotation_of_the_student_is_still_named_in_feedback():
    """Control: the student's words misquoted ("me and my friends" is not in the paragraph) are still an altered quotation,
    whatever the feedback frames around the other spans."""
    answer = ('1. "me and my friends" — write "my friend and I" instead.\n'
              '2. Not "We was" but "We were".')
    _case, rc = deliver(_feedback(answer), "text")
    flagged = [f for f in [*rc.findings, *rc.structural_findings] if f.code in ("INT-REQ-003", "ES-SRC-001") and "me and my friends" in f.message]
    assert flagged
