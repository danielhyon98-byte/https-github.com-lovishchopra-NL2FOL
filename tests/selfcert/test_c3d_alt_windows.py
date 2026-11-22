"""The second readings of c3d read around what changed (repair of the c3d clearance).

A quotation mark that opens or closes no quotation is read as the stray mark it is ("... 1919 ’(sat)."), and a short bracket after
a closing quotation mark is read with that quotation's marks blanked ('He said “no” (sat).'). Each is a second reading of the text
with some marks blanked. Read whole, one stray mark in a long answer read the whole answer a second time: the parsers' sweep of
hostile inputs ran a sixth slower and its test passed its two-minute limit in the full suite. Each second reading now reads the
blanked marks' paragraphs only, at most a fixed window around each mark, and a window of blanks and ASCII punctuation alone not at
all. These tests pin both halves: what the second readings find (far into a long answer, in any paragraph) and how much they
read (deterministic: the lengths read, never a wall-clock time). Never weakened: an expected value here is never relaxed."""
from __future__ import annotations

import pytest

from epinoic_logic import selfcert as sc
from epinoic_logic.selfcert import reader as R

from ..timing import empty_caches

PROSE = "The delegates met again in the spring and the talks went on for many weeks. "


def _alt_reads(monkeypatch) -> list[int]:
    """The lengths of the texts the second readings read (recorded while they run)."""
    seen: list[int] = []
    orig = R._read_text_one

    def spy(text, ctx):
        import sys
        if sys._getframe(1).f_code.co_name == "_read_alt_windows":
            seen.append(len(text))
        return orig(text, ctx)
    monkeypatch.setattr(R, "_read_text_one", spy)
    return seen


@pytest.mark.parametrize("tail", [" ’(sat).", "’ [sat].", " ’ (signature valid)."])
def test_a_stray_mark_far_into_a_long_answer_still_uncovers_its_label(tail):
    text = PROSE * 120 + "The treaty was signed in 1919" + tail
    empty_caches()
    assert sc.read(text).refuses() is True
    assert sc.read(PROSE * 120 + "The treaty was signed in 1919.").refuses() is False  # (the control)


def test_a_stray_mark_in_a_later_paragraph_is_found_and_named_by_its_paragraph():
    text = PROSE * 3 + "\n\n" + PROSE * 2 + "\n\n" + PROSE + "The treaty was signed in 1919 ’(sat)."
    empty_caches()
    r = sc.read(text)
    assert r.refuses() is True
    at = text.index("(sat)")
    assert any(h.start <= at < h.end or at <= h.start < at + 6 for h in r.hits), r.hits
    assert all(not h.piece.startswith("paragraph") or h.piece.startswith("paragraph 3") for h in r.hits
               if h.start >= text.index("The treaty")), r.hits


def test_a_quoted_label_far_into_a_long_answer_is_still_read():
    text = PROSE * 120 + "Clemenceau said “never again” (sat)."
    empty_caches()
    assert sc.read(text).refuses() is True
    assert sc.read(PROSE * 120 + "Clemenceau said “never again”.").refuses() is False  # (the control)


def test_one_stray_mark_in_a_long_answer_is_read_again_in_a_window_only(monkeypatch):
    seen = _alt_reads(monkeypatch)
    text = 'The poem says "the bulbs lie under frost' + " (A1)" * 4000 + " z"
    empty_caches()
    sc.read(text)
    assert seen, "the stray mark was not read again"
    assert max(seen) <= 2 * R._ALT_WINDOW + 400 < len(text) // 4, seen


def test_a_run_of_stray_marks_with_no_word_is_not_read_again(monkeypatch):
    seen = _alt_reads(monkeypatch)
    text = "The value is 5 m. " + ")\"”’]»" * 3333 + "x"
    empty_caches()
    sc.read(text)
    # (the marks after the sentence are blanks and ASCII punctuation once blanked: only the ends next to a word are read again)
    assert sum(seen) <= 2 * (2 * R._ALT_MARGIN + 100), seen


def test_marks_in_separate_paragraphs_are_read_in_their_paragraphs(monkeypatch):
    seen = _alt_reads(monkeypatch)
    para = PROSE * 4
    text = para + "\n\n" + para + "A ’(sat)." + "\n\n" + para + "\n\n" + para + "B ’(sat)." + "\n\n" + para
    empty_caches()
    assert sc.read(text).refuses() is True
    assert len(seen) == 2 and all(n <= len(para) + 20 for n in seen), seen
