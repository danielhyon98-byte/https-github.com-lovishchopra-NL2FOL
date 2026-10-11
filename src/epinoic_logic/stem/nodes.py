"""Frozen AST nodes of the STEM front end and the helpers every later stage reads them with.

The parser (``parser.py``) builds only these node types; ``to_ir`` (stage ``checks``)
translates only these node types into allowlisted IR 1.0 nodes. Every node carries the
offsets ``start``/``end`` of the text it was read from (offsets of the original text,
because every view is a 1:1 map).

Node types:

``Num``            a numeral (:class:`~epinoic_logic.stem.numbers.ExactNumber`)
``Quantity``       a numeral with a unit (:class:`~epinoic_logic.stem.units.UnitExpr`)
``WithUnit``       a unit after a closing group that contains a number (``(40 − 20) K``)
``Sym``            a symbol; ``kind`` is ``symbol``, ``word`` (a word written as a symbol), ``constant`` (π), ``label`` (a prose name
                   before a relation sign: "Energy absorbed"), ``chem`` (``n(H₂O)``,
                   ``[H⁺]``), ``bond`` (``O=O``)
``Neg``            unary minus
``BinOp``          ``+ - * /`` (``written`` keeps the sign as written, ``implicit`` marks
                   juxtaposition)
``PlusMinus``      ``±``/``∓`` inside a formula (binary, or unary when ``left`` is None)
``Pow``            an integer power ``|n| <= max_int_power``
``Root``           a square root (``√x``, ``\\sqrt{x}``, ``x^½``)
``Func``           sin cos tan arcsin arccos arctan ln log (with ``base``) log10 exp
``Apply``          ``f(x)``: a named function applied to an argument
``Abs``            ``|x|``
``Percent``        ``n %``
``Degrees``        an angle written with ``°``
``Magnification``  ``50×``
``Ratio``          ``a : b``
``BoolOp``         ``and or xor not`` (Computer Science)
``Unsupported``    a construct outside the encodings, with the reason (calculus, Σ, ``!``,
                   a fractional or symbolic power, a vector, a complex number, ...)

``Chain`` is ``L0 op1 E1 … opk Ek`` (relation signs between operands), and an
``Operand`` holds the one or two readings of one operand (implicit multiplication
resolved two ways). Helpers: :func:`walk`, :func:`symbols`, :func:`node_count`,
:func:`depth`, :func:`is_closed`, :func:`unsupported_reasons`, :func:`shape_key`,
:func:`align`, :func:`render`, :func:`is_value`, :func:`value_of`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterator, Optional, Union

from .numbers import ExactNumber
from .units import UnitExpr

__all__ = [
    "Abs", "Apply", "BinOp", "BoolOp", "Chain", "Degrees", "Func", "Magnification", "Neg", "Node", "Num", "Operand", "Percent", "PlusMinus",
    "Pow", "Quantity", "Ratio", "Root", "Sym", "Unsupported", "WithUnit", "align", "children", "depth", "is_closed", "is_value", "node_count", "render",
    "shape_key", "symbols", "unsupported_reasons", "value_of", "walk",
]


@dataclass(frozen=True)
class Num:
    number: ExactNumber
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Quantity:
    number: ExactNumber
    unit: UnitExpr
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class WithUnit:
    """A unit written after a closing group that contains a number: ``(40 − 20) K``."""

    arg: "Node"
    unit: UnitExpr
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Sym:
    name: str
    kind: str = "symbol"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Neg:
    arg: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class BinOp:
    op: str  # '+', '-', '*', '/'
    left: "Node"
    right: "Node"
    start: int = 0
    end: int = 0
    written: str = ""
    implicit: bool = False


@dataclass(frozen=True)
class PlusMinus:
    sign: str  # '±' or '∓'
    left: Optional["Node"]
    right: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Pow:
    base: "Node"
    exp: int
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Root:
    arg: "Node"
    index: int = 2
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Func:
    name: str
    arg: "Node"
    base: Optional[int] = None
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Apply:
    name: str
    arg: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Abs:
    arg: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Percent:
    arg: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Degrees:
    arg: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Magnification:
    arg: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Ratio:
    left: "Node"
    right: "Node"
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class BoolOp:
    op: str  # 'and', 'or', 'xor', 'not'
    args: tuple["Node", ...]
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Unsupported:
    reason: str
    text: str = ""
    start: int = 0
    end: int = 0


Node = Union[Num, Quantity, WithUnit, Sym, Neg, BinOp, PlusMinus, Pow, Root, Func, Apply, Abs, Percent, Degrees, Magnification, Ratio, BoolOp, Unsupported]


@dataclass(frozen=True)
class Operand:
    """One operand of a chain with its readings (one, or two when implicit multiplication or
    a letter run could be read two ways). ``error`` is set when the operand could not be read
    (ST-PARSE-001 / ST-PARSE-002 / ST-LIM-001; ``code`` names which)."""

    readings: tuple[Node, ...]
    start: int
    end: int
    error: str = ""
    code: str = ""

    @property
    def node(self) -> Optional[Node]:
        return self.readings[0] if self.readings else None


@dataclass(frozen=True)
class Chain:
    """``operands[0] ops[0] operands[1] … ops[k-1] operands[k]``. ``lead`` is set when the chain
    opened with a relation sign: a continuation line (``= (2.35 − 2.50)/2.50 × 100``) whose
    first operand lives on an earlier line (``operands[0]`` is then a placeholder ``Sym`` of kind
    ``continuation``), or a prose label (``Energy absorbed = …``, a ``Sym`` of kind ``label``).
    ``connective`` is what joined this chain to the previous one in its span (``⇒``, ``∴``,
    ``or``, ``and``, ``,``, ``so``, ...), empty for the first."""

    operands: tuple[Operand, ...]
    ops: tuple[str, ...]
    start: int
    end: int
    lead: str = ""
    connective: str = ""
    truncated: bool = False

    @property
    def links(self) -> int:
        return len(self.ops)


def children(node: Node) -> tuple[Node, ...]:
    if isinstance(node, (Neg, Pow, Root, Func, Apply, Abs, Percent, Degrees, Magnification, WithUnit)):
        return (node.arg if not isinstance(node, Pow) else node.base,)
    if isinstance(node, (BinOp, Ratio)):
        return (node.left, node.right)
    if isinstance(node, PlusMinus):
        return (node.right,) if node.left is None else (node.left, node.right)
    if isinstance(node, BoolOp):
        return node.args
    return ()


def walk(node: Node) -> Iterator[Node]:
    """Every node of the tree, pre-order (iterative: no recursion limit)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        stack.extend(reversed(children(cur)))


