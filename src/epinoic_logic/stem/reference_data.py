"""Closed STEM reference data: the quantities the data-booklet symbols stand for, and the booklet formulas.

This module is data. Nothing here is evaluated: every dimension is an exact :class:`~epinoic_logic.stem.units.Dimension`
built from integer exponents, every coefficient an exact ``Fraction``, and the readers in :mod:`.reference` only look
entries up. It follows the pattern of :mod:`.constants` (the booklet constants), and like that table it never supplies a
value the answer did not write: it fixes what a symbol *is* (kinetic energy, momentum), so the dimension of an answer's own
law for it can be compared with the quantity's (ST-REF-001, docs/STEM_DESIGN.md section 24).

* ``QUANTITIES``: one row per (symbol, profile family): the quantity's key and name, its dimension, its SI unit as text,
  and the other quantities the same letter commonly names (``ambiguous_with``). A symbol whose row lists another quantity
  is fixed only by the stated result's unit or the request (:func:`.reference.fixed_quantity`); one that no row lists for
  the profile is never fixed (a miss, never a false alarm).
* ``FORMULAS``: the data-booklet right-hand sides, each a product of reference symbols with integer powers and an exact
  coefficient (``E_k = ½mv²`` is ``1/2 · m¹ · v²``). A test checks that every right-hand side has its quantity's dimension,
  so a typing error in the table cannot fire a finding.
* ``BOOKLET_LAWS``: the data-booklet laws as the booklets write them, one quantity each (sums, roots and the sequence
  formulas of Mathematics too). They are read by the STEM front end itself, at first use, into the same nodes an answer's
  law is read into (:func:`.reference.booklet_laws`), so the form check (ST-REF-002) can set a law the answer states beside
  every booklet law for the same quantity over the same variables. A test reads each one and checks its dimension.

The profiles are the STEM profile keys of :mod:`.limits` (``physics``, ``chemistry``, ``biology``, ``ess``,
``sports_science``, ``design_technology``, ``stem``, and the Mathematics keys). Mathematics has the sequence quantities only
(dimensionless, for the form check); Computer Science has none.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from .units import Dimension

__all__ = ["QUANTITIES", "FORMULAS", "BOOKLET_LAWS", "GIVENS_LAWS", "DEFINITION_GIVENS_LAWS", "OBJECT_ORDINALS", "MEASUREMENT_NOUNS", "RefQuantity", "RefFormula", "QUANTITY_NAMES", "PHYSICS_PROFILES", "CHEMISTRY_PROFILES",
           "MATHEMATICS_PROFILES"]


def _d(m: int = 0, kg: int = 0, s: int = 0, a: int = 0, k: int = 0, mol: int = 0, cd: int = 0, angle: int = 0) -> Dimension:
    return Dimension((m, kg, s, a, k, mol, cd), angle)


#: the profile families a row applies to
PHYSICS_PROFILES = frozenset({"physics", "design_technology", "sports_science", "stem"})
CHEMISTRY_PROFILES = frozenset({"chemistry", "biology", "ess", "stem"})
MATHEMATICS_PROFILES = frozenset({"mathematics_aa", "mathematics_ai", "mathematics"})
_ALL_SCIENCE = PHYSICS_PROFILES | CHEMISTRY_PROFILES
_CHEM = CHEMISTRY_PROFILES - {"stem"}
_BIOLOGY = frozenset({"biology"})
_BODY = frozenset({"sports_science", "biology"})
_ESS = frozenset({"ess"})

# dimensions, by name
LENGTH, MASS, TIME, TEMPERATURE, AMOUNT = _d(m=1), _d(kg=1), _d(s=1), _d(k=1), _d(mol=1)
SPEED, ACCELERATION = _d(m=1, s=-1), _d(m=1, s=-2)
FORCE, ENERGY, POWER = _d(m=1, kg=1, s=-2), _d(m=2, kg=1, s=-2), _d(m=2, kg=1, s=-3)
MOMENTUM, PRESSURE, DENSITY = _d(m=1, kg=1, s=-1), _d(m=-1, kg=1, s=-2), _d(m=-3, kg=1)
FREQUENCY, CHARGE, CURRENT = _d(s=-1), _d(s=1, a=1), _d(a=1)
POTENTIAL, RESISTANCE = _d(m=2, kg=1, s=-3, a=-1), _d(m=2, kg=1, s=-3, a=-2)
VOLUME, CONCENTRATION, MOLAR_MASS = _d(m=3), _d(m=-3, mol=1), _d(kg=1, mol=-1)
SPECIFIC_HEAT, LATENT_HEAT = _d(m=2, s=-2, k=-1), _d(m=2, s=-2)
SPRING_CONSTANT, ANGULAR_VELOCITY = _d(kg=1, s=-2), _d(s=-1, angle=1)
AREA, MASS_PER_AREA = _d(m=2), _d(m=-2, kg=1)
DIMENSIONLESS = _d()


@dataclass(frozen=True)
class RefQuantity:
    """What a data-booklet symbol stands for in a family of profiles. ``ambiguous_with`` names the other quantities the
    letter commonly stands for (so the symbol alone does not fix it); ``names`` are the words a request uses for it."""

    symbol: str
    profiles: frozenset[str]
    key: str
    name: str
    dimension: Dimension
    si_unit: str
    ambiguous_with: tuple[str, ...] = ()
    names: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefFormula:
    """A data-booklet formula: ``lhs = coefficient × Π symbol^power`` over reference symbols (``terms``), for the quantity
    ``quantity``; ``text`` is how the booklet writes it."""

    key: str
    quantity: str
    lhs: str
    coefficient: Fraction
    terms: tuple[tuple[str, int], ...]
    text: str
    profiles: frozenset[str]


def _q(symbols: tuple[str, ...], profiles: frozenset[str], key: str, name: str, dim: Dimension, unit: str, ambiguous: tuple[str, ...] = (),
       names: tuple[str, ...] = ()) -> tuple[RefQuantity, ...]:
    return tuple(RefQuantity(s, profiles, key, name, dim, unit, ambiguous, names or (name,)) for s in symbols)


#: every reference quantity, by symbol spelling (the front end's canonical names: ``E_k``, ``Δh``, ``λ``)
QUANTITIES: tuple[RefQuantity, ...] = (
    # mechanics
    *_q(("E_k", "E_K", "Ek", "KE", "E_kin"), _ALL_SCIENCE, "kinetic_energy", "kinetic energy", ENERGY, "J"),
    *_q(("E_p", "E_P", "Ep", "PE", "GPE", "ΔE_p", "ΔE_P", "ΔGPE"), _ALL_SCIENCE, "potential_energy", "potential energy", ENERGY, "J",
        names=("potential energy", "gravitational potential energy")),
    *_q(("p",), PHYSICS_PROFILES, "momentum", "momentum", MOMENTUM, "kg m s⁻¹", ("pressure",)),
    # pressure in physics shares its letters with momentum and power: fixed only by the stated result's unit or the request
    # (repair round 2, ADV2 probe zs02: "p = F × A" for a pressure in Pa)
    *_q(("p", "P"), PHYSICS_PROFILES, "pressure", "pressure", PRESSURE, "Pa", ("momentum", "power")),
    *_q(("p",), CHEMISTRY_PROFILES - {"stem"}, "pressure", "pressure", PRESSURE, "Pa", ("momentum",)),
    *_q(("F", "F_net", "F_res"), PHYSICS_PROFILES, "force", "force", FORCE, "N", names=("force", "resultant force", "net force")),
    *_q(("a",), PHYSICS_PROFILES, "acceleration", "acceleration", ACCELERATION, "m s⁻²"),
    *_q(("v",), PHYSICS_PROFILES, "velocity", "velocity", SPEED, "m s⁻¹", names=("velocity", "speed")),
    *_q(("u",), PHYSICS_PROFILES, "initial_velocity", "initial velocity", SPEED, "m s⁻¹", names=("initial velocity", "initial speed")),
    *_q(("Δv",), PHYSICS_PROFILES, "velocity_change", "change in velocity", SPEED, "m s⁻¹"),
    *_q(("m",), _ALL_SCIENCE, "mass", "mass", MASS, "kg"),
    *_q(("t", "Δt"), _ALL_SCIENCE, "time", "time", TIME, "s"),
    *_q(("s",), PHYSICS_PROFILES, "displacement", "displacement", LENGTH, "m", names=("displacement", "distance")),
    *_q(("d",), PHYSICS_PROFILES, "distance", "distance", LENGTH, "m"),
    *_q(("h", "Δh"), PHYSICS_PROFILES, "height", "height", LENGTH, "m", ("Planck constant",)),
    *_q(("g",), PHYSICS_PROFILES, "free_fall", "acceleration of free fall", ACCELERATION, "m s⁻²", names=("acceleration of free fall",
        "gravitational field strength")),
    *_q(("W",), PHYSICS_PROFILES, "work", "work done", ENERGY, "J", ("weight",), names=("work done", "work")),
    *_q(("P",), PHYSICS_PROFILES, "power", "power", POWER, "W", ("pressure",)),
    *_q(("k",), PHYSICS_PROFILES, "spring_constant", "spring constant", SPRING_CONSTANT, "N m⁻¹", ("Boltzmann constant", "Coulomb constant")),
    *_q(("x",), PHYSICS_PROFILES, "extension", "extension", LENGTH, "m", ("a position",)),
    *_q(("ω",), PHYSICS_PROFILES, "angular_velocity", "angular velocity", ANGULAR_VELOCITY, "rad s⁻¹"),
    # thermal
    *_q(("Q",), PHYSICS_PROFILES, "thermal_energy", "thermal energy", ENERGY, "J", ("charge",), names=("thermal energy", "heat", "energy")),
    *_q(("ΔT", "Δθ"), _ALL_SCIENCE, "temperature_change", "temperature change", TEMPERATURE, "K"),
    *_q(("T",), _ALL_SCIENCE, "temperature", "temperature", TEMPERATURE, "K", ("period", "tension")),
    *_q(("c",), PHYSICS_PROFILES, "specific_heat", "specific heat capacity", SPECIFIC_HEAT, "J kg⁻¹ K⁻¹", ("speed of light", "concentration")),
    *_q(("L",), PHYSICS_PROFILES, "latent_heat", "specific latent heat", LATENT_HEAT, "J kg⁻¹", ("a length", "the Avogadro constant")),
    # waves
    *_q(("f",), PHYSICS_PROFILES, "frequency", "frequency", FREQUENCY, "Hz"),
    *_q(("λ",), PHYSICS_PROFILES, "wavelength", "wavelength", LENGTH, "m", ("decay constant",)),
    # electricity
    *_q(("I",), PHYSICS_PROFILES, "current", "current", CURRENT, "A", ("intensity",)),
    *_q(("V",), PHYSICS_PROFILES, "potential_difference", "potential difference", POTENTIAL, "V", ("volume",),
        names=("potential difference", "voltage", "p.d.")),
    *_q(("R",), PHYSICS_PROFILES, "resistance", "resistance", RESISTANCE, "Ω", ("radius", "gas constant")),
    *_q(("q",), PHYSICS_PROFILES, "charge", "charge", CHARGE, "C"),
    # matter
    *_q(("ρ",), _ALL_SCIENCE, "density", "density", DENSITY, "kg m⁻³", ("resistivity",)),
    *_q(("V",), CHEMISTRY_PROFILES - {"stem"}, "volume", "volume", VOLUME, "m³", ("potential difference",)),
    *_q(("n",), CHEMISTRY_PROFILES, "amount", "amount of substance", AMOUNT, "mol", ("refractive index", "a count"),
        names=("amount of substance", "amount", "moles", "number of moles")),
    *_q(("M",), CHEMISTRY_PROFILES, "molar_mass", "molar mass", MOLAR_MASS, "g mol⁻¹", ("a mass",)),
    *_q(("pH",), CHEMISTRY_PROFILES, "pH", "pH", DIMENSIONLESS, "(none)"),
    *_q(("η",), _ALL_SCIENCE, "efficiency", "efficiency", DIMENSIONLESS, "(none)"),
    # the other quantities a letter names, so the result's unit or the request can fix it (and the form check, ST-REF-002)
    *_q(("T",), PHYSICS_PROFILES, "period", "period", TIME, "s", ("temperature", "tension"), names=("period", "time period")),
    *_q(("l",), PHYSICS_PROFILES, "length", "length", LENGTH, "m"),
    *_q(("L",), PHYSICS_PROFILES, "length", "length", LENGTH, "m", ("specific latent heat",)),
    *_q(("r",), PHYSICS_PROFILES, "radius", "radius", LENGTH, "m", names=("radius",)),
    *_q(("E",), PHYSICS_PROFILES, "energy", "energy", ENERGY, "J", ("electric field strength", "emf"), names=("energy", "energy transferred")),
    *_q(("A",), PHYSICS_PROFILES, "area", "area", AREA, "m²", ("amplitude", "nucleon number"), names=("area", "cross-sectional area")),
    *_q(("W",), PHYSICS_PROFILES, "weight", "weight", FORCE, "N", ("work done",), names=("weight",)),
    *_q(("Q",), PHYSICS_PROFILES, "charge", "charge", CHARGE, "C", ("thermal energy",), names=("charge",)),
    *_q(("Q",), _CHEM, "thermal_energy", "thermal energy", ENERGY, "J", ("reaction quotient",), names=("thermal energy", "heat", "energy")),
    *_q(("c",), _CHEM, "concentration", "concentration", CONCENTRATION, "mol dm⁻³", ("specific heat capacity",), names=("concentration",)),
    *_q(("c",), _CHEM, "specific_heat", "specific heat capacity", SPECIFIC_HEAT, "J kg⁻¹ K⁻¹", ("concentration",),
        names=("specific heat capacity",)),
    # the two states of a dilution (repair round 2, holdout2 inverted-formula class): the numbered symbols are as ambiguous as
    # their letters, so a law of one is read only when a result's unit or the request fixes the quantity
    *_q(("c_1", "c_2"), _CHEM, "concentration", "concentration", CONCENTRATION, "mol dm⁻³", ("specific heat capacity",), names=("concentration",)),
    *_q(("c_1", "c_2"), _CHEM, "specific_heat", "specific heat capacity", SPECIFIC_HEAT, "J kg⁻¹ K⁻¹", ("concentration",),
        names=("specific heat capacity",)),
    *_q(("V_1", "V_2"), _CHEM, "volume", "volume", VOLUME, "m³", ("potential difference",)),
    *_q(("M",), _BIOLOGY, "magnification", "magnification", DIMENSIONLESS, "(none)", ("molar mass",), names=("magnification",)),
    *_q(("I",), _BIOLOGY, "image_size", "image size", LENGTH, "m", ("intensity",), names=("image size", "image length")),
    *_q(("A",), _BIOLOGY, "actual_size", "actual size", LENGTH, "m", ("area",), names=("actual size", "actual length", "real size")),
    *_q(("BMI",), _BODY, "bmi", "body mass index", MASS_PER_AREA, "kg m⁻²", names=("bmi", "body mass index")),
    # ESS: the Lincoln index of a capture-mark-recapture estimate (repair round 2; counts, so dimensionless)
    *_q(("N",), _ESS, "population_size", "population size", DIMENSIONLESS, "(none)",
        names=("population size", "estimated population size", "population estimate", "estimated population")),
    # Mathematics: the sequence quantities (dimensionless; read by the form check only)
    *_q(("S_n",), MATHEMATICS_PROFILES, "series_sum", "sum of the first n terms", DIMENSIONLESS, "(none)", names=("sum",)),
    *_q(("u_n",), MATHEMATICS_PROFILES, "nth_term", "n-th term", DIMENSIONLESS, "(none)"),
    # Mathematics: mensuration (repair round 5, ADV5-06: 'V = 2πrh' for a cylinder's volume). A letter of a mathematics answer
    # names many things (r a ratio or a correlation, h a step, A a set), so each is fixed only by a result's unit or the
    # request ("Calculate its volume"), never by the letter alone
    *_q(("V",), MATHEMATICS_PROFILES, "volume", "volume", VOLUME, "m³", ("a variable",), names=("volume",)),
    *_q(("A",), MATHEMATICS_PROFILES, "area", "area", AREA, "m²", ("a variable",), names=("area", "surface area", "curved surface area")),
    *_q(("r",), MATHEMATICS_PROFILES, "radius", "radius", LENGTH, "m", ("a common ratio", "a correlation coefficient"), names=("radius",)),
    *_q(("h",), MATHEMATICS_PROFILES, "height", "height", LENGTH, "m", ("a step",), names=("height",)),
)

#: the data-booklet formulas (right-hand sides over reference symbols)
FORMULAS: tuple[RefFormula, ...] = (
    RefFormula("kinetic_energy", "kinetic_energy", "E_k", Fraction(1, 2), (("m", 1), ("v", 2)), "E_k = ½mv²", _ALL_SCIENCE),
    RefFormula("potential_energy", "potential_energy", "ΔE_p", Fraction(1), (("m", 1), ("g", 1), ("Δh", 1)), "ΔE_p = mgΔh", _ALL_SCIENCE),
    RefFormula("momentum", "momentum", "p", Fraction(1), (("m", 1), ("v", 1)), "p = mv", PHYSICS_PROFILES),
    RefFormula("force", "force", "F", Fraction(1), (("m", 1), ("a", 1)), "F = ma", PHYSICS_PROFILES),
    RefFormula("work", "work", "W", Fraction(1), (("F", 1), ("s", 1)), "W = Fs", PHYSICS_PROFILES),
    RefFormula("power", "power", "P", Fraction(1), (("W", 1), ("t", -1)), "P = W/t", PHYSICS_PROFILES),
    RefFormula("pressure", "pressure", "p", Fraction(1), (("F", 1), ("A", -1)), "p = F/A", PHYSICS_PROFILES),
    RefFormula("potential_difference", "potential_difference", "V", Fraction(1), (("I", 1), ("R", 1)), "V = IR", PHYSICS_PROFILES),
    RefFormula("thermal_energy", "thermal_energy", "Q", Fraction(1), (("m", 1), ("c", 1), ("ΔT", 1)), "Q = mcΔT", PHYSICS_PROFILES),
    RefFormula("velocity", "velocity", "v", Fraction(1), (("f", 1), ("λ", 1)), "v = fλ", PHYSICS_PROFILES),
    RefFormula("acceleration", "acceleration", "a", Fraction(1), (("Δv", 1), ("Δt", -1)), "a = Δv/Δt", PHYSICS_PROFILES),
    RefFormula("current", "current", "I", Fraction(1), (("q", 1), ("t", -1)), "I = Δq/Δt", PHYSICS_PROFILES),
    RefFormula("density", "density", "ρ", Fraction(1), (("m", 1), ("V", -1)), "ρ = m/V", _ALL_SCIENCE),
    RefFormula("amount", "amount", "n", Fraction(1), (("m", 1), ("M", -1)), "n = m/M", CHEMISTRY_PROFILES),
    RefFormula("frequency", "frequency", "f", Fraction(1), (("T", -1),), "f = 1/T", PHYSICS_PROFILES),
)

#: quantity key -> its plain name (for messages)
QUANTITY_NAMES: Mapping[str, str] = MappingProxyType({q.key: q.name for q in QUANTITIES})

#: the data-booklet laws as written: (profiles, quantity key, law). Each is read by the STEM front end into nodes at first use
#: (:func:`.reference.booklet_laws`); a law whose reading fails, or whose left side is no lone symbol, is left out (a miss,
#: never a false alarm). The form check (ST-REF-002) names a law the answer states for a fixed quantity when it has exactly
#: the variables of one or more of these laws for that quantity and differs from every one of them as a function. A
#: quantity's laws over one set of variables are all listed (``E_p = mgh`` and ``ΔE_p = mgΔh``; ``P = VI`` and ``P = IV``),
#: so an equivalent spelling is never named; geometry is left out, because one letter names many shapes there.
BOOKLET_LAWS: tuple[tuple[frozenset[str], str, str], ...] = (
    # energy, momentum, force, work and power
    (_ALL_SCIENCE, "kinetic_energy", "E_k = ½mv²"), (_ALL_SCIENCE, "kinetic_energy", "KE = ½mv²"), (_ALL_SCIENCE, "kinetic_energy", "Ek = ½mv²"),
    (_ALL_SCIENCE, "kinetic_energy", "E_K = ½mv²"), (PHYSICS_PROFILES, "kinetic_energy", "E_k = p²/(2m)"),
    (_ALL_SCIENCE, "potential_energy", "ΔE_p = mgΔh"), (_ALL_SCIENCE, "potential_energy", "E_p = mgh"), (_ALL_SCIENCE, "potential_energy", "E_p = mgΔh"),
    (_ALL_SCIENCE, "potential_energy", "GPE = mgh"), (_ALL_SCIENCE, "potential_energy", "PE = mgh"), (PHYSICS_PROFILES, "potential_energy", "E_p = ½kx²"),
    (PHYSICS_PROFILES, "momentum", "p = mv"),
    (PHYSICS_PROFILES, "force", "F = ma"), (PHYSICS_PROFILES, "force", "F = mg"), (PHYSICS_PROFILES, "force", "F = kx"),
    (PHYSICS_PROFILES, "force", "F = mv²/r"), (PHYSICS_PROFILES, "force", "F = mω²r"), (PHYSICS_PROFILES, "force", "F = Δp/Δt"),
    (PHYSICS_PROFILES, "work", "W = Fs"), (PHYSICS_PROFILES, "work", "W = Fd"), (PHYSICS_PROFILES, "weight", "W = mg"),
    (PHYSICS_PROFILES, "power", "P = W/t"), (PHYSICS_PROFILES, "power", "P = E/t"), (PHYSICS_PROFILES, "power", "P = Fv"),
    (PHYSICS_PROFILES, "power", "P = VI"), (PHYSICS_PROFILES, "power", "P = IV"), (PHYSICS_PROFILES, "power", "P = I²R"),
    (PHYSICS_PROFILES, "power", "P = V²/R"),
    (PHYSICS_PROFILES, "pressure", "p = F/A"), (PHYSICS_PROFILES, "pressure", "P = F/A"),
    (PHYSICS_PROFILES, "energy", "E = Pt"), (PHYSICS_PROFILES, "energy", "E = VIt"), (PHYSICS_PROFILES, "energy", "E = IVt"),
    (PHYSICS_PROFILES, "energy", "E = VQ"), (PHYSICS_PROFILES, "energy", "E = QV"),
    # electricity
    (PHYSICS_PROFILES, "potential_difference", "V = IR"), (PHYSICS_PROFILES, "potential_difference", "V = W/Q"),
    (PHYSICS_PROFILES, "potential_difference", "V = E/Q"), (PHYSICS_PROFILES, "potential_difference", "V = P/I"),
    (PHYSICS_PROFILES, "resistance", "R = V/I"), (PHYSICS_PROFILES, "resistance", "R = ρL/A"), (PHYSICS_PROFILES, "resistance", "R = ρl/A"),
    (PHYSICS_PROFILES, "current", "I = V/R"), (PHYSICS_PROFILES, "current", "I = Q/t"), (PHYSICS_PROFILES, "current", "I = q/t"),
    (PHYSICS_PROFILES, "current", "I = P/V"),
    (PHYSICS_PROFILES, "charge", "Q = I × t"), (PHYSICS_PROFILES, "charge", "q = I × t"),
    # thermal physics
    (PHYSICS_PROFILES, "thermal_energy", "Q = mcΔT"), (PHYSICS_PROFILES, "thermal_energy", "Q = mcΔθ"), (PHYSICS_PROFILES, "thermal_energy", "Q = mL"),
    (_CHEM, "thermal_energy", "Q = mcΔT"), (_CHEM, "thermal_energy", "Q = mcΔθ"),
    # motion, circles, waves and oscillations
    (PHYSICS_PROFILES, "velocity", "v = fλ"), (PHYSICS_PROFILES, "velocity", "v = d/t"), (PHYSICS_PROFILES, "velocity", "v = s/t"),
    (PHYSICS_PROFILES, "velocity", "v = u + at"), (PHYSICS_PROFILES, "velocity", "v = ωr"), (PHYSICS_PROFILES, "velocity", "v = 2πr/T"),
    (PHYSICS_PROFILES, "acceleration", "a = Δv/Δt"), (PHYSICS_PROFILES, "acceleration", "a = (v − u)/t"), (PHYSICS_PROFILES, "acceleration", "a = F/m"),
    (PHYSICS_PROFILES, "acceleration", "a = v²/r"), (PHYSICS_PROFILES, "acceleration", "a = ω²r"),
    (PHYSICS_PROFILES, "displacement", "s = ut + ½at²"), (PHYSICS_PROFILES, "displacement", "s = vt"), (PHYSICS_PROFILES, "displacement", "s = ½(u + v)t"),
    (PHYSICS_PROFILES, "distance", "d = vt"),
    (PHYSICS_PROFILES, "frequency", "f = 1/T"), (PHYSICS_PROFILES, "frequency", "f = v/λ"),
    (PHYSICS_PROFILES, "wavelength", "λ = v/f"),
    (PHYSICS_PROFILES, "period", "T = 1/f"), (PHYSICS_PROFILES, "period", "T = 2π√(l/g)"), (PHYSICS_PROFILES, "period", "T = 2π√(L/g)"),
    (PHYSICS_PROFILES, "period", "T = 2π√(m/k)"), (PHYSICS_PROFILES, "period", "T = 2πr/v"),
    (PHYSICS_PROFILES, "angular_velocity", "ω = 2π/T"), (PHYSICS_PROFILES, "angular_velocity", "ω = 2πf"), (PHYSICS_PROFILES, "angular_velocity", "ω = v/r"),
    # matter and amounts
    (_ALL_SCIENCE, "density", "ρ = m/V"),
    (CHEMISTRY_PROFILES, "amount", "n = m/M"), (CHEMISTRY_PROFILES, "amount", "n = cV"), (CHEMISTRY_PROFILES, "amount", "n = pV/(RT)"),
    (_CHEM, "concentration", "c = n/V"), (_CHEM, "volume", "V = n/c"), (_CHEM, "volume", "V = nRT/p"), (_CHEM, "pressure", "p = nRT/V"),
    # a dilution, c₁V₁ = c₂V₂, solved for each of its symbols
    (_CHEM, "concentration", "c_2 = c_1 × V_1 / V_2"), (_CHEM, "concentration", "c_1 = c_2 × V_2 / V_1"),
    (_CHEM, "volume", "V_2 = c_1 × V_1 / c_2"), (_CHEM, "volume", "V_1 = c_2 × V_2 / c_1"),
    (CHEMISTRY_PROFILES, "molar_mass", "M = m/n"),
    # biology and the body
    (_BIOLOGY, "magnification", "M = I/A"), (_BIOLOGY, "actual_size", "A = I/M"), (_BIOLOGY, "image_size", "I = AM"), (_BIOLOGY, "image_size", "I = MA"),
    (_BODY, "bmi", "BMI = m/h²"),
    # ESS: Lincoln index, N = (number marked in the first sample × number caught in the second) / number of marked recaptured
    (_ESS, "population_size", "N = MC/R"), (_ESS, "population_size", "N = (M × C)/R"),
    # Mathematics: arithmetic sequences and series
    (MATHEMATICS_PROFILES, "nth_term", "u_n = u_1 + (n − 1)d"),
    (MATHEMATICS_PROFILES, "series_sum", "S_n = (n/2)(2u_1 + (n − 1)d)"), (MATHEMATICS_PROFILES, "series_sum", "S_n = (n/2)(u_1 + u_n)"),
    # Mathematics: mensuration of the cylinder, cone and sphere (repair round 5, ADV5-06)
    (MATHEMATICS_PROFILES, "volume", "V = πr²h"), (MATHEMATICS_PROFILES, "volume", "V = (1/3)πr²h"), (MATHEMATICS_PROFILES, "volume", "V = (4/3)πr³"),
    (MATHEMATICS_PROFILES, "area", "A = πr²"), (MATHEMATICS_PROFILES, "area", "A = 2πrh"), (MATHEMATICS_PROFILES, "area", "A = 4πr²"),
    (MATHEMATICS_PROFILES, "area", "A = 2πr² + 2πrh"),
)

# ----------------------------------------------------------------------------------------------- closed cue tables
#: words and phrases that state an extrapolation caveat (ST-RANGE-001 stays silent when the answer writes one)
EXTRAPOLATION_CAVEATS: tuple[str, ...] = (
    "extrapolat", "outside the range", "outside the measured range", "outside the data", "beyond the data", "beyond the range",
    "beyond the measured range", "beyond the measurements", "assuming the trend continues", "if the trend continues", "assumes the trend",
    "may not hold", "might not hold", "may not apply", "might not apply", "may not be valid", "might not be valid", "may not continue",
    "might not continue", "unreliable", "cannot be relied", "should be treated with caution", "with caution", "denature",
)
#: request phrases that ask for working (ST-WORK-001)
WORKING_CUES: tuple[str, ...] = (
    "show your working", "show working", "showing your working", "showing working", "show full working", "show all working", "show all your working",
    "show all the working", "show your full working", "showing full working", "showing all working", "showing all your working", "show the working",
    "with working", "show your method", "show each step", "showing each step", "show all steps", "show the steps",
    # repair round 3 (V3-H2-STEM-MISSES): the participle forms of "show your method"
    "showing your method", "show the method", "showing the method", "showing method", "show method",
)
#: command terms that ask for a calculation; with two or more marks they ask for working too (ST-WORK-001)
WORKING_COMMANDS: tuple[str, ...] = ("calculate", "determine", "show")
#: The laws in which a temperature is the absolute (thermodynamic) temperature, as the base symbols each holds (subscripts
#: aside): the ideal gas law and its rearrangements, the combined gas laws (Boyle, Charles, Gay-Lussac), the Gibbs energy,
#: the mean kinetic energy of a particle, the Stefan-Boltzmann law and Wien's law. A value written in °C or °F substituted
#: for their T must first be converted to kelvin (repair round 4, ADV4-01: ST-UNIT-003 reads it in kelvin). A law of the
#: working is one of these when its symbols are among one row's and include T.
ABSOLUTE_TEMPERATURE_LAWS: tuple[frozenset[str], ...] = (
    frozenset({"p", "P", "V", "n", "R", "T"}),                 # pV = nRT and its rearrangements; p₁V₁/T₁ = p₂V₂/T₂, V₂ = V₁T₂/T₁, p₂ = p₁T₂/T₁
    frozenset({"ΔG", "ΔH", "ΔS", "T", "G", "H", "S"}),         # ΔG = ΔH − TΔS
    frozenset({"E", "Eₖ", "E_k", "Ek", "KE", "k", "T"}),       # E = (3/2)kT
    frozenset({"P", "L", "σ", "A", "T", "e", "ε"}),            # P = eσAT⁴
    frozenset({"λ", "λₘₐₓ", "λ_max", "b", "T"}),              # λ_max T = b
)
#: the laws of uniform motion over which the stated givens are checked for consistency (ST-GIVEN-004): the booklet's text of
#: each (:data:`BOOKLET_LAWS`); their symbols are the standard u, v, a, t and s of uniform motion
GIVENS_LAWS: frozenset[str] = frozenset({"v = u + at", "s = ut + ½at²", "s = ½(u + v)t"})
#: definitions over which the stated givens are checked for consistency whatever the motion (ST-GIVEN-004, repair round 3,
#: ADV3-09): the booklet's text of each, with the dimension (exponents over m, kg, s, A, K, mol, cd) each symbol must carry
#: for the definition to be read: a density, a mass and a volume for ``ρ = m/V``
DEFINITION_GIVENS_LAWS: dict[str, dict[str, tuple[int, int, int, int, int, int, int]]] = {
    "ρ = m/V": {"ρ": (-3, 1, 0, 0, 0, 0, 0), "m": (0, 1, 0, 0, 0, 0, 0), "V": (3, 0, 0, 0, 0, 0, 0)},
}

#: words before a second binding of a symbol that mark a change of the same quantity, not another quantity (ST-SCOPE-002)
CHANGE_MARKERS: tuple[str, ...] = (
    "later", "now", "then", "after", "afterwards", "becomes", "become", "became", "changes", "changed", "new", "increases", "increased",
    "decreases", "decreased", "rises", "rose", "falls", "fell", "drops", "dropped", "final", "finally", "next", "second", "when", "until",
    "instead", "corrected", "correction", "revised", "recalculated", "updated",
)
#: ordinals that, before an object noun ("the second trolley"), name another object, not a change of the same quantity; before
#: a measurement noun ("the second reading") they keep marking a change (ST-SCOPE-002)
OBJECT_ORDINALS: frozenset[str] = frozenset({"first", "second", "third", "fourth", "other", "another", "former", "latter"})
MEASUREMENT_NOUNS: frozenset[str] = frozenset({"reading", "readings", "measurement", "measurements", "value", "values", "attempt", "trial", "trials",
                                               "time", "calculation", "result", "results", "run", "estimate", "try", "step", "part"})
#: words that carry no quantity in a binding's noun phrase ("The car's speed is v = …": car, speed)
NOUN_PHRASE_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "of", "in", "at", "on", "to", "for", "and", "or", "its", "it", "this", "that", "these",
    "with", "by", "as", "so", "we", "our", "their", "his", "her", "given", "data", "let", "take", "taking", "using", "use", "where", "has", "have",
    "value", "values", "equal", "equals", "s", "about", "approximately", "therefore", "hence", "thus", "which", "gives", "get", "find", "found",
})
#: nouns of a stated target that the answer says a value meets or misses ("meets the 80% target", "the target of at least
#: 80% is met"), read for ST-ROUND-001 when the value is one the working rounded (repair round 2, holdout2 rounding class)
TARGET_NOUNS: tuple[str, ...] = ("target", "threshold", "minimum", "requirement", "benchmark", "goal", "pass mark", "standard", "criterion",
                                 "cut-off", "cutoff", "quota",
                                 # a limit a value reaches or stays within ('the speed limit is 30 m s⁻¹'; repair round 5, ADV5-05)
                                 "limit", "maximum")
#: verbs that say a value reaches a target (it is at least the target), goes beyond it, or misses it (it is below it)
TARGET_REACH_VERBS: frozenset[str] = frozenset({"meet", "meets", "met", "meeting", "reach", "reaches", "reached", "reaching", "achieve", "achieves",
                                                "achieved", "achieving", "hit", "hits", "hitting", "satisfy", "satisfies", "satisfied", "attain",
                                                "attains", "attained", "pass", "passes", "passed"})
TARGET_EXCEED_VERBS: frozenset[str] = frozenset({"exceed", "exceeds", "exceeded", "exceeding", "beat", "beats", "beaten", "surpass", "surpasses",
                                                 "surpassed", "above", "over"})
TARGET_MISS_VERBS: frozenset[str] = frozenset({"miss", "misses", "missed", "missing", "below", "under", "short"})
#: the bound a target states before its value ("a target of at least 80%", "a maximum of 5 g"): (phrase, IR order operator the
#: value must meet); a target with none is one to reach (at least its value)
TARGET_BOUNDS: tuple[tuple[str, str], ...] = (
    ("no less than", "ge"), ("not less than", "ge"), ("at least", "ge"), ("minimum of", "ge"), ("more than", "gt"), ("greater than", "gt"),
    ("higher than", "gt"), ("above", "gt"), ("over", "gt"), ("no more than", "le"), ("not more than", "le"), ("at most", "le"),
    ("maximum of", "le"), ("less than", "lt"), ("lower than", "lt"), ("below", "lt"), ("under", "lt"),
)
#: comparison phrases of prose ("0.25 s is not less than 0.25 s"): (phrase, IR order operator)
COMPARISON_PHRASES: tuple[tuple[str, str], ...] = (
    ("less than or equal to", "le"), ("greater than or equal to", "ge"), ("more than or equal to", "ge"), ("at least", "ge"), ("at most", "le"),
    ("no more than", "le"), ("no less than", "ge"), ("less than", "lt"), ("smaller than", "lt"), ("lower than", "lt"), ("below", "lt"),
    ("under", "lt"), ("greater than", "gt"), ("more than", "gt"), ("larger than", "gt"), ("higher than", "gt"), ("above", "gt"), ("over", "gt"),
    ("exceeds", "gt"), ("equal to", "eq"),
)
