"""Round-10 clearance (integrated round c3), handoff pass: channel items the parallel fixers handed over.

* Critical records 3 and 11 (handoffs H2 and H4 of the parsers, H2 of STEM): a word bound read meta-text from a closed list and set
  aside only a sliver of the working, so ess-t16 (a correct answer of 433 words of prose under "no more than 450 words in total, plus
  working") drew an error-level INT-REQ-005 at 457 words. Now a paragraph a meta lead opens ("Assumption: ...", "One correction for
  your planning: ...", rule meta-lead) is meta-text when what it says after the lead is about the task, the sources or the method; a
  note about the answer inside a paragraph of content leaves its own words out (``markdown.is_answer_note``); part labels and mark
  annotations are no words of any branch's answer; the result line of a calculated part ("Answer: 3,660 t ...") is working.
* Overseer handoff 5 (c3 maa-t16): a line "f(x) = (x + 3)(x − 3)²" was read as the compound part label "f(x)" (part f, sub-part x),
  so part (c)'s claims stood under section f and the request item (c) was reported unaddressed (INT-REQ-004).
* Parsers handoff H6.1 (c3 mai-t16 i5): a 'justify' item answered by a point claim that gives its reason ("..., so this stationary
  point is a minimum") drew INT-REQ-008 ("no judgement/point claim was found").
* Parsers handoff H5 (major record 7): request items (a scenario sentence is no item; "so state ..." belongs to its item; a bracket
  inside a part is no part label), pinned here on the shapes the record names.
* Overseer handoff 5 (feedback-rules/1): the quotation feedback says that words the writer gives as its own (a correction, a model, a
  gloss, a suggested form) are to be marked as such, not removed; a quotation of a text that no text holds is still to be removed.

The recorded material is ``data/c3_core_material.json`` and ``data/c3_handoff_material.json`` (copied verbatim from the round).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.channel import feedback as fb
from epinoic_logic.channel import request_parser as RP

from ..core_hostile import SHAPES, one, sweep
from .c3_core_support import C3, _deliver

HANDOFF = json.loads((Path(__file__).parent / "data" / "c3_handoff_material.json").read_text(encoding="utf-8"))


def _item(task: str) -> dict:
    return HANDOFF["c3"]["specialists"].get(task) or C3["c3"]["specialists"][task]


def _receipt(task: str, text: str | None = None):
    hub, _ch, reply, rc = _deliver(_item(task), None, text)
    hub.close()
    return reply, rc


def _codes(rc, *codes):
    return [f for f in rc.findings if f.code in codes]


# ------------------------------------------------------------------------------------------ the word measure

def test_ess_t16_meets_its_bound_and_its_assumption_note_is_meta_text():
    _reply, rc = _receipt("ess-t16")
    assert not _codes(rc, "INT-REQ-005"), [(f.severity, f.message[:200]) for f in _codes(rc, "INT-REQ-005")]
    text = _item("ess-t16")["response_text"]
    first = text.split("\n\n")[0]
    assert first.startswith("Assumption:") and RP.is_meta_lead_paragraph(first) and RP.is_meta_paragraph(first)
    words, notes, exempt = RP.measure_answer_words(text, excludes=("working",))
    assert words <= 450 and notes >= 24 and exempt > 0, (words, notes, exempt)


def test_control_ess_t16_with_prose_over_its_bound_is_still_an_error():
    text = _item("ess-t16")["response_text"]
    extra = " ".join(["Rewetting also changes the habitat of the bog in ways that the booklet describes only in part."] * 4)
    longer = text.replace("On balance, rewetting is effective", extra + "\n\nOn balance, rewetting is effective")
    _reply, rc = _receipt("ess-t16", longer)
    over = _codes(rc, "INT-REQ-005")
    assert over and over[0].severity == "error", [(f.code, f.message[:160]) for f in rc.findings]


@pytest.mark.parametrize("para, meta", [
    ("Assumption: SL, Paper 1 practice. The Halden Moss booklet is a fictional practice case, so I use its figures as given and do not "
     "check them against outside data.", True),
    ("One correction for your planning: at HL, Paper 1 gives two passages and you write one analysis on each rather than choosing one.", True),
    ("Assumptions: all figures are in $, as the case states.", True),
    # a marked assumption is the answer's own content (bi-t14: an assumption a part asks for, with its mark)
    ("Assumption: marked beetles mix randomly with the unmarked beetles before the second catch. [1]", False),
    # content after the lead's sentence keeps the paragraph the answer's
    ("Assumption: the market is competitive. Demand for timber falls as its price rises, so revenue falls.", False),
    # a lead that names no assumption, correction, clarification, caveat or disclaimer
    ("Analysis: rewetting raises the water table, so decomposition slows.", False),
])
def test_rule_meta_lead_reads_what_the_paragraph_says(para, meta):
    assert RP.is_meta_lead_paragraph(para) is meta


def test_a_meta_lead_never_leaves_a_response_with_no_answer():
    """An answer that is nothing but a paragraph a meta lead opens is that paragraph (INT-REQ-012 reads this measure): rule meta-lead
    sets such a paragraph aside only beside an answer proper."""
    only = ("Assumptions: 1 MB = 10⁶ bytes. The question does not define Mbit, so this answer reads Mbit as 10⁶ bits, the SI meaning "
            "of the prefix M.")
    words, notes, _ = RP.measure_answer_words(only)
    assert words == RP.count_words(only) and notes == 0 and RP.count_paragraphs(only) == 1
    beside = only + "\n\nThe file takes 14.4 seconds to send at 1 Mbit per second."
    words, notes, _ = RP.measure_answer_words(beside)
    assert words == RP.count_words("The file takes 14.4 seconds to send at 1 Mbit per second.") and notes == RP.count_words(only)
    assert RP.count_paragraphs(beside) == 1


def test_a_note_about_the_answer_inside_a_paragraph_of_content_leaves_out_its_own_words_only():
    content = "The Act banned the employment of children under nine in textile mills. It also set up a paid inspectorate."
    note = "Casualty and cost figures are left out, because I cannot confirm exact numbers here; take them from your textbook and cite them."
    words, notes, _ = RP.measure_answer_words(content + " " + note)
    assert words == RP.count_words(content) and notes == RP.count_words(note)


def test_part_labels_and_mark_annotations_are_no_words_on_any_branch():
    text = "(a) The Act banned child labour in mills. [1]\n(b) It set up an inspectorate. [2 marks]"
    words, _notes, _ = RP.measure_answer_words(text)
    assert words == RP.count_words("The Act banned child labour in mills. It set up an inspectorate.")
    assert RP.count_paragraphs("(a) [2]\n\nThe Act banned child labour in mills.") == 1


def test_the_result_line_of_a_calculated_part_is_working():
    text = "(b) Carbon dioxide released = 610 ha × 6.0 t = 3,660 t\nAnswer: 3,660 t of carbon dioxide each year"
    words, _notes, exempt = RP.measure_answer_words(text, excludes=("working",))
    assert words == 0 and exempt > 0
    # without working lines in its paragraph, an 'Answer:' line is prose
    words, _notes, _ = RP.measure_answer_words("Answer: the Act mattered most because it set up inspection.", excludes=("working",))
    assert words > 0


# ------------------------------------------------------------------------------------------ coverage, command terms, items

def test_maa_t16_part_c_is_addressed_and_a_function_line_is_no_part_label():
    _reply, rc = _receipt("maa-t16")
    assert not _codes(rc, "INT-REQ-004"), [f.message[:160] for f in _codes(rc, "INT-REQ-004")]
    assert RP.compound_label("f(x) = (x + 3)(x − 3)²  A1") is None and RP.compound_label("g(x) ≥ 0") is None
    assert RP.compound_label("(a)(i) [1]") == "a.i" and RP.compound_label("a(ii) Calculate the mean.") == "a.ii"


def test_mai_t16_justify_is_answered_by_a_point_that_gives_its_reason():
    _reply, rc = _receipt("mai-t16")
    assert not _codes(rc, "INT-REQ-008"), [f.message[:160] for f in _codes(rc, "INT-REQ-008")]


def test_control_a_justify_item_with_no_reason_given_is_still_named():
    item = dict(_item("mai-t16"))
    item["question"] = "(a) Justify that the stationary point is a minimum. [2]"
    hub, _ch, _reply, rc = _deliver(item, None, "The stationary point is at r = 3.75.")
    hub.close()
    assert _codes(rc, "INT-REQ-008")


@pytest.mark.parametrize("question, texts", [
    ("(a) Show that the coefficient of x is (c + 3b). [2] (b) Find x when f(x) = 0. [2]",
     ["(a) Show that the coefficient of x is (c + 3b). [2]", "(b) Find x when f(x) = 0. [2]"]),
    ("The city of Port Aldwyn runs 240 diesel buses. Each bus uses 50 kg of fuel a day. (a) Calculate the mass of fuel used per day. [2] "
     "(b) Calculate the mass of carbon dioxide released, and so state whether the target is met. [2]",
     ["(a) Calculate the mass of fuel used per day. [2]", "(b) Calculate the mass of carbon dioxide released, and so state whether the target is met. [2]"]),
    ("(a) Calculate the mean. [2] So state your answer to 3 s.f. (b) Explain the trend. [2]",
     ["(a) Calculate the mean. [2] So state your answer to 3 s.f.", "(b) Explain the trend. [2]"]),
])
def test_request_items_scenario_sentences_closing_instructions_and_brackets(question, texts):
    from epinoic_logic.stem.hub_hooks import STEM_HOOKS
    items = RP.extract_items(question, extra_imperatives=tuple(STEM_HOOKS.request_imperatives))
    assert [i.text for i in items] == texts


CS_P10A_HEAD = ("I'm a Computer Science HL student (the course first assessed in May 2027; my exams are in May 2027). Paper 1 Section A "
                "practice on A4.3, machine learning approaches. A recycling plant uses a camera and a k-nearest neighbours classifier (k = 5) to "
                "decide whether each item on a conveyor belt is aluminium (positive) or not aluminium (negative). On a labelled test set of 600 "
                "items, the classifier correctly identified 132 aluminium items. ")


@pytest.mark.parametrize("extra", [(), ("find", "solve")], ids=["general", "stem imperatives"])
def test_a_scenario_sentence_before_the_labelled_parts_is_no_item(extra):
    """Round-10 leftover R10-PARSERS-7 (c3 cs-p10a i1): the scenario sentence 'A recycling plant uses a camera ... to decide whether
    each item ... is aluminium ...' was a request item of its own (its 'to decide' read as a command). An infinitive of purpose in a
    sentence that sets the scene asks for nothing: the parts are the items. A sentence that addresses the writer, states an
    obligation, opens with a command or asks a question is still an item (controls)."""
    question = CS_P10A_HEAD + "(a) Construct the confusion matrix for the test set. [2] (b) Calculate the accuracy. [3]"
    items = RP.extract_items(question, extra_imperatives=extra)
    assert [i.text for i in items] == ["(a) Construct the confusion matrix for the test set. [2]", "(b) Calculate the accuracy. [3]"]
    assert RP.is_scenario_sentence("A recycling plant uses a camera to decide whether each item is aluminium.")
    for sentence in ("Use Source A to explain why the treaty failed.", "The essay should use evidence to explain the decline.",
                     "Your answer needs to describe the method.", "A survey was carried out; explain what it shows.",
                     "The plant manager says that the classifier is reliable. Is it?", "The question asks you to evaluate the claim."):
        assert not RP.is_scenario_sentence(sentence), sentence
    assert [i.text for i in RP.extract_items("The plant sorts cans. Use the data to explain why accuracy misleads.")] == \
        ["Use the data to explain why accuracy misleads."]


# ------------------------------------------------------------------------------------------ feedback wording

def test_the_quotation_feedback_asks_first_and_keeps_the_removal_of_an_invented_quotation():
    text = fb.render_instruction("src.quote_not_found", {})
    assert "Quote the words exactly as the text gives them" in text and "remove the quotation and what is credited to it" in text
    assert "If the words are your own (a correction, a model, a gloss or a suggested form)" in text and len(text) <= 500


# ------------------------------------------------------------------------------------------ hostile input

@pytest.mark.parametrize("shape", SHAPES)
def test_the_new_measure_readers_are_linear_on_hostile_input(shape):
    def entries(text):
        yield "meta lead", lambda: RP.is_meta_lead_paragraph("Assumption: " + text)
        yield "meta paragraph", lambda: RP.is_meta_paragraph("One correction for your planning: " + text)
        yield "labels and marks", lambda: RP.blank_labels_and_marks(text)
        yield "measure (working)", lambda: RP.measure_answer_words("Answer: 5 = " + text, excludes=("working",))
        yield "paragraphs", lambda: RP.count_paragraphs(text)
        yield "compound label", lambda: RP.compound_label(text)

    assert not sweep(entries, texts=one(shape)), shape
