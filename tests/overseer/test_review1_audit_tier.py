"""Regression tests for the audit-tier defects found by adversarial review round 1 of the Overseer.

* the journal bound: the router's clearance records never use up the event budget, and a transfer journaled
  digest-only is never treated as checkable (OVS-AUDIT-005, live and FINAL);
* an insider re-signing a status with the engine key and emitting it WITHOUT its problem is still replayed from the
  citing outcome's problem (RES-007); a constraint status re-signed that way is exposed by R2's arithmetic (RES-007)
  and the unreplayable result is AUDIT-005;
* L2 implied findings (RCPT-004): a finding the receipt's own structured results imply, dropped or downgraded by a
  patched channel, is named live with the shadow off; the identity checks are re-run on the journaled envelope;
* a fault decided live (TRN-007) survives the eviction of its result into the batch audit;
* a clearance issued after a task audit failed a transfer on a batch-only code is never better than that audit.
"""
from __future__ import annotations

import ast
import pathlib
import uuid

import epinoic_logic
from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.engine import sink
from epinoic_logic.engine.provenance import sign_result
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.overseer import JournalSet, may_act, may_release
from epinoic_logic.overseer.checks.receipts import FIXED_SEVERITY, VARIABLE_SEVERITY
from epinoic_logic.translate.outcome import compose_outcome

from .conftest import (
    DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, KEY, english_report, findings, int_problem, make_auditor, make_keyring, new_channel, problems_fn, run_task,
)
from .test_audit_joint_divergence import _merged_synthesis


def _codes(audit, severity: str = "error") -> set[str]:
    return {f.code for f in audit.report.findings if f.severity == severity}


# ============================================================================================ the journal bound (blocker)
def test_clearance_records_never_use_up_the_event_budget():
    kr = make_keyring()
    auditor = make_auditor(keyring=kr, journals=JournalSet(kr, max_entries=6))
    try:
        def many_clearances(task):
            for _ in range(60):
                auditor.clearance(task.uid, task.mids["rep_en"], receipt=task.receipts["rep_en"])
        task = run_task(auditor, before_synthesis=many_clearances)
        events = [e.event for e in auditor.journal(task.uid).entries() if e.event is not None]
        assert len(events) == 6 and not any(ev.digest_only for ev in events)
        assert sum(1 for e in auditor.journal(task.uid).entries() if e.kind == "clearance") >= 60
    finally:
        auditor.close()


def test_a_forged_result_past_the_journal_bound_never_clears():
    """The reviewer's blocker: past the bound every event was digest-only and an unsigned ENTAILED passed live and FINAL."""
    def forge(out, claim, report):
        v = out.verification.model_copy(update={"signature": None, "signature_key_id": None, "status": S.ENTAILED})
        return out.model_copy(update={"verification": v, "display_status": S.ENTAILED})
    kr = make_keyring()
    auditor = make_auditor(keyring=kr, journals=JournalSet(kr, max_entries=1))
    try:
        ch = new_channel(auditor)
        ch.channel.verify_claim_fn = problems_fn({"en-point": int_problem("en-point", "work_hours", 5, op="gt", bound=8)}, transform=forge)
        m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = ch.respond(m.message_id, english_report())
        assert next(o for o in rc.outcomes if o.claim_id == "en-point").display_status is S.ENTAILED
        ev = [e.event for e in auditor.journal(ch.uid).entries() if e.event is not None]
        assert ev[-1].digest_only
        clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-AUDIT-005" in clr.codes and not may_act(rc, clr)
        audit = auditor.audit(ch.uid, final=True)
        assert audit.state == "AUDIT_FAILED" and audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
        f = findings(audit, "OVS-AUDIT-005")
        assert f and f[0].severity == "error" and rc.message_id in f[0].message_ids
    finally:
        auditor.close()


