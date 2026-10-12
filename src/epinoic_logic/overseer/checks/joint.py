"""Joint consistency: the cross-agent pool as journaled, and every contradiction named claim-minimally.

* JOINT-004 (live): the pool before a call must be the pool the previous event left (nothing changes the channel's
  pool between transfers), every claim a call adds or changes must carry its outcome's translation problem, every
  formalized outcome of a delivered report that is not an echo of the request must be in the pool the call left (the
  channel pools every outcome that carries a problem), and the live pool must equal the last journaled snapshot.
* B3 independent joint consistency (batch):

  1. every formalized claim of the task at its current version is pooled from the JOURNALED OUTCOMES
     (:func:`derived_pool`: each delivered, non-echo report's outcomes that carry a problem, in delivery order, the
     latest version of a claim id winning and the supersession rule applied), never from the channel's own pool, so a
     channel that delivers a formalized outcome without pooling it cannot keep its contradiction from the check;
  2. ``check_cross_report_consistency`` runs as an auditor run (unsigned, then signed under ``overseer-run``) with
     ``assumed_readings`` from the snapshot's ambiguous flags; it attributes claim-minimally and re-checks after
     setting each conflict aside, so one contradiction never hides another;
  3. each auditor conflict set S counts as NAMED only if some receipt named a set T with S a subset of T
     (INT-CONFLICT-001, or INT-CONFLICT-005 for a self-refuting claim, S = {c}); otherwise S is JOINT-001, citing the
     auditor's signed joint run and its attribution runs;
  4. each channel-named set T is re-run alone at the versions it had when it was named (that event's pool snapshot
     after the call, which is what the receipt named; a claim id the call did not touch keeps its earlier version);
     a CONSISTENT result is JOINT-003 (a false conflict);
  5. a joint check that is undecided, cannot be built, or breaches ``JOINT_LIMITS`` is JOINT-002 (warning).
"""
from __future__ import annotations

from typing import Optional

from ...engine.statuses import VerificationStatus as S
from ...integrity.cross_check import JOINT_LIMITS, check_cross_report_consistency, joint_problem
from ...ir.canonical import canonical_json, problem_digest, sha256_hex
from ...engine.runner import verify
from ..view import REPORT_KINDS, Transfer
from . import CheckContext
from .synthesis import named_conflict_sets

__all__ = ["check_pool", "check_live_pool", "independent_joint", "JointOutcome", "derived_pool", "PooledClaim"]


def _entries(pool) -> dict[str, tuple[str, bool]]:
    return {p.claim_id: (p.problem_digest, p.ambiguous) for p in pool}


def _pairs(*pools) -> list[tuple[Optional[str], str]]:
    return [(p.report_id, p.claim_id) for pool in pools for p in pool]


def _pools_outcomes(t: Transfer) -> bool:
    """Whether the channel pooled this transfer's formalized outcomes: a delivered report that is not an echo of the
    request (INT-REQ-011: verified for the record, never pooled)."""
    return (t.kind in REPORT_KINDS and t.delivered and t.receipt is not None and t.report is not None and not t.digest_only
            and not any(f.code == "INT-REQ-011" for f in t.receipt.findings))


