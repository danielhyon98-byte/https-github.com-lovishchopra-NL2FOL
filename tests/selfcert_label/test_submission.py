"""Interface (e) of stage 2a: submission. Two submissions of the same answer share ONE call through a module-level in-flight
table, even through two labeller instances (two ``default_labeller()`` lookups); successes are cached (an LRU of 4,096),
failures never are; a shared flight or a cached success costs no budget; a provider labeller starts at submission; a handle that
is never collected costs nothing more; each call keeps its one retry with fresh canaries inside min(15 s, deadline - now - 2 s).
Every label here is scripted or comes from a fake transport: no provider is called."""
from __future__ import annotations

import gc
import threading

import pytest

from epinoic_logic import selfcert_label
from epinoic_logic.selfcert_label import (BudgetedLabeller, CallFailure, ProviderLabeller, RecordedLabeller, Reply, build_input,
                                          clear_shared_calls, labellers, model_digest, shared_calls_state)
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, reply_json

REQ = {"subject": "chemistry", "task_type": "short_answer"}
CLEAN = "The molar mass of water is 18 g/mol.\n\nIt boils at 100 degrees Celsius at sea level."
OTHER = "The molar mass of carbon dioxide is 44 g/mol."


class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _transport(calls: list, reply=None, gate: "threading.Event | None" = None):
    """A fake provider transport that answers every request with a valid reply naming nothing (canaries gated)."""
    def transport(system, user, *, max_tokens, timeout_s):
        calls.append(timeout_s)
        if gate is not None:
            gate.wait(5)
        if reply is not None:
            return reply(user, len(calls))
        return Reply(_valid_for(user), "end_turn")
    return transport


def _valid_for(user_text: str) -> str:
    """A valid reply to the request whose user text is ``user_text`` (found among the requests rendered for CLEAN/OTHER)."""
    for text in (CLEAN, OTHER):
        for attempt in (0, 1):
            inp = build_input(text, REQ, key=KEY, prompt_path=None)
            req = inp.requests[0] if attempt == 0 else inp.render(0, attempt=1, diagnostic=("malformed",))
            if req.user_text == user_text:
                return reply_json(req)
    raise AssertionError("an unexpected request")


KEY = b"selfcert-label fixed test key (tests only)"


@pytest.fixture(autouse=True)
def _fresh():
    clear_shared_calls()
    yield
    clear_shared_calls()


def test_two_submissions_through_two_default_labeller_instances_make_one_call():
    calls: list = []
    first = ProviderLabeller(_transport(calls), key=KEY, model_id="configured-model")
    second = ProviderLabeller(_transport(calls), key=KEY, model_id="configured-model")
    with selfcert_label.using_default_labeller(first):
        h1 = selfcert_label.default_labeller().submit(CLEAN, REQ)  # the service's step 4
    with selfcert_label.using_default_labeller(second):
        h2 = selfcert_label.default_labeller().submit(CLEAN, dict(REQ))  # the hub, later, through another instance
    r2 = second.result(h2)
    r1 = first.result(h1)
    assert calls == [15.0]  # ONE call, with the full per-call timeout
    assert r1 is r2 and r1.state == "none_named"
    assert shared_calls_state() == {"in_flight": 0, "cached": 1, "flights": 1, "joined": 1, "cache_hits": 0}


def test_the_faithful_fake_shares_one_flight_between_instances():
    a, b = ReaderBackedLabeller(), ReaderBackedLabeller()
    ha, hb = a.submit(CLEAN, REQ), b.submit(CLEAN, REQ)
    assert shared_calls_state()["in_flight"] == 1 and shared_calls_state()["joined"] == 1
    ra, rb = a.result(ha), b.result(hb)
    assert ra is rb and ra.state == "none_named" and (a.calls, b.calls) == (1, 0)
    # a third submission is a cache hit: no call at all
    hc = ReaderBackedLabeller().submit(CLEAN, REQ)
    assert hc.result() is ra and shared_calls_state()["cache_hits"] == 1


