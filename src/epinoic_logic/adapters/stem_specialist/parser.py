"""``StemTextParser``: claims from a STEM specialist's answer (docs/STEM_DESIGN.md, section 9).

The parser reads the same :class:`~epinoic_logic.stem.document.StemDocument` the STEM pack
checks (one memoised document per answer, request and profile), so claim ids, statement
numbers and check ids cannot diverge:

* **Claims** are the document's statements: a sentence, a derivation line, a display row, a
  list item, a code block, a table or a data line. A claim's id is the statement's
  ``s<paragraph>.<n>`` in the ``sciences`` branch, and the same numbering with the branch's own
  letter in the other two (``m<paragraph>.<n>`` for mathematics, ``c<paragraph>.<n>`` for
  Computer Science), so a Physics and a Mathematics report on one task never share a claim id
  (the combinator's ledger refuses shared ids, INT-LEDGER-014; two agents of one branch share the
  numbering, as two agents of any other branch do). Its text is an offset substring of the
  original answer (cut to the contract's 4,000 characters, never rewritten).
  ``original_response`` is verbatim. Code blocks, data lines, tables and display maths become
  claims; nothing vanishes. Statements beyond the report's 512-claim limit are merged into
  ``s.tail`` (``m.tail``, ``c.tail``) with the unresolved-issue text the channel turns into
  INT-REQ-013. A statement that carries maths is never taken for a note because it has no
  words (``√8 = 2√2``); only a note clause or a self-certification is a note.
* **Roles** (no new role, design D11): notes and self-certifications are ``other`` (never
  material; the shared ``is_note_sentence``/``is_self_certification`` rules); a heading line
  with no content of its own ("Given:", "Working:") is ``structural``; a Given or data
  line, a value bound to a symbol, a table or data line is ``evidence``/``arithmetic``; a law or
  formula with no numerals is ``evidence``/``factual`` (its truth is the evidence service's);
  a substitution, arithmetic or algebra step is ``quantitative``/``arithmetic``; the last
  chain-bearing statement of a part, and a prose value after "therefore", "so", "hence" or "the
  answer is", is the part's result (``quantitative``, material), so a derivation never reads
  as "no answer"; a code block is a material ``point``; in an explanation paragraph the first
  substantive sentence is the ``point`` (material, supported by the paragraph's other claims),
  a sentence with "because", "since", "so", "therefore", "hence" or "thus" and no value is a
  ``link`` supporting the earlier claims, an assumption ("neglecting air resistance") is
  ``analysis`` and is copied to ``report.assumptions``, anything else is ``analysis``.
* **Quotations** of supplied texts and peer reports are found and credited by the rule every
  parser shares (``sources.attribute_excerpt``), on the quotation view of the answer (code
  masked, an inch or arcsecond mark after a number is not a quotation mark), so the channel and
  the core pack check them exactly as on the other branches.
* **Assumptions.** A claim whose relations the STEM pack decides records "numeric relations of
  this statement are decided by the STEM pack checks <ids>" with the planned check ids.

An empty answer raises ``AdapterError`` (the channel turns it into INT-REQ-009); any other
answer yields claims, a code-only answer included. Nothing here evaluates text.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from ...stem.document import StemDocument, build_document
from ...stem.limits import PROFILES as STEM_PROFILES
from ...stem.si_reading import si_quote_view
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from ...translate.subjects import resolve_profile
from ...ir.schema import SourceRef
from ..base import AdapterError
from ..english_specialist.parser import documents_named
from ..markdown import MAX_CLAIM_TEXT_CHARS, dangling_quote_offset, find_quotation_spans, is_note_sentence, is_self_certification, split_note_clauses
from ..sources import attribute_excerpt

__all__ = ["StemTextParser", "MODE_PROFILES", "ID_PREFIXES", "claim_id_for", "stem_profile_key", "TAIL_CLAIM_ID", "CHECKS_ASSUMPTION"]

#: the STEM profile a branch mode falls back to when the subject label names no STEM profile
MODE_PROFILES = {"sciences": "stem", "mathematics": "mathematics", "computer_science": "computer_science"}
TAIL_CLAIM_ID = "s.tail"
#: the letter a branch mode's claim ids start with (the document's statement ids always start with 's')
ID_PREFIXES = {"sciences": "s", "mathematics": "m", "computer_science": "c"}
#: the assumption text a claim carries for the checks the STEM pack runs on its relations
CHECKS_ASSUMPTION = "numeric relations of this statement are decided by the STEM pack checks "
_MAX_CLAIMS = 512
_MAX_ASSUMPTIONS = 32
_MAX_REPORT_ASSUMPTIONS = 64
_MIN_QUOTE_CHARS = 4
_SELF_REPORT = "self-certified in the response text"
_DIGIT_RE = re.compile(r"[0-9⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]")
_RESULT_CUE_RE = re.compile(r"\b(?:therefore|hence|thus|so|the answer is|the result is|giving|gives|which gives)\b", re.IGNORECASE)
_LINK_CUE_RE = re.compile(r"\b(?:because|since|so|therefore|hence|thus|as a result|consequently)\b", re.IGNORECASE)
_ASSUMPTION_RE = re.compile(
    r"^\s*(?:\(?[a-z]{1,3}\)\s*)?(?:assuming|assume|we assume|neglecting|ignoring|we neglect|we ignore|treating|treat|approximating)\b"
    r"|\b(?:is|are|was|were|can be|may be)\s+(?:neglected|ignored|assumed|negligible)\b|\bassume[sd]?\b|\bnegligible\b", re.IGNORECASE)
_CHAIN_OUTCOMES = frozenset({"check", "context", "undecided"})
_PARA_BREAK_RE = re.compile(r"\n[ \t\r]*\n")
#: a heading-like line with no content of its own ('Given:', 'Working:', 'Solution (a):')
_HEADING_RE = re.compile(r"^[\W_]*[A-Za-z][A-Za-z ()]{0,30}:[\W_]*$")


def stem_profile_key(subject: Optional[str], mode: str = "sciences") -> str:
    """The STEM profile key a subject label reads under: its own profile when that is a STEM profile
    (physics, chemistry, mathematics_aa, computer_science, ...), else the branch mode's fallback."""
    key = resolve_profile(subject).key
    if key in STEM_PROFILES:
        return key
    return MODE_PROFILES.get(mode, "stem")


