"""Branching infrastructure: one branch per subject family, all plugged into the same hub.

A ``SubjectBranch`` bundles what differs by subject: the eligibility profile, the
adapter that turns the specialist's output into claim records, and an
``IntegrityPack`` of subject-specific checks (deterministic findings plus formal
problems the engine decides with no model involved). Everything else, the envelope,
hand-off, ledger, staleness and cross-agent checks, the engine and the signing, is
shared hub integrity and is never re-implemented per branch.

Additions for the STEM branches (docs/STEM_DESIGN.md, sections 8.1 and 11.1), all with
defaults that keep every existing pack and branch unchanged:

* ``FormalCheck`` carries ``claim_ids`` (the claims its relation rests on; the channel puts
  them on INT-SUBJ findings), ``policy`` (a named engine policy, ``linear`` or ``nonlinear``;
  never raw ``Limits``), ``failure_severity`` (``error``: INT-SUBJ-001, ``warning``:
  INT-SUBJ-004 for a check that relied on a reading the report did not state) and
  ``inconsistent_is_failure`` (False: INCONSISTENT_PREMISES is undecided, not a failure).
* ``SubjectBranch.hub_hooks`` (:class:`BranchHooks`): optional request and coverage readings
  the channel applies for the branch (none for the non-STEM branches).
* ``SubjectBranch.run_packs`` guards every pack call: a pack that raises yields the hub's
  PACK-INTERNAL-001 error and a BR-INTERNAL-001 warning naming it, and the other packs still
  run. It prefers a pack's
  ``formal_checks_for(report, request_text)`` when the pack defines one (the request's
  bindings and show-that targets matter to STEM checks); ``formal_checks(report)`` otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Protocol, runtime_checkable

from ..ir.schema import Problem
from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from ..translate.subjects import SubjectProfile, resolve_profile


@dataclass(frozen=True)
class FormalCheck:
    """A problem the engine should decide about the report itself (no model involved).

    ``claim_ids`` names the delivered claims whose text holds the statement the check was built
    from (the claims the checked relation rests on), so a finding about the check (INT-SUBJ-001 /
    INT-SUBJ-002 / INT-SUBJ-004) can name the claim the router holds; the description names them
    too. ``policy``: the named engine policy the channel verifies it under (``engine.policies``).
    ``failure_severity``: the severity of a definitive failure (``error`` is INT-SUBJ-001,
    ``warning`` INT-SUBJ-004). ``inconsistent_is_failure``: whether INCONSISTENT_PREMISES counts
    as a failure (True for every pre-STEM check) or as undecided (STEM checks, design D13)."""
    check_id: str
    kind: str
    description: str
    problem: Problem
    expected_if_sound: str = "ENTAILED"
    claim_ids: tuple[str, ...] = ()
    policy: str = "linear"
    failure_severity: Literal["error", "warning"] = "error"
    inconsistent_is_failure: bool = True


@runtime_checkable
class IntegrityPack(Protocol):
    name: str

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]: ...

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]: ...


@runtime_checkable
class BranchHooks(Protocol):
    """Readings a branch lends the channel (STEM: ``stem.hub_hooks.STEM_HOOKS``). Every method takes
    and returns plain data; ``profile_key`` is the subject profile the channel resolved for the agent.

    * ``request_imperatives``: extra imperative verbs that make a request sentence an item;
    * ``coverage_terms``: extra words a claim offers the item-coverage heuristic;
    * ``echo_exempt``: True when the answer is evidently not a restatement of the request;
    * ``word_count_view``: the text a word bound is measured on."""
    request_imperatives: tuple[str, ...]

    def coverage_terms(self, claim_text: str, report_text: str, request_text: Optional[str], profile_key: str) -> frozenset[str]: ...

    def echo_exempt(self, report_text: str, request_text: str, profile_key: str) -> bool: ...

    def word_count_view(self, text: str, profile_key: str) -> str: ...


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
    hub_hooks: Optional[BranchHooks] = None

    def parser(self) -> ReportParser:
        return self.parser_factory()

    def run_packs(self, report: SpecialistReport, request_text: Optional[str] = None) -> tuple[list[StructuralFinding], list[FormalCheck]]:
        """Every pack's findings and formal checks. Each pack, and each of its two calls, runs on its own: a pack that fails internally
        adds ``PACK-INTERNAL-001`` (error) naming the pack and the call, together with the branch infrastructure's
        ``BR-INTERNAL-001`` (warning: the pack, the exception type and the stage, never the exception's text), and the other packs'
        findings and formal checks still reach the receipt, so one failing check never discards the rest and the router never
        reads the missing findings as a pass. A pack's ``formal_checks_for(report, request_text)`` is preferred when the pack
        defines one (the request's bindings and show-that targets matter to STEM checks); ``formal_checks(report)`` otherwise."""
        findings: list[StructuralFinding] = []
        formal: list[FormalCheck] = []
        for p in self.packs:
            for_request = getattr(p, "formal_checks_for", None)
            formal_call = (lambda p=p, f=for_request: f(report, request_text)) if callable(for_request) else (lambda p=p: p.formal_checks(report))
            for what, call in (("checks", lambda p=p: p.checks(report, request_text)), ("formal checks", formal_call)):
                try:
                    out = list(call())
                except Exception as exc:  # noqa: BLE001 - reported on the receipt, never silent
                    findings.append(StructuralFinding(
                        code="PACK-INTERNAL-001", severity="error",
                        message=f"the {getattr(p, 'name', type(p).__name__)} integrity pack's {what} failed internally ({type(exc).__name__}); its {what} are missing "
                                f"from this receipt and the router must not treat them as passed; the other packs ran",
                        rule_source="hub integrity (a failing pack is reported, never silently skipped)"))
                    findings.append(_pack_failure(p, exc, what))
                    continue
                if what == "checks":
                    findings += out
                else:
                    formal += out
        return findings, formal


def _pack_failure(pack: object, exc: BaseException, stage: str) -> StructuralFinding:
    name = str(getattr(pack, "name", type(pack).__name__))[:80]
    return StructuralFinding(code="BR-INTERNAL-001", severity="warning",
                             message=(f"pack {name!r} failed internally ({type(exc).__name__}) during {stage}; its findings are missing from this "
                                      "receipt, and the router must not treat the pack as passed"),
                             rule_source="branch infrastructure: a pack failure is named, never silent")


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
