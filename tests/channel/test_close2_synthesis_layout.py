"""Close round 2 of the argument-diagnosis regression review, DIFF-05 (in part): a synthesis carried the subject findings its
source reports' arrivals raised about their paragraphs and sentence style (HI-STR-001 "body paragraph 1 has no judgement
move", ES-STR-001 "body paragraph 4 carries 0 quotation(s)", ES-STY-003) as INT-HIST-001 warnings, so a finding about a
report's layout, false on many literary and historical answers in both trees, was spread onto a synthesis that has no such
paragraphs; the committed base kept those syntheses clean. A synthesis restates the claims it cites, never the report's
paragraphs, so it no longer carries a layout finding (``bus._LAYOUT_PREFIXES``); the finding stays in the history the
synthesis references, and the report itself, which is the same text, still has it: a relay names it again and a router
forward carries it. Every other finding of the history (a failed Given check, an error of a check) is carried as before.

What this round leaves of DIFF-05 (docs/ARGUMENT_DIAGNOSTICS.md, section 13): the relays, and the errors and non-layout
warnings a synthesis carries from a source receipt that raised them falsely in both trees.

Wording of this round's own; the positive was checked to fail on the tree before the round."""
from __future__ import annotations

import json
from pathlib import Path

from epinoic_logic.adapters.history_specialist import fixtures
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.canonical import sha256_hex

from .history_support import HIST
from .test_relay_history import MISSTATED, arrive
from .test_relay_history import _synthesis as physics_synthesis

KEY = b"close2-synthesis-layout-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
CORPUS = Path(__file__).resolve().parents[2] / "docs" / "qa_corpus" / "history"


def _arrival():
    text = json.loads((CORPUS / "mutations" / "missing_judgement.json").read_text())["text"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="essay",
                                selected_agent_ids=["history-specialist", "combinator"]))
    m, _req, _ = hub.dispatch("t", "history-specialist", fixtures.QUESTION)
    reply, rc = hub.receive("t", m.message_id, text, agent_id="history-specialist", report_id="rep-h")
    assert reply is not None
    return ch, rc


def _layout(rc) -> list:
    return [sf for sf in rc.structural_findings if sf.code == "HI-STR-001"]


def _carried_layout(receipt) -> list:
    return [f for f in receipt.findings if f.code == HIST and "HI-STR-001" in f.message]


def _synthesis(ch, claim_ids: list[str]) -> Synthesis:
    claims = {c.claim_id: c.claim_text for c in ch.transmitted_reports["rep-h"].claims}
    text = " ".join(claims[c] for c in claim_ids)
    return Synthesis(synthesis_id="syn", request_id="q", task_id="t", combinator_agent_id="combinator", source_report_ids=["rep-h"],
                     claims=[SynthesizedClaim(claim_id="syn-1", text=text, source_claim_ids=claim_ids, transformation="carried")],
                     text=text, text_sha256=sha256_hex(text), created_at="2026-10-24T00:00:00Z")


def test_a_synthesis_carries_no_layout_finding_of_its_source_report():
    ch, rc = _arrival()
    [layout] = _layout(rc)  # the arrival raises the paragraph finding on every claim of its paragraph, the point included
    point = layout.claim_ids[0]
    _msg, syn = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, _synthesis(ch, [point]))
    assert not _carried_layout(syn), [f.message[:160] for f in syn.findings]
    # the finding stays in the history the synthesis references
    [ref] = [h for h in syn.history if h.receipt_id == rc.receipt_id]
    assert "HI-STR-001" in [sf.code for sf in ref.unresolved_subject_findings]


def test_control_the_report_itself_keeps_its_layout_finding_on_a_relay_and_a_forward():
    ch, rc = _arrival()
    assert _layout(rc)
    report = ch.transmitted_reports["rep-h"]
    _msg, relayed = ch.relay("history-specialist", AgentRole.SPECIALIST, "combinator", AgentRole.COMBINATOR, report)
    assert "HI-STR-001" in [sf.code for sf in relayed.structural_findings]  # the same text, read again: named as before the round
    _msg, forwarded = ch.relay("router", AgentRole.ROUTER, "combinator", AgentRole.COMBINATOR, report, in_reply_to=ch.delivered_to_router["rep-h"][0])
    assert _carried_layout(forwarded)  # a forward re-checks nothing and carries it


def test_control_a_synthesis_still_carries_a_failed_given_check_of_the_claim_it_cites():
    ch, rc = arrive(MISSTATED)
    claims = {c.claim_id: c.claim_text for c in ch.transmitted_reports["r"].claims}
    _msg, syn = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, physics_synthesis(ch, claims["s1.1"], ["s1.1"]))
    carried = [f for f in syn.findings if f.code == HIST]
    assert [f.claim_ids for f in carried] == [["s1.1"]] and "INT-SUBJ-004" in carried[0].message
