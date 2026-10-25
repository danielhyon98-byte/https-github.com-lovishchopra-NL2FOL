"""Deterministic grounding checks.

Source integrity is a non-negotiable of the specialist agents: never invent
quotations or citations. This module checks the one kind of grounding that code
can check exactly, a quotation against the supplied text, and marks every other
kind as not checkable. It sets ``Grounding.verified``; nothing else does.

Matching is attempted in three tiers, reported through ``GroundingCheck.method``:

1. ``verbatim_match``: the excerpt occurs character for character.
2. ``normalized_match``: the excerpt occurs after typographic normalization of both
   sides (curly/straight quotes, dash variants and the spaces around a dash, whitespace
   runs, ellipsis forms, invisible characters): ``like - just as I -`` typed for the
   text's ``like—just as I—`` is the same quotation. Case is NOT folded: a changed word is a changed quotation.
   Two further normalizations belong to this tier because they are the conventions
   of quoting itself, not changes to the words: the quotation marks INSIDE an excerpt
   are folded to one class (a quotation that nests the text's double marks as single
   marks matches; ``QuotationMatch.note`` says so), and a line break of the document
   may be written ``" / "`` in the excerpt (verse quoted in running prose).
3. ``normalized_match`` with elision: an excerpt containing an ellipsis matches when
   each fragment occurs in order in the normalized text AND the whole span stays
   within :data:`ELISION_WINDOW_CHARS` plus the excerpt's own length. Fragments that
   are far apart are a long elision, reported by the inexact tier, never as a match.
   An elision mark in brackets or parentheses (``[...]``, ``[…]``, ``[ . . . ]``,
   ``(...)``), the academic form, is read as the same ellipsis in every tier
   (:func:`unbracket_elisions`).

A fourth, *inexact* tier (:func:`locate_quotation_inexact`) finds the words after a
conventional adjustment of written analysis: a changed initial capital (a sentence
opening quoted mid-sentence), omitted or added verse line-break marks (``/``), or the
text's own double speech mark at a line or stanza start or end left out of a quotation that
runs across the break (:data:`NOTE_EDGE_MARKS`; every stanza of a dramatic monologue that
opens with a speech mark);
:func:`locate_long_elision` finds an elision whose fragments all occur in order but span
more than the elision window. The inexact tier also folds diacritics on both sides (each
character decomposed with NFKD and its combining marks, Unicode category Mn, dropped, the
offset map kept), so ``"Bayardo San Román"`` quoted from a text that prints ``Bayardo San
Roman`` is located and reported as differing in diacritics. Neither verifies a grounding:
``Grounding.verified`` stays ``False`` for the IR path, but the check's ``detail`` says the
quotation *differs in form* and names the difference, so the Overseer (and the channel) can
tell a form problem from an invented quotation.

An excerpt that differs from the text only in how its accented letters are encoded
(precomposed ``é`` against ``e`` plus a combining accent) has the same letters: the
normalized tier finds it (``QuotationMatch.note`` says so), never the diacritics tier.

Every reference of a grounding is checked, whatever its ``kind``: an excerpt is located in the
named document, and a reference without an excerpt has its document (and the plausibility of
its locator) checked. Each reference keeps its own outcome (``GroundingCheck.ref_index``), and
the references together give the target's support (:func:`grounding_support`): ``complete``,
``partial``, ``failed`` or ``uncheckable``. Only complete support verifies a grounding: a
reference to a document that was never supplied is surfaced and never hidden behind another
reference that was found. A grounding with no reference is ``not_checkable``.

Figures are typed (:mod:`.quantities`): a located excerpt verifies a premise only when it
states the premise's figures, compared as exact values with one recorded derivation where the
spelling differs (``20%`` for ``0.2`` or ``1/5`` is ``20 x 1/100 = 1/5``), and in the reading
the compared symbol's meaning declares (a dimensionless fraction, a percentage, a unit). A figure
the record states as ROUNDED ("x is 0.33 to 2 decimal places", "about 0.33", "0.33 (3 s.f.)")
states every value within its stated tolerance, so it also establishes an assignment's bounds at
the two ends of that interval (``x >= 0.325 and x < 0.335``: one recorded derivation,
:func:`.quantities.stated_intervals`); a symbol bounded on both sides takes both ends from one
stated interval. A wider, narrower or shifted interval is not what the record states, and an
exact or given figure (no rounding cue) states no interval at all, so an interval in its place
stays unestablished. The numeral of a precision cue is no end of a range: "0.33 to 2 decimal
places" states 0.33.

Whole content. A check confers task or source authority on a premise (``verified=True``) only when it
verifies the premise's WHOLE content (:mod:`.relations`). For a premise with numeric content that is
one of two shapes. An **assignment** (each conjunct compares one symbol with one literal: ``d = 120``,
``n >= 5``) is verified by a record that states the figure, typed, in a way that establishes the
comparison (:func:`.assertion.stated_as`: "more than 17" establishes no ``n = 17``; "at most 350
words" establishes ``limit = 350`` and ``words <= 350``; a figure negated or excluded where it stands
or in its own predicate, "x is not 17", or one option of a disjunction or one end of a range, establishes
nothing). A **relation** (arithmetic
over symbols or figures, a comparison of two terms, an inequation, a comparison inside a logical
formula) is never verified by its figures occurring in a record: the ``8`` of "120 km in 8 hours" is
no evidence for ``speed = d * 8``. Only a record that STATES the same relation as a formula, as a
given, verifies it (:func:`.relations.stated_relation`, method ``relation_in_source``); otherwise the
relation is the translation's own and stays unverified (``verified=None``: an unverified dependency
that blocks release), whatever its grounding kind, and even when its excerpt was located. A premise
with no numeric content (a proposition) keeps the span rule: located excerpts are its reference.

Authority. The kinds ``arithmetic_fact``, ``task_setting`` and ``rubric_rule`` claim the task's
authority, which only application-created records confer: the supplied texts and the task
record (:class:`~.contracts.TaskRecord`). The kind is the translator's proposal and stays
unchecked until code validates it (:func:`check_problem_grounding`, methods ``numeric_in_task``
and ``relation_in_source``):

* **validated** (``verified=True``): an excerpt of those records is located and states the
  premise's whole content, or the records state it (an assignment: every figure, typed, with spans
  and derivations, stated so that it establishes the comparison; a relation: the formula itself,
  stated as a given);
* **refuted** (``verified=False``, an evidence failure the engine reports as an ungrounded
  dependency): the task record was given and neither it nor a supplied text states the figure,
  or the records state another figure of the same unit and none of the premise's (the supplied
  text says 120 km where the premise says 160 km);
* **unvalidated** (``verified=None``, recorded with a ``numeric_in_task`` or ``relation_in_source``
  check whose ``verified`` is None): no record available to this layer states it or contradicts it
  (the task's own wording was not given), or the records state a relation's figures but not the
  relation. It is never trusted by this layer: the outcome lists it as unvalidated task authority
  and does not permit release on it.

Offsets returned always refer to the ORIGINAL text.

Cost. A supplied text's normalised forms (typographic, verse line breaks as slashes, quote
marks folded, line-break marks dropped, diacritics folded) and their offset maps are built
once per text, on first use, and kept in a bounded least-recently-used cache keyed by
``(document_id, sha256 of the text)`` (:class:`TextForms`); every locating function answers
from that cache and memoises its own answer per ``(excerpt, sha256 of the text)`` in a
second bounded cache, so one parse or check never locates the same excerpt in the same
document twice, whichever caller asks. Every cached value is a pure function of the excerpt and the text, so a
cached answer is the answer the uncached code gives; both caches are thread-safe.
"""
from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Hashable, Literal, Optional, Sequence

from ..ir.schema import Assertion, Grounding, Problem, SourceRef, Symbol
from .contracts import ClaimRecord, GroundingCheck, GroundingSupport, SuppliedText, TaskRecord
from .assertion import stated_as
from .quantities import (TRIVIAL_VALUES, DeclaredReading, SourceText, declared_reading, figure_stated_plainly, figures_in, interval_derivation,
                         literal_matches, rounded_intervals)
from .relations import assignment_parts, numeric_shape, stated_relation, writes_relation

MatchMethod = Literal["verbatim_match", "normalized_match"]
#: Largest distance (characters of the original text, beyond the excerpt's own length)
#: that the fragments of an elided quotation may span and still count as one quotation.
ELISION_WINDOW_CHARS = 400

_CHAR_MAP: dict[str, str] = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "´": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    "…": "...",
}
_INVISIBLE = frozenset({"­", "​", "‌", "‍", "⁠", "﻿"})
_OUTER_QUOTES = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("«", "»"))


@dataclass(frozen=True)
class QuotationMatch:
    """Where an excerpt was found in the original text and how. ``note`` names a
    quoting convention the match relied on beyond typographic normalization."""
    start: int
    end: int
    matched: str
    method: MatchMethod
    elided: bool = False
    note: Optional[str] = None


#: Every grounding check whose quotation was located in another form says so in its detail with these words.
FORM_DIFFERS = "differs in form"
NOTE_QUOTES_FOLDED = "quotation marks inside the excerpt folded to one class (the nesting level of the marks differs)"
NOTE_LINEBREAK_SLASH = "line breaks of the document written as ' / ' in the excerpt"
NOTE_COMPOSITION = "accented letters encoded differently (precomposed against a letter plus a combining mark); the letters are the same"


