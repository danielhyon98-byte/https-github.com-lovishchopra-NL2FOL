"""L6 peer exchange and synthesis, B2 ledger re-check and B3 contradictions: forwards and peer documents are the
delivered text, and a synthesis accounts for the reports as delivered and names every contradiction."""
from __future__ import annotations

import epinoic_logic.channel.bus as bus
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.integrity import AgentRole, IntegrityFinding, SynthesizedClaim
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

from .conftest import (
    DOC, HI_INPUT, HI_TEXT, default_synthesis, english_report, findings, int_problem, ovs_errors, run_task,
)

CONFLICT = dict(en_problems={"en-point": int_problem("en-point", "x", 7, op="gt", bound=5)},
                hi_problems={"h1.1": int_problem("h1.1", "x", 2, op="lt", bound=3)})
CONSISTENT = dict(en_problems={"en-point": int_problem("en-point", "x", 7, op="gt", bound=5)},
                  hi_problems={"h1.1": int_problem("h1.1", "x", 7, op="gt", bound=3)})


# ------------------------------------------------------------------------------------------- peer
def test_peer_003_is_stated_for_a_genuine_peer_exchange(auditor):
    task = run_task(auditor)
    f = findings(task.audit(), "OVS-PEER-003")
    assert f and f[0].severity == "info" and f[0].document_ids == ["peer:en"] and task.mids["fwd"] in f[0].message_ids


def test_t7_a_forward_altered_in_transit_is_rejected_by_the_channel_and_confirmed(auditor):
    task = run_task(auditor, peer=False, synthesis=False)
    delivered = SpecialistReport.model_validate(task.messages["rep_en"].payload)
    altered = delivered.model_copy(update={"unresolved_issues": ["edited by the router"]})
    msg, rf = task.ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, altered, in_reply_to=task.mids["rep_en"])
    assert msg is None and rf.status is TransmissionStatus.REJECTED and any(f.code == "INT-HANDOFF-013" for f in rf.findings)
    audit = task.audit()
    assert not ovs_errors(audit, allow=()) and audit.transfer_states[rf.message_id] == "AUDIT_PASSED"


def test_peer_001_a_forward_that_matches_a_mutated_typed_copy(auditor):
    task = run_task(auditor, peer=False, synthesis=False)
    held = task.ch.channel.transmitted_reports["rep-en-1"]
    held.claims.pop()  # the channel's copy is changed in place, so its own forward check compares like with like
    msg, rf = task.ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, held, in_reply_to=task.mids["rep_en"])
    assert msg is not None and rf.status is not TransmissionStatus.REJECTED
    audit = task.audit()
    f = findings(audit, "OVS-PEER-001")
    assert f and set(f[0].message_ids) == {rf.message_id, task.mids["rep_en"]} and f[0].report_ids == ["rep-en-1"]
    assert findings(audit, "OVS-CUST-004")
    assert audit.transfer_states[rf.message_id] == "AUDIT_FAILED"


def test_t7b_a_peer_document_one_word_off_is_peer_002(auditor):
    task = run_task(auditor, synthesis=False)
    report = SpecialistReport.model_validate(task.messages["rep_en"].payload)
    doc = SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist",
                       text=report.original_response.replace("endless", "endlessly"))
    m, _r, rq = task.ch.request("router", "history-specialist", HI_INPUT, [doc])
    f = [x for x in findings(task.audit(), "OVS-PEER-002") if rq.message_id in x.message_ids]
    assert f and f[0].document_ids == ["peer:en"] and "not byte-identical" in f[0].message and task.mids["fwd"] in f[0].message_ids


def test_t7c_a_peer_document_with_no_forward_is_peer_002(auditor):
    task = run_task(auditor, peer=False, synthesis=False)
    doc = SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist", text=english_report().original_response)
    _m, _r, rq = task.ch.request("router", "history-specialist", HI_INPUT, [doc])
    f = [x for x in findings(task.audit(), "OVS-PEER-002") if rq.message_id in x.message_ids]
    assert f and "no forward" in f[0].message


# ------------------------------------------------------------------------------------------- synthesis
def test_syn_001_a_synthesis_citing_an_undelivered_report(auditor):
    ghost = english_report(report_id="rep-ghost", created_at="2026-10-11T11:10:00Z")

    def inject(task):
        task.ch.channel.transmitted_reports["rep-ghost"] = ghost  # never delivered: written into the channel's records
    syn = default_synthesis(source_report_ids=("rep-en-1", "rep-hi-1", "rep-ghost"))
    task = run_task(auditor, before_synthesis=inject, synthesis_obj=syn)
    assert task.receipts["syn"].status is not TransmissionStatus.REJECTED
    f = findings(task.audit(), "OVS-SYN-001")
    assert f and "rep-ghost" in f[0].report_ids and f[0].message_ids == [task.mids["syn"]]


