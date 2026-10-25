"""Synthesis: does a synthesis account for the reports as they were delivered, and does it name every contradiction?

* SYN-001 (live): a delivered synthesis cites a report that, per the journal, was not delivered before it.
* B2 ledger re-check (batch): ``check_synthesis_ledger`` runs against the JOURNALED reports (never the live
  ``transmitted_reports``), with the channel's scope rule (the cited reports plus each agent's current report, in
  delivery order) and the journaled requests' texts as ``extra_texts``. An error the synthesis receipt lacks is
  SYN-002 naming the INT code and claims (a changed figure, an altered quotation, a dropped material claim, inflated
  certainty); an INT-LEDGER error the receipt carries that the re-check does not reproduce is RCPT-005 (warning).
* ``check_conflict_disclosure`` runs against every contradiction among the claims the synthesis accounts for: those
  named on the channel (its receipts' INT-CONFLICT-001 sets) and those the auditor's own joint check found (B3). A
  non-disclosure the receipt lacks is SYN-003.
"""
from __future__ import annotations

from typing import Iterable, Optional

from ...integrity.cross_check import check_conflict_disclosure
from ...integrity.ledger import check_synthesis_ledger
from ..view import Transfer
from . import CheckContext

__all__ = ["check_synthesis_citations", "ledger_scope", "recheck_ledger", "recheck_disclosure", "named_conflict_sets"]


def check_synthesis_citations(ctx: CheckContext, t: Transfer) -> None:
    """SYN-001."""
    if t.kind != "relay_synthesis" or not t.delivered or t.synthesis is None:
        return
    missing = [rid for rid, seq in t.cited_delivery_seqs.items() if seq is None]
    if missing:
        ids = t.ids()
        ctx.ovs(t.seq, "OVS-SYN-001", f"synthesis {t.synthesis.synthesis_id} ({t.message_id}) cites reports {missing} that were not delivered on this channel before it",
                message_ids=ids["message_ids"], report_ids=[t.synthesis.synthesis_id] + missing, agent_ids=ids["agent_ids"], claim_ids=[t.synthesis.synthesis_id])


def ledger_scope(ctx: CheckContext, t: Transfer):
    """The channel's scope rule on journaled deliveries: every cited report plus each agent's current report."""
    transmitted = ctx.view.transmitted_before(t.seq)
    latest: dict[str, str] = {}
    for rid, tr in transmitted.items():
        latest[tr.report.agent_id] = rid
    cited = set(t.synthesis.source_report_ids)
    return [tr.report for rid, tr in transmitted.items() if rid in cited or latest.get(tr.report.agent_id) == rid]


def _request_texts(ctx: CheckContext, before_seq: int) -> list[str]:
    out: list[str] = []
    for r in ctx.view.requests_before(before_seq):
        out.append(r.request.user_input)
        out += [s.text for s in r.request.supplied_texts]
    return list(dict.fromkeys(out))


def _key(f) -> tuple:
    return (f.code, f.severity, frozenset(f.claim_ids))


def recheck_ledger(ctx: CheckContext, t: Transfer) -> None:
    """B2: SYN-002 and RCPT-005 for one delivered synthesis."""
    if t.kind != "relay_synthesis" or not t.delivered or t.synthesis is None or t.receipt is None:
        return
    scope = ledger_scope(ctx, t)
    found = check_synthesis_ledger(scope, t.synthesis, extra_texts=_request_texts(ctx, t.seq))
    on_receipt = {_key(f) for f in t.receipt.findings}
    ids = t.ids()
    owners: dict[str, list[str]] = {}
    for r in scope:
        for c in r.claims:
            owners.setdefault(c.claim_id, []).append(r.report_id)
    for f in found:
        if f.severity != "error" or _key(f) in on_receipt:
            continue
        # the synthesis and the reports whose claims the finding names (claim ids are unique only within a report)
        rids = list(f.report_ids) or ids["report_ids"] + [r for c in f.claim_ids for r in owners.get(c, [])]
        ctx.ovs(t.seq, "OVS-SYN-002", f"the ledger re-check of synthesis {t.synthesis.synthesis_id} against the journaled reports finds {f.code} ({f.message[:300]}), which the synthesis receipt lacks",
                claim_ids=f.claim_ids, message_ids=ids["message_ids"], report_ids=rids, agent_ids=list(f.agent_ids) or ids["agent_ids"],
                document_ids=f.document_ids)
    reproduced = {_key(f) for f in found}
    for f in t.receipt.findings:
        if f.code.startswith("INT-LEDGER") and f.severity == "error" and _key(f) not in reproduced:
            ctx.ovs(t.seq, "OVS-RCPT-005", f"synthesis receipt {t.receipt_id} carries {f.code} for {f.claim_ids}, which the ledger re-check on the journaled reports does not reproduce",
                    claim_ids=f.claim_ids, message_ids=ids["message_ids"], report_ids=ids["report_ids"], agent_ids=ids["agent_ids"])


