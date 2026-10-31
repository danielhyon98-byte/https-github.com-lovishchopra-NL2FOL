"""B5 shadow-channel replay: a fresh channel fed the journaled inputs must issue the same receipts.

A fresh ``TranslatorChannel`` is built from the journaled plan and configuration, with the channel's branch registry
and the auditor's run key (``overseer-run``; never an engine key). Its ``verify_claim_fn`` serves the journaled
``TranslationResult`` of each claim (by report id, claim id and claim-text digest) and re-verifies its problem with
the engine; the translator model is never called. The journaled transfers are re-issued in sequence order:

* requests with the journaled call (items and constraints given, the user input and supplied texts);
* raw texts the hub refused are re-sent as raw text; a raw text that was parsed is re-issued as the delivered report
  through ``respond`` with the same stated sender (exactly what ``respond_text`` does after parsing), so later
  forwards of it compare against the same payload;
* the journaled reports, forwards and syntheses, with message ids mapped to the shadow's.

Per sequence number the status, the MULTISET of ``(code, severity, claim_ids, report_ids)`` finding tuples (two
INT-REQ-004 naming nothing count twice), the coverage records, the constraint results and the outcomes' display statuses
are compared (review round 3).
Excluded: time-dependent codes (INT-HANDOFF-005, 016, 017) and the codes a journal cannot reproduce because their
cause never reaches a receipt (INT-STALE-011, a stale translation the channel dropped; INT-REQ-006 and INT-SYNTH-013,
hooks that raised). When the channel had a synthesis-formalization hook, synthesis transfers are not comparable (the
hook is a model call) and coverage says so.

* An error or a warning the shadow raises more often than the receipt is RCPT-004; a receipt finding the shadow does
  not raise is RCPT-005 (warning); a different status, coverage, constraint results or display statuses is RCPT-008.
* When an undecided engine run (TIMEOUT, UNKNOWN) on either side explains a difference, it is RES-008 instead: the
  environment's nondeterminism never becomes an accusation. Only a run under the channel's pinned configuration (or
  the same with unsat cores on) explains anything: an undecided run under a configuration swapped in later is the
  fault itself.

Limit (stated, not hidden): this shadow runs in the auditor's process with the repository's channel code. It catches
channel STATE corrupted between transfers, dropped or added findings, and environment nondeterminism; a patch to the
channel's CODE that is still active when the shadow runs is executed by the shadow too and is invisible to it. The
receipt-level rules (RCPT-002, RCPT-007) and the batch re-derivations with their own functions (B2-B4) cover that case;
a shadow in a separate process (the design's section 15 mitigation) is not built in this stage.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from ...channel.contracts import Constraint, RequestItem
from ...engine.results import VerificationResult
from ...engine.runner import verify
from ...engine.sink import capture_results
from ...engine.statuses import VerificationStatus as S
from ...integrity.contracts import AgentRole, Synthesis
from ...translate.contracts import SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from ...translate.outcome import compose_outcome
from ..keys import RUN_KEY_ID
from ..faithful import faithful
from ..view import Transfer
from . import CheckContext

__all__ = ["run_shadow", "SHADOW_EXCLUDED"]

SHADOW_EXCLUDED = frozenset({"INT-HANDOFF-005", "INT-HANDOFF-016", "INT-HANDOFF-017", "INT-STALE-011", "INT-REQ-006", "INT-SYNTH-013"})
_UNDECIDED = (S.TIMEOUT.value, S.UNKNOWN.value)


def _tuples(findings) -> Counter:
    """The receipt's findings as a multiset of ``(code, severity, claim_ids, report_ids)``: two findings of one code
    that name nothing (one INT-REQ-004 per unaddressed item) count twice, so deleting one of them is a difference."""
    out: Counter = Counter()
    for f in findings:
        if f.code in SHADOW_EXCLUDED:
            continue
        out[(f.code, f.severity, tuple(sorted(f.claim_ids)), tuple(sorted(f.report_ids)))] += 1
    return out


def _structured(rc) -> dict[str, list]:
    """The receipt's structured results the shadow compares besides its findings: coverage records, constraint results
    and the outcomes' display statuses."""
    return {
        "coverage": sorted((c.item_id, c.addressed, tuple(sorted(c.addressed_by_claim_ids))) for c in rc.coverage),
        "constraint_results": sorted((c.constraint_id, c.satisfied, c.method, c.formal_status) for c in rc.constraint_results),
        "outcome display statuses": sorted((o.report_id, o.claim_id, getattr(o.display_status, "value", o.display_status)) for o in rc.outcomes),
    }


