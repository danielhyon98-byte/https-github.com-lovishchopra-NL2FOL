"""Deterministic structural checks for English specialist answers.

Every check here is code over text. None is a solver result and none judges the
quality of a reading. The rules are *working rules* taken from the English
specialist's own knowledge documents (master prompt non-negotiables, paragraphs.md,
formatting.md, application.md); they are not official IB rules, and every finding
says so in ``rule_source``.

Codes (stable; add, never rename)
---------------------------------
Source integrity
* ``ES-SRC-001`` error   quotation not found in the supplied text it cites (verbatim,
                          normalized, or in any recognised adjusted form), or cites an
                          unknown document. An undisclosed quotation from memory
                          surfaces here: the message says the excerpt may be invented,
                          altered, or quoted from memory without the disclosure.
* ``ES-SRC-002`` error   a location citation (``(p. 48)``, ``(García Márquez, p. 48)``,
                          ``(ch. 3, p. 49)``, ``Act 1 Scene 2``, ``(1.2.34)``, ``line 12``,
                          ``page 48``, ``Chapter 3`` ...) whose scheme no supplied text
                          declares (``locator_scheme``): the location cannot be
                          verified and must never be invented.
* ``ES-SRC-003`` warning the answer says a quotation is from memory ("from memory",
                          "as I recall", "if memory serves" ...). The phrase is searched
                          outside the sentence's quotations, and a quotation located in a
                          supplied text (a colleague's own disclosure, quoted exactly) does
                          not count: the disclosure is the quoted author's, not the quoter's.
                          The phrase must be a disclosure: an unlocated quotation in the
                          sentence, a quotation word, or the method's own label set aside by
                          ``split_note_clauses`` (not one about dates and figures only); "from
                          memory" as part of the argument ("the speaker recalls the scene from
                          memory") is not a finding.
* ``ES-SRC-004`` warning a quotation with no supplied text to check it against.
* ``ES-SRC-005`` warning a quotation found only by joining separate spans of the text
                          without marking the omission (formatting.md S12: quote exactly).
* ``ES-SRC-006`` warning a quotation whose words are in the text but whose form differs
                          (initial capital changed, verse line-break mark omitted, or an
                          elision longer than the elision window whose fragments all occur
                          in order): S12, but not an invented quotation; the same case the
                          channel reports as INT-REQ-010, never ES-SRC-001.
* ``ES-SRC-007`` info    an elided quotation (``...``); the span it covers is stated.
* ``ES-SRC-008`` error / warning a quotation attributed by the sentence to one supplied text
                          (its author, title or the peer specialist named) but located only in
                          another: an error when a relayed colleague's report is involved
                          (the poem's words credited to the colleague, or the colleague's to
                          the poet), a warning between two literary texts.
  When no supplied text contains an excerpt, the ``ES-SRC-001`` message lists every text
  searched.

Structure (paragraphs.md)
* ``ES-STR-001`` warning a body paragraph with fewer than two quotations of at least two
                          words: proxy for P7, one idea carried by two strands.
* ``ES-STR-002`` info    a body paragraph outside 230-390 words: proxy for P13 ("the model
                          runs about 350 words. Paragraphs the user accepted ran from
                          roughly 230 to 390 words"). Not raised when the request text
                          passed to :func:`structural_checks` sets a word count.
  Neither applies to outline, plan or bullet deliverables (``task_type``) nor to
  heading, list or meta blocks.

Meta-text (master_prompt.txt internal-processing visibility rule, non-negotiable 3)
* ``ES-META-001`` warning a block or sentence that narrates checks or steps, certifies the
                          answer's own accuracy or is a pasted receipt (``VERIFIED: all claims
                          checked and confirmed.``, "I have checked ...", "every figure in this
                          paragraph is accurate", a JSON-shaped line): it is not analysis,
                          provides no evidence and plays no part in verification, wherever it
                          stands and whether or not it carries quotation marks.

Style (formatting.md)
* ``ES-STY-001`` info    first person (I, we, my, our, me, us) outside quotations: S2
                          (a Roman numeral ``I`` after Act/Part/Book ... is not first person).
* ``ES-STY-002`` info    British and American spellings mixed in one answer (-ise/-ize,
                          -yse/-yze, -our/-or, -re/-er, -ce/-se and other paired forms): S18.
* ``ES-STY-003`` warning a sentence that is only a quotation: S11, embed every quotation.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from ...translate.common import truncate
from ...translate.contracts import SpecialistReport, StructuralFinding
from ..generic_structured import generic_source_findings
from ..markdown import split_note_clauses
from ..sources import check_excerpt, strip_trailing_punctuation
from .parser import (
    Paragraph, Sentence, documents_named, excerpt_located, is_meta_sentence, is_peer_document, long_elision_of, segment, strip_quotations,
)

__all__ = [
    "structural_checks", "RULE_SOURCES", "MIN_STRAND_QUOTATIONS", "MIN_QUOTATION_WORDS",
    "BODY_WORDS_MIN", "BODY_WORDS_MAX", "OUTLINE_TASK_RE", "WORD_BOUND_RE", "citation_schemes", "find_citations",
    "attribution_findings", "memory_findings", "source_findings",
]

_WORKING = " (working rule, not an official IB rule)"
RULE_SOURCES: dict[str, str] = {
    "ES-SRC-001": "english_specialist/master_prompt.txt non-negotiable 1, source integrity" + _WORKING,
    "ES-SRC-002": "english_specialist/master_prompt.txt non-negotiable 1 and resolved conflict 12, citations" + _WORKING,
    "ES-SRC-003": "english_specialist/application.md section 8, source integrity" + _WORKING,
    "ES-SRC-004": "english_specialist/master_prompt.txt non-negotiable 1, source integrity" + _WORKING,
    "ES-SRC-005": "english_specialist/formatting.md S12" + _WORKING,
    "ES-SRC-006": "english_specialist/formatting.md S12, quotation form" + _WORKING,
    "ES-SRC-007": "english_specialist/formatting.md S12, elided quotation" + _WORKING,
    "ES-SRC-008": "english_specialist/master_prompt.txt non-negotiable 1, attribution of quotations" + _WORKING,
    "ES-STR-001": "english_specialist/paragraphs.md P7" + _WORKING,
    "ES-STR-002": "english_specialist/paragraphs.md P13" + _WORKING,
    "ES-META-001": "english_specialist/master_prompt.txt visibility rule and non-negotiable 3" + _WORKING,
    "ES-STY-001": "english_specialist/formatting.md S2" + _WORKING,
    "ES-STY-002": "english_specialist/formatting.md S18" + _WORKING,
    "ES-STY-003": "english_specialist/formatting.md S11" + _WORKING,
}

MIN_STRAND_QUOTATIONS = 2
MIN_QUOTATION_WORDS = 2
#: paragraphs.md P13: the model runs about 350 words; accepted paragraphs ran from roughly 230 to 390.
BODY_WORDS_MIN = 230
BODY_WORDS_MAX = 390
_EXCERPT_CHARS = 80
#: Deliverables whose blocks are not prose paragraphs; P7 and P13 do not apply to them.
OUTLINE_TASK_RE = re.compile(r"outline|plan|bullet|notes?", re.IGNORECASE)
#: A word count set by the request ("no more than 300 words", "about 250 words", "250-300 words"): P13 then yields to it.
WORD_BOUND_RE = re.compile(r"\b\d{2,4}(?:\s*(?:-|–|to)\s*\d{2,4})?\s+words\b", re.IGNORECASE)

# --- citations -----------------------------------------------------------------------
_TOKEN_SCHEME: dict[str, str] = {
    "p": "page", "pp": "page", "page": "page", "pages": "page",
    "l": "line", "ll": "line", "line": "line", "lines": "line",
    "para": "paragraph", "paras": "paragraph", "paragraph": "paragraph", "paragraphs": "paragraph",
    "ch": "custom", "chapter": "custom", "chapters": "custom", "stanza": "custom", "stanzas": "custom",
    "canto": "custom", "cantos": "custom", "verse": "custom", "verses": "custom", "part": "custom", "parts": "custom",
    "book": "custom", "books": "custom", "sonnet": "custom",
    "sc": "act_scene_line", "scene": "act_scene_line", "scenes": "act_scene_line", "act": "act_scene_line",
}
_LOCATOR_TOKEN = (
    r"(?:pp?|pages?|ll?|lines?|paras?|paragraphs?|ch|chapters?|stanzas?|cantos?|verses?|parts?|books?|sonnet|sc|scenes?)"
)
_RANGE = r"\d+(?:\s*[-–—]\s*\d+)?"
_TOKEN_IN_TEXT_RE = re.compile(r"\b(" + _LOCATOR_TOKEN + r")\.?\s*\d", re.IGNORECASE)
_ACT_SCENE_RE = re.compile(r"\bAct\b|\b(?:\d+|[IVXivx]+)\.(?:\d+|[IVXivx]+)\.\d+")
#: Generic words that look like "Name 12" inside parentheses but are not author-page citations.
_NOT_AUTHORS = frozenset({
    "example", "examples", "figure", "fig", "table", "question", "questions", "criterion", "criteria", "section",
    "step", "steps", "option", "paper", "unit", "level", "grade", "mark", "marks", "point", "points", "sentence",
    "note", "notes", "appendix", "group", "item", "task", "year", "week", "day", "number", "no",
})
_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # a locator token anywhere inside parentheses: (p. 48) (García Márquez, p. 48) (ch. 3, p. 49) (see pp. 12-13)
    re.compile(r"\(\s*(?:[^()]{0,80}?[\s,;:]\s*)?" + _LOCATOR_TOKEN + r"\.?\s*" + _RANGE + r"[^()]*\)", re.IGNORECASE),
    # Act 1, Scene 2 / Act 1 Scene 2 / Act 1.2.3 / Act I, scene ii, 45
    re.compile(r"\bAct\s+(?:[IVXL]+|\d+)\s*[.,]?\s*(?:[Ss]cene\s+)?(?:[IVXLivxl]+|\d+)(?:\s*[.,]\s*" + _RANGE + r")?"),
    # act.scene.line inside parentheses, optionally after an author: (1.2.34) (Shakespeare, 3.3.165)
    re.compile(r"\((?:[^()]*?[\s,;:])?(?:\d+|[IVXivx]+)\.(?:\d+|[IVXivx]+)\.\d+(?:\s*[-–—]\s*\d+)?[^()]*\)"),
    # author-page: (García Márquez 48) (Shelley, 102-3); every word capitalised, first word not a generic label
    re.compile(r"\((?P<author>[A-ZÀ-Þ][\w'’.-]*(?:\s+[A-ZÀ-Þ][\w'’.-]*)*),?\s+\d{1,4}(?:\s*[-–—]\s*\d{1,4})?\)"),
    # prose forms
    re.compile(r"\b(?:lines?|ll?\.)\s*" + _RANGE + r"\b", re.IGNORECASE),
    re.compile(r"\bpages?\s+" + _RANGE + r"\b", re.IGNORECASE),
    re.compile(r"\b(?:chapters?|ch\.)\s*\d+\b", re.IGNORECASE),
)
_FROM_MEMORY_RE = re.compile(
    r"\b(?:from (?:memory|recollection)|as I (?:recall|remember)|I recall|if memory serves|quoting from memory|recalled from memory)\b",
    re.IGNORECASE,
)
_QUOTE_WORD_RE = re.compile(r"\bquot(?:e|es|ed|ing|ation|ations)\b", re.IGNORECASE)
#: A from-memory label that concerns dates or figures (the History register) and names no quotation.
_DATES_FIGURES_RE = re.compile(r"\b(?:dates?|figures?|statistics|numbers|years?|percentages?)\b", re.IGNORECASE)
_FIRST_PERSON_RE = re.compile(r"\b(?:I|[Ww]e|[Mm]y|[Oo]ur|[Mm]e|[Uu]s)\b")
_ROMAN_NUMERAL_RE = re.compile(r"\b(?:Act|Part|Book|Scene|Chapter|Vol\.?|Volume|Section|Canto|Stanza)\s+[IVXL]+\b")
# -ise/-ize and -yse/-yze (analyse/analyze) families; inflections included.
_ISE_RE = re.compile(r"\b([A-Za-z]{3,}[iy]s(?:e|es|ed|ing|ation|ations))\b")
_IZE_RE = re.compile(r"\b([A-Za-z]{3,}[iy]z(?:e|es|ed|ing|ation|ations))\b")
_ISE_FALSE_FRIENDS = frozenset({
    "rise", "arise", "wise", "otherwise", "likewise", "clockwise", "advise", "surprise", "promise", "compromise",
    "comprise", "exercise", "precise", "concise", "noise", "praise", "raise", "disguise", "franchise", "supervise",
    "revise", "devise", "advertise", "despise", "enterprise", "expertise", "improvise", "merchandise", "televise",
    "chastise", "excise", "incise", "demise", "paradise", "premise", "reprise", "treatise", "poise", "appraise",
    "cruise", "bruise", "guise", "anise", "valise", "mortise", "chemise", "surmise", "apprise", "circumcise",
})
_IZE_FALSE_FRIENDS = frozenset({"size", "prize", "seize", "capsize", "resize", "downsize", "outsize", "maize", "baize"})
_BARE_QUOTATION_RE = re.compile(r'^[\"“][^\"”]+[\"”][.!?,;:]?$')


def _spelling_lexicon() -> tuple[frozenset[str], frozenset[str]]:
    """Paired British / American word forms (with inflections) beyond the -ise/-ize families."""
    british: set[str] = set()
    american: set[str] = set()
    our_words = ("honour", "colour", "behaviour", "labour", "favour", "neighbour", "humour", "flavour", "rumour", "odour",
                 "vigour", "harbour", "armour", "savour", "valour", "endeavour", "splendour", "fervour", "candour", "clamour")
    suffixes = ("", "s", "ed", "ing", "able", "ably", "ful", "fully", "less", "al", "ally", "ite", "ites", "ism", "ist", "ists")
    for w in our_words:
        am = w[:-3] + "or"
        for suf in suffixes:
            british.add(w + suf)
            american.add(am + suf)
    for w in ("centre", "theatre", "metre", "sombre", "spectre", "fibre", "calibre", "lustre", "meagre"):
        am = w[:-2] + "er"
        british.update({w, w + "s", w[:-1] + "ed", w[:-2] + "ring", w + "ly"})
        american.update({am, am + "s", am + "ed", am + "ing", am + "ly"})
    for w in ("defence", "offence", "pretence"):
        am = w[:-2] + "se"
        british.update({w, w + "s", w + "less"})
        american.update({am, am + "s", am + "less"})
    for w in ("analogue", "catalogue"):
        british.update({w, w + "s"})
        american.update({w[:-2], w[:-2] + "s"})
    pairs = (
        (("grey", "greys", "greyed", "greyer", "greyest", "greyness"), ("gray", "grays", "grayed", "grayer", "grayest", "grayness")),
        (("judgement", "judgements"), ("judgment", "judgments")),
        (("acknowledgement", "acknowledgements"), ("acknowledgment", "acknowledgments")),
        (("travelling", "travelled", "traveller", "travellers"), ("traveling", "traveled", "traveler", "travelers")),
        (("modelling", "modelled"), ("modeling", "modeled")),
        (("labelling", "labelled"), ("labeling", "labeled")),
        (("cancelled", "cancelling"), ("canceled", "canceling")),
        (("jewellery",), ("jewelry",)),
        (("mould", "moulds", "moulded", "mouldy"), ("mold", "molds", "molded", "moldy")),
        (("plough", "ploughs", "ploughed", "ploughing"), ("plow", "plows", "plowed", "plowing")),
        (("sceptical", "sceptic", "sceptics", "scepticism"), ("skeptical", "skeptic", "skeptics", "skepticism")),
        (("fulfil", "fulfils", "fulfilment"), ("fulfill", "fulfills", "fulfillment")),
        (("instalment", "instalments"), ("installment", "installments")),
        (("skilful", "skilfully", "wilful", "wilfully"), ("skillful", "skillfully", "willful", "willfully")),
        (("ageing",), ("aging",)),
        (("manoeuvre", "manoeuvres", "manoeuvred", "manoeuvring"), ("maneuver", "maneuvers", "maneuvered", "maneuvering")),
        (("cosy", "cosier", "cosiest"), ("cozy", "cozier", "coziest")),
        (("pyjamas",), ("pajamas",)),
    )
    for brit, amer in pairs:
        british.update(brit)
        american.update(amer)
    return frozenset(british), frozenset(american)


BRITISH_FORMS, AMERICAN_FORMS = _spelling_lexicon()
_WORD_RE = re.compile(r"[A-Za-z]+")


def _finding(code: str, severity: str, message: str, claim_ids: Iterable[str] = ()) -> StructuralFinding:
    return StructuralFinding(
        code=code, severity=severity, message=truncate(message, 2000),  # type: ignore[arg-type]
        claim_ids=sorted(set(claim_ids)), rule_source=RULE_SOURCES[code],
    )


def _claims_for_sentence(report: SpecialistReport, sentence: Sentence) -> list[str]:
    """Claims whose text is this sentence, contain it, or are its truncated form."""
    text = sentence.text.strip()
    out: list[str] = []
    for c in report.claims:
        body = c.claim_text.strip()
        if body == text or (len(text) > 20 and text in body):
            out.append(c.claim_id)
        elif body.endswith("...") and len(body) > 3 and text.startswith(body[:-3]):
            out.append(c.claim_id)
    return out


def _claims_for_paragraph(report: SpecialistReport, para: Paragraph) -> list[str]:
    """The paragraph's point claim (the point whose text is one of its sentences), when any."""
    texts = {s.text.strip() for s in para.sentences}
    return [c.claim_id for c in report.claims if c.claim_role == "point" and c.claim_text.strip() in texts][:1]


