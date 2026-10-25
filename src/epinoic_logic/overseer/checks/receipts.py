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
* RCPT-004 (implied findings, live, every transfer): the receipt's own structured results and the journaled inputs
  imply findings the channel always raises, at a fixed severity; one that is absent, or present at a lower severity,
  is RCPT-004 naming the code (RCPT-002 alone cannot see a finding dropped together with a consistently recomputed
  status, and the shadow is sampled):

  - every constraint result with ``satisfied`` false needs INT-REQ-005 naming it (its ``formal_result_id``, or for a
    deterministic constraint its id in the message): error for a word bound or any non-paragraph constraint, warning
    for a paragraph bound (the request's journaled constraint kind decides);
  - every branch formal check with ``satisfied`` false needs INT-SUBJ-001 (error), or INT-SUBJ-004 (warning) for a
    check its pack declares at failure severity warning (rule ``failure-severity``: the STEM checks that fail only under
    a reading the report did not state; R2 requires INT-SUBJ-001 for every check the pack declares at error), and with
    ``satisfied`` null INT-SUBJ-002 (warning), naming its ``formal_result_id``;
  - every finding of a code the channel raises at one severity only (:data:`FIXED_SEVERITY`, kept identical to the
    channel's code by a drift test) carries at least that severity;
  - a response that was not REJECTED passed the channel's identity checks, so they are re-run on the journaled
    envelope, request and plan: the sender is the agent the request was addressed to (else INT-REQ-001), the envelope
    binds the payload (``bind_payload``: INT-ENV-008), and every finding ``check_report_against_plan`` gives is on
    the receipt at its severity;
  - a delivered report (response, raw text or relay) whose report id an earlier journaled delivery carries with other
    content (compared without ``created_at``) needs INT-HANDOFF-015 (error, blocking);
  - a request needs INT-HANDOFF-002 when the journaled plan did not select its addressee, and INT-HANDOFF-004 when it
    supplies a document outside the plan's retrieval scope (both errors, so the request is REJECTED);
  - (review round 3) the plan is always the FIRST journaled plan (``view.plan_at``); a delivered response's coverage
    records are the image of the channel's coverage rule re-run on the journaled request and report (bound at import:
    a patched class is not used), and each unaddressed item has its own INT-REQ-004 at its severity; a response
    supplying texts the request did not needs INT-REQ-002; a delivered relay needs the relay-party rule
    (INT-HANDOFF-002), INT-HANDOFF-001 and, unless a router forward, ``bind_payload`` (INT-ENV-008); every delivered
    transfer's sender role may issue its contract (INT-ENV-007); a response whose event captured a signed
    INCONSISTENT_PREMISES run of the channel's cross-report joint check names a conflict (INT-CONFLICT-001/005/004);
    and a request's word and paragraph bounds are not weaker than its own user input states (``extract_constraints``).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Optional

from ...channel.bus import _BLOCKING_PREFIXES, _SCOPE_TAIL, TranslatorChannel, _fit_summary
from ...channel.contracts import TransmissionReceipt, TransmissionStatus
from ...channel.events import model_json
from ...engine.statuses import is_definitive
from ...ir.canonical import sha256_hex
from ..view import REPORT_KINDS, Transfer
from . import CheckContext, json_diff_paths

__all__ = ["check_receipt_custody", "check_presented_receipt", "expected_status", "check_status", "check_delivery", "check_identifiers",
           "check_summary", "identifier_universe", "check_implied_findings", "implied_findings", "FIXED_SEVERITY", "VARIABLE_SEVERITY"]

#: ``INT-*`` codes the channel and the integrity package raise at exactly one severity (every other code below is raised
#: at a severity that depends on the case: :data:`VARIABLE_SEVERITY`). A drift test scans the package's source and
#: keeps this table identical to what the code emits.
FIXED_SEVERITY: dict[str, str] = {
    **{c: "error" for c in (
        "INT-CONFLICT-001", "INT-CONFLICT-002", "INT-CONFLICT-003", "INT-ENV-002", "INT-ENV-003", "INT-ENV-004", "INT-ENV-006", "INT-ENV-007",
        "INT-ENV-008", "INT-ENV-009", "INT-ENV-010", "INT-ENV-011", "INT-GLOSSARY-001", "INT-GLOSSARY-003", "INT-GLOSSARY-004", "INT-GLOSSARY-006",
        "INT-GLOSSARY-007", "INT-HANDOFF-001", "INT-HANDOFF-002", "INT-HANDOFF-003", "INT-HANDOFF-004", "INT-HANDOFF-007", "INT-HANDOFF-008",
        "INT-HANDOFF-011", "INT-HANDOFF-012", "INT-HANDOFF-013", "INT-HANDOFF-015", "INT-INTERNAL-001", "INT-LEDGER-000", "INT-LEDGER-001",
        "INT-LEDGER-002", "INT-LEDGER-003", "INT-LEDGER-004", "INT-LEDGER-005", "INT-LEDGER-006", "INT-LEDGER-008", "INT-LEDGER-009",
        "INT-LEDGER-012", "INT-LEDGER-013", "INT-LEDGER-014", "INT-LEDGER-015", "INT-LEDGER-023", "INT-LEDGER-025", "INT-LEDGER-030", "INT-LEDGER-031", "INT-LEDGER-032",
        "INT-REQ-000", "INT-REQ-001", "INT-REQ-002", "INT-REQ-003", "INT-REQ-009", "INT-REQ-011", "INT-REQ-012", "INT-REQ-015",
        "INT-STALE-001", "INT-STALE-002", "INT-STALE-003", "INT-STALE-004", "INT-STALE-005", "INT-STALE-006", "INT-STALE-007", "INT-STALE-008",
        "INT-STALE-009", "INT-STALE-010", "INT-STALE-011", "INT-SUBJ-001", "INT-SUBJ-003", "INT-SYNTH-001", "INT-SYNTH-006", "INT-SYNTH-010",
        "INT-SYNTH-014")},
    **{c: "warning" for c in (
        "INT-CONFLICT-004", "INT-ENV-001", "INT-ENV-005", "INT-GLOSSARY-005", "INT-HANDOFF-005", "INT-HANDOFF-009", "INT-HANDOFF-010",
        "INT-HANDOFF-014", "INT-HANDOFF-016", "INT-HANDOFF-017", "INT-LEDGER-010", "INT-LEDGER-016", "INT-LEDGER-017", "INT-LEDGER-018", "INT-LEDGER-019",
        "INT-LEDGER-020", "INT-LEDGER-021", "INT-LEDGER-024", "INT-LEDGER-026", "INT-LEDGER-027", "INT-LEDGER-028", "INT-LEDGER-029", "INT-REQ-006",
        "INT-REQ-008",
        "INT-REQ-010", "INT-REQ-013", "INT-REQ-014", "INT-REQ-016", "INT-SUBJ-002", "INT-SUBJ-004", "INT-SYNTH-003", "INT-SYNTH-004", "INT-SYNTH-005", "INT-SYNTH-007", "INT-SYNTH-008", "INT-SYNTH-009",
        "INT-SYNTH-012", "INT-SYNTH-013")},
    **{c: "info" for c in ("INT-CONFLICT-006", "INT-GLOSSARY-002", "INT-HANDOFF-006", "INT-LEDGER-011", "INT-LEDGER-022", "INT-SYNTH-002", "INT-SYNTH-011")},
}
#: Codes raised at a severity that depends on the case (INT-REQ-004: required item or not; INT-REQ-005: word or
#: paragraph bound, checked by the constraint rule; INT-CONFLICT-005: a fixed or an assumed reading; INT-REQ-007: an error
#: for a TRANSLATED claim, a warning when its translation is AMBIGUOUS_TRANSLATION, checked by the rule
#: ``ambiguous-reading``). INT-LEDGER-027 and INT-LEDGER-028 are the development branch's warnings (a from-memory label
#: dropped; a misspelt quotation); the Overseer's review-round ledger errors raised under those numbers before the
#: translator merge are INT-LEDGER-030 (comparison turned, negation added) and INT-LEDGER-031 (text-composition). INT-LEDGER-029 is the
#: development branch's synthesis self-report (a warning); the Overseer's name-substitution error raised under that number before the
#: second translator merge is INT-LEDGER-032. INT-SYNTH-014 (a value outside the synthesis contract's closed vocabularies) and
#: INT-CONFLICT-006 (a disclosed conflict the hub found no contradiction for) are the development branch's too.
VARIABLE_SEVERITY = frozenset({"INT-REQ-004", "INT-REQ-005", "INT-REQ-007", "INT-CONFLICT-005"})
#: The channel's own rules the implied findings re-run, bound when this module is imported: a channel whose class is
#: patched later (a rule replaced at run time) is re-derived with the rule as shipped, not with the patch.
_CHANNEL_COVERAGE = TranslatorChannel._coverage
_CHANNEL_RELAY_PARTIES = TranslatorChannel._relay_parties
_RANK = {"info": 0, "warning": 1, "error": 2}


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


def _present(findings, code: str, severity: str, *, formal_result_id: Optional[str] = None, message_prefix: Optional[str] = None,
             claim_ids: Optional[set[str]] = None) -> Optional[str]:
    """None when a finding of ``code`` (naming the result, the message prefix or the claims, when given) is on the
    receipt at ``severity`` or above; else ``"absent"`` or the lower severity it carries."""
    best: Optional[str] = None
    for f in findings:
        if f.code != code:
            continue
        if formal_result_id is not None and f.formal_result_id != formal_result_id:
            continue
        if message_prefix is not None and not f.message.startswith(message_prefix):
            continue
        if claim_ids is not None and claim_ids and not (set(f.claim_ids) & claim_ids):
            continue
        if _RANK.get(f.severity, -1) >= _RANK[severity]:
            return None
        best = f.severity if best is None or _RANK.get(f.severity, -1) > _RANK.get(best, -1) else best
    return best or "absent"


def implied_findings(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """``(code, how, why)`` for every finding the receipt's structured results and the journaled inputs imply that the
    receipt lacks (``how`` is ``absent`` or the lower severity it carries)."""
    rc = t.receipt
    if rc is None:
        return []
    out: list[tuple[str, str, str]] = []
    req = ctx.view.by_seq[t.request_seq].request if t.request_seq is not None and t.request_seq in ctx.view.by_seq else None
    kinds = {c.constraint_id: c.kind for c in req.constraints} if req is not None else {}
    for cr in rc.constraint_results:
        if cr.satisfied is not False:
            continue
        sev = "warning" if kinds.get(cr.constraint_id, "").endswith("paragraphs") else "error"
        if cr.method == "formal" and cr.formal_result_id:
            how = _present(rc.findings, "INT-REQ-005", sev, formal_result_id=cr.formal_result_id)
        else:
            how = _present(rc.findings, "INT-REQ-005", sev, message_prefix=f"constraint {cr.constraint_id} not satisfied")
        if how:
            out.append(("INT-REQ-005", how, f"constraint {cr.constraint_id} is not satisfied on the receipt, so the channel raises INT-REQ-005 ({sev}) naming it"))
    for fc in rc.formal_checks:
        if fc.method != "formal" or not fc.formal_result_id or fc.satisfied is True:
            continue
        code, sev = ("INT-SUBJ-001", "error") if fc.satisfied is False else ("INT-SUBJ-002", "warning")
        how = _present(rc.findings, code, sev, formal_result_id=fc.formal_result_id)
        if how and fc.satisfied is False and _present(rc.findings, "INT-SUBJ-004", "warning", formal_result_id=fc.formal_result_id) is None:
            # rule failure-severity (STEM readiness): a check its pack declares at severity warning fails with INT-SUBJ-004
            # (warning); R2 (formal.check_branch_satisfied) requires INT-SUBJ-001 for every check the pack declares at error
            how = None
        if how:
            out.append((code, how, f"formal check {fc.constraint_id} is {'not satisfied' if fc.satisfied is False else 'undecided'} on the receipt, so the channel raises {code} ({sev}) naming it"
                        + (" (or INT-SUBJ-004, warning, for a check its pack declares at severity warning)" if fc.satisfied is False else "")))
    for f in rc.findings:
        fixed = FIXED_SEVERITY.get(f.code)
        if fixed is not None and _RANK.get(f.severity, -1) < _RANK[fixed]:
            out.append((f.code, f.severity, f"the channel raises {f.code} only at severity {fixed}"))
        if f.code == "INT-REQ-005" and f.formal_result_id:
            cr = next((c for c in rc.constraint_results if c.formal_result_id == f.formal_result_id), None)
            if cr is not None and f.severity != "error" and not kinds.get(cr.constraint_id, "paragraphs").endswith("paragraphs"):
                out.append((f.code, f.severity, f"constraint {cr.constraint_id} is a {kinds.get(cr.constraint_id)} bound, which the channel reports at severity error"))
        if f.code == "INT-REQ-007" and f.severity != "error":
            # rule ambiguous-reading: the channel lowers INT-REQ-007 to a warning only for a claim whose translation is
            # AMBIGUOUS_TRANSLATION (the inconsistency belongs to the translator's assumed reading); for any other claim it
            # is an error, and the finding names the claim's outcome by its result id
            o = next((x for x in rc.outcomes if f.formal_result_id and x.verification is not None and x.verification.result_id == f.formal_result_id), None)
            ambiguous = o is not None and getattr(o.translation.status, "value", o.translation.status) == "AMBIGUOUS_TRANSLATION"
            if not ambiguous:
                out.append((f.code, f.severity, "the channel raises INT-REQ-007 at severity error except for a claim whose translation is "
                            "AMBIGUOUS_TRANSLATION (rule ambiguous-reading); "
                            + ("this one names no outcome of the receipt" if o is None else f"claim {o.claim_id}'s translation is {getattr(o.translation.status, 'value', o.translation.status)}")))
    if t.kind in ("response", "response_text") and t.receipt.status is not TransmissionStatus.REJECTED and req is not None and t.report is not None:
        out.extend(_identity_implied(ctx, t, req))
        out.extend(_coverage_implied(ctx, t, req))
    out.extend(_reuse_implied(ctx, t))
    if t.kind == "request":
        out.extend(_request_scope_implied(ctx, t))
        out.extend(_request_constraints_implied(ctx, t))
    if t.kind in ("relay_forward", "relay_report", "relay_synthesis") and t.receipt.status is not TransmissionStatus.REJECTED:
        out.extend(_relay_implied(ctx, t))
    if t.receipt.status is not TransmissionStatus.REJECTED:
        out.extend(_role_implied(ctx, t))
    if t.kind in ("response", "response_text", "relay_report"):
        out.extend(_joint_implied(ctx, t))
    return out


def _branch_hooks(ctx: CheckContext, t: Transfer, rep) -> tuple[Any, str]:
    """``(hub hooks, profile key)`` of the branch that served ``rep``'s agent on this channel (its subject in the first
    journaled plan, else the plan's subject, resolved by the channel's registry): what the merged channel lends its
    heuristics. ``(None, "")`` when the branch lends none."""
    plan = ctx.view.plan_at(t.seq)
    registry = ctx.registry
    if registry is None:
        from ...branches import default_registry
        registry = default_registry()
    subject = plan.agent_subjects.get(rep.agent_id, plan.subject) if plan is not None else rep.subject
    try:
        branch, profile = registry.for_subject(subject)
    except Exception:
        return None, ""
    hooks = getattr(branch, "hub_hooks", None)
    return (hooks or None), (getattr(profile, "key", "") if hooks else "")


def _coverage_implied(ctx: CheckContext, t: Transfer, req) -> list[tuple[str, str, str]]:
    """The channel's coverage rule (``TranslatorChannel._coverage``, a deterministic lexical rule: called, not copied)
    re-run on the journaled request and report: the receipt's coverage records must be its image, and every item it
    leaves unaddressed needs its own INT-REQ-004 (warning for a required item, info otherwise). A receipt that marks an
    unaddressed item addressed, and drops its INT-REQ-004, is the exact image of nothing that was checked."""
    rc = t.receipt
    rep = t.report
    echoed = any(f.code == "INT-REQ-011" for f in rc.findings)
    # rule merged-coverage (the translator merge): the merged channel lends the coverage rule the branch's hub hooks (the
    # STEM branches give each claim the dimensions of its quantities as extra words), so the re-run is given the hooks of
    # the branch serving the report's agent and that branch's profile key, read from the first journaled plan and the
    # registry, and the channel's own hook guard; a branch with no hooks is re-run exactly as before
    hooks, profile_key = _branch_hooks(ctx, t, rep)
    try:
        expected = _CHANNEL_COVERAGE(SimpleNamespace(_hook=TranslatorChannel._hook), req, rep, echoed=echoed, hooks=hooks, profile_key=profile_key)
    except Exception as exc:
        ctx.note(f"{t.kind} {t.message_id}: the channel's coverage rule could not be re-run on the journaled request and report ({type(exc).__name__}); "
                 "its coverage records and INT-REQ-004 are not re-derived")
        return []
    out: list[tuple[str, str, str]] = []
    exp = sorted((c.item_id, c.addressed, tuple(sorted(c.addressed_by_claim_ids))) for c in expected)
    got = sorted((c.item_id, c.addressed, tuple(sorted(c.addressed_by_claim_ids))) for c in rc.coverage)
    if exp != got:
        wrong = sorted({e[0] for e in exp} ^ {g[0] for g in got} | {e[0] for e, g in zip(exp, got) if e != g})
        out.append(("coverage records", "different", f"the channel's coverage rule re-run on the journaled request and report gives items {wrong[:8]} other coverage "
                    f"than the receipt states ({[(e[0], e[1]) for e in exp][:8]} re-derived, {[(g[0], g[1]) for g in got][:8]} on the receipt)"))
    items = {i.item_id: i for i in req.items}
    for c in expected:
        if c.addressed or c.item_id not in items:
            continue
        sev = "warning" if items[c.item_id].required else "info"
        how = _present(rc.findings, "INT-REQ-004", sev, message_prefix=f"request item {c.item_id} appears unaddressed")
        if how:
            out.append(("INT-REQ-004", how, f"request item {c.item_id} is unaddressed under the channel's coverage rule re-run on the journaled request and report, "
                        f"so the channel raises INT-REQ-004 ({sev}) naming it"))
    return out


def _request_constraints_implied(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """A request's word and paragraph bounds against the bounds its own ``user_input`` states (``extract_constraints``,
    the rule the channel applies when no constraints are given): a bound the user input states that the request drops,
    or carries weaker ("no more than 80 words" checked as 800), is a miscommunicated transfer (RCPT-004)."""
    from ...channel.request_parser import extract_constraints
    req = t.request
    if req is None:
        return []
    try:
        stated = extract_constraints(req.user_input)
    except Exception:
        return []
    out: list[tuple[str, str, str]] = []
    for c in stated:
        if c.kind not in ("max_words", "min_words", "max_paragraphs", "min_paragraphs") or c.value is None:
            continue
        try:
            want = int(str(c.value))
        except ValueError:
            continue
        held = []
        for x in req.constraints:
            if x.kind == c.kind and x.value is not None:
                try:
                    held.append(int(str(x.value)))
                except ValueError:
                    continue
        strongest = (min(held) if c.kind.startswith("max") else max(held)) if held else None
        if strongest is None or (strongest > want if c.kind.startswith("max") else strongest < want):
            out.append(("request constraints", "weaker", f"the request's user input states {c.kind} {want}, but the request checks "
                        + (f"{c.kind} {strongest}" if strongest is not None else "no such bound") + ": the answer is held to a weaker bound than the one asked for"))
    return out


def _router_ids_before(ctx: CheckContext, seq: int) -> set[str]:
    """The senders of the requests the channel accepted before ``seq`` (the merged channel's ``router_ids``)."""
    out: set[str] = set()
    for x in ctx.view.transfers:
        if x.seq >= seq or x.kind != "request" or x.receipt is None or x.receipt.status is TransmissionStatus.REJECTED:
            continue
        sender = x.call.get("from_agent_id") if isinstance(x.call.get("from_agent_id"), str) else x.sender_agent_id
        if sender:
            out.add(sender)
    return out


def _relay_implied(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """The relay path's blocking rules re-run on the journaled call, envelope and the FIRST journaled plan: the sender
    and the recipient are parties the plan selected unless they act in an infrastructure role, and a synthesis names a
    selected combinator (``TranslatorChannel._relay_parties``, INT-HANDOFF-002); the payload belongs to the plan's
    request and task (INT-HANDOFF-001); a relay that is not a router forward is bound to its payload (``bind_payload``,
    INT-ENV-008). Each is an error the channel REJECTS on, so a delivered relay that needed one lacks it (RCPT-004)."""
    from types import SimpleNamespace
    from ...integrity.contracts import AgentMessage, AgentRole
    from ...integrity.envelope import bind_payload
    from ..faithful import faithful
    rc = t.receipt
    plan = ctx.view.plan_at(t.seq)
    obj = t.synthesis if t.kind == "relay_synthesis" else t.report
    env = t.envelope or {}
    if plan is None or obj is None or not env:
        return []
    try:
        msg = faithful(AgentMessage, env)
        from_role = AgentRole(t.call.get("from_role") or env.get("sender_role"))
        to_role = AgentRole(t.call.get("to_role") or env.get("recipient_role"))
    except Exception:
        return []
    to_agent = t.call.get("to_agent_id") if isinstance(t.call.get("to_agent_id"), str) else env.get("recipient_agent_id")
    expected = []
    try:
        # the merged channel holds the router's identity as the senders of its accepted requests (``router_ids``, read by
        # the INT-ENV-007 rule of ``_relay_parties``): re-derived from the requests journaled before this relay
        expected += _CHANNEL_RELAY_PARTIES(SimpleNamespace(plan=plan, router_ids=_router_ids_before(ctx, t.seq)), msg, from_role, to_agent or "", to_role, obj)
    except Exception as exc:  # never silent: the coverage notes say which rules were not re-derived
        ctx.note(f"relay {t.message_id}: the channel's relay-party rule could not be re-run on the journaled relay ({type(exc).__name__}); "
                 "its INT-HANDOFF-002 and INT-ENV-007 are not re-derived")
    out: list[tuple[str, str, str]] = []
    for f in expected:
        how = _present(rc.findings, f.code, "error")
        if how:
            out.append((f.code, how, f"re-run on the journaled relay and the first journaled plan: {f.message[:200]}"))
    if obj.request_id != plan.request_id or obj.task_id != plan.task_id:
        how = _present(rc.findings, "INT-HANDOFF-001", "error")
        if how:
            out.append(("INT-HANDOFF-001", how, f"the relayed payload belongs to request/task {obj.request_id}/{obj.task_id}, not the plan's {plan.request_id}/{plan.task_id}"))
    if t.kind != "relay_forward":
        try:
            bound = bind_payload(msg, obj)
        except Exception:
            bound = []
        for f in bound:
            how = _present(rc.findings, f.code, f.severity)
            if how:
                out.append((f.code, how, f"re-run on the journaled envelope: {f.message[:200]}"))
    return out


def _role_implied(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """INT-ENV-007 (error, blocking): the envelope's sender role may issue its contract (``allowed_sender_roles``, the
    ROLE_CONTRACTS table), re-checked on the journaled envelope of every transfer the channel did not reject."""
    from ...integrity.envelope import allowed_sender_roles
    env = t.envelope or {}
    contract, role = env.get("contract"), env.get("sender_role")
    if not isinstance(contract, str) or not isinstance(role, str):
        return []
    allowed = allowed_sender_roles(contract)
    if allowed is None or role in {r.value for r in allowed}:
        return []
    how = _present(t.receipt.findings, "INT-ENV-007", "error")
    if not how:
        return []
    return [("INT-ENV-007", how, f"a {role} may not issue the contract {contract!r} (allowed senders: {sorted(r.value for r in allowed)})")]


#: Problem id of the channel's cross-report joint consistency run over the whole pool (``check_cross_report_consistency``;
#: its attribution sub-runs carry other ids).
JOINT_PROBLEM_PREFIX = "joint-cross-report"


def _joint_implied(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """A signed INCONSISTENT_PREMISES run of the channel's cross-report joint check captured in this event decides that
    the pooled claims contradict each other: the receipt must name it (INT-CONFLICT-001 or -005, or the -004 assumed-reading
    warning). An engine-side insider answering the channel's check with a re-signed CONSISTENT would otherwise hide the
    contradiction from the router until the batch tier's independent joint check (B3)."""
    rc = t.receipt
    if rc is None or not t.event.captured:
        return []
    found = []
    for c in t.event.captured:
        if not c.result_json or f'"{JOINT_PROBLEM_PREFIX}"' not in c.result_json:
            continue
        try:
            data = json.loads(c.result_json)
        except Exception:
            continue
        pid = str(data.get("problem_id") or "")
        if pid == JOINT_PROBLEM_PREFIX and data.get("status") == "INCONSISTENT_PREMISES":
            found.append(c.result_id)
    if not found:
        return []
    named = any(f.code in ("INT-CONFLICT-001", "INT-CONFLICT-005") or (f.code == "INT-CONFLICT-004") for f in rc.findings)
    if named:
        return []
    return [("INT-CONFLICT-001", "absent", f"the channel's cross-report joint check ran in this event and the engine signed INCONSISTENT_PREMISES "
             f"(results {found[:4]}): the pooled claims contradict each other, and the receipt names no conflict")]


#: Findings after which the channel returns before its report-id reuse rule runs (no request, a payload that does not
#: re-validate, a claim of another report).
_REUSE_SKIPPED = frozenset({"INT-REQ-000", "INT-REQ-009", "INT-HANDOFF-012"})


def _content(payload: Optional[dict]) -> Optional[dict]:
    """A journaled report payload without its delivery timestamp: the channel's ``_content_dump`` of the report."""
    if not isinstance(payload, dict):
        return None
    return {k: v for k, v in payload.items() if k != "created_at"}


def _reuse_implied(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """INT-HANDOFF-015 (error, blocking): a report id already delivered on this channel arrives again with different
    content (the journaled payloads compared without ``created_at``, as the channel's ``_content_dump`` compares them).
    Re-derived from the journaled earlier delivery, so a channel that omits the finding is caught live."""
    rc = t.receipt
    rep = t.report
    if rc is None or rep is None or t.kind not in ("response", "response_text", "relay_report"):
        return []
    if {f.code for f in rc.findings} & _REUSE_SKIPPED:
        return []
    held = ctx.view.first_delivery(rep.report_id, before_seq=t.seq)
    if held is None:
        return []
    a, b = _content(held.payload), _content(t.payload)
    if a is None or b is None or a == b:
        return []
    how = _present(rc.findings, "INT-HANDOFF-015", "error")
    if not how:
        return []
    changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return [("INT-HANDOFF-015", how, f"report id {rep.report_id!r} was delivered at event {held.seq} ({held.message_id}) with other content ({changed[:8]} differ): "
             "a reused report id with a different payload is blocking and is not delivered")]


def _request_scope_implied(ctx: CheckContext, t: Transfer) -> list[tuple[str, str, str]]:
    """The request path's plan-scope rules re-run on the journaled plan and request: the addressee is an agent the plan
    selected (INT-HANDOFF-002) and every supplied document is within the plan's retrieval scope (INT-HANDOFF-004)."""
    rc = t.receipt
    req = t.request
    plan = ctx.view.plan_at(t.seq)
    if rc is None or req is None or plan is None:
        return []
    out: list[tuple[str, str, str]] = []
    if req.to_agent_id not in plan.selected_agent_ids:
        how = _present(rc.findings, "INT-HANDOFF-002", "error")
        if how:
            out.append(("INT-HANDOFF-002", how, f"the request is addressed to {req.to_agent_id!r}, which the journaled plan did not select ({sorted(plan.selected_agent_ids)})"))
    if plan.allowed_document_ids:
        outside = sorted({d.document_id for d in req.supplied_texts if d.document_id not in set(plan.allowed_document_ids)})
        if outside:
            how = _present(rc.findings, "INT-HANDOFF-004", "error")
            if how:
                out.append(("INT-HANDOFF-004", how, f"the request supplies documents outside the journaled plan's retrieval scope: {outside[:8]}"))
    return out


def _identity_implied(ctx: CheckContext, t: Transfer, req) -> list[tuple[str, str, str]]:
    """The respond path's identity and plan checks, re-run on the journaled envelope, request and plan (a response the
    channel delivered passed them, or carries what they give)."""
    from ...integrity.contracts import AgentMessage
    from ...integrity.envelope import bind_payload
    from ...integrity.handoff import check_report_against_plan
    from ..faithful import faithful
    rc = t.receipt
    rep = t.report
    out: list[tuple[str, str, str]] = []
    sender = t.sender_agent_id
    if sender is not None and sender != req.to_agent_id:
        how = _present(rc.findings, "INT-REQ-001", "error")
        if how:
            out.append(("INT-REQ-001", how, f"the response came from {sender!r} but the request was addressed to {req.to_agent_id!r}"))
    expected = []
    try:
        expected += bind_payload(faithful(AgentMessage, t.envelope), rep)
    except Exception:
        pass
    plan = ctx.view.plan_at(t.seq)
    if plan is not None:
        expected += check_report_against_plan(plan, rep)
    # The channel's rule (``TranslatorChannel._supplied_text_mismatch``), re-derived here on its own: a report text whose
    # document id the journaled request did not send (also when it sent none), or whose text differs from the one sent
    # under that id (SHA-256 of the text), is INT-REQ-002 (error, blocking); quotations are checked against the router's
    # texts only.
    from ...translate.contracts import sha256_text
    req_texts = {d.document_id: sha256_text(d.text) for d in req.supplied_texts}
    bad = sorted({d.document_id for d in rep.supplied_texts if req_texts.get(d.document_id) != sha256_text(d.text)})
    if bad:
        how = _present(rc.findings, "INT-REQ-002", "error")
        if how:
            out.append(("INT-REQ-002", how, f"the report supplies texts {bad[:8]} the journaled request did not send, or changed"))
    seen: set[tuple[str, str]] = set()
    for f in expected:
        if (f.code, f.severity) in seen:
            continue
        seen.add((f.code, f.severity))
        how = _present(rc.findings, f.code, f.severity, claim_ids=set(f.claim_ids) if f.code in ("INT-HANDOFF-006", "INT-HANDOFF-012") else None)
        if how:
            out.append((f.code, how, f"re-run on the journaled envelope and plan: {f.message[:200]}"))
    return out


def check_implied_findings(ctx: CheckContext, t: Transfer) -> None:
    """RCPT-004 for every implied finding the receipt lacks or carries at a lower severity (module docstring)."""
    for code, how, why in implied_findings(ctx, t):
        if not code.startswith("INT-"):  # a structured field (coverage records, request constraints), not a finding
            ctx.ovs(t.seq, "OVS-RCPT-004", f"receipt {t.receipt_id} of {t.kind} {t.message_id}: {code} {how}: {why}", **t.ids())
            continue
        what = "lacks it" if how == "absent" else f"carries it at severity {how}"
        ctx.ovs(t.seq, "OVS-RCPT-004", f"receipt {t.receipt_id} of {t.kind} {t.message_id} implies {code} but {what}: {why}", **t.ids())
