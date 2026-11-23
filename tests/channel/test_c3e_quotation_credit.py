"""Push check of 2be42c48 (critical_open 3) and the c3d run's open channel items.

1. The af6dfe04 regression, the rest of it: ``own_text._OWN_TEXT_CREDIT_BEFORE_RE`` read any first-person possessive before a quotation
   as credit to the answer's own text ('Se nos pide', where 'nos' was taken for the French possessive; 'Our teacher wrote'; 'Mi
   profesora escribió:'), and any part of a piece of writing ('The heading reads') as a part of the answer's own. On c2/sp-t15 with
   the task's 'instituto' changed to 'colegio', each of these frames lost its INT-REQ-003 error when the answer also wrote the altered
   wording in its own voice, before or after the quotation. Now wording attributed to the task, to whoever sets or marks it (a
   teacher, an examiner), to the request by its verb ('Se nos pide', 'We were asked', 'On nous demande') or to a part that may be the
   task's ('The heading reads', 'La primera línea dice:') is checked against the task in every frame and language; only the answer's
   own voice credits its own text: a first-person possessive before a kind or a part of a piece of writing ('my closing line', 'mi
   artículo'), a first-person verb of writing or saying ('As I wrote above'), a kind of the answer's own writing ('The article opens
   with'), or a part with no verb of a text's saying ('The second sentence, "..."'). The af6dfe04 behaviour for the answer's own
   corrections stays (``test_c3c_own_correction.py``, ``test_c3d_quotation_frames.py``).
2. The c3d leftovers in the channel's paths:
   * '- Mal: "El primer semana fue difícil". Bien: "La primera semana fue difícil"' on sp-t16 charged the correction INT-REQ-003 at
     error: the markdown correction readers read only the English 'Right:' and 'Correct:' labels. They now read the one class of
     correction labels the one reader of the writer's own words reads (``markdown.CORRECTION_RIGHT_LABELS``), alone at the start of a
     sentence or after the wording they replace, an arrow between or not;
   * 'Before: "x". After: "y".' on the English branch (ll-t16) charged both spans INT-REQ-003 and ES-SRC-001: the parser cut the pair
     into two sentences, so the one reader never saw it. The parser now reads a sentence with its neighbour when the two hold one
     labelled correction pair across their boundary;
   * 'As I said above, "..."' on the English branch was credited to the text under analysis before the own-text reading ran. A
     quotation credited to the answer's own text in its own voice, which the answer's own words hold word for word and no supplied text
     holds all but one or two words of, is now credited to no text, so the channel's own-wording reading decides it.
   In every case a misquotation of a supplied text or of the task stays charged (INV-Q1).
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import own_text as ot
from epinoic_logic.adapters.english_specialist.parser import parse_response
from epinoic_logic.translate.contracts import SuppliedText

from ..branches import d9d10_hub as H
from ..branches import d9d10_texts as T
from .test_c3c_own_correction import BETTER, _charged

# ------------------------------------------------------------------------- 1. a misquotation of the task, credited in any frame
#: (altered task wording, the task's own wording)
ALTERED = {
    "colegio": ("Escribe un artículo de opinión para la revista digital de tu colegio",
                "Escribe un artículo de opinión para la revista digital de tu instituto"),
    "invierno": ("Tu ciudad recibe cada invierno miles de turistas", "Tu ciudad recibe cada verano miles de turistas"),
}
FRAMES = [
    # the four frames of critical_open 3
    'Se nos pide lo siguiente: "%s".',
    'Our teacher wrote "%s".',
    'Mi profesora escribió: "%s".',
    'The heading reads "%s".',
    # the same classes: a part that may be the task's, read by a verb of a text's saying; a word that only points back
    'The opening line reads "%s".',
    'La primera línea dice: "%s".',
    'The title reads "%s".',
    'Como se indica arriba: "%s".',
    # the request by its verb, active, passive or impersonal, in each language
    'Nos piden: "%s".',
    'Se te pide: "%s".',
    'We were asked: "%s".',
    'Le professeur demande : "%s".',
    # whoever sets or marks the task
    'El profesor nos pidió: «%s».',
    'Our examiner set this: "%s".',
]
FRAME_IDS = ["es-se-nos-pide", "en-our-teacher", "es-mi-profesora", "en-heading-reads", "en-opening-line-reads", "es-primera-linea-dice",
             "en-title-reads", "es-como-se-indica-arriba", "es-nos-piden", "es-se-te-pide", "en-we-were-asked", "fr-professeur-demande",
             "es-profesor-nos-pidio", "en-our-examiner"]


def _lb(extra: str) -> list[tuple[str, str]]:
    rc = H.recorded("c2/sp-t15", T.SP_T15 + "\n\n" + extra)
    assert not [f for f in rc.findings if f.code == "INT-INTERNAL-001"], [f.message for f in rc.findings]
    return [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code]


@pytest.mark.parametrize("which", sorted(ALTERED))
@pytest.mark.parametrize("frame", FRAMES, ids=FRAME_IDS)
def test_a_misquotation_of_the_task_is_charged_in_every_frame_alone_and_with_the_own_wording(frame, which):
    alt, exact = ALTERED[which]
    assert exact.casefold() in T.SP_T15_Q.casefold() and alt.casefold() not in T.SP_T15_Q.casefold()
    assert _lb(frame % alt) == [("INT-REQ-003", "error")]
    # the answer also writes the altered wording in its own voice, before the quotation and after it
    assert _lb(alt + ". " + frame % alt) == [("INT-REQ-003", "error")]
    assert _lb(frame % alt + "\n\n" + alt + ".") == [("INT-REQ-003", "error")]


@pytest.mark.parametrize("frame", FRAMES, ids=FRAME_IDS)
def test_the_task_quoted_exactly_is_no_finding_in_these_frames(frame):
    for _alt, exact in ALTERED.values():
        assert _lb(frame % exact) == [], frame


@pytest.mark.parametrize("sentence, expected", [
    # the answer's own voice credits its own text
    ('In my closing line, "x"', True),
    ('My heading: "x"', True),
    ('My opening line reads "x"', True),
    ('The heading of my article reads "x"', True),
    ('Mon article commence par "x"', True),
    ('As I wrote above, "x"', True),
    ('As I said above, "x"', True),
    ('The article opens with "x"', True),
    ('The model opens with "x"', True),
    ('The second sentence, "x"', True),
    # a possessive before anything but a piece of writing, the request by its verb, whoever sets the task: never the answer's own
    ('Se nos pide lo siguiente: "x"', False),
    ('Our teacher wrote "x"', False),
    ('Mi profesora escribió: "x"', False),
    ('My teacher says "x"', False),
    ('Nuestra profesora escribió: "x"', False),
    ('Nos piden: "x"', False),
    ('We were asked: "x"', False),
    ('On nous demande : "x"', False),
    ('Le professeur écrit : "x"', False),
    ('The examiner wrote "x"', False),
    # a part alone, read by a verb of a text's saying, may be the task's
    ('The heading reads "x"', False),
    ('The opening line reads "x"', False),
    ('La primera línea dice: "x"', False),
    ('The title says "x"', False),
    # a word that only points back credits nothing by itself
    ('Como se indica arriba: "x"', False),
    ('As shown above, "x"', False),
], ids=lambda v: v if isinstance(v, str) else None)
def test_only_the_answers_own_voice_credits_a_quotation_to_its_own_text(sentence, expected):
    assert ot.credits_own_text(sentence, sentence.index('"')) is expected


def test_the_answers_own_wording_credited_in_its_own_voice_is_still_no_finding():
    """The c3d pins hold: an exact quotation of the answer's own model text credited in its own voice draws nothing."""
    assert _lb('As I wrote above, "Cada verano, nuestra ciudad se llena de turistas".') == []
    assert _lb('The article opens with "Cada verano, nuestra ciudad se llena de turistas".') == []


