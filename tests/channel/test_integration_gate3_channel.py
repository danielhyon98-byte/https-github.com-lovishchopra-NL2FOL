"""Integration gate 3: the channel's findings (channel/bus.py).

* blocker, critical (combinator faults): the relay ran the envelope binding, the party checks and the synthesis-id reuse
  check on the caller's Synthesis object before, and independently of, re-validating it. An object built around
  validation (``model_construct``, ``model_copy(update=...)``, a subclass) therefore raised out of the relay (a missing
  ``synthesis_id`` or ``combinator_agent_id``: AttributeError; ``combinator_agent_id=None``: a ValidationError while the
  INT-HANDOFF-002 finding was built; a list or a dict: unhashable), or was delivered and stored under an identity no
  check saw (a subclass whose dump names a combinator the plan did not select was ACCEPTED). The relay now re-validates
  the payload as delivered first, refuses it with INT-REQ-009 when it does not re-validate (nothing raised, nothing
  stored), and runs every identity, party and content check on the object read back from the delivered payload. The same
  holds for a report relayed or forwarded, and for a report handed to ``respond`` (which raised the same way: a report
  whose sender, request or task cannot head an envelope is refused with INT-REQ-009).
* major (correctness, round-2 finding partly fixed): a name of this system's checks that is also an ordinary word of the
  subjects ("the overseer", "the translator", "Z3", "formally confirmed") counted as a check result in any sentence that
  also named a capitalised "<X> report" or the writer's own text ("my essay", "this answer"), so a student's essay supplied
  as a text REJECTED the request (INT-REQ-009) and an answer was INT-REQ-014 and WITHHELD by the gate. Such a name states a
  check result now only when the sentence states that it checked a report or answer of THIS exchange (the name checks it,
  it was checked by the name, or it holds on the name's credit), and a request is never refused on such a name: it is
  dispatched with a warning. The eight sentences of the finding are clean controls for the request, the response and the
  overseer's fidelity check (OVS-FID-009 reads the same rule).
* the class sweep (channel): ``_PART_END_RE`` ("[1" before a long blank run in a request's last part), ``_NOTE_LABEL_RE``
  ("Note" before a long blank run in an answer) and ``_ITEM_LABEL_RE`` split a blank run between two runs (quadratic); their
  runs are possessive now and they match exactly what they matched (the old forms are the specification below).
"""
from __future__ import annotations

import random
import re
import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel import bus as B
from epinoic_logic.channel import request_parser as RP
from epinoic_logic.channel.bus import check_result_statement
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

from ..timing import empty_caches

KEY = b"gate3-channel-key-0123456789abcdef"
COMBINATOR = "dummy-combinator"
TEXT = ("London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
        "Coal smoke from homes and workshops hung over the city for much of the year.")


def codes(receipt) -> list[str]:
    return sorted({f.code for f in receipt.findings})


def _channel() -> TranslatorChannel:
    plan = WorkPlan(plan_id="plan-i", request_id="req-i", task_id="task-i", subject="History", task_type="short_answer",
                    selected_agent_ids=["history-specialist", COMBINATOR])
    ch = TranslatorChannel(plan, signing_key=KEY)
    request_msg, _req, rr = ch.request("router", "history-specialist", "Outline the context of London in 1802 in one paragraph.")
    assert rr.status is TransmissionStatus.ACCEPTED
    msg, rc = ch.respond_text(request_msg.message_id, TEXT, agent_id="history-specialist", report_id="rep-i")
    assert msg is not None, rc.summary
    return ch


def _synthesis(ch: TranslatorChannel) -> Synthesis:
    claims = ch.transmitted_reports["rep-i"].claims
    sc = [{"claim_id": f"s{i}", "text": c.claim_text, "source_claim_ids": [c.claim_id], "transformation": "carried"} for i, c in enumerate(claims)]
    text = " ".join(c["text"] for c in sc)
    return Synthesis.model_validate({"synthesis_id": "syn-i", "request_id": "req-i", "task_id": "task-i", "combinator_agent_id": COMBINATOR,
                                     "source_report_ids": ["rep-i"], "claims": sc, "text": text, "text_sha256": sha256_text(text),
                                     "created_at": "2026-11-01T08:00:00Z"})


def _relay(ch: TranslatorChannel, payload):
    return ch.relay(COMBINATOR, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)


