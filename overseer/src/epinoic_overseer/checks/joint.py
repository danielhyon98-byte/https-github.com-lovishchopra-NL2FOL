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
     a CONSISTENT result is JOINT-003 (a false conflict). Rule ``pooled-only-conflict`` (round-8 clearance c1): a set the
     re-run still finds inconsistent is re-run once more with its symbols READ APART as the channel reads them before it
     charges a conflict (``integrity.cross_check``: a symbol whose glosses name different quantities in two claims,
     ``split_by_gloss``, and a candidate value a claim tests and rejects, ``rename_candidates_apart``, each renamed apart
     per claim). When that reading is CONSISTENT the conflict exists only through pooling one name for two things (maa-t14:
     "x = −5 is rejected because it does not satisfy x > 4" pooled with the domain x > 4 of another claim), so it is
     JOINT-003 too; when it cannot be built or decided, JOINT-002 (warning), so an agent's false_conflict accusation of it
     is left unresolved, never refuted by a re-run that could not see the pooling;
  5. a joint check that is undecided, cannot be built, or breaches ``JOINT_LIMITS`` is JOINT-002 (warning).
"""
from __future__ import annotations

import json
import re
from fractions import Fraction
from typing import Optional

from epinoic_logic.api.engine import VerificationStatus as S
from epinoic_logic.api.integrity import JOINT_LIMITS, check_cross_report_consistency, joint_problem, split_by_gloss

try:  # the channel's candidate reading (round-8 clearance c1); without it only the glosses are read apart
    from epinoic_logic.api.integrity import rename_candidates_apart as _rename_candidates_apart
except ImportError:  # pragma: no cover - an older channel
    _rename_candidates_apart = None

from epinoic_logic.api.ir import canonical_json, problem_digest, sha256_hex
from epinoic_logic.api.engine import verify
from ..view import REPORT_KINDS, Transfer
from . import CheckContext
from .synthesis import named_conflict_sets

#: Rule ``pooled-only-conflict`` (module docstring, step 4): a named conflict that exists only through pooling one name for two
#: quantities or for a rejected candidate is a false conflict.
POOLED_ONLY_RULE = "pooled-only-conflict"
#: Rule ``evaluation-point`` (round-9 clearance c2, the c2 lenses: maa-t15 m5.3 "Check: at x = 0, g(0) = 3 and h(3) = 1 = 0 + 1." was
#: pooled with m7.1 "x + 1 = (x − 3)/2", whose solution is −5, and charged INT-CONFLICT-001 at error level): a value at which a claim
#: evaluates or checks an expression ("at x = 0", "when x = 2", "for x = 3", "with x = 1") is local to that claim, like a candidate it
#: rejects: the symbol it fixes is read apart in that claim before a conflict is charged. Read from the claim's text by one bounded pattern.
EVALUATION_POINT_RULE = "evaluation-point"
_EVAL_POINT_RE = re.compile(r"\b(?:at|when|for|with|if|where)[ \t]{1,3}([A-Za-z][A-Za-z0-9_]{0,15})[ \t]{0,3}=[ \t]{0,3}([−-]?)[ \t]{0,2}(\d{1,12}(?:\.\d{1,12})?)(?![\d.])",
                            re.IGNORECASE)
_IR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

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


def _revised_report_id(view, t: Transfer) -> Optional[str]:
    """The report id a revision's revision request revises (``None`` for an answer to any other request)."""
    if t.kind not in ("response", "response_text"):
        return None
    req = view.by_message.get(t.in_reply_to or "")
    block = req.request.revision if req is not None and req.request is not None else None
    return block.revises_report_id if block is not None else None


