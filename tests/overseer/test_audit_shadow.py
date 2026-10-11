"""B5 shadow-channel replay: a fresh channel fed the journaled inputs must issue the same receipts. Dropped findings
(RCPT-004), unreproducible findings (RCPT-005), another status (RCPT-008), and environment nondeterminism (RES-008,
never an accusation)."""
from __future__ import annotations

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, IntegrityFinding
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.overseer import JournalSet

from .conftest import (
    DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, english_report, findings, make_auditor, make_keyring, new_channel, ovs_errors, run_task,
)

_INVENTED = english_report(EN_TEXT + ' The foreman insists "the bell is our only god".',
                           [dict(c) for c in EN_CLAIMS] + [dict(claim_id="en-ev3", claim_text="the bell is our only god", claim_role="evidence", materiality="supporting",
                                                                 source_refs=[SourceRef(document_id="doc-mill", excerpt="the bell is our only god")])])


def _respond(auditor, report, cfg=None):
    ch = new_channel(auditor, config=cfg) if cfg is not None else new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, report)
    return ch, rc


def test_control_the_shadow_agrees_with_every_receipt(auditor):
    task = run_task(auditor)
    audit = task.audit()
    assert audit.coverage.shadow_run == "run"
    assert not {"OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-008", "OVS-RES-008"} & {f.code for f in audit.report.findings}
    assert not ovs_errors(audit, allow=())


def test_a_dropped_error_finding_is_rcpt_004(auditor, monkeypatch):
    """The live channel ran patched code; the shadow runs the repository's (an in-process shadow cannot see a patch that is
    still active when it runs: it executes the same code, which is why B2-B4 re-derive with their own functions)."""
    orig = TranslatorChannel._receipt

    def drop(self, message_id, direction, status, findings_, **kw):
        return orig(self, message_id, direction, status, [f for f in findings_ if f.code != "INT-REQ-003"], **kw)
    with monkeypatch.context() as mp:
        mp.setattr(TranslatorChannel, "_receipt", drop)
        ch, rc = _respond(auditor, _INVENTED)
    assert not any(f.code == "INT-REQ-003" for f in rc.findings)
    f = [x for x in findings(auditor.audit(ch.uid), "OVS-RCPT-004") if "INT-REQ-003" in x.message]
    assert f and f[0].claim_ids == ["en-ev3"] and f[0].message_ids == [rc.message_id] and f[0].severity == "error"


def test_a_receipt_finding_the_shadow_does_not_reproduce_is_rcpt_005(auditor, monkeypatch):
    orig = TranslatorChannel._receipt

    def extra(self, message_id, direction, status, findings_, **kw):
        if direction == "specialist_to_router":
            findings_ = list(findings_) + [IntegrityFinding(code="INT-HANDOFF-010", severity="warning", message="task type differs", claim_ids=["en-point"])]
        return orig(self, message_id, direction, status, findings_, **kw)
    with monkeypatch.context() as mp:
        mp.setattr(TranslatorChannel, "_receipt", extra)
        ch, rc = _respond(auditor, _INVENTED)
    f = [x for x in findings(auditor.audit(ch.uid), "OVS-RCPT-005") if "INT-HANDOFF-010" in x.message]
    assert f and f[0].severity == "warning" and f[0].claim_ids == ["en-point"]


def test_channel_state_corrupted_between_transfers_gives_another_status_rcpt_008(auditor):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    ch.respond(m.message_id, english_report())
    planted = english_report(report_id="rep-planted", created_at="2026-10-11T11:20:00Z")
    ch.channel.transmitted_reports["rep-planted"] = planted  # never delivered: written into the channel's records
    msg, rf = ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, planted)
    assert msg is not None and rf.status is not TransmissionStatus.REJECTED  # the corrupted channel accepts the forward
    audit = auditor.audit(ch.uid)
    f8 = findings(audit, "OVS-RCPT-008")
    assert f8 and f8[0].message_ids == [rf.message_id] and "REJECTED" in f8[0].message
    assert any("INT-HANDOFF-013" in x.message for x in findings(audit, "OVS-RCPT-004"))
    assert findings(audit, "OVS-PEER-001")  # the live tier already refused to vouch for the forward


def test_an_undecided_engine_run_explains_a_difference_as_res_008(monkeypatch):
    auditor = make_auditor()
    try:
        orig = TranslatorChannel._receipt

        def extra(self, message_id, direction, status, findings_, **kw):
            if direction == "specialist_to_router":
                findings_ = list(findings_) + [IntegrityFinding(code="INT-HANDOFF-010", severity="warning", message="task type differs", claim_ids=["en-point"])]
            return orig(self, message_id, direction, status, findings_, **kw)
        with monkeypatch.context() as mp:
            mp.setattr(TranslatorChannel, "_receipt", extra)
            ch, rc = _respond(auditor, _INVENTED, cfg=SolverConfig(timeout_ms=3000, memory_max_mb=None, rlimit=1))
        assert any(c.formal_status == "TIMEOUT" for c in rc.constraint_results)
        audit = auditor.audit(ch.uid)
        f = [x for x in findings(audit, "OVS-RES-008") if rc.message_id in x.message_ids and "undecided" in x.message]
        assert f and f[0].severity == "warning"
        assert not [x for x in findings(audit, "OVS-RCPT-005") if rc.message_id in x.message_ids]
    finally:
        auditor.close()


def test_the_shadow_is_skipped_and_said_so_for_a_digest_only_journal():
    kr = make_keyring()
    auditor = make_auditor(keyring=kr, journals=JournalSet(kr, max_entries=1))
    try:
        task = run_task(auditor, synthesis=False)
        audit = task.audit()
        assert audit.coverage.shadow_run == "skipped" and any("digest-only" in n for n in audit.coverage.notes)
        assert any(f.code == "OVS-AUDIT-002" for f in audit.report.findings)
        assert audit.state != "AUDIT_PASSED"
    finally:
        auditor.close()


def test_a_patch_still_active_during_the_audit_is_reproduced_by_the_in_process_shadow(auditor, monkeypatch):
    """Documented limit: the shadow executes the same code; a channel patch active while it runs is not visible to it.
    The receipt-level rules still catch the inconsistency the patch leaves (here the summary names a dropped code)."""
    orig = TranslatorChannel._receipt

    def drop(self, message_id, direction, status, findings_, **kw):
        return orig(self, message_id, direction, status, [f for f in findings_ if f.code != "INT-REQ-003"], **kw)
    monkeypatch.setattr(TranslatorChannel, "_receipt", drop)
    ch, rc = _respond(auditor, _INVENTED)
    audit = auditor.audit(ch.uid)
    assert not [x for x in findings(audit, "OVS-RCPT-004") if "INT-REQ-003" in x.message]
    assert findings(audit, "OVS-RCPT-007") and audit.state == "AUDIT_FAILED"


def test_shadow_can_be_turned_off_and_coverage_says_so(auditor):
    task = run_task(auditor, synthesis=False)
    assert task.audit(shadow=False).coverage.shadow_run == "not_run"
