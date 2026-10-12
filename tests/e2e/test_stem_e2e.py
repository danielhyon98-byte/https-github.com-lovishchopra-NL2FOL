"""STEM end to end through ``RouterHub`` (docs/STEM_DESIGN.md, sections 1 and 16): Physics, Chemistry and Mathematics
answers in LaTeX, Unicode and ASCII; the observed case as an INT-SUBJ-001 error naming the step; a multi-agent Physics
and Mathematics task with a combinator; every engine result signed and bound to the receipt; the scope tail kept."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.channel import bus as bus_module
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.statuses import SCOPE_STATEMENT
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.canonical import sha256_hex

KEY = b"stem-e2e-test-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
SCOPE_TAIL = "Formal results concern only the encoded checks under their premises; coverage is heuristic."


@pytest.fixture
def signed_results(monkeypatch):
    """Every engine result the channel produces, to check its signature and its binding to the receipt."""
    seen = []
    real = bus_module.verify

    def capture(*a, **k):
        res = real(*a, **k)
        seen.append(res)
        return res

    monkeypatch.setattr(bus_module, "verify", capture)
    return seen


def run(subject: str, agent: str, request: str, answer: str):
    hub = RouterHub(signing_key=KEY, key_id="stem-e2e", config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request)
    reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return hub, reply, rc


# (subject, agent, request, answer, None when correct else a fragment of the claim the INT-SUBJ-001 error must name)
NOTATIONS = [
    # Physics
    ("Physics", "physics-specialist", "A stone falls from rest for 3.0 s. Calculate its speed.",
     "$v = u + at = 0 + 9.8 \\times 3.0 = 29.4\\ \\text{m s}^{-1}$", None),
    ("Physics", "physics-specialist", "A stone falls from rest for 3.0 s. Calculate its speed.",
     "$v = u + at = 0 + 9.8 \\times 3.0 = 32.4\\ \\text{m s}^{-1}$", "= 32.4"),
    ("Physics", "physics-specialist", "Calculate the kinetic energy of a 2.0 kg mass moving at 3.0 m/s.", "Eₖ = ½mv² = ½ × 2.0 × 3.0² = 9.0 J.", None),
    ("Physics", "physics-specialist", "Calculate the kinetic energy of a 2.0 kg mass moving at 3.0 m/s.", "Eₖ = ½mv² = ½ × 2.0 × 3.0² = 18 J.", "= 18 J"),
    ("Physics", "physics-specialist", "Calculate the momentum of a 1200 kg car moving at 25 m/s.", "p = m*v = 1200 * 25 = 30000 kg m/s", None),
    ("Physics", "physics-specialist", "Calculate the momentum of a 1200 kg car moving at 25 m/s.", "p = m*v = 1200 * 25 = 35000 kg m/s", "= 35000"),
    # Chemistry
    ("Chemistry", "chemistry-specialist", "Calculate the amount of water in 36 g.", "$n = \\frac{m}{M} = \\frac{36}{18.0} = 2.0\\ \\text{mol}$", None),
    ("Chemistry", "chemistry-specialist", "Calculate the amount of water in 36 g.", "$n = \\frac{m}{M} = \\frac{36}{18.0} = 3.0\\ \\text{mol}$", "= 3.0"),
    ("Chemistry", "chemistry-specialist", "Balance the combustion of hydrogen.", "2H₂ + O₂ → 2H₂O", None),
    ("Chemistry", "chemistry-specialist", "Balance the combustion of hydrogen.", "2H₂ + O₂ → H₂O", "→ H₂O"),
    ("Chemistry", "chemistry-specialist", "Calculate the concentration.", "c = n/V = 0.50 mol / 0.250 dm^3 = 2.0 mol dm^-3", None),
    ("Chemistry", "chemistry-specialist", "Calculate the concentration.", "c = n/V = 0.50 mol / 0.250 dm^3 = 0.5 mol dm^-3", "= 0.5 mol"),
    # Mathematics
    ("Mathematics: Analysis and Approaches", "maths-specialist", "Solve 3x + 5 = 20.", "$3x + 5 = 20 \\Rightarrow 3x = 15 \\Rightarrow x = 5$", None),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "Solve 3x + 5 = 20.", "$3x + 5 = 20 \\Rightarrow 3x = 15 \\Rightarrow x = 6$", "x = 6"),
    ("Mathematics: Analysis and Approaches", "maths-specialist", "Simplify the surd.", "√8 = 2√2", None),
    ("Mathematics: Applications and Interpretation", "maths-specialist", "Find the sum of the first 10 terms of 3, 7, 11, ...",
     "S_10 = 10/2 * (2*3 + 9*4) = 210", None),
    ("Mathematics: Applications and Interpretation", "maths-specialist", "Find the sum of the first 10 terms of 3, 7, 11, ...",
     "S_10 = 10/2 * (2*3 + 9*4) = 220", "= 220"),
]


@pytest.mark.parametrize("subject,agent,request_text,answer,wrong", NOTATIONS, ids=[f"{n[0][:9]}-{i}" for i, n in enumerate(NOTATIONS)])
def test_stem_answers_in_every_notation(subject, agent, request_text, answer, wrong, signed_results):
    hub, reply, rc = run(subject, agent, request_text, answer)
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert rc.branch == ("mathematics" if subject.startswith("Mathematics") else "sciences")
    rep = hub.channels["t"].transmitted_reports["r1"]
    assert rep.original_response == answer
    stem_checks = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-")]
    assert stem_checks, [s.code for s in rc.structural_findings]
    if wrong is None:
        assert rc.errors == [] and all(c.satisfied is True for c in stem_checks), [(c.constraint_id, c.formal_status) for c in stem_checks]
    else:
        errs = [f for f in rc.errors if f.code == "INT-SUBJ-001"]
        assert errs and any(wrong in next(c.claim_text for c in rep.claims if c.claim_id == cid) for f in errs for cid in f.claim_ids)
        assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS  # a content finding: delivered, never rejected
    # every engine result is signed with the hub's key and bound to this receipt
    ids = set(rc.formal_result_ids)
    mine = [r for r in signed_results if r.result_id in ids]
    assert mine and all(verify_signature(r, KEY) and r.signature_key_id == "stem-e2e" for r in mine)
    assert all(r.scope_statement == SCOPE_STATEMENT for r in mine)
    assert {c.formal_result_id for c in stem_checks} <= ids
    assert rc.summary.endswith(SCOPE_TAIL)


def test_the_observed_case_is_an_error_naming_the_step():
    _, reply, rc = run("Physics", "physics-specialist", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.",
                       "a = (20 - 0)/4.0 = 6.0 m s⁻²")
    assert reply is not None and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    err = [f for f in rc.errors if f.code == "INT-SUBJ-001"]
    assert len(err) == 1 and err[0].claim_ids == ["s1.1"] and "'(20 - 0)/4.0 = 6.0 m s⁻²'" in err[0].message


def test_nonlinear_checks_record_their_policy_on_the_signed_result(signed_results):
    _, _, rc = run("Mathematics: Analysis and Approaches", "maths-specialist", "Solve x^2 - 5x + 6 = 0.",
                   "$x^2 - 5x + 6 = 0 \\Rightarrow (x-2)(x-3) = 0$, so $x = 2$ or $x = 3$.")
    assert rc.errors == []
    nonlinear = [r for r in signed_results if r.result_id in set(rc.formal_result_ids) and r.limits is not None]
    assert nonlinear and all(r.limits.allow_nonlinear and verify_signature(r, KEY) for r in nonlinear)


def test_multi_agent_physics_and_maths_with_a_combinator(signed_results):
    plan = WorkPlan(plan_id="p-multi", request_id="q-multi", task_id="t-multi", subject="Physics", task_type="short_answer",
                    selected_agent_ids=["physics-specialist", "maths-specialist", "combinator"],
                    agent_subjects={"maths-specialist": "Mathematics: Analysis and Approaches"})
    hub = RouterHub(signing_key=KEY, key_id="stem-e2e", config=CFG)
    hub.open_task(plan)
    mp, _, _ = hub.dispatch("t-multi", "physics-specialist", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.")
    mm, reqm, _ = hub.dispatch("t-multi", "maths-specialist", "Solve 4a = 20 for a.")
    assert reqm.subject == "Mathematics: Analysis and Approaches"
    rp_msg, rp = hub.receive("t-multi", mp.message_id, "Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻².",
                             agent_id="physics-specialist", report_id="rep-phys")
    rm_msg, rm = hub.receive("t-multi", mm.message_id, "$4a = 20 \\Rightarrow a = 5$", agent_id="maths-specialist", report_id="rep-maths")
    assert rp.branch == "sciences" and rm.branch == "mathematics"
    assert rp.errors == [] and rm.errors == [] and rp_msg is not None and rm_msg is not None
    ch = hub.channels["t-multi"]
    phys, maths = ch.transmitted_reports["rep-phys"], ch.transmitted_reports["rep-maths"]
    # each STEM branch numbers its claims with its own letter, so the combinator's ledger can account for both reports
    assert [c.claim_id for c in phys.claims] == ["s1.1", "s1.2"] and [c.claim_id for c in maths.claims] == ["m1.1"]
    claims = [SynthesizedClaim(claim_id="syn-1", text="The acceleration is therefore 5.0 m s⁻².", source_claim_ids=["s1.2"], transformation="carried"),
              SynthesizedClaim(claim_id="syn-2", text="Solving 4a = 20 also gives a = 5.", source_claim_ids=["m1.1"], transformation="paraphrased")]
    text = " ".join(c.text for c in claims)
    syn = Synthesis(synthesis_id="syn-multi", request_id="q-multi", task_id="t-multi", combinator_agent_id="combinator",
                    source_report_ids=["rep-phys", "rep-maths"], claims=claims, text=text, text_sha256=sha256_hex(text), created_at="2026-10-12T00:00:00Z")
    reply, rs = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert reply is not None and rs.status is not TransmissionStatus.REJECTED
    assert rs.errors == [], [(f.code, f.message[:120]) for f in rs.errors]
    assert all(r.summary.endswith(SCOPE_TAIL) for r in hub.receipts("t-multi") if r.direction != "router_to_specialist")
    for rc in (rp, rm):
        ids = set(rc.formal_result_ids)
        results = [r for r in signed_results if r.result_id in ids]
        assert results and all(verify_signature(r, KEY) for r in results)
    # a synthesis that changes the computed figure is caught by the ledger
    bad_claims = [SynthesizedClaim(claim_id="syn-3", text="The acceleration is therefore 6.0 m s⁻².", source_claim_ids=["s1.2"], transformation="paraphrased")]
    bad = Synthesis(synthesis_id="syn-bad", request_id="q-multi", task_id="t-multi", combinator_agent_id="combinator", source_report_ids=["rep-phys", "rep-maths"],
                    claims=bad_claims, text=bad_claims[0].text, text_sha256=sha256_hex(bad_claims[0].text), created_at="2026-10-12T00:01:00Z")
    _, rb = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, bad)
    assert any(f.code == "INT-LEDGER-023" for f in rb.errors)


def test_a_wrong_maths_step_and_a_correct_physics_answer_on_one_task():
    plan = WorkPlan(plan_id="p-2", request_id="q-2", task_id="t-2", subject="Physics", task_type="short_answer",
                    selected_agent_ids=["physics-specialist", "maths-specialist"], agent_subjects={"maths-specialist": "Mathematics: Analysis and Approaches"})
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(plan)
    mp, _, _ = hub.dispatch("t-2", "physics-specialist", "Calculate the weight of a 2.0 kg mass, taking g = 9.8 m s⁻².")
    mm, _, _ = hub.dispatch("t-2", "maths-specialist", "Solve 2x + 1 = 9.")
    _, rp = hub.receive("t-2", mp.message_id, "W = mg = 2.0 × 9.8 = 19.6 N", agent_id="physics-specialist", report_id="r-p")
    _, rm = hub.receive("t-2", mm.message_id, "$2x + 1 = 9 \\Rightarrow 2x = 8 \\Rightarrow x = 3$", agent_id="maths-specialist", report_id="r-m")
    assert rp.errors == [] and rp.branch == "sciences"
    assert rm.branch == "mathematics" and any(f.code == "INT-SUBJ-001" for f in rm.errors)
    assert rm.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
