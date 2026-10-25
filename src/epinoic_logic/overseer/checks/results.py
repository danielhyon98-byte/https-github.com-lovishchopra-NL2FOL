"""L3 results: is every result a receipt cites a signed engine run of the problem it names, inside this task?

Every captured result goes into the store and is signature-verified there; every id the receipt cites is then
resolved by its citation kind:

* RES-001: a receipt copy under a LOCAL key id that no capture of this channel produced while capture was active.
* RES-002 (warning): a cited result that is not retained (evicted, cited before the auditor attached, or a degraded
  view); unverifiable, never an accusation.
* RES-003: unsigned, invalid HMAC, or signed under an undeclared key id (a declared key id with no secret configured
  is AUDIT-004 instead: the auditor cannot verify, and says so).
* RES-004: ``check_result_binding`` against the cited problem (the translation's problem for an outcome, the stored
  problem otherwise): problem digest, claim, request or problem id, or an internally inconsistent binding.
* RES-005: out of task or reused. Outcome, constraint and branch results must be captured in this event, except a
  stored result of the same channel bound to the identical problem digest, claim id and claim-text digest (a caching
  translator; recorded as reused in coverage, design decision 23). Results carried by the INT-CONFLICT findings of a
  synthesis receipt (a contradiction named earlier on the channel) may come from an earlier event of the same channel;
  a result any other finding cites (INT-LEDGER-011's synthesis-entailment check included) must be an engine run of the
  citing event. Nothing may come from a later event, another channel or another request.
* RES-005 for a result of a declared EXTERNAL engine (produced outside the capture, stored at its first citation, which
  counts as its production at that event in every tier): re-cited by a later event for another problem, claim or claim
  text, or issued (its signed ``issued_at``) before the request the citing response answers. Anything else about its
  freshness is not decidable and is stated in the coverage notes.
* RES-006: one id with two contents in the store, or a receipt copy whose signature verifies but which is not
  byte-identical to the stored result (a copy whose signature fails is RES-003, which already names it forged).
* RES-009: ``display_status`` must equal ``display_status_for(translation, verification, key, key_id)`` with the
  verification key of the result's key id (the channel's own key when the result is unsigned or names an
  undeclared key id), so an unsigned or forged ENTAILED is never displayable.
* RES-010: the outcome's translation (ids and ``claim_text_sha256``) binds to the delivered claim text: the
  INT-STALE-011 rule re-applied to journaled content.
* RCPT-006 for a cited result id that has no content anywhere (no capture, no store entry, no tombstone, no copy).

Refinements of the design text: a receipt copy whose signature fails is RES-003 only (RES-006 is kept for two
validly signed contents under one id, so one forgery gives one accusation); a result id that resolves nowhere is
RCPT-006 (a dangling identifier) because without content its key id, and so RES-001, cannot be decided; an evicted
result whose binding would have to be re-checked is RES-002. Every result JSON is re-parsed with
:func:`~epinoic_logic.overseer.faithful.faithful`, since the ``exclude_none`` serialisation drops ``None`` values that
the signatures cover.
"""
from __future__ import annotations

import json
from typing import Optional

from ...engine.provenance import binding_inconsistencies
from ...engine.results import VerificationResult
from ...engine.statuses import is_definitive
from ...ir.canonical import canonical_json, problem_digest, sha256_hex
from ...ir.schema import Problem
from ...translate.contracts import sha256_text
from ...translate.outcome import display_status_for
from ..contracts import Citation, ResultTombstone, StoredResult
from ..faithful import faithful
from ..view import Transfer, cited_results
from . import CheckContext

__all__ = ["store_captured", "check_results", "binding_problems", "replayable_problem", "check_replayable", "check_unreplayed", "engine_run_problems",
           "journaled_capture", "replay_source", "replay_config"]



