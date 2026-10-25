"""ST-ROUND-001 (stem_rounding_changes_conclusion): a comparison the answer makes with a value it rounded holds for the
rounded value and not for the unrounded one, or the other way round (decided by the engine: an ``rnd`` check).
ST-RANGE-001 (stem_extrapolation): a model fitted to the request's data series is evaluated outside the series' range,
with no caveat. ST-WORK-001 (stem_missing_working): the request asks for working and the answer states only its result.
"""
from __future__ import annotations

from .argdiag_hub import deliver, failed_checks, findings, stem_flags, structural
from .. import argdiag_cases as C


def test_a_rounding_that_turns_the_comparison_is_st_round_001():
    rc = deliver("s04_rounding_flips_conclusion")
    [f] = findings(rc, "INT-SUBJ-004")
    assert f.defect == "stem_rounding_changes_conclusion" and "ST-ROUND-001" in f.message
    assert [c.constraint_id for c in failed_checks(rc)] == ["stem-rnd-1"]


def test_control_a_rounding_that_keeps_the_comparison_is_clean():
    assert stem_flags(deliver("s04c_control_rounding")) == []


def test_an_evaluation_outside_the_data_range_is_st_range_001():
    rc = deliver("s07_extrapolation")
    [f] = structural(rc, "ST-RANGE-001")
    assert f.severity == "warning" and f.defect == "stem_extrapolation" and "60 °C" in f.message and "10 to 30" in f.message


def test_controls_an_interpolation_and_an_extrapolation_with_a_caveat_are_clean():
    assert stem_flags(deliver("s07c_control_interpolation")) == []
    case = C.load_case("s07_extrapolation")
    caveated = case["answer"] + " This is an extrapolation beyond the measured range, so it may not hold (the enzyme may denature)."
    assert not structural(deliver(case, answer=caveated), "ST-RANGE-001")


def test_a_bare_result_where_working_is_asked_for_is_st_work_001():
    rc = deliver("s08_bare_stem_answer")
    [f] = structural(rc, "ST-WORK-001")
    assert f.severity == "warning" and f.defect == "stem_missing_working" and f.claim_ids


def test_control_the_same_result_with_its_working_is_clean():
    assert stem_flags(deliver("s08c_control_working_shown")) == []
    case = C.load_case("s08_bare_stem_answer")
    worked = "a = (v − u)/t = (20 − 0)/4.0 = 5.0 m s⁻². The acceleration is 5.0 m s⁻²."
    assert not structural(deliver(case, answer=worked), "ST-WORK-001")
