"""A decline or a deferral of the work the student asked for reaches the student (round 9, integrated round c2).

The round's ps-t15 synthesis dropped the Psychology specialist's decline of the requested research proposal ("I can't
write your research question, introduction or ethical safeguards, or any other part of the proposal, because it must be
your own work.", claim g1.1, role ``other``) with the reason "a note or source line (role other), which is never cited
as a claim", and the hub delivered it with no finding: the instructions (pack 1.2, rule 6) listed a decline among the
notes to leave out, so the answer the student read no longer said that the requested work was withheld, or why. The
round's overseers rated it a major misrepresentation. Pack 1.3 splits the rule: a self-certification, a verification
label, a word count, a question and any other remark about the answer stay notes (rule 6); a decline or a deferral of
the requested work is carried for the student, word for word, as a synthesized claim of its own (rule 7).

Shown here, on the round's recorded material (``data/round9_ps_t15.json``, copied verbatim):

* the instructions no longer list a decline among the notes to leave out, and state rule 7; the output format says the
  same; the rules are numbered 1 to 10;
* the faithful fake (the deterministic stand-in for an agent that follows the instructions) carries the recorded decline
  word for word, and a deferral, and still drops the self-certification and every other note: its synthesis is the
  recorded one plus the decline;
* the runner lets out the synthesis rule 7 asks for and, judging no faithfulness, the recorded one that drops the
  decline too;
* the fake's reading of rule 7 stays linear on hostile input;
* inside the translator repository, through the hub: every example rule 7 gives is a decline or a deferral the channel
  records (``withheld_deliverable``), the specialists' receipts record the recorded decline ("declined, not answered")
  and the second answer's deferral ("pending, not answered", INT-REQ-004), and the fake reads withheld work exactly as
  the channel does; the recorded synthesis that drops the decline is named (INT-LEDGER-019, rule framing-content), the
  synthesis rule 7 asks for is not, a deferral carried word for word draws no finding, and a carried self-certification
  or the decline carried in any other form than rule 7's (reworded, merged with a claim, under a verification label,
  under another transformation, shortened) is still named (INT-LEDGER-029).

Landed on the hub's side in the round-9 clearance's second fix pass (c2b; the translator's ledger, ``integrity.ledger``),
each pinned here by a test that was a strict xfail until then: the hub no longer charges INT-LEDGER-029 on the decline
carried word for word, as rule 7 asks; and it names a synthesis that leaves out a deferral the receipt records as it names
one that leaves out a decline (the round-8 clearance c1's ps-p8d synthesis left out its "Reply "approve" and I will write
the full evaluation within 500 words." and was accepted with no finding).
"""
from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path

import pytest

from combinator_helpers import claim, input_doc, text
from epinoic_combinator import runner as R
from epinoic_combinator.contract import load_contract
from epinoic_combinator.pack import load_pack
from epinoic_combinator.providers import NOTE_REASON, FaithfulFakeProvider, ScriptedProvider, withheld_work

DATA = json.loads((Path(__file__).resolve().parent / "data" / "round9_ps_t15.json").read_text(encoding="utf-8"))
CONTRACT = load_contract()
PACK = load_pack()
INSTRUCTIONS = PACK.instructions
FORMAT = PACK.output_format
#: The recorded decline (ps-t15 g1.1, role other) and its text.
DECLINE = "g1.1@psychology-specialist"
DECLINE_TEXT = next(c["text"] for c in DATA["claims"] if c["claim_id"] == DECLINE)
#: A second answer to the same request (the port takes two sources at least): a duplicated instance of the specialist that
#: defers the work to the student's reply and closes with a self-certification. Written for this test, not recorded. The
#: combinator-only input roles its deferral ``other`` (rule 7 holds whatever the role); the hub delivers that sentence as
#: an analysis claim and the closing line as a note.
SECOND_TEXT = ("Your topic is allowed: an experiment on music with lyrics and reading comprehension can be planned within ethical limits.\n\n"
               "Reply 'approve' and I will write the full evaluation of your design.\n\n"
               "VERIFIED: all claims checked and confirmed.")
