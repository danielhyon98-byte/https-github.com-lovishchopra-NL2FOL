"""Integration gate 2: the channel's findings (channel/bus.py, channel/request_parser.py).

* critical: a synthesis or report object built around validation could carry None in a field that has a default but is not
  Optional (a synthesized claim's transformation, certainty or materiality, the synthesis's ledger or conflicts, a claim's
  role). The delivered payload is dumped without None, so the recipient read the default while the ledger ran on the
  caller's None: a rule skipped silently (transformation), or the whole ledger lost behind an INT-INTERNAL-001 error. The
  relay and the response now validate the object's full dump too (None kept), refuse such an object with INT-REQ-009 (and
  INT-SYNTH-014 for a value outside a closed vocabulary), and run every check on the object read back from the delivered
  payload.
* majors: the strong 'check result of this exchange' rule read ordinary subject content as a relayed check result: "the
  overseer" (plantation overseers), "the translator" (literature in translation), "the checker", "Z3" (Konrad Zuse's 1941
  computer), "formally confirmed" / "formally proved" (treaties, theorems). Requests carrying such a question or text were
  REJECTED (INT-REQ-009) and answers carrying such a sentence were INT-REQ-014 and WITHHELD by the gate. Those names now
  state a check result only in the exchange's own frame (a report or answer of the exchange, or the agent's own text, named
  in the sentence), and the student's question is read for finding codes and receipt statuses only.
* critical (handed over by the parsers fixer, owner's sweep): two request-parser patterns backtracked over blank runs
  (``_LABEL_LINE_RE``: cubic, 9 s at 2,000 blanks; ``_PART_LABEL_RE``: quadratic). Their blank runs are possessive now, and
  the patterns match exactly what the old ones matched (the old patterns are kept below as the specification).
* the class sweep: ``_clause_of`` stripped a closing "begins"/"ends" with a pattern that rescanned a blank run from every
  position (quadratic); it is read backwards once now.

The sweep tests at the end feed each module's public text entry points the standard hostile inputs (``tests/core_hostile.py``).
"""
from __future__ import annotations

import random
import re
import time
from typing import Any

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel import bus as B
from epinoic_logic.channel import request_parser as RP
from epinoic_logic.channel.bus import check_result_statement
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, WorkPlan
from epinoic_logic.translate.contracts import SuppliedText, sha256_text

from ..core_hostile import HOSTILE, inputs, sweep

KEY = b"gate2-channel-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000)
COMBINATOR = "dummy-combinator"
TEXT = ("London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
        "Coal smoke from homes and workshops hung over the city for much of the year.")


def codes(receipt) -> list[str]:
    return sorted({f.code for f in receipt.findings})


# ============================================================================================ critical: None in a defaulted field
def _channel() -> tuple[TranslatorChannel, list]:
    plan = WorkPlan(plan_id="plan-n", request_id="req-n", task_id="task-n", subject="History", task_type="short_answer",
                    selected_agent_ids=["history-specialist", COMBINATOR])
    ch = TranslatorChannel(plan, signing_key=KEY)
    request_msg, _req, rr = ch.request("router", "history-specialist", "Outline the context of London in 1802 in one paragraph.")
    assert rr.status is TransmissionStatus.ACCEPTED
    msg, rc = ch.respond_text(request_msg.message_id, TEXT, agent_id="history-specialist", report_id="rep-n")
    assert msg is not None, rc.summary
    return ch, list(ch.transmitted_reports["rep-n"].claims)


def _synthesis(claims) -> Synthesis:
    sc = [{"claim_id": f"s{i}", "text": c.claim_text, "source_claim_ids": [c.claim_id], "transformation": "carried"} for i, c in enumerate(claims)]
    text = " ".join(c["text"] for c in sc)
    return Synthesis.model_validate({"synthesis_id": "syn-n", "request_id": "req-n", "task_id": "task-n", "combinator_agent_id": COMBINATOR,
                                     "source_report_ids": ["rep-n"], "claims": sc, "text": text, "text_sha256": sha256_text(text),
                                     "created_at": "2026-10-31T15:00:00Z"})