def derived_pool(view, upto_seq: Optional[int] = None) -> list[PooledClaim]:
    """The cross-agent pool as the journaled OUTCOMES define it (the channel's pooling rule re-applied, never its own
    pool): in delivery order, every delivered non-echo report first supersedes the claims of the same ids that the same
    agent formalized in another report (the channel's ``_supersession`` rule; a report that answers nothing supersedes
    nothing; a revision first supersedes every claim of the report its revision request revises), then pools each of its
    outcomes that carries a problem, keyed by claim id (a later version wins)."""
    from epinoic_logic.api.channel import material_claims as _material_claims
    from epinoic_logic.api.translate import TranslationStatus
    pool: dict[str, PooledClaim] = {}
    for t in view.transfers:
        if upto_seq is not None and t.seq > upto_seq:
            break
        if not _pools_outcomes(t):
            continue
        rep = t.report
        answers = not any(f.code in ("INT-REQ-011", "INT-REQ-012") for f in t.receipt.findings) and bool(_material_claims(rep))
        if answers:
            # a revision supersedes the report its revision request revises, whatever their claims share: every pooled claim
            # of that report leaves the pool (the channel's ``_revision_supersession``, design section 53)
            revised = _revised_report_id(view, t)
            if revised is not None and revised != rep.report_id:
                for cid in [cid for cid, held in pool.items() if held.report_id == revised and held.agent_id == rep.agent_id]:
                    del pool[cid]
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
    from epinoic_logic.api.channel import channel_pool as _pool
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
        from epinoic_logic.api.integrity import IntegrityFinding
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
        elif len(probs) >= 2:
            # rule pooled-only-conflict: the same set with its symbols read apart as the channel reads them
            apart_id, apart_status, how = _apart_recheck(ctx, probs, request_id=request_id, cfg=cfg, seq=seq)
            if not how:
                continue  # nothing to read apart: the conflict is the claims' own, as encoded
            if apart_status == S.CONSISTENT.value:
                ctx.ovs(seq, "OVS-JOINT-003", f"{code} names {sorted(claims)} (receipt of {t.message_id}), but the conflict exists only through pooling: with "
                        f"{how} read apart, as the channel reads them before it charges a conflict, the engine finds the claims consistent at the versions "
                        f"they had then: a false conflict (rule {POOLED_ONLY_RULE})", claim_ids=sorted(claims),
                        message_ids=[t.message_id] + mids if t.message_id else mids, report_ids=rids, agent_ids=aids, formal_result_id=apart_id,
                        related_result_ids=[x for x in (res_id, rid) if x])
            elif apart_status != S.INCONSISTENT_PREMISES.value:
                ctx.ovs(seq, "OVS-JOINT-002", f"the re-check of the conflict {sorted(claims)} named by {code} with {how} read apart could not be decided "
                        f"({apart_status or 'not buildable'}; rule {POOLED_ONLY_RULE}): whether it exists only through pooling is undecided",
                        claim_ids=sorted(claims), message_ids=mids, report_ids=rids, agent_ids=aids, formal_result_id=apart_id or res_id)


def evaluation_points(text: Optional[str]) -> list[tuple[str, Fraction]]:
    """Rule ``evaluation-point``: ``(symbol, value)`` for every value at which ``text`` says it evaluates or checks ("at x = 0")."""
    out: list[tuple[str, Fraction]] = []
    for m in _EVAL_POINT_RE.finditer((text or "")[:4000]):
        try:
            v = Fraction(m.group(3))
        except (ValueError, ZeroDivisionError):
            continue
        out.append((m.group(1), -v if m.group(2) else v))
    return out


def _literal_value(node) -> Optional[Fraction]:
    if isinstance(node, dict) and node.get("op") in ("int", "real"):
        try:
            return Fraction(str(node.get("value")))
        except (ValueError, ZeroDivisionError):
            return None
    if isinstance(node, dict) and node.get("op") == "neg":
        inner = _literal_value(node.get("arg"))
        return -inner if inner is not None else None
    return None


def _mentions(node, names: set) -> bool:
    """Whether ``node`` (IR JSON) mentions a symbol of ``names`` (iteratively)."""
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") == "var" and n.get("name") in names:
                return True
            stack.extend(v for k, v in n.items() if k != "value")
        elif isinstance(n, list):
            stack.extend(n)
    return False


