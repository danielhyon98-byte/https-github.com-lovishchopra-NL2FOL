"""Stress tests for STEM support (docs/STEM_DESIGN.md, section 13), run with ``-m stress``:

* p95 hub ``receive`` for a typical three-part Physics answer below 250 ms;
* a 128-check answer through the hub below 2.5 s;
* an adversarial 400,000-character input (nested brackets, unclosed ``$``, ``1e1e1e``, 30-digit numbers) through the
  front end below 1.5 s;
* the labelled corpus through the hub, every item below 2.5 s;
* non-STEM subjects unchanged by construction: their receipts never build a STEM document or carry a STEM check.

Measurements are written to ``tests/stress/results/stem.json``.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document, clear_document_cache, document_cache_info
from epinoic_logic.translate.contracts import SuppliedText

pytestmark = pytest.mark.stress
RESULTS_DIR = Path(__file__).parent / "results"
CORPUS = Path(__file__).resolve().parents[1] / "stem" / "data" / "stem_corpus.json"
KEY = b"stem-stress-key-0123456789abcdefghij"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
_RESULTS: dict[str, object] = {}


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100.0 * (len(xs) - 1))))]


def record(name: str, data: object) -> None:
    _RESULTS[name] = data
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / "stem.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    old[name] = data
    path.write_text(json.dumps(old, indent=2, ensure_ascii=False))


def three_part_answer(rng: random.Random) -> tuple[str, str]:
    """A typical three-part Physics answer with its request: Given block, three worked chains, restatements."""
    u = rng.choice(["0.0", "1.0", "2.0", "3.0"])
    v = f"{rng.randint(12, 30)}.0"
    t = f"{rng.randint(3, 9)}.0"
    m = f"{rng.randint(2, 9)}.0"
    a = (float(v) - float(u)) / float(t)
    a_s = f"{a:.2g}" if a < 10 else f"{a:.3g}"
    s = (float(u) + float(v)) / 2 * float(t)
    s_s = f"{s:.3g}"
    f_s = f"{float(m) * float(a_s):.2g}"
    question = (f"A {m} kg trolley accelerates uniformly from {u} m s⁻¹ to {v} m s⁻¹ in {t} s.\n(a) Calculate its acceleration.\n"
                f"(b) Calculate the distance travelled.\n(c) Calculate the resultant force.")
    answer = (f"Given: m = {m} kg, u = {u} m s⁻¹, v = {v} m s⁻¹, t = {t} s.\n\n"
              f"(a) a = (v − u)/t = ({v} − {u})/{t} = {a_s} m s⁻². The acceleration is therefore {a_s} m s⁻².\n\n"
              f"(b) s = (u + v)t/2 = ({u} + {v}) × {t}/2 = {s_s} m. The distance is therefore {s_s} m.\n\n"
              f"(c) F = ma = {m} × {a_s} = {f_s} N. The resultant force is therefore {f_s} N.")
    return question, answer


def receive(hub: RouterHub, task: str, subject: str, question: str, answer: str, supplied=()):
    hub.open_task(WorkPlan(plan_id=f"p-{task}", request_id=f"q-{task}", task_id=task, subject=subject, task_type="short_answer", selected_agent_ids=["a"]))
    m, _, _ = hub.dispatch(task, "a", question, list(supplied))
    t0 = time.perf_counter()
    _, rc = hub.receive(task, m.message_id, answer, agent_id="a", report_id=f"r-{task}")
    return rc, time.perf_counter() - t0


def test_p95_receive_of_a_typical_three_part_physics_answer_is_below_250_ms():
    rng = random.Random(20261012)
    hub = RouterHub(signing_key=KEY, config=CFG)
    receive(hub, "warm", "Physics", *three_part_answer(rng))
    lat, checks, errors = [], [], 0
    for k in range(60):
        q, a = three_part_answer(rng)
        rc, dt = receive(hub, f"t{k}", "Physics", q, a)
        lat.append(dt)
        checks.append(len(rc.formal_checks))
        errors += len(rc.errors)
    data = {"answers": len(lat), "p50_ms": pct(lat, 50) * 1000, "p95_ms": pct(lat, 95) * 1000, "max_ms": max(lat) * 1000,
            "checks_per_answer": [min(checks), max(checks)], "error_findings": errors}
    record("three_part_physics", data)
    assert errors == 0, data
    assert min(checks) >= 8, data
    assert data["p95_ms"] < 250, data


def test_a_128_check_answer_is_below_2_5_s():
    answer = "\n\n".join(f"Step {i}: {i}.0 × 2.0 = {2 * i}.0" for i in range(1, 129 + 12))
    hub = RouterHub(signing_key=KEY, config=CFG)
    rc, dt = receive(hub, "t128", "Physics", "Calculate each product.", answer)
    data = {"checks": len(rc.formal_checks), "satisfied": sum(1 for c in rc.formal_checks if c.satisfied), "seconds": dt,
            "codes": sorted({s.code for s in rc.structural_findings})}
    record("checks_128", data)
    assert data["checks"] == 128 and data["satisfied"] == 128 and "ST-LIM-002" in data["codes"], data
    assert dt < 2.5, data


def _adversarial_mix() -> str:
    parts = ["(" * 100_000, ("$x = 1 " * 15_000)[:100_000], "1e" * 50_000, " ".join(["x = " + "9" * 30] * 2_900)[:100_000]]
    return "".join(parts)[:400_000]


def test_an_adversarial_400k_input_through_the_front_end_is_below_1_5_s():
    text = _adversarial_mix()
    assert len(text) == 400_000
    build_document("x = 1", None, "physics")  # warm-up: imports and tables
    runs = []
    for _ in range(5):  # the best of five runs: the figure least disturbed by other load on the machine
        clear_document_cache()
        t = time.perf_counter()
        doc = build_document(text, None, "physics")
        runs.append(time.perf_counter() - t)
    singles = {}
    for name, body in (("nested_brackets", "(" * 400_000), ("unclosed_dollars", ("$x = 1 " * 60_000)[:400_000]), ("1e_chain", "1e" * 200_000),
                       ("digits_30", " ".join(["x = " + "9" * 30] * 12_000)[:400_000])):
        best = float("inf")
        for _ in range(2):
            clear_document_cache()
            t = time.perf_counter()
            single = build_document(body, None, "physics")
            best = min(best, time.perf_counter() - t)
        assert not [f for f in single.findings if f.code == "ST-INTERNAL-001"], name
        singles[name] = round(best, 3)  # recorded, not asserted: the design target is the mixed input
    data = {"mixed_runs_s": [round(x, 3) for x in runs], "best_s": round(min(runs), 3), "single_pattern_400k_s": singles,
            "findings": sorted({f.code for f in doc.findings})}
    record("adversarial_400k", data)
    assert not [f for f in doc.findings if f.code == "ST-INTERNAL-001"]
    assert min(runs) < 1.5, data


def test_the_labelled_corpus_through_the_hub_stays_within_bounds():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["items"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    lat = []
    for k, it in enumerate(corpus):
        rc, dt = receive(hub, f"c{k}", it["subject"], it["question"], it["response_text"], [SuppliedText(**s) for s in it.get("supplied_texts", [])])
        assert rc.status is not TransmissionStatus.REJECTED
        lat.append(dt)
    data = {"items": len(lat), "p50_ms": pct(lat, 50) * 1000, "p95_ms": pct(lat, 95) * 1000, "max_ms": max(lat) * 1000, "total_s": sum(lat)}
    record("corpus_through_hub", data)
    assert max(lat) < 2.5, data


def test_non_stem_subjects_build_no_stem_document_and_carry_no_stem_check():
    hub = RouterHub(signing_key=KEY, config=CFG)
    answers = {
        "History": "Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932. The Depression was therefore decisive.",
        "Economics": "Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 0.5.",
        "English A: Literature": "The poet's \"smokeless air\" sets the city apart from its ordinary condition; the image is therefore ironic.",
        "Business Management": "With a profit of 50,000 on revenue of 250,000 the profit margin is 20 per cent.",
    }
    clear_document_cache()
    for k, (subject, text) in enumerate(answers.items()):
        rc, _dt = receive(hub, f"n{k}", subject, "Answer the question.", text)
        assert rc.branch not in ("sciences", "mathematics", "computer_science")
        assert not any(c.constraint_id.startswith("stem-") for c in rc.formal_checks)
        assert not any(s.code.startswith("ST-") for s in rc.structural_findings)
    built = document_cache_info().misses
    record("non_stem_unchanged", {"subjects": list(answers), "stem_documents_built": built})
    assert built == 0
