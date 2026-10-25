"""Typed figures of source text: what a figure states, in which unit, to which precision and how exactly.

The translation layer reads the figures of the texts it may cite as sources (the claim, its supporting claims, the
supplied texts, the task record) into :class:`StatedFigure` records, deterministically. No text is executed: numerals
are read by the bounded STEM number scanner (:func:`epinoic_logic.stem.numbers.scan_number`) and a closed table of
number words, a written calculation by a closed arithmetic reader (:func:`written_calculation_value`: numerals,
``+ − × ÷``, parentheses, per cent, currency marks, the unit and scale words of an operand, LaTeX read as plain marks),
and every value is an exact :class:`~fractions.Fraction`.

Three uses:

* **Typed correspondence** (:func:`literal_matches`). An IR literal corresponds to a stated figure when the two values
  are equal as written, or after ONE explicit derivation that is recorded with the match: a percentage (per mille,
  percentage point, basis point) to its fraction (``20% = 20 x 1/100 = 1/5``), a scale word (``$13 billion = 13 x
  10^9``), or a unit conversion through the STEM unit table (``2 h = 120 min``) when the symbol the literal is compared
  with declares a unit. Decimal and rational spellings of one value agree (``0.2`` and ``1/5``) because both are exact
  fractions. A symbol whose meaning declares a reading (a dimensionless fraction, a percentage, a unit, a scale) admits
  only the derivations consistent with it: ``tax_rate = 20`` for "the tax rate is 20%" is a unit mismatch when the
  symbol is declared dimensionless, and ``tax_rate = 0.2`` is one when it is declared in per cent.
* **Stated exactness** (:func:`stated_exactness`). The wording around a figure decides how exactly it is stated, never
  the solver: an exactness cue ("exactly", "precisely", "without rounding", "not rounded", "unrounded", "without
  approximation") makes it ``exact``; a rounding cue ("to 2 decimal places", "3 s.f.", "to the nearest ten", "rounded
  down", "approximately", "about", "≈") makes it ``rounded`` with the tolerance the cue states (half a unit of the last
  written place when it states none); with neither it is ``unstated``. An approximation cue, a word or a sign, governs
  only the figure it is written against ("about 30", "0.33 approximately", "≈ 118"); governing another word or another
  figure ("think about it", "almost certain", "about 2 people think that x = 0.33", "x ≈ 1/3 so x = 0.33") it states
  nothing about the figure (:func:`_approximation_cues`). When cues of both kinds govern one figure the nearest cue decides;
  occurrences of one figure with conflicting readings are ``conflicting``. A figure written as the result of a
  calculation written before it, with no cue, is read from that calculation: ``exact`` when the calculation as
  written gives exactly that figure (``$2.00 − $0.40 = $1.60``), ``rounded`` to half a unit of its last written
  place when it gives a value the figure rounds (``−12.50 ÷ 18.75 = −0.67``), and otherwise (a calculation the
  reader cannot compute, or one the figure does not round) ``rounded`` by the convention of written calculation,
  a presumption the precision decision treats as weaker than a cue (:attr:`Exactness.by_convention`). The figure is
  such a result only when the calculation ENDS at its '=' (:func:`_calculation_run`) and the figure ends the
  expression: in "If x = 1/3 then x = 0.33", "x = 1/3 implies x = 0.33", "x × 3 = 1.00", "HR = 72" or "= 3 − 1" the
  sign equates the figure with a variable, a symbol or an expression that holds one, or the figure is an operand of
  a further expression, so the figure is that term's value and only its cues decide its exactness. A figure stated
  as rounded by a cue or by a calculation it rounds states the interval of its tolerance (:func:`stated_intervals`:
  "x is 0.33 to 2 decimal places" states [0.325, 0.335), in the reading the symbol declares); the numeral of a cue that
  states a precision is no figure and no end of a range (:func:`in_precision_cue`).
* **Sentence context** (:func:`sentence_of`): the sentence that holds a figure. A full stop ends a sentence before a
  capital or before a lower-case symbol that opens a statement ("Define b. n = 17.": :data:`_SYMBOL_START_RE`), never
  after an abbreviation. Whether a clause ASSERTS its figures (as
  coverage needs) is read by :mod:`.assertion`, clause by clause; :func:`is_definitional` is only the coarse keyword
  test of a whole sentence ("define", "let", "iff", "suppose", "arbitrary") and decides nothing in the pipeline.

A figure is located by its offsets in the ORIGINAL text, so every reading names the span it rests on.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Iterable, Literal, Optional, Sequence

__all__ = [
    "SourceText", "StatedFigure", "Exactness", "DeclaredReading", "Match",
    "figures_in", "stated_exactness", "declared_reading", "literal_matches", "tolerance_bounds",
    "sentence_of", "is_definitional", "fraction_text", "is_year_like", "TRIVIAL_VALUES", "written_calculation_value", "approximate_text",
    "in_precision_cue", "LOWER_CASE_ABBREVIATIONS", "stated_intervals", "rounded_intervals", "interval_derivation", "figure_stated_plainly",
    "interval_text",
]

SourceKind = Literal["claim", "supporting_claim", "supplied_text", "task"]
ExactnessKind = Literal["exact", "rounded", "unstated", "conflicting"]
RoundingMode = Literal["nearest", "down", "up"]

#: Values that are no stated figure of a source: zero, one and the powers of ten a percentage or a conversion brings in.
TRIVIAL_VALUES = frozenset({Fraction(0), Fraction(1), Fraction(10), Fraction(100), Fraction(1000)})
#: The longest figure-bearing text read (characters); a longer text is read up to this bound.
MAX_TEXT_CHARS = 400_000


@dataclass(frozen=True)
class SourceText:
    """A text the translation layer may cite as the source of a figure."""
    kind: SourceKind
    ident: str
    text: str


@dataclass(frozen=True)
class StatedFigure:
    """One figure as a source writes it. ``value`` is the signed value of the numeral as written (no unit and no scale
    applied); ``half_width`` is half a unit in its last written place, in its own unit (0 for an exact form: a fraction,
    a number word); ``unit_factor`` is the SI factor of its unit (percent 1/100), ``scale`` the multiplier of a scale word."""
    source_kind: SourceKind
    source_id: str
    start: int
    end: int
    written: str
    numeral: str
    value: Fraction
    has_point: bool
    places: int
    half_width: Fraction
    unit: Optional[str] = None
    unit_factor: Optional[Fraction] = None
    unit_dim: Optional[str] = None
    currency: Optional[str] = None
    scale: int = 1
    scale_word: Optional[str] = None
    word: bool = False

    @property
    def scaled(self) -> Fraction:
        return self.value if self.scale == 1 else self.value * self.scale

    @property
    def is_percent_like(self) -> bool:
        return self.unit in _RATIO_UNITS

    def where(self) -> str:
        """``claim c1 characters 30-34 ('0.33')``: the span a reading rests on, for diagnostics."""
        label = {"claim": "claim", "supporting_claim": "supporting claim", "supplied_text": "supplied text", "task": "task"}[self.source_kind]
        return f"{label} {self.source_id} characters {self.start}-{self.end} ({self.written!r})"


@dataclass(frozen=True)
class Exactness:
    """How exactly the wording states a figure. ``half_width`` (nearest) or ``step`` (down, up) is the tolerance in the
    figure's own unit; ``cue`` is the phrase that decided it, at ``cue_start``-``cue_end`` of the source text.
    ``computed`` is the exact value of the written calculation the figure is stated as the result of, when the reader
    could compute it; ``by_convention`` marks a rounded reading that rests only on the convention of written
    calculation (no cue, and no computed value the figure rounds), a presumption rather than a statement."""
    kind: ExactnessKind
    cue: Optional[str] = None
    cue_start: Optional[int] = None
    cue_end: Optional[int] = None
    mode: RoundingMode = "nearest"
    precision: Optional[str] = None
    half_width: Optional[Fraction] = None
    step: Optional[Fraction] = None
    by_convention: bool = False
    computed: Optional[Fraction] = None

    def describe(self) -> str:
        if self.kind == "exact":
            if self.computed is not None:
                return f"stated exactly: the written calculation {self.cue!r} gives exactly this value"
            return f"stated exactly ({self.cue!r})" if self.cue else "stated exactly"
        if self.kind == "rounded":
            if self.by_convention:
                gives = f" (as written it gives {approximate_text(self.computed)}, which this figure does not round)" if self.computed is not None else ""
                return f"the result of a written calculation{gives}, read to half a unit of its last place by convention"
            if self.computed is not None:
                return (f"rounded: the written calculation {self.cue!r} gives {approximate_text(self.computed)}, which this figure states to half a "
                        "unit of its last written place")
            return f"rounded{'' if self.mode == 'nearest' else ' ' + self.mode} ({self.cue!r}" + (f", {self.precision}" if self.precision else "") + ")"
        if self.kind == "conflicting":
            return "stated with conflicting exactness cues"
        return "stated with no exactness or rounding cue"


@dataclass(frozen=True)
class DeclaredReading:
    """The reading a symbol's meaning declares for its value: a dimensionless ``fraction``, a ``percent``, a measurement
    ``unit`` (SI ``factor`` and dimension), a ``scale`` word, or ``none``."""
    kind: Literal["none", "fraction", "percent", "unit"]
    factor: Optional[Fraction] = None
    dim: Optional[str] = None
    scale: int = 1
    text: str = ""


@dataclass(frozen=True)
class Match:
    """An IR literal tied to a stated figure: ``derivation`` says how (``as written``, ``20% = 20 x 1/100 = 1/5``)."""
    figure: StatedFigure
    derivation: str
    factor: Fraction = Fraction(1)


# ------------------------------------------------------------------ number words

_UNIT_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
               "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
               "nineteen": 19}
_TENS_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_FRACTION_WORDS = {"half": 2, "halves": 2, "third": 3, "thirds": 3, "quarter": 4, "quarters": 4, "fourth": 4, "fourths": 4,
                   "fifth": 5, "fifths": 5, "tenth": 10, "tenths": 10}
_NUMBER_WORD_RE = re.compile(
    r"(?<![\w-])(?:(?P<tens>" + "|".join(_TENS_WORDS) + r")(?:[-\s](?P<tunit>" + "|".join(k for k in _UNIT_WORDS if 0 < _UNIT_WORDS[k] < 10) + r"))?"
    r"|(?P<unit>" + "|".join(_UNIT_WORDS) + r")"
    r"|(?P<a>a|an))"
    r"(?:[-\s](?P<frac>" + "|".join(_FRACTION_WORDS) + r"))?(?![\w-])",
    re.IGNORECASE,
)
_SCALE_WORDS = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12, "bn": 10 ** 9, "mn": 10 ** 6}
_SCALE_RE = re.compile(r"\s*(?P<w>hundred|thousand|million|billion|trillion|bn|mn)s?(?![a-z])", re.IGNORECASE)

# ------------------------------------------------------------------ units around a numeral

#: Ratio units: written after a numeral, they make it a part of a hundred (thousand, ten thousand).
_RATIO_UNITS = {"%": Fraction(1, 100), "percent": Fraction(1, 100), "percentage point": Fraction(1, 100), "per mille": Fraction(1, 1000),
                "basis point": Fraction(1, 10_000)}
_RATIO_RE = re.compile(
    r"\s*(?:(?P<pct>%|per\s*-?\s*cent\b|percent\b|pc\b(?=\s|$|[.,;)]))(?:\s*(?P<pp>points?\b))?|(?P<ppt>percentage\s+points?\b|pp\b|p\.p\.)"
    r"|(?P<pm>‰|per\s+mill?e?\b)|(?P<bp>basis\s+points?\b|bps?\b))",
    re.IGNORECASE,
)
_CURRENCY_BEFORE_RE = re.compile(r"(?:US\$|A\$|C\$|NZ\$|HK\$|\$|£|€|¥|₹|₩)\s?$")
_CURRENCY_WORDS = ("dollars", "dollar", "pounds", "pound", "euros", "euro", "yen", "rupees", "krona", "kronor", "francs", "cents", "pence")
_UNIT_TOKEN_RE = re.compile(r"\s?(?P<u>[A-Za-zµμΩ°℃][A-Za-z0-9µμΩ°⁻¹²³⁴⁵⁶⁷⁸⁹⁰/·.^\-]{0,15})")
_SIGN_CHARS = "-−–"


def _unit_reading(token: str) -> Optional[tuple[str, Fraction, str]]:
    """``(unit text, SI factor, dimension name)`` of a unit written after a numeral, from the STEM unit table, or None."""
    token = token.rstrip(".,;:)").strip()
    if not token or len(token) > 16:
        return None
    from ..stem.units import dimension_name, parse_unit  # imported here: the STEM package imports adapters that import this layer
    try:
        expr = parse_unit(token)
    except Exception:  # an unreadable unit is no unit
        return None
    if expr is None or not expr.known or len(expr.readings) != 1:
        return None
    reading = expr.readings[0]
    if reading.dim is None or reading.factor is None:
        return None
    return token, reading.factor, dimension_name(reading.dim)


def _scan_numeral(text: str, i: int):
    from ..stem.numbers import scan_number  # see _unit_reading
    try:
        return scan_number(text, i, thousands_comma=True, scientific=True, decimal_comma=False)
    except Exception:  # a numeral the scanner cannot read is skipped
        return None


# ------------------------------------------------------------------ cues of exactness and rounding

_NUMWORD = r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_EXACT_CUE_RE = re.compile(r"\bexact(?:ly)?\b|\bprecisely\b|\bwithout\s+(?:any\s+)?rounding\b|\bnot\s+(?:been\s+)?rounded\b|\bunrounded\b"
                           r"|\bno\s+rounding\b|\bin\s+full\b|\bwithout\s+(?:any\s+)?approximation\b|\bno\s+approximation\b"
                           r"|\bnot\s+(?:an?\s+)?approximat(?:e|ed|ely|ion)\b", re.IGNORECASE)
_DP_CUE_RE = re.compile(r"(?:\b(?:to|correct\s+to|accurate\s+to|rounded\s+to|given\s+to)\s+)?\(?(?P<n>" + _NUMWORD
                        + r")\s*(?:decimal\s+places?|d\.\s?p\.?|dp)(?![a-z])\)?", re.IGNORECASE)
_SF_CUE_RE = re.compile(r"(?:\b(?:to|correct\s+to|accurate\s+to|rounded\s+to|given\s+to)\s+)?\(?(?P<n>" + _NUMWORD
                        + r")\s*(?:significant\s+(?:figures?|digits?)|sig\.?\s*figs?\.?|s\.\s?f\.?|sf)(?![a-z])\)?", re.IGNORECASE)
_NEAREST_CUE_RE = re.compile(r"\b(?:rounded\s+)?to\s+the\s+nearest\s+(?P<what>whole\s+number|integer|unit|ten|tenth|hundred|hundredth|thousand|"
                             r"thousandth|million|\d[\d,]*(?:\.\d+)?)s?\b", re.IGNORECASE)
_DIRECTED_CUE_RE = re.compile(r"\brounded\s+(?P<dir>up|down)\b|\b(?P<trunc>truncated)\b", re.IGNORECASE)
_ROUNDED_CUE_RE = re.compile(r"\brounded\b|\bround(?:ing)?\s+(?:to|off)\b|\b(?:correct|accurate)\s+to\b", re.IGNORECASE)
_APPROX_CUE_RE = re.compile(r"≈|≃|≅|∼|~|\bapprox(?:imately|imated|imate|\.|\b)|\babout\b|\baround\b|\broughly\b|\bnearly\b|\balmost\b|\bcirca\b"
                            r"|\bc\.\s?(?=\d)|\bsome\b(?=\s+\d)", re.IGNORECASE)
#: An approximation cue (a word: "about", "around", "roughly", "nearly", "almost", "approximately", "circa"; or a sign:
#: "≈", "~") states that a figure is approximate only where it governs THAT figure (:func:`_approximation_cues`): a word
#: written right before it ("about 30", "approximately equal to 0.33", "roughly −2", "about a third", "the approximate
#: value of 0.33"), or right after it and its unit ("0.33 approximately", "30 m (approx.)"); a sign written right before
#: it ("x ≈ 0.33", "117.72 N ≈ 118 N": 118). Governing another word or another figure ("think about it",
#: "almost certain", "nearly all", "about 2 people think that x = 0.33", "12 kg × 9.81 = 117.72 ≈ 118") it states nothing
#: about the figure.
_APPROX_GAP_BEFORE_RE = re.compile(r"\s*(?:(?:the\s+)?(?:value|figure|total|amount|number|result|estimate|level|rate)\s+(?:of\s+|is\s+)?)?"
                                   r"(?:(?:equal|equals|close)\s+to\s+|to\s+|at\s+|as\s+)?\(?\s*", re.IGNORECASE)
_APPROX_GAP_AFTER_RE = re.compile(r"\s*[,(]?\s*")
_APPROX_SIGN_GAP_RE = re.compile(r"[ \t]*\(?[ \t]*")
#: A figure written right after a cue ('about 30', '≈ −0.5'): the cue governs that one, not one before it.
_FIGURE_AHEAD_RE = re.compile(r"\s*(?:(?:equal|equals|close)\s+to\s+|to\s+)?\(?\s*(?:US\$|A\$|C\$|NZ\$|HK\$|[$£€¥₹₩])?\s?[-−–+]?(?:\d|\.\d)")
#: The approximation words that may follow the figure they govern ('0.33 approximately', '30 (approx.)').
_POSTPOSED_APPROX = frozenset({"approx", "approx.", "approximately"})
#: How far from a figure an approximation cue that governs it may stand (its gap words included), in characters.
_APPROX_REACH = 56
_NEAREST_VALUES = {"whole number": Fraction(1), "integer": Fraction(1), "unit": Fraction(1), "ten": Fraction(10), "tenth": Fraction(1, 10),
                   "hundred": Fraction(100), "hundredth": Fraction(1, 100), "thousand": Fraction(1000), "thousandth": Fraction(1, 1000),
                   "million": Fraction(10 ** 6)}
#: The coarse keyword test of :func:`is_definitional` (coverage reads assertion clause by clause: :mod:`.assertion`).
_DEFINITIONAL_RE = re.compile(r"\bdefin(?:e|ed|es|ing|ition)\b|\blet\b|\bdenotes?\b|\biff\b|\bif\s+and\s+only\s+if\b|\bsuppos(?:e|ing)\b"
                              r"|\bassum(?:e|ing)\b|\bhypothetic|\barbitrary\b|\bwhether\b|\bfor\s+(?:any|all|every)\b|\bstands?\s+for\b"
                              r"|\bdoes\s+not\s+assert\b", re.IGNORECASE)
_ABBREVIATIONS = frozenset({"approx", "c", "e.g", "i.e", "etc", "vs", "no", "d.p", "s.f", "dp", "sf", "cf", "fig", "p", "pp", "ca", "al", "st", "mr", "mrs", "dr"})
#: Abbreviations a full stop closes before a LOWER-CASE word ("e.g. n", "approx. the", "vol. x", "ch. v"): the list above
#: and the further ones the clause reader (:mod:`.assertion`) knows. A word written with an inner full stop ("U.S", "p.m")
#: is an abbreviation too.
LOWER_CASE_ABBREVIATIONS = _ABBREVIATIONS | frozenset({"eg", "ie", "viz", "resp", "est", "ed", "vol", "ch", "sec", "eq", "eqn"})
#: A sentence may open with a lower-case SYMBOL rather than a capital ("n = 17.", "x is 5.", "b holds.", "θ = 30°."): a single
#: letter (the article "a" only before a comparison sign), an identifier with a digit or an underscore ("x1", "num_states"),
#: a Greek letter, or any word a comparison sign follows ("speed = 15"). A full stop before one ends the sentence, unless it
#: closes an abbreviation (:data:`LOWER_CASE_ABBREVIATIONS`); any other lower-case word after a full stop continues it
#: ("approx. the", "Suppose b holds. then n = 17": the supposition still governs).
_SYMBOL_START_RE = re.compile(
    r"(?:[b-z]|a(?=\s*(?:=|<|>|≤|≥|≠|≈)))(?![A-Za-z0-9_]|\.[A-Za-z])"  # a letter, not the 'i' of 'i.e.' or the 'e' of 'e.g.'
    r"|[a-z][A-Za-z]*(?:\d|_)[A-Za-z0-9_]*(?![A-Za-z0-9_])"
    r"|[α-ωϑϕϖϰϱϵ](?![A-Za-z0-9_])"
    r"|[a-z][A-Za-z0-9_]*(?=\s*(?:=|<|>|≤|≥|≠|≈))"
)


@dataclass(frozen=True)
class _Cue:
    kind: Literal["exact", "rounded"]
    start: int
    end: int
    text: str
    mode: RoundingMode = "nearest"
    precision: Optional[str] = None
    places: Optional[int] = None          # decimal places stated
    sig_figs: Optional[int] = None        # significant figures stated
    nearest: Optional[Fraction] = None    # 'to the nearest X'
    generic: bool = False                 # 'approximately', 'rounded' with no precision


def _number_of(word: str) -> Optional[int]:
    word = word.lower()
    if word.isdigit():
        return int(word)
    return _WORD_NUMBERS.get(word)


@lru_cache(maxsize=512)
def _cue_lists(text: str) -> tuple[tuple[_Cue, ...], tuple[_Cue, ...]]:
    """``(cues, approximation cues)`` of ``text``, each in start order: the exactness and rounding cues with their spans,
    and apart from them the approximation cues, which govern only the figure they are written against
    (:func:`_approximation_cues`). A rounding cue inside an exactness cue ("not rounded", "without rounding", "without
    approximation") is dropped."""
    out: list[_Cue] = []
    words: list[_Cue] = []
    # Which characters an exactness cue, and a rounding cue already kept, covers: one lookup per cue instead of a scan of
    # every cue found so far, so the work stays linear in the text whatever an untrusted text repeats.
    exact = bytearray(len(text) + 1)
    for m in _EXACT_CUE_RE.finditer(text):
        exact[m.start():m.end()] = b"\x01" * (m.end() - m.start())
        out.append(_Cue("exact", m.start(), m.end(), m.group(0)))

    def inside_exact(s: int, e: int) -> bool:
        """A span of an exactness cue holds ``s``, or holds ``e - 1`` (the cue ends inside it)."""
        return bool(exact[s]) or (e > 0 and bool(exact[e - 1]))

    taken = bytearray(len(text) + 1)

    def add(cue: _Cue) -> None:
        if inside_exact(cue.start, cue.end) or taken[cue.start]:
            return
        taken[cue.start:cue.end] = b"\x01" * (cue.end - cue.start)
        out.append(cue)

    for m in _DP_CUE_RE.finditer(text):
        n = _number_of(m.group("n"))
        if n is not None:
            add(_Cue("rounded", m.start(), m.end(), m.group(0), precision=f"{n} decimal place{'s' if n != 1 else ''}", places=n))
    for m in _SF_CUE_RE.finditer(text):
        n = _number_of(m.group("n"))
        if n is not None and n > 0:
            add(_Cue("rounded", m.start(), m.end(), m.group(0), precision=f"{n} significant figure{'s' if n != 1 else ''}", sig_figs=n))
    for m in _NEAREST_CUE_RE.finditer(text):
        what = re.sub(r"\s+", " ", m.group("what").lower())
        value = _NEAREST_VALUES.get(what)
        if value is None:
            try:
                value = Fraction(what.replace(",", ""))
            except (ValueError, ZeroDivisionError):
                value = None
        if value:
            add(_Cue("rounded", m.start(), m.end(), m.group(0), precision=f"to the nearest {what}", nearest=value))
    for m in _DIRECTED_CUE_RE.finditer(text):
        mode: RoundingMode = "down" if (m.group("dir") or "").lower() == "down" else ("up" if m.group("dir") else "down")
        add(_Cue("rounded", m.start(), m.end(), m.group(0), mode=mode, generic=True, precision="truncated" if m.group("trunc") else None))
    for m in _ROUNDED_CUE_RE.finditer(text):
        add(_Cue("rounded", m.start(), m.end(), m.group(0), generic=True))
    for m in _APPROX_CUE_RE.finditer(text):
        cue = _Cue("rounded", m.start(), m.end(), m.group(0), generic=True)
        if not m.group(0).lower().startswith(("c.", "some")):
            if not (inside_exact(cue.start, cue.end) or taken[cue.start]):
                words.append(cue)  # an approximation cue governs only the figure it is written against
            continue
        add(cue)  # 'c. 1450', 'some 300': written against their figure by construction
    return tuple(sorted(out, key=lambda c: c.start)), tuple(sorted(words, key=lambda c: c.start))


def _cues(text: str) -> tuple[_Cue, ...]:
    """The exactness and rounding cues of ``text`` in start order, approximation cues aside (:func:`_cue_lists`)."""
    return _cue_lists(text)[0]


@lru_cache(maxsize=512)
def _approximation_cue_starts(text: str) -> tuple[int, ...]:
    return tuple(c.start for c in _cue_lists(text)[1])


def _approximation_cues(text: str, figure: "StatedFigure") -> list[_Cue]:
    """The approximation cues of ``text`` that govern ``figure`` (see :data:`_APPROX_GAP_BEFORE_RE`): a word written
    right before it (only white space, a bracket, 'to', 'at', 'equal to' or 'the value of' between them) or, for
    'approximately' and 'approx.' that govern no figure after them, right after it and its unit (a comma or a bracket
    between them); a sign right before it ('≈ 0.33': the term before the sign is what the figure approximates). Found by
    bisection among the cues near the figure, so the work per figure stays bounded."""
    cues, starts = _cue_lists(text)[1], _approximation_cue_starts(text)
    out: list[_Cue] = []
    for k in range(bisect_left(starts, figure.start - _APPROX_REACH), bisect_right(starts, figure.end + _APPROX_REACH)):
        c = cues[k]
        word = c.text[0].isalpha()
        if c.end <= figure.start:
            gap = _APPROX_GAP_BEFORE_RE if word else _APPROX_SIGN_GAP_RE
            if gap.fullmatch(text, c.end, figure.start) is not None:
                out.append(c)
        elif c.start >= figure.end:
            if not word or c.text.lower() not in _POSTPOSED_APPROX or _FIGURE_AHEAD_RE.match(text, c.end) is not None:
                continue  # a sign, 'about', 'nearly' precede what they govern; 'approximately 30' governs the 30
            if _APPROX_GAP_AFTER_RE.fullmatch(text, figure.end, c.start) is not None:
                out.append(c)
    return out


@lru_cache(maxsize=512)
def _precision_cue_spans(text: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """``(starts, ends)`` of the cues of ``text`` that state a precision ("to 2 decimal places", "3 s.f."), in order, read
    within :data:`MAX_TEXT_CHARS` as the figures are (computed once per text)."""
    spans = [(c.start, c.end) for c in _cues(text[:MAX_TEXT_CHARS]) if c.places is not None or c.sig_figs is not None]
    return tuple(a for a, _b in spans), tuple(b for _a, b in spans)


def in_precision_cue(text: str, pos: int) -> bool:
    """Whether character ``pos`` of ``text`` lies inside a cue that states a precision ("to 2 decimal places", "3 s.f."):
    its numeral says how exactly a figure is written. It is no figure, and no other end of a range: "x is 0.33 to 2
    decimal places" states 0.33, not a range from 0.33 to 2 (found by bisection)."""
    starts, ends = _precision_cue_spans(text)
    k = bisect_right(starts, pos) - 1
    return k >= 0 and pos < ends[k]


@lru_cache(maxsize=512)
def _sentences(text: str) -> tuple[tuple[int, int], ...]:
    """Sentence spans of ``text``: ends at ``!``, ``?``, ``;`` and line breaks, and at a full stop followed by a space and
    a capital (or the end) or a lower-case symbol that opens a statement ("Define b. n = 17.": two sentences, see
    :data:`_SYMBOL_START_RE`), never at a decimal point or after a common abbreviation ("approx.", "d.p.", "e.g.")."""
    bounds: list[tuple[int, int]] = []
    start = 0
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        end = False
        if ch in "!?;\n":
            end = True
        elif ch == ".":
            prev_digit = i > 0 and text[i - 1].isdigit()
            next_digit = i + 1 < n and text[i + 1].isdigit()
            if not (prev_digit and next_digit):
                j = i + 1
                while j < n and text[j] in " \t\"'”’)]":
                    j += 1
                word = re.search(r"([A-Za-z.]+)$", text[max(start, i - 8):i])
                abbrev = word is not None and word.group(1).lower().strip(".") in _ABBREVIATIONS
                if j >= n or (j > i + 1 and (text[j].isupper() or text[j] in "\"“‘('")):
                    end = not abbrev
                elif j > i + 1 and text[j].islower() and _SYMBOL_START_RE.match(text, j) is not None:
                    written = word.group(1).strip(".") if word is not None else ""
                    end = not (written.lower() in LOWER_CASE_ABBREVIATIONS or "." in written)
        if end:
            bounds.append((start, i + 1))
            start = i + 1
        i += 1
    if start < n:
        bounds.append((start, n))
    return tuple(bounds)


@lru_cache(maxsize=512)
def _sentence_starts(text: str) -> tuple[int, ...]:
    """The start of every sentence of ``text``, in order (the sentences are contiguous and do not overlap)."""
    return tuple(a for a, _b in _sentences(text))


def sentence_of(text: str, start: int, end: int) -> tuple[int, int]:
    """The span of the sentence of ``text`` that holds ``start``-``end`` (found by bisection: the sentences are ordered
    and do not overlap, so only the last one starting at or before ``start`` can hold it)."""
    k = bisect_right(_sentence_starts(text), start) - 1
    if k >= 0:
        a, b = _sentences(text)[k]
        if a <= start < b:
            return a, max(b, min(end, len(text)))
    return 0, len(text)


def is_definitional(text: str) -> bool:
    """True when ``text`` holds a definitional or suppositional keyword ("define b iff n = 17", "let x be", "for any y").
    A coarse keyword test kept for callers; whether a figure is asserted is read by :func:`.assertion.assertion_at`."""
    return _DEFINITIONAL_RE.search(text) is not None


# ------------------------------------------------------------------ reading figures


#: A unit of two or three space-separated words right after a numeral: each word a unit symbol of up to four letters with an
#: optional power ("m³ s⁻¹", "J kg⁻¹ K⁻¹", "km h⁻¹").
_MULTI_WORD_UNIT_RE = re.compile(r"\s?([A-Za-zµμ°]{1,4}[⁻¹²³⁴⁵⁶⁷⁸⁹⁰^\-0-9]*(?: [A-Za-zµμ]{1,3}[⁻¹²³⁴⁵⁶⁷⁸⁹⁰^\-0-9]*){1,2})")


def _figure_unit(text: str, end: int) -> tuple[int, Optional[str], Optional[Fraction], Optional[str], int, Optional[str]]:
    """What follows a numeral: ``(new end, unit, factor, dimension, scale, scale word)``."""
    scale, scale_word = 1, None
    m = _SCALE_RE.match(text, end)
    if m is not None:
        scale_word = m.group("w").lower()
        scale = _SCALE_WORDS[scale_word]
        end = m.end()
    r = _RATIO_RE.match(text, end)
    if r is not None:
        if r.group("pct") and not r.group("pp"):
            return r.end(), "%", _RATIO_UNITS["%"], "dimensionless", scale, scale_word
        if r.group("pp") or r.group("ppt"):
            return r.end(), "percentage point", _RATIO_UNITS["percentage point"], "dimensionless", scale, scale_word
        if r.group("pm"):
            return r.end(), "per mille", _RATIO_UNITS["per mille"], "dimensionless", scale, scale_word
        if r.group("bp"):
            return r.end(), "basis point", _RATIO_UNITS["basis point"], "dimensionless", scale, scale_word
    u = _UNIT_TOKEN_RE.match(text, end)
    if u is not None and u.start("u") == end and re.match(r"(?:s|st|nd|rd|th)(?![A-Za-z])", text[end:end + 3]):
        u = None  # '1880s' (a decade), '2nd', '21st': no unit
    if u is not None:
        token = u.group("u")
        lowered = token.lower().rstrip(".,;:)")
        if lowered in _CURRENCY_WORDS:
            return u.start("u") + len(token.rstrip(".,;:)")), lowered, None, "currency", scale, scale_word
        # a unit of two or three words ("km h⁻¹", "m s⁻¹", "m³ s⁻¹", "J kg⁻¹ K⁻¹"; a first word may carry its power) before a
        # one-word one, the longest that reads as a unit first (repair round 2: "21 m³ s⁻¹" was read as 21 m³)
        many = _MULTI_WORD_UNIT_RE.match(text[end:end + 40])
        if many is not None:
            words = many.group(1).split(" ")
            for n in range(len(words), 1, -1):
                candidate = " ".join(words[:n])
                reading = _unit_reading(candidate)
                if reading is not None:
                    return end + many.start(1) + len(candidate), reading[0], reading[1], reading[2], scale, scale_word
        reading = _unit_reading(token)
        if reading is not None:
            return u.start("u") + len(reading[0]), reading[0], reading[1], reading[2], scale, scale_word
    return end, None, None, None, scale, scale_word


def _sign_and_currency(text: str, start: int) -> tuple[int, int, Optional[str]]:
    """``(new start, sign, currency)`` for what precedes a numeral: a currency mark and a minus sign written against it."""
    currency = None
    s = start
    before = text[max(0, s - 4):s]
    cm = _CURRENCY_BEFORE_RE.search(before)
    if cm is not None:
        currency = cm.group(0).strip()
        s -= len(cm.group(0))
    sign = 1
    if s > 0 and text[s - 1] in _SIGN_CHARS:
        prior = text[s - 2] if s >= 2 else " "
        if not (prior.isalnum() or prior in "_)]."):
            sign = -1
            s -= 1
    return s, sign, currency


def _fraction_after(text: str, end: int) -> Optional[tuple[int, int]]:
    """A denominator written ``/d`` right after a numeral (``1/3``), not a date (``12/10/2026``) or a unit (``km/h``)."""
    m = re.match(r"/(\d{1,9})(?![\d/]|\.\d)", text[end:end + 12])
    if m is None:
        return None
    den = int(m.group(1))
    return (end + m.end(), den) if den else None


_YEAR_BEFORE_RE = re.compile(r"(?<!\d)1\d{3}$|(?<!\d)20\d{2}$")


def _two_digits_at(text: str, i: int) -> bool:
    return i + 1 < len(text) and text[i].isdigit() and text[i + 1].isdigit() and (i + 2 >= len(text) or not text[i + 2].isdigit())


@lru_cache(maxsize=256)
def _figures(kind: str, ident: str, text: str) -> tuple[StatedFigure, ...]:
    text = text[:MAX_TEXT_CHARS]
    out: list[StatedFigure] = []
    # the characters of the cues that state a precision ('2 decimal places'): their numerals are no figures (one lookup
    # per numeral, so the scan stays linear in the text)
    cue_numerals = bytearray(len(text) + 1)
    for c in _cues(text):
        if c.places is not None or c.sig_figs is not None:
            cue_numerals[c.start:c.end] = b"\x01" * (c.end - c.start)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        starts_number = ("0" <= ch <= "9") or (ch == "." and i + 1 < n and "0" <= text[i + 1] <= "9" and (i == 0 or not text[i - 1].isalnum()))
        if not starts_number:
            i += 1
            continue
        joined = i > 1 and text[i - 1] in "-–" and (text[i - 2].isalpha() or _YEAR_BEFORE_RE.search(text[max(0, i - 6):i - 1]) is not None and _two_digits_at(text, i))
        if joined or (i > 0 and (text[i - 1].isalpha() or text[i - 1] == "_" or (text[i - 1] == "." and i > 1 and text[i - 2].isalnum()))):
            # part of an identifier or a label ('v22', 'h1.4', 'COVID-19') or the second year of a range ('1960-61')
            j = i
            while j < n and (text[j].isalnum() or text[j] in "._"):
                j += 1
            i = j
            continue
        scan = _scan_numeral(text, i)
        if scan is None or scan.end <= i:
            i += 1
            continue
        if scan.number is None or cue_numerals[i]:
            i = scan.end
            continue
        num = scan.number
        end = scan.end
        grouped = _grouped_thousands(text, i, scan)
        if grouped is not None:
            num, end = grouped  # '€18 000', '12 500', '1 250.75': one figure grouped in thousands by spaces (repair round 3)
        start, sign, currency = _sign_and_currency(text, i)
        value, has_point, places, half = num.value, num.has_point, max(0, -num.last_place) if num.has_point else 0, num.half_width
        numeral = num.text
        frac = _fraction_after(text, end) if not num.has_point and not num.scientific else None
        if frac is not None:
            end, den = frac
            value = Fraction(value, den)
            numeral = text[i:end]
            has_point, places, half = False, 0, Fraction(0)
        end, unit, factor, dim, scale, scale_word = _figure_unit(text, end)
        out.append(StatedFigure(source_kind=kind, source_id=ident, start=start, end=end, written=text[start:end].strip(), numeral=numeral.replace("−", "-"),  # type: ignore[arg-type]
                                value=sign * value, has_point=has_point, places=places, half_width=half, unit=unit, unit_factor=factor, unit_dim=dim,
                                currency=currency, scale=scale, scale_word=scale_word))
        i = max(end, scan.end)
    for m in _NUMBER_WORD_RE.finditer(text):
        tens, tunit, unit_w, art, frac_w = m.group("tens"), m.group("tunit"), m.group("unit"), m.group("a"), m.group("frac")
        if art and not frac_w:
            continue  # 'a' or 'an' alone is no figure
        if tens:
            whole = _TENS_WORDS[tens.lower()] + (_UNIT_WORDS[tunit.lower()] if tunit else 0)
        elif unit_w:
            whole = _UNIT_WORDS[unit_w.lower()]
        else:
            whole = 1
        value = Fraction(whole, _FRACTION_WORDS[frac_w.lower()]) if frac_w else Fraction(whole)
        end, unit, factor, dim, scale, scale_word = _figure_unit(text, m.end())
        out.append(StatedFigure(source_kind=kind, source_id=ident, start=m.start(), end=end, written=text[m.start():end].strip(), numeral=m.group(0),  # type: ignore[arg-type]
                                value=value, has_point=False, places=0, half_width=Fraction(0), unit=unit, unit_factor=factor, unit_dim=dim,
                                scale=scale, scale_word=scale_word, word=True))
    return tuple(sorted(out, key=lambda f: f.start))


#: The separators that group a numeral's thousands in the SI and IB style: a space, a thin space, a no-break space, a narrow
#: no-break space, and LaTeX's thin space (``18\,000``).
_GROUP_SEPARATORS = (" ", "\u2009", "\u00a0", "\u202f", "\\,")


def _grouped_thousands(text: str, i: int, scan) -> Optional[tuple[Any, int]]:
    """``(the number, its end)`` when the whole numeral of one to three digits at ``i`` is followed by groups of exactly three
    digits, each after one thousands separator (:data:`_GROUP_SEPARATORS`), and then by no further digit ("€18 000", "12 500",
    "1 250.75", "18\\,000"): one figure grouped in thousands, as the SI and the IB write it (repair round 3, V3-E2E: a task's
    "€18 000" was read as 18 and 0). None otherwise, so "in 2019 500 people" (a four-digit first group) is two figures."""
    num = scan.number
    head = text[i:scan.end]
    if num.has_point or getattr(num, "scientific", False) or not head.isdigit() or not 1 <= len(head) <= 3 or (i > 0 and text[i - 1].isdigit()):
        return None
    digits = head
    j = scan.end
    groups = 0
    while groups < 6:
        sep = next((g for g in _GROUP_SEPARATORS if text.startswith(g, j)), None)
        if sep is None:
            break
        k = j + len(sep)
        block = text[k:k + 3]
        if len(block) != 3 or not block.isdigit() or (k + 3 < len(text) and text[k + 3].isdigit()):
            break
        digits += block
        j = k + 3
        groups += 1
    if not groups:
        return None
    if j + 1 < len(text) and text[j] == "." and text[j + 1].isdigit():
        k = j + 1
        while k < len(text) and text[k].isdigit() and k - j <= 30:
            k += 1
        digits += text[j:k]
        j = k
    again = _scan_numeral(digits, 0)
    if again is None or again.number is None or again.end != len(digits):
        return None
    return again.number, j


def figures_in(source: SourceText) -> tuple[StatedFigure, ...]:
    """Every figure of ``source`` in order: numerals (with sign, currency, unit, scale word) and number words."""
    return _figures(source.kind, source.ident, source.text)


def is_year_like(figure: StatedFigure) -> bool:
    """A four-digit whole number from 1000 to 2199 written with no unit, currency or point: a date, which identifies a
    quantity rather than stating one."""
    return (not figure.word and not figure.has_point and figure.unit is None and figure.currency is None and figure.scale == 1
            and figure.value.denominator == 1 and 1000 <= figure.value <= 2199 and len(figure.numeral.lstrip("-")) == 4)


# ------------------------------------------------------------------ exactness


def _calculation_result(text: str, figure: StatedFigure, sentence: tuple[int, int]) -> Optional[tuple[str, str]]:
    """The written calculation a figure is stated as the result of ("1 ÷ 8.40 = US$0.1190") as ``(calculation with its
    result, its left side)``, or None. The figure follows an '=' (or '≈'), the text before that sign, back to the
    previous '=' or the start of the clause (a comma, colon or semicolon), ENDS in a calculation
    (:func:`_calculation_run`), and the figure ends the expression (it is no operand of a further one: "= 3 − 1",
    "= 5(2 × 3)"). Anything else right before the sign (a variable, a symbol, a word that is no unit of an operand) is
    the term the sign equates with the figure, so the figure states that term's value, not a calculation's result:
    "If x = 1/3 then x = 0.33", "x = 1/3 implies x = 0.33", "Given x = 1/3 we get x = 0.33", "x × 3 = 1.00" and
    "70 cm³ and HR = 72" state no calculation for their last figure, and neither does "Since x = 1/3, x = 0.33"."""
    s0 = sentence[0]
    j = figure.start - 1
    while j >= s0 and text[j] in " \t":
        j -= 1
    if j < s0 or text[j] not in "=≈≃":
        return None
    eq = j
    k = eq - 1
    while k >= s0 and text[k] not in "=:\n;" and not (text[k] == "," and not (k > 0 and text[k - 1].isdigit() and k + 1 < len(text) and text[k + 1].isdigit())):
        k -= 1
    left = text[k + 1:eq]
    if _EXPRESSION_CONTINUES_RE.match(_latex_plain(text[figure.end:figure.end + 48])) is not None or _calculation_run(left) is None:
        return None
    return text[k + 1:figure.end].strip(), left


# ------------------------------------------------------------------ written calculations

#: The reader reads at most this many characters before an '=' (a calculation that runs past them is not read), and at
#: most this many tokens and this nesting depth.
_CALC_MAX_CHARS = 600
_CALC_MAX_TOKENS = 64
_CALC_MAX_DEPTH = 24
#: The most words the unit of one operand takes ('J kg⁻¹ K⁻¹', 'million litres').
_CALC_MAX_UNIT_WORDS = 4
_VULGAR_FRACTIONS = {"½": Fraction(1, 2), "⅓": Fraction(1, 3), "⅔": Fraction(2, 3), "¼": Fraction(1, 4), "¾": Fraction(3, 4), "⅕": Fraction(1, 5),
                     "⅖": Fraction(2, 5), "⅗": Fraction(3, 5), "⅘": Fraction(4, 5), "⅙": Fraction(1, 6), "⅚": Fraction(5, 6), "⅛": Fraction(1, 8),
                     "⅜": Fraction(3, 8), "⅝": Fraction(5, 8), "⅞": Fraction(7, 8)}
_CALC_TOKEN_RE = re.compile(
    r"(?P<sp>\s+)"
    r"|(?P<cur>(?:US|A|C|NZ|HK)\$|[$£€¥₹₩])"
    r"|(?P<num>(?:(?:\d{1,3}(?:,\d{3})+(?![\d,])|\d{1,30})(?:\.\d{1,30})?|\.\d{1,30})(?:[eE][-+−]?\d{1,3})?(?!\d))"
    r"|(?P<vf>[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])"
    r"|(?P<const>π)"
    r"|(?P<pct>%)"
    r"|(?P<op>[-+−–×*·⋅÷/])"
    r"|(?P<lp>\()|(?P<rp>\))"
    r"|(?P<pow>[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)"
    r"|(?P<caret>\^)"
    r"|(?P<root>[√∛∜])"
    r"|(?P<lb>[\[{])|(?P<rb>[\]}])"
    r"|(?P<bar>\|)"
    r"|(?P<word>[A-Za-zµμΩ°℃][A-Za-zµμΩ°℃²³⁻¹/]{0,23})"
    r"|(?P<other>.)",
    re.DOTALL,
)
_CALC_OPS = {"+": "+", "-": "-", "−": "-", "–": "-", "×": "*", "*": "*", "·": "*", "⋅": "*", "÷": "/", "/": "/"}
#: Opening marks a calculation may follow with no space: quotation marks and code ticks.
_CALC_QUOTES = frozenset("'\"‘’“”`«»")
_CALC_SIGNS = frozenset("+-−–")
#: Tokens that can open an operand (a numeral, a currency mark, a bracket, a root, a constant) and tokens that can close
#: one (a numeral, a bracket, a per cent sign, a power, a constant).
_CALC_OPENS = frozenset({"num", "vf", "const", "cur", "lp", "lb", "bar", "root", "func"})
_CALC_CLOSES = frozenset({"num", "vf", "const", "rp", "rb", "bar", "pct", "pow"})
_CALC_MARKS = _CALC_OPENS | _CALC_CLOSES | {"op", "caret"}
#: Units of everyday measures the STEM unit table does not read (it reads SI and laboratory units).
_EVERYDAY_UNITS = frozenset({"tonne", "tonnes", "ton", "tons", "mile", "miles", "foot", "feet", "ft", "inch", "inches", "yard", "yards", "mph",
                             "kph", "gallon", "gallons", "acre", "acres", "hectare", "hectares", "ha", "year", "years", "yr", "yrs", "month",
                             "months", "week", "weeks", "hr", "hrs", "mins", "secs", "°", "degree", "degrees", "barrel", "barrels", "kcal"})
#: English words the STEM unit table reads as rare units ('as' attosecond, 'am' attometre, 'us' microsecond): never the
#: unit of an operand in a written calculation.
_NOT_UNIT_WORDS = frozenset({"as", "am", "us"})
#: Function words: never the count noun of an operand ('2 + 1 and −0.5').
_FUNCTION_WORDS = frozenset({"and", "or", "but", "nor", "then", "than", "thus", "hence", "therefore", "since", "because", "if", "when",
                             "while", "which", "that", "the", "for", "from", "with", "per", "via", "are", "was", "were", "has", "have", "had",
                             "gives", "give", "giving", "gets", "get", "got", "makes", "make", "made", "yields", "yield", "implies", "imply",
                             "means", "mean", "follows", "follow", "equals", "equal", "becomes", "become", "let", "not", "you", "they", "also"})
#: What follows a figure that is an operand of a further expression, not its result: an operator before an operand
#: ("= 3 − 1", "= 5 × 42", "= 1.6 x 100"), or a bracket, a root, π, a letter or a power written against it (an implicit
#: product or a power: "= 5(2 × 3)", "= 2√3", "= 3t", "= 2³").
_EXPRESSION_CONTINUES_RE = re.compile(r"\s*(?:[-+−–×*·⋅÷/^]|[xX](?=\s*[\d(.]))\s*(?:\d|\.\d|[($£€¥½⅓⅔¼¾√π])|[(√∛∜πA-Za-z⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]")
#: Functions a written calculation may apply to a numeral ('sin(30)', 'ln 2', 'log(2.5 × 10⁻⁴)'): a calculation the reader
#: does not compute.
_CALC_FUNCTIONS = frozenset({"sin", "cos", "tan", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "ln", "log", "lg", "exp", "sqrt"})
#: LaTeX commands read by :func:`_latex_plain`: operators, a constant, spacing, text, fractions and roots.
_LATEX_SIGNS = {"times": " × ", "cdot": " · ", "div": " ÷ ", "ast": " * ", "pi": "π"}
_LATEX_SPACING = frozenset({",", ";", ":", "!", " ", "quad", "qquad", "displaystyle", "textstyle", "left", "right", "big", "Big", "bigl", "bigr",
                            "Bigl", "Bigr"})
_LATEX_TEXT = frozenset({"text", "mathrm", "textrm", "rm", "mbox", "operatorname", "textit", "mathit"})
_LATEX_FRACTIONS = frozenset({"frac", "dfrac", "tfrac"})


def _latex_group(text: str, i: int) -> Optional[tuple[str, int]]:
    """The argument of a LaTeX command at ``text[i]`` (after spaces): a braced group (its content) or one character;
    ``(content, index after it)``, or None (no argument, or an unbalanced group)."""
    n = len(text)
    while i < n and text[i] == " ":
        i += 1
    if i >= n:
        return None
    if text[i] != "{":
        return (text[i], i + 1) if text[i] not in "}\\" else None
    depth = 0
    for j in range(i, n):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
    return None


def _latex_plain(text: str, depth: int = 0) -> str:
    """``text`` with the LaTeX of written calculations read as plain marks: ``\\times`` ×, ``\\cdot`` ·, ``\\div`` ÷,
    ``\\pi`` π, ``\\frac{a}{b}`` ((a)/(b)), ``\\sqrt{a}`` √(a), ``^{a}`` ^(a), ``\\text{kg}`` kg, ``\\%`` %, ``\\$`` $,
    spacing and ``\\left``/``\\right`` dropped. Any other command is kept as written (it is no calculation the reader
    reads). Nothing is executed; the text is read once, and nesting is bounded."""
    if "\\" not in text and "^{" not in text:
        return text
    if depth > _CALC_MAX_DEPTH:
        return text
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            m = re.match(r"[A-Za-z]+", text[i + 1:i + 1 + 24])
            name = m.group(0) if m is not None else text[i + 1]
            j = i + 1 + len(name)
            if name in _LATEX_SIGNS:
                out.append(_LATEX_SIGNS[name])
            elif name in _LATEX_SPACING:
                out.append(" ")
                if name in ("left", "right") and j < n and text[j] == ".":
                    j += 1
            elif name in ("%", "$", "{", "}"):
                out.append(name)
            elif name in _LATEX_TEXT:
                g = _latex_group(text, j)
                if g is None:
                    out.append(text[i:j])
                else:
                    out.append(" " + _latex_plain(g[0], depth + 1) + " ")
                    j = g[1]
            elif name in _LATEX_FRACTIONS:
                a = _latex_group(text, j)
                b = _latex_group(text, a[1]) if a is not None else None
                if a is None or b is None:
                    out.append(text[i:j])
                else:
                    out.append(f"(({_latex_plain(a[0], depth + 1)})/({_latex_plain(b[0], depth + 1)}))")
                    j = b[1]
            elif name == "sqrt":
                k = j
                if k < n and text[k] == "[":
                    close = text.find("]", k)
                    k = close + 1 if close != -1 else k
                g = _latex_group(text, k)
                if g is None:
                    out.append(text[i:j])
                else:
                    out.append(f"√({_latex_plain(g[0], depth + 1)})")
                    j = g[1]
            else:
                out.append(text[i:j])
            i = j
            continue
        if ch == "^" and i + 1 < n and text[i + 1] == "{":
            g = _latex_group(text, i + 1)
            if g is not None:
                out.append(f"^({_latex_plain(g[0], depth + 1)})")
                i = g[1]
                continue
        out.append(ch)
        i += 1
    return "".join(out)


class _CalcError(Exception):
    """A written calculation the reader does not compute."""


def _calc_tokens(left: str) -> list[tuple[str, str, bool]]:
    """``(kind, text, preceded by white space)`` for each token of ``left``; an ``x`` between operands is a times sign."""
    out: list[tuple[str, str, bool]] = []
    space = False
    for m in _CALC_TOKEN_RE.finditer(left):
        kind = m.lastgroup or "other"
        if kind == "sp":
            space = True
            continue
        out.append((kind, m.group(0), space))
        space = False
    for i in range(1, len(out) - 1):
        kind, text, sp = out[i]
        if kind == "word" and text in ("x", "X") and out[i - 1][0] in ("num", "vf", "rp", "pct") and out[i + 1][0] in ("num", "vf", "lp", "cur"):
            out[i] = ("op", "×", sp)
    for i, (kind, text, sp) in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else None
        if kind == "word" and text in _CALC_FUNCTIONS and nxt is not None and nxt[0] in ("num", "vf", "lp", "lb", "const"):
            out[i] = ("func", text, sp)  # a function applied to an operand: 'sin(30)', 'ln 2'
        elif kind == "word" and text == "e" and nxt is not None and nxt[0] in ("caret", "pow") and not nxt[2]:
            out[i] = ("const", text, sp)  # the constant e raised to a power: 'e^2'
        elif kind == "cur" and not (nxt is not None and nxt[0] == "num"):
            out[i] = ("other", text, sp)  # a '$' before no numeral is no currency mark (a LaTeX math delimiter)
    return out


_UNIT_POWER_RE = re.compile(r"(?:[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+|\^-?\d{1,2})$")


@lru_cache(maxsize=2048)
def _is_unit_word(word: str) -> bool:
    """A unit (the STEM unit table, or an everyday measure, possibly with a power: 'yr⁻¹') or a currency word: what the
    unit of an operand may be."""
    w = word.rstrip(".,;:)")
    if not w or w in _NOT_UNIT_WORDS:
        return False
    if w.lower() in _CURRENCY_WORDS or w.lower() in _EVERYDAY_UNITS or _unit_reading(w) is not None:
        return True
    base = _UNIT_POWER_RE.sub("", w)
    return base != w and base.lower() in _EVERYDAY_UNITS


def _is_count_noun(word: str) -> bool:
    """A lower-case word of three or more letters that is no function word ('tickets', 'counts'): what an operand may
    count. Never a single letter (a variable), a word written in capitals (a symbol: 'HR') or a connective ('then')."""
    w = word.rstrip(".,;:)")
    return len(w) >= 3 and w.isascii() and w.isalpha() and w.islower() and w not in _FUNCTION_WORDS


def _percent_words(words: Sequence[str]) -> int:
    """How many of ``words`` spell a percentage at their start ('percent', 'per cent': 1 or 2), else 0."""
    lowered = [w.lower().rstrip(".,;:)") for w in words[:2]]
    if lowered[:1] == ["percent"]:
        return 1
    if lowered == ["per", "cent"]:
        return 2
    return 0


def _unit_group(words: Sequence[str], counted: bool) -> bool:
    """Whether ``words`` (written right after an operand) are that operand's unit: an optional scale word ('million'),
    then a percentage ('per cent') or units and currency words ('litres', 'J kg⁻¹ K⁻¹', 'dollars'), each unit possibly
    joined by 'per', 'a' or 'an' ('$1.60 per litre', '$5 an hour'), or, when ``counted`` (the words stand before an
    operator or a closing bracket, inside the calculation), one count noun among them ('3 tickets × $2.50', '1600 counts
    min⁻¹ × ...', '$12.50 per ticket × 3')."""
    ws = list(words)
    if not ws or len(ws) > _CALC_MAX_UNIT_WORDS:
        return False
    if _SCALE_WORDS.get(ws[0].lower().rstrip(".,;:)").rstrip("s")) is not None:
        ws = ws[1:]
        if not ws:
            return True
    p = _percent_words(ws)
    if p:
        ws = ws[p:]
        if not ws:
            return True
    nouns = 0
    for k, w in enumerate(ws):
        if w in ("per", "a", "an"):  # lower case: 'A' is the ampere
            if k + 1 >= len(ws) or ws[k + 1] in ("per", "a", "an"):
                return False  # 'per', 'a' and 'an' join a unit that follows them
            continue
        if _is_unit_word(w):
            continue
        if counted and nouns == 0 and _is_count_noun(w):
            nouns += 1
            continue
        return False
    return True


def _symbol_like(token: tuple[str, str, bool]) -> bool:
    """A token that names a quantity rather than reads as prose: a single letter (not the words 'a' and 'I'), possibly with
    a power ('x', 'x²'), or another alphabetic sign ('λ', 'Δ')."""
    kind, text, _sp = token
    if kind == "word":
        return sum(c.isalpha() for c in text) == 1 and text not in ("a", "A", "I")
    return kind == "other" and text.isalpha()


def _calculation_start(tokens: list[tuple[str, str, bool]]) -> int:
    """Where the run of calculation tokens that ends ``tokens`` starts: numerals, operators, brackets, per cent and
    currency marks, powers, roots and π, and the words an operand carries (:func:`_unit_group`). A word group is taken
    only right after an operand, as that operand's unit: at the end only a unit, a currency or a scale word; before an
    operator or a closing bracket also a count noun; and never a letter glued to a numeral ('3x', a variable). Any other
    word (prose, a connective, a variable, a symbol) ends the scan, and so does an opening bracket the run does not
    close ('f(1 + 2'); a closing bracket the run does not open ('(a) (80 − 40)') is cut from its start."""
    i = len(tokens)
    depth = 0
    while i > 0:
        kind = tokens[i - 1][0]
        if kind in _CALC_MARKS:
            if kind in ("rp", "rb"):
                depth += 1
            elif kind in ("lp", "lb"):
                if depth == 0:
                    break  # an opening bracket the run does not close encloses it
                depth -= 1
            i -= 1
            continue
        if kind != "word":
            break
        g = i - 1
        while g > 0 and tokens[g - 1][0] == "word":
            g -= 1
        words = tokens[g:i]
        if g == 0 or tokens[g - 1][0] not in _CALC_CLOSES:
            break  # prose, a connective, a variable or a symbol: it is no unit of an operand
        if not words[0][2] and tokens[g - 1][0] in ("num", "vf") and sum(c.isalpha() for c in words[0][1]) == 1:
            break  # a letter glued to a numeral ('3x', '2y²') is a variable
        follower = tokens[i][0] if i < len(tokens) else None
        if follower is not None and follower not in ("op", "caret", "rp", "rb", "bar"):
            break  # words between two operands with no operator ('in 2025 output 4,200'): prose
        if not _unit_group([w[1] for w in words], counted=follower is not None):
            break
        i = g
    # a closing bracket the run does not open is no part of it: the run starts after the last such bracket
    start, depth = i, 0
    for t in range(i, len(tokens)):
        kind = tokens[t][0]
        if kind in ("lp", "lb"):
            depth += 1
        elif kind in ("rp", "rb"):
            depth -= 1
            if depth < 0:
                start, depth = t + 1, 0
    return start


def _has_operation(run: Sequence[tuple[str, str, bool]]) -> bool:
    """Whether ``run`` holds an arithmetic operation: an operator between two operands, a root of an operand, or a power
    of a numeral, a constant or a bracket. A unit's power ('cm³') is none, and neither is a function value alone
    ('sin 30°', 'ln 2'): an operator must join it to another operand ('10 × sin 25°', 'ln 2 ÷ 8')."""
    for t, (kind, text, _sp) in enumerate(run):
        if kind in ("op", "caret") and 0 < t < len(run) - 1:
            before, after = run[t - 1], run[t + 1]
            if (before[0] in _CALC_CLOSES or before[0] == "word") and (after[0] in _CALC_OPENS or (after[0] == "op" and after[1] in _CALC_SIGNS)):
                return True
        elif kind == "root" and t + 1 < len(run) and run[t + 1][0] in _CALC_OPENS:
            return True
        elif kind == "pow" and t > 0 and run[t - 1][0] in ("num", "vf", "const", "rp", "rb", "bar"):
            return True
    return False


def _calculation_run(left: str) -> Optional[tuple[tuple[str, str, bool], ...]]:
    """The tokens of the calculation that ENDS ``left`` (the text before an '='), or None when ``left`` does not end in
    one. LaTeX is read as plain marks first (:func:`_latex_plain`). The run (:func:`_calculation_start`) must

    * start with an operand: a numeral, a currency mark, a bracket, a root or π, or a sign written against one
      ('−12.50'); a run that starts with a binary operator ('× 3' after 'x') continues an expression that holds a term
      that is no numeral, and a numeral glued to a word ('v2') is part of an identifier. A leading sign after a
      variable ('x −0.5 + 1') is that variable's operator;
    * end with an operand: a numeral, a closing bracket, a per cent sign, a power, or the unit of an operand;
    * hold an arithmetic operation (:func:`_has_operation`).

    The reader reads the last :data:`_CALC_MAX_CHARS` characters of ``left``; a calculation that runs past them, or that
    has more than :data:`_CALC_MAX_TOKENS` tokens, is not read."""
    cut = len(left) > _CALC_MAX_CHARS
    return _calculation_run_of(left[-_CALC_MAX_CHARS:] if cut else left, cut)


@lru_cache(maxsize=2048)
def _calculation_run_of(tail: str, cut: bool) -> Optional[tuple[tuple[str, str, bool], ...]]:
    """:func:`_calculation_run` of the last characters ``tail`` of a left side (``cut`` when the left side was longer):
    cached on that bounded tail, so the structural test and the reader read one text once."""
    tokens = _calc_tokens(_latex_plain(tail))
    i = _calculation_start(tokens)
    run = tokens[i:]
    if not run or len(run) > _CALC_MAX_TOKENS or (cut and i == 0):
        return None
    before = tokens[i - 1] if i > 0 else None
    opened = before is not None and ((before[0] == "other" and before[1] in _CALC_QUOTES) or before[0] in ("lp", "lb"))
    kind, text, space = run[0]
    if kind == "op":
        if text not in _CALC_SIGNS or len(run) < 2 or run[1][2] or run[1][0] not in _CALC_OPENS:
            return None  # a binary operator, or a sign set apart from its operand: the left operand is outside the run
        if before is not None and not opened and (not space or _symbol_like(before)):
            return None  # 'x −0.5 + 1', 'v−0.5': the sign is the operator of a variable
    elif kind in _CALC_OPENS:
        if before is not None and not space and not opened and kind in ("num", "vf", "cur"):
            return None  # a numeral glued to a word or a sign ('v2 − 0.5', 'Δ2'): part of an identifier
        if before is not None and not space and kind in ("lp", "lb") and (before[0] == "word" or _symbol_like(before)):
            return None  # a bracket written against a symbol ('f(2) + 1', 'h(0.25)'): the symbol's argument, no numeral
    else:
        return None  # a power, a per cent sign or a word: the expression starts before the run
    last = run[-1][0]
    if last not in _CALC_CLOSES and last != "word":
        return None
    return tuple(run) if _has_operation(run) else None


def _calc_items(run: Sequence[tuple[str, str, bool]]) -> Optional[list[object]]:
    """The operands (exact values) and operators of a run of calculation tokens, or None. The words after a numeral are
    its unit (:func:`_unit_group`): a scale word multiplies it ('15 million'), a percentage word makes it a hundredth
    ('20 per cent'), units, currency words and a count noun are dropped ('120 km', '3 tickets'). A power, a root, π or a
    bracket other than a parenthesis is a calculation the reader does not compute."""
    items: list[object] = []
    k = 0
    while k < len(run):
        kind, text, _sp = run[k]
        if kind == "cur":
            if k + 1 >= len(run) or run[k + 1][0] != "num":
                return None
        elif kind in ("num", "vf"):
            if kind == "vf":
                value = _VULGAR_FRACTIONS[text]
                if k > 0 and run[k - 1][0] == "num" and not _sp:
                    return None  # a mixed number ('2½') is not read
            else:
                value = Fraction(text.replace(",", "").replace("−", "-"))
            j = k + 1
            if j < len(run) and run[j][0] == "pct":
                value /= 100
                j += 1
            if j < len(run) and run[j][0] == "word" and len(run[j][1]) == 1 and not run[j][2]:
                return None  # a letter glued to a numeral ('3x', '2y') is a variable, not a unit: an equation, not a calculation
            words: list[str] = []
            while j < len(run) and run[j][0] == "word" and len(words) < _CALC_MAX_UNIT_WORDS:
                words.append(run[j][1])
                j += 1
            if words:
                scale = _SCALE_WORDS.get(words[0].lower().rstrip(".,;:)").rstrip("s"))
                rest = words[1:] if scale is not None else words
                if scale is not None:
                    value *= scale
                if _percent_words(rest):
                    value /= 100
            items.append(value)
            k = j
            continue
        elif kind == "op":
            items.append(_CALC_OPS[text])
        elif kind in ("lp", "rp"):
            items.append(text)
            if kind == "rp":
                j = k + 1
                while j < len(run) and run[j][0] == "word" and j - k <= _CALC_MAX_UNIT_WORDS:
                    j += 1
                words = [w[1] for w in run[k + 1:j]]
                if words and (_SCALE_WORDS.get(words[0].lower().rstrip(".,;:)").rstrip("s")) is not None or _percent_words(words)):
                    return None  # a scale or a percentage of a bracketed operand is not read
                k = j  # the unit of the bracketed operand ('(2 + 3) kg'), which the run's scan read as one
                continue
        else:  # a per cent sign or a word that follows no numeral, a power, a root, a constant, another bracket
            return None
        k += 1
    return items


def _calc_parse(items: list[object]) -> Optional[Fraction]:
    """The exact value of ``items`` read with the usual precedence (unary signs, then × ÷, then + −, left to right), or
    None when they are no complete calculation (an operand missing, unbalanced parentheses, a division by zero)."""
    if sum(1 for it in items if isinstance(it, Fraction)) < 2 or not any(it in ("+", "-", "*", "/") for it in items):
        return None  # one numeral is no calculation
    pos = 0

    def peek() -> object:
        return items[pos] if pos < len(items) else None

    def expr(depth: int) -> Fraction:
        nonlocal pos
        value = term(depth)
        while peek() in ("+", "-"):
            op = items[pos]
            pos += 1
            other = term(depth)
            value = value + other if op == "+" else value - other
        return value

    def term(depth: int) -> Fraction:
        nonlocal pos
        value = unary(depth)
        while peek() in ("*", "/"):
            op = items[pos]
            pos += 1
            other = unary(depth)
            if op == "/":
                if other == 0:
                    raise _CalcError("division by zero")
                value = value / other
            else:
                value = value * other
        return value

    def unary(depth: int) -> Fraction:
        nonlocal pos
        if depth > _CALC_MAX_DEPTH:
            raise _CalcError("too deep")
        item = peek()
        if item in ("+", "-"):
            pos += 1
            value = unary(depth + 1)
            return -value if item == "-" else value
        if item == "(":
            pos += 1
            value = expr(depth + 1)
            if peek() != ")":
                raise _CalcError("unbalanced")
            pos += 1
            return value
        if isinstance(item, Fraction):
            pos += 1
            return item
        raise _CalcError("operand expected")

    try:
        value = expr(0)
    except _CalcError:
        return None
    return value if pos == len(items) else None


def written_calculation_value(left: str) -> Optional[Fraction]:
    """The exact value of the calculation that ENDS ``left`` (the text before an '='), or None when ``left`` does not end
    in one (:func:`_calculation_run`) or the reader does not compute it. The run of the calculation is what stands
    right before the '=': prose before it is left out ("In 2025 output 4,200 − 3,000"), and a word right before the '='
    that is no unit of the last operand ("1/3 then x", "1/3 implies x": a variable the '=' is about) means ``left`` ends
    in no calculation. The reader is closed: numerals (thousands commas and an exponent allowed) and the vulgar
    fractions, ``+ − × ÷ * /`` and ``x`` between operands, parentheses, a per cent sign or word (a hundredth), currency
    marks (dropped), a scale word after a numeral (``15 million``), the unit of an operand (dropped: ``120 km ÷ 1.5 h``,
    ``3 tickets × $2.50``; only a unit or a currency word may end the calculation), and LaTeX read as plain marks
    (``\\frac``, ``\\times``); a single letter glued to a numeral (``3x + 2``) is a variable, so that text is an equation
    and no calculation. A power, a root, π, a function or implicit multiplication is a calculation it does not compute.
    Nothing is executed."""
    run = _calculation_run(left)
    if run is None:
        return None
    items = _calc_items(run)
    return _calc_parse(items) if items is not None else None


def _calculation_reading(figure: StatedFigure, computed: Fraction) -> Optional[Literal["exact", "rounded"]]:
    """``exact`` when the written calculation gives exactly the figure (as written, with its scale word, or as the
    fraction its per cent states), ``rounded`` when the figure rounds it to half a unit of its last written place,
    else None."""
    candidates = [(figure.value, figure.half_width)]
    if figure.scale != 1:
        candidates.append((figure.value * figure.scale, figure.half_width * figure.scale))
    if figure.is_percent_like and figure.unit_factor:
        candidates.append((figure.value * figure.scale * figure.unit_factor, figure.half_width * figure.scale * figure.unit_factor))
    if any(computed == v for v, _h in candidates):
        return "exact"
    if any(h and v - h <= computed <= v + h for v, h in candidates):
        return "rounded"
    return None


def approximate_text(value: Optional[Fraction]) -> str:
    """``value`` for a diagnostic: a terminating decimal, or ``a/b`` with six significant figures beside it."""
    if value is None:
        return "?"
    shown = _show(value)
    if "/" not in shown:
        return shown
    from decimal import Decimal
    return f"{shown} (≈ {format(Decimal(value.numerator) / Decimal(value.denominator), '.6g')})"


def _sig_fig_half_width(value: Fraction, sig: int) -> Optional[Fraction]:
    if value == 0:
        return None
    v = abs(value)
    exp = 0
    while v >= 10:
        v /= 10
        exp += 1
    while v < 1:
        v *= 10
        exp -= 1
    return Fraction(1, 2) * Fraction(10) ** (exp - sig + 1)


def _exactness_from_cue(cue: _Cue, figure: StatedFigure) -> Exactness:
    if cue.kind == "exact":
        return Exactness("exact", cue=cue.text, cue_start=cue.start, cue_end=cue.end)
    unit_step = figure.half_width * 2 if figure.half_width else Fraction(1)
    if cue.places is not None:
        half = Fraction(1, 2) * Fraction(10) ** (-cue.places)
    elif cue.sig_figs is not None:
        half = _sig_fig_half_width(figure.value, cue.sig_figs) or figure.half_width
    elif cue.nearest is not None:
        half = cue.nearest / 2
    else:
        half = figure.half_width
    if cue.mode != "nearest":
        step = half * 2 if half else unit_step
        return Exactness("rounded", cue=cue.text, cue_start=cue.start, cue_end=cue.end, mode=cue.mode, precision=cue.precision or "its last written place", step=step)
    return Exactness("rounded", cue=cue.text, cue_start=cue.start, cue_end=cue.end, precision=cue.precision or "half a unit of its last written place",
                     half_width=half)




@lru_cache(maxsize=512)
def _splitting_commas(text: str) -> tuple[int, ...]:
    """The positions of the commas of ``text`` that split clauses, in order: every comma except one between digits
    ('790,000')."""
    n = len(text)
    return tuple(k for k in range(n) if text[k] == "," and not (k > 0 and text[k - 1].isdigit() and k + 1 < n and text[k + 1].isdigit()))


@lru_cache(maxsize=512)
def _cue_starts(text: str) -> tuple[int, ...]:
    """The start of every cue of ``text`` (:func:`_cues`, which is ordered by start)."""
    return tuple(c.start for c in _cues(text))


@lru_cache(maxsize=512)
def _cue_reach(text: str) -> int:
    """The length of the longest cue of ``text`` (0 without one): a cue that starts at ``s`` ends by ``s`` plus this."""
    return max((c.end - c.start for c in _cues(text)), default=0)


@lru_cache(maxsize=4096)
def _run_before(text: str, pos: int) -> int:
    """The start of the run of spaces, commas and closing brackets that ends at ``pos``: the least ``q`` with
    ``text[q:pos]`` made of those characters only."""
    q = pos
    while q > 0 and text[q - 1] in " ,)":
        q -= 1
    return q


@lru_cache(maxsize=4096)
def _run_after(text: str, pos: int) -> int:
    """The end of the run of spaces, commas and opening brackets that starts at ``pos``: the first index from ``pos`` on
    whose character is none of those (``len(text)`` when there is none)."""
    r = pos
    while r < len(text) and text[r] in " ,(":
        r += 1
    return r


def _nearest_cue(text: str, lo: int, hi: int, figure: StatedFigure) -> _Cue:
    """``min(cues[lo:hi], key=(distance to the figure, not exact, generic))``, the first such cue in order, where
    ``cues[lo:hi]`` (non-empty) are cues of ``text`` in start order. It reads only the cues that can be nearest: the first
    ones starting at or after the figure (all at one distance), and those before it back to where even the longest cue
    (:func:`_cue_reach`) would end farther from the figure than the nearest found."""
    cues, starts, reach = _cues(text), _cue_starts(text), _cue_reach(text)

    def key(c: _Cue) -> tuple[int, bool, bool]:
        if c.end <= figure.start:
            d = figure.start - c.end
        elif c.start >= figure.end:
            d = c.start - figure.end
        else:
            d = 0
        return (d, c.kind != "exact", c.generic)

    best: Optional[tuple[tuple[int, bool, bool], int]] = None
    k = bisect_left(starts, figure.end, lo, hi)
    j = k
    while j < hi and starts[j] == starts[k]:
        cand = (key(cues[j]), j)
        if best is None or cand < best:
            best = cand
        j += 1
    i = k - 1
    while i >= lo:
        if best is not None and figure.start - (starts[i] + reach) > best[0][0]:
            break  # this cue, and every one before it, ends farther before the figure than the nearest found
        cand = (key(cues[i]), i)
        if best is None or cand < best:
            best = cand
        i -= 1
    assert best is not None, "a non-empty range of cues has a nearest one"
    return cues[best[1]]


def _clause_of(text: str, sentence: tuple[int, int], start: int, end: int) -> tuple[int, int]:
    """The comma-delimited clause of a sentence that holds a figure (a comma between digits, '790,000', splits nothing):
    from the nearest splitting comma before the figure to the nearest one after it, within the sentence (found by
    bisection, so reading every figure of a long sentence stays linear)."""
    a, b = sentence
    commas = _splitting_commas(text)
    left = a
    k = bisect_right(commas, start - 1) - 1
    if k >= 0 and commas[k] >= a:
        left = commas[k] + 1
    right = b
    k = bisect_left(commas, end)
    if k < len(commas) and commas[k] < b:
        right = commas[k]
    return left, right


def stated_exactness(figure: StatedFigure, text: str) -> Exactness:
    """How exactly ``text`` states ``figure`` (see the module docstring). The cue nearest the figure in its clause
    decides, else a cue that closes the clause before it or opens the clause after it ("x is 0.33, to 2 decimal
    places"; "then x is 0.33, without rounding"); an approximation cue counts only where it governs the figure
    (:func:`_approximation_cues`). With no cue, a figure written as the result of a calculation that ends at its '='
    is read from that calculation (exact when it gives exactly the figure, rounded when the figure rounds it) and is
    otherwise rounded by convention. A pure function of the figure and the text (both immutable), so it is cached: the
    grounding and evidence readings ask it of the same figure many times (repair round 5, ADV5-13)."""
    return _stated_exactness(figure, text)


@lru_cache(maxsize=8192)
def _stated_exactness(figure: StatedFigure, text: str) -> Exactness:
    sentence = sentence_of(text, figure.start, figure.end)
    clause = _clause_of(text, sentence, figure.start, figure.end)

    def distance(c: _Cue) -> int:
        if c.end <= figure.start:
            return figure.start - c.end
        if c.start >= figure.end:
            return c.start - figure.end
        return 0

    # The cues are ordered by start, so those of the sentence, and those of the clause within them, are slices; the work
    # per figure is bounded by the cues near it, not by every cue of a long sentence (linear in an untrusted text).
    all_cues, starts = _cues(text), _cue_starts(text)
    s_lo, s_hi = bisect_left(starts, sentence[0]), bisect_left(starts, sentence[1])
    c_lo, c_hi = bisect_left(starts, clause[0], s_lo, s_hi), bisect_left(starts, clause[1], s_lo, s_hi)
    governing = _approximation_cues(text, figure)
    if c_lo < c_hi:
        best = min([_nearest_cue(text, c_lo, c_hi, figure), *governing], key=lambda c: (distance(c), c.kind != "exact", c.generic))
        return _exactness_from_cue(best, figure)
    after = text[clause[1]:clause[1] + 3]
    before = text[max(sentence[0], clause[0] - 3):clause[0]]
    cues: list[_Cue] = []
    if before.rstrip().endswith(","):
        # a cue that closes the clause before: it ends in the run of ' ,)' before the clause, so it starts at most the
        # longest cue's length before that run
        run = _run_before(text, clause[0])
        lo = bisect_left(starts, run - _cue_reach(text), s_lo, s_hi)
        cues += [c for c in all_cues[lo:bisect_left(starts, clause[0], s_lo, s_hi)]
                 if c.end <= clause[0] and not text[c.end:clause[0]].strip(" ,)")]
    if after.startswith(","):
        # a cue that opens the clause after: it starts in the run of ' ,(' after the clause
        hi = bisect_right(starts, _run_after(text, clause[1] + 1), s_lo, s_hi)
        cues += [c for c in all_cues[bisect_left(starts, clause[1], s_lo, s_hi):hi]
                 if c.start >= clause[1] and not text[clause[1] + 1:c.start].strip(" ,(")]
    cues += governing
    if cues:
        best = min(cues, key=lambda c: (distance(c), c.kind != "exact", c.generic))
        return _exactness_from_cue(best, figure)
    calc = _calculation_result(text, figure, sentence)
    if calc is not None:
        written, left = calc
        computed = written_calculation_value(left)
        reading = _calculation_reading(figure, computed) if computed is not None else None
        if reading == "exact":
            return Exactness("exact", cue=written, computed=computed)
        return Exactness("rounded", cue=written, precision="half a unit of its last written place", half_width=figure.half_width,
                         by_convention=reading is None, computed=computed)
    return Exactness("unstated")


def tolerance_bounds(value: Fraction, exactness: Exactness, factor: Fraction = Fraction(1)) -> Optional[tuple[Fraction, Fraction, bool, bool]]:
    """``(lower, upper, lower inclusive, upper inclusive)`` of the values a rounded figure states, in the IR's unit (the
    tolerance multiplied by the derivation's ``factor``); None for a figure that is not rounded or has no tolerance."""
    if exactness.kind != "rounded":
        return None
    if exactness.mode == "nearest":
        if not exactness.half_width:
            return None
        h = exactness.half_width * factor
        return value - h, value + h, True, False
    if not exactness.step:
        return None
    step = exactness.step * factor
    if exactness.mode == "down":
        return (value, value + step, True, False) if value >= 0 else (value - step, value, False, True)
    return (value - step, value, False, True) if value >= 0 else (value, value + step, True, False)


def interval_text(bounds: tuple[Fraction, Fraction, bool, bool]) -> str:
    """``[0.325, 0.335)``: an interval for a diagnostic."""
    lo, hi, lo_incl, hi_incl = bounds
    return f"{'[' if lo_incl else '('}{_show(lo)}, {_show(hi)}{']' if hi_incl else ')'}"


def rounded_intervals(figure: StatedFigure, text: str, declared: Optional[DeclaredReading] = None) -> list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]]:
    """``(interval, derivation, exactness)`` for each interval the wording of a figure stated as ROUNDED gives it, in the
    IR's unit, one per derivation the symbol's declared reading admits (:func:`literal_matches`). Empty for a figure
    stated exactly, given with no cue, or rounded only by the convention of written calculation (a presumption, not a
    statement). How the figure's own words state it (plainly, or negated, or as one end of a range) is not read here:
    :func:`stated_intervals` reads it."""
    if declared is None:
        declared = DeclaredReading("none")
    ex = stated_exactness(figure, text)
    if ex.kind != "rounded" or ex.by_convention:
        return []
    return _intervals_of(figure, ex, declared)


