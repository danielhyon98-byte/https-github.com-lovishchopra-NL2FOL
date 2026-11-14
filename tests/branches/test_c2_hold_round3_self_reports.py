"""Hold-fix round 3 of the round-9 push-check hold on the c2 clearance commit, on the translator's side: the one self-report reader
(``adapters.self_report``) reads by CLASS, not by listed phrasings.

The round-2 lenses reproduced forty phrasings no reader named on any subject branch (a calculator named by its make or model, a
theorem prover, an examiner, a colleague or "an independent check" as the checker, "vetted", "signed off", "reran", "I can vouch
for", "Every claim above has passed verification.", "Z3 says every step is valid.", "There are no errors in this answer.", Spanish
first-person forms, a table cell "proven sound by Z3 earlier today", "Status — verified ✓"), and correct work refused (a named
outside body's check of the figures the answer quotes, historians checking dates against parish records, worked checks, a
self-report quoted inside a source under analysis, a statistics office's check reported as evidence). These tests pin, on every
subject branch:

* each phrasing is named CORE-SELF-001 on the receipt, the claims holding it carry the advisory status (INT-HANDOFF-006) and none is
  material; written at the end of the answer's own paragraph, it is still named CORE-SELF-001;
* the correct work draws no CORE-SELF-001, no advisory status and (on the English branches) no ES-META-001;
* the reader by class: every combination of an internal checker, a checking verb and the answer's own items is named, and every
  combination of a named outside party with the figures the answer quotes is not.
"""
from __future__ import annotations

import itertools

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import self_report as sr

from .c2_hold_texts import ROUND3, ROUND3_CORRECT_WORK, SUBJECTS
from .test_c2_clearance_parsers import codes, through_hub
from .test_c2_hold_round2_self_reports import _holding

QUESTION = "Answer the question."
IDS = [s[0] for s in SUBJECTS]


@pytest.mark.parametrize("sentence", ROUND3)
def test_the_one_reader_names_every_round_3_phrasing(sentence):
    assert md.is_self_certification(sentence) and sr.is_self_report(sentence), sentence


@pytest.mark.parametrize("sentence", ROUND3_CORRECT_WORK)
def test_the_one_reader_names_no_round_3_correct_work(sentence):
    assert not md.is_self_certification(sentence), (sentence, sr.reading_form(sentence))