def store_captured(ctx: CheckContext, t: Transfer) -> None:
    """Put every result this event captured into the store (signature verified at put); a second content under a held
    id is RES-006. Every captured result under a LOCAL key must also be a run of this channel's engine as journaled:
    its solver configuration the channel's (``engine_run_problems``) and its component versions the running engine's,
    else RES-004 (an insider re-signing a status with a tiny budget or other versions would otherwise make the replay
    inconclusive instead of refuting it)."""
    plan = ctx.view.plan_at(t.seq)
    for c in t.event.captured:
        out = ctx.store.put(c, channel_uid=ctx.view.channel_uid, task_id=ctx.view.task_id, request_id=getattr(plan, "request_id", ctx.view.request_id),
                            event_seq=t.seq, origin="captured")
        if out.conflict is not None:
            ctx.ovs(t.seq, "OVS-RES-006", f"result id {c.result_id} is held with two different contents ({out.conflict[0][:12]} and {out.conflict[1][:12]})",
                    formal_result_id=c.result_id, **t.ids())
        _check_engine_run(ctx, t, c.result_id, c.result_json, c.key_id, "captured in this event")
    if t.event.captured_overflow:
        ctx.ovs(t.seq, "OVS-AUDIT-002", f"the capture of event {t.seq} overflowed: {t.event.captured_overflow} engine runs were not captured", **t.ids())


def _allowed_configs(view, seq: int) -> Optional[list]:
    """The solver configurations the channel's engine runs under at ``seq`` (the journaled config, and the same with
    ``produce_unsat_core`` forced on, as the integrity package's cross-report, synthesis and paraphrase checks run it),
    and each of them under every named engine policy (rule ``policy-configs``, the translator merge: a branch formal check
    runs under ``engine.policies.policy_config(policy, config)``, which for the ``nonlinear`` policy caps the ``rlimit`` at
    ``NONLINEAR_RLIMIT``); None when the journal records no config (nothing to compare)."""
    from ...engine.policies import PACK_POLICIES, policy_config
    info = view.info_at(seq) if view is not None else {}
    if not info.get("config"):
        return None
    cfg = view.config_at(seq)
    base = [cfg, cfg.model_copy(update={"produce_unsat_core": True})]
    out = list(base)
    for name in sorted(PACK_POLICIES):
        for c in base:
            pc = policy_config(name, c)
            if pc not in out:
                out.append(pc)
    return out


def engine_run_problems(view, res: VerificationResult, seq: int) -> list[str]:
    """Why ``res`` is not a run of the channel's engine at ``seq`` (empty when it is): a solver configuration other than
    the channel's journaled one, or component versions other than the running engine's. Decided for results under a
    local key only (the caller's rule); an external engine runs under its own configuration and versions."""
    from ...engine.provenance import compute_versions
    why: list[str] = []
    allowed = _allowed_configs(view, seq)
    if allowed is not None and res.solver_config not in allowed:
        cfg = allowed[0]
        diff = sorted(k for k, v in res.solver_config.model_dump().items() if v != cfg.model_dump().get(k) and k != "produce_unsat_core")
        why.append(f"solver configuration {diff or ['produce_unsat_core']} differs from the channel's journaled configuration")
    if res.versions != compute_versions():
        diff = sorted(k for k, v in res.versions.model_dump().items() if v != compute_versions().model_dump().get(k))
        why.append(f"component versions {diff} differ from the running engine's")
    return why


def _check_engine_run(ctx: CheckContext, t: Transfer, rid: str, result_json: Optional[str], key_id: Optional[str], where: str) -> None:
    if not result_json or ctx.keyring.key_status(key_id) != "local":
        return
    try:
        res = faithful(VerificationResult, json.loads(result_json))
    except Exception:
        return
    if ctx.keyring.key_status(res.signature_key_id) != "local":
        return
    why = engine_run_problems(ctx.view, res, t.seq)
    if why:
        ctx.ovs(t.seq, "OVS-RES-004", f"result {rid} ({where}, local key {res.signature_key_id!r}) is not a run of this channel's engine: {'; '.join(why)}; "
                "a replay under it could not refute its status", formal_result_id=rid, **t.ids())


