"""STEM fault injection in the arena harness (``scripts/arena/stem_mutations.py`` and ``run_arena.py``): the three STEM
mutations find their sites without the front end under test, change a figure so that no rounding absorbs it, are
skipped when an answer has no site, apply only to STEM subjects, and are each named on the receipt with their code in a
contained multi-agent round; the English/History mutations and rounds are unchanged."""
from __future__ import annotations

import json
import sys
import time
from fractions import Fraction
from pathlib import Path

import pytest

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402
import stem_mutations as sm  # noqa: E402

TROLLEY_Q = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
TROLLEY = "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻²."
RUNNER_Q = "A runner covers 120 m in 8.0 s. Calculate the average speed."
RUNNER = "v = d/t = 120 m / 8.0 s = 15 m s⁻¹. The average speed is therefore 15 m s⁻¹."


@pytest.mark.parametrize("number, slipped", [("5.0", "8.0"), ("0.0125", "0.0425"), ("9.81", "6.81"), ("7", "4"), ("120", "420"), ("6.0", "9.0")])
def test_the_leading_digit_moves_by_three(number, slipped):
    assert sm.leading_digit_slip(number) == slipped
    a, b = Fraction(number), Fraction(slipped)
    lead = Fraction(10) ** (len(number.split(".")[0].lstrip("0")) - 1) if Fraction(number) >= 1 else Fraction(1, 10 ** (len(number) - len(number.lstrip("0.")) - 1))
    assert abs(a - b) >= 3 * lead * Fraction(99, 100)


def test_a_number_with_no_significant_digit_is_refused():
    with pytest.raises(ValueError):
        sm.leading_digit_slip("0.000")


def test_the_arithmetic_slip_changes_one_stated_result():
    inj = sm.mutate_stem(TROLLEY, TROLLEY_Q, "stem_arithmetic_slip")
    assert inj is not None and inj.expected == ("INT-SUBJ-001",)
    assert inj.marker == "(20 - 0)/4.0 = 8.0" and inj.marker in inj.text
    assert inj.text.replace("= 8.0", "= 5.0", 1) == TROLLEY  # exactly one figure changed


def test_the_wrong_unit_needs_operands_with_units():
    inj = sm.mutate_stem(RUNNER, RUNNER_Q, "stem_wrong_unit")
    assert inj is not None and inj.expected == ("ST-DIM-001", "ST-DIM-002") and inj.marker == "120 m / 8.0 s = 15 m s⁻²"
    # bare numbers fix no dimension: no site
    assert sm.mutate_stem(TROLLEY, TROLLEY_Q, "stem_wrong_unit") is None


def test_the_substitution_changes_a_given_value_inside_a_calculation_only():
    inj = sm.mutate_stem(RUNNER, RUNNER_Q, "stem_substitution")
    assert inj is not None and inj.marker == "120 m / 5.0 s" and inj.expected == ("INT-SUBJ-001",)
    # a Given line or a value stated for a symbol is no substitution
    given = "Given: t = 8.0 s.\nv = 120/4.0 = 30"
    assert sm.mutate_stem(given, RUNNER_Q, "stem_substitution") is None or "8.0" in sm.mutate_stem(given, RUNNER_Q, "stem_substitution").text
    assert sm.mutate_stem("t = 8.0 s and d = 120 m.", RUNNER_Q, "stem_substitution") is None
    assert sm.mutate_stem(RUNNER, "Calculate the speed.", "stem_substitution") is None  # no value in the request


def test_prose_has_no_site():
    for kind in sm.STEM_MUTATIONS:
        assert sm.mutate_stem("The war began in 1914 for many reasons; 2 sides fought.", "Explain the war of 1914.", kind) is None
    with pytest.raises(ValueError):
        sm.mutate_stem(TROLLEY, TROLLEY_Q, "invented_quotation")


def test_stem_subjects_are_the_stem_branches():
    assert sm.is_stem_subject("Physics") and sm.is_stem_subject("Chemistry") and sm.is_stem_subject("Mathematics: Analysis and Approaches")
    assert sm.is_stem_subject("Computer Science") and sm.is_stem_subject("Sports, Exercise and Health Science")
    assert not sm.is_stem_subject("History") and not sm.is_stem_subject("English A: Literature") and not sm.is_stem_subject("Underwater Basket Weaving")


