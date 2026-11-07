"""Round-8 clearance (arena round 8, integrated round c1): the STEM findings of the overseer lenses, each reproduced through the hub and
fixed at its cause, with clean controls (correct working that must hold) and negative controls (wrong working that must still be
named). docs/STEM_DESIGN.md, section 39.

* false errors on correct work: a symbol the answer defines by a formula is read by it in a symbolic step (rule step-definition), a
  factor every term of the premise carries and the step cancels is non-zero (rule cancelled-factor), a quantity restated in another unit
  is a conversion (rule unit-restatement), a unit after a bare surd belongs to the value, a value its clause rejects is no step, the
  negative square root is one case of the solutions, 'the first whole number is n = 23' answers an inequality (rule integer-bound), 'At
  x = 2:' is an evaluation point, a relation inside quotation marks is no root or step (rule quoted-relation), a Boolean output reads its
  definition (rule boolean-output), a dash list marker is no minus (rule list-marker), a based numeral composed of digits restates no
  digit (rule based-composition), a function power keeps its run ('cos²(10t)');
* injected faults that crossed unnamed: count nouns ('60 quadrats', '85 beats'), decimals cut by an ellipsis (rule cut-decimal), a mark
  annotation between a line and its continuation, a glued letter run ('GMm/r² = mv²/r'), a declared letter run ('kx = mg, so x =
  k/(mg)'), a Boolean derivation and a truth table of a defined output, a general term against its instances, a step over one function
  application (rule function-atom), a request value miscopied or swapped (rule request-substitution), a prose share, a Given cited from
  the question (rule cited-given);
* smaller readings: template blanks, the part of a show-that target, a hex digit's value, an ordinal alone, the molar volume;
* the remaining majors: a sum of bound symbols with no lone head is evaluated (rule bound-sum), a whole value ending in zero takes the
  bound operands' figures (rule bound-figures), a wrong value stated for a booklet constant is named at warning (rule booklet-value), a
  stated value of π is held to its digits (rule constant-statement), a wrong mole ratio is named (rule mole-ratio), a line with a
  bidirectional control is decided in neither order (rule bidi-control), a value with its sum in brackets (rule parenthetical-sum), a
  relation after a group nested beyond the bound is named, a closed value restated on the next line (rule restated-line), a line that
  names its quantity (rule labelled-line), and the adversarial lens's own variants of restated values.

The last section bounds the CPU time of the new readings on hostile input of about 20,000 characters.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.document import clear_document_cache
from epinoic_logic.translate.contracts import SuppliedText

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"round-8-clearance-stem-key-0123456789"
SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches", "mathematics_ai": "Mathematics: Applications and Interpretation",
            "chemistry": "Chemistry", "computer_science": "Computer Science", "biology": "Biology", "ess": "Environmental Systems and Societies"}
PHYS, AA, AI, CHEM, CS, BIO, ESS = "physics", "mathematics_aa", "mathematics_ai", "chemistry", "computer_science", "biology", "ess"
ROUND8 = json.loads((Path(__file__).parents[1] / "fixtures" / "stem" / "round8" / "c1_answers.json").read_text(encoding="utf-8"))["answers"]


def receive(profile: str, answer: str, request: str = "Answer the question.", texts: tuple[str, ...] = ()):
    clear_document_cache()
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    supplied = [SuppliedText(document_id=f"peer:doc{i}", title="peer", text=t) for i, t in enumerate(texts)]
    m, _, _ = hub.dispatch("t", agent, request, supplied)
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    hub.close()
    return rc


def recorded(tid: str, text: "str | None" = None):
    a = ROUND8[tid]
    peer = (ROUND8[a["peer"]]["response_text"],) if a["peer"] else ()
    return receive(a["profile"], a["response_text"] if text is None else text, a["question"], peer)


def mutated(tid: str, old: str, new: str):
    text = ROUND8[tid]["response_text"]
    assert text.count(old) == 1, old
    return recorded(tid, text.replace(old, new))


def findings(rc) -> list:
    return list(rc.findings) + list(rc.structural_findings)


def errors(rc) -> list[tuple[str, tuple[str, ...]]]:
    return [(f.code, tuple(f.claim_ids)) for f in findings(rc) if f.severity == "error"]


def named(rc, code: str, claim: "str | None" = None) -> bool:
    return any(f.code == code and (claim is None or claim in f.claim_ids) for f in findings(rc))


def failed(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is False]


def held(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is True]


def subj_warnings(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-004"]


# ============================================================================== the recorded answers: correct work is never an error

@pytest.mark.parametrize("tid", sorted(ROUND8))
def test_no_recorded_round_8_answer_carries_a_stem_error(tid):
    """14 false INT-SUBJ-001 on five of the nine genuine STEM answers (ph-p8b 3, ph-t14 3, maa-t14 2, maa-p8b 5, cs-t14 1) and five more
    on the breadth probe's cs-2: every one of these answers is correct, so none carries an error now."""
    rc = recorded(tid)
    assert not [e for e in errors(rc) if e[0] == "INT-SUBJ-001"], [f.message[:300] for f in findings(rc) if f.severity == "error"]


def test_the_identity_steps_of_the_physics_answer_hold_through_the_definitions():
    """ph-p8b s3.1, s7.1 and s8.2: '−(k/m)x = −ω²x', '√((k/m)(A² − x²)) = ω√(A² − x²)' and '2π√(2m/k) = √2 × T' hold because ω = √(k/m)
    and T = 2π√(m/k) are stated; ω had been pinned to 10 and T to the rounded 0.63 s with k and m free (rule step-definition)."""
    rc = recorded("ph-p8b")
    assert not failed(rc), failed(rc)
    assert len([c for c in rc.formal_checks if c.constraint_id.startswith("stem-alg") and c.satisfied]) >= 4


# ============================================================================== rule step-definition and rule cancelled-factor

TROLLEY_SPRING = "A trolley of mass 0.50 kg on a spring of constant 50 N m⁻¹ oscillates."
OMEGA = ("m = 0.50 kg\nk = 50 N m⁻¹\nThe resultant force is −kx, so ma = −kx, which gives a = −(k/m)x = −ω²x.\n"
         "ω = √(k/m) = √((50 N m⁻¹)/(0.50 kg)) = √(100 s⁻²) = 10.0 rad s⁻¹")