class _RogueSynthesis(Synthesis):
    """A synthesis whose delivered dump names another combinator than its attribute (built around validation)."""

    def model_dump(self, *args, **kwargs):
        data = super().model_dump(*args, **kwargs)
        data["combinator_agent_id"] = "rogue-agent"
        return data


class _RogueReport(SpecialistReport):
    """A report whose delivered dump names another agent than its attribute."""

    def model_dump(self, *args, **kwargs):
        data = super().model_dump(*args, **kwargs)
        data["agent_id"] = "rogue-agent"
        for claim in data.get("claims", []):
            claim["agent_id"] = "rogue-agent"
        return data


_BAD_VALUES = [None, ["x"], {"a": 1}, 5]
_IDENTITY = ("synthesis_id", "combinator_agent_id", "request_id", "task_id")


# ============================================================================================ blocker: the relay re-validates first
@pytest.mark.parametrize("field", _IDENTITY)
def test_a_synthesis_built_without_an_identity_field_is_refused_never_raised(field):
    ch = _channel()
    data = dict(_synthesis(ch).__dict__)
    data.pop(field)
    relayed, rc = _relay(ch, Synthesis.model_construct(**data))
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)
    assert "INT-INTERNAL-001" not in codes(rc) and not ch.syntheses


@pytest.mark.parametrize("value", _BAD_VALUES, ids=repr)
@pytest.mark.parametrize("field", _IDENTITY)
def test_a_synthesis_whose_identity_field_is_none_or_unhashable_is_refused_never_raised(field, value):
    ch = _channel()
    for bad in (_synthesis(ch).model_copy(update={field: value}), Synthesis.model_construct(**{**_synthesis(ch).__dict__, field: value})):
        relayed, rc = _relay(ch, bad)
        assert relayed is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)
        assert "INT-INTERNAL-001" not in codes(rc) and not ch.syntheses


def test_a_synthesis_whose_dump_names_an_unselected_combinator_is_checked_as_delivered():
    """The finding's case (d): ACCEPTED and stored under 'rogue-agent' before; the party and envelope checks now read the
    delivered payload, so the unselected combinator and the envelope mismatch are named and nothing is stored."""
    ch = _channel()
    relayed, rc = _relay(ch, _RogueSynthesis.model_validate(_synthesis(ch).model_dump()))
    assert relayed is None and rc.status is TransmissionStatus.REJECTED, codes(rc)
    assert {"INT-HANDOFF-002", "INT-ENV-008"} <= set(codes(rc)), codes(rc)
    named = next(f for f in rc.findings if f.code == "INT-HANDOFF-002")
    assert "rogue-agent" in named.message and "syn-i" not in ch.syntheses


@pytest.mark.parametrize("field", ("report_id", "agent_id", "request_id", "task_id"))
def test_a_report_relayed_with_a_broken_identity_field_is_refused_never_raised(field):
    ch = _channel()
    rep = ch.transmitted_reports["rep-i"]
    data = dict(rep.__dict__)
    data.pop(field)
    for bad in [SpecialistReport.model_construct(**data)] + [rep.model_copy(update={field: v}) for v in _BAD_VALUES[:3]]:
        relayed, rc = ch.relay("history-specialist", AgentRole.SPECIALIST, COMBINATOR, AgentRole.COMBINATOR, bad)
        assert relayed is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)
        assert "INT-INTERNAL-001" not in codes(rc)
        forwarded, rf = ch.relay("router", AgentRole.ROUTER, COMBINATOR, AgentRole.COMBINATOR, bad)
        assert forwarded is None and rf.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rf), codes(rf)


def test_a_report_whose_dump_names_another_agent_is_checked_as_delivered():
    ch = _channel()
    rep = ch.transmitted_reports["rep-i"]
    relayed, rc = ch.relay("history-specialist", AgentRole.SPECIALIST, COMBINATOR, AgentRole.COMBINATOR, _RogueReport.model_validate(rep.model_dump()))
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and "INT-ENV-008" in codes(rc), codes(rc)


