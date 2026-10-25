"""B2 of the end-to-end run: twelve false INT-SUBJ-001 errors on correct work, in eight classes of misreading, each fixed at
its cause; every sentence quoted in the report gives no error now, and a wrong twin of each (the same construct, wrong)
still fails.

1. a count noun before an operator: '4 categories − 1 = 3' was read as '− 1 = 3' (the count is an operand);
2. mixed units: '4 min 30 s = (4 × 60 + 30) s' was cut to '30 s = …' (a compound quantity is the sum of its parts);
3. a value restated in brackets: '= 0.870 (87%)' was read as the product 0.870 × 87%;
4. a chain cut at an ellipsis: '= 2.084429… + 18.420681… = 20.505110…' (a numeral with a glued ellipsis is truncated:
   its half-width is a full unit in its last digit);
5. a figure from another chain: '0.1 pH unit' and '26%' (and '[1]', a mark annotation) were checked against the final
   value of an earlier chain (a restatement is of the same quantity, and of the chain in its own statement first);
6. bit groups: '1011 0110₂' is one binary numeral, not 1011 and 6;
7. a quoted failing test: '(2 <= 1) fails' asserts that the comparison does not hold;
8. a pair whose end is an expression: 'falls from $1.60 to $2.00 − $0.60 = $1.40' ends at $1.40, not $2.00.
"""
from __future__ import annotations

import pytest

from .argdiag_hub import deliver, findings
from .. import argdiag_cases as C

# (case, the quoted sentence's text as the answer writes it, its wrong twin, a fragment the twin's error quotes)
SENTENCES = [
    ("e2e-B2-bi", "The degrees of freedom are 4 categories − 1 = 3.", "The degrees of freedom are 4 categories − 1 = 4.", "4 categories − 1 = 4"),
    ("e2e-B2-ph", "4 min 30 s = (4 × 60 + 30) s = 270 s", "4 min 30 s = (4 × 60 + 20) s = 260 s", "4 min 30 s = (4 × 60 + 20) s"),
    ("e2e-B2-ph", "= 0.870 (87%)", "= 0.780 (78%)", "= 0.780"),
    ("e2e-B2-maa", "= 2.084429… + 18.420681… = 20.505110…", "= 2.084429… + 18.420681… = 21.505110…", "21.505110"),  # beyond τ = 1%
    ("e2e-B2-maa", "= 0.693147… / 2.050511… = 0.338036… months", "= 0.693147… / 2.050511… = 0.348036… months", "0.348036"),
    ("e2e-B2-ch", "Percentage increase = (1.259 − 1) × 100 = 25.9%, so about 26%", "Percentage increase = (1.259 − 1) × 100 = 25.9%, so about 36%", "36%"),
    ("e2e-B2-ess", "(1.259 − 1) × 100 = 25.9%, so about 26%", "(1.259 − 1) × 100 = 25.9%, so about 36%", "36%"),
    ("e2e-B2-ess", "(1.259 − 1) × 100 = 25.9%", "(1.259 − 1) × 100 = 35.9%", "35.9%"),
    ("e2e-B2-cs", "so 1011 0110₂ = B6₁₆", "so 1011 0110₂ = B7₁₆", "B7₁₆"),
    ("e2e-B2-cs", "(0110 1101₂ = 109)", "(0110 1101₂ = 119)", "119"),
    ("e2e-B2-cs", "the final test (2 <= 1) fails", "the final test (2 <= 3) fails", "2 <= 3"),
    ("e2e-B13-ec", "falls from $1.60 to $2.00 − $0.60 = $1.40", "falls from $1.60 to $2.00 + $0.60 = $2.60", "$2.00 + $0.60 = $2.60"),
]


def _errors(rc) -> list:
    return [f for f in findings(rc, "INT-SUBJ-001") if f.severity == "error"]


@pytest.mark.parametrize("case_id", sorted({c for c, *_ in SENTENCES} - {"e2e-B13-ec"}))
def test_the_b2_answers_carry_no_stem_error(case_id):
    assert _errors(deliver(case_id)) == [], case_id


def test_the_economics_pair_whose_end_is_an_expression_carries_no_error():
    assert not [f for f in _errors(deliver("e2e-B13-ec")) if "pair_direction" in f.message]


@pytest.mark.parametrize("case_id,sentence,twin,fragment", SENTENCES, ids=[f"{c}:{t[:24]}" for c, _s, t, _f in SENTENCES])
def test_the_wrong_twin_of_each_sentence_still_fails(case_id, sentence, twin, fragment):
    case = C.load_case(case_id)
    assert case["answer"].count(sentence) >= 1, sentence
    rc = deliver(case, answer=case["answer"].replace(sentence, twin, 1))
    assert any(fragment in f.message for f in _errors(rc)), [f.message[:160] for f in _errors(rc)]


def test_quote_them_exactly_asks_for_the_figures_as_written_not_exact_arithmetic():
    # 'quote them exactly' (e2e-B2-ess) qualifies the quoting: the CO₂ arithmetic keeps the tolerance of its written figures
    rc = deliver("e2e-B2-ess")
    assert not [f for f in _errors(rc) if "421 − 280" in f.message]
    case = C.load_case("e2e-B2-ess")
    wrong = case["answer"].replace("(421 − 280) ÷ 280 × 100 = 50.4%", "(421 − 280) ÷ 280 × 100 = 55.4%", 1)
    assert any("55.4%" in f.message for f in _errors(deliver(case, answer=wrong)))