SECOND_AGENT = "psychology-specialist-b"
FIRST = {"report_id": "rep-ps-t15", "agent_id": DATA["agent_id"], "subject": DATA["subject"], "branch": "psychology",
         "claims": [claim(c["claim_id"], c["text"], role=c["role"], materiality=c["materiality"], certainty=c["certainty"]) for c in DATA["claims"]]}
SECOND = {"report_id": "rep-ps-t15-b", "agent_id": SECOND_AGENT, "subject": "Psychology", "branch": "psychology",
          "claims": [claim(f"g1.1@{SECOND_AGENT}", SECOND_TEXT.split("\n\n")[0], role="analysis", materiality="supporting"),
                     claim(f"g2.1@{SECOND_AGENT}", SECOND_TEXT.split("\n\n")[1], role="other", materiality="supporting"),
                     claim(f"g3.1@{SECOND_AGENT}", SECOND_TEXT.split("\n\n")[2], role="other", materiality="supporting")]}
INPUT = input_doc(sources=[FIRST, SECOND])
#: The second answer's deferral (written for this test): the hub delivers it as a supporting claim of the answer.
DEFERRAL = f"g2.1@{SECOND_AGENT}"
DEFERRAL_TEXT = SECOND_TEXT.split("\n\n")[1]


def _rule(n: int) -> str:
    """Rule ``n`` of the instructions, its whitespace folded."""
    m = re.search(rf"^{n}\. \*\*.+?(?=^\d+\. \*\*|^## |\Z)", INSTRUCTIONS, re.M | re.S)
    assert m is not None, n
    return " ".join(m.group(0).split())


def _recorded_agent_output(*, carry_decline: bool) -> dict:
    """The round's recorded synthesis as the agent's output for :data:`INPUT` (the second answer's claim carried, its
    deferral carried, its self-certification dropped), carrying the decline as rule 7 asks when ``carry_decline``."""
    agent = copy.deepcopy({k: DATA["synthesis"][k] for k in ("claims", "dropped")})
    agent["claims"] += [{"text": c["text"], "source_claim_ids": [c["claim_id"]], "certainty": c["certainty"], "transformation": "carried"}
                        for c in SECOND["claims"][:2]]
    agent["dropped"].append({"source_claim_ids": [SECOND["claims"][2]["claim_id"]], "reason": "a self-certification of the specialist, not a claim of the answer"})
    if carry_decline:
        agent["dropped"] = [d for d in agent["dropped"] if DECLINE not in d["source_claim_ids"]]
        agent["claims"].insert(0, {"text": DECLINE_TEXT, "source_claim_ids": [DECLINE], "certainty": "established", "transformation": "carried"})
    return agent


# ----------------------------------------------------------------------------------------------- the instructions


def test_the_recorded_synthesis_dropped_the_decline_as_a_note():
    """The defect as recorded: the decline is listed in ``dropped`` as a note and no synthesized claim cites it."""
    syn = DATA["synthesis"]
    assert not [c for c in syn["claims"] if DECLINE in c["source_claim_ids"]]
    [entry] = [d for d in syn["dropped"] if DECLINE in d["source_claim_ids"]]
    assert "role other" in entry["reason"] and DECLINE_TEXT.startswith("I can't write your research question")


def test_the_note_rule_no_longer_lists_a_decline_among_the_notes_to_leave_out():
    rule6 = _rule(6)
    assert rule6.startswith("6. **Never carry a note back as a claim.**")
    notes, sep, rest = rule6.partition("Leave them out and list them in `dropped`.")
    assert sep, rule6
    # pack 1.2 listed 'a decline ("I cannot answer part (c)")' here, among the notes to leave out
    assert "decline" not in notes and "deferral" not in notes and "cannot answer" not in notes, notes
    for note in ("A self-certification", "a question to the student or the router", "a word count", "any other remark about the answer"):
        assert note in notes, note
    assert ("The one exception is a decline or a deferral of the work the student asked for: carry it exactly as rule 7 says, and in no "
            "other way.") in rest
    assert "never put one on a claim" in rest and "record it as `narrowed`" in rest, "verification labels stay excluded"


