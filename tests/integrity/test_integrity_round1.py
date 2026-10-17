"""Regression tests for the integrity-layer issues found by the round-1 overseer trials
(lenses: combinator-faults, router-envelope-overseer, formal-robustness).

Each test reproduces one way an agent could hide a drop, rewrite, inflation,
contradiction, stale or forged result, wrong-task report or tampered message, and
asserts that it surfaces as a SPECIFIC finding carrying the identifiers the Overseer
needs. ``test_inter_agent.py`` holds the original flows; nothing here repeats them.
"""
from __future__ import annotations

import math
import uuid

import pytest

import epinoic_logic.integrity as integrity
from epinoic_logic.engine import SolverConfig, sign_result, verify
from epinoic_logic.engine.provenance import binding_digest_of, sha256_hex, versions_digest
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import (
    AgentMessage, AgentRole, ConflictRecord, IntegrityFinding, LedgerEntry, MessageLog, Synthesis, SynthesizedClaim, WorkPlan,
    bind_payload, check_cross_report_consistency, check_paraphrase_coverage, check_report_against_plan, check_report_set,
    check_result_binding, check_synthesis_entailment, check_synthesis_ledger, claim_ids_from_core, joint_problem, meaningful,
    parse_rfc3339, payload_hash, run_integrity_checks, seal_plan, sign_message, verify_report_digest,
)
from epinoic_logic.ir.schema import Assertion, Problem, SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
KEY = b"integrity-round1-key-0123456789abcdef"
REQ, TASK = "req-r1", "task-r1"
DOC = SourceRef(document_id="doc-q", locator="q1", excerpt="A car covers 120 m in 8.0 s. Find its speed.")


def V(n): return {"op": "var", "name": n}
def R(v): return {"op": "real", "value": str(v)}
def I(v): return {"op": "int", "value": str(v)}
def cmp(op, l, r): return {"op": op, "left": l, "right": r}
def AND(*xs): return {"op": "and", "args": list(xs)}


def report(agent, subject, claims, report_id=None, request_id=REQ, task_id=TASK, task_type="short_answer", created_at="2026-10-11T09:00:00Z", course_level="unknown", overrides=None):
    rid = report_id or f"rep-{agent}"
    text = " ".join(c["claim_text"] for c in claims)
    recs = []
    for c in claims:
        base = dict(request_id=request_id, task_id=task_id, report_id=rid, agent_id=agent, subject=subject, task_type=task_type)
        base.update((overrides or {}).get(c["claim_id"], {}))
        recs.append(ClaimRecord(**base, **c))
    return SpecialistReport(report_id=rid, request_id=request_id, task_id=task_id, agent_id=agent, subject=subject, task_type=task_type, course_level=course_level,
                            original_response=text, response_sha256=sha256_text(text), created_at=created_at, claims=recs)


