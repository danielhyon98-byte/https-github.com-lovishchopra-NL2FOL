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
* both shapes are assessed on every COUNTEREXAMPLE, as the translation layer assesses
  both: a counterexample that also has the W110 shape is still checked for ``E111``.
  Only an ``E110`` already withholds the verdict, so only then is the E111 check
  skipped. A no-verdict code takes precedence: an advisory of the other shape, which
  says the counterexample stands, is not carried beside it;
* the coverage checks run inside the decision's documented bound (an entailment may take
  up to twice ``timeout_ms``): the procedure and the checks share one deadline, each
  check's solver calls get what is left of it (never more than ``timeout_ms`` each), a
  check with nothing left is skipped (it decides nothing, as an undecided check does),
  and each one's time is recorded in ``timings`` (``coverage_probe_figure``,
  ``coverage_probe_reason``, with ``_skipped`` for a skipped one);
* an ENTAILED proof whose relied-on premises restate the conclusion (the conclusion, or
  each of its "and" conjuncts, is one of them or one of their conjuncts, as written or
  in a trivially different form: ``41 = dt`` for ``dt = 41``, ``not not p`` for ``p``,
  ``x <= a and x >= a`` for ``x = a``; :func:`circular_premises`) carries ``E112``
  (circular) when those premises are the writer's own: no check in this process
  established them, whatever kind their grounding claims (:func:`assumed_grounding` is
  ``not has_authority``, policy 2026.10-v5): the claim was assumed, not derived. A
  restated premise that a check verified against the task record or a supplied text is
  a transcription check, not a circle;
* a payload that never becomes a Problem is still bound to a digest of exactly what was
  sent, whatever it is (``None``, a list, a number, a dict nested deeper than the
  recursion limit or holding a lone surrogate or an integer too long for decimal text),
  so the validator's INVALID_FORMALIZATION reaches the caller, never an INTERNAL_ERROR
  raised while the rejection is bound;
* with ``produce_unsat_core`` the raw core record is serialised on every ENTAILED,
  INCONSISTENT_PREMISES and UNSATISFIABLE result, a vacuous ENTAILED included (its record
  is empty, with the negated conclusion alone unsatisfiable).

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

Argument diagnosis (rules ``argdiag-2``, :mod:`.argument`):

* after the decision and before binding and signing, ``verify`` runs the argument stage on every
  decided problem unless the caller passed ``diagnose=False`` (internal probes, cross checks, branch
  formal checks and constraint checks do). Its diagnostics (``named_diagnostics``, engine layer only)
  and the rule version (``argument_rules``) are part of the signed result; a stage that raises, runs
  out of budget or returns something outside the contract records ``argdiag-2/incomplete:<reason>``
  and no diagnostic, so it can never fire a rule or read as "none found";
* ``severity_cap`` (``(level, reason)``; the translator passes ``("info", "ambiguous_translation")``
  for an ambiguous translation) is applied before signing, with ``capped_from`` recorded, except to the
  codes the cap does not cover (the equivocation codes);
* ``diagnose`` and ``severity_cap`` are Python keywords only, reachable from neither HTTP nor
  ``SolverConfig``; a diagnosis never changes the status, the dependency lists or the engine
  diagnostics.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

import z3

from .. import named as _named
from ..ir.schema import DEFAULT_LIMITS, Assertion, Grounding, Limits, Problem, Symbol, Var
from ..version import ARG_RULES_VERSION
from . import argument as _argument
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
from .policies import MAX_COEFFICIENT_DIGITS, MAX_FORCED_VALUE_DIGITS, NONLINEAR_MAX_DEGREE, coefficient_digits, forced_value_digits, max_degree
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


#: The fallback encoding of :func:`_raw_digest` starts with a byte no JSON text starts with, so its digests never collide
#: with the digest of a payload that canonical JSON can serialise.
_FALLBACK_TAG = "\x00epinoic:raw-payload:"
#: Containers and leaves the fallback encoding visits before it stops (a payload shared with itself many times over can
#: expand exponentially; the cut is recorded in the encoded text, so the digest stays deterministic).
_FALLBACK_BUDGET = 1_000_000


def _raw_digest(raw: object) -> str:
    """The digest a result binds for a payload that never became a Problem. Total: it never raises.

    Bytes and text are digested as they arrived (text as UTF-8, a lone surrogate written with ``surrogatepass``), and any
    other payload as its canonical JSON, so a dict, a list, a number or ``None`` is digested exactly as its JSON text would
    be (for valid text and a serialisable dict, the same digest as before). A payload canonical JSON cannot serialise
    (nesting deeper than the recursion limit, an integer with more digits than Python converts to text, a value of a
    non-JSON type) is digested over :func:`_fallback_encoding`. The validator's own status and diagnostics then reach the
    caller, instead of an INTERNAL_ERROR raised while the rejection was being bound."""
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(raw)).hexdigest()
    if isinstance(raw, str):
        return hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest()
    from ..ir.canonical import canonical_json, sha256_hex
    try:
        return sha256_hex(canonical_json(raw))
    except Exception:  # noqa: BLE001 - not serialisable as JSON (RecursionError, ValueError, TypeError, or its own code raised)
        pass
    try:
        text = _fallback_encoding(raw)
    except Exception:  # noqa: BLE001 - a payload that cannot even be walked is bound by its type alone
        text = f"{_FALLBACK_TAG}#unreadable:{type(raw).__name__}"
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def _fallback_leaf(value: object) -> str:
    """One leaf of :func:`_fallback_encoding`: JSON text where JSON has a form, a tagged token otherwise."""
    import json
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, int):
        try:
            return str(value)
        except ValueError:  # more digits than Python converts to decimal text
            return ("#int:-" if value < 0 else "#int:") + format(abs(value), "x")
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return "#" + type(value).__name__