def journaled_capture(view, rid: str):
    """The journaled capture of ``rid`` (the event's own copy of the result and its problem), or None. The journal keeps it
    when the store has evicted the result, so a replay never depends on the store's bound."""
    if view is None:
        return None
    for t in view.transfers:
        c = t.captured.get(rid)
        if c is not None and c.result_json:
            return t.seq, c
    return None


def replay_source(view, store, rid: str) -> Optional[tuple[str, Optional[str], int, str]]:
    """(result JSON, problem JSON or None, event seq, origin) a replay of ``rid`` is built from: the live store record, else
    the journaled capture, else a journaled receipt's outcome copy (a result of a declared external engine). None when no
    content is held anywhere."""
    rec = store.live(rid) if store is not None else None
    if rec is not None and rec.origin in ("captured", "external") and rec.channel_uid == getattr(view, "channel_uid", rec.channel_uid):
        res = store.parsed(rid)
        return rec.result_json, replayable_problem(view, rid, rec, res), rec.event_seq, rec.origin
    if rec is not None:
        return None
    jc = journaled_capture(view, rid)
    if jc is not None:
        seq, c = jc
        try:
            res = faithful(VerificationResult, json.loads(c.result_json))
        except Exception:
            return None
        return c.result_json, c.problem_json or replayable_problem(view, rid, None, res), seq, "captured"
    tomb = store.get(rid) if store is not None else None
    if tomb is not None and getattr(tomb, "origin", None) == "external" and view is not None:
        for t in view.transfers:
            if t.receipt is None:
                continue
            for o in t.receipt.outcomes:
                p = o.translation.problem
                if o.verification is not None and o.verification.result_id == rid and p is not None:
                    js = canonical_json(o.verification.model_dump(mode="json", exclude_none=True))
                    if sha256_hex(js) == tomb.result_sha256:
                        return js, canonical_json(p), tomb.event_seq, "external"
    return None


def replay_config(view, res: VerificationResult, seq: int, origin: str):
    """The solver configuration a replay runs under: for a local engine run, the channel's journaled configuration (the
    result's own only when it is one the channel runs under, a named engine policy's included), never a configuration
    the result itself names; for an external engine, the result's own (its budget cannot make a definitive status pass:
    an undecided replay of a definitive status is OVS-AUDIT-005). Rule ``unsigned-probe`` (the translator merge): an
    UNSIGNED captured result is the translator's own probe (the pipeline's stated-figure and stated-precision runs under
    the translator's configuration); no receipt can rely on it (a receipt citing an unsigned result is RES-001), so it is
    replayed under its own configuration, a check that it reproduces."""
    if origin != "captured" or not res.signature:
        return res.solver_config
    allowed = _allowed_configs(view, seq)
    if allowed is None or res.solver_config in allowed:
        return res.solver_config
    return allowed[0]


def replayable_problem(view, rid: str, rec, res: Optional[VerificationResult]) -> Optional[str]:
    """The problem a stored result can be replayed on (canonical JSON): the problem captured with it, else the problem
    of a journaled outcome citing it whose digest is the result's own binding digest (a result emitted into the capture
    without its problem is still replayed when a receipt carries the problem it is bound to). None when there is none."""
    if getattr(rec, "problem_json", None):
        return rec.problem_json
    want = res.binding.problem_digest if res is not None else None
    if not want or view is None:
        return None
    for t in view.transfers:
        if t.receipt is None:
            continue
        for o in t.receipt.outcomes:
            p = o.translation.problem
            if o.verification is not None and o.verification.result_id == rid and p is not None and problem_digest(p) == want:
                return canonical_json(p)
    return None