def written_precision_intervals(figure: StatedFigure, text: str, declared: Optional[DeclaredReading] = None
                                ) -> list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]]:
    """The intervals a figure states at its WRITTEN precision, for the grounding checks: those of :func:`rounded_intervals`
    (a figure stated as rounded by a cue, "≈ 1.55", "about 30%", "to 2 d.p.", or by a calculation it rounds), and, for a
    figure written as the result of a calculation the closed reader does not compute (a power, a root, a decimal power
    of ten: rounded only by the convention of written calculation, with no computed value), the half-unit enclosure of
    its last written place ("10^(−8.2) = 6.31 × 10⁻⁹" states [6.305 × 10⁻⁹, 6.315 × 10⁻⁹); "… = 1.259" states
    [1.2585, 1.2595)). The source wrote that result to that many places, so the enclosure is what it states; whether a
    claim may use the interval rather than the figure itself is the precision decision's (:mod:`.precision`), not this
    reading's. A given figure with no cue and no calculation ("x is 0.33."), an exact figure, and a figure its own
    written calculation contradicts (a slip: "1.90 − 0.30 = 1.61") state no interval."""
    out = rounded_intervals(figure, text, declared)
    if out:
        return out
    ex = stated_exactness(figure, text)
    if ex.kind == "rounded" and ex.by_convention and ex.computed is None and ex.mode == "nearest" and ex.half_width:
        return _intervals_of(figure, ex, declared if declared is not None else DeclaredReading("none"))
    return []


