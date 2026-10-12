"""Reading view and masked views of an agent's text, all of the same length as the original.

Section 4.1 of docs/STEM_DESIGN.md. The original text is never altered: claims are
offset substrings of it. Normalisation happens only in views that are 1:1 character maps,
so an offset in any view is the same offset in the original.

:func:`reading_view`
    * U+2212 MINUS SIGN becomes ``-``;
    * NBSP, U+2007, U+2009, U+200A and U+202F become a space (the number scanner still
      reads a thin space between digit groups through the original);
    * zero-width characters (U+200B, U+200C, U+200D, U+2060, U+FEFF) become a space, so a
      hidden character can split a token but never silently join two;
    * U+22C5 DOT OPERATOR and U+2219 BULLET OPERATOR become U+00B7 MIDDLE DOT (a
      multiplication marker in math and unit context, a hydrate dot in a formula);
      U+2217 ASTERISK OPERATOR becomes ``*``; U+2126 OHM SIGN becomes ``Ω``;
    * an en dash U+2013 or figure dash U+2012 is a minus only after the start, a space,
      an operator, ``(`` or a relation sign and before a digit or a letter; ``3–5 s``
      between two numbers stays a dash (a range, named unsupported) and so does ``H–H``;
    * U+2011 NON-BREAKING HYPHEN becomes ``-``;
    * ``×`` stays its own token; superscript and subscript digits and signs stay as they
      stand (nothing is expanded). Letters of other scripts are left alone, so a Cyrillic
      ``а`` that looks like a Latin ``a`` is never read as one: the lexer rejects it.

:func:`masked_view` replaces given ranges by a same-length placeholder: an upper-case
first character, then a lower-case filler that is no space, punctuation, quotation mark or
digit; newlines inside a range are kept so line numbers do not move. The prose view
(:func:`prose_view`) masks every math span, code span and quantity carrying a unit, so the
shared sentence splitter can start a sentence at a masked span but never splits inside one,
and never sees a decimal point, prime, inch mark or quotation mark inside one.
"""
from __future__ import annotations

from typing import Iterable

__all__ = ["MASK_FILL", "MASK_HEAD", "blank_ranges", "masked_view", "prose_view", "reading_view"]

MASK_HEAD = "X"
MASK_FILL = "x"

_SPACES = {" ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
           " ": " ", " ": " ", " ": " ", "　": " "}
_ZERO_WIDTH = {"​": " ", "‌": " ", "‍": " ", "⁠": " ", "﻿": " "}
_SIMPLE = {"−": "-", "⋅": "·", "∙": "·", "∗": "*", "Ω": "Ω", "‑": "-"} | _SPACES | _ZERO_WIDTH
_DASHES = frozenset({"–", "‒"})
#: characters after which an en dash is a minus sign
_MINUS_BEFORE = frozenset(" \t\n([{+-−×·*/÷=<>≤≥≈≠~^:,;≤≥≈≠⇒→∴")


def reading_view(text: str) -> str:
    """The 1:1 reading view of ``text`` (same length; see the module docstring)."""
    if not text:
        return text
    out = list(text)
    n = len(text)
    for i, ch in enumerate(text):
        rep = _SIMPLE.get(ch)
        if rep is not None:
            out[i] = rep
        elif ch in _DASHES:
            prev = text[i - 1] if i > 0 else " "
            nxt = text[i + 1] if i + 1 < n else ""
            if (prev in _MINUS_BEFORE or prev in _SIMPLE) and nxt and (nxt.isalnum() or nxt in "(√\\"):
                out[i] = "-"
    return "".join(out)


def _merged(ranges: Iterable[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    rs = sorted((max(0, a), min(n, b)) for a, b in ranges if b > a)
    out: list[tuple[int, int]] = []
    for a, b in rs:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def masked_view(text: str, ranges: Iterable[tuple[int, int]]) -> str:
    """``text`` with every range replaced by a same-length placeholder (``Xxxx``), newlines kept."""
    n = len(text)
    merged = _merged(ranges, n)
    if not merged:
        return text
    parts: list[str] = []
    pos = 0
    for a, b in merged:
        parts.append(text[pos:a])
        seg = text[a:b]
        filled = []
        head = True
        for ch in seg:
            if ch == "\n":
                filled.append("\n")
                head = True
            else:
                filled.append(MASK_HEAD if head else MASK_FILL)
                head = False
        parts.append("".join(filled))
        pos = b
    parts.append(text[pos:])
    return "".join(parts)


def blank_ranges(text: str, ranges: Iterable[tuple[int, int]]) -> str:
    """``text`` with every range replaced by spaces (newlines kept): markup markers and list
    markers vanish from the math scan without moving any offset."""
    n = len(text)
    merged = _merged(ranges, n)
    if not merged:
        return text
    parts: list[str] = []
    pos = 0
    for a, b in merged:
        parts.append(text[pos:a])
        parts.append("".join("\n" if ch == "\n" else " " for ch in text[a:b]))
        pos = b
    parts.append(text[pos:])
    return "".join(parts)


def prose_view(reading: str, math_ranges: Iterable[tuple[int, int]], blank: Iterable[tuple[int, int]] = ()) -> str:
    """The prose view: ``reading`` with math, code and unit-quantity ranges masked by
    placeholders and markup markers (emphasis, list markers) blanked."""
    return masked_view(blank_ranges(reading, blank), math_ranges)
