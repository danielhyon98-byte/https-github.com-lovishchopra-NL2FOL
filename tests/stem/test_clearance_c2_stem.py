"""Round-9 clearance (arena round 9, integrated round c2): the STEM findings of the overseer lenses and the records carried from round 8,
each reproduced through the hub and fixed at its cause, with clean controls (correct working that must hold, with no error) and negative
controls (wrong working that must still be named). docs/STEM_DESIGN.md, section 40.

* false errors on correct work: a derived condition read with the condition the part states (rule stated-condition), a request value of
  another part's question no value of this part (rule part-condition for order relations), a law substituted with values on both sides
  (rule premise-substitution, both sides), a law evaluated with a rounded constant on the next line (rule evaluation-step), a new law after
  a principle line (rule new-law), a velocity of zero the question states in words (rule rest-value), a restatement in another unit of the
  value its own line states, never another part's (rule unit-restatement, scoped), a coupled mass and a carried result no Given (rules
  combined-value and carried-value), a unit defined by a value (rule unit-definition), a dash between two numbers (rule spaced-dash);
* injected faults that crossed unnamed: a law substituted with stated coefficients (rule substitution-instance), a completed square, the
  multiples of the bit and the stated decimal convention of the byte (rule data-convention), a whole number converted (rule
  converted-value), a formula labelling a quantity after its unit (rule species-label), bond enthalpies the request gives (rule bond-data),
  a step after a mark annotation, a mole ratio stated alone, a booklet constant put in as a numeral, a step joined to its law by 'and', a
  truth table of an output the request defines, a derivation on consecutive lines, prose shares, folds and comparisons, a format character
  inside a figure (rule format-character), a temperature the request states in °C put in as the same number of kelvin (rule
  kelvin-substitution), working laid out in a table (rule table-working), coordinate pairs (rule coordinate-pair), a change, percentage
  points, a quotient and a share the prose states (rules prose-change, percentage-points, quotient-share, referent-share), a word formula
  before its working (rule word-formula-chain);
* relations read in part or dropped with nothing named: a numeral written with a thousands space (rules cut-label, thousands-value,
  cut-decimal); a false ST-RANGE-001 on a definition evaluated at a value the request states (rule definition-law);
* a claim that started inside a word ('n = amount ÷ volume' for 'Concentration = …').

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
from epinoic_logic.stem.units import decimal_data_stated, stem_parse_unit
from epinoic_logic.translate.contracts import SuppliedText

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"round-9-clearance-stem-key-0123456789"
SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches", "mathematics_ai": "Mathematics: Applications and Interpretation",
            "chemistry": "Chemistry", "computer_science": "Computer Science", "biology": "Biology", "ess": "Environmental Systems and Societies"}
PHYS, AA, AI, CHEM, CS, BIO, ESS = "physics", "mathematics_aa", "mathematics_ai", "chemistry", "computer_science", "biology", "ess"
ROUND9 = json.loads((Path(__file__).parents[1] / "fixtures" / "stem" / "round9" / "c2_answers.json").read_text(encoding="utf-8"))["answers"]


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
    a = ROUND9[tid]
    peer = (a["peer_text"],) if a["peer_text"] else ()
    return receive(a["profile"], a["response_text"] if text is None else text, a["question"], peer)


def mutated(tid: str, *edits: str):
    text = ROUND9[tid]["response_text"]
    for old, new in zip(edits[::2], edits[1::2]):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return recorded(tid, text)


def findings(rc) -> list:
    return list(rc.findings) + list(rc.structural_findings)


def errors(rc) -> list[tuple[str, tuple[str, ...]]]:
    return [(f.code, tuple(f.claim_ids)) for f in findings(rc) if f.severity == "error"]


def stem_errors(rc) -> list[tuple[str, tuple[str, ...]]]:
    """The errors of the STEM checks (a line that repeats the request is also named INT-REQ-011, which is no STEM finding)."""
    return [e for e in errors(rc) if e[0] == "INT-SUBJ-001"]


def named(rc, code: str, claim: "str | None" = None) -> bool:
    return any(f.code == code and (claim is None or claim in f.claim_ids) for f in findings(rc))


def failed(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is False]


def held(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is True]


def subj_warnings(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-004"]


def messages(rc) -> list[str]:
    return [f"{f.severity} {f.code} {list(f.claim_ids)} {f.message[:200]}" for f in findings(rc)]


# ============================================================================== the recorded answers: correct work is never an error

@pytest.mark.parametrize("tid", sorted(ROUND9))
def test_no_recorded_round_9_answer_carries_a_stem_error(tid):
    """Four false INT-SUBJ-001 on three of the genuine STEM answers of round 9 (ch-p9b, maa-t15, ph-t15 twice) and one on the cs-t15 answer
    the specialist revised from feedback: every one of these answers is correct, so none carries an error now."""
    rc = recorded(tid)
    assert not [e for e in errors(rc) if e[0] == "INT-SUBJ-001"], messages(rc)


@pytest.mark.parametrize("tid", ["ph-t15", "ph-t15-revised", "cs-t15", "cs-t15-revised", "ch-p9b"])
def test_the_recorded_answers_with_false_warnings_carry_none(tid):
    """ph-t15 s5.1/s5.2 (a step from the principle line, and the substitution of part (d)), the revised ph-t15's coupled mass, cs-t15 c1.1
    ('1 Mbit = 10⁶ bits' against the request's 10⁶ bytes) and the revised cs-t15's 'reads Mbit as 10⁶ bits' had INT-SUBJ-004 on correct
    work."""
    rc = recorded(tid)
    assert not subj_warnings(rc), messages(rc)


# ============================================================================== a condition is no assertion (maa-t15)

def test_the_derived_condition_is_read_with_the_condition_the_part_states():
    """maa-t15 m2.2/m2.3: '36 − 4k > 0' after 'Two distinct real roots need Δ > 0' and 'Δ = (−6)² − 4(1)(k)' had been decided from the
    equation alone, as if it held for every k (counterexample k = 9): the condition is a premise of the step now (rule stated-condition), and
    the request's 'For k = 5' of part (b) gives k no value in part (a) (rule part-condition, order relations)."""
    rc = recorded("maa-t15")
    assert not errors(rc), messages(rc)
    assert any(c.constraint_id.startswith("stem-cmp") and c.satisfied for c in rc.formal_checks)


@pytest.mark.parametrize("edits", [
    ("k < 9  A1\n\nSo the required values are k < 9.", "k < 6  A1\n\nSo the required values are k < 6."),  # the wrong final answer
    ("36 − 4k > 0  A1", "36 − 4k < 0  A1"),  # the condition reversed
    ("with a = 1, b", "with a = 4, b"),  # the round's arithmetic slip: a coefficient stated in prose
    ("b = −6, c = k", "b = −9, c = k"),  # the round's substitution fault
    ("x² − 6x = (x − 3)² − 9", "x² − 6x = (x − 3)² − 6"),  # the lens's variant: a completed square
])
def test_the_faults_of_part_a_are_named(edits):
    rc = mutated("maa-t15", *edits)
    assert named(rc, "INT-SUBJ-001"), messages(rc)


def test_the_condition_control_of_the_communication_lens_holds():
    """K20: the same working without the prose coefficients ('Δ = b² − 4ac' then 'Δ = (−6)² − 4(1)(k)'): the line puts values in for a and
    b and the symbol k for c (rule substitution-instance), so no step leaves c free, and the inequality steps hold."""
    rc = receive(AA, "(a) Two distinct real roots need Δ > 0, where Δ = b² − 4ac:\nΔ = (−6)² − 4(1)(k)\n36 − 4k > 0\n4k < 36\nk < 9\n\n"
                     "(b) For k = 5, f(x) = x² − 6x + 5 = (x − 3)² − 4.",
                 "Let f(x) = x² − 6x + k. (a) Find the values of k for which f(x) = 0 has two distinct real roots. (b) For k = 5, complete the square.")
    assert not errors(rc), messages(rc)
    wrong = receive(AA, "(a) Two distinct real roots need Δ > 0, where Δ = b² − 4ac:\nΔ = (−6)² − 4(1)(k)\n36 − 4k > 0\n4k < 36\nk < 8\n",
                    "Let f(x) = x² − 6x + k. (a) Find the values of k for which f(x) = 0 has two distinct real roots.")
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)  # E3b of the communication lens: 'k < 8'


