"""Step 10 of the checks port (PROTOCOL.md section 5.2): the asynchronous overseer-agent review is never a release
condition and never changes a decision. Whatever fails in it (the overseer port's ``repeats`` or ``review``, a ticket
out of contract or for another plan, a slow or failing flash router) the verdict keeps exactly the decision and the
reasons it has without the review, the review is recorded unqueued (``queued: false``), and the call is never later
than its budget allows: the router only gets what is left of the budget, at most ``router_timeout_s``.

Every test runs twice (``port_kind``): with the TEST DOUBLE ``RecordingPort`` and with ``RealPort``, the overseer
sub-project's real embedded adapter (tests/integration/helpers.py); the failing variants below are built on either."""
from __future__ import annotations

import dataclasses
import time

import pytest

from epinoic_logic.integration.delivery import verify_verdict_signature
from epinoic_logic.integration.turn import TurnChecker
from tests.integration.helpers import PORT_KINDS, VERDICT_KEY_HEX, hello, port_class, write_router_module
from tests.integration.test_turn_checker import FlippingClock, _checker, _request, _run

ASYNC = {"OVERSEER_AGENTS": "async"}


def _decision(verdict) -> tuple:
    d = verdict["delivery"]
    return d["decision"], d["reasons"], (d["deliverable"] or {}).get("agent_id"), verdict["summary"], verdict["counts"]


@pytest.fixture(params=PORT_KINDS)
def port_kind(request) -> str:
    """``double`` (the test double) or ``real`` (the overseer sub-project's embedded adapter)."""
    return request.param


def _baseline(name: str, port_kind: str = "double") -> tuple:
    verdict, _ = _run([name], port=port_class(port_kind)())  # no review at all
    return _decision(verdict)


def _variants(base: type) -> dict[str, type]:
    """The failing reviews, built on the test double or on the real adapter."""
    class RaisingReview(base):
        def review(self, hub, task_id, admission):
            raise RuntimeError("SYNTHETIC review failure")

    class RaisingRepeats(base):
        def repeats(self, hub, task_id):
            raise RuntimeError("SYNTHETIC repeats failure")

    class ExtraKeyTicket(base):
        def review(self, hub, task_id, admission):
            return dict(super().review(hub, task_id, admission), extra=1)

    class OtherPlanTicket(base):
        def review(self, hub, task_id, admission):
            t = super().review(hub, task_id, admission)
            return dict(t, plan=dict(t["plan"], plan_id="floor-of-another-request"))

    class NotAMessage(base):
        def review(self, hub, task_id, admission):
            return "not a ticket"
    return {c.__name__: c for c in (RaisingReview, RaisingRepeats, ExtraKeyTicket, OtherPlanTicket, NotAMessage)}


@pytest.mark.parametrize("name", ["hi-s1", "hi-s2"])  # a delivered answer and a refused one
@pytest.mark.parametrize("variant,origin", [("RaisingReview", "floor"), ("ExtraKeyTicket", "floor"), ("OtherPlanTicket", "floor"),
                                            ("NotAMessage", "floor"), ("RaisingRepeats", None)])
def test_a_failing_review_never_changes_the_decision_or_its_reasons(name, variant, origin, port_kind):
    port_cls = _variants(port_class(port_kind))[variant]
    verdict, port = _run([name], port=port_cls(hello_message=hello(agents="async")), **ASYNC)
    assert _decision(verdict) == _baseline(name, port_kind)
    assert verdict["overseer"]["review"] == {"queued": False, "plan_origin": origin, "plan_refusal": None, "router": None}
    assert verdict["overseer"]["refusal"] != "internal_error" and "KIT-DL-900" not in verdict["delivery"]["reasons"]


def test_the_failure_is_recorded_in_the_evidence_with_its_type_only(tmp_path, port_kind):
    import json
    ExtraKeyTicket = _variants(port_class(port_kind))["ExtraKeyTicket"]
    _run(["hi-s1"], port=ExtraKeyTicket(hello_message=hello(agents="async")), SIM_EVIDENCE_DIR=str(tmp_path / "ev"), **ASYNC)
    [path] = list((tmp_path / "ev").glob("*.json"))
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["review_error"] == {"type": "IntegrationError", "code": "KIT-OP-001"}
    assert evidence["admission"]["origin"] == "floor"


