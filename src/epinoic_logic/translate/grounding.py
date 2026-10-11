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
3. ``normalized_match`` with elision: an excerpt containing an ellipsis matches when
   each fragment occurs in order in the normalized text.

Offsets returned always refer to the ORIGINAL text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from ..ir.schema import Assertion, Grounding, Problem, SourceRef, Symbol
from .contracts import ClaimRecord, GroundingCheck, SuppliedText

MatchMethod = Literal["verbatim_match", "normalized_match"]

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
    """Where an excerpt was found in the original text and how."""
    start: int
    end: int
    matched: str
    method: MatchMethod
    elided: bool = False


def _normalize_indexed(text: str) -> tuple[str, list[int]]:
    """Normalize ``text``; return the result and, per output char, its source offset."""
    out: list[str] = []
    idx: list[int] = []
    pending_space: Optional[int] = None
    for pos, ch in enumerate(text):
        if ch in _INVISIBLE:
            continue
        if ch.isspace():
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


def _strip_outer_quotes(excerpt: str) -> str:
    s = excerpt.strip()
    for left, right in _OUTER_QUOTES:
        if len(s) >= 2 and s.startswith(left) and s.endswith(right):
            return s[1:-1].strip()
    return s


def _span(idx: list[int], start: int, length: int) -> tuple[int, int]:
    return idx[start], idx[start + length - 1] + 1


def _find_elided(fragments: list[str], norm_text: str, idx: list[int], text: str) -> Optional[QuotationMatch]:
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
    return QuotationMatch(first_start, end, text[first_start:end], "normalized_match", elided=True)


def locate_quotation(excerpt: str, text: str) -> Optional[QuotationMatch]:
    """Find ``excerpt`` in ``text`` (verbatim, then normalized, then elided)."""
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
    if "..." in norm_ex:
        fragments = [f.strip() for f in norm_ex.split("...") if f.strip()]
        if fragments:
            return _find_elided(fragments, norm_text, idx, text)
    return None


def find_quotation(excerpt: str, text: str) -> Optional[tuple[int, int, str]]:
    """Return ``(start, end, matched_text)`` in ``text`` for ``excerpt``, or ``None``."""
    match = locate_quotation(excerpt, text)
    if match is None:
        return None
    return match.start, match.end, match.matched


def _check_quotation_ref(target_id: str, ref: SourceRef, docs: dict[str, SuppliedText]) -> GroundingCheck:
    doc = docs.get(ref.document_id)
    if doc is None:
        return GroundingCheck(
            target_id=target_id, kind="quotation", method="verbatim_match", verified=False,
            document_id=ref.document_id, detail="document_id is not among the supplied texts",
        )
    if not ref.excerpt or not ref.excerpt.strip():
        return GroundingCheck(
            target_id=target_id, kind="quotation", method="verbatim_match", verified=False,
            document_id=ref.document_id, detail="quotation grounding carries no excerpt",
        )
    match = locate_quotation(ref.excerpt, doc.text)
    if match is None:
        return GroundingCheck(
            target_id=target_id, kind="quotation", method="normalized_match", verified=False,
            document_id=ref.document_id, detail="excerpt not found in the document (verbatim or normalized)",
        )
    how = {"verbatim_match": "verbatim", "normalized_match": "after typographic normalization"}[match.method]
    if match.elided:
        how = "as an elided quotation, fragments in order, after typographic normalization"
    return GroundingCheck(
        target_id=target_id, kind="quotation", method=match.method, verified=True,
        document_id=ref.document_id, detail=f"found {how} at characters {match.start}-{match.end}",
    )


def check_grounding(target_id: str, grounding: Grounding, docs: dict[str, SuppliedText]) -> tuple[Grounding, list[GroundingCheck]]:
    """Check one grounding; return the grounding with ``verified`` set and the checks."""
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

    Quotation groundings are verified True/False against the supplied text named by
    ``document_id``; all other kinds are ``not_checkable`` and get ``verified=None``.
    The input problem is not modified.
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
