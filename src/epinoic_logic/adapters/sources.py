"""Shared source-integrity helpers for adapters.

Both the generic adapter and the English specialist adapter must answer the same
question deterministically: *does this quoted excerpt occur in the supplied text it
cites?* The authoritative matcher is
:func:`epinoic_logic.translate.grounding.locate_quotation` (verbatim, then
typographic normalization, then explicit ellipsis within a bounded window). This
module reports every way an excerpt can relate to the text as a distinct status so
that nothing is silently accepted and nothing legitimate is called invented:

* ``found``         exact or typographically normalized match.
* ``found_elided``  an excerpt with an ellipsis whose fragments occur in order within
                    the elision window; reported apart so a stitched quotation is
                    visible (the detail gives the span covered).
* ``found_inexact`` the words occur but the quotation's form differs by a conventional
                    adjustment: the initial capital (a sentence opening quoted
                    mid-sentence) or an omitted verse line-break mark. Reported with
                    the difference named, never as an invented quotation.
* ``found_long_elision`` an excerpt with an ellipsis whose fragments all occur in order
                    but span more than the elision window (``ELISION_WINDOW_CHARS``)
                    beyond the quoted words: the words occur, so this is a long
                    elision, a form difference to report as a warning (the detail names
                    the omitted span), never an invented quotation. The channel reports
                    the same excerpt as INT-REQ-010.
* ``found_joined``  every multi-word fragment occurs, in order, each within a short
                    gap of the next, but the text as quoted does not: the quotation
                    joins spans without marking the omission (``"We killed him
                    openly, but we're innocent."`` for a line whose speech tag was
                    dropped).
* ``not_found``     the words are not in the document in any of these forms.
* ``no_document`` / ``no_texts`` / ``empty``: nothing to check against.

Trailing sentence punctuation written inside the closing quotation mark
(``"legitimate defense,"``) belongs to the sentence, not the quoted words, so every
match is retried without it.

Nothing here sets ``Grounding.verified``; that remains the grounding module's job.

Cost: :func:`check_excerpt` answers each ``(excerpt, document_id, sha256 of the text)`` once
and keeps the answer in a bounded least-recently-used cache, and the text's normalised forms
come from the grounding module's cache (:func:`~epinoic_logic.translate.grounding.text_forms`),
so a parser, the packs and the channel asking about the same excerpt in the same document
within one parse or check share one answer. The answer is a pure function of the excerpt and
the text, so caching never changes it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping, Optional, Sequence

from ..translate.contracts import SuppliedText
from ..translate.grounding import (
    BoundedLRU, locate_long_elision, locate_quotation, locate_quotation_inexact, normalize_quote, normalized_text, text_sha256,
)

__all__ = [
    "ExcerptCheck", "ExcerptStatus", "FOUND_STATUSES", "check_excerpt", "strip_trailing_punctuation", "word_count",
    "JOIN_GAP_CHARS", "EXCERPT_CHECK_MAX_ENTRIES", "clear_excerpt_cache",
    "UNCREDITED_QUOTATION", "attribute_excerpt", "uncredited_assumption", "uncredited_excerpt",
]

ExcerptStatus = Literal["found", "found_elided", "found_inexact", "found_long_elision", "found_joined", "not_found", "no_document", "no_texts", "empty"]

#: Statuses under which the quoted words were located in the document (in some form).
FOUND_STATUSES: frozenset[str] = frozenset({"found", "found_elided", "found_inexact", "found_long_elision", "found_joined"})

_TRAILING_PUNCT = ".,;:!?"
_FRAGMENT_SPLIT_RE = re.compile(r"[,;:.!?]+")
#: Largest gap (characters of normalized text) allowed between consecutive fragments of
#: a joined quotation. A dropped speech tag is about twenty characters; anything much
#: longer stitches distinct sentences together and is reported as not found.
JOIN_GAP_CHARS = 80
_MIN_FRAGMENT_WORDS = 2
#: Excerpt checks kept: one per (excerpt, document_id, sha256 of the text), bounded by count and by the characters held.
EXCERPT_CHECK_MAX_ENTRIES = 16_384
EXCERPT_CHECK_MAX_CHARS = 8_000_000
_CHECKS = BoundedLRU(EXCERPT_CHECK_MAX_ENTRIES, EXCERPT_CHECK_MAX_CHARS)


@dataclass(frozen=True)
class ExcerptCheck:
    """Outcome of checking one excerpt against one supplied text."""

    status: ExcerptStatus
    document_id: Optional[str]
    detail: str
    excerpt_checked: str

    @property
    def ok(self) -> bool:
        """True only for an exact (or typographically normalized) match."""
        return self.status == "found"

    @property
    def located(self) -> bool:
        """True when the quoted words were found in the document in some form."""
        return self.status in FOUND_STATUSES


def strip_trailing_punctuation(excerpt: str) -> str:
    """Remove sentence punctuation that was written inside the closing quotation mark."""
    return excerpt.strip().rstrip(_TRAILING_PUNCT).strip()


def word_count(text: str) -> int:
    """Whitespace-token count (the proxy used for every length rule)."""
    return len(text.split())


def _joined_fragments(excerpt: str, text: str, document_id: Optional[str] = None) -> Optional[int]:
    """When every multi-word fragment of ``excerpt`` occurs in order in ``text`` with at
    most :data:`JOIN_GAP_CHARS` between consecutive fragments, return the largest gap;
    otherwise ``None``."""
    fragments = [f.strip() for f in _FRAGMENT_SPLIT_RE.split(normalize_quote(excerpt)) if f.strip()]
    fragments = [f for f in fragments if len(f.split()) >= _MIN_FRAGMENT_WORDS]
    if len(fragments) < 2:
        return None
    norm_text = normalized_text(text, document_id)
    cursor = 0
    largest_gap = 0
    previous_end: Optional[int] = None
    for frag in fragments:
        pos = norm_text.find(frag, cursor)
        if pos < 0:
            return None
        if previous_end is not None:
            gap = pos - previous_end
            if gap > JOIN_GAP_CHARS:
                return None
            largest_gap = max(largest_gap, gap)
        previous_end = pos + len(frag)
        cursor = previous_end
    return largest_gap


def check_excerpt(excerpt: Optional[str], document_id: Optional[str], docs: Mapping[str, SuppliedText]) -> ExcerptCheck:
    """Check ``excerpt`` against the supplied text ``document_id`` names.

    ``docs`` maps document ids to supplied texts. An excerpt with no usable words is
    ``empty``; a missing document is ``no_document`` (or ``no_texts`` when nothing
    was supplied at all); otherwise one of the statuses in the module docstring.
    """
    cleaned = strip_trailing_punctuation(excerpt or "")
    if not cleaned:
        return ExcerptCheck("empty", document_id, "excerpt carries no words", cleaned)
    if not docs:
        return ExcerptCheck("no_texts", document_id, "no supplied text to check the quotation against", cleaned)
    doc = docs.get(document_id or "")
    if doc is None:
        return ExcerptCheck("no_document", document_id, "document_id is not among the supplied texts", cleaned)
    key = (excerpt or "", document_id, text_sha256(doc.text))
    cached = _CHECKS.get(key)
    if cached is None:
        cached = _check_in_document(excerpt or "", cleaned, document_id, doc.text)
        _CHECKS.put(key, cached, weight=len(key[0]) + len(cached.detail) + len(cached.excerpt_checked) + 1)
    return cached


def clear_excerpt_cache() -> None:
    """Empty the excerpt-check cache (tests; a process that wants its memory back)."""
    _CHECKS.clear()


def _check_in_document(excerpt: str, cleaned: str, document_id: Optional[str], doc_text: str) -> ExcerptCheck:
    """The status of ``excerpt`` (``cleaned``: without trailing sentence punctuation) in the
    supplied text ``document_id`` whose words are ``doc_text``."""
    match = locate_quotation(excerpt, doc_text, document_id=document_id) or locate_quotation(cleaned, doc_text, document_id=document_id)
    if match is not None:
        how = "verbatim" if match.method == "verbatim_match" else "after typographic normalization"
        if match.elided:
            return ExcerptCheck(
                "found_elided", document_id,
                f"found as an elided quotation: the fragments occur in order and span {match.end - match.start} characters "
                f"(characters {match.start}-{match.end}); the omitted words are not quoted",
                cleaned,
            )
        return ExcerptCheck("found", document_id, f"found {how} at characters {match.start}-{match.end}", cleaned)
    inexact = locate_quotation_inexact(cleaned, doc_text, document_id=document_id)
    if inexact is not None:
        near, difference = inexact
        return ExcerptCheck(
            "found_inexact", document_id,
            f"the words occur in the document (characters {near.start}-{near.end}) but the quotation {difference}",
            cleaned,
        )
    far = locate_long_elision(cleaned, doc_text, document_id=document_id)
    if far is not None:
        near, difference = far
        return ExcerptCheck(
            "found_long_elision", document_id,
            f"the words occur in the document (characters {near.start}-{near.end}) but the quotation {difference}",
            cleaned,
        )
    gap = _joined_fragments(cleaned, doc_text, document_id)
    if gap is not None:
        return ExcerptCheck(
            "found_joined", document_id,
            "every fragment occurs in order, but the quotation joins separate spans of the text without marking the "
            f"omission (largest omitted span {gap} characters)",
            cleaned,
        )
    return ExcerptCheck("not_found", document_id, "excerpt not found in the document (verbatim or normalized)", cleaned)


# ------------------------------------------------------------------ attribution (one rule for every parser)

#: The assumption a parser records for a quotation it credits to no supplied text. The core
#: pack reads it back (:func:`uncredited_excerpt`) and reports the quotation as unverifiable
#: (``CORE-SRC-003``), so a quotation left without a source reference never goes silent.
UNCREDITED_QUOTATION = "quotation with no supplied text to check it against"


def uncredited_assumption(excerpt: str, why: Optional[str] = None) -> str:
    """The assumption recording a quotation credited to no supplied text (``why`` says why)."""
    out = f'{UNCREDITED_QUOTATION}: "{excerpt[:200]}"'
    return out + (f" ({why})" if why else "")


def uncredited_excerpt(assumption: str) -> Optional[str]:
    """The excerpt an :func:`uncredited_assumption` names (cut to 200 characters), or None
    when ``assumption`` is not one."""
    head = f'{UNCREDITED_QUOTATION}: "'
    if not assumption.startswith(head):
        return None
    body = assumption[len(head):]
    if body.endswith('"'):
        return body[:-1] or None
    cut = body.rfind('" (')
    return (body[:cut] or None) if cut >= 0 else None


def attribute_excerpt(excerpt: str, named: Sequence[str], docs: Mapping[str, SuppliedText], *,
                      text_under_analysis: Optional[str] = None) -> tuple[Optional[str], list[str]]:
    """``(document_id, assumptions)`` for one quotation of a sentence that names the supplied
    texts ``named``. One rule for every parser:

    * the text that holds the words wins (located in any recognised form, :func:`check_excerpt`);
      when several hold them, the one the sentence names; a located text other than the one
      named is credited and the discrepancy recorded (the packs report it as a wrong credit,
      ``ES-SRC-008`` / ``CORE-SRC-005``);
    * a quotation located in no text is credited to the one text the sentence names, whether
      or not that text holds the words, with the assumption that it was found in none (the hub
      then reports it as not found, ``INT-REQ-003``);
    * otherwise it is credited to NO text and the :func:`uncredited_assumption` is recorded, so
      the core pack reports it as unverifiable (``CORE-SRC-003``). A text is never credited
      merely for being supplied first.

    ``text_under_analysis`` is a branch's own notion of what an unnamed quotation quotes: the
    English branch passes its one literary (non-peer) text, the text the analytical answer is
    about, so an altered quotation of the poem stays refutable (``INT-REQ-003``) when the
    sentence names nothing; it is credited only when the sentence names no text at all."""
    if not docs:
        return None, [uncredited_assumption(excerpt)]
    located = [doc_id for doc_id in docs if check_excerpt(excerpt, doc_id, docs).located]
    searched = ", ".join(docs)
    if located:
        if len(named) == 1 and named[0] in located:
            return named[0], []
        if len(named) == 1:
            return located[0], [f"the sentence attributes this quotation to {named[0]} but the words were located only in {', '.join(located)}"]
        return located[0], []
    if len(named) == 1:
        return named[0], [f"excerpt found in none of the supplied texts [{searched}]; attributed to {named[0]} because the sentence names it"]
    if not named and text_under_analysis is not None and text_under_analysis in docs:
        return text_under_analysis, [f"excerpt found in none of the supplied texts [{searched}]; attributed to {text_under_analysis}, "
                                     "the one literary text under analysis, because the sentence names no supplied text"]
    why = "the sentence names no supplied text" if not named else f"the sentence names several supplied texts ({', '.join(named)})"
    return None, [uncredited_assumption(excerpt, f"{why} and the words occur in none of [{searched}]")]
