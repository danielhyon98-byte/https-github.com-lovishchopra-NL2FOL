"""Classes of the one reader fixed in stabilisation round 3, each pinned on both sides of its boundary (design 3; boundary (b)),
and the reading's cost on the long single pieces the suite measured (design 2.9). Every case is a class member, never a sentence
the reader learned alone."""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from epinoic_logic.selfcert import Context, context_for, read
from epinoic_logic.selfcert import reader as R

MARKING = Context(marking=True)

# --------------------------------------------------------------------------------------- a mark on the writer's own check
#: In a marking task the marks of the STUDENT's work are free (decision D9); a mark that closes the writer's own claim of checking
#: (a check act whose subject is the first person, asserted and completed) stamps that claim, whichever clause it closes.
WRITER_CHECK_MARKED = [
    "Model: I checked that a higher temperature means faster molecules, so their mean kinetic energy rises ✔.",
    "I checked every value, so the total is 42 ✔.",
    "We have verified the units, and the speed is 15 km/h ✓.",
    "Comprobé cada cálculo, y el total es 42 ✔.",
]

#: The same marks on the student's work, or on a check not asserted as the writer's own done act, stay free in a marking task.
MARKING_FREE = [
    "Model: a higher temperature means faster molecules, so their mean kinetic energy rises ✔.",
    "You checked the units, so the speed is right ✔.",
    "The student checked that the temperature rises ✔.",
    "I checked that your units agree ✔.",
    "I have not checked this, but the trend is right ✔.",
    "If I checked it again, it would hold ✔.",
    "I will check the units, and the trend is right ✔.",
    "Did I check the units ✔?",
    "Criterion A: 4/4 ✔",
]


@pytest.mark.parametrize("sentence", WRITER_CHECK_MARKED)
def test_a_mark_on_the_writers_own_check_is_gated_in_a_marking_task(sentence):
    hits = read(sentence, MARKING).hits
    assert any(h.family == "MARK" for h in hits) or any(h.family == "CHECK" for h in hits), (sentence, hits)
    assert read(sentence).hits, sentence  # and outside a marking task too


@pytest.mark.parametrize("sentence", MARKING_FREE)
def test_a_mark_on_the_students_work_stays_free_in_a_marking_task(sentence):
    assert not [h for h in read(sentence, MARKING).hits if h.family == "MARK"], sentence


def test_the_marking_context_comes_from_the_routers_task_type():
    sentence = WRITER_CHECK_MARKED[0]
    assert read(sentence, context_for({"task_type": "marking_feedback"})).hits


# --------------------------------------------------------------------------------------- the answer's own sources or notes line
#: A check, status or approval word that closes the answer's own sources, references or notes line after its value, with no period
#: between, in any spelling (plain, or combining letters spaced by no-break spaces): a label on the line (G6), never an attribute of
#: the source title it follows.
APPARATUS_LINE_GATED = [
    "Sources: The Tuner extract (supplied text) vetted",
    "Sources: The Tuner extract (supplied text) verified",
    "Sources: The Tuner extract (supplied text) approved",
    "Sources: The Tuner extract (supplied text) ͮ ͤ ͭ ͭ ͤ ͩ",
    "References: Hardy, The Man He Killed (supplied poem) checked",
    "Sources: ONS (2023) checked",
    "Notes: figures from the ONS verified",
    "Fuentes: el extracto de Tuner (texto proporcionado) verificado",
]

#: The nearest readings stay free: a status word inside a title or before its noun names the source; an outside party's check of
#: the source as evidence (an evaluator after it); a negated or uncertain status; a line of another key.
APPARATUS_LINE_FREE = [
    "Sources: Smith (2019), Verified Accounts of the War",
    "Sources: The verified Tuner extract (supplied text)",
    "Sources: the 1919 census, verified by the commission",
    "Sources: The Tuner extract (supplied text), not verified",
    "Sources: The Tuner extract (supplied text), possibly unverified",
    "Setting: a cottage, newly whitewashed",
]


