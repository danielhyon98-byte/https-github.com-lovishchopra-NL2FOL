"""Security round 1: the links between the figures of a list are read in linear time (``quant._AND_LINK``, ``quant._ITEM_LEAD``).

A dated pair joined by 'and' ('4.5 million in 1931 and 5.6 million in 1932') and the next item of a list after a pair (',
655', ' and 720 mm in 2023') were read with two white-space quantifiers side by side ('\\s*,?\\s+and', '\\s*(?:,...|\\s+and')
that split a run of white space between them in every way before failing: a pair, 16,000 spaces and a word held the prose
reading of a report for 2.8 s (8,000: 0.8 s). The run is now read once, possessively, and every list is read as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import quant

from ..growth import growth

OLD_AND_LINK = "\\s*,?\\s+and\\s+"
OLD_ITEM_LEAD = "\\s*(?:,\\s*(?:and\\s+)?|\\s+and\\s+)"


def _old(p: re.Pattern) -> re.Pattern:
    return re.compile(p.pattern.replace(quant._AND_LINK, OLD_AND_LINK).replace(quant._ITEM_LEAD, OLD_ITEM_LEAD), p.flags)


SI = quant._si_patterns()
#: (name, pattern after the round, pattern before it, how its readers apply it)
PATTERNS = [("and_dated", quant._AND_DATED_RE, "scan"), ("list_item", quant._LIST_ITEM_RE, "anchored"), ("undated_item", quant._UNDATED_ITEM_RE, "anchored"),
            ("si.and_dated", SI.and_dated, "scan"), ("si.list_item", SI.list_item, "anchored")]
PATTERNS = [(name, new, _old(new), how) for name, new, how in PATTERNS]


def test_the_old_patterns_are_rebuilt():
    for name, new, old, _how in PATTERNS:
        assert old.pattern != new.pattern and (OLD_AND_LINK in old.pattern or OLD_ITEM_LEAD in old.pattern), name
        assert quant._AND_LINK not in old.pattern and quant._ITEM_LEAD not in old.pattern, name


def _hostile(n: int, run: str = " ") -> str:
    return "Output rose from 5 in 2019 to 6 in 2020" + run * n + "x so it grew. Prices rose from 30 in 1920 to 45 in 1923" + run * n + "and so on."


def test_a_long_run_after_a_list_figure_is_read_in_linear_time():
    for run in (" ", "\t", " "):
        ratio, small, large = growth(quant.undecided_quant_statements, _hostile(2000, run), _hostile(8000, run), clear=quant._analyse.cache_clear)
        assert ratio < 8.0, (repr(run), ratio, small, large)


def test_the_si_reading_of_a_long_run_after_a_list_figure_grows_linearly():
    ratio, small, large = growth(lambda t: quant.undecided_quant_statements(t, reading=quant.SI_READING), _hostile(2000), _hostile(8000),
                                 clear=quant._analyse.cache_clear)
    assert ratio < 8.0, (ratio, small, large)


FIGURE = "It reached 6 million in 2020"


def test_each_link_pattern_is_read_in_linear_time():
    """Each pattern as its reader applies it: a scan of the clause, or a match where the figure before it ends."""
    for name, new, _old_p, how in PATTERNS:
        def run(t, new=new, how=how):
            return sum(1 for _m in new.finditer(t)) if how == "scan" else new.match(t, len(FIGURE)) is not None
        ratio, small, large = growth(run, FIGURE + " " * 2000 + "x", FIGURE + " " * 8000 + "x")
        assert ratio < 8.0, (name, ratio, small, large)


CLAUSES = [
    "Output rose from 4.5 million in 1931 and 5.6 million in 1932, then 6 million in 1933.",
    "It was 3 million in 1929, and had reached 4 million in 1930 and then 5 million in 1931.",
    "Rainfall rose from 610 mm in 2019 to 640, 655, 690 and 720 mm in 2023.",
    "from 610 mm in 2019 to 640 ,655 , 690  and   720 mm in 2023",
    "It fell from £30 in 1920 to £25 in 1921 , and £20 in 1922, and to £15 in 1923",
    "Unemployment was 1.2 million in 1929\tand 2.8 million in 1932.",
    "Exports of 10 tonnes in 1900 , and 20 tonnes in 1910 and about 30 tonnes in 1920.",
    "The count was 5 in 2019 ,and 6 in 2020; then 7 in 2021 and so on.",
    "In 1919 it was 45 000, and 50 000 in 1920 and 55 000 in 1921.",
    "Prices rose to 12% in 2020 and stood at 9% in 2021, and 8% in 2022.",
    "6 in 2020 , , and 7 in 2021",
    "5 in 2019 and 6 in 2020",
    "5 in 2019 and",
    "",
]


def _random_clauses(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    pieces = ["5", "6.5", "1 000", "45 000", "£30", "about 7", "million", "tonnes", "%", "in 2019", "in 2020", "by 1932", " ", "  ", "\t", " ", ",",
              ", ", " and ", "and", "then", "to", "had", "reached", "rose to", "was", "x", ".", ";"]
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randrange(0, 18))) for _ in range(n)]


def _norm(m):
    return None if m is None else (m.span(), m.groupdict())


def test_every_list_is_read_as_before():
    texts = CLAUSES + _random_clauses(4000, seed=43)
    for s in texts:
        for name, new, old, how in PATTERNS:
            if how == "scan":
                assert [_norm(m) for m in new.finditer(s)] == [_norm(m) for m in old.finditer(s)], (name, s)
            else:
                for i in range(len(s) + 1):
                    assert _norm(new.match(s, i)) == _norm(old.match(s, i)), (name, s, i)


def test_lists_are_still_read():
    m = quant._LIST_ITEM_RE.match(", and 5.6 million in 1932", 0)
    assert m and m.group("n3") == "5.6" and m.group("d3").strip() == "in 1932"
    m = quant._AND_DATED_RE.search("It was 3 million in 1929, and had reached 4 million in 1930.")
    assert m and (m.group("n1"), m.group("n2")) == ("3", "4")
    assert quant._UNDATED_ITEM_RE.match(" and 720 mm in 2023").group("n3") == "720"
    assert quant._LIST_ITEM_RE.match("  x") is None and quant._UNDATED_ITEM_RE.match(" , x") is None
