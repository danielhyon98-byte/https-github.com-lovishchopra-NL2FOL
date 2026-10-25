"""Repair round 5, the combinator's ledger readings (the re-run review's variants of five classes, and one regression):

* combinator-faults-7 (the weakened swap check): a figure is excused as copied context only when the source states the
  whole synthesized run back to the start of its sentence, so a swap of two parallel statements' figures whose telling word
  (a year) stands far before the figure is still a change; the same statements with each figure in place are clean.
* combinator-faults-7 (ordinal labels): a step label written as a numeral ("Trial 1", "Week 2") for the source's ordinal
  ("the first trial", "week two") is the same label, never an introduced figure; a label the source does not state is.
* combinator-faults-8: accounting parentheses for a negative amount ("(2,400.50)") and a precision note ("(2 s.f.)") are
  notations of the figure, not figures; a changed amount is still a change, and "(2) per cent" stays the figure 2.
* combinator-faults-3: a check mark with a verdict, a "QA:" or "Quality check:" label, a guarantee, a bracketed outcome, a
  result line that is only a verdict, the answer reviewed and approved, and the infrastructure finding no problems are
  verification-status statements; the same words about the subject are not.
* combinator-faults-5: "As the poem puts it:", "In X's words,", '"..." — X.', "X:" opening a sentence and a credit by a
  person's role ("The President declares that") credit the quotation to that text.
* ADV5-12: a word-count line appended to a synthesized claim is a measurement, never INT-LEDGER-029."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import is_self_certification, is_word_count_line
from epinoic_logic.integrity import SynthesizedClaim
from epinoic_logic.integrity.ledger import aligned_differences, check_synthesis_ledger, figure_changes, misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText

from .test_ledger_round8 import FACT, NOTE, TWO, _codes, _report, _synthesis

# ------------------------------------------------------------------------------------------------ combinator-faults-7: swaps

RENT = ["In 2018 the average rent in the city centre increased by 4.5 per cent, while in 2021 the average rent in the city "
        "centre increased by 2.1 per cent."]


def test_a_swap_whose_telling_word_stands_far_before_the_figure_is_a_change():
    synthesis = ("In 2018 the average rent in the city centre increased by 2.1 per cent, while in 2021 the average rent in the city "
                 "centre increased by 4.5 per cent.")
    figures, _meaning = aligned_differences(synthesis, RENT)
    assert len(figures) == 2 and all("put in place of" in f for f in figures)


def test_control_the_same_statements_with_each_figure_in_place_are_clean():
    synthesis = "In 2018 the average rent in the city centre rose by 4.5 per cent, and in 2021 the average rent in the city centre rose by 2.1 per cent."
    assert aligned_differences(synthesis, RENT) == ([], [])


# ------------------------------------------------------------------------------------------------ combinator-faults-7: labels

@pytest.mark.parametrize("synthesis, source", [
    ("Trial 1: the mass was 12.40 g. Trial 2: the mass was 12.85 g.", "In the first trial the mass was 12.40 g; in the second trial the mass was 12.85 g."),
    ("Week 1: sales = 300. Week 2: sales = 420.", "In week one sales were 300, and in week two sales were 420."),
    ("Round 3: score = 7.", "In the third round the score was 7."),
], ids=["trial", "week", "round"])
def test_a_step_label_written_as_a_numeral_restates_the_sources_ordinal(synthesis, source):
    fc = figure_changes(synthesis, [source])
    assert fc.introduced == [] and fc.dropped == [] and fc.reprecised == []


@pytest.mark.parametrize("synthesis, introduced", [("Trial 3: the mass was 12.40 g.", "3"), ("Trial 1: the mass was 12.45 g.", "12.45")])
def test_control_a_label_or_a_figure_the_source_does_not_state_is_introduced(synthesis, introduced):
    assert introduced in figure_changes(synthesis, ["In the first trial the mass was 12.40 g."]).introduced


# ------------------------------------------------------------------------------------------------ combinator-faults-8

@pytest.mark.parametrize("synthesis, source", [
    ("The deficit was (2,400.50) pounds.", "The deficit was −2,400.50 pounds."),
    ("The speed is 3.7 m s⁻¹ (2 s.f.).", "The speed is 3.7 m s⁻¹."),
    ("The speed is 3.7 m s⁻¹ (to 2 sig. figs).", "The speed is 3.7 m s⁻¹."),
], ids=["accounting parentheses", "s.f. note", "sig. figs note"])
def test_a_notation_of_the_figure_is_no_figure(synthesis, source):
    fc = figure_changes(synthesis, [source])
    assert fc.introduced == [] and fc.dropped == [] and fc.reprecised == []


@pytest.mark.parametrize("synthesis, source, introduced", [
    ("The deficit was (2,400.75) pounds.", "The deficit was −2,400.50 pounds.", "2400.75"),
    ("The speed is 3.8 m s⁻¹ (2 s.f.).", "The speed is 3.7 m s⁻¹.", "3.8"),
])
def test_control_a_changed_figure_beside_the_notation_is_still_introduced(synthesis, source, introduced):
    assert introduced in figure_changes(synthesis, [source]).introduced


def test_control_a_bracketed_figure_that_is_no_money_amount_stays_unsigned():
    fc = figure_changes("The rate is (2) per cent.", ["The rate is 2 per cent."])
    assert fc.introduced == [] and fc.dropped == []


# ------------------------------------------------------------------------------------------------ combinator-faults-3

STATUS_FORMS = ["✓ Everything checks out.", "✔ All is in order.", "QA: passed.", "Quality check: passed.", "Correctness guaranteed.",
                "This has been reviewed and approved.", "(Checked.)", "Result: correct.", "The router found no errors in this answer.",
                "Approved by the overseer."]
SUBJECT_FORMS = ["The firm checked its accounts.", "Result: the firm should expand.", "The hub of the network found no problems with the cable.",
                 "12 (checked)", "The council approved the plan.", "Quality: high in the domestic market.", "✓ Prices rose in 2020.",
                 "✓ The firm checks out its rivals."]


@pytest.mark.parametrize("sentence", STATUS_FORMS)
def test_a_short_status_form_is_a_self_certification(sentence):
    assert is_self_certification(sentence)


@pytest.mark.parametrize("sentence", SUBJECT_FORMS)
def test_control_the_same_words_about_the_subject_are_none(sentence):
    assert not is_self_certification(sentence)


@pytest.mark.parametrize("added", [" Correctness guaranteed.", " ✓ Everything checks out.", " (Checked.)"])
def test_a_status_form_appended_to_a_synthesized_claim_is_int_ledger_029(added):
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text + added, source_claim_ids=["s1.1"], transformation="merged", evidence_refs=TWO)])
    assert "INT-LEDGER-029" in _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))


# ------------------------------------------------------------------------------------------------ ADV5-12: word counts

@pytest.mark.parametrize("added", [" Word count: 52.", " (48 words)"])
def test_a_word_count_appended_to_a_synthesized_claim_is_no_int_ledger_029(added):
    assert is_word_count_line(added.strip())
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text + added, source_claim_ids=["s1.1"], transformation="merged", evidence_refs=TWO)])
    assert "INT-LEDGER-029" not in _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))


def test_control_a_count_inside_a_sentence_is_no_word_count_line():
    assert not is_word_count_line("The report counts 52 words of praise for the reform.")


# ------------------------------------------------------------------------------------------------ combinator-faults-5

POEM = {"doc-poem": SuppliedText(document_id="doc-poem", title="Ozymandias (supplied text)", author="Percy Bysshe Shelley",
                                 text="Look on my Works, ye Mighty, and despair!"),
        "report:r9": SuppliedText(document_id="report:r9", title=None, author="english-specialist",
                                  text="the ruined statue warns every ruler that power does not last")}
OWN = '"the ruined statue warns every ruler that power does not last"'
SPEECH = {"doc-sp": SuppliedText(document_id="doc-sp", title="Address to the nation, 1933 (supplied extract)", author="Franklin D. Roosevelt",
                                 text="the only thing we have to fear is fear itself"),
          "report:r4": SuppliedText(document_id="report:r4", title=None, author="history-specialist", text="the address was meant to calm a frightened nation")}


@pytest.mark.parametrize("sentence", [f"As the poem puts it: {OWN}.", f"In Shelley's words, {OWN}.", f"{OWN} — Shelley.", f"Shelley: {OWN}.",
                                      f"In the poet's words: {OWN}."])
def test_a_credit_form_presents_the_specialists_words_as_the_poems(sentence):
    [found] = misattributed_quotations(sentence, POEM)
    assert "occurs only in" in found


def test_a_credit_by_the_authors_role_presents_the_specialists_words_as_the_speech():
    assert misattributed_quotations('The President declares that "the address was meant to calm a frightened nation".', SPEECH)


@pytest.mark.parametrize("sentence", ['As the poem puts it: "Look on my Works, ye Mighty, and despair!"', f"{OWN}, the English specialist argues.",
                                      f"Shelley's tone shifts here; {OWN} is my own reading."])
def test_control_a_true_credit_or_the_writers_own_reading_is_no_misattribution(sentence):
    assert misattributed_quotations(sentence, POEM) == []
