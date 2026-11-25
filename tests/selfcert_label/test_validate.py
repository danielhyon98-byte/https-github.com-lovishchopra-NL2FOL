"""Validation of a reply (meaning-check design 2.5.4): T10 (each malformed shape and its fault), T9 (anchoring under the
reader's visible form, with the original offsets pinned) and T8 (an unlocated span: one repair retry, then malformed; with a
second valid span, named)."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.selfcert_label import build_input, validate_reply
from epinoic_logic.selfcert_label.fakes import ScriptedLabeller, canary_spans, id_of, reply_json
from epinoic_logic.selfcert_label.labellers import Reply

from .conftest import CODES

REQ = {"subject": "physics", "task_type": "short_answer"}
TEXT = "The speed is 15 km/h.\n\nEvery figure here stands firm."


@pytest.fixture
def inp(key, test_prompt):
    return build_input(TEXT, REQ, key=key, prompt_path=test_prompt)


def _v(inp, raw, stop="end_turn"):
    return validate_reply(raw, stop, inp.requests[0], inp.scope)


def test_a_valid_reply_keeps_only_offsets_and_category(inp):
    req = inp.requests[0]
    raw = reply_json(req, {id_of(req, 1): [("stands firm", "OUTCOME")]})
    v = _v(inp, raw)
    assert (v.state, v.fault) == ("named", None)
    (sp,) = v.spans
    assert TEXT[sp.start:sp.end] == "stands firm" and sp.category == "OUTCOME" and sp.segment == 1
    assert v.canary_positive == v.canary_caught >= 1
    assert "stands" not in json.dumps(v.as_dict())


def test_a_valid_reply_that_names_nothing_is_none_named(inp):
    v = _v(inp, reply_json(inp.requests[0]))
    assert (v.state, v.fault, v.spans) == ("none_named", None, ())


def test_t10_each_malformed_reply_gives_its_fault(inp):
    req = inp.requests[0]
    good = json.loads(reply_json(req))
    missing = dict(good, verdicts=good["verdicts"][:-1])
    assert _v(inp, json.dumps(missing)).fault == "incomplete"
    dup_key = json.dumps(good)[:-1] + ', "schema": "selfcert-label/1"}'
    assert _v(inp, dup_key).fault == "malformed" and _v(inp, dup_key).notes == ("duplicate-key",)
    deep = dict(good, verdicts=good["verdicts"][:-1] + [{"id": good["verdicts"][-1]["id"], "v": "gated",
                                                         "spans": [{"quote": [[[[1]]]], "category": "CHECK"}]}])
    assert _v(inp, json.dumps(deep)).fault == "malformed" and _v(inp, json.dumps(deep)).notes == ("depth",)
    nan = json.dumps(good)[:-1] + ', "x": NaN}'
    assert _v(inp, nan).fault == "malformed" and _v(inp, nan).notes == ("non-finite",)
    inf = json.dumps(good)[:-1] + ', "x": 1e999}'
    assert _v(inp, inf).notes == ("non-finite",)
    big = json.dumps(good) + " " * (33 * 1024)
    assert _v(inp, big).fault == "oversized_reply"
    assert _v(inp, json.dumps(good), stop="max_tokens").fault == "truncated"
    for v in (_v(inp, json.dumps(missing)), _v(inp, dup_key), _v(inp, big)):
        assert v.state == "unavailable" and v.spans == ()


def test_shape_faults_are_malformed_and_id_faults_incomplete(inp):
    req = inp.requests[0]
    good = json.loads(reply_json(req))
    ids = [v["id"] for v in good["verdicts"]]
    cases = {
        "extra key": dict(good, note="all clear"),
        "wrong schema": dict(good, schema="selfcert-label/2"),
        "unknown value": dict(good, verdicts=[dict(good["verdicts"][0], v="maybe")] + good["verdicts"][1:]),
        "spans on none": dict(good, verdicts=[dict(good["verdicts"][0], v="none", spans=[{"quote": "x", "category": "CHECK"}])]
                              + good["verdicts"][1:]),
        "no spans on gated": dict(good, verdicts=[{"id": ids[0], "v": "gated"}] + good["verdicts"][1:]),
        "nine spans": dict(good, verdicts=[{"id": ids[0], "v": "gated", "spans": [{"quote": "The", "category": "CHECK"}] * 9}]
                           + good["verdicts"][1:]),
        "unknown category": dict(good, verdicts=[{"id": ids[0], "v": "gated", "spans": [{"quote": "The", "category": "PASS"}]}]
                                 + good["verdicts"][1:]),
        "long quote": dict(good, verdicts=[{"id": ids[0], "v": "gated", "spans": [{"quote": "x" * 301, "category": "CHECK"}]}]
                           + good["verdicts"][1:]),
        "empty quote": dict(good, verdicts=[{"id": ids[0], "v": "gated", "spans": [{"quote": "", "category": "CHECK"}]}]
                            + good["verdicts"][1:]),
        "a reason field": dict(good, verdicts=[dict(good["verdicts"][0], reason="looks fine")] + good["verdicts"][1:]),
    }
    for name, obj in cases.items():
        v = _v(inp, json.dumps(obj))
        assert (v.state, v.fault) == ("unavailable", "malformed"), name
    assert _v(inp, "not json at all").fault == "malformed"
    assert _v(inp, "").fault == "malformed"
    assert _v(inp, None).fault == "malformed"
    dup_id = dict(good, verdicts=good["verdicts"] + [good["verdicts"][0]])
    assert _v(inp, json.dumps(dup_id)).fault == "incomplete"
    reordered = dict(good, verdicts=list(reversed(good["verdicts"])))
    assert _v(inp, json.dumps(reordered)).fault == "incomplete"
    extra_none = dict(good, verdicts=good["verdicts"] + [{"id": "s99", "v": "none"}])
    assert _v(inp, json.dumps(extra_none)).fault == "incomplete"


def test_one_code_fence_is_stripped_and_no_more(inp):
    body = reply_json(inp.requests[0])
    assert _v(inp, "```json\n" + body + "\n```").state == "none_named"
    assert _v(inp, "```\n" + body + "\n```").state == "none_named"
    assert _v(inp, "```json\n```json\n" + body + "\n```\n```").fault == "malformed"
    assert _v(inp, "```python\n" + body + "\n```").fault == "malformed"


def test_a_missed_canary_fails_the_control_check(inp):
    req = inp.requests[0]
    v = _v(inp, reply_json(req, canaries=False))
    assert (v.state, v.fault) == ("unavailable", "control")
    cid = req.positive_canary_ids[0]
    wrong = {cid: [("words that are not in the canary", "CHECK")]}
    assert _v(inp, reply_json(req, wrong, canaries=False)).fault == "control"


def test_a_quote_may_not_touch_a_placeholder_or_a_substitute(key, test_prompt):
    req_d = dict(REQ, user_input="Explain why the method gives a fair test.")
    text = 'The task says "the method gives a fair test" and this is checked. Then >>> verified.'
    inp = build_input(text, req_d, key=key, prompt_path=test_prompt)
    req = inp.requests[0]
    sid = id_of(req, 0)
    # the placeholder token itself and a quote spanning it are unlocated
    for q in ("⟦task⟧", 'says "⟦task⟧" and', "the method gives a fair test"):
        v = validate_reply(reply_json(req, {sid: [(q, "CHECK")]}), "end_turn", req, inp.scope)
        assert (v.state, v.fault) == ("unavailable", "malformed"), q
    ok = validate_reply(reply_json(req, {sid: [("this is checked", "CHECK")]}), "end_turn", req, inp.scope)
    assert ok.state == "named"
    sid2 = id_of(req, 1)
    v = validate_reply(reply_json(req, {sid2: [("››› verified", "CHECK")]}), "end_turn", req, inp.scope)
    assert v.fault == "malformed"
    v = validate_reply(reply_json(req, {sid2: [("verified", "CHECK")]}), "end_turn", req, inp.scope)
    assert v.state == "named" and text[v.spans[0].start:v.spans[0].end] == "verified"


@pytest.mark.parametrize("text,quote,expected", [
    # letter-spaced, given in folded form
    ("Paragraph one.\n\nThe result is V E R I F I E D now.", "VERIFIED", "V E R I F I E D"),
    # look-alike letters (Cyrillic) given in Latin
    ("Paragraph one.\n\nТhis аnswer is соrrect.", "This answer is correct", "Тhis аnswer is соrrect"),
    # enclosed letters
    ("Paragraph one.\n\nThe speed is 15 km/h. \U0001F185\U0001F174\U0001F181\U0001F178\U0001F175\U0001F178\U0001F174\U0001F173",
     "VERIFIED", "\U0001F185\U0001F174\U0001F181\U0001F178\U0001F175\U0001F178\U0001F174\U0001F173"),
    # an invisible character inside the word, removed in rendering and mapped back
    ("Paragraph one.\n\nAll of it was veri​fied.", "verified", "veri​fied"),
    # fullwidth letters
    ("Paragraph one.\n\nStatus: ＶＥＲＩＦＩＥＤ.", "VERIFIED",
     "ＶＥＲＩＦＩＥＤ"),
])
def test_t9_a_folded_quote_is_located_at_the_pinned_original_offsets(key, test_prompt, text, quote, expected):
    inp = build_input(text, REQ, key=key, prompt_path=test_prompt)
    req = inp.requests[0]
    sid = id_of(req, len(inp.scope.segments) - 1)
    v = validate_reply(reply_json(req, {sid: [(quote, "STATUS")]}), "end_turn", req, inp.scope)
    assert v.state == "named"
    (sp,) = v.spans
    assert text[sp.start:sp.end] == expected
    assert (sp.start, sp.end) == (text.index(expected), text.index(expected) + len(expected))


def test_t8_an_unlocated_span_alone_is_retried_once_then_malformed(key, test_prompt):
    def script(req, n):
        return reply_json(req, {id_of(req, 1): [("this answer is verified", "CHECK")]})  # not in the sentence
    lab = ScriptedLabeller(script, key=key, prompt_path=test_prompt)
    res = lab.label(TEXT, REQ)
    assert (res.state, res.kind) == ("unavailable", "malformed")
    assert len(lab.requests) == 2 and lab.requests[1].attempt == 1 and lab.requests[1].diagnostic == ("malformed",)
    assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-002"]


def test_t8_with_a_second_valid_span_the_reply_names(key, test_prompt):
    def script(req, n):
        return reply_json(req, {id_of(req, 1): [("this answer is verified", "CHECK"), ("stands firm", "OUTCOME")]})
    lab = ScriptedLabeller(script, key=key, prompt_path=test_prompt)
    res = lab.label(TEXT, REQ)
    assert res.state == "named" and len(lab.requests) == 1
    assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-001"]


def test_a_span_naming_an_unknown_id_is_malformed_unless_another_survives(inp):
    req = inp.requests[0]
    extra = [{"id": "s99", "v": "gated", "spans": [{"quote": "speed", "category": "CHECK"}]}]
    assert _v(inp, reply_json(req, extra=extra)).fault == "malformed"
    v = _v(inp, reply_json(req, {id_of(req, 1): [("stands firm", "OUTCOME")]}, extra=extra))
    assert v.state == "named" and v.notes == ("unlocated",)


def test_t10_a_truncated_reply_splits_the_chunk_into_two_halves(key, test_prompt):
    calls = []

    def script(req, n):
        calls.append(req)
        if n == 0:
            return Reply(reply_json(req), "max_tokens")
        return Reply(reply_json(req), "end_turn")
    lab = ScriptedLabeller(script, key=key, prompt_path=test_prompt)
    res = lab.label(TEXT, REQ)
    assert res.state == "none_named"
    assert [(r.attempt, r.part) for r in calls] == [(0, None), (1, 0), (1, 1)]
    assert [i.segment for i in calls[1].items if i.segment is not None] == [0]
    assert [i.segment for i in calls[2].items if i.segment is not None] == [1]
    assert all(canary_spans(r) for r in calls)  # each half carries its own canaries
