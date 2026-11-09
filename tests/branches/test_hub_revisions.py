"""The router hub's specialist-feedback entry points (``RouterHub.request_revision``, ``revision_outcome``, ``revisions``):
they refuse without an auditor, on a closed hub and on a closed task; the router sends exactly the rendered text; and the
hub's records (its revision ledger and its copies of signed verdicts audits) are deep copies an edit never reaches."""
from __future__ import annotations

import hashlib

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.hub import AuditorNotAttached, HubClosed, RevisionIssue

from ..channel.revision_support import BAD_TEXT, CFG, DOC, GOOD_CLAIMS, INVENTED, KEY, QUESTION, plan, report
from ..overseer_attach import overseer  # the overseer's public package API; skips the test where it is not installed


def _hub(auditor=None) -> RouterHub:
    return RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=auditor)


def _auditor():
    ov = overseer()
    keyring = ov.KeyRing({k: ov.EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, b"hub-revision-test-overseer-secret-0123456789")
    return ov.TransferAuditor(keyring, replay_mode="inline", eager=True, inline_final_release=True)


def _answer(hub: RouterHub):
    p = plan()
    hub.open_task(p)
    m, _req, _rq = hub.dispatch(p.task_id, "english-specialist", QUESTION, [DOC])
    a, rc = hub.receive(p.task_id, m.message_id, report(BAD_TEXT, GOOD_CLAIMS + [INVENTED]))
    return p.task_id, m, a, rc


def test_every_feedback_entry_point_refuses_without_an_auditor():
    hub = _hub()
    task_id, _m, a, _rc = _answer(hub)
    with pytest.raises(AuditorNotAttached):
        hub.request_revision(task_id, a.message_id)
    with pytest.raises(AuditorNotAttached):
        hub.revision_outcome(task_id, a.message_id)
    with pytest.raises(AuditorNotAttached):
        hub.revisions(task_id)
    hub.close()


def test_a_closed_hub_and_a_closed_task_send_nothing():
    hub = _hub(_auditor())
    task_id, _m, a, _rc = _answer(hub)
    hub.close_task(task_id)
    issue = hub.request_revision(hub.closed_channels[next(iter(hub.closed_channels))].channel_uid, a.message_id)
    assert isinstance(issue, RevisionIssue) and not issue.allowed and issue.reason == "task_closed"
    hub.close()
    with pytest.raises(HubClosed):
        hub.request_revision(task_id, a.message_id)


def test_the_router_sends_exactly_the_rendered_text_and_the_records_are_copies():
    hub = _hub(_auditor())
    try:
        task_id, _m, a, _rc = _answer(hub)
        issue = hub.request_revision(task_id, a.message_id)
        assert issue.allowed and issue.reason == "issued" and issue.round == 1 and issue.max_rounds == 2
        assert hashlib.sha256(issue.rendered.encode("utf-8")).hexdigest() == issue.revision.rendered_sha256
        assert issue.message.payload["revision"]["rendered_sha256"] == issue.revision.rendered_sha256
        uid = hub.channels[task_id].channel_uid
        ledger = hub.revisions(task_id)
        assert [r.revision_id for r in ledger["issued"]] == [issue.revision.revision_id]
        copy = hub.revision_records(uid)[0][1]
        object.__setattr__(copy, "round", 99)  # an edit of a returned copy never reaches the ledger
        assert hub.revision_records(uid)[0][1].round == 1
        audit = hub.audit(task_id)
        hub.record_verdicts(uid, audit)
        got = hub.verdicts_audits(uid)[0]
        object.__setattr__(got, "state", "AUDIT_FAILED")
        assert hub.verdicts_audits(uid)[0].state == audit.state and hub.verdicts_audits(uid)[0] is not got
    finally:
        hub.close()
