"""Follow-up c3g, the channel fixer: the push check of 08c4a36b and the c3f leftovers (channel, own-text and sources items). Expected
values are fixed here; each item is pinned with its twin.

1. Reason 7 of the push check (suspicious 2): ``TranslatorChannel._blockquote_quotations`` read only the first 64 blockquote blocks of
   at most 2,000 characters each, with no unread notice, so an altered task sentence drew INT-REQ-003 after 0 or 63 benign blocks and
   nothing after 64, and nothing inside one block of 2,321 characters. Every block is now read, and a block of more than one sentence
   is read whole and sentence by sentence (no bound, so nothing is left unread; the reading stays linear).
2. The c3f leftover on sp-t16 marking feedback: the role reader (``markdown._span_roles``) and the one reader of the writer's own words
   (``own_text``) read different correction frames, so either the channel charged a correct correction of the student's email
   INT-REQ-003 ('You wrote "x"; instead, write "y"', 'Tu as écrit « x » ; écris « y »') or the auditor named its corrected half
   OVS-FID-004 ('You wrote "x"; it should be "y"', '«x», pero debería ser «y»'). Both readers now read one class of frames.
3. The c3f leftover on ``sources.own_model_words`` (public API, read by the packs and the transfer auditor): it now consults the one
   reading of a correction's halves by role (``own_text.correction_reading``), so it agrees with the channel and the English parser on
   a correction's FREE and QUOTATION halves, in an essay and a feedback task. A ``task_type`` keyword lets a reader outside the
   channel read the frames in its task.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import own_text as ot
from epinoic_logic.adapters.sources import SuppliedText, own_model_words
from epinoic_logic.channel.bus import TranslatorChannel

from .test_c3f_own_corrections import ALT, EXACT, TASK_EXACT, _sp15, _sp16

# ------------------------------------------------------------------------------------------- 1. every blockquote block is read


@pytest.mark.parametrize("benign", [0, 63, 64, 200])
def test_an_altered_blockquote_after_any_number_of_benign_blocks_is_charged(benign):
    extra = "\n\n".join([f"> Nota {i}." for i in range(benign)] + ["> " + ALT])
    assert _sp15(extra) == [("INT-REQ-003", "error")]


@pytest.mark.parametrize("benign", [0, 64, 200])
def test_the_exact_task_after_any_number_of_benign_blocks_draws_nothing(benign):
    extra = "\n\n".join([f"> Nota {i}." for i in range(benign)] + ["> " + EXACT])
    assert _sp15(extra) == []


def test_an_altered_sentence_inside_one_long_block_is_charged():
    """The judge's probe: one block of more than 2,000 characters holding the altered task sentence."""
    block = "> " + " ".join(f"Nota número {i} del texto." for i in range(90)) + " " + ALT + "."
    assert len(block) > 2300
    assert _sp15(block) == [("INT-REQ-003", "error")]
    lines = "\n".join("> " + part + "." for part in block[2:].rstrip(".").split(". "))  # the same block over many '>' lines
    assert _sp15(lines) == [("INT-REQ-003", "error")]


def test_a_long_block_of_own_words_and_the_exact_task_draws_nothing():
    block = "> " + " ".join(f"Nota número {i} del texto." for i in range(90)) + " " + EXACT + "."
    assert _sp15(block) == []


def test_each_altered_sentence_of_a_block_is_named_once():
    """Two altered sentences of one block are named apart; the same altered sentence in another block is named once."""
    request = EXACT + ". " + TASK_EXACT + ". Mi correo está abajo."
    other = TASK_EXACT.replace("gracias", "noticias")
    text = "> " + ALT + ". " + other + ". Una nota mía.\n\n> " + ALT + "."
    report = SimpleNamespace(original_response=text, claims=[], report_id="r", agent_id="a")
    got = TranslatorChannel._blockquote_quotations(report, [], request_text=request)
    assert [f.code for f in got] == ["INT-REQ-003", "INT-REQ-003"]
    assert ["colegio" in f.message for f in got] == [True, False] and "'noticias'" in got[1].message


