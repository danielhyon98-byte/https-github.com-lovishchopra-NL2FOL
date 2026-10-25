"""Two faults of the overseer's translation checks found by the delivery policy's formal path (``docs/DELIVERY.md``), with
clean controls. Before the fixes no reviewed answer could ever be delivered FORMALLY CHECKED through an audited hub:

1. ``summary_matches`` listed the review-currency alternatives with ``dict.fromkeys((report, None))``. A
   ``SpecialistReport`` is a frozen model whose claims are a list, so hashing it raised ``TypeError`` and the whole
   translation check of every outcome carrying a fidelity review failed internally (OVS-AUDIT-001, error): every reviewed
   transfer's clearance was AUDIT_FAILED.
2. ``grounding_faults`` re-ran the grounding check without the task record, so a premise the task record validated
   (``numeric_in_task``, ``relation_in_source``) could not be reproduced and every genuine task-validated premise was
   named overstated (OVS-TRN-003, error). The re-run now gets the task record of the journaled request, only when its
   digest is the one the translation records (rule ``task-record-rerun``); a verification the task does not support is
   still named.
"""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.overseer.checks.translation import grounding_faults, summary_matches
from epinoic_logic.translate.contracts import TaskRecord
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from .conftest import CFG, KEY, make_auditor, make_keyring
from .delivery_support import PHYSICS, QUESTION, Verifier, physics_report, speed_translation

AGENT = "physics-specialist"
TASK = TaskRecord.of(PHYSICS["task_id"], PHYSICS["request_id"], QUESTION)


def outcome(*, distance: int = 120, speed: int = 15, review: bool = True, task: TaskRecord = TASK):
    report = physics_report(AGENT, "rep-a", (("p1.1", f"The speed is {speed} km/h."),))
    claim = report.claims[1]
    translator = Translator(FixtureTranslationProvider({"p1.1": speed_translation("p1.1", distance=distance, speed=speed)}), config=CFG)
    reviewer = SemanticReviewer(FixtureReviewProvider({"p1.1": {"verdict": "faithful", "issues": []}})) if review else None
    o = verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="hub", task=task)
    return o, claim, report


# ============================================================================================ 1. summary_matches
def test_a_reviewed_outcomes_summary_is_matched_with_the_report_and_the_task():
    o, claim, report = outcome()
    assert o.semantic_review is not None and o.release.permitted
    keyring = make_keyring()
    assert summary_matches(o, claim, o.verification, keyring, report=report, task=TASK)  # raised TypeError before the fix
    assert summary_matches(o, claim, o.verification, keyring, report=report, task=None) is False  # the review is bound to the task
    # control: a summary the composer did not write is still refused, with every alternative tried
    forged = o.model_copy(update={"summary": o.summary.replace("ENTAILED", "CONSISTENT", 1) + " (edited)"})
    assert not summary_matches(forged, claim, o.verification, keyring, report=report, task=TASK)


def test_a_reviewed_transfer_is_audited_without_an_internal_failure():
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = WorkPlan(plan_id="plan-fix", selected_agent_ids=[AGENT], **PHYSICS)
        ch = hub.open_task(plan)
        ch.verify_claim_fn = Verifier()
        m = hub.dispatch(plan.task_id, AGENT, QUESTION)[0]
        _msg, rc = hub.receive(plan.task_id, m.message_id, physics_report(AGENT, "rep-a"))
        [o] = [o for o in rc.outcomes if o.claim_id == "p1.1"]
        assert o.semantic_review is not None and o.release.permitted
        audit = hub.audit(plan.task_id)
        codes = {f.code for f in audit.report.findings}
        assert "OVS-AUDIT-001" not in codes and "OVS-TRN-003" not in codes, sorted(codes)
        assert audit.state == "AUDIT_PASSED" and audit.transfer_states[rc.message_id] == "AUDIT_PASSED"
        assert hub.clearance(plan.task_id, rc.message_id, receipt=rc).state == "AUDIT_PASSED"
    finally:
        hub.close()


# ============================================================================================ 2. grounding_faults
def test_a_task_validated_premise_is_reproduced_with_the_task_record():
    o, claim, report = outcome()
    tr = o.translation
    methods = {c.target_id: (c.method, c.verified) for c in tr.grounding_checks}
    assert methods["D"] == ("numeric_in_task", True) and methods["SPEED"] == ("relation_in_source", True) and tr.task_sha256 == TASK.text_sha256
    overstated, absent = grounding_faults(tr, report, task=TASK)
    assert overstated == [] and absent == []
    # without the task record the re-run cannot reproduce the task's validations: the old false OVS-TRN-003
    assert grounding_faults(tr, report)[0]
    # a task record of another text is never borrowed: the re-run goes without it
    other = TaskRecord.of(PHYSICS["task_id"], PHYSICS["request_id"], "A car travels 120 km in 8 hours. Find its average speed in km/h.")
    assert grounding_faults(tr, report, task=other)[0]


def test_a_verification_the_task_does_not_support_is_still_named():
    """Control: the task says 120 km; a translation using 160 km fails its grounding check, and a translation that
    records that failed check as verified is named overstated even with the task record."""
    o, claim, report = outcome(distance=160, speed=20)
    tr = o.translation
    failed = [c for c in tr.grounding_checks if c.target_id == "D"]
    assert failed and failed[0].verified is False
    flipped = tr.model_copy(update={"grounding_checks": [c.model_copy(update={"verified": True}) if c.target_id == "D" else c for c in tr.grounding_checks]})
    overstated, _absent = grounding_faults(flipped, report, task=TASK)
    assert any("D" in x and "re-run does not verify it" in x for x in overstated), overstated