def claim_id_for(statement_id: str, mode: str = "sciences") -> str:
    """The claim id of a document statement in a branch mode: ``s1.2`` -> ``m1.2`` in mathematics."""
    prefix = ID_PREFIXES.get(mode, "s")
    return prefix + statement_id[1:] if statement_id.startswith("s") else statement_id


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _claim_text(text: str, start: int, end: int) -> str:
    """The statement as an offset substring of the answer, cut to the contract's claim length."""
    return text[start:min(end, start + MAX_CLAIM_TEXT_CHARS)].rstrip()


def _mask_quotations(sentence: str, spans: list[tuple[int, int, str]]) -> str:
    out = list(sentence)
    for start, end, _inner in spans:
        out[start:end] = " " * (end - start)
    return "".join(out)


def _quotations(text_st: str, view_st: str) -> list[tuple[int, int, str]]:
    """``(start, end, excerpt)`` of the quotations of one statement, found on the quotation view and
    read back from the original characters (the view only masks code and number marks)."""
    out: list[tuple[int, int, str]] = []
    for start, end, inner in find_quotation_spans(view_st):
        k = view_st.find(inner, start, end) if inner else -1
        excerpt = text_st[k:k + len(inner)] if k >= 0 else inner
        if len(excerpt.strip()) >= _MIN_QUOTE_CHARS:
            out.append((start, end, excerpt))
    return out


