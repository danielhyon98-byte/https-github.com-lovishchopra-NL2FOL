"""Repair round 2, the quantitative prose reader (``branches.quant``): each class with its positive and a clean control.

* folds: "more than halved", "nearly halved", "fell threefold" are read with the bound on the right side (a fold of a factor
  below one is mirrored), and a repeated fold ("halved twice") is read in both readings (FA-AUTH-ESS-FOLD-INVERTED);
* a hedge ("close to doubling") is a symmetric approach band, and a negated figure ("it has not doubled", "this was not a
  rise of 20 per cent") is checked as negated (I2);
* a per-cent change that restates the result of the previous sentence's worked equation is checked against it
  (FA-ARITH-ECON-CROSS-SENTENCE);
* a list of figures between two years is the consecutive years' series when the counts match (FA-ALLDATA-GEO-SERIES);
* a change stated as a written calculation ("an increase of $9.00 − $8.00 = $1.00") states its result, not its first
  operand.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches.quant import extract_quant_checks
from epinoic_logic.engine import SolverConfig, verify

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def decided(sentence: str) -> list[tuple[str, str]]:
    return [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(sentence, request_id="r", claim_id="c")]


def statuses(sentence: str) -> set[str]:
    return {s for _k, s in decided(sentence)}


@pytest.mark.parametrize("right, wrong", [
    ("Unemployment was 36% in 2005 and 15% in 2015, so it more than halved.", "Unemployment was 36% in 2005 and 24% in 2015, so it more than halved."),
    ("Unemployment was 36% in 2005 and 19% in 2015, so it nearly halved.", "Unemployment was 36% in 2005 and 12% in 2015, so it nearly halved."),
    ("Output was 18 units in 2005 and 40 units in 2015, so it more than doubled.", "Output was 18 units in 2005 and 30 units in 2015, so it more than doubled."),
    ("Unemployment was 36% in 2005 and 12% in 2015, so it fell threefold.", "Unemployment was 36% in 2005 and 24% in 2015, so it fell threefold."),
    ("Unemployment was 36% in 2005 and 9% in 2015, so it halved twice.", "Unemployment was 36% in 2005 and 18% in 2015, so it halved twice."),
])
def test_a_fold_is_read_with_its_bound_on_the_right_side(right, wrong):
    assert decided(right) and statuses(right) == {"ENTAILED"}
    assert "COUNTEREXAMPLE" in statuses(wrong)


@pytest.mark.parametrize("right, wrong", [
    ("The population grew from 9.6 million in 1990 to 17.8 million in 2024, so it has not doubled.",
     "The population grew from 9.6 million in 1990 to 19.4 million in 2024, so it has not doubled."),
    ("Prices rose from 40 to 44, so this was not a rise of 20 per cent.", "Prices rose from 40 to 48, so this was not a rise of 20 per cent."),
    ("Prices rose from 40 to 44, which wasn't a rise of 20 per cent.", "Prices rose from 40 to 48, which wasn't a rise of 20 per cent."),
])
def test_a_negated_figure_is_checked_as_negated(right, wrong):
    assert statuses(right) == {"ENTAILED"}
    assert "COUNTEREXAMPLE" in statuses(wrong)


def test_not_only_affirms_the_figure_it_precedes():
    assert statuses("The population grew from 9.6 million in 1990 to 19.2 million in 2024, so it not only doubled.") == {"ENTAILED"}


def test_a_hedged_fold_is_an_approach_band():
    assert statuses("The population grew from 9.6 million in 1990 to 17.8 million in 2024, close to doubling.") == {"ENTAILED"}
    assert "COUNTEREXAMPLE" in statuses("The population grew from 9.6 million in 1990 to 11.0 million in 2024, close to doubling.")


def test_a_per_cent_change_restating_the_worked_result_is_checked_against_it():
    right = "The price rose from $8.00 to $9.00, an increase of $9.00 − $8.00 = $1.00. The price therefore rose by 12.5%."
    wrong = "The price rose from $8.00 to $9.00, an increase of $9.00 − $8.00 = $1.00. The price therefore rose by 15%."
    assert statuses(right) == {"ENTAILED"}
    assert ("percent_change", "COUNTEREXAMPLE") in decided(wrong)


@pytest.mark.parametrize("sentence, status", [
    ("The price rose from $8.00 to $9.00, an increase of $9.00 − $8.00 = $1.00.", "ENTAILED"),
    ("The price rose from $8.00 to $9.00, an increase of $9.00 − $8.00 = $1.50.", "COUNTEREXAMPLE"),
    ("Sales fell from 1,200 to 950 units, a fall of 1,200 − 950 = 250 units.", "ENTAILED"),
])
def test_a_change_written_as_a_calculation_states_its_result(sentence, status):
    assert decided(sentence) == [("abs_change", status)]


def test_a_list_of_figures_between_two_years_is_the_years_series():
    assert decided("Rainfall rose every year from 610 mm in 2019 to 640, 655, 690 and 720 mm in 2023.") == [("series_monotonic", "ENTAILED")]
    assert decided("Rainfall rose every year from 610 mm in 2019 to 640, 655, 600 and 720 mm in 2023.") == [("series_monotonic", "COUNTEREXAMPLE")]


def test_a_list_whose_count_does_not_match_the_years_is_no_series():
    assert decided("Rainfall rose every year from 610 mm in 2019 to 640, 655 and 720 mm in 2023.") == []
