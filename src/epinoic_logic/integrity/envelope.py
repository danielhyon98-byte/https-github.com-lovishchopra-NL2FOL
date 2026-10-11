"""Message-envelope checks: replay, tampering, broken reply chains, cross-task leakage."""
from __future__ import annotations

from typing import Optional

from .contracts import AgentMessage, IntegrityFinding


class MessageLog:
    """In-memory log of accepted envelopes for one request. A persistent store can
    replace it later; the checks are the same."""

    def __init__(self) -> None:
        self._by_id: dict[str, AgentMessage] = {}
        self._idem: dict[str, str] = {}

    def accept(self, msg: AgentMessage) -> list[IntegrityFinding]:
        findings: list[IntegrityFinding] = []
        prior = self._by_id.get(msg.message_id)
        if prior is not None:
            if prior.payload_sha256 == msg.payload_sha256:
                findings.append(IntegrityFinding(code="INT-ENV-001", severity="warning", message="duplicate message id with identical payload (replay)", message_ids=[msg.message_id]))
            else:
                findings.append(IntegrityFinding(code="INT-ENV-002", severity="error", message="message id reused with a DIFFERENT payload", message_ids=[msg.message_id]))
            return findings
        if msg.idempotency_key and msg.idempotency_key in self._idem and self._idem[msg.idempotency_key] != msg.message_id:
            findings.append(IntegrityFinding(code="INT-ENV-005", severity="warning", message="idempotency key already used by another message", message_ids=[msg.message_id, self._idem[msg.idempotency_key]]))
        if msg.in_reply_to is not None:
            target: Optional[AgentMessage] = self._by_id.get(msg.in_reply_to)
            if target is None:
                findings.append(IntegrityFinding(code="INT-ENV-003", severity="error", message="in_reply_to references an unknown message", message_ids=[msg.message_id, msg.in_reply_to]))
            elif target.request_id != msg.request_id or target.task_id != msg.task_id:
                findings.append(IntegrityFinding(code="INT-ENV-004", severity="error", message="reply crosses request/task boundaries", message_ids=[msg.message_id, msg.in_reply_to]))
        self._by_id[msg.message_id] = msg
        if msg.idempotency_key:
            self._idem.setdefault(msg.idempotency_key, msg.message_id)
        return findings

    def get(self, message_id: str) -> Optional[AgentMessage]:
        return self._by_id.get(message_id)
