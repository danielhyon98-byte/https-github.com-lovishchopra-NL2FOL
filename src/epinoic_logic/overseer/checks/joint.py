"""Joint consistency: the cross-agent pool as journaled, and every contradiction named claim-minimally.

* JOINT-004 (live): the pool before a call must be the pool the previous event left (nothing changes the channel's
  pool between transfers), every claim a call adds or changes must carry its outcome's translation problem, and the
  live pool must equal the last journaled snapshot.
* B3 independent joint consistency (batch):

  1. every formalized claim of the task at its current version is pooled from the last journaled pool snapshot, the
     problems resolved from the journaled outcomes by ``(claim_id, problem_digest)``, in snapshot order;
  2. ``check_cross_report_consistency`` runs as an auditor run (unsigned, then signed under ``overseer-run``) with
     ``assumed_readings`` from the snapshot's ambiguous flags; it attributes claim-minimally and re-checks after
     setting each conflict aside, so one contradiction never hides another;
  3. each auditor conflict set S counts as NAMED only if some receipt named a set T with S a subset of T
     (INT-CONFLICT-001, or INT-CONFLICT-005 for a self-refuting claim, S = {c}); otherwise S is JOINT-001, citing the
     auditor's signed joint run and its attribution runs;
  4. each channel-named set T is re-run alone at the versions it had when it was named (that event's pool snapshot);
     a CONSISTENT result is JOINT-003 (a false conflict);
  5. a joint check that is undecided, cannot be built, or breaches ``JOINT_LIMITS`` is JOINT-002 (warning).
"""
from __future__ import annotations

from typing import Optional

from ...engine.statuses import VerificationStatus as S
from ...integrity.cross_check import JOINT_LIMITS, check_cross_report_consistency, joint_problem
from ...ir.canonical import canonical_json, problem_digest, sha256_hex
from ...engine.runner import verify
from ..view import Transfer
from . import CheckContext
from .synthesis import named_conflict_sets

__all__ = ["check_pool", "check_live_pool", "independent_joint", "JointOutcome"]


def _entries(pool) -> dict[str, tuple[str, bool]]:
    return {p.claim_id: (p.problem_digest, p.ambiguous) for p in pool}


def check_pool(ctx: CheckContext, t: Transfer) -> None:
    """JOINT-004 for one event: the pool before it equals the previous event's pool after; additions carry outcomes."""
    if ctx.view.degraded:
        return
    ids = t.ids()
    prev = ctx.view.previous(t.seq)
    before = _entries(t.pool_before)
    if prev is not None:
        after_prev = _entries(prev.pool_after)
        if before != after_prev:
            changed = sorted(set(before) ^ set(after_prev) | {c for c in set(before) & set(after_prev) if before[c] != after_prev[c]})
            mids, rids, aids = ctx.message_ids_for_claims(changed)
            ctx.ovs(t.seq, "OVS-JOINT-004", f"the channel's cross-agent pool changed between transfers {prev.seq} and {t.seq} (claims {changed[:8]}): nothing the channel issued changed it",
                    claim_ids=changed, message_ids=ids["message_ids"] + mids, report_ids=rids, agent_ids=aids)
    after = _entries(t.pool_after)
    added = [c for c in after if c not in before or after[c][0] != before[c][0]]
    if not added:
        return
    outcome_digests: dict[str, set[str]] = {}
    if t.receipt is not None:
        for o in t.receipt.outcomes:
            if o.translation.problem is not None:
                outcome_digests.setdefault(o.claim_id, set()).add(problem_digest(o.translation.problem))
    wrong = [c for c in added if after[c][0] not in outcome_digests.get(c, set())]
    if wrong:
        ctx.ovs(t.seq, "OVS-JOINT-004", f"{t.kind} {t.message_id} pooled formalizations of claims {wrong[:8]} that no outcome on its receipt carries", claim_ids=wrong, **ids)