def _normalize_indexed(text: str, *, newline_as_slash: bool = False) -> tuple[str, list[int]]:
    """Normalize ``text``; return the result and, per output char, its source offset.

    With ``newline_as_slash`` every line break of ``text`` is rendered ``" / "``, the
    convention for quoting verse in running prose, so an excerpt written that way
    matches the document's lines; a blank line (a stanza break) is rendered ``" // "``.
    Matching compares slash runs leniently (:func:`_fold_slash_runs`), so a quotation
    that writes the stanza break as ``" / "`` or ``" // "`` is found either way."""
    out: list[str] = []
    idx: list[int] = []
    pending_space: Optional[int] = None
    for pos, ch in enumerate(text):
        if ch in _INVISIBLE:
            continue
        if ch.isspace():
            if newline_as_slash and ch == "\n" and out:
                if out[-1] == "/":  # a blank line: the second break joins the first mark as "//"
                    out.append("/")
                    idx.append(pos)
                    pending_space = pos
                    continue
                out.append(" ")
                idx.append(pending_space if pending_space is not None else pos)
                out.append("/")
                idx.append(pos)
                pending_space = pos
                continue
            if out and pending_space is None:
                pending_space = pos
            continue
        if pending_space is not None:
            out.append(" ")
            idx.append(pending_space)
            pending_space = None
        for mapped in _CHAR_MAP.get(ch, ch):
            if mapped == "-" and out and out[-1] == "-":
                continue  # collapse dash runs ("--" and "---" both become "-")
            out.append(mapped)
            idx.append(pos)
    if "-" in out:
        out, idx = _close_dash_spaces(out, idx)
    return _collapse_spaced_ellipsis(out, idx)


def _close_dash_spaces(chars: list[str], idx: list[int]) -> tuple[list[str], list[int]]:
    """Drop the spaces on both sides of a dash (every dash variant is already ``-``), so a spaced dash typed for the
    text's em dash (``like - just``, ``like – just``) compares equal to ``like—just`` and to ``like — just``: the
    spacing of a dash is typography, not words. Applied to the text and the excerpt alike."""
    out: list[str] = []
    out_idx: list[int] = []
    n = len(chars)
    for i, ch in enumerate(chars):
        if ch == " " and ((i + 1 < n and chars[i + 1] == "-") or (out and out[-1] == "-")):
            continue
        out.append(ch)
        out_idx.append(idx[i])
    return out, out_idx


def _collapse_spaced_ellipsis(chars: list[str], idx: list[int]) -> tuple[str, list[int]]:
    """Rewrite ``. . .`` as ``...`` so spaced and unspaced ellipses compare equal."""
    out: list[str] = []
    out_idx: list[int] = []
    i = 0
    n = len(chars)
    while i < n:
        if chars[i] == "." and i + 4 < n and chars[i + 1] == " " and chars[i + 2] == "." and chars[i + 3] == " " and chars[i + 4] == ".":
            out.extend(["...", ])
            out_idx.extend([idx[i]])
            out[-1:] = [".", ".", "."]
            out_idx[-1:] = [idx[i], idx[i + 2], idx[i + 4]]
            i += 5
            continue
        out.append(chars[i])
        out_idx.append(idx[i])
        i += 1
    return "".join(out), out_idx


def normalize_quote(s: str) -> str:
    """Typographic normalization used for tier-2 matching (see module docstring)."""
    return _normalize_indexed(s)[0]


def _fold_slash_runs(chars: str, idx: Optional[list[int]] = None) -> tuple[str, list[int]]:
    """Fold a run of verse line-break marks (``//``, ``/ /``) to one ``/`` so a stanza break
    written with one or two marks compares equal; the offset map (``idx``) is kept in step.
    With ``idx`` None an identity map is used (for an excerpt, whose offsets are not needed)."""
    if idx is None:
        idx = list(range(len(chars)))
    out: list[str] = []
    out_idx: list[int] = []
    for ch, pos in zip(chars, idx):
        if ch == "/":
            k = len(out) - 1
            while k >= 0 and out[k] == " ":
                k -= 1
            if k >= 0 and out[k] == "/":  # a second mark of the same break: drop it and the spaces between
                del out[k + 1:]
                del out_idx[k + 1:]
                continue
        out.append(ch)
        out_idx.append(pos)
    return "".join(out), out_idx


def _fold_diacritics_indexed(chars: str, idx: Optional[Sequence[int]] = None) -> tuple[str, list[int]]:
    """Fold diacritics: every non-ASCII character is decomposed (NFKD) and its combining
    marks (Unicode category ``Mn``) are dropped, so ``Román`` and ``Roman`` compare equal.
    The offset map (``idx``; an identity map when None) is kept in step: each character a
    decomposition yields maps to the offset of the character it came from."""
    if idx is None:
        idx = range(len(chars))
    out: list[str] = []
    out_idx: list[int] = []
    for ch, pos in zip(chars, idx):
        if ch.isascii():
            out.append(ch)
            out_idx.append(pos)
            continue
        for part in unicodedata.normalize("NFKD", ch):
            if unicodedata.category(part) != "Mn":
                out.append(part)
                out_idx.append(pos)
    return "".join(out), out_idx


def fold_diacritics(s: str) -> str:
    """``s`` with its diacritics folded (see :func:`_fold_diacritics_indexed`)."""
    return s if s.isascii() else _fold_diacritics_indexed(s)[0]


def _extend_over_marks(text: str, end: int) -> int:
    """Move ``end`` past combining marks that follow it in ``text`` (an accent written as a
    letter plus a combining mark belongs to the letter it follows)."""
    while end < len(text) and unicodedata.category(text[end]) == "Mn":
        end += 1
    return end


#: An elision mark in brackets or parentheses, the academic form of an ellipsis: "[...]", "[…]", "[ . . . ]", "(...)".
_BRACKETED_ELISION_RE = re.compile(r"\s*[\[(]\s*(?:(?:\.\s*){3}|…)\s*[\])]\s*")


def unbracket_elisions(excerpt: str) -> str:
    """``excerpt`` with every bracketed or parenthesised elision mark ("[...]", "[…]", "[ . . . ]", "(...)") written as
    the plain ellipsis " ... " every tier reads as an elision, so a quotation in the standard academic form is located
    like the same words with "..." (never reported as invented)."""
    if "[" not in excerpt and "(" not in excerpt:
        return excerpt
    return _BRACKETED_ELISION_RE.sub(" ... ", excerpt).strip()


def _strip_outer_quotes(excerpt: str) -> str:
    s = excerpt.strip()
    for left, right in _OUTER_QUOTES:
        if len(s) >= 2 and s.startswith(left) and s.endswith(right):
            return s[1:-1].strip()
    return s


def _span(idx: Sequence[int], start: int, length: int) -> tuple[int, int]:
    return idx[start], idx[start + length - 1] + 1


def _fold_quote_marks(normalized: str) -> str:
    """After normalization every quotation mark is ``'`` or ``"``; fold both to one class.
    The mapping is one character to one, so an offset map stays valid."""
    return normalized.replace("'", '"')


def _folded_candidates(norm_ex: str) -> list[str]:
    """The excerpt with its quotation marks folded, and, when a mark sits at an edge, the
    excerpt without that edge mark: a quoter who nests the text's quotation closes it at the
    end of the excerpt even where the text's own quotation runs on."""
    folded = _fold_quote_marks(norm_ex)
    out = [folded]
    trimmed = folded.strip('"').strip()
    if trimmed and trimmed != folded:
        out.append(trimmed)
    return out


def _find_folded(norm_ex: str, norm_text: str, idx: Sequence[int], text: str, note: str, folded_text: Optional[str] = None) -> Optional[QuotationMatch]:
    """The excerpt with its quotation marks folded to one class, found in the text folded the
    same way (``folded_text``, when the caller already holds it, is ``_fold_quote_marks(norm_text)``)."""
    if "'" not in norm_ex and '"' not in norm_ex:
        return None
    if folded_text is None:
        folded_text = _fold_quote_marks(norm_text)
    for cand in _folded_candidates(norm_ex):
        pos = folded_text.find(cand)
        if pos >= 0:
            start, end = _span(idx, pos, len(cand))
            return QuotationMatch(start, end, text[start:end], "normalized_match", note=note)
    return None


def _elision_fragments(norm_ex: str) -> list[str]:
    return [f.strip() for f in norm_ex.split("...") if f.strip()] if "..." in norm_ex else []


def _find_elided(fragments: list[str], norm_text: str, idx: Sequence[int], text: str, *, window: Optional[int] = ELISION_WINDOW_CHARS) -> Optional[QuotationMatch]:
    """Fragments in order within ``window`` characters beyond their own length; ``window``
    None means any distance (used to tell a long elision from an invented quotation)."""
    cursor = 0
    first_start: Optional[int] = None
    end = 0
    for frag in fragments:
        pos = norm_text.find(frag, cursor)
        if pos < 0:
            return None
        if first_start is None:
            first_start = idx[pos]
        end = idx[pos + len(frag) - 1] + 1
        cursor = pos + len(frag)
    if first_start is None:
        return None
    if window is not None and end - first_start > window + sum(len(f) for f in fragments):
        return None  # fragments this far apart are a long elision, not an elided quotation
    return QuotationMatch(first_start, end, text[first_start:end], "normalized_match", elided=True)


# ---------------------------------------------------------------- cached forms and memoised locating


class BoundedLRU:
    """A thread-safe least-recently-used map bounded by its number of entries and, when
    ``max_weight`` is set, by the total weight of its entries (the characters of the texts
    behind them). The least recently used entries are dropped first; the newest entry is
    always kept, whatever its weight."""

    def __init__(self, max_entries: int, max_weight: Optional[int] = None) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self.max_weight = max_weight
        self._data: "OrderedDict[Hashable, tuple[Any, int]]" = OrderedDict()
        self._weight = 0
        self._lock = threading.Lock()

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return default
            self._data.move_to_end(key)
            return item[0]

    def put(self, key: Hashable, value: Any, weight: int = 1) -> None:
        with self._lock:
            old = self._data.pop(key, None)
            if old is not None:
                self._weight -= old[1]
            self._data[key] = (value, weight)
            self._weight += weight
            while len(self._data) > self.max_entries or (self.max_weight is not None and self._weight > self.max_weight and len(self._data) > 1):
                _key, (_value, w) = self._data.popitem(last=False)
                self._weight -= w

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._weight = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    @property
    def weight(self) -> int:
        with self._lock:
            return self._weight


