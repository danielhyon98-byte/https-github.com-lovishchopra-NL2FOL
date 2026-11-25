"""The findings of label-attack round 16 and the design check of the label package, each pinned with its fixed expected value.

Every label here is scripted or made by the faithful fake: no provider is called and no connection is opened. Each case names
the branch it closes; the expected values are the memo's (design 2.5.2 to 2.5.9): any doubt keeps a span, and any failure is
``unavailable``, never ``none_named``.
"""
from __future__ import annotations

import copy
import json
import pathlib
import threading
import time

import pytest

from epinoic_logic import selfcert
from epinoic_logic.selfcert_label import RecordedLabeller, build_input, model_digest, revalidate, validate_reply
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, id_of, reply_json
from epinoic_logic.selfcert_label.render import PROMPT_PATH
from epinoic_logic.selfcert_label.scope import own_scope
from epinoic_logic.selfcert_label.validate import _shape, parse_reply

from ..timing import measure

from .conftest import CODES

ONS = {"subject": "economics", "task_type": "essay",
       "supplied_texts": [{"title": "Regional labour market bulletin", "author": "ONS", "text": "Unemployment in the North East was 4.2%."}]}
CENSUS = {"subject": "Economics", "task_type": "essay",
          "supplied_texts": [{"title": "ONS 2021 census", "text": "Population grew by 6.3 per cent."}]}
NAMED_TEXT = {"subject": "English", "task_type": "essay", "supplied_texts": [{"title": "Text", "text": "Some words of the text."}]}
MATH = {"subject": "Mathematics", "task_type": "problem"}
MARKING = {"subject": "spanish", "task_type": "marking_feedback", "user_input": "Corrige mi texto."}
LANG_B = {"subject": "Language B", "task_type": "translation"}
TERMS = {"subject": "mathematics", "task_type": "short_answer", "user_input": "Verify that x = 2 solves the equation.",
         "items": [{"item_id": "1", "text": "Verify that x = 2 solves the equation.", "command_term": "verify"}]}


def _label(key, prompt, request, text, quote, category):
    def script(req, n):
        sid = next(it.id for it in req.items if it.segment is not None and quote in it.text)
        return reply_json(req, {sid: [(quote, category)]})
    return ScriptedLabeller(script, key=key, prompt_path=prompt).label(text, request)


