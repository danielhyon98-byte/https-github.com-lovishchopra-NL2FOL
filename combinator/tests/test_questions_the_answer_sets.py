"""A question the answer sets the student is content of the answer, never a note (round 10, integrated round c3).

The round's ll-t16 synthesis carried the English A: Language and Literature specialist's "To test a direction, answer
these from the adverts themselves: 1. Your notes say the camera ..." and dropped the four questions that sentence
announces (p4-s02 "What does that choice do to who counts as part of the family?", p4-s04, p4-s06 and p4-s07 "4. Does one
question work across all three adverts, or only two?") as "a question or practice prompt to the student, a note rather
than a claim of the answer", so the student was told to answer questions the synthesis does not hold. The instructions
(pack 1.3, rule 6) listed "a question to the student or the router" among the notes to leave out, whatever the question
did, and the round's agent followed them. Pack 1.4 splits the rule: a question that asks the student or the router
something back (what they mean, which text they use, whether they want more) stays a note; a question the answer sets
the student (a practice, test, revision or guiding question) is content, kept like any other claim, and a kept sentence
that announces questions, a list or steps keeps every question, item and step it announces (one the delivery roled
``other`` stays a note, as the hub reads it).

Shown here, on the round's recorded material (``data/round10_ll_t16.json``, copied verbatim):

* the defect as recorded;
* rule 6 names a question back as a note and a question the answer sets as content, with the round's own sentences as
  its examples; rule 9 forbids dropping a question the answer sets as a note or anything a kept sentence announces; the
  output format says the same; the pack is 1.4;
* the faithful fake (the deterministic stand-in for an agent that follows the instructions) carries the four recorded
  questions word for word and still drops every note, a question back included;
* the runner lets out the synthesis rule 6 asks for and, judging no faithfulness, the recorded one too;
* inside the translator repository, through the hub, with the recorded response delivered through the channel: a
  synthesis that drops the questions as notes, as the round's agent did, is named (INT-LEDGER-019 on each question; the
  delivery reads them as material claims since the round-10 clearance), and the faithful fake's synthesis, which keeps
  them, is accepted with no finding; the fake reads withheld work as the channel does on the round's material, the
  decline "I can't choose your line of inquiry, and I can't write your introduction, ..." included (the fake's reading
  missed that form, which the hub reads as a decline since the same clearance, so the fake dropped it: INT-LEDGER-019);
* the hub's claim ledger on the round's delivery as recorded (the questions roled interpretation, supporting): with the
  questions kept it names nothing on them; with them dropped, as recorded, rule framing-content names each one (announced
  items: the carried sentence announces questions the synthesis no longer holds; landed on the translator's side in the
  round-10 clearance's handoff pass, which removed the strict xfail that pinned it as open).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from combinator_helpers import claim, input_doc, text
from epinoic_combinator import runner as R
from epinoic_combinator.contract import load_contract
from epinoic_combinator.pack import load_pack
from epinoic_combinator.providers import NOTE_REASON, FaithfulFakeProvider, ScriptedProvider, withheld_work

DATA = json.loads((Path(__file__).resolve().parent / "data" / "round10_ll_t16.json").read_text(encoding="utf-8"))
CONTRACT = load_contract()
PACK = load_pack()
INSTRUCTIONS = PACK.instructions
FORMAT = PACK.output_format
BY_ID = {c["claim_id"]: c for c in DATA["claims"]}
#: The four questions of the recorded answer's numbered list, as the round's hub delivered them, and the sentence that
#: announces them (carried by the recorded synthesis).
QUESTIONS = ("p4-s02", "p4-s04", "p4-s06", "p4-s07")
QUESTION_TEXTS = tuple(BY_ID[q]["text"] for q in QUESTIONS)
LEAD = "p4-point"
#: The reason the round's agent gave for each question it dropped.
RECORDED_REASON = "a question or practice prompt to the student, a note rather than a claim of the answer"
#: The recorded decline of the requested essay (rule 7), roled ``thesis`` by the round's delivery.
DECLINE = "p1-s01"
#: A second answer to the same request (the port takes two sources at least), written for this test, not recorded: a
#: duplicated instance of the specialist that states one claim and asks the student something back. The combinator-only
#: input roles that question ``other``: a question back is a note (rule 6).
SECOND_AGENT = "english-a-lang-lit-specialist-b"
SECOND_CONTENT = "Your notes already point to a line about who counts as family in the campaign."
QUESTION_BACK = "Would you like me to say more about the slogan?"
FIRST = {"report_id": "rep-ll-t16", "agent_id": DATA["agent_id"], "subject": DATA["subject"], "branch": "english",
         "claims": [claim(c["claim_id"], c["text"], role=c["role"], materiality=c["materiality"], certainty=c["certainty"]) for c in DATA["claims"]]}
SECOND = {"report_id": "rep-ll-t16-b", "agent_id": SECOND_AGENT, "subject": DATA["subject"], "branch": "english",
          "claims": [claim(f"p1-point@{SECOND_AGENT}", SECOND_CONTENT, role="point", certainty="probable"),
                     claim(f"p2-point@{SECOND_AGENT}", QUESTION_BACK, role="other", materiality="supporting", certainty="possible")]}
INPUT = input_doc(sources=[FIRST, SECOND])


def _rule(n: int) -> str:
    """Rule ``n`` of the instructions, its whitespace folded."""
    m = re.search(rf"^{n}\. \*\*.+?(?=^\d+\. \*\*|^## |\Z)", INSTRUCTIONS, re.M | re.S)
    assert m is not None, n
    return " ".join(m.group(0).split())


def _recorded_agent_output(*, keep_questions: bool) -> dict:
    """The round's recorded synthesis as the agent's output for :data:`INPUT` (the second answer's claim carried, its question
    back dropped), keeping the four questions as rule 6 asks when ``keep_questions``."""
    agent = copy.deepcopy(DATA["synthesis"])
    agent["claims"].append({"text": SECOND_CONTENT, "source_claim_ids": [f"p1-point@{SECOND_AGENT}"], "certainty": "probable", "transformation": "carried"})
    agent["dropped"].append({"source_claim_ids": [f"p2-point@{SECOND_AGENT}"], "reason": "a question back to the student, a note rather than a claim of the answer"})
    if keep_questions:
        agent["dropped"] = [d for d in agent["dropped"] if not set(d["source_claim_ids"]) & set(QUESTIONS)]
        at = next(i for i, c in enumerate(agent["claims"]) if LEAD in c["source_claim_ids"]) + 1
        for q in QUESTIONS:
            agent["claims"].insert(at, {"text": BY_ID[q]["text"], "source_claim_ids": [q], "certainty": BY_ID[q]["certainty"], "transformation": "carried"})
            at += 1
    return agent


# ----------------------------------------------------------------------------------------------- the recorded defect


def test_the_recorded_synthesis_carried_the_announcing_sentence_and_dropped_its_questions_as_notes():
    syn = DATA["synthesis"]
    cited = {cid for c in syn["claims"] for cid in c["source_claim_ids"]}
    assert LEAD in cited and BY_ID[LEAD]["text"].startswith("To test a direction, answer these from the adverts themselves:")
    assert all(t.rstrip().endswith("?") for t in QUESTION_TEXTS), QUESTION_TEXTS
    assert not set(QUESTIONS) & cited
    for q in QUESTIONS:
        [entry] = [d for d in syn["dropped"] if q in d["source_claim_ids"]]
        assert entry["reason"] == RECORDED_REASON
        assert BY_ID[q]["role"] != "other", "the round's delivery roled each question as a claim of the answer, not as a note"


# ----------------------------------------------------------------------------------------------- the instructions


def test_the_pack_is_1_4():
    assert PACK.version == "1.4" and FORMAT["instruction_pack"]["version"] == "1.4"
    assert INSTRUCTIONS.splitlines()[0] == "# Combinator instructions (instruction pack `combinator-instructions` 1.4)"


def test_rule_6_keeps_a_question_back_among_the_notes():
    notes, sep, _rest = _rule(6).partition("Leave them out and list them in `dropped`.")
    assert sep
    for phrase in ("a question to the student or the router that asks something back",
                   "(what they mean, which text or edition they use, whether they want more:",
                   '"Which edition are you using?"', '"Would you like me to say more about the reparations?"'):
        assert phrase in notes, phrase
    # pack 1.3 read every question to the student as a note, whatever it did
    assert "a question to the student or the router, a word count" not in notes
    assert "sets the student" not in notes and "practice" not in notes, "a question the answer sets is no note"


def test_rule_6_makes_a_question_the_answer_sets_content():
    _notes, _sep, rest = _rule(6).partition("Leave them out and list them in `dropped`.")
    for phrase in ("A question the answer sets the student is not a note:",
                   "a practice, test, revision or guiding question that the student is told to answer or think through",
                   'often numbered or announced by a sentence such as "answer these:" or "ask yourself", is content of the answer',
                   "Keep it like any other claim of the answer, by rules 1 to 5, and never list it in `dropped` as a note or as a question "
                   "to the student.",
                   "When you keep a sentence that announces questions, a list or steps",
                   "keep every question, item and step it announces as well, unless its `role` is `other`."):
        assert phrase in rest, phrase
    # the one exception to the role rule is still rule 7's: a question the answer sets that the delivery roled 'other' stays a note
    assert ("A source claim whose `role` is `other` is a note: never cite one in `claims`, whatever you write. The one exception is a "
            "decline or a deferral of the work the student asked for") in rest


def test_rule_6_gives_the_rounds_own_sentences_as_examples():
    """The examples of a question the answer sets are the recorded answer's: the sentence that announces them and two of the
    questions the round's agent dropped."""
    examples = re.findall(r"\"([^\"]+)\"", _rule(6).split("A question the answer sets the student is not a note")[1].split("Keep it like")[0])
    assert examples[2:] == ["To test a direction, answer these from the adverts themselves:", BY_ID["p4-s04"]["text"], BY_ID["p4-s07"]["text"]], examples
    assert BY_ID[LEAD]["text"].startswith(examples[2])
    assert examples[:2] == ["answer these:", "ask yourself"]


