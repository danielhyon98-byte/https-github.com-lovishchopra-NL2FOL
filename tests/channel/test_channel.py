"""Router -> specialist -> router through the translator channel, plus agent-to-agent relay."""
from __future__ import annotations

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus, extract_constraints, extract_items
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText,
    TranslationResult, TranslationStatus, sha256_text,
)

KEY = b"channel-test-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
EXTRACT = ("The lawyer stood by the thesis of homicide in legitimate defense of honor, which was upheld by the court in good faith. "
           "'We killed him openly,' Pedro Vicario said, 'but we're innocent.'")
DOC = SuppliedText(document_id="doc-cdf", title="Chronicle of a Death Foretold (extract)", author="Gabriel García Márquez", text=EXTRACT, locator_scheme="none")
USER_INPUT = ("Analyse how the writer presents the administration of justice in the extract. Use quotations from the extract. "
              "Write no more than 60 words.")


def plan(**over):
    base = dict(plan_id="plan-9", request_id="req-9", task_id="task-9", subject="English A: Literature", task_type="analytical_paragraph",
                selected_agent_ids=["english-specialist", "history-specialist", "combinator"], allowed_document_ids=["doc-cdf"])
    base.update(over)
    return WorkPlan(**base)


def english_report(text: str, claims: list[dict], agent="english-specialist", request_id="req-9", task_id="task-9", report_id="rep-en-1", docs=(DOC,)):
    return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, subject="English A: Literature", task_type="analytical_paragraph",
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=list(docs), created_at="2026-10-11T11:00:00Z",
                            claims=[ClaimRecord(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, subject="English A: Literature", task_type="analytical_paragraph", **c) for c in claims])


GOOD_TEXT = ("García Márquez presents justice as compromised: the lawyer's \"thesis of homicide in legitimate defense of honor\" "
             "uses ironic legal diction, and the twins' claim \"but we're innocent\" severs guilt from the killing.")
GOOD_CLAIMS = [
    dict(claim_id="en-point", claim_text="García Márquez presents the administration of justice as compromised", claim_role="point", supporting_claim_ids=["en-ev1", "en-ev2", "en-dev"]),
    dict(claim_id="en-ev1", claim_text="thesis of homicide in legitimate defense of honor", claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt="thesis of homicide in legitimate defense of honor")]),
    dict(claim_id="en-ev2", claim_text="but we're innocent", claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt="but we're innocent")]),
    dict(claim_id="en-dev", claim_text="the phrase uses ironic legal diction", claim_role="device", certainty="probable"),
]


def test_request_is_made_explicit_and_logged():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, req, receipt = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    assert msg is not None and receipt.status is TransmissionStatus.ACCEPTED
    kinds = sorted(c.kind for c in req.constraints)
    assert kinds == ["max_words", "must_cite_supplied_text"] and next(c for c in req.constraints if c.kind == "max_words").value == "60"
    assert len(req.items) >= 1 and req.items[0].text.startswith("Analyse")
    assert msg.contract == "task_request/1.0" and msg.payload["user_input_sha256"] == req.user_input_sha256


def test_request_to_unselected_agent_is_rejected():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _, receipt = ch.request("router", "physics-specialist", USER_INPUT, [DOC])
    assert msg is None and receipt.status is TransmissionStatus.REJECTED and receipt.errors[0].code == "INT-HANDOFF-002"


def test_good_response_flows_back_with_formal_constraint_results():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, req, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    reply, receipt = ch.respond(msg.message_id, english_report(GOOD_TEXT, GOOD_CLAIMS))
    assert reply is not None and reply.in_reply_to == msg.message_id and reply.contract == "specialist_report/1.0"
    assert receipt.status in (TransmissionStatus.ACCEPTED, TransmissionStatus.ACCEPTED_WITH_FINDINGS)
    assert not receipt.errors, [f.model_dump() for f in receipt.errors]
    words = next(c for c in receipt.constraint_results if c.constraint_id == next(k.constraint_id for k in req.constraints if k.kind == "max_words"))
    assert words.satisfied is True and words.method == "formal" and words.formal_status == "ENTAILED" and words.formal_result_id in receipt.formal_result_ids
    cite = next(c for c in receipt.constraint_results if c.method == "deterministic")
    assert cite.satisfied is True
    assert all(c.addressed for c in receipt.coverage)
    assert "Formal results concern only the encoded checks" in receipt.summary


