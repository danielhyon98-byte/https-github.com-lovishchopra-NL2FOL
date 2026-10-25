"""Security round 1: stated conversions and part labels are read in linear time.

``translate.relations._CONVERSION_RE`` ('1 month = 30 days', '30 days in a month') read the space after 'in', 'per' or 'to'
with two quantifiers side by side (one before the optional article, one after it), and
``translate.diag_argument._PART_LABEL_RE`` the space before a part label with two around the optional '**': a long run of
spaces with no conversion or label after it was split between them in every way before failing. The runs are now read
possessively, and every text is read as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.translate import diag_argument as D, relations as TR

from ..growth import growth

OLD_CONVERSION = re.compile(
    "\\b(?:1|one|a|an|each|every)\\s+(?P<a>[A-Za-z]+)\\s*(?:=|is|equals|is\\s+equal\\s+to|to\\s+be|as|has|have|contains?|makes?)\\s*"
    "(?P<n>\\d+(?:\\.\\d+)?)\\s*(?P<b>[A-Za-z]+)"
    "|\\b(?P<n2>\\d+(?:\\.\\d+)?)\\s*(?P<b2>[A-Za-z]+)\\s+(?:in|per|to)\\s+(?:a|an|one|each|every|the)?\\s*(?P<a2>[A-Za-z]+)", re.IGNORECASE)
OLD_PART_LABEL = re.compile("^\\s*(?:\\*\\*)?\\s*(?:part\\s+)?\\(?(?P<label>[a-h]|[ivx]{1,4}|\\d{1,2})\\)?(?:[).:]|\\s)", re.IGNORECASE)


def _conversions(text: str):
    return [(m.span(), m.groupdict()) for m in TR._CONVERSION_RE.finditer(text)]


def test_a_long_run_after_in_is_read_in_linear_time():
    for shape in ("It takes 30 days in{}1 x", "It takes 30 days per{}the{}9", "1 month ={}x"):
        ratio, small, large = growth(_conversions, shape.replace("{}", " " * 2000), shape.replace("{}", " " * 8000))
        assert ratio < 8.0, (shape, ratio, small, large)


def test_a_long_run_before_a_part_label_is_read_in_linear_time():
    for shape in ("{}x", "{}**{}x", "**{}part{}9x"):
        ratio, small, large = growth(D._part_label, shape.replace("{}", " " * 2000), shape.replace("{}", " " * 8000))
        assert ratio < 8.0, (shape, ratio, small, large)


TEXTS = ["Take 1 month = 30 days.", "one month is 30 days", "a year has 365 days", "take 1 month to be 30 days", "30 days in a month", "30 days per month",
         "12 months in the year", "1 hour is equal to 60 minutes", "1 kgis 5 g", "a monthis 30 days", "30 daysin a month", "30 days in theatre",
         "60 s to a minute", "an hour equals 60min", "every week has  7  days", "1 m = 100cm", "30\tdays\tin\ta\tmonth", "2 per", ""]
LABELS = ["(a) Explain.", "a) Explain.", "Part (b) Calculate", "**(c)** Find", "  ** (iii) Show", "2. Describe", "(ix) x", "part 3: y", "** part x)",
          "(z) not a label", "Explain (a).", "   ", "**", "(12)", "(123)", ""]


def _random_texts(n: int, seed: int, pieces: list[str]) -> list[str]:
    rnd = random.Random(seed)
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 14))) for _ in range(n)]


def test_every_conversion_is_read_as_before():
    pieces = ["1", "one", "a", "an", "every", "30", "2.5", "days", "month", "kg", "in", "per", "to", "the", "is", "=", "equals", "is equal to", "to be",
              "has", " ", "  ", "\t", "x", "."]
    for s in TEXTS + _random_texts(40_000, 53, pieces):
        assert _conversions(s) == [(m.span(), m.groupdict()) for m in OLD_CONVERSION.finditer(s)], repr(s)


def test_every_part_label_is_read_as_before():
    pieces = ["**", "*", " ", "  ", "\t", "\n", "part", "Part", "(", ")", "a", "b", "iii", "ix", "2", "12", ".", ":", "x", "Explain"]
    for s in LABELS + _random_texts(40_000, 59, pieces):
        a, b = D._PART_LABEL_RE.match(s), OLD_PART_LABEL.match(s)
        assert (a and (a.span(), a.groupdict())) == (b and (b.span(), b.groupdict())), repr(s)


def test_conversions_and_labels_are_still_read():
    assert [m.group("n") or m.group("n2") for m in TR._CONVERSION_RE.finditer("Take 1 month = 30 days, so 7 days in a week.")] == ["30", "7"]
    assert D._part_label("(b) Calculate the speed.") == "b" and D._part_label("**Part (c)** Find x") == "c"
    assert D._part_label("Explain why.") is None