def test_a_symbol_defined_by_a_formula_is_read_by_it_in_a_symbolic_identity():
    rc = receive(PHYS, OMEGA, TROLLEY_SPRING)
    assert not failed(rc) and not errors(rc), [f.message[:200] for f in findings(rc)]
    wrong = receive(PHYS, OMEGA.replace("= −ω²x", "= −2ω²x"), TROLLEY_SPRING)  # the negative control of the overseer's reproduction
    assert named(wrong, "INT-SUBJ-001"), failed(wrong)
    bad_def = receive(PHYS, OMEGA.replace("ω = √(k/m) =", "ω = √(m/k) =").replace("= 10.0 rad", "= 0.1 rad"), TROLLEY_SPRING)
    assert named(bad_def, "INT-SUBJ-001")


@pytest.mark.parametrize("answer,ok", [("T = 2π√(m/k)\nT′ = 2π√(2m/k) = √2 × T", True), ("T = 2π√(m/k)\nT′ = 2π√(2m/k) = 2 × T", False)])
def test_a_rounded_restatement_is_never_substituted_into_a_symbolic_identity(answer, ok):
    rc = receive(PHYS, answer + "\nT = 0.63 s", TROLLEY_SPRING)
    assert (not errors(rc)) is ok, errors(rc)


def test_a_step_to_a_value_still_reads_the_data_by_their_values():
    """A step to a value ('λ = 0.087 h⁻¹' from 'λT½ = ln 2' with T½ = 8.0 h stated) keeps the stated half-life: the definition T½ = ln 2/λ
    would make the premise empty (this shape is pinned by tests/stem/test_stem_repair7.py as well)."""
    rc = receive(PHYS, "T½ = 8.0 h\nT½ = ln 2/λ, so λT½ = ln 2\nλ = 0.087 h⁻¹")
    assert not errors(rc), errors(rc)


ESCAPE = "Derive the escape speed from a planet of mass M and radius R."


@pytest.mark.parametrize("answer,ok", [
    ("Escape is possible when the total energy at the surface is zero: ½mv² − GMm/R = 0, so v = √(2GM/R).", True),
    ("Escape is possible when the total energy at the surface is zero: ½mv² − GMm/R = 0, so v = √(GM/R).", False),
    ("½mv² − mgh = 0, so v = √(2gh).", True),
    ("½mv² − mgh = 0, so v = √(gh).", False),
    ("mgh = ½mv², so v = √(2gh).", True),
    ("mgh = ½mv², so v = √(gh).", False),
])
def test_a_cancelled_factor_is_read_non_zero_and_a_wrong_step_still_fails(answer, ok):
    """ph-t14 s6.1 had been refuted with m = 0, which satisfies the energy equation for every v; 'mgh = ½mv²' told the correct and the
    wrong step apart nowhere (the same warning on both): the declared run mgh is read as m·g·h now (rule letter-run)."""
    rc = receive(PHYS, answer, ESCAPE)
    if ok:
        assert not failed(rc) and not subj_warnings(rc), [f.message[:200] for f in findings(rc)]
    else:
        assert named(rc, "INT-SUBJ-001"), failed(rc)


# ============================================================================== rule unit-restatement and the unit after a surd

HOURS = "T² = 1.156 × 10⁸ s²\nT = √(1.156 × 10⁸ s²) = 1.075 × 10⁴ s\nT = (1.075 × 10⁴ s)/(3600 s h⁻¹) = 2.99 h"


def test_a_value_restated_in_another_unit_is_a_conversion_never_a_new_root():
    rc = receive(PHYS, HOURS)
    assert not errors(rc), [f.message[:200] for f in findings(rc)]
    assert any(c.constraint_id.startswith("stem-cnv") and c.satisfied for c in rc.formal_checks)
    wrong = receive(PHYS, HOURS.replace("(1.075 × 10⁴ s)/", "(1.175 × 10⁴ s)/").replace("= 2.99 h", "= 3.26 h"))
    assert named(wrong, "INT-SUBJ-001") and any(c.startswith("stem-cnv") for c in failed(wrong)), failed(wrong)


def test_the_hours_control_of_the_overseer_draws_no_error():
    text = ROUND8["ph-t14"]["response_text"].replace("T = (1.075 × 10⁴ s)/(3600 s h⁻¹) = 2.99 h, which agrees", "In hours, T = 10750 ÷ 3600 = 2.99 h, which agrees")
    assert not errors(recorded("ph-t14", text))


@pytest.mark.parametrize("answer,ok", [("Speed = 20√3 cm s⁻¹ = (√3/5) m s⁻¹ ≈ 0.346 m s⁻¹", True), ("Speed = 20√3 cm s⁻¹ = (√3/4) m s⁻¹ ≈ 0.433 m s⁻¹", False),
                                       ("L = 3√2 cm = 4.24 cm", True), ("L = 3√2 cm = 4.84 cm", False), ("L = √(25 m²) = 5 m", True)])
def test_a_unit_after_a_bare_surd_is_the_values_unit(answer, ok):
    rc = receive(AA if "Speed" in answer else PHYS, answer)
    assert (not errors(rc)) is ok, [f.message[:200] for f in findings(rc)]


# ============================================================================== values that are no roots and no steps

LOGS = "Solve log₃(x + 4) + log₃(x − 4) = 2."


def test_a_rejected_value_and_the_negative_root_are_no_principal_root_step():
    rc = receive(AA, "x² − 16 = 9\nx² = 25\nx = 5 or x = −5\nx = −5 is rejected because it does not satisfy x > 4\nx = 5", LOGS)
    assert not errors(rc), [f.message[:200] for f in findings(rc)]
    wrong = receive(AA, "x² − 16 = 9\nx² = 25\nx = 5 or x = −6\nx = −6 is rejected because it does not satisfy x > 4\nx = 5", LOGS)
    assert named(wrong, "INT-SUBJ-001")


FIRST_DAY = "Find the first day n on which the total exceeds 1000, where S = 2n² + n."
INTEGER = ("The positive root of 2n² + n − 1000 = 0 is n = (−1 + √8001)/4.\nSo 22 < (−1 + √8001)/4 < 23.\n"
           "For n > 0 the inequality holds exactly when n > (−1 + √8001)/4, so the first whole number is n = 23.")


