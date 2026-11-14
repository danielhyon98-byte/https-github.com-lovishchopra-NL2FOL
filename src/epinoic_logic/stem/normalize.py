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
    * ``+/-`` written before a number (``±0.5 °C`` written ``+/-0.5 °C``, ``1620 +/- 32``) becomes ``±`` and two spaces (STEM repair 4:
      the answer's own uncertainty is read as the supplied texts' is; elsewhere, ``+/- buttons``, it stays as written);
    * integration gate 3 (rule sign-forms): the fullwidth and small forms of the relation signs, the arithmetic operators and the
      brackets the grammar reads (``＝ ﹦ ＜ ＞ ﹤ ﹥ ＋ ﹢ － ﹣ ＊ ﹡ ／ （ ） ［ ］ ﹙ ﹚``), TWO CONSECUTIVE EQUALS SIGNS ``⩵``, the
      over-equal forms ``≦ ≧`` (as ``⩽ ⩾`` are read), the fraction slash ``⁄``, the ratio sign ``∶``, the tilde operator ``∼``, the
      dingbat signs ``✕ ✖ ➕ ➖ ➗`` and the increment sign ``∆`` (U+2206, read as the Greek ``Δ`` it is drawn as) become the sign they
      stand for, one character for one. Before, each was an unknown character: a step written with ``＝`` had no relation, no check
      and no finding, and one written with ``＋`` or ``／`` was cut at it (``3 ＋ 4 = 7`` read as ``4 = 7``, an error on correct work).
      Every other mathematical sign the grammar does not read is an ``ERROR`` token of the lexer (``lexer.sign_outside_grammar``);
    * integration gate 4 (rule sign-forms in every category): the equals signs of other categories, U+1F7F0 HEAVY EQUALS SIGN ``🟰`` (an
      emoji models emit) and U+A78A MODIFIER LETTER SHORT EQUALS SIGN ``꞊``, and the double hyphens drawn as ``=``, U+30A0
      KATAKANA-HIRAGANA DOUBLE HYPHEN ``゠`` and U+2E40 DOUBLE HYPHEN ``⹀``, become ``=``. Before, each was read as nothing and named
      nothing: a wrong step written with one crossed the hub ACCEPTED with no check and no finding. The other look-alikes of a relation
      sign are the lexer's (``lexer.RELATION_LOOKALIKES``, read by the unread-relation rule);
    * integration gate 4: every other invisible character (a Unicode default-ignorable code point: the variation selectors, the soft
      hyphen, the bidirectional marks, embeddings, overrides and isolates, the invisible operators of mathematical text, the tag
      characters, the fillers) becomes a space, as the zero-width characters do: it is read as it is drawn, as nothing between two
      tokens (``a``, U+2062 INVISIBLE TIMES, ``b`` is the juxtaposition ``a b``). Unread, such a character ended the run and let a run
      start right after it, as a blank does not: the emoji presentation selector U+FE0F, which follows the dingbat signs as models
      write them (``✖``, ``➕`` or ``🟰`` then U+FE0F), cut ``x = 3 ✖ 4 = 12`` so written into ``4 = 12`` (an error on correct
      work), and an invisible mark between two numerals (INVISIBLE TIMES, a left-to-right mark, a soft hyphen) did the same to
      ``x = 3 4 = 12``, whose relation, with a blank, is named unread (ST-PARSE-001);
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

__all__ = ["MASK_FILL", "MASK_HEAD", "SIGN_FORMS", "blank_ranges", "masked_view", "prose_view", "reading_view"]

MASK_HEAD = "X"
MASK_FILL = "x"

_SPACES = {" ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
           " ": " ", " ": " ", " ": " ", "　": " "}
