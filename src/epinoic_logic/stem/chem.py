"""Chemical formulas and equations (section 4.8 of docs/STEM_DESIGN.md).

Read in the chemistry, biology and ESS profiles (and the multi-science ``stem`` profile):

* formulas from element symbols of the periodic table (symbols only: no masses are held
  here, molar masses are data and go to the evidence service), counts as subscripts or
  digits (``H₂O``, ``H2O``, ``H_2O``, ``H_{2}O``), parenthesised or bracketed groups nested
  at most ``max_chem_group_depth`` deep (``Ca(OH)₂``), hydrate dots (``CuSO₄·5H₂O``);
* charges ``²⁺``, ``⁻``, ``^{2+}``, ``^-`` and a glued ASCII charge at the end of a species:
  digits before the sign after ``]`` are the charge (``[Cu(NH3)4]2+``); with two or more digits
  the last one is the charge (``SO42-`` is SO₄²⁻, ``Cr2O72-`` is Cr₂O₇²⁻); a single digit is the
  charge of a one-element ion (``Fe2+``, ``Al3+``, ``O2-``) and a count otherwise (``NH4+``,
  ``NO3-``, ``H3O+``); a state symbol may follow (``Fe2+(aq)``); electrons ``e⁻``;
* state symbols ``(s) (l) (g) (aq)``, which are read and ignored;
* arrows ``→``, ``⇌``, ``->``, ``<=>``, ``\\rightarrow``, ``\\rightleftharpoons``;
  coefficients as integers, decimals or fractions (``½O₂``, ``1/2 O2``).

Isotope notation, an unknown element symbol (``Ch₄``), a bound exceeded (species per side,
atoms per species, group depth) make the equation unreadable: ST-CHEM-001 with the reason.
:func:`find_equations` locates equations in a line by their arrow and the species around
it, so ``For 2H₂ + O₂ → 2H₂O, burning ...`` yields ``2H₂ + O₂ → 2H₂O``.

This module reads structure only. It reports, per species, the atoms of one formula unit
and the charge; whether an equation balances is decided by the engine (stage ``checks``
pins the coefficients and defines a tally per element and side).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from .limits import DEFAULT_LIMITS, StemLimits
from .numbers import SUBSCRIPT_DIGITS, SUPERSCRIPT_DIGITS, VULGAR_FRACTIONS, is_ascii_digit

__all__ = ["ARROWS", "ELEMENTS", "ChemEquation", "Species", "canonical_formula", "find_equations", "latex_to_chem", "parse_equation", "parse_species"]

ELEMENTS = frozenset("""
H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag
Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa
U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
""".split())

#: arrow spellings -> canonical arrow
ARROWS = {"→": "→", "⟶": "→", "->": "→", "-->": "→", "⇌": "⇌", "<=>": "⇌", "⇄": "⇌", "↔": "⇌", "\\rightarrow": "→", "\\to": "→",
          "\\longrightarrow": "→", "\\rightleftharpoons": "⇌", "\\leftrightarrows": "⇌"}
_STATES = ("(aq)", "(s)", "(l)", "(g)")
_SUP_SIGN = {"⁺": 1, "⁻": -1}
_MAX_SPECIES_CHARS = 80
_MAX_LINE_SCAN = 4000


@dataclass(frozen=True)
class Species:
    """One species as written: ``coefficient`` (1 when none is written), the atoms of one
    formula unit (element -> count), the charge, the state symbol, and offsets."""

    text: str
    coefficient: Fraction
    atoms: tuple[tuple[str, int], ...]
    charge: int = 0
    state: str = ""
    electron: bool = False
    start: int = 0
    end: int = 0
    coefficient_written: bool = False

    @property
    def formula(self) -> str:
        return "".join(f"{el}{n if n != 1 else ''}" for el, n in self.atoms) if not self.electron else "e"


@dataclass(frozen=True)
class ChemEquation:
    """``left arrow right``. ``error`` (with ``code`` ST-CHEM-001) is set when the equation is
    recognised by its arrow but cannot be read; ``left``/``right`` are then what could be read."""

    text: str
    left: tuple[Species, ...]
    right: tuple[Species, ...]
    arrow: str
    start: int
    end: int
    error: str = ""
    code: str = ""

    @property
    def readable(self) -> bool:
        return not self.error and bool(self.left) and bool(self.right)

    def elements(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for sp in self.left + self.right:
            for el, _n in sp.atoms:
                seen.setdefault(el, None)
        return tuple(seen)


class _ChemError(Exception):
    pass


def _count(s: str, i: int) -> tuple[int, int]:
    """A count after an element or group: subscript digits, ASCII digits, ``_2``, ``_{2}``. Returns (end, count) (count 1 if none)."""
    n = len(s)
    if i < n and s[i] in SUBSCRIPT_DIGITS:
        j = i
        while j < n and s[j] in SUBSCRIPT_DIGITS and j - i < 4:
            j += 1
        return j, int("".join(SUBSCRIPT_DIGITS[c] for c in s[i:j]))
    if i < n and is_ascii_digit(s[i]):
        j = i
        while j < n and is_ascii_digit(s[j]) and j - i < 4:
            j += 1
        return j, int(s[i:j])
    if i + 1 < n and s[i] == "_":
        if s[i + 1] == "{":
            j = i + 2
            while j < n and is_ascii_digit(s[j]) and j - i < 6:
                j += 1
            if j > i + 2 and j < n and s[j] == "}":
                return j + 1, int(s[i + 2:j])
            raise _ChemError("an unreadable subscript")
        if is_ascii_digit(s[i + 1]):
            j = i + 1
            while j < n and is_ascii_digit(s[j]) and j - i < 4:
                j += 1
            return j, int(s[i + 1:j])
    return i, 1


def _charge(s: str, i: int) -> tuple[int, Optional[int]]:
    """A charge at ``i``: ``²⁺``, ``⁻``, ``³⁺``, ``^{2+}``, ``^2+``, ``^+``, ``^{-}``. Returns (end, charge) or (i, None)."""
    n = len(s)
    j = i
    digits = ""
    while j < n and s[j] in SUPERSCRIPT_DIGITS and j - i < 3:
        digits += SUPERSCRIPT_DIGITS[s[j]]
        j += 1
    if j < n and s[j] in _SUP_SIGN:
        return j + 1, _SUP_SIGN[s[j]] * (int(digits) if digits else 1)
    if digits:
        return i, None
    if i < n and s[i] == "^":
        k = i + 1
        brace = k < n and s[k] == "{"
        if brace:
            k += 1
        e = k
        while e < n and is_ascii_digit(s[e]) and e - k < 3:
            e += 1
        num = s[k:e]
        if e < n and s[e] in "+-−":
            sign = 1 if s[e] == "+" else -1
            e += 1
            if brace:
                if e < n and s[e] == "}":
                    e += 1
                else:
                    return i, None
            return e, sign * (int(num) if num else 1)
    return i, None


def _formula(s: str, i: int, end: int, depth: int, limits: StemLimits) -> tuple[int, dict[str, int]]:
    """Atoms of a formula part from ``i`` up to a stop character; groups recurse (bounded depth)."""
    atoms: dict[str, int] = {}
    j = i
    while j < end:
        ch = s[j]
        if "A" <= ch <= "Z":
            k = j + 1
            if k < end and "a" <= s[k] <= "z":
                k += 1
            sym = s[j:k]
            if sym not in ELEMENTS:
                raise _ChemError(f"unknown element symbol {sym!r}")
            k, cnt = _count(s, k)
            atoms[sym] = atoms.get(sym, 0) + cnt
            j = k
            continue
        if ch in "([":
            if s.startswith(_STATES, j):
                break  # a state symbol ends the formula
            if depth + 1 > limits.max_chem_group_depth:
                raise _ChemError(f"groups nested deeper than {limits.max_chem_group_depth}")
            close = ")" if ch == "(" else "]"
            k, inner = _formula(s, j + 1, end, depth + 1, limits)
            if k >= end or s[k] != close:
                raise _ChemError("an unbalanced group")
            k, cnt = _count(s, k + 1)
            for el, c in inner.items():
                atoms[el] = atoms.get(el, 0) + c * cnt
            j = k
            continue
        break
    for el, c in atoms.items():
        if c > limits.max_atoms_per_species:
            raise _ChemError(f"{c} atoms of {el} in one species (bound {limits.max_atoms_per_species})")
    return j, atoms


def _coefficient(s: str, i: int, end: int) -> tuple[int, Fraction, bool]:
    if i < end and s[i] in VULGAR_FRACTIONS:
        a, b = VULGAR_FRACTIONS[s[i]]
        return i + 1, Fraction(a, b), True
    j = i
    while j < end and is_ascii_digit(s[j]) and j - i < 4:
        j += 1
    if j == i:
        return i, Fraction(1), False
    if j < end and s[j] == "/" and j + 1 < end and is_ascii_digit(s[j + 1]):
        k = j + 1
        while k < end and is_ascii_digit(s[k]) and k - j < 4:
            k += 1
        return k, Fraction(int(s[i:j]), int(s[j + 1:k])), True
    if j < end and s[j] == "." and j + 1 < end and is_ascii_digit(s[j + 1]):
        k = j + 1
        while k < end and is_ascii_digit(s[k]) and k - j < 4:
            k += 1
        return k, Fraction(int(s[i:j] + s[j + 1:k]), 10 ** (k - j - 1)), True
    return j, Fraction(int(s[i:j])), True


def parse_species(text: str, *, start: int = 0, limits: StemLimits = DEFAULT_LIMITS, allow_coefficient: bool = True) -> Species:
    """Parse one species (``2H₂O(l)``, ``Fe²⁺(aq)``, ``CuSO₄·5H₂O``, ``½O₂``, ``2e⁻``,
    ``SO_4^{2-}``). Raises ``ValueError`` with the reason when it cannot be read (callers turn
    that into ST-CHEM-001); never evaluates the text."""
    s = text.strip()
    if not s:
        raise ValueError("an empty species")
    if len(s) > _MAX_SPECIES_CHARS:
        raise ValueError("a species longer than the bound")
    try:
        return _species(s, start, limits, allow_coefficient)
    except _ChemError as exc:
        raise ValueError(str(exc)) from None


def _species(s: str, start: int, limits: StemLimits, allow_coefficient: bool) -> Species:
    n = len(s)
    i = 0
    if s[0] in SUPERSCRIPT_DIGITS or s[0] in SUBSCRIPT_DIGITS or s.startswith("^{") or s.startswith("_{"):
        raise _ChemError("isotope notation")
    coef, written = Fraction(1), False
    if allow_coefficient:
        i, coef, written = _coefficient(s, 0, n)
        while i < n and s[i] == " ":
            i += 1
    if i < n and s[i] == "e" and (i + 1 == n or s[i + 1] in "⁻-^"):
        j = i + 1
        if j < n:
            j2, ch = _charge(s, j)
            if ch is None and s[j] == "-":
                j2, ch = j + 1, -1
            if ch != -1:
                raise _ChemError("an electron with a charge other than -1")
            j = j2
        if j != n:
            raise _ChemError(f"unexpected text after an electron: {s[j:]!r}")
        return Species(text=s, coefficient=coef, atoms=(), charge=-1, electron=True, start=start, end=start + n, coefficient_written=written)
    if i >= n or not ("A" <= s[i] <= "Z" or s[i] in "(["):
        raise _ChemError(f"no formula in {s!r}")
    s = _ascii_charge(s, i)
    n = len(s)
    atoms: dict[str, int] = {}
    j, part = _formula(s, i, n, 0, limits)
    for el, c in part.items():
        atoms[el] = atoms.get(el, 0) + c
    # hydrate dots: CuSO₄·5H₂O
    while j < n and s[j] in "·•.*":
        k, mult, _w = _coefficient(s, j + 1, n)
        if mult.denominator != 1:
            raise _ChemError("a fractional hydrate count")
        k2, part = _formula(s, k, n, 0, limits)
        if k2 == k:
            raise _ChemError("a hydrate dot with no formula after it")
        for el, c in part.items():
            atoms[el] = atoms.get(el, 0) + c * mult.numerator
        j = k2
    charge = 0
    state = ""
    # charge and state in either order
    for _ in range(2):
        k, ch = _charge(s, j)
        if ch is not None:
            charge = ch
            j = k
            continue
        matched = False
        for st in _STATES:
            if s.startswith(st, j):
                state = st[1:-1]
                j += len(st)
                matched = True
                break
        if matched:
            continue
        if j < n and s[j] in "+-" and j + 1 == n:
            charge = 1 if s[j] == "+" else -1
            j += 1
        break
    if j != n:
        raise _ChemError(f"unexpected text {s[j:j + 12]!r} in a species")
    if not atoms:
        raise _ChemError("a species with no atoms")
    ordered = tuple(sorted(atoms.items(), key=lambda kv: (kv[0] != "C", kv[0] != "H", kv[0])))
    return Species(text=s, coefficient=coef, atoms=ordered, charge=charge, state=state, start=start, end=start + n, coefficient_written=written)


def _ascii_charge(s: str, i: int) -> str:
    """``s`` with a glued ASCII charge at its end rewritten as ``^{n±}`` (see the module docstring);
    unchanged when it has none or already writes the charge explicitly."""
    if "^" in s:
        return s
    end = len(s)
    tail = ""
    for st in _STATES:
        if s.endswith(st) and end - len(st) > i:
            tail, end = st, end - len(st)
            break
    if end - 1 <= i or s[end - 1] not in "+-−":
        return s
    sign = "+" if s[end - 1] == "+" else "-"
    a = end - 1
    while a > i and is_ascii_digit(s[a - 1]) and end - 1 - a < 4:
        a -= 1
    digits = s[a:end - 1]
    if not digits:
        return s[:end - 1] + "^{" + sign + "}" + tail
    before = s[a - 1] if a - 1 >= i else ""
    if not (before.isalpha() or before in ")]"):
        return s
    if before == "]":
        count, charge = "", digits
    elif len(digits) >= 2:
        count, charge = digits[:-1], digits[-1]
    elif s[i:a] in ELEMENTS:
        count, charge = "", digits  # a one-element ion: Fe2+, O2-
    else:
        count, charge = digits, ""  # a count, then a single charge: NH4+, NO3-
    return s[:a] + count + "^{" + charge + sign + "}" + tail


_SUB_OUT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUP_OUT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def canonical_formula(text: str) -> str:
    """One spelling of a formula as written: counts as subscript digits (``H_2O``, ``H_{2}O``,
    ``H2O`` -> ``H₂O``), charges as superscripts (``SO_4^{2-}`` -> ``SO₄²⁻``, ``Na+`` -> ``Na⁺``).
    The order of the written symbols is kept, so ``[N₂]`` and ``[\\mathrm{N_2}]`` name one symbol."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "_":
            j = i + 1
            if j < n and text[j] == "{":
                k = text.find("}", j)
                if k < 0:
                    out.append(text[i:])
                    break
                out.append(text[j + 1:k].translate(_SUB_OUT))
                i = k + 1
                continue
            k = j
            while k < n and is_ascii_digit(text[k]):
                k += 1
            out.append(text[j:k].translate(_SUB_OUT))
            i = k
            continue
        if ch == "^":
            j = i + 1
            if j < n and text[j] == "{":
                k = text.find("}", j)
                if k < 0:
                    out.append(text[i:])
                    break
                out.append(text[j + 1:k].replace("−", "-").translate(_SUP_OUT))
                i = k + 1
                continue
            k = j
            while k < n and (is_ascii_digit(text[k]) or text[k] in "+-−"):
                k += 1
            out.append(text[j:k].replace("−", "-").translate(_SUP_OUT))
            i = k
            continue
        if is_ascii_digit(ch) and out and (out[-1][-1:].isalpha() or out[-1][-1:] in ")]₀₁₂₃₄₅₆₇₈₉"):
            out.append(ch.translate(_SUB_OUT))
            i += 1
            continue
        if ch in "+-" and i == n - 1 and out:
            out.append(ch.translate(_SUP_OUT))
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def latex_to_chem(text: str) -> str:
    """A plain chemistry reading of LaTeX: ``\\mathrm{}``/``\\text{}`` wrappers and their braces are
    dropped, ``\\rightarrow`` and kin become arrows, spacing commands become spaces. Subscript
    and superscript groups (``_{2}``, ``^{2+}``) are kept for :func:`parse_species`. Bounded by
    the input length."""
    out: list[str] = []
    i = 0
    n = len(text)
    wrapper_depths: list[int] = []
    depth = 0
    while i < n:
        if text.startswith("\\", i):
            matched = False
            for w in ("\\mathrm{", "\\text{", "\\textrm{", "\\rm{", "\\ce{"):
                if text.startswith(w, i):
                    depth += 1
                    wrapper_depths.append(depth)
                    i += len(w)
                    matched = True
                    break
            if matched:
                continue
            for a in sorted((k for k in ARROWS if k.startswith("\\")), key=len, reverse=True):
                if text.startswith(a, i) and not (i + len(a) < n and text[i + len(a)].isalpha()):
                    out.append(" " + ARROWS[a] + " ")
                    i += len(a)
                    matched = True
                    break
            if matched:
                continue
            if i + 1 < n and text[i + 1] in ",;:! ":
                out.append(" ")
                i += 2
                continue
            if text.startswith("\\cdot", i):
                out.append("·")
                i += 5
                continue
            out.append(text[i])
            i += 1
            continue
        ch = text[i]
        if ch == "{":
            depth += 1
            out.append(ch)
        elif ch == "}":
            if wrapper_depths and wrapper_depths[-1] == depth:
                wrapper_depths.pop()
            else:
                out.append(ch)
            depth -= 1
        elif ch == "~":
            out.append(" ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _split_arrow(text: str) -> Optional[tuple[int, int, str]]:
    """The first arrow of ``text`` (longest spelling first): ``(start, end, canonical)``."""
    best: Optional[tuple[int, int, str]] = None
    for a in sorted(ARROWS, key=len, reverse=True):
        k = text.find(a)
        if k >= 0 and (best is None or k < best[0]):
            if a.startswith("\\") and k + len(a) < len(text) and text[k + len(a)].isalpha():
                continue
            best = (k, k + len(a), ARROWS[a])
    return best


def parse_equation(text: str, *, start: int = 0, limits: StemLimits = DEFAULT_LIMITS) -> Optional[ChemEquation]:
    """Parse ``text`` as one equation (``2H₂ + O₂ → 2H₂O``). None when it has no arrow.
    An unreadable species or a bound exceeded gives an equation with ``error`` set (ST-CHEM-001)."""
    arrow = _split_arrow(text)
    if arrow is None:
        return None
    a, b, canon = arrow
    sides: list[list[Species]] = []
    error = ""
    for part, base in ((text[:a], start), (text[b:], start + b)):
        species: list[Species] = []
        for piece, off in _plus_split(part):
            if len(species) >= limits.max_species_per_side:
                error = error or f"more than {limits.max_species_per_side} species on one side"
                break
            try:
                species.append(parse_species(piece, start=base + off, limits=limits))
            except ValueError as exc:
                error = error or f"{piece.strip()!r}: {exc}"
        sides.append(species)
    if not error and (not sides[0] or not sides[1]):
        error = "an arrow without species on both sides"
    return ChemEquation(text=text, left=tuple(sides[0]), right=tuple(sides[1]), arrow=canon, start=start, end=start + len(text), error=error,
                        code="ST-CHEM-001" if error else "")


def _plus_split(part: str) -> list[tuple[str, int]]:
    """Split one side at ``+`` signs that separate species (a ``+`` with a space on either side,
    not a charge glued to a formula such as ``Na+`` before another ``+`` or at the end of the side)."""
    out: list[tuple[str, int]] = []
    n = len(part)
    seg_start = 0
    i = 0
    while i < n:
        ch = part[i]
        if ch == "+":
            prev_space = i == 0 or part[i - 1] == " "
            next_space = i + 1 >= n or part[i + 1] == " "
            if prev_space or next_space:
                glued_charge = not prev_space and next_space and _ends_formula(part[seg_start:i]) and (_next_is_plus(part, i + 1) or not part[i + 1:].strip())
                if not glued_charge:  # 'Na+ + Cl-' and a last 'Zn2+' keep their charge
                    piece = part[seg_start:i]
                    if piece.strip():
                        out.append((piece, seg_start))
                    seg_start = i + 1
        i += 1
    piece = part[seg_start:]
    if piece.strip():
        out.append((piece, seg_start))
    return out


def _ends_formula(piece: str) -> bool:
    p = piece.rstrip()
    return bool(p) and (p[-1].isalnum() or p[-1] in "₀₁₂₃₄₅₆₇₈₉)]")


def _next_is_plus(part: str, i: int) -> bool:
    j = i
    while j < len(part) and part[j] == " ":
        j += 1
    return j < len(part) and part[j] == "+"


def _shaped(word: str) -> bool:
    """A word that looks like a species (for locating an equation in prose): optional
    coefficient, then upper-case element-shaped letters, digits, subscripts, groups, charges,
    states, or an electron."""
    w = word
    if not w:
        return False
    i = 0
    n = len(w)
    while i < n and (is_ascii_digit(w[i]) or w[i] in VULGAR_FRACTIONS or w[i] in "./"):
        i += 1
    if i >= n:
        return False
    if w[i] == "e" and (i + 1 == n or w[i + 1] in "⁻-^"):
        return True
    if not ("A" <= w[i] <= "Z" or w[i] in "(["):
        return False
    prev_upper = False
    has_upper = False
    while i < n:
        c = w[i]
        state = next((st for st in _STATES if w.startswith(st, i)), None)
        if state is not None:
            i += len(state)
            prev_upper = False
            continue
        if "A" <= c <= "Z":
            prev_upper = True
            has_upper = True
        elif "a" <= c <= "z":
            if not prev_upper:
                return False
            prev_upper = False
        elif c in "0123456789₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻()[]·_{}^+-":
            prev_upper = False
        else:
            return False
        i += 1
    return has_upper


def find_equations(line: str, offset: int = 0, *, limits: StemLimits = DEFAULT_LIMITS) -> list[ChemEquation]:
    """Equations in one line of prose, located by their arrows: species-shaped words joined by
    ``+`` on both sides of an arrow. A word that is not species-shaped ends a side; trailing
    punctuation and an unmatched bracket at either end are left out. Offsets are absolute
    (``offset`` is the line's start)."""
    if len(line) > _MAX_LINE_SCAN:
        line = line[:_MAX_LINE_SCAN]
    words: list[tuple[str, int, int]] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == " ":
            i += 1
            continue
        j = i
        while j < n and line[j] != " ":
            j += 1
        words.append((line[i:j], i, j))
        i = j
    # split arrows glued to words ('A→B')
    split: list[tuple[str, int, int]] = []
    for w, a, b in words:
        arrow = _split_arrow(w)
        if arrow is not None and w not in ARROWS:
            k, e, _c = arrow
            if w[:k]:
                split.append((w[:k], a, a + k))
            split.append((w[k:e], a + k, a + e))
            if w[e:]:
                split.append((w[e:], a + e, b))
        else:
            split.append((w, a, b))
    words = split
    out: list[ChemEquation] = []
    used_until = -1
    for idx, (w, a, b) in enumerate(words):
        if w not in ARROWS or idx <= used_until:
            continue
        left = _side(words, idx, -1)
        right = _side(words, idx, 1)
        if left is None or right is None:
            continue
        (ls, _le), (_rs, re) = left, right
        _core, s_off, _x = _clean_span(*words[ls])
        _core2, _y, e_off = _clean_span(*words[re])
        text = line[s_off:e_off]
        eq = parse_equation(text, start=offset + s_off, limits=limits)
        if eq is not None:
            out.append(eq)
        used_until = re
    return out


def _clean_span(word: str, a: int, b: int) -> tuple[str, int, int]:
    """``word`` without trailing punctuation and without an unmatched bracket at either end, with its offsets."""
    w = word
    while w:
        if w[-1] in ".,;:!?":
            w, b = w[:-1], b - 1
        elif w[-1] == ")" and w.count(")") > w.count("("):
            w, b = w[:-1], b - 1
        elif w[0] == "(" and w.count("(") > w.count(")"):
            w, a = w[1:], a + 1
        else:
            break
    return w, a, b


def _clean(word: str) -> str:
    return _clean_span(word, 0, len(word))[0]


def _side(words: list[tuple[str, int, int]], arrow_idx: int, step: int) -> Optional[tuple[int, int]]:
    """Word indices ``(first, last)`` of the species list on one side of the arrow."""
    idx = arrow_idx + step
    first = last = None
    expect_species = True
    count = 0
    while 0 <= idx < len(words):
        w = words[idx][0]
        if expect_species:
            core = _clean(w)
            if not core or not _shaped(core):
                break
            if first is None:
                first = idx
            last = idx
            count += 1
            # punctuation glued to the word ends the side
            if step > 0 and w != core and w[-1] in ".,;:!?":
                break
            if step < 0 and w != core and w[0] == "(":
                break
            expect_species = False
        else:
            if w != "+":
                break
            expect_species = True
        idx += step
        if count > 32:
            break
    if first is None or last is None:
        return None
    return (min(first, last), max(first, last))
