"""Channel behaviour found wanting by the round-2 arena overseers: a specialist relaying a
colleague's report under its own name, a report id re-delivered with another payload
overwriting the held copy, relay parties the plan never selected, receipt summaries that
overflowed the contract, raw-text identity decided by the adapter instead of the hub,
quotation form differences reported as invented quotations, a response that restates the
request, content instructions lost to a constraint in the same sentence, word bounds
counting meta-text, per-agent task types, stale translations displayed under another text,
ambiguous pooled readings, undisclosed contradictions on a synthesis, and superseded reports
still in circulation."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus, count_answer_words, extract_items
from epinoic_logic.channel.bus import _fit_summary
from epinoic_logic.channel.contracts import SUMMARY_MAX_CHARS
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus
from epinoic_logic.integrity import AgentRole, ConflictRecord, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.integrity.contracts import plan_digest
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText,
    TranslationResult, TranslationStatus, sha256_text,
)

KEY = b"round2-channel-test-key-0123456789"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK = "task-r2"
POEM_TEXT = ("My name is Ozymandias, King of Kings;\nLook on my Works, ye Mighty, and despair!\nNothing beside remains. Round the decay\n"
             "Of that colossal Wreck, boundless and bare\nThe lone and level sands stretch far away.")
POEM = SuppliedText(document_id="doc-poem", title="Sonnet", text=POEM_TEXT)
HISTORY = ("The sonnet was printed in January 1818. Wheat had cost 80 shillings a quarter in 1815. Britain after Waterloo, fought on 18 June 1815, "
           "was a country of postwar distress. Dates other than the poem's own are from memory; check your notes.")
ASK_EN = "Write one analytical paragraph on power in the poem against the historical context. Quote from the poem and from the History specialist."


def two_subject_plan(**over) -> WorkPlan:
    base = dict(plan_id="plan-r2", request_id="req-r2", task_id=TASK, subject="English A: Literature", task_type="analytical_paragraph",
                selected_agent_ids=["history-specialist", "english-specialist", "dummy-combinator"], allowed_document_ids=["doc-poem", "peer:hi"],
                agent_subjects={"history-specialist": "History"})
    base.update(over)
    return WorkPlan(**base)


def physics_plan(agents: list[str], request_id: str = "req-s") -> WorkPlan:
    return WorkPlan(plan_id="plan-s", request_id=request_id, task_id=TASK, subject="Physics", task_type="short_answer", selected_agent_ids=agents)


def deliver_history(hub: RouterHub, report_id: str = "rep-hi", text: str = HISTORY):
    m, req, _ = hub.dispatch(TASK, "history-specialist", "Outline the historical context of the poem in one paragraph of no more than 200 words.")
    reply, rc = hub.receive(TASK, m.message_id, text, agent_id="history-specialist", report_id=report_id)
    return m, req, reply, rc


def report(agent: str, rid: str, text: str, claims: list[dict], subject: str = "Physics", task_type: str = "short_answer", docs=(), request_id: str = "req-s") -> SpecialistReport:
    return SpecialistReport(report_id=rid, request_id=request_id, task_id=TASK, agent_id=agent, subject=subject, task_type=task_type, original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=list(docs), created_at="2026-10-11T11:00:00Z",
                            claims=[ClaimRecord(request_id=request_id, task_id=TASK, report_id=rid, agent_id=agent, subject=subject, task_type=task_type, **c) for c in claims])


def history_report(rid: str, text: str = HISTORY) -> SpecialistReport:
    claims = [dict(claim_id="h1", claim_text="The sonnet was printed in January 1818.", claim_role="evidence"),
              dict(claim_id="h2", claim_text="Wheat had cost 80 shillings a quarter in 1815.", claim_role="evidence")]
    return report("history-specialist", rid, text, claims, subject="History", task_type="analytical_paragraph", request_id="req-r2")


def consistent_copy(rep: SpecialistReport, *, replace: tuple[str, str] | None = None, report_id: str | None = None) -> SpecialistReport:
    """A forgery whose text, digest and claims change together, so the payload still re-validates."""
    data = rep.model_dump(mode="json", exclude_none=True)
    text = data["original_response"] if replace is None else data["original_response"].replace(*replace)
    claims = [{**c, "claim_text": c["claim_text"] if replace is None else c["claim_text"].replace(*replace), "report_id": report_id or c["report_id"]} for c in data["claims"]]
    return SpecialistReport.model_validate({**data, "report_id": report_id or data["report_id"], "original_response": text, "response_sha256": sha256_text(text), "claims": claims})


def synthesis_of(rep: SpecialistReport, combinator: str = "dummy-combinator", report_ids: list[str] | None = None, request_id: str = "req-r2") -> Synthesis:
    material = [c for c in rep.claims if c.materiality == "material"]
    sc = [SynthesizedClaim(claim_id=f"s{i}", text=c.claim_text, certainty="probable", source_claim_ids=[c.claim_id], transformation="carried") for i, c in enumerate(material)]
    text = " ".join(c.text for c in sc)
    return Synthesis(synthesis_id="syn-1", request_id=request_id, task_id=TASK, combinator_agent_id=combinator, source_report_ids=report_ids or [rep.report_id],
                     claims=sc, text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")


def speed_problem(claim_id: str, value: str, request_id: str = "req-s") -> Problem:
    V = lambda n: {"op": "var", "name": n}
    R = lambda v: {"op": "real", "value": str(v)}
    return Problem.model_validate({"problem_id": f"p-{claim_id}", "request_id": request_id, "claim_id": claim_id, "query": "entailment",
                                   "symbols": [{"name": "speed", "sort": "Real", "meaning": "the speed in m/s"}],
                                   "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}, "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("speed"), "right": R(value)}}})


def outcome(claim: ClaimRecord, rep: SpecialistReport, problem: Problem, *, status: TranslationStatus = TranslationStatus.TRANSLATED, text_sha: str | None = None) -> ClaimVerificationOutcome:
    res = verify(problem, CFG, signing_key=KEY, key_id="t")
    tr = TranslationResult(translation_id=f"tr-{rep.report_id}-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=rep.report_id, status=status,
                           claim_text_sha256=text_sha, eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="t"),
                           problem=problem, translator_version="t", policy_version="t", created_at="2026-10-11T11:00:00Z")
    display = res.status if status is TranslationStatus.TRANSLATED else VerificationStatus.AMBIGUOUS_TRANSLATION
    return ClaimVerificationOutcome(outcome_id=f"o-{rep.report_id}-{claim.claim_id}", request_id=claim.request_id, report_id=rep.report_id, claim_id=claim.claim_id, translation=tr, verification=res,
                                    display_status=display, summary="stub", created_at="2026-10-11T11:00:00Z")


# ------------------------------------------------------- relay impersonation and overwrite


def test_a_specialist_cannot_relay_a_colleagues_report_or_overwrite_the_held_copy():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    _, _, reply, _ = deliver_history(hub)
    held = SpecialistReport.model_validate(reply.payload)
    forged = consistent_copy(held, replace=("80 shillings", "60 shillings"))
    fwd, fr = ch.relay("english-specialist", AgentRole.SPECIALIST, "dummy-combinator", AgentRole.COMBINATOR, forged)
    assert fwd is None and fr.status is TransmissionStatus.REJECTED
    env = [f for f in fr.errors if f.code == "INT-ENV-008"]
    assert env and "sender" in env[0].message and set(env[0].agent_ids) == {"english-specialist", "history-specialist"}
    assert any(f.code == "INT-HANDOFF-015" for f in fr.errors)
    assert "80 shillings" in ch.transmitted_reports["rep-hi"].original_response  # the delivered copy is untouched
    good, gr = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, held, in_reply_to=reply.message_id)
    assert good is not None and gr.status is TransmissionStatus.ACCEPTED, [f.model_dump() for f in gr.findings]
    bad, br = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, forged)
    assert bad is None and any(f.code == "INT-HANDOFF-013" and "altered in transit" in f.message for f in br.errors)
    ghost = consistent_copy(held, replace=("80 shillings", "60 shillings"), report_id="rep-ghost")
    g, grc = ch.relay("english-specialist", AgentRole.SPECIALIST, "dummy-combinator", AgentRole.COMBINATOR, ghost)
    assert g is None and any(f.code == "INT-ENV-008" for f in grc.errors)
    assert not [f for f in grc.findings if f.code == "INT-HANDOFF-009"]  # the victim is not blamed for a revision it never made
    assert list(ch.transmitted_reports) == ["rep-hi"] and "rep-ghost" not in ch.transmitted_reports


def test_a_report_id_reused_with_another_payload_is_rejected_and_the_first_delivery_kept():
    ch = TranslatorChannel(two_subject_plan(), signing_key=KEY, config=CFG)
    first = history_report("rep-hi")
    m, _, _ = ch.request("router", "history-specialist", "Outline the context.")
    r1, _ = ch.respond(m.message_id, first)
    assert r1 is not None
    revised = consistent_copy(first, replace=("80 shillings", "60 shillings"))
    m2, _, _ = ch.request("router", "history-specialist", "Outline the context.")
    r2, rc2 = ch.respond(m2.message_id, revised)
    assert r2 is None and rc2.status is TransmissionStatus.REJECTED
    reuse = [f for f in rc2.errors if f.code == "INT-HANDOFF-015"]
    assert reuse and reuse[0].report_ids == ["rep-hi"] and "first delivery is kept" in reuse[0].message
    assert "80 shillings" in ch.transmitted_reports["rep-hi"].original_response
    assert not [f for f in rc2.findings if f.code == "INT-HANDOFF-009"]
    m3, _, _ = ch.request("router", "history-specialist", "Outline the context.")
    r3, rc3 = ch.respond(m3.message_id, first)  # the identical payload again is a duplicate delivery, not an error
    assert r3 is not None and any(f.code == "INT-ENV-001" for f in rc3.findings) and not rc3.errors


def test_relay_parties_must_be_selected_by_the_plan():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    _, _, reply, _ = deliver_history(hub)
    held = SpecialistReport.model_validate(reply.payload)
    fwd, fr = ch.relay("router", AgentRole.ROUTER, "economics-specialist", AgentRole.SPECIALIST, held, in_reply_to=reply.message_id)
    assert fwd is None and fr.status is TransmissionStatus.REJECTED
    assert any(f.code == "INT-HANDOFF-002" and f.agent_ids == ["economics-specialist"] for f in fr.errors)
    rogue = synthesis_of(held, combinator="rogue-combinator")
    r, rr = ch.relay("rogue-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, rogue)
    assert r is None and rr.status is TransmissionStatus.REJECTED
    assert any(f.code == "INT-HANDOFF-002" and "rogue-combinator" in f.agent_ids for f in rr.errors)
    assert not [f for f in rr.findings if f.code.startswith("INT-LEDGER")]  # an unselected combinator's ledger is not examined
    masked = synthesis_of(held)
    r2, rr2 = ch.relay("english-specialist", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, masked)
    assert r2 is None and any(f.code == "INT-ENV-008" and "dummy-combinator" in f.message for f in rr2.errors)
    ok, okr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, masked)
    assert ok is not None and okr.status is not TransmissionStatus.REJECTED
    ok2, okr2 = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "overseer", AgentRole.OVERSEER, masked)  # infrastructure roles need no selection
    assert ok2 is not None and not [f for f in okr2.findings if f.code == "INT-HANDOFF-002"]


# ------------------------------------------------------------- receipt summary bound


def test_five_hundred_arithmetic_sentences_yield_a_receipt_within_the_contract():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["history-specialist"]))
    m, _, _ = hub.dispatch("t", "history-specialist", "Describe the growth of enrolment.")
    sentences = ["Enrolment rose from 200 to 260 students, an increase of 30 per cent."] * 499 + ["Enrolment rose from 200 to 260 students, an increase of 45 per cent."]
    reply, rc = hub.receive("t", m.message_id, " ".join(sentences), agent_id="history-specialist", report_id="rep-500")  # must not raise
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    assert len(rc.formal_checks) == 500 and len(rc.summary) <= SUMMARY_MAX_CHARS
    assert "500 (499 ok, 1 FAILED, 0 undecided)" in rc.summary and "FAILED: core-quant-" in rc.summary
    assert sum(1 for f in rc.findings if f.code == "INT-SUBJ-001") == 1 and rc.summary.endswith("coverage is heuristic.")


def test_summary_is_cut_defensively_but_keeps_the_scope_sentence():
    tail = "Formal results concern only the encoded checks under their premises; coverage is heuristic."
    fitted = _fit_summary("x" * 20_000 + " " + tail)
    assert len(fitted) <= SUMMARY_MAX_CHARS and fitted.endswith(tail) and "[summary truncated]" in fitted
    assert _fit_summary("short " + tail) == "short " + tail


# ---------------------------------------------------------- identity before parsing


def test_raw_text_identity_is_decided_before_parsing_on_every_branch():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(two_subject_plan())
    m, _, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem. Quote from the poem.", [POEM])
    text = 'The boast "King of Kings" is hollow.'
    reply, rc = hub.receive(TASK, m.message_id, text, agent_id="rogue-specialist", report_id="rep-rogue")
    assert reply is None and rc.status is TransmissionStatus.REJECTED and rc.branch == "english"
    codes = {f.code for f in rc.errors}
    assert {"INT-HANDOFF-002", "INT-REQ-001"} <= codes
    assert all("not parsed" in f.message for f in rc.errors if f.code in ("INT-HANDOFF-002", "INT-REQ-001"))
    assert "rep-rogue" not in hub.channels[TASK].transmitted_reports
    reply2, rc2 = hub.receive(TASK, m.message_id, text, agent_id="history-specialist", report_id="rep-wrong")  # selected, but not the addressee
    assert reply2 is None and any(f.code == "INT-REQ-001" for f in rc2.errors) and not [f for f in rc2.errors if f.code == "INT-HANDOFF-002"]


def test_a_report_relabelled_by_an_adapter_is_bound_to_the_stated_sender():
    ch = TranslatorChannel(two_subject_plan(), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "history-specialist", "Outline the context.")
    reply, rc = ch.respond(m.message_id, history_report("rep-hi"), sender_agent_id="english-specialist")
    assert reply is None and {"INT-ENV-008", "INT-REQ-001"} <= {f.code for f in rc.errors}
    assert "rep-hi" not in ch.transmitted_reports


# ------------------------------------------------------- quotation form differences


def test_quotation_form_differences_are_warnings_not_invented_quotations():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-f", request_id="req-f", task_id=TASK, subject="English A: Literature", task_type="analytical_paragraph", selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-poem"]))
    ask = "Write one analytical paragraph on power in the poem. Quote from the poem."
    m, _, _ = hub.dispatch(TASK, "english-specialist", ask, [POEM])
    slash = 'The ruin frames the boast: "Round the decay / Of that colossal Wreck, boundless and bare" answers the pedestal.'
    reply, rc = hub.receive(TASK, m.message_id, slash, agent_id="english-specialist", report_id="rep-slash")
    assert reply is not None and not [f for f in rc.findings if f.code in ("INT-REQ-003", "INT-REQ-010")], [f.model_dump() for f in rc.findings]
    assert not [sf for sf in rc.structural_findings if sf.code in ("ES-SRC-001", "ES-SRC-006", "CORE-SRC-001")]
    m2, _, _ = hub.dispatch(TASK, "english-specialist", ask, [POEM])
    capital = 'The command to "look on my Works, ye Mighty, and despair" rings hollow.'
    reply2, rc2 = hub.receive(TASK, m2.message_id, capital, agent_id="english-specialist", report_id="rep-capital")
    assert reply2 is not None and rc2.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    form = [f for f in rc2.findings if f.code == "INT-REQ-010"]
    assert form and form[0].severity == "warning" and "initial capital" in form[0].message and "not an invented quotation" in form[0].message
    assert not [f for f in rc2.findings if f.code in ("INT-REQ-003", "INT-SUBJ-003")]
    assert not [sf for sf in rc2.structural_findings if sf.code in ("CORE-SRC-001", "ES-SRC-001")]


def test_long_elision_is_a_form_warning_and_not_found_names_every_supplied_text():
    filler = " ".join(["the clock ticks on and the yard stays grey"] * 20)
    doc_a = SuppliedText(document_id="doc-a", text=f"The lamp stays unlit in the hall. {filler} Nothing moves outside.")
    doc_b = SuppliedText(document_id="doc-b", text="Outside, the yard is a measured dose of grey and nothing moves.")
    ch = TranslatorChannel(physics_plan(["specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "specialist", "Describe the hall.", [doc_a, doc_b])
    claims = [dict(claim_id="q-long", claim_text="The hall is described from the lamp to the outside.", claim_role="evidence", source_refs=[SourceRef(document_id="doc-a", excerpt="The lamp stays unlit ... Nothing moves outside")]),
              dict(claim_id="q-missing", claim_text="The lamp burns brightly in the hall.", claim_role="evidence", source_refs=[SourceRef(document_id="doc-a", excerpt="the lamp burns brightly")]),
              dict(claim_id="q-misattributed", claim_text="The yard is grey in the hall.", claim_role="evidence", source_refs=[SourceRef(document_id="doc-a", excerpt="a measured dose of grey")])]
    reply, rc = ch.respond(m.message_id, report("specialist", "rep-q", "The hall is described.", claims, docs=(doc_a, doc_b)))
    assert reply is not None
    by = {(f.code, f.claim_ids[0]): f for f in rc.findings if f.code in ("INT-REQ-003", "INT-REQ-010")}
    long = by[("INT-REQ-010", "q-long")]
    assert long.severity == "warning" and "elides about" in long.message and "long elision" in long.message and ("INT-REQ-003", "q-long") not in by
    missing = by[("INT-REQ-003", "q-missing")]
    assert missing.severity == "error" and "not found in the supplied texts ['doc-a', 'doc-b']" in missing.message and missing.document_ids == ["doc-a", "doc-b"]
    assert "misattributed" in by[("INT-REQ-003", "q-misattributed")].message and "['doc-b']" in by[("INT-REQ-003", "q-misattributed")].message
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-003"]  # the core pack's grounding error for the same excerpts is not escalated a second time


# --------------------------------------------------------------------- request echo


def test_a_response_that_restates_the_request_is_named_and_covers_nothing():
    ch = TranslatorChannel(physics_plan(["specialist"]), signing_key=KEY, config=CFG)
    ask = "Explain the causes of the banking crisis of 1931 and assess which mattered most."
    m, _, _ = ch.request("router", "specialist", ask)
    reply, rc = ch.respond(m.message_id, report("specialist", "rep-echo", ask, [dict(claim_id="e-1", claim_text=ask, claim_role="point")]))
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # a content finding travels with the report
    echoed = [f for f in rc.findings if f.code == "INT-REQ-011"]
    assert echoed and echoed[0].severity == "error" and "restates the request" in echoed[0].message and echoed[0].claim_ids == ["e-1"]
    assert rc.coverage and all(not c.addressed and not c.addressed_by_claim_ids for c in rc.coverage)
    assert any(f.code == "INT-REQ-004" for f in rc.findings)
    near = "The causes of the banking crisis of 1931: explain them, and assess which mattered most."
    m2, _, _ = ch.request("router", "specialist", ask)
    _, rc2 = ch.respond(m2.message_id, report("specialist", "rep-near", near, [dict(claim_id="e-2", claim_text=near, claim_role="point")]))
    assert any(f.code == "INT-REQ-011" and "distinct words" in f.message for f in rc2.findings)
    answer = "The crisis began when the Creditanstalt failed in May 1931; the collapse of confidence mattered most."
    m3, _, _ = ch.request("router", "specialist", ask)
    _, rc3 = ch.respond(m3.message_id, report("specialist", "rep-ans", answer, [dict(claim_id="e-3", claim_text=answer, claim_role="judgement")]))
    assert not [f for f in rc3.findings if f.code == "INT-REQ-011"] and all(c.addressed for c in rc3.coverage)


# ------------------------------------------------------------- request parsing


def test_content_instructions_sharing_a_sentence_with_a_constraint_become_items():
    items = extract_items("Outline, with dated and quantified evidence, the economic impact of the Wall Street Crash on the United States between 1929 and 1933. "
                          "Write no more than 200 words and give a judgement on which effect mattered most.")
    assert [(i.command_term, i.level) for i in items] == [("outline", 2), ("give a judgement", 3)]
    assert items[1].text == "Give a judgement on which effect mattered most."
    items2 = extract_items("A literature student is reading Shelley's sonnet 'Ozymandias' (written in 1817 and published in January 1818). In one paragraph of no more than "
                           "200 words, outline for that student the historical context of its composition, with dated evidence. Label dates from memory as your method requires.")
    assert [i.command_term for i in items2] == ["outline", "label"] and items2[0].text.startswith("Outline for that student")
    assert [i.kind for i in extract_items("Compare how both poets present loss. Write between 300 and 400 words in three paragraphs, citing the texts.")] == ["instruction"]
    assert extract_items("Write one analytical paragraph on power in the poem. Quote from the poem.")[0].text == "Power in the poem."
    assert extract_items("Write one paragraph: what is the speed?")[0].text == "What is the speed?"


def test_an_unaddressed_judgement_item_is_flagged_when_it_shared_a_sentence_with_the_word_bound():
    ch = TranslatorChannel(physics_plan(["specialist"]), signing_key=KEY, config=CFG)
    ask = "Outline the effects of the crash. Write no more than 200 words and give a judgement on which effect mattered most."
    m, req, _ = ch.request("router", "specialist", ask)
    assert [i.command_term for i in req.items] == ["outline", "give a judgement"]
    text = "Share values fell, banks failed and trade shrank after the crash."
    _, rc = ch.respond(m.message_id, report("specialist", "rep-nojudge", text, [dict(claim_id="n-1", claim_text=text, claim_role="evidence")]))
    unaddressed = [f for f in rc.findings if f.code == "INT-REQ-004"]
    assert unaddressed and "give a judgement" in unaddressed[0].message.lower() and any(f.code == "INT-REQ-008" for f in rc.findings)
    judged = text + " On balance the bank failures mattered most."
    m2, _, _ = ch.request("router", "specialist", ask)
    _, rc2 = ch.respond(m2.message_id, report("specialist", "rep-judge", judged, [dict(claim_id="n-1", claim_text=text, claim_role="evidence"), dict(claim_id="n-2", claim_text="On balance the bank failures mattered most.", claim_role="analysis")]))
    assert not [f for f in rc2.findings if f.code in ("INT-REQ-004", "INT-REQ-008")], [f.message for f in rc2.findings]


def test_word_bounds_are_measured_over_the_answer_proper():
    body = "The Depression was decisive because it destroyed the security of moderate voters in 1930."
    assert count_answer_words(body + "\n\nVERIFIED: all claims checked and confirmed.") == (count_answer_words(body)[0], 6)
    ch = TranslatorChannel(physics_plan(["specialist"]), signing_key=KEY, config=CFG)
    m, _, _ = ch.request("router", "specialist", "What is the speed? Write no more than 6 words.")
    text = "The speed is fifteen m/s.\n\nVERIFIED: all claims checked and confirmed."
    _, rc = ch.respond(m.message_id, report("specialist", "rep-w", text, [dict(claim_id="w-1", claim_text="The speed is fifteen m/s.", claim_role="quantitative")]))
    words = next(c for c in rc.constraint_results if c.constraint_id == "c1")
    assert words.satisfied is True and "6 words of note or meta-text blocks excluded" in words.detail
    assert not [f for f in rc.findings if f.code == "INT-REQ-005"]


# -------------------------------------------------------------- per-agent task types


def test_per_agent_task_types_travel_on_requests_and_reports():
    plan = two_subject_plan(agent_task_types={"history-specialist": "short_answer"})
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan)
    _, req, reply, rc = deliver_history(hub)
    assert req.task_type == "short_answer" and reply is not None and reply.payload["task_type"] == "short_answer"
    assert not [f for f in rc.findings if f.code == "INT-HANDOFF-010"]
    _, req2, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem.", [POEM])
    assert req2.task_type == "analytical_paragraph"
    assert plan_digest(two_subject_plan()) == plan_digest(two_subject_plan(agent_task_types={})) != plan_digest(plan)
    with pytest.raises(ValueError, match="did not select"):
        two_subject_plan(agent_task_types={"economics-specialist": "essay"})


# ------------------------------------------------- superseded reports in circulation


def test_supersession_names_forwards_and_quoting_reports_and_a_synthesis_citing_the_old_report():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    _, _, reply, _ = deliver_history(hub, "rep-hi-1")
    old = SpecialistReport.model_validate(reply.payload)
    fwd, fr = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, old, in_reply_to=reply.message_id)
    assert fwd is not None and fr.status is TransmissionStatus.ACCEPTED
    peer = SuppliedText(document_id="peer:hi", title="History report relayed through the hub", text=old.original_response)
    m2, _, _ = hub.dispatch(TASK, "english-specialist", ASK_EN, [POEM, peer])
    en = ('The boast "King of Kings" is read against a sonnet that, as the History specialist notes, "was printed in January 1818". '
          'The reversal of "Nothing beside remains" is complete.')
    reply2, rc2 = hub.receive(TASK, m2.message_id, en, agent_id="english-specialist", report_id="rep-en")
    assert reply2 is not None and not [f for f in rc2.findings if f.code == "INT-REQ-003"]
    quoting = [c["claim_id"] for c in reply2.payload["claims"] if any(r["document_id"] == "peer:hi" for r in c.get("source_refs", []))]
    assert quoting
    _, _, reply3, rc3 = deliver_history(hub, "rep-hi-2", HISTORY.replace("January 1818", "January 1819"))
    assert reply3 is not None and any(f.code == "INT-HANDOFF-009" for f in rc3.findings)
    circ = [f for f in rc3.findings if f.code == "INT-HANDOFF-014"]
    assert circ and circ[0].severity == "warning" and "remains in circulation" in circ[0].message
    assert "forwarded by the router to ['english-specialist']" in circ[0].message and fwd.message_id in circ[0].message_ids
    assert "rep-en" in circ[0].report_ids and circ[0].document_ids == ["peer:hi"] and set(quoting) <= set(circ[0].claim_ids)
    assert "no longer occur in the current report" in circ[0].message
    syn = synthesis_of(old, report_ids=["rep-hi-1"])
    r, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert r is not None
    sup = [f for f in rr.findings if f.code == "INT-HANDOFF-014"]
    assert sup and "superseded with report 'rep-hi-2'" in sup[0].message and set(sup[0].report_ids) == {"rep-hi-1", "rep-hi-2"}
    collisions = [f for f in rr.findings if f.code == "INT-LEDGER-014"]
    assert collisions and all("superseded" in f.message for f in collisions)
    fwd2, fr2 = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, old, in_reply_to=reply.message_id)
    assert fwd2 is not None and any(f.code == "INT-HANDOFF-014" and "superseded report" in f.message for f in fr2.findings)


# ------------------------------------------------- translations bound to the claim text


def test_stale_translation_is_a_finding_and_is_neither_delivered_nor_pooled():
    def stale_fn(claim, rep):
        return outcome(claim, rep, speed_problem("a-1", "15"), text_sha=sha256_text("The speed is 15 m/s, measured earlier."))

    ch = TranslatorChannel(physics_plan(["physics-specialist"]), signing_key=KEY, verify_claim_fn=stale_fn, config=CFG)
    claim = dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")
    m, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    reply, rc = ch.respond(m.message_id, report("physics-specialist", "rep-a", "The speed is 15 m/s.", [claim]))
    assert reply is not None  # the report is delivered; the stale outcome is not
    stale = [f for f in rc.findings if f.code == "INT-STALE-011"]
    assert stale and stale[0].severity == "error" and "different text" in stale[0].message and stale[0].claim_ids == ["a-1"]
    assert rc.outcomes == [] and ch.formalized == {} and "INT-STALE-011" in rc.summary
    ch.verify_claim_fn = lambda c, r: outcome(c, r, speed_problem("a-1", "15"), text_sha=sha256_text(c.claim_text))
    m2, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    _, rc2 = ch.respond(m2.message_id, report("physics-specialist", "rep-a2", "The speed is 15 m/s.", [claim]))
    assert rc2.outcomes and "a-1" in ch.formalized and not [f for f in rc2.findings if f.code == "INT-STALE-011"]


def test_conflicts_over_an_ambiguous_pooled_claim_say_so_and_a_synthesis_must_disclose_them():
    problems = {"a-1": speed_problem("a-1", "15"), "b-1": speed_problem("b-1", "16")}

    def verify_fn(claim, rep):
        p = problems.get(claim.claim_id)
        if p is None:
            return None
        status = TranslationStatus.AMBIGUOUS_TRANSLATION if claim.claim_id == "b-1" else TranslationStatus.TRANSLATED
        return outcome(claim, rep, p, status=status, text_sha=sha256_text(claim.claim_text))

    ch = TranslatorChannel(physics_plan(["physics-specialist", "maths-specialist", "combinator"]), signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    m1, _, _ = ch.request("router", "physics-specialist", "What is the speed?")
    m2, _, _ = ch.request("router", "maths-specialist", "Compute 120 divided by 8.")
    ch.respond(m1.message_id, report("physics-specialist", "rep-a", "The speed is 15 m/s.", [dict(claim_id="a-1", claim_text="The speed is 15 m/s.", claim_role="quantitative")]))
    _, r2 = ch.respond(m2.message_id, report("maths-specialist", "rep-b", "The speed is 16 m/s.", [dict(claim_id="b-1", claim_text="The speed is 16 m/s.", claim_role="quantitative")]))
    conflict = [f for f in r2.findings if f.code == "INT-CONFLICT-001"]
    assert conflict and "AMBIGUOUS_TRANSLATION" in conflict[0].message and "['b-1']" in conflict[0].message and "assumed reading" in conflict[0].message
    assert ch.ambiguous_pooled == {"b-1"}

    def syn(conflicts=(), synthesis_id="syn-c"):
        claims = [SynthesizedClaim(claim_id="s-a", text="The speed is 15 m/s.", certainty="probable", source_claim_ids=["a-1"], transformation="carried"),
                  SynthesizedClaim(claim_id="s-b", text="The speed is 16 m/s.", certainty="probable", source_claim_ids=["b-1"], transformation="carried")]
        text = "The speed is 15 m/s. The speed is 16 m/s."
        return Synthesis(synthesis_id=synthesis_id, request_id="req-s", task_id=TASK, combinator_agent_id="combinator", source_report_ids=["rep-a", "rep-b"],
                         claims=claims, conflicts=list(conflicts), text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")

    relayed, rr = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn())
    assert relayed is not None and rr.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    undisclosed = [f for f in rr.findings if f.code == "INT-CONFLICT-002"]
    assert undisclosed and undisclosed[0].severity == "error" and set(undisclosed[0].claim_ids) == {"a-1", "b-1"}
    assert undisclosed[0].formal_result_id in rr.formal_result_ids and set(undisclosed[0].report_ids) == {"rep-a", "rep-b"}
    assert "assumed reading" in undisclosed[0].message
    record = [ConflictRecord(conflict_id="cf-1", claim_ids=["a-1", "b-1"], description="the specialists disagree on the speed")]
    # (round 5: the revised synthesis needs its own id; the same id with the conflict record added is refused, INT-HANDOFF-015)
    reused, rr_reused = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn(conflicts=record))
    assert reused is None and any(f.code == "INT-HANDOFF-015" and "conflicts" in f.message for f in rr_reused.findings)
    disclosed = syn(conflicts=record, synthesis_id="syn-c2")
    _, rr2 = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, disclosed)
    assert not [f for f in rr2.findings if f.code == "INT-CONFLICT-002"] and any(f.code == "INT-CONFLICT-001" for f in rr2.findings)
