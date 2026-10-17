"""The task record through the channel (external review of 2026-10-12, findings 2 and 4, channel side).

A premise whose kind claims the task's authority (``arithmetic_fact``, ``task_setting``, ``rubric_rule``) is validated only
against application-created records: the supplied texts and the task as the router issued it. A fidelity reviewer must be
shown that original task. The channel holds the request each report answers, so it hands its task record to an injected
verifier that declares a ``task`` parameter; a verifier with the two-argument signature is called exactly as before.
"""
from __future__ import annotations

import json

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, TaskRecord, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.providers.rendering import render_review_user_prompt
from epinoic_logic.translate.review import SemanticReviewer

KEY = b"task-record-channel-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
QUESTION = "A car travels 120 km in 8 hours. Find its average speed in km/h."
#: The same task stating the relation as a given (only a record that states a relation verifies it).
QUESTION_STATED = "A car travels 120 km in 8 hours. Use speed = d / 8. Find its average speed in km/h."
IDS = dict(request_id="req-t", task_id="task-t", subject="Physics", task_type="calculation")


def _plan() -> WorkPlan:
    return WorkPlan(plan_id="plan-t", selected_agent_ids=["physics-specialist"], **IDS)


def _report(claim_text: str) -> SpecialistReport:
    claim = ClaimRecord(**IDS, report_id="rep-t", agent_id="physics-specialist", claim_id="p1.1", claim_text=claim_text, claim_role="quantitative",
                        proposed_claim_kind="arithmetic")
    return SpecialistReport(**IDS, report_id="rep-t", agent_id="physics-specialist", original_response=claim_text, response_sha256=sha256_text(claim_text),
                            claims=[claim], created_at="2026-10-12T00:00:00Z")


def _translation(distance: int, speed: int) -> str:
    """A fixture translation: distance and speed = distance / 8 labelled arithmetic_fact with no source reference."""
    v = lambda n: {"op": "var", "name": n}  # noqa: E731
    r = lambda x: {"op": "real", "value": str(x)}  # noqa: E731
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": IDS["request_id"], "claim_id": "p1.1", "query": "entailment",
               "symbols": [{"name": "d", "sort": "Real"}, {"name": "speed", "sort": "Real"}],
               "premises": [{"id": "D", "expr": {"op": "eq", "left": v("d"), "right": r(distance)}, "label": f"distance {distance} km", "grounding": {"kind": "arithmetic_fact"}},
                            {"id": "SPEED", "expr": {"op": "eq", "left": v("speed"), "right": {"op": "div", "left": v("d"), "right": r(8)}}, "grounding": {"kind": "arithmetic_fact"}}],
               "conclusion": {"id": "C", "expr": {"op": "eq", "left": v("speed"), "right": r(speed)}, "label": f"the speed is {speed} km/h"}}
    return json.dumps({"problem": problem, "interpretation": {"reading": "speed is distance over time", "glossary": [], "ambiguity_flags": []},
                       "ambiguous": False, "unsupported_reason": None})