#: Supplied texts whose forms are kept (entries) and the characters of text behind them (weight).
TEXT_FORMS_MAX_ENTRIES = 64
TEXT_FORMS_MAX_CHARS = 2_000_000
#: Excerpt-in-document answers kept (entries), and the characters of excerpts and matched spans they hold (weight):
#: a long elision's match can hold a large slice of the text, so the memo is bounded by size as well as by count.
LOCATE_MEMO_MAX_ENTRIES = 16_384
LOCATE_MEMO_MAX_CHARS = 8_000_000

_SHA_BY_TEXT = BoundedLRU(TEXT_FORMS_MAX_ENTRIES, TEXT_FORMS_MAX_CHARS)  # the text itself -> its sha256 (str hashes are cached, so this is O(1) per call)
_TEXT_FORMS = BoundedLRU(TEXT_FORMS_MAX_ENTRIES, TEXT_FORMS_MAX_CHARS)   # (document_id, sha256) -> TextForms
_LOCATE_MEMO = BoundedLRU(LOCATE_MEMO_MAX_ENTRIES, LOCATE_MEMO_MAX_CHARS)  # (function, excerpt, sha256) -> (answer,)


def text_sha256(text: str) -> str:
    """The sha256 of ``text`` (UTF-8), memoised per text so a large document is hashed once."""
    digest = _SHA_BY_TEXT.get(text)
    if digest is None:
        digest = hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()  # never raises on a lone surrogate
        _SHA_BY_TEXT.put(text, digest, weight=len(text) + 1)
    return digest


def _offsets(idx: Sequence[int]) -> Sequence[int]:
    return array("i", idx)  # 4 bytes per offset (a supplied text is at most 400 000 characters) instead of a list of int objects


class TextForms:
    """The normalised forms of one supplied text and their offset maps into the ORIGINAL
    text, each built once, on first use. Obtained through :func:`text_forms`, which keeps
    one instance per ``(document_id, sha256 of the text)`` in a bounded LRU cache. Building a
    form twice in two threads is harmless (the same value is assigned)."""

    __slots__ = ("text", "_norm", "_quotes_folded", "_slash", "_slash_quotes_folded", "_no_marks", "_no_marks_casefold", "_has_newline", "_has_slash",
                 "_is_ascii", "_diacritics", "_edge", "_edge_slash", "_has_edge_marks")

    def __init__(self, text: str) -> None:
        self.text = text
        self._norm: Optional[tuple[str, Sequence[int]]] = None
        self._quotes_folded: Optional[str] = None
        self._slash: Optional[tuple[str, Sequence[int]]] = None
        self._slash_quotes_folded: Optional[str] = None
        self._no_marks: Optional[tuple[str, Sequence[int]]] = None
        self._no_marks_casefold: Optional[str] = None
        self._has_newline: Optional[bool] = None
        self._has_slash: Optional[bool] = None
        self._is_ascii: Optional[bool] = None
        self._diacritics: Optional[tuple[str, Sequence[int]]] = None
        self._edge: Optional[tuple[str, Sequence[int]]] = None
        self._edge_slash: Optional[tuple[str, Sequence[int]]] = None
        self._has_edge_marks: Optional[bool] = None

    @property
    def is_ascii(self) -> bool:
        if self._is_ascii is None:
            self._is_ascii = self.text.isascii()
        return self._is_ascii

    @property
    def has_newline(self) -> bool:
        if self._has_newline is None:
            self._has_newline = "\n" in self.text
        return self._has_newline

    @property
    def has_slash(self) -> bool:
        if self._has_slash is None:
            self._has_slash = "/" in self.text
        return self._has_slash

    def norm(self) -> tuple[str, Sequence[int]]:
        """Typographic normalisation (tier 2) and its offset map."""
        if self._norm is None:
            chars, idx = _normalize_indexed(self.text)
            self._norm = (chars, _offsets(idx))
        return self._norm

    def quotes_folded(self) -> str:
        """The normalised text with every quotation mark folded to one class (same offsets as :meth:`norm`)."""
        if self._quotes_folded is None:
            self._quotes_folded = _fold_quote_marks(self.norm()[0])
        return self._quotes_folded

    def slash(self) -> tuple[str, Sequence[int]]:
        """Line breaks rendered ``" / "`` (a blank line ``" // "``), slash runs folded, and the offset map."""
        if self._slash is None:
            chars, idx = _fold_slash_runs(*_normalize_indexed(self.text, newline_as_slash=True))
            self._slash = (chars, _offsets(idx))
        return self._slash

    def slash_quotes_folded(self) -> str:
        if self._slash_quotes_folded is None:
            self._slash_quotes_folded = _fold_quote_marks(self.slash()[0])
        return self._slash_quotes_folded

    def no_marks(self) -> tuple[str, Sequence[int]]:
        """The normalised text with verse line-break marks dropped, and the offset map."""
        if self._no_marks is None:
            chars, idx = _drop_linebreak_marks(*self.norm())
            self._no_marks = (chars, _offsets(idx))
        return self._no_marks

    def no_marks_casefold(self) -> str:
        if self._no_marks_casefold is None:
            self._no_marks_casefold = self.no_marks()[0].casefold()
        return self._no_marks_casefold

    @property
    def has_edge_marks(self) -> bool:
        """The text opens or closes a line with its own double quotation mark (verse dialogue: every stanza of a
        dramatic monologue opening with a speech mark)."""
        if self._has_edge_marks is None:
            self._has_edge_marks = self.has_newline and _EDGE_MARK_RE.search(self.text) is not None
        return self._has_edge_marks

    def edge(self) -> tuple[str, Sequence[int]]:
        """The normalised text with the double quotation marks that open or close a line removed, and the offset map."""
        if self._edge is None:
            filtered, fmap = _drop_edge_marks(self.text)
            chars, idx = _normalize_indexed(filtered)
            self._edge = (chars, _offsets([fmap[i] for i in idx]))
        return self._edge

    def edge_slash(self) -> tuple[str, Sequence[int]]:
        """As :meth:`edge`, with line breaks rendered ``" / "`` (a blank line ``" // "``) and slash runs folded."""
        if self._edge_slash is None:
            filtered, fmap = _drop_edge_marks(self.text)
            chars, idx = _fold_slash_runs(*_normalize_indexed(filtered, newline_as_slash=True))
            self._edge_slash = (chars, _offsets([fmap[i] for i in idx]))
        return self._edge_slash

    def diacritics(self) -> tuple[str, Sequence[int]]:
        """The normalised text with its diacritics folded (NFKD, combining marks dropped), and the offset map."""
        if self._diacritics is None:
            chars, idx = _fold_diacritics_indexed(*self.norm())
            self._diacritics = (chars, _offsets(idx))
        return self._diacritics


#: A double quotation mark (any typographic form) at the start of a line (after indentation) or at its end.
_DOUBLE_MARKS = '"“”„‟″«»'
_EDGE_MARK_RE = re.compile(r"(?m)^[ \t]*[" + _DOUBLE_MARKS + r"]|[" + _DOUBLE_MARKS + r"][ \t]*$")
NOTE_EDGE_MARKS = "omits the text's own speech mark at a line or stanza start or end"


def _drop_edge_marks(text: str) -> tuple[str, list[int]]:
    """``text`` without the double quotation marks that open or close a line, and per kept character its offset in
    ``text``: the forms in which a quotation that runs across a line or stanza break and leaves out the text's own
    speech mark at the break is located."""
    drop: set[int] = set()
    line_start = 0
    for line in text.split("\n"):
        stripped = line.strip(" \t\r")
        if stripped:
            first = line_start + (len(line) - len(line.lstrip(" \t\r")))
            last = line_start + len(line.rstrip(" \t\r")) - 1
            if text[first] in _DOUBLE_MARKS:
                drop.add(first)
            if last != first and text[last] in _DOUBLE_MARKS:
                drop.add(last)
        line_start += len(line) + 1
    keep = [i for i in range(len(text)) if i not in drop]
    return "".join(text[i] for i in keep), keep


def _excerpt_without_edge_marks(norm_ex: str) -> str:
    """A normalised excerpt with the double marks beside its own line-break marks removed ("nipperkin!" / "But" ->
    "nipperkin! / But"), so a quoter who kept one of the text's speech marks at a break and dropped the other compares
    equal to the text without its edge marks."""
    out = re.sub(r'"(?=\s*/)', "", norm_ex)
    out = re.sub(r'(?<=/)(\s*)"', r"\1", out)
    return " ".join(out.split())


def _text_key(text: str, document_id: Optional[str]) -> tuple[str, str]:
    return (document_id or "", text_sha256(text))


def text_forms(text: str, document_id: Optional[str] = None) -> TextForms:
    """The cached :class:`TextForms` of ``text`` (keyed by ``(document_id, sha256)``)."""
    key = _text_key(text, document_id)
    forms = _TEXT_FORMS.get(key)
    if forms is None:
        forms = TextForms(text)
        _TEXT_FORMS.put(key, forms, weight=len(text) + 1)
    return forms


def normalized_text(text: str, document_id: Optional[str] = None) -> str:
    """:func:`normalize_quote` of a supplied text, from the cache."""
    return text_forms(text, document_id).norm()[0]


def _memoised(kind: str, excerpt: str, text: str, document_id: Optional[str], compute: Callable[[str, TextForms], Any]) -> Any:
    """``compute(excerpt, forms)`` once per ``(kind, excerpt, sha256 of text)``: the answer is a
    function of the excerpt and the words of the text only, so a caller that names the document
    and one that does not share it, and the same excerpt is never located twice in one text."""
    key = (kind, excerpt, text_sha256(text))
    hit = _LOCATE_MEMO.get(key)
    if hit is not None:
        return hit[0]
    answer = compute(excerpt, text_forms(text, document_id))
    match = answer[0] if isinstance(answer, tuple) else answer
    _LOCATE_MEMO.put(key, (answer,), weight=len(excerpt) + 1 + (len(match.matched) if isinstance(match, QuotationMatch) else 0))
    return answer


