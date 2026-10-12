"""The signed audit: HMAC under the audit key, report digest, scope statement, the ``overseer_audit/1.0`` envelope,
determinism, supersession, clearance precedence, the code table, and fail-closed internal errors."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.statuses import SCOPE_STATEMENT
from epinoic_logic.integrity import AgentMessage, AgentRole, MessageLog, ROLE_CONTRACTS, payload_hash, verify_message
from epinoic_logic.integrity.contracts import verify_report_digest
from epinoic_logic.overseer import (
    AUDIT_SCOPE_SENTENCE, OVS_CODES, EngineKey, KeyRing, OverseerView, audit_envelope, ovs_finding, run_overseer_checks, sign_audit, transfer_states,
    verify_audit,
)
from epinoic_logic.overseer.checks import fidelity
from epinoic_logic.overseer.codes import is_agent_code, severity_of

from .conftest import KEY, SECRET, findings, int_problem, make_auditor, run_task

CONFLICT = dict(en_problems={"en-point": int_problem("en-point", "x", 7, op="gt", bound=5)},
                hi_problems={"h1.1": int_problem("h1.1", "x", 2, op="lt", bound=3)})


# ------------------------------------------------------------------------------------------- signing
def test_audit_signature_verifies_and_any_edit_breaks_it(auditor, keyring):
    task = run_task(auditor)
    audit = task.audit()
    assert audit.signature_key_id == "overseer-audit" and verify_audit(audit, keyring)
    assert verify_report_digest(audit.report)
    assert not verify_audit(audit.model_copy(update={"state": "AUDIT_PASSED"} if audit.state != "AUDIT_PASSED" else {"final": True}), keyring)
    edited_report = audit.report.model_copy(deep=True)
    edited_report.findings = []
    assert not verify_audit(audit.model_copy(update={"report": edited_report}), keyring)
    assert not verify_audit(audit, KeyRing({"hub": EngineKey(KEY)}, SECRET[::-1]))
    assert not verify_audit(audit.model_copy(update={"signature": None}), keyring)
    assert not verify_audit(audit.model_copy(update={"signature_key_id": "hub"}), keyring)


def test_every_audit_carries_the_scope_statement(auditor):
    audit = run_task(auditor, synthesis=False).audit()
    assert audit.scope_statement.startswith(SCOPE_STATEMENT)
    assert AUDIT_SCOPE_SENTENCE in audit.scope_statement
    assert "It does not show that any claim is true or any reading correct." in audit.scope_statement


def test_audit_head_and_store_digest(auditor):
    task = run_task(auditor)
    audit = task.audit()
    j = auditor.journal(task.uid)
    assert audit.journal_head.index <= j.head()[0]
    assert audit.journal_head.entry_hash == j.entries()[audit.journal_head.index - 1].entry_hash
    from epinoic_logic.overseer.view import cited_results
    cited = {r for t in auditor.view(task.uid).transfers if t.receipt is not None for r, _k, _p in cited_results(t.receipt)}
    assert audit.store_digest == auditor.store.digest(cited)
    assert audit.message_ids == [t for t in audit.transfer_states]


def test_audit_envelope_is_an_overseer_contract_signed_under_the_audit_key(auditor, keyring):
    audit = run_task(auditor, synthesis=False).audit()
    env = audit_envelope(audit, keyring)
    assert env.contract == "overseer_audit/1.0" and env.sender_role is AgentRole.OVERSEER and env.sender_agent_id == "overseer-auditor"
    assert verify_message(env, keyring.subkey("audit")) and not verify_message(env, KEY)
    log = MessageLog(signing_key=keyring.subkey("audit"), request_id=audit.request_id)
    assert log.accept(env) == []
    assert ROLE_CONTRACTS["overseer_audit"] == frozenset({AgentRole.OVERSEER}) and ROLE_CONTRACTS["overseer_verdict"] == frozenset({AgentRole.OVERSEER})


@pytest.mark.parametrize("contract", ["overseer_audit/1.0", "overseer_verdict/1.0"])
def test_a_specialist_cannot_issue_overseer_contracts(contract):
    payload = {"x": 1}
    msg = AgentMessage(message_id="m1", request_id="r", task_id="t", sender_agent_id="english-specialist", sender_role=AgentRole.SPECIALIST,
                       recipient_role=AgentRole.ROUTER, contract=contract, payload=payload, payload_sha256=payload_hash(payload), created_at="2026-10-11T10:00:00Z")
    assert [f.code for f in MessageLog().accept(msg)] == ["INT-ENV-007"]


def test_message_log_messages_in_acceptance_order_without_duplicates():
    log = MessageLog()
    msgs = []
    for i in range(3):
        p = {"i": i}
        m = AgentMessage(message_id=f"m{i}", request_id="r", task_id="t", sender_agent_id="router", sender_role=AgentRole.ROUTER, recipient_role=AgentRole.SPECIALIST,
                         contract="task_request/1.0", payload=p, payload_sha256=payload_hash(p), created_at="2026-10-11T10:00:00Z")
        log.accept(m)
        msgs.append(m)
    log.accept(msgs[1])  # a replay is not stored twice
    assert [m.message_id for m in log.messages()] == ["m0", "m1", "m2"] and isinstance(log.messages(), tuple)


# ------------------------------------------------------------------------------------------- determinism, supersession
def _shape(audit):
    return [(f.code, f.severity, f.message, tuple(f.message_ids), tuple(f.claim_ids), tuple(f.report_ids), f.formal_result_id, tuple(f.related_result_ids))
            for f in audit.report.findings]


def test_the_same_journal_and_store_give_the_same_report(auditor, monkeypatch):
    import epinoic_logic.channel.bus as bus
    monkeypatch.setattr(bus, "check_cross_report_consistency", lambda *a, **k: (None, []))
    task = run_task(auditor, **CONFLICT)
    a1, a2 = task.audit(), task.audit()
    assert a1.audit_id != a2.audit_id and a2.supersedes == a1.audit_id
    assert _shape(a1) == _shape(a2) and findings(a1, "OVS-JOINT-001")
    assert a1.report.formal_result_ids == a2.report.formal_result_ids and a1.report.checks_run == a2.report.checks_run
    assert a1.transfer_states == a2.transfer_states and a1.divergences == a2.divergences
    # the pure function over a fresh view of the same journal gives the same findings
    st = auditor._channels[task.uid]
    r = run_overseer_checks(OverseerView.from_journal(st.journal, auditor.store), keyring=auditor.keyring, store=auditor.store, live=st.live(), registry=st.registry,
                            replays=auditor._replays(st), rederived=auditor._rederived(st), shadow=True)
    assert [(f.code, f.message) for f in r.report.findings] == [(f.code, f.message) for f in a1.report.findings]


def test_a_transfer_audit_is_signed_and_scoped_to_one_transfer(auditor, keyring):
    task = run_task(auditor, synthesis=False)
    ta = auditor.transfer_audit(task.uid, task.mids["rep_en"])
    assert ta.scope == "transfer" and ta.mode == "live" and ta.message_ids == [task.mids["rep_en"]] and verify_audit(ta, keyring)
    assert auditor.transfer_audit(task.uid, task.mids["rep_en"]).supersedes == ta.audit_id


# ------------------------------------------------------------------------------------------- clearance precedence
def test_clearance_precedence_and_agent_codes_never_change_a_clearance(auditor):
    task = run_task(auditor, synthesis=False)
    view = auditor.view(task.uid)
    mid = task.mids["req_en"]
    agent = ovs_finding("OVS-AGENT-001", "an overseer agent's statement refuted", message_ids=[mid])
    warn = ovs_finding("OVS-AUDIT-002", "coverage lost", message_ids=[mid])
    err = ovs_finding("OVS-CUST-001", "payload altered", message_ids=[mid])
    assert transfer_states(view, [(1, agent)])[0][mid] == "AUDIT_PASSED"
    assert transfer_states(view, [(1, warn)])[0][mid] == "AUDIT_PASSED_WITH_FINDINGS"
    assert transfer_states(view, [(1, warn)], {mid: {"r1"}})[0][mid] == "AUDIT_PENDING"
    states, task_state = transfer_states(view, [(1, err)], {mid: {"r1"}})
    assert states[mid] == "AUDIT_FAILED" and task_state == "AUDIT_FAILED"
    # a response depends on its request: it cannot pass while the request failed
    assert states[task.mids["rep_en"]] == "AUDIT_FAILED"


def test_an_internal_check_failure_is_audit_001_and_fails_closed(auditor, monkeypatch):
    def boom(ctx, t):
        raise RuntimeError("check crashed")
    monkeypatch.setattr(fidelity, "check_fidelity", boom)
    task = run_task(auditor, synthesis=False)
    audit = task.audit()
    f = findings(audit, "OVS-AUDIT-001")
    assert f and "fidelity" in f[0].message and "cannot pass" in f[0].message
    assert audit.transfer_states[task.mids["rep_en"]] == "AUDIT_FAILED" and audit.state == "AUDIT_FAILED"


def test_run_overseer_checks_never_raises_on_a_broken_view(auditor):
    task = run_task(auditor, synthesis=False)
    view = auditor.view(task.uid)
    view.transfers[1].receipt = "not a receipt"  # type: ignore[assignment]
    result = run_overseer_checks(view, keyring=auditor.keyring, store=auditor.store, shadow=False)
    assert any(f.code == "OVS-AUDIT-001" for f in result.report.findings) and result.task_state == "AUDIT_FAILED"


# ------------------------------------------------------------------------------------------- the code table
def test_the_code_table_has_every_code_once_with_one_severity():
    # design section 16, with the seven translator-oversight codes of section 18, the five consolidation codes of
    # section 19 (OVS-CONS-001..004, OVS-REP-001) and OVS-AUDIT-005 (review round 1: a check a transfer needs cannot run)
    assert len(OVS_CODES) == 71
    families = {}
    for code, (sev, stage, meaning) in OVS_CODES.items():
        assert code.startswith("OVS-") and sev in ("error", "warning", "info") and stage and meaning
        families[code.split("-")[1]] = families.get(code.split("-")[1], 0) + 1
    assert families == {"CUST": 6, "RCPT": 8, "RES": 10, "FORM": 4, "FID": 9, "PEER": 3, "SYN": 3, "JOINT": 4, "DIV": 2, "AUDIT": 5, "AGENT": 5, "TRN": 7,
                        "CONS": 4, "REP": 1}
    assert {OVS_CODES[c][0] for c in ("OVS-CONS-004", "OVS-REP-001", "OVS-AUDIT-005")} == {"error"} and OVS_CODES["OVS-CONS-003"][0] == "info"
    assert severity_of("OVS-RES-002") == "warning" and severity_of("OVS-PEER-003") == "info" and is_agent_code("OVS-AGENT-004")
    f = ovs_finding("OVS-RES-008", "x", message_ids=["m", "m", ""], formal_result_id="r", related_result_ids=["r", "q"])
    assert f.severity == "warning" and f.message_ids == ["m"] and f.related_result_ids == ["q"] and f.deterministic
    with pytest.raises(KeyError):
        ovs_finding("OVS-NOPE-001", "x")


def test_non_success_is_never_presented_as_passed(auditor):
    auditor_pending = make_auditor(eager=False)
    try:
        task = run_task(auditor_pending, synthesis=False)
        clr = auditor_pending.clearance(task.uid, task.mids["rep_en"])
        assert clr.state == "AUDIT_PENDING"
    finally:
        auditor_pending.close()
    final_inline = run_task(auditor, synthesis=False).audit(final=True)
    assert any(f.code == "OVS-AUDIT-002" and "inline" in f.message for f in final_inline.report.findings)
    assert final_inline.state != "AUDIT_PASSED"
