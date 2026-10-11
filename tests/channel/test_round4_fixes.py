"""Channel behaviour found wanting by the round-4 arena overseers: a lone UTF-16 surrogate (half an emoji) that raised out
of the hub, a self-refuting claim reported as a conflict with an innocent colleague claim and a disclosure demanded of a
faithful synthesis, decimals and thousands-separated figures counted as two words, quotation marks and possessives that
kept a paragraph from covering its request item, a specialist's hand-on of its own report called a duplicate delivery,
a refused relay recorded as delivered, a colleague's figure misreported in a paraphrase, and a synthesis whose
quotations and paraphrased content crossed unchecked."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel.bus import _terms, surrogate_offsets
from epinoic_logic.channel.request_parser import count_answer_words, count_words
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText, TranslationResult, TranslationStatus, sha256_text,
)

KEY = b"round4-channel-test-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
HI_T8 = json.loads((Path(__file__).parents[1] / "integrity" / "data" / "r4_hi_t8.json").read_text())
HI_T8_PROBLEMS = {cid: Problem.model_validate(p) for cid, p in HI_T8["problems"].items()}
POEM = SuppliedText(document_id="doc-wb", title="Composed upon Westminster Bridge, September 3, 1802", author="William Wordsworth",
                    text="Earth has not anything to show more fair:\nDull would he be of soul who could pass by\nA sight so touching in its majesty:\n"
                         "This City now doth, like a garment, wear\nThe beauty of the morning; silent, bare,\nAll bright and glittering in the smokeless air.\n"
                         "Dear God! the very houses seem asleep;\nAnd all that mighty heart is lying still!")


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def plan(agents, subject="History", task_type="short_answer", request_id="req-hi-t8", task_id="hi-t8", **over) -> WorkPlan:
    return WorkPlan(plan_id=f"plan-{task_id}", request_id=request_id, task_id=task_id, subject=subject, task_type=task_type, selected_agent_ids=list(agents), **over)


def report(agent, rid, claims, *, subject="History", task_type="short_answer", request_id="req-hi-t8", task_id="hi-t8", text=None, docs=(), created_at="2026-10-11T11:00:00Z"):
    text = text if text is not None else " ".join(c["claim_text"] for c in claims)
    return SpecialistReport(report_id=rid, request_id=request_id, task_id=task_id, agent_id=agent, subject=subject, task_type=task_type, original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=list(docs), created_at=created_at,
                            claims=[ClaimRecord(request_id=request_id, task_id=task_id, report_id=rid, agent_id=agent, subject=subject, task_type=task_type, **c) for c in claims])


def outcome(claim: ClaimRecord, rep: SpecialistReport, problem: Problem, status=TranslationStatus.TRANSLATED) -> ClaimVerificationOutcome:
    res = verify(problem, CFG, signing_key=KEY, key_id="t")
    tr = TranslationResult(translation_id=f"tr-{rep.report_id}-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=rep.report_id, status=status,
                           claim_text_sha256=sha256_text(claim.claim_text), eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="t"),
                           problem=problem, translator_version="t", policy_version="t", created_at="2026-10-11T11:00:00Z")
    return ClaimVerificationOutcome(outcome_id=f"o-{rep.report_id}-{claim.claim_id}", request_id=claim.request_id, report_id=rep.report_id, claim_id=claim.claim_id, translation=tr, verification=res,
                                    display_status=res.status, summary="stub", created_at="2026-10-11T11:00:00Z")


# ------------------------------------------------------------ 1. a lone surrogate never raises out of the hub (blocker)


@pytest.mark.parametrize("surrogate", ["\ud83d", "\ude00"])
@pytest.mark.parametrize("subject,agent,task_type", [("English A: Literature", "english-specialist", "analytical_paragraph"), ("History", "history-specialist", "short_answer")])
def test_a_lone_surrogate_is_rejected_with_its_offset_on_both_branches(surrogate, subject, agent, task_type):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan([agent], subject=subject, task_type=task_type, request_id="req-s", task_id="t-s"))
    msg, _req, _rq = hub.dispatch("t-s", agent, "Write one paragraph on the poem's stillness. Write no more than 300 words.", [POEM])
    text = "Wordsworth presents the city as \"lying still\", and the calm is the speaker's. The city glows " + surrogate + "."
    reply, rc = hub.receive("t-s", msg.message_id, text, agent_id=agent, report_id="rep-s")  # never raises
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    [f] = [x for x in rc.findings if x.code == "INT-REQ-009"]
    assert f.severity == "error" and f"offset(s) {text.index(surrogate)}" in f.message and "surrogate" in f.message
    assert rc.findings and all(x.code != "INT-REQ-001" for x in rc.findings)


def test_a_request_with_a_lone_surrogate_is_rejected_not_raised_and_hashing_never_raises():
    ch = TranslatorChannel(plan(["history-specialist"]), signing_key=KEY, config=CFG)
    msg, req, rc = ch.request("router", "history-specialist", "Outline the crash \ud83d of 1929.")
    assert msg is None and rc.status is TransmissionStatus.REJECTED and "INT-REQ-009" in codes(rc.findings) and "\ud83d" not in req.user_input
    assert surrogate_offsets("ok \ud800 and \udfff") == [3, 9] and surrogate_offsets("an emoji \U0001F600 is fine") == []
    assert sha256_text("a\ud83d") and sha256_hex("a\ud83d") and sha256_text("plain") == sha256_hex("plain")  # valid text hashes as before


# ------------------------------------------------------------ 2. a self-refuting claim is named alone (hi-t8, r4)


def _hi_t8_channel(ambiguous=frozenset({"h1.2", "h1.5", "h1.6"}), order=None):
    ids = order or [c["claim_id"] for c in HI_T8["claims"]]
    claims = {c["claim_id"]: c for c in HI_T8["claims"]}
    rep = report("history-specialist", "rep-hi-t8-0", [dict(claim_id=cid, claim_text=claims[cid]["claim_text"], claim_role=claims[cid]["claim_role"], materiality=claims[cid]["materiality"]) for cid in ids],
                 text=HI_T8["response_text"])

    def verify_fn(claim, r):
        p = HI_T8_PROBLEMS.get(claim.claim_id)
        status = TranslationStatus.AMBIGUOUS_TRANSLATION if claim.claim_id in ambiguous else TranslationStatus.TRANSLATED
        return outcome(claim, r, p, status) if p is not None else None

    ch = TranslatorChannel(plan(["history-specialist", "dummy-combinator"]), signing_key=KEY, config=CFG, verify_claim_fn=verify_fn)
    m, _, _ = ch.request("router", "history-specialist", HI_T8["question"])
    reply, rc = ch.respond(m.message_id, rep)
    return ch, reply, rc


def _hi_t8_synthesis(ch, conflicts=()):
    claims = [SynthesizedClaim(claim_id=f"s{i}", text=c["text"], certainty=c["certainty"], source_claim_ids=c["source_claim_ids"], transformation=c["transformation"])
              for i, c in enumerate(HI_T8["synthesis"])]
    text = " ".join(c.text for c in claims)
    syn = Synthesis(synthesis_id="syn-hi-t8", request_id="req-hi-t8", task_id="hi-t8", combinator_agent_id="dummy-combinator", source_report_ids=["rep-hi-t8-0"],
                    claims=claims, conflicts=list(conflicts), text=text, text_sha256=sha256_text(text), created_at="2026-10-11T15:00:00Z")
    return ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)


@pytest.mark.parametrize("order", [None, ["h1.5", "h1.4", "h1.3", "h1.2", "h1.1", "h1.6"]])
def test_hi_t8_genuine_delivery_names_h1_5_alone_as_a_warning_under_its_assumed_reading(order):
    ch, reply, rc = _hi_t8_channel(order=order)
    assert reply is not None
    conflict = [f for f in rc.findings if f.code.startswith("INT-CONFLICT")]
    assert [(f.code, f.severity, f.claim_ids) for f in conflict] == [("INT-CONFLICT-005", "warning", ["h1.5"])]
    assert "assumed reading" in conflict[0].message and conflict[0].report_ids == ["rep-hi-t8-0"]
    assert not [f for f in rc.findings if f.severity == "error"], [(f.code, f.message[:80]) for f in rc.findings if f.severity == "error"]
    assert ch.conflicts_seen == []
    rel, sr = _hi_t8_synthesis(ch)  # the faithful synthesis is not asked to disclose a self-refutation
    assert rel is not None and not codes(sr.findings) & {"INT-CONFLICT-001", "INT-CONFLICT-002"}


def test_hi_t8_with_a_fixed_translation_the_self_refutation_is_an_error_but_still_demands_no_disclosure():
    ch, reply, rc = _hi_t8_channel(ambiguous=frozenset())
    assert [(f.code, f.severity, f.claim_ids) for f in rc.findings if f.code.startswith("INT-CONFLICT")] == [("INT-CONFLICT-005", "error", ["h1.5"])]
    _rel, sr = _hi_t8_synthesis(ch)
    assert "INT-CONFLICT-002" not in codes(sr.findings) and "INT-CONFLICT-001" not in codes(sr.findings)


# ------------------------------------------------------------ 3. a figure is one word (word bounds)


def test_decimals_and_thousands_separated_figures_are_one_word_each():
    assert count_words("from 1.9 million to 100,000 men, 63.2% and 1.9m") == 9
    assert count_words("h1.5 e.g. well-known it's") == 6  # an identifier and an abbreviation are unchanged
    assert count_answer_words(HI_T8["response_text"]) == (186, 8)  # hi-t8 has five decimals: measured 191 before
    hi_t7 = "Signed on 28 June 1919, the treaty limited the army to 100,000 men, and by November 1923 one US dollar bought about 4.2 trillion marks."
    assert count_words(hi_t7) == 25


def test_a_200_word_answer_with_decimals_satisfies_no_more_than_200_words():
    sentence = "Unemployment rose from 1.9 to 3.1 million, about 63.2 per cent, and reached 100,000 more by spring. "  # 17 words, 4 figures with separators
    text = (sentence * 11 + "That year was the turning point of the period, as the figures show.").strip()  # 11 x 17 + 13 = 200 words
    assert count_words(text) == 200
    ch = TranslatorChannel(plan(["history-specialist"]), signing_key=KEY, config=CFG)
    m, req, _ = ch.request("router", "history-specialist", HI_T8["question"])
    reply, rc = ch.respond(m.message_id, report("history-specialist", "rep-200", [dict(claim_id="h1", claim_text="Unemployment rose from 1.9 to 3.1 million.", claim_role="evidence")], text=text))
    [c1] = [c for c in rc.constraint_results if c.constraint_id == "c1"]
    assert c1.satisfied is True and "measured 200 words" in c1.detail and "INT-REQ-005" not in codes(rc.findings)


# ------------------------------------------------------------ 4. coverage reads terms without marks and on light stems


EN_P3_ITEM = "How the poem's 'smokeless air' and stillness can be read against that historical context."


def test_coverage_terms_drop_quotation_marks_and_possessives():
    assert _terms(EN_P3_ITEM) == {"against", "air", "can", "context", "historical", "poem", "read", "smokeless", "stillness"}


def test_en_p3_paragraph_addresses_its_item():
    q = ("You have received the History specialist's context paragraph through the hub; it is supplied to you as the document peer:hi-p3. Write one analytical paragraph on "
         "how the poem's 'smokeless air' and stillness can be read against that historical context. Quote exactly from the poem.")
    ch = TranslatorChannel(plan(["english-specialist"], subject="English A: Literature", task_type="analytical_paragraph", request_id="req-p3", task_id="p3"), signing_key=KEY, config=CFG)
    m, req, _ = ch.request("router", "english-specialist", q, [POEM])
    assert [i.text for i in req.items] == [EN_P3_ITEM]
    claims = [dict(claim_id="p1-point", claim_text="Wordsworth presents the City in the morning as clear and still, and the History specialist's account of London in 1802 suggests that this clarity and calm are an exception.", claim_role="point"),
              dict(claim_id="p1-s02", claim_text="The adjective \"smokeless\" defines the air by what it lacks, and the line \"All bright and glittering in the smokeless air\" makes that absence the condition of the brightness.", claim_role="device", materiality="supporting"),
              dict(claim_id="p1-s04", claim_text="Stillness works through personification: the houses \"seem asleep\" and \"all that mighty heart is lying still\".", claim_role="interpretation", materiality="supporting")]
    reply, rc = ch.respond(m.message_id, report("english-specialist", "rep-en-p3", claims, subject="English A: Literature", task_type="analytical_paragraph", request_id="req-p3", task_id="p3", docs=[POEM]))
    assert reply is not None and rc.coverage[0].addressed and "p1-s02" in rc.coverage[0].addressed_by_claim_ids
    assert "INT-REQ-004" not in codes(rc.findings)


# ------------------------------------------------------------ 5. hand-offs and refused relays are not duplicates


def _delivered_physics(ch, rid="rep-1", created_at="2026-10-11T11:00:00Z"):
    m, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    rep = report("physics-specialist", rid, [dict(claim_id="ph-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")], subject="Physics", request_id="req-s", task_id="task-s", created_at=created_at)
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None
    return m, rep, reply


def test_a_specialist_handing_its_delivered_report_to_the_combinator_is_not_a_duplicate():
    ch = TranslatorChannel(plan(["physics-specialist", "combinator"], subject="Physics", request_id="req-s", task_id="task-s"), signing_key=KEY, config=CFG)
    _m, rep, _reply = _delivered_physics(ch)
    rel, rr = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, rep)
    assert rel is not None and "INT-ENV-001" not in codes(rr.findings), [f.message for f in rr.findings]
    again, ra = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, rep)  # the same hand-off twice IS a duplicate
    assert again is not None and "INT-ENV-001" in codes(ra.findings)


def test_the_same_report_relayed_again_to_the_router_is_a_duplicate_whatever_id_names_the_router():
    ch = TranslatorChannel(plan(["physics-specialist", "combinator"], subject="Physics", request_id="req-s", task_id="task-s"), signing_key=KEY, config=CFG)
    _m, rep, _reply = _delivered_physics(ch)
    rel, rr = ch.relay("physics-specialist", AgentRole.SPECIALIST, "router", AgentRole.ROUTER, rep)
    assert "INT-ENV-001" in codes(rr.findings)


@pytest.mark.parametrize("created_at,differs", [("2026-10-11T11:00:00Z", False), ("2026-10-11T11:30:00Z", True)])
def test_a_redelivery_to_the_router_says_only_the_timestamp_differs_only_when_it_does(created_at, differs):
    ch = TranslatorChannel(plan(["physics-specialist"], subject="Physics", request_id="req-s", task_id="task-s"), signing_key=KEY, config=CFG)
    m, rep, _ = _delivered_physics(ch)
    again = rep.model_copy(update={"created_at": created_at})
    _r, rc = ch.respond(m.message_id, again)
    dup = [f for f in rc.findings if f.code == "INT-ENV-001"]
    assert len(dup) == 1 and ("only the timestamp differs" in dup[0].message) is differs


def test_a_refused_forward_is_not_recorded_as_transmitted():
    ch = TranslatorChannel(plan(["physics-specialist", "maths-specialist"], subject="Physics", request_id="req-s", task_id="task-s"), signing_key=KEY, config=CFG)
    _m, rep, reply = _delivered_physics(ch)
    bad, br = ch.relay("router", AgentRole.ROUTER, "maths-specialist", AgentRole.SPECIALIST, rep, in_reply_to="no-such-message")
    assert bad is None and "INT-ENV-003" in codes(br.findings)
    good, gr = ch.relay("router", AgentRole.ROUTER, "maths-specialist", AgentRole.SPECIALIST, rep, in_reply_to=reply.message_id)
    assert good is not None and "INT-ENV-001" not in codes(gr.findings)


# ------------------------------------------------------------ 6. a colleague's figure misreported in a paraphrase (INT-REQ-014)


PEER = SuppliedText(document_id="peer:hi-p3", title="history-specialist report rep-hi-p3-0 relayed through the hub", author="history-specialist",
                    text="London in 1802 was the largest city in Europe, with close to a million inhabitants at the first national census of 1801.")


@pytest.mark.parametrize("sentence,flagged", [
    ("The scale of that heart matters, because the History specialist gives close to two million inhabitants and calls London \"the largest city in Europe\".", True),
    ("The scale of that heart matters, because the History specialist gives close to a million inhabitants and calls London \"the largest city in Europe\".", False),
    ("The poem was printed in 1807, which bears out the History specialist's claim that London was \"the largest city in Europe\".", False),
])
def test_a_figure_credited_to_the_peer_that_the_peer_never_gave_is_named(sentence, flagged):
    ch = TranslatorChannel(plan(["english-specialist"], subject="English A: Literature", task_type="analytical_paragraph", request_id="req-p3", task_id="p3"), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "english-specialist", "Write one analytical paragraph on the poem's stillness against the historical context.", [POEM, PEER])
    rep = report("english-specialist", "rep-en", [dict(claim_id="p1-s05", claim_text=sentence, claim_role="interpretation")], subject="English A: Literature", task_type="analytical_paragraph",
                 request_id="req-p3", task_id="p3", docs=[POEM, PEER])
    _reply, rc = ch.respond(m.message_id, rep)
    f = [x for x in rc.findings if x.code == "INT-REQ-014"]
    assert bool(f) is flagged
    if flagged:
        assert f[0].severity == "warning" and "'two million'" in f[0].message and f[0].claim_ids == ["p1-s05"] and f[0].document_ids == ["peer:hi-p3"]


# ------------------------------------------------------------ 7. a synthesis that changes what its sources said


def _p3_synthesis_channel():
    ch = TranslatorChannel(plan(["english-specialist", "dummy-combinator"], subject="English A: Literature", task_type="analytical_paragraph", request_id="req-p3", task_id="p3"), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "english-specialist", "Write one analytical paragraph on how the poem presents the city at rest.", [POEM])
    claims = [dict(claim_id="p1-point", claim_text="Wordsworth presents the city as alive and at rest at once.", claim_role="point"),
              dict(claim_id="p1-s01", claim_text="The city \"doth, like a garment, wear\" the beauty of the morning, so the verb makes it an agent.", claim_role="interpretation")]
    reply, _ = ch.respond(m.message_id, report("english-specialist", "rep-en", claims, subject="English A: Literature", task_type="analytical_paragraph", request_id="req-p3", task_id="p3", docs=[POEM]))
    assert reply is not None
    return ch


def _relay(ch, text, transformation="paraphrased"):
    claims = [SynthesizedClaim(claim_id="s0", text="Wordsworth presents the city as alive and at rest at once.", certainty="probable", source_claim_ids=["p1-point"], transformation="carried"),
              SynthesizedClaim(claim_id="s1", text=text, certainty="probable", source_claim_ids=["p1-s01"], transformation=transformation)]
    body = " ".join(c.text for c in claims)
    syn = Synthesis(synthesis_id="syn-p3", request_id="req-p3", task_id="p3", combinator_agent_id="dummy-combinator", source_report_ids=["rep-en"], claims=claims, text=body,
                    text_sha256=sha256_text(body), created_at="2026-10-11T15:00:00Z")
    return ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)


def test_an_altered_quotation_in_a_relayed_synthesis_is_an_error_and_an_unchecked_paraphrase_is_stated():
    rel, rr = _relay(_p3_synthesis_channel(), "The city \"doth, like a cloak, wear\" the beauty of the morning, so the verb makes it an agent.")
    assert rel is not None
    [q] = [f for f in rr.findings if f.code == "INT-LEDGER-025"]
    assert q.severity == "error" and "doth, like a cloak, wear" in q.message and q.claim_ids == ["s1", "p1-s01"]
    [s12] = [f for f in rr.findings if f.code == "INT-SYNTH-012"]
    assert s12.severity == "warning" and s12.claim_ids[0] == "s1" and "NOT formally checked on this channel" in s12.message
    rel2, rr2 = _relay(_p3_synthesis_channel(), "The city \"doth, like a garment, wear\" the beauty of the morning, so the verb makes it an agent.", transformation="carried")
    assert rel2 is not None and not codes(rr2.findings) & {"INT-LEDGER-025", "INT-SYNTH-012"}
