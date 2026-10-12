"""Readings the corpus evaluation (stage ``corpus-eval``) found missing or wrong in the STEM front end and checks, each
fixed in the STEM modules and pinned here: correct work stays clean, the wrong version is named, and every new path is
bounded on adversarial input (it never raises and never evaluates text).

* a restatement written as inline maths (``therefore $2.6\\,\\text{m s}^{-2}$``) and a signed prose number (``−0.70``);
* a derivation line followed on its line by a sentence of prose;
* a chemical equation inside one ``\\mathrm{…}`` wrapper;
* a word formula whose label ends in a superscript or a per cent (``BMI = mass/height² = …``, ``× 100% = 600 J / …``);
* a parenthesised unit denominator (``J/(g K)``, ``kJ/(m^2 yr)``) and the SEHS names ``SV``, ``HR``, ``BMI``;
* a hexadecimal numeral that opens with a digit (``2A₁₆``);
* the dimension of a symbolic side with integer coefficients (``½mv²``, ``2as``);
* an order chain ``T₁ = 300 K > T₂ = 250 K``; a result after ``estimated at``; steps after ``we get``;
* a substitution whose factors are written in another order matches each factor once (``SV × HR = 70 × 42``);
* a restatement in a unit the table does not hold, paired only with the same unit;
* a Boolean name definition (``M = …``) and a truth-table column it heads;
* a factorisation stated inside a chain (``x² − 7x + 12 = (x − 3)(x − 4) = 0``);
* Euler's number to a closed power (``e^{1.386}``), Σ over integer bounds, and a function or derivative evaluated at a
  point against the formula the answer states;
* a complex value (``x = ±2i``) named undecided, not taken for a law; a show-that target never taken from bracketed data;
* a ratio equality (``12:18 = 2:3``) compared by cross products, and a step label (``Step 1: …``) that is no ratio;
* the lexer's fast paths (brackets first, the scientific forms tried only at their opening character, extents without
  values) read exactly what the full paths read.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document, clear_document_cache, lex, reading_view
from epinoic_logic.stem.checks import _injective
from epinoic_logic.stem.nodes import BinOp, Func, Neg, Num, Sym, Unsupported, render, replace_symbol
from epinoic_logic.stem.numbers import exact_integer
from epinoic_logic.stem.parser import STEM_NAMES
from epinoic_logic.stem.relations import dimension_of
from epinoic_logic.stem.scope import Scope
from epinoic_logic.stem.units import unit_group

KEY = b"stem-reading-extensions-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
MATH, PHYS, CHEM, CS, SEHS = ("Mathematics: Analysis and Approaches", "Physics", "Chemistry", "Computer Science",
                              "Sports, Exercise and Health Science")


def receipt(subject: str, request: str, answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=["a"]))
    m, _, _ = hub.dispatch("t", "a", request)
    _, rc = hub.receive("t", m.message_id, answer, agent_id="a", report_id="r1")
    return rc


def kinds(rc) -> dict[str, bool]:
    return {c.constraint_id: c.satisfied for c in rc.formal_checks}


def failed(rc) -> set[str]:
    return {c.constraint_id.rsplit("-", 1)[0] for c in rc.formal_checks if c.satisfied is False}


def clean(rc) -> bool:
    return not rc.errors and not any(f.code == "INT-SUBJ-004" for f in rc.findings) and all(c.satisfied is not False for c in rc.formal_checks)


def rel_kinds(text: str, profile: str, request: str = "q") -> list[tuple[str, str]]:
    doc = build_document(text, request, profile)
    return [(r.kind, r.outcome) for r in doc.relations]


# ----------------------------------------------------------------------------------- restatements, signs
def test_a_restatement_written_as_inline_maths_is_checked():
    good = "Using $a = \\frac{8.0 - 1.5}{2.5} = 2.6\\,\\text{m s}^{-2}$. The acceleration is therefore $2.6\\,\\text{m s}^{-2}$."
    rc = receipt(PHYS, "Calculate the acceleration.", good)
    assert clean(rc) and any(c.startswith("stem-res") for c in kinds(rc))
    bad = receipt(PHYS, "Calculate the acceleration.", good.replace("therefore $2.6", "therefore $-2.6"))
    assert "stem-res" in failed(bad) and any(f.code == "INT-SUBJ-001" for f in bad.errors)


def test_a_minus_before_a_prose_number_is_its_sign_and_a_hyphen_is_not():
    rc = receipt("Biology", "Find p.", "Using p = 1 − q = 1 − 0.30 = 0.70. The frequency is therefore −0.70.")
    assert "stem-res" in failed(rc)
    ok = receipt("Biology", "Find p.", "Using p = 1 − q = 1 − 0.30 = 0.70. The frequency is therefore 0.70.")
    assert clean(ok)
    doc = build_document("The isotope helium-4 has 2 protons.", "q", "chemistry")
    assert all(render(pv.node) != "-4" for pv in doc.prose_values)


def test_result_participles_before_at_or_as_are_cues_and_a_condition_is_not():
    rc = receipt("Biology", "Estimate N.", "With n₁ = 40 and n₂ = 36 and m = 6, N = n₁n₂/m = 40 × 36/6 = 240. The population is therefore estimated at −240.")
    assert "stem-res" in failed(rc)
    doc = build_document("v = 2.0 × 3.0 = 6.0 m s⁻¹. So at 6.0 m s⁻¹ the drag is small.", "q", "physics")
    assert not any(r.kind == "res" for r in doc.relations)


# ------------------------------------------------------------------------------------------ segmentation
def test_a_derivation_line_followed_by_a_sentence_splits_and_a_bare_derivation_does_not():
    text = ("Using $s = ut + \\frac{1}{2}at^2 = 4.0 \\times 5.0 + \\frac{1}{2} \\times 0.80 \\times 5.0^2 = 30\\,\\text{m}$. "
            "The displacement is therefore $30\\,\\text{m}$.")
    doc = build_document(text, "q", "physics")
    assert len(doc.statements) == 2 and doc.statement_text(doc.statements[1].id).startswith("The displacement")
    assert any(r.kind == "res" for r in doc.relations)
    single = build_document("x = 2 + 3 = 5", "q", "physics")
    assert len(single.statements) == 1


# ----------------------------------------------------------------------------------------------- chemistry
def test_a_chemical_equation_inside_one_mathrm_wrapper_is_balanced_or_not():
    ok = receipt(CHEM, "Write the equation.", "The balanced equation is $\\mathrm{2H_2 + O_2 \\rightarrow 2H_2O}$.")
    assert kinds(ok).get("stem-chem-1") is True
    bad = receipt(CHEM, "Write the equation.", "The balanced equation is $\\mathrm{H_2 + O_2 \\rightarrow 2H_2O}$.")
    assert "stem-chem" in failed(bad)
    # a physics reading has no chemistry: the wrapper is text there, never a balance check
    assert not any(k == "chem" for k, _o in rel_kinds("$\\mathrm{2H_2 + O_2 \\rightarrow 2H_2O}$", "physics"))


# ------------------------------------------------------------------------------------------ word formulas
@pytest.mark.parametrize("subject, text, wrong", [
    (SEHS, "BMI = mass/height² = 72/1.80² = 22 kg m⁻².", "BMI = mass/height² = 72/1.80² = 32 kg m⁻²."),
    (PHYS, "Efficiency = useful output/total input × 100% = 600 J / 800 J × 100% = 75%.",
     "Efficiency = useful output/total input × 100% = 600 J / 800 J × 100% = 65%."),
])
def test_a_word_formula_is_followed_by_its_numeric_chain(subject, text, wrong):
    rc = receipt(subject, "Calculate it.", text)
    assert clean(rc) and any(c.startswith("stem-eq") for c in kinds(rc))
    assert "stem-eq" in failed(receipt(subject, "Calculate it.", wrong))


# ------------------------------------------------------------------------------------------------- units
@pytest.mark.parametrize("text, unit", [("c = 4.18 J/(g K)", "J/(g K)"), ("GPP = 4200 kJ/(m^2 yr)", "kJ/(m^2 yr)"), ("x = 4.18 J/(mol K).", "J/(mol K)"),
                                        ("R = 8.31 J/(mol*K)", "J/(mol*K)")])
def test_a_parenthesised_unit_denominator_belongs_to_the_quantity(text, unit):
    doc = build_document(text, "q", "chemistry")
    (b,) = [x for v in doc.bindings.values() for x in v]
    assert b.unit is not None and b.unit.text == unit


def test_a_bracket_after_a_quantity_that_is_no_unit_stays_outside_it():
    doc = build_document("y = 3 (x + 1)/(x y)", "q", "mathematics_aa")
    assert "(x + 1)" in render(doc.items[0].chains[0].operands[1].readings[0])


def test_unit_group_accepts_units_and_exponents_only():
    def toks(s: str):
        r = reading_view(s)
        return lex(r, 0, len(r)).tokens
    from epinoic_logic.stem.limits import profile_for
    prof = profile_for("physics")
    for good in ("g K", "m^2 yr", "mol*K", "m² s", "kg m^-1"):
        t = toks(good)
        assert unit_group(t, 0, len(t), prof), good
    for bad in ("x + 1", "2 m", "m^", "", "Δx", "m^x"):
        t = toks(bad)
        assert not unit_group(t, 0, len(t), prof), bad


def test_heat_capacity_with_a_slashed_unit_has_its_dimension():
    rc = receipt(CHEM, "Find Q.", "With m = 100.0 g, c = 4.18 J/(g K) and ΔT = 12.0 K, Q = mcΔT = 100.0 * 4.18 * 12.0 = 5016 K.")
    assert any(s.code == "ST-DIM-001" for s in rc.structural_findings)
    ok = receipt(CHEM, "Find Q.", "With m = 100.0 g, c = 4.18 J/(g K) and ΔT = 12.0 K, Q = mcΔT = 100.0 * 4.18 * 12.0 = 5016 J.")
    assert clean(ok) and not any(s.code.startswith("ST-DIM") for s in ok.structural_findings)


def test_sports_science_names_are_symbols():
    assert {"SV", "HR", "BMI"} <= STEM_NAMES
    rc = receipt(SEHS, "Find Q.", "With SV = 70 cm³ and HR = 72 min⁻¹, Q = SV × HR = 70 × 72 = 5040 cm³ min⁻¹.")
    assert clean(rc) and kinds(rc).get("stem-sub-1") is True and not any(s.code == "ST-UNDEC-002" for s in rc.structural_findings)


# ----------------------------------------------------------------------------------------- based numerals
@pytest.mark.parametrize("text, ok", [("2A₁₆ = 2 × 16 + 10 = 42", True), ("2A₁₆ = 2 × 16 + 12 = 44", False), ("3F₁₆ = 63", True), ("3F₁₆ = 62", False)])
def test_a_hexadecimal_numeral_may_open_with_a_digit(text, ok):
    rc = receipt(CS, "Convert.", text)
    assert any(c.startswith("stem-base") for c in kinds(rc))
    assert clean(rc) is ok


def test_a_digit_before_hex_letters_without_a_base_mark_is_not_a_numeral():
    r = reading_view("2AB = 5")
    toks = lex(r, 0, len(r), cs=True).tokens
    assert toks[0].text == "2"


# ------------------------------------------------------------------------------------------- dimensions
def test_integer_coefficients_of_a_symbolic_side_are_dimensionless_and_bare_numbers_are_not():
    doc = build_document("Given: m = 2.0 kg, v = 3.0 m s⁻¹.", "q", "physics")
    scope = Scope()
    for v in doc.bindings.values():
        for b in v:
            scope.add(b)
    half_mv2 = build_document("E = ½mv²", "q", "physics").items[0].chains[0].operands[1].readings[0]
    two_mv = BinOp("*", Num(exact_integer(2)), Sym("m"))
    assert dimension_of(half_mv2, scope, coefficients=True) is not None
    assert dimension_of(two_mv, scope, coefficients=True) is not None and dimension_of(two_mv, scope) is None
    # a numeric chain of bare numbers stays unitless as written: never a dimension finding
    rc = receipt(PHYS, "Find v.", "v = 120 / 8 = 15 m s⁻¹")
    assert not any(s.code.startswith("ST-DIM") for s in rc.structural_findings)


@pytest.mark.parametrize("answer, finding", [
    ("Given: m = 1.6 kg, v = 4.5 m/s.\nUsing E_k = (1/2)mv^2 = (1/2) * 1.6 * 4.5^2 = 16 W. The kinetic energy is therefore 16 W.", True),
    ("Given: m = 1.6 kg, v = 4.5 m/s.\nUsing E_k = (1/2)mv^2 = (1/2) * 1.6 * 4.5^2 = 16 J. The kinetic energy is therefore 16 J.", False),
])
def test_a_result_unit_of_another_dimension_is_named(answer, finding):
    rc = receipt(PHYS, "Calculate the kinetic energy of a 1.6 kg object moving at 4.5 m s⁻¹.", answer)
    assert any(s.code == "ST-DIM-001" for s in rc.structural_findings) is finding
    assert not rc.errors


# ------------------------------------------------------------------------------------- comparisons, steps
@pytest.mark.parametrize("op, ok", [(">", True), ("<", False)])
def test_an_order_chain_between_bound_symbols_is_compared(op, ok):
    rc = receipt(PHYS, "Compare.", f"T₁ = 300 K {op} T₂ = 250 K, so the first sample is {'hotter' if ok else 'cooler'}.")
    assert any(c.startswith("stem-cmp") for c in kinds(rc)) and clean(rc) is ok


@pytest.mark.parametrize("word", ["we get", "we obtain", "this yields", "which leads to"])
def test_step_words_make_a_rearrangement_a_checked_step(word):
    good = receipt(PHYS, "Rearrange.", f"From v² = u² + 2as {word} s = (v² − u²)/(2a).")
    bad = receipt(PHYS, "Rearrange.", f"From v² = u² + 2as {word} s = (v² − u²)/a.")
    assert kinds(good).get("stem-alg-1") is True and "stem-alg" in failed(bad)


# ------------------------------------------------------------------------------------------ substitutions
def test_each_factor_of_a_reordered_substitution_stands_for_one_symbol():
    bad = receipt(SEHS, "Find Q.", "With SV = 70 cm³ and HR = 72 min⁻¹, Q = SV × HR = 70 × 42 = 2940 cm³ min⁻¹.")
    assert "stem-sub" in failed(bad)
    swapped = receipt(SEHS, "Find Q.", "With SV = 70 cm³ and HR = 72 min⁻¹, Q = SV × HR = 72 × 70 = 5040 cm³ min⁻¹.")
    assert clean(swapped)


def test_injective_choices_are_bounded():
    assert _injective([[1, 2], [1, 2]]) == [(1, 2), (2, 1)]
    assert _injective([[1], [1]]) == []
    assert _injective([list(range(8))] * 8, limit=120) is None  # 8! orderings: refused, never enumerated in full
    t = time.perf_counter()
    assert _injective([list(range(40))] * 40, limit=120) is None
    assert time.perf_counter() - t < 1.0


# ------------------------------------------------------------------------------------- unknown units
def test_a_restatement_in_an_unknown_unit_pairs_only_with_the_same_unit():
    text = "Using NPP = GPP − R = 2500 − 1800 = 700 kJ m⁻² yr⁻¹. The net primary productivity is therefore {} kJ m⁻² yr⁻¹."
    bad = receipt("Environmental Systems and Societies", "Find NPP.", text.format("−700"))
    assert "stem-res" in failed(bad) and any(f.code == "INT-SUBJ-004" for f in bad.findings) and not bad.errors
    assert clean(receipt("Environmental Systems and Societies", "Find NPP.", text.format("700")))
    other = build_document("x = 2 + 3 = 5 kJ m⁻² yr⁻¹. So it is therefore 5 kg yr⁻¹.", "q", "ess")
    assert not any(r.kind == "res" for r in other.relations)


# -------------------------------------------------------------------------------------------- Boolean
def test_a_boolean_name_definition_is_no_identity_and_checks_its_table_column():
    rows = ["| 0 | 0 | 0 | 0 |", "| 0 | 0 | 1 | 0 |", "| 0 | 1 | 0 | 0 |", "| 0 | 1 | 1 | 1 |", "| 1 | 0 | 0 | 0 |", "| 1 | 0 | 1 | 1 |",
            "| 1 | 1 | 0 | 1 |", "| 1 | 1 | 1 | 1 |"]
    table = "| A | B | C | M |\n|---|---|---|---|\n" + "\n".join(rows)
    rc = receipt(CS, "Majority.", table + "\n\nHere M = (A ∧ B) ∨ (A ∧ C) ∨ (B ∧ C).")
    assert clean(rc) and kinds(rc).get("stem-tt-1") is True and not any(c.startswith("stem-bool") for c in kinds(rc))
    wrong = table.replace("| 0 | 1 | 1 | 1 |", "| 0 | 1 | 1 | 0 |")
    assert "stem-tt" in failed(receipt(CS, "Majority.", wrong + "\n\nHere M = (A ∧ B) ∨ (A ∧ C) ∨ (B ∧ C)."))
    # an identity with the name on both sides is still an identity
    assert "stem-bool" in failed(receipt(CS, "Absorb.", "A + A·B = B"))


# ---------------------------------------------------------------------------------------- factorisation
@pytest.mark.parametrize("text, ok", [("x² − 7x + 12 = (x − 3)(x − 4) = 0", True), ("x² − 7x + 12 = (x − 3)(x + 4) = 0", False),
                                      ("x^2 + 2x - 3 = (x - 1)(x + 3) = 0", True)])
def test_a_factorisation_inside_a_chain_is_an_identity_check(text, ok):
    rc = receipt(MATH, "Solve.", f"Factorising, {text}, so the solutions follow.")
    assert any(c.startswith("stem-alg") for c in kinds(rc)) and clean(rc) is ok


def test_a_law_with_several_symbols_is_never_read_as_a_factorisation():
    assert not any(k == "alg" for k, _o in rel_kinds("mgh = ½mv² = 0", "mathematics_aa"))
    assert not any(k == "alg" for k, _o in rel_kinds("x² − 7x + 12 = (x − 3)(x − 4) = 0", "physics"))


# ------------------------------------------------------------------------------- Euler's number, Σ, f(2)
@pytest.mark.parametrize("text, ok", [("$e^{2(0.693)} = e^{1.386} \\approx 4.00$", True), ("e^{1.386} ≈ 5.00", False), ("e² ≈ 7.39", True),
                                      ("e^{-0.5} = 0.607", True), ("e^{-0.5} = 0.707", False)])
def test_euler_number_to_a_closed_power_is_an_exponential(text, ok):
    rc = receipt(MATH, "Evaluate.", text)
    assert any(c.startswith("stem-eq") for c in kinds(rc)) and clean(rc) is ok


def test_euler_power_of_an_unknown_and_e_in_the_sciences_stay_as_before():
    assert ("link", "undecided") in rel_kinds("$e^{2x} = 4$", "mathematics_aa")
    doc = build_document("e^2 = 7.39", "q", "physics")
    assert not any(isinstance(n, Func) for it in doc.items for c in it.chains for o in c.operands for n in o.readings)


@pytest.mark.parametrize("text, ok", [("$\\sum_{k=1}^{4} k^2 = 1 + 4 + 9 + 16 = 30$", True), ("Σ_{k=1}^{5} (2k − 1) = 25", True),
                                      ("$\\sum_{k=1}^{4} k^2 = 31$", False), ("$\\sum_{k=0}^{3} 2k = 12$", True)])
def test_a_sum_over_integer_bounds_is_its_terms(text, ok):
    rc = receipt(MATH, "Sum.", text)
    assert any(c.startswith("stem-eq") for c in kinds(rc)) and clean(rc) is ok


@pytest.mark.parametrize("text", ["$\\sum_{k=1}^{n} k = 10$", "$\\sum_{k=1}^{1000} k = 500500$", "$\\sum_{i=0}^{3} 2^i = 15$", "Σ x = 3"])
def test_a_sum_with_symbolic_or_many_bounds_stays_undecided(text):
    assert ("link", "undecided") in rel_kinds(text, "mathematics_aa")


@pytest.mark.parametrize("answer, ok", [("f(x) = x² + 1, so f(2) = 2² + 1 = 5.", True), ("f(x) = x² + 1, so f(2) = 2² + 2 = 6.", False),
                                        ("For f(x) = x³ − 2x, f′(x) = 3x² − 2, so f′(2) = 3 × 2² − 2 = 10.", True),
                                        ("For f(x) = x³ − 2x, f′(x) = 3x² − 2, so f′(2) = 3 × 3² − 2 = 25.", False)])
def test_a_function_evaluation_is_set_against_the_stated_formula(answer, ok):
    rc = receipt(MATH, "Evaluate.", answer)
    assert clean(rc) is ok
    assert not any(s.code == "ST-UNDEC-001" and "function of an unknown" in s.message for s in rc.structural_findings)


def test_the_stated_derivative_itself_stays_undecided():
    rc = receipt(MATH, "Differentiate.", "For f(x) = x³ − 2x, f′(x) = 3x² − 2.")
    assert any(s.code == "ST-UNDEC-001" and "derivative" in s.message for s in rc.structural_findings)
    # with no stated formula an evaluation of a derivative stays undecided
    assert ("link", "undecided") in rel_kinds("f′(2) = 10", "mathematics_aa")


def test_replace_symbol_rebuilds_explicitly_and_is_bounded():
    expr = BinOp("+", BinOp("*", Sym("x"), Sym("x")), Num(exact_integer(1)))
    out = replace_symbol(expr, "x", Num(exact_integer(2)))
    assert render(out) == "2·2 + 1" or "2" in render(out) and "x" not in render(out)
    deep: object = Sym("x")
    for _ in range(80):
        deep = Neg(deep)
    assert replace_symbol(deep, "x", Num(exact_integer(1))) is None  # beyond the depth bound: refused, not recursed
    assert replace_symbol(Unsupported("a limit"), "x", Num(exact_integer(1))) == Unsupported("a limit")


# ------------------------------------------------------------------------------------- complex, targets
@pytest.mark.parametrize("text", ["so the roots are complex: x = ±2i.", "z = 3 + 4i"])
def test_a_complex_value_is_named_undecided(text):
    doc = build_document(text, "q", "mathematics_aa")
    assert any(f.code == "ST-UNDEC-001" and "complex" in f.message for f in doc.findings)


def test_a_law_written_with_outside_notation_is_still_a_law():
    assert ("formula", "formula") in rel_kinds("F = ma⃗", "physics")


def test_a_show_that_target_is_never_taken_from_bracketed_data():
    q = "Show that 4.0 g of sodium hydroxide is 0.10 mol (M = 40.0 g mol⁻¹)."
    ok = receipt(CHEM, q, "n = m/M = 4.0/40.0 = 0.10 mol")
    assert kinds(ok).get("stem-tgt-1") is True
    bad = receipt(CHEM, q, "n = m/M = 4.0/20.0 = 0.20 mol")
    assert any(f.code == "INT-SUBJ-004" for f in bad.findings) and "stem-tgt" in failed(bad)


# ------------------------------------------------------------------------------------ ratios, step labels
@pytest.mark.parametrize("subject, answer, ok", [(MATH, "12:18 = 2:3", True), (MATH, "12:18 = 3:4", False),
                                                 ("Biology", "The phenotype ratio is 75:25 = 3:1.", True),
                                                 ("Biology", "The phenotype ratio is 75:25 = 2:1.", False)])
def test_a_ratio_equality_is_compared_by_cross_products(subject, answer, ok):
    rc = receipt(subject, "Simplify the ratio.", answer)
    assert kinds(rc) == {"stem-eq-1": ok}
    assert clean(rc) if ok else any(f.code == "INT-SUBJ-001" for f in rc.errors)


def test_a_step_label_glued_to_its_colon_is_no_ratio():
    ok = receipt(PHYS, "Calculate each product.", "Step 1: 3.0 × 2.0 = 6.0\n\nStep 2: 6.0 × 2.0 = 12")
    assert kinds(ok) == {"stem-eq-1": True, "stem-eq-2": True} and clean(ok)
    bad = receipt(PHYS, "Calculate each product.", "Step 1: 3.0 × 2.0 = 7.0")
    assert kinds(bad) == {"stem-eq-1": False}
    doc = build_document("Step 1: 3.0 × 2.0 = 6.0", "q", "physics")
    assert [doc.text[s.start:s.end] for s in doc.spans.spans if s.kind == "math_run"] == ["3.0 × 2.0 = 6.0"]


# ------------------------------------------------------------------------------------ lexer fast paths
FAST_PATH_TEXTS = ["(" * 40 + "1,5 [2,3] (1,5) {1,5}", "a <=> b <-> c <= d >= e != f => g -> h == i ** 2", "1 × 10^5, 2.5e3, 1e1e1, 3 \\times 10^{-4}, 10⁻³",
                   "4.0 x 10^3 and 4.0x10^3 and 4 * 10**3 and 4·10^3 and 4 ⋅ 10^3 and 2 x", "x_{max} = Q1 + V2 + ΔH° + f′(x) + T'' + v₁ + kₘ",
                   "12 345 678 and 1,234,567 and 0.5 and .5 and 1. and 1,5", "$x = 1 " * 5, "e5 E5 2e 2e+ 2e-3 2E−11 2e3x", "1" + "0" * 400 + " = 1"]


@pytest.mark.parametrize("text", FAST_PATH_TEXTS)
def test_lexer_extents_agree_with_and_without_values(text):
    view = reading_view(text)
    for mode in ("plain", "latex"):
        full = lex(view, mode=mode).tokens
        bare = lex(view, mode=mode, values=False).tokens
        assert [t[:5] + t[6:] for t in full] == [t[:5] + t[6:] for t in bare]


def test_lexer_fast_paths_read_brackets_operators_and_scientific_forms():
    toks = lex("(a) [b] <=> c 1 × 10^5 2.5e3 1e1e")
    assert [(t.kind, t.text) for t in toks.tokens[:6]] == [("LPAR", "("), ("IDENT", "a"), ("RPAR", ")"), ("LPAR", "["), ("IDENT", "b"), ("RPAR", "]")]
    assert toks.tokens[3].space and not toks.tokens[4].space
    assert [(t.kind, t.text) for t in toks.tokens[6:]] == [("REL", "⇔"), ("IDENT", "c"), ("NUM", "1 × 10^5"), ("NUM", "2.5e3"), ("NUM", "1"),
                                                         ("IDENT", "e"), ("NUM", "1"), ("IDENT", "e")]
    assert toks.tokens[8].value.value == 100000 and toks.tokens[9].value.value == 2500
    # a comma inside brackets separates numbers; outside, one or two digits after it are a decimal comma
    inside = lex("(1,5)").tokens
    assert [t.text for t in inside] == ["(", "1", ",", "5", ")"]
    assert [t.text for t in lex("x = 1,5").tokens][-1] == "1,5"


# --------------------------------------------------------------------------- adversarial, new paths
ADVERSARIAL = [
    ("sum_huge_bounds", "mathematics_aa", "$\\sum_{k=1}^{99999999999} k = 1$ and Σ_{k=-9999}^{9999} k = 0"),
    ("sum_nested", "mathematics_aa", "$" + "\\sum_{k=1}^{4} " * 60 + "k = 1$"),
    ("sum_index_storm", "mathematics_aa", "Σ_{k=1}^{24} " + "k × " * 120 + "k = 5"),
    ("euler_nested", "mathematics_aa", "$e^{" * 300 + "1" + "}" * 300 + " = 2$"),
    ("euler_huge", "mathematics_aa", "e^{1e999999} = 1 and e^{" + "9" * 5000 + "} = 2"),
    ("unit_group_storm", "chemistry", "c = 4.18 J/(" + "g K " * 3000 + ")"),
    ("unit_group_unclosed", "chemistry", "c = 4.18 J/(" + "(" * 2000),
    ("derivative_storm", "mathematics_aa", "f′(x) = 3x² − 2. " + "f′(2) = 3 × 2² − 2 = 10. " * 200),
    ("function_self", "mathematics_aa", "f(x) = f(x) + 1, so f(2) = f(2) + 1 = 3."),
    ("bool_defs", "computer_science", "M = " + "(A ∧ " * 200 + "B" + ")" * 200 + "\n\n| A | B | M |\n|---|---|---|\n| 0 | 0 | 0 |"),
    ("signed_prose", "physics", "x = 2 + 2 = 4. It is therefore " + "−4 −3 −2 " * 2000),
    ("order_chain", "physics", " > ".join(f"T_{i} = {i}" for i in range(400))),
    ("factorisation_deep", "mathematics_aa", "x = " + "(x − 1)" * 300 + " = 0"),
    ("hex_storm", "computer_science", "2A₁₆ " * 4000 + "= 42"),
    ("confusable_e", "mathematics_aa", "е^{2} = 7.39 and ℯ^{2} = 7.39"),
]


@pytest.mark.parametrize("name, profile, text", ADVERSARIAL, ids=[a[0] for a in ADVERSARIAL])
def test_new_paths_are_bounded_on_adversarial_input(name, profile, text):
    clear_document_cache()
    t = time.perf_counter()
    d = build_document(text, "Show that x = 1 (y = 2).", profile)
    assert time.perf_counter() - t < 3.0, name
    assert not [f for f in d.findings if f.code == "ST-INTERNAL-001"], name
    assert all(f.severity in ("info", "warning") for f in d.findings)


@pytest.mark.parametrize("name, profile, text", ADVERSARIAL[:8], ids=[a[0] for a in ADVERSARIAL[:8]])
def test_new_paths_never_raise_out_of_the_hub(name, profile, text):
    subject = {"mathematics_aa": MATH, "chemistry": CHEM, "computer_science": CS, "physics": PHYS}[profile]
    t = time.perf_counter()
    rc = receipt(subject, "Calculate x.", text)
    assert time.perf_counter() - t < 8.0, name
    assert rc.status.value != "REJECTED"