def _intervals_of(figure: StatedFigure, ex: Exactness, declared: DeclaredReading) -> list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]]:
    """The intervals the exactness ``ex`` gives ``figure``, one per derivation the declared reading admits."""
    centres = {figure.value, figure.scaled}
    if figure.is_percent_like:
        centres.add(figure.scaled * (figure.unit_factor or Fraction(1, 100)))
    if declared.kind == "unit" and figure.unit_factor is not None and figure.unit_dim == declared.dim and declared.factor:
        centres.add(figure.scaled * figure.unit_factor / declared.factor)
    out: list[tuple[tuple[Fraction, Fraction, bool, bool], Match, Exactness]] = []
    seen: set[tuple[Fraction, Fraction, bool, bool]] = set()
    for centre in sorted(centres | {-c for c in centres}, key=lambda c: (c < 0, abs(c))):
        for m in literal_matches(centre, [figure], declared)[0]:
            bounds = tolerance_bounds(centre, ex, m.factor)
            if bounds is None or bounds in seen:
                continue
            seen.add(bounds)
            out.append((bounds, m, ex))
    return out


def interval_derivation(bounds: tuple[Fraction, Fraction, bool, bool], match: Match, exactness: Exactness) -> str:
    """The recorded derivation of an interval a rounded figure states ("supplied text doc characters 5-9 ('0.33') rounded
    ('to 2 decimal places', 2 decimal places): it states [0.325, 0.335)")."""
    via = "" if match.derivation.startswith("as written") else f", {match.derivation}"
    return f"{match.figure.where()} {exactness.describe()}{via}: it states {interval_text(bounds)}"


