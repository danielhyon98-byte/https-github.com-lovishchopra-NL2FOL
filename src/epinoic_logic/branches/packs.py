"""Integrity packs: the subject-specific checks each branch carries, plus the core pack
every branch runs. Deterministic findings cite the pack's working rules; formal checks
are problems the engine decides about the report's own statements.

``CorePack(reading=...)`` takes a :class:`~epinoic_logic.stem.si_reading.QuantReading`. The
default, ``quant.GENERAL``, is today's core pack byte for byte (every non-STEM branch). The STEM
branches run ``CorePack(reading=SI_READING)`` (docs/STEM_DESIGN.md, section 12): the prose
arithmetic is read in SI (``quant`` module docstring), quotations are read on the quotation view
(code masked; an inch or arcsecond mark attached to a number, ``12″`` or ``0.5"``, is never a
quotation mark, so CORE-SRC-004 does not fire on it), and chronology, self-certification and the
sentences of every finding are read on the STEM statements of the prose view (maths and
quantities masked, so ``1500 K`` is never a year). CORE-SRC-001 (per ``source_ref``) is the same
under both readings."""
from __future__ import annotations

import itertools
import re
from fractions import Fraction
from functools import lru_cache
from typing import NamedTuple, Optional

from .. import lexis
from ..adapters.history_specialist.chronology import chronology_relations
from ..adapters.history_specialist.sentences import split_sentences as _split_sentences, strip_json_spans
from ..adapters.markdown import (ABSENT_BEFORE_RE, ABSENT_JOIN_RE, MEMORY_LABEL_RE as _MEMORY_LABEL_RE, absent_mentions, dangling_quote_offset,
                                 find_quotation_spans, is_memory_label, is_self_certification, parser_quotation_spans, self_cert_vocabulary,
                                 strip_emphasis, unbalanced_double_quotes, verification_label)
from ..adapters.self_report import is_worked_check, not_a_self_report, reading_form, self_report_spots
from ..adapters.sources import OWN_MODEL_NOTE, check_excerpt, own_model_words, specialist_names, strip_trailing_punctuation, uncredited_excerpt
from ..stem.si_reading import QuantReading, si_prose_view, si_quant_view, si_quote_view, si_statements
from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from ..translate.grounding import FORM_DIFFERS, check_claim_sources, find_quotation, locate_excerpt, locate_quotation_inexact
from ..translate.subjects import resolve_profile
from .base import FormalCheck
from .quant import ARITH_ENDPOINT_REASON, GENERAL, LONG_NUMBER_RUN_REASON, WORKED_EQUATION_REASON, XRATE_OPEN_REASON, extract_quant_checks, undecided_quant_statements

_PARA_RE = re.compile(r"\n\s*\n")
#: The most formal checks the core pack sends to the engine for one transmission (arithmetic first, then chronology). An answer far
#: beyond any request's length could otherwise hold the hub for seconds; the statements beyond the limit are named, never dropped
#: silently (CORE-QNT-001 / CORE-CHR-001: 'not checked: the check limit was reached').
MAX_FORMAL_CHECKS = 500
#: The authors of a study as an in-text citation names them: one surname, two joined by 'and' or '&', or a surname with 'et al.' or
#: 'and colleagues' ('Halvorsen et al.', 'Tversky and Kahneman', 'Woollett & Maguire', 'Halvorsen and colleagues').
_STUDY_NAME = r"[A-ZÀ-Ý][a-zà-ÿ'’-]+"
#: Blank runs are possessive: what follows each is never a blank, so the matches are the same and a long run is read once.
_STUDY_AUTHORS = (rf"{_STUDY_NAME}(?:\s(?:and|&)\s{_STUDY_NAME})?(?:\s++et\s++al\.?|\s++and\s++(?:his\s++|her\s++|their\s++)?(?:colleagues|co-?workers))?")
#: A study attribution in the narrative form, 'Frederick (2005)', 'Halvorsen et al. (2019)', 'Halvorsen and colleagues (2019)'.
_STUDY_RE = re.compile(rf"\b({_STUDY_AUTHORS})\s*+\((\d{{4}})[a-z]?\)")
#: A bracketed citation group, '(Halvorsen & Lund, 2019)', '(Woollett, 2011)', '(Maguire et al., 2000; Woollett & Maguire, 2011)': each
#: part is an author list and a year. The group is at most 300 characters with no bracket inside, so each opening bracket is read once.
_CITATION_GROUP_RE = re.compile(r"\(([^()\n]{4,300})\)")
_CITATION_PART_RE = re.compile(rf"\s*+({_STUDY_AUTHORS}),?\s++(\d{{4}})[a-z]?\s*+")
#: Capitalised words that open a bracketed date or reference but name no author ('(June, 2019)', '(Table 1, 2019)').
_NOT_AUTHORS = frozenset("""january february march april may june july august september october november december spring summer autumn winter
    table figure fig source sources paper section question part page chapter unit topic year grade level exam test the in see""".split())


def study_attributions(text: str) -> list[str]:
    """The study attributions of ``text`` in the narrative form ('Halvorsen et al. (2019)', 'Halvorsen and colleagues (2019)') and in
    bracketed APA citations ('(Halvorsen & Lund, 2019)', '(Woollett, 2011)', each part of '(A, 2000; B & C, 2011)'), in order."""
    found: list[tuple[int, str]] = []
    for m in _STUDY_RE.finditer(text):
        if m.group(1).split()[0].lower() not in _NOT_AUTHORS:
            found.append((m.start(), m.group(0)))
    for g in _CITATION_GROUP_RE.finditer(text):
        for part in g.group(1).split(";"):
            pm = _CITATION_PART_RE.fullmatch(part)
            if pm is not None and pm.group(1).split()[0].lower() not in _NOT_AUTHORS:
                found.append((g.start(), f"({part.strip()})"))
    return [x for _pos, x in sorted(found, key=lambda t: t[0])]
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
#: A possessive noun of a view with its complement clause right after a source's name: 'Tomas Reyes's view that the company could "..."',
#: 'the Economics specialist's claim that ...'. The clause credits the quotation to the source unless it names an inner speaker of its own
#: (a capitalised name: 'the Economics specialist's point is that Tomas Reyes wants to "..."' quotes Reyes, not the specialist).
_VIEW_THAT_RE = re.compile(r"^['’]s\s+(?:own\s+)?(?:view|claim|argument|reading|point|position|account|conclusion|suggestion|belief|assumption|contention|insistence)"
                           r"\s+(?:is\s+)?that\b(?P<clause>[^.;:!?\"“”]*)$", re.IGNORECASE)


def _view_credit(gap: str) -> bool:
    """True when ``gap`` (the text between a source's name and a quotation) is a possessive view with its complement clause
    (:data:`_VIEW_THAT_RE`) naming no inner speaker."""
    m = _VIEW_THAT_RE.match(gap)
    return bool(m) and not re.search(r"(?<![\w'’])(?!I\b)[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]", m.group("clause"))


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


def _sentences_for(text: str, reading: QuantReading = GENERAL, view: str = "prose") -> list[tuple[int, int, str, str]]:
    """``_sentences_with_paragraph`` under a reading: the general reading's blank-line paragraphs and shared splitter, or
    in the SI reading the STEM statements (numbered as the STEM claim ids) of the prose view (``view="prose"``: maths and
    quantities masked) or the quotation view (``view="quote"``: code and number marks masked)."""
    if not reading.si:
        return _sentences_with_paragraph(text)
    v = si_prose_view(text, reading.profile) if view == "prose" else si_quote_view(text, reading.profile)
    paras: dict[int, list[tuple[int, int, int]]] = {}
    for p, n, a, b in si_statements(text, reading.profile):
        paras.setdefault(p, []).append((n, a, b))
    out: list[tuple[int, int, str, str]] = []
    for p in sorted(paras):
        items = paras[p]
        para_text = v[items[0][1]:items[-1][2]]
        out.extend((p, n, v[a:b].strip(), para_text) for n, a, b in items)
    return out


def _chronology_formal(report: SpecialistReport, prefix: str, limit: Optional[int] = None, reading: QuantReading = GENERAL) -> list[FormalCheck]:
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
    check-limit finding), so an oversized answer costs no work beyond the limit. In the SI reading (``reading``) the sentences are
    the STEM statements of the prose view (maths and quantities masked, so ``1500 K`` is never a year) and each check names the
    STEM claim of its statement."""
    from ..ir.schema import Problem
    out: list[FormalCheck] = []
    n = 0
    grounding = {"kind": "supplied_text", "verified": True}

    def var(name: str) -> dict:
        return {"op": "var", "name": name}

    def eq(name: str, value: int, label: str, pid: str) -> dict:
        return {"id": pid, "expr": {"op": "eq", "left": var(name), "right": {"op": "int", "value": str(value)}}, "label": label[:1000], "grounding": grounding}

    units = _chronology_units(report.original_response, reading)
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
                                   problem=Problem.model_validate(problem), claim_ids=_chronology_claims(report, sent, rel, reading)))
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
                               claim_ids=_chronology_claims(report, sent, rel, reading)))
    return out


def _chronology_units(text: str, reading: QuantReading = GENERAL) -> list[tuple[str, str, list]]:
    """The decided dated relations of ``text`` as the units the engine checks: ``(sentence, paragraph, relations)``. The items of one
    containment list (one cue, one outer period: 'including A in d1, B in d2 and C in d3') are one unit, so a list costs one engine
    call; every other relation is a unit of its own. ``reading``: the sentences of :func:`_sentences_for`."""
    units: list[tuple[str, str, list]] = []
    for _pi, _si, sent, para in _sentences_for(text, reading):
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


def _quant_formal(report: SpecialistReport, prefix: str, limit: Optional[int] = None, reading: QuantReading = GENERAL) -> list[FormalCheck]:
    """The report's own arithmetic as engine problems. A relation stated across sentences (a
    derived figure, 'rose in each year', 'the greatest rise' whose figures stand in another
    sentence of the paragraph) says in its description where its year and figures were read.
    With ``limit``, only the first ``limit`` checks are built (their claims named), the rest being
    the core pack's check-limit finding. ``reading``: the general or the SI reading of the prose arithmetic (``quant``)."""
    out: list[FormalCheck] = []
    checks = extract_quant_checks(report.original_response, request_id=report.request_id, claim_id=f"{report.report_id}:{prefix}", reading=reading)
    for qc in (checks if limit is None else checks[: max(0, limit)]):
        description = f"report's own arithmetic: {_excerpt_around(qc.sentence, qc.phrase)}" + (f" [{qc.basis[:400]}]" if qc.basis else "") + (f" [{qc.rule}]" if qc.rule else "")
        out.append(FormalCheck(check_id=f"{prefix}-{qc.check_id}", kind=qc.kind, description=description, problem=qc.problem,
                               claim_ids=_quant_claims(report, qc, reading), failure_severity="warning" if qc.failure_severity == "warning" else "error"))
    return out


def _figure_formal(report: SpecialistReport, prefix: str, limit: Optional[int] = None, reading: QuantReading = GENERAL) -> list[FormalCheck]:
    """The figures the report takes from its supplied tables and texts, checked against them (:mod:`.grounded_figures`; round 9 second pass,
    c2 adversarial-live bug 16). Not on the STEM branches (the SI reading), whose ``stem-giv`` check reads the supplied tables itself."""
    if reading.si:
        return []
    from .grounded_figures import figure_grounding_checks
    return figure_grounding_checks(report, prefix, limit)


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


def _si_claims_for_fragment(report: SpecialistReport, fragment: str, reading: QuantReading, view_of) -> tuple[str, ...]:
    """SI reading only: the claims of the STEM statement whose text in ``view_of`` (the view the fragment was read on) holds
    ``fragment``, so an INT-SUBJ finding about a prose relation names its claim."""
    frag = " ".join(fragment.split())
    if not frag:
        return ()
    view = view_of(report.original_response, reading.profile)
    for p, n, a, b in si_statements(report.original_response, reading.profile):
        if frag in " ".join(view[a:b].split()):
            return tuple(_claims_for_si_statement(report, view[a:b], reading, p, n))
    return ()


def _quant_claims(report: SpecialistReport, qc, reading: QuantReading = GENERAL) -> tuple[str, ...]:
    """The claims a prose arithmetic check names: in the SI reading the STEM claim of the statement that holds it (read on the SI
    quant view); otherwise the claims whose text holds its statement (:func:`_claims_for_statement`)."""
    if reading.si:
        return _si_claims_for_fragment(report, qc.sentence, reading, si_quant_view)
    return tuple(_claims_for_statement(report, qc.sentence, qc.phrase))


