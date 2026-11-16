"""Round-10 clearance (arena round 10, integrated round c3): the STEM findings of the overseer lenses and the records carried from rounds 8
and 9, each reproduced through the hub and fixed at its cause, with clean controls (correct working that must hold, with no error) and
negative controls (wrong working that must still be named). docs/STEM_DESIGN.md, section 42.

* false errors on correct work (seven INT-SUBJ-001 on four genuine c3 answers): the tonne read in every sciences profile when the text names
  tonnes (rule tonne-reading), never a bare value compared before a letter that may be its unit (rule unread-unit-letter); a '±' written on
  the stated value alone read as a margin (rule stated-margin); an evaluation 'f(3) = …' never a definition of f (rule evaluation-head); the
  request's identity words scoped to the part that states them, and an equation in two letters never an identity (rules part-condition for
  identity words and two-variable-equation); 'at r = 3' after a value an evaluation point, never a stated root, and no chain joined across
  inline-maths delimiters with prose between (rules evaluation-point, wherever it stands, and inline-delimiters);
* injected faults that crossed unnamed: a show-that target never a premise of the steps of its own part (rule show-that-target); a mole
  ratio written 'Ratio A : B = x : y'; a prefixed unit, or a unit of another dimension, on SI working (rules si-prefix and si-dimension);
  alignment environments written on one line (rule environment-rows); the working cells of a table beyond its bound named (ST-LIM-002) and
  a table's totals (rule table-totals); a share, a change, a net value, a total over a stated extent the prose states (rules share-or,
  change-share, net-difference, rate-total; derived shares named undecided); a whole sum stated with '=' (rule whole-sum); a unit after a
  bracket bounding its rounding; derivatives with π and negative powers (rule derivative, Laurent terms); 'k_BT' as k_B × T (rule
  subscript-product); abbreviations bound to their numbers (rule abbreviation); a letter of another script between numerals; control
  characters (rule control-character);
* the STEM word-count view keeps the relation signs of working and drops mark annotations and part labels (rule working-view).

The last section bounds the CPU time of every new reading and of each touched module's public entry points on the standard hostile inputs
of about 20,000 characters.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.request_parser import count_words, measure_answer_words
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem import calculus as stem_calculus
from epinoic_logic.stem import checks as stem_checks
from epinoic_logic.stem import document as stem_document
from epinoic_logic.stem import hub_hooks as stem_hooks
from epinoic_logic.stem import lexer as stem_lexer
from epinoic_logic.stem import normalize as stem_normalize
from epinoic_logic.stem import relations as stem_relations
from epinoic_logic.stem import scope as stem_scope
from epinoic_logic.stem import spans as stem_spans
from epinoic_logic.stem import units as stem_units
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.document import clear_document_cache
from epinoic_logic.stem.hub_hooks import StemHooks
from epinoic_logic.translate.contracts import SuppliedText

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"round-10-clearance-stem-key-0123456789"
SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches", "mathematics_ai": "Mathematics: Applications and Interpretation",
            "chemistry": "Chemistry", "computer_science": "Computer Science", "biology": "Biology", "ess": "Environmental Systems and Societies"}
PHYS, AA, AI, CHEM, CS, BIO, ESS = "physics", "mathematics_aa", "mathematics_ai", "chemistry", "computer_science", "biology", "ess"
ROUND10 = json.loads((Path(__file__).parents[1] / "fixtures" / "stem" / "round10" / "c3_answers.json").read_text(encoding="utf-8"))["answers"]


def receive(profile: str, answer: str, request: str = "Answer the question.", texts: "tuple[str, ...] | list[str]" = ()):
    clear_document_cache()
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    supplied = [SuppliedText(document_id=f"doc{i}", title="supplied", text=t) for i, t in enumerate(texts)]
    m, _, _ = hub.dispatch("t", agent, request, supplied)
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    hub.close()
    return rc


def recorded(tid: str, text: "str | None" = None):
    a = ROUND10[tid]
    return receive(a["profile"], a["response_text"] if text is None else text, a["question"], tuple(a["supplied_texts"]))


def mutated(tid: str, *edits: str):
    text = ROUND10[tid]["response_text"]
    for old, new in zip(edits[::2], edits[1::2]):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return recorded(tid, text)


def findings(rc) -> list:
    return list(rc.findings) + list(rc.structural_findings)


def errors(rc) -> list[tuple[str, tuple[str, ...]]]:
    return [(f.code, tuple(f.claim_ids)) for f in findings(rc) if f.severity == "error"]


def stem_errors(rc) -> list[tuple[str, tuple[str, ...]]]:
    return [e for e in errors(rc) if e[0] == "INT-SUBJ-001"]


def named(rc, code: str, text: "str | None" = None) -> bool:
    return any(f.code == code and (text is None or text in f.message) for f in findings(rc))


def failed(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is False]


def held(rc) -> list[str]:
    return [c.constraint_id for c in rc.formal_checks if c.satisfied is True]


def messages(rc) -> list[str]:
    return [f"{f.severity} {f.code} {list(f.claim_ids)} {f.message[:220]}" for f in findings(rc)]


def fault_named(rc, text: str) -> bool:
    """A finding of a failed check (INT-SUBJ-001 or the warning INT-SUBJ-004) that quotes ``text``."""
    return any(f.code in ("INT-SUBJ-001", "INT-SUBJ-004") and text in f.message for f in findings(rc))


# ============================================================================== the recorded answers: correct work is never an error

@pytest.mark.parametrize("tid", sorted(ROUND10))
def test_no_recorded_round_10_answer_carries_a_stem_error(tid):
    """Seven false INT-SUBJ-001 on four genuine STEM answers of c3 (ch-p10c s4.7, ch-t16 s6.1, maa-t16 m3.6/m3.4, m3.11/m3.4, m6.5 and m6.6,
    mai-t16 m21.1/m21.2): every one of these answers is correct, so none carries an INT-SUBJ-001 now, and no check of them fails."""
    rc = recorded(tid)
    assert not stem_errors(rc) and not failed(rc), messages(rc)


def test_the_requested_tonne_totals_of_ch_p10c_are_read_and_hold():
    """The two results the request asks for in tonnes ('Per day: 240 × 0.24441 t = 58.7 t of CO₂', 'Per year: 58.66 t × 360 = 2.11 × 10⁴ t')
    were ST-PARSE-001 'outside the grammar'; with the tonne read they are checked and hold, and the slips '68.7 t' and '2.41 × 10⁴ t' are
    named (the lens's cp-F6 and cp-F7)."""
    rc = recorded("ch-p10c")
    assert not named(rc, "ST-PARSE-001", "Per day") and not named(rc, "ST-PARSE-001", "Per year"), messages(rc)
    assert fault_named(mutated("ch-p10c", "= 58.7 t of CO₂", "= 68.7 t of CO₂"), "68.7 t")
    assert fault_named(mutated("ch-p10c", "= 2.11 × 10⁴ t of CO₂", "= 2.41 × 10⁴ t of CO₂"), "2.41 × 10⁴ t")


@pytest.mark.parametrize("old,new,quote", [
    ("= 2.444 × 10⁵ g = 0.2444 t per bus", "= 2.444 × 10⁵ g = 2.444 t per bus", "2.444 t"),       # g to t slip (cp-F8)
    ("= 144.12 + 26.26 = 170.38 g mol⁻¹", "= 144.12 + 26.26 = 172.38 g mol⁻¹", "172.38"),         # molar mass slip (cp-F3)
])
def test_slips_in_ch_p10c_are_still_named(old, new, quote):
    assert fault_named(mutated("ch-p10c", old, new), quote)


# ============================================================================== false errors: each shape alone, with its control

TONNE_Q = "A fleet releases 2.444 × 10⁵ g of carbon dioxide per day. State this mass in tonnes."


@pytest.mark.parametrize("answer", ["m(CO₂) = 2.444 × 10⁵ g = 0.2444 t per day", "m(CO₂) = 2.444 × 10⁵ g = 0.2444 tonnes per day",
                                    "m(CO₂) = 2.444 × 10⁵ g = 244.4 kg per day"])
def test_a_mass_converted_to_tonnes_holds(answer):
    """Rule tonne-reading: the request names tonnes, so 't' after a number is the tonne in Chemistry too (and the word 'tonnes' in every
    profile); '2.444 × 10⁵ g = 0.2444 t' had been read as '2.444 × 10⁵ g = 0.2444' and failed at error severity (c3 ch-p10c s4.7)."""
    rc = receive(CHEM, answer, TONNE_Q)
    assert held(rc) and not failed(rc) and not errors(rc), messages(rc)


def test_a_wrong_conversion_to_tonnes_is_named():
    assert named(receive(CHEM, "m(CO₂) = 2.444 × 10⁵ g = 2.444 t per day", TONNE_Q), "INT-SUBJ-001")


def test_a_stated_mass_in_tonnes_is_read_in_physics_when_the_request_states_it():
    q = "A lorry has a mass of 12 t. Calculate its weight (g = 9.8 N kg⁻¹)."
    rc = receive(PHYS, "W = mg = 12 t × 9.8 N kg⁻¹ = 1.2 × 10⁵ N", q)
    assert held(rc) and not errors(rc), messages(rc)
    assert named(receive(PHYS, "W = mg = 12 t × 9.8 N kg⁻¹ = 1.2 × 10⁴ N", q), "INT-SUBJ-001")


def test_a_bare_value_before_a_letter_that_may_be_its_unit_is_withheld():
    """Rule unread-unit-letter (P4): where the tonne is not read (the text writes a symbol t), a stated value followed by 't' is never
    compared as a bare number: the relation is withheld (ST-PARSE-001), never a false error."""
    rc = receive(CHEM, "The rise Δt is small.\nm = 2.444 × 10⁵ g = 0.2444 t per bus per day", "Give the mass.")
    assert not errors(rc) and named(rc, "ST-PARSE-001", "may be its unit"), messages(rc)


def test_a_bare_letter_t_after_a_number_with_no_mass_stays_a_letter():
    """The tonne is read from a number and 't' alone only when the text names a mass that way: 'We get v = 3 t then' reads 'v = 3'."""
    doc = build_document("We get v = 3 t then", "A spring is extended by 4.0 cm.", PHYS)
    assert [doc.text[i.start:i.end] for i in doc.items][:1] == ["v = 3"]


PM_Q = "Each burette reading has an uncertainty of ±0.05 cm³. Calculate the uncertainty in a titre."


@pytest.mark.parametrize("answer", ["Uncertainty in one titre = 0.05 cm³ + 0.05 cm³ = ±0.10 cm³", "Uncertainty in one titre = 0.05 cm³ + 0.05 cm³ = 0.10 cm³",
                                    "±0.05 cm³ + ±0.05 cm³ = ±0.10 cm³", "Uncertainty = 0.05 + 0.05 = ±0.10"])
def test_an_uncertainty_written_with_plus_or_minus_on_its_size_holds(answer):
    """Rule stated-margin: '= ±0.10 cm³' on the stated side alone states a margin of size 0.10; it had been read as two roots that must both
    equal the computed 0.10 (c3 ch-t16 s6.1, INT-SUBJ-001 on correct work)."""
    rc = receive(CHEM, answer, PM_Q)
    assert held(rc) and not failed(rc) and not errors(rc), messages(rc)


def test_a_wrong_uncertainty_size_is_named():
    assert named(receive(CHEM, "Uncertainty in one titre = 0.05 cm³ + 0.05 cm³ = ±0.20 cm³", PM_Q), "INT-SUBJ-001")


def test_roots_written_with_plus_or_minus_keep_both_branches():
    rc = receive(AA, "x² = 4, so x = ±2", "Solve x² = 4.")
    assert held(rc) and not errors(rc), messages(rc)


EVAL_Q = "Let f(x) = x³ − 3x. Find f′(x), evaluate f(2), and find f″(x)."


@pytest.mark.parametrize("answer", ["f′(x) = 3x² − 3\nf(2) = 8 − 6 = 2\nf″(x) = 6x", "f′(x) = 3x² − 3\nf(2) = 2³ − 3(2) = 2\nf″(x) = 6x",
                                    "f(x) = x³ − 3x\nf(2) = 8 − 6 = 2\nf′(x) = 3x² − 3\nf″(x) = 6x"])
def test_an_evaluation_line_is_never_the_definition_of_the_function(answer):
    """Rule evaluation-head: 'f(2) = 8 − 6' evaluates f; it had been recorded as f's definition, so the power rule differentiated a constant
    and the correct f″ failed (c3 maa-t16 m3.6/m3.4 and m3.11/m3.4)."""
    rc = receive(AA, answer, EVAL_Q)
    assert held(rc) and not failed(rc) and not errors(rc), messages(rc)


def test_a_wrong_derivative_after_an_evaluation_is_still_named():
    assert named(receive(AA, "f′(x) = 3x² − 3\nf(2) = 8 − 6 = 2\nf″(x) = 6x + 1", EVAL_Q), "INT-SUBJ-001")


LINE_Q = "(a) Factorise x² − 5x + 6. (b) Find the equation of the line through (1, 2) with gradient 3."


@pytest.mark.parametrize("answer", ["(a) x² − 5x + 6 = (x − 2)(x − 3)\n\n(b) y − 2 = 3(x − 1)\ny = 3x − 1",
                                    "(a) x² − 5x + 6 = (x − 2)(x − 3)\n\n(b) y − 16 = (1/12)(x − 1)\n12y − 192 = x − 1"])
def test_the_equation_of_a_line_is_no_identity_whatever_another_part_asks(answer):
    """Rules part-condition for identity words and two-variable-equation: 'hence factorise' in part (a) names no identity of part (b), and an
    equation with a letter on each side the other side lacks is a line's, read as a step to its rearrangement (c3 maa-t16 m6.5, m6.6)."""
    rc = receive(AA, answer, LINE_Q)
    assert not errors(rc) and not failed(rc), messages(rc)


@pytest.mark.parametrize("answer,quote", [("(a) x² − 5x + 6 = (x − 2)(x − 4)\n\n(b) y − 2 = 3(x − 1)\ny = 3x − 1", "(x − 4)"),
                                          ("(a) x² − 5x + 6 = (x − 2)(x − 3)\n\n(b) y − 2 = 3(x − 1)\ny = 3x − 2", "3x − 2")])
def test_a_wrong_factorisation_or_rearrangement_is_still_named(answer, quote):
    assert fault_named(receive(AA, answer, LINE_Q), quote)


AI_Q = ("A = 2πr² + 660/r. (e) Justify that this value of r gives a minimum. [2]")


@pytest.mark.parametrize("answer", [
    "Also, $\\dfrac{dA}{dr} \\approx -35.6$ at $r = 3$ and $\\approx 9.0$ at $r = 4$, so the gradient changes from negative to positive.",
    "Also, at $r = 3$ the gradient is about −35.6 and at $r = 4$ it is about 9.0, so the gradient changes sign.",
    "Also, dA/dr ≈ −35.6 at r = 3 and dA/dr ≈ 9.0 at r = 4, so the gradient changes from negative to positive.",
])
def test_evaluation_points_are_no_stated_roots(answer):
    """Rules evaluation-point (wherever it stands) and inline-delimiters: 'at r = 3' after a value, or opening a clause, states where
    something is evaluated; and '$r = 3$ and $\\approx 9.0$' joins no relation across the delimiters (c3 mai-t16 m21.1/m21.2: the two points
    were read as the roots of the equation on the line before, INT-SUBJ-001 on correct work)."""
    text = "As a check, at the stationary point $\\dfrac{1320}{r^3} = 8\\pi$.\n" + answer
    rc = receive(AI, text, AI_Q)
    assert not errors(rc) and not failed(rc), messages(rc)


def test_stated_roots_are_still_checked():
    assert named(receive(AA, "x² − 5x + 6 = 0\nx = 2 or x = 4", "Solve x² − 5x + 6 = 0."), "INT-SUBJ-001")


# ============================================================================== injected faults that crossed unnamed

BOX_Q = ("An open box has a square base of side x cm and height h cm, and holds 500 cm³. (a) Show that h = 500/x². [1] "
         "(b) Show that the surface area S cm² of the open box is S = x² + 2000/x. [2]")


def test_a_correct_show_that_derivation_holds():
    rc = receive(AI, "(a) x²h = 500, so h = 500/x²\n\n(b) S = x² + 4xh\n= x² + 4x × 500/x²\n= x² + 2000/x", BOX_Q)
    assert held(rc) and not failed(rc) and not errors(rc), messages(rc)


@pytest.mark.parametrize("answer,quote", [
    ("(a) x²h = 500, so h = 500/x²\n\n(b) S = x² + 2xh\n= x² + 4x × 500/x²\n= x² + 2000/x", "2xh"),
    ("(a) x²h = 500, so h = 500/x²\n\n(b) S = x² + 4xh\n= x² + 2x × 500/x²\n= x² + 2000/x", "2x × 500"),
])
def test_a_wrong_line_before_the_show_that_target_is_named(answer, quote):
    """Rule show-that-target: the request's 'Show that … S = x² + 2000/x' is what part (b) must establish, never a premise of its steps; with
    it as a premise both sides of a wrong first step equalled S and the step was ENTAILED (the c3 mai-t16 stem_substitution miss)."""
    rc = receive(AI, answer, BOX_Q)
    assert named(rc, "INT-SUBJ-001") and any(quote in f.message for f in findings(rc) if f.code == "INT-SUBJ-001"), messages(rc)


def test_the_target_of_another_part_is_still_a_result_the_answer_may_use():
    doc = build_document("(b) S = x² + 4xh\n= x² + 4x × 500/x²\n= x² + 2000/x", BOX_Q, AI)
    targets = {f.name: f.target for fl in doc.formulas.values() for f in fl if f.source == "request"}
    assert targets.get("h") == "(a)" and targets.get("S") == "(b)", targets


def test_the_mai_t16_surface_area_mutation_is_named():
    """The harness's c3 mai-t16 stem_substitution ('A = 2πr⁵ + 2πrh') passed the step with the request's target as a premise."""
    rc = mutated("mai-t16", "$A = 2\\pi r^2 + 2\\pi r h$ (M1)", "$A = 2\\pi r^5 + 2\\pi r h$ (M1)")
    assert named(rc, "INT-SUBJ-001"), messages(rc)


def test_a_wrong_mole_ratio_written_as_a_ratio_of_species_is_named():
    """'Ratio C₁₂H₂₆ : CO₂ = 1 : 24' after an equation giving 1 : 12 is read as a stated mole ratio (rule mole-ratio): a warning."""
    rc = mutated("ch-p10c", "Ratio C₁₂H₂₆ : CO₂ = 1 : 12, so n(CO₂) = 12 × 462.79 mol = 5553.5 mol",
                 "Ratio C₁₂H₂₆ : CO₂ = 1 : 24, so n(CO₂) = 24 × 462.79 mol = 11107 mol")
    assert named(rc, "INT-SUBJ-004"), messages(rc)


@pytest.mark.parametrize("profile,request_text,answer,ok", [
    (PHYS, "A 2.0 kg mass moves at 3.0 m s⁻¹. Calculate its kinetic energy.", "E_k = ½mv² = 0.5 × 2.0 × 3.0² = 9.0 kJ", False),
    (PHYS, "A 2.0 kg mass moves at 3.0 m s⁻¹. Calculate its kinetic energy.", "E_k = ½mv² = 0.5 × 2.0 × 3.0² = 9.0 J", True),
    (PHYS, "Calculate the weight of a 2.0 kg mass on Earth.", "W = mg = 2.0 × 9.8 = 19.6 kN", False),
    (PHYS, "A wave has frequency 50 Hz and speed 340 m s⁻¹. Calculate its wavelength.", "λ = v/f = 340/50 = 6.8 mm", False),
    (PHYS, "A wave has frequency 50 Hz and speed 340 m s⁻¹. Calculate its wavelength.", "λ = v/f = 340/50 = 6.8 m", True),
])
def test_a_prefixed_unit_on_working_in_si_numerals_is_named(profile, request_text, answer, ok):
    """Rule si-prefix: every numeral of the working repeats an SI quantity, so the result is in the SI unit; a prefix on the stated value is
    set against it by the unit companion (ST-UNIT-003, a warning). Before, the as-written reading took the prefix as a label."""
    rc = receive(profile, answer, request_text)
    if ok:
        assert not errors(rc) and not failed(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-004", "ST-UNIT-003"), messages(rc)


@pytest.mark.parametrize("answer", ["\\begin{align} x &= 2 + 2 \\\\ &= 5 \\end{align}", "\\begin{align*} x &= 2 + 2 \\\\ &= 5 \\end{align*}",
                                    "$$\\begin{aligned} x &= 2 + 2 \\\\ &= 5 \\end{aligned}$$", "\\begin{eqnarray} x &=& 2 + 2 \\\\ &=& 5 \\end{eqnarray}"])
def test_an_alignment_environment_on_one_line_is_checked(answer):
    """Rule environment-rows: the rows of an environment written on one line are a chain as on separate lines (the second row had been
    read as a labelled line and dropped); eqnarray's '&=&' reads its second mark as layout."""
    assert named(receive(AA, answer, "Calculate the value and show your working."), "INT-SUBJ-001")


def test_a_correct_alignment_environment_holds():
    rc = receive(AA, "\\begin{align} x &= 2 + 2 \\\\ &= 4 \\end{align}", "Calculate the value and show your working.")
    assert held(rc) and not errors(rc), messages(rc)


@pytest.mark.parametrize("answer", ["\\begin{align} x &= 2 + 2 \\\\ &= 5 \\end{alig}", "\\begin{align} x &= 2 + 2 \\\\ &= 5"])
def test_a_relation_in_an_environment_no_span_reads_is_named(answer):
    rc = receive(AA, answer, "Calculate the value and show your working.")
    assert named(rc, "ST-PARSE-001") and not errors(rc), messages(rc)


def _table(n: int, bad: set[int]) -> str:
    return "| n | working |\n|---|---|\n" + "\n".join(f"| {i} | {i} + 1 = {i + 1 if i not in bad else i + 2} |" for i in range(1, n + 1))


def test_working_cells_of_a_long_table_are_read_up_to_the_check_budget():
    """The table's cells of working are read up to the report's check budget (they were cut at 96 cells, so a slip in row 50 or 99 of a
    100-row table crossed with no check)."""
    for bad in (50, 99):
        rc = receive(CS, _table(100, {bad}), "Calculate the value and show your working.")
        assert named(rc, "INT-SUBJ-001"), (bad, messages(rc))
    assert not errors(receive(CS, _table(100, set()), "Calculate the value and show your working."))


def test_working_cells_beyond_the_bound_are_named():
    rc = receive(CS, _table(200, {150}), "Calculate the value and show your working.")
    assert named(rc, "ST-LIM-002", "cells of working in a table beyond the bound"), messages(rc)


@pytest.mark.parametrize("old,new,quote,code", [
    ("(456 of 600, or 76%)", "(456 of 600, or 67%)", "67", "INT-SUBJ-001"),                           # rule share-or (cs-p10a)
])
def test_a_share_the_prose_states_is_named(old, new, quote, code):
    rc = mutated("cs-p10a", old, new)
    assert named(rc, code) and any(quote in f.message for f in findings(rc) if f.code == code), messages(rc)


@pytest.mark.parametrize("old,new,quote", [
    ("a fall of 4.5 t ha⁻¹ yr⁻¹, or 75%", "a fall of 4.5 t ha⁻¹ yr⁻¹, or 70%", "70%"),                 # rule change-share
    ("net sink of about 0.3 t CO₂", "net sink of about 0.5 t CO₂", "0.5"),                            # rule net-difference
])
def test_a_change_or_a_net_value_the_prose_states_is_named(old, new, quote):
    """Rules change-share and net-difference (ess-t16): which values the change is between is a reading, so the failure is a warning."""
    rc = mutated("ess-t16", old, new)
    assert any(f.code == "INT-SUBJ-004" and quote in f.message for f in findings(rc)), messages(rc)


def test_a_share_with_a_plural_verb_is_checked():
    ok = receive(ESS, "The drained 610 ha are about 73% of the bog's 840 ha.", "Calculate.")
    bad = receive(ESS, "The drained 610 ha are about 80% of the bog's 840 ha.", "Calculate.")
    assert held(ok) and not errors(ok), messages(ok)
    assert named(bad, "INT-SUBJ-001"), messages(bad)


@pytest.mark.parametrize("old,new", [("so 54% of dividing cells are at metaphase", "so 45% of dividing cells are at metaphase"),
                                     ("against 16% in the control", "against 26% in the control")])
def test_a_derived_share_whose_operands_are_not_found_is_named_undecided(old, new):
    """Rule derived-share: 'so 54% of dividing cells …, against 16% in the control' is formed from counts the sentence does not state: it is
    named ST-UNDEC-001 (it had been read by nothing), never an error."""
    rc = mutated("bi-t16", old, new)
    assert named(rc, "ST-UNDEC-001", "the prose derives") and not stem_errors(rc), messages(rc)


def test_a_wrong_kelvin_conversion_in_a_bracket_is_named():
    """Rule whole-sum: '17 + 273 = 300 K' adds whole numbers, so 300 states every digit (its zero had been read as a rounding place)."""
    rc = mutated("ph-t16", "(17 + 273 = 290 K)", "(17 + 273 = 300 K)")
    assert named(rc, "INT-SUBJ-001") and not failed(recorded("ph-t16")), messages(rc)


def test_a_wrong_mean_with_its_unit_after_the_bracket_is_named():
    """A unit after a bracket bounds its rounding (rule operand-precision): '= 22.50 cm³' for a mean of 22.40 had passed with τ = 1/100."""
    rc = mutated("ch-t16", "÷ 3 = 22.40 cm³  [1]", "÷ 3 = 22.50 cm³  [1]")
    assert named(rc, "INT-SUBJ-001"), messages(rc)


@pytest.mark.parametrize("answer,ok", [
    ("$\\dfrac{d}{dr}\\left(2\\pi r^2\\right) = 4\\pi r$", True), ("$\\dfrac{d}{dr}\\left(2\\pi r^2\\right) = 2\\pi r$", False),
    ("$\\dfrac{d}{dr}\\left(660r^{-1}\\right) = -660r^{-2}$", True), ("$\\dfrac{d}{dr}\\left(660r^{-1}\\right) = -960r^{-2}$", False),
    ("d/dr(660r⁻¹) = −660r⁻²", True), ("d/dr(660r⁻¹) = 660r⁻²", False),
])
def test_derivatives_with_pi_and_negative_powers_are_checked(answer, ok):
    """Rule derivative, Laurent terms: π in a coefficient and negative powers of the variable are differentiated term by term (they had been
    ST-UNDEC-001 'a derivative' whatever their value: the c3 mai-t16 stem_arithmetic_slip miss)."""
    rc = receive(AI, answer, "A = 2πr² + 660/r. Find dA/dr.")
    if ok:
        assert held(rc) and not failed(rc) and not errors(rc), messages(rc)
    else:
        assert named(rc, "INT-SUBJ-001"), messages(rc)


def test_a_derivative_of_the_request_s_function_is_checked_at_warning_severity():
    q = "(b) Show that the total surface area of a can, A cm², is given by A = 2πr² + 660/r. [2] (c) Find dA/dr. [2]"
    ok = receive(AI, "(c) $\\dfrac{dA}{dr} = 4\\pi r - \\dfrac{660}{r^2}$", q)
    bad = receive(AI, "(c) $\\dfrac{dA}{dr} = 4\\pi r + \\dfrac{660}{r^2}$", q)
    assert held(ok) and not failed(ok), messages(ok)
    assert named(bad, "INT-SUBJ-004") and not stem_errors(bad), messages(bad)


def test_k_b_t_is_read_as_a_product():
    """Rule subscript-product: 'k_BT' (k_B × T) with T bound; the misremembered k_B and the Celsius temperature are named (ph-F5, ph-F6), the
    correct answer holds with no undecided warning on 'k_BT' or 'N_A' (rule booklet-dimension)."""
    rc = recorded("ph-t16")
    assert not named(rc, "ST-UNDEC-002"), messages(rc)
    assert named(mutated("ph-t16", "× 308 = 6.4 × 10⁻²¹ J ✔", "× 35 = 7.2 × 10⁻²² J ✔"), "INT-SUBJ-001")


def test_abbreviations_bound_to_their_numbers_check_the_substitution():
    """Rule abbreviation: 'true positives (TP) 132, false positives (FP) 18' bind TP and FP, so 'Precision = TP ÷ (TP + FP) = 132 ÷ (132 +
    12)' (FN put in for FP) is named; '(TP + TN)' is arithmetic, no Boolean derivation."""
    rc = recorded("cs-p10a")
    assert not named(rc, "ST-UNDEC-002") and not named(rc, "ST-UNDEC-001", "Boolean derivation"), messages(rc)
    bad = mutated("cs-p10a", "= 132 ÷ (132 + 18)\n= 132 ÷ 150\n= 22/25 = 0.880 (3 s.f.)", "= 132 ÷ (132 + 12)\n= 132 ÷ 144\n= 11/12 = 0.917 (3 s.f.)")
    assert named(bad, "INT-SUBJ-001"), messages(bad)


@pytest.mark.parametrize("answer", ["F = 2.0 х 3.0 = 6.0 N", "F = 2.0 х 3.0 = 7.0 N"])
def test_a_letter_of_another_script_between_numerals_is_withheld(answer):
    """The Cyrillic х between two numerals is a sign outside the grammar there (as the Latin x is): the relation is named ST-PARSE-001; it
    had ended the run and '3.0 = 6.0 N' failed as an error on correct work."""
    rc = receive(PHYS, answer, "Calculate the value and show your working.")
    assert named(rc, "ST-PARSE-001") and not errors(rc), messages(rc)


@pytest.mark.parametrize("answer,inside", [("a = 20/4\x00 = 6 m s⁻²", True), ("x = 1\x00 + 2 = 3", True), ("a = 20/4 = 5 m s⁻²\x1b[2J", False)])
def test_a_control_character_is_a_blank_and_is_named(answer, inside):
    """Rule control-character: a C0 control is read as a blank and its statement named (ST-PARSE-001). A relation it stands inside is
    withheld and named at its check (ST-PARSE-001, never decided: correct input it splits is never failed, the existing safety pin of
    test_checks_safety); a NUL had dropped it with nothing named. A control outside every relation leaves the relation decided. The channel
    may refuse such a response first (INT-REQ-009)."""
    clear_document_cache()
    doc = build_document(answer, "Calculate the acceleration.", PHYS)
    cp = build_checks(doc, report_id="r", request_id="q")
    assert any(f.code == "ST-PARSE-001" and "control character" in f.message for f in doc.findings), doc.findings
    withheld = [f for f in cp.findings if f.code == "ST-PARSE-001" and "rule control-character" in f.message]
    if inside:
        assert withheld and not cp.checks, (cp.findings, cp.checks)
    else:
        assert cp.checks and not withheld, (cp.findings, cp.checks)


# ============================================================================== the word-count view (rule working-view)

def test_the_word_count_view_keeps_working_and_drops_marks_and_labels():
    """The view had turned each line of working into one word with no relation sign, so the 'plus working' exemption no longer found it, and
    counted every '[1]' and part label: ess-t16 was measured 488 words. The view keeps the sign ('Xmath=') and blanks the annotations and
    labels; without its assumption line (a note the channel's note reader is to leave out) the answer is within its 450 words.

    Rewritten in round 10's handoff pass to the channel's new rule (c3 critical record 3, parsers handoff H4: a 'plus working' bound
    leaves out all of the working, and the result line of a calculated part, "Answer: 3,660 t ...", is working when its paragraph
    holds working). The exempt words are still pinned exactly, now as the four lines of working and the two result lines, and the
    result lines are named (stricter than a count alone)."""
    a = ROUND10["ess-t16"]["response_text"]
    view = lambda t: StemHooks().word_count_view(t, ESS)  # noqa: E731
    answer, _notes, exempt = measure_answer_words(a, excludes=("working",), view=view)
    # each of the four lines of working keeps its sign in the view; exactly their words and those of the two result lines are set
    # outside the bound
    working = [ln for ln in view(a).splitlines() if "Xmath=" in ln]
    results = [ln for ln in view(a).splitlines() if ln.startswith("Answer:")]
    assert len(working) == 4 and len(results) == 2 and all(any(ch.isdigit() for ch in ln) for ln in results), (working, results)
    assert exempt == sum(count_words(ln) for ln in working + results) > 0 and answer < 470, (answer, exempt, working, results)
    assert measure_answer_words(a, excludes=(), view=view)[0] == answer + exempt
    lean = a.replace("Assumption: SL, Paper 1 practice. The Halden Moss booklet is a fictional practice case, so I use its figures as given and do "
                     "not check them against outside data.\n\n", "")
    assert measure_answer_words(lean, excludes=("working",), view=view)[0] <= 450
    shown = view("(a) Volume = 840 ha × 4.5 m = 3780 ha m [1]\nThe peat is deep. [1]")
    assert "Xmath=" in shown and "[1]" not in shown and "(a)" not in shown, shown


def test_the_variant_without_its_assumption_line_meets_its_bound():
    rc = mutated("ess-t16", "Assumption: SL, Paper 1 practice. The Halden Moss booklet is a fictional practice case, so I use its figures as given "
                 "and do not check them against outside data.\n\n", "")
    assert not named(rc, "INT-REQ-005"), messages(rc)


# ============================================================================== bounds on hostile input

_N = 20_000
STANDARD = {
    "blanks": " " * _N + "x", "tabs": "\t" * _N + "x", "line breaks": "\n" * _N + "x", "stops": "." * _N + "x",
    "closing marks": ")" * (_N // 2) + "]" * (_N // 2) + "x", "mark labels": "x = 5" + " (A1)" * (_N // 5) + " z",
    "parentheses": "(" * _N + "x", "brackets": "[" * _N + "x", "fence openers": "```\n" * (_N // 4) + "x",
    "number words": "one and " * (_N // 8) + "x", "= links": "x = " * (_N // 4) + "!", "list markers": "- " * (_N // 2) + "!",
}
NEW_SHAPES = {
    "tonnes": "m = 2.444 × 10⁵ g = 0.2444 t per bus " * (_N // 38) + "in tonnes",
    "lone t": "12 t " * (_N // 5) + "x",
    "plus-or-minus": "0.05 + 0.05 = ±0.10 " * (_N // 20) + "x",
    "evaluations": "f(x) = x³\n" + "f(2) = 8 − 6 = 2\n" * (_N // 17) + "f″(x) = 6x",
    "at points": "dA/dr ≈ −35.6 at r = 3 and ≈ 9.0 at r = 4, " * (_N // 44) + "so",
    "inline delimiters": "$r = 3$ and $\\approx 9.0$ at " * (_N // 30) + "$r = 4$",
    "show that": "Show that S = x² + 2000/x. " * (_N // 27) + "x",
    "ratios": "N₂ + 3H₂ → 2NH₃\n" + "Ratio N₂ : NH₃ = 1 : 2, " * (_N // 25) + "!",
    "environments": "\\begin{align} x &= 2 + 2 \\\\ &= 4 \\end{align} " * (_N // 47) + "x",
    "row separators": "x &= 2 " + "\\\\ &= 2 " * (_N // 9) + "x",
    "shares": "(456 of 600, or 76%) " * (_N // 21) + "x",
    "changes": "1.5 t, against 6.0 t: a fall of 4.5 t, or 75%. " * (_N // 47) + "x",
    "net values": "removes 0.9 t but releases 0.6 t, so a net sink of about 0.3 t. " * (_N // 62) + "x",
    "derived shares": "so 54% of dividing cells, against 16% in the control. " * (_N // 54) + "x",
    "whole sums": "17 + 273 = 300 K, " * (_N // 18) + "x",
    "laurent": "d/dr(660r⁻¹) = −660r⁻² " * (_N // 23) + "x",
    "subscript products": "k_BT " * (_N // 5) + "= 1",
    "abbreviations": "true positives (TP) 132, " * (_N // 25) + "x",
    "possessives": "the bog's 840 ha " * (_N // 17) + "x",
    "cyrillic times": "2.0 х 3.0 = 6.0 " * (_N // 16) + "x",
    "controls": "a = 20/4\x00 = 5 " * (_N // 15) + "x",
    "table rows": "| n | working |\n|---|---|\n" + "| 1 | 1 + 1 = 2 |\n" * (_N // 17),
    "apostrophes": "x'" * (_N // 2) + "s",
}


@pytest.mark.parametrize("name", sorted(STANDARD) + sorted(NEW_SHAPES))
@pytest.mark.parametrize("profile", [PHYS, AA, CHEM, CS])
def test_the_new_readings_are_bounded_on_hostile_input(name, profile):
    """Every public entry point of the touched modules, through the whole document and its checks, on each standard hostile input of about
    20,000 characters and on the shapes of this round's readings: far inside the bound (8 CPU seconds per input and profile)."""
    text = STANDARD.get(name) or NEW_SHAPES[name]
    clear_document_cache()
    t0 = time.process_time()
    doc = build_document(text, "(a) Show that S = x² + 2000/x. [2] (b) State the mass in tonnes. Ratio N₂ : NH₃.", profile)
    build_checks(doc, report_id="r", request_id="q")
    assert time.process_time() - t0 < 8.0, name


@pytest.mark.parametrize("name", sorted(STANDARD) + sorted(NEW_SHAPES))
def test_the_new_entry_points_are_linear(name):
    """The new readers' own entry points, module by module, on each hostile input: units.tonne_stated (three scans), scope.prescan_names and
    defined_abbreviations (one scan, capped), normalize.reading_view (one pass), lexer.lex (the possessive and the letter-between-numerals
    rules look a few characters each way), spans.find_spans (through build_document), hub_hooks.word_count_view (one pass over the lines),
    calculus.laurent (bounded depth and terms), and the anchored or bounded patterns of relations and checks."""
    text = STANDARD.get(name) or NEW_SHAPES[name]
    t0 = time.process_time()
    stem_units.tonne_stated(text, text)
    stem_scope.prescan_names(text)
    stem_scope.defined_abbreviations(text)
    stem_normalize.reading_view(text)
    stem_lexer.lex(text, 0, min(len(text), 4000), mode="plain")
    StemHooks().word_count_view(text, PHYS)
    stem_hooks._without_labels_and_marks(text)
    for pattern in (stem_relations._MOLE_RATIO_RE, stem_relations._SHARE_OR_RE, stem_relations._NET_OF_RE, stem_relations._CHANGE_OF_RE,
                    stem_relations._DERIVED_SHARE_BEFORE_RE, stem_relations._TIMES_THE_RE, stem_relations._EVAL_AT_RE,
                    stem_relations._VALUE_BEFORE_AT_RE, stem_relations._CLAUSE_BEFORE_AT_RE, stem_relations._AGAINST_TAIL_RE,
                    stem_checks._UNIT_LETTER_AFTER_RE, stem_units._TONNE_WORD_RE, stem_units._MASS_T_RE):
        for _m in pattern.finditer(text):
            pass
    for k in range(0, min(len(text), 4000), 97):
        stem_relations._row_start(text, k)
    assert time.process_time() - t0 < 4.0, name


def test_the_laurent_reader_is_bounded():
    """calculus.laurent reads at most a bounded depth and number of terms: a deeply nested or long sum is refused (None), never a stall."""
    from epinoic_logic.stem.nodes import BinOp, Num, Pow, Sym
    from epinoic_logic.stem.numbers import exact_integer
    node = Sym("r", "symbol")
    for k in range(2000):
        node = BinOp("+", node, Pow(Sym("r", "symbol"), -((k % 12) + 1)), 0, 0)
    t0 = time.process_time()
    assert stem_calculus.laurent(node, "r") is None
    deep = Num(exact_integer(1))
    for _ in range(5000):
        deep = BinOp("*", deep, Sym("r", "symbol"), 0, 0)
    assert stem_calculus.laurent(deep, "r") is None
    assert time.process_time() - t0 < 2.0


def test_the_document_entry_point_reads_spans_once():
    """spans.find_spans and document.build_document on the environments and possessives shapes: the display rows and the quantity runs are
    read once each (the time bound above), and the row-start rule reads at most 160 characters back."""
    text = NEW_SHAPES["environments"] + NEW_SHAPES["possessives"]
    clear_document_cache()
    t0 = time.process_time()
    doc = build_document(text, "Calculate.", AA)
    assert doc.spans.spans is not None and stem_spans.DISPLAY_ENVIRONMENTS
    assert stem_document.document_cache_info() is not None
    assert time.process_time() - t0 < 8.0


# ============================================================================== smaller readings

def test_a_misremembered_law_of_gravitation_is_named():
    """'F = GMm/r' stated without working is named against the booklet's F = GMm/r² (ST-REF-002, a warning); the right law is clean."""
    bad = build_document("The force is F = GMm/r, from the data booklet.", "Calculate the gravitational force.", PHYS)
    ok = build_document("The force is F = GMm/r², from the data booklet.", "Calculate the gravitational force.", PHYS)
    assert any(f.code == "ST-REF-002" for f in bad.findings), bad.findings
    assert not any(f.code == "ST-REF-002" for f in ok.findings), ok.findings


def test_a_ratio_of_three_species_is_no_two_species_ratio():
    """The ratio reader takes two species only: 'N₂ : H₂ : NH₃ = 1 : 3 : 2' (round-9 ch-t15) is never read as 'H₂ : NH₃ = 1 : 3'."""
    assert not list(stem_relations._MOLE_RATIO_RE.finditer("the mole ratio, N₂ : H₂ : NH₃ = 1 : 3 : 2."))
    m = stem_relations._MOLE_RATIO_RE.search("Ratio C₁₂H₂₆ : CO₂ = 1 : 12, so")
    assert m is not None and (m.group("a"), m.group("b"), m.group("x"), m.group("y")) == ("C₁₂H₂₆", "CO₂", "1", "12")


def test_a_per_cent_that_restates_its_line_is_no_derived_share():
    """'… × 100 = 0.5% [1] So 0.5% of the solar radiation …' restates the result its own line checks: no ST-UNDEC-001."""
    doc = build_document("Efficiency = 50 ÷ 10000 × 100 = 0.5% [1]\nSo 0.5% of the solar radiation reaching the vegetation is stored.",
                         "Calculate the efficiency.", ESS)
    assert not any(f.code == "ST-UNDEC-001" and "prose derives" in f.message for f in doc.findings), doc.findings


def test_a_species_between_unit_atoms_labels_the_quantity():
    """Rule species-label, between unit atoms: '610 ha × 6.0 t CO₂ ha⁻¹ yr⁻¹ = 3,660 t CO₂ yr⁻¹' (ess-t16 s3.1) is checked and holds; it had
    been ST-PARSE-001 'outside the grammar', so the slip '3,960' crossed undecided."""
    rc = recorded("ess-t16")
    assert not named(rc, "ST-PARSE-001", "610 ha × 6.0 t CO₂"), messages(rc)
    bad = mutated("ess-t16", "= 3,660 t CO₂ yr⁻¹ [1]", "= 3,960 t CO₂ yr⁻¹ [1]")
    assert named(bad, "INT-SUBJ-001", "3,960"), messages(bad)


def test_the_totals_of_a_table_are_checked():
    """Rule table-totals: a table with a total column and a total row states its totals ('| Actually aluminium | 132 (TP) | 12 (FN) | 144 |',
    '| Total | 150 | 450 | 600 |'): each is set against the counts it sums (a warning, a reading), and a wrong total is named (csa-table)."""
    rc = recorded("cs-p10a")
    assert len(held(rc)) >= 26 and not failed(rc), messages(rc)
    bad = mutated("cs-p10a", "| Total | 150 | 450 | 600 |", "| Total | 150 | 460 | 600 |")
    assert any(f.code == "INT-SUBJ-004" for f in findings(bad)) and not stem_errors(bad), messages(bad)


@pytest.mark.parametrize("stated,ok", [("6.4 × 10⁻²¹ kJ", False), ("6.4 × 10⁻²⁴ kJ", True), ("6.4 × 10⁻²¹ J", True)])
def test_a_prefixed_unit_on_a_product_law_with_a_coefficient_is_named(stated, ok):
    """Rule si-prefix, the c3 ph-t16 shape: '(3/2)k_BT = 1.5 × 1.38 × 10⁻²³ × 308 = 6.4 × 10⁻²¹ kJ'. align() pairs nothing there (the
    coefficient 3/2 faces the numeral 1.5), so the working's numerals were never read and the kJ crossed as a label; the law's factors are
    paired in order for the unit companion, k_B and T in J K⁻¹ and K, and the wrong prefix is named (ST-UNIT-003, a warning). The right
    value in kJ and the recorded value in J hold."""
    rc = mutated("ph-t16", "× 308 = 6.4 × 10⁻²¹ J ✔", f"× 308 = {stated} ✔")
    assert not stem_errors(rc), messages(rc)
    if ok:
        assert not failed(rc), messages(rc)
    else:
        assert fault_named(rc, "6.4 × 10⁻²¹ kJ") and named(rc, "INT-SUBJ-004", "ST-UNIT-003"), messages(rc)


def test_the_factor_pairs_of_a_product_law_are_exact_and_bounded():
    """_factor_pairs pairs symbols with numerals and coefficients with numerals of their value only; a coefficient that differs, a factor
    that is no numeral, or a product longer than its bound pairs nothing."""
    from epinoic_logic.stem.nodes import BinOp, Num, Sym
    from epinoic_logic.stem.numbers import scan_number

    def num(text: str) -> Num:
        return Num(scan_number(text, 0).number, 0, len(text))

    law = BinOp("*", BinOp("/", num("3"), num("2")), BinOp("*", Sym("k_B"), Sym("T")))
    work = BinOp("*", BinOp("*", num("1.5"), num("2.0")), num("308"))
    pairs, coefficients = stem_relations._factor_pairs(law, work)
    assert [n for n, _w in pairs] == ["k_B", "T"] and len(coefficients) == 1
    wrong = BinOp("*", BinOp("*", num("1.4"), num("2.0")), num("308"))
    assert stem_relations._factor_pairs(law, wrong) == ([], set())
    long_law, long_work = Sym("a0"), num("1")
    for k in range(1, 40):
        long_law, long_work = BinOp("*", long_law, Sym(f"a{k}")), BinOp("*", long_work, num("1"))
    assert stem_relations._factor_pairs(long_law, long_work) == ([], set())


@pytest.mark.parametrize("total,ok", [("that is about 2,745 t CO₂ a year less", True), ("that is about 2,800 t CO₂ a year less", True),
                                      ("that is about 2,475 t CO₂ a year less", False), ("that is 2,795 t CO₂ a year less", False),
                                      ("that is 2,700 t CO₂ a year less", True)])
def test_a_total_over_a_stated_extent_and_rate_is_checked(total, ok):
    """Rule rate-total (ess-t16): 'a fall of 4.5 t ha⁻¹ yr⁻¹, or 75%. Across the 610 ha drained, that is about 2,745 t CO₂ a year less': the
    total against 610 × 4.5, the extent times the rate before it whose unit is per hectare, within the approximation band when the prose
    says about ('2,700' holds as 2,745 to the operands' two significant figures). A wrong total is named at warning severity (which rate the
    total is of is a reading); before, nothing read it (es-F5)."""
    rc = recorded("ess-t16") if total.startswith("that is about 2,745") else mutated("ess-t16", "that is about 2,745 t CO₂ a year less", total)
    assert not stem_errors(rc), messages(rc)
    checks = [c for c in rc.formal_checks if "rule rate-total" in (c.detail or "")]
    assert len(checks) == 1, [c.detail for c in rc.formal_checks]
    assert checks[0].satisfied is ok, checks[0].detail
    if not ok:
        assert any(f.code == "INT-SUBJ-004" and "rate-total" in f.message for f in findings(rc)), messages(rc)


def test_a_total_needs_a_rate_per_its_extent():
    """Rule rate-total reads a total only after a rate whose unit is per the extent's unit: a rate per another unit, or none, plans nothing."""
    none = build_document("Across the 610 ha drained, that is about 2,745 t CO₂ a year less.", "Evaluate the strategy.", ESS)
    other = build_document("The rate is 4.5 t km⁻² yr⁻¹. Across the 610 ha drained, that is about 2,745 t CO₂ a year less.", "Evaluate.", ESS)
    for doc in (none, other):
        assert not any("rule rate-total" in (r.reason or "") for r in doc.relations), [r.reason for r in doc.relations]


def test_the_rate_total_reading_is_bounded():
    """Thousands of extents and totals with a rate before each are read in linear time (a bisection finds each rate)."""
    text = "The fall is 4.5 t ha⁻¹ yr⁻¹. " + "Across the 610 ha drained, that is about 2,745 t CO₂ a year less. " * 1500
    clear_document_cache()
    start = time.process_time()
    build_document(text, "Evaluate the strategy.", ESS)
    assert time.process_time() - start < 60


@pytest.mark.parametrize("stated,ok", [("3.2 × 10⁵ J", False), ("3.2 × 10⁵ Pa", True)])
def test_a_unit_of_another_dimension_on_si_working_is_named(stated, ok):
    """Rule si-dimension (the ph-unit variant of c3 ph-t16): 'P2 = P1 × T2/T1 = 3.0 × 10⁵ × 308/290 = 3.2 × 10⁵ J', the request's 3.0 × 10⁵
    Pa and the answer's 308 K and 290 K: read in those units the working gives a pressure, and the stated joule is of another dimension
    (ST-DIM-001, a warning: the reading is inferred). Before, the reading was taken as incomplete and the joule crossed with no finding."""
    rc = mutated("ph-t16", "= 3.2 × 10⁵ Pa ✔", f"= {stated} ✔")
    assert not stem_errors(rc), messages(rc)
    dim = [f for f in findings(rc) if f.code == "ST-DIM-001" and "rule si-dimension" in f.message]
    if ok:
        assert not dim and not failed(rc), messages(rc)
    else:
        assert dim and all(f.severity == "warning" for f in dim) and "'J'" in dim[0].message, messages(rc)


@pytest.mark.parametrize("answer,ok", [("W = mg = 2.0 × 9.8 = 19.6 J", False), ("W = mg = 2.0 × 9.8 = 19.6 N", True)])
def test_a_weight_stated_in_joules_is_named(answer, ok):
    """Rule si-dimension on a booklet constant: m = 2.0 kg (the request) and g = 9.8 m s⁻² give newtons; a weight stated in joules is named."""
    rc = receive(PHYS, answer, "Calculate the weight of a 2.0 kg mass on Earth.")
    assert not stem_errors(rc), messages(rc)
    assert any(f.code == "ST-DIM-001" for f in findings(rc)) is (not ok), messages(rc)


def test_the_tonne_word_is_read_only_where_the_tonne_is():
    """Rule tonne-reading reads the word 'tonnes' as the tonne where the symbol t is read (the profile's tonne, or the rule's switch) and as
    no unit elsewhere, as before: the translator's figures and the other branches' worked arithmetic ('10.0 − 4.0 = 6.0 million tonnes per
    year', whose scale word governs the line) are unchanged by it."""
    assert stem_units.stem_parse_unit("tonnes", tonne=True).known and stem_units.stem_parse_unit("tonnes per day", tonne=True).known
    assert stem_units.stem_parse_unit("tonnes", tonne=False) is None and stem_units.parse_unit("tonnes") is None
    assert stem_units.parse_unit("megatonnes") is None and stem_units.stem_parse_unit("megatonnes", tonne=True).known


@pytest.mark.parametrize("request_text,answer", [
    ("A trolley starts from rest; its velocity was 1.5 m s⁻¹ at 1.0 s, 3.0 m s⁻¹ at 2.0 s and 4.5 m s⁻¹ at 3.0 s. Find its velocity at 2.5 s.",
     "The velocity rises by 1.5 m s⁻¹ each second, so v = 1.5t. At t = 2.5 s, v = 1.5 × 2.5 = 3.75 m s⁻¹."),
    ("A spring was loaded with 1.0 N, 2.0 N, 3.0 N and 4.0 N, giving extensions of 2.0 cm, 4.0 cm, 6.0 cm and 8.0 cm. Predict the extension "
     "for a load of 2.5 N.", "The extension rises by 2.0 cm per newton, so x = 2.0F. For F = 2.5 N, x = 2.0 × 2.5 = 5.0 cm."),
    ("A stone is dropped from rest. Take g = 9.8 m s⁻². Calculate the distance fallen in 2.0 s.",
     "Using s = ½gt², s = 4.9t². For t = 2.0 s, s = 4.9 × 2.0² = 19.6 m."),
])
def test_a_fitted_law_s_coefficient_is_never_read_as_a_pure_number(request_text, answer):
    """Rule si-dimension reads only numerals that repeat quantities of known unit: a fitted law's coefficient carries a unit ('v = 1.5t',
    'x = 2.0F', 's = 4.9t²'), so working that multiplies by it is never named ST-DIM-001 (the round-1 repair's clean controls)."""
    rc = receive(PHYS, answer, request_text)
    assert not any(f.code == "ST-DIM-001" for f in findings(rc)) and not stem_errors(rc), messages(rc)
