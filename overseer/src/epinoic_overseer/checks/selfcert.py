"""The auditor's own structural self-certification detector (FID-009), independent of the adapters' phrase lists.

It is a token-level rule, not a regular expression over raw text. A sentence is flagged when it has

1. a SUBJECT that refers to the answer's own items:

   * a determiner or quantifier (``every``, ``each``, ``all``, ``these``, ``those``, ``the above``, ``my``, ``our``;
     also ``all of the``, ``each of these``, ``all the``), at most two modifiers and an ITEM NOUN from a closed
     lexicon (quotation, quote, figure, date, number, statistic, claim, fact, point, reference, citation, source,
     detail; named extension: line and excerpt, for "every quoted line above"), optionally followed by words that
     place the items in the answer (``above``, ``here``, ``given``, ``cited``, ``in this answer`` ...);
   * ``the`` with an item noun only when the items are placed in the answer ("the figures above", "the dates in this
     paragraph"), so "the census figures" is never a subject;
   * a first-person ``I`` or ``we`` (then the predicate must be a checking act); and

2. a PREDICATE, reached from the subject across auxiliaries and a few adverbs only, that is a checking act (check,
   verify, confirm, validate, cross-check, compare against, double-check, in any inflection) or an accuracy or
   reliability attribute (accurate, correct, reliable, exact, verbatim, error-free, need no further checking).

A predicate under negation or a deontic modal ("have not been checked", "should be verified", "must be confirmed")
is a disclaimer, not a certification. A check credited to another agent ("checked by the registrar") or dated ("in
1851") is a historical statement about a past check, not a certification of the answer. A first-person check offered
for later ("I will check them against each criterion", "we can verify your table": ``will``, ``shall`` or ``can``
between the subject and the checking act) is an offer to check the reader's work, not a certification of the answer
(named rule ``offered-check``, the translator merge: the merged STEM parser delivers such an offer as a point). The rule
is a heuristic: it only ever yields a warning (FID-009), never an error.
"""
from __future__ import annotations

import re

__all__ = ["flags_self_certification", "sentences"]

_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n(?=\s*(?:[-*•]|\d{1,2}[.)])\s)")

_QUANTIFIERS = frozenset({"every", "each", "all", "these", "those", "my", "our"})
_ITEMS = frozenset({
    "quotation", "quotations", "quote", "quotes", "figure", "figures", "date", "dates", "number", "numbers", "statistic", "statistics",
    "claim", "claims", "fact", "facts", "point", "points", "reference", "references", "citation", "citations", "source", "sources",
    "detail", "details",
    # named extension (r5: "Every quoted line above has been checked against the poem's text")
    "line", "lines", "excerpt", "excerpts",
})
_PLACING = frozenset({"above", "here", "below", "given", "cited", "quoted", "listed", "used", "stated", "provided", "included", "mentioned"})
_PLACE_NOUNS = frozenset({"answer", "paragraph", "response", "essay", "report", "analysis", "text", "section", "summary", "work", "piece"})
_AUX = frozenset({"is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "do", "does", "did", "will", "shall", "can", "all",
                  "both", "each", "also", "now", "already", "carefully", "fully", "thoroughly", "independently", "individually", "personally",
                  "here", "above", "therefore", "hence", "so", "then", "just", "indeed", "every", "one", "of", "them", "it", "entirely",
                  "completely", "wholly", "totally", "absolutely", "and"})
_NEGATION = frozenset({"not", "never", "no", "cannot", "can't", "isn't", "aren't", "wasn't", "weren't", "hasn't", "haven't", "hadn't", "don't",
                       "doesn't", "didn't", "won't", "unverified", "unchecked", "nor"})
_MODAL = frozenset({"should", "must", "need", "needs", "ought", "may", "might", "could", "would", "please"})
_CHECK_STEMS = ("check", "verif", "confirm", "validat", "cross-check", "crosscheck", "double-check", "doublecheck", "compar")
_NOT_CHECKS = frozenset({"checkpoint", "checkpoints", "comparative", "comparatively", "comparable", "incomparable", "checkered", "checkmate"})
_ACCURACY = frozenset({"accurate", "correct", "reliable", "exact", "verbatim", "error-free", "precise", "faithful"})
_FIRST_PERSON_OBJECTS = frozenset({"me", "us", "myself", "ourselves", "hand"})
_MAX_MODIFIERS = 2
_MAX_GAP = 6
#: Rule ``offered-check``: auxiliaries that make a first-person checking act an offer for later, not a check done.
_OFFER = frozenset({"will", "shall", "can"})


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text or "") if s and s.strip()]


def _tokens(sentence: str) -> list[str]:
    return [t.lower().replace("’", "'") for t in _TOKEN_RE.findall(sentence)]


