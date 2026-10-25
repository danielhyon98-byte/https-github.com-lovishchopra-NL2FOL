"""Channel behaviour found wanting by the round-3 arena overseers: note claims counting as
coverage and an all-notes answer delivered as if it addressed the request, an echo of the
request superseding the agent's genuine report, INT-HANDOFF-014 naming never-located excerpts
as stale, a re-parsed retransmission refused as a forged payload, a claim of another report
surfacing as a bare value error, an inflected restatement escaping INT-REQ-011, claims folded
beyond the contract limit crossing unchecked, a branch pack calling an excerpt invented after
the hub said its words occur, and the verdict cue list the History parser could not import."""
from __future__ import annotations

import re

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus, VERDICT_CUES
from epinoic_logic.channel.bus import _VERDICT_CUE
from epinoic_logic.channel.cues import verdict_cue_regex
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText,
    TranslationResult, TranslationStatus, sha256_text,
)

KEY = b"round3-channel-test-key-0123456789"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK = "task-r3"
POEM_TEXT = ("My name is Ozymandias, King of Kings;\nLook on my Works, ye Mighty, and despair!\nNothing beside remains. Round the decay\n"
             "Of that colossal Wreck, boundless and bare\nThe lone and level sands stretch far away.")
POEM = SuppliedText(document_id="doc-poem", title="Sonnet", text=POEM_TEXT)
HISTORY = ("The sonnet was printed in January 1818. Wheat had cost 80 shillings a quarter in 1815. Britain after Waterloo, fought on 18 June 1815, "
           "was a country of postwar distress. Dates other than the poem's own are from memory; check your notes.")


def plan(agents: list[str], subject: str = "Physics", task_type: str = "short_answer", request_id: str = "req-s", **over) -> WorkPlan:
    base = dict(plan_id="plan-r3", request_id=request_id, task_id=TASK, subject=subject, task_type=task_type, selected_agent_ids=agents)
    base.update(over)
    return WorkPlan(**base)


def two_subject_plan(**over) -> WorkPlan:
    return plan(["history-specialist", "english-specialist", "dummy-combinator"], subject="English A: Literature", task_type="analytical_paragraph", request_id="req-r3",
                allowed_document_ids=["doc-poem", "peer:hi"], agent_subjects={"history-specialist": "History"}, **over)


def report(agent: str, rid: str, text: str, claims: list[dict], subject: str = "Physics", task_type: str = "short_answer", docs=(), request_id: str = "req-s",
           created_at: str = "2026-10-11T11:00:00Z", unresolved: list[str] = ()) -> SpecialistReport:
    return SpecialistReport(report_id=rid, request_id=request_id, task_id=TASK, agent_id=agent, subject=subject, task_type=task_type, original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=list(docs), created_at=created_at, unresolved_issues=list(unresolved),
                            claims=[ClaimRecord(request_id=request_id, task_id=TASK, report_id=rid, agent_id=agent, subject=subject, task_type=task_type, **c) for c in claims])


def history_report(rid: str, text: str = HISTORY, docs=()) -> SpecialistReport:
    claims = [dict(claim_id="h1", claim_text="The sonnet was printed in January 1818.", claim_role="evidence"),
              dict(claim_id="h2", claim_text="Wheat had cost 80 shillings a quarter in 1815.", claim_role="evidence"),
              dict(claim_id="h3", claim_text="Dates other than the poem's own are from memory; check your notes.", claim_role="other", materiality="supporting")]
    return report("history-specialist", rid, text, claims, subject="History", task_type="analytical_paragraph", request_id="req-r3", docs=docs)


def speed_problem(claim_id: str, value: str, request_id: str = "req-s") -> Problem:
    V = lambda n: {"op": "var", "name": n}
    R = lambda v: {"op": "real", "value": str(v)}
    return Problem.model_validate({"problem_id": f"p-{claim_id}", "request_id": request_id, "claim_id": claim_id, "query": "entailment",
                                   "symbols": [{"name": "speed", "sort": "Real", "meaning": "the speed in m/s"}],
                                   "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}, "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}}})