def clear_grounding_caches() -> None:
    """Empty every cache of this module (tests; a process that wants its memory back)."""
    _SHA_BY_TEXT.clear()
    _TEXT_FORMS.clear()
    _LOCATE_MEMO.clear()


def locate_quotation(excerpt: str, text: str, *, document_id: Optional[str] = None) -> Optional[QuotationMatch]:
    """Find ``excerpt`` in ``text`` (verbatim, then normalized, then elided).

    The normalized tier also folds the quotation marks inside the excerpt to one class
    (nested marks) and reads ``" / "`` in the excerpt as a line break of the document;
    a match that relied on either carries a ``note``. ``document_id`` names the supplied
    text for the cache key; the answer never depends on it."""
    return _memoised("exact", excerpt, text, document_id, _locate_quotation)


def _locate_quotation(excerpt: str, forms: TextForms) -> Optional[QuotationMatch]:
    text = forms.text
    ex = _strip_outer_quotes(excerpt)
    if not ex:
        return None
    pos = text.find(ex)
    if pos >= 0:
        return QuotationMatch(pos, pos + len(ex), ex, "verbatim_match")
    ex = unbracket_elisions(ex)  # "[...]" / "(...)" read as the ellipsis it is, in every tier below
    norm_text, idx = forms.norm()
    norm_ex = normalize_quote(ex)
    if not norm_ex:
        return None
    pos = norm_text.find(norm_ex)
    if pos >= 0:
        start, end = _span(idx, pos, len(norm_ex))
        return QuotationMatch(start, end, text[start:end], "normalized_match")
    if "'" in norm_ex or '"' in norm_ex:
        folded = _find_folded(norm_ex, norm_text, idx, text, NOTE_QUOTES_FOLDED, forms.quotes_folded())
        if folded is not None:
            return folded
    slash_text: Optional[str] = None
    slash_idx: Sequence[int] = ()
    slash_ex = norm_ex
    if "/" in norm_ex and forms.has_newline:
        # Line breaks of the document become " / " and a blank line " // "; slash runs are folded on both sides so a
        # stanza break written with one or two marks compares equal.
        slash_text, slash_idx = forms.slash()
        slash_ex = _fold_slash_runs(norm_ex)[0]
        pos = slash_text.find(slash_ex)
        if pos >= 0:
            start, end = _span(slash_idx, pos, len(slash_ex))
            return QuotationMatch(start, end, text[start:end], "normalized_match", note=NOTE_LINEBREAK_SLASH)
        if "'" in slash_ex or '"' in slash_ex:
            folded = _find_folded(slash_ex, slash_text, slash_idx, text, NOTE_LINEBREAK_SLASH + "; " + NOTE_QUOTES_FOLDED, forms.slash_quotes_folded())
            if folded is not None:
                return folded
    fragments = _elision_fragments(norm_ex)
    if fragments:
        found = _find_elided(fragments, norm_text, idx, text)
        if found is None and slash_text is not None:
            found = _find_elided(_elision_fragments(slash_ex), slash_text, slash_idx, text)
            if found is not None:
                found = QuotationMatch(found.start, found.end, found.matched, found.method, elided=True, note=NOTE_LINEBREAK_SLASH)
        if found is not None:
            return found
    return _composition_match(norm_ex, forms)


def _diacritic_occurrences(norm_ex: str, forms: TextForms):
    """Every ``(start, end)`` in the original text where ``norm_ex`` occurs once diacritics are
    folded on both sides (``end`` extended over trailing combining marks), in order."""
    folded_text, idx = forms.diacritics()
    folded_ex = fold_diacritics(norm_ex)
    if not folded_ex.strip():
        return
    pos = folded_text.find(folded_ex)
    while pos >= 0:
        start, end = _span(idx, pos, len(folded_ex))
        yield start, _extend_over_marks(forms.text, end)
        pos = folded_text.find(folded_ex, pos + 1)


def _composition_match(norm_ex: str, forms: TextForms) -> Optional[QuotationMatch]:
    """The excerpt where it differs from the text only in how accented letters are encoded
    (precomposed against a letter plus a combining mark): the same letters, a normalized match."""
    if norm_ex.isascii() and forms.is_ascii:
        return None
    composed = unicodedata.normalize("NFC", norm_ex)
    for start, end in _diacritic_occurrences(norm_ex, forms):
        if unicodedata.normalize("NFC", normalize_quote(forms.text[start:end])) == composed:
            return QuotationMatch(start, end, forms.text[start:end], "normalized_match", note=NOTE_COMPOSITION)
    return None


def _diacritics_difference(norm_ex: str, norm_matched: str) -> str:
    """'differs in diacritics', naming the words that differ when the two spans pair word for word."""
    quoted, held = norm_ex.split(), norm_matched.split()
    pairs = [(a, b) for a, b in zip(quoted, held) if a != b] if len(quoted) == len(held) else []
    if not pairs:
        return "differs in diacritics"
    shown = "; ".join(f"'{a}' where the document has '{b}'" for a, b in pairs[:3])
    return f"differs in diacritics ({shown})"


def _diacritics_match(ex: str, forms: TextForms) -> Optional[tuple[QuotationMatch, str]]:
    """The excerpt located once diacritics are folded on both sides (contiguously, or as an
    elided quotation within the elision window): ``(match, difference)``, or None."""
    norm_ex = normalize_quote(ex)
    if not norm_ex or (norm_ex.isascii() and forms.is_ascii):
        return None
    text = forms.text
    for start, end in _diacritic_occurrences(norm_ex, forms):
        return QuotationMatch(start, end, text[start:end], "normalized_match"), _diacritics_difference(norm_ex, normalize_quote(text[start:end]))
    fragments = _elision_fragments(fold_diacritics(norm_ex))
    if fragments:
        folded_text, idx = forms.diacritics()
        found = _find_elided(fragments, folded_text, idx, text)
        if found is not None:
            end = _extend_over_marks(text, found.end)
            return (QuotationMatch(found.start, end, text[found.start:end], "normalized_match", elided=True),
                    "differs in diacritics (an elided quotation whose fragments occur in order once accents are set aside)")
    return None


def _swap_first_alpha_case(s: str) -> str:
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.swapcase() + s[i + 1:]
    return s


def _drop_linebreak_marks(chars: str, idx: Sequence[int]) -> tuple[str, list[int]]:
    """Remove verse line-break marks (``/``) from normalized text, collapsing the spaces
    around them, while keeping the offset map into the original text."""
    out: list[str] = []
    out_idx: list[int] = []
    for ch, pos in zip(chars, idx):
        if ch == "/":
            continue
        if ch == " " and out and out[-1] == " ":
            continue
        out.append(ch)
        out_idx.append(pos)
    while out and out[-1] == " ":
        out.pop()
        out_idx.pop()
    return "".join(out), out_idx


def locate_quotation_inexact(excerpt: str, text: str, *, document_id: Optional[str] = None) -> Optional[tuple[QuotationMatch, str]]:
    """Find ``excerpt`` after a conventional quotation-form adjustment; ``(match, difference)``.

    Tried only after :func:`locate_quotation` failed. Three adjustments are recognised:
    the first alphabetic character's case (``"for the immense majority"`` quoted from a
    sentence opening ``For``), verse line-break marks omitted or added (``"mock the
    meat"`` for ``mock / The meat``, where the case of the word after the mark may also
    differ), and diacritics (``"Bayardo San Román"`` for ``Bayardo San Roman``: both sides
    folded with NFKD and their combining marks dropped; the difference reads ``differs in
    diacritics`` and names the words). Anything else (a changed word, a reordering) is not
    found; a long elision is a separate question answered by :func:`locate_long_elision`.
    """
    return _memoised("inexact", excerpt, text, document_id, _locate_quotation_inexact)


def _locate_quotation_inexact(excerpt: str, forms: TextForms) -> Optional[tuple[QuotationMatch, str]]:
    text = forms.text
    ex = unbracket_elisions(_strip_outer_quotes(excerpt))
    if not ex:
        return None
    swapped = _swap_first_alpha_case(ex)
    if swapped != ex:
        pos = text.find(swapped)
        if pos >= 0:
            return QuotationMatch(pos, pos + len(swapped), swapped, "verbatim_match"), "differs only in the initial capital"
        norm_text, idx = forms.norm()
        norm_sw = normalize_quote(swapped)
        pos = norm_text.find(norm_sw)
        if pos >= 0 and norm_sw:
            start, end = _span(idx, pos, len(norm_sw))
            return QuotationMatch(start, end, text[start:end], "normalized_match"), "differs only in the initial capital"
    if "/" in ex or forms.has_slash:
        stripped_text, idx2 = forms.no_marks()
        stripped_ex, _ = _drop_linebreak_marks(*_normalize_indexed(ex))
        if stripped_ex:
            pos = stripped_text.find(stripped_ex)
            how = "omits or adds a verse line-break mark"
            if pos < 0:
                pos = forms.no_marks_casefold().find(stripped_ex.casefold())
                how = "omits or adds a verse line-break mark and differs in letter case at a line start"
            if pos >= 0:
                start, end = _span(idx2, pos, len(stripped_ex))
                return QuotationMatch(start, end, text[start:end], "normalized_match"), how
    if forms.has_edge_marks:
        found = _edge_marks_match(ex, forms)
        if found is not None:
            return found
    return _diacritics_match(ex, forms)


