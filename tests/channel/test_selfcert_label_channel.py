"""The meaning label wired into the channel (meaning-check design 2.5.1 item 2, 2.5.6, 2.5.8; stage 2a, owner R4).

Every label here is scripted (``ScriptedLabeller``) or made by the faithful fake the suite installs; no provider is called. The
expected values are fixed in the tests:

* T4 (a valid label naming one sentence): exactly one INT-SELF-001 naming the place and the family, the receipt
  ACCEPTED_WITH_FINDINGS, the named claim's success display withheld (NOT_ELIGIBLE), the response gate withholding the answer,
  feedback by place under rule ``self.certification``, and no word of the named sentence in any receipt message, summary,
  reason or feedback;
* T5 (a valid label naming nothing): no INT-SELF finding, the reader-only receipt status (ACCEPTED), record ``none_named``,
  the delivered payload byte-identical;
* T3 (every verdict ``none``, canaries included): INT-SELF-002 ``control`` after exactly one retry with fresh canaries;
* T11 (a timeout; a spent budget): INT-SELF-002 ``timeout``; INT-SELF-002 ``budget`` with no call made;
* a synthesis relayed by the combinator is labelled with ``writer='combinator'``; a forward carries the label of the delivery;
* any exception in label code is INT-SELF-002 ``label-failed``, never INT-INTERNAL-001;
* the record lives on the call's event (``label_json``, ``labelled_text``, ``labelled_text_sha256``), never in a payload.
"""
from __future__ import annotations

import hashlib
import json

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel import feedback as fb
from epinoic_logic.channel.bus import SELFCERT_LABEL_CODES, SELFCERT_LABEL_SEVERITY, answer_label_text, synthesis_label_text
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.selfcert_label import (BudgetedLabeller, CallFailure, UnconfiguredLabeller, build_input, check_t24, shared_calls_state,
                                          using_default_labeller)
from epinoic_logic.selfcert_label.fakes import TEST_KEY, ReaderBackedLabeller, ScriptedLabeller, reply_json
from epinoic_logic.selfcert_label.labellers import Labeller
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
from epinoic_logic.translate.outcome import WITHHELD_SELF_REPORT_MEANING

from .revision_support import GOOD_CLAIMS, GOOD_TEXT, answer, block_for, issue
from .test_channel import CFG, KEY, _speed_problem, _stub_outcome

#: A sentence the rule reader passes, which the scripted label names (a scripted reply decides what it names).
NAMED = "The second table settles the matter for every value."
TEXT = "The speed is 15 m/s.\n\n" + NAMED + " The time is 8 s."
QUESTION = "What is the speed if d = 120 m and t = 8 s?"


def _gate(sentence: str, category: str = "OUTCOME"):
    """A scripted reply naming ``sentence`` (the item whose text is exactly it) and every canary."""
    def script(req, n):
        gated = {it.id: [(sentence, category)] for it in req.items if it.canary is None and it.text == sentence}
        return reply_json(req, gated)
    return script


def _none(req, n):
    return reply_json(req, {})


def _plan(**over):
    base = dict(plan_id="plan-lab", request_id="req-9", task_id="task-9", subject="Physics", task_type="short_answer",
                selected_agent_ids=["physics-specialist", "combinator"], allowed_document_ids=[])
    base.update(over)
    return WorkPlan(**base)


def _report(text=TEXT, rid="rep-a"):
    claims = [("a-1", "The speed is 15 m/s."), ("a-2", NAMED), ("a-3", "The time is 8 s.")]
    return SpecialistReport(report_id=rid, request_id="req-9", task_id="task-9", agent_id="physics-specialist", subject="Physics", task_type="short_answer",
                            original_response=text, response_sha256=sha256_text(text), created_at="2026-11-26T10:00:00Z",
                            claims=[ClaimRecord(request_id="req-9", task_id="task-9", report_id=rid, agent_id="physics-specialist", subject="Physics",
                                                task_type="short_answer", claim_id=cid, claim_text=t, claim_role="quantitative",
                                                proposed_claim_kind="arithmetic") for cid, t in claims])


def _verify_all_entailed(claim, report):
    return _stub_outcome(claim, report, _speed_problem(claim.claim_id, 15), "ENTAILED")


def _channel(labeller=None, events=None, verify=True):
    return TranslatorChannel(_plan(), signing_key=KEY, key_id="t", config=CFG, verify_claim_fn=_verify_all_entailed if verify else None,
                             observers=[events.append] if events is not None else (), selfcert_labeller=labeller)


