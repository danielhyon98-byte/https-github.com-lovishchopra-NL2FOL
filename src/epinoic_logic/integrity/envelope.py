"""Message-envelope checks: replay, tampering, forged or re-headed envelopes, broken
reply chains, role/contract impersonation, cross-request leakage.

``payload_sha256`` proves only that the payload the receiver holds is the payload the
envelope was built for (INTEGRITY). A sender who replaces the payload and recomputes
the hash passes that check, so AUTHENTICITY needs the envelope signature: a log
constructed with ``signing_key`` rejects unsigned or badly signed envelopes
(INT-ENV-006). Without a key the log cannot authenticate senders and says so in its
docstring rather than in a finding, because in-process buses legitimately run
unsigned; the Overseer's own inputs (engine results) are checked separately and
there a missing key IS an error.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .contracts import AgentMessage, AgentRole, IntegrityFinding, envelope_digest, verify_message

# Which sender roles may issue which payload contracts. Keys are the contract name
# without its version; a contract not listed here is unrestricted.
ROLE_CONTRACTS: dict[str, frozenset[AgentRole]] = {
    "work_plan": frozenset({AgentRole.ROUTER}),
    "task_request": frozenset({AgentRole.ROUTER}),
    "specialist_report": frozenset({AgentRole.SPECIALIST}),
    # A delivered report forwarded by the router to another agent (a hand-off). The payload is the report unchanged;
    # the channel checks it against what was delivered (INT-HANDOFF-013), so the router cannot alter a report in transit.
    "specialist_report_forward": frozenset({AgentRole.ROUTER}),
    "verification_result": frozenset({AgentRole.VERIFIER}),
    "synthesis": frozenset({AgentRole.COMBINATOR}),
    "integrity_report": frozenset({AgentRole.OVERSEER, AgentRole.VERIFIER}),
    "retrieval_result": frozenset({AgentRole.RETRIEVAL}),
    # The Overseer's signed transfer audit (overseer/audit.py) and an overseer agent's verdict, wrapped and signed by the
    # verdict intake. Both come from the Overseer role only; trust comes from the key that signed them (audit key versus
    # intake key), the contract and the schema, never from the role alone.
    "overseer_audit": frozenset({AgentRole.OVERSEER}),
    "overseer_verdict": frozenset({AgentRole.OVERSEER}),
}


def contract_name(contract: str) -> str:
    return contract.split("/", 1)[0].strip().lower()


def allowed_sender_roles(contract: str) -> Optional[frozenset[AgentRole]]:
    return ROLE_CONTRACTS.get(contract_name(contract))


class MessageLog:
    """In-memory log of accepted envelopes for one request. A persistent store can
    replace it later; the checks are the same.

    ``signing_key``: when given, every envelope must carry a valid signature.
    ``request_id``: when given, envelopes for another request are flagged (INT-ENV-009).
    ``enforce_roles``: check the sender role against the contract table (INT-ENV-007)
    and a reply's sender against the replied-to message's recipient (INT-ENV-010)."""

    def __init__(self, *, signing_key: Optional[bytes] = None, request_id: Optional[str] = None, enforce_roles: bool = True) -> None:
        self._by_id: dict[str, AgentMessage] = {}
        self._digest: dict[str, str] = {}
        self._idem: dict[str, str] = {}
        self.signing_key = signing_key
        self.request_id = request_id
        self.enforce_roles = enforce_roles

    def accept(self, msg: AgentMessage) -> list[IntegrityFinding]:
        findings: list[IntegrityFinding] = []
        mid = [msg.message_id]
        agents = [msg.sender_agent_id]
        prior = self._by_id.get(msg.message_id)
        if prior is not None:
            if prior.payload_sha256 != msg.payload_sha256:
                findings.append(IntegrityFinding(code="INT-ENV-002", severity="error", message="message id reused with a DIFFERENT payload", message_ids=mid, agent_ids=agents))
            elif self._digest[msg.message_id] != envelope_digest(msg):
                changed = sorted(k for k in prior.model_dump(mode="json") if k not in ("signature", "signature_key_id") and getattr(prior, k) != getattr(msg, k))
                findings.append(IntegrityFinding(code="INT-ENV-002", severity="error", message=f"message id reused with the same payload but a changed envelope header ({changed}); this is a re-headed message, not a replay", message_ids=mid, agent_ids=sorted({prior.sender_agent_id, msg.sender_agent_id})))
            else:
                findings.append(IntegrityFinding(code="INT-ENV-001", severity="warning", message="duplicate message id with identical envelope and payload (replay)", message_ids=mid, agent_ids=agents))
            return findings
        if self.signing_key is not None and not verify_message(msg, self.signing_key):
            findings.append(IntegrityFinding(code="INT-ENV-006", severity="error", message="envelope is unsigned or its signature is invalid; the sender cannot be authenticated", message_ids=mid, agent_ids=agents))
        if self.request_id is not None and msg.request_id != self.request_id:
            findings.append(IntegrityFinding(code="INT-ENV-009", severity="error", message=f"message belongs to request {msg.request_id!r} but this log is for request {self.request_id!r}", message_ids=mid, agent_ids=agents))
        if self.enforce_roles:
            allowed = allowed_sender_roles(msg.contract)
            if allowed is not None and msg.sender_role not in allowed:
                findings.append(IntegrityFinding(code="INT-ENV-007", severity="error", message=f"a {msg.sender_role.value} may not issue the contract {msg.contract!r} (allowed senders: {sorted(r.value for r in allowed)}); role impersonation", message_ids=mid, agent_ids=agents))
        if msg.idempotency_key and msg.idempotency_key in self._idem and self._idem[msg.idempotency_key] != msg.message_id:
            first_id = self._idem[msg.idempotency_key]
            first = self._by_id.get(first_id)
            if first is not None and first.payload_sha256 != msg.payload_sha256:
                findings.append(IntegrityFinding(code="INT-ENV-011", severity="error", message="idempotency key reused by another message with a DIFFERENT payload; a retry must resend the same payload", message_ids=[msg.message_id, first_id], agent_ids=agents))
            else:
                findings.append(IntegrityFinding(code="INT-ENV-005", severity="warning", message="idempotency key already used by another message with the same payload (retry)", message_ids=[msg.message_id, first_id], agent_ids=agents))
        if msg.in_reply_to is not None:
            target: Optional[AgentMessage] = self._by_id.get(msg.in_reply_to)
            if target is None:
                findings.append(IntegrityFinding(code="INT-ENV-003", severity="error", message="in_reply_to references an unknown message", message_ids=[msg.message_id, msg.in_reply_to], agent_ids=agents))
            else:
                if target.request_id != msg.request_id or target.task_id != msg.task_id:
                    findings.append(IntegrityFinding(code="INT-ENV-004", severity="error", message="reply crosses request/task boundaries", message_ids=[msg.message_id, msg.in_reply_to], agent_ids=agents))
                if self.enforce_roles and (msg.sender_role != target.recipient_role or (target.recipient_agent_id is not None and msg.sender_agent_id != target.recipient_agent_id)):
                    findings.append(IntegrityFinding(code="INT-ENV-010", severity="error", message=f"reply comes from {msg.sender_role.value} {msg.sender_agent_id!r} but the replied-to message was addressed to {target.recipient_role.value} {target.recipient_agent_id!r}", message_ids=[msg.message_id, msg.in_reply_to], agent_ids=sorted({msg.sender_agent_id} | ({target.recipient_agent_id} if target.recipient_agent_id else set()))))
        self._by_id[msg.message_id] = msg
        self._digest[msg.message_id] = envelope_digest(msg)
        if msg.idempotency_key:
            self._idem.setdefault(msg.idempotency_key, msg.message_id)
        return findings

    def get(self, message_id: str) -> Optional[AgentMessage]:
        return self._by_id.get(message_id)

    def messages(self) -> tuple[AgentMessage, ...]:
        """Every accepted envelope in acceptance order (the first acceptance of each message id; a replayed or
        re-headed duplicate is never stored). A tuple, so a reader cannot reorder or drop entries of the log; the
        envelopes are the log's own objects."""
        return tuple(self._by_id.values())


