"""Round-10 clearance (integrated round c3), integration fixer: a quotation left alone in the student-facing text (communication
fidelity, minor; the follow-up of c2 bug 19, which the round-9 clearance fixed: no quotation is rendered twice).

The lit-t16 synthesis carried the evidence claim p2-q01, '"The queen is somewhere in the dark"', and dropped the 'Next step' note
that quoted it (p2-point, as the round's hub delivered it; the parsers roled it a note, ``other``, during the same clearance):
the combinator port rendered the quotation alone at the end of the student-facing text ('... care and hurt have merged in the
speaker's grief. "The queen is somewhere in the dark"') and no finding named it. The communication-fidelity overseer's exchange
x10 reproduces it (``data/c3_orphaned_quotation.json`` holds both, copied verbatim from the round).

* The port renders a carried quotation claim only inside a claim that quotes it (``combinator_port.orphaned_quotations``;
  ``student_facing_text`` with the claims' citations and the input's sources, as ``synthesis_payload`` calls it): a quotation whose
  every quoting source claim the synthesis left out is not rendered on its own, and the hub names the synthesized claim the
  student does not read (INT-LEDGER-017, warning), so a synthesis carrying a quotation nothing uses is never accepted silently.
  The quotations its sentences hold are still rendered once, inside them (c2 bug 19), and the text stays a composition of its
  claims (no INT-LEDGER-031).
* Controls: a quotation no other source claim quotes (a specialist's own bare quotation), one a carried claim quotes (whatever
  its synthesized text became), one only another report's claim quotes, one the synthesis made from a claim that is not that
  quotation, a quotation of two words, and a synthesis whose text would be left empty keep the quotation rendered; without the
  citations and sources the composer is the round-9 one (``test_c2b_student_facing_text.py``, unchanged).
* The reader is linear: it reads each text once and looks each quotation up (the standard hostile inputs of
  ``tests/core_hostile.py``, and the contract's bounds).
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import pytest

from epinoic_logic.integration import combinator_port as CB
from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.protocol import PROTOCOL
from epinoic_logic.integrity.ledger import quotations_held_verbatim

from ..core_hostile import SHAPES, one, sweep

DATA = json.loads((Path(__file__).parent / "data" / "c3_orphaned_quotation.json").read_text(encoding="utf-8"))
QUEEN = '"The queen is somewhere in the dark"'
PACK = {"name": "combinator-instructions", "version": "1.0", "sha256": "9a" * 32}
IDS = {"task_id": "t_" + "0" * 31 + "3", "request_id": "a_" + "0" * 31 + "3"}
#: The port combines two answers at least (its combined mode): a second answer, dropped by the synthesis with its reason.
PEER = {"report_id": "rep-peer", "agent_id": "history-specialist", "subject": "History", "branch": "history",
        "claims": [{"claim_id": "h1.1", "role": "point", "materiality": "material", "certainty": "probable",
                    "claim_text_sha256": sha256_text("The poem was published in 2019."), "text": "The poem was published in 2019."}]}
PEER_DROPPED = {"source_claim_ids": ["h1.1"], "reason": "the publication date answers another question than the poem's grief"}
#: How each recorded delivery is read: as the round's hub delivered it (the note roled a point), and with the note roled
#: 'other' under an id of its own, as the parsers deliver it since the round-10 clearance.
DELIVERIES = ("as recorded", "note roled other")


def _claims(task: str, delivery: str) -> list[dict]:
    """The delivered claims of ``task``: as recorded, or with its 'Next step' note roled 'other' under a sentence id."""
    claims = copy.deepcopy(DATA[task]["delivered_claims"])
    if delivery == "note roled other":
        for c in claims:
            if c["text"].startswith("Next step"):
                c.update(claim_id="p2-s01", role="other", materiality="supporting")
    return claims


def _note(claims: list[dict]) -> str:
    [note] = [c["claim_id"] for c in claims if c["text"].startswith("Next step")]
    return note


def _input(task: str, claims: list[dict]) -> CB.CombinatorInput:
    item = DATA[task]
    source = {"report_id": f"rep-{task}", "agent_id": item["agent_id"], "subject": item["subject"], "branch": "english",
              "claims": [{**c, "claim_text_sha256": sha256_text(c["text"])} for c in claims]}
    return CB.build_input(IDS, [source, PEER], PACK)


def _output(task: str, claims: list[dict], *, drop_the_quotation: bool = False) -> dict:
    """The recorded synthesis of ``task`` as a port output: its claims as the combinator wrote them, its dropped note cited
    under the id the delivery gives it, and the peer answer dropped (``drop_the_quotation``: the quotation dropped with its note,
    the control)."""
    syn = DATA[task]["synthesis"]
    note = _note(claims)
    out_claims = [{**c, "evidence_refs": None} for c in syn["claims"] if not (drop_the_quotation and c["text"] == QUEEN)]
    dropped = [{**d, "source_claim_ids": [note if x == "p2-point" else x for x in d["source_claim_ids"]]} for d in syn["dropped"]]
    if drop_the_quotation:
        [quotation] = [c["claim_id"] for c in claims if c["text"] == QUEEN]
        dropped = [{**d, "source_claim_ids": [*d["source_claim_ids"], quotation]} if note in d["source_claim_ids"] else d for d in dropped]
    return {"schema": "epinoic.integration.combinator-output.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": IDS,
            "instruction_pack_sha256": PACK["sha256"], "claims": out_claims, "dropped": [*dropped, PEER_DROPPED], "conflicts": []}


def _payload(task: str, delivery: str, **kw) -> tuple[dict, list[dict], CB.CombinatorInput, CB.CombinatorOutput]:
    claims = _claims(task, delivery)
    inp = _input(task, claims)
    out = CB.check_output(_output(task, claims, **kw), inp)
    payload = CB.synthesis_payload(out, inp, synthesis_id=f"syn-{task}", combinator_agent_id="synthesis", created_at="2026-11-15T10:00:00Z")
    return payload, claims, inp, out


#: The last sentence each synthesis carries before the quotation the round rendered alone.
LAST_SENTENCE = {"lit-t16": "suggests that care and hurt have merged in the speaker's grief.", "x10": "so routine continues while speech fails."}


@pytest.mark.parametrize("delivery", DELIVERIES)
@pytest.mark.parametrize("task", ("lit-t16", "x10"))
def test_the_port_never_renders_a_quotation_whose_quoting_note_was_dropped_on_its_own(task, delivery):
    payload, claims, inp, out = _payload(task, delivery)
    texts = [c.text for c in out.claims]
    [orphan] = [i for i, t in enumerate(texts) if t == QUEEN]
    citations = [list(c.source_claim_ids) for c in out.claims]
    sources = [[(c.claim_id, c.text) for c in s.claims] for s in inp.sources]
    assert CB.orphaned_quotations(texts, citations, sources) == {orphan: [_note(claims)]}
    text = payload["text"]
    assert QUEEN not in text and "queen" not in text.casefold(), text[-200:]
    assert text.endswith(LAST_SENTENCE[task]), text[-200:]
    # c2 bug 19 stays fixed: every quotation a sentence holds is rendered once, inside that sentence
    held = quotations_held_verbatim(texts)
    assert held, "the synthesis carries quotation claims beside the sentences that quote them"
    for i in held:
        assert text.count(texts[i]) == 1, texts[i]
    # the text is the claims joined, the held quotations and the orphaned one left out
    assert text == " ".join(t for i, t in enumerate(texts) if i not in held and i != orphan)
    assert text == CB.student_facing_text(texts, citations=citations, sources=sources)
    # the round-9 composer (no citations, no sources) still renders the quotation alone: the port passes them
    assert CB.student_facing_text(texts).endswith(LAST_SENTENCE[task] + " " + QUEEN)


def _report(task: str, claims: list[dict]):
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport
    item = DATA[task]
    base = dict(request_id=IDS["request_id"], task_id=IDS["task_id"], report_id=f"rep-{task}", agent_id=item["agent_id"], subject=item["subject"],
                task_type=item["task_type"])
    records = [ClaimRecord(**base, claim_id=c["claim_id"], claim_text=c["text"], claim_role=c["role"], materiality=c["materiality"], certainty=c["certainty"])
               for c in claims]
    response = item["response_text"]
    return SpecialistReport(report_id=f"rep-{task}", request_id=IDS["request_id"], task_id=IDS["task_id"], agent_id=item["agent_id"], subject=item["subject"],
                            task_type=item["task_type"], original_response=response, response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
                            created_at="2026-11-15T09:00:00Z", claims=records)


def _peer_report():
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport
    c = PEER["claims"][0]
    response = c["text"]
    return SpecialistReport(report_id=PEER["report_id"], request_id=IDS["request_id"], task_id=IDS["task_id"], agent_id=PEER["agent_id"], subject="History",
                            task_type="short_answer", original_response=response, response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
                            created_at="2026-11-15T09:00:00Z",
                            claims=[ClaimRecord(request_id=IDS["request_id"], task_id=IDS["task_id"], report_id=PEER["report_id"], agent_id=PEER["agent_id"],
                                                subject="History", task_type="short_answer", claim_id=c["claim_id"], claim_text=c["text"], claim_role="point",
                                                materiality="material", certainty="probable")])


def _ledger(task: str, delivery: str, **kw):
    """The hub's claim ledger (``integrity.ledger.check_synthesis_ledger``, as the channel calls it on a relay) on the port's
    payload, with the recorded delivery and the supplied poem."""
    from epinoic_logic.integrity.contracts import Synthesis
    from epinoic_logic.integrity.ledger import check_synthesis_ledger
    payload, claims, _inp, _out = _payload(task, delivery, **kw)
    poem = DATA[task]["supplied_texts"][0]
    findings = check_synthesis_ledger([_report(task, claims), _peer_report()], Synthesis.model_validate(payload), extra_texts=(poem["text"],),
                                      document_texts={poem["document_id"]: poem["text"]})
    return payload, findings


@pytest.mark.parametrize("delivery", DELIVERIES)
@pytest.mark.parametrize("task", ("lit-t16", "x10"))
def test_the_hub_names_the_quotation_the_student_does_not_read_and_the_text_stays_a_composition(task, delivery):
    payload, findings = _ledger(task, delivery)
    [orphan] = [c["claim_id"] for c in payload["claims"] if c["text"] == QUEEN]
    named = [f for f in findings if orphan in f.claim_ids]
    assert named and all(f.code.startswith("INT-LEDGER-") for f in named), [(f.code, f.claim_ids[:4], f.message[:160]) for f in findings]
    assert any(f.severity in ("warning", "error") for f in named), [(f.code, f.severity, f.message[:160]) for f in named]
    assert not [f for f in findings if f.code in ("INT-LEDGER-031", "INT-LEDGER-023")], [(f.code, f.message[:200]) for f in findings]
    # no other synthesized claim is named on the text: the held quotations are rendered once, inside their sentences
    synthesized = {c["claim_id"] for c in payload["claims"]}
    on_the_text = {cid for f in findings if f.code == "INT-LEDGER-017" for cid in f.claim_ids} & synthesized
    assert on_the_text <= {orphan}, [(f.claim_ids, f.message[:160]) for f in findings if f.code == "INT-LEDGER-017"]


@pytest.mark.parametrize("task", ("lit-t16", "x10"))
def test_control_the_quotation_dropped_with_its_note_draws_no_finding_on_the_text(task):
    payload, findings = _ledger(task, "note roled other", drop_the_quotation=True)
    assert QUEEN not in payload["text"] and payload["text"].endswith(LAST_SENTENCE[task])
    assert not [f for f in findings if f.code in ("INT-LEDGER-017", "INT-LEDGER-031", "INT-LEDGER-023")], [(f.code, f.message[:200]) for f in findings]


def test_through_a_hub_relay_the_x10_answer_as_delivered_today_names_the_quotation():
    """End to end on the x10 answer as the hub delivers it now (ids read from the delivery): the port's synthesis, carrying the
    quotation and dropping the note as the overseer's combinator did, is relayed, accepted with the quotation named, and its text
    ends with the paragraph's last sentence."""
    from epinoic_logic.channel import TransmissionStatus, TranslatorChannel
    from epinoic_logic.engine import SolverConfig
    from epinoic_logic.integrity import AgentRole, WorkPlan
    from epinoic_logic.translate.contracts import SuppliedText
    item = DATA["x10"]
    key = b"c3-orphaned-quotation-key-0123456789"
    plan = WorkPlan(plan_id="plan-x10", request_id=IDS["request_id"], task_id=IDS["task_id"], subject=item["subject"], task_type=item["task_type"],
                    selected_agent_ids=[item["agent_id"], PEER["agent_id"], "synthesis"], agent_subjects={PEER["agent_id"]: "History"})
    ch = TranslatorChannel(plan, signing_key=key, config=SolverConfig(timeout_ms=3000, memory_max_mb=None))
    supplied = [SuppliedText(**t) for t in item["supplied_texts"]]
    for agent, text in ((item["agent_id"], item["response_text"]), (PEER["agent_id"], PEER["claims"][0]["text"])):
        m, _req, _rr = ch.request("router", agent, item["question"], supplied_texts=supplied)
        reply, rc = ch.respond_text(m.message_id, text, agent_id=agent, report_id=f"rep-{agent}")
        assert reply is not None, rc.summary
    reports = list(ch.transmitted_reports.values())
    x10 = reports[0]
    quotation = [c.claim_id for c in x10.claims if c.claim_text == QUEEN]
    notes = [c.claim_id for c in x10.claims if c.claim_text.startswith("Next step") and QUEEN in c.claim_text]
    assert quotation and notes, ("the delivery holds the quotation claim and the note that quotes it", [(c.claim_id, c.claim_text[:60]) for c in x10.claims])
    sources = [CB.source_report(r.model_dump(mode="json"), "english" if r is x10 else "history") for r in reports]
    inp = CB.build_input(IDS, sources, PACK)
    carried = [c for c in x10.claims if c.claim_role != "other" and c.claim_id not in notes or c.claim_id in quotation]
    left = [c.claim_id for c in x10.claims if c not in carried]
    out = CB.check_output({"schema": "epinoic.integration.combinator-output.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": IDS,
                           "instruction_pack_sha256": PACK["sha256"],
                           "claims": [{"text": c.claim_text, "source_claim_ids": [c.claim_id], "certainty": c.certainty, "transformation": "carried",
                                       "evidence_refs": None} for c in carried],
                           "dropped": [{"source_claim_ids": left, "reason": "notes of the specialist, not claims of the answer"},
                                       {"source_claim_ids": [c.claim_id for c in reports[1].claims], "reason": PEER_DROPPED["reason"]}],
                           "conflicts": []}, inp)
    payload = CB.synthesis_payload(out, inp, synthesis_id="syn-x10", combinator_agent_id="synthesis", created_at="2026-11-15T10:00:00Z")
    assert QUEEN not in payload["text"] and payload["text"].endswith(LAST_SENTENCE["x10"]), payload["text"]
    [orphan] = [c["claim_id"] for c in payload["claims"] if c["text"] == QUEEN]
    relayed, receipt = ch.relay("synthesis", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)
    assert relayed is not None and receipt.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS, receipt.summary
    named = [f for f in receipt.findings if f.code.startswith("INT-LEDGER-") and orphan in f.claim_ids]
    assert named and {f.severity for f in named} & {"warning", "error"}, [(f.code, f.claim_ids[:4], f.message[:160]) for f in receipt.findings]
    assert not [f for f in receipt.findings if f.code == "INT-LEDGER-031"], [(f.code, f.message[:200]) for f in receipt.findings]


