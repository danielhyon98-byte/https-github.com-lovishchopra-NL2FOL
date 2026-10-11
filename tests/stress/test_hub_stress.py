"""Layer 3 stress tests for the branching hub: many specialists across subjects, the
report's-own-arithmetic checks under volume, and adversarial numeric text."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub, extract_quant_checks
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

pytestmark = pytest.mark.stress
RESULTS_DIR = Path(__file__).parent / "results"
KEY = b"hub-stress-key-0123456789abcdefgh"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

SUBJECTS = {
    "History": ("history-specialist", "The Depression created the Nazi electorate. Unemployment rose from 1.4 million in 1928 to 6.1 million in 1932, a 335 per cent increase. The counter-case is that the unemployed often voted Communist. By the criterion of necessity the Depression was decisive. The vote fell in November 1932, after the party had become the largest in July 1932."),
    "Economics": ("economics-specialist", "Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 0.5. Revenue rose from 200,000 to 260,000, an increase of 30 per cent. Demand is therefore inelastic on balance."),
    "Business Management": ("business-specialist", "With a profit of 50,000 on revenue of 250,000 the profit margin is 20 per cent. Fixed costs of 50,000 and variable costs of 30,000 gave a total of 80,000. The firm should therefore proceed."),
    "Psychology": ("psychology-specialist", "Loftus and Palmer (1974) showed leading questions alter estimates. 30 per cent of the 150 participants, or 45, reported seeing glass. The effect was significant at p < 0.05; therefore the claim holds to a large extent."),
    "English A: Literature": ("english-specialist", "Justice is compromised. The lawyer's \"thesis of homicide in legitimate defense of honor\" uses ironic legal diction. Ultimately the diction exposes a system that protects honour, not justice."),
}


def rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return float("nan")


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100.0 * (len(xs) - 1))))]


def record(name, data):
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))


def test_five_subjects_hundred_cycles_each():
    hub = RouterHub(signing_key=KEY, config=CFG)
    for subject, (agent, _) in SUBJECTS.items():
        hub.open_task(WorkPlan(plan_id=f"p-{agent}", request_id="req-hs", task_id=f"t-{agent}", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    rss0 = rss_mb()
    lat: dict[str, list[float]] = {s: [] for s in SUBJECTS}
    statuses: dict[str, int] = {}
    formal_total = 0
    for i in range(100):
        for subject, (agent, text) in SUBJECTS.items():
            s = time.perf_counter()
            m, _, _ = hub.dispatch(f"t-{agent}", agent, "Evaluate the claim with evidence.")
            _, rc = hub.receive(f"t-{agent}", m.message_id, text + f" (cycle {i})", agent_id=agent, report_id=f"rep-{agent}-{i}")
            lat[subject].append((time.perf_counter() - s) * 1000.0)
            statuses[rc.status.value] = statuses.get(rc.status.value, 0) + 1
            formal_total += len(rc.formal_checks)
            assert rc.status is not TransmissionStatus.REJECTED
            assert all(fc.satisfied for fc in rc.formal_checks), [fc.detail for fc in rc.formal_checks if not fc.satisfied]
    rss1 = rss_mb()
    data = {"cycles_per_subject": 100, "subjects": list(SUBJECTS), "p50_ms": {s: pct(v, 50) for s, v in lat.items()}, "p95_ms": {s: pct(v, 95) for s, v in lat.items()},
            "formal_checks_decided": formal_total, "statuses": statuses, "rss_growth_mb": rss1 - rss0}
    record("hub_subjects", data)
    assert all(pct(v, 95) < 1500 for v in lat.values()), data
    assert data["rss_growth_mb"] < 150, data


def test_adversarial_numeric_text_never_crashes_and_stays_fast():
    rng = random.Random(7)
    worst = 0.0
    produced = 0
    for i in range(300):
        kind = i % 6
        if kind == 0:
            text = "Revenue rose from " + "9" * 60 + " to " + "9" * 61 + ", an increase of 10 per cent."
        elif kind == 1:
            text = " ".join(f"{rng.randint(1, 999999):,}" for _ in range(400)) + " an increase of 5 per cent."
        elif kind == 2:
            text = "rose from 0 to 100, an increase of 100 per cent. " * 50
        elif kind == 3:
            text = "from 1.5 to 3, doubled; from 3 to 9, trebled; from 9 to 36, quadrupled; " * 20
        elif kind == 4:
            text = "50 per cent of the 0 respondents, or 0, agreed. " + "100 per cent of the 1,000,000,000 respondents, or 999,999,999, agreed."
        else:
            text = "from 1e309 to 2e309, an increase of 100 per cent; from -5 to 5, an increase of 200 per cent."
        s = time.perf_counter()
        checks = extract_quant_checks(text, request_id="r", claim_id="c")
        from epinoic_logic.engine import verify
        for c in checks:
            r = verify(c.problem, CFG)
            assert r.status.value != "INTERNAL_ERROR", r.diagnostics
        produced += len(checks)
        worst = max(worst, (time.perf_counter() - s) * 1000.0)
    record("hub_adversarial_numeric", {"texts": 300, "checks_produced": produced, "worst_ms": worst})
    assert worst < 5000, worst