def _relay(ch: TranslatorChannel, payload):
    return ch.relay(COMBINATOR, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)


@pytest.mark.parametrize("field,vocabulary", [("transformation", True), ("certainty", True), ("materiality", True),
                                              ("source_claim_ids", False), ("evidence_refs", False)])
def test_a_synthesized_claim_with_none_in_a_defaulted_field_is_refused_not_delivered(field, vocabulary):
    ch, claims = _channel()
    syn = _synthesis(claims)
    bad = syn.claims[0].model_copy(update={field: None})
    relayed, rc = _relay(ch, syn.model_copy(update={"claims": [bad, *syn.claims[1:]]}))
    assert relayed is None and rc.status is TransmissionStatus.REJECTED, (rc.status, codes(rc))
    assert "INT-REQ-009" in codes(rc) and ("INT-SYNTH-014" in codes(rc)) == vocabulary, codes(rc)
    assert "INT-INTERNAL-001" not in codes(rc) and not ch.syntheses


@pytest.mark.parametrize("field", ["ledger", "conflicts", "claims"])
def test_a_synthesis_with_none_in_a_defaulted_list_is_refused_not_delivered(field):
    ch, claims = _channel()
    relayed, rc = _relay(ch, _synthesis(claims).model_copy(update={field: None}))
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)
    assert "INT-INTERNAL-001" not in codes(rc) and not ch.syntheses


def test_a_dropped_hedge_under_transformation_none_is_refused_and_under_carried_is_named():
    """The finding's case: transformation=None with an edited text skipped INT-LEDGER-010 silently, and the router read
    'carried'. Now it is refused; the same edit labelled 'carried' is delivered with INT-LEDGER-010."""
    ch, claims = _channel()
    syn = _synthesis(claims)
    edited = syn.claims[0].text.replace("close to a million", "a million")
    for value, refused in ((None, True), ("carried", False)):
        ch2, _c = _channel()
        bad = syn.claims[0].model_copy(update={"transformation": value, "text": edited})
        text = " ".join([edited, *(c.text for c in syn.claims[1:])])
        relayed, rc = _relay(ch2, syn.model_copy(update={"claims": [bad, *syn.claims[1:]], "text": text, "text_sha256": sha256_text(text)}))
        assert (relayed is None) == refused, (value, codes(rc))
        if not refused:
            assert "INT-LEDGER-010" in codes(rc), codes(rc)


def test_a_valid_synthesis_object_is_delivered_and_checked_as_delivered():
    ch, claims = _channel()
    syn = _synthesis(claims)
    relayed, rc = _relay(ch, syn)
    assert relayed is not None and rc.status is not TransmissionStatus.REJECTED, codes(rc)
    assert Synthesis.model_validate(relayed.payload) == syn and ch.syntheses["syn-n"] == syn


@pytest.mark.parametrize("field", ["claim_role", "materiality", "certainty", "proposed_claim_kind", "source_refs", "assumptions"])
def test_a_report_relay_with_none_in_a_claim_s_defaulted_field_is_refused(field):
    ch, _claims = _channel()
    rep = ch.transmitted_reports["rep-n"]
    bad = rep.model_copy(update={"claims": [rep.claims[0].model_copy(update={field: None}), *rep.claims[1:]]})
    relayed, rc = ch.relay("history-specialist", AgentRole.SPECIALIST, COMBINATOR, AgentRole.COMBINATOR, bad)
    assert relayed is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)
    # control: the report as delivered is handed on
    again, rc2 = ch.relay("history-specialist", AgentRole.SPECIALIST, COMBINATOR, AgentRole.COMBINATOR, rep)
    assert again is not None, codes(rc2)


def test_a_response_with_none_in_a_defaulted_field_is_refused():
    plan = WorkPlan(plan_id="plan-r", request_id="req-n", task_id="task-n", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"])
    ch = TranslatorChannel(plan, signing_key=KEY)
    msg, _req, _rr = ch.request("router", "history-specialist", "Outline the context of London in 1802 in one paragraph.")
    good_ch, _c = _channel()
    rep = good_ch.transmitted_reports["rep-n"]
    for bad in (rep.model_copy(update={"assumptions": None}), rep.model_copy(update={"claims": [rep.claims[0].model_copy(update={"claim_role": None}), *rep.claims[1:]]})):
        delivered, rc = ch.respond(msg.message_id, bad)
        assert delivered is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc), codes(rc)