def _edge_marks_match(ex: str, forms: TextForms) -> Optional[tuple[QuotationMatch, str]]:
    """The excerpt located once the text's own double quotation marks at line and stanza edges are set aside: a
    quotation that runs across a stanza break of verse dialogue (every stanza of 'The Man He Killed' opens with a speech
    mark) and leaves that mark out, with ``" / "``, ``" // "`` or no break mark. ``(match, difference)``, or None."""
    text = forms.text
    norm_ex = normalize_quote(ex)
    if not norm_ex:
        return None
    if "/" in norm_ex:
        slash_text, slash_idx = forms.edge_slash()
        for cand in dict.fromkeys((_fold_slash_runs(norm_ex)[0], _fold_slash_runs(_excerpt_without_edge_marks(norm_ex))[0])):
            pos = slash_text.find(cand)
            if pos >= 0 and cand:
                start, end = _span(slash_idx, pos, len(cand))
                return QuotationMatch(start, end, text[start:end], "normalized_match"), f"{NOTE_EDGE_MARKS} (its line breaks written ' / ')"
        stripped_ex = _drop_linebreak_marks(*_normalize_indexed(_excerpt_without_edge_marks(norm_ex)))[0]
    else:
        stripped_ex = norm_ex
    edge_text, edge_idx = forms.edge()
    pos = edge_text.find(stripped_ex) if stripped_ex else -1
    if pos >= 0:
        start, end = _span(edge_idx, pos, len(stripped_ex))
        how = NOTE_EDGE_MARKS + (" and its line-break marks" if "/" in norm_ex else " (and marks no line break)")
        return QuotationMatch(start, end, text[start:end], "normalized_match"), how
    return None


def locate_long_elision(excerpt: str, text: str, *, document_id: Optional[str] = None) -> Optional[tuple[QuotationMatch, str]]:
    """An elided excerpt whose fragments all occur in order but span more than
    :data:`ELISION_WINDOW_CHARS` beyond the quoted words: ``(match, difference)`` naming the
    omitted span, or None. The words were found, so this is a form difference (a long
    elision), not an invented quotation; it never verifies a grounding."""
    return _memoised("long_elision", excerpt, text, document_id, _locate_long_elision)


def _locate_long_elision(excerpt: str, forms: TextForms) -> Optional[tuple[QuotationMatch, str]]:
    ex = unbracket_elisions(_strip_outer_quotes(excerpt))
    fragments = _elision_fragments(normalize_quote(ex)) if ex else []
    if len(fragments) < 2:
        return None
    norm_text, idx = forms.norm()
    far = _find_elided(fragments, norm_text, idx, forms.text, window=None)
    if far is None:
        return None
    omitted = far.end - far.start - sum(len(f) for f in fragments)
    return far, (f"elides about {omitted} characters of the document between its fragments, more than the "
                 f"{ELISION_WINDOW_CHARS}-character window of an elided quotation (a long elision, not an invented quotation)")


def find_quotation(excerpt: str, text: str, *, document_id: Optional[str] = None) -> Optional[tuple[int, int, str]]:
    """Return ``(start, end, matched_text)`` in ``text`` for ``excerpt``, or ``None``."""
    match = locate_quotation(excerpt, text, document_id=document_id)
    if match is None:
        return None
    return match.start, match.end, match.matched


def is_peer_document(doc: SuppliedText) -> bool:
    """A relayed specialist's report supplied as a document ('peer:<task>', or an author '<subject>-specialist'): the
    same rule as ``adapters.sources.is_peer_text``. Another agent's report is evidence of what that agent said, never a
    source: an excerpt located in it confers no authority on a premise (agent self-reports are advisory)."""
    author = (doc.author or "").strip().lower()
    return doc.document_id.startswith("peer:") or author.endswith("-specialist") or author.endswith(" specialist")


def _check_quotation_ref(target_id: str, ref: SourceRef, docs: dict[str, SuppliedText], kind: str = "quotation", ref_index: Optional[int] = None) -> GroundingCheck:
    doc = docs.get(ref.document_id)
    if doc is None:
        return GroundingCheck(
            target_id=target_id, kind=kind, method="verbatim_match", verified=False,  # type: ignore[arg-type]
            document_id=ref.document_id, detail="document_id is not among the supplied texts", ref_index=ref_index,
        )
    if not ref.excerpt or not ref.excerpt.strip():
        return GroundingCheck(
            target_id=target_id, kind=kind, method="verbatim_match", verified=False,  # type: ignore[arg-type]
            document_id=ref.document_id, detail="quotation grounding carries no excerpt", ref_index=ref_index,
        )
    match = locate_quotation(ref.excerpt, doc.text, document_id=doc.document_id)
    if match is None:
        inexact = locate_quotation_inexact(ref.excerpt, doc.text, document_id=doc.document_id) or locate_long_elision(ref.excerpt, doc.text, document_id=doc.document_id)
        if inexact is not None:
            near, difference = inexact
            return GroundingCheck(
                target_id=target_id, kind=kind, method="normalized_match", verified=False,  # type: ignore[arg-type]
                document_id=ref.document_id, ref_index=ref_index,
                detail=f"quotation {FORM_DIFFERS} from the document: the words occur at characters {near.start}-{near.end} but the quotation {difference}",
            )
        return GroundingCheck(
            target_id=target_id, kind=kind, method="normalized_match", verified=False,  # type: ignore[arg-type]
            document_id=ref.document_id, detail="excerpt not found in the document (verbatim or normalized)", ref_index=ref_index,
        )
    how = {"verbatim_match": "verbatim", "normalized_match": "after typographic normalization"}[match.method]
    if match.elided:
        how = f"as an elided quotation, fragments in order within {match.end - match.start} characters, after typographic normalization"
    if match.note:
        how += f" ({match.note})"
    if is_peer_document(doc):
        # peer_report: the words are another agent's, so the reference is located but verifies nothing (an unverified or
        # ungrounded dependency the engine lists, which blocks release until a task record or a primary text supports it)
        return GroundingCheck(
            target_id=target_id, kind=kind, method=match.method, verified=None,  # type: ignore[arg-type]
            document_id=ref.document_id, ref_index=ref_index,
            detail=(f"peer_report: found {how} at characters {match.start}-{match.end} of {ref.document_id}, a relayed peer specialist's report; "
                    "another agent's report is no source, so the reference is located but confers no authority"),
        )
    return GroundingCheck(
        target_id=target_id, kind=kind, method=match.method, verified=True,  # type: ignore[arg-type]
        document_id=ref.document_id, detail=f"found {how} at characters {match.start}-{match.end}", ref_index=ref_index,
    )


def _check_document_ref(target_id: str, ref: SourceRef, docs: dict[str, SuppliedText], kind: str, ref_index: int) -> GroundingCheck:
    """A reference without an excerpt: its document must be supplied, and a locator needs a locator scheme. A document
    that exists locates nothing, so the reference is unchecked (``verified=None``), never a verification."""
    doc = docs.get(ref.document_id)
    if doc is None:
        return GroundingCheck(target_id=target_id, kind=kind, method="locator_exists", verified=False, document_id=ref.document_id,  # type: ignore[arg-type]
                              detail="document_id is not among the supplied texts: the reference names a document that was never supplied", ref_index=ref_index)
    if ref.locator and doc.locator_scheme == "none":
        return GroundingCheck(target_id=target_id, kind=kind, method="locator_exists", verified=False, document_id=ref.document_id,  # type: ignore[arg-type]
                              detail="a locator was given but the supplied text has no locator scheme", ref_index=ref_index)
    return GroundingCheck(target_id=target_id, kind=kind, method="locator_exists", verified=None, document_id=ref.document_id,  # type: ignore[arg-type]
                          detail="document exists; the reference carries no excerpt, so it locates nothing" + ("; locator form not checked" if ref.locator else ""),
                          ref_index=ref_index)


def support_of(target_id: str, checks: Sequence[GroundingCheck]) -> Optional[GroundingSupport]:
    """The support a target's per-reference checks give together (see :class:`~.contracts.GroundingSupport`); None when
    the target has no per-reference check."""
    per_ref = [c for c in checks if c.target_id == target_id and c.ref_index is not None]
    if not per_ref:
        return None
    located = sum(1 for c in per_ref if c.verified is True)
    refuted = sum(1 for c in per_ref if c.verified is False)
    unchecked = len(per_ref) - located - refuted
    if located == len(per_ref):
        level = "complete"
    elif located:
        level = "partial"
    elif refuted:
        level = "failed"
    else:
        level = "uncheckable"
    return GroundingSupport(target_id=target_id, references=len(per_ref), located=located, refuted=refuted, unchecked=unchecked, support=level)  # type: ignore[arg-type]


def grounding_support(checks: Sequence[GroundingCheck]) -> list[GroundingSupport]:
    """:func:`support_of` for every target that has per-reference checks, in order of first appearance."""
    seen = list(dict.fromkeys(c.target_id for c in checks if c.ref_index is not None))
    return [s for s in (support_of(t, checks) for t in seen) if s is not None]


def _verified_for(support: GroundingSupport) -> Optional[bool]:
    """Only complete support verifies; a refuted reference refutes the grounding; anything else stays unchecked."""
    if support.support == "complete":
        return True
    return False if support.refuted else None


def check_grounding(target_id: str, grounding: Grounding, docs: dict[str, SuppliedText]) -> tuple[Grounding, list[GroundingCheck]]:
    """Check one grounding; return the grounding with ``verified`` set and the checks.

    Every source_ref is checked and keeps its own check (``ref_index``): an excerpt is located in its document, a
    reference without an excerpt has its document and locator checked. A quotation needs an excerpt in every reference.
    ``verified`` is True only when every reference was located (complete support), False when any reference was
    refuted (an excerpt not found, a document never supplied, a locator the text cannot have), and None otherwise; a
    grounding with no reference is ``not_checkable``. Any ``verified`` value the model wrote is discarded.
    """
    if grounding.kind == "quotation":
        if not grounding.source_refs:
            check = GroundingCheck(
                target_id=target_id, kind="quotation", method="verbatim_match", verified=False,
                detail="quotation grounding has no source_refs",
            )
            return grounding.model_copy(update={"verified": False}), [check]
        checks = [_check_quotation_ref(target_id, ref, docs, ref_index=i) for i, ref in enumerate(grounding.source_refs)]
        # every reference located verifies; any refuted refutes; a reference located only in a peer report leaves it unchecked
        verified: Optional[bool] = True if all(c.verified is True for c in checks) else (False if any(c.verified is False for c in checks) else None)
        return grounding.model_copy(update={"verified": verified}), checks
    if grounding.source_refs:
        checks = [_check_quotation_ref(target_id, ref, docs, kind=grounding.kind, ref_index=i) if ref.excerpt and ref.excerpt.strip()
                  else _check_document_ref(target_id, ref, docs, grounding.kind, i) for i, ref in enumerate(grounding.source_refs)]
        support = support_of(target_id, checks)
        assert support is not None
        return grounding.model_copy(update={"verified": _verified_for(support)}), checks
    check = GroundingCheck(
        target_id=target_id, kind=grounding.kind, method="not_checkable", verified=None,
        document_id=None, detail=f"grounding kind {grounding.kind} is not deterministically checkable",
    )
    # Any 'verified' value the model wrote is discarded: only checks set it.
    return grounding.model_copy(update={"verified": None}), [check]