def outcome(claim: ClaimRecord, rep: SpecialistReport, problem: Problem) -> ClaimVerificationOutcome:
    res = verify(problem, CFG, signing_key=KEY, key_id="t")
    tr = TranslationResult(translation_id=f"tr-{rep.report_id}-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=rep.report_id, status=TranslationStatus.TRANSLATED,
                           claim_text_sha256=sha256_text(claim.claim_text), eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="t"),
                           problem=problem, translator_version="t", policy_version="t", created_at="2026-10-11T11:00:00Z")
    return ClaimVerificationOutcome(outcome_id=f"o-{rep.report_id}-{claim.claim_id}", request_id=claim.request_id, report_id=rep.report_id, claim_id=claim.claim_id, translation=tr, verification=res,
                                    display_status=res.status, summary="stub", created_at="2026-10-11T11:00:00Z")


def codes(findings) -> set[str]:
    return {f.code for f in findings}


# ------------------------------------------------------------ 1. notes never count as an answer (INT-REQ-012)


def test_an_all_notes_answer_addresses_nothing_and_is_named():
    ch = TranslatorChannel(plan(["specialist"]), signing_key=KEY, config=CFG)
    ask = "Explain the causes of the banking crisis of 1931 and assess which cause mattered most."
    m, _, _ = ch.request("router", "specialist", ask)
    notes = "The causes of the banking crisis of 1931 are from memory; the assessment of which cause mattered most has been verified."
    rep = report("specialist", "rep-notes", notes, [dict(claim_id="n-1", claim_text="The causes of the banking crisis of 1931 are from memory.", claim_role="other", materiality="supporting"),
                                                      dict(claim_id="n-2", claim_text="The assessment of which cause mattered most has been verified.", claim_role="other", materiality="supporting")])
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # a content finding travels with the report
    no_answer = [f for f in rc.findings if f.code == "INT-REQ-012"]
    assert no_answer and no_answer[0].severity == "error" and "none of its 2 claim(s) is material" in no_answer[0].message and set(no_answer[0].claim_ids) == {"n-1", "n-2"}
    assert rc.coverage and all(not c.addressed and not c.addressed_by_claim_ids for c in rc.coverage)  # the notes share every word with the items and still address none
    assert any(f.code == "INT-REQ-004" for f in rc.findings) and "INT-REQ-012" in rc.summary


def test_a_note_claim_never_addresses_an_item_beside_material_claims():
    ch = TranslatorChannel(plan(["specialist"]), signing_key=KEY, config=CFG)
    m, req, _ = ch.request("router", "specialist", "What is the speed? Justify the unit chosen.")
    assert [i.item_id for i in req.items] == ["i1", "i2"]
    rep = report("specialist", "rep-mixed", "The speed is 15 m/s. The unit chosen is justified from memory.",
                 [dict(claim_id="q-1", claim_text="The speed is 15 m/s.", claim_role="quantitative"),
                  dict(claim_id="q-2", claim_text="The unit chosen is justified from memory.", claim_role="other", materiality="supporting")])
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None and not [f for f in rc.findings if f.code == "INT-REQ-012"]
    by_item = {c.item_id: c for c in rc.coverage}
    assert by_item["i1"].addressed and by_item["i1"].addressed_by_claim_ids == ["q-1"]
    assert not by_item["i2"].addressed and by_item["i2"].addressed_by_claim_ids == []  # the note that shares the item's words does not count