# ----------------------------------------------------------------------------------------------- controls of the reader

Q = '"one two three four"'


def _compose(texts, citations, sources) -> tuple[dict, str]:
    return CB.orphaned_quotations(texts, citations, sources), CB.student_facing_text(texts, citations=citations, sources=sources)


def test_the_orphaned_quotation_and_its_spellings():
    note = [("a-q1", Q), ("a-p", "A point of the answer."), ("a-s1", f"Next step: write a paragraph on {Q} and test it.")]
    texts, citations = [Q, "A point of the answer."], [["a-q1"], ["a-p"]]
    assert _compose(texts, citations, [note]) == ({0: ["a-s1"]}, "A point of the answer.")
    # the sources as a mapping claim id -> text, a final stop after the quotation, curly marks against straight ones
    assert CB.orphaned_quotations(texts, citations, [dict(note)]) == {0: ["a-s1"]}
    assert CB.orphaned_quotations(['"one two three four".', texts[1]], citations, [note]) == {0: ["a-s1"]}
    curly = [("a-q1", "“one two three four”"), note[1], note[2]]
    assert CB.orphaned_quotations(["“one two three four”", texts[1]], citations, [curly]) == {0: ["a-s1"]}
    # a word's apostrophe is part of the word, never a mark
    own = '"the speaker\'s grief is here"'
    assert CB.orphaned_quotations([own, texts[1]], citations, [[("a-q1", own), note[1], ("a-s1", f"Next: {own}.")]]) == {0: ["a-s1"]}
    # every quoting claim left out, the dropped one and one left unaccounted alike: both named
    two = [*note, ("a-s2", f"Also {Q}, once more.")]
    assert CB.orphaned_quotations(texts, citations, [two]) == {0: ["a-s1", "a-s2"]}