def figure_stated_plainly(figure: StatedFigure, text: str) -> bool:
    """Whether the figure's own words state it as a VALUE, plainly or approximately: not negated or excluded where it
    stands, not one option of a disjunction or one end of a range (:func:`.assertion.stated_as`), and not a bound ("at
    most 0.33 (2 d.p.)" bounds the value; it does not state the interval around 0.33: :func:`.assertion.relation_at`)."""
    from .assertion import relation_at, stated_as  # imported here: the reader imports this module
    return stated_as(text, figure.start, figure.end, "eq") is None and relation_at(text, figure.start, figure.end) in ("eq", "approx")


def stated_intervals(figure: StatedFigure, text: str, declared: Optional[DeclaredReading] = None) -> list[tuple[tuple[Fraction, Fraction, bool, bool], str]]:
    """The intervals a figure STATED AS ROUNDED states, in the IR's unit, one per derivation the symbol's declared reading
    admits (:func:`literal_matches`), as ``((lower, upper, lower inclusive, upper inclusive), derivation)``: "x is 0.33 to 2
    decimal places" states [0.325, 0.335); "about 23%", read as a dimensionless fraction, states [0.225, 0.235). The
    figure's own words must state it plainly or approximately (:func:`figure_stated_plainly`). Empty for a figure stated
    exactly, given with no cue, or rounded only by the convention of written calculation (a presumption, not a
    statement). Values compare by magnitude, as in :func:`literal_matches`, so the interval may lie on either side of 0."""
    intervals = rounded_intervals(figure, text, declared)
    if not intervals or not figure_stated_plainly(figure, text):
        return []
    return [(bounds, interval_derivation(bounds, m, ex)) for bounds, m, ex in intervals]


