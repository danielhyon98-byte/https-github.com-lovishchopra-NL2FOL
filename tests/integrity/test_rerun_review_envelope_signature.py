"""Re-run review finding security-1, envelope side: MessageLog.accept raised TypeError on a forged envelope signature
holding non-ASCII text. It now refuses the envelope (INT-ENV-006) and never raises."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity.contracts import AgentMessage, AgentRole, payload_hash, sign_message, verify_message
from epinoic_logic.integrity.envelope import MessageLog

KEY = b"rerun-review-envelope-key-0123456"


def message(**over) -> AgentMessage:
    payload = {"x": 1}
    data = dict(message_id="m1", request_id="r", task_id="t", sender_agent_id="a", sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER,
                contract="specialist_report/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at="2026-10-17T00:00:00Z")
    data.update(over)
    return AgentMessage(**data)


@pytest.mark.parametrize("forged", ["\u00e9" * 64, "A" * 64, "0" * 63, ""])
def test_a_forged_envelope_signature_is_refused_not_raised(forged: str):
    signed = sign_message(message(), KEY, "k")
    bad = signed.model_copy(update={"signature": forged})
    assert verify_message(bad, KEY) is False
    findings = MessageLog(signing_key=KEY).accept(bad)
    assert "INT-ENV-006" in [f.code for f in findings]


def test_the_genuine_envelope_signature_verifies():
    """Control."""
    signed = sign_message(message(), KEY, "k")
    assert verify_message(signed, KEY) and MessageLog(signing_key=KEY).accept(signed) == []