def plan(**over):
    base = dict(plan_id="plan-r1", request_id=REQ, task_id=TASK, subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist", "maths-specialist"], allowed_document_ids=["doc-q"])
    base.update(over)
    return WorkPlan(**base)


def synthesis(claims, ledger=(), conflicts=(), reports=("rep-physics-specialist", "rep-maths-specialist"), text=None, created_at="2026-10-11T09:05:00Z", **over):
    text = text or (" ".join(c.text for c in claims) or "(empty)")
    base = dict(synthesis_id="syn-r1", request_id=REQ, task_id=TASK, combinator_agent_id="combinator", source_report_ids=list(reports), claims=list(claims), ledger=list(ledger), conflicts=list(conflicts), text=text, text_sha256=sha256_text(text), created_at=created_at)
    base.update(over)
    return Synthesis(**base)


def phys(claim_id, speed, *, request_id=REQ, extra_symbols=(), extra_premises=(), def_grounding=None, meaning="speed in m/s"):
    return Problem.model_validate({
        "problem_id": f"pp-{claim_id}"[:128], "request_id": request_id, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": "v", "sort": "Real", "meaning": meaning}, {"name": "d", "sort": "Real"}, {"name": "t", "sort": "Real"}, *extra_symbols],
        "premises": [{"id": "D", "expr": cmp("eq", V("d"), R(120)), "grounding": {"kind": "task_setting", "verified": True}},
                     {"id": "T", "expr": cmp("eq", V("t"), R(8)), "grounding": {"kind": "task_setting", "verified": True}},
                     {"id": "DEF", "expr": cmp("eq", V("v"), {"op": "div", "left": V("d"), "right": R(8)}), "grounding": def_grounding or {"kind": "arithmetic_fact", "verified": True}},
                     *extra_premises],
        "conclusion": {"id": "C", "expr": cmp("eq", V("v"), R(speed))}})


def phys_other_distance(claim_id, speed, distance=128):
    """A claim consistent on its own (its own distance gives its own speed) that contradicts ``phys(..., 15)`` only through
    the shared distance ``d``: a genuine two-claim contradiction. ``phys(..., 16)`` is not one, since its own premises
    (d = 120, v = d/8) already refute its conclusion v = 16 (round 4: claim-minimal attribution names it alone)."""
    data = phys(claim_id, speed).model_dump(mode="json", exclude_none=True)
    data["premises"] = [{**a, "expr": cmp("eq", V("d"), R(distance))} if a["id"] == "D" else a for a in data["premises"]]
    return Problem.model_validate(data)


def two_reports():
    p = report("physics-specialist", "Physics", [
        dict(claim_id="ph-1", claim_text="The speed is 15 m/s and the motion is uniform.", claim_role="quantitative", certainty="established", source_refs=[DOC]),
        dict(claim_id="ph-2", claim_text="Quote to two significant figures.", claim_role="other", certainty="probable", materiality="supporting", source_refs=[DOC]),
        dict(claim_id="ph-3", claim_text="Air resistance is assumed negligible.", claim_role="other", certainty="possible", source_refs=[SourceRef(document_id="doc-q", locator="q1-note")])])
    m = report("maths-specialist", "Physics", [dict(claim_id="ma-1", claim_text="120 divided by 8 equals 15.", claim_role="quantitative", certainty="established", source_refs=[DOC])])
    return p, m


def codes(fs): return [f.code for f in fs]
def by_code(fs, code): return [f for f in fs if f.code == code]
def carried(cid, text, src, refs=(DOC,)): return SynthesizedClaim(claim_id=cid, text=text, source_claim_ids=[src], transformation="carried", evidence_refs=list(refs))
def drop(*ids, reason="presentation notes folded into the answer"): return LedgerEntry(source_claim_ids=list(ids), transformation="dropped", reason=reason)
def msg(message_id, payload, **over):
    base = dict(message_id=message_id, request_id=REQ, task_id=TASK, sender_agent_id="physics-specialist", sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.COMBINATOR,
                contract="specialist_report/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at="2026-10-11T10:00:00Z")
    base.update(over)
    return AgentMessage(**base)


# ------------------------------------------------------------------ claim ids outside the assertion-id grammar (blocker)
@pytest.mark.parametrize("cid_a,cid_b", [(uuid.UUID(int=0x7f3a9c2e4b1d4e8f9a0b1c2d3e4f5a6b).hex, "1" + uuid.uuid4().hex[1:]), ("claim#1", "claim#2"), ("ph 1", "ma 1"), ("k" * 128, "m" * 128), ("phys::v-1", "maths::v-1")])
def test_any_contract_claim_id_is_pooled_and_mapped_exactly(cid_a, cid_b):
    p = report("physics-specialist", "Physics", [dict(claim_id=cid_a, claim_text="The speed is 15 m/s.", claim_role="quantitative", source_refs=[DOC])])
    m = report("maths-specialist", "Physics", [dict(claim_id=cid_b, claim_text="The speed is 16 m/s.", claim_role="quantitative", source_refs=[DOC])])
    syn = synthesis([carried("s-1", "The speed is 15 m/s.", cid_a)], ledger=[drop(cid_b, reason="duplicate arithmetic")],
                    conflicts=[ConflictRecord(conflict_id="cf", claim_ids=[cid_a, cid_b], description="speeds differ")])
    # Round 4 (stricter than the pinned rule it replaces): cid_b's own premises refute its conclusion, so the claim-minimal
    # attribution names cid_b ALONE (INT-CONFLICT-005), mapped exactly through the alias table, and never the innocent cid_a.
    formalized = {cid_a: phys(cid_a, 15), cid_b: phys(cid_b, 16)}
    rep = run_integrity_checks(plan(), [p, m], syn, formalized, {"s-1": Assertion(id="S1", expr=cmp("eq", V("v"), R(16)))}, signing_key=KEY, config=CFG)
    c5 = by_code(rep.findings, "INT-CONFLICT-005")
    assert c5 and c5[0].claim_ids == [cid_b] and c5[0].formal_result_id in rep.formal_result_ids
    assert "INT-CONFLICT-001" not in codes(rep.findings) and "INT-CONFLICT-002" not in codes(rep.findings)
    assert any(f.code == "INT-SYNTH-001" and f.claim_ids[0] == "s-1" for f in rep.findings)
    assert "INT-GLOSSARY-004" not in codes(rep.findings)
    # a genuine two-claim contradiction (each claim consistent alone) is INT-CONFLICT-001 naming both, mapped exactly
    formalized = {cid_a: phys(cid_a, 15), cid_b: phys_other_distance(cid_b, 16)}
    rep = run_integrity_checks(plan(), [p, m], syn, formalized, {"s-1": Assertion(id="S1", expr=cmp("eq", V("v"), R(16)))}, signing_key=KEY, config=CFG)
    c1 = by_code(rep.findings, "INT-CONFLICT-001")
    assert c1 and set(c1[0].claim_ids) == {cid_a, cid_b} and c1[0].formal_result_id in rep.formal_result_ids
    assert "INT-CONFLICT-002" not in codes(rep.findings), "honest disclosure must not be reported as undisclosed"
    assert any(f.code == "INT-SYNTH-001" and f.claim_ids[0] == "s-1" for f in rep.findings)
    assert "INT-GLOSSARY-004" not in codes(rep.findings)


def test_claim_ids_from_core_uses_alias_table_not_string_splitting():
    probs = [phys("ph::alt", 16), phys("ma-1", 15)]
    joint, findings, jmap = joint_problem(probs, request_id=REQ)
    assert joint is not None and findings == []
    res = verify(joint, CFG)
    assert res.status is S.INCONSISTENT_PREMISES
    assert claim_ids_from_core(res.premises_relied_on, jmap) == ["ma-1", "ph::alt"]
    assert all(_id.startswith("c0:") or _id.startswith("c1:") for _id in res.premises_relied_on)
    # prefix collision 'a'+'b::P' vs 'a::b'+'P' is impossible under aliases
    pa = Problem.model_validate({"problem_id": "x1", "request_id": REQ, "claim_id": "a", "query": "consistency", "symbols": [{"name": "n", "sort": "Int"}], "premises": [{"id": "b::P", "expr": cmp("gt", V("n"), I(0))}]})
    pb = Problem.model_validate({"problem_id": "x2", "request_id": REQ, "claim_id": "a::b", "query": "consistency", "symbols": [{"name": "n", "sort": "Int"}], "premises": [{"id": "P", "expr": cmp("lt", V("n"), I(0))}]})
    res2, f2 = check_cross_report_consistency([pa, pb], request_id=REQ, config=CFG)
    assert res2.status is S.INCONSISTENT_PREMISES and set(by_code(f2, "INT-CONFLICT-001")[0].claim_ids) == {"a", "a::b"}


def test_glossary_004_names_the_claims_when_the_joint_problem_cannot_be_built():
    _, f = check_cross_report_consistency([phys("ph-1", 15), phys("ph-1", 16)], request_id=REQ, config=CFG)
    g4 = by_code(f, "INT-GLOSSARY-004")
    assert g4 and g4[0].claim_ids == ["ph-1"]


# ------------------------------------------------------------------ disclosure of contradictions (blocker)
def test_decoy_conflict_record_does_not_count_as_disclosure():
    p, m = two_reports()
    syn = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1")], ledger=[drop("ma-1", "ph-2", "ph-3")],
                    conflicts=[ConflictRecord(conflict_id="decoy", claim_ids=["ph-1", "ph-2"], description="significant figures")])
    formalized = {"ph-1": phys("ph-1", 15), "ma-1": phys_other_distance("ma-1", 16)}  # a genuine two-claim contradiction
    rep = run_integrity_checks(plan(), [p, m], syn, formalized, signing_key=KEY, config=CFG)
    c2 = by_code(rep.findings, "INT-CONFLICT-002")
    assert c2 and set(c2[0].claim_ids) == {"ph-1", "ma-1"} and c2[0].formal_result_id
    # Round 4 (stricter): when ma-1 refutes itself (phys(..., 16)), the contradiction is ma-1's alone (INT-CONFLICT-005)
    # and no disclosure of a conflict with the innocent ph-1 is demanded of the combinator.
    rep = run_integrity_checks(plan(), [p, m], syn, {"ph-1": phys("ph-1", 15), "ma-1": phys("ma-1", 16)}, signing_key=KEY, config=CFG)
    assert [f.claim_ids for f in by_code(rep.findings, "INT-CONFLICT-005")] == [["ma-1"]]
    assert "INT-CONFLICT-001" not in codes(rep.findings) and "INT-CONFLICT-002" not in codes(rep.findings)
    with pytest.raises(Exception):
        ConflictRecord(conflict_id="self", claim_ids=["ma-1", "ma-1"], description="n/a")


def test_disclosure_through_synthesized_claim_ids_is_accepted():
    p, m = two_reports()
    formalized = {"ph-1": phys("ph-1", 15), "ma-1": phys_other_distance("ma-1", 16)}  # a genuine two-claim contradiction
    syn = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1"), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")],
                    conflicts=[ConflictRecord(conflict_id="cf", claim_ids=["s-1", "s-2"], description="the two computed speeds differ")])
    rep = run_integrity_checks(plan(), [p, m], syn, formalized, signing_key=KEY, config=CFG)
    assert "INT-CONFLICT-001" in codes(rep.findings) and "INT-CONFLICT-002" not in codes(rep.findings)
    # Round 4 (stricter): a self-refuting ma-1 (phys(..., 16)) is INT-CONFLICT-005 alone; no conflict naming ph-1
    rep = run_integrity_checks(plan(), [p, m], syn, {"ph-1": phys("ph-1", 15), "ma-1": phys("ma-1", 16)}, signing_key=KEY, config=CFG)
    assert [f.claim_ids for f in by_code(rep.findings, "INT-CONFLICT-005")] == [["ma-1"]] and "INT-CONFLICT-001" not in codes(rep.findings) and "INT-CONFLICT-002" not in codes(rep.findings)


