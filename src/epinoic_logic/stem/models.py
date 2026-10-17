"""Exponential models and their evaluations: the ``mod`` check (section 4.7 of docs/STEM_DESIGN.md).

A *model* is a function of one variable that the answer or the request defines with a power of e, or of a positive
closed base, whose exponent holds symbols: ``P = P₀e^(kt)`` (a request that names no variable: the answer's
applications ``P(t)``, ``P(t + 1)`` name it), ``C(t) = C0 e^(−kt)``, ``A(t) = 500 × 1.05^t``. An *application* is the
model's letter glued to a bracket in the answer (``P(t + 4)``, ``P(6)``), which the parser reads as a product (a
function name other than f, g and h is no function to it); in a ``mod`` check it is the model's expression with the
variable replaced by the argument. Nothing here evaluates text: every rewrite rebuilds a tree of the parser's nodes, and
the application is told apart from a product only by the written text (the letter glued to its bracket).

The encoding (``checks._mod``) asks whether any value of the variables, and of the stated symbols within their stated
values, satisfies the link. It reads every power ``B^X`` of an exponent in symbols through positive variables: with
``X = c + Σ qᵢ·mᵢ`` (``c`` a rational constant, ``qᵢ`` rational, ``mᵢ`` distinct monomials) and ``sᵢ`` the largest rational
step of which every coefficient of ``mᵢ`` in the link (on both sides, for one base) is an integer multiple,
``B^X = B^c · Π uᵢ^(qᵢ/sᵢ)`` with ``uᵢ = B^(sᵢ·mᵢ) > 0``, bounded by the enclosure of ``B^(sᵢ·range)`` when every symbol of
``mᵢ`` has stated values. Every real solution of the link gives positive values of the ``uᵢ``, so the reading only widens
the solutions: UNSATISFIABLE proves that no value satisfies the link (``P(t + 4) = P₀e^(k(t + 1))`` asks ``e^(3k) = 1``
with k stated as 2.05), SATISFIABLE never proves that the link holds for every value.

What is read is deliberately narrow, so a misreading never decides anything: the link is an equality written with ``=``
whose two sides hold no written decimal (a rounded figure in a model relation would need its rounding interval, and an
identity such as ``N(t + 5) = 0.5 N(t)`` holds only within it), no unit, no other construct outside the encodings, and
at least one application; an exponent is a polynomial in symbols with rational coefficients (degree at most
``MAX_DEGREE``); a base is e or a positive rational. A model's own definition (``C(t) = C0 e^(−kt)``) is no check.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from math import gcd, lcm
from typing import Callable, Optional

from .nodes import (
    Abs, Apply, BinOp, BoolOp, Degrees, Func, Magnification, Neg, Node, Num, Percent, PlusMinus, Pow, Quantity, Ratio, RealPower, Root, Sym, Unsupported,
    WithUnit, walk,
)
from .scope import Model

__all__ = [
    "Exponential", "MAX_DEGREE", "MAX_MONOMIALS", "MAX_POWER", "Model", "all_symbols", "application_of", "applications", "denominators", "exact_value",
    "has_exponential",
    "exponential", "exponent_polynomial", "is_model_expression", "model_link_sides", "monomial_node", "relaxation_fits", "render_model", "resolve_model", "rewrite_applications",
    "split_runs", "substitute",
]

#: the largest total degree of a monomial in an exponent, the most distinct monomials (per base) in one link, and the
#: largest power of one positive variable the reading may write (the nonlinear policy bounds the degree of the whole term)
MAX_DEGREE = 4
MAX_MONOMIALS = 8
MAX_POWER = 12
_MAX_DEPTH = 64
#: node types a side of a model link may hold besides numerals, symbols and the powers of an exponent in symbols
_ALLOWED = (Neg, BinOp, Pow, RealPower, Func, Root)
_REFUSED = (Quantity, WithUnit, Percent, Degrees, PlusMinus, Apply, Abs, Magnification, Ratio, BoolOp)


@dataclass(frozen=True)
class Exponential:
    """A power whose exponent holds symbols: ``base`` None for e, else the closed base node."""

    base: Optional[Node]
    exponent: Node


def exponential(node: Node) -> Optional[Exponential]:
    """The base and exponent of a power whose exponent holds symbols (``e^(kt)``, ``1.05^t``), as the parser keeps them."""
    if isinstance(node, Unsupported) and node.reason == "a symbolic power" and node.arg is not None:
        if node.name == "exp":
            return Exponential(None, node.arg)
        if node.name == "pow" and node.base is not None:
            return Exponential(node.base, node.arg)
    return None


def _children(node: Node) -> tuple[Node, ...]:
    e = exponential(node)
    if e is not None:
        return (e.exponent,) if e.base is None else (e.base, e.exponent)
    from .nodes import children
    return children(node)


def _walk(node: Node):
    """Every node, the exponents of the powers in symbols included (``nodes.walk`` stops at an unsupported node)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        stack.extend(reversed(_children(cur)))