def test_zero_answer_words_is_named_even_with_a_material_claim_recorded():
    ch = TranslatorChannel(plan(["specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "specialist", "What is the speed?")
    rep = report("specialist", "rep-cert", "VERIFIED: all claims checked and confirmed.", [dict(claim_id="c-1", claim_text="VERIFIED: all claims checked and confirmed.", claim_role="quantitative")])
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None
    f = [x for x in rc.findings if x.code == "INT-REQ-012"]
    assert f and "0 words" in f[0].message and "6 words of note or meta-text" in f[0].message
    assert rc.coverage and not any(c.addressed for c in rc.coverage)


# ------------------------------------------------------------ 3. an echo never supersedes the genuine report


def test_an_echo_of_the_request_never_supersedes_the_genuine_report_or_its_pool():
    problems = {("rep-1", "a-1"): speed_problem("a-1", "15")}
    ch = TranslatorChannel(plan(["physics-specialist", "combinator"]), signing_key=KEY, config=CFG,
                           verify_claim_fn=lambda c, r: outcome(c, r, problems[(r.report_id, c.claim_id)]) if (r.report_id, c.claim_id) in problems else None)
    ask = "Explain the speed of the trolley and assess which measurement mattered most."
    m1, _, _ = ch.request("router", "physics-specialist", ask)
    genuine = report("physics-specialist", "rep-1", "The speed is 15 m/s; the timing mattered most.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative"), dict(claim_id="a-2", claim_text="The timing mattered most.", claim_role="judgement")])
    r1, rc1 = ch.respond(m1.message_id, genuine)
    assert r1 is not None and "a-1" in ch.formalized
    # Rewritten to the stricter rule of repair round 3 (V3-H2-STEM-MISSES): the report links no claim to another, so its
    # ranking judgement 'The timing mattered most.' is a bare assertion (ARG-BARE-001) on arrival, carried on the relay as
    # its one finding. The relay was ACCEPTED with no finding before; every other assertion is the earlier one.
    assert [(f.code, f.claim_ids) for f in rc1.findings] == [("INT-ARG-001", ["a-2"])] and "ARG-BARE-001" in rc1.findings[0].message
    fwd, fr = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, genuine, in_reply_to=r1.message_id)
    assert fwd is not None and fr.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    assert [(f.code, f.severity, f.claim_ids) for f in fr.findings] == [("INT-HIST-001", "warning", ["a-2"])] and "INT-ARG-001" in fr.findings[0].message
    m2, _, _ = ch.request("router", "physics-specialist", ask)
    problems[("rep-2", "a-1")] = speed_problem("a-1", "99")  # an echo whose claims get formalized must still not enter the pool
    echo = report("physics-specialist", "rep-2", ask, [dict(claim_id="a-1", claim_text=ask, claim_role="point"), dict(claim_id="a-2", claim_text=ask, claim_role="point")])
    r2, rc2 = ch.respond(m2.message_id, echo)
    assert r2 is not None and "INT-REQ-011" in codes(rc2.findings)
    assert "INT-HANDOFF-009" not in codes(rc2.findings) and "INT-HANDOFF-014" not in codes(rc2.findings)
    assert ch.superseded == {} and ch.formalized["a-1"].conclusion.expr.right.value == "15" and ch.formalized_by["a-1"] == ("physics-specialist", "rep-1")
    assert rc2.outcomes and rc2.outcomes[0].claim_id == "a-1"  # the echo's outcome is delivered for the record, not pooled
    fwd2, fr2 = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, genuine, in_reply_to=r1.message_id)
    assert fwd2 is not None and "INT-HANDOFF-014" not in codes(fr2.findings)  # the genuine report is still the current one


