"""Inter-agent communication integrity: envelopes, handoff, claim ledger, formal cross-checks.

``run_integrity_checks`` never raises: every check runs inside a guard and an
internal failure becomes an INT-INTERNAL-001 error finding naming the check, so
the Overseer always receives a report.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from ..engine.results import SolverConfig, VerificationResult
from ..ir.schema import Assertion, Problem
from ..translate.contracts import SpecialistReport
from .contracts import (  # noqa: F401
    AgentMessage, AgentRole, ConflictRecord, IntegrityFinding, IntegrityReport, LedgerEntry, Synthesis,
    SynthesizedClaim, WorkPlan, payload_hash, parse_rfc3339, plan_digest, report_digest, seal_plan, sign_message,
    verify_message, verify_report_digest, envelope_digest, CERTAINTY_RANK, MESSAGE_MAX_CHARS,
)
from .cross_check import (  # noqa: F401
    JointMap, check_cross_report_consistency, check_paraphrase_coverage, check_synthesis_entailment, claim_ids_from_core,
    joint_problem,
)
from .envelope import MessageLog, bind_payload, ROLE_CONTRACTS  # noqa: F401
from .handoff import check_report_against_plan, check_report_set, check_result_binding  # noqa: F401
from .ledger import check_synthesis_ledger, meaningful, report_set_findings  # noqa: F401

REQUIRES_FORMAL_CHECK_ERROR = frozenset({"merged", "generalized"})
REQUIRES_FORMAL_CHECK_WARNING = frozenset({"narrowed", "paraphrased"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _grounding_docs(problem: Problem) -> set[str]:
    docs: set[str] = set()
    for s in problem.symbols:
        if s.grounding is not None:
            docs.update(r.document_id for r in s.grounding.source_refs)
    for a in list(problem.premises) + ([problem.conclusion] if problem.conclusion is not None else []):
        if a.grounding is not None:
            docs.update(r.document_id for r in a.grounding.source_refs)
    return docs


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
    (shared glossary); each entry is bound to the plan (key == Problem.claim_id,
    Problem.request_id == plan.request_id, claim present in a report) before it is
    pooled. ``synthesized_conclusions`` maps synthesized claim_id -> the formal
    conclusion to test against the union of the cited sources' premises.
    ``prior_results`` maps claim_id -> a stored VerificationResult to check for
    staleness against the current formalization and solver ``config``.
    """
    findings: list[IntegrityFinding] = []
    checks: list[str] = []
    formal_ids: list[str] = []
    report_ids = [r.report_id for r in reports]
    agent_ids = sorted({r.agent_id for r in reports})
    formalized = formalized or {}
    report_claim_ids = {c.claim_id for r in reports for c in r.claims}
    claims_by_id = {c.claim_id: c for r in reports for c in r.claims}
    valid: dict[str, Problem] = {}
    conflicting_sets: list[tuple[frozenset[str], Optional[str]]] = []

    def guarded(name: str, fn: Callable[[], None]) -> None:
        checks.append(name)
        try:
            fn()
        except Exception as exc:  # a failing check must not hide the whole report
            findings.append(IntegrityFinding(code="INT-INTERNAL-001", severity="error", message=f"integrity check {name!r} failed internally ({type(exc).__name__}: {str(exc)[:300]}); its findings are missing from this report and the Overseer must not treat the check as passed", report_ids=report_ids, agent_ids=agent_ids, claim_ids=sorted(formalized)))

    def handoff() -> None:
        for r in reports:
            findings.extend(check_report_against_plan(plan, r))
        findings.extend(check_report_set(plan, reports))
        if synthesis is None:
            findings.extend(report_set_findings(reports)[0])

    guarded("handoff", handoff)

    if synthesis is not None:
        def ledger() -> None:
            findings.extend(check_synthesis_ledger(reports, synthesis))
            syn_ids = dict(claim_ids=[synthesis.synthesis_id], agent_ids=[synthesis.combinator_agent_id])
            if synthesis.request_id != plan.request_id or synthesis.task_id != plan.task_id:
                findings.append(IntegrityFinding(code="INT-LEDGER-008", severity="error", message=f"synthesis belongs to another request/task ({synthesis.request_id}/{synthesis.task_id}) than the plan ({plan.request_id}/{plan.task_id})", **syn_ids))
            if plan.allowed_document_ids:
                allowed = set(plan.allowed_document_ids)
                for sc in synthesis.claims:
                    outside = sorted({r.document_id for r in sc.evidence_refs if r.document_id not in allowed})
                    if outside:
                        findings.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"synthesized claim cites documents outside the retrieval scope: {outside} (introduced by the combinator)", claim_ids=[sc.claim_id], document_ids=outside, agent_ids=[synthesis.combinator_agent_id]))
            created = parse_rfc3339(synthesis.created_at)
            if created is None:
                findings.append(IntegrityFinding(code="INT-HANDOFF-008", severity="error", message=f"synthesis created_at {synthesis.created_at!r} is not an RFC 3339 timestamp", **syn_ids))
            else:
                cited = set(synthesis.source_report_ids)
                for r in reports:
                    rc = parse_rfc3339(r.created_at)
                    if r.report_id in cited and rc is not None and created < rc:
                        findings.append(IntegrityFinding(code="INT-HANDOFF-016", severity="warning", message=f"synthesis created at {created.isoformat()} precedes report {r.report_id} created at {rc.isoformat()} that it cites", report_ids=[r.report_id], agent_ids=[synthesis.combinator_agent_id, r.agent_id], claim_ids=[synthesis.synthesis_id]))
                if plan.deadline_at:
                    dl = parse_rfc3339(plan.deadline_at)
                    if dl is not None and created > dl:
                        findings.append(IntegrityFinding(code="INT-HANDOFF-017", severity="warning", message=f"synthesis created at {created.isoformat()} is after the plan deadline {dl.isoformat()}", **syn_ids))

        guarded("ledger", ledger)

    def formalization_binding() -> None:
        allowed = set(plan.allowed_document_ids)
        for key, problem in formalized.items():
            why = []
            if key != problem.claim_id:
                why.append(f"map key {key!r} != Problem.claim_id {problem.claim_id!r}")
            if problem.request_id != plan.request_id:
                why.append(f"Problem.request_id {problem.request_id!r} != plan.request_id {plan.request_id!r}")
            if why:
                findings.append(IntegrityFinding(code="INT-STALE-009", severity="error", message="formalization does not belong to this claim/request and is excluded from the joint checks: " + "; ".join(why), claim_ids=sorted({key, problem.claim_id})))
                continue
            if reports and key not in report_claim_ids:
                findings.append(IntegrityFinding(code="INT-STALE-010", severity="error", message=f"formalization supplied for claim {key!r}, which no specialist report contains; excluded from the joint checks", claim_ids=[key], report_ids=report_ids))
                continue
            if allowed:
                outside = sorted(d for d in _grounding_docs(problem) if d not in allowed)
                if outside:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"formalization of claim {key!r} grounds premises in documents outside the retrieval scope: {outside}", claim_ids=[key], document_ids=outside))
            valid[key] = problem

    if formalized:
        guarded("formalization_binding", formalization_binding)

    if prior_results:
        def staleness() -> None:
            by_result: dict[str, list[str]] = {}
            for cid, res in prior_results.items():
                by_result.setdefault(res.result_id, []).append(cid)
            for rid, cids in by_result.items():
                if len(cids) > 1:
                    findings.append(IntegrityFinding(code="INT-STALE-008", severity="error", message=f"result id {rid!r} is shared by the stored results of claims {sorted(cids)}; results cannot be disambiguated by id", claim_ids=sorted(cids), formal_result_id=rid))
            for cid, res in prior_results.items():
                if reports and cid not in report_claim_ids:
                    findings.append(IntegrityFinding(code="INT-STALE-010", severity="error", message=f"stored verification result supplied for claim {cid!r}, which no specialist report contains", claim_ids=[cid], formal_result_id=res.result_id, report_ids=report_ids))
                cur = valid.get(cid)
                if cur is None:
                    findings.append(IntegrityFinding(code="INT-STALE-004", severity="error", message="stored result has no current (valid) formalization to compare against; it is unverifiable evidence", claim_ids=[cid], formal_result_id=res.result_id))
                else:
                    findings.extend(check_result_binding(res, cur, signing_key, config=config))

        guarded("staleness", staleness)

    problems = list(valid.values())
    if len(problems) >= 2:
        def cross() -> None:
            res, f = check_cross_report_consistency(problems, request_id=plan.request_id, config=config, signing_key=signing_key)
            findings.extend(f)
            if res is not None:
                formal_ids.append(res.result_id)
            for x in f:
                if x.code == "INT-CONFLICT-001":
                    conflicting_sets.append((frozenset(x.claim_ids), x.formal_result_id))

        guarded("cross_report_consistency", cross)

    if synthesis is not None and synthesized_conclusions:
        def entailment() -> None:
            by_id = {c.claim_id: c for c in synthesis.claims}
            for scid, concl in synthesized_conclusions.items():
                sc = by_id.get(scid)
                if sc is None:
                    findings.append(IntegrityFinding(code="INT-SYNTH-004", severity="warning", message="formal conclusion given for a claim not present in the synthesis", claim_ids=[scid]))
                    continue
                sources = [valid[sid] for sid in sc.source_claim_ids if sid in valid]
                unformalized = [sid for sid in sc.source_claim_ids if sid not in valid]
                if not sources:
                    findings.append(IntegrityFinding(code="INT-SYNTH-005", severity="warning", message=f"synthesized claim has no formalized source claims (cited: {sc.source_claim_ids}); entailment not checkable", claim_ids=[scid] + unformalized))
                    continue
                res, f = check_synthesis_entailment(sources, concl, request_id=plan.request_id, synthesized_claim_id=scid, config=config, signing_key=signing_key, unformalized_source_ids=unformalized, prior_results=prior_results)
                findings.extend(f)
                if res is not None:
                    formal_ids.append(res.result_id)
                    formal_ids.extend(rid for x in f for rid in x.related_result_ids)
                for x in f:
                    if x.code == "INT-CONFLICT-001":
                        conflicting_sets.append((frozenset(x.claim_ids) - {scid}, x.formal_result_id))
                if sc.transformation in ("carried", "paraphrased") and len(sources) == 1 and not unformalized:
                    res2, f2 = check_paraphrase_coverage(sources[0], concl, request_id=plan.request_id, synthesized_claim_id=scid, config=config, signing_key=signing_key)
                    findings.extend(f2)
                    if res2 is not None:
                        formal_ids.append(res2.result_id)

        guarded("synthesis_entailment", entailment)

    if synthesis is not None:
        def required_checks() -> None:
            supplied = set(synthesized_conclusions or {})
            for sc in synthesis.claims:
                known = [claims_by_id[s] for s in sc.source_claim_ids if s in claims_by_id]
                material = sc.materiality == "material" or any(c.materiality == "material" for c in known)
                if not material or sc.claim_id in supplied:
                    continue
                if sc.transformation in REQUIRES_FORMAL_CHECK_ERROR:
                    findings.append(IntegrityFinding(code="INT-SYNTH-006", severity="error", message=f"material claim produced by '{sc.transformation}' from {sc.source_claim_ids} has no formal conclusion in synthesized_conclusions: the required synthesis-entailment check was NOT performed", claim_ids=[sc.claim_id] + list(sc.source_claim_ids), agent_ids=[synthesis.combinator_agent_id]))
                elif sc.transformation in REQUIRES_FORMAL_CHECK_WARNING:
                    findings.append(IntegrityFinding(code="INT-SYNTH-012", severity="warning", message=f"material claim produced by '{sc.transformation}' from {sc.source_claim_ids} has no formal conclusion in synthesized_conclusions: content changes were not formally checked", claim_ids=[sc.claim_id] + list(sc.source_claim_ids), agent_ids=[synthesis.combinator_agent_id]))

        guarded("required_formal_checks", required_checks)

        def disclosure() -> None:
            by_id = {c.claim_id: c for c in synthesis.claims}

            def as_sources(ids: list[str]) -> set[str]:
                out: set[str] = set()
                for i in ids:
                    sc = by_id.get(i)
                    out.update(sc.source_claim_ids if sc is not None and sc.source_claim_ids else [i])
                return out

            records = [as_sources(list(c.claim_ids)) for c in synthesis.conflicts]
            seen: set[frozenset[str]] = set()
            for conflicting, rid in conflicting_sets:
                if len(conflicting) < 2 or conflicting in seen:
                    continue
                seen.add(conflicting)
                covering = [r for r in records if len(r & conflicting) >= 2]
                disclosed = conflicting <= set().union(*covering) if covering else False
                if not disclosed:
                    findings.append(IntegrityFinding(code="INT-CONFLICT-002", severity="error", message=f"a formal contradiction between specialist claims {sorted(conflicting)} is not disclosed in the synthesis conflict records (a record counts only if it names at least two of the conflicting claims, and together the records must name them all)", claim_ids=sorted(conflicting), formal_result_id=rid, agent_ids=[synthesis.combinator_agent_id], deterministic=False))

        guarded("conflict_disclosure", disclosure)

    report = IntegrityReport(report_id=uuid.uuid4().hex, request_id=plan.request_id, task_id=plan.task_id, checks_run=checks, findings=findings, formal_result_ids=formal_ids, created_at=_now())
    report.report_sha256 = report_digest(report)
    return report
