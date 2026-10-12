"""Decimal-exponent factoring and exact literal text (docs/STEM_DESIGN.md, section 7.3).

IR 1.0 bounds a numeric literal to ``max_const_digits`` (40) digits. Planck's constant to nine
significant figures already has 42 digits written as a plain decimal, so the STEM encodings
never write a scaled value in full. Every IR term built by :mod:`.to_ir` is a :class:`Term`:
an IR expression (the *mantissa*) and an integer decimal exponent ``k``, standing for
``⟦expr⟧ × 10^k``.

* A literal whose exact text is short (at most :data:`PLAIN_DIGITS` digits: ``20``, ``4.0``,
  ``0.0125``, ``5/18``) is kept as written with ``k = 0``, so a counterexample shows the values
  the report wrote. A longer one is split as ``m × 10^k`` with ``1 <= |m| < 10``
  (:func:`split`): ``6.62607015 × 10⁻³⁴`` is the literal ``6.62607015`` with ``k = -34``.
* Products and quotients add and subtract exponents; an integer power multiplies them.
* Sums and comparisons align their operands to the smallest exponent among them, scaling the
  others by an exact power of ten (a literal operand absorbs the power of ten into its own
  text; any other operand is multiplied by the literal ``10^d``).
* A comparison ``|C − S| ≤ h + τ·|C|`` is decided in a frame ``F`` (:func:`to_frame`,
  :func:`literal_in_frame`): ``|C·10^−F − S·10^−F| ≤ h·10^−F + τ·|C·10^−F|``, an exact identity
  because ``10^F > 0``. The engine therefore decides the relation with small literals, and the
  frame is recorded in the problem's notes ("decimal exponent factored: 10^F").

Only when a literal still has more than :data:`MAX_LITERAL_DIGITS` digits after factoring
(two terms of a sum that differ by more than about 10^38, say) is the relation not encoded:
:class:`LiteralTooLong` is raised and the caller reports ST-LIM-001. Exponents are integer
bookkeeping on written exponents and exact unit factors; nothing here decides a relation.
``Fraction`` values are built only from integer pairs, and every loop is bounded.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

__all__ = [
    "MAX_LITERAL_DIGITS", "MAX_NARY_ARGS", "PLAIN_DIGITS", "LiteralTooLong", "Term", "add_terms", "align", "digit_count", "div_literal", "floor_log10",
    "frame_for", "int_power", "lit", "literal_in_frame", "literal_text", "mul_terms", "nary", "neg_term", "real", "split", "sub_terms", "to_frame",
    "var_term",
]

#: the IR limit on the digits of one numeric literal (``Limits.max_const_digits``)
MAX_LITERAL_DIGITS = 40
#: a literal with at most this many digits is kept as written (``k = 0``)
PLAIN_DIGITS = 24
#: the largest power of ten one alignment may introduce (its literal has this many digits plus one)
_MAX_SHIFT = MAX_LITERAL_DIGITS - 1
#: integers whose bit length exceeds this are never formatted or split (a bound on work, far above any STEM value)
_MAX_BITS = 4096


class LiteralTooLong(ValueError):
    """A literal would exceed :data:`MAX_LITERAL_DIGITS` digits even after factoring (ST-LIM-001)."""


def _estimate(n: int) -> int:
    """A lower estimate of ``floor(log10(n))`` for a positive integer, from its bit length."""
    return (n.bit_length() - 1) * 30103 // 100000


def floor_log10(x: Fraction) -> int:
    """``floor(log10(|x|))`` for a non-zero rational, exactly (integer comparisons only)."""
    if x == 0:
        raise ValueError("floor_log10 of zero")
    x = abs(Fraction(x))
    if x.numerator.bit_length() > _MAX_BITS or x.denominator.bit_length() > _MAX_BITS:
        raise LiteralTooLong("a value too large to factor")
    k = _estimate(x.numerator) - _estimate(x.denominator) - 1
    ten = Fraction(10)
    for _ in range(8):  # the estimate is within two of the answer; the loop is bounded
        if ten ** (k + 1) <= x:
            k += 1
        else:
            break
    for _ in range(8):
        if ten ** k > x:
            k -= 1
        else:
            break
    return k


def split(value: Fraction) -> tuple[Fraction, Optional[int]]:
    """``value = m × 10^k`` with ``1 <= |m| < 10``; ``(0, None)`` for exact zero (scale-free)."""
    if value == 0:
        return Fraction(0), None
    k = floor_log10(value)
    return Fraction(value) / (Fraction(10) ** k), k


def literal_text(value: Fraction) -> str:
    """Exact IR text of a rational: an integer (``-7``), a terminating decimal (``0.25``) or
    ``p/q`` (``5/18``). The decimal form is used whenever it is exact because its digit count is
    the value's own (``0.000125`` has 7 digits, ``1/8000`` has 5; both are accepted)."""
    value = Fraction(value)
    if value.numerator.bit_length() > _MAX_BITS or value.denominator.bit_length() > _MAX_BITS:
        raise LiteralTooLong("a value too large to write")
    if value.denominator == 1:
        return str(value.numerator)
    den = value.denominator
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        return f"{value.numerator}/{value.denominator}"
    places = max(twos, fives)
    scaled = abs(value.numerator) * (10 ** places) // value.denominator
    digits = str(scaled).rjust(places + 1, "0")
    sign = "-" if value < 0 else ""
    return f"{sign}{digits[:-places]}.{digits[-places:]}"