def _figure_changed_synthesis():
    claims = [SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
              SynthesizedClaim(claim_id="s2", text="The Factory Act of 1834 banned the employment of children under nine in textile mills.", source_claim_ids=["h1.1"], transformation="carried"),
              SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried")]
    return default_synthesis(claims=claims)


def test_t6_the_channel_names_a_changed_figure_and_the_audit_confirms(auditor):
    task = run_task(auditor, synthesis_obj=_figure_changed_synthesis())
    assert any(f.code == "INT-LEDGER-023" for f in task.receipts["syn"].findings)
    audit = task.audit()
    assert not findings(audit, "OVS-SYN-002") and not findings(audit, "OVS-RCPT-005")


def test_t6b_with_the_channels_ledger_patched_out_the_audit_finds_it(auditor, monkeypatch):
    monkeypatch.setattr(bus, "check_synthesis_ledger", lambda *a, **k: [])
    task = run_task(auditor, synthesis_obj=_figure_changed_synthesis())
    assert not any(f.code == "INT-LEDGER-023" for f in task.receipts["syn"].findings)
    audit = task.audit()
    f = [x for x in findings(audit, "OVS-SYN-002") if "INT-LEDGER-023" in x.message]
    assert f and "s2" in f[0].claim_ids and f[0].message_ids[0] == task.mids["syn"] and f[0].severity == "error"
    assert audit.transfer_states[task.mids["syn"]] == "AUDIT_FAILED"


def test_t6c_synthesis_payload_edited_after_receipt_is_cust_001(auditor):
    task = run_task(auditor)
    task.ch.channel.log.get(task.mids["syn"]).payload["claims"][0]["text"] = "The writer presents work as a joy"
    clr = auditor.clearance(task.uid, task.mids["syn"])
    assert clr.state == "AUDIT_FAILED" and "OVS-CUST-001" in clr.codes


def test_rcpt_005_a_ledger_error_the_recheck_does_not_reproduce(auditor, monkeypatch):
    real = bus.check_synthesis_ledger

    def spurious(scope, synthesis, **kw):
        return list(real(scope, synthesis, **kw)) + [IntegrityFinding(code="INT-LEDGER-002", severity="error", message="material source claim dropped", claim_ids=["en-ev1"])]
    monkeypatch.setattr(bus, "check_synthesis_ledger", spurious)
    task = run_task(auditor)
    f = findings(task.audit(), "OVS-RCPT-005")
    assert f and f[0].severity == "warning" and f[0].claim_ids == ["en-ev1"] and "INT-LEDGER-002" in f[0].message


# ------------------------------------------------------------------------------------------- contradictions (B3)
def test_t10b_control_the_channel_named_and_the_synthesis_disclosed_the_contradiction(auditor):
    task = run_task(auditor, conflicts=({"conflict_id": "k1", "claim_ids": ["en-point", "h1.1"], "description": "x cannot exceed 5 and be below 3"},), **CONFLICT)
    assert any(f.code == "INT-CONFLICT-001" for f in task.receipts["rep_hi"].findings)
    audit = task.audit()
    assert not findings(audit, "OVS-JOINT-001") and not findings(audit, "OVS-SYN-003") and not findings(audit, "OVS-JOINT-003")


def test_t10b_control_undisclosed_but_named_on_the_receipt(auditor):
    task = run_task(auditor, **CONFLICT)
    assert any(f.code == "INT-CONFLICT-002" for f in task.receipts["syn"].findings)
    audit = task.audit()
    assert not findings(audit, "OVS-JOINT-001") and not findings(audit, "OVS-SYN-003")


def test_t10_cross_check_patched_out_gives_joint_001_and_syn_003_citing_the_auditors_run(auditor, keyring, monkeypatch):
    monkeypatch.setattr(bus, "check_cross_report_consistency", lambda *a, **k: (None, []))
    task = run_task(auditor, **CONFLICT)
    assert not any(f.code.startswith("INT-CONFLICT") for rc in task.receipts.values() for f in rc.findings)
    audit = task.audit()
    j1, s3 = findings(audit, "OVS-JOINT-001"), findings(audit, "OVS-SYN-003")
    assert j1 and sorted(j1[0].claim_ids) == ["en-point", "h1.1"] and {task.mids["rep_en"], task.mids["rep_hi"]} <= set(j1[0].message_ids)
    assert s3 and sorted(s3[0].claim_ids) == ["en-point", "h1.1"] and task.mids["syn"] in s3[0].message_ids
    run = auditor.store.get(j1[0].formal_result_id)
    assert run is not None and run.origin == "auditor_run" and run.key_id == "overseer-run" and run.signature_ok_at_put
    assert run.status == "INCONSISTENT_PREMISES"
    assert j1[0].formal_result_id in audit.report.formal_result_ids
    assert audit.state == "AUDIT_FAILED"


def test_t10c_a_false_conflict_is_joint_003(auditor, monkeypatch):
    real = bus.check_cross_report_consistency

    def fabricate(problems, **kw):
        res, f = real(problems, **kw)
        ids = sorted(p.claim_id for p in problems)
        if len(ids) >= 2:
            f = list(f) + [IntegrityFinding(code="INT-CONFLICT-001", severity="error", message="specialist claims contradict each other", claim_ids=ids,
                                            formal_result_id=res.result_id if res is not None else None, deterministic=False)]
        return res, f
    monkeypatch.setattr(bus, "check_cross_report_consistency", fabricate)
    task = run_task(auditor, **CONSISTENT)
    f = findings(task.audit(), "OVS-JOINT-003")
    assert f and sorted(f[0].claim_ids) == ["en-point", "h1.1"] and f[0].severity == "error"
