"""Worked equations of the prose branches decided by the engine (Economics, Business Management and the generic branch).

A specialist of a prose subject writes its working in '=' form: ``Break-even quantity = $6,000 ÷ $2.00 = 3,000 loaves per
month``, ``Tax revenue = $0.40 × 105 million litres = $42 million``, ``Dependency ratio = 31 ÷ 69 × 100 = 44.9``, ``Growth rate =
(31 − 11) ÷ 10 = 2.0%``. :func:`~epinoic_logic.branches.quant.worked_equations` finds such a line (the prose arithmetic reader
names it undecided, CORE-QNT-001); this module reads its links as written arithmetic and builds the IR problem the engine decides,
so a wrong result (``= 2,000 loaves``) is the engine's INT-SUBJ-001 and a right one is ENTAILED. Nothing is evaluated: the text is
read by a closed grammar into IR nodes, and the division, the products and the comparison with the stated value are left to the
engine. Python reads digits only (the value of each written figure and half a unit in its last digit).

The reading (closed; anything outside it is not read, and the equation stays named undecided by CORE-QNT-001):

* figures in digits (thousands groups, a decimal, scientific notation through the STEM number reader ``stem.numbers.scan_number``:
  ``2.5 × 10³``), with an optional sign, a currency sign before them (``$``, ``US$``, ``£``, ``€``, ``¥``: a label of the unit of
  account, every figure of the line in one currency), a spelled-out scale word after them (``thousand``, ``million``, ``billion``,
  ``trillion``; ``m``, ``bn``, ``k``, ``tn`` glued to the figure or after a currency figure), a per cent sign (``%``, ``per cent``)
  and up to four unit words (``litres``, ``loaves per month``, ``people``), which are labels;
* the operators ``+``, ``−``, a spaced ``-`` or ``–``, ``×``, ``*``, ``·``, a spaced ``x``, ``÷`` and ``/``, brackets, and a
  whole power ``^n`` or ``ⁿ`` from 0 to 12; a hyphen between two digits (``15-64``) is a range label, not read;
* label words before the first figure of the first link (``The tax is $0.40 × ...``), unless their last word is one that takes part
  in the arithmetic (``half of``, ``twice``, ``the sum of``): then the line is not read;
* the formula written in symbols at the head of the working (``rs = 1 − (6 × Σd²) ÷ (n³ − n) = 1 − (6 × 66) ÷ (6³ − 6) = ...``,
  ``PV = 1000 ÷ (1 + r)^n = 1000 ÷ 1.05^3 = ...``): leading links that hold a letter the reading does not read are its statement,
  set aside when links of figures follow them; a letter in a later link refuses the line;
* a bracketed comment inside a link that holds words and no operator (``4.00% − 5.20% (inflation from paragraph [2])``) is set
  aside, and so is a restatement in brackets that holds an '=' (``0.762 million ÷ 12.70 million × 100 (762 thousand = 0.762 million)
  = 6.50%``: :func:`~epinoic_logic.branches.quant.worked_equations` cuts no link at it); a stated result written with its sign
  (``= +$53,900``) is read as its value;
* a relative change stated right after the result of a difference of two amounts (``Change = $4,125 million − $2,400 million =
  +$1,725 million per year (an increase of 71.88%)``) is a second problem of the line: ``(A − B) ÷ B`` against the stated per cent, a
  fall a negative change; it is read only when the stated difference has the direction's sign, so working written old minus new is
  never read the wrong way round;
* the stated result is the figure that opens the last link, with its scale word, per cent sign and unit words.

A line is not read when its figures carry two different units of measurement (the STEM unit table, or a unit of time such as
``month`` and ``year``: ``120 km ÷ 90 minutes = 80 km/h`` converts a unit the line does not write), when a divisor that is not a
single figure holds a quotient of its own, or when a product multiplies two quotients by expressions (each would make the problem
nonlinear), or when it is longer than the bounds (:data:`MAX_TOKENS`, :data:`MAX_DEPTH`).

Per cent readings. A per cent sign is read as a fraction (``5% × $200 = $10``); a stated result in per cent is also read as
written (``(31 − 11) ÷ 10 = 2.0%`` is the demographers' rate per cent from rates per 1,000), and, when an operand carries a per cent
sign and no figure of the line carries a currency sign, every per cent sign as written (``12.5% − 10.0% = 2.5 percentage points``;
``5% × $200 = $1,000`` has no such reading). The check fails only when the stated value lies outside its band under every reading
(the conclusion is the disjunction of the readings' bands), so an ambiguous per cent is never an error.

Scale words. A scale word governs the figure it follows (``105 million litres``), so a line whose operands carry their own
(``$600 × 4.0 million = $2,400 million``) is read as written. A specialist often writes the line's scale once, after the stated
result, for figures it reads from a table in that unit (``10.0 − 4.0 = 6.0 million tonnes per year`` for imports of 10.0 and 4.0
million tonnes): when the stated result carries a scale word and no operand does, the line is also read in that scale (the
operands and the result in the result's written units, ``h`` half a unit in its last written digit), beside the reading as
written (``$1,500,000 + $500,000 = $2 million``), and the check fails only when the stated value lies outside its band under both
readings (``10.0 − 4.0 = 7.0 million tonnes per year`` fails; ``10.0 million − 4.0 million = 7.0 million`` fails as written). A
correct line in one consistent scale is therefore never an error.

Parts in brackets. A figure stated with the sum or difference of its parts in brackets ('$11,300 (5,200 + 4,000 + 1,500 + 600)',
'$1,237.50 million per year in total ($712.50 + $525)') is read the same way (:func:`breakdown_problems`): the parts are the written
expression, the figure before the bracket its stated result. Years in brackets are no parts.

Tolerance (the STEM rule, ``stem.tolerance``): the stated value S passes when ``|C − S| ≤ h + τ·|C|`` for the value C of the
written expression; ``h`` is half a unit in S's last written digit (the trailing zeros of a whole number count only up to the
smallest significant-figure count of the measured operands: a decimal, scientific notation, a scale word or a unit word make an
operand measured), times S's scale; ``τ`` is 1/20 after ``≈`` or an approximation word, else 1/100; when every figure is exact (a
whole number with no scale or unit word), τ is 0 and h is half a unit in S's last digit for a result of two or more digits, else
0 (``7 ÷ 3 = 2`` fails, ``1,000 ÷ 3 = 333`` holds). The band is inside the IR, so the engine decides.

Scope: a worked-arithmetic check proves a property of its encoding only: that the written arithmetic holds, or does not, under the
readings named and the tolerance rule. It does not establish that the figures are true, that the formula is the right one for the
question, or that the units are right.
"""
from __future__ import annotations

import contextvars
import re
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from typing import Optional

from ..ir.schema import Problem
from ..stem.numbers import ExactNumber, scan_number
from ..stem.si_reading import SI_READING, si_unit
from ..stem.tolerance import TAU_APPROX, TAU_EQUAL, approx_word_in, band_expr
from .quant import worked_equations

__all__ = ["MAX_DEPTH", "MAX_TOKENS", "MAX_WORKED_CHECKS", "WORKED_RULE", "WORKED_SCOPE", "WorkedProblem", "breakdown_problems", "clock_problems",
           "decided_worked_chains", "payback_problems", "worked_problems"]

#: The most worked equations one report sends to the engine; the rest stay named undecided (CORE-QNT-001).
MAX_WORKED_CHECKS = 64
#: The most tokens a line of working is read with, and the deepest bracket nesting.
MAX_TOKENS = 80
MAX_DEPTH = 8
_MAX_POWER = 12

WORKED_SCOPE = ("Worked-arithmetic check: proves a property of its encoding only. It proves that the written arithmetic of the line holds, or does "
                "not hold, under the readings named and the tolerance rule; currency signs and unit words are labels. It does not establish that "
                "the figures are true, that the formula is the right one for the question, or that a unit is the right one.")
WORKED_RULE = ("tolerance: |C − S| ≤ h + τ·|C|; h: half a unit in S's last written digit (a whole number's trailing zeros only to the measured "
               "operands' significant figures), times its scale; τ: 1/20 after ≈ or about, else 1/100, and 0 with h only for a result of two or more "
               "digits when every figure is exact; a per cent sign read as a fraction and, for a stated result in per cent, as written; a scale word "
               "after the stated result only also read as the line's scale (h then in the result's written units)")

#: A currency sign, a dollar sign with its country letters included ('P$2,150', 'NZ$40', 'HK$5': clearance c3, ec-t16's P$ figures were
#: read as no figures, so a wrong product of them crossed with no finding)
_CUR = r"(?:US\$|U\.S\.\s?\$|[A-Z]{1,3}\$|\$|£|€|¥)"
_CUR_RE = re.compile(_CUR)
_SCALE_WORDS = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
_SCALE_ABBREV = {"k": 10**3, "m": 10**6, "bn": 10**9, "tn": 10**12, "trn": 10**12}
_SCALE_WORD_RE = re.compile(r"\s?(thousand|million|billion|trillion)(?![\w])", re.IGNORECASE)
_SCALE_GLUED_RE = re.compile(r"(k|m|bn|tn|trn)(?![\w])")
_SCALE_SPACED_RE = re.compile(r"\s(k|m|bn|tn|trn)(?![\w])")
_PCT_RE = re.compile(r"\s?(?:%|per\s?cent|percent(?!age))", re.IGNORECASE)
#: A unit word after a figure: letters (a glued '/' joins two: 'km/h'), never the multiplication sign 'x'.
_UNIT_WORD_RE = re.compile(r"\s+(?![xX](?![\w]))([A-Za-zµμΩ°][A-Za-zµμΩ°²³⁻¹'’-]*(?:/[A-Za-zµμΩ°][A-Za-zµμΩ°²³⁻¹-]*)*)")
_SUPER = {"⁰": 0, "¹": 1, "²": 2, "³": 3, "⁴": 4, "⁵": 5, "⁶": 6, "⁷": 7, "⁸": 8, "⁹": 9}
#: Units of time a line may convert without writing the factor ('per month' and 'per year'); the STEM unit table covers the rest.
_TIME_WORDS = {"year": "year", "years": "year", "yr": "year", "yrs": "year", "annum": "year", "month": "month", "months": "month", "week": "week",
               "weeks": "week", "decade": "decade", "decades": "decade", "century": "century", "centuries": "century", "day": "day", "days": "day",
               "hour": "hour", "hours": "hour", "minute": "minute", "minutes": "minute", "second": "second", "seconds": "second"}
#: Words that take part in the arithmetic when they end the words before the first figure ('half of', 'twice', 'the sum of').
_ARITHMETIC_WORDS = frozenset("""of times twice thrice half halves third thirds quarter quarters double doubled triple tripled by per over than plus minus less
    more from into between sum product difference quotient average mean total root square cube ratio percent percentage fraction""".split())
_APPROX_SIGN_RE = re.compile(r"[≈≃~]")
#: Words after a figure that are English, never a unit symbol ('in' is no inch in '$6,000 in fixed costs').
_LABEL_WORDS = frozenset("per a an each every of in on at to is as by or and the for from with are was were be".split())


class _Refuse(Exception):
    """The line is outside the reading: it is not read, and stays named undecided."""


class _SymbolRefuse(_Refuse):
    """A link holds a letter the reading does not read (a symbol of a formula: 'Σd²', 'n³ − n', '(1 + r)^n')."""


@dataclass(frozen=True)
class _Fig:
    number: ExactNumber
    scale: int                    # the power of ten a scale word multiplies by (0 for none)
    percent: bool
    units: tuple[str, ...]        # the unit words after the figure
    cur: str
    text: str

    @property
    def value(self) -> Fraction:
        return self.number.value * Fraction(10) ** self.scale

    @property
    def measured(self) -> bool:
        return bool(self.number.has_point or self.number.scientific or self.scale or self.units)


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t   ":
        i += 1
    return i


