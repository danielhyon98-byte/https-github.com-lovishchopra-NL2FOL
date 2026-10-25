"""B16, grounding half: a premise interval grounds when it is the interval a figure of the excerpt states at its WRITTEN
precision: a figure stated as rounded ("≈ 1.55"), or the result of a written calculation ("10^(−8.2) = 6.31 × 10⁻⁹",
"… = 1.259"), read to half a unit of its last written place, in superscript and caret notation alike, at the closure that
interval implies or closed at both ends (whether the claim may use it is the precision step's decision). A wider, narrower
or shifted interval still fails, and so does an interval in place of a figure given exactly (the exactness rule). An
excerpt quotes a figure when it covers its sign, numeral and scale word; the unit after it may stand outside."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.grounding import check_problem_grounding

H = ("The hydrogen-ion concentration at pH 8.2 is [H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³, and at pH 8.1 it is [H⁺] = 10^(−8.1) = "
     "7.94 × 10⁻⁹ mol dm⁻³. The ratio is 7.94 × 10⁻⁹ ÷ 6.31 × 10⁻⁹ = 1.259 (this is 10^0.1).")
CARET = "[H+] = 10^(-8.2) = 6.31×10^-9 mol dm-3."
APPROX = "From January to July prices multiplied by ≈ 1.55 each month."


def _interval(text: str, excerpt: str, lo: str, hi: str, lo_op: str = "ge", hi_op: str = "lt"):
    doc = SuppliedText(document_id="doc", title=None, author=None, text=text)
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": "the value as the text states it"}],
        "premises": [{"id": "Q", "expr": {"op": "and", "args": [{"op": lo_op, "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": lo}},
                                                                {"op": hi_op, "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": hi}}]},
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": excerpt}]}}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0"}}}})
    grounded, checks = check_problem_grounding(problem, [doc])
    return grounded.premises[0].grounding.verified, [c for c in checks if c.method == "figures_in_excerpt"]


def _assignment(text: str, excerpt: str, value: str, meaning: str = "the figure as the text states it"):
    doc = SuppliedText(document_id="doc", title=None, author=None, text=text)
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": meaning}],
        "premises": [{"id": "Q", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": value}},
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": excerpt}]}}],
        "conclusion": {"id": "C", "expr": {"op": "ne", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0"}}}})
    grounded, _checks = check_problem_grounding(problem, [doc])
    return grounded.premises[0].grounding.verified


@pytest.mark.parametrize("text, excerpt, lo, hi", [
    (H, "10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³", "0.000000006305", "0.000000006315"),   # q_h82
    (H, "10^(−8.1) = 7.94 × 10⁻⁹ mol dm⁻³", "0.000000007935", "0.000000007945"),   # q_h81
    (H, "= 1.259 (this is 10^0.1)", "1.2585", "1.2595"),                             # q_ratio
    (CARET, "6.31×10^-9", "0.000000006305", "0.000000006315"),                     # caret notation, the unit outside the excerpt
    (APPROX, "≈ 1.55 each month", "1.545", "1.555"),                                 # after "≈"
])
def test_the_half_unit_enclosure_of_a_stated_figure_grounds(text, excerpt, lo, hi):
    verified, [check] = _interval(text, excerpt, lo, hi)
    assert verified is True and check.verified is True and "half a unit" in check.detail


@pytest.mark.parametrize("text, excerpt, lo, hi", [(H, "= 1.259 (this is 10^0.1)", "1.2585", "1.2595"), (APPROX, "≈ 1.55 each month", "1.545", "1.555")])
def test_the_enclosure_closed_at_both_ends_grounds_and_one_open_at_its_included_end_does_not(text, excerpt, lo, hi):
    assert _interval(text, excerpt, lo, hi, "ge", "le")[0] is True
    assert _interval(text, excerpt, lo, hi, "gt", "lt")[0] is False      # narrower by its end point: not what the text states


@pytest.mark.parametrize("lo, hi", [("1.25", "1.27"), ("1.2580", "1.2595"), ("1.2585", "1.2596"), ("1.2575", "1.2585")])
def test_a_wider_narrower_or_shifted_interval_still_fails(lo, hi):
    assert _interval(H, "= 1.259 (this is 10^0.1)", lo, hi)[0] is False


def test_an_interval_in_place_of_a_figure_given_exactly_still_fails():
    assert _interval("The ratio is 1.259.", "The ratio is 1.259", "1.2585", "1.2595")[0] is False
    assert _assignment("The ratio is 1.259.", "The ratio is 1.259", "1.259") is True   # the figure itself grounds


def test_an_excerpt_must_cover_the_sign_numeral_and_scale_word_but_not_the_unit():
    assert _assignment("The car travelled 120 km in 8 hours.", "travelled 120", "120", "the distance travelled (km)") is True
    assert _assignment("The temperature fell to −8.2 degrees.", "8.2 degrees", "-8.2") is False       # the sign is part of the figure
    assert _assignment("Revenue rose to £2.5 million.", "£2.5", "2500000", "revenue (£)") is False    # so is its scale word
    assert _assignment("Revenue rose to £2.5 million.", "£2.5 million", "2500000", "revenue (£)") is True