def _fresh():
    plan = WorkPlan(plan_id="plan-r", request_id="req-i", task_id="task-i", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"])
    ch = TranslatorChannel(plan, signing_key=KEY)
    msg, _req, _rr = ch.request("router", "history-specialist", "Outline the context of London in 1802 in one paragraph.")
    return ch, msg, _channel().transmitted_reports["rep-i"]


@pytest.mark.parametrize("field", ("report_id", "agent_id", "request_id", "task_id"))
def test_a_response_with_a_broken_identity_field_is_refused_never_raised(field):
    ch, msg, rep = _fresh()
    data = dict(rep.__dict__)
    data.pop(field)
    for bad in [SpecialistReport.model_construct(**data)] + [rep.model_copy(update={field: v}) for v in _BAD_VALUES[:3]]:
        delivered, rc = ch.respond(msg.message_id, bad)
        assert delivered is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)
        assert "INT-INTERNAL-001" not in codes(rc) and not ch.transmitted_reports


def test_a_response_whose_dump_names_another_agent_is_checked_as_delivered():
    ch, msg, rep = _fresh()
    delivered, rc = ch.respond(msg.message_id, _RogueReport.model_validate(rep.model_dump()))
    assert delivered is None and rc.status is TransmissionStatus.REJECTED and {"INT-ENV-008", "INT-HANDOFF-002"} <= set(codes(rc)), codes(rc)
    assert not ch.transmitted_reports


def test_controls_valid_objects_are_delivered_with_the_receipt_they_had():
    """Negative controls: a synthesis, a relayed report, a forward and a response that validated on construction are
    delivered exactly as before (the re-validation adds nothing to their receipts)."""
    ch = _channel()
    syn = _synthesis(ch)
    relayed, rc = _relay(ch, syn)
    assert relayed is not None and rc.status is not TransmissionStatus.REJECTED and "INT-REQ-009" not in codes(rc), codes(rc)
    assert ch.syntheses["syn-i"] == syn and Synthesis.model_validate(relayed.payload) == syn
    rep = ch.transmitted_reports["rep-i"]
    handed, rh = ch.relay("history-specialist", AgentRole.SPECIALIST, COMBINATOR, AgentRole.COMBINATOR, rep)
    assert handed is not None and "INT-REQ-009" not in codes(rh), codes(rh)
    ch2, msg, rep2 = _fresh()
    delivered, rd = ch2.respond(msg.message_id, rep2)
    assert delivered is not None and rd.status is not TransmissionStatus.REJECTED, codes(rd)
    # the same synthesis as a mapping gets the same receipt codes as the object
    ch3 = _channel()
    _m, as_mapping = _relay(ch3, _synthesis(ch3).model_dump(mode="json", exclude_none=True))
    assert codes(as_mapping) == codes(rc)


# ============================================================================================ major: framed check names
CFG = SolverConfig(timeout_ms=4000)
#: The finding's supplied texts (each REJECTED with INT-REQ-009 before): content, never a check result of the exchange.
FRAMED_TEXTS = [
    ("History", "history-specialist", "Explain how plantation labour was controlled in Jamaica.",
     "The Colonial Office report confirmed that the overseer flogged workers who failed to meet the quota."),
    ("English A: Literature", "english-specialist", "Comment on the student's essay about The Metamorphosis.",
     "In my essay I show that the translator's choice of 'vermin' holds closer to Kafka's Ungeziefer than earlier versions."),
    ("History", "history-specialist", "Explain the significance of the Treaty of Versailles.",
     "This report shows the treaty was formally confirmed by the Allied powers in January 1920."),
    ("Computer Science", "computer-science-specialist", "Evaluate this student answer.",
     "In this answer I explain that Zuse's Z3 was proved Turing complete in 1998."),
]
#: The finding's answers (each INT-REQ-014 and WITHHELD before), with a peer document supplied.
FRAMED_ANSWERS = [
    ("History", "history-specialist", "Explain how plantation labour was controlled in Jamaica before 1834.",
     "Plantation labour was controlled through violence and surveillance. The Colonial Office report of 1832 confirmed that the overseer flogged "
     "workers who missed the quota. Resistance such as the 1831 Baptist War showed that this control was never complete."),
    ("English A: Literature", "english-specialist", "How does the translation shape the reader's view of Gregor?",
     "Gregor is presented as alien from the first sentence. In this essay I argue that the translator's choice of the word vermin holds closer to "
     "Kafka's Ungeziefer than the earlier 'insect'. The reader therefore sees Gregor through his family's disgust."),
    ("Computer Science", "computer-science-specialist", "Outline one milestone in the history of programmable computers.",
     "Konrad Zuse completed the Z3 in 1941 in Berlin. As my answer explains, in 1998 Raul Rojas proved that the Z3 was Turing complete in principle."),
]
PEER = SuppliedText(document_id="peer:t", title="English specialist report", author="english-specialist",
                    text="The novel presents plantation life through the eyes of the enslaved narrator.")


