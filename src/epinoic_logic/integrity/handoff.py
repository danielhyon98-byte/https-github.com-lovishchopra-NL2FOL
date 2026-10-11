"""Router -> specialist handoff checks and verification-result staleness checks."""
from __future__ import annotations

from typing import Optional

from ..engine.provenance import verify_signature
from ..engine.results import VerificationResult
from ..ir.canonical import problem_digest
from ..ir.schema import Problem
from ..translate.contracts import SpecialistReport
from .contracts import IntegrityFinding, WorkPlan


def check_report_against_plan(plan: WorkPlan, report: SpecialistReport) -> list[IntegrityFinding]:
    f: list[IntegrityFinding] = []
    if report.request_id != plan.request_id or report.task_id != plan.task_id:
        f.append(IntegrityFinding(code="INT-HANDOFF-001", severity="error", message=f"report {report.report_id} answers request/task ({report.request_id}/{report.task_id}) but the plan is ({plan.request_id}/{plan.task_id})"))
    if report.agent_id not in plan.selected_agent_ids:
        f.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"agent {report.agent_id} was not selected by the router for this task"))
    if report.subject.strip().lower() != plan.subject.strip().lower():
        f.append(IntegrityFinding(code="INT-HANDOFF-003", severity="error", message=f"report subject {report.subject!r} differs from planned subject {plan.subject!r}"))
    if report.task_type != plan.task_type:
        f.append(IntegrityFinding(code="INT-HANDOFF-003", severity="warning", message=f"report task_type {report.task_type!r} differs from planned {plan.task_type!r}"))
    if plan.allowed_document_ids:
        allowed = set(plan.allowed_document_ids)
        outside = sorted({ref.document_id for c in report.claims for ref in c.source_refs if ref.document_id not in allowed} | {t.document_id for t in report.supplied_texts if t.document_id not in allowed})
        if outside:
            f.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"report cites documents outside the retrieval scope: {outside}", claim_ids=[c.claim_id for c in report.claims if any(r.document_id in outside for r in c.source_refs)]))
    if plan.deadline_at and report.created_at > plan.deadline_at:
        f.append(IntegrityFinding(code="INT-HANDOFF-005", severity="warning", message="report created after the plan deadline"))
    for c in report.claims:
        if c.advisory_verification_status is not None:
            f.append(IntegrityFinding(code="INT-HANDOFF-006", severity="info", message="agent self-reported a verification status; ignored", claim_ids=[c.claim_id]))
    return f


def check_result_binding(result: VerificationResult, current_problem: Problem, signing_key: Optional[bytes] = None) -> list[IntegrityFinding]:
    """A result is only valid for the exact representation it was produced for."""
    f: list[IntegrityFinding] = []
    if result.binding.problem_digest != problem_digest(current_problem):
        f.append(IntegrityFinding(code="INT-STALE-001", severity="error", message="verification result was produced for a different representation of this claim; it must not be reused", claim_ids=[current_problem.claim_id], formal_result_id=result.result_id))
    if result.claim_id != current_problem.claim_id or result.request_id != current_problem.request_id:
        f.append(IntegrityFinding(code="INT-STALE-003", severity="error", message="verification result ids do not match the claim being decided", claim_ids=[current_problem.claim_id], formal_result_id=result.result_id))
    if signing_key is not None and not verify_signature(result, signing_key):
        f.append(IntegrityFinding(code="INT-STALE-002", severity="error", message="verification result is unsigned or its signature is invalid; the Overseer must not trust it", claim_ids=[current_problem.claim_id], formal_result_id=result.result_id))
    return f
