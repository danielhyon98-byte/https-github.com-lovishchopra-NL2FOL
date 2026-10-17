"""The overseer port ``epinoic.integration.overseer-port.v1`` (``integration/PROTOCOL.md`` section 6).

The overseer is reached only through this port, which is what lets it be a separate sub-project. The service never
imports the overseer package: it loads the port adapter named by ``EPINOIC_OVERSEER_PORT`` (a module exposing
``connect(config)``) and validates everything the adapter returns with the functions here, as untrusted data.

Operations (embedded mode, v1, over the overseer package's own calls; sidecar mode later, as messages over a local
authenticated socket):

==============  ==============================================================================================
``hello``       auditor version, pinned pack digests, key ids, replay mode (:class:`OverseerHello`)
``new_hub``     a ``RouterHub`` with a ``TransferAuditor`` attached (``KeyRing`` of the engine keys and the overseer secret)
``clearance``   ``hub.clearance`` and ``policy.act_decision`` before every action, waiting at most 250 ms
                (:class:`ClearanceDecision`)
``close``       ``hub.close_task``: the FINAL audit, signed under ``overseer-audit`` (:class:`FinalAudit`)
``deliver``     ``hub.consolidate`` + ``delivery_decision(..., hub=hub)``, or ``release_decision`` for a synthesis
                (:class:`DeliveryDecision`)
``view``        the authoritative journal view of the delivered claims (``hub.view``)
``repeats``     repeated-fault counts per answer (``hub.repeats``), an input of the flash router's request
``review``      the asynchronous overseer-agent review under an admitted routing plan (:class:`ReviewTicket`);
                never on the critical path, never a release condition
==============  ==============================================================================================

Trust rules carried over unchanged: only deterministic ``OVS-*`` findings affect clearance; ``OVS-AGENT-*`` never changes
a clearance; the auditor holds engine keys only to verify and signs under its own subkeys; every audit carries the
engine scope statement and the TR6 sentence; overseer agents are built only from the exported pack and their verdicts
are validated, never obeyed. The embedded adapter is connected in phase 2 (it is not on this tree).
"""
from __future__ import annotations

import importlib
import re
from typing import Annotated, Any, Literal, Mapping, Optional, Protocol, Sequence

from pydantic import Field, StringConstraints, ValidationError

from .canonical import CanonicalError, loads_strict
from .errors import IntegrationError
from .protocol import (
    AUDIT_SCOPE_STATEMENT, OVERSEER_REFUSALS, SCOPE_STATEMENT, AgentId, Frozen, Id, OvsCode, Sha256, Version,
)

__all__ = [
    "PORT_VERSION", "ACTABLE_STATES", "CLEARANCE_STATES", "DELIVERABLE_CONSOLIDATIONS", "MAX_PENDING_WAIT_MS",
    "AUDIT_KEY_ID", "OverseerHello", "ClearanceDecision", "FinalAudit", "DeliveryDecision", "ReviewTicket",
    "OverseerPort", "check_hello", "check_clearance", "check_final_audit", "check_delivery", "check_review_ticket",
    "load_port",
]

PORT_VERSION = "1.0"
CLEARANCE_STATES: tuple[str, ...] = ("AUDIT_FAILED", "AUDIT_PENDING", "AUDIT_PASSED_WITH_FINDINGS", "AUDIT_PASSED")
ACTABLE_STATES: frozenset[str] = frozenset({"AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"})
DELIVERABLE_CONSOLIDATIONS: frozenset[str] = frozenset({"CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS"})
#: The router may wait at most this long for a PENDING clearance; then the transfer is held (``policy.MAX_PENDING_WAIT_MS``).
MAX_PENDING_WAIT_MS = 250
AUDIT_KEY_ID = "overseer-audit"
_AGENT_CODE_RE = re.compile(r"^OVS-AGENT-")