# ============================================================================== bindings scoped to their part (ch-p9b, ph-t15)

CH = ("A technician dissolved 84.20 g of sucrose, C₁₂H₂₂O₁₁, and made the solution up to 250.0 cm³. Use C 12.01, H 1.01, O 16.00. "
      "Calculate the concentration, and the number of molecules in 1.00 cm³ of a dilution.")
TWO_PARTS_V = ("(b) V = 250.0 cm³ = 0.2500 dm³\nc = 0.245954 mol ÷ 0.2500 dm³ = 0.98382 mol dm⁻³\n\n(e) V = 1.00 cm³ = 1.00 × 10⁻³ dm³\n"
               "n = 0.19676 mol dm⁻³ × 1.00 × 10⁻³ dm³ = 1.9676 × 10⁻⁴ mol")


def test_a_symbol_stated_again_in_another_part_restates_its_own_value():
    """ch-p9b s5.2/s11.2: 'V = 1.00 cm³ = 1.00 × 10⁻³ dm³' in (e) had been set against part (b)'s V = 0.2500 dm³ (rule unit-restatement,
    c = 1/4000, r = 1/1000000): the line states its own value, which its own conversion checks."""
    rc = receive(CHEM, TWO_PARTS_V, CH)
    assert not errors(rc), messages(rc)
    assert len([c for c in rc.formal_checks if c.constraint_id.startswith("stem-cnv") and c.satisfied]) >= 2
    wrong = receive(CHEM, TWO_PARTS_V.replace("= 1.00 × 10⁻³ dm³\n", "= 1.00 × 10⁻² dm³\n"), CH)
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)  # G28: the wrong conversion of part (e) itself


def test_the_hours_restatement_of_the_same_part_is_still_a_conversion():
    """The round-8 rule keeps its case: a line that gives T a value in hours after the seconds of the same part restates them."""
    hours = "T² = 1.156 × 10⁸ s²\nT = √(1.156 × 10⁸ s²) = 1.075 × 10⁴ s\nT = (1.075 × 10⁴ s)/(3600 s h⁻¹) = 2.99 h"
    rc = receive(PHYS, hours)
    assert not errors(rc) and any(c.constraint_id.startswith("stem-cnv") and c.satisfied for c in rc.formal_checks), messages(rc)
    wrong = receive(PHYS, hours.replace("= 2.99 h", "= 3.26 h"))
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)


PH = ("A railway wagon of mass 1.2 × 10⁴ kg is released from rest and rolls down through a vertical height of 0.46 m. "
      "It then collides with a stationary wagon of mass 8.0 × 10³ kg and the two couple together. The coupled wagons are "
      "brought to rest by a buffer in 0.60 s. Show your working with units.")
MOMENTUM = ("m₁u₁ + m₂u₂ = (m₁ + m₂)v\n(1.2 × 10⁴ kg)(3.0 m s⁻¹) + (8.0 × 10³ kg)(0) = (1.2 × 10⁴ kg + 8.0 × 10³ kg)v\n"
            "3.6 × 10⁴ kg m s⁻¹ = (2.0 × 10⁴ kg)v\nv = 1.8 m s⁻¹")


def test_a_law_substituted_with_an_unknown_left_reads_both_sides():
    """ph-t15 s3.2/s3.3: the law, then the law with values put in on both sides and v left: u₁ and u₂ (the stationary wagon's 0) had stayed
    free, so the step was refuted at error severity (r = 36001). Both sides' values are read for their symbols now (rule
    premise-substitution); a wrong value of a stated symbol still fails."""
    rc = receive(PHYS, MOMENTUM, PH)
    assert not errors(rc) and not subj_warnings(rc), messages(rc)
    swapped = receive(PHYS, "m₁ = 1.2 × 10⁴ kg, u₁ = 3.0 m s⁻¹, m₂ = 8.0 × 10³ kg, u₂ = 0.\nm₁u₁ + m₂u₂ = (m₁ + m₂)v\n"
                            "(8.0 × 10³ kg)(3.0 m s⁻¹) + (1.2 × 10⁴ kg)(0) = (2.0 × 10⁴ kg)v\nv = 1.2 m s⁻¹", PH)
    assert named(swapped, "INT-SUBJ-001"), messages(swapped)  # G02


PARTS_REUSE = ("(a) v² = 2 × 9.8 m s⁻² × 0.46 m = 9.016 m² s⁻², so v = 3.00 m s⁻¹\n\n(b) v = 1.8 m s⁻¹, in the original direction\n\n"
               "(d) Principle: impulse equals change in momentum, FΔt = Δp.\nΔp = m(v − u) = (2.0 × 10⁴ kg)(0 − 1.8 m s⁻¹) = −3.6 × 10⁴ kg m s⁻¹")