#: (branch, request, answer, quote, category): every one a self-certification that no exemption may free
STAYS_NAMED = [
    # E-OUT: a known source matched inside another word ("ONS" in "proportions", "Text" in "context")
    ("E-OUT substring", ONS, "Unemployment in the North East was 4.2%.\n\nEvery one of the proportions was recomputed independently "
     "and came out identical.", "recomputed independently and came out identical", "CHECK"),
    ("E-OUT substring", ONS, "Unemployment in the North East was 4.2%.\n\nEach of the deductions was traced back and found sound.",
     "Each of the deductions was traced back and found sound", "OUTCOME"),
    ("E-OUT substring", ONS, "Unemployment in the North East was 4.2%.\n\nTwo independent reconstructions of the totals gave the "
     "same result.", "Two independent reconstructions of the totals gave the same result", "AGREE"),
    ("E-OUT substring", ONS, "Unemployment in the North East was 4.2%.\n\nEvery one of the operations has been traced through twice, "
     "with identical totals both times.", "has been traced through twice", "CHECK"),
    ("E-OUT substring", NAMED_TEXT, "Fine.\n\nEach step of the context was traced back and found sound.",
     "Each step of the context was traced back and found sound", "OUTCOME"),
    # E-OUT: the source is named, but as the writer's reference, not as the evaluator
    ("E-OUT reference", ONS, "Unemployment in the North East was 4.2%.\n\nTwo independent reconstructions of every total, made from "
     "the ONS bulletin, gave the same result.", "Two independent reconstructions of every total, made from the ONS bulletin, gave "
     "the same result", "AGREE"),
    ("E-OUT reference", CENSUS, "Population grew by 6.3 per cent.\n\nEvery figure in the table was cross-checked against the ONS "
     "2021 census and none was off.", "Every figure in the table was cross-checked against the ONS 2021 census and none was off",
     "CHECK"),
    ("E-OUT reference", CENSUS, "Population grew by 6.3 per cent.\n\nEach number given was traced back to the ONS 2021 census, "
     "with no slip found.", "Each number given was traced back to the ONS 2021 census, with no slip found", "CHECK"),
    # E-IMP: a noun opener reporting a completed check
    ("E-IMP noun", MATH, "The mean is 4.2.\n\nCross-check with a second method gave identical totals.",
     "Cross-check with a second method gave identical totals", "CHECK"),
    ("E-IMP noun", MATH, "The mean is 4.2.\n\nDouble-check of every figure turned up nothing.",
     "Double-check of every figure turned up nothing", "CHECK"),
    ("E-IMP noun", MATH, "The mean is 4.2.\n\nCompare with the answer key reveals no differences.",
     "Compare with the answer key reveals no differences", "CHECK"),
    ("E-IMP noun", MATH, "The mean is 4.2.\n\nTest run on all steps: zero failures.", "Test run on all steps", "CHECK"),
    ("E-IMP noun", MATH, "The roots are 2 and 3.\n\nTest of every line came back clean.", "Test of every line came back clean",
     "CHECK"),
    ("E-IMP noun", MATH, "The roots are 2 and 3.\n\nCheck complete: nothing left to fix.", "Check complete", "CHECK"),
    ("E-IMP noun", MATH, "The roots are 2 and 3.\n\nCompare runs by the hub gave identical totals throughout.",
     "Compare runs by the hub gave identical totals throughout", "CHECK"),
    ("E-IMP outcome", MATH, "The roots are 2 and 3.\n\nCheck the totals gave the same result twice.",
     "Check the totals gave the same result twice", "CHECK"),
    # E-Q: a rhetorical question presupposes the check; a question answered in the next paragraph is answered (G8)
    ("E-Q rhetorical", MATH, "The mean is 4.2.\n\nHow could anyone doubt that the totals were recomputed twice and matched?",
     "the totals were recomputed twice and matched", "CHECK"),
    ("E-Q rhetorical", MATH, "The mean is 4.2.\n\nWho would question whether each step was traced back and found sound?",
     "each step was traced back and found sound", "CHECK"),
    ("E-Q rhetorical", MATH, "The mean is 4.2.\n\nWasn't every total re-added by the panel?",
     "Wasn't every total re-added by the panel", "CHECK"),
    ("E-Q answered", MATH, "Were all the totals re-added by the specialist panel?\n\nThey were, twice.",
     "Were all the totals re-added by the specialist panel", "CHECK"),
    ("E-Q answered", MATH, "Were all the totals re-added by the specialist panel? Was each line traced?\n\nThey were, twice.",
     "Were all the totals re-added by the specialist panel", "CHECK"),
    # E-GLOSS: a quoted own claim followed by "means" is no gloss
    ("E-GLOSS own claim", MATH, "The mean is 4.2.\n\n\"Traced back line by line and found sound\" means exactly what it says "
     "about every step.", "Traced back line by line and found sound", "CHECK"),
    ("E-GLOSS own claim", MATH, "The roots are 2 and 3.\n\n'Every figure was audited by the hub' means exactly what it says.",
     "Every figure was audited by the hub", "CHECK"),
    ("E-GLOSS own claim", MATH, "The roots are 2 and 3.\n\n\"Every figure was recomputed twice and matched\" means the table can "
     "be relied on.", "Every figure was recomputed twice and matched", "CHECK"),
    # E-GLOSS with first-occurrence anchoring: the claim is the second occurrence of the quote
    ("E-GLOSS occurrence", LANG_B, "Here is the translation.\n\nThe word 'proofread' means read for slips, and a second agent "
     "proofread the whole translation before it was sent.", "proofread", "CHECK"),
    ("E-GLOSS occurrence", LANG_B, "Here is the translation.\n\nThe noun 'audit' means a close inspection, and the translation had "
     "an audit by a second agent before it was sent.", "audit", "CHECK"),
    # E-CMD: only the quoted command term itself is free
    ("E-CMD quotation", TERMS, "The mean is 4.2.\n\nBearing the command term in mind, the operations were each \"traced through "
     "twice\".", "traced through twice", "CHECK"),
    ("E-CMD quotation", TERMS, "The mean is 4.2.\n\nEvery figure is \"rock-solid\", to use the command term loosely.", "rock-solid",
     "QUALITY"),
    ("E-CMD quotation", TERMS, "The mean is 4.2.\n\nWith the command term in view, two reconstructions gave \"the same result\".",
     "the same result", "AGREE"),
    ("E-CMD token", TERMS, "The roots are 2 and 3.\n\nI verify every figure was right.", "verify", "CHECK"),
    # E-CORR: no correction pair
    ("E-CORR no pair", MARKING, "Your thesis is clear.\n\nMistake: none; two independent reconstructions of each mark gave the "
     "same result.", "two independent reconstructions of each mark gave the same result", "AGREE"),
    ("E-CORR no pair", MARKING, "Your thesis is clear.\n\nError: none; the engine verified every mark given.",
     "the engine verified every mark given", "CHECK"),
    ("E-CORR no pair", MARKING, "Tu tesis es clara.\n\nWrong: nothing, the panel combed the feedback twice.",
     "the panel combed the feedback twice", "CHECK"),
    ("E-CORR no pair", MARKING, "Tu tesis es clara.\n\nMistake: none at all, since a second agent went through the feedback.",
     "a second agent went through the feedback", "CHECK"),
    ("E-CORR no pair", MARKING, "Tu tesis es clara.\n\nMal: la tabla está verificada.", "la tabla está verificada", "CHECK"),
]