def _respond(labeller=None, events=None, text=TEXT, verify=True):
    ch = _channel(labeller, events, verify)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    msg, rc = ch.respond(m.message_id, _report(text))
    return ch, m, msg, rc


def _label_codes(rc):
    return [f.code for f in rc.findings if f.code.startswith("INT-SELF-")]


def _record(ch, message_id):
    rec_json, _text, _req = ch.label_records[message_id]
    return json.loads(rec_json)


# ============================================================================================ codes and tables
def test_the_label_codes_and_their_severities():
    assert dict(SELFCERT_LABEL_CODES) == {"named": "INT-SELF-001", "unavailable": "INT-SELF-002"}
    assert dict(SELFCERT_LABEL_SEVERITY) == {"INT-SELF-001": "warning", "INT-SELF-002": "warning"}
    assert fb.CODE_RULES["INT-SELF-001"] == ("channel", ("self.certification",))
    assert "INT-SELF-002" not in fb.CODE_RULES  # an outage is never fed back


# ============================================================================================ T4
def test_t4_a_valid_label_naming_one_sentence():
    events: list = []
    lab = ScriptedLabeller(_gate(NAMED))
    ch, m, msg, rc = _respond(lab, events)
    named = [f for f in rc.findings if f.code == "INT-SELF-001"]
    assert len(named) == 1 and _label_codes(rc) == ["INT-SELF-001"]
    f = named[0]
    assert f.severity == "warning" and f.deterministic is False
    assert f.message.startswith("paragraph 2, sentence 1 of the answer:") and "family OUTCOME" in f.message
    assert f.claim_ids == ["a-2"] and f.message_ids == [msg.message_id]
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    # T18 on the channel's surfaces: the named claim's success display is withheld; the others keep theirs
    shown = {o.claim_id: o.display_status.value for o in rc.outcomes}
    assert shown == {"a-1": "ENTAILED", "a-2": "NOT_ELIGIBLE", "a-3": "ENTAILED"}
    a2 = next(o for o in rc.outcomes if o.claim_id == "a-2")
    assert WITHHELD_SELF_REPORT_MEANING in a2.summary
    assert "Claim outcomes: {'ENTAILED': 2, 'NOT_ELIGIBLE': 1}" in rc.summary
    assert "Self-certification gate: 1 sentence(s) named, withheld." in rc.summary
    # no token of the named sentence in any receipt message or the summary
    for text in [x.message for x in rc.findings] + [rc.summary]:
        for token in ("second table", "settles", "matter for every value"):
            assert token not in text
    # the record: named, with the offsets of the sentence in the labelled text, on the event only
    rec = _record(ch, msg.message_id)
    assert rec["state"] == "named" and rec["writer"] == "specialist"
    assert [(s["place"], s["category"], TEXT[s["start"]:s["end"]]) for s in rec["spans"]] == [("paragraph 2, sentence 1", "OUTCOME", NAMED)]
    ev = events[-1]
    assert ev.kind == "response" and ev.message_id == msg.message_id
    assert json.loads(ev.label_json) == rec and ev.labelled_text == TEXT
    assert ev.labelled_text_sha256 == hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
    assert ev.label_sha256 == hashlib.sha256(ev.label_json.encode("utf-8")).hexdigest()
    assert "selfcert-label-record" not in ev.envelope_json and "selfcert-label-record" not in ev.receipt_json
    assert "label_json" not in json.dumps(msg.payload) and "seal" not in msg.payload
    assert check_t24(rc) == () and check_t24(ev) == ()
    # the release gate of the channel withholds it, whatever the accuracy
    gate = assess_response([rc], synthesis_required=False)
    assert gate.display_status == "WITHHELD" and gate.delivered is False
    assert gate.label.startswith("withheld: the self-certification gate withholds the answer: a sentence of the answer certifies")
    assert all("second table" not in r for r in gate.reasons) and "second table" not in gate.label
    # exactly one label call, no retry
    assert len(lab.requests) == 1


