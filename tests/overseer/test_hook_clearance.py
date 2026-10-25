"""Clearance through the hub and the router policy (design section 7; tamper cases T1, T2, T2c, T5, T13).

The router asks ``hub.clearance`` immediately before acting, presenting the receipt it holds, and acts only when
``policy.may_act(receipt, clearance)``. The receipt the router presents is checked (T2): a flipped status, an edited
summary or formal status on the router's own copy, or on the channel's shared copy, is RCPT-001 naming the field, and
the transfer is not acted on. ``may_act`` also refuses a REJECTED receipt, a receipt edited after its clearance, a
clearance for another transfer and anything that is not a clearance. PENDING is never acted on: the router waits at
most 250 ms, then the transfer is held for the batch audit. ``may_release`` gates the synthesis on a FINAL, signed,
latest, unsuperseded task audit that covers the channel as it stands."""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.integrity import AgentRole
from epinoic_logic.integrity.contracts import AgentMessage, payload_hash
from epinoic_logic.overseer import (
    MAX_PENDING_WAIT_MS, TransferClearance, act_decision, bounded_wait_ms, check_before_acting, may_act, may_release, receipt_digest,
    release_decision, sign_audit,
)

from .conftest import EN_INPUT, DOC, codes_of, english_report, findings, make_auditor
from .test_hook_hub import BAD_QUOTE_CLAIMS, BAD_QUOTE_TEXT, HubTask, audited_hub, hub_task


@pytest.fixture
def hub():
    h = audited_hub()
    yield h
    h.close()


def with_findings_task(hub) -> HubTask:
    """A task whose English response is delivered ACCEPTED_WITH_FINDINGS (a quotation the extract does not hold)."""
    task = hub_task(hub, en_report=english_report(text=BAD_QUOTE_TEXT, claims=BAD_QUOTE_CLAIMS))
    rc = task.receipts["rep_en"]
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and "INT-REQ-003" in {f.code for f in rc.findings}
    return task


def presented(rc, **update):
    return rc.model_copy(deep=True, update=update)


# ============================================================================================ the receipt the router presents (T2)
def test_a_genuine_receipt_clears_and_may_be_acted_on(hub):
    task = with_findings_task(hub)
    rc = task.receipts["rep_en"]
    clr = hub.clearance(task.key, rc.message_id, receipt=rc)
    assert clr.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and clr.receipt_id == rc.receipt_id
    assert clr.presented_receipt_sha256 == clr.receipt_sha256 == receipt_digest(rc)
    assert may_act(rc, clr) and act_decision(rc, clr).reason == "ok"


def test_t2_the_router_flips_its_own_copy_and_presents_it(hub):
    task = with_findings_task(hub)
    rc = task.receipts["rep_en"]
    flipped = presented(rc, status=TransmissionStatus.ACCEPTED)
    clr = hub.clearance(task.key, rc.message_id, receipt=flipped)
    assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-001" in clr.codes
    f = [x for x in findings(hub.audit(task.key), "OVS-RCPT-001") if rc.message_id in x.message_ids]
    assert f and "status" in f[0].message and rc.receipt_id in f[0].message
    assert not may_act(flipped, clr) and not may_act(rc, clr)
    assert task.ch.receipts[1].status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # the channel's copy is intact


def test_t2_the_router_flips_the_shared_receipt_object(hub):
    task = with_findings_task(hub)
    rc = task.receipts["rep_en"]
    assert rc is task.ch.receipts[1]  # receipts are shared with the router (gap G2)
    rc.status = TransmissionStatus.ACCEPTED
    clr = hub.clearance(task.key, rc.message_id)  # nothing presented: the channel's (edited) copy is compared
    assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-001" in clr.codes and not may_act(rc, clr)


@pytest.mark.parametrize("field", ["summary", "constraint_formal_status", "findings_dropped"])
def test_t2c_t5_other_edits_of_the_router_copy_are_named(hub, field):
    task = with_findings_task(hub)
    rc = task.receipts["rep_en"]
    if field == "summary":
        edited = presented(rc, summary="Delivered with no findings.")
    elif field == "constraint_formal_status":
        cr = rc.constraint_results[0].model_copy(update={"formal_status": "COUNTEREXAMPLE"})
        edited = presented(rc, constraint_results=[cr] + list(rc.constraint_results[1:]))
    else:
        edited = presented(rc, findings=[])
    clr = hub.clearance(task.key, rc.message_id, receipt=edited)
    assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-001" in clr.codes and not may_act(edited, clr)
    named = {"summary": "summary", "constraint_formal_status": "constraint_results", "findings_dropped": "findings"}[field]
    assert any(named in f.message for f in findings(hub.audit(task.key), "OVS-RCPT-001"))