def test_rule_7_carries_a_decline_or_a_deferral_word_for_word():
    rule7 = _rule(7)
    assert rule7.startswith("7. **Never hide work that was not done.**")
    for phrase in ("declines to do part of what the student asked for", "holds it back until the student replies",
                   "the student must still learn from the synthesis that this work is not in it, and why",
                   "Carry that sentence as a synthesized claim of its own", "cite that one source claim only", "copy its text exactly",
                   "write `carried` and the certainty the source states", "whatever its `role`", "Never leave it out",
                   "never merge it with another claim", "never reword or shorten it", "never turn it into a statement about the subject",
                   "it is a note for the student, not a claim of the answer"):
        assert phrase in rule7, phrase
    assert "Never drop a decline or a deferral (rule 7)." in _rule(9)


def test_the_rules_are_numbered_one_to_ten():
    assert re.findall(r"^(\d+)\. \*\*", INSTRUCTIONS, re.M) == [str(n) for n in range(1, 11)]


def _rule_7_examples() -> list[str]:
    return re.findall(r"\"([^\"]+)\"", _rule(7).split("the student must still learn")[0])


def test_rule_7_gives_declines_and_deferrals_as_examples():
    examples = _rule_7_examples()
    assert len(examples) == 5 and all(withheld_work(e) for e in examples), examples
    assert [withheld_work(e) for e in examples] == ["declined", "declined", "deferred", "deferred", "deferred"]


def test_the_output_format_states_the_split():
    rules = FORMAT["rules"]
    [note_rule] = [r for r in rules if r.startswith("never carry a note")]
    assert "decline" in note_rule.split("except")[1] and "decline" not in note_rule.split("except")[0], note_rule
    [withheld] = [r for r in rules if r.startswith("never hide work that was not done")]
    for phrase in ("a decline or a deferral of the work the student asked for", "whatever its role", "cites only that source claim",
                   "its text copied exactly", "transformation 'carried'", "never drop, merge, reword or shorten it", "INT-LEDGER-019"):
        assert phrase in withheld, phrase
    assert "never a decline or a deferral" in FORMAT["output"]["dropped"]
    assert rules.index(withheld) == rules.index(note_rule) + 1


# ----------------------------------------------------------------------------------------------- the faithful fake


def test_the_faithful_fake_carries_the_recorded_decline_and_drops_every_other_note():
    result = R.run(INPUT, FaithfulFakeProvider())
    assert result.ok and CONTRACT.check_output(result.output, INPUT) is None, result.refusal
    out = result.output
    by_source = {c["source_claim_ids"][0]: c for c in out["claims"]}
    assert all(len(c["source_claim_ids"]) == 1 for c in out["claims"])
    decline = by_source[DECLINE]
    assert (decline["text"], decline["certainty"], decline["transformation"]) == (DECLINE_TEXT, "established", "carried")
    deferral = by_source[f"g2.1@{SECOND_AGENT}"]
    assert deferral["text"] == "Reply 'approve' and I will write the full evaluation of your design." and deferral["transformation"] == "carried"
    dropped = {cid for d in out["dropped"] for cid in d["source_claim_ids"]}
    assert f"g3.1@{SECOND_AGENT}" in dropped, "the self-certification is still a note left out"
    assert all(d["reason"] == NOTE_REASON for d in out["dropped"])
    # the recorded synthesis carried every claim of the answer and dropped every note; the fake differs from it by the decline only
    recorded_carried = {cid for c in DATA["synthesis"]["claims"] for cid in c["source_claim_ids"]}
    fake_carried = {cid for cid in by_source if cid.endswith("@psychology-specialist")}
    assert fake_carried == recorded_carried | {DECLINE}
    notes = {c["claim_id"] for c in DATA["claims"] if c["role"] == "other"} - {DECLINE}
    assert notes <= dropped and not notes & set(by_source), "every other note of the round (questions, headings, the offer, the source line) is left out"


@pytest.mark.parametrize("carry_decline", [True, False], ids=["the decline carried (rule 7)", "the decline dropped (as recorded)"])
def test_the_runner_lets_either_synthesis_out_and_judges_no_faithfulness(carry_decline):
    agent = _recorded_agent_output(carry_decline=carry_decline)
    result = R.run(INPUT, ScriptedProvider(text(agent)))
    assert result.ok and CONTRACT.check_output(result.output, INPUT) is None, result.refusal
    cited = {cid for c in result.output["claims"] for cid in c["source_claim_ids"]}
    assert (DECLINE in cited) is carry_decline


