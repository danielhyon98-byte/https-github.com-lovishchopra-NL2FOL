"""Integration gate 1, handoff fixer: the adapters' claim ids and cut claims.

* combinator-faults-9 (critical): the STEM parser numbered its claims ``s{p}.{n}`` with no agent qualifier, so two STEM
  specialists of one branch on one task delivered the same claim ids: the hub charged every correct synthesis of the group
  with INT-LEDGER-014 and INT-LEDGER-002 errors (and a derived INT-LEDGER-023), and the combinator port refused the group's
  input (KIT-CB-001: two source claims share a claim id). The STEM parser now qualifies its ids with the agent on request
  (``qualify_ids``: ``s1.2@ess-specialist``, as the generic parser's ids are, on the main path, the paragraph fallback and the
  tail), and the hub asks for it whenever a report's ids would be ids a report of another agent already delivered on the
  task holds (``channel.bus.needs_qualified_ids``; the overseer's re-parse applies the same rule). A report that collides with
  nothing keeps its ids, so the keys recorded for them (supersession, fixtures, adjudications, the overseer pack's worked
  examples) stay valid.
* overseer handoff 4 (second half): an over-long sentence cut inside a long run of blanks was stripped back to the word
  before the run ('The value is 5 m....', 20 characters), so it no longer read as cut at the contract limit and a faithful
  History transfer failed its audit (OVS-FID-001). ``markdown.truncate_claim_text`` collapses the whitespace runs of an
  over-long text before the cut.
"""
from __future__ import annotations

import dataclasses
import re

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.stem_specialist import StemTextParser
from epinoic_logic.adapters.stem_specialist import parser as stem_parser
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import agent_claim_tag
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integration import combinator_port as CB
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_overseer import EngineKey, KeyRing, TransferAuditor
from epinoic_logic.translate.contracts import sha256_text

KEY = b"integration-gate-1-handoff-adapters-key-01"
SECRET = b"integration-gate-1-handoff-secret-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
PACK = {"name": "combinator-instructions", "version": "1.0", "sha256": "9a" * 32}
CHEM = "A 2.0 mol sample of gas occupies 48 dm³ at room temperature.\n\nThe molar volume is therefore 48 / 2.0 = 24 dm³ mol⁻¹."
ESS = "The pond holds 2.0 mol of dissolved carbon dioxide.\n\nIts concentration is 2.0 / 4.0 = 0.50 mol dm⁻³ in a 4.0 dm³ sample."
GROUP = (("chemistry-specialist", CHEM, "rep-ch", "Chemistry"), ("ess-specialist", ESS, "rep-ess", "Environmental Systems and Societies"))


def stem_report(text: str, agent: str, subject: str, rid: str, **kw):
    return StemTextParser().parse_response(text, request_id="req", task_id="task", report_id=rid, subject=subject, task_type="short_answer",
                                           agent_id=agent, **kw)


def _keyring() -> KeyRing:
    return KeyRing({k: EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, SECRET)


def _group_hub():
    """A hub task with two STEM specialists of one branch (both read by the sciences branch) and a combinator, audited."""
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=TransferAuditor(_keyring(), replay_mode="inline", eager=True, shadow="always"))
    hub.open_task(WorkPlan(plan_id="p", request_id="req-g", task_id="task-g", subject="Chemistry", task_type="short_answer",
                           selected_agent_ids=["chemistry-specialist", "ess-specialist", "combinator"],
                           agent_subjects={"ess-specialist": "Environmental Systems and Societies"}))
    reports = []
    for agent, text, rid, _subject in GROUP:
        m, _req, _rq = hub.dispatch("task-g", agent, "Answer the question.")
        reply, rc = hub.receive("task-g", m.message_id, text, agent_id=agent, report_id=rid)
        assert reply is not None, rc.summary
        reports.append(hub.channels["task-g"].transmitted_reports[rid])
    return hub, reports


