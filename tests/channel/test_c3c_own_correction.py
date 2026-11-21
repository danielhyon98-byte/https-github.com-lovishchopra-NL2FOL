"""Push check of 2ff70224, item R10-OWN-TEXT-ONE-READER (still partial): an arrow correction written in the answer's own text,
'"x" -> "y"', still drew INT-REQ-003 and ES-SRC-001 at error level. The one reader (``own_text.own_text_kinds``) named "y" the
writer's own (a FRAME) but left "x", the wording the correction replaces, a quotation of a text; the English parser then credited
"x" to the text under analysis, so the channel reported it not found (INT-REQ-003) and the English pack invented (ES-SRC-001).

Now the one reader names each own correction (``own_text.correction_pairs``: the replaced wording and its correction). The replaced
span keeps its kind None (``own_text_kinds``) and stays out of ``own_text_spans``, the transfer auditor's reader, whose control keeps
the original of a correction a quotation; the channel decides both spans with the sources in view, as it decides a FRAME. Both
directions are pinned here:

* an own correction ('"x" -> "y"', '"x" => "y"', '"x" should be "y"', '"x" becomes "y"', '"y" rather than "x"', '"y" instead of
  "x"'), at any length, draws neither finding (nor CORE-SRC-003) on either span;
* a misquotation of a supplied text written as a correction's replaced wording, or credited to the text ('The notes say "..." ->'),
  is still INT-REQ-003 and ES-SRC-001 at error level (INV-Q1: a supplied text that holds its words, altered or not, keeps it a
  quotation);
* the replaced wording that alters the request (the student's own words) is still INT-REQ-003 at error level, while one built from
  words scattered over the request alters nothing.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import own_text as ot

from .c3_core_support import C3, _deliver

LL = C3["c3"]["specialists"]["ll-t16"]
QUOTE_CODES = ("INT-REQ-003", "ES-SRC-001", "CORE-SRC-003")
BETTER = "the adverts sell saving as a family duty"


def _charged(extra: str, task_type: str) -> dict[str, list[tuple[str, str]]]:
    """The quotation findings (code, severity) at warning or error on the claims of ll-t16 with ``extra`` appended, by claim text."""
    item = dict(LL)
    item["task_type"] = task_type
    hub, _ch, reply, rc = _deliver(item, None, LL["response_text"] + "\n\n" + extra)
    hub.close()
    texts = {c["claim_id"]: c["claim_text"] for c in reply.payload["claims"]}
    out: dict[str, list[tuple[str, str]]] = {}
    for f in [*rc.findings, *rc.structural_findings]:
        assert f.code != "INT-INTERNAL-001", f.message
        if f.code in QUOTE_CODES and f.severity in ("error", "warning"):
            for cid in f.claim_ids:
                out.setdefault(texts.get(cid, cid), []).append((f.code, f.severity))
    return out


# ------------------------------------------------------------------------------------------------ the answer's own corrections
@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra", [
    f'Your thesis is vague: "the adverts are about money" -> "{BETTER}".',
    f'Your thesis is vague: "the adverts are about money" → "{BETTER}".',
    f'Your thesis is vague: "the adverts are about money" => "{BETTER}".',
    f'"the adverts are about money" should be "{BETTER}".',
    f'A vague thesis such as "the adverts are about money" becomes "{BETTER}".',
    f'Better: "{BETTER}" rather than "the adverts are about money".',
    f'Write "{BETTER}" instead of "the adverts are about money".',
    'Your thesis: "greed" -> "thrift".',
    'Your thesis: "money matters" -> "thrift matters".',
], ids=["ascii-arrow", "arrow", "double-arrow", "should-be", "becomes", "rather-than", "instead-of", "one-word", "two-words"])
def test_an_own_correction_draws_no_quotation_finding_on_either_span(extra, task_type):
    assert _charged(extra, task_type) == {}


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
@pytest.mark.parametrize("extra, misquoted", [
    # the notes hold 'A grandmother cooks for a huge family.': one word changed
    (f'Fix the quotation: "A grandmother cooks for a tiny family." -> "{BETTER}."', "A grandmother cooks for a tiny family."),
    (f'"A grandmother cooks for a tiny family" -> "{BETTER}".', "A grandmother cooks for a tiny family"),
    # credited to the text: a quotation of it, whatever follows
    (f'The notes say "A grandmother cooks for a tiny family" -> "{BETTER}".', "A grandmother cooks for a tiny family"),
], ids=["fix-label", "bare", "credited"])
def test_a_misquotation_of_a_supplied_text_as_the_replaced_wording_is_still_charged(extra, misquoted, task_type):
    charged = _charged(extra, task_type)
    codes = next((v for k, v in charged.items() if misquoted in k and k.strip('"').startswith(misquoted[:12])), None)
    assert codes is not None, charged
    assert ("INT-REQ-003", "error") in codes and ("ES-SRC-001", "error") in codes, charged


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_the_replaced_wording_that_alters_the_request_is_still_charged(task_type):
    """The request reads 'Please choose a line of inquiry for me': 'enquiry' for 'inquiry' alters the student's own words."""
    charged = _charged('"choose a line of enquiry for me" -> "choose one focus for me"', task_type)
    assert charged == {'"choose a line of enquiry for me"': [("INT-REQ-003", "error")]}, charged