def test_a_synthesis_citing_a_digest_only_report_fails_with_it_and_is_never_released():
    kr = make_keyring()
    auditor = make_auditor(keyring=kr, journals=JournalSet(kr, max_entries=4))
    try:
        task = run_task(auditor)  # events 5 (the History report) and 6 (the synthesis) are digest-only
        audit = task.audit(final=True)
        assert audit.transfer_states[task.mids["rep_hi"]] == "AUDIT_FAILED"
        assert audit.transfer_states[task.mids["syn"]] == "AUDIT_FAILED"
        assert not findings(audit, "OVS-SYN-001")  # the digest-only delivery is a delivery: no false citation finding
        assert not may_release(task.receipts["syn"], audit, auditor.keyring, audits=auditor.audits(task.uid), journal=auditor.journal(task.uid))
    finally:
        auditor.close()


# ============================================================================================ insider re-signing without the problem
def _resign(with_problem: bool):
    def transform(out, claim, report):
        if out.verification is None:
            return out
        new_status = S.ENTAILED if out.verification.status is S.COUNTEREXAMPLE else S.COUNTEREXAMPLE
        forged = sign_result(out.verification.model_copy(update={"status": new_status, "result_id": "forged-" + uuid.uuid4().hex[:12], "signature": None,
                                                                 "signature_key_id": None}), KEY, out.verification.signature_key_id)
        sink.emit(forged, out.translation.problem if with_problem else None)
        return compose_outcome(claim, out.translation, forged, signing_key=KEY, key_id=out.verification.signature_key_id)
    return transform


def test_an_insider_resigned_outcome_emitted_without_its_problem_is_replayed_from_the_receipt():
    for with_problem in (True, False):
        auditor = make_auditor(shadow="off")
        try:
            ch = new_channel(auditor)
            ch.channel.verify_claim_fn = problems_fn({"en-point": int_problem("en-point", "work_hours", 5, op="gt", bound=8)}, transform=_resign(with_problem))
            m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
            _reply, rc = ch.respond(m.message_id, english_report())
            o = next(o for o in rc.outcomes if o.claim_id == "en-point")
            assert o.display_status is S.ENTAILED  # 5 > 8 is false; the forged signed status says otherwise
            auditor.drain()
            clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
            assert clr.state == "AUDIT_FAILED" and "OVS-RES-007" in clr.codes, (with_problem, clr)
            audit = auditor.audit(ch.uid, final=True)
            assert "OVS-RES-007" in _codes(audit) and audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
        finally:
            auditor.close()


_LONG = EN_TEXT + " " + " ".join(["The mill wheel kept turning through the night."] * 12)


def test_an_insider_resigned_constraint_status_without_its_problem_is_exposed_by_r2():
    orig = TranslatorChannel._formal_bound

    def insider(self, req, c, measured):
        token = sink._ACTIVE.set(())  # the genuine run is kept out of the channel's capture
        try:
            res = orig(self, req, c, measured)
        finally:
            sink._ACTIVE.reset(token)
        if res.status is S.COUNTEREXAMPLE:
            res = sign_result(res.model_copy(update={"status": S.ENTAILED, "result_id": "forged-" + uuid.uuid4().hex[:12], "signature": None,
                                                     "signature_key_id": None}), self.key, self.key_id)
        sink.emit(res, None)
        return res

    auditor = make_auditor(shadow="off", replay_mode="inline", eager=True)
    try:
        TranslatorChannel._formal_bound = insider
        try:
            ch = new_channel(auditor)
            m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
            _reply, rc = ch.respond(m.message_id, english_report(_LONG))
        finally:
            TranslatorChannel._formal_bound = orig
        cr = next(c for c in rc.constraint_results if c.formal_status is not None)
        assert cr.formal_status == "ENTAILED" and cr.satisfied is True and not any(f.code == "INT-REQ-005" for f in rc.findings)
        auditor.drain()
        clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and {"OVS-RES-007", "OVS-AUDIT-005"} <= set(clr.codes)
        audit = auditor.audit(ch.uid, final=True)
        f = [x for x in findings(audit, "OVS-RES-007") if x.formal_result_id == cr.formal_result_id]
        assert f and "measures" in f[0].message
    finally:
        auditor.close()