@pytest.mark.parametrize("sentence", ROUND3)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_every_phrasing_is_named_on_every_branch_and_never_material(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" in codes(rc), (subject, sentence, codes(rc))
    holding = _holding(reply, sentence)
    assert not [c for c in holding if c["materiality"] == "material"], holding
    for c in holding:
        assert c.get("advisory_verification_status") is not None, c
        assert [f for f in rc.findings if f.code == "INT-HANDOFF-006" and c["claim_id"] in f.claim_ids], codes(rc)


@pytest.mark.parametrize("sentence", [s for s in ROUND3 if "|" not in s and not s.startswith("*")])
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_every_phrasing_closing_the_answers_own_paragraph_is_named(subject, agent, task_type, base, sentence):
    _reply, rc = through_hub(base + " " + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert [f for f in rc.structural_findings if f.code == "CORE-SELF-001"], (subject, sentence, codes(rc))


@pytest.mark.parametrize("sentence", ROUND3_CORRECT_WORK)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_round_3_correct_work_draws_no_self_report_on_any_branch(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    found = set(codes(rc))
    assert "CORE-SELF-001" not in found, (subject, sentence, [f.message for f in rc.structural_findings if f.code == "CORE-SELF-001"])
    assert not [c for c in reply.payload["claims"] if c.get("advisory_verification_status") is not None]
    if "checked and confirmed by" in sentence:  # the English pack's narration rule reads the one reader's vetoes too
        assert "ES-META-001" not in found, (subject, sentence)


def test_a_source_authors_check_is_never_the_writers_through_a_neighbouring_maths_sentence():
    text = ("From 2x + 3 = 11 we get 2x = 8, so x = 4. The figures above are taken from Source B, whose author checked them against parish "
            "registers.")
    assert sr.self_report_spots(text) == []
    _reply, rc = through_hub(text, QUESTION, subject="Mathematics: Analysis and Approaches", agent="maths-specialist", task_type="calculation")
    assert "CORE-SELF-001" not in codes(rc)


# ============================================================================================ the reader by class
CHECKERS = ["by my teacher", "on my calculator", "with a Casio fx-83 calculator", "by the system", "by Z3", "with Desmos", "in GeoGebra",
            "by a tutor", "by a classmate", "on a TI-Nspire", "using Wolfram Alpha", "by the solver", "by an independent check", ""]
ITEMS = ["All the values above", "Every figure here", "Each step", "These calculations", "All of my answers", "The numbers in this answer"]
CHECKS = ["were verified", "have been checked", "were double-checked", "have been confirmed", "were validated", "were vetted",
          "have been signed off", "were cross-checked", "were recalculated", "were proofread", "were re-verified", "were cross-referenced"]


def test_every_internal_check_of_the_answers_items_is_named():
    missed = [s for s in (f"{i} {c} {k}".strip() + "." for i, c, k in itertools.product(ITEMS, CHECKS, CHECKERS)) if not sr.is_self_report(s)]
    assert not missed, missed[:10]


def test_every_first_person_or_tool_check_and_every_correctness_verdict_on_the_answer_is_named():
    acts = ["checked every value above", "double-checked all of the figures", "verified each step", "confirmed all the calculations",
            "recalculated every figure", "vetted all the numbers", "reran each calculation", "went back over all the numbers", "re-did the working"]
    subjects = ["I", "We", "My teacher", "My GDC", "The calculator", "Z3", "The engine", "A classmate"]
    missed = [s for s in (f"{a} {b}." for a, b in itertools.product(subjects, acts)) if not sr.is_self_report(s)]
    verdicts = ["Everything above is correct.", "All the figures above are accurate.", "Every step here is right.", "My calculations are all correct.",
                "The working above contains no errors.", "There is nothing wrong with this answer.", "Nothing in this answer needs correcting.",
                "This response is error-free.", "Each answer above is exact.", "Everything in my answer is accurate."]
    missed += [s for s in verdicts if not sr.is_self_report(s)]
    assert not missed, missed


def test_no_named_outside_partys_check_of_the_quoted_figures_is_named():
    parties = ["the ONS", "Eurostat", "the World Bank", "the National Audit Office", "historians", "the census office", "independent auditors",
               "the IMF", "later studies", "the Treasury", "Gallup", "the statistics office", "the OECD"]
    acts = ["verified every figure above", "has verified all of the figures quoted above", "checked these dates against parish records",
            "confirmed the GDP figures quoted above", "validated all of the figures above", "has confirmed each of these statistics"]
    named = [s for s in (f"{p[0].upper() + p[1:]} {a}." for p, a in itertools.product(parties, acts)) if sr.is_self_report(s)]
    passive = ["All of the figures above were verified by {p}.", "The GDP figures quoted above were confirmed by {p} in 2022.",
               "These dates have been confirmed by {p}."]
    named += [s for s in (t.format(p=p) for p, t in itertools.product(parties, passive)) if sr.is_self_report(s)]
    assert not named, named[:10]


@pytest.mark.parametrize("sentence", [
    "Keynes was right about aggregate demand.", "The correct value of g is 9.81 m/s².", "The court was correct to uphold the appeal.",
    "This paragraph argues that the court is correct to uphold the thesis.", "Each figure is right there in the poem.",
    "My grandfather checked every ledger in the shop.", "His teacher approved every essay.", "The treaty was approved by the Senate in 1920.",
    "We can verify the result by differentiating.", "Students should double-check their working.", "The checks passed the inspection.",
    "Las cifras fueron verificadas por el INE.", "El gobierno aprobó la ley en 2019.", "The hypothesis was tested and the results agree with the model.",
])
def test_content_that_shares_the_vocabulary_is_not_named(sentence):
    assert not sr.is_self_report(sentence), (sentence, sr.reading_form(sentence))