# ------------------------------------------------------------------ declared readings and typed correspondence

_DECL_PERCENT_RE = re.compile(r"\b(?:in|as\s+an?|as)\s+(?:a\s+)?(?:percent(?:age)?s?|per\s*-?\s*cent)\b|\(\s*%\s*\)|\bin\s+%|\(\s*(?:per\s*cent|percent)\s*[,)]"
                              r"|\bpercent(?:age)?\s+(?:value|figure)\b", re.IGNORECASE)
_DECL_FRACTION_RE = re.compile(r"\bdimensionless\b|\bas\s+a\s+(?:decimal|fraction|proportion)\b|\bdecimal\s+fraction\b|\bproportion\b|\bfraction\s+of\b",
                               re.IGNORECASE)
#: A scale the meaning declares for the symbol's unit ("in millions", "(million litres)", "$ billion"); a scale word that
#: follows a numeral ("about 13 billion dollars") glosses a value and declares nothing.
_DECL_SCALE_RE = re.compile(r"(?<![\d.,])(?<![\d.,]\s)\b(?:in\s+)?(?P<w>thousand|million|billion|trillion)s?\b", re.IGNORECASE)
_DECL_UNIT_RE = re.compile(r"\bin\s+(?P<u>[A-Za-zµμ°][A-Za-z0-9µμ°⁻¹²³/·^\- ]{0,14}?)(?=\s*[(,);.]|$)|\((?P<p>[^(),]{1,20})[,)]", re.IGNORECASE)


