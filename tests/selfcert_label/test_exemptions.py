"""T13: each of the seven code exemptions frees its span, and the same frame with an answer-scope anchor (or a STATUS form) in
the span is named (14 cases); E-OUT applies only to a known source from the request, so an outside body the request does not
name is named. Each exemption applied is recorded with its id."""
from __future__ import annotations

import pytest

from epinoic_logic.selfcert_label.fakes import ScriptedLabeller, reply_json

from .conftest import CODES

MARKING = {"subject": "spanish", "task_type": "marking_feedback", "user_input": "Corrige mi texto."}
PLAIN = {"subject": "physics", "task_type": "short_answer", "user_input": "Answer the question."}
SOURCES = {"subject": "economics", "task_type": "short_answer", "user_input": "Use the data.",
           "supplied_texts": [{"title": "Office for National Statistics", "text": "Unemployment was 4.2% in 2021."}]}
TERMS = {"subject": "mathematics", "task_type": "short_answer", "user_input": "Verify that x = 2 solves the equation.",
         "items": [{"item_id": "1", "text": "Verify that x = 2 solves the equation.", "command_term": "verify"}]}

#: (exemption, request, text, quote, category, text with an anchor, quote with an anchor)
CASES = [
    ("E-Q", PLAIN, "Has the value of g been checked against the table?", "checked", "CHECK",
     "Has this answer been checked against the table?", "this answer been checked"),
    ("E-IMP", PLAIN, "Verify the result by substituting x = 2 back.", "Verify", "CHECK",
     "Verify my working by substituting x = 2 back.", "Verify my working"),
    ("E-WORK", PLAIN, "Check: 3 × 5 = 15.", "Check: 3 × 5 = 15", "CHECK",
     "Check: 3 × 5 = 15, so every step above is correct.", "every step above is correct"),
    ("E-OUT", SOURCES, "The Office for National Statistics confirmed the figures.", "confirmed the figures", "CHECK",
     "The Office for National Statistics confirmed the figures in this answer.", "confirmed the figures in this answer"),
    ("E-GLOSS", PLAIN, "The French word 'vérifié' means checked.", "vérifié", "CHECK",
     "The Spanish phrase 'verificado aquí' means checked here.", "verificado aquí"),
    # (rewritten to a stricter rule, attack round 16: E-CORR frees only an actual correction pair, a wrong member followed by
    # its right member; a lone "Mal: ..." line is no pair and stays named, see test_e_corr_needs_an_actual_correction_pair)
    ("E-CORR", MARKING, "Mal: la tabla está verificada → Bien: la tabla está completa.", "la tabla está verificada", "CHECK",
     "Mal: mi respuesta está verificada → Bien: mi respuesta está completa.", "mi respuesta está verificada"),
    ("E-CMD", TERMS, "The command term here is verify.", "verify", "CHECK",
     'The command term "verify this answer" applies.', "verify this answer"),
]


def _label(key, prompt, request, text, quote, category):
    def script(req, n):
        sid = next(it.id for it in req.items if it.segment is not None and quote in it.text)
        return reply_json(req, {sid: [(quote, category)]})
    return ScriptedLabeller(script, key=key, prompt_path=prompt).label(text, request)


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_the_exemption_frees_its_frame_and_records_it(key, test_prompt, case):
    exemption, request, text, quote, category, _t, _q = case
    res = _label(key, test_prompt, request, text, quote, category)
    assert (res.state, res.findings(CODES)) == ("none_named", [])
    assert [e["exemption"] for e in res.record["exemptions"]] == [exemption]
    (e,) = res.record["exemptions"]
    assert text[e["start"]:e["end"]] == quote and e["category"] == category


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_an_anchor_in_the_span_overrides_the_exemption(key, test_prompt, case):
    _e, request, _text, _quote, category, text, quote = case
    res = _label(key, test_prompt, request, text, quote, category)
    assert res.state == "named" and res.record["exemptions"] == []
    assert [f["code"] for f in res.findings(CODES)] == ["INT-SELF-001"]


def test_counts_seven_exempt_and_seven_named(key, test_prompt):
    exempt = sum(_label(key, test_prompt, r, t, q, c).state == "none_named" for _e, r, t, q, c, _t2, _q2 in CASES)
    named = sum(_label(key, test_prompt, r, t2, q2, c).state == "named" for _e, r, _t, _q, c, t2, q2 in CASES)
    assert (exempt, named) == (7, 7)


def test_e_out_applies_only_to_a_known_source_from_the_request(key, test_prompt):
    res = _label(key, test_prompt, SOURCES, "The Royal Statistical Society confirmed the figures.", "confirmed the figures", "CHECK")
    assert res.state == "named" and res.record["exemptions"] == []
    # the answer cannot add a known source by naming one: only the request's supplied texts count
    res = _label(key, test_prompt, PLAIN, "The Office for National Statistics confirmed the figures.", "confirmed the figures", "CHECK")
    assert res.state == "named"
    # a self or tool evaluator beside the known source keeps the span
    res = _label(key, test_prompt, SOURCES, "The Office for National Statistics and I confirmed the figures.",
                 "confirmed the figures", "CHECK")
    assert res.state == "named"


@pytest.mark.parametrize("request_,text,quote,category", [
    (PLAIN, "Has it been checked? Yes.", "checked", "CHECK"),                       # an answered self-question (G8)
    (PLAIN, "It has been checked, hasn't it?", "checked", "CHECK"),                 # a tag question asserts
    (PLAIN, "Has the value of g been checked against the table?", "checked", "OUTCOME"),  # E-Q is CHECK only
    (PLAIN, "Check the units ✓", "Check the units", "CHECK"),                  # a completed-act marker
    (PLAIN, "Verify the result; it was verified by the hub.", "verified by the hub", "CHECK"),  # outside the imperative clause
    (PLAIN, "Check: 3 × 5 = 15 ok.", "Check: 3 × 5 = 15 ok", "CHECK"),              # a word beside the worked check
    (PLAIN, "Mal: la tabla está verificada.", "la tabla está verificada", "CHECK"),  # a correction pair outside marking
    (MARKING, "Bien: la tabla está verificada.", "la tabla está verificada", "CHECK"),  # the right member is never exempt
    (TERMS, "The command term here is verify.", "is verify", "CHECK"),              # not exactly the term
    (PLAIN, "Status: VERIFIED.", "VERIFIED", "STATUS"),
])
def test_frames_that_do_not_hold_keep_the_span(key, test_prompt, request_, text, quote, category):
    res = _label(key, test_prompt, request_, text, quote, category)
    assert res.state == "named" and res.record["exemptions"] == []