def test_a_velocity_the_question_brings_to_rest_is_read_in_its_part():
    """ph-t15 s5.1/s5.2: 'Δp = m(v − u) = (2.0 × 10⁴ kg)(0 − 1.8 m s⁻¹)' in (d) had been set against the velocities parts (a) and (b) gave v
    (INT-SUBJ-001), and read as a step from the principle line (INT-SUBJ-004); the zero is the velocity the question states in words (rule
    rest-value), u the result part (b) carries (rule carried-value), m the coupled mass (rule combined-value), and the line states a new law
    (rule new-law)."""
    rc = receive(PHYS, PARTS_REUSE, PH)
    assert not errors(rc) and not subj_warnings(rc), messages(rc)
    sign = receive(PHYS, PARTS_REUSE.replace("= −3.6 × 10⁴ kg m s⁻¹", "= 3.6 × 10⁴ kg m s⁻¹"), PH)
    assert named(sign, "INT-SUBJ-001"), messages(sign)  # G10: the sign slip
    wrong_v = receive(PHYS, PARTS_REUSE.replace("(b) v = 1.8 m s⁻¹", "(b) v = 2.8 m s⁻¹"), PH)
    assert not errors(wrong_v) or named(wrong_v, "INT-SUBJ-001")  # E2f's slip of part (b) is that part's own


def test_a_value_no_question_brings_to_rest_is_still_set_against_the_bindings():
    """The control of rule rest-value: with no words of rest in the request, a zero put in for v in another part is still checked against
    v's stated values, at error severity, as STEM repair 6 has it."""
    rc = receive(PHYS, PARTS_REUSE, "A railway wagon of mass 1.2 × 10⁴ kg rolls down a slope through 0.46 m and collides with a wagon of mass "
                                    "8.0 × 10³ kg moving at 1.0 m s⁻¹.")
    assert named(rc, "INT-SUBJ-001"), messages(rc)


X3A = ("Givens:\nM = 6.4 × 10²³ kg\nr = 5.000 × 10⁶ m\nG = 6.67 × 10⁻¹¹ N m² kg⁻²\nπ = 3.14159\n\n(b) [3]\nT² = 4π²r³/(GM)\n"
       "T² = (39.48)(1.250 × 10²⁰ m³)/(4.2688 × 10¹³ N m² kg⁻¹) = 1.156 × 10⁸ s²\nT = √(1.156 × 10⁸ s²) = 1.075 × 10⁴ s\n")
ORBIT = ("A satellite orbits a planet of mass 6.4 × 10²³ kg at a radius of 5.000 × 10⁶ m. G = 6.67 × 10⁻¹¹ N m² kg⁻². (b) Calculate the period T "
         "of the orbit.")


@pytest.mark.parametrize("answer,ok", [
    (X3A, True),
    (X3A.replace("(39.48)", "4π²"), True),
    (X3A.replace("= 1.156 × 10⁸ s²", "= 1.256 × 10⁸ s²").replace("√(1.156", "√(1.256").replace("= 1.075 × 10⁴ s", "= 1.121 × 10⁴ s"), False),
    (X3A.replace("(1.250 × 10²⁰ m³)", "(1.350 × 10²⁰ m³)").replace("= 1.156 × 10⁸ s²", "= 1.249 × 10⁸ s²").replace("√(1.156", "√(1.249")
     .replace("= 1.075 × 10⁴ s", "= 1.118 × 10⁴ s"), False),
])
def test_a_law_evaluated_with_a_rounded_constant_on_the_next_line_is_a_substitution(answer, ok):
    """X3a (carried from round 8): 'T² = 4π²r³/(GM)' then 'T² = (39.48)(…)/(…) = …' had been an algebra step decided exactly, so the rounded
    4π² refuted it (r = 77109375000/667). The line evaluates the law at the values it writes (rule evaluation-step): a substitution within
    the '=' band; a wrong result and a wrong value put in are still errors."""
    rc = receive(PHYS, answer, ORBIT)
    assert (not errors(rc)) is ok, messages(rc)
    if not ok:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


# ============================================================================== Computer Science: data units and conventions (cs-t15)

CS_REQ = ("(b) A video file is 1.8 GB and the school's upload speed is 40 Mbit/s. Calculate the minimum time, in minutes, needed to upload the "
          "file. Take 1 GB = 1000 MB and 1 byte = 8 bits. [3] (c) Files are sent in packets that each carry 1500 bytes of data. Calculate the "
          "number of packets needed to send a 6.0 MB file, taking 1 MB = 10⁶ bytes. [2]")


