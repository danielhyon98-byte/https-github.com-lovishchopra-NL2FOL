"""Security round 1: the closing of a wrapped sentence is read in linear time (``sentences._WRAP_CLOSE_RE``).

``inner_sentences`` splits a quotation or a JSON string wrapped round a whole sentence; the core pack reads every sentence
of every non-STEM report through it. The closing pattern was searched from every closing mark of a run, each attempt
reading the rest of the run again, and the white space after the marks was split between its two quantifiers in every way
before failing: a sentence of 8,000 closing quotation marks took 4.2 s to receive in Economics (the base, 1.1 s). The
pattern now starts only at the first mark of a run and reads possessively; its leftmost match is the one it was.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.adapters.history_specialist import sentences as S

from ..growth import growth

#: The pattern before this round, kept as data to pin that every closing is read as before.
OLD = re.compile("[\\\"”’'»]+\\s*\\}?\\s*$")


def _hostile(n: int, mark: str = "’", tail: str = "!") -> str:
    return "The answer is clear " + mark * n + tail


def test_a_sentence_of_closing_marks_is_split_in_linear_time():
    for mark, tail in (("’", "!"), ("\"", " So it follows"), ("»", "x"), ("'", "\u0000")):
        ratio, small, large = growth(S.inner_sentences, _hostile(1000, mark, tail), _hostile(4000, mark, tail))
        assert ratio < 8.0, (mark, ratio, small, large)


def test_white_space_after_a_closing_mark_is_read_once():
    ratio, small, large = growth(S.inner_sentences, "“The crash came.”" + " " * 2000 + "x", "“The crash came.”" + " " * 8000 + "x")
    assert ratio < 8.0, (ratio, small, large)


CASES = [
    "\"The crash of 1929 came after the boom. Banks failed in 1930.\"",
    "{\"answer\": \"Prices rose in 1923. The mark collapsed.\"}",
    "“The war ended in 1918. The treaty was signed in 1919.”  ",
    "‘It began. It ended.’\n",
    "«Il pleut. Il fait froid.» }",
    "\"One.\" \"Two.\"",
    "No wrapping here. None at all.",
    "\"Unclosed. Still open.",
    "\"Closed twice.\"\"",
    "\"Brace then text.\" } more",
    "\"Two braces.\" }}",
    "'Single quotes. Inside.' ",
    "\"A\" ” \"",
    "",
    "”",
    "’’’",
    "\"x\"\t \n",
]


def test_every_closing_is_read_as_before():
    rnd = random.Random(5)
    pieces = ["\"", "”", "’", "'", "»", " ", "\t", "\n", "}", "{", "a", ".", "A. ", "1929", ":"]
    texts = CASES + ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 18))) for _ in range(20_000)]
    for s in texts:
        a, b = OLD.search(s), S._WRAP_CLOSE_RE.search(s)
        assert (a and a.span()) == (b and b.span()), repr(s)


def test_wrapped_sentences_are_still_split():
    assert S.inner_sentences("\"The crash of 1929 came after the boom. Banks failed in 1930.\"") == [
        "The crash of 1929 came after the boom.", "Banks failed in 1930."]
    assert S.inner_sentences("{\"answer\": \"Prices rose in 1923. The mark collapsed.\"}") == ["Prices rose in 1923.", "The mark collapsed."]
    # clean controls: no wrapping, or one sentence inside, stay as they are
    assert S.inner_sentences("No wrapping here. None at all.") == ["No wrapping here. None at all."]
    assert S.inner_sentences("\"Only one sentence.\"") == ["\"Only one sentence.\""]
