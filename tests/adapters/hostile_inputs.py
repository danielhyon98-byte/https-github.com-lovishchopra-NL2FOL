"""The standard hostile inputs of the integration gate 2 sweep (data only; nothing here is evaluated).

Each is a run of about 20,000 characters of one shape the readers' patterns scan, followed by a character that defeats a match, so a
reader that rescans the run from each of its characters, or splits it between adjacent runs, shows it in the time it takes: blanks,
tabs, line breaks, stops, closing marks, mark labels such as (A1), parentheses, brackets, fence openers, number words joined by 'and',
'=' links and list markers. ``PREFIXED`` puts a few of them after the words that bring a reader into the state that reads them (an
ordering cue, a dated pair of figures, a quotation, the synthesis as a subject, a sentence end).

``bounded(fn, text)`` runs one call and returns its wall-clock time and any exception; the sweep tests assert every call of every public entry
point stays under a bound far above what a linear reader takes (a few hundredths of a second), so a load on the machine does not fail
them while a quadratic reader (seconds to hours at this size) does.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

N = 20_000

HOSTILE: dict[str, str] = {
    "blanks": " " * N + "x",
    "tabs": "\t" * N + "x",
    "line breaks": "\n" * N + "x",
    "blank lines": "\n \n" * (N // 3) + "x",
    "stops": "." * N + "x",
    "bangs": "!" * N + "x",
    "stops and blanks": ". " * (N // 2) + "x",
    "closing marks": ")\"”’]»" * (N // 6) + "x",
    "mark labels": " (A1)" * (N // 5) + " z",
    "bare mark labels": "  A1" * (N // 4) + " z",
    "parentheses": "(" * N + "x",
    "brackets": "[" * N + "x",
    "braces": "{" * N + "x",
    "fence openers": "```a\n" * (N // 5),
    "tilde fence openers": "~~~a\n" * (N // 5),
    "brace lines": "{x\n" * (N // 3),
    "number words joined by and": "one and " * (N // 8) + "x",
    "= links": "x = " * (N // 4) + "!",
    "list markers": "\n1. " * (N // 4) + "x",
    "inline list markers": "1. " * (N // 3) + "x",
    "hyphens": "-" * N + "x",
    "quotation marks": '"a ' * (N // 3),
    "curly quotation marks": "“a " * (N // 3),
}

#: Words that bring a reader into the state that reads the run after them.
PREFIXES: dict[str, str] = {
    "after a sentence": "The value is 5 m. ",
    "after an ordering cue": "The strike began in May 1921. The crisis followed",
    "after a dated pair": "Unemployment rose from 3 million in 1930 to 4.5 million in 1931",
    "after a share": "20 per cent of",
    "after a quotation's opening": 'The poem says "the bulbs lie under frost',
    "after the synthesis": "This synthesis",
}
#: The runs read after each prefix.
PREFIXED_RUNS = ("blanks", "tabs", "line breaks", "stops", "closing marks", "mark labels")


def prefixed() -> dict[str, str]:
    """Every run of :data:`PREFIXED_RUNS` after every prefix of :data:`PREFIXES`."""
    return {f"{run} {where}": words + HOSTILE[run] for where, words in PREFIXES.items() for run in PREFIXED_RUNS}


def all_inputs() -> dict[str, str]:
    """The standard runs and the prefixed ones."""
    return {**HOSTILE, **prefixed()}


def bounded(fn: Callable[[str], Any], text: str) -> tuple[float, Optional[BaseException]]:
    """``(wall-clock seconds, exception)`` of ``fn(text)``: the exception the call raised, or None. The caller asserts the time and
    which refusals are answers (an empty answer is an ``AdapterError``); any other exception is a crash the sweep reports."""
    t = time.perf_counter()
    error: Optional[BaseException] = None
    try:
        fn(text)
    except Exception as exc:  # noqa: BLE001 - returned to the caller, which decides whether it is a refusal or a crash
        error = exc
    return time.perf_counter() - t, error
