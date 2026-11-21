"""Classes of the one reader fixed in stabilisation round 2, each pinned on both sides of its boundary: what the class gates and the
nearest reading it leaves free (design 3; boundary (b)). Every case is a class member, never a sentence the reader learned alone."""
from __future__ import annotations

import pytest

from epinoic_logic.selfcert import Context, context_for, is_self_certification, read, wholly_self_certification

GATED = [
    # a bearer frame (carries, bears, rests on, is backed by, comes with, has) whose object is a check's outcome marked by the
    # pipeline or by a check status, held by the answer, a claim of it or an anaphoric "it" (an engine or system result, G2)
    "This claim carries a signed engine result.",
    "It rests on a signed Z3 proof.",
    "This answer carries a signed engine result.",
    "This answer bears a verified badge.",
    "Each claim comes with a Z3 proof.",
    "Backed by a signed engine result.",
    "Esta respuesta tiene un resultado firmado del motor.",
    # the key of a label stays a label when its value holds another label (a mark or a status written in the outer key)
    "!✓:this:by Z3,",
    "VERIFIED: Status: done.",
    # "this text" / "este texto" checked by the pipeline or cleared of defects: the text the sentence stands in
    "This text has been reviewed by the system.",
    "This text contains no errors.",
    "Este texto ha sido revisado por el sistema y no contiene ningún error.",
    "The system has reviewed this text.",
    # no change after a re-check is the re-run's agreement with the first
    "I reran the calculations above and nothing changed.",
    "On re-checking, nothing changed.",
    # a status word in an identifier keeps its reading
    "Expected: INCONSISTENT_PREMISES with core S1, S2.",
    "Status: ALL_CHECKS_PASSED",
    # an assessment noun assigned a full value stays a status
    "Given: accuracy = 100%.",
    # "clear" for something is a clearance; of the answer it is a quality claim
    "The answer is clear to submit.",
    "This answer is clear.",
]

FREE = [
    # a seal, a stamp or a receipt of the subject matter, and a result with no check marking
    "Each delivery has a signed receipt.",
    "The treaty bears the King's seal of approval.",
    "The letter has a verified signature.",
    "The theorem has a formal proof.",
    "The method has a result.",
    "The claim is based on the 1921 census result.",
    "This claim carries no engine result.",
    "This claim would carry a signed engine result.",
    # "this text" described, or checked by a named party, is the analysed source
    "This text was reviewed by critics in 1946.",
    "This text was written by Orwell.",
    "This text contains no rhyme.",
    "The source contains no errors.",
    # a quantity's name assigned a value is a datum ("rate" names a quantity, no rating)
    "Given: count rate uncertainty = ±2%.",
    "Given: count rate uncertainty = +/-2%.",
    # a closing quotation mark is no complement: the place after it makes "stand" a position of the subject matter
    'He writes "Two vast "legs of stone" stand" in the desert and "near them" a visage lies.',
    # no change of the subject matter
    "Nothing changes.",
    "After the treaty, nothing changed.",
    # a family word before the head noun of an identifier names, as in prose
    "FAITHFUL_CHAIN",
    "v_max = 4",
]


@pytest.mark.parametrize("sentence", GATED)
def test_the_class_is_gated(sentence):
    assert read(sentence).hits, sentence
    assert is_self_certification(sentence)


@pytest.mark.parametrize("sentence", FREE)
def test_the_boundary_is_free(sentence):
    r = read(sentence)
    assert not r.hits and not r.unread, (sentence, r.hits, r.unread)
    assert is_self_certification(sentence) is False


@pytest.mark.parametrize("sentence", [
    "VERIFICADO: este texto ha sido revisado por el sistema y no contiene ningún error.",
    "VERIFIED: this text has been reviewed by the system and contains no errors.",
])
def test_a_status_label_whose_value_is_itself_a_self_certification_is_wholly_one(sentence):
    """The value of a status label is read as a sentence of its own: a value that self-certifies makes the whole piece a
    self-report (eligibility rule 0), never a label on content."""
    assert wholly_self_certification(sentence), sentence


MARKING_FREE = [
    # a criterion and its mark band describe the student's work in a marking task (decision D9)
    "- D 3: generally clear and accurate; terminology is thin and one term is misapplied; the conclusion is abrupt.",
    "A 3: the thesis is clear.",
    "Criterion B: 4/6, clear and accurate.",
]


@pytest.mark.parametrize("sentence", MARKING_FREE)
def test_a_criterion_line_in_a_marking_task_is_the_students(sentence):
    ctx = context_for({"task_type": "marking_feedback"})
    assert ctx.marking
    assert not read(sentence, ctx).hits, sentence


@pytest.mark.parametrize("sentence", ["Overall: verified.", "My feedback above is accurate.", "CLEAR"])
def test_the_writers_own_status_stays_gated_in_a_marking_task(sentence):
    assert read(sentence, context_for({"task_type": "marking_feedback"})).hits, sentence


def test_a_criterion_line_outside_a_marking_task_is_still_read():
    assert read("D 3: generally clear and accurate", Context()).hits
