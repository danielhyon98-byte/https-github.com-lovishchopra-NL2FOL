"""Top-level verification entry point: validate -> compile -> decide -> bind -> sign.

``verify`` never raises. Every failure mode becomes a result with a non-success
status and diagnostics, so callers (the service, the Overseer) always receive a
bound, auditable record of what happened.

Trust rules enforced here:

* a payload that arrives as bytes, text or a plain object is untrusted; any
  ``grounding.verified=True`` it asserts is discarded (``E505`` diagnostic) because
  only deterministic checks run in this process may set it;
* premise authority (:mod:`.authority`): only a grounding a check in this process
  verified establishes a premise. A quotation no check verified is an ungrounded
  dependency; every other grounding no check verified is an ``unverified_dependencies``
  entry, whatever authority its kind claims (an unchecked ``arithmetic_fact``,
  ``task_setting`` or ``rubric_rule`` included), so a model-chosen label can never hide
  an unsupported premise and a summary can never call it established;
* policy evidence is computed whatever the output options say: the unsat core is always
  extracted, and the dependency lists, the vacuity check and the circularity check rest
  on it. ``SolverConfig.produce_unsat_core`` only decides whether the raw ``unsat_core``
  record is serialised; "not computed" never reads as "no dependencies";
* a definitive status that used no premise at all carries ``E108`` (vacuous) so the
  outcome layer never displays a tautology as a verified claim;
* a COUNTEREXAMPLE that only reassigns a figure the problem defines but never asserts
  (a premise ``b <-> (n = 17)`` whose numeric symbol no other premise mentions, and with
  ``b`` asserted the conclusion is ENTAILED) is a coverage question, not by itself a
  mistranslation: a definition is not an assertion, and the question may leave the figure
  open. It carries the advisory ``W110`` and the COUNTEREXAMPLE stands as the verdict on
  the encoding. Only source-linked evidence that a source asserts the figure (a grounding
  on the figure or the defined atom that a check in this process verified:
  :func:`source_stated_symbols`) makes it ``E110`` (unasserted figure), which the outcome
  layer never displays as a verdict;
* a COUNTEREXAMPLE over zero premises carries ``E108`` (it says only that the conclusion
  is not a tautology). One whose falsification needs nothing but conclusion symbols that
  no premise mentions, a figure among them (for every assignment of the premises some
  value of those symbols makes the conclusion true), carries the advisory ``W111``: the
  question may leave them unconstrained, so the COUNTEREXAMPLE stands. Only source-linked
  evidence that a source states one of them (a verified grounding on the symbol) makes it
  ``E111`` (unencoded reason). A Bool point that no premise links to stays a
  COUNTEREXAMPLE with no diagnostic: that is the non sequitur verdict. The translation
  layer creates that evidence from the sources it holds (``translate.coverage``: a
  clause of the claim, a supporting claim, a supplied text or the task record that
  asserts the figure, read from its grammar by ``translate.assertion``), so its decision
  and this one are the same decision;
* an ENTAILED proof whose relied-on premises restate the conclusion (the conclusion, or
  each of its "and" conjuncts, is one of them or one of their conjuncts) carries ``E112``
  (circular) when those premises are the writer's own (an assumption, a specialist
  inference, general knowledge, an unchecked arithmetic_fact): the claim was assumed, not
  derived. A restated premise grounded in the task or a text is a transcription check.

Limits and policies:

* ``limits`` must be a :class:`~epinoic_logic.ir.schema.Limits`. Anything else is an
  INTERNAL_ERROR result, never a run under guessed bounds;
* every result path records ``limits`` on the result when they differ from
  ``DEFAULT_LIMITS``, before signing, and binds their digest
  (``Binding.limits_digest``, part of the binding digest), so a result decided under
  permissive limits never shares a binding with a default one. Default runs record
  neither: the default values are part of the bound policy identity
  (``Versions.policy_id``);
* when nonlinear terms are allowed, an assertion whose polynomial degree exceeds
  :data:`~epinoic_logic.engine.policies.NONLINEAR_MAX_DEGREE` is UNSUPPORTED (``E201``)
  before compilation, because Z3 cannot be interrupted inside some high-degree polynomial
  operations and would overrun its timeout.
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
from .authority import (  # noqa: F401 - re-exported: callers import the dependency rules from the runner
    CHECKABLE_KINDS,
    TASK_GIVEN_KINDS,
    UNGROUNDED_KINDS,
    assumed_grounding,
    has_authority,
    is_ungrounded,
    is_unverified,
    ungrounded_dependencies,
    unverified_dependencies,
)
from .compiler import CompileError, compile_problem
from .errors import DiagnosticCode
from .policies import NONLINEAR_MAX_DEGREE, max_degree
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
from .validator import ValidationOutcome, parse_and_validate, validate_problem

_PROCEDURES = {"entailment": run_entailment, "consistency": run_consistency, "satisfiability": run_satisfiability}


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
    The core is always computed (:mod:`.procedures`), so this check never depends on
    ``SolverConfig.produce_unsat_core``.
    """
    if proc.status is VerificationStatus.ENTAILED and not proc.core:
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
    if proc.status is VerificationStatus.COUNTEREXAMPLE and not problem.premises:
        return Diagnostic(
            code=DiagnosticCode.VACUOUS_RESULT.value,
            message="vacuous: the entailment query has no premises, so its COUNTEREXAMPLE says only that the conclusion is not a "
                    "tautology (nothing the claim rests on was encoded)",
            path="premises",
        )
    return None