def test_t1_a_log_payload_edited_after_receipt_fails_the_transfer_and_its_dependants(hub):
    task = hub_task(hub)
    hub.channel_for(task.key).log.get(task.mids["rep_en"]).payload["claims"][0]["claim_text"] = "The writer presents work as joyful"
    clr = hub.clearance(task.key, task.mids["rep_en"])
    assert clr.state == "AUDIT_FAILED" and "OVS-CUST-001" in clr.codes
    fwd = hub.clearance(task.key, task.mids["fwd"], receipt=task.receipts["fwd"])
    assert fwd.state == "AUDIT_FAILED" and not may_act(task.receipts["fwd"], fwd)  # the forward depends on the delivery


def test_t13_a_message_written_around_the_channel_never_clears(hub):
    task = hub_task(hub, synthesis=False)
    payload = english_report(report_id="rep-sneaked").model_dump(mode="json", exclude_none=True)
    msg = AgentMessage(message_id="m-sneaked", request_id="req-ovs", task_id="task-ovs", sender_agent_id="english-specialist",
                       sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0", payload=payload,
                       payload_sha256=payload_hash(payload), in_reply_to=task.mids["req_en"], created_at="2026-10-11T11:00:00Z")
    assert task.ch.log.accept(msg) == []
    clr = hub.clearance(task.key, "m-sneaked")
    assert clr.state == "AUDIT_FAILED" and clr.codes == ["OVS-CUST-003"]
    assert "OVS-CUST-003" in codes_of(hub.audit(task.key))


def test_repeated_clearances_of_an_untouched_transfer_agree(hub):
    task = hub_task(hub)
    states = {(c.state, tuple(c.codes)) for c in (hub.clearance(task.key, task.mids["syn"], receipt=task.receipts["syn"]) for _ in range(3))}
    assert len(states) == 1


# ============================================================================================ may_act refusals
def test_may_act_refuses_a_rejected_receipt_even_when_the_audit_passes(hub):
    task = hub_task(hub, synthesis=False)
    _m, _req, rq = hub.dispatch(task.key, "rogue-agent", EN_INPUT, [DOC])
    assert rq.status is TransmissionStatus.REJECTED
    clr = hub.clearance(task.key, rq.message_id, receipt=rq)
    assert clr.state == "AUDIT_PASSED"  # the audit vouches for the receipt, not for the content
    d = act_decision(rq, clr)
    assert not d.allowed and "REJECTED" in d.reason


def test_may_act_refuses_a_receipt_edited_after_its_clearance(hub):
    task = with_findings_task(hub)
    rc = task.receipts["rep_en"]
    clr = hub.clearance(task.key, rc.message_id, receipt=rc)
    assert may_act(rc, clr)
    rc.summary = rc.summary + " Verified."
    assert not may_act(rc, clr)
    rc2 = presented(task.receipts["req_en"])
    assert not may_act(rc2, clr)  # a clearance for another transfer


@pytest.mark.parametrize("bad", ["none", "dict", "namespace", "other_receipt_id", "pending", "failed"])
def test_may_act_refuses_anything_that_is_not_a_passing_clearance_for_the_receipt(hub, bad):
    task = hub_task(hub, synthesis=False)
    rc = task.receipts["rep_en"]
    clr = hub.clearance(task.key, rc.message_id, receipt=rc)
    assert may_act(rc, clr)
    forged = {
        "none": None,
        "dict": clr.model_dump(),
        "namespace": SimpleNamespace(**clr.model_dump()),
        "other_receipt_id": clr.model_copy(update={"receipt_id": "another"}),
        "pending": clr.model_copy(update={"state": "AUDIT_PENDING"}),
        "failed": clr.model_copy(update={"state": "AUDIT_FAILED"}),
    }[bad]
    d = act_decision(rc, forged)
    assert not d.allowed and d.hold == (bad == "pending")
    assert not may_act(None, clr) and not may_act("receipt", clr)


# ============================================================================================ bounded PENDING wait
def test_bounded_wait_ms_clamps_every_request():
    assert MAX_PENDING_WAIT_MS == 250
    for asked, got in ((0, 0), (-5, 0), (100, 100), (250, 250), (10_000, 250), (math.inf, 250), (math.nan, 0), ("soon", 0), (None, 0), (12.9, 12)):
        assert bounded_wait_ms(asked) == got