def test_single_claim_core_is_internal_inconsistency_not_a_cross_specialist_conflict():
    other = Problem.model_validate({"problem_id": "pm", "request_id": REQ, "claim_id": "ma-1", "query": "entailment", "symbols": [{"name": "k", "sort": "Real"}],
                                    "premises": [{"id": "K", "expr": cmp("eq", V("k"), R(3)), "grounding": {"kind": "task_setting", "verified": True}}], "conclusion": {"id": "C", "expr": cmp("gt", V("k"), R(2))}})
    formalized = {"ph-1": phys("ph-1", 16), "ma-1": other}
    res, f = check_cross_report_consistency(list(formalized.values()), request_id=REQ, config=CFG, signing_key=KEY)
    assert codes(f) == ["INT-CONFLICT-005"] and f[0].claim_ids == ["ph-1"] and "internally inconsistent" in f[0].message
    p, m = two_reports()
    syn = synthesis([carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-1", reason="specialist's own arithmetic is inconsistent"), drop("ph-2", "ph-3")])
    rep = run_integrity_checks(plan(), [p, m], syn, formalized, signing_key=KEY, config=CFG)
    assert "INT-CONFLICT-005" in codes(rep.findings) and "INT-CONFLICT-002" not in codes(rep.findings)


def test_undisclosed_contradiction_found_by_the_entailment_path_is_flagged():
    p, m = two_reports()
    third = report("physics-specialist", "Physics", [dict(claim_id="other", claim_text="v positive", claim_role="quantitative", source_refs=[DOC])], report_id="rep-third")
    other = Problem.model_validate({"problem_id": "x", "request_id": REQ, "claim_id": "other", "query": "consistency", "symbols": [{"name": "v", "sort": "Int"}], "premises": [{"id": "P", "expr": cmp("gt", V("v"), I(0))}]})
    formalized = {"ph-1": phys("ph-1", 15), "ma-1": phys_other_distance("ma-1", 16), "other": other}  # ph-1 and ma-1 genuinely contradict each other
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["ph-1", "ma-1"], transformation="merged", evidence_refs=[DOC])],
                    ledger=[drop("other", "ph-2", "ph-3")], reports=("rep-physics-specialist", "rep-maths-specialist", "rep-third"))
    rep = run_integrity_checks(plan(), [p, m, third], syn, formalized, {"s-1": Assertion(id="S", expr=cmp("eq", V("v"), R(15)))}, signing_key=KEY, config=CFG)
    assert "INT-GLOSSARY-001" in codes(rep.findings)  # cross-report check withheld
    c2 = by_code(rep.findings, "INT-CONFLICT-002")
    assert c2 and set(c2[0].claim_ids) == {"ph-1", "ma-1"}
    # Round 4 (stricter): on the entailment path too, a self-refuting ma-1 (phys(..., 16)) is named alone and demands no disclosure
    rep = run_integrity_checks(plan(), [p, m, third], syn, {**formalized, "ma-1": phys("ma-1", 16)}, {"s-1": Assertion(id="S", expr=cmp("eq", V("v"), R(15)))}, signing_key=KEY, config=CFG)
    assert [f.claim_ids for f in by_code(rep.findings, "INT-CONFLICT-005")] == [["s-1", "ma-1"]]
    assert "INT-CONFLICT-001" not in codes(rep.findings) and "INT-CONFLICT-002" not in codes(rep.findings)


# ------------------------------------------------------------------ ledger accounting (blockers)
def test_ledger_entry_must_point_at_an_existing_claim_that_cites_the_source():
    p, m = two_reports()
    syn = synthesis([carried("s-2", "120 divided by 8 equals 15.", "ma-1")],
                    ledger=[LedgerEntry(source_claim_ids=["ph-1"], transformation="merged", synthesized_claim_id="s-99"),
                            LedgerEntry(source_claim_ids=["ph-3"], transformation="carried"),
                            LedgerEntry(source_claim_ids=["ph-2"], transformation="narrowed", synthesized_claim_id="s-2", reason="same number")])
    f = check_synthesis_ledger([p, m], syn)
    l12 = by_code(f, "INT-LEDGER-012")
    assert len(l12) == 3 and {c for x in l12 for c in x.claim_ids} >= {"ph-1", "ph-3", "ph-2", "s-99", "s-2"}
    assert {c for x in by_code(f, "INT-LEDGER-002") if x.severity == "error" for c in x.claim_ids} == {"ph-1", "ph-3"}