@pytest.mark.parametrize("n,ok", [("23", True), ("24", False), ("22", False)])
def test_the_first_whole_number_answers_the_inequality(n, ok):
    """'n = 23' had been decided as a root of 2n² + n − 1000 = 0 (81 ≠ 0); it is checked against the inequality before it now: it must hold
    at n and fail at n − 1 (rule integer-bound)."""
    rc = receive(AA, INTEGER.replace("n = 23", f"n = {n}"), FIRST_DAY)
    assert (not errors(rc)) is ok, errors(rc)
    assert len([c for c in rc.formal_checks if "integer-bound" in c.detail]) == 2 or not ok


def test_an_evaluation_point_is_no_root_and_a_function_power_keeps_its_run():
    rc = receive(AA, "v² + 100x² = 1600\nAt x = 2: v² = 1600 − 400 = 1200, so |v| = 20√3.")
    assert not errors(rc), [f.message[:200] for f in findings(rc)]
    doc = build_document("100x² = 1600 cos²(10t)", "Answer.", AA)
    assert not [r for r in doc.relations if doc.text[r.start:r.end].strip() == "100x² = 1600"], [doc.text[r.start:r.end] for r in doc.relations]
    doc = build_document("y = 3 cos²(2t)", "Answer.", AA)
    assert not [r for r in doc.relations if r.kind == "binding"], [(r.kind, doc.text[r.start:r.end]) for r in doc.relations]


@pytest.mark.parametrize("text, point", [("v = 3t(2 − t) = 0\nAt t = 2: v = 0", True), ("v = 3t(2 − t) = 0\n- When t = 2, v = 0", True),
                                         ("3t(2 − t) = 0\nThe velocity changes sign at t = 2, so it turns back.", False)])
def test_an_evaluation_point_opens_its_clause(text, point):
    """Rule evaluation-point reads a cue word that opens its clause; 'changes sign at t = 2, so' (round 7's maa-t13) still states a root
    of the equation before it, whose holding check the rule had dropped."""
    doc = build_document(text, "Answer the question.", AA)
    assert any("(rule evaluation-point)" in (r.reason or "") for r in doc.relations) is point, [(r.kind, r.reason) for r in doc.relations]


def test_a_quoted_peer_value_is_no_root_of_the_answers_equation():
    """maa-p8b m8.10/m8.11: the Physics specialist's quoted 'v = 0.35 m s⁻¹' had been set against 'v² = 1600 − 400' in cm s⁻¹."""
    rc = recorded("maa-p8b")
    assert not named(rc, "INT-SUBJ-001")
    doc = build_document('v² = 1600 − 400 = 1200, so |v| = 20√3 cm s⁻¹.\nThe Physics specialist\'s "v = 0.35 m s⁻¹ (2 s.f.)" agrees.', "Answer.", AA)
    assert not [r for r in doc.relations if r.kind == "sol"], [(r.kind, doc.text[r.start:r.end]) for r in doc.relations]


# ============================================================================== Boolean outputs, derivations and truth tables

CIRCUIT = "A circuit has output X = (A AND B) OR (NOT A AND C)."


@pytest.mark.parametrize("answer,ok", [
    ("X = (A AND B) OR (NOT A AND C). Check: when A = 0, NOT A = 1 and A AND B = 0, so X = C.", True),
    ("X = (A AND B) OR (NOT A AND C). Check: when A = 0, NOT A = 1 and A AND B = 0, so X = B.", False),
])
def test_a_conditional_boolean_statement_reads_the_outputs_definition(answer, ok):
    rc = receive(CS, answer, CIRCUIT)
    assert (not errors(rc)) is ok, [f.message[:200] for f in findings(rc)]


def test_a_truth_table_of_the_requests_output_is_checked_row_by_row():
    assert any(c.constraint_id.startswith("stem-tt") and c.satisfied for c in recorded("cs-t14").formal_checks)
    rc = mutated("cs-t14", "| 1 | 0 | 1 | 0 | 0 | 0 | 0 |", "| 1 | 0 | 1 | 0 | 0 | 0 | 1 |")
    assert named(rc, "INT-SUBJ-001") and any(c.startswith("stem-tt") for c in failed(rc))


def test_each_line_of_a_boolean_derivation_is_checked_against_the_line_before():
    rc = recorded("cs-t14")
    steps = [c for c in rc.formal_checks if "the step of the Boolean derivation" in c.detail]
    assert len(steps) == 5 and all(c.satisfied for c in steps), [(c.constraint_id, c.satisfied) for c in steps]
    wrong = mutated("cs-t14", "= NOT B AND (NOT A OR A), by", "= NOT B AND (NOT A AND A), by")
    assert named(wrong, "INT-SUBJ-001", "c22.1"), [(f.code, f.claim_ids) for f in findings(wrong)]


# ============================================================================== dash lists and based numerals

@pytest.mark.parametrize("answer,ok", [("Working:\n- 20 − 4.0 = 16 m s⁻¹\n- 16/4.0 = 4.0 m s⁻²", True), ("- 3 + 4 = 7", True), ("- 3 + 4 = 8", False)])
def test_a_dash_list_marker_is_never_a_minus(answer, ok):
    rc = receive(PHYS if "Working" in answer else AA, answer)
    assert (not errors(rc)) is ok, errors(rc)
    assert held(rc) or not ok


def test_the_breadth_cs_2_answer_reads_its_list_and_its_composed_numeral():
    rc = recorded("cs-2")
    assert not errors(rc) and not failed(rc), [f.message[:200] for f in findings(rc)]
    assert len(held(rc)) >= 6


# ============================================================================== count nouns and cut decimals

@pytest.mark.parametrize("old,new,code", [
    ("= 3.15 plants per m². Each", "= 6.15 plants per m². Each", "INT-SUBJ-001"),
    ("189 ÷ 60 quadrats", "189 ÷ 90 quadrats", "INT-SUBJ-001"),
])
def test_a_line_with_count_nouns_is_checked(old, new, code):
    """bi-t14's density line had been read as two label bindings ('Mean density = 189 ÷ 60', 'quadrats = 3.15'): no check, no finding."""
    assert any(c.satisfied for c in recorded("bi-t14").formal_checks if "quadrats" in c.detail)
    assert named(mutated("bi-t14", old, new), code, "s1.1")


@pytest.mark.parametrize("line, wrong", [("1,000 ÷ 3 = 334 items is a third of the list.", True), ("1,000 ÷ 3 = 333 items is a third of the list.", False),
                                         ("Total = 12 plants + 15 plants = 28 plants", True), ("Total = 12 plants + 15 plants = 27 plants", False)])
