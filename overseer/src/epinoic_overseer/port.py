"""The embedded overseer port adapter: ``EPINOIC_OVERSEER_PORT=epinoic_overseer.port`` (the service's default),
``connect(config)``.

The service reaches the overseer ONLY through this port (``integration/PROTOCOL.md`` section 6; the translator's
``integration/overseer_port.py`` validates every message it returns as untrusted data). It never imports this package
otherwise, and this package reaches the translator only through its public API (``epinoic_logic.api``) and the
integration protocol (``epinoic_logic.integration``).

Operations (embedded mode, v1), each over the overseer's own calls:

* ``hello()``: port version 1.0, mode ``embedded``, this release's version (``epinoic_overseer.__version__``) as the
  auditor version, the installed knowledge pack's digest (the only pack its agents are built from and its verdict intake
  accepts), the overseer's own key ids (``overseer-audit`` among them), replay mode ``process``, no inline-replayed FINAL
  release, the 250 ms bound, the agents (``off`` or ``async``) and the profiles: ``["standard"]`` (decision D30);
* ``new_hub(...)``: a ``RouterHub`` with a :class:`~epinoic_overseer.audit.TransferAuditor` attached: a key ring of the
  engine key (verification only, under the service's key id and the ids the hub's own components sign under) and the
  overseer secret's subkeys, replay in a separate process. One auditor per call (its journals die with the call); every
  call's auditor replays through the port's one replay worker, started and checked at ``connect`` (a cold worker per call
  would leave every response clearance pending past the 250 ms bound while it starts). Refused unless the service
  hands it the engine key and key id the port was connected with;
* ``clearance(...)``: ``hub.clearance`` (waiting at most 250 ms) and ``policy.act_decision``; ``receipt_sha256`` is the
  digest the journal keeps for the presented receipt (``policy.receipt_digest``: SHA-256 of its canonical JSON, the
  service's ``turn.receipt_sha256``); ``error_codes`` are the clearance's error-level ``OVS-*`` codes, never an agent's;
* ``close(...)``: ``hub.close_task``: the FINAL task audit, signed under ``overseer-audit``, with the journal head, the
  engine scope statement and the TR6 sentence verbatim;
* ``deliver(...)``: single and duplicate modes: the FINAL audit authentic and passed, then ``hub.consolidate`` and
  ``consolidate.delivery_decision(..., hub=hub)``; combined mode: ``policy.release_decision`` on the synthesis receipt.
  Every reason the overseer gives is mapped onto exactly one label of the protocol's closed refusals
  (:data:`REFUSAL_RULES`; a reason no rule maps, or two rules map, raises :class:`UnmappedReason`: the call then answers
  a signed ``KIT-DL-900`` verdict, never a silent ``not_deliverable``);
* ``view(...)``: the authoritative journal view; ``repeats(...)``: the repeated faults per transfer (message id), from
  ``hub.repeats``;
* ``review(...)``: the asynchronous overseer-agent review under the admitted routing plan (the flash router's, or the
  minimum-oversight floor's). It queues the review and returns at once with a ticket naming exactly that plan; the
  review runs after delivery on the port's review worker: the task is reviewed by as many overseer agents as the plan's
  most demanding transfer asks for (its ``instances``), every one built from the installed pack, through ``hub.review``
  (the verdict intake, validation and combination of the package). It is never a release condition and changes no
  clearance, delivery or verdict. Its outcome is kept as metadata only (decision D22: ids, plan, codes, counts).

**Agents.** ``agents: "async"`` needs a provider for the overseer agents: ``config["agent_provider_factory"]`` (agent id ->
completion provider; the simulation and the tests give one). No live provider is wired here and none has been called.
Without a factory the agents are disabled at start-up (decision D18: ``async_work_disabled``): the hello says
``agents: "off"`` and the service runs no review; it never refuses to start for it.

**The trust boundary.** Embedded, this adapter is trusted code inside the service's process and holds the overseer
secret the service also holds; it holds the engine key to verify only. Agent verdicts are advisory: only the auditor's
deterministic ``OVS-*`` findings reach a clearance or an audit.
"""
from __future__ import annotations