def _located_in(excerpt: str, report: SpecialistReport) -> list[str]:
    docs = {t.document_id: t for t in report.supplied_texts}
    return [doc_id for doc_id in docs if excerpt_located(excerpt, doc_id, docs)]


# ------------------------------------------------------------------ citations


def find_citations(text: str) -> list[str]:
    """Location citations in ``text`` (quotations already masked), longest match first,
    with matches contained in another match dropped."""
    spans: list[tuple[int, int]] = []
    for pattern in _CITATION_PATTERNS:
        for m in pattern.finditer(text):
            author = m.groupdict().get("author") if m.groupdict() else None
            if author is not None and author.split()[0].lower().rstrip(".") in _NOT_AUTHORS:
                continue
            spans.append((m.start(), m.end()))
    kept: list[tuple[int, int]] = []
    for s, e in sorted(spans, key=lambda x: (x[0], -(x[1] - x[0]))):
        if any(ks <= s and e <= ke for ks, ke in kept):
            continue
        kept.append((s, e))
    return [text[s:e] for s, e in kept]


def citation_schemes(citation: str) -> set[str]:
    """The ``locator_scheme`` values a citation would need in order to be checkable."""
    schemes: set[str] = set()
    for m in _TOKEN_IN_TEXT_RE.finditer(citation):
        schemes.add(_TOKEN_SCHEME[m.group(1).lower()])
    if _ACT_SCENE_RE.search(citation):
        schemes.add("act_scene_line")
    if not schemes:
        schemes.add("page")  # author-page form: a bare number after a name is a page
    return schemes