def test_a_whole_count_of_things_keeps_exact_work_exact(line, wrong):
    """A count noun made '334 items' a measured quantity, so τ = 1/100 let '1,000 ÷ 3 = 334 items' hold (the overseer's STEM probe
    arithmetic-exact-third on round 7's cs-t13 found no check left to tamper with); a whole count of things is exact (rule count-noun)."""
    rc = receive(CS if "items" in line else BIO, "On average a linear search compares 1,000 ÷ 2 = 500 items, and " + line if "items" in line else line)
    assert bool(failed(rc)) is wrong and (("INT-SUBJ-001" in [e[0] for e in errors(rc)]) is wrong), (failed(rc), errors(rc))


def test_a_cardiac_cycle_with_a_wrong_unit_is_named():
    assert not named(recorded("bi-p8d"), "ST-DIM-001")
    assert named(mutated("bi-p8d", "85 beats = 0.71 s.", "85 beats = 0.71 m."), "ST-DIM-001", "s2.3")


@pytest.mark.parametrize("old,new,claim", [
    ("= 23\\,425 - 7045.59\\ldots = 16\\,379.41\\ldots$ A1", "= 23\\,425 - 7045.59\\ldots = 46\\,379.41\\ldots$ A1", "m4.1"),
    ("$a^2 = 95^2 + 120^2", "$a^2 = 95^5 + 120^2", "m2.1"),
])
def test_a_decimal_cut_by_an_ellipsis_is_a_value_and_its_slips_are_named(old, new, claim):
    """mai-t14: every worked line had been 'outside the encodings: an ellipsis' (16 ST-UNDEC-001), so both injections got only the
    warning the genuine line had; the substitution line was also withheld for the mark annotation between it and its continuation."""
    genuine = recorded("mai-t14")
    assert not errors(genuine) and not [f for f in genuine.findings if "an ellipsis" in f.message]
    assert named(mutated("mai-t14", old, new), "INT-SUBJ-001", claim)


# ============================================================================== steps after a balance, general terms, function atoms

SATELLITE = "A satellite of mass m orbits a planet of mass M at radius r. Show that v² = GM/r."


@pytest.mark.parametrize("answer,ok", [
    ("Gravity provides the centripetal force: GMm/r² = mv²/r, so v² = GM/r.", True),
    ("Gravity provides the centripetal force: GMm/r² = mv²/r, so v² = GM/r².", False),
    ("At equilibrium kx = mg, so x = mg/k.", True),
    ("At equilibrium kx = mg, so x = k/(mg).", False),
])
def test_a_step_after_a_balance_is_checked(answer, ok):
    rc = receive(PHYS, answer, SATELLITE)
    assert any(c.constraint_id.startswith("stem-alg") for c in rc.formal_checks)
    assert (not errors(rc)) is ok, errors(rc)


def test_a_general_term_is_set_against_its_instances():
    """maa-t14's 'uₙ = u₁ + (n − 4)d' had been named only against the data booklet (ST-REF-002, a warning)."""
    assert not errors(recorded("maa-t14"))
    rc = mutated("maa-t14", "uₙ = u₁ + (n − 1)d.", "uₙ = u₁ + (n − 4)d.")
    assert named(rc, "INT-SUBJ-001", "m2.1")


@pytest.mark.parametrize("answer,ok", [("(b) With t ≥ 0, set 4 cos(10t) = 2.\ncos(10t) = 1/2  M1", True), ("(b) With t ≥ 0, set 4 cos(10t) = 2.\ncos(10t) = 4/2  M1", False)])
def test_a_step_over_one_function_application_reads_it_as_one_value(answer, ok):
    rc = receive(AA, answer)
    assert (not errors(rc)) is ok and not [f for f in rc.findings if "function of an unknown" in f.message], [f.message[:120] for f in findings(rc)]


# ============================================================================== request values, shares and cited Givens

DROP = "A ball of mass 2.0 kg is dropped from a height of 5.0 m. Take g = 9.8 m s⁻². Calculate its loss of gravitational potential energy."
SUVAT = "A car moving at 3.0 m s⁻¹ accelerates uniformly to 15 m s⁻¹ in 4.0 s. Calculate its acceleration."


@pytest.mark.parametrize("answer,request_text,ok", [
    ("ΔE = mgh = 2.0 × 9.8 × 50 = 980 J", DROP, False),
    ("ΔE = mgh = 2.0 × 9.8 × 5.0 = 98 J", DROP, True),
    ("a = (v − u)/t = (3.0 − 15)/4.0 = −3.0 m s⁻²", SUVAT, False),
    ("a = (v − u)/t = (15 − 3.0)/4.0 = 3.0 m s⁻²", SUVAT, True),
    ("E = hf = 6.63 × 10⁻³⁴ × 5.0 × 10¹⁴ = 3.3 × 10⁻¹⁹ J", "Light of frequency 5.0 × 10¹⁴ Hz and wavelength 6.0 × 10⁻⁷ m. Calculate the photon energy.", True),
])
def test_a_miscopied_or_swapped_request_value_is_named(answer, request_text, ok):
    """h written for a height is the request's one length when the numeral is no value of Planck's constant; u and v take the request's
    initial and final speed ('moving at', 'to'). A reading of the request, so a warning (INT-SUBJ-004)."""
    rc = receive(PHYS, answer, request_text)
    assert bool(subj_warnings(rc)) is not ok and not errors(rc), [f.message[:200] for f in findings(rc)]


@pytest.mark.parametrize("answer,ok", [
    ("540 kJ is 85% of 720 kJ.", False), ("540 kJ is 75% of 720 kJ.", True),
    ("Respiration takes 540 kJ m⁻² yr⁻¹ of the 720 kJ m⁻² yr⁻¹, which is 85%.", False),
    ("Respiration takes 540 kJ m⁻² yr⁻¹ of the 720 kJ m⁻² yr⁻¹, which is 75%.", True),
    ("they ate only 1800 of the 1.0 × 10⁴ kJ m⁻² yr⁻¹ (28%)", False), ("they ate only 1800 of the 1.0 × 10⁴ kJ m⁻² yr⁻¹ (18%)", True),
])
def test_a_prose_share_is_checked(answer, ok):
    rc = receive(ESS, answer)
    assert any(c.constraint_id.startswith("stem-eq") for c in rc.formal_checks)
    assert (not errors(rc)) is ok, errors(rc)