def test_rule_9_forbids_dropping_a_question_the_answer_sets_or_what_a_kept_sentence_announces():
    rule9 = _rule(9)
    assert ("Never drop a question the answer sets the student as a note, and never drop a question, item or step that a sentence you "
            "keep announces, unless its `role` is `other` (rule 6).") in rule9
    assert "Never drop a decline or a deferral (rule 7)." in rule9


def test_the_output_format_states_the_split():
    rules = FORMAT["rules"]
    [note_rule] = [r for r in rules if r.startswith("never carry a note")]
    for phrase in ("a question that asks the student or the router something back (what they mean, which text they use, whether they "
                   "want more) back as a claim: list it in dropped",
                   "a question the answer sets the student (a practice, test, revision or guiding question the student is told to answer or "
                   "think through, often numbered or announced by 'answer these:') is content, not a note: keep it like any other claim and "
                   "never list it in dropped as a note",
                   "when you keep a sentence that announces questions, a list or steps, keep every question, item and step it announces "
                   "unless its role is 'other' (a material claim left out is named, INT-LEDGER-019)"):
        assert phrase in note_rule, phrase
    assert "never a question the answer sets the student (it is content)" in FORMAT["output"]["dropped"]
    [drop_rule] = [r for r in rules if r.startswith("list every source claim left out in dropped")]
    assert "or a question the answer sets the student (it is content)" in drop_rule


