"""``StemTextParser``: claims from a STEM specialist's answer (docs/STEM_DESIGN.md, section 9).

The parser reads the same :class:`~epinoic_logic.stem.document.StemDocument` the STEM pack
checks (one memoised document per answer, request and profile), so claim ids, statement
numbers and check ids cannot diverge:

* **Claims** are the document's statements: a sentence, a derivation line (an equation continued
  on lines that open with ``=`` is one), a display row, a list item, a code block, a table row or a
  data line, cut by the round-7 layout rules (``stem/layout.py``: part labels, label-only lines and
  mark annotations are furniture). A claim's id is the statement's
  ``s<paragraph>.<n>`` in the ``sciences`` branch, and the same numbering with the branch's own
  letter in the other two (``m<paragraph>.<n>`` for mathematics, ``c<paragraph>.<n>`` for
  Computer Science), so a Physics and a Mathematics report on one task never share a claim id
  (the combinator's ledger refuses shared ids, INT-LEDGER-014; two agents of one branch share the
  numbering, as two agents of any other branch do). Its text is the statement's stretch of the
  original answer with the markup inside it left out (emphasis markers, closing mark annotations),
  cut to the contract's 4,000 characters, never rewritten; a statement with no markup inside is an
  offset substring.
  ``original_response`` is verbatim. Code blocks, data lines, tables and display maths become
  claims; nothing vanishes. Statements beyond the report's 512-claim limit are merged into
  ``s.tail`` (``m.tail``, ``c.tail``) with the unresolved-issue text the channel turns into
  INT-REQ-013. A statement that carries maths is never taken for a note because it has no
  words (``√8 = 2√2``); only a note clause or a self-certification is a note.
* **Roles** (no new role, design D11) are the generic branch's round-7 reading of the same
  statements (``generic_parser.assign_roles``: notes, questions and headings are ``other``; the
  answer of each part is material; a consequence or a judgement rests on the claims before it; a
  caveat is no support; supports never form a cycle), so a STEM answer keeps the claims round 7
  verified (docs/STEM_DESIGN.md, section 20). The STEM refinements apply where round 7 did not
  rule (:meth:`StemTextParser._refine`): a code block is a material ``point``; a "Given:" or
  "Working:" heading and a table header row with no words are ``structural``; a binding or a law
  the answer presents as given ("Given:", "Taking g = 9.81 m s⁻²", "Using a = (v − u)/t:") is
  ``evidence``; a judgement restating a checked result is ``quantitative``; a reason sentence
  ("because", "since") is a ``link``; an answer with no part labels and no material claim has its
  result made material, so a derivation never reads as "no answer". An assumption ("neglecting
  air resistance") read as ``analysis`` is copied to ``report.assumptions``.
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
from ...stem.layout import ANNOTATION_ONLY_RE, LABEL_ONLY_REST_RE, TABLE_ROW_RE, TABLE_SEPARATOR_RE, plain_line

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
#: the headings of a derivation's own structure: a heading over given data or working is structural, never a note
_STRUCTURE_HEAD_RE = re.compile(r"^[\W_]*(?:given|data|known|working|workings|solution|method|calculations?)(?:\s*\(?[a-z0-9]{1,4}\)?)?\s*:[\W_]*$")
#: a heading over given data ("Given:", "Data:", "Known values:"): the lines under it state what the answer takes as given
_GIVEN_HEAD_RE = re.compile(r"^[\W_]*(?:given|data|known)(?:\s+(?:data|values|quantities))?\s*:[\W_]*$")
#: a statement led by what it takes as given ("Given m = 2.0 kg", "Taking g = 9.81 m s⁻²", "Using a = (v − u)/t:")
_GIVEN_CUE_RE = re.compile(r"^[\W_]*(?:given|taking|take|using|use|data|known)\b", re.IGNORECASE)
#: a word of a table's header row (two letters or more, Boolean operator names aside): a header row with one is a heading
_HEADER_WORD_RE = re.compile(r"\b(?!(?:AND|OR|NOT|XOR|NAND|NOR)\b)[A-Za-z]{2,}")
#: a reason given for what the sentence or the one before it states: a link
_REASON_RE = re.compile(r"\b(?:because|since)\b", re.IGNORECASE)
#: a blank line between paragraphs (the generic branch's paragraph cut)
_PARAGRAPH_CUT_RE = re.compile(r"\n\s*\n")


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


def _generic():
    """The generic branch's parser module (imported on first use: ``branches`` imports this module through its registry)."""
    from ...branches import generic_parser
    return generic_parser