def test_the_hub_bounds_the_whole_wait_by_one_deadline(hub, monkeypatch):
    """Replay and re-derivation share one deadline: a slow replay leaves less time for re-derivation, never more."""
    import time
    task = hub_task(hub, synthesis=False)
    replayer = hub.auditor.replayer
    waits: list[tuple[str, float]] = []
    passed: list[int] = []
    real_drain, real_tasks, real_clearance = replayer.drain, replayer.wait_tasks, hub.auditor.clearance

    def slow_drain(timeout_s=None, **kw):
        waits.append(("drain", timeout_s))
        time.sleep(0.15)
        return real_drain(timeout_s=timeout_s, **kw)
    monkeypatch.setattr(replayer, "drain", slow_drain)
    monkeypatch.setattr(replayer, "wait_tasks", lambda timeout_s: (waits.append(("tasks", timeout_s)), real_tasks(timeout_s))[1])
    monkeypatch.setattr(hub.auditor, "clearance", lambda uid, mid, **kw: (passed.append(kw["wait_ms"]), real_clearance(uid, mid, **kw))[1])
    for asked in (0, 100, 60_000):
        waits.clear()
        t0 = time.monotonic()
        hub.clearance(task.key, task.mids["rep_en"], wait_ms=asked)
        spent = time.monotonic() - t0
        if asked == 0:
            assert waits == []
            continue
        budget = min(asked, MAX_PENDING_WAIT_MS) / 1000
        assert waits[0] == ("drain", budget)
        assert all(kind == "tasks" and t <= budget - 0.14 for kind, t in waits[1:])
        assert spent < budget + 0.1
    assert passed == [0, 0, 0]  # the auditor itself never waits again


class _PendingHub:
    """A hub whose clearance stays PENDING (a replay that never finishes): records every wait asked for."""

    def __init__(self, inner, task, *, pending_calls: int):
        self.inner, self.task, self.waits, self.pending_calls = inner, task, [], pending_calls

    def clearance(self, task_key, message_id, *, receipt=None, wait_ms=0):
        self.waits.append(wait_ms)
        clr = self.inner.clearance(task_key, message_id, receipt=receipt, wait_ms=wait_ms)
        if len(self.waits) <= self.pending_calls:
            return clr.model_copy(update={"state": "AUDIT_PENDING", "pending_result_ids": ["r-outstanding"]})
        return clr


def test_a_transfer_still_pending_after_the_bounded_wait_is_held(hub):
    task = hub_task(hub, synthesis=False)
    rc = task.receipts["rep_en"]
    stuck = _PendingHub(hub, task, pending_calls=99)
    d = check_before_acting(stuck, task.key, rc, wait_ms=60_000)
    assert not d.allowed and d.hold and d.state == "AUDIT_PENDING" and stuck.waits == [0, 250]
    late = _PendingHub(hub, task, pending_calls=1)
    d = check_before_acting(late, task.key, rc)
    assert d.allowed and not d.hold and late.waits == [0, 250]
    quick = _PendingHub(hub, task, pending_calls=0)
    assert check_before_acting(quick, task.key, rc).allowed and quick.waits == [0]


def test_a_real_pending_transfer_clears_within_the_wait():
    """Inline mode without eager replay: the live asynchronous tier is outstanding until the router's wait runs it."""
    h = audited_hub(auditor=make_auditor(eager=False))
    try:
        task = hub_task(h, synthesis=False)
        rc = task.receipts["rep_en"]
        assert h.clearance(task.key, rc.message_id, receipt=rc).state == "AUDIT_PENDING"
        assert not may_act(rc, h.clearance(task.key, rc.message_id, receipt=rc))
        d = check_before_acting(h, task.key, rc)
        assert d.allowed and d.clearance.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
    finally:
        h.close()


def test_check_before_acting_refuses_when_no_clearance_can_be_had():
    from epinoic_logic.branches import RouterHub
    from .conftest import CFG, KEY
    plain = RouterHub(signing_key=KEY, config=CFG)
    task = hub_task(plain, synthesis=False)
    d = check_before_acting(plain, task.key, task.receipts["rep_en"])
    assert not d.allowed and "AuditorNotAttached" in d.reason
    assert not check_before_acting(plain, task.key, "not a receipt").allowed


# ============================================================================================ may_release
def released(hub, task, final, receipt=None):
    auditor = hub.auditor
    return release_decision(receipt if receipt is not None else task.receipts["syn"], final, auditor.keyring, audits=auditor.audits(task.uid),
                            journal=auditor.journal(task.uid))


