"""Check round 13 of the c3g follow-up on the ledger (expected values fixed here): two recorded round-7 synthesis claims drew a new
INT-LEDGER-029 on the c3g working tree, though neither states a verification status of the answer:

* r7 mai-t13 s1 (a marking synthesis): '... after 11 complete years the value is still below 6000 (4000(1.036)^11 = 5902.25) ...':
  'complete' is an ordinary adjective after a count and 'below' compares a figure; the computation is shown, no verdict is wider;
* r7 maa-p7b-s3: "The Physics report's values agree with this answer (its λ = ... matches k = ...)": a named peer report's stated
  values compared with the answer's, the computation shown: a material claim (boundary (b)).

Their self-reporting twins stay named. And the number-word reader read "desde dos mil diez" as 2 and 1010 (the small number taken
after a word of quantity, "desde"): a small number before "mil" is read with it, 2010."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.integrity import ledger as L

DATA = Path(__file__).resolve().parent / "data" / "r7_syntheses.json"


def _claim(task: str, claim_id: str) -> str:
    records = json.loads(DATA.read_text(encoding="utf-8"))[task]
    items = records if isinstance(records, list) else [records]

    def walk(x):
        if isinstance(x, dict):
            if x.get("claim_id") == claim_id and isinstance(x.get("text"), str):
                return x["text"]
            for v in x.values():
                got = walk(v)
                if got:
                    return got
        elif isinstance(x, list):
            for v in x:
                got = walk(v)
                if got:
                    return got
        return None
    text = walk(items)
    assert text, (task, claim_id)
    return text


@pytest.mark.parametrize("task,claim_id", [("mai-t13", "s1"), ("p7b", "maa-p7b-s3")])
def test_the_recorded_r7_syntheses_state_no_verification_status(task, claim_id):
    text = _claim(task, claim_id)
    assert L._self_report_sentences(text) == [], (task, claim_id)


@pytest.mark.parametrize("sentence", [
    "After 11 complete years the value is still below 6000 (4000(1.036)^11 = 5902.25) ✓, and so is every other line here.",
    "The reviewer agrees with this answer (2 + 2 = 4).",
    "This synthesis has been verified.",
])
def test_their_self_reporting_twins_are_named(sentence):
    assert L._self_report_sentences(sentence), sentence


@pytest.mark.parametrize("text, figures", [("desde dos mil diez", ["2010"]), ("desde dos euros", ["2"]),
                                           ("más de dos mil alumnos", ["2000"])])
def test_a_small_number_before_mil_is_read_with_it(text, figures):
    assert [v for _a, _b, v in L._spanish_word_figures(text)] == figures
