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
    "APPROX_OPS", "APPROX_WORDS", "EXACT_PHRASES", "ROUNDING_PHRASES", "SHORT_RULE", "STEM_SCOPE", "STEM_TOLERANCE_RULE", "TAU_APPROX", "TAU_EQUAL",
    "abs_expr", "approx_qualifies", "band_expr", "exactness_phrase", "half_width", "is_measured", "rounding_phrase", "tau_for",
]

#: τ for ``=`` with a measured operand (R2)
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
    "R2 relative slack τ: 1/100 for '=' with a measured operand (a decimal, scientific notation or a unit in the computed expression or in a stated "
    "expression, a stated value with a unit, a rounded intermediate or constant); over exact operands a stated decimal gets h alone (τ = 0), so its "
    "spelling never widens the band; 1/20 for '≈', '≃', '~' or '=' after approximately, about, roughly, estimate; exact mode (every operand and S "
    "exact, '='), and exactness the answer states beside the relation or the request states for a relation between pure numbers ('exactly', "
    "'without rounding', 'the exact value'): τ = 0 and h = 0; a rounding the request asks for or the answer states keeps h whatever the spelling "
    "of S (no exact mode; a fraction of two integers takes the h of its terminating decimal expansion); in an algebra step a rounded value in the "
    "conclusion gets h and the same τ rule. Each check records the policy that decided it. "
    "R3 interval readings: a carried intermediate (the answer's own earlier rounded result) ranges over [w − h(w), w + h(w)]; a written constant matching "
    "the data booklet at its written precision ranges over the hull of its rounding interval and the booklet value; an unbound standard-constant symbol "
    "admitted by a dimension check ranges over its accepted values (warning on failure); π, e and function values range over their enclosures. "
    "Given data, constants whose value the answer states and exact coefficients are taken as written. "
    "R4 band: the check passes iff some admissible reading gives |C − S| ≤ h(S) + τ·|C| (Form E, entailment, when no operand has an interval reading; "
    "Form S, satisfiability, otherwise); a value set against a value also adds the left value's own half-width. "
    "R5 conversions: exact table factors, τ = 0; a temperature on an offset scale (°C, °F) set against another scale is converted once, on the "
    "value its side states (a unit after a group applies to the evaluated group), never term by term, and as a difference when the statement "
    "speaks of a change. R6 comparisons (<, ≤, >, ≥, ≠) between written values are exact. "
    "R7 substitution: a substituted numeral w matches a binding b iff |w − b| ≤ max(h(b), h(w)) (one value is a rounding of the other; "
    "an exact integer the answer states in Mathematics has h = 0), in b's written unit, in SI, or in a unit of b's dimension that the "
    "same working uses. R8 restated result: |S − S′| ≤ max(h(S), h(S′)) in SI. R9 prose relations keep the quant tolerance rule. "
    "R10 roots: a decimal root r passes iff a real root lies in [r − h(r), r + h(r)]; an exact root passes iff it satisfies the equation exactly."
)

SHORT_RULE = (
    "STEM tolerance: S must lie within h + τ·|C| of the value C computed from the written expression; h is half a unit in S's last digit; "
    "τ is 1% for '=' over measured data, 5% for '≈'/about, else 0; stated exactness makes h and τ 0; rounded values, constants and "
    "functions range over intervals."
)
assert len(SHORT_RULE) <= 300


