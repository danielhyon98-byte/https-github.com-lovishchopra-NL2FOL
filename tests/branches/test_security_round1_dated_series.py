"""Security round 1: a supplied data text's dated series is read in linear time (``packs._DATED_LINE_RE``).

``_dated_series`` reads a supplied text written one year a line ("2020: 8.9") for the table-figure check. Each line was
matched with backtracking quantifiers, two of them around an optional separator and two around an optional unit word, so a
line holding a year, a long run of spaces and a word was split between them in every way before failing: quadratic in the
run, and one line of a supplied text can hold 400,000 characters. Every quantifier is now possessive, which reads every
line as before (each quantifier's longest reading is the only one the rest of the line can follow).
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import packs

from ..growth import growth

#: The line pattern before this round, kept as data to pin that every line is read as before.
OLD = re.compile("\\s*(1[6-9]\\d{2}|20\\d{2})\\s*[:=\\-\u2013|,]?\\s*(-?\\d+(?:\\.\\d+)?)\\s*(?:%|[a-z]{0,12})?\\s*$", re.IGNORECASE)


def test_a_long_line_is_read_in_linear_time():
    for line in ("1999{} x", "1999 5{} x", "1999:{}-x", "2020 8.9 %{}per", "1999{}5{}x"):
        small, large = line.replace("{}", " " * 2000), line.replace("{}", " " * 8000)
        ratio, ts, tl = growth(packs._dated_series, small, large)
        assert ratio < 8.0, (line, ratio, ts, tl)


LINES = ["2020: 8.9", "2020 - 8.9", "2020 8.9", "2020 8.9%", "2020 8.9 %", " 1999 -5", "1999 - -5", "2019 | 12 %", "2020\u20134.5",
         "2001,  3.2 million", "2001, 3.2 millions", "2020 8.9 percentagepoints", "1999-", "1999 -", "1650 = 7.25 tonnes", "2100 5",
         "1599 5", "2020 8.9 x y", "2020 8.", "2020 .5", "2020 5.25.1", "2020:8.9   ", "2020 8.9 PER", "\t2020\t3\t", "2020 3e4", "2020 3,000"]


def test_every_line_is_read_as_before():
    rnd = random.Random(3)
    pieces = ["2020", "1999", "1650", " ", "  ", "\t", ":", "=", "-", "\u2013", "|", ",", "5", "8.9", "-3", ".", "%", "x", "tonnes", "PER", "abcdefghijklmn"]
    lines = LINES + ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 9))) for _ in range(30_000)]
    for s in lines:
        a, b = OLD.match(s), packs._DATED_LINE_RE.match(s)
        assert (a and (a.span(), a.groups())) == (b and (b.span(), b.groups())), repr(s)


def test_a_dated_series_is_still_read():
    text = "Table 1: Inflation in Country P (%)\n2018: 2.1\n2019 - 2.4\n2020 8.9\n2021 | 5.6 %\nnot a line\n1999 -5"
    series = packs._dated_series(text)
    assert {y: [w for _v, w in vals] for y, vals in series.items()} == {2018: ["2.1"], 2019: ["2.4"], 2020: ["8.9"], 2021: ["5.6"], 1999: ["5"]}
