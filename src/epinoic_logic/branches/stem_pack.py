"""``StemPack(mode)``: the STEM integrity pack (docs/STEM_DESIGN.md, sections 8 and 11).

One pack serves the three STEM branches; ``mode`` is ``sciences``, ``mathematics`` or
``computer_science`` and sets the fallback reading profile when a report's subject names no
STEM profile (chemical equations, the molar ``M`` and the tonne follow the subject's own
profile through ``stem.limits``). For each report the pack reads the shared
:class:`~epinoic_logic.stem.document.StemDocument` (the one the STEM parser read: same text,
request and profile) and the checks stage's :func:`~epinoic_logic.stem.checks.build_checks`:

* :meth:`StemPack.checks` returns the front end's and the checks stage's ST findings as
  ``StructuralFinding`` (codes and severities of section 8.2; the pack emits no error-severity
  finding: every STEM error is an engine result), each naming the claims of its statements;
* :meth:`StemPack.formal_checks_for` (``SubjectBranch.run_packs`` prefers it) returns one
  ``FormalCheck`` per planned check: the IR 1.0 problem (validated with
  ``Problem.model_validate``), the expected status, the claim ids (and, for a substitution, the
  claims stating the values it is checked against: ``related_claim_ids``), the named policy
  (``linear``/``nonlinear``), the failure severity and ``inconsistent_is_failure=False``;
  :meth:`StemPack.formal_checks` is the relay form (no request: ``stem-giv`` and ``stem-tgt``
  are not built and checks bind only to the answer's own values).

Statement ids map to the report's claims: a claim whose id is the statement id, or the statement
id with a STEM branch's letter (raw text through ``StemTextParser``: ``s1.2``, ``m1.2``,
``c1.2``), else the claims whose text is an offset substring overlapping the statement, else
the claims that mention the statement's text (the shared two-way substring rule). Descriptions
and messages name the report's own claim ids: the ``[claims s1.2]`` of a description and the
statement ids of a front-end message are rewritten to the claims they map to. An internal failure of the pack is ST-INTERNAL-001 (warning), never an exception and
never a silent pass. When the failure leaves the report with no STEM checks at all (the pack raised, or the front end
failed internally and returned an empty document), the hub's PACK-INTERNAL-001 (error, as ``SubjectBranch.run_packs``
raises it for a pack that raises) stands beside it, so an emptied STEM document can never read as a pass: the receipt
carries an error. That is the pack's one error-severity finding; every STEM error about the answer is an engine result.
The scope statement of every check is in its problem's ``notes``.
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Optional

from ..adapters.stem_specialist.parser import ID_PREFIXES, MODE_PROFILES, stem_profile_key
from ..ir.schema import Problem
from ..named import DEFECT_LABELS, code_spec
from ..stem.checks import CheckPlan, build_checks
from ..stem.document import StemDocument, build_document
from ..translate.contracts import SpecialistReport, StructuralFinding
from .base import FormalCheck

__all__ = ["StemPack", "STEM_RULE_SOURCE"]

STEM_RULE_SOURCE = "STEM front end and checks (docs/STEM_DESIGN.md, section 8.2)"
_MAX_MESSAGE = 2000
_MAX_CLAIMS_NAMED = 8
_CACHE_ENTRIES = 32
#: a statement id inside a message or a description ('s1.2', 's.tail')
_SID_RE = re.compile(r"(?<![\w.])s(?:\d+\.\d+|\.tail)(?![\w.])")


class StemPack:
    """The STEM pack of one branch mode (module docstring)."""

    def __init__(self, mode: str = "sciences") -> None:
        if mode not in MODE_PROFILES:
            raise ValueError(f"unknown STEM pack mode {mode!r}; expected one of {sorted(MODE_PROFILES)}")
        self.mode = mode
        self.name = f"stem-{mode}"
        self._cache: "OrderedDict[tuple, tuple[list[StructuralFinding], list[FormalCheck]]]" = OrderedDict()
        self._lock = threading.Lock()  # the registry's packs are shared by every hub and channel

    # ---------------------------------------------------------------------------------- pack protocol

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        return list(self._evaluate(report, request_text)[0])

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """The relay form: no request, so no Given or show-that check, and bindings from the answer only."""
        return list(self._evaluate(report, None)[1])

    def formal_checks_for(self, report: SpecialistReport, request_text: Optional[str]) -> list[FormalCheck]:
        return list(self._evaluate(report, request_text)[1])

    # ------------------------------------------------------------------------------------- internals

    def document(self, report: SpecialistReport, request_text: Optional[str] = None) -> StemDocument:
        """The shared document of this report (memoised by the front end)."""
        data = tuple(t.text for t in report.supplied_texts if t.text and t.text.strip())  # the request's data: tables (rule table-data), values (supplied-values)
        return build_document(report.original_response, request_text, stem_profile_key(report.subject, self.mode), **({"data": data} if data else {}))

    def _evaluate(self, report: SpecialistReport, request_text: Optional[str]) -> tuple[list[StructuralFinding], list[FormalCheck]]:
        key = (report.report_id, report.request_id, report.response_sha256, report.subject, request_text,
               tuple((c.claim_id, c.claim_text) for c in report.claims))
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        try:
            out = self._build(report, request_text)
        except Exception as exc:  # the pack never raises on agent text; a failure is named, never a pass
            out = ([StructuralFinding(code="ST-INTERNAL-001", severity="warning",
                                      message=(f"the STEM pack failed internally ({type(exc).__name__}) while reading this report; its STEM checks are "
                                               "missing from this receipt and must not be read as passed"),
                                      claim_ids=[], rule_source=STEM_RULE_SOURCE),
                    self._missing_checks(f"the pack failed internally ({type(exc).__name__}) while reading this report")], [])
        with self._lock:
            self._cache[key] = out
            while len(self._cache) > _CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return out

    def _missing_checks(self, why: str) -> StructuralFinding:
        """The hub's PACK-INTERNAL-001 (error) for a report whose STEM checks are all missing (module docstring)."""
        return StructuralFinding(code="PACK-INTERNAL-001", severity="error",
                                 message=(f"the {self.name} integrity pack's checks are missing from this receipt: {why}; the router must not "
                                          "treat them as passed (no STEM check of this report was built or run)")[:_MAX_MESSAGE],
                                 claim_ids=[], rule_source="hub integrity (a failing pack is reported, never silently skipped)")

    def _plan(self, doc: StemDocument, report: SpecialistReport, relay: bool) -> CheckPlan:
        return build_checks(doc, report_id=report.report_id, request_id=report.request_id, relay=relay)

    def _build(self, report: SpecialistReport, request_text: Optional[str]) -> tuple[list[StructuralFinding], list[FormalCheck]]:
        doc = self.document(report, request_text)
        plan = self._plan(doc, report, relay=request_text is None)
        claim_map = _ClaimMap(report, doc)
        findings: list[StructuralFinding] = []
        for f in doc.findings:
            findings.append(_finding(f.code, f.severity, claim_map.relabel(f.message), claim_map.ids(f.statement_ids)))
        if not doc.statements and any(f.code == "ST-INTERNAL-001" for f in doc.findings):
            # the front end failed internally and returned an empty document: every STEM check of the report is missing
            findings.append(self._missing_checks("the STEM front end failed internally and read no statement of the answer"))
        for f in plan.findings:
            findings.append(_finding(f.code, f.severity, claim_map.relabel(f.message), claim_map.ids(f.statement_ids)))
        formal: list[FormalCheck] = []
        for pc in plan.checks:
            try:
                problem = Problem.model_validate(pc.problem)
            except Exception as exc:  # a built problem the IR refuses: named, never run, never a pass
                findings.append(_finding("ST-INTERNAL-001", "warning",
                                         f"{pc.check_id}: the STEM pack built a problem the IR refuses ({type(exc).__name__}); the check was not run",
                                         claim_map.ids(pc.claim_ids)))
                continue
            claim_ids = claim_map.ids(pc.claim_ids, limit=None)
            related = tuple(c for c in claim_map.ids(pc.related_ids) if c not in claim_ids)
            formal.append(FormalCheck(check_id=pc.check_id, kind=pc.kind, description=claim_map.relabel(pc.description), problem=problem,
                                      expected_if_sound=pc.expected_if_sound, claim_ids=tuple(claim_ids), policy=pc.policy,
                                      failure_severity="warning" if pc.failure_severity == "warning" else "error",
                                      inconsistent_is_failure=pc.inconsistent_is_failure, related_claim_ids=related,
                                      # the defect a failure names, when the STEM check carries a canonical label
                                      defect=getattr(pc, "defect", None) if getattr(pc, "defect", None) in DEFECT_LABELS else None))
        return findings, formal


