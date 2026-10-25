"""An accuracy mark closing a line of working ("A1", "(A1) M1 A1.") is read in linear time (``generic_parser.accuracy_marked``,
which the generic and STEM parsers call). The pattern it reproduces (``_ACCURACY_MARK_RE``), searched from every start,
was quadratic on a long run of white space or of marks that never reaches the end of the line: a STEM answer with 20,000
spaces in a sentence took more than 3 s to parse (handed over by the security fixes, parser-safety class)."""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.adapters.stem_specialist.parser import StemTextParser
from epinoic_logic.branches.generic_parser import _ACCURACY_MARK_RE, accuracy_marked

PIECES = [" ", "  ", "\t", " ", "(", ")", "A", "M", "R", "N", "G", "AG", "1", "2", "12", "٣", ".", ";", ",", "x", "A1", "(A1)", "M1", "b"]


def test_the_reader_gives_the_patterns_answer_on_every_shape():
    rng = random.Random(17)
    for _ in range(60_000):
        s = "".join(rng.choice(PIECES) for _ in range(rng.randint(0, 12)))
        assert accuracy_marked(s) is (_ACCURACY_MARK_RE.search(s) is not None), repr(s)


@pytest.mark.parametrize("line, marked", [("x = 3   A1", True), ("x = 3 (A1)", True), ("x = 3 (A1) M1 A1.", True), ("x = 3\tA1", True),
                                          ("x  A12 AG", True), ("x = 3 A1", False), ("x  A123", False), ("A1 is the cell", False)])
def test_marks_are_read_as_before(line, marked):
    assert accuracy_marked(line) is marked is (_ACCURACY_MARK_RE.search(line) is not None)


@pytest.mark.parametrize("line", [" " * 200_000 + "x", "(A1)" * 50_000 + "((", "  A1" * 50_000 + "((", "a" + " " * 200_000 + "(A"])
def test_the_reader_is_linear_on_adversarial_lines(line):
    t = time.perf_counter()
    accuracy_marked(line)
    assert time.perf_counter() - t < 2.0


def test_a_stem_answer_with_a_long_white_space_run_is_parsed_quickly():
    text = "The mass is" + " " * 20_000 + "m = 2.0 kg and the speed is 3.0 m s-1."
    parser = StemTextParser(agent_id="physics-specialist")
    t = time.perf_counter()
    report = parser.parse_response(text, request_id="q", task_id="t", report_id="r", subject="Physics", task_type="structured_question",
                                   agent_id="physics-specialist", request_text="Find the kinetic energy.")
    assert time.perf_counter() - t < 2.0 and report.claims
