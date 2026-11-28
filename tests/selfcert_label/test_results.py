"""Results, the record and the labellers (meaning-check design 2.5.6, 2.5.8): T3 (a suppressed canary: one retry with a fresh
canary, then control), T4 (one named span: one INT-SELF-001 by place and family, no word of the quote outside the raw reply),
T5 (none_named: no finding), T7 (a changed byte of the raw reply does not re-validate), T11 (timeout; budget with no call), T12
(the circuit breaker on a fake clock), the unconfigured default, recorded replies, the cache of successes, and the provider
labeller over an injected transport."""
from __future__ import annotations

import copy
import json
import re

import pytest

from epinoic_logic.selfcert_label import (BudgetedLabeller, CachingLabeller, CallFailure, CircuitBreakerLabeller, KINDS,
                                          ProviderLabeller, RecordedLabeller, Reply, UnconfiguredLabeller, build_input,
                                          default_labeller, model_digest, revalidate)
from epinoic_logic.selfcert_label.fakes import ScriptedLabeller, id_of, reply_json

from .conftest import CODES

REQ = {"subject": "chemistry", "task_type": "short_answer"}
CLEAN = "The molar mass of water is 18 g/mol.\n\nIt boils at 100 degrees Celsius at sea level."
NAMED = "The molar mass of water is 18 g/mol.\n\nEvery figure here stands firm, beyond doubt."
QUOTE = "stands firm, beyond doubt"


class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _all_but_raw(record: dict) -> str:
    rec = copy.deepcopy(record)
    for a in rec["attempts"]:
        a.pop("raw_reply", None)
    return json.dumps(rec, ensure_ascii=False)


def test_t3_a_reply_that_marks_every_id_none_fails_control_after_one_fresh_retry(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: reply_json(req, canaries=False), key=key, prompt_path=test_prompt)
    res = lab.label(CLEAN, REQ)
    assert (res.state, res.kind) == ("unavailable", "control")
    assert len(lab.requests) == 2
    first, retry = lab.requests
    assert (first.attempt, retry.attempt, retry.diagnostic) == (0, 1, ("control",))
    canary = lambda r: [(i.id, i.text) for i in r.items if i.canary is not None]  # noqa: E731
    assert canary(first) != canary(retry)  # fresh canaries
    assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-002"]
    assert res.findings(CODES)[0]["kind"] == "control" and res.withholds


def test_t4_one_named_span_gives_one_finding_by_place_and_family_and_no_word_of_the_quote(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [(QUOTE, "OUTCOME")]}), key=key, prompt_path=test_prompt)
    res = lab.label(NAMED, REQ)
    assert res.state == "named" and len(lab.requests) == 1
    (f,) = res.findings(CODES)
    assert (f["code"], f["place"], f["family"], f["severity"], f["deterministic"]) == (
        "INT-SELF-001", "paragraph 2, sentence 1", "OUTCOME", "warning", False)
    # (rewritten, stage 2a: the message names the label version, which moved selfcert-label-1 -> selfcert-label-2)
    assert f["message"] == ("paragraph 2, sentence 1 of the answer: the meaning label names a self-certification (family OUTCOME; "
                            "label selfcert-label-2): never delivered (rule self-certification-gate)")
    (sp,) = res.record["spans"]
    assert NAMED[sp["start"]:sp["end"]] == QUOTE
    outside = _all_but_raw(res.record) + json.dumps(res.findings(CODES))
    for token in re.findall(r"\w+", QUOTE):
        assert token not in outside, token
    assert QUOTE in res.record["attempts"][0]["raw_reply"]  # the quote stays only in the raw reply


def test_t5_a_valid_none_named_gives_no_finding_and_changes_nothing(key, test_prompt):
    text = str(CLEAN)
    lab = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt)
    res = lab.label(text, REQ)
    assert (res.state, res.kind, res.findings(CODES), res.withholds) == ("none_named", None, [], False)
    assert res.record["state"] == "none_named" and res.record["spans"] == []
    assert text == CLEAN  # the answer is never edited
    assert not any(w in json.dumps(res.record) for w in ("pass", "passed", "verified", "clean", "approved"))


def test_the_record_holds_every_required_field(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [(QUOTE, "OUTCOME")]}), key=key, prompt_path=test_prompt)
    rec = lab.label(NAMED, REQ).record
    # (rewritten to a stricter rule, attack round 16: the record also carries its seal, the SHA-256 of everything else in it)
    assert set(rec) == {"record", "input_key", "label_version", "label_digest", "model_digest", "writer", "state", "kind", "spans",
                        "exemptions", "canary", "attempts", "seal"}
    # (rewritten, stage 2a: the record carries the label version, which moved selfcert-label-1 -> selfcert-label-2)
    assert rec["record"] == "selfcert-label-record/1" and rec["label_version"] == "selfcert-label-2"
    assert re.fullmatch(r"[0-9a-f]{64}", rec["model_digest"]) and rec["model_digest"] == model_digest("fake:scripted")
    (a,) = rec["attempts"]
    assert set(a) == {"chunk", "part", "attempt", "diagnostic", "request_key", "raw_reply", "raw_sha256", "stop_reason",
                      "call_fault", "detail", "validation"}
    assert rec["canary"]["positive"] == rec["canary"]["caught"]