# ------------------------------------------------------------------ checks


def source_findings(report: SpecialistReport, paragraphs: Optional[tuple[Paragraph, ...]] = None) -> list[StructuralFinding]:
    """ES-SRC-001 / 005 / 006 / 007 from the shared excerpt check; ES-SRC-004 when nothing was supplied.

    With no supplied text, quotations cannot be attributed to a document, so the
    parser records none; evidence claims and the quotations found in the prose are
    counted instead.
    """
    if not report.supplied_texts:
        cited = [c for c in report.claims if c.claim_role == "evidence" or any(r.excerpt and r.excerpt.strip() for r in c.source_refs)]
        quoted = sum(len(p.quotations) for p in paragraphs) if paragraphs else 0
        if not cited and not quoted:
            return []
        count = len(cited) or quoted
        return [_finding(
            "ES-SRC-004", "warning",
            f"{count} quotation(s) appear in the answer but no supplied text was given to check them against",
            [c.claim_id for c in cited],
        )]
    out: list[StructuralFinding] = []
    claims = {c.claim_id: c for c in report.claims}
    docs = {t.document_id: t for t in report.supplied_texts}
    for f in generic_source_findings(
        report, code="ES-SRC-001", joined_code="ES-SRC-005", inexact_code="ES-SRC-006", elided_code="ES-SRC-007", locator_code="ES-SRC-002",
    ):
        message = f.message
        if f.code == "ES-SRC-001":
            # an elided quotation whose fragments all occur in order but span more than the elision window: the
            # words occur, so this is a form difference (a warning, as the channel's INT-REQ-010), never 'invented'
            claim = claims.get(f.claim_ids[0]) if f.claim_ids else None
            long = next((
                (r, long_elision_of(r.excerpt, r.document_id, docs)) for r in (claim.source_refs if claim else [])
                if r.excerpt and r.document_id in docs and truncate(strip_trailing_punctuation(r.excerpt), _EXCERPT_CHARS) in message
            ), None)
            if long is not None and long[1]:
                ref, difference = long
                out.append(_finding(
                    "ES-SRC-006", "warning",
                    f"quotation '{truncate(ref.excerpt or '', _EXCERPT_CHARS)}' cited by claim {claim.claim_id if claim else '?'} in {ref.document_id}: {difference}; "
                    "the words occur in the text, so this is a long elision to be marked, not an invented quotation",
                    f.claim_ids,
                ))
                continue
        if f.code == "ES-SRC-001" and "not found in the document" in message:
            searched = [t.document_id for t in report.supplied_texts]
            claim = claims.get(f.claim_ids[0]) if f.claim_ids else None
            excerpts = [r.excerpt for r in claim.source_refs if r.excerpt] if claim else []
            elsewhere = sorted({d for ex in excerpts for d in _located_in(ex, report)})
            if elsewhere:
                message += f"; the words occur in {', '.join(elsewhere)}, not in the text cited"
            else:
                message += f"; searched every supplied text ({', '.join(searched)}): found in none"
            message += " (not in the supplied text: invented, altered, or quoted from memory without the required one-line disclosure)"
        out.append(f.model_copy(update={"rule_source": RULE_SOURCES[f.code], "message": truncate(message, 2000)}))
    return out


