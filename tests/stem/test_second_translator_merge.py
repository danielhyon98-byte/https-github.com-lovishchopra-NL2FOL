"""Regression tests for the STEM readings the second translator merge joined: the development branch's end-to-end detection
fixes (docs/STEM_DESIGN.md section 33: the LaTeX thin space between digit groups, closed powers read as one value, a model's
evaluation checked by itself) and the overseer build's STEM repairs (sections 21 to 32). Each test fails on the merge as git
first assembled it, where a reading of one side hid a check of the other or put a warning on correct work:

* rule ``restated-binding`` (STEM repair 2) paired a value after "giving" with a finance solver's setting ('$C/Y = 12$'), once
  the thin-space reading made the value ('$FV = -11\\,491.11$') readable: INT-SUBJ-004 on the genuine mai-e1 answer, and a
  second failed check beside the injected substitution the development branch's test pins alone;
* the count reader (STEM repair 1) took '2P₀' for the permutation count ⁿPᵣ (a subscript digit passes ``str.isdigit``), so
  'P(0) = 2P₀' after the model P = P₀e^(kt) was named undecided and its model evaluation (``stem-mod``) was never checked.
"""
from __future__ import annotations

import pytest

from epinoic_logic.stem import build_document
from epinoic_logic.stem.lexer import COMBINATION, PERMUTATION, combination_at

from .test_e2e_run1_detection import SPEC, receive
from .test_model_evaluations import MODEL_Q, receive as receive_model


def _res(text: str, profile: str) -> list:
    return [r for r in build_document(text, "Q", profile).relations if r.kind == "res"]


# ============================================================================================ rule restated-binding
def test_the_genuine_finance_solver_line_gets_no_warning():
    _reply, rc = receive("mai-e1")
    assert [(fc.constraint_id, fc.formal_status) for fc in rc.formal_checks if fc.satisfied is False] == []
    assert not [f for f in rc.findings if f.code.startswith("INT-SUBJ") and "m13.1" in f.claim_ids], [(f.code, f.claim_ids) for f in rc.findings]


def test_a_value_after_giving_is_not_set_against_a_relation_between_unknowns():
    assert _res("Finance solver: $N = 24$, $PV = 18\\,000$, $C/Y = 12$, giving $FV = -11\\,491.11$.", "mathematics_ai") == []
    assert _res("Then x/y = 5.0, so z = 6.0.", "mathematics_aa") == []


def test_control_a_relation_whose_symbols_have_stated_values_is_still_restated():
    for value in ("5.0", "6.0"):
        got = _res(f"Given v = 20 m s⁻¹ and t = 4.0 s. Then v/t = 5.0 m s⁻², so a = {value} m s⁻².", "physics")
        assert len(got) == 1 and "(rule restated-binding)" in got[0].reason, got


# ============================================================================================ counts and subscripted symbols
@pytest.mark.parametrize("text", ["2P₀", "2C₀ = 0.10 mol dm⁻³", "3P₁ + P₂", "5C₂ = 10"])
def test_a_coefficient_before_a_subscripted_letter_is_no_count(text):
    assert combination_at(text, 0, len(text)) is None


@pytest.mark.parametrize("text, reason", [("6P2 = 30", PERMUTATION), ("5C2 = 10", COMBINATION), ("10C3 = 120", COMBINATION),
                                          ("₅P₂ = 20", PERMUTATION), ("⁵C₂ = 10", COMBINATION)])
def test_control_the_written_counts_are_still_counts(text, reason):
    got = combination_at(text, 0, len(text))
    assert got is not None and got[1] == reason


def test_a_model_evaluation_at_zero_against_twice_the_initial_value_is_checked():
    rc = receive_model("P₀ = 250 and k = 2.05 (3 s.f.).\nP(t + 1) = P₀e^(k(t + 1))\nP(0) = 2P₀", MODEL_Q)
    mods = {fc.constraint_id: fc.formal_status for fc in rc.formal_checks if fc.constraint_id.startswith("stem-mod-")}
    assert mods == {"stem-mod-1": "SATISFIABLE", "stem-mod-2": "UNSATISFIABLE"}, mods
    assert not [r for r in build_document("P(0) = 2P₀", MODEL_Q, "mathematics_aa").relations if "permutation" in (r.reason or "")]
