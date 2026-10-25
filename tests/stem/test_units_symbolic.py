"""ST-UNIT-003 (stem_unit_error): the working computes with numbers whose units it does not convert. Two cases:

* written: both sides carry units of one dimension but different scales and the as-written numbers agree only without the
  conversion ('… = 5000 g' for a mass in kg): a unit companion check (``stem-<kind>-<n>u``) holds iff the SI reading holds,
  and its failure is INT-SUBJ-001 with the FormalCheck's defect stem_unit_error;
* traced: bare numbers repeat the numbers of bindings stated in non-SI units ('m = 500 g', then '500 × 9.8'): the companion
  is a warning (INT-SUBJ-004), named ST-UNIT-003 in its description.
"""
from __future__ import annotations

import pytest

from .argdiag_hub import decided, deliver, failed_checks, findings, stem_flags


def _companions(text: str, request=None, profile: str = "physics"):
    return {cid: v for cid, v in decided(text, request, profile).items() if cid.endswith("u")}


def test_bare_numbers_of_non_si_bindings_are_named_st_unit_003():
    rc = deliver("s03a_unit_no_conversion_bare")
    [f] = findings(rc, "INT-SUBJ-004")
    assert f.defect == "stem_unit_error" and "ST-UNIT-003" in f.message and f.claim_ids
    assert [c.constraint_id for c in failed_checks(rc)] == ["stem-eq-1u"]


@pytest.mark.parametrize("case_id,companion", [("s03b_unit_no_conversion_units", "stem-eq-1u"), ("s03d_unit_symbolic_bindings", "stem-sub-1u")])
def test_written_units_that_hold_only_as_written_are_labelled_stem_unit_error(case_id, companion):
    rc = deliver(case_id)
    [f] = findings(rc, "INT-SUBJ-001")
    assert f.severity == "error" and f.defect == "stem_unit_error" and "ST-UNIT-003" in f.message
    assert [c.constraint_id for c in failed_checks(rc)] == [companion]


@pytest.mark.parametrize("case_id", ["s03k_control_conversion", "s03dk_control_symbolic_bindings"])
def test_controls_with_the_conversion_done_are_clean(case_id):
    assert stem_flags(deliver(case_id)) == []


@pytest.mark.parametrize("text", [
    "v = 5.03 m s⁻¹ × 3.6 = 18.1 km h⁻¹",          # a conversion by hand: the factor is written
    "v = 67 km h⁻¹ ÷ 3.6 = 18.6 m s⁻¹",
    "m = 2.5 kg = 2500 g",
    "E = 2.0 kJ + 500 J = 2500 J",
])
def test_controls_conversions_written_out_build_no_failing_companion(text):
    assert all(ok is not False for _pc, ok in _companions(text).values()), text


@pytest.mark.parametrize("text", [
    "W = F × d = 2.0 kN × 3.0 m = 6.0 J",            # the prefix lost: holds only as written
    "E = 2.0 kJ × 3 = 6.0 J",
])
def test_a_lost_prefix_fails_its_companion(text):
    comps = _companions(text)
    assert comps and any(ok is False and pc.defect == "stem_unit_error" for pc, ok in comps.values()), text
    assert decided(text)["stem-eq-1"][1] is True  # the arithmetic as written holds: the fault is the units, and only the companion names it


def test_control_the_same_working_with_the_prefix_kept_builds_no_companion():
    assert _companions("W = F × d = 2.0 kN × 3.0 m = 6.0 kJ") == {}
    assert decided("m = 2.5 kg = 25 g")["stem-cnv-1"][1] is False  # a value against a value is a conversion, decided in SI
