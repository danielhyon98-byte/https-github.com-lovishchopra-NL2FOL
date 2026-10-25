"""The claim and report layers of the argument diagnosis (rules ``argdiag-2``): their two entry points.

* :func:`claim_diagnostics` is called by ``outcome.compose_outcome`` for every outcome, NOT_ELIGIBLE included. It runs
  ``diag_argument.RULES`` and then ``diag_evidence.RULES`` over a frozen :class:`DiagContext` and merges what they name
  with the trusted engine result's own diagnostics (only a result that binds, is current and, when the composer holds the
  key, carries a signature that verifies: anything else contributes nothing).
* :func:`report_diagnostics` is called by the channel once per delivered report. It runs ``diag_argument.REPORT_RULES``
  and then ``diag_evidence.REPORT_RULES`` over a :class:`ReportContext` (the delivered claims and the request, with or
  without outcomes).

Both entry points guard every rule (one that raises, returns something other than named diagnostics of its layer, or
times out is named in the result's ``incomplete`` list and fires nothing), apply the caps where the diagnostic is made
(an ambiguous translation caps the codes it covers at info; a code whose warning scope does not hold is capped at info
with ``not_source_bound``; ``capped_from`` records the severity before the cap, which release still reads), leave out a
generic warning that a more specific one dominates, order the result and keep it within its bound (an overflow is named,
never dropped silently). A diagnostic never changes a display status, a dependency list, a grounding check or a finding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

from ..engine.results import VerificationResult
from ..engine.statuses import VerificationStatus
from ..named import (
    MAX_PER_CLAIM,
    MAX_PER_RECEIPT,
    NamedDiagnostic,
    apply_cap_rule,
    is_blocking,
    merge,
    ordered,
    rules_state,
    suppress_dominated,
)
from . import diag_argument, diag_evidence
from .contracts import ClaimRecord, ClaimVerificationOutcome, PremiseRole, SpecialistReport, TaskRecord, TranslationResult, TranslationStatus
from .roles import premise_roles as _premise_roles

__all__ = ["DiagContext", "ReportContext", "RequestItemView", "Diagnosis", "build_context", "claim_diagnostics", "report_diagnostics",
           "R0_CODES"]

#: The engine codes whose assertion ids are the premises R0 found the proof needs (the writer's links, and the facts).
R0_CODES = ("ARG-LINK-001", "ARG-FACT-001")


@dataclass(frozen=True)
class DiagContext:
    """Everything a claim rule may read. ``verification`` is the trusted engine result or None; ``engine_diagnostics`` and
    ``engine_rules`` come from it. ``needed_premises`` are the premises R0 found the proof needs (the assertion ids of
    ARG-LINK-001 and ARG-FACT-001), or None when R0 named none (a rule then grades the result's core instead).
    ``source_bound`` and ``data_texts`` are the evidence module's readings of the request and the report."""
    claim: ClaimRecord
    translation: TranslationResult
    display: VerificationStatus
    report: Optional[SpecialistReport] = None
    supporting: tuple[ClaimRecord, ...] = ()
    task: Optional[TaskRecord] = None
    verification: Optional[VerificationResult] = None
    premise_roles: tuple[PremiseRole, ...] = ()
    engine_diagnostics: tuple[NamedDiagnostic, ...] = ()
    engine_rules: Optional[str] = None
    needed_premises: Optional[tuple[str, ...]] = None
    source_bound: bool = False
    data_texts: bool = False

    @property
    def task_text(self) -> Optional[str]:
        return self.task.text if self.task is not None else None

    @property
    def ambiguous(self) -> bool:
        return self.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION

    @property
    def core(self) -> tuple[str, ...]:
        """The premises the trusted engine result relied on (empty without one)."""
        return tuple(self.verification.premises_relied_on) if self.verification is not None else ()


@dataclass(frozen=True)
class RequestItemView:
    """One request item as a report rule reads it (the channel's ``RequestItem``, as plain data)."""
    item_id: str
    text: str
    command_term: Optional[str] = None
    level: Optional[int] = None


@dataclass(frozen=True)
class ReportContext:
    """Everything a report rule may read: the delivered report, the task record, the outcomes of its claims (possibly
    none), the request's items and the evidence module's readings of the request and the report."""
    report: SpecialistReport
    task: Optional[TaskRecord] = None
    outcomes: tuple[ClaimVerificationOutcome, ...] = ()
    items: tuple[RequestItemView, ...] = ()
    source_bound: bool = False
    data_texts: bool = False

    @property
    def task_text(self) -> Optional[str]:
        return self.task.text if self.task is not None else None


@dataclass(frozen=True)
class Diagnosis:
    """What a layer named (capped, deduplicated, ordered and bounded) and every rule that did not finish."""
    diagnostics: tuple[NamedDiagnostic, ...] = ()
    incomplete: tuple[str, ...] = field(default_factory=tuple)


def _rule_name(rule: Any) -> str:
    module = getattr(rule, "__module__", None) or ""
    name = getattr(rule, "__qualname__", None) or getattr(rule, "__name__", None) or type(rule).__name__
    return (module.rsplit(".", 1)[-1] + "." if module else "") + str(name)[:80]


def _run(rules: Sequence[Callable[..., Iterable[NamedDiagnostic]]], ctx: Any, layer: str, incomplete: list[str]) -> list[NamedDiagnostic]:
    """Every rule's diagnostics; a rule that raises or returns anything but named diagnostics of ``layer`` fires nothing
    and is named in ``incomplete``."""
    out: list[NamedDiagnostic] = []
    for rule in rules:
        try:
            found = list(rule(ctx) or ())
        except Exception as exc:  # noqa: BLE001 - a failing rule is named, never raised and never read as "none found"
            incomplete.append(f"{_rule_name(rule)}: {type(exc).__name__}")
            continue
        if any(not isinstance(d, NamedDiagnostic) or d.layer != layer for d in found):
            incomplete.append(f"{_rule_name(rule)}: returned something other than {layer}-layer named diagnostics")
            continue
        out.extend(found)
    return out


def _with_claim(diags: Iterable[NamedDiagnostic], claim_id: str) -> list[NamedDiagnostic]:
    return [d if d.claim_ids else NamedDiagnostic.model_validate({**d.model_dump(mode="python"), "claim_ids": [claim_id]}) for d in diags]


def _guarded_reading(fn: Callable[..., bool], arg: Any, what: str, incomplete: list[str]) -> bool:
    try:
        return bool(fn(arg))
    except Exception as exc:  # noqa: BLE001
        incomplete.append(f"diag_evidence.{what}: {type(exc).__name__}")
        return False


def _needed(engine: Sequence[NamedDiagnostic]) -> Optional[tuple[str, ...]]:
    ids = [a for d in engine if d.code in R0_CODES for a in d.assertion_ids]
    return tuple(dict.fromkeys(ids)) if any(d.code in R0_CODES for d in engine) else None


def build_context(claim: ClaimRecord, translation: TranslationResult, display: VerificationStatus, *, verification: Optional[VerificationResult] = None,
                  report: Optional[SpecialistReport] = None, task: Optional[TaskRecord] = None) -> tuple[DiagContext, list[str]]:
    """The :class:`DiagContext` of one claim (``verification`` must already be the TRUSTED result, or None) and the names of
    the readings that failed while it was built."""
    incomplete: list[str] = []
    supporting: tuple[ClaimRecord, ...] = ()
    if report is not None:
        wanted = set(claim.supporting_claim_ids) - {claim.claim_id}
        supporting = tuple(c for c in report.claims if c.claim_id in wanted)
    roles = tuple(translation.premise_roles) or tuple(_premise_roles(translation.problem, translation.grounding_checks))
    engine = tuple(verification.named_diagnostics or ()) if verification is not None else ()
    ctx = DiagContext(
        claim=claim, translation=translation, display=display, report=report, supporting=supporting, task=task, verification=verification,
        premise_roles=roles, engine_diagnostics=engine, engine_rules=verification.argument_rules if verification is not None else None,
        needed_premises=_needed(engine),
        source_bound=_guarded_reading(diag_evidence.source_bound, task.text if task is not None else None, "source_bound", incomplete),
        data_texts=_guarded_reading(diag_evidence.supplies_data_texts, report, "supplies_data_texts", incomplete) if report is not None else False,
    )
    return ctx, incomplete


def _bound(diags: list[NamedDiagnostic], limit: int, incomplete: list[str], where: str) -> list[NamedDiagnostic]:
    """Merged, dominance-suppressed and ordered diagnostics within ``limit``. An overflow keeps the blocking diagnostics
    first (a warning is never cut for an info record of lower precedence: re-run review INV-5), names what it left out,
    and keeps the kept ones in precedence order."""
    items = ordered(suppress_dominated(merge(diags)))
    if len(items) > limit:
        incomplete.append(f"overflow: {len(items) - limit} diagnostic(s) beyond the bound of {limit} per {where} were not kept")
        rank = {id(d): k for k, d in enumerate(items)}
        kept = sorted(items, key=lambda d: (not is_blocking(d), rank[id(d)]))[:limit]
        items = sorted(kept, key=lambda d: rank[id(d)])
    return items


def claim_diagnostics(ctx: DiagContext, incomplete: Sequence[str] = ()) -> Diagnosis:
    """The diagnosis of one claim (module docstring): the trusted engine result's diagnostics merged with the claim layer's."""
    from ..adapters.markdown import quotation_task
    missing: list[str] = list(incomplete)
    state, reason = rules_state(ctx.engine_rules)
    if ctx.verification is not None and state == "incomplete":
        missing.append(f"engine: {reason}")
    # quotation roles in the enclosing task (the channel's plan, or what the caller states); the claim's own task type is
    # advisory and never widens them (repair round 5, INV-QROLE-1)
    with quotation_task(getattr(ctx.claim, "task_type", None), advisory=True):
        found = _run(diag_argument.RULES, ctx, "claim", missing) + _run(diag_evidence.RULES, ctx, "claim", missing)
    found = _with_claim(found, ctx.claim.claim_id)
    if ctx.ambiguous:
        found = apply_cap_rule(found, "ambiguous_translation")
    found = apply_cap_rule(found, "not_source_bound", source_bound=ctx.source_bound, data_texts=ctx.data_texts)
    items = _bound(list(ctx.engine_diagnostics) + found, MAX_PER_CLAIM, missing, "claim")
    return Diagnosis(diagnostics=tuple(items), incomplete=tuple(dict.fromkeys(missing)))


def report_diagnostics(report: SpecialistReport, task: Optional[TaskRecord], outcomes: Iterable[ClaimVerificationOutcome] = (), *,
                       items: Iterable[Any] = ()) -> Diagnosis:
    """The report-level diagnosis of one delivered report (module docstring). ``items`` are the request's items (objects
    with ``item_id``, ``text`` and optionally ``command_term`` and ``level``)."""
    missing: list[str] = []
    views = tuple(RequestItemView(item_id=str(getattr(i, "item_id", "")), text=str(getattr(i, "text", "")), command_term=getattr(i, "command_term", None),
                                  level=getattr(i, "level", None)) for i in items)
    rctx = ReportContext(report=report, task=task, outcomes=tuple(outcomes), items=views,
                         source_bound=_guarded_reading(diag_evidence.source_bound, task.text if task is not None else None, "source_bound", missing),
                         data_texts=_guarded_reading(diag_evidence.supplies_data_texts, report, "supplies_data_texts", missing))
    from ..adapters.markdown import quotation_task
    with quotation_task(getattr(report, "task_type", None), advisory=True):  # the report's own task type is advisory (INV-QROLE-1)
        found = _run(diag_argument.REPORT_RULES, rctx, "report", missing) + _run(diag_evidence.REPORT_RULES, rctx, "report", missing)
    found = apply_cap_rule(found, "not_source_bound", source_bound=rctx.source_bound, data_texts=rctx.data_texts)
    kept = _bound(found, MAX_PER_RECEIPT, missing, "report")
    return Diagnosis(diagnostics=tuple(kept), incomplete=tuple(dict.fromkeys(missing)))