def _claim_text(text: str, start: int, end: int, markup: list[tuple[int, int]] = ()) -> str:
    """The statement's text: its stretch of the answer with the markup inside it left out (emphasis markers and the
    mark annotations that close a line or a sentence: ``**What the question wants:** the value`` is "What the question
    wants: the value", ``reaching 22 at E [1].`` is "reaching 22 at E.", as on the generic branch), cut to the
    contract's claim length. A statement with no markup inside is an offset substring of the answer."""
    inner = [(max(a, start), min(b, end)) for a, b in markup if a < end and start < b]
    if not inner:
        return text[start:min(end, start + MAX_CLAIM_TEXT_CHARS)].rstrip()
    parts: list[str] = []
    pos = start
    for a, b in inner:
        if a > pos:
            parts.append(text[pos:a])
        pos = max(pos, b)
    parts.append(text[pos:end])
    return "".join(parts)[:MAX_CLAIM_TEXT_CHARS].rstrip()


def _units(text: str, rows: list[dict]) -> list:
    """One generic-branch unit per statement, with what the generic parser records for a unit of the same line
    (``generic_parser._units_of``): its paragraph (the blank-line paragraphs of the answer), its logical line, the
    part it stands in (a part lead opens one, label-only or not), whether it is on its part's opening line, whether its
    line closes on an accuracy mark, and the line's heading status (a short line closing on a colon, a short title, a
    table's header row). The lead (note, heading, question, result, ...) is the generic classification."""
    g = _generic()
    _PART_LEAD_RE, _Unit, _classify, _line_heading, _ACCURACY_MARK_RE, _NOT_OPENING = (
        g._PART_LEAD_RE, g._Unit, g._classify, g._line_heading, g._ACCURACY_MARK_RE, g._NOT_OPENING)
    starts = [0]
    for m in _PARAGRAPH_CUT_RE.finditer(text):
        starts.append(m.end())

    def paragraph(offset: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    # physical lines: offsets, the part each opens, label-only leads, accuracy marks, table header rows
    line_starts = [0]
    k = text.find("\n")
    while k >= 0:
        line_starts.append(k + 1)
        k = text.find("\n", k + 1)
    plains = []
    for li, ls in enumerate(line_starts):
        le = line_starts[li + 1] - 1 if li + 1 < len(line_starts) else len(text)
        plains.append(plain_line(text[ls:le])[0])

    def line_of(offset: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    lead_lines = {li for li, pl in enumerate(plains) if _PART_LEAD_RE.match(pl)}
    label_only = {li for li in lead_lines if LABEL_ONLY_REST_RE.fullmatch(plains[li][_PART_LEAD_RE.match(plains[li]).end():])}
    headers = {li for li, pl in enumerate(plains) if TABLE_ROW_RE.match(pl) and li + 1 < len(plains)
               and TABLE_SEPARATOR_RE.match(plains[li + 1]) and "-" in plains[li + 1]}
    part_at: list[int] = []
    count = 0
    for li in range(len(plains)):
        if li in lead_lines:
            count += 1
        part_at.append(count)
    # the logical line of each statement: the first physical line of the line it stands on (the segmenter joins the
    # lines that continue one, and every sentence of a line shares it)
    last_lines = [line_of(max(r["a"], r["b"] - 1)) for r in rows]
    logical: list[int] = [min(r["line"], line_of(r["a"])) for r in rows]
    accuracy_lines = {li for li, pl in enumerate(plains) if _ACCURACY_MARK_RE.search(pl)}
    units: list[_Unit] = []
    paras = [paragraph(r["a"]) for r in rows]
    # heading status per logical line: the line's own text (its statements), and whether a line follows it in its paragraph
    by_line: dict[int, list[int]] = {}
    for i, ln in enumerate(logical):
        by_line.setdefault(ln, []).append(i)
    order = sorted(by_line)
    heading_of: dict[int, bool] = {}
    for n, ln in enumerate(order):
        idx = by_line[ln]
        body = " ".join(rows[i]["text"] for i in idx)
        following = n + 1 < len(order) and paras[by_line[order[n + 1]][0]] == paras[idx[0]]
        heading_of[ln] = ln in headers or (ln not in lead_lines and _line_heading(body, following))
    for i, r in enumerate(rows):
        ln = logical[i]
        u = _Unit(text=r["text"], para=paras[i], line=ln, part=part_at[ln] if ln < len(part_at) else count)
        units.append(_classify(u, heading_of[ln]))
    # opening lines of parts: a part lead with content opens its part on its own line; after a label-only lead the
    # first line that is no heading, no note and no question opens it
    awaiting = False
    done: set[int] = set()
    lead_list = sorted(lead_lines)
    li_pos = 0
    for ln in order:
        while li_pos < len(lead_list) and lead_list[li_pos] < ln:
            if lead_list[li_pos] in label_only:
                awaiting = True
            li_pos += 1
        idx = by_line[ln]
        if ln in lead_lines and ln not in label_only:
            for i in idx:
                units[i].opening = True
            awaiting = False
        elif awaiting and not heading_of[ln] and not all(units[i].lead in _NOT_OPENING for i in idx):
            for i in idx:
                units[i].opening = True
            awaiting = False
        done.add(ln)
        # the result an accuracy mark credits closes its line
        if any(x in accuracy_lines for x in range(ln, max(last_lines[i] for i in idx) + 1)):
            units[idx[-1]].accuracy = True
    return units


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

    def _statements(self, text: str, doc: StemDocument) -> tuple[list[tuple[str, str, int, int, int, str, int]], list[str]]:
        """``(id, kind, start, end, paragraph, part, line)`` of every statement (``line``: the first line of the logical
        line it stands on), or a paragraph fallback when the front end produced none (it never raises; an internal
        failure leaves the document empty)."""
        unresolved: list[str] = []
        out = [(st.id, st.kind, st.start, st.end, st.paragraph, st.part, st.line) for st in doc.statements if st.end > st.start and text[st.start:st.end].strip()]
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
            out.append((f"s{p}.1", "paragraph", lo, hi, p, "", text.count("\n", 0, lo)))
        why = "; ".join(f.message for f in doc.findings)[:300] or "no statement was read"
        unresolved.append(f"the STEM front end produced no statements ({why}); each paragraph was kept as one claim and its relations were not read")
        return out, unresolved

    def _claims(self, text: str, doc: StemDocument, supplied: list[SuppliedText]) -> tuple[list[dict], list[str], list[str]]:
        statements, unresolved = self._statements(text, doc)
        docs = {t.document_id: t for t in supplied}
        view = si_quote_view(text, doc.profile.key) if len(doc.reading) == len(text) else text
        markup = sorted(doc.spans.markup) if len(doc.reading) == len(text) else []
        prose_valued = {pv.statement_id for pv in doc.prose_values}
        report_assumptions: list[str] = []
        rows: list[dict] = []
        for sid, kind, a, b, para, part, line in statements:
            text_st = text[a:b]
            claim_text = _claim_text(text, a, b, markup)
            core, notes = split_note_clauses(claim_text)
            rels = doc.relations_for(sid)
            checks = [r.check_id for r in doc.checks_for(sid)]
            maths = bool(rels) or bool(doc.items_for(sid)) or kind in ("code", "table", "data_line", "derivation", "display_row")
            if maths and not core and not notes:
                core = claim_text.strip()  # maths with no words is no empty sentence
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
            stem_role, stem_kind, chain = self._role(kind, core or claim_text, rels, refs, quotes, False, doc, sid)
            rows.append(dict(sid=sid, kind=kind, a=a, b=b, para=para, part=part, line=line, chain=chain, stem_role=stem_role, stem_kind=stem_kind, refs=refs,
                             quoted=bool(refs or quotes), assumptions=list(dict.fromkeys(assumptions))[:_MAX_ASSUMPTIONS], text=claim_text,
                             self_report=is_self_certification(claim_text), value=bool(_DIGIT_RE.search(core or "")),
                             maths_note=maths and bool(notes) and not core.strip(), res=any(r.kind == "res" for r in rels if r.outcome == "check"),
                             prose_value=sid in prose_valued))
        self._assign(text, rows)
        for r in rows:
            if r["role"] == "analysis" and _ASSUMPTION_RE.search(split_note_clauses(r["text"])[0] or ""):
                report_assumptions.append(r["text"][:500])
        unresolved += self._self_report_notes(rows, self.mode)
        if doc.overflow:
            unresolved.append(f"{doc.overflow} sentences beyond the report's claim limit ({_MAX_CLAIMS}) were merged into claim {claim_id_for(TAIL_CLAIM_ID, self.mode)} and were not individually roled or checked")
        cid = lambda sid: claim_id_for(sid, self.mode)  # noqa: E731
        pending = [dict(claim_id=cid(r["sid"]), claim_text=r["text"], claim_role=r["role"], proposed_claim_kind=r["claim_kind"], source_refs=r["refs"],
                        assumptions=r["assumptions"], materiality=r["materiality"], supporting_claim_ids=[cid(x) for x in r["supports"]],
                        advisory_verification_status=_SELF_REPORT if r["self_report"] else None) for r in rows[:_MAX_CLAIMS]]
        return pending, list(dict.fromkeys(report_assumptions)), unresolved

    # ------------------------------------------------------------------------------------------ roles

    def _assign(self, text: str, rows: list[dict]) -> None:
        """Roles, materiality and supports of the statements: the generic branch's round-7 reading
        (``generic_parser.assign_roles``: notes, questions and headings are ``other``; the answer of each part is
        material; a consequence or a judgement rests on the claims before it; a caveat is no support; supports never
        form a cycle), run on units built from the STEM statements (:func:`_units`), then the STEM refinements of
        section 9.2 that round 7 did not rule on (:meth:`_refine`)."""
        units = _units(text, rows)
        para_units: list[list] = []
        last = None
        for u in units:
            if not para_units or u.para != last:
                para_units.append([])
                last = u.para
            para_units[-1].append(u)
        assigned = _generic().assign_roles(para_units, [r["quoted"] for r in rows])
        for i, r in enumerate(rows):
            r["role"], r["material"], r["answer"] = assigned.roles[i], assigned.material[i], assigned.answer[i]
            r["consequence"] = assigned.consequence[i]
            r["supports_idx"] = sorted(set(assigned.supports.get(i, ())) - {i}) if assigned.roles[i] != "other" else []
            r["lead"], r["dev_part"], r["para_dev"] = units[i].lead, units[i].part, units[i].para
        self._refine(rows)
        for i, r in enumerate(rows):
            if r["role"] == "other":
                r["supports_idx"] = []
            r["supports"] = [rows[j]["sid"] for j in r["supports_idx"] if rows[j]["role"] != "other"][:_MAX_CLAIMS]
            mat = (r["material"] or r["role"] in ("point", "judgement")) and r["role"] != "other"
            r["materiality"] = "material" if mat else "supporting"
            if r["role"] == r["stem_role"]:
                r["claim_kind"] = r["stem_kind"]
            else:
                r["claim_kind"] = "arithmetic" if r["role"] == "quantitative" else ("factual" if r["role"] == "evidence" and not r["refs"] else "unknown")

    @staticmethod
    def _refine(rows: list[dict]) -> None:
        """The STEM refinements (section 9.2 of the design) on top of the generic branch's roles. None adds a support, so
        no cycle can form:

        * a code block is a material point (it answers the item; it is never read for meaning);
        * a heading over given data or working ("Given:", "Working:") is ``structural``, not a note, and so is a table's
          header row that holds no word (``| A | B |``: maths with no words is never a note); a header row with words
          ("| Pass | low | high |") stays a heading, as on the generic branch;
        * a statement whose relations only bind values or state a law and that states no other value in its prose is
          ``evidence`` (arithmetic or factual) when the answer presents it as what it takes as given: under a "Given:" or
          "Data:" heading (``m = 2.0 kg``), led by "Given", "Taking" or "Using" ("Using a = (v − u)/t:"), or where the
          generic reading would take it for its paragraph's point ("The trolley starts from rest, so u = 0."); a law or
          a binding written as a line of working ("V = ε − Ir" over its substitution, "At rest means v = 0:", "Let T be
          the half-life, so C(T) = ½C0:") keeps the generic reading's role. A part's answer, a quotation and a prose
          value are never evidence;
        * a sentence that restates a result the STEM pack checks (a prose value after "therefore", "so", "the answer
          is") is ``quantitative``;
        * a reason sentence ("because", "since") with no value that the generic reading leaves as analysis is a ``link``
          (a consequence is the generic reading's: a judgement when it opens the sentence, plain otherwise);
        * a working step that opens a prose paragraph whose result a later sentence of the paragraph restates ("Using
          a = Δv/Δt, a = (20 − 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻².") is a supporting step, not
          the paragraph's point: the restatement is the result;
        * a note clause that holds maths ("(Figures from memory: g = 9.8.)") is a note;
        * an answer with no part labels whose claims hold no material one has its result made material: the last
          chain-bearing statement, else the last statement that states a value (a derivation never reads as "no
          answer").
        """
        for i, r in enumerate(rows):
            if r["role"] == "point" and r["chain"] and not r["answer"] and r["stem_role"] == "quantitative" \
                    and any(x["res"] and x["para_dev"] == r["para_dev"] for x in rows[i + 1:]):
                r["role"], r["material"], r["supports_idx"] = "quantitative", False, []
        given_head: Optional[int] = None  # the paragraph of the last "Given:" heading whose lines are still running
        for i, r in enumerate(rows):
            if r["kind"] == "tail":
                r["role"], r["material"], r["supports_idx"] = "other", False, []
                continue
            if r["maths_note"]:
                r["role"], r["material"], r["supports_idx"] = "other", False, []
                continue
            if r["kind"] == "code":
                r["role"], r["material"], r["supports_idx"] = "point", True, []
                continue
            if r["role"] == "other" and r["lead"] == "heading" and not r["self_report"]:
                head = r["text"].strip().lower()
                given_head = r["para_dev"] if _GIVEN_HEAD_RE.match(head) else None
                if (r["kind"] == "table" and not _HEADER_WORD_RE.search(r["text"])) or _STRUCTURE_HEAD_RE.match(head):
                    r["role"] = "structural"
                continue
            under_given = given_head is not None and given_head == r["para_dev"]
            if r["role"] == "other":
                continue
            if r["stem_role"] == "evidence" and r["kind"] not in ("table", "data_line") and not r["quoted"] and not r["answer"] and not r["prose_value"] \
                    and r["role"] in ("quantitative", "analysis", "point") and (r["role"] == "point" or under_given or _GIVEN_CUE_RE.match(r["text"])):
                if r["role"] == "point":
                    r["material"] = False
                r["role"], r["supports_idx"] = "evidence", []
                continue
            given_head = None  # a line that states no given value ends the lines under a "Given:" heading
            if r["res"] and r["role"] == "judgement":
                r["role"] = "quantitative"
                continue
            if r["role"] == "analysis" and r["stem_role"] == "link" and _REASON_RE.search(r["text"]):
                r["role"] = "link"
        if any(r["dev_part"] for r in rows) or any(r["role"] not in ("other", "structural") and (r["material"] or r["role"] in ("point", "judgement")) for r in rows):
            return
        live = [r for r in rows if r["role"] not in ("other", "structural")]
        chains = [r for r in live if r["chain"]]
        values = [r for r in live if r["role"] == "quantitative" and r["value"]]
        last = chains[-1] if chains else (values[-1] if values else None)
        if last is not None:
            last["material"] = True
        for r in live:
            if r["role"] == "quantitative" and not r["chain"] and r["value"] and _RESULT_CUE_RE.search(r["text"]):
                r["material"] = True

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
    def _self_report_notes(rows: list[dict], mode: str) -> list[str]:
        out: list[str] = []
        demoted = [r for r in rows if r["self_report"]]
        if demoted:
            shown = "; ".join(f"{claim_id_for(r['sid'], mode)} ('{r['text'][:80]}')" for r in demoted)
            out.append(f"{len(demoted)} statement(s) carrying verification-status language were roled other and count as no material claim: {shown[:600]}")
        return out
