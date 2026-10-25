"""STEM repair 12: the twelfth independent test of the STEM completion found four problems. Three are in the STEM front end; each is fixed
at its cause, for its whole class, and every new reading has a clean control (correct working is never flagged):

* rule ``identity-variable`` (high): an identity checked from the trivially true premise (a derivative against the power rule, an
  antiderivative by its derivative, a definite integral's evaluation bracket, a Given function against the request's, a factorisation)
  took the request's value of its variable as a value the step substitutes ('bindings included: t'), so an identity whose stated side lacks
  the variable ('d/dt (6 − 6t) = −6t' beside the request's 't = 1') was decided at that one value and held: ENTAILED, satisfied, no finding,
  a failure shown as a success. An identity is stated for every value of its own variables: they take no binding and no formula, and the
  check's detail says so;
* rule ``prose-base`` for numerals with letter digits (medium): a hexadecimal numeral with letter digits in prose ('In hexadecimal, 1000 is
  3E9.', '3E9₁₆', 'In base 16, …', '1000 in denary is 3E9 in hexadecimal.', 'The hexadecimal number 3E9 is 1000 in denary.') was no number to
  the front end, so the restatement had no check. In a computer-science answer a numeral of digits and the capital letters A to F (or of
  digits and small letters, at least one of each) is read in base 16 where the words beside it name that base. Closing the class found two
  false failures of the same rule on correct working, fixed with it: a numeral set equal with '=' to one whose base the words after it name
  ('1000 = 3E8 in hexadecimal.', '1000 = 1111101000 in binary.') was written arithmetic on decimal numerals, and a base phrase opening the
  clause with no comma ('In binary 1000 is 1111101000.', 'In octal 64 is 100.') was read as the first numeral's base only;
* rule ``inline-restatement`` after an approximation word (medium): a value after ', which is about' or ', about …' right after the chain
  its line closes was no restatement ('= 2.67 A, which is about 2.6 A', '= 37.7%, about 37%'), so a wrong rounding had no check. Such a
  value restates the chain, the approximation word naming its rounding: τ 0, as for every restated result (R8).

The fourth (a circular translation in affine or scaled form) is the overseer's: tests/overseer/test_stem_repair12.py.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.tolerance import STEM_TOLERANCE_RULE, TAU_APPROX, tau_for

from .test_stem_repair5 import PROFILE, SPEC, before, clean, decide, failing, holds, new, replaced, task, warnings

MA_END = "Marks shown are a provisional allocation."
CS_END = "Next step: trace"
PH_FALL = "the current from the cell falls, from 4.1 A to 2.7 A."
PH_LINE = "the current from the cell falls: I = 12 V / 4.5 Ω = 2.67 A"
ES_T = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
ES_LINE = "From B to C the dissolved oxygen falls by (6.1 − 3.8) ÷ 6.1 × 100 = "


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"(rule {rule})" in c[3]]


def _doc(tid: str, text: str):
    clear_document_cache()
    data = tuple(t["text"] for t in SPEC[tid].get("supplied_texts") or [])
    return build_document(text, SPEC[tid]["question"], PROFILE[tid], **({"data": data} if data else {}))


# ============================================================================================ rule identity-variable
@pytest.mark.parametrize("line,ok", [
    ("The rate of change of a is d/dt (6 − 6t) = −6t.", False), ("The rate of change of a is d/dt (6 − 6t) = −6.", True),
    ("Also d/dt (5t + 2) = 5t.", False), ("Also d/dt (5t + 2) = 5.", True),
    ("Also ∫4t dt = 4t.", False), ("Also ∫4t dt = 2t² + C.", True),
    ("Also ∫₀¹ 4t dt = [4t]₀¹.", False), ("Also ∫₀¹ 4t dt = [2t²]₀¹.", True),
    ("Also ∫(6t − 3t²) dt = 6 − 6t.", False), ("Also ∫(6t − 3t²) dt = 3t² − t³ + C.", True),
    ("Also ∫2 dt = t².", False), ("Also ∫2 dt = 2t + C.", True),
])
def test_an_identity_in_the_request_s_variable_is_decided_for_every_value(line, ok):
    """maa-t13's request gives 't = 1' (part (a)). Before, the wrong identities among these took it as a substituted value of t and held
    (−6 = −6 · 1, 4 = 4 · 1, …): ENTAILED with no finding. Each is decided for every value of t now, as an error, and the right ones hold."""
    checks, findings = new("maa-t13", before("maa-t13", MA_END, line, sep="\n"))
    assert len(checks) == 1 and holds(checks[0]) is ok and checks[0][0] == "alg" and checks[0][2] == "error", checks
    assert "bindings included" not in checks[0][3], checks
    assert failing(checks) == ([] if ok else checks) and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("line,stated", [
    ("The rate of change of a is d/dt (6 − 6t) = −6t.", "'d/dt (6 − 6t) = −6t'"), ("Also ∫4t dt = 4t.", "'∫4t dt = 4t'"),
    ("Also ∫₀¹ 4t dt = [4t]₀¹.", "'∫₀¹ 4t dt = [4t]₀¹'"), ("Also d/dt (5t + 2) = 5t.", "'d/dt (5t + 2) = 5t'"),
])
def test_the_identity_s_problem_gives_its_variable_no_value_and_its_detail_says_so(line, stated):
    """The problem the engine decides: the trivially true premise, no binding and no formula of t, and the detail names the reading
    (rule identity-variable). Before, the premises held 'B_t: t = 1' and the detail said 'bindings included: t'."""
    text = before("maa-t13", MA_END, line, sep="\n")
    plan = build_checks(_doc("maa-t13", text), report_id="r", request_id="q")
    picked = [pc for pc in plan.checks if stated in pc.description]
    assert len(picked) == 1, [pc.description[:80] for pc in plan.checks]
    pc = picked[0]
    ids = [p["id"] for p in pc.problem["premises"]]
    assert "PREV" in ids and not [i for i in ids if i.startswith(("B_", "FORMULA"))], ids
    assert "an identity, stated for every value of t: no binding or formula of it is included, so it is decided for every value (rule " \
           "identity-variable)" in pc.description


@pytest.mark.parametrize("line,ok", [("Given: v(t) = 3.", False), ("Given: v(t) = 3t².", False), ("Given: v(t) = 6t − 3t².", True)])
def test_a_given_function_is_set_against_the_request_s_for_every_value(line, ok):
    """'Given: v(t) = 3.' agrees with the request's v(t) = 6t − 3t² at t = 1 only: before, it held there. The Given is set against the
    request's function for every value of t, at warning severity (that it restates the request's function is a reading)."""
    checks, _f = new("maa-t13", before("maa-t13", MA_END, line, sep="\n\n"))
    gf = _rule(checks, "given-function")
    assert len(gf) == 1 and holds(gf[0]) is ok and gf[0][2] == "warning" and "bindings included" not in gf[0][3], checks
    assert failing(checks) == ([] if ok else gf), checks


@pytest.mark.parametrize("text,ok", [
    ("d/dt (6 − 6t) = −6t", False), ("d/dt (6 − 6t) = −6", True), ("∫6t dt = 6t", False), ("∫6t dt = 3t² + C", True),
    ("t² − 3t = t(t − 2) = 0", False), ("t² − 3t = t(t − 3) = 0", True),
])
def test_an_identity_is_decided_alike_with_and_without_a_request_that_gives_its_variable_a_value(text, ok):
    req = ("A particle moves in a straight line. Its velocity, v m s^-1, at time t seconds is given by v(t) = 6t - 3t^2, for 0 <= t <= 3.\n"
           "(a) Find the acceleration of the particle when t = 1. [2]")
    with_req, _f = decide(text, req, "mathematics_aa")
    without, _f2 = decide(text, None, "mathematics_aa")
    assert [(c[0], c[1], c[2]) for c in with_req] == [(c[0], c[1], c[2]) for c in without], (with_req, without)
    assert len(with_req) == 1 and holds(with_req[0]) is ok, with_req


def test_a_step_from_a_stated_relation_still_binds_the_values_it_substitutes():
    """The control: rule identity-variable reads identities only. ph-t13's '1/R = 1/4.0 Ω + 1/6.0 Ω' is a step from the stated
    '1/R = 1/R₁ + 1/R₂', and it still binds the resistances it substitutes, and holds."""
    checks, _f = task("ph-t13", SPEC["ph-t13"]["response_text"])
    step = [c for c in checks if c[0] == "alg" and "'1/R = 1/4.0 Ω + 1/6.0 Ω'" in c[3]]
    assert len(step) == 1 and holds(step[0]) and "bindings included: R_1, R_2" in step[0][3] and "identity-variable" not in step[0][3], step
    assert not failing(checks)


# ============================================================================================ rule prose-base, letter digits
@pytest.mark.parametrize("line,ok", [
    ("In hexadecimal, 1000 is 3E9.", False), ("In hexadecimal, 1000 is 3E8.", True),
    ("In hexadecimal, 1000 is 3E9₁₆.", False), ("In hexadecimal, 1000 is 3E8₁₆.", True),
    ("In base 16, 1000 is 3E9.", False), ("In base 16, 1000 is 3E8.", True),
    ("1000 in denary is 3E9 in hexadecimal.", False), ("1000 in denary is 3E8 in hexadecimal.", True),
    ("The hexadecimal number 3E9 is 1000 in denary.", False), ("The hexadecimal number 3E8 is 1000 in denary.", True),
    ("In hexadecimal, 255 is FE.", False), ("In hexadecimal, 255 is FF.", True),
    ("In hexadecimal, 4095 is FFE.", False), ("In hexadecimal, 4095 is FFF.", True),
    ("In hex, 26 is 1B.", False), ("In hex, 26 is 1A.", True),
    ("In hexadecimal, 1000 is 3e9.", False), ("In hexadecimal, 1000 is 3e8.", True),
])
def test_a_hexadecimal_restatement_with_letter_digits_is_read(line, ok):
    """The tester's five shapes and the class: a numeral of letters alone, small letters, 'hex'. Before, none had a check or an ST code."""
    checks, findings = new("cs-t13", before("cs-t13", CS_END, line))
    assert len(checks) == 1 and checks[0][0] == "base" and holds(checks[0]) is ok and checks[0][2] == "error", checks
    assert "(rule prose-base)" in checks[0][3] and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("line", [
    "The largest byte value, 255, is FE.",                          # no word names a base: letters are never read as a numeral
    "In hexadecimal, the digits A to F stand for 10 to 15.",        # no restatement
    "In hexadecimal, 171 is ab.",                                   # small letters alone: a word ('ab', 'be', 'face'), never a numeral
    "Our team FF has 255 members.",
])
def test_letter_digits_no_words_name_base_16_for_are_no_numeral(line):
    clean("cs-t13", before("cs-t13", CS_END, line))
    checks, _f = new("cs-t13", before("cs-t13", CS_END, line))
    assert checks == [], checks