# --------------------------------------------------------------------------- agent-qualified STEM claim ids (combinator-faults-9)


def test_the_parser_qualifies_its_ids_with_the_agent_on_request_and_keeps_them_otherwise():
    plain = stem_report(CHEM, "chemistry-specialist", "Chemistry", "rep-ch")
    assert [c.claim_id for c in plain.claims] == ["s1.1", "s2.1"]  # unchanged when nothing collides
    tag = agent_claim_tag("ess-specialist")
    qual = stem_report(ESS, "ess-specialist", "Environmental Systems and Societies", "rep-ess", qualify_ids=True)
    assert [c.claim_id for c in qual.claims] == [f"s1.1@{tag}", f"s2.1@{tag}"]
    assert all(x in {c.claim_id for c in qual.claims} for c in qual.claims for x in c.supporting_claim_ids)  # supports name its own ids
    maths = StemTextParser(mode="mathematics").parse_response("Solve x + 2 = 5.\n\nx = 3.", request_id="r", task_id="t", report_id="rep-m",
                                                              subject="Mathematics: Analysis and Approaches", task_type="short_answer",
                                                              agent_id="maths-specialist", qualify_ids=True)
    assert all(re.fullmatch(r"m\d+\.\d+@maths-specialist", c.claim_id) for c in maths.claims), [c.claim_id for c in maths.claims]


def test_the_paragraph_fallback_and_the_tail_are_qualified_too(monkeypatch):
    real = stem_parser.build_document

    def no_statements(*a, **kw):
        return dataclasses.replace(real(*a, **kw), statements=())
    monkeypatch.setattr(stem_parser, "build_document", no_statements)
    rep = stem_report(CHEM, "chemistry-specialist", "Chemistry", "rep-f", qualify_ids=True)
    assert [c.claim_id for c in rep.claims] == ["s1.1@chemistry-specialist", "s2.1@chemistry-specialist"]
    monkeypatch.undo()
    long = "\n".join(f"x{k} = {k}" for k in range(600))
    rep = stem_report(long, "physics-specialist", "Physics", "rep-t", qualify_ids=True)
    assert rep.claims[-1].claim_id == "s.tail@physics-specialist"
    assert any("merged into claim s.tail@physics-specialist " in u for u in rep.unresolved_issues), rep.unresolved_issues


def test_two_stem_agents_of_one_branch_on_one_task_deliver_disjoint_ids_and_the_audit_reproduces_them():
    hub, reports = _group_hub()
    try:
        chem, ess = reports
        assert [c.claim_id for c in chem.claims] == ["s1.1", "s2.1"]  # the first keeps its ids
        tag = agent_claim_tag("ess-specialist")
        assert [c.claim_id for c in ess.claims] == [f"s1.1@{tag}", f"s2.1@{tag}"]  # the second would collide: qualified
        assert not {c.claim_id for c in chem.claims} & {c.claim_id for c in ess.claims}
        receipts = hub.receipts("task-g")
        assert receipts and "INT-REQ-016" not in {f.code for r in receipts for f in r.findings}  # no collision left to name
        audit = hub.audit("task-g")
        codes = {f.code for f in audit.report.findings}
        assert "OVS-CUST-006" not in codes, [f.message[:200] for f in audit.report.findings if f.code == "OVS-CUST-006"]
        # the combinator port builds the group's input (it refused it with KIT-CB-001 before the fix)
        sources = [CB.source_report(r.model_dump(mode="json"), "sciences") for r in reports]
        inp = CB.build_input({"task_id": "t_" + "0" * 31 + "1", "request_id": "a_" + "0" * 31 + "1"}, sources, PACK)
        assert len({c.claim_id for s in inp.sources for c in s.claims}) == 4
        # a verbatim synthesis of both reports raises no shared-id error
        claims = [{"claim_id": f"k{i}", "text": c.claim_text, "source_claim_ids": [c.claim_id], "transformation": "carried", "materiality": c.materiality}
                  for i, c in enumerate(c for r in reports for c in r.claims)]
        text = " ".join(c["text"] for c in claims)
        syn = {"synthesis_id": "syn-g", "request_id": "req-g", "task_id": "task-g", "combinator_agent_id": "combinator",
               "source_report_ids": ["rep-ch", "rep-ess"], "claims": claims, "ledger": [], "conflicts": [], "text": text,
               "text_sha256": sha256_text(text), "created_at": "2026-10-31T15:00:00Z"}
        msg, rc = hub.channels["task-g"].relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
        assert msg is not None and not {f.code for f in rc.findings} & {"INT-LEDGER-014", "INT-LEDGER-002", "INT-LEDGER-023"}, \
            [(f.code, f.message[:160]) for f in rc.findings]
    finally:
        hub.close()


