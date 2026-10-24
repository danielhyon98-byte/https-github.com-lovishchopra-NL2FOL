"""Hand-written STEM corpus items: algebra, roots, logarithms, surds, sequences, inequalities, calculus
(a definite integral of a polynomial checked since STEM repair 10, a derivative of one since STEM repair 11), percentages, conversions, comparisons, show-that targets, chemical equations,
Boolean identities, truth tables and based numerals, in mixed notations.

Every label is computed here from data the builder writes: exact ``Fraction`` arithmetic, exact
element and charge tallies of species written as data, Boolean functions enumerated over every
assignment, polynomial identities compared at more points than their degree, integer comparisons
for logarithm bounds. No item text is read for meaning.
"""
from __future__ import annotations

from fractions import Fraction as F
from typing import Callable, Optional

from corpus_dsl import Item, Mut, R, Step, fault_proof, mismatch_proof, numeric_proof
from corpus_items import ITEMS, add_item, catalogue, holds, mut, tags
from corpus_lib import Iv, W, fmt, isqrt_iv, point, widest

MATH_AA = "Mathematics: Analysis and Approaches"
MATH_AI = "Mathematics: Applications and Interpretation"
CS = "Computer Science"
PHYS, CHEM, BIO = "Physics", "Chemistry", "Biology"
ESS = "Environmental Systems and Societies"
SEHS = "Sports, Exercise and Health Science"
DT = "Design Technology"

#: π as an exact rational enclosure (its decimal expansion to 15 places, ± one unit): the corpus never evaluates π
PI = Iv(F("3.141592653589793"), F("3.141592653589794"))


def item(ident: str, subject: str, topic: str, nota: str, question: str, response: str, steps: list[Step], muts=(), undecided=(), auto=(),
         extra_tags=()) -> Item:
    it = Item(ident, subject, question, response, tags(R(nota), *extra_tags), steps, r=R(nota), topic=topic, auto=tuple(auto),
              undecided=list(undecided))
    it.muts.extend(muts)
    return add_item(it)


def eq(key: str, text: str, expr: Callable, S: str, *, S_text: Optional[str] = None, deps=(), exact=False, sci=None, kind="eq", mutable=True) -> Step:
    return Step(key, text, kind, deps=tuple(deps), expr=expr, S=S, S_text=S_text, exact_work=exact, sci=sci, mutable=mutable)


def other(key: str, text: str, kind: str, proof: dict, deps=()) -> Step:
    return Step(key, text, kind, deps=tuple(deps), proof=dict(proof, holds=proof.get("holds", True)))


# ------------------------------------------------------------------------------------------ exact proofs
def poly(coeffs: list[F], x: F) -> F:
    out = F(0)
    for c in coeffs:
        out = out * x + c
    return out


def identity_proof(f: Callable[[F], F], g: Callable[[F], F], degree: int) -> dict:
    """Two polynomials of degree at most ``degree`` are identical iff they agree at ``degree + 1`` points."""
    pts = [F(k) for k in range(-2, degree + 2)]
    diffs = [(fmt(x), fmt(f(x) - g(x))) for x in pts]
    same = all(f(x) == g(x) for x in pts)
    return {"rule": f"two polynomials of degree <= {degree} agree everywhere iff they agree at {degree + 1} points", "points": diffs,
            "holds": same, "fails": not same}


def derivative_proof(coeffs: list[F], stated: list[F]) -> dict:
    """STEM repair 11: the derivative of the polynomial with ``coeffs`` (highest power first) by the power rule, against the stated
    derivative's coefficients, compared as polynomials at more points than their degree."""
    n = len(coeffs) - 1
    formed = [c * (n - i) for i, c in enumerate(coeffs[:-1])]
    degree = max(len(formed), len(stated)) - 1
    proof = identity_proof(lambda x: poly(formed, x), lambda x: poly(stated, x), max(degree, 0))
    return dict(proof, rule="the derivative by the power rule (" + ", ".join(fmt(c) for c in formed) + ", highest power first) against the stated "
                            "derivative: " + proof["rule"])


def roots_proof(coeffs: list[F], stated: list[F], all_roots: list[F]) -> dict:
    ok_members = all(poly(coeffs, r) == 0 for r in stated)
    missing = [r for r in all_roots if poly(coeffs, r) == 0 and r not in stated]
    return {"rule": "each stated root satisfies the polynomial exactly; a real root left out makes the stated set incomplete",
            "stated": [fmt(r) for r in stated], "missing": [fmt(r) for r in missing], "holds": ok_members and not missing,
            "fails": bool(missing) or not ok_members}


def step_proof(premise: Callable[[dict], bool], conclusion: Callable[[dict], bool], witness: dict) -> dict:
    """A step that does not follow: a witness satisfies the premise and refutes the conclusion."""
    p, c = premise(witness), conclusion(witness)
    return {"rule": "a witness satisfies the preceding relation and refutes the stated step", "witness": {k: fmt(v) for k, v in witness.items()},
            "premise": p, "conclusion": c, "fails": p and not c}


def cmp_proof(a: str, op: str, b: str) -> dict:
    x, y = W(a).value, W(b).value
    val = {"<": x < y, ">": x > y, "≤": x <= y, "≥": x >= y}[op]
    return {"rule": "an exact comparison of the written values (R6)", "a": a, "op": op, "b": b, "holds": val, "fails": not val}


def tally(side: list[tuple[int, dict, int]]) -> tuple[dict, int]:
    atoms: dict[str, F] = {}
    charge = F(0)
    for coef, comp, q in side:
        for el, n in comp.items():
            atoms[el] = atoms.get(el, F(0)) + F(coef) * n
        charge += F(coef) * q
    return atoms, charge


def chem_proof(left, right) -> dict:
    la, lq = tally(left)
    ra, rq = tally(right)
    same = la == ra and lq == rq
    return {"rule": "element and charge tallies of both sides, from the species written as data", "left": {k: fmt(v) for k, v in sorted(la.items())},
            "right": {k: fmt(v) for k, v in sorted(ra.items())}, "charge": [fmt(lq), fmt(rq)], "holds": same, "fails": not same}


def assignments(names: list[str]):
    for k in range(2 ** len(names)):
        yield {n: bool((k >> (len(names) - 1 - i)) & 1) for i, n in enumerate(names)}


def bool_proof(f, g, names: list[str]) -> dict:
    diff = next((a for a in assignments(names) if f(a) != g(a)), None)
    return {"rule": "both sides enumerated over every assignment", "distinguishing": None if diff is None else {k: int(v) for k, v in diff.items()},
            "holds": diff is None, "fails": diff is not None}


def table_proof(rows: list[tuple], f, n_in: int) -> dict:
    bad = [r for r in rows if bool(r[n_in]) != f(*[bool(x) for x in r[:n_in]])]
    return {"rule": "each stated output row against the expression", "wrong_rows": [list(r) for r in bad], "holds": not bad, "fails": bool(bad)}


def base_proof(digits: str, base: int, stated: int) -> dict:
    v = int(digits, base)
    return {"rule": "positional value of the digits", "digits": digits, "base": base, "value": v, "stated": stated, "holds": v == stated, "fails": v != stated}


def table_text(header: list[str], rows: list[tuple]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(int(x)) for x in r) + " |" for r in rows]
    return "\n".join(out)


