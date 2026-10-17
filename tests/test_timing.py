"""The benchmark conditions of the suite's wall-clock bounds (tests/timing.py; review of 12 October 2026, sections 1 and 8).

The review: one full-suite run measured a bracket-heavy hub crossing at about 2.49 s against its 2 s bound, while the same
test met the bound on its own; keep the timing test visible and stabilise its benchmark conditions rather than relax it.
These tests hold the conditions to that: one disturbed run no longer fails a fast call (it did under the single-sample
rule), while a call that is slow on most runs still fails (negative controls), the verdict is exactly the median of all
the runs, every run starts with the package's caches empty and the earlier heap frozen, and the converted tests stay in the
default suite with their bounds unchanged.
"""
from __future__ import annotations

import gc
import importlib
import itertools
import statistics
import time

import pytest

from .timing import cache_entries, decided, empty_caches, measure

BOUND = 0.05  # seconds; the synthetic calls below sleep well clear of it on either side
SLOW, FAST = 0.12, 0.002


def _scripted(durations):
    """A call whose n-th run sleeps ``durations[n]`` (the last value repeats), and the list of runs made."""
    calls: list[int] = []

    def run():
        n = len(calls)
        calls.append(n)
        time.sleep(durations[min(n, len(durations) - 1)])
        return n
    return run, calls


def test_repeat_must_be_odd_so_the_median_is_one_of_the_runs():
    for repeat in (0, 2, 4, -1):
        with pytest.raises(ValueError):
            measure(lambda: None, BOUND, repeat=repeat)


def test_a_call_slow_on_every_run_fails_the_bound():
    """Negative control: stabilised conditions never pass a slow call."""
    run, calls = _scripted([SLOW])
    timing = measure(run, BOUND)
    assert not timing.holds and timing.under == 0 and len(timing.wall) == 3, timing
    assert "NOT under the 0.05 s bound" in str(timing)


def test_a_call_slow_on_a_majority_of_runs_fails_even_when_some_runs_are_fast():
    """Negative control: slow, fast, slow, fast, slow (after the warm-up) is a median over the bound."""
    run, _calls = _scripted([FAST, SLOW, FAST, SLOW, FAST, SLOW])
    timing = measure(run, BOUND)
    assert not timing.holds and len(timing.wall) == 5 and timing.under == 2, timing


def test_one_disturbed_run_no_longer_fails_a_fast_call():
    """The review's failure: one run disturbed (here the first measured run sleeps past the bound) while the call is fast.
    The single sample it replaces fails; the median of five does not."""
    run, _calls = _scripted([FAST, SLOW, FAST])  # warm-up, one disturbed run, then fast runs
    assert not measure(run, BOUND, repeat=1).holds, "the single-sample rule fails on the disturbed run"
    run, _calls = _scripted([FAST, SLOW, FAST])
    timing = measure(run, BOUND)
    assert timing.holds and timing.wall[0] >= BOUND and timing.under == 3 and len(timing.wall) == 4, timing


def test_the_early_decision_is_the_median_of_all_runs():
    """For every pattern of runs under or over the bound, stopping once the majority is decided gives the verdict of the
    median of all ``repeat`` runs."""
    for repeat in (1, 3, 5, 7):
        for pattern in itertools.product((True, False), repeat=repeat):
            walls = [BOUND / 2 if under else BOUND * 2 for under in pattern]
            verdict = None
            for taken in range(1, repeat + 1):
                verdict = decided(sum(pattern[:taken]), taken, repeat)
                if verdict is not None:
                    break
            assert verdict == (statistics.median(walls) < BOUND), (repeat, pattern)


def test_the_warm_up_runs_once_and_is_not_measured():
    run, calls = _scripted([FAST])
    timing = measure(run, BOUND)
    assert timing.results == (1, 2, 3) and calls == [0, 1, 2, 3], "run 0 is the warm-up; runs 1 to 3 are measured"
    assert "one unmeasured warm-up run first" in str(timing)
    run, calls = _scripted([FAST])
    cold = measure(run, BOUND, warmup=False)
    assert cold.results == (0, 1, 2) and "no warm-up run" in str(cold), "the report says when a test warmed the path itself"