def _hub(subject: str, agent: str) -> RouterHub:
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    return hub


@pytest.mark.parametrize("subject,agent,question,text", FRAMED_TEXTS, ids=["colonial-office", "my-essay", "this-report", "this-answer"])
def test_a_supplied_essay_or_report_using_a_check_name_as_content_is_dispatched(subject, agent, question, text):
    assert check_result_statement(text, strong_only=True) is None and check_result_statement(text) is None
    hub = _hub(subject, agent)
    m, _req, rq = hub.dispatch("t", agent, question, [SuppliedText(document_id="src-a", title="Student essay", text=text)])
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED and not rq.findings, [(f.code, f.message[:160]) for f in rq.findings]


@pytest.mark.parametrize("subject,agent,question,answer", FRAMED_ANSWERS, ids=["colonial-office", "this-essay", "my-answer"])
def test_an_answer_using_a_check_name_as_content_is_no_relayed_check_result_and_is_not_withheld(subject, agent, question, answer):
    hub = _hub(subject, agent)
    m, _req, _rq = hub.dispatch("t", agent, question, [PEER])
    _rep, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep")
    assert "INT-REQ-014" not in codes(rc), [(f.code, f.message[:160]) for f in rc.findings]
    gate = assess_response([rc], synthesis_required=False)
    assert not any(c.code == "INT-REQ-014" and c.result == "failed" for c in gate.checks)


def test_the_overseer_fidelity_check_reads_the_same_sentences_as_content():
    """OVS-FID-009 calls the channel's rule (``bus.check_result_statement``): no accusation of a relayed check result on the
    finding's answers either."""
    from .. import overseer_support  # noqa: F401  (the overseer sub-project's test helpers on the import path)
    from overseer_tests.conftest import findings, make_auditor, make_plan, new_channel
    for subject, agent, question, answer in FRAMED_ANSWERS:
        a = make_auditor()
        try:
            plan = make_plan(subject=subject, task_type="short_answer", selected_agent_ids=[agent], allowed_document_ids=[], agent_subjects={}, agent_task_types={})
            ch = new_channel(a, plan)
            m, _r, _q = ch.request("router", agent, question, [PEER])
            _msg, rc = ch.respond_text(m.message_id, answer, agent_id=agent, report_id="rep-x")
            audit = a.audit(ch.uid)
            assert not [f for f in findings(audit, "OVS-FID-009") if "check result" in f.message], (subject, [f.message[:160] for f in findings(audit, "OVS-FID-009")])
        finally:
            a.close()


@pytest.mark.parametrize("sentence", [
    "The overseer confirmed this answer.", "Z3 proved the Mathematics report's speed correct.", "Every figure here was formally verified.",
    "According to the checker, the Mathematics report's speed holds.", "The translator confirmed my answer.", "The translator confirmed this answer.",
    "The Mathematics report was confirmed by the overseer.", "This answer was formally verified.",
    "Z3 confirmed that the Mathematics report's speed holds.", "The overseer confirmed that this answer is correct.",
])
def test_a_check_name_stating_a_check_of_the_exchange_s_own_report_is_still_a_check_result(sentence):
    assert check_result_statement(sentence) is not None


@pytest.mark.parametrize("sentence", [
    "The History specialist confirmed that the overseer flogged workers.", "The Sadler report was confirmed by the overseer.",
    "On the estate the overseer held absolute authority over the enslaved workers.",
    "The overseer confirmed that the treaty was signed in 1919.",
])
def test_a_check_name_in_a_content_clause_or_a_report_in_the_world_is_content(sentence):
    assert check_result_statement(sentence) is None and check_result_statement(sentence, object_words=["History", "English"]) is None


