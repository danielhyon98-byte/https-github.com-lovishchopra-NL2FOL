"""Review round 8, parser-safety-3 (``adapters.markdown._split_note_clauses``): the terminal and bare-label scans once ran
as unanchored searches over the whole sentence, so a run of spaces or tabs in the middle of a sentence made them quadratic
(5,000 spaces took about a second and 20,000 about seventeen). The terminal is now found from the end, the bare-label scan
reads a bounded window, and every whitespace run is read as one space first: a sentence of 400,000 spaces is read at once,
and the readings of ordinary sentences are unchanged (pinned below as the previous reader gave them)."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters.markdown import _split_note_clauses


def _split(sentence: str):
    if hasattr(_split_note_clauses, "cache_clear"):
        _split_note_clauses.cache_clear()
    return _split_note_clauses(sentence)


@pytest.mark.parametrize("n", [100_000, 400_000])
def test_a_long_whitespace_run_is_read_in_linear_time(n):
    start = time.perf_counter()
    assert _split("It is 5 m; " + " " * n + "x.") == ("It is 5 m; x.", ())
    assert _split("It is 5 m (from memory) ;" + "\t " * n + "From memory, x.") == ("It is 5 m; From memory, x.", ("from memory",))
    assert time.perf_counter() - start < 2.0


@pytest.mark.parametrize("sentence, expected", [
    ("The rate is 5 m s-1 (from memory); the mass is 2 kg.", ("The rate is 5 m s-1; the mass is 2 kg.", ("from memory",))),
    ("It is 5 m;   x.", ("It is 5 m; x.", ())),
    ("From memory, the treaty was signed in 1648.", ("the treaty was signed in 1648.", ("From memory",))),
    ("The answer is 12 (checked) – see above.", ("The answer is 12 (checked) – see above.", ())),
    ("Note: this is from memory.", ("", ("Note: this is from memory.",))),
    ("The value  is\t5 m  (approx.)  .", ("The value is\t5 m (approx.).", ())),
    ("The battle was in 1415 — from memory — and it was won.", ("The battle was in 1415 — and it was won.", ("from memory",))),
    ("Confidence: high; the date is 1848.", ("", ("Confidence: high; the date is 1848.",))),
    ("The date is 1848; (I have checked this).", ("The date is 1848;.", ("I have checked this",))),
])
def test_ordinary_sentences_read_as_before(sentence, expected):
    assert _split(sentence) == expected