def test_t7_one_changed_byte_of_the_raw_reply_does_not_revalidate(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [(QUOTE, "OUTCOME")]}), key=key, prompt_path=test_prompt)
    res = lab.label(NAMED, REQ)
    ok = revalidate(res.record, NAMED, REQ, key=key, prompt_path=test_prompt)
    assert ok.ok and ok.mismatches == ()
    bad = copy.deepcopy(res.record)
    raw = bad["attempts"][0]["raw_reply"]
    bad["attempts"][0]["raw_reply"] = raw.replace('"gated"', '"gatee"', 1)
    rv = revalidate(bad, NAMED, REQ, key=key, prompt_path=test_prompt)
    assert not rv.ok and "raw_sha256" in rv.mismatches and "validation" in rv.mismatches and "state" in rv.mismatches
    # a whitespace byte that changes no reading still does not re-validate (the digest of the raw reply)
    bad2 = copy.deepcopy(res.record)
    bad2["attempts"][0]["raw_reply"] = raw + " "
    rv2 = revalidate(bad2, NAMED, REQ, key=key, prompt_path=test_prompt)
    # (rewritten to a stricter rule, attack round 16: the record's seal is broken too)
    assert not rv2.ok and rv2.mismatches == ("seal", "raw_sha256")
    # an edited state, a dropped attempt, another answer, another key: each is named
    for edit, field in ((lambda r: r.update(state="none_named"), "state"), (lambda r: r.update(attempts=[]), "state"),
                        (lambda r: r.update(spans=[]), "spans")):
        r = copy.deepcopy(res.record)
        edit(r)
        assert field in revalidate(r, NAMED, REQ, key=key, prompt_path=test_prompt).mismatches
    assert "input_key" in revalidate(res.record, NAMED + " ", REQ, key=key, prompt_path=test_prompt).mismatches
    assert not revalidate(res.record, NAMED, REQ, key=key + b"x", prompt_path=test_prompt).ok
    assert revalidate({"record": "other"}, NAMED, REQ, key=key).mismatches == ("record",)


def test_a_retried_record_revalidates(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: "not json" if n == 0 else reply_json(req), key=key, prompt_path=test_prompt)
    res = lab.label(CLEAN, REQ)
    assert res.state == "none_named" and len(res.record["attempts"]) == 2
    assert revalidate(res.record, CLEAN, REQ, key=key, prompt_path=test_prompt).ok


def test_t11_a_timeout_and_an_exhausted_budget(key, test_prompt):
    def slow(req, n):
        raise TimeoutError
    clock = Clock()
    res = ScriptedLabeller(slow, key=key, prompt_path=test_prompt, clock=clock).label(CLEAN, REQ, deadline=clock() + 30)
    assert (res.state, res.kind) == ("unavailable", "timeout")
    assert [f["kind"] for f in res.findings(CODES)] == ["timeout"]
    # a deadline too close for the full timeout: no retry after a timeout
    lab = ScriptedLabeller(slow, key=key, prompt_path=test_prompt, clock=clock)
    assert lab.label(CLEAN, REQ, deadline=clock() + 10).kind == "timeout" and len(lab.requests) == 1
    # no time left at all: no call
    lab = ScriptedLabeller(slow, key=key, prompt_path=test_prompt, clock=clock)
    assert lab.label(CLEAN, REQ, deadline=clock() + 1).kind == "timeout" and lab.requests == []
    # an exhausted budget: no provider call
    calls = []

    def transport(system, user, *, max_tokens, timeout_s):
        calls.append(timeout_s)
        return Reply("{}", "end_turn")
    budgeted = BudgetedLabeller(ProviderLabeller(transport, key=key, model_id="configured-model", prompt_path=test_prompt), 0)
    res = budgeted.label(CLEAN, REQ)
    assert (res.state, res.kind, calls) == ("unavailable", "budget", [])


def test_each_call_gets_the_remaining_deadline_capped_at_15_seconds(key, test_prompt):
    clock = Clock()
    seen = []

    def transport(system, user, *, max_tokens, timeout_s):
        seen.append((timeout_s, max_tokens))
        clock.t += 5
        raise CallFailure("provider-error")
    ProviderLabeller(transport, key=key, model_id="m", clock=clock, prompt_path=test_prompt).label(CLEAN, REQ, deadline=clock() + 20)
    assert seen == [(15.0, 1200), (13.0, 1200)]


