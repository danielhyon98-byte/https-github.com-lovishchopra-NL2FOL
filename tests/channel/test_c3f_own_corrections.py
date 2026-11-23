"""Push check of a9129c78 (the critical-fixes lens, the challenger and the readings lens) and the c3e run's open channel items. Expected
values are fixed here; each item is pinned with its faulty twin.

1. The correction frames in every language the channel reads: on c3/sp-t16 (a marking task) 'Escribe "La primera semana fue difícil"
   en vez de "El primer semana fue difícil".' charged the corrected span INT-REQ-003 at error while the English 'instead of' form was
   free. ``markdown.INSTEAD_OF_WORDS`` ('instead of', 'rather than', 'en vez de', 'en lugar de', 'au lieu de', 'plutôt que', 'à la place
   de') is now one class for the role reader and the one reader of the writer's own words.
2. The halves of an own correction read by ROLE (``own_text.correction_reading``, ll-t16): the replaced half of a correction that
   restores a supplied text's exact wording is the writer's own example of the misquotation and free ('Wrong: "Not every kitchen has a
   home." Right: "Not every kitchen has a door."'), while a corrected half that presents a supplied text's wording altered is checked
   as a quotation of that text ('Mal: "Made with love." Bien: "Made with care. Finished with care."'), in an essay and a feedback task.
3. The c3e leftovers: the own-correction frames 'Draft:/Final:', 'Change X to Y', 'Replace X with Y', 'Instead of X, write Y', 'Rewrite X
   as Y', 'Your sentence X could become Y', 'You wrote X; a stronger version is Y', '- Weak/- Strong', 'Not X but Y' (the imperative and
   lead frames in any task, as the existing labels; 'becomes' and 'not ... but' in a feedback task only, since in an analysis they
   describe the text); a blockquote line that alters the task; a quotation under a correction's label ALONE ('Bien: "..."' with no
   wording it replaces in view) that alters the task.
4. The readings lens's minor over-flag: INT-LEDGER-029 read the IA criterion sentence of r7 ch-t13 ('Conclusion rewards an answer ...
   that is compared with accepted science with sources cited.') as a verification label.

In every case a misquotation of a supplied text or of the task stays charged (INV-Q1).
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import own_text as ot
from epinoic_logic.integrity import ledger

from ..branches import d9d10_hub as H
from ..branches import d9d10_texts as T
from .c3_core_support import _deliver
from .test_c3c_own_correction import BETTER, LL

VAGUE = "the adverts are about money"
#: The error-level codes a quotation can draw on the English branch: the channel's, the English pack's and the core pack's.
QUOTE_ERRORS = ("INT-REQ-003", "ES-SRC-001", "CORE-SRC-003", "CORE-SRC-006", "INT-SUBJ-003")


def _ll(extra: str, task_type: str) -> dict[str, list[str]]:
    """The quotation findings at error on the claims of ll-t16 with ``extra`` appended, by claim text (sorted codes)."""
    item = dict(LL)
    item["task_type"] = task_type
    hub, _ch, reply, rc = _deliver(item, None, LL["response_text"] + "\n\n" + extra)
    hub.close()
    texts = {c["claim_id"]: c["claim_text"] for c in reply.payload["claims"]}
    out: dict[str, list[str]] = {}
    for f in [*rc.findings, *rc.structural_findings]:
        assert f.code != "INT-INTERNAL-001", f.message
        if f.code in QUOTE_ERRORS and f.severity == "error":
            for cid in f.claim_ids or ["-"]:
                out.setdefault(texts.get(cid, cid), []).append(f.code)
    return {k: sorted(set(v)) for k, v in out.items()}


SP16_LINE = '- "El primer semana fue difícil" → "La primera semana fue difícil" (semana'


def _sp16(line: str = SP16_LINE, extra: str = "") -> list[tuple[str, str]]:
    assert SP16_LINE in T.SP_T16
    rc = H.recorded("c3/sp-t16", T.SP_T16.replace(SP16_LINE, line) + extra)
    assert not [f for f in rc.findings if f.code == "INT-INTERNAL-001"], [f.message for f in rc.findings]
    return [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code]


# ------------------------------------------------------------------------------------- 1. the correction frames in every language
@pytest.mark.parametrize("line", [
    '- Escribe "La primera semana fue difícil" en vez de "El primer semana fue difícil" (semana',
    '- Escribe "La primera semana fue difícil" en lugar de "El primer semana fue difícil" (semana',
    '- Écris "La primera semana fue difícil" au lieu de "El primer semana fue difícil" (semana',
    '- "La primera semana fue difícil" plutôt que "El primer semana fue difícil" (semana',
    '- Write "La primera semana fue difícil" instead of "El primer semana fue difícil" (semana',
    '- "La primera semana fue difícil" rather than "El primer semana fue difícil" (semana',
    '- En vez de «El primer semana fue difícil», escribe «La primera semana fue difícil» (semana',
    '- Escribiste «El primer semana fue difícil»; lo correcto es «La primera semana fue difícil» (semana',
    '- Cambia "El primer semana fue difícil" por "La primera semana fue difícil" (semana',
    '- No "El primer semana fue difícil" sino "La primera semana fue difícil" (semana',
], ids=["es-en-vez-de", "es-en-lugar-de", "fr-au-lieu-de", "fr-plutot-que", "en-instead-of", "en-rather-than", "es-en-vez-de-escribe",
        "es-lo-correcto-es", "es-cambia-por", "es-no-sino"])
def test_an_own_correction_in_any_language_on_the_marking_task_draws_no_quotation_finding(line):
    assert _sp16(line) == []


@pytest.mark.parametrize("line", [
    '- Escribe "La primera semana fue difícil" en vez de "La primer semana fue difícil" (semana',
    '- Écris "La primera semana fue difícil" au lieu de "La primer semana fue difícil" (semana',
    '- Escribiste «La primer semana fue difícil»; lo correcto es «La primera semana fue difícil» (semana',
], ids=["en-vez-de", "au-lieu-de", "lo-correcto-es"])
def test_a_misquotation_of_the_students_email_as_the_replaced_wording_is_still_charged(line):
    """The email says 'El primer semana fue difícil'; 'La primer ...' misquotes it (INV-Q1)."""
    assert ("INT-REQ-003", "error") in _sp16(line)


@pytest.mark.parametrize("text", ['Escribe "a b" en vez de "c d".', '"a b" en lugar de "c d".', 'Écris "a b" au lieu de "c d".',
                                  '"a b" plutôt que "c d".', '"a b" à la place de "c d".', '"a b" instead of "c d".'])
def test_the_one_class_of_instead_of_words_is_read_by_both_readers(text):
    spans = md.find_quotation_spans(text)
    assert md._span_roles(text, spans, feedback=True) == ["correction", "quotation"]
    assert md._span_roles(text, spans, feedback=False) == ["quotation", "quotation"]
    assert ot.own_text_kinds(text, spans) == [ot.OWN_FRAME, None]
    assert ot.correction_pairs(text, spans) == [(1, 0)]


# ---------------------------------------------------------------------------- 2. the halves of an own correction read by role
@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra", [
    'Wrong: "Not every kitchen has a home." Right: "Not every kitchen has a door."',
    'Mal: "Made with care." Bien: "Made with love. Finished with love."',
    'Your quotation "Not every kitchen has a home." -> "Not every kitchen has a door."',
], ids=["wrong-right", "mal-bien", "arrow"])
def test_a_correction_that_restores_the_sources_exact_wording_is_free(extra, task_type):
    assert _ll(extra, task_type) == {}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra, charged", [
    # the corrected half alters the advert's voiceover the notes quote ('Not every kitchen has a door.')
    ('Wrong: "Not every kitchen has a home." Right: "Not every kitchen has a room."', '"Not every kitchen has a room."'),
    # a fabricated corrected half of the slogan the notes quote ('Made with love. Finished with love.')
    ('Mal: "Made with love." Bien: "Made with care. Finished with care."', '"Made with care. Finished with care."'),
    # the replaced half is the advert's own words the notes quote: the corrected half presents the advert's wording, altered
    ('Before: "Every kitchen has a story." After: "Every kitchen has a secret."', '"Every kitchen has a secret."'),
], ids=["wrong-right-altered", "mal-bien-fabricated", "before-after-altered"])
def test_a_corrected_half_that_alters_the_sources_wording_is_charged(extra, charged, task_type):
    got = _ll(extra, task_type)
    assert charged in got and "INT-REQ-003" in got[charged] and "ES-SRC-001" in got[charged], got


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_the_replaced_half_of_a_correction_to_the_writers_own_wording_stays_charged_when_it_misquotes(task_type):
    """INV-Q1: the correction is not the source's wording, so the altered quotation of the notes stays one."""
    got = _ll(f'Wrong: "A grandmother cooks for a tiny family". Right: "{BETTER}".', task_type)
    assert "INT-REQ-003" in got.get('"A grandmother cooks for a tiny family"', []), got