def _assertion_vars(problem: Problem) -> tuple[set[str], set[str]]:
    """``(symbols the premises mention, symbols the conclusion mentions)``."""
    premise_vars: set[str] = set()
    for pr in problem.premises:
        _expr_vars(pr.expr, premise_vars)
    concl_vars = _expr_vars(problem.conclusion.expr, set()) if problem.conclusion is not None else set()
    return premise_vars, concl_vars


def source_stated_symbols(problem: Problem, names) -> list[Symbol]:
    """The symbols among ``names`` whose own grounding a check in this process verified (``verified=True``): source-linked
    evidence that a source states them. A label, a meaning or a grounding kind the translation chose is never such
    evidence, and an untrusted payload cannot supply it (its ``verified=True`` is discarded, ``E505``).

    The grounding's kind is not consulted. Coverage asks whether a source states what the encoding left open, not whether
    that statement is established: a figure the specialist's answer states from memory (``general_knowledge``) is still
    a figure the claim asserts, and a translation that only defines it omitted the assertion. Whether a premise is
    established is the separate authority rule of the dependency lists (:func:`~.authority.has_authority`). On a symbol,
    ``verified`` is coverage evidence and nothing else: no dependency list reads symbol groundings."""
    wanted = set(names)
    return [s for s in problem.symbols if s.name in wanted and s.grounding is not None and s.grounding.verified is True]


def _evidence_text(symbols: list[Symbol]) -> str:
    """'n (task_setting, verified against doc-1)' for each symbol a check located in a source."""
    out = []
    for sym in symbols[:6]:
        g = sym.grounding
        docs = sorted({r.document_id for r in g.source_refs}) if g is not None else []
        out.append(f"{sym.name} ({g.kind if g is not None else 'no grounding'}, verified" + (f" against {', '.join(docs[:3])}" if docs else "") + ")")
    return ", ".join(out)


def _unencoded_reason_diagnostic(problem: Problem, proc: ProcedureOutcome, compiled, config: SolverConfig) -> Optional[Diagnostic]:
    """A COUNTEREXAMPLE (over at least one premise) that falsifies the conclusion only through symbols no premise
    mentions: for every assignment that satisfies the premises, some value of those free symbols makes the conclusion
    true (decided by Z3 over ``premises AND forall free. NOT conclusion``, unsat).

    That is structural underdetermination, which can be the right answer to the question ("is x < y for an arbitrary
    y?"), so by itself it is the advisory ``W111`` and the counterexample stands. It is ``E111`` (unencoded reason: no
    verdict on the claim) only with source-linked evidence that a source states one of the free symbols
    (:func:`source_stated_symbols`): then the translation omitted what its source states. Undecided probes leave the
    counterexample as it is, with no diagnostic."""
    if proc.status is not VerificationStatus.COUNTEREXAMPLE or problem.conclusion is None or not problem.premises or compiled.conclusion is None:
        return None
    premise_vars, concl_vars = _assertion_vars(problem)
    sorts = {sym.name: sym.sort for sym in problem.symbols}
    free = sorted(v for v in concl_vars - premise_vars if v in compiled.symbols)
    # A Bool point no premise links to is the classic non sequitur: "the evidence holds and the point fails" is a verdict
    # on the claim. A figure the conclusion compares that no premise states is not: any value refutes it.
    if not free or not any(sorts.get(v) in _NUMERIC_SORTS for v in free):
        return None
    try:
        solver = z3.Solver(ctx=compiled.ctx)
        solver.set("timeout", int(config.timeout_ms))
        if config.rlimit is not None:
            solver.set("rlimit", int(config.rlimit))
        for term in compiled.premises.values():
            solver.add(term)
        solver.add(z3.ForAll([compiled.symbols[v] for v in free], z3.Not(compiled.conclusion)))
        answer = solver.check()
    except z3.Z3Exception:
        return None
    if answer != z3.unsat:
        return None
    model = proc.model or {}
    shown = ", ".join(f"{v}={model[v]}" for v in free if v in model) or ", ".join(free)
    stated = source_stated_symbols(problem, free)
    if stated:
        return Diagnostic(
            code=DiagnosticCode.UNENCODED_REASON.value,
            message=(f"unencoded reason: the counterexample falsifies the conclusion only through symbol(s) {', '.join(free)}, which no premise "
                     f"mentions ({shown}), and a source states {_evidence_text(stated)}: for every assignment of the premises some value of "
                     "them makes the conclusion true, so the translation omitted what its source states and this COUNTEREXAMPLE is no "
                     "verdict on the claim"),
            path="conclusion",
        )
    return Diagnostic(
        code=DiagnosticCode.UNENCODED_REASON_ADVISORY.value,
        message=(f"coverage (advisory): the counterexample falsifies the conclusion only through symbol(s) {', '.join(free)}, which no premise "
                 f"mentions ({shown}); for every assignment of the premises some value of them makes the conclusion true. No source-linked "
                 "evidence (a grounding on these symbols verified against the task or a supplied text) shows that a source states them, so "
                 "the question may leave them unconstrained and the COUNTEREXAMPLE stands as the verdict on the encoding; if a source does "
                 "state them, the translation omitted that premise"),
        path="conclusion",
    )