def test_controls_a_quotation_some_claim_uses_or_no_claim_quotes_stays_rendered():
    point = ("a-p", "A point of the answer.")
    texts, citations = [Q, "A point of the answer."], [["a-q1"], ["a-p"]]
    # the specialist's own bare quotation: no other source claim quotes it
    assert _compose(texts, citations, [[("a-q1", Q), point]]) == ({}, f"{Q} A point of the answer.")
    # a carried claim quotes it, whatever its synthesized text became (here a paraphrase without the quotation)
    sources = [[("a-q1", Q), point, ("a-s1", f"She says {Q} here.")]]
    assert _compose([Q, "A point of the answer.", "She says it here."], [["a-q1"], ["a-p"], ["a-s1"]], sources)[0] == {}
    # two quoting claims, one carried
    sources = [[("a-q1", Q), point, ("a-s1", f"She says {Q} here."), ("a-s2", f"Next step: {Q}.")]]
    assert _compose([Q, "A point of the answer.", "She says it here."], [["a-q1"], ["a-p"], ["a-s1"]], sources)[0] == {}
    # only another report's claim quotes it: a peer quoting the same line is not the claim that used this evidence
    assert _compose(texts, citations, [[("a-q1", Q), point], [("b-s1", f"B says {Q} too.")]]) == ({}, f"{Q} A point of the answer.")
    # another synthesized claim quotes it: the student reads it there (the round-9 rule leaves it out, nothing more)
    texts3 = [Q, "A point of the answer.", f"The writer says {Q} again."]
    assert _compose(texts3, [["a-q1"], ["a-p"], ["a-p"]], [[("a-q1", Q), point, ("a-s1", f"Next step: {Q}.")]]) == \
        ({}, f"A point of the answer. The writer says {Q} again.")
    # the synthesized quotation was made from a claim that is not that quotation (the note itself): its own content
    assert _compose(texts, [["a-s1"], ["a-p"]], [[("a-q1", Q), point, ("a-s1", f"Next step: {Q}.")]])[0] == {}
    # a quotation of two words may recur legitimately (the duplicated-content rule's floor)
    two = '"two words"'
    assert _compose([two, "A point of the answer."], citations, [[("a-q1", two), point, ("a-s1", f"Next: {two}.")]]) == \
        ({}, f"{two} A point of the answer.")
    # a citation the sources do not hold, or none at all: nothing to read it by
    assert _compose(texts, [["x9"], ["a-p"]], [[("a-q1", Q), point, ("a-s1", f"Next step: {Q}.")]])[0] == {}
    assert _compose(texts, [None, ["a-p"]], [[("a-q1", Q), point, ("a-s1", f"Next step: {Q}.")]])[0] == {}


