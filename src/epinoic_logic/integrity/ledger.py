"""Claim-ledger accounting for the information-preserving combinator.

Structural accounting is necessary but not sufficient (context document, section 4):
it catches dropped, orphaned, inflated and evidence-stripped claims, id collisions
between reports and between the source and synthesis namespaces, ledger entries that
point nowhere, and student-facing text that diverges from the claim ledger. Whether a
synthesized claim FOLLOWS from its sources is a formal question answered in
``cross_check.py``.
"""
from __future__ import annotations

import re
from typing import Optional

from ..translate.contracts import ClaimRecord, SpecialistReport
from .contracts import CERTAINTY_RANK, IntegrityFinding, Synthesis

PLACEHOLDERS = frozenset({"n/a", "na", "-", ".", "tbd", "see above", "none", "null", "nil", "todo", "?", "x", "...", "as above", "same"})
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_LIST_MARKER_RE = re.compile(r"(?m)^\s*\(?\d{1,2}[.)]\s")


def meaningful(text: Optional[str]) -> bool:
    """A reason or basis counts only if it says something: whitespace, punctuation
    and placeholder strings ('n/a', '-', 'see above', ...) do not."""
    if not text:
        return False
    t = " ".join(text.split()).casefold()
    if not t or t in PLACEHOLDERS:
        return False
    return sum(ch.isalpha() for ch in t) >= 3


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def report_set_findings(reports: list[SpecialistReport]) -> tuple[list[IntegrityFinding], set[str]]:
    """Duplicate report ids (INT-LEDGER-013) and claim ids shared across reports
    (INT-LEDGER-014). Returns the findings and the set of colliding claim ids, which
    no ledger accounting may silently resolve."""
    f: list[IntegrityFinding] = []
    by_rid: dict[str, list[SpecialistReport]] = {}
    for r in reports:
        by_rid.setdefault(r.report_id, []).append(r)
    for rid, rs in by_rid.items():
        if len(rs) > 1:
            f.append(IntegrityFinding(code="INT-LEDGER-013", severity="error", message=f"report id {rid!r} is used by {len(rs)} reports (agents {[r.agent_id for r in rs]}); report-level provenance is ambiguous", report_ids=[rid], agent_ids=sorted({r.agent_id for r in rs}), claim_ids=[c.claim_id for r in rs for c in r.claims]))
    owners: dict[str, list[SpecialistReport]] = {}
    for r in reports:
        for c in r.claims:
            owners.setdefault(c.claim_id, []).append(r)
    colliding: set[str] = set()
    for cid, rs in owners.items():
        if len({r.report_id for r in rs}) > 1 or len(rs) > 1:
            colliding.add(cid)
            f.append(IntegrityFinding(code="INT-LEDGER-014", severity="error", message=f"claim id {cid!r} appears in reports {[r.report_id for r in rs]}; neither copy can be accounted for by id", claim_ids=[cid], report_ids=[r.report_id for r in rs], agent_ids=sorted({r.agent_id for r in rs})))
    return f, colliding


def _source_index(reports: list[SpecialistReport], colliding: set[str]) -> tuple[dict[str, ClaimRecord], dict[str, str]]:
    idx: dict[str, ClaimRecord] = {}
    report_of: dict[str, str] = {}
    for r in reports:
        for c in r.claims:
            if c.claim_id in colliding:
                continue
            idx[c.claim_id] = c
            report_of[c.claim_id] = r.report_id
    return idx, report_of