def _read_figure(s: str, i: int) -> tuple[_Fig, int]:
    """One figure of a link at ``s[i:]`` (a currency sign first), with its scale word, per cent sign and unit words."""
    start = i
    cur = ""
    m = _CUR_RE.match(s, i)
    if m:
        cur = m.group(0).replace(" ", "").replace("U.S.", "US")
        cur = "$" if cur in ("US$", "$") else cur
        i = _skip_ws(s, m.end())
    if i >= len(s) or not (s[i].isdigit() and s[i].isascii() or (s[i] == "." and i + 1 < len(s) and s[i + 1].isdigit())):
        raise _Refuse("no figure")
    point_groups = _POINT_GROUPS.get()
    scan = scan_number(s, i, thousands_point=point_groups, thousands_comma=not point_groups)
    if scan is None or scan.number is None:
        raise _Refuse("a figure outside the number reader's bounds")
    j = scan.end
    if j < len(s) and s[j].isdigit() and s[j] not in _SUPER:  # a superscript after the figure is its power ('6³'), read as a token
        raise _Refuse("a figure read in part")
    if j < len(s) and s[j] in ",." and j + 1 < len(s) and s[j + 1].isdigit():
        raise _Refuse("a decimal comma or a broken thousands group")
    scale = 0
    sm = _SCALE_GLUED_RE.match(s, j)
    if sm is None:
        sm = _SCALE_WORD_RE.match(s, j)
    if sm is None and cur:
        sm = _SCALE_SPACED_RE.match(s, j)
    if sm is not None:
        word = sm.group(1).lower()
        scale = len(str(_SCALE_WORDS.get(word) or _SCALE_ABBREV[word])) - 1
        j = sm.end()
    percent = False
    pm = _PCT_RE.match(s, j)
    if pm is not None:
        percent = True
        j = pm.end()
    units: list[str] = []
    while len(units) < 4:
        um = _UNIT_WORD_RE.match(s, j)
        if um is None:
            break
        word = um.group(1)
        if word.lower() in ("x",):
            break
        units.append(word)
        j = um.end()
    return _Fig(scan.number, scale, percent, tuple(units), cur, s[start:j].strip()), j


_OPS = {"+": "+", "−": "-", "×": "*", "*": "*", "·": "*", "÷": "/", "/": "/"}


def _tokens(link: str) -> list:
    """The tokens of one link: ('fig', _Fig), ('op', '+-*/'), ('(',), (')',), ('pow', n)."""
    out: list = []
    s = link
    i = _skip_ws(s, 0)
    while i < len(s):
        if len(out) > MAX_TOKENS:
            raise _Refuse("too long")
        ch = s[i]
        prev_operand = bool(out) and out[-1][0] in ("fig", ")", "pow")
        if ch in "([":
            out.append(("(",))
            i += 1
        elif ch in ")]":
            out.append((")",))
            i += 1
        elif ch in _OPS:
            out.append(("op", _OPS[ch]))
            i += 1
        elif ch in "-–":
            # a hyphen or dash between two digits is a range label ('15-64'); a spaced one, or one before a figure, is a minus
            glued = i > 0 and s[i - 1].isdigit() and i + 1 < len(s) and s[i + 1].isdigit()
            if glued or (ch == "–" and prev_operand and not (i > 0 and s[i - 1] == " " and i + 1 < len(s) and s[i + 1] == " ")):
                raise _Refuse("a range or a dash between figures")
            out.append(("op", "-"))
            i += 1
        elif ch in "xX" and prev_operand and (i + 1 >= len(s) or not s[i + 1].isalnum()) and (i == 0 or not s[i - 1].isalnum()):
            out.append(("op", "*"))
            i += 1
        elif ch == "^":
            m = re.match(r"\^\{?(\d{1,2})\}?", s[i:])
            if not m or not prev_operand:
                raise _Refuse("a power outside the reading")
            out.append(("pow", int(m.group(1))))
            i += m.end()
        elif ch in _SUPER and prev_operand:
            j = i
            digits = ""
            while j < len(s) and s[j] in _SUPER:
                digits += str(_SUPER[s[j]])
                j += 1
            out.append(("pow", int(digits)))
            i = j
        elif ch in _VULGAR:
            if prev_operand:
                raise _Refuse("two figures with no operator between them")
            out.append(("fig", _Fig(ExactNumber(text=ch, value=_VULGAR[ch], sig_figs=1, last_place=0, exact=True, vulgar=True), 0, False, (), "", ch)))
            i += 1
        elif ch.isdigit() and ch.isascii() or ch == "." or _CUR_RE.match(s, i):
            if prev_operand:
                raise _Refuse("two figures with no operator between them")
            fig, i = _read_figure(s, i)
            out.append(("fig", fig))
        elif ch.isalpha():
            raise _SymbolRefuse(f"a character outside the reading ({ch!r})")
        else:
            raise _Refuse(f"a character outside the reading ({ch!r})")
        i = _skip_ws(s, i)
    return out


class _Parser:
    """A recursive-descent reading of the tokens into a small tree (closed grammar)."""

    def __init__(self, tokens: list) -> None:
        self.t = tokens
        self.k = 0
        self.depth = 0

    def peek(self):
        return self.t[self.k] if self.k < len(self.t) else None

    def take(self):
        tok = self.peek()
        self.k += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.peek() is not None:
            raise _Refuse("tokens left over")
        return node

    def expr(self):
        node = self.term()
        while (tok := self.peek()) is not None and tok[0] == "op" and tok[1] in "+-":
            self.take()
            right = self.term()
            node = ("add", node, right) if tok[1] == "+" else ("sub", node, right)
        return node

    def term(self):
        node = self.unary()
        while (tok := self.peek()) is not None and tok[0] == "op" and tok[1] in "*/":
            self.take()
            right = self.unary()
            node = ("mul", node, right) if tok[1] == "*" else ("div", node, right)
        return node

    def unary(self):
        tok = self.peek()
        if tok is not None and tok[0] == "op" and tok[1] in "+-":
            self.take()
            arg = self.unary()
            return ("neg", arg) if tok[1] == "-" else arg
        return self.power()

    def power(self):
        node = self.primary()
        while (tok := self.peek()) is not None and tok[0] == "pow":
            self.take()
            if tok[1] > _MAX_POWER:
                raise _Refuse("a power beyond 12")
            node = ("pow", node, tok[1])
        return node

    def primary(self):
        tok = self.take()
        if tok is None:
            raise _Refuse("an operand is missing")
        if tok[0] == "fig":
            return ("fig", tok[1])
        if tok[0] == "(":
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise _Refuse("brackets nested too deep")
            node = self.expr()
            close = self.take()
            if close is None or close[0] != ")":
                raise _Refuse("an unclosed bracket")
            self.depth -= 1
            return node
        raise _Refuse("an operator where an operand belongs")


def _figures(node) -> list[_Fig]:
    if node[0] == "fig":
        return [node[1]]
    out: list[_Fig] = []
    for child in node[1:]:
        if isinstance(child, tuple):
            out += _figures(child)
    return out


def _real(f: Fraction) -> dict:
    return {"op": "real", "value": f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)}


def _var(name: str) -> dict:
    return {"op": "var", "name": name}


class _Encoder:
    """One reading's IR: ``pct_operands`` reads an operand's per cent sign as a fraction (True) or as written (False)."""

    def __init__(self, tag: str, pct_operands: bool) -> None:
        self.tag = tag
        self.pct_operands = pct_operands
        self.aux: list[tuple[str, dict, dict, str]] = []   # (name, definition, guard, label)

    def enc(self, node, shown: str) -> tuple[dict, bool]:
        kind = node[0]
        if kind == "fig":
            f: _Fig = node[1]
            v = f.value / 100 if (f.percent and self.pct_operands) else f.value
            return _real(v), True
        if kind == "neg":
            e, closed = self.enc(node[1], shown)
            return {"op": "neg", "arg": e}, closed
        if kind in ("add", "sub", "mul"):
            (a, ca), (b, cb) = self.enc(node[1], shown), self.enc(node[2], shown)
            if kind == "add":
                args = (a["args"] if a.get("op") == "add" else [a]) + (b["args"] if b.get("op") == "add" else [b])
                return {"op": "add", "args": args}, ca and cb
            if kind == "sub":
                return {"op": "sub", "left": a, "right": b}, ca and cb
            if not ca and not cb:
                raise _Refuse("a product of two quotients by expressions")
            args = (a["args"] if a.get("op") == "mul" else [a]) + (b["args"] if b.get("op") == "mul" else [b])
            return {"op": "mul", "args": args}, ca and cb
        if kind == "div":
            a, ca = self.enc(node[1], shown)
            divisor = node[2]
            sign = 1
            while divisor[0] == "neg":
                sign, divisor = -sign, divisor[1]
            if divisor[0] == "fig":
                f = divisor[1]
                v = f.value / 100 if (f.percent and self.pct_operands) else f.value
                if v == 0:
                    raise _Refuse("a division by zero")
                return {"op": "div", "left": a, "right": _real(sign * v)}, ca
            b, cb = self.enc(node[2], shown)
            if not cb:
                raise _Refuse("a divisor that holds a quotient of its own")
            if not ca:
                raise _Refuse("a quotient of a quotient by an expression")
            name = f"q{self.tag}_{len(self.aux) + 1}"
            definition = {"op": "eq", "left": {"op": "mul", "args": [_var(name), b]}, "right": a}
            guard = {"op": "ne", "left": b, "right": _real(Fraction(0))}
            self.aux.append((name, definition, guard, f"{name} is a quotient of the written expression {shown}"))
            return _var(name), False
        if kind == "pow":
            base, closed = self.enc(node[1], shown)
            n = node[2]
            if n == 0:
                return _real(Fraction(1)), True
            if n == 1:
                return base, closed
            if not closed:
                raise _Refuse("a power of a quotient by an expression")
            return {"op": "mul", "args": [base] * n}, True
        raise _Refuse("a node outside the reading")


def _unit_key(word: str) -> Optional[str]:
    """The unit of measurement a unit word names (the STEM unit table or a unit of time), or None for a label ('loaves', 'people')."""
    w = word.strip("'’-")
    low = w.lower()
    if low in _TIME_WORDS:
        return _TIME_WORDS[low]
    if low in _LABEL_WORDS:
        return None
    try:
        u = si_unit(w, SI_READING.profile)
    except Exception:  # noqa: BLE001 - an unreadable word is a label
        u = None
    if u is not None and u.factor == 1 and not u.affine and not any(u.dim.exps) and not u.dim.angle:
        return None  # a pure count ('loaves', 'people', 'items', when the unit table reads count nouns): a label, no unit to convert
    return f"{w}" if u is not None else None


def _compound_key(f) -> str:
    """The figure's unit words that name units of measurement, as one compound unit ("m³ s⁻¹"), or ""."""
    return " ".join(k for w in f.units for k in [_unit_key(w)] if k)


def _products_only(trees) -> bool:
    """True when no link of the line adds or subtracts (products, quotients, powers and signs only)."""
    def walk(node) -> bool:
        if node[0] in ("add", "sub"):
            return False
        return all(walk(child) for child in node[1:] if isinstance(child, tuple))
    return all(walk(t) for t in trees)


