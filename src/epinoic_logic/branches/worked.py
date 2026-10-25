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

__all__ = ["MAX_DEPTH", "MAX_TOKENS", "MAX_WORKED_CHECKS", "WORKED_RULE", "WORKED_SCOPE", "WorkedProblem", "decided_worked_chains", "worked_problems"]

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
               "digits when every figure is exact; a per cent sign read as a fraction and, for a stated result in per cent, as written")

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
    if j < len(s) and s[j].isdigit():
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
    trees = []
    for link in expr_links:
        toks = _tokens(link)
        if not any(t[0] == "op" or t[0] == "pow" for t in toks):
            raise _Refuse("a link that is not an expression")
        trees.append(_Parser(toks).parse())
    rl = result_link.strip()
    sign = 1
    while rl[:1] in "-−":
        sign = -sign
        rl = rl[1:].lstrip()
    cur_first = _CUR_RE.match(rl)
    if cur_first:
        after = rl[cur_first.end():].lstrip()
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


@lru_cache(maxsize=32)
def _reads(text: str) -> tuple[tuple[str, str, Optional[_Read], str], ...]:
    """``(phrase, statement, read or None, why not)`` for every worked equation of ``text``, at most :data:`MAX_WORKED_CHECKS` read."""
    out: list[tuple[str, str, Optional[_Read], str]] = []
    for eq in worked_equations(text):
        if sum(1 for _p, _s, r, _w in out if r is not None) >= MAX_WORKED_CHECKS:
            out.append((eq.phrase, eq.statement, None, "the limit of worked-arithmetic checks per report was reached"))
            continue
        try:
            r = _read(eq.phrase, eq.statement)
            Problem.model_validate(_problem(r, pid="worked-check", claim_id="worked-check", request_id="worked-check")[0])  # the IR's own schema
            out.append((eq.phrase, eq.statement, r, ""))
        except _Refuse as why:
            out.append((eq.phrase, eq.statement, None, str(why)))
        except Exception as exc:  # noqa: BLE001 - never an exception on agent text; the equation stays named undecided (CORE-QNT-001)
            out.append((eq.phrase, eq.statement, None, f"not read ({type(exc).__name__})"))
    return tuple(out)


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


def _problem(r: _Read, *, pid: str, claim_id: str, request_id: str) -> tuple[dict, str]:
    operands = [f for t in r.links for f in _figures(t)]
    S = r.result
    has_pct_operand = any(f.percent for f in operands)
    readings: list[tuple[str, bool, bool]] = [("per cent as a fraction" if (has_pct_operand or S.percent) else "as written", True, True)]
    if S.percent:
        readings.append(("the stated per cent as written, an operand's per cent as a fraction" if has_pct_operand else "the stated per cent as written", True, False))
    if has_pct_operand and not S.cur and not any(f.cur for f in operands):
        # per-cent arithmetic stated in per cent or in points ('12.5% − 10.0% = 2.5 percentage points'); never for an amount of money
        # ('5% × $200 = $1,000' is no reading of a tax of 5 per cent)
        readings.append(("every per cent as written", False, False))
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
        h_written = Fraction(1, 2) if S.number.digit_count >= 2 else Fraction(0)
    else:
        h_written = S.number.half_width_for(min_sf)
    h_written *= Fraction(10) ** S.scale
    symbols: list[dict] = []
    premises: list[dict] = []
    bands: list[dict] = []
    shown_expr = " = ".join(r.shown_links)
    for k, (label, pct_operands, pct_result) in enumerate(readings, start=1):
        tag = "" if k == 1 else str(k)
        enc = _Encoder(tag, pct_operands)
        c, r_name = f"c{tag}", f"r{tag}"
        stated = S.value / 100 if (S.percent and pct_result) else S.value
        h = h_written / 100 if (S.percent and pct_result) else h_written
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
    names = "; ".join(label for label, _a, _b in readings)
    mode = ("exact mode: every figure is exact" + (", h = 1/2" if h_written else ", h = 0") if exact else
            f"h = {_fmt(h_written)}" + (" (≈ or about: τ = 1/20)" if r.approx else ""))
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
        out.append(WorkedProblem(phrase, statement, problem, description))
    return out


def decided_worked_chains(text: str) -> set[str]:
    """The phrases of the worked equations of ``text`` that :func:`worked_problems` builds a problem for."""
    return {phrase for phrase, _s, r, _w in _reads(text) if r is not None}