import hmac
import queue
import re
import threading
import time
import uuid
import weakref
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.overseer_port import AUDIT_KEY_ID as PORT_AUDIT_KEY_ID
from epinoic_logic.integration.overseer_port import MAX_PENDING_WAIT_MS as PORT_MAX_PENDING_WAIT_MS
from epinoic_logic.integration.overseer_port import PORT_VERSION
from epinoic_logic.integration.protocol import AUDIT_SCOPE_STATEMENT as PROTOCOL_AUDIT_SCOPE_STATEMENT
from epinoic_logic.integration.protocol import OVERSEER_REFUSALS, PROTOCOL
from epinoic_logic.integration.protocol import SCOPE_STATEMENT as PROTOCOL_SCOPE_STATEMENT

from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.engine import SCOPE_STATEMENT, SolverConfig, verify
from epinoic_logic.api.ir import Problem, canonical_json, problem_digest

from . import __version__
from .audit import TransferAuditor, verify_audit
from .codes import is_agent_code, severity_of
from .contracts import AUDIT_SCOPE_SENTENCE
from .keys import AUDIT_KEY_ID, AUDITOR_KEY_IDS, EngineKey, KeyRing
from .pack import installed_pack
from .policy import ACTABLE_STATES, MAX_PENDING_WAIT_MS, act_decision, receipt_digest, release_decision
from .replay import Replayer, ReplayJob

__all__ = [
    "PROFILES", "HUB_ENGINE_KEY_IDS", "REFUSAL_RULES", "UnmappedReason", "refusal_label", "ReviewRecord", "EmbeddedOverseerPort", "connect",
]

#: The overseer-agent profiles this release offers (decision D30: ``standard`` only; ``fast`` is not offered).
PROFILES: tuple[str, ...] = ("standard",)
#: The key ids, beside the service's own, that the hub's components sign engine results under with the one engine key:
#: a channel opened on its own, the engine's default and the cross-agent consistency and synthesis checks.
HUB_ENGINE_KEY_IDS: tuple[str, ...] = ("hub", "channel", "default", "integrity")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_MIN_KEY_BYTES = 32
#: How long ``connect`` gives the replay worker to start and decide its self-check.
SELF_CHECK_S = 60.0
#: Reviews waiting for the review worker; one more is dropped (its ticket says so), never queued without bound.
REVIEW_QUEUE_BOUND = 64
#: Review outcomes kept as metadata (decision D22), newest last.
REVIEW_LOG_BOUND = 1000

if AUDIT_SCOPE_SENTENCE != PROTOCOL_AUDIT_SCOPE_STATEMENT or SCOPE_STATEMENT != PROTOCOL_SCOPE_STATEMENT:  # pragma: no cover - a release defect
    raise ImportError("the overseer's scope statements are not the integration protocol's (TR6): this adapter cannot speak the port")
if AUDIT_KEY_ID != PORT_AUDIT_KEY_ID or MAX_PENDING_WAIT_MS != PORT_MAX_PENDING_WAIT_MS:  # pragma: no cover - a release defect
    raise ImportError("the overseer's audit key id or pending bound is not the port's")


# ============================================================================================ the refusal map
class UnmappedReason(RuntimeError):
    """A reason of the overseer's delivery rule that no rule of :data:`REFUSAL_RULES` maps, or that two rules map: a
    defect of this release, never a silent ``not_deliverable`` (the call answers a signed KIT-DL-900 verdict)."""


