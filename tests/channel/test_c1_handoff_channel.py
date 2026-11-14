"""Round-8 clearance (integrated round c1), handoff fixer: the request reader's items and citation constraint (the parsers
fixer's handoff item 2; critical finding "whole questions are dropped from the request items").

* "Question 2 [5 marks]: Solve ..." and "Question 3 [5 marks]: Solve ... Show full working." (maa-t14) are items with their
  own text, after Question 1's lettered parts; Question 1's stem is no item (its parts are), and the answer's own
  "Question 2" heading addresses the item of Question 2, so a reply that leaves Questions 2 and 3 out is seen leaving them
  out (INT-REQ-004);
* a sentence about a third party's later use of the answer ("A Psychology student will use your answer to evaluate ...",
  bi-p8d; the same in ec-p8a), a permission ("Since we're allowed to use our GDC in Paper 1, ...", maa-t14) or the student's
  own description of a paper ("... it only asks me to discuss the study ...", breadth ps-3) is context: no item, and its
  command term raises no INT-REQ-008;
* an instruction about form ("Skip the plan and give the full answer now.", "Write a model answer to this practice task in
  Spanish.", breadth ec-1 and sp-1) makes no coverage item, while one that names a topic still does;
* "quoting exactly from the extract" (lit-t14, ll-t14) asks for quotations (must_cite_supplied_text), as "Use quotations"
  already did.

The recorded requests are the round's own (``tests/fixtures/stem/round8/c1_answers.json``, ``tests/branches/c1_texts.py``,
``tests/channel/data/c1_core_material.json``); the breadth requests are quoted from the breadth round's specialists."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.channel.request_parser import (extract_constraints, extract_items, is_context_sentence, question_label,
                                                  question_pieces)
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SuppliedText

from ..branches import c1_texts as C
from ..core_hostile import SHAPES, one, sweep
from ..timing import measure
from .c1_core_support import CFG, KEY, SPEC, by_code, deliver

ROOT = Path(__file__).resolve().parents[2]
ANSWERS = json.loads((ROOT / "tests" / "fixtures" / "stem" / "round8" / "c1_answers.json").read_text(encoding="utf-8"))["answers"]

#: Breadth round b1's requests (the specialists' recorded questions), quoted verbatim.
PS_3_Q = ("Psychology, SL, Paper 2. Section B of Paper 2 is worth 25 marks, I get 60 minutes for it, and it only asks me to discuss the study "
          "through one concept. How many minutes per mark does that give me, and how should I split the 60 minutes between planning and writing?")
SP_1_Q = ("Spanish B, SL, Paper 1 (productive skills: writing), the 2020 syllabus; my exams are in May 2027. Write a model answer to this practice "
          "task in Spanish. Skip the plan and give the full text now. Tarea: Tu instituto quiere reducir el uso de plástico en la cafetería. "
          "Escribe un texto para convencer a los estudiantes de que participen en la campaña «Cero plástico». Elige uno de estos tipos de texto: "
          "artículo para la revista escolar, discurso, folleto. I choose the article for the school magazine. Write no more than 450 words.")


def _items(question: str, subject: str):
    branch, _profile = default_registry().for_subject(subject)
    hooks = getattr(branch, "hub_hooks", None)
    return extract_items(question, extra_imperatives=hooks.request_imperatives) if hooks else extract_items(question)


# ------------------------------------------------------------------------------------ questions are items (maa-t14)


def test_every_question_of_maa_t14_is_an_item_with_its_own_text():
    q = SPEC["maa-t14"]["question"]
    items = _items(q, SPEC["maa-t14"]["subject"])
    texts = [i.text for i in items]
    assert texts[:3] == [t for t in texts if t.startswith(("(a)", "(b)", "(c)"))]
    assert "Question 2 [5 marks]: Solve the equation log₃(x + 4) + log₃(x − 4) = 2." in texts
    assert any(t.startswith("Question 3 [5 marks]: Solve the equation 2^(2x+1) − 5 × 2^x + 2 = 0.") for t in texts)
    assert not any("allowed to use our GDC" in t or "A swimmer's training plan" in t for t in texts)  # a permission, Question 1's stem
    assert len(items) == 5 and [question_label(t) for t in texts[3:]] == ["q2", "q3"]
    assert [ok for ok, _piece in question_pieces(q)] == [False, True, True, True]


def test_the_answers_question_headings_address_the_questions_and_a_reply_that_leaves_them_out_is_named():
    text = SPEC["maa-t14"]["response_text"]
    _h, _c, _reply, rc = deliver("maa-t14")
    assert all(c.addressed for c in rc.coverage) and {c.method for c in rc.coverage} == {"part_label"}
    assert not by_code(rc.findings, "INT-REQ-004")
    _h, _c, _reply, rc = deliver("maa-t14", text[:text.find("Question 2")])
    named = by_code(rc.findings, "INT-REQ-004")
    assert len(named) == 2 and "Question 2 [5 marks]" in named[0].message and "Question 3 [5 marks]" in named[1].message
    _h, _c, _reply, rc = deliver("maa-t14", text[:text.find("Question 3")])
    [named] = by_code(rc.findings, "INT-REQ-004")
    assert "Question 3 [5 marks]" in named.message


@pytest.mark.parametrize("request_text,expected", [
    ("Question 1: Explain inflation. Question 2: Explain deflation.", ["Question 1: Explain inflation.", "Question 2: Explain deflation."]),
    ("QUESTION 1. Define GDP.\nQUESTION 2. Define GNI.", ["QUESTION 1. Define GDP.", "QUESTION 2. Define GNI."]),
    ("Answer question 2. Explain inflation.", ["Explain inflation."]),  # a mention, no heading: the general reading
    ("Question 2.5 is hard. Explain inflation.", ["Explain inflation."]),
])
def test_question_headings_cut_the_request_and_a_mention_does_not(request_text, expected):
    assert [i.text for i in extract_items(request_text)] == expected


@pytest.mark.parametrize("extra", [(), ("find", "solve")])
def test_question_headings_on_lines_of_their_own_cut_the_request_too(extra):
    """A request that sets each question heading on a line of its own ("Question 2 [5 marks]" and its text below), with or
    without the STEM branches' imperatives (which cut a request at its part lines too): each question is an item."""
    q = ("Paper 1 practice.\nQuestion 1 [7 marks]\nA swimmer trains.\n(a) Find the daily increase. [3]\n(b) Find the total time. [2]\n"
         "Question 2 [5 marks]\nSolve the equation x + 1 = 2.\nQuestion 3 [5 marks]\nSolve 2x = 4. Show full working.")
    texts = [i.text for i in extract_items(q, extra_imperatives=extra)]
    assert texts == ["(a) Find the daily increase. [3]", "(b) Find the total time. [2]", "Question 2 [5 marks]\nSolve the equation x + 1 = 2.",
                     "Question 3 [5 marks]\nSolve 2x = 4. Show full working."], texts
    assert [question_label(t) for t in texts[2:]] == ["q2", "q3"]