def check_synthesis_ledger(reports: list[SpecialistReport], synthesis: Synthesis) -> list[IntegrityFinding]:
    f: list[IntegrityFinding] = []
    sid = [synthesis.synthesis_id]
    report_ids = {r.report_id for r in reports}
    missing_reports = [rid for rid in synthesis.source_report_ids if rid not in report_ids]
    if missing_reports:
        f.append(IntegrityFinding(code="INT-LEDGER-000", severity="error", message=f"synthesis cites reports that were not provided: {missing_reports}", report_ids=missing_reports, agent_ids=[synthesis.combinator_agent_id], claim_ids=sid))
    for r in reports:
        if r.request_id != synthesis.request_id or r.task_id != synthesis.task_id:
            f.append(IntegrityFinding(code="INT-LEDGER-008", severity="error", message=f"report {r.report_id} belongs to another request/task ({r.request_id}/{r.task_id}) than the synthesis ({synthesis.request_id}/{synthesis.task_id})", report_ids=[r.report_id], agent_ids=[r.agent_id], claim_ids=[c.claim_id for c in r.claims]))

    set_findings, colliding = report_set_findings(reports)
    f += set_findings
    sources, report_of = _source_index(reports, colliding)
    all_source_ids = {c.claim_id for r in reports for c in r.claims}
    synthesized_ids = {s.claim_id for s in synthesis.claims}
    accounted: set[str] = set()
    listed_reports = set(synthesis.source_report_ids)

    for sc in synthesis.claims:
        if sc.claim_id in all_source_ids:
            f.append(IntegrityFinding(code="INT-LEDGER-015", severity="error", message=f"synthesized claim reuses the source claim id {sc.claim_id!r} (report {report_of.get(sc.claim_id, '?')}); a changed claim must be a NEW record linked to its source, never a rewrite under the same id", claim_ids=[sc.claim_id], report_ids=[report_of[sc.claim_id]] if sc.claim_id in report_of else [], agent_ids=[synthesis.combinator_agent_id]))
        unknown = [s for s in sc.source_claim_ids if s not in sources and s not in colliding]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"synthesized claim cites unknown source claims {unknown}", claim_ids=[sc.claim_id] + unknown, agent_ids=[synthesis.combinator_agent_id]))
        known = [sources[s] for s in sc.source_claim_ids if s in sources]
        foreign = sorted({report_of[c.claim_id] for c in known if report_of[c.claim_id] not in listed_reports})
        if foreign:
            f.append(IntegrityFinding(code="INT-LEDGER-016", severity="warning", message=f"synthesized claim cites source claims from reports {foreign} that the synthesis does not list in source_report_ids", claim_ids=[sc.claim_id] + [c.claim_id for c in known if report_of[c.claim_id] in foreign], report_ids=foreign))
        accounted.update(s for s in sc.source_claim_ids if s not in colliding)
        if sc.transformation == "new" or not sc.source_claim_ids:
            f.append(IntegrityFinding(code="INT-LEDGER-005", severity="error", message="synthesized claim has no source claim: the combinator introduced content no specialist asserted", claim_ids=[sc.claim_id], agent_ids=[synthesis.combinator_agent_id]))
            continue
        if sc.transformation == "dropped":
            f.append(IntegrityFinding(code="INT-LEDGER-009", severity="error", message="a present synthesized claim cannot have transformation 'dropped'", claim_ids=[sc.claim_id]))
        if not known:
            continue
        known_ids = [c.claim_id for c in known]
        material_sources = [c for c in known if c.materiality == "material"]
        weakest = min(CERTAINTY_RANK[c.certainty] for c in known)
        if CERTAINTY_RANK[sc.certainty] > weakest:
            f.append(IntegrityFinding(code="INT-LEDGER-003", severity="error", message=f"certainty inflated: synthesis says {sc.certainty!r} but the weakest source is rank {weakest} ({[c.certainty for c in known]})", claim_ids=[sc.claim_id] + known_ids))
        have = {(r.document_id, r.locator): r for r in sc.evidence_refs}
        lost = [c.claim_id for c in material_sources if any((r.document_id, r.locator) not in have for r in c.source_refs)]
        if lost:
            f.append(IntegrityFinding(code="INT-LEDGER-004", severity="error", message=f"evidence references of material source claims {lost} were not preserved in the '{sc.transformation}' claim", claim_ids=[sc.claim_id] + lost, document_ids=sorted({r.document_id for c in material_sources if c.claim_id in lost for r in c.source_refs})))
        altered = sorted({c.claim_id for c in known for r in c.source_refs if (r.document_id, r.locator) in have and r.excerpt and have[(r.document_id, r.locator)].excerpt and _norm(r.excerpt) != _norm(have[(r.document_id, r.locator)].excerpt)})
        if altered:
            f.append(IntegrityFinding(code="INT-LEDGER-020", severity="warning", message=f"evidence excerpt differs from the source's under the same (document, locator) for source claims {altered}", claim_ids=[sc.claim_id] + altered, document_ids=sorted({r.document_id for c in known if c.claim_id in altered for r in c.source_refs})))
        if sc.transformation == "carried":
            if len(known) != 1 or len(sc.source_claim_ids) != 1:
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message=f"claim marked 'carried' cites {len(sc.source_claim_ids)} sources; 'carried' requires exactly one source with identical text, use 'merged'", claim_ids=[sc.claim_id] + known_ids))
            elif _norm(known[0].claim_text) != _norm(sc.text):
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message="claim marked 'carried' but its text differs from the source; record it as 'paraphrased' or a new linked claim", claim_ids=[sc.claim_id, known[0].claim_id]))
        if material_sources and sc.materiality == "supporting":
            f.append(IntegrityFinding(code="INT-LEDGER-021", severity="warning", message=f"material source claims {[c.claim_id for c in material_sources]} became a 'supporting' synthesized claim: materiality downgraded", claim_ids=[sc.claim_id] + [c.claim_id for c in material_sources]))
        if material_sources and sc.transformation in ("merged", "generalized", "narrowed"):
            what = "content removed; formal coverage check required" if sc.transformation == "narrowed" else "formal synthesis-entailment check required"
            f.append(IntegrityFinding(code="INT-LEDGER-011", severity="info", message=f"material content produced by '{sc.transformation}' from {[c.claim_id for c in material_sources]}: {what}", claim_ids=[sc.claim_id] + [c.claim_id for c in material_sources]))

    for entry in synthesis.ledger:
        unknown = [s for s in entry.source_claim_ids if s not in sources and s not in colliding]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"ledger entry cites unknown source claims {unknown}", claim_ids=unknown, agent_ids=[synthesis.combinator_agent_id]))
        entry_ids = [s for s in entry.source_claim_ids if s not in colliding]
        if entry.transformation == "dropped":
            if not meaningful(entry.reason):
                f.append(IntegrityFinding(code="INT-LEDGER-006", severity="error", message=f"source claims dropped without a meaningful recorded reason (reason={entry.reason!r})", claim_ids=list(entry.source_claim_ids), agent_ids=[synthesis.combinator_agent_id]))
            else:
                material = [s for s in entry_ids if s in sources and sources[s].materiality == "material"]
                if material:
                    f.append(IntegrityFinding(code="INT-LEDGER-019", severity="warning", message=f"MATERIAL source claims {material} were dropped from the answer; recorded reason: {entry.reason!r}", claim_ids=material, agent_ids=[synthesis.combinator_agent_id]))
            accounted.update(entry_ids)
            continue
        target = next((s for s in synthesis.claims if s.claim_id == entry.synthesized_claim_id), None) if entry.synthesized_claim_id else None
        if target is None:
            f.append(IntegrityFinding(code="INT-LEDGER-012", severity="error", message=f"ledger entry '{entry.transformation}' for {list(entry.source_claim_ids)} points to synthesized claim {entry.synthesized_claim_id!r}, which does not exist in the synthesis; the sources are NOT accounted for", claim_ids=list(entry.source_claim_ids) + ([entry.synthesized_claim_id] if entry.synthesized_claim_id else []), agent_ids=[synthesis.combinator_agent_id]))
            continue
        not_cited = [s for s in entry.source_claim_ids if s not in target.source_claim_ids]
        if not_cited:
            f.append(IntegrityFinding(code="INT-LEDGER-012", severity="error", message=f"ledger entry '{entry.transformation}' says {not_cited} went into synthesized claim {target.claim_id!r}, but that claim does not cite them; the sources are NOT accounted for", claim_ids=not_cited + [target.claim_id], agent_ids=[synthesis.combinator_agent_id]))
        accounted.update(s for s in entry_ids if s in target.source_claim_ids)

    unaccounted_supporting: dict[str, list[str]] = {}
    for cid, c in sources.items():
        if cid in accounted:
            continue
        if c.materiality == "material":
            f.append(IntegrityFinding(code="INT-LEDGER-002", severity="error", message="material source claim is neither carried, transformed nor recorded as dropped", claim_ids=[cid], report_ids=[report_of[cid]], agent_ids=[c.agent_id]))
        else:
            unaccounted_supporting.setdefault(report_of[cid], []).append(cid)
    for rid, cids in unaccounted_supporting.items():  # one note per report: supporting claims need not be carried, the router is told which were not
        agent = next(r.agent_id for r in reports if r.report_id == rid)
        f.append(IntegrityFinding(code="INT-LEDGER-022", severity="info", message=f"{len(cids)} supporting source claim(s) of report {rid} are neither carried, transformed nor recorded as dropped: {cids[:12]}{'...' if len(cids) > 12 else ''}", claim_ids=cids, report_ids=[rid], agent_ids=[agent]))
    for r in reports:
        for c in r.claims:
            if c.claim_id in colliding:
                f.append(IntegrityFinding(code="INT-LEDGER-002" if c.materiality == "material" else "INT-LEDGER-022", severity="error" if c.materiality == "material" else "info", message=f"{c.materiality} source claim {c.claim_id!r} of report {r.report_id} cannot be accounted for: its id is shared with another report", claim_ids=[c.claim_id], report_ids=[r.report_id], agent_ids=[r.agent_id]))

    for conf in synthesis.conflicts:
        if conf.status == "resolved_with_basis" and not meaningful(conf.basis):
            f.append(IntegrityFinding(code="INT-CONFLICT-003", severity="error", message=f"conflict marked resolved without a meaningful documented basis (basis={conf.basis!r})", claim_ids=list(conf.claim_ids), agent_ids=[synthesis.combinator_agent_id]))
        unknown = [cid for cid in conf.claim_ids if cid not in all_source_ids and cid not in synthesized_ids]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"conflict record {conf.conflict_id} cites unknown claims {unknown}", claim_ids=unknown, agent_ids=[synthesis.combinator_agent_id]))

    f += _text_coverage(synthesis)
    return f