def all_symbols(node: Node) -> set[str]:
    """The names of the symbols of ``node``, those in the exponents of its powers included (constants are no symbols)."""
    return {n.name for n in _walk(node) if isinstance(n, Sym) and n.kind == "symbol"}


def has_exponential(node: Node) -> bool:
    return any(exponential(n) is not None for n in _walk(node))


def exact_value(node: Node) -> Optional[Fraction]:
    """The exact rational value of a closed node of written integers (``250``, ``1/2``, ``−5``, ``2^3``): no decimal, no
    function, no constant; None otherwise. Exact integer arithmetic on the parser's numerals only."""
    if isinstance(node, Num):
        n = node.number
        if n.has_point or n.scientific or n.base != 10:
            return None
        return n.value
    if isinstance(node, Neg):
        v = exact_value(node.arg)
        return None if v is None else -v
    if isinstance(node, BinOp) and node.op in ("+", "-", "*", "/"):
        a, b = exact_value(node.left), exact_value(node.right)
        if a is None or b is None:
            return None
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        return None if b == 0 else a / b
    if isinstance(node, Pow) and abs(node.exp) <= 12:
        v = exact_value(node.base)
        if v is None or (v == 0 and node.exp < 0):
            return None
        return v ** node.exp
    return None


def exact_numerals(node: Node) -> bool:
    """Every numeral of ``node`` (the exponents of its powers included) is written exactly: no decimal point, no
    scientific notation (a rounded figure in a model relation would need its rounding interval)."""
    for n in _walk(node):
        if isinstance(n, Num) and (n.number.has_point or n.number.scientific or n.number.base != 10):
            return False
    return True


Monomial = tuple[tuple[str, int], ...]


def exponent_polynomial(node: Node) -> Optional[dict[Monomial, Fraction]]:
    """``node`` (an exponent) as a polynomial with rational coefficients: monomial (sorted ``(symbol, power)`` pairs; ``()``
    is the constant) to coefficient, zero coefficients dropped. None for anything else: a decimal, a constant (π), a
    function, a division by a symbol, a degree beyond :data:`MAX_DEGREE`."""
    out = _poly(node, 0)
    if out is None:
        return None
    if any(sum(p for _s, p in m) > MAX_DEGREE for m in out):
        return None
    return {m: c for m, c in out.items() if c != 0}


def _poly(node: Node, depth: int) -> Optional[dict[Monomial, Fraction]]:
    if depth > _MAX_DEPTH:
        return None
    if isinstance(node, Num):
        v = exact_value(node)
        return None if v is None else {(): v}
    if isinstance(node, Sym):
        return {((node.name, 1),): Fraction(1)} if node.kind == "symbol" else None
    if isinstance(node, Neg):
        a = _poly(node.arg, depth + 1)
        return None if a is None else {m: -c for m, c in a.items()}
    if isinstance(node, BinOp):
        a, b = _poly(node.left, depth + 1), _poly(node.right, depth + 1)
        if a is None or b is None:
            return None
        if node.op in ("+", "-"):
            out = dict(a)
            for m, c in b.items():
                out[m] = out.get(m, Fraction(0)) + (c if node.op == "+" else -c)
            return out
        if node.op == "*":
            return _times(a, b)
        if node.op == "/":
            if set(b) != {()} or b[()] == 0:
                return None  # a division by a symbol is no polynomial
            return {m: c / b[()] for m, c in a.items()}
        return None
    if isinstance(node, Pow) and 0 <= node.exp <= MAX_DEGREE:
        a = _poly(node.base, depth + 1)
        if a is None:
            return None
        out: dict[Monomial, Fraction] = {(): Fraction(1)}
        for _ in range(node.exp):
            out = _times(out, a)
            if len(out) > 4 * MAX_MONOMIALS:
                return None
        return out
    return None


def _times(a: dict[Monomial, Fraction], b: dict[Monomial, Fraction]) -> dict[Monomial, Fraction]:
    out: dict[Monomial, Fraction] = {}
    for ma, ca in a.items():
        for mb, cb in b.items():
            powers: dict[str, int] = dict(ma)
            for s, p in mb:
                powers[s] = powers.get(s, 0) + p
            m = tuple(sorted(powers.items()))
            out[m] = out.get(m, Fraction(0)) + ca * cb
    return out