def _conjuncts(expr) -> list:
    """The "and" conjuncts of ``expr`` (nested conjunctions flattened); ``[expr]`` for anything else."""
    out, stack = [], [expr]
    while stack:
        node = stack.pop()
        if getattr(node, "op", None) == "and":
            stack.extend(reversed(node.args))
        else:
            out.append(node)
    return out


def _canonical(expr) -> str:
    import json
    return json.dumps(expr.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":"))


def circular_premises(problem: Problem, relied_on: Optional[list[str]] = None) -> list[str]:
    """The premises (among ``relied_on`` when given) that restate the conclusion: the conclusion, or each of its "and"
    conjuncts, is syntactically one of these premises or one of their conjuncts. Empty when the conclusion is derived
    from something else. Purely syntactic, no solver."""
    if problem.conclusion is None:
        return []
    pool = [pr for pr in problem.premises if relied_on is None or pr.id in relied_on]
    if not pool:
        return []
    owner: dict[str, str] = {}
    for pr in pool:
        owner.setdefault(_canonical(pr.expr), pr.id)
        for c in _conjuncts(pr.expr):
            owner.setdefault(_canonical(c), pr.id)
    needed = [_canonical(c) for c in _conjuncts(problem.conclusion.expr)]
    if not needed or not all(n in owner for n in needed):
        return []
    return list(dict.fromkeys(owner[n] for n in needed))


