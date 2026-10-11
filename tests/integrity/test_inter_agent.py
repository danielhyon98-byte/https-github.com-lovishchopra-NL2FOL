"""Simulated router -> specialists -> combinator -> Overseer flows with injected
miscommunications. Each injected fault must surface as a specific finding; the clean
flow must produce no errors."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import (
    AgentMessage, AgentRole, ConflictRecord, LedgerEntry, MessageLog, Synthesis, SynthesizedClaim, WorkPlan,
    check_cross_report_consistency, check_report_against_plan, check_result_binding, check_synthesis_entailment,
    check_synthesis_ledger, payload_hash, run_integrity_checks,
)
from epinoic_logic.ir.schema import Assertion, Problem, SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
KEY = b"integrity-test-key-0123456789abcdef"
REQ, TASK = "req-77", "task-77"


def V(n): return {"op": "var", "name": n}
def R(v): return {"op": "real", "value": str(v)}
def cmp(op, l, r): return {"op": op, "left": l, "right": r}


def report(agent, subject, claims, report_id=None, request_id=REQ, task_id=TASK, task_type="short_answer", docs=()):
    text = " ".join(c["claim_text"] for c in claims)
    return SpecialistReport(
        report_id=report_id or f"rep-{agent}", request_id=request_id, task_id=task_id, agent_id=agent, subject=subject, task_type=task_type,
        original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T10:00:00Z",
        supplied_texts=list(docs),
        claims=[ClaimRecord(request_id=request_id, task_id=task_id, report_id=report_id or f"rep-{agent}", agent_id=agent, subject=subject, task_type=task_type, **c) for c in claims],
    )


def plan(**over):
    base = dict(plan_id="plan-1", request_id=REQ, task_id=TASK, subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist", "maths-specialist"], allowed_document_ids=["doc-q"])
    base.update(over)
    return WorkPlan(**base)


def physics_problem(claim_id, speed_value):
    """Specialist asserts v = d/t with d=120, t=8 and claims v == speed_value (shared glossary: v, d, t)."""
    return Problem.model_validate({
        "problem_id": f"pp-{claim_id}", "request_id": REQ, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": "v", "sort": "Real", "meaning": "speed in m/s"}, {"name": "d", "sort": "Real"}, {"name": "t", "sort": "Real"}],
        "premises": [
            {"id": "D", "expr": cmp("eq", V("d"), R(120)), "grounding": {"kind": "task_setting", "verified": True}},
            {"id": "T", "expr": cmp("eq", V("t"), R(8)), "grounding": {"kind": "task_setting", "verified": True}},
            {"id": "DEF", "expr": cmp("eq", V("v"), {"op": "div", "left": V("d"), "right": R(8)}), "grounding": {"kind": "arithmetic_fact", "verified": True}},
        ],
        "conclusion": {"id": "C", "expr": cmp("eq", V("v"), R(speed_value))},
    })


def synthesis(claims, ledger=(), conflicts=(), reports=("rep-physics-specialist", "rep-maths-specialist")):
    text = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-1", request_id=REQ, task_id=TASK, combinator_agent_id="combinator", source_report_ids=list(reports),
                     claims=list(claims), ledger=list(ledger), conflicts=list(conflicts), text=text, text_sha256=sha256_text(text), created_at="2026-10-11T10:05:00Z")


@pytest.fixture
def two_reports():
    phys = report("physics-specialist", "Physics", [
        dict(claim_id="ph-1", claim_text="The speed is 15 m/s.", claim_role="quantitative", proposed_claim_kind="arithmetic", certainty="established",
             source_refs=[SourceRef(document_id="doc-q", locator="q1")]),
        dict(claim_id="ph-2", claim_text="The method assumes constant speed.", claim_role="other", certainty="probable", materiality="supporting"),
    ])
    maths = report("maths-specialist", "Physics", [
        dict(claim_id="ma-1", claim_text="120 divided by 8 equals 15.", claim_role="quantitative", proposed_claim_kind="arithmetic", certainty="established",
             source_refs=[SourceRef(document_id="doc-q", locator="q1")]),
    ])
    return phys, maths


def test_clean_flow_has_no_errors(two_reports):
    phys, maths = two_reports
    syn = synthesis([
        SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", certainty="established", source_claim_ids=["ph-1", "ma-1"], transformation="merged",
                         evidence_refs=[SourceRef(document_id="doc-q", locator="q1")]),
    ], ledger=[LedgerEntry(source_claim_ids=["ph-2"], transformation="dropped", reason="supporting assumption folded into the explanation")])
    formalized = {"ph-1": physics_problem("ph-1", 15), "ma-1": physics_problem("ma-1", 15)}
    concl = {"s-1": Assertion(id="S1", expr=cmp("eq", V("v"), R(15)))}
    rep = run_integrity_checks(plan(), [phys, maths], syn, formalized, concl, signing_key=KEY, config=CFG)
    assert rep.errors == [], [f.model_dump() for f in rep.errors]
    assert {"handoff", "ledger", "cross_report_consistency", "synthesis_entailment"} <= set(rep.checks_run)
    assert len(rep.formal_result_ids) == 2


def test_dropped_material_claim_without_record(two_reports):
    phys, maths = two_reports
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="120 divided by 8 equals 15.", source_claim_ids=["ma-1"], transformation="carried",
                                      evidence_refs=[SourceRef(document_id="doc-q", locator="q1")])])
    codes = {f.code for f in check_synthesis_ledger([phys, maths], syn) if f.severity == "error"}
    assert "INT-LEDGER-002" in codes


def test_certainty_inflation_and_evidence_loss(two_reports):
    phys, maths = two_reports
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="The method certainly assumes constant speed.", certainty="established", source_claim_ids=["ph-2"], transformation="paraphrased"),
                     SynthesizedClaim(claim_id="s-2", text="The speed is 15 m/s.", source_claim_ids=["ph-1"], transformation="paraphrased", evidence_refs=[]),
                     SynthesizedClaim(claim_id="s-3", text="120 divided by 8 equals 15.", source_claim_ids=["ma-1"], transformation="carried", evidence_refs=[SourceRef(document_id="doc-q", locator="q1")])])
    findings = check_synthesis_ledger([phys, maths], syn)
    by = {f.code: f for f in findings}
    assert "INT-LEDGER-003" in by and "s-1" in by["INT-LEDGER-003"].claim_ids
    assert "INT-LEDGER-004" in by and "s-2" in by["INT-LEDGER-004"].claim_ids


def test_orphan_synthesized_claim(two_reports):
    phys, maths = two_reports
    syn = synthesis([SynthesizedClaim(claim_id="s-x", text="Air resistance was negligible.", source_claim_ids=[], transformation="new"),
                     SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["ph-1", "ma-1"], transformation="merged", evidence_refs=[SourceRef(document_id="doc-q", locator="q1")])],
                    ledger=[LedgerEntry(source_claim_ids=["ph-2"], transformation="dropped", reason="supporting")])
    codes = {f.code for f in check_synthesis_ledger([phys, maths], syn)}
    assert "INT-LEDGER-005" in codes


def test_cross_report_contradiction_named_and_disclosure_required(two_reports):
    phys, maths = two_reports
    # Round 4 (stricter than the rule it replaces): physics_problem("ma-1", 16) refutes itself (its own d = 120, t = 8 give
    # v = 15), so the claim-minimal attribution names ma-1 ALONE (INT-CONFLICT-005) and never the innocent ph-1.
    res, findings = check_cross_report_consistency([physics_problem("ph-1", 15), physics_problem("ma-1", 16)], request_id=REQ, config=CFG, signing_key=KEY)
    assert res is not None and res.status.value == "INCONSISTENT_PREMISES"
    assert [(f.code, f.claim_ids) for f in findings] == [("INT-CONFLICT-005", ["ma-1"])]
    # a genuine two-claim contradiction: ma-1 is consistent on its own (its distance gives its speed) but contradicts ph-1
    data = physics_problem("ma-1", 16).model_dump(mode="json", exclude_none=True)
    data["premises"] = [{**a, "expr": cmp("eq", V("d"), R(128))} if a["id"] == "D" else a for a in data["premises"]]
    other = Problem.model_validate(data)
    formalized = {"ph-1": physics_problem("ph-1", 15), "ma-1": other}
    res, findings = check_cross_report_consistency(list(formalized.values()), request_id=REQ, config=CFG, signing_key=KEY)
    assert res is not None and res.status.value == "INCONSISTENT_PREMISES"
    conflict = [f for f in findings if f.code == "INT-CONFLICT-001"]
    assert conflict and set(conflict[0].claim_ids) == {"ph-1", "ma-1"} and conflict[0].formal_result_id == res.result_id and not conflict[0].deterministic

    undisclosed = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["ph-1"], transformation="carried", evidence_refs=[SourceRef(document_id="doc-q", locator="q1")])],
                            ledger=[LedgerEntry(source_claim_ids=["ma-1", "ph-2"], transformation="dropped", reason="duplicate")])
    rep = run_integrity_checks(plan(), [phys, maths], undisclosed, formalized, signing_key=KEY, config=CFG)
    assert {"INT-CONFLICT-001", "INT-CONFLICT-002"} <= {f.code for f in rep.errors}

    disclosed = synthesis(undisclosed.claims, ledger=undisclosed.ledger,
                          conflicts=[ConflictRecord(conflict_id="cf-1", claim_ids=["ph-1", "ma-1"], description="specialists disagree on the computed speed", status="unresolved")])
    rep2 = run_integrity_checks(plan(), [phys, maths], disclosed, formalized, signing_key=KEY, config=CFG)
    codes2 = {f.code for f in rep2.errors}
    assert "INT-CONFLICT-001" in codes2 and "INT-CONFLICT-002" not in codes2


def test_synthesis_not_entailed_by_sources(two_reports):
    phys, maths = two_reports
    sources = [physics_problem("ph-1", 15), physics_problem("ma-1", 15)]
    stronger = Assertion(id="S1", expr=cmp("gt", V("v"), R(15)))  # combinator overstates
    res, findings = check_synthesis_entailment(sources, stronger, request_id=REQ, synthesized_claim_id="s-1", config=CFG, signing_key=KEY)
    assert res.status.value == "COUNTEREXAMPLE" and any(f.code == "INT-SYNTH-001" for f in findings)
    faithful = Assertion(id="S1", expr=cmp("eq", V("v"), R(15)))
    res2, findings2 = check_synthesis_entailment(sources, faithful, request_id=REQ, synthesized_claim_id="s-1", config=CFG, signing_key=KEY)
    assert res2.status.value == "ENTAILED" and not any(f.severity == "error" for f in findings2)


def test_synthesis_entailed_only_via_inference_is_flagged():
    src = Problem.model_validate({
        "problem_id": "h1", "request_id": REQ, "claim_id": "hi-1", "query": "entailment",
        "symbols": [{"name": "q", "sort": "Bool"}, {"name": "p", "sort": "Bool"}],
        "premises": [{"id": "E", "expr": V("q"), "grounding": {"kind": "quotation", "verified": True}},
                     {"id": "L", "expr": {"op": "implies", "left": V("q"), "right": V("p")}, "grounding": {"kind": "specialist_inference", "certainty": "probable"}}],
        "conclusion": {"id": "C", "expr": V("p")},
    })
    res, findings = check_synthesis_entailment([src], Assertion(id="S", expr=V("p")), request_id=REQ, synthesized_claim_id="s-h", config=CFG)
    assert res.status.value == "ENTAILED" and any(f.code == "INT-SYNTH-002" and "hi-1" in f.claim_ids for f in findings)


def test_glossary_sort_conflict_blocks_joint_check():
    a = physics_problem("ph-1", 15)
    b = Problem.model_validate({"problem_id": "x", "request_id": REQ, "claim_id": "other", "query": "consistency",
                                "symbols": [{"name": "v", "sort": "Int"}], "premises": [{"id": "P", "expr": cmp("gt", V("v"), {"op": "int", "value": "0"})}]})
    res, findings = check_cross_report_consistency([a, b], request_id=REQ, config=CFG)
    assert res is None and findings[0].code == "INT-GLOSSARY-001"


def test_stale_and_unsigned_results_rejected():
    p1 = physics_problem("ph-1", 15)
    r = verify(p1, CFG, signing_key=KEY, key_id="k")
    assert check_result_binding(r, p1, KEY) == []
    changed = p1.model_copy(update={"notes": "re-translated with a different reading"})
    codes = {f.code for f in check_result_binding(r, changed, KEY)}
    assert "INT-STALE-001" in codes
    unsigned = verify(p1, CFG)
    assert {f.code for f in check_result_binding(unsigned, p1, KEY)} == {"INT-STALE-002"}
    forged = r.model_copy(update={"status": S.ENTAILED, "claim_id": "ph-1"})
    forged = forged.model_copy(update={"ungrounded_dependencies": ["X"]})
    assert "INT-STALE-002" in {f.code for f in check_result_binding(forged, p1, KEY)}


def test_handoff_faults(two_reports):
    phys, _ = two_reports
    assert check_report_against_plan(plan(), phys) == []
    wrong_task = report("physics-specialist", "Physics", [dict(claim_id="ph-9", claim_text="x", claim_role="other")], task_id="task-99")
    assert "INT-HANDOFF-001" in {f.code for f in check_report_against_plan(plan(), wrong_task)}
    rogue = report("history-specialist", "Physics", [dict(claim_id="h-1", claim_text="x", claim_role="other")])
    assert "INT-HANDOFF-002" in {f.code for f in check_report_against_plan(plan(), rogue)}
    off_subject = report("physics-specialist", "Chemistry", [dict(claim_id="c-1", claim_text="x", claim_role="other")])
    assert "INT-HANDOFF-003" in {f.code for f in check_report_against_plan(plan(), off_subject)}
    out_of_scope = report("physics-specialist", "Physics", [dict(claim_id="o-1", claim_text="x", claim_role="evidence", source_refs=[SourceRef(document_id="doc-leak", locator="p1")])])
    f = [x for x in check_report_against_plan(plan(), out_of_scope) if x.code == "INT-HANDOFF-004"]
    assert f and f[0].claim_ids == ["o-1"]
    self_cert = report("physics-specialist", "Physics", [dict(claim_id="sc-1", claim_text="x", claim_role="other", advisory_verification_status="verified")])
    assert "INT-HANDOFF-006" in {x.code for x in check_report_against_plan(plan(), self_cert)}


def test_envelope_replay_tamper_and_reply_chain():
    log = MessageLog()
    payload = {"report_id": "rep-1", "claims": 3}
    m1 = AgentMessage(message_id="m1", request_id=REQ, task_id=TASK, sender_agent_id="physics-specialist", sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.COMBINATOR,
                      contract="specialist_report/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at="2026-10-11T10:00:00Z")
    assert log.accept(m1) == []
    assert [f.code for f in log.accept(m1)] == ["INT-ENV-001"]
    tampered = {"report_id": "rep-1", "claims": 2}
    m1b = AgentMessage(**{**m1.model_dump(), "payload": tampered, "payload_sha256": payload_hash(tampered)})
    assert [f.code for f in log.accept(m1b)] == ["INT-ENV-002"]
    with pytest.raises(Exception):
        AgentMessage(**{**m1.model_dump(), "message_id": "m2", "payload": tampered})  # hash no longer matches
    orphan = AgentMessage(**{**m1.model_dump(), "message_id": "m3", "in_reply_to": "never-sent"})
    assert [f.code for f in log.accept(orphan)] == ["INT-ENV-003"]
    # a role-consistent reply (from the combinator m1 was addressed to) that crosses the task boundary
    cross = AgentMessage(**{**m1.model_dump(), "message_id": "m4", "task_id": "task-other", "in_reply_to": "m1", "sender_agent_id": "combinator",
                            "sender_role": AgentRole.COMBINATOR, "recipient_role": AgentRole.SPECIALIST, "contract": "synthesis/1.0"})
    assert [f.code for f in log.accept(cross)] == ["INT-ENV-004"]
    # the same reply from a role m1 was NOT addressed to is a reply-chain fault as well
    wrong_role = AgentMessage(**{**m1.model_dump(), "message_id": "m5", "task_id": "task-other", "in_reply_to": "m1"})
    assert [f.code for f in log.accept(wrong_role)] == ["INT-ENV-004", "INT-ENV-010"]
