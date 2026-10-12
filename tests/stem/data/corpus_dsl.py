"""The item language of the STEM corpus builder: renderers per notation, steps, mutations.

An item is written once per notation by a template. Every relation the answer states is a
:class:`Step` with its exact substring of the answer, its kind and the value computation the
label rests on (``expr`` over a valuation ``v``: ``v("4.0")`` is the written number, a point for
correct-step labels and its widest interval for fault labels). Mutations are text
replacements with the fault class, the codes and check kinds that name it, and an exact proof.
No item text is evaluated: values come from the builder's own decimal strings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction as F
from typing import Callable, Optional

from corpus_lib import (TAU_MAX, Iv, W, acceptance, fails_widest, fmt, holds_point, leading_digit_slip, point, remap, round_sig,
                        widest)

SUP = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def sup(x) -> str:
    return str(x).translate(SUP)


def sub(x) -> str:
    return str(x).translate(SUB)


#: unit renderings: key -> (unicode, ascii, latex)
UNITS = {
    "m": ("m", "m", r"\text{m}"), "s": ("s", "s", r"\text{s}"), "kg": ("kg", "kg", r"\text{kg}"), "g": ("g", "g", r"\text{g}"),
    "N": ("N", "N", r"\text{N}"), "J": ("J", "J", r"\text{J}"), "kJ": ("kJ", "kJ", r"\text{kJ}"), "W": ("W", "W", r"\text{W}"),
    "kW": ("kW", "kW", r"\text{kW}"), "Pa": ("Pa", "Pa", r"\text{Pa}"), "kPa": ("kPa", "kPa", r"\text{kPa}"), "MPa": ("MPa", "MPa", r"\text{MPa}"),
    "V": ("V", "V", r"\text{V}"), "A": ("A", "A", r"\text{A}"), "ohm": ("Ω", "ohm", r"\Omega"), "Hz": ("Hz", "Hz", r"\text{Hz}"),
    "K": ("K", "K", r"\text{K}"), "mol": ("mol", "mol", r"\text{mol}"), "C": ("C", "C", r"\text{C}"), "km": ("km", "km", r"\text{km}"),
    "cm": ("cm", "cm", r"\text{cm}"), "mm": ("mm", "mm", r"\text{mm}"), "h": ("h", "h", r"\text{h}"), "min": ("min", "min", r"\text{min}"),
    "m/s": ("m s⁻¹", "m/s", r"\text{m s}^{-1}"), "m/s2": ("m s⁻²", "m/s^2", r"\text{m s}^{-2}"), "km/h": ("km h⁻¹", "km/h", r"\text{km h}^{-1}"),
    "kg m/s": ("kg m s⁻¹", "kg m/s", r"\text{kg m s}^{-1}"), "Ns": ("N s", "N s", r"\text{N s}"),
    "g/mol": ("g mol⁻¹", "g/mol", r"\text{g mol}^{-1}"), "mol/dm3": ("mol dm⁻³", "mol/dm^3", r"\text{mol dm}^{-3}"),
    "dm3": ("dm³", "dm^3", r"\text{dm}^{3}"), "cm3": ("cm³", "cm^3", r"\text{cm}^{3}"), "m3": ("m³", "m^3", r"\text{m}^{3}"),
    "m2": ("m²", "m^2", r"\text{m}^{2}"), "mm2": ("mm²", "mm^2", r"\text{mm}^{2}"), "kJ/mol": ("kJ mol⁻¹", "kJ/mol", r"\text{kJ mol}^{-1}"),
    "J/kgK": ("J kg⁻¹ K⁻¹", "J/(kg K)", r"\text{J kg}^{-1}\,\text{K}^{-1}"), "kg/m3": ("kg m⁻³", "kg/m^3", r"\text{kg m}^{-3}"),
    "J/molK": ("J mol⁻¹ K⁻¹", "J/(mol K)", r"\text{J mol}^{-1}\,\text{K}^{-1}"), "N/m2": ("N m⁻²", "N/m^2", r"\text{N m}^{-2}"),
    "kg/m2": ("kg m⁻²", "kg/m^2", r"\text{kg m}^{-2}"), "eV": ("eV", "eV", r"\text{eV}"), "Js": ("J s", "J s", r"\text{J s}"),
    "Nm": ("N m", "N m", r"\text{N m}"), "um": ("µm", "um", r"\mu\text{m}"), "nm": ("nm", "nm", r"\text{nm}"), "L": ("L", "L", r"\text{L}"),
    "mL": ("mL", "mL", r"\text{mL}"), "bit": ("bit", "bit", r"\text{bit}"), "B": ("B", "B", r"\text{B}"),
    "cm3/min": ("cm³ min⁻¹", "cm^3/min", r"\text{cm}^{3}\,\text{min}^{-1}"), "dm3/min": ("dm³ min⁻¹", "dm^3/min", r"\text{dm}^{3}\,\text{min}^{-1}"),
    "/min": ("min⁻¹", "min^-1", r"\text{min}^{-1}"), "mg": ("mg", "mg", r"\text{mg}"), "kWh": ("kW h", "kW h", r"\text{kW h}"),
    "MJ": ("MJ", "MJ", r"\text{MJ}"), "GPa": ("GPa", "GPa", r"\text{GPa}"), "N/mm2": ("N mm⁻²", "N/mm^2", r"\text{N mm}^{-2}"),
    "J/gK": ("J g⁻¹ K⁻¹", "J/(g K)", r"\text{J g}^{-1}\,\text{K}^{-1}"), "m/min": ("m min⁻¹", "m/min", r"\text{m min}^{-1}"),
    "/m2": ("m⁻²", "/m^2", r"\text{m}^{-2}"), "/yr": ("yr⁻¹", "/yr", r"\text{yr}^{-1}"), "yr": ("yr", "yr", r"\text{yr}"),
    "kJ/m2yr": ("kJ m⁻² yr⁻¹", "kJ/(m^2 yr)", r"\text{kJ m}^{-2}\,\text{yr}^{-1}"), "mol/L": ("mol L⁻¹", "mol/L", r"\text{mol L}^{-1}"),
}


@dataclass(frozen=True)
class R:
    """A renderer for one notation: ``unicode``, ``ascii``, ``latex`` (inline ``$…$``) or ``display`` (``\\[…\\]`` rows)."""
    nota: str

    @property
    def latex(self) -> bool:
        return self.nota in ("latex", "display")

    @property
    def ix(self) -> int:
        return {"unicode": 0, "ascii": 1, "latex": 2, "display": 2}[self.nota]

    def u(self, key: str) -> str:
        return UNITS[key][self.ix]

    def q(self, num: str, key: str) -> str:
        """A quantity: number and unit."""
        if self.latex:
            return f"{num}\\,{self.u(key)}"
        return f"{num} {self.u(key)}"

    @property
    def x(self) -> str:
        return {"unicode": " × ", "ascii": " * ", "latex": r" \times ", "display": r" \times "}[self.nota]

    @property
    def minus(self) -> str:
        return "−" if self.nota == "unicode" else "-"

    def neg(self, num: str) -> str:
        return (self.minus + num) if not num.startswith("-") else num

    def sci(self, mant: str, exp: int) -> str:
        if self.nota == "unicode":
            return f"{mant} × 10{sup(exp)}"
        if self.nota == "ascii":
            return f"{mant} x 10^{exp}"
        return f"{mant} \\times 10^{{{exp}}}"

    def sq(self, base: str, n: int = 2) -> str:
        if self.nota == "unicode":
            return f"{base}{sup(n)}"
        if self.nota == "ascii":
            return f"{base}^{n}"
        return f"{base}^{{{n}}}" if len(str(n)) > 1 else f"{base}^{n}"

    def frac(self, a: str, b: str) -> str:
        if self.latex:
            return f"\\frac{{{a}}}{{{b}}}"
        wrap = lambda s: f"({s})" if any(c in s for c in "+-−×*/ ") else s  # noqa: E731
        return f"{wrap(a)}/{wrap(b)}"

    def m(self, s: str) -> str:
        """Inline maths: ``$…$`` in LaTeX, as is otherwise."""
        return f"${s}$" if self.latex else s

    def sym(self, name: str, subscript: str = "") -> str:
        if self.latex:
            name = {"Δ": "\\Delta ", "λ": "\\lambda", "ρ": "\\rho", "θ": "\\theta", "σ": "\\sigma", "η": "\\eta", "ε": "\\varepsilon"}.get(name[:1], name[:1]) + name[1:] \
                if name[:1] in "ΔλρθσηεΔ" else name
        if not subscript:
            return name
        if self.latex or self.nota == "ascii":
            return f"{name}_{subscript}" if len(subscript) == 1 else f"{name}_{{{subscript}}}" if self.latex else f"{name}_{subscript}"
        return f"{name}{sub(subscript)}" if subscript.isdigit() else f"{name}_{subscript}"

    @property
    def half(self) -> str:
        return {"unicode": "½", "ascii": "0.5", "latex": r"\frac{1}{2}", "display": r"\frac{1}{2}"}[self.nota]

    @property
    def approx(self) -> str:
        return {"unicode": "≈", "ascii": "~", "latex": r"\approx", "display": r"\approx"}[self.nota]

    @property
    def arrow(self) -> str:
        return {"unicode": "⇒", "ascii": "=>", "latex": r"\Rightarrow", "display": r"\Rightarrow"}[self.nota]

    def sqrt(self, s: str) -> str:
        if self.latex:
            return f"\\sqrt{{{s}}}"
        if self.nota == "ascii":
            return f"sqrt({s})"
        return f"√({s})"

    def num(self, spec: str) -> str:
        """A decimal spec as written in this notation (a leading '-' becomes the notation's minus)."""
        return self.neg(spec[1:]) if spec.startswith("-") else spec


NOTATION_TAGS = {"unicode": "unicode", "ascii": "ascii", "latex": "latex_inline", "display": "latex_display"}


# ---------------------------------------------------------------------------------------------- steps
@dataclass
class Step:
    key: str
    text: str
    kind: str
    deps: tuple = ()
    expr: Optional[Callable] = None     # lambda v: <value>; v(spec, const=None)
    S: Optional[str] = None             # spec of the stated value
    S_text: Optional[str] = None        # how the stated value is written inside ``text`` (default: S)
    exact_work: bool = False
    proof: Optional[dict] = None        # for kinds without a numeric statement: a proof the builder computed
    sci: Optional[tuple] = None         # (mantissa spec, exponent, renderer) when S is written in scientific notation
    sign_ok: bool = True                # a sign mutation makes sense (C != 0)
    mutable: bool = True                # automatic mutations may target this step

    def stated(self) -> str:
        return self.S_text if self.S_text is not None else self.S


@dataclass
class Mut:
    cls: str
    target: str
    repl: list
    codes: tuple
    kinds: tuple
    proof: dict
    note: str
    affected: tuple = ()
    severity: str = "error"


@dataclass
class Item:
    id: str
    subject: str
    question: str
    response: str
    notation: list
    steps: list
    task_type: str = "short_answer"
    undecided: list = field(default_factory=list)  # (step text, codes, reason keyword)
    muts: list = field(default_factory=list)
    supplied: list = field(default_factory=list)
    auto: tuple = ("slip", "pow10", "sign", "round")  # automatic operators allowed on this item
    topic: str = ""
    r: Optional[R] = None
    #: the answer writes a unit the design's table does not hold (yr): its relations are checked as written only and a
    #: failure is INT-SUBJ-004 (section 6.4), so a numeric fault is named by INT-SUBJ-001 or INT-SUBJ-004
    unknown_units: bool = False

    def step(self, key: str) -> Step:
        return next(s for s in self.steps if s.key == key)


# ------------------------------------------------------------------------------------- step proofs
def numeric_proof(st: Step) -> dict:
    """The label of a correct numeric step: it holds at the written values (corpus_lib). A value that involves π, a
    logarithm or a root is an exact rational enclosure ``Iv`` and must hold at both of its ends."""
    C = st.expr(point)
    S = W(st.S, exact_int=st.exact_work)
    if isinstance(C, Iv):
        ok = holds_point(C.lo, S, exact_work=st.exact_work) and holds_point(C.hi, S, exact_work=st.exact_work)
        return {"rule": "holds at the written values for every value of the enclosure: |C - S| <= h(S), tau = 0", "C": [fmt(C.lo), fmt(C.hi)], "S": st.S,
                "h": fmt(S.h_narrow), "holds": ok}
    ok = holds_point(C, S, exact_work=st.exact_work)
    return {"rule": "holds at the written values: |C - S| <= h(S), tau = 0", "C": fmt(C), "S": st.S, "h": fmt(F(0) if st.exact_work else S.h_narrow),
            "holds": ok}


def fault_proof(expr: Callable, S_spec: str, v=widest) -> dict:
    """The label of a numeric fault: it fails over the widest reading (corpus_lib)."""
    C = expr(point)
    civ = expr(v)
    civ = Iv.of(civ)
    S = W(S_spec)
    ok = fails_widest(civ, S)
    lo, hi = acceptance(S.value, S.h_wide, TAU_MAX)
    shown = [fmt(C.lo), fmt(C.hi)] if isinstance(C, Iv) else fmt(C)
    return {"rule": "fails over the widest reading: no C in [C_lo, C_hi] lies in the band |C - S| <= h_wide(S) + |C|/20",
            "C": shown, "C_lo": fmt(civ.lo), "C_hi": fmt(civ.hi), "S": S_spec, "band": [fmt(lo), fmt(hi)], "fails": ok}


def mismatch_proof(a_spec: str, b_spec: str, what: str) -> dict:
    """Two written values that cannot be the same value: |a − b| > h_wide(a) + h_wide(b) (R7, R8)."""
    a, b = W(a_spec), W(b_spec)
    ok = abs(a.value - b.value) > a.h_wide + b.h_wide
    return {"rule": f"{what}: |a - b| > h_wide(a) + h_wide(b)", "a": a_spec, "b": b_spec, "diff": fmt(abs(a.value - b.value)),
            "h_sum": fmt(a.h_wide + b.h_wide), "fails": ok}


def scaled(spec: str, k: int) -> str:
    """The written number with its decimal point moved ``k`` places right (a power-of-ten slip), as a spec."""
    if "e" in spec:
        m, e = spec.split("e")
        return f"{m}e{int(e) + k}"
    sign = "-" if spec.startswith("-") else ""
    s = spec.lstrip("-")
    ip, _, fp = s.partition(".")
    digits = ip + fp
    point_at = len(ip) + k
    if point_at <= 0:
        digits = "0" * (1 - point_at) + digits
        point_at = 1
    if point_at >= len(digits):
        out = digits + "0" * (point_at - len(digits))
    else:
        out = digits[:point_at] + "." + digits[point_at:]
    out = out.lstrip("0") or "0"
    if out.startswith("."):
        out = "0" + out
    return sign + out


# ------------------------------------------------------------------------------- expression trees
# One tree renders the text of a formula or a substitution in a notation and computes its exact value
# over a valuation, so the text and the label can never disagree.
@dataclass(frozen=True)
class E:
    op: str            # num sym add sub mul div pow neg half frac paren
    args: tuple = ()
    val: str = ""      # num: decimal spec; sym: name; frac: "p/q"
    sub: str = ""      # sym subscript
    const: Optional[str] = None  # num: booklet value of a written constant
    implicit: bool = False       # mul: juxtaposition (symbols)


def N(spec: str, const: Optional[str] = None) -> E:
    return E("num", val=spec, const=const)


def S(name: str, subscript: str = "") -> E:
    return E("sym", val=name, sub=subscript)


def add(*xs: E) -> E:
    out = xs[0]
    for x in xs[1:]:
        out = E("add", (out, x))
    return out


def minus(a: E, b: E) -> E:
    return E("sub", (a, b))


def mul(*xs: E, implicit: bool = False) -> E:
    out = xs[0]
    for x in xs[1:]:
        out = E("mul", (out, x), implicit=implicit)
    return out


def div(a: E, b: E) -> E:
    return E("div", (a, b))


def pw(a: E, n: int) -> E:
    return E("pow", (a,), val=str(n))


def neg(a: E) -> E:
    return E("neg", (a,))


HALF_E = E("half")


def X(n: int) -> E:
    """An exact integer (a coefficient, the 1 of 1 − q, the 70 of the rule of 70): written as is, valued exactly."""
    return E("int", val=str(n))


def frac(p: int, q: int) -> E:
    return E("frac", val=f"{p}/{q}")


_PREC = {"add": 1, "sub": 1, "mul": 2, "div": 2, "neg": 3, "pow": 4, "num": 5, "sym": 5, "half": 5, "frac": 5, "int": 5}


def value(e: E, v, env: Optional[dict] = None):
    env = env or {}
    if e.op == "num":
        return v(e.val, const=e.const)
    if e.op == "sym":
        key = e.val + ("_" + e.sub if e.sub else "")
        return v(env[key])
    if e.op == "half":
        return F(1, 2)
    if e.op == "int":
        return F(int(e.val))
    if e.op == "frac":
        p, q = e.val.split("/")
        return F(int(p), int(q))
    if e.op == "neg":
        return -value(e.args[0], v, env)
    a = value(e.args[0], v, env)
    if e.op == "pow":
        return a ** int(e.val)
    b = value(e.args[1], v, env)
    return {"add": lambda: a + b, "sub": lambda: a - b, "mul": lambda: a * b, "div": lambda: a / b}[e.op]()


def subst(e: E, env: dict) -> E:
    """The tree with every symbol replaced by its value (a written substitution)."""
    if e.op == "sym":
        key = e.val + ("_" + e.sub if e.sub else "")
        return N(env[key])
    if not e.args:
        return e
    return E(e.op, tuple(subst(a, env) for a in e.args), e.val, e.sub, e.const, e.implicit if e.op != "mul" else False)


def _prec(e: E) -> int:
    if e.op == "num" and "e" in e.val:
        return 2  # a number in scientific notation is a product: 3.0 × 10⁸
    return _PREC[e.op]


def render(e: E, r: R, parent: int = 0, right: bool = False, parent_op: str = "") -> str:
    """The text of ``e`` in notation ``r``; a child is wrapped in parentheses only when precedence needs it
    (a right operand of a non-associative operator at equal precedence, any product as a divisor)."""
    p = _prec(e)
    s = _render(e, r, p)
    wrap = p < parent or (right and p == parent and parent_op in ("sub", "div"))
    if right and parent_op == "div" and e.op == "mul":
        wrap = True
    if wrap and not (r.latex and parent_op == "div"):
        return f"({s})"
    return s


def _render(e: E, r: R, p: int) -> str:
    if e.op == "num":
        if "e" in e.val:
            m, x = e.val.split("e")
            return r.sci(r.num(m), int(x))
        return r.num(e.val)
    if e.op == "sym":
        return r.sym(e.val, e.sub)
    if e.op == "int":
        return e.val
    if e.op == "half":
        return {"unicode": "½", "ascii": "(1/2)", "latex": r"\frac{1}{2}", "display": r"\frac{1}{2}"}[r.nota]
    if e.op == "frac":
        a, b = e.val.split("/")
        return f"\\frac{{{a}}}{{{b}}}" if r.latex else f"({a}/{b})"
    if e.op == "neg":
        return r.minus + render(e.args[0], r, p, parent_op="neg")
    if e.op == "pow":
        base = render(e.args[0], r, 5, parent_op="pow")
        return r.sq(base, int(e.val))
    a, b = e.args
    if e.op == "div" and r.latex:
        return f"\\frac{{{render(a, r)}}}{{{render(b, r)}}}"
    la, rb = render(a, r, p, parent_op=e.op), render(b, r, p, right=True, parent_op=e.op)
    if e.op == "div":
        return f"{la}/{rb}"
    if e.op == "mul":
        if e.implicit:
            return f"{la} {rb}" if r.latex and re.search(r"\\[A-Za-z]+$", la) else f"{la}{rb}"
        return f"{la}{r.x}{rb}"
    if e.op == "add":
        return f"{la} + {rb}"
    return f"{la} {r.minus if r.nota == 'unicode' else '-'} {rb}"


def disjoint_proof(a: Iv, b: Iv, what: str) -> dict:
    """Two computed sides that no admissible reading brings together: [a] widened by |a|/20 misses [b]."""
    big = max(abs(a.lo), abs(a.hi))
    lo, hi = a.lo - TAU_MAX * big, a.hi + TAU_MAX * big
    ok = hi < b.lo or lo > b.hi
    return {"rule": f"{what}: the interval of one side, widened by 1/20 of its magnitude, misses the other side's interval",
            "a": [fmt(a.lo), fmt(a.hi)], "b": [fmt(b.lo), fmt(b.hi)], "fails": ok}


def sig_figs(spec: str) -> int:
    m = spec.split("e")[0].lstrip("-")
    digits = m.replace(".", "").lstrip("0")
    return max(1, len(digits))


def walk(e: E):
    yield e
    for a in e.args:
        yield from walk(a)


def replace_node(e: E, target: E, new: Optional[E]) -> E:
    """``e`` with the first node identical (by identity) to ``target`` replaced by ``new`` (``None`` drops a factor of a product)."""
    if e is target:
        return new
    if not e.args:
        return e
    args = []
    done = False
    for a in e.args:
        if not done and any(x is target for x in walk(a)):
            na = replace_node(a, target, new)
            done = True
            args.append(na)
        else:
            args.append(a)
    if e.op == "mul" and any(x is None for x in args):
        rest = [x for x in args if x is not None]
        return rest[0]
    return E(e.op, tuple(args), e.val, e.sub, e.const, e.implicit)