@pytest.mark.parametrize("line,ok", [
    ("1.8 GB × 1000 MB per GB = 1800 MB", True),
    ("1.8 GB × 1000 MB per GB = 4800 MB", False),  # the round's arithmetic slip
    ("1.8 GB × 4000 MB per GB = 1800 MB", False),  # the round's substitution fault
    ("Upload speed 40 Mbit/s = 40 × 10⁶ bits per second = 4.0 × 10⁷ bits per second", True),
    ("1 kbit = 1000 bits", True),
    ("1 kbit = 100 bits", False),
    ("1 byte = 8 bits", True),
    ("1 byte = 4 bits", False),
    ("6 bytes = 40 bits", False),
])
def test_data_units_under_the_stated_convention_are_decided(line, ok):
    """cs-t15 c3.2 had eight readings (MB and GB binary or decimal: ST-PARSE-002, unchecked) though the request fixes 1 GB = 1000 MB (rule
    data-convention); 'Mbit' was an unknown atom; a whole number converted had its own half-width added to the band, so '1 byte = 4 bits'
    held (rule converted-value)."""
    rc = receive(CS, line, CS_REQ)
    if ok:
        assert not stem_errors(rc) and held(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


def test_a_unit_defined_by_a_value_restates_no_result():
    """The revised cs-t15 c1.3/c1.4 (K25): 'this answer reads Mbit as 10⁶ bits' after '1 MB = 10⁶ bytes' had been set against the megabyte
    as a restated result (c = 8000000, r = 1000000; rule unit-definition)."""
    rc = receive(CS, "Assumptions: 1 MB = 10⁶ bytes. The question does not define Mbit, so this answer reads Mbit as 10⁶ bits, the SI meaning "
                     "of the prefix M.", "A file is 1.8 GB. Take 1 GB = 1000 MB and 1 byte = 8 bits; 1 MB = 10⁶ bytes.")
    assert not errors(rc) and not subj_warnings(rc), messages(rc)


@pytest.mark.parametrize("text,stated", [("Take 1 GB = 1000 MB and 1 byte = 8 bits", True), ("taking 1 MB = 10⁶ bytes", True),
                                         ("1 MB = 10^6 bytes", True), ("1 kB = 1 000 bytes", True), ("1 KB = 1024 bytes", False),
                                         ("1 GB = 1000 MB; 1 KB = 1024 B", False), ("no convention here", False)])
def test_the_decimal_convention_is_read_from_the_texts(text, stated):
    assert decimal_data_stated(text) is stated


def test_the_multiples_of_the_bit_are_units():
    for word, factor in (("kbit", 1000), ("Mbit", 10 ** 6), ("Gbit", 10 ** 9)):
        u = stem_parse_unit(word)
        assert u is not None and not u.unknown and [r.factor for r in u.readings] == [factor], word
    assert stem_parse_unit("packets") is not None and not stem_parse_unit("bytes per packet").unknown


# ============================================================================== dashes written for a minus sign

@pytest.mark.parametrize("dash", ["–", "—", "‐"])
def test_a_dash_between_two_numbers_is_a_minus(dash):
    """'Δv = 20 – 4.0 = 16 m s⁻¹' had cut the left operand: '4.0 = 16 m s⁻¹' was checked and failed (INT-SUBJ-001 on correct work; rule
    spaced-dash)."""
    rc = receive(PHYS, f"Δv = 20 {dash} 4.0 = 16 m s⁻¹")
    assert not errors(rc) and held(rc), messages(rc)
    wrong = receive(PHYS, f"Δv = 20 {dash} 4.0 = 15 m s⁻¹")
    assert named(wrong, "INT-SUBJ-001"), messages(wrong)
    prose = receive(PHYS, f"The change in speed is 20 {dash} 4.0 = 16 m s⁻¹, so the car slowed.")
    assert not errors(prose), messages(prose)


def test_a_dash_after_a_letter_withholds_the_relation_and_a_prose_dash_keeps_its_check():
    rc = receive(PHYS, "Δv = v – 4.0 = 16 m s⁻¹")
    assert not errors(rc) and named(rc, "ST-PARSE-001"), messages(rc)
    prose = receive(PHYS, "a = 20/4.0 = 5.0 m s⁻² — the acceleration of the trolley.")
    assert not errors(prose) and held(prose) and not named(prose, "ST-PARSE-001"), messages(prose)


# ============================================================================== chemistry readings (ch-t15)

@pytest.mark.parametrize("line,code", [("Volume of NH₃ = 1500 cm³ H₂ × (2 ÷ 3) = 1000 cm³", None),
                                       ("Volume of NH₃ = 1500 cm³ H₂ × (2 ÷ 3) = 1200 cm³", "INT-SUBJ-001"),
                                       ("Volume of NH₃ = 1500 cm³ H₂ × (2 ÷ 3) = 1000 cm²", "ST-DIM-001")])
def test_a_formula_after_a_unit_labels_the_quantity(line, code):
    """ch-t15 s8.6: the formula after the unit ended the maths run, so the line was read as 'NH₃ = 1500 cm³' and a label binding: the
    round's wrong unit ('1000 cm²') and a wrong value crossed with nothing named (rule species-label)."""
    rc = receive(CHEM, line)
    if code is None:
        assert not errors(rc) and held(rc), messages(rc)
    else:
        assert named(rc, code), messages(rc)


def test_a_bond_count_is_checked_against_the_bond_enthalpies_the_request_gives():
    """ch-t15 s3.1: '4 × N≡N + 3 × H–H = 1 × 945 + 3 × 436' (the round's substitution fault) crossed with only the arithmetic held: the
    bonds had no value. The request's 'N≡N 945 kJ mol⁻¹' binds the bond now (rule bond-data), and the sum is evaluated."""
    rc = mutated("ch-t15", "Bonds broken: 1 × N≡N", "Bonds broken: 4 × N≡N")
    assert named(rc, "INT-SUBJ-001", "s3.1"), messages(rc)
    assert not errors(recorded("ch-t15"))


@pytest.mark.parametrize("ratio,ok", [("1 : 2", True), ("1 : 3", False)])
def test_a_mole_ratio_stated_alone_is_checked(ratio, ok):
    """'N₂ + 3H₂ → 2NH₃. The mole ratio of N₂ to NH₃ is 1 : 3.': the full stop after the ratio had stopped the reading, and a sentence that
    holds no relation had no item to plan the check from."""
    rc = receive(CHEM, f"N₂ + 3H₂ → 2NH₃. The mole ratio of N₂ to NH₃ is {ratio}.")
    assert any(c.constraint_id.startswith("stem-eq") for c in rc.formal_checks), messages(rc)
    assert (not subj_warnings(rc)) is ok, messages(rc)


def test_a_word_formula_claim_starts_where_its_words_start():
    """ch-t15 s12.1 had been 'n = amount ÷ volume, with V = 2.00 dm³:' for 'Concentration = amount ÷ volume, …': the word formula's symbol
    was written at the end of its words, so the run, the statement and the claim started on the word's last letter."""
    for text, profile, word in (("Concentration = amount ÷ volume, with V = 2.00 dm³:\nc = 0.400 mol ÷ 2.00 dm³ = 0.200 mol dm⁻³", CHEM, "Concentration"),
                                ("Momentum = mass × velocity = 2.0 kg × 3.0 m s⁻¹ = 6.0 kg m s⁻¹", PHYS, "Momentum"),
                                ("Pressure = force ÷ area", PHYS, "Pressure")):
        doc = build_document(text, "Answer the question.", profile)
        assert doc.statement_text(doc.statements[0].id).startswith(word), [doc.statement_text(s.id) for s in doc.statements]


# ============================================================================== physics and mathematics readings

@pytest.mark.parametrize("answer,ok", [("The ball falls from rest, so mgh = ½mv² and v² = 2gh.", True),
                                       ("The ball falls from rest, so mgh = ½mv² and v² = gh.", False)])
def test_a_step_joined_to_its_law_by_and_is_checked(answer, ok):
    """c1 #7: 'So mgh = ½mv² and v² = gh.' was neither checked nor named (rule and-step, laws)."""
    rc = receive(PHYS, answer, "A ball falls from rest through a height h. Find v² at the bottom.")
    assert held(rc) if ok else named(rc, "INT-SUBJ-001"), messages(rc)


@pytest.mark.parametrize("answer,request_text", [
    ("W = mg = 2.0 kg × 9.18 m s⁻² = 18.4 N", "Calculate the weight of a 2.0 kg mass."),
    ("E = hf = 6.36 × 10⁻³⁴ J s × 5.0 × 10¹⁴ Hz = 3.2 × 10⁻¹⁹ J", "Calculate the energy of a photon of frequency 5.0 × 10¹⁴ Hz."),
])
def test_a_booklet_constant_put_in_as_a_numeral_is_set_against_the_booklet(answer, request_text):
    """c1 #15: the substitution introduced the value of g or h, so the booklet was never consulted (rule booklet-value, substitutions)."""
    rc = receive(PHYS, answer, request_text)
    assert subj_warnings(rc), messages(rc)
    good = receive(PHYS, answer.replace("9.18", "9.81").replace("18.4", "19.6").replace("6.36", "6.63").replace("3.2 ×", "3.3 ×"), request_text)
    assert not subj_warnings(good) and not errors(good), messages(good)


def test_the_molar_volume_put_in_is_set_against_the_booklet():
    rc = receive(CHEM, "At STP, V = nV_m = 0.100 mol × 22.4 dm³ mol⁻¹ = 2.24 dm³")
    assert subj_warnings(rc), messages(rc)
    assert not subj_warnings(receive(CHEM, "At STP, V = nV_m = 0.100 mol × 22.7 dm³ mol⁻¹ = 2.27 dm³"))


def test_a_step_after_a_mark_annotation_is_checked():
    """mai-t15 m6.1/m7.1: '$y - 2 = -6(x - 5)$ M1' then '$y = -3x + 17$ A1' (the round's arithmetic slip) crossed: the closing delimiter
    and the mark annotation after the line kept it from ending its statement, so no step was read."""
    rc = mutated("mai-t15", "is $y - 2 = -3(x - 5)$ M1", "is $y - 2 = -6(x - 5)$ M1")
    assert named(rc, "INT-SUBJ-001"), messages(rc)
    assert not errors(recorded("mai-t15"))


# ============================================================================== Computer Science: Boolean tables and derivations

TT_REQ = "A circuit has output X = (A AND B) OR (NOT A AND C). Construct the truth table for X."
TT_ROWS = "| A | B | C | X |\n|---|---|---|---|\n"


@pytest.mark.parametrize("outputs,ok", [("01010011", True), ("11110111", False)])
def test_a_truth_table_of_an_output_the_request_defines_is_checked(outputs, ok):
    """c1 #13/#14 (a): a plain A | B | C | X table under 'output X = …' had been named undecided only."""
    rows = "".join(f"| {a} | {b} | {c} | {o} |\n" for (a, b, c), o in zip(((a, b, c) for a in "01" for b in "01" for c in "01"), outputs))
    rc = receive(CS, TT_ROWS + rows, TT_REQ)
    assert held(rc) if ok else named(rc, "INT-SUBJ-001"), messages(rc)


DERIVATION = ("NOT (A OR B) AND A\n= (NOT A AND NOT B) AND A, by De Morgan's law\n= NOT B AND (NOT A AND A), by the associative law\n"
              "= NOT B AND {x}, by the complement law\n= {y}, by the {law} law")


@pytest.mark.parametrize("x,y,law,ok", [("0", "0", "null", True), ("1", "NOT B", "identity", False)])
def test_a_derivation_on_consecutive_lines_is_checked_line_by_line(x, y, law, ok):
    """c1 #13/#14 (b): with no blank line between them, only the first step of the derivation had been read."""
    rc = receive(CS, DERIVATION.format(x=x, y=y, law=law), "Use Boolean algebra to show that NOT (A OR B) AND A simplifies to 0.")
    assert (not failed(rc)) is ok and (named(rc, "INT-SUBJ-001") is not ok), messages(rc)


# ============================================================================== prose shares, folds and comparisons

@pytest.mark.parametrize("profile,text,ok", [
    (ESS, "Species 1 makes up 62.5% of the individuals (25 of 40).", True),
    (ESS, "Species 1 makes up 72.5% of the individuals (25 of 40).", False),
    (ESS, "Its most common species makes up 30% of its individuals (12 of 40), whereas species 1 makes up 62.5% of Woodland B’s individuals "
          "(25 of 40).", True),
    (BIO, "Ventilation rises from 7.0 to 51.2 dm³ min⁻¹, about 7.3 times the resting rate.", True),
    (BIO, "Ventilation rises from 7.0 to 51.2 dm³ min⁻¹, about 9.3 times the resting rate.", False),
    (ESS, "Woodland A’s D value is higher, 5.38 against 2.33, so Woodland A has greater biodiversity.", True),
    (ESS, "Woodland A’s D value is higher, 2.33 against 5.38, so Woodland A has greater biodiversity.", False),
])
def test_a_relation_the_prose_states_between_its_values_is_checked(profile, text, ok):
    """c1 #12 and the lens's variants G33, G34: a reversed share, a fold after a from-to pair and a worded comparison crossed with no check
    and no finding (rules prose-share reversed, prose-fold, worded-comparison)."""
    rc = receive(profile, text)
    if ok:
        assert held(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


# ============================================================================== format characters inside a figure

@pytest.mark.parametrize("char", ["\u200b", "\u2060", "\u00ad", "\ufeff", "\U000e0031"])
def test_a_format_character_inside_a_figure_is_named(char):
    """bi-t15 '= 7.0 dm³ min⁻¹' written '= 7.<char>5 dm³ min⁻¹': the relation was checked against '7' and held, so the wrong result crossed
    with no finding. A relation reaching a figure with an invisible format character inside it is named (rule format-character)."""
    text = ROUND9["bi-t15"]["response_text"]
    assert text.count("= 7.0 dm³ min⁻¹ [1]") == 1
    rc = recorded("bi-t15", text.replace("= 7.0 dm³ min⁻¹ [1]", "= 7." + char + "5 dm³ min⁻¹ [1]"))
    # the channel may refuse the response itself (INT-REQ-009 for the characters it refuses); the STEM pack names the figure in any case
    assert named(rc, "ST-PARSE-001") or named(rc, "INT-REQ-009"), messages(rc)
    assert not held(rc) or not any("7." in c.detail and "= 7" in c.detail for c in rc.formal_checks if c.satisfied), messages(rc)
    doc = build_document(text.replace("= 7.0 dm³ min⁻¹ [1]", "= 7." + char + "5 dm³ min⁻¹ [1]"), ROUND9["bi-t15"]["question"], BIO)
    assert any(f.code == "ST-PARSE-001" and "format character" in f.message for f in doc.findings), [f.message[:120] for f in doc.findings]
    plain = recorded("bi-t15", text.replace("= 7.0 dm³ min⁻¹ [1]", "= 7.5 dm³ min⁻¹ [1]"))
    assert named(plain, "INT-SUBJ-001"), messages(plain)


# ============================================================================== a temperature stated in °C put in in kelvin

_GAS_BOUND = "A gas sample: p = 1.0 × 10⁵ Pa, V = 2.0 × 10⁻³ m³, T = 27 °C. R = 8.31 J K⁻¹ mol⁻¹. Calculate n."
_GAS_WORDS = "A gas sample of volume 2.0 × 10⁻³ m³ at 27 °C and 1.0 × 10⁵ Pa. Calculate the amount n."
_GAS_V = "A gas: n = 0.50 mol, T = 27 °C, p = 1.0 × 10⁵ Pa. Calculate V."


@pytest.mark.parametrize("profile,answer,request_text,ok", [
    (CHEM, "n = pV/(RT) = (1.0 × 10⁵ Pa × 2.0 × 10⁻³ m³)/(8.31 J K⁻¹ mol⁻¹ × 27 K) = 0.89 mol", _GAS_BOUND, False),
    (CHEM, "n = pV/(RT) = (1.0 × 10⁵ Pa × 2.0 × 10⁻³ m³)/(8.31 J K⁻¹ mol⁻¹ × 300 K) = 0.080 mol", _GAS_BOUND, True),
    (CHEM, "n = pV/(RT) = (1.0 × 10⁵ Pa × 2.0 × 10⁻³ m³)/(8.31 J K⁻¹ mol⁻¹ × 27 K) = 0.89 mol", _GAS_WORDS, False),
    (CHEM, "n = pV/(RT) = (1.0 × 10⁵ Pa × 2.0 × 10⁻³ m³)/(8.31 J K⁻¹ mol⁻¹ × 300 K) = 0.080 mol", _GAS_WORDS, True),
    (PHYS, "n = pV/(RT) = (1.0 × 10⁵ Pa × 2.0 × 10⁻³ m³)/(8.31 J K⁻¹ mol⁻¹ × 27 K) = 0.89 mol", _GAS_WORDS, False),
    (PHYS, "n = pV/(RT) = (1.0 × 10⁵ Pa × 2.0 × 10⁻³ m³)/(8.31 J K⁻¹ mol⁻¹ × 300.15 K) = 0.0802 mol", _GAS_WORDS, True),
    (PHYS, "V = nRT/p = (0.50 mol × 8.31 J K⁻¹ mol⁻¹ × 27 K)/(1.0 × 10⁵ Pa) = 1.1 × 10⁻³ m³", _GAS_V, False),
    (PHYS, "V = nRT/p = (0.50 mol × 8.31 J K⁻¹ mol⁻¹ × 300 K)/(1.0 × 10⁵ Pa) = 1.2 × 10⁻² m³", _GAS_V, True),
    (PHYS, "V = nRT/p = (0.50 mol × 8.31 J K⁻¹ mol⁻¹ × 27 K)/(1.0 × 10⁵ Pa) = 1.1 × 10⁻³ m³",
     "A gas of 0.50 mol at 27 °C and 1.0 × 10⁵ Pa. Calculate V.", False),
])
def test_a_celsius_temperature_put_in_as_the_same_number_of_kelvin_is_named(profile, answer, request_text, ok):
    """G05 (critical): a temperature the request gives in °C, substituted as the same number in kelvin, was never compared with the
    request, so the Celsius-for-kelvin slip crossed ACCEPTED. The substituted value is set against the request's value in kelvin, the
    offset exact (rule kelvin-substitution): an error when the request binds the symbol ('T = 27 °C'), a warning when the request states
    the temperature in words (which quantity it is, is a reading). The value converted correctly holds with no finding."""
    rc = receive(profile, answer, request_text)
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc) and not subj_warnings(rc), messages(rc)
    else:
        assert failed(rc), messages(rc)
        assert named(rc, "INT-SUBJ-001") or subj_warnings(rc), messages(rc)
        if "T = 27 °C" in request_text:
            assert named(rc, "INT-SUBJ-001"), messages(rc)


@pytest.mark.parametrize("request_text", ["Water of mass 2.0 kg is heated by 27 °C. Calculate the energy Q.",
                                          "Water of mass 2.0 kg has a temperature rise of 27 °C. Calculate the energy Q."])
def test_a_temperature_change_stated_in_celsius_is_the_same_number_of_kelvin(request_text):
    """Clean control of rule kelvin-substitution: a change of temperature has no offset, so '27 K' for the request's change of 27 °C
    holds with no finding."""
    rc = receive(PHYS, "Q = mcΔT = 2.0 kg × 4200 J kg⁻¹ K⁻¹ × 27 K = 2.3 × 10⁵ J", request_text)
    assert held(rc) and not failed(rc) and not errors(rc) and not subj_warnings(rc), messages(rc)


# ============================================================================== calculations laid out in a table (rule table-working)

_TABLE_HEAD = "| Solution | Working | Change in mass |\n|---|---|---|\n"


@pytest.mark.parametrize("row,ok", [
    ("| Distilled water | (2.81 − 2.50) ÷ 2.50 × 100 | +12.4% |", True),
    ("| Distilled water | (2.81 − 2.50) ÷ 2.50 × 100 | +16.4% |", False),
    ("| 0.590 mol dm⁻³ | (2.30 − 2.49) ÷ 2.49 × 100 | −7.6% |", True),
    ("| 0.590 mol dm⁻³ | (2.30 − 2.49) ÷ 2.49 × 100 | −9.6% |", False),
])
def test_a_table_cell_of_arithmetic_is_set_against_the_value_after_it(row, ok):
    """bi-p9b part (a): six rows of '| solution | arithmetic | result |' had no check at all, so a wrong percentage crossed with no
    finding. The cell of arithmetic is read with the value of the next cell as its result; that pairing is a reading, so a failure is
    a warning (rule table-working)."""
    rc = receive(BIO, _TABLE_HEAD + row)
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc) and not subj_warnings(rc), messages(rc)
    else:
        assert failed(rc) and subj_warnings(rc) and not errors(rc), messages(rc)


