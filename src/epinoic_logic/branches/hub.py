"""Router hub: the primary router agent's single integration surface.

The router opens one channel per task from its work plan, dispatches requests to
any number of specialists (English, History, Psychology, Economics, Business
Management, ...), receives their raw text or structured reports back through the
branch that matches the task's subject, and reads receipts. Every message crosses
the translator channel; nothing is forwarded raw, and nothing raises into the router:
a call the hub cannot carry (a task id no plan opened, a payload that is neither text
nor a report, raw text with no stated sender) gets a REJECTED receipt that says why.

What the hub refuses before the channel sees it:

* ``dispatch`` checks the call against the request contract (``channel.contracts.TaskRequest``):
  the request text must be text, not blank, and at most 400,000 characters; the sender and the
  recipient agent ids text of 1 to 128 characters with no lone UTF-16 surrogate; the supplied
  texts a list of at most 16 ``SuppliedText`` records. A call outside it gets a REJECTED receipt
  (INT-REQ-009 naming every fault) on a placeholder request that carries none of the refused
  input: nothing is sent, and no request is registered on the channel. A call the channel still
  cannot build into a request (its own bounds) is refused the same way, naming the error's type;
* ``receive`` refuses a stated agent or report id that is not text or is longer than 128
  characters (INT-REQ-009). Such an id is never cut to fit, because a shortened identity could
  name another agent. A reply the channel cannot carry is REJECTED with INT-REQ-009 naming the
  error's type;
* a call on a task id no plan opened is quarantined under the id's text, cut to 128 characters
  with every lone surrogate replaced, so an id that is not valid text still gets its REJECTED
  receipt (INT-HANDOFF-001 for a request, INT-REQ-009 for a reply), and ``receipts`` finds it
  under the same id.

The checks are on the call's shape only (types, lengths, valid text); they read no content and
decide nothing about the request or the answer.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Union

from ..engine.results import SolverConfig
from ..integrity.contracts import AgentMessage, AgentRole, IntegrityFinding, WorkPlan, payload_hash
from ..ir.canonical import sha256_hex
from ..translate.contracts import SpecialistReport, SuppliedText
from ..channel.bus import TranslatorChannel, VerifyClaimFn
from ..channel.contracts import TaskRequest, TransmissionReceipt, TransmissionStatus
from .base import BranchRegistry
from .registry import default_registry

#: The agent a quarantine plan selects: no real agent is ever addressed through a task the hub did not open.
_NO_AGENT = "hub:no-agent"
#: The sender a refused request names when the call stated none the contract accepts.
_NO_SENDER = "hub:unknown-sender"
#: Bounds of the request contract (``channel.contracts.TaskRequest``) the hub checks before the channel builds a request.
MAX_AGENT_ID_CHARS = 128
MAX_REQUEST_CHARS = 400_000
MAX_SUPPLIED_TEXTS = 16
#: How much of a refused identifier a finding shows.
_SHOWN_CHARS = 48
#: The text of a refused request: it names the faults, never the refused input.
_PLACEHOLDER = "(request not carried by the hub: "
_SURROGATE_RE = re.compile("[\ud800-\udfff]")


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
        """Send the router's request to a specialist through the task's channel. A call outside the request contract (module
        docstring) is REJECTED with INT-REQ-009 on a placeholder request and nothing is sent; a task id no plan opened is
        REJECTED with INT-HANDOFF-001. Nothing raises."""
        ch = self.channels.get(task_id) if isinstance(task_id, str) else None
        faults = request_faults(from_agent_id, to_agent_id, user_input, supplied_texts)
        if ch is None:
            return self._dispatch_unopened(task_id, to_agent_id, user_input, supplied_texts, from_agent_id, faults)
        if faults:
            return self._refused_request(ch, from_agent_id, to_agent_id, faults)
        try:
            return ch.request(from_agent_id, to_agent_id, user_input, list(supplied_texts))
        except Exception as exc:  # noqa: BLE001 - the channel's own bounds: refused, never raised into the router
            return self._refused_request(ch, from_agent_id, to_agent_id, [_channel_fault("request", exc)])

    def receive(self, task_id: str, request_message_id: str, payload: Union[str, SpecialistReport, Mapping[str, Any], Any], *, agent_id: Optional[str] = None,
                report_id: Optional[str] = None, agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Deliver a specialist's reply through the task's channel. A report object is checked as it stands; a mapping (a report as
        JSON received over the wire) takes its sender and report id from its own fields when the call states none; any other payload
        goes to the channel's payload path (REJECTED with INT-REQ-009). Raw text needs a stated sender and report id: without them it
        is REJECTED unparsed. A stated agent or report id that is not text or is longer than 128 characters is REJECTED (INT-REQ-009),
        never cut. A task id no plan opened is REJECTED (INT-REQ-009 naming the task). Nothing raises."""
        ch = self.channels.get(task_id) if isinstance(task_id, str) else None
        if ch is None:
            return self._receive_unopened(task_id, request_message_id, payload, agent_id, report_id)
        # a report object names its own sender and id (checked by its contract); the call's ids matter for any other payload
        faults = [] if isinstance(payload, SpecialistReport) else [f for f in (_stated_id_fault("agent", agent_id), _stated_id_fault("report", report_id)) if f]
        if faults:
            return self._refused_reply(ch, request_message_id, payload, agent_id, report_id, "the reply was not delivered: " + "; ".join(faults))
        try:
            return self._deliver(ch, request_message_id, payload, agent_id, report_id, agent_version)
        except Exception as exc:  # noqa: BLE001 - a reply the channel cannot carry is refused, never raised into the router
            return self._refused_reply(ch, request_message_id, payload, agent_id, report_id, "the reply was not delivered: " + _channel_fault("reply", exc))

    def receipts(self, task_id: str) -> list[TransmissionReceipt]:
        ch = self.channels.get(task_id) if isinstance(task_id, str) else None
        if ch is None:
            ch = self._unopened.get(_task_key(task_id))
        return list(ch.receipts) if ch is not None else []

    def branch_for(self, subject: str) -> str:
        return self.registry.for_subject(subject)[0].key

    # ------------------------------------------------------------------ delivery

    @staticmethod
    def _deliver(ch: TranslatorChannel, request_message_id: Any, payload: Any, agent_id: Optional[str], report_id: Optional[str],
                 agent_version: Optional[str]) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        if isinstance(payload, SpecialistReport):
            return ch.respond(request_message_id, payload)
        if isinstance(payload, Mapping):
            agent_id = agent_id if agent_id is not None else _field(payload, "agent_id")
            report_id = report_id if report_id is not None else _field(payload, "report_id")
        if not isinstance(payload, str):
            return ch.respond_text(request_message_id, payload, agent_id=str(agent_id or ""), report_id=str(report_id or ""), agent_version=agent_version)
        if agent_id is None or report_id is None:
            missing = " and ".join(x for x, v in (("agent_id", agent_id), ("report_id", report_id)) if v is None)
            return ch._withheld_payload(_reply_target(request_message_id), payload, agent_id=str(agent_id or ""),
                                        report_id=str(report_id or ""), branch_key=ch.branch.key,
                                        message=f"raw response text arrived with no stated {missing}; the hub cannot bind it to a sender or a report, so it was not parsed or delivered")
        return ch.respond_text(request_message_id, payload, agent_id=agent_id, report_id=report_id, agent_version=agent_version)

    # ------------------------------------------------------------------ refusals

    @staticmethod
    def _refused_request(ch: TranslatorChannel, from_agent_id: Any, to_agent_id: Any, faults: list[str], *,
                         findings: tuple[IntegrityFinding, ...] = (), summary: Optional[str] = None) -> tuple[None, TaskRequest, TransmissionReceipt]:
        """A REJECTED receipt for a request the hub does not carry: a placeholder request (the faults as its text, no items, no
        constraints, no supplied texts) is logged as the channel logs a refused request, and nothing is sent or registered."""
        sender = _usable_id(from_agent_id) or _NO_SENDER
        recipient = _usable_id(to_agent_id) or _NO_AGENT
        plan = ch.plan
        text = (_PLACEHOLDER + "; ".join(faults))[:4000] + ")"
        now = _now()
        req = TaskRequest(request_id=plan.request_id, task_id=plan.task_id, plan_id=plan.plan_id, from_agent_id=sender, to_agent_id=recipient,
                          subject=ch._subject_for(recipient), course_level=plan.course_level, task_type=ch._task_type_for(recipient),
                          user_input=text, user_input_sha256=sha256_hex(text), items=[], constraints=[], supplied_texts=[], created_at=now)
        payload = req.model_dump(mode="json", exclude_none=True)
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=req.request_id, task_id=req.task_id, sender_agent_id=sender,
                           sender_role=AgentRole.ROUTER, recipient_role=AgentRole.SPECIALIST, recipient_agent_id=recipient,
                           contract="task_request/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at=now)
        logged = ch.log.accept(msg)
        named = sorted({a for a in (_usable_id(from_agent_id), _usable_id(to_agent_id)) if a})
        refusal = IntegrityFinding(code="INT-REQ-009", severity="error", agent_ids=named, message_ids=[msg.message_id],
                                   message="the request was not sent to any agent: " + "; ".join(faults))
        stated = [f.model_copy(update={"message_ids": sorted(set(f.message_ids) | {msg.message_id})}) for f in findings]
        all_findings = [*stated, *logged, refusal]
        codes = ", ".join(dict.fromkeys(f.code for f in all_findings))
        receipt = ch._receipt(msg.message_id, "router_to_specialist", TransmissionStatus.REJECTED, all_findings,
                              summary=summary or f"Request REJECTED: the hub could not carry the call as a request ({len(faults)} fault(s)); findings: {codes}.")
        return None, req, receipt

    @staticmethod
    def _refused_reply(ch: TranslatorChannel, request_message_id: Any, payload: Any, agent_id: Any, report_id: Any,
                       message: str) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """A REJECTED receipt (INT-REQ-009, ``message``) for a reply the hub does not carry; the envelope names only usable ids."""
        if isinstance(payload, SpecialistReport):
            agent_id, report_id = agent_id or payload.agent_id, report_id or payload.report_id
        elif isinstance(payload, Mapping):
            agent_id, report_id = agent_id or _field(payload, "agent_id"), report_id or _field(payload, "report_id")
        return ch._withheld_payload(_reply_target(request_message_id), payload, agent_id=_usable_id(agent_id) or "", report_id=_usable_id(report_id) or "",
                                    branch_key=ch.branch.key, message=message)

    # ------------------------------------------------------------------ calls on a task no plan opened

    def _quarantine(self, task_id: Any) -> TranslatorChannel:
        key = _task_key(task_id)
        ch = self._unopened.get(key)
        if ch is None:
            plan = WorkPlan(plan_id="unopened-task", request_id="unopened-task", task_id=key, subject="generic", task_type="unopened", selected_agent_ids=[_NO_AGENT])
            ch = TranslatorChannel(plan, signing_key=self.key, key_id=self.key_id, verify_claim_fn=None, config=self.config, registry=self.registry)
            self._unopened[key] = ch
        return ch

    def _dispatch_unopened(self, task_id: Any, to_agent_id: Any, user_input: Any, supplied_texts, from_agent_id: Any,
                           faults: list[str]) -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        ch = self._quarantine(task_id)
        key = _task_key(task_id)
        no_task = (f"no task {key!r} is open on this hub (open_task was not called with its plan); the request was not sent to any agent")
        summary = f"Request REJECTED: no task {key[:64]!r} is open on this hub; findings: INT-HANDOFF-001"
        if not faults:
            try:
                _msg, req, first = ch.request(str(from_agent_id or "router"), str(to_agent_id or _NO_AGENT), user_input if isinstance(user_input, str) else str(user_input),
                                              [t for t in (supplied_texts or ()) if isinstance(t, SuppliedText)])
            except Exception as exc:  # noqa: BLE001 - refused below with the reason, never raised
                faults = [_channel_fault("request", exc)]
            else:
                ch.receipts.remove(first)  # the quarantine plan's own refusal is replaced by the reason that matters
                finding = IntegrityFinding(code="INT-HANDOFF-001", severity="error", message=no_task, message_ids=[first.message_id])
                receipt = ch._receipt(first.message_id, "router_to_specialist", TransmissionStatus.REJECTED, [finding], summary=summary + ".")
                return None, req, receipt
        finding = IntegrityFinding(code="INT-HANDOFF-001", severity="error", message=no_task)
        return self._refused_request(ch, from_agent_id, to_agent_id, faults, findings=(finding,), summary=summary + ", INT-REQ-009.")

    def _receive_unopened(self, task_id: Any, request_message_id: Any, payload: Any, agent_id: Optional[str], report_id: Optional[str]) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        ch = self._quarantine(task_id)
        return self._refused_reply(ch, request_message_id, payload, agent_id, report_id,
                                   f"no task {_task_key(task_id)!r} is open on this hub (open_task was not called with its plan); "
                                   "the response replies to no request of it and was not delivered")