def test_the_recorded_shares_hold():
    rc = recorded("ess-t14")
    shares = [c for c in rc.formal_checks if "the share the prose states" in c.detail]
    assert len(shares) == 2 and all(c.satisfied for c in shares)


FIELD = "A planet has mass 6.4 × 10²³ kg. G = 6.67 × 10⁻¹¹ N m² kg⁻². Calculate the field strength at 3.4 × 10⁶ m."


def test_a_given_cited_from_the_question_fails_as_an_error_and_an_uncited_one_as_a_warning():
    assert named(receive(PHYS, "Given: G = 6.67 × 10⁻¹⁰ N m² kg⁻² (from the question).", FIELD), "INT-SUBJ-001")
    uncited = receive(PHYS, "Given: G = 6.67 × 10⁻¹⁰ N m² kg⁻².", FIELD)
    assert subj_warnings(uncited) and not errors(uncited)
    assert not errors(receive(PHYS, "Given: G = 6.67 × 10⁻¹¹ N m² kg⁻² (from the question).", FIELD))


def test_a_unit_after_a_power_of_a_numeral_is_read():
    text = ROUND8["ph-t14"]["response_text"].replace("G = 6.67 × 10⁻¹¹ N m² kg⁻² (from the question)", "G = 6.67 × 40⁻¹¹ N m² kg⁻² (from the question)")
    rc = recorded("ph-t14", text)
    assert not [f for f in findings(rc) if "unexpected 'kg'" in f.message]


def test_a_value_cited_from_the_question_in_a_block_with_no_list_markers_is_a_given():
    """The round's substitution mutation of ph-t14: 'G = 6.67 × 40⁻¹¹ N m² kg⁻² (from the question)' under 'Givens, in SI:' with no list
    markers was a plain binding (a closed expression, no single value), so the wrong G was named nowhere; a value whose statement cites
    the question for a symbol the request gives is set against the request's value (rule cited-given), an error when it fails. The
    genuine line holds, and so does the same value written as a power of ten in brackets."""
    old = "G = 6.67 × 10⁻¹¹ N m² kg⁻² (from the question)"
    assert ("INT-SUBJ-001", ("s2.6",)) in errors(mutated("ph-t14", old, "G = 6.67 × 40⁻¹¹ N m² kg⁻² (from the question)"))
    assert not errors(recorded("ph-t14"))
    assert not errors(mutated("ph-t14", old, "G = 6.67 × 10^(−11) N m² kg⁻² (from the question)"))


# ============================================================================== smaller readings

def test_template_blanks_are_no_maths_and_no_emphasis():
    line = "Model skeleton: n = 1.15 ÷ 46.08 = ____ mol (unrounded); ΔT = 42.5 − 18.0 = ____ K; ΔH = −Q ÷ n = ____ kJ mol⁻¹."
    rc = receive(CHEM, line)
    assert not subj_warnings(rc) and not [f for f in rc.findings if f.code == "ST-UNDEC-002"], [f.message[:120] for f in findings(rc)]
    doc = build_document(line, "Answer.", CHEM)
    assert doc.statement_text(doc.statements[0].id).count("____") == 3


def test_a_show_that_target_is_set_against_its_own_part():
    rc = recorded("ph-t14")
    tgt = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-tgt")]
    assert tgt and all(c.satisfied for c in tgt) and "2.99 h" in tgt[0].detail, [(c.constraint_id, c.detail[:100]) for c in tgt]


def test_a_hex_digit_and_an_ordinal_raise_no_false_given_warning():
    assert not subj_warnings(recorded("cs-t14")), [f.message[:150] for f in subj_warnings(recorded("cs-t14"))]
    assert not subj_warnings(recorded("maa-t14")), [f.message[:150] for f in subj_warnings(recorded("maa-t14"))]


def test_a_course_or_exam_year_of_the_request_is_no_data_range():
    """ph-t14's request says 'exams in May 2027 (the course first assessed in 2025)': ST-RANGE-001 had read 2025 to 2027 as the range of
    the request's data and named the period in seconds as an extrapolation ('the model is evaluated at 1075')."""
    for text in (ROUND8["ph-t14"]["response_text"],
                 ROUND8["ph-t14"]["response_text"].replace("= 2.99 h, which agrees with about 3 hours.",
                                                           "= 2.99 h, which agrees with about 3 hours.\nIn hours, T = 10750 ÷ 3600 = 2.99 h.")):
        assert not named(recorded("ph-t14", text), "ST-RANGE-001")


def test_every_check_that_holds_an_enclosure_says_it_is_the_stem_packs():
    """The algebra steps of ph-p8b that use the π enclosure had not said that its bounds are numeric enclosures computed by the STEM pack,
    not engine results; every check whose problem holds one says so now."""
    a = ROUND8["ph-p8b"]
    doc = build_document(a["response_text"], a["question"], a["profile"])
    plan = build_checks(doc, report_id="r", request_id="q")
    held = [pc for pc in plan.checks if any(p["id"].startswith("ENC_") for p in pc.problem["premises"])]
    assert held and all("numeric enclosures computed by the STEM pack" in pc.description for pc in held), [pc.check_id for pc in held]


def test_the_outdated_molar_volume_is_no_accepted_value():
    request = "Calculate the volume of 0.100 mol of gas at STP."
    assert subj_warnings(receive(CHEM, "V = nV_m = 0.100 mol × V_m = 2.24 dm³", request))
    assert not subj_warnings(receive(CHEM, "V = nV_m = 0.100 mol × V_m = 2.27 dm³", request))


# ============================================================================== bound sums, bound figures, booklet values, ratios

@pytest.mark.parametrize("line, wrong", [("A = 2.0 m² and B = 3.0 m², so A + B = 6.0 m²", True), ("A = 2.0 m² and B = 3.0 m², so A + B = 5.0 m²", False),
                                         ("A = 2.0 m² and B = 3.0 m², so A + B = 5.0 m². The total area is 5.0 m².", False)])
def test_a_sum_of_bound_symbols_with_no_lone_head_is_evaluated(line, wrong):
    """'A + B = 6.0 m²' after both values had been read as an equation in an unknown: no check and nothing named (rule bound-sum)."""
    rc = receive(PHYS, line)
    assert [c.constraint_id for c in rc.formal_checks if c.constraint_id.startswith("stem-sub")], [c.constraint_id for c in rc.formal_checks]
    assert (("INT-SUBJ-001", ("s1.1",)) in errors(rc)) is wrong and (bool(failed(rc)) is wrong), (errors(rc), failed(rc))


