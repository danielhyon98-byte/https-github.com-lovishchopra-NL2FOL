"""Regression tests for the fourth independent verification of finding 1 (exactness, 12 October 2026 review).

The verification found the reviewer's own reproduction succeeding again with "exactly" left out: in the cue-less
conditional "If x = 1/3 then x = 0.33." the figure 0.33 was read as the rounded result of the written calculation
"1/3 then x = 0.33", because the reader took the left side of every '=' that held an operator anywhere, and dropped any
words after a numeral as its unit. The faithful exact encoding (counterexample x = 1/3) was then rejected for its "stated
precision", the translator was told to widen 0.33, and the widened retry was accepted as ENTAILED, recorded as an
unchanged semantic repair and released.

The cause, for its whole class: a figure is the result of a written calculation only when the calculation ENDS at its
'=' (the operand right before the sign is a numeral, a bracket, a power or the unit of a numeral), the run of the
calculation starts with an operand, and the figure ends the expression. A variable, a symbol, a connective or a function
symbol before the '=' makes the figure that term's value. The same holds for an approximation cue, a word or a sign: it
states nothing about a figure it is not written against ("think about it", "almost certain", "about 2 people think that
...", "x ≈ 1/3 so x = 0.33"), and "without approximation" states exactness. Each case is checked at the reader and through
the pipeline (one provider call, never rejected for precision, never ENTAILED, never released), with negative controls in
which a written calculation, a rounding cue or an exactness cue really is there.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TranslationStatus as T, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.quantities import SourceText, figures_in, sentence_of, stated_exactness, written_calculation_value
from epinoic_logic.translate.quantities import _calculation_result  # the reader under test
from epinoic_logic.translate.review import SemanticReviewer

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"calculation-result-and-cue-scope-key-0123"
GIVEN = "Let x equal exactly 1/3."


def V(n):
    return {"op": "var", "name": n}


def R(v):
    return {"op": "real", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


EXACT = eq(V("x"), R("0.33"))
WIDENED = {"op": "and", "args": [{"op": "ge", "left": V("x"), "right": R("0.325")}, {"op": "lt", "left": V("x"), "right": R("0.335")}]}


def problem(conclusion):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": "x", "sort": "Real", "meaning": "x"}],
            "premises": [{"id": "P", "expr": eq(V("x"), R("1/3")), "label": GIVEN,
                          "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "task", "excerpt": GIVEN}]}}],
            "conclusion": {"id": "C", "expr": conclusion, "label": "x = 0.33"}}


def output(p):
    return {"problem": p, "interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def run(claim_text, attempts, *, faithful_review=True):
    """The verifier's scenario: the claim, a supporting claim and the supplied text stating x = 1/3 exactly, and a review
    fixture that calls every encoding faithful (so only the translation layer stands between a weakening and release)."""
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")
    support = ClaimRecord(**ids, claim_id="s0", claim_text=GIVEN, claim_role="evidence")
    claim = ClaimRecord(**ids, claim_id="c", claim_text=claim_text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        supporting_claim_ids=["s0"])
    body = f"{claim_text} {GIVEN}"
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, support],
                              supplied_texts=[SuppliedText(document_id="task", text=GIVEN)], created_at="2026-10-16T00:00:00Z")
    provider = FixtureTranslationProvider({"c": [output(p) for p in attempts]})
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}})) if faithful_review else None
    outcome = verify_claim(claim, report, Translator(provider, config=CFG, max_attempts=2), reviewer, config=CFG, signing_key=KEY, key_id="k")
    return outcome, provider


def last_figure(text, written):
    return [f for f in figures_in(SourceText("claim", "c", text)) if f.written == written][-1]


def calculation_of(text, written):
    f = last_figure(text, written)
    return _calculation_result(text, f, sentence_of(text, f.start, f.end))


# =========================================================================== the verifier's cases

#: Every cue-less phrasing the fourth verification listed, and the comma form it compared them with.
VERIFIER_CASES = [
    "If x = 1/3 then x = 0.33.",
    "x = 1/3 implies x = 0.33.",
    "When x = 1/3 it follows that x = 0.33.",
    "Given x = 1/3 we get x = 0.33.",
    "Claim: if x = 1/3 then x = 0.33, which is false.",
    "If x = 1/3, then x = 0.33.",
]


@pytest.mark.parametrize("left", [" 1/3 then x ", " 1/3 then b ", "1/3 implies x ", " 1/3 and therefore x ", " 1/3 it follows that x ",
                                  " 1/3 we get x ", " 1/3 so x ", " 1/3 x "])
def test_words_before_the_sign_are_no_unit_of_the_calculation(left):
    """The reader returned 1/3 for ' 1/3 then x ': 'then' and 'x' were dropped as unit words. A word right before the '='
    that is no unit of the last operand is the term the '=' is about, so the left side ends in no calculation."""
    assert written_calculation_value(left) is None


def test_a_calculation_written_right_before_the_sign_is_still_computed():
    """Negative control: the same calculation with nothing between it and the '=' is read and computed as written."""
    assert written_calculation_value(" 1/3 ") == Fraction(1, 3)
    assert written_calculation_value(" then 1/3 ") == Fraction(1, 3)  # prose before the calculation is left out
    assert written_calculation_value("120 km ÷ 1.5 h ") == Fraction(80)  # a unit of the last operand ends it


@pytest.mark.parametrize("text", VERIFIER_CASES)
def test_a_cue_less_conditional_states_no_calculation_for_its_figure(text):
    assert calculation_of(text, "0.33") is None
    ex = stated_exactness(last_figure(text, "0.33"), text)
    assert ex.kind == "unstated" and ex.computed is None and not ex.by_convention


@pytest.mark.parametrize("text", VERIFIER_CASES)
def test_the_faithful_exact_encoding_of_a_cue_less_conditional_is_never_rejected_for_precision(text):
    """The faithful exact encoding (counterexample x = 1/3) is no longer rejected with 'stated precision' advice to widen
    0.33: an undecorated decimal whose two readings disagree is AMBIGUOUS_TRANSLATION, after one provider call, never a
    verdict, and never released, even with a review that calls the encoding faithful."""
    outcome, provider = run(text, [problem(EXACT)])
    assert len(provider.calls) == 1
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.display_status is S.AMBIGUOUS_TRANSLATION
    assert not any(d.startswith("attempt") and "stated precision" in d for d in outcome.translation.diagnostics)
    assert outcome.translation.repairs == []
    flag = next(f for f in outcome.translation.interpretation.ambiguity_flags if f.code == "stated_precision")
    assert "COUNTEREXAMPLE" in flag.message and "ENTAILED" in flag.message
    [reading] = [r for r in outcome.translation.figure_readings if r.literal == "0.33"]
    assert reading.exactness == "unstated" and reading.calculated is None and reading.by_convention is False
    assert outcome.release is not None and not outcome.release.permitted


@pytest.mark.parametrize("text", VERIFIER_CASES)
def test_the_widening_the_old_advice_asked_for_never_earns_entailed_or_release(text):
    """The verifier's sequence: the faithful exact encoding, then the widened one the old feedback asked for. The widened
    retry is never requested; served first it is no translation of the claim either (its 0.33 is unstated)."""
    outcome, provider = run(text, [problem(EXACT), problem(WIDENED)])
    assert len(provider.calls) == 1 and outcome.translation.repairs == []
    assert outcome.display_status is not S.ENTAILED and not outcome.release.permitted
    outcome, provider = run(text, [problem(WIDENED)])
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.display_status is S.AMBIGUOUS_TRANSLATION
    assert outcome.verification is not None and outcome.verification.status is S.ENTAILED  # the weakened encoding would prove
    assert not outcome.release.permitted


def test_with_an_exactness_cue_the_conditional_keeps_its_counterexample():
    """Negative control (the reviewer's own wording): the exact claim is TRANSLATED with the counterexample x = 1/3."""
    outcome, provider = run("If x is exactly 1/3, then x is exactly 0.33, without rounding.", [problem(EXACT)])
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE and len(provider.calls) == 1
    assert [(a.symbol, a.value) for a in outcome.verification.counterexample.assignments] == [("x", "1/3")]


def test_a_written_calculation_before_the_sign_keeps_its_rounded_reading_through_the_pipeline():
    """Negative control: 'x = 1/3 = 0.33' writes the calculation 1/3 right before the '=' of 0.33, which rounds it; the
    exact equality is rejected for its stated precision (the feedback names that calculation, not a variable), and the
    retry at exactly that tolerance is the claim (an unchanged conclusion read as its source states it)."""
    text = "Since x = 1/3 = 0.33, the claim holds."
    calc = calculation_of(text, "0.33")
    assert calc is not None and calc[0] == "1/3 = 0.33"
    outcome, provider = run(text, [problem(EXACT), problem(WIDENED)])
    assert any("stated precision" in d and "'1/3 = 0.33' gives 1/3" in d for d in provider.calls[1].prior_diagnostics)
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    assert [(r.kind, r.conclusion) for r in outcome.translation.repairs] == [("semantic", "unchanged")]


# =========================================================================== the whole class

#: The '=' of the last figure equates it with a variable, a symbol, an expression that holds one, or a function symbol's
#: value; or the figure is an operand of a further expression. None of them is the result of a written calculation.
NOT_A_RESULT = [
    ("x = 1/3 so x = 0.33.", "0.33"),
    ("x = 1/3 hence x = 0.33.", "0.33"),
    ("x = 1/3 therefore x = 0.33.", "0.33"),
    ("x = 1/3 ⇒ x = 0.33.", "0.33"),
    ("x = 1/3 → x = 0.33.", "0.33"),
    ("If x = 1/3 x = 0.33.", "0.33"),                  # a variable right after the numeral, with no connective
    ("x = 1/3 then θ = 0.33.", "0.33"),                 # a symbol
    ("x = 1/3 then x1 = 0.33.", "0.33"),                # an identifier
    ("x = 0.333 so x × 3 = 1.00.", "1.00"),              # an operator whose left operand is a variable
    ("x = 1/3 then x − 0.5 + 1 = 0.83.", "0.83"),        # the old reader read the variable's minus as a sign: 1/3 − 0.5 + 1
    ("x = 1/3 then x −0.5 + 1 = 0.83.", "0.83"),
    ("x = 1/3 then f(x) = 0.33.", "0.33"),              # a function symbol's value
    ("f(2) = f(2) + 1 = 3.", "3"),                       # the old reader computed (2) + 1 = 3
    ("With SV = 70 cm³ and HR = 72 min⁻¹, Q = SV × HR.", "72 min⁻¹"),  # the old reader took cm³ for a power
    ("Solve x² + 4 = 0.", "0"),                          # an equation
    ("Δ = b² − 4ac = 17", "17"),
    ("n = c × 0.0250 = 2.50 × 10⁻³ mol", "2.50 × 10⁻³ mol"),
    ("(31 − 11) ÷ 10 = 20 ÷ 10 = 2.0%", "20"),           # the figure is the first operand of the next expression
    ("(2 × 3 + 9 × 4) = 5(2 + 1) = 15", "5"),            # a factor of an implicit product
    ("√8 = 2√2", "2"),
]


@pytest.mark.parametrize("text,written", NOT_A_RESULT)
def test_a_figure_the_sign_equates_with_a_term_that_is_no_calculation_is_no_calculation_result(text, written):
    assert calculation_of(text, written) is None
    ex = stated_exactness(last_figure(text, written), text)
    assert not ex.by_convention and ex.computed is None


@pytest.mark.parametrize("text,claim_value", [("x = 0.333 so x × 3 = 1.00.", "1.00"), ("x = 1/3 then x − 0.5 + 1 = 0.83.", "0.83")])
def test_a_variable_expression_is_never_rejected_for_precision_through_the_pipeline(text, claim_value):
    """Before the fix both were read as rounded results of a written calculation (by convention, or computed from the
    misread 1/3 − 0.5 + 1), so the faithful encoding, which fails exactly, was rejected and the widening accepted."""
    start = "1/3" if "1/3" in text else "0.333"
    term = {"op": "mul", "args": [V("x"), R("3")]} if "×" in text else {"op": "add", "args": [{"op": "sub", "left": V("x"), "right": R("0.5")}, R("1")]}
    given = f"Let x equal exactly {start}."
    p = problem(eq(term, R(claim_value)))
    p["premises"] = [{"id": "P", "expr": eq(V("x"), R(start)), "label": given,
                      "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "task", "excerpt": given}]}}]
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")
    claim = ClaimRecord(**ids, claim_id="c", claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic")
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim],
                              supplied_texts=[SuppliedText(document_id="task", text=given)], created_at="2026-10-16T00:00:00Z")
    provider = FixtureTranslationProvider({"c": [output(p)]})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG, max_attempts=2), None, config=CFG, signing_key=KEY, key_id="k")
    assert len(provider.calls) == 1 and outcome.display_status is not S.ENTAILED
    assert not any(d.startswith("attempt") and "stated precision" in d for d in outcome.translation.diagnostics)
    assert outcome.translation.status in (T.AMBIGUOUS_TRANSLATION, T.TRANSLATED)
    if outcome.translation.status is T.TRANSLATED:
        assert outcome.display_status is S.COUNTEREXAMPLE