def test_letter_digits_are_read_in_computer_science_answers_only():
    assert decide("In hexadecimal, 255 is FE.", None, "physics")[0] == []
    checks, _f = decide("In hexadecimal, 255 is FE.", None, "computer_science")
    assert [(c[0], c[1]) for c in checks] == [("base", "COUNTEREXAMPLE")], checks


@pytest.mark.parametrize("text,ok", [
    ("1000 = 3E8 in hexadecimal.", True), ("1000 = 3E9 in hexadecimal.", False), ("1000 = 1111101000 in binary.", True),
    ("1000 = 1111101100 in binary.", False), ("255 = FF in hexadecimal.", True), ("255 = FE in hexadecimal.", False),
    ("So 1000 = 3E8 in hexadecimal.", True),
])
def test_a_numeral_set_equal_to_one_whose_base_the_words_after_it_name_is_a_base_conversion(text, ok):
    """Before, '1000 = 3E8 in hexadecimal.' and '1000 = 1111101000 in binary.' were written arithmetic on decimal numerals (3E8 as
    3 × 10⁸): correct working failed (INT-SUBJ-001), and '255 = FF' was an equation in the unknown F."""
    checks, findings = decide(text, None, "computer_science")
    assert len(checks) == 1 and checks[0][0] == "base" and holds(checks[0]) is ok and "(rule prose-base)" in checks[0][3], checks
    assert not warnings(findings), findings
    # the same line inside the recorded answer (its offsets are the statement's, not the document's start)
    checks, findings = new("cs-t13", before("cs-t13", CS_END, text))
    assert len(checks) == 1 and checks[0][0] == "base" and holds(checks[0]) is ok, checks
    assert failing(checks) == ([] if ok else checks) and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("text,ok", [
    ("In binary 1000 is 1111101000.", True), ("In binary 1000 is 1111101100.", False), ("In octal 64 is 100.", True), ("In octal 100 is 64.", True),
    ("In octal 64 is 101.", False), ("In hexadecimal 1000 is 3E8.", True), ("In hexadecimal 1000 is 3E9.", False), ("Written in binary 6 is 110.", True),
    ("In hexadecimal, the number 1000 is 3E8.", True), ("In hexadecimal, the number 1000 is 3E9.", False), ("In binary the number 5 is 100.", False),
])
def test_a_base_phrase_opening_the_clause_is_read_either_way_with_or_without_a_comma(text, ok):
    """Before, 'In binary 1000 is 1111101000.' and 'In octal 64 is 100.' failed correct working: with no comma the phrase was read as the
    first numeral's base only ('binary 1000', as in 'the binary number 1000'). Read as the opening phrase it is, as with the comma."""
    checks, findings = decide(text, None, "computer_science")
    assert len(checks) == 1 and checks[0][0] == "base" and holds(checks[0]) is ok, checks
    assert not warnings(findings), findings
    checks, findings = new("cs-t13", before("cs-t13", CS_END, text))
    assert len(checks) == 1 and checks[0][0] == "base" and holds(checks[0]) is ok and failing(checks) == ([] if ok else checks), checks