def node_count(node: Node) -> int:
    return sum(1 for _ in walk(node))


def depth(node: Node, *, flatten: bool = True) -> int:
    """Depth of the tree. With ``flatten`` (the default) a run of the same ``+`` or ``*`` counts
    as one level, as the IR encoding flattens it into one n-ary node, so a long sum is not deep."""
    best = 0
    stack = [(node, 1, "")]
    while stack:
        cur, d, parent_op = stack.pop()
        here = d
        if flatten and isinstance(cur, BinOp) and cur.op in "+*" and cur.op == parent_op:
            here = d - 1
        best = max(best, here)
        op = cur.op if isinstance(cur, BinOp) else ""
        for c in children(cur):
            stack.append((c, here + 1, op))
    return best


def symbols(node: Node) -> tuple[str, ...]:
    """Names of the symbols of ``node`` (kind ``symbol``, ``chem``, ``bond``, ``label``), in order, without repeats.
    Constants (π, e) are not symbols."""
    seen: dict[str, None] = {}
    for n in walk(node):
        if isinstance(n, Sym) and n.kind != "constant":
            seen.setdefault(n.name, None)
        elif isinstance(n, Apply):
            seen.setdefault(n.name + "()", None)
    return tuple(seen)


def is_closed(node: Node) -> bool:
    """True when the node contains no symbol (constants π and e allowed) and nothing unsupported."""
    for n in walk(node):
        if isinstance(n, (Sym, Apply)) and not (isinstance(n, Sym) and n.kind == "constant"):
            return False
        if isinstance(n, Unsupported):
            return False
    return True


