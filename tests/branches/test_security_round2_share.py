"""Security round 2, SEC-V5: a stated share ('5 per cent of the 200 seats, or 10') is read in linear time (``quant._SHARE_RE``
and the SI reading's share pattern).

The share pattern read the white space after 'of' with two quantifiers (``\\s+of\\s+(?:the\\s+)?...\\s*``) and the white space
of the link between the whole and the part with three (``\\s*,\\s*(?:or...)?`` then ``\\s*(?:about...)?\\s*``). Before a long
run of white space that no figure follows, each try split the run between them in every way: quadratic in the run after
'of', cubic after the comma (twenty shares with a run of 200 spaces after the comma took 22 s). Every run of white space of
the links is now read once (possessive): what a run may stand before (a word, 'or', 'that is', a bracket, a figure) never
starts with white space, so a run read in part leaves the same match or none. These tests pin the growth of the reading
and that every share is read as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import quant

from ..growth import growth

#: The links before this round, kept as data to pin that every share is read as before.
OLD_OF = r"\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*"
OLD_LINK = (r"(?:\s+[a-z]+){0,2}?(?:\s*,\s*(?:or|i\.e\.|that is)?|\s+(?:or|was|is|=|that is|i\.e\.)|\s*\()"
            r"\s*(?:about|around|roughly|some)?\s*")


def _old(p: "re.Pattern[str]") -> "re.Pattern[str]":
    assert quant._SHARE_OF in p.pattern and quant._SHARE_LINK in p.pattern
    return re.compile(p.pattern.replace(quant._SHARE_OF, OLD_OF).replace(quant._SHARE_LINK, OLD_LINK), p.flags)


PATTERNS = {"general": quant._SHARE_RE, "si": quant._si_patterns().share}
OLD = {name: _old(p) for name, p in PATTERNS.items()}


def test_the_general_reading_uses_the_share_pattern():
    assert quant._GENERAL_PATTERNS.share is quant._SHARE_RE


def _scan(rx):
    return lambda text: sum(1 for _m in rx.finditer(text)) + (rx.search(text) is not None)


#: Long runs of white space where the links read them, none followed by a figure (each repeated so one scan reads many).
HOSTILE = {
    "after 'of the'": lambda n: ("5 per cent of the" + " " * n + "x. ") * 20,
    "after 'of'": lambda n: ("5 per cent of" + "\t " * (n // 2) + "x. ") * 20,
    "after the comma": lambda n: ("5 per cent of the 200 seats," + " " * n + "or none. ") * 20,
    "after the bracket": lambda n: ("5 per cent of the 200 seats (" + " " * n + "none). ") * 20,
    "after 'or'": lambda n: ("45% of the 1,200 workers or" + "\n " * (n // 2) + "most. ") * 20,
}


def test_a_long_run_of_white_space_in_a_share_is_read_in_linear_time():
    """Four times the run costs about four times as much (before: about sixteen times after 'of', sixty-four after the comma)."""
    for shape, make in HOSTILE.items():
        small, large = (50, 200) if shape == "after the comma" else (500, 2000)
        for name, rx in PATTERNS.items():
            ratio, t_small, t_large = growth(_scan(rx), make(small), make(large))
            assert ratio < 8.0, (shape, name, ratio, t_small, t_large)


def test_the_prose_arithmetic_reading_of_a_share_with_a_long_run_grows_linearly():
    text = lambda n: "The figures follow. " + ("Labour won 5 per cent of the 200 seats," + " " * n + "or none. ") * 10 + " The end."
    ratio, small, large = growth(quant.undecided_quant_statements, text(50), text(200), clear=quant._analyse.cache_clear)
    assert ratio < 8.0, (ratio, small, large)


SENTENCES = [
    "Labour won 5 per cent of the 200 seats, or 10.",
    "About 45% of the 1,200 workers (540) were women.",
    "It took 12 per cent of the 3,000, i.e. 360.",
    "Some 10% of 50 is 5.",
    "Roughly 20 per cent of about 400 = 80 people.",
    "30 per cent of roughly 2,000 people, that is 600, left.",
    "5 per cent of the 200 or 10 were lost.",
    "25%  of   the    80 tonnes ,   or   about   20 tonnes.",
    "15 per cent of the 1.2 million arrivals, or some 180,000.",
    "50% of the 12 seats was 6 and 20% of 30 was 6.",
    "7 per cent of the 300 workers in the mill, or 21.",
    "7 per cent of the 300 workers in the old mill, or 21.",
    "8 per cent of\nthe\n100\n(\n8\n)",
    "9 per cent of the 1 000 000 people, i.e. 90 000.",
    "10 percent of the $5 billion budget, that is about $500 million.",
    "11 per cent of the 200, or",
    "12 per cent of the , or 5",
    "x 13% of the 100 is (about 13)",
    "A 14 per cent of the 100 seats = 14 seats.",
    "1.5 per cent of the 2,000 mm, or 30 mm",
    "50 per cent of the 10 m² (5 m²)",
    "3 × 10³ per cent of the 4 × 10² kg, or 12 × 10³ kg",
]


def _random_texts(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["5", "45", "1,200", "3.5", "200", "per cent", "percent", "%", "of", "the", "about", "around", "roughly", "some", ",", "or",
              "i.e.", "that is", "is", "was", "=", "(", ")", "seats", "workers", "in", "mill", "tonnes", "million", "$", "x", "·", "×", "10³"]
    spaces = [" ", " ", " ", "  ", "\t", "\n", " \n ", "", "   "]
    out = []
    for _ in range(n):
        toks = []
        for _ in range(rnd.randrange(4, 26)):
            toks.append(rnd.choice(pieces))
            toks.append(rnd.choice(spaces))
        out.append("".join(toks))
    return out


def _sig(m):
    return None if m is None else (m.span(), m.groups())


def test_every_share_is_read_as_before():
    """Both share patterns find the same matches, with the same groups, as before the round: scanning the whole text, and
    searched and anchored from every place of it."""
    compared = 0
    for s in SENTENCES + _random_texts(300, seed=5):
        for name, new in PATTERNS.items():
            old = OLD[name]
            assert [_sig(m) for m in new.finditer(s)] == [_sig(m) for m in old.finditer(s)], (name, s)
            for i in range(len(s) + 1):
                assert _sig(new.search(s, i)) == _sig(old.search(s, i)), (name, s, i)
                assert _sig(new.match(s, i)) == _sig(old.match(s, i)), (name, s, i)
            compared += 1
    assert compared == 2 * (len(SENTENCES) + 300)


def test_stated_shares_are_still_read_and_checked():
    """Clean controls: each share is read with its three figures and checked as before."""
    m = quant._SHARE_RE.search("Labour won 5 per cent of the 200 seats, or 10.")
    assert m is not None and (m.group(0), m.groups()) == ("5 per cent of the 200 seats, or 10", ("5", "200", "seats", "10", None))
    m = quant._SHARE_RE.search("About 45% of the 1,200 workers (540) were women.")
    assert m is not None and m.groups()[:4] == ("45", "1,200", None, "540")
    for s in ("Labour won 5 per cent of the 200 seats, or 10.", "It took 12 per cent of the 3,000, i.e. 360.", "Some 10% of 50 is 5."):
        assert [c.kind for c in quant.extract_quant_checks(s, request_id="r", claim_id="c")] == ["share"], s
