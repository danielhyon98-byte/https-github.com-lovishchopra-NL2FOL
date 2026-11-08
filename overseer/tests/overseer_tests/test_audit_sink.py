"""The result sink: every engine run inside a scope is captured as canonical JSON at emit time, without changing what
``verify`` returns."""
from __future__ import annotations

import asyncio
import json
import threading

from epinoic_logic.engine import verify
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.sink import capture_active, capture_results, emit
from epinoic_logic.ir.canonical import canonical_json, sha256_hex

from .conftest import CFG, KEY, int_problem


def _strip_volatile(d: dict) -> dict:
    d = dict(d)
    for k in ("result_id", "issued_at", "timings", "signature"):
        d.pop(k, None)
    return d


def test_no_capture_is_a_no_op_and_verify_is_unchanged():
    assert not capture_active()
    p = int_problem("c1", "x", 5, op="gt", bound=3)
    plain = verify(p, CFG, signing_key=KEY, key_id="t")
    with capture_results() as cap:
        captured = verify(p, CFG, signing_key=KEY, key_id="t")
    assert _strip_volatile(plain.model_dump(mode="json")) == _strip_volatile(captured.model_dump(mode="json"))
    assert verify_signature(captured, KEY) and verify_signature(plain, KEY)
    assert len(cap.items) == 1
    emit(plain, p)  # outside any capture: nothing happens, nothing raises


def test_capture_holds_the_canonical_signed_result_and_the_problem():
    p = int_problem("c1", "x", 5, op="gt", bound=3)
    with capture_results() as cap:
        res = verify(p, CFG, signing_key=KEY, key_id="t")
    (c,) = cap.items
    assert c.result_id == res.result_id and c.key_id == "t"
    assert c.result_json == canonical_json(res.model_dump(mode="json", exclude_none=True))
    assert c.result_sha256 == sha256_hex(c.result_json)
    assert c.problem_json == canonical_json(p) and c.problem_digest == sha256_hex(canonical_json(p))
    assert json.loads(c.result_json)["signature"] == res.signature


def test_nested_captures_each_see_their_own_runs():
    p = int_problem("c1", "x", 5, op="gt", bound=3)
    with capture_results() as outer:
        verify(p, CFG)
        with capture_results() as inner:
            verify(p, CFG)
        verify(p, CFG)
    assert len(outer.items) == 3 and len(inner.items) == 1
    assert inner.items[0].result_id == outer.items[1].result_id


def test_a_result_mutated_after_emit_does_not_change_the_capture():
    p = int_problem("c1", "x", 5, op="gt", bound=3)
    with capture_results() as cap:
        res = verify(p, CFG, signing_key=KEY, key_id="t")
    before = cap.items[0].result_json
    res.status = res.status.__class__("COUNTEREXAMPLE")
    res.signature = None
    assert cap.items[0].result_json == before
    assert json.loads(before)["status"] == "ENTAILED"


