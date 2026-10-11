"""The Z3 memory limit is process-global while ``memory_max_mb`` is a per-verification
budget: under concurrency the engine scales the limit by the number of verifications
running at once and never lowers it while any runs (lowering it under load made Z3 abort
and the next solver call segfault the process, found by the arena stress harness)."""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine import procedures as P


@pytest.fixture
def recorded(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(P.z3, "set_param", lambda name, value: calls.append(int(value)))
    monkeypatch.setattr(P, "_applied_memory_mb", None)
    monkeypatch.setattr(P, "_active_verifications", 0)
    return calls


def test_limit_scales_with_active_verifications_and_only_falls_when_idle(recorded):
    cfg = SolverConfig(memory_max_mb=512)
    P.apply_global_memory_limit(cfg)
    P.apply_global_memory_limit(cfg)
    P.apply_global_memory_limit(cfg)
    assert recorded == [512, 1024, 1536] and P.active_verifications() == 3
    P.release_global_memory_limit(cfg)
    P.release_global_memory_limit(cfg)
    assert recorded == [512, 1024, 1536]  # two still running: the limit is not lowered under load
    P.release_global_memory_limit(cfg)
    assert recorded[-1] == 512 and P.active_verifications() == 0


def test_unlimited_callers_are_counted_so_colleagues_budgets_scale(recorded):
    P.apply_global_memory_limit(SolverConfig(memory_max_mb=None))
    P.apply_global_memory_limit(SolverConfig(memory_max_mb=512))
    assert recorded == [1024]
    P.release_global_memory_limit(SolverConfig(memory_max_mb=512))
    P.release_global_memory_limit(SolverConfig(memory_max_mb=None))
    assert P.active_verifications() == 0


def test_reset_after_a_memory_abort_never_goes_below_the_running_need(recorded):
    cfg = SolverConfig(memory_max_mb=512)
    for _ in range(4):
        P.apply_global_memory_limit(cfg)
    P.reset_global_memory_limit()
    assert recorded[-1] >= 4 * P.DEFAULT_MEMORY_MB
    for _ in range(4):
        P.release_global_memory_limit(cfg)


def test_floor_applies_per_verification(recorded):
    P.apply_global_memory_limit(SolverConfig(memory_max_mb=128))
    assert recorded == [P.MEMORY_FLOOR_MB]
    P.release_global_memory_limit(SolverConfig(memory_max_mb=128))


@pytest.mark.stress
def test_default_budget_survives_thirty_two_concurrent_verifications():
    """Run in a subprocess: the failure mode is a segmentation fault, not an exception."""
    script = textwrap.dedent("""
        from concurrent.futures import ThreadPoolExecutor
        from epinoic_logic.engine import SolverConfig, verify
        cfg = SolverConfig(timeout_ms=2000)  # default per-verification budget
        problem = {"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                   "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}],
                   "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "y"}}},
                                {"id": "P2", "expr": {"op": "gt", "left": {"op": "var", "name": "y"}, "right": {"op": "var", "name": "z"}}}],
                   "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "z"}}}}
        with ThreadPoolExecutor(max_workers=32) as pool:
            statuses = list(pool.map(lambda _: verify(problem, cfg, signing_key=b"k" * 32, key_id="t").status.value, range(400)))
        assert statuses.count("ENTAILED") == 400, statuses
        print("ok")
    """)
    proc = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0 and "ok" in proc.stdout, (proc.returncode, proc.stderr[-2000:])