def test_t4_feedback_names_the_place_never_the_passage():
    lab = ScriptedLabeller(_gate("The pattern recurs throughout the passage."))
    from .revision_support import plan as rev_plan
    ch = TranslatorChannel(rev_plan(), signing_key=KEY, key_id="hub", config=CFG, selfcert_labeller=lab)
    text = GOOD_TEXT + " The pattern recurs throughout the passage."
    case = answer(text, GOOD_CLAIMS, ch=ch)
    named = [f for f in case.rc.findings if f.code == "INT-SELF-001"]
    assert len(named) == 1 and named[0].message.startswith("paragraph 1, sentence 3 of the answer:") and named[0].claim_ids == []
    flaws = [c for c in fb.eligible_flaws(case.rc, case.rep, case.req) if c.code == "INT-SELF-001"]
    assert len(flaws) == 1
    c = flaws[0]
    assert (c.rule, c.basis, c.claim_ids, c.params, c.flaw_class, c.removal_ok) == ("self.certification", "channel", (), (), "fidelity", True)
    assert [(e.kind, e.detail) for e in c.evidence] == [("receipt_finding", "paragraph 1, sentence 3")]
    block = block_for(case)
    rendered = fb.render_revision_message(block)
    assert "Place in your answer: paragraph 1, sentence 3." in rendered
    assert "pattern recurs" not in rendered and "throughout the passage" not in rendered
    # the channel binds and contains the block: an INT-SELF-001 flaw by place is an allowlisted finding of the receipt
    _m2, _req2, rq2 = issue(case, block)
    assert rq2.status is TransmissionStatus.ACCEPTED and rq2.findings == []


def test_two_named_places_are_two_flaws():
    def script(req, n):
        gated = {it.id: [(it.text, "CHECK")] for it in req.items if it.canary is None and it.text in ("The tone darkens here.", "The image returns at the end.")}
        return reply_json(req, gated)
    from .revision_support import plan as rev_plan
    ch = TranslatorChannel(rev_plan(), signing_key=KEY, key_id="hub", config=CFG, selfcert_labeller=ScriptedLabeller(script))
    case = answer(GOOD_TEXT + " The tone darkens here.\n\nThe image returns at the end.", GOOD_CLAIMS, ch=ch)
    places = sorted(e.detail for c in fb.eligible_flaws(case.rc, case.rep, case.req) if c.code == "INT-SELF-001" for e in c.evidence)
    assert places == ["paragraph 1, sentence 3", "paragraph 2, sentence 1"]


# ============================================================================================ T5
def test_t5_a_valid_label_naming_nothing_changes_nothing():
    events: list = []
    _ch0, _m0, msg0, base = _respond(ReaderBackedLabeller(), verify=True)  # the reader-only baseline (the faithful fake)
    ch, _m, msg, rc = _respond(ScriptedLabeller(_none), events)
    assert _label_codes(rc) == [] and rc.status is base.status is TransmissionStatus.ACCEPTED
    assert sorted(f.code for f in rc.findings) == sorted(f.code for f in base.findings) == []
    assert _record(ch, msg.message_id)["state"] == "none_named"
    assert msg.payload_sha256 == msg0.payload_sha256 and msg.payload == msg0.payload  # the delivered payload is byte-identical
    assert "Self-certification gate" not in rc.summary  # a label that names nothing is never shown, as a pass or otherwise
    assert [o.display_status.value for o in rc.outcomes] == ["ENTAILED", "ENTAILED", "ENTAILED"]
    assert check_t24(rc) == () and check_t24(events[-1]) == ()


# ============================================================================================ T3 and T11
def test_t3_a_reply_that_drops_the_canaries_is_unavailable_after_one_retry():
    lab = ScriptedLabeller(lambda req, n: reply_json(req, {}, canaries=False))
    ch, _m, msg, rc = _respond(lab)
    unread = [f for f in rc.findings if f.code == "INT-SELF-002"]
    assert len(unread) == 1 and _label_codes(rc) == ["INT-SELF-002"]
    assert "(control; label selfcert-label-" in unread[0].message and unread[0].claim_ids == []
    assert len(lab.requests) == 2 and lab.requests[0].request_key != lab.requests[1].request_key  # one retry, fresh canaries
    rec = _record(ch, msg.message_id)
    assert (rec["state"], rec["kind"]) == ("unavailable", "control")
    assert [o.display_status.value for o in rc.outcomes] == ["ENTAILED", "ENTAILED", "ENTAILED"]  # an outage names no claim
    assert assess_response([rc], synthesis_required=False).display_status == "WITHHELD"
    assert not [c for c in fb.eligible_flaws(rc, _report(), ch.requests[_m.message_id]) if c.code.startswith("INT-SELF")]
    assert check_t24(rc) == ()


def test_t11_a_timeout_and_a_spent_budget():
    lab = ScriptedLabeller([CallFailure("timeout"), CallFailure("timeout")])
    _ch, _m, _msg, rc = _respond(lab)
    unread = [f for f in rc.findings if f.code == "INT-SELF-002"]
    assert len(unread) == 1 and "(timeout; label selfcert-label-" in unread[0].message
    inner = ScriptedLabeller(_none)
    ch, _m, msg, rc = _respond(BudgetedLabeller(inner, 0))
    unread = [f for f in rc.findings if f.code == "INT-SELF-002"]
    assert len(unread) == 1 and "(budget; label selfcert-label-" in unread[0].message
    assert inner.requests == []  # no provider call
    assert _record(ch, msg.message_id)["kind"] == "budget"


