"""The overseer's operations on the translator's router hub: ``RouterHub.clearance``, ``repeats``, ``consolidate``,
``review_pool``, ``review`` and, since design section 53 (specialist feedback and revision), ``request_revision``,
``revision_outcome`` and ``revisions``.

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

Specialist feedback and revision (design section 53; ``feedback.py``): ``request_revision`` builds the signed revision
request for an answer from the journal, the reference task audit and the hub's copies of the signed verdicts audits
(``review`` gives the hub a copy of every verdicts audit it issues, ``RouterHub.record_verdicts``), and re-issues the
original request with it to the answer's author through the channel; ``revision_outcome`` classifies the revision; both
record signed entries in the hub's revision ledger (``RouterHub.record_revision``), escalations included, and an escalated
chain counts as a repeated fault for the pool's plan (at least two instances).

Architecture step 3 (the twofold mode): ``review_pool`` reads each task's size and, for a combined answer, its sources
and merged part (``twofold.pool_item``), so the plan reviews a combined answer N_FOLD; ``review`` under a pool plan that
reviews the task N_FOLD runs it (``_review_twofold``, ``twofold.run_twofold``) instead of one dossier, and every review
under a pool plan records the decision behind its dossier's review in the signed verdicts audit.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from epinoic_logic.api.branches import HubReview, PoolReview
from epinoic_logic.api.ir import canonical_json

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

    # ------------------------------------------------------------------ specialist feedback and revision (design section 53)
    @staticmethod
    def _escalations(hub: Any, uid: str) -> list[Any]:
        from .feedback import RevisionEscalation, verify_record
        records = hub.revision_records(uid) if callable(getattr(hub, "revision_records", None)) else []
        return [r for k, r in records if k == "escalation" and isinstance(r, RevisionEscalation) and verify_record(r, hub.auditor.keyring)]

    def request_revision(self, hub: Any, task_key: Any, answer_message_id: str, *, from_agent_id: str = "router") -> Any:
        """``RouterHub.request_revision``: build, sign and send the revision request for the answer ``answer_message_id``
        (``feedback.build_revision_request``) through the task's channel, or say why not; an escalation is signed and
        recorded in the hub's revision ledger. The router names an answer and supplies no text."""
        from epinoic_logic.api.branches import RevisionIssue
        from epinoic_logic.api.channel import render_revision_message
        from .feedback import build_revision_request, escalation_for, issue_record
        auditor = hub.auditor
        ch = hub.channel_for(task_key)
        if not any(c is ch for c in list(hub.channels.values())):
            return RevisionIssue(allowed=False, reason="task_closed")
        uid = hub.journaled_uid(auditor, ch)
        view = auditor.view(uid)
        task_audit = self._reference_audit(auditor, uid, view)
        escalated = sorted({m for e in self._escalations(hub, uid) for m in e.chain_message_ids})
        res = build_revision_request(view, answer_message_id, task_audit=task_audit, keyring=auditor.keyring, verdicts_audits=hub.verdicts_audits(uid),
                                     escalated=escalated)
        if res.escalation_reason:
            answer = view.by_message.get(answer_message_id)
            esc = escalation_for(task_id=view.task_id, channel_uid=uid, agent_id=(answer.sender_agent_id if answer is not None else None) or "unknown",
                                 chain_message_ids=res.chain_message_ids, rounds_used=max(0, res.round - 1), max_rounds=res.max_rounds,
                                 remaining_signatures=res.remaining_signatures, remaining_codes=res.remaining_codes, reason=res.escalation_reason,
                                 keyring=auditor.keyring)
            hub.record_revision(uid, "escalation", esc)
            return RevisionIssue(allowed=False, reason=res.escalation_reason, round=res.round, max_rounds=res.max_rounds, escalation=esc)
        if res.block is None:
            return RevisionIssue(allowed=False, reason=res.reason, round=res.round, max_rounds=res.max_rounds)
        block = res.block
        original = view.by_message[block.original_request_message_id].request
        msg, req, rc = ch.request(from_agent_id, block.to_agent_id, original.user_input, list(original.supplied_texts), items=list(original.items),
                                  constraints=list(original.constraints), revision=block)
        if msg is None:
            return RevisionIssue(allowed=False, reason="refused_by_channel", round=block.round, max_rounds=block.max_rounds, request=req, receipt=rc, revision=block)
        hub.record_revision(uid, "issued", issue_record(block, channel_uid=uid, request_message_id=msg.message_id, receipt_status=rc.status.value,
                                                        keyring=auditor.keyring))
        return RevisionIssue(allowed=True, reason="issued", round=block.round, max_rounds=block.max_rounds, message=msg, request=req, receipt=rc,
                             revision=block, rendered=render_revision_message(block))

    def revision_outcome(self, hub: Any, task_key: Any, revised_message_id: str) -> Any:
        """``RouterHub.revision_outcome``: the signed outcome of a revision (``feedback.revision_outcome``) over a fresh
        reference task audit and the task's repeat report, recorded in the hub's revision ledger; an outcome that escalates
        records the chain's signed escalation once."""
        from .feedback import escalation_for, revision_chain
        from .feedback import revision_outcome as _outcome
        from .repeats import detect_repeats
        auditor = hub.auditor
        ch = hub.channel_for(task_key)
        prior_views, audits, view, task_audit = self._repeat_inputs(hub, ch)
        report = detect_repeats([*prior_views, view], audits, keyring=auditor.keyring)
        out = _outcome(view, revised_message_id, task_audit=task_audit, keyring=auditor.keyring, repeats=report)
        uid = view.channel_uid
        hub.record_revision(uid, "outcome", out)
        if out.next == "escalated":
            revised = view.by_message[revised_message_id]
            chain = revision_chain(view, revised)
            ids = [x for req, b in chain for x in (b.revises_message_id, req.message_id) if x] + [revised_message_id]
            if not set(ids) & {m for e in self._escalations(hub, uid) for m in e.chain_message_ids}:
                left = [f for f in out.flaws if f.bucket in ("persisted", "not_rechecked")]
                esc = escalation_for(task_id=view.task_id, channel_uid=uid, agent_id=out.agent_id, chain_message_ids=ids, rounds_used=out.round,
                                     max_rounds=out.max_rounds, remaining_signatures=[f.signature for f in left] + [i.signature for i in out.introduced],
                                     remaining_codes=[f.code for f in left] + [i.code for i in out.introduced], reason=out.escalation_reason or "budget_exhausted",
                                     keyring=auditor.keyring)
                hub.record_revision(uid, "escalation", esc)
        return out

    def revisions(self, hub: Any, task_key: Any) -> dict[str, list[Any]]:
        """``RouterHub.revisions``: the channel's revision ledger by kind (copies)."""
        ch = hub.channel_for(task_key)
        records = hub.revision_records(ch.channel_uid)
        return {"issued": [r for k, r in records if k == "issued"], "outcomes": [r for k, r in records if k == "outcome"],
                "escalations": [r for k, r in records if k == "escalation"]}

    # ------------------------------------------------------------------ the pool and the review
    def review_pool(self, hub: Any, task_keys: Sequence[Any], pool: Any, *, mode: Optional[str] = None) -> Any:
        """A self-duplicating review of a batch of tasks (``RouterHub.review_pool``; ``pool.py``): one dossier per task,
        keyed by its channel uid, with the task's repeated faults; ``pool.plan`` decides the instances; each task is
        reviewed through ``review`` by exactly the instances the plan assigns it. Agents never gate clearance."""
        from .pool import OverseerPool
        if not isinstance(pool, OverseerPool):
            raise TypeError("a pool review needs an OverseerPool configured from a loaded knowledge pack")
        chans: dict[str, Any] = {}
        keys: dict[str, Any] = {}
        for k in task_keys:
            ch = hub.channel_for(k)
            if ch.channel_uid in chans:
                raise ValueError("a task is given twice in one batch")
            chans[ch.channel_uid], keys[ch.channel_uid] = ch, k
        from .twofold import pool_item
        auditor = hub.auditor
        # integration step: the risk signals and records each task's journaled transfers carry (named defects, load-bearing
        # writer's assumptions, unchecked sources, STEM method errors, ...) only ever escalate its review (``pool.plan_pool``);
        # architecture step 3: each task's size, and for a combined answer its sources and merged part, each with its own
        # reading, so the plan reviews it N_FOLD (the floor's method for it)
        items = []
        for uid, ch in chans.items():
            repeats = [r for r in hub.repeats(ch).repeats if r.channel_uid == uid]
            by_message: dict[str, int] = {}
            for r in repeats:
                by_message[r.message_id] = by_message.get(r.message_id, 0) + 1
            # an escalated revision chain (design section 53) is reviewed like a repeated fault: by at least two instances
            escalations = self._escalations(hub, uid)
            for e in escalations:
                last = e.chain_message_ids[-1] if e.chain_message_ids else None
                if last:
                    by_message[last] = by_message.get(last, 0) + 1
            item, _layout = pool_item(auditor.view(hub.journaled_uid(auditor, ch)), uid, len(repeats) + len(escalations), by_message)
            items.append(item)
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
        if pool_plan is not None and uid in getattr(pool_plan, "twofold", {}):
            return self._review_twofold(hub, ch, uid, runners, pool_plan, mode)
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
            notes.extend(_pool_notes(pool_plan, uid))
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
        _keep_verdicts(hub, uid, audit)
        return HubReview(audit=audit, task_audit=task_audit, mode=mode, runs=tuple(runs), assessments=tuple(assessments), combined=combined,
                         refused=tuple(refused), runner_errors=tuple(errors), superseding_audit_ids=superseding)


