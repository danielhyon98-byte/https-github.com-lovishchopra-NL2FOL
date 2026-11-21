"""Attack round 6 of the c3b fix: the Geography and Language B false positives the round reproduced on the working tree, each with
its expected value fixed here (the inputs are the attack's own).

* Geography: a figure compared with another ("28 fewer than Site 1's 214", "6 below Site 1's 24", "3 above Site 7's 42", "9% of that
  at Site 1") and a figure after the change it measures in any tense ("falls by about 91%", "fell by about 39%", "an increase of about
  47%") are derived from cells, never cells of the table (the change and from-to checks decide them).
* Language B: a range written in words ("de 450 a 600", "entre 450 y 600", "between 450 and 600") is a bound, never the stated count;
  the stated count is the number words ("unas quinientas diez palabras"), checked against the measured count.
* A misread cell and a false count are still named.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from . import d9d10_hub as H
from . import d9d10_texts as T


def _text(record: str) -> str:
    return getattr(T, record.split("/")[1].upper().replace("-", "_"))


@pytest.mark.parametrize("record, sentence", [
    ("c1/ge-t14", "In your table, Site 2's count of 186 is 28 fewer than Site 1's 214."),
    ("c1/ge-t14", "In your table, Site 4's EQS of 18 is 6 below Site 1's 24."),
    ("c1/ge-t14", "In your table, Site 2's count of 186 is 28 lower than Site 1's 214."),
    ("c1/ge-t14", "In your table, Site 2 had 28 fewer pedestrians than Site 1 (186 against 214)."),
    ("c1/ge-t14", "In your table, Site 8's count of 45 is 3 above Site 7's 42."),
    ("c1/ge-t14", "In your table, the pedestrian count falls by about 91% from Site 1 to Site 10 (214 to 19)."),
    ("c1/ge-t14", "In your table, the pedestrian count at Site 10 (19) is 9% of that at Site 1 (214)."),
    ("c2/ge-t15", "According to the table, coal's share fell by about 39% (46% to 28%)."),
    ("c2/ge-t15", "According to the table, natural gas's share rose from 15% in 2005 to 22% in 2025, an increase of about 47%."),
])
def test_a_derived_figure_is_no_cell(record, sentence):
    base = H.recorded(record)
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    assert set(H.codes(rc)) <= set(H.codes(base)), H.codes(rc)
    base_bad = [c for c in H.checks(base) if c[1] == "COUNTEREXAMPLE"]
    assert [c for c in H.checks(rc) if c[1] == "COUNTEREXAMPLE" and c not in base_bad] == []


@pytest.mark.parametrize("record, sentence", [
    ("c1/ge-t14", "In your table, Site 2's count is 168."),
    ("c2/ge-t15", "According to the table, coal's share was 64% in 2025."),
])
def test_a_misread_cell_is_still_named(record, sentence):
    rc = H.recorded(record, _text(record) + "\n\n" + sentence)
    assert H.failed(rc, "INT-SUBJ-001"), H.codes(rc)


_WC = "Word count: about 513 including headline and byline (about 499 in the body), inside the 450–600 range."


@pytest.mark.parametrize("line", [
    "Recuento: unas quinientas diez palabras, dentro del límite de 450 a 600.",
    "Recuento: unas quinientas diez palabras, entre 450 y 600.",
    "Recuento de palabras: unas quinientas diez (el límite es de 450 a 600).",
    "Word count: about five hundred and ten words, between 450 and 600.",
])
def test_a_range_in_words_is_a_bound_and_the_number_words_are_the_count(line):
    text = _text("c2/sp-t15")
    assert _WC in text
    rc = H.recorded("c2/sp-t15", text.replace(_WC, line, 1))
    assert [c for c in H.checks(rc, "language-b-word-count") if c[1] == "COUNTEREXAMPLE"] == []
    assert [f.code for f in rc.findings if "lb_word_count" in f.message] == []


@pytest.mark.parametrize("line", ["Recuento: unas seiscientas cincuenta palabras, dentro del límite de 450 a 600.",
                                  "Word count: about 380, inside the 450–600 range."])
def test_a_false_count_beside_a_range_is_still_named(line):
    rc = H.recorded("c2/sp-t15", _text("c2/sp-t15").replace(_WC, line, 1))
    assert ("language-b-word-count-1", "COUNTEREXAMPLE") in H.checks(rc, "language-b-word-count")


@pytest.mark.parametrize("line, holds", [
    ("Excess discharge = 5.4 − 1.2 = 5.2 m³ s⁻¹.", False),
    ("Storm 2 excess discharge = 16.2 − 1.1 = 14.1 m³ s⁻¹", False),
    ("Excess = 5.4 + 1.2 = 7.6 m³ s⁻¹", False),
    ("Excess = 5.4 − 1.2 = 5.2 m s⁻¹", False),
    ("Excess = 5.4 m³ s⁻¹ − 1.2 m³ s⁻¹ = 5.2 m³ s⁻¹", False),
    ("Excess discharge = 5.4 − 1.2 = 4.2 m³ s⁻¹.", True),
    ("Excess = 5.4 m³ s⁻¹ − 1.2 m³ s⁻¹ = 4.2 m³ s⁻¹", True),
])
def test_a_chain_whose_result_carries_a_compound_unit_is_checked(line, holds):
    """The unit words of one figure are one compound unit ("m³ s⁻¹"): the chain is read, and a false result is named."""
    rc = H.recorded("c2/ge-p9c", _text("c2/ge-p9c") + "\n\n" + line)
    named = [f for f in rc.findings if f.code == "INT-SUBJ-001" and "worked_arithmetic" in f.message and line.split("=")[1].strip()[:5] in f.message]
    assert (named == []) is holds, H.codes(rc)


@pytest.mark.parametrize("line, holds", [("Ten sites at 100 m intervals cover 1,200 m of the main road.", False),
                                         ("Ten sites at 100 m intervals cover 900 m of the main road.", True)])
def test_the_length_the_sites_cover_is_the_span_of_the_distance_column(line, holds):
    rc = H.recorded("c1/ge-t14", _text("c1/ge-t14") + "\n\n" + line)
    assert ("geography-transect-2", "ENTAILED" if holds else "COUNTEREXAMPLE") in H.checks(rc, "geography-transect")


@pytest.mark.parametrize("line, holds", [
    ("Base flow fell from 1.2 m³ s⁻¹ before Storm 1 to 1.1 m³ s⁻¹ before Storm 2, a fall of about 18%.", False),
    ("Base flow fell from 1.2 m³ s⁻¹ before Storm 1 to 1.1 m³ s⁻¹ before Storm 2, a fall of about 8%.", True),
])
def test_a_from_to_pair_at_points_before_or_after_is_checked(line, holds):
    rc = H.recorded("c2/ge-p9c", _text("c2/ge-p9c") + "\n\n" + line)
    assert ("geography-from-to-percent-1", "ENTAILED" if holds else "COUNTEREXAMPLE") in H.checks(rc, "geography-from-to-percent")
