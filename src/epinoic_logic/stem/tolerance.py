"""The STEM tolerance rule (R1 to R10) and the band builders (docs/STEM_DESIGN.md, section 5.2).

:data:`STEM_TOLERANCE_RULE` is the full rule; :data:`SHORT_RULE` (300 characters or fewer)
is the ``[rule]`` suffix of every check description. The functions here compute the two
numbers the rule needs from what was written (the half-width ``h`` of a stated value and the
relative slack ``τ``) and build the band as IR data. The absolute value and the band are
inside the IR (``ite``), so the engine, not Python, decides whether a stated value lies in its
band. Python only reads digits: ``h`` is half a unit in the last written digit, an exact
``Fraction``.

The band (R4) is ``|C − S| ≤ h + τ·|C|``: symmetric around the computed value C and
sign-aware, so ``−9.8`` against ``−9.81`` and a stated zero need no special case.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Optional

from .numbers import ExactNumber

__all__ = [
    "APPROX_OPS", "APPROX_WORDS", "SHORT_RULE", "STEM_SCOPE", "STEM_TOLERANCE_RULE", "TAU_APPROX", "TAU_EQUAL", "abs_expr", "band_expr", "half_width",
    "is_measured", "tau_for",
]

#: τ for ``=`` with any decimal or measured operand (R2)
TAU_EQUAL = Fraction(1, 100)
#: τ for ``≈``, ``≃``, ``~`` and for ``=`` after "approximately", "about", "roughly", "estimate" (R2)
TAU_APPROX = Fraction(1, 20)
APPROX_OPS = frozenset({"≈", "≃", "~"})
APPROX_WORDS = ("approximately", "approx.", "about", "roughly", "estimate", "around", "nearly")

STEM_SCOPE = (
    "STEM check: proves a property of its encoding only. It proves that the written arithmetic, substitution, conversion, algebraic step, "
    "balance or Boolean identity holds, or does not hold, under the stated premises, the documented readings and the STEM tolerance rule. "
    "It does not establish that a law applies, that data are true, that a model is physically valid, that a unit is the right one beyond "
    "the dimension and conversion checks, or that the answer is what the question wanted."
)

STEM_TOLERANCE_RULE = (
    "STEM tolerance rule. E is the written expression, S the written value it is said to equal, C the exact value of E under the reading in force. "
    "R1 half-width h(S): half a unit in the last written digit of S's mantissa times its power of ten (5.0 gives 0.05, 1.20 × 10³ gives 5); an exact "
    "fraction or surd gives 0; the trailing zeros of an integer written without a point count only up to the smallest significant-figure count of the "
    "expression's measured operands (1200 with 2-s.f. operands gives 50). "
    "R2 relative slack τ: 1/100 for '=' with any decimal or measured operand or a decimal S; 1/20 for '≈', '≃', '~' or '=' after approximately, about, "
    "roughly, estimate; exact mode (every operand and S exact, '='): τ = 0 and h = 0. "
    "R3 interval readings: a carried intermediate (the answer's own earlier rounded result) ranges over [w − h(w), w + h(w)]; a written constant matching "
    "the data booklet at its written precision ranges over the hull of its rounding interval and the booklet value; an unbound standard-constant symbol "
    "admitted by a dimension check ranges over its accepted values (warning on failure); π, e and function values range over their enclosures. "
    "Given data, constants whose value the answer states and exact coefficients are taken as written. "
    "R4 band: the check passes iff some admissible reading gives |C − S| ≤ h(S) + τ·|C| (Form E, entailment, when no operand has an interval reading; "
    "Form S, satisfiability, otherwise); a value set against a value also adds the left value's own half-width. "
    "R5 conversions: exact table factors, τ = 0. R6 comparisons (<, ≤, >, ≥, ≠) between written values are exact. "
    "R7 substitution: a substituted numeral w matches a binding b iff |w − b| ≤ h(b) + h(w), in b's written unit or in SI. "
    "R8 restated result: |S − S′| ≤ h(S) + h(S′) in SI. R9 prose relations keep the quant tolerance rule. "
    "R10 roots: a decimal root r passes iff a real root lies in [r − h(r), r + h(r)]; an exact root passes iff it satisfies the equation exactly."
)

SHORT_RULE = (
    "STEM tolerance: S must lie within h + τ·|C| of the value C computed from the written expression; h is half a unit in S's last digit; "
    "τ is 1% for '=', 5% for '≈'/about, 0 for conversions, comparisons and exact work; rounded intermediates, constants and functions range "
    "over their intervals."
)
assert len(SHORT_RULE) <= 300


def is_measured(number: ExactNumber, has_unit: bool) -> bool:
    """A measured operand: written with a decimal point, in scientific notation, or with a unit."""
    return bool(has_unit or number.has_point or number.scientific)


def half_width(number: ExactNumber, *, min_sig_figs: Optional[int] = None, exact_mode: bool = False) -> Fraction:
    """R1: half a unit in the last written digit; 0 in exact mode, for a vulgar fraction, a based
    numeral or a bare power of ten; the integer trailing-zero rule with ``min_sig_figs``."""
    if exact_mode:
        return Fraction(0)
    return number.half_width_for(min_sig_figs)


def tau_for(kind: str, *, approx: bool, exact_mode: bool) -> Fraction:
    """R2/R5/R6/R7/R8: the relative slack for a check kind. ``approx`` (``≈`` or an approximation word)
    always gives 1/20; conversions, comparisons, substitutions, restatements, givens and roots
    use none; an arithmetic link uses 1/100 unless it is in exact mode."""
    if approx:
        return TAU_APPROX
    if kind in ("cnv", "cmp", "res", "giv", "sub-match", "sol-root", "tgt"):
        return Fraction(0)
    if exact_mode:
        return Fraction(0)
    return TAU_EQUAL


def abs_expr(x: dict) -> dict:
    """``|x|`` as ``ite(x >= 0, x, -x)``."""
    return {"op": "ite", "cond": {"op": "ge", "left": x, "right": {"op": "real", "value": "0"}}, "then": x, "otherwise": {"op": "neg", "arg": x}}


def band_expr(c: dict, r: dict, h: dict, tau: Fraction, tau_literal: Optional[dict] = None) -> dict:
    """``|c − r| <= h + τ·|c|`` (R4). ``h`` is a literal node already expressed in the comparison's
    frame; ``τ`` is a pure ratio, so it needs no frame. With ``τ = 0`` the band is ``|c − r| <= h``."""
    left = abs_expr({"op": "sub", "left": c, "right": r})
    if tau == 0:
        right = h
    else:
        slack = {"op": "mul", "args": [tau_literal or {"op": "real", "value": f"{tau.numerator}/{tau.denominator}" if tau.denominator != 1 else str(tau.numerator)},
                                       abs_expr(c)]}
        right = slack if h.get("value") == "0" and h.get("op") == "real" else {"op": "add", "args": [h, slack]}
    return {"op": "le", "left": left, "right": right}