def _keep_verdicts(hub: Any, uid: str, audit: Any) -> None:
    """Give the hub its copy of a signed verdicts audit (the advisory items of specialist feedback read only these)."""
    keep = getattr(hub, "record_verdicts", None)
    if callable(keep):
        keep(uid, audit)


def _pool_notes(pool_plan: Any, uid: str) -> list[str]:
    """What the signed verdicts audit records of the pool plan a review runs: the plan, who planned it (the flash router,
    or the minimum-oversight floor), the floor it was held to and any refusal, and the decision behind this dossier's
    review (the flash decision maker's, with what it read and priced, or the floor's)."""
    from .floor import admission_note, decision_note
    notes = [f"overseer pool plan {pool_plan.plan_id}: {len(pool_plan.instances)} instance(s) (maximum {pool_plan.config.max_instances}, quota "
             f"{pool_plan.config.per_instance_quota}, tier {pool_plan.config.model_tier}) of pack {pool_plan.pack.name} {pool_plan.pack.version} "
             f"{pool_plan.pack.sha256}; this task to {pool_plan.assignments[uid]}; {'; '.join(pool_plan.reasons)}",
             admission_note(pool_plan)]
    record = next((d for d in pool_plan.admission.decisions if d.key == uid), None)
    if record is not None:
        notes.append(decision_note(record))
    return notes


