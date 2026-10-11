"""Generic adapter for specialists that already emit structured reports.

This is the integration contract for every new IB specialist agent: emit a JSON
document that matches :class:`~epinoic_logic.translate.contracts.SpecialistReport`
(or wrap it as ``{"report": {...}}``) and this adapter turns it into an immutable
report and runs subject-neutral structural checks. No prose parsing happens here;
subject-specific heuristics belong in dedicated adapters such as
``english_specialist``.

Parsing rules
-------------
* The caller's identifiers (``request_id``, ``task_id``, ``report_id``) are
  authoritative. When the document carries them they must agree, otherwise
  :class:`~epinoic_logic.adapters.base.AdapterError` is raised: a report can never
  be re-labelled onto another request.
* Fields the document omits (``agent_id``, ``subject``, ``task_type``,
  ``course_level``, ``agent_version``, ``created_at``) are filled from the caller.
  Claims missing their report-level identifiers inherit them from the report.
* The caller's ``supplied_texts`` are the platform's ground truth and always win.
  When the document also carries ``supplied_texts`` they must be the same documents
  (same ids, same text hashes) or the report is rejected: an agent can never ship
  its own "source" for its quotations to be checked against. Only when the caller
  supplies no texts are the document's accepted, and the report then records in
  ``unresolved_issues`` that the texts came from the agent, not the platform.
* A claim that names another ``task_id`` or ``agent_id`` than the report's is
  rejected: a claim cannot be smuggled into a report from another task or agent.
* ``created_at``, when present, must be an RFC 3339 timestamp.
* ``response_sha256`` is computed when absent and must match when present; the
  report contract enforces immutability either way.

Structural checks (codes are stable; add, never rename)
-------------------------------------------------------
* ``GEN-SRC-001`` (error): a claim cites an excerpt that is not found verbatim or
  after typographic normalization in the supplied text it names, or names a
  document that was not supplied (with or without an excerpt), or nothing was
  supplied to check against.
* ``GEN-SRC-002`` (warning): a quotation found only by joining separate spans of
  the text without marking the omission.
* ``GEN-SRC-003`` (warning): a quotation whose words occur but whose form differs
  (initial capital, verse line-break mark); not an invented quotation.
* ``GEN-SRC-004`` (info): an elided quotation; the detail states the span covered.
* ``GEN-SRC-005`` (warning): a locator cited on a document that declares no locator
  scheme, so the location cannot be checked.
* ``GEN-STR-001`` (error): a claim lists a ``supporting_claim_id`` or
  ``parent_claim_id`` that is not a claim of the report.
* ``GEN-STR-002`` (error): a claim supports itself, or claims form a support cycle.
* ``GEN-DUP-001`` (info): two claims have the same text after whitespace and case
  normalization.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import ValidationError

from ..translate.common import truncate, utc_now_rfc3339
from ..translate.contracts import ClaimRecord, SpecialistReport, StructuralFinding, SuppliedText, sha256_text
from .base import AdapterError, register
from .sources import check_excerpt

__all__ = [
    "GenericStructuredAdapter", "ADAPTER", "AGENT_ID", "RFC3339_RE",
    "generic_source_findings", "generic_link_findings", "generic_cycle_findings", "generic_duplicate_findings",
]

AGENT_ID = "generic-structured"
_IDENTITY_FIELDS = ("request_id", "task_id", "report_id")
_REPORT_FILL_FIELDS = ("agent_id", "subject", "task_type", "course_level", "agent_version")
_CLAIM_INHERITED_FIELDS = ("request_id", "task_id", "report_id", "agent_id", "agent_version", "subject", "course_level", "task_type")
_MAX_JSON_BYTES = 2_000_000
_EXCERPT_CHARS = 80
_WS_RE = re.compile(r"\s+")
#: RFC 3339 date-time with ``Z`` or an explicit offset (what ``created_at`` must look like).
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_AGENT_TEXTS_NOTE = "supplied_texts were provided by the agent, not by the platform; quotations were checked against the agent's own texts"


def _normalized_text(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().casefold()


def _load_document(text: str) -> dict[str, Any]:
    if len(text.encode("utf-8", errors="replace")) > _MAX_JSON_BYTES:
        raise AdapterError("structured report exceeds the size limit")
    try:
        document = json.loads(text)
    except (ValueError, RecursionError):
        raise AdapterError("structured report is not valid JSON") from None
    if isinstance(document, dict) and set(document) == {"report"}:
        document = document["report"]
    if not isinstance(document, dict):
        raise AdapterError("structured report must be a JSON object (optionally wrapped as {'report': ...})")
    return dict(document)


class GenericStructuredAdapter:
    """Adapter for reports that are already structured JSON (see module docstring)."""

    agent_id: str = AGENT_ID

    def parse_response(
        self,
        text: str,
        *,
        request_id: str,
        task_id: str,
        report_id: str,
        subject: str,
        task_type: str,
        supplied_texts: list[SuppliedText],
        course_level: str = "unknown",
        agent_version: Optional[str] = None,
    ) -> SpecialistReport:
        """Validate a structured JSON report, filling omitted fields from the caller.

        Raises :class:`AdapterError` on malformed JSON, identity mismatch, a wrong
        ``response_sha256`` or any contract violation. Error messages never include
        the report text.
        """
        document = _load_document(text)
        caller = dict(request_id=request_id, task_id=task_id, report_id=report_id)
        for field in _IDENTITY_FIELDS:
            present = document.get(field)
            if present is None:
                document[field] = caller[field]
            elif present != caller[field]:
                raise AdapterError(f"report {field} does not match the caller's {field}")
        fill = dict(agent_id=self.agent_id, subject=subject, task_type=task_type, course_level=course_level, agent_version=agent_version)
        for field in _REPORT_FILL_FIELDS:
            if document.get(field) is None and fill[field] is not None:
                document[field] = fill[field]
        agent_texts = document.get("supplied_texts")
        if supplied_texts:
            if agent_texts:
                if not _same_texts(agent_texts, supplied_texts):
                    raise AdapterError("report supplied_texts do not match the caller's supplied texts; the platform's texts are authoritative")
            document["supplied_texts"] = [t.model_dump(mode="json") for t in supplied_texts]
        elif agent_texts:
            issues = document.get("unresolved_issues")
            if issues is None:
                issues = []
            if isinstance(issues, list):
                document["unresolved_issues"] = [*issues, _AGENT_TEXTS_NOTE]
        else:
            document["supplied_texts"] = []
        if document.get("created_at") is None:
            document["created_at"] = utc_now_rfc3339()
        elif not isinstance(document["created_at"], str) or not RFC3339_RE.match(document["created_at"]):
            raise AdapterError("created_at is not an RFC 3339 timestamp")
        original = document.get("original_response")
        if not isinstance(original, str) or not original:
            raise AdapterError("structured report must carry a non-empty original_response string")
        digest = sha256_text(original)
        if document.get("response_sha256") is None:
            document["response_sha256"] = digest
        elif document["response_sha256"] != digest:
            raise AdapterError("response_sha256 does not match original_response; reports are immutable")
        claims = document.get("claims")
        if claims is None:
            document["claims"] = []
        elif isinstance(claims, list):
            document["claims"] = [self._inherit(c, document) for c in claims]
            for c in document["claims"]:
                if isinstance(c, dict):
                    for field in ("task_id", "agent_id"):
                        if c.get(field) is not None and c.get(field) != document.get(field):
                            raise AdapterError(f"claim {field} does not match the report's {field}; a claim cannot belong to another task or agent")
        try:
            return SpecialistReport.model_validate(document)
        except ValidationError as exc:
            locations = sorted({".".join(str(p) for p in e.get("loc", ())) or "<root>" for e in exc.errors()[:8]})
            raise AdapterError("structured report violates the SpecialistReport contract at: " + ", ".join(locations)) from None

    @staticmethod
    def _inherit(claim: Any, document: dict[str, Any]) -> Any:
        if not isinstance(claim, dict):
            return claim
        filled = dict(claim)
        for field in _CLAIM_INHERITED_FIELDS:
            if filled.get(field) is None and document.get(field) is not None:
                filled[field] = document[field]
        return filled

    def structural_checks(self, report: SpecialistReport) -> list[StructuralFinding]:
        """Subject-neutral checks: source excerpts, claim links, support cycles, duplicate claims."""
        findings: list[StructuralFinding] = []
        findings += generic_source_findings(report)
        findings += generic_link_findings(report)
        findings += generic_cycle_findings(report)
        findings += generic_duplicate_findings(report)
        return findings


def _same_texts(agent_texts: Any, caller_texts: list[SuppliedText]) -> bool:
    """True when the agent's ``supplied_texts`` name the same documents with the same text."""
    if not isinstance(agent_texts, list):
        return False
    expected = {t.document_id: sha256_text(t.text) for t in caller_texts}
    seen: dict[str, str] = {}
    for item in agent_texts:
        if not isinstance(item, dict) or not isinstance(item.get("document_id"), str) or not isinstance(item.get("text"), str):
            return False
        seen[item["document_id"]] = sha256_text(item["text"])
    return seen == expected