def test_an_equation_solved_after_the_bindings_is_still_no_evaluation():
    """Control: an equation whose part goes on to state a new value of one of its symbols is solved for it, as before."""
    rc = receive(AA, "x = 3\n2x + y = 10, so y = 4")
    assert not errors(rc) and not failed(rc), [f.message[:200] for f in findings(rc)]


@pytest.mark.parametrize("line, wrong", [("R = R₁ + R₂ = 10 Ω", True), ("R = R₁ + R₂ = 9.0 Ω", False)])
def test_a_whole_value_ending_in_zero_takes_the_bound_operands_figures(line, wrong):
    """R₁ = 4.0 Ω and R₂ = 5.0 Ω have two significant figures, so '10 Ω' is stated to the unit (h = 0.5), as the written '4.0 Ω + 5.0 Ω = 10 Ω'
    is decided; before, the one-figure half-width 5 let the wrong total hold (rule bound-figures)."""
    rc = receive(PHYS, "R₁ = 4.0 Ω and R₂ = 5.0 Ω.\n" + line)
    assert bool(failed(rc)) is wrong and (("INT-SUBJ-001" in [e[0] for e in errors(rc)]) is wrong), (failed(rc), errors(rc))


def test_one_figure_operands_keep_the_one_figure_reading_of_a_trailing_zero():
    rc = receive(PHYS, "R₁ = 4 Ω and R₂ = 5 Ω.\nR = R₁ + R₂ = 10 Ω")
    assert not failed(rc) and not errors(rc), failed(rc)


@pytest.mark.parametrize("line, warned", [("Taking g = 9.18 m s⁻², W = mg = 2.0 × 9.18 = 18.4 N", True),
                                          ("Taking g = 9.81 m s⁻², W = mg = 2.0 × 9.81 = 19.6 N", False),
                                          ("Taking g = 9.8 m s⁻², W = mg = 2.0 × 9.8 = 19.6 N", False),
                                          ("Taking g = 10 m s⁻², W = mg = 2.0 × 10 = 20 N", False),
                                          ("On the Moon g = 1.62 m s⁻², so W = mg = 2.0 × 1.62 = 3.24 N", False)])
def test_a_wrong_value_stated_for_a_booklet_constant_is_named_at_warning(line, warned):
    """'Taking g = 9.18 m s⁻²' had crossed ACCEPTED with every check held: only formulas were compared with the booklet (rule booklet-value).
    The value is set against the booklet's accepted values at its own precision; another body (the Moon) is no restatement of it."""
    rc = receive(PHYS, line)
    assert bool(subj_warnings(rc)) is warned and not errors(rc), ([f.message[:200] for f in subj_warnings(rc)], errors(rc))
    if warned:
        assert any("data-booklet constant" in f.message for f in subj_warnings(rc))


def test_the_booklet_value_check_leaves_a_request_value_alone():
    rc = receive(PHYS, "Taking g = 9.18 m s⁻², W = mg = 2.0 × 9.18 = 18.4 N", "On this planet g = 9.18 m s⁻². Find the weight of a 2.0 kg mass.")
    assert not subj_warnings(rc) and not errors(rc), [f.message[:200] for f in findings(rc)]


@pytest.mark.parametrize("line, wrong", [("π = 3.12", True), ("π = 3.13", True), ("π = 3.14", False), ("π = 3.1416", False), ("π = 3.1415", False),
                                         ("π ≈ 3.1", False)])
def test_a_stated_value_of_pi_is_held_to_its_digits(line, wrong):
    """'π = 3.12' held under τ = 1/100 (rule constant-statement: τ = 0 for a constant's own value)."""
    rc = receive(AA, "Taking " + line + ", the area is A = πr².")
    assert (("INT-SUBJ-001" in [e[0] for e in errors(rc)]) is wrong), errors(rc)


def _pack(profile: str, answer: str, request: str = "Answer the question."):
    """``(failed, held, ST findings)`` of the STEM pack itself on ``answer``: its planned checks run by the engine under their
    policies, as the channel runs them, each ``(check id, claim ids)``, and the front end's and the checks stage's findings as
    ``(code, statement ids)``. Used where the channel refuses the answer before parsing it (rule bidi-text, the round-8
    clearance's handoff fixer), so the pack's own rule bidi-control stays held to what it decides."""
    from epinoic_logic.engine.policies import policy_config, policy_limits
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.ir.schema import Problem
    clear_document_cache()
    doc = build_document(answer, request, profile)
    plan = build_checks(doc, report_id="r", request_id="q")
    failed_, held_ = [], []
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
        (held_ if res.status.value == pc.expected_if_sound else failed_).append((pc.check_id, tuple(pc.claim_ids)))
    return failed_, held_, [(f.code, tuple(f.statement_ids)) for f in (*doc.findings, *plan.findings)]


def _refused_for_bidi(rc) -> bool:
    """The channel's rule bidi-text: the response is REJECTED before it is parsed, with one INT-REQ-009 naming a bidirectional
    control by its code point, and nothing of it is checked or delivered."""
    named = [f for f in rc.findings if f.code == "INT-REQ-009" and "bidirectional embedding, override or isolate" in f.message]
    return (rc.status.value == "REJECTED" and len(named) == 1 and "U+" in named[0].message and not rc.formal_checks and not rc.outcomes
            and not rc.structural_findings)


def test_a_relation_before_a_bidirectional_control_on_its_line_is_still_checked():
    """Control: the control governs the text after it only, so a wrong relation before it on the same line is still named.

    Rewritten to a stricter rule by the round-8 clearance's handoff fixer (rule bidi-text, the STEM fixer's handoff item 2): the
    channel now refuses any specialist response holding a bidirectional control (INT-REQ-009, REJECTED, never delivered), as the
    combinator port's text rule refuses one in a synthesis. The receipt assertion became that refusal; the assertions on what the
    STEM pack decides (the wrong relation before the control fails on s1.1, which is named ST-UNDEC-001) are kept, on the pack."""
    answer = "v = 2.0 × 3.0 = 7.0 m s⁻¹ and \u202eb = 1 + 1 = 3"
    rc = receive(PHYS, answer)
    assert _refused_for_bidi(rc), findings(rc)
    failed_, _held, st = _pack(PHYS, answer)
    assert failed_ == [("stem-eq-1", ("s1.1",))] and ("ST-UNDEC-001", ("s1.1",)) in st, (failed_, st)


