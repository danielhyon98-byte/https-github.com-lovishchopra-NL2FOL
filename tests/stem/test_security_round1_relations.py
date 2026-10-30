"""Security round 1: three readings of a STEM request in linear time (``stem.relations``).

- ``_PROPERTY_SHOW_RE`` (a show-that request about a property of a number) read the words between 'that' and 'is' with
  three quantifiers that all take white space, so a request of 'Show that', a long run of spaces, 'is', another run and a
  word was split between them in every way before failing: 10 s on a 4,000-character request. It is a yes or no; the
  rewritten pattern answers it as before on every request.
- ``_PROSE_RANGE_RE`` (a range of data stated in words or figures) was scanned from every digit of a run of digits, each
  start reading the run again: 11 s on a request of 20,000 digits. ``_prose_ranges`` gives the pattern's own matches.
- ``_ASK_SENTENCE_RE`` (a sentence of the request that asks for something) was scanned from every line break of a run
  of blank lines, each start reading the run again: 30 s on a request of 20,000 line breaks. ``_ask_sentences`` gives
  the pattern's own matches.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.stem import relations as R

from ..growth import growth

#: The show-that pattern before this round, kept as data to pin that every request is answered as before.
OLD_PROPERTY_SHOW = re.compile(
    "\\bshow\\s+that\\s+[^.?!]{1,40}?\\s+(?:is|are)\\s+(?:not\\s+)?(?:an?\\s+)?(?:prime|composite|irrational|rational|even|odd"
    "|integer|whole\\s+number|natural\\s+number|perfect\\s+(?:square|cube)|multiple\\s+of|factor\\s+of|divisible\\s+by)\\b")


def _shows(req: str) -> bool:
    return R._PROPERTY_SHOW_RE.search(req[:4000]) is not None


def test_a_show_that_request_with_long_runs_of_space_is_read_in_linear_time():
    for shape in ("show that{} x", "show that{}is{}x", "show that 13{}is{}x", "show that\t{}\nare{}y"):
        ratio, small, large = growth(_shows, shape.replace("{}", " " * 400), shape.replace("{}", " " * 1600))
        assert ratio < 8.0, (shape, ratio, small, large)


def test_a_run_of_digits_in_a_request_is_read_in_linear_time():
    for unit in ("1", "1,", "1,,", "12.5"):
        ratio, small, large = growth(R._prose_ranges, "Q = 1.6R + 4 for R " + unit * (2500 // len(unit)) + " x.",
                                     "Q = 1.6R + 4 for R " + unit * (10000 // len(unit)) + " x.")
        assert ratio < 8.0, (unit, ratio, small, large)


def test_a_run_of_blank_lines_in_a_request_is_read_in_linear_time():
    for unit in ("\n", "\n ", ".\n", "?\t"):
        ratio, small, large = growth(R._ask_sentences, "Use p = mv." + unit * (2500 // len(unit)) + "x",
                                     "Use p = mv." + unit * (10000 // len(unit)) + "x")
        assert ratio < 8.0, (unit, ratio, small, large)


SHOW_REQUESTS = [
    "show that 13 is prime. [2 marks]",
    "show that √2 is irrational.",
    "show that 91 is not prime",
    "show that the sum of two odd numbers is even",
    "show that n² + n is even for every integer n",
    "show that 3 and 5 are both prime",
    "show that   is prime",
    "show that  is prime",
    "show that x is a multiple of 3",
    "show that 6 is a perfect square",
    "show that 12 is an integer",
    "show that 7 is divisible by 7",
    "show that this number, which is large, is composite",
    "show that a very long description of the number that runs on for more than forty letters is prime",
    "show that 13 is prime? yes",
    "show that 1.5 is rational",
    "show\nthat\n13\nis\nprime",
    "showthat 13 is prime",
    "show that13 is prime",
    "show that 13 isprime",
    "show that 13 is primes",
    "explain why 13 is prime",
    "",
]


def test_every_show_that_request_is_answered_as_before():
    rnd = random.Random(13)
    pieces = ["show", "that", "is", "are", "not", "an", "a", "prime", "even", "perfect square", "divisible by", "13", "x", " ", "  ",
              "\t", "\n", ".", "?", "!", ",", "√2", "showthat", "is is", "abcdefghijabcdefghijabcdefghij"]
    texts = SHOW_REQUESTS + ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 14))) for _ in range(30_000)]
    texts += ["show that" + "".join(rnd.choice([" ", "x", "\t", "ab"]) for _ in range(rnd.randrange(0, 50))) + " is " + rnd.choice(["prime", "x", "not even"])
              for _ in range(20_000)]
    for s in texts:
        assert (OLD_PROPERTY_SHOW.search(s) is not None) == (R._PROPERTY_SHOW_RE.search(s) is not None), repr(s)


def _norm(matches):
    return [(m.span(), m.groupdict()) for m in matches]


RANGE_REQUESTS = [
    "For eleven storms with rainfall totals between 10 mm and 40 mm, the peak discharge fits the line Q = 1.6R + 4.",
    "hours of revision h (from 2 to 10 hours), the regression line s = 4.8h + 41",
    "for 10–40 mm of rain and 5-6 hours",
    "between 1,000 and 2,500 kg, from 0.5 to 1.5 s",
    "values 3,5-6 mm and 6.7,8-9 and 6.75,,8-9 cm",
    "between them,5-10 hours and ,,5-10 hours",
    "between 5   and 7 °C and from 2 kg to 9 kg",
    "1,2,3,4-5,6 and 12.5-13.5% and 7 – 8 µm",
    "between 10 mm and   and 40 mm",
    "from 3 to",
    "1-",
    "x1-2y and 3 -4 and 5- 6",
    "betweenness 3-4, fromage 5 to 6",
    "1111111111-2 and ,1,1,1-2",
    "",
]


def _random_range_texts(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["between", "from", "and", "to", " ", "  ", "1", "12", "1,000", ",", ",,", ".", ".5", "-", "–", "mm", "kg", "°C", "%", "x", "h", "\n"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 20))) for _ in range(n)]


def test_every_range_is_read_as_before():
    for s in RANGE_REQUESTS + _random_range_texts(40_000, seed=17):
        assert _norm(R._prose_ranges(s)) == _norm(R._PROSE_RANGE_RE.finditer(s)), repr(s)


ASK_REQUESTS = [
    "A car of mass 1200 kg moves at 20 m/s. Calculate its momentum. Find the kinetic energy.\n(b) Explain why it slows.",
    "Trolley A has mass 2 kg. Trolley B has mass 3 kg.\n\n\nWhat is the momentum of trolley A?",
    "(a) Calculate the time for the sound to reach a wall.\n  (b)  How far does it travel?",
    "calculate x. find y! what is z? state w\n",
    "No command here.\n\n\n\nJust text.",
    "Use p = mv.\n \n \nShow that p = 24000.",
    "Determine.Compare.Estimate.Predict.Which.How.Work out.",
    "...Find x",
    "Explain\n\nExplain",
    "",
    "\n",
]


def _random_ask_texts(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["Calculate", "find", "What", "how", "Show", "x", "the mass", "(a)", "(b) ", ".", "!", "?", "\n", " ", "\t", "  ", "Work out", "ab"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 20))) for _ in range(n)]


def test_every_asking_sentence_is_read_as_before():
    for s in ASK_REQUESTS + _random_ask_texts(40_000, seed=19):
        assert _norm(R._ask_sentences(s)) == _norm(R._ASK_SENTENCE_RE.finditer(s)), repr(s)


def test_the_readings_still_find_what_they_did():
    assert _shows("show that 13 is prime. [2 marks]") and _shows("show that √2 is irrational") and _shows("show that 91 is not prime")
    assert not _shows("explain why 13 is prime") and not _shows("show that 13 is large")
    ranges = R._prose_ranges("For storms with rainfall between 10 mm and 40 mm, hours (from 2 to 10 hours), 10–40 mm")
    assert [(m.group("lo") or m.group("lo2") or m.group("lo3"), m.group("hi") or m.group("hi2") or m.group("hi3")) for m in ranges] == [
        ("10", "40"), ("2", "10"), ("10", "40")]
    asks = R._ask_sentences("Trolley A has mass 2 kg.\n\nCalculate the momentum of trolley A. What is its speed?")
    assert [m.group(0).strip() for m in asks] == ["Calculate the momentum of trolley A", "What is its speed"]
