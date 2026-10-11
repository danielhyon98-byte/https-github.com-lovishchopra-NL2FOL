"""Claim-ledger accounting for the information-preserving combinator.

Structural accounting is necessary but not sufficient (context document, section 4):
it catches dropped, orphaned, inflated and evidence-stripped claims. Whether a
synthesized claim FOLLOWS from its sources is a formal question answered in
``cross_check.py``.
"""
from __future__ import annotations

from ..translate.contracts import ClaimRecord, SpecialistReport
from .contracts import CERTAINTY_RANK, IntegrityFinding, Synthesis


def _source_index(reports: list[SpecialistReport]) -> dict[str, ClaimRecord]:
    idx: dict[str, ClaimRecord] = {}
    for r in reports:
        for c in r.claims:
            idx[c.claim_id] = c
    return idx


def check_synthesis_ledger(reports: list[SpecialistReport], synthesis: Synthesis) -> list[IntegrityFinding]:
    f: list[IntegrityFinding] = []
    report_ids = {r.report_id for r in reports}
    missing_reports = [rid for rid in synthesis.source_report_ids if rid not in report_ids]
    if missing_reports:
        f.append(IntegrityFinding(code="INT-LEDGER-000", severity="error", message=f"synthesis cites reports that were not provided: {missing_reports}"))
    for r in reports:
        if r.request_id != synthesis.request_id or r.task_id != synthesis.task_id:
            f.append(IntegrityFinding(code="INT-LEDGER-008", severity="error", message=f"report {r.report_id} belongs to another request/task than the synthesis"))

    sources = _source_index(reports)
    accounted: set[str] = set()

    for sc in synthesis.claims:
        unknown = [sid for sid in sc.source_claim_ids if sid not in sources]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"synthesized claim cites unknown source claims {unknown}", claim_ids=[sc.claim_id] + unknown))
        known = [sources[sid] for sid in sc.source_claim_ids if sid in sources]
        accounted.update(sc.source_claim_ids)
        if sc.transformation == "new" or not sc.source_claim_ids:
            f.append(IntegrityFinding(code="INT-LEDGER-005", severity="error", message="synthesized claim has no source claim: the combinator introduced content no specialist asserted", claim_ids=[sc.claim_id]))
            continue
        if sc.transformation == "dropped":
            f.append(IntegrityFinding(code="INT-LEDGER-009", severity="error", message="a present synthesized claim cannot have transformation 'dropped'", claim_ids=[sc.claim_id]))
        if known:
            weakest = min(CERTAINTY_RANK[c.certainty] for c in known)
            if CERTAINTY_RANK[sc.certainty] > weakest:
                f.append(IntegrityFinding(code="INT-LEDGER-003", severity="error", message=f"certainty inflated: synthesis says {sc.certainty!r} but the weakest source is rank {weakest}", claim_ids=[sc.claim_id] + [c.claim_id for c in known]))
            if sc.transformation in ("carried", "paraphrased", "narrowed"):
                have = {(r.document_id, r.locator) for r in sc.evidence_refs}
                lost = [c.claim_id for c in known if c.materiality == "material" and any((r.document_id, r.locator) not in have for r in c.source_refs)]
                if lost:
                    f.append(IntegrityFinding(code="INT-LEDGER-004", severity="error", message="evidence references of material source claims were not preserved", claim_ids=[sc.claim_id] + lost))
            if sc.transformation == "carried" and len(known) == 1 and known[0].claim_text.strip() != sc.text.strip():
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message="claim marked 'carried' but its text differs from the source; record it as 'paraphrased' or a new linked claim", claim_ids=[sc.claim_id, known[0].claim_id]))
            if sc.transformation in ("merged", "generalized") and sc.materiality == "material":
                f.append(IntegrityFinding(code="INT-LEDGER-011", severity="info", message=f"material claim produced by '{sc.transformation}': formal synthesis-entailment check required", claim_ids=[sc.claim_id]))

    for entry in synthesis.ledger:
        accounted.update(entry.source_claim_ids)
        if entry.transformation == "dropped" and not entry.reason:
            f.append(IntegrityFinding(code="INT-LEDGER-006", severity="error", message="source claim dropped without a recorded reason", claim_ids=list(entry.source_claim_ids)))
        unknown = [sid for sid in entry.source_claim_ids if sid not in sources]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"ledger entry cites unknown source claims {unknown}", claim_ids=unknown))

    for cid, c in sources.items():
        if cid in accounted:
            continue
        sev = "error" if c.materiality == "material" else "info"
        f.append(IntegrityFinding(code="INT-LEDGER-002", severity=sev, message=f"{c.materiality} source claim is neither carried, transformed nor recorded as dropped", claim_ids=[cid]))

    for conf in synthesis.conflicts:
        if conf.status == "resolved_with_basis" and not conf.basis:
            f.append(IntegrityFinding(code="INT-CONFLICT-003", severity="error", message="conflict marked resolved without a documented basis", claim_ids=list(conf.claim_ids)))
        unknown = [cid for cid in conf.claim_ids if cid not in sources and cid not in {s.claim_id for s in synthesis.claims}]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"conflict record cites unknown claims {unknown}", claim_ids=unknown))
    return f