@pytest.mark.parametrize("ratio, wrong", [("1 : 2", True), ("1 : 1", False)])
def test_a_wrong_mole_ratio_from_the_balanced_equation_is_named(ratio, wrong):
    """'The mole ratio of H₂ to H₂O is 1 : 2' after '2H₂ + O₂ → 2H₂O' (1 : 1) was ACCEPTED: the equation balances and the arithmetic holds
    (rule mole-ratio: the coefficients of the last equation holding both species, at warning severity)."""
    rc = receive(CHEM, f"2H₂ + O₂ → 2H₂O. The mole ratio of H₂ to H₂O is {ratio}, so n(H₂O) = 4.0 × 2 = 8.0 mol.")
    assert bool(subj_warnings(rc)) is wrong and not errors(rc), [f.message[:200] for f in findings(rc)]
    if wrong:
        assert any("mole ratio" in f.message for f in subj_warnings(rc))


@pytest.mark.parametrize("shown", ["\u202e5.0\u202c", "\u202e0.5\u202c", "\u20675.0\u2069"])
def test_a_line_with_a_bidirectional_control_is_never_shown_as_checked(shown):
    """'a = (20 − 0)/4.0 = U+202E 5.0 U+202C' is displayed as 0.5 but was checked as 5.0 and held (and the form a reader sees correctly
    failed): a relation that reaches into text an embedding, override or isolate governs is named ST-UNDEC-001 and decided in neither
    order (rule bidi-control); the other lines are still checked.

    Rewritten to a stricter rule by the round-8 clearance's handoff fixer (rule bidi-text): the channel now refuses the whole response
    (INT-REQ-009, REJECTED), so no check of it is shown at all; the assertions on the STEM pack's own reading (the line with the control
    named ST-UNDEC-001 and not decided, the other line's wrong relation checked and failing on s1.2, one check in all) are kept, on the
    pack."""
    answer = f"a = (20 − 0)/4.0 = {shown} m s⁻²\nv = 2.0 × 3.0 = 7.0 m s⁻¹"
    rc = receive(PHYS, answer)
    assert _refused_for_bidi(rc), findings(rc)
    failed_, held_, st = _pack(PHYS, answer)
    assert ("ST-UNDEC-001", ("s1.1",)) in st, st
    assert [c for c, _ids in failed_ + held_] == ["stem-eq-1"] and failed_ == [("stem-eq-1", ("s1.2",))], (failed_, held_)


@pytest.mark.parametrize("line, warned", [("Oxygen atoms: 7 on the left (4 + 6) and 7 on the right.", True),
                                          ("Oxygen atoms: 7 on the left (1 + 6) and 7 on the right.", False)])
def test_a_value_with_its_sum_in_brackets_is_set_against_it(line, warned):
    """'7 on the left (4 + 6)' was dropped with nothing named (rule parenthetical-sum, a reading: warning)."""
    rc = receive(CHEM, line)
    assert bool(subj_warnings(rc)) is warned and not errors(rc), [f.message[:200] for f in findings(rc)]


def test_a_bracket_that_opens_a_calculation_is_no_parenthetical_sum():
    """Control (the recorded biology line): 'From 10 °C to 20 °C the uptake rises by (40 − 18) ÷ 18 × 100 = 122%.' holds, and the bracket
    is no sum of the 20 °C before it."""
    rc = receive(BIO, "From 10 °C to 20 °C the uptake rises by (40 − 18) ÷ 18 × 100 = 122%.")
    assert not failed(rc) and not subj_warnings(rc) and not errors(rc), [f.message[:200] for f in findings(rc)]


@pytest.mark.parametrize("text, links", [("$x = 3 + 4$ M1\n\nCost $= 2 \\times 7 = 14$", ["2 \\times 7 = 14"]),
                                         ("$x = 3 + 4$ M1\n\nso $= 7$", ["3 + 4$ M1\n\nso $= 7"]),
                                         ("$x = 3 + 4$ M1\n\n$= 7$", ["3 + 4$ M1\n\n$= 7"])])
def test_a_line_that_names_its_quantity_is_no_continuation(text, links):
    """mai-t14 '… = 342.982…$ m M1' then 'Cost $= 18.50 × 342.982…$': the cost had been read as the next link of the perimeter's chain
    and set against it (a false INT-SUBJ-001 once cut decimals were read); a line whose prose names a quantity before its relation sign
    is that quantity's value (rule labelled-line), while 'so $= …$' and a bare '$= …$' after a mark continue the chain as before."""
    doc = build_document(text, "Answer the question.", AI)
    checked = [text[r.start:r.end] for r in doc.relations if r.outcome == "check"]
    assert checked == links, checked


# the adversarial lens's own STEM variants of the round's answers (wrong results that must be named, one correct control)
LENS_VARIANTS = [
    ("maa-p8b", "T = π/5 s  A1", "T = π/4 s  A1", "m5.4"),
    ("maa-p8b", "so cos(10t) = 1/2 has", "so cos(10t) = 4/2 has", "m6.3"),
    ("mai-t14", r"Cost $= \$6345$ (nearest dollar) A1", r"Cost $= \$6435$ (nearest dollar) A1", None),
    ("mai-t14", r"Percentage error $= 1.46\%$ (3 s.f.) A1", r"Percentage error $= 1.64\%$ (3 s.f.) A1", None),
    ("bi-t14", "Mean density = 189 ÷ 60 quadrats = 3.15 plants per m².", "Mean density = 189 ÷ 60 quadrats = 4.15 plants per m².", None),
]


@pytest.mark.parametrize("tid, old, new, claim", LENS_VARIANTS)
def test_the_lens_variants_of_restated_values_are_named(tid, old, new, claim):
    """'T = 2π/10' then 'T = π/4 s' (rule restated-line: one chain over two lines), the cost restated as '\\$6435' after the chain gives
    6345.17… (an escaped dollar is the currency sign; a line that names the quantity a line before named restates it, rule
    labelled-line), the percentage error restated as 1.64% after 1.4569…% (a cut per cent restated as a per cent), and a density over
    a count noun: each crossed with nothing named."""
    rc = mutated(tid, old, new)
    assert [e for e in errors(rc) if e[0] == "INT-SUBJ-001" and (claim is None or claim in e[1])], [f.message[:200] for f in findings(rc)]