@pytest.mark.parametrize("answer,ok", [
    ("| Solution | Working |\n|---|---|\n| Distilled water | (2.81 − 2.50) ÷ 2.50 × 100 = +12.4% |", True),
    ("| Solution | Working |\n|---|---|\n| Distilled water | (2.81 − 2.50) ÷ 2.50 × 100 = +16.4% |", False),
    ("| Quantity | Working | Value |\n|---|---|---|\n| Speed | 100 m ÷ 20 s | 5.0 m s⁻¹ |", True),
    ("| Quantity | Working | Value |\n|---|---|---|\n| Speed | 100 m ÷ 20 s | 7.0 m s⁻¹ |", False),
])
def test_working_written_inside_a_table_cell_is_checked(answer, ok):
    """A cell holding 'arithmetic = value' is a line of working (an error when it fails); a speed cell and its value cell as above."""
    rc = receive(PHYS, answer)
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert failed(rc) and (named(rc, "INT-SUBJ-001") or subj_warnings(rc)), messages(rc)
        if "=" in answer.split("\n")[-1]:
            assert named(rc, "INT-SUBJ-001"), messages(rc)


@pytest.mark.parametrize("low,ok", [("low = mid + 4 = 7", True), ("low = mid + 4 = 4", False)])
def test_a_trace_table_cell_takes_the_value_its_row_states(low, ok):
    """The breadth round's trace-table cell 'low = mid + 4 = 4' with 'mid = 3' in its row crossed; the row's binding cell is read with
    its working cell (and a name bordered by a cell bar is a name: rule table-working)."""
    rc = receive(CS, f"| Step | mid | low |\n|---|---|---|\n| 1 | mid = 3 | {low} |")
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


