"""Contracts of the Overseer's transfer audit.

* ``JournalEntry``: one hash-chained, MAC'd entry of a channel's journal (an event, a clearance decision,
  a recorded gap or a seal).
* ``StoredResult`` / ``ResultTombstone``: a signed engine result retained by the auditor, and what remains
  of it after eviction.
* ``TransferClearance``: the audit state of one transfer, for the router to read before acting.
* ``OverseerAudit``: the signed audit, wrapping an ``IntegrityReport`` of ``OVS-*`` findings with its
  coverage and rule divergences.

The ``IntegrityReport`` is the existing model, unchanged; an overseer agent's output is a different
contract (``overseer_verdict/1.0``) so it can never be mistaken for the infrastructure's own report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..channel.events import ChannelEvent
from ..engine.statuses import SCOPE_STATEMENT
from ..integrity.contracts import IntegrityReport

__all__ = [
    "AUDIT_SCOPE_SENTENCE", "AUDIT_SCOPE_STATEMENT", "AUDITOR_VERSION", "ClearanceState", "CLEARANCE_STATES", "JournalEntry", "StoredResult",
    "ResultTombstone", "Citation", "TransferClearance", "AuditCoverage", "Divergence", "JournalHead", "OverseerAudit",
]

AUDITOR_VERSION = "overseer-audit/1.0"
#: Trust rule TR6: carried by every audit together with the engine's scope statement.
AUDIT_SCOPE_SENTENCE = (
    "This audit covers only the transfers journaled since the auditor was attached to the channel. It shows whether the "
    "recorded transfers, receipts and signed results agree with each other and with this repository's rules. It does not "
    "show that any claim is true or any reading correct."
)
AUDIT_SCOPE_STATEMENT = SCOPE_STATEMENT + " " + AUDIT_SCOPE_SENTENCE

ClearanceState = Literal["AUDIT_FAILED", "AUDIT_PENDING", "AUDIT_PASSED_WITH_FINDINGS", "AUDIT_PASSED"]
#: Precedence: FAILED, then PENDING, then PASSED_WITH_FINDINGS, then PASSED.
CLEARANCE_STATES: tuple[str, ...] = ("AUDIT_FAILED", "AUDIT_PENDING", "AUDIT_PASSED_WITH_FINDINGS", "AUDIT_PASSED")


@dataclass(frozen=True)
class JournalEntry:
    """One journal entry. ``entry_hash = sha256(canonical(entry without entry_hash and mac))`` and
    ``mac = HMAC(journal key, entry_hash)``; ``prev_hash`` links it to the entry before (the genesis hash for the first).
    ``kind`` is an event kind, or ``clearance`` / ``gap`` / ``seal`` for the auditor's own records (``record_json``)."""
    index: int
    channel_uid: str
    kind: str
    event: Optional[ChannelEvent]
    record_json: Optional[str]
    prev_hash: str
    entry_hash: str
    mac: str

    def body(self) -> dict:
        return {"index": self.index, "channel_uid": self.channel_uid, "kind": self.kind, "event": self.event.to_dict() if self.event is not None else None,
                "record_json": self.record_json, "prev_hash": self.prev_hash}

    def size(self) -> int:
        return (self.event.content_size() if self.event is not None else 0) + len(self.record_json or "")


@dataclass(frozen=True)
class Citation:
    """Where a receipt cites a result: the event, the citation kind and the JSON path on the receipt."""
    event_seq: int
    kind: Literal["outcome", "constraint", "branch_formal", "finding_formal", "finding_related", "receipt_formal"]
    path: str


@dataclass(frozen=True)
class StoredResult:
    """A signed result retained by the auditor. The full ``result_json`` is kept while the result is live: the SMT-LIB
    binding text is inside the signed text, and stripping it would break verification."""
    result_id: str
    channel_uid: str
    task_id: str
    request_id: str
    event_seq: int
    origin: Literal["captured", "external", "auditor_run", "replay"]
    result_json: str
    result_sha256: str
    problem_json: Optional[str]
    problem_digest: Optional[str]
    key_id: Optional[str]
    key_status: Literal["local", "external", "auditor", "unknown"]
    signature_ok_at_put: bool
    signature_reason: str
    status: str
    binding_digest: str
    captured_at: str

    def size(self) -> int:
        return len(self.result_json) + len(self.problem_json or "")


