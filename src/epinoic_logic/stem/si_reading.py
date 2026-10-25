"""The SI reading of the prose arithmetic extractor and the core pack (docs/STEM_DESIGN.md, section 12).

``branches.quant`` reads the prose relations of a report (per cent changes, folds, shares, totals,
dated series) and ``branches.packs.CorePack`` reads its quotations, chronology and self-reports.
Both take a :class:`QuantReading`. The default reading, ``branches.quant.GENERAL``, is today's
code path byte for byte, and every non-STEM branch keeps it. The three STEM branches run
``CorePack(reading=SI_READING)``, which changes only how the text is read:

* **Scale words.** Only spelled-out scale words (``thousand``, ``million``, ``billion``,
  ``trillion``, ``quadrillion``, ``bn``) scale a figure. ``m``, ``k``, ``K``, ``M``, ``A`` and
  ``g`` are units, never scales, so ``500 mm to 2 m`` and ``300 K`` are read as written.
* **Units.** A figure followed by a unit symbol is read through :mod:`.units` into an exact SI
  value and a dimension (:func:`si_unit`). Two figures pair only when their dimensions agree
  (``500 g to 1.0 kg`` is a doubling); different dimensions, and a relative change on an
  offset temperature scale (°C, °F), are undecided with the reason named by the extractor.
* **Numbers.** Scientific notation (``1.5e-6``, ``6.67 × 10⁻¹¹``) is read exactly through
  :func:`.numbers.scan_number` (:func:`si_number`); a figure may carry a sign, and the view maps
  U+2212 to ``-``, so a signed change is honoured. Repeated folds are read by the extractor
  (``halved twice`` is a factor of 1/4).
* **Views.** Every view is a same-length copy of the text, so offsets never move:

  - :func:`si_quant_view`: the reading view with every relation-bearing math span (LaTeX, a
    math run, verbal arithmetic, chemistry, code, tables) masked by a placeholder. The
    extractor sees only prose relations and ``StemPack`` only math relations, so one statement
    is never checked twice. Quantities (``500 g``) stay readable;
  - :func:`si_prose_view`: the document's prose view (math, code and quantities masked), for
    chronology (``1500 K`` is never a year), self-certification and sentence reading;
  - :func:`si_quote_view`: the original text with code masked, for quotation reading.

  All three mask an inch or arcsecond mark attached to a number (``12″``, ``0.5"``), so it is
  never read as a quotation mark (:func:`mask_number_marks`).
* **Statements.** Sentences are the STEM segmenter's statements (:func:`si_statements`), so a
  finding's paragraph and statement numbers match the STEM claim ids ``s<paragraph>.<n>``.

This module imports nothing from ``branches`` or ``channel`` (design section 3.3); it holds the
reading's type, the SI constant and the SI helper functions. Nothing here evaluates text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from typing import Optional

from .document import StemDocument, build_document
from .limits import PROFILES, profile_for
from .normalize import masked_view, reading_view
from .numbers import scan_number
from .units import UNITS, Dimension, dimension_name, parse_unit

__all__ = [
    "QuantReading", "SI_READING", "SI_SCALE_UNIT", "SI_SCALES", "SiUnit", "mask_number_marks", "si_digits_pattern", "si_number", "si_prose_view",
    "si_quant_view", "si_quote_view", "si_statements", "si_unit", "si_unit_pattern",
]


@dataclass(frozen=True)
class QuantReading:
    """How ``branches.quant`` and ``CorePack`` read a text. Frozen and hashable: it is part of the
    extractor's cache key. ``si`` switches every SI rule of the module docstring on; ``profile``
    is the STEM profile key the views and statements are read under (``stem`` by default)."""

    name: str
    si: bool = False
    profile: str = ""

    def for_profile(self, key: Optional[str]) -> "QuantReading":
        """This reading for one subject profile. The general reading ignores the profile; the SI
        reading falls back to the ``stem`` profile for a key that is not a STEM profile."""
        if not self.si:
            return self
        key = key if key in PROFILES else "stem"
        return self if key == self.profile else replace(self, profile=key)


SI_READING = QuantReading(name="si", si=True, profile="stem")

#: scale words of the SI reading: spelled out only (``m``, ``k`` are units here)
SI_SCALE_UNIT = r"quadrillion|trillion|billion|million|thousand|bn"
SI_SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "bn": 10**9, "trillion": 10**12, "quadrillion": 10**15}

#: span kinds whose content is maths the STEM pack decides (masked from the prose extractor)
_MATH_KINDS = frozenset({"code_block", "code_inline", "latex_display", "latex_inline", "chem", "math_run", "verbal", "table"})
_CODE_KINDS = frozenset({"code_block", "code_inline"})
#: marks that read as inches, arcminutes or arcseconds right after a digit
_PRIMES = frozenset("″′")
_PARA_BREAK_RE = re.compile(r"\n[ \t\r]*\n")
#: views are as long as the answer (up to 400,000 characters), so few are kept
_MAX_VIEW_CACHE = 16


def _doc(text: str, profile: str) -> StemDocument:
    return build_document(text, None, profile)


def _ranges(doc: StemDocument, kinds: frozenset[str]) -> list[tuple[int, int]]:
    return [(sp.start, sp.end) for sp in doc.spans.spans if sp.kind in kinds]


def mask_number_marks(text: str) -> str:
    """``text`` (same length) with every inch or arcsecond mark attached to a number masked: a
    prime or double prime (``″``, ``′``) right after a digit, and a straight double mark right
    after a digit when no quotation is open before it in its paragraph (an even number of
    straight double marks precede it), so ``12" long`` is a measurement while the closing mark of
    ``"... in 1802"`` stays a quotation mark."""
    if not text or not any(ch in text for ch in ('"', "″", "′")):
        return text
    out = list(text)
    starts = {m.end() for m in _PARA_BREAK_RE.finditer(text)}
    open_marks = 0
    for i, ch in enumerate(text):
        if i in starts:
            open_marks = 0  # a blank line ends the paragraph
        if ch in _PRIMES and i > 0 and text[i - 1].isdigit():
            out[i] = "X"
        elif ch == '"':
            if i > 0 and text[i - 1].isdigit() and open_marks % 2 == 0:
                out[i] = "X"
            else:
                open_marks += 1
    return "".join(out)


@lru_cache(maxsize=_MAX_VIEW_CACHE)
def si_quant_view(text: str, profile: str = "stem") -> str:
    """The extractor's view: the reading view with relation-bearing maths and code masked and
    number marks masked (see the module docstring). Same length as ``text``."""
    doc = _doc(text, profile)
    return mask_number_marks(masked_view(reading_view(text), _ranges(doc, _MATH_KINDS)))


@lru_cache(maxsize=_MAX_VIEW_CACHE)
def si_prose_view(text: str, profile: str = "stem") -> str:
    """The document's prose view (maths, code and quantities masked, markup blanked) with number
    marks masked. Same length as ``text``."""
    doc = _doc(text, profile)
    prose = doc.prose if len(doc.prose) == len(text) else text
    return mask_number_marks(prose)


@lru_cache(maxsize=_MAX_VIEW_CACHE)
def si_quote_view(text: str, profile: str = "stem") -> str:
    """The quotation view: the original characters with code masked and number marks masked, so
    a string literal in code and an inch mark are never quotations. Same length as ``text``."""
    doc = _doc(text, profile)
    return mask_number_marks(masked_view(text, _ranges(doc, _CODE_KINDS)))


@lru_cache(maxsize=_MAX_VIEW_CACHE)
def si_statements(text: str, profile: str = "stem") -> tuple[tuple[int, int, int, int], ...]:
    """``(paragraph, statement number, start, end)`` of every statement of ``text`` that is not
    code, in document order: the STEM segmenter's statements, so ``(p, n)`` is claim ``s<p>.<n>``.
    The merged tail (``s.tail``) has number 0."""
    doc = _doc(text, profile)
    return tuple((st.paragraph, st.index, st.start, st.end) for st in doc.statements if st.kind != "code")


# ------------------------------------------------------------------------------------------- numbers

_SUPER = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def si_digits_pattern() -> str:
    """Regex alternation (no groups) of a figure in scientific notation: ``1.5e-6``, ``6.0E3``,
    ``6.67 × 10⁻¹¹``, ``3.0 x 10^8``, ``1.2×10^{6}``, ``1.2*10**6``. Exponents of one or two
    digits; :func:`si_number` reads the value exactly and enforces the bounds."""
    mant = r"(?<![\d.])\d+(?:\.\d+)?"  # never starting inside a digit run: one attempt per run keeps every pattern on it linear
    exp = rf"(?:\^\{{?-?\d{{1,2}}\}}?|\*\*-?\d{{1,2}}|⁻?[{_SUPER}]{{1,2}})"
    return rf"{mant}(?:[eE][-+]?\d{{1,2}}(?![\d.])|\s?[×xX*·]\s?10{exp}(?![\d{_SUPER}]))"


def si_number(num: str) -> Optional[Fraction]:
    """The exact value of a figure as the SI reading writes it (a sign, scientific notation,
    thousands groups, a decimal), or None when it is not one numeral within the front end's bounds."""
    s = reading_view(num.strip())
    sign = 1
    if s.startswith(("-", "+")):
        sign = -1 if s[0] == "-" else 1
        s = s[1:].lstrip()
    if not s or not (s[0].isdigit() or s[0] == "."):
        return None
    scan = scan_number(s, 0, orig=s)
    if scan is None or scan.number is None or scan.end != len(s):
        return None
    return sign * scan.number.value