def test_a_queued_review_names_the_admitted_plan(port_kind):
    verdict, port = _run(["hi-s2"], port=port_class(port_kind)(hello_message=hello(agents="async")), **ASYNC)
    assert verdict["overseer"]["review"] == {"queued": True, "plan_origin": "floor", "plan_refusal": None, "router": None}
    assert port.reviewed[0].effective.transfers[0].reviews == 2
    assert _decision(verdict) == _baseline("hi-s2", port_kind)


def test_a_slow_router_never_holds_the_verdict_past_its_time_limit(tmp_path, monkeypatch, port_kind):
    name = write_router_module(tmp_path, monkeypatch, "slow_router_for_turns", plan_body="    time.sleep(60)\n")
    rt, port = _checker(port_class(port_kind)(hello_message=hello(agents="async")), FLASH_ROUTER=name, **ASYNC)
    assert rt.checker.router.attached
    rt.checker = TurnChecker(dataclasses.replace(rt.checker.cfg, router_timeout_s=1.0), port=port, corpus=rt.checker.corpus,
                             router=rt.checker.router, evidence_tap=rt.checker.tap)
    req, envs = _request(rt, ["hi-s1"])
    started = time.monotonic()
    verdict = rt.checker.check(req)
    took = time.monotonic() - started
    assert verify_verdict_signature(verdict, bytes.fromhex(VERDICT_KEY_HEX))
    review = verdict["overseer"]["review"]
    assert (review["queued"], review["plan_origin"], review["plan_refusal"]) == (True, "floor", "KIT-RT-016")
    assert review["router"]["name"] == "test-flash-router"
    assert _decision(verdict) == _baseline("hi-s1", port_kind)
    assert took < 20.0, f"the router's wait is bounded ({took:.1f} s for the whole call, the router cut at 1 s)"


def test_the_router_only_gets_what_is_left_of_the_budget(tmp_path, monkeypatch, port_kind):
    """With the budget spent before step 10, the router is not asked at all: the floor runs (KIT-RT-016, no time left)
    and the decision is the one the budget alone gives (the claims left are NOT_ATTEMPTED)."""
    marker = tmp_path / "asked.txt"
    name = write_router_module(tmp_path, monkeypatch, "budget_router_for_turns", plan_body=f"    open({str(marker)!r}, 'w').write('asked')\n    return '{{}}'\n")
    clock = FlippingClock()
    port = port_class(port_kind)(hello_message=hello(agents="async"))
    original = port.deliver

    def deliver(hub, task_id, *, mode, synthesis=None):
        out = original(hub, task_id, mode=mode, synthesis=synthesis)
        clock.flip()  # the budget is spent once delivery is decided: nothing is left for the router
        return out
    port.deliver = deliver
    verdict, _ = _run(["hi-s1"], port=port, clock=clock, FLASH_ROUTER=name, **ASYNC)
    review = verdict["overseer"]["review"]
    assert (review["plan_origin"], review["plan_refusal"], review["queued"]) == ("floor", "KIT-RT-016", True)
    assert not marker.exists(), "the router was never asked"
    assert _decision(verdict) == _baseline("hi-s1", port_kind)


def test_a_router_plan_is_admitted_within_the_budget_and_changes_nothing(tmp_path, monkeypatch, port_kind):
    name = write_router_module(tmp_path, monkeypatch, "fast_router_for_turns")
    verdict, port = _run(["hi-s2"], port=port_class(port_kind)(hello_message=hello(agents="async")), FLASH_ROUTER=name, **ASYNC)
    review = verdict["overseer"]["review"]
    assert (review["queued"], review["plan_origin"], review["plan_refusal"]) == (True, "router", None)
    assert _decision(verdict) == _baseline("hi-s2", port_kind)
