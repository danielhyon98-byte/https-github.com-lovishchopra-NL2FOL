"""Integration gate 1 (critical finding parser-safety-4): the shared sentence splitter (``history_specialist.sentences``), read by
the History, English and generic parsers, the quantitative reader and the STEM segmentation, ended a sentence with
``[.?!]+[closers]*(?=\\s+\\S)``. A run of stops not followed by whitespace and text ('x = 9!!!...!') was read again from each of
its stops: n² steps (9.24 s at 20,000 characters; the STEM front end 71 s at 80,000). The end is now read only from the first stop
of a run, with possessive runs: the same boundaries in linear time, for the sentence and the clause readings."""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.adapters.history_specialist import sentences as hs
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

from ..growth import growth
from ..timing import empty_caches

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
CLOSERS = "\"”’')\\]»"
OLD_END_RE = re.compile(rf"[.?!]+[{CLOSERS}]*(?=\s+\S)")
OLD_CLAUSE_END_RE = re.compile(rf"[.?!;]+[{CLOSERS}]*(?=\s+\S)")


def test_the_sentence_and_clause_ends_are_those_of_the_old_patterns():
    rng = random.Random(9)
    alphabet = [".", "!", "?", ";", '"', "”", "’", "'", ")", "]", "»", " ", "  ", "\t", "\n", "A", "b", "9", "x", "e.g.", "c."]
    for _ in range(30000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 20)))
        assert [m.span() for m in hs._END_RE.finditer(text)] == [m.span() for m in OLD_END_RE.finditer(text)], repr(text)
        assert [m.span() for m in hs._CLAUSE_END_RE.finditer(text)] == [m.span() for m in OLD_CLAUSE_END_RE.finditer(text)], repr(text)


@pytest.mark.parametrize("make", [
    lambda n: "x = 9" + "!" * n,              # the finding's input: a run that no text follows
    lambda n: "x = 9" + "?!." * (n // 3),
    lambda n: "x = 9" + ";" * n,
    lambda n: "x = 9" + "!" * n + " ok",      # a run that text follows (fast before the gate too)
])
def test_a_long_run_of_stops_is_read_in_linear_time(make):
    for semicolons in (False, True):
        t = time.perf_counter()
        hs.sentence_boundaries(make(400000), semicolons=semicolons, capital_next=not semicolons)
        assert time.perf_counter() - t < 2.0  # before the gate: 9.24 s at 20,000 characters
        ratio, small, large = growth(lambda text: hs.sentence_boundaries(text, semicolons=semicolons), make(20000), make(80000), clear=empty_caches)
        assert ratio < LINEAR, (ratio, small, large)
    assert hs.split_sentences("It rose. Then it fell!!! " + "!" * 50) == ["It rose.", "Then it fell!!! " + "!" * 50]


def test_the_stem_front_end_reads_a_run_of_stops_within_its_bound():
    from epinoic_logic.stem import build_document, clear_document_cache
    clear_document_cache()
    t = time.perf_counter()
    build_document("x = 9" + "!" * 80000, None, "physics")
    assert time.perf_counter() - t < 5.0  # before the gate: 71.39 s at 80,000 characters


def test_a_history_answer_ending_in_a_run_of_stops_crosses_the_hub_in_seconds():
    hub = RouterHub(signing_key=b"integration-gate-1-sentences-key-012345", key_id="k", config=SolverConfig(timeout_ms=8000, memory_max_mb=None))
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
    m, _, _ = hub.dispatch("t", "history-specialist", "Answer the question.")
    t = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, "x = 9" + "!" * 20000, agent_id="history-specialist", report_id="r1")
    assert time.perf_counter() - t < 10.0  # before the gate: over 45 s
    assert rc.status.value.startswith("ACCEPTED")
