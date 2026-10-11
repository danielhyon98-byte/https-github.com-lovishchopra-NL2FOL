"""Integrity packs: the subject-specific checks each branch carries, plus the core pack
every branch runs. Deterministic findings cite the pack's working rules; formal checks
are problems the engine decides about the report's own statements."""
from __future__ import annotations

import re
from typing import Optional

from ..adapters.history_specialist.chronology import chronology_relations
from ..adapters.history_specialist.sentences import split_sentences as _split_sentences, strip_json_spans
from ..adapters.markdown import MEMORY_LABEL_RE as _MEMORY_LABEL_RE, SELF_CERT_RE, dangling_quote_offset, find_quotation_spans, is_memory_label, unbalanced_double_quotes
from ..adapters.sources import check_excerpt, strip_trailing_punctuation, uncredited_excerpt
from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from ..translate.grounding import FORM_DIFFERS, check_claim_sources, find_quotation
from .base import FormalCheck
from .quant import extract_quant_checks, undecided_quant_statements

_PARA_RE = re.compile(r"\n\s*\n")
_STUDY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s(?:and|&)\s[A-Z][a-z]+)?(?:\set\sal\.?)?)\s*\((\d{4})\)")
_PCT_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*(?:per cent|percent(?!age)|%)")
#: A from-memory label that speaks of quotations (a figures label does not vouch for a quotation).
_QUOTE_MEMORY_LABEL_RE = re.compile(r"quot(?:ation|e)s?[^.;\n]{0,60}\bfrom memory\b|\bquoted from memory\b|\bfrom memory\b[^.;\n]{0,60}quot(?:ation|e)", re.IGNORECASE)
#: Shortest quoted span the core pack reports as an unverifiable quotation (a title or a single term is not one).
_MIN_QUOTE_CHARS = 12
_EXCERPT_CHARS = 80
#: A peer agent's report supplied as a document: 'peer:<task>' or an author of the form '<subject>-specialist'.
_PEER_AUTHOR_RE = re.compile(r"^[a-z]+(?:[-_ ][a-z]+)*[-_ ]specialist$")
#: 'the poem', 'the extract': the one non-peer supplied text, when there is exactly one; 'the colleague', 'the peer': the one peer text.
_GENERIC_SOURCES = ("poem", "sonnet", "extract", "passage", "text", "novel", "play", "speech", "source", "document", "story", "essay", "article")
_GENERIC_PEERS = ("peer", "colleague", "other specialist", "peer agent", "peer specialist")
#: A saying verb or attribution phrase after a named source binds the quotation that follows to that source.
_ATTRIBUTION_RE = re.compile(
    r"\b(?:describes?|described|notes?|noted|writes?|wrote|says?|said|states?|stated|warns?|warned|argues?|argued|observes?|observed|calls?|called|records?|recorded|reports?|reported|"
    r"explains?|explained|points? out|pointed out|adds?|added|concludes?|concluded|remarks?|remarked|insists?|insisted|tells?|told|puts? it|put it|claims?|claimed|asserts?|asserted|"
    r"answers?|answered|speaks? of|spoke of|refers? to|referred to|mentions?|mentioned|quotes?|quoted|cites?|cited|repeats?|repeated|opens? with|closes? with|ends? with|begins? with|reads?|"
    r"shows?|showed|presents?|presented|gives?|gave|offers?|offered|uses?|used|employs?|employed|contains?|contained|includes?|included|depicts?|depicted|portrays?|portrayed|"
    r"in (?:his|her|its|their) words|(?:'s|’s) (?:words?|phrase|phrasing|paragraph|account|setting|description|point|claim|note|warning|line|lines|verdict))\b",
    re.IGNORECASE,
)
#: A reporting clause: '<outer speaker> argues/notes/writes ... that' introduces an inner subject whose words are the outer speaker's report.
_REPORTING_RE = re.compile(r"\b(?:argues?|argued|notes?|noted|writes?|wrote|says?|said|states?|stated|claims?|claimed|observes?|observed|suggests?|suggested|holds?|held|maintains?|contends?|reports?|reported|concludes?|concluded|insists?|shows?|points? out|adds?)\s+that\b", re.IGNORECASE)
#: An attribution phrase that precedes the source's name: 'according to the History specialist, "..."'.
_LEADING_ATTRIBUTION_RE = re.compile(r"\b(?:according to|in the words of|as|per)\s+(?:the\s+|my\s+|our\s+)?$", re.IGNORECASE)
#: A source named right after a quotation as its tag: '"...", the History specialist writes' / '"...", as Shelley puts it'.
#: Nothing but punctuation, an optional saying verb or attribution phrase and an article may stand between the quotation and the name.
_TAG_HEAD_RE = re.compile(
    r"^[\s,;:—–-]*(?:(?:as|according to|in the words of|so|says|said|writes|wrote|notes|noted|observes|observed|argues|argued|remarks|remarked|adds|added|warns|warned|concludes|concluded|states|stated|in)\s+)?(?:the\s+|my\s+|our\s+)?$",
    re.IGNORECASE,
)


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """(paragraph number, paragraph) over the raw response, 1-based."""
    return [(pi, p.strip()) for pi, p in enumerate((p for p in _PARA_RE.split(text.strip()) if p.strip()), start=1)]


