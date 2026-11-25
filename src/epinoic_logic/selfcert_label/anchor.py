"""Anchoring a quoted span under the reader's visible form (meaning-check design 2.5.4 step 5; overseer-side design 3.3 step 4).

A quote counts only when it is located in the sentence whose id it carries. Both are brought to the reader's visible form
(:func:`epinoic_logic.selfcert.visible_form`, rules N1 to N7: invisible characters removed, compatibility forms, look-alikes and
letter-spaced runs folded, marks shown as reading tokens), with white space collapsed and quotation marks folded, so a label
that quotes "VERIFIED" for "V E R I F I E D" or plain Latin for look-alike letters is still located. The located span is mapped
back to the rendered sentence and from there, through the scope's offset map, to the original text.

The reader exposes its fold's index map only inside its package, so this module builds the map on top of the public function:
the sentence is cut into pieces at white space between ordinary words (never inside a letter-spaced run, a hyphen-joined break or
markup), each piece is folded alone, and the cut is kept only when the folded pieces put together give exactly the folded
sentence. A piece that folds character by character maps character by character; any other piece maps every visible character to
the whole piece, and a sentence whose pieces do not reproduce its fold maps every visible character to the whole sentence. Either
way a span can only grow, never shrink, so an approximate map widens what blocks and never frees anything (a piece that
folds otherwise keeps its common head and tail one to one, and maps what lies between to that whole range).

A quote may not touch a forbidden character (a placeholder or a delimiter substitute): those positions are masked with a
character no quote can hold, so one search gives the first occurrence that satisfies every condition. Linear in the sentence and
the quote.
"""
from __future__ import annotations

import bisect
import functools
import re
from dataclasses import dataclass
from typing import Optional

from .. import selfcert

__all__ = ["VisibleMap", "visible_map", "locate", "locate_all", "fold_quote"]

#: Pieces up to this length are mapped character by character when they fold that way.
_MASK = "\x00"
_QUOTE_FOLD = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
                             "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"',
                             "»": '"', "‹": "'", "›": "'"})
_WS_RE = re.compile(r"\s+")
_PIECE_RE = re.compile(r"\S+\s*|\s+")
#: A token that may join its neighbours when folded (a single character, a trailing or leading joiner, markup, an entity).
_JOINING_RE = re.compile(r"\A(?:\S|.*[-‐‑­*_<>&;]|[-‐‑*_<>&].*)\Z", re.DOTALL)


@functools.lru_cache(maxsize=8192)
def _vf(s: str) -> str:
    return selfcert.visible_form(s)


@dataclass(frozen=True)
class VisibleMap:
    """``text``: the folded sentence (white space collapsed, quotation marks folded, forbidden positions masked); the rendered
    range ``[starts[i], ends[i])`` is what its character ``i`` stands for. Both lists are non-decreasing."""
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]


def _pieces(rendered: str, forbidden: tuple[tuple[int, int], ...]) -> list[tuple[int, int]]:
    """Pieces of ``rendered``: cut at white space between two non-joining tokens and around every forbidden range."""
    cuts = {0, len(rendered)}
    for a, b in forbidden:
        cuts.add(a)
        cuts.add(b)
    toks = [(m.start(), m.end()) for m in _PIECE_RE.finditer(rendered)]
    for k in range(1, len(toks)):
        prev = rendered[toks[k - 1][0]:toks[k - 1][1]].strip()
        cur = rendered[toks[k][0]:toks[k][1]].strip()
        if prev and cur and not _JOINING_RE.match(prev) and not _JOINING_RE.match(cur):
            cuts.add(toks[k][0])
    ordered = sorted(c for c in cuts if 0 <= c <= len(rendered))
    return [(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1) if ordered[i] < ordered[i + 1]]


