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
    "UNCREDITED_QUOTATION", "attribute_excerpt", "credited_spans", "document_mentions", "governing_document", "uncredited_assumption", "uncredited_excerpt",
    "Credit", "quotation_credit", "is_peer_text", "peer_prose_span", "credited_agents", "clause_boundaries",
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


#: Verbs of a reporting clause: "The English specialist argues that ... '...'" credits the outer speaker.
_REPORTING_VERB_RE = re.compile(r"^\W*(?:\w+\W+){0,3}?(?:argues?|argued|writes?|wrote|notes?|noted|says?|said|claims?|claimed|suggests?|suggested|describes?|described|calls?|called|"
                                r"observes?|observed|states?|stated|contends?|contended|reports?|reported|gives?|gave|records?|recorded|explains?|explained|remarks?|remarked|"
                                r"quotes?|quoted|cites?|cited|insists?|insisted|maintains?|maintained|puts? it|points? out|dates?|dated|reads?)\b", re.IGNORECASE)
_POSSESSIVE_GAP_RE = re.compile(r"^['’]s?\s*[\"'“”‘’«»„]?\s*$")


def _names_of(doc: SuppliedText) -> list[str]:
    """How a sentence names ``doc``: its author (full name and surname; a specialist agent "history-specialist" also as
    "history specialist"), and the title of a non-peer text up to any parenthesis, colon or comma."""
    names: list[str] = []
    author = (doc.author or "").strip()
    if author:
        names.append(author)
        if author.endswith("-specialist"):
            names.append(author.replace("-", " "))
        parts = author.split()
        if len(parts) > 1 and len(parts[-1]) >= 3 and parts[-1][0].isupper():
            names.append(parts[-1])
    peer = doc.document_id.startswith("peer:") or author.endswith("-specialist")
    if doc.title and not peer:
        title = re.split(r"[(:,]", doc.title)[0].strip()
        if len(title) >= 3:
            names.append(title)
    return [n for n in names if len(n) >= 3]


