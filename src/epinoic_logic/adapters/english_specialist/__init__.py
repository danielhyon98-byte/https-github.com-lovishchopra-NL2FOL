"""English specialist adapter: the worked example of a specialist-to-report adapter.

* :mod:`parser` proposes claims from PETAL-style analytical prose.
* :mod:`structural` runs the deterministic checks derived from the specialist's
  own knowledge documents (working rules, not official IB rules).
* :mod:`fixtures` holds Example 1 texts and IR fixtures for the fixture provider.

The adapter instance is registered under ``agent_id`` ``english-specialist`` when
this module is imported.
"""
from __future__ import annotations

from typing import Optional

from ...translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from ..base import register
from . import parser, structural
from .parser import AGENT_ID, DEFAULT_SUBJECT

__all__ = ["EnglishSpecialistAdapter", "ADAPTER", "AGENT_ID", "DEFAULT_SUBJECT", "parser", "structural"]


class EnglishSpecialistAdapter:
    """Adapter for the English specialist agent (see package docstring)."""

    agent_id: str = AGENT_ID

    def parse_response(
        self,
        text: str,
        *,
        request_id: str,
        task_id: str,
        report_id: str,
        subject: str = DEFAULT_SUBJECT,
        task_type: str,
        supplied_texts: list[SuppliedText],
        course_level: str = "unknown",
        agent_version: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> SpecialistReport:
        """Parse an analytical answer into a report (see :func:`parser.parse_response`).

        ``agent_id`` is the sender identity the hub states; it is carried into the report
        unchanged so the channel's identity checks compare who answered with who was asked."""
        return parser.parse_response(
            text, request_id=request_id, task_id=task_id, report_id=report_id, subject=subject or DEFAULT_SUBJECT,
            task_type=task_type, supplied_texts=supplied_texts, course_level=course_level, agent_version=agent_version,
            agent_id=agent_id,
        )

    def structural_checks(self, report: SpecialistReport) -> list[StructuralFinding]:
        """Deterministic findings (see :func:`structural.structural_checks`)."""
        return structural.structural_checks(report)


ADAPTER = register(EnglishSpecialistAdapter())
