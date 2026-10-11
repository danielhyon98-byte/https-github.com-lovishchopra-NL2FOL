"""L2 receipts: is every receipt the exact image of what was checked?

* RCPT-001: the live channel receipt, and in ``clearance`` the receipt the router presents, compared field by field
  with the journaled receipt; the differing fields are named.
* RCPT-002: the status recomputed from the journaled receipt with the channel's own rules (taken from the code, not
  copied: ``_BLOCKING_PREFIXES`` is imported). A request is REJECTED when any finding is an error and ACCEPTED
  otherwise, even with warnings. A response or relay is REJECTED when any error code starts with a blocking prefix;
  else ACCEPTED_WITH_FINDINGS when there is any finding, any error or warning structural finding, or any outcome
  whose verification is present and not definitive; else ACCEPTED.
* RCPT-003: delivery agrees with status (journaled return value and what the call added to the channel's records).
* RCPT-006: every identifier the receipt names resolves in the journaled payloads and calls, the plan, the log or the
  result store.
* RCPT-007: the summary regenerated with the channel's own static summary functions equals the receipt's; a
  non-request receipt ends with the channel's scope sentence.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ...channel.bus import _BLOCKING_PREFIXES, _SCOPE_TAIL, TranslatorChannel, _fit_summary
from ...channel.contracts import TransmissionReceipt, TransmissionStatus
from ...channel.events import model_json
from ...engine.statuses import is_definitive
from ...ir.canonical import sha256_hex
from ..view import REPORT_KINDS, Transfer
from . import CheckContext, json_diff_paths

__all__ = ["check_receipt_custody", "check_presented_receipt", "expected_status", "check_status", "check_delivery", "check_identifiers",
           "check_summary", "identifier_universe"]


def _diff_receipt(journaled: Optional[dict], other: Any) -> tuple[Optional[str], list[str]]:
    try:
        text = model_json(other)
    except Exception:
        return None, ["$ (receipt cannot be serialised)"]
    paths = json_diff_paths(journaled, json.loads(text)) if journaled is not None else []
    return sha256_hex(text), paths


def check_receipt_custody(ctx: CheckContext, t: Transfer) -> None:
    """RCPT-001 against the channel's own receipt object."""
    if ctx.view.degraded or ctx.live is None or not t.receipt_id or t.event.receipt_sha256 is None:
        return
    live = next((r for r in reversed(list(getattr(ctx.live, "receipts", []) or [])) if getattr(r, "receipt_id", None) == t.receipt_id), None)
    if live is None:
        ctx.ovs(t.seq, "OVS-RCPT-001", f"receipt {t.receipt_id} of {t.kind} {t.message_id} is no longer held by the channel", **t.ids())
        return
    sha, paths = _diff_receipt(t.receipt_dump, live)
    if sha != t.event.receipt_sha256:
        ctx.ovs(t.seq, "OVS-RCPT-001", f"the channel's receipt {t.receipt_id} for {t.message_id} differs from the journaled receipt" + (f" in fields {paths}" if paths else ""), **t.ids())


def check_presented_receipt(ctx: CheckContext, t: Transfer, presented: Any) -> Optional[str]:
    """RCPT-001 against the receipt the router presents to ``clearance``; returns the presented receipt's digest."""
    sha, paths = _diff_receipt(t.receipt_dump, presented)
    if sha != t.event.receipt_sha256:
        rid = getattr(presented, "receipt_id", None)
        ctx.ovs(t.seq, "OVS-RCPT-001", f"the receipt the router presents for {t.message_id} (receipt {rid}) differs from the journaled receipt {t.receipt_id}"
                + (f" in fields {paths}" if paths else ""), **t.ids())
    return sha


def expected_status(kind: str, receipt: TransmissionReceipt) -> TransmissionStatus:
    """The channel's status rule applied to the receipt's own contents."""
    findings = receipt.findings
    if kind == "request":
        return TransmissionStatus.REJECTED if any(f.severity == "error" for f in findings) else TransmissionStatus.ACCEPTED
    if any(f.severity == "error" and f.code.startswith(_BLOCKING_PREFIXES) for f in findings):
        return TransmissionStatus.REJECTED
    subject_flag = any(sf.severity in ("error", "warning") for sf in receipt.structural_findings)
    undecided = any(o.verification is not None and not is_definitive(o.verification.status) for o in receipt.outcomes)
    if findings or subject_flag or undecided:
        return TransmissionStatus.ACCEPTED_WITH_FINDINGS
    return TransmissionStatus.ACCEPTED