def unsupported_reasons(node: Node) -> tuple[str, ...]:
    out: dict[str, None] = {}
    for n in walk(node):
        if isinstance(n, Unsupported):
            out.setdefault(n.reason, None)
    return tuple(out)


def is_value(node: Node) -> bool:
    """A single number or quantity, possibly signed, a per cent, an angle in degrees or a magnification."""
    cur = node
    while isinstance(cur, (Neg, Percent, Degrees, Magnification)):
        cur = cur.arg
    return isinstance(cur, (Num, Quantity))


def value_of(node: Node) -> Optional[tuple[Fraction, Optional[ExactNumber], Optional[UnitExpr], str]]:
    """``(value as written, the numeral, its unit, wrapper)`` for a value node (:func:`is_value`),
    with the sign applied; ``wrapper`` is ``%``, ``°``, ``×`` or empty. None otherwise."""
    sign = 1
    wrapper = ""
    cur = node
    while isinstance(cur, (Neg, Percent, Degrees, Magnification)):
        if isinstance(cur, Neg):
            sign = -sign
        elif isinstance(cur, Percent):
            wrapper = "%"
        elif isinstance(cur, Degrees):
            wrapper = "°"
        else:
            wrapper = "×"
        cur = cur.arg
    if isinstance(cur, Num):
        return sign * cur.number.value, cur.number, None, wrapper
    if isinstance(cur, Quantity):
        return sign * cur.number.value, cur.number, cur.unit, wrapper
    return None


def _flatten(node: Node, op: str) -> list[Node]:
    out: list[Node] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, BinOp) and cur.op == op:
            stack.append(cur.right)
            stack.append(cur.left)
        else:
            out.append(cur)
    return out


def shape_key(node: Node) -> str:
    """A structural key that ignores offsets, how a sign was written and grouping: two trees
    with equal keys say the same thing in the same order (used to compare readings)."""
    return render(node, canonical=True)


def align(symbolic: Node, numeric: Node) -> Optional[list[tuple[Node, Node]]]:
    """Pair the leaves of ``symbolic`` with the subtrees of ``numeric`` when both trees have the
    same shape apart from substituted leaves: a symbol on the left may stand opposite any subtree
    on the right (``(v − u)/t`` against ``(20 − 0)/4.0`` pairs v–20, u–0, t–4.0); numbers must
    match numbers of equal value. Products and sums are compared as flattened, ordered lists
    (``mcΔT`` against ``0.50 × 4200 × 20``). Returns the pairs, or None when the shapes differ."""
    pairs: list[tuple[Node, Node]] = []
    stack: list[tuple[Node, Node]] = [(symbolic, numeric)]
    steps = 0
    while stack:
        steps += 1
        if steps > 4096:
            return None
        a, b = stack.pop()
        if isinstance(a, Sym) and a.kind != "constant":
            pairs.append((a, b))
            continue
        if isinstance(a, Apply):
            pairs.append((a, b))
            continue
        if isinstance(a, (Num, Quantity)):
            vb = value_of(b)
            if vb is None or vb[0] != a.number.value:
                return None
            continue
        if isinstance(a, Sym):  # a constant must stay a constant
            if not (isinstance(b, Sym) and b.name == a.name):
                return None
            continue
        if isinstance(a, BinOp) and a.op in "+*":
            if not (isinstance(b, BinOp) and b.op == a.op):
                return None
            la, lb = _flatten(a, a.op), _flatten(b, b.op)
            if len(la) != len(lb):
                return None
            stack.extend(zip(reversed(la), reversed(lb)))
            continue
        if type(a) is not type(b):
            return None
        if isinstance(a, BinOp):
            if a.op != b.op:  # type: ignore[union-attr]
                return None
            stack.append((a.right, b.right))  # type: ignore[union-attr]
            stack.append((a.left, b.left))  # type: ignore[union-attr]
            continue
        if isinstance(a, Pow):
            if a.exp != b.exp:  # type: ignore[union-attr]
                return None
            stack.append((a.base, b.base))  # type: ignore[union-attr]
            continue
        if isinstance(a, Func):
            if a.name != b.name or a.base != b.base:  # type: ignore[union-attr]
                return None
            stack.append((a.arg, b.arg))  # type: ignore[union-attr]
            continue
        if isinstance(a, PlusMinus):
            if a.sign != b.sign or (a.left is None) != (b.left is None):  # type: ignore[union-attr]
                return None
            if a.left is not None:
                stack.append((a.left, b.left))  # type: ignore[union-attr,arg-type]
            stack.append((a.right, b.right))  # type: ignore[union-attr]
            continue
        ca, cb = children(a), children(b)
        if len(ca) != len(cb) or isinstance(a, Unsupported):
            return None
        stack.extend(zip(reversed(ca), reversed(cb)))
    return pairs


