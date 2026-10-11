"""Chemical species and equations: structure only (docs/STEM_DESIGN.md, section 4.8)."""
from __future__ import annotations

import time
from fractions import Fraction

import pytest

from epinoic_logic.stem.chem import canonical_formula, find_equations, latex_to_chem, parse_equation, parse_species
from epinoic_logic.stem.limits import StemLimits


def atoms(text: str) -> dict[str, int]:
    return dict(parse_species(text).atoms)


@pytest.mark.parametrize("text, expected", [
    ("H₂O", {"H": 2, "O": 1}), ("H2O", {"H": 2, "O": 1}), ("H_2O", {"H": 2, "O": 1}), ("H_{2}O", {"H": 2, "O": 1}),
    ("Ca(OH)₂", {"Ca": 1, "O": 2, "H": 2}), ("Al₂(SO₄)₃", {"Al": 2, "S": 3, "O": 12}), ("CuSO₄·5H₂O", {"Cu": 1, "S": 1, "O": 9, "H": 10}),
    ("Mg(((OH)))₂", {"Mg": 1, "O": 2, "H": 2}), ("H999O", {"H": 999, "O": 1}),
])
def test_formulas(text, expected):
    assert atoms(text) == expected


@pytest.mark.parametrize("text, expected_atoms, charge", [
    ("Fe²⁺", {"Fe": 1}, 2), ("SO₄^{2-}", {"S": 1, "O": 4}, -2), ("SO4^2-", {"S": 1, "O": 4}, -2), ("CO₃²⁻", {"C": 1, "O": 3}, -2),
    ("NH₄⁺", {"N": 1, "H": 4}, 1), ("Cl⁻", {"Cl": 1}, -1), ("Na+", {"Na": 1}, 1), ("OH-", {"O": 1, "H": 1}, -1),
    # glued ASCII charges
    ("Fe2+", {"Fe": 1}, 2), ("Al3+", {"Al": 1}, 3), ("O2-", {"O": 1}, -2), ("NH4+", {"N": 1, "H": 4}, 1), ("NO3-", {"N": 1, "O": 3}, -1),
    ("H3O+", {"H": 3, "O": 1}, 1), ("SO42-", {"S": 1, "O": 4}, -2), ("PO43-", {"P": 1, "O": 4}, -3), ("Cr2O72-", {"Cr": 2, "O": 7}, -2),
    ("Hg22+", {"Hg": 2}, 2), ("[Cu(NH3)4]2+", {"Cu": 1, "N": 4, "H": 12}, 2), ("[Fe(CN)6]3-", {"Fe": 1, "C": 6, "N": 6}, -3),
])
def test_charges(text, expected_atoms, charge):
    sp = parse_species(text)
    assert dict(sp.atoms) == expected_atoms and sp.charge == charge


def test_coefficients_states_and_electrons():
    sp = parse_species("2H₂O(l)")
    assert sp.coefficient == 2 and sp.coefficient_written and sp.state == "l"
    assert parse_species("½O₂").coefficient == Fraction(1, 2)
    assert parse_species("Fe2+(aq)").state == "aq" and parse_species("Fe2+(aq)").charge == 2
    assert parse_species("Cl-(aq)").charge == -1
    e = parse_species("2e⁻")
    assert e.electron and e.charge == -1 and e.coefficient == 2 and e.atoms == ()
    assert parse_species("2Fe3+").coefficient == 2 and parse_species("2Fe3+").charge == 3


@pytest.mark.parametrize("text, reason", [
    ("Ch₄", "unknown element symbol 'Ch'"), ("¹⁴C", "isotope notation"), ("Mg((((OH))))₂", "nested deeper than 3"), ("H1000", "1000 atoms of H"),
    ("H₂O₂₂₂₂₂₂₂", "2222 atoms of O"), ("xyz", "no formula"), ("", "an empty species"), ("(", "an unbalanced group"), ("H₂O)", "unexpected text"),
    ("H" * 300, "longer than the bound"),
])
def test_unreadable_species_raise_value_error_with_the_reason(text, reason):
    with pytest.raises(ValueError, match=reason.replace("(", r"\(")):
        parse_species(text)


