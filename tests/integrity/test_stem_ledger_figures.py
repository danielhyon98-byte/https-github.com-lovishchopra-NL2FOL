"""Synthesis-fidelity figures read scientific notation (docs/STEM_DESIGN.md, section 11.5): one figure per numeral in
scientific notation, equal to its plain decimal spelling; figures with no exponent are read as before."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.ledger import _exact_decimal, _figure_differences, check_synthesis_ledger, figure_spellings, figure_tokens
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
from fractions import Fraction


@pytest.mark.parametrize("text,token", [
    ("c = 3.0e8 m/s", "300000000"),
    ("c = 3.0 × 10⁸ m s⁻¹", "300000000"),
    ("c = 3.0 x 10^8 m/s", "300000000"),
    ("G is 6.67 × 10⁻¹¹ N m² kg⁻²", "0.0000000000667"),
    ("n = 1.2*10**6", "1200000"),
    ("x = 6.0E-3", "0.006"),
    ("q = 1.6 × 10^{-19} C", "0.00000000000000000016"),
    ("x = −2.5e3", "-2500"),
])
def test_scientific_notation_is_one_exact_figure(text, token):
    assert figure_tokens(text) == {token}


def test_today_the_mantissa_and_the_power_are_no_longer_two_figures():
    labels = [label for label, _keys in figure_spellings("G is 6.67 × 10⁻¹¹ N m² kg⁻².")]
    assert labels == ["6.67 × 10⁻¹¹"]
    assert "6.67" not in figure_tokens("G is 6.67 × 10⁻¹¹.") and "10" not in figure_tokens("G is 6.67 × 10⁻¹¹.")


def test_spellings_meet_across_notations():
    keys_a = dict(figure_spellings("c = 3.0e8 m/s"))["3.0e8"]
    keys_b = dict(figure_spellings("c = 3.0 × 10⁸ m/s"))["3.0 × 10⁸"]
    keys_c = dict(figure_spellings("c = 300000000 m/s"))["300000000"]
    assert keys_a & keys_b and keys_a & keys_c and "3e8" in keys_a


@pytest.mark.parametrize("text,tokens", [
    ("In 1802 there were 2 million people.", {"1802", "2"}),
    ("The rate rose from 3.2 to 24.9 per cent.", {"3.2", "24.9"}),
    ("It cost 1,200 marks in 1923.", {"1200", "1923"}),
    ("Two thirds of 600 voted.", {"600", "0.6667"}),
    ("The 10 cats ate 5.", {"10", "5"}),
])
def test_figures_with_no_exponent_are_read_as_before(text, tokens):
    assert figure_tokens(text) == tokens


def test_figures_beyond_the_scanner_bounds_are_not_read():
    assert figure_tokens("x = 1e999 and y = 1.0 × 10^999") == set()


def test_exact_decimal():
    assert _exact_decimal(Fraction(667, 10 ** 13)) == "0.0000000000667" and _exact_decimal(Fraction(-3, 2)) == "-1.5"
    assert _exact_decimal(Fraction(1, 3)) == "1/3" and _exact_decimal(Fraction(0)) == "0" and _exact_decimal(Fraction(5, 4)) == "1.25"


def test_a_restated_figure_in_another_notation_is_not_introduced_and_a_changed_one_is():
    introduced, dropped, _ = _figure_differences("The speed of light is 3.0e8 m/s.", ["c = 3.0 × 10⁸ m s⁻¹"])
    assert introduced == [] and dropped == []
    introduced, dropped, _ = _figure_differences("The speed of light is 3.0e9 m/s.", ["c = 3.0 × 10⁸ m s⁻¹"])
    assert introduced == ["3.0e9"] and dropped == ["3.0 × 10⁸"]


def _report(text):
    rid, req, task = "rep-p", "req", "task"
    return SpecialistReport(report_id=rid, request_id=req, task_id=task, agent_id="physics-specialist", subject="Physics", task_type="short_answer",
                            original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(request_id=req, task_id=task, report_id=rid, agent_id="physics-specialist", subject="Physics",
                                                task_type="short_answer", claim_id="s1.1", claim_text=text, claim_role="quantitative")])


def _synthesis(text):
    claims = [SynthesizedClaim(claim_id="syn-1", text=text, source_claim_ids=["s1.1"], transformation="paraphrased")]
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=["rep-p"], claims=claims,
                     text=text, text_sha256=sha256_hex(text), created_at="2026-10-12T00:00:00Z")


def test_the_ledger_compares_scientific_figures():
    source = _report("The photon energy is E = 3.3 × 10⁻¹⁹ J.")
    same = check_synthesis_ledger([source], _synthesis("Each photon carries 3.3e-19 J."))
    assert not any(f.code in ("INT-LEDGER-023", "INT-LEDGER-024") for f in same)
    changed = check_synthesis_ledger([source], _synthesis("Each photon carries 3.3e-18 J."))
    assert any(f.code == "INT-LEDGER-023" and "3.3e-18" in f.message for f in changed)


def test_superscript_digits_never_raise_out_of_the_ledger():
    # '¹⁹'.isdigit() is True but int('¹⁹') raises: the pairing reader used to raise on any superscript exponent
    source = _report("In March 2026 the charge was 1.6 × 10⁻¹⁹ C and the mass m² was 4 kg².")
    out = check_synthesis_ledger([source], _synthesis("In March 2026 the charge was 1.6 × 10⁻¹⁹ C and the mass m² was 4 kg²."))
    assert not any(f.severity == "error" for f in out)