def test_control_a_stem_and_a_mathematics_report_keep_their_ids():
    plan = WorkPlan(plan_id="p", request_id="req-m", task_id="task-m", subject="Physics", task_type="short_answer",
                    selected_agent_ids=["physics-specialist", "maths-specialist"], agent_subjects={"maths-specialist": "Mathematics: Analysis and Approaches"})
    ch = TranslatorChannel(plan, signing_key=KEY, config=CFG)
    ids = []
    for agent, text, rid in (("physics-specialist", "a = (20 - 0)/4.0 = 5.0 m s⁻²", "rep-p"), ("maths-specialist", "$4a = 20 \\Rightarrow a = 5$", "rep-m")):
        m, _req, rr = ch.request("router", agent, "Answer the question.")
        assert rr.status is TransmissionStatus.ACCEPTED
        msg, rc = ch.respond_text(m.message_id, text, agent_id=agent, report_id=rid)
        assert msg is not None, rc.summary
        ids.append([c.claim_id for c in ch.transmitted_reports[rid].claims])
    assert ids == [["s1.1"], ["m1.1"]]  # different letters: nothing collides, nothing is qualified


# --------------------------------------------------------------------------- a claim cut inside a run of blanks (overseer handoff 4)


@pytest.mark.parametrize("fill", [" ", "\t", " \n"])
def test_an_over_long_claim_has_its_blank_runs_collapsed_before_the_cut(fill):
    assert md.truncate_claim_text("  a short claim  ") == "a short claim"  # within the limit: as it is
    assert md.truncate_claim_text("The value is 5 m. " + fill * 10000 + "It is 6 m.") == "The value is 5 m. It is 6 m."
    long = "The value is 5 m. " + fill * 10000 + "word " * 1000
    cut = md.truncate_claim_text(long)
    assert cut.endswith("...") and md.MAX_CLAIM_TEXT_CHARS - 3 <= len(cut) <= md.MAX_CLAIM_TEXT_CHARS, len(cut)


@pytest.mark.parametrize("fill", [" ", "\t"])
def test_a_history_answer_with_a_long_blank_run_passes_its_audit(fill):
    keyring = KeyRing({k: EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, b"integration-gate-1-handoff-secret-0123456789")
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=TransferAuditor(keyring, replay_mode="inline", eager=True, shadow="always"))
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="History", task_type="short_answer",
                               selected_agent_ids=["history-specialist"]))
        m, _req, _rq = hub.dispatch("t", "history-specialist", "Answer the question.")
        reply, rc = hub.receive("t", m.message_id, "The value is 5 m. " + fill * 10000 + "It is 6 m.", agent_id="history-specialist", report_id="r1")
        audit = hub.audit("t")
    finally:
        hub.close()
    assert reply is not None and rc.status.value.startswith("ACCEPTED")
    assert "OVS-FID-001" not in {f.code for f in audit.report.findings}, [f.message[:200] for f in audit.report.findings]
    assert getattr(audit.state, "value", audit.state) in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
