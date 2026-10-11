"""Every ``OVS-*`` finding code, with exactly one severity, the stage that decides it and what it means.

The table is the single source: a finding is built only through :func:`ovs_finding`, which takes the
severity from here, so no check can raise a code under another severity. ``OVS-AGENT-*`` codes concern
overseer agents and never change a transfer's clearance (design decision 16).
"""
from __future__ import annotations

from typing import Literal, Optional

from ..integrity.contracts import IntegrityFinding

Severity = Literal["error", "warning", "info"]

#: code -> (severity, stage, meaning)
OVS_CODES: dict[str, tuple[Severity, str, str]] = {
    "OVS-CUST-001": ("error", "custody", "envelope payload altered after issue (rehash or canonical diff against the journal; names the JSON paths; the journal copy is authoritative)"),
    "OVS-CUST-002": ("error", "custody", "envelope header altered after issue (envelope digest differs; names the fields)"),
    "OVS-CUST-003": ("error", "custody", "transfer not journaled (written around the channel), or a journaled message missing from the log"),
    "OVS-CUST-004": ("error", "custody", "a typed copy (transmitted_reports, ch.requests) diverges from the journaled delivery"),
    "OVS-CUST-005": ("error", "custody", "journal chain broken (hash, link, sequence or HMAC); everything after the break is unverifiable and the task audit fails"),
    "OVS-CUST-006": ("error", "custody", "the raw text the hub received is not the text that was parsed or refused"),
    "OVS-RCPT-001": ("error", "receipts", "receipt differs from the journaled receipt (the channel's copy or the copy the router presents; names the fields)"),
    "OVS-RCPT-002": ("error", "receipts", "receipt status is not the image of its contents under the channel's status rule"),
    "OVS-RCPT-003": ("error", "receipts", "delivery contradicts status (a REJECTED transfer delivered, pooled, forwarded or recorded, or an accepted one not recorded)"),
    "OVS-RCPT-004": ("error", "receipts", "an error-level finding re-derived on journaled inputs (shadow replay) is absent from the receipt (names the code)"),
    "OVS-RCPT-005": ("warning", "receipts", "a receipt finding the re-derivation does not reproduce"),
    "OVS-RCPT-006": ("error", "receipts", "the receipt names identifiers that resolve nowhere"),
    "OVS-RCPT-007": ("error", "receipts", "the summary states something the structured fields do not support, or a non-request receipt lacks the scope sentence"),
    "OVS-RCPT-008": ("error", "receipts", "the shadow channel, fed the journaled inputs, issues another status for this transfer, and no undecided engine run explains it"),
    "OVS-RES-001": ("error", "results", "a cited result under a local key id was never produced by the engine while capture was active"),
    "OVS-RES-002": ("warning", "results", "a cited result is not retained (evicted, before attachment, degraded mode); unverifiable, not an accusation"),
    "OVS-RES-003": ("error", "results", "result unsigned, signature invalid, or signed under an undeclared key id"),
    "OVS-RES-004": ("error", "results", "result bound to another problem or ids, or its binding is internally inconsistent"),
    "OVS-RES-005": ("error", "results", "result out of task or reused (another channel, task or request, a later event, or an earlier event re-cited as fresh)"),
    "OVS-RES-006": ("error", "results", "one result id with two contents, or a receipt copy not byte-identical to the stored result"),
    "OVS-RES-007": ("error", "results", "replay on a fresh engine gives another definitive status, or another problem or config digest"),
    "OVS-RES-008": ("warning", "results", "replay inconclusive (timeout or unknown on either side, component versions changed, budget exceeded)"),
    "OVS-RES-009": ("error", "results", "display status not derivable from the translation and the signed result"),
    "OVS-RES-010": ("error", "results", "outcome translation not bound to the delivered claim (claim text digest or ids)"),
    "OVS-FORM-001": ("error", "formal", "formal_status differs from the cited result's status"),
    "OVS-FORM-002": ("error", "formal", "satisfied is not the image of the status"),
    "OVS-FORM-003": ("error", "formal", "the checked problem is not the one re-derived from the payload (recount or pack digest)"),
    "OVS-FORM-004": ("error", "formal", "a re-derived formal check is absent from the receipt"),
    "OVS-FID-001": ("error", "fidelity", "a delivered claim text does not occur in original_response"),
    "OVS-FID-002": ("error", "fidelity", "a quotation or excerpt in a delivered claim is absent from original_response"),
    "OVS-FID-003": ("error", "fidelity", "a figure or date in a delivered claim is absent from original_response under every spelling"),
    "OVS-FID-004": ("error", "fidelity", "a quotation located in no supplied text, with no receipt finding naming the claim"),
    "OVS-FID-005": ("error", "fidelity", "a self-report or self-certification (by its own fields or the branch detector) delivered as content"),
    "OVS-FID-006": ("warning", "fidelity", "response content that no claim carries (parse loss)"),
    "OVS-FID-007": ("warning", "fidelity", "quotations self-grounded (checked only against texts the specialist supplied)"),
    "OVS-FID-008": ("error", "fidelity", "a supplied text under a requested document id altered in the report"),
    "OVS-FID-009": ("warning", "fidelity", "the auditor's independent structural detector flags a self-certification delivered as content"),
    "OVS-PEER-001": ("error", "peer", "forward not byte-identical to the delivery, or a forward of an undelivered or REJECTED report"),
    "OVS-PEER-002": ("error", "peer", "peer document differs from the forwarded original_response, or no forward to that recipient preceded it"),
    "OVS-PEER-003": ("info", "peer", "peer document linked to its forward by text equality only"),
    "OVS-SYN-001": ("error", "synthesis", "synthesis cites a report not delivered before it"),
    "OVS-SYN-002": ("error", "synthesis", "a ledger fault found against the journaled reports is absent from the synthesis receipt (names the INT code)"),
    "OVS-SYN-003": ("error", "synthesis", "a conflict non-disclosure (against all contradictions) is absent from the synthesis receipt"),
    "OVS-JOINT-001": ("error", "joint", "unnamed contradiction (claim-minimal; cites the auditor's signed run)"),
    "OVS-JOINT-002": ("warning", "joint", "independent joint check undecided, not buildable, or over the joint limits"),
    "OVS-JOINT-003": ("error", "joint", "a named conflict not reproduced by the engine (false conflict)"),
    "OVS-JOINT-004": ("error", "joint", "the live pool differs from the journaled snapshot or from the outcomes' problems"),
    "OVS-DIV-001": ("error", "divergence", "an error-level integrity rule fires in the Overseer's report but on no receipt (names the INT code, classification and owner)"),
    "OVS-DIV-002": ("warning", "divergence", "a warning- or info-level rule divergence"),
    "OVS-AUDIT-001": ("error", "audit", "an audit check failed internally (named); no PASSED state"),
    "OVS-AUDIT-002": ("warning", "audit", "audit coverage lost (eviction, capture inactive, digest-only journal, queue overflow, degraded view)"),
    "OVS-AUDIT-003": ("info", "audit", "live replay sampled (k of n replayed)"),
    "OVS-AUDIT-004": ("error", "audit", "no verification key configured for a declared key id in use"),
    "OVS-AGENT-001": ("error", "verdicts", "an overseer agent's statement is refuted by a verified signed result or a deterministic check"),
    "OVS-AGENT-002": ("warning", "verdicts", "an accusation's identifiers or evidence pointers do not resolve"),
    "OVS-AGENT-003": ("info", "verdicts", "accusation confirmed; the router acts on the confirming OVS-* finding"),
    "OVS-AGENT-004": ("warning", "verdicts", "accusation neither confirmed nor refuted (human review)"),
    "OVS-AGENT-005": ("error", "verdicts", "verdict invalid (unparseable, schema, role, contract, signature, digest or dossier binding); discarded"),
}

