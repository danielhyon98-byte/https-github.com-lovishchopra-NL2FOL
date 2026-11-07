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

__all__ = ["MAX_DEPTH", "MAX_TOKENS", "MAX_WORKED_CHECKS", "WORKED_RULE", "WORKED_SCOPE", "WorkedProblem", "breakdown_problems", "decided_worked_chains",
           "worked_problems"]

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

_CUR = r"(?:US\$|U\.S\.\s?\$|A\$|C\$|\$|£|€|¥)"
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
    scan = scan_number(s, i)
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


@dataclass(frozen=True)
class _Read:
    phrase: str
    statement: str
    links: tuple            # parsed expression links (trees)
    shown_links: tuple[str, ...]
    result: _Fig
    approx: bool


def _strip_label(link: str) -> str:
    """The first link without the label words before its first figure ('The tax is $0.40 × ...'), or a refusal when those words take
    part in the arithmetic ('half of $6,000 ÷ 2')."""
    m = re.search(rf"[\d(\[]|{_CUR}|[-−]\s*(?:{_CUR}\s*)?\d|\.\d", link)
    if m is None:
        raise _Refuse("no figure")
    head = link[:m.start()]
    if not head.strip():
        return link
    if re.search(r"\d", head) or not re.fullmatch(r"[\s\w'’:,.\-]+", head):
        raise _Refuse("label words outside the reading")
    words = re.findall(r"[A-Za-z]+", head)
    if words and words[-1].lower() in _ARITHMETIC_WORDS:
        raise _Refuse("label words that take part in the arithmetic")
    return link[m.start():]


def _read(phrase: str, statement: str) -> _Read:
    parts = re.split(r"([=≈])", phrase)
    links = parts[0::2]
    seps = parts[1::2]
    if len(links) < 2:
        raise _Refuse("no stated result")
    links = [_strip_label(links[0])] + links[1:]
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
    if len(units) > 1:
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
_YEAR_ONLY_RE = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
#: The longest text the breakdown reader reads.
_BREAKDOWN_MAX_CHARS = 200_000


def _breakdown_reads(text: str) -> list[tuple[str, str, _Read]]:
    """``(phrase, statement, read)`` for every figure of ``text`` stated with the sum of its parts in brackets: the parts are read as the
    written expression and the figure before the bracket (with its scale word) as its stated result, so the engine decides it as any worked
    line (the scale rule included: '$1,237.50 million ... ($712.50 + $525)' is read in millions). Years in brackets ('(2019 + 2020)') are
    no parts."""
    out: list[tuple[str, str, _Read]] = []
    for m in _BREAKDOWN_RE.finditer(text[:_BREAKDOWN_MAX_CHARS]):
        parts = m.group("parts")
        figures = re.findall(r"\d[\d,.]*", parts)
        if all(_YEAR_ONLY_RE.match(f) for f in figures):
            continue
        stated_text = m.group("stated") + m.group("words")
        try:
            toks = _tokens(parts)
            tree = _Parser(toks).parse()
            result, _end = _read_figure(stated_text.strip(), 0)
        except _Refuse:
            continue
        except Exception:  # noqa: BLE001 - never an exception on agent text: the figure is not read
            continue
        figs = _figures(tree) + [result]
        if len({f.cur for f in figs if f.cur}) > 1 or len({k for f in figs for w in f.units for k in [_unit_key(w)] if k}) > 1:
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        statement = text[line_start: line_end if line_end >= 0 else len(text)].strip()
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
    """The phrases of the worked equations of ``text`` that :func:`worked_problems` builds a problem for."""
    return {phrase for phrase, _s, r, _w in _reads(text) if r is not None}
