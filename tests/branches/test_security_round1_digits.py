"""Security round 1, SEC-1: the figure reader's space-grouped thousands are read in linear time (``quant._DIGITS``).

Repair round 4 (rerun-parser-safety-13) read thousands grouped by a space ('45 000', '1 800 000') as one figure with the
alternative ``\\d{1,3}(?:[ ]\\d{3})+`` (any of four space characters). Each group of a long run is preceded by a space, so
it passed the figure's guard against starting inside a digit run and became a new match start that read the run again to
its end: reading figures was quadratic on a run of space-grouped digits, and every branch's prose-arithmetic reading
(``undecided_quant_statements``) holds the hub for tens of seconds on a hostile answer (' 000' repeated 8,000 times: 13 s
against the base's 1.0 s). A group that follows two groups of three digits of its run no longer starts a space-grouped
figure: the figure from there reads the same groups to the same end as the figure from the group before, which every scan
has already tried. These tests pin the growth of the reading and that every figure is read as before.
"""
from __future__ import annotations

import random
import re

from epinoic_logic.branches import quant

from ..growth import growth

BS = chr(92)
SEP = "[ " + BS + "u00a0" + BS + "u2009" + BS + "u202f]"
#: The guard this round added to the space-grouped alternative; the patterns without it are the ones before the round.
GUARD = "(?!(?<=" + SEP + BS + "d{3}" + SEP + BS + "d{3}" + SEP + ")" + BS + "d{3})"
SPACES = (" ", " ", " ", " ")


def _patterns():
    """Every compiled pattern of the module (and of its SI reading) built on the figure reader's digits."""
    out = []

    def add(name, value):
        if isinstance(value, re.Pattern):
            if quant._DIGITS in value.pattern:
                out.append((name, value))
        elif isinstance(value, tuple):
            for i, x in enumerate(value):
                add(f"{name}[{i}]", x)
    for name, value in vars(quant).items():
        add(name, value)
    add("_si_patterns()", tuple(quant._si_patterns()))
    return out


PATTERNS = _patterns()
OLD = {name: re.compile(p.pattern.replace(GUARD, ""), p.flags) for name, p in PATTERNS}


def test_the_guard_is_in_the_digits_reader_and_every_pattern_built_on_it():
    assert GUARD in quant._DIGITS
    assert len(PATTERNS) >= 30
    assert all(GUARD in p.pattern for _n, p in PATTERNS)


def _hostile(n: int, unit: str = " 000") -> str:
    return "The answer is clear. " + unit * n + " So the conclusion follows."


def _scan_all(text: str) -> int:
    hits = 0
    for _name, p in PATTERNS:
        hits += p.search(text) is not None
        hits += sum(1 for _m in p.finditer(text))
    return hits


def test_scanning_a_long_run_of_space_grouped_digits_grows_linearly():
    """Four times the run costs about four times as much (the alternative without the guard: about sixteen times)."""
    for unit in (" 000", " 000", " 123 456 789", " 000"):
        ratio, small, large = growth(_scan_all, _hostile(250, unit), _hostile(1000, unit))
        assert ratio < 8.0, (unit, ratio, small, large)


def test_the_prose_arithmetic_reading_of_a_hostile_answer_grows_linearly():
    """The reader every non-STEM branch's core pack runs on a report (``undecided_quant_statements``), on the answer the
    verification found: four times the run, about four times the cost."""
    ratio, small, large = growth(quant.undecided_quant_statements, _hostile(500), _hostile(2000), clear=quant._analyse.cache_clear)
    assert ratio < 8.0, (ratio, small, large)


def test_the_si_reading_of_a_hostile_answer_grows_linearly():
    ratio, small, large = growth(lambda t: quant.undecided_quant_statements(t, reading=quant.SI_READING), _hostile(500), _hostile(2000),
                                 clear=quant._analyse.cache_clear)
    assert ratio < 8.0, (ratio, small, large)


SENTENCES = [
    "Output rose from 30000 to 45 000 tonnes in 1923.",
    "The population grew from 1 800 000 in 1900 to 2 400 000 in 1910, a rise of 600 000.",
    "Unemployment fell from 3 100 000 to 2 400 000, a fall of 700 000 people.",
    "Prices rose by 12 per cent, from £450 000 to £504 000.",
    "Revenue was $1 250 000.50 in 2020 and $1 400 000 in 2021.",
    "The figure 1234 567 890 is not grouped at its head.",
    "Exports of 12 345 678 tonnes exceeded the target of 10 000 000 tonnes by 2 345 678 tonnes.",
    "The value is 3 349 800 584 083 after 889 138 and 1 000 000.",
    "It falls from $1.60 to $2.00 − $0.60 = 138 349 800 before rising to 140 000.",
    "In 2019 45 000 people moved, and 5 000 more in 2020.",
    "A total of 2 500 + 2 800 + 700 = 6 000 per month.",
    "The 12 000 seats and 3 500 votes, totalling 15 500, were counted.",
    "A rise from 1 000 000× 10³ to 2 000 000 is read in SI only.",
    "Of the 45 000 workers, 4 500 (10 per cent) were women.",
    "It doubled from 2 000 to 4 000, then rose further to 8 000 000 by 1990.",
    "123 456 789 012 345 678 901 234 567 890 is a long figure.",
    "Values: 1 000, 2 000, 3 000 and 4 000 in 1920, 1921, 1922 and 1923.",
    "The count 1 00 000 is grouped the Indian way and 10 0000 is not grouped.",
    "A run 000 000 000 000 000 000 000 000 000 000 000 000 ends here.",
    "The ratio changed by −45 000 per 1,000 people.",
    "1 000 1 000 1 000 1 000 alternate heads and groups.",
    "12 345 12 345 12 345 repeat a short chain.",
    "The 2.5 000 and 1,5 000 forms are not thousands.",
    "Spending of € 1 000 000 and US$ 2 000 000 was planned.",
]