def _chronology_claims(report: SpecialistReport, sent: str, rel, reading: QuantReading = GENERAL) -> tuple[str, ...]:
    """The claims a chronology check names: in the SI reading the STEM claim of the statement that holds it (read on the prose
    view); otherwise the claims whose text holds its sentence (:func:`_claims_for_statement`)."""
    if reading.si:
        return _si_claims_for_fragment(report, sent, reading, si_prose_view)
    return tuple(_claims_for_statement(report, sent, rel.cue))


def _is_peer_text(t: SuppliedText) -> bool:
    return t.document_id.startswith("peer:") or bool(t.author and _PEER_AUTHOR_RE.match(t.author.strip().lower()))


#: A person a case or a source names by role ("the finance director", "the operations manager", "the CEO").
_CASE_ROLE_RE = re.compile(r"\bthe\s++((?:finance|managing|marketing|operations|sales|production|human\s++resources|HR|technical)\s++"
                           r"(?:director|manager)|chief\s++(?:executive|financial|operating)\s++officer|CEO|CFO|owner|founder|chair(?:man|woman|person)?"
                           r"|spokes(?:man|woman|person)|headteacher|mayor)\b", re.IGNORECASE)


#: The leading word of a supplied text's title that names it in prose ('Brackwater' of 'Brackwater Garden Buildings Ltd'): a capitalised
#: word of four letters or more.
_TITLE_LEAD_RE = re.compile(r"\s{0,4}['\"“‘]?([A-Z][^\W\d_]{3,30})\b")
#: Kinds of supplied material a title word names besides :data:`_GENERIC_SOURCES` ('the Brackwater case study', 'the Brackwater case').
_CASE_KINDS = ("case study", "case text", "case", "scenario", "stimulus", "data")


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
    # a person a supplied text names by role ("The finance director says: ..." in a case study): a sentence that credits words to that
    # role credits them to that text, so the Economics specialist's words given to the case's finance director are a wrong credit
    # (CORE-SRC-005; c1 adversarial bm-p8a-misattr). Only a role one supplied text alone names.
    role_docs: dict[str, set[str]] = {}
    for t in non_peer:
        for m in _CASE_ROLE_RE.finditer(t.text[:200_000]):
            role_docs.setdefault(" ".join(m.group(1).lower().split()), set()).add(t.document_id)
    for role, docs in role_docs.items():
        if len(docs) == 1:
            names.setdefault(f"the {role}", (next(iter(docs)), f"the {role} of {next(iter(docs))}"))
    # a supplied text named by the leading word of its title and a kind ('the Brackwater case study says: "..."' for 'Brackwater Garden
    # Buildings Ltd (case study, ...)'; round 9, c2 lens-al 12h): the credit is that text's, so words that occur only in a colleague's
    # report are a wrong credit (CORE-SRC-005). Only a title word one supplied text alone opens with.
    title_words: dict[str, set[str]] = {}
    for t in non_peer:
        first = _TITLE_LEAD_RE.match(t.title or "")
        # a name, not a common word that opens the title ('Last orders at the deep end'): the text never writes it in lower case, as it
        # never writes 'brackwater' (it writes 'Brackwater' in every place), where an opinion column titled 'Last orders ...' writes 'last'
        if first and not re.search(r"(?<![^\W\d_])" + re.escape(first.group(1).lower()) + r"(?![^\W\d_])", t.text[:200_000]):
            title_words.setdefault(first.group(1).lower(), set()).add(t.document_id)
    for word, docs in title_words.items():
        if len(docs) == 1:
            doc_id = next(iter(docs))
            for g in (*_GENERIC_SOURCES, *_CASE_KINDS):
                names.setdefault(f"the {word} {g}", (doc_id, f"the {word} {g}"))
    if len(non_peer) == 1:
        for g in _GENERIC_SOURCES:
            names.setdefault(f"the {g}", (non_peer[0].document_id, f"the {g}"))
        for g in _CASE_KINDS[:2]:  # 'the case study', 'the case text' (never 'the case' alone: 'in the case of')
            names.setdefault(f"the {g}", (non_peer[0].document_id, f"the {g}"))
    if len(peers) == 1:
        for g in _GENERIC_PEERS:
            names.setdefault(f"the {g}", (peers[0].document_id, f"the {g}"))
            names.setdefault(f"my {g}", (peers[0].document_id, f"my {g}"))
    return names


def _holds_quotation(excerpt: str, doc: SuppliedText) -> bool:
    """Whether ``doc`` holds the quoted words: verbatim or after typographic normalization (``find_quotation``), with the sentence
    punctuation written inside the closing mark set aside (``locate_excerpt``), or in a conventional difference of form, the first
    letter's case, a verse mark or diacritics (``locate_quotation_inexact``; round 9, c2 lens-al 12f: '"imports fall by 2.5 million
    tonnes per year"' of a colleague's 'Imports fall by ...' is the colleague's words, so a credit to the case is still checked)."""
    return bool(find_quotation(excerpt, doc.text, document_id=doc.document_id) or locate_excerpt(excerpt, doc.text, document_id=doc.document_id)
                or locate_quotation_inexact(strip_trailing_punctuation(excerpt), doc.text, document_id=doc.document_id))


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
                if (_ATTRIBUTION_RE.search(before[me:]) or _LEADING_ATTRIBUTION_RE.search(before[:mentions[-1][0]])
                        or _view_credit(before[me:])):
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


_WORD_RUN_RE = re.compile(r"\w+")
#: At most this many other quotations are compared with one quotation key (:func:`_absorbed_quotation_keys`); a key whose
#: rarest word more quotations hold than this is kept (reported), never absorbed unread.
_ABSORB_CANDIDATES = 512


def _absorbed_quotation_keys(keys: list[str]) -> set[str]:
    """The quotation keys that occur as whole words inside another key (a word quoted from a quotation the answer already
    gives: 'the verb "killed"' after '"We killed him openly"'). Exactly what searching every key in every other key gave,
    found through the keys that hold the key's rarest word: every word of a key occurs as a whole word in a key that holds
    it so, so those keys are the only candidates. The pairwise search was quadratic in an answer's quotations (round-8
    clearance c1, handoff fixer: 2,000 short quotations took 18 s of the English and generic packs' reading); a key whose
    candidates exceed :data:`_ABSORB_CANDIDATES` is compared with that many and otherwise kept."""
    distinct = list(dict.fromkeys(keys))
    postings: dict[str, list[int]] = {}
    for i, k in enumerate(distinct):
        for w in set(_WORD_RUN_RE.findall(k)):
            postings.setdefault(w, []).append(i)
    longest_first = lambda ids: sorted(ids, key=lambda j: -len(distinct[j]))  # noqa: E731
    postings = {w: longest_first(ids) for w, ids in postings.items()}
    every = longest_first(range(len(distinct)))
    out: set[str] = set()
    for k in distinct:
        runs = set(_WORD_RUN_RE.findall(k))
        pool = min((postings[w] for w in runs), key=len) if runs else every
        pattern = None
        for checked, j in enumerate(pool):
            other = distinct[j]
            if len(other) <= len(k) or checked >= _ABSORB_CANDIDATES:
                break  # longest first: no key after this one is longer (only a longer key can hold another)
            if pattern is None:
                pattern = re.compile(rf"(?<!\w){re.escape(k)}(?!\w)")
            if pattern.search(other):
                out.add(k)
                break
    return out


def _is_english_subject(subject: Optional[str]) -> bool:
    from ..translate.subjects import resolve_profile
    try:
        return resolve_profile(subject).key in ("english_a_literature", "english_a_language_literature", "literature_performance", "language_a_other", "english")
    except Exception:
        return False


_UNSUPPLIED = "unsupplied:"
#: A colleague credited by name whose report was not supplied to this agent ('The Economics specialist's view that ...').
_UNSUPPLIED_PEER = _UNSUPPLIED + "specialist:"
_SPECIALIST_MENTION_RE = re.compile(r"\b(?:the|my|our)\s+((?:[A-Za-z][\w-]*\s+){1,4}?specialist)\b(?!\s*['’]s\s+(?:report|answer)\s+(?:was|is)\s+not\b)",
                                    re.IGNORECASE)


def _with_unsupplied_credits(sentence: str, spans: list[tuple[int, int, str]], names: dict[str, tuple[str, str]], texts: list[SuppliedText],
                             own_names: frozenset = frozenset()) -> dict[str, tuple[str, str]]:
    """``names`` plus the sources ``sentence`` credits that were not supplied to this agent ('Hardy's speaker', 'Hardy's poem',
    'Pakenham writes', 'the Economics specialist' when no report of that colleague was supplied, and 'the poem' when no literary
    text was supplied), each under a pseudo document id; a name already among the supplied texts' names, and the agent's own name
    (``own_names``: 'the Business Management specialist' in its own answer), is left to them."""
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
    # a colleague is unsupplied only when no supplied report is that colleague's under any of its names ('the Mathematics specialist' for a
    # report of mathematics-aa-specialist, sources.specialist_names), and only when every supplied report can be named at all
    peer_names: set[str] = set()
    nameless_peer = False
    for t in texts:
        if _is_peer_text(t):
            known = [n.lower() for n in specialist_names((t.author or "").strip())]
            nameless_peer = nameless_peer or not known
            peer_names.update(known)
    for m in (_SPECIALIST_MENTION_RE.finditer(text) if not nameless_peer else ()):
        phrase = " ".join(m.group(1).split()).lower()
        if phrase in low_names or phrase in own_names or phrase in peer_names \
                or any(n.endswith(" " + phrase) or phrase.endswith(" " + n) for n in (*low_names, *peer_names) if n.endswith("specialist")):
            continue
        extra.setdefault(phrase, (_UNSUPPLIED_PEER + phrase, f"the {' '.join(m.group(1).split())}"))
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


#: Words before a quoted word that say the text lacks it ('has no "like"', 'never says "ayudar"', 'does not use "toda"', 'without
#: "as"'), what may join two such words ('has no "like" or "as"'), and the quoted words a sentence says the text lacks: the
#: frame reader of ``adapters.markdown`` (moved there unchanged in integration gate 1, so the parsers credit such a mention to
#: no text by the same frames; the channel and the Overseer import it from here under these names).
_ABSENT_BEFORE_RE = ABSENT_BEFORE_RE
_ABSENT_JOIN_RE = ABSENT_JOIN_RE
_absent_mentions = absent_mentions


def _claims_mentioning(report: SpecialistReport, fragment: str) -> list[str]:
    frag = " ".join(fragment.split())
    return [c.claim_id for c in report.claims if frag and (frag in " ".join(c.claim_text.split()) or " ".join(c.claim_text.split()) in frag)]


def _claims_for_si_statement(report: SpecialistReport, sentence: str, reading: QuantReading, paragraph: int, number: int) -> list[str]:
    """The claims a finding about one sentence names. The general reading matches the sentence text
    (:func:`_claims_mentioning`). The SI reading reads a masked view, so it names the STEM statement
    ``s<paragraph>.<number>`` (``m``/``c`` in the mathematics and Computer Science branches) when the
    report carries that claim, else the claims that mention the statement's original text."""
    if not reading.si:
        return _claims_mentioning(report, sentence)
    sid = f"{paragraph}.{number}" if number else ".tail"
    ids = {c.claim_id for c in report.claims}
    # the STEM parsers qualify their ids with the agent ('s1.2@physics-specialist'): the id before the qualifier names it
    base: dict[str, str] = {}
    for c in report.claims:
        base.setdefault(c.claim_id.split("@", 1)[0], c.claim_id)
    for prefix in ("s", "m", "c"):  # the STEM branches' claim ids (adapters.stem_specialist.parser.ID_PREFIXES)
        if prefix + sid in ids:
            return [prefix + sid]
        if prefix + sid in base:
            return [base[prefix + sid]]
    for p, n, a, b in si_statements(report.original_response, reading.profile):
        if p == paragraph and n == number:
            return _claims_mentioning(report, report.original_response[a:b])
    return _claims_mentioning(report, sentence)


# ------------------------------------------------------------------ marks of marking feedback (c1 breadth finding 16)

#: A mark awarded out of a maximum, with an optional range: '3 out of 5 (range 2–3)', '6/11 (range 5–7)'. Bounded figures and blank runs.
#: Round 9 (c2): also a mark 'n of N' (beside a mark word: 'Provisional mark: 16 of 15') and a mark written as a range, 'a to b out of N',
#: 'a–b of N' ('Provisional mark: 1 to 2 out of 4', '5–6 of 15'), whose top is held to the maximum and whose range is summed.
_MARK_VALUE = (r"(?:(?P<a>\d{1,3})\s{0,3}(?:to|[–—-])\s{0,3})?(?P<n>\d{1,3})\s{0,3}(?:out\s{1,3}of|of|/)\s{0,3}(?P<m>\d{1,3})(?![\d.,]?\d)"
               r"(?:\s{0,3}\(\s{0,3}range\s{1,3}(?P<lo>\d{1,3})\s{0,3}(?:[–—-]|to)\s{0,3}(?P<hi>\d{1,3})\s{0,3}\))?")
