"""AST to IR 1.0 (docs/STEM_DESIGN.md, section 7). No schema change, no evaluation of text.

:class:`Encoder` translates the frozen AST nodes of :mod:`.nodes` into IR 1.0 data (plain
``dict`` objects in the JSON form :class:`epinoic_logic.ir.schema.Problem` validates), one
allowlisted node at a time; anything else raises :class:`EncodeError` with the ST code and the
reason (an undecided relation, never a guess). :class:`ProblemBuilder` collects the symbols,
premises and notes of one problem. Every literal is exact (an integer, a terminating decimal
or ``p/q`` text) and at most 40 digits after decimal-exponent factoring (:mod:`.scaling`).

Encodings (section 7.4):

=========================  ==================================================================
construct                  encoding
=========================  ==================================================================
quantity                   literal × exact SI factor (SI reading) or the literal as written
``+ − unary−``             ``add`` (n-ary, flattened, nested beyond 32), ``sub``, ``neg``
``× · *`` juxtaposition    ``mul`` (linear while at most one factor holds a variable)
``a / b``, b a literal     ``div`` (b ≠ 0 checked exactly first: ST-UNDEF-001)
``a / b`` otherwise        auxiliary ``q``: ``Q_DEF q·b = a`` and ``GUARD b ≠ 0`` (never a ``div``
                           by a variable); a closed divisor whose value is exactly zero is
                           ST-UNDEF-001, one whose admissible values include zero ST-UNDEC-001
``xⁿ`` (2 ≤ n ≤ 12)        ``mul`` of n copies (a literal, a small closed term or a variable);
                           a compound base with variables first gets ``P_DEF p = x``
``x⁰``, ``x⁻ⁿ``            ``1`` (``0⁰`` is ST-UNDEF-001); ``q·xⁿ = 1`` with ``GUARD x ≠ 0``
``√x``                     auxiliary ``sq``: ``S_SQ sq ≥ 0 ∧ sq·sq = x`` (nonlinear); a closed
                           negative radicand is ST-UNDEF-001
``|x|``                    ``ite(x ≥ 0, x, −x)``
``n %``                    ``n/100`` (SI reading) or ``n`` (as written)
``a mod b``, ``a div b``   ``to_real(mod(A, b))``, ``to_real(idiv(A, b))``: A the Int encoding of written whole numbers
                           joined by ``+ − ×``, powers and nested remainders and quotients, its value not negative,
                           b a positive written whole number (STEM repair 2); anything else ST-UNDEC-001
``±``                      the sign choice of the reading (the caller combines both choices)
exact-table function       its exact value: rational, or ``q·sq`` with ``sq·sq = 2`` or ``3``
other function, π, e       enclosure symbol ``enc`` with ``ENC_LO ≤ enc ≤ ENC_HI`` (forces Form S)
``b^x``, x no integer      (a ``RealPower``: closed ``b`` and ``x``, no unit) its exact value when it is rational
                           (``16^(3/4) = 8``: the exact-value table) and fits a literal, else the enclosure of
                           ``exp(x·ln b)`` for ``b > 0``; ``0^x = 0`` for ``x > 0``; a base that is zero under a
                           non-positive exponent is ST-UNDEF-001, one that is or may be negative ST-UNDEC-001 (no real
                           power is chosen)
``bⁿ``, n beyond 12        (a ``RealPower`` whose exponent is an integer: closed ``b``, no unit) its exact value when it
                           fits a literal, else the interval power of ``b`` (outward rounded, any sign of ``b``); a
                           zero base under a non-positive exponent is ST-UNDEF-001, a result beyond 10^±300 ST-UNDEC-001
function of an unknown     ST-UNDEC-001
=========================  ==================================================================

Symbols map one-to-one into ``^[a-z][a-z0-9_]{0,63}$`` (:func:`ir_name`): ``v`` → ``s_v``, ``V`` →
``s_cap_v``, ``v₀`` → ``s_v_0``, ``Δv`` → ``s_delta_v``, ``θ`` → ``s_theta``, ``f′`` → ``s_f_prime``,
with a numeric suffix on collision. Auxiliaries are ``q_<n>``, ``p_<n>``, ``sq_<n>``, ``enc_<n>``
and ``x_<n>`` (interval operands); user symbols always start with ``s_``, so they never collide.

Groundings (section 7.6) are attached to every premise: report figures and definitions of the
compared values are ``supplied_text`` (verified: located in the report), request values
``task_setting`` (verified: located in the request), laws and the preceding relation of a step
``specialist_inference``, guards and side conditions ``assumption``, auxiliary definitions and
enclosures ``arithmetic_fact`` (encoding devices, not claims of the report), and a booklet value
for an unstated symbol ``assumption`` (the engine lists it in ``ungrounded_dependencies``).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterator, Optional

from .enclosures import EnclosureError, Interval, cross_check, enclose, exact_log, exact_real_power, exact_trig, isqrt_interval, pi_interval
from .nodes import (
    Abs, Apply, BinOp, BoolOp, Degrees, Func, IntOp, Magnification, Neg, Node, Num, Percent, PlusMinus, Pow, Quantity, Ratio, RealPower, Root,
    Sym, Unsupported, WithUnit, render, shape_key, walk,
)
from .numbers import ExactNumber
from .scaling import (
    LiteralTooLong, Term, add_terms, digit_count, div_literal, floor_log10, lit, literal_text, mul_terms, nary, neg_term, real, sub_terms, to_frame,
    var_term,
)
from .tolerance import STEM_SCOPE, abs_expr
from .units import UnitExpr

__all__ = [
    "EncodeError", "Encoder", "IR_LIMITS", "IntervalLeaf", "ProblemBuilder", "Reading", "SymbolDomain", "grounding", "inspect_ir", "ir_name",
    "PI_DEGREE", "real_power_value",
]

#: IR bounds the builder enforces before a problem leaves the pack (the engine's ``Limits`` defaults, and the
#: design's 48 symbols per check, section 4.9)
IR_LIMITS = {"symbols": 48, "premises": 128, "nodes": 2000, "depth": 40, "nary": 32, "digits": 40, "degree": 24}
_ENC_DIGITS = 25
_MAX_ENCODE_DEPTH = 64
#: closed compound bases up to this many IR nodes are repeated in a power (keeps the power linear)
_COPY_NODES = 12

PI_DEGREE = Fraction(1, 180)


class EncodeError(Exception):
    """A planned check the encodings cannot express: ``code`` is the ST code, ``reason`` names why."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


# --------------------------------------------------------------------------- symbol names

_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ϵ": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta", "ϑ": "theta_v",
    "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "µ": "mu", "ν": "nu", "ξ": "xi", "ο": "omicron", "π": "pi", "ρ": "rho", "σ": "sigma",
    "τ": "tau", "υ": "upsilon", "φ": "phi", "ϕ": "phi_v", "χ": "chi", "ψ": "psi", "ω": "omega",
}
_GREEK_UPPER = {"Α": "alpha", "Β": "beta", "Γ": "gamma", "Δ": "delta", "Ε": "epsilon", "Ζ": "zeta", "Η": "eta", "Θ": "theta", "Ι": "iota", "Κ": "kappa",
                "Λ": "lambda", "Μ": "mu", "Ν": "nu", "Ξ": "xi", "Ο": "omicron", "Π": "pi", "Ρ": "rho", "Σ": "sigma", "Τ": "tau", "Υ": "upsilon",
                "Φ": "phi", "Χ": "chi", "Ψ": "psi", "Ω": "omega"}
