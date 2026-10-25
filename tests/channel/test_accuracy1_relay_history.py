"""Accuracy round 1, DV2-05: what a relay or a synthesis carries from the receipts of the reports it builds on.

A forward of a report to a peer specialist (which builds on the report as material) and a synthesis (which restates the
claims it cites) carried every unresolved finding of the reports' earlier receipts as INT-HIST-001, heuristic readings
included, so a correct report's false coverage, layout, derived-figure or parse warnings were spread onto the transmissions
built on it, which then read ACCEPTED_WITH_FINDINGS where the committed base reads ACCEPTED. They now carry the errors and
the warnings that state a fault the content was found to have (``channel.bus._DECIDED_WARNINGS``: a branch check that
failed under a reading the report did not state, a named argument defect, a system check result handed on as content; and
``_DECIDED_SUBJECT_WARNINGS``, a subject finding that names a STEM defect);
every other warning stays listed in the history the receipt references. A forward or a relay to the combinator, which
composes the answer from the report, still carries every unresolved finding.

Positive cases (the false carry is gone), caught twins (a decided fault and an error are still carried) and controls (the
combinator still receives everything), in wording of this round's own; nothing from a case is executed."""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel.gate import assess_response
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.canonical import sha256_hex

from .history_support import HIST, assert_carries_exactly, assert_forwards_to_a_peer

KEY = b"accuracy1-relay-history-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
ASK = "Given v = 30 m/s and t = 6 s, calculate the acceleration."
MISSTATED = "Given: v = 60 m/s and t = 6 s.\na = v/t = 60/6 = 10 m s⁻²."
FAITHFUL = "Given: v = 30 m/s and t = 6 s.\na = v/t = 30/6 = 5 m s⁻²."
WRONG_SUM = "a = (30 - 0)/6.0 = 6.0 m s⁻²"
#: A correct answer with a sentence the derived-figure reading cannot decide (a heuristic warning on that claim, CORE-QNT-001).
NOTED = FAITHFUL + " The speed roughly doubled over the run."
PEER = "maths-specialist"


def _arrive(answer: str, ask: str = ASK):
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer",
                                selected_agent_ids=["physics-specialist", PEER, "combinator"],
                                agent_subjects={PEER: "Mathematics: Analysis and Approaches"}))
    m, _req, _ = hub.dispatch("t", "physics-specialist", ask)
    reply, rc = hub.receive("t", m.message_id, answer, agent_id="physics-specialist", report_id="r")
    assert reply is not None
    return ch, rc, reply


def _to_peer(ch, reply):
    return ch.relay("router", AgentRole.ROUTER, PEER, AgentRole.SPECIALIST, ch.transmitted_reports["r"], in_reply_to=reply.message_id)


def _heuristic_only(rc) -> bool:
    return bool([f for f in rc.findings if f.severity == "warning"]) and not [f for f in rc.findings if f.severity == "error"] \
        and not [f for f in rc.findings if f.code in ("INT-SUBJ-004", "INT-ARG-001", "INT-REQ-017")]


def _synthesis(ch, claim_ids: list[str]) -> Synthesis:
    claims = {c.claim_id: c.claim_text for c in ch.transmitted_reports["r"].claims}
    text = " ".join(claims[c] for c in claim_ids)
    return Synthesis(synthesis_id="syn", request_id="q", task_id="t", combinator_agent_id="combinator", source_report_ids=["r"],
                     claims=[SynthesizedClaim(claim_id="syn-1", text=text, source_claim_ids=claim_ids, transformation="carried")],
                     text=text, text_sha256=sha256_hex(text), created_at="2026-10-25T00:00:00Z")


# ------------------------------------------------------------------------------------- a forward to a peer specialist

def test_a_forward_to_a_peer_carries_no_heuristic_warning_of_a_correct_report():
    # a correct answer whose arrival is left with a heuristic reading only (the coverage of an item the plain working does
    # not name in words): the peer receives the report clean, and the warning stays in the history the forward references
    ch, rc, reply = _arrive(FAITHFUL, ASK + " Explain what the answer shows about the motion.")
    assert _heuristic_only(rc), [(f.code, f.severity) for f in rc.findings]
    _msg, fwd = _to_peer(ch, reply)
    assert not [f for f in fwd.findings if f.code == HIST]
    assert_forwards_to_a_peer(fwd, rc)
    assert fwd.status is TransmissionStatus.ACCEPTED


def test_caught_twin_a_forward_to_a_peer_still_carries_a_failed_given_check():
    ch, rc, reply = _arrive(MISSTATED)
    assert [f.code for f in rc.findings if f.code == "INT-SUBJ-004"]
    _msg, fwd = _to_peer(ch, reply)
    carried = [f for f in fwd.findings if f.code == HIST]
    assert [f.severity for f in carried] == ["warning"] and "INT-SUBJ-004 (warning)" in carried[0].message
    assert carried[0].formal_result_id is not None  # the signed result travels with it
    assert_forwards_to_a_peer(fwd, rc)


