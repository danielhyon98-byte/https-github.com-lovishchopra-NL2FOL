"""STEM review, relay history (docs/STEM_DESIGN.md, section 11.6): a relayed or forwarded report carries references to
its earlier receipts and what they left unresolved, so a later transmission that re-checks less (a relay runs without
the request; a forward re-checks nothing) never erases an earlier failed Given check or warning. The combinator and the
router see the accumulated history: each unresolved finding travels as INT-HIST-001 with its own severity, claims and
signed result, and the receipt's ``history`` references every earlier receipt. Controls: a clean arrival leaves the
relay ACCEPTED with the arrival referenced; a carried error never blocks delivery; a refused transmission is no history."""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import ReceiptReference, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.canonical import sha256_hex

from .history_support import HIST, assert_carries_exactly

KEY = b"relay-history-test-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
ASK = "Given v = 20 m/s and t = 4 s, calculate the acceleration."
MISSTATED = "Given: v = 40 m/s and t = 4 s.\na = v/t = 40/4 = 10 m s⁻²."
FAITHFUL = "Given: v = 20 m/s and t = 4 s.\na = v/t = 20/4 = 5 m s⁻²."


def arrive(answer: str, ask: str = ASK):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer",
                                selected_agent_ids=["physics-specialist", "combinator"]))
    m, _req, _ = hub.dispatch("t", "physics-specialist", ask)
    reply, rc = hub.receive("t", m.message_id, answer, agent_id="physics-specialist", report_id="r")
    assert reply is not None
    return ch, rc


def given_failure(receipt):
    return [f for f in receipt.findings if f.code == "INT-SUBJ-004"]


def test_the_arrival_names_the_misstated_given_value():
    _ch, rc = arrive(MISSTATED)
    assert [f.claim_ids for f in given_failure(rc)] == [["s1.1"]]
    assert ("stem-giv-1", False) in [(c.constraint_id, c.satisfied) for c in rc.formal_checks]


def test_a_relay_without_the_request_carries_the_failed_given_check():
    ch, rc = arrive(MISSTATED)
    _msg, relayed = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, ch.transmitted_reports["r"])
    assert relayed.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # before the review: ACCEPTED with no finding
    assert not given_failure(relayed) and not [c for c in relayed.formal_checks if c.constraint_id.startswith("stem-giv")]  # the relay form builds no Given check
    carried = [f for f in relayed.findings if f.code == HIST]
    assert len(carried) == 1 and carried[0].severity == "warning" and carried[0].claim_ids == ["s1.1"]
    assert "INT-SUBJ-004 (warning)" in carried[0].message and rc.receipt_id in carried[0].message
    assert carried[0].formal_result_id == given_failure(rc)[0].formal_result_id  # the signed result travels with it
    assert [h.receipt_id for h in relayed.history] == [rc.receipt_id]
    ref = relayed.history[0]
    assert isinstance(ref, ReceiptReference) and ref.payload_kind == "report" and ref.payload_id == "r" and ref.direction == "specialist_to_router"
    assert [(c.constraint_id, c.satisfied) for c in ref.unresolved_checks] == [("stem-giv-1", False)]
    assert "History: 1 earlier receipt(s)" in relayed.summary and HIST in relayed.summary


def test_a_router_forward_carries_it_too():
    """The forward names the delivery it carries on (``in_reply_to``), as a faithful forward does. Changed in repair round 1
    (re-run review re-5): a forward that names none is now INT-HANDOFF-018 (tests/channel/test_forward_reply_link.py), so
    this test's forward names its delivery and still asserts the strict rule that it adds no finding of its own."""
    ch, rc = arrive(MISSTATED)
    _msg, forwarded = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, ch.transmitted_reports["r"],
                               in_reply_to=ch.delivered_to_router["r"][0])
    assert forwarded.formal_checks == []  # a forward re-checks nothing
    assert_carries_exactly(forwarded, rc)


def test_a_clean_arrival_leaves_the_relay_accepted_with_its_history_referenced():
    ch, rc = arrive(FAITHFUL)
    assert rc.status is TransmissionStatus.ACCEPTED
    _msg, relayed = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, ch.transmitted_reports["r"])
    assert relayed.status is TransmissionStatus.ACCEPTED and relayed.findings == []
    assert [h.receipt_id for h in relayed.history] == [rc.receipt_id] and not relayed.history[0].unresolved


def test_the_history_accumulates_and_each_finding_is_carried_once():
    ch, rc = arrive(MISSTATED)
    report = ch.transmitted_reports["r"]
    _m1, relayed = ch.relay("physics-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, report)
    _m2, forwarded = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, report)
    assert [h.receipt_id for h in forwarded.history] == [rc.receipt_id, relayed.receipt_id]
    assert [f.claim_ids for f in forwarded.findings if f.code == HIST] == [["s1.1"]]  # the relay's carried copy is not carried again
    assert not forwarded.history[1].unresolved_findings  # a receipt's carried findings belong to the receipt they came from


def test_a_carried_error_keeps_its_severity_and_never_blocks_delivery():
    ch, rc = arrive("a = (20 - 0)/4.0 = 6.0 m s⁻²", "A trolley accelerates from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.")
    assert [f.code for f in rc.errors] == ["INT-SUBJ-001"]
    msg, forwarded = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, ch.transmitted_reports["r"])
    assert msg is not None and forwarded.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    assert [(f.code, f.severity, f.claim_ids) for f in forwarded.errors] == [(HIST, "error", ["s1.1"])]


def test_a_refused_transmission_is_no_part_of_the_history():
    ch, rc = arrive(MISSTATED)
    report = ch.transmitted_reports["r"]
    bad, refused = ch.relay("combinator", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, report)  # not the owner: refused
    assert bad is None and refused.status is TransmissionStatus.REJECTED and refused.history == []
    _msg, forwarded = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, report)
    assert [h.receipt_id for h in forwarded.history] == [rc.receipt_id]


def _synthesis(ch, text: str, claim_ids: list[str]) -> Synthesis:
    return Synthesis(synthesis_id="syn", request_id="q", task_id="t", combinator_agent_id="combinator", source_report_ids=["r"],
                     claims=[SynthesizedClaim(claim_id="syn-1", text=text, source_claim_ids=claim_ids, transformation="carried")],
                     text=text, text_sha256=sha256_hex(text), created_at="2026-10-12T00:00:00Z")


def test_a_synthesis_carries_what_concerns_the_claims_it_cites():
    ch, rc = arrive(MISSTATED)
    claims = {c.claim_id: c.claim_text for c in ch.transmitted_reports["r"].claims}
    _msg, cites_given = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(ch, claims["s1.1"], ["s1.1"]))
    carried = [f for f in cites_given.findings if f.code == HIST]
    assert [f.claim_ids for f in carried] == [["s1.1"]] and "INT-SUBJ-004" in carried[0].message
    assert rc.receipt_id in [h.receipt_id for h in cites_given.history]


def test_a_synthesis_of_other_claims_references_the_history_without_carrying_it():
    ch, rc = arrive(MISSTATED)
    claims = {c.claim_id: c.claim_text for c in ch.transmitted_reports["r"].claims}
    _msg, other = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(ch, claims["s1.2"], ["s1.2"]))
    assert not [f for f in other.findings if f.code == HIST]
    assert rc.receipt_id in [h.receipt_id for h in other.history]