def _check_symbol(symbol: Symbol, docs: dict[str, SuppliedText], checks: list[GroundingCheck]) -> Symbol:
    if symbol.grounding is None:
        return symbol
    grounding, found = check_grounding(symbol.name, symbol.grounding, docs)
    checks.extend(found)
    return symbol.model_copy(update={"grounding": grounding})


#: Kinds that claim the task's authority (a figure, setting or rubric rule given with the task). The translator
#: proposes the kind; code validates it against the supplied texts and the task record.
TASK_AUTHORITY_KINDS = frozenset({"arithmetic_fact", "task_setting", "rubric_rule"})
#: The document ids a reference may use to cite the task record itself (besides the record's own task_id).
TASK_DOCUMENT_IDS = frozenset({"task", "the request", "request"})


@dataclass(frozen=True)
class _Literal:
    """A numeric literal of an expression with the reading its compared symbol declares. ``required`` is the comparison an
    assignment conjunct states about its symbol (``eq``, ``lt``, ``le``, ``gt``, ``ge``, read from the symbol's side), which
    the stated figure must establish (:func:`.assertion.stated_as`); None for a literal of a relation."""
    written: str
    value: Fraction
    declared: DeclaredReading
    symbol: Optional[str]
    required: Optional[str] = None
    #: the years the compared symbol's name and meaning name ("p2010", "residents in 2010"): the time the figure is about
    years: frozenset[str] = frozenset()


#: A year written in digits (1500-2099), never part of a longer number.
_YEAR_TOKEN_RE = re.compile(r"(?<![\d.,])(1[5-9]\d{2}|20\d{2})(?![.,]?\d)")


def _years_named(*texts: Optional[str]) -> frozenset[str]:
    """The years ``texts`` name in digits (a symbol's name and meaning: "p2010", "Lowtown residents in 2010")."""
    return frozenset(m.group(1) for t in texts if t for m in _YEAR_TOKEN_RE.finditer(t))


def _about_another_time(lit: "_Literal", text: str, start: int, end: int) -> Optional[str]:
    """Why the figure at ``start``-``end`` of ``text`` is not about the time the literal's symbol names, or None: its
    asserting clause (:func:`.assertion.asserting_clause`, read where it stands in its document) names years, none of
    them a year the symbol's name or meaning names ("In 2020 Lowtown had 252 residents" for ``p2010``, "Lowtown residents
    in 2010"). A figure of another year is another quantity's figure, so it states nothing about this symbol (rule
    same-quantity, conflicting qualifier). A clause that names no year, or a symbol that names none, is not read here."""
    if not lit.years:
        return None
    from .assertion import asserting_clause
    a, b = asserting_clause(text, start, end)
    years = {m.group(1) for m in _YEAR_TOKEN_RE.finditer(text, a, b) if not (m.start() < end and start < m.end())}
    if years and not (years & lit.years):
        return f"about {', '.join(sorted(years))}, while {lit.symbol} is about {', '.join(sorted(lit.years))} (another year's figure)"
    return None


def _literals(expr, symbols: dict[str, Symbol]) -> list[_Literal]:
    """The non-trivial numeric literals of ``expr`` (integers, decimals and fractions alike: one value, one figure), each
    with the reading the symbol it is directly compared with declares (``tax_rate = 0.2`` with ``tax_rate`` declared
    dimensionless). Zero, one and the powers of ten a percentage or conversion brings in are no figures of a relation. For an
    assignment (:func:`.relations.assignment_parts`) every literal is the figure itself (``k = 10`` for "10 km"), and
    carries the comparison its conjunct states about its symbol."""
    parts = assignment_parts(expr)
    if parts is not None:
        out_a: list[_Literal] = []
        for name, required, node in parts:
            lit = node.arg if getattr(node, "op", None) == "neg" else node  # type: ignore[attr-defined]
            try:
                value = Fraction(lit.value)  # type: ignore[attr-defined]
            except (ValueError, ZeroDivisionError):
                continue
            if getattr(node, "op", None) == "neg":
                value = -value
            # a literal an assignment compares directly with its symbol is the figure itself, trivial or not ("10 km": k = 10)
            sym = symbols.get(name)
            written = lit.value if getattr(node, "op", None) != "neg" else f"-{lit.value}"  # type: ignore[attr-defined]
            out_a.append(_Literal(written, value, declared_reading(sym.meaning if sym is not None else None), name, required,
                                  _years_named(name, sym.meaning if sym is not None else None)))
        return out_a
    out: list[_Literal] = []
    stack: list[tuple[object, Optional[str]]] = [(expr, None)]
    while stack:
        node, compared = stack.pop()
        op = getattr(node, "op", None)
        if op in ("int", "real"):
            try:
                value = Fraction(node.value)  # type: ignore[attr-defined]
            except (ValueError, ZeroDivisionError):
                continue
            if abs(value) in TRIVIAL_VALUES:
                continue
            sym = symbols.get(compared) if compared else None
            out.append(_Literal(node.value, value, declared_reading(sym.meaning if sym is not None else None), compared))  # type: ignore[attr-defined]
            continue
        if op in ("eq", "ne", "lt", "le", "gt", "ge"):
            left, right = node.left, node.right  # type: ignore[attr-defined]
            lname = left.name if getattr(left, "op", None) == "var" else None
            rname = right.name if getattr(right, "op", None) == "var" else None
            stack.append((left, rname))
            stack.append((right, lname))
            continue
        for key in ("arg", "left", "right", "cond", "then", "otherwise"):
            child = getattr(node, key, None)
            if child is not None:
                stack.append((child, None))
        stack.extend((a, None) for a in (getattr(node, "args", None) or ()))
    return out


def _figures_check(target_id: str, kind: str, literals: list[_Literal], sources: list[SourceText], document_id: Optional[str], method: str,
                   what: str, within: Optional[dict[tuple[str, str], list[tuple[int, int, Optional[frozenset[Fraction]]]]]] = None
                   ) -> tuple[Optional[bool], Optional[GroundingCheck], list[_Literal]]:
    """Whether ``sources`` state every literal (typed, see :func:`.quantities.literal_matches`), each literal of an
    assignment so that the stated figure establishes its comparison (:func:`.assertion.stated_as`): ``(True, check naming
    the derivations, or None when every figure is stated as written, [])``, ``(False, check naming what is missing, the
    missing literals)``. With ``within`` only the figures inside one of a source's spans count (the located excerpts,
    read where they stand in their document; one document may hold several), and inside an elided excerpt's span only
    the figures the excerpt itself quotes (``allowed`` values: what an elision leaves out is not quoted)."""
    def inside(src: SourceText, f) -> bool:
        spans = within.get((src.kind, src.ident)) if within is not None else None
        return spans is None or any(a <= f.start and f.end <= b and (allowed is None or f.value in allowed) for a, b, allowed in spans)

    figures = [f for src in sources for f in figures_in(src) if inside(src, f)]
    texts = {(src.kind, src.ident): src.text for src in sources}
    missing: list[_Literal] = []
    conflicts: list[str] = []
    found: list[str] = []
    unmatched: list[tuple[_Literal, list[str]]] = []
    for lit in literals:
        matches, why = literal_matches(lit.value, figures, lit.declared)
        if matches and lit.required is not None:
            kept = []
            for m in matches:
                text = texts.get((m.figure.source_kind, m.figure.source_id))
                reason = stated_as(text, m.figure.start, m.figure.end, lit.required) if text is not None else "its text is not at hand"
                if reason is None and text is not None:
                    reason = _about_another_time(lit, text, m.figure.start, m.figure.end)
                if reason is None:
                    kept.append(m)
                else:
                    why = [*why, f"{m.figure.where()} is {reason}, so it does not state {lit.symbol} {_OP_WORDS.get(lit.required, lit.required)} {lit.written}"]
            matches = kept
        if matches:
            m = matches[0]
            if not m.derivation.startswith("as written") or method == "numeric_in_task":
                found.append(f"{lit.written} ({m.figure.where()}: {m.derivation})")
        else:
            unmatched.append((lit, why))
    tolerance = _tolerance_ends([lit for lit, _why in unmatched], figures, texts) if unmatched else {}
    for k, (lit, why) in enumerate(unmatched):
        if k in tolerance:
            found.append(f"{lit.written} ({tolerance[k]})")
        else:
            missing.append(lit)
            conflicts.extend(why[:2])
    if missing:
        detail = f"{what} does not state the premise's figures {list(dict.fromkeys(m.written for m in missing))[:8]}"
        if conflicts:
            detail += "; " + "; ".join(dict.fromkeys(conflicts))
        return False, GroundingCheck(target_id=target_id, kind=kind, method=method, verified=False, document_id=document_id, detail=detail[:2000]), missing  # type: ignore[arg-type]
    if found:
        return True, GroundingCheck(target_id=target_id, kind=kind, method=method, verified=True, document_id=document_id,  # type: ignore[arg-type]
                                    detail=(f"{what} states the premise's figures: " + "; ".join(found))[:2000]), []
    return True, None, []