def test_controls_the_text_is_never_left_empty_and_the_round_9_call_is_unchanged():
    sources = [[("a-q1", Q), ("a-s1", f"Next step: {Q}.")]]
    assert CB.orphaned_quotations([Q], [["a-q1"]], sources) == {0: ["a-s1"]}
    assert CB.student_facing_text([Q], citations=[["a-q1"]], sources=sources) == Q, "the only claim is rendered rather than nothing"
    texts = ['"Nobody else quotes this line at all"', "The writer turns to the budget.", '"twice quoted words here"', 'She says "twice quoted words here".']
    assert CB.student_facing_text(texts) == '"Nobody else quotes this line at all" The writer turns to the budget. She says "twice quoted words here".'
    assert CB.student_facing_text(texts, citations=[["a"], ["b"], ["c"], ["d"]], sources=[[("a", texts[0]), ("b", texts[1]), ("c", texts[2]), ("d", texts[3])]]) == \
        CB.student_facing_text(texts)
    with pytest.raises(ValueError):
        CB.orphaned_quotations([Q, "x"], [["a-q1"]], sources)


# ----------------------------------------------------------------------------------------------- linear on hostile input


def _entries(text: str):
    """The reader and the composer on a synthesis and sources made of the hostile text, quoted and plain."""
    quoted = '"' + text[:3_990] + '"'
    texts = [quoted, text, "The writer says " + quoted + " again.", text[:4_000]]
    citations = [["a-q"], ["a-p"], ["a-s"], ["b-1"]]
    sources = [[("a-q", quoted), ("a-p", text), ("a-s", "Next step: " + quoted), ("a-t", text * 2)], [("b-1", text[:4_000]), ("b-2", quoted)]]
    alone = [quoted, "A point."]
    yield "orphaned_quotations", lambda: CB.orphaned_quotations(texts, citations, sources)
    yield "orphaned_quotations (alone)", lambda: CB.orphaned_quotations(alone, [["a-q"], ["a-p"]], sources)
    yield "student_facing_text (with sources)", lambda: CB.student_facing_text(texts, citations=citations, sources=sources)
    yield "student_facing_text (alone)", lambda: CB.student_facing_text(alone, citations=[["a-q"], ["a-p"]], sources=sources)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_orphaned_quotation_reader(shape):
    """Round-10 c3 class sweep (the port's quotation reader and composer), on the standard hostile inputs."""
    assert not sweep(_entries, texts=one(shape))


