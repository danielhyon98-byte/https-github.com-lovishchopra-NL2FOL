"""Branching infrastructure: one branch per subject family, all plugged into the same hub.

A ``SubjectBranch`` bundles what differs by subject: the eligibility profile, the
adapter that turns the specialist's output into claim records, and an
``IntegrityPack`` of subject-specific checks (deterministic findings plus formal
problems the engine decides with no model involved). Everything else, the envelope,
hand-off, ledger, staleness and cross-agent checks, the engine and the signing, is
shared hub integrity and is never re-implemented per branch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, runtime_checkable

from ..ir.schema import Problem
from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from ..translate.subjects import SubjectProfile, resolve_profile


@dataclass(frozen=True)
class FormalCheck:
    """A problem the engine should decide about the report itself (no model involved)."""
    check_id: str
    kind: str
    description: str
    problem: Problem
    expected_if_sound: str = "ENTAILED"


@runtime_checkable
class IntegrityPack(Protocol):
    name: str

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]: ...

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]: ...


@runtime_checkable
class ReportParser(Protocol):
    agent_id: str

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str, task_type: str,
                       supplied_texts: list[SuppliedText] = (), course_level: str = "unknown", agent_version: Optional[str] = None,
                       agent_id: Optional[str] = None) -> SpecialistReport: ...


@dataclass(frozen=True)
class SubjectBranch:
    key: str
    display_name: str
    profile_keys: tuple[str, ...]                      # subject profile keys this branch serves
    parser_factory: Callable[[], ReportParser]
    packs: tuple[IntegrityPack, ...]
    notes: str = ""

    def parser(self) -> ReportParser:
        return self.parser_factory()

    def run_packs(self, report: SpecialistReport, request_text: Optional[str] = None) -> tuple[list[StructuralFinding], list[FormalCheck]]:
        findings: list[StructuralFinding] = []
        formal: list[FormalCheck] = []
        for p in self.packs:
            findings += p.checks(report, request_text)
            formal += p.formal_checks(report)
        return findings, formal


class BranchRegistry:
    """Resolves a subject label to its branch; falls back to the generic branch."""

    def __init__(self, branches: list[SubjectBranch], default_key: str = "generic") -> None:
        self._by_key = {b.key: b for b in branches}
        self._by_profile: dict[str, SubjectBranch] = {}
        for b in branches:
            for pk in b.profile_keys:
                self._by_profile[pk] = b
        self.default_key = default_key

    def for_subject(self, subject: Optional[str]) -> tuple[SubjectBranch, SubjectProfile]:
        profile = resolve_profile(subject)
        branch = self._by_profile.get(profile.key) or self._by_key[self.default_key]
        return branch, profile

    def keys(self) -> list[str]:
        return sorted(self._by_key)

    def get(self, key: str) -> SubjectBranch:
        return self._by_key[key]