def check_replayable(ctx: CheckContext, t: Transfer) -> None:
    """AUDIT-005: a definitive engine result this transfer's receipt cites that cannot be replayed (captured without its
    problem, and no journaled outcome carries the problem it is bound to; or evicted from the store with no journaled
    copy to replay). Replay is what exposes a status re-signed with the engine key, so such a result is never passed.
    An evicted result whose event still holds its capture is replayed from the journal (``replay_source``)."""
    rc = t.receipt
    if rc is None:
        return
    for rid in dict.fromkeys(r for r, _k, _p in cited_results(rc)):
        rec = ctx.store.get(rid)
        if rec is None or rec.origin not in ("captured", "external") or rec.channel_uid != ctx.view.channel_uid:
            continue
        status = rec.status if isinstance(rec, ResultTombstone) else None
        res = ctx.store.parsed(rid) if isinstance(rec, StoredResult) else None
        if res is not None:
            status = res.status.value
        if status is None or not is_definitive(status):
            continue
        src = replay_source(ctx.view, ctx.store, rid)
        if src is None or not src[1]:
            why = ("was evicted from the store and no journaled capture or receipt copy holds it" if src is None and isinstance(rec, ResultTombstone)
                   else "was captured without its problem and no journaled outcome carries the problem it is bound to")
            ctx.ovs(t.seq, "OVS-AUDIT-005", f"result {rid} ({status}) cited by {t.kind} {t.message_id} {why}: it cannot be replayed, so a re-signed status "
                    "could not be exposed; the transfer cannot pass", formal_result_id=rid, **t.ids())


def check_unreplayed(ctx: CheckContext, t: Transfer, replays: dict) -> None:
    """AUDIT-005 (batch, after the replay tier ran): a definitive result this transfer cites that the store evicted and
    that no completed replay covers. Its status was never re-verified, so the transfer cannot pass."""
    rc = t.receipt
    if rc is None:
        return
    for rid in dict.fromkeys(r for r, _k, _p in cited_results(rc)):
        rec = ctx.store.get(rid)
        if not isinstance(rec, ResultTombstone) or rec.origin not in ("captured", "external") or rec.channel_uid != ctx.view.channel_uid:
            continue
        if not is_definitive(rec.status) or rid in replays:
            continue
        ctx.ovs(t.seq, "OVS-AUDIT-005", f"result {rid} ({rec.status}) cited by {t.kind} {t.message_id} was evicted from the store and no completed replay covers it: "
                "its signed status was never re-verified; the transfer cannot pass", formal_result_id=rid, **t.ids())


def binding_problems(result: VerificationResult, problem: Problem, key: Optional[bytes] = None) -> list[str]:
    """Why ``result`` does not bind to ``problem`` (empty when it does): the problem digest, the claim and request ids
    (the INT-STALE-001/003 rules of ``check_result_binding``), the problem id, and the binding's internal consistency
    (INT-STALE-007). Signature and version staleness are decided elsewhere (RES-003, RES-008)."""
    why: list[str] = []
    if result.binding.problem_digest != problem_digest(problem):
        why.append("bound to another problem (digest)")
    if result.claim_id != problem.claim_id or result.request_id != problem.request_id:
        why.append("bound to another claim or request")
    if result.problem_id != problem.problem_id:
        why.append(f"problem id {result.problem_id!r} != {problem.problem_id!r}")
    if _internal_binding(result):
        why.append("binding internally inconsistent")
    return why


def _internal_binding(result: VerificationResult) -> list[str]:
    """The engine's own reading of a binding's internal consistency (``provenance.binding_inconsistencies``): the binding
    digest over the problem, configuration, versions (with the build, schema and policy identity) and, since the engine
    binds them, the non-default validation limits. The audit never re-derives the rule, so it cannot disagree with the
    engine whose results it reads (before the second translator merge it recomputed the digest without the limits)."""
    return binding_inconsistencies(result)


def _channel_key_id(ctx: CheckContext, seq: int) -> Optional[str]:
    return ctx.view.key_id_at(seq)


def _sig_finding(ctx: CheckContext, t: Transfer, rid: str, key_id: Optional[str], ok: bool, reason: str, where: str) -> bool:
    """RES-003 / AUDIT-004 for a result whose signature does not verify; True when a finding was raised."""
    if ok:
        return False
    ids = t.ids()
    if key_id and ctx.keyring.is_declared(key_id) and not ctx.keyring.has_secret(key_id):
        ctx.ovs(t.seq, "OVS-AUDIT-004", f"result {rid} ({where}) is signed under the declared key id {key_id!r}, for which no verification key is configured; it is not verified",
                formal_result_id=rid, **ids)
        return True
    ctx.ovs(t.seq, "OVS-RES-003", f"result {rid} ({where}) cannot be trusted: {reason}", formal_result_id=rid, **ids)
    return True


