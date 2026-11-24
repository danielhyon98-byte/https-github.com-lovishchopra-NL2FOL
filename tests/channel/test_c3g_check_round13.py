"""Check round 13 of the c3g follow-up on the own-correction reader (expected values fixed here): a correction whose two halves are both
versions of one supplied text's wording, neither exact, and that wording stands outside the text's quotation marks (the student's own
email): the replaced half is the misquotation, charged as one, and the corrected half the writer's correction of it, never checked as a
quotation of the text ('Wrong: "La primer semana fue difícil". Right: "La primera semana fue difícil"' on the student's "El primer semana
fue difícil"). A quoted source's wording (an advert's slogan inside the notes' quotation marks) keeps its corrected half checked."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import own_text as ot


@pytest.mark.parametrize("text, docs, expected", [
    ('Wrong: "La primer semana fue difícil". Right: "La primera semana fue difícil".',
     {"s": "Hola Marta: El primer semana fue difícil, pero ahora estoy bien."}, {}),
    ('Wrong: "a b c d e". Right: "a b c x f".', {"n": 'It says "a b c d f" there.'}, {1: ot.CORRECTION_QUOTATION}),
])
def test_a_correction_of_the_students_misquoted_wording_is_no_quotation(text, docs, expected):
    assert ot.correction_reading(text, docs) == expected
