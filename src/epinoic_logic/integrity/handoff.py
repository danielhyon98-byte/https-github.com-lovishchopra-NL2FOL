"""Router -> specialist handoff checks and verification-result staleness checks.

Every finding carries the report id, agent id and claim ids it is about, so a
report-level fault is as actionable for the Overseer as a claim-level one.
"""
from __future__ import annotations

from typing import Optional

from ..engine.provenance import compute_versions, config_digest, verify_signature, versions_digest
from ..engine.results import SolverConfig, VerificationResult, Versions
from ..ir.canonical import problem_digest, sha256_hex
from ..ir.schema import Problem
from ..translate.contracts import SpecialistReport
from .contracts import IntegrityFinding, WorkPlan, parse_rfc3339


def _ids(report: SpecialistReport) -> dict:
    return dict(report_ids=[report.report_id], agent_ids=[report.agent_id], claim_ids=[c.claim_id for c in report.claims])


def check_report_against_plan(plan: WorkPlan, report: SpecialistReport) -> list[IntegrityFinding]:
    f: list[IntegrityFinding] = []
    ids = _ids(report)
    if report.request_id != plan.request_id or report.task_id != plan.task_id:
        f.append(IntegrityFinding(code="INT-HANDOFF-001", severity="error", message=f"report {report.report_id} answers request/task ({report.request_id}/{report.task_id}) but the plan is ({plan.request_id}/{plan.task_id})", **ids))
    if report.agent_id not in plan.selected_agent_ids:
        f.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"agent {report.agent_id} was not selected by the router for this task (selected: {plan.selected_agent_ids})", **ids))
    planned_subject = plan.agent_subjects.get(report.agent_id, plan.subject)
    if report.subject.strip().lower() != planned_subject.strip().lower():
        f.append(IntegrityFinding(code="INT-HANDOFF-003", severity="error", message=f"report subject {report.subject!r} differs from planned subject {planned_subject!r} for agent {report.agent_id}", **ids))
    if report.task_type != plan.task_type:
        f.append(IntegrityFinding(code="INT-HANDOFF-010", severity="warning", message=f"report task_type {report.task_type!r} differs from planned {plan.task_type!r}", **ids))
    if plan.course_level not in (None, "unknown") and report.course_level not in (None, "unknown") and report.course_level != plan.course_level:
        f.append(IntegrityFinding(code="INT-HANDOFF-011", severity="error", message=f"report course_level {report.course_level!r} differs from planned {plan.course_level!r}", **ids))
    if plan.allowed_document_ids:
        allowed = set(plan.allowed_document_ids)
        claim_docs = {ref.document_id for c in report.claims for ref in c.source_refs}
        text_docs = {t.document_id for t in report.supplied_texts}
        outside = sorted({d for d in claim_docs | text_docs if d not in allowed})
        if outside:
            offending = [c.claim_id for c in report.claims if any(r.document_id in outside for r in c.source_refs)]
            where = "claims" if offending else "supplied_texts"
            f.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"report cites documents outside the retrieval scope in its {where}: {outside}", claim_ids=offending or ids["claim_ids"], report_ids=ids["report_ids"], agent_ids=ids["agent_ids"], document_ids=outside))
    if plan.deadline_at:
        deadline = parse_rfc3339(plan.deadline_at)
        created = parse_rfc3339(report.created_at)
        if deadline is None:
            f.append(IntegrityFinding(code="INT-HANDOFF-008", severity="error", message=f"plan deadline_at {plan.deadline_at!r} is not an RFC 3339 timestamp; the deadline cannot be enforced", **ids))
        if created is None:
            f.append(IntegrityFinding(code="INT-HANDOFF-008", severity="error", message=f"report created_at {report.created_at!r} is not an RFC 3339 timestamp with an explicit offset; lateness cannot be decided", **ids))
        elif deadline is not None and created > deadline:
            f.append(IntegrityFinding(code="INT-HANDOFF-005", severity="warning", message=f"report created at {created.isoformat()} is after the plan deadline {deadline.isoformat()}", **ids))
    elif parse_rfc3339(report.created_at) is None:
        f.append(IntegrityFinding(code="INT-HANDOFF-008", severity="error", message=f"report created_at {report.created_at!r} is not an RFC 3339 timestamp with an explicit offset", **ids))
    for c in report.claims:
        if c.advisory_verification_status is not None or c.advisory_verification_eligibility is not None:
            what = [n for n, v in (("verification status", c.advisory_verification_status), ("verification eligibility", c.advisory_verification_eligibility)) if v is not None]
            f.append(IntegrityFinding(code="INT-HANDOFF-006", severity="info", message=f"agent self-reported {' and '.join(what)}; advisory only, ignored", claim_ids=[c.claim_id], report_ids=ids["report_ids"], agent_ids=ids["agent_ids"]))
        mismatch = [n for n, a, b in (("request_id", c.request_id, report.request_id), ("task_id", c.task_id, report.task_id), ("agent_id", c.agent_id, report.agent_id), ("subject", c.subject.strip().lower(), report.subject.strip().lower()), ("task_type", c.task_type, report.task_type)) if a != b]
        if c.course_level not in (None, "unknown") and report.course_level not in (None, "unknown") and c.course_level != report.course_level:
            mismatch.append("course_level")
        if mismatch:
            f.append(IntegrityFinding(code="INT-HANDOFF-012", severity="error", message=f"claim {c.claim_id} carries provenance that differs from its report in {mismatch}: a wrong-task or wrong-agent claim hidden inside a right-task report", claim_ids=[c.claim_id], report_ids=ids["report_ids"], agent_ids=sorted({report.agent_id, c.agent_id})))
    return f