def check_live_pool(ctx: CheckContext) -> None:
    """JOINT-004 against the live channel: its pool now equals the last journaled snapshot."""
    if ctx.view.degraded or ctx.live is None or not ctx.view.transfers:
        return
    from ...channel.events import _pool
    last = ctx.view.transfers[-1]
    live = _entries(_pool(ctx.live))
    snap = _entries(last.pool_after)
    if live != snap:
        changed = sorted(set(live) ^ set(snap) | {c for c in set(live) & set(snap) if live[c] != snap[c]})
        mids, rids, aids = ctx.message_ids_for_claims(changed)
        ctx.ovs(last.seq, "OVS-JOINT-004", f"the channel's live cross-agent pool differs from the snapshot journaled after transfer {last.seq} (claims {changed[:8]})",
                claim_ids=changed, message_ids=mids, report_ids=rids, agent_ids=aids)


class JointOutcome:
    def __init__(self) -> None:
        self.sets: list[tuple[frozenset[str], Optional[str], list[str], str]] = []  # (claims, result id, related, code)
        self.pool_size = 0
        self.run_id: Optional[str] = None


def _problems_for(ctx: CheckContext, pool, upto_seq: int):
    probs, missing = [], []
    for p in pool:
        prob = ctx.view.outcome_problem(p.claim_id, p.problem_digest, upto_seq)
        (probs.append(prob) if prob is not None else missing.append(p.claim_id))
    return probs, missing


def independent_joint(ctx: CheckContext) -> JointOutcome:
    """B3: the auditor's own joint consistency check over the final pool; JOINT-001/002/003."""
    out = JointOutcome()
    view = ctx.view
    if view.degraded or not view.transfers:
        return out
    last = view.transfers[-1]
    pool = list(last.pool_after)
    out.pool_size = len(pool)
    ctx.coverage.joint_pool_size = len(pool)
    plan = view.plan_at(last.seq)
    request_id = plan.request_id if plan is not None else view.request_id
    cfg = view.config_at(last.seq)
    probs, missing = _problems_for(ctx, pool, last.seq)
    if missing:
        mids, rids, aids = ctx.message_ids_for_claims(missing)
        ctx.ovs(last.seq, "OVS-JOINT-002", f"the independent joint check cannot resolve the journaled problems of pooled claims {missing[:8]} (no journaled outcome carries them)",
                claim_ids=missing, message_ids=mids, report_ids=rids, agent_ids=aids)
    if len(probs) >= 2:  # the channel's rule: a conflict is a cross-claim notion, checked once two claims are pooled
        assumed = frozenset(p.claim_id for p in pool if p.ambiguous)
        memo_key = "B3|" + sha256_hex(canonical_json([[problem_digest(p) for p in probs], cfg.model_dump(mode="json"), sorted(assumed), request_id]))
        memo = ctx.store.memo_get(memo_key)
        if memo is None:
            def run():
                return check_cross_report_consistency(probs, request_id=request_id, config=cfg, signing_key=None, assumed_readings=assumed)
            (res, findings), run_ids = ctx.auditor_run(run, seq=last.seq)
            memo = (res.result_id if res is not None else None, res.status.value if res is not None else None, [f.model_dump(mode="json") for f in findings], run_ids)
            ctx.store.memo_put(memo_key, memo)
        else:
            for rid in memo[3]:
                if rid not in ctx.auditor_result_ids:
                    ctx.auditor_result_ids.append(rid)
        run_id, run_status, fdumps, run_ids = memo
        out.run_id = run_id
        from ...integrity.contracts import IntegrityFinding
        findings = [IntegrityFinding.model_validate(d) for d in fdumps]
        for f in findings:
            if f.code in ("INT-CONFLICT-001", "INT-CONFLICT-005"):
                claims = frozenset(f.claim_ids if f.code == "INT-CONFLICT-001" else f.claim_ids[-1:])
                out.sets.append((claims, f.formal_result_id, list(f.related_result_ids), f.code))
            elif f.code in ("INT-CONFLICT-004", "INT-GLOSSARY-004", "INT-GLOSSARY-006", "INT-GLOSSARY-007", "INT-GLOSSARY-001"):
                mids, rids, aids = ctx.message_ids_for_claims(f.claim_ids)
                ctx.ovs(last.seq, "OVS-JOINT-002", f"the independent joint check over {len(probs)} pooled claims did not decide ({f.code}: {f.message[:200]})",
                        claim_ids=f.claim_ids, message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=f.formal_result_id or run_id)
        if run_status is not None and run_status not in (S.CONSISTENT.value, S.INCONSISTENT_PREMISES.value) and not any(f.code.startswith(("INT-CONFLICT-004", "INT-GLOSSARY")) for f in findings):
            ctx.ovs(last.seq, "OVS-JOINT-002", f"the independent joint check over {len(probs)} pooled claims returned {run_status}", formal_result_id=run_id)
    named = named_conflict_sets(ctx)
    for claims, rid, related, code in out.sets:
        covered = any(claims <= t_claims for _s, t_claims, _r, _t_code in named)
        if covered:
            continue
        mids, rids, aids = ctx.message_ids_for_claims(claims)
        what = "a self-refuting claim" if code == "INT-CONFLICT-005" else "a contradiction"
        ctx.ovs(last.seq, "OVS-JOINT-001", f"{what} between {sorted(claims)} that no receipt of the task named (auditor's independent joint check, claim-minimal)",
                claim_ids=sorted(claims), message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=rid, related_result_ids=[r for r in related if r] + ([out.run_id] if out.run_id else []))
    _false_conflicts(ctx, named)
    return out


