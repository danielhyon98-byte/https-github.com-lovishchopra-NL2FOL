"""Z3 decision procedures over a compiled problem.

Three procedures, one per ``Problem.query``:

* ``run_consistency``   -> CONSISTENT | INCONSISTENT_PREMISES | UNKNOWN | TIMEOUT
* ``run_satisfiability`` -> SATISFIABLE | UNSATISFIABLE | UNKNOWN | TIMEOUT
* ``run_entailment``    -> INCONSISTENT_PREMISES | ENTAILED | COUNTEREXAMPLE | UNKNOWN | TIMEOUT

Entailment ALWAYS checks premise consistency first. Without that step, inconsistent
premises would make every conclusion "entailed" (vacuous entailment), which is
exactly the kind of silent error this engine exists to expose.

Every premise is asserted under its own tracking literal so that unsat cores can
be reported as premise ids: for ENTAILED these are the premises the proof relied
on; for INCONSISTENT_PREMISES they are the conflicting set. The core is ALWAYS
extracted (the tracking literals are passed as assumptions, so Z3 has it at no extra
cost): the dependency lists, the vacuity check and the circularity check are policy
evidence that rest on it, and ``SolverConfig.produce_unsat_core`` only decides whether
the runner serialises the raw core record. "Not computed" can never read as "no
dependencies".

Resource bounds: ``SolverConfig.timeout_ms`` is applied to each solver call, so an
entailment run may take up to twice the timeout. ``rlimit`` gives a deterministic
cutoff independent of wall-clock. A solver answer of ``unknown`` is classified as
TIMEOUT when Z3's reason mentions a timeout, cancellation or resource limit, and
as UNKNOWN otherwise. Neither is ever a success.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

import z3

from .compiler import Compiled, to_smt2
from .results import SolverConfig, StageTiming
from .statuses import VerificationStatus

NEGATED_CONCLUSION_MARKER = "__negated_conclusion__"
#: Lowest Z3 memory budget (MB) this engine will ever apply. Below it Z3 aborts with a
#: ``Z3Exception`` and the next solver call in the same process can segfault; the
#: schema minimum of ``SolverConfig.memory_max_mb`` matches this floor.
MEMORY_FLOOR_MB = 128
#: Budget restored after a memory abort (the ``SolverConfig`` default).
DEFAULT_MEMORY_MB = 512
_memory_lock = threading.Lock()
_applied_memory_mb: Optional[int] = None
#: Verifications currently between apply_global_memory_limit and release_global_memory_limit.
_active_verifications = 0
_TIMEOUT_REASONS = ("timeout", "canceled", "cancelled", "resource", "interrupted", "max. resource")
_MEMOUT_REASONS = ("memout", "memory")


@dataclass
class ProcedureOutcome:
    status: VerificationStatus
    model: Optional[dict[str, str]] = None
    core: list[str] = field(default_factory=list)
    includes_negated_conclusion: bool = False
    reason_unknown: Optional[str] = None
    timings: list[StageTiming] = field(default_factory=list)
    smt2: Optional[str] = None
    memout: bool = False


def _make_solver(compiled: Compiled, config: SolverConfig) -> z3.Solver:
    solver = z3.Solver(ctx=compiled.ctx)
    solver.set("timeout", int(config.timeout_ms))
    if config.rlimit is not None:
        solver.set("rlimit", int(config.rlimit))
    solver.set("random_seed", int(config.random_seed))
    return solver


def apply_global_memory_limit(config: SolverConfig) -> None:
    """Enter one verification's memory budget; pair with :func:`release_global_memory_limit`.

    ``memory_max_mb`` is the budget of ONE verification, never below :data:`MEMORY_FLOOR_MB`.
    Z3's ``memory_max_size`` is process-global (all contexts share it), so the limit applied
    is that budget times the number of verifications running at once, and while any
    verification runs the limit is only ever raised: 32 threads under a 512 MB limit meant
    for one run exhaust it together, Z3 aborts, and the next solver call segfaults the
    process. The limit falls back to the single budget only when no verification is
    active. The service refuses client-supplied values (see ``service.app``); library
    callers sharing a process with other Z3 users should pass ``memory_max_mb=None``
    (the verification is still counted so colleagues' budgets scale).
    """
    global _applied_memory_mb, _active_verifications
    with _memory_lock:
        _active_verifications += 1
        if config.memory_max_mb is None:
            return
        budget = max(int(config.memory_max_mb), MEMORY_FLOOR_MB) * _active_verifications
        if _applied_memory_mb is None or budget > _applied_memory_mb:
            z3.set_param("memory_max_size", budget)
            _applied_memory_mb = budget


def release_global_memory_limit(config: SolverConfig) -> None:
    """Leave one verification's budget. When nothing is running any more the process-wide
    limit returns to the single budget (lowering it is safe only then)."""
    global _applied_memory_mb, _active_verifications
    with _memory_lock:
        _active_verifications = max(0, _active_verifications - 1)
        if _active_verifications == 0 and config.memory_max_mb is not None:
            budget = max(int(config.memory_max_mb), MEMORY_FLOOR_MB)
            if _applied_memory_mb != budget:
                z3.set_param("memory_max_size", budget)
                _applied_memory_mb = budget


def reset_global_memory_limit() -> None:
    """After a memory abort: restore a budget no lower than what the verifications still
    running need (the default budget per active verification); never lower under load."""
    global _applied_memory_mb
    with _memory_lock:
        budget = max(DEFAULT_MEMORY_MB * max(1, _active_verifications), _applied_memory_mb or 0)
        z3.set_param("memory_max_size", budget)
        _applied_memory_mb = budget


def active_verifications() -> int:
    """Verifications currently holding a memory budget (for tests and diagnostics)."""
    with _memory_lock:
        return _active_verifications


def _classify_unknown(solver: z3.Solver) -> tuple[VerificationStatus, str, bool]:
    reason = solver.reason_unknown() or "unknown"
    lowered = reason.lower()
    if any(tag in lowered for tag in _TIMEOUT_REASONS):
        return VerificationStatus.TIMEOUT, reason, False
    memout = any(tag in lowered for tag in _MEMOUT_REASONS)
    return VerificationStatus.UNKNOWN, reason, memout


def format_value(value: z3.ExprRef) -> str:
    """Exact textual form of a model value: 'true'/'false', integer, or 'a/b'."""
    if z3.is_true(value):
        return "true"
    if z3.is_false(value):
        return "false"
    if z3.is_int_value(value):
        return value.as_string()
    if z3.is_rational_value(value):
        frac: Fraction = value.as_fraction()
        return str(frac.numerator) if frac.denominator == 1 else f"{frac.numerator}/{frac.denominator}"
    if z3.is_algebraic_value(value):
        # Irrational algebraic numbers cannot arise in v1 (linear arithmetic), but be explicit if they do.
        return f"~{value.approx(20)}"
    return str(value)


def extract_model(compiled: Compiled, model: z3.ModelRef, completion: bool) -> dict[str, str]:
    """Exact values for every declared symbol, in declaration order."""
    out: dict[str, str] = {}
    for name, sym in compiled.symbols.items():
        out[name] = format_value(model.eval(sym, model_completion=completion))
    return out


def _tracked_assertions(solver: z3.Solver, compiled: Compiled, negate_conclusion: bool) -> list[tuple[str, z3.BoolRef]]:
    """Assert each premise under a fresh tracking literal (names cannot clash with
    IR identifiers, which may not start with an underscore)."""
    ctx = compiled.ctx
    tracks: list[tuple[str, z3.BoolRef]] = []
    for index, (premise_id, term) in enumerate(compiled.premises.items()):
        literal = z3.Bool(f"__track_{index}", ctx)
        solver.add(z3.Implies(literal, term, ctx))
        tracks.append((premise_id, literal))
    if negate_conclusion:
        if compiled.conclusion is None:
            raise ValueError("entailment requires a conclusion")
        literal = z3.Bool("__track_neg_conclusion", ctx)
        solver.add(z3.Implies(literal, z3.Not(compiled.conclusion, ctx), ctx))
        tracks.append((NEGATED_CONCLUSION_MARKER, literal))
    return tracks


def _core_ids(solver: z3.Solver, tracks: list[tuple[str, z3.BoolRef]]) -> list[str]:
    core = list(solver.unsat_core())
    return [pid for pid, lit in tracks if any(lit.eq(c) for c in core)]


def _timed_check(solver: z3.Solver, tracks: list[tuple[str, z3.BoolRef]], stage: str, timings: list[StageTiming]) -> z3.CheckSatResult:
    start = time.perf_counter()
    result = solver.check(*[lit for _, lit in tracks])
    timings.append(StageTiming(stage=stage, ms=(time.perf_counter() - start) * 1000.0))
    return result


def _smt2_or_none(compiled: Compiled, config: SolverConfig, negate_conclusion: bool) -> Optional[str]:
    return to_smt2(compiled, negate_conclusion=negate_conclusion) if config.produce_smt2 else None


def _check_premises(compiled: Compiled, config: SolverConfig, stage: str, sat_status: VerificationStatus,
                    unsat_status: VerificationStatus, timings: list[StageTiming]) -> ProcedureOutcome:
    solver = _make_solver(compiled, config)
    tracks = _tracked_assertions(solver, compiled, negate_conclusion=False)
    result = _timed_check(solver, tracks, stage, timings)
    if result == z3.sat:
        return ProcedureOutcome(status=sat_status, model=extract_model(compiled, solver.model(), config.model_completion), timings=timings)
    if result == z3.unsat:
        return ProcedureOutcome(status=unsat_status, core=_core_ids(solver, tracks), timings=timings)
    status, reason, memout = _classify_unknown(solver)
    return ProcedureOutcome(status=status, reason_unknown=reason, timings=timings, memout=memout)


def run_consistency(compiled: Compiled, config: SolverConfig) -> ProcedureOutcome:
    """Are the premises jointly satisfiable?"""
    timings: list[StageTiming] = []
    outcome = _check_premises(compiled, config, "consistency", VerificationStatus.CONSISTENT, VerificationStatus.INCONSISTENT_PREMISES, timings)
    outcome.smt2 = _smt2_or_none(compiled, config, negate_conclusion=False)
    return outcome


def run_satisfiability(compiled: Compiled, config: SolverConfig) -> ProcedureOutcome:
    """Same check as consistency, reported as SATISFIABLE / UNSATISFIABLE for query problems."""
    timings: list[StageTiming] = []
    outcome = _check_premises(compiled, config, "satisfiability", VerificationStatus.SATISFIABLE, VerificationStatus.UNSATISFIABLE, timings)
    outcome.smt2 = _smt2_or_none(compiled, config, negate_conclusion=False)
    return outcome


def run_entailment(compiled: Compiled, config: SolverConfig) -> ProcedureOutcome:
    """Do the premises entail the conclusion? Consistency is checked first."""
    if compiled.conclusion is None:
        raise ValueError("entailment requires a conclusion")
    timings: list[StageTiming] = []
    smt2 = _smt2_or_none(compiled, config, negate_conclusion=True)

    first = _check_premises(compiled, config, "consistency", VerificationStatus.CONSISTENT, VerificationStatus.INCONSISTENT_PREMISES, timings)
    if first.status is not VerificationStatus.CONSISTENT:
        first.smt2 = smt2
        first.model = None  # no witness is reported for a failed or inconsistent precheck
        return first

    solver = _make_solver(compiled, config)
    tracks = _tracked_assertions(solver, compiled, negate_conclusion=True)
    result = _timed_check(solver, tracks, "entailment", timings)
    if result == z3.unsat:
        core = _core_ids(solver, tracks)
        return ProcedureOutcome(
            status=VerificationStatus.ENTAILED,
            core=[pid for pid in core if pid != NEGATED_CONCLUSION_MARKER],
            includes_negated_conclusion=NEGATED_CONCLUSION_MARKER in core,
            timings=timings, smt2=smt2,
        )
    if result == z3.sat:
        return ProcedureOutcome(
            status=VerificationStatus.COUNTEREXAMPLE,
            model=extract_model(compiled, solver.model(), config.model_completion),
            timings=timings, smt2=smt2,
        )
    status, reason, memout = _classify_unknown(solver)
    return ProcedureOutcome(status=status, reason_unknown=reason, timings=timings, smt2=smt2, memout=memout)