#: The total of a marking: 'Provisional total: 6 out of 11 (range 5–7)', 'Total mark: 9/20', 'Provisional total across the four parts: 3 to 6
#: out of 11'.
_MARK_TOTAL_RE = re.compile(r"\b(?:provisional\s{1,3})?total(?:\s{1,3}mark)?(?:\s{1,3}(?:across|for|over|of)\s{1,3}[^:\n]{1,40}?)?\s{0,3}:\s{0,3}" + _MARK_VALUE,
                            re.IGNORECASE)
#: The mark of one part: 'Provisional mark: 3 out of 5 (range 2–3)', 'Mark for (b): 2/4', or of one assessment criterion: 'Criterion A: 4/5',
#: 'Criterion B (Analysis and evaluation) – 3 out of 5' (round-8 clearance c1, handoff fixer: an English A feedback stating "Criterion A:
#: 6/5 ... Total: 14/20", 6 over its maximum and criteria summing to 17, drew no finding).
_MARK_PART_RE = re.compile(r"\b(?:(?:provisional\s{1,3})?mark(?:\s{1,3}for\s{1,3}[^:\n]{1,20})?\s{0,3}:|criterion\s{1,3}[A-Za-z](?![\w])(?:\s{0,3}\([^)\n]{1,60}\))?\s{0,3}[:\u2013\u2014-])"
                           r"\s{0,3}" + _MARK_VALUE, re.IGNORECASE)
#: The most part marks one total is read against.
_MAX_MARK_PARTS = 24
MARKS_SCOPE = ("Marks check: proves a property of its encoding only: that the marks the feedback states are consistent with one another "
               "(each within its maximum, the stated total within the sum of the part marks when the parts' maxima make up the total's). It does "
               "not establish that any mark is deserved.")


def _mark_of(m: "re.Match[str]") -> tuple[int, int, int, int]:
    """``(stated, maximum, low, high)`` of a mark; a mark with no range has low = high = stated; a mark written as a range ('1 to 2 out of
    4') has its two ends as low and high and its top as the stated mark."""
    n, mx = int(m.group("n")), int(m.group("m"))
    if m.group("a"):
        a = int(m.group("a"))
        return max(a, n), mx, min(a, n), max(a, n)
    lo, hi = (int(m.group("lo")), int(m.group("hi"))) if m.group("lo") else (n, n)
    return n, mx, min(lo, hi), max(lo, hi)


#: The other mark a part may get, stated right after its mark ('Provisional mark: 1 out of 3. It would be 2 if your teacher's scheme gives
#: the division its own mark.'; c1 ch-t14): the part's range, for the total, runs to it.
_ALTERNATIVE_MARK_RE = re.compile(r"\b(?:it|this|that|the\s{1,3}mark)\s{1,3}(?:would|could|might)\s{1,3}(?:be|rise\s{1,3}to|go\s{1,3}up\s{1,3}to)\s{1,3}(\d{1,3})\b",
                                  re.IGNORECASE)


def _with_alternative_mark(text: str, m: "re.Match[str]", stop: int) -> tuple[int, int, int, int]:
    """:func:`_mark_of` of a part mark, its range widened to the other mark the text states for the part before the next part's mark
    (within 300 characters of it), when that mark is no more than the part's maximum."""
    n, mx, lo, hi = _mark_of(m)
    alt = _ALTERNATIVE_MARK_RE.search(text, m.end(), min(stop, m.end() + 300))
    if alt is not None and int(alt.group(1)) <= mx:
        v = int(alt.group(1))
        return n, mx, min(lo, v), max(hi, v)
    return n, mx, lo, hi


