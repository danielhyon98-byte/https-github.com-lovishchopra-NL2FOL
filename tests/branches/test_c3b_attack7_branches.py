"""Attack round 7 of the c3b fix: the Geography branch items the round reproduced on the working tree that this fix closes, each
with its expected value fixed here (the inputs are the attack's own).

* A figure stated with its working in brackets is decided whatever stands between them: a unit written with superscripts
  ("23.6 m³ s⁻¹ (5.4 + 16.2)"), words of the sentence ("5.2 m³ s⁻¹ above its base flow (5.4 − 1.2)"), a year ("213 PJ in 2025
  (0.22 × 1,050)"), nested brackets ("24 ((24 + 22 + 23) ÷ 3)"), a percentage of a figure ("251 PJ (22% of 1,050 PJ)"). The
  correct twins are not named.
* A bracket on the next line, or one that more working operates on ("× 100\\n(51.2 − 7.0) ÷ 7.0 × 100"), holds no stated figure's
  parts; a year before a bracket is a date, never its result.
* Language B: a stated count of listed connectors is read with words between the noun and the list ("four connectors to
  organise the argument: ...").
* The case-figure anchor (``geography._anchor``) reads the clause bounds once per sentence: linear on one long sentence (it was
  quadratic: 0.69 s at 200 kB for the anchor alone).

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import geography as G
from epinoic_logic.branches import worked as W

from . import d9d10_hub as H
from . import d9d10_texts as T


def _text(record: str) -> str:
    return getattr(T, record.split("/")[1].upper().replace("-", "_"))


def _new_counterexamples(record: str, sentence: str) -> list:
    base = H.recorded(record)
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    base_bad = [c for c in H.checks(base) if c[1] == "COUNTEREXAMPLE"]
    return [c for c in H.checks(rc) if c[1] == "COUNTEREXAMPLE" and c not in base_bad]


@pytest.mark.parametrize("record, wrong, right", [
    ("c2/ge-p9c", "The two peak discharges add up to 23.6 m³ s⁻¹ (5.4 + 16.2).",
     "The two peak discharges add up to 21.6 m³ s⁻¹ (5.4 + 16.2)."),
    ("c2/ge-p9c", "Storm 1's peak discharge was 5.2 m³ s⁻¹ above its base flow (5.4 − 1.2).",
     "Storm 1's peak discharge was 4.2 m³ s⁻¹ above its base flow (5.4 − 1.2)."),
    ("c2/ge-p9c", "Storm 2's peak was 14.1 m³ s⁻¹ above its base flow (16.2 − 1.1).",
     "Storm 2's peak was 15.1 m³ s⁻¹ above its base flow (16.2 − 1.1)."),
    ("c2/ge-t15", "Natural gas supply rose from 123 PJ in 2005 (0.15 × 820) to 213 PJ in 2025 (0.22 × 1,050).",
     "Natural gas supply rose from 123 PJ in 2005 (0.15 × 820) to 231 PJ in 2025 (0.22 × 1,050)."),
    ("c2/ge-t15", "In 2025 natural gas supplied 251 PJ (22% of 1,050 PJ).", "In 2025 natural gas supplied 231 PJ (22% of 1,050 PJ)."),
    ("c1/ge-t14", "In your table, the mean EQS of Sites 1 to 3 is 24 ((24 + 22 + 23) ÷ 3).",
     "In your table, the mean EQS of Sites 1 to 3 is 23 ((24 + 22 + 23) ÷ 3)."),
])
def test_a_figure_with_its_working_in_brackets_is_decided(record, wrong, right):
    assert len(_new_counterexamples(record, wrong)) == 1, wrong
    assert _new_counterexamples(record, right) == [], right


@pytest.mark.parametrize("text", [
    "(b) Percentage change = (final − initial) ÷ initial × 100\n(51.2 − 7.0) ÷ 7.0 × 100 = 631.4%",
    "The 2025 profit before interest and tax ($380,000 ÷ $336,000 × 100) rose.",
    "so v² = 2(3.0 × 10⁻² J)/(0.50 kg) = 0.12 m² s⁻²",
])
def test_a_bracket_that_is_more_working_or_follows_a_year_is_no_stated_figure(text):
    assert W._breakdown_reads(text) == []


def test_the_case_figure_anchor_is_linear_on_one_long_sentence():
    def run(n: int) -> float:
        text = ("Haiti 3 deaths Kobe 4 deaths " * (n // 28 + 1))[:n]
        places = G._places(text)
        bounds = [i for i, c in enumerate(text) if c in ";\n"]
        t = time.perf_counter()
        for m in G._CASE_FIG_RE.finditer(text):
            G._anchor(text, m.start(), "", places, [], bounds)
        return time.perf_counter() - t
    small = min(run(25_000) for _ in range(2))
    large = min(run(200_000) for _ in range(2))
    assert large < max(0.05, small) * 16, (small, large)  # (a quadratic anchor gives about 64 for 8 times the text)


def test_a_stated_count_of_listed_connectors_is_read_after_words_before_the_list():
    # (Language B: up to six words may stand between "connectors" and the list's colon, attack round 7)
    wrong = 'The model uses four connectors to organise the argument: "Sin embargo", "Además" and "En primer lugar".'
    right = 'The model uses three connectors to organise the argument: "Sin embargo", "Además" and "En primer lugar".'
    assert len(_new_counterexamples("c2/sp-t15", wrong)) == 1
    assert _new_counterexamples("c2/sp-t15", right) == []
