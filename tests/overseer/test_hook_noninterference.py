"""The channel observer hook does not interfere with the channel (design section 13.3).

With no observer the channel calls straight through and opens no result capture. With a raising observer, an observer
that tries to mutate the event, any number of collectors, the auditor, or all of them at once, the receipts, the
returned messages and the channel's state are identical to a channel without observers (uuids, digests over them and
times excluded). An observer that raises never breaks a transfer; its failure is recorded, bounded. Abuse: an observer
that issues a transfer from inside its notification, and one that bypasses the event's frozen-ness, are both reported
by the audit (CUST-003, CUST-005)."""
from __future__ import annotations

import dataclasses
import json
import re
import threading
from typing import Any, Callable

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.channel.events import OBSERVER_ERRORS_MAX, ChannelEvent
from epinoic_logic.engine.sink import capture_active
from epinoic_logic.integrity import AgentRole
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

from .conftest import CFG, DOC, EN_INPUT, EN_TEXT, HI_INPUT, HI_TEXT, KEY, codes_of, default_synthesis, english_report, int_problem, make_auditor, make_plan, problems_fn

# ============================================================================================ normalisation (shared with the equivalence tests)
_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
_H64 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
_U32 = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
#: Request-constraint problem ids carry eight hex digits of a uuid (``constraint-<id>-<hex8>``; design gap G1).
_CONSTRAINT = re.compile(r"(constraint-[A-Za-z0-9_]+-)([0-9a-f]{8})(?![0-9a-f])")
_TIME_KEYS = {"timings", "monotonic_ns", "latency_ms", "elapsed_ms"}
#: Lists the channel orders by identifier value (uuids): compared as sets once the ids are replaced.
_ID_SETS = {"formal_result_ids", "related_result_ids"}