@lru_cache(maxsize=1024)
def declared_reading(meaning: Optional[str]) -> DeclaredReading:
    """The reading a symbol's meaning declares (see :class:`DeclaredReading`); ``none`` when it declares none."""
    if not meaning:
        return DeclaredReading("none")
    scale = 1
    sm = _DECL_SCALE_RE.search(meaning)
    if sm is not None:
        scale = _SCALE_WORDS[sm.group("w").lower()]
    if _DECL_FRACTION_RE.search(meaning):
        return DeclaredReading("fraction", factor=Fraction(1), dim="dimensionless", scale=scale, text=meaning)
    if _DECL_PERCENT_RE.search(meaning):
        return DeclaredReading("percent", factor=Fraction(1, 100), dim="dimensionless", scale=scale, text=meaning)
    found: list[tuple[bool, tuple[str, Fraction, str]]] = []
    for m in _DECL_UNIT_RE.finditer(meaning):
        token = (m.group("u") or m.group("p") or "").strip()
        token = re.sub(r"^(?:thousand|million|billion|trillion)s?\s+", "", token, flags=re.IGNORECASE)
        reading = _unit_reading(token) if token else None
        if reading is not None and reading[2] != "dimensionless":
            found.append((m.group("p") is not None, reading))
    if found:
        # a unit glossed in parentheses ("peak discharge in A (m³/s)") is the declaration, and an "in X" phrase before it is a
        # qualifier: a place, a group or a label ("in A", "in C") whose letter the unit table also reads (repair round 5, DA-5);
        # with no parenthesised unit the first "in X" unit declares, as before
        reading = next((r for glossed, r in found if glossed), found[0][1])
        return DeclaredReading("unit", factor=reading[1], dim=reading[2], scale=scale, text=meaning)
    return DeclaredReading("none", scale=scale, text=meaning)