def check_report_set(plan: WorkPlan, reports: list[SpecialistReport]) -> list[IntegrityFinding]:
    """Plan-level accounting of WHO reported: a selected specialist that never reports is
    silent data loss (INT-HANDOFF-007); an agent reporting twice may have superseded
    itself (INT-HANDOFF-009)."""
    f: list[IntegrityFinding] = []
    by_agent: dict[str, list[SpecialistReport]] = {}
    for r in reports:
        by_agent.setdefault(r.agent_id, []).append(r)
    missing = sorted(set(plan.selected_agent_ids) - set(by_agent))
    if missing:
        f.append(IntegrityFinding(code="INT-HANDOFF-007", severity="error", message=f"selected agents delivered no report: {missing}; any synthesis is incomplete", agent_ids=missing, report_ids=[r.report_id for r in reports]))
    for agent, rs in sorted(by_agent.items()):
        if len(rs) > 1:
            f.append(IntegrityFinding(code="INT-HANDOFF-009", severity="warning", message=f"agent {agent} delivered {len(rs)} reports for one task; later reports may supersede earlier ones", agent_ids=[agent], report_ids=[r.report_id for r in rs], claim_ids=[c.claim_id for r in rs for c in r.claims]))
    return f


def check_result_binding(result: VerificationResult, current_problem: Problem, signing_key: Optional[bytes] = None, *, config: Optional[SolverConfig] = None, versions: Optional[Versions] = None) -> list[IntegrityFinding]:
    """A result is only valid for the exact representation, solver configuration and
    component versions it was produced for, and only when its signature verifies.

    ``config`` is the current solver configuration (compared when given); ``versions``
    defaults to the running engine's versions. With no ``signing_key`` the signature
    CANNOT be verified and that is itself an error (INT-STALE-006): the Overseer
    trusts only signed results."""
    f: list[IntegrityFinding] = []
    ids = dict(claim_ids=[current_problem.claim_id], formal_result_id=result.result_id)
    if result.binding.problem_digest != problem_digest(current_problem):
        f.append(IntegrityFinding(code="INT-STALE-001", severity="error", message="verification result was produced for a different representation of this claim; it must not be reused", **ids))
    if result.claim_id != current_problem.claim_id or result.request_id != current_problem.request_id:
        f.append(IntegrityFinding(code="INT-STALE-003", severity="error", message=f"verification result ids ({result.request_id}/{result.claim_id}) do not match the claim being decided ({current_problem.request_id}/{current_problem.claim_id})", **ids))
    if signing_key is None:
        f.append(IntegrityFinding(code="INT-STALE-006", severity="error", message="verification result signature NOT verified: no verification key configured; the Overseer must not treat it as engine evidence", **ids))
    elif not verify_signature(result, signing_key):
        f.append(IntegrityFinding(code="INT-STALE-002", severity="error", message="verification result is unsigned or its signature is invalid; the Overseer must not trust it", **ids))
    b = result.binding
    expected_binding = sha256_hex("|".join((b.problem_digest, b.config_digest, b.versions_digest)))
    inconsistent = []
    if b.binding_digest != expected_binding:
        inconsistent.append("binding_digest != sha256(problem_digest|config_digest|versions_digest)")
    if config_digest(result.solver_config) != b.config_digest:
        inconsistent.append("config_digest != digest(solver_config)")
    if versions_digest(result.versions) != b.versions_digest:
        inconsistent.append("versions_digest != digest(versions)")
    if inconsistent:
        f.append(IntegrityFinding(code="INT-STALE-007", severity="error", message="verification result binding is internally inconsistent: " + "; ".join(inconsistent), **ids))
    current_versions = versions or compute_versions()
    stale = []
    if config is not None and b.config_digest != config_digest(config):
        stale.append(f"solver configuration differs from the current one (result: {result.solver_config.model_dump()})")
    if b.versions_digest != versions_digest(current_versions):
        stale.append(f"component versions differ from the current ones (result: {result.versions.model_dump()}, current: {current_versions.model_dump()})")
    if stale:
        f.append(IntegrityFinding(code="INT-STALE-005", severity="error", message="verification result was produced under a different " + " and ".join(stale), **ids))
    return f