def test_a_report_of_notes_only_never_supersedes_and_a_revision_names_what_changed():
    ch = TranslatorChannel(plan(["physics-specialist"]), signing_key=KEY, config=CFG)
    m1, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    genuine = report("physics-specialist", "rep-1", "The speed is 15 m/s. The time is 4 s.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative"), dict(claim_id="a-2", claim_text="The time is 4 s.", claim_role="quantitative")])
    ch.respond(m1.message_id, genuine)
    m2, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    notes = report("physics-specialist", "rep-notes", "Figures are from memory; verify them.", [dict(claim_id="a-1", claim_text="Figures are from memory; verify them.", claim_role="other", materiality="supporting")])
    _, rc = ch.respond(m2.message_id, notes)
    assert "INT-REQ-012" in codes(rc.findings) and "INT-HANDOFF-009" not in codes(rc.findings) and ch.superseded == {}
    m3, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    revised = report("physics-specialist", "rep-2", "The speed is 16 m/s. The time is 4 s.", [dict(claim_id="a-1", claim_text="The speed is 16 m/s.", claim_role="quantitative"), dict(claim_id="a-2", claim_text="The time is 4 s.", claim_role="quantitative")])
    _, rc3 = ch.respond(m3.message_id, revised)
    sup = [f for f in rc3.findings if f.code == "INT-HANDOFF-009"]
    assert sup and "re-stating claims ['a-2'] (same text)" in sup[0].message and "revising claims ['a-1'] (same id, changed text)" in sup[0].message
    assert set(sup[0].claim_ids) == {"a-1", "a-2"} and ch.superseded["rep-1"] == "rep-2" and "rep-1" in sup[0].report_ids
    m4, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    renumbered = report("physics-specialist", "rep-3", "The time is 4 s. The speed is 16 m/s.", [dict(claim_id="b-1", claim_text="The time is 4 s.", claim_role="quantitative"), dict(claim_id="b-2", claim_text="The speed is 16 m/s.", claim_role="quantitative")])
    _, rc4 = ch.respond(m4.message_id, renumbered)
    sup4 = [f for f in rc4.findings if f.code == "INT-HANDOFF-009"]
    assert sup4 and "re-stating claims ['b-1', 'b-2'] (same text)" in sup4[0].message and "revising" not in sup4[0].message  # positional ids shifted; the texts decide
    assert set(sup4[0].report_ids) == {"rep-3", "rep-1", "rep-2"}


# ------------------------------------------------------------ 4. INT-HANDOFF-014 wording and deduplicated ids


def test_in_circulation_tells_a_stale_excerpt_from_one_never_located_and_dedupes_ids():
    ch = TranslatorChannel(two_subject_plan(), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "history-specialist", "Outline the context.")
    old = history_report("rep-hi-1")
    r1, _ = ch.respond(m.message_id, old)
    assert r1 is not None
    peer = SuppliedText(document_id="peer:hi", title="History report relayed through the hub", text=old.original_response)
    en_claims = [dict(claim_id="e-1", claim_text='The sonnet "was printed in January 1818".', claim_role="evidence", source_refs=[SourceRef(document_id="peer:hi", excerpt="was printed in January 1818")]),
                 dict(claim_id="e-2", claim_text='The History specialist says the poem "sold in its thousands".', claim_role="evidence", source_refs=[SourceRef(document_id="peer:hi", excerpt="sold in its thousands")]),
                 dict(claim_id="e-3", claim_text='Wheat "had cost 80 shillings a quarter".', claim_role="evidence", source_refs=[SourceRef(document_id="peer:hi", excerpt="had cost 80 shillings a quarter")])]
    for rid in ("rep-en-1", "rep-en-2"):  # two reports of the quoting agent cite the same claim ids
        me, _, _ = ch.request("router", "english-specialist", "Write one analytical paragraph on power in the poem.", [POEM, peer])
        en = report("english-specialist", rid, "The sonnet was printed in January 1818; the poem sold in its thousands; wheat had cost 80 shillings a quarter.", en_claims,
                    subject="English A: Literature", task_type="analytical_paragraph", docs=(POEM, peer), request_id="req-r3")
        reply, rc = ch.respond(me.message_id, en)
        assert reply is not None and [f.claim_ids for f in rc.findings if f.code == "INT-REQ-003"] == [["e-2"]]  # the invented excerpt is named on arrival
    m2, _, _ = ch.request("router", "history-specialist", "Outline the context.")
    _, rc2 = ch.respond(m2.message_id, history_report("rep-hi-2", HISTORY.replace("January 1818", "January 1819")))
    circ = [f for f in rc2.findings if f.code == "INT-HANDOFF-014"]
    assert len(circ) == 1
    msg = circ[0].message
    assert "excerpts cited by claims ['e-1'] occurred in the superseded report and no longer occur in the current report" in msg
    assert "excerpts cited by claims ['e-2'] were never located in the superseded report either" in msg
    assert "e-3" not in msg  # still occurs: not named
    assert circ[0].claim_ids == ["e-1", "e-2"] and len(circ[0].report_ids) == len(set(circ[0].report_ids))
    assert circ[0].report_ids == ["rep-hi-1", "rep-hi-2", "rep-en-1", "rep-en-2"] and circ[0].document_ids == ["peer:hi"]