def check_pool(ctx: CheckContext, t: Transfer) -> None:
    """JOINT-004 for one event: the pool before it equals the previous event's pool after; additions carry outcomes;
    every formalized outcome the event delivered is pooled. For a transfer whose receipt content is not held (journaled
    digest-only past the bound: AUDIT-005) only the continuity is decided, never an accusation about its outcomes."""
    if ctx.view.degraded:
        return
    ids = t.ids()
    prev = ctx.view.previous(t.seq)
    before = _entries(t.pool_before)
    if prev is not None:
        after_prev = _entries(prev.pool_after)
        if before != after_prev:
            changed = sorted(set(before) ^ set(after_prev) | {c for c in set(before) & set(after_prev) if before[c] != after_prev[c]})
            mids, rids, aids = ctx.message_ids_for_claims(changed, pairs=_pairs(t.pool_before, prev.pool_after))
            ctx.ovs(t.seq, "OVS-JOINT-004", f"the channel's cross-agent pool changed between transfers {prev.seq} and {t.seq} (claims {changed[:8]}): nothing the channel issued changed it",
                    claim_ids=changed, message_ids=ids["message_ids"] + mids, report_ids=rids, agent_ids=aids)
    if t.digest_only or (t.receipt is None and t.receipt_dump is None and t.event.receipt_sha256 is not None):
        return  # the receipt's content is not held (past the journal bound: AUDIT-005 says so); only the continuity above is decidable
    after = _entries(t.pool_after)
    added = [c for c in after if c not in before or after[c][0] != before[c][0]]
    outcome_digests: dict[str, set[str]] = {}
    if t.receipt is not None:
        for o in t.receipt.outcomes:
            if o.translation.problem is not None:
                outcome_digests.setdefault(o.claim_id, set()).add(problem_digest(o.translation.problem))
    wrong = [c for c in added if after[c][0] not in outcome_digests.get(c, set())]
    if wrong:
        ctx.ovs(t.seq, "OVS-JOINT-004", f"{t.kind} {t.message_id} pooled formalizations of claims {wrong[:8]} that no outcome on its receipt carries", claim_ids=wrong, **ids)
    if _pools_outcomes(t):
        unpooled = sorted({o.claim_id for o in t.receipt.outcomes if o.translation.problem is not None and o.claim_id not in wrong  # one fault, one finding
                           and after.get(o.claim_id, (None,))[0] != problem_digest(o.translation.problem)})
        if unpooled:
            ctx.ovs(t.seq, "OVS-JOINT-004", f"{t.kind} {t.message_id} delivered formalized outcomes of claims {unpooled[:8]} that the channel did not put in the "
                    "cross-agent pool: their contradictions with other claims would go unchecked", claim_ids=unpooled, **ids)


class PooledClaim:
    """One claim of :func:`derived_pool`: its current problem, reading flag and the delivery it came from."""
    __slots__ = ("claim_id", "problem", "ambiguous", "report_id", "agent_id", "seq")

    def __init__(self, claim_id: str, problem, ambiguous: bool, report_id: str, agent_id: str, seq: int) -> None:
        self.claim_id, self.problem, self.ambiguous, self.report_id, self.agent_id, self.seq = claim_id, problem, ambiguous, report_id, agent_id, seq


def derived_pool(view, upto_seq: Optional[int] = None) -> list[PooledClaim]:
    """The cross-agent pool as the journaled OUTCOMES define it (the channel's pooling rule re-applied, never its own
    pool): in delivery order, every delivered non-echo report first supersedes the claims of the same ids that the same
    agent formalized in another report (the channel's ``_supersession`` rule; a report that answers nothing supersedes
    nothing), then pools each of its outcomes that carries a problem, keyed by claim id (a later version wins)."""
    from ...channel.bus import _material_claims
    from ...translate.contracts import TranslationStatus
    pool: dict[str, PooledClaim] = {}
    for t in view.transfers:
        if upto_seq is not None and t.seq > upto_seq:
            break
        if not _pools_outcomes(t):
            continue
        rep = t.report
        answers = not any(f.code in ("INT-REQ-011", "INT-REQ-012") for f in t.receipt.findings) and bool(_material_claims(rep))
        if answers:
            for c in rep.claims:
                held = pool.get(c.claim_id)
                if held is not None and held.agent_id == rep.agent_id and held.report_id != rep.report_id:
                    del pool[c.claim_id]
        for o in t.receipt.outcomes:
            if o.translation.problem is None:
                continue
            pool.pop(o.claim_id, None)  # re-inserted last: the pool keeps insertion order like the channel's dict
            pool[o.claim_id] = PooledClaim(o.claim_id, o.translation.problem, o.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION,
                                           rep.report_id, rep.agent_id, t.seq)
    return list(pool.values())


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
        mids, rids, aids = ctx.message_ids_for_claims(changed, pairs=_pairs(_pool(ctx.live), last.pool_after))
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
    """B3: the auditor's own joint consistency check over the pool the journaled outcomes define; JOINT-001/002/003."""
    out = JointOutcome()
    view = ctx.view
    if view.degraded or not view.transfers:
        return out
    last = view.transfers[-1]
    pool = derived_pool(view)
    pairs = [(p.report_id, p.claim_id) for p in pool]
    out.pool_size = len(pool)
    ctx.coverage.joint_pool_size = len(pool)
    plan = view.plan_at(last.seq)
    request_id = plan.request_id if plan is not None else view.request_id
    cfg = view.config_at(last.seq)
    probs = [p.problem for p in pool]
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
                mids, rids, aids = ctx.message_ids_for_claims(f.claim_ids, pairs=pairs)
                ctx.ovs(last.seq, "OVS-JOINT-002", f"the independent joint check over {len(probs)} pooled claims did not decide ({f.code}: {f.message[:200]})",
                        claim_ids=f.claim_ids, message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=f.formal_result_id or run_id)
        if run_status is not None and run_status not in (S.CONSISTENT.value, S.INCONSISTENT_PREMISES.value) and not any(f.code.startswith(("INT-CONFLICT-004", "INT-GLOSSARY")) for f in findings):
            ctx.ovs(last.seq, "OVS-JOINT-002", f"the independent joint check over {len(probs)} pooled claims returned {run_status}", formal_result_id=run_id)
    named = named_conflict_sets(ctx)
    for claims, rid, related, code in out.sets:
        covered = any(claims <= t_claims for _s, t_claims, _r, _t_code in named)
        if covered:
            continue
        mids, rids, aids = ctx.message_ids_for_claims(claims, pairs=pairs)
        what = "a self-refuting claim" if code == "INT-CONFLICT-005" else "a contradiction"
        ctx.ovs(last.seq, "OVS-JOINT-001", f"{what} between {sorted(claims)} that no receipt of the task named (auditor's independent joint check, claim-minimal)",
                claim_ids=sorted(claims), message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=rid, related_result_ids=[r for r in related if r] + ([out.run_id] if out.run_id else []))
    _false_conflicts(ctx, named)
    return out


