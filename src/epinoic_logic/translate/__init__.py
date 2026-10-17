"""Translation layer: specialist claims -> restricted IR problems -> Overseer outcomes.

Public entry points:

* :class:`Translator` (``pipeline``): eligibility + subject policy + provider +
  strict parsing/validation + grounding -> :class:`TranslationResult`.
* :class:`SemanticReviewer` (``review``): advisory fidelity review.
* :func:`compose_outcome` / :func:`verify_claim` (``outcome``): what the Overseer receives;
  :func:`assess_release` keeps permission to release apart from the formal status, and
  :func:`review_currency` says whether a fidelity review still describes the current inputs.

Contracts are re-exported from ``contracts``, among them :class:`TaskRecord`, the task as the
router issued it (the only source of task authority besides the supplied texts).
"""
from .contracts import (  # noqa: F401
    SuppliedText, ClaimRole, ProposedClaimKind, ClaimRecord, SpecialistReport,
    EligibilityClass, EligibilityDecision, GroundingCheck, AmbiguityFlag, AtomGloss,
    Interpretation, ProviderInfo, TranslationStatus, StructuralFinding, TranslationResult,
    SemanticFidelityReview, ClaimVerificationOutcome,
    TaskRecord, GroundingSupport, FigureReading, RepairRecord, CoverageNote, ReviewBinding, ReleaseAssessment,
)
from .outcome import assess_release, compose_outcome, display_status_for, verify_claim  # noqa: F401
from .pipeline import Translator, apply_subject_policy  # noqa: F401
from .review import SemanticReviewer, review_currency  # noqa: F401

__all__ = [
    "SuppliedText", "ClaimRole", "ProposedClaimKind", "ClaimRecord", "SpecialistReport",
    "EligibilityClass", "EligibilityDecision", "GroundingCheck", "AmbiguityFlag", "AtomGloss",
    "Interpretation", "ProviderInfo", "TranslationStatus", "StructuralFinding", "TranslationResult",
    "SemanticFidelityReview", "ClaimVerificationOutcome",
    "TaskRecord", "GroundingSupport", "FigureReading", "RepairRecord", "CoverageNote", "ReviewBinding", "ReleaseAssessment",
    "Translator", "apply_subject_policy", "SemanticReviewer", "review_currency", "compose_outcome", "display_status_for", "verify_claim",
    "assess_release",
]