def substitute(node: Node, name: str, value: Node, depth: int = 0) -> Optional[Node]:
    """``node`` with the symbol ``name`` replaced by ``value`` everywhere, the exponents of its powers in symbols included
    (``nodes.replace_symbol`` leaves an unsupported node as it is). None for a node it does not rebuild."""
    if depth > _MAX_DEPTH:
        return None
    rec: Callable[[Node], Optional[Node]] = lambda n: substitute(n, name, value, depth + 1)  # noqa: E731
    e = exponential(node)
    if e is not None:
        x = rec(e.exponent)
        if x is None:
            return None
        if e.base is None:
            return replace(node, arg=x)
        b = rec(e.base)
        return None if b is None else replace(node, arg=x, base=b)
    if isinstance(node, Sym):
        return value if node.name == name and node.kind == "symbol" else node
    if isinstance(node, (Num, Quantity, Unsupported)):
        return node
    if isinstance(node, (Neg, Func, Root)):
        a = rec(node.arg)
        return None if a is None else replace(node, arg=a)
    if isinstance(node, Pow):
        b = rec(node.base)
        return None if b is None else replace(node, base=b)
    if isinstance(node, RealPower):
        b, x = rec(node.base), rec(node.exponent)
        return None if b is None or x is None else replace(node, base=b, exponent=x)
    if isinstance(node, BinOp):
        a, b = rec(node.left), rec(node.right)
        return None if a is None or b is None else replace(node, left=a, right=b)
    return None


def is_model_expression(node: Node) -> bool:
    """A model's expression: at least one power whose exponent holds symbols, and nothing a ``mod`` check cannot read."""
    return has_exponential(node) and _readable(node, 0)