# ======================================================================================= MATHEMATICS AA
for _k, (_nota, _p, _q) in enumerate([("unicode", 3, 4), ("latex", 2, 5), ("ascii", -1, 6), ("display", 1, -3)]):
    r = R(_nota)
    b, c = -(_p + _q), _p * _q
    coeffs = [F(1), F(b), F(c)]

    def term(v: int, rr: R = r) -> str:
        return f"(x {'+' if v < 0 else rr.minus if rr.nota == 'unicode' else '-'} {abs(v)})"

    def lin(coef: int, rr: R = r) -> str:
        if coef == 0:
            return ""
        sign = "+" if coef > 0 else (rr.minus if rr.nota == "unicode" else "-")
        return f" {sign} {abs(coef) if abs(coef) != 1 else ''}x"

    const = f" {'+' if c > 0 else (r.minus if r.nota == 'unicode' else '-')} {abs(c)}"
    poly_t = f"{r.sq('x', 2)}{lin(b)}{const}"
    fact_t = f"{term(_p)}{term(_q)}"
    root = lambda v, rr=r: f"x = {rr.num(str(v))}"  # noqa: E731
    roots_plain = f"{root(_p)} or {root(_q)}"
    if _nota == "unicode" or _nota == "ascii":
        resp = f"Factorising, {poly_t} = {fact_t} = 0, so the solutions are {roots_plain}."
        sol_t = f"the solutions are {roots_plain}"
        lost = f"the solutions are {root(_p)}"
    elif _nota == "latex":
        resp = f"Factorising, ${poly_t} = {fact_t} = 0$, so the solutions are ${root(_p)}$ or ${root(_q)}$."
        sol_t = f"the solutions are ${root(_p)}$ or ${root(_q)}$"
        lost = f"the solutions are ${root(_p)}$"
    else:
        resp = f"Factorising:\n\\[ {poly_t} = {fact_t} = 0 \\]\nso the solutions are ${root(_p)}$ or ${root(_q)}$."
        sol_t = f"the solutions are ${root(_p)}$ or ${root(_q)}$"
        lost = f"the solutions are ${root(_p)}$"
    fact_step = f"{poly_t} = {fact_t}"
    P = lambda x, cs=coeffs: poly(cs, x)  # noqa: E731
    Q = lambda x, p=_p, q=_q: (x - p) * (x - q)  # noqa: E731
    wrong_fact = f"{term(_p)}{term(-_q)}"
    Q2 = lambda x, p=_p, q=_q: (x - p) * (x + q)  # noqa: E731
    item(f"math-quad-{_k + 1}", MATH_AA, "quadratics", _nota, f"Solve x² {'+' if b >= 0 else '−'} {abs(b)}x {'+' if c >= 0 else '−'} {abs(c)} = 0.", resp,
         [other("fact", fact_step, "alg", identity_proof(P, Q, 2)),
          other("sol", sol_t, "sol", roots_proof(coeffs, [F(_p), F(_q)], [F(_p), F(_q)]), deps=("fact",))],
         muts=[mut("lost_root", "sol", [(sol_t, lost)], roots_proof(coeffs, [F(_p)], [F(_p), F(_q)]), f"the root x = {_q} was left out of the stated solutions"),
               mut("wrong_rearrangement", "fact", [(fact_t, wrong_fact, fact_step)], identity_proof(P, Q2, 2),
                   f"the factorisation has the sign of {_q} flipped; the stated roots still solve the original equation", affected=("sol",))])

for _k, (_nota, _a, _b, _c) in enumerate([("unicode", 3, 5, 20), ("latex", 4, -7, 9), ("ascii", 2, 9, 1)]):
    r = R(_nota)
    m = r.minus if r.nota == "unicode" else "-"
    rhs1 = _c - _b
    x = F(rhs1, _a)
    arrow = r.arrow
    lhs0 = f"{_a}x {'+' if _b > 0 else m} {abs(_b)} = {_c}"
    s1 = f"{_a}x = {r.num(str(rhs1))}"
    s2 = f"x = {r.num(str(x))}"
    wrong1 = rhs1 + 2 * _b if _b > 0 else rhs1 + 2 * _b
    w1 = f"{_a}x = {r.num(str(wrong1))}"
    w2v = F(wrong1, _a)
    w2 = f"x = {r.num(str(w2v.numerator)) if w2v.denominator == 1 else str(w2v.numerator) + '/' + str(w2v.denominator)}"
    body = f"{lhs0} {arrow} {s1} {arrow} {s2}"
    resp = f"${body}$" if r.latex else body
    prem = lambda d, a=_a, bb=_b, cc=_c: a * d["x"] + bb == cc  # noqa: E731
    concl = lambda d, a=_a, w=wrong1: a * d["x"] == w  # noqa: E731
    item(f"math-linear-{_k + 1}", MATH_AA, "equations", _nota, f"Solve {_a}x {'+' if _b > 0 else '−'} {abs(_b)} = {_c}.", resp,
         [other("s1", s1, "alg", {"rule": "the step follows exactly", "check": f"{_a}x + {_b} = {_c} iff {_a}x = {rhs1}"}),
          other("s2", s2, "alg", {"rule": "the step follows exactly", "check": f"x = {fmt(x)}"}, deps=("s1",))],
         muts=[mut("wrong_rearrangement", "s1", [(s1, w1, body), (s2, w2, body)], step_proof(prem, concl, {"x": x}),
                   f"the constant {_b} moved across without changing its sign: {_a}x = {wrong1}", affected=("s2",))])

for _k, (_nota, _prem, _good, _bad, _wit, _P, _C) in enumerate([
        ("unicode", "v = u + at", "t = (v − u)/a", "t = (v + u)/a", {"u": F(1), "a": F(2), "t": F(3), "v": F(7)},
         lambda d: d["v"] == d["u"] + d["a"] * d["t"], lambda d: d["t"] == (d["v"] + d["u"]) / d["a"]),
        ("latex", "A = \\frac{1}{2}bh", "h = \\frac{2A}{b}", "h = \\frac{A}{2b}", {"b": F(4), "h": F(3), "A": F(6)},
         lambda d: d["A"] == F(1, 2) * d["b"] * d["h"], lambda d: d["h"] == d["A"] / (2 * d["b"]))]):
    r = R(_nota)
    body = f"{_prem} {r.arrow} {_good}"
    resp = f"Making the new subject: {'$' + body + '$' if r.latex else body}."
    item(f"math-rearrange-{_k + 1}", MATH_AA, "algebra", _nota, "Make the stated symbol the subject of the formula.", resp,
         [other("step", _good, "alg", {"rule": "the rearrangement is an equivalence for non-zero divisors"})],
         muts=[mut("wrong_rearrangement", "step", [(_good, _bad)], step_proof(_P, _C, _wit), f"the rearranged formula is wrong: {_bad}")])

item("math-log-1", MATH_AA, "logarithms", "latex", "Evaluate log₁₀ 1000 exactly.", "$\\log_{10} 1000 = 3$ because $10^3 = 1000$.",
     [eq("log", "\\log_{10} 1000 = 3", lambda v: F(3), "3", exact=True), eq("pow", "10^3 = 1000", lambda v: F(1000), "1000", exact=True)], auto=("slip",))
item("math-log-2", MATH_AA, "logarithms", "unicode", "Evaluate log 0.01 and ln 1 exactly.", "log 0.01 = −2 and ln 1 = 0.",
     [eq("log", "log 0.01 = −2", lambda v: F(-2), "-2", S_text="−2", exact=True), eq("ln", "ln 1 = 0", lambda v: F(0), "0", exact=True)], auto=("slip",))

_surd1 = {"rule": "(5√2)² = 50 and both sides are non-negative", "holds": True}
item("math-surd-1", MATH_AA, "surds", "unicode", "Simplify √50.", "√50 = √(25 × 2) = 5√2",
     [other("s", "√(25 × 2) = 5√2", "eq", _surd1)],
     muts=[mut("arithmetic_slip", "s", [("5√2", "2√5")], {"rule": "(2√5)² = 20, not 50: the two non-negative sides differ", "fails": True},
               "√50 simplified as 2√5", kinds=("eq",))])