_State = Literal["AUDIT_FAILED", "AUDIT_PENDING", "AUDIT_PASSED_WITH_FINDINGS", "AUDIT_PASSED"]
_Refusal = Literal[
    "clearance_failed", "clearance_pending", "final_audit_not_passed", "signature_invalid", "custody_failed", "stale",
    "consolidation_conflicting", "no_deliverable_output", "receipt_error_findings", "not_deliverable",
]


class OverseerHello(Frozen):
    schema_: Literal["epinoic.integration.overseer-hello.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    port_version: Literal["1.0"]
    mode: Literal["embedded", "sidecar"]
    auditor_version: Version
    pack_digests: list[Sha256] = Field(min_length=1, max_length=16)
    key_ids: list[Id] = Field(min_length=1, max_length=16)
    replay_mode: Literal["process"]
    inline_final_release: Literal[False]
    max_pending_wait_ms: int = Field(ge=1, le=MAX_PENDING_WAIT_MS)
    agents: Literal["off", "async"]
    profiles: list[Literal["standard", "fast"]] = Field(min_length=1, max_length=2)

    model_config = Frozen.model_config | {"populate_by_name": True}


class ClearanceDecision(Frozen):
    schema_: Literal["epinoic.integration.overseer-clearance.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    task_id: Id
    message_id: Id
    receipt_sha256: Sha256
    state: _State
    may_act: bool
    error_codes: list[OvsCode] = Field(default_factory=list, max_length=64)
    waited_ms: int = Field(ge=0, le=MAX_PENDING_WAIT_MS)

    model_config = Frozen.model_config | {"populate_by_name": True}


class AuditSignature(Frozen):
    alg: Literal["hmac-sha256"]
    key_id: Id
    value: Sha256


class FinalAudit(Frozen):
    schema_: Literal["epinoic.integration.overseer-final-audit.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    task_id: Id
    audit_id: Id
    channel_uid: Id
    scope: Literal["FINAL"]
    state: _State
    error_codes: list[OvsCode] = Field(default_factory=list, max_length=128)
    journal_head: Sha256
    scope_statement: Literal[SCOPE_STATEMENT]  # type: ignore[valid-type]
    audit_scope_statement: Literal[AUDIT_SCOPE_STATEMENT]  # type: ignore[valid-type]
    signature: AuditSignature

    model_config = Frozen.model_config | {"populate_by_name": True}


class ConsolidationOut(Frozen):
    id: Id
    status: Literal["CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS", "CONFLICTING", "NO_DELIVERABLE_OUTPUT"]
    basis: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class DeliverableOut(Frozen):
    agent_id: AgentId
    message_id: Id
    answer_sha256: Sha256


class DeliveryDecision(Frozen):
    schema_: Literal["epinoic.integration.overseer-delivery.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    task_id: Id
    kind: Literal["consolidation", "release"]
    allowed: bool
    refusal: Optional[_Refusal] = None
    final_audit_id: Id
    consolidation: Optional[ConsolidationOut] = None
    deliverable: Optional[DeliverableOut] = None

    model_config = Frozen.model_config | {"populate_by_name": True}


class TicketPlan(Frozen):
    origin: Literal["router", "floor"]
    plan_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
    refusal: Optional[Annotated[str, StringConstraints(pattern=r"^KIT-RT-[0-9]{3}$")]] = None


class ReviewTicket(Frozen):
    schema_: Literal["epinoic.integration.overseer-review-ticket.v1"] = Field(alias="schema")
    protocol: Literal["epinoic.integration.v1"]
    ticket_id: Id
    task_id: Id
    queued: bool
    dropped: bool
    plan: TicketPlan

    model_config = Frozen.model_config | {"populate_by_name": True}


class OverseerPort(Protocol):
    """What a port adapter offers the service (embedded: in process; sidecar: over a socket). Every return value is a
    JSON object that the service validates with the ``check_*`` functions below before acting on it."""

    def hello(self) -> Mapping[str, Any]: ...

    def new_hub(self, *, signing_key: bytes, key_id: str, verify_claim_fn: Any, config: Any) -> Any: ...

    def clearance(self, hub: Any, task_id: str, message_id: str, receipt: Any, *, wait_ms: int) -> Mapping[str, Any]: ...

    def close(self, hub: Any, task_id: str) -> Mapping[str, Any]: ...

    def deliver(self, hub: Any, task_id: str, *, mode: str, synthesis: Any = None) -> Mapping[str, Any]: ...

    def view(self, hub: Any, task_id: str) -> Any: ...

    def repeats(self, hub: Any, task_id: str) -> Mapping[str, int]: ...

    def review(self, hub: Any, task_id: str, admission: Any) -> Mapping[str, Any]: ...


def _data(raw: Any) -> dict:
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = loads_strict(raw)
        except CanonicalError as exc:
            raise IntegrationError("KIT-OP-001", f"not protocol JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise IntegrationError("KIT-OP-001", "an overseer-port message is a JSON object")
    return raw


def _agent_codes(codes: Any) -> bool:
    return isinstance(codes, list) and any(isinstance(c, str) and _AGENT_CODE_RE.match(c) for c in codes)


def _validate(model: type, data: dict, code: str = "KIT-OP-001") -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise IntegrationError(code, f"the message does not validate ({exc.error_count()} error(s))") from None


def check_hello(raw: Any) -> OverseerHello:
    data = _data(raw)
    if data.get("port_version") != PORT_VERSION:
        raise IntegrationError("KIT-OP-002", "the overseer port version is not 1.0")
    digests = data.get("pack_digests")
    if not isinstance(digests, list) or not digests or not all(isinstance(d, str) and re.fullmatch(r"[0-9a-f]{64}", d) for d in digests):
        raise IntegrationError("KIT-OP-003", "the hello names no pinned pack digest")
    if data.get("replay_mode") != "process":
        raise IntegrationError("KIT-OP-004", "the auditor replays journaled inputs in process only")
    if data.get("inline_final_release") is not False:
        raise IntegrationError("KIT-OP-005", "inline-replayed FINAL audits are never accepted for release")
    hello = _validate(OverseerHello, data)
    if AUDIT_KEY_ID not in hello.key_ids:
        raise IntegrationError("KIT-OP-012", "the hello declares no overseer-audit key id")
    return hello


def check_clearance(raw: Any, *, task_id: str, message_id: str, receipt_sha256: str) -> ClearanceDecision:
    data = _data(raw)
    if data.get("state") not in CLEARANCE_STATES:
        raise IntegrationError("KIT-OP-006", "the clearance state is not one of the four audit states")
    if _agent_codes(data.get("error_codes")):
        raise IntegrationError("KIT-OP-008", "an OVS-AGENT code never affects a clearance")
    c = _validate(ClearanceDecision, data)
    if (c.task_id, c.message_id, c.receipt_sha256) != (task_id, message_id, receipt_sha256):
        raise IntegrationError("KIT-OP-010", "the clearance is for another transfer")
    if c.may_act and (c.state not in ACTABLE_STATES or c.error_codes):
        raise IntegrationError("KIT-OP-007", "may_act is true for a state that is not passed, or with error-level findings")
    return c


def check_final_audit(raw: Any, *, task_id: str) -> FinalAudit:
    data = _data(raw)
    if data.get("scope_statement") != SCOPE_STATEMENT or data.get("audit_scope_statement") != AUDIT_SCOPE_STATEMENT:
        raise IntegrationError("KIT-OP-009", "the audit does not carry the engine scope statement and the TR6 sentence verbatim")
    sig = data.get("signature")
    if not isinstance(sig, dict) or sig.get("key_id") != AUDIT_KEY_ID or not sig.get("value"):
        raise IntegrationError("KIT-OP-012", "the FINAL audit is not signed under overseer-audit")
    if data.get("state") not in CLEARANCE_STATES:
        raise IntegrationError("KIT-OP-006", "the audit state is not one of the four audit states")
    if _agent_codes(data.get("error_codes")):
        raise IntegrationError("KIT-OP-008", "an OVS-AGENT code never decides an audit state")
    a = _validate(FinalAudit, data)
    if a.task_id != task_id:
        raise IntegrationError("KIT-OP-010", "the audit is for another task")
    if a.state in ACTABLE_STATES and a.error_codes:
        raise IntegrationError("KIT-OP-011", "a passed FINAL audit lists error-level findings")
    return a


def check_delivery(raw: Any, *, task_id: str, final_audit_id: str, answers: Sequence[tuple[str, str, str]]) -> DeliveryDecision:
    """``answers`` holds (agent_id, message_id, answer_sha256) for each answer of the call, and ("synthesis", message
    id, digest) for a synthesis: a deliverable must be one of them."""
    data = _data(raw)
    d = _validate(DeliveryDecision, data)
    if d.task_id != task_id or d.final_audit_id != final_audit_id:
        raise IntegrationError("KIT-OP-010", "the decision is for another task or another FINAL audit")
    if d.allowed != (d.refusal is None) or (d.allowed and d.deliverable is None):
        raise IntegrationError("KIT-OP-011", "an allowed decision names a deliverable and no refusal; a refused one names its refusal")
    if d.kind == "consolidation":
        if d.consolidation is None:
            raise IntegrationError("KIT-OP-011", "a consolidation decision names its consolidated response")
        if d.allowed and d.consolidation.status not in DELIVERABLE_CONSOLIDATIONS:
            raise IntegrationError("KIT-OP-011", "only CONSOLIDATED and CONSOLIDATED_WITH_FINDINGS are deliverable")
    elif d.consolidation is not None or (d.deliverable is not None and d.deliverable.agent_id != "synthesis"):
        raise IntegrationError("KIT-OP-011", "a release decision concerns the synthesis only")
    if d.deliverable is not None and (d.deliverable.agent_id, d.deliverable.message_id, d.deliverable.answer_sha256) not in set(answers):
        raise IntegrationError("KIT-OP-010", "the deliverable is not one of this call's answers")
    if d.refusal is not None and d.refusal not in OVERSEER_REFUSALS:  # pragma: no cover - the Literal already refuses it
        raise IntegrationError("KIT-OP-011", "unknown refusal label")
    return d


def check_review_ticket(raw: Any, *, task_id: str) -> ReviewTicket:
    t = _validate(ReviewTicket, _data(raw))
    if t.task_id != task_id:
        raise IntegrationError("KIT-OP-010", "the ticket is for another task")
    if t.queued and t.dropped:
        raise IntegrationError("KIT-OP-011", "a review is either queued or dropped")
    return t


def load_port(spec: Optional[str], config: Mapping[str, Any]) -> OverseerPort:
    """Connect the overseer port adapter named by ``spec`` (a module exposing ``connect(config)``). The overseer is
    required: anything that prevents a connection is ``KIT-HS-007 overseer_unavailable``, before the service binds."""
    name = (spec or "").strip()
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", name):
        raise IntegrationError("KIT-HS-007", "EPINOIC_OVERSEER_PORT names no overseer port adapter module")
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - reported as the named refusal, never a traceback
        raise IntegrationError("KIT-HS-007", f"the overseer port adapter {name!r} cannot be imported ({type(exc).__name__})") from None
    connect = getattr(module, "connect", None)
    if not callable(connect):
        raise IntegrationError("KIT-HS-007", f"the overseer port adapter {name!r} exposes no connect(config)")
    try:
        port = connect(dict(config))
    except IntegrationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IntegrationError("KIT-HS-007", f"the overseer port adapter failed to connect ({type(exc).__name__})") from None
    try:
        check_hello(port.hello())
    except IntegrationError as exc:
        raise IntegrationError("KIT-HS-007", f"the overseer's hello is out of contract ({exc.code})") from None
    return port