def check_status(ctx: CheckContext, t: Transfer) -> None:
    """RCPT-002."""
    if t.receipt is None:
        return
    exp = expected_status(t.kind, t.receipt)
    if exp is not t.receipt.status:
        ctx.ovs(t.seq, "OVS-RCPT-002", f"receipt {t.receipt_id} states {t.receipt.status.value} but the channel's status rule gives {exp.value} for its own contents "
                f"(findings {sorted({f.code for f in t.receipt.findings})})", **t.ids())


def _pool_key(pool) -> list:
    return [(p.claim_id, p.problem_digest, p.ambiguous) for p in pool]


def check_delivery(ctx: CheckContext, t: Transfer) -> None:
    """RCPT-003: delivery agrees with status."""
    if t.receipt is None or ctx.view.degraded:
        return
    ev = t.event
    ids = t.ids()
    wrong: list[str] = []
    rid = t.report_id
    if t.status == "REJECTED":
        if ev.returned_message:
            wrong.append("the message was returned to the caller")
        if _pool_key(ev.pool) != _pool_key(ev.pool_before):
            wrong.append("the cross-agent pool changed")
        if ev.conflicts_added:
            wrong.append("conflicts were recorded")
        if ev.forwards_added:
            wrong.append(f"forwards were recorded {[list(f) for f in ev.forwards_added]}")
        if ev.recipients_added:
            wrong.append(f"recipient records were added {[list(r) for r in ev.recipients_added]}")
        if ev.requests_added:
            wrong.append("the request was stored")
        if rid and rid in ev.transmitted_added:
            wrong.append(f"report {rid} was entered into transmitted_reports")
        elif rid and t.kind in REPORT_KINDS + ("relay_forward",):
            earlier = ctx.view.first_delivery(rid, before_seq=t.seq)
            if earlier is not None and ev.typed_copy_sha256 is not None and ev.typed_copy_sha256 != earlier.event.payload_sha256 and ev.typed_copy_sha256 == ev.payload_sha256:
                wrong.append(f"the held report {rid} was replaced by the rejected payload")
    elif t.status is not None:
        if not ev.returned_message:
            wrong.append("the message was not returned to the caller")
        if t.kind == "request" and t.message_id not in ev.requests_added:
            wrong.append("the accepted request was not stored")
        if t.kind in REPORT_KINDS and rid and ev.typed_copy_sha256 is None:
            wrong.append(f"report {rid} is not held in transmitted_reports")
        if t.kind == "relay_forward" and rid and not any(f[0] == rid and f[2] == t.message_id for f in ev.forwards_added):
            wrong.append(f"the forward of {rid} was not recorded")
    if wrong:
        ctx.ovs(t.seq, "OVS-RCPT-003", f"{t.kind} {t.message_id} has status {t.status} but " + "; ".join(wrong), **ids)


def identifier_universe(ctx: CheckContext, upto_seq: int) -> dict[str, set[str]]:
    """Every identifier the journal makes resolvable up to ``upto_seq``: claims, reports, messages, agents, documents,
    constraint and item ids, results."""
    claims: set[str] = set()
    reports: set[str] = set()
    messages: set[str] = set()
    agents: set[str] = {"router"}
    docs: set[str] = set()
    plan = ctx.view.plan_at(upto_seq)
    if plan is not None:
        agents.update(plan.selected_agent_ids)
        agents.update(plan.agent_subjects)
        docs.update(plan.allowed_document_ids)
    for t in ctx.view.transfers:
        if t.seq > upto_seq:
            break
        if t.message_id:
            messages.add(t.message_id)
        messages.update(t.event.log_added)
        for k in ("request_message_id", "in_reply_to"):
            v = t.call.get(k)
            if isinstance(v, str):
                messages.add(v)
        for k in ("from_agent_id", "to_agent_id", "agent_id", "sender_agent_id"):
            v = t.call.get(k)
            if isinstance(v, str):
                agents.add(v)
        env = t.envelope or {}
        for k in ("sender_agent_id", "recipient_agent_id"):
            if env.get(k):
                agents.add(env[k])
        if env.get("in_reply_to"):
            messages.add(env["in_reply_to"])
        p = t.payload or {}
        if isinstance(p.get("report_id"), str):
            reports.add(p["report_id"])
        if isinstance(p.get("agent_id"), str):
            agents.add(p["agent_id"])
        for c in p.get("claims") or []:
            if isinstance(c, dict):
                if isinstance(c.get("claim_id"), str):
                    claims.add(c["claim_id"])
                for ref in c.get("source_refs") or []:
                    if isinstance(ref, dict) and isinstance(ref.get("document_id"), str):
                        docs.add(ref["document_id"])
                for s in c.get("source_claim_ids") or []:
                    if isinstance(s, str):
                        claims.add(s)
        for st in p.get("supplied_texts") or []:
            if isinstance(st, dict) and isinstance(st.get("document_id"), str):
                docs.add(st["document_id"])
        if t.synthesis is not None:
            claims.add(t.synthesis.synthesis_id)
            agents.add(t.synthesis.combinator_agent_id)
            reports.update(t.synthesis.source_report_ids)
            for c in t.synthesis.conflicts:
                claims.update(c.claim_ids)
            for le in t.synthesis.ledger:
                claims.update(le.source_claim_ids)
            for sc in t.synthesis.claims:
                docs.update(r.document_id for r in sc.evidence_refs)
        if t.request is not None:
            claims.update(f"constraint:{c.constraint_id}" for c in t.request.constraints)
        for old, new in t.event.superseded_added:
            reports.update((old, new))
        for rid_, _rec, mid in t.event.forwards_added:
            reports.add(rid_)
            messages.add(mid)
        for pe in list(t.event.pool) + list(t.event.pool_before):
            claims.add(pe.claim_id)
            if pe.report_id:
                reports.add(pe.report_id)
            if pe.agent_id:
                agents.add(pe.agent_id)
    return {"claims": claims, "reports": reports, "messages": messages, "agents": agents, "documents": docs}