def _renamed_symbol(node, old: str, new: str):
    if isinstance(node, dict):
        if node.get("op") == "var" and node.get("name") == old:
            return {**node, "name": new}
        return {k: (_renamed_symbol(v, old, new) if k != "value" else v) for k, v in node.items()}
    if isinstance(node, list):
        return [_renamed_symbol(v, old, new) for v in node]
    return node


def rename_points_apart(probs: list, texts: list[Optional[str]]) -> tuple[list, dict[str, list[str]], list[str]]:
    """Rule ``evaluation-point`` (:data:`EVALUATION_POINT_RULE`): ``(problems, renamed, unread)``. Each problem whose claim text
    (``texts``, aligned with ``probs``) says it evaluates or checks at ``x = v`` and that holds a premise fixing a numeric symbol at
    that value (``x = v``: the symbol of that name, or, when the text's name is not a symbol of the problem, the one symbol the
    problem fixes at ``v``) has that symbol renamed apart in that problem only (``renamed``: claim id -> symbols); ``unread`` names
    the claims whose text states an evaluation point that no premise of theirs fixes (the pooling is then undecided). Data only:
    each problem is copied as JSON, renamed, and validated again as an IR problem."""
    from epinoic_logic.api.ir import Problem
    out, renamed, unread = [], {}, []
    for k, prob in enumerate(probs):
        points = evaluation_points(texts[k] if k < len(texts) else None)
        if not points:
            out.append(prob)
            continue
        try:
            data = json.loads(prob.model_dump_json(exclude_none=True))
            sorts = {s["name"]: s.get("sort") for s in data.get("symbols") or []}
            fixed: dict[str, set] = {}
            for pr in data.get("premises") or []:
                e = pr.get("expr") or {}
                if e.get("op") != "eq":
                    continue
                for var, lit in ((e.get("left"), e.get("right")), (e.get("right"), e.get("left"))):
                    v = _literal_value(lit)
                    if isinstance(var, dict) and var.get("op") == "var" and v is not None and sorts.get(var.get("name")) in ("Int", "Real"):
                        fixed.setdefault(str(var["name"]), set()).add(v)
            names = []
            for name, value in points:
                hits = [n for n, vs in fixed.items() if value in vs and n == name]
                if not hits:
                    by_value = [n for n, vs in fixed.items() if value in vs]
                    hits = by_value if len(by_value) == 1 else []
                if not hits:
                    unread.append(str(prob.claim_id))
                names += [n for n in hits if n not in names]
            if not names:
                out.append(prob)
                continue
            # every numeric symbol the claim's own premises define from an evaluated one is evaluated at that point too ("gx = 2x + 3"
            # beside "x = 0": g(0)), so it is read apart with it; a fixed point of the premises, bounded by the problem's symbols
            changed = True
            while changed and len(names) < len(sorts):
                changed = False
                for pr in data.get("premises") or []:
                    e = pr.get("expr") or {}
                    if e.get("op") != "eq":
                        continue
                    for var, rhs in ((e.get("left"), e.get("right")), (e.get("right"), e.get("left"))):
                        if not (isinstance(var, dict) and var.get("op") == "var" and sorts.get(var.get("name")) in ("Int", "Real")):
                            continue
                        y = str(var["name"])
                        if y not in names and _mentions(rhs, set(names)):
                            names.append(y)
                            changed = True
            taken = set(sorts)
            for n in names:
                new = f"{n}_at{k}"[:60]
                i = 0
                while new in taken or not _IR_NAME_RE.match(new):
                    i += 1
                    new = f"at{k}_{i}"
                taken.add(new)
                data = _renamed_symbol(data, n, new)
                for sym in data.get("symbols") or []:
                    if sym.get("name") == n:
                        sym["name"] = new
            out.append(Problem.model_validate(data))
            renamed[str(prob.claim_id)] = names
        except Exception:  # noqa: BLE001 - a problem that cannot be read apart is pooled as it is (and its pooling is undecided)
            unread.append(str(prob.claim_id))
            out.append(prob)
    return out, renamed, sorted(set(unread))