def attribution_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-SRC-008: a sentence names exactly one supplied text (author, surname, title, the peer
    specialist, or "the poem" when one literary text was supplied) but its quotation is located
    only in another supplied text. An error when a relayed colleague's report is on either side."""
    docs = {t.document_id: t for t in report.supplied_texts}
    if len(docs) < 2:
        return []
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if para.kind == "meta":
            continue
        for sentence in para.sentences:
            if not sentence.quotations or sentence.role == "other":
                continue
            named = documents_named(strip_quotations(sentence.text), docs)
            if len(named) != 1:
                continue
            for q in sentence.quotations:
                if not q.delimited:
                    continue
                located = [d for d in docs if excerpt_located(q.excerpt, d, docs)]
                if not located or named[0] in located:
                    continue
                peer = is_peer_document(docs[named[0]]) or any(is_peer_document(docs[d]) for d in located)
                claim_ids = [c.claim_id for c in report.claims if any(r.excerpt == q.excerpt for r in c.source_refs)] or _claims_for_sentence(report, sentence)
                out.append(_finding(
                    "ES-SRC-008", "error" if peer else "warning",
                    f"paragraph {para.index}, sentence {sentence.index} attributes the quotation '{truncate(q.excerpt, _EXCERPT_CHARS)}' to "
                    f"{named[0]} but the words occur only in {', '.join(located)}; the quotation is real but credited to the wrong text",
                    claim_ids,
                ))
    return out


