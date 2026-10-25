"""Word-bound scopes are read in linear time (repair of the argument-diagnosis integration, invariants INV-1 and INV-2).

The scope reader of a word bound (``channel.request_parser.bound_scope``) once matched its "for the answer" and part-label
patterns on the raw request: ``\\s*[,)]?\\s*`` backtracked quadratically over a run of whitespace after a bound, and the
label-gap pattern, five optional whitespace quantifiers in a row, cubically over a run before one. It also cut the whole
request into sentences and parts again for every bound, so a request stating thousands of bounds took quadratic time. A
request may hold 400,000 characters (``channel.contracts``), so one hostile request could stall the router.

Now the sentences, the parts and the request with its whitespace runs collapsed are computed once per request
(``_ScopeIndex``), each bound reads a bounded window of the collapsed text and binary searches, and every label gap is
collapsed before it is matched. The scope patterns read a run of whitespace of any length as one gap, so ordinary scopes
are unchanged: pinned below, and checked against the previous reader over 4,446 requests when the change was made.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.channel.request_parser import bound_scope, collapse_whitespace, extract_constraints


def _scopes(text: str) -> list[tuple[str, str, str | None, list[str]]]:
    return [(c.kind, c.value, c.scope.kind if c.scope else None, list(c.scope.parts) if c.scope else []) for c in extract_constraints(text)]


@pytest.mark.parametrize("n", [80_000, 400_000])
def test_a_whitespace_run_after_a_bound_is_read_in_linear_time(n):
    start = time.perf_counter()
    assert _scopes("Answer in max 100 words" + " " * n + "x.") == [("max_words", "100", None, [])]
    assert _scopes("Answer in max 100 words" + "\t \n" * (n // 3) + "for the answer.") == [("max_words", "100", "answer_proper", [])]
    assert time.perf_counter() - start < 2.0


def test_a_whitespace_run_before_a_bound_is_read_in_linear_time():
    request = "Answer the question. " + ("(a)" + " " * 112 + "x under 150 words. ") * 2000  # about 270,000 characters
    start = time.perf_counter()
    found = extract_constraints(request)
    assert time.perf_counter() - start < 3.0
    assert found and all(c.scope is not None and c.scope.kind == "part" and c.scope.parts == ["a"] for c in found)


def test_thousands_of_bounds_are_read_in_linear_time():
    start = time.perf_counter()
    extract_constraints("Answer in max 5 words. " * 16_000)  # 368,000 characters, 16,000 bounds
    extract_constraints("5 words max. " * 20_000)  # bounds written after their number: the overlap test
    assert time.perf_counter() - start < 4.0


@pytest.mark.parametrize("request_text, expected", [
    ("Answer (e) under 150 words.", [("max_words", "150", "part", ["e"])]),
    ("(e) and (f) under 120 words each.", [("max_words", "120", "each_part", ["e", "f"])]),
    ("(e)   should   be   under   150 words.", [("max_words", "150", "part", ["e"])]),
    ("(e) [4]\n(150 words max)", [("max_words", "150", "part", ["e"])]),
    ("Write about the poem in no more than 500 words in total.", [("max_words", "500", None, [])]),
    ("Max 400 words for the answer, plus a plan.", [("max_words", "400", "answer_proper", [])]),
    ("Max 400 words for the answer plan.", [("max_words", "400", None, [])]),
    ("The answer should be no more than 300 words.", [("max_words", "300", "answer_proper", [])]),
    ("Write ONE body paragraph (max 300 words).", [("max_words", "300", "paragraph", [])]),
    ("(a) Explain the cause (100 words max). (b) Evaluate it.", [("max_words", "100", "part", ["a"])]),
])
def test_ordinary_scopes_read_as_before(request_text, expected):
    got = _scopes(request_text)
    for item in expected:
        assert item in got


def test_collapse_whitespace_writes_each_run_as_one_space():
    assert collapse_whitespace("a  \n\t b\n\nc") == "a b c"
    text = "Keep (e)\n\n   under 150 words."
    start = text.index("under")
    scope = bound_scope(text, start, start + len("under 150 words"))
    assert scope is not None and scope.kind == "part" and scope.parts == ["e"]