# ------------------------------------------------------------ 5. identical content under the same report id


def test_identical_content_under_the_same_report_id_is_a_duplicate_delivery_not_a_forgery():
    ch = TranslatorChannel(plan(["specialist"]), signing_key=KEY, config=CFG)
    claims = [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")]
    m1, _, _ = ch.request("router", "specialist", "What is the speed?")
    r1, _ = ch.respond(m1.message_id, report("specialist", "rep-a", "The speed is 15 m/s.", claims, created_at="2026-10-11T11:00:00Z"))
    assert r1 is not None
    m2, _, _ = ch.request("router", "specialist", "What is the speed?")
    r2, rc2 = ch.respond(m2.message_id, report("specialist", "rep-a", "The speed is 15 m/s.", claims, created_at="2026-10-11T11:05:00Z"))  # re-parsed: new timestamp, same answer
    assert r2 is not None and rc2.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and not rc2.errors
    dup = [f for f in rc2.findings if f.code == "INT-ENV-001"]
    assert dup and "identical content" in dup[0].message and "only the timestamp differs" in dup[0].message
    assert ch.transmitted_reports["rep-a"].created_at == "2026-10-11T11:00:00Z"  # the first delivery is kept
    m3, _, _ = ch.request("router", "specialist", "What is the speed?")
    r3, rc3 = ch.respond(m3.message_id, report("specialist", "rep-a", "The speed is 16 m/s.", [dict(claim_id="a-1", claim_text="The speed is 16 m/s.", claim_role="quantitative")], created_at="2026-10-11T11:05:00Z"))
    assert r3 is None and rc3.status is TransmissionStatus.REJECTED
    reuse = [f for f in rc3.errors if f.code == "INT-HANDOFF-015"]
    assert reuse and "'claims'" in reuse[0].message and "'original_response'" in reuse[0].message and "'response_sha256'" in reuse[0].message and "created_at" not in reuse[0].message
    m4, _, _ = ch.request("router", "specialist", "What is the speed?")
    r4, rc4 = ch.respond(m4.message_id, report("specialist", "rep-a", "The speed is 15 m/s.", claims + [dict(claim_id="a-2", claim_text="The speed is 15 m/s.", claim_role="quantitative")]))
    assert r4 is None and any(f.code == "INT-HANDOFF-015" and "'claims'" in f.message for f in rc4.errors)  # same text, different claims


def test_a_raw_text_retransmission_under_the_same_report_id_is_delivered_as_a_duplicate():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan(["history-specialist"], subject="History", task_type="essay"))
    text = "Enrolment rose from 200 to 260 students in 1920, an increase of 30 per cent."
    m1, _, _ = hub.dispatch(TASK, "history-specialist", "Describe the growth of enrolment.")
    r1, _ = hub.receive(TASK, m1.message_id, text, agent_id="history-specialist", report_id="rep-raw")
    m2, _, _ = hub.dispatch(TASK, "history-specialist", "Describe the growth of enrolment.")
    r2, rc2 = hub.receive(TASK, m2.message_id, text, agent_id="history-specialist", report_id="rep-raw")
    assert r1 is not None and r2 is not None and "INT-HANDOFF-015" not in codes(rc2.findings) and "INT-ENV-001" in codes(rc2.findings)


# ------------------------------------------------------------ 6. a claim of another report is a provenance fault