def test_claim_id_namespace_collisions_are_errors():
    p, m = two_reports()
    recycled = synthesis([SynthesizedClaim(claim_id="ph-1", text="The speed is about 15 m/s.", source_claim_ids=["ph-1"], transformation="paraphrased", evidence_refs=[DOC]), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")])
    f = check_synthesis_ledger([p, m], recycled)
    l15 = by_code(f, "INT-LEDGER-015")
    assert l15 and l15[0].claim_ids == ["ph-1"] and l15[0].report_ids == ["rep-physics-specialist"]
    a = report("physics-specialist", "Physics", [dict(claim_id="c-1", claim_text="The speed is 15 m/s.", claim_role="quantitative", source_refs=[DOC])])
    b = report("maths-specialist", "Physics", [dict(claim_id="c-1", claim_text="The speed is 16 m/s.", claim_role="quantitative", source_refs=[DOC])])
    f = check_synthesis_ledger([a, b], synthesis([carried("s-1", "The speed is 16 m/s.", "c-1")]))
    l14 = by_code(f, "INT-LEDGER-014")
    assert l14 and l14[0].claim_ids == ["c-1"] and set(l14[0].report_ids) == {"rep-physics-specialist", "rep-maths-specialist"}
    assert len([x for x in by_code(f, "INT-LEDGER-002") if x.severity == "error"]) == 2
    same_rid = report("maths-specialist", "Physics", [dict(claim_id="ma-1", claim_text="x", claim_role="other")], report_id="rep-physics-specialist")
    rep = run_integrity_checks(plan(), [p, same_rid], None, signing_key=KEY, config=CFG)
    assert any(x.code == "INT-LEDGER-013" and x.report_ids == ["rep-physics-specialist"] for x in rep.findings)


def test_evidence_preservation_applies_to_merged_and_generalized_and_materiality_downgrade():
    p, m = two_reports()
    merged = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s and the motion is uniform.", source_claim_ids=["ph-1", "ma-1"], transformation="merged", evidence_refs=[])], ledger=[drop("ph-2", "ph-3")])
    assert {"s-1", "ph-1", "ma-1"} <= set(by_code(check_synthesis_ledger([p, m], merged), "INT-LEDGER-004")[0].claim_ids)
    gen = synthesis([SynthesizedClaim(claim_id="s-1", text="Speeds come out around 15 m/s.", source_claim_ids=["ph-1"], transformation="generalized", evidence_refs=[]), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")])
    assert "INT-LEDGER-004" in codes(check_synthesis_ledger([p, m], gen))
    down = synthesis([SynthesizedClaim(claim_id="s-1", text="Taken together, the speed is 15 m/s and air resistance is negligible.", certainty="possible", materiality="supporting", source_claim_ids=["ph-1", "ph-3", "ma-1"], transformation="merged", evidence_refs=[])], ledger=[drop("ph-2")])
    f = check_synthesis_ledger([p, m], down)
    assert "INT-LEDGER-004" in codes(f) and "INT-LEDGER-021" in codes(f) and "INT-LEDGER-011" in codes(f)


def test_required_formal_check_not_performed_is_visible():
    p, m = two_reports()
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 16 m/s.", source_claim_ids=["ph-1", "ma-1"], transformation="merged", evidence_refs=[DOC]),
                     SynthesizedClaim(claim_id="s-3", text="Air resistance is negligible.", certainty="possible", source_claim_ids=["ph-3"], transformation="paraphrased", evidence_refs=[SourceRef(document_id="doc-q", locator="q1-note")])],
                    ledger=[drop("ph-2")])
    rep = run_integrity_checks(plan(), [p, m], syn, {"ph-1": phys("ph-1", 15), "ma-1": phys("ma-1", 15)}, synthesized_conclusions={}, signing_key=KEY, config=CFG)
    s6 = by_code(rep.findings, "INT-SYNTH-006")
    assert s6 and s6[0].severity == "error" and s6[0].claim_ids[0] == "s-1"
    s12 = by_code(rep.findings, "INT-SYNTH-012")
    assert s12 and s12[0].severity == "warning" and s12[0].claim_ids[0] == "s-3"
    assert "required_formal_checks" in rep.checks_run


# ------------------------------------------------------------------ ledger majors and minors
@pytest.mark.parametrize("text", ["   ", "\n", ".", "-", "n/a", "see above", "tbd", None, "ok"])
def test_placeholder_reasons_and_bases_are_not_meaningful(text):
    assert not meaningful(text)
    p, m = two_reports()
    syn = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1")], ledger=[LedgerEntry(source_claim_ids=["ma-1", "ph-2", "ph-3"], transformation="dropped", reason=text)],
                    conflicts=[ConflictRecord(conflict_id="cf", claim_ids=["ph-1", "ma-1"], description="speed disagreement", status="resolved_with_basis", basis=text)])
    f = check_synthesis_ledger([p, m], syn)
    assert "INT-CONFLICT-003" in codes(f) and "INT-LEDGER-006" in codes(f)
    assert meaningful("arithmetic re-checked against the task values")


def test_carried_with_two_sources_and_text_coverage_and_narrowed():
    p, m = two_reports()
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 16 m/s.", source_claim_ids=["ph-1", "ma-1"], transformation="carried", evidence_refs=[DOC])], ledger=[drop("ph-2", "ph-3")])
    assert "INT-LEDGER-010" in codes(check_synthesis_ledger([p, m], syn))
    diverged = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1"), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")],
                         text="The speed is 16 m/s. 120 divided by 8 equals 16, and the car accelerates throughout.")
    f = check_synthesis_ledger([p, m], diverged)
    assert set(by_code(f, "INT-LEDGER-017")[0].claim_ids) == {"s-1", "s-2"} and "16" in by_code(f, "INT-LEDGER-018")[0].message
    narrowed = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["ph-1"], transformation="narrowed", evidence_refs=[DOC]), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")])
    l11 = by_code(check_synthesis_ledger([p, m], narrowed), "INT-LEDGER-011")
    assert l11 and "s-1" in l11[0].claim_ids and "coverage" in l11[0].message


def test_material_drop_excerpt_change_and_unlisted_report_are_visible():
    p, m = two_reports()
    f = check_synthesis_ledger([p, m], synthesis([carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-1", reason="student only needs the number"), drop("ph-2", "ph-3")]))
    assert any(x.code == "INT-LEDGER-019" and x.claim_ids == ["ph-1"] for x in f)
    altered = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1", refs=[SourceRef(document_id="doc-q", locator="q1", excerpt="A car covers 150 m in 8.0 s. Find its speed.")]), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")])
    assert any(x.code == "INT-LEDGER-020" and "s-1" in x.claim_ids and x.document_ids == ["doc-q"] for x in check_synthesis_ledger([p, m], altered))
    unlisted = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1"), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")], reports=("rep-physics-specialist",))
    assert any(x.code == "INT-LEDGER-016" and x.report_ids == ["rep-maths-specialist"] and "ma-1" in x.claim_ids for x in check_synthesis_ledger([p, m], unlisted))


# ------------------------------------------------------------------ synthesis entailment (majors)
def test_clean_flow_has_no_noise_and_weaker_paraphrase_is_flagged():
    res, f = check_synthesis_entailment([phys("ph-1", 15), phys("ma-1", 15)], Assertion(id="S1", expr=cmp("eq", V("v"), R(15))), request_id=REQ, synthesized_claim_id="s-1", config=CFG, signing_key=KEY)
    assert res.status is S.ENTAILED and f == [], [x.model_dump() for x in f]
    res2, f2 = check_paraphrase_coverage(phys("ph-1", 15), Assertion(id="S1", expr=cmp("ge", V("v"), R(15))), request_id=REQ, synthesized_claim_id="s-1", config=CFG, signing_key=KEY)
    assert res2.status is S.COUNTEREXAMPLE and codes(f2) == ["INT-SYNTH-007"] and f2[0].claim_ids == ["s-1", "ph-1"]
    p, m = two_reports()
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is at least 15 m/s.", source_claim_ids=["ph-1"], transformation="paraphrased", evidence_refs=[DOC]), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")])
    rep = run_integrity_checks(plan(), [p, m], syn, {"ph-1": phys("ph-1", 15), "ma-1": phys("ma-1", 15)}, {"s-1": Assertion(id="S1", expr=cmp("ge", V("v"), R(15)))}, signing_key=KEY, config=CFG)
    assert "INT-SYNTH-007" in codes(rep.findings) and not rep.errors