# --------------------------------------------------------------------------- context is no item (and no INT-REQ-008)


@pytest.mark.parametrize("question,subject,context", [
    (ANSWERS["bi-p8d"]["question"], ANSWERS["bi-p8d"]["subject"], "A Psychology student will use your answer"),
    (C.EC_P8A_Q, "Economics", "A Business Management student will use your answer"),
    (SPEC["maa-t14"]["question"], SPEC["maa-t14"]["subject"], "allowed to use our GDC"),
    (PS_3_Q, "Psychology", "it only asks me to discuss"),
])
def test_a_context_sentence_is_no_item_and_its_command_term_is_not_the_specialists(question, subject, context):
    items = _items(question, subject)
    assert items and not any(context in i.text for i in items), [i.text for i in items]
    assert not any(i.level == 3 and i.command_term in ("evaluate", "discuss") for i in items if context in i.text)


def test_bi_p8d_raises_no_judgement_finding_for_the_third_partys_evaluation():
    item = ANSWERS["bi-p8d"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-bi", request_id="req-bi", task_id="task-bi", subject=item["subject"], task_type="short_answer",
                           selected_agent_ids=["biology-specialist", "dummy-combinator"], allowed_document_ids=[]))
    m, req, _rq = hub.dispatch("task-bi", "biology-specialist", item["question"], [])
    assert not any("Psychology student" in i.text for i in req.items)
    _reply, rc = hub.receive("task-bi", m.message_id, item["response_text"], agent_id="biology-specialist", report_id="rep-bi-0")
    assert not by_code(rc.findings, "INT-REQ-008"), [f.message for f in by_code(rc.findings, "INT-REQ-008")]


