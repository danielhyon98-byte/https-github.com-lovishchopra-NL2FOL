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
  ``Problem.model_validate``), the expected status, the claim ids, the named policy
  (``linear``/``nonlinear``), the failure severity and ``inconsistent_is_failure=False``;
  :meth:`StemPack.formal_checks` is the relay form (no request: ``stem-giv`` and ``stem-tgt``
  are not built and checks bind only to the answer's own values).

Statement ids map to the report's claims by source span and text, never by id spelling alone: the
claims whose text is an offset substring overlapping the statement, else the claims that mention
the statement's text (the shared two-way substring rule). A claim whose id is the statement id,
or the statement id with a STEM branch's letter (raw text through ``StemTextParser``: ``s1.2``,
``m1.2``, ``c1.2``), is the statement's one claim only when its text agrees with the statement
(it overlaps the statement's span, it is the text the parser gives the statement, or it mentions
the statement); a familiar-looking id whose text is another statement's is no evidence, the
statement is mapped by text and the disagreement is ST-CLAIM-001 (warning), so a check of one
statement can never be attributed to another claim because of how its id is spelled.
Descriptions and messages name the report's own claim ids: the ``[claims s1.2]`` of a description
and the statement ids of a front-end message are rewritten to the claims they map to. An internal
failure of the pack is ST-INTERNAL-001 (warning), never an exception and never a silent pass. The
scope statement of every check is in its problem's ``notes``.
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Optional

from ..adapters.stem_specialist.parser import ID_PREFIXES, MODE_PROFILES, statement_claim_text, stem_profile_key
from ..ir.schema import Problem
from ..named import DEFECT_LABELS, code_spec
from ..stem.checks import CheckPlan, build_checks
from ..stem.document import StemDocument, build_document
from ..translate.contracts import SpecialistReport, StructuralFinding
from .base import FormalCheck
from .generic_parser import agent_claim_tag

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
        return build_document(report.original_response, request_text, stem_profile_key(report.subject, self.mode))

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
                                      claim_ids=[], rule_source=STEM_RULE_SOURCE)], [])
        with self._lock:
            self._cache[key] = out
            while len(self._cache) > _CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return out

    def _plan(self, doc: StemDocument, report: SpecialistReport, relay: bool) -> CheckPlan:
        return build_checks(doc, report_id=report.report_id, request_id=report.request_id, relay=relay)

    def _build(self, report: SpecialistReport, request_text: Optional[str]) -> tuple[list[StructuralFinding], list[FormalCheck]]:
        doc = self.document(report, request_text)
        plan = self._plan(doc, report, relay=request_text is None)
        claim_map = _ClaimMap(report, doc)
        findings: list[StructuralFinding] = []
        for f in doc.findings:
            findings.append(_finding(f.code, f.severity, claim_map.relabel(f.message), claim_map.ids(f.statement_ids)))
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
            formal.append(FormalCheck(check_id=pc.check_id, kind=pc.kind, description=claim_map.relabel(pc.description), problem=problem,
                                      expected_if_sound=pc.expected_if_sound, claim_ids=tuple(claim_ids), policy=pc.policy,
                                      failure_severity="warning" if pc.failure_severity == "warning" else "error",
                                      inconsistent_is_failure=pc.inconsistent_is_failure, defect=pc.defect if pc.defect in DEFECT_LABELS else None))
        mismatch = claim_map.mismatch_finding()
        if mismatch is not None:
            findings.append(mismatch)
        return findings, formal


def _finding(code: str, severity: str, message: str, claim_ids: list[str]) -> StructuralFinding:
    sev = severity if severity in ("warning", "info") else "warning"  # the STEM pack itself never emits an error
    spec = code_spec(code)  # a named STEM diagnostic (ST-REF-001, ST-WORK-001, ...) carries its canonical defect label
    defect = spec.defect if spec is not None and spec.defect in DEFECT_LABELS else None
    return StructuralFinding(code=code, severity=sev, message=message[:_MAX_MESSAGE], claim_ids=claim_ids, rule_source=STEM_RULE_SOURCE, defect=defect)