def citation_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-SRC-002: a location citation whose scheme no supplied text declares."""
    declared = {t.locator_scheme for t in report.supplied_texts} - {"none"}
    out: list[StructuralFinding] = []
    for para in paragraphs:
        for sentence in para.sentences:
            unverifiable: dict[str, set[str]] = {}
            for cite in find_citations(strip_quotations(sentence.text)):
                missing = citation_schemes(cite) - declared
                if missing:
                    unverifiable[cite] = missing
            if not unverifiable:
                continue
            cites = sorted(unverifiable)
            shown = "; ".join(truncate(c, 40) for c in cites[:4])
            needed = ", ".join(sorted(set().union(*unverifiable.values())))
            reason = (
                f"no supplied text declares a matching locator scheme ({needed})" if report.supplied_texts
                else "no text was supplied"
            )
            out.append(_finding(
                "ES-SRC-002", "error",
                f"paragraph {para.index}, sentence {sentence.index} gives a location citation ({shown}) but {reason}; "
                "line, act, page and chapter numbers cannot be verified and must not be invented",
                _claims_for_sentence(report, sentence),
            ))
    return out


def memory_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-SRC-003: the answer says a quotation is from memory. The phrase is searched with the
    sentence's quotations masked (a quoted colleague's disclosure is the colleague's), and it
    counts only when it is the writer's own disclosure about quoting: the sentence has a
    quotation NOT located in a supplied text, or names quoting ("quoting from memory", "the
    quotation above is from memory"), or the phrase is the method's own label
    (``markdown.split_note_clauses`` sets it aside: "As I recall, ...", "..., if memory serves,
    ...", a note sentence) and that label does not concern dates or figures only. "From memory"
    as part of the argument ("The speaker recalls the scene from memory, which explains ...",
    "Wordsworth wrote the sonnet from memory of a single morning, so ...") is analysis, not a
    disclosure, and a sentence whose only quotation is located in a supplied text is no finding."""
    out: list[StructuralFinding] = []
    docs = {t.document_id: t for t in report.supplied_texts}
    for para in paragraphs:
        for sentence in para.sentences:
            plain = strip_quotations(sentence.text)
            if not _FROM_MEMORY_RE.search(plain):
                continue
            unlocated = [q for q in sentence.quotations if not q.delimited or not docs or not any(excerpt_located(q.excerpt, d, docs) for d in docs)]
            core, notes = split_note_clauses(sentence.text)
            labelled = not core or any(_FROM_MEMORY_RE.search(n) for n in notes)
            own = plain.replace("[quotation]", " ")  # the writer's own words: the placeholder is not a quotation word
            if unlocated or _QUOTE_WORD_RE.search(own) or (labelled and not _DATES_FIGURES_RE.search(own)):
                out.append(_finding(
                    "ES-SRC-003", "warning",
                    f"paragraph {para.index}, sentence {sentence.index} quotes from memory; such quotations are "
                    "unverified against any supplied text",
                    _claims_for_sentence(report, sentence),
                ))
    return out