#: Written calculations: the result is still read from them, as written (exact) or as the rounding of what they give.
CALCULATIONS = [
    ("PED = −12.50 ÷ 18.75 = −0.67", "−0.67", "rounded", Fraction(-2, 3), False),
    ("x = 1/3 = 0.33", "0.33", "rounded", Fraction(1, 3), False),
    ("If x = 1/3 then 1/3 = 0.33.", "0.33", "rounded", Fraction(1, 3), False),
    ("The price paid is $2.00 − $0.40 = $1.60.", "$1.60", "exact", Fraction(8, 5), False),
    ("3 tickets × $2.50 = $7.50", "$7.50", "exact", Fraction(15, 2), False),            # a count noun inside the calculation
    ("The speed is 120 km ÷ 1.5 h = 80 km/h.", "80 km/h", "exact", Fraction(80), False),  # units of the operands
    ("Tax revenue: $0.40 x 105 million = $42 million.", "$42 million", "exact", Fraction(42_000_000), False),
    ("20 per cent × 50 = 10", "10", "exact", Fraction(10), False),                       # a percentage word is a hundredth
    ("Q = I*t = 6.0E-3 * 150 = 0.90 C", "0.90 C", "exact", Fraction(9, 10), False),        # an exponent
    ("$v = u + at = 0 + 9.8 \\times 3.0 = 29.4\\ \\text{m s}^{-1}$", "29.4", "exact", Fraction(147, 5), False),  # LaTeX
    ("Since $\\frac{3}{4} = 0.75$, the share exceeds a half.", "0.75", "exact", Fraction(3, 4), False),           # '$' is math
    ("The rate is 2³ ÷ 3 = 2.67, which exceeds 2.6.", "2.67", "rounded", None, True),   # a power: the convention
    ("KE = ½ × 2.0 × 3.0² = 9.0 J", "9.0 J", "rounded", None, True),
    ("So √2 × 3 = 4.24", "4.24", "rounded", None, True),
    ("The component is 10 × sin 25° = 4.23 N.", "4.23 N", "rounded", None, True),       # a function value in a calculation
]