def test_the_reader_is_linear_at_the_contracts_bounds():
    # 16 reports of 512 claims (the input's bounds), 15 million characters in all, their long claims quoting densely: every
    # report holds the 256 quotation claims, 16 notes (each quoting one of them, so each quotation is quoted by one note in all)
    # and 240 long claims; 256 synthesized quotation claims, each citing its quotation claim in every report (so every report is
    # read), whose quoting notes are all left out, and 256 points: each text is read once and each quotation looked up, where a
    # search per quotation over the reports would read billions of characters
    quotes = [f'"word word word {k}"' for k in range(256)]
    filler = ('"a b c d" ' * 380)[:3_700]
    reports = [[(f"r{r}-q{k}", quotes[k]) for k in range(256)] + [(f"r{r}-n{k}", f"Next step: {quotes[r * 16 + k]} {filler}") for k in range(16)]
               + [(f"r{r}-f{k}", filler) for k in range(240)] for r in range(16)]
    texts = quotes + [f"Point {k}." for k in range(256)]
    citations = [[f"r{r}-q{k}" for r in range(16)] for k in range(256)] + [[f"r{k % 16}-f{k % 240}"] for k in range(256)]
    assert all(len(rep) == 512 for rep in reports) and sum(len(t) for rep in reports for _cid, t in rep) > 14_000_000
    t0 = time.process_time()
    found = CB.orphaned_quotations(texts, citations, reports)
    composed = CB.student_facing_text(texts, citations=citations, sources=reports)
    spent = time.process_time() - t0
    assert len(found) == 256 and composed.startswith("Point 0.") and '"word' not in composed, (len(found), composed[:80])
    assert spent < 8.0, f"{spent:.2f} s"