@pytest.mark.parametrize("text", ["In binary, the answer has 5 bits.", "In binary, a number is stored as 101.", "In binary the number of bits is 5.",
                                  "The speed of light is 3E8 m/s."])
def test_no_restatement_no_base_check(text):
    assert decide(text, None, "computer_science")[0] == []


# ============================================================================================ rule inline-restatement, approximation words
@pytest.mark.parametrize("tail,ok", [
    (", which is about 2.6 A.", False), (", which is about 2.7 A.", True), (", about 2.6 A to 2 s.f.", False), (", about 2.7 A to 2 s.f.", True),
    (", approximately 2.6 A.", False), (", roughly 2.7 A.", True), (", i.e. about 2.6 A.", False), (", so about 2.7 A.", True),
    (", or about 2.6 A.", False), (", which is approximately 2.7 A.", True), (", which is nearly 2.6 A.", False),
    # a rounding verb, 'equal to' after the approximation word, the value in brackets
    (", which rounds to 2.6 A.", False), (", which rounds to 2.7 A.", True), (", rounded to 2.7 A.", True), (", rounded up to 2.6 A.", False),
    (", which is approximately equal to 2.6 A.", False), (", which is approximately equal to 2.7 A.", True), (" (about 2.6 A).", False),
    (" (about 2.7 A).", True),
])
def test_a_value_after_an_approximation_word_restates_the_chain_its_line_closes(tail, ok):
    """ph-t13: the tester's ', which is about' and ', about … to 2 s.f.' and the class (each approximation word after each connective, or
    alone). Before, none had a check. The restatement is an error check with τ 0 (R8), its detail naming the reading."""
    checks, findings = new("ph-t13", replaced("ph-t13", PH_FALL, PH_LINE + tail))
    res = [c for c in checks if c[0] == "res"]
    assert len(res) == 1 and holds(res[0]) is ok and res[0][2] == "error", checks
    if "round" not in tail:  # an approximation word names the rounding (a rounding verb states it: τ is 0 for every restated result)
        assert ("τ = 0 (a restated result: the approximation word before it names its rounding, R8), on the line of working it restates (rule "
                "inline-restatement)") in res[0][3], res[0][3]
    assert failing(checks) == ([] if ok else res), checks