def test_equations():
    eq = parse_equation("2H₂ + O₂ → 2H₂O")
    assert eq.readable and eq.arrow == "→" and [s.coefficient for s in eq.left] == [2, 1] and eq.right[0].formula == "H2O"
    assert parse_equation("N₂ + 3H₂ ⇌ 2NH₃").arrow == "⇌" and parse_equation("H₂ <=> H₂").arrow == "⇌"
    assert parse_equation("CH4 + 2O2 -> CO2 + 2H2O").arrow == "→"
    eq = parse_equation("Cu2+ + Zn -> Cu + Zn2+")
    assert [(s.formula, s.charge) for s in eq.left] == [("Cu", 2), ("Zn", 0)] and [(s.formula, s.charge) for s in eq.right] == [("Cu", 0), ("Zn", 2)]
    eq = parse_equation("Zn(s) + Cu²⁺(aq) → Zn²⁺(aq) + Cu(s)")
    assert eq.readable and eq.elements() == ("Zn", "Cu")
    assert parse_equation("no arrow here") is None


def test_unreadable_equations_are_st_chem_001():
    eq = parse_equation("Ch₄ + O₂ → CO₂")
    assert eq.code == "ST-CHEM-001" and "Ch" in eq.error and not eq.readable
    eq = parse_equation("→ CO₂")
    assert eq.code == "ST-CHEM-001" and "both sides" in eq.error
    eq = parse_equation(" + ".join(["H₂"] * 17) + " → H₂")
    assert eq.code == "ST-CHEM-001" and "more than 16 species" in eq.error
    eq = parse_equation("H₂ + H₂ + H₂ → H₂", limits=StemLimits(max_species_per_side=2))
    assert eq.code == "ST-CHEM-001"


def test_find_equations_in_prose():
    found = find_equations("For 2H₂ + O₂ → 2H₂O, burning releases energy.", 100)
    assert [(e.text, e.start, e.end) for e in found] == [("2H₂ + O₂ → 2H₂O", 104, 119)]
    assert [e.text for e in find_equations("(Cl₂ + 2e⁻ → 2Cl⁻)", 0)] == ["Cl₂ + 2e⁻ → 2Cl⁻"]
    assert [e.text for e in find_equations("Then CaCO₃(s) → CaO(s) + CO₂(g) and Mg + 2HCl → MgCl₂ + H₂.", 0)] == [
        "CaCO₃(s) → CaO(s) + CO₂(g)", "Mg + 2HCl → MgCl₂ + H₂"]
    assert [e.text for e in find_equations("So Fe2+(aq) + 2e- -> Fe(s).", 0)] == ["Fe2+(aq) + 2e- -> Fe(s)"]
    assert find_equations("x → y means maps to", 0) == []


def test_latex_and_canonical_forms():
    assert latex_to_chem(r"\ce{H2O}") == "H2O" and latex_to_chem(r"\mathrm{H_2O}") == "H_2O" and latex_to_chem(r"\text{CO}_2") == "CO_2"
    assert canonical_formula("H2O") == canonical_formula("H_{2}O") == "H₂O"
    assert canonical_formula("SO4^{2-}") == "SO₄²⁻"


def test_chemistry_is_bounded_and_linear():
    t = time.perf_counter()
    for text in ("H" * 79, "(" * 79, "Fe" * 40, "H₂O" * 26, "e" * 79, "[" * 40 + "]" * 39):
        try:
            parse_species(text)
        except ValueError:
            pass
    line = " + ".join(["2H₂O"] * 3000) + " → " + " + ".join(["H₂"] * 3000)
    find_equations(line, 0)
    parse_equation(line)
    assert time.perf_counter() - t < 2.0
