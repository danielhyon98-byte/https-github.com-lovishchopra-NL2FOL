"""Repair round 2, STEM front end: each fixed class with a positive and a clean control, delivered through the hub as a
specialist's raw answer.

* a substituted rearrangement whose values the task gives ("V = IR, so R = 6.0 / 0.50 = 12 Ω") is a valid step; the wrong
  rearrangement still fails (ADV2-02);
* a law whose head carries a subscript digit (CO₂) is a law, so evaluating it past the data is stem_extrapolation
  (MISS-EXTRAP-SUBSCRIPT); a trend stepped in arithmetic past the data is too (ADV2-08), also when the data series writes
  its unit once ("at 10, 20 and 30 °C");
* a value after a preposition ("in 2000", "at 60 °C") is when the equation after it is evaluated, never an operand of it;
* a comparison made with a rounded value is named in its other natural shapes (ADV2-06);
* a word equation is read as the formula it spells: a wrong one is stem_wrong_formula, a correct one is clean (ADV2-07);
* a time converted inline in brackets binds the law's variable (ADV2-12);
* a comparison only named as a condition is no claim that it holds, while one whose truth value the sentence states is
  checked (FA-IFF-CS-MENTION);
* the per-line work of a long answer is bounded (parser-safety-11): the faster readers give exactly the old readings.
"""
from __future__ import annotations

import random
import re

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.document import _MarkupIndex
from epinoic_logic.stem.layout import emphasis_spans, plain_line
from epinoic_logic.stem.normalize import MASK_FILL, MASK_HEAD, blank_ranges, masked_view
from epinoic_logic.stem.segment import _starts_with_relation

KEY = b"repair-round-2-stem-tests-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
ESS = ("Environmental Systems and Societies", "ess-specialist")
BIO = ("Biology", "biology-specialist")
CS = ("Computer Science", "computer-science-specialist")


