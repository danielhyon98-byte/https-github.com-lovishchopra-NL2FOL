"""Channel behaviour found wanting by the round-10 clearance overseers (integrated round c3), fixed by the core fixer:

* critical: the cross-claim consistency check pooled translator symbols that only share a name (ch-p10c 'x0', glossed 'value of
  the left-hand side of a stated equation' in seven claims; maa-t16 'fm3' for f(-3) and F(-3), 'd1' for f'(-1) and f'(1)), so
  correct answers carried error-level INT-CONFLICT-001 and their syntheses INT-CONFLICT-001 and INT-CONFLICT-002;
* critical: a sort clash between two translations of one answer (ec-t16 'boats19' and 'boats25', Real in g11.7 and Int in g11.9)
  was an error-level INT-GLOSSARY-001 that withheld the joint check, on the receipt and on the synthesis;
* critical: the decline and deferral reader missed declines of one item (bm-t16 i4, ge-t16 i2) and applied a deferral of part
  (d) to every part (ec-t16), a coordinated academic-integrity decline included (ll-t16, exchanges x05a, x05b, x06);
* minor: C0 control characters inside a specialist's response were delivered inside a claim (rule control-text).

The recorded material is ``data/c3_core_material.json`` (copied verbatim from the round and the lens's exchanges)."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.channel.bus import (CONTROL_TEXT_CLASS, bidi_control_message, control_text_message, report_bidi_findings, withheld_deliverable,
                                       withheld_items)
from epinoic_logic.channel.request_parser import extract_items
from epinoic_logic.translate.contracts import SpecialistReport, sha256_text

from ..core_hostile import SHAPES, one, sweep
from ..timing import measure
from .c3_core_support import C3, deliver_c3, deliver_exchange, relay, synthesis_of, translations


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def named(findings, code: str) -> list:
    return [f for f in findings if f.code == code]


# ------------------------------------------------------------------ critical: one symbol name for two quantities is no contradiction

@pytest.mark.parametrize("task", ["ch-p10c", "maa-t16"])
def test_a_name_shared_by_different_quantities_is_no_contradiction_on_the_receipt_or_the_synthesis(task):
    hub, ch, reply, rc = deliver_c3(task, translations(task))
    try:
        assert not named(rc.findings, "INT-CONFLICT-001"), [(f.claim_ids, f.message[:200]) for f in named(rc.findings, "INT-CONFLICT-001")]
        _msg, syn = relay(ch, synthesis_of(ch, reply, C3["c3"]["syntheses"][task]))
        assert not [f for f in syn.findings if f.code in ("INT-CONFLICT-001", "INT-CONFLICT-002")], [(f.code, f.claim_ids) for f in syn.findings if f.code.startswith("INT-CONFLICT")]
    finally:
        hub.close()
    # what remains is a translation fault, at most a warning, naming the symbols
    rest = [f for f in rc.findings if f.code.startswith(("INT-CONFLICT", "INT-GLOSSARY"))]
    assert all(f.severity == "warning" for f in rest), [(f.code, f.severity) for f in rest]
    if task == "maa-t16":
        msgs = " ".join(f.message for f in named(rc.findings, "INT-GLOSSARY-005"))
        assert "'fm3'" in msgs and "functions ['f'] against ['F']" in msgs      # f(-3) of the cubic is not F(-3) of the antiderivative
        assert "'d1'" in msgs and "arithmetic ['3+6-9'] against ['3-6-9']" in msgs  # f'(-1) is not f'(1)


def test_ec_t16_a_sort_clash_between_translations_is_a_warning_and_the_check_still_runs():
    hub, ch, reply, rc = deliver_c3("ec-t16", translations("ec-t16"))
    try:
        assert not named(rc.findings, "INT-GLOSSARY-001")
        clash = [f for f in named(rc.findings, "INT-GLOSSARY-005") if "declared as Real" in f.message]
        assert {f.message.split("'")[1] for f in clash} == {"boats19", "boats25"} and all(f.severity == "warning" for f in clash)
        assert all(any(c.startswith("g11.7") for c in f.claim_ids) and any(c.startswith("g11.9") for c in f.claim_ids) for f in clash)
        assert not [f for f in rc.findings if f.code.startswith(("INT-GLOSSARY", "INT-CONFLICT")) and f.severity == "error"]
        _msg, syn = relay(ch, synthesis_of(ch, reply, C3["c3"]["syntheses"]["ec-t16"]))
        assert not named(syn.findings, "INT-GLOSSARY-001") and not [f for f in syn.findings if f.code.startswith(("INT-GLOSSARY", "INT-CONFLICT")) and f.severity == "error"]
    finally:
        hub.close()


# ------------------------------------------------------------------ critical: declines and deferrals read per item

def _coverage(rc) -> dict:
    return {c.item_id: c.addressed for c in rc.coverage}


def _req004(rc) -> dict:
    return {f.message.split()[2]: f.message for f in named(rc.findings, "INT-REQ-004")}


@pytest.mark.parametrize("name,deliver", [("ll-t16", deliver_c3), ("x05a", deliver_exchange), ("x05b", deliver_exchange)])
def test_a_coordinated_academic_integrity_decline_declines_the_essay_and_its_bound(name, deliver):
    hub, _ch, _reply, rc = deliver(name)
    hub.close()
    assert not [f for f in named(rc.findings, "INT-REQ-005") if f.severity == "error"], [f.message[:200] for f in named(rc.findings, "INT-REQ-005")]
    assert _coverage(rc) == {"i1": False} and "the answer declines the deliverable" in _req004(rc)["i1"]
    assert all(c.satisfied is None and c.method == "not_checkable" for c in rc.constraint_results if c.constraint_id), rc.constraint_results


@pytest.mark.parametrize("task,item,words", [("bm-t16", "i4", "LEGO comparison: I cannot give"),
                                             ("ge-t16", "i2", "The February 2023 Turkey and Syria earthquakes are not used in this answer")])
def test_a_decline_of_one_item_is_recorded_on_that_item_and_every_other_item_keeps_its_coverage(task, item, words):
    hub, _ch, _reply, rc = deliver_c3(task)
    hub.close()
    cov = _coverage(rc)
    assert cov[item] is False and all(v for k, v in cov.items() if k != item), cov
    assert "the answer declines this item" in _req004(rc)[item] and words in _req004(rc)[item]


@pytest.mark.parametrize("name,deliver,pending", [("ec-t16", deliver_c3, "i4"), ("x06", deliver_exchange, "i3")])
def test_a_deferral_of_one_part_leaves_the_answered_parts_addressed(name, deliver, pending):
    hub, _ch, _reply, rc = deliver(name)
    hub.close()
    cov = _coverage(rc)
    assert cov[pending] is False and all(v for k, v in cov.items() if k != pending), cov
    req = _req004(rc)
    assert set(req) == {pending} and "the answer defers this item to the student's reply" in req[pending] and "pending" in req[pending]


def test_a_deferral_or_decline_that_names_no_part_still_withholds_every_item():
    """The round-8 readings stay: a decline of the whole deliverable, and a deferral of 'the full evaluation', name no part."""
    items = extract_items("(a) Describe the method. [2] (b) Evaluate the study. [6]")
    w = withheld_items('Here is a plan.\n\nReply "approve" and I will write the full evaluation within 500 words.', items)
    assert set(w) == {"i1", "i2"} and all(kind == "deferred" and whole for kind, _s, whole in w.values())
    w = withheld_items("I can't write the analysis or the conclusion sections, because they must be your own work.", items)
    assert set(w) == {"i1", "i2"} and all(kind == "declined" for kind, _s, _w in w.values())
    # an answer that withholds nothing withholds no item, and an item merely mentioned in a refusal of something else is kept
    assert withheld_items("(a) The method used a random sample. (b) The study is valid because the sample was large.", items) == {}
    assert withheld_items("(b) I cannot be sure the sample was random, but the study is valid overall.", items) == {}
    assert withheld_deliverable("Reply \"approve\" and I will write the full answer to part (d).")[0] == "deferred"


# ------------------------------------------------------------------ minor: C0 control characters (rule control-text)

def _payload(text: str, response: str = "Revenue rose from $40m to $50m, an increase of 25%.") -> dict:
    ids = dict(request_id="r", task_id="t", report_id="rep-t-0", agent_id="economics-specialist", subject="Economics", task_type="short_answer")
    return dict(ids, original_response=response, response_sha256=sha256_text(response), created_at="2026-11-15T10:00:00Z",
                claims=[dict(ids, claim_id="g1.1", claim_text=text, claim_role="point", materiality="material")])


def _deliver_raw(payload):
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.integrity import WorkPlan
    from .c2_core_support import CFG, KEY
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Economics", task_type="short_answer",
                           selected_agent_ids=["economics-specialist", "combinator"], allowed_document_ids=[]))
    m, _req, _rq = hub.dispatch("t", "economics-specialist", "(a) Define a common pool resource. [2]", [])
    try:
        return hub.receive("t", m.message_id, payload, agent_id="economics-specialist", report_id="rep-t-0")[1]
    finally:
        hub.close()


def _control_refusals(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-REQ-009" and "rule control-text" in f.message]


def test_a_response_holding_c0_control_characters_is_refused_naming_them():
    """The adversarial lens's rob-nul variant: '(a) Definition\\x00\\x01\\x02 [2]' was delivered inside claim g2.1."""
    text = "(a) Definition\x00\x01\x02 [2]\n\nA common pool resource is rivalrous and non-excludable."
    rc = _deliver_raw(text)
    assert rc.status.value == "REJECTED" and len(_control_refusals(rc)) == 1 and not rc.outcomes, [(f.code, f.message[:160]) for f in rc.findings]
    f = _control_refusals(rc)[0]
    assert "U+0000 at character offset 14" in f.message and "U+0001" in f.message and "U+0002" in f.message and "Definition" not in f.message
    # a structured report: the response is clean, a claim's text is not; JSON text with the escaped control is refused alike
    for payload in (_payload("Revenue rose\x07 to $50m."), json.dumps(_payload("Revenue rose\x7f to $50m."))):
        rc = _deliver_raw(payload)
        assert rc.status.value == "REJECTED" and _control_refusals(rc) and _control_refusals(rc)[0].claim_ids == ["g1.1"], [(f.code, f.message[:160]) for f in rc.findings]