@pytest.mark.parametrize("task_type", ["hl_essay", "marking_feedback"])
def test_the_replaced_wording_quoted_exactly_from_the_request_or_a_text_is_no_finding(task_type):
    assert _charged('"choose a line of inquiry for me" -> "choose one focus for me"', task_type) == {}
    assert _charged(f'"A grandmother cooks for a huge family" -> "{BETTER}".', task_type) == {}


def test_the_channel_message_of_an_altered_request_names_the_request():
    item = dict(LL)
    hub, _ch, _reply, rc = _deliver(item, None, LL["response_text"] + "\n\n" + '"choose a line of enquiry for me" -> "choose one focus for me"')
    hub.close()
    msgs = [f.message for f in rc.findings if f.code == "INT-REQ-003"]
    assert len(msgs) == 1 and "the request holds all of its words but 'enquiry' (an altered quotation)" in msgs[0], msgs


# ------------------------------------------------------------------------------------------------------------ the one reader
@pytest.mark.parametrize("sentence, pairs", [
    ('"x" -> "y"', [(0, 1)]),
    ('Your thesis is vague: "the adverts are about money" → "the adverts sell saving".', [(0, 1)]),
    ('"fue" should be "fuimos".', [(0, 1)]),
    ('"fue" becomes "fuimos".', [(0, 1)]),
    ('Write "thrift sells" -> "the adverts sell thrift".', [(0, 1)]),
    ('Better: "I have gone" rather than "I has went".', [(1, 0)]),
    ('You would normally say "¿Cómo están?" instead of "¿Cómo estáis?".', [(1, 0)]),
    ('"x" -> "y". Then "a" should be "b".', [(0, 1), (2, 3)]),
    # a span joined to an own span by "and" or a comma continues its list (a FRAME), so it replaces nothing
    ('"x" -> "y" and "a" should be "b".', [(0, 1)]),
    # credited to a text: a quotation of it, never part of an own correction
    ('Your email says "I has went" → "I have gone".', []),
    ('The poem reads "the sea was angry" -> "the sea was furious".', []),
    ('She wrote "thrift sells" -> "the adverts sell thrift".', []),
    # no correction: two quotations
    ('The notes say "Every kitchen." and "Everyone."', []),
], ids=["placeholder", "thesis", "should-be", "becomes", "imperative-write", "rather-than", "instead-of", "two-pairs", "list",
        "email-says", "poem-reads", "she-wrote", "two-quotes"])
def test_the_one_reader_names_each_own_correction(sentence, pairs):
    spans = md.find_quotation_spans(sentence)
    kinds = ot.own_text_kinds(sentence, spans)
    assert ot.correction_pairs(sentence, spans) == pairs
    assert ot.correction_originals(sentence, spans) == [any(i == r for r, _c in pairs) for i in range(len(spans))]
    for replaced, correction in pairs:
        # the replaced wording keeps its kind (None) and stays out of the auditor's own spans; the correction is the writer's own
        assert kinds[replaced] is None and kinds[correction] is not None
        assert (spans[replaced][0], spans[replaced][1]) not in [(a, b) for a, b, _i in ot.own_text_spans(sentence)]


def test_the_correction_reading_is_linear_on_many_corrections():
    text = ('"a b" -> "c d". ' * 4000) + "\n\n" + ('"x" rather than "y". ' * 4000)
    t = time.perf_counter()
    kinds = ot.own_text_kinds(text)
    pairs = ot.correction_pairs(text)
    assert len(kinds) == 16000 and len(pairs) == 8000 and time.perf_counter() - t < 10.0


@pytest.mark.parametrize("mark", ["->", "-->", "—>", "=>", "→", ">", "should   be :", "becomes:", ". Correct form:", "; corrected  sentence :",
                                  "Right:", "said"])
