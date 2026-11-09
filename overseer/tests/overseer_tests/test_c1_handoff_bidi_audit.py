"""Round-8 clearance (integrated round c1), handoff fixer: the transfer auditor re-derives the channel's rule bidi-text.

A specialist's response whose own text holds a bidirectional embedding, override or isolate is refused by the channel (INT-REQ-009,
REJECTED, never delivered; ``tests/channel/test_c1_handoff_bidi.py``). The auditor reads the rule from the journaled input with the
channel's own functions, bound at import (``checks.receipts._bidi_implied``): a refusal passes the audit, and a channel that delivers
such a response (its rule removed at run time) is OVS-RCPT-004, the receipt lacking the INT-REQ-009 its input implies."""
from __future__ import annotations

import pytest

import epinoic_logic.channel.bus as bus
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.api.translate import sha256_text

from .conftest import findings, make_auditor, new_channel, ovs_errors

TEXT = "The Montgomery bus boycott began on 5 December \u202e1955\u202c and lasted 381 days."


def _plan() -> WorkPlan:
    return WorkPlan(plan_id="plan-bidi", request_id="req-bidi", task_id="task-bidi", subject="History", task_type="short_answer",
                    selected_agent_ids=["history-specialist", "combinator"])


def _structured(text: str) -> dict:
    ids = dict(request_id="req-bidi", task_id="task-bidi", report_id="rep-bidi-0", agent_id="history-specialist", subject="History",
               task_type="short_answer")
    claim = dict(ids, claim_id="h1.1", claim_text=text, claim_role="point", materiality="material")
    return dict(ids, original_response=text, response_sha256=sha256_text(text), claims=[claim], created_at="2026-11-06T10:00:00Z")


def _audit(payload):
    auditor = make_auditor()
    ch = new_channel(auditor, _plan())
    m, _req, _rq = ch.request("router", "history-specialist", "When did the Montgomery bus boycott begin, and how long did it last?", [])
    _reply, rc = ch.respond_text(m.message_id, payload, agent_id="history-specialist", report_id="rep-bidi-0")
    return rc, auditor.audit(ch.uid)


def _rcpt_bidi(audit) -> list:
    return [f for f in findings(audit, "OVS-RCPT-004") if "INT-REQ-009" in f.message and "bidi-text" in f.message]


@pytest.mark.parametrize("payload", [TEXT, _structured(TEXT)], ids=["raw text", "structured report"])
def test_a_refused_response_passes_the_audit(payload):
    rc, audit = _audit(payload)
    assert rc.status.value == "REJECTED" and any(f.code == "INT-REQ-009" and "bidirectional" in f.message for f in rc.findings)
    assert not _rcpt_bidi(audit) and not ovs_errors(audit), [(f.code, f.message[:200]) for f in audit.report.findings]


@pytest.mark.parametrize("payload", [TEXT, _structured(TEXT)], ids=["raw text", "structured report"])
def test_a_channel_that_delivers_a_response_holding_a_control_is_named(monkeypatch, payload):
    """The channel's rule removed at run time (a channel version without it, or a compromised one): the response is delivered, and
    the auditor, whose copy of the rule was bound when it was imported, names the INT-REQ-009 the journaled input implies."""
    monkeypatch.setattr(bus, "bidi_control_message", lambda what, text: None)
    monkeypatch.setattr(bus, "report_bidi_findings", lambda report: [])
    rc, audit = _audit(payload)
    assert rc.status.value != "REJECTED" and not any(f.code == "INT-REQ-009" for f in rc.findings)
    named = _rcpt_bidi(audit)
    assert named and "U+202E" in named[0].message, [(f.code, f.message[:200]) for f in audit.report.findings]


def test_control_a_clean_response_is_not_named():
    rc, audit = _audit(TEXT.replace("\u202e", "").replace("\u202c", ""))
    assert rc.status.value != "REJECTED" and not _rcpt_bidi(audit)
