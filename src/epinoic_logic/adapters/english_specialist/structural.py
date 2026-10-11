"""Deterministic structural checks for English specialist answers.

Every check here is code over text. None is a solver result and none judges the
quality of a reading. The rules are *working rules* taken from the English
specialist's own knowledge documents (master prompt non-negotiables, paragraphs.md,
formatting.md, application.md); they are not official IB rules, and every finding
says so in ``rule_source``.

Codes (stable; add, never rename)
---------------------------------
Source integrity
* ``ES-SRC-001`` error   quotation not found in the supplied text it cites (verbatim or
                          after typographic normalization), or cites an unknown document.
* ``ES-SRC-002`` error   a line/act/page citation such as ``(l. 12)`` or ``Act 1.2.3``
                          while no supplied text has a locator scheme: locations cannot be
                          verified and must never be invented.
* ``ES-SRC-003`` warning the phrase "from memory": the answer quotes without the text.
* ``ES-SRC-004`` warning a quotation with no supplied text to check it against.
* ``ES-SRC-005`` warning a quotation found only by joining separate spans of the text
                          without marking the omission (formatting.md S12: quote exactly).

Structure (paragraphs.md)
* ``ES-STR-001`` warning a body paragraph with fewer than two quotations of at least two
                          words: proxy for P7, one idea carried by two strands.
* ``ES-STR-002`` info    a body paragraph outside 250-450 words: proxy for P13 (~350 words).

Style (formatting.md)
* ``ES-STY-001`` info    first person (I, we, my, our, me, us) outside quotations: S2.
* ``ES-STY-002`` info    both -ise/-yse and -ize/-yze spellings in one answer: S18.
* ``ES-STY-003`` warning a sentence that is only a quotation: S11, embed every quotation.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from ...translate.common import truncate
from ...translate.contracts import SpecialistReport, StructuralFinding
from ..generic_structured import generic_source_findings
from .parser import Paragraph, Sentence, segment, strip_quotations

__all__ = [
    "structural_checks", "RULE_SOURCES", "MIN_STRAND_QUOTATIONS", "MIN_QUOTATION_WORDS",
    "BODY_WORDS_MIN", "BODY_WORDS_MAX",
]

_WORKING = " (working rule, not an official IB rule)"
RULE_SOURCES: dict[str, str] = {
    "ES-SRC-001": "english_specialist/master_prompt.txt non-negotiable 1, source integrity" + _WORKING,
    "ES-SRC-002": "english_specialist/master_prompt.txt non-negotiable 1 and resolved conflict 12, citations" + _WORKING,
    "ES-SRC-003": "english_specialist/application.md section 8, source integrity" + _WORKING,
    "ES-SRC-004": "english_specialist/master_prompt.txt non-negotiable 1, source integrity" + _WORKING,
    "ES-SRC-005": "english_specialist/formatting.md S12" + _WORKING,
    "ES-STR-001": "english_specialist/paragraphs.md P7" + _WORKING,
    "ES-STR-002": "english_specialist/paragraphs.md P13" + _WORKING,
    "ES-STY-001": "english_specialist/formatting.md S2" + _WORKING,
    "ES-STY-002": "english_specialist/formatting.md S18" + _WORKING,
    "ES-STY-003": "english_specialist/formatting.md S11" + _WORKING,
}

MIN_STRAND_QUOTATIONS = 2
MIN_QUOTATION_WORDS = 2
BODY_WORDS_MIN = 250
BODY_WORDS_MAX = 450
_EXCERPT_CHARS = 80

_CITATION_RE = re.compile(
    r"\(\s*(?:l{1,2}\.?|lines?|p{1,2}\.?|pages?)\s*\d+(?:\s*[-–—]\s*\d+)?\s*\)"
    r"|\bAct\s+(?:[IVXL]+|\d+)\s*[.,]\s*(?:[Ss]cene\s+)?(?:[IVXLivxl]+|\d+)(?:\s*[.,]\s*\d+(?:\s*[-–—]\s*\d+)?)?"
    r"|\((?:\d+|[IVXivx]+)\.(?:\d+|[IVXivx]+)\.\d+(?:\s*[-–—]\s*\d+)?\)"
    r"|\b(?:lines?|l{1,2}\.)\s*\d+(?:\s*[-–—]\s*\d+)?\b",
    re.IGNORECASE,
)
_FROM_MEMORY_RE = re.compile(r"\bfrom memory\b", re.IGNORECASE)
_FIRST_PERSON_RE = re.compile(r"\b(?:I|[Ww]e|[Mm]y|[Oo]ur|[Mm]e|[Uu]s)\b")
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


def _finding(code: str, severity: str, message: str, claim_ids: Iterable[str] = ()) -> StructuralFinding:
    return StructuralFinding(
        code=code, severity=severity, message=truncate(message, 2000),  # type: ignore[arg-type]
        claim_ids=sorted(set(claim_ids)), rule_source=RULE_SOURCES[code],
    )


def _claims_for_sentence(report: SpecialistReport, sentence: Sentence) -> list[str]:
    """Claims whose text is this sentence, or that contain it (sentence-level attribution)."""
    text = sentence.text.strip()
    return [c.claim_id for c in report.claims if c.claim_text.strip() == text or (len(text) > 20 and text in c.claim_text)]


def _claims_for_paragraph(report: SpecialistReport, para: Paragraph) -> list[str]:
    """The paragraph's point claim (the claim whose text is its first sentence), when any."""
    if not para.sentences:
        return []
    first = para.sentences[0].text.strip()
    return [c.claim_id for c in report.claims if c.claim_role == "point" and c.claim_text.strip() == first]


