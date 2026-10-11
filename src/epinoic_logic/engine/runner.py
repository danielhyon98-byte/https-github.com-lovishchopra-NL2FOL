"""Top-level verification entry point: validate -> compile -> decide -> bind -> sign.

``verify`` never raises. Every failure mode becomes a result with a non-success
status and diagnostics, so callers (the service, the Overseer) always receive a
bound, auditable record of what happened.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Union

from ..ir.schema import DEFAULT_LIMITS, Limits, Problem
from .compiler import CompileError, compile_problem
from .errors import DiagnosticCode
from .procedures import ProcedureOutcome, apply_global_memory_limit, run_consistency, run_entailment, run_satisfiability
from .provenance import binding_for_unparsed, compute_binding, compute_versions, sign_result
from .results import Counterexample, Diagnostic, ModelAssignment, SolverConfig, StageTiming, VerificationResult
from .statuses import VerificationStatus
from .validator import parse_and_validate, validate_problem

_PROCEDURES = {"entailment": run_entailment, "consistency": run_consistency, "satisfiability": run_satisfiability}
UNGROUNDED_KINDS = frozenset({"assumption", "specialist_inference", "general_knowledge"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _raw_digest(raw: Union[bytes, str, dict]) -> str:
    if isinstance(raw, dict):
        from ..ir.canonical import canonical_json
        raw = canonical_json(raw)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _status_for_compile_error(code: str) -> VerificationStatus:
    return VerificationStatus.UNSUPPORTED if code.startswith("E2") else VerificationStatus.INVALID_FORMALIZATION


def ungrounded_dependencies(problem: Problem, relied_on: list[str]) -> list[str]:
    """Relied-on premises whose support is missing, inferential, assumed, or failed a grounding check."""
    by_id = {p.id: p for p in problem.premises}
    out: list[str] = []
    for pid in relied_on:
        premise = by_id.get(pid)
        if premise is None:
            continue
        g = premise.grounding
        if g is None or g.kind in UNGROUNDED_KINDS or g.verified is False:
            out.append(pid)
    return out


def _assignments(problem: Problem, model: dict[str, str]) -> list[ModelAssignment]:
    sorts = {s.name: s.sort for s in problem.symbols}
    return [ModelAssignment(symbol=name, sort=sorts[name], value=value) for name, value in model.items() if name in sorts]


def _solver_diagnostics(outcome: ProcedureOutcome) -> list[Diagnostic]:
    if outcome.status is VerificationStatus.TIMEOUT:
        return [Diagnostic(code=DiagnosticCode.SOLVER_TIMEOUT.value, message=f"solver stopped at its resource bound: {outcome.reason_unknown}")]
    if outcome.status is VerificationStatus.UNKNOWN:
        code = DiagnosticCode.SOLVER_MEMOUT if outcome.memout else DiagnosticCode.SOLVER_UNKNOWN
        return [Diagnostic(code=code.value, message=f"solver returned unknown: {outcome.reason_unknown}")]
    return []


def verify(
    problem_or_raw: Union[Problem, bytes, str, dict],
    config: SolverConfig = SolverConfig(),
    limits: Limits = DEFAULT_LIMITS,
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> VerificationResult:
    """Verify a problem (or an untrusted JSON payload) and return a bound result."""
    timings: list[StageTiming] = []
    versions = compute_versions()
    result_id = uuid.uuid4().hex
    base = dict(result_id=result_id, versions=versions, solver_config=config, issued_at=_now())

    def finish(result: VerificationResult) -> VerificationResult:
        result.timings = timings + result.timings
        if signing_key:
            return sign_result(result, signing_key, key_id or "default")
        return result

    try:
        t0 = time.perf_counter()
        if isinstance(problem_or_raw, Problem):
            problem: Optional[Problem] = problem_or_raw
            outcome = validate_problem(problem, limits)
        else:
            problem, outcome = parse_and_validate(problem_or_raw, limits)
        timings.append(StageTiming(stage="validate", ms=(time.perf_counter() - t0) * 1000.0))

        if problem is None:
            return finish(VerificationResult(
                **base, request_id="unknown", claim_id="unknown", problem_id="unknown", query=None,
                status=outcome.status or VerificationStatus.INVALID_FORMALIZATION,
                binding=binding_for_unparsed(_raw_digest(problem_or_raw), config, versions),
                diagnostics=outcome.diagnostics,
            ))

        ids = dict(request_id=problem.request_id, claim_id=problem.claim_id, problem_id=problem.problem_id, query=problem.query)
        if not outcome.ok:
            return finish(VerificationResult(
                **base, **ids, status=outcome.status or VerificationStatus.INVALID_FORMALIZATION,
                binding=compute_binding(problem, config, versions, None), diagnostics=outcome.diagnostics,
            ))

        t1 = time.perf_counter()
        try:
            compiled = compile_problem(problem)
        except CompileError as exc:
            timings.append(StageTiming(stage="compile", ms=(time.perf_counter() - t1) * 1000.0))
            return finish(VerificationResult(
                **base, **ids, status=_status_for_compile_error(exc.diagnostic.code),
                binding=compute_binding(problem, config, versions, None), diagnostics=[exc.diagnostic],
            ))
        timings.append(StageTiming(stage="compile", ms=(time.perf_counter() - t1) * 1000.0))

        apply_global_memory_limit(config)
        proc = _PROCEDURES[problem.query](compiled, config)
        relied = list(proc.core)
        result = VerificationResult(
            **base, **ids, status=proc.status,
            binding=compute_binding(problem, config, versions, proc.smt2),
            premises_relied_on=relied,
            ungrounded_dependencies=ungrounded_dependencies(problem, relied),
            diagnostics=_solver_diagnostics(proc),
            timings=proc.timings,
            reason_unknown=proc.reason_unknown,
        )
        if proc.status is VerificationStatus.COUNTEREXAMPLE and proc.model is not None:
            result.counterexample = Counterexample(assignments=_assignments(problem, proc.model))
        elif proc.status in (VerificationStatus.CONSISTENT, VerificationStatus.SATISFIABLE) and proc.model is not None:
            result.witness_model = _assignments(problem, proc.model)
        if proc.status in (VerificationStatus.INCONSISTENT_PREMISES, VerificationStatus.UNSATISFIABLE, VerificationStatus.ENTAILED) and relied:
            from .results import UnsatCore
            result.unsat_core = UnsatCore(premise_ids=relied, includes_negated_conclusion=proc.includes_negated_conclusion)
        return finish(result)
    except Exception as exc:  # never leak internals; never raise to the caller
        ids = dict(request_id="unknown", claim_id="unknown", problem_id="unknown", query=None)
        if isinstance(problem_or_raw, Problem):
            ids = dict(request_id=problem_or_raw.request_id, claim_id=problem_or_raw.claim_id, problem_id=problem_or_raw.problem_id, query=problem_or_raw.query)
        try:
            binding = compute_binding(problem_or_raw, config, versions, None) if isinstance(problem_or_raw, Problem) else binding_for_unparsed(_raw_digest(problem_or_raw), config, versions)
        except Exception:
            binding = binding_for_unparsed("unavailable", config, versions)
        return finish(VerificationResult(
            **base, **ids, status=VerificationStatus.INTERNAL_ERROR, binding=binding,
            diagnostics=[Diagnostic(code=DiagnosticCode.INTERNAL.value, message=f"internal error of type {type(exc).__name__}")],
        ))