def _readable(node: Node, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        return False
    e = exponential(node)
    if e is not None:
        if exponent_polynomial(e.exponent) is None:
            return False
        if e.base is not None:
            b = exact_value(e.base)
            if b is None or b <= 0:
                return False
        return True
    if isinstance(node, (Num, Sym)):
        return True
    if isinstance(node, _REFUSED) or isinstance(node, Unsupported):
        return False
    if isinstance(node, (RealPower, Func)):
        return all(not (isinstance(n, Sym) and n.kind == "symbol") for n in walk(node)) and not any(isinstance(n, Unsupported) for n in walk(node))
    if isinstance(node, _ALLOWED):
        from .nodes import children
        return all(_readable(c, depth + 1) for c in children(node))
    return False


def application_of(sym: Node, arg: Node, text: str) -> bool:
    """``sym`` (a one-letter symbol) glued to the bracket that holds exactly ``arg`` in ``text``: ``P(t + 4)``, ``P(6)``.
    A space between the letter and the bracket (``P (t + 4)``), or a bracket that holds more than ``arg``, is no
    application: the product the parser reads stands."""
    if not isinstance(sym, Sym) or sym.kind != "symbol" or len(sym.name) != 1 or not text:
        return False
    a, b = sym.end, getattr(arg, "start", -1)
    if not (0 <= a < len(text) and text[a] == "("):
        return False
    if b <= a or text[a + 1:b].strip(" \t"):
        return False
    e = getattr(arg, "end", -1)
    if e < b or e > len(text):
        return False
    rest = text[e:e + 8].lstrip(" \t")
    return rest.startswith(")")


def _rightmost(node: Node) -> tuple[Node, list[BinOp]]:
    """The last factor of a product and the products above it (``2·P`` gives ``P`` and ``[2·P]``)."""
    path: list[BinOp] = []
    cur = node
    while isinstance(cur, BinOp) and cur.op == "*" and len(path) < _MAX_DEPTH:
        path.append(cur)
        cur = cur.right
    return cur, path


def _replace_rightmost(path: list[BinOp], value: Node) -> Node:
    node = value
    for p in reversed(path):
        node = replace(p, right=node)
    return node


def rewrite_applications(node: Node, text: str, expand: Callable[[str, Node], Optional[Node]], depth: int = 0) -> tuple[Optional[Node], int]:
    """``node`` with every application of a model (``expand(name, argument)`` gives the model's expression at the argument,
    or None when ``name`` is no model) replaced by that expression, and how many were replaced. ``(None, 0)`` when an
    application cannot be expanded (its argument holds another application). Only the answer's own nodes are matched
    against ``text``: an expanded expression (whose offsets point into the text that defined the model) is never scanned."""
    if depth > _MAX_DEPTH:
        return None, 0
    if isinstance(node, BinOp) and node.op == "*":
        last, _path = _rightmost(node.left)
        if isinstance(last, Sym) and application_of(last, node.right, text):
            arg, n_arg = rewrite_applications(node.right, text, expand, depth + 1)
            if arg is None or n_arg:
                return None, 0
            value = expand(last.name, arg)
            if value is not None:
                left, n_left = rewrite_applications(node.left, text, expand, depth + 1)
                if left is None:
                    return None, 0
                still, path = _rightmost(left)
                if still is not last:
                    return None, 0
                return (_replace_rightmost(path, value) if path else value), n_left + 1
        left, n_left = rewrite_applications(node.left, text, expand, depth + 1)
        right, n_right = rewrite_applications(node.right, text, expand, depth + 1)
        if left is None or right is None:
            return None, 0
        return (replace(node, left=left, right=right) if (n_left or n_right) else node), n_left + n_right
    if isinstance(node, BinOp):
        left, n_left = rewrite_applications(node.left, text, expand, depth + 1)
        right, n_right = rewrite_applications(node.right, text, expand, depth + 1)
        if left is None or right is None:
            return None, 0
        return (replace(node, left=left, right=right) if (n_left or n_right) else node), n_left + n_right
    if isinstance(node, (Neg, Func, Root)):
        arg, n = rewrite_applications(node.arg, text, expand, depth + 1)
        if arg is None:
            return None, 0
        return (replace(node, arg=arg) if n else node), n
    if isinstance(node, Pow):
        base, n = rewrite_applications(node.base, text, expand, depth + 1)
        if base is None:
            return None, 0
        return (replace(node, base=base) if n else node), n
    return node, 0


def applications(node: Node, text: str, depth: int = 0) -> list[tuple[str, Node]]:
    """Every glued application ``(letter, argument)`` in ``node`` (any one-letter symbol: the caller keeps the models')."""
    out: list[tuple[str, Node]] = []
    if depth > _MAX_DEPTH:
        return out
    if isinstance(node, BinOp) and node.op == "*":
        last, _path = _rightmost(node.left)
        if isinstance(last, Sym) and application_of(last, node.right, text):
            out.append((last.name, node.right))
    if isinstance(node, (BinOp,)):
        out += applications(node.left, text, depth + 1) + applications(node.right, text, depth + 1)
    elif isinstance(node, (Neg, Func, Root)):
        out += applications(node.arg, text, depth + 1)
    elif isinstance(node, Pow):
        out += applications(node.base, text, depth + 1)
    return out


def split_runs(node: Node, letters: set[str]) -> Optional[Node]:
    """``node`` with every symbol written as a run of letters that are each a one-letter symbol of the text (``kt`` with k
    and t in scope) read as the product of those letters, the exponents of its powers included. The front end reads a
    declared run as one name (an answer that writes ``kt = ln 2`` declares ``kt``); a model whose applications put their
    argument in for one of the letters is read with the run as the product it stands for (``P = P₀e^(kt)``, ``P(t + 1)``)."""
    out: Optional[Node] = node
    for n in list(_walk(node)):
        if isinstance(n, Sym) and n.kind == "symbol" and len(n.name) >= 2 and n.name.isascii() and n.name.isalpha() and all(c in letters for c in n.name):
            prod: Node = Sym(n.name[0], start=n.start, end=n.start + 1)
            for i, c in enumerate(n.name[1:], start=1):
                prod = BinOp("*", prod, Sym(c, start=n.start + i, end=n.start + i + 1), n.start, n.end, implicit=True)
            out = substitute(out, n.name, prod) if out is not None else None
    return out


def resolve_model(model: Model, arguments: list[Node], letters: set[str]) -> Optional[tuple[str, Node]]:
    """``(variable, expression)`` of ``model``: the variable it names (``C(t) = …``), else the one symbol of its expression
    that the answer's applications put arguments in for (``P(t + 1)``, ``P(t)`` name t of ``P = P₀e^(kt)``), reading a run of
    one-letter symbols as their product when only that names it (:func:`split_runs`). None when no symbol or several do:
    ``P(6)`` alone could stand for t or for k, and a description such as "Let k be the growth constant" can name a
    parameter as readily as the variable, so neither is read."""
    if model.var:
        return model.var, model.expr
    seen_args: set[str] = set()
    for arg in arguments:
        seen_args |= all_symbols(arg)
    for expr in (model.expr, split_runs(model.expr, letters | {c for c in seen_args if len(c) == 1})):
        if expr is None:
            continue
        found = seen_args & all_symbols(expr)
        if len(found) == 1:
            return next(iter(found)), expr
    return None


def model_link_sides(left: Node, right: Node, text: str, expand: Callable[[str, Node], Optional[Node]]) -> Optional[tuple[Node, Node, int]]:
    """Both sides of an equality with every application of a model expanded, when there is at least one and the link is
    one a ``mod`` check reads (module docstring); None otherwise (the link keeps its old reading)."""
    lr, nl = rewrite_applications(left, text, expand)
    rr, nr = rewrite_applications(right, text, expand)
    if lr is None or rr is None or nl + nr == 0:
        return None
    for side in (lr, rr):
        if not _readable(side, 0) or not exact_numerals(side):
            return None
    if not (has_exponential(lr) or has_exponential(rr)) or not relaxation_fits(lr, rr):
        return None
    return lr, rr, nl + nr


def relaxation_fits(*sides: Node) -> bool:
    """The positive-variable reading of the link (its two sides, or the sides of every reading of it) stays within the
    bounds: at most :data:`MAX_MONOMIALS` variables per base and no power beyond :data:`MAX_POWER` of one of them (so a
    planned check can always be written)."""
    by_base: dict[Optional[Fraction], list[dict[Monomial, Fraction]]] = {}
    for side in sides:
        for n in _walk(side):
            e = exponential(n)
            if e is None:
                continue
            poly = exponent_polynomial(e.exponent)
            base = None if e.base is None else exact_value(e.base)
            if poly is None or (e.base is not None and (base is None or base <= 0)):
                return False
            by_base.setdefault(base, []).append(poly)
    for polys in by_base.values():
        steps = denominators(polys)
        if len(steps) > MAX_MONOMIALS:
            return False
        for p in polys:
            for m, c in p.items():
                if m and abs(c / steps[m]) > MAX_POWER:
                    return False
    return True


def monomial_node(m: Monomial, start: int = 0, end: int = 0) -> Node:
    """A monomial (at least one symbol) as a product of symbols and powers (for descriptions and interval bounds)."""
    if not m:
        raise ValueError("an empty monomial is a constant")
    node: Optional[Node] = None
    for s, p in m:
        f: Node = Sym(s, start=start, end=end)
        if p != 1:
            f = Pow(f, p, start, end)
        node = f if node is None else BinOp("*", node, f, start, end)
    assert node is not None
    return node


def render_model(node: Node, depth: int = 0) -> str:
    """A plain rendering that shows the powers of an exponent in symbols (``P_0·e^(k·(t + 4))``), for descriptions only."""
    from .nodes import render
    if depth > _MAX_DEPTH:
        return "…"
    r = lambda n: render_model(n, depth + 1)  # noqa: E731
    e = exponential(node)
    if e is not None:
        base = "e" if e.base is None else r(e.base)
        if e.base is not None and not isinstance(e.base, (Num, Sym)):
            base = f"({base})"
        return f"{base}^({r(e.exponent)})"
    if isinstance(node, BinOp):
        a, b = r(node.left), r(node.right)
        if node.op in ("*", "/"):
            if isinstance(node.left, BinOp) and node.left.op in ("+", "-"):
                a = f"({a})"
            if isinstance(node.right, BinOp) and (node.right.op in ("+", "-") or node.op == "/"):
                b = f"({b})"
            return f"{a}·{b}" if node.op == "*" else f"{a}/{b}"
        return f"{a} {node.op} {b}"
    if isinstance(node, Neg):
        inner = r(node.arg)
        return f"−({inner})" if isinstance(node.arg, BinOp) else f"−{inner}"
    if isinstance(node, Pow):
        base = r(node.base)
        if not isinstance(node.base, (Num, Sym)):
            base = f"({base})"
        return f"{base}^{node.exp}"
    if isinstance(node, (Num, Sym)) or not any(exponential(n) is not None for n in _walk(node)):
        return render(node)
    return render(node)


def denominators(polys: list[dict[Monomial, Fraction]]) -> dict[Monomial, Fraction]:
    """For each monomial of the exponents of one base, the step ``s`` of its positive variable ``u = B^(s·m)``: the
    greatest common divisor of its coefficients in the link (each coefficient is then an integer multiple of ``s``, and the
    powers of ``u`` are as small as they can be: ``e^(−40k)`` is one variable, not a 40th power)."""
    coeffs: dict[Monomial, list[Fraction]] = {}
    for p in polys:
        for m, c in p.items():
            if m:
                coeffs.setdefault(m, []).append(c)
    out: dict[Monomial, Fraction] = {}
    for m, cs in coeffs.items():
        den = 1
        for c in cs:
            den = lcm(den, c.denominator)
        g = 0
        for c in cs:
            g = gcd(g, abs(int(c * den)))
        out[m] = Fraction(g or 1, den)
    return out