# ============================================================================================ majors: ordinary content is no check result
CONTENT = [
    "On the estate the overseer held absolute authority over the enslaved workers.",
    "The treaty was formally confirmed by the Allied powers in January 1920.",
    "Konrad Zuse completed the Z3 in 1941. In 1998 it was proved that the Z3 was Turing complete.",
    "The translator's choice of vermin held closer to Kafka's Ungeziefer than earlier versions.",
    "This result was formally proved in Euclid's Elements.",
    "The seL4 microkernel was formally verified in 2009.",
]
QUESTIONS = [
    "Why was the role of the overseer held to be so important on sugar plantations?",
    "Explain how the overseer's authority on the plantation passed to the planters after 1865.",
    "To what extent did the overseer verify the enslaved workers' output on cotton plantations?",
    "Discuss how the translator's choices held the tone of the original poem.",
    "How did the checker confirm that the ballots were counted correctly in the 1876 election?",
]
PEER = SuppliedText(document_id="peer:t", title="English specialist report", author="english-specialist",
                    text="The novel presents plantation life through the eyes of the enslaved narrator.")


def _hub(subject: str = "History", agent: str = "history-specialist"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    return hub


@pytest.mark.parametrize("sentence", CONTENT)
def test_ordinary_content_naming_a_check_word_is_no_check_result(sentence):
    """The rule the channel's request scan, INT-REQ-014 and the Overseer's fidelity check (which calls this function) read."""
    assert check_result_statement(sentence) is None
    assert check_result_statement(sentence, strong_only=True) is None
    assert check_result_statement(sentence, object_words=["English", "specialist", "report"]) is None


@pytest.mark.parametrize("sentence", CONTENT + ["Translator's note: the translator's rendering of the final stanza was confirmed by the poet in 1921."])
def test_a_supplied_text_of_ordinary_content_is_dispatched(sentence):
    hub = _hub()
    m, _req, rq = hub.dispatch("t", "history-specialist", "Analyse the source in one paragraph.", [SuppliedText(document_id="src", title="Source A", text=sentence)])
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED, [(f.code, f.message[:160]) for f in rq.findings]


@pytest.mark.parametrize("question", QUESTIONS)
def test_a_student_question_using_check_words_is_dispatched(question):
    hub = _hub()
    m, _req, rq = hub.dispatch("t", "history-specialist", question)
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED, [(f.code, f.message[:160]) for f in rq.findings]


@pytest.mark.parametrize("question", ["Explain INT-SUBJ-001 and why the check failed.", "The hub receipt says the answer was ACCEPTED_WITH_FINDINGS; explain why it failed."])
def test_a_request_text_carrying_a_finding_code_or_a_receipt_status_is_still_refused(question):
    hub = _hub()
    m, _req, rq = hub.dispatch("t", "history-specialist", question)
    assert m is None and rq.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rq)


@pytest.mark.parametrize("subject,agent,question,answer", [
    ("History", "history-specialist", "Explain how plantation labour was controlled in Jamaica before 1834.",
     "Plantation labour was controlled through violence and surveillance. On each estate the overseer held absolute authority over the "
     "enslaved workers, and the Slave Codes of 1696 gave planters legal backing."),
    ("Computer Science", "computer-science-specialist", "Outline one milestone in the history of programmable computers.",
     "Konrad Zuse completed the Z3 in 1941 in Berlin. It was the first working programmable, fully automatic digital computer. In 1998 "
     "Raul Rojas proved that the Z3 was Turing complete in principle."),
])
def test_an_answer_of_ordinary_content_is_no_relayed_check_result_and_is_not_withheld_for_it(subject, agent, question, answer):
    hub = _hub(subject, agent)
    m, _req, rq = hub.dispatch("t", agent, question, [PEER])
    assert m is not None, codes(rq)
    _rep, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep")
    assert "INT-REQ-014" not in codes(rc), [(f.code, f.message[:160]) for f in rc.findings]
    gate = assess_response([rc], synthesis_required=False)
    assert not any(c.code == "INT-REQ-014" for c in gate.checks)