def test_a_claim_carrying_another_reports_provenance_is_int_handoff_012_not_a_value_error():
    ch = TranslatorChannel(plan(["specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "specialist", "What is the speed?")
    good = report("specialist", "rep-a", "The speed is 15 m/s. The time is 4 s.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")])
    foreign = ClaimRecord(request_id="req-other", task_id=TASK, report_id="rep-other", agent_id="specialist", subject="Physics", task_type="short_answer", claim_id="x-9", claim_text="The time is 4 s.", claim_role="quantitative")
    smuggled = good.model_copy(update={"claims": [*good.claims, foreign]})  # built around validation
    reply, rc = ch.respond(m.message_id, smuggled)
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    prov = [f for f in rc.errors if f.code == "INT-HANDOFF-012"]
    assert len(prov) == 1 and prov[0].claim_ids == ["x-9"] and "['report_id', 'request_id']" in prov[0].message and "'rep-other'" in prov[0].message and "'req-other'" in prov[0].message
    assert "INT-REQ-009" not in codes(rc.findings)
    assert "rep-a" not in ch.transmitted_reports
    fwd, fr = ch.relay("specialist", AgentRole.SPECIALIST, "router", AgentRole.ROUTER, smuggled)
    assert fwd is None and any(f.code == "INT-HANDOFF-012" and f.claim_ids == ["x-9"] for f in fr.errors) and "INT-REQ-009" not in codes(fr.findings)
    broken = good.model_copy(update={"response_sha256": "0" * 64})
    _, rcb = ch.respond(m.message_id, broken)
    assert "INT-REQ-009" in codes(rcb.findings)  # a genuine contract fault is still INT-REQ-009


# ------------------------------------------------------------ 7. an inflected restatement quoting the request


def test_an_inflected_restatement_quoting_the_requests_words_is_an_echo():
    ch = TranslatorChannel(two_subject_plan(), signing_key=KEY, config=CFG)
    ask = "Analyse how the poet presents the ruin of power in the sonnet. Quote from the poem."
    m, _, _ = ch.request("router", "english-specialist", ask, [POEM])
    near = 'This paragraph analyses how the poet presented "the ruin of power" in the sonnet, with quotations from the poem.'
    rep = report("english-specialist", "rep-near", near, [dict(claim_id="e-1", claim_text=near, claim_role="point")], subject="English A: Literature", task_type="analytical_paragraph", docs=(POEM,), request_id="req-r3")
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None
    echoed = [f for f in rc.findings if f.code == "INT-REQ-011"]
    assert echoed and "light stems" in echoed[0].message and "quotes the request's own words" in echoed[0].message and "the ruin of power" in echoed[0].message
    assert rc.coverage and not any(c.addressed for c in rc.coverage)
    m2, _, _ = ch.request("router", "english-specialist", ask, [POEM])
    answer = 'The boast "King of Kings" is answered by the ruin: power presented as a wreck, the sonnet analysing its collapse through the pedestal.'
    rep2 = report("english-specialist", "rep-ans", answer, [dict(claim_id="e-2", claim_text=answer, claim_role="point", source_refs=[SourceRef(document_id="doc-poem", excerpt="King of Kings")])],
                  subject="English A: Literature", task_type="analytical_paragraph", docs=(POEM,), request_id="req-r3")
    _, rc2 = ch.respond(m2.message_id, rep2)
    assert "INT-REQ-011" not in codes(rc2.findings)  # a genuine answer that quotes the poem is not an echo


# ------------------------------------------------------------ 9. claims folded beyond the limit never cross unchecked


def test_folded_claims_are_named_with_their_unchecked_quotations():
    ch = TranslatorChannel(two_subject_plan(), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "english-specialist", "Write one analytical paragraph on power in the poem.", [POEM])
    tail_text = 'The boast "King of Kings" is hollow. The narrator insists that "the river carried every secret of the town", which seals the point.'
    claims = [dict(claim_id="p1-point", claim_text="The sonnet mocks power.", claim_role="point"),
              dict(claim_id="p-tail", claim_text=tail_text, claim_role="other", materiality="supporting", certainty="possible")]
    issue = "600 claims beyond the report's claim limit (512) were merged into claim p-tail and were not individually roled or checked"
    rep = report("english-specialist", "rep-fold", "The sonnet mocks power. " + tail_text, claims, subject="English A: Literature", task_type="analytical_paragraph", docs=(POEM,), request_id="req-r3", unresolved=[issue])
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None
    fold = [f for f in rc.findings if f.code == "INT-REQ-013"]
    assert len(fold) == 1 and fold[0].severity == "warning" and fold[0].claim_ids == ["p-tail"]
    assert "merged 600 claims beyond the claim limit (512)" in fold[0].message and "2 quotation(s) in the merged text were not checked" in fold[0].message
    assert "of which 1 occur in no supplied text" in fold[0].message and "the river carried every secret of the town" in fold[0].message and "King of Kings" not in fold[0].message.split("of which")[1]
    plain = report("english-specialist", "rep-plain", "The sonnet mocks power.", claims[:1], subject="English A: Literature", task_type="analytical_paragraph", docs=(POEM,), request_id="req-r3")
    m2, _, _ = ch.request("router", "english-specialist", "Write one analytical paragraph on power in the poem.", [POEM])
    _, rc2 = ch.respond(m2.message_id, plain)
    assert "INT-REQ-013" not in codes(rc2.findings)


def test_an_invented_quotation_beyond_the_claim_limit_does_not_cross_silently():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(two_subject_plan())
    m, _, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem. Quote from the poem.", [POEM])
    body = " ".join(f"The ruin answers the boast in sentence {i} of the paragraph." for i in range(530))  # beyond the 512-claim limit
    text = body + ' The narrator also insists that "the river carried every secret of the town", which seals the point.'
    reply, rc = hub.receive(TASK, m.message_id, text, agent_id="english-specialist", report_id="rep-600")
    assert reply is not None and len(reply.payload["claims"]) <= 512
    # Either the parser kept the quotation as a claim of its own and the hub refuted it (INT-REQ-003), or it fell into the
    # folded tail and the hub names it among the unchecked quotations that occur in no supplied text (INT-REQ-013).
    refuted = [f for f in rc.findings if f.code == "INT-REQ-003"]
    folded = [f for f in rc.findings if f.code == "INT-REQ-013"]
    assert folded and "merged" in folded[0].message and folded[0].claim_ids == ["p-tail"]
    assert refuted or "the river carried every secret of the town" in folded[0].message, [f.message[:200] for f in rc.findings]


# ------------------------------------------------------------ branch -SRC-001 errors for an excerpt the hub located


def test_no_branch_pack_calls_an_excerpt_invented_after_the_hub_said_its_words_occur():
    ch = TranslatorChannel(two_subject_plan(), signing_key=KEY, config=CFG)
    peer_text = 'The ruin frames the boast: "Look on my Works, ye Mighty, and despair" answers the pedestal.'
    peer = SuppliedText(document_id="peer:hi", title="English report relayed through the hub", text=peer_text)
    m, _, _ = ch.request("router", "history-specialist", "Outline the context of the poem.", [POEM, peer])
    rep = report("history-specialist", "rep-hi-form", 'The English specialist notes that the command to "look on my Works, ye Mighty, and despair" rings hollow. The sonnet was printed in January 1818.',
                 [dict(claim_id="h-1", claim_text='The English specialist notes that the command to "look on my Works, ye Mighty, and despair" rings hollow.', claim_role="perspective",
                       source_refs=[SourceRef(document_id="peer:hi", excerpt="look on my Works, ye Mighty, and despair")]),
                  dict(claim_id="h-2", claim_text="The sonnet was printed in January 1818.", claim_role="evidence")],
                 subject="History", task_type="analytical_paragraph", docs=(POEM, peer), request_id="req-r3")
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None
    form = [f for f in rc.findings if f.code == "INT-REQ-010"]
    assert form and form[0].claim_ids == ["h-1"] and "initial capital" in form[0].message
    assert "INT-REQ-003" not in codes(rc.findings) and "INT-SUBJ-003" not in codes(rc.findings)
    assert not [sf for sf in rc.structural_findings if sf.code.endswith("-SRC-001") and sf.severity == "error" and "h-1" in sf.claim_ids], [sf.model_dump() for sf in rc.structural_findings]
    assert not [f for f in rc.findings if f.severity == "error"], [f.message for f in rc.errors]
    assert not [sf for sf in rc.structural_findings if sf.severity == "error"], [sf.model_dump() for sf in rc.structural_findings]


# ------------------------------------------------------------ 10. the shared verdict cue list


def test_verdict_cues_are_shared_and_cover_the_criteria_wordings():
    from epinoic_logic.channel.cues import VERDICT_CUES as direct
    assert direct is VERDICT_CUES and isinstance(VERDICT_CUES, tuple) and all(c == c.lower() for c in VERDICT_CUES)
    assert {"on balance", "mattered most", "matters most", "weighed by", "by the criteria", "by the criterion", "outweigh"} <= set(VERDICT_CUES)
    assert re.compile(r"\b(" + verdict_cue_regex() + r")\b", re.IGNORECASE).pattern == _VERDICT_CUE.pattern
    for sentence in ("The redistribution mattered most, by the criteria of directness, reach and permanence.",
                     "Weighed by necessity, Khrushchev's retreat was the answer.",
                     "The famine outweighed the plenum.", "This holds for the 1959 harvest."):
        assert _VERDICT_CUE.search(sentence), sentence
    assert not _VERDICT_CUE.search("The Depression was responsible for the rise of the party.")


def test_a_judgement_by_the_criteria_satisfies_a_level_three_term():
    ch = TranslatorChannel(plan(["specialist"]), signing_key=KEY, config=CFG)
    ask = "Evaluate which effect of the redistribution mattered most."
    m, req, _ = ch.request("router", "specialist", ask)
    assert req.items[0].level == 3
    text = "The redistribution reached most families. The redistribution mattered most, by the criteria of directness, reach and permanence."
    rep = report("specialist", "rep-crit", text, [dict(claim_id="j-1", claim_text="The redistribution reached most families.", claim_role="evidence"),
                                                   dict(claim_id="j-2", claim_text="The redistribution mattered most, by the criteria of directness, reach and permanence.", claim_role="analysis")])
    _, rc = ch.respond(m.message_id, rep)
    assert "INT-REQ-008" not in codes(rc.findings), [f.message for f in rc.findings]
    weighed = report("specialist", "rep-weigh", "Weighed by necessity, the retreat was the answer.", [dict(claim_id="j-3", claim_text="Weighed by necessity, the retreat was the answer.", claim_role="analysis")])
    m2, _, _ = ch.request("router", "specialist", ask)
    _, rc2 = ch.respond(m2.message_id, weighed)
    assert "INT-REQ-008" not in codes(rc2.findings)
    bare = report("specialist", "rep-bare", "The redistribution reached most families.", [dict(claim_id="j-4", claim_text="The redistribution reached most families.", claim_role="evidence")])
    m3, _, _ = ch.request("router", "specialist", ask)
    _, rc3 = ch.respond(m3.message_id, bare)
    assert "INT-REQ-008" in codes(rc3.findings)


# ------------------------------------------------------------ an inline from-memory label is not a note block


def test_a_sentence_with_an_inline_from_memory_label_is_answer_not_note():
    from epinoic_logic.channel import count_answer_words, count_paragraphs
    dated = 'In July 1791 "Church and King" crowds burned the house of the dissenter Joseph Priestley (from memory).'
    answer, notes = count_answer_words(dated)
    assert answer >= 14 and notes == 2 and count_paragraphs(dated) == 1  # the substance counts; only the label is meta-text
    assert count_answer_words("Dates and figures are from memory; verify them against your notes.") == (0, 11)
    assert count_answer_words("From memory, the mark stood at about 4.2 to the dollar in 1914.")[0] >= 10
    ch = TranslatorChannel(plan(["history-specialist"], subject="History"), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "history-specialist", "Outline the context in no more than 220 words.")
    rep = report("history-specialist", "rep-inline", dated, [dict(claim_id="h-1", claim_text=dated, claim_role="evidence", assumptions=["from memory"])], subject="History")
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None and "INT-REQ-012" not in codes(rc.findings)  # a dated sentence with its label inline is an answer
    words = next(c for c in rc.constraint_results if c.constraint_id == "c1")
    assert words.satisfied is True and "2 words of note or meta-text" in words.detail