#: Every reason the overseer's ``consolidate.delivery_decision`` (with its re-check at delivery), ``policy.release_decision``
#: (with its journal coverage) and this adapter's own FINAL-audit rule give, as (pattern, label): each reason matches
#: exactly one pattern (``tests/overseer_tests/test_port_adapter.py`` reads every reason from the code). Labels are the
#: protocol's closed refusals.
REFUSAL_RULES: tuple[tuple[str, str], ...] = (
    # this adapter: the FINAL audit before anything is delivered
    (r"^the FINAL audit does not verify under the audit key$", "signature_invalid"),
    (r"^the FINAL audit is AUDIT_PENDING: not passed$", "clearance_pending"),
    (r"^the FINAL audit is AUDIT_FAILED: not passed$", "final_audit_not_passed"),
    # consolidate.delivery_decision
    (r"^not a consolidated response$", "not_deliverable"),
    (r"^the consolidated response does not verify under the consolidation key \(unsigned or edited\)$", "signature_invalid"),
    (r"^status CONFLICTING: the answers conflict and are disclosed, not chosen$", "consolidation_conflicting"),
    (r"^status (?!CONFLICTING:)[A-Z_]+: no answer may be delivered$", "no_deliverable_output"),
    (r"^answer \S+ is never delivered: it repeats a fault$", "not_deliverable"),
    (r"^answer \S+ is never delivered: it is excluded \(.*\)$", "receipt_error_findings"),
    (r"^answer \S+ is not the consolidated response's deliverable answer$", "not_deliverable"),
    (r"^the hub that issued the consolidated response is required to re-check, at delivery, that it is the latest and its answer unaltered$", "not_deliverable"),
    (r"^the hub cannot re-check the consolidated response at delivery \(\w+\)$", "custody_failed"),
    (r"^the consolidated response is not the latest this hub issued for its input: .*$", "stale"),
    (r"^a later task audit of the channel exists: the consolidation was decided on a superseded audit; consolidate again$", "stale"),
    (r"^custody of the deliverable answer could not be re-checked at delivery \(\w+\)$", "custody_failed"),
    (r"^custody re-checked at delivery: .*$", "custody_failed"),
    # policy.release_decision
    (r"^no task audit$", "final_audit_not_passed"),
    (r"^a \w+-scope audit is not a task audit$", "final_audit_not_passed"),
    (r"^the task audit is not FINAL$", "final_audit_not_passed"),
    (r"^the task audit does not verify under the audit key$", "signature_invalid"),
    (r"^the channel's audits were not given$", "not_deliverable"),
    (r"^the task audit is not the latest task audit of its channel$", "stale"),
    (r"^the task audit was superseded$", "stale"),
    (r"^task audit state AUDIT_PENDING: not passed$", "clearance_pending"),
    (r"^task audit state (?!AUDIT_PENDING:)[A-Z_]+: not passed$", "final_audit_not_passed"),
    (r"^the task audit cannot be read$", "final_audit_not_passed"),
    (r"^the FINAL audit's replays ran inline \(OVS-AUDIT-002\): .*$", "final_audit_not_passed"),
    (r"^not a receipt$", "not_deliverable"),
    (r"^the channel REJECTED the synthesis: it was not delivered$", "no_deliverable_output"),
    (r"^the synthesis receipt carries error-level findings .*$", "receipt_error_findings"),
    (r"^the task audit does not include the synthesis transfer$", "stale"),
    (r"^the synthesis transfer's state is AUDIT_PENDING: not passed$", "clearance_pending"),
    (r"^the synthesis transfer's state is (?!AUDIT_PENDING:)\S+: not passed$", "clearance_failed"),
    (r"^the transfer is not a journaled synthesis$", "not_deliverable"),
    (r"^the synthesis receipt differs from the journaled receipt$", "custody_failed"),
    (r"^the synthesis message to be released is not the journaled synthesis \(payload digest\)$", "custody_failed"),
    (r"^the synthesis message to be released cannot be compared with the journal$", "custody_failed"),
    (r"^custody of the synthesis could not be re-checked at release \(\w+\)$", "custody_failed"),
    (r"^custody re-checked at release: .*$", "custody_failed"),
    # policy._journal_covers (through release_decision)
    (r"^the audit names no journal head$", "final_audit_not_passed"),
    (r"^the journal belongs to another channel$", "custody_failed"),
    (r"^the journal chain does not verify$", "custody_failed"),
    (r"^the journal cannot be read$", "custody_failed"),
    (r"^the journal was evicted: the audit cannot be compared with it$", "custody_failed"),
    (r"^the audit's journal head is not an entry of this journal$", "custody_failed"),
    (r"^\d+ journal entr(?:y|ies) \(transfers or gaps\) after the audit: it does not cover the channel as it stands$", "stale"),
)
_RULES = tuple((re.compile(p, re.DOTALL), label) for p, label in REFUSAL_RULES)
assert all(label in OVERSEER_REFUSALS and label != "internal_error" for _p, label in REFUSAL_RULES)


def refusal_label(reason: str) -> str:
    """The protocol's refusal label for one reason of the overseer's delivery rule: exactly one rule must map it."""
    labels = [label for rx, label in _RULES if rx.match(str(reason))]
    if len(labels) != 1:
        raise UnmappedReason(f"{len(labels)} refusal rules map the reason {str(reason)[:200]!r}")
    return labels[0]


