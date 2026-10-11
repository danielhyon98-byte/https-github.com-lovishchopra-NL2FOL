"""Layer 3 stress tests for the verification engine (run with: pytest -m stress tests/stress).

Severe-usage scenarios: sustained sequential load with latency percentiles and
resident-memory growth, threaded concurrency with result equality against the
sequential run, high-volume adversarial payloads at and beyond the limits,
bounded timeouts under concurrent load, and a mixed soak. Thresholds are
deliberately generous (shared CI hosts); they catch crashes, leaks and unbounded
latency, not micro-regressions. Numbers are written to tests/stress/results/.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S, is_definitive
from epinoic_logic.ir.schema import Limits, Problem

pytestmark = pytest.mark.stress
RESULTS_DIR = Path(__file__).parent / "results"
CFG = SolverConfig(timeout_ms=2000, memory_max_mb=None)


def rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return float("nan")


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100.0 * (len(xs) - 1))))]


def record(name: str, data: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))


def V(n): return {"op": "var", "name": n}
def I(v): return {"op": "int", "value": str(v)}
def cmp(op, l, r): return {"op": op, "left": l, "right": r}


def transitivity(i: int) -> Problem:
    return Problem.model_validate({
        "problem_id": f"p{i}", "request_id": f"r{i}", "claim_id": f"c{i}", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}],
        "premises": [{"id": "P1", "expr": cmp("gt", V("x"), V("y"))}, {"id": "P2", "expr": cmp("gt", V("y"), V("z"))}],
        "conclusion": {"id": "C", "expr": cmp("gt", V("x"), V("z"))},
    })


def argument_chain(i: int, broken: bool) -> Problem:
    prem = [
        {"id": "E1", "expr": V("q"), "grounding": {"kind": "quotation", "verified": True}},
        {"id": "L1", "expr": {"op": "implies", "left": V("q"), "right": V("d")}, "grounding": {"kind": "specialist_inference"}},
    ]
    if not broken:
        prem.append({"id": "L2", "expr": {"op": "implies", "left": V("d"), "right": V("p")}, "grounding": {"kind": "specialist_inference"}})
    return Problem.model_validate({
        "problem_id": f"a{i}", "request_id": f"r{i}", "claim_id": f"c{i}", "query": "entailment",
        "symbols": [{"name": "q", "sort": "Bool"}, {"name": "d", "sort": "Bool"}, {"name": "p", "sort": "Bool"}],
        "premises": prem, "conclusion": {"id": "C", "expr": V("p")},
    })


def hard_nonlinear(i: int) -> Problem:
    return Problem.model_validate({
        "problem_id": f"h{i}", "request_id": f"r{i}", "claim_id": f"c{i}", "query": "satisfiability",
        "symbols": [{"name": "a", "sort": "Int"}, {"name": "b", "sort": "Int"}, {"name": "c", "sort": "Int"}],
        "premises": [
            {"id": "P1", "expr": cmp("gt", V("a"), I(1))}, {"id": "P2", "expr": cmp("gt", V("b"), I(1))}, {"id": "P3", "expr": cmp("gt", V("c"), I(1))},
            {"id": "P4", "expr": cmp("eq", {"op": "add", "args": [{"op": "mul", "args": [V("a"), V("a"), V("a")]}, {"op": "mul", "args": [V("b"), V("b"), V("b")]}]}, {"op": "mul", "args": [V("c"), V("c"), V("c")]})},
            {"id": "P5", "expr": cmp("lt", V("c"), I(10 ** 12))},
        ],
    })


def test_sequential_throughput_and_memory_growth():
    n = 1000
    for i in range(20):
        verify(transitivity(i), CFG)
    rss_before = rss_mb()
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    t0 = time.perf_counter()
    for i in range(n):
        s = time.perf_counter()
        r = verify(transitivity(i), CFG)
        latencies.append((time.perf_counter() - s) * 1000.0)
        statuses[r.status.value] = statuses.get(r.status.value, 0) + 1
    wall = time.perf_counter() - t0
    rss_after = rss_mb()
    data = {"n": n, "throughput_per_s": n / wall, "p50_ms": pct(latencies, 50), "p95_ms": pct(latencies, 95), "p99_ms": pct(latencies, 99),
            "max_ms": max(latencies), "rss_before_mb": rss_before, "rss_after_mb": rss_after, "rss_growth_mb": rss_after - rss_before, "statuses": statuses}
    record("sequential", data)
    assert statuses == {"ENTAILED": n}, statuses
    assert data["p99_ms"] < 250.0, data
    assert data["rss_growth_mb"] < 80.0, data  # leak guard: 1000 fresh Z3 contexts must be released


def test_concurrent_threads_match_sequential():
    problems = [argument_chain(i, broken=(i % 3 == 0)) for i in range(240)]
    sequential = [(verify(p, CFG).status, verify(p, CFG).binding.binding_digest) for p in problems]
    with ThreadPoolExecutor(max_workers=16) as pool:
        concurrent = list(pool.map(lambda p: (lambda r: (r.status, r.binding.binding_digest))(verify(p, CFG)), problems))
    assert concurrent == sequential
    broken = [s for s, _ in concurrent if s is S.COUNTEREXAMPLE]
    entailed = [s for s, _ in concurrent if s is S.ENTAILED]
    assert len(broken) == 80 and len(entailed) == 160
    record("concurrency", {"problems": len(problems), "workers": 16, "equal_to_sequential": True})


def _adversarial_payloads() -> list[bytes]:
    out: list[bytes] = []
    base = '{"problem_id":"p","request_id":"r","claim_id":"c","query":"consistency","symbols":[{"name":"a","sort":"Bool"},{"name":"x","sort":"Int"}],"premises":[%s]}'
    for depth in (41, 500, 10_000):
        bomb = '{"op":"not","arg":' * depth + '{"op":"var","name":"a"}' + "}" * depth
        out.append((base % ('{"id":"P","expr":' + bomb + "}")).encode())
    wide = '{"op":"and","args":[' + ",".join(['{"op":"var","name":"a"}'] * 5000) + "]}"
    out.append((base % ('{"id":"P","expr":' + wide + "}")).encode())
    out.append((base % ('{"id":"P","expr":{"op":"exec","code":"import os"}}')).encode())
    out.append((base % ('{"id":"P","expr":{"op":"gt","left":{"op":"var","name":"x"},"right":{"op":"int","value":"%s"}}}' % ("9" * 5000))).encode())
    out.append((base % ('{"id":"P","expr":{"op":"eq","left":{"op":"var","name":"a"},"right":{"op":"var","name":"x"}}}')).encode())
    out.append((base % ('{"id":"P","expr":{"op":"gt","left":{"op":"idiv","left":{"op":"var","name":"x"},"right":{"op":"var","name":"x"}},"right":{"op":"int","value":"0"}}}')).encode())
    out.append(b"\xff\xfe not utf8 \x00")
    out.append(b"[" * 200_000)
    out.append(("x" * 1_100_000).encode())
    many = ",".join('{"id":"P%d","expr":{"op":"var","name":"a"}}' % i for i in range(5000))
    out.append((base % many).encode())
    return out


def test_adversarial_volume_rejected_fast_without_internal_errors():
    payloads = _adversarial_payloads()
    rounds = 20
    worst = 0.0
    counts: dict[str, int] = {}
    for _ in range(rounds):
        for raw in payloads:
            s = time.perf_counter()
            r = verify(raw, CFG)
            worst = max(worst, (time.perf_counter() - s) * 1000.0)
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
            assert not is_definitive(r.status)
            assert r.status is not S.INTERNAL_ERROR, r.diagnostics
    record("adversarial", {"payloads": len(payloads), "rounds": rounds, "worst_ms": worst, "statuses": counts})
    assert worst < 3000.0, worst


def test_timeouts_bounded_under_concurrent_load():
    cfg = SolverConfig(timeout_ms=100, memory_max_mb=None)
    lim = Limits(allow_nonlinear=True)
    problems = [hard_nonlinear(i) for i in range(16)]

    def one(p):
        s = time.perf_counter()
        r = verify(p, cfg, lim)
        return r.status, (time.perf_counter() - s) * 1000.0

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(one, problems))
    worst = max(ms for _, ms in results)
    record("timeouts", {"n": len(results), "timeout_ms": 100, "worst_wall_ms": worst, "statuses": sorted({s.value for s, _ in results})})
    assert all(s in (S.TIMEOUT, S.UNKNOWN) for s, _ in results)
    assert worst < 100 * 1 + 4000, worst  # one check per satisfiability query; generous slack for 16 threads on 4 cores


def test_soak_mixed_workload():
    duration_s = float(os.environ.get("EPINOIC_SOAK_SECONDS", "60"))
    rss_before = rss_mb()
    counts: dict[str, int] = {}
    n = 0
    t_end = time.perf_counter() + duration_s
    makers = [lambda i: transitivity(i), lambda i: argument_chain(i, broken=False), lambda i: argument_chain(i, broken=True)]
    while time.perf_counter() < t_end:
        if n % 10 == 9:
            r = verify(_adversarial_payloads()[n % 11], CFG)
        else:
            r = verify(makers[n % 3](n), CFG)
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
        n += 1
    rss_after = rss_mb()
    record("soak", {"seconds": duration_s, "verifications": n, "statuses": counts, "rss_growth_mb": rss_after - rss_before})
    assert counts.get("INTERNAL_ERROR", 0) == 0
    assert rss_after - rss_before < 100.0