def _claim_texts(ctx: CheckContext, claim_ids, upto_seq: int) -> dict[str, str]:
    """The text of each claim id as the latest delivered report holding it, up to ``upto_seq``, states it."""
    wanted = set(claim_ids)
    out: dict[str, str] = {}
    for t in ctx.view.transfers:
        if t.seq > upto_seq:
            break
        rep = getattr(t, "report", None)
        if rep is None or t.kind not in REPORT_KINDS:
            continue
        for c in rep.claims:
            if c.claim_id in wanted:
                out[c.claim_id] = c.claim_text
    return out


def _apart_recheck(ctx: CheckContext, probs: list, *, request_id: str, cfg, seq: int) -> tuple[Optional[str], Optional[str], str]:
    """Rule ``pooled-only-conflict``: ``(result id, status, what was read apart)`` of the auditor's run of ``probs`` pooled
    with its symbols read apart (glosses naming different quantities, candidates a claim rejects, and, rule ``evaluation-point``,
    a value a claim evaluates or checks at); ``what`` is empty when nothing is read apart (the run is then not made). Memoised in
    the store like every auditor run."""
    try:
        apart, splits = split_by_gloss(list(probs))
        candidates: dict = {}
        if _rename_candidates_apart is not None:
            apart, candidates = _rename_candidates_apart(apart)
        texts = _claim_texts(ctx, [p.claim_id for p in apart], seq)
        apart, points, unread = rename_points_apart(apart, [texts.get(p.claim_id) for p in apart])
    except Exception as exc:  # noqa: BLE001 - a reading that fails cannot clear a conflict: undecided
        return None, None, f"the symbols (the reading failed: {type(exc).__name__})"
    parts = []
    if splits:
        parts.append("the symbol(s) " + ", ".join(sorted(splits)[:6]) + " (glossed as different quantities)")
    if candidates:
        named = sorted({n for v in candidates.values() for n, _new, _aid in v})
        parts.append("the candidate value(s) of " + ", ".join(named[:6]) + " that claim(s) " + ", ".join(sorted(candidates)[:6]) + " test and reject")
    if points:
        parts.append("the value(s) of " + ", ".join(sorted({n for v in points.values() for n in v})[:6]) + " that claim(s) "
                     + ", ".join(sorted(points)[:6]) + f" evaluate or check at (rule {EVALUATION_POINT_RULE})")
    if unread and not parts:
        # a claim says it evaluates at a value no premise of its own fixes: whether the conflict exists only through pooling is undecided
        return None, None, f"the evaluation point(s) of claim(s) {', '.join(unread[:6])} (no premise fixes them; rule {EVALUATION_POINT_RULE})"
    if not parts:
        return None, None, ""
    how = " and ".join(parts)
    memo_key = "J3A|" + sha256_hex(canonical_json([[problem_digest(p) for p in apart], cfg.model_dump(mode="json"), request_id]))
    memo = ctx.store.memo_get(memo_key)
    if memo is None:
        def run():
            joint, f, _jm = joint_problem(apart, request_id=request_id, joint_id="overseer-recheck-apart")
            if joint is None:
                return None, [x.code for x in f]
            return verify(joint, cfg, JOINT_LIMITS), []
        (res, _codes), run_ids = ctx.auditor_run(run, seq=seq)
        memo = (res.result_id if res is not None else None, res.status.value if res is not None else None, run_ids)
        ctx.store.memo_put(memo_key, memo)
    else:
        for r in memo[2]:
            if r not in ctx.auditor_result_ids:
                ctx.auditor_result_ids.append(r)
    return memo[0], memo[1], how