def test_t12_five_consecutive_provider_errors_open_the_breaker_for_60_seconds(key, test_prompt):
    clock = Clock()
    calls = []

    def transport(system, user, *, max_tokens, timeout_s):
        calls.append(clock())
        raise CallFailure("provider-error")
    inner = ProviderLabeller(transport, key=key, model_id="m", clock=clock, prompt_path=test_prompt)
    lab = CircuitBreakerLabeller(inner, clock=clock)
    assert lab.health() == "ok"
    r1 = lab.label(CLEAN, REQ)
    r2 = lab.label(CLEAN, REQ)
    assert len(calls) == 4 and lab.health() == "ok"
    r3 = lab.label(CLEAN, REQ)  # the fifth failure opens the breaker; its retry is not made
    assert len(calls) == 5 and lab.health() == "degraded"
    r4 = lab.label(CLEAN, REQ)  # the sixth call is not made: a fast unavailable
    assert len(calls) == 5 and (r4.state, r4.kind) == ("unavailable", "provider-error")
    assert r4.record["attempts"][0]["detail"] == "circuit-open"
    assert all(r.state == "unavailable" for r in (r1, r2, r3))
    clock.t += 59.9
    lab.label(CLEAN, REQ)
    assert len(calls) == 5 and lab.health() == "degraded"
    clock.t += 0.2
    assert lab.health() == "ok"
    lab.label(CLEAN, REQ)  # calls resume after 60 s
    assert len(calls) == 7


def test_a_reply_closes_the_breaker_count(key, test_prompt):
    clock = Clock()
    # four failures, a reply (malformed, so retried), then three failures: never five in a row
    replies = iter(["err"] * 4 + ["ok"] + ["err"] * 3)

    def transport(system, user, *, max_tokens, timeout_s):
        if next(replies) == "err":
            raise CallFailure("provider-error")
        return Reply("not json", "end_turn")
    lab = CircuitBreakerLabeller(ProviderLabeller(transport, key=key, model_id="m", clock=clock, prompt_path=test_prompt), clock=clock)
    for _ in range(4):
        lab.label(CLEAN, REQ)
    assert lab.health() == "ok" and lab.consecutive == 3


@pytest.mark.real_labeller  # (stage 2a: the suite installs the faithful fake as the default; this test reads the PRODUCTION one)
def test_the_default_labeller_is_unconfigured_and_withholds_everything(key, test_prompt):
    lab = default_labeller()
    assert isinstance(lab, UnconfiguredLabeller) and lab.health() == "off"
    for text in (CLEAN, NAMED, "", "x"):
        res = lab.label(text, REQ)
        assert (res.state, res.kind, res.record["attempts"]) == ("unavailable", "not-configured", [])
        assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-002"]
    h = lab.submit(CLEAN, REQ)
    assert lab.result(h).kind == "not-configured"


def test_a_recorded_labeller_serves_by_request_key_and_an_unrecorded_key_is_not_recorded(key, test_prompt):
    inp = build_input(CLEAN, REQ, key=key, prompt_path=test_prompt)
    req = inp.requests[0]
    digest = model_digest("recorded-model")
    recordings = {req.request_key: {"raw_text": reply_json(req), "stop_reason": "end_turn", "model_digest": digest}}
    lab = RecordedLabeller(recordings, key=key, model_digest=digest, prompt_path=test_prompt)
    assert lab.label(CLEAN, REQ).state == "none_named"
    res = lab.label(NAMED, REQ)
    assert (res.state, res.kind) == ("unavailable", "not-recorded") and len(res.record["attempts"]) == 1
    other = RecordedLabeller(recordings, key=key, model_digest=model_digest("another-model"), prompt_path=test_prompt)
    assert other.label(CLEAN, REQ).kind == "not-recorded"
    # a recorded reply that fails validation is retried; the retry's key is unrecorded, and the reply's fault names the outcome
    bad = {req.request_key: {"raw_text": "{}", "model_digest": digest}}
    res = RecordedLabeller(bad, key=key, model_digest=digest, prompt_path=test_prompt).label(CLEAN, REQ)
    assert (res.state, res.kind) == ("unavailable", "malformed")


