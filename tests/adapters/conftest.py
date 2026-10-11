"""Shared helpers for adapter tests. No network, no model calls."""
from __future__ import annotations

from typing import Optional

from epinoic_logic.adapters.english_specialist import parser
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

DOC_ID = "doc-1"
TEXT = (
    "The lamp stays unlit in the hall. She does not look up; the clock ticks on.\n"
    'Outside, the yard is "a measured dose of grey" and nothing moves.'
)
IDS = dict(request_id="req-a", task_id="task-a", report_id="rep-a")


def supplied(text: str = TEXT, document_id: str = DOC_ID, locator_scheme: str = "none") -> SuppliedText:
    return SuppliedText(document_id=document_id, text=text, locator_scheme=locator_scheme)  # type: ignore[arg-type]


def parse(text: str, texts: Optional[list[SuppliedText]] = None, **overrides) -> SpecialistReport:
    kwargs = dict(IDS, subject="English A: Literature", task_type="analytical_paragraph",
                  supplied_texts=[supplied()] if texts is None else texts)
    kwargs.update(overrides)
    return parser.parse_response(text, **kwargs)


def by_id(report: SpecialistReport, claim_id: str):
    return next(c for c in report.claims if c.claim_id == claim_id)


def by_role(report: SpecialistReport, role: str):
    return [c for c in report.claims if c.claim_role == role]