def _outcome_claim_digest(ctx: CheckContext, rid: str, before_seq: int) -> list[Optional[str]]:
    """The claim-text digests of earlier outcomes citing ``rid`` (for the reuse exception)."""
    out = []
    for cit in ctx.store.citations(rid):
        if cit.kind != "outcome" or cit.event_seq >= before_seq:
            continue
        t = ctx.view.by_seq.get(cit.event_seq)
        if t is None or t.receipt is None:
            continue
        for o in t.receipt.outcomes:
            if o.verification is not None and o.verification.result_id == rid:
                out.append(o.translation.claim_text_sha256)
    return out


def check_results(ctx: CheckContext, t: Transfer) -> None:
    rc = t.receipt
    if rc is None:
        return
    ids = t.ids()
    view = ctx.view
    plan = view.plan_at(t.seq)
    channel_key_id = _channel_key_id(ctx, t.seq)
    outcome_rids = {o.verification.result_id for o in rc.outcomes if o.verification is not None}
    by_rid: dict[str, list[tuple[str, str]]] = {}
    for rid, kind, path in cited_results(rc):
        ctx.store.cite(rid, Citation(event_seq=t.seq, kind=kind, path=path))
        ctx.cited_result_ids.add(rid)
        if kind == "outcome" or rid in outcome_rids:
            continue  # outcomes carry a full copy: decided with it below
        by_rid.setdefault(rid, []).append((kind, path))
    for rid, cites in by_rid.items():
        kinds = {k for k, _p in cites}
        path = cites[0][1]
        rec = ctx.store.get(rid)
        if rec is None:
            if view.degraded or t.digest_only or view.first_seq > 1:
                ctx.ovs(t.seq, "OVS-RES-002", f"result {rid} cited at {path} is not retained (" + ("degraded view" if view.degraded else "digest-only journal" if t.digest_only else "cited before the auditor attached") + "); it is unverifiable, not accused",
                        formal_result_id=rid, **ids)
            else:
                ctx.ovs(t.seq, "OVS-RCPT-006", f"receipt {t.receipt_id} cites result {rid} at {path}, which no engine run captured on this channel and no store holds: it resolves nowhere",
                        formal_result_id=rid, **ids)
            continue
        ctx.coverage.results_resolved += 1
        # membership: the strictest rule of the kinds citing it (a synthesis may carry an earlier CONFLICT result of this
        # channel in its INT-CONFLICT findings only; a result cited by any other finding, INT-LEDGER-011 and the synthesis
        # entailment check included, must be an engine run of this event)
        citing_codes = {f.code for f in rc.findings if f.formal_result_id == rid or rid in f.related_result_ids}
        lenient = (t.kind == "relay_synthesis" and kinds <= {"finding_formal", "finding_related", "receipt_formal"} and bool(citing_codes)
                   and all(c.startswith("INT-CONFLICT") for c in citing_codes))
        _membership(ctx, t, rid, rec, lenient, path, rid in t.captured)
        if isinstance(rec, ResultTombstone):
            if not rec.signature_ok_at_put:
                _sig_finding(ctx, t, rid, rec.key_id, False, "its signature did not verify when it was stored", path)
            ctx.ovs(t.seq, "OVS-RES-002", f"result {rid} cited at {path} was evicted from the store: its membership and its signature at storage are decided, its binding cannot be re-checked",
                    formal_result_id=rid, **ids)
            continue
        if rec.signature_ok_at_put:
            ctx.coverage.results_signature_verified += 1
        else:
            _sig_finding(ctx, t, rid, rec.key_id, False, rec.signature_reason, path)
        res = ctx.store.parsed(rid)
        if res is not None and plan is not None and res.request_id != plan.request_id:
            ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} cited at {path} was produced for request {res.request_id!r}, not this task's request {plan.request_id!r}", formal_result_id=rid, **ids)
        if res is not None and rec.problem_json:
            try:
                prob = faithful(Problem, json.loads(rec.problem_json))
            except Exception:
                prob = None
            if prob is not None:
                why = binding_problems(res, prob, None)
                if why:
                    ctx.ovs(t.seq, "OVS-RES-004", f"result {rid} cited at {path} does not bind to the problem it was decided on: {why}", formal_result_id=rid, **ids)
        elif res is not None:
            why = _internal_binding(res)
            if why:
                ctx.ovs(t.seq, "OVS-RES-004", f"result {rid} cited at {path}: {why}", formal_result_id=rid, **ids)
    for i, o in enumerate(rc.outcomes):
        _check_outcome(ctx, t, i, o, channel_key_id)