class Normaliser:
    """Replaces uuids by placeholders numbered in order of first appearance, digests (which cover uuids and times) by
    one marker, timestamps by one marker, and drops timing fields; JSON strings are parsed and normalised in place.
    Result-id lists the channel sorts by uuid value are compared as sets."""

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}

    def _id(self, m: re.Match) -> str:
        return self.ids.setdefault(m.group(0), f"<id{len(self.ids) + 1}>")

    def text(self, s: str) -> Any:
        st = s.strip()
        if st[:1] in "{[" and len(st) > 1:
            try:
                return self(json.loads(st))
            except ValueError:
                pass
        s = _TS.sub("<ts>", s)
        s = _H64.sub("<sha256>", s)
        s = _UUID.sub(self._id, s)
        s = _CONSTRAINT.sub(lambda m: m.group(1) + self.ids.setdefault(m.group(2), f"<id{len(self.ids) + 1}>"), s)
        return _U32.sub(self._id, s)

    def __call__(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                key = self.text(k) if isinstance(k, str) else k
                if k in _TIME_KEYS:
                    out[key] = "<time>"
                elif k in _ID_SETS and isinstance(v, list):
                    out[key] = sorted(self(v), key=str)
                else:
                    out[key] = self(v)
            return out
        if isinstance(obj, (list, tuple)):
            return [self(v) for v in obj]
        if isinstance(obj, str):
            return self.text(obj)
        if hasattr(obj, "model_dump"):
            return self(obj.model_dump(mode="json"))
        return obj


def channel_state(ch: Any) -> dict:
    """Everything the channel holds after a script, as plain JSON values."""
    return {
        "receipts": [r.model_dump(mode="json") for r in ch.receipts],
        "log": [m.model_dump(mode="json") for m in ch.log.messages()],
        "requests": [[mid, r.model_dump(mode="json")] for mid, r in ch.requests.items()],
        "transmitted": [[rid, r.model_dump(mode="json")] for rid, r in ch.transmitted_reports.items()],
        "formalized": [[cid, p.model_dump(mode="json")] for cid, p in ch.formalized.items()],
        "formalized_by": [[cid, list(v)] for cid, v in ch.formalized_by.items()],
        "ambiguous": sorted(ch.ambiguous_pooled),
        "forwards": [[rid, [list(x) for x in v]] for rid, v in ch.forwards.items()],
        "superseded": [[k, v] for k, v in ch.superseded.items()],
        "conflicts": [[sorted(c), r] for c, r in ch.conflicts_seen],
        "recipients": [[rid, sorted(v)] for rid, v in ch.report_recipients.items()],
    }


def returned_value(value: Any) -> Any:
    return [v.model_dump(mode="json") if hasattr(v, "model_dump") else v for v in value]


# ============================================================================================ the script
EN_PROBLEMS = {"en-point": int_problem("en-point", "work_hours", 12, op="gt", bound=8)}
HI_PROBLEMS = {"h1.1": int_problem("h1.1", "min_age", 9, op="ge", bound=9)}
BAD_QUOTE = [dict(claim_id="en-point", claim_text="The writer presents work as endless", claim_role="point", materiality="material"),
             dict(claim_id="en-ev1", claim_text="We work until the bell", claim_role="evidence", materiality="supporting",
                  source_refs=[{"document_id": "doc-mill", "excerpt": "We work until the dawn"}])]
KINDS = ["request", "request", "response", "response", "relay_forward", "request", "response_text", "relay_synthesis", "response"]


def script(ch: Any) -> list:
    """Every kind of transfer, delivered and REJECTED, on one channel; returns what every call returned."""
    out = []
    ch.verify_claim_fn = problems_fn(EN_PROBLEMS)
    m, req, rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    out.append(returned_value((m, req, rq)))
    out.append(returned_value(ch.request("router", "rogue-agent", EN_INPUT, [DOC])))  # REJECTED: not selected
    reply, rc = ch.respond(m.message_id, english_report())
    out.append(returned_value((reply, rc)))
    out.append(returned_value(ch.respond(m.message_id, english_report(claims=BAD_QUOTE, report_id="rep-en-2"))))  # delivered with findings
    fwd = ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload), in_reply_to=reply.message_id)
    out.append(returned_value(fwd))
    ch.verify_claim_fn = problems_fn(HI_PROBLEMS)
    peer = SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist", text=EN_TEXT)
    m2, req2, rq2 = ch.request("router", "history-specialist", HI_INPUT, [peer])
    out.append(returned_value((m2, req2, rq2)))
    out.append(returned_value(ch.respond_text(m2.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")))
    out.append(returned_value(ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, default_synthesis())))
    out.append(returned_value(ch.respond("no-such-request", english_report(report_id="rep-en-3"))))  # REJECTED: INT-REQ-000
    return out


def new_channel(observers=()) -> TranslatorChannel:
    return TranslatorChannel(make_plan(), signing_key=KEY, key_id="hub", config=CFG, observers=observers)


def outcome(ch: TranslatorChannel) -> Any:
    n = Normaliser()
    returned = script(ch)
    return n({"returned": returned, "state": channel_state(ch)})


class Collector:
    def __init__(self) -> None:
        self.events: list[ChannelEvent] = []
        self.dicts: list[dict] = []

    def __call__(self, ev: ChannelEvent) -> None:
        self.events.append(ev)
        self.dicts.append(ev.to_dict())


def raiser(ev: ChannelEvent) -> None:
    raise RuntimeError("observer bug")


def mutator(ev: ChannelEvent) -> None:
    """Tries every ordinary way of changing the event; each one raises (the event and its parts are frozen)."""
    attempts = [lambda: setattr(ev, "status", "ACCEPTED"), lambda: setattr(ev, "receipt_json", "{}"), lambda: delattr(ev, "kind"),
                lambda: ev.captured.append(None), lambda: ev.pool.append(None), lambda: ev.log_added.append("x")]
    if ev.captured:
        attempts.append(lambda: setattr(ev.captured[0], "result_json", "{}"))
    if ev.pool:
        attempts.append(lambda: setattr(ev.pool[0], "claim_id", "x"))
    for attempt in attempts:
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            attempt()
    raise dataclasses.FrozenInstanceError("cannot assign to field 'status'")


# ============================================================================================ straight through with no observer
def test_no_observer_calls_straight_through_without_a_capture():
    seen: list[bool] = []
    inner = problems_fn(EN_PROBLEMS)

    def watching(claim, report):
        seen.append(capture_active())
        return inner(claim, report)

    plain = new_channel()
    assert plain.observers == () and plain.observer_errors == []
    m, _r, _q = plain.request("router", "english-specialist", EN_INPUT, [DOC])
    plain.verify_claim_fn = watching
    plain.respond(m.message_id, english_report())
    assert seen and set(seen) == {False} and plain._observation.seq == 0 and plain._observation.depth == 0
    n = len(seen)
    observed = new_channel([Collector()])
    m, _r, _q = observed.request("router", "english-specialist", EN_INPUT, [DOC])
    observed.verify_claim_fn = watching
    observed.respond(m.message_id, english_report())
    assert len(seen) == 2 * n and set(seen[n:]) == {True} and observed._observation.seq == 2 and observed._observation.depth == 0


def test_the_entry_points_keep_their_names_and_signatures():
    import inspect
    ch = new_channel()
    for name in ("request", "respond_text", "respond", "relay"):
        fn = getattr(TranslatorChannel, name)
        assert fn.__name__ == name and inspect.signature(fn) == inspect.signature(fn.__wrapped__)
        assert fn.__doc__ == fn.__wrapped__.__doc__
    assert list(inspect.signature(ch.request).parameters)[:3] == ["from_agent_id", "to_agent_id", "user_input"]


# ============================================================================================ identical outcomes
VARIANTS: dict[str, Callable[[], list]] = {
    "raising": lambda: [raiser],
    "mutating": lambda: [mutator],
    "collectors": lambda: [Collector(), Collector()],
    "auditor": lambda: ["auditor"],
    "everything": lambda: [raiser, Collector(), mutator, "auditor", raiser, Collector()],
}


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_receipts_messages_and_state_are_identical_with_any_observers(variant):
    baseline = outcome(new_channel())
    auditor = make_auditor()
    try:
        ch = new_channel()
        for o in VARIANTS[variant]():
            ch.add_observer(auditor.observer_for(ch) if o == "auditor" else o)
        assert outcome(ch) == baseline
        assert ch._observation.seq == len(KINDS)
        raising = sum(1 for o in ch.observers if o in (raiser, mutator))
        assert len(ch.observer_errors) == raising * len(KINDS)
        assert all(err[2] in ("RuntimeError", "FrozenInstanceError") for err in ch.observer_errors)
        if variant in ("auditor", "everything"):
            audit = auditor.audit(ch.channel_uid)
            # the one fault the script plants (rep-en-2 quotes "We work until the dawn", which its response does not carry)
            errors = [f for f in audit.report.findings if f.severity == "error" and f.code != "OVS-DIV-001"]
            assert [(f.code, f.claim_ids, f.report_ids) for f in errors] == [("OVS-FID-002", ["en-ev1"], ["rep-en-2"])], codes_of(audit)
    finally:
        auditor.close()


def test_the_script_covers_every_receipt_status():
    ch = new_channel()
    script(ch)
    assert {r.status.value for r in ch.receipts} == {"ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"}


# ============================================================================================ events
def test_one_event_per_router_call_in_order_with_respond_text_as_one_event():
    c = Collector()
    ch = new_channel([c])
    script(ch)
    assert [e.kind for e in c.events] == KINDS
    assert [e.seq for e in c.events] == list(range(1, len(KINDS) + 1))
    assert {e.channel_uid for e in c.events} == {ch.channel_uid}
    text_event = c.events[KINDS.index("response_text")]
    assert text_event.raw_text == HI_TEXT and text_event.status == ch.receipts[6].status.value
    assert [e.delivered for e in c.events] == [r.status.value != "REJECTED" for r in ch.receipts]


def test_every_observer_gets_the_same_immutable_event():
    first, last = Collector(), Collector()
    ch = new_channel([first, mutator, raiser, last])
    script(ch)
    assert len(first.events) == len(last.events) == len(KINDS)
    for a, b, d in zip(first.events, last.events, first.dicts):
        assert a is b and a.to_dict() == d  # the same object, unchanged by the mutator in between


def test_the_event_is_built_before_the_call_returns_and_the_returned_objects_are_the_methods_own():
    order: list[str] = []
    ch = new_channel()
    ch.add_observer(lambda ev: order.append(f"event:{ev.receipt_id}:{len(ch.receipts)}"))
    m, req, rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    order.append("returned")
    assert order == [f"event:{rq.receipt_id}:1", "returned"]
    assert m is ch.log.get(m.message_id) and rq is ch.receipts[-1] and req is ch.requests[m.message_id]
    ch.verify_claim_fn = problems_fn(EN_PROBLEMS)
    reply, rc = ch.respond(m.message_id, english_report())
    assert reply is ch.log.get(reply.message_id) and rc is ch.receipts[-1]


def test_an_observer_added_during_a_notification_sees_only_later_events():
    late = Collector()
    ch = new_channel()

    def adder(ev):
        if ev.seq == 1:
            ch.add_observer(late)
    ch.add_observer(adder)
    script(ch)
    assert [e.seq for e in late.events] == list(range(2, len(KINDS) + 1))


# ============================================================================================ failures never reach the caller
def test_observer_failures_are_recorded_bounded_and_never_raised():
    ch = new_channel([raiser] * (OBSERVER_ERRORS_MAX + 6))
    m, _req, rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    assert m is not None and rq.status.value == "ACCEPTED"
    errors = ch.observer_errors
    assert len(errors) == OBSERVER_ERRORS_MAX and errors[0] == (1, "raiser", "RuntimeError")
    errors.clear()  # a copy: the channel's record is not changed
    assert len(ch.observer_errors) == OBSERVER_ERRORS_MAX


def test_an_observer_must_be_callable():
    with pytest.raises(TypeError):
        new_channel(["not callable"])
    ch = new_channel()
    with pytest.raises(TypeError):
        ch.add_observer(42)
    assert ch.observers == ()


@pytest.mark.parametrize("observed", [False, True])
def test_a_call_that_raises_reraises_the_same_exception_and_emits_a_raised_event(observed):
    boom = RuntimeError("payload cannot be serialised")

    class NotAContract:
        request_id, task_id = "req-ovs", "task-ovs"

        def model_dump(self, **kw):
            raise boom

    c = Collector()
    ch = new_channel([c] if observed else [])
    before = Normaliser()(channel_state(ch))
    with pytest.raises(RuntimeError) as excinfo:
        ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, NotAContract())
    assert excinfo.value is boom
    assert Normaliser()(channel_state(ch)) == before
    if observed:
        assert len(c.events) == 1 and c.events[0].raised == "RuntimeError" and c.events[0].receipt_id is None and c.events[0].message_id is None
        assert ch._observation.depth == 0
        m, _req, rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])  # the channel goes on working
        assert c.events[-1].seq == 2 and c.events[-1].receipt_id == rq.receipt_id
    else:
        assert c.events == []