def _sentences_with_paragraph(text: str) -> list[tuple[int, int, str, str]]:
    """(paragraph number, sentence number, sentence, paragraph) over the raw response, 1-based,
    split with the shared abbreviation-aware splitter (``c.``, ``approx.``, initials never end a sentence)."""
    out: list[tuple[int, int, str, str]] = []
    for pi, para in _paragraphs(text):
        for si, sent in enumerate(_split_sentences(para), start=1):
            out.append((pi, si, sent.strip(), para))
    return out


def _chronology_formal(report: SpecialistReport, prefix: str) -> list[FormalCheck]:
    """Every dated ordering a sentence asserts ('after', 'before', 'followed', 'preceded',
    with or without 'by') becomes an entailment problem: the event the sentence places
    later must have the later day ordinal ((year*12+month)*32+day). The relations come
    from ``history_specialist.chronology.chronology_relations``, the extractor the History
    proxy ``HI-CHR-001`` also reads, with the paragraph as context for a date whose year
    the sentence does not state, so the proxy and the engine never disagree. A relation the
    extractor could not pair (an aside date, an unstated year, two events in the same month
    with no days) is not a problem here; ``CorePack`` reports it as ``CORE-CHR-001``."""
    from ..ir.schema import Problem
    out: list[FormalCheck] = []
    n = 0
    for _pi, _si, sent, para in _sentences_with_paragraph(report.original_response):
        for rel in chronology_relations(sent, para):
            if not rel.decided or rel.later_ordinal is None or rel.earlier_ordinal is None:
                continue
            n += 1
            problem = {
                "problem_id": f"chron-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:chronology-{n}", "query": "entailment",
                "symbols": [{"name": "later_event", "sort": "Int", "meaning": f"{rel.later_text} as a day ordinal ((year*12+month)*32+day; an unstated month or day counts 0)"},
                            {"name": "earlier_event", "sort": "Int", "meaning": f"{rel.earlier_text} as a day ordinal ((year*12+month)*32+day; an unstated month or day counts 0)"}],
                "premises": [{"id": "D1", "expr": {"op": "eq", "left": {"op": "var", "name": "later_event"}, "right": {"op": "int", "value": str(rel.later_ordinal)}}, "label": rel.later_text, "grounding": {"kind": "supplied_text", "verified": True}},
                             {"id": "D2", "expr": {"op": "eq", "left": {"op": "var", "name": "earlier_event"}, "right": {"op": "int", "value": str(rel.earlier_ordinal)}}, "label": rel.earlier_text, "grounding": {"kind": "supplied_text", "verified": True}}],
                "conclusion": {"id": "ORDER", "expr": {"op": "gt", "left": {"op": "var", "name": "later_event"}, "right": {"op": "var", "name": "earlier_event"}},
                               "label": f"'{rel.later_text}' is later than '{rel.earlier_text}', as the sentence's '{rel.cue}' asserts" + (f" ({rel.reason})" if rel.reason else "")},
            }
            out.append(FormalCheck(check_id=f"{prefix}-chronology-{n}", kind="chronology",
                                   description=f"stated order of dated events ('{rel.cue}': {rel.later_text} later than {rel.earlier_text}): {sent.strip()[:160]}", problem=Problem.model_validate(problem)))
    return out


def _quant_formal(report: SpecialistReport, prefix: str) -> list[FormalCheck]:
    """The report's own arithmetic as engine problems. A relation stated across sentences (a
    derived figure, 'rose in each year', 'the greatest rise' whose figures stand in another
    sentence of the paragraph) says in its description where its year and figures were read."""
    out: list[FormalCheck] = []
    for qc in extract_quant_checks(report.original_response, request_id=report.request_id, claim_id=f"{report.report_id}:{prefix}"):
        description = f"report's own arithmetic: {qc.sentence[:160]}" + (f" [{qc.basis[:400]}]" if qc.basis else "") + (f" [{qc.rule}]" if qc.rule else "")
        out.append(FormalCheck(check_id=f"{prefix}-{qc.check_id}", kind=qc.kind, description=description, problem=qc.problem))
    return out


def _is_peer_text(t: SuppliedText) -> bool:
    return t.document_id.startswith("peer:") or bool(t.author and _PEER_AUTHOR_RE.match(t.author.strip().lower()))


