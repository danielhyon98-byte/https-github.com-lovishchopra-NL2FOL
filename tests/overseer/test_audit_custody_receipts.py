"""L1 custody and L2 receipts: the transfer the router acts on is the one issued, and every receipt is the exact image of
what was checked. Each tampering case asserts the exact code, severity and identifiers, and that the transfer cannot
pass; each control asserts no ``OVS-*`` error and a verifying audit signature."""
from __future__ import annotations

import dataclasses

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel.bus import _SCOPE_TAIL
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.overseer import OverseerView, ResultStore, run_overseer_checks, verify_audit
from epinoic_logic.translate.contracts import SpecialistReport, sha256_text

from .conftest import (
    DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, HI_TEXT, KEY, CFG, codes_of, english_report, findings, make_auditor, make_keyring, make_plan, new_channel,
    ovs_errors, problems_fn, int_problem, run_task,
)


def _invented_report():
    """An English report whose evidence claim cites words the extract does not contain (INT-REQ-003 on the receipt)."""
    text = EN_TEXT + ' The foreman insists "the bell is our only god".'
    claims = [dict(c) for c in EN_CLAIMS] + [dict(claim_id="en-ev3", claim_text="the bell is our only god", claim_role="evidence", materiality="supporting",
                                                  source_refs=[SourceRef(document_id="doc-mill", excerpt="the bell is our only god")])]
    return english_report(text, claims)


# ------------------------------------------------------------------------------------------- controls
def test_control_task_has_no_ovs_error_and_a_verifying_signature(auditor, keyring):
    task = run_task(auditor)
    audit = task.audit()
    assert not ovs_errors(audit, allow=()), [(f.code, f.message) for f in ovs_errors(audit, allow=())]
    assert verify_audit(audit, keyring)
    assert set(audit.transfer_states.values()) <= {"AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"}
    for name in ("req_en", "rep_en", "fwd", "req_hi", "rep_hi", "syn"):
        clr = auditor.clearance(task.uid, task.mids[name], receipt=task.receipts[name])
        assert clr.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and clr.receipt_sha256 == clr.presented_receipt_sha256


def test_a_correctly_rejected_transfer_audits_passed(auditor):
    ch = new_channel(auditor)
    msg, _req, rc = ch.request("router", "physics-specialist", EN_INPUT, [DOC])
    assert msg is None and rc.status is TransmissionStatus.REJECTED
    clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
    assert clr.state == "AUDIT_PASSED" and clr.codes == []


# ------------------------------------------------------------------------------------------- L1 custody
def test_t1_payload_edited_in_the_log_is_cust_001(auditor):
    task = run_task(auditor, synthesis=False)
    mid = task.mids["rep_en"]
    task.ch.channel.log.get(mid).payload["claims"][0]["claim_text"] = "The writer presents work as a joy"
    clr = auditor.clearance(task.uid, mid)
    assert clr.state == "AUDIT_FAILED" and "OVS-CUST-001" in clr.codes
    f = findings(task.audit(), "OVS-CUST-001")
    assert f and f[0].severity == "error" and f[0].message_ids == [mid] and f[0].claim_ids == ["en-point"] and f[0].report_ids == ["rep-en-1"]
    assert "claims[0].claim_text" in f[0].message
    # a forward of that delivery depends on it: it cannot pass either
    assert auditor.clearance(task.uid, task.mids["fwd"]).state == "AUDIT_FAILED"


def test_header_altered_in_the_log_is_cust_002(auditor):
    task = run_task(auditor, synthesis=False)
    mid = task.mids["req_en"]
    log = task.ch.channel.log
    log._by_id[mid] = log.get(mid).model_copy(update={"recipient_agent_id": "history-specialist"})
    clr = auditor.clearance(task.uid, mid)
    assert clr.state == "AUDIT_FAILED"
    f = findings(task.audit(), "OVS-CUST-002")
    assert f and f[0].message_ids == [mid] and "recipient_agent_id" in f[0].message
    assert not findings(task.audit(), "OVS-CUST-001")  # a header edit is not a payload edit


def test_t1b_deep_mutation_of_the_typed_copy_is_cust_004(auditor):
    task = run_task(auditor, synthesis=False)
    popped = task.ch.channel.transmitted_reports["rep-en-1"].claims.pop()
    audit = task.audit()
    f = findings(audit, "OVS-CUST-004")
    assert f and f[0].severity == "error" and f[0].report_ids == ["rep-en-1"] and popped.claim_id in f[0].claim_ids
    assert f[0].message_ids == [task.mids["rep_en"]]
    assert audit.transfer_states[task.mids["rep_en"]] == "AUDIT_FAILED"


def test_request_typed_copy_mutation_is_cust_004(auditor):
    task = run_task(auditor, synthesis=False)
    task.ch.channel.requests[task.mids["req_en"]].constraints.clear()
    f = findings(task.audit(), "OVS-CUST-004")
    assert f and f[0].message_ids == [task.mids["req_en"]] and "constraints" in f[0].message