def request_faults(from_agent_id: Any, to_agent_id: Any, user_input: Any, supplied_texts: Any) -> list[str]:
    """What keeps a ``dispatch`` call outside the request contract (module docstring), each fault named without echoing the
    refused input; empty when the channel may build the request. A request text holding a lone surrogate is left to the
    channel, which refuses it with the offsets named (INT-REQ-009)."""
    faults = [f for f in (_id_fault("sender", from_agent_id), _id_fault("recipient", to_agent_id)) if f]
    if not isinstance(user_input, str):
        faults.append(f"the request text is {_kind(user_input)}, not text")
    elif not user_input.strip():
        faults.append("the request text is empty" if not user_input else "the request text is blank (white space only)")
    elif len(user_input) > MAX_REQUEST_CHARS:
        faults.append(f"the request text has {len(user_input):,} characters, more than the {MAX_REQUEST_CHARS:,} the request contract allows")
    if not isinstance(supplied_texts, (list, tuple)):
        faults.append(f"the supplied texts are {_kind(supplied_texts)}, not a list of SuppliedText records")
    else:
        if len(supplied_texts) > MAX_SUPPLIED_TEXTS:
            faults.append(f"{len(supplied_texts)} supplied texts, more than the {MAX_SUPPLIED_TEXTS} the request contract allows")
        bad = [str(i) for i, t in enumerate(supplied_texts) if not isinstance(t, SuppliedText)]
        if bad:
            faults.append(f"the supplied text(s) at position(s) {', '.join(bad[:8])}{' and more' if len(bad) > 8 else ''} are not SuppliedText records")
    return faults