# ------------------------------------------------------------------ checks


def generic_source_findings(
    report: SpecialistReport,
    *,
    code: str = "GEN-SRC-001",
    joined_code: str = "GEN-SRC-002",
    inexact_code: str = "GEN-SRC-003",
    elided_code: str = "GEN-SRC-004",
    locator_code: str = "GEN-SRC-005",
) -> list[StructuralFinding]:
    """Source-integrity findings for every ``source_ref`` of every claim.

    ``code`` (error) when an excerpt is not found or a document was not supplied;
    ``joined_code`` (warning) for a quotation joined from separate spans;
    ``inexact_code`` (warning) when the words occur but the form differs;
    ``elided_code`` (info) for an elided quotation; ``locator_code`` (warning) for a
    locator on a document that declares no locator scheme.
    """
    docs = {t.document_id: t for t in report.supplied_texts}
    findings: list[StructuralFinding] = []
    for claim in report.claims:
        for ref in claim.source_refs:
            who = f"claim {claim.claim_id} ({claim.claim_role})"
            if not ref.excerpt or not ref.excerpt.strip():
                if docs and ref.document_id not in docs:
                    findings.append(StructuralFinding(
                        code=code, severity="error",
                        message=f"{who} cites document {ref.document_id}, which was not supplied",
                        claim_ids=[claim.claim_id],
                    ))
                elif ref.locator and ref.document_id in docs and docs[ref.document_id].locator_scheme == "none":
                    findings.append(StructuralFinding(
                        code=locator_code, severity="warning",
                        message=f"{who} cites locator '{truncate(ref.locator, 40)}' in {ref.document_id}, which declares no locator scheme; the location cannot be checked",
                        claim_ids=[claim.claim_id],
                    ))
                continue
            check = check_excerpt(ref.excerpt, ref.document_id, docs)
            if check.status == "found":
                continue
            shown = truncate(check.excerpt_checked or ref.excerpt, _EXCERPT_CHARS)
            prefix = f"quotation '{shown}' cited by {who} in {ref.document_id or 'no document'}: {check.detail}"
            if check.status == "found_joined":
                findings.append(StructuralFinding(code=joined_code, severity="warning", message=prefix, claim_ids=[claim.claim_id]))
            elif check.status == "found_inexact":
                findings.append(StructuralFinding(code=inexact_code, severity="warning", message=prefix, claim_ids=[claim.claim_id]))
            elif check.status == "found_elided":
                findings.append(StructuralFinding(code=elided_code, severity="info", message=prefix, claim_ids=[claim.claim_id]))
            else:
                findings.append(StructuralFinding(code=code, severity="error", message=prefix, claim_ids=[claim.claim_id]))
    return findings


