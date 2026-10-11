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
  translator; recorded as reused in coverage, design decision 23). Results carried by findings of a synthesis
  receipt may come from an earlier event of the same channel. Nothing may come from a later event, another channel
  or another request.
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

from ...engine.provenance import config_digest, versions_digest
from ...engine.results import VerificationResult
from ...ir.canonical import canonical_json, problem_digest, sha256_hex
from ...ir.schema import Problem
from ...translate.contracts import sha256_text
from ...translate.outcome import display_status_for
from ..contracts import Citation, ResultTombstone, StoredResult
from ..faithful import faithful
from ..view import Transfer, cited_results
from . import CheckContext

__all__ = ["store_captured", "check_results", "binding_problems"]



def store_captured(ctx: CheckContext, t: Transfer) -> None:
    """Put every result this event captured into the store (signature verified at put); a second content under a held
    id is RES-006."""
    plan = ctx.view.plan_at(t.seq)
    for c in t.event.captured:
        out = ctx.store.put(c, channel_uid=ctx.view.channel_uid, task_id=ctx.view.task_id, request_id=getattr(plan, "request_id", ctx.view.request_id),
                            event_seq=t.seq, origin="captured")
        if out.conflict is not None:
            ctx.ovs(t.seq, "OVS-RES-006", f"result id {c.result_id} is held with two different contents ({out.conflict[0][:12]} and {out.conflict[1][:12]})",
                    formal_result_id=c.result_id, **t.ids())
    if t.event.captured_overflow:
        ctx.ovs(t.seq, "OVS-AUDIT-002", f"the capture of event {t.seq} overflowed: {t.event.captured_overflow} engine runs were not captured", **t.ids())


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
    b = result.binding
    why = []
    if b.binding_digest != sha256_hex("|".join((b.problem_digest, b.config_digest, b.versions_digest))):
        why.append("binding_digest is not sha256(problem|config|versions)")
    if config_digest(result.solver_config) != b.config_digest:
        why.append("config_digest is not the digest of solver_config")
    if versions_digest(result.versions) != b.versions_digest:
        why.append("versions_digest is not the digest of versions")
    return why


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
        # membership: the strictest rule of the kinds citing it (a synthesis may carry earlier conflict results in findings only)
        lenient = t.kind == "relay_synthesis" and kinds <= {"finding_formal", "finding_related", "receipt_formal"}
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
        if isinstance(rec, StoredResult) and rec.result_sha256 != copy_sha and not sig_bad:
            ctx.ovs(t.seq, "OVS-RES-006", f"the receipt's copy of result {rid} at {path}.verification is not byte-identical to the result the engine produced", claim_ids=claim_ids, formal_result_id=rid, **ids)
        elif isinstance(rec, ResultTombstone) and rec.result_sha256 != copy_sha and not sig_bad:
            ctx.ovs(t.seq, "OVS-RES-006", f"the receipt's copy of result {rid} at {path}.verification differs from the (evicted) result the engine produced", claim_ids=claim_ids, formal_result_id=rid, **ids)
        if not captured_here:
            _outcome_membership(ctx, t, o, rec, path)
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
