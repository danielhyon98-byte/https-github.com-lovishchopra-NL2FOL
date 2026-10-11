"""Layer 3 stress tests for the translator channel and integrity cross-checks."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText,
    TranslationResult, TranslationStatus, sha256_text,
)

pytestmark = pytest.mark.stress
RESULTS_DIR = Path(__file__).parent / "results"
KEY = b"stress-channel-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
EXTRACT = "The lawyer stood by the thesis of homicide in legitimate defense of honor. 'We killed him openly,' Pedro Vicario said, 'but we're innocent.'"
DOC = SuppliedText(document_id="doc-cdf", text=EXTRACT, locator_scheme="none")
ASK = "Analyse how the writer presents justice in the extract. Use quotations from the extract. Write no more than 80 words."
TEXT = "Justice is compromised: \"thesis of homicide in legitimate defense of honor\" is ironic legal diction, and \"but we're innocent\" severs guilt from the act."


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


def plan(agents, subject="English A: Literature"):
    return WorkPlan(plan_id="plan-s", request_id="req-s", task_id="task-s", subject=subject, task_type="analytical_paragraph", selected_agent_ids=agents, allowed_document_ids=["doc-cdf"])


def report(agent, rid, text=TEXT, subject="English A: Literature", claims=None):
    claims = claims or [
        dict(claim_id=f"{rid}-point", claim_text="justice is presented as compromised", claim_role="point", supporting_claim_ids=[f"{rid}-ev"]),
        dict(claim_id=f"{rid}-ev", claim_text="thesis of homicide in legitimate defense of honor", claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt="thesis of homicide in legitimate defense of honor")]),
    ]
    return SpecialistReport(report_id=rid, request_id="req-s", task_id="task-s", agent_id=agent, subject=subject, task_type="analytical_paragraph", original_response=text, response_sha256=sha256_text(text),
                            supplied_texts=[DOC], created_at="2026-10-11T12:00:00Z",
                            claims=[ClaimRecord(request_id="req-s", task_id="task-s", report_id=rid, agent_id=agent, subject=subject, task_type="analytical_paragraph", **c) for c in claims])


def test_channel_cycles_sequential_latency_and_memory():
    ch = TranslatorChannel(plan(["english-specialist"]), signing_key=KEY, config=CFG)
    for i in range(10):
        m, _, _ = ch.request("router", "english-specialist", ASK, [DOC])
        ch.respond(m.message_id, report("english-specialist", f"w{i}", text=TEXT + f" {i}"))
    rss0 = rss_mb()
    lat = []
    statuses = {}
    for i in range(300):
        s = time.perf_counter()
        m, _, _ = ch.request("router", "english-specialist", ASK, [DOC])
        _, rc = ch.respond(m.message_id, report("english-specialist", f"r{i}", text=TEXT + f" cycle {i}"))
        lat.append((time.perf_counter() - s) * 1000.0)
        statuses[rc.status.value] = statuses.get(rc.status.value, 0) + 1
    rss1 = rss_mb()
    data = {"cycles": 300, "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99), "rss_growth_mb": rss1 - rss0, "statuses": statuses}
    record("channel_sequential", data)
    assert statuses.get("REJECTED", 0) == 0
    assert data["p99_ms"] < 500 and data["rss_growth_mb"] < 120, data


def test_channel_threads_independent_channels():
    def worker(k):
        ch = TranslatorChannel(plan(["english-specialist"]), signing_key=KEY, config=CFG)
        ok = 0
        for i in range(40):
            m, _, _ = ch.request("router", "english-specialist", ASK, [DOC])
            _, rc = ch.respond(m.message_id, report("english-specialist", f"t{k}-{i}", text=TEXT + f" {k}-{i}"))
            ok += rc.status is not TransmissionStatus.REJECTED and all(c.satisfied for c in rc.constraint_results)
        return ok
    with ThreadPoolExecutor(max_workers=16) as pool:
        counts = list(pool.map(worker, range(16)))
    record("channel_threads", {"workers": 16, "cycles_each": 40, "ok": counts})
    assert counts == [40] * 16


def _outcome(claim, rep, problem):
    res = verify(problem, CFG, signing_key=KEY, key_id="s")
    tr = TranslationResult(translation_id=f"tr-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=rep.report_id, status=TranslationStatus.TRANSLATED,
                           eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="s"),
                           problem=problem, translator_version="s", policy_version="s", created_at="2026-10-11T12:00:00Z")
    return ClaimVerificationOutcome(outcome_id=f"o-{claim.claim_id}", request_id=claim.request_id, report_id=rep.report_id, claim_id=claim.claim_id, translation=tr, verification=res, display_status=res.status, summary="s", created_at="2026-10-11T12:00:00Z")


def _numeric_problem(cid, idx, value):
    V = lambda n: {"op": "var", "name": n}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-s", "claim_id": cid, "query": "entailment",
                                   "symbols": [{"name": f"q{idx}", "sort": "Int"}, {"name": "shared", "sort": "Int"}],
                                   "premises": [{"id": "A", "expr": {"op": "eq", "left": V(f"q{idx}"), "right": {"op": "int", "value": str(idx)}}, "grounding": {"kind": "arithmetic_fact", "verified": True}},
                                                {"id": "B", "expr": {"op": "eq", "left": V("shared"), "right": {"op": "int", "value": str(value)}}, "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "ge", "left": V(f"q{idx}"), "right": {"op": "int", "value": "0"}}}})


def test_many_claims_accumulating_cross_check_scales_and_names_conflict():
    """8 specialists (the router may select at most 16) each answer 15 requests, so 120
    formalized claims accumulate on one channel; the very last claim contradicts the
    shared value and must be named, and the joint check must stay decidable."""
    n_agents, rounds = 8, 15
    agents = [f"spec-{i}" for i in range(n_agents)]
    total = n_agents * rounds
    problems = {f"c{k}": _numeric_problem(f"c{k}", k, 42) for k in range(total)}
    problems[f"c{total - 1}"] = _numeric_problem(f"c{total - 1}", total - 1, 43)

    def verify_fn(claim, rep):
        p = problems.get(claim.claim_id)
        return _outcome(claim, rep, p) if p else None

    ch = TranslatorChannel(plan(agents, subject="Physics"), signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    lat = []
    last = None
    k = 0
    for r in range(rounds):
        for a in agents:
            # the answer must not restate the request: "value 0" to "Give the shared value (round 0)" is an echo (INT-REQ-011),
            # which is never pooled, so the 120th formalization would be missing for a reason this test does not measure
            m, _, _ = ch.request("router", a, f"Give the shared value (round {r}).")
            rid = f"rep-{a}-{r}"
            rep = SpecialistReport(report_id=rid, request_id="req-s", task_id="task-s", agent_id=a, subject="Physics", task_type="analytical_paragraph", original_response=f"The computed value is {k}.", response_sha256=sha256_text(f"The computed value is {k}."), created_at="2026-10-11T12:00:00Z",
                                   claims=[ClaimRecord(request_id="req-s", task_id="task-s", report_id=rid, agent_id=a, subject="Physics", task_type="analytical_paragraph", claim_id=f"c{k}", claim_text=f"value {k}", claim_role="quantitative", proposed_claim_kind="arithmetic")])
            s = time.perf_counter()
            _, last = ch.respond(m.message_id, rep)
            lat.append((time.perf_counter() - s) * 1000.0)
            k += 1
    conflict = [f for f in last.findings if f.code == "INT-CONFLICT-001"]
    undecided = [f for f in last.findings if f.code == "INT-CONFLICT-004"]
    record("channel_scale", {"agents": n_agents, "rounds": rounds, "formalized": len(ch.formalized), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "last_ms": lat[-1], "conflict_named": bool(conflict), "undecided": bool(undecided)})
    assert len(ch.formalized) == total
    assert conflict and not undecided, [f.model_dump() for f in last.findings][:3]
    assert f"c{total - 1}" in conflict[0].claim_ids
    assert lat[-1] < 5000


def test_adversarial_responses_never_crash_and_never_deliver_wrong_identity():
    ch = TranslatorChannel(plan(["english-specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "english-specialist", ASK, [DOC])
    rejected = flagged = 0
    for i in range(200):
        kind = i % 5
        if kind == 0:
            rep = report("history-specialist", f"x{i}")                   # unselected agent
        elif kind == 1:
            rep = report("english-specialist", f"x{i}", text=TEXT + " " + " ".join(["w"] * 200))  # overlong
        elif kind == 2:
            rep = report("english-specialist", f"x{i}", claims=[dict(claim_id=f"c{i}", claim_text="made up", claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt=f"invented words {i}")])])
        elif kind == 3:
            rep = report("english-specialist", f"x{i}", claims=[dict(claim_id=f"c{i}", claim_text="leak", claim_role="evidence", source_refs=[SourceRef(document_id="doc-other", excerpt="z")])])
        else:
            rep = report("english-specialist", f"x{i}", subject="Chemistry")
        reply, rc = ch.respond(m.message_id if kind != 4 else "ghost", rep)
        if rc.status is TransmissionStatus.REJECTED:
            rejected += 1
            assert reply is None
        else:
            flagged += 1
            assert rc.findings
    record("channel_adversarial", {"responses": 200, "rejected": rejected, "delivered_with_findings": flagged})
    assert rejected + flagged == 200 and rejected >= 80
