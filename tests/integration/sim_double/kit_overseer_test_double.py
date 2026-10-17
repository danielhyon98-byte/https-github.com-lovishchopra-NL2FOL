"""TEST DOUBLE of the overseer port adapter, for the simulation's WIRING test only (integration/sim/README.md).

``run_sim.py --test-overseer-port kit_overseer_test_double --test-pythonpath <this directory>:<repository root>`` starts
the checks service with this module as ``EPINOIC_OVERSEER_PORT``, so the drivers, the evidence tap and the gates can be
exercised end to end before the rebuilt overseer's adapter exists. It is ``tests/integration/helpers.RecordingPort``
(fixture clearances, a FINAL audit that passes, a delivery that allows the first reply of the task), kept per task. It
audits nothing: ``run_sim.py`` therefore reports every gate NOT RUN when this double is attached ("the overseer port is a
test double"), and lists what the gates computed only as a sub-check. It is not part of any package, its hello names it
(``auditor_version`` 0.0.0-test-double), and nothing outside the tests imports it.
"""
from __future__ import annotations

from typing import Any

from tests.integration.helpers import RecordingPort, hello

AUDITOR_VERSION = "0.0.0-test-double"


class PerTaskRecordingPort(RecordingPort):
    """``RecordingPort`` whose delivery reads only the replies of the call it is asked about: the hub's plan names the
    call's request id, and every reply carries it (one long-lived service runs many calls, some for the same task: a
    re-armed retry is a new attempt of the same turn; the base double serves one test's single call)."""

    def deliver(self, hub: Any, task_id: str, *, mode: str, synthesis: Any = None) -> dict:
        channel = hub.channels.get(task_id)
        request_id = channel.plan.request_id if channel is not None else None
        mine = [(reply, rc) for reply, rc in self.replies if reply is not None and reply.task_id == task_id and reply.request_id == request_id]
        kept, self.replies = self.replies, mine
        try:
            return super().deliver(hub, task_id, mode=mode, synthesis=synthesis)
        finally:
            self.replies = kept


def connect(config: Any) -> PerTaskRecordingPort:
    return PerTaskRecordingPort(hello_message=hello(auditor_version=AUDITOR_VERSION, agents=str(config.get("agents") or "off")))
