"""ES-STR-001 (one idea carried by two strands, each with its own evidence) is a rule of the analytical paragraph and the
essay. It applies when the task type is one, or when the request asks for a paragraph or an essay; a short answer that
quotes once is not held to it (the false alarm on a quoted transcription, c04-quote, and on f07)."""
from __future__ import annotations

from functools import lru_cache

import pytest

from epinoic_logic.adapters.english_specialist.parser import parse_response
from epinoic_logic.adapters.english_specialist.structural import strands_apply, structural_checks
from epinoic_logic.translate.contracts import SuppliedText

from ..argdiag_hub import run_case

POEM = "The house at night is a closed fist.\nThe lamps go out one by one,\nand I am the last thing left awake."
ANSWER = ("The speaker feels trapped by the house. The image \"a closed fist\" makes the house grip the speaker, and the night "
          "closes around her as the lamps go out, so the home that should shelter her holds her instead.")


def _report(task_type: str):
    return parse_response(ANSWER, request_id="r", task_id="t", report_id="rep", task_type=task_type,
                          supplied_texts=[SuppliedText(document_id="poem", text=POEM)])


def _strand_findings(task_type: str, request_text=None) -> list:
    return [f for f in structural_checks(_report(task_type), request_text=request_text) if f.code == "ES-STR-001"]


def test_an_analytical_paragraph_with_one_strand_gets_es_str_001():
    [f] = _strand_findings("analytical_paragraph")
    assert f.severity == "warning" and "two strands" in f.message


def test_a_request_that_asks_for_a_paragraph_brings_the_rule_in():
    assert _strand_findings("short_answer", request_text="Write one analytical paragraph on how the poet presents the house.")
    assert _strand_findings("essay")


@pytest.mark.parametrize("task_type, request_text", [("short_answer", None), ("short_answer", "How does the poet present the speaker's feelings?"),
                                                     ("outline", "Write a paragraph plan."), ("data_response", None)])
def test_a_short_answer_or_an_outline_is_not_held_to_two_strands(task_type, request_text):
    assert _strand_findings(task_type, request_text) == []


def test_strands_apply_reads_the_deliverable():
    assert strands_apply("analytical_paragraph") and strands_apply("Essay") and strands_apply("short_answer", "Answer in a short essay.")
    assert strands_apply("short_answer", "Can you write ONE paragraph in my PETAL and DIE format?")
    assert not strands_apply("short_answer") and not strands_apply("bullet_notes", "a paragraph") and not strands_apply(None)


@pytest.mark.parametrize("request_text", ["Please mark my paragraph and tell me what to fix.", "I want to use this poem in my essay.",
                                          "My paragraph is below; is the quotation embedded well?"])
def test_a_request_that_only_mentions_the_students_own_paragraph_asks_for_none(request_text):
    """Feedback on a student's paragraph is no analytical paragraph of the specialist's (the r7 marking-feedback answer)."""
    assert not strands_apply("marking_feedback", request_text) and _strand_findings("marking_feedback", request_text) == []


@lru_cache(maxsize=None)
def _delivered(case_id: str, mode: str = "text"):
    return run_case(case_id, mode)


@pytest.mark.parametrize("case_id", ["c04_quoted_transcription", "f07_circular_joined_quote"])
def test_the_short_answer_cases_get_no_strand_warning(case_id):
    rc = _delivered(case_id).receipt
    assert [f.code for f in rc.structural_findings if f.code == "ES-STR-001"] == []
    assert not [f for f in rc.findings if "ES-STR-001" in f.message]


def test_the_analytical_paragraph_case_keeps_the_rule():
    """The English e2e answer is an analytical paragraph task: its one-strand paragraphs are still named."""
    rc = _delivered("e2e-B8-en").receipt
    assert [f.code for f in rc.structural_findings if f.code == "ES-STR-001"]
