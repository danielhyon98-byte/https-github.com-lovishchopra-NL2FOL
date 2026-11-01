"""The standard hostile inputs of the integration gate 2 sweep for the core packages (channel, integrity, translate, engine,
ir, service, cli), as data, and the CPU-time sweep the per-module sweep tests run. Nothing here is evaluated.

Each input is a run of about 20,000 characters of one shape the readers' patterns scan, followed by a character that
defeats a match: blanks, tabs, line breaks, stops, closing marks, mark labels such as (A1), parentheses, brackets, fence
openers, number words joined by 'and', '=' links and list markers, and the shapes the sweep found (a run of digits joined
by dashes, unclosed brackets and LaTeX groups, relative clauses opened by commas; integration gate 3: formula constants
"× 10", figures in scientific notation, number words before small counts). ``PREFIXED`` puts the runs after words that
bring a reader into the state that reads them (a sentence end, a figure, a name, a hedge, a credit; integration gate 3: a
postposed "approximately", an unclosed mark annotation "[1", a comparison "more", a note label, a ratio word "per").

Integration gate 3: each sweep test is parametrized over the shapes (:data:`SHAPES`, one test per shape, :func:`one`), so a
test makes a few dozen calls and the suite's wall-clock timeout per test (``pyproject.toml``, 120 s) never decides a sweep on
a loaded machine: the per-call CPU-time bound does, unchanged.

A quadratic reader takes seconds to hours on 20,000 characters and a regular-expression blow-up longer; a linear one takes
milliseconds. The sweep asserts a CPU-time bound per call far above the linear time (so a loaded machine does not fail it)
and far below the quadratic one, and empties the package's memoisation caches before each call, so every call is a first
reading of its text.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

from .timing import empty_caches

N = 20_000

HOSTILE: dict[str, str] = {
    "blanks": " " * N + "x",
    "tabs": "\t" * N + "x",
    "line breaks": "\n" * N + "x",
    "blank lines": "\n \n" * (N // 3) + "x",
    "stops": "." * N + "x",
    "stops and blanks": ". " * (N // 2) + "x",
    "closing marks": ")\"”’]»" * (N // 6) + "x",
    "mark labels": "x = 5" + " (A1)" * (N // 5) + " z",
    "parentheses": "(" * N + "x",
    "brackets": "[" * N + "x",
    "braces": "{" * N + "x",
    "fence openers": "```a\n" * (N // 5) + "x",
    "number words joined by and": "one and " * (N // 8) + "x",
    "= links": "x = " * (N // 4) + "!",
    "list markers": "\n1. " * (N // 4) + "x",
    "commas": ", " * (N // 2) + "x",
    "relative clauses": ", which x" * (N // 9) + " 1990.",
    "dashed digits": "1–2–" * (N // 4) + "x",
    "latex groups": "\\frac{" * (N // 6) + "x",
    "dollar signs": "$a " * (N // 3) + "x",
    "quotation marks": '"a ' * (N // 3) + "x",
    # integration gate 3: a claim of formula constants (the ledger read its incidental figures again for every figure),
    # figures in scientific notation and number words around small counts (a reader blanked or checked them per figure)
    "formula constants": "× 10" * (N // 4) + "x",
    "scientific figures": "2 × 10³ " * (N // 8) + "x",
    "number words and counts": "twelve under nine " * (N // 18) + "x",
}

#: Words that bring a reader into the state that reads the run after them.
PREFIXES: dict[str, str] = {
    "after a sentence": "The value is 5 m. ",
    "after a figure": "In 1990 the total was 5",
    "after a name": "The Factory Act of 1833",
    "after a hedge": "Inflation may have",
    "after a credit": "Historians agree that",
    # integration gate 3: the states the gate-3 findings and their class sweep read a blank run in
    "after a postposed approximation": "The population was 30 approximately",
    "after an unclosed mark": "(a) Find x. [1",
    "after a comparison": "Inflation hurt savers more",
    "after a note label": "Note",
    "after a ratio word": "It rose by 5 per",
}
PREFIXED_RUNS = ("blanks", "line breaks", "stops", "closing marks", "parentheses", "relative clauses", "dashed digits")


def inputs() -> dict[str, str]:
    """The standard runs and the prefixed ones."""
    out = dict(HOSTILE)
    for where, words in PREFIXES.items():
        for run in PREFIXED_RUNS:
            out[f"{run} {where}"] = words + HOSTILE[run]
    return out


#: Every hostile input by its shape, built once.
INPUTS: dict[str, str] = inputs()
#: The shapes a sweep test is parametrized over (``@pytest.mark.parametrize("shape", SHAPES)``).
SHAPES: tuple[str, ...] = tuple(INPUTS)


def one(shape: str, texts: dict[str, str] | None = None) -> dict[str, str]:
    """The one hostile input of ``shape`` (from ``texts``, default :data:`INPUTS`), as the ``texts`` a sweep reads."""
    return {shape: (INPUTS if texts is None else texts)[shape]}


#: CPU seconds one call of a reader may take on one 20,000-character input: linear readers take milliseconds to a few
#: tenths of a second (the slowest measured, the ledger's figure-pairing reader, about 0.45 s); a quadratic scan of the
#: same input takes seconds to minutes.
BOUND = 4.0


def sweep(entries: Callable[[str], Iterable[tuple[str, Callable[[], object]]]], *, bound: float = BOUND,
          refusals: tuple[type[BaseException], ...] = (ValueError,), texts: dict[str, str] | None = None) -> list[tuple[str, str, float]]:
    """Run every entry point ``entries(text)`` names on every hostile text and return ``(entry, shape, CPU seconds)`` for
    each call over ``bound``. An exception of ``refusals`` is a refusal of hostile input, which is allowed (it fails
    loudly); any other exception propagates (a crash is a bug the sweep reports)."""
    slow: list[tuple[str, str, float]] = []
    for shape, text in (texts or inputs()).items():
        for name, call in entries(text):
            empty_caches()
            c0 = time.process_time()
            try:
                call()
            except refusals:
                pass
            spent = time.process_time() - c0
            if spent > bound:
                slow.append((name, shape, round(spent, 2)))
    return slow