def test_overlong_response_fails_word_constraint_formally_but_is_delivered_with_findings():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    long_text = GOOD_TEXT + " " + " ".join(["justice"] * 80)
    reply, receipt = ch.respond(msg.message_id, english_report(long_text, GOOD_CLAIMS))
    assert reply is not None and receipt.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    failed = [c for c in receipt.constraint_results if c.satisfied is False]
    assert failed and failed[0].formal_status == "COUNTEREXAMPLE"
    assert any(f.code == "INT-REQ-005" and f.formal_result_id == failed[0].formal_result_id and not f.deterministic for f in receipt.findings)


def test_invented_quotation_flagged_on_the_way_back():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    bad = [dict(c) for c in GOOD_CLAIMS]
    bad[1] = dict(claim_id="en-ev1", claim_text="the court of honor demanded blood", claim_role="evidence", source_refs=[SourceRef(document_id="doc-cdf", excerpt="the court of honor demanded blood")])
    _, receipt = ch.respond(msg.message_id, english_report(GOOD_TEXT, bad))
    assert any(f.code == "INT-REQ-003" and f.claim_ids == ["en-ev1"] for f in receipt.errors)
    assert receipt.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS


def test_wrong_agent_or_wrong_task_response_is_rejected_not_delivered():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    reply, receipt = ch.respond(msg.message_id, english_report(GOOD_TEXT, GOOD_CLAIMS, agent="history-specialist", report_id="rep-h"))
    assert reply is None and receipt.status is TransmissionStatus.REJECTED and any(f.code == "INT-REQ-001" for f in receipt.errors)
    reply2, receipt2 = ch.respond(msg.message_id, english_report(GOOD_TEXT, GOOD_CLAIMS, request_id="req-other", task_id="task-other", report_id="rep-x"))
    assert reply2 is None and any(f.code in ("INT-HANDOFF-001", "INT-ENV-004") for f in receipt2.errors)
    reply3, receipt3 = ch.respond("no-such-request", english_report(GOOD_TEXT, GOOD_CLAIMS, report_id="rep-y"))
    assert reply3 is None and any(f.code in ("INT-REQ-000", "INT-ENV-003") for f in receipt3.errors)


def test_duplicate_delivery_is_flagged():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    rep = english_report(GOOD_TEXT, GOOD_CLAIMS)
    ch.respond(msg.message_id, rep)
    _, receipt = ch.respond(msg.message_id, rep)
    assert any(f.code == "INT-ENV-001" for f in receipt.findings)


def _stub_outcome(claim: ClaimRecord, report: SpecialistReport, problem: Problem, status_value: str) -> ClaimVerificationOutcome:
    res = verify(problem, CFG, signing_key=KEY, key_id="t")
    tr = TranslationResult(translation_id=f"tr-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=report.report_id, status=TranslationStatus.TRANSLATED,
                           eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="t"),
                           problem=problem, translator_version="t", policy_version="t", created_at="2026-10-11T11:00:00Z")
    return ClaimVerificationOutcome(outcome_id=f"o-{claim.claim_id}", request_id=claim.request_id, report_id=report.report_id, claim_id=claim.claim_id, translation=tr, verification=res,
                                    display_status=res.status, summary="stub", created_at="2026-10-11T11:00:00Z")


def _speed_problem(claim_id: str, value: str) -> Problem:
    V = lambda n: {"op": "var", "name": n}
    R = lambda v: {"op": "real", "value": str(v)}
    return Problem.model_validate({"problem_id": f"p-{claim_id}", "request_id": "req-9", "claim_id": claim_id, "query": "entailment",
                                   "symbols": [{"name": "speed", "sort": "Real"}],
                                   "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}, "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}}})


