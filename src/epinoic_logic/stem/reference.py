"""Readers of the closed STEM reference (:mod:`.reference_data`) and of the unit table, for the reference checks
(docs/STEM_DESIGN.md, section 24).

Nothing here evaluates text or decides a stated relation: the readers look entries up, multiply exact unit factors and
add integer dimension exponents. Three readers serve the checks:

* :func:`fixed_quantity` says what a symbol stands for, only when that is fixed: the symbol is unambiguous in the
  profile, or the unit of a result the answer states for it decides it, or the request names the quantity ("Calculate its
  kinetic energy"); and the dimension guard agrees (a result stated for the symbol has the quantity's dimension).
  Otherwise None, so an ambiguous letter (``p``: momentum or pressure) is never judged (a miss, never a false alarm).
* :func:`coefficient_free_dimension` is the dimension of a law's right-hand side with every numeric coefficient dropped,
  whatever its spelling (``½mv``, ``0.5 × m × v``, ``m × v / 2`` all have the dimension of ``mv``).
* :func:`as_written_reading` says whether the as-written reading of a relation (every number taken at face value, units
  unconverted) is admissible beside its SI reading (section 6.4). It is not when the written units contradict it: both
  sides carry units of one dimension whose scale factors differ (``3 × 2.0 kg = 6.0 g``, ``2.5 km / 10 min = 0.25 m s⁻¹``),
  a per cent sign stands on the stated value of a computation that writes no ×100 (``300/400 = 0.75 %``), or a per cent is a
  factor of a product whose stated value carries none (``80 × 25 % = 2000``). The checks stage then decides the relation
  under both readings and, in a companion check, that the as-written reading never holds where the SI reading fails
  (ST-UNIT-003, ``stem_unit_error``).
* :func:`pure_coefficient_dimension` is the dimension of a law's right-hand side when every numeral in it is a pure
  coefficient (a vulgar fraction such as ``½``, or an integer written without a point that no stated quantity has as its
  value): ``½mv`` has the dimension of ``mv``, while ``x = 2.0F`` (a fitted constant, "2.0 cm per newton") or ``F = 50x``
  (``k = 50 N m⁻¹`` substituted) has no dimension the check may judge, since its numeral may carry the missing unit (ST-REF-001).
* :func:`booklet_laws` reads the closed table of data-booklet laws (:data:`.reference_data.BOOKLET_LAWS`) into nodes with the
  STEM front end itself, once per profile, and :func:`differs_as_function` says when an answer's law and a booklet law over the
  same variables are different functions: their rational enclosures (:mod:`.enclosures`) at a fixed sample point are
  disjoint, which proves it. Agreement is never claimed; it only keeps the check silent (ST-REF-002).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Callable, Mapping, Optional

from .constants import match_written
from .enclosures import EnclosureError, Interval, enclose, isqrt_interval
from .nodes import Abs, BinOp, Degrees, Func, Magnification, Neg, Node, Num, Percent, PlusMinus, Pow, Quantity, Root, Sym, WithUnit, symbols, walk
from .reference_data import BOOKLET_LAWS, FORMULAS, QUANTITIES, RefFormula, RefQuantity
from .units import DIMENSIONLESS, Dimension, UnitExpr

__all__ = ["quantities_for", "fixed_quantity", "booklet_formulas", "formula_dimension", "coefficient_free_dimension", "written_scale",
           "as_written_reading", "unit_written_once", "unit_scale", "dimension_text", "pure_coefficient_dimension", "BookletLaw", "booklet_laws", "enclose_node",
           "differs_as_function"]

SymbolDim = Callable[[str], Optional[Dimension]]
SymbolScale = Callable[[str], Optional[Fraction]]


def quantities_for(symbol: str, profile_key: str) -> tuple[RefQuantity, ...]:
    """The reference rows of ``symbol`` in the profile (empty when the table has none)."""
    return tuple(q for q in QUANTITIES if q.symbol == symbol and profile_key in q.profiles)


def _names_quantity(request_text: str, q: RefQuantity) -> bool:
    """The request names the quantity (whole words, case-insensitive): "Calculate its kinetic energy"."""
    low = " " + " ".join("".join(c if c.isalnum() else " " for c in request_text[:4000].lower()).split()) + " "
    return any((" " + " ".join(n.lower().replace(".", " ").split()) + " ") in low for n in q.names)


def fixed_quantity(symbol: str, profile_key: str, *, result_dims: tuple[Dimension, ...] = (), request_text: str = "") -> Optional[RefQuantity]:
    """The reference quantity ``symbol`` stands for, when it is fixed (module docstring), else None. ``result_dims`` are the
    dimensions of the results the answer states for the symbol (their units); every one must agree with the quantity."""
    rows = quantities_for(symbol, profile_key)
    if not rows:
        return None
    keys = {q.key for q in rows}
    pick: Optional[RefQuantity] = None
    if len(keys) == 1 and not rows[0].ambiguous_with:
        pick = rows[0]
    if pick is None and result_dims:
        fits = {q.key: q for q in rows if all(d.same_physical(q.dimension) for d in result_dims)}
        if len(fits) == 1:
            pick = next(iter(fits.values()))
    if pick is None and request_text:
        named = {q.key: q for q in rows if _names_quantity(request_text, q)}
        if len(named) == 1:
            pick = next(iter(named.values()))
    if pick is None:
        return None
    if any(not d.same_physical(pick.dimension) for d in result_dims):
        return None  # the dimension guard: a result stated for the symbol has another dimension, so its identity is in doubt
    return pick


def booklet_formulas(quantity_key: str, profile_key: str) -> tuple[RefFormula, ...]:
    """The data-booklet formulas of a quantity in the profile."""
    return tuple(f for f in FORMULAS if f.quantity == quantity_key and profile_key in f.profiles)


def formula_dimension(f: RefFormula, profile_key: str) -> Optional[Dimension]:
    """The dimension of a booklet formula's right-hand side (from its terms' reference quantities); None when a term has
    no single reference quantity in the profile."""
    dim = DIMENSIONLESS
    for sym, power in f.terms:
        dims = {q.dimension for q in quantities_for(sym, profile_key)}
        if len(dims) != 1:
            return None
        dim = dim * next(iter(dims)).power(power)
    return dim


def coefficient_free_dimension(node: Node, symbol_dim: SymbolDim, depth: int = 0, *,
                               num_dim: Optional[Callable[[Num], Optional[Dimension]]] = None) -> Optional[Dimension]:
    """The dimension of an expression with every numeric coefficient dimensionless, whatever its spelling (``½``, ``0.5``,
    ``1/2``, ``2``), constants (π, e) dimensionless, a symbol's from ``symbol_dim``; None when a part is unknown or a sum
    adds terms of two dimensions. ``num_dim`` gives a numeral another dimension (a bare number read in a binding's unit)."""
    if depth > 64:
        return None
    rec = lambda n: coefficient_free_dimension(n, symbol_dim, depth + 1, num_dim=num_dim)  # noqa: E731
    if isinstance(node, Num):
        return DIMENSIONLESS if num_dim is None else num_dim(node)
    if isinstance(node, Quantity):
        return None if node.unit.unknown else node.unit.dim
    if isinstance(node, WithUnit):
        inner = rec(node.arg)
        return None if inner is None or node.unit.unknown or node.unit.dim is None else inner * node.unit.dim
    if isinstance(node, Sym):
        return DIMENSIONLESS if node.kind == "constant" else symbol_dim(node.name)
    if isinstance(node, (Neg, Abs, Magnification)):
        return rec(node.arg)
    if isinstance(node, Percent):
        return DIMENSIONLESS
    if isinstance(node, PlusMinus):
        if node.left is None:
            return rec(node.right)
        a, b = rec(node.left), rec(node.right)
        return a if a is not None and b is not None and a.same_physical(b) else None
    if isinstance(node, BinOp):
        a, b = rec(node.left), rec(node.right)
        if a is None or b is None:
            return None
        if node.op in "+-":
            return a if a.same_physical(b) else None
        return a * b if node.op == "*" else a / b
    if isinstance(node, Pow):
        a = rec(node.base)
        return None if a is None else a.power(node.exp)
    if isinstance(node, Root):
        a = rec(node.arg)
        if a is None or any(e % 2 for e in a.exps) or a.angle % 2:
            return None
        return Dimension(tuple(e // 2 for e in a.exps), a.angle // 2)  # type: ignore[arg-type]
    if isinstance(node, Func):
        return DIMENSIONLESS if rec(node.arg) is not None else None
    if isinstance(node, Degrees):
        return Dimension((0, 0, 0, 0, 0, 0, 0), 1)
    return None


def pure_coefficient_dimension(node: Node, symbol_dim: SymbolDim, *, stated_values: frozenset[Fraction] = frozenset(),
                               depth: int = 0) -> Optional[Dimension]:
    """The dimension of a law's right-hand side when every numeral in it is a pure coefficient (module docstring): a vulgar
    fraction, or an integer written without a point, in no scientific form, whose value is not among ``stated_values`` (the
    values of the quantities the answer and the request state with a unit). None when a numeral may be a constant with a
    unit of its own (``2.0`` in ``x = 2.0F``, ``50`` in ``F = 50x`` after ``k = 50 N m⁻¹``), a part is unknown, or a sum adds
    terms of two dimensions: then nothing about the law's dimension can be concluded (a miss, never a false alarm)."""
    for n in walk(node):
        if isinstance(n, Num):
            num = n.number
            if num.vulgar:
                continue
            if num.has_point or num.scientific or num.based or num.base != 10 or num.value.denominator != 1 or num.value in stated_values:
                return None
    return coefficient_free_dimension(node, symbol_dim, depth)


# ----------------------------------------------------------------------------------------------- the booklet laws (ST-REF-002)
@dataclass(frozen=True)
class BookletLaw:
    """A data-booklet law read into nodes: ``lhs = rhs`` for the quantity ``quantity``, over ``variables`` (the symbols of
    ``rhs`` that are no constants); ``text`` is how the table writes it."""

    quantity: str
    lhs: str
    rhs: Node
    variables: frozenset[str]
    text: str


@lru_cache(maxsize=32)
def booklet_laws(profile_key: str) -> tuple[BookletLaw, ...]:
    """The booklet laws of the profile, read by the STEM front end from the closed table, once per profile (outside the
    document cache, and with the reference checks off: a law read here runs no reference check of its own, which would read
    the table again). A law whose reading is not one formula with a lone symbol on its left is left out."""
    from .document import _build  # the front end reads its own closed table; imported here (it imports this module)
    from .limits import DEFAULT_LIMITS, profile_for

    out: list[BookletLaw] = []
    docs = []
    for profiles, quantity, text in BOOKLET_LAWS:
        if profile_key not in profiles:
            continue
        try:
            docs.append((quantity, text, _build(text, "", profile_for(profile_key), DEFAULT_LIMITS, reference_checks=False)))
        except Exception:  # a table row the reader cannot read is left out (never a finding)
            continue
    for quantity, text, doc in docs:
        rels = [r for r in doc.relations if r.kind == "formula" and r.left is not None and r.right is not None]
        if len(rels) != 1 or len(rels[0].left.readings) != 1 or len(rels[0].right.readings) != 1:
            continue
        lhs, rhs = rels[0].left.readings[0], rels[0].right.readings[0]
        if not isinstance(lhs, Sym) or lhs.kind != "symbol":
            continue
        out.append(BookletLaw(quantity, lhs.name, rhs, frozenset(symbols(rhs)), text))
    return tuple(out)


#: the sample values of a law's variables (distinct, positive, away from the poles of the booklet laws: no 1, no 0)
_SAMPLES = (Fraction(7, 3), Fraction(11, 5), Fraction(13, 4), Fraction(17, 6), Fraction(19, 7), Fraction(23, 9), Fraction(29, 8), Fraction(31, 12),
            Fraction(37, 10), Fraction(41, 15), Fraction(43, 14), Fraction(47, 18))


def enclose_node(node: Node, env: Mapping[str, Fraction], depth: int = 0, *, decimal_widths: bool = False) -> Optional[Interval]:
    """A rational enclosure of ``node`` with every symbol at its value in ``env`` (π and e by their enclosures, the functions
    by :func:`.enclosures.enclose`); None for a node outside this reading (a unit, a per cent, ±, an unsupported construct), a
    symbol with no value, or a value outside a function's domain. Nothing is evaluated from text: the nodes were read by
    the front end, and the arithmetic is exact rational interval arithmetic rounded outward."""
    if depth > 64:
        return None
    rec = lambda n: enclose_node(n, env, depth + 1, decimal_widths=decimal_widths)  # noqa: E731
    try:
        if isinstance(node, Num):
            num = node.number
            if decimal_widths and (num.has_point or num.scientific) and not num.vulgar:
                h = num.half_width  # a decimal as written stands for its rounding interval; an integer is exact
                return Interval(num.value - h, num.value + h)
            return Interval.point(num.value)
        if isinstance(node, Sym):
            if node.kind == "constant":
                return enclose("pi") if node.name in ("π", "pi") else enclose("e") if node.name == "e" else None
            v = env.get(node.name)
            return None if v is None else Interval.point(v)
        if isinstance(node, Neg):
            a = rec(node.arg)
            return None if a is None else -a
        if isinstance(node, Abs):
            a = rec(node.arg)
            return None if a is None else a.abs()
        if isinstance(node, BinOp):
            a, b = rec(node.left), rec(node.right)
            if a is None or b is None:
                return None
            if node.op == "+":
                return a + b
            if node.op == "-":
                return a - b
            if node.op == "*":
                return a * b
            return a / b
        if isinstance(node, Pow):
            a = rec(node.base)
            return None if a is None else a.power(node.exp)
        if isinstance(node, Root):
            a = rec(node.arg)
            return None if a is None or a.lo < 0 else isqrt_interval(a)
        if isinstance(node, Func):
            a = rec(node.arg)
            return None if a is None else enclose(node.name, a, base=node.base)
    except (EnclosureError, ZeroDivisionError, ValueError, OverflowError):
        return None
    return None


def difference_witness(a: Node, b: Node, variables: frozenset[str]) -> Optional[dict[str, Fraction]]:
    """The sample point at which the expressions ``a`` and ``b`` over ``variables`` are proven to differ (their rational
    enclosures are disjoint there), trying two fixed points; None when they overlap at both, or when either cannot be
    enclosed (agreement is not proven by this; it only keeps the caller silent)."""
    names = sorted(variables)
    if len(names) > len(_SAMPLES):
        return None
    for shift in (0, 5):
        env = {n: _SAMPLES[(k + shift) % len(_SAMPLES)] for k, n in enumerate(names)}
        ia, ib = enclose_node(a, env), enclose_node(b, env)
        if ia is None or ib is None:
            return None
        if ia.hi < ib.lo or ib.hi < ia.lo:
            return env
    return None


def differs_as_function(a: Node, b: Node, variables: frozenset[str]) -> bool:
    """True when the expressions ``a`` and ``b`` over ``variables`` are proven to be different functions
    (:func:`difference_witness`)."""
    return difference_witness(a, b, variables) is not None


def unit_scale(unit: Optional[UnitExpr]) -> Optional[Fraction]:
    """The exact SI factor of a unit with one reading (1 for no unit); None for an ambiguous, unknown, inexact or offset unit."""
    if unit is None:
        return Fraction(1)
    if unit.unknown or len(unit.readings) != 1:
        return None
    r = unit.readings[0]
    if r.factor is None or r.affine is not None:
        return None
    return r.factor


def written_scale(node: Node, symbol_scale: SymbolScale, depth: int = 0) -> Optional[Fraction]:
    """The factor by which the SI reading of ``node`` exceeds its as-written reading, when one factor applies to the whole
    expression: a bare numeral 1, a quantity its unit's factor, a per cent 1/100, a symbol its bindings' (``symbol_scale``),
    a product or quotient the product or quotient of its factors, a sum the factor its terms share. None when no single
    factor applies (terms in different units, an angle, an offset temperature, an inexact or unknown unit)."""
    if depth > 64:
        return None
    rec = lambda n: written_scale(n, symbol_scale, depth + 1)  # noqa: E731
    if isinstance(node, Num):
        return Fraction(1)
    if isinstance(node, Quantity):
        return unit_scale(node.unit)
    if isinstance(node, WithUnit):
        a, u = rec(node.arg), unit_scale(node.unit)
        return None if a is None or u is None else a * u
    if isinstance(node, Percent):
        a = rec(node.arg)
        return None if a is None else a / 100
    if isinstance(node, Sym):
        return Fraction(1) if node.kind == "constant" else symbol_scale(node.name)
    if isinstance(node, (Neg, Abs, Magnification)):
        return rec(node.arg)
    if isinstance(node, PlusMinus):
        if node.left is None:
            return rec(node.right)
        a, b = rec(node.left), rec(node.right)
        return a if a is not None and a == b else None
    if isinstance(node, BinOp):
        a, b = rec(node.left), rec(node.right)
        if a is None or b is None:
            return None
        if node.op in "+-":
            return a if a == b else None
        if node.op == "*":
            return a * b
        return a / b if b != 0 else None
    if isinstance(node, Pow):
        a = rec(node.base)
        if a is None or a == 0:
            return None
        return a ** node.exp
    if isinstance(node, (Root, Func)):
        return Fraction(1) if rec(node.arg) == 1 else None
    return None


def _carries_unit(node: Node, symbol_scale: SymbolScale) -> bool:
    """A unit is written on the expression: a quantity, a unit after a group, or a symbol bound with a unit."""
    for n in walk(node):
        if isinstance(n, (Quantity, WithUnit)):
            return True
        if isinstance(n, Sym) and n.kind != "constant":
            s = symbol_scale(n.name)
            if s is None or s != 1:
                return True
    return False


def _stated_unit(node: Node) -> bool:
    cur = node
    while isinstance(cur, Neg):
        cur = cur.arg
    return isinstance(cur, (Quantity, WithUnit))


def _is_percent_value(node: Node) -> bool:
    cur = node
    while isinstance(cur, Neg):
        cur = cur.arg
    return isinstance(cur, Percent)


def _percent_factor(node: Node) -> bool:
    """A per cent is a factor of a product or quotient (``80 × 25 %``): the product is a plain number."""
    for n in walk(node):
        if isinstance(n, BinOp) and n.op in "*/":
            for side in (n.left, n.right):
                cur = side
                while isinstance(cur, Neg):
                    cur = cur.arg
                if isinstance(cur, Percent):
                    return True
    return False


def _times_hundred(node: Node) -> bool:
    """The computation multiplies by 100 at its top level (``(421 − 280) ÷ 280 × 100``, ``0.75 × 100``): the per cent the
    stated value carries is that conversion, so the as-written reading is the per cent number."""
    stack = [node]
    seen = 0
    while stack and seen < 64:
        seen += 1
        cur = stack.pop()
        if isinstance(cur, Neg):
            stack.append(cur.arg)
        elif isinstance(cur, BinOp) and cur.op == "*":
            stack.extend((cur.left, cur.right))
        elif isinstance(cur, BinOp) and cur.op == "/":
            stack.append(cur.left)
        elif isinstance(cur, Num) and cur.number.value == 100:
            return True
    return False


def _bare_factors(node: Node) -> set[Fraction]:
    """The bare numerals that multiply (or divide: their reciprocals) the computation at its top level, and their product:
    the candidates for a conversion factor written by hand (``× 3.6``, ``÷ 1000``, ``× 1000 / 60``)."""
    out: set[Fraction] = set()
    total = Fraction(1)
    stack: list[tuple[Node, bool]] = [(node, False)]
    seen = 0
    while stack and seen < 64:
        seen += 1
        cur, inverted = stack.pop()
        if isinstance(cur, Neg):
            stack.append((cur.arg, inverted))
        elif isinstance(cur, BinOp) and cur.op == "*":
            stack.extend(((cur.left, inverted), (cur.right, inverted)))
        elif isinstance(cur, BinOp) and cur.op == "/":
            stack.extend(((cur.left, inverted), (cur.right, not inverted)))
        elif isinstance(cur, Num) and cur.number.value != 0 and not cur.number.vulgar:
            v = 1 / cur.number.value if inverted else cur.number.value
            out.add(v)
            total *= v
    if len(out) > 1:
        out.add(total)
    return out


def _pure_dimension(node: Node, symbol_dim: SymbolDim, profile_key: str) -> Optional[Dimension]:
    """The dimension of a written expression with a bare numeral read as a pure number, unless it is a written
    data-booklet constant (``9.81`` is g): then it has the constant's dimension. None when a part is unknown."""
    def num_dim(n: Num) -> Dimension:
        num = n.number
        if num.vulgar or num.based or num.base != 10 or num.value == 0:
            return DIMENSIONLESS
        m = match_written(num.value, num.half_width, num.sig_figs, None, unit_given=False, profile_key=profile_key)
        return m.constant.dim if m is not None else DIMENSIONLESS

    def rec(n: Node, depth: int) -> Optional[Dimension]:
        if depth > 64:
            return None
        if isinstance(n, Num):
            return num_dim(n)
        if isinstance(n, BinOp) and n.op in "*/":
            a, b = rec(n.left, depth + 1), rec(n.right, depth + 1)
            if a is None or b is None:
                return None
            return a * b if n.op == "*" else a / b
        if isinstance(n, BinOp) and n.op in "+-":
            a, b = rec(n.left, depth + 1), rec(n.right, depth + 1)
            return a if a is not None and b is not None and a.same_physical(b) else None
        if isinstance(n, (Neg, Abs)):
            return rec(n.arg, depth + 1)
        if isinstance(n, Pow):
            a = rec(n.base, depth + 1)
            return None if a is None else a.power(n.exp)
        return coefficient_free_dimension(n, symbol_dim, depth + 1)

    return rec(node, 0)


def as_written_reading(computed: Node, stated: Node, *, symbol_scale: SymbolScale, symbol_dim: SymbolDim, profile_key: str) -> tuple[bool, str]:
    """``(admissible, reason)``: whether the as-written reading of ``computed = stated`` is admissible beside its SI reading
    (module docstring). ``reason`` says why it is not; it is empty when the reading is admissible, including when the two
    readings coincide."""
    fc, fs = written_scale(computed, symbol_scale), written_scale(stated, symbol_scale)
    if fc is not None and fs is not None and fc == fs:
        return True, ""
    if _is_percent_value(stated) and not any(isinstance(n, Percent) for n in walk(computed)) and not _times_hundred(computed):
        return False, ("a per cent sign on the stated value converts it (× 1/100), and the computation writes no × 100, so the stated per cent "
                       "number cannot be read as written")
    if _percent_factor(computed) and not any(isinstance(n, Percent) for n in walk(stated)):
        return False, "a per cent is a factor of the product, which is therefore a plain number, and the stated value carries no per cent"
    if fc is None or fs is None or not _stated_unit(stated) or not _carries_unit(computed, symbol_scale):
        return True, ""
    if fs != 0 and fc / fs in _bare_factors(computed):
        return True, ""  # a conversion by hand: the bare factor is exactly the ratio of the units (5.03 m s⁻¹ × 3.6 = 18.1 km h⁻¹)
    dc, ds = _pure_dimension(computed, symbol_dim, profile_key), _pure_dimension(stated, symbol_dim, profile_key)
    if dc is None or ds is None or not dc.same_physical(ds):
        return True, ""  # a bare number may carry a unit of its own (0.100 mol dm⁻³ × 0.0250, the volume in dm³)
    return False, (f"both sides carry units of one dimension ({dimension_text(dc)}) whose scale factors differ ({_ratio(fc)} against {_ratio(fs)}), "
                   f"so the written numbers cannot be compared without converting them")


def unit_written_once(before: Node, rounded: Node) -> Optional[Node]:
    """The value before a rounding read in the unit the rounded value writes, when a chain writes its unit (or its per cent
    sign) once, after the rounded value (``= 52.4 ≈ 52%``, ``= 24.447 ≈ 24.45 cm³``): ``before`` is a bare numeral as close
    to the rounded value as written (within a tenth of it), and ``rounded`` a quantity or a per cent of one numeral. A
    rounding never converts a unit, so the bare value is in that unit too. None otherwise: a bare value of another scale
    (``= 0.7896 ≈ 79%``, a conversion in the rounding step) keeps its own reading (repair round 2 for the rounding check;
    repair round 3, ADV3-03, for the unit companion of the rounding link)."""
    if not isinstance(before, Num):
        return None
    if isinstance(rounded, Quantity):
        written = rounded.number.value
    elif isinstance(rounded, Percent) and isinstance(rounded.arg, Num):
        written = rounded.arg.number.value
    else:
        return None
    if abs(before.number.value - written) > abs(written) / 10:
        return None
    return Quantity(before.number, rounded.unit, before.start, before.end) if isinstance(rounded, Quantity) else Percent(before, before.start, before.end)


def _ratio(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def dimension_text(dim: Dimension) -> str:
    from .units import dimension_name
    name = dimension_name(dim)
    return name if name == str(dim) else f"{name}, {dim}"
