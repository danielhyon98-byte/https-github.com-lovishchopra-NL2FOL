"""Security round 1: whether a request states a relation is read in linear time (``packs._REQUEST_RELATION_RE``).

``request_model_extrapolation`` runs only when the request states a relation ('fits the line Q = 1.6R + 4'). The pattern
was searched from every letter of the request, and from a letter inside a long word it read the word again to its end
before failing, so a request of one 19,000-letter word took 3.5 s to receive on a general branch. It is now tried from the
start of a word only and reads the name possessively; it answers the question (does the request state a relation) as
before on every request.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import packs

from ..growth import growth

#: The pattern before this round, kept as data to pin that every request is answered as before.
OLD = re.compile("[A-Za-z][\\w\u2080-\u2089]*\\s*=\\s*[-\u2212]?[\\w(.\u221a]")


def _states(text: str) -> bool:
    return packs._REQUEST_RELATION_RE.search(text[:20000]) is not None


def test_a_long_word_is_read_in_linear_time():
    for unit in ("A", "ab1", "x\u2081", "_Q"):
        ratio, small, large = growth(_states, "Explain the model " + unit * (4000 // len(unit)) + " and its limits.",
                                     "Explain the model " + unit * (16000 // len(unit)) + " and its limits.")
        assert ratio < 8.0, (unit, ratio, small, large)


def test_a_long_word_before_a_relation_is_read_in_linear_time():
    ratio, small, large = growth(_states, "Fit " + "Q" * 4000 + " so that y = 1.6R + 4", "Fit " + "Q" * 16000 + " so that y = 1.6R + 4")
    assert ratio < 8.0, (ratio, small, large)


REQUESTS = [
    "The peak discharge fits the line Q = 1.6R + 4 for rainfall between 10 mm and 40 mm.",
    "Use y=−2x+3 to predict y.",
    "Given x\u2081 = (a + b)/2, find a.",
    "Show that E = \u221a(2gh).",
    "If 2x = 6, what is x?",
    "Let \u03b1 = 0.5 and n = 10.",
    "The model s = 4.8h + 41 was fitted on revision hours.",
    "a == b is a comparison, not a relation.",
    "x = - 3",
    "x =\n\t.5",
    "No relation here, only words and 12 figures.",
    "Q1_total= 5",
    "_x = 5",
    "9a = b",
    "\u00e9t\u00e9 = 3",
    "t\u2081 =",
    "",
]


def test_every_request_is_answered_as_before():
    rnd = random.Random(7)
    pieces = ["Q", "x", "a1", "_", "\u2081", "\u00e9", "9", " ", "\t", "\n", "=", "==", "-", "\u2212", "(", ".", "\u221a", "+", ",", "R",
              "fits the line ", "\u03b1"]
    texts = REQUESTS + ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 16))) for _ in range(40_000)]
    for s in texts:
        assert (OLD.search(s) is not None) == (packs._REQUEST_RELATION_RE.search(s) is not None), repr(s)


def test_a_relation_is_still_found():
    assert _states("The peak discharge fits the line Q = 1.6R + 4.")
    assert _states("Given x\u2081 = (a + b)/2, find a.")
    # clean controls: no relation, or a comparison, is not one
    assert not _states("Explain why prices rose in 1923.")
    assert not _states("a == b")
