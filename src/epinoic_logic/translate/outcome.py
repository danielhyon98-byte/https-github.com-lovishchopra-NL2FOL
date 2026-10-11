"""Compose what the Overseer receives for one claim.

``compose_outcome`` derives a ``display_status`` deterministically and writes a
plain-language summary of what was checked, under which assumptions, and what
remains unverified. ``verify_claim`` is the convenience path
translate -> engine -> (review) -> compose.

Display rules (never relaxed):

* ``TRANSLATED``             -> the engine's status, provided the engine result is
  bound to exactly the translated problem; a missing or mis-bound result is
  ``INTERNAL_ERROR``. When the composer holds the signing key, a result whose
  signature does not verify is likewise rejected (``E501``). A definitive status
  that the engine marked vacuous (``E108``: no premise was used) is displayed as
  ``INVALID_FORMALIZATION``, never as a verdict.
* ``AMBIGUOUS_TRANSLATION``  -> ``AMBIGUOUS_TRANSLATION`` (the best-reading problem may
  have been verified for inspection, but an ambiguous claim is never displayed as
  a result).
* ``NOT_ELIGIBLE``           -> ``NOT_ELIGIBLE``
* ``UNSUPPORTED``            -> ``UNSUPPORTED``
* ``INVALID_FORMALIZATION``  -> ``INVALID_FORMALIZATION``
* ``TRANSLATION_FAILED``     -> ``INTERNAL_ERROR``

The summary always ends with the engine's scope statement verbatim.
"""
from __future__ import annotations

from typing import Iterable, Optional

from ..engine.errors import DiagnosticCode
from ..engine.provenance import verify_signature
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify as engine_verify
from ..engine.statuses import DEFINITIVE, SCOPE_STATEMENT, VerificationStatus
from ..ir.canonical import problem_digest
from ..ir.schema import Problem
from .common import new_id, truncate, utc_now_rfc3339
from .contracts import (
    ClaimRecord,
    ClaimVerificationOutcome,
    SemanticFidelityReview,
    SpecialistReport,
    StructuralFinding,
    TranslationResult,
    TranslationStatus,
)
from .pipeline import Translator
from .review import SemanticReviewer

__all__ = ["compose_outcome", "display_status_for", "verify_claim", "STATUS_MEANING", "SUMMARY_MAX_CHARS"]

SUMMARY_MAX_CHARS = 4000
_LABEL_CHARS = 160
_DIAG_CHARS = 300
_MAX_LISTED = 8

STATUS_MEANING: dict[VerificationStatus, str] = {
    VerificationStatus.ENTAILED: (
        "the encoded conclusion follows from the encoded premises (the premises are consistent and no "
        "assignment satisfies them while falsifying the conclusion)"
    ),
    VerificationStatus.COUNTEREXAMPLE: (
        "the encoded conclusion does not follow from the encoded premises: an assignment satisfies every "
        "premise and falsifies the conclusion"
    ),
    VerificationStatus.INCONSISTENT_PREMISES: "the encoded premises contradict each other, so the conclusion was not tested",
    VerificationStatus.CONSISTENT: "the encoded statements can all hold together",
    VerificationStatus.SATISFIABLE: "the encoded statements can be satisfied together",
    VerificationStatus.UNSATISFIABLE: "the encoded statements cannot all hold together",
    VerificationStatus.UNKNOWN: "the solver could not decide the encoded problem; nothing was verified",
    VerificationStatus.TIMEOUT: "the solver stopped at its resource bound; nothing was verified",
    VerificationStatus.UNSUPPORTED: "the claim or its encoding needs constructs outside the supported formal language; nothing was verified",
    VerificationStatus.INVALID_FORMALIZATION: "no valid formal encoding of the claim was obtained; nothing was verified",
    VerificationStatus.AMBIGUOUS_TRANSLATION: "the claim admits materially different readings; nothing is verified until a reading is fixed",
    VerificationStatus.NOT_ELIGIBLE: "the claim is not a solver question under policy; it is routed to another check and nothing was verified",
    VerificationStatus.INTERNAL_ERROR: "the verification layer failed; nothing was verified",
}

_TRANSLATION_DISPLAY: dict[TranslationStatus, VerificationStatus] = {
    TranslationStatus.AMBIGUOUS_TRANSLATION: VerificationStatus.AMBIGUOUS_TRANSLATION,
    TranslationStatus.NOT_ELIGIBLE: VerificationStatus.NOT_ELIGIBLE,
    TranslationStatus.UNSUPPORTED: VerificationStatus.UNSUPPORTED,
    TranslationStatus.INVALID_FORMALIZATION: VerificationStatus.INVALID_FORMALIZATION,
    TranslationStatus.TRANSLATION_FAILED: VerificationStatus.INTERNAL_ERROR,
}


