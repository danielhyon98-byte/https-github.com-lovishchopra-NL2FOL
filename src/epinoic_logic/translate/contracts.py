"""Versioned contracts between subject-specialist agents, the translator, the
verification engine and the Overseer.

Principles (Epinoic AI architecture, sections 4, 5 and 11 of the context document):
- The ORIGINAL specialist response is immutable; its hash is carried everywhere.
- Claims have stable ids. A materially changed claim is a NEW claim record linked to
  its source, never a rewrite under the same id.
- Agent-supplied confidence, eligibility and verification status are ADVISORY. They
  are recorded for audit and never trusted. The Overseer takes status only from
  signed engine results.
- Three correctness dimensions are kept separate: structural (deterministic code),
  semantic fidelity (advisory review), formal validity (engine).
"""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..engine.results import VerificationResult
from ..engine.statuses import VerificationStatus
from ..ir.schema import Certainty, Grounding, GroundingKind, Problem, SourceRef

ClaimRole = Literal[
    # shared
    "thesis", "point", "evidence", "link", "structural", "quantitative", "other",
    # English (Device -> Interpretation -> Effect)
    "device", "interpretation", "effect",
    # History and other argued subjects (Claim -> Evidence -> Analysis -> Judgement -> Link)
    "analysis", "judgement", "counter_evidence", "perspective",
    # source operation (Origin, Purpose, Content -> Value, Limitation)
    "origin", "purpose", "content", "value", "limitation",
]
ProposedClaimKind = Literal[
    "formal_logic", "arithmetic", "factual", "interpretive", "rubric_judgment", "unknown",
]
LocatorScheme = Literal["none", "line", "paragraph", "page", "act_scene_line", "custom"]


class SuppliedText(BaseModel):
    """A text supplied with the task (an extract, poem, passage). Untrusted input."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=500)
    author: Optional[str] = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=400_000)
    locator_scheme: LocatorScheme = Field(
        default="none",
        description=(
            "how locations in this text may be cited; callers opt in to a scheme. The default 'none' means no "
            "page, line or act citation can be checked against this text, so citations are reported as unverifiable"
        ),
    )
    provenance: Optional[str] = Field(default=None, max_length=1000, description="where the text came from; e.g. 'supplied by student'")


class ClaimRecord(BaseModel):
    """One claim extracted from a specialist report. Input to the translator."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    report_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    agent_version: Optional[str] = Field(default=None, max_length=64)
    subject: str = Field(min_length=1, max_length=128, description="e.g. 'English A: Language and Literature'")
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128, description="e.g. 'analytical_paragraph', 'essay', 'outline'")
    claim_id: str = Field(min_length=1, max_length=128)
    claim_text: str = Field(min_length=1, max_length=4000)
    claim_role: ClaimRole = "other"
    proposed_claim_kind: ProposedClaimKind = Field(default="unknown", description="agent-proposed; advisory")
    materiality: Literal["material", "supporting"] = "material"
    certainty: Certainty = Field(default="established", description="agent-stated certainty; advisory")
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=32)
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    assessment_criteria: list[str] = Field(default_factory=list, max_length=32)
    supporting_claim_ids: list[str] = Field(default_factory=list, max_length=512, description="a paragraph's point legitimately supports every claim in it, so the bound equals the report's claim limit")
    parent_claim_id: Optional[str] = Field(default=None, max_length=128)
    advisory_verification_eligibility: Optional[bool] = Field(default=None, description="agent self-report; never trusted")
    advisory_verification_status: Optional[str] = Field(default=None, max_length=64, description="agent self-report; ignored, recorded for audit")


def sha256_text(text: str) -> str:
    """sha256 of ``text`` as UTF-8. A lone UTF-16 surrogate (a truncated emoji arriving as ``"\\ud83d"`` in an agent's
    JSON) is not valid Unicode and has no UTF-8 form; it is encoded with ``surrogatepass`` so hashing agent text can never
    raise (valid text hashes exactly as before). The channel rejects such text before parsing (INT-REQ-009)."""
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