# ----------------------------------------------------------------------------------------------- the faithful fake


def test_the_faithful_fake_carries_the_questions_the_answer_sets_and_drops_every_note():
    result = R.run(INPUT, FaithfulFakeProvider())
    assert result.ok and CONTRACT.check_output(result.output, INPUT) is None, result.refusal
    out = result.output
    by_source = {c["source_claim_ids"][0]: c for c in out["claims"]}
    assert all(len(c["source_claim_ids"]) == 1 and c["transformation"] == "carried" for c in out["claims"])
    for q in (LEAD, *QUESTIONS):
        assert (by_source[q]["text"], by_source[q]["certainty"]) == (BY_ID[q]["text"], BY_ID[q]["certainty"]), q
    dropped = {cid for d in out["dropped"] for cid in d["source_claim_ids"]}
    notes = {c["claim_id"] for c in DATA["claims"] if c["role"] == "other"} | {f"p2-point@{SECOND_AGENT}"}
    assert dropped == notes and all(d["reason"] == NOTE_REASON for d in out["dropped"]), "every note, the question back included, is left out"
    # the fake reads a note by its role only: beside the four questions it also keeps p8-point, the Sources line the round's
    # delivery roled a material point and the round's agent dropped as a note (the hub named that drop, INT-LEDGER-019)
    recorded = {cid for c in DATA["synthesis"]["claims"] for cid in c["source_claim_ids"]}
    assert {cid for cid in by_source if "@" not in cid} == recorded | set(QUESTIONS) | {"p8-point"}