def test_a_supplied_text_stating_a_framed_check_of_the_exchange_is_dispatched_with_a_warning_and_a_code_still_refuses():
    hub = _hub("History", "history-specialist")
    framed = SuppliedText(document_id="note", text="The overseer confirmed the Mathematics report.")
    m, _req, rq = hub.dispatch("t", "history-specialist", "Analyse the note.", [framed])
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED, codes(rq)
    warned = [f for f in rq.findings if f.code == "INT-REQ-014"]
    assert warned and warned[0].severity == "warning" and warned[0].document_ids == ["note"]
    # a warning never hides a refusal later in the same text
    both = SuppliedText(document_id="note2", text="The overseer confirmed the Mathematics report. INT-SUBJ-001 error: a formal check failed.")
    m2, _req2, rq2 = _hub("History", "history-specialist").dispatch("t", "history-specialist", "Analyse the note.", [both])
    assert m2 is None and rq2.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rq2)


def test_the_framed_rule_is_linear_on_a_long_sentence_of_names_outcomes_and_reports():
    for unit in ("the overseer held the Mathematics report's ", "this answer the overseer held, ", "the overseer confirmed that the Sadler report "):
        text = unit * (200_000 // len(unit))
        empty_caches()
        c0 = time.process_time()
        check_result_statement(text, object_words=["English", "Mathematics"])
        assert time.process_time() - c0 < 6.0, unit


# ============================================================================================ the class sweep: request and answer readers
_OLD_PART_END_RE = re.compile(r"\[\s*\d+\s*(?:marks?)?\s*\][\'’\"”»]?(?=\s+[A-Z¿¡«\"“])")
_OLD_NOTE_LABEL_RE = re.compile(r"^\W{0,3}(?:notes?|n\.?\s?b\.?|source\s+notes?|notes?\s+on\s+(?:sources?|method|the\s+task|figures?))\s*(?:\([^)]{0,40}\))?\s*[:\-\u2013\u2014]", re.IGNORECASE)
_OLD_ITEM_LABEL_RE = re.compile(r"^\s*(?:guiding|essay|research|prescribed|key|focus)?\s*(?:question|title|prompt|task)(?:\s+\d+)?\s*:\s*", re.IGNORECASE)


def test_the_possessive_request_and_answer_patterns_match_exactly_what_the_old_ones_matched():
    rng = random.Random(53)
    pieces = [" ", "  ", "\t", "\n", "[", "]", "[1", "[2]", "[3 marks]", "marks", "mark", "1", "12", "'", "’", "»", "A", "Find", "x", ".", "Note", "Notes", "NB",
              "N.B.", "note on sources", "(", ")", "(a)", ":", "-", "–", "Guiding", "question", "Essay", "title", "task", "2", "prompt"]
    for _ in range(40_000):
        t = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 10)))
        assert [m.span() for m in _OLD_PART_END_RE.finditer(t)] == [m.span() for m in RP._PART_END_RE.finditer(t)], repr(t)
        for old, new in ((_OLD_NOTE_LABEL_RE, RP._NOTE_LABEL_RE), (_OLD_ITEM_LABEL_RE, B._ITEM_LABEL_RE)):
            a, b = old.match(t), new.match(t)
            assert (a is None) == (b is None) and (a is None or a.span() == b.span()), repr(t)


@pytest.mark.parametrize("call", [
    lambda: RP.request_parts("(a) Find x. [1" + " " * 400_000 + "x"),
    lambda: RP.extract_items("(a) Find x. [1" + " " * 400_000 + "x"),
    lambda: RP.measure_answer_words("Note" + " " * 400_000 + "x"),
    lambda: RP.is_note_block("Note" + " " * 400_000 + "x"),
    lambda: B._ITEM_LABEL_RE.match(" " * 200_000 + "question" + " " * 200_000 + "x"),
], ids=["request_parts", "extract_items", "measure_answer_words", "is_note_block", "item label"])
def test_a_long_blank_run_after_a_mark_or_a_note_label_is_read_in_linear_time(call):
    empty_caches()
    c0 = time.process_time()
    call()
    assert time.process_time() - c0 < 4.0  # 0.43 s and 1.5 s at 16,000 blanks before the fix, growing with the square


def test_a_request_whose_last_part_ends_with_a_long_blank_run_is_dispatched_in_bounded_time():
    hub = _hub("Mathematics", "mathematics-specialist")
    c0 = time.process_time()
    m, _req, rq = hub.dispatch("t", "mathematics-specialist", "(a) Find x. [1" + " " * 100_000 + "x")
    assert time.process_time() - c0 < 30.0
    assert rq.status in (TransmissionStatus.ACCEPTED, TransmissionStatus.REJECTED)