def test_may_release_a_synthesis_under_its_final_audit(hub):
    task = hub_task(hub)
    final = hub.close_task(task.key)
    d = released(hub, task, final)
    assert d.allowed, d.reason
    assert may_release(task.receipts["syn"], final, hub.auditor.keyring, audits=hub.auditor.audits(task.uid), journal=hub.auditor.journal(task.uid))


def test_may_release_refuses_a_non_final_superseded_or_unsigned_audit(hub):
    task = hub_task(hub)
    first = hub.audit(task.key)
    assert "not FINAL" in released(hub, task, first).reason
    final = hub.audit(task.key, final=True)
    assert released(hub, task, final).allowed
    assert "does not verify" in released(hub, task, first.model_copy(update={"final": True})).reason
    forged = final.model_copy(update={"state": "AUDIT_PASSED"}) if final.state != "AUDIT_PASSED" else final.model_copy(update={"created_at": "2026-01-01T00:00:00Z"})
    assert "does not verify" in released(hub, task, forged).reason
    later = hub.audit(task.key, final=True)  # supersedes the final audit
    assert later.supersedes == final.audit_id and not released(hub, task, final).allowed and released(hub, task, later).allowed
    resigned_elsewhere = sign_audit(final.model_copy(update={"scope": "verdicts"}), hub.auditor.keyring)
    assert "not a task audit" in released(hub, task, resigned_elsewhere).reason


def test_may_release_refuses_a_failed_task_an_edited_or_rejected_synthesis_and_a_non_synthesis(hub):
    task = hub_task(hub)
    final = hub.close_task(task.key)
    syn = task.receipts["syn"]
    assert "differs from the journaled" in released(hub, task, final, presented(syn, summary="Released.")).reason
    assert "REJECTED" in released(hub, task, final, presented(syn, status=TransmissionStatus.REJECTED)).reason
    assert "not a journaled synthesis" in released(hub, task, final, task.receipts["rep_en"]).reason
    assert not released(hub, task, final, "not a receipt").allowed
    assert not release_decision(syn, final, hub.auditor.keyring, audits=None, journal=hub.auditor.journal(task.uid)).allowed
    bad = hub_task(hub, plan=None, synthesis=True, en_text="The mill wheel turned all night.")  # claims the response does not carry: FID-001
    bad_final = hub.close_task(bad.key)
    assert bad_final.state == "AUDIT_FAILED"
    d = release_decision(bad.receipts["syn"], bad_final, hub.auditor.keyring, audits=hub.auditor.audits(bad.uid), journal=hub.auditor.journal(bad.uid))
    assert not d.allowed and "AUDIT_FAILED" in d.reason


class _Journal:
    """A journal stand-in with an entry after the audit's head (or another channel), for the coverage rule."""

    def __init__(self, real, *, extra_event=False, channel_uid=None, broken=False):
        self.real, self.extra_event, self.broken = real, extra_event, broken
        self.channel_uid = channel_uid or real.channel_uid
        self.evicted = False

    def verify_chain(self):
        return "broken" if self.broken else self.real.verify_chain()

    def entries(self):
        entries = list(self.real.entries())
        if self.extra_event:
            last_event = next(e for e in reversed(entries) if e.event is not None)
            entries.append(SimpleNamespace(event=last_event.event, kind=last_event.kind, entry_hash="x", index=len(entries) + 1))
        return tuple(entries)


@pytest.mark.parametrize("case", ["event_after_head", "another_channel", "chain_broken"])
def test_may_release_requires_the_audit_to_cover_the_channel_as_it_stands(hub, case):
    task = hub_task(hub)
    final = hub.close_task(task.key)
    real = hub.auditor.journal(task.uid)
    journal = {"event_after_head": _Journal(real, extra_event=True), "another_channel": _Journal(real, channel_uid="other"),
               "chain_broken": _Journal(real, broken=True)}[case]
    d = release_decision(task.receipts["syn"], final, hub.auditor.keyring, audits=hub.auditor.audits(task.uid), journal=journal)
    assert not d.allowed
    assert {"event_after_head": "after the audit", "another_channel": "another channel", "chain_broken": "does not verify"}[case] in d.reason


def test_policy_never_reads_a_verdict_and_never_raises_on_malformed_inputs():
    junk = [None, 1, "x", object(), {}, [], SimpleNamespace(state="AUDIT_PASSED")]
    for a in junk:
        for b in junk:
            assert may_act(a, b) is False
            assert may_release(a, b, None, audits=[], journal=None) is False
    assert isinstance(TransferClearance, type)