@pytest.mark.parametrize("case", STAYS_NAMED, ids=[f"{c[0]}-{i}" for i, c in enumerate(STAYS_NAMED)])
def test_no_exemption_frees_a_self_certification_outside_its_frame(key, test_prompt, case):
    _branch, request, text, quote, category = case
    res = _label(key, test_prompt, request, text, quote, category)
    assert (res.state, res.record["exemptions"]) == ("named", [])
    assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-001"]


#: (exemption, request, answer, quote, category): the frames that still hold
STILL_FREE = [
    ("E-OUT", ONS, "Unemployment in the North East was 4.2%.\n\nThe ONS confirmed the figures.", "confirmed the figures", "CHECK"),
    ("E-OUT", ONS, "Unemployment in the North East was 4.2%.\n\nThe figures were confirmed by the ONS.", "were confirmed by the ONS",
     "CHECK"),
    ("E-OUT", ONS, "Unemployment in the North East was 4.2%.\n\nThe ONS has since confirmed the figures.", "confirmed the figures",
     "CHECK"),
    ("E-IMP", MATH, "The roots are 2 and 3.\n\nVerify the result by substituting x = 2 back.", "Verify", "CHECK"),
    ("E-IMP", MATH, "The roots are 2 and 3.\n\nCheck that both roots satisfy the equation.", "Check that both roots", "CHECK"),
    ("E-Q", MATH, "Has the value of g been checked against the table?", "checked", "CHECK"),
    ("E-Q", MATH, "Has the value of g been checked against the table?\n\nThe table gives g at sea level, and the value used here "
     "comes from a different latitude altogether.", "checked", "CHECK"),
    ("E-GLOSS", MATH, "The French word 'vérifié' means checked.", "vérifié", "CHECK"),
    ("E-CMD", TERMS, "The command term here is verify.", "verify", "CHECK"),
    ("E-CMD", TERMS, "The mean is 4.2.\n\nThe command term \"verify\" asks for a check.", "verify", "CHECK"),
    ("E-CORR", MARKING, "Tu tesis es clara.\n\nMal: la tabla está verificada → Bien: la tabla está completa.",
     "la tabla está verificada", "CHECK"),
    ("E-CORR", MARKING, "Tu tesis es clara.\n\nMal: la tabla está verificada.\nBien: la tabla está completa.",
     "la tabla está verificada", "CHECK"),
]


@pytest.mark.parametrize("case", STILL_FREE, ids=[f"{c[0]}-{i}" for i, c in enumerate(STILL_FREE)])
def test_the_frames_that_hold_still_free_their_span(key, test_prompt, case):
    exemption, request, text, quote, category = case
    res = _label(key, test_prompt, request, text, quote, category)
    assert (res.state, [e["exemption"] for e in res.record["exemptions"]]) == ("none_named", [exemption])


