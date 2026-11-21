"""Attack round 2 of the c3b fix: the paths, branches and correct-work findings the round reproduced on the working tree, each with its
expected value fixed here.

* Paths: a claim whose text the reader cannot read (a bidi override run) never shows a success status on the outcome display (the
  composer fails closed like the fallback and the port); a specialist report's claims are read by ``claim_text``; ``label_on_content``
  is linear in a run of marks.
* Branches (D9/D10): the Geography and Language B builds are cached by the content of what they read (a cache keyed by ids served one
  supplied table's verdict for another's figures); a Language B address-form example must be the production's own words; the Language B
  word-count and figure readers are linear; every Language B and ab initio course routes to the language_b branch; a capitalised Spanish
  number word that opens a sentence is read at its place.
* Correct work: a denary result of decimal arithmetic beside a binary numeral keeps its decimal reading.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters.self_report import label_on_content
from epinoic_logic.branches import RouterHub, language_b
from epinoic_logic.branches.spanish_lexicon import spanish_number_figures
from epinoic_logic.translate.outcome import _self_report_claim
from epinoic_logic.translate.subjects import resolve_profile

from . import d9d10_hub as H


# ------------------------------------------------------------------------------------------------------------------ paths
@pytest.mark.parametrize("text", [
    "If x > 2 and y > x then y > 2. \u202edeifirev\u202c",
    "\u202edeifirev\u202c If x > 2 and y > x then y > 2.",
    "If x > 2 and y > x then y > 2.\n\u202edeifirev\u202c",
])
def test_a_claim_the_reader_cannot_read_never_shows_success(text):
    assert _self_report_claim(text) is True


def test_a_plain_relation_still_shows_its_engine_status():
    assert _self_report_claim("If x > 2 and y > x then y > 2.") is False


def test_label_on_content_is_linear_in_a_run_of_marks():
    base = "The treaty was signed in 1919.\n\n"
    t0 = time.perf_counter()
    assert label_on_content(base + "✓ " * 2000) is True
    small = time.perf_counter() - t0
    t0 = time.perf_counter()
    assert label_on_content(base + "✓ " * 16000) is True
    large = time.perf_counter() - t0
    # eight times the marks: a quadratic reader took about sixty times as long; a linear one about eight
    assert large < max(2.0, 20 * small), (small, large)


# ------------------------------------------------------------------------------------------------------------------ branches
_TABLE = "Site | Distance (m) | Mean pedestrian count | EQS\n1 | 0 | 214 | 24\n4 | 300 | {n} | 18\n5 | 400 | 88 | 15"


def test_a_geography_build_is_not_served_from_another_supplied_tables_cache():
    ans = "According to your table, Site 4 had a mean pedestrian count of 97 per 10 minutes."
    good = ("doc-sites", "My fieldwork data", "Student", _TABLE.format(n=97))
    bad = ("doc-sites", "My fieldwork data", "Student", _TABLE.format(n=79))
    rc = H.through_hub(ans, "Describe Site 4.", *H.GEO, task_type="short_answer", docs=(good,))
    assert H.checks(rc, "geography-supplied") == [("geography-supplied-figure-1", "ENTAILED")]
    rc = H.through_hub(ans, "Describe Site 4.", *H.GEO, task_type="short_answer", docs=(bad,))
    assert H.checks(rc, "geography-supplied") == [("geography-supplied-figure-1", "COUNTEREXAMPLE")]
    assert [f.code for f in rc.findings if f.code == "INT-SUBJ-001"] == ["INT-SUBJ-001"]


def test_the_language_b_cache_key_holds_the_supplied_texts_content():
    a = H.report(*H.SPB, "1. Según el texto, en 2015 quedaban 212 vecinos.", task_type="reading_comprehension",
                 docs=(("doc-v", "Artículo", "A", "En 2015 solo quedaban 212 vecinos."),))
    b = H.report(*H.SPB, "1. Según el texto, en 2015 quedaban 212 vecinos.", task_type="reading_comprehension",
                 docs=(("doc-v", "Artículo", "A", "En 2015 solo quedaban 312 vecinos."),))
    assert a.report_id == b.report_id
    assert language_b._inputs_key(a, "q") != language_b._inputs_key(b, "q")
    assert language_b._inputs_key(a, "q") != language_b._inputs_key(a, "another request")


def test_an_address_form_example_found_nowhere_in_the_model_is_never_a_satisfied_check():
    answer, *_ = H.RECORDED["c2/sp-t15"]
    rc = H.recorded("c2/sp-t15", answer + '\n\nThe model addresses its readers as vosotros ("¿Y vosotros qué opináis?").')
    got = dict(H.checks(rc, "language-b-address-form"))
    assert got == {"language-b-address-form-1": "COUNTEREXAMPLE"}
    assert "INT-SUBJ-004" in H.codes(rc, "warning")
    rc = H.recorded("c2/sp-t15", answer + '\n\nThe model addresses its readers as tú ("¿Y tú qué opinas?").')
    assert dict(H.checks(rc, "language-b-address-form")) == {"language-b-address-form-1": "ENTAILED"}


@pytest.mark.parametrize("unit", ["The text has 300 words. ", '"de" la que "', "Word count: about 513 words. "])
def test_the_language_b_pack_is_linear_in_the_answer(unit):
    from epinoic_logic.branches.language_b import LanguageBPack

    def run(n):
        text = (unit * (n // len(unit) + 1))[:n]
        rep = H.report(*H.SPB, text, task_type="reading_comprehension", docs=(("doc-v", "Artículo", "A", "En 2015 solo quedaban 212 vecinos."),),
                       claims=[dict(claim_id="c1", claim_text=text[:3000], claim_role="point", materiality="material")])
        rep = rep.model_copy(update={"report_id": f"rep-{n}-{len(unit)}"})
        t0 = time.perf_counter()
        p = LanguageBPack()
        p.checks(rep, "Read the article and answer the questions.")
        p.formal_checks_for(rep, "Read the article and answer the questions.")
        return time.perf_counter() - t0
    small, large = run(12_500), run(100_000)
    assert large < max(3.0, 24 * small), (small, large)


@pytest.mark.parametrize("label", ["English B", "English B HL", "Arabic B", "Japanese B", "Hindi B", "Español B", "Lengua B: Español",
                                   "Language acquisition: Spanish", "French ab initio", "Language B: Spanish"])
def test_every_language_b_course_routes_to_the_language_b_branch(label):
    assert resolve_profile(label).key == "language_b"
    assert RouterHub(signing_key=H.KEY, config=H.CFG).branch_for(label) == "language_b"


@pytest.mark.parametrize("label,key", [("English A: Literature", "english_a_literature"), ("English", "english"),
                                       ("Spanish A: Literature", "language_a_other"), ("Geografía", "geography"), ("Geography", "geography")])
def test_language_a_and_other_labels_keep_their_profiles(label, key):
    assert resolve_profile(label).key == key


@pytest.mark.parametrize("text,value", [("Doscientos sesenta y ocho personas viven hoy.", "268"),
                                        ("Mil doscientos cincuenta habitantes tenía Valdeoca en 1960.", "1250"),
                                        ("1. Mil doscientos cincuenta habitantes en 1960", "1250"),
                                        ("Llegaron tarde. Quince alumnos volvieron.", "15")])
def test_a_capitalised_spanish_number_word_opening_a_sentence_is_read(text, value):
    assert [v for _a, _b, v in spanish_number_figures(text)] == [value]


def test_a_capitalised_once_is_english():
    assert spanish_number_figures("Once the war ended, trade grew.") == []


def test_a_capitalised_spanish_figure_equal_to_the_text_draws_no_error():
    answer, *_ = H.RECORDED["c1/sp-t14"]
    rc = H.recorded("c1/sp-t14", answer + "\n\nDoscientos sesenta y ocho personas viven hoy en Valdeoca, según el texto.")
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001" and "Doscientos" in (f.message or "")]
    assert all(s == "ENTAILED" for c, s in H.checks(rc, "language-b-supplied-figure"))


# ------------------------------------------------------------------------------------------------------------------ correct work
@pytest.mark.parametrize("text", ["The binary number 1011 is 11 in denary, since 8 + 2 + 1 = 11.",
                                  "The binary number 1011 equals 8 + 0 + 2 + 1 = 11 in denary.",
                                  "The binary number 1011 is 8 + 2 + 1 = 11 in denary.",
                                  "The binary number 1011 is 11 in denary, since 1×8 + 0×4 + 1×2 + 1×1 = 11."])
def test_a_denary_result_beside_a_binary_numeral_is_no_false_error(text):
    rc = H.through_hub(text, "Convert 1011 from binary to denary.", "Computer Science", "cs-specialist", "short_answer")
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"], [f.message for f in rc.findings]


def test_a_wrong_denary_value_is_still_an_error():
    rc = H.through_hub("The binary number 1011 is 12 in denary, since 1×8 + 0×4 + 1×2 + 1×1 = 12.", "Convert 1011 from binary to denary.",
                       "Computer Science", "cs-specialist", "short_answer")
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001"]


# ------------------------------------------------------------------------------------------------------------------ Geography fold words
def test_a_fold_word_against_the_ratio_the_line_works_out():
    answer, *_ = H.RECORDED["c2/ge-p9c"]
    old = "This is a threefold increase (16.2 ÷ 5.4 = 3.0)."
    assert old in answer
    rc = H.recorded("c2/ge-p9c", answer.replace(old, "This is a fourfold increase (16.2 ÷ 5.4 = 3.0)."))
    assert ("geography-fold-1", "COUNTEREXAMPLE") in H.checks(rc, "geography-fold")
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001" and "geo_fold" in (f.message or "")]
    rc = H.recorded("c2/ge-p9c")
    assert H.checks(rc, "geography-fold") == [("geography-fold-1", "ENTAILED")]
