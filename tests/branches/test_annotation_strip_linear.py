"""Markscheme annotations closing a line ("[2]", "(3 marks)", "  M1", "(A1)") are stripped in linear time
(``generic_parser._strip_annotations``). The pattern it reproduces (``_TRAILING_ANNOTATION_RE``), substituted over the
whole line, was quadratic on a long run of white space inside a sentence: an Economics answer with 20,000 tabs between
two sentences took 17 s to receive (parser-safety-3, the generic branch parser that serves the generic subjects)."""
from __future__ import annotations

import random
import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import _TRAILING_ANNOTATION_RE, _strip_annotations
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

PIECES = [" ", "  ", "\t", "\n", " ", "(", ")", "[", "]", "A", "M", "R", "N", "G", "AG", "1", "2", "12", "123", "٣", ".", ";",
          ",", "x", "A1", "(A1)", "M1", "b", "marks", "mark", "spare", " marks", "[2]", "[1 spare]", "(3 marks)", "(M1)", "  M1",
          "\tA2", "[ 2 ]", "( 3 mark )"]


def test_the_reader_gives_the_patterns_answer_on_every_shape():
    rng = random.Random(23)
    for _ in range(80_000):
        s = "".join(rng.choice(PIECES) for _ in range(rng.randint(0, 14)))
        assert _strip_annotations(s) == _TRAILING_ANNOTATION_RE.sub("", s).rstrip(), repr(s)


@pytest.mark.parametrize("line, stripped", [
    ("x = 5 [2]", "x = 5"), ("x = 5 [2].", "x = 5."), ("x = 5 [1 spare] [2 marks]", "x = 5"), ("x = 5 (3 marks);", "x = 5;"),
    ("x = 5  M1  A1", "x = 5"), ("x = 5\tA1", "x = 5"), ("x = 5 (M1)(A1)", "x = 5"), ("x = 5  AG  ", "x = 5"),
    # Clean controls: the same marks not closing the line, or not set off as the pattern requires, stay.
    ("x = 5 M1", "x = 5 M1"), ("x = 5  M1 A1", "x = 5  M1 A1"), ("x = 5 [2] .", "x = 5 [2] ."), ("[2] is the second item", "[2] is the second item"),
    ("x = 5  M123", "x = 5  M123"), ("The value is 5 m.  It is 6 m.", "The value is 5 m.  It is 6 m."),
])
def test_annotations_are_stripped_as_before(line, stripped):
    assert _strip_annotations(line) == stripped == _TRAILING_ANNOTATION_RE.sub("", line).rstrip()


@pytest.mark.parametrize("line", [
    "The value is 5 m." + " " * 50_000 + "It is 6 m.", "x" + "\t" * 50_000 + "y", "a" + " " * 50_000 + "[2",
    "[2]" * 20_000 + "x", "  M1" * 15_000 + "((", " " * 50_000,
])
def test_the_reader_is_linear_on_adversarial_lines(line):
    t = time.perf_counter()
    _strip_annotations(line)
    assert time.perf_counter() - t < 2.0


def test_an_economics_answer_with_a_long_white_space_run_is_received_quickly():
    text = "The value is 5 m." + "\t" * 20_000 + "It is 6 m."
    hub = RouterHub(signing_key=b"parser-safety-key-0123456789abcdef", key_id="k", config=SolverConfig(timeout_ms=5000, memory_max_mb=None))
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Economics", task_type="short_answer",
                           selected_agent_ids=["economics-specialist"]))
    message, _r, _c = hub.dispatch("t", "economics-specialist", "Answer the question.")
    t = time.perf_counter()
    _reply, receipt = hub.receive("t", message.message_id, text, agent_id="economics-specialist", report_id="r1")
    assert time.perf_counter() - t < 5.0 and receipt.status.value != "VERIFIED"