@pytest.mark.parametrize("answer", ["| Range | Count |\n|---|---|\n| 10 - 20 | 15 |\n| 20-30 | 7 |",
                                    "| Years | Change |\n|---|---|\n| 2019 – 2020 | 15 |",
                                    "| Trial | Time / s |\n|---|---|\n| 1 | 12.1 |\n| 2 | 12.3 |\n| Mean | (12.1 + 12.3) ÷ 2 = 12.2 |"])
def test_a_range_in_a_table_is_no_subtraction(answer):
    """Clean controls of rule table-working: two figures joined by a hyphen or a dash in a cell may be a range, so they are set against
    nothing; a mean worked in a cell holds."""
    rc = receive(PHYS, answer)
    assert not failed(rc) and not errors(rc) and not subj_warnings(rc), messages(rc)


# ============================================================================== numerals written with a thousands space

def test_a_relation_cut_by_a_thousands_space_is_named():
    """G16 and cs-t15: '6 000 000 bytes ÷ 1500 bytes per packet = 5000 packets' was read as the label 'bytes per packet = 5000 packets'
    with no check and no finding. The words before the sign are the unit of a figure of a longer expression: the relation is named
    ST-PARSE-001 (rule cut-label), as a plain space is no thousands separator of the grammar."""
    for answer in ("6 000 000 bytes ÷ 1500 bytes per packet = 5000 packets", "6 000 000 bytes ÷ 1500 bytes per packet = 4000 packets"):
        rc = receive(CS, answer)
        assert named(rc, "ST-PARSE-001") and not held(rc) and not errors(rc), messages(rc)
    control = receive(PHYS, "After 3.0 s the velocity = 15 m s⁻¹")
    assert not named(control, "ST-PARSE-001"), messages(control)