def _false_conflicts(ctx: CheckContext, named) -> None:
    """JOINT-003: each channel-named set re-run alone at the versions it had when it was named. A named claim that had no
    formalization in the pool at that point is JOINT-003 itself, and the pooled part of the set is still re-run (rule
    ``padded-conflict``, review round 3: padding a false conflict with an unformalized claim never hides it)."""
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
        # the versions the receipt named are the ones the call left in the pool (pool_after wins); a claim the call did not
        # touch keeps the version it had before
        snap = {p.claim_id: p for p in list(t.pool_before) + list(t.pool_after)}
        pool = [snap[c] for c in sorted(claims) if c in snap]
        unpooled = sorted(c for c in claims if c not in snap)
        if unpooled:
            # the channel names conflicts only among pooled formalizations: a named claim with none at that point is a
            # conflict the engine never decided on that claim (rule ``padded-conflict``); the pooled part is re-run below
            pmids, prids, paids = ctx.message_ids_for_claims(unpooled)
            ctx.ovs(seq, "OVS-JOINT-003", f"{code} names {sorted(claims)} (receipt of {t.message_id}) but claims {unpooled} had no formalization in the cross-agent pool "
                    "at that point: a conflict named on a claim the engine never decided", claim_ids=sorted(claims),
                    message_ids=([t.message_id] if t.message_id else []) + pmids, report_ids=prids, agent_ids=paids, related_result_ids=[rid] if rid else [])
        if not pool:
            continue
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
        mids, rids, aids = ctx.message_ids_for_claims(claims, pairs=_pairs(pool))
        if status == S.CONSISTENT.value:
            part = f" (the pooled part {sorted(c.claim_id for c in pool)})" if unpooled else ""
            ctx.ovs(seq, "OVS-JOINT-003", f"{code} names {sorted(claims)} (receipt of {t.message_id}) but the engine finds them{part} consistent at the versions they had then: a false conflict",
                    claim_ids=sorted(claims), message_ids=[t.message_id] + mids if t.message_id else mids, report_ids=rids, agent_ids=aids, formal_result_id=res_id, related_result_ids=[rid] if rid else [])
        elif status is None or status != S.INCONSISTENT_PREMISES.value:
            ctx.ovs(seq, "OVS-JOINT-002", f"the re-check of the conflict {sorted(claims)} named by {code} could not be decided ({status or codes})",
                    claim_ids=sorted(claims), message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=res_id)
