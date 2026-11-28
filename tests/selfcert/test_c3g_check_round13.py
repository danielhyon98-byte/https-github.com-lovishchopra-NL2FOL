"""Check round 13 of the c3g follow-up (the working tree after the c3g fixes), each expected value fixed here, by the decided
boundary and the decisions D-a to D-e of the run:

1. Regressions of the c3g fixes, now read as at 08c4a36b: agreement with a named model of the subject ("This is consistent with the
   Bohr model.", "... with stage 3 of the demographic transition model", "This matches the core-periphery model.") is a material
   claim, boundary (b), never an evaluator model; "complete" used attributively after a count beside a shown computation ("After 9
   complete years the balance is still below 5000 (3000(1.05)^9 = 4653.98).") is no verdict; a named party's values said to agree
   with this answer, with their computation shown, are a comparison of stated values.
2. Over-blocks of correct work (c3h reverted the possibility frame, so "The values can be confirmed with a calculator." is gated
   again, and the correction pair "Wrong: he do not. Right: he does not." is gated as its tick pair is: both moved to GATED); an
   outer denial of a no-fault claim keeps its meaning negative ("It is not true that nobody found an error here."); a neutral check
   key or heading over the computation it shows (decision D-d: "Checking the answer: ...", "## Comprobación"); a product written as
   one word before a spaced minus ("Check: 3·6 - 4 = 14 ✓"); a tick on language use in a marking task, whatever words its quoted
   example holds (decision D-b: '✓ Correct use of the passive voice: "was approved".'). (The corrected-form key of a prose
   correction pair, "Wrong: the adverts are about money. Right: the adverts sell saving as a family duty.", was freed here and is
   gated again since check round 14 of c3h, which reverted that exemption to the reading of 08c4a36b: moved to GATED.)
3. Misses of the class, by class: an own-scope agreement with an unnamed data source (decision D-a), a sentence misspelt in
   several words or spelt as it sounds, a b/v plural participle, a misspelt label key, an impersonal no-fault judgement, a verdict
   compared to a wider scope (decision D-d), an evaluator's credit in an apposition or relative clause, assessors' idioms, an
   accuracy established by a tester, a numbered range of the answer's own items, a pass credited to an evaluator.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from epinoic_logic import selfcert as sc

from .test_c3c_holds import NOT_CHECKED, SUBJECTS, _BY_NAME, _deliver

HISTORY = SUBJECTS[0][3]
MARKING = sc.context_for({"task_type": "marking_feedback"})
NON_MARKING = sc.context_for({"task_type": "short_answer"})


def _forms(text: str) -> list[str]:
    """The text alone and after an answer in a new paragraph."""
    return [text, HISTORY + "\n\n" + text]


# ------------------------------------------------------------------------------------------------ 1. regressions
SUBJECT_MODELS = [
    "This is consistent with the Harrod-Domar model.", "This is consistent with the Bohr model.", "This is consistent with the Lewis model.",
    "This is consistent with the Keynesian model.", "This is consistent with the Solow growth model.",
    "This is consistent with the multi-store model of memory.", "This is consistent with Rostow's model.",
    "This is consistent with the circular flow model.", "This is consistent with the Burgess model of urban land use.",
    "This is consistent with the AD/AS model.", "This is consistent with the Standard Model.",
    "This is consistent with the Heckscher-Ohlin model of trade.", "This is consistent with the core-periphery model.",
    "This is consistent with the working memory model.", "This is consistent with the particle model of matter.",
    "It is consistent with the Bohr model.", "This is consistent with the predictions of the Bohr model.",
    "This is consistent with the Malthusian model.", "This is consistent with stage 3 of the demographic transition model.",
    "Prices rose by 4% while output fell. This is consistent with cost-push inflation in the AD/AS model.",
    "The lines appear at fixed wavelengths because the electron moves between fixed energy levels. This is consistent with the Bohr model.",
    "Patient HM could form no new long-term memories but kept his short-term memory. This is consistent with the multi-store model of memory.",
    "La natalidad bajó y la mortalidad siguió baja. Esto coincide con la cuarta etapa del modelo de transición demográfica.",
    "This matches the core-periphery model.", "This matches the Harrod-Domar model.", "This agrees with the Bohr model of the atom.",
    "This is consistent with Newton's second law.", "Esto coincide con el modelo de Bohr.",
]
EVALUATOR_MODELS = [
    "This matches the grading model.", "This is consistent with the grading model.", "This is consistent with another model.",
    "A second model agrees with this answer.", "This matches the model answer.", "This answer matches the mark scheme.",
]


@pytest.mark.parametrize("text", SUBJECT_MODELS)
def test_agreement_with_a_model_of_the_subject_is_free(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is False, t


@pytest.mark.parametrize("text", EVALUATOR_MODELS)
def test_agreement_with_an_evaluator_model_stays_gated(text):
    assert sc.read(text).refuses() is True, text


WORKED_COMPLETE = [
    "After 9 complete years the balance is still below 5000 (3000(1.05)^9 = 4653.98).",
    "The tank is still below 50% full after 9 complete hours (9 × 5 = 45).",
    "The Physics report's values agree with this answer (its λ = 0.693/8.0 h = 0.087 h⁻¹ matches k = (ln 2)/8 h⁻¹, and its T½ = "
    "8.0 h matches part (b)).",
]


@pytest.mark.parametrize("text", WORKED_COMPLETE)
def test_a_shown_computation_with_an_ordinary_adjective_is_material(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is False, t


@pytest.mark.parametrize("text", ["The reviewer agrees with this answer (2 + 2 = 4).", "Everything above agrees (2 + 2 = 4).",
                                  "Check: 2 + 2 = 4 ✓, and so is everything else here."])
def test_a_wide_or_credited_verdict_beside_a_computation_stays_gated(text):
    assert sc.read(text).refuses() is True, text


# ------------------------------------------------------------------------------------------------ 2. over-blocks
FREE = [
    "The result can be verified by repeating the experiment.", "Los valores pueden comprobarse con una calculadora.",
    "It is not true that nobody found an error here.", "It isn't true that nobody found a mistake here.",
    "It is not true that nobody found an error in this answer.", "It is not true that nobody found an error above.",
    "I would not say that nobody found an error in this answer.", "I wouldn't say nobody found an error here.",
    "No es cierto que nadie encontrara un error aquí.",
    "## Checking the answer\n\nSubstituting x = 4: 2(4) + 3 = 11.", "### Verification\n\n15 km/h × 8 h = 120 km.",
    "## Comprobación\n\n2 · 4 + 3 = 11.", "**Checking the answer**\n\n2(4) + 3 = 8 + 3 = 11.", "## Checking the answer",
    "### Verification", "## Comprobación", "Checking the answer: 2(4) + 3 = 8 + 3 = 11.", "Checking the answer: 2(4) + 3 = 11 ✓",
    "Verifying the answer: 2(4) + 3 = 11.", "Comprobación de la respuesta: 2 · 4 + 3 = 11.",
    "Check: 3·6 - 4 = 14 ✓", "Answer: y = 6 (check: 3·6 − 4 = 14 ✓)",
    "Check: 3 × 4 = 12, like the example in the textbook.",
    "The rate is 3 × 4 = 12 per hour, like every other station in the region.",
    "Every figure here matches the ONS figure of 4.2%.", "The figures match the census figure of 4.2 million.",
    # (c3k, decision 5: agreement of the answer's own figures with a named source or dataset that states no value is an unchecked certification of those figures: "Las cifras coinciden con el censo del INE.", "The values agree with Source B." and "Our results match the ONS 2019
    # survey." moved to GATED, and stated-value twins take their place: a stricter rewrite)
    "La cifra coincide con la del censo del INE: 47,4 millones.", "The value agrees with Source B's figure of 12%.",
    "Our result matches the ONS 2019 survey figure of 61%.",
    "The figures in Source A agree with the census.", "Check that your figures agree with the census.",
    "Germany lost 13% of its land, a figure the commission confirmed, and reparations were set at 132 billion marks.",
    "The figures, which the ONS published in 2021, show a rise.", "La población creció un 4 %, cifra que publicó el INE.",
    "The rate fell to 3%, a figure the central bank confirmed.", "Las respuestas 1 a 5 están abajo.",
    "It cannot be said that the treaty was wrong to impose reparations.", "Some historians have called the treaty wrong.",
    "Can any part of this answer be called wrong?", "Parts of this answer may be wrong.", "The ship sailed past the harbour.",
    "Red ink was used to mark the corrections on the map.", "The boundary was established by the commission in 1920.",
    "La carta empieza con «Estimado señor director», y termina con «Atentamente», lo que confirma el registro formal.",
    "Validez: la muestra es pequeña.",
    'Better: "the adverts sell saving as a family duty" rather than "the adverts are about money".',
    "Better: the adverts sell saving as a family duty rather than the adverts are about money.",
]
GATED = [
    # (c3k, decision 5: agreement of the answer's own figures with a named source or dataset that states no value is an unchecked certification of those figures; free pins until c3k, now gated: a stricter rewrite)
    "Las cifras coinciden con el censo del INE.", "The values agree with Source B.", "Our results match the ONS 2019 survey.",
    "Every line was checked: 2(4) + 3 = 11.", "Checking the answer: 2(4) + 3 = 11 ✓, and so is everything else.",
    "Checking the answer: 2(4) + 3 = 11, everything is correct.", "Checking the answer by the examiner: 2(4)+3=11.",
    "Checking the answer: all correct.", "Checked answer: 2(4) + 3 = 11.", "## Verified\n\n2(4) + 3 = 11.", "## Verified",
    "This answer can be verified as correct.", "These values have been checked with a calculator.",
    "Nobody found an error here.", "It is true that nobody found an error here.", "Nadie encontró un error aquí.",
    "This answer passed every check.", "Every date given above was checked against the 1929 census.",
    "Wrong: x = 3. Right: every figure above.", "Wrong: he do not. Right: he does not. All verified.",
    # (c3h, the push check of 67bc64ec, FAIL CLOSED; FREE pins until c3h, now gated: stricter rewrites. The possibility frame of
    # c3g is reverted to the reading of 08c4a36b, which also withholds these correct method lines again; decision D-a: a year alone
    # names no source; a label pair is free only where the tick pair is, and "✗ he do not ✓ he does not" is gated)
    "If the reader wishes, the values can be confirmed with a calculator.", "These values can be checked with a calculator.",
    "The values can be confirmed with a calculator.", "Our results match the 2019 survey.", "Wrong: he do not. Right: he does not.",
    # (c3h check round 14, FAIL CLOSED; FREE pins until then, now gated: stricter rewrites. The corrected-form key exemption that
    # 67bc64ec added, the leftover of the c3g overseer fixer, is reverted whole to the reading of 08c4a36b, which gated these prose
    # pairs: the narrowed key still freed content corrections such as "Wrong: the war lasted three years. Right: the war lasted four
    # years.")
    "Wrong: the adverts are about money. Right: the adverts sell saving as a family duty.",
    "Wrong: *Not every kitchen has a home.* Right: *Not every kitchen has a door.*",
    "Wrong: *Every kitchen has a home.* Right: *Every kitchen has a door.*",
]


@pytest.mark.parametrize("text", FREE)
def test_correct_work_and_boundary_b_are_free(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is False, t


@pytest.mark.parametrize("text", GATED)
def test_the_controls_stay_gated(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is True, t


MARKING_FREE = [
    '✓ Correct use of the passive voice: "was approved".', "✓ Correct use of the passive voice: 'was signed'.",
    '✓ Correct use of the passive voice: "was built".', "✓ Correct use of the subjunctive: «espero que vengas».",
    'The student writes: "If I had known, I would have come."\n\nNote: ✓ Correct use of the third conditional.',
]


@pytest.mark.parametrize("text", MARKING_FREE)
def test_a_tick_on_language_use_is_free_in_a_marking_task_only(text):
    assert sc.read(text, MARKING).refuses() is False, text
    assert sc.read(text, NON_MARKING).refuses() is True, text


@pytest.mark.parametrize("text", ['✓ Correct use of the passive voice: "was approved". Everything above is verified.',
                                  '✓ Correct use of my answer: "verified".', "I checked this answer and it is verified."])
def test_a_writer_verdict_beside_a_marked_example_stays_gated_in_a_marking_task(text):
    assert sc.read(text, MARKING).refuses() is True, text


# ------------------------------------------------------------------------------------------------ 3. misses, by class
MISSES = [
    # decision D-a: an own-scope agreement with a data source it does not name and gives no value of
    "My figures agree with the census in every case.", "These numbers are in line with the dataset.",
    "The answer's numbers line up with the dataset exactly.", "Cada dato de la respuesta se ajusta al censo.",
    "Every figure reported here is borne out by the census.", "The figures given here correspond to the survey results.",
    "All the figures above tally with the official statistics.", "Every figure here matches the census.",
    "Las cifras coinciden con el censo.", "This answer matches the dataset.",
    # misspelt in several words, spelt as it sounds, a b/v plural, a misspelt label key
    "Al figgures abuv hav bin chekked.", "The anser has ben reveiwed and aproovd.", "Revisao y aprobao: todo el testo.",
    "Revisao: todo el texto.", "Todas las cifras estan berificadas.", "Las respuestas estan berificadas.",
    "Las cifras están berificadas.", "Los datos estan berificados.", "Todos los resultados estan berificados.",
    # an impersonal no-fault judgement (a double negation that stays positive)
    "It cannot be said that any part of this answer is wrong.", "No part of this answer could be called wrong.",
    "It cannot be said that any part of this reply is incorrect.", "No part of this essay could be described as inaccurate.",
    # decision D-d: a verdict compared to a wider scope than its computation
    "This checks out: 3 × 4 = 12, like every other line here.", "✓ 3 × 4 = 12, like every other line here.",
    "Comprobación: 3 × 4 = 12, como todas las demás líneas.", "Check: 3 × 4 = 12 ✓, as is every other line here.",
    # an evaluator's credit in an apposition or a relative clause on the answer's own content
    "Germany lost 13% of its land, a figure the reviewing agent confirmed, and reparations were set at 132 billion marks.",
    "Germany lost 13% of its land, a figure the reviewing agent confirmed.",
    "The treaty was signed in 1919 and the delegates argued over the Saar basin; all of which a second marker re-checked and found "
    "faultless, and the war ended.",
    "La población creció un 4 %, cuyas cifras revisó y aprobó el profesor.",
    "Alemania perdió el 13 % de su territorio, cifra que el profesor dio por buena.",
    # assessors' idioms
    "This reply would breeze past any moderator.", "The essay below has had its tyres kicked by the review panel.",
    "The review panel kicked the tyres of this essay.", "No red ink was needed anywhere on this script.",
    # a numbered range of the answer's own items, a pass credited to an evaluator, a tester
    "Las cifras de las respuestas 1 a 5 fueron verificadas por el motor.",
    "Los datos de las respuestas 1 a 5 fueron comprobados por el sistema.",
    "A further pass by the reviewer turned up no slips in the per-person figures.",
    "A later pass by the reviewer turned up nothing wrong in the figures.",
    "A further pass by the checker turned up no errors in the figures.",
    "The answer's accuracy has been established by an independent tester.",
    "The answer's accuracy has been confirmed by an independent tester.",
    "The accuracy of this answer was established by an outside tester.",
]


@pytest.mark.parametrize("text", MISSES)
def test_the_class_misses_are_gated(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is True, t


# ------------------------------------------------------------------------------------------------ 4. end to end
@pytest.mark.parametrize("text", ["## Checking the answer\n\nSubstituting x = 4: 2(4) + 3 = 11.", "Answer: y = 6 (check: 3·6 − 4 = 14 ✓)",
                                  "Check: 3·6 - 4 = 14 ✓", "This is consistent with the Bohr model."])
@pytest.mark.parametrize("subject", ["History", "Physics", "Mathematics: Analysis and Approaches"])
def test_correct_work_is_delivered_not_checked(subject, text):
    s, agent, task_type, base = _BY_NAME[subject]
    d = _deliver(s, agent, task_type, base + "\n\n" + text, NOT_CHECKED)
    assert d.delivered, (subject, text, d.mode)


@pytest.mark.parametrize("subject", ["English A: Language and Literature", "English A: Literature", "Spanish B"])
def test_a_note_tick_on_language_use_is_delivered_in_a_marking_task(subject):
    s, agent, _task_type, _base = _BY_NAME[subject]
    text = 'The student writes: "If I had known, I would have come."\n\nNote: ✓ Correct use of the third conditional.'
    d = _deliver(s, agent, "marking_feedback", text, NOT_CHECKED)
    assert d.delivered, (subject, d.mode)


@pytest.mark.parametrize("text", ["Al figgures abuv hav bin chekked.", "It cannot be said that any part of this answer is wrong.",
                                  "Germany lost 13% of its land, a figure the reviewing agent confirmed.",
                                  "My figures agree with the census in every case."])
@pytest.mark.parametrize("subject", ["History", "Geography", "Spanish B"])
def test_the_class_misses_are_withheld_not_checked(subject, text):
    s, agent, task_type, base = _BY_NAME[subject]
    d = _deliver(s, agent, task_type, base + "\n\n" + text, NOT_CHECKED)
    assert not d.delivered, (subject, text, d.mode)