# ============================================================================================ connection
def _refuse_connect(detail: str) -> IntegrationError:
    return IntegrationError("KIT-HS-007", detail)


def connect(config: Mapping[str, Any]) -> "EmbeddedOverseerPort":
    """The port for one service (``integration/overseer_port.load_port`` calls it once, before the service binds).

    ``config``: ``engine_key`` and ``engine_key_id`` (the engine key, verification only), ``overseer_secret``,
    ``replay_mode`` (``process`` only), ``agents`` (``off`` or ``async``) and, optionally, ``agent_provider_factory``.
    Refuses (raising; start-up then reports ``KIT-HS-007``) anything else, and a replay worker that fails its self-check."""
    if not isinstance(config, Mapping):
        raise _refuse_connect("the port's configuration is not a mapping")
    if config.get("replay_mode") != "process":
        raise _refuse_connect("the overseer replays journaled inputs in a separate process only")
    agents = config.get("agents", "off")
    if agents not in ("off", "async"):
        raise _refuse_connect("the agents setting is off or async")
    engine_key, engine_key_id, secret = config.get("engine_key"), config.get("engine_key_id"), config.get("overseer_secret")
    if not isinstance(engine_key, (bytes, bytearray)) or len(engine_key) < _MIN_KEY_BYTES:
        raise _refuse_connect("the engine key is missing or shorter than 32 bytes")
    if not isinstance(engine_key_id, str) or not _KEY_ID_RE.match(engine_key_id) or engine_key_id in AUDITOR_KEY_IDS:
        raise _refuse_connect("the engine key id is missing or reserved")
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < _MIN_KEY_BYTES:
        raise _refuse_connect("the overseer secret is missing or shorter than 32 bytes")
    if hmac.compare_digest(bytes(secret), bytes(engine_key)):
        raise _refuse_connect("the overseer secret equals the engine key")
    factory = config.get("agent_provider_factory")
    if factory is not None and not callable(factory):
        raise _refuse_connect("the agent provider factory is not callable")
    port = EmbeddedOverseerPort(engine_key=bytes(engine_key), engine_key_id=engine_key_id, overseer_secret=bytes(secret), agents=agents,
                                agent_provider_factory=factory)
    problem = port.self_check()
    if problem is not None:
        port.shutdown()
        raise _refuse_connect(f"the replay worker failed its self-check ({problem})")
    return port


# ============================================================================================ per-call state
@dataclass
class _Call:
    """What the port remembers of one call's hub: the channel of each task it closed and its FINAL audit."""
    channels: dict[str, Any] = field(default_factory=dict)
    finals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewRecord:
    """The metadata of one asynchronous review (decision D22: no content)."""
    ticket_id: str
    task_id: str
    plan_origin: str
    plan_id: str
    plan_refusal: Optional[str]
    instances: int
    state: str  # queued | done | failed | dropped
    audit_id: Optional[str] = None
    verdicts_assessed: int = 0
    agent_codes: tuple[str, ...] = ()
    error: Optional[str] = None


