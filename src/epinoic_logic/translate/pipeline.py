"""Translation pipeline: one specialist claim -> one ``TranslationResult``.

Order of operations (each step is deterministic code except the provider call):

1. **Eligibility** (``eligibility.decide_eligibility``): policy decides whether the
   claim is a solver question at all. The agent's self-report is ignored.
2. **Subject policy** (``subjects``): the IB subject profile may narrow the
   decision further. A class the profile does not allow (for example a
   QUANTITATIVE_CLAIM in a literature course) is downgraded to
   ``NOT_ELIGIBLE_OTHER`` with the reason recorded. An ineligible claim never
   reaches a provider.
3. **Provider** (``providers``): the model proposes a formalization as JSON text.
   The text is untrusted data. It is parsed with a strict JSON parser, validated
   against the IR schema, checked by the engine validator (identifiers, sorts,
   policy allowlist, limits), and its ``request_id``/``claim_id`` must match the
   claim. Schema and validity failures are fed back once as ``prior_diagnostics``;
   policy (``UNSUPPORTED``) and identity failures are not retried.
4. **Grounding** (``grounding``): quotation groundings are checked verbatim against
   the supplied texts and ``verified`` is set by code only.
4b. **Stated figures** (``engine.runner.unasserted_figure_definitions``): a premise that
   only defines an atom by a comparison of a figure no other premise mentions
   (``b <-> (n = 17)`` with ``n`` free) asserts nothing. When the conclusion fails only
   because of such a figure (the engine's COUNTEREXAMPLE turns ENTAILED once the defined
   atoms are asserted: ``E110``), the output is INVALID_FORMALIZATION with that diagnostic
   (fed back once); otherwise the unasserted definitions are recorded as a note.
5. **Status**: ``TRANSLATED``, or ``AMBIGUOUS_TRANSLATION`` when the provider
   flagged ambiguity, ``UNSUPPORTED`` when it declined or the validator rejected a
   construct by policy, ``INVALID_FORMALIZATION`` when no valid encoding was
   obtained, ``TRANSLATION_FAILED`` when the provider failed, ``NOT_ELIGIBLE``
   from steps 1 and 2.

Nothing in this module evaluates model output; the problem is data all the way
to the engine. Logs carry identifiers and statuses only, never claim or student text.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from pydantic import ValidationError

from ..engine.errors import DiagnosticCode
from ..engine.results import SolverConfig
from ..engine.runner import unasserted_figure_definitions, verify as engine_verify
from ..engine.statuses import VerificationStatus
from ..engine.validator import validate_problem
from ..ir.schema import DEFAULT_LIMITS, Limits, Problem
from ..version import IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION
from . import prompts, subjects
from .common import new_id, truncate, utc_now_rfc3339
from .contracts import (
    ClaimRecord,
    EligibilityClass,
    EligibilityDecision,
    GroundingCheck,
    Interpretation,
    ProviderInfo,
    SpecialistReport,
    TranslationResult,
    TranslationStatus,
    sha256_text,
)
from .eligibility import decide_eligibility
from .grounding import check_problem_grounding
from .parsing import ProviderOutputError, parse_json_object
from .providers.base import ProviderError, TranslationProvider, TranslationRequest
from .subjects import SubjectProfile

__all__ = ["Translator", "apply_subject_policy", "REQUIRED_OUTPUT_KEYS"]

logger = logging.getLogger(__name__)

REQUIRED_OUTPUT_KEYS: tuple[str, ...] = ("problem", "interpretation", "ambiguous", "unsupported_reason")
_MAX_DIAGNOSTIC_CHARS = 500
_MAX_SCHEMA_ERRORS = 12


def apply_subject_policy(eligibility: EligibilityDecision, profile: SubjectProfile) -> EligibilityDecision:
    """Narrow an eligibility decision by the subject profile.

    An eligible class the profile does not allow becomes ``NOT_ELIGIBLE_OTHER``
    (not eligible, routed per :func:`subjects.route_for`) with the original reasons
    kept and the downgrade reason appended. Everything else is returned unchanged.
    """
    if not eligibility.eligible or profile.allows(eligibility.eligibility_class):
        return eligibility
    downgraded = EligibilityClass.NOT_ELIGIBLE_OTHER
    return EligibilityDecision(
        eligibility_class=downgraded,
        eligible=False,
        decided_by="deterministic",
        reasons=[
            *eligibility.reasons,
            f"class {eligibility.eligibility_class.value} not allowed for subject profile {profile.key}",
        ],
        route_to=subjects.route_for(downgraded),
        policy_version=eligibility.policy_version,
    )


class _Rejected(Exception):
    """Internal: an attempt produced output the pipeline cannot accept."""

    def __init__(self, status: TranslationStatus, diagnostics: list[str], retryable: bool) -> None:
        super().__init__(diagnostics[0] if diagnostics else status.value)
        self.status = status
        self.diagnostics = diagnostics
        self.retryable = retryable


@dataclass
class _Accepted:
    status: TranslationStatus
    problem: Problem
    interpretation: Interpretation
    grounding_checks: list[GroundingCheck]
    notes: list[str] = field(default_factory=list)


def _format_validation_error(exc: ValidationError, what: str) -> str:
    lines = []
    for err in exc.errors()[:_MAX_SCHEMA_ERRORS]:
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = str(err.get("msg", "invalid"))
        lines.append(f"{loc or '<root>'}: {msg}")
    more = exc.error_count() - len(lines)
    text = f"{what} does not match the schema: " + "; ".join(lines)
    if more > 0:
        text += f"; and {more} more"
    return truncate(text, _MAX_DIAGNOSTIC_CHARS * 2)


class Translator:
    """Turns one claim of a specialist report into a :class:`TranslationResult`.

    ``provider`` is any :class:`~epinoic_logic.translate.providers.base.TranslationProvider`.
    ``max_attempts`` bounds provider calls per claim (default 2: one retry with the
    previous attempt's diagnostics). ``limits`` are the IR shape limits enforced by
    the engine validator before anything is accepted. ``config`` bounds the solver run
    that decides whether a conclusion fails only on a figure the problem defines but
    never asserts (run only when such a definition is present).
    """

    def __init__(
        self,
        provider: TranslationProvider,
        policy_version: str = POLICY_VERSION,
        max_attempts: int = 2,
        prompt_version: str = prompts.TRANSLATE_PROMPT_VERSION,
        limits: Limits = DEFAULT_LIMITS,
        config: SolverConfig = SolverConfig(),
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.provider = provider
        self.policy_version = policy_version
        self.max_attempts = max_attempts
        self.prompt_version = prompt_version
        self.limits = limits
        self.config = config

    # ------------------------------------------------------------------ public

    def translate(self, claim: ClaimRecord, report: SpecialistReport) -> TranslationResult:
        """Translate ``claim`` (which must belong to ``report``) into a bound result.

        Never raises for provider or model-output problems; those become statuses.
        """
        if claim.report_id != report.report_id or claim.request_id != report.request_id:
            raise ValueError("claim does not belong to the report")
        profile = subjects.resolve_profile(claim.subject)
        eligibility = apply_subject_policy(decide_eligibility(claim, self.policy_version), profile)
        if not eligibility.eligible:
            result = self._result(claim, TranslationStatus.NOT_ELIGIBLE, eligibility, diagnostics=list(eligibility.reasons))
            self._log(result, attempts=0)
            return result

        supporting_ids = set(claim.supporting_claim_ids) - {claim.claim_id}  # a claim never supports itself
        base = dict(
            claim=claim,
            supporting_claims=[c for c in report.claims if c.claim_id in supporting_ids],
            supplied_texts=list(report.supplied_texts),
            eligibility=eligibility,
            prompt_version=self.prompt_version,
            ir_version=IR_VERSION,
            subject_profile_text=subjects.prompt_profile_text(profile),
        )

        prior: list[str] = []
        collected: list[str] = []
        attempts = 0
        while attempts < self.max_attempts:
            attempts += 1
            request = TranslationRequest(**base, prior_diagnostics=list(prior))
            try:
                response = self.provider.propose(request)
            except ProviderError as exc:
                info = ProviderInfo(provider_name=self.provider.name, prompt_version=self.prompt_version, attempts=attempts)
                collected.append(f"attempt {attempts}: provider error: {truncate(str(exc), _MAX_DIAGNOSTIC_CHARS)}")
                result = self._result(claim, TranslationStatus.TRANSLATION_FAILED, eligibility, provider=info, diagnostics=collected)
                self._log(result, attempts=attempts)
                return result
            info = response.info.model_copy(update={"attempts": attempts})
            try:
                accepted = self._process(response.raw_text, claim, report, profile, attempts)
            except _Rejected as rejected:
                collected.extend(rejected.diagnostics)
                if rejected.retryable and attempts < self.max_attempts:
                    prior = list(rejected.diagnostics)
                    continue
                result = self._result(claim, rejected.status, eligibility, provider=info, diagnostics=collected)
                self._log(result, attempts=attempts)
                return result
            result = self._result(
                claim,
                accepted.status,
                eligibility,
                problem=accepted.problem,
                interpretation=accepted.interpretation,
                grounding_checks=accepted.grounding_checks,
                provider=info,
                diagnostics=collected + accepted.notes,
            )
            self._log(result, attempts=attempts)
            return result
        raise AssertionError("unreachable: attempt loop exited without a result")  # pragma: no cover

    # ----------------------------------------------------------------- private

    def _process(
        self,
        raw_text: str,
        claim: ClaimRecord,
        report: SpecialistReport,
        profile: SubjectProfile,
        attempt: int,
    ) -> _Accepted:
        """Parse, validate, policy-check and ground one provider output."""
        tag = f"attempt {attempt}"
        try:
            obj = parse_json_object(raw_text)
        except ProviderOutputError as exc:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {exc}"], retryable=True) from None

        missing = [k for k in REQUIRED_OUTPUT_KEYS if k not in obj]
        if missing:
            raise _Rejected(
                TranslationStatus.INVALID_FORMALIZATION,
                [f"{tag}: output is missing required key(s): {', '.join(missing)}"],
                retryable=True,
            )

        raw_problem = obj["problem"]
        if raw_problem is None:
            reason = obj.get("unsupported_reason")
            text = reason.strip() if isinstance(reason, str) and reason.strip() else "no unsupported_reason was given"
            raise _Rejected(
                TranslationStatus.UNSUPPORTED,
                [f"{tag}: provider declined to encode the claim: {truncate(text, _MAX_DIAGNOSTIC_CHARS)}"],
                retryable=False,
            )
        if not isinstance(raw_problem, dict):
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: problem must be a JSON object or null"], retryable=True)
        try:
            problem = Problem.model_validate(raw_problem)
        except ValidationError as exc:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {_format_validation_error(exc, 'problem')}"], retryable=True) from None
        except RecursionError:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: problem nesting is too deep to validate"], retryable=False) from None

        if problem.request_id != claim.request_id or problem.claim_id != claim.claim_id:
            raise _Rejected(
                TranslationStatus.INVALID_FORMALIZATION,
                [f"{tag}: problem request_id/claim_id do not match the claim being translated"],
                retryable=False,
            )

        outcome = validate_problem(problem, self.limits)
        if not outcome.ok:
            diagnostics = [
                f"{tag}: {d.code}: {truncate(d.message, _MAX_DIAGNOSTIC_CHARS)}" + (f" at {d.path}" if d.path else "")
                for d in outcome.diagnostics
            ]
            if outcome.status is VerificationStatus.UNSUPPORTED:
                raise _Rejected(TranslationStatus.UNSUPPORTED, diagnostics, retryable=False)
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, diagnostics, retryable=True)

        disallowed = sorted({s.sort for s in problem.symbols if s.sort != "Bool" and s.sort not in profile.numeric_sorts})
        if disallowed:
            raise _Rejected(
                TranslationStatus.INVALID_FORMALIZATION,
                [f"{tag}: sort(s) {', '.join(disallowed)} are not permitted by subject profile {profile.key}; use Bool"
                 + (f" or {', '.join(sorted(profile.numeric_sorts))}" if profile.numeric_sorts else "")],
                retryable=True,
            )

        grounded, checks = check_problem_grounding(problem, report.supplied_texts)

        try:
            interpretation = Interpretation.model_validate(obj["interpretation"])
        except ValidationError as exc:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {_format_validation_error(exc, 'interpretation')}"], retryable=True) from None
        except RecursionError:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: interpretation nesting is too deep to validate"], retryable=False) from None

        ambiguous = obj["ambiguous"]
        if not isinstance(ambiguous, bool):
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: ambiguous must be a JSON boolean"], retryable=True)

        notes: list[str] = []
        failed = [c for c in checks if c.verified is False]
        if failed:
            notes.append(
                f"{len(failed)} grounding check(s) failed: " + ", ".join(sorted({c.target_id for c in failed}))
            )
        notes += self._stated_figures(grounded, tag)
        status = TranslationStatus.AMBIGUOUS_TRANSLATION if (ambiguous or interpretation.ambiguity_flags) else TranslationStatus.TRANSLATED
        if ambiguous and not interpretation.ambiguity_flags:
            notes.append("provider marked the claim ambiguous without listing ambiguity flags")
        return _Accepted(status=status, problem=grounded, interpretation=interpretation, grounding_checks=checks, notes=notes)

    def _stated_figures(self, problem: Problem, tag: str) -> list[str]:
        """A premise that only defines an atom by a comparison of a figure no other premise mentions asserts nothing.
        When the conclusion fails only on such a figure (the engine's ``E110``: COUNTEREXAMPLE as encoded, ENTAILED once
        the defined atoms are asserted), the output is rejected as INVALID_FORMALIZATION with the diagnostic, which is
        fed back once, so a counterexample that merely sets the stated figure to another value is never a verdict
        (ambiguous or not). Otherwise each unasserted definition is recorded as a note: the verdict does not rest on it."""
        defs = unasserted_figure_definitions(problem)
        if not defs:
            return []
        if problem.query == "entailment" and problem.conclusion is not None:
            probe = engine_verify(problem, self.config)
            diag = next((d for d in probe.diagnostics if d.code == DiagnosticCode.UNASSERTED_FIGURE.value), None)
            if diag is not None:
                raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {diag.code}: {truncate(diag.message, _MAX_DIAGNOSTIC_CHARS * 3)}" + (f" at {diag.path}" if diag.path else "")], retryable=True)
        named = ", ".join(f"{d.premise_id} ({d.atom} over {', '.join(d.figures)})" for d in defs[:8]) + (f" and {len(defs) - 8} more" if len(defs) > 8 else "")
        return [truncate(f"unasserted figure definition(s): premise(s) {named} define an atom by a figure that no premise asserts or constrains, "
                         "so the figure their labels state is not encoded as stated; the engine verdict does not rest on them", _MAX_DIAGNOSTIC_CHARS * 2)]

    def _result(
        self,
        claim: ClaimRecord,
        status: TranslationStatus,
        eligibility: EligibilityDecision,
        *,
        problem: Optional[Problem] = None,
        interpretation: Optional[Interpretation] = None,
        grounding_checks: Optional[list[GroundingCheck]] = None,
        provider: Optional[ProviderInfo] = None,
        diagnostics: Optional[list[str]] = None,
    ) -> TranslationResult:
        return TranslationResult(
            translation_id=new_id("tr"),
            claim_id=claim.claim_id,
            request_id=claim.request_id,
            report_id=claim.report_id,
            status=status,
            eligibility=eligibility,
            claim_text_sha256=sha256_text(claim.claim_text),
            problem=problem,
            interpretation=interpretation,
            grounding_checks=list(grounding_checks or []),
            provider=provider,
            translator_version=TRANSLATOR_VERSION,
            policy_version=self.policy_version,
            diagnostics=list(diagnostics or []),
            created_at=utc_now_rfc3339(),
        )

    @staticmethod
    def _log(result: TranslationResult, *, attempts: int) -> None:
        # Identifiers and statuses only: never claim text, excerpts or diagnostics.
        logger.info(
            "translation %s claim=%s status=%s class=%s attempts=%d",
            result.translation_id,
            result.claim_id,
            result.status.value,
            result.eligibility.eligibility_class.value,
            attempts,
        )