#: How a comparison reads in a check's detail.
_OP_WORDS = {"eq": "=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}
_LOWER_BOUNDS = ("ge", "gt")
_UPPER_BOUNDS = ("le", "lt")


def _end_establishes(bounds: tuple[Fraction, Fraction, bool, bool], lit: _Literal) -> bool:
    """Whether the interval ``bounds`` that a rounded figure states establishes the assignment conjunct ``lit`` at one of
    its ends: ``symbol >= lower`` always and ``symbol > lower`` only when the lower end is excluded; ``symbol <= upper``
    always and ``symbol < upper`` only when the upper end is excluded. A bound at any other value is not what it states."""
    lo, hi, lo_incl, hi_incl = bounds
    if lit.required in _LOWER_BOUNDS:
        return lit.value == lo and (lit.required == "ge" or not lo_incl)
    if lit.required in _UPPER_BOUNDS:
        return lit.value == hi and (lit.required == "le" or not hi_incl)
    return False


def _tolerance_ends(literals: list[_Literal], figures: Sequence[Any], texts: dict[tuple[str, str], str]) -> dict[int, str]:
    """``{index of a literal: derivation}`` for the bounds of an assignment that are the ends of the interval a figure
    STATED AS ROUNDED states (:func:`.quantities.stated_intervals`: "x is 0.33 to 2 decimal places" states
    ``x >= 0.325 and x < 0.335``), read where the figure stands in its record. A symbol bounded on both sides takes both
    ends from ONE stated interval, never one end from each of two figures; a symbol with one bound takes the end of any.
    An exact or given figure states no interval, so an interval in its place stays unestablished (a weakening)."""
    by_symbol: dict[str, list[int]] = {}
    for k, lit in enumerate(literals):
        if lit.symbol is not None and lit.required in _LOWER_BOUNDS + _UPPER_BOUNDS:
            by_symbol.setdefault(lit.symbol, []).append(k)
    # what each symbol needs: both ends of one interval (a lower and an upper bound), or the end of any (one bound); a
    # symbol with more bounds than that takes none from a tolerance
    pending: dict[str, tuple[int, ...]] = {}
    for name, indices in by_symbol.items():
        lowers = [k for k in indices if literals[k].required in _LOWER_BOUNDS]
        uppers = [k for k in indices if literals[k].required in _UPPER_BOUNDS]
        if len(lowers) == 1 and len(uppers) == 1:
            pending[name] = (lowers[0], uppers[0])
        elif len(indices) == 1:
            pending[name] = (indices[0],)
    out: dict[int, str] = {}
    plain: dict[int, bool] = {}  # how a figure's own words state it, read once (only for a figure whose interval ends at a wanted bound)
    for declared in dict.fromkeys(literals[ks[0]].declared for ks in pending.values()):
        mine = {name: ks for name, ks in pending.items() if literals[ks[0]].declared == declared}
        wanted = {literals[k].value for ks in mine.values() for k in ks}
        for f in figures:  # in order: the first interval that establishes what a symbol needs decides, and the scan stops when none is left
            if not mine:
                break
            text = texts.get((f.source_kind, f.source_id))
            if text is None:
                continue
            for bounds, m, ex in rounded_intervals(f, text, declared):
                if bounds[0] not in wanted and bounds[1] not in wanted:
                    continue
                if id(f) not in plain:
                    plain[id(f)] = figure_stated_plainly(f, text)
                if not plain[id(f)]:
                    break
                for name, ks in list(mine.items()):
                    if all(_end_establishes(bounds, literals[k]) for k in ks):
                        derivation = interval_derivation(bounds, m, ex)
                        for k in ks:
                            out[k] = derivation
                        del mine[name]
    return out


def _expr_text(expr) -> str:
    """A short rendering of an IR expression for a check's detail (data, never evaluated)."""
    op = getattr(expr, "op", None)
    if op == "var":
        return expr.name  # type: ignore[attr-defined]
    if op in ("int", "real"):
        return expr.value  # type: ignore[attr-defined]
    if op in ("eq", "ne", "lt", "le", "gt", "ge"):
        sign = {"eq": "=", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}[op]
        return f"{_expr_text(expr.left)} {sign} {_expr_text(expr.right)}"  # type: ignore[attr-defined]
    if op in ("add", "mul", "and", "or"):
        sign = {"add": " + ", "mul": " * ", "and": " and ", "or": " or "}[op]
        return "(" + sign.join(_expr_text(a) for a in expr.args) + ")"  # type: ignore[attr-defined]
    if op in ("sub", "div", "idiv", "mod", "implies", "iff"):
        sign = {"sub": " - ", "div": " / ", "idiv": " div ", "mod": " mod ", "implies": " -> ", "iff": " <-> "}[op]
        return f"({_expr_text(expr.left)}{sign}{_expr_text(expr.right)})"  # type: ignore[attr-defined]
    if op == "neg":
        return f"-{_expr_text(expr.arg)}"  # type: ignore[attr-defined]
    if op in ("not", "to_real"):
        return f"{op}({_expr_text(expr.arg)})"  # type: ignore[attr-defined]
    return op or "?"


def _relation_text(assertion: Assertion) -> str:
    return truncate_detail(_expr_text(assertion.expr), 160)


def truncate_detail(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _conflicting_figures(assertion: Assertion, missing: list[_Literal], sources: list[SourceText]) -> list[str]:
    """Figures the records state for the same kind of quantity as a premise figure they do not state: the same unit
    dimension, taken from the compared symbol's declared reading or from the premise's own label ("Distance is 160 km"
    against a text's "120 km"). Evidence that the premise substituted a figure, not merely that it is unstated."""
    label_figures = figures_in(SourceText("claim", assertion.id, assertion.label)) if assertion.label else ()
    out: list[str] = []
    for lit in missing:
        dims: set[str] = set()
        if lit.declared.kind == "unit" and lit.declared.dim:
            dims.add(lit.declared.dim)
        dims |= {f.unit_dim for f in label_figures if f.unit_dim and f.unit_dim not in ("dimensionless", "currency") and abs(f.value) == abs(lit.value)}
        if not dims:
            continue
        stated = [f for src in sources for f in figures_in(src) if f.unit_dim in dims]
        if stated:
            out.append(f"{lit.written} is stated nowhere, while " + ", ".join(f.where() for f in stated[:3]) + f" state(s) a {'/'.join(sorted(dims))} figure")
    return out


def _task_doc(task: Optional[TaskRecord]) -> Optional[SuppliedText]:
    if task is None:
        return None
    return SuppliedText(document_id=task.task_id, title="the task as issued", text=task.text, provenance=f"task record issued by {task.issued_by}")


def _ref_docs(docs: dict[str, SuppliedText], task: Optional[TaskRecord]) -> dict[str, SuppliedText]:
    """The documents a reference may name: the supplied texts and, when given, the task record (by its task_id or as
    'task')."""
    tdoc = _task_doc(task)
    if tdoc is None:
        return docs
    out = dict(docs)
    for ident in (task.task_id, *TASK_DOCUMENT_IDS):  # type: ignore[union-attr]
        out.setdefault(ident, tdoc.model_copy(update={"document_id": ident}))
    return out


def _authority_sources(grounding: Grounding, docs: dict[str, SuppliedText], supplied: Sequence[SuppliedText], task: Optional[TaskRecord]) -> tuple[list[SourceText], list[str]]:
    """The records a task-authority premise may rest on: the documents its references name, else every supplied text and
    the task record. ``(sources, the named document ids)``."""
    # a relayed peer report is never a record of the task: its figures and relations validate no task authority
    named = [r.document_id for r in grounding.source_refs if r.document_id in docs and not is_peer_document(docs[r.document_id])]
    if named:
        sources = [SourceText("task" if task is not None and docs[d].text == task.text and d not in {t.document_id for t in supplied} else "supplied_text",  # type: ignore[arg-type]
                              d, docs[d].text) for d in dict.fromkeys(named)]
        return sources, named
    sources = [SourceText("supplied_text", t.document_id, t.text) for t in supplied if not is_peer_document(t)]
    if task is not None:
        sources.append(SourceText("task", task.task_id, task.text))
    return sources, []


def _check_authority(assertion: Assertion, grounding: Grounding, literals: list[_Literal], docs: dict[str, SuppliedText], supplied: Sequence[SuppliedText],
                     task: Optional[TaskRecord], checks: list[GroundingCheck]) -> Grounding:
    """Validate the task authority a kind claims (see the module docstring). Called only for an unchecked grounding of a
    task-authority kind (no reference verified its whole content, none refuted it). A relation is validated only by a
    record that states it (:func:`.relations.stated_relation`); its figures occurring in a record leave it unvalidated."""
    kind = grounding.kind
    sources, named = _authority_sources(grounding, docs, supplied, task)
    searched = ", ".join(dict.fromkeys(s.ident for s in sources)) or "no supplied text and no task record"
    doc_id = named[0] if named else None
    no_task = "" if task is not None else "; no task record was given, so the task's own wording could not be checked"
    relation = numeric_shape(assertion.expr) == "relation"
    if relation:
        stated = stated_relation(assertion.expr, sources)
        if stated is not None:
            checks.append(GroundingCheck(target_id=assertion.id, kind=kind, method="relation_in_source", verified=True, document_id=stated.source.ident[:200],  # type: ignore[arg-type]
                                         detail=(f"the kind {kind} claims the task's authority, and the task material states the premise's relation "
                                                 f"{_relation_text(assertion)} as a given: {stated.where()}")[:2000]))
            return grounding.model_copy(update={"verified": True})
    if not literals:
        verified = False if task is not None else None
        if relation:
            detail = (f"the kind {kind} claims the task's authority, but no record states the premise's relation {_relation_text(assertion)} (searched: "
                      f"{searched}) and it states no figure a record could hold: "
                      + ("no record validates it" if verified is False else f"its authority is unvalidated{no_task}"))
        else:
            detail = (f"the kind {kind} claims the task's authority, but the premise states no figure and no excerpt of a supplied text "
                      f"or of the task locates it (searched: {searched}): " + ("no record validates it" if verified is False else f"its authority is unvalidated{no_task}"))
        checks.append(GroundingCheck(target_id=assertion.id, kind=kind, method="relation_in_source" if relation else "numeric_in_task",  # type: ignore[arg-type]
                                     verified=verified, document_id=doc_id, detail=detail[:2000]))
        return grounding.model_copy(update={"verified": verified})
    verified, check, missing = _figures_check(assertion.id, kind, literals, sources, doc_id, "numeric_in_task", f"the task material ({searched})")
    if verified is True:
        if relation:
            # the figures are the records', the relation is not: a figure says nothing about the relation it enters
            stated_figures = (check.detail if check is not None else "the task material states every figure as written") or ""
            checks.append(GroundingCheck(target_id=assertion.id, kind=kind, method="relation_in_source", verified=None, document_id=doc_id,  # type: ignore[arg-type]
                                         detail=(f"the kind {kind} claims the task's authority, but no record states the premise's relation "
                                                 f"{_relation_text(assertion)} (searched: {searched}): {stated_figures}; figures occurring in a record are "
                                                 "no evidence for the relation that combines them, so the relation is the translation's own and stays "
                                                 "unverified until a record states it")[:2000]))
            return grounding.model_copy(update={"verified": None})
        if check is not None:
            checks.append(check)
        return grounding.model_copy(update={"verified": True})
    assert check is not None
    conflicts = _conflicting_figures(assertion, missing, sources)
    if task is not None or conflicts:
        detail = f"the kind {kind} claims the task's authority, but {check.detail}" + (f"; {'; '.join(conflicts)}" if conflicts else "")
        checks.append(check.model_copy(update={"detail": (detail + ": the premise is the translation's own figure, an evidence failure, so its "
                                                          "dependency is unresolved")[:2000]}))
        return grounding.model_copy(update={"verified": False})
    checks.append(check.model_copy(update={"verified": None, "detail": (f"the kind {kind} claims the task's authority, which is unvalidated: {check.detail}"
                                                                       f"{no_task}; until a record validates it the premise is not a task fact")[:2000]}))
    return grounding.model_copy(update={"verified": None})


def _located_spans(grounding: Grounding, docs: dict[str, SuppliedText], task: Optional[TaskRecord]) -> list[tuple[SourceText, tuple[int, int], Optional[str]]]:
    """``(the document a reference names, the characters its excerpt occupies, the excerpt as written when it was located
    as an elided quotation, else None)`` for every reference whose excerpt the verbatim or normalised tiers locate (the
    tiers that verify a reference). An elided excerpt's span also holds what the elision left out, which it does not
    quote."""
    out: list[tuple[SourceText, tuple[int, int], Optional[str]]] = []
    for ref in grounding.source_refs:
        if not ref.excerpt or not ref.excerpt.strip():
            continue
        doc = docs.get(ref.document_id)
        if doc is None:
            continue
        match = locate_quotation(ref.excerpt, doc.text, document_id=doc.document_id)
        if match is None:
            continue
        is_task = task is not None and doc.text == task.text and ref.document_id in (TASK_DOCUMENT_IDS | {task.task_id})
        out.append((SourceText("task" if is_task else "supplied_text", ref.document_id, doc.text), (match.start, match.end),  # type: ignore[arg-type]
                    ref.excerpt if match.elided else None))
    return out


def _check_assertion(assertion: Assertion, docs: dict[str, SuppliedText], checks: list[GroundingCheck], symbols: Optional[dict[str, Symbol]] = None,
                     task: Optional[TaskRecord] = None, authority: bool = False, supplied: Sequence[SuppliedText] = ()) -> Assertion:
    """Check an assertion's grounding (whole content, see the module docstring). Every reference is located first; a
    located excerpt then verifies the premise only when it states the premise's whole content, read where it stands in its
    document:

    * an assignment's figures (typed: ``0.2`` and ``1/5`` are both stated by "20%", one recorded derivation; a symbol's
      declared reading is respected), each stated so that it establishes its comparison: otherwise ``verified=False`` with
      a ``figures_in_excerpt`` check naming what the excerpt lacks (a premise 'items[1] is 3' grounded by the excerpt
      'scores = [12, 19, 23, ...]');
    * a relation itself, as a given (``relation_in_source``): otherwise ``verified=None`` (the span is located, the
      relation is the translation's own), whatever the kind.

    With ``authority`` a premise of a task-authority kind that no reference verified is validated against the supplied
    texts and the task record (:func:`_check_authority`)."""
    if assertion.grounding is None:
        return assertion
    grounding, found = check_grounding(assertion.id, assertion.grounding, docs)
    if authority and grounding.kind in TASK_AUTHORITY_KINDS and not grounding.source_refs:
        found = [c for c in found if c.method != "not_checkable"]  # the authority check below reports on it instead
    checks.extend(found)
    literals = _literals(assertion.expr, symbols or {})
    relation = numeric_shape(assertion.expr) == "relation"
    spans = _located_spans(grounding, docs, task) if grounding.verified is True else []
    if grounding.verified is True and spans and literals:
        within: dict[tuple[str, str], list[tuple[int, int, Optional[frozenset[Fraction]]]]] = {}
        located: list[SourceText] = []
        for src, span, elided in spans:  # one document named by several references is one source with several located spans
            key = (src.kind, src.ident)
            if key not in within:
                within[key] = []
                located.append(src)
            allowed = None if elided is None else frozenset(f.value for f in figures_in(SourceText(src.kind, src.ident, elided)))
            within[key].append((span[0], span[1], allowed))
        verified, check, _missing = _figures_check(assertion.id, grounding.kind, literals, located, spans[0][0].ident, "figures_in_excerpt",
                                                   "the excerpt is located but", within=within)
        if check is not None:
            if verified is True:
                check = check.model_copy(update={"detail": (check.detail or "").replace("the excerpt is located but states", "the located excerpt states")})
            else:
                check = check.model_copy(update={"detail": f"{check.detail}: it does not ground this premise"[:2000]})
            checks.append(check)
        if verified is False:
            grounding = grounding.model_copy(update={"verified": False})
    if grounding.verified is True and relation:
        stated = None
        for src, span, elided in spans:
            if elided is not None and not writes_relation(assertion.expr, elided):
                continue  # an elided excerpt quotes only its fragments: the relation must be among them
            stated = stated_relation(assertion.expr, [src], within=span)
            if stated is not None:
                break
        if stated is not None:
            checks.append(GroundingCheck(target_id=assertion.id, kind=grounding.kind, method="relation_in_source", verified=True,
                                         document_id=stated.source.ident[:200],
                                         detail=(f"the located excerpt states the premise's relation {_relation_text(assertion)} as a given: "
                                                 f"{stated.where()}")[:2000]))
        else:
            checks.append(GroundingCheck(target_id=assertion.id, kind=grounding.kind, method="relation_in_source", verified=None,
                                         document_id=spans[0][0].ident[:200] if spans else None,
                                         detail=(f"the references are located, but none states the premise's relation {_relation_text(assertion)} as "
                                                 "a given: a located span that holds the relation's figures or words about them does not state the "
                                                 "relation, so the relation is the translation's own and is not verified by the span")[:2000]))
            grounding = grounding.model_copy(update={"verified": None})
    if authority and grounding.kind in TASK_AUTHORITY_KINDS and grounding.verified is None:
        grounding = _check_authority(assertion, grounding, literals, docs, supplied, task, checks)
    return assertion.model_copy(update={"grounding": grounding})


def check_problem_grounding(problem: Problem, supplied_texts: list[SuppliedText], task: Optional[TaskRecord] = None) -> tuple[Problem, list[GroundingCheck]]:
    """Return a copy of ``problem`` with every ``grounding.verified`` set, plus the checks.

    Every reference is checked (an excerpt located, a document and locator checked) against the supplied text named by
    ``document_id`` or, when ``task`` is given, the task record (cited by its task_id or as 'task'); a grounding is
    verified only by complete support. A premise of a task-authority kind (``arithmetic_fact``, ``task_setting``,
    ``rubric_rule``) that no reference verified is validated against the supplied texts and the task record (see the
    module docstring): True when they state every figure it states; False when the task record was given and they do
    not, or when they state a conflicting figure of the same unit (the engine then reports it as an ungrounded
    dependency); otherwise None with an ``unvalidated`` ``numeric_in_task`` check. Other kinds with no reference stay
    ``not_checkable`` (``verified=None``). The input problem is not modified.
    """
    docs = _ref_docs({t.document_id: t for t in supplied_texts}, task)
    by_name = {s.name: s for s in problem.symbols}
    checks: list[GroundingCheck] = []
    symbols = [_check_symbol(s, docs, checks) for s in problem.symbols]
    premises = [_check_assertion(p, docs, checks, by_name, task, authority=True, supplied=supplied_texts) for p in problem.premises]
    conclusion = _check_assertion(problem.conclusion, docs, checks, by_name, task) if problem.conclusion is not None else None
    checked = problem.model_copy(update={"symbols": symbols, "premises": premises, "conclusion": conclusion})
    return checked, checks


def check_claim_sources(claim: ClaimRecord, supplied_texts: list[SuppliedText]) -> list[GroundingCheck]:
    """Check a claim record's own ``source_refs`` against the supplied texts.

    A ref with an excerpt is checked as a quotation. A ref without an excerpt only
    has its document (and the plausibility of its locator) checked.
    """
    docs = {t.document_id: t for t in supplied_texts}
    checks: list[GroundingCheck] = []
    for ref in claim.source_refs:
        if ref.excerpt and ref.excerpt.strip():
            checks.append(_check_quotation_ref(claim.claim_id, ref, docs))
            continue
        doc = docs.get(ref.document_id)
        if doc is None:
            verified, detail = False, "document_id is not among the supplied texts"
        elif ref.locator and doc.locator_scheme == "none":
            verified, detail = False, "a locator was given but the supplied text has no locator scheme"
        else:
            verified, detail = True, "document exists" + ("; locator form not checked" if ref.locator else "")
        checks.append(GroundingCheck(
            target_id=claim.claim_id, kind="supplied_text", method="locator_exists", verified=verified,
            document_id=ref.document_id, detail=detail,
        ))
    return checks