def test_pooled_source_conclusion_is_never_silent_evidence():
    src = Problem.model_validate({"problem_id": "u1", "request_id": REQ, "claim_id": "ph-u", "query": "entailment",
                                  "symbols": [{"name": "d", "sort": "Real"}, {"name": "w", "sort": "Real", "meaning": "work done in J"}],
                                  "premises": [{"id": "D", "expr": cmp("eq", V("d"), R(120)), "grounding": {"kind": "task_setting", "verified": True}}],
                                  "conclusion": {"id": "C", "expr": cmp("eq", V("w"), R(900)), "grounding": {"kind": "quotation", "verified": True}}})
    res, f = check_synthesis_entailment([src], Assertion(id="S", expr=cmp("eq", V("w"), R(900))), request_id=REQ, synthesized_claim_id="s-u", config=CFG, signing_key=KEY)
    assert res.status is S.ENTAILED and codes(f) == ["INT-SYNTH-008"] and f[0].claim_ids == ["s-u", "ph-u"] and f[0].related_result_ids
    # the same reliance is acceptable once a signed ENTAILED result for that exact source is supplied
    good = phys("ph-1", 15)
    prior = verify(good, CFG, signing_key=KEY, key_id="k")
    concl_only = Problem.model_validate({**good.model_dump(mode="json", exclude_none=True), "premises": [], "claim_id": "ph-1"})
    # Rewritten for the external review of 2026-10-12 (stale results): a prior result counts only as current-policy
    # evidence, so it must be bound consistently to the pooled source. The prior is re-bound to that source with its
    # binding digest recomputed and re-signed, and the check now also verifies the signature (the same assertion, under
    # the stricter rule); the old shortcut, a swapped problem digest under a stale binding digest, is refused.
    pd = __import__("epinoic_logic.ir.canonical", fromlist=["problem_digest"]).problem_digest(concl_only)
    b = prior.binding
    rebound = sign_result(prior.model_copy(update={"binding": b.model_copy(update={
        "problem_digest": pd, "binding_digest": binding_digest_of(pd, b.config_digest, b.versions_digest, b.limits_digest)})}), KEY, "k")
    _, f2 = check_synthesis_entailment([concl_only], Assertion(id="S", expr=cmp("eq", V("v"), R(15))), request_id=REQ, synthesized_claim_id="s-1", config=CFG, signing_key=KEY, prior_results={"ph-1": rebound})
    assert codes(f2) == []
    inconsistent = prior.model_copy(update={"binding": b.model_copy(update={"problem_digest": pd})})
    _, f3 = check_synthesis_entailment([concl_only], Assertion(id="S", expr=cmp("eq", V("v"), R(15))), request_id=REQ, synthesized_claim_id="s-1", config=CFG, prior_results={"ph-1": inconsistent})
    assert "INT-SYNTH-008" in codes(f3)


def test_partial_formalization_is_named_and_refutation_stays_an_error():
    A = Problem.model_validate({"problem_id": "A", "request_id": REQ, "claim_id": "a-1", "query": "consistency", "symbols": [{"name": "a", "sort": "Int"}, {"name": "b", "sort": "Int"}],
                                "premises": [{"id": "P", "expr": cmp("eq", V("a"), I(1)), "grounding": {"kind": "rubric_rule", "verified": True}}]})
    ra = report("physics-specialist", "Physics", [dict(claim_id="a-1", claim_text="Criterion A scores 1.", claim_role="quantitative", source_refs=[DOC])])
    rb = report("maths-specialist", "Physics", [dict(claim_id="b-1", claim_text="Criterion B scores 2.", claim_role="quantitative", source_refs=[DOC])])
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="Total marks are 3.", source_claim_ids=["a-1", "b-1"], transformation="merged", evidence_refs=[DOC])])
    rep = run_integrity_checks(plan(), [ra, rb], syn, {"a-1": A}, {"s-1": Assertion(id="S", expr=cmp("eq", {"op": "add", "args": [V("a"), V("b")]}, I(3)))}, signing_key=KEY, config=CFG)
    s9 = by_code(rep.findings, "INT-SYNTH-009")
    assert s9 and "b-1" in s9[0].claim_ids and "1 of 2" in s9[0].message and "INT-SYNTH-001" not in codes(rep.findings)
    # a claim that CONTRADICTS the formalized source is an error even with an unformalized co-source
    res, f = check_synthesis_entailment([A], Assertion(id="S", expr=cmp("eq", V("a"), I(2))), request_id=REQ, synthesized_claim_id="s-2", config=CFG, unformalized_source_ids=["b-1"])
    assert res.status is S.COUNTEREXAMPLE and codes(f) == ["INT-SYNTH-001"] and "REFUTED" in f[0].message and "b-1" in f[0].claim_ids and f[0].related_result_ids


def test_non_verdict_statuses_name_the_responsible_party():
    srcs = [phys("ph-1", 15), phys("ma-1", 15)]
    _, f = check_synthesis_entailment(srcs, Assertion(id="S", expr=cmp("eq", V("v"), I(15))), request_id=REQ, synthesized_claim_id="s-1", config=CFG)
    assert codes(f) == ["INT-SYNTH-010"] and f[0].severity == "error" and f[0].claim_ids == ["s-1"] and "E102" in f[0].message
    bad = Problem.model_validate({"problem_id": "b1", "request_id": REQ, "claim_id": "bad-1", "query": "consistency", "symbols": [{"name": "v", "sort": "Real"}], "premises": [{"id": "P", "expr": cmp("gt", V("w"), R(0))}]})
    _, f = check_cross_report_consistency(srcs + [bad], request_id=REQ, config=CFG)
    assert codes(f) == ["INT-GLOSSARY-007"] and f[0].claim_ids == ["bad-1"] and "E101" in f[0].message
    big = [Problem.model_validate({"problem_id": f"b{i}", "request_id": REQ, "claim_id": f"b-{i}", "query": "consistency", "symbols": [{"name": f"s{i}_{j}", "sort": "Bool"} for j in range(11)], "premises": [{"id": "P", "expr": V(f"s{i}_0")}]}) for i in range(100)]
    res, f = check_cross_report_consistency(big, request_id=REQ, config=CFG)
    assert res is not None and codes(f) == ["INT-GLOSSARY-006"] and len(f[0].claim_ids) == 100 and "E300" in f[0].message
    res, f = check_cross_report_consistency([phys("ph-1", 15), phys_other_distance("ma-1", 16)], request_id=REQ, config=SolverConfig(timeout_ms=3000, memory_max_mb=None, produce_unsat_core=False))
    assert set(by_code(f, "INT-CONFLICT-001")[0].claim_ids) == {"ph-1", "ma-1"}, "cores are always requested"
    # Round 4 (stricter): a self-refuting claim is attributed alone, also without the caller asking for cores
    res, f = check_cross_report_consistency([phys("ph-1", 15), phys("ma-1", 16)], request_id=REQ, config=SolverConfig(timeout_ms=3000, memory_max_mb=None, produce_unsat_core=False))
    assert codes(f) == ["INT-CONFLICT-005"] and f[0].claim_ids == ["ma-1"], "cores are always requested"