@pytest.mark.parametrize("line", ["In hours, T = 10750 ÷ 3600 = 2.99 h.", "In hours, T = (1.075 × 10⁴ s)/(3600 s h⁻¹) = 2.99 h."])
def test_a_second_conversion_to_hours_restates_the_first_value(line):
    """The lens's control: a correct conversion of the period to hours written after the answer already gave it in hours had been read as
    a stated root of T's equation in seconds (INT-SUBJ-001 on correct work); rule unit-restatement takes the last value of T stated in
    another unit of the dimension."""
    rc = mutated("ph-t14", "= 2.99 h, which agrees with about 3 hours.", "= 2.99 h, which agrees with about 3 hours.\n" + line)
    assert not [e for e in errors(rc) if e[0] == "INT-SUBJ-001"], [f.message[:300] for f in findings(rc) if f.severity == "error"]


@pytest.mark.parametrize("pair, wrong", [("T = 2π/10\nT = π/5 s", False), ("T = 2π/10\nT = π/4 s", True), ("x = 6/8\nx = 3/4", False),
                                         ("x = 6/8\nx = 2/3", True)])
def test_a_closed_value_restated_on_the_next_line_is_checked(pair, wrong):
    rc = receive(AA, pair)
    assert bool(failed(rc)) is wrong and (("INT-SUBJ-001" in [e[0] for e in errors(rc)]) is wrong), (failed(rc), errors(rc))


def test_the_cases_of_a_factorised_equation_are_no_restatement_of_a_function_value():
    """Rule function-restatement controls: 'sin x = 1/2' and 'sin x = −1' as the cases of a factorised equation (on separate lines, or
    joined by 'or') are never set against each other; a restatement after 'so' is."""
    for text, planned in (("(2 sin x − 1)(sin x + 1) = 0\nsin x = 1/2\nsin x = −1", 0),
                          ("(2 sin x − 1)(sin x + 1) = 0, so sin x = 1/2 or sin x = −1", 0),
                          ("cos x = 1/2\nso cos x = 1/2 has two solutions", 1)):
        doc = build_document(text, "Answer the question.", AA)
        assert len([r for r in doc.relations if "(rule function-restatement)" in (r.reason or "")]) == planned, text


def test_values_joined_as_alternatives_or_roots_are_no_restatement():
    """Controls: two values joined by 'or', and the roots of an equation on consecutive lines, are not set against each other."""
    for text in ("x = (1 + √5)/2 or\nx = (1 − √5)/2", "x² − x − 1 = 0\nx = (1 + √5)/2\nx = (1 − √5)/2"):
        doc = build_document(text, "Answer the question.", AA)
        assert not [r for r in doc.relations if "(rule restated-line)" in (r.reason or "")], text


@pytest.mark.parametrize("group", ["\\frac{1}{" * 300 + "2" + "}" * 300, "\\sqrt{" * 300 + "4" + "}" * 300])
def test_a_relation_after_a_group_nested_beyond_the_bound_is_named(group):
    """A relation after a 300-deep \\frac or \\sqrt had been read as the value of a 'label' made of the markup: no check, nothing named."""
    doc = build_document("$" + group + " = 5$\n\nAlso 2 + 2 = 5.", "Answer the question.", AA)
    assert [f.code for f in doc.findings] == ["ST-PARSE-001"] and [r.kind for r in doc.relations if r.outcome == "check"] == ["eq"], doc.findings


# ============================================================================== the new readings stay linear on hostile input

_N = 20_000
HOSTILE = {
    "underscores": ("x = 2 = " + "_" * 4 + " ") * (_N // 13),
    "blank runs": "= " + " " * _N + "____" + "x",
    "ellipses": ("1.5… + " * (_N // 7)) + "= 2",
    "ldots": ("0.309017\\ldots \\times " * (_N // 21)) + "1 = 2",
    "count nouns": ("12 plants ÷ 3 quadrats = " * (_N // 25)) + "4",
    "dash lists": "- 3 + 4 = 7\n" * (_N // 12),
    "quotes": ('"v = 0.35 m s⁻¹" ' * (_N // 18)),
    "open quotes": ('"v = 2 ' * (_N // 7)),
    "evaluation points": "At x = 2: " * (_N // 10),
    "first whole numbers": "so the first whole number is n = 23 " * (_N // 36),
    "boolean continuations": "NOT A OR A\n" + "= NOT B AND 1, by the identity law: NOT B AND 1 = NOT B\n" * (_N // 56),
    "glued runs": "GMm/r² = mv²/r, so " * (_N // 19) + "v = 1",
    "function powers": "y = 3 cos²(2t) + " * (_N // 18) + "1",
    "shares": "540 kJ is 85% of 720 kJ, and " * (_N // 29),
    "marks between lines": ("$a^2 = 95^2$ M1\n$= 9025$ A1\n" * (_N // 30)),
    "rejected values": "x = −5 is rejected because it does not satisfy x > 4\n" * (_N // 52),
    "mole ratios": "2H₂ + O₂ → 2H₂O. " + "The mole ratio of H₂ to H₂O is 1 : 2, " * (_N // 40),
    "booklet values": "Taking g = 9.18 m s⁻², " * (_N // 22),
    "bidi lines": "a = 2.0 × 3.0 = \u202e6.0\u202c\n" * (_N // 17),
    "bracket sums": "7 on the left (4 + 6) and " * (_N // 26),
    "bound sums": "A = 2.0 m² and B = 3.0 m², so A + B = 6.0 m²\n" * (_N // 45),
    "restated lines": "T = 2π/10\n" * (_N // 10),
    "labelled lines": "Cost $= 2 \\times 7 = 14$ M1\n\nCost $= \\$15$\n" * (_N // 40),
    "escaped dollars": "$= \\$" + "\\$" * (_N // 2) + "5$",
    "function restatements": "cos(10t) = 1/2\n" + "so cos(10t) = 1/2 has one solution, " * (_N // 37),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
@pytest.mark.parametrize("profile", [PHYS, AA, CS, ESS])
def test_the_new_readings_are_bounded_on_hostile_input(name, profile):
    text = HOSTILE[name]
    clear_document_cache()
    t0 = time.process_time()
    doc = build_document(text, "Answer the question. Show that x = 2.", profile)
    build_checks(doc, report_id="r", request_id="q")
    assert time.process_time() - t0 < 8.0, name