@pytest.mark.parametrize("keep_questions", [True, False], ids=["the questions kept (rule 6)", "the questions dropped (as recorded)"])
def test_the_runner_lets_either_synthesis_out_and_judges_no_faithfulness(keep_questions):
    agent = _recorded_agent_output(keep_questions=keep_questions)
    result = R.run(INPUT, ScriptedProvider(text(agent)))
    assert result.ok and CONTRACT.check_output(result.output, INPUT) is None, result.refusal
    cited = {cid for c in result.output["claims"] for cid in c["source_claim_ids"]}
    assert set(QUESTIONS) & cited == (set(QUESTIONS) if keep_questions else set())


# ----------------------------------------------------------------------------------------------- through the hub


KEY = b"combinator-set-questions-key-0123456789"
#: The second answer delivered through the hub: its one claim (the English parser roles a closing question back to the
#: student as a point, so the question back is shown on the combinator-only input above, not here).
HUB_SECOND = SECOND_CONTENT


def _deliver(kit):
    """The recorded response, with its supplied text, and the second answer delivered through the translator's channel; the
    port's input, the delivered reports and the ids the delivery gives the four recorded questions (found by their text)."""
    from epinoic_logic.channel import TranslatorChannel
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.integrity import WorkPlan
    from epinoic_logic.translate.contracts import SuppliedText
    agents = {DATA["agent_id"]: DATA["response_text"], SECOND_AGENT: HUB_SECOND}
    plan = WorkPlan(plan_id="plan-ll-t16", request_id="req-ll-t16", task_id="task-ll-t16", subject=DATA["subject"], task_type=DATA["task_type"],
                    selected_agent_ids=[*agents, "synthesis"])
    ch = TranslatorChannel(plan, signing_key=KEY, config=SolverConfig(timeout_ms=3000, memory_max_mb=None))
    supplied = [SuppliedText(**t) for t in DATA["supplied_texts"]]
    for agent, response in agents.items():
        m, _req, _rr = ch.request("router", agent, DATA["question"], supplied_texts=supplied)
        reply, rc = ch.respond_text(m.message_id, response, agent_id=agent, report_id=f"rep-{agent}")
        assert reply is not None, rc.summary
    reports = list(ch.transmitted_reports.values())
    sources = [kit.source_report(r.model_dump(mode="json"), "english") for r in reports]
    inp = kit.build_input({"task_id": "task-ll-t16", "request_id": "req-ll-t16"}, sources, PACK.identity())
    questions = [c.claim_id for c in reports[0].claims if c.claim_text in QUESTION_TEXTS]
    assert len(questions) == 4, ("the delivery holds each recorded question as a claim of its own", [(c.claim_id, c.claim_text[:60]) for c in reports[0].claims])
    return ch, inp, reports, questions