def _marks_formal(report: SpecialistReport, prefix: str, limit: Optional[int] = None, reading: QuantReading = GENERAL) -> list[FormalCheck]:
    """The marks a marking-feedback answer states, decided by the engine (c1 breadth finding 16): each mark against its maximum ('6 out of
    5' fails), and the stated total against the sum of the part marks when the parts' maxima make up the total's maximum ('Provisional
    total: 8 out of 11 (range 7–9)' over parts of 3, 2 and 1 fails: the total lies outside 5 to 7, the sum of the parts' ranges). Read only
    in a marking or feedback task (``markdown.corrections_apply``); a failure is INT-SUBJ-001 naming the claims that state the marks."""
    from ..adapters.markdown import corrections_apply
    from ..ir.schema import Problem
    if not corrections_apply(report.task_type):
        return []
    text = report.original_response[:200_000]
    total = _MARK_TOTAL_RE.search(text)
    parts = [m for m in _MARK_PART_RE.finditer(text) if total is None or m.start() != total.start()][:_MAX_MARK_PARTS]
    out: list[FormalCheck] = []
    V = lambda name: {"op": "var", "name": name}  # noqa: E731
    I = lambda v: {"op": "int", "value": str(v)}  # noqa: E731

    def claims(m: "re.Match[str]") -> tuple[str, ...]:
        return tuple(_claims_mentioning(report, m.group(0)) or _claims_for_statement(report, m.group(0), m.group(0)))[:8]

    for k, m in enumerate(([total] if total else []) + parts, start=1):
        n, mx, lo, hi = _mark_of(m)
        if len(out) >= (limit if limit is not None else MAX_FORMAL_CHECKS):
            return out
        prob = {"problem_id": f"marks-{report.report_id}-{k}", "request_id": report.request_id, "claim_id": f"{report.report_id}:marks-{k}",
                "query": "entailment", "symbols": [{"name": "awarded", "sort": "Int", "meaning": "the highest mark stated"},
                                                   {"name": "maximum", "sort": "Int", "meaning": "the maximum it is stated out of"}],
                "premises": [{"id": "AWARDED", "expr": {"op": "eq", "left": V("awarded"), "right": I(max(n, hi))}, "label": f"stated mark {m.group(0)[:80]}",
                              "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}},
                             {"id": "MAXIMUM", "expr": {"op": "eq", "left": V("maximum"), "right": I(mx)}, "label": f"stated maximum {mx}",
                              "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}}],
                "conclusion": {"id": "WITHIN_MAXIMUM", "expr": {"op": "le", "left": V("awarded"), "right": V("maximum")},
                               "label": f"the mark stated in '{m.group(0)[:80]}' is at most its maximum"},
                "notes": MARKS_SCOPE}
        out.append(FormalCheck(check_id=f"{prefix}-marks-{len(out) + 1}", kind="marks_arithmetic",
                               description=f"the mark '{m.group(0)[:120]}' against its maximum [rule: a mark, and the top of its range, is at most its maximum]",
                               problem=Problem.model_validate(prob), claim_ids=claims(m)))
    if total is not None and len(parts) >= 2:
        n, mx, lo, hi = _mark_of(total)
        part_marks = [_with_alternative_mark(text, p, parts[j + 1].start() if j + 1 < len(parts) else len(text)) for j, p in enumerate(parts)]
        if sum(p[1] for p in part_marks) == mx and len(out) < (limit if limit is not None else MAX_FORMAL_CHECKS):
            symbols = [{"name": f"p{j}_lo", "sort": "Int", "meaning": f"the lowest mark stated for part {j}"} for j in range(1, len(part_marks) + 1)]
            symbols += [{"name": f"p{j}_hi", "sort": "Int", "meaning": f"the highest mark stated for part {j}"} for j in range(1, len(part_marks) + 1)]
            symbols.append({"name": "total", "sort": "Int", "meaning": "the total the feedback states"})
            premises = []
            for j, (pn, pmx, plo, phi) in enumerate(part_marks, start=1):
                for bound, v in (("lo", plo), ("hi", phi)):
                    premises.append({"id": f"P{j}_{bound.upper()}", "expr": {"op": "eq", "left": V(f"p{j}_{bound}"), "right": I(v)},
                                     "label": f"part {j}: {parts[j - 1].group(0)[:60]}",
                                     "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
            # a total written as a range ('3 to 6 out of 11') lies within the sum of the parts' ranges at both ends (round 9, c2 ec-t15-total)
            symbols.append({"name": "total_lo", "sort": "Int", "meaning": "the lowest total the feedback states"})
            premises.append({"id": "TOTAL", "expr": {"op": "eq", "left": V("total"), "right": I(hi)}, "label": f"stated total {total.group(0)[:80]}",
                             "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
            premises.append({"id": "TOTAL_LO", "expr": {"op": "eq", "left": V("total_lo"), "right": I(lo)}, "label": f"stated total, its lowest value {lo}",
                             "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
            low = {"op": "add", "args": [V(f"p{j}_lo") for j in range(1, len(part_marks) + 1)]}
            high = {"op": "add", "args": [V(f"p{j}_hi") for j in range(1, len(part_marks) + 1)]}
            prob = {"problem_id": f"marks-{report.report_id}-total", "request_id": report.request_id, "claim_id": f"{report.report_id}:marks-total",
                    "query": "entailment", "symbols": symbols, "premises": premises,
                    "conclusion": {"id": "TOTAL_OF_PARTS", "expr": {"op": "and", "args": [{"op": "ge", "left": V("total_lo"), "right": low},
                                                                                         {"op": "le", "left": V("total"), "right": high}]},
                                   "label": "the stated total (both ends of its range) lies within the sum of the part marks (their ranges included)"},
                    "notes": MARKS_SCOPE}
            out.append(FormalCheck(check_id=f"{prefix}-marks-{len(out) + 1}", kind="marks_arithmetic",
                                   description=(f"the total '{total.group(0)[:120]}' against the sum of the {len(part_marks)} part marks, whose maxima make up "
                                                f"its maximum of {mx} [rule: the stated total lies within the sum of the parts' marks, their ranges included]"),
                                   problem=Problem.model_validate(prob), claim_ids=claims(total)))
    return out


#: A fold or a multiple named without a figure ('doubled', 'Doubling', 'twice', 'three times', 'halved'): in a paragraph that states no
#: figure it is a manner of speaking, not arithmetic a reader could check, so it is not named undecided.
_FOLD_ONLY_RE = re.compile(r"\b(?:doubl\w*|tripl\w*|trebl\w*|quadrupl\w*|halv\w*|twice|thrice|(?:two|three|four|five|ten)\s+times)\b", re.IGNORECASE)
_NUMBER_WORD_RE = re.compile(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million"
                             r"|billion|half|third|quarter|per\s*cent|percent)\b", re.IGNORECASE)


def _states_a_figure(text: str) -> bool:
    """A digit, or a number word other than the fold words themselves ('three times' names no figure; 'from two to four' does)."""
    return bool(re.search(r"\d", text)) or bool(_NUMBER_WORD_RE.search(_FOLD_ONLY_RE.sub(" ", text)))


#: The SI reading's undecided reason when the prose around the maths states no pair (the maths itself is masked from the prose reader).
# ---------------------------------------------------------------- precise real-world figures with no source (CORE-SRC-002, per claim)
# Round 9 second pass (c1 adversarial-live#22, c2 adversarial-live bug 22): 'last year about 3.7 million hectares of tropical rainforest were
# cleared worldwide' and 'about 262 million people worldwide have asthma, and 455,000 people died of it last year' crossed with no finding that
# named them, the answer's own Sources line saying nothing was consulted. A precise count, area or rate (a figure of four digits or more, or one
# with a scale word or a unit of measure) in a sentence that places it in the world beyond the supplied material ('worldwide', 'globally', 'in
# the world', 'last year', 'each year', 'annually', 'nationally'), stated by no supplied text and not by the request, under no from-memory label
# and credited to no source in its sentence, is named on its claim. Info, as the report-level finding of the same code (the overseer's code
# table holds CORE-SRC-002 at info); each claim is named once.
_WORLD_MARKER_RE = re.compile(r"\b(?:worldwide|world-wide|globally|across\s+the\s+(?:world|globe)|in\s+the\s+world|the\s+world['’]s|around\s+the\s+world"
                              r"|last\s+year|each\s+year|every\s+year|a\s+year\s+worldwide|annually|nationally|nationwide|in\s+recent\s+years)\b", re.IGNORECASE)
_PRECISE_FIGURE_RE = re.compile(
    r"(?<![\w.,])(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?|\d+(?:\.\d+)?(?=\s*+(?:million|billion|trillion|thousand|hectares|ha\b|km|tonnes|tons"
    r"|kJ|MJ|GJ|kg|people|deaths|cases|patients|species)))(?![\d,.]?\d)(?P<scale>\s*+(?:million|billion|trillion|thousand)\b)?")
_HELD_NUMBER_RE = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\d.,])\d+(?:\.\d+)?")
_SOURCE_CREDIT_RE = re.compile(r"\b(?:according\s+to|(?:estimates?|estimated|reports?|reported|records?|recorded|states?|stated)\s+(?:by|in)\b|source[sd]?\s*:)",
                               re.IGNORECASE)


def _unsourced_world_figures(report: SpecialistReport, request_text: Optional[str]) -> list[StructuralFinding]:
    """CORE-SRC-002 (info) on each claim that states a precise real-world figure no supplied text and not the request holds (the comment
    above). Bounded: at most 200 claims of at most 4,000 characters are read, each with its own scans."""
    held: set[str] = set()
    for t in [x.text[:200_000] for x in report.supplied_texts] + [request_text[:50_000] if request_text else ""]:
        held.update(m.group(0).replace(",", "") for m in _HELD_NUMBER_RE.finditer(t))  # the texts' numbers, read once
    out: list[StructuralFinding] = []
    for c in report.claims[:200]:
        text = c.claim_text[:4000]
        if c.claim_role == "other" or not _WORLD_MARKER_RE.search(text) or _MEMORY_LABEL_RE.search(text) or _SOURCE_CREDIT_RE.search(text):
            continue
        figures = [(m.group("n"), m.group(0).strip()) for m in itertools.islice(_PRECISE_FIGURE_RE.finditer(text), 40)
                   if not re.fullmatch(r"(?:1[0-9]|20)\d\d", m.group("n"))]
        missing = list(dict.fromkeys(shown for n, shown in figures if n.replace(",", "") not in held))
        if not missing:
            continue
        out.append(StructuralFinding(code="CORE-SRC-002", severity="info", claim_ids=[c.claim_id],
                                     message=(f"claim {c.claim_id} states precise real-world figures ({', '.join(missing[:4])}) that no supplied text and not the "
                                              "request holds, with no source, library reference or from-memory label: the figures are unverified"),
                                     rule_source="sources.md L5 (working rule): a precise figure about the world needs its source"))
    return out


_NO_FIGURES_REASON = "no figures are stated with it in its sentence"
#: The words of ``quant._no_pair_reason`` for a sentence whose figures stand only in written arithmetic.
_WRITTEN_ONLY_REASON = "its figures only as written arithmetic"
_MATHS_FIGURES_REASON = ("its sentence states its figures only in written maths, which the STEM checks read (the prose reader reads no pair of "
                         "figures beside it)")
_DIGIT_IN_MATHS_RE = re.compile(r"\d\s*[=≈×÷*/+−-]|[=≈×÷*/+−-]\s*\d")


def _si_statement_texts(report: SpecialistReport, u, reading: QuantReading) -> list[str]:
    """The claim texts (as written, maths included) of the STEM statement an undecided SI statement reads."""
    ids = set(_claims_for_si_statement(report, u.sentence_text, reading, u.paragraph, u.sentence))
    return [c.claim_text for c in report.claims if c.claim_id in ids]


def _restates_written_result(phrase: str, texts: list[str]) -> bool:
    """Whether the derived figure of ``phrase`` ('an increase of 180%') restates the stated result of written arithmetic on its own line
    ('(0.84 − 0.30) ÷ 0.30 × 100 = 180%'): the same figure, with its per cent sign, after an '=' or '≈' of the sentence."""
    m = re.search(r"([-+−]?\d[\d,]*(?:\.\d+)?)\s*(%|per\s*cent|percent)", phrase or "")
    if m is None:
        return False
    figure = m.group(1).replace(",", "").lstrip("+").replace("−", "-")
    pattern = re.compile(r"[=≈]\s*[-+−]?" + re.escape(figure.lstrip("-")) + r"\s*(?:%|per\s*cent|percent)(?![\d.])")
    if any(pattern.search(t.replace(",", "")) for t in texts):
        return True
    # the written result rounded at the restated figure's own precision ('= 631.4%, so 631% to three significant figures; an increase of
    # 631%': round 9, c2 bi-t15): the restatement of a result the STEM check decides, never arithmetic of its own
    try:
        stated = abs(Fraction(figure))
    except (ValueError, ZeroDivisionError):
        return False
    places = len(figure.split(".")[1]) if "." in figure else 0
    half = Fraction(1, 2) / Fraction(10) ** places
    for t in texts:
        for r in re.finditer(r"[=≈]\s*[-+−]?(\d[\d,]{0,20}(?:\.\d{1,12})?)\s*(?:%|per\s*cent|percent)(?![\d.])", t[:20000]):
            try:
                if abs(Fraction(r.group(1).replace(",", "")) - stated) <= half:
                    return True
            except (ValueError, ZeroDivisionError):
                continue
    return False


# ---------------------------------------------------------------- near-miss names of a supplied text (rule case-name, CORE-SRC-008)
# Round-8 clearance c1 (breadth item 19, F18): 'Tidewater Kayaks should keep its price at $45.' on the Tidewell Kayaks case, and
# 'If Brackwood buys ...' in an answer that elsewhere writes the case's Brackwater, crossed the hub with no finding: a near miss of a
# name the case states reads as another business, and nothing compared the answer's names with the case's.

#: A word of letters in any script (digits and '_' excluded): the tokens the reader reads, in one pass.
_NAME_TOKEN_RE = re.compile(r"[^\W\d_]+")
#: What may stand between a sentence's opening and its first word: blanks, opening quotation marks and brackets, emphasis, heading
#: and list marks. A capitalised word after them and after a sentence stop, a colon, a semicolon, a table bar or a closing bracket
#: (a list label, '(a)') is capitalised by its place, not as a name.
_NAME_LEAD_SKIP = frozenset(" \t\"'“”‘’«»([{*_#>•·-–—")
_NAME_LEAD_STOPS = frozenset(".!?:;|)]}\n\r")
#: The most characters read back from a word for its sentence's opening: a word after a longer run of blanks and marks is read as
#: a sentence's first word (no name), so a run of 20,000 blanks costs this many steps, never the run.
_NAME_LEAD_LOOK = 24
#: A name has at least this many letters; a near miss shares at least this many first letters with a name the case states ...
_NAME_MIN = 5
#: ... and at least this share of the shorter word, and differs after the shared opening by at most this many letters on each side
#: ('Tidewater' and 'Tidewell': 'Tidew' then 'ater' and 'ell'; 'Brackwood' and 'Brackwater': 'Brackw' then 'ood' and 'ater').
_NAME_SHARE = 0.6
_NAME_TAIL = 4
#: The neighbours kept per name (the capitalised words next to it in a run: 'Kayaks' of 'Tidewell Kayaks'), the case names compared
#: with one answer name, the answer names compared at all (each sharing its first five letters with a name of the case) and the
#: findings of one report: bounds no answer within the contract's limits reaches with real names, so hostile input costs at most
#: their product in constant-time steps.
_NAME_NEIGHBOURS = 16
_NAME_COMPARED = 32
_NAME_READ = 2048
_NAME_FINDINGS = 16


def _name_like(word: str) -> bool:
    """A capitalised word of five or more letters, the rest lower case ('Tidewell', 'Nandakumar'; not 'NASA', not 'McDonald')."""
    return len(word) >= _NAME_MIN and word[0].isupper() and word[1:].islower()


def _opens_a_sentence(text: str, start: int) -> bool:
    """Whether the word at ``start`` is a sentence's (or a list item's, a table cell's, a heading's) first word: its capital is then
    the place's, never evidence of a name. Reads back at most :data:`_NAME_LEAD_LOOK` characters."""
    i, steps = start - 1, 0
    while i >= 0 and text[i] in _NAME_LEAD_SKIP:
        if steps >= _NAME_LEAD_LOOK:
            return True
        i -= 1
        steps += 1
    if i < 0:
        return True
    ch = text[i]
    return ch in _NAME_LEAD_STOPS or (ch.isdigit() and text[i + 1:i + 2] in (".", ")"))


def _names_of(text: str, skip: tuple[tuple[int, int], ...] = ()) -> dict[str, tuple[str, frozenset[str]]]:
    """``{lower-case name: (the name as first written, the capitalised words next to it in its runs)}`` for the names ``text``
    writes: each capitalised word of five or more letters (:func:`_name_like`) that stands in a run of capitalised words joined by
    single blanks ('Tidewell Kayaks', 'Priya Nandakumar', 'Brackwater Garden Buildings Ltd') or that no sentence opens with
    ('If Brackwood buys'). Words inside the spans ``skip`` (sorted, disjoint: the answer's quotations) are not read. One pass over
    the words; each name keeps at most :data:`_NAME_NEIGHBOURS` neighbours."""
    toks = [(m.start(), m.end(), m.group()) for m in _NAME_TOKEN_RE.finditer(text)]
    out: dict[str, list] = {}
    n, i, k = len(toks), 0, 0
    while i < n:
        j = i
        if toks[i][2][0].isupper():
            while j + 1 < n and toks[j + 1][2][0].isupper() and text[toks[j][1]:toks[j + 1][0]] in (" ", " "):
                j += 1
        for p in range(i, j + 1):
            a, _b, w = toks[p]
            if not _name_like(w) or (i == j and _opens_a_sentence(text, a)):
                continue
            while k < len(skip) and skip[k][1] <= a:
                k += 1
            if k < len(skip) and skip[k][0] <= a:
                continue  # inside a quotation: an altered name there is the altered quotation's (INT-REQ-003), named once
            entry = out.setdefault(w.lower(), [w, set()])
            for q in (p - 1, p + 1):
                if i <= q <= j and len(entry[1]) < _NAME_NEIGHBOURS:
                    entry[1].add(toks[q][2].lower())
        i = j + 1
    return {low: (w, frozenset(nb)) for low, (w, nb) in out.items()}


def _near_miss(word: str, name: str) -> Optional[tuple[int, int, int]]:
    """``(shared opening, letters after it in ``word``, letters after it in ``name``)`` when the lower-case ``word`` is a near miss
    of the lower-case ``name``: not the same word, neither one the other's opening (an inflection or a derived form: 'Calvessa',
    'Calvessan'; 'Garden', 'Gardens'), the same first five letters and three fifths of the shorter word, at most four letters
    different after them on each side, and not one root (``lexis.root``: two forms of one word). None otherwise."""
    if word == name or word.startswith(name) or name.startswith(word):
        return None
    p = 0
    for x, y in zip(word, name):
        if x != y:
            break
        p += 1
    if p < _NAME_MIN or p < _NAME_SHARE * min(len(word), len(name)):
        return None
    tw, tn = len(word) - p, len(name) - p
    if tw > _NAME_TAIL or tn > _NAME_TAIL:
        return None
    if lexis.root(word) == lexis.root(name):
        return None
    return p, tw, tn


class NameMisses(NamedTuple):
    """What rule case-name read: ``found``, ``(name the answer writes, the case's name it nearly writes, the supplied text's id,
    why)`` per near miss (at most :data:`_NAME_FINDINGS`), and ``unread``, the answer's names past the read bound
    (:data:`_NAME_READ`) that were not compared, which the core pack reports rather than passing over silently."""
    found: list[tuple[str, str, str, str]]
    unread: int


def near_miss_names(response: str, texts: list[SuppliedText], request_text: Optional[str] = None) -> NameMisses:
    """Rule case-name (CORE-SRC-008): each name of ``response`` (:func:`_names_of`, outside its quotations) that no supplied text
    (a relayed peer report included, with titles and authors) and not the request states as a word, and that is a near miss
    (:func:`_near_miss`) of a name a supplied text that is not a peer report states in a run of capitalised words, outside its
    sentences' first words or in its title, when either the two stand beside the same capitalised word ('Tidewater Kayaks' and
    'Tidewell Kayaks') or the answer itself also writes the case's name ('If Brackwood buys ...' beside 'Brackwater' elsewhere).
    Linear in the texts; the comparisons are bounded (:data:`_NAME_COMPARED` per name, :data:`_NAME_READ` names), and the names
    past the read bound are counted (:class:`NameMisses`), never dropped unsaid."""
    if not texts or not isinstance(response, str) or not response:
        return NameMisses([], 0)
    stated: set[str] = set()
    for t in texts:
        for part in (t.text, t.title or "", t.author or ""):
            stated.update(m.group().lower() for m in _NAME_TOKEN_RE.finditer(part))
    stated.update(m.group().lower() for m in _NAME_TOKEN_RE.finditer(request_text or ""))
    case: dict[str, tuple[str, set[str], str]] = {}
    for t in texts:
        if _is_peer_text(t):
            continue
        title = t.title or ""
        for source in (t.text, title + "."):
            for low, (w, nb) in _names_of(source).items():
                entry = case.setdefault(low, (w, set(), t.document_id))
                if len(entry[1]) < _NAME_NEIGHBOURS:
                    entry[1].update(sorted(nb)[:_NAME_NEIGHBOURS - len(entry[1])])
        for m in _NAME_TOKEN_RE.finditer(title):
            if _name_like(m.group()):
                case.setdefault(m.group().lower(), (m.group(), set(), t.document_id))
    if not case:
        return NameMisses([], 0)
    by_opening: dict[str, list[str]] = {}
    for low in case:
        by_opening.setdefault(low[:_NAME_MIN], []).append(low)
    quoted = tuple((a, b) for a, b, _inner in find_quotation_spans(response))
    written = {m.group().lower() for m in _NAME_TOKEN_RE.finditer(response)}
    out: list[tuple[str, str, str, str]] = []
    read = unread = 0
    for low, (w, nb) in _names_of(response, quoted).items():
        if low in stated:
            continue
        bucket = by_opening.get(low[:_NAME_MIN])
        if not bucket:
            continue
        read += 1
        if read > _NAME_READ or len(out) >= _NAME_FINDINGS:
            unread += read > _NAME_READ  # past the read bound: counted, never compared; past the findings bound: the fault is named
            continue
        for name in bucket[:_NAME_COMPARED]:
            miss = _near_miss(low, name)
            if miss is None:
                continue
            case_word, case_nb, doc_id = case[name]
            beside = sorted(nb & case_nb)
            if beside:
                why = f"both stand before or after '{beside[0]}'"
            elif name in written:
                why = f"the answer also writes '{case_word}'"
            else:
                continue
            p, tw, tn = miss
            out.append((w, case_word, doc_id, f"the same first {p} letters, then {tw} and {tn} letters that differ; {why}"))
            break
    return NameMisses(out, unread)


class CorePack:
    """Runs for every subject: quotation grounding against supplied texts, numeric
    self-consistency of the report's own figures (and CORE-QNT-001 for a stated derived
    figure no check could be built for), labelling of figures from memory,
    unverifiable, undelimited or misattributed quotations, dated orderings that could
    not be decided, and self-certification language. Quotations are read in straight,
    curly or mixed double marks, guillemets and delimited single marks of two or more
    words, exactly as the parsers read them, after pasted JSON fragments are removed. ``reading`` (the STEM branches:
    ``SI_READING``) changes only how the text is read (module docstring); the default general reading is the core pack of
    every other branch."""
    name = "core"

    def __init__(self, reading: QuantReading = GENERAL) -> None:
        self.reading = reading

    def _reading(self, report: SpecialistReport) -> QuantReading:
        """The pack's reading for this report: the general reading as it is, the SI reading under the report's subject profile."""
        if not self.reading.si:
            return self.reading
        return self.reading.for_profile(resolve_profile(report.subject).key)

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        r = self._reading(report)
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
        f += self._guarded("unsourced real-world figures", lambda: _unsourced_world_figures(report, request_text), f) or []
        disagreeing, disputed = self._guarded("quotation references", lambda: self._quotation_ref_disagreements(report), f) if report.supplied_texts else ([], frozenset())
        f += disagreeing or []
        f += self._guarded("unverifiable quotations", lambda: self._unverifiable_quotations(report, has_memory_label, disputed or frozenset(), request_text, r), f) or []
        if report.supplied_texts:
            f += self._guarded("misattributed quotations", lambda: self._misattributed_quotations(report, r), f) or []
            f += self._guarded("names of the supplied texts", lambda: self._near_miss_case_names(report, request_text), f) or []
        f += self._guarded("quotation marks", lambda: self._unbalanced_quotation_marks(report, r), f) or []
        f += self._guarded("self-certification", lambda: self._self_certification(report, r), f) or []
        f += self._guarded("chronology", lambda: self._undecided_chronology(report, r), f) or []
        f += self._guarded("arithmetic", lambda: self._undecided_arithmetic(report, r), f) or []
        f += self._guarded("support links", lambda: self._support_cycles(report), f) or []
        f += self._guarded("check limit", lambda: self._formal_overflow(report, r), f) or []
        if not r.si and request_text:
            # argument diagnostics (ST-RANGE-001, docs/ARGUMENT_DIAGNOSTICS.md section 3.4): a model the request states with the range of
            # its data, evaluated outside it on a general branch
            f += self._guarded("model range", lambda: request_model_extrapolation(report, request_text), f) or []
        return f

    @staticmethod
    def _formal_overflow(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:
        """CORE-QNT-001 / CORE-CHR-001 for the stated relations beyond :data:`MAX_FORMAL_CHECKS`: they were read but not sent to the engine,
        so the receipt says so and names their claims rather than passing them silently."""
        text = report.original_response
        quant = extract_quant_checks(text, request_id=report.request_id, claim_id=f"{report.report_id}:core", reading=reading)
        chron = [(sent, group[0]) for sent, _para, group in _chronology_units(text, reading)]
        if len(quant) + len(chron) <= MAX_FORMAL_CHECKS:
            return []
        out: list[StructuralFinding] = []
        rule = f"hub integrity: at most {MAX_FORMAL_CHECKS} formal checks per transmission; a stated relation beyond the limit is reported, not skipped"
        over_q = quant[MAX_FORMAL_CHECKS:]
        over_c = chron[max(0, MAX_FORMAL_CHECKS - len(quant)):]
        if over_q:
            ids = list(dict.fromkeys(cid for qc in over_q[:40] for cid in _quant_claims(report, qc, reading)))[:8]
            out.append(StructuralFinding(code="CORE-QNT-001", severity="warning", claim_ids=ids, rule_source=rule,
                                         message=f"{len(over_q)} statement(s) of the report's own arithmetic were not checked: the limit of {MAX_FORMAL_CHECKS} formal checks per "
                                                 f"transmission was reached (first unchecked: '{_excerpt_around(over_q[0].sentence, over_q[0].phrase, 120)}'); the stated arithmetic was not checked"))
        if over_c:
            ids = list(dict.fromkeys(cid for sent, rel in over_c[:40] for cid in _chronology_claims(report, sent, rel, reading)))[:8]
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
            if c.claim_role == "other" or OWN_MODEL_NOTE in c.assumptions:
                continue  # (the writer's own model sentence the parser recorded as such is no quotation: round 9, c2 la-3)
            text, _removed = strip_json_spans(c.claim_text)
            # the quotations a parser reads (``parser_quotation_spans``): a correction or a suggestion in a marking task is the writer's
            # own words, never an unaccounted quotation of the claim (integration gate 1, end-to-end B5, B13); outside a feedback task
            # these are every quoted span, as before
            quotes = [inner.strip() for _s, _e, inner in parser_quotation_spans(text) if len(inner.strip()) >= 4]
            # a 'Model:' or 'Rewrite:' line of the writer's own words (``sources.own_model_words``: no supplied text holds them, or all
            # but one or two of them, or four in a row) quotes nothing of a text; the same label over an altered line of the text is
            # still a quotation, checked here (round 9, c2 la-3: the parser recorded the model sentence's evidence claim as the writer's
            # own, while the sentence's point, which carries the same words, was charged CORE-SRC-006 and its INT-SUBJ-003 copy)
            quotes = [q for q in quotes if not own_model_words(text, q, docs)]
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
    def _unverifiable_quotations(report: SpecialistReport, has_memory_label: bool, disputed: frozenset = frozenset(), request_text: Optional[str] = None,
                                 reading: QuantReading = GENERAL) -> list[StructuralFinding]:
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
        quotations. A quotation a parser recorded as credited to no text is reported whatever its length
        with no text supplied too ('Me ne frego'). Two kinds of quoted words are no quotation to verify: words the request
        itself holds (the guiding question's 'returning home', a true/false statement's 'toda',
        the pasted question's 'complete years': they are located in the request), and a word the
        sentence says the text lacks ('the bruise comparison has no "like" or "as"', 'the text
        never says "ayudar"': a mention, not a quotation). A word quoted from a quotation the
        answer already gives ('the verb "killed"' after '"We killed him openly"') is that quotation's. In the SI reading the
        quotation view is read (code and number marks masked)."""
        source = si_quote_view(report.original_response, reading.profile) if reading.si else report.original_response
        text, _removed = strip_json_spans(source)
        # read as the parsers read it: emphasis markers inside a quotation ('"*una mujer muy simpático*"') are markup, not the words quoted
        text = strip_emphasis(text)
        spans = parser_quotation_spans(text)  # the quotations a parser reads: a correction in a marking task is the writer's own words
        mentions = {_quote_key(q) for q in _absent_mentions(text, find_quotation_spans(text))}  # read on every span, as before
        quoted = [inner.strip() for _s, _e, inner in spans if len(inner.strip()) >= _MIN_QUOTE_CHARS]
        texts = list(report.supplied_texts)
        recorded: list[tuple[str, str]] = []  # (claim id, excerpt) the parser credited to no text, whatever its length, texts or none
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
        if texts:
            docs = {t.document_id: t for t in texts}
            cited = {strip_trailing_punctuation(r.excerpt) for c in report.claims for r in c.source_refs if r.excerpt}
            quoted = [q for q in quoted if strip_trailing_punctuation(q) not in cited and not any(check_excerpt(q, d, docs).located for d in docs) and _quote_key(q) not in disputed]
        if request_text and request_text.strip():
            request_doc = {"the request": SuppliedText(document_id="the request", title=None, author="router", text=request_text)}
            quoted = [q for q in quoted if not check_excerpt(q, "the request", request_doc).located]
        quoted = [q for q in quoted if _quote_key(q) not in mentions]
        # the writer's own model sentence under a 'Model:' or 'Rewrite:' label (``sources.own_model_words``, recorded by the parser as
        # OWN_MODEL_NOTE) is no quotation to verify (round 9, c2 la-3: once CORE-SRC-006 no longer charged it, it was named unverifiable)
        own = {_quote_key(q) for _s, _e, inner in spans for q in [inner.strip()] if q
               and any(OWN_MODEL_NOTE in c.assumptions and q in c.claim_text for c in report.claims)}
        if own:
            quoted = [q for q in quoted if _quote_key(q) not in own]
        # a word quoted from a quotation the answer already gives ('the verb "killed"' after '"We killed him openly"') is that quotation's
        keys = [_quote_key(q) for q in quoted]
        absorbed = _absorbed_quotation_keys(keys)
        quoted = [q for q, k in zip(quoted, keys) if k not in absorbed]
        if not quoted:
            return []
        reported = {strip_trailing_punctuation(q) for q in quoted}
        recorded_ids = [cid for cid, ex in recorded if ex in reported]
        quote_label = bool(_QUOTE_MEMORY_LABEL_RE.search(text))
        sentences = [s for _pi, _si, s, _p in _sentences_with_paragraph(text)]
        # every quotation in a sentence carrying a from-memory label: the labelled sentences are read once and searched as one
        # text (a NUL between them, which no quotation holds), not every sentence again for every quotation (round-8 clearance
        # c1, handoff fixer: quadratic in an answer whose every quotation carries a label)
        labelled = [s for s in sentences if is_memory_label(s)]
        joined = "\x00".join(labelled)
        labelled_in_sentence = bool(labelled) and all((q in joined) if "\x00" not in q else any(q in s for s in labelled) for q in dict.fromkeys(quoted))
        shown = "; ".join("'" + (q[:_EXCERPT_CHARS] + ("..." if len(q) > _EXCERPT_CHARS else "")) + "'" for q in quoted[:4])
        claim_ids = list(dict.fromkeys([c.claim_id for c in report.claims if any(q in c.claim_text for q in quoted)] + recorded_ids))[:8]
        where = f"no supplied text holds them and their sentences credit them to none of the supplied texts [{', '.join(t.document_id for t in texts)}]" if texts else "no text was supplied"
        rule = "source integrity (quote from memory only with permission, and say so)"
        if quote_label or labelled_in_sentence:
            return [StructuralFinding(code="CORE-SRC-003", severity="info", message=f"{len(quoted)} quotation(s) quoted from memory by the specialist's own label; {where}, so they are unverified: {shown}", claim_ids=claim_ids, rule_source=rule)]
        why = "the from-memory label concerns dates and figures, not quotations" if has_memory_label else "no from-memory label is present"
        return [StructuralFinding(code="CORE-SRC-003", severity="warning", message=f"{len(quoted)} quotation(s) cannot be verified: {where} and {why}: {shown}", claim_ids=claim_ids, rule_source=rule)]

    @staticmethod
    def _misattributed_quotations(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:
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
        own_names = frozenset(n.lower() for n in specialist_names(report.agent_id or ""))
        by_id = {t.document_id: t for t in texts}
        by_claim = {c.claim_id: c.claim_text for c in report.claims}
        out: list[StructuralFinding] = []
        seen: set[tuple[str, str]] = set()
        rule = "source integrity (attribute every quotation to the text that holds it; a colleague's words are not the author's and the author's are not the colleague's)"
        for _pi, _si, sent, _para in _sentences_for(report.original_response, reading, "quote"):
            sent, _removed = strip_json_spans(sent)
            spans = [(s, e, inner.strip()) for s, e, inner in find_quotation_spans(sent) if len(inner.strip()) >= 4]
            if not spans:
                continue
            sentence_names = _with_unsupplied_credits(sent, spans, names, texts, own_names)
            for (_s, _e, excerpt), attributed in zip(spans, _attributions(sent, spans, sentence_names)):
                if attributed is None:
                    continue
                doc_id, label, others = attributed
                located = sorted(t.document_id for t in texts if _holds_quotation(excerpt, t))
                if doc_id.startswith(_UNSUPPLIED_PEER):
                    # credited to a colleague whose report this agent was not given: the words of a supplied text are not the colleague's
                    if not located or (excerpt, doc_id) in seen:
                        continue
                    seen.add((excerpt, doc_id))
                    shown = excerpt[:_EXCERPT_CHARS] + ("..." if len(excerpt) > _EXCERPT_CHARS else "")
                    claim_ids = ([c for c in _claims_mentioning(report, sent) if excerpt in by_claim.get(c, "")]
                                 or _claims_for_excerpt(report, sent, excerpt, [x for _s2, _e2, x in spans]))[:8]
                    competing = [(d, l) for d, l in others if d in located]
                    if competing:
                        out.append(StructuralFinding(code="CORE-SRC-005", severity="warning",
                                                     message=f"quotation '{shown}' is credited in its sentence to {label}, a colleague whose report was not supplied to this agent, but the sentence "
                                                             f"also names {', '.join(l + ' (' + d + ')' for d, l in competing)}, and the words occur in {', '.join(located)}: the credit is ambiguous; the words are genuine",
                                                     claim_ids=claim_ids, rule_source=rule))
                        continue
                    out.append(StructuralFinding(code="CORE-SRC-005", severity="error",
                                                 message=f"quotation '{shown}' is credited in its sentence to {label}, a colleague whose report was not supplied to this agent, but its words "
                                                         f"occur in {', '.join(located)}: the words of a supplied text are credited to a colleague",
                                                 claim_ids=claim_ids, rule_source=rule))
                    continue
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
    def _unbalanced_quotation_marks(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:
        """CORE-SRC-004: a paragraph whose double quotation marks (straight, curly, mixed,
        guillemets) cannot be paired; the quotation at the dangling mark could not be
        delimited, so it was not checked against any text. The dangling mark is located by
        context (``markdown.dangling_quote_offset``), so the spans the writer did delimit
        around it are still checked."""
        out: list[StructuralFinding] = []
        source = si_quote_view(report.original_response, reading.profile) if reading.si else report.original_response
        for pi, para in _paragraphs(source):
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
    def _near_miss_case_names(report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        """CORE-SRC-008 (warning, rule case-name; round-8 clearance c1, breadth item 19): a name the answer writes that no supplied
        text and not the request states, a near miss of a name a supplied text states (:func:`near_miss_names`): 'Tidewater Kayaks'
        on the Tidewell Kayaks case, 'Brackwood' in an answer that elsewhere writes the case's Brackwater. The name reads as another
        person, place or business and was checked against no source. A name inside a quotation is the quotation's (INT-REQ-003)."""
        rule = "source integrity (a name the supplied case states is written as the case writes it)"
        out: list[StructuralFinding] = []
        read = near_miss_names(report.original_response, list(report.supplied_texts), request_text)
        for word, name, doc_id, why in read.found:
            out.append(StructuralFinding(code="CORE-SRC-008", severity="warning", rule_source=rule, claim_ids=_claims_mentioning(report, word)[:8],
                                         message=(f"the answer names '{word[:64]}', which no supplied text and not the request states, close to '{name[:64]}', "
                                                  f"a name the supplied text {doc_id} states ({why}): a near miss of a name the case states reads as another "
                                                  "person, place or business, and it was checked against no source")))
        if read.unread:
            out.append(StructuralFinding(code="CORE-SRC-008", severity="warning", rule_source=rule,
                                         message=(f"{read.unread} more of the answer's names share their first {_NAME_MIN} letters with a name the supplied case "
                                                  f"states and are stated by no supplied text, beyond the {_NAME_READ:,} the rule compares: they were not compared "
                                                  "with the case's names, so a near miss among them is not named")))
        return out

    @staticmethod
    def _undecided_chronology(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:
        """CORE-CHR-001: a sentence orders two dated events but the pair could not be
        decided (the only date before the cue sits in an aside about the subject, a year is
        not stated, or both events fall in the same month with no days / the same year with
        no months). The order was stated and not checked; silence would hide that."""
        out: list[StructuralFinding] = []
        for pi, si, sent, para in _sentences_for(report.original_response, reading):
            for rel in chronology_relations(sent, para):
                if rel.decided:
                    continue
                what = "orders two dated events" if rel.kind == "order" else "places a dated event within a dated period" if rel.kind in ("within", "overlaps") else "places a date at a point of a dated period"
                out.append(StructuralFinding(code="CORE-CHR-001", severity="warning",
                                             message=f"paragraph {pi}, sentence {si} {what} ('{rel.cue}': {rel.statement}) but the relation could not be decided: {rel.reason}; the stated relation was not checked",
                                             claim_ids=(_claims_for_si_statement(report, sent, reading, pi, si) if reading.si
                                                        else (_claims_for_statement(report, sent, rel.cue) or _claims_mentioning(report, sent)))[:8],
                                             rule_source="chronology (exact, dated items): a stated order that cannot be paired is reported, not skipped"))
        return out

    @staticmethod
    def _undecided_arithmetic(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:  # noqa: C901
        """CORE-QNT-001: a stated derived figure ('a rise of 50 per cent', 'tripled', 'a change of
        0 per cent') or a relation over dated figures ('rose in each year', 'the greatest rise of the
        period') that no engine problem could be built for: the units of its pair cannot be compared,
        or no pair stands in its clause and the paragraph's dated series does not supply one (none,
        several, or a year that cannot be read); a stated length of years whose dates cannot be paired
        or are too coarse; and a worked equation ('$6,000 ÷ $2.00 = 3,000 loaves'), written arithmetic
        the prose reader does not decide, unless the branch's own subject pack decides it (an elasticity
        on the Economics branch, a margin on the Business branch). The arithmetic was stated and not
        checked; silence would hide that (``quant.undecided_quant_statements``). One finding per sentence
        and reason; the phrases it names are bounded, the rest counted."""
        out: list[StructuralFinding] = []
        grouped: dict[tuple[int, int, str], list] = {}
        decided = pack_decided_equations(report)
        para_text: Optional[dict[int, str]] = None
        for u in undecided_quant_statements(report.original_response, reading=reading):
            if u.reason == WORKED_EQUATION_REASON and any(u.phrase and (u.phrase in d or d.startswith(u.phrase)) for d in decided):
                continue  # decided by the subject pack (an elasticity or a margin worked as a division)
            reason = u.reason
            if _FOLD_ONLY_RE.search(u.phrase or "") and not _states_a_figure(u.sentence_text or ""):
                if para_text is None:
                    para_text = {pi: para for pi, _si, _sent, para in _sentences_for(report.original_response, reading)}
                if not _states_a_figure(para_text.get(u.paragraph, "")):
                    # 'doubled', 'twice', 'three times' in a paragraph that states no figure states no arithmetic to check (breadth item 13);
                    # in a paragraph of dated figures ('The point stands in 1930. Membership doubled in the decade.') the fold may be
                    # one of theirs, so it is still named undecided (round 4: reported, not skipped)
                    continue
            if reading.si:
                originals = _si_statement_texts(report, u, reading)
                if _restates_written_result(u.phrase, originals):
                    continue  # '(0.84 − 0.30) ÷ 0.30 × 100 = 180%, an increase of 180%': the STEM check decides the result it restates (c1 bi-p8d)
                if reason.startswith(_NO_FIGURES_REASON) and any(_DIGIT_IN_MATHS_RE.search(t) for t in originals):
                    # the sentence does state figures, in written maths the STEM checks read: say so, never 'no figures are stated'
                    reason = _MATHS_FIGURES_REASON + reason[len(_NO_FIGURES_REASON):]
            elif _WRITTEN_ONLY_REASON in reason and _restates_written_result(u.phrase, [u.sentence_text or ""]):
                # '= 200% Result: the peak discharge rose by 200%': the per cent restates the stated result of the sentence's written arithmetic,
                # which the worked-arithmetic check decides (or names undecided itself): never arithmetic of its own (round 9 second pass, c2 ge-p9c g3.2)
                continue
            grouped.setdefault((u.paragraph, u.sentence, reason), []).append(u)
        for (pi, si, reason), items in grouped.items():
            names = list(dict.fromkeys(u.phrase[:120] for u in items))
            shown, more = [], 0
            for name in names:
                if sum(len(x) + 4 for x in shown) + len(name) > 900:
                    more += 1
                    continue
                shown.append(name)
            phrases = "', '".join(shown) + (f"' and {more} more" if more else "'")
            what = ("states worked arithmetic" if reason == WORKED_EQUATION_REASON else "states figures in words" if reason == LONG_NUMBER_RUN_REASON
                    else "states a change between two figures" if reason == ARITH_ENDPOINT_REASON
                    else "states the direction of an exchange rate" if reason == XRATE_OPEN_REASON
                    else "states a derived figure or a relation over dated figures")
            if reading.si:  # the STEM claim of the statement (paragraph and statement numbers are the STEM claim ids)
                ids = _claims_for_si_statement(report, items[0].sentence_text, reading, pi, si)
            else:
                ids = list(dict.fromkeys(cid for u in items for cid in (_claims_for_statement(report, u.sentence_text, u.phrase) or _claims_for_statement(report, u.phrase, u.phrase)
                                                                          or _claims_mentioning(report, u.sentence_text))))
            out.append(StructuralFinding(code="CORE-QNT-001", severity="warning",
                                         message=f"paragraph {pi}, sentence {si} {what} ('{phrases}) that could not be checked: {reason[:600]}; the stated arithmetic was not checked",
                                         claim_ids=ids[:8],
                                         rule_source="numeric self-consistency: a stated change that cannot be bound to its figures is reported, not skipped"))
        return out

    @staticmethod
    def _self_certification(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:
        """CORE-SELF-001: verification-status vocabulary in the response body, or a verification label on a sentence
        (``markdown.verification_label``: "Verified: ...", "... (verified).", "..., as formally verified.", "Checked."), or a
        sentence the shared self-report reader names (``markdown.is_self_certification`` on the sentence with its quotations
        masked: "All calculations have been verified by the system and are confirmed.", "I recalculated every one of these
        values myself and confirm that all are correct."; round-9 push-check hold on the c2 clearance commit: the History and
        Economics branches named such a sentence only by the parser's advisory status, which no gate read). Every branch
        carries this pack, so every branch names the same sentences. An agent's statement about its own checking is advisory
        and ignored; status comes only from signed engine results. A label attached to content leaves the content a claim like
        any other (the parsers keep its role), so its message says so. The message never repeats the certifying words.

        Hold-fix round 2: the sentence is read by the one reader (``adapters.self_report``: normalised as the student sees it, a
        quotation masked only where attributed or analysed, read by vocabulary class), the vocabulary and the label are held to its
        vetoes (a named outside party's check, a worked check that shows its computation, a question), and the answer as written is
        read once more, paragraph by paragraph, line by line and cell by cell (``self_report.self_report_spots``), so a heading, a
        line or a cell no sentence of the branch's reading holds ("## All figures verified" in the STEM reading) is named too."""
        out: list[StructuralFinding] = []
        seen: set[str] = set()
        covered: list[str] = []  # the reading forms of the sentences named, so the answer-wide pass never names one twice
        # the SI reading reads a view with maths and quantities masked; a worked check ("Check: 2(4) + 3 = 11 ✓") shows its
        # computation only in the statement as written, so the vetoes also read that
        written = ({(p, n): report.original_response[a:b] for p, n, a, b in si_statements(report.original_response, reading.profile)}
                   if reading.si else {})
        for pi, si, sent, _para in _sentences_for(report.original_response, reading):
            # an outside party's check, a worked check, a question: never a self-report
            read = reading_form(sent)
            vetoed = not_a_self_report(read) or ((pi, si) in written and not_a_self_report(reading_form(written[(pi, si)])))
            # the vocabulary and the label read the sentence as the one reader does, a quotation attributed to a source or analysed
            # masked (hold-fix round 3: "Source A ... insists that \"every figure in this report has been checked and verified by the
            # Ministry\", which a historian should treat with caution" was named by the vocabulary inside the source's own words)
            vocabulary = self_cert_vocabulary(read) is not None and not vetoed  # the receipt and engine vocabulary, its content-word forms only in a frame
            label = None if (vocabulary or vetoed) else verification_label(read)
            # quotations masked only where attributed; a worked check the branch's reading masked is read as written
            semantic = not vocabulary and label is None and is_self_certification(sent) and not ((pi, si) in written and is_worked_check(written[(pi, si)]))
            if not vocabulary and label is None and not semantic:
                continue
            key = " ".join(sent.split())
            if key in seen:
                continue
            seen.add(key)
            covered.append(" ".join(reading_form(sent).split()))
            if (pi, si) in written:  # the statement as written (the SI view masks its quantities)
                covered.append(" ".join(reading_form(written[(pi, si)]).split()))
            if vocabulary:
                message = (f"paragraph {pi}, sentence {si} contains verification-status language (an agent certifying its own output or imitating a channel "
                           "receipt); agent self-reports are advisory and ignored, and no claim in that sentence counts as material")
            elif semantic:
                message = (f"paragraph {pi}, sentence {si} states that the answer or its items were checked, verified or confirmed (an agent certifying "
                           "its own output); agent self-reports are advisory and ignored, and the sentence is no claim of the answer and no evidence "
                           "that anything was checked")
            elif label.position == "whole":
                message = (f"paragraph {pi}, sentence {si} is nothing but a verification-status label (an agent certifying its own output); agent "
                           "self-reports are advisory and ignored, and the label is no claim of the answer and no evidence of a check")
            else:
                where = {"before": "in front of", "after": "after"}.get(label.position, "inside")
                message = (f"paragraph {pi}, sentence {si} carries a verification-status label {where} its content (an agent certifying its own output); "
                           "agent self-reports are advisory and ignored: the label is no evidence that anything was checked, and the content it is "
                           "attached to is a claim like any other")
            out.append(StructuralFinding(code="CORE-SELF-001", severity="warning", message=message, claim_ids=(_claims_for_si_statement(report, sent, reading, pi, si) if reading.si else _claims_mentioning(report, sent))[:8], rule_source="architecture: agent self-reports are advisory; the Overseer trusts only signed engine results"))
        # the answer as written, read by the one reader whatever this branch's sentence reading kept (a heading, a line, a table cell)
        for pno, piece in self_report_spots(report.original_response):
            key = " ".join(reading_form(piece).split())
            if not key or any(key in k or k in key for k in covered if k):
                continue
            covered.append(key)
            out.append(StructuralFinding(
                code="CORE-SELF-001", severity="warning",
                message=(f"paragraph {pno} of the answer as written holds a line, heading or table cell stating that the answer or its items were "
                         "checked, verified or confirmed (an agent certifying its own output); agent self-reports are advisory and ignored, and it "
                         "is no claim of the answer and no evidence that anything was checked"),
                claim_ids=_claims_mentioning(report, piece)[:8], rule_source="architecture: agent self-reports are advisory; the Overseer trusts only signed engine results"))
        return out

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """The report's own arithmetic and chronology as engine problems, each extractor on its own (a failure of one is reported by
        :meth:`checks` as CORE-INTERNAL-001, which reads the same extraction, and never discards the other), capped at
        :data:`MAX_FORMAL_CHECKS` per transmission (the rest are named by CORE-QNT-001 / CORE-CHR-001 in :meth:`checks`), under the
        pack's reading."""
        r = self._reading(report)
        out: list[FormalCheck] = []
        for build in (_quant_formal, _chronology_formal, _marks_formal, _figure_formal):
            if len(out) >= MAX_FORMAL_CHECKS:
                break  # nothing beyond the limit is built: the check-limit finding names it
            try:
                out += build(report, "core", MAX_FORMAL_CHECKS - len(out), r)
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
        # A pack that cannot even be loaded is a failing pack (round-8 clearance c1, overseer handoff item 4): it was skipped with no
        # finding, so an English answer whose checks never ran read as checked. ES-INTERNAL-001 names it, as a failure inside the
        # checks does, and the delivery policy counts it as unchecked working.
        try:
            from ..adapters.english_specialist.structural import structural_checks
        except Exception as exc:
            return [StructuralFinding(code="ES-INTERNAL-001", severity="warning", message=f"the English integrity pack could not be loaded ({type(exc).__name__}); its findings are missing from this receipt and the router must not treat the pack as passed", rule_source="hub integrity (a failing pack is reported, never silently skipped)")]
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
            for attribution in study_attributions(c.claim_text):
                if not c.source_refs:
                    f.append(StructuralFinding(code="PS-SRC-001", severity="warning", message=f"study attribution {attribution!r} has no knowledge-document or library grounding", claim_ids=[c.claim_id], rule_source="blueprint core operation (Psychology: Claim -> Study -> Link -> Evaluation); sources.md L5 (working rule)"))
            if re.search(r"\b(significant(?:ly)?|statistically)\b", c.claim_text, re.IGNORECASE) and not _PCT_RE.search(c.claim_text) and not re.search(r"\bp\s*[<=>]\s*0?\.\d+", c.claim_text):
                f.append(StructuralFinding(code="PS-STR-001", severity="info", message="'significant' used without a figure or p-value", claim_ids=[c.claim_id], rule_source="command terms C7 (quantities checked in parts; working rule)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        return []  # numeric self-consistency comes from CorePack


#: An elasticity named in full or by its abbreviation: 'price elasticity of demand', 'income elasticity of demand', 'PED', 'YED', 'XED', 'PES'.
_ELASTICITY_TERM = r"(?:(?:price|income|cross(?:-price)?)\s+elasticity\s+of\s+(?:demand|supply)|elasticity|\bPED\b|\bYED\b|\bXED\b|\bPES\b)"
_ELASTICITY_TERM_RE = re.compile(_ELASTICITY_TERM, re.IGNORECASE)
#: A signed figure of written working: an ASCII or Unicode minus, a currency sign, thousands separators ('−12.50', '$100,800', '-0.67').
_WORKED_NUM = r"[-+−]?\s?(?:US)?[$£€¥]?\s?[-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+−]?\s?(?:US)?[$£€¥]?\s?[-−]?\d+(?:\.\d+)?"
#: 'PED of −1.67', 'a price elasticity of demand of -0.5', 'the elasticity is 2': a stated value (not the first figure of a division).
_ELASTICITY_VALUE_RE = re.compile(rf"{_ELASTICITY_TERM}[^.;\n]{{0,80}}?(?:\b(?:is|was|of|equals|at)\b|=)\s*(?P<v>[-+−]?\d+(?:\.\d+)?)(?!\s*(?:%|per\s*cent|percent|[÷/×*]|\d))",
                                   re.IGNORECASE)
_PCT_SIGNED_RE = re.compile(r"(?<![\d.])([-+−]?\d{1,3}(?:\.\d+)?)\s*(?:per cent|percent(?!age)|%)")
#: Words naming the numerator (the quantity's change) and the denominator (the price's or income's change) of an elasticity.
_ELASTICITY_NUMERATOR_RE = re.compile(r"\b(?:quantity|quantities|demanded|demand|sales|sold|bought|purchases|supplied|output)\b", re.IGNORECASE)
_ELASTICITY_DENOMINATOR_RE = re.compile(r"\b(?:price|prices|income|incomes)\b", re.IGNORECASE)
#: One link of written working that divides two figures ('−12.50 ÷ 18.75', '(−12.50%) / (18.75%)') and the link after it that states the result.
#: The blank runs of the links are possessive (integration gate 2): the runs around each optional bracket and per cent sign were adjacent,
#: split in every way before a link of blanks failed (3.7 s at 4,000 blanks, k² to k³ steps); every run is followed by a bracket, a sign,
#: a figure or the end, so the links read are the same.
_DIVISION_LINK_RE = re.compile(rf"^\s*+\(?\s*+(?P<a>{_WORKED_NUM})\s*+%?\s*+\)?\s*+[÷/]\s*+\(?\s*+(?P<b>{_WORKED_NUM})\s*+%?\s*+\)?\s*+$")
#: A margin's working: '(A ÷ B) × 100', 'A ÷ B × 100', with currency signs.
_MARGIN_LINK_RE = re.compile(rf"^\s*+\(?\s*+(?P<a>{_WORKED_NUM})\s*+[÷/]\s*+(?P<b>{_WORKED_NUM})\s*+\)?\s*+[×x*]\s*+100\s*+$")
_RESULT_LINK_RE = re.compile(rf"^\s*(?P<c>{_WORKED_NUM})(?P<pct>\s*(?:%|per\s*cent|percent(?!age)))?(?![\d,.]*\d)")
_MARGIN_LABEL_RE = re.compile(r"\b(?:(?:gross|net|operating)\s+)?(?:profit\s+)?margin\b(?!\s+of\s+safety)", re.IGNORECASE)


def _worked_value(text: str) -> Fraction:
    """The exact value of one figure of written working ('−12.50', '$100,800', '- 0.67')."""
    t = re.sub(r"(?:US)?[$£€¥]|\s", "", text).replace("−", "-").replace(",", "")
    negative = t.count("-") % 2 == 1
    return -Fraction(t.replace("-", "").lstrip("+")) if negative else Fraction(t.replace("-", "").lstrip("+"))


def _rational(x: Fraction) -> dict:
    return {"op": "real", "value": f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)}


def _labelled_divisions(text: str, label_re: "re.Pattern[str]", link_re: "re.Pattern[str]", *, percent: bool) -> list[tuple[str, Fraction, Fraction, Fraction, str]]:
    """``(chain, a, b, stated, label)`` for every worked equation of ``text`` whose first link names ``label_re`` and which divides two figures
    (``link_re``) before a link stating the result: 'PED = −12.50 ÷ 18.75 = −0.67', 'Gross profit margin = (gross profit ÷ sales revenue) × 100
    = ($100,800 ÷ $201,600) × 100 = 50.00%'. A result in per cent is required when ``percent``."""
    from .quant import worked_equations
    out: list[tuple[str, Fraction, Fraction, Fraction, str]] = []
    for eq in worked_equations(text):
        chain = eq.phrase
        links = re.split(r"[=≈]", eq.statement)
        label = label_re.search(links[0])
        if label is None:
            continue
        for k in range(len(links) - 1, 0, -1):
            m, r = link_re.match(links[k - 1]), _RESULT_LINK_RE.match(links[k])
            if m is None or r is None or (percent and not r.group("pct")):
                continue
            try:
                a, b, c = _worked_value(m.group("a")), _worked_value(m.group("b")), _worked_value(r.group("c"))
            except (ValueError, ZeroDivisionError):
                break
            if b != 0:
                out.append((chain, a, b, c, " ".join(label.group(0).split())))
            break
    return out


def elasticity_equations(text: str) -> list[tuple[str, Fraction, Fraction, Fraction, str]]:
    """The elasticities a report works out as a division ('PED = −12.50 ÷ 18.75 = −0.67'): ``(chain, numerator, denominator, stated, term)``."""
    return _labelled_divisions(text, _ELASTICITY_TERM_RE, _DIVISION_LINK_RE, percent=False)


def margin_equations(text: str) -> list[tuple[str, Fraction, Fraction, Fraction, str]]:
    """The margins a report works out as '(A ÷ B) × 100 = m%': ``(chain, A, B, m, label)``."""
    return _labelled_divisions(text, _MARGIN_LABEL_RE, _MARGIN_LINK_RE, percent=True)


def _worked_branch(report: SpecialistReport) -> Optional[str]:
    """The prose branch whose pack decides the report's worked equations (:mod:`.worked`): ``economics``, ``business_management`` or
    ``generic`` (a subject no other default branch serves: Geography, a language B, ...); None for every other branch."""
    from ..translate.subjects import resolve_profile
    from .registry import BRANCHES
    key = resolve_profile(report.subject).key
    if key in ("economics", "business_management"):
        return key
    if any(key in b.profile_keys for b in BRANCHES if b.key != "generic"):
        return None
    return "generic"


def pack_decided_equations(report: SpecialistReport) -> set[str]:
    """The worked equations of ``report`` its subject pack decides (an elasticity on the Economics branch, a margin on the Business
    branch, and on those two branches and the generic branch every worked equation the worked-arithmetic reader reads,
    :mod:`.worked`), so the core pack does not also name them undecided: the undecided report and a verdict never both name a line."""
    from .worked import decided_worked_chains
    branch = _worked_branch(report)
    text = report.original_response
    if branch is None:
        return set()
    decided = decided_worked_chains(text)
    if branch == "economics":
        decided |= {chain for chain, *_rest in elasticity_equations(text)}
    elif branch == "business_management":
        decided |= {chain for chain, *_rest in margin_equations(text)}
    return decided


def _worked_checks(report: SpecialistReport, prefix: str, skip: set[str]) -> list[FormalCheck]:
    """The report's worked equations as engine problems (:func:`.worked.worked_problems`), each naming the claims of its statement;
    equations in ``skip`` are decided by the pack's own check (an elasticity, a margin)."""
    from ..ir.schema import Problem
    from .worked import breakdown_problems, clock_problems, payback_problems, worked_problems
    out: list[FormalCheck] = []
    built = worked_problems(report.original_response, report_id=report.report_id, request_id=report.request_id, prefix=prefix, skip=frozenset(skip))
    built += breakdown_problems(report.original_response, report_id=report.report_id, request_id=report.request_id, prefix=prefix)
    built += clock_problems(report.original_response, report_id=report.report_id, request_id=report.request_id, prefix=prefix)
    built += payback_problems(report.original_response, report_id=report.report_id, request_id=report.request_id, prefix=prefix)
    for wp in built:
        out.append(FormalCheck(check_id=f"{prefix}-{len(out) + 1}", kind="worked_arithmetic",
                               description=wp.description, problem=Problem.model_validate(wp.problem), expected_if_sound="ENTAILED",
                               claim_ids=tuple(_claims_for_statement(report, wp.statement, wp.phrase) or _claims_for_statement(report, wp.phrase, wp.phrase)),
                               policy="linear", failure_severity="error", inconsistent_is_failure=False))
    return out


def _ratio_check(check_id: str, kind: str, report: SpecialistReport, n: int, statement: str, phrase: str, a: Fraction, b: Fraction, stated: Fraction,
                 *, scale: Fraction, signed: bool, floor: Fraction, label: str, meanings: tuple[str, str]) -> FormalCheck:
    """``scale * a / b`` against the stated figure within the tolerance rule (5 per cent of the computed value, or ``floor``). With ``signed``
    the stated sign must be the computed one ('−12.50 ÷ 18.75 = 0.67' fails); otherwise magnitudes are compared."""
    from ..ir.schema import Problem
    from .quant import _within
    V = lambda name: {"op": "var", "name": name}  # noqa: E731
    ratio = {"op": "mul", "args": [_rational(scale), {"op": "div", "left": V("num"), "right": _rational(b)}]} if scale != 1 else {"op": "div", "left": V("num"), "right": _rational(b)}
    if not signed:
        if (a < 0) != (b < 0):
            ratio = {"op": "neg", "arg": ratio}
        concl = _within(ratio, abs(stated), Fraction(1, 20), floor)
    else:
        sign = -1 if stated < 0 else 1
        oriented = ratio if sign > 0 else {"op": "neg", "arg": ratio}
        concl = _within(oriented, abs(stated), Fraction(1, 20), floor)
    prob = {"problem_id": f"{kind}-{report.report_id}-{n}", "request_id": report.request_id, "claim_id": f"{report.report_id}:{kind}-{n}", "query": "entailment",
            "symbols": [{"name": "num", "sort": "Real", "meaning": meanings[0]}, {"name": "den", "sort": "Real", "meaning": meanings[1]}],
            "premises": [{"id": "NUM", "expr": {"op": "eq", "left": V("num"), "right": _rational(a)}, "label": f"{meanings[0]} = {_fmt_fraction(a)}", "grounding": {"kind": "supplied_text", "verified": True}},
                         {"id": "DEN", "expr": {"op": "eq", "left": V("den"), "right": _rational(b)}, "label": f"{meanings[1]} = {_fmt_fraction(b)}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "conclusion": {"id": kind.upper(), "expr": concl, "label": label[:1000]}}
    rule = ("tolerance: the stated figure must lie within 5% of the value computed from the report's own figures"
            + (f", or within {float(floor):g} of it" if floor else "") + ("; the stated sign must be the computed one" if signed else "; magnitudes compared"))
    return FormalCheck(check_id=check_id, kind=kind, description=f"{_excerpt_around(statement, phrase)} [{rule}]", problem=Problem.model_validate(prob),
                       claim_ids=tuple(_claims_for_statement(report, statement, phrase) or _claims_for_statement(report, phrase, phrase)))


def _quantity_first(sentence: str, p1: "re.Match[str]", p2: "re.Match[str]") -> bool:
    """Whether the first of two percentage changes of ``sentence`` is the quantity's (the elasticity's own term set aside). When a word
    naming the other change stands between them ('Quantity demanded fell by 10 per cent when price rose by 20 per cent'), each figure is
    the change of the word nearest before it; when both follow their words ('the quantity bought falls by proportionally less than the price
    rises (12.50% against 18.75%)'), they come in the order the words were last named."""
    masked = _ELASTICITY_TERM_RE.sub(lambda x: " " * len(x.group(0)), sentence)
    nums = [m.start() for m in _ELASTICITY_NUMERATOR_RE.finditer(masked)]
    dens = [m.start() for m in _ELASTICITY_DENOMINATOR_RE.finditer(masked)]

    def nearest(pos: int) -> Optional[str]:
        cands = [(x, "q") for x in nums if x < pos] + [(x, "p") for x in dens if x < pos]
        return max(cands)[1] if cands else None
    k1, k2 = nearest(p1.start()), nearest(p2.start())
    if any(p1.end() <= x < p2.start() for x in nums + dens) and k1 and k2 and k1 != k2:
        return k1 == "q"
    last_q = max((x for x in nums if x < p1.start()), default=None)
    last_p = max((x for x in dens if x < p1.start()), default=None)
    if last_p is None:
        return True
    if last_q is None:
        return False
    return last_q < last_p


def _fmt_fraction(x: Fraction) -> str:
    from .quant import _fmt
    return _fmt(x)


class EconomicsPack:
    name = "economics"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        text = report.original_response.lower()
        if "diagram" in text and not re.search(r"\b(shift|curve|axis|equilibrium|intersect)", text):
            f.append(StructuralFinding(code="EC-STR-001", severity="info", message="a diagram is mentioned but no curve, shift or equilibrium is described", rule_source="blueprint core operation (Economics: Define -> Model/Diagram -> Mechanism -> Apply -> Evaluate); working rule"))
        for c in report.claims:
            if _ELASTICITY_TERM_RE.search(c.claim_text) and not re.search(r"\d", c.claim_text):
                f.append(StructuralFinding(code="EC-STR-002", severity="info", message="elasticity asserted without a value or the percentage changes it is computed from", claim_ids=[c.claim_id], rule_source="command terms C7 (working rule)"))
        return f

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """An elasticity stated with the figures it is computed from: worked as a division ('PED = −12.50 ÷ 18.75 = −0.67': the quotient,
        sign included, against the stated result), or stated in prose with the two percentage changes on its line ('a PED of −1.67 means
        that the quantity bought falls by proportionally less than the price rises (12.50% against 18.75%)', 'the price elasticity of demand is
        0.5'): the quantity's change over the price's (or income's) change against the stated value, magnitudes compared. The term may be
        written in full or as PED, YED, XED or PES, with an ASCII or Unicode minus."""
        out: list[FormalCheck] = []
        n = 0
        text = report.original_response
        chains = elasticity_equations(text)
        for chain, a, b, c, term in chains:
            n += 1
            out.append(_ratio_check(f"economics-elasticity-{n}", "elasticity", report, n, chain, chain, a, b, c, scale=Fraction(1), signed=True, floor=Fraction(0),
                                    label=f"stated {term} {_fmt_fraction(c)} against {_fmt_fraction(a)} / {_fmt_fraction(b)} as worked", meanings=("the dividend as worked", "the divisor as worked")))
        worked = [chain for chain, *_rest in chains]
        for _pi, _si, sent, _para in _sentences_with_paragraph(text):
            if len(_PCT_SIGNED_RE.findall(sent)) < 2:
                continue
            for m in _ELASTICITY_VALUE_RE.finditer(sent):
                # the value and its two percentage changes stand on one line ('a PED of −1.67 means ... (12.50% against 18.75%)'); a result line
                # under lines of working ('Result: PED = −0.67') is read with its worked division, never with figures of other lines
                line_start = sent.rfind("\n", 0, m.start()) + 1
                line_end = sent.find("\n", m.end())
                raw_line = sent[line_start: line_end if line_end >= 0 else len(sent)]
                line = " ".join(raw_line.split())
                if any(w and w in line for w in worked):
                    continue  # the worked division of this line is checked above
                pcts = list(_PCT_SIGNED_RE.finditer(raw_line))
                if len(pcts) < 2:
                    continue
                stated = _worked_value(m.group("v"))
                first, second = abs(_worked_value(pcts[0].group(1))), abs(_worked_value(pcts[1].group(1)))
                q, p = (first, second) if _quantity_first(raw_line, pcts[0], pcts[1]) else (second, first)
                if p == 0:
                    continue
                n += 1
                phrase = " ".join(m.group(0).split())
                out.append(_ratio_check(f"economics-elasticity-{n}", "elasticity", report, n, line, phrase, q, p, stated, scale=Fraction(1), signed=False, floor=Fraction(0),
                                        label=f"stated elasticity {_fmt_fraction(abs(stated))} against {_fmt_fraction(q)} / {_fmt_fraction(p)} (the percentage changes its sentence states)",
                                        meanings=("percentage change in quantity", "percentage change in price or income")))
                break  # one stated value per sentence is read against its two percentage changes
        out += _worked_checks(report, "economics-worked", set(worked))
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
        """Margins stated with the figures they are computed from: margin = profit / revenue, in prose ('a profit of 50,000 on revenue of
        250,000 ... the profit margin is 20 per cent') or worked as '(A ÷ B) × 100 = m%' under a margin label ('Gross profit margin = (gross
        profit ÷ sales revenue) × 100 = ($100,800 ÷ $201,600) × 100 = 50.00%'), within the tolerance rule (or half a percentage point)."""
        out: list[FormalCheck] = []
        n = 0
        margins = margin_equations(report.original_response)
        for chain, a, b, m, label in margins:
            n += 1
            out.append(_ratio_check(f"business-margin-{n}", "margin", report, n, chain, chain, a, b, m, scale=Fraction(100), signed=True, floor=Fraction(1, 2),
                                    label=f"stated {label} {_fmt_fraction(m)} per cent against 100 * {_fmt_fraction(a)} / {_fmt_fraction(b)} as worked",
                                    meanings=("the numerator as worked (profit)", "the denominator as worked (revenue)")))
        for sent in _split_sentences(report.original_response):
            m = re.search(r"(?:profit|gross|net)\s+margin[^.]{0,60}?(\d{1,3}(?:\.\d+)?)\s*(?:per cent|percent|%)", sent, re.IGNORECASE)
            nums = re.findall(r"(?:profit|revenue|sales)\s+of\s+(?:\$|£|€)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|m|thousand|k)?", sent, re.IGNORECASE)
            if m and len(nums) >= 2:
                n += 1
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
                out.append(FormalCheck(check_id=f"business-margin-{n}", kind="margin", description=sent.strip()[:160], problem=Problem.model_validate(prob),
                                       claim_ids=tuple(_claims_for_statement(report, sent, m.group(0)))))
        out += _worked_checks(report, "business-worked", {chain for chain, *_rest in margins})
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
        """The report's worked equations as engine problems (:mod:`.worked`: 'Dependency ratio = 31 ÷ 69 × 100 = 44.9')."""
        return _worked_checks(report, "generic-worked", set())


#: argument diagnostics: a relation the request states ('Q = 1.6R + 4'), read before the STEM front end is run on a general branch
_REQUEST_RELATION_RE = re.compile(r"(?<![\w₀-₉])(?=[\w₀-₉]*?[A-Za-z])[\w₀-₉]++\s*+=\s*+[-−]?[\w(.√]")


def request_model_extrapolation(report: SpecialistReport, request_text: str) -> list[StructuralFinding]:
    """ST-RANGE-001 (stem_extrapolation) on a general branch (argument diagnostics, docs/ARGUMENT_DIAGNOSTICS.md section 3.4): the
    request states a model and the range of the data it was fitted on ("For eleven storms with rainfall totals between 10 mm and
    40 mm, the peak discharge fits the line Q = 1.6R + 4"), and the answer evaluates the model outside that range ("Q = 1.6 × 150
    + 4 = 244") with no caveat. The STEM front end reads it (its request-model reading, ``stem.relations``) on the answer as
    written and the request, under the general science profile; only that finding is kept, mapped to the claims of its
    statement. Silent when the request states no relation."""
    if not _REQUEST_RELATION_RE.search(request_text[:20000]) or not any(ch.isdigit() for ch in report.original_response[:200_000]):
        return []
    from ..stem.document import build_document
    from .stem_pack import _ClaimMap, _finding
    doc = build_document(report.original_response, request_text, "stem")
    claim_map = _ClaimMap(report, doc)
    return [_finding(x.code, x.severity, claim_map.relabel(x.message), claim_map.ids(x.statement_ids)) for x in doc.findings if x.code == "ST-RANGE-001"]