def _coherent_si(word: str) -> bool:
    """A unit word of the coherent SI (a factor of one to the SI base units, no offset: 'm', 'm²', 's⁻¹', 'kg', 'N'): figures in such units
    multiply and divide as written. 'km', 'cm', 'minutes' or '°C' are not."""
    w = word.strip("'’-")
    if w.lower() in _TIME_WORDS and w.lower() not in ("second", "seconds"):
        return False
    try:
        u = si_unit(w, SI_READING.profile)
    except Exception:  # noqa: BLE001 - an unreadable word is not a unit read as coherent
        return False
    return u is not None and u.factor == 1 and not u.affine


@dataclass(frozen=True)
class _Read:
    phrase: str
    statement: str
    links: tuple            # parsed expression links (trees)
    shown_links: tuple[str, ...]
    result: _Fig
    approx: bool


#: Blanks and opening quotation marks: what may stand before a line's working without being a label of it.
_OPENING_MARKS = " \t\"'“‘«„"
#: Vulgar fractions read as exact figures ('½ × $150 × (5.5 − 4.0)': round 9, c1 adversarial 14).
_VULGAR = {"½": Fraction(1, 2), "⅓": Fraction(1, 3), "⅔": Fraction(2, 3), "¼": Fraction(1, 4), "¾": Fraction(3, 4), "⅕": Fraction(1, 5), "⅛": Fraction(1, 8)}
_VULGAR_CHARS = "".join(_VULGAR)
#: Where the words before a line's arithmetic end their clause: a comma, a semicolon, 'so', 'giving', 'which is', or a copula that ends
#: the words ('so the loan needed is $60,000 − $45,000', 'At 7%, interest is $15,000 × 7%'). Read on the head only (bounded by the link).
_HEAD_BOUNDARY_RE = re.compile(r"[,;]|\b(?:so|thus|hence|giving|gives?|gave|says?|said|which\s+is|that\s+is|i\.e\.|is|are|was|were|equals?|comes\s+to)\b", re.IGNORECASE)
#: The start of a figure of the arithmetic, read back from its first digit: a sign, a currency sign, an opening bracket, blanks.
_FIGURE_LEAD_CHARS = frozenset(" \t([−-+$£€¥")


def _arithmetic_start(link: str) -> Optional[int]:
    """Where the arithmetic of the link starts: the first figure an operator follows (quant's ``_OPERATOR_BETWEEN_RE``), with the sign,
    currency sign and brackets written before it; None when no operator stands between two figures."""
    from .quant import _OPERATOR_BETWEEN_RE
    m = _OPERATOR_BETWEEN_RE.search(link)
    if m is None:
        return None
    i = m.start()
    while i > 0 and link[i - 1] in _FIGURE_LEAD_CHARS:
        i -= 1
    if i >= 2 and link[i - 2:i] == "US":
        i -= 2
    return i


def _strip_label(link: str) -> str:
    """The first link without the label words before its first figure ('The tax is $0.40 × ...'), or a refusal when those words take
    part in the arithmetic ('half of $6,000 ÷ 2'). Words before the arithmetic that hold figures of their own ('Option 1 costs $60,000
    against $45,000 of cash, so the loan needed is $60,000 − $45,000', 'At 7%, interest is $15,000 × 7%') are cut at the last clause
    boundary before the arithmetic (:data:`_HEAD_BOUNDARY_RE`; round 9, c1 stem-integration 27): what follows the boundary is read by the
    label rule, and the line is refused when no boundary separates the figures from the arithmetic."""
    m = re.search(rf"[\d(\[{_VULGAR_CHARS}]|{_CUR}|[-−]\s*(?:{_CUR}\s*)?\d|\.\d", link)
    if m is None:
        raise _Refuse("no figure")
    head = link[:m.start()]
    if not head.strip(_OPENING_MARKS):
        return link[m.start():] if head.strip() else link  # an opening quotation mark before the working ('("13,700 / 7,000 = 1.96")') is no label
    if re.search(r"\d", head) or not re.fullmatch(r"[\s\w'’:,.\-]+", head):
        raise _Refuse("label words outside the reading")
    words = re.findall(r"[A-Za-z]+", head)
    if words and words[-1].lower() in _ARITHMETIC_WORDS and not (
            words[-1].lower() == "of" and len(words) >= 2 and words[-2].lower() not in _ARITHMETIC_WORDS):
        # ("half of $6,000 ÷ 2" takes part; "a doubling time of 70 ÷ 2" names the working's result, attack round 3)
        raise _Refuse("label words that take part in the arithmetic")
    return link[m.start():]


#: A word formula before the figures it is worked with, closed by 'here' or 'so' ('stock ÷ current liabilities, here 6,200 ÷ 7,000'): words,
#: the operators between them and brackets, no figure. Bounded by the link.
_WORD_FORMULA_HEAD_RE = re.compile(r"[A-Za-z][\w'’ ()÷×*/+−–-]{0,200}?,?\s*+(?:here|so|that\s++is|i\.e\.|giving|gives)\s*+:?\s*+")


def _strip_head(link: str) -> str:
    """The first link without the words before its arithmetic: :func:`_strip_label`'s rule, and two more heads (round 9, c1 adversarial 14
    and stem-integration 27). Words before the arithmetic that hold figures of their own ('Option 1 costs $60,000 against $45,000 of cash,
    so the loan needed is $60,000 − $45,000', 'At 7%, interest is $15,000 × 7%') are cut at the last clause boundary before the arithmetic
    (:data:`_HEAD_BOUNDARY_RE`): what follows the boundary is read by the label rule, and the line is refused when no boundary separates the
    figures from the arithmetic or when the words after it take part in the arithmetic. A word formula closed by 'here' ('stock ÷ current
    liabilities, here 6,200 ÷ 7,000') is the statement of the working that follows it."""
    first = re.search(rf"[\d(\[{_VULGAR_CHARS}]|{_CUR}|[-−]\s*(?:{_CUR}\s*)?\d|\.\d", link)
    start = _arithmetic_start(link) if first is not None and link[:first.start()].strip(_OPENING_MARKS) else None
    if start is not None and start > 0 and len(link) <= 2000:
        head = link[:start]
        if re.search(r"\d", head):
            cuts = list(_HEAD_BOUNDARY_RE.finditer(head))
            rest = head[cuts[-1].end():] if cuts else head
            if not cuts or re.search(r"\d", rest) or not re.fullmatch(r"[\s\w'’:.\-]*", rest):
                raise _Refuse("label words outside the reading")
            words = re.findall(r"[A-Za-z]+", rest)
            if words and words[-1].lower() in _ARITHMETIC_WORDS and not (
                    words[-1].lower() == "of" and len(words) >= 2 and words[-2].lower() not in _ARITHMETIC_WORDS):
                raise _Refuse("label words that take part in the arithmetic")
            return link[start:]
        if _WORD_FORMULA_HEAD_RE.fullmatch(head):
            return link[start:]
    return _strip_label(link)


#: Whether the statement being read is Spanish: there a point separates thousands ("50.000 habitantes"), never decimals.
_POINT_GROUPS: contextvars.ContextVar = contextvars.ContextVar("worked_point_groups", default=False)


def _read(phrase: str, statement: str) -> _Read:
    from ..stem.lexer import _spanish_text
    token = _POINT_GROUPS.set(_spanish_text(statement, 0, len(statement)))
    try:
        return _read_inner(phrase, statement)
    finally:
        _POINT_GROUPS.reset(token)


def _read_inner(phrase: str, statement: str) -> _Read:
    parts = re.split(r"([=≈])", phrase)
    links = parts[0::2]
    seps = parts[1::2]
    if len(links) < 2:
        raise _Refuse("no stated result")
    links = [_strip_head(links[0])] + links[1:]
    *expr_links, result_link = links
    # a comment in brackets inside the working ('4.00% − 5.20% (inflation from paragraph [2])', '(units cancel)'): words and no operator,
    # so no part of the arithmetic; it is set aside before the link is read (c1 adversarial: such a chain was named undecided only)
    expr_links = [_COMMENT_RE.sub(" ", link) for link in expr_links]
    trees = []
    kept: list[str] = []
    for k, link in enumerate(expr_links):
        try:
            toks = _tokens(link)
        except _SymbolRefuse:
            if not trees and k + 1 < len(expr_links):
                # the formula written in symbols before the working ('1 − (6 × Σd²) ÷ (n³ − n) = 1 − (6 × 66) ÷ (6³ − 6) = 1 − 396 ÷ 210
                # = ...'): its statement, not a figure of the working, set aside as the label words before the first figure are, when
                # links of figures follow it; a symbol in a later link still refuses the line (c1 adversarial ge-t14-rs)
                continue
            raise
        if not any(t[0] == "op" or t[0] == "pow" for t in toks):
            raise _Refuse("a link that is not an expression")
        trees.append(_Parser(toks).parse())
        kept.append(link)
    expr_links = kept
    rl = result_link.strip()
    sign = 1
    if rl[:1] == "+":
        rl = rl[1:].lstrip()  # a stated gain written with its sign ('= +$53,900')
    while rl[:1] in "-−":
        sign = -sign
        rl = rl[1:].lstrip()
    cur_first = _CUR_RE.match(rl)
    if cur_first:
        after = rl[cur_first.end():].lstrip()
        if after[:1] == "+":
            rl = rl[:cur_first.end()] + after[1:]
            after = after[1:]
        if after[:1] in "-−":
            sign = -sign
            rl = rl[:cur_first.end()] + after[1:]
    result, _end = _read_figure(rl, 0)
    if sign < 0:
        result = _Fig(replace(result.number, value=-result.number.value), result.scale, result.percent, result.units, result.cur, "−" + result.text)
    figs = [f for t in trees for f in _figures(t)] + [result]
    curs = {f.cur for f in figs if f.cur}
    if len(curs) > 1:
        raise _Refuse("figures in two currencies")
    units = {k for f in figs for w in f.units for k in [_unit_key(w)] if k}
    # (the unit words of one figure are ONE compound unit, "5.2 m³ s⁻¹": an additive chain whose figures share it, or whose operands
    # carry none, converts nothing; attack round 6 read m³ and s⁻¹ as two units and left '5.4 − 1.2 = 5.2 m³ s⁻¹' unread)
    compound = {_compound_key(f) for f in figs if _compound_key(f)}
    if len(units) > 1 and len(compound) == 1:
        units = compound
    if len(units) > 1 and not (_products_only(trees) and all(_coherent_si(u) for u in units)):
        # two units of measurement: a conversion the line does not write ('120 km ÷ 90 minutes = 80 km/h'), unless the line only multiplies
        # and divides figures in coherent SI units, whose product is the result's unit as written ('6.0 m × 1.8 m = 10.8 m²', '10.8 m² ×
        # 1.5 m s⁻¹ = 16.2 m³ s⁻¹': round 9, c2 ge-p9c)
        raise _Refuse("figures in two units of measurement")
    approx = bool(_APPROX_SIGN_RE.search("".join(seps))) or approx_word_in(statement[: max(0, statement.find(result_link.strip()))] if result_link.strip() in statement else statement)
    return _Read(phrase, statement, tuple(trees), tuple(" ".join(x.split()) for x in expr_links), result, approx)


#: A bracketed comment of a link: at least one word of three letters and no arithmetic operator or '=' inside (bounded: 120 characters).
_COMMENT_RE = re.compile(r"\s{0,3}\((?=[^()\n]{0,120}?[A-Za-z]{3})[^()\n=+×÷*/−–^-]{1,120}\)")


