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

import re
from fractions import Fraction
from typing import Optional

from .numbers import ExactNumber

__all__ = [
    "APPROX_OPS", "APPROX_WORDS", "SHORT_RULE", "approx_word_before", "approx_word_in", "STEM_SCOPE", "STEM_TOLERANCE_RULE", "TAU_APPROX", "TAU_EQUAL", "abs_expr", "band_expr", "half_width",
    "is_measured", "tau_for",
]

#: τ for ``=`` with any decimal or measured operand (R2)
TAU_EQUAL = Fraction(1, 100)
#: τ for ``≈``, ``≃``, ``~`` and for ``=`` after "approximately", "about", "roughly", "estimate" (R2)
TAU_APPROX = Fraction(1, 20)
APPROX_OPS = frozenset({"≈", "≃", "~"})
APPROX_WORDS = ("approximately", "approx.", "about", "roughly", "estimate", "around", "nearly")
#: an approximation word as a whole word (stem-soundness-6, round 7: a substring had matched 'linearly', 'thoroughly', 'Around the bend')
_APPROX_WORD = r"(?<![A-Za-z])(?:approximately|approx\.?|about|roughly|estimated?|around|nearly)(?![A-Za-z])"
_APPROX_ANY_RE = re.compile(_APPROX_WORD, re.IGNORECASE)
#: ... directly before what it qualifies: only spaces, "equal to", "is", a colon, a comma or the opening of inline maths may follow it
_APPROX_END_RE = re.compile(_APPROX_WORD + r"(?:[ \t]+(?:equal[ \t]+to|is))?[ \t:,$(\\]*$", re.IGNORECASE)


def approx_word_before(text: str) -> bool:
    """An approximation word, as a whole word, ends ``text`` (R2): it qualifies what follows ('v ≈', 'is about 6.3', 'approximately
    $2.0 × 3.0 = 6.3$'). A word that qualifies another quantity earlier in the sentence ('for about 3 s, and v = …') does not."""
    return bool(_APPROX_END_RE.search(text[-80:]))


def approx_word_in(text: str) -> bool:
    """An approximation word anywhere in ``text``, as a whole word (the gap between the two sides of a relation: '= about 6.3')."""
    return bool(_APPROX_ANY_RE.search(text))

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
    "expression's measured operands (1200 with 2-s.f. operands gives 50), and none count for a value set against a value with no operands (a "
    "conversion's or a restatement's two values: 600 gives 50). "
    "R2 relative slack τ: 1/20 for '≈', '≃', '~' or '=' after approximately, about, roughly, estimate, whatever the check (a conversion included) "
    "but a restated result (R8: an approximation word before a restated value names its rounding, STEM repair 12); "
    "otherwise 1/100 for '=' in written arithmetic with any decimal or measured operand or a decimal S, and 0 for the checks R5 to R10 name; exact mode "
    "(every operand and S exact, '='): τ = 0, and h = 0 unless S closes rational written arithmetic with two or more significant figures: then h(S) is "
    "half a unit in its last written digit, every trailing zero counting, so a whole computed value is stated exactly and one that is not whole may be "
    "stated to S's last digit ('(92 − 18) ÷ 18 × 100 = 411%'; '7/3 = 2' fails; STEM repair 11, rule exact-rounding). "
    "R3 interval readings: a carried intermediate (the answer's own earlier rounded result) ranges over [w − h(w), w + h(w)]; a written constant matching "
    "the data booklet at its written precision ranges over the hull of its rounding interval and the booklet value; an unbound standard-constant symbol "
    "admitted by a dimension check ranges over its accepted values (warning on failure); π, e and function values range over their enclosures. "
    "Given data, constants whose value the answer states and exact coefficients are taken as written. "
    "R4 band: the check passes iff some admissible reading gives |C − S| ≤ h(S) + τ·|C| (Form E, entailment, when no operand has an interval reading; "
    "Form S, satisfiability, otherwise); a value set against a value also adds the left value's own half-width. "
    "R5 conversions: exact table factors, τ = 0 (1/20 after '≈' or about, R2). R6 comparisons (<, ≤, >, ≥, ≠) between written values are exact. "
    "R7 substitution: a substituted numeral w matches a binding b iff |w − b| ≤ h(b) + h(w), in b's written unit or in SI; a value the request "
    "or a text supplied with it states, and a Given that restates one, is data taken as written: w (a substituted numeral or a Given value) matches it "
    "iff one of the two is the other rounded to its own last written digit, |w − b| ≤ max(h(w), h(b)) (STEM repair 11, rule given-data: '0.49 Ω' "
    "for the request's 0.50 ohm fails, '0.5 Ω' holds). "
    "R8 restated result: |S − S′| ≤ h(S) + h(S′) in SI, with no τ, also after an approximation word ('= 2.67 A, which is about 2.7 A'); a rounding "
    "the prose states for S gives h(S) ('to the nearest whole "
    "number' 1/2, 'to 2 s.f.', 'to 1 d.p.'), which says which trailing zeros of a whole number count, never less than half a unit in S's last "
    "written digit; so does a rounding stated for a line's own result ('= 34% to 2 s.f.', STEM repair 11, rule result-rounding). R9 prose "
    "relations keep the quant tolerance rule; a value the prose takes from a table supplied with "
    "the request matches the table's cells (or the difference of two rows) taken as written: |S − D| ≤ h(S). "
    "R10 roots: a decimal root r passes iff a real root lies in [r − h(r), r + h(r)]; an exact root passes iff it satisfies the equation exactly. "
    "R11 central value: a stated value written with its absolute uncertainty, S ± u, is set against C at its central value S under R1 to R4; u never "
    "widens the band and is not itself checked (STEM repair 3: u had been added to h, so a slip within it passed)."
)

#: the ``[rule]`` suffix of every check description: the rule as the checks apply it (STEM repair 1: the earlier short form said
#: "h is half a unit in S's last digit" and "0 for conversions", while R1's trailing-zero rule, R2's precedence of '≈' over
#: every check kind and R4's second half-width for a value set against a value were applied)
SHORT_RULE = (
    "STEM tolerance: |C − S| ≤ h + τ·|C|; h: half a unit in S's last digit (integer trailing zeros only to the operands' s.f.), plus C's own h "
    "if C is a stated value; τ: 1/20 for ≈/about, any check; else 1/100 for = in arithmetic, 0 for conversions, comparisons, substitutions, "
    "restatements, exact work."
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
    gives 1/20 whatever the kind (a conversion included) but a restated result: R8 bands a restatement
    with no τ, an approximation word before it naming its rounding (the restatement check has always
    applied that; STEM repair 12 states it here too); otherwise conversions, comparisons, substitutions,
    restatements, givens and roots use none, and an arithmetic link uses 1/100 unless it is in exact mode."""
    if kind == "res":
        return Fraction(0)
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
