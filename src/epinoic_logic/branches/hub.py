"""Router hub: the primary router agent's single integration surface.

The router opens one channel per task from its work plan, dispatches requests to
any number of specialists (English, History, Psychology, Economics, Business
Management, ...), receives their raw text or structured reports back through the
branch that matches the task's subject, and reads receipts. Every message crosses
the translator channel; nothing is forwarded raw.

Observation and the Overseer (optional; ``docs/OVERSEER_DESIGN.md`` sections 4, 5.3, 7 and 9-10). A hub built without
``observers`` and ``auditor`` opens channels with no observer, and they behave exactly as before.

* ``observers=``: generic channel observers attached to every channel the hub opens (``TranslatorChannel.add_observer``).
* ``auditor=``: a :class:`~epinoic_logic.overseer.audit.TransferAuditor`, attached FIRST to every channel the hub opens,
  so the authoritative journal is written before any other observer runs. It also enables:

  - ``clearance(task_key, message_id, receipt=None, wait_ms=0)``: the router's check immediately before acting on a
    transfer: custody of the message and its dependencies re-checked, the receipt the router presents (or the
    channel's) compared with the journal; ``wait_ms`` is clamped to ``policy.MAX_PENDING_WAIT_MS`` and bounds the
    whole wait for outstanding replay and re-derivation. Act only when ``policy.may_act(receipt, clearance)``;
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
    ``consolidate.delivery_decision`` only. ``repeats(task_key)`` is the task's repeat report (every channel the hub
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

import hmac
import threading
import time
import uuid
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Sequence, Union

from ..engine.results import SolverConfig
from ..integrity.contracts import AgentMessage, WorkPlan
from ..translate.contracts import SpecialistReport, SuppliedText
from ..channel.bus import ChannelObserver, TranslatorChannel, VerifyClaimFn
from ..channel.contracts import TaskRequest, TransmissionReceipt
from .base import BranchRegistry
from .registry import default_registry

if TYPE_CHECKING:  # the overseer package is imported lazily: a hub without an auditor never loads it
    from ..overseer.audit import TransferAuditor
    from ..overseer.combine import CombinedAssessment
    from ..overseer.consolidate import ConsolidatedResponse
    from ..overseer.contracts import OverseerAudit, TransferClearance
    from ..overseer.pool import OverseerPool, PoolPlan
    from ..overseer.repeats import RepeatReport
    from ..overseer.intake import VerdictIntake
    from ..overseer.runner import AgentRun, OverseerAgentRunner
    from ..overseer.validate import VerdictAssessment
    from ..overseer.view import OverseerView

#: Most channels ``closed_channels`` keeps (oldest dropped first; a dropped channel's journal stays with the auditor).
MAX_CLOSED_CHANNELS = 1024
_AUDITOR_METHODS = ("observer_for", "clearance", "audit", "view", "audits", "journal", "channel_uids", "seal", "close", "keyring", "store", "replayer")

# Hubs attached to each auditor: the replay worker stops when the last of them closes.
_AUDITOR_HUBS: "weakref.WeakKeyDictionary[Any, int]" = weakref.WeakKeyDictionary()
_AUDITOR_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AuditorNotAttached(RuntimeError):
    """An Overseer method of a hub built without ``auditor=``: nothing is shown as passed without an auditor."""


class HubClosed(RuntimeError):
    """A transfer or a new task on a hub that was closed."""


@dataclass(frozen=True)
class HubReview:
    """What one ``RouterHub.review`` did. ``audit`` is the signed ``verdicts``-scope audit; nothing here confirms,
    passes or clears a transfer (only the auditor's own ``OVS-*`` findings do)."""
    audit: "OverseerAudit"
    task_audit: "OverseerAudit"
    mode: str
    runs: tuple["AgentRun", ...]
    assessments: tuple["VerdictAssessment", ...]
    combined: Optional["CombinedAssessment"]
    refused: tuple[tuple[str, str], ...]
    runner_errors: tuple[tuple[str, str], ...]
    superseding_audit_ids: tuple[str, ...]


@dataclass(frozen=True)
class PoolReview:
    """What one ``RouterHub.review_pool`` did: the recorded plan and, per dossier key (the channel uid), the
    :class:`HubReview` of the instances the plan assigned. Nothing here confirms, passes or clears a transfer."""
    plan: "PoolPlan"
    reviews: dict[str, HubReview]
    task_keys: dict[str, Any]


def _same_subkeys(a: Any, b: Any) -> bool:
    return a is b or all(hmac.compare_digest(a.subkey(label), b.subkey(label)) for label in ("audit", "intake", "runs", "journal"))


class RouterHub:
    def __init__(self, *, signing_key: bytes, key_id: str = "hub", registry: Optional[BranchRegistry] = None,
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig(),
                 observers: Sequence[ChannelObserver] = (), auditor: Optional["TransferAuditor"] = None,
                 intake: Optional["VerdictIntake"] = None) -> None:
        self.registry = registry or default_registry()
        self.key, self.key_id, self.verify_claim_fn, self.config = signing_key, key_id, verify_claim_fn, config
        self.channels: dict[str, TranslatorChannel] = {}
        observers = tuple(observers)
        for o in observers:
            if not callable(o):
                raise TypeError(f"a channel observer must be callable, not {type(o).__name__}")
        self.observers: tuple[ChannelObserver, ...] = observers
        self.closed_channels: "OrderedDict[str, TranslatorChannel]" = OrderedDict()
        self._lock = threading.RLock()
        self._closed = False
        self.auditor: Optional["TransferAuditor"] = None
        self.intake: Optional["VerdictIntake"] = None
        self._consolidations: dict[str, list["ConsolidatedResponse"]] = {}
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
        return self.channels[task_id].request(from_agent_id, to_agent_id, user_input, list(supplied_texts))

    def receive(self, task_id: str, request_message_id: str, payload: Union[str, SpecialistReport], *, agent_id: Optional[str] = None,
                report_id: Optional[str] = None, agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        self._check_open()
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

    def _retire(self, ch: TranslatorChannel) -> None:
        """Keep a channel the hub no longer routes to under its key (replaced or closed): never lost, still auditable."""
        with self._lock:
            uid = ch.channel_uid
            self.closed_channels.pop(uid, None)
            self.closed_channels[uid] = ch
            while len(self.closed_channels) > MAX_CLOSED_CHANNELS:
                self.closed_channels.popitem(last=False)

    def close_task(self, task_key: str, *, audit: bool = True) -> Optional["OverseerAudit"]:
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
    def _require_auditor(self) -> "TransferAuditor":
        if self.auditor is None:
            raise AuditorNotAttached("this hub has no auditor: build it with auditor=TransferAuditor(...) to audit, clear or review transfers")
        return self.auditor

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

    def _journaled_uid(self, auditor: "TransferAuditor", ch: TranslatorChannel) -> str:
        uid = ch.channel_uid
        if uid not in auditor.channel_uids():
            raise LookupError(f"nothing of channel {uid} (task {ch.plan.task_id!r}) was journaled: there is nothing to audit")
        return uid

    def clearance(self, task_key: Any, message_id: str, *, receipt: Any = None, wait_ms: int = 0) -> "TransferClearance":
        """The router's check immediately before acting on a transfer (see the module docstring). ``wait_ms`` is clamped
        to ``policy.MAX_PENDING_WAIT_MS`` and bounds the whole wait (replay and re-derivation together). A channel of
        which nothing was journaled clears nothing (AUDIT_FAILED, CUST-003)."""
        from ..overseer.contracts import TransferClearance
        from ..overseer.policy import bounded_wait_ms
        auditor = self._require_auditor()
        ch = self._resolve(task_key)
        uid = ch.channel_uid
        if uid not in auditor.channel_uids():
            return TransferClearance(clearance_id=uuid.uuid4().hex, message_id=str(message_id), task_id=ch.plan.task_id, channel_uid=uid, state="AUDIT_FAILED",
                                     codes=["OVS-CUST-003"], finding_count=1, created_at=_now())
        budget = bounded_wait_ms(wait_ms)
        if budget:
            self._wait_for_replay(auditor, budget)
        return auditor.clearance(uid, message_id, receipt=receipt, wait_ms=0)

    @staticmethod
    def _wait_for_replay(auditor: "TransferAuditor", budget_ms: int) -> None:
        """Wait for outstanding replay, then re-derivation, at most ``budget_ms`` IN ALL (one deadline for both waits).
        Whatever is still outstanding leaves the transfer AUDIT_PENDING, never passed."""
        deadline = time.monotonic() + budget_ms / 1000.0
        replayer = auditor.replayer
        replayer.drain(timeout_s=budget_ms / 1000.0)
        left = deadline - time.monotonic()
        if left > 0:
            replayer.wait_tasks(timeout_s=left)

    def audit(self, task_key: Any, *, final: bool = False, shadow: Optional[bool] = None) -> "OverseerAudit":
        """The signed task audit of the channel ``task_key`` names (``TransferAuditor.audit``)."""
        auditor = self._require_auditor()
        return auditor.audit(self._journaled_uid(auditor, self._resolve(task_key)), final=final, shadow=shadow)

    def view(self, task_key: Any) -> "OverseerView":
        """The authoritative view of the channel, parsed from its journal."""
        auditor = self._require_auditor()
        return auditor.view(self._journaled_uid(auditor, self._resolve(task_key)))

    # ------------------------------------------------------------------ overseer agents
    def _review_intake(self) -> "VerdictIntake":
        from ..overseer.intake import VerdictIntake
        from ..overseer.pack import installed_pack
        with self._lock:
            if self.intake is None:
                self.intake = VerdictIntake(self._require_auditor().keyring, accepted_packs={installed_pack().identity})
            return self.intake

    def _reference_audit(self, auditor: "TransferAuditor", uid: str, view: "OverseerView") -> "OverseerAudit":
        from ..overseer.audit import verify_audit
        task_audits = [a for a in auditor.audits(uid) if a.scope == "task"]
        latest = task_audits[-1] if task_audits else None
        current = [t.message_id for t in view.transfers if t.message_id]
        if latest is not None and verify_audit(latest, auditor.keyring) and list(latest.message_ids) == current and latest.coverage.shadow_run == "run":
            return latest
        return auditor.audit(uid, final=bool(latest is not None and latest.final), shadow=True)

    # ------------------------------------------------------------------ consolidation and repeated faults
    def _task_channels(self, ch: TranslatorChannel) -> list[TranslatorChannel]:
        """The channels this hub opened for ``ch``'s task id that the auditor journaled, ``ch`` last: earlier channels of
        a reopened task first, in the order the hub retired them."""
        auditor = self._require_auditor()
        journaled = set(auditor.channel_uids())
        with self._lock:
            earlier = [c for uid, c in self.closed_channels.items() if c is not ch and c.plan.task_id == ch.plan.task_id and uid in journaled]
        return [*earlier, ch]

    def _latest_verified_audit(self, auditor: "TransferAuditor", uid: str) -> Optional["OverseerAudit"]:
        from ..overseer.audit import verify_audit
        task_audits = [a for a in auditor.audits(uid) if a.scope == "task"]
        return task_audits[-1] if task_audits and verify_audit(task_audits[-1], auditor.keyring) else None

    def _repeat_inputs(self, ch: TranslatorChannel) -> tuple[list[Any], dict[str, Any], Any, Any]:
        """(prior views, audits by channel uid, the channel's view, its reference task audit)."""
        auditor = self._require_auditor()
        uid = self._journaled_uid(auditor, ch)
        view = auditor.view(uid)
        task_audit = self._reference_audit(auditor, uid, view)
        prior_views, audits = [], {uid: task_audit}
        for c in self._task_channels(ch)[:-1]:
            prior_views.append(auditor.view(c.channel_uid))
            a = self._latest_verified_audit(auditor, c.channel_uid)
            if a is not None:
                audits[c.channel_uid] = a
        return prior_views, audits, view, task_audit

    def repeats(self, task_key: Any) -> "RepeatReport":
        """The repeat report of the task ``task_key`` names: every error-level fault of every answer, signed
        (``overseer/repeats.py``), over the channels this hub opened for that task id, in order."""
        from ..overseer.repeats import detect_repeats
        auditor = self._require_auditor()
        ch = self._resolve(task_key)
        prior_views, audits, view, _audit = self._repeat_inputs(ch)
        return detect_repeats([*prior_views, view], audits, keyring=auditor.keyring)

    def consolidate(self, task_key: Any, *, request_message_ids: Optional[Sequence[str]] = None,
                    user_input_sha256: Optional[str] = None) -> "ConsolidatedResponse":
        """The consolidated response to one input several agents answered on the task ``task_key`` names (see the
        module docstring and ``overseer/consolidate.py``). The response is signed and recorded; the router delivers an
        answer only through ``consolidate.delivery_decision``."""
        from ..overseer.consolidate import consolidate as _consolidate
        from ..overseer.repeats import detect_repeats
        auditor = self._require_auditor()
        ch = self._resolve(task_key)
        prior_views, audits, view, task_audit = self._repeat_inputs(ch)
        report = detect_repeats([*prior_views, view], audits, keyring=auditor.keyring)
        prior_audits = {k: v for k, v in audits.items() if k != ch.channel_uid}
        resp = _consolidate(view, keyring=auditor.keyring, store=auditor.store, audit=task_audit, request_message_ids=request_message_ids,
                            user_input_sha256=user_input_sha256, prior_views=prior_views, prior_audits=prior_audits, repeats=report)
        with self._lock:  # the hub keeps its own copy: an edit of the object returned to the router never reaches the record
            self._consolidations.setdefault(ch.channel_uid, []).append(resp.model_copy(deep=True))
        return resp

    def consolidations(self, task_key: Any) -> list["ConsolidatedResponse"]:
        """Every consolidated response this hub issued for the channel ``task_key`` names, in order (copies)."""
        ch = self._resolve(task_key)
        with self._lock:
            return [c.model_copy(deep=True) for c in self._consolidations.get(ch.channel_uid, [])]

    def _latest_consolidations(self, uid: str) -> list["ConsolidatedResponse"]:
        with self._lock:
            latest: dict[str, Any] = {}
            for c in self._consolidations.get(uid, []):
                latest.pop(c.user_input_sha256, None)
                latest[c.user_input_sha256] = c
            return list(latest.values())

    def review_pool(self, task_keys: Sequence[Any], pool: "OverseerPool", *, mode: Optional[str] = None) -> PoolReview:
        """A self-duplicating review of a batch of tasks (see the module docstring and ``overseer/pool.py``): one dossier
        per task, keyed by its channel uid, with the task's repeated faults; ``pool.plan`` decides the instances; each task
        is reviewed through ``review`` by exactly the instances the plan assigns it. Agents never gate clearance."""
        from ..overseer.pool import OverseerPool, PoolItem
        if not isinstance(pool, OverseerPool):
            raise TypeError("a pool review needs an OverseerPool configured from a loaded knowledge pack")
        self._require_auditor()
        chans: dict[str, TranslatorChannel] = {}
        keys: dict[str, Any] = {}
        for k in task_keys:
            ch = self._resolve(k)
            if ch.channel_uid in chans:
                raise ValueError("a task is given twice in one batch")
            chans[ch.channel_uid], keys[ch.channel_uid] = ch, k
        items = [PoolItem(key=uid, repeated_faults=sum(1 for r in self.repeats(ch).repeats if r.channel_uid == uid)) for uid, ch in chans.items()]
        plan = pool.plan(items)
        reviews: dict[str, HubReview] = {}
        for it in plan.items:
            reviews[it.key] = self.review(chans[it.key], pool.runners_for(plan, it.key), mode=mode or pool.config.mode, pool_plan=plan)
        return PoolReview(plan=plan, reviews=reviews, task_keys=keys)

    def review(self, task_key: Any, runners: Sequence["OverseerAgentRunner"], *, mode: str = "informed", pool_plan: Optional["PoolPlan"] = None) -> HubReview:
        """Overseer agents review the task's transfers (see the module docstring). Agents never gate clearance."""
        from ..overseer.audit import verify_audit
        from ..overseer.combine import combine_verdicts, combined_digest
        from ..overseer.intake import IntakeRefused
        from ..overseer.runner import OverseerAgentRunner
        from ..overseer.validate import build_verdicts_audit, validate_overseer_verdict
        from ..overseer.verdicts import MODES

        auditor = self._require_auditor()
        if mode not in MODES:
            raise ValueError(f"unknown review mode {mode!r}")
        runners = list(runners)
        if not runners:
            raise ValueError("a review needs at least one overseer agent runner")
        for r in runners:
            if type(r) is not OverseerAgentRunner:  # exactly the package's runner: no subclass decides how a reply reaches the intake
                raise TypeError("an overseer agent is an OverseerAgentRunner configured from a loaded knowledge pack")
        ids = [r.agent_id for r in runners]
        if len(set(ids)) != len(ids):
            raise ValueError("two runners share an agent id: each agent reviews a task once")
        from ..overseer.pool import HARD_MAX_INSTANCES
        if pool_plan is None and any(getattr(r, "pool_member", False) for r in runners):
            raise ValueError("pool instances review a task only under the pool plan that assigns them (pool_plan=...)")
        if len(runners) > HARD_MAX_INSTANCES:
            raise ValueError(f"a review runs at most {HARD_MAX_INSTANCES} overseer agents on one task")
        ch = self._resolve(task_key)
        uid = self._journaled_uid(auditor, ch)
        if pool_plan is not None:
            from ..overseer.pool import PoolPlan
            if not isinstance(pool_plan, PoolPlan) or uid not in pool_plan.assignments:
                raise ValueError("the pool plan does not assign this task")
            if sorted(ids) != sorted(pool_plan.assignments[uid]) or any(r.identity != pool_plan.pack for r in runners):
                raise ValueError("the runners are not the instances the pool plan assigns to this task under its pack")
        intake = self._review_intake()
        view = auditor.view(uid)
        task_audit = self._reference_audit(auditor, uid, view)
        consolidations = self._latest_consolidations(uid) if mode == "informed" else []
        ordered = sorted(runners, key=lambda r: r.agent_id)
        # 1. every dossier is issued before any agent runs; no agent ever receives another agent's verdict
        issued: list[tuple[Any, dict]] = []
        refused: list[tuple[str, str]] = []
        for r in ordered:
            try:
                d = intake.issue(view, agent_id=r.agent_id, lens=r.lens, mode=mode, pack=r.identity, audit=task_audit if mode == "informed" else None,
                                 consolidations=consolidations)
            except IntakeRefused as exc:
                refused.append((r.agent_id, exc.reason))
                continue
            issued.append((r, d))
        # 2. each agent runs once; its reply goes to the intake as data
        runs: list[Any] = []
        errors: list[tuple[str, str]] = []
        for r, d in issued:
            try:
                runs.append(r.run(d, intake))
            except Exception as exc:  # a broken runner never breaks the review; it is recorded as no review
                errors.append((r.agent_id, type(exc).__name__))
        # 3. every accepted verdict is validated against the journal and the signed results
        assessments: list[Any] = []
        for run in runs:
            if run.status != "submitted" or not run.message_id:
                continue
            accepted = intake.accepted(run.message_id)
            if accepted is None:
                continue
            assessments.append(validate_overseer_verdict(accepted.message, view, auditor.store, task_audit, auditor, intake=intake, live=ch,
                                                         registry=getattr(ch, "registry", None)))
        # 4. combination: no voting on facts
        combined = combine_verdicts(assessments, intake=intake) if assessments else None
        # 5. the signed verdicts-scope audit; its states are the auditor's latest task audit's, never an agent's
        task_audits = [a for a in auditor.audits(uid) if a.scope == "task" and verify_audit(a, auditor.keyring)]
        reference = task_audits[-1] if task_audits else task_audit
        audit_ids = [a.audit_id for a in task_audits]
        superseding = tuple(audit_ids[audit_ids.index(task_audit.audit_id) + 1:]) if task_audit.audit_id in audit_ids else ()
        findings = list(combined.findings) if combined is not None else []
        for run in sorted(runs, key=lambda x: x.agent_id):
            if run.status == "invalid" and run.finding is not None:
                findings.append(run.finding)
        notes = [f"references task audit {reference.audit_id}" + (f" (the review started from task audit {task_audit.audit_id})" if reference is not task_audit else ""),
                 f"review mode {mode}; {len(runners)} agent(s); {len(issued)} dossier(s) issued; {len(assessments)} verdict(s) assessed"]
        if consolidations:
            notes.append("dossiers show consolidated responses " + ", ".join(f"{c.consolidation_id} ({c.status})" for c in consolidations))
        if pool_plan is not None:
            notes.append(f"overseer pool plan {pool_plan.plan_id}: {len(pool_plan.instances)} instance(s) (maximum {pool_plan.config.max_instances}, quota "
                         f"{pool_plan.config.per_instance_quota}, tier {pool_plan.config.model_tier}) of pack {pool_plan.pack.name} {pool_plan.pack.version} "
                         f"{pool_plan.pack.sha256}; this task to {pool_plan.assignments[uid]}; {'; '.join(pool_plan.reasons)}")
        for agent_id, reason in refused:
            notes.append(f"agent {agent_id}: no dossier issued ({reason}); no review")
        for agent_id, err in errors:
            notes.append(f"agent {agent_id}: the runner failed ({err}); no review")
        for run in sorted(runs, key=lambda x: x.agent_id):
            pk = f"{run.pack.name} {run.pack.version} {run.pack.sha256}"
            what = {"submitted": "verdict accepted by the intake and assessed", "invalid": f"verdict rejected by the intake ({run.reason}): OVS-AGENT-005",
                    "provider_error": f"provider failure ({run.reason}): no review", "refused_input": f"input refused ({run.reason}): no review"}[run.status]
            notes.append(f"agent {run.agent_id} under pack {pk}: {what}")
        if combined is not None:
            notes.append(f"combined assessment sha256 {combined_digest(combined)}; groups {len(combined.groups)}; human review queue "
                         f"{len(combined.review_queue)}; no voting on facts")
        else:
            notes.append("no verdict was assessed: this is no review, and it states nothing about the transfers")
        notes.append("OVS-AGENT-* findings never change a transfer's clearance; an agent's verdict is advisory and decides nothing")
        audit = build_verdicts_audit(reference=reference, channel_uid=uid, task_id=reference.task_id, request_id=reference.request_id, findings=findings,
                                     keyring=auditor.keyring, message_ids=list(reference.message_ids), notes=notes)
        return HubReview(audit=audit, task_audit=task_audit, mode=mode, runs=tuple(runs), assessments=tuple(assessments), combined=combined,
                         refused=tuple(refused), runner_errors=tuple(errors), superseding_audit_ids=superseding)

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
