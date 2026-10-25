"""E2E B18: the request items the coverage heuristic (INT-REQ-004) asks the answer to address are the request's asks, and
an answer that addresses them is not told otherwise.

The ten false "appears unaddressed" warnings of the end-to-end run (cs, ge, lit, mai, sp) came from: a stem that asks
nothing taken for an item ("1. Priya buys a car ...", "2. The heights of sunflowers ...", "2. The Python code ... is
pasted below."); a bare part label ("(a)" before "(i)"); part items the answer covers in its own labelled sections
("(a)(i)", "(ii)"); instructions on the form or language of the answer ("Explain in English pls", "Can you write my thesis
statement properly and then ONE body paragraph proving it with exact quotes?", "Please quote my exact words when you point
out a mistake", which had also lost its word "quote"). The single-item rule clears c03-dich, c04-quote and i02c: a request
with exactly one item has no other item a material claim could be answering."""
from __future__ import annotations

import pytest

from epinoic_logic.channel.bus import _terms
from epinoic_logic.channel.request_parser import extract_constraints, extract_items, is_format_instruction, strip_constraint_spans

from ..argdiag_cases import load_case
from .dev_case_hub import run_case


def _items(run):
    return list(run.channel.requests.values())[-1].items


def _unaddressed_warnings(run):
    return [f for f in run.receipt.findings if f.code == "INT-REQ-004" and f.severity == "warning"]


@pytest.mark.parametrize("case_id", ["e2e-B18-cs", "e2e-B18-ge", "e2e-B18-lit", "e2e-B18-mai", "e2e-B18-sp"])
def test_the_e2e_answers_are_not_told_they_leave_an_item_unaddressed(case_id):
    run = run_case(case_id)
    assert not _unaddressed_warnings(run)
    required = [i.item_id for i in _items(run) if i.required]
    covered = {c.item_id for c in run.receipt.coverage if c.addressed}
    assert required and set(required) <= covered


@pytest.mark.parametrize("case_id, stem", [
    ("e2e-B18-mai", "1. Priya buys a car"),
    ("e2e-B18-mai", "2. The heights of sunflowers"),
    ("e2e-B18-cs", "2. The Python code from the practice sheet is pasted below."),
    ("e2e-B18-ge", "Selvaria"),
])
def test_a_stem_that_asks_nothing_is_no_item(case_id, stem):
    items = _items(run_case(case_id))
    assert not [i for i in items if i.text.startswith(stem)]
    assert len([i for i in items if i.text.startswith(("(a)", "(i)"))]) >= 1          # its sub-parts are the items


def test_a_bare_part_label_is_no_item_and_its_sub_parts_are():
    items = [i.text for i in _items(run_case("e2e-B18-ge"))]
    assert "(a)" not in items
    assert items[0].startswith("(i) Calculate") and items[1].startswith("(ii) Estimate")


def test_part_items_are_covered_by_the_answer_sections_with_their_labels():
    run = run_case("e2e-B18-ge")
    by_id = {c.item_id: c for c in run.receipt.coverage}
    for item in _items(run):
        assert by_id[item.item_id].addressed and by_id[item.item_id].method == "part_label", item.text


def test_a_table_answers_construct_the_table():
    run = run_case("e2e-B18-cs")
    item = next(i for i in _items(run) if "Construct the truth table" in i.text)
    assert next(c for c in run.receipt.coverage if c.item_id == item.item_id).addressed


@pytest.mark.parametrize("answer, addressed", [
    ("| A | B | X |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |", True),   # the table, nothing else
    ("The weather was mild and sunny all week.", False),                                               # control: no table
])
def test_the_lexical_reading_counts_a_table_for_construct_the_table(answer, addressed):
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.integrity import WorkPlan
    hub = RouterHub(signing_key=b"b18-table-key-0123456789abcdef0123")
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Economics", task_type="structured_question", selected_agent_ids=["economics-specialist"]))
    m, _req, _rq = hub.dispatch("t", "economics-specialist", "Construct the truth table for X = A AND B.")
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="economics-specialist", report_id="rep-table")
    assert rc.coverage[0].addressed is addressed and rc.coverage[0].method == "lexical_heuristic"
    assert bool([f for f in rc.findings if f.code == "INT-REQ-004" and f.severity == "warning"]) is (not addressed)


@pytest.mark.parametrize("text", [
    "Explain in English pls",
    "Please quote my exact words when you point out a mistake.",
    "Can you write my thesis statement properly and then ONE body paragraph proving it with exact quotes?",
])
def test_an_instruction_on_the_form_or_language_of_the_answer_is_no_required_item(text):
    assert is_format_instruction(text)
    items = [i for i in extract_items(f"Read my essay. {text}") if i.text == text]
    assert items and items[0].required is False