item("math-surd-2", MATH_AA, "surds", "latex", "Simplify √12 + √27.", "$\\sqrt{12} + \\sqrt{27} = 2\\sqrt{3} + 3\\sqrt{3} = 5\\sqrt{3}$",
     [other("a", "\\sqrt{12} + \\sqrt{27} = 2\\sqrt{3} + 3\\sqrt{3}", "eq", {"rule": "(2√3)² = 12 and (3√3)² = 27"}),
      other("b", "2\\sqrt{3} + 3\\sqrt{3} = 5\\sqrt{3}", "eq", {"rule": "2 + 3 = 5"})],
     muts=[mut("arithmetic_slip", "b", [("= 5\\sqrt{3}", "= 6\\sqrt{3}")], {"rule": "2√3 + 3√3 = 5√3 ≠ 6√3 since √3 ≠ 0", "fails": True},
               "the coefficients summed to 6", kinds=("eq",))])

item("math-seq-1", MATH_AA, "sequences", "unicode", "An arithmetic sequence has u₁ = 3 and d = 4. Find u₁₀.", "u₁₀ = u₁ + 9d = 3 + 9 × 4 = 39",
     [eq("e", "3 + 9 × 4 = 39", lambda v: F(3) + 9 * F(4), "39", exact=True)], auto=("slip", "sign"))
item("math-seq-2", MATH_AA, "sequences", "latex", "An arithmetic sequence has u₁ = 3 and d = 4. Find S₁₀.",
     "$S_{10} = \\frac{10}{2}(2 \\times 3 + 9 \\times 4) = 210$", [eq("e", "\\frac{10}{2}(2 \\times 3 + 9 \\times 4) = 210", lambda v: F(5) * (6 + 36), "210", exact=True)],
     auto=("slip", "pow10"))
item("math-geo-1", MATH_AA, "sequences", "unicode", "A geometric sequence has u₁ = 2 and r = 3. Find u₆ and S₅.",
     "u₆ = 2 × 3⁵ = 486 and S₅ = 2(3⁵ − 1)/(3 − 1) = 242.",
     [eq("u6", "2 × 3⁵ = 486", lambda v: F(2) * 3 ** 5, "486", exact=True), eq("s5", "2(3⁵ − 1)/(3 − 1) = 242", lambda v: F(2) * (3 ** 5 - 1) / 2, "242", exact=True)],
     auto=("slip", "sign"))
item("math-coord-1", MATH_AA, "coordinate geometry", "ascii", "Find the gradient of the line through (1, 3) and (5, 7).", "m = (7 - 3)/(5 - 1) = 4/4 = 1",
     [eq("a", "(7 - 3)/(5 - 1) = 4/4", lambda v: F(1), "1", S_text="4/4", exact=True, mutable=False), eq("b", "4/4 = 1", lambda v: F(1), "1", exact=True)], auto=("slip",))
item("math-coord-2", MATH_AA, "coordinate geometry", "latex", "Find the distance between (1, 3) and (5, 7).",
     "$d = \\sqrt{(5 - 1)^2 + (7 - 3)^2} = \\sqrt{32} \\approx 5.66$",
     [eq("d", "\\sqrt{32} \\approx 5.66", lambda v: isqrt_iv(Iv(F(32), F(32))), "5.66")], auto=("slip",))
item("math-index-1", MATH_AA, "indices", "unicode", "Simplify 2³ × 2⁴ and evaluate it.", "2³ × 2⁴ = 2⁷ = 128",
     [eq("a", "2³ × 2⁴ = 2⁷", lambda v: F(2) ** 7, "128", S_text="2⁷", exact=True, mutable=False), eq("b", "2⁷ = 128", lambda v: F(128), "128", exact=True)], auto=("slip",))
item("math-frac-1", MATH_AA, "fractions", "unicode", "Add 2/3 and 1/4.", "2/3 + 1/4 = 8/12 + 3/12 = 11/12",
     [other("a", "2/3 + 1/4 = 8/12 + 3/12", "eq", {"rule": "8/12 = 2/3 and 3/12 = 1/4 exactly"}),
      other("b", "8/12 + 3/12 = 11/12", "eq", {"rule": "8 + 3 = 11 over 12"})],
     muts=[mut("arithmetic_slip", "b", [("= 11/12", "= 11/24")], {"rule": "8/12 + 3/12 = 11/12 ≠ 11/24 (exact)", "fails": True}, "the denominators were added",
               kinds=("eq",))])
item("math-frac-2", MATH_AA, "fractions", "latex", "Multiply 3/4 by 2/9.", "$\\frac{3}{4} \\times \\frac{2}{9} = \\frac{6}{36} = \\frac{1}{6}$",
     [other("a", "\\frac{3}{4} \\times \\frac{2}{9} = \\frac{6}{36}", "eq", {"rule": "3 × 2 = 6, 4 × 9 = 36"}),
      other("b", "\\frac{6}{36} = \\frac{1}{6}", "eq", {"rule": "6/36 = 1/6 exactly"})],
     muts=[mut("arithmetic_slip", "b", [("= \\frac{1}{6}", "= \\frac{1}{9}")], {"rule": "6/36 = 1/6 ≠ 1/9 (exact)", "fails": True}, "6/36 reduced to 1/9", kinds=("eq",))])

for _k, (_nota, _text, _good, _bad, _wit, _P, _C) in enumerate([
        ("unicode", "2x − 3 < 7 ⇒ 2x < 10 ⇒ x < 5", "x < 5", "x > 5", {"x": F(0)}, lambda d: 2 * d["x"] - 3 < 7, lambda d: d["x"] > 5),
        ("latex", "$5 - x \\geq 2 \\Rightarrow -x \\geq -3 \\Rightarrow x \\leq 3$", "x \\leq 3", "x \\geq 3", {"x": F(0)}, lambda d: 5 - d["x"] >= 2,
         lambda d: d["x"] >= 3)]):
    item(f"math-ineq-{_k + 1}", MATH_AA, "inequalities", _nota, "Solve the inequality.", _text,
         [other("step", _good, "cmp", {"rule": "the inequality step is an equivalence (dividing by a negative number reverses the sign)"})],
         muts=[mut("wrong_comparison", "step", [(_good, _bad, _text, "last")], step_proof(_P, _C, _wit), f"the inequality sign of the last step is reversed: {_bad}")])

# calculus and other notation outside the encodings: named undecided; the arithmetic beside them is decided.
# STEM repair 11 (rule derivative): the derivative a polynomial's answer states is set against the derivative the power rule forms, so it is
# decided now (before: named undecided, 'derivative'); its label is computed here from the coefficients the builder writes
item("math-calc-1", MATH_AA, "calculus", "unicode", "Find f′(2) for f(x) = x³ − 2x.", "For f(x) = x³ − 2x, f′(x) = 3x² − 2, so f′(2) = 3 × 2² − 2 = 10.",
     [other("der", "f′(x) = 3x² − 2", "alg", derivative_proof([F(1), F(0), F(-2), F(0)], [F(3), F(0), F(-2)])),
      eq("e", "3 × 2² − 2 = 10", lambda v: F(3) * 4 - 2, "10", exact=True)], auto=("slip", "sign"))
# STEM repair 10 (rule definite-integral): a definite integral of a polynomial with whole-number limits set against the evaluation bracket of
# the antiderivative it states is the antiderivative check between the same limits, and the bracket at its limits is arithmetic; both are
# decided now (before: named undecided, 'integral'), each label computed here
item("math-calc-2", MATH_AA, "calculus", "latex", "Evaluate the integral of 3x² from 0 to 2.", "$\\int_0^2 3x^2\\,dx = [x^3]_0^2 = 8 - 0 = 8$",
     [other("int", "\\int_0^2 3x^2\\,dx = [x^3]_0^2", "alg",
            dict(identity_proof(lambda x: 3 * x * x, lambda x: 3 * x ** 2, 2),
                 rule="the derivative of the stated antiderivative x³ (3x², by the power rule) agrees with the integrand 3x² at 3 points (polynomials "
                      "of degree <= 2), and both sides integrate between 0 and 2")),
      other("ev", "[x^3]_0^2 = 8 - 0", "eq", {"rule": "the bracket at its limits, 2³ − 0³, against 8 − 0 (exact)", "computed": fmt(F(2) ** 3 - F(0) ** 3),
                                             "stated": fmt(F(8) - F(0)), "holds": F(2) ** 3 - F(0) ** 3 == F(8) - F(0)}),
      eq("e", "8 - 0 = 8", lambda v: F(8), "8", exact=True)], auto=("slip",))