@pytest.mark.parametrize("pad", ["", " ", "  *_ \t ", "\t \t*_*_"])
@pytest.mark.parametrize("lead", ["", "x" * 30, 'The notes say "a" and "b" ' * 6, "_" * 50])
def test_the_correction_mark_is_read_from_the_tail_of_the_window_as_from_the_whole(mark, pad, lead):
    """Repair 1 after clearance c3c: ``own_text_kinds`` searches the correction mark only in the window's last
    ``_CORRECTION_TAIL`` characters (the pattern ends at the window's end and matches at most 44 characters). The reading equals the
    search of the whole window, with every quotation mark, padding and lead, the longest marks included."""
    for q in ('"', "'", "”", "’", "»"):
        before = (lead + q + pad + mark + pad)[-ot._OWN_TEXT_BEFORE:]
        whole = bool(ot._CORRECTION_BEFORE_RE.search(before))
        tail = bool(ot._CORRECTION_BEFORE_RE.search(before, max(0, len(before) - ot._CORRECTION_TAIL)))
        assert whole is tail, (before, whole, tail)


# ------------------------------------------------------------------------------- the answer quoting its own earlier wording
# Round-8 attack (branches lens, Language B): 'The article opens with "Cada verano, nuestra ciudad se llena de turistas".' quotes the
# first sentence of the answer's own model article word for word, and the channel charged it INT-REQ-003 as an altered quotation of
# the request (the task holds all of its words but "nuestra" and "llena"). The one reader now reads it as the answer's own wording
# (``own_text.quotes_own_wording``); the task's words credited to the task, and an altered quotation of a supplied text, stay charged.
def _lb_new_quote_findings(extra: str) -> list[tuple[str, str]]:
    from ..branches import d9d10_hub as H
    from ..branches import d9d10_texts as T
    rc = H.recorded("c2/sp-t15", T.SP_T15 + "\n\n" + extra)
    assert not [f for f in rc.findings if f.code == "INT-INTERNAL-001"], [f.message for f in rc.findings]
    return [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-003" or "-SRC-" in f.code]


@pytest.mark.parametrize("extra", [
    'The article opens with "Cada verano, nuestra ciudad se llena de turistas".',
    'The model opens with "Cada verano, nuestra ciudad se llena de turistas".',
    'The second sentence, "Su presencia nos da trabajo y dinero", gives the advantage first.',
], ids=["article-opens", "model-opens", "second-sentence"])
def test_a_quotation_of_the_answers_own_model_text_is_no_altered_quotation_of_the_request(extra):
    assert _lb_new_quote_findings(extra) == []


@pytest.mark.parametrize("extra", [
    'Your task says "Tu ciudad recibe cada invierno miles de turistas".',
    'The task asks: "Tu ciudad recibe cada invierno miles de turistas".',
], ids=["your-task", "the-task"])
def test_an_altered_quotation_of_the_task_is_still_charged(extra):
    assert _lb_new_quote_findings(extra) == [("INT-REQ-003", "error")]


def test_the_answers_own_wording_never_excuses_an_altered_quotation_of_a_supplied_text():
    """ec-t16's supplied text says 'the number of boats grew and the catch rose'; the answer writes 'ships' in its own voice and then
    quotes that wording: still an altered quotation of the supplied text (INV-Q1)."""
    item = C3["c3"]["specialists"]["ec-t16"]
    extra = 'Between 2010 and 2019 the number of ships grew and the catch rose. In short, "the number of ships grew and the catch rose".'
    hub, _ch, _reply, rc = _deliver(item, None, item["response_text"] + "\n\n" + extra)
    hub.close()
    msgs = [f.message for f in rc.findings if f.code == "INT-REQ-003" and f.severity == "error"]
    assert len(msgs) == 1 and "doc-pelland holds all of its words but 'ships' (an altered quotation)" in msgs[0], msgs


@pytest.mark.parametrize("sentence, start, excerpt, expected", [
    ('The article opens with "Cada verano, nuestra ciudad se llena de turistas".', 23, "Cada verano, nuestra ciudad se llena de turistas", True),
    ('Your draft says "Cada verano, nuestra ciudad se llena de turistas".', 16, "Cada verano, nuestra ciudad se llena de turistas", False),
    ('The article opens with "Cada verano, nuestra".', 23, "Cada verano, nuestra", False),  # three words: too short
    ('The article opens with "Cada año, nuestra ciudad se llena de turistas".', 23, "Cada año, nuestra ciudad se llena de turistas", False),
], ids=["own", "your-draft", "short", "altered"])
def test_the_one_reader_names_a_quotation_of_the_answers_own_wording(sentence, start, excerpt, expected):
    answer = "Cada verano, nuestra ciudad se llena de turistas que llegan con mapas.\n\n" + sentence
    assert sentence[start] == '"'
    assert ot.quotes_own_wording(ot.unquoted_text(answer), sentence, start, excerpt) is expected


def test_unquoted_text_blanks_every_quotation_and_keeps_offsets():
    text = 'He said "a b c d" and "e".'
    out = ot.unquoted_text(text)
    assert len(out) == len(text) and '"' not in out and "a b c d" not in out and out.startswith("He said ")