def _relay(kit, ch, inp, provider, sid: str):
    """Through the combinator's runner, the port and the hub, as the service relays a synthesis."""
    from epinoic_logic.integration.canonical import canonical_json
    from epinoic_logic.integration.protocol import dump
    from epinoic_logic.integrity import AgentRole
    result = R.run(canonical_json(dump(inp)), provider)
    assert result.ok, result.refusal
    out = kit.check_output(result.text, inp)
    payload = kit.synthesis_payload(out, inp, synthesis_id=sid, combinator_agent_id="synthesis", created_at="2026-11-15T10:00:00Z")
    relayed, receipt = ch.relay("synthesis", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)
    assert relayed is not None, receipt.summary
    index = {cid: f"s{i}" for i, c in enumerate(out.claims) for cid in c.source_claim_ids}
    return receipt, index


def _as_the_round_did(reports, questions) -> dict:
    """What the round's agent did, on the delivery: every claim of the answer carried word for word, the decline carried as rule
    7 asks, every other note left out, and the four questions left out as notes with the recorded reason."""
    from epinoic_logic.channel.bus import withheld_deliverable
    agent: dict = {"claims": [], "dropped": []}
    for r in reports:
        for c in r.claims:
            if c.claim_id in questions:
                agent["dropped"].append({"source_claim_ids": [c.claim_id], "reason": RECORDED_REASON})
            elif c.claim_role == "other" and withheld_deliverable(c.claim_text) is None:
                agent["dropped"].append({"source_claim_ids": [c.claim_id], "reason": "a note of the specialist, not a claim of the answer"})
            else:
                agent["claims"].append({"text": c.claim_text, "source_claim_ids": [c.claim_id], "certainty": c.certainty, "transformation": "carried"})
    return agent


def test_through_the_hub_a_synthesis_that_drops_the_questions_as_notes_is_named(kit):
    ch, inp, reports, questions = _deliver(kit)
    receipt, _index = _relay(kit, ch, inp, ScriptedProvider(text(_as_the_round_did(reports, questions))), "syn-ll-t16-as-recorded")
    for q in questions:
        named = [f for f in receipt.findings if f.code == "INT-LEDGER-019" and q in f.claim_ids]
        assert named and named[0].severity == "warning" and RECORDED_REASON in named[0].message, \
            (q, [(f.code, f.claim_ids[:3], f.message[:160]) for f in receipt.findings])


def test_through_the_hub_the_synthesis_rule_6_asks_for_is_accepted_with_no_finding(kit):
    """The faithful fake keeps the four questions (and carries the decline the delivery roles 'other', as rule 7 asks): the hub
    accepts its synthesis and names nothing, so keeping a question the answer sets is never a note carried back as a claim."""
    from epinoic_logic.channel import TransmissionStatus
    ch, inp, reports, questions = _deliver(kit)
    receipt, index = _relay(kit, ch, inp, FaithfulFakeProvider(), "syn-ll-t16-faithful-fake")
    assert set(questions) <= set(index)
    assert receipt.status == TransmissionStatus.ACCEPTED and not receipt.findings, [(f.code, f.claim_ids[:3], f.message[:160]) for f in receipt.findings]


def test_through_the_hub_the_fake_carries_the_rounds_decline_as_the_channel_reads_it(kit):
    """The fake reads withheld work as the channel does on the round's material: the response, every paragraph and sentence of it,
    and every claim, recorded and delivered (the decline "I can't choose your line of inquiry, and I can't write your
    introduction, ..." is one since the round-10 clearance on both sides; the fake dropped it before)."""
    from epinoic_logic.channel.bus import withheld_deliverable
    _ch, _inp, reports, _questions = _deliver(kit)
    texts = [DATA["response_text"], *re.split(r"\n\s*\n", DATA["response_text"]), *(c["text"] for c in DATA["claims"]),
             *(c.claim_text for r in reports for c in r.claims)]
    texts += [s for t in list(texts) for s in re.split(r"(?<=[.!?])\s+", t)]
    differ = [(t[:80], withheld_work(t), withheld_deliverable(t)) for t in texts if withheld_work(t) != (withheld_deliverable(t) or (None,))[0]]
    assert not differ, differ
    assert withheld_work(BY_ID[DECLINE]["text"]) == "declined"
    [delivered] = [c for c in reports[0].claims if c.claim_text == BY_ID[DECLINE]["text"]]
    assert delivered.claim_role == "other", "the delivery reads the decline as a note since the round-10 clearance"
    result = R.run(input_doc(sources=[{**FIRST, "claims": [claim(delivered.claim_id, delivered.claim_text, role="other", materiality="supporting",
                                                                       certainty=delivered.certainty)]}, SECOND]), FaithfulFakeProvider())
    assert result.ok, result.refusal
    assert [(c["text"], c["transformation"]) for c in result.output["claims"] if c["source_claim_ids"] == [delivered.claim_id]] == \
        [(BY_ID[DECLINE]["text"], "carried")], "the decline, roled 'other' by the delivery, is carried word for word (rule 7)"