def _circular_diagnostic(problem: Problem, proc: ProcedureOutcome) -> Optional[Diagnostic]:
    """``E112`` when an ENTAILED proof's relied-on premises restate the conclusion (:func:`circular_premises`) and every
    restating premise is the writer's own (:func:`assumed_grounding`): the claim is assumed, not derived."""
    if proc.status is not VerificationStatus.ENTAILED or problem.conclusion is None:
        return None
    restating = circular_premises(problem, list(proc.core) or None)
    by_id = {pr.id: pr for pr in problem.premises}
    if not restating or not all(assumed_grounding(by_id[pid].grounding) for pid in restating if pid in by_id):
        return None
    labels = {pr.id: pr.label for pr in problem.premises}
    shown = "; ".join(f"{pid}" + (f" ({labels[pid][:100]!r})" if labels.get(pid) else "") for pid in restating[:6])
    return Diagnostic(
        code=DiagnosticCode.CIRCULAR_PREMISES.value,
        message=(f"circular: the premise(s) {shown} restate the conclusion (it, or each of its conjuncts, is asserted as a premise), so "
                 "the claim is assumed, not derived; this ENTAILED is no verdict on the claim"),
        path=f"premises.{restating[0]}",
    )


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
    """A COUNTEREXAMPLE that only reassigns figures the problem defines but never asserts: the entailment is re-run with
    each such defined atom asserted and is then ENTAILED.

    A definition is not an assertion, and the question may leave the figure open ("define b iff n = 17; does b
    necessarily hold?"), so by itself this is the advisory ``W110`` and the counterexample stands as the verdict on the
    encoding. It is ``E110`` (unasserted figure: no verdict on the claim, displayed as INVALID_FORMALIZATION) only with
    source-linked evidence that a source asserts the figure: a grounding on one of the reassigned figures or defined
    atoms that a check in this process verified (:func:`source_stated_symbols`). That the re-run is ENTAILED is never
    by itself a reason to add the premise. A re-run that is not ENTAILED leaves the counterexample as it is, with no
    diagnostic."""
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
    stated = source_stated_symbols(problem, [name for d in reassigned for name in (d.atom, *d.figures)])
    if stated:
        return Diagnostic(
            code=DiagnosticCode.UNASSERTED_FIGURE.value,
            message=("unasserted figure: the counterexample only reassigns figures the problem defines but never asserts: " + "; ".join(parts)
                     + f"; a source states {_evidence_text(stated)}, and with the defined atom(s) asserted the conclusion is ENTAILED, so the "
                     "translation omitted an assertion its source makes and this COUNTEREXAMPLE is no verdict on the claim (encode the stated "
                     "figure, the atom or the comparison itself, as a premise)"),
            path=f"premises.{reassigned[0].premise_id}",
        )
    return Diagnostic(
        code=DiagnosticCode.UNASSERTED_FIGURE_ADVISORY.value,
        message=("coverage (advisory): the counterexample only reassigns figures the problem defines but never asserts: " + "; ".join(parts)
                 + "; with the defined atom(s) asserted the conclusion would be ENTAILED, but a definition is not an assertion and no "
                 "source-linked evidence (a grounding on these figures or atoms verified against the task or a supplied text) shows that a "
                 "source asserts them, so the COUNTEREXAMPLE stands as the verdict on the encoding; if a source does assert the figure, "
                 "the translation omitted it"),
        path=f"premises.{reassigned[0].premise_id}",
    )


def _limits_record(limits: Limits) -> Optional[Limits]:
    """What a result records about the Limits it was decided under: ``None`` for the default
    values (they are part of the bound policy identity, ``Versions.policy_id``), else a plain
    ``Limits`` copy of the values that were enforced, which the binding also covers
    (``Binding.limits_digest``). Raises ``TypeError`` for anything that is not a ``Limits``."""
    if not isinstance(limits, Limits):
        raise TypeError("limits must be an epinoic_logic.ir.schema.Limits instance")
    values = {name: getattr(limits, name) for name in Limits.model_fields}
    if values == DEFAULT_LIMITS.model_dump():
        return None
    return Limits.model_validate(values)