def _random_texts(n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    words = ["rose", "fell", "from", "to", "and", "by", "of", "in 1923", "a rise of", "per cent", "%", "million", "people", "tonnes", "total",
             "totalling", "plus", "then", "before", "reaching", "short of", "exceeded", "out of", "times", "doubled", "=", "−", "+", ",",
             ".", "£", "$", "about", "nearly", "e3", "× 10³", "x7", "a12"]
    out = []
    for _ in range(n):
        toks = []
        for _ in range(rnd.randrange(3, 30)):
            if rnd.random() < 0.5:
                parts = [str(rnd.randrange(1, 1000 if rnd.random() < 0.7 else 100000))]
                for _ in range(rnd.choice([0, 1, 2, 3, 5])):
                    g = f"{rnd.randrange(0, 1000):03d}"
                    if rnd.random() < 0.08:
                        g = g[:rnd.choice([1, 2])] if rnd.random() < 0.5 else g + str(rnd.randrange(10))
                    parts.append(rnd.choice(SPACES) + g)
                toks.append("".join(parts) + ("." + str(rnd.randrange(100)) if rnd.random() < 0.1 else ""))
            else:
                toks.append(rnd.choice(words))
            toks.append(rnd.choice([" ", " ", "", ", ", " and "]))
        out.append("".join(toks))
    return out


def _starts(s: str) -> list[int]:
    """Where a reader starts an anchored match: not inside a run of digit chunks (the text before it, spaces aside, does
    not end in a digit), as after a name and its verb, after ',' or 'and'."""
    out = []
    for i in range(len(s) + 1):
        j = i
        while j > 0 and s[j - 1].isspace():
            j -= 1
        if j == 0 or not s[j - 1].isdigit():
            out.append(i)
    return out


def _head_ends(s: str) -> list[int]:
    """The ends of the heads of runs of space-separated digit chunks: where a reader that does not read space groups
    ('= 138 349', the expression-value reader) leaves the text for the next reader."""
    out = []
    for m in re.finditer(r"\d+", s):
        a, b = m.span()
        head = a < 2 or not (s[a - 1] in SPACES and s[a - 2].isdigit())
        if head and b < len(s) and s[b] in SPACES:
            out.append(b)
    return out


def _norm(m):
    return None if m is None else (m.span(), m.groups())


def test_every_figure_is_read_as_before():
    """Every pattern built on the digits finds the same matches, with the same groups, as before the guard: on whole
    texts (search and finditer), anchored at every start a reader leaves (after a word and the spaces after it), and
    scanning from the end of the head of a run, where the expression-value reader stops."""
    texts = SENTENCES + _random_texts(40, seed=11)
    compared = 0
    for s in texts:
        starts = _starts(s)
        heads = _head_ends(s)
        for name, new in PATTERNS:
            old = OLD[name]
            assert [_norm(m) for m in new.finditer(s)] == [_norm(m) for m in old.finditer(s)], (name, s)
            assert _norm(new.search(s)) == _norm(old.search(s)), (name, s)
            for i in starts:
                assert _norm(new.match(s, i)) == _norm(old.match(s, i)), (name, s, i)
            for i in heads:
                assert [_norm(m) for m in new.finditer(s, i)] == [_norm(m) for m in old.finditer(s, i)], (name, s, i)
            compared += 1
    assert compared == len(texts) * len(PATTERNS)


def test_space_grouped_figures_are_still_read_whole():
    """Clean controls of the reading the guard keeps: a grouped figure after a plain one, a long grouped figure, a run
    whose head is not a group, a figure after the head another reader took, and the checks they feed."""
    fig = quant._GENERAL_PATTERNS.figure
    assert [m.group("n9") for m in fig.finditer("from 30000 to 45 000 tonnes")] == ["30000", "45 000"]
    assert [m.group("n9") for m in fig.finditer("about 1 800 000 people")] == ["1 800 000"]
    assert [m.group("n9") for m in fig.finditer("the run 1234 567 890 here")] == ["1234", "567 890"]
    assert [m.group("n9") for m in fig.finditer("x 138 349 800 y", 5)] == ["349 800"]
    assert [m.group("n9") for m in fig.finditer("889 138 3 349 800 people")] == ["889", "138", "3 349 800"]
    checks = quant.extract_quant_checks("Output rose from 30 000 to 45 000 tonnes, a rise of 50 per cent.", request_id="r", claim_id="c")
    assert len(checks) == 1 and checks[0].kind == "percent_change"