@pytest.mark.parametrize("text", ["1 + " * 50_000 + "1 = 2", "(" * 100_000 + "2 = 3", "= 5.0 m s⁻² " * 20_000, "9" * 200_000 + " = 1",
                                  "a = 2 × 3 = 6 m\n" * 10_000])
def test_the_locators_are_bounded(text):
    t = time.perf_counter()
    for kind in sm.STEM_MUTATIONS:
        sm.mutate_stem(text, "Calculate 2 m and 3 s.", kind)
    assert time.perf_counter() - t < 5.0


def test_the_shared_mutations_are_unchanged():
    assert ra.MUTATIONS == ("invented_quotation", "invented_quotation_single", "altered_quotation", "self_certification", "wrong_arithmetic", "chronology_error")
    assert not set(sm.STEM_MUTATIONS) & set(ra.MUTATIONS)
    assert ra.stem_variant("No figures here.", "q", "stem_arithmetic_slip") == ("No figures here.", "SKIP")
    assert ra.stem_variant(TROLLEY, TROLLEY_Q, "stem_arithmetic_slip")[1] == "INT-SUBJ-001"
    assert ra.injection(TROLLEY, "stem_arithmetic_slip", TROLLEY_Q).markers == ("(20 - 0)/4.0 = 8.0",)


ITEMS = [
    {"task_id": "ph-1", "subject": "Physics", "agent_id": "physics-specialist", "task_type": "short_answer", "question": TROLLEY_Q, "supplied_texts": [],
     "response_text": TROLLEY},
    {"task_id": "ph-2", "subject": "Physics", "agent_id": "physics-specialist", "task_type": "short_answer", "question": RUNNER_Q, "supplied_texts": [],
     "response_text": RUNNER},
    {"task_id": "ch-1", "subject": "Chemistry", "agent_id": "chemistry-specialist", "task_type": "short_answer",
     "question": "Calculate the amount of substance in 9.0 g of water (M = 18.0 g mol⁻¹).", "supplied_texts": [],
     "response_text": "n = m/M = 9.0 g / 18.0 g mol⁻¹ = 0.50 mol. The amount of water is therefore 0.50 mol."},
    {"task_id": "ma-1", "subject": "Mathematics: Analysis and Approaches", "agent_id": "maths-specialist", "task_type": "short_answer",
     "question": "Solve 3x + 5 = 20.", "supplied_texts": [], "response_text": "3x + 5 = 20 ⇒ 3x = 15 ⇒ x = 5"},
    {"task_id": "hi-1", "subject": "History", "agent_id": "history-specialist", "task_type": "short_answer",
     "question": "Outline the rise in unemployment in Germany between 1928 and 1932.", "supplied_texts": [],
     "response_text": "Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932. The Depression was therefore decisive."},
]


def test_a_contained_round_names_every_stem_injection_and_leaves_history_unchanged(tmp_path):
    (tmp_path / "specialists").mkdir()
    for it in ITEMS:
        (tmp_path / "specialists" / f"{it['task_id']}.json").write_text(json.dumps(it, ensure_ascii=False), encoding="utf-8")
    out = ra.run_round(tmp_path)
    recs = out["records"]
    assert not out["failures"], [(r["file"], r["variant"], r.get("failure_reasons") or r.get("error")) for r in out["failures"]]
    history = {r["variant"] for r in recs if r["task_id"] == "hi-1"}
    assert history == {"genuine", *(k for k in ra.MUTATIONS if k != "altered_quotation")}  # no quotation to alter, no STEM variant
    for kind in sm.STEM_MUTATIONS:
        done = [r for r in recs if r["variant"] == kind]
        assert done and all(r["functional"] and r["named_by"] for r in done), kind
        assert {r["task_id"] for r in done} <= {"ph-1", "ph-2", "ch-1", "ma-1"}
        assert all(f["code"] in sm.STEM_EXPECTED[kind] for r in done for f in r["named_by"])
    assert {r["variant"] for r in recs if r["task_id"] == "ph-2"} >= set(sm.STEM_MUTATIONS)
    assert all(not [f for f in r["findings"] if f["severity"] == "error"] for r in recs if r["variant"] == "genuine")
    summary = (tmp_path / "summary.md").read_text()
    assert "| stem_arithmetic_slip |" in summary and "| stem_wrong_unit |" in summary and "| stem_substitution |" in summary
