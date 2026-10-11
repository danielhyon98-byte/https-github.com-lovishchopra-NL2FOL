"""Contracts for inter-agent communication integrity.

Where hallucination enters a multi-agent pipeline is not only inside one agent's
answer but BETWEEN agents: the router hands a task to a specialist that answers a
different task; the combinator drops a material claim, inflates its certainty,
merges two claims into a stronger one, or quietly reconciles a contradiction; the
Overseer reads a verification result that was produced for an earlier version of a
claim. Every message is therefore wrapped in a versioned envelope with a content
hash (integrity) and an optional HMAC signature (authenticity), every synthesized
claim must point at the source claims it came from with the transformation
recorded, and every verification result stays bound to the exact representation it
checked.

Every finding carries structured identifiers (claim ids, message ids, report ids,
agent ids, document ids, result ids) so the Overseer can act on it without parsing
prose. Messages are truncated, never the identifier lists.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..ir.canonical import canonical_json, sha256_hex
from ..ir.schema import Assertion, Certainty, SourceRef

MESSAGE_MAX_CHARS = 2000
_ELLIPSIS = " ...[truncated]"


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


# --------------------------------------------------------------------------- #
# Timestamps
# --------------------------------------------------------------------------- #

_TS_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")


def parse_rfc3339(value: Any) -> Optional[datetime]:
    """Parse an RFC 3339 timestamp into an aware UTC datetime, or return None.

    Accepted: ``2026-10-11T10:00:00Z``, lower-case ``t``/``z``, fractional seconds,
    numeric offsets (``+01:00``), and the space separator RFC 3339 permits. A
    timestamp without an explicit offset or ``Z`` is NOT accepted: instants are
    compared across agents, so the zone must be stated.
    """
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not _TS_SHAPE.match(s):
        return None
    s = s[:-1] + "+00:00" if s[-1] in "zZ" else s
    s = s[:10] + "T" + s[11:]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc)


def _require_rfc3339(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if parse_rfc3339(value) is None:
        raise ValueError(f"{field_name} must be an RFC 3339 timestamp with an explicit offset or Z; got {value!r}")
    return value


# --------------------------------------------------------------------------- #
# Payload hashing and envelope signing
# --------------------------------------------------------------------------- #

def _check_finite(obj: Any, path: str = "payload") -> None:
    """Reject NaN/Infinity: json.dumps would emit non-JSON tokens that a strict
    receiver cannot reproduce, so the content hash would not be reproducible."""
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError(f"non-finite number at {path} cannot be hashed canonically")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _check_finite(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check_finite(v, f"{path}[{i}]")


def payload_hash(payload: dict) -> str:
    _check_finite(payload)
    return sha256_hex(canonical_json(payload))


ENVELOPE_SIGNATURE_FIELDS = ("signature", "signature_key_id")


class AgentMessage(BaseModel):
    """Envelope for every inter-agent message. The payload is opaque JSON; its hash
    is part of the envelope so a mutated or truncated payload is detectable.

    ``payload_sha256`` is an INTEGRITY check only: a sender that replaces the payload
    and recomputes the hash passes it. Authenticity comes from ``signature``, an
    HMAC-SHA256 over the canonical envelope (every field except the two signature
    fields); see :func:`sign_message` and :func:`verify_message`.
    """
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
    created_at: str = Field(description="RFC 3339 timestamp with explicit offset or Z")
    signature: Optional[str] = Field(default=None, description="HMAC-SHA256 hex over the canonical envelope without the signature fields")
    signature_key_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("created_at")
    @classmethod
    def _ts(cls, v: str) -> str:
        return _require_rfc3339(v, "created_at")  # type: ignore[return-value]

    @model_validator(mode="after")
    def _hash(self) -> "AgentMessage":
        _check_finite(self.payload)
        if sha256_hex(canonical_json(self.payload)) != self.payload_sha256:
            raise ValueError("payload_sha256 does not match payload")
        return self


def envelope_signable_text(msg: AgentMessage) -> str:
    data = msg.model_dump(mode="json", exclude_none=True)
    for f in ENVELOPE_SIGNATURE_FIELDS:
        data.pop(f, None)
    return canonical_json(data)


def envelope_digest(msg: AgentMessage) -> str:
    """Digest of the whole envelope (header and payload hash) minus the signature
    fields. Two envelopes with the same message id but different digests are not a
    replay: something in the header was changed."""
    return sha256_hex(envelope_signable_text(msg))


def sign_message(msg: AgentMessage, key: bytes, key_id: str) -> AgentMessage:
    if not key:
        raise ValueError("signing key must not be empty")
    mac = hmac.new(key, envelope_signable_text(msg).encode("utf-8"), hashlib.sha256).hexdigest()
    return msg.model_copy(update={"signature": mac, "signature_key_id": key_id})


def verify_message(msg: AgentMessage, key: bytes) -> bool:
    if not msg.signature or not key:
        return False
    expected = hmac.new(key, envelope_signable_text(msg).encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, msg.signature)


# --------------------------------------------------------------------------- #
# Router plan
# --------------------------------------------------------------------------- #

class WorkPlan(BaseModel):
    """What the router decided. Specialists must answer THIS task, within THIS scope.

    ``allowed_document_ids`` empty means UNRESTRICTED (no retrieval-scope check);
    a plan that wants to forbid every citation must say so with a non-empty list
    of permitted documents. ``plan_sha256``, when present, must equal the digest of
    the rest of the plan so a swapped plan cannot re-legitimise reports."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=128)
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128)
    selected_agent_ids: list[str] = Field(min_length=1, max_length=16)
    allowed_document_ids: list[str] = Field(default_factory=list, max_length=64, description="retrieval scope the specialists may cite; empty = unrestricted")
    deadline_at: Optional[str] = Field(default=None, description="RFC 3339 timestamp with explicit offset or Z")
    budgets: dict[str, int] = Field(default_factory=dict)
    plan_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64, description="sha256 of the canonical plan without this field")

    @field_validator("deadline_at")
    @classmethod
    def _ts(cls, v: Optional[str]) -> Optional[str]:
        return _require_rfc3339(v, "deadline_at")

    @model_validator(mode="after")
    def _digest(self) -> "WorkPlan":
        if self.plan_sha256 is not None and self.plan_sha256 != plan_digest(self):
            raise ValueError("plan_sha256 does not match the plan")
        return self