def _is_check(tok: str) -> bool:
    return tok not in _NOT_CHECKS and any(tok.startswith(s) for s in _CHECK_STEMS)


def _is_predicate(tok: str) -> bool:
    return _is_check(tok) or tok in _ACCURACY


def _items_and_place(toks: list[str], j: int) -> tuple[int, bool]:
    """Consume item nouns at ``j`` and any words placing them in the answer; (end index, placed)."""
    while j < len(toks) and toks[j] in _ITEMS:
        j += 1
        if j + 1 < len(toks) and toks[j] == "and" and toks[j + 1] in _ITEMS:
            j += 1
    placed = False
    while j < len(toks):
        if toks[j] in _PLACING:
            j += 1
            placed = True
        elif toks[j] in ("in", "of") and j + 2 < len(toks) and toks[j + 1] in ("this", "the", "my", "our") and toks[j + 2] in _PLACE_NOUNS:
            j += 3
            placed = True
        else:
            break
    return j, placed


def _subject_end(toks: list[str], i: int) -> int:
    """Index just after a subject starting at ``i``, or -1."""
    t = toks[i]
    if t in ("i", "we"):
        return i + 1
    j = i
    needs_place = False
    if t == "the" and j + 1 < len(toks) and toks[j + 1] == "above":
        j += 2
    elif t in _QUANTIFIERS:
        j += 1
        if j + 1 < len(toks) and toks[j] == "of" and toks[j + 1] in ("the", "these", "those", "my", "our"):
            j += 2
        elif j < len(toks) and toks[j] == "the" and t in ("all", "both"):
            j += 1
    elif t == "the":
        j += 1
        needs_place = True
    else:
        return -1
    for _ in range(_MAX_MODIFIERS + 1):
        if j < len(toks) and toks[j] in _ITEMS:
            end, placed = _items_and_place(toks, j)
            if needs_place and not placed:
                return -1
            return end
        if j < len(toks) and toks[j] not in _AUX and toks[j] not in _NEGATION and not _is_predicate(toks[j]) and toks[j] not in _MODAL:
            j += 1  # a modifier ("mileage", "key", "quoted")
            continue
        break
    return -1


def _predicate_at(toks: list[str], j: int) -> int:
    """Index of the predicate reached from ``j`` across auxiliaries, or -1 (negation and modals stop it)."""
    gap = 0
    while j < len(toks) and gap <= _MAX_GAP:
        t = toks[j]
        if t in _NEGATION or t in _MODAL:
            if t in ("need", "needs", "no") and _no_further_check(toks, j):
                return j
            return -1
        if _is_predicate(t):
            return j
        if t == "error" and j + 1 < len(toks) and toks[j + 1] == "free":
            return j
        if t not in _AUX:
            return -1
        j += 1
        gap += 1
    return -1


def _no_further_check(toks: list[str], j: int) -> bool:
    """"need no further checking", "need no checking", "no further verification is needed"."""
    k = j + 1 if toks[j] in ("need", "needs") else j
    if k < len(toks) and toks[k] == "no":
        k += 1
        if k < len(toks) and toks[k] in ("further", "more", "additional"):
            k += 1
        return k < len(toks) and _is_check(toks[k])
    return False


def _historical(toks: list[str], k: int) -> bool:
    """The check is credited to another agent or dated: a past act, not a certification of the answer."""
    window = toks[k + 1:k + 8]
    for n, t in enumerate(window):
        if t == "by" and n + 1 < len(window) and window[n + 1] not in _FIRST_PERSON_OBJECTS:
            nxt = window[n + 1]
            if nxt in ("the", "a", "an", "his", "her", "their", "its") or nxt[:1].isalpha():
                return True
        if t in ("in", "during", "until", "before", "after", "since") and n + 1 < len(window) and window[n + 1].isdigit() and len(window[n + 1]) in (3, 4):
            return True
    return False


def flags_self_certification(sentence: str) -> bool:
    """True when the sentence certifies the answer's own items (see the module docstring)."""
    toks = _tokens(sentence)
    for i in range(len(toks)):
        end = _subject_end(toks, i)
        if end < 0:
            continue
        k = _predicate_at(toks, end)
        if k < 0:
            continue
        if toks[i] in ("i", "we") and not (_is_check(toks[k]) or toks[k] in ("need", "needs", "no")):
            continue  # "I am correct to say ..." is not a check
        if toks[i] in ("i", "we") and _OFFER & set(toks[end:k]):
            continue  # rule offered-check: "I will check them" offers a check of the reader's work; it certifies nothing done
        if _historical(toks, k):
            continue
        return True
    return False