def fraction_text(value: Fraction) -> str:
    """``value`` as an exact IR numeral: an integer, or a fraction ``a/b``."""
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _show(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    d = value.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:  # a terminating decimal
        from decimal import Decimal
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    return f"{value.numerator}/{value.denominator}"


def literal_matches(literal: Fraction, figures: Iterable[StatedFigure], declared: DeclaredReading = DeclaredReading("none")) -> tuple[list[Match], list[str]]:
    """The stated figures an IR ``literal`` corresponds to, each with its derivation, and the reasons a figure of the same
    number does NOT correspond under the symbol's declared reading (a unit mismatch). Values compare by magnitude: a
    text states a fall as a positive figure ("fell by 12")."""
    target = abs(literal)
    matches: list[Match] = []
    conflicts: list[str] = []
    for f in figures:
        v = abs(f.value)
        scaled = abs(f.scaled)
        candidates: list[tuple[Fraction, str, Fraction, str]] = []  # (value in the IR's unit, derivation, factor, reading it implies)
        if f.is_percent_like:
            ratio = f.unit_factor or Fraction(1, 100)
            candidates.append((scaled, f"as written ({f.written}, in {f.unit})", Fraction(f.scale), "percent"))
            candidates.append((scaled * ratio, f"{f.written} = {_show(scaled)} x {_show(ratio)} = {_show(scaled * ratio)} (dimensionless)", Fraction(f.scale) * ratio, "fraction"))
        else:
            candidates.append((v, f"as written ({f.written})", Fraction(1), "as_written"))
            if f.scale != 1:
                candidates.append((scaled, f"{f.written} = {_show(v)} x {f.scale:,} = {_show(scaled)}", Fraction(f.scale), "scaled"))
            if declared.kind == "unit" and f.unit_factor is not None and f.unit_dim == declared.dim and declared.factor:
                conv = f.unit_factor / declared.factor
                if conv != 1:
                    candidates.append((scaled * conv, f"{f.written} = {_show(scaled * conv)} in the symbol's declared unit", Fraction(f.scale) * conv, "converted"))
        for value, derivation, factor, implies in candidates:
            if value != target:
                continue
            reason = _reading_conflict(f, implies, declared)
            if reason is None:
                matches.append(Match(f, derivation, factor))
            else:
                conflicts.append(reason)
    return matches, conflicts


def _reading_conflict(f: StatedFigure, implies: str, declared: DeclaredReading) -> Optional[str]:
    """Why a value match is not a correspondence under the symbol's declared reading, or None."""
    if declared.kind == "fraction" and implies == "percent":
        return (f"{f.where()} states {f.written}, a percentage; the symbol is declared a dimensionless fraction, so the figure is "
                f"{_show(abs(f.scaled) * (f.unit_factor or Fraction(1, 100)))}, not {_show(abs(f.scaled))}")
    if declared.kind == "percent" and implies == "fraction":
        return f"{f.where()} states {f.written}; the symbol is declared in per cent, so the figure is {_show(abs(f.scaled))}, not its fraction"
    if declared.kind == "unit" and f.unit_dim is not None and f.unit_dim not in ("currency",) and declared.dim is not None and f.unit_dim != declared.dim:
        return f"{f.where()} states {f.written}, a {f.unit_dim}; the symbol is declared in a unit of {declared.dim}"
    if declared.kind == "unit" and implies == "as_written" and f.unit_factor is not None and declared.factor is not None and f.unit_dim == declared.dim \
            and f.unit_factor != declared.factor:
        return f"{f.where()} states {f.written}; in the symbol's declared unit the figure is {_show(abs(f.scaled) * f.unit_factor / declared.factor)}"
    if declared.scale != 1 and implies == "scaled":
        return f"{f.where()} states {f.written}; the symbol is declared in units of {declared.scale:,}, so the figure is {_show(abs(f.value))}"
    if declared.scale != 1 and implies == "as_written" and f.scale != declared.scale and f.scale != 1:
        return f"{f.where()} states {f.written}; the symbol is declared in units of {declared.scale:,}"
    return None


def sources_text(sources: Sequence[SourceText]) -> str:
    """The identities of ``sources`` for a diagnostic ('claim c1, supporting claim c2, supplied text doc')."""
    label = {"claim": "claim", "supporting_claim": "supporting claim", "supplied_text": "supplied text", "task": "task"}
    return ", ".join(f"{label[s.kind]} {s.ident}" for s in sources) or "no source text"