def plan_digest(plan: WorkPlan) -> str:
    data = plan.model_dump(mode="json", exclude_none=True)
    data.pop("plan_sha256", None)
    return sha256_hex(canonical_json(data))


def seal_plan(plan: WorkPlan) -> WorkPlan:
    return plan.model_copy(update={"plan_sha256": plan_digest(plan)})


# --------------------------------------------------------------------------- #
# Combinator output
# --------------------------------------------------------------------------- #

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
    formal_conclusion: Optional[Assertion] = Field(default=None, description="the combinator's formal statement of this claim over the cited sources' shared glossary; when present the channel checks that the cited formalized sources entail it")


class LedgerEntry(BaseModel):
    """Record of what the combinator did with a source claim that is not carried.

    A non-'dropped' entry must name the synthesized claim it went into
    (``synthesized_claim_id``), and that claim must cite the sources; otherwise the
    entry does not account for them. A 'dropped' entry needs a meaningful reason."""
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

    @model_validator(mode="after")
    def _distinct(self) -> "ConflictRecord":
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("conflict record lists the same claim id more than once; a conflict needs two distinct parties")
        return self


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
    created_at: str = Field(description="RFC 3339 timestamp with explicit offset or Z")

    @field_validator("created_at")
    @classmethod
    def _ts(cls, v: str) -> str:
        return _require_rfc3339(v, "created_at")  # type: ignore[return-value]

    @model_validator(mode="after")
    def _hash(self) -> "Synthesis":
        if sha256_hex(self.text) != self.text_sha256:
            raise ValueError("text_sha256 does not match text")
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate synthesized claim_id")
        return self


# --------------------------------------------------------------------------- #
# Findings and report
# --------------------------------------------------------------------------- #

class IntegrityFinding(BaseModel):
    """One finding for the Overseer. ``message`` is prose and is truncated to
    ``MESSAGE_MAX_CHARS``; the identifier lists are never truncated."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    severity: Literal["error", "warning", "info"]
    message: str = Field(max_length=MESSAGE_MAX_CHARS)
    claim_ids: list[str] = Field(default_factory=list)
    message_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    formal_result_id: Optional[str] = Field(default=None, description="VerificationResult.result_id when Z3 established the finding")
    related_result_ids: list[str] = Field(default_factory=list, description="further engine results consulted for this finding")
    deterministic: bool = True

    @field_validator("message", mode="before")
    @classmethod
    def _truncate(cls, v: Any) -> Any:
        if isinstance(v, str) and len(v) > MESSAGE_MAX_CHARS:
            return v[: MESSAGE_MAX_CHARS - len(_ELLIPSIS)] + _ELLIPSIS
        return v

    def has_identifier(self) -> bool:
        return bool(self.claim_ids or self.message_ids or self.report_ids or self.agent_ids or self.document_ids or self.formal_result_id)


class IntegrityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: str
    request_id: str
    task_id: str
    checks_run: list[str] = Field(default_factory=list)
    findings: list[IntegrityFinding] = Field(default_factory=list)
    formal_result_ids: list[str] = Field(default_factory=list)
    created_at: str
    report_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64, description="sha256 of the canonical report without this field; set by run_integrity_checks")

    @property
    def errors(self) -> list[IntegrityFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[IntegrityFinding]:
        return [f for f in self.findings if f.severity == "warning"]


def report_digest(report: IntegrityReport) -> str:
    data = report.model_dump(mode="json", exclude_none=True)
    data.pop("report_sha256", None)
    return sha256_hex(canonical_json(data))


def verify_report_digest(report: IntegrityReport) -> bool:
    return report.report_sha256 is not None and report.report_sha256 == report_digest(report)
