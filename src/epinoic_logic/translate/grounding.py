"""Deterministic grounding checks.

Source integrity is a non-negotiable of the specialist agents: never invent
quotations or citations. This module checks the one kind of grounding that code
can check exactly, a quotation against the supplied text, and marks every other
kind as not checkable. It sets ``Grounding.verified``; nothing else does.

Matching is attempted in three tiers, reported through ``GroundingCheck.method``:

1. ``verbatim_match``: the excerpt occurs character for character.
2. ``normalized_match``: the excerpt occurs after typographic normalization of both
   sides (curly/straight quotes, dash variants, whitespace runs, ellipsis forms,
   invisible characters). Case is NOT folded: a changed word is a changed quotation.
   Two further normalizations belong to this tier because they are the conventions
   of quoting itself, not changes to the words: the quotation marks INSIDE an excerpt
   are folded to one class (a quotation that nests the text's double marks as single
   marks matches; ``QuotationMatch.note`` says so), and a line break of the document
   may be written ``" / "`` in the excerpt (verse quoted in running prose).
3. ``normalized_match`` with elision: an excerpt containing an ellipsis matches when
   each fragment occurs in order in the normalized text AND the whole span stays
   within :data:`ELISION_WINDOW_CHARS` plus the excerpt's own length. Fragments that
   are far apart are a long elision, reported by the inexact tier, never as a match.

A fourth, *inexact* tier (:func:`locate_quotation_inexact`) finds the words after a
conventional adjustment of written analysis: a changed initial capital (a sentence
opening quoted mid-sentence) or omitted or added verse line-break marks (``/``);
:func:`locate_long_elision` finds an elision whose fragments all occur in order but span
more than the elision window. Neither verifies a grounding: ``Grounding.verified`` stays
``False`` for the IR path, but the check's ``detail`` says the quotation *differs in
form* and names the difference, so the Overseer (and the channel) can tell a form
problem from an invented quotation.

Every grounding whose ``source_refs`` carry an excerpt is checked against the named
document whatever its ``kind``; only groundings without an excerpt are
``not_checkable``.

Offsets returned always refer to the ORIGINAL text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from ..ir.schema import Assertion, Grounding, Problem, SourceRef, Symbol
from .contracts import ClaimRecord, GroundingCheck, SuppliedText

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


NOTE_QUOTES_FOLDED = "quotation marks inside the excerpt folded to one class (the nesting level of the marks differs)"
NOTE_LINEBREAK_SLASH = "line breaks of the document written as ' / ' in the excerpt"


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
    return _collapse_spaced_ellipsis(out, idx)


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


def _strip_outer_quotes(excerpt: str) -> str:
    s = excerpt.strip()
    for left, right in _OUTER_QUOTES:
        if len(s) >= 2 and s.startswith(left) and s.endswith(right):
            return s[1:-1].strip()
    return s


def _span(idx: list[int], start: int, length: int) -> tuple[int, int]:
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


def _find_folded(norm_ex: str, norm_text: str, idx: list[int], text: str, note: str) -> Optional[QuotationMatch]:
    if "'" not in norm_ex and '"' not in norm_ex:
        return None
    folded_text = _fold_quote_marks(norm_text)
    for cand in _folded_candidates(norm_ex):
        pos = folded_text.find(cand)
        if pos >= 0:
            start, end = _span(idx, pos, len(cand))
            return QuotationMatch(start, end, text[start:end], "normalized_match", note=note)
    return None


def _elision_fragments(norm_ex: str) -> list[str]:
    return [f.strip() for f in norm_ex.split("...") if f.strip()] if "..." in norm_ex else []


def _find_elided(fragments: list[str], norm_text: str, idx: list[int], text: str, *, window: Optional[int] = ELISION_WINDOW_CHARS) -> Optional[QuotationMatch]:
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


def locate_quotation(excerpt: str, text: str) -> Optional[QuotationMatch]:
    """Find ``excerpt`` in ``text`` (verbatim, then normalized, then elided).

    The normalized tier also folds the quotation marks inside the excerpt to one class
    (nested marks) and reads ``" / "`` in the excerpt as a line break of the document;
    a match that relied on either carries a ``note``."""
    ex = _strip_outer_quotes(excerpt)
    if not ex:
        return None
    pos = text.find(ex)
    if pos >= 0:
        return QuotationMatch(pos, pos + len(ex), ex, "verbatim_match")
    norm_text, idx = _normalize_indexed(text)
    norm_ex = normalize_quote(ex)
    if not norm_ex:
        return None
    pos = norm_text.find(norm_ex)
    if pos >= 0:
        start, end = _span(idx, pos, len(norm_ex))
        return QuotationMatch(start, end, text[start:end], "normalized_match")
    folded = _find_folded(norm_ex, norm_text, idx, text, NOTE_QUOTES_FOLDED)
    if folded is not None:
        return folded
    slash_text: Optional[str] = None
    slash_idx: list[int] = []
    slash_ex = norm_ex
    if "/" in norm_ex and "\n" in text:
        # Line breaks of the document become " / " and a blank line " // "; slash runs are folded on both sides so a
        # stanza break written with one or two marks compares equal.
        slash_text, slash_idx = _fold_slash_runs(*_normalize_indexed(text, newline_as_slash=True))
        slash_ex = _fold_slash_runs(norm_ex)[0]
        pos = slash_text.find(slash_ex)
        if pos >= 0:
            start, end = _span(slash_idx, pos, len(slash_ex))
            return QuotationMatch(start, end, text[start:end], "normalized_match", note=NOTE_LINEBREAK_SLASH)
        folded = _find_folded(slash_ex, slash_text, slash_idx, text, NOTE_LINEBREAK_SLASH + "; " + NOTE_QUOTES_FOLDED)
        if folded is not None:
            return folded
    fragments = _elision_fragments(norm_ex)
    if fragments:
        found = _find_elided(fragments, norm_text, idx, text)
        if found is None and slash_text is not None:
            found = _find_elided(_elision_fragments(slash_ex), slash_text, slash_idx, text)
            if found is not None:
                found = QuotationMatch(found.start, found.end, found.matched, found.method, elided=True, note=NOTE_LINEBREAK_SLASH)
        return found
    return None


def _swap_first_alpha_case(s: str) -> str:
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.swapcase() + s[i + 1:]
    return s


def _drop_linebreak_marks(chars: str, idx: list[int]) -> tuple[str, list[int]]:
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


def locate_quotation_inexact(excerpt: str, text: str) -> Optional[tuple[QuotationMatch, str]]:
    """Find ``excerpt`` after a conventional quotation-form adjustment; ``(match, difference)``.

    Tried only after :func:`locate_quotation` failed. Two adjustments are recognised:
    the first alphabetic character's case (``"for the immense majority"`` quoted from a
    sentence opening ``For``), and verse line-break marks omitted or added (``"mock the
    meat"`` for ``mock / The meat``, where the case of the word after the mark may also
    differ). Anything else (a changed word, a reordering) is not found; a long elision
    is a separate question answered by :func:`locate_long_elision`.
    """
    ex = _strip_outer_quotes(excerpt)
    if not ex:
        return None
    swapped = _swap_first_alpha_case(ex)
    if swapped != ex:
        pos = text.find(swapped)
        if pos >= 0:
            return QuotationMatch(pos, pos + len(swapped), swapped, "verbatim_match"), "differs only in the initial capital"
        norm_text, idx = _normalize_indexed(text)
        norm_sw = normalize_quote(swapped)
        pos = norm_text.find(norm_sw)
        if pos >= 0 and norm_sw:
            start, end = _span(idx, pos, len(norm_sw))
            return QuotationMatch(start, end, text[start:end], "normalized_match"), "differs only in the initial capital"
    if "/" in ex or "/" in text:
        norm_text, idx = _normalize_indexed(text)
        stripped_text, idx2 = _drop_linebreak_marks(norm_text, idx)
        stripped_ex, _ = _drop_linebreak_marks(*_normalize_indexed(ex))
        if stripped_ex:
            pos = stripped_text.find(stripped_ex)
            how = "omits or adds a verse line-break mark"
            if pos < 0:
                pos = stripped_text.casefold().find(stripped_ex.casefold())
                how = "omits or adds a verse line-break mark and differs in letter case at a line start"
            if pos >= 0:
                start, end = _span(idx2, pos, len(stripped_ex))
                return QuotationMatch(start, end, text[start:end], "normalized_match"), how
    return None


def locate_long_elision(excerpt: str, text: str) -> Optional[tuple[QuotationMatch, str]]:
    """An elided excerpt whose fragments all occur in order but span more than
    :data:`ELISION_WINDOW_CHARS` beyond the quoted words: ``(match, difference)`` naming the
    omitted span, or None. The words were found, so this is a form difference (a long
    elision), not an invented quotation; it never verifies a grounding."""
    ex = _strip_outer_quotes(excerpt)
    fragments = _elision_fragments(normalize_quote(ex)) if ex else []
    if len(fragments) < 2:
        return None
    norm_text, idx = _normalize_indexed(text)
    far = _find_elided(fragments, norm_text, idx, text, window=None)
    if far is None:
        return None
    omitted = far.end - far.start - sum(len(f) for f in fragments)
    return far, (f"elides about {omitted} characters of the document between its fragments, more than the "
                 f"{ELISION_WINDOW_CHARS}-character window of an elided quotation (a long elision, not an invented quotation)")


def find_quotation(excerpt: str, text: str) -> Optional[tuple[int, int, str]]:
    """Return ``(start, end, matched_text)`` in ``text`` for ``excerpt``, or ``None``."""
    match = locate_quotation(excerpt, text)
    if match is None:
        return None
    return match.start, match.end, match.matched


def _check_quotation_ref(target_id: str, ref: SourceRef, docs: dict[str, SuppliedText], kind: str = "quotation") -> GroundingCheck:
    doc = docs.get(ref.document_id)
    if doc is None:
        return GroundingCheck(
            target_id=target_id, kind=kind, method="verbatim_match", verified=False,  # type: ignore[arg-type]
            document_id=ref.document_id, detail="document_id is not among the supplied texts",
        )
    if not ref.excerpt or not ref.excerpt.strip():
        return GroundingCheck(
            target_id=target_id, kind=kind, method="verbatim_match", verified=False,  # type: ignore[arg-type]
            document_id=ref.document_id, detail="quotation grounding carries no excerpt",
        )
    match = locate_quotation(ref.excerpt, doc.text)
    if match is None:
        inexact = locate_quotation_inexact(ref.excerpt, doc.text) or locate_long_elision(ref.excerpt, doc.text)
        if inexact is not None:
            near, difference = inexact
            return GroundingCheck(
                target_id=target_id, kind=kind, method="normalized_match", verified=False,  # type: ignore[arg-type]
                document_id=ref.document_id,
                detail=f"quotation differs in form from the document: the words occur at characters {near.start}-{near.end} but the quotation {difference}",
            )
        return GroundingCheck(
            target_id=target_id, kind=kind, method="normalized_match", verified=False,  # type: ignore[arg-type]
            document_id=ref.document_id, detail="excerpt not found in the document (verbatim or normalized)",
        )
    how = {"verbatim_match": "verbatim", "normalized_match": "after typographic normalization"}[match.method]
    if match.elided:
        how = f"as an elided quotation, fragments in order within {match.end - match.start} characters, after typographic normalization"
    if match.note:
        how += f" ({match.note})"
    return GroundingCheck(
        target_id=target_id, kind=kind, method=match.method, verified=True,  # type: ignore[arg-type]
        document_id=ref.document_id, detail=f"found {how} at characters {match.start}-{match.end}",
    )


def check_grounding(target_id: str, grounding: Grounding, docs: dict[str, SuppliedText]) -> tuple[Grounding, list[GroundingCheck]]:
    """Check one grounding; return the grounding with ``verified`` set and the checks.

    A quotation grounding is verified against every source_ref. Any other kind whose
    source_refs carry an excerpt is checked the same way (an excerpt is checkable
    whatever label the translator put on it); a kind without an excerpt is
    ``not_checkable`` and gets ``verified=None``.
    """
    if grounding.kind == "quotation":
        if not grounding.source_refs:
            check = GroundingCheck(
                target_id=target_id, kind="quotation", method="verbatim_match", verified=False,
                detail="quotation grounding has no source_refs",
            )
            return grounding.model_copy(update={"verified": False}), [check]
        checks = [_check_quotation_ref(target_id, ref, docs) for ref in grounding.source_refs]
        verified = all(c.verified is True for c in checks)
        return grounding.model_copy(update={"verified": verified}), checks
    with_excerpt = [r for r in grounding.source_refs if r.excerpt and r.excerpt.strip()]
    if with_excerpt:
        checks = [_check_quotation_ref(target_id, ref, docs, kind=grounding.kind) for ref in with_excerpt]
        verified = all(c.verified is True for c in checks)
        return grounding.model_copy(update={"verified": verified}), checks
    unknown = [r.document_id for r in grounding.source_refs if r.document_id not in docs]
    detail = f"grounding kind {grounding.kind} is not deterministically checkable"
    if unknown:
        detail += "; document_id not among the supplied texts: " + ", ".join(sorted(set(unknown)))
    check = GroundingCheck(
        target_id=target_id, kind=grounding.kind, method="not_checkable", verified=None,
        document_id=grounding.source_refs[0].document_id if grounding.source_refs else None, detail=detail,
    )
    # Any 'verified' value the model wrote is discarded: only checks set it.
    return grounding.model_copy(update={"verified": None}), [check]


def _check_symbol(symbol: Symbol, docs: dict[str, SuppliedText], checks: list[GroundingCheck]) -> Symbol:
    if symbol.grounding is None:
        return symbol
    grounding, found = check_grounding(symbol.name, symbol.grounding, docs)
    checks.extend(found)
    return symbol.model_copy(update={"grounding": grounding})


def _check_assertion(assertion: Assertion, docs: dict[str, SuppliedText], checks: list[GroundingCheck]) -> Assertion:
    if assertion.grounding is None:
        return assertion
    grounding, found = check_grounding(assertion.id, assertion.grounding, docs)
    checks.extend(found)
    return assertion.model_copy(update={"grounding": grounding})


def check_problem_grounding(problem: Problem, supplied_texts: list[SuppliedText]) -> tuple[Problem, list[GroundingCheck]]:
    """Return a copy of ``problem`` with every ``grounding.verified`` set, plus the checks.

    Quotation groundings, and any grounding whose source_refs carry an excerpt, are
    verified True/False against the supplied text named by ``document_id``; kinds
    without an excerpt are ``not_checkable`` and get ``verified=None``. The input
    problem is not modified.
    """
    docs = {t.document_id: t for t in supplied_texts}
    checks: list[GroundingCheck] = []
    symbols = [_check_symbol(s, docs, checks) for s in problem.symbols]
    premises = [_check_assertion(p, docs, checks) for p in problem.premises]
    conclusion = _check_assertion(problem.conclusion, docs, checks) if problem.conclusion is not None else None
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