def test_glossary_findings_name_both_parties():
    other = Problem.model_validate({"problem_id": "x", "request_id": REQ, "claim_id": "other", "query": "consistency", "symbols": [{"name": "v", "sort": "Int"}], "premises": [{"id": "P", "expr": cmp("gt", V("v"), I(0))}]})
    for order in ([phys("ph-1", 15), other], [other, phys("ph-1", 15), phys("ma-1", 15)]):
        _, f = check_cross_report_consistency(order, request_id=REQ, config=CFG)
        assert by_code(f, "INT-GLOSSARY-001")[0].claim_ids == ["other", "ph-1"]
    res, f = check_cross_report_consistency([phys("ph-1", 15), phys("ma-1", 15, meaning="volume of the cylinder in cm^3")], request_id=REQ, config=CFG)
    assert res.status is S.CONSISTENT and codes(f) == ["INT-GLOSSARY-005"] and f[0].claim_ids == ["ma-1", "ph-1"]
    _, f = check_cross_report_consistency([phys("ph-1", 15), phys("ma-1", 15, meaning=" Speed in M/S ")], request_id=REQ, config=CFG)
    assert f == []


# ------------------------------------------------------------------ handoff (blockers and majors)
@pytest.mark.parametrize("created,expect", [
    ("2026-10-11T10:00:00Z", "INT-HANDOFF-005"), ("2026-10-11T08:30:00-05:00", "INT-HANDOFF-005"), ("2026-10-11T09:00:00.500Z", "INT-HANDOFF-005"),
    ("2026-10-11t10:00:00z", "INT-HANDOFF-005"), ("2026-10-11 10:00:00+00:00", "INT-HANDOFF-005"),
    ("2026-10-11T09:30:00+01:00", None), ("1", "INT-HANDOFF-008"), ("2026-10-11 10:00:00", "INT-HANDOFF-008"), ("yesterday", "INT-HANDOFF-008")])
def test_deadline_is_compared_as_instants(created, expect):
    r = report("physics-specialist", "Physics", [dict(claim_id="d-1", claim_text="x", claim_role="other")], created_at=created)
    f = check_report_against_plan(plan(deadline_at="2026-10-11T09:00:00Z"), r)
    assert codes(f) == ([expect] if expect else []), f
    if f:
        assert f[0].report_ids == ["rep-physics-specialist"] and f[0].claim_ids == ["d-1"]
    assert "INT-HANDOFF-005" in codes(check_report_against_plan(plan(deadline_at="2026-10-11T11:00:00+02:00"), report("physics-specialist", "Physics", [dict(claim_id="d-2", claim_text="x", claim_role="other")], created_at="2026-10-11T10:00:00Z")))


def test_missing_and_duplicate_agents_and_claim_level_provenance():
    p, m = two_reports()
    rep = run_integrity_checks(plan(), [p], synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1")], ledger=[drop("ph-2", "ph-3")], reports=("rep-physics-specialist",)), signing_key=KEY, config=CFG)
    h7 = by_code(rep.findings, "INT-HANDOFF-007")
    assert h7 and h7[0].severity == "error" and h7[0].agent_ids == ["maths-specialist"] and h7[0].report_ids == ["rep-physics-specialist"]
    p2 = report("physics-specialist", "Physics", [dict(claim_id="ph-1b", claim_text="The speed is 16 m/s.", claim_role="quantitative")], report_id="rep-physics-specialist-v2")
    h9 = by_code(check_report_set(plan(), [p, p2, m]), "INT-HANDOFF-009")
    assert h9 and h9[0].agent_ids == ["physics-specialist"] and set(h9[0].report_ids) == {"rep-physics-specialist", "rep-physics-specialist-v2"}
    hidden = report("physics-specialist", "Physics", [dict(claim_id="ph-7", claim_text="x", claim_role="other"), dict(claim_id="ph-8", claim_text="y", claim_role="other")],
                    overrides={"ph-7": {"task_id": "task-99"}, "ph-8": {"agent_id": "history-specialist", "subject": "History"}})
    h12 = by_code(check_report_against_plan(plan(), hidden), "INT-HANDOFF-012")
    assert [x.claim_ids for x in h12] == [["ph-7"], ["ph-8"]] and "history-specialist" in h12[1].agent_ids


def test_task_type_and_course_level_have_their_own_codes_and_report_findings_carry_ids():
    r = report("physics-specialist", "Physics", [dict(claim_id="tt-1", claim_text="x", claim_role="other")], task_type="essay", course_level="SL")
    f = check_report_against_plan(plan(course_level="HL"), r)
    assert [(x.code, x.severity) for x in f] == [("INT-HANDOFF-010", "warning"), ("INT-HANDOFF-011", "error")]
    assert all(x.report_ids == ["rep-physics-specialist"] and x.agent_ids == ["physics-specialist"] and x.claim_ids == ["tt-1"] for x in f)
    assert check_report_against_plan(plan(course_level="HL"), report("physics-specialist", "Physics", [dict(claim_id="u", claim_text="x", claim_role="other")], course_level="unknown")) == []
    wrong = report("physics-specialist", "Physics", [dict(claim_id="w", claim_text="x", claim_role="other")], task_id="task-99")
    h1 = by_code(check_report_against_plan(plan(), wrong), "INT-HANDOFF-001")[0]
    assert h1.report_ids == ["rep-physics-specialist"] and h1.agent_ids == ["physics-specialist"] and h1.claim_ids == ["w"]


def test_retrieval_scope_covers_combinator_and_formalized_grounding():
    p, m = two_reports()
    syn = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1", refs=[DOC, SourceRef(document_id="doc-wiki-kinematics", locator="sec:2")]), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")])
    rep = run_integrity_checks(plan(), [p, m], syn, signing_key=KEY, config=CFG)
    h4 = by_code(rep.findings, "INT-HANDOFF-004")
    assert h4 and h4[0].claim_ids == ["s-1"] and h4[0].document_ids == ["doc-wiki-kinematics"] and h4[0].agent_ids == ["combinator"]
    leaky = phys("ph-1", 15, def_grounding={"kind": "library_source", "verified": True, "source_refs": [{"document_id": "doc-leak", "locator": "p3"}]})
    rep = run_integrity_checks(plan(), [p, m], None, {"ph-1": leaky, "ma-1": phys("ma-1", 15)}, signing_key=KEY, config=CFG)
    h4 = by_code(rep.findings, "INT-HANDOFF-004")
    assert h4 and h4[0].claim_ids == ["ph-1"] and h4[0].document_ids == ["doc-leak"]
    sup = check_report_against_plan(plan(), report("physics-specialist", "Physics", [dict(claim_id="o-1", claim_text="x", claim_role="evidence", source_refs=[DOC])]).model_copy(update={"supplied_texts": [__import__("epinoic_logic.translate.contracts", fromlist=["SuppliedText"]).SuppliedText(document_id="doc-leak", text="t")]}))
    assert by_code(sup, "INT-HANDOFF-004")[0].document_ids == ["doc-leak"] and by_code(sup, "INT-HANDOFF-004")[0].claim_ids == ["o-1"]