_SUBDIGITS = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
_SUPS = {"⁺": "plus", "⁻": "minus", "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"}
_PUNCT = {"'": "prime", "′": "prime", "″": "dprime", "°": "std", "(": "of", "[": "conc", "+": "plus", "-": "minus", "·": "dot", "∥": "par", "⊥": "perp",
          "½": "half"}


def ir_name(original: str) -> str:
    """The readable IR identifier of a front-end symbol name (before collision suffixes): ``s_`` and a
    character-by-character transliteration. Two names may share a slug only when they differ in
    characters that transliterate alike; :class:`ProblemBuilder` then adds a numeric suffix, so the
    map is one-to-one within every problem."""
    parts: list[str] = []
    for i, ch in enumerate(original):
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            parts.append(ch)
        elif "A" <= ch <= "Z":
            parts.append(f"_cap_{ch.lower()}_")
        elif ch == "Δ" and i == 0:
            parts.append("delta_")
        elif ch in _GREEK:
            parts.append(f"_{_GREEK[ch]}_")
        elif ch in _GREEK_UPPER:
            parts.append(f"_cap_{_GREEK_UPPER[ch]}_")
        elif ch in _SUBDIGITS:
            parts.append(_SUBDIGITS[ch])
        elif ch in _SUPS:
            parts.append(f"_{_SUPS[ch]}_")
        elif ch == "_":
            parts.append("_")
        elif ch in _PUNCT:
            parts.append(f"_{_PUNCT[ch]}_")
        elif ch in ")]":
            parts.append("_")
        else:
            parts.append(f"_u{ord(ch):x}_")
    slug = "".join(parts)
    while "__" in slug:
        slug = slug.replace("__", "_")
    slug = slug.strip("_") or "x"
    name = "s_" + slug
    if len(name) > 64:
        digest = hashlib.sha256(original.encode("utf-8", errors="surrogatepass")).hexdigest()[:8]
        name = name[:52].rstrip("_") + "_" + digest
    return name


# --------------------------------------------------------------------------- groundings

_NOTES = {
    "figure": "figure stated in the report itself",
    "request": "value stated in the request (located deterministically)",
    "device": "encoding device: defines the auxiliary as the written expression; not a claim of the report",
    "enclosure": "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value",
    "guard": "side condition of the encoding (a divisor is non-zero)",
    "law": "a stated law or the preceding relation, used as a premise of the step",
    "carried": "the answer's own earlier rounded result: it ranges over its rounding interval",
}


def grounding(kind: str, note: str = "") -> dict:
    """The grounding of one premise (section 7.6). ``kind``: ``figure``, ``request``, ``device``,
    ``enclosure``, ``guard``, ``law``, ``booklet`` (an unstated symbol's booklet value), ``constant``
    (a written constant widened to its booklet value), ``side`` (a step's side condition),
    ``carried``."""
    if kind in ("figure", "carried"):
        return {"kind": "supplied_text", "verified": True, "note": (note or _NOTES[kind])[:1000]}
    if kind == "request":
        return {"kind": "task_setting", "verified": True, "note": (note or _NOTES["request"])[:1000]}
    if kind in ("device", "enclosure", "constant"):
        return {"kind": "arithmetic_fact", "note": (note or _NOTES.get(kind, _NOTES["device"]))[:1000]}
    if kind == "law":
        return {"kind": "specialist_inference", "note": (note or _NOTES["law"])[:1000]}
    if kind in ("guard", "side", "booklet"):
        return {"kind": "assumption", "note": (note or _NOTES["guard"])[:1000]}
    raise ValueError(f"unknown grounding kind {kind!r}")


# --------------------------------------------------------------------------- the problem builder


class ProblemBuilder:
    """Symbols, premises and notes of one IR problem. Every symbol has a role (``pinned``,
    ``interval``, ``aux``, ``free``); a Form S problem may have no ``free`` symbol, so a free symbol
    can never make it vacuously satisfiable."""

    def __init__(self, problem_id: str, request_id: str, claim_id: str) -> None:
        self.problem_id = problem_id
        self.request_id = request_id
        self.claim_id = claim_id
        self.symbols: dict[str, dict] = {}
        self.roles: dict[str, str] = {}
        self.premises: list[dict] = []
        self._pids: set[str] = set()
        self._counters: dict[str, int] = {}
        self._user: dict[str, str] = {}
        self.notes: list[str] = []
        self.nonlinear = False

    # ---------------------------------------------------------------- symbols
    def declare(self, name: str, sort: str = "Real", meaning: str = "", role: str = "aux") -> str:
        if name not in self.symbols:
            self.symbols[name] = {"name": name, "sort": sort, "meaning": meaning[:1000]} if meaning else {"name": name, "sort": sort}
            self.roles[name] = role
        return name

    def fresh(self, prefix: str, sort: str = "Real", meaning: str = "", role: str = "aux") -> str:
        n = self._counters.get(prefix, 0) + 1
        while f"{prefix}_{n}" in self.symbols:
            n += 1
        self._counters[prefix] = n
        return self.declare(f"{prefix}_{n}", sort, meaning, role)

    def user_symbol(self, original: str, *, sort: str = "Real", meaning: str = "", role: str = "free", tag: str = "") -> str:
        """The IR name of the front-end symbol ``original`` (one-to-one within the problem). ``tag``
        separates per-reading copies of one symbol (``s_m`` and ``s_m_r2``)."""
        key = original + ("\u0000" + tag if tag else "")
        if key in self._user:
            return self._user[key]
        base = ir_name(original) + (f"_{tag}" if tag else "")
        base = base[:60]
        name = base
        n = 2
        while name in self.symbols:
            name = f"{base[:58]}_{n}"
            n += 1
        self._user[key] = name
        return self.declare(name, sort, meaning or f"the symbol '{original}' as written in the report", role)

    # ---------------------------------------------------------------- premises
    def premise(self, pid: str, expr: dict, label: str, ground: dict) -> str:
        base = pid
        n = 2
        while pid in self._pids:
            pid = f"{base}_{n}"
            n += 1
        self._pids.add(pid)
        self.premises.append({"id": pid, "expr": expr, "label": label[:1000], "grounding": ground})
        return pid

    def note(self, text: str) -> None:
        if text and text not in self.notes:
            self.notes.append(text)

    # ---------------------------------------------------------------- output
    def problem(self, query: str, conclusion: Optional[tuple[str, dict, str]] = None) -> dict:
        notes = [STEM_SCOPE] + self.notes
        text = " ".join(notes)
        if len(text) > 4000:
            text = text[:3997] + "…"
        data: dict = {
            "ir_version": "1.0", "problem_id": self.problem_id, "request_id": self.request_id, "claim_id": self.claim_id, "query": query,
            "symbols": list(self.symbols.values()), "premises": list(self.premises), "notes": text,
        }
        if conclusion is not None:
            data["conclusion"] = {"id": conclusion[0], "expr": conclusion[1], "label": conclusion[2][:1000], "grounding": grounding("figure")}
        return data


# --------------------------------------------------------------------------- IR inspection (data only)


def _children(expr: dict) -> list[dict]:
    out: list[dict] = []
    for key in ("arg", "left", "right", "cond", "then", "otherwise"):
        v = expr.get(key)
        if isinstance(v, dict):
            out.append(v)
    args = expr.get("args")
    if isinstance(args, list):
        out.extend(a for a in args if isinstance(a, dict))
    return out