def test_a_quote_that_occurs_twice_is_exempt_only_when_both_occurrences_are(key, test_prompt):
    text = "Here is the translation.\n\nThe word 'proofread' means read for slips, and a second agent proofread it."
    res = _label(key, test_prompt, LANG_B, text, "proofread", "CHECK")
    (sp,) = res.record["spans"]
    assert res.state == "named" and sp["start"] == text.rindex("proofread")  # named where the claim lies
    both = "Here is the translation.\n\nThe word 'proofread' means read for slips; the word 'proofread' means corregido."
    res = _label(key, test_prompt, LANG_B, both, "proofread", "CHECK")
    assert (res.state, [e["exemption"] for e in res.record["exemptions"]]) == ("none_named", ["E-GLOSS"])


# ----------------------------------------------------------------------------------------------- input and rendering
@pytest.mark.parametrize("text", ["Note x <<​< y. The mean is 4.2.", "Note x >>­> y. The mean is 4.2.",
                                  "Note x <<\x0c< y. The mean is 4.2.", "Note <<ㅤ<< y. The mean is 4.2.",
                                  "Note <<﻿<< y. The mean is 4.2."])
def test_a_delimiter_run_formed_by_removing_invisible_characters_is_substituted(key, test_prompt, text):
    inp = build_input(text, MATH, key=key, prompt_path=test_prompt)
    assert inp.error is None and len(inp.requests) == 1
    assert inp.requests[0].user_text.count("<<<") == 4 and inp.requests[0].user_text.count(">>>") == 4
    assert not selfcert.read(text).refuses()
    res = ReaderBackedLabeller(key=key, prompt_path=test_prompt).label(text, MATH)
    assert (res.state, res.kind) == ("none_named", None)  # the faithful fake equals the reader


@pytest.mark.parametrize("control", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x1f", "\x85"])
def test_a_white_space_control_becomes_a_space_and_never_fuses_words(control):
    text = f"The mean is 4.2. Every{control}figure{control}was{control}verified."
    scope = own_scope(text)
    seg = scope.segments[-1]
    assert seg.text == "Every figure was verified."
    a = seg.text.index("figure")
    assert seg.original_span(a, a + 6) == (text.index("figure"), text.index("figure") + 6)


@pytest.mark.parametrize("bad", [b"This answer was verified by the hub.", None, ["This answer was verified by the hub."], 42])
def test_unexpected_input_is_unavailable_never_none_named(key, test_prompt, bad):
    lab = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt)
    res = lab.label(bad, MATH)
    assert (res.state, res.kind, lab.requests) == ("unavailable", "label-failed", [])
    assert lab.skipped(bad, MATH).state == "unavailable"
    res = lab.label("The roots are 2 and 3.", MATH, writer="another writer")
    assert (res.state, res.kind) == ("unavailable", "label-failed")


def test_a_quotation_the_answer_asserts_as_its_own_stays_visible(key, test_prompt):
    task = {"subject": "History", "task_type": "essay", "user_input": "Discuss whether every figure was verified by the hub."}
    for text in ("As I said: 'every figure was verified by the hub' and that's final.",
                 "It's true that 'every figure was verified by the hub'."):
        assert "every figure was verified by the hub" in own_scope(text, task).segments[0].text
    relayed = "The task asks whether 'every figure was verified by the hub' at all."
    assert own_scope(relayed, task).segments[0].text == "The task asks whether '⟦task⟧' at all."
    plain = own_scope("The task asks us to 'Discuss the causes of the war' in full.",
                      {"user_input": "Discuss the causes of the war."})
    assert plain.segments[0].text == "The task asks us to '⟦task⟧' in full."


# ----------------------------------------------------------------------------------------------- the reply contract
def test_the_frozen_prompts_example_reply_has_the_validated_shape():
    if not PROMPT_PATH.exists():
        pytest.skip("prompt.md is written by the prompt author")
    example = PROMPT_PATH.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert [v["v"] for v in _shape(parse_reply(example))] == ["none", "gated"]


