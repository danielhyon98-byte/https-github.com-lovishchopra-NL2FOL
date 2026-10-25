"""Security round 1: the part labels of a request are found in linear time (``request_parser._PART_LABEL_RE``, ``_PART_END_RE``).

A part label ('(a)', 'ii)', '2.') stands at the request's start, a line's start or after a sentence's end and white space. The
white space after a sentence's end was read by two quantifiers side by side ('\\s+' and '[ \\t]*'), which split a long run
between them in every way before failing when no label followed: a request of 32,000 spaces after a full stop held the hub for
86 s (the base's pattern alike; this tree reads the request's parts with it once more, ``_part_spans``). The end of a part
(its mark annotation) split the spaces after '[1' the same way. Both now read their white space possessively, and every
request is cut as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.channel import request_parser as RP

from ..growth import growth

OLD_PART_LABEL = re.compile(RP._PART_LABEL_RE.pattern.replace(")])\\s++|", ")])\\s+|"), RP._PART_LABEL_RE.flags)
OLD_PART_END = re.compile("\\[\\s*\\d+\\s*(?:marks?)?\\s*\\][\\'\u2019\\\"\u201d\u00bb]?(?=\\s+[A-Z\u00bf\u00a1\u00ab\\\"\u201c])")


def test_the_old_patterns_are_rebuilt():
    assert OLD_PART_LABEL.pattern != RP._PART_LABEL_RE.pattern and "\\s++" not in OLD_PART_LABEL.pattern
    assert OLD_PART_END.pattern != RP._PART_END_RE.pattern


def _hostile(n: int, run: str = " ") -> str:
    return "Answer the question. " + run * n + " Explain your answer. (a) Find x. [2 marks]" + run * n + "x"


def test_a_long_run_after_a_sentence_is_cut_in_linear_time():
    for run in (" ", "\t", " \n"):
        for reader in (RP._part_spans, RP.request_parts):
            ratio, small, large = growth(reader, _hostile(2000 // len(run), run), _hostile(8000 // len(run), run))
            assert ratio < 8.0, (reader.__name__, repr(run), ratio, small, large)


REQUESTS = ["(a) Explain why prices rose. [2 marks] (b) Calculate the change. [3]", "Answer both parts.\n(a) Find x.\n(b) Find y.",
            "a) one\nb) two", "1. Explain. 2. Describe.", "In 2020? 3. Indica la causa.", "... exam. 1. Según el texto ...", "part (a) is prose",
            "Paper 2 and 1.5 are no labels", "Read this: (iii) the third", "End.  \t (ii) Next", "\u201cQuote.\u201d (c) Then", "x) y", "(a)", "", "  (a) x",
            "Explain. [3]' My answer is pasted below.", "Explain [2 marks]   Next", "[1 + 2] Done", "[ 4 marks ]\u2019 Then", "[2]x", "[2] lower"]


def _random_requests(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["(a)", "(b)", "ii)", "iv)", "2.", "12)", "a)", " ", "  ", "\t", "\n", ".", "?", "!", ":", ";", "]", "\u201d", "\u2019", ")", "(", "Explain",
              "find", "x", "[2]", "[3 marks]", "[1", "marks", "\u00bf", "1.5"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 16))) for _ in range(n)]


def _norm(matches):
    return [(m.span(), m.span("label") if "label" in m.re.groupindex else None) for m in matches]


def test_every_part_label_and_part_end_is_found_as_before():
    for s in REQUESTS + _random_requests(40_000, seed=71):
        assert _norm(RP._PART_LABEL_RE.finditer(s)) == _norm(OLD_PART_LABEL.finditer(s)), repr(s)
        a, b = RP._PART_END_RE.search(s), OLD_PART_END.search(s)
        assert (a and a.span()) == (b and b.span()), repr(s)


def test_parts_are_still_cut():
    assert [lab for lab, _a, _b in RP._part_spans("(a) Explain why prices rose. [2 marks] (b) Calculate the change. [3]")] == ["a", "b"]
    assert [lab for lab, _t in RP.request_parts("Answer both parts.\n(a) Find x.\n(b) Find y.")][-2:] == ["a", "b"]
    assert RP._part_spans("Paper 2 and 1.5 are no labels") == []
