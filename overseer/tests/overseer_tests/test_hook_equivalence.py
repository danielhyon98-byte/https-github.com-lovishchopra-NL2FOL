"""The bus hook and the audit stage's manual observation helper are equivalent (design section 13.3).

The audit stage drove ``observe_call`` around the channel's four entry points by hand (``conftest.Observed``). The hook
in ``bus.py`` now does it inside the channel. The same scripted tasks, observed either way, give identical events,
identical journals (entry kinds, events and the auditor's own clearance records) and identical audits, modulo uuids,
digests over them and times. A channel observed both ways at once emits one event per call, never two."""
from __future__ import annotations

from typing import Any

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.integrity import AgentRole

from . import conftest as cf
from .conftest import CFG, DOC, EN_INPUT, KEY, english_report, make_auditor, make_plan, run_task
from .test_hook_noninterference import Collector, Normaliser, script


class Hooked:
    """A channel observed by the bus hook, shaped like ``conftest.Observed`` (``.channel``, ``.uid``), so the audit
    stage's scripted tasks run on it unchanged."""

    def __init__(self, channel: TranslatorChannel) -> None:
        self.__dict__["channel"] = channel

    @property
    def uid(self) -> str:
        return self.channel.channel_uid

    def __getattr__(self, name: str) -> Any:
        return getattr(self.channel, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self.channel, name, value)


def hooked_new_channel(auditor, plan=None, *, verify_claim_fn=None, key_id: str = "hub", config=CFG, **kw) -> Hooked:
    ch = TranslatorChannel(plan or make_plan(), signing_key=KEY, key_id=key_id, verify_claim_fn=verify_claim_fn, config=config, **kw)
    ch.add_observer(auditor.observer_for(ch))
    return Hooked(ch)


def journal_view(auditor, uid: str) -> list:
    """The journal as plain values: each entry's kind, event and record (hashes and MACs depend on the ids)."""
    n = Normaliser()
    out = []
    for e in auditor.journal(uid).entries():
        out.append(n({"index": e.index, "kind": e.kind, "event": e.event.to_dict() if e.event is not None else None, "record": e.record_json}))
    return out


def audit_view(audit) -> Any:
    n = Normaliser()
    return n({"state": audit.state, "transfer_states": list(audit.transfer_states.values()),
              "findings": sorted((f.code, f.severity, f.message) for f in audit.report.findings),
              "coverage": audit.coverage.model_dump(mode="json"), "divergences": [d.model_dump(mode="json") for d in audit.divergences]})


def both(flow, monkeypatch) -> tuple[Any, Any]:
    """Run ``flow(auditor)`` once observed by the manual helper and once by the hook; return (helper, hook) results."""
    out = []
    for hooked in (False, True):
        auditor = make_auditor()
        try:
            with monkeypatch.context() as m:
                if hooked:
                    from . import test_protocol_validate as pv
                    m.setattr(cf, "new_channel", hooked_new_channel)
                    m.setattr(pv, "new_channel", hooked_new_channel)
                task = flow(auditor)
            uid = task.uid
            ch = task.ch.channel if hasattr(task, "ch") else task.channel
            assert isinstance(ch._observers, tuple) and (len(ch.observers) == 1) is hooked
            audit = auditor.audit(uid)
            out.append((journal_view(auditor, uid), audit_view(audit)))
        finally:
            auditor.close()
    return out[0], out[1]


def _full(auditor):
    return run_task(auditor)


def _tampered(auditor):
    def tamper(task):  # T1: a delivered claim edited in the log payload after the receipt
        task.ch.channel.log.get(task.mids["rep_en"]).payload["claims"][0]["claim_text"] = "The writer presents work as joyful"
    return run_task(auditor, before_synthesis=tamper)


def _fid001(auditor):
    from .test_protocol_validate import fid001_task
    ch, _rc = fid001_task(auditor)
    return ch


FLOWS = {"full_task": _full, "tampered_t1": _tampered, "fid001": _fid001}


@pytest.mark.parametrize("flow", sorted(FLOWS))
def test_the_hook_and_the_manual_helper_give_identical_journals_and_audits(flow, monkeypatch):
    (helper_journal, helper_audit), (hook_journal, hook_audit) = both(FLOWS[flow], monkeypatch)
    assert hook_journal == helper_journal
    assert hook_audit == helper_audit
    assert any(e["kind"] == "clearance" for e in hook_journal) and any(e["event"] for e in hook_journal)
    if flow != "full_task":  # the faults are caught either way
        for a in (helper_audit, hook_audit):
            assert {"tampered_t1": "OVS-CUST-001", "fid001": "OVS-FID-001"}[flow] in {f[0] for f in a["findings"]} and a["state"] == "AUDIT_FAILED"


def test_a_plain_collector_receives_identical_events_either_way():
    from epinoic_logic.channel.events import observe_call

    class Manual:
        def __init__(self, channel, observers):
            self.__dict__.update(channel=channel, observers=list(observers))

        def __getattr__(self, name):
            if name in ("request", "respond", "respond_text", "relay"):
                return lambda *a, **k: observe_call(self.channel, name, a, k, self.observers)
            return getattr(self.channel, name)

        def __setattr__(self, name, value):
            setattr(self.channel, name, value)

    manual = Collector()
    script(Manual(TranslatorChannel(make_plan(), signing_key=KEY, key_id="hub", config=CFG), [manual]))
    hooked = Collector()
    script(TranslatorChannel(make_plan(), signing_key=KEY, key_id="hub", config=CFG, observers=[hooked]))
    assert len(manual.dicts) == len(hooked.dicts) > 0
    assert Normaliser()(manual.dicts) == Normaliser()(hooked.dicts)


def test_a_channel_observed_both_ways_at_once_emits_one_event_per_call():
    hook_seen, helper_seen = Collector(), Collector()
    ch = TranslatorChannel(make_plan(), signing_key=KEY, key_id="hub", config=CFG, observers=[hook_seen])
    observed = cf.Observed(ch, [helper_seen])
    m, _req, _rq = observed.request("router", "english-specialist", EN_INPUT, [DOC])  # the helper's call: the hook stays out
    ch.respond(m.message_id, english_report())  # a direct call: the hook's
    ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, english_report())
    assert [e.seq for e in helper_seen.events] == [1] and [e.seq for e in hook_seen.events] == [2, 3]
    assert [e.kind for e in helper_seen.events + hook_seen.events] == ["request", "response", "relay_forward"]
    assert observed.uid == ch.channel_uid and ch._observation.depth == 0