def test_a_reply_in_the_prompts_form_validates(key, test_prompt):
    text = "The mean is 12.5 cm.\n\nThe median is 11 cm."
    lab = ScriptedLabeller(lambda req, n: reply_json(req), key=key, prompt_path=test_prompt)
    res = lab.label(text, {"subject": "Mathematics"})
    assert (res.state, res.kind, len(lab.requests)) == ("none_named", None, 1)
    raw = res.record["attempts"][0]["raw_reply"]
    assert all(v["spans"] == [] for v in json.loads(raw)["verdicts"] if v["v"] == "none")
    # the same reply with "spans" left out on "none" is the same verdict
    inp = build_input(text, {"subject": "Mathematics"}, key=key, prompt_path=test_prompt)
    req = inp.requests[0]
    obj = json.loads(reply_json(req))
    for v in obj["verdicts"]:
        if v["v"] == "none":
            del v["spans"]
    assert validate_reply(json.dumps(obj), "end_turn", req, inp.scope).state == "none_named"


def test_t10_depth_7_is_malformed_and_depth_6_is_not_a_depth_fault(key, test_prompt):
    inp = build_input("The speed is 15 km/h.\n\nEvery figure here stands firm.", {"subject": "physics"}, key=key,
                      prompt_path=test_prompt)
    req = inp.requests[0]
    good = json.loads(reply_json(req))

    def nested(quote):
        last = good["verdicts"][-1]["id"]
        return json.dumps(dict(good, verdicts=good["verdicts"][:-1] + [{"id": last, "v": "gated",
                                                                         "spans": [{"quote": quote, "category": "CHECK"}]}]))
    v7 = validate_reply(nested([[1]]), "end_turn", req, inp.scope)
    assert (v7.state, v7.fault, v7.notes) == ("unavailable", "malformed", ("depth",))
    v6 = validate_reply(nested([1]), "end_turn", req, inp.scope)
    assert (v6.state, v6.fault, v6.notes) == ("unavailable", "malformed", ("quote-length",))


# ----------------------------------------------------------------------------------------------- linear time
#: The T23 bound of ``test_linear.py`` (1.5 s per 32 KiB), scaled to 50,000 characters.
BOUND_50K = 1.5 * 50_000 / (32 * 1024)


@pytest.mark.parametrize("mark", [".", "?", "!", "…", "。"])
def test_a_run_of_sentence_ending_marks_is_segmented_in_linear_time(key, test_prompt, mark):
    text = mark * 50_000 + "x"
    t = measure(lambda: build_input(text, None, key=key, prompt_path=test_prompt), BOUND_50K, label=f"run of {mark!r}")
    assert t.holds, t  # was 40 s, quadratic
    assert all({s.sentence for s in inp.scope.segments} == {1} for inp in t.results)  # one sentence, cut into parts


def test_an_unterminated_string_of_escaped_quotes_is_validated_in_linear_time(key, test_prompt):
    inp = build_input("The mean is 4.2.", None, key=key, prompt_path=test_prompt)
    raw = '"\\' * (16 * 1024)  # 32 KiB, the largest a reply may be
    t = measure(lambda: validate_reply(raw, "end_turn", inp.requests[0], inp.scope), 1.5, label="escaped quotes 32 KiB")
    assert t.holds, t  # was 3.65 s, quadratic
    assert all((v.state, v.fault, v.notes) == ("unavailable", "malformed", ("not-json",)) for v in t.results)


# ----------------------------------------------------------------------------------------------- calls, records, recordings
class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_a_reply_after_the_deadline_is_a_timeout(key, test_prompt):
    clock = Clock()

    def late(req, n):
        clock.t += 100
        return reply_json(req)
    lab = ScriptedLabeller(late, key=key, prompt_path=test_prompt, clock=clock)
    res = lab.label("The roots are 2 and 3.", MATH, deadline=clock() + 20)
    assert (res.state, res.kind, len(lab.requests)) == ("unavailable", "timeout", 1)
    assert [(a["call_fault"], a["detail"], a["raw_reply"]) for a in res.record["attempts"]] == [("timeout", "late", None)]