def _text_coverage(synthesis: Synthesis) -> list[IntegrityFinding]:
    """The student reads Synthesis.text, the Overseer reads the claim ledger; the two
    must agree. Each synthesized claim's text must occur in the student-facing text
    (INT-LEDGER-017) and every numeric literal in the text must occur in some claim
    (INT-LEDGER-018; list markers such as '1.' are ignored)."""
    f: list[IntegrityFinding] = []
    body = _norm(synthesis.text)
    absent = [c.claim_id for c in synthesis.claims if _norm(c.text) not in body]
    if absent:
        f.append(IntegrityFinding(code="INT-LEDGER-017", severity="warning", message=f"synthesized claims {absent} do not appear in the student-facing text; the ledger does not describe what the student reads", claim_ids=absent, agent_ids=[synthesis.combinator_agent_id]))
    text_wo_markers = _LIST_MARKER_RE.sub(" ", synthesis.text)
    in_claims = {m.group(0) for c in synthesis.claims for m in _NUMBER_RE.finditer(c.text)}
    stray = sorted({m.group(0) for m in _NUMBER_RE.finditer(text_wo_markers)} - in_claims, key=lambda s: (len(s), s))
    if stray:
        f.append(IntegrityFinding(code="INT-LEDGER-018", severity="warning", message=f"numeric literals {stray} appear in the student-facing text but in no synthesized claim; unledgered content", claim_ids=[synthesis.synthesis_id], agent_ids=[synthesis.combinator_agent_id]))
    return f
