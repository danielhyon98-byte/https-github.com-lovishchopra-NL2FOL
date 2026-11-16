"""Polynomials in one variable, for the antiderivative check (docs/STEM_DESIGN.md, section 7.9).

An indefinite integral of a polynomial written with the antiderivative the answer states (``∫6t dt = 3t²``,
``∫(6t − 3t²) dt = 3t² − t³ + C``) is checked by differentiating the stated antiderivative and setting the result
against the integrand for every value of the variable: the STEM pack forms the derivative of the parsed polynomial by
the power rule (this module; exact rational coefficients, a constant of integration drops out), and the engine decides
that the two polynomials are the same (an algebra check from a trivially true premise, so it holds iff they agree for
every value). Nothing here evaluates text: the input is a parsed node, the output a node. Anything that is not a
polynomial with rational coefficients in the variable (a function, a root, a symbol multiplying the variable, a power
beyond the bound) is refused (None), and the integral stays outside the encodings.

STEM repair 10 (rule definite-integral): a definite integral of a polynomial with whole-number limits set against a value
(``∫₀¹ 6t dt = 3``) is set against the antiderivative this module forms by the power rule taken the other way
(:func:`antiderivative`), evaluated between the limits by substitution; the engine decides the closed arithmetic.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Optional

from .nodes import BinOp, Neg, Node, Num, Pow, Sym
from .numbers import exact_integer

__all__ = ["antiderivative", "derivative", "laurent", "laurent_derivative", "laurent_node", "polynomial", "polynomial_node"]

#: the largest degree read (the parser's bound on an integer power)
MAX_DEGREE = 12
_MAX_DEPTH = 64


def polynomial(node: Node, x: str, depth: int = 0) -> Optional[tuple[dict[int, Fraction], bool]]:
    """``({power: coefficient}, has_constant_symbols)`` of ``node`` as a polynomial in ``x``. A symbol other than ``x``
    may only stand in an added constant (a constant of integration ``C``); None for anything else."""
    if depth > _MAX_DEPTH:
        return None
    if isinstance(node, Num):
        return ({0: node.number.value} if node.number.value else {}), False
    if isinstance(node, Sym):
        if node.kind == "constant":
            return None
        return ({1: Fraction(1)}, False) if node.name == x else ({}, True)
    if isinstance(node, Neg):
        inner = polynomial(node.arg, x, depth + 1)
        return None if inner is None else ({k: -c for k, c in inner[0].items()}, inner[1])
    if isinstance(node, BinOp):
        a = polynomial(node.left, x, depth + 1)
        b = polynomial(node.right, x, depth + 1)
        if a is None or b is None:
            return None
        if node.op in ("+", "-"):
            out = dict(a[0])
            for k, c in b[0].items():
                out[k] = out.get(k, Fraction(0)) + (c if node.op == "+" else -c)
            return {k: c for k, c in out.items() if c}, a[1] or b[1]
        if node.op == "*":
            if (a[1] and (b[1] or any(k > 0 for k in b[0]))) or (b[1] and any(k > 0 for k in a[0])):
                return None  # a symbol times the variable: no polynomial with rational coefficients
            out = {}
            for i, ci in a[0].items():
                for j, cj in b[0].items():
                    if i + j > MAX_DEGREE:
                        return None
                    out[i + j] = out.get(i + j, Fraction(0)) + ci * cj
            return {k: c for k, c in out.items() if c}, a[1] or b[1]
        if node.op == "/":
            if b[1] or set(b[0]) - {0} or not b[0].get(0):
                return None  # only a non-zero number divides
            return {k: c / b[0][0] for k, c in a[0].items()}, a[1]
        return None
    if isinstance(node, Pow):
        if node.exp < 0 or node.exp > MAX_DEGREE:
            return None
        base = polynomial(node.base, x, depth + 1)
        if base is None or base[1]:
            return None
        out: dict[int, Fraction] = {0: Fraction(1)}
        for _ in range(node.exp):
            nxt: dict[int, Fraction] = {}
            for i, ci in out.items():
                for j, cj in base[0].items():
                    if i + j > MAX_DEGREE:
                        return None
                    nxt[i + j] = nxt.get(i + j, Fraction(0)) + ci * cj
            out = {k: c for k, c in nxt.items() if c}
        return out, False
    return None


def derivative(coeffs: dict[int, Fraction]) -> dict[int, Fraction]:
    """The power rule: ``d/dx Σ c_k x^k = Σ k c_k x^(k−1)``."""
    return {k - 1: k * c for k, c in coeffs.items() if k >= 1 and c}


def antiderivative(coeffs: dict[int, Fraction]) -> Optional[dict[int, Fraction]]:
    """STEM repair 10 (rule definite-integral): the power rule taken the other way, ``∫ Σ c_k x^k dx = Σ c_k/(k+1) x^(k+1)`` (the constant
    of integration 0, which a definite integral cancels); None beyond the degree bound."""
    if any(k + 1 > MAX_DEGREE for k, c in coeffs.items() if c):
        return None
    return {k + 1: c / (k + 1) for k, c in coeffs.items() if k >= 0 and c}


def _number(v: Fraction, start: int, end: int) -> Node:
    if v.denominator == 1:
        return Num(exact_integer(int(v)), start, end)
    return BinOp("/", Num(exact_integer(v.numerator), start, end), Num(exact_integer(v.denominator), start, end), start, end, "/")


def polynomial_node(coeffs: dict[int, Fraction], x: str, start: int = 0, end: int = 0) -> Node:
    """The node of ``Σ c_k x^k`` (highest power first; ``0`` for the zero polynomial)."""
    terms = sorted(((k, c) for k, c in coeffs.items() if c), reverse=True)
    if not terms:
        return Num(exact_integer(0), start, end)
    out: Optional[Node] = None
    for k, c in terms:
        mag = abs(c)
        var: Optional[Node] = None if k == 0 else (Sym(x, "symbol", start, end) if k == 1 else Pow(Sym(x, "symbol", start, end), k, start, end))
        if var is None:
            term: Node = _number(mag, start, end)
        elif mag == 1:
            term = var
        else:
            term = BinOp("*", _number(mag, start, end), var, start, end, "×")
        if out is None:
            out = term if c > 0 else Neg(term, start, end)
        else:
            out = BinOp("+" if c > 0 else "-", out, term, start, end, "+" if c > 0 else "−")
    return out  # type: ignore[return-value]


# --------------------------------------------------------------------------- round-10 clearance (rule derivative, Laurent terms)

#: a term's key: (the power of the variable, the constant factors it carries, as a sorted tuple of names: ('π',) for 2πr²)
LaurentKey = tuple[int, tuple[str, ...]]
#: the named constants a coefficient may carry (an exact symbol the encoder encloses; the identity then holds for every value of it)
_COEFFICIENT_CONSTANTS = frozenset({"π"})
#: the most terms a Laurent polynomial is read with
_MAX_TERMS = 24


def laurent(node: Node, x: str, depth: int = 0) -> Optional[dict[LaurentKey, Fraction]]:
    """Round-10 clearance (rule derivative, Laurent terms): ``node`` as a sum of terms ``c · K · x^k``, ``c`` rational, ``K`` a product of
    the named constants of :data:`_COEFFICIENT_CONSTANTS` (π), ``k`` a whole number between ``−MAX_DEGREE`` and ``MAX_DEGREE`` (negative
    powers included: '660r⁻¹', '660/r²'): ``{(k, K): c}``. None for anything else (another symbol, a function, a root, a division by a sum),
    so the relation stays outside the encodings. Nothing is evaluated: the input is a parsed node."""
    if depth > _MAX_DEPTH:
        return None
    if isinstance(node, Num):
        return {(0, ()): node.number.value} if node.number.value else {}
    if isinstance(node, Sym):
        if node.name == x and node.kind == "symbol":
            return {(1, ()): Fraction(1)}
        if node.kind == "constant" and node.name in _COEFFICIENT_CONSTANTS:
            return {(0, (node.name,)): Fraction(1)}
        return None
    if isinstance(node, Neg):
        inner = laurent(node.arg, x, depth + 1)
        return None if inner is None else {k: -c for k, c in inner.items()}
    if isinstance(node, Pow):
        if abs(node.exp) > MAX_DEGREE or node.exp == 0:
            return None if node.exp else {(0, ()): Fraction(1)}
        base = laurent(node.base, x, depth + 1)
        if base is None or len(base) != 1:
            return None  # only a single term is raised to a power here ((r + 1)² is a polynomial's, read by :func:`polynomial`)
        (k, consts), c = next(iter(base.items()))
        if consts and node.exp < 0:
            return None
        return _clean({(k * node.exp, tuple(sorted(consts * node.exp)) if node.exp > 0 else ()): c ** node.exp})
    if isinstance(node, BinOp):
        a = laurent(node.left, x, depth + 1)
        b = laurent(node.right, x, depth + 1)
        if a is None or b is None:
            return None
        if node.op in ("+", "-"):
            out = dict(a)
            for key, c in b.items():
                out[key] = out.get(key, Fraction(0)) + (c if node.op == "+" else -c)
            return _clean(out)
        if node.op == "*":
            out = {}
            for (i, ki), ci in a.items():
                for (j, kj), cj in b.items():
                    if abs(i + j) > MAX_DEGREE:
                        return None
                    key = (i + j, tuple(sorted(ki + kj)))
                    out[key] = out.get(key, Fraction(0)) + ci * cj
            return _clean(out)
        if node.op == "/":
            if len(b) != 1:
                return None  # a division by a sum is no Laurent term
            (j, kj), cj = next(iter(b.items()))
            if kj or not cj:
                return None  # a division by a constant symbol or by zero
            out = {}
            for (i, ki), ci in a.items():
                if abs(i - j) > MAX_DEGREE:
                    return None
                out[(i - j, ki)] = out.get((i - j, ki), Fraction(0)) + ci / cj
            return _clean(out)
    return None


def _clean(terms: dict[LaurentKey, Fraction]) -> Optional[dict[LaurentKey, Fraction]]:
    out = {k: c for k, c in terms.items() if c}
    return out if len(out) <= _MAX_TERMS else None


def laurent_derivative(terms: dict[LaurentKey, Fraction]) -> dict[LaurentKey, Fraction]:
    """The power rule on each term, negative powers included: ``d/dx c·K·x^k = k·c·K·x^(k−1)``."""
    out: dict[LaurentKey, Fraction] = {}
    for (k, consts), c in terms.items():
        if k:
            key = (k - 1, consts)
            out[key] = out.get(key, Fraction(0)) + k * c
    return {k: c for k, c in out.items() if c}


def laurent_node(terms: dict[LaurentKey, Fraction], x: str, start: int = 0, end: int = 0) -> Node:
    """The node of ``Σ c·K·x^k`` (highest power first; a negative power written as a division by the variable's power)."""
    items = sorted(((k, consts, c) for (k, consts), c in terms.items() if c), key=lambda t: (-t[0], t[1]))
    if not items:
        return Num(exact_integer(0), start, end)
    out: Optional[Node] = None
    for k, consts, c in items:
        mag = abs(c)
        factors: list[Node] = []
        if mag != 1 or (not consts and k == 0):
            factors.append(_number(mag, start, end))
        factors.extend(Sym(name, "constant", start, end) for name in consts)
        if k > 0:
            factors.append(Sym(x, "symbol", start, end) if k == 1 else Pow(Sym(x, "symbol", start, end), k, start, end))
        term: Node = factors[0] if factors else Num(exact_integer(1), start, end)
        for f in factors[1:]:
            term = BinOp("*", term, f, start, end, "×")
        if k < 0:
            denominator: Node = Sym(x, "symbol", start, end) if k == -1 else Pow(Sym(x, "symbol", start, end), -k, start, end)
            term = BinOp("/", term, denominator, start, end, "/")
        if out is None:
            out = term if c > 0 else Neg(term, start, end)
        else:
            out = BinOp("+" if c > 0 else "-", out, term, start, end, "+" if c > 0 else "−")
    return out  # type: ignore[return-value]