def _degree_diagnostic(problem: Problem, limits: Limits) -> Optional[Diagnostic]:
    """``E201`` when nonlinear terms are allowed and an assertion's polynomial degree exceeds the
    engine bound. Under the linear gate every degree is at most 1, so nothing is checked."""
    if not limits.allow_nonlinear:
        return None
    degree, where = max_degree(problem)
    if degree <= NONLINEAR_MAX_DEGREE:
        return None
    return Diagnostic(
        code=DiagnosticCode.NONLINEAR_TERM.value,
        message=(
            f"polynomial degree {degree} exceeds the nonlinear policy bound {NONLINEAR_MAX_DEGREE}: "
            "the solver cannot be interrupted reliably on higher degrees"
        ),
        path=where,
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
    record: Optional[Limits] = None

    def finish(result: VerificationResult) -> VerificationResult:
        result.timings = timings + result.timings
        if record is not None:
            result.limits = record  # before signing: the record is covered by the signature
        if signing_key:
            return sign_result(result, signing_key, key_id or "default")
        return result

    try:
        record = _limits_record(limits)
        enforced = record if record is not None else DEFAULT_LIMITS
        t0 = time.perf_counter()
        trust_notes: list[Diagnostic] = []
        if isinstance(problem_or_raw, Problem):
            problem: Optional[Problem] = problem_or_raw
            outcome = validate_problem(problem, enforced)
        else:
            problem, outcome = parse_and_validate(problem_or_raw, enforced)
            if problem is not None:
                # Untrusted payload: nothing in this process checked its groundings.
                problem, trust_notes = _demote_asserted_verification(problem)
        if problem is not None and outcome.ok:
            too_high = _degree_diagnostic(problem, enforced)
            if too_high is not None:
                outcome = ValidationOutcome(ok=False, status=VerificationStatus.UNSUPPORTED, diagnostics=[too_high],
                                            node_count=outcome.node_count, max_depth=outcome.max_depth, sorts=outcome.sorts)
        timings.append(StageTiming(stage="validate", ms=(time.perf_counter() - t0) * 1000.0))

        if problem is None:
            return finish(VerificationResult(
                **base, request_id="unknown", claim_id="unknown", problem_id="unknown", query=None,
                status=outcome.status or VerificationStatus.INVALID_FORMALIZATION,
                binding=binding_for_unparsed(_raw_digest(problem_or_raw), config, versions, record),
                diagnostics=outcome.diagnostics,
            ))

        ids = dict(request_id=problem.request_id, claim_id=problem.claim_id, problem_id=problem.problem_id, query=problem.query)
        if not outcome.ok:
            return finish(VerificationResult(
                **base, **ids, status=outcome.status or VerificationStatus.INVALID_FORMALIZATION,
                binding=compute_binding(problem, config, versions, None, record), diagnostics=trust_notes + outcome.diagnostics,
            ))

        t1 = time.perf_counter()
        try:
            compiled = compile_problem(problem)
        except CompileError as exc:
            timings.append(StageTiming(stage="compile", ms=(time.perf_counter() - t1) * 1000.0))
            return finish(VerificationResult(
                **base, **ids, status=_status_for_compile_error(exc.diagnostic.code),
                binding=compute_binding(problem, config, versions, None, record), diagnostics=trust_notes + [exc.diagnostic],
            ))
        timings.append(StageTiming(stage="compile", ms=(time.perf_counter() - t1) * 1000.0))

        apply_global_memory_limit(config)
        figure_note: Optional[Diagnostic] = None
        reason_note: Optional[Diagnostic] = None
        try:
            proc = _PROCEDURES[problem.query](compiled, config)
            figure_note = _unasserted_figure_diagnostic(problem, proc, config)
            if figure_note is None:
                reason_note = _unencoded_reason_diagnostic(problem, proc, compiled, config)
        except z3.Z3Exception:
            # Z3 aborted (its memory budget was exhausted). Restore a budget the running
            # verifications can work within so later calls are not left under the exhausted one.
            reset_global_memory_limit()
            return finish(VerificationResult(
                **base, **ids, status=VerificationStatus.UNKNOWN,
                binding=compute_binding(problem, config, versions, None, record),
                diagnostics=trust_notes + [Diagnostic(code=DiagnosticCode.SOLVER_MEMOUT.value, message="solver aborted: memory budget exhausted")],
                reason_unknown="memory budget exhausted",
            ))
        finally:
            release_global_memory_limit(config)
        # The core is policy evidence, computed whatever produce_unsat_core says (see .procedures): the dependency lists,
        # E108 and E112 rest on it. The flag decides only whether the raw unsat_core record is serialised below.
        relied = list(proc.core)
        diagnostics = trust_notes + _solver_diagnostics(proc)
        vacuous = _vacuous_diagnostic(problem, proc, config)
        if vacuous is not None:
            diagnostics.append(vacuous)
        if figure_note is not None:
            diagnostics.append(figure_note)
        if reason_note is not None and vacuous is None:
            diagnostics.append(reason_note)
        circular = _circular_diagnostic(problem, proc) if vacuous is None else None
        if circular is not None:
            diagnostics.append(circular)
        result = VerificationResult(
            **base, **ids, status=proc.status,
            binding=compute_binding(problem, config, versions, proc.smt2, record),
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
        if config.produce_unsat_core and proc.status in (VerificationStatus.INCONSISTENT_PREMISES, VerificationStatus.UNSATISFIABLE, VerificationStatus.ENTAILED) and relied:
            from .results import UnsatCore
            result.unsat_core = UnsatCore(premise_ids=relied, includes_negated_conclusion=proc.includes_negated_conclusion)
        return finish(result)
    except Exception as exc:  # never leak internals; never raise to the caller
        ids = dict(request_id="unknown", claim_id="unknown", problem_id="unknown", query=None)
        if isinstance(problem_or_raw, Problem):
            ids = dict(request_id=problem_or_raw.request_id, claim_id=problem_or_raw.claim_id, problem_id=problem_or_raw.problem_id, query=problem_or_raw.query)
        try:
            binding = (compute_binding(problem_or_raw, config, versions, None, record) if isinstance(problem_or_raw, Problem)
                       else binding_for_unparsed(_raw_digest(problem_or_raw), config, versions, record))
        except Exception:
            binding = binding_for_unparsed("unavailable", config, versions, record)
        return finish(VerificationResult(
            **base, **ids, status=VerificationStatus.INTERNAL_ERROR, binding=binding,
            diagnostics=[Diagnostic(code=DiagnosticCode.INTERNAL.value, message=f"internal error of type {type(exc).__name__}")],
        ))
