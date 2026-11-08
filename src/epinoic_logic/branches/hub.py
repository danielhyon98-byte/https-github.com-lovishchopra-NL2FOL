"""Router hub: the primary router agent's single integration surface.

The router opens one channel per task from its work plan, dispatches requests to
any number of specialists (English, History, Psychology, Economics, Business
Management, ...), receives their raw text or structured reports back through the
branch that matches the task's subject, and reads receipts. Every message crosses
the translator channel; nothing is forwarded raw, and nothing raises into the router:
a call the hub cannot carry (a task id no plan opened, or one ``close_task`` closed, a
payload that is neither text nor a report, raw text with no stated sender) gets a
REJECTED receipt that says why. A hub the router itself closed (``close()``) refuses new
tasks and transfers with :class:`HubClosed`.

Observation and the Overseer (optional; ``docs/OVERSEER_DESIGN.md`` sections 4, 5.3, 7 and 9-10). A hub built without
``observers`` and ``auditor`` opens channels with no observer, and they behave exactly as before.

* ``observers=``: generic channel observers attached to every channel the hub opens (``TranslatorChannel.add_observer``).
* ``auditor=``: the overseer's transfer auditor (``epinoic_overseer.TransferAuditor``, the separate sub-project ``overseer/``,
  which this package never imports), attached FIRST to every channel the hub opens, so the authoritative journal is written
  before any other observer runs. It also enables the overseer methods below; the ones that run the overseer's own
  rules (``clearance``, ``repeats``, ``consolidate``, ``review_pool`` and ``review``) are carried out by the auditor's
  ``hub_operations`` (``epinoic_overseer.hub_ops``), to which the hub hands itself, and every one of them refuses with
  :class:`AuditorNotAttached` first when no auditor is attached:

  - ``clearance(task_key, message_id, receipt=None, wait_ms=0)``: the router's check immediately before acting on a
    transfer: custody of the message and its dependencies re-checked, the receipt the router presents (or the
    channel's) compared with the journal; ``wait_ms`` is clamped to ``policy.MAX_PENDING_WAIT_MS`` and bounds the
    whole wait for outstanding replay and re-derivation. Act only when ``policy.may_act(receipt, clearance)`` (the clearance
    must still be the auditor's latest word on the transfer);
  - ``audit(task_key, final=False, shadow=None)``: the signed task audit (scope ``task``);
  - ``view(task_key)``: the authoritative view of the channel, from its journal;
  - ``review(task_key, runners, mode="informed")``: overseer agents review the task. Each runner is an
    ``OverseerAgentRunner`` built from a loaded knowledge pack; the hub issues each one a dossier under ITS pack (all
    dossiers are issued before any agent runs), runs each once, and every reply goes through the verdict intake,
    validation and combination. It returns the signed ``verdicts``-scope audit inside a :class:`HubReview`. Agents
    never gate clearance: ``OVS-AGENT-*`` findings change no clearance, and a confirmed accusation acts only through
    the auditor's own ``OVS-*`` finding;
  - ``consolidate(task_key, request_message_ids=None, user_input_sha256=None)``: when several agents (duplicated
    instances of one specialist, or several specialists) answered the same input, the ONE consolidated response for the
    router (``overseer/consolidate.py``, contract ``consolidated_response/1.0``, signed under the consolidation key):
    equivalent answers grouped deterministically, a representative per group, every answer with an error-level finding
    or a repeated fault excluded (naming its codes and signed results), conflicts between groups disclosed. It reads the
    journal and the signed task audit, records the response (``consolidations``), and the router delivers through
    ``consolidate.delivery_decision(resp, keyring, hub=self)`` only (the hub re-checks at delivery that the response is
    its latest for that input, its task audit current and the deliverable answer's custody intact). ``repeats(task_key)`` is the task's repeat report (every channel the hub
    opened for that task id, in order);
  - ``review_pool(task_keys, pool, mode=None)``: a self-duplicating review of a batch of tasks: the
    ``overseer.pool.OverseerPool`` plans deterministically how many instances (one by default, more for a batch over the
    per-instance quota or with repeated faults, never past its maximum), every repeated-fault dossier goes to two
    independent instances, and each task is reviewed through ``review`` by the instances its plan assigns, the plan
    recorded in the signed verdicts audit. Instances are overseer agents: they never certify anything or change a status;
  - ``close_task(task_key)``: the channel leaves ``channels`` for ``closed_channels``, its FINAL task audit is issued
    and its journal sealed (a later transfer on it is reported, CUST-003);
  - ``close()``: stops the auditor's replay worker (process mode) when the last hub using that auditor closes.
    The worker starts with the first replay job. ``RouterHub`` is a context manager.

* ``open_task`` never loses a channel: a channel it would replace (a task id opened again) is kept in
  ``closed_channels`` (keyed by ``channel_uid``, at most :data:`MAX_CLOSED_CHANNELS`, oldest dropped first), its
  journal continues and it can still be audited (``audit(channel)``, ``audit(channel_uid)``). It is not sealed, so a
  router that puts it back under its key by hand (the arena does) keeps using it with its journal intact.

``task_key`` is a key of ``channels`` (a task id, or the key a router registered by hand), the ``channel_uid`` of a
channel in ``closed_channels``, or a channel this hub opened. Every Overseer method raises
:class:`AuditorNotAttached` without an auditor: nothing is ever shown as passed without one.

Deviations from ``docs/OVERSEER_DESIGN.md`` (stage ``hook``), listed as each stage requires:

* ``review`` returns a :class:`HubReview` whose ``audit`` is the signed ``verdicts``-scope audit; it also carries the
  reference task audit, the runs, the assessments, the combination and the refusals. The verdicts audit copies the
  state and transfer states of the auditor's latest task audit after validation (a targeted re-run may have issued a
  superseding one from the auditor's own findings), never anything an agent said, and it carries the intake's
  AGENT-005 findings for replies the intake rejected;
* ``review`` first takes a reference task audit with the shadow run: the latest signed task audit when it verifies,
  covers every journaled transfer and ran the shadow, else a new one. Validation's targeted re-run then has nothing
  left to discover from journaled inputs, so a review changes no clearance unless a live object was altered after the
  audit (then the auditor's own custody finding does);
* the hub's verdict intake (``intake=``, else created at the first review) accepts the installed pack's identity
  (``installed_pack().identity``); a runner configured with another pack is refused a dossier (``pack_unknown``), and
  only ``OverseerAgentRunner`` instances (configured from a loaded pack; not subclasses, which could change how a reply
  reaches the intake) are accepted as agents. A runner that raises is recorded in ``runner_errors`` as no review;
* the hub checks at construction that the auditor holds the hub's engine key under the hub's key id (a hub whose
  results the auditor cannot verify would fail every transfer), and ``closed_channels`` is bounded;
* ``clearance`` waits for the replayer itself under one deadline and then asks the auditor with ``wait_ms=0``: the
  auditor's own wait bounds replay and re-derivation separately, which could add up past the 250 ms of design section 7.

Consolidation stage (design section 19), listed as each stage requires: ``consolidate``, ``consolidations``, ``repeats``
and ``review_pool`` are added; ``review`` takes ``pool_plan=`` (the runners must be exactly the instances the plan assigns
to that task, under the plan's pack, and the plan is recorded in the verdicts audit's notes) and shows the channel's
latest consolidated response per input in informed dossiers (none in blind mode; a channel never consolidated issues
exactly the dossiers it issued before). A hub that never calls these behaves exactly as before.
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

from ..engine.results import SolverConfig
from ..integrity.contracts import AgentMessage, IntegrityFinding, WorkPlan
from ..translate.contracts import SpecialistReport, SuppliedText
from ..channel.bus import ChannelObserver, TranslatorChannel, VerifyClaimFn
from ..channel.contracts import TaskRequest, TransmissionReceipt, TransmissionStatus
from .base import BranchRegistry
from .registry import default_registry

#: Most channels ``closed_channels`` keeps (oldest dropped first; a dropped channel's journal stays with the auditor).
MAX_CLOSED_CHANNELS = 1024
#: The agent a quarantine plan selects: no real agent is ever addressed through a task the hub did not open.
_NO_AGENT = "hub:no-agent"
#: What an attached auditor provides (the overseer's ``TransferAuditor``; ``hub_operations`` carries out the overseer methods).
_AUDITOR_METHODS = ("observer_for", "clearance", "audit", "view", "audits", "journal", "channel_uids", "seal", "close", "keyring", "store", "replayer",
                    "hub_operations")

# Hubs attached to each auditor: the replay worker stops when the last of them closes.
_AUDITOR_HUBS: "weakref.WeakKeyDictionary[Any, int]" = weakref.WeakKeyDictionary()
_AUDITOR_LOCK = threading.Lock()


class AuditorNotAttached(RuntimeError):
    """An Overseer method of a hub built without ``auditor=``: nothing is shown as passed without an auditor."""


class HubClosed(RuntimeError):
    """A transfer or a new task on a hub that was closed."""


@dataclass(frozen=True)
class HubReview:
    """What one ``RouterHub.review`` did. ``audit`` is the signed ``verdicts``-scope audit; nothing here confirms,
    passes or clears a transfer (only the auditor's own ``OVS-*`` findings do). ``twofold`` is the N_FOLD review of a
    combined answer (the overseer's ``twofold.TwofoldReview``: each source's review, the temporary context as recorded
    and the merged review) when the pool plan reviewed the task that way, else ``None``."""
    audit: Any
    task_audit: Any
    mode: str
    runs: tuple[Any, ...]
    assessments: tuple[Any, ...]
    combined: Optional[Any]
    refused: tuple[tuple[str, str], ...]
    runner_errors: tuple[tuple[str, str], ...]
    superseding_audit_ids: tuple[str, ...]
    twofold: Optional[Any] = None


@dataclass(frozen=True)
class PoolReview:
    """What one ``RouterHub.review_pool`` did: the recorded plan and, per dossier key (the channel uid), the
    :class:`HubReview` of the instances the plan assigned. Nothing here confirms, passes or clears a transfer."""
    plan: Any
    reviews: dict[str, HubReview]
    task_keys: dict[str, Any]


def _same_subkeys(a: Any, b: Any) -> bool:
    return a is b or all(hmac.compare_digest(a.subkey(label), b.subkey(label)) for label in ("audit", "intake", "runs", "journal"))


class RouterHub:
    def __init__(self, *, signing_key: bytes, key_id: str = "hub", registry: Optional[BranchRegistry] = None,
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig(),
                 observers: Sequence[ChannelObserver] = (), auditor: Optional[Any] = None,
                 intake: Optional[Any] = None) -> None:
        self.registry = registry or default_registry()
        self.key, self.key_id, self.verify_claim_fn, self.config = signing_key, key_id, verify_claim_fn, config
        self.channels: dict[str, TranslatorChannel] = {}
        #: task id -> a quarantine channel that only issues REJECTED receipts for calls on a task no plan opened (never delivers)
        self._unopened: dict[str, TranslatorChannel] = {}
        observers = tuple(observers)
        for o in observers:
            if not callable(o):
                raise TypeError(f"a channel observer must be callable, not {type(o).__name__}")
        self.observers: tuple[ChannelObserver, ...] = observers
        self.closed_channels: "OrderedDict[str, TranslatorChannel]" = OrderedDict()
        self._lock = threading.RLock()
        self._closed = False
        self.auditor: Optional[Any] = None
        self.intake: Optional[Any] = None
        self._consolidations: dict[str, list[Any]] = {}
        if auditor is not None:
            missing = [m for m in _AUDITOR_METHODS if not hasattr(auditor, m)]
            if missing:
                raise TypeError(f"auditor must be a TransferAuditor (missing {missing})")
            held = auditor.keyring.verification_key(key_id)
            if held is None or not hmac.compare_digest(held, signing_key):
                raise ValueError(f"the auditor does not hold the hub's engine key under key id {key_id!r}: it could verify none of the hub's results")
            self.auditor = auditor
            with _AUDITOR_LOCK:
                _AUDITOR_HUBS[auditor] = _AUDITOR_HUBS.get(auditor, 0) + 1
        if intake is not None:
            if self.auditor is None:
                raise ValueError("a verdict intake needs the hub's auditor")
            if not _same_subkeys(intake.keyring, self.auditor.keyring):
                raise ValueError("the intake and the auditor are configured with different overseer secrets")
            self.intake = intake

    # ------------------------------------------------------------------ tasks and transfers
    def _check_open(self) -> None:
        if self._closed:
            raise HubClosed("this hub is closed")

    def open_task(self, plan: WorkPlan) -> TranslatorChannel:
        self._check_open()
        ch = TranslatorChannel(plan, signing_key=self.key, key_id=self.key_id, verify_claim_fn=self.verify_claim_fn, config=self.config, registry=self.registry)
        if self.auditor is not None:
            ch.add_observer(self.auditor.observer_for(ch))
        for obs in self.observers:
            ch.add_observer(obs)
        with self._lock:
            old = self.channels.get(plan.task_id)
            if old is not None and old is not ch:
                self._retire(old)
            self.channels[plan.task_id] = ch
        return ch

    def dispatch(self, task_id: str, to_agent_id: str, user_input: str, supplied_texts: list[SuppliedText] = (), *, from_agent_id: str = "router") -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        self._check_open()
        ch = self.channels.get(task_id) if isinstance(task_id, str) else None
        if ch is None:
            return self._dispatch_unopened(task_id, to_agent_id, user_input, supplied_texts, from_agent_id)
        return ch.request(from_agent_id, to_agent_id, user_input, list(supplied_texts))

    def receive(self, task_id: str, request_message_id: str, payload: Union[str, SpecialistReport, Mapping[str, Any], Any], *, agent_id: Optional[str] = None,
                report_id: Optional[str] = None, agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Deliver a specialist's reply through the task's channel. A report object is checked as it stands; a mapping (a report as
        JSON received over the wire) takes its sender and report id from its own fields when the call states none; any other payload
        goes to the channel's payload path (REJECTED with INT-REQ-009). Raw text needs a stated sender and report id: without them it
        is REJECTED unparsed. A task id no plan opened (or one ``close_task`` closed) is REJECTED (INT-REQ-009 naming the task).
        Nothing raises, except :class:`HubClosed` on a hub the router closed."""
        self._check_open()
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
        if ch is None and isinstance(task_id, str) and task_id and self._quarantine_key(task_id).startswith("sha256:"):
            ch = self._unopened.get(self._quarantine_key(task_id))  # a task id that is not valid Unicode is quarantined under its digest
        return list(ch.receipts) if ch is not None else []

    def branch_for(self, subject: str) -> str:
        return self.registry.for_subject(subject)[0].key

    # ------------------------------------------------------------------ calls on a task no plan opened
    def _closed_task(self, task_id: Any) -> bool:
        """Whether ``task_id`` names a task this hub opened and ``close_task`` closed (its channel kept in ``closed_channels``)."""
        with self._lock:
            return isinstance(task_id, str) and task_id not in self.channels and any(c.plan.task_id == task_id for c in self.closed_channels.values())

    def _no_task_reason(self, task_id: Any) -> str:
        if self._closed_task(task_id):
            return f"task {str(task_id)[:128]!r} was closed on this hub (close_task); its channel takes no new transfer"
        return f"no task {str(task_id)[:128]!r} is open on this hub (open_task was not called with its plan)"

    @staticmethod
    def _quarantine_key(task_id: Any) -> str:
        """The key of the quarantine channel of a task id no plan opened: the id's first 128 characters, or, for an id
        that is not valid Unicode (a lone surrogate), a digest of it, so the quarantine plan is always a valid
        WorkPlan and the call returns a REJECTED receipt instead of raising."""
        key = str(task_id)[:128] or "unopened-task"
        try:
            key.encode("utf-8")
        except UnicodeEncodeError:
            key = "sha256:" + hashlib.sha256(key.encode("utf-8", "surrogatepass")).hexdigest()[:16]
        return key

    def _quarantine(self, task_id: Any) -> TranslatorChannel:
        key = self._quarantine_key(task_id)
        ch = self._unopened.get(key)
        if ch is None:
            plan = WorkPlan(plan_id="unopened-task", request_id="unopened-task", task_id=key, subject="generic", task_type="unopened", selected_agent_ids=[_NO_AGENT])
            ch = TranslatorChannel(plan, signing_key=self.key, key_id=self.key_id, verify_claim_fn=None, config=self.config, registry=self.registry)
            self._unopened[key] = ch
        return ch

    def _dispatch_unopened(self, task_id: Any, to_agent_id: Any, user_input: Any, supplied_texts, from_agent_id: Any) -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        reason = self._no_task_reason(task_id)
        ch = self._quarantine(task_id)
        _msg, req, first = ch.request(str(from_agent_id or "router"), str(to_agent_id or _NO_AGENT), user_input if isinstance(user_input, str) else str(user_input),
                                      [t for t in (supplied_texts or ()) if isinstance(t, SuppliedText)])
        ch.receipts.remove(first)  # the quarantine plan's own refusal is replaced by the reason that matters
        finding = IntegrityFinding(code="INT-HANDOFF-001", severity="error", message=f"{reason}; the request was not sent to any agent", message_ids=[first.message_id])
        short = (f"task {str(task_id)[:64]!r} was closed on this hub" if self._closed_task(task_id)
                 else f"no task {str(task_id)[:64]!r} is open on this hub")
        receipt = ch._receipt(first.message_id, "router_to_specialist", TransmissionStatus.REJECTED, [finding],
                              summary=f"Request REJECTED: {short}; findings: INT-HANDOFF-001.")
        return None, req, receipt

    def _receive_unopened(self, task_id: Any, request_message_id: Any, payload: Any, agent_id: Optional[str], report_id: Optional[str]) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        reason = self._no_task_reason(task_id)
        ch = self._quarantine(task_id)
        if isinstance(payload, SpecialistReport):
            agent_id, report_id = agent_id or payload.agent_id, report_id or payload.report_id
        elif isinstance(payload, Mapping):
            agent_id, report_id = agent_id or _field(payload, "agent_id"), report_id or _field(payload, "report_id")
        msg, receipt = ch._withheld_payload(request_message_id if isinstance(request_message_id, str) else None, payload, agent_id=str(agent_id or ""),
                                            report_id=str(report_id or ""), branch_key=ch.branch.key,
                                            message=f"{reason}; the response replies to no request of it and was not delivered")
        return msg, receipt

    def _retire(self, ch: TranslatorChannel) -> None:
        """Keep a channel the hub no longer routes to under its key (replaced or closed): never lost, still auditable."""
        with self._lock:
            uid = ch.channel_uid
            self.closed_channels.pop(uid, None)
            self.closed_channels[uid] = ch
            while len(self.closed_channels) > MAX_CLOSED_CHANNELS:
                self.closed_channels.popitem(last=False)

    def close_task(self, task_key: str, *, audit: bool = True) -> Optional[Any]:
        """Stop routing to the task's channel: it moves to ``closed_channels``; with an auditor, its FINAL task audit is
        issued (when ``audit`` and anything was journaled) and its journal is sealed. Returns that audit, or None."""
        with self._lock:
            ch = self.channels.pop(task_key)
            for key, other in list(self.channels.items()):  # the same channel registered under another key by hand
                if other is ch:
                    del self.channels[key]
            self._retire(ch)
        if self.auditor is None:
            return None
        uid = ch.channel_uid
        result = None
        if audit and uid in self.auditor.channel_uids():
            result = self.auditor.audit(uid, final=True)
        self.auditor.seal(uid, "hub.close_task")
        return result

    # ------------------------------------------------------------------ the Overseer
    def _require_auditor(self) -> Any:
        if self.auditor is None:
            raise AuditorNotAttached("this hub has no auditor: build it with auditor=TransferAuditor(...) to audit, clear or review transfers")
        return self.auditor

    def _operations(self) -> Any:
        """The attached auditor's ``hub_operations`` (raises :class:`AuditorNotAttached` without an auditor)."""
        return self._require_auditor().hub_operations

    def _review_intake(self) -> Any:
        """The verdict intake this hub's reviews issue dossiers from (the attached auditor's, through its ``hub_operations``)."""
        return self._operations()._review_intake(self)

    def _resolve(self, task_key: Any) -> TranslatorChannel:
        with self._lock:
            if isinstance(task_key, TranslatorChannel):
                if any(c is task_key for c in self.channels.values()) or self.closed_channels.get(task_key.channel_uid) is task_key:
                    return task_key
                raise KeyError("the channel was not opened by this hub")
            if isinstance(task_key, str):
                ch = self.channels.get(task_key)
                if ch is None:
                    ch = self.closed_channels.get(task_key)
                if ch is not None:
                    return ch
            raise KeyError(task_key)

    def channel_for(self, task_key: Any) -> TranslatorChannel:
        """The channel ``task_key`` names (a key of ``channels``, a ``closed_channels`` uid, or a channel of this hub)."""
        return self._resolve(task_key)

    def _journaled_uid(self, auditor: Any, ch: TranslatorChannel) -> str:
        uid = ch.channel_uid
        if uid not in auditor.channel_uids():
            raise LookupError(f"nothing of channel {uid} (task {ch.plan.task_id!r}) was journaled: there is nothing to audit")
        return uid

    def journaled_uid(self, auditor: Any, ch: TranslatorChannel) -> str:
        """``ch``'s uid when ``auditor`` journaled anything of it, else ``LookupError`` (a hook of the overseer's operations)."""
        return self._journaled_uid(auditor, ch)

    def clearance(self, task_key: Any, message_id: str, *, receipt: Any = None, wait_ms: int = 0) -> Any:
        """The router's check immediately before acting on a transfer (see the module docstring), carried out by the
        auditor's ``hub_operations``. ``wait_ms`` is clamped to ``policy.MAX_PENDING_WAIT_MS`` and bounds the whole wait
        (replay and re-derivation together). A channel of which nothing was journaled clears nothing (AUDIT_FAILED,
        CUST-003)."""
        return self._operations().clearance(self, task_key, message_id, receipt=receipt, wait_ms=wait_ms)

    def audit(self, task_key: Any, *, final: bool = False, shadow: Optional[bool] = None) -> Any:
        """The signed task audit of the channel ``task_key`` names (``TransferAuditor.audit``)."""
        auditor = self._require_auditor()
        return auditor.audit(self._journaled_uid(auditor, self._resolve(task_key)), final=final, shadow=shadow)

    def view(self, task_key: Any) -> Any:
        """The authoritative view of the channel, parsed from its journal."""
        auditor = self._require_auditor()
        return auditor.view(self._journaled_uid(auditor, self._resolve(task_key)))

    # ------------------------------------------------------------------ overseer agents
    def ensure_intake(self, factory: Any) -> Any:
        """This hub's verdict intake: the one given at construction, else the one ``factory()`` builds at the first
        review (built once, under the hub's lock; a hook of the overseer's operations)."""
        with self._lock:
            if self.intake is None:
                self.intake = factory()
            return self.intake

    # ------------------------------------------------------------------ consolidation and repeated faults
    def _task_channels(self, ch: TranslatorChannel) -> list[TranslatorChannel]:
        """The channels this hub opened for ``ch``'s task id that the auditor journaled, ``ch`` last: earlier channels of
        a reopened task first, in the order the hub retired them."""
        auditor = self._require_auditor()
        journaled = set(auditor.channel_uids())
        with self._lock:
            earlier = [c for uid, c in self.closed_channels.items() if c is not ch and c.plan.task_id == ch.plan.task_id and uid in journaled]
        return [*earlier, ch]

    def task_channels(self, ch: TranslatorChannel) -> list[TranslatorChannel]:
        """The journaled channels of ``ch``'s task id, ``ch`` last (a hook of the overseer's operations)."""
        return self._task_channels(ch)

    def repeats(self, task_key: Any) -> Any:
        """The repeat report of the task ``task_key`` names: every error-level fault of every answer, signed
        (``epinoic_overseer.repeats``), over the channels this hub opened for that task id, in order."""
        return self._operations().repeats(self, task_key)

    def consolidate(self, task_key: Any, *, request_message_ids: Optional[Sequence[str]] = None,
                    user_input_sha256: Optional[str] = None) -> Any:
        """The consolidated response to one input several agents answered on the task ``task_key`` names (see the
        module docstring and ``epinoic_overseer.consolidate``). The response is signed and recorded; the router delivers
        an answer only through ``consolidate.delivery_decision(resp, keyring, hub=self)``."""
        return self._operations().consolidate(self, task_key, request_message_ids=request_message_ids, user_input_sha256=user_input_sha256)

    def record_consolidation(self, channel_uid: str, resp: Any) -> None:
        """Record a consolidated response this hub issued for the channel ``channel_uid`` (a deep copy: an edit of the
        object returned to the router never reaches the record; a hook of the overseer's operations)."""
        with self._lock:
            self._consolidations.setdefault(channel_uid, []).append(resp.model_copy(deep=True))

    def consolidations(self, task_key: Any) -> list[Any]:
        """Every consolidated response this hub issued for the channel ``task_key`` names, in order (copies)."""
        ch = self._resolve(task_key)
        with self._lock:
            return [c.model_copy(deep=True) for c in self._consolidations.get(ch.channel_uid, [])]

    def _latest_consolidations(self, uid: str) -> list[Any]:
        with self._lock:
            latest: dict[str, Any] = {}
            for c in self._consolidations.get(uid, []):
                latest.pop(c.user_input_sha256, None)
                latest[c.user_input_sha256] = c
            return list(latest.values())

    def latest_consolidations(self, channel_uid: str) -> list[Any]:
        """The latest consolidated response per input for the channel ``channel_uid`` (a hook of the overseer's operations)."""
        return self._latest_consolidations(channel_uid)

    def review_pool(self, task_keys: Sequence[Any], pool: Any, *, mode: Optional[str] = None) -> PoolReview:
        """A self-duplicating review of a batch of tasks (see the module docstring and ``epinoic_overseer.pool``): one
        dossier per task, keyed by its channel uid, with the task's repeated faults; ``pool.plan`` decides the instances;
        each task is reviewed through ``review`` by exactly the instances the plan assigns it. Agents never gate
        clearance. Something that is no pool at all is refused (TypeError) before the auditor is asked for, as it always
        was; the overseer's operations then require an ``OverseerPool`` configured from a loaded knowledge pack."""
        if not (callable(getattr(pool, "plan", None)) and callable(getattr(pool, "runners_for", None))):
            raise TypeError("a pool review needs an OverseerPool configured from a loaded knowledge pack")
        return self._operations().review_pool(self, task_keys, pool, mode=mode)

    def review(self, task_key: Any, runners: Sequence[Any], *, mode: str = "informed", pool_plan: Optional[Any] = None) -> HubReview:
        """Overseer agents review the task's transfers (see the module docstring). Agents never gate clearance."""
        return self._operations().review(self, task_key, runners, mode=mode, pool_plan=pool_plan)

    # ------------------------------------------------------------------ lifecycle
    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        """Close the hub: no new task or transfer; the auditor's replay worker stops when the last hub using that
        auditor closes. Journals, audits and closed channels stay readable. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        auditor = self.auditor
        if auditor is None:
            return
        with _AUDITOR_LOCK:
            left = _AUDITOR_HUBS.get(auditor, 1) - 1
            if left > 0:
                _AUDITOR_HUBS[auditor] = left
                return
            _AUDITOR_HUBS.pop(auditor, None)
        auditor.close()

    def __enter__(self) -> "RouterHub":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _field(payload: Mapping[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    return value if isinstance(value, str) else None
