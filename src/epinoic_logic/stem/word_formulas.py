"""Word equations read as the symbol formulas they spell (repair round 2, ADV2-07).

School answers often write a law in words: ``kinetic energy = 0.5 × mass × speed² = 0.5 × 2.0 × 3.0² = 9.0 J`` or
``Magnification = image size / actual size = 40 000 / 20``. The STEM front end reads symbols, so the words stood between
the two sides of a relation as prose (a correct word equation was ST-PARSE-001) and a wrong one (``0.5 × mass × speed``)
was never set beside the data booklet's law.

:func:`word_formula_view` rewrites, in the 1:1 reading view only (the answer itself is never changed, and every offset
stays the same), each word equation whose words all name reference quantities into the symbols of those quantities: the
head (``kinetic energy``) and every word group of the right-hand side (``mass``, ``speed``; ``squared`` and ``cubed`` as
powers) become the quantity's symbol from the closed table :data:`.reference_data.QUANTITIES` (``E_k``, ``m``, ``v``),
written at the end of the words' own characters with spaces before it. The rest of the front end then reads the formula
as it reads ``E_k = 0.5 × m × v²``: its substitution is checked, and the reference checks (ST-REF-001 dimension, ST-REF-002
booklet form) set it beside the booklet's law. A value statement whose head is a quantity a word formula uses
(``Given image size = 40 mm``) has its head rewritten too, so the formula's symbol and its value are one symbol.

Nothing is rewritten unless every word of the right-hand side is covered by a reference name of the profile (a name two
quantities share, such as "energy", covers nothing), the right-hand side holds an operator, and the head is a reference
name preceded by nothing but a filler word ("so", "the", "given", "and"). Text is read only as characters; nothing is
evaluated. Bounded: at most :data:`_MAX_EQUALS` relation signs are read, each with windows of fixed size.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .reference_data import QUANTITIES

__all__ = ["word_formula_view"]

_MAX_EQUALS = 512
_HEAD_WINDOW = 64
_RHS_WINDOW = 200
_MAX_NAME_WORDS = 4
#: Words that may stand before the head of a word equation ('so kinetic energy = ...', 'Given image size = 40 mm').
_FILLER = frozenset("""
so then therefore thus hence and the its their his her a an using where with given since because as which this that now first next
""".split())
_POWER_WORDS = {"squared": "²", "cubed": "³"}
#: Characters a right-hand side of a word equation may hold besides letters, digits and spaces.
_RHS_MARKS = frozenset(".,×x*·÷/+-−–^²³()½¼¾⁻¹")
_OPERATORS = frozenset("×*·÷/+-−–^²³")


@lru_cache(maxsize=32)
def _names(profile_key: str) -> dict[tuple[str, ...], str]:
    """``{name words: symbol}`` of the profile: every name of a reference quantity, lower-cased, with the first spelling the
    table gives the quantity; a name two quantities share is left out."""
    keys: dict[tuple[str, ...], set[str]] = {}
    symbol_of: dict[str, str] = {}
    for q in QUANTITIES:
        if profile_key not in q.profiles:
            continue
        symbol_of.setdefault(q.key, q.symbol)
        for name in q.names:
            words = tuple(name.lower().replace(".", " ").replace("-", " ").split())
            if words and len(words) <= _MAX_NAME_WORDS and all(w.isalpha() for w in words):
                keys.setdefault(words, set()).add(q.key)
    return {w: symbol_of[next(iter(k))] for w, k in keys.items() if len(k) == 1}


def _words(text: str, a: int, b: int) -> list[tuple[int, int, str]]:
    """``(start, end, lower-case word)`` of the Latin letter runs of ``text[a:b]``."""
    out: list[tuple[int, int, str]] = []
    i = a
    while i < b:
        if "a" <= text[i].lower() <= "z":
            j = i
            while j < b and "a" <= text[j].lower() <= "z":
                j += 1
            out.append((i, j, text[i:j].lower()))
            i = j
        else:
            i += 1
    return out


def _head(text: str, k: int, names: dict[tuple[str, ...], str]) -> Optional[tuple[int, int, tuple[str, ...]]]:
    """The reference name right before the relation sign at ``k`` (a filler word, or nothing, before it), else None."""
    j = k - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    end = j + 1
    lo = max(0, k - _HEAD_WINDOW)
    i = end
    while i > lo and (text[i - 1].isalpha() and text[i - 1].isascii() or text[i - 1] in " \t"):
        i -= 1
    words = _words(text, i, end)
    for n in range(min(_MAX_NAME_WORDS, len(words)), 0, -1):
        tail = tuple(w for _a, _b, w in words[-n:])
        if tail not in names:
            continue
        before = words[:-n]
        if before and before[-1][2] not in _FILLER:
            return None  # 'total kinetic energy': another quantity's name
        if not before and i > 0 and (text[i - 1].isalnum() or text[i - 1] in "_^"):
            return None
        return words[-n][0], words[-1][1], tail
    return None


def _rhs_end(text: str, k: int) -> int:
    """Where the right-hand side after the relation sign at ``k`` ends: the next relation sign, a line break, a semicolon, or a
    full stop or comma before a space (never a decimal point), within a fixed window."""
    n = min(len(text), k + 1 + _RHS_WINDOW)
    i = k + 1
    while i < n:
        ch = text[i]
        if ch in "=≈<>≤≥\n;":
            return i
        if ch in ".," and (i + 1 >= len(text) or text[i + 1] in " \t\n"):
            return i
        i += 1
    return i


def _cover(words: list[tuple[int, int, str]], names: dict[tuple[str, ...], str]) -> Optional[list[tuple[int, int, str, str]]]:
    """The right-hand side's words as ``(start, end, symbol, power)``, every word covered by a reference name (longest first)
    or a power word after one; None when a word is not covered."""
    out: list[tuple[int, int, str, str]] = []
    i = 0
    while i < len(words):
        w = words[i][2]
        if w in _POWER_WORDS and out and not out[-1][3]:
            a, _b, sym, _p = out[-1]
            out[-1] = (a, words[i][1], sym, _POWER_WORDS[w])
            i += 1
            continue
        for n in range(min(_MAX_NAME_WORDS, len(words) - i), 0, -1):
            key = tuple(x[2] for x in words[i:i + n])
            if key in names:
                out.append((words[i][0], words[i + n - 1][1], names[key], ""))
                i += n
                break
        else:
            return None
    return out


def _put(chars: list[str], a: int, b: int, symbol: str, power: str = "") -> None:
    """Write ``symbol`` (and a power mark after it) into ``chars[a:b]``: at the end of the span when no power word is folded in
    (so a superscript written after the words still follows the symbol), else at its start; spaces elsewhere."""
    width = b - a
    body = symbol + power
    if len(body) > width:
        return
    fill = [" "] * width
    at = 0 if power else width - len(body)
    for t, ch in enumerate(body):
        fill[at + t] = ch
    chars[a:b] = fill


def word_formula_view(reading: str, profile_key: str) -> str:
    """``reading`` with every word equation of the profile's reference names written in symbols (module docstring); the
    same length, and unchanged when there is none."""
    if "=" not in reading:
        return reading
    names = _names(profile_key)
    if not names:
        return reading
    edits: list[tuple[int, int, str, str]] = []
    used: set[tuple[str, ...]] = set()
    heads: list[tuple[int, int, tuple[str, ...]]] = []
    k = reading.find("=")
    seen = 0
    while k >= 0 and seen < _MAX_EQUALS:
        seen += 1
        head = _head(reading, k, names)
        if head is not None:
            heads.append(head)
            end = _rhs_end(reading, k)
            rhs = reading[k + 1:end]
            every = _words(reading, k + 1, end)
            words = [w for w in every if w[2] != "x"]  # a spaced 'x' is a times sign
            operator = any(ch in _OPERATORS for ch in rhs) or len(words) < len(every)
            if rhs.strip() and operator and all(ch.isalnum() and ch.isascii() or ch in " \t" or ch in _RHS_MARKS for ch in rhs):
                cover = _cover(words, names) if words else None
                if cover:
                    edits.append((head[0], head[1], names[head[2]], ""))
                    edits.extend(cover)
                    used.add(head[2])
                    for a, b, _sym, _p in cover:
                        used.add(tuple(w for _x, _y, w in _words(reading, a, b) if w not in _POWER_WORDS))
        k = reading.find("=", k + 1)
    if not edits:
        return reading
    taken = {(a, b) for a, b, _s, _p in edits}
    for a, b, words in heads:  # a value stated for a quantity a word formula uses: its head is the same symbol
        if words in used and (a, b) not in taken:
            edits.append((a, b, names[words], ""))
    chars = list(reading)
    for a, b, symbol, power in edits:
        _put(chars, a, b, symbol, power)
    return "".join(chars)
