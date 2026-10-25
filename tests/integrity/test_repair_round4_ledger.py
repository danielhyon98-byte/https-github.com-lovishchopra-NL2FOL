"""Repair round 4, the combinator's ledger readings (the re-run review's variants of four classes):

* combinator-faults-3: short and symbolic self-certification ("Formally verified ✓", "This answer has passed every quality
  check.", "Status: VALID.", "(all steps checked)") is verification-status language, INT-LEDGER-029 in a synthesis; a
  subject's own checks, a "Result:" line and a passing the answer reports of something else are not.
* combinator-faults-5: a quotation credited after its closing mark ('"...", the leaflet says.', '"...", says the leaflet.',
  '"...", according to the leaflet.', '"...", as Churchill put it.', '"..." (Churchill, 1940).') or through a possessive
  noun ("Churchill's speech states that ...") is credited to that text: a specialist's prose presented as its words is
  a misattribution. A credit that opens a clause of its own, and a quotation the credited text holds, are not.
* combinator-faults-7: a synthesized step of a parallel trace states the source's own statement ("so total = 8" of the
  second loop), never a figure swapped from the first loop's; a figure the source states with other words is still a
  swap. A truth table's rows written "010" restate a table that writes the bits in cells.
* combinator-faults-8: one figure in SI decimal grouping ("0.000 42", "1.138 429"), apostrophe thousands ("12'500"), a
  bracketed exponent ("10^(−3)"), a unit's caret exponent ("dm^-3") or a spaced minus in a sign's place ("x = − 3") is the
  figure written plainly; a genuine change is still a change."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import is_self_certification
from epinoic_logic.integrity import SynthesizedClaim
from epinoic_logic.integrity.ledger import aligned_differences, check_synthesis_ledger, figure_changes, misattributed_quotations
from epinoic_logic.translate.contracts import SuppliedText

from .test_ledger_round8 import FACT, NOTE, TWO, _codes, _report, _synthesis

# ------------------------------------------------------------------------------------------------ combinator-faults-3

SHORT_SELF_REPORTS = ["This answer has passed every quality check.", "Formally verified ✓", "Status: VALID.", "Confidence: 100% (all steps checked).",
                      "Checked.", "All verified!", "This response has passed all the checks.", "Status — passed."]
NOT_SELF_REPORTS = ["The theory was verified.", "Checked against the census, the figure is 4.2 million.", "Status: endangered.",
                    "The bill passed every reading in Parliament.", "This essay argues that the policy passed every test of legitimacy.",
                    "Result: the firm should expand.", "Outcome: success in the domestic market.", "The program prints Status: VALID when the input is accepted.",
                    "All steps of the method must be checked before the experiment.", "This answer argues that the reform passed the test of time.",
                    "Project status: complete.", "Each step is shown below."]


@pytest.mark.parametrize("sentence", SHORT_SELF_REPORTS)
def test_a_short_or_symbolic_status_is_a_self_certification(sentence):
    assert is_self_certification(sentence)


@pytest.mark.parametrize("sentence", NOT_SELF_REPORTS)
def test_control_the_same_words_about_the_subject_are_no_self_certification(sentence):
    assert not is_self_certification(sentence)


@pytest.mark.parametrize("added", [" Formally verified ✓", " This answer has passed every quality check.", " Status: VALID."])
def test_a_short_status_appended_to_a_synthesized_claim_is_int_ledger_029(added):
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text + added, source_claim_ids=["s1.1"], transformation="merged", evidence_refs=TWO)])
    [f] = _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))["INT-LEDGER-029"]
    assert f.severity == "warning" and f.claim_ids[0] == "y1"


def test_control_a_synthesized_claim_with_no_status_has_no_int_ledger_029():
    syn = _synthesis([SynthesizedClaim(claim_id="y1", text=FACT.claim_text, source_claim_ids=["s1.1"], transformation="merged", evidence_refs=TWO)])
    assert "INT-LEDGER-029" not in _codes(check_synthesis_ledger([_report([FACT, NOTE])], syn))


# ------------------------------------------------------------------------------------------------ combinator-faults-5

DOCS = {"doc-sp": SuppliedText(document_id="doc-sp", title="Speech to Parliament, 1940 (supplied extract)", author="Winston Churchill",
                               text="We shall defend our island, whatever the cost may be."),
        "report:r4": SuppliedText(document_id="report:r4", title=None, author="history-specialist", text="the speech was designed to steady a frightened public."),
        "doc-leaflet": SuppliedText(document_id="doc-leaflet", title="Love it? (council leaflet, supplied text)", author="Kestrelford Borough Council",
                                    text="So why are you throwing away food?")}
PEER = '"the speech was designed to steady a frightened public"'


@pytest.mark.parametrize("sentence", [f"{PEER}, Churchill says.", f"{PEER}, as Churchill put it.", f"{PEER} (Churchill, 1940).",
                                      f"Churchill's speech states that {PEER}.", f"{PEER}, the leaflet says.", f"{PEER}, says the leaflet.",
                                      f"{PEER}, according to the leaflet.", f"{PEER} (council leaflet).", f"The council's leaflet states that {PEER}."])
def test_a_credit_after_the_quotation_or_through_a_possessive_names_the_misattribution(sentence):
    [found] = misattributed_quotations(sentence, DOCS)
    assert "occurs only in" in found and "history-specialist report r4" in found


@pytest.mark.parametrize("sentence", [f"{PEER}, the History specialist notes.", f"{PEER}, and the leaflet says nothing of it.",
                                      f"{PEER}, Churchill says that the island will be defended.", f"{PEER} (line 3).",
                                      '"We shall defend our island", Churchill says.', '"We shall defend our island" (Churchill, 1940).'])
def test_control_a_correct_credit_a_new_clause_or_a_locator_is_no_misattribution(sentence):
    assert misattributed_quotations(sentence, DOCS) == []


# ------------------------------------------------------------------------------------------------ combinator-faults-7

LOOP_SOURCE = ["On the first loop, i is 0, so total = 3. On the second loop, i is 1, so total = 8."]
PASS_SOURCE = ["Pass 1: mid 4, 21 < 9 is false, so high = 3. Pass 3: mid 2, 12 < 9 is false, so high = 1."]


@pytest.mark.parametrize("synthesis, sources", [
    ("Loop 1: i = 0 so total = 3. Loop 2: i = 1 so total = 8.", LOOP_SOURCE),
    ("Pass 1 takes mid 4, and 21 > 9 so high = 3. Pass 3 takes mid 2, and 12 > 9 so high = 1.", PASS_SOURCE),
    ("Pass 3 takes mid 2, and 12 > 9 so high = 1. Pass 1 takes mid 4, and 21 > 9 so high = 3.", PASS_SOURCE),
    ("Pass 1 takes mid 4, and 21 > 9 so high = 3.", ["Pass 1: mid 4, 21 < 9 is false, so high = 3.", "Pass 3: mid 2, 12 < 9 is false, so high = 1."]),
])
def test_a_paraphrased_parallel_trace_states_each_step_as_its_source_does(synthesis, sources):
    assert aligned_differences(synthesis, sources) == ([], [])


@pytest.mark.parametrize("synthesis, sources", [
    ("Loop 1: i = 0 so total = 3. Loop 2: i = 1 so total = 3.", LOOP_SOURCE),
    ("In 2019 sales were 500.", ["In 2019 sales were 300. In 2020 sales were 500."]),
])
def test_control_a_figure_swapped_into_another_statement_is_still_a_change(synthesis, sources):
    figures, _meaning = aligned_differences(synthesis, sources)
    assert figures and "put in place of" in figures[0]


TABLE = "| A | B | C | X |\n|---|---|---|---|\n| 0 | 0 | 0 | 0 |\n| 0 | 1 | 0 | 1 |\n| 1 | 1 | 0 | 1 |"


def test_rows_of_bits_restate_a_table_that_writes_the_bits_in_cells():
    assert figure_changes("Rows: 000 → 0; 010 → 1; 110 → 1.", [TABLE]).introduced == []


@pytest.mark.parametrize("synthesis, source", [("Rows: 000 → 0; 011 → 1.", TABLE), ("The answer is 110.", "The rows are 1, 1, 0 and then 0.")])
def test_control_a_row_the_table_does_not_hold_or_a_list_in_prose_is_no_row(synthesis, source):
    assert figure_changes(synthesis, [source]).introduced != []


# ------------------------------------------------------------------------------------------------ combinator-faults-8

@pytest.mark.parametrize("synthesis, source", [
    ("The value is 0.000 42 m.", "The value is 0.00042 m."),
    ("The probability is 0.047 79.", "The probability is 0.04779."),
    ("The ratio is 1.138 429.", "The ratio is 1.138429."),
    ("The town has 12'500 residents.", "The town has 12500 residents."),
    ("The rate is 2.5 × 10⁻³ mol dm⁻³.", "The rate is 2.5 × 10^(−3) mol dm⁻³."),
    ("The rate is 2.5 × 10⁻³ mol dm⁻³.", "The rate is 2.5 x 10^-3 mol dm^-3."),
    ("x = -3", "x = − 3"),
])
def test_one_figure_in_two_notations_is_one_figure(synthesis, source):
    fc = figure_changes(synthesis, [source])
    assert fc.introduced == [] and fc.dropped == [] and fc.reprecised == []


@pytest.mark.parametrize("synthesis, source, introduced", [
    ("The value is 0.000 43 m.", "The value is 0.00042 m.", "0.00043"),
    ("The town has 13'500 residents.", "The town has 12500 residents.", "13500"),
    ("x = 5 − 3", "x = -3", "5"),
])
def test_control_a_changed_figure_in_either_notation_is_still_introduced(synthesis, source, introduced):
    assert introduced in figure_changes(synthesis, [source]).introduced