def _fallback_encoding(raw: object) -> str:
    """A deterministic text for any payload, built by an iterative walk (no recursion, so nesting depth is no limit): dict
    keys in a fixed order, lists in order, a container met again inside itself written ``#cycle``, and the walk cut after
    :data:`_FALLBACK_BUDGET` items (``#cut``). It is not JSON and never equals a canonical JSON text (:data:`_FALLBACK_TAG`)."""
    out: list[str] = [_FALLBACK_TAG]
    open_ids: set[int] = set()
    stack: list[tuple[str, object]] = [("value", raw)]
    budget = _FALLBACK_BUDGET
    while stack:
        kind, item = stack.pop()
        if kind == "text":
            out.append(item)  # type: ignore[arg-type]
            continue
        if kind == "close":
            open_ids.discard(item)  # type: ignore[arg-type]
            continue
        budget -= 1
        if budget < 0:
            out.append("#cut")
            break
        if isinstance(item, (dict, list, tuple)):
            if id(item) in open_ids:
                out.append("#cycle")
                continue
            open_ids.add(id(item))
            stack.append(("close", id(item)))
            if isinstance(item, dict):
                # ordered by the key's type and text only (a stable sort never compares the values)
                entries = sorted((((type(k).__name__, _fallback_leaf(k)), v) for k, v in item.items()), key=lambda kv: kv[0])
                stack.append(("text", "}"))
                for i in range(len(entries) - 1, -1, -1):
                    (_kind, key), value = entries[i]
                    stack.append(("value", value))
                    stack.append(("text", key + ":"))
                    if i:
                        stack.append(("text", ","))
                stack.append(("text", "{"))
            else:
                stack.append(("text", "]"))
                for i in range(len(item) - 1, -1, -1):
                    stack.append(("value", item[i]))
                    if i:
                        stack.append(("text", ","))
                stack.append(("text", "["))
            continue
        out.append(_fallback_leaf(item))
    return "".join(out)


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


#: Solver calls the decision stage may spend, each bounded by ``timeout_ms`` (integration contract, resource bounds: "an
#: entailment may take up to twice the timeout"). The coverage probes below run inside the same bound, on what the
#: procedure left of it, so a verify call never holds the solver longer than the documented bound for its decision.
DECISION_SOLVER_CALLS = 2
#: Stage names of the coverage probes in ``VerificationResult.timings`` (a probe skipped because the decision bound was
#: spent is recorded with the ``_skipped`` suffix: it decided nothing, exactly like a probe the solver left undecided).
PROBE_FIGURE_STAGE = "coverage_probe_figure"
PROBE_REASON_STAGE = "coverage_probe_reason"


def _remaining_ms(deadline: float) -> int:
    """Whole milliseconds left before ``deadline`` (a ``time.perf_counter`` value); never negative."""
    return max(0, int((deadline - time.perf_counter()) * 1000.0))


def _unencoded_reason_diagnostic(problem: Problem, proc: ProcedureOutcome, compiled, config: SolverConfig,
                                 deadline: Optional[float] = None, timings: Optional[list[StageTiming]] = None) -> Optional[Diagnostic]:
    """A COUNTEREXAMPLE (over at least one premise) that falsifies the conclusion only through symbols no premise
    mentions: for every assignment that satisfies the premises, some value of those free symbols makes the conclusion
    true (decided by Z3 over ``premises AND forall free. NOT conclusion``, unsat).

    That is structural underdetermination, which can be the right answer to the question ("is x < y for an arbitrary
    y?"), so by itself it is the advisory ``W111`` and the counterexample stands. It is ``E111`` (unencoded reason: no
    verdict on the claim) only with source-linked evidence that a source states one of the free symbols
    (:func:`source_stated_symbols`): then the translation omitted what its source states.

    The probe's solver call is bounded by ``timeout_ms`` and by what is left before ``deadline`` (the decision bound,
    :data:`DECISION_SOLVER_CALLS`); with nothing left it is skipped, which decides nothing. Its time is appended to
    ``timings`` (stage :data:`PROBE_REASON_STAGE`). A probe that decides nothing (skipped, undecided or failed) leaves the
    counterexample standing only when no source-linked evidence bears on the free symbols, which the evidence check decides
    without the solver: with such evidence the COUNTEREXAMPLE is no verdict until the probe decides (``E111``, saying the
    probe did not decide), so a spent bound never lets a counterexample stand that the probe could have withheld (repair
    round 1, re-run review INV-4)."""
    if proc.status is not VerificationStatus.COUNTEREXAMPLE or problem.conclusion is None or not problem.premises or compiled.conclusion is None:
        return None
    premise_vars, concl_vars = _assertion_vars(problem)
    sorts = {sym.name: sym.sort for sym in problem.symbols}
    free = sorted(v for v in concl_vars - premise_vars if v in compiled.symbols)
    # A Bool point no premise links to is the classic non sequitur: "the evidence holds and the point fails" is a verdict
    # on the claim. A figure the conclusion compares that no premise states is not: any value refutes it.
    if not free or not any(sorts.get(v) in _NUMERIC_SORTS for v in free):
        return None
    stated = source_stated_symbols(problem, free)
    model = proc.model or {}
    shown = ", ".join(f"{v}={model[v]}" for v in free if v in model) or ", ".join(free)
    budget = int(config.timeout_ms) if deadline is None else min(int(config.timeout_ms), _remaining_ms(deadline))
    if budget < 1:
        if timings is not None:
            timings.append(StageTiming(stage=PROBE_REASON_STAGE + "_skipped", ms=0.0))
        return _undecided_reason(free, shown, stated, "was skipped: the decision bound was spent") if stated else None
    started = time.perf_counter()
    try:
        solver = z3.Solver(ctx=compiled.ctx)
        solver.set("timeout", budget)
        if config.rlimit is not None:
            solver.set("rlimit", int(config.rlimit))
        for term in compiled.premises.values():
            solver.add(term)
        solver.add(z3.ForAll([compiled.symbols[v] for v in free], z3.Not(compiled.conclusion)))
        answer = solver.check()
    except z3.Z3Exception:
        return _undecided_reason(free, shown, stated, "could not run") if stated else None
    finally:
        if timings is not None:
            timings.append(StageTiming(stage=PROBE_REASON_STAGE, ms=(time.perf_counter() - started) * 1000.0))
    if answer == z3.sat:
        return None
    if answer != z3.unsat:
        return _undecided_reason(free, shown, stated, "was undecided within its bound") if stated else None
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


def _undecided_reason(free: list[str], shown: str, stated, why: str) -> Diagnostic:
    """``E111`` for a COUNTEREXAMPLE whose unencoded-reason probe decided nothing (:func:`_unencoded_reason_diagnostic`)
    while a source states one of the free symbols: no verdict on the claim until the probe decides."""
    return Diagnostic(
        code=DiagnosticCode.UNENCODED_REASON.value,
        message=(f"unencoded reason (undecided): the counterexample falsifies the conclusion through symbol(s) {', '.join(free)}, which no "
                 f"premise mentions ({shown}), and a source states {_evidence_text(stated)}; the probe that decides whether the conclusion "
                 f"turns only on them {why}, so this COUNTEREXAMPLE is no verdict on the claim until it decides"),
        path="conclusion",
    )