@lru_cache(maxsize=32)
def _reads(text: str) -> tuple[tuple[str, str, Optional[_Read], str], ...]:
    """``(phrase, statement, read or None, why not)`` for every worked equation of ``text``, at most :data:`MAX_WORKED_CHECKS` read; a
    relative change stated after a difference's result (:func:`_relative_change_read`) is read after its equation, its ``why`` the tag
    :data:`_RELATIVE_TAG`."""
    out: list[tuple[str, str, Optional[_Read], str]] = []
    n_read = 0  # counted as the reads are made (a sum over the list at every equation was quadratic in the number of equations)
    for eq in worked_equations(text):
        if n_read >= MAX_WORKED_CHECKS:
            out.append((eq.phrase, eq.statement, None, "the limit of worked-arithmetic checks per report was reached"))
            continue
        try:
            r = _read(eq.phrase, eq.statement)
            Problem.model_validate(_problem(r, pid="worked-check", claim_id="worked-check", request_id="worked-check")[0])  # the IR's own schema
            out.append((eq.phrase, eq.statement, r, ""))
            n_read += 1
        except _Refuse as why:
            out.append((eq.phrase, eq.statement, None, str(why)))
            continue
        except Exception as exc:  # noqa: BLE001 - never an exception on agent text; the equation stays named undecided (CORE-QNT-001)
            out.append((eq.phrase, eq.statement, None, f"not read ({type(exc).__name__})"))
            continue
        if n_read >= MAX_WORKED_CHECKS:
            continue
        try:
            rel = _relative_change_read(r)
            if rel is not None:
                Problem.model_validate(_problem(rel, pid="worked-check", claim_id="worked-check", request_id="worked-check")[0])
                out.append((rel.phrase, rel.statement, rel, _RELATIVE_TAG))
                n_read += 1
        except Exception:  # noqa: BLE001 - never an exception on agent text: the relative change is left to the prose reader
            pass
    return tuple(out)


#: The ``why`` of a relative change read after its difference (:func:`_relative_change_read`), so its check is described as such.
_RELATIVE_TAG = "relative change of the difference"
#: A relative change written right after a difference's stated result: '= +$1,725 million per year (an increase of 71.88%)', ', a fall of
#: 4.2%'. Bounded: at most 40 characters of unit words between the result and the change; the per cent ends its bracket or clause.
_REL_CHANGE_AFTER_RE = re.compile(
    r"^[^()\n%=]{0,40}?[\s,;(]{1,3}(?:an?\s+)?(?:(?P<up>increase|rise|growth|gain)|(?P<down>decrease|fall|drop|decline|reduction))\s+of\s+"
    r"(?P<pct>\d{1,4}(?:\.\d{1,6})?\s?(?:%|per\s?cent))(?=\s*(?:\)|[.;,]|$))", re.IGNORECASE)


def _relative_change_read(r: _Read) -> Optional[_Read]:
    """The relative change a line states right after the result of a difference of two figures ('Change = $4,125 million − $2,400 million =
    +$1,725 million per year (an increase of 71.88%)'): the change of the first figure on the second, ``(A − B) ÷ B``, against the stated
    per cent (a fall is a negative change), or None. Read only when the line is that one difference, both figures are amounts in one
    currency with no per cent sign, and the stated result's sign is the direction's ('an increase' of a positive difference, 'a fall' of a
    negative one), so 'old − new' working is never read the wrong way round."""
    if len(r.links) != 1:
        return None
    tree = r.links[0]
    if not (tree[0] == "sub" and tree[1][0] == "fig" and tree[2][0] == "fig"):
        return None
    a, b = tree[1][1], tree[2][1]
    if a.percent or b.percent or r.result.percent or a.cur != b.cur or b.value == 0 or r.result.value == 0:
        return None
    at = r.statement.find(r.phrase)
    if at < 0:
        return None
    m = _REL_CHANGE_AFTER_RE.match(r.statement[at + len(r.phrase):])
    if m is None or (m.group("up") is not None) != (r.result.value > 0):
        return None
    pct, _end = _read_figure(m.group("pct"), 0)
    if m.group("down") is not None:
        pct = _Fig(replace(pct.number, value=-pct.number.value), pct.scale, pct.percent, pct.units, pct.cur, "−" + pct.text)
    shown = f"({a.text} − {b.text}) ÷ {b.text}"
    rel_tree = ("div", ("sub", ("fig", a), ("fig", b)), ("fig", b))
    words = " ".join(m.group(0).strip(" ,;(").split())
    return _Read(f"{r.phrase} ({words})", r.statement, (rel_tree,), (shown,), pct, r.approx)


@dataclass(frozen=True)
class WorkedProblem:
    """One worked equation as an engine problem: ``phrase`` (the written arithmetic), ``statement`` (its sentence), the IR problem
    (a plain mapping the caller validates) and the check's description."""
    phrase: str
    statement: str
    problem: dict
    description: str


def _fmt(f: Fraction) -> str:
    if f.denominator == 1:
        return str(f.numerator)
    d = f.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    return f"{float(f):.12g}" if d == 1 else str(f)


#: The name of a scale for the reading that lets the stated result's scale word govern the line.
_SCALE_NAMES = {3: "thousands", 6: "millions", 9: "billions", 12: "trillions"}