def _cross(verify_fn, claim_text: str, question: str = QUESTION):
    ch = TranslatorChannel(_plan(), signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    msg, _req, _rq = ch.request("router", "physics-specialist", question)
    _reply, receipt = ch.respond(msg.message_id, _report(claim_text))
    assert receipt.status is not TransmissionStatus.REJECTED
    [outcome] = receipt.outcomes
    return outcome


def test_a_two_argument_verifier_is_called_as_before_and_task_authority_stays_unvalidated():
    calls: list[tuple] = []
    translator = Translator(FixtureTranslationProvider({"p1.1": _translation(120, 15)}), config=CFG)

    def verify_fn(claim, report):
        calls.append((claim.claim_id, report.report_id))
        return verify_claim(claim, report, translator, config=CFG, signing_key=KEY)

    outcome = _cross(verify_fn, "The speed is 15 km/h.")
    assert calls == [("p1.1", "rep-t")]
    assert outcome.display_status is S.ENTAILED                       # the formal result of the encoding ...
    assert outcome.verification.unverified_dependencies == ["D", "SPEED"]  # ... resting on task authority nothing validated
    assert outcome.translation.task_sha256 is None and not outcome.release.permitted


def test_a_verifier_that_declares_task_receives_the_request_as_issued_and_the_reviewer_sees_it():
    seen: list[TaskRecord] = []
    review_provider = FixtureReviewProvider({"p1.1": {"verdict": "faithful", "issues": []}})
    reviewer = SemanticReviewer(review_provider)

    def verify_fn(claim, report, task=None):
        seen.append(task)
        translator = Translator(FixtureTranslationProvider({"p1.1": _translation(120, 15)}), config=CFG)
        return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, task=task)

    outcome = _cross(verify_fn, "The speed is 15 km/h.")
    assert seen == [TaskRecord.of(IDS["task_id"], IDS["request_id"], QUESTION)]
    # Rewritten to a stricter rule (repair 2 of the integration, verifier finding 2): the task's own wording validates the
    # distance, but its 8 is no evidence for the relation speed = d / 8, which the task does not state: that premise is
    # the translation's own, an unverified dependency in the signed result, and release is refused although the review
    # is faithful
    figures = {c.target_id: c.verified for c in outcome.translation.grounding_checks if c.method == "numeric_in_task"}
    relations = {c.target_id: c.verified for c in outcome.translation.grounding_checks if c.method == "relation_in_source"}
    assert figures == {"D": True} and relations == {"SPEED": None}
    assert outcome.verification.ungrounded_dependencies == [] and outcome.verification.unverified_dependencies == ["SPEED"]
    assert outcome.translation.task_sha256 == sha256_text(QUESTION)
    # the reviewer was shown the original task, and its review is bound to it
    [request] = review_provider.calls
    assert request.task is not None and request.task.text == QUESTION and QUESTION in render_review_user_prompt(request)
    assert outcome.semantic_review.binding is not None and outcome.semantic_review.binding.task_sha256 == sha256_text(QUESTION)
    assert outcome.semantic_review.verdict == "faithful" and not outcome.release.permitted
    assert any("SPEED" in u for u in outcome.release.unresolved), outcome.release.unresolved


def test_a_task_that_states_the_relation_establishes_every_premise_and_release_follows_the_review():
    """The pair of the test above: the task states the relation as a given ("Use speed = d / 8"), so the task's own wording
    validates the distance and the relation; every premise is established in the signed result, and the faithful review
    the reviewer made with the original task in view permits release."""
    seen: list[TaskRecord] = []
    review_provider = FixtureReviewProvider({"p1.1": {"verdict": "faithful", "issues": []}})
    reviewer = SemanticReviewer(review_provider)

    def verify_fn(claim, report, task=None):
        seen.append(task)
        translator = Translator(FixtureTranslationProvider({"p1.1": _translation(120, 15)}), config=CFG)
        return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, task=task)

    outcome = _cross(verify_fn, "The speed is 15 km/h.", QUESTION_STATED)
    assert seen == [TaskRecord.of(IDS["task_id"], IDS["request_id"], QUESTION_STATED)]
    figures = {c.target_id: c.verified for c in outcome.translation.grounding_checks if c.method == "numeric_in_task"}
    relations = {c.target_id: c.verified for c in outcome.translation.grounding_checks if c.method == "relation_in_source"}
    assert figures == {"D": True} and relations == {"SPEED": True}
    assert outcome.verification.ungrounded_dependencies == [] and outcome.verification.unverified_dependencies == []
    [request] = review_provider.calls
    assert request.task is not None and request.task.text == QUESTION_STATED and QUESTION_STATED in render_review_user_prompt(request)
    assert outcome.release.permitted, outcome.release.unresolved


def test_with_the_task_record_a_substituted_figure_is_an_evidence_failure_through_the_channel():
    """The review's 120-to-160 substitution, through the channel: the task says 120 km, so the invented 160 is refuted
    (an ungrounded dependency and a failed check); the formal ENTAILED is reported as such and release is refused."""
    def verify_fn(claim, report, task=None):
        translator = Translator(FixtureTranslationProvider({"p1.1": _translation(160, 20)}), config=CFG)
        return verify_claim(claim, report, translator, config=CFG, signing_key=KEY, task=task)

    outcome = _cross(verify_fn, "The speed is 20 km/h.")
    assert outcome.display_status is S.ENTAILED
    # (repair 2 of the integration: the relation speed = d / 8 no record states is listed as well, never hidden)
    assert outcome.verification.ungrounded_dependencies == ["D"] and outcome.verification.unverified_dependencies == ["SPEED"]
    failed = [c for c in outcome.translation.grounding_checks if c.target_id == "D" and c.verified is False]
    assert failed and "160" in failed[0].detail and "120 km" in failed[0].detail
    assert not outcome.release.permitted and "Failed grounding checks: D" in outcome.summary