def _undecided(items, allowed=None) -> bool:
    """True when any captured run is undecided (TIMEOUT or UNKNOWN) under a configuration the channel runs under
    (``allowed``: the pinned configuration, and the same with unsat cores on; None accepts any). An undecided run under
    another configuration (a starved budget swapped in) explains nothing: it is the fault, not the environment."""
    import json
    for c in items:
        try:
            data = json.loads(c.result_json) if c.result_json else None
            if not data or data.get("status") not in _UNDECIDED:
                continue
            if allowed is not None and faithful(VerificationResult, data).solver_config not in allowed:
                continue
            return True
        except Exception:
            continue
    return False


def run_shadow(ctx: CheckContext) -> str:
    """Run the shadow channel over the view; returns the coverage state (``run``, ``skipped``)."""
    view = ctx.view
    if view.degraded or not view.transfers:
        ctx.note("shadow replay skipped: no journaled transfers")
        return "skipped"
    if any(t.digest_only for t in view.transfers):
        ctx.note("shadow replay skipped: the journal holds digest-only entries, so the inputs cannot be re-issued")
        return "skipped"
    if len(view.plans) > 1:
        ctx.note("shadow replay uses the first journaled plan; the plan changed during the task")
    from ...channel.bus import TranslatorChannel
    plan = view.plan
    first = view.transfers[0].seq
    info = view.info_at(first)
    cfg = view.config_at(first)
    allowed = [cfg, cfg.model_copy(update={"produce_unsat_core": True})]
    registry = ctx.registry
    if registry is None:
        from ...branches import default_registry
        registry = default_registry()
    runs_key = ctx.keyring.subkey("runs")
    translations: dict[tuple[str, str], list] = {}
    for t in view.transfers:
        if t.receipt is None:
            continue
        for o in t.receipt.outcomes:
            translations.setdefault((o.report_id, o.claim_id), []).append(o.translation)

    def serve(claim, report):
        cands = translations.get((report.report_id, claim.claim_id), [])
        digest = sha256_text(claim.claim_text)
        tr = next((x for x in cands if x.claim_text_sha256 == digest), None) or next((x for x in cands if x.claim_text_sha256 is None), None)
        if tr is None:
            return None
        ver: Optional[VerificationResult] = None
        if tr.problem is not None and tr.status in (TranslationStatus.TRANSLATED, TranslationStatus.AMBIGUOUS_TRANSLATION):
            # as translate.outcome.verify_claim runs it: on an ambiguous translation the argument diagnosis is capped at
            # info on the assumed reading (capped_from keeps the uncapped severity)
            cap = ("info", "ambiguous_translation") if tr.status is TranslationStatus.AMBIGUOUS_TRANSLATION else None
            ver = verify(tr.problem, cfg, signing_key=runs_key, key_id=RUN_KEY_ID, severity_cap=cap)
        return compose_outcome(claim, tr, ver, signing_key=runs_key, key_id=RUN_KEY_ID)

    shadow = TranslatorChannel(plan, signing_key=runs_key, key_id=RUN_KEY_ID, verify_claim_fn=serve, config=cfg, registry=registry)
    hook = bool(info.get("formalize_synthesis_hook"))
    if hook:
        ctx.note("shadow replay: synthesis transfers not comparable (the channel had a synthesis-formalization hook)")
    mid_map: dict[str, str] = {}

    def m(x: Optional[str]) -> Optional[str]:
        return mid_map.get(x, x) if x else x

    for t in view.transfers:
        if t.receipt is None or t.payload is None:
            continue
        call = t.call
        try:
            with capture_results() as cap:
                if t.kind == "request":
                    req = t.request
                    items = [faithful(RequestItem, i) for i in call["items"]] if call.get("items") is not None else None
                    cons = [faithful(Constraint, c) for c in call["constraints"]] if call.get("constraints") is not None else None
                    msg, _req, rc = shadow.request(req.from_agent_id, req.to_agent_id, req.user_input, list(req.supplied_texts), items=items, constraints=cons)
                elif t.kind == "response_text" and t.withheld is not None:
                    texts = [faithful(SuppliedText, s) for s in call["supplied_texts"]] if call.get("supplied_texts") is not None else None
                    msg, rc = shadow.respond_text(m(call.get("request_message_id")), t.raw_text or "", agent_id=call.get("agent_id") or t.withheld.get("agent_id"),
                                                  report_id=call.get("report_id") or t.withheld.get("report_id"), supplied_texts=texts, agent_version=call.get("agent_version"))
                elif t.kind in ("response", "response_text"):
                    report = faithful(SpecialistReport, t.payload)
                    sender = call.get("sender_agent_id") if t.kind == "response" else call.get("agent_id")
                    msg, rc = shadow.respond(m(call.get("request_message_id") or t.in_reply_to), report, sender_agent_id=sender)
                elif t.kind in ("relay_forward", "relay_report", "relay_synthesis"):
                    obj: Any = faithful(Synthesis, t.payload) if t.kind == "relay_synthesis" else faithful(SpecialistReport, t.payload)
                    msg, rc = shadow.relay(call.get("from_agent_id"), AgentRole(call.get("from_role")), call.get("to_agent_id"), AgentRole(call.get("to_role")), obj,
                                           in_reply_to=m(call.get("in_reply_to")))
                else:
                    continue
        except Exception as exc:
            ctx.note(f"shadow replay of transfer {t.seq} ({t.kind}) could not be re-issued ({type(exc).__name__}); later transfers are compared against a partial shadow")
            continue
        if t.message_id and rc is not None:
            mid_map[t.message_id] = rc.message_id
        if t.kind == "relay_synthesis" and hook:
            continue
        undecided = _undecided(t.event.captured, allowed) or _undecided(cap.items, allowed)
        ours, theirs = _tuples(rc.findings), _tuples(t.receipt.findings)
        ids = t.ids()
        # every finding the shadow raises more often than the receipt (an error or a warning: a deleted warning hides as much
        # from the router as a deleted error), and every receipt finding the shadow raises less often
        missing = [(k, ours[k] - theirs.get(k, 0)) for k in ours if ours[k] > theirs.get(k, 0) and k[1] in ("error", "warning")]
        extra = [k for k in theirs if theirs[k] > ours.get(k, 0)]
        status_differs = rc.status is not t.receipt.status
        mine, journaled = _structured(rc), _structured(t.receipt)
        fields = [name for name in mine if mine[name] != journaled[name]]
        if undecided and (missing or extra or status_differs or fields):
            ctx.ovs(t.seq, "OVS-RES-008", f"the shadow channel's receipt for {t.kind} {t.message_id} differs ({'status ' + rc.status.value + ' vs ' + t.receipt.status.value + '; ' if status_differs else ''}"
                    f"codes {sorted({k[0] for k, _n in missing} | {k[0] for k in extra})}{'; ' + ', '.join(fields) if fields else ''}) and an undecided engine run under the channel's "
                    "configuration explains it", **ids)
            continue
        for k, n in missing:
            ctx.ovs(t.seq, "OVS-RCPT-004", f"re-derived on the journaled inputs, {t.kind} {t.message_id} raises {k[0]} ({k[1]}) for claims {list(k[2])}"
                    + (f" {ours[k]} times, where its receipt carries it {theirs.get(k, 0)} times" if ours[k] > 1 or theirs.get(k, 0) else ", which its receipt lacks"),
                    claim_ids=list(k[2]), message_ids=ids["message_ids"], report_ids=ids["report_ids"] + list(k[3]), agent_ids=ids["agent_ids"])
        for k in extra:
            ctx.ovs(t.seq, "OVS-RCPT-005", f"receipt {t.receipt_id} carries {k[0]} ({k[1]}) for claims {list(k[2])}, which the shadow channel does not reproduce on the journaled inputs",
                    claim_ids=list(k[2]), message_ids=ids["message_ids"], report_ids=ids["report_ids"] + list(k[3]), agent_ids=ids["agent_ids"])
        if status_differs:
            ctx.ovs(t.seq, "OVS-RCPT-008", f"the shadow channel fed the journaled inputs issues {rc.status.value} for {t.kind} {t.message_id}, whose receipt states {t.receipt.status.value}", **ids)
        if fields:
            ctx.ovs(t.seq, "OVS-RCPT-008", f"the shadow channel fed the journaled inputs issues other {', '.join(fields)} for {t.kind} {t.message_id} than its receipt states", **ids)
    return "run"