def test_caught_twin_a_forward_to_a_peer_still_carries_an_error():
    ch, rc, reply = _arrive(WRONG_SUM, "A trolley accelerates from rest to 30 m s⁻¹ in 6.0 s. Calculate its acceleration.")
    assert [f.code for f in rc.errors] == ["INT-SUBJ-001"]
    _msg, fwd = _to_peer(ch, reply)
    assert [(f.code, f.severity) for f in fwd.errors] == [(HIST, "error")]
    assert fwd.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS


def test_control_a_forward_to_the_combinator_still_carries_every_unresolved_finding():
    ch, rc, reply = _arrive(FAITHFUL, ASK + " Explain what the answer shows about the motion.")
    assert _heuristic_only(rc)
    _msg, fwd = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, ch.transmitted_reports["r"], in_reply_to=reply.message_id)
    assert_carries_exactly(fwd, rc)
    assert fwd.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS


# --------------------------------------------------------------------------------------------------------- a synthesis

def test_a_synthesis_carries_no_heuristic_warning_of_the_claims_it_cites():
    ch, rc, _reply = _arrive(NOTED)
    [note] = [sf for sf in rc.structural_findings if sf.code == "CORE-QNT-001" and sf.severity == "warning"]
    _msg, syn = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(ch, list(note.claim_ids)))
    assert not [f for f in syn.findings if f.code == HIST], [f.message[:160] for f in syn.findings]
    [ref] = [h for h in syn.history if h.receipt_id == rc.receipt_id]  # the history stays referenced, the note listed there
    assert "CORE-QNT-001" in [sf.code for sf in ref.unresolved_subject_findings]


def test_a_forward_to_a_peer_carries_no_heuristic_subject_finding():
    ch, rc, reply = _arrive(NOTED)
    assert [sf for sf in rc.structural_findings if sf.code == "CORE-QNT-001" and sf.severity == "warning"]
    _msg, fwd = _to_peer(ch, reply)
    assert not [f for f in fwd.findings if f.code == HIST and "CORE-QNT-001" in f.message]
    [ref] = [h for h in fwd.history if h.receipt_id == rc.receipt_id]
    assert "CORE-QNT-001" in [sf.code for sf in ref.unresolved_subject_findings]


def test_caught_twin_a_synthesis_still_carries_a_failed_given_check_of_a_cited_claim():
    ch, rc, _reply = _arrive(MISSTATED)
    [given] = [f for f in rc.findings if f.code == "INT-SUBJ-004"]
    _msg, syn = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(ch, list(given.claim_ids)))
    carried = [f for f in syn.findings if f.code == HIST]
    assert [f.claim_ids for f in carried] == [list(given.claim_ids)] and "INT-SUBJ-004" in carried[0].message


# ------------------------------------------------------------------ the gate reads a carried fault once (moved, same rule)

def test_a_carried_fault_is_counted_once_and_counted_when_its_source_is_not_read():
    """The mechanism of tests/channel/test_response_gate_b13.py::test_a_finding_carried_from_a_receipt_the_gate_reads_is_not_counted_twice,
    pinned on a forward that carries a decided fault: read with its source receipt, the carried finding is not counted
    twice; read without it, the carried finding counts as the finding it carries."""
    ch, rc, reply = _arrive(MISSTATED)
    _msg, fwd = _to_peer(ch, reply)
    carried = [f for f in fwd.findings if f.code == HIST]
    assert carried and all(rc.receipt_id in f.message for f in carried)
    both = assess_response([rc, fwd], synthesis_required=False)
    assert not [c for c in both.checks if c.check.startswith("carried ")]
    alone = assess_response([fwd], synthesis_required=False)
    assert [c for c in alone.checks if c.check.startswith("carried ")]


# ------------------------------------------------------------------ a STEM defect of the subject findings is still carried

def test_caught_twin_a_forward_to_a_peer_and_a_synthesis_still_carry_a_stem_defect():
    # a wrong formula (½mv for the kinetic energy): the arrival names it among its subject findings at warning (a named STEM
    # defect and a dimension error), and both stay carried onto the forward to a peer and onto a synthesis citing the claim
    ch, rc, reply = _arrive("Ek = ½mv = 0.5 × 2.0 × 3.0 = 3.0 J.", "A trolley of mass 2.0 kg moves at 3.0 m s⁻¹. Calculate its kinetic energy. [2 marks]")
    stem = sorted(sf.code for sf in rc.structural_findings if sf.severity == "warning" and sf.code.startswith("ST-"))
    assert "ST-REF-001" in stem and "ST-DIM-001" in stem
    _msg, fwd = _to_peer(ch, reply)
    carried = [f for f in fwd.findings if f.code == HIST]
    assert sorted(code for code in stem if any(code in f.message for f in carried)) == stem
    claim_ids = sorted({cid for sf in rc.structural_findings if sf.code in stem for cid in sf.claim_ids})
    _msg, syn = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(ch, claim_ids))
    assert [code for code in stem if any(code in f.message for f in syn.findings if f.code == HIST)] == stem