def digit_count(text: str) -> int:
    """Digits of a literal text, counted as the IR validator counts them."""
    return sum(1 for ch in text if "0" <= ch <= "9")


def _checked_text(value: Fraction) -> str:
    value = Fraction(value)
    if value.numerator.bit_length() > 5 * MAX_LITERAL_DIGITS or value.denominator.bit_length() > 5 * MAX_LITERAL_DIGITS:
        raise LiteralTooLong(f"a literal of more than {MAX_LITERAL_DIGITS} digits")
    text = literal_text(value)
    if digit_count(text) > MAX_LITERAL_DIGITS:
        raise LiteralTooLong(f"the literal {text[:24]}… has {digit_count(text)} digits after decimal-exponent factoring; the bound is {MAX_LITERAL_DIGITS}")
    return text


def real(value: Fraction) -> dict:
    """A Real literal node of ``value`` (at most :data:`MAX_LITERAL_DIGITS` digits)."""
    return {"op": "real", "value": _checked_text(Fraction(value))}


@dataclass(frozen=True)
class Term:
    """``⟦expr⟧ × 10^k``. ``closed`` when ``expr`` holds no IR variable; ``lit`` is the mantissa when
    ``expr`` is a single literal; ``zero`` for an exact zero literal, which takes any exponent."""

    expr: dict
    k: int = 0
    closed: bool = True
    lit: Optional[Fraction] = None
    zero: bool = False

    @property
    def value(self) -> Optional[Fraction]:
        """The exact value when the term is a single literal."""
        if self.zero:
            return Fraction(0)
        if self.lit is None:
            return None
        return self.lit * (Fraction(10) ** self.k)


def lit(value: Fraction) -> Term:
    """A literal term: kept as written when its text is short, else split as ``m × 10^k``."""
    v = Fraction(value)
    if v == 0:
        return Term({"op": "real", "value": "0"}, 0, True, Fraction(0), True)
    if v.numerator.bit_length() <= 5 * PLAIN_DIGITS and v.denominator.bit_length() <= 5 * PLAIN_DIGITS:
        text = literal_text(v)
        if digit_count(text) <= PLAIN_DIGITS:
            return Term({"op": "real", "value": text}, 0, True, v)
    m, k = split(v)
    assert k is not None
    return Term({"op": "real", "value": _checked_text(m)}, k, True, m)


def var_term(name: str, k: int = 0) -> Term:
    """An IR variable standing for ``name × 10^k``."""
    return Term({"op": "var", "name": name}, k, False)


def literal_in_frame(value: Fraction, frame: int) -> dict:
    """The literal ``value × 10^−frame`` (``value`` expressed in a frame of exponent ``frame``)."""
    v = Fraction(value)
    if v == 0:
        return {"op": "real", "value": "0"}
    if abs(frame) > 4 * MAX_LITERAL_DIGITS + 400:
        raise LiteralTooLong("an exponent too far from the frame")
    return {"op": "real", "value": _checked_text(v / (Fraction(10) ** frame))}


def _ten(d: int) -> dict:
    if d > _MAX_SHIFT:
        raise LiteralTooLong(f"a factor 10^{d} exceeds {MAX_LITERAL_DIGITS} digits")
    return {"op": "real", "value": "1" + "0" * d}


def _scaled_expr(t: Term, d: int) -> dict:
    """``t`` multiplied by ``10^d`` (``d >= 0``) so it can sit in a frame ``d`` places lower."""
    if d == 0 or t.zero:
        return t.expr
    if d > _MAX_SHIFT + 400:
        raise LiteralTooLong("terms whose exponents differ too much to align")
    if t.lit is not None:
        return {"op": "real", "value": _checked_text(t.lit * (Fraction(10) ** d))}
    factor = _ten(d)
    if t.expr.get("op") == "mul" and len(t.expr["args"]) < MAX_NARY_ARGS:
        return {"op": "mul", "args": [factor] + list(t.expr["args"])}
    return {"op": "mul", "args": [factor, t.expr]}


