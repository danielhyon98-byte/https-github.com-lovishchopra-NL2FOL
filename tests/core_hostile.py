"""The standard hostile inputs of the integration gate 2 sweep for the core packages (channel, integrity, translate, engine,
ir, service, cli), as data, and the CPU-time sweep the per-module sweep tests run. Nothing here is evaluated.

Each input is a run of about 20,000 characters of one shape the readers' patterns scan, followed by a character that
defeats a match: blanks, tabs, line breaks, stops, closing marks, mark labels such as (A1), parentheses, brackets, fence
openers, number words joined by 'and', '=' links and list markers, and the shapes the sweep found (a run of digits joined
by dashes, unclosed brackets and LaTeX groups, relative clauses opened by commas). ``PREFIXED`` puts the runs after words
that bring a reader into the state that reads them (a sentence end, a figure, a name, a hedge, a credit).

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
}

#: Words that bring a reader into the state that reads the run after them.
PREFIXES: dict[str, str] = {
    "after a sentence": "The value is 5 m. ",
    "after a figure": "In 1990 the total was 5",
    "after a name": "The Factory Act of 1833",
    "after a hedge": "Inflation may have",
    "after a credit": "Historians agree that",
}
PREFIXED_RUNS = ("blanks", "line breaks", "stops", "closing marks", "parentheses", "relative clauses", "dashed digits")


def inputs() -> dict[str, str]:
    """The standard runs and the prefixed ones."""
    out = dict(HOSTILE)
    for where, words in PREFIXES.items():
        for run in PREFIXED_RUNS:
            out[f"{run} {where}"] = words + HOSTILE[run]
    return out


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