def test_channel_uids_are_distinct_per_instance():
    a, b = new_channel(), new_channel()
    assert a.channel_uid != b.channel_uid and re.fullmatch(r"[0-9a-f]{32}", a.channel_uid)
    assert a.channel_uid == a.channel_uid


def test_parallel_channels_on_threads_never_mix_their_events_or_results():
    collectors = [Collector() for _ in range(4)]
    channels = [new_channel([c]) for c in collectors]
    errors: list[BaseException] = []

    def run(ch):
        try:
            script(ch)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(ch,)) for ch in channels]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    seen: set[str] = set()
    for ch, c in zip(channels, collectors):
        assert {e.channel_uid for e in c.events} == {ch.channel_uid} and [e.seq for e in c.events] == list(range(1, len(KINDS) + 1))
        captured = {r.result_id for e in c.events for r in e.captured}
        cited = {o.verification.result_id for r in ch.receipts for o in r.outcomes if o.verification is not None}
        assert cited and cited <= captured and not captured & seen
        seen |= captured


# ============================================================================================ abuse: reported by the audit
def test_a_transfer_issued_from_inside_a_notification_is_not_journaled_and_is_reported():
    auditor = make_auditor()
    try:
        ch = new_channel()
        ch.add_observer(auditor.observer_for(ch))
        sneaked: list[str] = []

        def sneaky(ev):
            if ev.seq == 1:
                m, _req, _rq = ch.request("router", "history-specialist", HI_INPUT, [])
                sneaked.append(m.message_id)
        ch.add_observer(sneaky)
        m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        assert sneaked and ch._observation.seq == 1  # the nested call emitted no event of its own
        audit = auditor.audit(ch.channel_uid)
        cust = [f for f in audit.report.findings if f.code == "OVS-CUST-003"]
        assert cust and any(sneaked[0] in f.message_ids for f in cust) and audit.state == "AUDIT_FAILED"
    finally:
        auditor.close()


def test_an_observer_that_bypasses_the_frozen_event_breaks_the_journal_chain():
    auditor = make_auditor()
    try:
        ch = new_channel()
        ch.add_observer(auditor.observer_for(ch))

        def forger(ev):  # deliberate subversion after the auditor journaled the event
            object.__setattr__(ev, "status", "ACCEPTED")
        ch.add_observer(forger)
        ch.request("router", "rogue-agent", EN_INPUT, [DOC])  # REJECTED, rewritten as ACCEPTED in the shared event
        assert auditor.journal(ch.channel_uid).verify_chain() is not None
        audit = auditor.audit(ch.channel_uid)
        assert "OVS-CUST-005" in codes_of(audit) and audit.state == "AUDIT_FAILED"
    finally:
        auditor.close()