item("math-count-1", MATH_AA, "counting", "unicode", "In how many orders can five books be arranged?", "The number of orders is 5! = 5 × 4 × 3 × 2 × 1 = 120.",
     [eq("e", "5 × 4 × 3 × 2 × 1 = 120", lambda v: F(120), "120", exact=True)], undecided=[("5! = 5 × 4 × 3 × 2 × 1", ("ST-UNDEC-001",), "factorial")],
     auto=("slip",))
item("math-sum-1", MATH_AA, "series", "latex", "Evaluate the sum of k² for k = 1 to 4.", "$\\sum_{k=1}^{4} k^2 = 1 + 4 + 9 + 16 = 30$",
     [other("sig", "\\sum_{k=1}^{4} k^2 = 1 + 4 + 9 + 16", "eq", {"rule": "the terms k² for k = 1..4 are 1, 4, 9, 16"}),
      eq("e", "1 + 4 + 9 + 16 = 30", lambda v: F(30), "30", exact=True)],
     muts=[mut("arithmetic_slip", "sig", [("k^2", "k^3", "\\sum_{k=1}^{4} k^2")], {"rule": "Σ k³ for k = 1..4 is 100, not 1 + 4 + 9 + 16 = 30 (exact)", "fails": True},
               "the summand was written k³ while the terms are those of k²", kinds=("eq",))], auto=("slip",))
item("math-sum-2", MATH_AA, "series", "unicode", "Find the sum of the first five odd numbers.", "Σ_{k=1}^{5} (2k − 1) = 1 + 3 + 5 + 7 + 9 = 25",
     [other("sig", "Σ_{k=1}^{5} (2k − 1) = 1 + 3 + 5 + 7 + 9", "eq", {"rule": "the terms 2k − 1 for k = 1..5 are 1, 3, 5, 7, 9"}),
      eq("e", "1 + 3 + 5 + 7 + 9 = 25", lambda v: F(25), "25", exact=True)], auto=("slip",))

# ======================================================================================= MATHEMATICS AI
item("mai-pct-1", MATH_AI, "percentages", "unicode", "A price rose from 40 to 46. Calculate the percentage increase.",
     "Percentage increase = (46 − 40)/40 × 100 = 15%. The increase is therefore 15%.",
     [eq("e", "(46 − 40)/40 × 100 = 15%", lambda v: (v("46") - v("40")) / v("40") * 100, "15", S_text="15"),
      eq("res", "therefore 15%", lambda v: v("15"), "15", S_text="15", deps=("e",), kind="res")], auto=("slip", "sign"))
item("mai-pct-2", MATH_AI, "percentages", "latex", "A population fell from 65 to 52. Calculate the percentage change.",
     "$\\frac{52 - 65}{65} \\times 100 = -20\\%$", [eq("e", "\\frac{52 - 65}{65} \\times 100 = -20\\%", lambda v: (v("52") - v("65")) / v("65") * 100, "-20",
                                                       S_text="-20")], auto=("slip",))
item("mai-ci-1", MATH_AI, "finance", "unicode", "1000 euros is invested at 5% compound interest for 3 years. Find the final value.", "FV = 1000 × 1.05³ = 1157.63",
     [eq("e", "1000 × 1.05³ = 1157.63", lambda v: F(1000) * F("1.05") ** 3, "1157.63")], auto=("slip", "pow10", "round"))
item("mai-ci-2", MATH_AI, "finance", "ascii", "2500 euros is invested at 4% compound interest for 5 years. Find the final value.", "FV = 2500 * 1.04^5 = 3041.63",
     [eq("e", "2500 * 1.04^5 = 3041.63", lambda v: F(2500) * F("1.04") ** 5, "3041.63")], auto=("slip", "pow10"))
item("mai-mean-1", MATH_AI, "statistics", "unicode", "Find the mean of 12, 15, 18 and 21.", "mean = (12 + 15 + 18 + 21)/4 = 66/4 = 16.5",
     [eq("a", "(12 + 15 + 18 + 21)/4 = 66/4", lambda v: F(66, 4), "66/4", S_text="66/4", exact=True), eq("b", "66/4 = 16.5", lambda v: F(66, 4), "16.5")],
     auto=("slip",))
item("mai-circle-1", MATH_AI, "geometry", "unicode", "Find the area of a circle of radius 3.0 cm.", "A = πr² = π × 3.0² = 28.3 cm²",
     [eq("e", "π × 3.0² = 28.3 cm²", lambda v: PI * F("9.00") if v is point else Iv.of(v("3.0")) * Iv.of(v("3.0")) * PI, "28.3", S_text="28.3")],
     auto=("slip", "pow10"))
item("mai-cyl-1", MATH_AI, "geometry", "latex", "Find the volume of a cylinder of radius 2.0 cm and height 5.0 cm.",
     "$V = \\pi r^2 h = \\pi \\times 2.0^2 \\times 5.0 = 62.8\\,\\text{cm}^{3}$",
     [eq("e", "\\pi \\times 2.0^2 \\times 5.0 = 62.8\\,\\text{cm}^{3}", lambda v: PI * 20 if v is point else Iv.of(v("2.0")) * Iv.of(v("2.0")) * Iv.of(v("5.0")) * PI,
         "62.8")], auto=("slip",))
item("mai-pyth-1", MATH_AI, "geometry", "unicode", "Find the hypotenuse of a right triangle with sides 6.0 m and 8.0 m.", "c = √(6.0² + 8.0²) = √100 = 10.0 m",
     [eq("a", "√(6.0² + 8.0²) = √100", lambda v: F(10), "10", S_text="√100", mutable=False), eq("b", "√100 = 10.0 m", lambda v: F(10), "10.0")], auto=("slip", "pow10"))
item("mai-trig-1", MATH_AI, "trigonometry", "unicode", "A 10 N force acts at 60° to the horizontal. Find its horizontal component.", "F_x = F cos θ = 10 cos 60° = 5.0 N",
     [eq("e", "10 cos 60° = 5.0 N", lambda v: F(5), "5.0")], auto=("slip", "sign"))
item("mai-trig-2", MATH_AI, "trigonometry", "latex", "A ladder of length 8.0 m makes 30° with the ground. Find the height it reaches.",
     "$h = 8.0 \\sin 30^{\\circ} = 4.0\\,\\text{m}$", [eq("e", "8.0 \\sin 30^{\\circ} = 4.0\\,\\text{m}", lambda v: v("8.0") / 2, "4.0")], auto=("slip",))
item("mai-sci-1", MATH_AI, "standard form", "unicode", "Multiply 3.2 × 10⁴ by 2.0 × 10³.", "(3.2 × 10⁴) × (2.0 × 10³) = 6.4 × 10⁷",
     [eq("e", "(3.2 × 10⁴) × (2.0 × 10³) = 6.4 × 10⁷", lambda v: v("3.2e4") * v("2.0e3"), "6.4e7", S_text="6.4 × 10⁷", sci=("6.4", 7, R("unicode")))],
     auto=("slip", "pow10"))