# ----------------------------------------------------------------- 2a. the correction labels of the markdown readers (sp-t16)
SP16_LINE = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana'


def _sp16(line: str) -> list[tuple[str, str]]:
    assert SP16_LINE in T.SP_T16
    rc = H.recorded("c3/sp-t16", T.SP_T16.replace(SP16_LINE, line))
    return [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code]


PAIRS = [
    ('Mal', 'Bien'), ('Incorrecto', 'Correcto'), ('Error', 'Mejor'), ('Antes', 'Después'), ('Before', 'After'), ('Faux ', 'Juste '),
    ('Mal', 'Forma correcta'), ('Wrong', 'Right'),
]


@pytest.mark.parametrize("replaced, correction", PAIRS, ids=[f"{a.strip()}-{b.strip()}" for a, b in PAIRS])
@pytest.mark.parametrize("gap", ['. ', ' ', ' → '], ids=["stop", "blank", "arrow"])
def test_a_labelled_correction_pair_on_the_language_b_marking_answer_is_no_quotation_finding(replaced, correction, gap):
    line = f'- {replaced}: "El primer semana fue difícil"{gap}{correction}: "La primera semana fue difícil" (semana'
    assert _sp16(line) == []


@pytest.mark.parametrize("replaced, correction", PAIRS[:4], ids=[f"{a}-{b}" for a, b in PAIRS[:4]])
def test_a_misquotation_of_the_students_email_under_a_replaced_label_is_still_charged(replaced, correction):
    """The student's email says 'El primer semana fue difícil'; 'La primer ...' misquotes it (INV-Q1)."""
    line = f'- {replaced}: "La primer semana fue difícil". {correction}: "La primera semana fue difícil" (semana'
    assert ("INT-REQ-003", "error") in _sp16(line)


