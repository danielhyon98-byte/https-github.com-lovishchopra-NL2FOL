"""Contracts for inter-agent communication integrity.

Where hallucination enters a multi-agent pipeline is not only inside one agent's
answer but BETWEEN agents: the router hands a task to a specialist that answers a
different task; the combinator drops a material claim, inflates its certainty,
merges two claims into a stronger one, or quietly reconciles a contradiction; the
Overseer reads a verification result that was produced for an earlier version of a
claim. Every message is therefore wrapped in a versioned envelope with a content
hash, every synthesized claim must point at the source claims it came from with the
transformation recorded, and every verification result stays bound to the exact
representation it checked.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ir.canonical import canonical_json, sha256_hex
from ..ir.schema import Certainty, SourceRef


class AgentRole(str, Enum):
    ROUTER = "router"
    RETRIEVAL = "retrieval"
    SPECIALIST = "specialist"
    VERIFIER = "verifier"
    COMBINATOR = "combinator"
    OVERSEER = "overseer"
    GATE = "response_gate"


CERTAINTY_RANK: dict[str, int] = {"possible": 1, "probable": 2, "established": 3}

Transformation = Literal["carried", "paraphrased", "merged", "narrowed", "generalized", "new", "dropped"]


class AgentMessage(BaseModel):
    """Envelope for every inter-agent message. The payload is opaque JSON; its hash
    is part of the envelope so a mutated or truncated payload is detectable."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    message_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    sender_agent_id: str = Field(min_length=1, max_length=128)
    sender_role: AgentRole
    sender_version: Optional[str] = Field(default=None, max_length=64)
    recipient_role: AgentRole
    recipient_agent_id: Optional[str] = Field(default=None, max_length=128)
    contract: str = Field(min_length=1, max_length=64, description="payload contract name/version, e.g. 'specialist_report/1.0'")
    payload: dict
    payload_sha256: str = Field(min_length=64, max_length=64)
    in_reply_to: Optional[str] = Field(default=None, max_length=128)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)
    created_at: str

    @model_validator(mode="after")
    def _hash(self) -> "AgentMessage":
        if sha256_hex(canonical_json(self.payload)) != self.payload_sha256:
            raise ValueError("payload_sha256 does not match payload")
        return self


def payload_hash(payload: dict) -> str:
    return sha256_hex(canonical_json(payload))


class WorkPlan(BaseModel):
    """What the router decided. Specialists must answer THIS task, within THIS scope."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=128)
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128)
    selected_agent_ids: list[str] = Field(min_length=1, max_length=16)
    allowed_document_ids: list[str] = Field(default_factory=list, max_length=64, description="retrieval scope the specialists may cite")
    deadline_at: Optional[str] = Field(default=None, description="RFC 3339 UTC")
    budgets: dict[str, int] = Field(default_factory=dict)


class SynthesizedClaim(BaseModel):
    """A claim in the combinator's synthesis, with its provenance to source claims."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    certainty: Certainty = "established"
    materiality: Literal["material", "supporting"] = "material"
    source_claim_ids: list[str] = Field(default_factory=list, max_length=64)
    transformation: Transformation = "carried"
    evidence_refs: list[SourceRef] = Field(default_factory=list, max_length=64)


class LedgerEntry(BaseModel):
    """Record of what the combinator did with a source claim that is not carried."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_claim_ids: list[str] = Field(min_length=1, max_length=64)
    transformation: Transformation
    synthesized_claim_id: Optional[str] = None
    reason: Optional[str] = Field(default=None, max_length=1000)


class ConflictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    conflict_id: str = Field(min_length=1, max_length=128)
    claim_ids: list[str] = Field(min_length=2, max_length=64)
    description: str = Field(max_length=2000)
    status: Literal["unresolved", "resolved_with_basis"] = "unresolved"
    basis: Optional[str] = Field(default=None, max_length=2000)


class Synthesis(BaseModel):
    """The combinator's output: student-facing text plus the claim ledger."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    synthesis_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    combinator_agent_id: str = Field(min_length=1, max_length=128)
    source_report_ids: list[str] = Field(min_length=1, max_length=32)
    claims: list[SynthesizedClaim] = Field(default_factory=list, max_length=512)
    ledger: list[LedgerEntry] = Field(default_factory=list, max_length=512)
    conflicts: list[ConflictRecord] = Field(default_factory=list, max_length=64)
    text: str = Field(min_length=1, max_length=400_000)
    text_sha256: str = Field(min_length=64, max_length=64)
    created_at: str

    @model_validator(mode="after")
    def _hash(self) -> "Synthesis":
        if sha256_hex(self.text) != self.text_sha256:
            raise ValueError("text_sha256 does not match text")
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate synthesized claim_id")
        return self


class IntegrityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    severity: Literal["error", "warning", "info"]
    message: str = Field(max_length=2000)
    claim_ids: list[str] = Field(default_factory=list)
    message_ids: list[str] = Field(default_factory=list)
    formal_result_id: Optional[str] = Field(default=None, description="VerificationResult.result_id when Z3 established the finding")
    deterministic: bool = True


class IntegrityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: str
    request_id: str
    task_id: str
    checks_run: list[str] = Field(default_factory=list)
    findings: list[IntegrityFinding] = Field(default_factory=list)
    formal_result_ids: list[str] = Field(default_factory=list)
    created_at: str

    @property
    def errors(self) -> list[IntegrityFinding]:
        return [f for f in self.findings if f.severity == "error"]