# ============================================================================================ L2 implied findings
def _dropping(codes, *, downgrade: bool = False):
    orig = TranslatorChannel._finish

    def fin(self, msg, direction, findings_, *a, **kw):
        if downgrade:
            kept = [f.model_copy(update={"severity": "warning"}) if f.code in codes else f for f in findings_]
        else:
            kept = [f for f in findings_ if f.code not in codes]
        return orig(self, msg, direction, kept, *a, **kw)
    return fin


def test_a_dropped_word_limit_finding_is_named_live_with_the_shadow_off(monkeypatch):
    auditor = make_auditor(shadow="off")
    try:
        monkeypatch.setattr(TranslatorChannel, "_finish", _dropping({"INT-REQ-005"}))
        ch = new_channel(auditor)
        m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = ch.respond(m.message_id, english_report(_LONG))
        assert any(c.satisfied is False for c in rc.constraint_results) and not rc.findings
        clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes and not may_act(rc, clr)
        f = [x for x in findings(auditor.audit(ch.uid), "OVS-RCPT-004") if "INT-REQ-005" in x.message]
        assert f and rc.message_id in f[0].message_ids
    finally:
        auditor.close()


def test_a_downgraded_word_limit_finding_is_named_live(monkeypatch):
    auditor = make_auditor(shadow="off")
    try:
        monkeypatch.setattr(TranslatorChannel, "_finish", _dropping({"INT-REQ-005"}, downgrade=True))
        ch = new_channel(auditor)
        m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = ch.respond(m.message_id, english_report(_LONG))
        assert [(f.code, f.severity) for f in rc.findings] == [("INT-REQ-005", "warning")]
        audit = auditor.audit(ch.uid)
        assert [x for x in findings(audit, "OVS-RCPT-004") if "INT-REQ-005" in x.message and "severity warning" in x.message]
        assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        auditor.close()


def test_a_dropped_impersonation_finding_is_named_live(monkeypatch):
    """A report the History specialist sent in answer to the English request, its blocking identity findings dropped."""
    import epinoic_logic.channel.bus as bus
    codes = {"INT-ENV-010", "INT-HANDOFF-003", "INT-HANDOFF-010", "INT-REQ-001"}
    orig_block = bus._is_blocking
    auditor = make_auditor(shadow="off")
    try:
        monkeypatch.setattr(TranslatorChannel, "_finish", _dropping(codes))
        monkeypatch.setattr(bus, "_is_blocking", lambda fs: orig_block([f for f in fs if f.code not in codes]))
        ch = new_channel(auditor)
        m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = ch.respond(m.message_id, english_report(agent="history-specialist"))
        assert rc.status.value == "ACCEPTED" or rc.status.value == "ACCEPTED_WITH_FINDINGS"
        clr = auditor.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes
        msgs = " ".join(x.message for x in findings(auditor.audit(ch.uid), "OVS-RCPT-004"))
        assert "INT-REQ-001" in msgs and "INT-HANDOFF-003" in msgs
    finally:
        auditor.close()


def test_control_genuine_receipts_imply_nothing_missing(auditor):
    task = run_task(auditor)
    ch = new_channel(auditor)
    m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _reply, rc = ch.respond(m.message_id, english_report(_LONG))
    assert any(f.code == "INT-REQ-005" for f in rc.findings)
    assert not findings(task.audit(), "OVS-RCPT-004") and not findings(auditor.audit(ch.uid), "OVS-RCPT-004")


def _emitted_severities() -> dict[str, set[str]]:
    """Every ``IntegrityFinding(code="INT-...", severity=...)`` the package's source emits outside the Overseer."""
    root = pathlib.Path(epinoic_logic.__file__).parent
    out: dict[str, set[str]] = {}
    for p in root.rglob("*.py"):
        if "overseer" in p.relative_to(root).parts:
            continue
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            code, sev = kw.get("code"), kw.get("severity")
            if isinstance(code, ast.Constant) and isinstance(code.value, str) and code.value.startswith("INT-") and sev is not None:
                out.setdefault(code.value, set()).add(sev.value if isinstance(sev, ast.Constant) else "<case>")
    return out