def named_conflict_sets(ctx: CheckContext, upto_seq: Optional[int] = None) -> list[tuple[int, frozenset[str], Optional[str], str]]:
    """Every contradiction a receipt of the channel named: ``(event seq, claim set, result id, code)`` for
    INT-CONFLICT-001 (synthesized claim ids removed) and INT-CONFLICT-005 (the one claim)."""
    out: list[tuple[int, frozenset[str], Optional[str], str]] = []
    synthesized: set[str] = set()
    for t in ctx.view.transfers:
        if t.synthesis is not None:
            synthesized.update(c.claim_id for c in t.synthesis.claims)
            synthesized.add(t.synthesis.synthesis_id)
    for t in ctx.view.transfers:
        if upto_seq is not None and t.seq > upto_seq:
            break
        if t.receipt is None:
            continue
        for f in t.receipt.findings:
            if f.code not in ("INT-CONFLICT-001", "INT-CONFLICT-005"):
                continue
            claims = frozenset(c for c in f.claim_ids if c not in synthesized)
            if f.code == "INT-CONFLICT-005" and f.claim_ids:
                claims = frozenset([f.claim_ids[-1]])
            if claims:
                out.append((t.seq, claims, f.formal_result_id, f.code))
    return out


def recheck_disclosure(ctx: CheckContext, t: Transfer, auditor_sets: Iterable[tuple[frozenset[str], Optional[str]]] = ()) -> None:
    """B2 disclosure: SYN-003 for a contradiction among the synthesis's claims that it does not disclose and whose
    non-disclosure the receipt does not name."""
    if t.kind != "relay_synthesis" or not t.delivered or t.synthesis is None or t.receipt is None:
        return
    scope_ids = {c.claim_id for r in ledger_scope(ctx, t) for c in r.claims}
    sets: list[tuple[frozenset[str], Optional[str]]] = []
    for _seq, claims, rid, code in named_conflict_sets(ctx, t.seq):
        if code == "INT-CONFLICT-001" and claims <= scope_ids:
            sets.append((claims, rid))
    for claims, rid in auditor_sets:
        if len(claims) >= 2 and claims <= scope_ids:
            sets.append((frozenset(claims), rid))
    found = check_conflict_disclosure(t.synthesis, sets)
    on_receipt = {frozenset(f.claim_ids) for f in t.receipt.findings if f.code == "INT-CONFLICT-002"}
    ids = t.ids()
    for f in found:
        if frozenset(f.claim_ids) in on_receipt:
            continue
        mids, rids, aids = ctx.message_ids_for_claims(f.claim_ids)
        ctx.ovs(t.seq, "OVS-SYN-003", f"synthesis {t.synthesis.synthesis_id} does not disclose the contradiction between {sorted(f.claim_ids)} and its receipt does not say so (INT-CONFLICT-002 absent)",
                claim_ids=f.claim_ids, message_ids=ids["message_ids"] + mids, report_ids=ids["report_ids"] + rids, agent_ids=ids["agent_ids"] + aids,
                formal_result_id=f.formal_result_id)