#: phrases that state exactness, in a request or beside a relation of the answer ("Calculate 1/2 exactly, without rounding.")
EXACT_PHRASES = (
    "exactly", "exact value", "exact values", "exact answer", "exact answers", "exact form", "exact fraction", "exact fractions", "exact result",
    "exact solution", "exact solutions", "exact expression", "exact terms", "without rounding", "do not round", "don't round", "no rounding",
    "not rounded", "unrounded",
)
#: phrases that ask for or state a rounded value ("to 2 decimal places", "correct to 3 s.f.", "to the nearest whole number")
ROUNDING_PHRASES = (
    "decimal place", "decimal places", "d.p.", "dp", "significant figure", "significant figures", "s.f.", "sf", "sig fig", "sig figs", "nearest",
    "round", "rounded", "rounding", "correct to", "approximate", "approximately", "estimate",
)
_NOT_ROUNDING = ("without rounding", "no rounding", "not rounded", "unrounded", "do not round", "don't round")
_NEGATED_BY = ("not ", "n't ", "need not be ", "needn't be ", "not need to be ", "no need to be ", "not be ", "never ")
_COUNT_WORDS = frozenset({"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "once", "twice"})
#: verbs of reproducing a text: "exactly" after one of them ("quote them exactly") asks for the figures as written
_REPRODUCE_VERBS = frozenset({"quote", "quotes", "quoted", "quoting", "cite", "cites", "cited", "citing", "copy", "copies", "copied", "copying",
                              "reproduce", "reproduced", "reproducing", "transcribe", "transcribed", "repeat", "repeated", "relay", "relayed"})
#: "exactly as …" phrases that refer to a text as written ("exactly as given", "exactly as stated")
_AS_WRITTEN = frozenset({"given", "written", "stated", "printed", "shown", "quoted", "reported", "supplied", "provided", "they", "it", "in"})


def _find_phrases(text: str, phrases: tuple[str, ...]) -> list[tuple[str, int, int, str]]:
    """``(phrase, start, end, low)`` for every occurrence of a phrase as whole words in ``text`` (lower-cased, spaces
    collapsed). Bounded: one ``find`` scan per phrase over at most 4,000 characters."""
    low = " ".join(text[:4000].lower().split())
    out: list[tuple[str, int, int, str]] = []
    for phrase in phrases:
        start = 0
        while True:
            k = low.find(phrase, start)
            if k < 0:
                break
            start = k + 1
            end = k + len(phrase)
            if (k > 0 and low[k - 1].isalnum()) or (end < len(low) and low[end].isalnum() and phrase[-1].isalnum()):
                continue
            out.append((phrase, k, end, low))
    return out


def exactness_phrase(text: str) -> str:
    """The phrase of ``text`` that states exactness ("exactly", "exact value", "without rounding"), or ''. A negated phrase
    ("need not be exact") does not count, nor "exactly" before a count ("exactly two reasons", "exactly 3 significant
    figures"): it qualifies the count, not a value; nor "exactly" that says how to reproduce a text ("quote them exactly",
    "copy the figures exactly", "use them exactly as given"): it asks for the figures as written, which keeps their rounding."""
    for phrase, k, end, low in _find_phrases(text, EXACT_PHRASES):
        before = low[max(0, k - 24):k]
        if any(before.endswith(n) for n in _NEGATED_BY):
            continue
        if phrase == "exactly":
            rest = low[end:end + 48].lstrip(" ,:").split(" ")
            nxt = rest[0] if rest else ""
            if nxt.rstrip(".,;:") in _COUNT_WORDS:
                continue
            if nxt[:1].isdigit() and nxt.rstrip(".,;:").isdigit() and len(rest) > 1 and rest[1].isalpha() and len(rest[1]) >= 3:
                continue  # 'exactly 3 significant figures', 'exactly 2 reasons'
            if any(w in _REPRODUCE_VERBS for w in before.replace(",", " ").split()[-4:]) \
                    or (nxt == "as" and len(rest) > 1 and rest[1].rstrip(".,;:") in _AS_WRITTEN):
                continue  # 'quote them exactly', 'use the figures exactly as given'
        return phrase
    return ""


#: words that may stand between an approximation word and the relation it qualifies ("approximately, v = …", "we estimate
#: that v = …", "this gives roughly v = …")
_APPROX_LINKS = frozenset({"so", "then", "is", "are", "was", "we", "get", "gives", "give", "that", "be", "to", "equal", "equals", "which", "it",
                           "as", "at", "this", "value", "of"})


def approx_qualifies(before: str) -> bool:
    """An approximation word (``APPROX_WORDS``, whole words only) qualifies the relation that follows ``before`` (the prose
    right before it): it is among the last words of that prose and only linking words stand between it and the relation
    ("approximately 2.0 × 3.0 = 6.3", "we estimate that v = …", "Roughly, v = …"). A word inside another word ('linearly',
    'thoroughly') or one that qualifies another quantity ("for about 3 s, and v = …", "Around the bend, v = …") does not."""
    tail = before[-160:].lower()
    words: list[str] = []
    cur: list[str] = []
    for ch in tail:
        if ch.isalpha() or (ch == "." and cur and "".join(cur) == "approx"):
            cur.append(ch)
            continue
        if cur:
            words.append("".join(cur))
            cur = []
        if ch.isdigit():
            words.append("#")  # a figure between the word and the relation: the word qualifies that figure
    if cur:
        words.append("".join(cur))
    for w in reversed(words[-6:]):
        if w in APPROX_WORDS:
            return True
        if w not in _APPROX_LINKS:
            return False
    return False


def rounding_phrase(text: str) -> str:
    """The phrase of ``text`` that asks for or states a rounded or approximate value, or ''. "Without rounding" and its
    kin state exactness instead."""
    excluded = [(k, end) for _p, k, end, _low in _find_phrases(text, _NOT_ROUNDING)]
    for phrase, k, end, _low in _find_phrases(text, ROUNDING_PHRASES):
        if any(a <= k < b for a, b in excluded):
            continue
        return phrase
    return ""


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