class StemTextParser:
    """Parser of the ``sciences``, ``mathematics`` and ``computer_science`` branches (module docstring).
    ``accepts_request_text``: the channel passes the request text, so the parser reads the same
    document (bindings, show-that targets, planned check ids) as the STEM pack."""

    accepts_request_text = True

    def __init__(self, agent_id: str = "science-specialist", mode: str = "sciences") -> None:
        self.agent_id = agent_id
        self.mode = mode if mode in MODE_PROFILES else "sciences"

    def parse_response(self, text: str, *, request_id: str, task_id: str, report_id: str, subject: str, task_type: str,
                       supplied_texts: list[SuppliedText] = (), course_level: str = "unknown", agent_version: Optional[str] = None,
                       agent_id: Optional[str] = None, request_text: Optional[str] = None) -> SpecialistReport:
        if not text or not text.strip():
            raise AdapterError("the specialist answer is empty")
        agent = agent_id or self.agent_id
        base = dict(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, agent_version=agent_version, subject=subject,
                    course_level=course_level, task_type=task_type)
        doc = build_document(text, request_text, stem_profile_key(subject, self.mode))
        pending, report_assumptions, unresolved = self._claims(text, doc, list(supplied_texts))
        if not pending:
            raise AdapterError("the specialist answer yields no statements")
        claims = [ClaimRecord(**base, **p) for p in pending]
        return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, agent_version=agent_version, subject=subject,
                                course_level=course_level, task_type=task_type, original_response=text, response_sha256=sha256_text(text),
                                supplied_texts=list(supplied_texts), claims=claims, assumptions=report_assumptions[:_MAX_REPORT_ASSUMPTIONS],
                                unresolved_issues=unresolved[:64], created_at=_now())

    # ------------------------------------------------------------------------------------------ claims

    def _statements(self, text: str, doc: StemDocument) -> tuple[list[tuple[str, str, int, int, int, str]], list[str]]:
        """``(id, kind, start, end, paragraph, part)`` of every statement, or a paragraph fallback when the
        front end produced none (it never raises; an internal failure leaves the document empty)."""
        unresolved: list[str] = []
        out = [(st.id, st.kind, st.start, st.end, st.paragraph, st.part) for st in doc.statements if st.end > st.start and text[st.start:st.end].strip()]
        if out:
            return out, unresolved
        cuts = [0] + [m.end() for m in _PARA_BREAK_RE.finditer(text)] + [len(text)]
        p = 0
        for lo, hi in zip(cuts, cuts[1:]):
            while lo < hi and text[lo].isspace():
                lo += 1
            while hi > lo and text[hi - 1].isspace():
                hi -= 1
            if hi <= lo or p >= _MAX_CLAIMS:
                continue
            p += 1
            out.append((f"s{p}.1", "paragraph", lo, hi, p, ""))
        why = "; ".join(f.message for f in doc.findings)[:300] or "no statement was read"
        unresolved.append(f"the STEM front end produced no statements ({why}); each paragraph was kept as one claim and its relations were not read")
        return out, unresolved

    def _claims(self, text: str, doc: StemDocument, supplied: list[SuppliedText]) -> tuple[list[dict], list[str], list[str]]:
        statements, unresolved = self._statements(text, doc)
        docs = {t.document_id: t for t in supplied}
        view = si_quote_view(text, doc.profile.key) if len(doc.reading) == len(text) else text
        report_assumptions: list[str] = []
        rows: list[dict] = []
        for sid, kind, a, b, para, part in statements:
            text_st = text[a:b]
            core, notes = split_note_clauses(text_st)
            rels = doc.relations_for(sid)
            checks = [r.check_id for r in doc.checks_for(sid)]
            maths = bool(rels) or bool(doc.items_for(sid)) or kind in ("code", "table", "data_line", "derivation", "display_row")
            if maths and not core and not notes:
                core = text_st.strip()  # maths with no words is no empty sentence
            if maths:
                note = kind == "tail" or is_self_certification(text_st) or (bool(notes) and not core)
            else:
                note = kind == "tail" or not core or is_self_certification(text_st) or is_note_sentence(core)
            refs: list[SourceRef] = []
            assumptions: list[str] = []
            quotes = _quotations(text_st, view[a:b]) if kind not in ("code", "table") else []
            if quotes:
                named = documents_named(_mask_quotations(text_st, quotes), docs) if docs else []
                for _s, _e, excerpt in quotes:
                    doc_id, notes_for_excerpt = attribute_excerpt(excerpt, named, docs, sentence=text_st)
                    if doc_id:
                        refs.append(SourceRef(document_id=doc_id, excerpt=excerpt[:2000]))
                    assumptions.extend(notes_for_excerpt)
            if kind not in ("code", "table") and dangling_quote_offset(view[a:b]) is not None:
                assumptions.append("the statement has an unbalanced quotation mark; the span it opens or closes was not treated as a quotation and was not checked")
            if core:
                assumptions.extend(f"inline label recorded, not part of the claim: {n[:200]}" for n in notes)
            if checks:
                assumptions.append(CHECKS_ASSUMPTION + ", ".join(checks))
            role, claim_kind, chain = self._role(kind, core or text_st, rels, refs, quotes, note, doc, sid)
            if role == "analysis" and _ASSUMPTION_RE.search(core or ""):
                report_assumptions.append(_claim_text(text, a, b)[:500])
            rows.append(dict(sid=sid, kind=kind, para=para, part=part, chain=chain, role=role, claim_kind=claim_kind, refs=refs,
                             assumptions=list(dict.fromkeys(assumptions))[:_MAX_ASSUMPTIONS], text=_claim_text(text, a, b),
                             self_report=is_self_certification(text_st), value=bool(_DIGIT_RE.search(core or ""))))
        self._materiality(rows)
        self._supports(rows)
        unresolved += self._self_report_notes(rows, self.mode)
        if doc.overflow:
            unresolved.append(f"{doc.overflow} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {claim_id_for(TAIL_CLAIM_ID, self.mode)} and were not individually roled or checked")
        cid = lambda sid: claim_id_for(sid, self.mode)  # noqa: E731
        pending = [dict(claim_id=cid(r["sid"]), claim_text=r["text"], claim_role=r["role"], proposed_claim_kind=r["claim_kind"], source_refs=r["refs"],
                        assumptions=r["assumptions"], materiality=r["materiality"], supporting_claim_ids=[cid(x) for x in r["supports"]],
                        advisory_verification_status=_SELF_REPORT if r["self_report"] else None) for r in rows[:_MAX_CLAIMS]]
        return pending, list(dict.fromkeys(report_assumptions)), unresolved

    @staticmethod
    def _role(kind: str, core: str, rels, refs, quotes, note: bool, doc: StemDocument, sid: str) -> tuple[str, str, bool]:
        """``(role, proposed kind, chain-bearing)`` of one statement (section 9.2 of the design)."""
        if note:
            return "other", "unknown", False
        if kind == "code":
            return "point", "unknown", False
        if kind in ("table", "data_line"):
            return "evidence", "arithmetic", False
        outcomes = {r.outcome for r in rels}
        if not outcomes and _HEADING_RE.match(core):
            return "structural", "unknown", False
        if outcomes & _CHAIN_OUTCOMES:
            return "quantitative", "arithmetic", True
        if outcomes:
            if outcomes <= {"formula"} and not _DIGIT_RE.search(core):
                return "evidence", "factual", False  # a law or definition: its truth is the evidence service's
            return "evidence", "arithmetic", False   # values stated for symbols (Given, 'taking g = 9.81')
        if refs or quotes:
            return "evidence", "factual" if not refs else "unknown", False
        if doc.items_for(sid):
            return ("quantitative", "arithmetic", False) if _DIGIT_RE.search(core) else ("analysis", "unknown", False)
        if _DIGIT_RE.search(core):
            return "quantitative", "arithmetic", False
        if _ASSUMPTION_RE.search(core):
            return "analysis", "unknown", False
        if _LINK_CUE_RE.search(core):
            return "link", "unknown", False
        return "analysis", "unknown", False

    @staticmethod
    def _materiality(rows: list[dict]) -> None:
        """Results are material: per part, the last chain-bearing statement (else the last statement
        stating a value), and every prose value after a result cue. In a paragraph of prose only, the
        first substantive sentence is its point. Code blocks are material; notes never are."""
        for r in rows:
            r["materiality"] = "supporting"
        parts: dict[str, list[dict]] = {}
        for r in rows:
            parts.setdefault(r["part"], []).append(r)
        for items in parts.values():
            chains = [r for r in items if r["chain"]]
            values = [r for r in items if r["role"] == "quantitative"]
            last = chains[-1] if chains else (values[-1] if values else None)
            if last is not None:
                last["materiality"] = "material"
        for r in rows:
            if r["role"] == "quantitative" and not r["chain"] and r["value"] and _RESULT_CUE_RE.search(r["text"]):
                r["materiality"] = "material"
            if r["role"] in ("point",):
                r["materiality"] = "material"
        paragraphs: dict[int, list[dict]] = {}
        for r in rows:
            paragraphs.setdefault(r["para"], []).append(r)
        for items in paragraphs.values():
            body = [r for r in items if r["role"] != "other"]
            if len(body) > 1 and all(r["role"] in ("analysis", "link") and not r["value"] for r in body) and body[0]["role"] == "analysis":
                body[0]["role"] = "point"
                body[0]["materiality"] = "material"

    @staticmethod
    def _supports(rows: list[dict]) -> None:
        """A paragraph's point is supported by the paragraph's other claims; a link by the claims before
        it in its paragraph. A note never supports anything."""
        for r in rows:
            r["supports"] = []
        paragraphs: dict[int, list[dict]] = {}
        for r in rows:
            paragraphs.setdefault(r["para"], []).append(r)
        for items in paragraphs.values():
            body = [r for r in items if r["role"] != "other"]
            for i, r in enumerate(body):
                if r["role"] == "point" and r["kind"] != "code":
                    r["supports"] = [x["sid"] for x in body if x is not r][:_MAX_CLAIMS]
                elif r["role"] == "link":
                    r["supports"] = [x["sid"] for x in body[:i]][:_MAX_CLAIMS]

    @staticmethod
    def _self_report_notes(rows: list[dict], mode: str) -> list[str]:
        out: list[str] = []
        demoted = [r for r in rows if r["self_report"]]
        if demoted:
            shown = "; ".join(f"{claim_id_for(r['sid'], mode)} ('{r['text'][:80]}')" for r in demoted)
            out.append(f"{len(demoted)} statement(s) carrying verification-status language were roled other and count as no material claim: {shown[:600]}")
        return out
