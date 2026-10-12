"""Integrity packs: the subject-specific checks each branch carries, plus the core pack
every branch runs. Deterministic findings cite the pack's working rules; formal checks
are problems the engine decides about the report's own statements."""
from __future__ import annotations

import re
from functools import lru_cache
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
#: The most formal checks the core pack sends to the engine for one transmission (arithmetic first, then chronology). An answer far
#: beyond any request's length could otherwise hold the hub for seconds; the statements beyond the limit are named, never dropped
#: silently (CORE-QNT-001 / CORE-CHR-001: 'not checked: the check limit was reached').
MAX_FORMAL_CHECKS = 500
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
    r"admits?|admitted|identifies|identified|suggests?|suggested|implies|implied|concedes?|conceded|confesses|confessed|declares?|declared|recalls?|recalled|explains?|"
    r"in (?:his|her|its|their) words|(?:'s|’s) (?:words?|phrase|phrasing|paragraph|account|setting|description|point|claim|note|warning|line|lines|verdict))\b",
    re.IGNORECASE,
)
#: A credit to a source that was NOT supplied to this agent: '<Name>'s speaker / poem / narrator / lines' or '<Name> writes / admits / says'
#: ('Hardy's speaker himself admits that ...', 'Hardy's poem identifies ...'), and, when no literary text was supplied, 'the poem', 'the poet',
#: 'the speaker', 'the narrator'. Words credited this way that occur only in a colleague's own prose are the colleague's (CORE-SRC-005).
_UNSUPPLIED_WORK_RE = re.compile(r"\b([A-ZÀ-ÖØ-Þ][\w'’-]+(?:\s+[A-ZÀ-ÖØ-Þ][\w'’-]+)?)(?:'s|’s)\s+(?:own\s+)?(speaker|poem|narrator|persona|poet|monologue|lines?|verse|stanza|text|novel|play|story|words|soldier|protagonist|character|sonnet|ode)\b")
_UNSUPPLIED_AUTHOR_RE = re.compile(r"\b([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{2,})\s+(?:himself\s+|herself\s+|itself\s+)?(?=(?:writes|wrote|says|said|admits|admitted|identifies|identified|suggests|suggested|calls|called|describes|described|presents|presented|claims|claimed|insists|insisted|states|stated|declares|declared)\b)")
_UNSUPPLIED_GENERIC = ("the poem", "the poet", "the speaker", "the narrator", "the persona", "the sonnet")
_NOT_A_NAME = frozenset({"The", "This", "That", "These", "Those", "It", "Its", "He", "She", "They", "We", "I", "Against", "In", "On", "By", "And", "But", "Yet", "So", "Here", "There", "When", "While"})
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
    split with the shared abbreviation-aware splitter (``c.``, ``approx.``, initials never end a sentence).
    Memoised per text (a bounded cache): every check of the core pack walks the same sentences."""
    return list(_sentences_with_paragraph_cached(text))


@lru_cache(maxsize=32)
def _sentences_with_paragraph_cached(text: str) -> tuple[tuple[int, int, str, str], ...]:
    out: list[tuple[int, int, str, str]] = []
    for pi, para in _paragraphs(text):
        for si, sent in enumerate(_split_sentences(para), start=1):
            out.append((pi, si, sent.strip(), para))
    return tuple(out)


def _chronology_formal(report: SpecialistReport, prefix: str, limit: Optional[int] = None) -> list[FormalCheck]:
    """Every dated relation a sentence asserts becomes an entailment problem. An ordering
    ('after', 'before', 'followed', 'preceded', with or without 'by', and a duration 'ran from D1
    to D2'): the event the sentence places later must have the later day ordinal
    ((year*12+month)*32+day). A containment ('December 1899, including ... on 11 December', 'The
    1840s, which included the Railway Mania of 1845 to 1847'): the inner interval of day ordinals
    lies within the outer one (the items of one list, 'including A in d1, B in d2 and C in d3', are one
    problem whose conclusion holds every item inside the period, and its description names first the
    items the dates place outside); after 'during' an inner range must meet the outer period. A same-year
    relation ('the poem's 1902 date falls at the war's close'): the two years are equal. The
    relations come from ``history_specialist.chronology.chronology_relations``, the extractor the
    History proxy ``HI-CHR-001`` also reads, with the paragraph as context for a date whose year the
    sentence does not state, so the proxy and the engine never disagree. A relation the extractor
    could not pair (an aside date, an unstated year, two events in the same month with no days) is
    not a problem here; ``CorePack`` reports it as ``CORE-CHR-001``. Each check names the claims
    whose text holds the sentence. With ``limit``, only the first ``limit`` units are built (the rest are named by the core pack's
    check-limit finding), so an oversized answer costs no work beyond the limit."""
    from ..ir.schema import Problem
    out: list[FormalCheck] = []
    n = 0
    grounding = {"kind": "supplied_text", "verified": True}

    def var(name: str) -> dict:
        return {"op": "var", "name": name}

    def eq(name: str, value: int, label: str, pid: str) -> dict:
        return {"id": pid, "expr": {"op": "eq", "left": var(name), "right": {"op": "int", "value": str(value)}}, "label": label[:1000], "grounding": grounding}

    units = _chronology_units(report.original_response)
    for sent, para, group in (units if limit is None else units[: max(0, limit)]):
        rel = group[0]
        ordinal_note = "as a day ordinal ((year*12+month)*32+day)"
        if len(group) > 1:
            # 'including Tanganyika in 1961, Kenya in 1963 and Botswana in 1966': one problem, every item inside the one outer period
            olo, ohi = group[0].bounds[2], group[0].bounds[3]
            symbols = [{"name": "outer_start", "sort": "Int", "meaning": f"first day of {rel.earlier_text} {ordinal_note}"},
                       {"name": "outer_end", "sort": "Int", "meaning": f"last day of {rel.earlier_text} {ordinal_note}"}]
            premises = [eq("outer_start", olo, f"{rel.earlier_text} begins", "D0S"), eq("outer_end", ohi, f"{rel.earlier_text} ends", "D0E")]
            args = []
            for i, r in enumerate(group, start=1):
                ilo, ihi = r.bounds[0], r.bounds[1]
                symbols += [{"name": f"inner{i}_start", "sort": "Int", "meaning": f"first day of {r.later_text} {ordinal_note}"},
                            {"name": f"inner{i}_end", "sort": "Int", "meaning": f"last day of {r.later_text} {ordinal_note}"}]
                premises += [eq(f"inner{i}_start", ilo, f"{r.later_text} begins", f"D{i}S"), eq(f"inner{i}_end", ihi, f"{r.later_text} ends", f"D{i}E")]
                args += [{"op": "ge", "left": var(f"inner{i}_start"), "right": var("outer_start")}, {"op": "le", "left": var(f"inner{i}_end"), "right": var("outer_end")}]
            concl = {"op": "and", "args": args}
            items = ", ".join(r.later_text for r in group[:-1]) + f" and {group[-1].later_text}"
            outside = [r.later_text for r in group if r.violated]
            label = f"{items} each lie within '{rel.earlier_text}', as the sentence's '{rel.cue}' asserts"
            reasons = "; ".join(dict.fromkeys(r.reason for r in group if r.reason))
            if reasons:
                label += f" ({reasons})"
            n += 1
            problem = {"problem_id": f"chron-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:chronology-{n}", "query": "entailment",
                       "symbols": symbols, "premises": premises, "conclusion": {"id": "ORDER", "expr": concl, "label": label[:1000]}}
            statement = "; ".join(r.statement for r in (group if not outside else [r for r in group if r.violated] + [r for r in group if not r.violated]))
            out.append(FormalCheck(check_id=f"{prefix}-chronology-{n}", kind="chronology",
                                   description=(f"stated containment of dated events ('{rel.cue}': {statement})"
                                                + (f" [read by date: {', '.join(outside)} outside {rel.earlier_text}]" if outside else "")
                                                + f": {_excerpt_around(sent.strip(), rel.cue)}"),
                                   problem=Problem.model_validate(problem), claim_ids=tuple(_claims_for_statement(report, sent, rel.cue))))
            continue
        if rel.kind in ("within", "overlaps") and rel.bounds:
            ilo, ihi, olo, ohi = rel.bounds
            symbols = [{"name": "inner_start", "sort": "Int", "meaning": f"first day of {rel.later_text} {ordinal_note}"},
                       {"name": "inner_end", "sort": "Int", "meaning": f"last day of {rel.later_text} {ordinal_note}"},
                       {"name": "outer_start", "sort": "Int", "meaning": f"first day of {rel.earlier_text} {ordinal_note}"},
                       {"name": "outer_end", "sort": "Int", "meaning": f"last day of {rel.earlier_text} {ordinal_note}"}]
            premises = [eq("inner_start", ilo, f"{rel.later_text} begins", "D1"), eq("inner_end", ihi, f"{rel.later_text} ends", "D2"),
                        eq("outer_start", olo, f"{rel.earlier_text} begins", "D3"), eq("outer_end", ohi, f"{rel.earlier_text} ends", "D4")]
            if rel.kind == "within":
                concl = {"op": "and", "args": [{"op": "ge", "left": var("inner_start"), "right": var("outer_start")}, {"op": "le", "left": var("inner_end"), "right": var("outer_end")}]}
                label = f"'{rel.later_text}' lies within '{rel.earlier_text}', as the sentence's '{rel.cue}' asserts"
            else:
                concl = {"op": "and", "args": [{"op": "le", "left": var("inner_start"), "right": var("outer_end")}, {"op": "ge", "left": var("inner_end"), "right": var("outer_start")}]}
                label = f"'{rel.later_text}' falls during '{rel.earlier_text}', as the sentence's '{rel.cue}' asserts"
            kind_word = "containment"
        elif rel.kind == "same_year" and rel.bounds:
            symbols = [{"name": "stated_year", "sort": "Int", "meaning": f"the year of {rel.later_text}"},
                       {"name": "reference_year", "sort": "Int", "meaning": f"the year of {rel.earlier_text}"}]
            premises = [eq("stated_year", rel.bounds[0], rel.later_text, "D1"), eq("reference_year", rel.bounds[1], rel.earlier_text, "D2")]
            concl = {"op": "eq", "left": var("stated_year"), "right": var("reference_year")}
            label = f"'{rel.later_text}' falls in the year of {rel.earlier_text}, as the sentence's '{rel.cue}' asserts"
            kind_word = "same year"
        elif rel.later_ordinal is not None and rel.earlier_ordinal is not None:
            symbols = [{"name": "later_event", "sort": "Int", "meaning": f"{rel.later_text} as a day ordinal ((year*12+month)*32+day; an unstated month or day counts 0)"},
                       {"name": "earlier_event", "sort": "Int", "meaning": f"{rel.earlier_text} as a day ordinal ((year*12+month)*32+day; an unstated month or day counts 0)"}]
            premises = [eq("later_event", rel.later_ordinal, rel.later_text, "D1"), eq("earlier_event", rel.earlier_ordinal, rel.earlier_text, "D2")]
            concl = {"op": "gt", "left": var("later_event"), "right": var("earlier_event")}
            label = f"'{rel.later_text}' is later than '{rel.earlier_text}', as the sentence's '{rel.cue}' asserts"
            kind_word = "order"
        else:
            continue
        n += 1
        if rel.reason:
            label += f" ({rel.reason})"
        problem = {"problem_id": f"chron-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:chronology-{n}", "query": "entailment",
                   "symbols": symbols, "premises": premises, "conclusion": {"id": "ORDER", "expr": concl, "label": label[:1000]}}
        out.append(FormalCheck(check_id=f"{prefix}-chronology-{n}", kind="chronology",
                               description=f"stated {kind_word} of dated events ('{rel.cue}': {rel.statement}): {_excerpt_around(sent.strip(), rel.cue)}", problem=Problem.model_validate(problem),
                               claim_ids=tuple(_claims_for_statement(report, sent, rel.cue))))
    return out


def _chronology_units(text: str) -> list[tuple[str, str, list]]:
    """The decided dated relations of ``text`` as the units the engine checks: ``(sentence, paragraph, relations)``. The items of one
    containment list (one cue, one outer period: 'including A in d1, B in d2 and C in d3') are one unit, so a list costs one engine
    call; every other relation is a unit of its own."""
    units: list[tuple[str, str, list]] = []
    for _pi, _si, sent, para in _sentences_with_paragraph(text):
        lists: dict[tuple, list] = {}
        for rel in chronology_relations(sent, para):
            if not rel.decided:
                continue
            if rel.kind == "within" and rel.bounds:
                key = (rel.cue, rel.earlier_text, rel.bounds[2], rel.bounds[3])
                if key in lists:
                    lists[key].append(rel)
                    continue
                lists[key] = [rel]
                units.append((sent, para, lists[key]))
                continue
            units.append((sent, para, [rel]))
    return units


def _quant_formal(report: SpecialistReport, prefix: str, limit: Optional[int] = None) -> list[FormalCheck]:
    """The report's own arithmetic as engine problems. A relation stated across sentences (a
    derived figure, 'rose in each year', 'the greatest rise' whose figures stand in another
    sentence of the paragraph) says in its description where its year and figures were read.
    With ``limit``, only the first ``limit`` checks are built (their claims named), the rest being
    the core pack's check-limit finding."""
    out: list[FormalCheck] = []
    checks = extract_quant_checks(report.original_response, request_id=report.request_id, claim_id=f"{report.report_id}:{prefix}")
    for qc in (checks if limit is None else checks[: max(0, limit)]):
        description = f"report's own arithmetic: {_excerpt_around(qc.sentence, qc.phrase)}" + (f" [{qc.basis[:400]}]" if qc.basis else "") + (f" [{qc.rule}]" if qc.rule else "")
        out.append(FormalCheck(check_id=f"{prefix}-{qc.check_id}", kind=qc.kind, description=description, problem=qc.problem,
                               claim_ids=tuple(_claims_for_statement(report, qc.sentence, qc.phrase))))
    return out


def _excerpt_around(statement: str, phrase: str, width: int = 160) -> str:
    """``statement`` as quoted in a check's description: whole when short, otherwise a window of ``width`` characters around the
    phrase the check reads, so a false phrase at the end of a long unpunctuated block is quoted, not cut off."""
    statement = " ".join(statement.split())
    if len(statement) <= width:
        return statement
    at = statement.find(" ".join(phrase.split())) if phrase else -1
    if at < 0:
        return statement[:width] + "..."
    start = max(0, min(at - width // 3, len(statement) - width))
    return ("..." if start else "") + statement[start: start + width] + ("..." if start + width < len(statement) else "")


#: report identity -> (the report, its claims' texts with whitespace collapsed): every formal check and undecided finding of one transmission
#: names its claims from the same texts, so they are normalised once per report, not once per check (bounded: the last few reports).
_NORMALISED_TEXTS: dict[int, tuple[SpecialistReport, list[tuple[str, str]]]] = {}


def _normalised_claim_texts(report: SpecialistReport) -> list[tuple[str, str]]:
    hit = _NORMALISED_TEXTS.get(id(report))
    if hit is not None and hit[0] is report and len(hit[1]) == len(report.claims):
        return hit[1]
    texts = [(c.claim_id, " ".join(c.claim_text.split())) for c in report.claims]
    if len(_NORMALISED_TEXTS) >= 8:
        _NORMALISED_TEXTS.pop(next(iter(_NORMALISED_TEXTS)))
    _NORMALISED_TEXTS[id(report)] = (report, texts)
    return texts


def _claims_for_statement(report: SpecialistReport, statement: str, phrase: str = "") -> list[str]:
    """The delivered claims a formal check about ``statement`` names: the claims whose text holds the statement; else, when the
    statement spans several claims (a long block the parser cut where the check did not), the claims inside it that hold the
    phrase the check reads; else every claim holding the phrase."""
    stmt = " ".join(statement.split())
    key = " ".join(phrase.split())
    texts = _normalised_claim_texts(report)
    holding = [cid for cid, t in texts if stmt and stmt in t]
    if holding:
        return holding[:8]
    inside = [cid for cid, t in texts if t and t in stmt and (not key or key in t)]
    if inside:
        return inside[:8]
    return [cid for cid, t in texts if key and key in t][:8]


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


def _quote_key(text: str) -> str:
    """A quotation compared with an excerpt: whitespace collapsed, quotation marks and trailing punctuation stripped, case folded."""
    return strip_trailing_punctuation(" ".join(text.split()).strip(" '\"“”‘’«»„")).casefold()


def _is_english_subject(subject: Optional[str]) -> bool:
    from ..translate.subjects import resolve_profile
    try:
        return resolve_profile(subject).key in ("english_a_literature", "english_a_language_literature", "literature_performance", "language_a_other", "english")
    except Exception:
        return False


_UNSUPPLIED = "unsupplied:"


def _with_unsupplied_credits(sentence: str, spans: list[tuple[int, int, str]], names: dict[str, tuple[str, str]], texts: list[SuppliedText]) -> dict[str, tuple[str, str]]:
    """``names`` plus the sources ``sentence`` credits that were not supplied to this agent ('Hardy's speaker', 'Hardy's poem',
    'Pakenham writes', and 'the poem' when no literary text was supplied), each under a pseudo document id; a name already
    among the supplied texts' names is left to them."""
    prose = list(sentence)
    for s, e, _inner in spans:
        for i in range(s, e):
            prose[i] = " "
    text = "".join(prose)
    low_names = set(names)
    extra: dict[str, tuple[str, str]] = {}
    for m in _UNSUPPLIED_WORK_RE.finditer(text):
        name = m.group(1)
        if name.split()[0] in _NOT_A_NAME or name.lower() in low_names or name.split()[-1].lower() in low_names:
            continue
        phrase = " ".join(m.group(0).split()).lower()
        extra.setdefault(phrase, (_UNSUPPLIED + phrase, " ".join(m.group(0).split())))
    for m in _UNSUPPLIED_AUTHOR_RE.finditer(text):
        name = m.group(1)
        if name in _NOT_A_NAME or name.lower() in low_names:
            continue
        extra.setdefault(name.lower(), (_UNSUPPLIED + name.lower(), name))
    if not any(not _is_peer_text(t) for t in texts) and not extra and not _named_mentions(text, names):
        # 'the poem', 'the speaker' only when the sentence names no other source: 'The English specialist's paragraph identifies the
        # speaker's motive' credits the colleague, not the speaker
        for g in _UNSUPPLIED_GENERIC:
            if g not in low_names:
                extra.setdefault(g, (_UNSUPPLIED + g, g))
    if not extra:
        return names
    return {**extra, **names}


def _inside_peer_quotation(excerpt: str, doc: SuppliedText) -> bool:
    """True when ``excerpt`` is located in the colleague's text inside one of the colleague's own quotations (the colleague quoting
    the poem), so the words are the quoted author's, not the colleague's."""
    hit = find_quotation(excerpt, doc.text, document_id=doc.document_id)
    if hit is None:
        return False
    start, end = hit[0], hit[1]
    return any(s <= start and end <= e for s, e, _inner in find_quotation_spans(doc.text))


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
        disagreeing, disputed = self._guarded("quotation references", lambda: self._quotation_ref_disagreements(report), f) if report.supplied_texts else ([], frozenset())
        f += disagreeing or []
        f += self._guarded("unverifiable quotations", lambda: self._unverifiable_quotations(report, has_memory_label, disputed or frozenset()), f) or []
        if report.supplied_texts:
            f += self._guarded("misattributed quotations", lambda: self._misattributed_quotations(report), f) or []
        f += self._guarded("quotation marks", lambda: self._unbalanced_quotation_marks(report), f) or []
        f += self._guarded("self-certification", lambda: self._self_certification(report), f) or []
        f += self._guarded("chronology", lambda: self._undecided_chronology(report), f) or []
        f += self._guarded("arithmetic", lambda: self._undecided_arithmetic(report), f) or []
        f += self._guarded("support links", lambda: self._support_cycles(report), f) or []
        f += self._guarded("check limit", lambda: self._formal_overflow(report), f) or []
        return f

    @staticmethod
    def _formal_overflow(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-QNT-001 / CORE-CHR-001 for the stated relations beyond :data:`MAX_FORMAL_CHECKS`: they were read but not sent to the engine,
        so the receipt says so and names their claims rather than passing them silently."""
        text = report.original_response
        quant = extract_quant_checks(text, request_id=report.request_id, claim_id=f"{report.report_id}:core")
        chron = [(sent, group[0]) for sent, _para, group in _chronology_units(text)]
        if len(quant) + len(chron) <= MAX_FORMAL_CHECKS:
            return []
        out: list[StructuralFinding] = []
        rule = f"hub integrity: at most {MAX_FORMAL_CHECKS} formal checks per transmission; a stated relation beyond the limit is reported, not skipped"
        over_q = quant[MAX_FORMAL_CHECKS:]
        over_c = chron[max(0, MAX_FORMAL_CHECKS - len(quant)):]
        if over_q:
            ids = list(dict.fromkeys(cid for qc in over_q[:40] for cid in _claims_for_statement(report, qc.sentence, qc.phrase)))[:8]
            out.append(StructuralFinding(code="CORE-QNT-001", severity="warning", claim_ids=ids, rule_source=rule,
                                         message=f"{len(over_q)} statement(s) of the report's own arithmetic were not checked: the limit of {MAX_FORMAL_CHECKS} formal checks per "
                                                 f"transmission was reached (first unchecked: '{_excerpt_around(over_q[0].sentence, over_q[0].phrase, 120)}'); the stated arithmetic was not checked"))
        if over_c:
            ids = list(dict.fromkeys(cid for sent, rel in over_c[:40] for cid in _claims_for_statement(report, sent, rel.cue)))[:8]
            out.append(StructuralFinding(code="CORE-CHR-001", severity="warning", claim_ids=ids, rule_source=rule,
                                         message=f"{len(over_c)} dated relation(s) were not checked: the limit of {MAX_FORMAL_CHECKS} formal checks per transmission was reached "
                                                 f"(first unchecked: '{over_c[0][1].cue}': {over_c[0][1].statement}); the stated relations were not checked"))
        return out

    @staticmethod
    def _guarded(what: str, fn, out: list[StructuralFinding]):
        """Run one check of the core pack on its own: a check that fails internally adds CORE-INTERNAL-001 (error) naming it, and
        every other check still runs, so one failing extractor never discards the receipt's other findings."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - reported, never silent
            out.append(StructuralFinding(code="CORE-INTERNAL-001", severity="error",
                                         message=f"the core pack's {what} check failed internally ({type(exc).__name__}); its findings (and the formal checks built from "
                                                 f"the same reading) are missing from this receipt, and the router must not treat it as passed; the other checks ran",
                                         rule_source="hub integrity (a failing check is reported, never silently skipped)"))
            return None

    @staticmethod
    def _support_cycles(report: SpecialistReport) -> list[StructuralFinding]:
        """CORE-STR-001 (error): a claim that supports itself, or claims whose ``supporting_claim_ids`` form a cycle, in any delivered
        report on any branch, parsed or structured: none of them can be evidence for the others, so an argument the translator
        builds from them would be circular. The finding names the claims of each cycle once."""
        from ..adapters.generic_structured import generic_cycle_findings
        if not any(c.supporting_claim_ids for c in report.claims):
            return []
        rule = "argument structure: support links run from evidence to the point and to the judgement, never in a circle"
        return [StructuralFinding(code="CORE-STR-001", severity="error", message=x.message, claim_ids=list(x.claim_ids)[:16], rule_source=rule)
                for x in generic_cycle_findings(report, code="CORE-STR-001")][:16]

    @staticmethod
    def _quotation_ref_disagreements(report: SpecialistReport) -> tuple[list[StructuralFinding], frozenset]:
        """CORE-SRC-006 (error): a claim whose text quotes words that no supplied text holds, while the claim (or a claim it rests on)
        credits a supplied text through its source references and no reference or note records those words: the quotation in the
        claim and the excerpt its source reference carries disagree ('"Had we two but met"' in the text, 'Had he and I but met' in the
        reference), so the grounding check, which reads only the reference, would pass an altered quotation. On the English branch a
        quotation with no reference at all in a report on one literary text is credited to that text, as the English parser credits it
        (``attribute_excerpt``'s text under analysis). A parsed report never raises it: every quotation a parser reads is carried by a
        source reference or recorded in an assumption. Returns the findings and the quotations they name (kept out of CORE-SRC-003)."""
        docs = {t.document_id: t for t in report.supplied_texts}
        by_id = {c.claim_id: c for c in report.claims}
        literary = [d for d, t in docs.items() if not _is_peer_text(t)]
        text_under_analysis = literary[0] if len(literary) == 1 and _is_english_subject(report.subject) else None
        found: dict[str, dict] = {}
        # quotations a parser recorded in an assumption anywhere in the report (credited to no text, found in none): accounted for
        recorded = {_quote_key(ex) for c in report.claims for a in c.assumptions for ex in [uncredited_excerpt(a)] if ex}
        all_notes = " ".join(a for c in report.claims for a in c.assumptions).casefold()
        all_carried = {_quote_key(r.excerpt) for x in report.claims for r in x.source_refs if r.excerpt}
        for c in report.claims:
            if c.claim_role == "other":
                continue
            text, _removed = strip_json_spans(c.claim_text)
            quotes = [inner.strip() for _s, _e, inner in find_quotation_spans(text) if len(inner.strip()) >= 4]
            if not quotes:
                continue
            refs = [r for x in [c, *(by_id[i] for i in c.supporting_claim_ids if i in by_id)] for r in x.source_refs if r.excerpt and r.document_id in docs]
            for q in quotes:
                key = _quote_key(q)
                if (not key or key in recorded or key in all_carried or any(len(k) >= 8 and (k in key or key in k) for k in all_carried)
                        or " ".join(q.split()).casefold()[:60] in all_notes):
                    continue
                if any(check_excerpt(q, d, docs).located for d in docs):
                    continue  # genuine words: the grounding of the reference is the channel's
                if refs:
                    rec = found.setdefault(key, {"quote": q, "claims": [], "refs": refs, "how": "refs"})
                elif text_under_analysis is not None:
                    rec = found.setdefault(key, {"quote": q, "claims": [], "refs": [], "how": "text"})
                else:
                    continue
                rec["claims"].append(c.claim_id)
        out: list[StructuralFinding] = []
        rule = "source integrity (a claim's quotation must be the excerpt its source reference carries, and the excerpt must occur in the text credited)"
        for rec in found.values():
            shown = rec["quote"][:_EXCERPT_CHARS] + ("..." if len(rec["quote"]) > _EXCERPT_CHARS else "")
            if rec["how"] == "refs":
                cited = "; ".join(dict.fromkeys(f"'{r.excerpt[:_EXCERPT_CHARS]}' ({r.document_id})" for r in rec["refs"]))
                message = (f"claim(s) {', '.join(rec['claims'][:8])} quote '{shown}', which no supplied text holds, while their source references carry {cited}: "
                           f"the claim's quotation and its source reference disagree, so the reference's grounding does not vouch for the words the claim states")
            else:
                message = (f"claim(s) {', '.join(rec['claims'][:8])} quote '{shown}' with no source reference or note, in a report on one literary text "
                           f"({text_under_analysis}), which does not hold the words: an unlocated quotation of the text under analysis")
            out.append(StructuralFinding(code="CORE-SRC-006", severity="error", message=message, claim_ids=rec["claims"][:8], rule_source=rule))
        return out, frozenset(found)

    @staticmethod
    def _unverifiable_quotations(report: SpecialistReport, has_memory_label: bool, disputed: frozenset = frozenset()) -> list[StructuralFinding]:
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
            quoted = [q for q in quoted if strip_trailing_punctuation(q) not in cited and not any(check_excerpt(q, d, docs).located for d in docs) and _quote_key(q) not in disputed]
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
        by_id = {t.document_id: t for t in texts}
        by_claim = {c.claim_id: c.claim_text for c in report.claims}
        out: list[StructuralFinding] = []
        seen: set[tuple[str, str]] = set()
        rule = "source integrity (attribute every quotation to the text that holds it; a colleague's words are not the author's and the author's are not the colleague's)"
        for _pi, _si, sent, _para in _sentences_with_paragraph(report.original_response):
            sent, _removed = strip_json_spans(sent)
            spans = [(s, e, inner.strip()) for s, e, inner in find_quotation_spans(sent) if len(inner.strip()) >= 4]
            if not spans:
                continue
            sentence_names = _with_unsupplied_credits(sent, spans, names, texts)
            for (_s, _e, excerpt), attributed in zip(spans, _attributions(sent, spans, sentence_names)):
                if attributed is None:
                    continue
                doc_id, label, others = attributed
                located = sorted(t.document_id for t in texts if find_quotation(excerpt, t.text, document_id=t.document_id))
                if doc_id.startswith(_UNSUPPLIED):
                    # credited to an author or work this agent was not given: wrong only when the words are a colleague's own prose
                    own_prose = [d for d in located if _is_peer_text(by_id[d]) and not _inside_peer_quotation(excerpt, by_id[d])]
                    if not located or len(own_prose) != len(located) or (excerpt, doc_id) in seen:
                        continue
                    seen.add((excerpt, doc_id))
                    shown = excerpt[:_EXCERPT_CHARS] + ("..." if len(excerpt) > _EXCERPT_CHARS else "")
                    out.append(StructuralFinding(code="CORE-SRC-005", severity="error",
                                                 message=f"quotation '{shown}' is credited in its sentence to {label}, a source not supplied to this agent, but its words occur only in "
                                                         f"{', '.join(own_prose)}, in the colleague's own prose rather than in a quotation the colleague makes: a colleague's words are credited to {label}",
                                                 claim_ids=([c for c in _claims_mentioning(report, sent) if excerpt in by_claim.get(c, "")] or _claims_for_excerpt(report, sent, excerpt, [x for _s2, _e2, x in spans]))[:8],
                                                 rule_source=rule))
                    continue
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
                what = "orders two dated events" if rel.kind == "order" else "places a dated event within a dated period" if rel.kind in ("within", "overlaps") else "places a date at a point of a dated period"
                out.append(StructuralFinding(code="CORE-CHR-001", severity="warning",
                                             message=f"paragraph {pi}, sentence {si} {what} ('{rel.cue}': {rel.statement}) but the relation could not be decided: {rel.reason}; the stated relation was not checked",
                                             claim_ids=(_claims_for_statement(report, sent, rel.cue) or _claims_mentioning(report, sent))[:8],
                                             rule_source="chronology (exact, dated items): a stated order that cannot be paired is reported, not skipped"))
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
                                         claim_ids=(_claims_for_statement(report, items[0].sentence_text, items[0].phrase) or _claims_mentioning(report, items[0].sentence_text))[:8],
                                         rule_source="numeric self-consistency: a stated change that cannot be bound to its figures is reported, not skipped"))
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
        """The report's own arithmetic and chronology as engine problems, each extractor on its own (a failure of one is reported by
        :meth:`checks` as CORE-INTERNAL-001, which reads the same extraction, and never discards the other), capped at
        :data:`MAX_FORMAL_CHECKS` per transmission (the rest are named by CORE-QNT-001 / CORE-CHR-001 in :meth:`checks`)."""
        out: list[FormalCheck] = []
        for build in (_quant_formal, _chronology_formal):
            if len(out) >= MAX_FORMAL_CHECKS:
                break  # nothing beyond the limit is built: the check-limit finding names it
            try:
                out += build(report, "core", MAX_FORMAL_CHECKS - len(out))
            except Exception:  # noqa: BLE001 - checks() names the failing extractor (CORE-INTERNAL-001)
                continue
        return out[:MAX_FORMAL_CHECKS]


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