@pytest.mark.parametrize("value,ok", [("37%", False), ("38%", True)])
def test_a_percentage_restated_after_about(value, ok):
    checks, _f = new("ess-t13", replaced("ess-t13", ES_T, ES_LINE + f"37.7%, about {value}."))
    res = [c for c in checks if c[0] == "res"]
    assert len(res) == 1 and holds(res[0]) is ok, checks
    assert failing(checks) == ([] if ok else res), checks


def test_a_value_whose_statement_closes_no_chain_before_it_is_no_inline_restatement():
    """The photon line of the labelled corpus: '4.0 × 10⁻¹⁹ J, which is about 2.5 eV' follows a prose quantity, not a chain its
    statement closes, so it is read by the other readings (the restatement of the chain on the line before), never as an inline one."""
    text = ("The energy of a photon is E = hf, where h is the Planck constant and f = 5.0 × 10¹⁴ Hz.\nE = hf = 4.0 × 10⁻¹⁹ J\n"
            "So each photon carries 4.0 × 10⁻¹⁹ J, which is about 2.5 eV.")
    checks, _f = decide(text, "Light of frequency 5.0 × 10¹⁴ Hz falls on a metal surface. Calculate the energy of one photon.", "physics")
    assert not [c for c in checks if "(rule inline-restatement)" in c[3]], checks