@pytest.mark.parametrize("text,written,kind,computed,convention", CALCULATIONS)
def test_a_written_calculation_that_ends_at_the_sign_is_still_read(text, written, kind, computed, convention):
    assert calculation_of(text, written) is not None
    ex = stated_exactness(last_figure(text, written), text)
    assert (ex.kind, ex.computed, ex.by_convention) == (kind, computed, convention)


def test_a_function_value_alone_is_no_written_calculation():
    """'ln 2 = 0.693' and 'sin 30° = 0.5' apply no arithmetic operator: as before, no calculation is read for them (no
    presumption of rounding), while 'ln 2 / 8.0 = 0.0866' is a calculation the reader does not compute (it does not drop
    'ln' and compute 2 / 8.0)."""
    for text, written in [("the working uses ln 2 = 0.693", "0.693"), ("sin 30° = 0.5", "0.5")]:
        assert calculation_of(text, written) is None
    ex = stated_exactness(last_figure("decay constant ln 2 / 8.0 = 0.0866 h^-1", "0.0866 h^-1"), "decay constant ln 2 / 8.0 = 0.0866 h^-1")
    assert ex.kind == "rounded" and ex.by_convention and ex.computed is None


# =========================================================================== the scope of an approximation word

@pytest.mark.parametrize("text", [
    "The question about x: if x = 1/3 then x = 0.33.",
    "Think about it: x = 1/3 so x = 0.33.",
    "We talk about x = 0.33 here.",
    "It is almost certain that x = 0.33.",
    "Nearly all agree x = 0.33.",
    "About 2 people think that if x = 1/3 then x = 0.33.",   # the word governs another figure of the clause
    "x ≈ 1/3 so x = 0.33.",                                   # so does the sign
])
def test_an_approximation_cue_that_governs_another_word_or_figure_is_no_rounding_cue_for_this_one(text):
    """'about' a topic, 'almost' certain, 'nearly' all, 'about 2' people, '≈ 1/3': the cue governs another word or
    another figure, so it states nothing about 0.33, which stays unstated; through the pipeline the faithful encoding is
    ambiguous, never rejected for precision."""
    ex = stated_exactness(last_figure(text, "0.33"), text)
    assert ex.kind == "unstated"
    outcome, provider = run(text, [problem(EXACT), problem(WIDENED)])
    assert len(provider.calls) == 1 and outcome.translation.status is T.AMBIGUOUS_TRANSLATION and not outcome.release.permitted


