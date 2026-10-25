"""Security round 1: an average rate is read in linear time (``quant._RATE_RES``).

The rate tail stands unbracketed at the end of the two average-rate patterns, so its 'annually' alternative is a pattern of
its own: white space, then 'annually' or 'yearly', anywhere in a clause that mentions an average. It was tried from every
space of a run and read the run again to its end each time: a clause of 'averaging' and 8,000 spaces held the prose
reading for 1.4 s (4,000 spaces: 0.3 s). It now starts only where its run of white space starts; every match ends on a
letter, so the scan reaches a space inside a run only after trying the run's start, and the matches are the ones they were.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import quant

from ..growth import growth

#: The patterns before this round: the same patterns with the rate tail as it was.
OLD = [re.compile(p.pattern.replace(quant._RATE_SCAN_TAIL, quant._RATE_TAIL), p.flags) for p in quant._RATE_RES]


def test_the_old_patterns_are_rebuilt():
    assert all(quant._RATE_SCAN_TAIL in p.pattern for p in quant._RATE_RES)
    assert all(quant._RATE_TAIL in p.pattern and quant._RATE_SCAN_TAIL not in p.pattern for p in OLD)


def _scan(text: str) -> int:
    return sum(1 for p in quant._RATE_RES for _m in p.finditer(text))


def _hostile(n: int, run: str = " ") -> str:
    return "Output grew, averaging" + run * n + "x a year. The war ended in 1918."


def test_a_long_run_of_white_space_in_an_average_is_scanned_in_linear_time():
    for run in (" ", "\t", " ", " \n"):
        ratio, small, large = growth(_scan, _hostile(2000 // len(run), run), _hostile(8000 // len(run), run))
        assert ratio < 8.0, (run, ratio, small, large)


def test_the_prose_reading_of_an_average_with_a_long_run_grows_linearly():
    ratio, small, large = growth(quant.undecided_quant_statements, _hostile(2000), _hostile(8000), clear=quant._analyse.cache_clear)
    assert ratio < 8.0, (ratio, small, large)


CLAUSES = [
    "Output rose by an average of 450 miles a year between 1900 and 1910.",
    "The railway grew, averaging 450 miles a year, and averaging about 2.5 million tonnes per year after 1920.",
    "At an average rate of 450 miles per year it expanded; an annual average increase of £3,000 annually.",
    "It averaged 1 200 tonnes each month and averages 12 seats every decade.",
    "Exports grew annually and   yearly, and the average of 7 was reached  annually.",
    "averaging     450 miles    a    year",
    "an average of 5   annually",
    "average\tgrowth of 30 000 people yearly",
    "a fall averaging 40 per year, a rise averaging 3 per cent a year",
    "averaging x a year",
    "The average was high. It rose annually.",
    ",  annually and.  yearly",
    "",
]


def _random_clauses(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["averaging", "averaged", "an average of", "average", "annual", "rate of", "450", "1 200", "2.5 million", "tonnes", "miles",
              "a", "per", "each", "year", "month", "annually", "yearly", " ", "  ", "\t", "\n", ",", ".", "x", "£", "about"]
    return [" ".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 16))) if rnd.random() < 0.5 else
            "".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 16))) for _ in range(n)]


def _norm(m):
    return m.span(), m.groupdict()


def test_every_average_is_read_as_before():
    for s in CLAUSES + _random_clauses(30_000, seed=23):
        for new, old in zip(quant._RATE_RES, OLD):
            assert [_norm(m) for m in new.finditer(s)] == [_norm(m) for m in old.finditer(s)], (new.pattern[:40], s)


def test_average_rates_are_still_read():
    d = [x for x in quant._derived_phrases("The railway grew, averaging 450 miles a year.") if x.kind == "rate_change"]
    assert len(d) == 1 and d[0].stated == 450 and d[0].noun == "miles" and d[0].per == "year"
    d = [x for x in quant._derived_phrases("Output rose by an average of 2.5 million tonnes per month.") if x.kind == "rate_change"]
    assert len(d) == 1 and d[0].stated == 2_500_000 and d[0].per == "month"
