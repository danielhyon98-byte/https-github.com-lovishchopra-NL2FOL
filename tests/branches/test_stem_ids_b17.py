"""B17: STEM claim ids are namespaced by agent when two agents deliver in one task.

The STEM parser numbers claims by statement (``s1.1``); two agents of one STEM branch (Chemistry and ESS) delivering on one
task held the same ids, so the channel named the collision (INT-REQ-016) and a synthesis citing ``s1.1`` could not be
accounted for. ``StemTextParser`` takes the task's agents (``task_agent_ids``, :attr:`accepts_task_agents`): with two or
more, every id carries the agent's qualifier, as the generic branch's ids do (``s1.1@ess-specialist``); with one, ids are
unchanged. The STEM pack maps its checks to the qualified ids.
"""
from __future__ import annotations

from epinoic_logic.adapters.stem_specialist.parser import StemTextParser
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"b17-test-key-0123456789abcdef0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
AGENTS = ["chemistry-specialist", "ess-specialist"]
WORK = {
    "chemistry-specialist": ("Calculate the mass of 0.250 mol of NaCl (M = 58.5 g mol⁻¹).", "m = nM = 0.250 × 58.5 = 14.6 g.\nSo the mass is 14.6 g.",
                             "Chemistry"),
    "ess-specialist": ("CO2 rose from 280 to 421 ppm; find the percentage increase.", "The increase is (421 − 280) ÷ 280 × 100 = 50.4%.\nSo it is about 50%.",
                       "Environmental Systems and Societies"),
}


def _parse(agent: str, task_agents=None):
    request, answer, subject = WORK[agent]
    return StemTextParser(agent_id=agent).parse_response(answer, request_id="q", task_id="t", report_id="r-" + agent, subject=subject,
                                                        task_type="structured_question", agent_id=agent, request_text=request,
                                                        task_agent_ids=task_agents)


def _hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Chemistry", task_type="structured_question", selected_agent_ids=AGENTS,
                           agent_subjects={"ess-specialist": "Environmental Systems and Societies"}))
    return hub


def test_two_agent_ids_are_distinct():
    a, b = _parse("chemistry-specialist", AGENTS), _parse("ess-specialist", AGENTS)
    ids_a, ids_b = [c.claim_id for c in a.claims], [c.claim_id for c in b.claims]
    assert ids_a == ["s1.1@chemistry-specialist", "s1.2@chemistry-specialist"] and ids_b == ["s1.1@ess-specialist", "s1.2@ess-specialist"]
    assert not set(ids_a) & set(ids_b)
    assert b.claims[1].supporting_claim_ids == ["s1.1@ess-specialist"]                 # supports carry the qualifier too


def test_control_single_agent_ids_are_unchanged():
    for task_agents in (None, ["ess-specialist"], ["ess-specialist", "ess-specialist"]):
        assert [c.claim_id for c in _parse("ess-specialist", task_agents).claims] == ["s1.1", "s1.2"]


def test_the_collision_is_named_with_plain_ids_and_gone_with_qualified_ones():
    # plain ids: the second agent's report collides with the first's (the channel's INT-REQ-016)
    hub = _hub()
    for agent in AGENTS:
        m, _req, _rq = hub.dispatch("t", agent, WORK[agent][0], [])
        _r, rc = hub.receive("t", m.message_id, _parse(agent))
    assert any(f.code == "INT-REQ-016" for f in rc.findings)
    # qualified ids (the parser told the task's agents): no collision, and the STEM checks name the qualified claims
    hub = _hub()
    for agent in AGENTS:
        m, _req, _rq = hub.dispatch("t", agent, WORK[agent][0], [])
        _r, rc = hub.receive("t", m.message_id, _parse(agent, AGENTS))
        assert not any(f.code == "INT-REQ-016" for f in rc.findings)
        checks = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-")]
        assert checks and all(cid.endswith("@" + agent) for c in checks for cid in c.claim_ids)
        assert all(c.satisfied is True for c in checks)