@pytest.mark.parametrize("text", ["Without approximation, x = 0.33.", "x = 0.33 is not an approximation.", "No approximation is made: x = 0.33."])
def test_a_negated_approximation_states_exactness(text):
    """'Without approximation' was read as a rounding cue ('approx' inside 'approximation'): it states the opposite."""
    assert stated_exactness(last_figure(text, "0.33"), text).kind == "exact"


@pytest.mark.parametrize("text", ["x is about 0.33.", "x is approximately equal to 0.33.", "x = 0.33 approximately.", "x = 0.33 (approx.)",
                                  "0.33, approximately", "About 0.33 of the class passed.", "x is around −0.33 here.", "x ≈ 0.33", "x~0.33",
                                  "The approximate value of 0.33 is used."])
def test_an_approximation_cue_that_governs_the_figure_still_states_rounding(text):
    """Negative control: a word written right before the figure (or 'approximately' right after it), or a sign right
    before it, states that the figure is approximate."""
    written = "−0.33" if "−0.33" in text else "0.33"
    assert stated_exactness(last_figure(text, written), text).kind == "rounded"


def test_an_approximation_cue_governs_the_figure_it_is_written_against_and_no_other():
    """'about a third' governs 'a third', not the 0.33 it glosses; '≈ 118 N' governs 118, not the 12 kg and 9.81 of the
    calculation before it (which read as written), nor the 117.72 it approximates (the calculation gives it exactly)."""
    text = "x = 0.33 (about a third)."
    assert stated_exactness(last_figure(text, "a third"), text).kind == "rounded"
    assert stated_exactness(last_figure(text, "0.33"), text).kind == "unstated"
    text = "R = mg = 12 kg × 9.81 m/s² = 117.72 N ≈ 118 N"
    kinds = {f.written: stated_exactness(f, text) for f in figures_in(SourceText("claim", "c", text))}
    assert kinds["12 kg"].kind == "unstated" and kinds["9.81 m/s²"].kind == "unstated"
    assert kinds["117.72 N"].kind == "exact" and kinds["117.72 N"].computed == Fraction(11772, 100)
    assert kinds["118 N"].kind == "rounded" and kinds["118 N"].cue == "≈"
    # and the precision cues keep their reach over the clause: 'Rounded to 2 d.p.,' still governs 0.33 past 'nearly all'
    text = "Rounded to 2 d.p., nearly all agree x = 0.33"
    ex = stated_exactness(last_figure(text, "0.33"), text)
    assert ex.kind == "rounded" and ex.precision == "2 decimal places"