def _binding_problem(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> Optional[str]:
    """Why ``verification`` cannot be trusted for ``translation``; ``None`` when it binds.

    With ``signing_key`` the result must also carry a signature that verifies under
    that key (and, when ``key_id`` is given, name that key); a result whose status or
    content was altered after signing is rejected here rather than displayed.
    """
    if verification is None:
        return "no engine result was produced for the translated problem"
    problem = translation.problem
    if problem is None:
        return "an engine result was supplied but the translation carries no problem"
    if verification.claim_id != translation.claim_id or verification.request_id != translation.request_id:
        return "the engine result is for a different claim"
    if verification.problem_id != problem.problem_id or verification.binding.problem_digest != problem_digest(problem):
        return "the engine result is not bound to the translated problem (digest mismatch)"
    if signing_key is not None:
        if not verification.signature:
            return f"the engine result is unsigned although a signing key is configured ({DiagnosticCode.SIGNATURE_INVALID.value})"
        if key_id is not None and verification.signature_key_id != key_id:
            return f"the engine result is signed with an unexpected key id ({DiagnosticCode.SIGNATURE_INVALID.value})"
        if not verify_signature(verification, signing_key):
            return f"the engine result's signature does not verify ({DiagnosticCode.SIGNATURE_INVALID.value})"
    return None


def _is_vacuous(verification: VerificationResult) -> bool:
    return verification.status in DEFINITIVE and any(d.code == DiagnosticCode.VACUOUS_RESULT.value for d in verification.diagnostics)


def display_status_for(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> VerificationStatus:
    """Deterministic display status for a translation plus optional engine result."""
    if translation.status is TranslationStatus.TRANSLATED:
        if _binding_problem(translation, verification, signing_key, key_id) is not None:
            return VerificationStatus.INTERNAL_ERROR
        assert verification is not None
        if _is_vacuous(verification):
            return VerificationStatus.INVALID_FORMALIZATION
        return verification.status
    return _TRANSLATION_DISPLAY[translation.status]


# ----------------------------------------------------------------- summary text


def _label(problem: Problem, assertion_id: str) -> str:
    for p in problem.premises:
        if p.id == assertion_id:
            return truncate(p.label or "(no label)", _LABEL_CHARS)
    if problem.conclusion is not None and problem.conclusion.id == assertion_id:
        return truncate(problem.conclusion.label or "(no label)", _LABEL_CHARS)
    return "(not in problem)"


def _grounding_note(problem: Problem, assertion_id: str) -> str:
    for p in problem.premises:
        if p.id == assertion_id:
            g = p.grounding
            if g is None:
                return "no grounding"
            note = f"{g.kind}, {g.certainty}"
            if g.verified is False:
                note += "; grounding check failed"
            return note
    return "not in problem"


def _listed(items: list[str]) -> str:
    shown = items[:_MAX_LISTED]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def _eligibility_lines(translation: TranslationResult) -> list[str]:
    e = translation.eligibility
    state = "eligible for the formal check" if e.eligible else f"not eligible; routed to {e.route_to or 'unresolved'}"
    reasons = _listed([truncate(r, _DIAG_CHARS) for r in e.reasons]) if e.reasons else "none recorded"
    return [f"Eligibility ({e.policy_version}): {e.eligibility_class.value}, {state}. Reasons: {reasons}."]


def _checked_lines(translation: TranslationResult) -> list[str]:
    problem = translation.problem
    if problem is None:
        return ["Checked: nothing was submitted to the solver."]
    text = (
        f"Checked: {problem.query} query over {len(problem.symbols)} symbol(s) and {len(problem.premises)} premise(s)"
    )
    if problem.conclusion is not None:
        text += f"; conclusion '{problem.conclusion.id}': {truncate(problem.conclusion.label or '(no label)', _LABEL_CHARS)}"
    return [text + "."]


def _verification_lines(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> list[str]:
    lines: list[str] = []
    problem = translation.problem
    if verification is None or problem is None:
        return lines
    binding_issue = _binding_problem(translation, verification, signing_key, key_id)
    if binding_issue is not None:
        lines.append(f"Engine result rejected: {binding_issue}.")
        return lines
    if translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION:
        lines.append(
            f"The best-reading encoding was run for inspection and returned {verification.status.value}; "
            "because the claim is ambiguous this is not displayed as a result."
        )
    if _is_vacuous(verification):
        vacuous = next(d for d in verification.diagnostics if d.code == DiagnosticCode.VACUOUS_RESULT.value)
        lines.append(
            f"Vacuous result: the engine returned {verification.status.value} but {truncate(vacuous.message, _DIAG_CHARS)} "
            f"({vacuous.code}); it is displayed as INVALID_FORMALIZATION, not as a verdict."
        )
    if verification.premises_relied_on:
        lines.append("Premises relied on: " + _listed([f"{pid} ({_label(problem, pid)})" for pid in verification.premises_relied_on]) + ".")
    elif verification.status in DEFINITIVE:
        lines.append("Premises relied on: none recorded.")
    if verification.ungrounded_dependencies:
        lines.append(
            "Ungrounded dependencies (relied on but not established by the supplied material): "
            + _listed([f"{pid} ({_grounding_note(problem, pid)})" for pid in verification.ungrounded_dependencies])
            + "."
        )
    if verification.unverified_dependencies:
        lines.append(
            "Unverified dependencies (asserted by the translation, checked by no procedure): "
            + _listed([f"{pid} ({_grounding_note(problem, pid)})" for pid in verification.unverified_dependencies])
            + "."
        )
    if verification.premises_relied_on and not verification.ungrounded_dependencies and not verification.unverified_dependencies:
        lines.append("Ungrounded dependencies: none; unverified dependencies: none.")
    if verification.counterexample is not None:
        lines.append("Counterexample: " + _listed([f"{a.symbol}={a.value}" for a in verification.counterexample.assignments]) + ".")
    if verification.witness_model:
        lines.append("Witness assignment: " + _listed([f"{a.symbol}={a.value}" for a in verification.witness_model]) + ".")
    if verification.status not in DEFINITIVE and verification.diagnostics:
        lines.append("Engine diagnostics: " + _listed([f"{d.code}: {truncate(d.message, _DIAG_CHARS)}" for d in verification.diagnostics]) + ".")
    if verification.signature and signing_key is not None:
        lines.append(f"Engine result {verification.result_id} is signed (key {verification.signature_key_id}) and its signature was verified by this layer.")
    elif verification.signature:
        lines.append(
            f"Engine result {verification.result_id} carries a signature (key {verification.signature_key_id}) that this layer did not verify; "
            "the Overseer must verify it before relying on the result."
        )
    else:
        lines.append(f"Engine result {verification.result_id} is unsigned.")
    return lines


def _grounding_lines(translation: TranslationResult) -> list[str]:
    failed = [c for c in translation.grounding_checks if c.verified is False]
    if not failed:
        return []
    return ["Failed grounding checks: " + _listed([f"{c.target_id}: {truncate(c.detail or c.method, _DIAG_CHARS)}" for c in failed]) + "."]


def _ambiguity_lines(translation: TranslationResult) -> list[str]:
    if translation.status is not TranslationStatus.AMBIGUOUS_TRANSLATION or translation.interpretation is None:
        return []
    flags = translation.interpretation.ambiguity_flags
    if not flags:
        return ["Ambiguity: the provider marked the claim ambiguous without listing specific flags."]
    return ["Ambiguity: " + _listed([
        f"{f.code}: {truncate(f.message, _DIAG_CHARS)}" + (f" (alternatives: {' | '.join(truncate(a, 80) for a in f.alternatives)})" if f.alternatives else "")
        for f in flags
    ]) + "."]


def _translation_diagnostic_lines(translation: TranslationResult) -> list[str]:
    if translation.status in (TranslationStatus.TRANSLATED, TranslationStatus.AMBIGUOUS_TRANSLATION, TranslationStatus.NOT_ELIGIBLE):
        return []
    if not translation.diagnostics:
        return []
    return ["Translation diagnostics: " + _listed([truncate(d, _DIAG_CHARS) for d in translation.diagnostics]) + "."]


def _structural_lines(structural: list[StructuralFinding]) -> list[str]:
    errors = [f for f in structural if f.severity == "error"]
    warnings = [f for f in structural if f.severity == "warning"]
    infos = [f for f in structural if f.severity == "info"]
    text = f"Structural findings (deterministic, not solver results): {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} informational."
    if errors:
        text += " Errors: " + _listed([f"{f.code}: {truncate(f.message, _DIAG_CHARS)}" for f in errors]) + "."
    return [text]


def _review_lines(review: Optional[SemanticFidelityReview]) -> list[str]:
    if review is None:
        return []
    text = f"Advisory semantic-fidelity review: {review.verdict} (advisory only; not a verification)."
    if review.issues:
        text += " Issues: " + _listed([truncate(i, _DIAG_CHARS) for i in review.issues]) + "."
    return [text]


def _fit(body: str, tail: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """Join ``body`` and ``tail`` within ``limit`` characters, cutting the body, never the tail."""
    sep = "\n"
    if len(body) + len(sep) + len(tail) <= limit:
        return body + sep + tail
    room = limit - len(sep) - len(tail)
    marker = " [summary truncated]"
    if room <= len(marker):
        return tail[:limit]
    return body[: room - len(marker)].rstrip() + marker + sep + tail


def build_summary(
    claim: ClaimRecord,
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    review: Optional[SemanticFidelityReview],
    structural: list[StructuralFinding],
    display: VerificationStatus,
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> str:
    """Deterministic plain-language summary; ends with ``SCOPE_STATEMENT`` verbatim."""
    lines: list[str] = [
        f"Claim {claim.claim_id} (role {claim.claim_role}, subject {claim.subject}): "
        f"translation {translation.status.value}; display status {display.value}.",
        f"Status meaning: {STATUS_MEANING[display]}.",
    ]
    lines += _eligibility_lines(translation)
    lines += _checked_lines(translation)
    lines += _verification_lines(translation, verification, signing_key, key_id)
    if translation.status is TranslationStatus.TRANSLATED and verification is None:
        lines.append("Engine result rejected: no engine result was produced for the translated problem.")
    lines += _grounding_lines(translation)
    lines += _ambiguity_lines(translation)
    lines += _translation_diagnostic_lines(translation)
    lines += _structural_lines(structural)
    lines += _review_lines(review)
    return _fit("\n".join(lines), SCOPE_STATEMENT)


# -------------------------------------------------------------------- compose


def compose_outcome(
    claim: ClaimRecord,
    translation: TranslationResult,
    verification: Optional[VerificationResult] = None,
    review: Optional[SemanticFidelityReview] = None,
    structural: Iterable[StructuralFinding] = (),
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> ClaimVerificationOutcome:
    """Assemble the Overseer-facing outcome for one claim.

    ``verification`` is used only when it binds to the translated problem (same
    claim, same problem id and digest) and, when ``signing_key`` is given, carries a
    signature that verifies under it; anything else is displayed as
    ``INTERNAL_ERROR`` and explained in the summary. Agent self-reports play no part.
    """
    if translation.claim_id != claim.claim_id or translation.request_id != claim.request_id:
        raise ValueError("translation does not belong to the claim")
    if review is not None and review.translation_id != translation.translation_id:
        raise ValueError("review does not belong to the translation")
    findings = list(structural)
    display = display_status_for(translation, verification, signing_key, key_id)
    summary = build_summary(claim, translation, verification, review, findings, display, signing_key, key_id)
    return ClaimVerificationOutcome(
        outcome_id=new_id("oc"),
        request_id=claim.request_id,
        report_id=claim.report_id,
        claim_id=claim.claim_id,
        translation=translation,
        verification=verification,
        semantic_review=review,
        structural_findings=findings,
        display_status=display,
        summary=summary,
        created_at=utc_now_rfc3339(),
    )


def verify_claim(
    claim: ClaimRecord,
    report: SpecialistReport,
    translator: Translator,
    reviewer: Optional[SemanticReviewer] = None,
    structural: Iterable[StructuralFinding] = (),
    config: SolverConfig = SolverConfig(),
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> ClaimVerificationOutcome:
    """Translate, verify with the engine, optionally review, and compose the outcome.

    The engine runs only for ``TRANSLATED`` and ``AMBIGUOUS_TRANSLATION`` results
    that carry a problem. For an ambiguous claim the best-reading problem is still
    verified so reviewers can inspect it, but the display status stays
    ``AMBIGUOUS_TRANSLATION``. The reviewer, when given, runs whenever a problem exists.
    """
    translation = translator.translate(claim, report)
    verification: Optional[VerificationResult] = None
    if translation.problem is not None and translation.status in (
        TranslationStatus.TRANSLATED,
        TranslationStatus.AMBIGUOUS_TRANSLATION,
    ):
        verification = engine_verify(translation.problem, config, signing_key=signing_key, key_id=key_id)
    review: Optional[SemanticFidelityReview] = None
    if reviewer is not None and translation.problem is not None:
        review = reviewer.review(claim, translation)
    return compose_outcome(claim, translation, verification, review, structural, signing_key=signing_key, key_id=key_id)
