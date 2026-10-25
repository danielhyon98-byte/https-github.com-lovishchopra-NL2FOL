"""Round-7 hand-off (robustness) on the hub: a task id that is not valid Unicode is REJECTED, never raised.

``RouterHub.dispatch("\\ud83d", ...)`` and ``RouterHub.receive("\\ud83d", ...)`` raised a pydantic ``ValidationError``
from ``WorkPlan(task_id=key)`` in the quarantine of a task no plan opened (a lone surrogate is no valid string). The
quarantine key of such an id is now a digest of it, so both calls return a REJECTED receipt naming the task (the id
written escaped), its receipts stay readable under the same id, and ids that worked before keep their quarantine."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.contracts import TransmissionStatus

KEY = b"r7-hub-handoff-test-key-0123456789abcdef"
HI_Q = "Explain the significance of the Factory Act of 1833. Write no more than 120 words."
HI_A = "The Factory Act of 1833 banned the employment of children under nine in textile mills."


@pytest.mark.parametrize("task_id", ["\ud83d", "\udc00", "task-\ud83d-7", "\ud83d" * 300], ids=["high", "low", "inside", "long"])
def test_a_task_id_holding_a_lone_surrogate_is_rejected_and_never_raises(task_id):
    hub = RouterHub(signing_key=KEY)
    try:
        m, req, rc = hub.dispatch(task_id, "history-specialist", HI_Q)
        assert m is None and rc.status is TransmissionStatus.REJECTED and [f.code for f in rc.findings] == ["INT-HANDOFF-001"]
        assert "is open on this hub" in rc.findings[0].message and req.to_agent_id == "history-specialist"
        rc.model_dump_json()  # the receipt is valid Unicode: the id is written escaped
        r2, rc2 = hub.receive(task_id, "msg", HI_A, agent_id="history-specialist", report_id="rep-x")
        assert r2 is None and rc2.status is TransmissionStatus.REJECTED
        assert any(f.code == "INT-REQ-009" and "is open on this hub" in f.message for f in rc2.findings)
        r3, rc3 = hub.receive(task_id, "msg", {"agent_id": "history-specialist", "report_id": "rep-y"})
        assert r3 is None and rc3.status is TransmissionStatus.REJECTED
        rc2.model_dump_json()
        assert len(hub.receipts(task_id)) == 3
        assert task_id not in hub.channels
    finally:
        hub.close()


def test_control_ids_that_worked_before_keep_their_quarantine():
    hub = RouterHub(signing_key=KEY)
    try:
        for tid in ("no-such-task", None, 5, "x" * 500):
            m, _req, rc = hub.dispatch(tid, "history-specialist", HI_Q)
            assert m is None and rc.status is TransmissionStatus.REJECTED and [f.code for f in rc.findings] == ["INT-HANDOFF-001"]
        assert len(hub.receipts("no-such-task")) == 1 and hub.receipts("never-seen") == []
        assert hub._quarantine_key("no-such-task") == "no-such-task" and hub._quarantine_key("x" * 500) == "x" * 128
        assert hub._quarantine_key("\ud83d").startswith("sha256:") and hub._quarantine_key("\ud83d") != hub._quarantine_key("\udc00")
    finally:
        hub.close()