@pytest.mark.parametrize("ok", ["\t", "\n", "\r\n"])
def test_control_a_tab_a_line_feed_and_a_carriage_return_are_not_refused(ok):
    rc = _deliver_raw(f"(a) A common pool resource is rivalrous{ok}and non-excludable.")
    assert rc.status.value != "REJECTED" and not _control_refusals(rc)
    assert control_text_message("response text", f"a{ok}b") is None


def test_the_rule_reads_the_whole_c0_range_but_tab_line_feed_and_carriage_return():
    refused = {chr(c) for c in range(0x80) if control_text_message("t", f"a{chr(c)}b") is not None}
    assert refused == {chr(c) for c in range(0x20) if c not in (9, 10, 13)} | {"\x7f"}
    assert CONTROL_TEXT_CLASS and bidi_control_message("response text", "a\x00b") is not None  # the response rule the Overseer binds


# ------------------------------------------------------------------ the readers added in this pass are linear

def _entries(text: str):
    items = extract_items("(a) Define the term. [2] (b) Explain the effect. [4] (c) Evaluate the policy. [15]")
    yield "withheld_items", lambda: withheld_items(text, items)
    yield "control_text_message", lambda: control_text_message("response text", text)
    yield "bidi_control_message", lambda: bidi_control_message("response text", text)
    rep = SpecialistReport.model_validate(_payload(text[:4000] or "x", response=text or "x"))
    yield "report_bidi_findings", lambda: report_bidi_findings(rep)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c3_channel_readers(shape):
    """The readers this pass added or extended, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("name,text", [
    ("every sentence a decline", "I cannot give that figure. " * 15_000),
    ("every character a control", "\x01" * 399_999 + "x"),
    ("declines naming a part", "I cannot give part (a) or part (b) here, so I have left them out. " * 6_000),
])
def test_the_c3_channel_readers_are_linear_on_long_hostile_responses(name, text):
    items = extract_items("(a) Define the term. [2] (b) Explain the effect. [4] (c) Evaluate the policy. [15]")
    timing = measure(lambda: withheld_items(text, items), bound=3.0, repeat=3, label=f"withheld_items, {name}")
    assert timing.holds, timing
    timing = measure(lambda: bidi_control_message("response text", text), bound=2.0, repeat=3, label=f"control-text, {name}")
    assert timing.holds, timing
