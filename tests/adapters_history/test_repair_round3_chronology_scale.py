"""Repair round 3, ADV3-10: the chronology cue reader is linear in the length of its sentence.

Every cue of a sentence used to read the whole text before and after it (its date tokens, its clause breaks, the noun phrase
of each side), so a run-on answer of thousands of cues and no sentence end was read in quadratic time: a 300 KB answer held
the channel about 270 s. Each cue now reads a window of its sentence (``_CUE_WINDOW`` characters on either side, cut back to
a word boundary); a sentence of prose lies inside the window whole and is read exactly as before. The bound is checked by
counting the characters the reader tokenises, not by a clock."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist import chronology as C

SOUP_UNIT = "so because therefore all every caused after compared with control 'quote' \"q\" (x) [y] {z} — … "


def _scanned(monkeypatch, text: str) -> int:
    """The characters the date tokeniser reads while the relations of ``text`` (its own paragraph) are extracted."""
    total = [0]
    real = C._tokens

    def counting(t):
        total[0] += len(t)
        return real(t)

    monkeypatch.setattr(C, "_tokens", counting)
    C._chronology_relations_cached.cache_clear()
    C._paragraph_sentences.cache_clear()
    C.chronology_relations(text, text)
    monkeypatch.setattr(C, "_tokens", real)
    return total[0]


def test_the_cue_reader_reads_a_run_on_text_in_linear_time(monkeypatch):
    small = (SOUP_UNIT * 400)[:20_000]
    large = (SOUP_UNIT * 1600)[:80_000]
    s, l = _scanned(monkeypatch, small), _scanned(monkeypatch, large)
    assert s > 0
    # four times the text, about four times the reading (quadratic reading would be sixteen times)
    assert l <= 5 * s, (s, l)


def test_each_cue_reads_a_bounded_window_cut_at_word_boundaries():
    text = "word " * 5000 + "after" + " word" * 5000
    start = text.index("after")
    lo, hi = C._cue_window(text, start, start + len("after"))
    assert hi - lo <= 2 * C._CUE_WINDOW + len("after")
    assert text[lo - 1] == " " and text[hi] == " "          # no word is cut
    short = "The Treaty of Versailles of 1919 came after the armistice of 1918."
    assert C._cue_window(short, short.index("after"), short.index("after") + 5) == (0, len(short))


@pytest.mark.parametrize("sentence, later, earlier", [
    ("The Treaty of Versailles of 1919 came after the armistice of 1918.", "1919", "1918"),
    ("The election of 1933 came before the crash of 1929.", "1929", "1933"),   # the stated order, decided (and false)
])
def test_a_prose_sentence_is_read_as_before(sentence, later, earlier):
    rel = [r for r in C.chronology_relations(sentence) if r.decided]
    assert [(r.later_text, r.earlier_text) for r in rel] == [(later, earlier)]


def test_an_order_deep_inside_a_long_run_on_text_is_still_read():
    pad = "and the people waited and talked and argued " * 200
    rel = [r for r in C.chronology_relations(pad + "the election of 1933 came before the crash of 1929 " + pad) if r.decided]
    assert [(r.later_text, r.earlier_text, r.later > r.earlier) for r in rel] == [("1929", "1933", False)]