@pytest.mark.parametrize("text, roles", [
    ('Mal: "x y". Bien: "z w".', ["quotation", "correction"]),
    ('Bien: "z w".', ["correction"]),
    ('Correcto (registro formal): "z w".', ["correction"]),
    ('"x y" → Bien: "z w".', ["quotation", "correction"]),
    ('"x y". Mejor: "z w".', ["quotation", "correction"]),
    ('Antes: "x y". Después: "z w".', ["quotation", "correction"]),
    ('Before: "x y". After: "z w".', ["quotation", "correction"]),
    ('Faux : "x y". Juste : "z w".', ["quotation", "correction"]),
    # a longer head is no label; a span the sentence credits to a text stays a quotation
    ('Bien, pero cuidado con esto: "z w".', ["quotation"]),
    ('Your email says "x y". Bien: "z w".', ["quotation", "correction"]),
    ('Your email says: "z w".', ["quotation"]),
], ids=["mal-bien", "bien-alone", "correcto-bracket", "arrow-bien", "mejor-after-span", "antes-despues", "before-after", "faux-juste",
        "longer-head", "email-then-bien", "email"])
def test_the_markdown_role_reader_reads_the_one_class_of_correction_labels_in_a_feedback_task(text, roles):
    spans = md.find_quotation_spans(text)
    assert md._span_roles(text, spans, feedback=True) == roles
    # outside a feedback task every span stays a quotation
    assert md._span_roles(text, spans, feedback=False) == ["quotation"] * len(spans)


@pytest.mark.parametrize("mark", [". Bien:", " → Bien:", " -> Correct:", " => Mejor :", ". Versión   corregida :", " ⟶ Après :",
                                  " --> corrected sentence :"])
@pytest.mark.parametrize("pad", ["", " *_ "])
def test_the_arrow_before_a_label_is_read_from_the_tail_of_the_window_as_from_the_whole(mark, pad):
    """c3e adds an arrow before a correction label; the tail search (``_CORRECTION_TAIL``) still equals the whole-window search."""
    for q in ('"', "'", "”", "’", "»"):
        before = ("x" * 120 + q + pad + mark + pad)[-ot._OWN_TEXT_BEFORE:]
        whole = ot._CORRECTION_BEFORE_RE.search(before)
        tail = ot._CORRECTION_BEFORE_RE.search(before, max(0, len(before) - ot._CORRECTION_TAIL))
        assert bool(whole) is bool(tail) is True, (before, whole, tail)
        assert len(whole.group(0)) <= 50