def _walk_ir(expr: dict) -> Iterator[tuple[dict, int]]:
    stack = [(expr, 1)]
    while stack:
        node, d = stack.pop()
        yield node, d
        for c in _children(node):
            stack.append((c, d + 1))


def _has_var(expr: dict) -> bool:
    return any(n.get("op") == "var" for n, _d in _walk_ir(expr))


def _degree(expr: dict) -> int:
    """Polynomial degree as the engine's policy module counts it (var 1, literal 0, ``mul``/``div`` sum, else max)."""
    out: dict[int, int] = {}
    order: list[dict] = []
    stack = [expr]
    while stack:
        node = stack.pop()
        order.append(node)
        stack.extend(_children(node))
    for node in reversed(order):
        kids = [out[id(c)] for c in _children(node)]
        op = node.get("op")
        if op == "var":
            d = 1
        elif op in ("mul", "div", "idiv", "mod"):
            d = sum(kids)
        else:
            d = max(kids, default=0)
        out[id(node)] = d
    return out[id(expr)]


@dataclass(frozen=True)
class IRReport:
    symbols: int
    premises: int
    nodes: int
    depth: int
    nonlinear: bool
    degree: int
    max_nary: int
    max_digits: int


def inspect_ir(problem: dict) -> IRReport:
    """Counts of a built problem, by walking its IR as data: symbols, premises, nodes, depth, whether a
    ``mul`` has two or more factors holding a variable (the validator's nonlinear rule), the highest
    polynomial degree, the widest n-ary node and the longest literal."""
    exprs = [p["expr"] for p in problem.get("premises", [])]
    if problem.get("conclusion"):
        exprs.append(problem["conclusion"]["expr"])
    nodes = depth = max_nary = max_digits = degree = 0
    nonlinear = False
    for e in exprs:
        degree = max(degree, _degree(e))
        for node, d in _walk_ir(e):
            nodes += 1
            depth = max(depth, d)
            args = node.get("args")
            if isinstance(args, list):
                max_nary = max(max_nary, len(args))
                if node.get("op") == "mul" and sum(1 for a in args if _has_var(a)) >= 2:
                    nonlinear = True
            if node.get("op") in ("real", "int"):
                max_digits = max(max_digits, digit_count(str(node.get("value", ""))))
    return IRReport(len(problem.get("symbols", [])), len(exprs) - (1 if problem.get("conclusion") else 0), nodes, depth, nonlinear, degree, max_nary,
                    max_digits)


# --------------------------------------------------------------------------- readings and domains


@dataclass(frozen=True)
class Reading:
    """One reading of a check (section 6.4): ``si`` (every quantity in SI) or as written; the index of
    the reading of each ambiguous unit (keyed by the quantity's start offset); ``angle`` for a
    trigonometric argument written without ° or π and for an inverse function's result (``deg`` or
    ``rad``); ``affine`` applies the °C/°F offset (explicit conversions only); ``sign`` is the choice
    for every ``±`` (+1 or −1); ``degrees_si`` converts a value written in degrees to radians; ``percent`` (STEM repair 5) reads a
    per cent as its fraction in a reading as written ('1620 × 2% = 32.4 counts min⁻¹': units as written, 2% as 0.02)."""

    si: bool = False
    units: tuple[tuple[int, int], ...] = ()
    angle: str = "rad"
    affine: bool = False
    sign: int = 1
    degrees_si: bool = False
    label: str = "as written"
    percent: bool = False

    def unit_index(self, start: int) -> int:
        for s, idx in self.units:
            if s == start:
                return idx
        return 0


@dataclass(frozen=True)
class IntervalLeaf:
    """A written numeral that ranges over an interval (R3): a carried intermediate or a written
    constant. ``lo``/``hi`` are as written (the SI reading scales them by the unit's factor)."""

    lo: Fraction
    hi: Fraction
    kind: str  # 'carried' | 'constant'
    note: str


@dataclass
class SymbolDomain:
    """The values a front-end symbol may take in one problem: pinned values (an OR of equalities) or
    intervals (an OR of ``lo ≤ x ≤ hi``), as written and in SI, with the grounding of each."""

    name: str
    values_aw: list[tuple[Fraction, Fraction]] = field(default_factory=list)  # (lo, hi) as written
    values_si: list[Optional[tuple[Fraction, Fraction]]] = field(default_factory=list)
    groundings: list[dict] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    booklet: bool = False

    def add(self, lo_aw: Fraction, hi_aw: Fraction, si: Optional[tuple[Fraction, Fraction]], ground: dict, label: str) -> None:
        self.values_aw.append((lo_aw, hi_aw))
        self.values_si.append(si)
        self.groundings.append(ground)
        self.labels.append(label)

    @property
    def is_interval(self) -> bool:
        return any(lo != hi for lo, hi in self.values_aw) or any(v is not None and v[0] != v[1] for v in self.values_si)

    def ranges(self, si: bool) -> list[tuple[Fraction, Fraction]]:
        if not si:
            return list(self.values_aw)
        out = []
        for aw, s in zip(self.values_aw, self.values_si):
            out.append(s if s is not None else aw)
        return out

    def hull(self, si: bool) -> Interval:
        rs = self.ranges(si)
        return Interval(min(r[0] for r in rs), max(r[1] for r in rs))


# --------------------------------------------------------------------------- the encoder


def _key(node: Node) -> str:
    return shape_key(node)


def _exact_rational(node: Node) -> Optional[Fraction]:
    """The exact rational value of a closed node built from numerals with ``+ − × ÷`` and integer powers
    (no units, no π, no functions), for table lookups only; None otherwise."""
    if isinstance(node, Num):
        return node.number.value
    if isinstance(node, Neg):
        v = _exact_rational(node.arg)
        return None if v is None else -v
    if isinstance(node, BinOp):
        a, b = _exact_rational(node.left), _exact_rational(node.right)
        if a is None or b is None:
            return None
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if b == 0:
            return None
        return a / b
    if isinstance(node, Pow):
        a = _exact_rational(node.base)
        if a is None or (a == 0 and node.exp <= 0):
            return None
        return a ** node.exp
    if isinstance(node, RealPower):
        return real_power_value(node)
    return None


def real_power_value(node: RealPower) -> Optional[Fraction]:
    """The exact value of a ``RealPower`` when the encoder writes it exactly: its base and exponent written as exact
    rationals, :func:`~.enclosures.exact_real_power` of them (``16^(3/4)`` is 8, ``4^1.5`` is 8; an integer power of a
    negative base takes the sign of its parity, ``(−3/2)^13`` is ``−3^13/2^13``), and the value fits one IR literal. None
    for an irrational value (``10^0.4``, ``2^(−3.5)``) and for a rational one too long to write (``(2413/2400)^−60``),
    both of which the encoder encloses, and for anything not written as figures."""
    b, x = _exact_rational(node.base), _exact_rational(node.exponent)
    if b is None or x is None:
        return None
    if b == 0:
        return Fraction(0) if x > 0 else None
    if b < 0:
        if x.denominator != 1:
            return None  # which real power of a negative base the writer means is not chosen
        v = exact_real_power(-b, x)
        v = None if v is None else (v if x.numerator % 2 == 0 else -v)
    else:
        v = exact_real_power(b, x)
    return v if v is not None and _fits_literal(v) else None