def bind_payload(msg: AgentMessage, payload_obj: BaseModel) -> list[IntegrityFinding]:
    """Compare the envelope header with the parsed contract inside it. The envelope's
    request_id/task_id must equal the payload's, and the sender must be the agent the
    payload claims to come from (``agent_id`` for reports, ``combinator_agent_id`` for a
    synthesis). INT-ENV-008 on any mismatch."""
    mismatch: list[str] = []
    for env_field, payload_field in (("request_id", "request_id"), ("task_id", "task_id")):
        pv = getattr(payload_obj, payload_field, None)
        if pv is not None and pv != getattr(msg, env_field):
            mismatch.append(f"{env_field}: envelope {getattr(msg, env_field)!r} vs payload {pv!r}")
    owner = next((getattr(payload_obj, a) for a in ("agent_id", "combinator_agent_id", "sender_agent_id") if getattr(payload_obj, a, None) is not None), None)
    if owner is not None and owner != msg.sender_agent_id:
        mismatch.append(f"sender: envelope {msg.sender_agent_id!r} vs payload {owner!r}")
    if not mismatch:
        return []
    claim_ids = [c.claim_id for c in getattr(payload_obj, "claims", []) or [] if hasattr(c, "claim_id")]
    report_ids = [getattr(payload_obj, "report_id")] if getattr(payload_obj, "report_id", None) else ([getattr(payload_obj, "synthesis_id")] if getattr(payload_obj, "synthesis_id", None) else [])
    return [IntegrityFinding(code="INT-ENV-008", severity="error", message="envelope header does not match the payload it carries: " + "; ".join(mismatch), message_ids=[msg.message_id], agent_ids=sorted({msg.sender_agent_id} | ({owner} if owner else set())), report_ids=report_ids, claim_ids=claim_ids)]
