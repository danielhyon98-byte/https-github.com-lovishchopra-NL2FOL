"""ST-REF-001 (stem_wrong_formula): a law the answer applies whose dimensions are not those of the quantity its symbol names
in the closed reference (``stem/reference_data.py``: E_k is kinetic energy, p is momentum in physics). Fixed only when the
symbol is unambiguous in the profile, or the result's unit or the request names the quantity, and the dimension guard agrees.
"""
from __future__ import annotations

import pytest

from epinoic_logic.named import NAMED_CODES
from epinoic_logic.stem import build_document
from epinoic_logic.stem.reference import booklet_formulas, fixed_quantity, formula_dimension, quantities_for
from epinoic_logic.stem.reference_data import FORMULAS, QUANTITIES

from .argdiag_hub import deliver, stem_flags, structural


def _codes(text: str, request=None, profile: str = "physics") -> list[str]:
    return [f.code for f in build_document(text, request, profile).findings]


@pytest.mark.parametrize("case_id,claim", [("s02_wrong_formula", "s1.2"), ("s02b_wrong_formula_units_inline", "s1.1")])
def test_a_law_with_the_wrong_dimensions_is_named_stem_wrong_formula(case_id, claim):
    rc = deliver(case_id)
    [f] = structural(rc, "ST-REF-001")
    assert f.severity == "warning" and f.defect == "stem_wrong_formula" and f.claim_ids == [claim]
    assert "kinetic energy" in f.message and "momentum" in f.message
    assert NAMED_CODES["ST-REF-001"].defect == "stem_wrong_formula"


def test_control_the_correct_law_is_clean():
    assert stem_flags(deliver("s00_control_ke")) == []
    for text in ("E_k = ½mv² = ½ × 2.0 × 3.0² = 9.0 J", "E_k = 0.5 × m × v² = 0.5 × 2.0 × 3.0² = 9.0 J", "p = mv = 2.0 × 3.0 = 6.0 kg m s⁻¹"):
        assert "ST-REF-001" not in _codes(text), text


def test_control_an_ambiguous_symbol_with_no_unit_is_not_fixed():
    # p is momentum or pressure: with no unit and no request naming it, the reference does not fix it, so nothing is named
    assert "ST-REF-001" not in _codes("p = ½mv² = ½ × 2.0 × 3.0² = 9.0")
    assert fixed_quantity("p", "physics") is None or fixed_quantity("p", "physics").ambiguous_with
    # the result's unit decides it: then the wrong law is named
    assert "ST-REF-001" in _codes("p = ½mv² = ½ × 2.0 × 3.0² = 9.0 kg m s⁻¹")


def test_a_coefficient_written_as_a_decimal_or_a_divisor_is_no_dimension():
    # 0.5 m v² and m v / 2 read like ½ m v²: the coefficient carries no dimension (the ST-DIM coefficient rule)
    assert "ST-REF-001" not in _codes("E_k = 0.5 × m × v² = 0.5 × 2.0 × 3.0² = 9.0 J")
    assert "ST-REF-001" in _codes("E_k = m × v / 2 = 2.0 × 3.0 / 2 = 3.0 J")
    assert "ST-REF-001" in _codes("E_k = mv = 2.0 × 3.0 = 6.0 J")


def test_the_reference_is_closed_data():
    assert all(q.symbol and q.dimension is not None and q.profiles for q in QUANTITIES)
    assert {f.quantity for f in FORMULAS} >= {"kinetic_energy", "momentum"}
    ke = fixed_quantity("E_k", "physics")
    assert ke is not None and ke.key == "kinetic_energy" and quantities_for("E_k", "physics")
    [law] = booklet_formulas("kinetic_energy", "physics")
    assert formula_dimension(law, "physics") == ke.dimension
