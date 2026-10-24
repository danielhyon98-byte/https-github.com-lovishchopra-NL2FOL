"""Contracts for the inter-agent communication channel.

Every message between agents (router -> specialist, specialist -> router, agent ->
agent) passes through the channel. A request is turned into an explicit
``TaskRequest`` (what is asked, under which constraints, with which texts). A
response is checked against the request it answers before the recipient sees it,
and the recipient receives a ``TransmissionReceipt`` beside the payload saying
exactly what was checked and what was found.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ir.canonical import sha256_hex
from ..integrity.contracts import IntegrityFinding
from ..translate.contracts import ClaimVerificationOutcome, StructuralFinding, SuppliedText

ConstraintKind = Literal["max_words", "min_words", "max_paragraphs", "min_paragraphs", "must_cite_supplied_text", "must_address_all_items", "other"]
#: Longest receipt summary; the channel summarises per-check lists as counts and truncates defensively, never raising.
SUMMARY_MAX_CHARS = 8000


class RequestItem(BaseModel):
    """One thing the request asks the specialist to do (a question or instruction)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["question", "instruction"] = "instruction"
    required: bool = True
    command_term: Optional[str] = Field(default=None, description="IB command term detected in the item, e.g. 'to what extent'")
    level: Optional[int] = Field(default=None, ge=1, le=3, description="command-term level: 1 recall, 2 apply/explain, 3 analyse/evaluate (needs a judgement)")


class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    constraint_id: str = Field(min_length=1, max_length=64)
    kind: ConstraintKind
    value: Optional[str] = Field(default=None, description="numeric value as exact text, when applicable")
    text: str = Field(min_length=1, max_length=1000, description="the constraint as stated in the request")
    excludes: list[Literal["working", "diagram"]] = Field(default_factory=list, max_length=2, description=(
        "what the request sets outside a word bound ('Write no more than 350 words, plus working and your diagram'): the "
        "bound is measured over the prose only, without working lines (equations, calculation lines, tables) and, for "
        "'diagram', without the description of a diagram"))


class TaskRequest(BaseModel):
    """The router's request to a specialist, made explicit and immutable."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    plan_id: str = Field(min_length=1, max_length=128)
    from_agent_id: str = Field(min_length=1, max_length=128)
    to_agent_id: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=128)
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128)
    user_input: str = Field(min_length=1, max_length=400_000)
    user_input_sha256: str = Field(min_length=64, max_length=64)
    items: list[RequestItem] = Field(default_factory=list, max_length=64)
    constraints: list[Constraint] = Field(default_factory=list, max_length=64)
    supplied_texts: list[SuppliedText] = Field(default_factory=list, max_length=16)
    created_at: str

    @model_validator(mode="after")
    def _hash(self) -> "TaskRequest":
        if sha256_hex(self.user_input) != self.user_input_sha256:
            raise ValueError("user_input_sha256 does not match user_input")
        return self


class TransmissionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"                            # no findings
    ACCEPTED_WITH_FINDINGS = "ACCEPTED_WITH_FINDINGS"  # delivered; recipient must read the findings
    REJECTED = "REJECTED"                            # not delivered: identity, integrity or scope violation


class CoverageRecord(BaseModel):
    """Which claims address which request item. Heuristic unless an adapter tags claims: ``part_label`` when the item is a
    lettered or numbered part and the answer labels its parts (the claims under the same label address it),
    ``lexical_heuristic`` otherwise (shared content terms with a claim or with a paragraph's claims together)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_id: str
    addressed: bool
    addressed_by_claim_ids: list[str] = Field(default_factory=list)
    method: Literal["adapter_tag", "part_label", "lexical_heuristic", "not_checkable"]


class ConstraintResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    constraint_id: str
    satisfied: Optional[bool]
    method: Literal["formal", "deterministic", "not_checkable"]
    detail: str = Field(max_length=2000)
    formal_result_id: Optional[str] = None
    formal_status: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list, max_length=64, description=(
        "for a check of the report's own statement (receipt.formal_checks): the delivered claims whose text holds the "
        "clause the check was built from, so the router can tell which claim a failed or undecided check concerns"))


class TransmissionReceipt(BaseModel):
    """What the channel did to one message. Travels with the payload to the recipient
    and to the Overseer."""
    model_config = ConfigDict(extra="forbid")
    receipt_id: str
    message_id: str
    request_id: str
    task_id: str
    direction: Literal["router_to_specialist", "specialist_to_router", "agent_to_agent"]
    status: TransmissionStatus
    findings: list[IntegrityFinding] = Field(default_factory=list)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    outcomes: list[ClaimVerificationOutcome] = Field(default_factory=list)
    branch: Optional[str] = Field(default=None, description="subject branch that handled the message")
    structural_findings: list[StructuralFinding] = Field(default_factory=list, description="branch integrity-pack findings (deterministic)")
    formal_checks: list[ConstraintResult] = Field(default_factory=list, description="branch formal checks decided by the engine about the report's own statements")
    formal_result_ids: list[str] = Field(default_factory=list)
    summary: str = Field(max_length=SUMMARY_MAX_CHARS)
    created_at: str

    @property
    def errors(self) -> list[IntegrityFinding]:
        return [f for f in self.findings if f.severity == "error"]
