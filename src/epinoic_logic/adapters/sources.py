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
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping, Optional

from ..translate.contracts import SuppliedText
from ..translate.grounding import locate_long_elision, locate_quotation, locate_quotation_inexact, normalize_quote

__all__ = [
    "ExcerptCheck", "ExcerptStatus", "FOUND_STATUSES", "check_excerpt", "strip_trailing_punctuation", "word_count",
    "JOIN_GAP_CHARS",
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


def _joined_fragments(excerpt: str, text: str) -> Optional[int]:
    """When every multi-word fragment of ``excerpt`` occurs in order in ``text`` with at
    most :data:`JOIN_GAP_CHARS` between consecutive fragments, return the largest gap;
    otherwise ``None``."""
    fragments = [f.strip() for f in _FRAGMENT_SPLIT_RE.split(normalize_quote(excerpt)) if f.strip()]
    fragments = [f for f in fragments if len(f.split()) >= _MIN_FRAGMENT_WORDS]
    if len(fragments) < 2:
        return None
    norm_text = normalize_quote(text)
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
    match = locate_quotation(excerpt or "", doc.text) or locate_quotation(cleaned, doc.text)
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
    inexact = locate_quotation_inexact(cleaned, doc.text)
    if inexact is not None:
        near, difference = inexact
        return ExcerptCheck(
            "found_inexact", document_id,
            f"the words occur in the document (characters {near.start}-{near.end}) but the quotation {difference}",
            cleaned,
        )
    far = locate_long_elision(cleaned, doc.text)
    if far is not None:
        near, difference = far
        return ExcerptCheck(
            "found_long_elision", document_id,
            f"the words occur in the document (characters {near.start}-{near.end}) but the quotation {difference}",
            cleaned,
        )
    gap = _joined_fragments(cleaned, doc.text)
    if gap is not None:
        return ExcerptCheck(
            "found_joined", document_id,
            "every fragment occurs in order, but the quotation joins separate spans of the text without marking the "
            f"omission (largest omitted span {gap} characters)",
            cleaned,
        )
    return ExcerptCheck("not_found", document_id, "excerpt not found in the document (verbatim or normalized)", cleaned)