def test_another_answer_another_key_or_another_model_is_another_call():
    calls: list = []
    lab = ProviderLabeller(_transport(calls), key=KEY, model_id="m1")
    lab.result(lab.submit(CLEAN, REQ))
    lab.result(lab.submit(OTHER, REQ))
    assert len(calls) == 2
    other_model = ProviderLabeller(lambda *a, **k: (_ for _ in ()).throw(CallFailure("provider-error")), key=KEY, model_id="m2")
    res = other_model.result(other_model.submit(CLEAN, REQ))
    assert res.state == "unavailable"  # never served the first model's cached success
    other_key = ScriptedLabeller(lambda req, n: reply_json(req), key=KEY + b"x")
    assert other_key.result(other_key.submit(CLEAN, REQ)).record["model_digest"] == model_digest("fake:scripted")
    assert len(other_key.requests) == 1


def test_scripted_labellers_never_share_between_instances():
    a = ScriptedLabeller(lambda req, n: reply_json(req))
    b = ScriptedLabeller(lambda req, n: "not json")
    ra, rb = a.result(a.submit(CLEAN, REQ)), b.result(b.submit(CLEAN, REQ))
    assert (ra.state, rb.state) == ("none_named", "unavailable") and (len(a.requests), len(b.requests)) == (1, 2)


def test_recorded_labellers_share_only_under_a_named_scope():
    inp = build_input(CLEAN, REQ, key=KEY)
    digest = model_digest("recorded-model")
    rec = {inp.requests[0].request_key: {"raw_text": reply_json(inp.requests[0]), "model_digest": digest}}
    a = RecordedLabeller(rec, key=KEY, model_digest=digest)
    b = RecordedLabeller(rec, key=KEY, model_digest=digest)
    a.result(a.submit(CLEAN, REQ))
    b.result(b.submit(CLEAN, REQ))
    assert (a.calls, b.calls) == (1, 1)
    clear_shared_calls()
    c = RecordedLabeller(rec, key=KEY, model_digest=digest, share_scope="round-labels-digest")
    d = RecordedLabeller(rec, key=KEY, model_digest=digest, share_scope="round-labels-digest")
    c.result(c.submit(CLEAN, REQ))
    d.result(d.submit(CLEAN, REQ))
    assert (c.calls, d.calls) == (1, 0)
    with pytest.raises(ValueError):
        RecordedLabeller(rec, key=KEY, model_digest=digest, share_scope="")


def test_a_failure_is_never_cached_and_a_success_is():
    calls: list = []
    outcomes = iter([CallFailure("provider-error"), CallFailure("provider-error"), None])

    def reply(user, n):
        o = next(outcomes)
        if o is not None:
            raise o
        return Reply(_valid_for(user), "end_turn")
    lab = ProviderLabeller(_transport(calls, reply), key=KEY, model_id="m")
    first = lab.result(lab.submit(CLEAN, REQ))
    assert (first.state, first.kind, len(calls)) == ("unavailable", "provider-error", 2)  # the call and its one retry
    assert shared_calls_state()["cached"] == 0
    second = lab.result(lab.submit(CLEAN, REQ))  # the failure was not kept: a new call
    assert second.state == "none_named" and len(calls) == 3
    third = lab.result(lab.submit(CLEAN, REQ))
    assert third is second and len(calls) == 3 and shared_calls_state()["cache_hits"] == 1


def test_the_cache_of_successes_is_an_lru_of_4096(monkeypatch):
    assert labellers.CACHE_SIZE == 4096
    monkeypatch.setattr(labellers, "CACHE_SIZE", 2)
    lab = ReaderBackedLabeller()
    for k in range(3):
        lab.result(lab.submit(CLEAN + f" Line {k}.", REQ))
    assert shared_calls_state()["cached"] == 2
    lab.result(lab.submit(CLEAN + " Line 0.", REQ))  # the oldest was evicted: computed again
    assert lab.calls == 4