@pytest.mark.parametrize("sentence", [
    "The overseer confirmed this answer.", "Z3 proved the Mathematics report's speed correct.", "Every figure here was formally verified.",
    "According to the checker, the Mathematics report's speed holds.", "The translator confirmed my answer.",
])
def test_a_check_word_in_the_exchange_s_frame_is_still_a_check_result(sentence):
    assert check_result_statement(sentence) is not None


# ============================================================================================ critical: request-parser blank runs
#: The patterns before the fix, kept as the specification the possessive ones must match exactly.
OLD_LABEL_LINE_RE = re.compile(r"^\s*(?:\(?[a-z]{1,4}\)|\d{1,2}[.)]|part\s+\(?[a-z0-9]{1,4}\)?)?\s*(?:\[\s*\d+(?:\s+(?:marks?|spare))?\s*\])?\s*$|^\s*\d{4}(?:\s*\([^)]{0,30}\))?\s*$", re.IGNORECASE)
OLD_PART_LABEL_RE = re.compile(r"(?:^|(?<=\n)|(?<=[.?!:;\]»\"'”’)])\s+|(?<=[.?!:;\]»\"'”’])(?=\())[ \t]*(?P<label>\((?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|(?:[a-hA-H]|i{1,3}|iv|vi{0,3}|ix|x)\)|\d{1,2}[.)])(?=\s)")


def test_the_possessive_label_patterns_match_exactly_what_the_old_ones_matched():
    rng = random.Random(41)
    pieces = [" ", "  ", "\t", "\n", "\r", " ", "(a)", "a)", "(ii)", "1.", "2)", "part", " (b)", "[2]", "[3 marks]", "[1 spare]", "2024", "(no tax)",
              ".", "?", "]", "”", "x", "Find", "5", "marks", "spare", ")", "("]
    for _ in range(60000):
        line = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 9)))
        old, new = OLD_LABEL_LINE_RE.match(line), RP._LABEL_LINE_RE.match(line)
        assert (old is None) == (new is None) and (old is None or old.span() == new.span()), repr(line)
        assert [(m.span(), m.span("label")) for m in OLD_PART_LABEL_RE.finditer(line)] == [(m.span(), m.span("label")) for m in RP._PART_LABEL_RE.finditer(line)], repr(line)


def test_a_line_of_blanks_under_a_request_that_exempts_working_is_counted_in_linear_time():
    answer = "Output fell because demand fell after 1990.\n" + " " * 100_000 + "x"
    c0 = time.process_time()
    words = RP.measure_answer_words(answer, excludes=("working",))
    assert time.process_time() - c0 < 4.0  # the finding's 2 KB answer took 17.6 s; 2,000 blanks took 9.2 s in the pattern alone
    assert words[0] == RP.count_words("Output fell because demand fell after 1990. x")


def test_an_answer_with_a_line_of_blanks_crosses_the_hub_under_a_bound_that_exempts_working():
    """The finding's path: the hub measures the word bound of a request that exempts working over every answer line, and a
    2 KB answer with one line of blanks took 17.6 s before the fix."""
    hub = _hub("Economics", "economics-specialist")
    m, _req, rq = hub.dispatch("t", "economics-specialist", "Explain why output fell after 1990. Write no more than 300 words plus working.")
    assert m is not None, codes(rq)
    c0 = time.process_time()
    _rep, rc = hub.receive("t", m.message_id, "Output fell because demand fell after 1990.\n" + " " * 100_000 + "x",
                           agent_id="economics-specialist", report_id="rep")
    assert time.process_time() - c0 < 30.0
    assert rc.status is not TransmissionStatus.REJECTED or "INT-REQ-009" in codes(rc), codes(rc)