@pytest.mark.parametrize("answer", ["P = 4 000 euros\nI = P × 0.05 = 200 euros", "The principal is P = 4 000 euros, so I = P × 0.05 = 200 euros.",
                                    "Given: P = 4 000 euros\nI = P × 0.05 = 200 euros"])
def test_a_value_written_with_a_thousands_space_binds_nothing(answer):
    """'P = 4 000 euros' bound P = 4, so the correct 'I = P × 0.05 = 200 euros' failed as an error. The value is named (rule
    thousands-value; a Given's by the Given rule) and binds nothing."""
    rc = receive(AI, answer)
    assert not errors(rc) and named(rc, "ST-PARSE-001"), messages(rc)


@pytest.mark.parametrize("answer", ["After the first payment the remaining loan is 23 425 − 7045.59… = 46 379.41… dollars.",
                                    "After the first payment the remaining loan is 23 425 − 7045.59... = 16 379.41... dollars."])
def test_a_relation_of_a_thousands_space_numeral_and_a_cut_decimal_is_named(answer):
    """c1 lens: the line with a space-grouped numeral and a cut decimal was dropped with nothing named (without the ellipsis it was
    ST-PARSE-001): an ellipsis after a digit is maths beside the sign (rule cut-decimal)."""
    rc = receive(AI, answer, "A loan of 23 425 dollars is reduced by a first payment. Find the remaining loan after the first payment.")
    assert named(rc, "ST-PARSE-001") and not errors(rc), messages(rc)


# ============================================================================== coordinate pairs (rule coordinate-pair)

def test_a_midpoint_written_as_a_pair_is_checked_component_by_component():
    """mai-t15 stem_substitution: 'Midpoint of AB = ((5 + 8)/2, (1 + 3)/2)' then '= (5, 2)' was named only undecided (a coordinate pair
    outside the encodings). The pairs are compared component by component; the genuine answer holds with no warning on the pair."""
    text = ROUND9["mai-t15"]["response_text"]
    assert text.count("\\frac{2 + 8}{2}") == 1
    rc = recorded("mai-t15", text.replace("\\frac{2 + 8}{2}", "\\frac{5 + 8}{2}"))
    assert named(rc, "INT-SUBJ-001", "m2.1"), messages(rc)
    genuine = recorded("mai-t15")
    assert not [f for f in findings(genuine) if f.code.startswith("ST-") and "m2.1" in f.claim_ids], messages(genuine)


@pytest.mark.parametrize("answer,ok", [
    ("Midpoint $= \\left(\\frac{2 + 8}{2},\\ \\frac{1 + 3}{2}\\right) = (5,\\ 2)$", True),
    ("Midpoint $= \\left(\\frac{2 + 8}{2},\\ \\frac{1 + 3}{2}\\right) = (5,\\ 3)$", False),
    ("$\\vec{AB} = (8 - 2,\\ 3 - 1) = (6,\\ 2)$", True),
    ("$\\vec{AB} = (8 - 2,\\ 3 - 1) = (6,\\ 1)$", False),
])
def test_pairs_of_closed_components_are_compared_in_order(answer, ok):
    rc = receive(AI, answer)
    if ok:
        assert not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


# ============================================================================== more relations the prose states

@pytest.mark.parametrize("profile,text,ok,code", [
    (ESS, "The peak discharge rose by 200%, from 5.4 m³ s⁻¹ in Storm 1 to 16.2 m³ s⁻¹ in Storm 2.", True, ""),
    (ESS, "The peak discharge rose by 300%, from 5.4 m³ s⁻¹ in Storm 1 to 16.2 m³ s⁻¹ in Storm 2.", False, "INT-SUBJ-001"),
    (ESS, "Impermeable cover rose from 20.0% to 47.5%, a rise of 27.5 percentage points.", True, ""),
    (ESS, "Impermeable cover rose from 20.0% to 47.5%, a rise of 25.7 percentage points.", False, "INT-SUBJ-001"),
    (ESS, "The efficiency (1800 ÷ 1.0 × 10⁴) gives 18%.", True, ""),
    (ESS, "The efficiency (1800 ÷ 1.0 × 10⁴) gives 28%.", False, "INT-SUBJ-001"),
    (ESS, "The food eaten is 1800 kJ m⁻² yr⁻¹. Of the food eaten, 1080 kJ m⁻² yr⁻¹ (60%) was lost as heat.", True, ""),
    (ESS, "The food eaten is 1800 kJ m⁻² yr⁻¹. Of the food eaten, 1080 kJ m⁻² yr⁻¹ (70%) was lost as heat.", False, "INT-SUBJ-004"),
])
def test_changes_points_quotients_and_shares_the_prose_states_are_checked(profile, text, ok, code):
    """c1 #12 and #15 carried: a per cent change with labels between its values (rule prose-change), percentage points (rule
    percentage-points), a bracketed quotient that 'gives' a per cent (rule quotient-share) and a share whose whole an opening clause
    names (rule referent-share, a reading: a warning) crossed with no check and no finding."""
    rc = receive(profile, text)
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc) and not subj_warnings(rc), messages(rc)
    else:
        assert failed(rc) and named(rc, code), messages(rc)


def test_a_share_of_a_whole_the_answer_never_states_is_named_undecided():
    rc = receive(ESS, "Of the food eaten, 1080 kJ m⁻² yr⁻¹ (60%) was lost as heat.")
    assert named(rc, "ST-UNDEC-001"), messages(rc)