def test_capture_is_thread_isolated():
    p = int_problem("c1", "x", 5, op="gt", bound=3)
    seen: dict[str, int] = {}

    def worker(name: str, n: int) -> None:
        with capture_results() as cap:
            for _ in range(n):
                verify(p, CFG)
        seen[name] = len(cap.items)

    with capture_results() as main_cap:
        threads = [threading.Thread(target=worker, args=(f"t{i}", i + 1)) for i in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
    assert seen == {"t0": 1, "t1": 2, "t2": 3}
    assert len(main_cap.items) == 0  # a plain thread does not inherit the caller's context


def test_asyncio_to_thread_lands_in_the_callers_capture():
    p = int_problem("c1", "x", 5, op="gt", bound=3)

    async def run():
        with capture_results() as cap:
            await asyncio.to_thread(verify, p, CFG)
        return cap

    cap = asyncio.run(run())
    assert len(cap.items) == 1


def test_emit_never_raises_on_garbage():
    with capture_results() as cap:
        emit(object(), object())
        emit(None, None)

        class Exploding:
            def model_dump(self, **kw):
                raise RuntimeError("boom")
        emit(Exploding(), None)
    assert cap.items == []


def test_raw_path_captures_the_demoted_problem_and_unparsed_payload_none():
    data = int_problem("c1", "x", 5, op="gt", bound=3).model_dump(mode="json")
    data["premises"][0]["grounding"]["verified"] = True  # self-certification on the untrusted path
    with capture_results() as cap:
        res = verify(data, CFG)
        bad = verify("{not json", CFG)
    good, unparsed = cap.items
    assert json.loads(good.problem_json)["premises"][0]["grounding"].get("verified") is None
    assert any(d.code == "E505" for d in res.diagnostics)
    assert unparsed.problem_json is None and unparsed.result_id == bad.result_id


def test_capture_overflow_is_counted_not_hidden():
    p = int_problem("c1", "x", 5, op="gt", bound=3)
    with capture_results(max_items=2) as cap:
        for _ in range(4):
            verify(p, CFG)
    assert len(cap.items) == 2 and cap.overflow == 2


# ------------------------------------------------------------------------------------------- channel events
import dataclasses as _dc
import re as _re

import pytest as _pytest

from epinoic_logic.channel import TranslatorChannel as _Channel
from epinoic_logic.channel.events import ObservationState, observe_call, snapshot_event, take_before

from .conftest import DOC, EN_INPUT, english_report, make_auditor, make_plan, problems_fn, run_task

_VOLATILE = _re.compile(r"\b[0-9a-f]{32}\b|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z|(?<=\"ms\":)[0-9.e+-]+|(?<=\"signature\":\")[0-9a-f]{64}")  # ids, times, timings, MACs over them


def _scrub(text: str) -> str:
    return _VOLATILE.sub("<v>", text)


def _plain_run(observers):
    """The synthetic exchange on a fresh channel, observed by ``observers`` (or not at all)."""
    ch = _Channel(make_plan(), signing_key=KEY, key_id="hub", config=CFG,
                  verify_claim_fn=problems_fn({"en-point": int_problem("en-point", "work_hours", 12, op="gt", bound=8)}))
    st = ObservationState()
    m, _req, rq = observe_call(ch, "request", ("router", "english-specialist", EN_INPUT, [DOC]), {}, observers, state=st)
    msg, rc = observe_call(ch, "respond", (m.message_id, english_report()), {}, observers, state=st)
    state = (sorted(ch.transmitted_reports), sorted(ch.formalized), len(ch.receipts), len(ch.log.messages()))
    return [_scrub(x.model_dump_json()) for x in (rq, rc)], _scrub(msg.model_dump_json()), state


def test_observation_does_not_change_receipts_messages_or_channel_state():
    def raising(event):
        raise RuntimeError("observer failure")

    def mutating(event):
        event.status = "ACCEPTED"  # frozen: raises, and no other observer or the channel is affected

    baseline = _plain_run([])
    assert _plain_run([raising]) == baseline
    assert _plain_run([mutating]) == baseline
    auditor = make_auditor()
    try:
        assert _plain_run([lambda e: auditor.on_event(e)]) == baseline  # the auditor attached changes nothing either
    finally:
        auditor.close()


def test_an_observer_that_tries_to_mutate_the_event_cannot_affect_another():
    seen = []

    def mutating(event):
        event.status = "REJECTED"

    ch = _Channel(make_plan(), signing_key=KEY, key_id="hub", config=CFG)
    st = ObservationState()
    observe_call(ch, "request", ("router", "english-specialist", EN_INPUT, [DOC]), {}, [mutating, seen.append], state=st)
    assert seen and seen[0].status == "ACCEPTED" and st.observer_errors == [(1, "test_an_observer_that_tries_to_mutate_the_event_cannot_affect_another.<locals>.mutating", "FrozenInstanceError")]
    with _pytest.raises(_dc.FrozenInstanceError):
        seen[0].captured = ()


def test_a_raised_call_emits_a_raised_event_and_reraises_the_same_exception(monkeypatch):
    seen = []
    ch = _Channel(make_plan(), signing_key=KEY, key_id="hub", config=CFG)
    boom = ValueError("bad call")

    def explode(*a, **k):
        raise boom
    monkeypatch.setattr(ch, "relay", explode)
    st = ObservationState()
    with _pytest.raises(ValueError) as info:
        observe_call(ch, "relay", ("router",), {}, [seen.append], state=st)
    assert info.value is boom
    assert seen[0].raised == "ValueError" and seen[0].receipt_json is None and seen[0].seq == 1


def test_nested_calls_emit_one_event_and_the_plan_is_carried_once():
    seen = []
    ch = _Channel(make_plan(), signing_key=KEY, key_id="hub", config=CFG)
    st = ObservationState()
    m, _r, _q = observe_call(ch, "request", ("router", "history-specialist", "Explain the Factory Act of 1833.", []), {}, [seen.append], state=st)
    from .conftest import HI_TEXT
    observe_call(ch, "respond_text", (m.message_id, HI_TEXT), {"agent_id": "history-specialist", "report_id": "rep-hi-1"}, [seen.append], state=st)
    assert [e.kind for e in seen] == ["request", "response_text"] and [e.seq for e in seen] == [1, 2]
    assert seen[0].plan_json is not None and seen[1].plan_json is None and seen[0].plan_sha256 == seen[1].plan_sha256
    assert seen[1].raw_text == HI_TEXT and seen[1].typed_copy_sha256 == seen[1].payload_sha256
    assert seen[1].captured and all(c.result_json for c in seen[1].captured)  # the chronology check's run was captured
    assert seen[1].transmitted_added == ("rep-hi-1",) and seen[0].requests_added == (m.message_id,)


def test_snapshot_reads_only():
    ch = _Channel(make_plan(), signing_key=KEY, key_id="hub", config=CFG)
    before = take_before(ch)
    out = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    dump = [r.model_dump_json() for r in ch.receipts]
    ev = snapshot_event(ch, "request", channel_uid="u", seq=1, before=before, call={"method": "request"}, returned=out)
    assert [r.model_dump_json() for r in ch.receipts] == dump and ev.message_id == out[2].message_id and ev.status == "ACCEPTED"