@pytest.mark.parametrize("run", [" " * 100_000, "\t" * 100_000, "\n" * 100_000])
def test_a_blank_run_after_a_sentence_end_is_read_for_part_labels_in_linear_time(run):
    request = "The value is 5 m. " + run + "It is 6 m. (a) Find the speed. [2]"
    c0 = time.process_time()
    parts, items = RP.request_parts(request), RP.extract_items(request)
    assert time.process_time() - c0 < 4.0  # 3.54 s for request_parts at 8,000 blanks before the fix
    assert parts == RP.request_parts("The value is 5 m. It is 6 m. (a) Find the speed. [2]") or len(parts) == len(RP.request_parts("The value is 5 m. It is 6 m. (a) Find the speed. [2]"))
    assert items


# ============================================================================================ the class sweep: a closing period word
def test_the_period_edge_is_stripped_exactly_as_the_pattern_stripped_it_in_linear_time():
    rng = random.Random(43)
    pieces = [" ", "\n", "\t", "ends", "begins", "x", "s", "end", "1923", " "]
    for _ in range(40000):
        a = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 8)))
        assert B._PERIOD_EDGE_RE.sub("", a) == B._without_period_edge(a), repr(a)
    c0 = time.process_time()
    assert B._clause_of("In 1990 the total was 5 people.", [" " * 80_000 + "x"], None) is None
    assert time.process_time() - c0 < 4.0  # 31 s at 80,000 blanks before the fix


# ============================================================================================ the sweep, one test per module
def _request_parser_entries(text: str):
    yield "extract_items", lambda: RP.extract_items(text)
    yield "extract_constraints", lambda: RP.extract_constraints(text)
    yield "request_parts", lambda: RP.request_parts(text)
    yield "count_words", lambda: RP.count_words(text)
    yield "count_answer_words", lambda: RP.count_answer_words(text)
    yield "measure_answer_words", lambda: RP.measure_answer_words(text)
    yield "measure_answer_words(working, diagram)", lambda: RP.measure_answer_words(text, excludes=("working", "diagram"))
    yield "is_note_block", lambda: RP.is_note_block(text)


def test_sweep_request_parser():
    assert not sweep(_request_parser_entries)


def _bus_entries(text: str):
    yield "check_result_statement", lambda: check_result_statement(text, object_words=["English", "report"])
    yield "check_result_statement(strong)", lambda: check_result_statement(text, strong_only=True)
    yield "check_result_statement(codes)", lambda: check_result_statement(text, codes_only=True)
    yield "_clause_of(text)", lambda: B._clause_of(text, ["5 people", "1990"], "5")
    yield "_clause_of(anchor)", lambda: B._clause_of("In 1990 the total was 5 people.", [text], "5")
    yield "_find_figure", lambda: B._find_figure(text, "1990", 0)


def test_sweep_bus_readers():
    assert not sweep(_bus_entries)


def _channel_entries(text: str):
    """The channel's own entry points on hostile text: the request (the student's question, a supplied text) and a
    synthesis relayed with a hostile student-facing text."""
    def request_question():
        hub = _hub()
        hub.dispatch("t", "history-specialist", text)

    def request_supplied():
        hub = _hub()
        hub.dispatch("t", "history-specialist", "Analyse the source.", [SuppliedText(document_id="src", text=text)])

    def relay_synthesis():
        ch, claims = _channel()
        syn = _synthesis(claims)
        body = syn.text + " " + text
        _relay(ch, syn.model_copy(update={"text": body, "text_sha256": sha256_text(body)}))

    yield "dispatch(question)", request_question
    yield "dispatch(supplied text)", request_supplied
    yield "relay(synthesis text)", relay_synthesis


def test_sweep_channel_entry_points():
    assert not sweep(_channel_entries, bound=20.0, texts=dict(HOSTILE))


def _answer_entries(text: str):
    def receive():
        hub = _hub()
        m, _req, _rq = hub.dispatch("t", "history-specialist", "Explain the causes of the 1929 crash in one paragraph.")
        hub.receive("t", m.message_id, "The crash followed speculation on margin. " + text, agent_id="history-specialist", report_id="rep")
    yield "receive(History answer)", receive


def test_sweep_channel_response():
    """A History answer carrying each hostile run crosses the channel (parse, packs, ledger, checks) in bounded time."""
    assert not sweep(_answer_entries, bound=30.0, texts=dict(HOSTILE))