@dataclass(frozen=True)
class ResultTombstone:
    """What remains of an evicted result: membership, origin and duplicate checks still decide; its content is gone."""
    result_id: str
    result_sha256: str
    status: str
    binding_digest: str
    channel_uid: str
    task_id: str
    event_seq: int
    key_id: Optional[str]
    signature_ok_at_put: bool
    origin: str


class TransferClearance(BaseModel):
    """The audit state of one transfer. Distinct from the receipt status: a transfer the channel correctly REJECTED
    audits PASSED, because the audit vouches for the receipt, not for the content. ``receipt_sha256`` is the digest of
    the receipt as journaled; a router must act only on a receipt with that digest."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    clearance_id: str
    message_id: str
    receipt_id: Optional[str] = None
    receipt_sha256: Optional[str] = None
    presented_receipt_sha256: Optional[str] = None
    task_id: str
    channel_uid: str
    seq: Optional[int] = None
    state: ClearanceState
    final: bool = False
    codes: list[str] = Field(default_factory=list)
    finding_count: int = 0
    audit_id: Optional[str] = None
    pending_result_ids: list[str] = Field(default_factory=list)
    created_at: str


class Divergence(BaseModel):
    """A rule the Overseer's own integrity report raises and no receipt of the task carries. The classification tells
    maintainers where the rule belongs; changing it is their decision."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    int_code: str
    severity: Literal["error", "warning", "info"]
    classification: Literal["rule_ownership", "time_dependent", "transmission_fault"]
    owner: Literal["channel", "integrity", "harness"]
    claim_ids: list[str] = Field(default_factory=list)
    message: str = Field(default="", max_length=2000)


class AuditCoverage(BaseModel):
    """What the audit could and could not decide. A non-empty ``notes`` or ``degraded`` means coverage was lost and
    is reported (AUDIT-002), never passed."""
    model_config = ConfigDict(extra="forbid")
    transfers: int = 0
    events_raised: int = 0
    results_cited: int = 0
    results_resolved: int = 0
    results_signature_verified: int = 0
    results_replayed: int = 0
    results_replay_pending: int = 0
    results_sampled_out: int = 0
    replay_mode: str = "none"
    claims_checked: int = 0
    joint_pool_size: int = 0
    shadow_run: Literal["run", "not_run", "not_built", "skipped"] = "not_run"
    degraded: bool = False
    digest_only_entries: int = 0
    captured_uncited: list[str] = Field(default_factory=list)
    reused_results: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class JournalHead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int
    entry_hash: str


class OverseerAudit(BaseModel):
    """A signed Overseer audit. ``signature`` is HMAC-SHA256 under the audit subkey over the canonical audit without
    its two signature fields (:func:`~epinoic_logic.overseer.audit.sign_audit`). A signed audit is never edited: a
    later audit of the same scope names it in ``supersedes``."""
    model_config = ConfigDict(extra="forbid")
    audit_id: str
    supersedes: Optional[str] = None
    scope: Literal["transfer", "task", "verdicts"]
    mode: Literal["live", "batch"]
    final: bool = False
    state: ClearanceState
    task_id: str
    request_id: str
    channel_uid: str
    message_ids: list[str] = Field(default_factory=list)
    transfer_states: dict[str, ClearanceState] = Field(default_factory=dict)
    journal_head: Optional[JournalHead] = None
    store_digest: str
    report: IntegrityReport
    coverage: AuditCoverage
    divergences: list[Divergence] = Field(default_factory=list)
    key_ids_used: list[str] = Field(default_factory=list)
    auditor_version: str = AUDITOR_VERSION
    scope_statement: str = AUDIT_SCOPE_STATEMENT
    created_at: str
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None