@pytest.mark.parametrize("text", [
    "Please explain why the tax is regressive.",
    "Prove the statement.",
    "Explain in English why the poem's ending is hopeful.",
    "Please quote the line where the speaker changes her mind and explain it.",
])
def test_an_instruction_that_asks_for_content_stays_required(text):
    assert not is_format_instruction(text)
    assert all(i.required for i in extract_items(text))


def test_the_word_quote_is_kept_and_the_citing_constraint_still_extracted():
    text = "Please quote my exact words when you point out a mistake."
    assert "quote" in strip_constraint_spans(text)
    assert [c.kind for c in extract_constraints(text)].count("must_cite_supplied_text") == 1
    assert "quote" in next(i.text for i in extract_items(text))


@pytest.mark.parametrize("case_id", ["c03_true_dichotomy", "c04_quoted_transcription", "i02c_control_rct_cause"])
def test_the_only_item_of_a_request_is_addressed_by_a_material_claim_on_its_topic(case_id):
    run = run_case(case_id)
    items = _items(run)
    assert len([i for i in items if i.required]) == 1
    assert run.receipt.coverage[0].addressed and not _unaddressed_warnings(run)


def test_stems_match_y_to_ies():
    assert _terms("the effect of CCTV on burglary") & _terms("burglaries fell by 30%")
    assert _terms("one study") & _terms("two studies")


@pytest.mark.parametrize("subject, agent, ask, answer", [
    ("History", "history-specialist",
     "Evaluate the claim that the collapse of parliamentary government in Germany between 1930 and 1932 was caused by the Great "
     "Depression. Write a short response of no more than 250 words with dated evidence.",
     "García Márquez thus encourages the reader to test the claim rather than accept it. The key word is the adverb, which "
     "conventionally means publicly. Ultimately the reader is left to weigh a declared innocence against a guilt the text keeps."),
    ("English A: Literature", "english-specialist",
     "Write one analytical paragraph on how the extract constructs the reader's view of guilt and innocence. Quote from the extract.",
     '"For the immense majority of people there was only one victim: Bayardo San Roman."'),
])
def test_the_single_item_rule_never_counts_form_words_or_the_frame_of_the_ask(subject, agent, ask, answer):
    # an answer on another subject that shares only "claim" (the frame of "Evaluate the claim that ..."), and a bare
    # quotation that shares only "one" (the form of "Write one analytical paragraph ..."), address nothing
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.integrity import WorkPlan
    hub = RouterHub(signing_key=b"b18-single-item-key-0123456789abcd")
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, req, _rq = hub.dispatch("t", agent, ask)
    assert len([i for i in req.items if i.required]) == 1
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-x")
    assert [f for f in rc.findings if f.code == "INT-REQ-004" and f.severity == "warning"]


def test_the_single_item_rule_needs_a_claim_on_the_request_topic():
    case = load_case("i02c_control_rct_cause")
    case["answer"] = "Two plus two is four. The weather was mild that year."
    case["translations"] = []
    run = run_case("i02c_control_rct_cause", case=case)
    assert not run.receipt.coverage[0].addressed and _unaddressed_warnings(run)


def test_an_unaddressed_real_part_still_warns():
    case = load_case("e2e-B4-bm")
    start = case["answer"].index("**(c) [3]**")
    end = case["answer"].index("**(d) [2]**")
    case["answer"] = case["answer"][:start] + case["answer"][end:]
    run = run_case("e2e-B4-bm", case=case)
    item = next(i for i in _items(run) if i.text.startswith("(c) Calculate the margin of safety"))
    assert not next(c for c in run.receipt.coverage if c.item_id == item.item_id).addressed
    assert [f for f in _unaddressed_warnings(run) if item.item_id in f.message]


def test_a_numbered_part_that_asks_something_stays_an_item_before_its_sub_parts():
    items = [i.text for i in extract_items("1. Calculate the mean of the data. [2]\n(a) State the median. [1]\n(b) State the mode. [1]")]
    assert items[0].startswith("1. Calculate the mean") and len(items) == 3


def test_parts_of_a_non_english_request_stay_items():
    text = ("3. Indica si las siguientes frases son verdaderas (V) o falsas (F). a) En el huerto se usan productos químicos. "
            "b) El proyecto ha ayudado a personas mayores. 4. ¿Qué temen algunos comerciantes de la zona?")
    items = [i.text[:2] for i in extract_items(text)]
    assert items == ["3.", "a)", "b)", "4."]