def test_the_blockquote_reader_stays_linear_with_no_bound():
    request = EXACT + ". " + "Mi correo está abajo. " * 50
    docs = [SuppliedText(document_id="d", title=None, author="student", text="Querida familia: " * 50)]
    times = []
    for n in (1000, 4000):
        blocks = "\n\n".join(f"> {ALT} {i}" for i in range(n))
        long_block = "> " + " ".join(f"Nota {i}." for i in range(n)) + " " + ALT + "."
        report = SimpleNamespace(original_response=blocks + "\n\n" + long_block, claims=[], report_id="r", agent_id="a")
        t = time.perf_counter()
        got = TranslatorChannel._blockquote_quotations(report, docs, request_text=request)
        times.append(time.perf_counter() - t)
        assert len(got) == n + 1  # every block and the altered sentence of the long block
    assert times[1] < 20.0 and times[1] < 8 * max(times[0], 0.05), times


# ----------------------------------------------------------------- 2. one class of correction frames for the two readers
X, Y = '"El primer semana fue difícil"', '"La primera semana fue difícil"'
GX, GY = "«El primer semana fue difícil»", "«La primera semana fue difícil»"
FEEDBACK_FRAMES = [
    "You wrote {x}; write {y} instead.", "You wrote {x}; it should be {y}.", "You wrote {x}; this should read {y}.",
    "You wrote {x}, but it should be {y}.", "You wrote {x}. It should be {y}.", "You wrote {x}; that should be {y}.",
    "You wrote {x} - it should be {y}.", "You wrote {x}: write {y}.", "You wrote {x}; instead, write {y}.", "You put {x}; it needs to be {y}.",
    "Escribiste {x}; debería ser {y}.", "Escribiste {x}; escribe {y}.", "Escribiste {x}; lo correcto es {y}.",
    "Escribiste {x}, pero debería ser {y}.", "Tu as écrit {x} ; il faut écrire {y}.", "Tu as écrit {x} ; écris {y}.",
    "{x}: it should be {y}.", "Your sentence {x} should read {y}.",
]


@pytest.mark.parametrize("marks", [(X, Y), (GX, GY)], ids=["straight", "guillemets"])
@pytest.mark.parametrize("frame", FEEDBACK_FRAMES)
def test_the_role_reader_and_the_one_reader_agree_on_a_feedback_correction(frame, marks):
    line = "- " + frame.format(x=marks[0], y=marks[1])
    with md.quotation_task("marking_feedback"):
        spans = md.find_quotation_spans(line)
        roles = md._span_roles(line, spans)
        kinds = ot.own_text_kinds(line, spans)
        pairs = ot.correction_pairs(line, spans)
    assert roles == ["quotation", roles[1]] and roles[1] in ("correction", "suggestion"), roles
    assert kinds == [None, ot.OWN_FRAME] and pairs == [(0, 1)], (kinds, pairs)


@pytest.mark.parametrize("frame", ["You wrote {x}; it should be {y}.", "{x}: it should be {y}.", "Escribiste {x}, pero debería ser {y}."])
def test_a_feedback_only_frame_pairs_nothing_in_an_essay(frame):
    """'should be' and 'debería ser' are read in a feedback task only, as before: in an analysis both spans stay quotations."""
    line = frame.format(x=X, y=Y)
    with md.quotation_task("hl_essay"):
        spans = md.find_quotation_spans(line)
        assert md._span_roles(line, spans) == ["quotation", "quotation"]
        assert ot.own_text_kinds(line, spans)[1] is None and ot.correction_pairs(line, spans) == []


SP16_TAIL = " (semana"