def _source_names(texts: list[SuppliedText]) -> dict[str, tuple[str, str]]:
    """Phrases that name a supplied text in prose -> (document_id, label): an author's full
    name and surname, a title (parenthetical and subtitle removed), and for a peer agent's
    report the agent spoken of as '<subject> specialist'."""
    names: dict[str, tuple[str, str]] = {}
    for t in texts:
        if t.author:
            author = " ".join(t.author.split())
            if _is_peer_text(t):
                phrase = re.sub(r"[-_]+", " ", author.lower())
                names[phrase] = (t.document_id, f"the {phrase}")
            else:
                names[author.lower()] = (t.document_id, author)
                surname = author.split()[-1]
                if len(surname) >= 3 and surname.isalpha():
                    names[surname.lower()] = (t.document_id, author)
        if t.title and not _is_peer_text(t):
            title = re.sub(r"\s*\([^)]*\)", "", t.title).split(",")[0].strip().strip("'\"“”‘’").lower()
            if len(title) >= 4 and re.search(r"[^\W\d_]", title):
                names[title] = (t.document_id, f"'{title}'")
    non_peer = [t for t in texts if not _is_peer_text(t)]
    peers = [t for t in texts if _is_peer_text(t)]
    if len(non_peer) == 1:
        for g in _GENERIC_SOURCES:
            names.setdefault(f"the {g}", (non_peer[0].document_id, f"the {g}"))
    if len(peers) == 1:
        for g in _GENERIC_PEERS:
            names.setdefault(f"the {g}", (peers[0].document_id, f"the {g}"))
            names.setdefault(f"my {g}", (peers[0].document_id, f"my {g}"))
    return names