def test_the_unconfigured_labeller_withholds_every_answer_the_reader_passes():
    ch, _m, msg, rc = _respond(UnconfiguredLabeller())
    assert [(f.code, "(not-configured; label selfcert-label-" in f.message) for f in rc.findings if f.code.startswith("INT-SELF")] == [("INT-SELF-002", True)]
    assert _record(ch, msg.message_id)["kind"] == "not-configured"
    assert "Self-certification gate: not read, withheld." in rc.summary


# ============================================================================================ the reader first
def test_a_reader_refusal_is_journaled_skipped_with_no_label_call():
    lab = ScriptedLabeller(_none)
    text = "The speed is 15 m/s.\n\nEvery figure above was verified twice and is correct."
    ch, _m, msg, rc = _respond(lab, text=text, verify=False)
    assert lab.requests == [] and _label_codes(rc) == []
    rec = _record(ch, msg.message_id)
    assert (rec["state"], rec["reason"]) == ("skipped", "reader-refused")


# ============================================================================================ label code that fails
class _Raises(Labeller):
    def __init__(self, where: str):
        self.where = where

    def submit(self, raw_text, request=None, *, writer="specialist", deadline=None):
        if self.where == "submit":
            raise RuntimeError("submit failed")
        return object()

    def result(self, handle):
        raise RuntimeError("collect failed")

    def skipped(self, raw_text, request=None, *, writer="specialist"):
        raise RuntimeError("skip failed")


def test_an_exception_in_label_code_is_int_self_002_label_failed():
    for where in ("submit", "result"):
        ch, _m, msg, rc = _respond(_Raises(where))
        assert [f.code for f in rc.findings if f.code.startswith("INT-")] == ["INT-SELF-002"], where
        f = rc.findings[-1]
        assert "(label-failed;" in f.message and "INT-INTERNAL" not in " ".join(x.code for x in rc.findings)
        assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
        rec_json, text, _req = ch.label_records[msg.message_id]
        assert text == TEXT and (rec_json is None or json.loads(rec_json)["kind"] == "label-failed")
    # a reader refusal whose skipped record cannot be made fails the same way
    ch, _m, msg, rc = _respond(_Raises("result"), text="The speed is 15 m/s.\n\nEvery figure above was verified twice and is correct.", verify=False)
    assert [f.code for f in rc.findings if f.code.startswith("INT-SELF")] == ["INT-SELF-002"]


def test_a_labeller_that_is_not_one_is_refused_at_construction():
    import pytest
    with pytest.raises(TypeError):
        TranslatorChannel(_plan(), signing_key=KEY, selfcert_labeller=object())


# ============================================================================================ the default, looked up at use time
def test_the_default_labeller_is_looked_up_at_each_use():
    ch = _channel(verify=False)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    with using_default_labeller(ScriptedLabeller(_gate(NAMED))):
        _msg, rc = ch.respond(m.message_id, _report())
    assert _label_codes(rc) == ["INT-SELF-001"]
    m2, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    _msg, rc2 = ch.respond(m2.message_id, _report(rid="rep-b"))  # the suite's default again (the faithful fake)
    assert _label_codes(rc2) == []


# ============================================================================================ relays
def test_a_synthesis_is_labelled_with_writer_combinator():
    lab = ScriptedLabeller(_gate("Both figures fit the brief."))
    ch = _channel(lab, verify=False)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    ch.respond(m.message_id, _report())
    text = "The speed is 15 m/s. Both figures fit the brief."
    syn = Synthesis(synthesis_id="syn-1", request_id="req-9", task_id="task-9", combinator_agent_id="combinator", source_report_ids=["rep-a"],
                    claims=[SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["a-1"], transformation="carried"),
                            SynthesizedClaim(claim_id="s-2", text="Both figures fit the brief.", source_claim_ids=["a-2"], transformation="paraphrased")],
                    text=text, text_sha256=sha256_text(text), created_at="2026-11-26T10:05:00Z")
    relayed, rc = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert relayed is not None
    named = [f for f in rc.findings if f.code == "INT-SELF-001"]
    assert len(named) == 1 and named[0].message.startswith("paragraph 1, sentence 2 of the synthesis:") and named[0].claim_ids == ["s-2"]
    rec = _record(ch, relayed.message_id)
    assert rec["writer"] == "combinator" and rec["state"] == "named"
    req = lab.requests[-1]
    context = json.loads(req.user_text.split("<<<DATA context", 1)[1].split("\n", 2)[1])
    assert context["writer"] == "combinator" and context["subject"] == "Physics"
    assert synthesis_label_text(syn) == text  # every claim's words are in the text
    _rec_json, labelled, req_json = ch.label_records[relayed.message_id]
    assert labelled == text and json.loads(req_json)["task_type"] == "short_answer"
    assert assess_response([rc], synthesis_required=False).display_status == "WITHHELD"


def test_a_forward_carries_the_label_of_the_delivery_and_shares_its_call():
    events: list = []
    ch = _channel(None, events, verify=False)  # the suite's faithful fake, through the default
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    delivered, rc = ch.respond(m.message_id, _report())
    assert _record(ch, delivered.message_id)["state"] == "none_named"
    fwd, frc = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, _report(), in_reply_to=delivered.message_id)
    assert fwd is not None and frc.status is not TransmissionStatus.REJECTED
    assert _record(ch, fwd.message_id) == _record(ch, delivered.message_id)
    assert events[-1].kind == "relay_forward" and events[-1].labelled_text == TEXT
    assert shared_calls_state()["flights"] == 1  # the forward joined the delivery's cached label


# ============================================================================================ the record can be re-validated
def test_the_journaled_request_rebuilds_the_input_and_the_record_revalidates():
    events: list = []
    lab = ScriptedLabeller(_gate(NAMED))
    ch, _m, msg, _rc = _respond(lab, events)
    ev = events[-1]
    rec = json.loads(ev.label_json)
    again = build_input(ev.labelled_text, json.loads(ev.label_request_json), key=TEST_KEY)
    assert again.input_key == rec["input_key"]
    assert build_input(ev.labelled_text, ch.requests[_m.message_id], key=TEST_KEY).input_key == rec["input_key"]
    assert lab.revalidate_record(rec, ev.labelled_text, json.loads(ev.label_request_json)).ok is True
    assert UnconfiguredLabeller().revalidate_record(rec, ev.labelled_text, json.loads(ev.label_request_json)).ok is False


def test_a_digest_only_event_keeps_the_digests_and_drops_the_record():
    events: list = []
    _respond(ScriptedLabeller(_gate(NAMED)), events)
    ev = events[-1]
    d = ev.to_dict()
    assert {"label_json", "label_sha256", "labelled_text", "labelled_text_sha256", "label_request_json"} <= set(d)
    small = ev.as_digest_only()
    assert (small.label_json, small.labelled_text, small.label_request_json) == (None, None, None)
    assert (small.label_sha256, small.labelled_text_sha256) == (ev.label_sha256, ev.labelled_text_sha256)
    assert ev.content_size() > small.content_size()


def test_a_request_event_and_a_refused_answer_carry_no_record():
    events: list = []
    ch = _channel(ScriptedLabeller(_none), events, verify=False)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    assert events[-1].label_json is None and events[-1].labelled_text is None
    _msg, rc = ch.respond(m.message_id, _report().model_copy(update={"agent_id": "someone-else"}))
    assert rc.status is TransmissionStatus.REJECTED and events[-1].label_json is None and events[-1].labelled_text_sha256 is None


# ============================================================================================ the labelled text
def test_a_structured_report_is_labelled_with_its_own_texts():
    rep = _report().model_copy(update={"assumptions": ["Assume no air resistance."]})
    assert answer_label_text(rep) == TEXT + "\n\nAssume no air resistance."
    assert answer_label_text(_report()) == TEXT
    assert answer_label_text(rep, TEXT) == TEXT  # an answer that arrived as prose is labelled as it arrived


def test_a_report_relayed_by_its_author_is_labelled_on_its_delivery_text():
    lab = ScriptedLabeller(_gate(NAMED))
    ch = _channel(lab, verify=False)
    m, _req, _rq = ch.request("router", "physics-specialist", QUESTION)
    delivered, _rc = ch.respond(m.message_id, _report())
    relayed, rrc = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, _report())
    assert relayed is not None and rrc.status is not TransmissionStatus.REJECTED
    assert [f.message.split(":")[0] for f in rrc.findings if f.code == "INT-SELF-001"] == ["paragraph 2, sentence 1 of the answer"]
    assert ch.label_records[relayed.message_id][1] == TEXT and _record(ch, relayed.message_id) == _record(ch, delivered.message_id)
    assert len(lab.requests) == 1  # the relay shared the delivery's label: one call
