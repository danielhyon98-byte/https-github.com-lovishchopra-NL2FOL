"""Regression tests of the prose-arithmetic and core-pack findings of the rerun lens review: bounded work on adversarial
answers (number words, digit runs, '=' chains), no mantissa read alone, no chronology cue paired across a quoted sentence.
"""
from __future__ import annotations

import re
import time

import pytest

from epinoic_logic.branches import RouterHub, quant as q
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"lens-c-branch-key-0123456789abcdef0123"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)


def _send(subject: str, agent: str, request: str, answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rq = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


# ------------------------------------------------------------------ parser-safety-2, 7, 8, 12: linear on adversarial runs


@pytest.mark.parametrize("label,fn", [
    ("total pattern, number words joined by 'and'", lambda: q._TOTAL_RE.search("one hundred and " * 1250)),
    ("SI total pattern, number words", lambda: q._si_patterns().total.search("one hundred and " * 1250)),
    ("pairs, a run of number words", lambda: q._pairs("twenty-three " * 1538)),
    ("pairs (SI), a run of number words", lambda: q._pairs("twenty-three " * 1538, q._si_patterns())),
    ("SI total pattern, a binary digit run", lambda: q._si_patterns().total.search("0b" + "1" * 20000)),
    ("SI total pattern, a decimal digit run", lambda: q._si_patterns().total.search("x " + "1" * 20000)),
    ("worked equations, a long '=' chain", lambda: q.worked_equations("= 1 " * 5000)),
])
def test_the_prose_arithmetic_patterns_stay_linear(label, fn):
    assert _timed(fn) < 5.0, label   # 20,000 characters: tens of seconds to minutes before the fix


def test_number_words_still_read_as_numbers():
    for words in ("two hundred and sixty", "forty-five", "one hundred", "nineteen hundred", "nine hundred and ninety-nine"):
        assert re.fullmatch(q._WNUM, words), words
    # 'and' joins a number only after 'hundred': 'between one and two' is two figures
    m = re.match(q._WNUM, "one and two")
    assert m is not None and m.group(0) == "one"


def test_worked_equations_keep_their_reading():
    assert [e.phrase for e in q.worked_equations("$6,000 ÷ $2.00 = 3,000 loaves")] == ["$6,000 ÷ $2.00 = 3,000 loaves"]
    assert [e.phrase for e in q.worked_equations("Dependency ratio = (22 + 9) ÷ 69 × 100\n= 31 ÷ 69 × 100\n= 44.9")] == \
        ["(22 + 9) ÷ 69 × 100 = 31 ÷ 69 × 100 = 44.9"]


# ------------------------------------------------------------------ parser-safety-13: scientific notation in the general reading


@pytest.mark.parametrize("answer", ["Output rose from 500 tonnes to 2.5e3 tonnes between 1990 and 2000.",
                                    "Output rose from 500 tonnes to 2.5 × 10³ tonnes between 1990 and 2000.",
                                    "It rose from 5 to 1e9 between 1990 and 2000."])
def test_ps13_a_figure_in_scientific_notation_is_never_read_by_its_mantissa(answer):
    rc = _send("Economics", "economics-specialist", "Describe the change in output.", answer)
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"]


def test_ps13_control_a_plain_figure_pair_is_still_decided():
    rc = _send("Economics", "economics-specialist", "Describe the change in output.", "Output fell from 500 tonnes to 2500 tonnes between 1990 and 2000.")
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001" and "pair_direction" in f.message]


# ------------------------------------------------------------------ robustness-and-contracts-7: chronology inside a quotation


@pytest.mark.parametrize("answer", [
    '"The crash of 1929 came after a speculative boom. Banks failed in 1930 and 1931."',
    "“The crash of 1929 came after a speculative boom. Banks failed in 1930 and 1931.”",
    '{"answer": "The 1929 crash followed speculative buying on margin. Banks failed in 1930 and 1931."}',
])
def test_rc7_a_quoted_or_json_wrapped_answer_pairs_no_cue_across_its_sentences(answer):
    rc = _send("History", "history-specialist", "Explain the causes of the Great Depression.", answer)
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"]


def test_rc7_control_a_wrong_order_inside_one_quoted_sentence_still_fails():
    rc = _send("History", "history-specialist", "Explain the causes of the Great Depression.", '"The crash of 1929 came after the bank failures of 1930."')
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001" and "chronology" in f.message]