_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}


def render(node: Node, canonical: bool = False) -> str:
    """A plain-text rendering (``(20 - 0)/4.0``). With ``canonical`` the rendering ignores how
    signs were written and is used as a structural key. Iterative over a bounded tree."""
    return _render(node, canonical, 0)


def _num_text(num: ExactNumber, canonical: bool) -> str:
    if canonical:
        v = num.value
        return f"{v.numerator}/{v.denominator}" if v.denominator != 1 else str(v.numerator)
    return " ".join(num.text.split())


def _render(node: Node, canonical: bool, level: int) -> str:
    if level > 64:
        return "…"
    r = lambda n, lv=level + 1: _render(n, canonical, lv)  # noqa: E731
    if isinstance(node, Num):
        return _num_text(node.number, canonical)
    if isinstance(node, Quantity):
        return f"{_num_text(node.number, canonical)} [{node.unit.text}]"
    if isinstance(node, WithUnit):
        return f"({r(node.arg)}) [{node.unit.text}]"
    if isinstance(node, Sym):
        return node.name
    if isinstance(node, Neg):
        inner = r(node.arg)
        return f"-({inner})" if isinstance(node.arg, (BinOp, PlusMinus)) else f"-{inner}"
    if isinstance(node, BinOp):
        sym = node.op if canonical or not node.written else node.written
        if not canonical and node.implicit:
            sym = "·"
        left, right = r(node.left), r(node.right)
        p = _PREC[node.op]
        if (isinstance(node.left, BinOp) and _PREC[node.left.op] < p) or (isinstance(node.left, PlusMinus) and node.left.left is not None and p == 2):
            left = f"({left})"
        if isinstance(node.right, BinOp) and (_PREC[node.right.op] < p or (_PREC[node.right.op] == p and node.op in "-/")):
            right = f"({right})"
        if isinstance(node.right, (Neg, PlusMinus)):
            right = f"({right})"
        return f"{left} {sym} {right}" if canonical or not node.implicit else f"{left}·{right}"
    if isinstance(node, PlusMinus):
        if node.left is None:
            return f"{node.sign}{r(node.right)}"
        return f"{r(node.left)} {node.sign} {r(node.right)}"
    if isinstance(node, Pow):
        base = r(node.base)
        if not isinstance(node.base, (Num, Sym)) or (isinstance(node.base, Num) and (node.base.number.value < 0 or node.base.number.scientific)):
            base = f"({base})"
        return f"{base}^{node.exp}"
    if isinstance(node, Root):
        return f"sqrt({r(node.arg)})"
    if isinstance(node, Func):
        name = node.name if node.base is None else f"log_{node.base}"
        return f"{name}({r(node.arg)})"
    if isinstance(node, Apply):
        return f"{node.name}({r(node.arg)})"
    if isinstance(node, Abs):
        return f"|{r(node.arg)}|"
    if isinstance(node, Percent):
        return f"{r(node.arg)}%"
    if isinstance(node, Degrees):
        return f"{r(node.arg)}°"
    if isinstance(node, Magnification):
        return f"{r(node.arg)}×"
    if isinstance(node, Ratio):
        return f"{r(node.left)} : {r(node.right)}"
    if isinstance(node, BoolOp):
        if node.op == "not":
            return f"¬({r(node.args[0])})"
        sym = {"and": " ∧ ", "or": " ∨ ", "xor": " ⊕ "}.get(node.op, f" {node.op} ")
        return "(" + sym.join(r(a) for a in node.args) + ")"
    if isinstance(node, Unsupported):
        return f"<unsupported: {node.reason}>"
    return "?"