_ZERO_WIDTH = {"​": " ", "‌": " ", "‍": " ", "⁠": " ", "﻿": " "}
#: integration gate 3 (rule sign-forms): the forms of a sign the grammar reads, one character for one (module docstring)
SIGN_FORMS = {"＝": "=", "﹦": "=", "⩵": "=", "＜": "<", "＞": ">", "﹤": "<", "﹥": ">", "≦": "≤", "≧": "≥",
              "＋": "+", "﹢": "+", "➕": "+", "－": "-", "﹣": "-", "➖": "-", "＊": "*", "﹡": "*", "✕": "×",
              "✖": "×", "／": "/", "⁄": "/", "➗": "÷", "（": "(", "）": ")", "﹙": "(", "﹚": ")", "［": "[",
              "］": "]", "∶": ":", "∼": "~", "∆": "Δ",
              # integration gate 4 (rule sign-forms in every category): the heavy and short equals signs and the double hyphens drawn as '='
              "\U0001f7f0": "=", "\ua78a": "=", "\u30a0": "=", "\u2e40": "="}
#: integration gate 4: the Unicode default-ignorable code points (DerivedCoreProperties, assigned or not), invisible like the zero-width
#: characters, become a space (module docstring)
_IGNORABLE_RANGES = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F),
                     (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8),
                     (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))
_INVISIBLE = {chr(c): " " for a, b in _IGNORABLE_RANGES for c in range(a, b + 1)}
_SIMPLE = {"−": "-", "⋅": "·", "∙": "·", "∗": "*", "Ω": "Ω", "‑": "-"} | _SPACES | _ZERO_WIDTH | _INVISIBLE | SIGN_FORMS
_DASHES = frozenset({"–", "‒"})
#: round-9 clearance (rule spaced-dash): the dashes a model writes for a minus between two numbers with a blank on each side ('20 – 4.0',
#: '10⁴ — 5', '(3.0) ‐ (1.5)'): the en dash, the figure dash, the em dash and U+2010 HYPHEN
_SPACED_DASHES = frozenset({"–", "‒", "—", "‐"})
#: what may stand right before the blank before such a dash (the end of a number, a closing bracket) and right after the blank after it
_DASH_LEFT_END = frozenset("0123456789)]⁰¹²³⁴⁵⁶⁷⁸⁹")
_DASH_RIGHT_START = frozenset("0123456789(.")
#: characters after which '+/-' written before a number is a plus-or-minus sign (STEM repair 4)
_PLUS_MINUS_BEFORE = frozenset(" \t\n(=:,;[")
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
        elif ch in _DASHES or ch in _SPACED_DASHES:
            prev = text[i - 1] if i > 0 else " "
            nxt = text[i + 1] if i + 1 < n else ""
            if ch in _DASHES and (prev in _MINUS_BEFORE or prev in _SIMPLE) and nxt and (nxt.isalnum() or nxt in "(√\\"):
                out[i] = "-"
            elif prev in " \t" and nxt in (" ", "\t") and i >= 2 and text[i - 2] in _DASH_LEFT_END and i + 2 < n and text[i + 2] in _DASH_RIGHT_START:
                # round-9 clearance (rule spaced-dash): a dash with one blank on each side between the end of a number and the start of one
                # ('Δv = 20 – 4.0 = 16 m s⁻¹') is a minus sign: it had cut the left operand, so '4.0 = 16 m s⁻¹' was checked and failed
                # (INT-SUBJ-001 on correct work). A dash written between words, a dash with no blank ('3–5 s', a range) and a dash before a
                # word ('= 5.0 m s⁻² — the acceleration') stay dashes
                out[i] = "-"
    if "+/-" in text:
        k = text.find("+/-")
        while k >= 0:
            prev = text[k - 1] if k > 0 else " "
            j = k + 3
            while j < n and j - k <= 4 and text[j] in " \t":
                j += 1
            if (prev in _PLUS_MINUS_BEFORE or prev.isdigit()) and j < n and (text[j].isdigit() or text[j] == "."):
                out[k], out[k + 1], out[k + 2] = "±", " ", " "
            k = text.find("+/-", k + 3)
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