@pytest.mark.parametrize("text, docs, expected", [
    ('Wrong: "a b c d e". Right: "a b c d f".', {"n": 'It says "a b c d f" there.'}, {0: ot.CORRECTION_FREE}),
    ('Wrong: "a b c d e". Right: "a b c x f".', {"n": 'It says "a b c d f" there.'}, {1: ot.CORRECTION_QUOTATION}),
    # the student's own wording corrected: the writer's correction, never a quotation
    ('Mal: "el gente es simpático". Bien: "la gente es simpática".', {"n": "Creo que el gente es simpático aquí."}, {}),
    # a neutral label disclaims nothing
    ('Before: "a b c d e". After: "a b c d f".', {"n": 'It says "a b c d f" there.'}, {}),
    # the writer's own wording, near no text
    (f'Wrong: "{VAGUE}". Right: "{BETTER}".', {"n": 'It says "a b c d f" there.'}, {}),
], ids=["free", "quotation", "student-wording", "neutral-label", "own-wording"])
def test_the_one_reader_reads_the_halves_by_role(text, docs, expected):
    assert ot.correction_reading(text, docs) == expected


# --------------------------------------------------------------------------------- 3a. the c3e own-correction frames on ll-t16
ANY_TASK_FRAMES = {
    "draft-final": f'Draft: "{VAGUE}". Final: "{BETTER}".',
    "change-to": f'Change "{VAGUE}" to "{BETTER}".',
    "replace-with": f'Replace "{VAGUE}" with "{BETTER}".',
    "instead-write": f'Instead of "{VAGUE}", write "{BETTER}".',
    "rewrite-as": f'Rewrite "{VAGUE}" as "{BETTER}".',
    "you-wrote": f'You wrote "{VAGUE}"; a stronger version is "{BETTER}".',
    "weak-strong": f'- Weak: "{VAGUE}"\n- Strong: "{BETTER}"',
}
FEEDBACK_FRAMES = {
    "could-become": f'Your sentence "{VAGUE}" could become "{BETTER}".',
    "not-but": f'Not "{VAGUE}" but "{BETTER}".',
}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("form", sorted(ANY_TASK_FRAMES))
def test_an_own_correction_frame_draws_no_quotation_finding_in_any_task(form, task_type):
    assert _ll(ANY_TASK_FRAMES[form], task_type) == {}