#: The stage names an audit's ``checks_run`` uses, in run order.
STAGES = ("custody", "receipts", "results", "formal", "fidelity", "peer", "synthesis", "joint", "divergence", "shadow", "replay", "verdicts")


def severity_of(code: str) -> Severity:
    return OVS_CODES[code][0]


def is_agent_code(code: str) -> bool:
    return code.startswith("OVS-AGENT-")


def ovs_finding(code: str, message: str, *, claim_ids=(), message_ids=(), report_ids=(), agent_ids=(), document_ids=(),
                formal_result_id: Optional[str] = None, related_result_ids=()) -> IntegrityFinding:
    """An ``OVS-*`` finding with the table's severity. Identifier lists are deduplicated in first-seen order;
    every finding is deterministic (decided by a digest, an HMAC, a re-run of repository rules or an
    auditor-signed engine run, never by agent text)."""
    if code not in OVS_CODES:
        raise KeyError(f"unknown Overseer code {code!r}")

    def ids(xs) -> list[str]:
        return list(dict.fromkeys(str(x) for x in xs if x is not None and str(x) != ""))

    related = [r for r in ids(related_result_ids) if r != formal_result_id]
    return IntegrityFinding(code=code, severity=OVS_CODES[code][0], message=message, claim_ids=ids(claim_ids), message_ids=ids(message_ids),
                            report_ids=ids(report_ids), agent_ids=ids(agent_ids), document_ids=ids(document_ids),
                            formal_result_id=formal_result_id, related_result_ids=related, deterministic=True)