def visible_map(rendered: str, forbidden: tuple[tuple[int, int], ...] = ()) -> VisibleMap:
    """The visible form of one rendered sentence with its map back (module docstring)."""
    whole = _vf(rendered)
    parts: list[str] = []
    sa: list[int] = []
    sb: list[int] = []
    for a, b in _pieces(rendered, forbidden):
        piece = rendered[a:b]
        folded = _vf(piece)
        parts.append(folded)
        if folded == piece:
            sa.extend(range(a, b))
            sb.extend(range(a + 1, b + 1))
            continue
        per = [_vf(ch) for ch in piece]
        if "".join(per) == folded:
            for k, f in enumerate(per):
                if f:
                    sa.extend([a + k] * len(f))
                    sb.extend([a + k + 1] * len(f))
            continue
        # the common head and tail of the piece and its fold map one to one; what lies between maps to its whole range
        n = min(len(piece), len(folded))
        p = 0
        while p < n and piece[p] == folded[p]:
            p += 1
        t = 0
        while t < n - p and piece[len(piece) - 1 - t] == folded[len(folded) - 1 - t]:
            t += 1
        mid = len(folded) - p - t
        sa.extend(range(a, a + p))
        sb.extend(range(a + 1, a + p + 1))
        sa.extend([a + p] * mid)
        sb.extend([b - t] * mid)
        sa.extend(range(b - t, b))
        sb.extend(range(b - t + 1, b + 1))
    visible = "".join(parts)
    if visible != whole:
        # the pieces do not reproduce the sentence's fold: every visible character stands for the whole sentence
        visible = whole
        sa = [0] * len(whole)
        sb = [len(rendered)] * len(whole)
    visible = visible.translate(_QUOTE_FOLD)
    # mask the visible characters that touch a forbidden range (the maps are non-decreasing: two bisections per range)
    if forbidden:
        chars = list(visible)
        for fa, fb in forbidden:
            for i in range(bisect.bisect_right(sb, fa), bisect.bisect_left(sa, fb)):
                chars[i] = _MASK
        visible = "".join(chars)
    # collapse white space to one space (leading white space dropped), keeping the map
    out: list[str] = []
    oa: list[int] = []
    ob: list[int] = []
    pos = 0
    for m in _WS_RE.finditer(visible):
        ws, we = m.start(), m.end()
        if ws > pos:
            out.append(visible[pos:ws])
            oa.extend(sa[pos:ws])
            ob.extend(sb[pos:ws])
        if oa:
            out.append(" ")
            oa.append(sa[ws])
            ob.append(sb[we - 1])
        pos = we
    if pos < len(visible):
        out.append(visible[pos:])
        oa.extend(sa[pos:])
        ob.extend(sb[pos:])
    return VisibleMap("".join(out), tuple(oa), tuple(ob))


def fold_quote(quote: str) -> str:
    """A quote in the same form as :func:`visible_map`'s text: folded, quotation marks folded, white space collapsed, trimmed."""
    if not isinstance(quote, str):
        return ""
    return _WS_RE.sub(" ", _vf(quote).translate(_QUOTE_FOLD)).strip()


def locate(quote: str, vmap: VisibleMap) -> Optional[tuple[int, int]]:
    """The rendered range ``[a, b)`` of the first occurrence of ``quote`` in the sentence ``vmap`` (module docstring), or None."""
    q = fold_quote(quote)
    if not q or _MASK in q:
        return None
    k = vmap.text.find(q)
    if k < 0:
        return None
    return (vmap.starts[k], vmap.ends[k + len(q) - 1])


def locate_all(quote: str, vmap: VisibleMap, limit: int) -> list[tuple[int, int]]:
    """The rendered ranges of the occurrences of ``quote`` in the sentence ``vmap``, in order (overlapping ones included), at
    most ``limit`` of them. An exemption may free a span only where the claim lies, so a quote that occurs more than once is
    exempt only when every occurrence is (attack round 16: a short quote located at its first occurrence, inside a gloss, freed
    the claim made by its second)."""
    q = fold_quote(quote)
    if not q or _MASK in q:
        return []
    out: list[tuple[int, int]] = []
    k = vmap.text.find(q)
    while k >= 0 and len(out) < limit:
        out.append((vmap.starts[k], vmap.ends[k + len(q) - 1]))
        k = vmap.text.find(q, k + 1)
    return out