@pytest.mark.parametrize("sentence, pairs", [
    ('"x y" → Bien: "z w".', [(0, 1)]),
    ('Mal: "x y" -> Correct: "z w".', [(0, 1)]),
    ('Before: "x y". After: "z w".', [(0, 1)]),
], ids=["arrow-bien", "arrow-correct", "before-after"])
def test_the_one_reader_names_a_pair_with_an_arrow_before_the_label(sentence, pairs):
    spans = md.find_quotation_spans(sentence)
    assert ot.correction_pairs(sentence, spans) == pairs
    assert ot.own_text_kinds(sentence, spans)[1] == ot.OWN_FRAME


# ---------------------------------------------------------------------------- 2b. a before-and-after pair on the English branch
@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra", [
    f'Before: "the adverts are about money". After: "{BETTER}".',
    f'Original: "the adverts are about money". Revised: "{BETTER}".',
    f'Before: "the adverts are about money".\nAfter: "{BETTER}".',
    f'Weak: "the adverts are about money". Stronger: "{BETTER}".',
], ids=["before-after", "original-revised", "before-after-lines", "weak-stronger"])
def test_a_before_and_after_pair_draws_no_quotation_finding_on_the_english_branch(extra, task_type):
    assert _charged(extra, task_type) == {}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_a_misquotation_of_the_notes_under_a_before_label_is_still_charged(task_type):
    """INV-Q1: the notes hold 'A grandmother cooks for a huge family.'; one word changed under 'Before:' stays a quotation."""
    charged = _charged('Before: "A grandmother cooks for a tiny family". After: "A grandmother cooks for a huge family".', task_type)
    assert charged == {'"A grandmother cooks for a tiny family"': [("INT-REQ-003", "error"), ("ES-SRC-001", "error")]}, charged


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_a_neutral_label_alone_marks_nothing_on_the_english_branch(task_type):
    assert _charged('Before: "the adverts are about money".', task_type) == {
        '"the adverts are about money"': [("INT-REQ-003", "error"), ("ES-SRC-001", "error")]}


# ---------------------------------------------------------------------- 2c. 'As I said above, "..."' on the English branch
OWN = "Put simply, the adverts sell saving as a family duty."


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra", [
    OWN + ' As I said above, "the adverts sell saving as a family duty".',
    OWN + '\n\nAs I wrote earlier, "the adverts sell saving as a family duty".',
    OWN + ' In my closing line, "the adverts sell saving as a family duty".',
], ids=["as-i-said-above", "as-i-wrote-earlier", "my-closing-line"])
def test_the_answers_own_wording_quoted_in_its_own_voice_is_no_finding_on_the_english_branch(extra, task_type):
    assert _charged(extra, task_type) == {}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra, quoted", [
    # altered: the answer's own words do not hold it
    (OWN + ' As I said above, "the adverts sell spending as a family duty".', '"the adverts sell spending as a family duty"'),
    # the answer never wrote it in its own voice
    ('As I said above, "the adverts sell saving as a family duty".', '"the adverts sell saving as a family duty"'),
    # a misquotation of the notes, written in the answer's own voice as well (INV-Q1)
    ('A grandmother cooks for a tiny family. As I said above, "A grandmother cooks for a tiny family".', '"A grandmother cooks for a tiny family"'),
], ids=["altered", "never-written", "misquotes-the-notes"])
def test_an_own_voice_frame_never_excuses_a_quotation_the_own_text_does_not_hold(extra, quoted, task_type):
    assert _charged(extra, task_type) == {quoted: [("INT-REQ-003", "error"), ("ES-SRC-001", "error")]}


def test_the_pair_reading_of_the_english_parser_is_linear_in_the_quotations():
    """Each sentence is read once with each neighbour, however many quotations it holds (``parser._quotation_credit``)."""
    notes = SuppliedText(document_id="notes", title=None, author="student", text="A grandmother cooks for a huge family.")
    para = " ".join(f'Before: "word{i} one two". After: "word{i} three four".' for i in range(150))
    one = 'The notes list ' + ", ".join(f'"w{i} a b"' for i in range(1500)) + "."
    t = time.perf_counter()
    for text in (para, one):
        parse_response("Thesis sentence here.\n\n" + text, request_id="r", task_id="t", report_id="p", task_type="hl_essay",
                       supplied_texts=[notes])
    assert time.perf_counter() - t < 60.0
