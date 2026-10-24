"""The hub's observer and auditor wiring, task lifecycle and replay worker lifecycle (design sections 4, 5.3 and 14).

A hub without observers or an auditor is unchanged and refuses every Overseer method. With ``auditor=`` every channel it
opens is journaled (the auditor first, then the hub's other observers), ``audit`` and ``view`` read the journal, a
reopened task id keeps the old channel in ``closed_channels`` where its journal verifies and it is still audited (T14),
``close_task`` issues the FINAL audit and seals the journal, and the replay worker stops with the last hub using it."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest

import epinoic_logic.branches.hub as hub_module
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.hub import AuditorNotAttached, HubClosed
from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.integrity import AgentRole
from epinoic_logic.overseer import EngineKey, KeyRing, TransferAuditor, verify_audit
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

from .conftest import (
    CFG, DOC, EN_INPUT, EN_TEXT, HI_INPUT, HI_TEXT, KEY, OTHER_KEY, SECRET, codes_of, default_synthesis, english_report, int_problem, make_auditor,
    make_keyring, make_plan, ovs_errors, problems_fn,
)
from .test_hook_noninterference import Collector, raiser

EN_PROBLEMS = {"en-point": int_problem("en-point", "work_hours", 12, op="gt", bound=8)}
HI_PROBLEMS = {"h1.1": int_problem("h1.1", "min_age", 9, op="ge", bound=9)}
#: An English response that misquotes the extract ("until the dawn"): the channel names it (INT-REQ-003) and delivers the
#: report ACCEPTED_WITH_FINDINGS. The receipt is the exact image of what was checked, so the audit has no error.
BAD_QUOTE_TEXT = 'The writer presents work as endless: the foreman\'s words "We work until the dawn" make labour the measure of time.'
BAD_QUOTE_CLAIMS = [
    dict(claim_id="en-point", claim_text="The writer presents work as endless", claim_role="point", materiality="material"),
    dict(claim_id="en-ev1", claim_text="We work until the dawn", claim_role="evidence", materiality="supporting",
         source_refs=[{"document_id": "doc-mill", "excerpt": "We work until the dawn"}]),
]


# ============================================================================================ a task driven through the hub
@dataclass
class HubTask:
    hub: RouterHub
    key: str
    ch: TranslatorChannel
    mids: dict[str, str] = field(default_factory=dict)
    receipts: dict[str, Any] = field(default_factory=dict)
    messages: dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.ch.channel_uid

    def all_mids(self) -> list[str]:
        return [r.message_id for r in self.ch.receipts]


def hub_task(hub: RouterHub, *, plan=None, en_report: Optional[SpecialistReport] = None, synthesis: bool = True, en_text: str = EN_TEXT,
             hi_text: str = HI_TEXT) -> HubTask:
    """The synthetic task through the hub: English request and structured report, the router's forward of it to the
    History specialist, the History request carrying it as ``peer:en``, the History raw text, and the synthesis."""
    plan = plan or make_plan()
    ch = hub.open_task(plan)
    task = HubTask(hub=hub, key=plan.task_id, ch=ch)
    ch.verify_claim_fn = problems_fn(EN_PROBLEMS)
    m, _req, rq = hub.dispatch(task.key, "english-specialist", EN_INPUT, [DOC])
    task.mids["req_en"], task.receipts["req_en"] = m.message_id, rq
    reply, rc = hub.receive(task.key, m.message_id, en_report or english_report(text=en_text))
    task.mids["rep_en"], task.receipts["rep_en"], task.messages["rep_en"] = rc.message_id, rc, reply
    fwd, rf = ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload),
                       in_reply_to=reply.message_id)
    task.mids["fwd"], task.receipts["fwd"] = rf.message_id, rf
    ch.verify_claim_fn = problems_fn(HI_PROBLEMS)
    peer = SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist", text=reply.payload["original_response"])
    m2, _req2, rq2 = hub.dispatch(task.key, "history-specialist", HI_INPUT, [peer])
    task.mids["req_hi"], task.receipts["req_hi"] = m2.message_id, rq2
    reply2, rc2 = hub.receive(task.key, m2.message_id, hi_text, agent_id="history-specialist", report_id="rep-hi-1")
    task.mids["rep_hi"], task.receipts["rep_hi"], task.messages["rep_hi"] = rc2.message_id, rc2, reply2
    if synthesis:
        ms, rs = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, default_synthesis())
        task.mids["syn"], task.receipts["syn"], task.messages["syn"] = rs.message_id, rs, ms
    return task


def audited_hub(**kw) -> RouterHub:
    auditor = kw.pop("auditor", None) or make_auditor()
    return RouterHub(signing_key=KEY, config=CFG, auditor=auditor, **kw)


@pytest.fixture
def hub():
    h = audited_hub()
    yield h
    h.close()


# ============================================================================================ without an auditor
def test_a_hub_without_observers_or_auditor_opens_unobserved_channels_and_refuses_overseer_methods():
    h = RouterHub(signing_key=KEY, config=CFG)
    task = hub_task(h)
    assert task.ch.observers == () and task.ch._observation.seq == 0 and h.auditor is None and h.observers == ()
    for call in (lambda: h.clearance(task.key, task.mids["rep_en"]), lambda: h.audit(task.key), lambda: h.view(task.key),
                 lambda: h.review(task.key, [])):
        with pytest.raises(AuditorNotAttached):
            call()
    assert h.close_task(task.key) is None and task.uid in h.closed_channels and task.key not in h.channels
    h.close()
    h.close()  # idempotent


def test_hub_observers_alone_see_every_transfer_and_a_raising_one_breaks_nothing():
    c = Collector()
    h = RouterHub(signing_key=KEY, config=CFG, observers=[raiser, c])
    task = hub_task(h)
    assert [e.kind for e in c.events] == ["request", "response", "relay_forward", "request", "response_text", "relay_synthesis"]
    assert [r.status.value for r in task.ch.receipts] == ["ACCEPTED"] * 6
    assert len(task.ch.observer_errors) == 6 and {e[2] for e in task.ch.observer_errors} == {"RuntimeError"}
    with pytest.raises(TypeError):
        RouterHub(signing_key=KEY, config=CFG, observers=["nope"])


# ============================================================================================ with an auditor
def test_the_auditor_is_attached_first_and_journals_every_transfer(hub):
    c = Collector()
    h = audited_hub(observers=[c], auditor=hub.auditor)
    task = hub_task(h)
    assert len(task.ch.observers) == 2 and task.ch.observers[1] is c
    assert getattr(task.ch.observers[0], "__qualname__", "") == "TransferAuditor.observe"
    events = hub.auditor.journal(task.uid).events()
    assert [e.message_id for e in events] == task.all_mids() == [e.message_id for e in c.events]
    view = h.view(task.key)
    assert [t.message_id for t in view.transfers] == task.all_mids() and not view.degraded


def test_the_task_audit_of_a_genuine_task_is_signed_and_clean(hub):
    task = hub_task(hub)
    audit = hub.audit(task.key)
    assert verify_audit(audit, hub.auditor.keyring) and audit.scope == "task" and audit.channel_uid == task.uid
    assert audit.message_ids == task.all_mids() and not ovs_errors(audit, allow=())
    assert audit.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and audit.coverage.shadow_run == "run"
    assert hub.audit(task.ch).audit_id != audit.audit_id  # by channel object too; a later audit supersedes the earlier one
    assert hub.auditor.audits(task.uid)[-1].supersedes == audit.audit_id


def test_the_hub_refuses_an_auditor_that_cannot_verify_its_results():
    other = TransferAuditor(KeyRing({"hub": EngineKey(OTHER_KEY)}, SECRET), replay_mode="inline")
    try:
        with pytest.raises(ValueError, match="engine key"):
            RouterHub(signing_key=KEY, config=CFG, auditor=other)
        with pytest.raises(ValueError, match="engine key"):
            RouterHub(signing_key=KEY, key_id="undeclared", config=CFG, auditor=other)
    finally:
        other.close()
    with pytest.raises(TypeError):
        RouterHub(signing_key=KEY, config=CFG, auditor=object())


def test_the_hub_refuses_an_intake_of_another_secret_or_without_an_auditor():
    from epinoic_logic.overseer import VerdictIntake, accepted_identities
    stranger = VerdictIntake(KeyRing({"hub": EngineKey(KEY)}, b"another-overseer-secret-0123456789abcdef!!"), accepted_packs=accepted_identities())
    with pytest.raises(ValueError):
        RouterHub(signing_key=KEY, config=CFG, intake=stranger)
    a = make_auditor()
    try:
        with pytest.raises(ValueError, match="secrets"):
            RouterHub(signing_key=KEY, config=CFG, auditor=a, intake=stranger)
        same = VerdictIntake(make_keyring(), accepted_packs=accepted_identities())
        assert RouterHub(signing_key=KEY, config=CFG, auditor=a, intake=same).intake is same
    finally:
        a.close()


def test_task_keys_resolve_only_to_this_hubs_channels(hub):
    task = hub_task(hub, synthesis=False)
    stranger = TranslatorChannel(make_plan(), signing_key=KEY, key_id="hub", config=CFG)
    for bad in ("no-such-task", stranger, 42, None):
        with pytest.raises(KeyError):
            hub.audit(bad)
    assert hub.channel_for(task.key) is task.ch is hub.channel_for(task.ch)


def test_a_channel_with_nothing_journaled_clears_nothing_and_has_no_audit(hub):
    ch = hub.open_task(make_plan())
    clr = hub.clearance(ch.plan.task_id, "never-issued")
    assert clr.state == "AUDIT_FAILED" and clr.codes == ["OVS-CUST-003"] and clr.channel_uid == ch.channel_uid
    with pytest.raises(LookupError):
        hub.audit(ch.plan.task_id)
    with pytest.raises(LookupError):
        hub.view(ch.plan.task_id)


# ============================================================================================ T14: a reopened task id
def test_t14_a_reopened_task_keeps_the_old_channel_whose_journal_verifies_and_is_audited(hub):
    first = hub_task(hub)
    second = hub.open_task(make_plan())
    assert hub.channels[first.key] is second and second is not first.ch and second.channel_uid != first.uid
    assert hub.closed_channels[first.uid] is first.ch
    journal = hub.auditor.journal(first.uid)
    assert journal.verify_chain() is None and not journal.sealed
    for key in (first.uid, first.ch):
        audit = hub.audit(key)
        assert verify_audit(audit, hub.auditor.keyring) and audit.channel_uid == first.uid and audit.message_ids == first.all_mids()
        assert not ovs_errors(audit, allow=())
    # the new channel has a journal of its own, and both stay distinct
    m, _req, _rq = hub.dispatch(first.key, "english-specialist", EN_INPUT, [DOC])
    assert [e.message_id for e in hub.auditor.journal(second.channel_uid).events()] == [m.message_id]
    assert m.message_id not in [e.message_id for e in hub.auditor.journal(first.uid).events()]
    assert sorted(hub.auditor.channel_uids(first.key)) == sorted([first.uid, second.channel_uid])


def test_t14_a_channel_put_back_by_hand_keeps_its_journal(hub):
    """The arena registers a variant channel under the task id, then puts the group channel back by hand."""
    group = hub_task(hub, synthesis=False)
    variant = hub.open_task(make_plan())
    hub.channels[group.key] = group.ch
    hub.channels[group.key + "::variant"] = variant
    ms, rs = group.ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, default_synthesis())
    assert rs.status.value != "REJECTED"
    assert [e.message_id for e in hub.auditor.journal(group.uid).events()][-1] == rs.message_id
    audit = hub.audit(group.key)
    assert not ovs_errors(audit, allow=()) and rs.message_id in audit.message_ids
    assert hub.channel_for(group.key + "::variant") is variant


def test_closed_channels_are_bounded(hub, monkeypatch):
    monkeypatch.setattr(hub_module, "MAX_CLOSED_CHANNELS", 3)
    opened = [hub.open_task(make_plan()) for _ in range(6)]
    assert list(hub.closed_channels) == [c.channel_uid for c in opened[2:5]]
    assert hub.channels[opened[0].plan.task_id] is opened[5]


# ============================================================================================ close_task
def test_close_task_issues_the_final_audit_and_seals_the_journal(hub):
    task = hub_task(hub)
    final = hub.close_task(task.key)
    assert final is not None and final.final and verify_audit(final, hub.auditor.keyring) and final.message_ids == task.all_mids()
    assert task.key not in hub.channels and hub.closed_channels[task.uid] is task.ch
    assert hub.auditor.journal(task.uid).sealed and hub.auditor.journal(task.uid).verify_chain() is None
    # Rewritten for the merged hub, which never raises into the router (a task id no open plan names gets a REJECTED
    # receipt from a quarantine channel): a dispatch on the closed task sends nothing, names the closed task, and leaves
    # the closed channel and its sealed journal exactly as they were (it was KeyError before the merge).
    entries = len(hub.auditor.journal(task.uid).entries())
    sent = len(task.ch.receipts)
    msg, _req, rq = hub.dispatch(task.key, "english-specialist", EN_INPUT, [DOC])
    assert msg is None and rq.status.value == "REJECTED" and [f.code for f in rq.findings] == ["INT-HANDOFF-001"]
    assert "was closed on this hub" in rq.findings[0].message and task.key in rq.findings[0].message
    assert len(hub.auditor.journal(task.uid).entries()) == entries and len(task.ch.receipts) == sent and task.key not in hub.channels
    assert hub.auditor.journal(task.uid).sealed and hub.auditor.journal(task.uid).verify_chain() is None
    assert hub.audit(task.uid).channel_uid == task.uid  # still auditable through closed_channels


def test_a_transfer_on_a_closed_channel_is_reported(hub):
    task = hub_task(hub, synthesis=False)
    hub.close_task(task.key)
    _ms, rs = task.ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, default_synthesis())  # router code kept the object
    audit = hub.audit(task.uid)
    assert "OVS-CUST-003" in codes_of(audit) and audit.state == "AUDIT_FAILED"
    assert hub.clearance(task.uid, rs.message_id).state == "AUDIT_FAILED"


def test_close_task_removes_every_key_of_the_channel_and_can_skip_the_audit(hub):
    task = hub_task(hub, synthesis=False)
    hub.channels["alias"] = task.ch
    audits_before = len(hub.auditor.audits(task.uid))
    assert hub.close_task(task.key, audit=False) is None
    assert "alias" not in hub.channels and len(hub.auditor.audits(task.uid)) == audits_before and hub.auditor.journal(task.uid).sealed


# ============================================================================================ lifecycle of the hub and the replay worker
def test_close_stops_the_auditor_only_when_its_last_hub_closes(monkeypatch):
    auditor = make_auditor()
    closed: list[int] = []
    real_close = auditor.close
    monkeypatch.setattr(auditor, "close", lambda: (closed.append(1), real_close())[1])
    a, b = RouterHub(signing_key=KEY, config=CFG, auditor=auditor), RouterHub(signing_key=KEY, config=CFG, auditor=auditor)
    a.close()
    assert closed == [] and a.closed and not b.closed
    hub_task(b, synthesis=False)
    b.close()
    assert closed == [1]
    b.close()
    assert closed == [1]
    for call in (lambda: b.open_task(make_plan()), lambda: b.dispatch("task-ovs", "english-specialist", EN_INPUT, [DOC]),
                 lambda: b.receive("task-ovs", "x", "text", agent_id="english-specialist", report_id="r")):
        with pytest.raises(HubClosed):
            call()
    assert b.audit("task-ovs").channel_uid  # journals and audits stay readable


def test_the_hub_is_a_context_manager():
    with audited_hub() as h:
        task = hub_task(h, synthesis=False)
    assert h.closed and h.audit(task.key).message_ids == task.all_mids()


def test_the_process_replay_worker_runs_with_the_hub_and_stops_with_it():
    auditor = make_auditor(replay_mode="process", eager=False)
    h = RouterHub(signing_key=KEY, config=CFG, auditor=auditor)
    try:
        task = hub_task(h, synthesis=False)
        clr = h.clearance(task.key, task.mids["rep_en"], wait_ms=250)
        assert clr.state in ("AUDIT_PENDING", "AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
        proc = auditor.replayer._proc
        assert proc is not None and proc.is_alive()
        audit = h.audit(task.key)
        assert audit.coverage.replay_mode == "process" and audit.coverage.results_replayed > 0 and not ovs_errors(audit, allow=())
    finally:
        h.close()
    assert auditor.replayer._proc is None and not proc.is_alive()


def test_hubs_on_threads_sharing_one_auditor_keep_their_channels_apart():
    auditor = make_auditor()
    hubs = [RouterHub(signing_key=KEY, config=CFG, auditor=auditor) for _ in range(4)]
    tasks: list[HubTask] = [None] * 4  # type: ignore[list-item]
    errors: list[BaseException] = []

    def run(i):
        try:
            tasks[i] = hub_task(hubs[i])
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    try:
        assert not errors and len({t.uid for t in tasks}) == 4
        for h, t in zip(hubs, tasks):
            audit = h.audit(t.key)
            assert audit.channel_uid == t.uid and audit.message_ids == t.all_mids() and not ovs_errors(audit, allow=())
            cited = {o.verification.result_id for r in t.ch.receipts for o in r.outcomes if o.verification is not None}
            assert cited and all(auditor.store.live(rid).channel_uid == t.uid for rid in cited)
    finally:
        for h in hubs:
            h.close()