# ----------------------------------------------------------------------------------------------- the hub's ledger, as the round delivered


def _ledger_as_delivered_in_the_round(kit, *, keep_questions: bool) -> list:
    """The hub's claim ledger (``integrity.ledger.check_synthesis_ledger``, as the channel calls it on a relay) on the round's
    delivery as recorded: the recorded claims with the roles the round's hub gave them (the four questions roled
    interpretation, supporting), the second answer, and the recorded synthesis (or the one rule 6 asks for)."""
    import hashlib
    from epinoic_logic.integration.canonical import canonical_json
    from epinoic_logic.integration.protocol import dump
    from epinoic_logic.integrity.contracts import Synthesis
    from epinoic_logic.integrity.ledger import check_synthesis_ledger
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport

    def report(source: dict, response: str):
        base = dict(request_id="req-ll-t16", task_id="task-ll-t16", report_id=source["report_id"], agent_id=source["agent_id"], subject=DATA["subject"],
                    task_type=DATA["task_type"])
        claims = [ClaimRecord(**base, claim_id=c["claim_id"], claim_text=c["text"], claim_role=c["role"], materiality=c["materiality"], certainty=c["certainty"])
                  for c in source["claims"]]
        return SpecialistReport(report_id=source["report_id"], request_id="req-ll-t16", task_id="task-ll-t16", agent_id=source["agent_id"], subject=DATA["subject"],
                                task_type=DATA["task_type"], original_response=response, response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
                                created_at="2026-11-15T10:00:00Z", claims=claims)

    reports = [report(FIRST, DATA["response_text"]), report(SECOND, f"{SECOND_CONTENT}\n\n{QUESTION_BACK}")]
    inp = kit.build_input({"task_id": "task-ll-t16", "request_id": "req-ll-t16"}, [kit.source_report(r.model_dump(mode="json"), "english") for r in reports],
                          PACK.identity())
    result = R.run(canonical_json(dump(inp)), ScriptedProvider(text(_recorded_agent_output(keep_questions=keep_questions))))
    assert result.ok, result.refusal
    payload = kit.synthesis_payload(kit.check_output(result.text, inp), inp, synthesis_id="syn-ll-t16", combinator_agent_id="synthesis",
                                    created_at="2026-11-15T10:00:00Z")
    supplied = DATA["supplied_texts"][0]
    return check_synthesis_ledger(reports, Synthesis.model_validate(payload), extra_texts=(supplied["text"],),
                                  document_texts={supplied["document_id"]: supplied["text"]})


def test_the_hubs_ledger_names_nothing_on_the_questions_when_the_synthesis_keeps_them(kit):
    """The control of the rule below: the synthesis rule 6 asks for draws no finding on the questions."""
    findings = _ledger_as_delivered_in_the_round(kit, keep_questions=True)
    assert not [f for f in findings if set(QUESTIONS) & set(f.claim_ids)], [(f.code, f.claim_ids[:3], f.message[:160]) for f in findings]


def test_the_hubs_ledger_names_the_questions_the_recorded_synthesis_dropped_whatever_their_role(kit):
    findings = _ledger_as_delivered_in_the_round(kit, keep_questions=False)
    for q in QUESTIONS:
        named = [f for f in findings if f.code == "INT-LEDGER-019" and q in f.claim_ids]
        assert named and named[0].severity == "warning" and LEAD in named[0].message, (q, [(f.code, f.claim_ids[:3], f.message[:160]) for f in findings])
