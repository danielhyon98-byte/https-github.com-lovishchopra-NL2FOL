"""Provider interfaces for the translation layer.

A provider turns a :class:`TranslationRequest` into raw text that the pipeline
parses and validates. Providers never see or set verification status; they are
replaceable (fixture, Anthropic Messages API, any OpenAI-compatible server) so the
platform is not tied to one model vendor.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ...ir.schema import Problem
from ..contracts import (
    ClaimRecord, EligibilityDecision, FigureReading, Interpretation, PremiseSource, ProviderInfo, ReviewBinding, SourceIdentity, SuppliedText, TaskRecord,
)


class ProviderError(RuntimeError):
    """A provider could not produce a response. The pipeline maps it to TRANSLATION_FAILED."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


class ProviderConfigurationError(ProviderError):
    """A provider is missing configuration or an optional dependency."""


class TranslationRequest(BaseModel):
    """Everything a provider needs to propose a formalization of one claim."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim: ClaimRecord
    supporting_claims: list[ClaimRecord] = Field(default_factory=list)
    supplied_texts: list[SuppliedText] = Field(default_factory=list)
    eligibility: EligibilityDecision
    prompt_version: str
    ir_version: str
    prior_diagnostics: list[str] = Field(
        default_factory=list,
        description="diagnostics from the previous attempt, so a retry can correct them (empty on the first attempt)",
    )
    subject_profile_text: Optional[str] = Field(
        default=None,
        max_length=4000,
        description=(
            "model-facing description of the IB subject profile (what the formal check can and cannot "
            "establish in this subject); produced by subjects.prompt_profile_text, rendered as the "
            "'subject_profile' data block"
        ),
    )
    task: Optional[TaskRecord] = Field(default=None, description="the task as the router issued it, when the caller holds it; rendered as the 'task' data block")


class ProviderResponse(BaseModel):
    """Raw provider text plus bookkeeping. ``raw_text`` is untrusted data."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    raw_text: str
    info: ProviderInfo


@runtime_checkable
class TranslationProvider(Protocol):
    """Proposes an IR formalization for a claim."""
    name: str

    def propose(self, request: TranslationRequest) -> ProviderResponse: ...


class ReviewRequest(BaseModel):
    """Input to an independent semantic-fidelity reviewer: the claim, the proposed problem and interpretation, and the
    evidence their fidelity is judged against: the original task (when known), the supporting claims' contents, the
    supplied texts, the identity and digest of every input (``sources``), the premise-to-source mapping with the
    deterministic checks, and how each compared figure is stated. ``binding`` ties the review to exactly these inputs
    and their versions; a request without the evidence (only the first three fields) is recorded as such and cannot
    count as an approval."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim: ClaimRecord
    problem: Problem
    interpretation: Interpretation
    task: Optional[TaskRecord] = None
    supporting_claims: list[ClaimRecord] = Field(default_factory=list)
    supplied_texts: list[SuppliedText] = Field(default_factory=list)
    sources: list[SourceIdentity] = Field(default_factory=list)
    premise_sources: list[PremiseSource] = Field(default_factory=list)
    figure_readings: list[FigureReading] = Field(default_factory=list)
    translation_diagnostics: list[str] = Field(default_factory=list, max_length=64)
    binding: Optional[ReviewBinding] = None
    prompt_version: Optional[str] = Field(default=None, description="the review prompt the request is rendered for")


@runtime_checkable
class ReviewProvider(Protocol):
    """Reviews whether a formalization is faithful to the claim (advisory)."""
    name: str

    def review(self, request: ReviewRequest) -> ProviderResponse: ...
