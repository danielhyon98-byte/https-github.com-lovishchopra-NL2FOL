"""Units, prefixes, dimensions and readings (docs/STEM_DESIGN.md, section 6)."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.stem.limits import PROFILES
from epinoic_logic.stem.units import DIMENSIONLESS, UNITS, Dimension, dimension_name, is_unit_atom, lookup_atom, parse_unit, unit_dimension

SPEED = Dimension((1, 0, -1, 0, 0, 0, 0))
ACCEL = Dimension((1, 0, -2, 0, 0, 0, 0))
FORCE = Dimension((1, 1, -2, 0, 0, 0, 0))
ENERGY = Dimension((2, 1, -2, 0, 0, 0, 0))
CONC = Dimension((-3, 0, 0, 0, 0, 1, 0))


def one(text: str, **kw):
    u = parse_unit(text, **kw)
    assert u is not None, text
    assert len(u.readings) == 1, (text, u.readings)
    return u.readings[0]


@pytest.mark.parametrize("text, factor", [
    ("km", Fraction(1000)), ("mg", Fraction(1, 10 ** 6)), ("µm", Fraction(1, 10 ** 6)), ("μs", Fraction(1, 10 ** 6)), ("um", Fraction(1, 10 ** 6)),
    ("ns", Fraction(1, 10 ** 9)), ("MPa", Fraction(10 ** 6)), ("GHz", Fraction(10 ** 9)), ("kJ", Fraction(1000)), ("dm³", Fraction(1, 1000)),
    ("cm³", Fraction(1, 10 ** 6)), ("mL", Fraction(1, 10 ** 6)), ("kWh", Fraction(3_600_000)), ("daN", Fraction(10)),
])
def test_prefixes_by_longest_match_with_exact_factors(text, factor):
    assert one(text).factor == factor


def test_ms_is_a_millisecond_and_m_s_is_metre_second():
    ms = one("ms")
    assert ms.factor == Fraction(1, 1000) and ms.dim == Dimension((0, 0, 1, 0, 0, 0, 0))
    m_s = one("m s")
    assert m_s.dim == Dimension((1, 0, 1, 0, 0, 0, 0))
    assert one("Nm").dim == ENERGY and one("N m").dim == ENERGY    # N is no prefix: newton metre either way


@pytest.mark.parametrize("text, dim", [
    ("m s⁻²", ACCEL), ("m/s/s", ACCEL), ("m/s²", ACCEL), ("m s^-2", ACCEL), ("m s^{-2}", ACCEL), ("m s**-2", ACCEL),
    ("J mol⁻¹ K⁻¹", Dimension((2, 1, -2, 0, -1, -1, 0))), ("mol dm⁻³", CONC), ("kg·m/s", Dimension((1, 1, -1, 0, 0, 0, 0))),
    ("kJ mol⁻¹", Dimension((2, 1, -2, 0, 0, -1, 0))), ("J/(mol K)", Dimension((2, 1, -2, 0, -1, -1, 0))), ("\\text{m s}^{-1}", SPEED),
    ("\\mathrm{mol\\,dm^{-3}}", CONC), ("N kg⁻¹", ACCEL), ("N m² kg⁻²", Dimension((3, -1, -2, 0, 0, 0, 0))), ("\\Omega^{-1}", Dimension((-2, -1, 3, 2, 0, 0, 0))),
    ("metres per second squared", ACCEL), ("kilometres per hour", SPEED), ("mol⁻² dm⁶", Dimension((6, 0, 0, 0, 0, -2, 0))),
])
def test_unit_expressions(text, dim):
    assert one(text).dim == dim


def test_exact_si_factors():
    assert one("km h⁻¹").factor == Fraction(5, 18)
    assert one("eV").factor == Fraction(1602176634, 10 ** 28)      # exact since the 2019 SI
    assert one("atm").factor == 101325
    assert one("min").factor == 60 and one("h").factor == 3600 and one("d").factor == 86400
    assert one("%").factor == Fraction(1, 100) and one("%").dim == DIMENSIONLESS
    assert one("°").factor is None and one("°").dim.angle == 1   # π/180 rad is not rational
    assert one("L").factor == Fraction(1, 1000)


def test_dimensions_of_derived_units():
    assert UNITS["N"].dim == FORCE
    assert UNITS["J"].dim == FORCE * Dimension((1, 0, 0, 0, 0, 0, 0))
    assert UNITS["W"].dim == UNITS["J"].dim / Dimension((0, 0, 1, 0, 0, 0, 0))
    assert UNITS["Pa"].dim == FORCE / Dimension((2, 0, 0, 0, 0, 0, 0))
    assert one("rad s⁻¹").dim.same_physical(one("Hz").dim)        # the angle is supplementary
    assert dimension_name(ACCEL) == "acceleration" and dimension_name(ENERGY) == "energy"


def test_ambiguity_table_bare_m_per_profile():
    chem = parse_unit("M", bare_m=PROFILES["chemistry"].bare_m)
    assert len(chem.readings) == 1 and chem.readings[0].dim == CONC and chem.readings[0].factor == 1000
    phys = parse_unit("M", bare_m=PROFILES["physics"].bare_m)
    assert len(phys.readings) == 2 and phys.ambiguity_code == "ST-UNIT-002"
    assert {r.dim for r in phys.readings} == {CONC, DIMENSIONLESS}
    maths = parse_unit("M", bare_m=PROFILES["mathematics_aa"].bare_m)
    assert len(maths.readings) == 1 and maths.readings[0].factor == 10 ** 6
    assert one("MPa").factor == 10 ** 6   # M as a prefix is never ambiguous


def test_tonne_only_in_ess_and_design_technology():
    assert parse_unit("t", tonne=PROFILES["physics"].tonne) is None
    ess = one("t", tonne=PROFILES["ess"].tonne)
    assert ess.factor == 1000 and ess.dim == Dimension((0, 1, 0, 0, 0, 0, 0))
    assert PROFILES["design_technology"].tonne and not PROFILES["chemistry"].tonne


def test_glued_ms_with_negative_exponent_has_two_readings():
    u = parse_unit("ms⁻¹")
    assert u is not None and len(u.readings) == 2 and u.ambiguity_code == "ST-UNIT-002"
    assert u.readings[0].factor == 1000 and u.readings[0].dim == Dimension((0, 0, -1, 0, 0, 0, 0))   # per millisecond (SI binding)
    assert u.readings[1].dim == SPEED and u.readings[1].factor == 1                                   # as evidently meant
    assert u.dim is None    # the readings disagree: no single dimension
    assert len(parse_unit("dm⁻³").readings) == 1   # not ambiguous: nobody writes day metre


def test_affine_temperatures():
    c = one("°C")
    assert c.affine == (Fraction(1), Fraction(27315, 100))
    f = one("°F")
    assert f.affine == (Fraction(5, 9), Fraction(45967, 100))
    compound = one("J kg⁻¹ °C⁻¹")
    assert compound.affine is None and compound.dim == Dimension((2, 0, -2, 0, -1, 0, 0))   # a temperature interval inside a compound


def test_unknown_atoms_are_kept_and_named():
    u = parse_unit("kJ m⁻² yr⁻¹")
    assert u is not None and u.unknown == ("yr",)
    assert u.readings[0].dim is None and u.readings[0].factor is None
    assert u.dim is None and not u.known


@pytest.mark.parametrize("text", ["", "abc", "5 m", "has", "m//s", "m^", "(m s", "m s)", "per", "x" * 200, "m 2", "squared"])
def test_not_units(text):
    assert parse_unit(text) is None


def test_atoms():
    assert is_unit_atom("kg") and is_unit_atom("Ω") and is_unit_atom("ohm") and is_unit_atom("Nm")
    assert not is_unit_atom("has")                     # no glued split h·as: only the curated glued units split
    assert is_unit_atom("as")                          # an attosecond atom; the parser reads atoms only in unit position
    assert lookup_atom("as")[0].prefix == "a" and lookup_atom("as")[0].unit.symbol == "s"
    assert not is_unit_atom("") and not is_unit_atom("xyz") and not is_unit_atom("t")
    assert [a.unit.symbol for a in lookup_atom("kg")] == ["g"] and lookup_atom("kg")[0].prefix == "k"
    assert lookup_atom("zz") == []


def test_unit_dimension_helper():
    assert unit_dimension("N") == FORCE
    assert unit_dimension("ms⁻¹") is None
    assert unit_dimension("yr") is None
