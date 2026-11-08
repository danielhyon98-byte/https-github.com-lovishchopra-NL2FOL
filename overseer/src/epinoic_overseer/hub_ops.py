"""The overseer's operations on the translator's router hub: ``RouterHub.clearance``, ``repeats``, ``consolidate``,
``review_pool`` and ``review``.

The translator's ``RouterHub`` never imports this package. A hub built with ``auditor=TransferAuditor(...)`` reaches
these operations through the auditor it was given (:attr:`TransferAuditor.hub_operations
<epinoic_overseer.audit.TransferAuditor.hub_operations>`), and a hub without an auditor refuses each of them with
``AuditorNotAttached`` before anything else, as it always did. Their bodies are the hub's own method bodies from before
the overseer became a separate sub-project, moved here unchanged: the same checks in the same order with the same
results. The hub keeps what is its own (its channels and their order, the consolidated responses it issued, its verdict
intake) and gives these operations its public hooks: ``channel_for``, ``journaled_uid``, ``task_channels``,
``record_consolidation``, ``latest_consolidations`` and ``ensure_intake`` (the translator's ``branches/hub.py``).

The result types the hub returns, :class:`~epinoic_logic.branches.hub.HubReview` and ``PoolReview``, are the
translator's; this module builds them through the translator's public API (``epinoic_logic.api.branches``).
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from epinoic_logic.api.branches import HubReview, PoolReview

__all__ = ["HubOperations", "HUB_OPERATIONS"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class HubOperations:
    """The operations a hub carrying a :class:`~epinoic_overseer.audit.TransferAuditor` delegates to. Stateless: every
    call takes the hub, whose auditor is attached (the hub checked it before delegating)."""

    # ------------------------------------------------------------------ clearance
    def clearance(self, hub: Any, task_key: Any, message_id: str, *, receipt: Any = None, wait_ms: int = 0) -> Any:
        """The router's check immediately before acting on a transfer (``RouterHub.clearance``). ``wait_ms`` is clamped
        to ``policy.MAX_PENDING_WAIT_MS`` and bounds the whole wait (replay and re-derivation together). A channel of
        which nothing was journaled clears nothing (AUDIT_FAILED, CUST-003)."""
        from .contracts import TransferClearance
        from .policy import bounded_wait_ms
        auditor = hub.auditor
        ch = hub.channel_for(task_key)
        uid = ch.channel_uid
        if uid not in auditor.channel_uids():
            return TransferClearance(clearance_id=uuid.uuid4().hex, message_id=str(message_id), task_id=ch.plan.task_id, channel_uid=uid, state="AUDIT_FAILED",
                                     codes=["OVS-CUST-003"], finding_count=1, created_at=_now())
        budget = bounded_wait_ms(wait_ms)
        if budget:
            self._wait_for_replay(auditor, budget)
        return auditor.clearance(uid, message_id, receipt=receipt, wait_ms=0)

    @staticmethod
    def _wait_for_replay(auditor: Any, budget_ms: int) -> None:
        """Wait for outstanding replay, then re-derivation, at most ``budget_ms`` IN ALL (one deadline for both waits).
        Whatever is still outstanding leaves the transfer AUDIT_PENDING, never passed."""
        deadline = time.monotonic() + budget_ms / 1000.0
        replayer = auditor.replayer
        replayer.drain(timeout_s=budget_ms / 1000.0)
        left = deadline - time.monotonic()
        if left > 0:
            replayer.wait_tasks(timeout_s=left)

    # ------------------------------------------------------------------ overseer agents
    def _review_intake(self, hub: Any) -> Any:
        from .intake import VerdictIntake
        from .pack import installed_pack
        return hub.ensure_intake(lambda: VerdictIntake(hub.auditor.keyring, accepted_packs={installed_pack().identity}))

    def _reference_audit(self, auditor: Any, uid: str, view: Any) -> Any:
        from .audit import verify_audit
        task_audits = [a for a in auditor.audits(uid) if a.scope == "task"]
        latest = task_audits[-1] if task_audits else None
        current = [t.message_id for t in view.transfers if t.message_id]
        if latest is not None and verify_audit(latest, auditor.keyring) and list(latest.message_ids) == current and latest.coverage.shadow_run == "run":
            return latest
        return auditor.audit(uid, final=bool(latest is not None and latest.final), shadow=True)

    # ------------------------------------------------------------------ consolidation and repeated faults
    def _latest_verified_audit(self, auditor: Any, uid: str) -> Optional[Any]:
        from .audit import verify_audit
        task_audits = [a for a in auditor.audits(uid) if a.scope == "task"]
        return task_audits[-1] if task_audits and verify_audit(task_audits[-1], auditor.keyring) else None

    def _repeat_inputs(self, hub: Any, ch: Any) -> tuple[list[Any], dict[str, Any], Any, Any]:
        """(prior views, audits by channel uid, the channel's view, its reference task audit)."""
        auditor = hub.auditor
        uid = hub.journaled_uid(auditor, ch)
        view = auditor.view(uid)
        task_audit = self._reference_audit(auditor, uid, view)
        prior_views, audits = [], {uid: task_audit}
        for c in hub.task_channels(ch)[:-1]:
            prior_views.append(auditor.view(c.channel_uid))
            a = self._latest_verified_audit(auditor, c.channel_uid)
            if a is not None:
                audits[c.channel_uid] = a
        return prior_views, audits, view, task_audit

    def repeats(self, hub: Any, task_key: Any) -> Any:
        """The repeat report of the task ``task_key`` names (``RouterHub.repeats``): every error-level fault of every
        answer, signed (``repeats.py``), over the channels the hub opened for that task id, in order."""
        from .repeats import detect_repeats
        auditor = hub.auditor
        ch = hub.channel_for(task_key)
        prior_views, audits, view, _audit = self._repeat_inputs(hub, ch)
        return detect_repeats([*prior_views, view], audits, keyring=auditor.keyring)

    def consolidate(self, hub: Any, task_key: Any, *, request_message_ids: Optional[Sequence[str]] = None,
                    user_input_sha256: Optional[str] = None) -> Any:
        """The consolidated response to one input several agents answered on the task ``task_key`` names
        (``RouterHub.consolidate``; ``consolidate.py``). The response is signed and recorded by the hub; the router
        delivers an answer only through ``consolidate.delivery_decision(resp, keyring, hub=hub)``."""
        from .consolidate import consolidate as _consolidate
        from .repeats import detect_repeats
        auditor = hub.auditor
        ch = hub.channel_for(task_key)
        prior_views, audits, view, task_audit = self._repeat_inputs(hub, ch)
        report = detect_repeats([*prior_views, view], audits, keyring=auditor.keyring)
        prior_audits = {k: v for k, v in audits.items() if k != ch.channel_uid}
        resp = _consolidate(view, keyring=auditor.keyring, store=auditor.store, audit=task_audit, request_message_ids=request_message_ids,
                            user_input_sha256=user_input_sha256, prior_views=prior_views, prior_audits=prior_audits, repeats=report)
        hub.record_consolidation(ch.channel_uid, resp)  # the hub keeps its own copy: an edit of the returned object never reaches the record
        return resp

    # ------------------------------------------------------------------ the pool and the review
    def review_pool(self, hub: Any, task_keys: Sequence[Any], pool: Any, *, mode: Optional[str] = None) -> Any:
        """A self-duplicating review of a batch of tasks (``RouterHub.review_pool``; ``pool.py``): one dossier per task,
        keyed by its channel uid, with the task's repeated faults; ``pool.plan`` decides the instances; each task is
        reviewed through ``review`` by exactly the instances the plan assigns it. Agents never gate clearance."""
        from .pool import OverseerPool, PoolItem
        if not isinstance(pool, OverseerPool):
            raise TypeError("a pool review needs an OverseerPool configured from a loaded knowledge pack")
        chans: dict[str, Any] = {}
        keys: dict[str, Any] = {}
        for k in task_keys:
            ch = hub.channel_for(k)
            if ch.channel_uid in chans:
                raise ValueError("a task is given twice in one batch")
            chans[ch.channel_uid], keys[ch.channel_uid] = ch, k
        from .emitted import risk_reading
        auditor = hub.auditor
        # integration step: the risk signals and records each task's journaled transfers carry (named defects, load-bearing
        # writer's assumptions, unchecked sources, STEM method errors, ...) only ever escalate its review (``pool.plan_pool``)
        items = []
        for uid, ch in chans.items():
            signals, records = risk_reading(auditor.view(hub.journaled_uid(auditor, ch)))
            items.append(PoolItem(key=uid, repeated_faults=sum(1 for r in hub.repeats(ch).repeats if r.channel_uid == uid),
                                  risk_signals=signals, risk_records=records))
        plan = pool.plan(items)
        reviews: dict[str, Any] = {}
        for it in plan.items:
            reviews[it.key] = hub.review(chans[it.key], pool.runners_for(plan, it.key), mode=mode or pool.config.mode, pool_plan=plan)
        return PoolReview(plan=plan, reviews=reviews, task_keys=keys)

    def review(self, hub: Any, task_key: Any, runners: Sequence[Any], *, mode: str = "informed", pool_plan: Optional[Any] = None) -> Any:
        """Overseer agents review the task's transfers (``RouterHub.review``). Agents never gate clearance."""
        from .audit import verify_audit
        from .combine import combine_verdicts, combined_digest
        from .intake import IntakeRefused
        from .runner import OverseerAgentRunner
        from .validate import build_verdicts_audit, validate_overseer_verdict
        from .verdicts import MODES

        auditor = hub.auditor
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
        from .pool import HARD_MAX_INSTANCES
        if pool_plan is None and any(getattr(r, "pool_member", False) for r in runners):
            raise ValueError("pool instances review a task only under the pool plan that assigns them (pool_plan=...)")
        if len(runners) > HARD_MAX_INSTANCES:
            raise ValueError(f"a review runs at most {HARD_MAX_INSTANCES} overseer agents on one task")
        ch = hub.channel_for(task_key)
        uid = hub.journaled_uid(auditor, ch)
        if pool_plan is not None:
            from .pool import PoolPlan
            if not isinstance(pool_plan, PoolPlan) or uid not in pool_plan.assignments:
                raise ValueError("the pool plan does not assign this task")
            if sorted(ids) != sorted(pool_plan.assignments[uid]) or any(r.identity != pool_plan.pack for r in runners):
                raise ValueError("the runners are not the instances the pool plan assigns to this task under its pack")
        intake = self._review_intake(hub)
        view = auditor.view(uid)
        task_audit = self._reference_audit(auditor, uid, view)
        consolidations = hub.latest_consolidations(uid) if mode == "informed" else []
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
            from .floor import admission_note
            notes.append(f"overseer pool plan {pool_plan.plan_id}: {len(pool_plan.instances)} instance(s) (maximum {pool_plan.config.max_instances}, quota "
                         f"{pool_plan.config.per_instance_quota}, tier {pool_plan.config.model_tier}) of pack {pool_plan.pack.name} {pool_plan.pack.version} "
                         f"{pool_plan.pack.sha256}; this task to {pool_plan.assignments[uid]}; {'; '.join(pool_plan.reasons)}")
            # who planned it (the flash router, or the minimum-oversight floor), the floor it was held to and any refusal
            notes.append(admission_note(pool_plan))
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


#: The one instance every :class:`~epinoic_overseer.audit.TransferAuditor` hands its hubs.
HUB_OPERATIONS = HubOperations()