def test_a_genuinely_rounded_claim_still_uses_its_stated_tolerance():
    """Negative control through the pipeline: the stated tolerance, exactly, is the claim (ENTAILED), and the false
    rounded claim keeps its counterexample at that tolerance."""
    outcome, _ = run("If x = 1/3, then x is 0.33 to 2 decimal places.", [problem(WIDENED)])
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    wrong = {"op": "and", "args": [{"op": "ge", "left": V("x"), "right": R("0.335")}, {"op": "lt", "left": V("x"), "right": R("0.345")}]}
    outcome, _ = run("If x = 1/3, then x is 0.34 to 2 decimal places.", [problem(wrong)])
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE


@pytest.mark.parametrize("left,value", [
    ("(2 + 3) kg × 2 ", Fraction(10)),               # the unit of a bracketed operand is dropped like a numeral's
    ("20 per cent × 50 ", Fraction(10)),             # a percentage word is a hundredth (it was dropped: 1000)
    ("3 tickets × $2.50 ", Fraction(15, 2)),         # a count noun inside the calculation
    ("150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 ", Fraction(10)),  # compound units, an everyday unit with a power
    ("3.0e8 / 5.0e14 ", Fraction(3, 5_000_000)),     # exponents
    ("\\frac{36}{18.0} ", Fraction(2)),              # LaTeX read as plain marks
    ("0 + 9.8 \\times 3.0 ", Fraction(147, 5)),
    ("$1.60 per litre × 100 litres ", Fraction(160)),  # 'per', 'a' and 'an' join a unit of the operand
    ("$5 an hour × 8 hours ", Fraction(40)),
    ("12 V − (4.14 A × 0.50 Ω) ", Fraction(993, 100)),  # 'A' is the ampere, no article
])
def test_the_reader_reads_the_units_percentages_and_notation_of_its_operands(left, value):
    assert written_calculation_value(left) == value


@pytest.mark.parametrize("left", [
    "(20 + 30) per cent × 2 ",   # a percentage of a bracketed operand is not read
    " 1/3 as ",                  # English words the unit table reads as rare units are no units here
    "2 + 1 us ",
    " 1/3 then x × 3 ",          # a variable inside the calculation
    "ln 2 / 8.0 ",               # a function value: no tail is computed with the function dropped
    "f(2) + 1 ",                 # a function symbol's value
    "x −0.5 + 1 ",               # the variable's operator is no sign
    "5 apples + 3 apples ",      # a count noun is no unit at the end of the calculation
    " 1/3 per x ",               # 'per' joins a unit, never a variable
    " 1/3 a x ",
])
def test_the_reader_declines_what_is_no_written_calculation_of_numerals(left):
    assert written_calculation_value(left) is None


def test_an_approximated_figure_is_stated_as_rounded():
    text = "x was approximated as 0.33 here."
    assert stated_exactness(last_figure(text, "0.33"), text).kind == "rounded"