# ========================================================================================== CONVERSIONS
for _ident, _subj, _nota, _q, _resp, _text, _C, _S, _St, _wrong, _wS in [
        ("phys-cnv-1", PHYS, "unicode", "Convert 72 km h⁻¹ into m s⁻¹.", "The speed is 72 km h⁻¹ = 20 m s⁻¹.", "72 km h⁻¹ = 20 m s⁻¹", F(20), "20", "20",
         "= 25 m s⁻¹", "25"),
        ("chem-cnv-1", CHEM, "unicode", "Convert 25.0 cm³ into dm³.", "The volume is 25.0 cm³ = 0.0250 dm³.", "25.0 cm³ = 0.0250 dm³", F("0.025"), "0.0250", "0.0250",
         "= 0.250 dm³", "0.250"),
        ("phys-cnv-2", PHYS, "unicode", "Convert 25 °C into kelvin.", "T = 25 °C = 298 K", "25 °C = 298 K", F("298.15"), "298", "298", "= 248 K", "248"),
        ("bio-cnv-1", BIO, "unicode", "Convert 50 µm into millimetres.", "The cell is 50 µm = 0.050 mm long.", "50 µm = 0.050 mm", F("0.05"), "0.050", "0.050",
         "= 0.50 mm", "0.50"),
        ("phys-cnv-3", PHYS, "ascii", "Convert 1.5 h into minutes.", "t = 1.5 h = 90 min", "1.5 h = 90 min", F(90), "90", "90", "= 150 min", "150"),
        ("dt-cnv-1", DT, "unicode", "Convert 1500 mm into metres.", "The rod is 1500 mm = 1.5 m long.", "1500 mm = 1.5 m", F("1.5"), "1.5", "1.5", "= 15 m", "15"),
        ("chem-cnv-2", CHEM, "latex", "Convert 350 g into kilograms.", "The mass is $350\\,\\text{g} = 0.350\\,\\text{kg}$.", "350\\,\\text{g} = 0.350\\,\\text{kg}",
         F("0.35"), "0.350", "0.350", "= 3.50\\,\\text{kg}", "3.50")]:
    st = eq("cnv", _text, lambda v, c=_C: c, _S, S_text=_St, kind="cnv")
    old_tail = _text[_text.rindex("="):]
    item(_ident, _subj, "conversions", _nota, _q, _resp, [st],
         muts=[mut("unit_conversion", "cnv", [(old_tail, _wrong, _text, "last")], fault_proof(lambda v, c=_C: c, _wS), f"the conversion factor was misapplied: {_wrong}")],
         auto=("pow10",))

# ========================================================================================== COMPARISONS
for _ident, _subj, _nota, _q, _resp, _good, _bad, _a, _op, _b in [
        ("phys-cmp-1", PHYS, "unicode", "Which gas sample is hotter?", "T₁ = 300 K > T₂ = 250 K, so the first sample is hotter.", "300 K > T₂", "300 K < T₂", "300", ">", "250"),
        ("chem-cmp-1", CHEM, "unicode", "Which reagent is in excess?", "Since 0.10 mol > 0.050 mol, the acid is in excess.", "0.10 mol > 0.050 mol", "0.10 mol < 0.050 mol",
         "0.10", ">", "0.050"),
        ("math-cmp-1", MATH_AA, "latex", "Which fraction is larger, 3/4 or 0.7?", "Since $\\frac{3}{4} = 0.75$ and $0.75 > 0.7$, the first fraction is larger.",
         "0.75 > 0.7", "0.75 < 0.7", "0.75", ">", "0.7"),
        ("ess-cmp-1", ESS, "unicode", "Compare the densities of the two sites.", "Site A is denser: 12 m⁻² > 8.5 m⁻².", "12 m⁻² > 8.5 m⁻²", "12 m⁻² < 8.5 m⁻²", "12", ">", "8.5"),
        ("bio-cmp-1", BIO, "ascii", "Compare the two allele frequencies.", "p = 0.70 > q = 0.30, so the dominant allele is more common.", "0.70 > q", "0.70 < q",
         "0.70", ">", "0.30")]:
    bad_op = {"<": ">", ">": "<"}[_op]
    item(_ident, _subj, "comparisons", _nota, _q, _resp, [other("cmp", _good, "cmp", cmp_proof(_a, _op, _b))],
         muts=[mut("wrong_comparison", "cmp", [(_good, _bad)], cmp_proof(_a, bad_op, _b), "the order sign is reversed")])

# ============================================================================================ SHOW THAT
for _ident, _subj, _nota, _q, _good, _bad, _S, _Sbad, _expr, _bexpr in [
        ("phys-tgt-1", PHYS, "unicode", "A 3.0 kg trolley is pulled by a resultant force of 6.0 N. Show that its acceleration is approximately 2 m s⁻².",
         "a = F/m = 6.0/3.0 = 2.0 m s⁻²", "a = F/m = 6.0/2.0 = 3.0 m s⁻²", "2.0", "3.0", lambda v: v("6.0") / v("3.0"), lambda v: v("6.0") / v("2.0")),
        ("chem-tgt-1", CHEM, "unicode", "Show that 4.0 g of sodium hydroxide is 0.10 mol (M = 40.0 g mol⁻¹).", "n = m/M = 4.0/40.0 = 0.10 mol",
         "n = m/M = 4.0/20.0 = 0.20 mol", "0.10", "0.20", lambda v: v("4.0") / v("40.0"), lambda v: v("4.0") / v("20.0")),
        ("phys-tgt-2", PHYS, "latex", "Show that the kinetic energy of a 2.0 kg mass moving at 3.0 m s⁻¹ is about 9 J.",
         "$E_k = \\frac{1}{2} \\times 2.0 \\times 3.0^2 = 9.0\\,\\text{J}$", "$E_k = \\frac{1}{2} \\times 2.0 \\times 4.0^2 = 16\\,\\text{J}$", "9.0", "16",
         lambda v: v("2.0") * v("3.0") ** 2 / 2, lambda v: v("2.0") * v("4.0") ** 2 / 2),
        ("math-tgt-1", MATH_AA, "unicode", "A line passes through (1, 3) and (5, 7). Show that its gradient is m = 1.", "m = (7 − 3)/(5 − 1) = 1",
         "m = (7 − 3)/(5 − 4) = 4", "1", "4", lambda v: F(1), lambda v: F(4)),
        ("sehs-tgt-1", SEHS, "unicode", "Show that a runner who covers 400 m in 50 s has a mean speed of 8 m s⁻¹.", "v = d/t = 400/50 = 8.0 m s⁻¹",
         "v = d/t = 400/25 = 16 m s⁻¹", "8.0", "16", lambda v: v("400") / v("50"), lambda v: v("400") / v("25"))]:
    tgt_val = {"phys-tgt-1": "2", "chem-tgt-1": "0.10", "phys-tgt-2": "9", "math-tgt-1": "1", "sehs-tgt-1": "8"}[_ident]
    item(_ident, _subj, "show that", _nota, _q, _good, [other("tgt", _good, "tgt", {"rule": "the final value lies in the band of the target", "target": tgt_val,
                                                                                "final": _S})],
         muts=[mut("show_that_mismatch", "tgt", [(_good, _bad)], mismatch_proof(tgt_val, _Sbad, "the final value against the show-that target"),
                   f"the final value {_Sbad} is not the target {tgt_val}; the arithmetic of the chain is consistent with its own figures")])

