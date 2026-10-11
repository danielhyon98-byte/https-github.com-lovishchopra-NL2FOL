"""Translation layer: specialist claims -> restricted IR problems -> Overseer outcomes.

Public entry points:

* :class:`Translator` (``pipeline``): eligibility + subject policy + provider +
  strict parsing/validation + grounding -> :class:`TranslationResult`.
* :class:`SemanticReviewer` (``review``): advisory fidelity review.
* :func:`compose_outcome` / :func:`verify_claim` (``outcome``): what the Overseer receives.

Contracts are re-exported from ``contracts``.
"""
from .contracts import (  # noqa: F401
    SuppliedText, ClaimRole, ProposedClaimKind, ClaimRecord, SpecialistReport,
    EligibilityClass, EligibilityDecision, GroundingCheck, AmbiguityFlag, AtomGloss,
    Interpretation, ProviderInfo, TranslationStatus, StructuralFinding, TranslationResult,
    SemanticFidelityReview, ClaimVerificationOutcome,
)
from .outcome import compose_outcome, display_status_for, verify_claim  # noqa: F401
from .pipeline import Translator, apply_subject_policy  # noqa: F401
from .review import SemanticReviewer  # noqa: F401

__all__ = [
    "SuppliedText", "ClaimRole", "ProposedClaimKind", "ClaimRecord", "SpecialistReport",
    "EligibilityClass", "EligibilityDecision", "GroundingCheck", "AmbiguityFlag", "AtomGloss",
    "Interpretation", "ProviderInfo", "TranslationStatus", "StructuralFinding", "TranslationResult",
    "SemanticFidelityReview", "ClaimVerificationOutcome",
    "Translator", "apply_subject_policy", "SemanticReviewer", "compose_outcome", "display_status_for", "verify_claim",
]
