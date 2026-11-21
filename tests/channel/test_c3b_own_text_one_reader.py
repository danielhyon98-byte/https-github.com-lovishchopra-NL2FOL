"""Round-10 leftover R10-OWN-TEXT-ONE-READER (major): the channel read the writer's own quoted words with ``markdown.own_form_flags``
and the transfer auditor with ``own_text.own_text_spans``, so on coaching shapes the channel charged the writer's own suggestion at
error level as an invented quotation (INT-REQ-003 and ES-SRC-001 on c3 ll-t16 with a 'Topic:' line, a 'Better:' rewrite or an arrow
correction appended) while the auditor read it as own text.

Now ONE reader decides: ``own_text.own_text_kinds`` reads each quoted span as the writer's FORM, FRAME or neither. The channel's
``markdown.own_form_flags`` is a thin call reading its FORMs; ``sources.own_model_words`` reads its FRAMEs with the supplied texts in
view (a frame over words a supplied text holds in a run, altered or not, stays a quotation and is checked: repair round 4, INV-Q1);
the auditor's ``own_text_spans`` is every FORM and FRAME."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import own_text as ot

from .c3_core_support import C3, _deliver

LL = C3["c3"]["specialists"]["ll-t16"]
QUOTE_CODES = ("INT-REQ-003", "ES-SRC-001", "CORE-SRC-003")


def _named(extra: str, task_type: str = "hl_essay") -> dict[str, list[str]]:
    item = dict(LL)
    item["task_type"] = task_type
    hub, _ch, reply, rc = _deliver(item, None, LL["response_text"] + "\n\n" + extra)
    hub.close()
    texts = {c["claim_id"]: c["claim_text"] for c in reply.payload["claims"]}
    out: dict[str, list[str]] = {}
    for f in [*rc.findings, *rc.structural_findings]:
        if f.code in QUOTE_CODES and f.severity in ("error", "warning"):
            for cid in f.claim_ids:
                out.setdefault(texts.get(cid, cid), []).append(f.code)
    return out


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra, own", [
    ('For your essay, a workable focus. Topic: "Money in savings adverts and the family table."', "Money in savings adverts and the family table"),
    ('Your thesis is vague. Better: "The adverts sell saving as a family duty."', "The adverts sell saving as a family duty"),
    ('Your thesis is vague: "the adverts are about money" → "the adverts sell saving as a family duty".', "the adverts sell saving as a family duty"),
], ids=["topic", "better", "arrow"])
def test_the_writers_suggested_wording_is_not_checked_against_the_supplied_texts(extra, own, task_type):
    named = _named(extra, task_type)
    assert not [t for t in named if own in t], named


def test_control_a_topic_label_over_a_supplied_texts_sentence_with_one_word_changed_is_still_an_altered_quotation():
    """INV-Q1 kept: the notes say 'A grandmother cooks for a huge family.'; a 'Topic:' label over those words with one changed is an
    altered quotation of the notes, checked as any other."""
    named = _named('Topic: "A grandmother cooks for a tiny family."')
    assert any("A grandmother cooks for a tiny family" in t and "INT-REQ-003" in codes for t, codes in named.items()), named


@pytest.mark.parametrize("sentence", [
    'Use "vosotros" here: it is the informal imperative of "andar".', 'Standard Spanish says "ya casi".',
    'Write "me gustaría que" → "me gustaría que vinieras".', 'Model (one sentence): "The camera stays low."',
    '"echarle ganas" means "to put effort in".', '"Ojo" is a fixed phrase.', 'You would normally say "¿Cómo están?" instead of "¿Cómo estáis?".',
    'Topic: "Money in savings adverts."', 'An invented example: the poet writes "the river carried every secret".', 'Your email says "I has went".',
    '"mero" is short for "mero mero".', '"Careful, it\'s hot!" translates as "¡Cuidado, quema!".', 'Better: "I have gone" rather than "I has went".',
    'It should be "fuimos", not "fue".', 'A diminutive-style form of "mero" is "merito".',
])
def test_the_channel_and_the_auditor_read_the_writers_own_words_with_one_reader(sentence):
    spans = md.find_quotation_spans(sentence)
    kinds = ot.own_text_kinds(sentence, spans)
    assert md.own_form_flags(sentence, spans) == [k == ot.OWN_FORM for k in kinds]
    assert [(a, b) for a, b, _i in ot.own_text_spans(sentence)] == [(a, b) for (a, b, _i), k in zip(spans, kinds) if k is not None]


@pytest.mark.parametrize("sentence, expected", [
    ('Topic: "Money in savings adverts."', [ot.OWN_FRAME]),
    ('Better: "I have gone" rather than "I has went".', [ot.OWN_FRAME, None]),
    ('Write "me gustaría que" → "me gustaría que vinieras".', [None, ot.OWN_FRAME]),
    ('"echarle ganas" means "to put effort in".', [None, ot.OWN_FORM]),
    ('Your email says "I has went".', [None]),
])
def test_the_one_reader_names_the_kind_of_each_span(sentence, expected):
    assert ot.own_text_kinds(sentence) == expected


def test_the_one_reader_is_linear_on_many_quotations():
    import time
    text = ('Better: "a b" rather than "c d", ' * 4000) + "\n\n" + ('"x" means "y". ' * 4000)
    t = time.perf_counter()
    kinds = ot.own_text_kinds(text)
    assert len(kinds) == 16000 and time.perf_counter() - t < 5.0