@pytest.mark.parametrize("sentence", [
    "Skip the plan and give the full answer now.",
    "Skip the plan and give the full text now.",
    "Write a model answer to this practice task in Spanish.",
    "Give the full answer now.",
    "A Psychology student will use your answer to evaluate a study of stress and memory, so state each result clearly with its units.",
    "Since we're allowed to use our GDC in Paper 1, you can use calculator values and give answers to 3 significant figures.",
    "Section B is worth 25 marks, and it only asks me to discuss the study through one concept.",
])
def test_form_and_context_sentences_are_read(sentence):
    assert is_context_sentence(sentence)
    assert not extract_items("Explain inflation. " + sentence)[1:], extract_items("Explain inflation. " + sentence)


@pytest.mark.parametrize("sentence", [
    "Write an essay on the causes of the war.",
    "Give the full answer to why prices rose.",
    "My teacher asked me to evaluate the policy, so evaluate it.",
    "Since the policy failed, evaluate its design.",
    "Skip the plan: will you write the essay?",
    "Explain why we are allowed to use calculators.",
])
def test_control_content_asked_for_is_still_an_item(sentence):
    assert not is_context_sentence(sentence)
    assert [i.text for i in extract_items(sentence)] == [sentence]


def test_the_breadth_form_instructions_make_no_items():
    ec_1 = SPEC["b1/ec-1"]["question"]
    assert [i.text[:3] for i in extract_items(ec_1)] == ["(g)"]
    sp_items = extract_items(SP_1_Q)
    assert not any(i.text in ("Write a model answer to this practice task in Spanish.", "Skip the plan and give the full text now.") for i in sp_items)
    # rewritten to the stricter rule of the round-9 clearance (c2b, sp-t15: a Language B request's task sentence is an item): the
    # one item is no longer the whole request but its Spanish task sentence, exactly; still no form instruction is an item
    assert [i.text for i in sp_items] == ["Escribe un texto para convencer a los estudiantes de que participen en la campaña «Cero plástico»."]
    assert [i.text for i in extract_items(PS_3_Q)] == ["How many minutes per mark does that give me, and how should I split the 60 minutes between planning and writing?"]


# ------------------------------------------------------------------------------------------ "quoting" asks to cite


@pytest.mark.parametrize("question", [C.LIT_T14_Q, C.LL_T14_Q])
def test_quoting_exactly_from_the_text_asks_for_quotations(question):
    [cite] = [c for c in extract_constraints(question) if c.kind == "must_cite_supplied_text"]
    assert cite.text.lower().startswith("quot")


def test_a_reply_that_quotes_meets_the_quoting_constraint_and_one_that_quotes_nothing_does_not():
    doc = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous",
                       text="The mill wheel turned all night. 'We work until the bell,' the foreman said, 'and then we sleep.' The children counted every hour in coal.")
    question = "Write one analytical paragraph on how the writer presents work, quoting exactly from the extract."
    for answer, met in (('The writer presents work as endless: the foreman\'s words "We work until the bell" make labour the measure of time.', True),
                        ("The writer presents work as endless and makes labour the measure of time.", False)):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="plan-q", request_id="req-q", task_id="task-q", subject="English A: Literature", task_type="analytical_paragraph",
                               selected_agent_ids=["english-specialist", "dummy-combinator"], allowed_document_ids=["doc-mill"]))
        m, req, _rq = hub.dispatch("task-q", "english-specialist", question, [doc])
        [cid] = [c.constraint_id for c in req.constraints if c.kind == "must_cite_supplied_text"]
        _reply, rc = hub.receive("task-q", m.message_id, answer, agent_id="english-specialist", report_id="rep-q-0")
        [res] = [r for r in rc.constraint_results if r.constraint_id == cid]
        assert res.satisfied is met, res.detail


# ------------------------------------------------------------------- a short quotation altered by one word (sp-t13)

#: The supplied article's sentence the sp-t13 answer quoted (breadth and adversarial rounds: «crecen amistades»).
HUERTOS = ("Los huertos comunitarios han cambiado el barrio. Muchos jóvenes empezaron a plantar junto a personas mayores que, en muchos "
           "casos, vivían solas. Según Ferrer, «aquí no solo crecen lechugas: crecen amistades». No todo ha sido fácil.")