def _problem(r: _Read, *, pid: str, claim_id: str, request_id: str) -> tuple[dict, str]:
    operands = [f for t in r.links for f in _figures(t)]
    S = r.result
    has_pct_operand = any(f.percent for f in operands)
    base: list[tuple[str, bool, bool]] = [("per cent as a fraction" if (has_pct_operand or S.percent) else "as written", True, True)]
    if S.percent:
        base.append(("the stated per cent as written, an operand's per cent as a fraction" if has_pct_operand else "the stated per cent as written", True, False))
    if has_pct_operand and not S.cur and not any(f.cur for f in operands):
        # per-cent arithmetic stated in per cent or in points ('12.5% − 10.0% = 2.5 percentage points'); never for an amount of money
        # ('5% × $200 = $1,000' is no reading of a tax of 5 per cent)
        base.append(("every per cent as written", False, False))
    # a scale word written once, after the stated result, for operands that carry none ('10.0 − 4.0 = 6.0 million tonnes per year'):
    # the line is also read in the result's scale (its figures in the result's written units), beside the reading as written
    # ('$1,500,000 + $500,000 = $2 million'); readings: (label, an operand's per cent as a fraction, the stated per cent as a fraction,
    # the stated value at its written scale)
    readings: list[tuple[str, bool, bool, bool]] = [(label, a, b, True) for label, a, b in base]
    if S.scale and not S.percent and not any(f.scale for f in operands):
        scale_name = _SCALE_NAMES.get(S.scale, f"units of 10^{S.scale}")
        readings = [(f"the scale word after the result governs the line (every figure in {scale_name})" + (f", {label}" if label != "as written" else ""), a, b, False)
                    for label, a, b in base] + readings
    exact = (not r.approx and all(not f.measured for f in operands) and not S.measured)
    measured_sf = [f.number.sig_figs for f in operands if f.measured]
    min_sf = min(measured_sf) if measured_sf else None
    if r.approx:
        tau = TAU_APPROX
    elif exact:
        tau = Fraction(0)
    else:
        tau = TAU_EQUAL
    if exact:
        h_unscaled = Fraction(1, 2) if S.number.digit_count >= 2 else Fraction(0)
    else:
        h_unscaled = S.number.half_width_for(min_sf)
    h_written = h_unscaled * Fraction(10) ** S.scale
    symbols: list[dict] = []
    premises: list[dict] = []
    bands: list[dict] = []
    shown_expr = " = ".join(r.shown_links)
    for k, (label, pct_operands, pct_result, at_scale) in enumerate(readings, start=1):
        tag = "" if k == 1 else str(k)
        enc = _Encoder(tag, pct_operands)
        c, r_name = f"c{tag}", f"r{tag}"
        value, h_read = (S.value, h_written) if at_scale else (S.number.value, h_unscaled)
        stated = value / 100 if (S.percent and pct_result) else value
        h = h_read / 100 if (S.percent and pct_result) else h_read
        symbols += [{"name": c, "sort": "Real", "meaning": f"the computed value of the written expression ({label})"},
                    {"name": r_name, "sort": "Real", "meaning": f"the stated value ({label})"}]
        for j, tree in enumerate(r.links, start=1):
            expr, _closed = enc.enc(tree, r.shown_links[j - 1])
            cj = c if j == 1 else f"{c}_{j}"
            if j > 1:
                symbols.append({"name": cj, "sort": "Real", "meaning": f"the computed value of link {j} of the written arithmetic ({label})"})
            premises.append({"id": f"C_DEF{tag}" + (f"_{j}" if j > 1 else ""), "expr": {"op": "eq", "left": _var(cj), "right": expr},
                             "label": f"{cj} is the value of the written expression '{r.shown_links[j - 1][:200]}' ({label})",
                             "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
        for name, definition, guard, aux_label in enc.aux:
            symbols.append({"name": name, "sort": "Real", "meaning": aux_label[:200]})
            premises.append({"id": f"Q_DEF_{name}", "expr": definition, "label": aux_label[:400],
                             "grounding": {"kind": "arithmetic_fact", "certainty": "established",
                                           "note": "encoding device: defines the auxiliary as the written quotient; not a claim of the report"}})
            premises.append({"id": f"GUARD_{name}", "expr": guard, "label": f"the divisor of {name} is not zero",
                             "grounding": {"kind": "assumption", "certainty": "established", "note": "side condition of the encoding (a divisor is non-zero)"}})
        premises.append({"id": f"R{tag}", "expr": {"op": "eq", "left": _var(r_name), "right": _real(stated)},
                         "label": f"{r_name} is the stated value, {S.text[:80]} ({label})",
                         "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
        link_bands = [band_expr(_var(c if j == 1 else f"{c}_{j}"), _var(r_name), _real(h), tau) for j in range(1, len(r.links) + 1)]
        bands.append(link_bands[0] if len(link_bands) == 1 else {"op": "and", "args": link_bands})
    conclusion = bands[0] if len(bands) == 1 else {"op": "or", "args": bands}
    names = "; ".join(label for label, _a, _b, _s in readings)
    h_shown = _fmt(h_written) if all(at for *_x, at in readings) else f"{_fmt(h_unscaled)} in the result's scale, {_fmt(h_written)} as written"
    mode = ("exact mode: every figure is exact" + (", h = 1/2" if h_written else ", h = 0") if exact else
            f"h = {h_shown}" + (" (≈ or about: τ = 1/20)" if r.approx else ""))
    problem = {
        "ir_version": "1.0", "problem_id": pid[:128], "request_id": request_id[:128], "claim_id": claim_id[:128], "query": "entailment",
        "symbols": symbols, "premises": premises,
        "conclusion": {"id": "STATED", "expr": conclusion,
                       "label": (f"the stated value {S.text[:80]} lies within h + τ·|C| of the value of {shown_expr[:300]} under "
                                 + ("some reading" if len(readings) > 1 else "the reading") + f" ({names}); {mode}, τ = {_fmt(tau)}")[:1000]},
        "notes": f"{WORKED_SCOPE} readings: {names}"[:4000],
    }
    description = (f"the written arithmetic: '{r.phrase[:240]}' (read as {shown_expr[:200]} against the stated {S.text[:80]}; readings: {names}; "
                   f"{mode}, τ = {_fmt(tau)}) [{WORKED_RULE}]")
    return problem, description


def worked_problems(text: str, *, report_id: str, request_id: str, prefix: str, skip: frozenset = frozenset()) -> list[WorkedProblem]:
    """The engine problems of the worked equations of ``text`` this module reads, in order; equations whose phrase is in ``skip``
    (decided by a subject pack's own check: an elasticity, a margin) are left to that check."""
    out: list[WorkedProblem] = []
    n = 0
    for phrase, statement, r, _why in _reads(text):
        if r is None or phrase in skip:
            continue
        n += 1
        problem, description = _problem(r, pid=f"{prefix}-{report_id}-{n}", claim_id=f"{report_id}:{prefix}-{n}", request_id=request_id)
        if _why == _RELATIVE_TAG:
            description = description.replace("the written arithmetic:", "the relative change stated after the difference:", 1)
        out.append(WorkedProblem(phrase, statement, problem, description))
    return out


# ------------------------------------------------------------------ a figure with its parts in brackets ('$11,300 (5,200 + 4,000 + 1,500 + 600)')

#: A stated figure followed by the sum or difference of its parts in brackets: '$11,300 (5,200 + 4,000 + 1,500 + 600)', '$1,237.50 million per
#: year in total ($712.50 + $525)'. Up to six words may stand between the figure and the bracket ('million per year in total'); the bracket
#: holds two to twelve figures joined by '+' or '−' and nothing else. Every run is bounded, so each figure is read once.
_BREAKDOWN_FIG = r"(?:US\$|[$£€¥])?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?!\d)|(?:US\$|[$£€¥])?\d+(?:\.\d+)?(?!\d)"
_BREAKDOWN_RE = re.compile(
    rf"(?<![\d.,])(?P<stated>{_BREAKDOWN_FIG})(?P<words>(?:\s{{1,3}}[A-Za-z]{{1,15}}){{0,6}}?)\s{{0,3}}"
    rf"\((?P<parts>\s{{0,3}}(?:{_BREAKDOWN_FIG})(?:\s{{0,3}}[+−-]\s{{0,3}}(?:{_BREAKDOWN_FIG})){{1,11}}\s{{0,3}})\)")
#: A stated figure followed by the product or quotient of two figures in brackets (attack round 4, ge-t15): '241.0 PJ (0.22 × 1,050)',
#: '311.6 PJ (0.38 × 820 PJ)', '15 km/h (120 ÷ 8)'. A unit of at most four letters may follow each figure; nothing else stands in the
#: bracket (a bracket that also holds '=' is working of its own, read by the worked-line reader).
_PRODUCT_RE = re.compile(
    rf"(?<![\d.,])(?P<stated>{_BREAKDOWN_FIG})(?P<words>(?:\s{{1,3}}[A-Za-z]{{1,15}}){{0,6}}?)\s{{0,3}}"
    rf"\((?P<parts>\s{{0,3}}(?:{_BREAKDOWN_FIG})(?:\s{{1,2}}[A-Za-z]{{1,4}})?\s{{0,3}}[×÷]\s{{0,3}}(?:{_BREAKDOWN_FIG})(?:\s{{1,2}}[A-Za-z]{{1,4}})?\s{{0,3}})\)")
#: A stated figure followed by any arithmetic of figures in brackets (attack round 7): a sum or difference after a unit written with
#: superscripts ('23.6 m³ s⁻¹ (5.4 + 16.2)'), nested brackets ('24 ((24 + 22 + 23) ÷ 3)'), a scale word or a unit after an operand
#: ('34 GJ (820 PJ ÷ 21.4 million people)'), a percentage of a figure ('251 PJ (22% of 1,050 PJ)'), a year between the figure and its
#: bracket ('123 PJ in 2005 (0.15 × 820)'). The bracket holds figures, operators, brackets, "of" after a percentage and unit or scale
#: words of at most ten letters; at most 120 characters. Each run is bounded.
#: A label noun before a small figure ("Storm 1", "Site 4", "Sites 1 and 2", "Question 3"): the figure names something, it states no
#: amount (attack round 8: '7.5 hours sooner ... than Storm 1 did (12 − 4.5)' was read against 1).
_LABEL_NOUN = (r"(?i:storms?|sites?|stations?|zones?|areas?|figures?|fig\.|tables?|years?|weeks?|days?|papers?|questions?|parts?|sections?|levels?|"
               r"grades?|groups?|samples?|quadrats?|transects?|points?|plots?|phases?|stages?|rounds?|trials?|cases?|options?|units?|chapters?|"
               r"lines?|steps?|criteri(?:on|a)|regions?|districts?|routes?|wards?|blocks?|rooms?|events?|wells?|boreholes?|"
               r"tormentas?|sitios?|zonas?|preguntas?|partes?|ejercicios?|criterios?|pasos?|l[ií]neas?|p[aá]rrafos?)")
# (a possessive after the label is the label all the same: "higher than Storm 1's (16.2 − 5.4)"; check round 10 of c3d)
_LABEL_FIG = rf"{_LABEL_NOUN}[ \t]{{1,3}}\d{{1,3}}(?![\d,.]\d)(?:[ \t]{{1,3}}(?:and|&|to|or|y|a)[ \t]{{1,3}}\d{{1,3}}(?![\d,.]\d))?(?:['’]s)?"
#: A figure that is the denominator of a rate or the maximum of a score ("per 10 minutes", "every 100 m", "out of 30", "/30"): it states no
#: result of the bracket after it (attack round 8).
_DENOMINATOR_FIG = r"(?:per|every|out[ \t]of|de[ \t]un[ \t]total[ \t]de|sobre)[ \t]{1,3}\d[\d,]{0,8}"
#: Text right before a stated figure that makes it a label or a denominator, never the bracket's result.
_NOT_A_RESULT_BEFORE_RE = re.compile(rf"(?:\b{_LABEL_NOUN}[ \t]{{1,3}}(?:\d{{1,3}}[ \t]{{1,3}}(?:and|&|to|or|y|a)[ \t]{{1,3}})?|"
                                     r"\b(?:per|every|out[ \t]of|de[ \t]un[ \t]total[ \t]de|sobre)[ \t]{1,3}|/[ \t]?)$", re.IGNORECASE)
_EXPR_WORD = (r"(?:[ \t]{1,3}(?:" + _LABEL_FIG + "|" + _DENOMINATOR_FIG + r"|[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ²³⁻¹/·]{0,14}|(?:1[89]\d{2}|20\d{2})(?![\d,.])))")
_EXPR_RE = re.compile(
    rf"(?<![\d.,])(?P<stated>{_BREAKDOWN_FIG})(?P<words>{_EXPR_WORD}{{0,10}}?)[ \t]{{1,3}}"
    r"\((?P<parts>\s{0,3}\(?\s{0,3}(?:US\$|[$£€¥])?\d[^\n]{1,118}?)\)(?=[\s.,;:!?]|$)")
_EXPR_PARTS_OK = re.compile(r"[\d\s.,+−\-×÷*/()%$£€¥A-Za-z²³⁻¹·]+")
_EXPR_PART_WORD = re.compile(r"[A-Za-z][A-Za-z²³⁻¹/·]*")
_YEAR_ONLY_RE = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
#: The longest text the breakdown reader reads.
_BREAKDOWN_MAX_CHARS = 200_000


class _BalancedMatch:
    """A match of :data:`_EXPR_RE` whose bracket is extended to its balanced close ("24 ((24 + 22 + 23) ÷ 3)")."""

    re = _EXPR_RE

    def __init__(self, m: "re.Match", parts_end: int, text: str):
        self._m, self._text, self._parts_end = m, text, parts_end

    def group(self, name=0):
        if name == "parts":
            return self._text[self._m.start("parts"):self._parts_end]
        if name == 0:
            return self._text[self._m.start():self._parts_end + 1]
        return self._m.group(name)

    def start(self, name=0):
        return self._m.start(name) if name else self._m.start()

    def end(self) -> int:
        return self._parts_end + 1


def _balanced(m: "re.Match", text: str):
    """``m`` with its bracket closed where its depth returns to zero (at most 120 characters), or None."""
    open_at = m.start("parts") - 1
    depth = 0
    for k in range(open_at, min(len(text), open_at + 122)):
        c = text[k]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                j = k + 1
                while j < len(text) and j - k < 4 and text[j] in " \t":
                    j += 1
                if j < len(text) and text[j] in "+−-×÷*/=^·":
                    return None  # "(51.2 − 7.0) ÷ 7.0 × 100": the bracket is an operand of more working, no stated result's parts
                return _BalancedMatch(m, k, text)
        elif c == "\n":
            return None
    return None


def _breakdown_reads(text: str) -> list[tuple[str, str, _Read]]:
    """``(phrase, statement, read)`` for every figure of ``text`` stated with the sum of its parts in brackets: the parts are read as the
    written expression and the figure before the bracket (with its scale word) as its stated result, so the engine decides it as any worked
    line (the scale rule included: '$1,237.50 million ... ($712.50 + $525)' is read in millions). Years in brackets ('(2019 + 2020)') are
    no parts."""
    out: list[tuple[str, str, _Read]] = []

    def labelled(m) -> bool:
        # a figure that names something or is a denominator ("than Storm 1 did (12 − 4.5)", "per 10 minutes (214 + 186)", "out of 30
        # (7 + 9 + 5)") states no result of the bracket: the stated figure is the one before it, read with it as words (attack round 8)
        return _NOT_A_RESULT_BEFORE_RE.search(text, max(0, m.start("stated") - 48), m.start("stated")) is not None
    found = sorted([m for m in list(_BREAKDOWN_RE.finditer(text[:_BREAKDOWN_MAX_CHARS])) + list(_PRODUCT_RE.finditer(text[:_BREAKDOWN_MAX_CHARS]))
                    if not labelled(m)], key=lambda x: x.start())
    # (a year read as the stated figure, "123 PJ in 2005 (0.15 × 820)", is no reading of the bracket: the general reader tries it)
    seen_brackets = {m.end() for m in found if not (_YEAR_ONLY_RE.match(m.group("stated")) and not m.group("words").strip())}
    for m0 in _EXPR_RE.finditer(text[:_BREAKDOWN_MAX_CHARS]):
        m = _balanced(m0, text)
        if m is None or m.end() in seen_brackets or _YEAR_ONLY_RE.match(m.group("stated")) or labelled(m0):
            continue  # (an unbalanced bracket; read by the sum or the product reader already; a year is a date, never a result:
            # "2025 profit before interest and tax ($380,000 ÷ $336,000 × 100)")
        parts = m.group("parts")
        if not _EXPR_PARTS_OK.fullmatch(parts) or not re.search(r"[+−×÷*/]|\s-\s|%\s{1,3}of\b", parts) or \
                len(re.findall(r"\d[\d,.]*", parts)) < 2 or "=" in parts:
            continue
        words = [w for w in _EXPR_PART_WORD.findall(parts) if w != "of"]
        if any(len(w) > 10 for w in words) or len(words) > 4:
            continue  # (words in the bracket are units or scale words, never a sentence)
        found.append(m)
        seen_brackets.add(m.end())
    found.sort(key=lambda x: x.start())
    for m in found:
        gap = text[m.start("parts") - 4:m.start("parts")]
        after = text[m.end():m.end() + 4].lstrip(" \t")
        if "\n" in gap or (after[:1] and after[:1] in "+−-×÷*/=^·"):
            continue  # "× 100\n(51.2 − 7.0) ÷ 7.0": a bracket on the next line, or one that more working operates on, holds no
            # stated figure's parts (attack round 7)
        parts = m.group("parts")
        if m.re is _EXPR_RE:
            parts = re.sub(r"%\s{1,3}of\b", "% ×", parts)  # "22% of 1,050 PJ": a percentage of a figure, a product
        figures = re.findall(r"\d[\d,.]*", parts)
        if all(_YEAR_ONLY_RE.match(f) for f in figures):
            continue
        if _YEAR_ONLY_RE.match(m.group("stated")) and not m.group("words").strip():
            continue  # "62% of primary energy in 2005 (100 − 38)": the year is a date, never the bracket's result (attack round 4)
        top = re.findall(r"\d[\d,.]*", re.sub(r"\([^()]*\)", " ", parts)) if m.re is _EXPR_RE else figures
        if m.re in (_PRODUCT_RE, _EXPR_RE) and re.sub(r"[^\d.]", "", m.group("stated")) in {re.sub(r"[^\d.]", "", f) for f in top}:
            continue  # "Christchurch's 185 deaths (300,000 ÷ 185)": the figure is an operand cited, the bracket works out another one
        stated_text = m.group("stated") + (re.sub(r"\s(?:1[89]\d{2}|20\d{2})\b.*$", "", m.group("words")) if m.re is _EXPR_RE else m.group("words"))
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        statement = text[line_start: line_end if line_end >= 0 else len(text)].strip()
        # in a Spanish statement a point separates thousands, in the bracket as in the stated figure ("perdió 1.038 habitantes entre
        # 1960 y 2015 (1.250 − 212)": 1250 − 212 = 1038; attack round 8), as the worked-line reader reads it
        from ..stem.lexer import _spanish_text
        token = _POINT_GROUPS.set(_spanish_text(statement, 0, len(statement)))
        try:
            toks = _tokens(parts)
            tree = _Parser(toks).parse()
            result, _end = _read_figure(stated_text.strip(), 0)
        except _Refuse:
            continue
        except Exception:  # noqa: BLE001 - never an exception on agent text: the figure is not read
            continue
        finally:
            _POINT_GROUPS.reset(token)
        figs = _figures(tree) + [result]
        if len({f.cur for f in figs if f.cur}) > 1 or (len({k for f in figs for w in f.units for k in [_unit_key(w)] if k}) > 1 and
                                                       len({_compound_key(f) for f in figs if _compound_key(f)}) != 1):
            continue
        phrase = " ".join(m.group(0).split())
        shown = " ".join(parts.split())
        out.append((phrase, statement, _Read(phrase, statement, (tree,), (shown,), result, approx_word_in(m.group("words")))))
        if len(out) >= MAX_WORKED_CHECKS:
            break
    return out


def breakdown_problems(text: str, *, report_id: str, request_id: str, prefix: str) -> list[WorkedProblem]:
    """The engine problems of the figures ``text`` states with the sum of their parts in brackets (:func:`_breakdown_reads`), numbered
    after the worked equations of the same prefix ('-b1', '-b2'): '$11,400 (5,200 + 4,000 + 1,500 + 600)' is a COUNTEREXAMPLE, '$11,300
    (...)' ENTAILED (c1 adversarial: parenthetical sums crossed silently)."""
    out: list[WorkedProblem] = []
    for n, (phrase, statement, r) in enumerate(_breakdown_reads(text), start=1):
        problem, description = _problem(r, pid=f"{prefix}-{report_id}-b{n}", claim_id=f"{report_id}:{prefix}-b{n}", request_id=request_id)
        try:
            Problem.model_validate(problem)
        except Exception:  # noqa: BLE001 - a problem the IR schema refuses is not built
            continue
        out.append(WorkedProblem(phrase, statement, problem, description.replace("the written arithmetic:", "the parts in brackets:", 1)))
    return out


def decided_worked_chains(text: str) -> set[str]:
    """The phrases of the worked equations of ``text`` that :func:`worked_problems` or :func:`clock_problems` builds a problem for."""
    return ({phrase for phrase, _s, r, _w in _reads(text) if r is not None} | {phrase for phrase, _s, _c in _clock_reads(text)}
            | {phrase for phrase, _s, _p in _payback_reads(text)})


# ------------------------------------------------------------------ a payback period in years and months ('3 years + ($55,000 ÷ $75,000) × 12 months = 3 years 8.8 months')

_PB_FIG = r"(?:US\$|[$£€¥])?\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?|(?:US\$|[$£€¥])?\s?\d+(?:\.\d+)?"
#: The working of a payback period: whole years plus the fraction of the next year's net cash flow, in months.
_PAYBACK_RE = re.compile(rf"^(?P<y>\d{{1,2}})\s*+years?\s*+\+\s*+\(\s*+(?P<a>{_PB_FIG})\s*+[÷/]\s*+(?P<b>{_PB_FIG})\s*+\)\s*+[×x*]\s*+12\s*+months?\s*+$",
                         re.IGNORECASE)
#: A stated payback period: '3 years + 8.8 months', '3 years 8.8 months', '4 years and 10.9 months'.
_PAYBACK_STATED_RE = re.compile(r"^\s*+(?P<y>\d{1,2})\s*+years?\s*+(?:\+|and|,)?\s*+(?P<m>\d{1,2}(?:\.\d{1,4})?)\s*+months?\s*+[.,;]?\s*+$", re.IGNORECASE)


@lru_cache(maxsize=32)
def _payback_reads(text: str) -> tuple[tuple[str, str, tuple], ...]:
    """``(phrase, statement, (years, a, b, stated))`` for every worked payback period of ``text`` (:data:`_PAYBACK_RE`), ``stated`` the
    chain's stated periods as ``(years, months, written months)``."""
    out: list[tuple[str, str, tuple]] = []
    if "month" not in text:
        return ()
    for eq in worked_equations(text):
        if len(out) >= MAX_WORKED_CHECKS:
            break
        head = eq.phrase.split("=", 1)[0]
        m = _PAYBACK_RE.match(head.strip())
        if m is None:
            continue
        try:
            a, _e1 = _read_figure(m.group("a").strip(), 0)
            b, _e2 = _read_figure(m.group("b").strip(), 0)
        except _Refuse:
            continue
        if b.value == 0 or (a.cur and b.cur and a.cur != b.cur):
            continue
        at = eq.statement.find(head.strip())
        chain = eq.statement[at + len(head.strip()):] if at >= 0 else eq.phrase[len(head):]
        stated = []
        for link in chain.split("=")[1:5]:
            sm = _PAYBACK_STATED_RE.match(link)
            if sm is None:
                break
            stated.append((int(sm.group("y")), Fraction(sm.group("m")), sm.group("m")))
        if stated:
            out.append((eq.phrase, eq.statement, (int(m.group("y")), a, b, tuple(stated))))
    return tuple(out)


def payback_problems(text: str, *, report_id: str, request_id: str, prefix: str) -> list[WorkedProblem]:
    """The engine problems of the payback periods of ``text`` (:func:`_payback_reads`; round 9, c1 adversarial 14: '= 3 years + 9.8 months'
    crossed as 'not checked'), numbered '-p1', '-p2': each stated period's years equal the written whole years and its months lie within
    half a unit in their last written digit plus 1/100 of the computed months (12 × a ÷ b)."""
    out: list[WorkedProblem] = []
    for n, (phrase, statement, (years, a, b, stated)) in enumerate(_payback_reads(text), start=1):
        months = Fraction(12) * a.value / b.value
        symbols = [{"name": "c", "sort": "Real", "meaning": "the months computed from the written fraction of the next year (12 × a ÷ b)"}]
        premises = [{"id": "C_DEF", "expr": {"op": "eq", "left": _var("c"), "right": {"op": "mul", "args": [_real(Fraction(12)), {"op": "div", "left": _real(a.value), "right": _real(b.value)}]}},
                     "label": f"c = 12 × {a.text} ÷ {b.text}", "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}}]
        bands = []
        for k, (y, m_value, m_text) in enumerate(stated, start=1):
            places = len(m_text.split(".")[1]) if "." in m_text else 0
            half = Fraction(1, 2) / Fraction(10) ** places
            symbols.append({"name": f"r{k}", "sort": "Real", "meaning": f"the stated months of '{y} years {m_text} months'"})
            premises.append({"id": f"R{k}", "expr": {"op": "eq", "left": _var(f"r{k}"), "right": _real(m_value)}, "label": f"r{k} = {m_text} months",
                             "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
            bands.append(band_expr(_var("c"), _var(f"r{k}"), _real(half), TAU_EQUAL))
            bands.append({"op": "eq", "left": _real(Fraction(y)), "right": _real(Fraction(years))})
        problem = {
            "ir_version": "1.0", "problem_id": f"{prefix}-{report_id}-p{n}"[:128], "request_id": request_id[:128], "claim_id": f"{report_id}:{prefix}-p{n}"[:128],
            "query": "entailment", "symbols": symbols, "premises": premises,
            "conclusion": {"id": "STATED", "expr": {"op": "and", "args": bands},
                           "label": f"every stated period has the written {years} whole years and months within h + τ·|C| of 12 × {a.text} ÷ {b.text} (τ = 1/100)"[:1000]},
            "notes": f"{WORKED_SCOPE} readings: a payback period in whole years and months"[:4000],
        }
        try:
            Problem.model_validate(problem)
        except Exception:  # noqa: BLE001 - a problem the IR schema refuses is not built
            continue
        shown = " = ".join(f"{y} years {t} months" for y, _v, t in stated)
        description = (f"the written arithmetic: '{phrase[:240]}' (read as {years} years + 12 × {a.text} ÷ {b.text} months = {_fmt(months)} months against the "
                       f"stated {shown[:120]}) [{WORKED_RULE}]")
        out.append(WorkedProblem(phrase, statement, problem, description))
    return out


# ------------------------------------------------------------------ clock times ('Storm 2: 14:00 − 09:30 = 4 hours 30 minutes = 4.5 hours')

#: A time of day on the 24-hour clock ('09:30', '14:00', '21:30'): hours 0 to 23, minutes 00 to 59, no digit or colon glued to it.
_CLOCK = r"(?<![\d:.])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])"
#: The difference of two times of day opening a worked equation: '14:00 − 09:30 = ...'.
_CLOCK_DIFF_RE = re.compile(rf"^{_CLOCK}\s*+[−–-]\s*+{_CLOCK}\s*+$")
#: A stated duration: '4 hours 30 minutes', '4 h 30 min', '4.5 hours', '12 hours', '270 minutes'. Anchored at both ends of one link.
_DURATION_RE = re.compile(
    r"^\s*+(?:(?:about|approximately|roughly|around)\s++)?(?:(?P<h>\d{1,3}(?:\.\d{1,4})?)\s*+(?:hours?|hrs?|h)\b(?:\s*+(?:and\s++)?(?P<m>\d{1,2})\s*+(?:minutes?|mins?|min)\b)?"
    r"|(?P<mm>\d{1,5}(?:\.\d{1,4})?)\s*+(?:minutes?|mins?|min)\b)\s*+[.,;]?\s*+$", re.IGNORECASE)


def _duration(link: str) -> Optional[tuple[Fraction, Fraction, str]]:
    """``(minutes, half-width in minutes, as written)`` of a stated duration link, or None: half a unit in the last written digit of its
    last part ('4 hours 30 minutes': half a minute; '4.5 hours': 0.05 hour; '12 hours': half an hour)."""
    m = _DURATION_RE.match(link)
    if m is None:
        return None
    shown = " ".join(link.split()).rstrip(".,;")
    if m.group("mm") is not None:
        v = Fraction(m.group("mm"))
        places = len(m.group("mm").split(".")[1]) if "." in m.group("mm") else 0
        return v, Fraction(1, 2) / Fraction(10) ** places, shown
    hours = Fraction(m.group("h"))
    if m.group("m") is not None:
        return hours * 60 + int(m.group("m")), Fraction(1, 2), shown
    places = len(m.group("h").split(".")[1]) if "." in m.group("h") else 0
    return hours * 60, Fraction(60, 2) / Fraction(10) ** places, shown


@lru_cache(maxsize=32)
def _clock_reads(text: str) -> tuple[tuple[str, str, tuple], ...]:
    """``(phrase, statement, (t1, t2, durations))`` for every worked equation of ``text`` that subtracts two times of day and states the
    elapsed time ('Storm 2: 14:00 − 09:30 = 4 hours 30 minutes = 4.5 hours'), in minutes; every stated duration of the chain is read. A
    later time before an earlier one (a span across midnight the line does not state) is not read."""
    out: list[tuple[str, str, tuple]] = []
    if ":" not in text:
        return ()
    for eq in worked_equations(text):
        if len(out) >= MAX_WORKED_CHECKS:
            break
        head, _sep, _rest = eq.phrase.partition("=")
        m = _CLOCK_DIFF_RE.match(head)
        if m is None:
            continue
        t1 = int(m.group(1)) * 60 + int(m.group(2))
        t2 = int(m.group(3)) * 60 + int(m.group(4))
        if t1 < t2:
            continue
        at = eq.statement.find(head.strip())
        chain = eq.statement[at + len(head.strip()):] if at >= 0 else eq.phrase[len(head):]
        durations = []
        for link in chain.split("=")[1:5]:
            d = _duration(link)
            if d is None:
                break
            durations.append(d)
        if durations:
            out.append((eq.phrase, eq.statement, (t1, t2, tuple(durations))))
    return tuple(out)


def clock_problems(text: str, *, report_id: str, request_id: str, prefix: str) -> list[WorkedProblem]:
    """The engine problems of the clock-time worked equations of ``text`` (:func:`_clock_reads`, round 9, c2 ge-p9c: '14:00 − 09:30 = 5
    hours 30 minutes' crossed as 'not checked'), numbered '-t1', '-t2': the difference of the two times, in minutes, against every stated
    duration of the chain within half a unit in its last written digit (exact times: no relative slack)."""
    from ..stem.tolerance import abs_expr
    out: list[WorkedProblem] = []
    for n, (phrase, statement, (t1, t2, durations)) in enumerate(_clock_reads(text), start=1):
        symbols = [{"name": "c", "sort": "Real", "meaning": "the elapsed time computed from the two times of day, in minutes"}]
        premises = [{"id": "C_DEF", "expr": {"op": "eq", "left": _var("c"), "right": {"op": "sub", "left": _real(Fraction(t1)), "right": _real(Fraction(t2))}},
                     "label": f"c is the later time minus the earlier, in minutes ({t1} − {t2})",
                     "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}}]
        bands = []
        for k, (value, half, shown) in enumerate(durations, start=1):
            symbols.append({"name": f"r{k}", "sort": "Real", "meaning": f"the stated elapsed time '{shown[:60]}', in minutes"})
            premises.append({"id": f"R{k}", "expr": {"op": "eq", "left": _var(f"r{k}"), "right": _real(value)}, "label": f"r{k} = {shown[:80]} = {_fmt(value)} minutes",
                             "grounding": {"kind": "supplied_text", "verified": True, "note": "figure stated in the report itself"}})
            bands.append({"op": "le", "left": abs_expr({"op": "sub", "left": _var("c"), "right": _var(f"r{k}")}), "right": _real(half)})
        shown_all = " = ".join(s for _v, _h, s in durations)
        problem = {
            "ir_version": "1.0", "problem_id": f"{prefix}-{report_id}-t{n}"[:128], "request_id": request_id[:128], "claim_id": f"{report_id}:{prefix}-t{n}"[:128],
            "query": "entailment", "symbols": symbols, "premises": premises,
            "conclusion": {"id": "STATED", "expr": bands[0] if len(bands) == 1 else {"op": "and", "args": bands},
                           "label": f"every stated elapsed time ({shown_all[:200]}) lies within half a unit in its last written digit of the difference of the two times"[:1000]},
            "notes": f"{WORKED_SCOPE} readings: times of day on the 24-hour clock read in minutes"[:4000],
        }
        try:
            Problem.model_validate(problem)
        except Exception:  # noqa: BLE001 - a problem the IR schema refuses is not built
            continue
        description = (f"the written arithmetic: '{phrase[:240]}' (read as {t1} − {t2} minutes against the stated {shown_all[:120]}; exact times, each stated "
                       f"time within half a unit in its last written digit) [{WORKED_RULE}]")
        out.append(WorkedProblem(phrase, statement, problem, description))
    return out


# ============================================================================================ prose arithmetic (clearance c3)
# Round 10's adversarial lens found arithmetic stated in prose that crossed every prose branch with no finding: a share with its per cent
# in brackets ('Eleven of the 46 students allocated to the app (32.9%)', 'It killed 185 people, more than 130 of them (about 85%)'), a
# change with its per cent in brackets ('the fleet fell from 412 to 236 boats (−57.28%)', 'the price rose 33.95% in nominal terms
# (P$2,150 to P$2,880)'), a per cent with its working in brackets and no '=' ('131.1% of the 2025 profit ... ($380,000 ÷ $336,000 × 100)'),
# a difference ("Haiti's 7.0 and Darfield's 7.1 differ by 0.3") and a distance from a bound ('about 900 words would fall 400 words below the
# 1,200-word minimum'). Each is read here as written arithmetic: the expression the sentence states is built from its own figures with a
# closed grammar and set against the figure it states, and the engine decides it under the worked tolerance rule (an approximation word
# or '≈' gives τ = 1/20). Nothing is evaluated: the expression is read by :func:`_tokens` and :class:`_Parser` as any worked line.

_P_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_P_CUR = r"(?:[A-Z]{1,3}\$|US\$|\$|£|€|¥)"
_P_WORD_NUM = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
               r"|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?")
_P_WORD_VALUES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                  "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
                  "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_P_APPROX = r"(?:about|around|roughly|approximately|approx\.?|nearly|almost|some|c\.|≈|~)"
#: A share: "a of (the) b <words> (p%)" or "a of them (p%)" with the total stated before it in the sentence.
_P_SHARE_RE = re.compile(rf"(?<![\w.,])(?:(?:more|fewer|less)\s+than\s+|over\s+|under\s+|only\s+|just\s+)?(?P<a>{_P_NUM}|{_P_WORD_NUM})\s+(?:out\s+)?of\s+"
                         rf"(?:(?:the|these|those|all)\s+)?(?:(?P<b>{_P_NUM})\b|(?P<them>them|these|those)\b)(?P<words>[^().;:%]{{0,80}}?)\s*\(\s*(?P<ap>{_P_APPROX}\s+)?"
                         rf"(?P<p>[-−]?\d{{1,3}}(?:\.\d+)?)\s*(?:%|per\s*cent)\s*\)", re.IGNORECASE)
#: A change from one figure to another with its per cent in brackets right after: "from 412 to 236 boats (−57.28%)".
_P_PAIR_PCT_RE = re.compile(rf"\bfrom\s+(?:{_P_APPROX}\s+)?(?P<x>{_P_CUR}?(?:{_P_NUM}))(?P<xs>\s*(?:thousand|million|billion))?\s+(?:[a-z][\w-]*\s+){{0,3}}?to\s+(?:{_P_APPROX}\s+)?"
                            rf"(?P<y>{_P_CUR}?(?:{_P_NUM}))(?P<ys>\s*(?:thousand|million|billion))?(?P<words>[^().;:%\d]{{0,40}}?)\s*\(\s*(?P<ap>{_P_APPROX}\s+)?(?P<sign>[-−+])?\s*"
                            rf"(?P<p>\d{{1,4}}(?:\.\d+)?)\s*(?:%|per\s*cent)\s*\)", re.IGNORECASE)
#: A per cent stated before its pair in brackets: "rose 33.95% in nominal terms (P$2,150 to P$2,880)".
_P_PCT_PAIR_RE = re.compile(rf"\b(?P<dir>rose|risen|rises|increased|increases|grew|grown|fell|fallen|falls|dropped|decreased|decreases|declined|climbed|jumped|"
                            rf"went\s+up|went\s+down)\s+(?:by\s+)?(?:(?P<ap>{_P_APPROX})\s+)?(?P<p>\d{{1,4}}(?:\.\d+)?)\s*(?:%|per\s*cent)(?P<gap>[^().;:]{{0,60}}?)"
                            rf"\(\s*(?:from\s+)?(?P<x>{_P_CUR}?(?:{_P_NUM}))\s+(?:to|→|->)\s+(?P<y>{_P_CUR}?(?:{_P_NUM}))\s*\)", re.IGNORECASE)
#: A per cent with its working in brackets and no '=': "131.1% of the 2025 profit before interest and tax ($380,000 ÷ $336,000 × 100)".
_P_PCT_WORK_RE = re.compile(rf"(?P<p>\d{{1,4}}(?:\.\d+)?)\s*(?:%|per\s*cent)(?P<gap>[^().;:%=≈]{{0,90}}?)\(\s*(?P<expr>[^()=≈;]{{3,120}}?[×÷*/][^()=≈;]{{1,120}}?)\s*\)",
                            re.IGNORECASE)
#: A per cent and its additive parts in brackets after it (a year or a few words between): "56% in 2025 (100 − 54)".
_P_PCT_PARTS_RE = re.compile(r"(?<![\d.,])(?P<p>\d{1,4}(?:\.\d+)?)\s*(?:%|per\s*cent)(?P<gap>[^().;:%=≈\d]{0,40}?(?:\b(?:1[89]\d{2}|20\d{2})\b)?"
                             r"[^().;:%=≈\d]{0,10}?)\(\s*(?P<expr>\d[\d.,]{0,10}(?:\s*[+−–-]\s*\d[\d.,]{0,10}){1,11})\s*\)", re.IGNORECASE)
#: A difference: "Haiti's 7.0 and Darfield's 7.1 differ by 0.3".
#: (Possessive runs: a unit read as blanks and letters, and the blanks before 'and' and 'differ', never given back one by one; the class
#: sweep of this stage measured 1.4 s for a figure followed by 20,000 blanks with the earlier '\\s*[%a-z]{0,8}\\s+and'.)
_P_DIFFER_RE = re.compile(rf"(?<![\w.,])(?P<a>{_P_NUM})(?P<au>(?:\s*+[%a-z]{{1,8}}+)?)\s++and\s++(?:[\w'’-]++\s++){{0,3}}?(?P<b>{_P_NUM})(?P<bu>(?:\s*+[%a-z]{{1,8}}+)?)"
                          rf"\s++differ\s++by\s++(?:(?P<ap>{_P_APPROX})\s++)?(?P<d>{_P_NUM})", re.IGNORECASE)
#: A distance from a bound: "about 900 words would fall 400 words below the 1,200-word minimum".
_P_BOUND_RE = re.compile(rf"(?<![\w.,])(?:(?P<ap>{_P_APPROX})\s+)?(?P<x>{_P_NUM})\s+(?P<u>[a-z]+)\b[^.;:]{{0,40}}?\b(?:would\s+|will\s+|could\s+|might\s+)?(?:fall|falls|fell|be|is|are|was"
                         rf"|were|lie|lies|sit|sits|come|comes|end|ends|land|lands)\s+(?:(?P<ap2>{_P_APPROX})\s+)?(?P<d>{_P_NUM})\s+(?P<du>[a-z]+)\s+(?P<dir>below|under|short\s+of"
                         rf"|above|over|beyond)\s+the\s+(?P<y>{_P_NUM})[-\s](?P<yu>[a-z]+)[-\s](?:minimum|maximum|limit|target|threshold|requirement|cap|ceiling|floor)", re.IGNORECASE)
_P_MAX_CHARS = 200_000
#: A party of a cost comparison: a labelled option ('Option 2', 'Plan B', 'Site A') or a capitalised name of up to three words.
_P_PARTY = (r"(?:(?:the\s+)?(?:Option|Plan|Proposal|Project|Site|Choice|Scheme|Strategy|Alternative|Supplier|Location|Route|Model)\s+(?:\d{1,2}|[A-Z])\b"
            r"|[A-Z][a-z][\w'’-]{1,30}(?:\s+[A-Z][\w'’-]{1,30}){0,2})")
#: A party's cost: "Option 1 costs $380,000", "Plan B would cost £2.4 million".
_P_COST_RE = re.compile(rf"(?P<party>{_P_PARTY})(?:['’]s\s+(?:outlay|cost|price))?\s+(?:costs?|would\s+cost|will\s+cost|is\s+priced\s+at|has\s+a\s+cost\s+of)\s+"
                        rf"(?:(?:about|around|roughly|approximately)\s+)?(?P<v>{_P_CUR}(?:{_P_NUM}))(?P<vs>\s*(?:thousand|million|billion))?\b")
#: A difference of two costs: "Option 2 is $110,000 cheaper", "Option 1 is $90,000 more expensive than Option 2", "Plan B costs £50,000 less
#: than Plan A".
_P_CHEAPER_RE = re.compile(rf"(?P<a>{_P_PARTY})\s+(?:is|was|would\s+be|will\s+be)\s+(?:(?P<ap>{_P_APPROX})\s+)?(?P<d>{_P_CUR}(?:{_P_NUM}))(?P<ds>\s*(?:thousand|million|billion))?"
                           rf"\s+(?P<cmp>cheaper|less\s+expensive|more\s+expensive|dearer|costlier)(?:\s+than\s+(?P<b>{_P_PARTY}))?"
                           rf"|(?P<a2>{_P_PARTY})\s+(?:costs?|would\s+cost|will\s+cost)\s+(?:(?P<ap2>{_P_APPROX})\s+)?(?P<d2>{_P_CUR}(?:{_P_NUM}))(?P<ds2>\s*(?:thousand|million|billion))?"
                           rf"\s+(?P<cmp2>more|less)\s+than\s+(?P<b2>{_P_PARTY})")


def _p_party(name: str) -> str:
    return " ".join(re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE).split()).lower()


def _p_cost_differences(text: str) -> list[tuple[str, str, _Read]]:
    """Clearance c3 (bm-cheaper: 'Option 2 is $110,000 cheaper' after 'Option 1 costs $380,000' and 'Option 2 costs $290,000', 90,000 apart,
    crossed with no finding): a stated difference of two parties' costs, read against the costs the paragraph states for them. The other
    party is the one named after 'than', or else the one other party the paragraph states a cost for; a paragraph that states two costs for
    one party, or costs for several other parties, states no one difference (not read)."""
    out: list[tuple[str, str, _Read]] = []
    for para in re.split(r"\n\s*\n", text):
        if not re.search(r"cheaper|expensive|dearer|costlier|\b(?:more|less)\s+than\b", para, re.IGNORECASE):
            continue
        costs: dict[str, set[str]] = {}
        for m in _P_COST_RE.finditer(para):
            if re.match(r"\s+(?:more|less)\s+than\b", para[m.end():m.end() + 24], re.IGNORECASE):
                continue  # 'Option 1 costs $90,000 more than Option 2': a difference, not Option 1's cost
            costs.setdefault(_p_party(m.group("party")), set()).add(_p_bare(m.group("v")) + (m.group("vs") or ""))
        if len(costs) < 2:
            continue
        for m in _P_CHEAPER_RE.finditer(para):
            a = _p_party(m.group("a") or m.group("a2"))
            b_raw = m.group("b") or m.group("b2")
            d = _p_bare(m.group("d") or m.group("d2")) + (m.group("ds") or m.group("ds2") or "")
            cmp = (m.group("cmp") or m.group("cmp2")).lower()
            if a not in costs or len(costs[a]) != 1:
                continue
            others = [_p_party(b_raw)] if b_raw else [k for k in costs if k != a]
            if len(others) != 1 or others[0] not in costs or others[0] == a or len(costs[others[0]]) != 1:
                continue
            cost_a, cost_b = next(iter(costs[a])), next(iter(costs[others[0]]))
            cheaper = cmp in ("cheaper", "less expensive", "less")
            expr = f"{cost_b} − {cost_a}" if cheaper else f"{cost_a} − {cost_b}"
            r = _p_read(" ".join(m.group(0).split()), _p_sentence(para, m.start(), m.end()), expr, d, bool(m.group("ap") or m.group("ap2")))
            if r is not None:
                out.append((r.phrase, r.statement, r))
    return out




def _p_value(token: str) -> str:
    """A figure of a prose relation written in digits for the worked grammar (a number word in its digits)."""
    t = token.strip()
    low = t.lower().replace("-", " ")
    if low in _P_WORD_VALUES:
        return str(_P_WORD_VALUES[low])
    if " " in low and all(w in _P_WORD_VALUES for w in low.split()):
        return str(sum(_P_WORD_VALUES[w] for w in low.split()))
    return t


def _p_read(phrase: str, statement: str, expr: str, stated: str, approx: bool) -> Optional[_Read]:
    try:
        tree = _Parser(_tokens(expr)).parse()
        result, _end = _read_figure(stated, 0)
    except _Refuse:
        return None
    except Exception:  # noqa: BLE001 - never an exception on agent text: the relation is not read
        return None
    figs = _figures(tree) + [result]
    if len({f.cur for f in figs if f.cur}) > 1:
        return None
    return _Read(phrase, statement, (tree,), (expr,), result, approx)


def _p_sentence(text: str, a: int, b: int) -> str:
    start = max(text.rfind(". ", 0, a) + 1, text.rfind("\n", 0, a) + 1, 0)
    ends = [k for k in (text.find(". ", b), text.find("\n", b)) if k >= 0]
    return " ".join(text[start:(min(ends) + 1 if ends else len(text))].split())


def _p_bare(fig: str) -> str:
    """A figure of a pair with its currency sign: one currency for every figure of the expression."""
    return fig.replace("−", "-")


def _prose_reads(text: str) -> list[tuple[str, str, _Read]]:
    """``(phrase, statement, read)`` of every prose relation of ``text`` this section reads (section comment)."""
    text = text[:_P_MAX_CHARS]
    out: list[tuple[str, str, _Read]] = []
    for m in _P_SHARE_RE.finditer(text):
        a = _p_value(m.group("a"))
        if m.group("b"):
            b = m.group("b")
        else:
            before = text[max(0, text.rfind(".", 0, m.start()) + 1, m.start() - 160):m.start()]
            totals = re.findall(rf"(?<![\w.,])({_P_NUM})\s+(?!per\b)[a-z]", before)
            if not totals:
                continue
            b = totals[-1]
        if _YEAR_ONLY_RE.match(b.replace(",", "")) or _YEAR_ONLY_RE.match(a.replace(",", "")):
            continue
        p = m.group("p").replace("−", "-")
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), f"{a} ÷ {b} × 100", f"{p}%", bool(m.group("ap")))
        if r is not None:
            out.append((r.phrase, r.statement, r))
    for m in _P_PAIR_PCT_RE.finditer(text):
        x, y = _p_bare(m.group("x")), _p_bare(m.group("y"))
        if m.group("xs") or m.group("ys"):
            x, y = x + (m.group("xs") or ""), y + (m.group("ys") or "")
        if _YEAR_ONLY_RE.match(x.replace(",", "")) and _YEAR_ONLY_RE.match(y.replace(",", "")):
            continue
        fall = bool(m.group("sign")) and m.group("sign") in "−-"
        if not m.group("sign") and re.search(r"\b(?:fell|fallen|falls|dropped|decreased|declined|shrank|went\s+down|cut)\b", text[max(0, m.start() - 60):m.start()], re.IGNORECASE):
            fall = True  # a fall written without its sign is a negative change ('fell from 412 to 236 boats (42.72%)')
        # the stated per cent is read without its sign and the change in its direction: a fall as (x − y) ÷ x
        expr = f"({x} − {y}) ÷ {x} × 100" if fall else f"({y} − {x}) ÷ {x} × 100"
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), expr, m.group("p") + "%", bool(m.group("ap")))
        if r is not None:
            out.append((r.phrase, r.statement, r))
    for m in _P_PCT_PAIR_RE.finditer(text):
        x, y = _p_bare(m.group("x")), _p_bare(m.group("y"))
        fall = re.match(r"(?:fell|fallen|falls|dropped|decreased|decreases|declined|went\s+down)", m.group("dir"), re.IGNORECASE) is not None
        expr = f"({x} − {y}) ÷ {x} × 100" if fall else f"({y} − {x}) ÷ {x} × 100"
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), expr, m.group("p") + "%", bool(m.group("ap")))
        if r is not None:
            out.append((r.phrase, r.statement, r))
    for m in _P_PCT_WORK_RE.finditer(text):
        expr = " ".join(m.group("expr").split())
        if re.search(r"[A-Za-z]{3,}", re.sub(r"(?:thousand|million|billion|per\s*cent)", " ", expr, flags=re.IGNORECASE)):
            continue  # words in the bracket: a comment, not working
        if not re.search(r"×\s*100\b|\*\s*100\b", expr):
            continue  # a per cent's working multiplies by 100; any other bracket is read by the worked equations or not at all
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), expr, m.group("p") + "%", False)
        if r is not None:
            out.append((r.phrase, r.statement, r))
    for m in _P_PCT_PARTS_RE.finditer(text):
        # a per cent followed by its parts in brackets, joined by + and − ("56% in 2025 (100 − 54)", "79% in 2025 (28 + 27 + 22)": attack
        # round 5): the per cent is the sum of its parts, read and checked
        expr = " ".join(m.group("expr").split())
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), expr, m.group("p") + "%", False)
        if r is not None:
            out.append((r.phrase, r.statement, r))
    for m in _P_DIFFER_RE.finditer(text):
        a, b = m.group("a"), m.group("b")
        if (m.group("au") or "").strip() != (m.group("bu") or "").strip():
            continue  # figures in two units differ by no figure of one
        hi, lo = (a, b) if float(a.replace(",", "")) >= float(b.replace(",", "")) else (b, a)
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), f"{hi} − {lo}", m.group("d"), bool(m.group("ap")))
        if r is not None:
            out.append((r.phrase, r.statement, r))
    for m in _P_BOUND_RE.finditer(text):
        units = {m.group("u").lower().rstrip("s"), m.group("du").lower().rstrip("s"), m.group("yu").lower().rstrip("s")}
        if len(units) != 1:
            continue  # one quantity: the figure, the distance and the bound in one unit
        x, d, y = m.group("x"), m.group("d"), m.group("y")
        expr = f"{y} − {x}" if re.match(r"(?:below|under|short)", m.group("dir"), re.IGNORECASE) else f"{x} − {y}"
        r = _p_read(" ".join(m.group(0).split()), _p_sentence(text, m.start(), m.end()), expr, d, bool(m.group("ap") or m.group("ap2")))
        if r is not None:
            out.append((r.phrase, r.statement, r))
    out.extend(_p_cost_differences(text))
    return out[:MAX_WORKED_CHECKS]


def prose_problems(text: str, *, report_id: str, request_id: str, prefix: str) -> list[WorkedProblem]:
    """The engine problems of the prose arithmetic of ``text`` (section comment), numbered '-p1', '-p2'."""
    out: list[WorkedProblem] = []
    for n, (phrase, statement, r) in enumerate(_prose_reads(text), start=1):
        problem, description = _problem(r, pid=f"{prefix}-{report_id}-p{n}", claim_id=f"{report_id}:{prefix}-p{n}", request_id=request_id)
        try:
            Problem.model_validate(problem)
        except Exception:  # noqa: BLE001 - a problem the IR schema refuses is not built
            continue
        out.append(WorkedProblem(phrase, statement, problem, description.replace("the written arithmetic:", "the arithmetic stated in prose:", 1)))
    return out