class EmbeddedOverseerPort:
    """The adapter (module docstring). Holds the engine key to verify only, the overseer secret's key ring, the shared
    replay worker and the review worker."""

    def __init__(self, *, engine_key: bytes, engine_key_id: str, overseer_secret: bytes, agents: str = "off",
                 agent_provider_factory: Optional[Callable[[str], Any]] = None) -> None:
        self._engine_key, self._engine_key_id = engine_key, engine_key_id
        ids = {k: EngineKey(engine_key) for k in (engine_key_id, *HUB_ENGINE_KEY_IDS) if k not in AUDITOR_KEY_IDS}
        self._keyring = KeyRing(ids, overseer_secret)
        self._replayer = Replayer(self._keyring, mode="process", tasks="inline")
        self._factory = agent_provider_factory
        #: the agents the service may queue reviews for: ``async`` only with a provider (decision D18: else disabled)
        self.agents = "async" if agents == "async" and agent_provider_factory is not None else "off"
        self.notices: tuple[str, ...] = ("async_work_disabled",) if agents == "async" and agent_provider_factory is None else ()
        self._pack = installed_pack()
        self._calls: "weakref.WeakKeyDictionary[Any, _Call]" = weakref.WeakKeyDictionary()
        self._lock = threading.Lock()
        self._reviews: "queue.Queue[Any]" = queue.Queue(maxsize=REVIEW_QUEUE_BOUND)
        self._review_thread: Optional[threading.Thread] = None
        self._review_log: deque = deque(maxlen=REVIEW_LOG_BOUND)
        self._closed = False

    def __repr__(self) -> str:  # never a key
        return f"EmbeddedOverseerPort(version={__version__!r}, engine_key_id={self._engine_key_id!r}, agents={self.agents!r})"

    # ------------------------------------------------------------------------------------------------- lifecycle
    def self_check(self) -> Optional[str]:
        """Start the replay worker and replay the integration self-test's linear entailment in it: ``None`` when the
        replay answers ENTAILED (the worker is then warm for every call)."""
        try:
            from epinoic_logic.integration.selftest import PROBLEMS
            problem = Problem.model_validate(PROBLEMS["linear-entailment"][1])
            cfg = SolverConfig()
            result = verify(problem, cfg)
            if result.status.value != "ENTAILED":
                return f"the in-process run answered {result.status.value}"
            job = ReplayJob(result_id="port-self-check-" + uuid.uuid4().hex, problem_json=canonical_json(problem), config_json=canonical_json(cfg),
                            original_status=result.status.value, problem_digest=problem_digest(problem), config_digest=result.binding.config_digest,
                            versions_digest=result.binding.versions_digest, always=True)
            self._replayer.submit(job)
            self._replayer.drain(timeout_s=SELF_CHECK_S)
            out = self._replayer.outcomes().get(job.result_id)
            if out is None or out.result_json is None:
                return "no replay within the self-check's time" if out is None else (out.error or "the replay gave no result")
            import json
            status = json.loads(out.result_json).get("status")
            return None if status == "ENTAILED" else f"the replay answered {status}"
        except Exception as exc:  # noqa: BLE001 - named for the KIT-HS-007 line, never raised from here
            return type(exc).__name__

    def shutdown(self) -> None:
        """Stop the review worker and the replay worker (tests, and a service that stops)."""
        self._closed = True
        try:
            self._reviews.put_nowait(None)
        except queue.Full:
            pass
        if self._review_thread is not None:
            self._review_thread.join(timeout=10)
        self._replayer.close()

    # ------------------------------------------------------------------------------------------------- hello, hub
    def hello(self) -> dict:
        return {"schema": "epinoic.integration.overseer-hello.v1", "protocol": PROTOCOL, "port_version": PORT_VERSION, "mode": "embedded",
                "auditor_version": __version__, "pack_digests": [self._pack.identity.sha256], "key_ids": sorted(AUDITOR_KEY_IDS),
                "replay_mode": "process", "inline_final_release": False, "max_pending_wait_ms": MAX_PENDING_WAIT_MS, "agents": self.agents,
                "profiles": list(PROFILES)}

    def new_hub(self, *, signing_key: bytes, key_id: str, verify_claim_fn: Any, config: Any) -> Any:
        if not isinstance(signing_key, (bytes, bytearray)) or not hmac.compare_digest(bytes(signing_key), self._engine_key) or key_id != self._engine_key_id:
            raise IntegrationError("KIT-OP-001", "the hub must sign with the engine key and key id the port was connected with")
        auditor = TransferAuditor(self._keyring, replay_mode="process", replayer=self._replayer)
        hub = RouterHub(signing_key=bytes(signing_key), key_id=key_id, verify_claim_fn=verify_claim_fn, config=config, auditor=auditor)
        with self._lock:
            self._calls[hub] = _Call()
        return hub

    def _call(self, hub: Any) -> _Call:
        with self._lock:
            call = self._calls.get(hub)
        if call is None:
            raise IntegrationError("KIT-OP-001", "this hub was not built by this port")
        return call

    def _channel(self, hub: Any, task_id: str) -> Any:
        call = self._call(hub)
        ch = call.channels.get(task_id)
        return ch if ch is not None else hub.channel_for(task_id)

    # ------------------------------------------------------------------------------------------------- the four messages
    def clearance(self, hub: Any, task_id: str, message_id: str, receipt: Any, *, wait_ms: int) -> dict:
        wait = max(0, min(int(wait_ms), MAX_PENDING_WAIT_MS))
        started = time.monotonic()
        clr = hub.clearance(self._channel(hub, task_id), message_id, receipt=receipt, wait_ms=wait)
        waited = min(wait, int((time.monotonic() - started) * 1000))
        decision = act_decision(receipt, clr, auditor=hub.auditor)
        errors = sorted({c for c in clr.codes if not is_agent_code(c) and severity_of(c) == "error"})
        return {"schema": "epinoic.integration.overseer-clearance.v1", "protocol": PROTOCOL, "task_id": task_id, "message_id": message_id,
                "receipt_sha256": receipt_digest(receipt), "state": clr.state,
                "may_act": bool(decision.allowed) and clr.state in ACTABLE_STATES and not errors, "error_codes": errors, "waited_ms": waited}

    def close(self, hub: Any, task_id: str) -> dict:
        call = self._call(hub)
        ch = hub.channel_for(task_id)
        audit = hub.close_task(task_id)
        if audit is None or audit.journal_head is None or not audit.signature:
            raise IntegrationError("KIT-OP-001", "the task has no signed FINAL audit (nothing of it was journaled)")
        call.channels[task_id], call.finals[task_id] = ch, audit
        errors = sorted({f.code for f in audit.report.findings if f.severity == "error" and f.code.startswith("OVS-") and not is_agent_code(f.code)})
        return {"schema": "epinoic.integration.overseer-final-audit.v1", "protocol": PROTOCOL, "task_id": task_id, "audit_id": audit.audit_id,
                "channel_uid": audit.channel_uid, "scope": "FINAL", "state": audit.state, "error_codes": errors,
                "journal_head": audit.journal_head.entry_hash, "scope_statement": SCOPE_STATEMENT, "audit_scope_statement": AUDIT_SCOPE_SENTENCE,
                "signature": {"alg": "hmac-sha256", "key_id": audit.signature_key_id, "value": audit.signature}}

    def _final_refusal(self, audit: Any) -> Optional[str]:
        """This adapter's own rule before any delivery: the FINAL audit verifies under the audit key and passed."""
        if not verify_audit(audit, self._keyring):
            return "the FINAL audit does not verify under the audit key"
        if audit.state not in ACTABLE_STATES:
            return f"the FINAL audit is {audit.state}: not passed"
        return None

    def deliver(self, hub: Any, task_id: str, *, mode: str, synthesis: Any = None) -> dict:
        call = self._call(hub)
        audit, ch = call.finals.get(task_id), call.channels.get(task_id)
        if audit is None or ch is None:
            raise IntegrationError("KIT-OP-001", "deliver comes after close: the task has no FINAL audit yet")
        out = {"schema": "epinoic.integration.overseer-delivery.v1", "protocol": PROTOCOL, "task_id": task_id, "final_audit_id": audit.audit_id}
        own = self._final_refusal(audit)
        if mode in ("single", "duplicate"):
            from .consolidate import delivery_decision
            resp = hub.consolidate(ch)
            decision = delivery_decision(resp, self._keyring, hub=hub)
            reason = own if own is not None else (None if decision.allowed else decision.reason)
            group = next((g for g in resp.groups if any(m.message_id == resp.deliverable_message_id for m in g.members)), None)
            out.update(kind="consolidation", consolidation={"id": resp.consolidation_id, "status": resp.status,
                                                            "basis": group.basis if group is not None else "none"})
            if reason is not None:
                out.update(allowed=False, refusal=refusal_label(reason), deliverable=None)
                return out
            out.update(allowed=True, refusal=None, deliverable=self._deliverable(hub, ch, resp.deliverable_message_id))
            return out
        if mode == "combined":
            auditor = hub.auditor
            decision = release_decision(synthesis, audit, self._keyring, audits=auditor.audits(ch.channel_uid), journal=auditor.journal(ch.channel_uid))
            reason = own if own is not None else (None if decision.allowed else decision.reason)
            out.update(kind="release", consolidation=None)
            if reason is not None:
                out.update(allowed=False, refusal=refusal_label(reason), deliverable=None)
                return out
            view = hub.view(ch)
            t = view.by_message.get(synthesis.message_id)
            out.update(allowed=True, refusal=None, deliverable={"agent_id": "synthesis", "message_id": synthesis.message_id,
                                                                "answer_sha256": t.event.payload_sha256})
            return out
        raise IntegrationError("KIT-OP-001", f"unknown delivery mode {mode!r}")

    def _deliverable(self, hub: Any, ch: Any, message_id: str) -> dict:
        """The deliverable answer as journaled: its sender (the hub's agent id), its message id and the SHA-256 of the raw
        answer text the specialist sent (the report's ``original_response``)."""
        t = hub.view(ch).by_message.get(message_id)
        payload = t.payload if t is not None else None
        text = payload.get("original_response") if isinstance(payload, dict) else None
        if t is None or not isinstance(text, str) or not t.sender_agent_id:
            raise IntegrationError("KIT-OP-001", "the deliverable answer is not a journaled report with its text")
        return {"agent_id": t.sender_agent_id, "message_id": message_id, "answer_sha256": sha256_text(text)}

    # ------------------------------------------------------------------------------------------------- data
    def view(self, hub: Any, task_id: str) -> Any:
        return hub.view(self._channel(hub, task_id))

    def repeats(self, hub: Any, task_id: str) -> dict[str, int]:
        report = hub.repeats(self._channel(hub, task_id))
        counts: dict[str, int] = {}
        for r in report.repeats:
            counts[r.message_id] = counts.get(r.message_id, 0) + 1
        return counts

    # ------------------------------------------------------------------------------------------------- the review
    def review(self, hub: Any, task_id: str, admission: Any) -> dict:
        plan = admission.effective
        ticket = {"schema": "epinoic.integration.overseer-review-ticket.v1", "protocol": PROTOCOL, "ticket_id": f"rv-{uuid.uuid4().hex}", "task_id": task_id,
                  "queued": False, "dropped": True, "plan": {"origin": admission.origin, "plan_id": plan.plan_id, "refusal": admission.refusal}}
        instances = max([int(t.instances) for t in plan.transfers] or [1])
        record = ReviewRecord(ticket_id=ticket["ticket_id"], task_id=task_id, plan_origin=admission.origin, plan_id=plan.plan_id,
                              plan_refusal=admission.refusal, instances=instances, state="dropped")
        if self.agents != "async" or self._closed:
            self._review_log.append(record)
            return ticket
        ch = self._channel(hub, task_id)
        try:
            self._ensure_review_worker()
            self._reviews.put_nowait((hub, ch, record))
        except queue.Full:
            self._review_log.append(record)
            return ticket
        ticket.update(queued=True, dropped=False)
        return ticket

    def _ensure_review_worker(self) -> None:
        with self._lock:
            if self._review_thread is None or not self._review_thread.is_alive():
                self._review_thread = threading.Thread(target=self._review_loop, name="overseer-port-review", daemon=True)
                self._review_thread.start()

    def _review_loop(self) -> None:
        while True:
            item = self._reviews.get()
            try:
                if item is None:
                    return
                hub, ch, record = item
                self._review_log.append(self._run_review(hub, ch, record))
            finally:
                self._reviews.task_done()

    def _run_review(self, hub: Any, ch: Any, record: ReviewRecord) -> ReviewRecord:
        """Run one admitted review (after delivery; never a release condition): as many overseer agents as the plan's most
        demanding transfer asks for, each built from the installed pack with its own provider, through ``hub.review``."""
        from .runner import OverseerAgentRunner
        from dataclasses import replace
        try:
            runners = [OverseerAgentRunner(self._pack, self._factory(f"overseer-review-{i}"), agent_id=f"overseer-review-{i}", lens="general")
                       for i in range(1, record.instances + 1)]
            review = hub.review(ch, runners, mode="informed")
            codes = tuple(sorted({f.code for f in review.audit.report.findings if is_agent_code(f.code)}))
            return replace(record, state="done", audit_id=review.audit.audit_id, verdicts_assessed=len(review.assessments), agent_codes=codes)
        except Exception as exc:  # noqa: BLE001 - a failed review is recorded, never raised: it decides nothing
            return replace(record, state="failed", error=type(exc).__name__)

    def wait_for_reviews(self, timeout_s: float = 60.0) -> bool:
        """Wait until every queued review has run (tests and the simulation): True when the queue drained in time."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._reviews.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return self._reviews.unfinished_tasks == 0

    def review_log(self) -> list[ReviewRecord]:
        """The metadata of every review this port queued or dropped, oldest first (at most :data:`REVIEW_LOG_BOUND`)."""
        return list(self._review_log)