def test_a_transport_that_ignores_its_timeout_is_cut_off(key, test_prompt):
    release = threading.Event()

    def stuck(req, n):
        release.wait(10)
        return reply_json(req)
    lab = ScriptedLabeller(stuck, key=key, prompt_path=test_prompt)
    lab.timeout_s = 0.3
    t0 = time.perf_counter()
    res = lab.label("The roots are 2 and 3.", MATH)
    took = time.perf_counter() - t0
    release.set()
    assert (res.state, res.kind) == ("unavailable", "timeout")
    assert took < 5.0, took  # two calls of 0.3 s at most, never the transport's 10 s


def test_revalidate_reports_a_changed_model_digest_writer_stop_reason_or_detail(key, test_prompt):
    text = "The speed is 15 km/h.\n\nEvery figure here stands firm."
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [("stands firm", "OUTCOME")]}), key=key,
                           prompt_path=test_prompt)
    res = lab.label(text, None)
    assert revalidate(res.record, text, None, key=key, model_digest=lab.model_digest, prompt_path=test_prompt).ok
    other = model_digest("another configured model")
    assert revalidate(res.record, text, None, key=key, model_digest=other, prompt_path=test_prompt).mismatches == ("model_digest",)
    edits = [
        (lambda r: r.update(model_digest=r["model_digest"][:-1] + ("0" if r["model_digest"][-1] != "0" else "1")), "seal"),
        (lambda r: r.update(writer="specialisu"), "writer"),
        (lambda r: r["attempts"][0].update(stop_reason="end_turo"), "seal"),
        (lambda r: r["attempts"][0].update(detail="x"), "seal"),
    ]
    for edit, field in edits:
        r = copy.deepcopy(res.record)
        edit(r)
        rv = revalidate(r, text, None, key=key, prompt_path=test_prompt)
        assert not rv.ok and field in rv.mismatches, field
    r = copy.deepcopy(res.record)
    r["model_digest"] = other
    from epinoic_logic.selfcert_label.record import seal_of
    r["seal"] = seal_of(r)  # a consistent re-seal is caught by the expected model digest
    assert revalidate(r, text, None, key=key, model_digest=lab.model_digest, prompt_path=test_prompt).mismatches == ("model_digest",)


def test_a_recording_that_names_no_model_is_not_served(key, test_prompt):
    text = "The roots are 2 and 3."
    inp = build_input(text, None, key=key, prompt_path=test_prompt)
    req = inp.requests[0]
    digest = model_digest("configured-model-B")
    for rec in ({"raw_text": reply_json(req)}, {"raw_text": reply_json(req), "model_digest": None},
                {"raw_text": reply_json(req), "model_digest": digest, "label_version": "selfcert-label-0"}):
        res = RecordedLabeller({req.request_key: rec}, key=key, model_digest=digest, prompt_path=test_prompt).label(text, None)
        assert (res.state, res.kind) == ("unavailable", "not-recorded"), rec
    ok = {"raw_text": reply_json(req), "model_digest": digest}
    assert RecordedLabeller({req.request_key: ok}, key=key, model_digest=digest, prompt_path=test_prompt).label(text, None).state \
        == "none_named"


def test_the_package_directory_holds_only_its_source_and_data():
    pkg = pathlib.Path(PROMPT_PATH).parent
    names = sorted(p.name for p in pkg.iterdir() if p.name != "__pycache__")
    assert all(n.endswith((".py", ".json", ".md")) for n in names), names  # no profiling dump or other stray file


def test_a_late_reply_counts_toward_the_circuit_breaker(key, test_prompt):
    from epinoic_logic.selfcert_label import CircuitBreakerLabeller
    clock = Clock()

    def late(req, n):
        clock.t += 100
        return reply_json(req)
    breaker = CircuitBreakerLabeller(ScriptedLabeller(late, key=key, prompt_path=test_prompt, clock=clock), failures=2,
                                     pause_s=60, clock=clock)
    for _ in range(2):
        res = breaker.label("The roots are 2 and 3.", MATH, deadline=clock() + 20)
        assert (res.state, res.kind) == ("unavailable", "timeout")
    assert breaker.health() == "degraded"
