"""The round-9 push check on the c2 clearance commit: the text rules bidi-text and hidden-text failed OPEN. ``bus.report_bidi_findings``
wrapped both rules in ``except Exception: return []`` (and ``synthesis_hidden_findings`` the hidden-text rule), so an exception inside
a reader gave no INT-REQ-009, and ``bidi_control_message`` (the raw-text rule ``respond_text`` applies before parsing) let an exception
escape. Each rule now fails closed: a reader that raises gives the refusal (INT-REQ-009 at error severity, naming the rule and the
exception's type, never its message), each rule on its own, and the channel refuses the payload. The tests force the readers to raise."""
from __future__ import annotations

import pytest

import epinoic_logic.channel.bus as bus
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

KEY = b"c2-hold-bidi-key-0123456789abcdef!!"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
IDS = dict(request_id="r", task_id="t", subject="History", task_type="short_answer")
TEXT = "The Treaty of Versailles was signed in 1919."


def _report() -> SpecialistReport:
    return SpecialistReport(**IDS, report_id="rep-b", agent_id="history-specialist", original_response=TEXT, response_sha256=sha256_text(TEXT),
                            created_at="2026-11-14T00:00:00Z",
                            claims=[ClaimRecord(**IDS, report_id="rep-b", agent_id="history-specialist", claim_id="c1", claim_text=TEXT,
                                                claim_role="point", materiality="material")])


def _raise_on(pattern):
    real = bus._report_class_findings

    def fake(report, rx, *args, **kwargs):
        if rx is pattern:
            raise RuntimeError("secret words of the answer")
        return real(report, rx, *args, **kwargs)
    return fake


@pytest.mark.parametrize("rule,pattern", [("bidi-text", "_BIDI_CONTROL_RE"), ("hidden-text", "_HIDDEN_TEXT_RE")])
def test_a_reader_that_raises_gives_the_refusal_never_an_empty_list(monkeypatch, rule, pattern):
    assert bus.report_bidi_findings(_report()) == []  # the control: a clean report names nothing
    monkeypatch.setattr(bus, "_report_class_findings", _raise_on(getattr(bus, pattern)))
    found = bus.report_bidi_findings(_report())
    assert [(f.code, f.severity) for f in found] == [("INT-REQ-009", "error")], found
    assert f"rule {rule}" in found[0].message and "RuntimeError" in found[0].message
    assert "secret words" not in found[0].message  # the exception's message is never repeated
    assert found[0].claim_ids == ["rep-b"] and found[0].agent_ids == ["history-specialist"]


def test_both_readers_raising_give_two_refusals(monkeypatch):
    def boom(*_a, **_k):
        raise ValueError("x")
    monkeypatch.setattr(bus, "_report_class_findings", boom)
    found = bus.report_bidi_findings(_report())
    assert [f.code for f in found] == ["INT-REQ-009", "INT-REQ-009"]
    assert ["rule bidi-text" in found[0].message, "rule hidden-text" in found[1].message] == [True, True]


def test_a_report_whose_texts_cannot_be_read_is_refused():
    class Broken:
        report_id = "rep-x"
        agent_id = "a"

        @property
        def original_response(self):
            raise RuntimeError("unreadable")
    found = bus.report_bidi_findings(Broken())
    assert found and all(f.code == "INT-REQ-009" and f.severity == "error" for f in found)


def test_the_raw_text_rule_fails_closed(monkeypatch):
    assert bus.bidi_control_message("response text", TEXT) is None

    def boom(_what, _text):
        raise RuntimeError("secret")
    monkeypatch.setattr(bus, "hidden_text_message", boom)
    why = bus.bidi_control_message("response text", TEXT)
    assert why is not None and "RuntimeError" in why and "secret" not in why


def test_the_synthesis_hidden_text_rule_fails_closed():
    class Broken:
        synthesis_id = "syn-1"
        combinator_agent_id = "comb"

        @property
        def claims(self):
            raise RuntimeError("unreadable")
    found = bus.synthesis_hidden_findings(Broken())
    assert [(f.code, f.severity) for f in found] == [("INT-REQ-009", "error")] and "rule hidden-text" in found[0].message


def test_through_the_hub_a_failing_reader_refuses_the_payload(monkeypatch):
    """End to end: the report delivered as an object through the hub, with the bidi-text reader forced to raise, is refused
    (INT-REQ-009 at error severity, REJECTED), never delivered with no finding."""
    monkeypatch.setattr(bus, "_report_class_findings", _raise_on(bus._BIDI_CONTROL_RE))
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        hub.open_task(WorkPlan(plan_id="p", selected_agent_ids=["history-specialist"], **IDS))
        m, _req, _rq = hub.dispatch("t", "history-specialist", "Explain the treaty.", [])
        _reply, rc = hub.receive("t", m.message_id, _report())
    finally:
        hub.close()
    refusals = [f for f in rc.findings if f.code == "INT-REQ-009" and "rule bidi-text" in f.message]
    assert refusals and all(f.severity == "error" for f in refusals), [(f.code, f.message[:120]) for f in rc.findings]
    assert rc.status.value == "REJECTED"


def test_through_the_hub_a_failing_raw_text_reader_refuses_the_text(monkeypatch):
    def boom(_what, _text):
        raise RuntimeError("secret")
    monkeypatch.setattr(bus, "hidden_text_message", boom)
    hub = RouterHub(signing_key=KEY, config=CFG)
    try:
        hub.open_task(WorkPlan(plan_id="p", selected_agent_ids=["history-specialist"], **IDS))
        m, _req, _rq = hub.dispatch("t", "history-specialist", "Explain the treaty.", [])
        _reply, rc = hub.receive("t", m.message_id, TEXT, agent_id="history-specialist", report_id="rep-t")
    finally:
        hub.close()
    assert [f for f in rc.findings if f.code == "INT-REQ-009" and f.severity == "error"], [(f.code, f.message[:120]) for f in rc.findings]
    assert rc.status.value == "REJECTED"