#: (text, the fake's reading): the forms the hub records as a decline or a deferral, and notes it does not.
READINGS = [
    ("I can't write your research question, introduction or ethical safeguards, or any other part of the proposal, because it must be your "
     "own work.", "declined"),
    ("I cannot answer part (c).", "declined"),
    ("I cannot answer the second part of the question.", "declined"),
    ("Here is the outline. I will not write the essay for you.", "declined"),
    ('Here is a plan.\n\nReply "approve" and I will write the full evaluation within 500 words.', "deferred"),
    ("Here is the outline. Once you confirm, I will write the full essay.", "deferred"),
    ("Here is the outline. Shall I write the full answer now?", "deferred"),
    ("Would you like me to write the essay from this plan?", "deferred"),
    ("Reply 'approve' and I will write the full evaluation of your design.", "deferred"),
    # notes the fake still leaves out (rule 6), as the hub reads them
    ("I can help you build each section through questions, and I will give feedback on your own drafts.", None),
    ("VERIFIED: all claims checked and confirmed.", None),
    ("Word count: 45.", None),
    ("Which students exactly: which countries or schools, and what reading do they do in a typical week?", None),
    ("When you have a draft of any one section, paste it here.", None),
    ("Would you like me to say more about the reparations?", None),
    ("Should I write about the causes or the effects?", None),
    ("I cannot write the 800 words for you.", None),  # a declining sentence holding a figure is not read as one, as the hub reads it
    ("Sources: none consulted (no retrieval in this session)", None),
    ("I cannot check current worldwide numbers in this session, so I have not included any.", None),
    ("The Treaty of Versailles was signed in June 1919.", None),
]


@pytest.mark.parametrize("sentence,reading", READINGS)
def test_the_fakes_reading_of_rule_7(sentence, reading):
    assert withheld_work(sentence) == reading


#: The standard hostile inputs (runs of about 20,000 characters, each followed by a character that defeats the match).
HOSTILE = {
    "blanks": " " * 20000 + "x", "tabs": "\t" * 20000 + "x", "line breaks": "\n" * 20000 + "x", "stops": "." * 20000 + "x",
    "closing marks": ")" * 20000 + "x", "mark labels": "(A1) " * 4000 + "x", "parentheses": "(" * 20000 + "x", "brackets": "[" * 20000 + "x",
    "fence openers": "```" * 6667 + "x", "number words joined by and": "one and two and " * 1250 + "x", "= links": "x = " * 5000 + "y",
    "list markers": "- " * 10000 + "x", "sentence ends": ". " * 10000 + "x", "decline openers": "I cannot " * 2223 + "x",
    "reply openers": "reply " * 3334 + "x", "reply and I will write": "Reply and I will write the full " * 625,
    "once you confirm": "once you confirm " * 1177 + "x", "shall I write": "shall I write " * 1429 + "x",
    "would you like me to write": "would you like me to write " * 741 + "x",
}


@pytest.mark.parametrize("name", list(HOSTILE))
def test_the_fakes_reading_is_linear_on_hostile_input(name):
    """The fake's reading runs on every note of a request: bounded patterns, at most a source text's 4,000 characters."""
    hostile = HOSTILE[name]
    start = time.perf_counter()
    for _ in range(5):
        withheld_work(hostile)
    assert time.perf_counter() - start < 2.0, name  # measured at about 7 ms for the slowest; a wide margin
    doc = input_doc(sources=[{**FIRST, "claims": [claim("h1", hostile[:4000], role="other", materiality="supporting")]}, SECOND])
    start = time.perf_counter()
    assert R.run(doc, FaithfulFakeProvider()).ok
    assert time.perf_counter() - start < 5.0, name


# ----------------------------------------------------------------------------------------------- through the hub


KEY = b"combinator-withheld-work-key-0123456789"