def _named_mentions(text: str, names: dict[str, tuple[str, str]]) -> list[tuple[int, int, str, str]]:
    """(start, end, document_id, label) for every named source mentioned in ``text``, in order."""
    low = text.lower()
    found: list[tuple[int, int, str, str]] = []
    for phrase, (doc_id, label) in names.items():
        for m in re.finditer(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", low):
            found.append((m.start(), m.end(), doc_id, label))
    found.sort()
    return found


def _attributions(sentence: str, spans: list[tuple[int, int, str]], names: dict[str, tuple[str, str]]) -> list[Optional[tuple[str, str, list[tuple[str, str]]]]]:
    """For each quotation span of ``sentence``, ``(document_id, label, others)``: the source
    its sentence credits it to and the other sources named before it, or None.

    A quotation is credited to the named source before it whose saying verb binds the
    quotation (``the History specialist notes that "..."``) or that an attribution phrase
    precedes (``according to X, "..."``); the credit carries to the following quotations of
    the sentence until another source is named. When the span before the quotation is a
    reporting clause, ``<A> argues that <B> presents ... "..."``, the OUTER speaker A is
    credited: the words are A's report, whatever B is said to do. ``others`` lists every
    other source named before the quotation, so a credit that competes with a second named
    source is reported as ambiguous rather than as a wrong credit. Failing that, a name right
    after the quotation with a saying verb (``"...", Shelley writes``) credits it.
    ``Shelley's "Ozymandias"`` credits nothing: a possessive before a title is a topic."""
    prose = list(sentence)
    for s, e, _inner in spans:
        for i in range(s, e):
            prose[i] = " "
    text = "".join(prose)
    out: list[Optional[tuple[str, str, list[tuple[str, str]]]]] = []
    current: Optional[tuple[str, str]] = None
    current_others: list[tuple[str, str]] = []
    for idx, (s, e, _excerpt) in enumerate(spans):
        prev_end = spans[idx - 1][1] if idx else 0
        next_start = spans[idx + 1][0] if idx + 1 < len(spans) else len(text)
        before, after = text[prev_end:s], text[e:next_start]
        mentions = _named_mentions(before, names)
        distinct = []
        for _ms, _me, doc_id, label in mentions:
            if all(doc_id != d for d, _l in distinct):
                distinct.append((doc_id, label))
        if mentions:
            chosen: Optional[tuple[str, str]] = None
            first = mentions[0]
            if len(distinct) >= 2 and _REPORTING_RE.search(before[first[1]: mentions[-1][0]]):
                chosen = (first[2], first[3])  # '<A> argues that <B> ...': the outer speaker's report
            else:
                _ms, me, doc_id, label = mentions[-1]
                if _ATTRIBUTION_RE.search(before[me:]) or _LEADING_ATTRIBUTION_RE.search(before[:mentions[-1][0]]):
                    chosen = (doc_id, label)
            current = chosen
            current_others = [d for d in distinct if chosen is None or d[0] != chosen[0]] if chosen else []
        attributed = current
        others = list(current_others)
        if attributed is None:
            following = _named_mentions(after[:80], names)
            if following and _TAG_HEAD_RE.match(after[: following[0][0]]) and (_ATTRIBUTION_RE.search(after[following[0][1]: following[0][1] + 60]) or _LEADING_ATTRIBUTION_RE.search(after[: following[0][0]])):
                attributed, others = (following[0][2], following[0][3]), []
        out.append((attributed[0], attributed[1], others) if attributed else None)
    return out


def _claims_for_excerpt(report: SpecialistReport, sentence: str, excerpt: str, sentence_excerpts: list[str]) -> list[str]:
    """The claims a finding about one quotation of ``sentence`` names: the claims whose source
    reference carries that excerpt, and the sentence's own claim; a claim that carries only the
    sentence's OTHER quotations (credited correctly) is not named."""
    key = strip_trailing_punctuation(" ".join(excerpt.split()))
    others = {strip_trailing_punctuation(" ".join(x.split())) for x in sentence_excerpts} - {key}

    def carried(c) -> set[str]:
        return {strip_trailing_punctuation(" ".join(r.excerpt.split())) for r in c.source_refs if r.excerpt}

    carriers = [c.claim_id for c in report.claims if key in carried(c)]
    mentioning = [c for c in report.claims if c.claim_id in set(_claims_mentioning(report, sentence))]
    own = [c.claim_id for c in mentioning if not (carried(c) and carried(c) <= others) and not (" ".join(c.claim_text.split()).strip(" '\"“”‘’«».,;:") in others)]
    ids = list(dict.fromkeys(carriers + own))
    return ids or [c.claim_id for c in report.claims if excerpt in c.claim_text]


def _claims_mentioning(report: SpecialistReport, fragment: str) -> list[str]:
    frag = " ".join(fragment.split())
    return [c.claim_id for c in report.claims if frag and (frag in " ".join(c.claim_text.split()) or " ".join(c.claim_text.split()) in frag)]


class CorePack:
    """Runs for every subject: quotation grounding against supplied texts, numeric
    self-consistency of the report's own figures (and CORE-QNT-001 for a stated derived
    figure no check could be built for), labelling of figures from memory,
    unverifiable, undelimited or misattributed quotations, dated orderings that could
    not be decided, and self-certification language. Quotations are read in straight,
    curly or mixed double marks, guillemets and delimited single marks of two or more
    words, exactly as the parsers read them, after pasted JSON fragments are removed."""
    name = "core"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        text = report.original_response
        for c in report.claims:
            for g in check_claim_sources(c, report.supplied_texts):
                # a quotation located in another form (initial capital, line-break mark, diacritics, long elision) is not
                # 'not found': the hub names it INT-REQ-010 and the subject pack warns, so no error here contradicts them
                if g.verified is False and FORM_DIFFERS not in (g.detail or ""):
                    f.append(StructuralFinding(code="CORE-SRC-001", severity="error", message="cited excerpt not found in the supplied text", claim_ids=[c.claim_id], rule_source="source integrity (every pack's non-negotiable 2)"))
        has_memory_label = bool(_MEMORY_LABEL_RE.search(text))
        if _PCT_RE.search(text) and not report.supplied_texts and not has_memory_label and not any(c.source_refs for c in report.claims):
            f.append(StructuralFinding(code="CORE-SRC-002", severity="info", message="figures stated without supplied sources, library references or a from-memory label", rule_source="sources.md L5 (working rule)"))
        f += self._unverifiable_quotations(report, has_memory_label)
        if report.supplied_texts:
            f += self._misattributed_quotations(report)
        f += self._unbalanced_quotation_marks(report)
        f += self._self_certification(report)
        f += self._undecided_chronology(report)
        f += self._undecided_arithmetic(report)
        return f

    @staticmethod
    def _unverifiable_quotations(report: SpecialistReport, has_memory_label: bool) -> list[StructuralFinding]:
        """CORE-SRC-003: every quotation with no text to check it against is reported: with
        no text supplied, every quotation; with texts supplied, a quotation that no supplied
        text holds and that no claim credits to a text (the parser found no named source for
        it), which the grounding check (INT-REQ-003) therefore never sees. With texts supplied,
        every quotation a parser recorded as credited to no text (the shared attribution rule's
        assumption, ``sources.uncredited_assumption``) is reported whatever its length, so a
        quotation the English, History or generic parser leaves without a source reference
        never goes silent. A from-memory label downgrades the finding to info only when it
        speaks of quotations or sits in the same sentence as the quotation; a label about dates
        and figures does not vouch for a quotation. Strings of a pasted JSON fragment are not
        quotations."""
        text, _removed = strip_json_spans(report.original_response)
        quoted = [inner.strip() for _s, _e, inner in find_quotation_spans(text) if len(inner.strip()) >= _MIN_QUOTE_CHARS]
        texts = list(report.supplied_texts)
        recorded: list[tuple[str, str]] = []  # (claim id, excerpt) the parser credited to no text
        if texts:
            docs = {t.document_id: t for t in texts}
            cited = {strip_trailing_punctuation(r.excerpt) for c in report.claims for r in c.source_refs if r.excerpt}
            seen = {strip_trailing_punctuation(q) for q in quoted}
            for c in report.claims:
                for a in c.assumptions:
                    ex = uncredited_excerpt(a)
                    if ex is None:
                        continue
                    recorded.append((c.claim_id, strip_trailing_punctuation(ex)))
                    if strip_trailing_punctuation(ex) not in seen:
                        seen.add(strip_trailing_punctuation(ex))
                        quoted.append(ex)
            quoted = [q for q in quoted if strip_trailing_punctuation(q) not in cited and not any(check_excerpt(q, d, docs).located for d in docs)]
        if not quoted:
            return []
        reported = {strip_trailing_punctuation(q) for q in quoted}
        recorded_ids = [cid for cid, ex in recorded if ex in reported]
        quote_label = bool(_QUOTE_MEMORY_LABEL_RE.search(text))
        sentences = [s for _pi, _si, s, _p in _sentences_with_paragraph(text)]
        labelled_in_sentence = all(any((q in s) and is_memory_label(s) for s in sentences) for q in quoted)
        shown = "; ".join("'" + (q[:_EXCERPT_CHARS] + ("..." if len(q) > _EXCERPT_CHARS else "")) + "'" for q in quoted[:4])
        claim_ids = list(dict.fromkeys([c.claim_id for c in report.claims if any(q in c.claim_text for q in quoted)] + recorded_ids))[:8]
        where = f"no supplied text holds them and their sentences credit them to none of the supplied texts [{', '.join(t.document_id for t in texts)}]" if texts else "no text was supplied"
        rule = "source integrity (quote from memory only with permission, and say so)"
        if quote_label or labelled_in_sentence:
            return [StructuralFinding(code="CORE-SRC-003", severity="info", message=f"{len(quoted)} quotation(s) quoted from memory by the specialist's own label; {where}, so they are unverified: {shown}", claim_ids=claim_ids, rule_source=rule)]
        why = "the from-memory label concerns dates and figures, not quotations" if has_memory_label else "no from-memory label is present"
        return [StructuralFinding(code="CORE-SRC-003", severity="warning", message=f"{len(quoted)} quotation(s) cannot be verified: {where} and {why}: {shown}", claim_ids=claim_ids, rule_source=rule)]

    @staticmethod
    def _misattributed_quotations(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-SRC-005: a quotation that the sentence attributes to a named source (a
        supplied text's author or title, a peer agent such as 'the History specialist',
        'the poem' when one non-peer text was supplied) with a saying verb, but whose
        words occur only in a different supplied text. The words are real; the credit
        is wrong, and a reader of the receipt must see which document actually holds
        them. In a reporting clause ('The English specialist argues that Blake presents
        ... "..."') the outer speaker is the credited source. When the sentence names a
        second source before the quotation and that source holds the words, the credit
        is ambiguous: a warning naming both, not an error. A quotation found in no text is
        left to the grounding check (INT-REQ-003) or, when uncredited, to CORE-SRC-003."""
        texts = list(report.supplied_texts)
        if not texts:
            return []
        names = _source_names(texts)
        out: list[StructuralFinding] = []
        seen: set[tuple[str, str]] = set()
        rule = "source integrity (attribute every quotation to the text that holds it; a colleague's words are not the author's and the author's are not the colleague's)"
        for _pi, _si, sent, _para in _sentences_with_paragraph(report.original_response):
            sent, _removed = strip_json_spans(sent)
            spans = [(s, e, inner.strip()) for s, e, inner in find_quotation_spans(sent) if len(inner.strip()) >= 4]
            if not spans:
                continue
            for (_s, _e, excerpt), attributed in zip(spans, _attributions(sent, spans, names)):
                if attributed is None:
                    continue
                doc_id, label, others = attributed
                located = sorted(t.document_id for t in texts if find_quotation(excerpt, t.text, document_id=t.document_id))
                if not located or doc_id in located:
                    continue
                key = (excerpt, doc_id)
                if key in seen:
                    continue
                seen.add(key)
                shown = excerpt[:_EXCERPT_CHARS] + ("..." if len(excerpt) > _EXCERPT_CHARS else "")
                claim_ids = _claims_for_excerpt(report, sent, excerpt, [x for _s2, _e2, x in spans])[:8]
                competing = [(d, l) for d, l in others if d in located]
                if competing:
                    both = " and ".join(f"{l} ({d})" for d, l in [(doc_id, label), *competing])
                    out.append(StructuralFinding(code="CORE-SRC-005", severity="warning",
                                                 message=f"quotation '{shown}' is credited in its sentence to {label} ({doc_id}) but the sentence also names {', '.join(l + ' (' + d + ')' for d, l in competing)}, and the words occur only in {', '.join(located)}: the credit is ambiguous between {both}; the words are genuine",
                                                 claim_ids=claim_ids, rule_source=rule))
                    continue
                out.append(StructuralFinding(code="CORE-SRC-005", severity="error",
                                             message=f"quotation '{shown}' is attributed in its sentence to {label} ({doc_id}) but occurs only in {', '.join(located)}: the words are genuine, the source credited is not the one that holds them",
                                             claim_ids=claim_ids, rule_source=rule))
        return out

    @staticmethod
    def _unbalanced_quotation_marks(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-SRC-004: a paragraph whose double quotation marks (straight, curly, mixed,
        guillemets) cannot be paired; the quotation at the dangling mark could not be
        delimited, so it was not checked against any text. The dangling mark is located by
        context (``markdown.dangling_quote_offset``), so the spans the writer did delimit
        around it are still checked."""
        out: list[StructuralFinding] = []
        for pi, para in _paragraphs(report.original_response):
            para, _removed = strip_json_spans(para)
            offset = dangling_quote_offset(para)
            if offset is None and not unbalanced_double_quotes(para):
                continue
            if offset is None:
                offset = max(para.rfind(ch) for ch in ('"', "“", "«", "„"))
            dangling = para[offset + 1:].strip() if offset >= 0 else ""
            shown = dangling[:_EXCERPT_CHARS] + ("..." if len(dangling) > _EXCERPT_CHARS else "")
            out.append(StructuralFinding(code="CORE-SRC-004", severity="warning", message=f"paragraph {pi} has an unbalanced quotation mark; the quotation opening at '{shown}' could not be delimited and was not checked against any text", claim_ids=_claims_mentioning(report, dangling[:60])[:8], rule_source="source integrity (quote exactly; every quotation must be checkable)"))
        return out

    @staticmethod
    def _undecided_chronology(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-CHR-001: a sentence orders two dated events but the pair could not be
        decided (the only date before the cue sits in an aside about the subject, a year is
        not stated, or both events fall in the same month with no days / the same year with
        no months). The order was stated and not checked; silence would hide that."""
        out: list[StructuralFinding] = []
        for pi, si, sent, para in _sentences_with_paragraph(report.original_response):
            for rel in chronology_relations(sent, para):
                if rel.decided:
                    continue
                out.append(StructuralFinding(code="CORE-CHR-001", severity="warning",
                                             message=f"paragraph {pi}, sentence {si} orders two dated events ('{rel.cue}': {rel.later_text} later than {rel.earlier_text}) but the order could not be decided: {rel.reason}; the stated order was not checked",
                                             claim_ids=_claims_mentioning(report, sent)[:8], rule_source="chronology (exact, dated items): a stated order that cannot be paired is reported, not skipped"))
        return out

    @staticmethod
    def _undecided_arithmetic(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-QNT-001: a stated derived figure ('a rise of 50 per cent', 'tripled', 'a change of
        0 per cent') or a relation over dated figures ('rose in each year', 'the greatest rise of the
        period') that no engine problem could be built for: the units of its pair cannot be compared,
        or no pair stands in its clause and the paragraph's dated series does not supply one (none,
        several, or a year that cannot be read). The arithmetic was stated and not checked; silence
        would hide that (``quant.undecided_quant_statements``)."""
        out: list[StructuralFinding] = []
        grouped: dict[tuple[int, int, str], list] = {}
        for u in undecided_quant_statements(report.original_response):
            grouped.setdefault((u.paragraph, u.sentence, u.reason), []).append(u)
        for (pi, si, reason), items in grouped.items():
            phrases = "', '".join(dict.fromkeys(u.phrase[:120] for u in items))
            out.append(StructuralFinding(code="CORE-QNT-001", severity="warning",
                                         message=f"paragraph {pi}, sentence {si} states a derived figure or a relation over dated figures ('{phrases}') that could not be checked: {reason[:600]}; the stated arithmetic was not checked",
                                         claim_ids=_claims_mentioning(report, items[0].sentence_text)[:8], rule_source="numeric self-consistency: a stated change that cannot be bound to its figures is reported, not skipped"))
        return out

    @staticmethod
    def _self_certification(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-SELF-001: verification-status vocabulary in the response body. An agent's
        statement about its own checking is advisory and ignored; status comes only from
        signed engine results. The message never repeats the certifying words."""
        out: list[StructuralFinding] = []
        seen: set[str] = set()
        for pi, si, sent, _para in _sentences_with_paragraph(report.original_response):
            if not SELF_CERT_RE.search(sent):
                continue
            key = " ".join(sent.split())
            if key in seen:
                continue
            seen.add(key)
            out.append(StructuralFinding(code="CORE-SELF-001", severity="warning", message=f"paragraph {pi}, sentence {si} contains verification-status language (an agent certifying its own output or imitating a channel receipt); agent self-reports are advisory and ignored, and no claim in that sentence counts as material", claim_ids=_claims_mentioning(report, sent)[:8], rule_source="architecture: agent self-reports are advisory; the Overseer trusts only signed engine results"))
        return out

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return _quant_formal(report, "core") + _chronology_formal(report, "core")


_ESSAY_BAND_WORDS = 800
#: The request asks for a verdict in words other than a command term ('give a judgement on which effect mattered most').
_JUDGEMENT_DEMAND_RE = re.compile(r"\b(?:judge|judg(?:e)?ments?|verdict|weigh(?:ing)? up|on balance|which [^.?!]{0,60}\b(?:mattered|matters) most)\b", re.IGNORECASE)


def request_demands_judgement(request_text: str) -> bool:
    """True when some sentence of the request carries a level-3 verdict command term
    (evaluate, discuss, to what extent, assess, examine, justify, recommend) or asks for a
    judgement in plain words. An 'outline' or 'describe' task (level 1-2) and a level-3 term
    with no verdict ('analyse') do not demand the History pack's judgement move."""
    from ..channel.request_parser import LEVEL3_VERDICT_TERMS, detect_command_term
    for sent in _split_sentences(request_text.strip()):
        term, level = detect_command_term(sent)
        if level == 3 and term in LEVEL3_VERDICT_TERMS:
            return True
    return bool(_JUDGEMENT_DEMAND_RE.search(request_text))


def request_sets_word_bound(request_text: str) -> bool:
    from ..channel.request_parser import extract_constraints
    return any(c.kind in ("max_words", "min_words") for c in extract_constraints(request_text))


class HistoryPack:
    name = "history"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        try:
            from ..adapters.history_specialist.structural import structural_checks
        except Exception:
            return []
        findings = structural_checks(report)
        if request_text and self._request_bounds_below_essay_band(request_text):
            findings = [x for x in findings if x.code != "HI-STR-004"]  # the request set a shorter deliverable; the exam-length guide does not apply
        if request_text and not request_demands_judgement(request_text):
            findings = [x for x in findings if x.code != "HI-STR-001"]  # an outline/describe task asks for no verdict; the judgement-move rule does not apply
        return findings

    @staticmethod
    def _request_bounds_below_essay_band(request_text: str) -> bool:
        from ..channel.request_parser import extract_constraints
        for c in extract_constraints(request_text):
            if c.kind == "max_words" and c.value is not None and int(c.value) < _ESSAY_BAND_WORDS:
                return True
            if c.kind == "max_paragraphs" and c.value is not None and int(c.value) <= 2:
                return True
        return False

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []  # chronology and numeric self-consistency run in CorePack for every subject


class EnglishPack:
    name = "english"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        try:
            from ..adapters.english_specialist.structural import structural_checks
        except Exception:
            return []
        try:
            findings = list(structural_checks(report))
        except Exception as exc:
            return [StructuralFinding(code="ES-INTERNAL-001", severity="warning", message=f"the English integrity pack failed internally ({type(exc).__name__}); its findings are missing from this receipt and the router must not treat the pack as passed", rule_source="hub integrity (a failing pack is reported, never silently skipped)")]
        if request_text and request_sets_word_bound(request_text):
            findings = [x for x in findings if x.code != "ES-STR-002"]  # the task set a word count; the working paragraph-length target does not apply
        return findings

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []


class PsychologyPack:
    """Studies must be grounded (name + year is an attribution, not evidence); figures must be self-consistent."""
    name = "psychology"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        for c in report.claims:
            for m in _STUDY_RE.finditer(c.claim_text):
                if not c.source_refs:
                    f.append(StructuralFinding(code="PS-SRC-001", severity="warning", message=f"study attribution {m.group(0)!r} has no knowledge-document or library grounding", claim_ids=[c.claim_id], rule_source="blueprint core operation (Psychology: Claim -> Study -> Link -> Evaluation); sources.md L5 (working rule)"))
            if re.search(r"\b(significant(?:ly)?|statistically)\b", c.claim_text, re.IGNORECASE) and not _PCT_RE.search(c.claim_text) and not re.search(r"\bp\s*[<=>]\s*0?\.\d+", c.claim_text):
                f.append(StructuralFinding(code="PS-STR-001", severity="info", message="'significant' used without a figure or p-value", claim_ids=[c.claim_id], rule_source="command terms C7 (quantities checked in parts; working rule)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []  # numeric self-consistency comes from CorePack


class EconomicsPack:
    name = "economics"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        text = report.original_response.lower()
        if "diagram" in text and not re.search(r"\b(shift|curve|axis|equilibrium|intersect)", text):
            f.append(StructuralFinding(code="EC-STR-001", severity="info", message="a diagram is mentioned but no curve, shift or equilibrium is described", rule_source="blueprint core operation (Economics: Define -> Model/Diagram -> Mechanism -> Apply -> Evaluate); working rule"))
        for c in report.claims:
            if re.search(r"\belasticity\b", c.claim_text, re.IGNORECASE) and not re.search(r"\d", c.claim_text):
                f.append(StructuralFinding(code="EC-STR-002", severity="info", message="elasticity asserted without a value or the percentage changes it is computed from", claim_ids=[c.claim_id], rule_source="command terms C7 (working rule)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """Elasticity = %change in quantity / %change in price when all three are stated."""
        out: list[FormalCheck] = []
        n = 0
        for sent in _split_sentences(report.original_response):
            m = re.search(r"elasticity[^.]{0,80}?(?:is|was|of|=|equals)\s*(-?\d+(?:\.\d+)?)", sent, re.IGNORECASE)
            pcts = _PCT_RE.findall(sent)
            if m and len(pcts) >= 2:
                n += 1
                from fractions import Fraction
                from ..ir.schema import Problem
                stated = Fraction(m.group(1)).__abs__()
                q, p = Fraction(pcts[0]), Fraction(pcts[1])
                if "price" in sent.lower()[: sent.lower().find(pcts[0])] if pcts[0] in sent else False:
                    q, p = p, q  # price change named first
                lo, hi = stated * Fraction(19, 20), stated * Fraction(21, 20)
                R = lambda x: {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}
                V = lambda s: {"op": "var", "name": s}
                ratio = {"op": "div", "left": V("dq"), "right": R(p)}
                prob = {"problem_id": f"ped-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:elasticity-{n}", "query": "entailment",
                        "symbols": [{"name": "dq", "sort": "Real", "meaning": "percentage change in quantity"}, {"name": "dp", "sort": "Real", "meaning": "percentage change in price"}],
                        "premises": [{"id": "DQ", "expr": {"op": "eq", "left": V("dq"), "right": R(q)}, "grounding": {"kind": "supplied_text", "verified": True}},
                                     {"id": "DP", "expr": {"op": "eq", "left": V("dp"), "right": R(p)}, "grounding": {"kind": "supplied_text", "verified": True}}],
                        "conclusion": {"id": "PED", "expr": {"op": "and", "args": [{"op": "ge", "left": ratio, "right": R(lo)}, {"op": "le", "left": ratio, "right": R(hi)}]}, "label": f"stated elasticity {stated}"}}
                out.append(FormalCheck(check_id=f"economics-elasticity-{n}", kind="elasticity", description=sent.strip()[:160], problem=Problem.model_validate(prob)))
        return out


class BusinessPack:
    name = "business_management"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        for c in report.claims:
            if re.search(r"\b(recommend|should)\b", c.claim_text, re.IGNORECASE) and c.claim_role in ("judgement", "point", "link") and not c.supporting_claim_ids:
                f.append(StructuralFinding(code="BM-STR-001", severity="info", message="a recommendation with no supporting claims recorded", claim_ids=[c.claim_id], rule_source="blueprint core operation (Business: Define -> Apply -> Analyse with the tool -> Evaluate); working rule"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """Margins stated with the figures they are computed from: margin = profit / revenue."""
        out: list[FormalCheck] = []
        n = 0
        for sent in _split_sentences(report.original_response):
            m = re.search(r"(?:profit|gross|net)\s+margin[^.]{0,60}?(\d{1,3}(?:\.\d+)?)\s*(?:per cent|percent|%)", sent, re.IGNORECASE)
            nums = re.findall(r"(?:profit|revenue|sales)\s+of\s+(?:\$|£|€)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|m|thousand|k)?", sent, re.IGNORECASE)
            if m and len(nums) >= 2:
                n += 1
                from fractions import Fraction
                from ..ir.schema import Problem
                scale = {"million": 10**6, "m": 10**6, "thousand": 10**3, "k": 10**3}
                vals = [Fraction(v.replace(",", "")) * scale.get((u or "").lower(), 1) for v, u in nums[:2]]
                low = sent.lower()
                profit, revenue = (vals[0], vals[1]) if low.find("profit") < low.find("revenue" if "revenue" in low else "sales") else (vals[1], vals[0])
                stated = Fraction(m.group(1))
                lo, hi = stated * Fraction(19, 20), stated * Fraction(21, 20)
                R = lambda x: {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}
                V = lambda s: {"op": "var", "name": s}
                margin = {"op": "mul", "args": [R(Fraction(100)), {"op": "div", "left": V("profit"), "right": R(revenue)}]}
                prob = {"problem_id": f"margin-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:margin-{n}", "query": "entailment",
                        "symbols": [{"name": "profit", "sort": "Real"}, {"name": "revenue", "sort": "Real"}],
                        "premises": [{"id": "PROFIT", "expr": {"op": "eq", "left": V("profit"), "right": R(profit)}, "grounding": {"kind": "supplied_text", "verified": True}},
                                     {"id": "REVENUE", "expr": {"op": "eq", "left": V("revenue"), "right": R(revenue)}, "grounding": {"kind": "supplied_text", "verified": True}}],
                        "conclusion": {"id": "MARGIN", "expr": {"op": "and", "args": [{"op": "ge", "left": margin, "right": R(lo)}, {"op": "le", "left": margin, "right": R(hi)}]}, "label": f"stated margin {stated} per cent"}}
                out.append(FormalCheck(check_id=f"business-margin-{n}", kind="margin", description=sent.strip()[:160], problem=Problem.model_validate(prob)))
        return out


class GenericPack:
    name = "generic"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        ids = {c.claim_id for c in report.claims}
        for c in report.claims:
            missing = [s for s in c.supporting_claim_ids if s not in ids]
            if missing:
                f.append(StructuralFinding(code="GEN-STR-001", severity="error", message=f"claim cites unknown supporting claims {missing}", claim_ids=[c.claim_id]))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []
