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

import re
from fractions import Fraction
from functools import lru_cache
from typing import Iterator, Optional

from ..adapters.history_specialist.chronology import chronology_relations
from ..adapters.history_specialist.sentences import inner_sentences as _inner_sentences, split_sentences as _split_sentences, strip_json_spans
from ..adapters.markdown import MEMORY_LABEL_RE as _MEMORY_LABEL_RE, SELF_CERT_RE, cited_quotation_spans, dangling_quote_offset, find_quotation_spans, is_memory_label, unbalanced_double_quotes, uncited_quotation_spans
from ..adapters.sources import check_excerpt, strip_trailing_punctuation, uncredited_excerpt
from ..stem.si_reading import QuantReading, si_prose_view, si_quant_view, si_quote_view, si_statements
from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText
from ..translate.grounding import FORM_DIFFERS, check_claim_sources, find_quotation
from ..translate.subjects import resolve_profile
from .base import FormalCheck
from .quant import GENERAL, WORKED_EQUATION_REASON, extract_quant_checks, undecided_quant_statements, worked_equations

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
    sentences = [(sent, para) for _pi, _si, whole, para in _sentences_for(text, reading) for sent in _inner_sentences(whole)]
    for sent, para in sentences:
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
                               claim_ids=_quant_claims(report, qc, reading)))
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
    """One rule with the grounding checks and the channel (:func:`epinoic_logic.translate.grounding.is_peer_document`): an
    id, an author or a provenance that names a relayed agent's report (repair round 4, rerun-security-2 variant: the
    pack read only an author of the form '<subject>-specialist')."""
    from ..translate.grounding import is_peer_document
    return is_peer_document(t)


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


#: Words before a quoted word that say the text lacks it: 'has no "like"', 'never says "ayudar"', 'does not use "toda"', 'without "as"'.
_ABSENT_BEFORE_RE = re.compile(
    r"(?:\b(?:has|have|had|contains?|uses?|includes?|gives?|offers?)\s+no\s+(?:(?:word|words|term|mention|instance|use)\s+(?:of\s+|like\s+)?)?"
    r"|\b(?:never|nowhere)\s+(?:says?|uses?|writes?|mentions?|contains?|includes?|states?)\s+(?:the\s+word\s+)?"
    r"|\b(?:does|did|do)\s*(?:not|n['’]t)\s+(?:say|use|write|mention|contain|include|state)\s+(?:the\s+word\s+)?"
    r"|\blacks?\s+(?:the\s+word\s+)?|\bwithout\s+(?:the\s+word\s+|a\s+|an\s+)?|\bno\s+(?:word\s+)?|\bneither\s+)$", re.IGNORECASE)
#: What may stand between two quoted words of one absent mention: 'has no "like" or "as"', 'neither "like" nor "as"'.
_ABSENT_JOIN_RE = re.compile(r"^\s*(?:,\s*)?(?:or|nor|and)\s+$|^\s*,\s*$", re.IGNORECASE)


def _absent_mentions(text: str, spans: list[tuple[int, int, str]]) -> list[str]:
    """The quoted words of ``text`` that its sentence says the text lacks ('the bruise comparison has no "like" or "as"', 'the text never
    says "ayudar"'): a mention of a word, not a quotation of a text."""
    out: list[str] = []
    prev_absent_end: Optional[int] = None
    for s, e, inner in spans:
        before = text[max(0, s - 60): s]
        if _ABSENT_BEFORE_RE.search(before) or (prev_absent_end is not None and _ABSENT_JOIN_RE.match(text[prev_absent_end: s])):
            out.append(inner.strip())
            prev_absent_end = e
        else:
            prev_absent_end = None
    return out


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
    for prefix in ("s", "m", "c"):  # the STEM branches' claim ids (adapters.stem_specialist.parser.ID_PREFIXES)
        if prefix + sid in ids:
            return [prefix + sid]
    for p, n, a, b in si_statements(report.original_response, reading.profile):
        if p == paragraph and n == number:
            return _claims_mentioning(report, report.original_response[a:b])
    return _claims_mentioning(report, sentence)


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
        disagreeing, disputed = self._guarded("quotation references", lambda: self._quotation_ref_disagreements(report), f) if report.supplied_texts else ([], frozenset())
        f += disagreeing or []
        f += self._guarded("unverifiable quotations", lambda: self._unverifiable_quotations(report, has_memory_label, disputed or frozenset(), request_text, r), f) or []
        if report.supplied_texts:
            f += self._guarded("misattributed quotations", lambda: self._misattributed_quotations(report, r), f) or []
        f += self._guarded("quotation marks", lambda: self._unbalanced_quotation_marks(report, r), f) or []
        f += self._guarded("self-certification", lambda: self._self_certification(report, r), f) or []
        f += self._guarded("chronology", lambda: self._undecided_chronology(report, r), f) or []
        f += self._guarded("arithmetic", lambda: self._undecided_arithmetic(report, r), f) or []
        f += self._guarded("support links", lambda: self._support_cycles(report), f) or []
        f += self._guarded("check limit", lambda: self._formal_overflow(report, r), f) or []
        if not r.si and request_text:
            f += self._guarded("model range", lambda: request_model_extrapolation(report, request_text), f) or []
        if report.supplied_texts:
            f += self._guarded("table figures", lambda: table_figure_mismatches(report, request_text), f) or []
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
            if c.claim_role == "other":
                continue
            text, _removed = strip_json_spans(c.claim_text)
            quotes = [inner.strip() for _s, _e, inner in cited_quotation_spans(text) if len(inner.strip()) >= 4]
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
        spans = cited_quotation_spans(text)
        # a quoted span whose role is no quotation (a correction, a suggestion, a mention such as a quoted function word)
        # is the writer's own words: a parser's uncredited-quotation record of it is no unverifiable quotation either
        mentions = {_quote_key(q) for q in _absent_mentions(text, spans)} | {_quote_key(inner.strip()) for _s, _e, inner, _role in uncited_quotation_spans(text)}
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
        # a word quoted from a quotation the answer already gives ('the verb "killed"' after '"We killed him openly"') is that quotation's
        keys = [_quote_key(q) for q in quoted]
        quoted = [q for q, k in zip(quoted, keys) if not any(k != other and re.search(rf"(?<!\w){re.escape(k)}(?!\w)", other) for other in keys)]
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
        by_id = {t.document_id: t for t in texts}
        by_claim = {c.claim_id: c.claim_text for c in report.claims}
        out: list[StructuralFinding] = []
        seen: set[tuple[str, str]] = set()
        rule = "source integrity (attribute every quotation to the text that holds it; a colleague's words are not the author's and the author's are not the colleague's)"
        for _pi, _si, sent, _para in _sentences_for(report.original_response, reading, "quote"):
            sent, _removed = strip_json_spans(sent)
            spans = [(s, e, inner.strip()) for s, e, inner in cited_quotation_spans(sent) if len(inner.strip()) >= 4]
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
    def _undecided_arithmetic(report: SpecialistReport, reading: QuantReading = GENERAL) -> list[StructuralFinding]:
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
        if not reading.si:
            decided |= worked_formal_checks(report)[1]  # decided by the STEM chain checker (B25)
        units = undecided_quant_statements(report.original_response, reading=reading)
        # every derived figure's transcription test in one pass over the sentences and the supplied texts (security round 2)
        transcribed = iter(_transcribed_all([(u.sentence_text, u.phrase) for u in units if u.reason != WORKED_EQUATION_REASON], report.supplied_texts))
        for u in units:
            if u.reason == WORKED_EQUATION_REASON:
                if any(u.phrase and (u.phrase in d or d.startswith(u.phrase)) for d in decided):
                    continue  # decided by the subject pack (an elasticity or a margin worked as a division) or by the STEM chain checker
            elif next(transcribed):
                continue  # 'fell by 30%' as the supplied extract states it: a transcription, not the writer's arithmetic (B25)
            grouped.setdefault((u.paragraph, u.sentence, u.reason), []).append(u)
        for (pi, si, reason), items in grouped.items():
            names = list(dict.fromkeys(u.phrase[:120] for u in items))
            shown, more = [], 0
            for name in names:
                if sum(len(x) + 4 for x in shown) + len(name) > 900:
                    more += 1
                    continue
                shown.append(name)
            phrases = "', '".join(shown) + (f"' and {more} more" if more else "'")
            what = "states worked arithmetic" if reason == WORKED_EQUATION_REASON else "states a derived figure or a relation over dated figures"
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
        """CORE-SELF-001: verification-status vocabulary in the response body. An agent's
        statement about its own checking is advisory and ignored; status comes only from
        signed engine results. The message never repeats the certifying words."""
        out: list[StructuralFinding] = []
        seen: set[str] = set()
        for pi, si, sent, _para in _sentences_for(report.original_response, reading):
            if not SELF_CERT_RE.search(sent):
                continue
            key = " ".join(sent.split())
            if key in seen:
                continue
            seen.add(key)
            out.append(StructuralFinding(code="CORE-SELF-001", severity="warning", message=f"paragraph {pi}, sentence {si} contains verification-status language (an agent certifying its own output or imitating a channel receipt); agent self-reports are advisory and ignored, and no claim in that sentence counts as material", claim_ids=(_claims_for_si_statement(report, sent, reading, pi, si) if reading.si else _claims_mentioning(report, sent))[:8], rule_source="architecture: agent self-reports are advisory; the Overseer trusts only signed engine results"))
        return out

    def formal_checks(self, report: SpecialistReport) -> list[FormalCheck]:
        """The report's own arithmetic and chronology as engine problems, each extractor on its own (a failure of one is reported by
        :meth:`checks` as CORE-INTERNAL-001, which reads the same extraction, and never discards the other), capped at
        :data:`MAX_FORMAL_CHECKS` per transmission (the rest are named by CORE-QNT-001 / CORE-CHR-001 in :meth:`checks`), under the
        pack's reading."""
        r = self._reading(report)
        out: list[FormalCheck] = []
        for build in (_quant_formal, _chronology_formal):
            if len(out) >= MAX_FORMAL_CHECKS:
                break  # nothing beyond the limit is built: the check-limit finding names it
            try:
                out += build(report, "core", MAX_FORMAL_CHECKS - len(out), r)
            except Exception:  # noqa: BLE001 - checks() names the failing extractor (CORE-INTERNAL-001)
                continue
        if not r.si:  # the general reading: the worked equations go through the STEM chain checker (B25)
            try:
                out += worked_formal_checks(report)[0][:max(0, MAX_FORMAL_CHECKS - len(out))]
            except Exception:  # noqa: BLE001 - checks() names the failing reader (CORE-INTERNAL-001); its equations stay undecided
                pass
        return out[:MAX_FORMAL_CHECKS]

    def formal_checks_for(self, report: SpecialistReport, request_text: Optional[str]) -> list[FormalCheck]:
        """:meth:`formal_checks`, and with the request's text the unit companions of the worked equations that combine the
        request's quantities (accuracy round 2, V1I-06: :func:`request_unit_formal_checks`), within the same cap. A failure of
        :meth:`formal_checks` propagates as before (the hub names the pack's failing call)."""
        out = self.formal_checks(report)
        if request_text and not self._reading(report).si and len(out) < MAX_FORMAL_CHECKS:
            try:
                out += request_unit_formal_checks(report, request_text)[:MAX_FORMAL_CHECKS - len(out)]
            except Exception:  # noqa: BLE001 - the companions are additional readings; their equations' arithmetic is checked above
                pass
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


def _attribution_in_texts(names: str, year: str, texts) -> bool:
    """A study attribution ('Loftus and Palmer (1974)') is grounded by a supplied text that names it: every surname of the
    attribution and its year stand within 120 characters of the first surname in one text (the study summary the task
    supplies). A named study no supplied text mentions stays ungrounded (PS-SRC-001)."""
    surnames = [w for w in re.findall(r"[A-Z][a-z]+", names) if w not in ("And",)]
    if not surnames or not texts:
        return False
    year_re = re.compile(rf"(?<!\d){re.escape(year)}(?!\d)")
    first = re.compile(rf"\b{re.escape(surnames[0])}\b")
    for t in texts:
        body = t.text or ""
        for m in first.finditer(body[:400_000]):
            window = body[m.start(): m.start() + 120]
            if year_re.search(window) and all(re.search(rf"\b{re.escape(w)}\b", window) for w in surnames[1:]):
                return True
    return False


class PsychologyPack:
    """Studies must be grounded (name + year is an attribution, not evidence); figures must be self-consistent."""
    name = "psychology"

    def checks(self, report: SpecialistReport, request_text: Optional[str] = None) -> list[StructuralFinding]:
        f: list[StructuralFinding] = []
        for c in report.claims:
            for m in _STUDY_RE.finditer(c.claim_text):
                if not c.source_refs and not _attribution_in_texts(m.group(1), m.group(2), report.supplied_texts):
                    f.append(StructuralFinding(code="PS-SRC-001", severity="warning", message=f"study attribution {m.group(0)!r} has no knowledge-document or library grounding", claim_ids=[c.claim_id], rule_source="blueprint core operation (Psychology: Claim -> Study -> Link -> Evaluation); sources.md L5 (working rule)"))
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
_DIVISION_LINK_RE = re.compile(rf"^\s*\(?\s*(?P<a>{_WORKED_NUM})\s*%?\s*\)?\s*[÷/]\s*\(?\s*(?P<b>{_WORKED_NUM})\s*%?\s*\)?\s*$")
#: A margin's working: '(A ÷ B) × 100', 'A ÷ B × 100', with currency signs.
_MARGIN_LINK_RE = re.compile(rf"^\s*\(?\s*(?P<a>{_WORKED_NUM})\s*[÷/]\s*(?P<b>{_WORKED_NUM})\s*\)?\s*[×x*]\s*100\s*$")
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


def pack_decided_equations(report: SpecialistReport) -> set[str]:
    """The worked equations of ``report`` its subject pack decides (an elasticity on the Economics branch, a margin on the Business
    branch), so the core pack does not also name them undecided."""
    from ..translate.subjects import resolve_profile
    key = resolve_profile(report.subject).key
    if key == "economics":
        return {chain for chain, *_rest in elasticity_equations(report.original_response)}
    if key == "business_management":
        return {chain for chain, *_rest in margin_equations(report.original_response)}
    return set()


#: currency signs blanked in the worked view: the STEM reader would take '$' for a TeX delimiter, and a sign is no operand
_CURRENCY_RE = re.compile(r"(?:US|A|C|NZ|HK)?\$|[£€¥₹]")
#: the most worked equations of one report read by the STEM chain checker (the rest stay named by CORE-QNT-001)
_MAX_WORKED = 120


def _phrase_span(text: str, start: int, end: int, phrase: str) -> Optional[tuple[int, int]]:
    """Where ``phrase`` (written with single spaces) stands in ``text[start:end]``, whose own spacing may differ (line breaks
    and runs of spaces between its words), as offsets of ``text``; None when it does not occur."""
    words = phrase.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words[:200])
    m = re.compile(pattern).search(text, start, end)
    return (m.start(), m.end()) if m else None


def _transcribed(sentence: str, phrase: str, texts) -> bool:
    """The derived figure stands in a supplied text word for word, with its context: the phrase and up to three words of
    its sentence on each side (at least four words in all, at least two of them context) occur in the text as one run of
    words, case, punctuation and quotation marks aside ('burglaries fell by 30% on the CCTV streets' in the extract;
    'domestic sales grew by 8% in 2024' against 'In 2024 its domestic sales grew by 8%': the context may be shorter on one
    side, re-run review A-FA-QNT). The figure is then a transcription of the text, not the writer's arithmetic. The phrase is
    placed at its first occurrence in the sentence's words; a text is read on its first 400,000 characters. One test of
    :func:`_transcribed_all`."""
    return _transcribed_all([(sentence, phrase)], texts)[0]


class _PhraseFinder:
    """Every occurrence of a set of word sequences in a sequence of words, found in one pass over the words (a trie of the
    sequences with failure links, so no word of the text is read again for another sequence or another start)."""

    def __init__(self, phrases) -> None:
        self._next: list[dict[str, int]] = [{}]
        self._ends: list[Optional[tuple[str, ...]]] = [None]
        for phrase in phrases:
            state = 0
            for word in phrase:
                child = self._next[state].get(word)
                if child is None:
                    child = len(self._next)
                    self._next[state][word] = child
                    self._next.append({})
                    self._ends.append(None)
                state = child
            self._ends[state] = phrase
        self._fail = [0] * len(self._next)
        self._out = [0] * len(self._next)   # the nearest state on the failure chain (itself excluded) where a sequence ends
        level = list(self._next[0].values())
        while level:
            below: list[int] = []
            for state in level:
                for word, child in self._next[state].items():
                    f = self._fail[state]
                    while f and word not in self._next[f]:
                        f = self._fail[f]
                    target = self._next[f].get(word, 0)
                    self._fail[child] = target if target != child else 0
                    self._out[child] = target if self._ends[target] is not None else self._out[target]
                    below.append(child)
            level = below

    def occurrences(self, words) -> Iterator[tuple[int, tuple[str, ...]]]:
        """``(start, sequence)`` for every occurrence of every sequence in ``words``, in order of where each ends."""
        state = 0
        nxt, fail, ends, out = self._next, self._fail, self._ends, self._out
        for i, word in enumerate(words):
            while state and word not in nxt[state]:
                state = fail[state]
            state = nxt[state].get(word, 0)
            hit = state if ends[state] is not None else out[state]
            while hit:
                phrase = ends[hit]
                yield i - len(phrase) + 1, phrase
                hit = out[hit]


def _transcribed_all(items, texts) -> list[bool]:
    """:func:`_transcribed` for every ``(sentence, phrase)`` of ``items``, in order, in one pass over the distinct sentences
    and one over each supplied text (security round 2, SEC-V1: one test per derived figure read the figure's whole sentence
    and every supplied text again, so many figures beside a long text cost the product of the two).

    The test is read on words: a phrase or a window of the sentence's words stands in a text's words, joined by single
    spaces, exactly when it is a run of the text's words, since no word is empty or holds white space (``lexis.tokens``).
    So each sentence's words are read once for the first place of each phrase, and each text's words once for every place
    of every phrase that needs one, with the words around it; a window is found when the words on its two sides at one
    such place are the window's."""
    out = [False] * len(items)
    if not items or not texts:
        return out
    from .. import lexis
    sentence_words: dict[str, tuple[str, ...]] = {}
    phrase_words: dict[str, tuple[str, ...]] = {}
    for sentence, phrase in items:
        if phrase:
            if sentence not in sentence_words:
                sentence_words[sentence] = tuple(lexis.tokens(sentence))
            if phrase not in phrase_words:
                phrase_words[phrase] = tuple(lexis.tokens(phrase))
    wanted = {ph for ph in phrase_words.values() if ph}
    if not wanted:
        return out
    finder = _PhraseFinder(wanted)
    first: dict[str, dict[tuple[str, ...], int]] = {}
    for sentence, words in sentence_words.items():
        places: dict[tuple[str, ...], int] = {}
        for start, ph in finder.occurrences(words):
            if ph not in places:
                places[ph] = start   # occurrences come in order of their ends: the earliest start of a phrase comes first
        first[sentence] = places
    needed: dict[tuple[str, ...], set[tuple[tuple[str, ...], tuple[str, ...]]]] = {}
    windows: list[Optional[tuple[tuple[str, ...], list[tuple[tuple[str, ...], tuple[str, ...]]]]]] = []
    for sentence, phrase in items:
        ph = phrase_words.get(phrase, ()) if phrase else ()
        k = first[sentence].get(ph, -1) if ph else -1
        if k < 0:
            windows.append(None)
            continue
        sent = sentence_words[sentence]
        keys = []
        for left in (3, 2, 1, 0):
            for right in (3, 2, 1, 0):
                if left + right < 2 or left > k or k + len(ph) + right > len(sent) or len(ph) + left + right < 4:
                    continue
                keys.append((sent[k - left:k], sent[k + len(ph):k + len(ph) + right]))
        windows.append((ph, keys))
        if keys:
            needed.setdefault(ph, set()).update(keys)
    if not needed:
        return out
    found: dict[tuple[str, ...], set] = {ph: set() for ph in needed}
    text_finder = _PhraseFinder(needed)
    for t in texts:
        if not t.text:
            continue
        body = lexis.tokens(t.text[:400_000])
        for j, ph in text_finder.occurrences(body):
            want, got = needed[ph], found[ph]
            if len(got) == len(want):
                continue
            e = j + len(ph)
            for left in range(min(3, j) + 1):
                before = body[j - left:j]
                for right in range(min(3, len(body) - e) + 1):
                    key = (before, body[e:e + right])
                    if key in want:
                        got.add(key)
    for i, entry in enumerate(windows):
        if entry is not None:
            ph, keys = entry
            got = found.get(ph)
            out[i] = bool(got) and any(key in got for key in keys)
    return out


#: An equation written inside a bracket of another one ('$8,100 + ($1.80 × 3,500 = $6,300) = $14,400'): its expression, its '=' and its
#: result, with no bracket, '=' or line break inside.
_NESTED_EQ_RE = re.compile(r"\((?P<expr>[^()=≈\n]{1,200}?)(?P<eq>[=≈])(?P<res>[^()=≈\n]{1,60})\)")


def _nested_equations(text: str, a: int, b: int) -> list[tuple[int, int, int]]:
    """``(expression start, '=' position, result end)`` of every equation written inside a bracket of the equation at ``a``-``b``
    whose expression puts an operator between two figures and whose result is a figure ('($1.80 × 3,500 = $6,300)')."""
    from .quant import _OPERATOR_BETWEEN_RE, _RESULT_START_RE
    out: list[tuple[int, int, int]] = []
    for m in _NESTED_EQ_RE.finditer(text, a, b):
        expr, res = m.group("expr"), m.group("res")
        if _OPERATOR_BETWEEN_RE.search(" ".join(expr.split())) and _RESULT_START_RE.match(" " + res.strip()):
            out.append((m.start("expr"), m.start("eq"), m.end("res")))
    return out


@lru_cache(maxsize=16)
def _worked_view(text: str, skipped: frozenset[str]) -> tuple[str, tuple[tuple[int, int, str], ...], str]:
    """The worked equations of ``text`` (but those in ``skipped``, which the subject pack decides) as a view of the same
    length: each equation's arithmetic (its phrase, from the first link that computes to the stated result, with the further
    links of its chain) kept with its currency signs blanked and its own line breaks read as spaces (one equation is one line,
    so it never continues another equation's chain: '= $8,100 ÷ $2.70' under a label line whose words are blanked), every other
    character blank but line breaks. An equation written in a bracket of another ('$8,100 + ($1.80 × 3,500 = $6,300) =
    $14,400') is read twice: the outer equation with the inner result blanked ('8,100 + (1.80 × 3,500) = 14,400'), and the
    inner one in a second view of the same length that keeps only it (repair round 2, I1). Returns the view, ``(start, end,
    chain)`` per equation kept, and the second view ('' when no equation holds another)."""
    keep = bytearray(len(text))
    inner = bytearray(len(text))
    spans: list[tuple[int, int, str]] = []
    quoted = [(qa, qb) for qa, qb, _inner in find_quotation_spans(text)] if ('"' in text or "“" in text or "'" in text or "‘" in text) else []
    for eq in worked_equations(text)[:_MAX_WORKED]:
        if any(eq.phrase and (eq.phrase in d or d.startswith(eq.phrase)) for d in skipped):
            continue
        span = _phrase_span(text, eq.start, eq.end, eq.phrase)
        if span is None:
            continue
        a, b = span
        signs = [k for k in (text.find("=", a, b), text.find("≈", a, b)) if k >= 0]
        sign = min(signs) if signs else a
        if any((qa <= a and b <= qb) or qa <= sign < qb for qa, qb in quoted):
            # an equation inside quotation marks is a mention: another report's line the answer quotes ('its written lines "ln 8.04 +
            # 8 ln 10 = 2.084429" ... do not hold'), not the answer's own arithmetic (repair round 2, I3); CORE-QNT-001 still names it.
            # The phrase may open on the words before the quotation ('... flag its written lines "ln 8.04 + ...'): the equation is
            # quoted when its relation sign stands inside the quotation (repair round 4, E2E-HI-MENTION-READ-AS-OWN-ARITHMETIC)
            continue
        if eq.tail:
            # the further links of the chain ('= 95.0' after '= 92.0') are read with it: a check of the first result alone would leave
            # them unchecked while the equation counted as decided (repair round 2, I1)
            whole = _phrase_span(text, eq.start, eq.end, f"{eq.phrase} {eq.tail}")
            if whole is None or whole[0] != a:
                continue  # the tail cannot be located with the phrase: the equation stays undecided (CORE-QNT-001)
            b = whole[1]
        for i in range(a, b):
            keep[i] = 1
        for e0, q, e1 in _nested_equations(text, a, b):
            for i in range(q, e1):
                keep[i] = 0  # the outer equation reads the bracket's expression, not its stated result
            for i in range(e0, e1):
                inner[i] = 1
        spans.append((a, b, eq.chain))

    # each equation ends its statement: the character after it (its ';' or full stop, or a blank) is a line break in the view, so two
    # equations of one line ('... = $15,750; total costs ...') are never read as one chain (repair round 2, I1)
    ends = {b for _a, b, _ph in spans if b < len(text)}

    def _view(mask: bytearray) -> str:
        out = "".join((" " if ch == "\n" else ch) if mask[i] else ("\n" if ch == "\n" or i in ends else " ") for i, ch in enumerate(text))
        return _CURRENCY_RE.sub(lambda m: " " * len(m.group(0)), out)
    return _view(keep), tuple(spans), (_view(inner) if any(inner) else "")


_WORKED_CACHE: dict[tuple, tuple[list[FormalCheck], set[str]]] = {}
#: A request that states a relation between two quantities ("fits the line Q = 1.6R + 4"): a letter, a relation sign, an operand.
#: (security round 1) Read as a yes or no only, and from the start of a word only: a name ends where its word ends, so a letter
#: inside a word has the relation sign the word's start has. A search from every letter of a long word read the word again to
#: its end (quadratic: 3.5 s on a 19,000-letter request); from the word's start, once, with the name read possessively. The
#: request states a relation exactly when it did (tests/branches/test_security_round1_request_relation.py).
_REQUEST_RELATION_RE = re.compile(r"(?<![\w₀-₉])(?=[\w₀-₉]*?[A-Za-z])[\w₀-₉]++\s*+=\s*+[-−]?[\w(.√]")


#: A figure the answer states for a year: the figure, a per cent sign, scale word or unit of up to two words, then "in
#: <year>" ("rose sharply to 11.4% in 2020", "was 2.4 million in 2010"). A change ("by 3.2 points in 2020", "a 3% rise in
#: 2020", "a rise of 3% in 2020") states no level of the year and is not read.
_DATED_FIGURE_RE = re.compile(
    r"(?<![\w.,])(?P<n>\d+(?:\.\d+)?)(?P<u>\s*%|\s+per\s*cent|\s+percent)?(?P<w>(?:\s+(?!in\b)[a-z]+){0,2}?)\s+in\s+(?P<y>1[6-9]\d{2}|20\d{2})\b", re.IGNORECASE)
#: Words that make the figure before them a change, not a level of its year.
_DATED_CHANGE_WORDS = frozenset({"rise", "fall", "increase", "decrease", "growth", "drop", "decline", "change", "gain", "loss", "points", "point",
                                 "percentage", "jump", "cut", "reduction"})
#: Words a clause of a trend may hold besides its quantity: the clause inherits the sentence's quantity then.
_TREND_WORDS = frozenset("""
rose rise rising risen fell fall falling fallen reached reaching climbed climbing grew growing dropped dropping declined declining
increased increasing decreased decreasing jumped jumping soared soaring sank sinking slumped recovered recovering peaked peaking
then before after later sharply steeply rapidly slightly gradually dramatically again back further finally stood standing was were
had its their it they level highest lowest value period year years
""".split())
#: Words of a table's title that name no quantity.
_TABLE_TITLE_STOP = frozenset({"table", "figure", "fig", "graph", "chart", "data", "source", "extract", "supplied", "text", "in", "of", "the", "a",
                               "an", "and", "for", "by", "per", "cent", "percent", "millions", "thousands", "billions"})


#: A line of a dated series: a year, an optional separator, one figure and an optional unit word. (security round 1) Every
#: quantifier is possessive: each one's longest reading is the only one the rest of the line can follow (white space before
#: a separator, digits before white space or a unit), so a line that is no series line fails in one pass. Read with
#: backtracking, a year followed by a long run of spaces and a word was quadratic in the run, and one line of a supplied text
#: can be 400,000 characters (tests/branches/test_security_round1_dated_series.py).
_DATED_LINE_RE = re.compile(r"\s*+(1[6-9]\d{2}|20\d{2})\s*+[:=\-–|,]?+\s*+(-?\d++(?:\.\d++)?+)\s*+(?:%|[a-z]{0,12}+)?+\s*+$", re.IGNORECASE)


def _dated_series(text: str) -> dict[int, list[tuple[Fraction, str]]]:
    """``{year: [(value, as written)]}`` of a supplied data text written one year a line ("2020: 8.9", "2020 - 8.9",
    "2020 8.9"): the lines whose first token is a year followed by one figure. Bounded: the first 400 lines."""
    out: dict[int, list[tuple[Fraction, str]]] = {}
    for line in text.splitlines()[:400]:
        m = _DATED_LINE_RE.match(line)
        if m:
            try:
                out.setdefault(int(m.group(1)), []).append((Fraction(m.group(2)), m.group(2)))
            except (ValueError, ZeroDivisionError):
                continue
    return out


def _half_unit(written: str) -> Fraction:
    """Half a unit of the last digit of a figure as written ("8.9": 0.05)."""
    return Fraction(1, 2 * 10 ** len(written.partition(".")[2]))


def _table_matches(answer: Fraction, written: str, table: Fraction, table_written: str) -> bool:
    """Whether the answer's figure states the table's: equal within half a unit of the last digit either writes (a rounding
    either way: "9%" for 8.9, "8.9" for 8.94), in the same scale or in another one (a power of 1,000: "2,400,000" for 2.4
    millions; or per cent as a fraction: "0.089" for 8.9 %)."""
    eps = Fraction(1, 10 ** 9)
    for factor in (1, 100, 1000, 10 ** 6, 10 ** 9):
        if abs(answer - table * factor) <= max(_half_unit(written), _half_unit(table_written) * factor) + eps:
            return True
        if abs(answer * factor - table) <= max(_half_unit(written) * factor, _half_unit(table_written)) + eps:
            return True
    return False


def table_figure_mismatches(report: SpecialistReport, request_text: Optional[str]) -> list[StructuralFinding]:
    """CORE-SRC-007 (warning; repair round 4, ADV4-12): a figure the answer states for a year ("rose sharply to 11.4% in
    2020") in a claim about the quantity of a supplied data text written one year a line ("Table 1: Unemployment rate in
    Country P (%)" ... "2020: 8.9"), where the request or the claim's sentence names that text ("Using Table 1", "According
    to Table 1"), while the text states another figure for that year. The figure is invented when the text states it for
    no year (``invented_figure``), else the claim states another year's figure (``source_mismatch``). The claim's clause
    must name the text's quantity (a word of its title), or hold only trend words and take the sentence's quantity, so a
    figure of another quantity ("while inflation fell to 1.2% in 2020") is never read against the table. A figure equal to
    the table's within half a unit of the last digit either writes, or in another scale (millions, per cent as a fraction),
    states it. Bounded: 64 claims, 16 figures each."""
    from ..adapters.sources import document_mentions
    from ..translate.grounding import is_peer_document
    tables = []
    for doc in report.supplied_texts:
        if is_peer_document(doc):
            continue
        series = _dated_series(doc.text or "")
        if len(series) < 3:
            continue
        title = (doc.text or "").splitlines()[0] if doc.text else ""
        words = {w for w in re.findall(r"[a-z]+", (title + " " + (doc.title or "")).casefold()) if w not in _TABLE_TITLE_STOP and len(w) > 2}
        tables.append((doc, series, words))
    if not tables:
        return []
    out: list[StructuralFinding] = []
    for c in [c for c in report.claims if c.claim_role != "other"][:64]:
        sentence = c.claim_text or ""
        for doc, series, words in tables:
            named = bool(document_mentions(sentence, doc)) or bool(request_text and document_mentions(request_text[:20000], doc))
            if not named or not words:
                continue
            sentence_words = set(re.findall(r"[a-z]+", sentence.casefold()))
            for m in list(_DATED_FIGURE_RE.finditer(sentence))[:16]:
                year = int(m.group("y"))
                stated = series.get(year)
                if not stated:
                    continue
                gap_words = set(re.findall(r"[a-z]+", (m.group("w") or "").casefold()))
                before = sentence[max(0, m.start() - 24):m.start()].casefold()
                if gap_words & _DATED_CHANGE_WORDS or re.search(r"\b(?:by|of)\s*$", before):
                    continue
                clause = re.split(r"[;,]|\bwhile\b|\bwhereas\b|\bbut\b|\band\b", sentence[:m.start()], flags=re.IGNORECASE)[-1]
                clause_words = {w for w in re.findall(r"[a-z]+", clause.casefold()) if len(w) > 2} - _TREND_WORDS - _TABLE_TITLE_STOP
                about = bool(clause_words & words) or (not clause_words and bool(sentence_words & words))
                if not about:
                    continue
                written = m.group("n")
                try:
                    value = Fraction(written)
                except (ValueError, ZeroDivisionError):
                    continue
                if any(_table_matches(value, written, v, w) for v, w in stated):
                    continue
                elsewhere = sorted(y for y, vs in series.items() if y != year and any(_table_matches(value, written, v, w) for v, w in vs))
                shown = ", ".join(w for _v, w in stated)
                where = (f"and states {written} for {', '.join(map(str, elsewhere[:3]))}: another year's figure" if elsewhere
                         else f"and states {written} for no year")
                out.append(StructuralFinding(
                    code="CORE-SRC-007", severity="warning", claim_ids=[c.claim_id], rule_source="source integrity (figures read from a supplied table)",
                    message=(f"claim {c.claim_id} states {written}{m.group('u') or ''} for {year}, read from {doc.document_id} ({(doc.title or doc.document_id)[:60]}), "
                             f"which states {shown} for {year} {where}")[:600]))
    return out


def request_model_extrapolation(report: SpecialistReport, request_text: str) -> list[StructuralFinding]:
    """ST-RANGE-001 (stem_extrapolation) on a general branch (repair round 3, V3-H2-STEM-MISSES): the request states a model
    and the range of the data it was fitted on ("For eleven storms with rainfall totals between 10 mm and 40 mm, the peak
    discharge fits the line Q = 1.6R + 4"), and the answer evaluates the model outside that range ("Q = 1.6 × 150 + 4 = 244")
    with no caveat. The STEM front end reads it (its request-model reading, ``stem.relations``) on the answer as written
    and the request, under the general science profile; only that finding is kept, mapped to the claims of its statement.
    Silent when the request states no relation."""
    if not _REQUEST_RELATION_RE.search(request_text[:20000]) or not any(ch.isdigit() for ch in report.original_response[:200_000]):
        return []
    from ..stem.document import build_document
    from .stem_pack import _ClaimMap, _finding
    doc = build_document(report.original_response, request_text, "stem")
    claim_map = _ClaimMap(report, doc)
    return [_finding(x.code, x.severity, claim_map.relabel(x.message), claim_map.ids(x.statement_ids)) for x in doc.findings if x.code == "ST-RANGE-001"]


def worked_formal_checks(report: SpecialistReport) -> tuple[list[FormalCheck], set[str]]:
    """The worked equations of a report on a general (non-STEM) branch, decided by the STEM chain checker (B25): the
    equations' arithmetic is read by ``stem.build_document`` on a same-length view that keeps only it (currency signs
    blanked, offsets kept; an equation inside a bracket of another is read in a second view, :func:`_worked_view`) and checked
    by ``stem.checks.build_checks`` under the STEM tolerance rule, one engine problem per link, each naming the claims that hold
    it, in the readings the STEM checker gives a figure (as written, or in SI). Its SI-unit companion (ST-UNIT-003) is a STEM
    convention and is not built here: a geography rate per 1,000 divided by 10 is per cent as written (the companion of a
    working of the request's own quantities is :func:`request_unit_formal_checks`). Returns the formal checks
    (ids ``core-stem-…``, ``core-nested-stem-…`` for the second view) and the chains of the equations they decide: an equation is
    decided only when every link of its chain ('=' or '≈') has a check whose relation stands inside it and no link of it is
    named undecided by the chain checker; any other equation stays named by CORE-QNT-001 (repair round 2, I1: a check of the
    first link alone, or of another equation of the same statement, decided nothing else). The STEM front end's own findings
    on the view are not reported (its prose is blank by construction)."""
    key = (report.report_id, report.request_id, report.response_sha256, report.subject, tuple((c.claim_id, c.claim_text) for c in report.claims))
    hit = _WORKED_CACHE.get(key)
    if hit is not None:
        return hit
    from dataclasses import replace as _replace
    from ..stem.checks import build_checks
    from ..stem.document import build_document
    from ..ir.schema import Problem
    from ..named import DEFECT_LABELS
    from .stem_pack import _ClaimMap
    text = report.original_response
    view, spans, nested_view = _worked_view(text, frozenset(pack_decided_equations(report)))
    checks: list[FormalCheck] = []
    decided: set[str] = set()
    built: dict[tuple[int, int], int] = {}  # equation span -> the checks built over it (one per link of the chain at least)
    open_spans: set[tuple[int, int]] = set()
    for prefix, one_view in (("core-", view), ("core-nested-", nested_view)):
        if not spans or not one_view.strip():
            continue
        doc = build_document(one_view, None, "stem")
        plan = build_checks(doc, report_id=report.report_id, request_id=report.request_id, relay=True)
        claim_map = _ClaimMap(report, _replace(doc, text=text))  # claims are found in the answer as written (currency signs included)
        # each planned check reads one relation of the view, found by its check id with its characters: an equation is covered by
        # the checks whose relations stand inside it, not by every check of the statement that holds it; a link the chain checker
        # could not build a check for (an ST finding at warning) leaves the equation undecided
        where = {rel.check_id: (rel.start, rel.end) for rel in doc.checks if rel.check_id}
        unbuilt = [where[f.check_id] for f in plan.findings if f.severity != "info" and f.check_id in where]
        open_spans |= {(a, b) for a, b, _ph in spans if any(s0 < b and a < e0 for s0, e0 in unbuilt)}
        for pc in plan.checks:
            if pc.relation_kind == "unit":
                continue  # the STEM SI-unit companion: '(31 − 11) ÷ 10 = 2.0%' turns a rate per 1,000 into per cent as written
            at = where.get(pc.check_id)
            if at is None:
                continue
            covered = [(a, b, ph) for a, b, ph in spans if at[0] < b and a < at[1]]
            if not covered:
                continue
            try:
                problem = Problem.model_validate(pc.problem)
            except Exception:  # noqa: BLE001 - a problem the IR refuses is never run; its equation stays undecided
                continue
            checks.append(FormalCheck(check_id=f"{prefix}{pc.check_id}", kind=pc.kind, description=claim_map.relabel(pc.description), problem=problem,
                                      expected_if_sound=pc.expected_if_sound, claim_ids=tuple(claim_map.ids(pc.claim_ids, limit=None)), policy=pc.policy,
                                      failure_severity="warning" if pc.failure_severity == "warning" else "error",
                                      inconsistent_is_failure=pc.inconsistent_is_failure, defect=pc.defect if pc.defect in DEFECT_LABELS else None))
            for a, b, _ph in covered:
                built[(a, b)] = built.get((a, b), 0) + 1
    # an equation is decided when every link of its chain has a check: '= 92.0 = 2^k = 95.0' has three links and one check
    decided.update(ph for a, b, ph in spans if (a, b) not in open_spans and built.get((a, b), 0) >= max(1, text[a:b].count("=") + text[a:b].count("≈")))
    out = (checks, decided)
    if len(_WORKED_CACHE) > 32:
        _WORKED_CACHE.clear()
    _WORKED_CACHE[key] = out
    return out


_REQUEST_UNIT_CACHE: dict[tuple, list[FormalCheck]] = {}


def request_unit_formal_checks(report: SpecialistReport, request_text: str) -> list[FormalCheck]:
    """:func:`_request_unit_checks` of a report on a general branch, on the same view of its worked equations as
    :func:`worked_formal_checks` reads (accuracy round 2, V1I-06); cached per report and request."""
    key = (report.report_id, report.request_id, report.response_sha256, report.subject, tuple((c.claim_id, c.claim_text) for c in report.claims),
           request_text)
    hit = _REQUEST_UNIT_CACHE.get(key)
    if hit is not None:
        return list(hit)
    text = report.original_response
    view, spans, _nested = _worked_view(text, frozenset(pack_decided_equations(report)))
    out = _request_unit_checks(report, text, view, request_text) if spans and view.strip() else []
    if len(_REQUEST_UNIT_CACHE) > 32:
        _REQUEST_UNIT_CACHE.clear()
    _REQUEST_UNIT_CACHE[key] = out
    return list(out)


def _request_unit_checks(report: SpecialistReport, text: str, view: str, request_text: str) -> list[FormalCheck]:
    """The traced unit companions (ST-UNIT-003, ``stem_unit_error``, warning) of the worked equations whose every numeral
    repeats a quantity the request states with its unit, or states it in SI (accuracy round 2, V1I-06: 'Total distance = 1.2 +
    300 = 301.2 m' for a walk of 1.2 km and 300 m, 'V = 50 × 12 = 600 m³' for 12 mm of rain on 50 m², which the general
    branches checked as plain arithmetic). The view is read again with the request (``stem.build_document``) and only these
    companions are kept: every traced number of one is a request's quantity (``stem.relations``, the companion of a working that
    substitutes into no symbol), so a number of the answer's own, a conversion factor or a rate per 1,000 builds none. Each
    reads the numerals in the request's units: the numbers combined without their conversion fail it."""
    from dataclasses import replace as _replace
    from ..stem.checks import build_checks
    from ..stem.document import build_document
    from ..ir.schema import Problem
    from .stem_pack import _ClaimMap
    doc = build_document(view, request_text, "stem")
    plan = build_checks(doc, report_id=report.report_id, request_id=report.request_id, relay=False)
    claim_map = _ClaimMap(report, _replace(doc, text=text))
    traced = {rel.check_id for rel in doc.checks if rel.check_id and rel.kind == "unit" and rel.unit_case == "traced" and rel.traced
              and all(bd.source == "request" and not bd.symbol for _a, _b, bd in rel.traced)}
    out: list[FormalCheck] = []
    for pc in plan.checks:
        if pc.relation_kind != "unit" or pc.check_id not in traced or pc.defect != "stem_unit_error":
            continue
        try:
            problem = Problem.model_validate(pc.problem)
        except Exception:  # noqa: BLE001 - a problem the IR refuses is never run
            continue
        out.append(FormalCheck(check_id=f"core-req-{pc.check_id}", kind=pc.kind, description=claim_map.relabel(pc.description), problem=problem,
                               expected_if_sound=pc.expected_if_sound, claim_ids=tuple(claim_map.ids(pc.claim_ids, limit=None)), policy=pc.policy,
                               failure_severity="warning", inconsistent_is_failure=pc.inconsistent_is_failure, defect="stem_unit_error"))
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
        for chain, a, b, m, label in margin_equations(report.original_response):
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