# ==================================================================================== CHEMICAL EQUATIONS
H2O = {"H": 2, "O": 1}
for _ident, _nota, _text, _left, _right, _bad_text, _bad_left, _bad_right, _cls in [
        ("chem-eqn-1", "unicode", "CH₄ + 2O₂ → CO₂ + 2H₂O", [(1, {"C": 1, "H": 4}, 0), (2, {"O": 2}, 0)], [(1, {"C": 1, "O": 2}, 0), (2, H2O, 0)],
         "CH₄ + O₂ → CO₂ + 2H₂O", [(1, {"C": 1, "H": 4}, 0), (1, {"O": 2}, 0)], [(1, {"C": 1, "O": 2}, 0), (2, H2O, 0)], "unbalanced_atoms"),
        ("chem-eqn-2", "unicode", "C₃H₈ + 5O₂ → 3CO₂ + 4H₂O", [(1, {"C": 3, "H": 8}, 0), (5, {"O": 2}, 0)], [(3, {"C": 1, "O": 2}, 0), (4, H2O, 0)],
         "C₃H₈ + 5O₂ → 3CO₂ + 3H₂O", [(1, {"C": 3, "H": 8}, 0), (5, {"O": 2}, 0)], [(3, {"C": 1, "O": 2}, 0), (3, H2O, 0)], "unbalanced_atoms"),
        ("chem-eqn-3", "ascii", "2C2H6 + 7O2 -> 4CO2 + 6H2O", [(2, {"C": 2, "H": 6}, 0), (7, {"O": 2}, 0)], [(4, {"C": 1, "O": 2}, 0), (6, H2O, 0)],
         "2C2H6 + 6O2 -> 4CO2 + 6H2O", [(2, {"C": 2, "H": 6}, 0), (6, {"O": 2}, 0)], [(4, {"C": 1, "O": 2}, 0), (6, H2O, 0)], "unbalanced_atoms"),
        ("chem-eqn-4", "latex", "$\\mathrm{N_2 + 3H_2 \\rightleftharpoons 2NH_3}$", [(1, {"N": 2}, 0), (3, {"H": 2}, 0)], [(2, {"N": 1, "H": 3}, 0)],
         "$\\mathrm{N_2 + 2H_2 \\rightleftharpoons 2NH_3}$", [(1, {"N": 2}, 0), (2, {"H": 2}, 0)], [(2, {"N": 1, "H": 3}, 0)], "unbalanced_atoms"),
        ("chem-eqn-5", "unicode", "MnO₄⁻ + 8H⁺ + 5e⁻ → Mn²⁺ + 4H₂O", [(1, {"Mn": 1, "O": 4}, -1), (8, {"H": 1}, 1), (5, {}, -1)], [(1, {"Mn": 1}, 2), (4, H2O, 0)],
         "MnO₄⁻ + 8H⁺ + 3e⁻ → Mn²⁺ + 4H₂O", [(1, {"Mn": 1, "O": 4}, -1), (8, {"H": 1}, 1), (3, {}, -1)], [(1, {"Mn": 1}, 2), (4, H2O, 0)], "unbalanced_charge"),
        ("chem-eqn-6", "unicode", "Fe³⁺ + e⁻ → Fe²⁺", [(1, {"Fe": 1}, 3), (1, {}, -1)], [(1, {"Fe": 1}, 2)],
         "Fe³⁺ + 2e⁻ → Fe²⁺", [(1, {"Fe": 1}, 3), (2, {}, -1)], [(1, {"Fe": 1}, 2)], "unbalanced_charge"),
        ("chem-eqn-7", "unicode", "Zn(s) + Cu²⁺(aq) → Zn²⁺(aq) + Cu(s)", [(1, {"Zn": 1}, 0), (1, {"Cu": 1}, 2)], [(1, {"Zn": 1}, 2), (1, {"Cu": 1}, 0)],
         "Zn(s) + Cu⁺(aq) → Zn²⁺(aq) + Cu(s)", [(1, {"Zn": 1}, 0), (1, {"Cu": 1}, 1)], [(1, {"Zn": 1}, 2), (1, {"Cu": 1}, 0)], "unbalanced_charge"),
        ("chem-eqn-8", "unicode", "CaCO₃ + 2HCl → CaCl₂ + H₂O + CO₂", [(1, {"Ca": 1, "C": 1, "O": 3}, 0), (2, {"H": 1, "Cl": 1}, 0)],
         [(1, {"Ca": 1, "Cl": 2}, 0), (1, H2O, 0), (1, {"C": 1, "O": 2}, 0)],
         "CaCO₃ + HCl → CaCl₂ + H₂O + CO₂", [(1, {"Ca": 1, "C": 1, "O": 3}, 0), (1, {"H": 1, "Cl": 1}, 0)],
         [(1, {"Ca": 1, "Cl": 2}, 0), (1, H2O, 0), (1, {"C": 1, "O": 2}, 0)], "unbalanced_atoms"),
        ("chem-eqn-9", "latex", "$\\mathrm{2Mg + O_2 \\rightarrow 2MgO}$", [(2, {"Mg": 1}, 0), (1, {"O": 2}, 0)], [(2, {"Mg": 1, "O": 1}, 0)],
         "$\\mathrm{Mg + O_2 \\rightarrow 2MgO}$", [(1, {"Mg": 1}, 0), (1, {"O": 2}, 0)], [(2, {"Mg": 1, "O": 1}, 0)], "unbalanced_atoms")]:
    resp = f"The balanced equation is {_text}."
    good = _text.strip("$")
    bad = _bad_text.strip("$")
    item(_ident, CHEM, "equations", _nota, "Write the balanced equation for the reaction.", resp, [other("eqn", good, "chem", chem_proof(_left, _right))],
         muts=[mut(_cls, "eqn", [(good, bad)], chem_proof(_bad_left, _bad_right), "a coefficient or charge was changed so the equation no longer balances")],
         extra_tags=("chemical_equation",))

# ====================================================================================== COMPUTER SCIENCE
for _ident, _nota, _resp, _step, _digits, _base, _val, _bad_step, _bad_val in [
        ("cs-base-1", "unicode", "1011₂ = 8 + 0 + 2 + 1 = 11", "1011₂ = 8 + 0 + 2 + 1", "1011", 2, 11, "1011₂ = 8 + 4 + 2 + 1", 15),
        ("cs-base-2", "ascii", "0b110010 = 32 + 16 + 2 = 50", "0b110010 = 32 + 16 + 2", "110010", 2, 50, "0b110010 = 32 + 16 + 4", 52),
        ("cs-base-3", "unicode", "2A₁₆ = 2 × 16 + 10 = 42", "2A₁₆ = 2 × 16 + 10", "2A", 16, 42, "2A₁₆ = 2 × 16 + 12", 44),
        ("cs-base-4", "unicode", "FF₁₆ = 15 × 16 + 15 = 255", "FF₁₆ = 15 × 16 + 15", "FF", 16, 255, "FF₁₆ = 16 × 16 + 15", 271)]:
    tail = _resp[_resp.rindex("=") + 1:].strip()
    bad_resp_tail = str(_bad_val)
    item(_ident, CS, "number bases", _nota, "Convert the number to denary, showing the place values.", _resp,
         [other("base", _step, "base", base_proof(_digits, _base, _val)),
          eq("sum", _resp[len(_step.split(" = ")[0]) + 3:], lambda v, x=_val: F(x), str(_val), exact=True, deps=("base",))],
         muts=[mut("wrong_base_conversion", "base", [(_step, _bad_step), (" = " + tail, " = " + bad_resp_tail, _resp, "last")], base_proof(_digits, _base, _bad_val),
                   f"a place value was misread; the sum ({_bad_val}) is consistent with it", affected=("sum",))])
for _ident, _nota, _resp, _digits, _base, _val, _bad in [("cs-base-5", "unicode", "45 = 32 + 8 + 4 + 1 = 101101₂", "101101", 2, 45, "101111₂"),
                                                        ("cs-base-6", "ascii", "0x3F = 63", "3F", 16, 63, "0x3E")]:
    stated = "101101₂" if _ident == "cs-base-5" else "0x3F"
    seg = "32 + 8 + 4 + 1 = 101101₂" if _ident == "cs-base-5" else "0x3F = 63"
    item(_ident, CS, "number bases", _nota, "Convert the number between bases.", _resp, [other("base", seg, "base", base_proof(_digits, _base, _val))],
         muts=[mut("wrong_base_conversion", "base", [(stated, _bad)], base_proof(_bad.replace("₂", "").replace("0x", ""), _base, _val),
                   f"the based numeral {_bad} does not equal {_val}")])

