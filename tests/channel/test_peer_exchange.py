"""Two specialists of different subjects on one task, exchanging outputs only through the
hub: the plan assigns each agent its subject (``WorkPlan.agent_subjects``), the channel
serves each agent through its own branch, and the router hands a delivered report to the
peer with the forward contract, which the channel checks against what was delivered."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.integrity.contracts import plan_digest
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

KEY = b"peer-exchange-test-key-0123456789ab"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
TASK = "task-p"
POEM = SuppliedText(document_id="doc-poem", title="Sonnet", text="My name is Ozymandias, King of Kings; Look on my Works, ye Mighty, and despair! Nothing beside remains.")
HISTORY = ("The sonnet was printed in January 1818. Egyptian antiquities had reached Britain in quantity: a colossal head of Ramesses II "
           "reached London in 1817. Britain after Waterloo, fought on 18 June 1815, was a country of postwar distress. "
           "Dates other than the poem's own are from memory; check your notes.")


def two_subject_plan() -> WorkPlan:
    return WorkPlan(plan_id="plan-p", request_id="req-p", task_id=TASK, subject="English A: Literature", task_type="analytical_paragraph",
                    selected_agent_ids=["history-specialist", "english-specialist", "dummy-combinator"],
                    allowed_document_ids=["doc-poem", "peer:hi"], agent_subjects={"history-specialist": "History"})


def deliver_history(hub: RouterHub):
    m, req, rq = hub.dispatch(TASK, "history-specialist", "In one paragraph of no more than 200 words, outline the historical context of the poem with dated evidence.")
    reply, rc = hub.receive(TASK, m.message_id, HISTORY, agent_id="history-specialist", report_id="rep-hi")
    return m, req, reply, rc


# ------------------------------------------------------------------ plan contract


def test_agent_subjects_must_name_selected_agents_and_keep_single_subject_digests():
    with pytest.raises(ValueError, match="did not select"):
        WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["a"], agent_subjects={"b": "Economics"})
    with pytest.raises(ValueError, match="non-empty"):
        WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["a"], agent_subjects={"a": "  "})
    single = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["a"])
    explicit = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["a"], agent_subjects={})
    assert plan_digest(single) == plan_digest(explicit)
    multi = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["a"], agent_subjects={"a": "Economics"})
    assert plan_digest(multi) != plan_digest(single)


# ------------------------------------------------------------- per-agent branch


def test_each_agent_is_served_by_its_own_subject_branch_on_one_channel():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(two_subject_plan())
    m, req, reply, rc = deliver_history(hub)
    assert req.subject == "History" and reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert rc.branch == "history" and reply.payload["subject"] == "History"
    assert not [f for f in rc.findings if f.code == "INT-HANDOFF-003"], [f.message for f in rc.findings]
    codes = {sf.code for sf in rc.structural_findings}
    assert codes and all(c.startswith(("HI-", "CORE-")) for c in codes)
    m2, req2, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem. Quote from the poem.", [POEM])
    assert req2.subject == "English A: Literature"
    text = 'Shelley undermines the king\'s boast: the pedestal\'s "King of Kings" is answered by "Nothing beside remains". The reversal is complete.'
    reply2, rc2 = hub.receive(TASK, m2.message_id, text, agent_id="english-specialist", report_id="rep-en")
    assert reply2 is not None and rc2.branch == "english" and reply2.payload["subject"] == "English A: Literature"
    assert all(sf.code.startswith(("ES-", "CORE-")) for sf in rc2.structural_findings)
    assert not [f for f in rc2.findings if f.code == "INT-HANDOFF-003"]


def test_unparseable_text_is_rejected_by_the_agents_own_branch():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(two_subject_plan())
    m, _, _ = hub.dispatch(TASK, "history-specialist", "Outline the context.")
    reply, rc = hub.receive(TASK, m.message_id, "   ", agent_id="history-specialist", report_id="rep-x")
    assert reply is None and rc.status is TransmissionStatus.REJECTED and rc.branch == "history"
    assert any(f.code == "INT-REQ-009" and "branch history" in f.message for f in rc.errors)


# --------------------------------------------------------------- router forward


def test_router_forwards_a_delivered_report_unchanged_and_the_peer_quotes_it_through_the_hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    m, _, reply, _ = deliver_history(hub)
    report = SpecialistReport.model_validate(reply.payload)
    fwd, fr = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, report, in_reply_to=reply.message_id)
    assert fwd is not None and fr.status is TransmissionStatus.ACCEPTED, [f.model_dump() for f in fr.findings]
    assert fwd.contract == "specialist_report_forward/1.0" and fwd.payload_sha256 == reply.payload_sha256
    assert not [f for f in fr.findings if f.code == "INT-ENV-001"]  # a forward to another recipient is not a replay
    peer_doc = SuppliedText(document_id="peer:hi", title="History specialist report relayed through the hub", text=report.original_response)
    m2, req2, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem against the historical context. Quote from the poem and from the History specialist.", [POEM, peer_doc])
    good = ('The boast "King of Kings" is read against a Britain that, as the History specialist notes, "was a country of postwar distress". '
            'The reversal of "Nothing beside remains" is complete.')
    reply2, rc2 = hub.receive(TASK, m2.message_id, good, agent_id="english-specialist", report_id="rep-en-good")
    assert reply2 is not None and not [f for f in rc2.findings if f.code == "INT-REQ-003"]
    bad = ('The boast "King of Kings" is read against a Britain that, as the History specialist notes, "was a country of postwar prosperity". '
           'The reversal of "Nothing beside remains" is complete.')
    m3, _, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem against the historical context. Quote from the poem and from the History specialist.", [POEM, peer_doc])
    reply3, rc3 = hub.receive(TASK, m3.message_id, bad, agent_id="english-specialist", report_id="rep-en-bad")
    misq = [f for f in rc3.errors if f.code == "INT-REQ-003"]
    # the peer's words were altered: the report is delivered WITH an error finding naming the claim, so the router can act
    assert misq and misq[0].claim_ids and rc3.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and reply3 is not None
    assert "INT-REQ-003" in rc3.summary


def test_router_cannot_forward_an_altered_or_undelivered_report():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    m, _, reply, _ = deliver_history(hub)
    report = SpecialistReport.model_validate(reply.payload)
    altered_text = report.original_response.replace("January 1818", "January 1819")
    # a consistent forgery: the text, its digest and the claims all changed together, so the payload still re-validates
    altered = SpecialistReport.model_validate({**report.model_dump(mode="json", exclude_none=True), "original_response": altered_text, "response_sha256": sha256_text(altered_text),
                                               "claims": [{**c.model_dump(mode="json", exclude_none=True), "claim_text": c.claim_text.replace("January 1818", "January 1819")} for c in report.claims]})
    fwd, fr = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, altered, in_reply_to=reply.message_id)
    assert fwd is None and fr.status is TransmissionStatus.REJECTED
    assert any(f.code == "INT-HANDOFF-013" and "altered in transit" in f.message for f in fr.errors)
    ghost = SpecialistReport.model_validate({**report.model_dump(mode="json", exclude_none=True), "report_id": "rep-ghost",
                                             "claims": [{**c.model_dump(mode="json", exclude_none=True), "report_id": "rep-ghost"} for c in report.claims]})
    fwd2, fr2 = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, ghost)
    assert fwd2 is None and any(f.code == "INT-HANDOFF-013" and "never delivered" in f.message for f in fr2.errors)


def test_a_specialist_may_not_issue_the_forward_contract_and_a_router_may_not_issue_a_report():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    m, _, reply, _ = deliver_history(hub)
    report = SpecialistReport.model_validate(reply.payload)
    # a specialist relaying a report it did not write under its own name is role impersonation on the reply check
    fwd, fr = ch.relay("english-specialist", AgentRole.SPECIALIST, "router", AgentRole.ROUTER, report, in_reply_to=reply.message_id)
    assert fwd is None and any(f.code == "INT-ENV-010" for f in fr.errors)
    # and a router that issues a report under the report contract (not the forward) is role impersonation
    from epinoic_logic.integrity import AgentMessage
    from epinoic_logic.integrity.contracts import payload_hash
    payload = report.model_dump(mode="json", exclude_none=True)
    msg = AgentMessage(message_id="m-router-report", request_id=report.request_id, task_id=report.task_id, sender_agent_id="router", sender_role=AgentRole.ROUTER,
                       recipient_role=AgentRole.SPECIALIST, recipient_agent_id="english-specialist", contract="specialist_report/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at="2026-10-11T11:00:00Z")
    assert [f.code for f in ch.log.accept(msg)] == ["INT-ENV-007"]


# ----------------------------------------------------------- paragraph layout


def test_paragraph_bound_overrun_is_a_layout_warning_but_a_word_bound_overrun_is_an_error():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-l", request_id="req-l", task_id=TASK, subject="English A: Literature", task_type="analytical_paragraph", selected_agent_ids=["english-specialist"], allowed_document_ids=["doc-poem"]))
    m, req, _ = hub.dispatch(TASK, "english-specialist", "Write one analytical paragraph on power in the poem. Quote from the poem. Write no more than 20 words.", [POEM])
    four_blocks = ('The boast "King of Kings" is hollow.\n\nThe "Works" are gone.\n\nOnly "Nothing beside remains".\n\nUltimately the sands win and the boast is answered by the ruin that frames it.')
    reply, rc = hub.receive(TASK, m.message_id, four_blocks, agent_id="english-specialist", report_id="rep-layout")
    assert reply is not None
    para = [f for f in rc.findings if f.code == "INT-REQ-005" and "paragraphs" in f.message]
    words = [f for f in rc.findings if f.code == "INT-REQ-005" and "words" in f.message]
    assert para and all(f.severity == "warning" for f in para) and "blocks" in para[0].message
    assert words and all(f.severity == "error" for f in words)


# ------------------------------------------------------- ledger scope on revision


def _synthesis_citing(report_ids: list[str], claims: list[tuple[str, str, list[str]]]) -> "Synthesis":
    from epinoic_logic.integrity import Synthesis, SynthesizedClaim
    text = " ".join(t for _, t, _ in claims)
    return Synthesis(synthesis_id="syn-1", request_id="req-p", task_id=TASK, combinator_agent_id="dummy-combinator", source_report_ids=report_ids,
                     claims=[SynthesizedClaim(claim_id=cid, text=t, certainty="probable", source_claim_ids=src, transformation="paraphrased") for cid, t, src in claims],
                     ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")


def test_synthesis_accounts_for_the_agents_current_report_not_the_superseded_one():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    first = "The sonnet was printed in January 1818. Egyptian antiquities had reached Britain in quantity. Dates other than the poem's own are from memory; check your notes."
    m1, _, _ = hub.dispatch(TASK, "history-specialist", "Outline the context in one paragraph.")
    hub.receive(TASK, m1.message_id, first, agent_id="history-specialist", report_id="rep-hi-1")
    m2, _, _ = hub.dispatch(TASK, "history-specialist", "Outline the context in one paragraph.")
    reply2, rc2 = hub.receive(TASK, m2.message_id, HISTORY, agent_id="history-specialist", report_id="rep-hi-2")
    assert any(f.code == "INT-HANDOFF-009" for f in rc2.findings)  # the agent re-stated its claim ids: rep-hi-1 is superseded
    material = [c["claim_id"] for c in reply2.payload["claims"] if c["materiality"] == "material"]
    syn = _synthesis_citing(["rep-hi-2"], [(f"s{i}", c["claim_text"], [c["claim_id"]]) for i, c in enumerate(reply2.payload["claims"]) if c["claim_id"] in material])
    relayed, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    codes = {f.code for f in rr.findings}
    assert relayed is not None and not codes & {"INT-LEDGER-014", "INT-LEDGER-002", "INT-LEDGER-008"}, [f.message for f in rr.findings]
    # citing the superseded report alongside the current one mixes two versions of the same claim ids
    mixed = _synthesis_citing(["rep-hi-1", "rep-hi-2"], [(f"s{i}", c["claim_text"], [c["claim_id"]]) for i, c in enumerate(reply2.payload["claims"]) if c["claim_id"] in material])
    _, rr2 = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, mixed)
    assert any(f.code == "INT-LEDGER-014" for f in rr2.findings)


def test_unaccounted_supporting_claims_are_one_note_per_report():
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(two_subject_plan())
    _, _, reply, _ = deliver_history(hub)
    claims = reply.payload["claims"]
    material = [c for c in claims if c["materiality"] == "material"]
    supporting = [c for c in claims if c["materiality"] != "material"]
    assert material and len(supporting) >= 2
    syn = _synthesis_citing(["rep-hi"], [(f"s{i}", c["claim_text"], [c["claim_id"]]) for i, c in enumerate(material)])
    _, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    notes = [f for f in rr.findings if f.code == "INT-LEDGER-022"]
    assert len(notes) == 1 and set(notes[0].claim_ids) == {c["claim_id"] for c in supporting} and notes[0].severity == "info"
