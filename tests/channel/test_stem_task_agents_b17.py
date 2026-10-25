"""E2E B17 through the channel: when a second STEM agent of the same branch delivers on a task (Chemistry and ESS), the
channel passes the task's delivering agents to the STEM parser (``task_agent_ids``), so the second report's claim ids
carry the agent's qualifier (``s1.1@ess-specialist``) and never collide with the first's (INT-REQ-016). The set is
delivery-based and per branch: the first delivery, a task whose plan names an agent that delivers nothing, and agents of
two STEM branches (which number with their own letters, s and m) keep plain ids."""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"b17-channel-test-key-0123456789abcdef01"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
WORK = {
    "chemistry-specialist": ("Calculate the mass of 0.250 mol of NaCl (M = 58.5 g mol⁻¹).", "m = nM = 0.250 × 58.5 = 14.6 g.\nSo the mass is 14.6 g."),
    "ess-specialist": ("CO2 rose from 280 to 421 ppm; find the percentage increase.", "The increase is (421 − 280) ÷ 280 × 100 = 50.4%.\nSo it is about 50%."),
}


def _deliver(agents: list[str], delivering: list[str]):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Chemistry", task_type="structured_question", selected_agent_ids=agents,
                           agent_subjects={"ess-specialist": "Environmental Systems and Societies"}))
    out = []
    for agent in delivering:
        m, _req, _rq = hub.dispatch("t", agent, WORK[agent][0], [])
        reply, rc = hub.receive("t", m.message_id, WORK[agent][1], agent_id=agent, report_id="r-" + agent)
        out.append((agent, reply, rc))
    return out


def test_two_stem_agents_on_one_task_never_share_a_claim_id():
    (a1, r1, rc1), (a2, r2, rc2) = _deliver(["chemistry-specialist", "ess-specialist"], ["chemistry-specialist", "ess-specialist"])
    first, second = [c["claim_id"] for c in r1.payload["claims"]], [c["claim_id"] for c in r2.payload["claims"]]
    assert first == ["s1.1", "s1.2"] and second == ["s1.1@ess-specialist", "s1.2@ess-specialist"]
    assert not any(f.code == "INT-REQ-016" for f in rc2.findings)
    checks = [c for c in rc2.formal_checks if c.constraint_id.startswith("stem-")]
    assert checks and all(cid.endswith("@ess-specialist") for c in checks for cid in c.claim_ids) and all(c.satisfied is True for c in checks)


def test_control_a_single_delivering_agent_keeps_plain_ids():
    [(_a, reply, rc)] = _deliver(["ess-specialist", "combinator"], ["ess-specialist"])
    assert [c["claim_id"] for c in reply.payload["claims"]] == ["s1.1", "s1.2"] and not any(f.code == "INT-REQ-016" for f in rc.findings)


def test_control_agents_of_two_stem_branches_keep_their_own_letters():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer",
                           selected_agent_ids=["physics-specialist", "maths-specialist"], agent_subjects={"maths-specialist": "Mathematics: Analysis and Approaches"}))
    mp, _r, _q = hub.dispatch("t", "physics-specialist", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.")
    mm, _r, _q = hub.dispatch("t", "maths-specialist", "Solve 4a = 20 for a.")
    rp, _rcp = hub.receive("t", mp.message_id, "Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻².",
                           agent_id="physics-specialist", report_id="rep-phys")
    rm, rcm = hub.receive("t", mm.message_id, "$4a = 20 \\Rightarrow a = 5$", agent_id="maths-specialist", report_id="rep-maths")
    assert [c["claim_id"] for c in rp.payload["claims"]] == ["s1.1", "s1.2"] and [c["claim_id"] for c in rm.payload["claims"]] == ["m1.1"]
    assert not any(f.code == "INT-REQ-016" for f in rcm.findings)
