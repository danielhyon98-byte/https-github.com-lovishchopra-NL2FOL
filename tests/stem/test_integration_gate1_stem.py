"""Integration gate 1 (before arena round 8): the STEM findings of the independent lenses, each reproduced and fixed at its
cause, with clean controls (correct working that must hold and wrong working that must still fail).

* the substitution check's band took the half-width of its numeric side in the written unit (um, nm, mmol, mg) while comparing
  in SI, so every value of that order passed (ho_d_ue_bio_magnification, docs/ARGUMENT_DIAGNOSTICS.md section 20.10);
* a bare stated result of a substitution whose symbols are bound in two units of one dimension passed as written, and a chain of
  bare numerals repeating I = 12 mm and M = 400 planned no unit companion (rule mixed-units, the pure-number accounting);
* bare numerals substituted for symbols the answer does not bind were never set against the request (rule request-substitution;
  a booklet constant accounted in the unit companion);
* probability notation P(A), P(X), P(A′), P(B | A), P(A ∪ B) is one symbol;
* a root set joined by 'or' (with or without a repeated 'x =') is one conclusion, and a '±' step inside a chain is two equations
  (rule or-roots; rerun-stem-soundness-10);
* a line opened by 'Expanding,', 'Simplifying,', 'Solving,', 'Factorising,' or 'Collecting terms,' is a step;
* a superscript letter exponent (2ˣ, eˣ) is read as a power (named ST-UNDEC-001 as 2^x is);
* the year and the hectare are units, and an unknown unit fails as a warning only where another reading was possible;
* a comparison the prose states of a symbol the working computed is checked (rule value-comparison);
* a binary numeral in prose read in two's complement is checked (rule binary-reading);
* an angle in degrees set against a bare computed side keeps the as-written reading beside the radian one (rule degree-reading);
* a bare count beside an amount of data, and kB, MB, GB with two readings (rule data-count);
* binary numerals the line converts, in nibbles, in two's complement (rule binary-reading);
* a value whose clause names another quantity is no restatement (stem-precision-1, broadened);
* a compound quantity in prose ('4 minutes 30 seconds') is one quantity, and a request value stated in one part of the request
  ties a symbol in that part only (rule unbound-substitution);
* a line of numerals grouped with spaces or apostrophes, and a one-line '|−3| + |2| = 5', are the answer proper (INT-REQ-012);
* a bare stated side that re-expresses a side with units is read in its statement's units (rule unit-system);
* a stated rounding followed by a contrast names no later value;
* the hectare in a conversion, and '/' read as the integer quotient where the statement says integer division.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.request_parser import count_answer_words
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.hub_hooks import STEM_HOOKS
from epinoic_logic.stem.units import is_data_unit, parse_unit

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"integration-gate-1-stem-key-0123456789"
_DEFINITE = {"ENTAILED", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE"}
SUBJECTS = {"physics": "Physics", "chemistry": "Chemistry", "biology": "Biology", "ess": "Environmental Systems and Societies",
            "mathematics_aa": "Mathematics: Analysis and Approaches", "mathematics_ai": "Mathematics: Applications and Interpretation",
            "computer_science": "Computer Science"}


def _holds(pc, res):
    s = res.status.value
    if s == pc.expected_if_sound and not any(d.code == "E108" for d in res.diagnostics):
        return True
    if s in _DEFINITE and s != pc.expected_if_sound:
        return None if (s == "INCONSISTENT_PREMISES" and not pc.inconsistent_is_failure) else False
    return None


def decide(text: str, profile: str = "physics", request: str | None = None):
    """Every planned check of ``text`` decided by the engine: ``(check id, holds, description, severity)``, and the finding codes."""
    doc = build_document(text, request, profile)
    plan = build_checks(doc, report_id="r1", request_id="q1")
    out = []
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
        out.append((pc.check_id, _holds(pc, res), pc.description, pc.failure_severity))
    return out, [f.code for f in list(doc.findings) + list(plan.findings)]


def held(text: str, profile: str = "physics", request: str | None = None, prefix: str = "stem-") -> list:
    checks, _f = decide(text, profile, request)
    return [h for cid, h, _d, _s in checks if cid.startswith(prefix)]


def receive(profile: str, answer: str, request: str = "Answer the question."):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def failed(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is False}


def errors(rc) -> list[str]:
    return [f.code for f in rc.findings if f.severity == "error"]


def no_stem_fault(rc) -> bool:
    """No failed check, no INT-SUBJ finding and no warning ST code beyond the undecided and parse ones."""
    return (not failed(rc) and not any(f.code.startswith("INT-SUBJ") for f in rc.findings)
            and not [f for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")
                     and not f.code.startswith(("ST-UNDEC", "ST-PARSE"))])


# ============================================================================================ the substitution band (blocker)
MAG = "A cell is drawn 12 mm long at a magnification of x400. Calculate the actual length of the cell in um."


@pytest.mark.parametrize("stated", ["99 um", "0.030 um", "3000 um", "0.30 mm", "450 µm", "9000 µm"])
def test_a_substituted_result_in_a_small_unit_is_compared_with_its_own_half_width(stated):
    assert held(f"I = 12 mm and M = 400.\nA = I/M = {stated}", "biology", prefix="stem-sub") == [False], stated


@pytest.mark.parametrize("stated", ["30 um", "30 µm", "0.030 mm"])
def test_clean_control_the_right_magnification_result_holds(stated):
    assert held(f"I = 12 mm and M = 400.\nA = I/M = {stated}", "biology", prefix="stem-sub") == [True], stated


@pytest.mark.parametrize("text, holds", [
    ("m = 250 mg and M = 50 g mol-1.\nn = m/M = 500 mmol", False), ("m = 250 mg and M = 50 g mol-1.\nn = m/M = 50 mmol", False),
    ("m = 250 mg and M = 50 g mol-1.\nn = m/M = 5.0 mmol", True), ("m = 250 mg and M = 50 g mol-1.\nn = m/M = 0.0050 mol", True),
    ("I = 12 mm and M = 400000.\nA = I/M = 30 nm", True), ("I = 12 mm and M = 400000.\nA = I/M = 300 nm", False),
    ("d = 3.0 m and v = 1500 m s-1.\nt = d/v = 2.0 ms", True), ("d = 3.0 m and v = 1500 m s-1.\nt = d/v = 20 ms", False),
])
def test_the_band_of_a_substitution_is_in_the_reading_s_units(text, holds):
    profile = "chemistry" if "mol" in text else "physics"
    assert held(text, profile, prefix="stem-sub") == [holds], text


def test_the_magnification_case_through_the_hub_names_the_fault():
    request = "An image of a cell is 12 mm long and the magnification is x400. Find the actual length of the cell in um."
    for stated in ("0.030 um", "9000 um", "450 um"):
        rc = receive("biology", f"Given I = 12 mm and M = 400. The actual length is A = I/M = {stated}.", request)
        assert "stem-sub-1" in failed(rc) and "INT-SUBJ-001" in errors(rc), stated
    assert no_stem_fault(receive("biology", "Given I = 12 mm and M = 400. The actual length is A = I/M = 30 um.", request))


# ============================================================================================ two units of one dimension
def test_a_bare_result_of_symbols_bound_in_two_units_is_read_in_si_only():
    req = "An image of a cell is 6.0 mm long and the actual cell is 20 um long. Calculate the magnification."
    rc = receive("biology", "I = 6.0 mm and A = 20 um.\nM = I/A = 0.3", req)
    hit = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert hit and "stem_unit_error" in hit[0].message and "rule mixed-units" in hit[0].message
    assert no_stem_fault(receive("biology", "I = 6.0 mm and A = 20 um.\nM = I/A = 300", req))


def test_a_bare_numeral_chain_repeating_a_length_and_a_magnification_is_read_in_their_units():
    rc = receive("biology", "I = 12 mm and M = 400.\nA = I/M = 12/400 = 0.030 um", MAG)
    assert "stem-eq-1u" in failed(rc) and any(f.code == "INT-SUBJ-004" and "ST-UNIT-003" in f.message for f in rc.findings)
    for right in ("I = 12 mm and M = 400.\nA = I/M = 12/400 = 0.030 mm", "I = 12 mm and M = 400.\nA = I/M = 12000/400 = 30 um"):
        assert no_stem_fault(receive("biology", right, MAG)), right


# ============================================================================================ rule request-substitution
@pytest.mark.parametrize("profile, request_text, wrong, right", [
    ("physics", "A 2.0 kg mass is raised 5.0 m. Calculate the gain in gravitational potential energy.",
     "ΔEp = mgΔh = 2.0 × 9.8 × 50 = 980 J", "ΔEp = mgΔh = 2.0 × 9.8 × 5.0 = 98 J"),
    ("physics", "2.0 kg of water is heated by 10 K. The specific heat capacity of water is 4200 J kg⁻¹ K⁻¹. Calculate the energy needed.",
     "Q = mcΔT = 2.0 × 4200 × 100 = 840000 J", "Q = mcΔT = 2.0 × 4200 × 10 = 84000 J"),
    ("physics", "A wave has a speed of 340 m s⁻¹ and a frequency of 170 Hz. Calculate its wavelength.",
     "λ = v/f = 170/340 = 0.50 m", "λ = v/f = 340/170 = 2.0 m"),
    ("chemistry", "Calculate the volume of 0.50 mol of an ideal gas at 27 °C and 100 kPa.",
     "V = nRT/p = 0.50 × 8.31 × 27/100000 = 0.0011 m³", "V = nRT/p = 0.50 × 8.31 × 300/100000 = 0.012 m³"),
])
def test_a_bare_substitution_is_set_against_the_one_request_quantity_of_each_symbol(profile, request_text, wrong, right):
    rc = receive(profile, wrong, request_text)
    giv = [f for f in rc.findings if f.code == "INT-SUBJ-004" and "rule request-substitution" in f.message]
    assert giv and not errors(rc), [(f.code, f.message[:160]) for f in rc.findings]
    assert no_stem_fault(receive(profile, right, request_text)), right


def test_a_pressure_left_in_kpa_beside_a_booklet_constant_is_a_unit_error():
    req = "Calculate the volume of 0.50 mol of an ideal gas at 300 K and 100 kPa."
    rc = receive("chemistry", "V = nRT/p = 0.50 × 8.31 × 300/100 = 12 m³", req)
    assert "stem-eq-1u" in failed(rc) and not errors(rc)
    assert no_stem_fault(receive("chemistry", "V = nRT/p = 0.50 × 8.31 × 300/100000 = 0.012 m³", req))


# ============================================================================================ probability notation
def test_probability_notation_is_one_symbol_and_an_impossible_probability_is_named():
    for text in ("P(A) = 0.3 + 0.9 = 1.2", "P(X) = 1.2", "P(B) = 0.3 + 0.9 = 1.2"):
        _checks, codes = decide(text, "mathematics_ai", "Find the probability.")
        assert "ST-GIVEN-003" in codes, text
    _checks, codes = decide("P(A) = 0.3 + 0.4 = 0.7", "mathematics_ai", "Find the probability.")
    assert "ST-GIVEN-003" not in codes


@pytest.mark.parametrize("request_text, wrong, right", [
    ("P(A) = 0.3, P(B) = 0.5 and P(A ∩ B) = 0.1. Find P(A ∪ B).", "P(A ∪ B) = P(A) + P(B) − P(A ∩ B) = 0.3 + 0.6 − 0.1 = 0.8",
     "P(A ∪ B) = P(A) + P(B) − P(A ∩ B) = 0.3 + 0.5 − 0.1 = 0.7"),
    ("P(A) = 0.3, P(B) = 0.5 and P(A ∩ B) = 0.1. Find P(A ∪ B).", "P(A ∪ B) = P(A) + P(B) − P(A ∩ B) = 0.3 + 0.5 + 0.1 = 0.9",
     "P(A ∪ B) = P(A) + P(B) − P(A ∩ B) = 0.3 + 0.5 − 0.1 = 0.7"),
    ("P(A) = 0.3. Find P(A′).", "P(A′) = 1 − P(A) = 1 − 0.4 = 0.6", "P(A′) = 1 − P(A) = 1 − 0.3 = 0.7"),
    ("P(A) = 0.4 and P(B|A) = 0.5. Find P(A ∩ B).", "P(A ∩ B) = P(A) × P(B|A) = 0.4 × 0.6 = 0.24", "P(A ∩ B) = P(A) × P(B|A) = 0.4 × 0.5 = 0.2"),
])
def test_a_probability_substitution_is_checked_against_the_request(request_text, wrong, right):
    rc = receive("mathematics_ai", wrong, request_text)
    assert any(c.startswith("stem-sub") for c in failed(rc)), [(c.constraint_id, c.satisfied) for c in rc.formal_checks]
    assert no_stem_fault(receive("mathematics_ai", right, request_text)), right


# ============================================================================================ root sets and '±' steps (rule or-roots)
@pytest.mark.parametrize("request_text, answer", [
    ("Solve x² = 9.", "x² = 9 ⇒ x = −3 or x = 3"),
    ("Solve x² = 9.", "x² = 9 ⇒ x = 3 or −3"),
    ("Solve x² − 2x − 3 = 0.", "x² − 2x − 3 = 0 ⇒ x = 3 or −1"),
    ("Solve x² = 9.", "x² = 9, so x = 3 or x = −3"),
    ("Solve (x − 1)² = 4.", "(x − 1)² = 4 ⇒ x − 1 = 2 or x − 1 = −2 ⇒ x = 3 or x = −1"),
    ("Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9 ⇒ x + 2 = ±3 ⇒ x = 1 or x = −5."),
    ("Solve (x − 1)^2 = 4.", "(x − 1)² = 4 ⇒ x − 1 = ±2 ⇒ x = 3 or x = −1"),
    ("Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9, so x + 2 = ±3, so x = 1 or x = −5."),
    ("Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9\nx + 2 = ±3\nx = 1 or x = −5"),
    ("Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9 ⇒ x + 2 = 3 or x + 2 = −3 ⇒ x = 1 or x = −5"),
])
def test_a_full_root_set_and_a_plus_minus_step_inside_a_chain_raise_nothing(request_text, answer):
    rc = receive("mathematics_aa", answer, request_text)
    assert no_stem_fault(rc) and not any(f.code == "ST-ALG-001" for f in rc.structural_findings), \
        ([(c.constraint_id, c.satisfied) for c in rc.formal_checks], [f.code for f in rc.findings + rc.structural_findings])


@pytest.mark.parametrize("request_text, answer", [
    ("Solve (x + 2)^2 = 9. [2 marks]", "(x + 2)² = 9 ⇒ x + 2 = ±3 ⇒ x = 1 or x = −4."),
    ("Solve x² = 9.", "x² = 9 ⇒ x = 3 or −4"),
    ("Solve x² = 9.", "x² = 9 ⇒ x = 3"),
    ("Solve x² − 2x − 3 = 0.", "x² − 2x − 3 = 0 ⇒ x = 3 or −2"),
])
def test_control_a_wrong_or_missing_root_still_fails(request_text, answer):
    assert "INT-SUBJ-001" in errors(receive("mathematics_aa", answer, request_text)), answer


def test_a_root_list_value_that_is_not_the_whole_term_is_no_root():
    # '−2√2' after 'or' is read whole or not at all: never as −2
    rc = receive("mathematics_aa", "x² = 8, so x = 2√2 or −2√2", "Solve the equation.")
    assert not errors(rc)


# ============================================================================================ step participles
@pytest.mark.parametrize("request_text, wrong, right", [
    ("Solve 3(x − 2) = 12.", "3(x − 2) = 12\nExpanding, 3x − 2 = 12\nAdding 2 to both sides, 3x = 14\nDividing by 3, x = 14/3",
     "3(x − 2) = 12\nExpanding, 3x − 6 = 12\nAdding 6 to both sides, 3x = 18\nDividing by 3, x = 6"),
    ("Solve 5x = 20.", "5x = 20\nSimplifying, x = 5", "5x = 20\nSimplifying, x = 4"),
    ("Solve x + 3 = 10.", "x + 3 = 10\nSolving, x = 8", "x + 3 = 10\nSolving, x = 7"),
    ("Solve x² + 5x + 6 = 0.", "x² + 5x + 6 = 0\nFactorising, (x + 2)(x + 4) = 0", "x² + 5x + 6 = 0\nFactorising, (x + 2)(x + 3) = 0"),
    ("Solve 2x + 3x = 10.", "2x + 3x = 10\nCollecting terms, 6x = 10", "2x + 3x = 10\nCollecting terms, 5x = 10"),
])
def test_a_line_opened_by_a_step_participle_is_checked_as_a_step(request_text, wrong, right):
    rc = receive("mathematics_aa", wrong, request_text)
    assert any(c.startswith("stem-alg") for c in failed(rc)) and "INT-SUBJ-001" in errors(rc), wrong
    assert no_stem_fault(receive("mathematics_aa", right, request_text)), right


# ============================================================================================ superscript letter exponents
@pytest.mark.parametrize("text", ["2ˣ = 16 ⇒ x = 8", "eˣ = 5 ⇒ x = 2", "3ˣ = 81 ⇒ x = 5", "2ⁿ = 8"])
def test_a_superscript_letter_exponent_is_a_symbolic_power_named_undecided(text):
    _checks, codes = decide(text, "mathematics_aa")
    assert "ST-UNDEC-001" in codes and "ST-PARSE-001" not in codes, codes
    doc = build_document(text, None, "mathematics_aa")
    assert any("a symbolic power" in r.reason for r in doc.relations if r.outcome == "undecided")


def test_control_superscript_digits_and_combinations_keep_their_reading():
    assert held("x² = 4 ⇒ x = ±2", "mathematics_aa", prefix="stem-sol") == [True]
    doc = build_document("⁵C₂ = 10", None, "mathematics_aa")
    assert any("binomial coefficient" in r.reason for r in doc.relations if r.outcome == "undecided")


# ============================================================================================ the year, the hectare, unknown units
NPP = "GPP is 500 kJ m⁻² yr⁻¹ and respiration is 200 kJ m⁻² yr⁻¹. Calculate NPP."


def test_the_year_is_a_unit_and_an_ess_slip_is_the_report_s_error():
    rc = receive("ess", "NPP = GPP − R = 500 − 200 = 700 kJ m⁻² yr⁻¹", NPP)
    assert "INT-SUBJ-001" in errors(rc) and not any(f.code == "ST-UNIT-001" for f in rc.structural_findings)
    right = receive("ess", "NPP = GPP − R = 500 − 200 = 300 kJ m⁻² yr⁻¹", NPP)
    assert no_stem_fault(right) and not any(f.code == "ST-UNIT-001" for f in right.structural_findings)
    assert no_stem_fault(receive("ess", "x = 500 − 200 = 300 t ha⁻¹", "Calculate the yield."))


def test_an_unknown_unit_fails_as_a_warning_only_where_another_reading_was_possible():
    _c, codes = decide("x = 500 − 200 = 700 kJ m⁻² mth⁻¹", "ess")
    checks, _codes = decide("x = 500 − 200 = 700 kJ m⁻² mth⁻¹", "ess")
    assert "ST-UNIT-001" in codes and [(h, sev) for cid, h, _d, sev in checks if cid == "stem-eq-1"] == [(False, "error")]
    checks, _codes = decide("Efficiency = 150 kJ m⁻² mth⁻¹ / 1500 kJ m⁻² mth⁻¹ × 100 = 20%", "ess")
    assert [(h, sev) for cid, h, _d, sev in checks if cid == "stem-eq-1"] == [(False, "warning")]


@pytest.mark.parametrize("text, holds", [("2.5 km² = 250 ha", True), ("Area = 2.5 km² = 2.5 × 10⁶ m² = 250 ha", True), ("2.5 km² = 25 ha", False)])
def test_the_hectare_converts(text, holds):
    assert set(held(text, "ess", prefix="stem-cnv")) == {holds}, text


def test_the_year_and_the_hectare_read_with_their_factors():
    yr, ha = parse_unit("yr"), parse_unit("ha")
    assert yr.readings[0].factor == 31557600 and ha.readings[0].factor == 10000 and not yr.unknown and not ha.unknown


# ============================================================================================ rule value-comparison
@pytest.mark.parametrize("answer, holds", [
    ("R = 12/1.99 = 6.03 Ω, so R is below 6.0 Ω.", False), ("R = 12/2.01 = 5.97 Ω, so R is below 6.0 Ω.", True),
    ("R = 12/1.99 = 6.03 Ω, so R is not below 6.0 Ω.", True), ("R = 12/2.01 = 5.97 Ω, so R is not below 6.0 Ω.", False),
    ("v = 100/4.0 = 25 m s⁻¹, so v is above 20 m s⁻¹.", True), ("v = 100/6.0 = 16.7 m s⁻¹, so v is above 20 m s⁻¹.", False),
])
def test_a_comparison_in_words_of_a_computed_symbol_is_checked(answer, holds):
    checks, _codes = decide(answer, "physics", "The resistance must be below 6.0 Ω. Is it?")
    cmp = [(h, d) for cid, h, d, _s in checks if cid.startswith("stem-cmp")]
    assert [h for h, _d in cmp] == [holds] and "the comparison the prose states of the symbol the working computed" in cmp[0][1], checks


# ============================================================================================ two's complement in prose
@pytest.mark.parametrize("answer, holds", [("11111110 in two's complement is −1", False), ("11111110 in two's complement is −2", True),
                                           ("11111011 in 8-bit two's complement is -5.", True), ("11111011 in 8-bit two's complement is -4.", False)])
def test_a_two_s_complement_value_stated_in_prose_is_checked(answer, holds):
    assert held(answer, "computer_science", "What is the value in 8-bit two's complement?", prefix="stem-base") == [holds], answer


# ============================================================================================ rule degree-reading
@pytest.mark.parametrize("profile, line", [
    ("mathematics_aa", "Angle C = 180 − 50 − 60 = 70°"), ("mathematics_aa", "Each exterior angle = 360/5 = 72°"),
    ("mathematics_aa", "Interior angle = (5 − 2) × 180 / 5 = 108°"), ("mathematics_aa", "The bearing is 90 + 35 = 125°"),
    ("physics", "θ = tan⁻¹(4.0/3.0) = 53.1°"), ("mathematics_ai", "θ = sin⁻¹(0.5) = 30°"),
    ("mathematics_ai", "Sector angle for A = 30/120 × 360 = 90°"), ("mathematics_ai", "Pie sector angle = 0.25 × 360 = 90°"),
    ("mathematics_ai", "cos C = (5² + 6² − 7²)/(2 × 5 × 6) = 0.2, so C = cos⁻¹(0.2) = 78.5°"), ("mathematics_ai", "1.2 × 180/π = 68.8°"),
    ("ess", "Pie chart angle for forest = 45% × 360 = 162°"),
    # the stem-soundness-8 controls keep their reading
    ("physics", "θ = 30° = 0.524 rad"), ("physics", "2 rad = 115°"), ("physics", "180° = π rad"), ("mathematics_aa", "45° = π/4 rad = 0.785 rad"),
])
def test_an_angle_in_degrees_against_a_bare_side_holds(profile, line):
    assert set(held(line, profile, prefix="stem-eq")) == {True}, line


@pytest.mark.parametrize("profile, line", [
    ("mathematics_aa", "Angle C = 180 − 50 − 60 = 80°"), ("physics", "θ = 30° = 0.624 rad"), ("physics", "θ = tan⁻¹(4.0/3.0) = 63.1°"),
    ("mathematics_ai", "θ = sin⁻¹(0.5) = 60°"), ("mathematics_ai", "1.2 × 180/π = 78.8°"), ("ess", "Pie chart angle for forest = 45% × 360 = 172°"),
])
def test_control_a_wrong_angle_still_fails(profile, line):
    assert False in held(line, profile, prefix="stem-eq"), line


def test_a_degree_radian_conversion_written_with_radians_is_still_compared_in_radians_only():
    checks, _codes = decide("θ = 30° = 0.524 rad.")
    assert "a degree read as π/180 rad" in next(d for cid, _h, d, _s in checks if cid == "stem-eq-1")


# ============================================================================================ rule data-count
@pytest.mark.parametrize("line", ["2 KiB = 2 × 1024 = 2048 bytes", "2^10 = 1024 bytes = 1 KiB", "64 bits = 64/8 = 8 bytes", "1440000 bytes = 1.44 MB",
                                  "size = 800 × 600 × 3 bytes = 1440000 bytes = 1.44 MB"])
def test_data_size_working_holds(line):
    assert set(held(line, "computer_science")) == {True}, line


@pytest.mark.parametrize("line", ["2 KiB = 2 × 1024 = 2148 bytes", "64 bits = 64/8 = 9 bytes", "1440000 bytes = 1.54 MB",
                                  "size = 800 × 600 × 3 bytes = 1540000 bytes", "2.00 KiB = 2.00 × 1000 = 2000 bytes",
                                  "16 bits = 1 byte"])
def test_control_wrong_data_size_working_fails(line):
    assert False in held(line, "computer_science"), line


def test_decimal_multiples_of_the_byte_have_both_readings():
    mb = parse_unit("MB")
    assert [r.factor for r in mb.readings] == [8 * 10 ** 6, 8 * 1024 ** 2] and mb.ambiguity_code == "ST-UNIT-002" and is_data_unit(mb)
    assert is_data_unit(parse_unit("bytes")) and not is_data_unit(parse_unit("%")) and not is_data_unit(parse_unit("m"))


# ============================================================================================ rule binary-reading
@pytest.mark.parametrize("request_text, answer", [
    ("Convert the binary number 10110110 to hexadecimal.", "10110110 = B6 in hexadecimal"),
    ("Convert the binary number 10110110 to hexadecimal.", "1011 0110 = B6 in hexadecimal"),
    ("Convert the 8-bit two's complement number 11111011 to denary.", "1111 1011₂ = −5 in two's complement"),
    ("Convert the 8-bit two's complement number 11111011 to denary.", "11111011 = −128 + 64 + 32 + 16 + 8 + 2 + 1 = −5"),
    ("Convert the 8-bit two's complement number 11010110 to denary.", "11010110 = −128 + 64 + 16 + 4 + 2 = −42"),
    ("Convert 42 to 8-bit binary.", "42 = 00101010"),
    ("Convert 10110110 to denary.", "10110110 = 128 + 32 + 16 + 4 + 2 = 182"),
])
def test_binary_conversions_hold(request_text, answer):
    assert no_stem_fault(receive("computer_science", answer, request_text)), answer


@pytest.mark.parametrize("request_text, answer", [
    ("Convert the binary number 10110110 to hexadecimal.", "10110110 = B7 in hexadecimal"),
    ("Convert 42 to 8-bit binary.", "42 = 00101011"),
    ("Convert 10110110 to denary.", "10110110 = 128 + 32 + 16 + 4 + 2 = 184"),
    ("Convert the 8-bit two's complement number 11111011 to denary.", "11111011 = −128 + 64 + 32 + 16 + 8 + 2 + 1 = −6"),
])
def test_control_wrong_binary_conversions_fail(request_text, answer):
    assert "INT-SUBJ-001" in errors(receive("computer_science", answer, request_text)), answer


def test_a_decimal_sum_s_value_keeps_its_decimal_reading():
    assert set(held("1011₂ = 8 + 2 + 1 = 11 and 0x2A = 42 and 377₈ = 255", "computer_science")) == {True}


# ============================================================================================ stem-precision-1, broadened
@pytest.mark.parametrize("profile, text", [
    ("mathematics_aa", "x = 15/3 = 5. Each item costs the same, so a cost of 2 per item."),
    ("physics", "η = 5.166/5.94 × 100 = 87%. The kettle is not ideal, so it wastes 13% of the energy."),
    ("biology", "χ² = 104.976 + 87.616 + 99.856 + 92.416 = 384.864. Four classes, so df is 3."),
    ("biology", "χ² = 3.2 + 1.1 + 0.4 = 4.7. There are 3 categories, so there are 2 degrees of freedom."),
    ("computer_science", "mid = (0 + 8) // 2 = 4. The target is larger, so the loop runs 3 times."),
    ("computer_science", "mid = (0 + 8) // 2 = 4. The target is larger, so low becomes 5."),
])
def test_a_value_naming_another_quantity_is_no_restatement(profile, text):
    assert held(text, profile, prefix="stem-res") == [], text


@pytest.mark.parametrize("profile, text", [
    ("physics", "a = (20 − 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 6.0 m s⁻²."),
    ("mathematics_aa", "x = 15/3 = 5. So x is 6."),
    ("physics", "η = 5.166/5.94 × 100 = 87%. So the efficiency is 78%."),
    ("mathematics_aa", "n = 24/8.0 = 3. So there are 4 half-lives."),
    ("mathematics_aa", "D = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4%\nTo the nearest whole number, the decrease is 61%."),
])
def test_control_a_wrong_restatement_of_the_chain_still_fails(profile, text):
    assert held(text, profile, prefix="stem-res") == [False], text


def test_degrees_of_freedom_are_no_angle():
    doc = build_document("There are 2 degrees of freedom.", None, "biology")
    assert not [pv for pv in doc.prose_values if "°" in str(pv.node) or "degree" in str(pv.node)]


# ============================================================================================ compound request quantities and part ties
KETTLE = ("A kettle rated 2.2 kW heats water in 4 minutes 30 seconds.\n(a) Calculate the energy supplied in this time.\n"
          "(b) The kettle is left on for another 30 s. Calculate the energy supplied in those 30 s.")


def test_a_compound_request_time_is_one_quantity_and_another_part_s_value_ties_nothing():
    answer = "(a)\nE = Pt = 2200 W × 270 s = 5.94 × 10⁵ J\n\n(b)\nE = Pt = 2200 W × 30 s = 6.6 × 10⁴ J"
    assert no_stem_fault(receive("physics", answer, KETTLE))
    assert no_stem_fault(receive("physics", answer, KETTLE.replace("4 minutes 30 seconds", "270 s")))
    req = "A kettle rated 2.2 kW heats water in 4 minutes 30 seconds. Calculate the energy supplied."
    rc = receive("physics", "E = Pt = 2200 W × 240 s = 5.28 × 10⁵ J", req)
    assert "stem-giv-1" in failed(rc) and not errors(rc)
    doc = build_document("x", "It heats water in 4 minutes 30 seconds and then 1 h 2 min 3 s.", "physics")
    assert sorted(float(q[0].number.value) for q in doc.request.quantities) == [270.0, 3723.0]


# ============================================================================================ INT-REQ-012 for lines of numerals
@pytest.mark.parametrize("profile, request_text, answer", [
    ("mathematics_ai", "Answer the question.", "21 131.40 − 18 000.00 = 3 131.40"),
    ("mathematics_ai", "Answer the question.", "21 131,40 − 18 000,00 = 3 131,40"),
    ("mathematics_ai", "Answer the question.", "21'131.40 − 18'000 = 3131.40"),
    ("mathematics_ai", "Answer the question.", "1 000 000 × 0.05 = 50 000"),
    ("mathematics_aa", "Evaluate.", "|−3| + |2| = 5"),
])
def test_a_line_of_numerals_is_the_answer_proper(profile, request_text, answer):
    rc = receive(profile, answer, request_text)
    assert "INT-REQ-012" not in [f.code for f in rc.findings], [(f.code, f.message[:120]) for f in rc.findings]
    words, _notes = count_answer_words(answer, view=lambda t: STEM_HOOKS.word_count_view(t, profile))
    assert words >= 1


def test_control_a_real_table_and_a_note_keep_their_reading():
    view = STEM_HOOKS.word_count_view("| A | B |\n|---|---|\n| 1 | 2 |", "mathematics_aa")
    assert "Xmath" not in view
    assert STEM_HOOKS.word_count_view("Note: 2019 2020", "mathematics_aa") == "Note: 2019 2020"


# ============================================================================================ rule unit-system
def test_a_bare_side_re_expressing_a_volume_is_read_in_the_statement_s_units():
    assert set(held("c = 0.0250 mol / 250 cm³ = 0.0250 / 0.250 = 0.100 mol dm⁻³", "chemistry", prefix="stem-eq")) == {True}
    assert False in held("c = 0.0250 mol / 250 cm³ = 0.0250 / 25.0 = 0.100 mol dm⁻³", "chemistry", prefix="stem-eq")
    assert False in held("c = 0.0250 mol / 250 cm³ = 0.0250 / 0.250 = 0.200 mol dm⁻³", "chemistry", prefix="stem-eq")


# ============================================================================================ a rounding, then a contrast
@pytest.mark.parametrize("answer", [
    "η = 0.796 = 79.6%. To 2 s.f. this is 80%, but the unrounded value 79.6% is below 80%, so it does not meet the standard.",
    "η = 0.796 = 79.6%. To 2 s.f. this is 80%, whereas the exact value is 79.6%.",
    "η = 0.796 = 79.6%. To 2 s.f. this is 80%, but the unrounded value is 79.6%.",
    "η = 0.796 = 79.6%. To 2 s.f. this is 80%, but unrounded it is 79.6%, which is below 80%.",
])
def test_a_stated_rounding_names_no_value_after_a_contrast(answer):
    req = "The kettle meets the standard only if its efficiency is at least 80%. Determine whether it meets the standard."
    assert no_stem_fault(receive("physics", answer, req)), answer


def test_control_a_wrong_rounding_before_a_contrast_still_fails():
    req = "The kettle meets the standard only if its efficiency is at least 80%. Determine whether it meets the standard."
    assert "INT-SUBJ-001" in errors(receive("physics", "η = 0.796 = 79.6%. To 2 s.f. this is 90%.", req))
    assert "INT-SUBJ-001" in errors(receive("physics", "η = 0.796 = 79.6%. To 2 s.f. this is 90%, but the unrounded value is 79.6%.", req))


# ============================================================================================ integer division
@pytest.mark.parametrize("text, holds", [("In integer division, 7 / 2 = 3 in Java.", True), ("In integer division, 7 / 2 = 4 in Java.", False),
                                         ("7 / 2 = 3.5", True), ("7 / 2 = 3", False)])
def test_slash_is_the_integer_quotient_where_the_statement_says_integer_division(text, holds):
    assert held(text, "computer_science", prefix="stem-eq") == [holds], text