@pytest.mark.parametrize("value,ok", [("15.0%", True), ("25.0%", False)])
def test_a_word_formula_before_its_working_leaves_the_working_checked(value, ok):
    """G31: 'percentage yield = actual yield ÷ theoretical yield × 100 = 150 cm³ ÷ 1000 cm³ × 100 = 25.0%' had no span at all (named
    unread only); the word formula is the label of the working after it (rule word-formula-chain)."""
    rc = receive(CHEM, f"percentage yield = actual yield ÷ theoretical yield × 100 = 150 cm³ ÷ 1000 cm³ × 100 = {value}")
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


def test_a_definition_evaluated_at_a_value_the_request_states_is_no_extrapolation():
    """ch-p9b: ST-RANGE-001 named c = n/V evaluated at the request's own 250.0 cm³ flask (and n = cV at part (e)'s 1.00 cm³) against the
    10 to 50 cm³ pipette volumes: a data-booklet definition holds at any value (rule definition-law); a fitted trend past its data is
    still named (tests/stem/test_rounding_range_working.py)."""
    rc = recorded("ch-p9b")
    assert not named(rc, "ST-RANGE-001"), messages(rc)


# ============================================================================== layout: labels with 'to', nested bars

def test_a_labelled_line_whose_label_holds_to_is_no_continuation():
    """mai-t15 (e): 'Distance to B $= …$' after 'Distance to A $= … = 5$ km M1' was read as the next link of that chain (the word 'to'
    counted as a continuation word anywhere in the label), and the relation across the two lines was withheld with a false ST-PARSE-001
    on m18.1/m19.1 and m19.1/m20.1. 'to' continues working only right before the sign."""
    rc = recorded("mai-t15")
    assert not [f for f in findings(rc) if f.code == "ST-PARSE-001" and {"m18.1", "m19.1", "m20.1"} & set(f.claim_ids)], messages(rc)


@pytest.mark.parametrize("answer,ok", [("||1|| = 2", False), ("||3|| = 5", False), ("||−3| − 5| = 7", False), ("||−3| − 5| = 2", True),
                                       ("||3|| = 3", True)])
def test_nested_absolute_values_on_a_line_of_their_own_are_checked(answer, ok):
    """A lone line of nested bars was read as a one-row table, so its relation was neither checked nor named; a lone line of bars that
    does not end with a bar is maths."""
    rc = receive(AA, answer, "Find the value.")
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


# ============================================================================== bounds on hostile input

_N = 20_000
HOSTILE = {
    "species after units": "n = 1500 cm³ H₂ × " * (_N // 18) + "2 = 3",
    "species runs": ("H₂O" * (_N // 3)),
    "format characters": ("7.\u200b5 = " * (_N // 7)) + "1",
    "data conventions": ("1 GB = 1000 MB, " * (_N // 15)),
    "data convention digits": "1 MB = " + "1 000 " * (_N // 6) + "bytes",
    "bit multiples": ("1 kbit = 1000 bits per Mbit, " * (_N // 30)),
    "spaced dashes": ("20 – 4.0 – " * (_N // 11)) + "= 16",
    "dashes after letters": ("v – 4.0 = " * (_N // 10)) + "16",
    "reversed shares": "makes up 62.5% of the individuals (25 of 40), " * (_N // 47),
    "folds": "rises from 7.0 to 51.2 dm³ min⁻¹, about 7.3 times, " * (_N // 52),
    "worded comparisons": "is higher, 5.38 against 2.33, " * (_N // 30),
    "unit definitions": "so this answer reads Mbit as 10⁶ bits, " * (_N // 40),
    "conditions": "need Δ > 0\nΔ = 36 − 4k\n36 − 4k > 0\n" * (_N // 34),
    "substitution instances": "m₁u₁ + m₂u₂ = (m₁ + m₂)v\n(1.2)(3.0) + (8.0)(0) = (1.2 + 8.0)v\n" * (_N // 64),
    "evaluation steps": "T² = 4π²r³/(GM)\nT² = (39.48)(1.25)/(4.27) = 11.6\n" * (_N // 48),
    "completed squares": "Complete the square on x² − 6x:\nx² − 6x = (x − 3)² − 9\n" * (_N // 56),
    "bond sums": "N≡N 945 kJ mol⁻¹, " * 32 + "4 × N≡N + 3 × H–H = 1 × 945 + 3 × 436\n" * (_N // 40),
    "and steps": "so mgh = ½mv² and v² = gh and " * (_N // 30),
    "mark annotations": "is $y - 2 = -3(x - 5)$ M1\n\n$y = -3x + 17$ A1\n" * (_N // 46),
    "derivation lines": "NOT A AND A\n" + "= NOT B AND 1, by the identity law\n" * (_N // 36),
    "celsius substitutions": "V = nRT/p = (0.50 mol × 8.31 J K⁻¹ mol⁻¹ × 27 K)/(1.0 × 10⁵ Pa) = 1.1 × 10⁻³ m³\n" * (_N // 84),
    "table working": "| A | B | C |\n|---|---|---|\n" + "| x = 3 | (2.81 − 2.50) ÷ 2.50 × 100 | +12.4% |\n" * (_N // 46),
    "wide table rows": "| " + "(1 + 2) × 3 | 9 | " * (_N // 18) + "\n|---|\n",
    "thousands spaces": "6 000 000 bytes ÷ 1500 bytes per packet = 4000 packets, P = 4 000 euros, " * (_N // 72),
    "coordinate pairs": "$= \\left(\\frac{2 + 8}{2},\\ \\frac{1 + 3}{2}\\right) = (5,\\ 2)$\n" * (_N // 52),
    "prose changes": "rose by 200%, from 5.4 m³ s⁻¹ in Storm 1 to 16.2 m³ s⁻¹ in Storm 2, a rise of 27.5 percentage points, " * (_N // 104),
    "referent shares": "Of the food eaten, 1080 kJ m⁻² yr⁻¹ (60%) was lost. The food eaten is 1800 kJ m⁻² yr⁻¹. " * (_N // 88),
    "nested bars": "||−3| − 5| = 2\n" * (_N // 15),
    "labels with to": "Distance to A $= \\sqrt{25} = 5$ km M1\n\n" * (_N // 38),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
@pytest.mark.parametrize("profile", [PHYS, AA, CS, CHEM, ESS])
def test_the_new_readings_are_bounded_on_hostile_input(name, profile):
    text = HOSTILE[name]
    clear_document_cache()
    t0 = time.process_time()
    doc = build_document(text, "Answer the question. N≡N 945 kJ mol⁻¹, H–H 436 kJ mol⁻¹. Take 1 GB = 1000 MB. Show that x = 2.", profile)
    build_checks(doc, report_id="r", request_id="q")
    assert time.process_time() - t0 < 8.0, name