def _id_fault(role: str, value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return f"the {role} agent id is {_kind(value)}, not text"
    if not value:
        return f"the {role} agent id is empty"
    if len(value) > MAX_AGENT_ID_CHARS:
        return f"the {role} agent id has {len(value):,} characters, more than {MAX_AGENT_ID_CHARS}"
    if _SURROGATE_RE.search(value):
        return f"the {role} agent id {_shown(value)} holds a lone UTF-16 surrogate (half a character), so it is not valid text"
    return None


def _stated_id_fault(role: str, value: Any) -> Optional[str]:
    """A stated reply id the hub refuses: not text, or longer than the contract's 128 characters (never cut to fit). ``None``
    (not stated) and a lone surrogate (the channel names it) are left to the channel."""
    if value is None:
        return None
    if not isinstance(value, str):
        return f"the stated {role} id is {_kind(value)}, not text"
    if len(value) > MAX_AGENT_ID_CHARS:
        return f"the stated {role} id has {len(value):,} characters, more than {MAX_AGENT_ID_CHARS}; an id is never cut to fit, since a shortened id could name another"
    return None


def _usable_id(value: Any) -> Optional[str]:
    """``value`` when the contracts accept it as an id (text of 1 to 128 characters with no lone surrogate), else ``None``."""
    if isinstance(value, str) and 0 < len(value) <= MAX_AGENT_ID_CHARS and not _SURROGATE_RE.search(value):
        return value
    return None


def _reply_target(request_message_id: Any) -> Optional[str]:
    """The request message id an envelope may name as the message it replies to (``AgentMessage.in_reply_to``), or ``None``."""
    return _usable_id(request_message_id)


def _task_key(task_id: Any) -> str:
    """The text a task id no plan opened is quarantined and named under: its text, every lone surrogate replaced by U+FFFD,
    cut to 128 characters (a value that is not text by its text form, or its type when it has none)."""
    if isinstance(task_id, str):
        text = task_id
    else:
        try:
            text = str(task_id)
        except Exception:  # noqa: BLE001 - a value whose text form raises is named by its type
            text = f"<{type(task_id).__name__}>"
    return _SURROGATE_RE.sub("�", text)[:MAX_AGENT_ID_CHARS] or "unopened-task"


def _channel_fault(what: str, exc: BaseException) -> str:
    return f"the channel could not carry the {what} ({type(exc).__name__}); nothing was sent or delivered"


def _kind(value: Any) -> str:
    return "None" if value is None else f"a value of type {type(value).__name__}"


def _shown(value: str) -> str:
    text = _SURROGATE_RE.sub("�", value)
    return repr(text[:_SHOWN_CHARS] + ("…" if len(text) > _SHOWN_CHARS else ""))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _field(payload: Mapping[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    return value if isinstance(value, str) else None