# --------------------------------------------------------------------------------------------- units


@dataclass(frozen=True)
class SiUnit:
    """A unit read for the prose extractor: its exact SI factor (None when the table has no exact
    rational factor, as for the degree), its dimension, and whether it is an offset scale."""

    text: str
    factor: Optional[Fraction]
    dim: Dimension
    affine: bool = False

    @property
    def dimension(self) -> str:
        return dimension_name(self.dim)


#: prefixes the prose extractor accepts in front of a unit symbol (the rare ones are left out so
#: '10 am' is never an attometre)
_PREFIXES = ("da", "T", "G", "M", "k", "h", "d", "c", "m", "µ", "μ", "u", "n", "p")
#: unit symbols the prose extractor never reads after a figure: the tonne (profile-bound), the
#: bare M (molar or mega by profile), the per cent sign (a per-cent figure of its own)
_SKIP = frozenset({"t", "M", "%"})
_EXP = rf"(?:⁻?[{_SUPER}]{{1,2}}|\^\{{?-?\d\}}?|\*\*-?\d)"


@lru_cache(maxsize=8)
def si_unit_pattern(tonne: bool = False) -> str:
    """Case-sensitive regex (no groups) of a unit expression after a figure: up to four atoms of
    the unit table (an optionally prefixed symbol with an optional exponent) joined by a space, a
    middle dot or a slash. Each atom must end the word, so 'm' never starts 'marks'. Wrap it in
    ``(?-i:...)`` inside a case-insensitive pattern; :func:`si_unit` validates the match."""
    atoms: set[str] = set()
    for sym, u in UNITS.items():
        if sym in _SKIP and not (sym == "t" and tonne):
            continue
        atoms.add(sym)
        if u.prefixable:
            for p in _PREFIXES:
                atoms.add(p + sym)
    alt = "|".join(re.escape(a) for a in sorted(atoms, key=lambda a: (-len(a), a)))
    atom = rf"(?:{alt}){_EXP}?(?![A-Za-zµμΩÅ°{_SUPER}])"
    return rf"{atom}(?:(?:\s?[/·]\s?| ){atom}){{0,3}}"


@lru_cache(maxsize=1024)
def si_unit(text: Optional[str], profile: str = "stem") -> Optional[SiUnit]:
    """The SI reading of a unit expression after a figure, or None when it is not one the table
    reads unambiguously (unknown atoms, two readings that disagree)."""
    if not text:
        return None
    prof = profile_for(profile if profile in PROFILES else "stem")
    expr = parse_unit(text.strip(), bare_m=prof.bare_m, tonne=prof.tonne)
    if expr is None or not expr.known:
        return None
    dims = {r.dim for r in expr.readings}
    factors = {r.factor for r in expr.readings}
    if len(dims) != 1 or len(factors) != 1:
        return None
    reading = expr.readings[0]
    if reading.dim is None:
        return None
    return SiUnit(text=text.strip(), factor=reading.factor, dim=reading.dim, affine=reading.affine is not None)

