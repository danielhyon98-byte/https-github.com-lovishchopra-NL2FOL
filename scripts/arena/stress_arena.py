#!/usr/bin/env python3
"""Stress the infrastructure with REAL specialist outputs: replay every transmission in a
round many times, sequentially and on 16 threads, and drive the HTTP service with the
same reports. Usage: stress_arena.py <round_dir> [replays=30]"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import load_items  # noqa: E402

KEY = b"arena-stress-key-0123456789abcdefg"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return float("nan")


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100.0 * (len(xs) - 1))))]


def load(round_dir: Path):
    """Specialist items; peer-dependent tasks are replayed with their peer's report supplied as a document, as the hub
    would have delivered it, so the stress figures cover the cross-subject exchange too."""
    items = load_items(round_dir / "specialists")
    by_id = {it["task_id"]: it for it in items}
    for it in items:
        peer = it.get("peer_of")
        if peer and peer in by_id:
            it["supplied_texts"] = [*it.get("supplied_texts", []), {"document_id": f"peer:{peer}", "title": f"{by_id[peer]['agent_id']} report relayed through the hub", "author": by_id[peer]["agent_id"], "text": by_id[peer]["response_text"]}]
    return items


def one_cycle(hub: RouterHub, item: dict, i: int) -> tuple[str, float]:
    texts = [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in item.get("supplied_texts", [])]
    task_id = f"{item['task_id']}-{i}"
    hub.open_task(WorkPlan(plan_id=f"plan-{task_id}", request_id=f"req-{item['task_id']}", task_id=task_id, subject=item["subject"], task_type=item.get("task_type", "analytical_paragraph"),
                           selected_agent_ids=[item["agent_id"]], allowed_document_ids=[t.document_id for t in texts]))
    t0 = time.perf_counter()
    m, _, _ = hub.dispatch(task_id, item["agent_id"], item["question"], texts)
    _, rc = hub.receive(task_id, m.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{task_id}")
    hub.channels.pop(task_id, None)
    return rc.status.value, (time.perf_counter() - t0) * 1000.0


def main(round_dir: Path, replays: int) -> dict:
    items = load(round_dir)
    out: dict = {"round": round_dir.name, "items": len(items), "replays": replays}
    hub = RouterHub(signing_key=KEY, config=CFG)
    rss0 = rss_mb()
    lat, statuses = [], {}
    t0 = time.perf_counter()
    for i in range(replays):
        for item in items:
            s, ms = one_cycle(hub, item, i)
            lat.append(ms)
            statuses[s] = statuses.get(s, 0) + 1
    out["sequential"] = {"transmissions": len(lat), "throughput_per_s": len(lat) / (time.perf_counter() - t0), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99), "statuses": statuses, "rss_growth_mb": rss_mb() - rss0}

    def worker(k):
        h = RouterHub(signing_key=KEY, config=CFG)
        res = []
        for i in range(max(1, replays // 4)):
            for item in items:
                res.append(one_cycle(h, item, 1000 * k + i)[0])
        return res
    t1 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = [s for r in pool.map(worker, range(16)) for s in r]
    out["threads16"] = {"transmissions": len(results), "wall_s": time.perf_counter() - t1, "rejected": results.count("REJECTED"), "statuses": {s: results.count(s) for s in set(results)}}

    # service under load with the same reports (verify endpoint with problems from the formal checks is covered by tests/service; here: outcomes path if available)
    try:
        import httpx
        from fastapi.testclient import TestClient
        from epinoic_logic.service.app import create_app
        from epinoic_logic.service.settings import ServiceSettings
        os.environ.setdefault("EPINOIC_SERVICE_TOKEN", "arena-token-0123456789abcdef")
        os.environ.setdefault("EPINOIC_SIGNING_KEY", KEY.hex())
        os.environ.setdefault("EPINOIC_SIGNING_KEY_ID", "arena")
        os.environ.setdefault("EPINOIC_RATE_PER_MINUTE", "100000")
        os.environ.setdefault("EPINOIC_MAX_CONCURRENCY", "64")  # the service sheds load above this with 503 + Retry-After; counted as "limited"
        app = create_app(ServiceSettings.from_env())
        client = TestClient(app)
        problem = {"problem_id": "arena-p", "request_id": "req-arena", "claim_id": "c", "query": "entailment",
                   "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}],
                   "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "y"}}}, {"id": "P2", "expr": {"op": "gt", "left": {"op": "var", "name": "y"}, "right": {"op": "var", "name": "z"}}}],
                   "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "var", "name": "z"}}}}
        codes = {}
        t2 = time.perf_counter()
        n = 0
        def hit(_):
            r = client.post("/v1/verify", json={"problem": problem}, headers={"Authorization": "Bearer " + os.environ["EPINOIC_SERVICE_TOKEN"]})
            return r.status_code
        with ThreadPoolExecutor(max_workers=32) as pool:
            for code in pool.map(hit, range(400)):
                codes[code] = codes.get(code, 0) + 1
                n += 1
        out["service"] = {"requests": n, "wall_s": time.perf_counter() - t2, "status_codes": codes,
                          "limited_503": codes.get(503, codes.get("503", 0)), "note": "503 = load shed by the bounded-concurrency admission with Retry-After, not a failure"}
    except Exception as exc:  # service optional in this harness
        out["service"] = {"error": f"{type(exc).__name__}: {exc}"}
    (round_dir / "stress.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    rd = Path(sys.argv[1]).resolve()
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    print(json.dumps(main(rd, n), indent=2))