def test_the_fixed_severity_table_is_what_the_channel_code_emits():
    emitted = _emitted_severities()
    fixed = {c: next(iter(s)) for c, s in emitted.items() if len(s) == 1 and "<case>" not in s}
    variable = {c for c, s in emitted.items() if len(s) > 1 or "<case>" in s}
    # the joint-check undecided codes are emitted through a parameter at warning
    assert {c: v for c, v in FIXED_SEVERITY.items() if c in fixed} == fixed
    assert set(fixed) <= set(FIXED_SEVERITY) and variable == set(VARIABLE_SEVERITY)
    assert set(FIXED_SEVERITY) - set(fixed) <= {"INT-CONFLICT-004", "INT-SYNTH-003"}


# ============================================================================================ live findings survive eviction
def test_a_summary_fault_found_live_survives_the_eviction_of_its_result():
    from .test_translation_oversight import POINT, run, trn

    def overclaim(out, claim, rep):
        return out.model_copy(update={"summary": "ENTAILED: the claim is proven true and needs no further review."})
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run(transform=overclaim, auditor=aud)
        aud.drain()
        live = aud.transfer_audit(ch.uid, rc.message_id)
        assert "OVS-TRN-007" in _codes(live)
        rid = next(o.verification.result_id for o in rc.outcomes if o.claim_id == POINT)
        aud.store._evict(rid)  # another task's activity evicted it under the global bound
        assert aud.store.live(rid) is None and aud.store.is_tombstoned(rid)
        audit = aud.audit(ch.uid, final=True)
        assert trn(audit, "OVS-TRN-007") and audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()


def test_the_summary_is_rechecked_against_the_verified_receipt_copy_of_an_evicted_result():
    from .test_translation_oversight import POINT, run, trn

    def overclaim(out, claim, rep):
        return out.model_copy(update={"summary": "ENTAILED: the claim is proven true and needs no further review."})
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run(transform=overclaim, auditor=aud)
        rid = next(o.verification.result_id for o in rc.outcomes if o.claim_id == POINT)
        aud.store._evict(rid)
        from epinoic_logic.overseer import OverseerView, run_overseer_checks
        result = run_overseer_checks(OverseerView.from_journal(aud.journal(ch.uid), aud.store), keyring=aud.keyring, store=aud.store, shadow=False)
        assert [f for _s, f in result.findings if f.code == "OVS-TRN-007"]  # the batch tier alone, from the receipt's verified copy
    finally:
        aud.close()


# ============================================================================================ clearance after a failing batch audit
def test_a_clearance_after_a_batch_audit_failed_the_transfer_is_never_better(auditor):
    task = run_task(auditor, synthesis_obj=_merged_synthesis())
    audit = task.audit()
    assert audit.transfer_states[task.mids["syn"]] == "AUDIT_FAILED" and findings(audit, "OVS-DIV-001")
    clr = auditor.clearance(task.uid, task.mids["syn"], receipt=task.receipts["syn"])
    assert clr.state == "AUDIT_FAILED" and "OVS-DIV-001" in clr.codes and not may_act(task.receipts["syn"], clr)
    final = task.audit(final=True)
    assert final.transfer_states[task.mids["syn"]] == "AUDIT_FAILED"
    from epinoic_logic.overseer.policy import check_before_acting

    class Hub:
        def clearance(self, key, mid, *, receipt=None, wait_ms=0):
            return auditor.clearance(task.uid, mid, receipt=receipt, wait_ms=wait_ms)
    dec = check_before_acting(Hub(), task.uid, task.receipts["syn"])
    assert not dec.allowed and dec.state == "AUDIT_FAILED"
