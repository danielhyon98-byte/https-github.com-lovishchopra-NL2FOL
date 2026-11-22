"""Push check of af6dfe04 (reason 5) and the c3c run's open own-text items, channel side.

1. REGRESSION of af6dfe04: the own-wording quotation rule (``own_text.quotes_own_wording``) set aside a misquotation of the task
   whenever the answer also wrote the altered wording in its own voice, unless the frame was an English 'you/your/the
   task|request|question|prompt|student|brief' frame. On c2/sp-t15 (Language B) with the task sentence altered to 'Tu ciudad recibe
   cada invierno miles de turistas', 'La consigna dice "..."', 'El enunciado pide: "..."', 'The instructions say "..."', 'The exam
   paper says "..."' and a bare quotation each gave INT-REQ-003 at 2ff70224 and nothing at af6dfe04. Now a quotation the request
   holds all but one or two words of is set aside as the answer's own wording only when its sentence credits it to the answer's own
   text ('The article opens with', 'The second sentence, "..."': ``own_text.credits_own_text``); a bare quotation, or one credited
   to the task in any frame and language, is checked against the task whatever the answer writes elsewhere. The answer's own
   corrections ('"x" -> "y"') keep the af6dfe04 behaviour (``test_c3c_own_correction.py``).
2. The c3c run's open items: an altered quotation of the answer's own model ('The article opens with "Cada año, nuestra ciudad
   ..."' where the model opens 'Cada verano, ...') is named (INT-REQ-003, "an altered quotation of the answer's own text"); an exact
   one stays free; and a labelled correction pair ('Wrong: "x". Right: "y"', 'Incorrect:/Correct:', 'Weak:/Stronger:', 'Mistake:/
   Correction:'), which a parser reads as two sentences, draws no quotation finding on either span, while a misquotation of a
   supplied text or of the request under such a label stays charged (INV-Q1).
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import own_text as ot

from ..branches import d9d10_hub as H
from ..branches import d9d10_texts as T
from .test_c3c_own_correction import BETTER, _charged

ALT = "Tu ciudad recibe cada invierno miles de turistas"  # the task says 'cada verano'


def _lb(extra: str, name: str = "c2/sp-t15", base: str = T.SP_T15) -> list[tuple[str, str]]:
    rc = H.recorded(name, base + "\n\n" + extra)
    assert not [f for f in rc.findings if f.code == "INT-INTERNAL-001"], [f.message for f in rc.findings]
    return [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code]


def _lb_messages(extra: str) -> list[str]:
    rc = H.recorded("c2/sp-t15", T.SP_T15 + "\n\n" + extra)
    return [f.message for f in rc.findings if f.code == "INT-REQ-003"]


# ----------------------------------------------------------------------------- 1. a misquotation of the task, in any frame
TASK_FRAMES = [
    # English
    'The task asks: "%s".',
    'Your task says "%s".',
    'The instructions say "%s".',
    'The exam paper says "%s".',
    'The prompt reads: "%s".',
    # Spanish
    'La consigna dice "%s".',
    'El enunciado pide: "%s".',
    'Según el enunciado, "%s".',
    'Como dice la tarea, "%s".',
    # French
    'Le sujet dit "%s".',
    # bare
    '"%s".',
]
TASK_FRAME_IDS = ["en-task-asks", "en-your-task", "en-instructions", "en-exam-paper", "en-prompt", "es-consigna", "es-enunciado-pide",
                  "es-segun-enunciado", "es-tarea", "fr-sujet", "bare"]


@pytest.mark.parametrize("frame", TASK_FRAMES, ids=TASK_FRAME_IDS)
def test_a_misquotation_of_the_task_is_charged_in_any_frame(frame):
    assert _lb(frame % ALT) == [("INT-REQ-003", "error")]


@pytest.mark.parametrize("frame", TASK_FRAMES, ids=TASK_FRAME_IDS)
def test_a_misquotation_of_the_task_is_charged_whatever_the_answer_writes_elsewhere(frame):
    """The af6dfe04 regression: the answer also writes the altered wording in its own voice, before or after the quotation."""
    assert _lb(ALT + ". " + frame % ALT) == [("INT-REQ-003", "error")]
    assert _lb(frame % ALT + "\n\n" + ALT + ".") == [("INT-REQ-003", "error")]


def test_the_message_names_the_task_and_the_altered_word():
    msgs = _lb_messages(ALT + ". " + 'La consigna dice "%s".' % ALT)
    assert len(msgs) == 1 and "the request holds all of its words but 'invierno' (an altered quotation)" in msgs[0], msgs


def test_the_task_quoted_exactly_is_no_finding_in_any_frame():
    exact = "Tu ciudad recibe cada verano miles de turistas"
    assert exact.casefold() in T.SP_T15_Q.casefold()
    for frame in TASK_FRAMES:
        assert _lb(frame % exact) == [], frame


# --------------------------------------------------------------- 2. the answer quoting its own text, exactly or altered
@pytest.mark.parametrize("extra", [
    'The article opens with "Cada verano, nuestra ciudad se llena de turistas".',
    'The model opens with "Cada verano, nuestra ciudad se llena de turistas".',
    'Mi artículo empieza con "Cada verano, nuestra ciudad se llena de turistas".',
    'As I wrote above, "Cada verano, nuestra ciudad se llena de turistas".',
], ids=["article-opens", "model-opens", "mi-articulo", "as-i-wrote-above"])
def test_an_exact_quotation_of_the_answers_own_text_is_no_finding(extra):
    assert _lb(extra) == []


@pytest.mark.parametrize("extra", [
    'The article opens with "Cada año, nuestra ciudad se llena de turistas".',
    'The model opens with "Cada año, nuestra ciudad se llena de turistas".',
    'Mi artículo empieza con "Cada año, nuestra ciudad se llena de turistas".',
], ids=["article-opens", "model-opens", "mi-articulo"])
def test_an_altered_quotation_of_the_answers_own_text_is_named(extra):
    assert _lb(extra) == [("INT-REQ-003", "error")]
    msgs = _lb_messages(extra)
    assert len(msgs) == 1 and ("its sentence credits it to the answer's own text, which holds all of its words but 'año' "
                               "(an altered quotation of the answer's own text)") in msgs[0], msgs


def test_the_answers_own_correction_is_still_not_charged_on_language_b():
    """The af6dfe04 behaviour for an own correction stays: its replaced wording is the answer's own text, not a quotation of the
    task, when the task does not hold half of it in a run."""
    assert _lb('"Cada verano, nuestra ciudad se llena" -> "Cada verano, nuestra ciudad se llena de turistas".') == []
    # with no text supplied, the correction's own words (a FRAME) and the wording it replaces are refuted only as altered
    # quotations of the task, and only when the task holds half of them in a run (c3d: both spans were charged before)
    assert _lb('"nuestra ciudad se llena de ruido" -> "nuestra ciudad se llena de turistas".') == []
    assert _lb('Wrong: "la ciudad es llena de gente". Right: "la ciudad está llena de gente".') == []


def test_an_own_correction_whose_replaced_wording_alters_the_task_is_still_charged_on_language_b():
    """The replaced wording misquotes the task sentence ('cada invierno' for 'cada verano') and the task holds half of it in a run."""
    assert _lb(f'"{ALT}" -> "Tu ciudad recibe cada verano miles de turistas".') == [("INT-REQ-003", "error")]
    assert _lb(f'Wrong: "{ALT}". Right: "Tu ciudad recibe cada verano miles de turistas".') == [("INT-REQ-003", "error")]


# ------------------------------------------------------------------------------ 3. a labelled correction pair
@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra", [
    f'Wrong: "the adverts are about money". Right: "{BETTER}".',
    f'- Wrong: "the adverts are about money"\n- Right: "{BETTER}"',
    f'Incorrect: "the adverts are about money". Correct: "{BETTER}".',
    f'Weak: "the adverts are about money". Stronger: "{BETTER}".',
    f'Mistake: "the adverts are about money". Correction: "{BETTER}".',
], ids=["wrong-right", "wrong-right-lines", "incorrect-correct", "weak-stronger", "mistake-correction"])
def test_a_labelled_correction_pair_draws_no_quotation_finding(extra, task_type):
    assert _charged(extra, task_type) == {}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_a_misquotation_of_a_supplied_text_under_a_wrong_label_is_still_charged(task_type):
    """INV-Q1: the notes hold 'A grandmother cooks for a huge family.'; one word changed under 'Wrong:' stays a quotation."""
    charged = _charged(f'Wrong: "A grandmother cooks for a tiny family". Right: "{BETTER}".', task_type)
    assert charged == {'"A grandmother cooks for a tiny family"': [("INT-REQ-003", "error"), ("ES-SRC-001", "error")]}, charged


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_the_replaced_wording_under_a_wrong_label_that_alters_the_request_is_still_charged(task_type):
    charged = _charged('Wrong: "choose a line of enquiry for me". Right: "choose one focus for me".', task_type)
    assert charged == {'"choose a line of enquiry for me"': [("INT-REQ-003", "error")]}, charged


SP16_LINE = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana'


@pytest.mark.parametrize("line", [
    '- Wrong: "El primer semana fue difícil". Right: "La primera semana fue difícil" (semana',
    '- Wrong: "El primer semana fue difícil" Right: "La primera semana fue difícil" (semana',
    '- Incorrect: "El primer semana fue difícil". Correct: "La primera semana fue difícil" (semana',
    '- "El primer semana fue difícil". Correct form: "La primera semana fue difícil" (semana',
], ids=["wrong-right", "wrong-right-no-stop", "incorrect-correct", "correct-form"])
def test_a_labelled_correction_on_the_language_b_marking_answer_is_no_quotation_finding(line):
    assert SP16_LINE in T.SP_T16
    rc = H.recorded("c3/sp-t16", T.SP_T16.replace(SP16_LINE, line))
    assert [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code] == []


def test_a_misquotation_of_the_students_email_under_a_wrong_label_is_still_charged():
    """The student's email says 'El primer semana fue difícil'; 'La primer ...' under 'Wrong:' misquotes it (INV-Q1)."""
    rc = H.recorded("c3/sp-t16", T.SP_T16.replace(SP16_LINE, '- Wrong: "La primer semana fue difícil". Right: "La primera semana fue difícil" (semana'))
    assert [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003"] == [("INT-REQ-003", "error")]


# ------------------------------------------------------------------------------------------------------------ the one reader
@pytest.mark.parametrize("sentence, expected", [
    ('The article opens with "x"', True),
    ('The second sentence, "x"', True),
    ('As I said above, "x"', True),
    ('Mi artículo empieza con "x"', True),
    ('In my closing line, "x"', True),
    ('"x"', False),
    ('The task asks: "x"', False),
    ('The instructions say "x"', False),
    ('The exam paper says "x"', False),
    ('La consigna dice "x"', False),
    ('El enunciado pide: "x"', False),
    ('Le sujet dit "x"', False),
    ('The first sentence of the task, "x"', False),
    ('Your article opens with "x"', False),
    ('The poem\'s first line, "x"', False),
], ids=["article", "second-sentence", "above", "mi-articulo", "my-line", "bare", "task", "instructions", "exam-paper", "consigna",
        "enunciado", "sujet", "sentence-of-the-task", "your-article", "poem-line"])
def test_the_one_reader_credits_a_quotation_to_the_answers_own_text_only_by_an_own_frame(sentence, expected):
    assert ot.credits_own_text(sentence, sentence.index('"')) is expected


@pytest.mark.parametrize("frame", ['The instructions say "%s".', 'La consigna dice "%s".', '"%s".'])
def test_the_one_reader_reads_the_task_s_words_as_own_wording_only_when_credited_to_the_answer(frame):
    answer = ALT + ".\n\n" + frame % ALT
    sentence = frame % ALT
    start = sentence.index('"')
    assert ot.quotes_own_wording(ot.unquoted_text(answer), sentence, start, ALT, credited=True) is False
    own = 'The article opens with "%s".' % ALT
    assert ot.quotes_own_wording(ot.unquoted_text(ALT + ".\n\n" + own), own, own.index('"'), ALT, credited=True) is True


@pytest.mark.parametrize("sentence, pairs", [
    ('Wrong: "x y". Right: "z w".', [(0, 1)]),
    ('- Mal: "x y". Bien: "z w".', [(0, 1)]),
    ('Incorrecto: "x y". Correcto: "z w".', [(0, 1)]),
    ('Faux : "x y". Juste : "z w".', [(0, 1)]),
    ('Before: "x y". After: "z w".', [(0, 1)]),
    ('Weak: "x y". Stronger: "z w".', [(0, 1)]),
    # the correction in the next sentence, outside the text read
    ('Wrong: "x y".', [(0, None)]),
    ('- Incorrect form: "x y".', [(0, None)]),
    ('Mal: "x y".', [(0, None)]),
    # a neutral label alone marks nothing; a span credited to a text is a quotation of it
    ('Before: "x y".', []),
    ('Original: "x y".', []),
    ('Your email says "I has went". Right: "I have gone".', []),
], ids=["wrong-right", "mal-bien", "incorrecto-correcto", "faux-juste", "before-after", "weak-stronger", "wrong-alone",
        "incorrect-form-alone", "mal-alone", "before-alone", "original-alone", "credited"])
def test_the_one_reader_names_a_labelled_correction_pair(sentence, pairs):
    spans = md.find_quotation_spans(sentence)
    kinds = ot.own_text_kinds(sentence, spans)
    assert ot.correction_pairs(sentence, spans) == pairs
    assert ot.correction_originals(sentence, spans) == [any(i == r for r, _c in pairs) for i in range(len(spans))]
    for replaced, correction in pairs:
        # the replaced wording keeps its kind (None) and stays out of the auditor's own spans; the correction is the writer's own
        assert kinds[replaced] is None
        assert correction is None or kinds[correction] == ot.OWN_FRAME


@pytest.mark.parametrize("mark", [". Bien:", "; corregida:", ". Versión   corregida :", ". Forma correcta:", ". Stronger:", ". After:", ". Après :",
                                  "; corrected sentence :"])
@pytest.mark.parametrize("pad", ["", " *_ "])
def test_the_new_correction_labels_are_read_from_the_tail_of_the_window_as_from_the_whole(mark, pad):
    """The tail search of ``own_text_kinds`` (``_CORRECTION_TAIL``) stays equal to the whole-window search with the c3d labels."""
    for q in ('"', "'", "”", "’", "»"):
        before = ("x" * 120 + q + pad + mark + pad)[-ot._OWN_TEXT_BEFORE:]
        whole = ot._CORRECTION_BEFORE_RE.search(before)
        tail = ot._CORRECTION_BEFORE_RE.search(before, max(0, len(before) - ot._CORRECTION_TAIL))
        assert bool(whole) is bool(tail) is True, (before, whole, tail)
        assert len(whole.group(0)) <= 44