@pytest.mark.parametrize("form", sorted(FEEDBACK_FRAMES))
def test_a_feedback_only_frame_draws_no_quotation_finding_in_a_feedback_task(form):
    assert _ll(FEEDBACK_FRAMES[form], "marking_feedback") == {}


@pytest.mark.parametrize("form", sorted(FEEDBACK_FRAMES))
def test_a_feedback_only_frame_leaves_both_spans_quotations_in_an_essay(form):
    """In an analysis 'the "rose" becomes a "canker"' and 'not "angry" but "resigned"' describe the text: both spans are checked."""
    got = _ll(FEEDBACK_FRAMES[form], "hl_essay")
    assert f'"{VAGUE}"' in got and f'"{BETTER}"' in got, got


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("frame", [
    'Change "A grandmother cooks for a tiny family" to "{b}".',
    'Instead of "A grandmother cooks for a tiny family", write "{b}".',
    'You wrote "A grandmother cooks for a tiny family"; a stronger version is "{b}".',
], ids=["change-to", "instead-write", "you-wrote"])
def test_a_misquotation_of_the_notes_in_an_own_correction_frame_is_still_charged(frame, task_type):
    got = _ll(frame.format(b=BETTER), task_type)
    assert "INT-REQ-003" in got.get('"A grandmother cooks for a tiny family"', []), got


# ----------------------------------------------------------------------------------------------- 3b. a blockquote of the task
ALT = "Escribe un artículo de opinión para la revista digital de tu colegio"
EXACT = "Escribe un artículo de opinión para la revista digital de tu instituto"


def _sp15(extra: str) -> list[tuple[str, str]]:
    rc = H.recorded("c2/sp-t15", T.SP_T15 + "\n\n" + extra)
    assert not [f for f in rc.findings if f.code == "INT-INTERNAL-001"], [f.message for f in rc.findings]
    return [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code]


@pytest.mark.parametrize("extra", ["> " + ALT, ALT + ".\n\n> " + ALT, "> " + ALT + "\n\n" + ALT + ".", ">" + ALT, "> **" + ALT + "**",
                                   "> " + ALT[:30] + "\n> " + ALT[30:]],
                         ids=["alone", "own-wording-before", "own-wording-after", "no-space", "bold", "two-lines"])
def test_a_blockquote_that_alters_the_task_is_charged(extra):
    assert _sp15(extra) == [("INT-REQ-003", "error")]


