"""Repair round 4, ADV4-10: an argument written in one sentence ("A, so B", "B because A", "Since A, B") argues for something,
so the generic and the STEM parsers give it materiality 'material' whatever its role, as the History and English parsers
do. A warning named on such a claim then reaches the receipt as INT-ARG-001 (a one-sentence paragraph has no point, so
the claim stayed 'supporting' and the receipt ACCEPTED with no finding). Controls: a sentence that states no reason of its
own, a note and a line of working keep their materiality."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import default_registry


def _claims(subject: str, text: str):
    branch, _profile = default_registry().for_subject(subject)
    report = branch.parser().parse_response(text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type="short_answer",
                                            supplied_texts=[], agent_id=f"{subject.lower().split()[0]}-specialist")
    return report.claims


@pytest.mark.parametrize("subject, text", [
    ("Geography", "The town opened a new library in 2015, and after that river pollution fell in 2016, so the new library caused the fall in river pollution."),
    ("Psychology", "Nine of the twelve students in our class prefer online lessons, so most students in the country prefer online lessons."),
    ("Economics", "Demand for the firm's product fell because the price of a substitute fell by 20 per cent."),
    ("Biology", "Natural selection is the survival of the fittest, and the fittest people are those who exercise most, so natural selection favours people who exercise most."),
])
def test_an_argument_in_one_sentence_is_material(subject, text):
    [claim] = _claims(subject, text)
    assert claim.materiality == "material" and claim.claim_role != "other"


@pytest.mark.parametrize("subject, text", [
    ("Geography", "River pollution in the town fell in 2016."),
    ("Economics", "The price of the substitute fell by 20 per cent in 2023."),
    ("Biology", "Mitochondria contain their own circular DNA."),
])
def test_control_a_sentence_with_no_reason_of_its_own_keeps_its_materiality(subject, text):
    [claim] = _claims(subject, text)
    assert claim.materiality == "supporting"