def test_the_cache_keeps_successes_only(key, test_prompt):
    n = {"calls": 0}

    def script(req, k):
        n["calls"] += 1
        return reply_json(req) if "boils" in req.user_text else "not json"
    inner = ScriptedLabeller(script, key=key, prompt_path=test_prompt)
    lab = CachingLabeller(inner, maxsize=2)
    assert lab.label(CLEAN, REQ).state == "none_named" and n["calls"] == 1
    assert lab.label(CLEAN, REQ).state == "none_named" and n["calls"] == 1 and lab.hits == 1
    assert lab.label(NAMED, REQ).state == "unavailable" and n["calls"] == 3
    assert lab.label(NAMED, REQ).state == "unavailable" and n["calls"] == 5  # a failure is never cached
    assert len(lab) == 1
    for i in range(3):
        lab.label(CLEAN + f" Line {i} boils.", REQ)
    assert len(lab) == 2  # the LRU bound
    unconfigured = CachingLabeller(UnconfiguredLabeller())
    assert unconfigured.label(CLEAN, REQ).kind == "not-configured" and len(unconfigured) == 0 and unconfigured.health() == "off"


def test_the_provider_labeller_keeps_only_the_model_digest(key, test_prompt):
    seen = []

    def transport(system, user, *, max_tokens, timeout_s):
        seen.append((system, user))
        return ("", "end_turn")
    lab = ProviderLabeller(transport, key=key, model_id="a-configured-model-identifier", prompt_path=test_prompt)
    assert lab.model_digest == model_digest("a-configured-model-identifier")
    assert "a-configured-model-identifier" not in repr(vars(lab))
    res = lab.label(CLEAN, REQ)
    assert (res.state, res.kind) == ("unavailable", "provider-error")  # an empty reply is a provider error
    assert len(seen) == 2 and seen[0][0] == test_prompt.read_text(encoding="utf-8")
    assert "a-configured-model-identifier" not in json.dumps(res.record)


def test_label_code_that_fails_is_unavailable_never_none_named(key, test_prompt, monkeypatch):
    from epinoic_logic.selfcert_label import labellers
    lab = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt)

    def boom(*a, **k):
        raise RuntimeError("label code fault")
    monkeypatch.setattr(labellers, "validate_reply", boom)
    res = lab.label(CLEAN, REQ)
    assert (res.state, res.kind) == ("unavailable", "label-failed")
    monkeypatch.undo()
    res = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt.parent / "absent.md").label(CLEAN, REQ)
    assert (res.state, res.kind) == ("unavailable", "label-failed")


def test_an_oversized_answer_is_withheld_with_no_call(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt)
    big = "\n\n".join(" ".join(f"Sentence {i} has a value of {i} m." for i in range(60)) for _ in range(30))
    res = lab.label(big, REQ)
    assert (res.state, res.kind, lab.requests) == ("unavailable", "oversized", [])


def test_a_skipped_record_and_every_kind_is_named():
    assert KINDS == ("not-configured", "provider-error", "timeout", "budget", "malformed", "incomplete", "control", "oversized",
                     "truncated", "label-failed", "not-recorded")
    res = UnconfiguredLabeller().skipped("This passed the hub's checks.", REQ)
    assert (res.state, res.findings(CODES), res.record["reason"]) == ("skipped", [], "reader-refused")
    assert res.withholds


@pytest.mark.parametrize("codes", [{}, {"named": "INT-SELF-001"}, {"unavailable": "INT-SELF-002"}, {"named": "", "unavailable": ""},
                                   {"named": "self-certified", "unavailable": "INT-SELF-002"}, None, "INT-SELF-001"])
def test_a_finding_is_never_made_without_its_receipt_code_and_never_dropped_for_want_of_one(codes, key, test_prompt):
    """The package names no receipt code of its own (the channel gives them in stage 2, where the overseer registers them): a
    state that gives a finding refuses a missing or malformed code rather than returning no finding (never ``none_named``)."""
    named = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [(QUOTE, "OUTCOME")]}), key=key,
                             prompt_path=test_prompt).label(NAMED, REQ)
    unavailable = UnconfiguredLabeller().label(CLEAN, REQ)
    assert (named.state, unavailable.state) == ("named", "unavailable")
    for res in (named, unavailable):
        if isinstance(codes, dict) and isinstance(codes.get(res.state), str) and codes[res.state].startswith("INT-SELF-"):
            assert [f["code"] for f in res.findings(codes)] == [codes[res.state]]
        else:
            with pytest.raises(ValueError):
                res.findings(codes)
    none_named = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt).label(CLEAN, REQ)
    assert none_named.findings({}) == [] and none_named.state == "none_named"


def test_a_synthesis_is_named_as_the_synthesis(key, test_prompt):
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [(QUOTE, "OUTCOME")]}), key=key, prompt_path=test_prompt)
    res = lab.label(NAMED, REQ, writer="combinator")
    assert res.findings(CODES)[0]["message"].startswith("paragraph 2, sentence 1 of the synthesis:")


@pytest.mark.parametrize("bad_key", [b"", "text", None])
def test_a_canary_key_is_required(bad_key, test_prompt):
    with pytest.raises(ValueError):
        ScriptedLabeller(lambda r, n: "", key=bad_key, prompt_path=test_prompt)