def check_identifiers(ctx: CheckContext, t: Transfer) -> None:
    """RCPT-006: every identifier the receipt names resolves somewhere (results are resolved by L3)."""
    rc = t.receipt
    if rc is None:
        return
    u = identifier_universe(ctx, t.seq)
    dangling: dict[str, list[str]] = {}

    def need(kind: str, ids, pool: set[str]) -> None:
        for x in ids:
            if x and x not in pool:
                dangling.setdefault(kind, [])
                if x not in dangling[kind]:
                    dangling[kind].append(x)

    for f in rc.findings:
        need("claim_ids", f.claim_ids, u["claims"])
        need("report_ids", f.report_ids, u["reports"])
        need("message_ids", f.message_ids, u["messages"])
        need("agent_ids", f.agent_ids, u["agents"])
        need("document_ids", f.document_ids, u["documents"])
    if rc.message_id != t.message_id:
        dangling.setdefault("message_id", []).append(rc.message_id)
    req = None
    if t.kind in ("response", "response_text") and t.request_seq is not None:
        req = ctx.view.by_seq[t.request_seq].request
    if req is not None:
        need("constraint_ids", [c.constraint_id for c in rc.constraint_results], {c.constraint_id for c in req.constraints})
        need("item_ids", [c.item_id for c in rc.coverage], {i.item_id for i in req.items})
    report_claims = {c.claim_id for c in t.report.claims} if t.report is not None else set()
    for cov in rc.coverage:
        need("claim_ids", cov.addressed_by_claim_ids, report_claims or u["claims"])
    for o in rc.outcomes:
        need("claim_ids", [o.claim_id], report_claims or u["claims"])
        need("report_ids", [o.report_id], {t.report_id} if t.report_id else u["reports"])
    for sf in rc.structural_findings:
        need("claim_ids", sf.claim_ids, u["claims"])
    if dangling:
        flat = "; ".join(f"{k}: {v[:8]}" for k, v in sorted(dangling.items()))
        ids = t.ids()
        ctx.ovs(t.seq, "OVS-RCPT-006", f"receipt {t.receipt_id} names identifiers that resolve nowhere in the journal, the plan, the log or the store ({flat})",
                claim_ids=dangling.get("claim_ids", []), message_ids=ids["message_ids"], report_ids=ids["report_ids"] + dangling.get("report_ids", []),
                agent_ids=ids["agent_ids"], document_ids=dangling.get("document_ids", []))


def check_summary(ctx: CheckContext, t: Transfer) -> None:
    """RCPT-007: the summary is the channel's own summary of the receipt's structured fields."""
    rc = t.receipt
    if rc is None:
        return
    if t.kind == "request":
        req = t.request
        if req is None:
            return
        expected = _fit_summary(TranslatorChannel._summary_request(req, rc.findings, rc.status))
    else:
        if not rc.summary.endswith(_SCOPE_TAIL):
            ctx.ovs(t.seq, "OVS-RCPT-007", f"receipt {t.receipt_id} does not end with the channel's scope sentence", **t.ids())
            return
        expected = _fit_summary(TranslatorChannel._summary_response(rc.status, rc.findings, rc.coverage, rc.constraint_results, rc.outcomes,
                                                                    rc.structural_findings, rc.formal_checks, rc.branch or "generic"))
    if rc.summary != expected:
        a, b = rc.summary, expected
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        ctx.ovs(t.seq, "OVS-RCPT-007", f"receipt {t.receipt_id} summary is not the summary of its own structured fields (first difference at character {i}: "
                f"{a[max(0, i - 20):i + 40]!r} vs {b[max(0, i - 20):i + 40]!r})", **t.ids())