def test_a_shared_flight_or_a_cached_success_costs_no_budget():
    calls: list = []
    budget = selfcert_label.CallBudget(1)
    a = BudgetedLabeller(ProviderLabeller(_transport(calls), key=KEY, model_id="m"), budget)
    b = BudgetedLabeller(ProviderLabeller(_transport(calls), key=KEY, model_id="m"), budget)
    ha, hb = a.submit(CLEAN, REQ), b.submit(CLEAN, REQ)
    assert a.result(ha).state == b.result(hb).state == "none_named"
    assert (len(calls), budget.remaining) == (1, 0)
    assert b.result(b.submit(CLEAN, REQ)).state == "none_named"  # a cache hit, with the budget spent
    res = b.result(b.submit(OTHER, REQ))
    assert (res.state, res.kind, len(calls)) == ("unavailable", "budget", 1)


def test_a_provider_labeller_starts_the_call_at_submission():
    calls: list = []
    gate = threading.Event()
    lab = ProviderLabeller(_transport(calls, gate=gate), key=KEY, model_id="m")
    h = lab.submit(CLEAN, REQ)
    for _ in range(500):
        if calls:
            break
        threading.Event().wait(0.01)
    assert calls == [15.0]  # the call began before anyone collected
    gate.set()
    assert lab.result(h).state == "none_named" and len(calls) == 1


def test_a_handle_that_is_never_collected_costs_nothing_more():
    lab = ScriptedLabeller(lambda req, n: reply_json(req))
    h = lab.submit(CLEAN, REQ)
    assert shared_calls_state()["in_flight"] == 1 and lab.requests == []  # nothing computed yet
    del h
    gc.collect()
    assert shared_calls_state()["in_flight"] == 0 and lab.requests == []  # its entry left with it; no call was ever made
    # a provider labeller's flight already started: it makes that one call, settles and leaves the table, and nothing else
    calls: list = []
    plab = ProviderLabeller(_transport(calls), key=KEY, model_id="m")
    plab.submit(CLEAN, REQ)
    gc.collect()
    for _ in range(500):
        if shared_calls_state()["cached"] == 1:
            break
        threading.Event().wait(0.01)
    assert calls == [15.0] and shared_calls_state()["in_flight"] == 0 and shared_calls_state()["cached"] == 1


def test_the_retry_draws_fresh_canaries_inside_the_deadline():
    clock = Clock()
    seen: list = []
    canaries: list = []

    def script(req, n):
        canaries.append([it.text for it in req.items if it.canary is not None])
        seen.append(req.attempt)
        clock.t += 4
        return "not json" if n == 0 else reply_json(req)
    lab = ScriptedLabeller(script, clock=clock)
    res = lab.result(lab.submit(CLEAN, REQ, deadline=clock() + 12))
    assert res.state == "none_named" and seen == [0, 1] and canaries[0] != canaries[1]
    assert lab.requests[1].diagnostic == ("malformed",)
    # the timeouts given to each call: min(15 s, deadline - now - 2 s)
    times: list = []
    tclock = Clock()

    def transport(system, user, *, max_tokens, timeout_s):
        times.append(timeout_s)
        tclock.t += 3
        raise CallFailure("provider-error")
    p = ProviderLabeller(transport, key=KEY, model_id="m", clock=tclock)
    out = p.result(p.submit(CLEAN, REQ, deadline=tclock() + 12))
    assert (out.state, out.kind, times) == ("unavailable", "provider-error", [10.0, 7.0])


def test_a_handle_of_input_that_cannot_be_read_is_unavailable_never_none_named():
    lab = ReaderBackedLabeller()
    for bad in (None, 42, b"bytes"):
        res = lab.result(lab.submit(bad, REQ))
        assert (res.state, res.kind) == ("unavailable", "label-failed")
    assert lab.result(object()).kind == "label-failed"
    big = "\n\n".join(" ".join(f"Sentence {i} has a value of {i} m." for i in range(60)) for _ in range(30))
    res = lab.result(lab.submit(big, REQ))
    assert (res.state, res.kind, lab.calls) == ("unavailable", "oversized", 0)