def _finding(code: str, severity: str, message: str, claim_ids: list[str]) -> StructuralFinding:
    sev = severity if severity in ("warning", "info") else "warning"  # the STEM pack itself never emits an error
    spec = code_spec(code)  # a STEM code of the named-code table (named.NAMED_CODES) carries its canonical defect label
    defect = spec.defect if spec is not None and spec.defect in DEFECT_LABELS else None
    return StructuralFinding(code=code, severity=sev, message=message[:_MAX_MESSAGE], claim_ids=claim_ids, rule_source=STEM_RULE_SOURCE, defect=defect)


class _ClaimMap:
    """Statement ids of the document -> claim ids of the report (module docstring)."""

    def __init__(self, report: SpecialistReport, doc: StemDocument) -> None:
        self.report = report
        self.doc = doc
        self.by_id = {c.claim_id for c in report.claims}
        self._memo: dict[str, list[str]] = {}
        text = report.original_response
        self._spans: list[tuple[str, int, int]] = []
        cursor = 0
        for c in report.claims:
            k = text.find(c.claim_text, cursor) if c.claim_text else -1
            if k < 0 and c.claim_text:
                k = text.find(c.claim_text)
            if k >= 0:
                self._spans.append((c.claim_id, k, k + len(c.claim_text)))
                cursor = k

    def statement(self, sid: str) -> list[str]:
        if sid in self._memo:
            return self._memo[sid]
        out: list[str] = []
        same = [v for v in [sid] + [p + sid[1:] for p in ID_PREFIXES.values() if sid.startswith("s")] if v in self.by_id]
        if same:
            out = [same[0]]
        else:
            st = self.doc.statement(sid)
            if st is not None:
                out = [cid for cid, a, b in self._spans if a < st.end and st.start < b]
                if not out:
                    frag = " ".join(self.doc.text[st.start:st.end].split())
                    out = [c.claim_id for c in self.report.claims
                           if frag and (frag in " ".join(c.claim_text.split()) or " ".join(c.claim_text.split()) in frag)]
        self._memo[sid] = out
        return out

    def relabel(self, text: str) -> str:
        """``text`` with every statement id of this document that maps to exactly one other claim id renamed to it."""
        def sub(m: "re.Match[str]") -> str:
            sid = m.group(0)
            if self.doc.statement(sid) is None:
                return sid
            mapped = self.statement(sid)
            return mapped[0] if len(mapped) == 1 else sid
        return _SID_RE.sub(sub, text) if "s" in text else text

    def ids(self, statement_ids, limit: Optional[int] = _MAX_CLAIMS_NAMED) -> list[str]:
        out: list[str] = []
        for sid in statement_ids:
            for cid in self.statement(sid):
                if cid not in out:
                    out.append(cid)
        return out if limit is None else out[:limit]