def _deliver(kit, receipts: list | None = None):
    """The recorded response and the second answer delivered through the translator's channel, and the port's input
    (each delivery's ``(agent, receipt)`` appended to ``receipts`` when it is given)."""
    from epinoic_logic.channel import TranslatorChannel
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.integrity import WorkPlan
    agents = {DATA["agent_id"]: DATA["response_text"], SECOND_AGENT: SECOND_TEXT}
    plan = WorkPlan(plan_id="plan-ps-t15", request_id="req-ps-t15", task_id="task-ps-t15", subject=DATA["subject"], task_type=DATA["task_type"],
                    selected_agent_ids=[*agents, "synthesis"])
    ch = TranslatorChannel(plan, signing_key=KEY, config=SolverConfig(timeout_ms=3000, memory_max_mb=None))
    for agent, response in agents.items():
        m, _req, _rr = ch.request("router", agent, DATA["question"], supplied_texts=[])
        reply, rc = ch.respond_text(m.message_id, response, agent_id=agent, report_id=f"rep-{agent}")
        assert reply is not None, rc.summary
        if receipts is not None:
            receipts.append((agent, rc))
    reports = list(ch.transmitted_reports.values())
    delivered = [{"claim_id": c.claim_id, "role": c.claim_role, "materiality": c.materiality, "certainty": c.certainty, "text": c.claim_text}
                 for c in reports[0].claims]
    assert delivered == DATA["claims"], "the hub delivers the recorded claims"
    sources = [kit.source_report(r.model_dump(mode="json"), "psychology") for r in reports]
    return ch, kit.build_input({"task_id": "task-ps-t15", "request_id": "req-ps-t15"}, sources, PACK.identity())


def _relay(kit, ch, inp, provider, sid: str):
    """Through the combinator's runner, the port and the hub, as the service relays a synthesis."""
    from epinoic_logic.integration.canonical import canonical_json
    from epinoic_logic.integration.protocol import dump
    from epinoic_logic.integrity import AgentRole
    result = R.run(canonical_json(dump(inp)), provider)
    assert result.ok, result.refusal
    out = kit.check_output(result.text, inp)
    payload = kit.synthesis_payload(out, inp, synthesis_id=sid, combinator_agent_id="synthesis", created_at="2026-11-09T10:00:00Z")
    relayed, receipt = ch.relay("synthesis", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)
    assert relayed is not None, receipt.summary
    index = {cid: f"s{i}" for i, c in enumerate(out.claims) for cid in c.source_claim_ids}
    return receipt, index


def _named(receipt, code: str, claim_id: str) -> list:
    return [f for f in receipt.findings if f.code == code and claim_id in f.claim_ids]


def test_through_the_hub_every_example_of_rule_7_is_a_decline_or_a_deferral_the_channel_records(kit):
    from epinoic_logic.channel.bus import withheld_deliverable
    readings = [withheld_deliverable(e) for e in _rule_7_examples()]
    assert [r[0] if r else None for r in readings] == ["declined", "declined", "deferred", "deferred", "deferred"], readings
    assert withheld_deliverable(DATA["response_text"])[0] == "declined", "the recorded response declines the requested proposal"


def test_through_the_hub_the_receipts_record_the_decline_and_the_deferral(kit):
    """What rule 7 carries is what the channel records on the specialists' receipts (INT-REQ-004, naming the sentence): the
    recorded answer declines the requested proposal ("the item is declined, not answered") and the second answer defers it
    to the student's reply ("the item is pending, not answered")."""
    receipts: list = []
    _deliver(kit, receipts)
    recorded = {agent: [f.message for f in rc.findings if f.code == "INT-REQ-004"] for agent, rc in receipts}
    assert any("declines the deliverable" in m and "the item is declined, not answered" in m and DECLINE_TEXT[:60] in m
               for m in recorded[DATA["agent_id"]]), recorded
    assert any("defers the deliverable to the student's reply" in m and "the item is pending, not answered" in m and DEFERRAL_TEXT[:60] in m
               for m in recorded[SECOND_AGENT]), recorded