def test_journaled_message_missing_from_the_log_is_cust_003(auditor):
    task = run_task(auditor, synthesis=False)
    del task.ch.channel.log._by_id[task.mids["req_hi"]]
    f = findings(task.audit(), "OVS-CUST-003")
    assert f and f[0].message_ids == [task.mids["req_hi"]] and "absent from the channel's log" in f[0].message


def test_clearance_of_an_unjournaled_message_fails(auditor):
    task = run_task(auditor, synthesis=False)
    clr = auditor.clearance(task.uid, "never-issued")
    assert clr.state == "AUDIT_FAILED" and clr.codes == ["OVS-CUST-003"]


def test_t15_withheld_raw_text_digest_rewritten_is_cust_006(auditor, monkeypatch):
    import epinoic_logic.channel.bus as bus
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "history-specialist", "Explain the Factory Act of 1833.", [])
    real = bus.sha256_text
    monkeypatch.setattr(bus, "sha256_text", lambda t: "0" * 64)
    # stated by the hub to come from an agent the request was not addressed to: withheld, only the digest is kept
    msg, rc = ch.respond_text(m.message_id, HI_TEXT, agent_id="english-specialist", report_id="rep-x")
    monkeypatch.setattr(bus, "sha256_text", real)
    assert msg is None and rc.status is TransmissionStatus.REJECTED
    f = findings(auditor.audit(ch.uid), "OVS-CUST-006")
    assert f and f[0].message_ids == [rc.message_id] and f[0].severity == "error"


def test_t15b_parsed_report_whose_original_response_is_not_the_raw_text_is_cust_006(auditor):
    ch = new_channel(auditor)
    branch, profile = ch.channel._agent_branches["history-specialist"]
    base_factory = branch.parser_factory

    class Rewriting:
        agent_id = "history-specialist"

        def parse_response(self, text, **kw):
            rep = base_factory().parse_response(text, **kw)
            changed = rep.original_response + " The Act was a total success."
            return rep.model_copy(update={"original_response": changed, "response_sha256": sha256_text(changed)})
    ch.channel._agent_branches["history-specialist"] = (dataclasses.replace(branch, parser_factory=Rewriting), profile)
    m, _r, _q = ch.request("router", "history-specialist", "Explain the Factory Act of 1833.", [])
    _msg, rc = ch.respond_text(m.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
    f = findings(auditor.audit(ch.uid), "OVS-CUST-006")
    assert f and f[0].message_ids == [rc.message_id] and f[0].report_ids == ["rep-hi-1"]


# ------------------------------------------------------------------------------------------- L2 receipts
def test_t2_router_flips_its_receipt_status_and_presents_it_rcpt_001(auditor):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, _invented_report())
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    presented = rc.model_copy(update={"status": TransmissionStatus.ACCEPTED})  # the router's own copy; the channel's is intact
    clr = auditor.clearance(ch.uid, rc.message_id, receipt=presented)
    assert clr.state == "AUDIT_FAILED" and clr.codes == ["OVS-RCPT-001"] and clr.presented_receipt_sha256 != clr.receipt_sha256
    f = findings(auditor.audit(ch.uid), "OVS-RCPT-001")
    assert f and f[0].message_ids == [rc.message_id] and "status" in f[0].message
    # the shared object edited in place is caught on the channel's own copy too
    rc.status = TransmissionStatus.ACCEPTED
    assert auditor.clearance(ch.uid, rc.message_id).state == "AUDIT_FAILED"


def test_t2_router_edits_formal_status_on_its_copy_rcpt_001(auditor):
    task = run_task(auditor, synthesis=False)
    rc = task.receipts["rep_en"]
    edited = rc.model_copy(update={"constraint_results": [c.model_copy(update={"formal_status": "ENTAILED", "satisfied": True}) for c in rc.constraint_results]
                                   + [c.model_copy(update={"constraint_id": "x"}) for c in rc.constraint_results[:1]]})
    clr = auditor.clearance(task.uid, rc.message_id, receipt=edited)
    assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-001" in clr.codes


def test_t2b_status_inconsistent_with_findings_is_rcpt_002(auditor, monkeypatch):
    orig = TranslatorChannel._receipt

    def forced(self, message_id, direction, status, findings, **kw):
        if status is TransmissionStatus.ACCEPTED_WITH_FINDINGS:
            status = TransmissionStatus.ACCEPTED
        return orig(self, message_id, direction, status, findings, **kw)
    monkeypatch.setattr(TranslatorChannel, "_receipt", forced)
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, _invented_report())
    audit = auditor.audit(ch.uid)
    f = findings(audit, "OVS-RCPT-002")
    assert f and f[0].message_ids == [rc.message_id] and "ACCEPTED_WITH_FINDINGS" in f[0].message
    assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"