def receive(answer: str, request: str, subject: str = "Physics", agent: str = "physics-specialist"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def errors(rc) -> list[str]:
    return [f.code for f in rc.findings if f.severity == "error"]


def defects(rc) -> set[str]:
    return set(re.findall(r'"defect":"([a-z_]+)"', rc.model_dump_json()))


def codes(rc) -> set[str]:
    return {f.code for f in list(rc.findings) + list(rc.structural_findings)}


# ------------------------------------------------------------------------------------------------------- substituted rearrangements

OHM = "A 6.0 V supply drives a current of 0.50 A through a resistor. Calculate its resistance."
MOMENTUM = "A 0.20 kg ball moving at 10 m/s hits a 1.0 kg block at rest and stops; the block moves off. Calculate the speed of the block."


@pytest.mark.parametrize("answer, task", [
    ("V = IR, so R = 6.0 / 0.50 = 12 Ω.", OHM),
    ("From V = IR we get R = 6.0 / 0.50 = 12 Ω.", OHM),
    ("m₁u₁ = m₂v₂, so v₂ = 0.20 × 10 / 1.0 = 2.0 m/s.", MOMENTUM),
])
def test_a_rearrangement_substituted_with_the_tasks_values_is_a_valid_step(answer, task):
    rc = receive(answer, task)
    assert errors(rc) == [] and "stem_invalid_step" not in defects(rc)


@pytest.mark.parametrize("answer, task", [
    ("V = IR, so R = 0.50 / 6.0 = 0.083 Ω.", OHM),
    ("m₁u₁ = m₂v₂, so v₂ = 1.0 × 10 / 0.20 = 50 m/s.", MOMENTUM),
])
def test_the_wrong_rearrangement_still_fails(answer, task):
    rc = receive(answer, task)
    assert "INT-SUBJ-001" in errors(rc) and "stem_invalid_step" in defects(rc)


# ------------------------------------------------------------------------------------------------------- extrapolation

CO2_2100 = "Atmospheric CO₂ rose from 340 ppm in 1980 to 410 ppm in 2020. Assuming a linear trend, estimate the concentration in 2100."
CO2_2000 = "Atmospheric CO₂ rose from 340 ppm in 1980 to 410 ppm in 2020. Assuming a linear trend, estimate the concentration in 2000."


def test_a_law_whose_head_has_a_subscript_digit_evaluated_past_the_data_is_an_extrapolation():
    rc = receive("CO₂ = 340 + 1.75(t − 1980), so in 2100 CO₂ = 340 + 1.75 × 120 = 550 ppm.", CO2_2100, *ESS)
    assert "ST-RANGE-001" in codes(rc) and "stem_extrapolation" in defects(rc)
    assert errors(rc) == []                                   # the evaluation itself is correct arithmetic


@pytest.mark.parametrize("answer", [
    "CO₂ = 340 + 1.75(t − 1980), so in 2000 CO₂ = 340 + 1.75 × 20 = 375 ppm.",
    "C = 340 + 1.75(t − 1980), so in 2000 C = 340 + 1.75 × 20 = 375 ppm.",
])
def test_the_same_law_evaluated_inside_the_data_is_clean(answer):
    rc = receive(answer, CO2_2000, *ESS)
    assert errors(rc) == [] and not defects(rc)


def test_a_value_after_a_preposition_is_no_operand_so_a_slip_after_it_is_still_caught():
    rc = receive("C = 340 + 1.75(t − 1980), so in 2000 C = 340 + 1.75 × 20 = 385 ppm.", CO2_2000, *ESS)
    assert "INT-SUBJ-001" in errors(rc) and "stem_arithmetic_slip" in defects(rc)
    heater = "A resistor's resistance R = 120 + 0.40T ohms, with T in °C. Calculate R at 60 °C."
    assert errors(receive("At 60 °C R = 120 + 0.40 × 60 = 144 Ω.", heater)) == []
    assert "INT-SUBJ-001" in errors(receive("At 60 °C R = 120 + 0.40 × 60 = 154 Ω.", heater))


RATES = "An enzyme's reaction rate was measured at 10, 20 and 30 °C: 6.0, 10.0 and 14.0 units."


def test_a_trend_stepped_past_a_series_that_writes_its_unit_once_is_an_extrapolation():
    rc = receive("The rate rises by 4.0 units per 10 °C. From 30 °C to 60 °C is three more steps, so the rate at 60 °C is 14.0 + 3 × 4.0 = 26 units.",
                 RATES + " Predict the rate at 60 °C.", *BIO)
    assert "ST-RANGE-001" in codes(rc) and "stem_extrapolation" in defects(rc)


def test_the_same_trend_stepped_inside_the_series_is_clean():
    rc = receive("The rate rises by 4.0 units per 10 °C. From 20 °C to 25 °C is half a step, so the rate at 25 °C is 10.0 + 0.5 × 4.0 = 12 units.",
                 RATES + " Estimate the rate at 25 °C.", *BIO)
    assert "ST-RANGE-001" not in codes(rc) and errors(rc) == []


def test_a_listed_series_shares_its_unit_in_the_request_reading():
    doc = build_document("x = 1", RATES, "biology")
    assert any(sorted(vals) == [10, 20, 30] for _unit, vals in doc.request.series)


# ------------------------------------------------------------------------------------------------------- rounding

EFFICIENCY = "A machine uses 500 J and delivers 347 J of useful energy. Is its efficiency at least 0.70?"


@pytest.mark.parametrize("answer", [
    "η = 347 / 500 ≈ 0.7, so η ≥ 0.70.",
    "η = 347 / 500 = 0.694, which is 0.7 to one significant figure. Since 0.7 is not less than 0.70, the efficiency is at least 0.70.",
])
def test_a_comparison_made_with_a_rounded_value_is_named(answer):
    assert "stem_rounding_changes_conclusion" in defects(receive(answer, EFFICIENCY))


def test_the_comparison_made_with_the_unrounded_value_is_clean():
    rc = receive("η = 347 / 500 = 0.694, so η < 0.70: the efficiency is below 0.70.", EFFICIENCY)
    assert "stem_rounding_changes_conclusion" not in defects(rc) and errors(rc) == []


# ------------------------------------------------------------------------------------------------------- word equations and inline conversions

TROLLEY = "A 2.0 kg trolley moves at 3.0 m/s. Calculate its kinetic energy."


def test_a_wrong_word_equation_is_a_wrong_formula():
    rc = receive("Kinetic energy = 0.5 × mass × speed = 0.5 × 2.0 × 3.0 = 3.0 J.", TROLLEY)
    assert "ST-REF-002" in codes(rc) and "stem_wrong_formula" in defects(rc)


def test_the_correct_word_equation_is_clean():
    rc = receive("Kinetic energy = 0.5 × mass × speed² = 0.5 × 2.0 × 3.0² = 9.0 J.", TROLLEY)
    assert not defects(rc) and "ST-PARSE-001" not in codes(rc) and errors(rc) == []


HEATER = "A 2000 W heater runs for 3.0 hours. Calculate the energy it transfers in joules."


def test_a_time_converted_inline_in_brackets_binds_the_law():
    rc = receive("E = Pt = 2000 W × (3.0 × 3600 s) = 2.16 × 10⁷ J.", HEATER)
    assert "ST-UNDEC-002" not in codes(rc) and errors(rc) == []
    assert "INT-SUBJ-001" in errors(receive("E = Pt = 2000 W × (3.0 × 3600 s) = 2.16 × 10⁶ J.", HEATER))


# ------------------------------------------------------------------------------------------------------- named conditions

def test_a_comparison_named_as_a_loop_condition_is_no_claim_that_it_holds():
    request = "A program runs a while loop with the condition n > 0, starting from n = 3 and decreasing n by 1 each time. Explain when the loop stops."
    rc = receive("A while loop with the condition n > 0 repeats while n is positive. Starting at n = 3, the loop stops when n = 0.", request, *CS)
    assert errors(rc) == []


def test_a_condition_whose_truth_value_the_sentence_states_is_checked():
    doc_ok = build_document("The final test (2 <= 1) fails, so the loop ends.", "", "computer_science")
    doc_bad = build_document("The final test (2 <= 3) fails, so the loop ends.", "", "computer_science")
    assert [it.source for it in doc_ok.items] == [it.source for it in doc_bad.items] != ["condition"]


# ------------------------------------------------------------------------------------------------------- bounded per-line work

def _emphasis_by_regex(line: str) -> list[tuple[int, int, int, int]]:
    rx = re.compile(r"(?<!\w)(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")
    return [(m.start(), m.end(), m.start(2), m.end(2)) for m in rx.finditer(line)]


@pytest.mark.parametrize("seed", range(6))
def test_the_fast_paths_give_the_readings_of_the_full_readers(seed):
    rng = random.Random(seed)
    alphabet = "ab *_=<>≈x1 2\n−\\&\t"
    for _ in range(300):
        line = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        if "\n" not in line:
            assert emphasis_spans(line) == _emphasis_by_regex(line), line
            text, index = plain_line(line)
            assert len(text) == len(index) and all(line[i] == ch for i, ch in zip(index, text))
        ranges = sorted({tuple(sorted(rng.sample(range(len(line) + 1), 2))) for _ in range(3)}) if len(line) > 1 else []
        old_blank = list(line)
        old_mask = list(line)
        for a, b in ranges:
            head = True
            for k in range(a, b):
                old_blank[k] = "\n" if line[k] == "\n" else " "
        merged = []
        for a, b in sorted(ranges):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            elif b > a:
                merged.append((a, b))
        for a, b in merged:
            head = True
            for k in range(a, b):
                if line[k] == "\n":
                    old_mask[k], head = "\n", True
                else:
                    old_mask[k], head = (MASK_HEAD if head else MASK_FILL), False
        assert blank_ranges(line, ranges) == "".join(old_blank)
        assert masked_view(line, ranges) == "".join(old_mask)
        for a in range(len(line)):
            s = line[a:].lstrip(" \t&")
            old = any(s.startswith(sign) for sign in ("=", "≈", "≃", "≠", "<", ">", "≤", "≥", "⇒", "\\approx", "\\neq", "\\leq", "\\geq",
                                                       "\\Rightarrow", "\\implies", "→", "\\to "))
            assert _starts_with_relation(line, a, len(line)) == old


def test_the_markup_index_finds_exactly_the_overlapping_ranges():
    rng = random.Random(7)
    ranges = [(a, a + rng.randint(1, 30)) for a in sorted(rng.sample(range(5000), 400))]
    index = _MarkupIndex(ranges)
    for _ in range(200):
        start = rng.randint(0, 5000)
        end = start + rng.randint(0, 200)
        assert sorted(index.overlapping(start, end)) == sorted((a, b) for a, b in ranges if a < end and b > start)


def test_a_long_answer_of_list_items_is_read_in_bounded_time():
    import time
    text = "- x = 1\n" * 12_500                                   # 100,000 characters
    t0 = time.perf_counter()
    doc = build_document(text, None, "physics")
    assert time.perf_counter() - t0 < 6.0                     # measured about 1 s (it was quadratic in statements x markers)
    assert len(doc.statements) == 512 and any(f.code == "ST-LIM-002" for f in doc.findings)