class _ClaimMap:
    """Statement ids of the document -> claim ids of the report, by source span and text (module docstring)."""

    def __init__(self, report: SpecialistReport, doc: StemDocument) -> None:
        self.report = report
        self.doc = doc
        self.by_id = {c.claim_id for c in report.claims}
        self.texts = {c.claim_id: c.claim_text for c in report.claims}
        self.qualifier = "@" + agent_claim_tag(report.agent_id)
        self._memo: dict[str, list[str]] = {}
        #: claim id whose spelling names a statement its text is not -> (that statement id, the claims the statement maps to)
        self.mismatches: dict[str, tuple[str, list[str]]] = {}
        text = report.original_response
        self._spans: dict[str, tuple[int, int]] = {}
        cursor = 0
        for c in report.claims:
            k = text.find(c.claim_text, cursor) if c.claim_text else -1
            if k < 0 and c.claim_text:
                k = text.find(c.claim_text)
            if k >= 0:
                self._spans.setdefault(c.claim_id, (k, k + len(c.claim_text)))
                cursor = k + 1  # a repeated line ("x = 2" in two parts) is found again further on, not at the same place

    def _expected(self, st) -> str:
        """The text the STEM parser gives the statement (interior markup left out), whitespace-normalised; '' on failure."""
        try:
            return " ".join(statement_claim_text(self.doc.text, self.doc, st.start, st.end).split())
        except Exception:  # the text check only refines the mapping; without it no id is trusted
            return ""

    def _by_text(self, st) -> list[str]:
        """The claims holding the statement's text: offset substrings overlapping its span, else the claims that mention
        its text or that it mentions (the shared two-way substring rule), on the statement as written or as the STEM
        parser gives it (interior markup left out)."""
        out = [cid for cid, (a, b) in self._spans.items() if a < st.end and st.start < b]
        if not out:
            frags = [f for f in (" ".join(self.doc.text[st.start:st.end].split()), self._expected(st)) if f]
            out = [c.claim_id for c in self.report.claims
                   if any(f in " ".join(c.claim_text.split()) or (" ".join(c.claim_text.split()) and " ".join(c.claim_text.split()) in f) for f in frags)]
        return out

    def _agrees(self, cid: str, st, by_text: list[str]) -> bool:
        """Claim ``cid`` holds the statement: it is among the claims holding its text, or its text is the text the STEM
        parser gives the statement (interior markup left out, so it need not be an offset substring)."""
        if cid in by_text:
            return True
        claim = " ".join(self.texts.get(cid, "").split())
        expected = self._expected(st)
        return bool(claim) and bool(expected) and claim == expected

    def statement(self, sid: str) -> list[str]:
        if sid in self._memo:
            return self._memo[sid]
        out: list[str] = []
        st = self.doc.statement(sid)
        if st is not None:
            by_text = self._by_text(st)
            spelled = [sid] + [p + sid[1:] for p in ID_PREFIXES.values() if sid.startswith("s")]
            # on a task with two or more agents the parser qualifies each id by its agent ('s1.1@ess-specialist', B17)
            same = [v for v in spelled + [v + self.qualifier for v in spelled] if v in self.by_id]
            if same and self._agrees(same[0], st, by_text):
                out = [same[0]]
            else:
                out = by_text
                if same:  # a familiar-looking id whose text is another statement's: mapped by text, and the router is told
                    self.mismatches.setdefault(same[0], (sid, list(out)))
        self._memo[sid] = out
        return out

    def relabel(self, text: str) -> str:
        """``text`` with every statement id of this document renamed to the claim it maps to. A statement id that maps
        to no single claim is left as it is, unless a claim of the report is spelled like it (that claim holds another
        statement): it is then renamed to the claims holding the statement, or written as a statement, never left to
        name the wrong claim."""
        def sub(m: "re.Match[str]") -> str:
            sid = m.group(0)
            if self.doc.statement(sid) is None:
                return sid
            mapped = self.statement(sid)
            if len(mapped) == 1:
                return mapped[0]
            if sid in self.by_id or any(p + sid[1:] in self.by_id for p in ID_PREFIXES.values()):
                return ", ".join(mapped) if mapped else f"statement {sid}"
            return sid
        return _SID_RE.sub(sub, text) if "s" in text else text

    def ids(self, statement_ids, limit: Optional[int] = _MAX_CLAIMS_NAMED) -> list[str]:
        out: list[str] = []
        for sid in statement_ids:
            for cid in self.statement(sid):
                if cid not in out:
                    out.append(cid)
        return out if limit is None else out[:limit]

    def mismatch_finding(self) -> Optional[StructuralFinding]:
        """ST-CLAIM-001 (warning) naming every claim id whose spelling names a statement its text is not, with the claims
        that statement's checks and findings were attached to instead (by text), or None."""
        if not self.mismatches:
            return None
        parts: list[str] = []
        named: list[str] = []
        for cid, (sid, mapped) in list(self.mismatches.items())[:_MAX_CLAIMS_NAMED]:
            st = self.doc.statement(sid)
            frag = " ".join(self.doc.text[st.start:st.end].split())[:80] if st is not None else ""
            target = ", ".join(mapped) if mapped else "no claim of the report (none holds its text)"
            parts.append(f"claim id {cid!r} is spelled like statement {sid} ('{frag}'), but its text is '{' '.join(self.texts.get(cid, '').split())[:80]}'; "
                         f"that statement's checks and findings are attached to {target}")
            named.extend([cid, *mapped])
        more = len(self.mismatches) - _MAX_CLAIMS_NAMED
        message = ("the report's claim ids disagree with their texts: " + "; ".join(parts) + (f"; and {more} more" if more > 0 else "")
                   + ". Results are attached to claims by their source spans and texts, never by the spelling of an id")
        return StructuralFinding(code="ST-CLAIM-001", severity="warning", message=message[:_MAX_MESSAGE], claim_ids=list(dict.fromkeys(named)),
                                 rule_source=STEM_RULE_SOURCE)
