"""Two text readers made linear at integration, each reproducing its pattern exactly:

* ``adapters.markdown.strip_markup`` removes emphasis through ``stem.layout.emphasis_spans`` with the helper's markers
  (backtick included) instead of ``EMPHASIS_RE.sub``, which scans lazily to the end of the line from every opener that
  has no closer (parser-safety-5 remainder);
* the English parser's sentence boundaries are read by ``_boundaries`` in one pass instead of ``_BOUNDARY_RE.finditer``,
  which retries a run of end marks from every position of it (parser-safety-4, English parser).
"""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.adapters.english_specialist.parser import _BOUNDARY_RE, _boundaries
from epinoic_logic.adapters.markdown import EMPHASIS_RE, strip_markup

EMPHASIS_PIECES = ["*", "**", "_", "__", "`", "``", "a", "b", " ", "x1", ".", "\n", "é", "-"]
BOUNDARY_PIECES = [".", "!", "?", "...", "\"", "”", "’", ")", "]", "}", "»", " ", "\n", "A", "b", "7", "{\"", "[", "(", "“", "l. 4", "Dr."]


def test_emphasis_is_removed_exactly_as_the_pattern_removes_it():
    from epinoic_logic.adapters.markdown import _strip_emphasis
    rng = random.Random(23)
    for _ in range(30_000):
        s = "".join(rng.choice(EMPHASIS_PIECES) for _ in range(rng.randint(0, 16)))
        assert _strip_emphasis(s) == EMPHASIS_RE.sub(r"\2", s), repr(s)


@pytest.mark.parametrize("text, plain", [("The **storm** is *near*.", "The storm is near."), ("Use `x = 2` here.", "Use x = 2 here."),
                                         ("snake_case_name stays", "snake_case_name stays")])
def test_control_ordinary_emphasis(text, plain):
    assert strip_markup(text) == plain


def test_strip_markup_is_linear_on_unclosed_openers():
    t = time.perf_counter()
    strip_markup("`a " * 200_000)
    assert time.perf_counter() - t < 3.0


def test_sentence_boundaries_are_the_patterns_matches():
    rng = random.Random(29)
    for _ in range(30_000):
        s = "".join(rng.choice(BOUNDARY_PIECES) for _ in range(rng.randint(0, 14)))
        assert _boundaries(s) == [(m.start(), m.end()) for m in _BOUNDARY_RE.finditer(s)], repr(s)


@pytest.mark.parametrize("text", ["!" * 200_000, "Word" + "." * 200_000 + "x", "?" * 100_000 + " lower"])
def test_sentence_boundaries_are_linear_on_long_runs_of_end_marks(text):
    t = time.perf_counter()
    _boundaries(text)
    assert time.perf_counter() - t < 2.0
