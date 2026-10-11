"""Shared source-integrity helpers for adapters.

Both the generic adapter and the English specialist adapter must answer the same
question deterministically: *does this quoted excerpt occur in the supplied text it
cites?* The authoritative matcher is
:func:`epinoic_logic.translate.grounding.locate_quotation` (verbatim, then
typographic normalization, then explicit ellipsis). This module adds two
conventions of written analysis on top of it, each reported distinctly so nothing
is silently accepted:

* **trailing sentence punctuation inside the quotation marks** (``"legitimate
  defense,"``): the comma or full stop belongs to the sentence, not the quoted
  words, so the match is retried without it. Reported as ``found``.
* **a quotation that joins separate spans without marking the omission**
  (``"We killed him openly, but we're innocent."`` for a dialogue line whose speech
  tag was dropped): every fragment occurs, in order, within a short window, but
  the text as quoted does not. Reported as ``found_joined`` so the adapter can
  flag it as a quotation-form problem rather than an invented quotation.

Nothing here sets ``Grounding.verified``; that remains the grounding module's job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping, Optional

from ..translate.contracts import SuppliedText
from ..translate.grounding import locate_quotation, normalize_quote

__all__ = ["ExcerptCheck", "ExcerptStatus", "check_excerpt", "strip_trailing_punctuation", "word_count"]

ExcerptStatus = Literal["found", "found_joined", "not_found", "no_document", "no_texts", "empty"]

_TRAILING_PUNCT = ".,;:!?"
_FRAGMENT_SPLIT_RE = re.compile(r"[,;:.!?]+")
_JOIN_WINDOW_CHARS = 400
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


def strip_trailing_punctuation(excerpt: str) -> str:
    """Remove sentence punctuation that was written inside the closing quotation mark."""
    return excerpt.strip().rstrip(_TRAILING_PUNCT).strip()


def word_count(text: str) -> int:
    """Whitespace-token count (the proxy used for every length rule)."""
    return len(text.split())


def _joined_fragments(excerpt: str, text: str) -> bool:
    """True when every multi-word fragment of ``excerpt`` occurs in order in ``text``
    within a short window, i.e. the quotation stitches spans together."""
    fragments = [f.strip() for f in _FRAGMENT_SPLIT_RE.split(normalize_quote(excerpt)) if f.strip()]
    fragments = [f for f in fragments if len(f.split()) >= _MIN_FRAGMENT_WORDS]
    if len(fragments) < 2:
        return False
    norm_text = normalize_quote(text)
    cursor = 0
    first: Optional[int] = None
    for frag in fragments:
        pos = norm_text.find(frag, cursor)
        if pos < 0:
            return False
        if first is None:
            first = pos
        cursor = pos + len(frag)
    return first is not None and (cursor - first) <= _JOIN_WINDOW_CHARS + len(excerpt)


def check_excerpt(excerpt: Optional[str], document_id: Optional[str], docs: Mapping[str, SuppliedText]) -> ExcerptCheck:
    """Check ``excerpt`` against the supplied text ``document_id`` names.

    ``docs`` maps document ids to supplied texts. An excerpt with no usable words is
    ``empty``; a missing document is ``no_document`` (or ``no_texts`` when nothing
    was supplied at all); otherwise one of ``found``, ``found_joined``, ``not_found``.
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
            how = "as an elided quotation with fragments in order"
        return ExcerptCheck("found", document_id, f"found {how} at characters {match.start}-{match.end}", cleaned)
    if _joined_fragments(cleaned, doc.text):
        return ExcerptCheck(
            "found_joined", document_id,
            "every fragment occurs in order, but the quotation joins separate spans of the text without marking the omission",
            cleaned,
        )
    return ExcerptCheck("not_found", document_id, "excerpt not found in the document (verbatim or normalized)", cleaned)