_bool = [
    ("cs-bool-1", "unicode", "By De Morgan's law, ¬(A ∧ B) = ¬A ∨ ¬B.", "¬(A ∧ B) = ¬A ∨ ¬B", "¬(A ∧ B) = ¬A ∧ ¬B",
     lambda a: not (a["A"] and a["B"]), lambda a: (not a["A"]) or (not a["B"]), lambda a: (not a["A"]) and (not a["B"]), ["A", "B"]),
    ("cs-bool-2", "unicode", "By absorption, A + A·B = A.", "A + A·B = A", "A + A·B = B",
     lambda a: a["A"] or (a["A"] and a["B"]), lambda a: a["A"], lambda a: a["B"], ["A", "B"]),
    ("cs-bool-3", "ascii", "Distributing, A AND (B OR C) = (A AND B) OR (A AND C).", "A AND (B OR C) = (A AND B) OR (A AND C)",
     "A AND (B OR C) = (A AND B) OR C", lambda a: a["A"] and (a["B"] or a["C"]), lambda a: (a["A"] and a["B"]) or (a["A"] and a["C"]),
     lambda a: (a["A"] and a["B"]) or a["C"], ["A", "B", "C"]),
    ("cs-bool-4", "unicode", "Exclusive or can be written A ⊕ B = (A ∧ ¬B) ∨ (¬A ∧ B).", "A ⊕ B = (A ∧ ¬B) ∨ (¬A ∧ B)", "A ⊕ B = (A ∧ B) ∨ (¬A ∧ ¬B)",
     lambda a: a["A"] != a["B"], lambda a: (a["A"] and not a["B"]) or (not a["A"] and a["B"]), lambda a: (a["A"] and a["B"]) or (not a["A"] and not a["B"]),
     ["A", "B"]),
    ("cs-bool-5", "unicode", "Double negation and De Morgan give ¬(¬A ∨ ¬B) = A ∧ B.", "¬(¬A ∨ ¬B) = A ∧ B", "¬(¬A ∨ ¬B) = A ∨ B",
     lambda a: not ((not a["A"]) or (not a["B"])), lambda a: a["A"] and a["B"], lambda a: a["A"] or a["B"], ["A", "B"])]
for _ident, _nota, _resp, _good, _bad, _lhs, _rhs, _brhs, _names in _bool:
    item(_ident, CS, "Boolean algebra", _nota, "Simplify or verify the Boolean expression.", _resp, [other("id", _good, "bool", bool_proof(_lhs, _rhs, _names))],
         muts=[mut("wrong_boolean_identity", "id", [(_good, _bad)], bool_proof(_lhs, _brhs, _names), "one side of the identity was changed")])

for _ident, _header, _f, _n in [("cs-tt-1", ["A", "B", "NOT (A AND B)"], lambda a, b: not (a and b), 2),
                                ("cs-tt-2", ["A", "B", "A XOR B"], lambda a, b: a != b, 2),
                                ("cs-tt-3", ["A", "B", "A OR B"], lambda a, b: a or b, 2)]:
    rows = [tuple(int(x) for x in bits) + (int(_f(*[bool(x) for x in bits])),) for bits in [(0, 0), (0, 1), (1, 0), (1, 1)]]
    text = table_text(_header, rows)
    bad_rows = list(rows)
    bad_rows[2] = bad_rows[2][:2] + (1 - bad_rows[2][2],)
    bad_text = table_text(_header, bad_rows)
    item(_ident, CS, "truth tables", "unicode", f"Complete the truth table for {_header[-1]}.", text, [other("tt", text, "tt", table_proof(rows, _f, _n))],
         muts=[mut("wrong_truth_table_row", "tt", [(text, bad_text)], table_proof(bad_rows, _f, _n), "the output of row (1, 0) was flipped")])
_maj = lambda a, b, c: (a and b) or (a and c) or (b and c)  # noqa: E731
_mrows = [tuple(bits) + (int(_maj(*[bool(x) for x in bits])),) for bits in [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]]
_mtext = table_text(["A", "B", "C", "M"], _mrows)
_mbad = list(_mrows)
_mbad[3] = _mbad[3][:3] + (0,)
_mbad_text = table_text(["A", "B", "C", "M"], _mbad)
item("cs-tt-4", CS, "truth tables", "unicode", "Complete the truth table of the majority function M of three inputs and give an expression for M.",
     _mtext + "\n\nHere M = (A ∧ B) ∨ (A ∧ C) ∨ (B ∧ C).", [other("tt", _mtext, "tt", table_proof(_mrows, _maj, 3))],
     muts=[mut("wrong_truth_table_row", "tt", [(_mtext, _mbad_text)], table_proof(_mbad, _maj, 3), "the output of row (0, 1, 1) was flipped")])

item("cs-code-1", CS, "programming", "unicode", "Write a function that returns the area of a circle, and use it for r = 2.",
     "```python\ndef area(r):\n    return 3.14159 * r ** 2\n```\nFor r = 2, the area is 3.14159 × 2² = 12.56636.",
     [eq("e", "3.14159 × 2² = 12.56636", lambda v: v("3.14159") * 4, "12.56636")], auto=("slip",), extra_tags=("code_block",))
item("cs-data-1", CS, "data representation", "unicode", "How many bytes does a 1920 by 1080 image with 24-bit colour need?",
     "The number of bits is 1920 × 1080 × 24 = 49766400, so the number of bytes is 49766400/8 = 6220800.",
     [eq("bits", "1920 × 1080 × 24 = 49766400", lambda v: F(1920 * 1080 * 24), "49766400", exact=True),
      eq("bytes", "49766400/8 = 6220800", lambda v: F(49766400, 8), "6220800", exact=True, deps=("bits",))], auto=("slip",))

# ===================================================================== PERCENTAGES, pH, VERBAL, ALIGN, PARTS
item("phys-eff-1", PHYS, "energy", "unicode", "A motor uses 800 J and does 600 J of useful work. Calculate its efficiency.",
     "Efficiency = useful output/total input × 100% = 600 J / 800 J × 100% = 75%. The efficiency is therefore 75%.",
     [eq("e", "600 J / 800 J × 100% = 75%", lambda v: v("600") / v("800") * 100, "75", S_text="75"),
      eq("res", "therefore 75%", lambda v: v("75"), "75", S_text="75", deps=("e",), kind="res")], auto=("slip", "sign", "res"))
item("chem-yield-1", CHEM, "stoichiometry", "unicode", "The theoretical yield is 6.0 g and 4.5 g is obtained. Calculate the percentage yield.",
     "Percentage yield = 4.5 g / 6.0 g × 100 = 75%. The percentage yield is therefore 75%.",
     [eq("e", "4.5 g / 6.0 g × 100 = 75%", lambda v: v("4.5") / v("6.0") * 100, "75", S_text="75"),
      eq("res", "therefore 75%", lambda v: v("75"), "75", S_text="75", deps=("e",), kind="res")], auto=("slip", "res"))
item("bio-pct-1", BIO, "osmosis", "unicode", "A potato cylinder's mass fell from 2.50 g to 2.25 g. Calculate the percentage change in mass.",
     "Percentage change = (2.25 − 2.50)/2.50 × 100 = −10%.", [eq("e", "(2.25 − 2.50)/2.50 × 100 = −10%", lambda v: (v("2.25") - v("2.50")) / v("2.50") * 100, "-10",
                                                               S_text="−10")], auto=("slip",))
_ess_eff = item("ess-eff-1", ESS, "energy flow", "unicode", "Calculate the efficiency of energy transfer between the trophic levels.",
                "Efficiency = 150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%.",
                [eq("e", "150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%", lambda v: v("150") / v("1500") * 100, "10", S_text="10")], auto=("slip",))
_ess_eff.unknown_units = True

item("chem-ph-1", CHEM, "acids", "unicode", "Calculate the pH of a solution with [H⁺] = 1.0 × 10⁻³ mol dm⁻³.",
     "pH = −log[H⁺] = −log(1.0 × 10⁻³) = 3.00. The pH is therefore 3.00.",
     [eq("e", "−log(1.0 × 10⁻³) = 3.00", lambda v: F(3), "3.00"), eq("res", "therefore 3.00", lambda v: v("3.00"), "3.00", deps=("e",), kind="res")],
     auto=("slip", "res"))
