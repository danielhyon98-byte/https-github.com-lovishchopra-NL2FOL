"""Channel behaviour found wanting by the arena overseer: raw text the adapter cannot
turn into a report is REJECTED with a receipt (never an exception out of the hub), the
delivered payload always re-validates against its contract, subject warnings change the
status and are named in the summary, a report that re-states claim ids evicts its stale
formalizations from the cross-agent pool, conflict findings name their reports, and the
receipt states whether a synthesis entailment check was performed."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus, count_paragraphs, extract_constraints
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.schema import Assertion, Problem, SourceRef
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText,
    TranslationResult, TranslationStatus, sha256_text,
)

KEY = b"robustness-test-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK = "task-r"


def plan(subject: str, agents: list[str], task_type: str = "short_answer") -> WorkPlan:
    return WorkPlan(plan_id="plan-r", request_id="req-r", task_id=TASK, subject=subject, task_type=task_type, selected_agent_ids=agents)


def report(agent: str, rid: str, text: str, claims: list[dict], subject: str = "Physics", task_type: str = "short_answer", docs=()) -> SpecialistReport:
    return SpecialistReport(report_id=rid, request_id="req-r", task_id=TASK, agent_id=agent, subject=subject, task_type=task_type, original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=list(docs), created_at="2026-10-11T11:00:00Z",
                            claims=[ClaimRecord(request_id="req-r", task_id=TASK, report_id=rid, agent_id=agent, subject=subject, task_type=task_type, **c) for c in claims])


def speed_problem(claim_id: str, value: str) -> Problem:
    V = lambda n: {"op": "var", "name": n}
    R = lambda v: {"op": "real", "value": str(v)}
    return Problem.model_validate({"problem_id": f"p-{claim_id}", "request_id": "req-r", "claim_id": claim_id, "query": "entailment",
                                   "symbols": [{"name": "speed", "sort": "Real", "meaning": "the speed in m/s"}],
                                   "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}, "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}}})


def outcome(claim: ClaimRecord, rep: SpecialistReport, problem: Problem) -> ClaimVerificationOutcome:
    res = verify(problem, CFG, signing_key=KEY, key_id="t")
    tr = TranslationResult(translation_id=f"tr-{rep.report_id}-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=rep.report_id, status=TranslationStatus.TRANSLATED,
                           eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="t"),
                           problem=problem, translator_version="t", policy_version="t", created_at="2026-10-11T11:00:00Z")
    return ClaimVerificationOutcome(outcome_id=f"o-{rep.report_id}-{claim.claim_id}", request_id=claim.request_id, report_id=rep.report_id, claim_id=claim.claim_id, translation=tr, verification=res,
                                    display_status=res.status, summary="stub", created_at="2026-10-11T11:00:00Z")


# ----------------------------------------------------------------- unparseable text


@pytest.mark.parametrize("subject,agent", [("History", "history-specialist"), ("English A: Literature", "english-specialist"), ("Economics", "economics-specialist"), ("Physics", "specialist")])
@pytest.mark.parametrize("text", ["", "   \n\n  \t "])
def test_empty_or_whitespace_text_is_rejected_with_a_receipt_on_every_branch(subject, agent, text):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan(subject, [agent]))
    m, _, _ = hub.dispatch(TASK, agent, "Explain the causes of the crisis.")
    reply, rc = hub.receive(TASK, m.message_id, text, agent_id=agent, report_id="rep-empty")
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    err = [f for f in rc.errors if f.code == "INT-REQ-009"]
    assert err and err[0].report_ids == ["rep-empty"] and err[0].agent_ids == [agent]
    assert "could not be parsed" in err[0].message and len(hub.receipts(TASK)) == 2


def test_oversized_answers_are_delivered_within_the_contract_not_raised():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan("History", ["history-specialist"], task_type="essay"))
    m, _, _ = hub.dispatch(TASK, "history-specialist", "To what extent was the Depression responsible for the Nazi rise?")
    text = " ".join(f"In {1919 + (i % 14)} the NSDAP held {i} seats." for i in range(530))
    reply, rc = hub.receive(TASK, m.message_id, text, agent_id="history-specialist", report_id="rep-530")
    assert rc.status is not TransmissionStatus.REJECTED and reply is not None
    delivered = SpecialistReport.model_validate(reply.payload)  # the payload the router holds re-validates
    assert len(delivered.claims) == 512 and delivered.claims[-1].claim_id == "h.tail" and delivered.claims[-1].materiality == "supporting"
    assert any("merged into claim h.tail" in u for u in delivered.unresolved_issues)
    bullets = "Dated items (from memory; verify them):\n\n" + "\n".join(f"- Reichstag sitting day {i} of the 1930 period — no majority found for the budget and the decree remained in force" for i in range(60))
    m2, _, _ = hub.dispatch(TASK, "history-specialist", "To what extent was the Depression responsible for the Nazi rise?")
    reply2, rc2 = hub.receive(TASK, m2.message_id, bullets, agent_id="history-specialist", report_id="rep-bullets")
    assert rc2.status is not TransmissionStatus.REJECTED and reply2 is not None
    rep2 = SpecialistReport.model_validate(reply2.payload)
    assert len(rep2.claims) == 61 and all(len(c.claim_text) <= 4000 for c in rep2.claims)
    assert rep2.claims[0].claim_role == "other" and not any(c.claim_text.startswith("-") for c in rep2.claims)


def test_seventy_sentence_paragraph_point_supports_every_claim_and_revalidates():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan("History", ["history-specialist"], task_type="essay"))
    m, _, _ = hub.dispatch(TASK, "history-specialist", "Describe the party's growth.")
    text = " ".join(f"In {1920 + (i % 12)} the party won {i} seats." for i in range(70)) + "\n\nDates and figures are from memory; verify them."
    reply, rc = hub.receive(TASK, m.message_id, text, agent_id="history-specialist", report_id="rep-70")
    assert rc.status is not TransmissionStatus.REJECTED
    delivered = SpecialistReport.model_validate(reply.payload)
    assert len(delivered.claims[0].supporting_claim_ids) == 69


def test_payload_that_does_not_revalidate_is_rejected_with_int_req_009():
    ch = TranslatorChannel(plan("Physics", ["physics-specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    good = report("physics-specialist", "rep-bad", "The speed is 15 m/s.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")])
    broken_claim = ClaimRecord.model_construct(**{**good.claims[0].model_dump(), "claim_text": ""})  # built around validation
    broken = good.model_copy(update={"claims": [broken_claim]})
    reply, rc = ch.respond(m.message_id, broken)
    assert reply is None and rc.status is TransmissionStatus.REJECTED
    assert any(f.code == "INT-REQ-009" and "re-validate" in f.message and f.report_ids == ["rep-bad"] for f in rc.errors)
    assert "rep-bad" not in ch.transmitted_reports


# -------------------------------------------------------------- status semantics


def test_subject_warning_changes_the_status_and_is_named_in_the_summary():
    ch = TranslatorChannel(plan("History", ["history-specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "history-specialist", "Describe the rise of the party.")
    text = 'The rise came after 1930, when the leader called the Reichstag "a parliament that could only say no" in a speech.'
    rep = report("history-specialist", "rep-q", text, [dict(claim_id="h1.1", claim_text=text, claim_role="evidence", materiality="supporting")], subject="History")
    reply, rc = ch.respond(m.message_id, rep)
    assert reply is not None and not rc.findings, [f.model_dump() for f in rc.findings]
    src = [sf for sf in rc.structural_findings if sf.code == "CORE-SRC-003"]
    assert src and src[0].severity == "warning" and "no from-memory label" in src[0].message and "a parliament that could only say no" in src[0].message
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # the router cannot miss a subject warning
    assert "CORE-SRC-003 x1" in rc.summary and "Subject findings: 1." not in rc.summary


def test_delivered_report_with_constraint_error_is_still_transmitted_for_the_ledger():
    ch = TranslatorChannel(plan("Physics", ["physics-specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "physics-specialist", "Give the speed in one paragraph of no more than 5 words.")
    text = "The speed is fifteen metres per second, measured twice."
    reply, rc = ch.respond(m.message_id, report("physics-specialist", "rep-long", text, [dict(claim_id="a-1", claim_text=text, claim_role="quantitative")]))
    assert reply is not None and any(f.code == "INT-REQ-005" for f in rc.errors)
    assert "rep-long" in ch.transmitted_reports  # delivered <=> transmitted


# ------------------------------------------------------------ cross-agent pool


def test_restated_claims_evict_stale_formalizations_and_name_the_supersession():
    problems = {("rep-1", "a-1"): speed_problem("a-1", 15), ("rep-1", "a-2"): speed_problem("a-2", 16)}

    def verify_fn(claim, rep):
        p = problems.get((rep.report_id, claim.claim_id))
        return outcome(claim, rep, p) if p else None

    ch = TranslatorChannel(plan("Physics", ["physics-specialist"]), signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    claims = [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative"), dict(claim_id="a-2", claim_text="The speed is 16 m/s.", claim_role="quantitative")]
    m1, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    _, r1 = ch.respond(m1.message_id, report("physics-specialist", "rep-1", "The speed is 15 m/s. The speed is 16 m/s.", claims))
    conflict = [f for f in r1.findings if f.code == "INT-CONFLICT-001"]
    assert conflict and set(conflict[0].claim_ids) == {"a-1", "a-2"} and conflict[0].report_ids == ["rep-1"]
    assert sorted(ch.formalized) == ["a-1", "a-2"]
    # The same agent re-states both claims; this time neither is formalized (NOT_ELIGIBLE, failed translation).
    m2, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    _, r2 = ch.respond(m2.message_id, report("physics-specialist", "rep-2", "The speed is 15 m/s. The speed is 16 m/s. Measured again.", claims))
    assert not [f for f in r2.findings if f.code.startswith(("INT-CONFLICT", "INT-GLOSSARY"))], [f.model_dump() for f in r2.findings]
    assert ch.formalized == {} and ch.formalized_by == {}
    sup = [f for f in r2.findings if f.code == "INT-HANDOFF-009"]
    assert sup and sup[0].severity == "warning" and set(sup[0].report_ids) == {"rep-1", "rep-2"} and set(sup[0].claim_ids) == {"a-1", "a-2"}


def test_cross_agent_conflict_names_both_reports():
    problems = {"a-1": speed_problem("a-1", 15), "b-1": speed_problem("b-1", 16)}

    def verify_fn(claim, rep):
        p = problems.get(claim.claim_id)
        return outcome(claim, rep, p) if p else None

    ch = TranslatorChannel(plan("Physics", ["physics-specialist", "maths-specialist"]), signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    m1, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    m2, _, _ = ch.request("router", "maths-specialist", "Compute 120 divided by 8.")
    ch.respond(m1.message_id, report("physics-specialist", "rep-a", "The speed is 15 m/s.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")]))
    _, r2 = ch.respond(m2.message_id, report("maths-specialist", "rep-b", "The speed is 16 m/s.", [dict(claim_id="b-1", claim_text="The speed is 16 m/s.", claim_role="quantitative")]))
    conflict = [f for f in r2.findings if f.code == "INT-CONFLICT-001"]
    assert conflict and conflict[0].report_ids == ["rep-a", "rep-b"] and set(conflict[0].agent_ids) == {"maths-specialist", "physics-specialist"}


# ---------------------------------------------------------- synthesis entailment


def _channel_with_formalized_source():
    problems = {"a-1": speed_problem("a-1", 15)}

    def verify_fn(claim, rep):
        p = problems.get(claim.claim_id)
        return outcome(claim, rep, p) if p else None

    ch = TranslatorChannel(plan("Physics", ["physics-specialist", "combinator"]), signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    m, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    reply, rc = ch.respond(m.message_id, report("physics-specialist", "rep-a", "The speed is 15 m/s.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")]))
    assert reply is not None and "a-1" in ch.formalized
    return ch


def _synthesis(text: str, **claim_fields) -> Synthesis:
    sc = SynthesizedClaim(claim_id="s-1", text=text, source_claim_ids=["a-1"], transformation="merged", **claim_fields)
    return Synthesis(synthesis_id="syn-1", request_id="req-r", task_id=TASK, combinator_agent_id="combinator", source_report_ids=["rep-a"], claims=[sc], text=text, text_sha256=sha256_text(text), created_at="2026-10-11T11:05:00Z")


def _speed_is(value: str) -> Assertion:
    return Assertion.model_validate({"id": "S", "expr": {"op": "eq", "left": {"op": "var", "name": "speed"}, "right": {"op": "real", "value": value}}})


def test_synthesis_without_formal_conclusion_says_the_check_was_not_performed():
    ch = _channel_with_formalized_source()
    relayed, rr = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis("The speed is 15 m/s."))
    assert relayed is not None
    ledger = [f for f in rr.findings if f.code == "INT-LEDGER-011"]
    assert ledger and "NOT performed on this channel" in ledger[0].message and "required" not in ledger[0].message
    assert not rr.formal_result_ids and not [f for f in rr.findings if f.code.startswith("INT-SYNTH")]


def test_synthesis_with_formal_conclusion_is_checked_by_the_engine():
    ch = _channel_with_formalized_source()
    _, ok = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis("The speed is 15 m/s.", formal_conclusion=_speed_is("15")))
    ledger = [f for f in ok.findings if f.code == "INT-LEDGER-011"]
    assert ledger and "performed on this channel" in ledger[0].message and ledger[0].formal_result_id in ok.formal_result_ids
    assert not [f for f in ok.findings if f.code == "INT-SYNTH-001"]
    _, bad = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis("The speed is 20 m/s.", formal_conclusion=_speed_is("20")))
    refuted = [f for f in bad.findings if f.code == "INT-SYNTH-001"]
    assert refuted and refuted[0].severity == "error" and "a-1" in refuted[0].claim_ids and refuted[0].formal_result_id in bad.formal_result_ids


def test_formalization_hook_supplies_the_conclusion_when_the_combinator_did_not():
    ch = _channel_with_formalized_source()
    ch.formalize_synthesis_fn = lambda sc, sources: _speed_is("15")
    _, rr = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis("The speed is 15 m/s."))
    assert rr.formal_result_ids and any(f.code == "INT-LEDGER-011" and "performed on this channel" in f.message for f in rr.findings)


# ------------------------------------------------------------- request parsing


def test_write_one_paragraph_is_a_paragraph_bound_and_notes_do_not_count():
    kinds = sorted((c.kind, c.value) for c in extract_constraints("Write one analytical paragraph: how does the writer present justice? Use quotations from the extract. Write no more than 400 words."))
    assert ("max_paragraphs", "1") in kinds and ("min_paragraphs", "1") in kinds and ("max_words", "400") in kinds
    assert ("max_paragraphs", "1") in {(c.kind, c.value) for c in extract_constraints("Write one body paragraph only, following your method, in no more than 350 words.")}
    body = "The Depression was decisive because it destroyed the security of moderate voters in 1930."
    assert count_paragraphs(body + "\n\nDates and figures are from memory; verify them against your notes before use.") == 1
    assert count_paragraphs(body + "\n\nVERIFIED: all claims checked and confirmed.") == 1
    assert count_paragraphs("## Heading\n\n" + body + "\n\nA second paragraph follows here with its own argument.") == 2


def test_one_paragraph_request_answered_in_four_is_a_formal_constraint_failure():
    ch = TranslatorChannel(plan("Physics", ["physics-specialist"]), signing_key=KEY, config=CFG)
    m, req, _ = ch.request("router", "physics-specialist", "Write one paragraph: what is the speed?")
    assert any(c.kind == "max_paragraphs" and c.value == "1" for c in req.constraints)
    text = "The speed is 15 m/s.\n\nIt was measured twice.\n\nThe method was timing.\n\nThe result is reliable."
    _, rc = ch.respond(m.message_id, report("physics-specialist", "rep-4", text, [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")]))
    failed = [c for c in rc.constraint_results if c.satisfied is False]
    assert failed and failed[0].method == "formal" and "measured 4 paragraphs" in failed[0].detail
