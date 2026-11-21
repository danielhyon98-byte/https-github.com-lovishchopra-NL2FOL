"""The reader is linear in the input length (design 2.9; not a stress test, no ``stress`` marker): for each hostile family at 8 KiB
and 32 KiB the time grows at most six-fold and the 32 KiB reading stays under 1.5 s (the median of five runs, caches emptied)."""
from __future__ import annotations

import pytest

from epinoic_logic.selfcert import read

from ..timing import measure

FAMILIES = {
    "letter-spaced": lambda n: ("V E R I F I E D " * (n // 16 + 1))[:n],
    "hyphens": lambda n: "-" * n,
    "quotation marks": lambda n: '"' * n,
    "nested parentheses": lambda n: "(" * (n // 2) + ")" * (n // 2),
    "one long token": lambda n: "a" * n,
    "alternating scripts": lambda n: ("αβγ абв " * (n // 8 + 1))[:n],
    "combining marks": lambda n: ("a" + "́" * 50) * (n // 51 + 1),
    "zero-width": lambda n: "a​" * (n // 2),
    "no punctuation": lambda n: ("the figures above were checked and " * (n // 35 + 1))[:n],
    "repeated not": lambda n: ("not " * (n // 4 + 1))[:n],
    # a line of thousands of mark codes: every bracket is a piece whose host line was read again per bracket (the round-10
    # stall class; 20,000 characters took tens of seconds before the per-line reading)
    "mark codes on one line": lambda n: "x = 5" + " (A1)" * (n // 5) + " z",
    "mark codes after prose": lambda n: "The price rose" + " (A1)" * (n // 5) + " x",
    "unclosed brackets": lambda n: "(a " * (n // 3),
    # a run of label keys in one sentence: a label inside a label's value was read once per key on the remainder (quadratic)
    "a run of label keys": lambda n: " ".join(['{"a": 1, "b": ['] * (n // 16)),
    # runs of line breaks inside one piece: the blank-line sentence end stripped a growing slice of the run per break (quadratic)
    "a run of line breaks": lambda n: "It is 5 m; " + "\n" * n + "x.",
    "a run of CRLF breaks": lambda n: "It is 5 m; " + "\r\n" * (n // 2) + "x.",
}


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_a_hostile_input_is_read_in_linear_time(family):
    make = FAMILIES[family]
    read("warm up the lexicon")
    small = measure(lambda: read(make(8 * 1024) + " "), 1.5, label=f"{family} at 8 KiB")
    large = measure(lambda: read(make(32 * 1024) + " "), 1.5, label=f"{family} at 32 KiB")
    assert large.holds, large
    ratio = (sorted(large.wall)[len(large.wall) // 2]) / max(sorted(small.wall)[len(small.wall) // 2], 0.05)  # a floor: times under 50 ms are noise
    assert ratio <= 6, (family, ratio, small, large)
