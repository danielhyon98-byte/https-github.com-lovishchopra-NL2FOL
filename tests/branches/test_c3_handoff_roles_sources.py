"""Round-10 clearance (integrated round c3), handoff pass: roles, the core pack's from-memory reading and the one reader of the
writer's own quoted words.

* Combinator handoff H2: the English parsers roled a question that asks the student or the router something back ("Would you like me
  to say more about the reparations?", "Which edition are you using?") a material point while every other branch roled it a note, so
  a synthesis that follows the combinator's rule 6 drew INT-LEDGER-019 on the English branches. It is a note on every branch now; the
  questions the answer sets the student under an "answer these ...:" lead stay material (handoff H9 of the parsers).
* Core handoff K5: the core pack read any from-memory wording as a label of the answer's figures, so ge-t16's decline "... so I have
  left those figures out rather than give them from memory." made its CORE-SRC-003 say "the from-memory label concerns dates and
  figures". It reads the label as the ledger does (``integrity.ledger.labels_report_figures_from_memory``).
* Overseer handoff 1(b): the transfer auditor's reader of the writer's own words in quotation marks (rules own-model and own-text) is
  the translator's now (``adapters.own_text``, exported through ``epinoic_logic.api.adapters``); the auditor imports it instead of
  its copy. (The channel's own-form reading, ``markdown.own_form_flags``, is still a reader of its own.)
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import is_question_back
from epinoic_logic.adapters.own_text import OWN_TEXT_RULE, own_model_spans, own_text_spans
from epinoic_logic.branches.packs import _labels_figures_from_memory

from ..channel.c3_core_support import C3, _deliver
from ..core_hostile import SHAPES, one, sweep

QUESTIONS_BACK = ["Would you like me to say more about the reparations?", "Which edition are you using?",
                  "Which of the three directions interests you most?", "Can you send me your draft of the introduction?"]
ENGLISH = {"English A: Language and Literature": ("english-a-lang-lit-specialist", "Analyse how the advert presents family."),
           "English A: Literature": ("english-a-literature-specialist", "Analyse how the poem presents grief.")}


def _roles(subject: str, agent: str, question: str, text: str) -> dict[str, tuple[str, str]]:
    item = {"task_id": "t-q", "subject": subject, "agent_id": agent, "task_type": "short_answer", "question": question, "supplied_texts": [],
            "response_text": text}
    hub, _ch, reply, _rc = _deliver(item, None, None)
    hub.close()
    return {c["claim_text"]: (c["claim_role"], c["materiality"]) for c in reply.payload["claims"]}


# ------------------------------------------------------------------------------------------ H2: a question back is a note

@pytest.mark.parametrize("subject", sorted(ENGLISH))
@pytest.mark.parametrize("question", QUESTIONS_BACK)
def test_a_question_back_to_the_student_is_a_note_on_the_english_branches(subject, question):
    agent, request = ENGLISH[subject]
    roles = _roles(subject, agent, request, "The answer makes one clear point about the topic, which the student can develop further.\n\n" + question)
    if question.startswith("Can you send"):  # a request to send work back is meta-text already (no claim at all) or a note
        assert roles.get(question, ("other", "supporting")) == ("other", "supporting"), roles
    else:
        assert roles[question] == ("other", "supporting"), roles


@pytest.mark.parametrize("text", ["What does that choice do to who counts as part of the family?", "Does one question work across all three adverts, or only two?",
                                  "Why does the narrator withhold the name?", "Would the speaker have said this in public?"])
def test_controls_a_question_the_answer_sets_is_no_question_back(text):
    assert not is_question_back(text)


def test_the_guiding_questions_under_an_answer_these_lead_stay_material():
    item = C3["c3"]["specialists"]["ll-t16"]
    hub, _ch, reply, _rc = _deliver(item, None, None)
    hub.close()
    questions = [c for c in reply.payload["claims"] if c["claim_text"].rstrip().endswith("?") and c["claim_id"].startswith("p4-")]
    assert len(questions) == 4 and all(c["materiality"] == "material" and c["claim_role"] != "other" for c in questions), \
        [(c["claim_id"], c["claim_role"], c["materiality"]) for c in questions]


# ------------------------------------------------------------------------------------------ K5: a from-memory label, as the ledger reads it

@pytest.mark.parametrize("text, labels", [
    ("The February 2023 Turkey and Syria earthquakes are not used in this answer: I have no approved source for their death tolls, so I have "
     "left those figures out rather than give them from memory.", False),
    ("None of these figures is in the case, so any number I gave from memory would be unverified.", False),
    ("Figures quoted from memory.", True),
    ("Dates and figures here are from memory; check them against your notes.", True),
    ("The Act was passed in 1833 (from memory).", True),
    # the veto is read in the wording's own clause: a word of another clause vetoes nothing (the general reading's reference corpus,
    # tests/branches/test_quant_si_reading.py, holds this sentence; reading it whole had dropped its label)
    ("The poem never mentions the war, so this reading rests on the History specialist's context, whose \"dates and figures\" are, in its "
     "own words, \"from memory and should be checked before they are cited\".", True),
    ("I never checked these figures, so treat them as given from memory.", True),
    ("The poem is short, so I would not give its dates from memory.", False),
])
def test_the_core_pack_reads_a_from_memory_label_as_the_ledger_does(text, labels):
    from epinoic_logic.integrity.ledger import labels_report_figures_from_memory
    assert _labels_figures_from_memory(text) is labels
    assert labels_report_figures_from_memory(text) is labels


def test_ge_t16s_decline_is_no_from_memory_label_of_its_figures():
    item = dict(C3["c3"]["specialists"]["ge-t16"])
    # a quotation no supplied text holds, appended as a mutation would: its CORE-SRC-003 must not say the decline labels figures
    item["response_text"] = item["response_text"] + '\n\nThe report also says that "the whole town was rebuilt within a single year".'
    hub, _ch, _reply, rc = _deliver(item, None, None)
    hub.close()
    named = [f for f in rc.structural_findings if f.code == "CORE-SRC-003"]
    assert named and all("the from-memory label concerns dates and figures" not in f.message for f in named), [f.message[:200] for f in named]


# ------------------------------------------------------------------------------------------ the one reader of the writer's own words

@pytest.mark.parametrize("task, span", [
    ("sp-t16", "¿Cómo están?"), ("sp-t16", "su casa"), ("sp-t16", "los echo mucho de menos"),     # forms a letter would normally use
    ("sp-t16", "me gustaría que"),                                                                 # a class of forms ("and other ... phrases")
    ("ll-t16", "Money in a bank's savings adverts."),                                              # a topic under its label, after an invented example
])
def test_the_recorded_own_words_are_read_as_the_writers(task, span):
    text = C3["c3"]["specialists"][task]["response_text"]
    inners = [inner.strip() for _a, _b, inner in own_text_spans(text)]
    assert any(i == span or i.startswith(span) for i in inners), (span, inners[:12])


def test_controls_a_quotation_credited_to_a_text_and_the_original_of_a_correction_stay_quotations():
    text = 'Your email says "Mi abuela cocina cada domingo." Change "una mujer muy simpático" → "una mujer muy simpática".'
    inners = {inner.strip() for _a, _b, inner in own_text_spans(text)}
    assert "una mujer muy simpática" in inners and "una mujer muy simpático" not in inners
    assert "Mi abuela cocina cada domingo." not in inners
    assert OWN_TEXT_RULE == "own-text" and own_model_spans('Model: "A higher price lowers demand."')


@pytest.mark.parametrize("shape", SHAPES)
def test_the_shared_readers_are_linear_on_hostile_input(shape):
    def entries(text):
        yield "own text", lambda: own_text_spans('Model: "' + text + '" → "' + text[:200] + '"')
        yield "own model", lambda: own_model_spans("Model: " + text)
        yield "question back", lambda: is_question_back("Which of " + text + "?")
        yield "memory label", lambda: _labels_figures_from_memory("from memory " + text)

    assert not sweep(entries, texts=one(shape)), shape


# ------------------------------------------------------------------------------------------ overseer handoff 5: a coaching answer's paragraphs

def test_a_declined_and_coached_answer_is_held_to_no_strands_rule():
    """ll-t16 declines the essay and coaches: its coaching paragraphs drew ES-STR-001 (fed back as "add a second strand quoted exactly
    from the text"). The control, the same paragraphs in an answer that analyses the text, is still named."""
    item = C3["c3"]["specialists"]["ll-t16"]
    hub, _ch, _reply, rc = _deliver(item, None, None)
    hub.close()
    assert not [f for f in rc.structural_findings if f.code == "ES-STR-001"]
    first, _sep, rest = item["response_text"].partition("\n\n")
    assert first.startswith("I can't choose your line of inquiry")
    hub, _ch, _reply, rc = _deliver(item, None, rest)  # the same answer without its decline
    hub.close()
    assert [f for f in rc.structural_findings if f.code == "ES-STR-001"]