def test_formalizations_and_prior_results_are_bound_to_the_request_and_report_set():
    p, m = two_reports()
    ghost = phys("ghost-1", 16)
    rep = run_integrity_checks(plan(), [p, m], None, {"ph-1": phys("ph-1", 15), "ma-1": phys("ma-1", 15), "ghost-1": ghost}, prior_results={"ghost-1": verify(ghost, CFG, signing_key=KEY, key_id="k")}, signing_key=KEY, config=CFG)
    s10 = by_code(rep.findings, "INT-STALE-010")
    assert len(s10) == 2 and all(x.claim_ids == ["ghost-1"] for x in s10) and "INT-CONFLICT-001" not in codes(rep.findings)
    rep = run_integrity_checks(plan(), [p, m], None, {"ph-1": phys("zzz", 16), "ma-1": phys("ma-1", 15, request_id="req-00")}, signing_key=KEY, config=CFG)
    s9 = by_code(rep.findings, "INT-STALE-009")
    assert len(s9) == 2 and s9[0].claim_ids == ["ph-1", "zzz"] and s9[1].claim_ids == ["ma-1"] and "cross_report_consistency" not in rep.checks_run


# ------------------------------------------------------------------ Overseer inputs: result binding (blockers)
def test_result_binding_enforces_config_versions_signature_and_digest_consistency():
    p1 = phys("ph-1", 15)
    r = verify(p1, CFG, signing_key=KEY, key_id="k")
    assert check_result_binding(r, p1, KEY, config=CFG) == []
    short = verify(p1, SolverConfig(timeout_ms=1, memory_max_mb=None), signing_key=KEY, key_id="k")
    assert codes(check_result_binding(short, p1, KEY, config=CFG)) == ["INT-STALE-005"]
    old = r.model_copy(update={"versions": r.versions.model_copy(update={"engine_version": "0.0.9"})})
    vd = versions_digest(old.versions)
    old = old.model_copy(update={"binding": old.binding.model_copy(update={"versions_digest": vd, "binding_digest": sha256_hex("|".join((old.binding.problem_digest, old.binding.config_digest, vd)))})})
    old = sign_result(old, KEY, "k")
    f = check_result_binding(old, p1, KEY, config=CFG)
    assert codes(f) == ["INT-STALE-005"] and "versions" in f[0].message and f[0].formal_result_id == r.result_id
    bad = r.model_copy(update={"binding": r.binding.model_copy(update={"binding_digest": "0" * 64})})
    assert codes(check_result_binding(bad, p1, None)) == ["INT-STALE-006", "INT-STALE-007"]


def test_unverifiable_signature_is_an_error_not_silence():
    p1, p2 = phys("ph-1", 15), phys("ma-1", 15)
    unsigned = verify(p1, CFG)
    f = check_result_binding(unsigned, p1, None, config=CFG)
    assert codes(f) == ["INT-STALE-006"] and f[0].severity == "error" and f[0].formal_result_id == unsigned.result_id
    edited = unsigned.model_copy(update={"status": S.COUNTEREXAMPLE})
    assert "INT-STALE-006" in codes(check_result_binding(edited, p1, None, config=CFG))
    p, m = two_reports()
    rep = run_integrity_checks(plan(), [p, m], None, {"ph-1": p1, "ma-1": p2}, prior_results={"ph-1": edited}, config=CFG)
    assert any(x.code == "INT-STALE-006" and x.claim_ids == ["ph-1"] for x in rep.findings)
    dup = sign_result(verify(p2, CFG, signing_key=KEY, key_id="k").model_copy(update={"result_id": unsigned.result_id}), KEY, "k")
    rep = run_integrity_checks(plan(), [p, m], None, {"ph-1": p1, "ma-1": p2}, prior_results={"ph-1": sign_result(unsigned, KEY, "k"), "ma-1": dup}, signing_key=KEY, config=CFG)
    assert any(x.code == "INT-STALE-008" and set(x.claim_ids) == {"ph-1", "ma-1"} for x in rep.findings)


# ------------------------------------------------------------------ envelopes (blockers)
def test_envelope_authenticity_header_changes_roles_and_payload_binding():
    payload = {"report_id": "rep-1", "claims": 3}
    forged = {"report_id": "rep-1", "claims": 2}
    log = MessageLog(signing_key=KEY, request_id=REQ)
    assert codes(log.accept(msg("u1", payload))) == ["INT-ENV-006"]
    signed = sign_message(msg("s1", payload), KEY, "k")
    assert log.accept(signed) == []
    assert codes(log.accept(sign_message(msg("f1", forged), b"other-key", "k"))) == ["INT-ENV-006"]
    tampered_header = sign_message(msg("s1", payload, task_id="task-other"), KEY, "k")
    f = log.accept(tampered_header)
    assert codes(f) == ["INT-ENV-002"] and "task_id" in f[0].message
    assert codes(log.accept(signed)) == ["INT-ENV-001"]
    assert codes(log.accept(sign_message(msg("x2", payload, request_id="req-other"), KEY, "k"))) == ["INT-ENV-009"]
    imp = sign_message(msg("v1", {"result_id": "r1", "status": "ENTAILED"}, contract="verification_result/1.0", recipient_role=AgentRole.OVERSEER), KEY, "k")
    assert codes(log.accept(imp)) == ["INT-ENV-007"]
    plan_msg = sign_message(msg("w1", {"plan": 1}, contract="work_plan/1.0", sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.OVERSEER), KEY, "k")
    assert codes(log.accept(plan_msg)) == ["INT-ENV-007"]
    # reply from a role the original was not addressed to
    reply = sign_message(msg("r1", payload, in_reply_to="s1", sender_agent_id="router", sender_role=AgentRole.ROUTER, recipient_role=AgentRole.SPECIALIST, contract="task_request/1.0"), KEY, "k")
    f = log.accept(reply)
    assert codes(f) == ["INT-ENV-010"] and set(f[0].message_ids) == {"r1", "s1"}
    # idempotency key reused with a different payload is an error, with the same payload a retry warning
    log2 = MessageLog()
    log2.accept(msg("i1", payload, idempotency_key="idem"))
    assert codes(log2.accept(msg("i2", payload, idempotency_key="idem"))) == ["INT-ENV-005"]
    assert codes(log2.accept(msg("i3", forged, idempotency_key="idem"))) == ["INT-ENV-011"]
    # envelope/payload binding
    p, _ = two_reports()
    f = bind_payload(msg("e1", p.model_dump(mode="json"), sender_agent_id="maths-specialist", task_id="task-99"), p)
    assert codes(f) == ["INT-ENV-008"] and f[0].report_ids == ["rep-physics-specialist"] and set(f[0].agent_ids) == {"maths-specialist", "physics-specialist"} and "ph-1" in f[0].claim_ids
    assert bind_payload(msg("e2", p.model_dump(mode="json")), p) == []