def _hub_crossing():
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.integrity import WorkPlan
    hub = RouterHub(signing_key=b"timing-conditions-key-0123456789ab", config=SolverConfig(timeout_ms=3000, memory_max_mb=None))
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Physics", task_type="short_answer",
                           selected_agent_ids=["science-specialist", "dummy-combinator"], allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", "science-specialist", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.", [])
    return hub.receive("t", m.message_id, "Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻².",
                       agent_id="science-specialist", report_id="rep-x")


def test_every_measured_run_starts_with_the_package_caches_empty():
    """Each measured run is a first crossing: no sample is served from what the warm-up or an earlier run cached."""
    seen: list[int] = []

    def run():
        seen.append(cache_entries())
        return _hub_crossing()
    timing = measure(run, 30.0)
    assert len(seen) == 1 + len(timing.wall) and seen[1:] == [0] * len(timing.wall), seen
    assert cache_entries() > 0, "the crossing fills the caches the conditions empty"


def test_the_shared_pack_caches_are_among_those_emptied():
    """The STEM packs the branch registry shares between hubs keep a report cache; it is emptied with the rest (if it is
    renamed out of reach this test fails rather than the conditions silently weakening)."""
    from . import timing as conditions
    _hub_crossing()
    packs = conditions._shared_pack_caches()
    assert packs and any(len(cache) for _pack, _attr, cache in packs)
    assert empty_caches() >= len(packs) and all(len(cache) == 0 for _pack, _attr, cache in packs) and cache_entries() == 0


def test_the_earlier_heap_is_frozen_during_each_run_and_released_after():
    frozen: list[int] = []
    measure(lambda: frozen.append(gc.get_freeze_count()), BOUND * 20)
    assert len(frozen) == 4 and frozen[0] == 0 and all(n > 0 for n in frozen[1:]), frozen
    assert gc.get_freeze_count() == 0 and gc.isenabled()

    def boom():
        if gc.get_freeze_count():
            raise RuntimeError("raised inside a measured run")
    with pytest.raises(RuntimeError):
        measure(boom, BOUND)
    assert gc.get_freeze_count() == 0, "the heap is released whatever the measured call does"


#: The tests measured under these conditions: the review's test and its siblings. Their bounds are the bounds they had.
CONVERTED = [
    ("tests.branches.test_r5_quant_packs", "test_bracket_heavy_answers_cross_the_english_branch_quickly", 2.0),
    ("tests.adapters_history.test_r5_parser_roles_notes", "test_bracket_heavy_answers_cross_the_history_branch_quickly", 2.0),
    ("tests.adapters_history.test_r5_parser_roles_notes", "test_strip_json_spans_is_linear_and_agrees_with_a_stack_scan", 1.0),
    ("tests.adapters.test_overseer_round4", "test_brace_like_text_is_scanned_in_linear_time", 1.0),
    ("tests.adapters.test_overseer_round5", "test_the_structural_rule_reads_pathological_text_in_linear_time", 2.0),
    ("tests.adapters.test_overseer_round6", "test_the_new_rules_read_pathological_text_in_linear_time", 2.0),
    ("tests.branches.test_r6_chronology_quant_hub", "test_formal_checks_are_capped_and_the_rest_reported", 10),
]


@pytest.mark.parametrize("module, name, bound", CONVERTED, ids=[name for _m, name, _b in CONVERTED])
def test_the_measured_tests_stay_visible_with_their_bounds(module, name, bound):
    """Kept visible: each measured test is in the default suite (no stress, skip or xfail mark) and asserts its original
    bound through the conditions, never a relaxed one."""
    import inspect
    func = getattr(importlib.import_module(module), name)
    marks = {m.name for m in getattr(func, "pytestmark", [])}
    assert not marks & {"stress", "skip", "skipif", "xfail"}, marks
    source = inspect.getsource(func)
    assert "measure(" in source and f"bound={bound}" in source and "assert timing.holds, timing" in source
