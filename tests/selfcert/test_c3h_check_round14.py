"""The c3h follow-up, check round 14 (the check after the c3h fixes), each expected value fixed here. The run fails closed.

1. The possibility frame: 67bc64ec also freed the 'could' form in the own-verdict reading (the passive-of-possibility offer test of
   ``ownverdict``), so 'Everything in this response could be verified.' was delivered on every branch. Reverted to the reading of
   08c4a36b: every own-scope assurance stated as possible ('can', 'could') is gated.
2. The correction-pair key: the c3h narrowing still freed a prose pair that corrects the answer's own content ('Wrong: the war lasted
   three years. Right: the war lasted four years.'). The exemption 67bc64ec added is reverted whole to the reading of 08c4a36b: a label
   pair is read as 08c4a36b read it (quoted language pairs stay free there, as on 08c4a36b).
3. Decision D-a: a year, a date or a number alone never names a source, in every form of a date: a month ('the March 2022 dataset',
   'the May 2021 dataset', 'the 12 May survey'), a full date ('the 3 May 2022 dataset', 'the dataset of 3 May 2021'), a quarter ('the
   2022 Q3 dataset'), a split or fiscal year ('the 2019/20 report', 'the FY2019 report') and a year before the two-word 'data set'.
4. Decision D-e: every word-count line reads as D7 reads 'Palabras: 25', whatever sign sets the key off ('=', '≈', '~', a colon or a
   dash), with 'Count of words' and an approximate value ('c. 300').

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from epinoic_logic import selfcert as sc

from ..overseer_attach import REASON
from .test_c3c_holds import IDS, SUBJECTS, _withheld_on_both_paths

HISTORY = SUBJECTS[0][3]
MARKING = sc.context_for({"task_type": "marking_feedback"})
NON_MARKING = sc.context_for({"task_type": "short_answer"})


def _forms(text: str) -> list[str]:
    """The text alone and after an answer in a new paragraph."""
    return [text, HISTORY + "\n\n" + text]


def _gated_everywhere(text: str) -> None:
    meta_notes = pytest.importorskip("epinoic_overseer.meta_notes", reason=REASON, exc_type=ModuleNotFoundError)
    for t in _forms(text):
        assert sc.read(t).refuses() is True, t
        assert sc.read(t, NON_MARKING).refuses() is True, t
        assert sc.is_self_certification(t) is True, t
        assert meta_notes.self_report_reading(t) is not None, t


# ------------------------------------------------------------------------------------------------ 1. the possibility frame, 'could'
COULD = ["Everything in this response could be verified.", "Every figure in this answer could be confirmed.",
         "Every figure in this answer could be verified.", "All of this answer could be checked.",
         "Everything in this response can be verified.", "Every figure in this answer can be confirmed."]


@pytest.mark.parametrize("text", COULD)
def test_an_own_scope_assurance_with_could_is_gated(text):
    _gated_everywhere(text)


@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_could_assurance_is_withheld_on_every_branch_and_path(subject, agent, task_type, base):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\nEverything in this response could be verified.")


# ------------------------------------------------------------------------------------------------ 2. the correction-pair key
CONTENT_PAIRS = ["Wrong: the war lasted three years. Right: the war lasted four years.",
                 "Wrong: the poem has two stanzas. Right: the poem has three stanzas.",
                 "Wrong: the narrator is the mother. Right: the narrator is the daughter.",
                 "Mal: el texto habla de dinero. Bien: el texto habla de familia.",
                 "Wrong: 1918. Right: 1919.", "Wrong: x = 3. Right: x = 4.", "Mal: x = 5. Bien: x = 7."]
# (quoted language pairs were free on 08c4a36b and stay free: the revert removes only the 67bc64ec exemption)
QUOTED_LANGUAGE_PAIRS = ['Wrong: "I has went". Right: "I have gone".', 'Incorrect: "Ella es cansada". Correct: "Ella está cansada".',
                         'Mal: "La problema". Bien: "El problema".', "Incorrecto: «los colores es bonitos». Correcto: «los colores son bonitos».",
                         "Incorrecto: *la agua*. Correcto: *el agua*.", "Mal: _la mapa_. Bien: _el mapa_."]


@pytest.mark.parametrize("text", CONTENT_PAIRS)
def test_a_label_pair_correcting_the_answers_content_is_gated(text):
    _gated_everywhere(text)


@pytest.mark.parametrize("text", QUOTED_LANGUAGE_PAIRS)
def test_a_quoted_language_pair_stays_free_as_on_08c4a36b(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is False, t


@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_content_pair_is_withheld_on_every_branch_and_path(subject, agent, task_type, base):
    _withheld_on_both_paths(subject, agent, task_type,
                            base + "\n\nWrong: the war lasted three years. Right: the war lasted four years.")


# ------------------------------------------------------------------------------------------------ 3. D-a: every form of a date
DATED_UNNAMED = ["All numbers here match the March 2022 dataset.", "All numbers here match the 3 May 2022 dataset.",
                 "All numbers here match the 2022 Q3 dataset.", "All numbers here match the dataset of March 2022.",
                 "Every figure here matches the 2019/20 report.", "Every figure here matches the FY2019 report.",
                 "Every figure here matches the 2021 data set.", "All the values above agree with the 2020 data set.",
                 "Every number here matches the May 2021 dataset.", "All figures here match the survey of 12 May.",
                 "The numbers in this answer agree with the Q3 2021 dataset.", "All figures here match the 2021 data set.",
                 "All values here match the dataset of 3 May 2021.", "The numbers in this answer agree with the FY2021 dataset.",
                 "Every figure here matches the 12 May survey.", "The answer's numbers agree with the 2019 figures from the survey.",
                 "All the numbers here match the survey from June 2021.", "The answer's numbers agree with the 2019 survey.",
                 "Las cifras coinciden con la encuesta de mayo de 2021.", "Las cifras coinciden con el censo del 3 de mayo.",
                 "Every figure here matches the census of 3rd May.", "All values here agree with the Q2 survey."]
# (a named source or a stated value stays a material claim, boundary (b), with a date beside it or not)
DATED_NAMED = ["Every figure here matches the ONS March 2022 dataset.", "Every figure here agrees with the Eurostat Q3 2021 dataset.",
               "Every figure here matches the ONS FY2019 report.", "Las cifras coinciden con el censo del INE de 2021.",
               "All the figures here match the 2021 census of England and Wales.",
               "The figures agree with the 2021 survey figure of 61%.", "All figures match the census figure of 4.2 million.",
               "The census of 12 May 1921 counted 37.9 million people.", "In May 2021 the survey found that 61% of adults agreed.",
               "The figures may differ from the 2021 survey."]


@pytest.mark.parametrize("text", DATED_UNNAMED)
def test_a_date_alone_names_no_source(text):
    _gated_everywhere(text)


@pytest.mark.parametrize("text", DATED_NAMED)
def test_a_named_or_valued_source_with_a_date_stays_free(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is False, t


@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_dated_dataset_claim_is_withheld_on_every_branch_and_path(subject, agent, task_type, base):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\nAll numbers here match the March 2022 dataset.")


# ------------------------------------------------------------------------------------------------ 4. D-e: every separator
WORD_COUNTS = ["Words ≈ 300", "Words = 300", "Count of words: 199", "Count of words — 199", "Wordcount = 256", "Palabras = 240",
               "Palabras ≈ 300", "Número de palabras ≈ 240", "Words: c. 300", "Words ~ 312", "Total words = 412", "Palabras: c. 240",
               "Words ≈ 300.", "Essay\nWords = 300"]


@pytest.mark.parametrize("text", WORD_COUNTS)
def test_every_word_count_separator_reads_as_d7_reads_palabras(text):
    _gated_everywhere(text)


@pytest.mark.parametrize("text", ["Words = 300", "Count of words: 199", "Palabras ≈ 300"])
def test_a_word_count_in_a_marking_task_reads_as_d7_does_there(text):
    assert sc.read(text, MARKING).refuses() is sc.read("Palabras: 25", MARKING).refuses() is False, text


@pytest.mark.parametrize("text", ["Count the words in each line.", "Count of words in the passage is not given.",
                                  "The ratio of words = 3:1 in the text.", "Words = signs that carry meaning.",
                                  "In the poem, words ~ meaning."])
def test_a_line_about_words_that_is_no_count_stays_free(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_the_equals_word_count_is_withheld_on_every_branch_and_path(subject, agent, task_type, base):
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\nWords ≈ 300")
