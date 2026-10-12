"""Several specialists talking to the primary router through the hub, each routed to its branch."""
from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"hub-test-key-0123456789abcdefghij"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def plan(task_id, subject, agents):
    return WorkPlan(plan_id=f"plan-{task_id}", request_id="req-hub", task_id=task_id, subject=subject, task_type="short_answer", selected_agent_ids=agents)


def test_three_subjects_through_one_hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan("t-hist", "History", ["history-specialist"]))
    hub.open_task(plan("t-econ", "Economics", ["economics-specialist"]))
    hub.open_task(plan("t-bm", "Business Management", ["business-specialist"]))

    m1, _, r1 = hub.dispatch("t-hist", "history-specialist", "To what extent was the Depression responsible for the Nazi rise? Explain with dated evidence.")
    m2, _, r2 = hub.dispatch("t-econ", "economics-specialist", "Calculate the price elasticity of demand and comment.")
    m3, _, r3 = hub.dispatch("t-bm", "business-specialist", "Calculate the profit margin and recommend whether to proceed.")
    assert all(r.status is TransmissionStatus.ACCEPTED for r in (r1, r2, r3))

    hist_text = ("The Depression created the Nazi electorate. Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932, and the Nazi vote rose with it. "
                 "The counter-case is that the unemployed often voted Communist. By the criterion of what made the breakthrough possible, the Depression was decisive. The vote fell in November 1932, after the party had become the largest in July 1932.")
    _, rh = hub.receive("t-hist", m1.message_id, hist_text, agent_id="history-specialist", report_id="rep-h")
    assert rh.branch == "history" and rh.status is not TransmissionStatus.REJECTED
    assert any(fc.constraint_id.startswith("core-chronology") and fc.satisfied for fc in rh.formal_checks)
    assert not any(f.code == "INT-REQ-008" for f in rh.findings)  # a judgement is present

    econ_text = "Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 2. Demand is therefore elastic."
    _, re_ = hub.receive("t-econ", m2.message_id, econ_text, agent_id="economics-specialist", report_id="rep-e")
    assert re_.branch == "economics" and re_.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    failed = [fc for fc in re_.formal_checks if fc.satisfied is False]
    assert failed and failed[0].formal_status == "COUNTEREXAMPLE"
    assert any(f.code == "INT-SUBJ-001" and f.formal_result_id == failed[0].formal_result_id for f in re_.errors)

    bm_text = "With a profit of 50,000 on revenue of 250,000 the profit margin is 20 per cent. Revenue rose from 200,000 to 250,000, an increase of 25 per cent. The firm should therefore proceed."
    _, rb = hub.receive("t-bm", m3.message_id, bm_text, agent_id="business-specialist", report_id="rep-b")
    assert rb.branch == "business_management"
    assert all(fc.satisfied for fc in rb.formal_checks) and len(rb.formal_checks) >= 2  # margin + percentage change both hold
    assert not rb.errors

    # Recorded behaviour change (docs/STEM_DESIGN.md, sections 10.2 and 18, item 1): Chemistry routes to the STEM
    # 'sciences' branch instead of 'generic'; an unrecognised subject still falls back to 'generic'.
    assert hub.branch_for("Psychology") == "psychology" and hub.branch_for("Chemistry") == "sciences" and hub.branch_for("Underwater Basket Weaving") == "generic"
    assert len(hub.receipts("t-hist")) == 2


def test_wrong_branch_agent_is_rejected_by_the_hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan("t-1", "Economics", ["economics-specialist"]))
    m, _, _ = hub.dispatch("t-1", "economics-specialist", "Explain the effect of a price ceiling.")
    reply, receipt = hub.receive("t-1", m.message_id, "A price ceiling below equilibrium causes a shortage.", agent_id="history-specialist", report_id="rep-x")
    assert reply is None and receipt.status is TransmissionStatus.REJECTED