def _stored_request_id(ctx: CheckContext, rec: StoredResult) -> Optional[str]:
    try:
        return json.loads(rec.result_json).get("request_id")
    except Exception:
        return None


def _membership(ctx: CheckContext, t: Transfer, rid: str, rec, lenient: bool, path: str, captured_here: bool) -> None:
    """RES-005 for constraint, branch and finding citations: where and when the cited result was produced. ``lenient``:
    cited only by findings of a synthesis receipt, which may carry a conflict result of an earlier event of this channel."""
    ids = t.ids()
    if captured_here:
        return
    if rec.channel_uid != ctx.view.channel_uid:
        ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} cited at {path} was produced on another channel ({rec.channel_uid}, task {rec.task_id!r}), not in this task", formal_result_id=rid, **ids)
        return
    if rec.event_seq > t.seq:
        ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} cited at {path} was produced by a later event ({rec.event_seq}) than the receipt citing it ({t.seq})", formal_result_id=rid, **ids)
        return
    if rec.origin in ("auditor_run", "replay"):
        ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} cited at {path} is an Overseer run, not an engine result of this transfer", formal_result_id=rid, **ids)
        return
    if lenient:
        return  # a conflict result carried onto the synthesis receipt from an earlier event of this channel
    ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} cited at {path} was produced by an earlier event ({rec.event_seq}) and re-cited as fresh by {t.kind} {t.message_id}", formal_result_id=rid, **ids)


