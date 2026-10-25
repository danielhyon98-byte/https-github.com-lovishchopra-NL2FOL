"""Security round 1: a decrease word after a figure is read in linear time (``integrity.ledger._DECREASE_AFTER_RE``).

The ledger reads, after every figure of a text, whether a decrease word follows it ('5% fall', '3 per cent decline'). The
white space around the optional per-cent unit was read by two quantifiers side by side, which split a long run after a figure
between them in every way before failing, once per figure. It is now read possessively; every figure is read as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.integrity import ledger as L

from ..growth import growth

OLD = re.compile("\\s*(?:%|per\\s*cent|percent)?\\s*(?:fall|decrease|drop|decline|reduction|loss|cut|contraction)\\b", re.IGNORECASE)


def test_a_long_run_after_a_figure_is_read_in_linear_time():
    for shape in ("5{}x", "5 %{}x", "5{}per cent{}x", "5{}%{}fal"):
        ratio, small, large = growth(lambda t: L._DECREASE_AFTER_RE.match(t, 1), shape.replace("{}", " " * 2000), shape.replace("{}", " " * 8000))
        assert ratio < 8.0, (shape, ratio, small, large)


CASES = ["5% fall", "5 % fall", "5 per cent decline", "5 percent drop", "5percent cut", "5 per  cent loss", "5\tfall", "5 fallen", "5 falls", "5% falling",
         "5 %  reduction", "5 PER CENT DECREASE", "5 contraction", "5 % x", "5", "5 per", "5 %%fall", "5 % per cent fall", "5\n%\nfall"]


def test_every_figure_is_read_as_before():
    rnd = random.Random(61)
    pieces = [" ", "  ", "\t", "\n", "%", "per", "per cent", "percent", "cent", "fall", "fallen", "decrease", "drop", "cut", "x", "loss", "s"]
    texts = CASES + ["5" + "".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 8))) for _ in range(40_000)]
    for s in texts:
        a, b = L._DECREASE_AFTER_RE.match(s, 1), OLD.match(s, 1)
        assert (a and a.span()) == (b and b.span()), repr(s)


def test_decreases_are_still_read():
    assert L._DECREASE_AFTER_RE.match("5% fall", 1) and L._DECREASE_AFTER_RE.match("5 per cent decline", 1)
    assert L._DECREASE_AFTER_RE.match("5 fallen", 1) is None and L._DECREASE_AFTER_RE.match("5 rise", 1) is None