def test_two_agents_contradicting_each_other_are_named_on_the_second_transmission():
    problems = {"a-1": _speed_problem("a-1", 15), "b-1": _speed_problem("b-1", 16)}

    def verify_fn(claim, report):
        p = problems.get(claim.claim_id)
        return _stub_outcome(claim, report, p, "ENTAILED") if p else None

    p = plan(subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist", "maths-specialist"], allowed_document_ids=[])
    ch = TranslatorChannel(p, signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    m1, _, _ = ch.request("router", "physics-specialist", "What is the speed if d = 120 m and t = 8 s?")
    m2, _, _ = ch.request("router", "maths-specialist", "Compute 120 divided by 8.")

    def rep(agent, cid, text, rid):
        return SpecialistReport(report_id=rid, request_id="req-9", task_id="task-9", agent_id=agent, subject="Physics", task_type="short_answer", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T11:00:00Z",
                                claims=[ClaimRecord(request_id="req-9", task_id="task-9", report_id=rid, agent_id=agent, subject="Physics", task_type="short_answer", claim_id=cid, claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic")])

    _, r1 = ch.respond(m1.message_id, rep("physics-specialist", "a-1", "The speed is 15 m/s.", "rep-a"))
    assert r1.status is not TransmissionStatus.REJECTED and r1.outcomes and r1.outcomes[0].display_status.value == "ENTAILED"
    _, r2 = ch.respond(m2.message_id, rep("maths-specialist", "b-1", "The speed is 16 m/s.", "rep-b"))
    conflict = [f for f in r2.findings if f.code == "INT-CONFLICT-001"]
    assert conflict and set(conflict[0].claim_ids) == {"a-1", "b-1"} and conflict[0].formal_result_id in r2.formal_result_ids
    assert r2.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS


def test_agent_to_agent_relay_of_synthesis_checks_ledger():
    ch = TranslatorChannel(plan(), signing_key=KEY)
    msg, _, _ = ch.request("router", "english-specialist", USER_INPUT, [DOC])
    ch.respond(msg.message_id, english_report(GOOD_TEXT, GOOD_CLAIMS))
    text = "Justice is presented as compromised."
    syn = Synthesis(synthesis_id="syn-1", request_id="req-9", task_id="task-9", combinator_agent_id="combinator", source_report_ids=["rep-en-1"],
                    claims=[SynthesizedClaim(claim_id="s-1", text=text, source_claim_ids=["en-point"], transformation="paraphrased")],
                    text=text, text_sha256=sha256_text(text), created_at="2026-10-11T11:05:00Z")
    relayed, receipt = ch.relay("combinator", AgentRole.COMBINATOR, "overseer", AgentRole.OVERSEER, syn)
    codes = {f.code for f in receipt.findings}
    assert relayed is not None and receipt.direction == "agent_to_agent"
    assert "INT-LEDGER-002" in codes  # evidence claims en-ev1/en-ev2/en-dev neither carried nor recorded as dropped
    wrong = syn.model_copy(update={"request_id": "req-other"})
    relayed2, receipt2 = ch.relay("combinator", AgentRole.COMBINATOR, "overseer", AgentRole.OVERSEER, wrong)
    assert relayed2 is None and receipt2.status is TransmissionStatus.REJECTED


def test_request_parser_extracts_items_and_constraints():
    text = "Compare how both poets present loss. To what extent is memory reliable in each poem? Write between 300 and 400 words in three paragraphs, citing the texts."
    items = extract_items(text)
    # The third sentence only states constraints (length, paragraphs, citing); it is not a content item to cover.
    assert [i.kind for i in items] == ["instruction", "question"]
    kinds = sorted((c.kind, c.value) for c in extract_constraints(text))
    assert ("min_words", "300") in kinds and ("max_words", "400") in kinds and ("min_paragraphs", "3") in kinds and ("max_paragraphs", "3") in kinds
    assert any(k == "must_cite_supplied_text" for k, _ in kinds)