@pytest.mark.parametrize("frame", [
    "- You wrote {x}; instead, write {y}", "- Tu as écrit {x} ; écris {y}", "- You wrote {x}: write {y}",
    "- You wrote {x}; it should be {y}", "- Escribiste {x}, pero debería ser {y}", "- {x}: it should be {y}",
], ids=["instead-write", "fr-ecris", "colon-write", "it-should-be", "pero-deberia", "colon-should-be"])
def test_a_correction_of_the_students_email_draws_no_quotation_finding(frame):
    assert _sp16(frame.format(x=X, y=Y) + SP16_TAIL) == []


@pytest.mark.parametrize("frame", ["- You wrote {x}; instead, write {y}", "- You wrote {x}; it should be {y}", "- Tu as écrit {x} ; écris {y}"])
def test_a_misquotation_of_the_students_email_in_those_frames_is_still_charged(frame):
    """The email says 'El primer semana fue difícil'; 'La primer ...' misquotes it (INV-Q1)."""
    assert ("INT-REQ-003", "error") in _sp16(frame.format(x='"La primer semana fue difícil"', y=Y) + SP16_TAIL)


# --------------------------------------------------------------- 3. own_model_words consults the one reading of the halves
NOTES = SuppliedText(document_id="n", title=None, author=None,
                     text='The voiceover says "Not every kitchen has a door." Then "Made with love. Finished with love." closes it.')
RESTORES = 'Wrong: "Not every kitchen has a home." Right: "Not every kitchen has a door."'
ALTERS = 'Mal: "Made with love." Bien: "Made with care. Finished with care."'


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("sentence, excerpt, own", [
    # the replaced half of a correction that restores the notes' exact wording: CORRECTION_FREE, the writer's own (was False)
    (RESTORES, "Not every kitchen has a home.", True),
    ('Mal: "Made with care." Bien: "Made with love. Finished with love."', "Made with care.", True),
    # the corrected half that presents the notes' wording altered: CORRECTION_QUOTATION, a quotation (was True)
    (ALTERS, "Made with care. Finished with care.", False),
    # the exact wording and a neutral label keep their readings
    (RESTORES, "Not every kitchen has a door.", False),
    ('Before: "Not every kitchen has a home." After: "Not every kitchen has a door."', "Not every kitchen has a home.", False),
], ids=["restores-replaced", "restores-replaced-mal-bien", "alters-corrected", "exact-corrected", "neutral-label"])
def test_own_model_words_reads_a_corrections_halves_by_role(sentence, excerpt, own, task_type):
    with md.quotation_task(task_type):
        assert own_model_words(sentence, excerpt, {"n": NOTES}) is own
        reading = ot.correction_reading(sentence, {"n": NOTES.text})
    spans = md.find_quotation_spans(sentence)
    at = next(k for k, sp in enumerate(spans) if sp[2].strip() == excerpt)
    expected = {True: ot.CORRECTION_FREE, False: ot.CORRECTION_QUOTATION}
    if at in reading:
        assert reading[at] == expected[own]


def test_the_task_type_keyword_reads_a_feedback_frame_outside_the_channel():
    """The transfer auditor reads with no task in context: with ``task_type`` it reads a feedback-only frame as the channel does."""
    line = 'You wrote "El primer semana fue difícil"; it should be "La primera semana fue difícil".'
    assert [sp[2] for sp in ot.own_text_spans(line)] == []
    assert [sp[2] for sp in ot.own_text_spans(line, task_type="marking_feedback")] == ["La primera semana fue difícil"]
    assert [sp[2] for sp in ot.own_text_spans(line, task_type="hl_essay")] == []
    # the enclosing task (the channel's plan) is never widened by the keyword
    with md.quotation_task("hl_essay", authoritative=True):
        assert ot.own_text_spans(line, task_type="marking_feedback") == []
    assert ot.correction_reading(RESTORES, {"n": NOTES.text}, task_type="hl_essay") == {0: ot.CORRECTION_FREE}
    assert own_model_words(RESTORES, "Not every kitchen has a home.", {"n": NOTES}, task_type="marking_feedback") is True
