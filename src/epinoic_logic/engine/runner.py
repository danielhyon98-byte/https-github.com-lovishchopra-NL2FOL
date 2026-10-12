"""Top-level verification entry point: validate -> compile -> decide -> bind -> sign.

``verify`` never raises. Every failure mode becomes a result with a non-success
status and diagnostics, so callers (the service, the Overseer) always receive a
bound, auditable record of what happened.

Trust rules enforced here:

* a payload that arrives as bytes, text or a plain object is untrusted; any
  ``grounding.verified=True`` it asserts is discarded (``E505`` diagnostic) because
  only deterministic checks run in this process may set it;
* a quotation grounding that no check verified positively is an ungrounded
  dependency; other asserted-but-unchecked groundings are listed separately as
  ``unverified_dependencies`` so a summary can never call them established;
* a definitive status that used no premise at all carries ``E108`` (vacuous) so the
  outcome layer never displays a tautology as a verified claim;
* a COUNTEREXAMPLE that only reassigns a figure the problem defines but never asserts
  (a premise ``b <-> (n = 17)`` whose numeric symbol no other premise mentions, and with
  ``b`` asserted the conclusion is ENTAILED) carries ``E110`` (unasserted figure), so the
  outcome layer never displays such a counterexample as a verdict on the claim.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Union

import z3

from ..ir.schema import DEFAULT_LIMITS, Assertion, Grounding, Limits, Problem, Symbol, Var
from .compiler import CompileError, compile_problem
from .errors import DiagnosticCode
from .procedures import (
    ProcedureOutcome,
    apply_global_memory_limit,
    release_global_memory_limit,
    reset_global_memory_limit,
    run_consistency,
    run_entailment,
    run_satisfiability,
)
from .provenance import binding_for_unparsed, compute_binding, compute_versions, sign_result
from .results import Counterexample, Diagnostic, ModelAssignment, SolverConfig, StageTiming, VerificationResult
from .statuses import VerificationStatus
from .validator import parse_and_validate, validate_problem

_PROCEDURES = {"entailment": run_entailment, "consistency": run_consistency, "satisfiability": run_satisfiability}
#: Grounding kinds that never establish a premise: they are the specialist's own steps.
UNGROUNDED_KINDS = frozenset({"assumption", "specialist_inference", "general_knowledge"})
#: Kinds given with the task itself; when unchecked they are asserted facts of the task, not of a source.
TASK_GIVEN_KINDS = frozenset({"arithmetic_fact", "task_setting", "rubric_rule"})
#: Kinds a deterministic check can verify positively; unchecked, they count as ungrounded.
CHECKABLE_KINDS = frozenset({"quotation"})


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


def is_ungrounded(grounding: Optional[Grounding]) -> bool:
    """True when a grounding does not establish its premise.

    Missing grounding, the inferential kinds, a failed check (``verified is False``)
    and a checkable kind (quotation) that no check verified positively are all
    ungrounded. The engine never trusts an asserted ``verified=True`` on a quotation
    unless a deterministic check set it; see :func:`verify` for the raw path.
    """
    if grounding is None or grounding.kind in UNGROUNDED_KINDS or grounding.verified is False:
        return True
    return grounding.kind in CHECKABLE_KINDS and grounding.verified is not True


def is_unverified(grounding: Optional[Grounding]) -> bool:
    """True for a grounding that is asserted but unchecked and is not a task-given fact."""
    if grounding is None or is_ungrounded(grounding):
        return False
    return grounding.verified is None and grounding.kind not in TASK_GIVEN_KINDS


def ungrounded_dependencies(problem: Problem, relied_on: list[str]) -> list[str]:
    """Relied-on premises whose support is missing, inferential, assumed, failed a grounding
    check, or (for checkable kinds) was never positively verified."""
    by_id = {p.id: p for p in problem.premises}
    return [pid for pid in relied_on if pid in by_id and is_ungrounded(by_id[pid].grounding)]


def unverified_dependencies(problem: Problem, relied_on: list[str]) -> list[str]:
    """Relied-on premises whose grounding is asserted (supplied_text, knowledge_document,
    library_source ...) but was not checked by any deterministic procedure."""
    by_id = {p.id: p for p in problem.premises}
    return [pid for pid in relied_on if pid in by_id and is_unverified(by_id[pid].grounding)]


def _demote_asserted_verification(problem: Problem) -> tuple[Problem, list[Diagnostic]]:
    """Discard ``grounding.verified=True`` on a problem that arrived as untrusted data.

    Only deterministic checks run in this process may set ``verified``. A payload
    that asserts it is self-certifying; the flag is reset to ``None`` (unchecked) and
    an ``E505`` diagnostic records the discard. ``False`` is kept: it only weakens.
    """
    diagnostics: list[Diagnostic] = []

    def demote(owner: str, g: Optional[Grounding]) -> Optional[Grounding]:
        if g is None or g.verified is not True:
            return g
        diagnostics.append(Diagnostic(
            code=DiagnosticCode.SELF_CERTIFICATION_REJECTED.value,
            message="grounding.verified=true was discarded: only deterministic grounding checks set it",
            path=owner,
        ))
        return g.model_copy(update={"verified": None})

    symbols: list[Symbol] = [s.model_copy(update={"grounding": demote(f"symbols[{i}].grounding", s.grounding)}) for i, s in enumerate(problem.symbols)]
    premises: list[Assertion] = [p.model_copy(update={"grounding": demote(f"premises[{i}].grounding", p.grounding)}) for i, p in enumerate(problem.premises)]
    conclusion = problem.conclusion.model_copy(update={"grounding": demote("conclusion.grounding", problem.conclusion.grounding)}) if problem.conclusion is not None else None
    if not diagnostics:
        return problem, []
    return problem.model_copy(update={"symbols": symbols, "premises": premises, "conclusion": conclusion}), diagnostics


def _vacuous_diagnostic(problem: Problem, proc: ProcedureOutcome, config: SolverConfig) -> Optional[Diagnostic]:
    """``E108`` when a definitive status rests on no premise at all.

    An ENTAILED proof whose unsat core contains only the negated conclusion holds under
    every assignment (a tautological or self-grounded conclusion); CONSISTENT or
    SATISFIABLE over zero premises asserts nothing. The status is still the solver's
    verdict about the encoding, but the outcome layer must not display it as a result.
    """
    if proc.status is VerificationStatus.ENTAILED and config.produce_unsat_core and not proc.core:
        return Diagnostic(
            code=DiagnosticCode.VACUOUS_RESULT.value,
            message="vacuous: the conclusion holds under every assignment; no premise was used in the proof",
            path="conclusion",
        )
    if proc.status in (VerificationStatus.CONSISTENT, VerificationStatus.SATISFIABLE) and not problem.premises:
        return Diagnostic(
            code=DiagnosticCode.VACUOUS_RESULT.value,
            message=f"vacuous: the {problem.query} query has no premises, so {proc.status.value} asserts nothing",
            path="premises",
        )
    return None


_COMPARE_OPS = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
_NUMERIC_SORTS = frozenset({"Int", "Real"})


@dataclass(frozen=True)
class FigureDefinition:
    """A premise that only DEFINES a Bool ``atom`` as a comparison over numeric ``figures`` that no other premise
    mentions (``b <-> (n = 17)`` with ``n`` free): it asserts nothing, so the figure its label states is never stated."""
    premise_id: str
    atom: str
    figures: tuple[str, ...]
    label: Optional[str]


def _expr_vars(expr, out: set[str]) -> set[str]:
    """Every symbol name ``expr`` mentions (an iterative walk: the validator bounds depth, this never recurses)."""
    stack = [expr]
    while stack:
        node = stack.pop()
        if getattr(node, "op", None) == "var":
            out.add(node.name)
            continue
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append(child)
        stack.extend(getattr(node, "args", None) or ())
    return out


def _is_figure_comparison(expr) -> bool:
    """A comparison of numeric terms, or a conjunction, disjunction or negation of such comparisons."""
    stack = [expr]
    while stack:
        node = stack.pop()
        op = getattr(node, "op", None)
        if op in _COMPARE_OPS:
            continue
        if op in ("and", "or"):
            stack.extend(node.args)
        elif op == "not":
            stack.append(node.arg)
        else:
            return False
    return True


def unasserted_figure_definitions(problem: Problem) -> list[FigureDefinition]:
    """The premises of ``problem`` that define a Bool atom by a comparison of numeric symbols (``iff`` with the atom on
    one side) while every numeric symbol of that comparison occurs in no premise other than such definitions. Each
    asserts nothing: whatever value the figure takes, the atom can be chosen to match. Purely syntactic, no solver."""
    sorts = {s.name: s.sort for s in problem.symbols}
    defs: list[tuple[str, str, set[str], Optional[str]]] = []
    for pr in problem.premises:
        e = pr.expr
        if getattr(e, "op", None) != "iff":
            continue
        for atom, other in ((e.left, e.right), (e.right, e.left)):
            if getattr(atom, "op", None) == "var" and sorts.get(atom.name) == "Bool" and _is_figure_comparison(other):
                figures = {v for v in _expr_vars(other, set()) if sorts.get(v) in _NUMERIC_SORTS}
                if figures:
                    defs.append((pr.id, atom.name, figures, pr.label))
                break
    if not defs:
        return []
    def_ids = {d[0] for d in defs}
    mentioned: set[str] = set()
    for pr in problem.premises:
        if pr.id not in def_ids:
            _expr_vars(pr.expr, mentioned)
    return [FigureDefinition(premise_id=pid, atom=atom, figures=tuple(sorted(figs)), label=label)
            for pid, atom, figs, label in defs if not (figs & mentioned)]


def _unasserted_figure_diagnostic(problem: Problem, proc: ProcedureOutcome, config: SolverConfig) -> Optional[Diagnostic]:
    """``E110`` when a COUNTEREXAMPLE only reassigns figures the problem defines but never asserts: the entailment is
    re-run with each such defined atom asserted (as the premise's label states it) and is then ENTAILED. The
    counterexample is still the solver's answer about the encoding, but it is no verdict on the claim, so the outcome
    layer displays it as INVALID_FORMALIZATION. A re-run that is not ENTAILED leaves the counterexample as it is."""
    if proc.status is not VerificationStatus.COUNTEREXAMPLE or problem.conclusion is None:
        return None
    defs = unasserted_figure_definitions(problem)
    if not defs:
        return None
    taken = {p.id for p in problem.premises} | {problem.conclusion.id}
    extra: list[Assertion] = []
    by_id: dict[str, FigureDefinition] = {}
    for i, d in enumerate(defs):
        aid = f"asserted_figure_{i}"
        while aid in taken:
            aid += "_"
        taken.add(aid)
        by_id[aid] = d
        extra.append(Assertion(id=aid, expr=Var(op="var", name=d.atom)))
    probe = problem.model_copy(update={"premises": list(problem.premises) + extra})
    try:
        again = _PROCEDURES["entailment"](compile_problem(probe), config.model_copy(update={"produce_smt2": False, "produce_unsat_core": True}))
    except Exception:  # a probe that cannot run leaves the counterexample as the solver gave it
        return None
    if again.status is not VerificationStatus.ENTAILED:
        return None
    model = proc.model or {}
    # The figures the conclusion needs are the asserted atoms the re-run's proof used (its unsat core).
    reassigned = [by_id[pid] for pid in again.core if pid in by_id] or [d for d in defs if model.get(d.atom) == "false"] or defs
    parts = []
    for d in reassigned:
        values = ", ".join(f"{f}={model[f]}" for f in d.figures if f in model)
        label = f" ({d.label[:120]!r})" if d.label else ""
        parts.append(f"premise {d.premise_id}{label} defines {d.atom} by a comparison of {', '.join(d.figures)}, which no premise asserts or constrains"
                     + (f" (the counterexample sets {values}, {d.atom}={model.get(d.atom, '?')})" if values else ""))
    return Diagnostic(
        code=DiagnosticCode.UNASSERTED_FIGURE.value,
        message=("unasserted figure: the counterexample only reassigns figures the problem defines but never asserts: " + "; ".join(parts)
                 + "; with the defined atom(s) asserted as the labels state them the conclusion is ENTAILED, so this COUNTEREXAMPLE is "
                 "no verdict on the claim (the translation must assert the stated figure: the atom, or the comparison itself, as a premise)"),
        path=f"premises.{reassigned[0].premise_id}",
    )


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
        trust_notes: list[Diagnostic] = []
        if isinstance(problem_or_raw, Problem):
            problem: Optional[Problem] = problem_or_raw
            outcome = validate_problem(problem, limits)
        else:
            problem, outcome = parse_and_validate(problem_or_raw, limits)
            if problem is not None:
                # Untrusted payload: nothing in this process checked its groundings.
                problem, trust_notes = _demote_asserted_verification(problem)
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
                binding=compute_binding(problem, config, versions, None), diagnostics=trust_notes + outcome.diagnostics,
            ))

        t1 = time.perf_counter()
        try:
            compiled = compile_problem(problem)
        except CompileError as exc:
            timings.append(StageTiming(stage="compile", ms=(time.perf_counter() - t1) * 1000.0))
            return finish(VerificationResult(
                **base, **ids, status=_status_for_compile_error(exc.diagnostic.code),
                binding=compute_binding(problem, config, versions, None), diagnostics=trust_notes + [exc.diagnostic],
            ))
        timings.append(StageTiming(stage="compile", ms=(time.perf_counter() - t1) * 1000.0))

        apply_global_memory_limit(config)
        figure_note: Optional[Diagnostic] = None
        try:
            proc = _PROCEDURES[problem.query](compiled, config)
            figure_note = _unasserted_figure_diagnostic(problem, proc, config)
        except z3.Z3Exception:
            # Z3 aborted (its memory budget was exhausted). Restore a budget the running
            # verifications can work within so later calls are not left under the exhausted one.
            reset_global_memory_limit()
            return finish(VerificationResult(
                **base, **ids, status=VerificationStatus.UNKNOWN,
                binding=compute_binding(problem, config, versions, None),
                diagnostics=trust_notes + [Diagnostic(code=DiagnosticCode.SOLVER_MEMOUT.value, message="solver aborted: memory budget exhausted")],
                reason_unknown="memory budget exhausted",
            ))
        finally:
            release_global_memory_limit(config)
        relied = list(proc.core)
        diagnostics = trust_notes + _solver_diagnostics(proc)
        vacuous = _vacuous_diagnostic(problem, proc, config)
        if vacuous is not None:
            diagnostics.append(vacuous)
        if figure_note is not None:
            diagnostics.append(figure_note)
        result = VerificationResult(
            **base, **ids, status=proc.status,
            binding=compute_binding(problem, config, versions, proc.smt2),
            premises_relied_on=relied,
            ungrounded_dependencies=ungrounded_dependencies(problem, relied),
            unverified_dependencies=unverified_dependencies(problem, relied),
            diagnostics=diagnostics,
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