def _review_twofold(self: HubOperations, hub: Any, ch: Any, uid: str, runners: Sequence[Any], pool_plan: Any, mode: str) -> Any:
    """The N_FOLD review of a combined answer the pool plan assigns (``twofold.run_twofold``): the source reviews in
    parallel, their validated outcomes as the bounded, request-scoped temporary context, the merged review with it, the
    combination; one signed verdicts audit records all of it, the context's record and its discard. Agents never gate
    clearance."""
    from .audit import verify_audit
    from .combine import combine_verdicts, combined_digest
    from .twofold import combined_layout, run_twofold
    from .validate import build_verdicts_audit, validate_overseer_verdict
    auditor = hub.auditor
    plan_twofold = pool_plan.twofold[uid]
    view = auditor.view(uid)
    layout = combined_layout(view)
    if layout is None or layout.n != len(plan_twofold.sources):
        raise ValueError("the pool plan reviews this task N_FOLD, but its journal holds no combined answer of that many sources")
    intake = self._review_intake(hub)
    task_audit = self._reference_audit(auditor, uid, view)
    consolidations = hub.latest_consolidations(uid) if mode == "informed" else []
    by_id = {r.agent_id: r for r in runners}

    def validate(message: Any, ctx: Any) -> Any:
        return validate_overseer_verdict(message, view, auditor.store, task_audit, auditor, intake=intake, live=ch, registry=getattr(ch, "registry", None),
                                         temporary_context=ctx)

    tw = run_twofold(layout=layout, view=view, plan_twofold=plan_twofold, runners=by_id, intake=intake, mode=mode, task_audit=task_audit,
                     consolidations=consolidations, validate=validate, combine=lambda xs: combine_verdicts(xs, intake=intake))
    parts = [*tw.sources, tw.merged]
    runs = tuple(r for p in parts for r in p.runs)
    assessments = tuple(a for p in parts for a in p.assessments)
    refused = tuple(x for p in parts for x in p.refused)
    errors = tuple(x for p in parts for x in p.runner_errors)
    combined = combine_verdicts(list(assessments), intake=intake) if assessments else None
    task_audits = [a for a in auditor.audits(uid) if a.scope == "task" and verify_audit(a, auditor.keyring)]
    reference = task_audits[-1] if task_audits else task_audit
    audit_ids = [a.audit_id for a in task_audits]
    superseding = tuple(audit_ids[audit_ids.index(task_audit.audit_id) + 1:]) if task_audit.audit_id in audit_ids else ()
    findings = list(combined.findings) if combined is not None else []
    for run in sorted(runs, key=lambda x: (x.agent_id, x.dossier_sha256 or "")):
        if run.status == "invalid" and run.finding is not None:
            findings.append(run.finding)
    rec = tw.context_record
    issued = sum(len(p.dossier_sha256) for p in parts)
    notes = [f"references task audit {reference.audit_id}" + (f" (the review started from task audit {task_audit.audit_id})" if reference is not task_audit else ""),
             f"review mode {mode}; N_FOLD review of a combined answer of {layout.n} sources (the twofold mode): {len(by_id)} agent(s); {issued} dossier(s) "
             f"issued; {len(assessments)} verdict(s) assessed"]
    unreviewed: list[int] = []
    for p, src in zip(tw.sources, layout.sources):
        confirmed = sum(1 for a in p.assessments for x in a.accusations if x.outcome == "confirmed")
        valid = sum(1 for a in p.assessments if getattr(a, "valid", False))
        head = f"source {src.index} of {layout.n} ({src.agent_id}, reports {', '.join(src.report_ids)}): "
        dossiers = f"dossiers {', '.join(d[:16] for d in p.dossier_sha256) or 'none'}"
        if valid:
            notes.append(head + f"reviewed before combination, in parallel, by {list(p.agent_ids)}; {dossiers}; {len(p.assessments)} verdict(s) assessed, "
                         f"{confirmed} accusation(s) confirmed")
            continue
        # architecture review after arena round 8: a source part no verdict was assessed on is NOT reviewed, and its note
        # says so with what each planned instance did, never "reviewed" (a non-success is never worded as a success)
        unreviewed.append(src.index)
        what = [f"{r.agent_id}: {r.status}" for r in p.runs] + [f"{a}: no dossier issued ({why})" for a, why in p.refused] \
            + [f"{a}: the runner failed ({err})" for a, err in p.runner_errors]
        notes.append(head + f"NOT reviewed before combination: no verdict was assessed on it ({'; '.join(what) or 'no instance ran'}); planned instances "
                     f"{list(p.agent_ids)}; {dossiers}; {len(p.assessments)} verdict(s) assessed, none valid: its silence in the temporary context shows "
                     "nothing, and no fault of it is known to the merged review")
    if rec:
        faults = sum(len(s["confirmed"]) for s in rec["sources"])
        notes.append(f"temporary context sha256 {tw.context_sha256}: request {rec['scope']['task_id']}/{rec['scope']['request_id']} only, {len(rec['sources'])} "
                     f"source(s), {faults} confirmed fault(s) of the source reviews ({rec['omitted']} omitted by the bound), {rec['bytes']} of at most "
                     f"{rec['max_bytes']} bytes, complete {str(rec['complete']).lower()}; validated outcomes only (no agent text, no finding code); "
                     + (f"source(s) {', '.join(str(i) for i in unreviewed)} NOT reviewed (reviewed 0: the context holds nothing of them); " if unreviewed else "")
                     + f"{'discarded after the request' if tw.context_discarded else 'NOT discarded'}")
        notes.append("temporary context as issued to the merged review: " + canonical_json(rec))
    confirmed_m = sum(1 for a in tw.merged.assessments for x in a.accusations if x.outcome == "confirmed")
    notes.append(f"merged review of the combinator's output (syntheses {', '.join(layout.synthesis_ids)}) with the temporary context, by "
                 f"{list(tw.merged.agent_ids)}; {len(tw.merged.assessments)} verdict(s) assessed, {confirmed_m} accusation(s) confirmed; carried faults "
                 + ("confirmed: " + "; ".join(f"{', '.join(c['claim_ids'])}" for c in tw.carried) if tw.carried else "confirmed: none"))
    if consolidations:
        notes.append("part dossiers show consolidated responses of their own answers only")
    notes.extend(_pool_notes(pool_plan, uid))
    for agent_id, reason in refused:
        notes.append(f"agent {agent_id}: no dossier issued ({reason}); no review")
    for agent_id, err in errors:
        notes.append(f"agent {agent_id}: the runner failed ({err}); no review")
    for run in sorted(runs, key=lambda x: (x.agent_id, x.dossier_sha256 or "")):
        pk = f"{run.pack.name} {run.pack.version} {run.pack.sha256}"
        what = {"submitted": "verdict accepted by the intake and assessed", "invalid": f"verdict rejected by the intake ({run.reason}): OVS-AGENT-005",
                "provider_error": f"provider failure ({run.reason}): no review", "refused_input": f"input refused ({run.reason}): no review"}[run.status]
        notes.append(f"agent {run.agent_id} under pack {pk} (dossier {str(run.dossier_sha256)[:16]}): {what}")
    if combined is not None:
        notes.append(f"combined assessment sha256 {combined_digest(combined)}; groups {len(combined.groups)}; human review queue "
                     f"{len(combined.review_queue)}; no voting on facts")
    else:
        notes.append("no verdict was assessed: this is no review, and it states nothing about the transfers")
    notes.append("OVS-AGENT-* findings never change a transfer's clearance; an agent's verdict is advisory and decides nothing")
    audit = build_verdicts_audit(reference=reference, channel_uid=uid, task_id=reference.task_id, request_id=reference.request_id, findings=findings,
                                 keyring=auditor.keyring, message_ids=list(reference.message_ids), notes=notes)
    _keep_verdicts(hub, uid, audit)
    return HubReview(audit=audit, task_audit=task_audit, mode=mode, runs=runs, assessments=assessments, combined=combined, refused=refused,
                     runner_errors=errors, superseding_audit_ids=superseding, twofold=tw)


HubOperations._review_twofold = _review_twofold  # type: ignore[attr-defined]

#: The one instance every :class:`~epinoic_overseer.audit.TransferAuditor` hands its hubs.
HUB_OPERATIONS = HubOperations()