def strand_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STR-001: body paragraph with fewer than two quotations of at least two words (P7 proxy)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if para.kind != "body":
            continue
        substantive = {q.excerpt for q in para.quotations if q.words >= MIN_QUOTATION_WORDS}
        if len(substantive) < MIN_STRAND_QUOTATIONS:
            out.append(_finding(
                "ES-STR-001", "warning",
                f"body paragraph {para.index} carries {len(substantive)} quotation(s) of at least {MIN_QUOTATION_WORDS} words; "
                f"the working rule expects one idea carried by two strands, each with its own evidence",
                _claims_for_paragraph(report, para),
            ))
    return out


def length_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STR-002: body paragraph outside the accepted 230-390 word range (P13 proxy)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if para.kind != "body":
            continue
        n = para.word_count
        if n < BODY_WORDS_MIN or n > BODY_WORDS_MAX:
            out.append(_finding(
                "ES-STR-002", "info",
                f"body paragraph {para.index} has {n} words; the working target is about 350 (accepted range about "
                f"{BODY_WORDS_MIN}-{BODY_WORDS_MAX}) unless the task sets a count",
                _claims_for_paragraph(report, para),
            ))
    return out


def meta_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-META-001: meta-text blocks, and prose sentences that narrate checks or steps, certify
    the answer's own accuracy or have the shape of a pasted receipt (quotation marks or not)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if para.kind == "meta":
            out.append(_finding(
                "ES-META-001", "warning",
                f"paragraph {para.index} is meta-text ('{truncate(para.text, _EXCERPT_CHARS)}'): a note about the text, a self-certification, a pasted receipt or a "
                "narrated check is not analysis, provides no evidence and plays no part in verification",
            ))
            continue
        if not para.is_prose:
            continue
        for sentence in para.sentences:
            if is_meta_sentence(sentence.text):
                out.append(_finding(
                    "ES-META-001", "warning",
                    f"paragraph {para.index}, sentence {sentence.index} narrates a check, certifies the answer or imitates a receipt "
                    f"('{truncate(sentence.text, _EXCERPT_CHARS)}'); such assurance is not analysis, counts as no material claim and plays no part in verification",
                    _claims_for_sentence(report, sentence),
                ))
    return out