def _fits_literal(value: Fraction) -> bool:
    """``value`` can be written as one IR literal (at most 40 digits after decimal-exponent factoring). Any failure to
    write it means it cannot: the caller then encloses the value."""
    try:
        lit(value)
    except (LiteralTooLong, ArithmeticError, AssertionError, ValueError):
        return False
    return True


#: the largest base-2 magnitude an integer power of a closed value may reach before it is computed (about 10^±300, the
#: range the exponential's enclosure accepts): beyond it the power is outside the encodings, never built
_MAX_POWER_BITS = 1000


def _power_magnitude_bits(b: Interval, n: int) -> int:
    """An upper bound of ``|log2 |b^n||`` from the bit lengths of the base's endpoints (no float, no power computed)."""
    def bits(x: Fraction) -> int:
        x = abs(x)
        if x == 0:
            return 0
        return abs(x.numerator.bit_length() - x.denominator.bit_length()) + 1
    return abs(n) * max(bits(b.lo), bits(b.hi))


def pi_multiple(node: Node) -> Optional[Fraction]:
    """``q`` when ``node`` is exactly ``q·π`` with ``q`` rational (``π/6``, ``2π/3``, ``−π``), else None."""
    if isinstance(node, Sym) and node.kind == "constant" and node.name == "π":
        return Fraction(1)
    if isinstance(node, Neg):
        v = pi_multiple(node.arg)
        return None if v is None else -v
    if isinstance(node, BinOp) and node.op in "*/":
        a, b = pi_multiple(node.left), pi_multiple(node.right)
        ra, rb = _exact_rational(node.left), _exact_rational(node.right)
        if node.op == "*":
            if a is not None and rb is not None:
                return a * rb
            if b is not None and ra is not None:
                return b * ra
            return None
        if a is not None and rb is not None and rb != 0:
            return a / rb
    return None


def _contains_pi(node: Node) -> bool:
    return any(isinstance(n, Sym) and n.kind == "constant" for n in walk(node))


_TRIG = frozenset({"sin", "cos", "tan"})
_INVERSE = frozenset({"arcsin", "arccos", "arctan"})
_INVERSE_DEGREES = {
    "arcsin": {Fraction(0): 0, Fraction(1, 2): 30, Fraction(1): 90, Fraction(-1, 2): -30, Fraction(-1): -90},
    "arccos": {Fraction(1): 0, Fraction(1, 2): 60, Fraction(0): 90, Fraction(-1, 2): 120, Fraction(-1): 180},
    "arctan": {Fraction(0): 0, Fraction(1): 45, Fraction(-1): -45},
}