def test_t2c_summary_edited_by_the_router_and_scope_sentence_dropped_by_the_channel(auditor, monkeypatch):
    task = run_task(auditor, synthesis=False)
    rc = task.receipts["rep_en"]
    edited = rc.model_copy(update={"summary": rc.summary.replace("Findings: none", "Findings: none; all claims verified")})
    assert auditor.clearance(task.uid, rc.message_id, receipt=edited).codes == ["OVS-RCPT-001"]
    orig = TranslatorChannel._receipt

    def no_scope(self, *a, summary, **kw):
        return orig(self, *a, summary=summary.replace(_SCOPE_TAIL, "All claims are verified."), **kw)
    monkeypatch.setattr(TranslatorChannel, "_receipt", no_scope)
    m, _r, _q = task.ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc2 = task.ch.respond(m.message_id, english_report(report_id="rep-en-2", created_at="2026-10-11T11:30:00Z"))
    f = [x for x in findings(task.audit(), "OVS-RCPT-007") if rc2.message_id in x.message_ids]
    assert f and "scope sentence" in f[0].message


def test_summary_claiming_what_the_fields_do_not_support_is_rcpt_007(auditor, monkeypatch):
    orig = TranslatorChannel._receipt

    def rosy(self, *a, summary, **kw):
        return orig(self, *a, summary=summary.replace("Findings: INT-REQ-003", "Findings: none"), **kw)
    monkeypatch.setattr(TranslatorChannel, "_receipt", rosy)
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, _invented_report())
    assert "Findings: none" in rc.summary
    f = findings(auditor.audit(ch.uid), "OVS-RCPT-007")
    assert f and f[0].message_ids == [rc.message_id]


def test_t2d_a_receipt_naming_an_identifier_that_resolves_nowhere_is_rcpt_006(auditor, monkeypatch):
    orig = TranslatorChannel._receipt

    def ghost(self, message_id, direction, status, findings, **kw):
        findings = [f.model_copy(update={"claim_ids": list(f.claim_ids) + ["ghost-claim"]}) if f.code == "INT-REQ-003" else f for f in findings]
        return orig(self, message_id, direction, status, findings, **kw)
    monkeypatch.setattr(TranslatorChannel, "_receipt", ghost)
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, _invented_report())
    f = findings(auditor.audit(ch.uid), "OVS-RCPT-006")
    assert f and f[0].claim_ids == ["ghost-claim"] and f[0].message_ids == [rc.message_id]


def test_a_rejected_transfer_that_was_delivered_anyway_is_rcpt_003(auditor, monkeypatch):
    orig = TranslatorChannel._finish

    def leaky(self, msg, *a, **kw):
        _m, rc = orig(self, msg, *a, **kw)
        return msg, rc  # the message is returned whatever the status
    monkeypatch.setattr(TranslatorChannel, "_finish", leaky)
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    msg, rc = ch.respond(m.message_id, english_report(agent="history-specialist", report_id="rep-wrong"))
    assert rc.status is TransmissionStatus.REJECTED and msg is not None
    f = findings(auditor.audit(ch.uid), "OVS-RCPT-003")
    assert f and f[0].message_ids == [rc.message_id] and "returned" in f[0].message


def test_an_accepted_request_that_was_not_stored_is_rcpt_003(auditor, monkeypatch):
    ch = new_channel(auditor)
    orig = TranslatorChannel.request

    def forgetful(self, *a, **kw):
        out = orig(self, *a, **kw)
        self.requests.pop(out[2].message_id, None)
        return out
    monkeypatch.setattr(TranslatorChannel, "request", forgetful)
    _m, _r, rc = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    f = findings(auditor.audit(ch.uid), "OVS-RCPT-003")
    assert f and f[0].message_ids == [rc.message_id] and "not stored" in f[0].message


# ------------------------------------------------------------------------------------------- degraded view
def test_from_channel_degraded_view_on_a_hub_without_hooks():
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = make_plan()
    ch = hub.open_task(plan)
    ch.verify_claim_fn = problems_fn({"en-point": int_problem("en-point", "work_hours", 12, op="gt", bound=8)})
    m, _req, _rq = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
    _msg, rc = hub.receive(plan.task_id, m.message_id, english_report())
    kr = make_keyring()
    store = ResultStore(kr)
    view = OverseerView.from_channel(ch, store=store)
    assert view.degraded and [t.kind for t in view.transfers] == ["request", "response"]
    result = run_overseer_checks(view, keyring=kr, store=store, live=ch, batch=True, shadow=False)
    codes = {f.code for f in result.report.findings}
    assert "OVS-AUDIT-002" in codes and "OVS-RES-002" in codes
    assert not codes & {"OVS-CUST-001", "OVS-CUST-002", "OVS-CUST-004", "OVS-RCPT-001", "OVS-RES-001", "OVS-RCPT-006"}
    assert result.task_state != "AUDIT_PASSED"  # degraded is never passed
    # a status inconsistent with the receipt's own contents is still decided without a journal
    rc.status = TransmissionStatus.REJECTED
    result2 = run_overseer_checks(OverseerView.from_channel(ch, store=store), keyring=kr, store=store, live=ch, batch=False, shadow=False)
    assert any(f.code == "OVS-RCPT-002" and rc.message_id in f.message_ids for f in result2.report.findings)