def first_person_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STY-001: first person outside quotations (S2, formal third person)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if para.kind == "meta":
            continue  # meta-text is reported once, by ES-META-001
        for sentence in para.sentences:
            plain = _ROMAN_NUMERAL_RE.sub(" ", strip_quotations(sentence.text))
            hits = sorted({m.group(0) for m in _FIRST_PERSON_RE.finditer(plain)})
            if hits:
                out.append(_finding(
                    "ES-STY-001", "info",
                    f"paragraph {para.index}, sentence {sentence.index} uses the first person ({', '.join(hits)}) outside a quotation",
                    _claims_for_sentence(report, sentence),
                ))
    return out


def _spelling_families(text: str) -> tuple[list[str], list[str]]:
    """British and American forms found outside quotations: -ise/-ize families plus the paired lexicon."""
    plain = strip_quotations(text)
    british = {m.group(1) for m in _ISE_RE.finditer(plain) if m.group(1).lower() not in _ISE_FALSE_FRIENDS and not _stem_false_friend(m.group(1), _ISE_FALSE_FRIENDS)}
    american = {m.group(1) for m in _IZE_RE.finditer(plain) if m.group(1).lower() not in _IZE_FALSE_FRIENDS and not _stem_false_friend(m.group(1), _IZE_FALSE_FRIENDS)}
    for m in _WORD_RE.finditer(plain):
        word = m.group(0)
        low = word.lower()
        if low in BRITISH_FORMS:
            british.add(word)
        elif low in AMERICAN_FORMS:
            american.add(word)
    return sorted(british), sorted(american)