def _false_conflicts(ctx: CheckContext, named) -> None:
    """JOINT-003: each channel-named set re-run alone at the versions it had when it was named."""
    view = ctx.view
    done: set[tuple[int, frozenset[str]]] = set()
    for seq, claims, rid, code in named:
        key = (seq, claims)
        if key in done:
            continue
        done.add(key)
        t = view.by_seq.get(seq)
        if t is None:
            continue
        snap = {p.claim_id: p for p in list(t.pool_after) + list(t.pool_before)}
        pool = [snap[c] for c in sorted(claims) if c in snap]
        if len(pool) != len(claims):
            continue  # the named claims were not all pooled at that point (e.g. named against an earlier version); nothing to re-run
        probs, missing = _problems_for(ctx, pool, seq)
        if missing:
            continue
        plan = view.plan_at(seq)
        request_id = plan.request_id if plan is not None else view.request_id
        cfg = view.config_at(seq).model_copy(update={"produce_unsat_core": True})
        memo_key = "J3|" + sha256_hex(canonical_json([[problem_digest(p) for p in probs], cfg.model_dump(mode="json"), request_id]))
        memo = ctx.store.memo_get(memo_key)
        if memo is None:
            def run():
                joint, f, _jm = joint_problem(probs, request_id=request_id, joint_id="overseer-recheck")
                if joint is None:
                    return None, [x.code for x in f]
                return verify(joint, cfg, JOINT_LIMITS), []
            (res, codes), run_ids = ctx.auditor_run(run, seq=seq)
            memo = (res.result_id if res is not None else None, res.status.value if res is not None else None, codes, run_ids)
            ctx.store.memo_put(memo_key, memo)
        else:
            for r in memo[3]:
                if r not in ctx.auditor_result_ids:
                    ctx.auditor_result_ids.append(r)
        res_id, status, codes, _ids = memo
        mids, rids, aids = ctx.message_ids_for_claims(claims)
        if status == S.CONSISTENT.value:
            ctx.ovs(seq, "OVS-JOINT-003", f"{code} names {sorted(claims)} (receipt of {t.message_id}) but the engine finds them consistent at the versions they had then: a false conflict",
                    claim_ids=sorted(claims), message_ids=[t.message_id] + mids if t.message_id else mids, report_ids=rids, agent_ids=aids, formal_result_id=res_id, related_result_ids=[rid] if rid else [])
        elif status is None or status != S.INCONSISTENT_PREMISES.value:
            ctx.ovs(seq, "OVS-JOINT-002", f"the re-check of the conflict {sorted(claims)} named by {code} could not be decided ({status or codes})",
                    claim_ids=sorted(claims), message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=res_id)