def _check_outcome(ctx: CheckContext, t: Transfer, i: int, o, channel_key_id: Optional[str]) -> None:
    ids = t.ids()
    ver = o.verification
    path = f"outcomes[{i}]"
    claim_ids = [o.claim_id]
    # RES-010: the translation binds to the delivered claim
    rep = t.report
    claim = next((c for c in rep.claims if c.claim_id == o.claim_id), None) if rep is not None else None
    why10: list[str] = []
    if rep is not None:
        if claim is None:
            why10.append(f"claim {o.claim_id!r} is not in report {rep.report_id}")
        else:
            tr = o.translation
            if o.claim_id != claim.claim_id or tr.claim_id != claim.claim_id:
                why10.append("claim id")
            if o.request_id != rep.request_id or tr.request_id != rep.request_id:
                why10.append("request id")
            if o.report_id != rep.report_id or tr.report_id != rep.report_id:
                why10.append("report id")
            if tr.claim_text_sha256 is not None and tr.claim_text_sha256 != sha256_text(claim.claim_text):
                why10.append("claim text (the translation was produced for another text of this claim)")
    if why10:
        ctx.ovs(t.seq, "OVS-RES-010", f"outcome {path} is not bound to the delivered claim {o.claim_id}: {why10}", claim_ids=claim_ids,
                formal_result_id=ver.result_id if ver is not None else None, **ids)
    if ver is None:
        return
    rid = ver.result_id
    ctx.cited_result_ids.add(rid)
    copy_json = canonical_json(ver.model_dump(mode="json", exclude_none=True))
    copy_sha = sha256_hex(copy_json)
    ok, reason = ctx.keyring.verify_result(ver)
    sig_bad = _sig_finding(ctx, t, rid, ver.signature_key_id, ok, reason, f"{path}.verification")
    if ok:
        ctx.coverage.results_signature_verified += 1
    rec = ctx.store.get(rid)
    captured_here = rid in t.captured
    if rec is None:
        ctx.coverage.results_resolved += 1
        status = ctx.keyring.key_status(ver.signature_key_id) if ver.signature else "unknown"
        if ok and status == "external":
            from ...engine.sink import CapturedResult
            prob = o.translation.problem
            ctx.store.put(CapturedResult(result_id=rid, key_id=ver.signature_key_id, result_json=copy_json, result_sha256=copy_sha,
                                         problem_json=canonical_json(prob) if prob is not None else None, problem_digest=problem_digest(prob) if prob is not None else None),
                          channel_uid=ctx.view.channel_uid, task_id=ctx.view.task_id, request_id=ctx.view.request_id, event_seq=t.seq, origin="external")
        elif ok and status == "local":
            if ctx.view.degraded or t.digest_only:
                ctx.ovs(t.seq, "OVS-RES-002", f"result {rid} at {path}.verification is not retained ({'degraded view' if ctx.view.degraded else 'digest-only journal'}); its origin cannot be decided", claim_ids=claim_ids, formal_result_id=rid, **ids)
            else:
                ctx.ovs(t.seq, "OVS-RES-001", f"result {rid} at {path}.verification is signed under the local key id {ver.signature_key_id!r} but no engine run of this channel produced it while capture was active",
                        claim_ids=claim_ids, formal_result_id=rid, **ids)
    else:
        ctx.coverage.results_resolved += 1
        # a result of a declared external engine is stored when it is first cited, at the citing event: that citation is
        # its production as far as this channel can see, in the live tier and in every later audit alike
        if getattr(rec, "origin", None) == "external" and rec.event_seq == t.seq and rec.channel_uid == ctx.view.channel_uid:
            captured_here = True
        if isinstance(rec, StoredResult) and rec.result_sha256 != copy_sha and not sig_bad:
            ctx.ovs(t.seq, "OVS-RES-006", f"the receipt's copy of result {rid} at {path}.verification is not byte-identical to the result the engine produced", claim_ids=claim_ids, formal_result_id=rid, **ids)
        elif isinstance(rec, ResultTombstone) and rec.result_sha256 != copy_sha and not sig_bad:
            ctx.ovs(t.seq, "OVS-RES-006", f"the receipt's copy of result {rid} at {path}.verification differs from the (evicted) result the engine produced", claim_ids=claim_ids, formal_result_id=rid, **ids)
        if isinstance(rec, ResultTombstone):
            ctx.ovs(t.seq, "OVS-RES-002", f"result {rid} at {path}.verification was evicted from the store: it is decided on the receipt's copy and replayed from the "
                    "journaled capture; with no journaled copy and no completed replay it cannot pass (OVS-AUDIT-005)", claim_ids=claim_ids, formal_result_id=rid, **ids)
        if not captured_here:
            _outcome_membership(ctx, t, o, rec, path)
    if ok and ctx.keyring.key_status(ver.signature_key_id) == "external":
        _external_freshness(ctx, t, o, ver, path)
    # RES-004: binding to the translation's problem
    prob = o.translation.problem
    if prob is None:
        ctx.ovs(t.seq, "OVS-RES-004", f"outcome {path} carries engine result {rid} but its translation carries no problem", claim_ids=claim_ids, formal_result_id=rid, **ids)
    else:
        why = binding_problems(ver, prob, None)
        if why:
            ctx.ovs(t.seq, "OVS-RES-004", f"result {rid} at {path}.verification is not bound to the translated problem of claim {o.claim_id}: {why}", claim_ids=claim_ids, formal_result_id=rid, **ids)
    # RES-009: the display status is derivable from the translation and the signed result
    kid = ver.signature_key_id if (ver.signature and ctx.keyring.is_declared(ver.signature_key_id)) else channel_key_id
    key = ctx.keyring.verification_key(kid)
    if key is None:
        ctx.ovs(t.seq, "OVS-AUDIT-004", f"no verification key is configured for key id {kid!r}; the display status of outcome {path} cannot be derived", claim_ids=claim_ids, formal_result_id=rid, **ids)
        return
    try:
        expected = display_status_for(o.translation, ver, key, kid)
    except Exception as exc:
        ctx.ovs(t.seq, "OVS-AUDIT-001", f"display status of outcome {path} could not be derived ({type(exc).__name__})", claim_ids=claim_ids, formal_result_id=rid, **ids)
        return
    if expected != o.display_status:
        ctx.ovs(t.seq, "OVS-RES-009", f"outcome {path} displays {o.display_status.value} but the translation and the signed result give {expected.value}", claim_ids=claim_ids, formal_result_id=rid, **ids)