def _stem_false_friend(word: str, friends: frozenset[str]) -> bool:
    """True when ``word`` is an inflection of a false friend (``surprised`` -> ``surprise``)."""
    w = word.lower()
    for suffix in ("ations", "ation", "ing", "es", "ed", "s"):
        if w.endswith(suffix):
            stem = w[: -len(suffix)]
            if stem in friends or stem + "e" in friends:
                return True
    return False


def spelling_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STY-002: British and American spellings mixed outside quotations (S18, one variety)."""
    british, american = _spelling_families(report.original_response)
    if not british or not american:
        return []
    return [_finding(
        "ES-STY-002", "info",
        "the answer mixes spelling varieties: British forms (" + ", ".join(british[:6]) + ") and American forms (" + ", ".join(american[:6]) + ")",
        [c.claim_id for c in report.claims if c.claim_role in ("point", "thesis")][:8],
    )]


def bare_quotation_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STY-003: a sentence that is nothing but a quotation (S11, embed every quotation)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if not para.is_prose:
            continue
        for sentence in para.sentences:
            if _BARE_QUOTATION_RE.match(sentence.text.strip()):
                excerpts = {q.excerpt for q in sentence.quotations}
                claim_ids = [c.claim_id for c in report.claims if any(r.excerpt in excerpts for r in c.source_refs if r.excerpt)]
                out.append(_finding(
                    "ES-STY-003", "warning",
                    f"paragraph {para.index}, sentence {sentence.index} is only a quotation ('{truncate(sentence.text, _EXCERPT_CHARS)}'); "
                    "every quotation should be embedded in a sentence of the writer's own",
                    claim_ids or _claims_for_sentence(report, sentence),
                ))
    return out


def structural_checks(report: SpecialistReport, paragraphs: Optional[tuple[Paragraph, ...]] = None, request_text: Optional[str] = None) -> list[StructuralFinding]:
    """All English specialist structural findings for ``report`` (see module docstring).

    ``paragraphs`` may be passed when the caller already segmented the answer;
    otherwise ``report.original_response`` is segmented here. The paragraph working
    rules (P7, P13) are skipped for outline, plan and bullet deliverables, and the
    length rule (P13) yields to a word count set in ``request_text`` when given.
    """
    if paragraphs is None:
        paragraphs = segment(report.original_response)
    findings: list[StructuralFinding] = []
    findings += source_findings(report, paragraphs)
    findings += attribution_findings(report, paragraphs)
    findings += citation_findings(report, paragraphs)
    findings += memory_findings(report, paragraphs)
    if not OUTLINE_TASK_RE.search(report.task_type or ""):
        findings += strand_findings(report, paragraphs)
        if not (request_text and WORD_BOUND_RE.search(request_text)):
            findings += length_findings(report, paragraphs)
    findings += meta_findings(report, paragraphs)
    findings += first_person_findings(report, paragraphs)
    findings += spelling_findings(report, paragraphs)
    findings += bare_quotation_findings(report, paragraphs)
    return findings
