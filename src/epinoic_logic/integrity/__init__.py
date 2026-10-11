"""Inter-agent communication integrity: envelopes, handoff, claim ledger, formal cross-checks."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from ..engine.results import SolverConfig, VerificationResult
from ..ir.schema import Assertion, Problem
from ..translate.contracts import SpecialistReport
from .contracts import (  # noqa: F401
    AgentMessage, AgentRole, ConflictRecord, IntegrityFinding, IntegrityReport, LedgerEntry, Synthesis,
    SynthesizedClaim, WorkPlan, payload_hash, CERTAINTY_RANK,
)
from .cross_check import check_cross_report_consistency, check_synthesis_entailment, joint_problem, claim_ids_from_core  # noqa: F401
from .envelope import MessageLog  # noqa: F401
from .handoff import check_report_against_plan, check_result_binding  # noqa: F401
from .ledger import check_synthesis_ledger  # noqa: F401


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_integrity_checks(
    plan: WorkPlan,
    reports: list[SpecialistReport],
    synthesis: Optional[Synthesis] = None,
    formalized: Optional[dict[str, Problem]] = None,
    synthesized_conclusions: Optional[dict[str, Assertion]] = None,
    prior_results: Optional[dict[str, VerificationResult]] = None,
    signing_key: Optional[bytes] = None,
    config: SolverConfig = SolverConfig(),
) -> IntegrityReport:
    """Run every applicable check and return one report for the Overseer.

    ``formalized`` maps claim_id -> Problem produced by the translator for that claim
    (shared glossary). ``synthesized_conclusions`` maps synthesized claim_id -> the
    formal conclusion to test against the union of the cited sources' premises.
    ``prior_results`` maps claim_id -> a stored VerificationResult to check for
    staleness against the current formalization.
    """
    findings: list[IntegrityFinding] = []
    checks: list[str] = []
    formal_ids: list[str] = []

    checks.append("handoff")
    for r in reports:
        findings += check_report_against_plan(plan, r)

    if synthesis is not None:
        checks.append("ledger")
        findings += check_synthesis_ledger(reports, synthesis)

    formalized = formalized or {}
    if prior_results:
        checks.append("staleness")
        for cid, res in prior_results.items():
            cur = formalized.get(cid)
            if cur is None:
                findings.append(IntegrityFinding(code="INT-STALE-004", severity="warning", message="stored result has no current formalization to compare against", claim_ids=[cid], formal_result_id=res.result_id))
            else:
                findings += check_result_binding(res, cur, signing_key)

    problems = list(formalized.values())
    if len(problems) >= 2:
        checks.append("cross_report_consistency")
        res, f = check_cross_report_consistency(problems, request_id=plan.request_id, config=config, signing_key=signing_key)
        findings += f
        if res is not None:
            formal_ids.append(res.result_id)
            if synthesis is not None and any(x.code == "INT-CONFLICT-001" for x in f):
                conflicting = {cid for x in f if x.code == "INT-CONFLICT-001" for cid in x.claim_ids}
                disclosed = any(set(c.claim_ids) & conflicting for c in synthesis.conflicts)
                if not disclosed:
                    findings.append(IntegrityFinding(code="INT-CONFLICT-002", severity="error", message="a formal contradiction between specialists is not disclosed in the synthesis conflict records", claim_ids=sorted(conflicting), formal_result_id=res.result_id, deterministic=False))

    if synthesis is not None and synthesized_conclusions:
        checks.append("synthesis_entailment")
        by_id = {c.claim_id: c for c in synthesis.claims}
        for scid, concl in synthesized_conclusions.items():
            sc = by_id.get(scid)
            if sc is None:
                findings.append(IntegrityFinding(code="INT-SYNTH-004", severity="warning", message="formal conclusion given for a claim not present in the synthesis", claim_ids=[scid]))
                continue
            sources = [formalized[sid] for sid in sc.source_claim_ids if sid in formalized]
            if not sources:
                findings.append(IntegrityFinding(code="INT-SYNTH-005", severity="warning", message="synthesized claim has no formalized source claims; entailment not checkable", claim_ids=[scid]))
                continue
            res, f = check_synthesis_entailment(sources, concl, request_id=plan.request_id, synthesized_claim_id=scid, config=config, signing_key=signing_key)
            findings += f
            if res is not None:
                formal_ids.append(res.result_id)

    return IntegrityReport(report_id=uuid.uuid4().hex, request_id=plan.request_id, task_id=plan.task_id, checks_run=checks, findings=findings, formal_result_ids=formal_ids, created_at=_now())