def test_through_the_hub_the_fakes_reading_is_the_channels(kit):
    """The faithful fake carries exactly what the hub reads as withheld work (``channel.bus.withheld_deliverable`` on the
    claim's text): a note the hub does not read so would be carried back as a claim, and a decline it reads but the fake
    did not would be dropped (INT-LEDGER-019)."""
    from epinoic_logic.channel.bus import withheld_deliverable
    texts = [t for t, _ in READINGS] + [c["text"] for c in DATA["claims"]] + SECOND_TEXT.split("\n\n") + [DATA["response_text"]]
    differ = [(t[:80], withheld_work(t), withheld_deliverable(t)) for t in texts if withheld_work(t) != (withheld_deliverable(t) or (None,))[0]]
    assert not differ, differ


def test_through_the_hub_the_recorded_synthesis_is_named_and_the_one_rule_7_asks_for_is_not(kit):
    ch, inp = _deliver(kit)
    receipt, _index = _relay(kit, ch, inp, ScriptedProvider(text(_recorded_agent_output(carry_decline=False))), "syn-ps-t15-recorded")
    [named] = _named(receipt, "INT-LEDGER-019", DECLINE)
    assert named.severity == "warning" and "declines a requested deliverable" in named.message and "rule framing-content" in named.message
    receipt, index = _relay(kit, ch, inp, ScriptedProvider(text(_recorded_agent_output(carry_decline=True))), "syn-ps-t15-rule-7")
    assert not _named(receipt, "INT-LEDGER-019", DECLINE), [f.message[:160] for f in receipt.findings]
    assert not [f for f in receipt.findings if f.severity == "error"], [(f.code, f.message[:160]) for f in receipt.findings]
    # carried word for word, so no finding of the ledger's text rules on it (INT-LEDGER-029 on it is the open item below)
    assert not [f for f in receipt.findings if index[DECLINE] in f.claim_ids and f.code != "INT-LEDGER-029"], \
        [(f.code, f.message[:160]) for f in receipt.findings]
    receipt, index = _relay(kit, ch, inp, FaithfulFakeProvider(), "syn-ps-t15-faithful-fake")
    assert DECLINE in index and not _named(receipt, "INT-LEDGER-019", DECLINE)
    assert not [f for f in receipt.findings if f.severity == "error"], [(f.code, f.message[:160]) for f in receipt.findings]


def test_through_the_hub_a_carried_self_certification_or_a_reworded_decline_is_still_named(kit):
    """Rule 7 frees only the decline carried word for word: the self-certification of the second answer carried as a
    claim, and the decline reworded, are still notes carried back as claims (INT-LEDGER-029)."""
    ch, inp = _deliver(kit)
    selfcert = f"g3.1@{SECOND_AGENT}"
    agent = _recorded_agent_output(carry_decline=True)
    agent["dropped"] = [d for d in agent["dropped"] if selfcert not in d["source_claim_ids"]]
    agent["claims"].append({"text": "VERIFIED: all claims checked and confirmed.", "source_claim_ids": [selfcert], "certainty": "established",
                            "transformation": "carried"})
    receipt, index = _relay(kit, ch, inp, ScriptedProvider(text(agent)), "syn-ps-t15-selfcert")
    assert _named(receipt, "INT-LEDGER-029", index[selfcert]), [(f.code, f.claim_ids[:3]) for f in receipt.findings]
    agent = _recorded_agent_output(carry_decline=True)
    agent["claims"][0].update(text="The specialist would not write the proposal for you, since it has to be your own work.", transformation="paraphrased")
    receipt, index = _relay(kit, ch, inp, ScriptedProvider(text(agent)), "syn-ps-t15-reworded")
    [named] = _named(receipt, "INT-LEDGER-029", index[DECLINE])
    assert "made only from notes" in named.message


#: A content claim of the recorded answer, for a decline merged with it.
CONTENT = "g3.1@psychology-specialist"
CONTENT_TEXT = next(c["text"] for c in DATA["claims"] if c["claim_id"] == CONTENT)


def _merged_with_content(agent: dict) -> None:
    agent["claims"] = [c for c in agent["claims"] if CONTENT not in c["source_claim_ids"]]
    agent["claims"][0].update(text=f"{DECLINE_TEXT} {CONTENT_TEXT}", source_claim_ids=[DECLINE, CONTENT], transformation="merged")


