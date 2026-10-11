"""Router hub: the primary router agent's single integration surface.

The router opens one channel per task from its work plan, dispatches requests to
any number of specialists (English, History, Psychology, Economics, Business
Management, ...), receives their raw text or structured reports back through the
branch that matches the task's subject, and reads receipts. Every message crosses
the translator channel; nothing is forwarded raw.
"""
from __future__ import annotations

from typing import Optional, Union

from ..engine.results import SolverConfig
from ..integrity.contracts import AgentMessage, WorkPlan
from ..translate.contracts import SpecialistReport, SuppliedText
from ..channel.bus import TranslatorChannel, VerifyClaimFn
from ..channel.contracts import TaskRequest, TransmissionReceipt
from .base import BranchRegistry
from .registry import default_registry


class RouterHub:
    def __init__(self, *, signing_key: bytes, key_id: str = "hub", registry: Optional[BranchRegistry] = None,
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig()) -> None:
        self.registry = registry or default_registry()
        self.key, self.key_id, self.verify_claim_fn, self.config = signing_key, key_id, verify_claim_fn, config
        self.channels: dict[str, TranslatorChannel] = {}

    def open_task(self, plan: WorkPlan) -> TranslatorChannel:
        ch = TranslatorChannel(plan, signing_key=self.key, key_id=self.key_id, verify_claim_fn=self.verify_claim_fn, config=self.config, registry=self.registry)
        self.channels[plan.task_id] = ch
        return ch

    def dispatch(self, task_id: str, to_agent_id: str, user_input: str, supplied_texts: list[SuppliedText] = (), *, from_agent_id: str = "router") -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        return self.channels[task_id].request(from_agent_id, to_agent_id, user_input, list(supplied_texts))

    def receive(self, task_id: str, request_message_id: str, payload: Union[str, SpecialistReport], *, agent_id: Optional[str] = None,
                report_id: Optional[str] = None, agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        ch = self.channels[task_id]
        if isinstance(payload, SpecialistReport):
            return ch.respond(request_message_id, payload)
        if agent_id is None or report_id is None:
            raise ValueError("agent_id and report_id are required for raw text")
        return ch.respond_text(request_message_id, payload, agent_id=agent_id, report_id=report_id, agent_version=agent_version)

    def receipts(self, task_id: str) -> list[TransmissionReceipt]:
        return list(self.channels[task_id].receipts)

    def branch_for(self, subject: str) -> str:
        return self.registry.for_subject(subject)[0].key