def _parse_time(value: Optional[str]):
    from datetime import datetime
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _external_freshness(ctx: CheckContext, t: Transfer, o, ver, path: str) -> None:
    """RES-005 for an external engine's result issued before the request the citing response answers (a replay of an
    earlier run): decided on the result's signed ``issued_at`` and the journaled request, the same way in every tier.
    What cannot be decided (a re-signed result issued after the request, for a text the translation does not bind) is
    stated in coverage, never passed silently as decided."""
    req_t = ctx.view.by_seq.get(t.request_seq) if t.request_seq is not None else None
    req_at = _parse_time((req_t.envelope or {}).get("created_at")) if req_t is not None else None
    issued = _parse_time(ver.issued_at)
    if req_at is not None and issued is not None and issued < req_at:
        ctx.ovs(t.seq, "OVS-RES-005", f"result {ver.result_id} at {path}.verification of the external engine {ver.signature_key_id!r} was issued at {ver.issued_at}, before the "
                f"request {req_t.message_id} it answers ({(req_t.envelope or {}).get('created_at')}): a result of an earlier run re-cited as fresh",
                claim_ids=[o.claim_id], formal_result_id=ver.result_id, **t.ids())
        return
    ctx.note(f"external results (e.g. {ver.result_id} under {ver.signature_key_id!r}) were produced outside the capture: their freshness is decided only by their "
             "signed issue time against the request and by the uniqueness of their citation (claim, claim text, problem)")


def _outcome_membership(ctx: CheckContext, t: Transfer, o, rec, path: str) -> None:
    """RES-005 for an outcome result not captured in this event, with the caching-translator exception."""
    ids = t.ids()
    rid = o.verification.result_id
    cid = [o.claim_id]
    if rec.channel_uid != ctx.view.channel_uid:
        ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} at {path}.verification was produced on another channel ({rec.channel_uid}, task {rec.task_id!r})", claim_ids=cid, formal_result_id=rid, **ids)
        return
    if rec.event_seq >= t.seq or getattr(rec, "origin", "captured") in ("auditor_run", "replay"):
        ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} at {path}.verification was not produced by an engine run before this transfer", claim_ids=cid, formal_result_id=rid, **ids)
        return
    prob = o.translation.problem
    same_problem = prob is not None and getattr(rec, "problem_digest", None) == problem_digest(prob)
    stored = ctx.store.parsed(rid)
    same_claim = stored is not None and stored.claim_id == o.claim_id
    earlier_digests = _outcome_claim_digest(ctx, rid, t.seq)
    same_text = bool(earlier_digests) and all(d == o.translation.claim_text_sha256 for d in earlier_digests) and o.translation.claim_text_sha256 is not None
    if same_problem and same_claim and same_text:
        if rid not in ctx.coverage.reused_results:
            ctx.coverage.reused_results.append(rid)
        return
    ctx.ovs(t.seq, "OVS-RES-005", f"result {rid} at {path}.verification was produced by an earlier event ({rec.event_seq}) for "
            + ("another problem" if not same_problem else "another claim" if not same_claim else "another text of the claim") + " and is re-cited as fresh",
            claim_ids=cid, formal_result_id=rid, **ids)
