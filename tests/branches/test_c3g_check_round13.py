"""Check round 13 of the c3g follow-up on the branch readers, each expected value fixed here:

1. Regression of the c3g insertion reader: a row named in an apposition, a bracket or a pair of dashes that IS the subject's referent
   ("One source, natural gas, ...", "The quietest site (site 10) ...", "The market leader, Alba, ...") keeps naming the figure's row,
   so a wrong figure keeps its COUNTEREXAMPLE and a correct one its ENTAILED, as at 08c4a36b; the insertions that hold no subject
   ("while coal declined", "coal aside", "as retail use fell", "with pedestrian numbers high") stay blanked.
2. Language B dating: a year of another clause or event (a coordinated clause, a relative clause, a fronted phrase of its own) dates
   no figure ("6. La fibra llegó en 2021 y la escuela reabrió con catorce alumnos." is correct); a year fronted before the line's first
   verb dates every clause it heads.
3. Language B present figures: a line of the present ("Hoy ...", "Actualmente ...") is read against the text's present figure of the
   place, another population noun included, even when the text states the line's figure for another year.
4. Geography from-to pairs with a scale word, and a request's from-to pair across its two labels ("Base flow fell from 1.2 to 1.0 m³ s⁻¹"), ("from 21.4 million to 28.0 million"): the second figure is read against the later year.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from . import d9d10_hub as H


def _new(name: str, sentence: str):
    base = H.RECORDED[name][0]
    b = H.recorded(name)
    before = set(H.checks(b))
    codes0 = {f.code for f in b.findings if f.severity in ("error", "warning")}
    rc = H.recorded(name, base + "\n\n" + sentence)
    return [x for x in H.checks(rc) if x not in before], {f.code for f in rc.findings if f.severity in ("error", "warning")} - codes0


# ------------------------------------------------------------------------------------------------ 1. referent appositions
GE15_WRONG = [
    "One source, natural gas, rose from 15% to 31%.", "The largest source in 2025, coal, supplied 27% of energy.",
    "One source (natural gas) supplied 31% of energy in 2025.", "The fuel — natural gas — supplied 31% in 2025.",
    "In 2025 the share of one fuel, natural gas, was 31%.",
]
GE15_RIGHT = [
    "One source, natural gas, rose from 15% to 22%.", "The largest source in 2025, coal, supplied 28% of energy.",
    "One source (natural gas) supplied 22% of energy in 2025.", "In 2025 the share of one fuel, natural gas, was 22%.",
]


@pytest.mark.parametrize("sentence", GE15_WRONG)
def test_a_wrong_figure_whose_row_is_an_apposition_is_named(sentence):
    new, codes = _new("c2/ge-t15", sentence)
    assert any(st == "COUNTEREXAMPLE" and cid.startswith("core-figure") for cid, st in new), (sentence, new)
    assert "INT-SUBJ-001" in codes, (sentence, codes)


@pytest.mark.parametrize("sentence", GE15_RIGHT)
def test_a_correct_figure_whose_row_is_an_apposition_is_entailed(sentence):
    new, codes = _new("c2/ge-t15", sentence)
    figs = [st for cid, st in new if cid.startswith("core-figure")]
    assert figs and all(st == "ENTAILED" for st in figs), (sentence, new)
    assert "INT-SUBJ-001" not in codes, (sentence, codes)


@pytest.mark.parametrize("sentence,ok", [
    ("Energy supply per person, while coal declined, was about 11.8 GJ in 2025.", False),
    ("Energy supply per person, while coal declined, was about 42 GJ in 2025.", True),
    ("Energy supply per person, coal aside, was about 11.8 GJ in 2025.", False),
])
def test_an_insertion_that_holds_no_subject_stays_blanked(sentence, ok):
    new, codes = _new("c2/ge-t15", sentence)
    assert ("geography-table-derived-5", "ENTAILED" if ok else "COUNTEREXAMPLE") in new, (sentence, new)
    assert ("INT-SUBJ-004" in codes) is (not ok), (sentence, codes)


@pytest.mark.parametrize("sentence", ["The busiest site, site 1, had a pedestrian count of 186.",
                                      "The quietest site (site 10) had a pedestrian count of 23.", "One site, site 4, had an EQS of 15.",
                                      "The pedestrian count at site 4, as retail use fell, was 60.",
                                      "At site 2 the EQS, with pedestrian numbers high, was 186."])
def test_a_site_table_figure_is_read_against_its_row(sentence):
    new, codes = _new("c1/ge-t14", sentence)
    assert ("geography-supplied-figure-1", "COUNTEREXAMPLE") in new and "INT-SUBJ-004" in codes, (sentence, new, codes)


DOC = ("doc-firms", "Market shares, 2024", "practice data",
       "Market share by firm (%)\n\nFirm | 2020 | 2024\nAlba | 40 | 34\nBrisa | 25 | 31\nCorvo | 20 | 18\nDelta | 15 | 17\n")
Q = "Using the supplied table, describe how market shares changed between 2020 and 2024."


@pytest.mark.parametrize("subject,agent", [("Economics", "economics-specialist"),
                                           ("Business Management", "business-management-specialist")])
@pytest.mark.parametrize("sentence,wrong", [("The market leader, Alba, had a share of 31% in 2024.", True),
                                            ("The market leader (Alba) had a share of 31% in 2024.", True),
                                            ("The market leader, Alba, had a share of 34% in 2024.", False),
                                            ("One firm, Brisa, rose from 25% to 40%.", True)])
def test_the_shared_table_reader_names_the_apposition_row(subject, agent, sentence, wrong):
    rc = H.through_hub("1. " + sentence, Q, subject, agent, "short_answer", (DOC,))
    figs = [st for cid, st in H.checks(rc) if cid.startswith("core-figure")]
    assert figs, (sentence, H.checks(rc))
    assert ("COUNTEREXAMPLE" in figs) is wrong and ("INT-SUBJ-001" in H.codes(rc)) is wrong, (sentence, H.checks(rc), H.codes(rc))


# ------------------------------------------------------------------------------------------------ 2-3. Language B
@pytest.mark.parametrize("sentence", [
    "6. La fibra llegó en 2021 y la escuela reabrió con catorce alumnos.", "6. La escuela, que cerró en 2009, reabrió con catorce alumnos.",
    "6. La escuela cerró en 2009; reabrió con catorce alumnos.", "6. Tras la llegada de la fibra en 2021, la escuela reabrió con catorce alumnos.",
    "6. Hoy viven en Valdeoca 268 personas.", "6. Actualmente Valdeoca tiene 268 habitantes.",
    "6. En 1960 había una escuela con más de cien alumnos y el pueblo tenía 1.250 habitantes.",
])
def test_a_correct_figure_is_never_charged_by_another_clause_year(sentence):
    new, codes = _new("c1/sp-t14", sentence)
    assert not any(st == "COUNTEREXAMPLE" for _cid, st in new), (sentence, new)
    assert "INT-SUBJ-001" not in codes, (sentence, codes)


@pytest.mark.parametrize("sentence", [
    "6. Hoy viven en Valdeoca 212 personas.", "6. Actualmente Valdeoca tiene 212 habitantes.",
    "6. Según el texto, hoy viven en Valdeoca 212 personas.", "6. En 1960 la escuela tenía catorce alumnos.",
    "6. En 1960 había una escuela con más de cien alumnos y el pueblo tenía 268 habitantes.",
    "6. La fibra llegó en 2021 y la escuela reabrió con cien alumnos.",
])
def test_a_wrong_figure_of_the_text_is_named(sentence):
    new, codes = _new("c1/sp-t14", sentence)
    assert any(st == "COUNTEREXAMPLE" for _cid, st in new) and "INT-SUBJ-001" in codes, (sentence, new, codes)


# ------------------------------------------------------------------------------------------------ 4. from-to with a scale word
@pytest.mark.parametrize("sentence,wrong", [("The population grew from 21.4 million to 28.0 million.", True),
                                            ("The population, while energy use rose, grew from 21.4 million to 28.0 million.", True),
                                            ("The population grew from 21.4 million to 24.9 million.", False)])
def test_a_from_to_pair_with_a_scale_word_reads_both_years(sentence, wrong):
    new, codes = _new("c2/ge-t15", sentence)
    figs = [st for cid, st in new if cid.startswith("core-figure")]
    assert len(figs) == 2, (sentence, new)
    assert ("COUNTEREXAMPLE" in figs) is wrong and ("INT-SUBJ-001" in codes) is wrong, (sentence, new, codes)


# ------------------------------------------------------------------------------------------------ 5. a request's from-to pair
@pytest.mark.parametrize("sentence,wrong", [("Base flow fell from 1.2 to 1.0 m³ s⁻¹ between the two storms.", True),
                                            ("Base flow fell from 1.2 to 1.1 m³ s⁻¹ between the two storms.", False)])
def test_a_from_to_pair_of_request_figures_reads_the_second_label(sentence, wrong):
    new, codes = _new("c2/ge-p9c", sentence)
    req = [st for cid, st in new if cid.startswith("geography-request-figure")]
    assert (req == ["COUNTEREXAMPLE"]) is wrong and ("INT-SUBJ-004" in codes) is wrong, (sentence, new, codes)
    assert not wrong or req, (sentence, new)


# ------------------------------------------------------------------------------------------------ 6. a year in Spanish words
@pytest.mark.parametrize("sentence,wrong", [("6. La escuela llevaba cerrada desde dos mil diez.", True),
                                            ("6. La escuela llevaba cerrada desde dos mil nueve.", False)])
def test_a_year_in_spanish_words_after_desde_is_read_whole(sentence, wrong):
    new, _codes = _new("c1/sp-t14", sentence)
    sts = [st for _cid, st in new]
    assert sts and ("COUNTEREXAMPLE" in sts) is wrong, (sentence, new)


# ------------------------------------------------------------------------------------------------ 7. a row named by its own words
@pytest.mark.parametrize("sentence,wrong", [("In 2025, 46% of energy was imported.", True),
                                            ("In 2025, 54% of energy was imported.", False),
                                            ("In 2005, 38% of energy supply was imported.", False)])
def test_a_row_named_by_the_words_only_it_holds_is_read(sentence, wrong):
    new, codes = _new("c2/ge-t15", sentence)
    figs = [st for cid, st in new if cid.startswith("core-figure")]
    assert figs and ("COUNTEREXAMPLE" in figs) is wrong and ("INT-SUBJ-001" in codes) is wrong, (sentence, new, codes)