def _undecided_figure(defs, stated, why: str) -> Diagnostic:
    """``E110`` for a COUNTEREXAMPLE whose unasserted-figure probe decided nothing (:func:`_unasserted_figure_diagnostic`)
    while a source states one of the defined figures or atoms: no verdict on the claim until the probe decides."""
    parts = "; ".join(f"premise {d.premise_id} defines {d.atom} by a comparison of {', '.join(d.figures)}, which no premise asserts" for d in defs[:4])
    return Diagnostic(
        code=DiagnosticCode.UNASSERTED_FIGURE.value,
        message=(f"unasserted figure (undecided): {parts}; a source states {_evidence_text(stated)}, and the probe that re-runs the entailment "
                 f"with the defined atom(s) asserted {why}, so this COUNTEREXAMPLE is no verdict on the claim until it decides"),
        path=f"premises.{defs[0].premise_id}",
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
    # the expression as JSON, written by the model's own serializer (field order fixed by the node class, so equal
    # expressions give equal text within one process)
    return expr.model_dump_json(exclude_none=True)


#: circular_premises answers by content: (conclusion, pool as (id, expression) pairs) -> the restating premise ids. The
#: translator's circularity rejection and the engine's E112 diagnostic read the same problem, and a pool with no restating
#: premise has no subset with one (repair round 2, ADV2-03: circularity was computed twice per claim).
_CIRCULAR_CACHE: "OrderedDict[tuple, tuple[str, ...]]" = OrderedDict()
_CIRCULAR_CACHE_MAX = 512
_CIRCULAR_LOCK = threading.Lock()


def circular_premises(problem: Problem, relied_on: Optional[list[str]] = None) -> list[str]:
    """See :func:`_circular_premises`; answers are kept by content (:data:`_CIRCULAR_CACHE`)."""
    if problem.conclusion is None:
        return []
    every = tuple((pr.id, _canonical(pr.expr)) for pr in problem.premises)
    concl = _canonical(problem.conclusion.expr)
    pool = every if relied_on is None else tuple(x for x in every if x[0] in relied_on)
    if not pool:
        return []
    with _CIRCULAR_LOCK:
        full = _CIRCULAR_CACHE.get((concl, every))
        if full is not None and not full:
            return []  # no premise restates the conclusion, so no subset of them does
        hit = _CIRCULAR_CACHE.get((concl, pool))
        if hit is not None:
            _CIRCULAR_CACHE.move_to_end((concl, pool))
            return list(hit)
    out = _circular_premises(problem, relied_on)
    with _CIRCULAR_LOCK:
        _CIRCULAR_CACHE[(concl, pool)] = tuple(out)
        while len(_CIRCULAR_CACHE) > _CIRCULAR_CACHE_MAX:
            _CIRCULAR_CACHE.popitem(last=False)
    return out


def _circular_premises(problem: Problem, relied_on: Optional[list[str]] = None) -> list[str]:
    """The premises (among ``relied_on`` when given) that restate the conclusion: the conclusion, or each of its "and"
    conjuncts, is one of these premises or one of their conjuncts. Empty when the conclusion is derived from something
    else. Purely syntactic, no solver.

    "Is" means equal as written, or equal in the normal form of :class:`_NormalForms`: a restatement written in a trivially
    different form (operands of a symmetric operator in another order, a comparison written the other way round, a
    negated comparison, a double negation, ``iff`` with a constant, a repeated disjunct or conjunct, ``x <= a and x >= a``
    for ``x = a``, a literal spelt differently) restates the conclusion exactly as the same text does. The normal form
    only adds matches to the written comparison, never removes one."""
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
    if needed and all(n in owner for n in needed):
        return list(dict.fromkeys(owner[n] for n in needed))
    return _restating_in_normal_form(problem.conclusion.expr, pool)


def _restating_in_normal_form(conclusion, pool: list[Assertion]) -> list[str]:
    """:func:`circular_premises` over normal forms: the premises of ``pool`` whose normal form, or a conjunct of it, is a
    conjunct of the conclusion's normal form, when every conjunct of the conclusion is one. Each expression is read in two
    normal forms, with and without ``x <= a and x >= a`` merged into ``x = a``, so ``x <= a and x >= a`` restates both
    ``x = a`` and ``x <= a``. A conclusion conjunct that normalises to a constant restates nothing (that is a tautology or a
    contradiction, which the vacuity and consistency checks name)."""
    forms = _NormalForms()
    owner: dict[int, str] = {}
    for pr in pool:
        for merge in (True, False):
            k = forms.of(pr.expr, merge)
            owner.setdefault(k, pr.id)
            for c in forms.conjuncts(k):
                owner.setdefault(c, pr.id)
    for merge in (True, False):
        needed = forms.conjuncts(forms.of(conclusion, merge))
        if not needed or any(forms.is_constant(n) for n in needed):
            continue
        if all(n in owner for n in needed):
            return list(dict.fromkeys(owner[n] for n in needed))
    return []


#: ``a > b`` is ``b < a`` and ``a >= b`` is ``b <= a``: the normal form keeps only ``lt``, ``le``, ``eq`` and ``ne``.
_FLIPPED_COMPARE = {"gt": "lt", "ge": "le"}
#: The comparison that holds exactly when the key does not (Int and Real are totally ordered).
_COMPLEMENT_COMPARE = {"lt": "ge", "le": "gt", "gt": "le", "ge": "lt", "eq": "ne", "ne": "eq"}
#: Children of each IR node, in order.
_CHILD_KEYS = ("arg", "left", "right", "cond", "then", "otherwise")
#: A literal longer than this is kept as written (Python's integer text limit is far above every validated literal).
_LITERAL_TEXT_MAX = 4000


class _NormalForms:
    """Normal forms of IR expressions, hash-consed so that equal forms share one integer id within one table.

    Every rewrite is an equivalence, so two expressions with the same form are equivalent; the converse does not hold (the
    form is a closed list of rewrites, not a decision procedure). Bottom-up, iterative (no recursion):

    * ``a > b`` is ``b < a``, ``a >= b`` is ``b <= a``; the operands of ``eq``, ``ne`` and ``iff`` are ordered;
    * ``not`` of a comparison is the complementary comparison, ``not not p`` is ``p``, ``not`` of a constant flips it;
    * ``and`` and ``or`` are flattened, ordered and without repeats; ``true`` and ``false`` are absorbed; with ``merge``
      ``x <= a and a <= x`` (in one conjunction) is ``x = a``;
    * ``iff`` and ``implies`` with a constant side, or with equal sides, are simplified; ``ite`` with a constant or negated
      condition, or equal branches, likewise;
    * ``add`` and ``mul`` are flattened and ordered;
    * an integer or rational literal is its value (``0.50`` is ``1/2``);
    * arithmetic identities (re-run review, fidelity-4 variant): ``x + 0``, ``x - 0``, ``x * 1`` and ``x / 1`` are ``x``;
      ``-c`` of a literal is the negated literal; a closed constant term (literals only) is its exact value when it
      holds at most one literal other than 0 and 1 (``40 + 1`` is ``41``: a literal spelt differently), while a term
      over two or more other literals (``2.0 + 0.40 * 60``) is a computation and is kept as written; ``a - b = 0`` and
      ``0 = a - b`` are ``a = b``. Solving an equation (``dt + 1 = 42``, ``2 * dt = 82``) is no rewrite of this form.

    The IR is read as data; nothing is evaluated (the folding above is exact rational arithmetic over the literals'
    values, on validated IR nodes)."""

    def __init__(self) -> None:
        self._ids: dict[tuple, int] = {}
        self._shapes: list[tuple] = []
        self.true = self._intern(("bool", True))
        self.false = self._intern(("bool", False))

    def _intern(self, shape: tuple) -> int:
        found = self._ids.get(shape)
        if found is None:
            found = len(self._shapes)
            self._ids[shape] = found
            self._shapes.append(shape)
        return found

    def is_constant(self, k: int) -> bool:
        return k in (self.true, self.false)

    def conjuncts(self, k: int) -> list[int]:
        shape = self._shapes[k]
        return list(shape[1]) if shape[0] == "and" else [k]

    def of(self, expr, merge: bool) -> int:
        """The id of ``expr``'s normal form (``merge``: read ``x <= a and a <= x`` as ``x = a``)."""
        done: dict[int, int] = {}
        stack: list[tuple[object, bool]] = [(expr, False)]
        while stack:
            node, expanded = stack.pop()
            if id(node) in done:
                continue
            kids = _children(node)
            if not expanded:
                stack.append((node, True))
                stack.extend((c, False) for c in reversed(kids) if id(c) not in done)
                continue
            done[id(node)] = self._combine(node, [done[id(c)] for c in kids], merge)
        return done[id(expr)]

    def _combine(self, node, kids: list[int], merge: bool) -> int:
        op = getattr(node, "op", None)
        if op == "var":
            return self._intern(("var", node.name))
        if op == "bool":
            return self.true if node.value else self.false
        if op in ("int", "real"):
            return self._literal(op, _literal_value(node.value))
        if op == "not":
            return self._negate(kids[0])
        if op in ("and", "or"):
            return self._junction(op, kids, merge)
        if op in ("add", "mul"):
            flat: list[int] = []
            for k in kids:
                shape = self._shapes[k]
                flat.extend(shape[1]) if shape[0] == op else flat.append(k)
            return self._arith(op, flat)
        if op == "sub" and len(kids) == 2:
            return self._sub(kids[0], kids[1])
        if op == "neg" and len(kids) == 1:
            return self._neg(kids[0])
        if op == "div" and len(kids) == 2 and self._value(kids[1]) == 1:
            return kids[0]
        if op == "iff":
            return self._iff(kids[0], kids[1])
        if op == "implies":
            return self._implies(kids[0], kids[1])
        if op == "ite":
            return self._ite(kids[0], kids[1], kids[2])
        if op in _COMPLEMENT_COMPARE:
            return self._compare(op, kids[0], kids[1])
        return self._intern((str(op), *kids))  # div, idiv, mod, to_real: kept as written, children normalised

    # -------------------------------------------------------------------- arithmetic identities (fidelity-4 variant)

    def _literal(self, op: str, value: str) -> int:
        return self._intern((op, value))

    def _value(self, k: int):
        """The exact value of a literal form, else None."""
        shape = self._shapes[k]
        if shape[0] not in ("int", "real"):
            return None
        from fractions import Fraction
        try:
            return Fraction(shape[1])
        except (ValueError, ZeroDivisionError):
            return None

    def _from_value(self, value, like: str) -> int:
        return self._literal("int" if like == "int" and value.denominator == 1 else "real", str(value))

    def _arith(self, op: str, members: list[int]) -> int:
        """``add`` / ``mul`` of normal forms: the identity element dropped, and a closed constant term with at most one
        literal other than 0 and 1 folded to its exact value (class docstring)."""
        unit = 0 if op == "add" else 1
        kept = [m for m in members if self._value(m) != unit]
        if not kept:
            return self._literal("int", str(unit))
        values = [self._value(m) for m in kept]
        if all(v is not None for v in values) and len(kept) > 1 and sum(1 for v in values if v not in (0, 1)) <= 1:
            total = values[0]
            for v in values[1:]:
                total = total + v if op == "add" else total * v
            like = "int" if all(self._shapes[m][0] == "int" for m in kept) else "real"
            return self._from_value(total, like)
        if len(kept) == 1:
            return kept[0]
        return self._intern((op, tuple(sorted(kept))))

    def _neg(self, k: int) -> int:
        v = self._value(k)
        if v is not None:
            return self._from_value(-v, self._shapes[k][0])
        return self._intern(("neg", k))

    def _sub(self, a: int, b: int) -> int:
        vb = self._value(b)
        if vb == 0:
            return a
        va = self._value(a)
        if va is not None and vb is not None and sum(1 for v in (va, vb) if v not in (0, 1)) <= 1:
            like = "int" if self._shapes[a][0] == "int" and self._shapes[b][0] == "int" else "real"
            return self._from_value(va - vb, like)
        return self._intern(("sub", a, b))

    def _compare(self, op: str, a: int, b: int) -> int:
        if op in ("eq", "ne"):
            # a - b = 0 (or 0 = a - b) is a = b: the difference of two equal terms is zero, and nothing else
            for x, y in ((a, b), (b, a)):
                if self._value(y) == 0 and self._shapes[x][0] == "sub":
                    a, b = self._shapes[x][1], self._shapes[x][2]
                    break
        if op in _FLIPPED_COMPARE:
            op, a, b = _FLIPPED_COMPARE[op], b, a
        if op in ("eq", "ne") and b < a:
            a, b = b, a
        return self._intern(("cmp", op, a, b))

    def _negate(self, k: int) -> int:
        if k == self.true:
            return self.false
        if k == self.false:
            return self.true
        shape = self._shapes[k]
        if shape[0] == "not":
            return shape[1]
        if shape[0] == "cmp":
            return self._compare(_COMPLEMENT_COMPARE[shape[1]], shape[2], shape[3])
        return self._intern(("not", k))

    def _junction(self, op: str, kids: list[int], merge: bool) -> int:
        unit, zero = (self.true, self.false) if op == "and" else (self.false, self.true)
        members: set[int] = set()
        for k in kids:
            shape = self._shapes[k]
            for m in (shape[1] if shape[0] == op else (k,)):
                if m == zero:
                    return zero
                if m != unit:
                    members.add(m)
        if op == "and" and merge:
            members = self._merge_bounds(members)
        if not members:
            return unit
        if len(members) == 1:
            return next(iter(members))
        return self._intern((op, tuple(sorted(members))))

    def _merge_bounds(self, members: set[int]) -> set[int]:
        """``a <= b`` and ``b <= a`` in one conjunction become ``a = b``."""
        bounds = {(self._shapes[m][2], self._shapes[m][3]): m for m in members if self._shapes[m][0] == "cmp" and self._shapes[m][1] == "le"}
        out = set(members)
        for (a, b), m in bounds.items():
            if a < b and (b, a) in bounds:
                out.discard(m)
                out.discard(bounds[(b, a)])
                out.add(self._compare("eq", a, b))
        return out

    def _iff(self, a: int, b: int) -> int:
        if a == self.true:
            return b
        if b == self.true:
            return a
        if a == self.false:
            return self._negate(b)
        if b == self.false:
            return self._negate(a)
        if a == b:
            return self.true
        return self._intern(("iff", min(a, b), max(a, b)))

    def _implies(self, a: int, b: int) -> int:
        if a == self.true:
            return b
        if a == self.false or b == self.true or a == b:
            return self.true
        if b == self.false:
            return self._negate(a)
        return self._intern(("implies", a, b))

    def _ite(self, c: int, t: int, o: int) -> int:
        if c == self.true:
            return t
        if c == self.false:
            return o
        if t == o:
            return t
        shape = self._shapes[c]
        if shape[0] == "not":
            c, t, o = shape[1], o, t
        return self._intern(("ite", c, t, o))


def _children(node) -> list:
    # an IR node keeps its fields in its __dict__: reading them there avoids the model's slow attribute fallback for the keys a
    # node does not have (repair round 2, ADV2-03: this walk was the largest single cost of a typical claim's argument checks)
    d = getattr(node, "__dict__", None)
    if d is None:
        kids = [getattr(node, key) for key in _CHILD_KEYS if getattr(node, key, None) is not None]
        return kids + list(getattr(node, "args", None) or ())
    kids = [d[key] for key in _CHILD_KEYS if d.get(key) is not None]
    args = d.get("args")
    return kids + list(args) if args else kids


def _literal_value(text: str) -> str:
    """An IR literal as its exact value (``"0.50"`` and ``"1/2"`` alike); a literal too long to read is kept as written."""
    if len(text) > _LITERAL_TEXT_MAX:
        return text
    from fractions import Fraction
    try:
        return str(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return text


def _circular_diagnostic(problem: Problem, proc: ProcedureOutcome, equivalent: Sequence[str] = ()) -> Optional[Diagnostic]:
    """``E112`` when an ENTAILED proof's relied-on premises restate the conclusion (:func:`circular_premises`) and every
    restating premise is the writer's own (:func:`assumed_grounding`), or when one relied-on premise of the writer's own is
    equivalent to the conclusion under every assignment (``equivalent``, decided by :func:`equivalent_premises`): the claim is
    assumed, not derived."""
    if proc.status is not VerificationStatus.ENTAILED or problem.conclusion is None:
        return None
    restating = circular_premises(problem, list(proc.core) or None)
    by_id = {pr.id: pr for pr in problem.premises}
    labels = {pr.id: pr.label for pr in problem.premises}
    if not restating or not all(assumed_grounding(by_id[pid].grounding) for pid in restating if pid in by_id):
        if not equivalent:
            return None
        shown = "; ".join(f"{pid}" + (f" ({labels[pid][:100]!r})" if labels.get(pid) else "") for pid in list(equivalent)[:6])
        return Diagnostic(
            code=DiagnosticCode.CIRCULAR_PREMISES.value,
            message=(f"circular: the premise(s) {shown}, which no check in this process established, restate the conclusion in other terms "
                     "(the solver finds the premise equivalent to the conclusion under every assignment), so the claim is assumed, not "
                     "derived; this ENTAILED is no verdict on the claim"),
            path=f"premises.{equivalent[0]}",
        )
    shown = "; ".join(f"{pid}" + (f" ({labels[pid][:100]!r})" if labels.get(pid) else "") for pid in restating[:6])
    return Diagnostic(
        code=DiagnosticCode.CIRCULAR_PREMISES.value,
        message=(f"circular: the premise(s) {shown} restate the conclusion (it, or each of its conjuncts, is asserted as a premise), so "
                 "the claim is assumed, not derived; this ENTAILED is no verdict on the claim"),
        path=f"premises.{restating[0]}",
    )


#: The restatement test beyond the normal form (:func:`equivalent_premises`) decides at most this many premises, each in at
#: most :data:`RESTATEMENT_RUN_MS` of solver time.
MAX_RESTATEMENT_CHECKS = 4
RESTATEMENT_RUN_MS = 1000
#: Stage name of that test in ``VerificationResult.timings``.
RESTATEMENT_STAGE = "restatement"


def equivalent_premises(problem: Problem, relied_on: Optional[Sequence[str]] = None, *, compiled=None, budget_ms: int = RESTATEMENT_RUN_MS,
                        timings: Optional[list[StageTiming]] = None) -> list[str]:
    """The premise (among ``relied_on`` when given) of the writer's own (:func:`assumed_grounding`) that restates the
    conclusion in other terms: equivalent to it under every assignment, decided by Z3 (``premise == conclusion`` valid),
    though no rewrite of :func:`circular_premises`'s normal form reads it ("2 x dt = 82", "dt + 1 = 42" or "40 < dt < 42"
    over Int, for "dt = 41"; a De Morgan form; repair round 2, fidelity-4 variant). A restatement is read as the argument
    rule ARG-CIRC-002 reads it: the conclusion computes nothing (no arithmetic), the premise uses the same symbols, and
    either it computes nothing and uses the conclusion's literal values, or it cites no source and is no computation of
    the conclusion's figure (``rate = 2.0 + 0.40 x 60`` for ``rate = 26`` is a step of working, never a circle). At most
    :data:`MAX_RESTATEMENT_CHECKS` premises are decided, within ``budget_ms`` in all; an undecided check finds nothing.
    When none restates the point alone, the conjunction of those candidates is decided once: premises of the writer's own
    that together are equivalent to the point ("dt <= 41" and "dt >= 41" for "dt = 41") restate it jointly and are all
    returned (repair round 4, fidelity-4 variant). Empty when there is none."""
    if problem.query != "entailment" or problem.conclusion is None or budget_ms < 1:
        return []
    concl = problem.conclusion.expr.model_dump(mode="json", exclude_none=True)
    if _argument._has_op(concl, _argument._ARITH):
        return []
    concl_vars = _argument._vars(concl)
    concl_literals = _argument._literal_values(concl)
    target = _canonical(problem.conclusion.expr)
    candidates: list[str] = []
    for pr in problem.premises:
        if relied_on is not None and pr.id not in relied_on:
            continue
        if not assumed_grounding(pr.grounding):
            continue
        node = pr.expr.model_dump(mode="json", exclude_none=True)
        if _argument._vars(node) != concl_vars or _canonical(pr.expr) == target:
            continue
        g = pr.grounding
        restates = not _argument._has_op(node, _argument._ARITH) and _argument._literal_values(node) == concl_literals
        unsourced = g is None or (g.kind in _argument.cues.WRITER_STEP_KINDS and not g.source_refs)
        if restates or (unsourced and not _argument._computation(node)):
            candidates.append(pr.id)
    if not candidates:
        return []
    started = time.perf_counter()
    found: list[str] = []
    try:
        if compiled is None:
            compiled = compile_problem(problem)
        for pid in candidates[:MAX_RESTATEMENT_CHECKS]:
            left = budget_ms - int((time.perf_counter() - started) * 1000.0)
            term = compiled.premises.get(pid)
            if left < 1 or term is None or compiled.conclusion is None:
                break
            solver = z3.Solver(ctx=compiled.ctx)
            solver.set("timeout", min(left, RESTATEMENT_RUN_MS))
            solver.add(z3.Not(term == compiled.conclusion))
            if solver.check() == z3.unsat:
                found.append(pid)
                break
        joint = candidates[:MAX_RESTATEMENT_CHECKS]
        left = budget_ms - int((time.perf_counter() - started) * 1000.0)
        if not found and len(joint) >= 2 and left >= 1 and compiled.conclusion is not None:
            # a restatement split across premises of the writer's own ("dt <= 41" and "dt >= 41" for "dt = 41"; repair round
            # 4, fidelity-4 variant): together they say the point, so it is assumed as surely as when one premise says it
            terms = [compiled.premises.get(pid) for pid in joint]
            if all(t is not None for t in terms):
                solver = z3.Solver(ctx=compiled.ctx)
                solver.set("timeout", min(left, RESTATEMENT_RUN_MS))
                solver.add(z3.Not(z3.And(*terms) == compiled.conclusion))
                if solver.check() == z3.unsat:
                    found.extend(joint)
    except (CompileError, z3.Z3Exception):
        return []
    finally:
        if timings is not None:
            timings.append(StageTiming(stage=RESTATEMENT_STAGE, ms=(time.perf_counter() - started) * 1000.0))
    return found


def premises_inconsistent(problem: Problem, *, budget_ms: int = RESTATEMENT_RUN_MS) -> bool:
    """Whether the premises of ``problem`` contradict each other, decided by Z3 within ``budget_ms`` (True only on a proof:
    an undecided or failed check is False). The translator asks it before it refuses an encoding as circular: premises that
    contradict each other prove nothing, so the engine's INCONSISTENT_PREMISES (consistency before entailment) is the
    verdict, never a circularity refusal (repair round 2: "they recalled more, and they did not recall more" was refused as
    circular, hiding the contradiction)."""
    if not problem.premises or budget_ms < 1:
        return False
    try:
        compiled = compile_problem(problem)
        solver = z3.Solver(ctx=compiled.ctx)
        solver.set("timeout", int(budget_ms))
        for term in compiled.premises.values():
            solver.add(term)
        return solver.check() == z3.unsat
    except (CompileError, z3.Z3Exception):
        return False


def conclusion_valid_alone(problem: Problem, *, budget_ms: int = RESTATEMENT_RUN_MS) -> bool:
    """Whether the conclusion of ``problem`` holds with no premise at all (its negation is unsatisfiable), decided by Z3
    within ``budget_ms`` (True only on a proof: an undecided or failed check is False). The translator asks it before it
    refuses an encoding as circular (repair round 3, tf_z19): a conclusion that holds whatever the premises say ("prices
    rose or did not rise") is not proved from itself; the engine names it vacuous (``E108``), which is the defect."""
    if problem.query != "entailment" or problem.conclusion is None or budget_ms < 1:
        return False
    try:
        compiled = compile_problem(problem)
        if compiled.conclusion is None:
            return False
        solver = z3.Solver(ctx=compiled.ctx)
        solver.set("timeout", int(budget_ms))
        solver.add(z3.Not(compiled.conclusion))
        return solver.check() == z3.unsat
    except (CompileError, z3.Z3Exception):
        return False


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


def _unasserted_figure_diagnostic(problem: Problem, proc: ProcedureOutcome, config: SolverConfig,
                                  deadline: Optional[float] = None, timings: Optional[list[StageTiming]] = None) -> Optional[Diagnostic]:
    """A COUNTEREXAMPLE that only reassigns figures the problem defines but never asserts: the entailment is re-run with
    each such defined atom asserted and is then ENTAILED.

    A definition is not an assertion, and the question may leave the figure open ("define b iff n = 17; does b
    necessarily hold?"), so by itself this is the advisory ``W110`` and the counterexample stands as the verdict on the
    encoding. It is ``E110`` (unasserted figure: no verdict on the claim, displayed as INVALID_FORMALIZATION) only with
    source-linked evidence that a source asserts the figure: a grounding on one of the reassigned figures or defined
    atoms that a check in this process verified (:func:`source_stated_symbols`). That the re-run is ENTAILED is never
    by itself a reason to add the premise. A re-run that decides against it (a COUNTEREXAMPLE again) leaves the
    counterexample as it is, with no diagnostic; a re-run that decides nothing (skipped, undecided or failed) leaves it so
    only when no source-linked evidence bears on the defined figures, and is otherwise ``E110`` saying the probe did not
    decide (repair round 1, re-run review INV-4).

    The re-run makes two solver calls (consistency, then entailment); each is bounded by ``timeout_ms`` and by half of
    what is left before ``deadline`` (the decision bound, :data:`DECISION_SOLVER_CALLS`), so the probe ends inside it.
    With nothing left the probe is skipped, which decides nothing. Its time is appended to ``timings`` (stage
    :data:`PROBE_FIGURE_STAGE`)."""
    if proc.status is not VerificationStatus.COUNTEREXAMPLE or problem.conclusion is None:
        return None
    defs = unasserted_figure_definitions(problem)
    if not defs:
        return None
    any_stated = source_stated_symbols(problem, [name for d in defs for name in (d.atom, *d.figures)])
    per_call = int(config.timeout_ms) if deadline is None else min(int(config.timeout_ms), _remaining_ms(deadline) // 2)
    if per_call < 1:
        if timings is not None:
            timings.append(StageTiming(stage=PROBE_FIGURE_STAGE + "_skipped", ms=0.0))
        return _undecided_figure(defs, any_stated, "was skipped: the decision bound was spent") if any_stated else None
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
    started = time.perf_counter()
    try:
        again = _PROCEDURES["entailment"](compile_problem(probe), config.model_copy(update={"produce_smt2": False, "produce_unsat_core": True,
                                                                                            "timeout_ms": per_call}))
    except Exception:  # a probe that cannot run decides nothing
        return _undecided_figure(defs, any_stated, "could not run") if any_stated else None
    finally:
        if timings is not None:
            timings.append(StageTiming(stage=PROBE_FIGURE_STAGE, ms=(time.perf_counter() - started) * 1000.0))
    if again.status in (VerificationStatus.TIMEOUT, VerificationStatus.UNKNOWN):
        return _undecided_figure(defs, any_stated, f"was {again.status.value} within its bound") if any_stated else None
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


def _forced_value_diagnostic(problem: Problem, limits: Limits) -> Optional[Diagnostic]:
    """``E307`` when nonlinear terms are allowed and the values the problem's products force could have more digits than
    :data:`~epinoic_logic.engine.policies.MAX_FORCED_VALUE_DIGITS` (:func:`~epinoic_logic.engine.policies.forced_value_digits`):
    neither the timeout nor the ``rlimit`` stops the solver inside nonlinear arithmetic on such values, so the problem is
    refused before it compiles (repair round 4, formal-robustness-1 variant: a chain of squarings of a 40-digit constant held
    one solver call for 37 s under a 2000 ms timeout). Under the linear gate products of unknowns are refused anyway."""
    if not limits.allow_nonlinear:
        return None
    digits, where = forced_value_digits(problem)
    if digits <= MAX_FORCED_VALUE_DIGITS:
        return None
    return Diagnostic(
        code=DiagnosticCode.COEFFICIENTS_TOO_LARGE.value,
        message=(f"the products of the problem force values of up to {digits} digits (a chain of products of fixed values); limit is "
                 f"{MAX_FORCED_VALUE_DIGITS}: the solver cannot be stopped at its timeout inside nonlinear arithmetic on such values"),
        path=where,
    )


def _coefficient_diagnostic(problem: Problem) -> Optional[Diagnostic]:
    """``E307`` when the bound on the digits the problem's exact arithmetic can reach exceeds
    :data:`~epinoic_logic.engine.policies.MAX_COEFFICIENT_DIGITS`: the solver could not be stopped at its timeout inside
    arithmetic on such numbers, so the problem is refused before it compiles (repair round 2)."""
    digits, where = coefficient_digits(problem)
    if digits <= MAX_COEFFICIENT_DIGITS:
        return None
    return Diagnostic(
        code=DiagnosticCode.COEFFICIENTS_TOO_LARGE.value,
        message=(f"the exact arithmetic of the problem can reach numbers of up to {digits} digits (products of literals and chains of "
                 f"them); limit is {MAX_COEFFICIENT_DIGITS}: the solver cannot be stopped at its timeout inside arithmetic on such numbers"),
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


def _severity_cap(cap) -> Optional[tuple[str, str]]:
    """``severity_cap`` as ``(level, reason)``; ``ValueError`` for anything else."""
    if cap is None:
        return None
    if not isinstance(cap, tuple) or len(cap) != 2 or cap[0] not in _named.SEVERITY_RANK or cap[1] not in _named.CAP_REASONS:
        raise ValueError("severity_cap must be (level, reason) with a severity and a cap reason")
    return cap[0], cap[1]


def _diagnose(problem: Problem, proc: ProcedureOutcome, compiled, config: SolverConfig, limits: Limits, diagnostics: list[Diagnostic],
              severity_cap) -> tuple[Optional[list], Optional[str]]:
    """Run the argument stage (module docstring) and return ``(named_diagnostics or None, argument_rules)``.

    The stage runs inside the verification's memory window. Anything it returns is checked against the contract: engine-layer
    named diagnostics only (a diagnostic with no claim is given the problem's claim), merged, with dominated generic
    warnings left out, ordered and bounded (an overflow makes the diagnosis incomplete, so nothing is dropped silently), then
    capped by ``severity_cap``. A stage that raises, or returns anything else, yields ``argdiag-2/incomplete:<reason>`` and no
    diagnostic."""
    try:
        cap = _severity_cap(severity_cap)
    except ValueError:
        return None, _named.incomplete_rules("invalid_severity_cap")
    apply_global_memory_limit(config)
    try:
        found, rules = _argument.diagnose(problem, proc, compiled, config, limits, list(diagnostics))
    except z3.Z3Exception:
        reset_global_memory_limit()
        return None, _named.incomplete_rules("solver_aborted")
    except Exception as exc:  # noqa: BLE001 - a failing rule fires nothing and is recorded, never raised
        return None, _named.incomplete_rules(f"internal_{type(exc).__name__}")
    finally:
        release_global_memory_limit(config)
    if not isinstance(rules, str) or not (rules == ARG_RULES_VERSION or _named.rules_state(rules)[0] == "incomplete"):
        return None, _named.incomplete_rules("unknown_rules")
    items = list(found or [])
    if any(not isinstance(d, _named.NamedDiagnostic) or d.layer != "engine" for d in items):
        return None, _named.incomplete_rules("not_engine_layer")
    items = [d if d.claim_ids else _named.NamedDiagnostic.model_validate({**d.model_dump(mode="python"), "claim_ids": [problem.claim_id]}) for d in items]
    items = _named.ordered(_named.suppress_dominated(_named.merge(items)))
    if len(items) > _named.MAX_PER_CLAIM:
        items, rules = items[:_named.MAX_PER_CLAIM], _named.incomplete_rules(f"overflow_{len(items) - _named.MAX_PER_CLAIM}")
    if cap is not None:
        level, reason = cap
        items = [c for d in items for c in (_named.cap([d], level, reason) if _cap_covers(d, reason) else [d])]
    return (items or None), rules


def _cap_covers(d, reason: str) -> bool:
    spec = _named.code_spec(d.code)
    if spec is None:
        return False
    return spec.capped_on_ambiguous if reason == "ambiguous_translation" else spec.warning_scope != "always"


def verify(
    problem_or_raw: Union[Problem, bytes, str, dict],
    config: SolverConfig = SolverConfig(),
    limits: Limits = DEFAULT_LIMITS,
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
    *,
    diagnose: bool = True,
    severity_cap: Optional[tuple[str, str]] = None,
) -> VerificationResult:
    """Verify a problem (or an untrusted JSON payload) and return a bound result.

    ``diagnose`` runs the argument stage (module docstring; False for internal probes and code-built checks, whose results
    then carry no ``argument_rules`` and are never release-eligible); ``severity_cap`` caps its diagnostics before signing
    (an ambiguous translation's reading). Both are Python keywords only."""
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
        if problem is not None and outcome.ok:
            too_large = _coefficient_diagnostic(problem) or _forced_value_diagnostic(problem, enforced)
            if too_large is not None:
                outcome = ValidationOutcome(ok=False, status=VerificationStatus.INVALID_FORMALIZATION, diagnostics=[too_large],
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
        probe_timings: list[StageTiming] = []
        try:
            # One deadline for the whole decision: the procedure, then the coverage probes on what it left.
            deadline = time.perf_counter() + DECISION_SOLVER_CALLS * int(config.timeout_ms) / 1000.0
            proc = _PROCEDURES[problem.query](compiled, config)
            figure_note = _unasserted_figure_diagnostic(problem, proc, config, deadline, probe_timings)
            # Both shapes are assessed, as the translation layer's coverage notes are: the advisory W110 does not settle
            # whether a source states a free conclusion symbol (E111); only the no-verdict E110 already withholds it.
            if figure_note is None or figure_note.code != DiagnosticCode.UNASSERTED_FIGURE.value:
                reason_note = _unencoded_reason_diagnostic(problem, proc, compiled, config, deadline, probe_timings)
            # A no-verdict code takes precedence: the other shape's advisory says the counterexample stands, which the
            # no-verdict code contradicts, so it is not carried beside it.
            if (reason_note is not None and reason_note.code == DiagnosticCode.UNENCODED_REASON.value
                    and figure_note is not None and figure_note.code == DiagnosticCode.UNASSERTED_FIGURE_ADVISORY.value):
                figure_note = None
            # A relied-on premise of the writer's own that restates the conclusion in other terms (E112 beyond the normal
            # form), decided within what the decision bound left.
            equivalent: list[str] = []
            if proc.status is VerificationStatus.ENTAILED and not circular_premises(problem, list(proc.core) or None):
                equivalent = equivalent_premises(problem, list(proc.core) or None, compiled=compiled,
                                                 budget_ms=min(RESTATEMENT_RUN_MS, _remaining_ms(deadline)), timings=probe_timings)
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
        circular = _circular_diagnostic(problem, proc, equivalent) if vacuous is None else None
        if circular is not None:
            diagnostics.append(circular)
        named_diagnostics, argument_rules = None, None
        stage_timings = list(proc.timings) + probe_timings
        if diagnose:
            t2 = time.perf_counter()
            named_diagnostics, argument_rules = _diagnose(problem, proc, compiled, config, enforced, diagnostics, severity_cap)
            stage_timings.append(StageTiming(stage="diagnose", ms=(time.perf_counter() - t2) * 1000.0))
        result = VerificationResult(
            **base, **ids, status=proc.status,
            binding=compute_binding(problem, config, versions, proc.smt2, record),
            premises_relied_on=relied,
            ungrounded_dependencies=ungrounded_dependencies(problem, relied),
            unverified_dependencies=unverified_dependencies(problem, relied),
            diagnostics=diagnostics,
            timings=stage_timings,
            reason_unknown=proc.reason_unknown,
            named_diagnostics=named_diagnostics,
            argument_rules=argument_rules,
        )
        if proc.status is VerificationStatus.COUNTEREXAMPLE and proc.model is not None:
            result.counterexample = Counterexample(assignments=_assignments(problem, proc.model))
        elif proc.status in (VerificationStatus.CONSISTENT, VerificationStatus.SATISFIABLE) and proc.model is not None:
            result.witness_model = _assignments(problem, proc.model)
        # The raw core record, when asked for, on every status the contract lists: an ENTAILED whose core holds no premise
        # (the vacuous E108 case) carries it too, empty, showing that the negated conclusion alone is unsatisfiable.
        if config.produce_unsat_core and proc.status in (VerificationStatus.INCONSISTENT_PREMISES, VerificationStatus.UNSATISFIABLE, VerificationStatus.ENTAILED):
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