class Encoder:
    """Translates AST nodes into scaled IR terms under one :class:`Reading`, adding auxiliary symbols
    and their defining premises to a :class:`ProblemBuilder`.

    ``env`` maps front-end symbol names to terms (a free, pinned or interval-bounded IR variable).
    ``intervals`` maps a numeral's offsets ``(start, end)`` to its interval reading. ``closed_only``
    refuses free symbols inside functions (a function of an unknown is ST-UNDEC-001).
    ``symbol_hulls`` gives the Python interval of each symbol (for pre-checks and function arguments).
    Flags after encoding: ``uses_intervals`` (an interval leaf, an interval symbol or an enclosure
    was used: the check must be Form S unless it is an algebra step), ``enclosures`` (names used)."""

    def __init__(self, builder: ProblemBuilder, reading: Reading, *, env: Optional[dict[str, Term]] = None,
                 intervals: Optional[dict[tuple[int, int], IntervalLeaf]] = None, symbol_hulls: Optional[dict[str, Interval]] = None,
                 interval_symbols: frozenset[str] = frozenset(), cache: Optional[dict] = None, tag: str = "") -> None:
        self.b = builder
        self.r = reading
        self.env = env or {}
        self.intervals = intervals or {}
        self.symbol_hulls = symbol_hulls or {}
        self.interval_symbols = interval_symbols
        self.cache = cache if cache is not None else {}
        self.tag = tag
        self.uses_intervals = False
        self.enclosures: list[str] = []
        self.exact_used: list[str] = []
        self._iv_cache: dict[int, Interval] = {}

    # ------------------------------------------------------------------ public
    def term(self, node: Node, depth: int = 0) -> Term:
        if depth > _MAX_ENCODE_DEPTH:
            raise EncodeError("ST-LIM-001", "an expression nested too deeply to encode")
        try:
            return self._term(node, depth)
        except LiteralTooLong as exc:
            raise EncodeError("ST-LIM-001", str(exc)) from None
        except EnclosureError as exc:
            raise EncodeError(exc.code, exc.reason) from None

    def free(self, node: Node) -> bool:
        """True when ``node`` holds a symbol with no value domain here (a free variable) or an ``f(x)``."""
        return _has_free(node, self.symbol_hulls)

    # ------------------------------------------------------------------ leaves
    def _unit_factor(self, unit: UnitExpr, start: int, value: Fraction) -> Fraction:
        """The SI value of ``value`` written in ``unit`` under this reading."""
        if not self.r.si:
            return value
        if unit.unknown or not unit.readings:
            raise EncodeError("ST-UNIT-001", f"the unit '{unit.text}' is not recognised")
        idx = min(self.r.unit_index(start), len(unit.readings) - 1)
        rd = unit.readings[idx]
        if rd.affine is not None and self.r.affine:
            factor, offset = rd.affine
            return factor * (value + offset)
        if rd.factor is None:
            if rd.is_angle and rd.atoms and rd.atoms[0].unit is not None and rd.atoms[0].unit.angle_degrees is not None:
                raise EncodeError("ST-UNDEC-001", f"an angle in '{unit.text}' compared in SI (radians need π)")
            raise EncodeError("ST-UNDEC-001", f"the unit '{unit.text}' has no exact SI factor")
        return value * rd.factor

    def _factor_of(self, unit: UnitExpr, start: int) -> Fraction:
        """The multiplicative SI factor of a unit under this reading (affine offsets excluded)."""
        if not self.r.si:
            return Fraction(1)
        if unit.unknown or not unit.readings:
            raise EncodeError("ST-UNIT-001", f"the unit '{unit.text}' is not recognised")
        idx = min(self.r.unit_index(start), len(unit.readings) - 1)
        rd = unit.readings[idx]
        if rd.factor is None:
            raise EncodeError("ST-UNDEC-001", f"the unit '{unit.text}' has no exact SI factor")
        return rd.factor

    def _number(self, number: ExactNumber, unit: Optional[UnitExpr], node: Node) -> Term:
        leaf = self.intervals.get((getattr(node, "start", -1), getattr(node, "end", -1)))
        if leaf is not None:
            return self._interval_leaf(leaf, number, unit, node)
        value = number.value
        if unit is not None:
            value = self._unit_factor(unit, getattr(node, "start", 0), value)
        return lit(value)

    def _interval_leaf(self, leaf: IntervalLeaf, number: ExactNumber, unit: Optional[UnitExpr], node: Node) -> Term:
        key = ("leaf", getattr(node, "start", 0), getattr(node, "end", 0))
        if key not in self.cache:
            name = self.b.fresh("x", meaning=f"the written {number.text} ({leaf.kind}) over [{literal_text(leaf.lo)}, {literal_text(leaf.hi)}] as written",
                                role="interval")
            k = self._frame_of(leaf.lo, leaf.hi)
            g = grounding("carried" if leaf.kind == "carried" else "constant", leaf.note)
            self.b.premise(f"X_LO_{name}", {"op": "ge", "left": {"op": "var", "name": name}, "right": real(leaf.lo / Fraction(10) ** k)}, leaf.note, g)
            self.b.premise(f"X_HI_{name}", {"op": "le", "left": {"op": "var", "name": name}, "right": real(leaf.hi / Fraction(10) ** k)}, leaf.note, g)
            self.cache[key] = var_term(name, k)
        self.uses_intervals = True
        t: Term = self.cache[key]
        if unit is not None and self.r.si:
            f = self._factor_of(unit, getattr(node, "start", 0))
            if f != 1:
                t, nl = mul_terms([lit(f), t])
        return t

    @staticmethod
    def _frame_of(lo: Fraction, hi: Fraction) -> int:
        m = max(abs(lo), abs(hi))
        if m == 0:
            return 0
        k = floor_log10(m)
        return 0 if -12 <= k < 12 else k

    # ------------------------------------------------------------------ dispatch
    def _term(self, node: Node, depth: int) -> Term:
        rec = lambda n: self.term(n, depth + 1)  # noqa: E731
        if isinstance(node, Num):
            return self._number(node.number, None, node)
        if isinstance(node, Quantity):
            return self._number(node.number, node.unit, node)
        if isinstance(node, WithUnit):
            inner = rec(node.arg)
            f = self._factor_of(node.unit, getattr(node, "start", 0))
            if f == 1:
                return inner
            t, _nl = mul_terms([lit(f), inner])
            return t
        if isinstance(node, Sym):
            return self._symbol(node)
        if isinstance(node, Neg):
            return neg_term(rec(node.arg))
        if isinstance(node, BinOp):
            if node.op == "+":
                return add_terms([rec(n) for n in _flatten(node, "+")])
            if node.op == "-":
                return sub_terms(rec(node.left), rec(node.right))
            if node.op == "*":
                factors = [rec(n) for n in _flatten(node, "*")]
                t, nl = mul_terms(factors)
                self.b.nonlinear |= nl
                return t
            return self._divide(node, rec(node.left), node.right, depth)
        if isinstance(node, PlusMinus):
            sign = self.r.sign if node.sign == "±" else -self.r.sign
            right = rec(node.right)
            if node.left is None:
                return right if sign > 0 else neg_term(right)
            left = rec(node.left)
            return add_terms([left, right]) if sign > 0 else sub_terms(left, right)
        if isinstance(node, Pow):
            return self._power(node, depth)
        if isinstance(node, RealPower):
            return self._real_power(node)
        if isinstance(node, Root):
            if node.index != 2:
                raise EncodeError("ST-UNDEC-001", f"a root of index {node.index}")
            return self._sqrt(node.arg, rec(node.arg), _key(node))
        if isinstance(node, Func):
            return self._function(node)
        if isinstance(node, Abs):
            t = rec(node.arg)
            if t.lit is not None:
                return lit(abs(t.value or Fraction(0)))
            return Term(abs_expr(t.expr), t.k, t.closed)
        if isinstance(node, Percent):
            t = rec(node.arg)
            if not self.r.si and not self.r.percent:
                return t
            if t.lit is not None:
                return lit((t.value or Fraction(0)) / 100)
            return Term(t.expr, t.k - 2, t.closed)
        if isinstance(node, Degrees):
            t = rec(node.arg)
            if not self.r.degrees_si:
                return t
            enc = self._enclosure_symbol("pi/180", None, pi_interval().scale(PI_DEGREE), "π/180 (degrees to radians)")
            out, nl = mul_terms([t, enc])
            self.b.nonlinear |= nl
            return out
        if isinstance(node, Magnification):
            return rec(node.arg)
        if isinstance(node, IntOp):
            return Term({"op": "to_real", "arg": _int_op_ir(node)}, 0, True)
        if isinstance(node, Ratio):
            raise EncodeError("ST-UNDEC-001", "a ratio outside a ratio relation")
        if isinstance(node, Apply):
            raise EncodeError("ST-UNDEC-001", f"a function of an unknown ({node.name}(…))")
        if isinstance(node, BoolOp):
            raise EncodeError("ST-UNDEC-001", "a Boolean expression in an arithmetic relation")
        if isinstance(node, Unsupported):
            raise EncodeError("ST-UNDEC-001", node.reason)
        raise EncodeError("ST-UNDEC-001", f"a construct outside the encodings ({type(node).__name__})")

    def _symbol(self, node: Sym) -> Term:
        if node.kind == "constant":
            return self._enclosure_symbol("pi", None, pi_interval(), "π")
        t = self.env.get(node.name)
        if t is None:
            raise EncodeError("ST-UNDEC-002", f"'{node.name}' has no stated value and no admissible booklet reading")
        if node.name in self.interval_symbols:
            self.uses_intervals = True
        return t

    # ------------------------------------------------------------------ division, powers, roots
    def _divide(self, node: BinOp, a: Term, divisor: Node, depth: int) -> Term:
        b = self.term(divisor, depth + 1)
        if b.zero:
            raise EncodeError("ST-UNDEF-001", f"a division by zero in '{render(node)[:80]}'")
        if b.lit is not None:
            return div_literal(a, b)
        if not self.free(divisor):
            self._nonzero_precheck(divisor, f"'{render(node)[:80]}'")
        key = ("q", self.r.label, _key(node))
        if key in self.cache:
            return self.cache[key]
        name = self.b.fresh("q", meaning=f"the quotient {render(node)[:200]}", role="aux")
        qk = a.k - b.k
        q = var_term(name, qk)
        prod, nl = mul_terms([Term({"op": "var", "name": name}, 0, False), Term(b.expr, 0, b.closed)])
        self.b.nonlinear |= nl
        self.b.premise(f"Q_DEF_{name}", {"op": "eq", "left": prod.expr, "right": a.expr}, f"{name} is the quotient {render(node)[:300]}", grounding("device"))
        self.b.premise(f"GUARD_{name}", {"op": "ne", "left": b.expr, "right": {"op": "real", "value": "0"}}, f"the divisor of {render(node)[:300]} is not zero",
                       grounding("guard"))
        self.cache[key] = q
        return q

    def _nonzero_precheck(self, divisor: Node, where: str) -> None:
        try:
            iv = self.interval(divisor)
        except EncodeError:
            return
        except EnclosureError:
            return
        if iv.is_point and iv.lo == 0:
            raise EncodeError("ST-UNDEF-001", f"a division by an expression that is exactly zero in {where}")
        if iv.contains_zero():
            # a guard that might fail would make a satisfiability query unsatisfiable for a reason that is no fault of the stated value
            raise EncodeError("ST-UNDEC-001", f"a divisor whose admissible values include zero in {where}")

    def _power(self, node: Pow, depth: int) -> Term:
        n = node.exp
        if n == 1:
            return self.term(node.base, depth + 1)
        base = self.term(node.base, depth + 1)
        if n == 0:
            if base.zero:
                raise EncodeError("ST-UNDEF-001", "0⁰ is undefined")
            if base.lit is None:
                if base.closed:
                    self._nonzero_precheck(node.base, f"the base of '{render(node)[:80]}'")
                self.b.premise("GUARD_POW0", {"op": "ne", "left": base.expr, "right": {"op": "real", "value": "0"}}, "the base of a zeroth power is not zero",
                               grounding("guard"))
            return lit(Fraction(1))
        m = abs(n)
        powered = self._positive_power(base, m, node)
        if n > 0:
            return powered
        if base.zero:
            raise EncodeError("ST-UNDEF-001", f"a negative power of zero in '{render(node)[:80]}'")
        if base.closed and base.lit is None:
            self._nonzero_precheck(node.base, f"the base of '{render(node)[:80]}'")
        key = ("qpow", self.r.label, _key(node))
        if key in self.cache:
            return self.cache[key]
        name = self.b.fresh("q", meaning=f"the negative power {render(node)[:200]}", role="aux")
        prod, nl = mul_terms([Term({"op": "var", "name": name}, 0, False), Term(powered.expr, 0, powered.closed)])
        self.b.nonlinear |= nl
        self.b.premise(f"Q_DEF_{name}", {"op": "eq", "left": prod.expr, "right": {"op": "real", "value": "1"}}, f"{name} is {render(node)[:300]}",
                       grounding("device"))
        self.b.premise(f"GUARD_{name}", {"op": "ne", "left": powered.expr, "right": {"op": "real", "value": "0"}}, "the base of a negative power is not zero",
                       grounding("guard"))
        t = var_term(name, -powered.k)
        self.cache[key] = t
        return t

    def _positive_power(self, base: Term, m: int, node: Pow) -> Term:
        if base.zero:
            return base
        if base.lit is not None or (base.closed and _ir_size(base.expr) <= _COPY_NODES) or base.expr.get("op") == "var":
            t, nl = mul_terms([base] * m)
            self.b.nonlinear |= nl
            return t
        key = ("p", self.r.label, _key(node.base))
        if key not in self.cache:
            name = self.b.fresh("p", meaning=f"the base {render(node.base)[:200]}", role="aux")
            self.b.premise(f"P_DEF_{name}", {"op": "eq", "left": {"op": "var", "name": name}, "right": base.expr}, f"{name} is {render(node.base)[:300]}",
                           grounding("device"))
            self.cache[key] = var_term(name, base.k)
        p = self.cache[key]
        t, nl = mul_terms([p] * m)
        self.b.nonlinear |= nl
        return t

    def _sqrt(self, arg: Node, x: Term, key_text: str) -> Term:
        if x.zero:
            return x
        if x.lit is not None and x.lit < 0:
            raise EncodeError("ST-UNDEF-001", f"the square root of a negative value in '{render(arg)[:80]}'")
        if x.closed and x.lit is None:
            try:
                iv = self.interval(arg)
            except (EncodeError, EnclosureError):
                iv = None
            if iv is not None and iv.hi < 0:
                raise EncodeError("ST-UNDEF-001", f"the square root of a negative value in '{render(arg)[:80]}'")
        key = ("sq", self.r.label, key_text)
        if key in self.cache:
            return self.cache[key]
        frame = x
        if x.k % 2:
            frame = Term(to_frame(x, x.k - 1), x.k - 1, x.closed, None if x.lit is None else x.lit * 10)
        name = self.b.fresh("sq", meaning=f"the principal square root of {render(arg)[:200]}", role="aux")
        v = {"op": "var", "name": name}
        self.b.premise(f"S_SQ_{name}", {"op": "and", "args": [{"op": "ge", "left": v, "right": {"op": "real", "value": "0"}},
                                                            {"op": "eq", "left": {"op": "mul", "args": [v, v]}, "right": frame.expr}]},
                       f"{name} is the non-negative square root of {render(arg)[:300]}", grounding("device"))
        self.b.nonlinear = True
        t = var_term(name, frame.k // 2)
        self.cache[key] = t
        return t

    def _surd(self, radicand: int) -> Term:
        key = ("surd", radicand)
        if key in self.cache:
            return self.cache[key]
        name = self.b.fresh("sq", meaning=f"the exact square root of {radicand} (exact-value table)", role="aux")
        v = {"op": "var", "name": name}
        self.b.premise(f"S_SQ_{name}", {"op": "and", "args": [{"op": "ge", "left": v, "right": {"op": "real", "value": "0"}},
                                                            {"op": "eq", "left": {"op": "mul", "args": [v, v]}, "right": {"op": "real", "value": str(radicand)}}]},
                       f"{name} is the square root of {radicand}", grounding("device"))
        self.b.nonlinear = True
        t = var_term(name, 0)
        self.cache[key] = t
        return t

    # ------------------------------------------------------------------ functions
    def _angle_radians(self, arg: Node) -> tuple[Interval, Optional[Fraction], str]:
        """The argument of a trigonometric function in radians (an interval), its exact value in
        degrees when it has one, and the angle unit used."""
        if isinstance(arg, Degrees):
            deg = self.interval(arg.arg)
            exact = deg.lo if deg.is_point else None
            return deg * pi_interval().scale(PI_DEGREE), exact, "deg"
        mult = pi_multiple(arg)
        if mult is not None:
            return pi_interval().scale(mult), mult * 180, "rad"
        iv = self.interval(arg)
        if _contains_pi(arg) or self.r.angle == "rad":
            exact = Fraction(0) if (iv.is_point and iv.lo == 0) else None
            return iv, exact, "rad"
        exact = iv.lo if iv.is_point else None
        return iv * pi_interval().scale(PI_DEGREE), exact, "deg"

    def _function(self, node: Func) -> Term:
        name = node.name
        if self.free(node.arg):
            raise EncodeError("ST-UNDEC-001", f"a function of an unknown ({name})")
        if name in _TRIG:
            rad, deg_exact, unit = self._angle_radians(node.arg)
            if deg_exact is not None:
                hit = exact_trig(name, deg_exact)
                if hit is not None:
                    self.exact_used.append(f"{name} {literal_text(deg_exact)}° (exact-value table)")
                    if hit.is_rational:
                        return lit(hit.coefficient)
                    t, nl = mul_terms([lit(hit.coefficient), self._surd(hit.radicand)])
                    return t
            label = f"{name}({render(node.arg)[:60]}{'' if unit == 'rad' or isinstance(node.arg, Degrees) else ' in degrees'})"
            return self._enclosure_symbol(name, rad, enclose(name, rad), label)
        if name in _INVERSE:
            x = self.interval(node.arg)
            if self.r.angle == "deg" and x.is_point and x.lo in _INVERSE_DEGREES[name]:
                self.exact_used.append(f"{name} {literal_text(x.lo)} = {_INVERSE_DEGREES[name][x.lo]}° (exact-value table)")
                return lit(Fraction(_INVERSE_DEGREES[name][x.lo]))
            out = enclose(name, x)
            if self.r.angle == "deg":
                out = out / pi_interval().scale(PI_DEGREE)
            return self._enclosure_symbol(name + ("_deg" if self.r.angle == "deg" else ""), x, out, f"{name}({render(node.arg)[:60]})"
                                          + (" in degrees" if self.r.angle == "deg" else " in radians"), check_name=name, check_iv=enclose(name, x))
        if name in ("ln", "log", "log10"):
            x = self.interval(node.arg)
            if x.is_point:
                hit = exact_log(name, x.lo, node.base)
                if hit is not None:
                    self.exact_used.append(f"{name}{'_' + str(node.base) if node.base else ''} {literal_text(x.lo)} = {literal_text(hit)} (exact)")
                    return lit(hit)
            if x.hi <= 0:
                raise EncodeError("ST-UNDEF-001", f"the logarithm of a non-positive value in '{render(node)[:80]}'")
            return self._enclosure_symbol(name, x, enclose(name, x, base=node.base), f"{name}({render(node.arg)[:60]})", base=node.base)
        if name == "exp":
            x = self.interval(node.arg)
            if x.is_point and x.lo == 0:
                return lit(Fraction(1))
            return self._enclosure_symbol(name, x, enclose(name, x), f"exp({render(node.arg)[:60]})")
        raise EncodeError("ST-UNDEC-001", f"the function {name}")

    def _real_power_interval(self, node: RealPower) -> tuple[Interval, Interval, Optional[Interval]]:
        """``(base, exponent, value)`` intervals of a ``RealPower``: the value is its exact point when it is rational and
        fits a literal (:func:`real_power_value`), else, for an integer exponent (a power beyond ``max_int_power``), the
        interval power of the base (outward rounded, a base of any sign), and for any other exponent the enclosure of
        ``exp(x·ln b)`` for a positive base; None for ``0^x`` with ``x > 0`` (exactly zero). Raises :class:`EncodeError` for
        a base that is zero under a non-positive exponent (ST-UNDEF-001), for a non-integer power of a base that is or may
        be negative (ST-UNDEC-001: which real power the writer means is not chosen here), for an integer power whose value
        would lie beyond about 10^±300 (ST-UNDEC-001), and for a power of an unknown."""
        if self.free(node.base) or self.free(node.exponent):
            raise EncodeError("ST-UNDEC-001", f"a non-integer power of an unknown ('{render(node)[:80]}')")
        b, x = self.interval(node.base), self.interval(node.exponent)
        integer = x.is_point and x.lo.denominator == 1
        if b.is_point and b.lo == 0:
            if x.lo > 0:
                return b, x, None
            raise EncodeError("ST-UNDEF-001", f"zero raised to a power that is not positive in '{render(node)[:80]}'")
        if b.lo <= 0 and not integer:
            raise EncodeError("ST-UNDEC-001", f"a non-integer power of a base that is or may be negative or zero in '{render(node)[:80]}'")
        if not any(isinstance(n, (Num, Quantity)) and (n.start, n.end) in self.intervals for n in walk(node)):
            # figures as written (no carried intermediate ranging over its rounding here): a rational power is exact
            # (16^(3/4) = 8, 8^(1/3) = 2, 3^13 = 1594323), as the table gives sin 30° = 1/2
            exact = real_power_value(node)
            if exact is not None:
                return b, x, Interval.point(exact)
        if integer:
            n = int(x.lo)
            if _power_magnitude_bits(b, n) > _MAX_POWER_BITS:
                raise EncodeError("ST-UNDEC-001", f"an integer power whose value lies beyond the bounds of the encodings in '{render(node)[:80]}'")
            return b, x, b.power(n)
        return b, x, enclose("exp", enclose("ln", b) * x)

    def _real_power(self, node: RealPower) -> Term:
        b, x, iv = self._real_power_interval(node)
        if iv is None:
            return lit(Fraction(0))
        if iv.is_point and _fits_literal(iv.lo):
            self.exact_used.append(f"{render(node)[:60]} = {literal_text(iv.lo)} (exact)")
            return lit(iv.lo)
        # an irrational value, or an exact one too long for a literal: enclosed (rounded outward), which forces Form S
        return self._enclosure_symbol("pow", b, iv, render(node)[:60], exponent=x)

    def _enclosure_symbol(self, name: str, x: Optional[Interval], iv: Interval, label: str, *, base: Optional[int] = None,
                          check_name: Optional[str] = None, check_iv: Optional[Interval] = None, exponent: Optional[Interval] = None) -> Term:
        key = ("enc", name, base, None if x is None else (x.lo, x.hi), None if exponent is None else (exponent.lo, exponent.hi))
        if key in self.cache:
            self.uses_intervals = True
            return self.cache[key]
        cname = check_name or name
        if cname in ("pi", "e", "sin", "cos", "tan", "arcsin", "arccos", "arctan", "ln", "log", "log10", "exp", "pow"):
            if not cross_check(cname, x, check_iv or iv, base=base, exponent=exponent):
                raise EncodeError("ST-INTERNAL-001", f"the enclosure of {label} failed its cross-check against the math library")
        lo, hi = _round_out(iv.lo, "down"), _round_out(iv.hi, "up")
        k = self._frame_of(lo, hi)
        enc = self.b.fresh("enc", meaning=f"enclosure of {label}"[:1000], role="interval")
        note = f"enclosure of {label}: [{literal_text(lo / Fraction(10) ** k)}, {literal_text(hi / Fraction(10) ** k)}]" + (f" × 10^{k}" if k else "")
        g = grounding("enclosure")
        self.b.premise(f"ENC_LO_{enc}", {"op": "ge", "left": {"op": "var", "name": enc}, "right": real(lo / Fraction(10) ** k)}, note, g)
        self.b.premise(f"ENC_HI_{enc}", {"op": "le", "left": {"op": "var", "name": enc}, "right": real(hi / Fraction(10) ** k)}, note, g)
        t = var_term(enc, k)
        self.cache[key] = t
        self.uses_intervals = True
        self.enclosures.append(label)
        return t

    # ------------------------------------------------------------------ Python interval evaluation (pre-checks and function arguments)
    def interval(self, node: Node) -> Interval:
        """The interval of a closed node under this reading: exact points for numerals, enclosures
        for π and functions, the hull of a symbol's admissible values. Used only to refuse undefined
        encodings and to place function arguments; never to decide a stated relation."""
        hit = self._iv_cache.get(id(node))
        if hit is not None:
            return hit
        iv = self._interval(node, 0)
        self._iv_cache[id(node)] = iv
        return iv

    def _interval(self, node: Node, depth: int) -> Interval:
        if depth > _MAX_ENCODE_DEPTH:
            raise EncodeError("ST-LIM-001", "an expression nested too deeply to evaluate")
        rec = lambda n: self._interval(n, depth + 1)  # noqa: E731
        if isinstance(node, (Num, Quantity)):
            leaf = self.intervals.get((node.start, node.end))
            unit = node.unit if isinstance(node, Quantity) else None
            if leaf is not None:
                f = self._factor_of(unit, node.start) if unit is not None else Fraction(1)
                return Interval(min(leaf.lo * f, leaf.hi * f), max(leaf.lo * f, leaf.hi * f))
            v = node.number.value
            if unit is not None:
                v = self._unit_factor(unit, node.start, v)
            return Interval.point(v)
        if isinstance(node, WithUnit):
            return rec(node.arg).scale(self._factor_of(node.unit, node.start))
        if isinstance(node, Sym):
            if node.kind == "constant":
                return pi_interval()
            h = self.symbol_hulls.get(node.name)
            if h is None:
                raise EncodeError("ST-UNDEC-001", f"a function of an unknown ('{node.name}')")
            return h
        if isinstance(node, Neg):
            return -rec(node.arg)
        if isinstance(node, BinOp):
            a, b = rec(node.left), rec(node.right)
            if node.op == "+":
                return a + b
            if node.op == "-":
                return a - b
            if node.op == "*":
                return a * b
            if b.is_point and b.lo == 0:
                raise EncodeError("ST-UNDEF-001", f"a division by zero in '{render(node)[:80]}'")
            return a / b
        if isinstance(node, PlusMinus):
            sign = self.r.sign if node.sign == "±" else -self.r.sign
            right = rec(node.right)
            if node.left is None:
                return right if sign > 0 else -right
            left = rec(node.left)
            return left + right if sign > 0 else left - right
        if isinstance(node, Pow):
            return rec(node.base).power(node.exp)
        if isinstance(node, RealPower):
            b, _x, iv = self._real_power_interval(node)
            return Interval.point(Fraction(0)) if iv is None else iv
        if isinstance(node, Root):
            x = rec(node.arg)
            if x.hi < 0:
                raise EncodeError("ST-UNDEF-001", "the square root of a negative value")
            return isqrt_interval(Interval(max(x.lo, Fraction(0)), x.hi))
        if isinstance(node, Abs):
            return rec(node.arg).abs()
        if isinstance(node, Percent):
            x = rec(node.arg)
            return x.scale(Fraction(1, 100)) if (self.r.si or self.r.percent) else x
        if isinstance(node, (Degrees, Magnification)):
            return rec(node.arg)
        if isinstance(node, IntOp):
            _int_op_ir(node)  # refuses what the encodings do not take, with the reason
            return Interval.point(Fraction(_int_value(node)))
        if isinstance(node, Func):
            name = node.name
            if name in _TRIG:
                rad, deg_exact, _unit = self._angle_radians(node.arg)
                if deg_exact is not None:
                    hit = exact_trig(name, deg_exact)
                    if hit is not None:
                        if hit.is_rational:
                            return Interval.point(hit.coefficient)
                        return isqrt_interval(Interval.point(Fraction(hit.radicand))).scale(hit.coefficient)
                return enclose(name, rad)
            if name in _INVERSE:
                out = enclose(name, rec(node.arg))
                return out / pi_interval().scale(PI_DEGREE) if self.r.angle == "deg" else out
            if name in ("ln", "log", "log10", "exp"):
                return enclose(name, rec(node.arg), base=node.base)
        raise EncodeError("ST-UNDEC-001", f"a construct outside the encodings ({type(node).__name__})")


# ------------------------------------------------------------------ integer remainder and quotient (STEM repair 2)
#: the most digits of one Int literal (the IR bound on a literal)
_INT_DIGITS = 40


def _whole(node: Node) -> Optional[int]:
    """The value of a written whole number (no point, no exponent form, no fraction character, no unit), else None."""
    if not isinstance(node, Num):
        return None
    num = node.number
    if num.has_point or num.scientific or num.vulgar or num.value.denominator != 1:
        return None
    v = int(num.value)
    return v if len(str(abs(v))) <= _INT_DIGITS else None


def _int_value(node: Node, depth: int = 0) -> Optional[int]:
    """The exact integer an integer expression of written whole numbers stands for (``+ − ×``, a power of at most 12, nested
    remainders and quotients under the encoding's own conditions), else None. Exact integer bookkeeping on written numbers
    only, as the encoder's pre-checks do; the engine decides every stated relation."""
    if depth > _MAX_ENCODE_DEPTH:
        return None
    rec = lambda n: _int_value(n, depth + 1)  # noqa: E731
    w = _whole(node)
    if w is not None:
        return w
    if isinstance(node, Neg):
        a = rec(node.arg)
        return None if a is None else -a
    if isinstance(node, BinOp) and node.op in "+-*":
        a, b = rec(node.left), rec(node.right)
        if a is None or b is None:
            return None
        out = a + b if node.op == "+" else a - b if node.op == "-" else a * b
        return out if len(str(abs(out))) <= _INT_DIGITS else None
    if isinstance(node, Pow) and 0 <= node.exp <= 12:
        a = rec(node.base)
        if a is None:
            return None
        out = a ** node.exp
        return out if len(str(abs(out))) <= _INT_DIGITS else None
    if isinstance(node, IntOp):
        a, b = rec(node.left), _whole(node.right)
        if a is None or b is None or a < 0 or b <= 0:
            return None
        return a % b if node.op == "mod" else a // b
    return None


def _int_ir(node: Node, depth: int = 0) -> dict:
    """The Int-sorted IR of an integer expression of written whole numbers (:func:`_int_value`'s forms)."""
    if depth > _MAX_ENCODE_DEPTH:
        raise EncodeError("ST-LIM-001", "an expression nested too deeply to encode")
    rec = lambda n: _int_ir(n, depth + 1)  # noqa: E731
    w = _whole(node)
    if w is not None:
        return {"op": "int", "value": str(w)}
    if isinstance(node, Neg):
        return {"op": "neg", "arg": rec(node.arg)}
    if isinstance(node, BinOp) and node.op in "+-*":
        if node.op == "-":
            return {"op": "sub", "left": rec(node.left), "right": rec(node.right)}
        op = "+" if node.op == "+" else "*"
        return nary("add" if op == "+" else "mul", [rec(n) for n in _flatten(node, op)])
    if isinstance(node, Pow) and 0 <= node.exp <= 12:
        if node.exp == 0:
            return {"op": "int", "value": "1"}
        base = rec(node.base)
        return base if node.exp == 1 else nary("mul", [base] * node.exp)
    if isinstance(node, IntOp):
        return _int_op_ir(node, depth + 1)
    raise EncodeError("ST-UNDEC-001", "an integer remainder or quotient of an operand that is not a whole number as written "
                                      f"('{render(node)[:60]}')")


def _int_op_ir(node: IntOp, depth: int = 0) -> dict:
    """``mod(A, b)`` or ``idiv(A, b)`` (Int): A the left operand's Int IR, its value not negative, b a positive written whole
    number. A negative operand or another divisor is outside the encodings: languages disagree there (Python's ``%`` and
    ``//`` round towards minus infinity, C's and Java's towards zero), and the IR admits only a literal divisor."""
    what = "an integer remainder" if node.op == "mod" else "an integer quotient"
    b = _whole(node.right)
    if b is None or b <= 0:
        raise EncodeError("ST-UNDEC-001", f"{what} whose divisor is not a positive whole number as written ('{render(node.right)[:60]}')")
    left = _int_ir(node.left, depth)
    a = _int_value(node.left)
    if a is None:
        raise EncodeError("ST-UNDEC-001", f"{what} of an operand that is not a whole number as written ('{render(node.left)[:60]}')")
    if a < 0:
        raise EncodeError("ST-UNDEC-001", f"{what} of a negative number (languages round it differently)")
    return {"op": "mod" if node.op == "mod" else "idiv", "left": left, "right": {"op": "int", "value": str(b)}}


def _round_out(x: Fraction, direction: str) -> Fraction:
    """``x`` rounded outward to :data:`_ENC_DIGITS` significant decimal digits."""
    if x == 0:
        return x
    k = floor_log10(x)
    scale = Fraction(10) ** (_ENC_DIGITS - 1 - k)
    y = x * scale
    n = y.numerator // y.denominator
    if direction == "up" and n != y:
        n += 1
    return Fraction(n) / scale


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


def _ir_size(expr: dict) -> int:
    return sum(1 for _ in _walk_ir(expr))


def _has_free(node: Node, valued: dict) -> bool:
    """True when ``node`` holds a named function application or a symbol with no value domain in
    this problem (a free variable of an algebra step)."""
    for n in walk(node):
        if isinstance(n, Apply):
            return True
        if isinstance(n, Sym) and n.kind != "constant" and n.name not in valued:
            return True
    return False