def _mentions(sentence: str, doc: SuppliedText) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for name in _names_of(doc):
        out += [(m.start(), m.end()) for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", sentence, re.IGNORECASE)]
    return sorted(set(out))


def document_mentions(sentence: str, doc: SuppliedText) -> list[tuple[int, int]]:
    """Where ``sentence`` names ``doc`` (by author, surname, title, or a relayed specialist's name), as character spans."""
    return _mentions(sentence, doc)


#: Where a credited clause ends: a semicolon, "!" or "?", a full stop or colon followed by whitespace or the end of the
#: text (never the "." of a decimal, "5.2 million", nor the ":" of a time), a comma before a conjunction, or a spaced dash.
#: A full stop after an abbreviation or an initial ("c. 1963", "Chester A. Arthur") does not end it either.
_CLAUSE_END_RE = re.compile(r"[;!?]|[.:](?=\s|$)|,\s+(?:but|while|whereas|although|though|yet|so)\b|\s[-–—]\s")
_ABBREVIATION_RE = re.compile(r"(?:^|[\s(\[])(?:c|ca|cf|approx|circa|e\.g|i\.e|vs|viz|vol|pp?|nos?|fig|St|Mr|Mrs|Ms|Dr|Jr|Sr|Gen|Col|Capt|Lt|Rev|Prof|Mt|[A-Z])$", re.IGNORECASE)
#: A credit that names the colleague after the words it credits: "according to the History specialist", "in the words
#: of the History specialist" (the mention follows it).
_ACCORDING_TO_RE = re.compile(r"\b(?:according\s+to|in\s+the\s+words\s+of|as\s+(?:reported|stated|given|recorded|noted)\s+by)\s+(?:the\s+)?$", re.IGNORECASE)
#: The start of the clause that ends where "according to <peer>" begins ("About 7.2 million arrived, according to ...").
_CLAUSE_START_RE = re.compile(r"[;!?]\s*|[.:](?=\s)\s*|,\s+(?:and|but|while|whereas|although|though|yet|so)\b\s*|\s[-–—]\s")


_BOUNDARY_RE = re.compile(r"[,;:](?=\s)|[.!?](?=[\s\"'”’)]|$)")


def clause_boundaries(text: str) -> list[int]:
    """Offsets of the clause boundaries of ``text``: a comma, semicolon or colon followed by whitespace, and a sentence stop
    followed by whitespace, a closing mark or the end, but never the point of a decimal ("3.3 million"), the full stop of
    an abbreviation or an initial ("c. 1963", "Chester A. Arthur"), nor the ":" of a time. Used wherever a clause of a
    specialist's sentence is quoted back, so a quotation never starts or stops inside a figure."""
    out: list[int] = []
    for m in _BOUNDARY_RE.finditer(text):
        if m.group(0) == "." and _ABBREVIATION_RE.search(text[:m.start()]):
            continue
        out.append(m.start())
    return out


def _clause_end(rest: str) -> int:
    """Offset in ``rest`` where its clause ends (:data:`_CLAUSE_END_RE`, skipping the full stop of an abbreviation)."""
    for m in _CLAUSE_END_RE.finditer(rest):
        if m.group(0) == "." and _ABBREVIATION_RE.search(rest[:m.start()]):
            continue
        return m.start()
    return len(rest)


def _clause_start(head: str) -> int:
    """Offset in ``head`` where the clause it ends with begins."""
    start = 0
    for m in _CLAUSE_START_RE.finditer(head):
        if m.group(0).startswith(".") and _ABBREVIATION_RE.search(head[:m.start()]):
            continue
        start = m.end()
    return start


def credited_spans(sentence: str, doc: SuppliedText) -> list[tuple[int, int]]:
    """The spans of ``sentence`` it credits to ``doc``: after each mention of ``doc`` that is a possessive ("the History
    specialist's figure of ...", "in the History specialist's account, ..."), the subject of a reporting verb ("the
    History specialist gives ...", "as the History specialist notes, ...") or the object of "according to" ("According
    to the History specialist, about 7.2 million ..."), the rest of that clause; when "according to <peer>" closes its
    clause ("About 7.2 million arrived, according to the History specialist."), the clause before it. A clause never ends
    at the point of a decimal ("5.2 million") or of an abbreviation ("c. 1963"). A figure inside such a span is stated
    as the colleague's."""
    out: list[tuple[int, int]] = []
    for a, b in _mentions(sentence, doc):
        rest = sentence[b:]
        leading = _ACCORDING_TO_RE.search(sentence[:a])
        if not (rest.startswith(("'s", "’s", "'", "’")) or _REPORTING_VERB_RE.match(rest) or leading):
            continue
        end = _clause_end(rest)
        if leading and not re.search(r"[^\W_]", rest[:end]):  # "..., according to the History specialist." credits the clause before
            head = sentence[:leading.start()]
            out.append((_clause_start(head), leading.start()))
            continue
        out.append((b, b + end))
    return out


def governing_document(sentence: str, excerpt: str, named: Sequence[str], docs: Mapping[str, SuppliedText]) -> tuple[Optional[str], str]:
    """Among the several texts a sentence names, the one its quotation of ``excerpt`` is credited to, and why: the text
    whose possessive governs the quotation ("the History specialist's '...'"), else the outer speaker of a reporting
    clause ("The English specialist argues that Blake presents ... '...'"), else the text named nearest before the
    quotation, else the first text the sentence names. ``(None, "")`` when the sentence names none of ``named``."""
    pos = sentence.find(excerpt.strip()) if excerpt.strip() else -1
    if pos < 0:
        pos = sentence.casefold().find(excerpt.strip().casefold()[:40]) if excerpt.strip() else -1
    found: list[tuple[int, int, str]] = []
    for doc_id in named:
        doc = docs.get(doc_id)
        if doc is None:
            continue
        found += [(a, b, doc_id) for a, b in _mentions(sentence, doc) if pos < 0 or not (pos <= a < pos + len(excerpt))]
    if not found:
        return None, ""
    found.sort()
    if pos >= 0:
        before = [m for m in found if m[1] <= pos]
        for a, b, doc_id in reversed(before):  # a possessive right before the opening mark governs the quotation
            gap = sentence[b:pos].strip()
            if gap.startswith(("'", "’")) and _POSSESSIVE_GAP_RE.match(gap):
                return doc_id, "its possessive governs the quotation"
        for a, b, doc_id in reversed(before):  # the nearest reporting clause: its speaker is the one quoted
            if _REPORTING_VERB_RE.match(sentence[b:pos]):
                return doc_id, "it is the speaker of the reporting clause that introduces the quotation"
        if before:
            return before[-1][2], "it is the text named nearest before the quotation"
    return found[0][2], "it is the first text the sentence names"


# ------------------------------------------------------------------ who a quotation is credited to (credit, not location)

#: Verbs that credit the words after them to their subject: "Hardy's speaker admits that ...", "The poem says ...", "The
#: English specialist argues that ...". Wider than the reporting verbs above (a speaker admits, confesses, declares, asks).
_CREDIT_VERBS = (r"(?:argues?|argued|writes?|wrote|notes?|noted|says?|said|claims?|claimed|suggests?|suggested|describes?|described|calls?|called|"
                 r"observes?|observed|states?|stated|contends?|contended|reports?|reported|explains?|explained|remarks?|remarked|insists?|insisted|"
                 r"maintains?|maintained|admits?|admitted|confess(?:es|ed)?|declares?|declared|tells?|told|asks?|asked|answers?|answered|concedes?|"
                 r"conceded|complains?|complained|recalls?|recalled|reflects?|reflected|wonders?|wondered|thinks?|thought|puts? it|points? out|adds?|added|"
                 r"concludes?|concluded|identifies|identified|reads?|speaks? of|spoke of|refers? to|referred to|mentions?|mentioned|quotes?|quoted|cites?|"
                 r"cited|presents?|presented|depicts?|depicted|portrays?|portrayed|labels?|labelled|labeled|terms?|termed|dubs?|dubbed|recounts?|recounted|"
                 r"reveals?|revealed|confirms?|confirmed|acknowledges?|acknowledged|exclaims?|exclaimed|protests?|protested|replies|replied|announces?|announced|"
                 r"dates?|dated|counts?|counted|gives?|gave|records?|recorded|estimates?|estimated|places?|placed|puts?|sees?|saw|treats?|treated|"
                 r"interprets?|interpreted|attributes?|attributed|traces?|traced|finds?|found|judges?|judged|holds?|held|names?|named|uses?|used|employs?|employed)")
#: Nouns a possessive may govern before the verb: "Hardy's speaker admits", "the English specialist's paragraph identifies".
_CREDIT_NOUNS = (r"(?:speaker|narrator|persona|poem|poet|line|lines|words?|phrase|phrasing|text|voice|monologue|paragraph|reading|account|verse|"
                 r"stanza|soldier|man|character|report|analysis|essay|view|argument|claim|note|sonnet|novel|play|story)")
_CREDIT_ADVERBS = r"(?:himself|herself|itself|themselves|also|then|even|openly|plainly|bluntly|simply|directly|explicitly|rightly|famously|later|here|still)"
#: The words between a credited name and its quotation: a bare possessive ("Hardy's '...'"), or an optional possessive
#: noun, adverbs and a crediting verb, then the rest of the clause.
_CREDIT_GAP_RE = re.compile(
    r"^(?:['’]s?\s*[,:]?\s*$"
    r"|(?:['’]s?(?:\s+own)?(?:\s+" + _CREDIT_NOUNS + r")?)?\s*,?\s+(?:" + _CREDIT_ADVERBS + r"\s+)*" + _CREDIT_VERBS + r"\b)",
    re.IGNORECASE)
#: Where a clause ends, so a verb never credits a quotation of the next clause ("Hardy's speaker calls the war 'quaint',
#: and the casualness 'exposes ...'": the second quotation is not the speaker's).
_CREDIT_CLAUSE_END_RE = re.compile(r"[;!?]|\.\s|:\s|,\s+(?:and|but|while|whereas|although|though|yet|so)\b|\s[-–—]\s")
#: A text named by kind rather than by name: "the poem", "the poet", "the speaker".
_GENERIC_LITERARY_RE = re.compile(r"\b(?:the|this)\s+(?:poem|poet|speaker|narrator|play|novel|sonnet|extract|passage|monologue|story)\b", re.IGNORECASE)
_LEADING_CREDIT_RE = re.compile(r"\b(?:according to|in the words of)\s+$", re.IGNORECASE)


@dataclass(frozen=True)
class Credit:
    """Who a quotation is credited to: ``document_id`` (None for a text named by kind, "the poem", when no one literary
    text is known), the ``phrase`` of the sentence that names it, and whether it is a text named by kind."""
    document_id: Optional[str]
    phrase: str
    generic: bool = False


def is_peer_text(doc: SuppliedText) -> bool:
    """A relayed specialist's report supplied as a document ('peer:<task>', or an author '<subject>-specialist')."""
    author = (doc.author or "").strip().lower()
    return doc.document_id.startswith("peer:") or author.endswith("-specialist") or author.endswith(" specialist")


def quotation_credit(sentence: str, quote_start: int, docs: Mapping[str, SuppliedText], *, other_sources: Sequence[str] = ()) -> Optional[Credit]:
    """The source ``sentence`` credits with the quotation that opens at ``quote_start``: the nearest text named before
    it (by author, surname, title or specialist name, or by kind: "the poem", "the speaker") whose name is followed by a
    possessive that governs the quotation ("Hardy's '...'") or by a crediting verb, through a possessive noun and adverbs
    ("Hardy's speaker himself admits that ...", "The poem says that ...", "The English specialist argues that ..."), with
    no clause boundary between the verb and the quotation; or a text after "according to". None when the sentence
    credits the quotation to no text. Names inside quotations are not read. A text named by kind is the one non-peer
    text of ``docs`` when there is exactly one, else a credit with no document. ``other_sources`` are further names
    (an author a colleague's report discusses, "Hardy") that credit a text not among ``docs``: a credit with no document."""
    from .markdown import find_quotation_spans
    spans = [(a, b) for a, b, _inner in find_quotation_spans(sentence)]

    def quoted(pos: int) -> bool:
        return any(a <= pos < b for a, b in spans)

    mentions: list[tuple[int, int, Optional[str], bool]] = []
    for doc_id, doc in docs.items():
        mentions += [(a, b, doc_id, False) for a, b in _mentions(sentence, doc) if not quoted(a)]
    for name in other_sources:
        if len(name) >= 3:
            mentions += [(m.start(), m.end(), None, False) for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", sentence) if not quoted(m.start())]
    literary = sorted({d for d, t in docs.items() if not is_peer_text(t) and not d.startswith("request:")})  # a request is the router's text, never 'the poem'
    for m in _GENERIC_LITERARY_RE.finditer(sentence):
        if not quoted(m.start()):
            mentions.append((m.start(), m.end(), literary[0] if len(literary) == 1 else None, True))
    before = sorted((m for m in mentions if m[1] <= quote_start), key=lambda m: (m[1], m[0]), reverse=True)
    credits: list[tuple[Credit, bool]] = []  # nearest first; True when the verb opens a reported clause ("argues that")
    for a, b, doc_id, generic in before:
        gap = sentence[b:quote_start]
        if _LEADING_CREDIT_RE.search(sentence[:a]) and re.fullmatch(r"\s*,?\s*", gap):
            credits.append((Credit(doc_id, sentence[a:b], generic), False))
            continue
        m = _CREDIT_GAP_RE.match(gap)
        if m is None or _CREDIT_CLAUSE_END_RE.search(gap[m.end():]):
            continue
        credits.append((Credit(doc_id, sentence[a:b + m.end()].strip(), generic), bool(re.match(r"\s+that\b", gap[m.end():], re.IGNORECASE))))
    if not credits:
        return None
    # A reporting clause credits its OUTER speaker: in "The English specialist argues that Blake presents ... '...'" the
    # words are the English specialist's report, not Blake's. The nearest speaker whose verb opens a reported clause wins.
    reporting = [c for c, opens_report in credits if opens_report]
    return reporting[0] if reporting else credits[0][0]


def peer_prose_span(excerpt: str, doc: SuppliedText) -> bool:
    """True when ``excerpt`` is located in the peer report ``doc`` in its own prose, outside the quotations the peer
    itself makes (the colleague's own words, not a text the colleague quoted)."""
    from .markdown import find_quotation_spans
    match = locate_quotation(excerpt, doc.text, document_id=doc.document_id) or locate_quotation(strip_trailing_punctuation(excerpt), doc.text, document_id=doc.document_id)
    if match is None:
        inexact = locate_quotation_inexact(strip_trailing_punctuation(excerpt), doc.text, document_id=doc.document_id)
        if inexact is None:
            return False
        match = inexact[0]
    return not any(a <= match.start and match.end <= b for a, b, _inner in find_quotation_spans(doc.text))


def credited_agents(text: str, agent_ids: Sequence[str]) -> list[str]:
    """The agents ``text`` credits with a view: a specialist named (as "the English specialist" for the agent id
    "english-specialist") with a possessive or as the subject of a crediting verb, outside quotations."""
    from .markdown import find_quotation_spans
    masked = text
    for a, b, _inner in reversed(find_quotation_spans(text)):
        masked = masked[:a] + " " * (b - a) + masked[b:]
    out: list[str] = []
    for agent in agent_ids:
        doc = SuppliedText(document_id=f"agent:{agent}", title=None, author=agent, text=" ")
        for _a, b in _mentions(masked, doc):
            rest = masked[b:b + 200]
            if re.match(r"['’]s?\b", rest) or re.match(r"\s*,?\s+(?:" + _CREDIT_ADVERBS + r"\s+)*" + _CREDIT_VERBS + r"\b", rest, re.IGNORECASE):
                out.append(agent)
                break
    return out


#: A capitalised name a colleague's report uses as a possessive ("Hardy's dramatic monologue"): the author it discusses.
_DISCUSSED_AUTHOR_RE = re.compile(r"(?<![\w'’])([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)['’]s\b")
_NOT_AN_AUTHOR = frozenset("The This That These Those Its His Her Their Our History English Economics Psychology Business".split())


def _credit_to_unsupplied(sentence: str, excerpt: str, docs: Mapping[str, SuppliedText], located: Sequence[str]) -> Optional[str]:
    """The assumption a parser records when ``sentence`` credits a quotation to a source that is not a supplied text (an
    author the colleague's report discusses, "Hardy's speaker admits that ...", or a text named by kind, "The poem says")
    while its words were located only in a relayed colleague's report, in the colleague's own prose: the credit is
    wrong (``CORE-SRC-005`` / the channel's ``INT-REQ-015``). None when the sentence credits the colleague or nothing."""
    from .markdown import find_quotation_spans
    key = excerpt.strip().casefold()[:40]
    span = next((s for s in find_quotation_spans(sentence) if key and key in s[2].casefold()), None)
    if span is None:
        return None
    discussed = sorted({m.group(1) for d in located for m in _DISCUSSED_AUTHOR_RE.finditer(docs[d].text) if m.group(1).split()[0] not in _NOT_AN_AUTHOR})
    credit = quotation_credit(sentence, span[0], docs, other_sources=discussed)
    if credit is None or (credit.document_id is not None and is_peer_text(docs[credit.document_id])):
        return None
    if not any(peer_prose_span(excerpt, docs[d]) for d in located):
        return None
    return (f"the sentence credits this quotation to {credit.phrase!r}, which is not a supplied text, but the words were located only in "
            f"{', '.join(located)}, in the colleague's own prose (a colleague's words credited to the source)")


def attribute_excerpt(excerpt: str, named: Sequence[str], docs: Mapping[str, SuppliedText], *,
                      text_under_analysis: Optional[str] = None, sentence: Optional[str] = None) -> tuple[Optional[str], list[str]]:
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
    sentence names nothing; it is credited only when the sentence names no text at all.

    ``sentence`` (the sentence with its quotation marks) lets a quotation located in no text,
    in a sentence that names SEVERAL texts, be credited by the reporting-clause rule
    (:func:`governing_document`: the possessive that governs it, the outer speaker, the text
    named nearest before it), so an altered quotation of a colleague in a sentence that also
    names the poet stays an ``INT-REQ-003`` error naming the claim; the assumption names every
    text the sentence names. Without ``sentence`` such a quotation is credited to no text."""
    if not docs:
        return None, [uncredited_assumption(excerpt)]
    located = [doc_id for doc_id in docs if check_excerpt(excerpt, doc_id, docs).located]
    searched = ", ".join(docs)
    if located:
        if len(named) == 1 and named[0] in located:
            return named[0], []
        if len(named) == 1:
            return located[0], [f"the sentence attributes this quotation to {named[0]} but the words were located only in {', '.join(located)}"]
        if sentence and not named and all(is_peer_text(docs[d]) for d in located):
            note = _credit_to_unsupplied(sentence, excerpt, docs, located)
            if note:
                return located[0], [note]
        return located[0], []
    if len(named) == 1:
        return named[0], [f"excerpt found in none of the supplied texts [{searched}]; attributed to {named[0]} because the sentence names it"]
    if len(named) > 1 and sentence:
        doc_id, why = governing_document(sentence, excerpt, named, docs)
        if doc_id is None:  # named by a cue the name finder does not read ("the poem"): never credited to none
            doc_id, why = named[0], "it is the first of the texts the sentence names"
        if doc_id is not None:
            return doc_id, [f"excerpt found in none of the supplied texts [{searched}]; the sentence names several supplied texts ({', '.join(named)}) "
                            f"and it is attributed to {doc_id} because {why}"]
    if not named and text_under_analysis is not None and text_under_analysis in docs:
        return text_under_analysis, [f"excerpt found in none of the supplied texts [{searched}]; attributed to {text_under_analysis}, "
                                     "the one literary text under analysis, because the sentence names no supplied text"]
    why = "the sentence names no supplied text" if not named else f"the sentence names several supplied texts ({', '.join(named)})"
    return None, [uncredited_assumption(excerpt, f"{why} and the words occur in none of [{searched}]")]