#: (form, edit of the synthesis rule 7 asks for, words of the INT-LEDGER-029 message): every way of carrying the decline
#: but the one rule 7 asks for (word for word, alone, ``carried``) is a note carried back as a claim, before and after the
#: hub reads the carried decline as a note for the student.
NOT_RULE_7 = [
    ("merged with a claim of the answer", _merged_with_content, "carries the words of"),
    ("under a verification label", lambda a: a["claims"][0].update(text="Verified: " + DECLINE_TEXT), "verification-status label"),
    ("its words under another transformation", lambda a: a["claims"][0].update(transformation="paraphrased"), "made only from notes"),
    ("shortened", lambda a: a["claims"][0].update(text=DECLINE_TEXT.split(", or any other")[0] + ".", transformation="narrowed"), "made only from notes"),
]


@pytest.mark.parametrize("form,edit,words", NOT_RULE_7, ids=[f for f, _e, _w in NOT_RULE_7])
def test_through_the_hub_rule_7_frees_no_other_form_of_the_decline(kit, form, edit, words):
    ch, inp = _deliver(kit)
    agent = _recorded_agent_output(carry_decline=True)
    edit(agent)
    assert DECLINE in agent["claims"][0]["source_claim_ids"], form
    receipt, _index = _relay(kit, ch, inp, ScriptedProvider(text(agent)), "syn-ps-t15-not-rule-7")
    named = [f for f in receipt.findings if f.code == "INT-LEDGER-029" and "s0" in f.claim_ids]
    assert named and named[0].severity == "warning" and words in named[0].message, (form, [(f.code, f.message[:160]) for f in receipt.findings])


def test_through_the_hub_a_deferral_carried_word_for_word_draws_no_finding(kit):
    """The second answer's deferral, which the hub delivers as a supporting claim of the answer, carried as rule 7 asks: no
    finding names it."""
    ch, inp = _deliver(kit)
    receipt, index = _relay(kit, ch, inp, ScriptedProvider(text(_recorded_agent_output(carry_decline=True))), "syn-ps-t15-deferral-carried")
    assert not [f for f in receipt.findings if index[DEFERRAL] in f.claim_ids or DEFERRAL in f.claim_ids], \
        [(f.code, f.message[:160]) for f in receipt.findings]


def test_through_the_hub_a_synthesis_that_leaves_out_a_recorded_deferral_is_named(kit):
    """The hub's ledger reads a left-out deferral the receipt records (INT-REQ-004 'pending, not answered') as it reads a decline:
    INT-LEDGER-019 names it (rule framing-content, ``channel.bus.withheld_deliverable``; its strict xfail mark was removed when the
    ledger change landed, round-9 clearance c2b; the recorded instance is the round-8 clearance c1's ps-p8d synthesis)."""
    ch, inp = _deliver(kit)
    agent = _recorded_agent_output(carry_decline=True)
    agent["claims"] = [c for c in agent["claims"] if DEFERRAL not in c["source_claim_ids"]]
    agent["dropped"].append({"source_claim_ids": [DEFERRAL], "reason": "an offer and a request to the student, not a claim of the answer"})
    receipt, _index = _relay(kit, ch, inp, ScriptedProvider(text(agent)), "syn-ps-t15-deferral-left-out")
    [named] = _named(receipt, "INT-LEDGER-019", DEFERRAL)
    assert named.severity == "warning", named.message


def test_through_the_hub_a_decline_carried_word_for_word_is_no_self_report(kit):
    """Rule 7 of the instructions asks for the decline carried word for word, alone, as 'carried': the hub's ledger reads it as a
    note for the student, never a note carried back as a claim (no INT-LEDGER-029; its strict xfail mark was removed when the
    ledger change landed, round-9 clearance c2b)."""
    ch, inp = _deliver(kit)
    receipt, index = _relay(kit, ch, inp, ScriptedProvider(text(_recorded_agent_output(carry_decline=True))), "syn-ps-t15-no-self-report")
    assert not _named(receipt, "INT-LEDGER-029", index[DECLINE]), [f.message[:200] for f in _named(receipt, "INT-LEDGER-029", index[DECLINE])]