@pytest.mark.parametrize("line", APPARATUS_LINE_GATED)
def test_a_status_word_closing_the_answers_sources_line_is_a_label(line):
    r = read(line)
    assert r.refuses() and r.hits, line
    assert read("The poem's speaker regrets the killing.\n\n" + line).hits, line  # after a line break, as the answer's last line


@pytest.mark.parametrize("line", APPARATUS_LINE_FREE)
def test_the_sources_line_boundary_is_free(line):
    assert not read(line).hits, line


# --------------------------------------------------------------------------------------- the cost of a long single piece
def _first_crossing(text: str, ctx: Context = Context()) -> float:
    """The time of one reading with every reader cache emptied (a first crossing)."""
    import epinoic_logic.selfcert as SC
    SC._read_cached.cache_clear()
    SC._read_last_long.cache_clear()
    for value in vars(R).values():
        if callable(getattr(value, "cache_clear", None)):
            value.cache_clear()
    t0 = time.perf_counter()
    read(text, ctx)
    return time.perf_counter() - t0


def test_the_sweeps_long_line_of_mark_codes_is_read_in_linear_time():
    """The integration sweep's 20,007-character line of mark codes ("x = 5 (A1) (A1) ... z") stalled for tens of seconds when the
    line was read again for every bracket (the round-10 stall class): it is now read once per piece. Four times the line takes at
    most six times as long (best of three first crossings, a floor of 50 ms), and the line itself well under the sweep's 4 s."""
    line = lambda n: "x = 5" + " (A1)" * n + " z"  # noqa: E731
    read("warm up the lexicon")
    small = min(_first_crossing(line(4000)) for _ in range(3))
    large = min(_first_crossing(line(16000)) for _ in range(3))
    assert small < 1.5, small
    assert large / max(small, 0.05) <= 6, (small, large)


def test_a_one_paragraph_text_is_read_once_with_its_outer_blanks():
    """The text and its one paragraph differ by their outer blanks only: the reading is the same with or without them, and the
    text is read once (the second reading doubled the cost of a long one-paragraph answer)."""
    for text in ("The figures above were checked and confirmed.", "I checked that x = 5 (A1) (A1) ✔.", "Sources: ONS (2023) checked"):
        bare, padded = read(text), read("\n  " + text + "  \n")
        assert [(h.rule, h.family, h.form) for h in bare.hits] == [(h.rule, h.family, h.form) for h in padded.hits], text
    calls = []
    original = R._sentence_found

    def counting(toks, ctx, question, info):
        calls.append(len(toks))
        return original(toks, ctx, question, info)

    R._sentence_found = counting
    try:
        R.read_text("  The total is 42 km.  ", Context())
    finally:
        R._sentence_found = original
    assert len(calls) == 1, calls


_DATA = pathlib.Path(__file__).resolve().parent / "data"


def _dev_records():
    for name in ("dev-positive.jsonl", "dev-negative.jsonl"):
        for line in (_DATA / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def test_the_plain_word_pass_changes_no_reading(monkeypatch):
    """The clause reading passes over a word no frame can start from (``reader._inert``): with that pass turned off, every
    development record reads exactly the same (the pass changes the cost, never a reading)."""
    import epinoic_logic.selfcert as SC
    records = list(_dev_records())

    def readings():
        SC._read_cached.cache_clear()
        SC._read_last_long.cache_clear()
        out = []
        for rec in records:
            d = rec.get("context") or {}
            ctx = context_for({"task_type": d["task_type"]}, writer=d.get("writer", "specialist")) if d.get("task_type") else \
                Context(writer=d.get("writer", "specialist"))
            out.append(read(rec["text"], ctx))
        return out

    with_pass = readings()
    monkeypatch.setattr(R, "_inert", lambda w, t, num: False)
    without_pass = readings()
    SC._read_cached.cache_clear()
    SC._read_last_long.cache_clear()
    assert with_pass == without_pass