def _no_locator_scheme(report: SpecialistReport) -> bool:
    return all(t.locator_scheme == "none" for t in report.supplied_texts)


# ------------------------------------------------------------------ checks


def source_findings(report: SpecialistReport, paragraphs: Optional[tuple[Paragraph, ...]] = None) -> list[StructuralFinding]:
    """ES-SRC-001 / ES-SRC-005 from the shared excerpt check; ES-SRC-004 when nothing was supplied.

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
    for f in generic_source_findings(report, code="ES-SRC-001", joined_code="ES-SRC-005"):
        out.append(f.model_copy(update={"rule_source": RULE_SOURCES[f.code]}))
    return out


def citation_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-SRC-002: line/act/page citations while no supplied text has a locator scheme."""
    if not _no_locator_scheme(report):
        return []
    out: list[StructuralFinding] = []
    for para in paragraphs:
        for sentence in para.sentences:
            cites = sorted({m.group(0) for m in _CITATION_RE.finditer(strip_quotations(sentence.text))})
            if not cites:
                continue
            shown = "; ".join(truncate(c, 40) for c in cites[:4])
            out.append(_finding(
                "ES-SRC-002", "error",
                f"paragraph {para.index}, sentence {sentence.index} gives a location citation ({shown}) but "
                + ("no supplied text has a locator scheme" if report.supplied_texts else "no text was supplied")
                + "; line, act and page numbers cannot be verified and must not be invented",
                _claims_for_sentence(report, sentence),
            ))
    return out


def memory_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-SRC-003: the answer says a quotation is from memory."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        for sentence in para.sentences:
            if _FROM_MEMORY_RE.search(sentence.text):
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
    """ES-STR-002: body paragraph outside the 250-450 word band (P13 proxy)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        if para.kind != "body":
            continue
        n = para.word_count
        if n < BODY_WORDS_MIN or n > BODY_WORDS_MAX:
            out.append(_finding(
                "ES-STR-002", "info",
                f"body paragraph {para.index} has {n} words; the working target is about 350 ({BODY_WORDS_MIN}-{BODY_WORDS_MAX}) "
                "unless the task sets a count",
                _claims_for_paragraph(report, para),
            ))
    return out


def first_person_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STY-001: first person outside quotations (S2, formal third person)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
        for sentence in para.sentences:
            hits = sorted({m.group(0) for m in _FIRST_PERSON_RE.finditer(strip_quotations(sentence.text))})
            if hits:
                out.append(_finding(
                    "ES-STY-001", "info",
                    f"paragraph {para.index}, sentence {sentence.index} uses the first person ({', '.join(hits)}) outside a quotation",
                    _claims_for_sentence(report, sentence),
                ))
    return out


def _spelling_families(text: str) -> tuple[list[str], list[str]]:
    plain = strip_quotations(text)
    ise = sorted({m.group(1) for m in _ISE_RE.finditer(plain) if m.group(1).lower() not in _ISE_FALSE_FRIENDS and not _stem_false_friend(m.group(1), _ISE_FALSE_FRIENDS)})
    ize = sorted({m.group(1) for m in _IZE_RE.finditer(plain) if m.group(1).lower() not in _IZE_FALSE_FRIENDS and not _stem_false_friend(m.group(1), _IZE_FALSE_FRIENDS)})
    return ise, ize


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
    """ES-STY-002: both -ise and -ize spellings outside quotations (S18, one variety)."""
    ise, ize = _spelling_families(report.original_response)
    if not ise or not ize:
        return []
    return [_finding(
        "ES-STY-002", "info",
        "the answer mixes spelling varieties: -ise forms (" + ", ".join(ise[:5]) + ") and -ize forms (" + ", ".join(ize[:5]) + ")",
        [c.claim_id for c in report.claims if c.claim_role in ("point", "thesis")][:8],
    )]


def bare_quotation_findings(report: SpecialistReport, paragraphs: tuple[Paragraph, ...]) -> list[StructuralFinding]:
    """ES-STY-003: a sentence that is nothing but a quotation (S11, embed every quotation)."""
    out: list[StructuralFinding] = []
    for para in paragraphs:
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


def structural_checks(report: SpecialistReport, paragraphs: Optional[tuple[Paragraph, ...]] = None) -> list[StructuralFinding]:
    """All English specialist structural findings for ``report`` (see module docstring).

    ``paragraphs`` may be passed when the caller already segmented the answer;
    otherwise ``report.original_response`` is segmented here.
    """
    if paragraphs is None:
        paragraphs = segment(report.original_response)
    findings: list[StructuralFinding] = []
    findings += source_findings(report, paragraphs)
    findings += citation_findings(report, paragraphs)
    findings += memory_findings(report, paragraphs)
    findings += strand_findings(report, paragraphs)
    findings += length_findings(report, paragraphs)
    findings += first_person_findings(report, paragraphs)
    findings += spelling_findings(report, paragraphs)
    findings += bare_quotation_findings(report, paragraphs)
    return findings
