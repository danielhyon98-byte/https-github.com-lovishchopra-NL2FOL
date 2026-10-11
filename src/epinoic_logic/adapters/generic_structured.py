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
  ``course_level``, ``agent_version``, ``supplied_texts``, ``created_at``) are
  filled from the caller. Claims missing their report-level identifiers inherit
  them from the report.
* ``response_sha256`` is computed when absent and must match when present; the
  report contract enforces immutability either way.

Structural checks (codes are stable; add, never rename)
-------------------------------------------------------
* ``GEN-SRC-001`` (error): a claim cites an excerpt that is not found verbatim or
  after typographic normalization in the supplied text it names (or names an
  unknown document, or nothing was supplied to check against). A quotation that is
  found only by joining separate spans is reported as ``GEN-SRC-002`` (warning).
* ``GEN-STR-001`` (error): a claim lists a ``supporting_claim_id`` or
  ``parent_claim_id`` that is not a claim of the report.
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

__all__ = ["GenericStructuredAdapter", "ADAPTER", "AGENT_ID", "generic_source_findings", "generic_link_findings", "generic_duplicate_findings"]

AGENT_ID = "generic-structured"
_IDENTITY_FIELDS = ("request_id", "task_id", "report_id")
_REPORT_FILL_FIELDS = ("agent_id", "subject", "task_type", "course_level", "agent_version")
_CLAIM_INHERITED_FIELDS = ("request_id", "task_id", "report_id", "agent_id", "agent_version", "subject", "course_level", "task_type")
_MAX_JSON_BYTES = 2_000_000
_EXCERPT_CHARS = 80
_WS_RE = re.compile(r"\s+")


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
        if not document.get("supplied_texts"):
            document["supplied_texts"] = [t.model_dump(mode="json") for t in supplied_texts]
        if document.get("created_at") is None:
            document["created_at"] = utc_now_rfc3339()
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
        """Subject-neutral checks: source excerpts, claim links, duplicate claims."""
        findings: list[StructuralFinding] = []
        findings += generic_source_findings(report)
        findings += generic_link_findings(report)
        findings += generic_duplicate_findings(report)
        return findings


# ------------------------------------------------------------------ checks


def generic_source_findings(report: SpecialistReport, *, code: str = "GEN-SRC-001", joined_code: str = "GEN-SRC-002") -> list[StructuralFinding]:
    """``code`` (error) for every cited excerpt not found in its document; ``joined_code``
    (warning) for a quotation found only by joining separate spans."""
    docs = {t.document_id: t for t in report.supplied_texts}
    findings: list[StructuralFinding] = []
    for claim in report.claims:
        for ref in claim.source_refs:
            if not ref.excerpt or not ref.excerpt.strip():
                continue
            check = check_excerpt(ref.excerpt, ref.document_id, docs)
            if check.status == "found":
                continue
            shown = truncate(check.excerpt_checked or ref.excerpt, _EXCERPT_CHARS)
            if check.status == "found_joined":
                findings.append(StructuralFinding(
                    code=joined_code, severity="warning",
                    message=f"quotation '{shown}' cited by claim {claim.claim_id} ({claim.claim_role}) in {ref.document_id}: {check.detail}",
                    claim_ids=[claim.claim_id],
                ))
                continue
            findings.append(StructuralFinding(
                code=code, severity="error",
                message=f"quotation '{shown}' cited by claim {claim.claim_id} ({claim.claim_role}) in {ref.document_id or 'no document'}: {check.detail}",
                claim_ids=[claim.claim_id],
            ))
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
