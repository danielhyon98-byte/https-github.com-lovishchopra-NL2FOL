"""The data-booklet constants table (docs/STEM_DESIGN.md, D3): table integrity, the written-
constant match (D3a, which only ever widens) and the dimension guard of the unstated-symbol
reading (D3b, warning severity only)."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.constants import CONSTANTS, booklet_reading, constant_by_key, constants_for_symbol, match_written
from epinoic_logic.stem.units import DIMENSIONLESS, parse_unit


def test_keys_are_unique_and_every_constant_is_well_formed():
    keys = [c.key for c in CONSTANTS]
    assert len(keys) == len(set(keys))
    for c in CONSTANTS:
        assert c.symbols and c.name
        assert c.value > 0
        lo, hi = c.hull
        assert lo <= c.value <= hi
        for v in c.values:
            # every accepted value is a rounding or a refinement of the booklet value: within 2 per cent
            assert abs(v - c.value) <= c.value / 50, (c.key, v)
        if c.unit:
            u = parse_unit(c.unit)
            assert u is not None and not u.unknown and u.dim == c.dim, c.key
        else:
            assert c.dim == DIMENSIONLESS


@pytest.mark.parametrize("key,exact", [
    ("c", Fraction(299792458)),
    ("h", Fraction(662607015, 10 ** 42)),
    ("e", Fraction(1602176634, 10 ** 28)),
    ("N_A", Fraction(602214076, 1) * Fraction(10) ** 15),
    ("k_B", Fraction(1380649, 10 ** 29)),
])
def test_the_exact_si_values_are_accepted(key, exact):
    assert exact in constant_by_key(key).values


@pytest.mark.parametrize("key,booklet", [
    ("g", Fraction(981, 100)), ("G", Fraction(667, 100) * Fraction(1, 10 ** 11)), ("c", Fraction(3) * 10 ** 8),
    ("h", Fraction(663, 100) * Fraction(1, 10 ** 34)), ("R", Fraction(831, 100)), ("V_m", Fraction(227, 10000)),
])
def test_booklet_values(key, booklet):
    assert constant_by_key(key).value == booklet


def test_ambiguous_letters_are_documented():
    for key in ("c", "h", "e", "R", "g", "k_B"):
        assert constant_by_key(key).ambiguous


def _unit(text):
    u = parse_unit(text)
    assert u is not None
    return u


@pytest.mark.parametrize("value,half,sig,unit,expected", [
    (Fraction(98, 10), Fraction(5, 100), 2, None, "g"),                                # bare 9.8
    (Fraction(98, 10), Fraction(5, 100), 2, "m s^-2", "g"),                            # 9.8 m s⁻²
    (Fraction(981, 100), Fraction(5, 1000), 3, "N kg^-1", "g"),                        # 9.81 N kg⁻¹ (same dimension)
    (Fraction(10), Fraction(1, 2), 1, "m s^-2", "g"),                                  # the written estimate 10, with a unit only
    (Fraction(66, 10) * Fraction(1, 10 ** 34), Fraction(5, 100) * Fraction(1, 10 ** 34), 2, None, "h"),
    (Fraction(663, 100) * Fraction(1, 10 ** 34), Fraction(5, 1000) * Fraction(1, 10 ** 34), 3, "J s", "h"),
    (Fraction(300) * 10 ** 6, Fraction(5) * 10 ** 5, 3, "m s^-1", "c"),                 # 3.00 × 10⁸ m s⁻¹
    (Fraction(16, 10) * Fraction(1, 10 ** 19), Fraction(5, 100) * Fraction(1, 10 ** 19), 2, "C", "e"),
    (Fraction(831, 100), Fraction(5, 1000), 3, None, "R"),
])
def test_a_written_constant_matches_at_its_written_precision(value, half, sig, unit, expected):
    u = _unit(unit) if unit else None
    dim = u.dim if u else None
    m = match_written(value, half, sig, dim, unit_given=u is not None)
    assert m is not None and m.constant.key == expected
    lo, hi = m.interval()
    assert lo <= value - half and hi >= value + half       # the rounding interval is kept
    assert lo <= m.constant.value <= hi                     # and the booklet value is inside: only widening


@pytest.mark.parametrize("value,half,sig,unit", [
    (Fraction(98, 10), Fraction(5, 100), 2, "m"),           # 9.8 m is a length, not g
    (Fraction(10), Fraction(1, 2), 1, None),                # a bare 10 is no evidence of g
    (Fraction(3), Fraction(1, 2), 1, None),                 # one significant figure
    (Fraction(97, 10), Fraction(5, 100), 2, None),          # 9.7: its rounding interval misses every accepted value
    (Fraction(1, 10 ** 14), Fraction(5, 10 ** 16), 2, None),  # dimensionless K_w is never read from a bare number
    (Fraction(0), Fraction(5, 100), 2, None),
])
def test_no_match(value, half, sig, unit):
    u = _unit(unit) if unit else None
    assert match_written(value, half, sig, u.dim if u else None, unit_given=u is not None) is None


def test_profiles_restrict_the_match():
    g_value = Fraction(667, 100) * Fraction(1, 10 ** 11)
    assert match_written(g_value, Fraction(5, 1000) * Fraction(1, 10 ** 11), 3, None, unit_given=False, profile_key="physics").constant.key == "G"
    assert match_written(g_value, Fraction(5, 1000) * Fraction(1, 10 ** 11), 3, None, unit_given=False, profile_key="chemistry") is None


# --------------------------------------------------------------------------- D3b: the dimension guard


def test_booklet_reading_needs_the_dimension():
    js = _unit("J s").dim
    r = booklet_reading("h", "physics", js)
    assert r is not None and r.constant.key == "h"
    assert r.lo <= Fraction(662607015, 10 ** 42) <= r.hi
    assert "did not state it" in r.note
    assert booklet_reading("h", "physics", _unit("m").dim) is None       # h as a height: no booklet reading
    assert booklet_reading("h", "physics", None) is None                 # unknown dimension: never guessed


def test_booklet_reading_separates_letters_by_dimension():
    assert booklet_reading("k", "physics", _unit("J K^-1").dim).constant.key == "k_B"
    assert booklet_reading("k", "physics", _unit("N m^2 C^-2").dim).constant.key == "k_e"
    assert booklet_reading("k", "physics", _unit("N m^-1").dim) is None   # a spring constant
    assert booklet_reading("G", "chemistry", _unit("N m^2 kg^-2").dim) is None  # G is not a chemistry booklet symbol here
    assert {c.key for c in constants_for_symbol("k")} == {"k_B", "k_e"}


def test_an_unstated_planck_constant_is_read_at_warning_severity():
    doc = build_document("E = hf = 3.3 × 10⁻¹⁹ J with f = 5.0 × 10¹⁴ Hz.", None, "physics")
    plan = build_checks(doc, report_id="r", request_id="q")
    pc = plan.check("stem-sub-1")
    assert pc is not None and pc.failure_severity == "warning"
    groundings = [p["grounding"] for p in pc.problem["premises"] if "did not state it" in p["grounding"].get("note", "")]
    assert groundings and all(g["kind"] == "assumption" for g in groundings)
    assert "booklet" in pc.description


def test_no_booklet_reading_when_no_dimension_confirms_one():
    # c × 0.0250 = 2.50 × 10⁻³ mol: c as the speed of light has the wrong dimension, so c stays unbound
    doc = build_document("n = c × 0.0250 = 2.50 × 10⁻³ mol", None, "chemistry")
    plan = build_checks(doc, report_id="r", request_id="q")
    assert plan.check("stem-sub-1") is None
    f = plan.finding_for("stem-sub-1")
    assert f is not None and f.code == "ST-UNDEC-002" and f.severity == "warning"


def test_a_bound_letter_is_never_given_a_booklet_value():
    doc = build_document("Given h = 2.0 m and m = 3.0 kg, E = mgh = 3.0 × 9.81 × 2.0 = 58.9 J.", "Take g = 9.81 m s⁻².", "physics")
    plan = build_checks(doc, report_id="r", request_id="q")
    for pc in plan.checks:
        assert pc.failure_severity == "error" or pc.relation_kind in ("giv", "tgt")
        assert "did not state it" not in str(pc.problem)
