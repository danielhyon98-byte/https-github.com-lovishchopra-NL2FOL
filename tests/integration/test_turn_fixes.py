"""The checks port's fixes of the pre-build's third verification (PROTOCOL.md section 5.2), on the synthetic corpus through
the real hub, parsers, fixture translations and engine; the overseer is the TEST DOUBLE ``RecordingPort``
(tests/integration/helpers.py), as in test_turn_checker.py.

* V3-M2: whatever an overseer-port adapter raises, ``SystemExit`` included (only ``KeyboardInterrupt`` goes through), the
  call answers a signed ``refuse_incomplete`` KIT-DL-900 verdict, never an exception (an HTTP 500); a ``SystemExit`` in
  the review leaves the review unqueued and changes neither the decision nor its reasons.
* V3-L3: the checker's configuration never shows a key in its ``repr``.
* V3-L5: a call refused before delivery still has its review planned and queued over the outputs received so far; a call
  refused before any output was received has nothing to review, and says so.
* Agent ids (pre-build NOTES 55): the hub names the specialists ``<slug>-specialist`` (``-specialist@a``/``@b`` in
  duplicate mode), as the arena and the hub's credit rules do; the verdict names every answer by its protocol agent id.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.adapters.sources import specialist_names
from epinoic_logic.integration.delivery import verify_verdict_signature
from epinoic_logic.integration.turn import CheckerConfig, hub_agent_id
from tests.integration.helpers import VERDICT_KEY_HEX, RecordingPort, hello
from tests.integration.test_turn_checker import _checker, _request, _run

ASYNC = {"OVERSEER_AGENTS": "async"}


class ExitingPort(RecordingPort):
    """An adapter whose operation ``exit_on`` raises ``SystemExit`` (as a sidecar client or a crashing adapter might)."""

    def __init__(self, exit_on: str, **kw) -> None:
        super().__init__(**kw)
        self.exit_on = exit_on

    def _maybe_exit(self, op: str) -> None:
        if self.exit_on == op:
            raise SystemExit(3)

    def new_hub(self, **kw):
        self._maybe_exit("new_hub")
        return super().new_hub(**kw)

    def clearance(self, hub, task_id, message_id, receipt, *, wait_ms):
        self._maybe_exit("clearance")
        return super().clearance(hub, task_id, message_id, receipt, wait_ms=wait_ms)

    def close(self, hub, task_id):
        self._maybe_exit("close")
        return super().close(hub, task_id)

    def deliver(self, hub, task_id, *, mode, synthesis=None):
        self._maybe_exit("deliver")
        return super().deliver(hub, task_id, mode=mode, synthesis=synthesis)

    def repeats(self, hub, task_id):
        self._maybe_exit("repeats")
        return super().repeats(hub, task_id)

    def review(self, hub, task_id, admission):
        self._maybe_exit("review")
        return super().review(hub, task_id, admission)


def _check_raw(port, names=("hi-s1",), **env):
    rt, port = _checker(port, **env)
    req, _envs = _request(rt, list(names))
    return rt.checker.check(req), port


@pytest.mark.parametrize("op", ["new_hub", "clearance", "close", "deliver"])
def test_a_system_exit_in_an_overseer_operation_is_a_signed_internal_error_verdict(op):
    verdict, _ = _check_raw(ExitingPort(op))
    assert verify_verdict_signature(verdict, bytes.fromhex(VERDICT_KEY_HEX))
    assert verdict["delivery"] == {"decision": "refuse_incomplete", "deliverable": None, "reasons": ["KIT-DL-900"], "consolidation": None,
                                   "synthesis": None}
    assert verdict["overseer"]["refusal"] == "internal_error" and verdict["summary"] is None


@pytest.mark.parametrize("op", ["repeats", "review"])
@pytest.mark.parametrize("name", ["hi-s1", "hi-s2"])
def test_a_system_exit_in_the_review_changes_neither_the_decision_nor_its_reasons(op, name):
    baseline, _ = _run([name])
    verdict, _ = _check_raw(ExitingPort(op, hello_message=hello(agents="async")), names=(name,), **ASYNC)
    assert verify_verdict_signature(verdict, bytes.fromhex(VERDICT_KEY_HEX))
    assert verdict["delivery"]["decision"] == baseline["delivery"]["decision"] and verdict["delivery"]["reasons"] == baseline["delivery"]["reasons"]
    assert verdict["overseer"]["review"]["queued"] is False
    assert verdict["overseer"]["refusal"] != "internal_error"


def test_a_keyboard_interrupt_still_goes_through():
    class Interrupting(RecordingPort):
        def close(self, hub, task_id):
            raise KeyboardInterrupt
    rt, _ = _checker(Interrupting())
    req, _envs = _request(rt, ["hi-s1"])
    with pytest.raises(KeyboardInterrupt):
        rt.checker.check(req)


def test_the_checker_configuration_shows_no_key_in_its_repr():
    rt, _ = _checker()
    cfg = rt.checker.cfg
    text = repr(cfg) + repr(rt.checker.__dict__)
    assert cfg.engine_key.hex() not in text and cfg.verdict_key.hex() not in text
    assert repr(cfg.engine_key) not in text and repr(cfg.verdict_key) not in text
    assert "engine_key_id" in repr(cfg) and "verdict_key_id" in repr(cfg)
    assert "engine_key=" not in repr(cfg) and "verdict_key=" not in repr(cfg)
    assert isinstance(cfg, CheckerConfig)


# ----------------------------------------------------------------------------------------------- V3-L5: the review of a refused call


def test_a_call_refused_at_the_response_clearance_still_has_its_review_queued():
    """The response's clearance does not pass: the call is refused (KIT-DL-003), and the review of the response received
    is planned at the floor (an agreement signal: two reviews) and queued; the decision is the one without a review."""
    plain, _ = _run(["hi-s1"], port=RecordingPort(clearance_state="AUDIT_FAILED"))
    calls = []

    class FailsOnTheResponse(RecordingPort):
        def clearance(self, hub, task_id, message_id, receipt, *, wait_ms):
            out = super().clearance(hub, task_id, message_id, receipt, wait_ms=wait_ms)
            calls.append(receipt.direction)
            if receipt.direction == "specialist_to_router":
                out = dict(out, state="AUDIT_FAILED", may_act=False)
            return out
    verdict, port = _run(["hi-s1"], port=FailsOnTheResponse(hello_message=hello(agents="async")), **ASYNC)
    assert calls == ["router_to_specialist", "specialist_to_router"]
    assert verdict["delivery"]["decision"] == "refuse_integrity" and verdict["delivery"]["reasons"] == ["KIT-DL-003"]
    assert verdict["overseer"]["review"] == {"queued": True, "plan_origin": "floor", "plan_refusal": None, "router": None}
    assert port.reviewed and port.reviewed[0].effective.transfers, "the response received is planned for review"
    assert plain["delivery"]["decision"] == "refuse_integrity"
    assert port.calls[-2:] == ["repeats", "review"] and "deliver" not in port.calls


def test_a_call_refused_before_any_output_was_received_has_nothing_to_review(tmp_path):
    verdict, port = _run(["hi-s1"], port=RecordingPort(clearance_state="AUDIT_FAILED", hello_message=hello(agents="async")),
                         SIM_EVIDENCE_DIR=str(tmp_path / "ev"), **ASYNC)
    assert verdict["delivery"]["decision"] == "refuse_integrity" and verdict["delivery"]["reasons"] == ["KIT-DL-003"]
    assert verdict["overseer"]["review"] == {"queued": False, "plan_origin": None, "plan_refusal": None, "router": None}
    assert "review" not in port.calls and "repeats" not in port.calls
    [path] = list((tmp_path / "ev").glob("*.json"))
    assert "no specialist output was received" in json.loads(path.read_text(encoding="utf-8"))["review_skipped"]


# ----------------------------------------------------------------------------------------------- agent ids (NOTES 55)


def test_the_hub_names_the_specialists_as_the_arena_does_and_the_verdict_by_protocol_ids():
    verdict, port = _run(["hi-s1"])
    assert [a["agent_id"] for a in verdict["bound"]["answers"]] == ["history"]
    assert verdict["delivery"]["deliverable"]["agent_id"] == "history"
    assert [reply.sender_agent_id for reply, _rc in port.replies] == ["history-specialist"]
    assert [reply.payload["agent_id"] for reply, _rc in port.replies] == ["history-specialist"]  # the delivered report's author


def test_duplicate_instances_are_named_as_their_specialist():
    verdict, port = _run(["hi-s1", "hi-s1"], mode="duplicate")
    assert [a["agent_id"] for a in verdict["bound"]["answers"]] == ["history@a", "history@b"]
    assert {reply.sender_agent_id for reply, _rc in port.replies} == {"history-specialist@a", "history-specialist@b"}
    assert verdict["delivery"]["deliverable"]["agent_id"] in ("history@a", "history@b")
    assert hub_agent_id("history@b") == "history-specialist@b" and hub_agent_id("english-a-literature") == "english-a-literature-specialist"
    # the hub's credit rules read an instance as its specialist ("the History specialist")
    assert specialist_names("history-specialist@a") == specialist_names("history-specialist") == ["history specialist"]
    assert specialist_names("mathematics-aa-specialist@b") == specialist_names("mathematics-aa-specialist")
    assert specialist_names("history@a") == [] and specialist_names("history-specialist@c") == []
