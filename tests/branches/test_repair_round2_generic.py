"""Repair round 2 (MISS-UNCH-RUBRIC-TEXT): on the generic branch, a judgement that opens its paragraph is the paragraph's
point, and the plain sentences after it are its reasons, as on the English branch; a consequence ('So ...') that opens a
paragraph still rests on nothing after it."""
from __future__ import annotations

from epinoic_logic.branches.generic_parser import GenericTextParser


def _claims(text: str):
    report = GenericTextParser().parse_response(text, request_id="r", task_id="t", report_id="rep", subject="Language B: Spanish",
                                                task_type="marking", supplied_texts=[])
    return report.claims


def test_an_opening_judgement_is_supported_by_the_sentences_after_it():
    claims = _claims("The email should receive 10 out of 12 for Criterion A. The rubric awards 10 marks to work with only minor errors. "
                     "The email has only two minor accent errors.")
    first = claims[0]
    assert first.claim_role == "judgement" and first.materiality == "material"
    assert first.supporting_claim_ids == [c.claim_id for c in claims[1:]]


def test_an_opening_consequence_rests_on_nothing_after_it():
    claims = _claims("So the email should receive 10 out of 12. The rubric awards 10 marks to work with only minor errors.")
    assert claims[0].supporting_claim_ids == []


def test_a_closing_judgement_keeps_the_claims_before_it():
    claims = _claims("The rubric awards 10 marks to work with only minor errors. The email has only two minor accent errors. "
                     "The email should therefore receive 10 out of 12.")
    assert claims[-1].claim_role == "judgement" and set(claims[-1].supporting_claim_ids) == {claims[0].claim_id, claims[1].claim_id}


# ------------------------------------------------------------------------------------------------------- a conclusion drawn from the sentence before it
# NAME-LINK-NONDISCRIMINATING (text delivery): "A. B. Since <B restated>, C." concludes C from B. The generic and History
# parsers read the point first, so C was a support of A with no support of its own, NOT_ELIGIBLE, and the evidence rules
# never saw what C rests on; a structured report records C as the point resting on A and B. A sentence whose leading reason
# clause restates a sentence before it now rests on the sentences before it. Controls: a reason of its own ("Because it
# imposed heavy reparations, ...") and a temporal "since" stay as they were.

from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter  # noqa: E402
from epinoic_logic.adapters.markdown import concludes_from_earlier, leading_reason_clause  # noqa: E402


def test_the_leading_reason_clause_is_read_up_to_its_comma():
    assert leading_reason_clause("Since households borrowed less, the rate rise reduced consumer spending.") == "households borrowed less"
    assert leading_reason_clause("Because the delegate objected to the terms, Source A suggests resentment.") == "the delegate objected to the terms"
    assert leading_reason_clause("Given that prices rose, demand fell.") == "prices rose"
    assert leading_reason_clause("Because of the war, prices rose.") is None          # a cause phrase, not a reason clause
    assert leading_reason_clause("Since 2010 prices have risen.") is None              # no clause closed by a comma
    assert leading_reason_clause("Prices rose, since demand grew.") is None            # the reason does not open the sentence


def test_a_reason_that_restates_an_earlier_sentence_concludes_from_it():
    assert concludes_from_earlier("Since households borrowed less, the rate rise reduced consumer spending.",
                                  ["Household borrowing fell sharply during 2023."])
    assert concludes_from_earlier("Since most households were cutting back, consumer confidence fell.",
                                  ["Survey data show that 62% of households cut their spending in 2023."])     # "cutting" meets "cut"


def test_a_reason_of_its_own_concludes_nothing_from_the_sentence_before_it():
    assert not concludes_from_earlier("Because it imposed heavy reparations, the government faced a crisis.", ["The treaty weakened the republic."])
    assert not concludes_from_earlier("Since the treaty took territory from Germany, Germans resented it.", ["Germany resented the treaty."])
    assert not concludes_from_earlier("Since y² > 4 and 1² = 1 is not greater than 4, y cannot be 1.", ["y is not 1."])  # symbols are no words


ECON = ("In March 2023 the central bank raised its base interest rate from 2% to 4%. Household borrowing fell sharply during 2023. "
        "Since households borrowed less, the rate rise reduced consumer spending.")


def test_the_generic_parser_rests_a_drawn_conclusion_on_the_sentences_before_it():
    c1, c2, c3 = _claims(ECON)
    assert c3.claim_role == "judgement" and c3.materiality == "material" and c3.supporting_claim_ids == [c1.claim_id, c2.claim_id]
    assert c3.claim_id not in c1.supporting_claim_ids                       # the point no longer rests on its own conclusion


def test_a_sentence_with_a_reason_of_its_own_still_supports_the_point():
    c1, c2 = _claims("The treaty weakened the Weimar Republic. Because it imposed heavy reparations, the government faced a financial crisis.")
    assert c1.claim_role == "point" and c1.supporting_claim_ids == [c2.claim_id] and c2.supporting_claim_ids == []


def _history(text: str):
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", task_type="source_analysis").claims


def test_the_history_parser_reads_a_drawn_conclusion_as_a_link_resting_on_the_point():
    h1, h2 = _history("Source A shows that the German delegate objected to the treaty. Because the delegate objected to the terms, "
                      "Source A suggests that some Germans resented the peace.")
    assert h2.claim_role == "link" and h2.materiality == "material" and h2.supporting_claim_ids == [h1.claim_id]
    k1, k2 = _history("The treaty weakened the Weimar Republic. Because it imposed heavy reparations, the government faced a financial crisis.")
    assert k2.claim_role == "analysis" and k1.supporting_claim_ids == [k2.claim_id]
