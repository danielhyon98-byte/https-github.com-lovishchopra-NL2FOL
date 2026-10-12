"""Router hub: the primary router agent's single integration surface.

The router opens one channel per task from its work plan, dispatches requests to
any number of specialists (English, History, Psychology, Economics, Business
Management, ...), receives their raw text or structured reports back through the
branch that matches the task's subject, and reads receipts. Every message crosses
the translator channel; nothing is forwarded raw, and nothing raises into the router:
a call the hub cannot carry (a task id no plan opened, a payload that is neither text
nor a report, raw text with no stated sender) gets a REJECTED receipt that says why.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from ..engine.results import SolverConfig
from ..integrity.contracts import AgentMessage, IntegrityFinding, WorkPlan
from ..translate.contracts import SpecialistReport, SuppliedText
from ..channel.bus import TranslatorChannel, VerifyClaimFn
from ..channel.contracts import TaskRequest, TransmissionReceipt, TransmissionStatus
from .base import BranchRegistry
from .registry import default_registry

#: The agent a quarantine plan selects: no real agent is ever addressed through a task the hub did not open.
_NO_AGENT = "hub:no-agent"


class RouterHub:
    def __init__(self, *, signing_key: bytes, key_id: str = "hub", registry: Optional[BranchRegistry] = None,
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig()) -> None:
        self.registry = registry or default_registry()
        self.key, self.key_id, self.verify_claim_fn, self.config = signing_key, key_id, verify_claim_fn, config
        self.channels: dict[str, TranslatorChannel] = {}
        #: task id -> a quarantine channel that only issues REJECTED receipts for calls on a task no plan opened (never delivers)
        self._unopened: dict[str, TranslatorChannel] = {}

    def open_task(self, plan: WorkPlan) -> TranslatorChannel:
        ch = TranslatorChannel(plan, signing_key=self.key, key_id=self.key_id, verify_claim_fn=self.verify_claim_fn, config=self.config, registry=self.registry)
        self.channels[plan.task_id] = ch
        return ch

    def dispatch(self, task_id: str, to_agent_id: str, user_input: str, supplied_texts: list[SuppliedText] = (), *, from_agent_id: str = "router") -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        ch = self.channels.get(task_id) if isinstance(task_id, str) else None
        if ch is None:
            return self._dispatch_unopened(task_id, to_agent_id, user_input, supplied_texts, from_agent_id)
        return ch.request(from_agent_id, to_agent_id, user_input, list(supplied_texts))

    def receive(self, task_id: str, request_message_id: str, payload: Union[str, SpecialistReport, Mapping[str, Any], Any], *, agent_id: Optional[str] = None,
                report_id: Optional[str] = None, agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Deliver a specialist's reply through the task's channel. A report object is checked as it stands; a mapping (a report as
        JSON received over the wire) takes its sender and report id from its own fields when the call states none; any other payload
        goes to the channel's payload path (REJECTED with INT-REQ-009). Raw text needs a stated sender and report id: without them it
        is REJECTED unparsed. A task id no plan opened is REJECTED (INT-REQ-009 naming the task). Nothing raises."""
        ch = self.channels.get(task_id) if isinstance(task_id, str) else None
        if ch is None:
            return self._receive_unopened(task_id, request_message_id, payload, agent_id, report_id)
        if isinstance(payload, SpecialistReport):
            return ch.respond(request_message_id, payload)
        if isinstance(payload, Mapping):
            agent_id = agent_id if agent_id is not None else _field(payload, "agent_id")
            report_id = report_id if report_id is not None else _field(payload, "report_id")
        if not isinstance(payload, str):
            return ch.respond_text(request_message_id, payload, agent_id=str(agent_id or ""), report_id=str(report_id or ""), agent_version=agent_version)
        if agent_id is None or report_id is None:
            missing = " and ".join(x for x, v in (("agent_id", agent_id), ("report_id", report_id)) if v is None)
            return ch._withheld_payload(request_message_id if isinstance(request_message_id, str) else None, payload, agent_id=str(agent_id or ""),
                                        report_id=str(report_id or ""), branch_key=ch.branch.key,
                                        message=f"raw response text arrived with no stated {missing}; the hub cannot bind it to a sender or a report, so it was not parsed or delivered")
        return ch.respond_text(request_message_id, payload, agent_id=agent_id, report_id=report_id, agent_version=agent_version)

    def receipts(self, task_id: str) -> list[TransmissionReceipt]:
        ch = self.channels.get(task_id) or self._unopened.get(task_id)
        return list(ch.receipts) if ch is not None else []

    def branch_for(self, subject: str) -> str:
        return self.registry.for_subject(subject)[0].key

    # ------------------------------------------------------------------ calls on a task no plan opened

    def _quarantine(self, task_id: Any) -> TranslatorChannel:
        key = str(task_id)[:128] or "unopened-task"
        ch = self._unopened.get(key)
        if ch is None:
            plan = WorkPlan(plan_id="unopened-task", request_id="unopened-task", task_id=key, subject="generic", task_type="unopened", selected_agent_ids=[_NO_AGENT])
            ch = TranslatorChannel(plan, signing_key=self.key, key_id=self.key_id, verify_claim_fn=None, config=self.config, registry=self.registry)
            self._unopened[key] = ch
        return ch

    def _dispatch_unopened(self, task_id: Any, to_agent_id: Any, user_input: Any, supplied_texts, from_agent_id: Any) -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        ch = self._quarantine(task_id)
        _msg, req, first = ch.request(str(from_agent_id or "router"), str(to_agent_id or _NO_AGENT), user_input if isinstance(user_input, str) else str(user_input),
                                      [t for t in (supplied_texts or ()) if isinstance(t, SuppliedText)])
        ch.receipts.remove(first)  # the quarantine plan's own refusal is replaced by the reason that matters
        finding = IntegrityFinding(code="INT-HANDOFF-001", severity="error", message=f"no task {str(task_id)[:128]!r} is open on this hub (open_task was not called with its plan); "
                                   "the request was not sent to any agent", message_ids=[first.message_id])
        receipt = ch._receipt(first.message_id, "router_to_specialist", TransmissionStatus.REJECTED, [finding],
                              summary=f"Request REJECTED: no task {str(task_id)[:64]!r} is open on this hub; findings: INT-HANDOFF-001.")
        return None, req, receipt

    def _receive_unopened(self, task_id: Any, request_message_id: Any, payload: Any, agent_id: Optional[str], report_id: Optional[str]) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        ch = self._quarantine(task_id)
        if isinstance(payload, SpecialistReport):
            agent_id, report_id = agent_id or payload.agent_id, report_id or payload.report_id
        elif isinstance(payload, Mapping):
            agent_id, report_id = agent_id or _field(payload, "agent_id"), report_id or _field(payload, "report_id")
        msg, receipt = ch._withheld_payload(request_message_id if isinstance(request_message_id, str) else None, payload, agent_id=str(agent_id or ""),
                                            report_id=str(report_id or ""), branch_key=ch.branch.key,
                                            message=f"no task {str(task_id)[:128]!r} is open on this hub (open_task was not called with its plan); "
                                                    "the response replies to no request of it and was not delivered")
        return msg, receipt


def _field(payload: Mapping[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    return value if isinstance(value, str) else None