class SpecialistReport(BaseModel):
    """Immutable structured report from a subject specialist."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    agent_version: Optional[str] = Field(default=None, max_length=64)
    subject: str = Field(min_length=1, max_length=128)
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128)
    original_response: str = Field(min_length=1, max_length=400_000)
    response_sha256: str = Field(min_length=64, max_length=64)
    supplied_texts: list[SuppliedText] = Field(default_factory=list, max_length=16)
    claims: list[ClaimRecord] = Field(default_factory=list, max_length=512)
    assumptions: list[str] = Field(default_factory=list, max_length=64)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=64)
    created_at: str = Field(description="RFC 3339 UTC timestamp")

    @model_validator(mode="after")
    def _immutable(self) -> "SpecialistReport":
        if sha256_text(self.original_response) != self.response_sha256:
            raise ValueError("response_sha256 does not match original_response; reports are immutable")
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate claim_id in report")
        for c in self.claims:
            if c.report_id != self.report_id or c.request_id != self.request_id:
                raise ValueError(f"claim {c.claim_id} does not belong to this report")
        return self


class EligibilityClass(str, Enum):
    PROPOSITIONAL_ARGUMENT = "PROPOSITIONAL_ARGUMENT"      # argument structure: evidence -> inference -> point
    ARITHMETIC_CONSTRAINT = "ARITHMETIC_CONSTRAINT"        # counts, lengths, marks, thresholds
    QUANTITATIVE_CLAIM = "QUANTITATIVE_CLAIM"              # exact numeric claim with given values
    NOT_ELIGIBLE_INTERPRETIVE = "NOT_ELIGIBLE_INTERPRETIVE"  # literary/historical interpretation as a truth claim
    NOT_ELIGIBLE_FACTUAL = "NOT_ELIGIBLE_FACTUAL"          # world or text fact: route to evidence service
    NOT_ELIGIBLE_RUBRIC_JUDGMENT = "NOT_ELIGIBLE_RUBRIC_JUDGMENT"  # subjective criterion judgement
    NOT_ELIGIBLE_OTHER = "NOT_ELIGIBLE_OTHER"


class EligibilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    eligibility_class: EligibilityClass
    eligible: bool
    decided_by: Literal["deterministic", "model", "hybrid"]
    reasons: list[str] = Field(default_factory=list)
    route_to: Optional[str] = Field(default=None, description="for ineligible claims: 'evidence_service', 'subject_evaluator', 'unresolved'")
    policy_version: str


class GroundingCheck(BaseModel):
    """Result of a DETERMINISTIC grounding check on a symbol or premise."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_id: str = Field(description="symbol name or assertion id")
    kind: GroundingKind
    method: Literal["verbatim_match", "normalized_match", "locator_exists", "numeric_in_task", "not_checkable"]
    verified: Optional[bool] = None
    document_id: Optional[str] = None
    detail: Optional[str] = Field(default=None, max_length=2000)


class AmbiguityFlag(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str = Field(max_length=2000)
    alternatives: list[str] = Field(default_factory=list, max_length=8)


class AtomGloss(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str
    meaning: str = Field(max_length=1000)
    grounding: Optional[Grounding] = None


class Interpretation(BaseModel):
    """Human-readable record of how the translator read the claim. Shown to the
    Overseer and reviewers so the reading can be challenged."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    reading: str = Field(max_length=4000)
    glossary: list[AtomGloss] = Field(default_factory=list)
    ambiguity_flags: list[AmbiguityFlag] = Field(default_factory=list)


class ProviderInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_name: str
    model_id: Optional[str] = None
    prompt_version: Optional[str] = None
    temperature: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    attempts: int = 1


class TranslationStatus(str, Enum):
    TRANSLATED = "TRANSLATED"
    AMBIGUOUS_TRANSLATION = "AMBIGUOUS_TRANSLATION"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_FORMALIZATION = "INVALID_FORMALIZATION"
    TRANSLATION_FAILED = "TRANSLATION_FAILED"


class StructuralFinding(BaseModel):
    """A deterministic structural or source-integrity finding (not a solver result)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    severity: Literal["error", "warning", "info"]
    message: str = Field(max_length=2000)
    claim_ids: list[str] = Field(default_factory=list)
    rule_source: Optional[str] = Field(default=None, max_length=200, description="e.g. 'english_specialist/paragraphs.md P7' (working rule, not an official IB rule)")
    deterministic: bool = True


class TranslationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation_id: str
    claim_id: str
    request_id: str
    report_id: str
    status: TranslationStatus
    eligibility: EligibilityDecision
    claim_text_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64, description=(
        "sha256 of the claim_text this translation was produced for (set by the translator). A translation is bound to the "
        "text it read, not only to (request_id, claim_id): the outcome composer and the channel reject one attached to a "
        "claim whose text differs, so a stale translation is never displayed under another text"))
    problem: Optional[Problem] = None
    interpretation: Optional[Interpretation] = None
    grounding_checks: list[GroundingCheck] = Field(default_factory=list)
    provider: Optional[ProviderInfo] = None
    translator_version: str
    policy_version: str
    diagnostics: list[str] = Field(default_factory=list)
    created_at: str


class SemanticFidelityReview(BaseModel):
    """Advisory review of whether the formalization matches the claim's meaning.
    Produced by an independent reviewer (model or human). Never a verification."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    review_id: str
    translation_id: str
    verdict: Literal["faithful", "unfaithful", "uncertain"]
    issues: list[str] = Field(default_factory=list)
    reviewer: ProviderInfo
    advisory_only: Literal[True] = True
    created_at: str


class ClaimVerificationOutcome(BaseModel):
    """What the verification layer hands to the Overseer for one claim.

    ``display_status`` is derived deterministically: a non-TRANSLATED translation
    maps to its own status; otherwise it is the engine's status. The Overseer must
    verify ``verification.signature`` before trusting it.
    """
    model_config = ConfigDict(extra="forbid")
    outcome_id: str
    request_id: str
    report_id: str
    claim_id: str
    translation: TranslationResult
    verification: Optional[VerificationResult] = None
    semantic_review: Optional[SemanticFidelityReview] = None
    structural_findings: list[StructuralFinding] = Field(default_factory=list)
    display_status: VerificationStatus
    summary: str = Field(max_length=4000, description="plain-language statement of what was checked, under which assumptions, and what remains unverified")
    created_at: str
