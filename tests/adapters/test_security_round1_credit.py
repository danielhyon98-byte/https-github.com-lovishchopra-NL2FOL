"""Security round 1: the words between a credited name and its quotation are read in linear time (``adapters.sources``).

``quotation_credit`` reads, for every name or kind before a quotation, the gap from the name to the quotation
(``_CREDIT_GAP_RE``: a possessive, a noun, adverbs and a crediting verb) and whether the name opens its sentence
(``_SENTENCE_OPEN_RE``). The gap's white space was split between two or three quantifiers before failing, so a gap of 1,000
spaces took 0.9 s and grew with its square (the base's pattern alike); the sentence opening was searched from every end mark
and line break, each start reading the white space after it. The gap is now read possessively and the opening from the
end of the text before the name; both read every text as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.adapters import sources as S

from ..growth import growth

#: The gap pattern before this round: the same pattern with its white space read as it was.
OLD_GAP = re.compile(
    S._CREDIT_GAP_RE.pattern.replace("['\u2019]s?\\s*+[,:]?+\\s*+$", "['\u2019]s?\\s*[,:]?\\s*$")
    .replace("(?:\\s++own)?(?:\\s++", "(?:\\s+own)?(?:\\s+").replace(")?)?(?:\\s*+,)?+\\s++(?:", ")?)?\\s*,?\\s+(?:").replace("\\s++)*", "\\s+)*"),
    S._CREDIT_GAP_RE.flags)
OLD_SENTENCE_OPEN = re.compile("(?:^|[.!?]\\s+|\\n)\\s*$")


def test_the_old_gap_pattern_is_rebuilt():
    assert OLD_GAP.pattern != S._CREDIT_GAP_RE.pattern
    assert not re.search(r"(?<!\\)[*+?}]\+", OLD_GAP.pattern), "a possessive quantifier is left in the rebuilt pattern"
    assert OLD_SENTENCE_OPEN.pattern == S._SENTENCE_OPEN_RE.pattern


def test_a_gap_of_white_space_is_read_in_linear_time():
    for shape in ("{}x", "'s{}x", "'s own{}x", "'s{},{}x", "{}also{}x", "'s speaker{}himself{}x"):
        ratio, small, large = growth(S._CREDIT_GAP_RE.match, shape.replace("{}", " " * 400), shape.replace("{}", " " * 1600))
        assert ratio < 8.0, (shape, ratio, small, large)


def test_the_text_before_a_name_is_read_in_linear_time():
    for shape in ("It is calm.{}x the ", "It is calm{}x the ", "It is calm!{} x "):
        unit = "\n" if "calm{}" in shape else " "
        ratio, small, large = growth(S._opens_sentence, shape.replace("{}", unit * 2000), shape.replace("{}", unit * 8000))
        assert ratio < 8.0, (shape, ratio, small, large)


GAPS = ["'s ", "\u2019s ", "'s, ", "'s: ", "'s", " ", "'s own words ", "'s speaker himself admits that ", " says that ", ", argues, ", " , says ",
        " ,says ", " also writes ", " then even says ", "'s poem says ", "'s own poem plainly states ", "'s\n", "'s  \n", "'s \t:\t", "'s x",
        " argues that the war, ", " calls the war ", " is ", " who wrote ", "'s narrator later observes ", "  ,  claims  ", " says", " said:",
        " saysx ", "'s owner says ", " , , says ", ""]


def _random_gaps(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["'s", "\u2019s", "'", " ", "  ", "\t", "\n", ",", ":", "own", "speaker", "poem", "himself", "also", "says", "argues", "writes",
              "that", "x", "admits", "words", "s"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 12))) for _ in range(n)]


def test_every_gap_is_read_as_before():
    for g in GAPS + _random_gaps(60_000, seed=37):
        a, b = S._CREDIT_GAP_RE.match(g), OLD_GAP.match(g)
        assert (a and a.span()) == (b and b.span()), repr(g)


def test_every_sentence_opening_is_read_as_before():
    rnd = random.Random(41)
    pieces = [".", "!", "?", " ", "  ", "\t", "\n", "\r", "\u2028", "x", "The poem", ";", ":"]
    texts = ["", " ", "\n", "x", "x.", "x. ", "x.\n", "x\n", "x\n ", "x \n", "x. y ", "x!\t", "x?\u2028", "x.\r\n", ". ", "x .", "x\ny"]
    texts += ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 10))) for _ in range(60_000)]
    for s in texts:
        assert S._opens_sentence(s) == (OLD_SENTENCE_OPEN.search(s) is not None), repr(s)


def test_credits_are_still_read():
    assert S._CREDIT_GAP_RE.match("'s speaker himself admits that ").end() == len("'s speaker himself admits")
    assert S._CREDIT_GAP_RE.match("'s ") and S._CREDIT_GAP_RE.match(", argues, ")
    assert S._CREDIT_GAP_RE.match(" is ") is None and S._CREDIT_GAP_RE.match("'s x") is None
    assert S._opens_sentence("") and S._opens_sentence("It is calm. ") and S._opens_sentence("It is calm\n")
    assert not S._opens_sentence("It is calm, and ")