def test_contract_hygiene_timestamps_nan_and_digests():
    for bad in ["", "yesterday", "2026-13-45T99:99:99Z", "2026-10-11 10:00:00"]:
        with pytest.raises(Exception):
            msg("t", {"a": 1}, created_at=bad)
        with pytest.raises(Exception):
            synthesis([], created_at=bad)
        with pytest.raises(Exception):
            plan(deadline_at=bad)
    assert parse_rfc3339("2026-10-11t10:00:00.25z").isoformat() == "2026-10-11T10:00:00.250000+00:00"
    with pytest.raises(Exception):
        msg("nan", {"x": math.nan})
    sealed = seal_plan(plan())
    assert sealed.plan_sha256 and WorkPlan(**sealed.model_dump())
    with pytest.raises(Exception):
        WorkPlan(**{**sealed.model_dump(), "subject": "Chemistry"})
    p, m = two_reports()
    rep = run_integrity_checks(plan(), [p, m], None, signing_key=KEY, config=CFG)
    assert verify_report_digest(rep)
    rep.findings.append(IntegrityFinding(code="X", severity="info", message="tampered"))
    assert not verify_report_digest(rep)
    late = synthesis([carried("s-1", "The speed is 15 m/s and the motion is uniform.", "ph-1"), carried("s-2", "120 divided by 8 equals 15.", "ma-1")], ledger=[drop("ph-2", "ph-3")], created_at="2026-10-11T08:00:00Z")
    rep = run_integrity_checks(plan(deadline_at="2026-10-11T07:00:00Z"), [p, m], late, signing_key=KEY, config=CFG)
    assert "INT-HANDOFF-016" in codes(rep.findings) and "INT-HANDOFF-017" in codes(rep.findings)


# ------------------------------------------------------------------ robustness: never raise, never lose ids (blocker)
def test_large_id_lists_truncate_messages_but_never_the_identifiers():
    n = 60
    probs = [Problem.model_validate({"problem_id": f"cy-{i}", "request_id": REQ, "claim_id": f"specialist-claim-{i:03d}-" + "z" * 10, "query": "consistency",
                                     "symbols": [{"name": f"x{i}", "sort": "Int"}, {"name": f"x{(i + 1) % n}", "sort": "Int"}], "premises": [{"id": "P", "expr": cmp("gt", V(f"x{i}"), V(f"x{(i + 1) % n}"))}]}) for i in range(n)]
    res, f = check_cross_report_consistency(probs, request_id=REQ, config=CFG, signing_key=KEY)
    c1 = by_code(f, "INT-CONFLICT-001")[0]
    assert len(c1.claim_ids) == 60 and len(c1.message) <= 2000 and c1.message.endswith("[truncated]")
    p, m = two_reports()
    unknown = [f"u{i:02d}" + "q" * 125 for i in range(64)]
    f = check_synthesis_ledger([p, m], synthesis([SynthesizedClaim(claim_id="s-1", text="x", source_claim_ids=unknown, transformation="merged")]))
    assert set(by_code(f, "INT-LEDGER-001")[0].claim_ids) >= set(unknown)
    leaky = report("physics-specialist", "Physics", [dict(claim_id="o-1", claim_text="x", claim_role="evidence", source_refs=[SourceRef(document_id=f"leak-{i:02d}-" + "d" * 190, locator="p1") for i in range(32)])])
    assert len(by_code(check_report_against_plan(plan(), leaky), "INT-HANDOFF-004")[0].document_ids) == 32
    reports = [report(f"agent-{i % 16}", "Physics", [dict(claim_id=pr.claim_id, claim_text=f"c{i}", claim_role="quantitative")], report_id=f"rep-{i}") for i, pr in enumerate(probs)]
    rep = run_integrity_checks(plan(selected_agent_ids=[f"agent-{i}" for i in range(16)], allowed_document_ids=[]), reports, None, {pr.claim_id: pr for pr in probs}, signing_key=KEY, config=CFG)
    assert "INT-CONFLICT-001" in codes(rep.findings)


def test_internal_failure_of_a_check_becomes_a_finding(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated")
    monkeypatch.setattr(integrity, "check_report_set", boom)
    p, m = two_reports()
    rep = run_integrity_checks(plan(), [p, m], None, signing_key=KEY, config=CFG)
    f = by_code(rep.findings, "INT-INTERNAL-001")
    assert f and f[0].severity == "error" and "'handoff'" in f[0].message and set(f[0].report_ids) == {"rep-physics-specialist", "rep-maths-specialist"}


def test_every_emitted_finding_carries_an_identifier():
    p, m = two_reports()
    collected: list[IntegrityFinding] = []
    formalized = {"ph-1": phys("ph-1", 15), "ma-1": phys("ma-1", 16)}
    collected += run_integrity_checks(plan(deadline_at="2026-10-11T08:00:00Z", course_level="HL"), [p, m, report("history-specialist", "Chemistry", [dict(claim_id="h-1", claim_text="x", claim_role="other", advisory_verification_status="verified")], task_type="essay", course_level="SL", created_at="2026-10-12T00:00:00Z")],
                                     synthesis([SynthesizedClaim(claim_id="s-new", text="new", transformation="new"), carried("s-1", "The speed is 15 m/s.", "ph-1"), SynthesizedClaim(claim_id="s-u", text="x", source_claim_ids=["nope"], transformation="carried")],
                                               ledger=[LedgerEntry(source_claim_ids=["ma-1"], transformation="dropped"), LedgerEntry(source_claim_ids=["zzz"], transformation="dropped", reason="r"), LedgerEntry(source_claim_ids=["ph-2"], transformation="merged", synthesized_claim_id="s-77")],
                                               conflicts=[ConflictRecord(conflict_id="cf", claim_ids=["ph-1", "qqq"], description="d", status="resolved_with_basis")], reports=("rep-physics-specialist", "rep-ghost")),
                                     {**formalized, "ghost-1": phys("ghost-1", 15), "mis": phys("ma-1", 15)}, {"s-1": Assertion(id="S", expr=cmp("eq", V("v"), R(15))), "s-9": Assertion(id="S", expr=cmp("eq", V("v"), R(15)))},
                                     prior_results={"zz": verify(phys("zz", 15), CFG)}, signing_key=KEY, config=CFG).findings
    assert len({f.code for f in collected}) >= 20
    missing = [(f.code, f.message[:60]) for f in collected if not f.has_identifier()]
    assert missing == [], missing
    overloaded = {c for c in {f.code for f in collected} if len({f.severity for f in collected if f.code == c}) > 1}
    assert overloaded == set()