def generic_link_findings(report: SpecialistReport, *, code: str = "GEN-STR-001") -> list[StructuralFinding]:
    """``code`` (error) for supporting or parent claim ids that are not in the report."""
    known = {c.claim_id for c in report.claims}
    findings: list[StructuralFinding] = []
    for claim in report.claims:
        unknown = sorted({cid for cid in claim.supporting_claim_ids if cid not in known})
        if claim.parent_claim_id is not None and claim.parent_claim_id not in known:
            unknown = sorted(set(unknown) | {claim.parent_claim_id})
        if unknown:
            findings.append(StructuralFinding(
                code=code, severity="error",
                message=f"claim {claim.claim_id} references claim id(s) not in the report: {', '.join(unknown)}",
                claim_ids=[claim.claim_id],
            ))
    return findings


def generic_cycle_findings(report: SpecialistReport, *, code: str = "GEN-STR-002") -> list[StructuralFinding]:
    """``code`` (error) when a claim supports itself (or is its own parent) or when claims
    form a cycle through ``supporting_claim_ids``.

    Only support edges take part in cycle detection: ``parent_claim_id`` points the
    other way (child to parent) and would make every legitimate point/evidence pair
    look circular.
    """
    known = {c.claim_id: c for c in report.claims}
    findings: list[StructuralFinding] = []
    for claim in report.claims:
        if claim.claim_id in claim.supporting_claim_ids or claim.parent_claim_id == claim.claim_id:
            findings.append(StructuralFinding(
                code=code, severity="error",
                message=f"claim {claim.claim_id} supports itself; a claim is never evidence for itself",
                claim_ids=[claim.claim_id],
            ))
    # Iterative DFS with colours over support edges; each cycle is reported once.
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {cid: WHITE for cid in known}
    reported: set[frozenset[str]] = set()
    for root in known:
        if colour[root] != WHITE:
            continue
        stack: list[tuple[str, list[str]]] = [(root, [s for s in known[root].supporting_claim_ids if s in known and s != root])]
        path: list[str] = [root]
        colour[root] = GREY
        while stack:
            node, pending = stack[-1]
            if pending:
                nxt = pending.pop()
                if colour[nxt] == WHITE:
                    colour[nxt] = GREY
                    path.append(nxt)
                    stack.append((nxt, [s for s in known[nxt].supporting_claim_ids if s in known and s != nxt]))
                elif colour[nxt] == GREY:
                    members = frozenset(path[path.index(nxt):])
                    if members not in reported:
                        reported.add(members)
                        ids = sorted(members)
                        findings.append(StructuralFinding(
                            code=code, severity="error",
                            message=f"claims {', '.join(ids)} form a support cycle; none of them can be evidence for the others",
                            claim_ids=ids,
                        ))
            else:
                colour[node] = BLACK
                stack.pop()
                path.pop()
    return findings


def generic_duplicate_findings(report: SpecialistReport, *, code: str = "GEN-DUP-001") -> list[StructuralFinding]:
    """``code`` (info) for groups of claims whose text is the same after normalization."""
    groups: dict[str, list[ClaimRecord]] = {}
    for claim in report.claims:
        groups.setdefault(_normalized_text(claim.claim_text), []).append(claim)
    findings: list[StructuralFinding] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        ids = [c.claim_id for c in members]
        findings.append(StructuralFinding(
            code=code, severity="info",
            message=f"{len(ids)} claims share the same text after normalization: {', '.join(ids)}",
            claim_ids=ids,
        ))
    return findings


#: The registered singleton (``agent_id`` ``generic-structured``).
ADAPTER = register(GenericStructuredAdapter())