# log10(2.5) lies in [0.397, 0.399]: 10^397 ≤ 2.5^1000 ≤ 10^399, compared as integers 10^397·2^1000 ≤ 5^1000 ≤ 10^399·2^1000
assert 10 ** 397 * 2 ** 1000 <= 5 ** 1000 <= 10 ** 399 * 2 ** 1000
_PH2 = Iv(4 - F("0.399"), 4 - F("0.397"))
item("chem-ph-2", CHEM, "acids", "latex", "Calculate the pH of a solution with [H⁺] = 2.5 × 10⁻⁴ mol dm⁻³.", "$\\text{pH} = -\\log(2.5 \\times 10^{-4}) = 3.60$",
     [eq("e", "-\\log(2.5 \\times 10^{-4}) = 3.60", lambda v: _PH2, "3.60")], auto=("slip",))

item("phys-verbal-1", PHYS, "electricity", "unicode", "Two resistors of 12 Ω and 8 Ω are in series. Find the total resistance.",
     "Adding the resistances, 12 plus 8 equals 20.", [eq("e", "12 plus 8 equals 20", lambda v: F(20), "20", exact=True)], auto=("slip",))
item("math-verbal-1", MATH_AI, "arithmetic", "unicode", "Share 45 sweets equally among 9 children.", "Each child gets 45 divided by 9, which is 5: 45 divided by 9 equals 5.",
     [eq("e", "45 divided by 9 equals 5", lambda v: F(5), "5", exact=True)], auto=("slip",))

item("phys-align-1", PHYS, "kinematics", "display", "A stone is dropped from rest. Calculate its speed after 2.0 s (g = 9.8 m s⁻²).",
     "Taking $u = 0$, $a = 9.8\\,\\text{m s}^{-2}$ and $t = 2.0\\,\\text{s}$:\n\\begin{align*}\nv &= u + at \\\\\n&= 0 + 9.8 \\times 2.0 \\\\\n&= 19.6\\,\\text{m s}^{-1}\n\\end{align*}",
     [eq("e", "0 + 9.8 \\times 2.0 \\\\\n&= 19.6\\,\\text{m s}^{-1}", lambda v: v("9.8") * v("2.0"), "19.6")], auto=("slip", "pow10"))

item("phys-parts-1", PHYS, "kinematics", "unicode", "A car accelerates from rest at 2.0 m s⁻² for 5.0 s.\n(a) Determine its final speed.\n(b) Find the distance travelled.",
     "Given: u = 0, a = 2.0 m s⁻², t = 5.0 s.\n(a) v = u + at = 0 + 2.0 × 5.0 = 10 m s⁻¹.\n(b) s = ut + ½at² = 0 × 5.0 + ½ × 2.0 × 5.0² = 25 m.",
     [eq("va", "0 + 2.0 × 5.0 = 10 m s⁻¹", lambda v: v("2.0") * v("5.0"), "10"),
      eq("sb", "0 × 5.0 + ½ × 2.0 × 5.0² = 25 m", lambda v: v("2.0") * v("5.0") ** 2 / 2, "25")], auto=("slip",), extra_tags=("part_labels",))

item("ess-table-1", ESS, "sampling", "unicode", "Use the quadrat counts to find the mean number of plants per quadrat.",
     "| Quadrat | Plants |\n|---|---|\n| 1 | 12 |\n| 2 | 15 |\n| 3 | 9 |\n| 4 | 16 |\n\nMean = (12 + 15 + 9 + 16)/4 = 13 plants per quadrat.",
     [eq("e", "(12 + 15 + 9 + 16)/4 = 13", lambda v: F(52, 4), "13", exact=True)], auto=("slip",), extra_tags=("supplied_data",))

# more notation outside the encodings, each beside decidable work
item("math-limit-1", MATH_AA, "limits", "latex", "Use the standard limit to approximate sin 0.010.",
     "Since $\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$, for a small angle $\\sin 0.010 \\approx 0.010$.",
     [], undecided=[("\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1", ("ST-UNDEC-001",), "limit")])
item("math-complex-1", MATH_AA, "complex numbers", "unicode", "Solve x² + 4 = 0.",
     "The discriminant is b² − 4ac = 0² − 4 × 1 × 4 = −16 < 0, so the roots are complex: x = ±2i.",
     [eq("disc", "0² − 4 × 1 × 4 = −16", lambda v: F(-16), "-16", S_text="−16", exact=True),
      other("neg", "−16 < 0", "cmp", cmp_proof("-16", "<", "0"), deps=("disc",))],
     undecided=[("x = ±2i", ("ST-UNDEC-001",), "complex")], auto=("slip",))
item("cs-complexity-1", CS, "algorithms", "unicode", "How many comparisons does one pass of bubble sort make on 8 items, and what is its time complexity?",
     "For n = 8 items each pass makes n − 1 = 8 − 1 = 7 comparisons, and the running time is T(n) = O(n²).",
     [eq("e", "8 − 1 = 7", lambda v: F(7), "7", exact=True)], undecided=[("T(n) = O(n²)", ("ST-UNDEC-001",), "asymptotic")], auto=("slip",))
item("math-fracpow-1", MATH_AA, "indices", "latex", "Evaluate 16^(3/4) without a calculator.", "$16^{3/4} = (\\sqrt[4]{16})^3 = 2^3 = 8$",
     [eq("e", "2^3 = 8", lambda v: F(8), "8", exact=True)], undecided=[("16^{3/4} = (\\sqrt[4]{16})^3", ("ST-UNDEC-001",), "fractional power")], auto=("slip",))

# a function evaluated at a point, checked against the formula the answer states
# a function name other than f, g or h is read as a product (C(12) is C × 12): the evaluation is not set against C(x) — a
# documented gap (docs/STEM_RESULTS.md); the arithmetic beside it is decided and correct work is not flagged
item("mai-func-1", MATH_AI, "functions", "unicode", "The cost function is C(x) = 40 + 2.5x. Find C(12).",
     "Using C(x) = 40 + 2.5x, the cost of 12 items is C(12) = 40 + 2.5 × 12 = 70.",
     [eq("e", "40 + 2.5 × 12 = 70", lambda v: v("40") + v("2.5") * 12, "70")], auto=("slip",))
item("math-func-2", MATH_AA, "functions", "latex", "Given f(x) = x² − 3x, find f(5).", "With $f(x) = x^2 - 3x$, we get $f(5) = 5^2 - 3 \\times 5 = 10$.",
     [other("ev", "f(5) = 5^2 - 3 \\times 5", "eq", {"rule": "the stated formula with x = 5"}),
      eq("e", "5^2 - 3 \\times 5 = 10", lambda v: F(10), "10", exact=True)],
     muts=[mut("wrong_substitution", "ev", [("5^2 - 3 \\times 5 = 10", "5^2 - 3 \\times 3 = 16")], {"rule": "f(5) = 25 − 15 = 10, but the written side is "
                                                                                                     "25 − 9 = 16 (exact)", "fails": True},
               "the argument was substituted as 3 in the second term; the arithmetic is consistent with it", kinds=("eq",), affected=("e",))], auto=("slip",))
item("math-deriv-1", MATH_AA, "calculus", "unicode", "For f(x) = x³ − 2x, find the gradient of the curve at x = 2.",
     "For f(x) = x³ − 2x, f′(x) = 3x² − 2, so f′(2) = 3 × 2² − 2 = 10.",
     [other("der", "f′(x) = 3x² − 2", "alg", derivative_proof([F(1), F(0), F(-2), F(0)], [F(3), F(0), F(-2)])),
      other("ev", "f′(2) = 3 × 2² − 2", "eq", {"rule": "the stated derivative formula with x = 2"}),
      eq("e", "3 × 2² − 2 = 10", lambda v: F(10), "10", exact=True)],
     muts=[mut("wrong_substitution", "ev", [("3 × 2² − 2 = 10", "3 × 3² − 2 = 25")], {"rule": "the stated formula at x = 2 is 10, the written side "
                                                                                            "3 × 3² − 2 = 25 (exact)", "fails": True},
               "the argument 2 was substituted as 3; the arithmetic is consistent with it", kinds=("eq",), affected=("e",))])