def test_r8_bands_a_restated_result_with_no_tau_after_an_approximation_word_too():
    """R2's 1/20 for an approximation word is every check's but a restated result's (R8): tau_for states what the restatement check has
    always applied, and the rule says so."""
    assert tau_for("res", approx=True, exact_mode=False) == 0 == tau_for("res", approx=False, exact_mode=False)
    for kind in ("eq", "cnv", "cmp", "giv", "sub-match", "sol-root", "tgt"):
        assert tau_for(kind, approx=True, exact_mode=False) == TAU_APPROX, kind
    assert "but a restated result (R8: an approximation word before a restated value names its rounding" in STEM_TOLERANCE_RULE
    assert "R8 restated result: |S − S′| ≤ h(S) + h(S′) in SI, with no τ, also after an approximation word" in STEM_TOLERANCE_RULE
    # executed: 2.6 against 2.67 is outside h(2.6) + h(2.67) = 0.055, and would be inside with τ = 1/20 (0.1335)
    checks, _f = new("ph-t13", replaced("ph-t13", PH_FALL, PH_LINE + ", which is about 2.6 A."))
    assert abs(Fraction("2.67") - Fraction("2.6")) > Fraction("0.055") and abs(Fraction("2.67") - Fraction("2.6")) < Fraction("0.055") + Fraction(1, 20) * Fraction("2.67")
    assert [c[0] for c in failing(checks)] == ["res"], checks


# ============================================================================================ every recorded STEM answer
@pytest.mark.parametrize("tid", ["ph-t13", "ph-p7b", "maa-t13", "maa-p7b", "mai-t13", "bi-t13", "ess-t13", "ch-t13", "cs-t13"])
def test_no_recorded_answer_fails_any_check(tid):
    """The new readings add no check to the recorded answers' that fails, and no warning."""
    every, findings = task(tid, SPEC[tid]["response_text"])
    assert not failing(every), failing(every)
    assert not [f for f in findings if f[0] in ("ST-DIM-001", "ST-DIM-002", "INT-SUBJ-004")], findings