@pytest.mark.parametrize("extra", ["> " + EXACT, "> Cada verano, nuestra ciudad se llena de turistas y de ruido."], ids=["exact", "own-words"])
def test_a_blockquote_of_the_exact_task_or_of_own_words_draws_nothing(extra):
    assert _sp15(extra) == []


# -------------------------------------------------------------------------------- 3c. a correction's label alone (design review)
TASK_ALT = "Escribe un correo electrónico a tu familia para darles las gracias"
TASK_EXACT = "Escribe un correo electrónico a la familia para darles las gracias"


@pytest.mark.parametrize("label", ["Bien", "Right", "After", "Juste ", "Correcto", "Después", "Mejor"])
def test_a_misquotation_of_the_task_under_a_correction_label_alone_is_charged(label):
    """The c3e design (kept): a correction's label alone makes its span a correction for the parsers, which read a sentence at a time.
    Read on the whole answer, a label with no wording it replaces in view corrects nothing: the task misquoted after it is charged."""
    assert _sp16(extra=f'\n\n{label}: "{TASK_ALT}".') == [("INT-REQ-003", "error")]
    assert _sp16(extra=f'\n\n{label}: "{TASK_EXACT}".') == []


@pytest.mark.parametrize("line", [
    '- Mal: "El primer semana fue difícil". Bien: "La primera semana fue difícil" (semana',
    '- Mal: "El primer semana fue difícil"\n- Bien: "La primera semana fue difícil" (semana',
    '- Antes: "El primer semana fue difícil"\n- Después: "La primera semana fue difícil" (semana',
], ids=["inline", "list-lines", "neutral-list-lines"])
def test_a_correction_label_with_its_replaced_half_in_view_stays_free(line):
    assert _sp16(line) == []


# ------------------------------------------------------------------------------------------- 4. a criterion sentence (ledger)
@pytest.mark.parametrize("sentence, read", [
    ("Conclusion rewards an answer to the research question that follows from the analysis and its uncertainties, and that is compared "
     "with accepted science with sources cited.", False),
    ("Criterion B requires a method that is checked against a second source.", False),
    ("The mark scheme credits an answer that verifies its result.", False),
    # about THIS answer, or a second clause: read as any other sentence
    ("Criterion E rewards this answer: everything was verified.", True),
    ("The rubric requires checking; all checks passed.", True),
    ("Evaluation rewards an answer that is checked, and this one was checked.", True),
    ("Conclusion: verified against the sources.", True),
])
def test_a_criterion_sentence_is_no_verification_label(sentence, read):
    assert bool(ledger._self_report_sentences(sentence)) is read


# ------------------------------------------------------------------------------------------------------------- linear readers
def test_the_new_readers_stay_linear():
    pairs = " ".join(f'Wrong: "w{i} a b c". Right: "w{i} a b d".' for i in range(400))
    docs = {"n": " ".join(f'"w{i} a b d"' for i in range(400))}
    t = time.perf_counter()
    reading = ot.correction_reading(pairs, docs)
    assert len(reading) == 400 and set(reading.values()) == {ot.CORRECTION_FREE}
    frames = " ".join(f'Change "x{i} y" to "z{i} w". Not "a{i}" but "b{i}".' for i in range(2000))
    with md.quotation_task("marking_feedback"):
        assert len(ot.correction_pairs(frames)) == 4000
    assert time.perf_counter() - t < 20.0


def test_the_lone_label_and_blockquote_readers_stay_linear():
    """The channel's two new readers read each span or block once; the answer's own voice is searched only for an altered quotation."""
    from types import SimpleNamespace

    from epinoic_logic.channel.bus import TranslatorChannel
    from epinoic_logic.translate.contracts import SuppliedText
    request = TASK_EXACT + ". " + EXACT + ". " + "Mi correo está abajo. " * 50
    docs = [SuppliedText(document_id="d", title=None, author="student", text="Querida familia: " * 50)]
    times = []
    for n in (1000, 4000):
        text = "\n".join(f'Bien: "{TASK_ALT} {i}".\n> {ALT} {i}\nfin.' for i in range(n))
        report = SimpleNamespace(original_response=text, claims=[], report_id="r", agent_id="a")
        t = time.perf_counter()
        lone = TranslatorChannel._lone_label_quotations(report, docs, request_text=request, task_type="marking_feedback")
        blocks = TranslatorChannel._blockquote_quotations(report, docs, request_text=request)
        times.append(time.perf_counter() - t)
        assert len(lone) == n and len(blocks) == 64  # every altered quotation named; at most 64 blocks read
    assert times[1] < 20.0 and times[1] < 8 * max(times[0], 0.05), times