def _spanish(answer: str):
    doc = SuppliedText(document_id="doc-huertos", title="Huertos", author="Periódico", text=HUERTOS)
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="plan-sp", request_id="req-sp", task_id="task-sp", subject="Language B: Spanish", task_type="short_answer",
                           selected_agent_ids=["spanish-specialist", "dummy-combinator"], allowed_document_ids=["doc-huertos"]))
    m, _req, _rq = hub.dispatch("task-sp", "spanish-specialist", "Lee el texto. ¿Qué dice Ferrer de los huertos? Justifica con palabras del texto.", [doc])
    _reply, rc = hub.receive("task-sp", m.message_id, answer, agent_id="spanish-specialist", report_id="rep-sp-0")
    return rc


def test_a_two_word_quotation_with_one_word_altered_is_named_altered():
    """«crecen amigos» where the text says «crecen amistades» (rule short-near-miss): the near form of the missing word stands next
    to the word the text holds, so the quotation is refutable (INT-REQ-003, altered), where the four-letter prefix rule missed it."""
    from epinoic_logic.channel.bus import displaced_word
    # the answer's own form (sp-t13): a verdict and its evidence quoted with no credit
    rc = _spanish("b) V: «personas mayores que, en muchos casos, vivían solas»; «crecen amigos»")
    named = [f for f in rc.findings if f.code == "INT-REQ-003"]
    assert named and "crecen amigos" in named[0].message and "altered" in named[0].message, [(f.code, f.message[:160]) for f in rc.findings]
    rc = _spanish("b) V: «personas mayores que, en muchos casos, vivían solas»; «crecen amistades»")
    assert not [f for f in rc.findings if f.code == "INT-REQ-003"]
    rc = _spanish("b) V: «personas mayores que, en muchos casos, vivían solas»; «crecen rápido»")  # no near form: unverifiable, not altered
    assert not [f for f in rc.findings if f.code == "INT-REQ-003" and "crecen rápido" in f.message]
    assert displaced_word("crecen amigos", HUERTOS) and displaced_word("amistad crecen", "crecen amistades crecen amistad") is False
    for control in ("crecen rápido", "crecen", "lechugas crecen", "solo crecen", "crecen amistades"):  # no near form next to the word held
        assert not displaced_word(control, HUERTOS), control


@pytest.mark.parametrize("excerpt", ["a b", "aaaa bbbb", "crecen amigos"])
def test_the_short_near_miss_is_read_in_linear_time(excerpt):
    from epinoic_logic.channel.bus import _text_word_index, displaced_word
    text = "crecen amistades " * 2_000 + "a " * 10_000 + "x"
    timing = measure(lambda: [displaced_word(excerpt, text) for _ in range(2_000)], bound=4.0, repeat=3, label=f"short near miss, {excerpt!r}")
    assert timing.holds, timing
    assert len(_text_word_index(text)[1]["crecen"]) == 64  # at most 64 positions of one word are kept


# ------------------------------------------------------------------------------------- the readers stay linear


def _item_entries(text: str):
    yield "extract_items", lambda: extract_items(text)
    yield "extract_items (STEM imperatives)", lambda: extract_items(text, extra_imperatives=("find", "solve"))
    yield "extract_items after a heading", lambda: extract_items("Question 1: Explain. " + text + " Question 2: Explain.")
    yield "question_pieces", lambda: question_pieces("Question 1 [5 marks]: x. " + text)
    yield "is_context_sentence", lambda: is_context_sentence("Since we are " + text)
    yield "is_context_sentence (form)", lambda: is_context_sentence("Skip the plan " + text)
    yield "question_label", lambda: question_label(text)
    yield "extract_constraints", lambda: extract_constraints("Quoting exactly " + text)
    from epinoic_logic.channel.bus import displaced_word
    yield "displaced_word", lambda: displaced_word("crecen amigos", "crecen " + text)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_item_readers(shape):
    """Every reader this handoff added to the request reader, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_item_entries, texts=one(shape))


@pytest.mark.parametrize("name,text", [
    ("question headings", "Question 1 [5 marks]: Explain. " * 700 + "x"),
    ("headings with no delimiter", "Question 12 " * 1_700 + "x"),
    ("permission clauses", "Since we're " + "allowed and " * 1_800 + "x"),
    ("form words", "Skip the plan " + "and give the full answer " * 800 + "x"),
])
def test_the_item_readers_are_linear_on_their_own_worst_inputs(name, text):
    timing = measure(lambda: len(extract_items(text)), bound=4.0, repeat=3, label=f"item readers, {name}")
    assert timing.holds, timing