def to_frame(t: Term, frame: int) -> dict:
    """The expression of ``⟦t⟧ × 10^(t.k − frame)``: the term's value expressed in the frame ``frame``.
    Raises :class:`LiteralTooLong` when the power of ten needed does not fit a literal."""
    if t.zero:
        return {"op": "real", "value": "0"}
    d = t.k - frame
    if d >= 0:
        return _scaled_expr(t, d)
    if t.lit is not None:
        return {"op": "real", "value": _checked_text(t.lit / (Fraction(10) ** (-d)))}
    return {"op": "div", "left": t.expr, "right": _ten(-d)}


def frame_for(t: Term, stated: Optional[Fraction] = None) -> int:
    """The frame a comparison is decided in: ``0`` when the computed term and the stated value both
    fit as written; else the computed term's exponent; else the stated value's own exponent."""
    candidates = [0, t.k]
    if stated is not None and stated != 0:
        _m, ks = split(stated)
        if ks is not None:
            candidates.append(ks)
    for f in candidates:
        try:
            to_frame(t, f)
            if stated is not None:
                literal_in_frame(stated, f)
            return f
        except LiteralTooLong:
            continue
    raise LiteralTooLong("no decimal frame holds both the computed expression and the stated value within the literal bound")


#: the IR limit on the arguments of one n-ary node (``Limits.max_nary_args``)
MAX_NARY_ARGS = 32


def nary(op: str, args: list[dict]) -> dict:
    """An n-ary ``add``/``mul``/``and``/``or`` node; beyond :data:`MAX_NARY_ARGS` arguments the
    tail is nested, so no node exceeds the IR bound."""
    if len(args) == 1:
        return args[0]
    if len(args) <= MAX_NARY_ARGS:
        return {"op": op, "args": list(args)}
    head = list(args[:MAX_NARY_ARGS - 1])
    return {"op": op, "args": head + [nary(op, list(args[MAX_NARY_ARGS - 1:]))]}


def align(*terms: Term) -> tuple[list[dict], int]:
    """The expressions of ``terms`` in one frame (the smallest exponent among them) and that exponent."""
    ks = [t.k for t in terms if not t.zero]
    base = min(ks) if ks else 0
    return [_scaled_expr(t, t.k - base) for t in terms], base


def add_terms(terms: list[Term]) -> Term:
    """``Σ terms`` in one frame; nested sums are flattened (n-ary ``add``)."""
    live = [t for t in terms if not t.zero] or terms[:1]
    if len(live) == 1:
        return live[0]
    exprs, k = align(*live)
    args: list[dict] = []
    for e in exprs:
        if e.get("op") == "add":
            args.extend(e["args"])
        else:
            args.append(e)
    return Term(nary("add", args), k, all(t.closed for t in live))


def sub_terms(a: Term, b: Term) -> Term:
    if b.zero:
        return a
    if a.zero:
        return neg_term(b)
    (ea, eb), k = align(a, b)
    return Term({"op": "sub", "left": ea, "right": eb}, k, a.closed and b.closed)


def neg_term(a: Term) -> Term:
    if a.zero:
        return a
    if a.lit is not None:
        return Term({"op": "real", "value": _checked_text(-a.lit)}, a.k, True, -a.lit)
    return Term({"op": "neg", "arg": a.expr}, a.k, a.closed)


def mul_terms(factors: list[Term]) -> tuple[Term, bool]:
    """``Π factors``: exponents add. Returns the term and whether two or more factors hold a
    variable (a nonlinear product)."""
    if len(factors) == 1:
        return factors[0], False
    if any(f.zero for f in factors):
        return lit(Fraction(0)), False
    args: list[dict] = []
    k = 0
    for f in factors:
        k += f.k
        if f.expr.get("op") == "mul":
            args.extend(f.expr["args"])
        else:
            args.append(f.expr)
    open_factors = sum(1 for f in factors if not f.closed)
    return Term(nary("mul", args), k, open_factors == 0), open_factors >= 2


def div_literal(a: Term, b: Term) -> Term:
    """``a / b`` for a non-zero single-literal divisor: the IR ``div`` the validator admits."""
    if b.lit is None or b.zero:
        raise ValueError("div_literal needs a non-zero literal divisor")
    if a.zero:
        return a
    return Term({"op": "div", "left": a.expr, "right": b.expr}, a.k - b.k, a.closed)


def int_power(base: Term, n: int) -> tuple[Term, bool]:
    """``base^n`` for ``2 <= n <= 12`` as a product of ``n`` copies of a literal, a closed term or a variable."""
    return mul_terms([base] * n)
