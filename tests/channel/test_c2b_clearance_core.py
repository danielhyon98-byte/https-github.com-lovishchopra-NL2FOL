"""Channel behaviour fixed by the core fixer's second pass of the round-9 clearance:

* major (independent push check of c4f276c): a revision that weakened a claim the revision request NAMED (its exact figure
  made approximate, turned into a range, hedged, or its calculation's relation dropped) carried no INT-REV-002 at all,
  because the preservation reader skipped the named claims, so nothing named the flagged figure made approximate and the
  outcome could not read the flaw as evaded from the receipt. The weakening of a named claim is now INT-REV-002 (warning),
  worded so the overseer's outcome reads it as weakening; correcting the named claim is not.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import feedback as fb
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport

from .revision_support import CFG, KEY, block_for, issue

QUESTION = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
BAD = "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻²."


@dataclass
class _Case:
    """The shape ``revision_support.block_for`` and ``issue`` read (a Physics answer whose s1.2 states a wrong result)."""
    hub: Any
    ch: Any
    m: Any
    req: Any
    a: Any
    rc: Any
    rep: SpecialistReport


def _physics() -> _Case:
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="plan-ph", request_id="req-ph", task_id="task-ph", subject="Physics", task_type="short_answer",
                                selected_agent_ids=["physics-specialist"]))
    m, req, _rq = hub.dispatch("task-ph", "physics-specialist", QUESTION, [])
    a, rc = hub.receive("task-ph", m.message_id, BAD, agent_id="physics-specialist", report_id="rep-ph-1")
    assert any(f.code == "INT-SUBJ-001" and "s1.2" in f.claim_ids for f in rc.findings), [f.code for f in rc.findings]
    return _Case(hub, ch, m, req, a, rc, SpecialistReport.model_validate(a.payload))


def _revise(revised: str):
    case = _physics()
    block = block_for(case, to_agent_id="physics-specialist")
    assert any(c.claim_id == "s1.2" for f in block.flaws for c in f.claims)
    m2, _r, rq = issue(case, block, to="physics-specialist")
    assert rq.status.value == "ACCEPTED", [f.message for f in rq.findings]
    a2, rc2 = case.hub.receive("task-ph", m2.message_id, revised, agent_id="physics-specialist", report_id="rep-ph-2")
    case.hub.close()
    return rc2


def _weakened(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-REV-002" and "weakened instead of corrected" in f.message]


def test_a_named_calculation_turned_into_an_estimate_is_named_as_weakened_not_corrected():
    rc = _revise("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a is about 6 m s⁻². The acceleration is therefore 6.0 m s⁻².")
    found = _weakened(rc)
    # the estimate makes the figure approximate and drops the calculation's relation: each way is named once, on s1.2, in the
    # overseer's weakening wording
    assert all(f.severity == "warning" and "s1.2" in f.claim_ids for f in found)
    assert sum("is made approximate" in f.message for f in found) == 1 and sum("is no longer stated" in f.message for f in found) == 1


def test_a_named_calculation_hedged_is_named():
    rc = _revise("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a may be (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻².")
    assert [f for f in _weakened(rc) if "s1.2" in f.claim_ids and "certainty of claims" in f.message]


def test_control_the_named_calculation_corrected_is_no_weakening():
    rc = _revise("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻².")
    assert not _weakened(rc) and not [f for f in rc.findings if f.code == "INT-REV-002"], [(f.code, f.message[:120]) for f in rc.findings]


def test_the_weakening_wording_is_the_one_the_outcome_reads():
    assert all(any(w in text for w in ("is made approximate", "is turned into a range", "certainty of claims", "is no longer stated"))
               for text in fb._EVASION_WORDING.values())
    assert set(fb._EVASION_WORDING) == {"made approximate", "turned into a range", "hedged", "its relation dropped"}
