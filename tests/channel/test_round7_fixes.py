"""Channel behaviour found wanting by the round-7 arena overseers, on the round-7 material (tests/channel/r7_support.py):

* blocker: a superscript digit ("counts min⁻¹", "10³", "(1/2)⁴") raised ValueError out of RouterHub.receive and
  TranslatorChannel.relay: maa-p7b (which credits the Physics specialist), its six mutations and the ess-t13, maa-t13,
  ph-t13 and p7b syntheses got no receipt. Every content check now runs guarded (INT-INTERNAL-001 naming it);
* correct STEM answers were charged with contradictions that came from one symbol name for two quantities;
* INT-REQ-007 was an error for an inconsistency that belongs to the translator's assumed reading;
* word bounds counted the working the request exempts ("plus working and your diagram") and the "Note:" blocks;
* multi-part questions became one lumped item, some parts and requests were dropped, and coverage could not see a part
  left out; a numbered answer in Spanish and a guiding question were reported unaddressed;
* an altered or invented quotation of a supplied text was only "unverifiable" (CORE-SRC-003);
* a possessive was read as crediting every quotation after it, across a colon (lit-p7c, ES-SRC-008 x2);
* a credited clause ran on into the agent's own working lines (bm-p7a g3.2, INT-REQ-014)."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import attribute_excerpt, quotation_credit
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel.request_parser import count_paragraphs, extract_constraints, extract_items, measure_answer_words
from epinoic_logic.translate.contracts import ClaimVerificationOutcome, SuppliedText

from .r7_support import COMB, SPEC, Run, by_code, codes

#: The harness's invented quotation, in the words the arena appends to a reply.
INVENTED = ' The narrator also insists that "the river carried every secret of the town", which seals the point.'


def errors(rc) -> list:
    return [f for f in rc.findings if f.severity == "error"]


# ------------------------------------------------------------------ blocker: nothing raises, every call gets a receipt


def test_the_p7b_exchange_is_delivered_with_receipts_and_its_synthesis_relayed():
    run = Run("p7b")  # maa-p7b answers after the Physics report (its text: "counts min⁻¹") is forwarded through the hub
    assert set(run.receipts) == {"ph-p7b", "maa-p7b"} and "maa-p7b" in run.delivered
    for rc in run.receipts.values():
        assert rc.status is not TransmissionStatus.REJECTED and "INT-INTERNAL-001" not in codes(rc.findings)
    msg, rr = run.relay_synthesis()
    assert msg is not None and rr.status is not TransmissionStatus.REJECTED and "INT-INTERNAL-001" not in codes(rr.findings)


@pytest.mark.parametrize("group", ["ess-t13", "maa-t13", "ph-t13"])
def test_the_recorded_syntheses_with_superscripts_are_relayed(group):
    msg, rr = Run(group).relay_synthesis()
    assert msg is not None and rr.status is not TransmissionStatus.REJECTED and "INT-INTERNAL-001" not in codes(rr.findings)


def test_a_reply_that_credits_a_peer_whose_report_writes_superscripts_is_delivered():
    reply = "The Physics specialist's corrected rate at t = 0 h is 1600 counts per minute, so C0 = 1600."
    run = Run("p7b", texts={"maa-p7b": reply})
    rc = run.receipts["maa-p7b"]
    assert "maa-p7b" in run.delivered and "INT-INTERNAL-001" not in codes(rc.findings)


@pytest.mark.parametrize("sentence", ["The rate is 1.5 × 10³ per hour.", "The value is 2⁵ = 32.", "Nitrate reached 8.4 mg dm⁻³ at site B.", "After 4 half-lives C = 1600 × (1/2)⁴ = 100."])
def test_a_synthesized_claim_with_superscripts_is_relayed(sentence):
    run = Run("ess-t13")
    base = run.synthesis()
    first = base.claims[0]
    claims = [{"text": sentence, "source_claim_ids": [s.split("@")[0] for s in first.source_claim_ids], "transformation": "merged"}]
    msg, rr = run.relay_synthesis(run.synthesis({"ess-t13": claims}))
    assert msg is not None and "INT-INTERNAL-001" not in codes(rr.findings)


def test_a_content_check_that_fails_internally_is_int_internal_001_and_the_rest_of_the_receipt_is_kept(monkeypatch):
    def broken(*_a, **_k):
        raise ValueError("invalid literal for int() with base 10: '¹'")
    monkeypatch.setattr(TranslatorChannel, "_peer_figures", staticmethod(broken))
    run = Run("p7b")
    rc = run.receipts["maa-p7b"]
    assert "maa-p7b" in run.delivered
    [internal] = by_code(rc.findings, "INT-INTERNAL-001")
    assert internal.severity == "error" and "peer figures" in internal.message and "ValueError" in internal.message
    assert rc.coverage and rc.constraint_results is not None  # the other checks still reached the receipt
    monkeypatch.setattr("epinoic_logic.channel.bus.check_synthesis_ledger", broken)
    msg, rr = run.relay_synthesis()
    assert msg is not None and any(f.code == "INT-INTERNAL-001" and "claim ledger" in f.message for f in rr.findings)


# ------------------------------------------------------------------ one symbol name for two quantities


POOLED = {"ph-t13": {"ph-t13": ["g1.1", "g3.1"]}, "p7b": {"ph-p7b": ["g1.1", "g4.1"]},
          "cs-t13": {"cs-t13": ["g3.1", "g4.1", "g7.1", "g7.2", "g9.1", "g9.5", "g11.1", "g11.2"]}}


@pytest.mark.parametrize("group", ["ph-t13", "cs-t13", "p7b"])
def test_glossary_conflations_are_neither_a_contradiction_nor_an_undisclosed_one(group):
    run = Run(group, pooled=POOLED[group])  # the recorded translations that conflated one symbol for two quantities, pooled through the hub
    assert len(run.ch.formalized) == sum(len(v) for v in POOLED[group].values())
    for rc in run.receipts.values():
        assert "INT-CONFLICT-001" not in codes(rc.findings), [f.message for f in by_code(rc.findings, "INT-CONFLICT-001")]
    assert any("INT-CONFLICT-004" in codes(rc.findings) for rc in run.receipts.values())
    assert run.ch.conflicts_seen == []
    _msg, rr = run.relay_synthesis()
    assert "INT-CONFLICT-001" not in codes(rr.findings) and "INT-CONFLICT-002" not in codes(rr.findings)


# ------------------------------------------------------------------ INT-REQ-007 under an assumed reading


def _outcome_with(status_value: str):
    from epinoic_logic.engine.statuses import VerificationStatus
    from epinoic_logic.translate.contracts import AmbiguityFlag, Interpretation, TranslationStatus

    class _V:
        result_id = "res-1"
        status = VerificationStatus.INCONSISTENT_PREMISES

    class _T:
        status = TranslationStatus(status_value)
        interpretation = Interpretation(reading="r", ambiguity_flags=[AmbiguityFlag(code="ROUNDED_LITERAL", message="-0.67 is encoded as an exact equality")])

    class _O:
        verification = _V()
        translation = _T()
    return _O()


def test_int_req_007_is_a_warning_under_an_assumed_reading_and_an_error_otherwise():
    claim = Run("ph-t13").report("ph-t13").claims[0]
    ambiguous = TranslatorChannel._inconsistent_premises(claim, _outcome_with("AMBIGUOUS_TRANSLATION"))
    assert ambiguous.code == "INT-REQ-007" and ambiguous.severity == "warning" and "assumed reading" in ambiguous.message and "ROUNDED_LITERAL" in ambiguous.message
    translated = TranslatorChannel._inconsistent_premises(claim, _outcome_with("TRANSLATED"))
    assert translated.code == "INT-REQ-007" and translated.severity == "error"


# ------------------------------------------------------------------ word bounds: the working, the diagram, the notes


@pytest.mark.parametrize("task,excludes,bound", [("ec-p7a", ["working", "diagram"], 350), ("ph-p7b", ["working"], 300), ("bm-p7a", ["working"], 400), ("ge-t13", ["working"], 350)])
def test_plus_working_and_diagram_are_read_as_exemptions_and_the_prose_is_within_the_bound(task, excludes, bound):
    [c] = [c for c in extract_constraints(SPEC[task]["question"]) if c.kind == "max_words"]
    assert c.excludes == excludes and int(c.value) == bound
    answer, _notes, exempt = measure_answer_words(SPEC[task]["response_text"], excludes=excludes)
    assert answer <= bound and exempt > 0


@pytest.mark.parametrize("task,answer_words,note_words", [("hi-t13", 303, 57), ("ess-t13", 345, 22)])
def test_a_note_block_is_out_of_the_word_count(task, answer_words, note_words):
    assert measure_answer_words(SPEC[task]["response_text"])[:2] == (answer_words, note_words)


@pytest.mark.parametrize("task", ["hi-t13", "hi-p7c", "lit-p7c"])
def test_a_note_block_is_no_paragraph(task):
    assert count_paragraphs(SPEC[task]["response_text"]) == 1


@pytest.mark.parametrize("group,task", [("hi-t13", "hi-t13"), ("ess-t13", "ess-t13"), ("p7a", "ec-p7a"), ("p7b", "ph-p7b"), ("p7a", "bm-p7a")])
def test_the_five_r7_replies_carry_no_word_bound_error(group, task):
    rc = Run(group).receipts[task]
    assert not [f for f in by_code(rc.findings, "INT-REQ-005") if f.severity == "error"], [f.message for f in by_code(rc.findings, "INT-REQ-005")]


def test_a_bound_plus_working_on_a_worked_answer_measures_the_prose_only():
    question = SPEC["bm-t13"]["question"].rstrip() + " Write no more than 120 words, plus working."
    words, _n, exempt = measure_answer_words(SPEC["bm-t13"]["response_text"], excludes=["working"])
    assert words <= 120 and exempt > 100
    run = Run("bm-t13")
    m, _r, _q = run.hub.dispatch("bm-t13", SPEC["bm-t13"]["agent_id"], question, [])
    _reply, rc = run.hub.receive("bm-t13", m.message_id, SPEC["bm-t13"]["response_text"], agent_id=SPEC["bm-t13"]["agent_id"], report_id="rep-bm-j5")
    bound = next(c for c in rc.constraint_results if "120" in c.detail)
    assert bound.satisfied is True and "prose only" in bound.detail


# ------------------------------------------------------------------ request items per part, coverage per part


def test_every_part_and_request_of_the_r7_questions_is_an_item():
    sp = [i.text for i in extract_items(SPEC["sp-t13"]["question"])]
    assert any(t.startswith("1.") and "Menciona dos detalles" in t for t in sp)
    assert any(t.startswith("2.") and "¿Quién tuvo la idea del huerto" in t for t in sp)
    assert len([t for t in sp if t[:2] in ("4.", "5.")]) == 2 and any(t.startswith("b)") for t in sp)
    mai = [i.text for i in extract_items(SPEC["mai-t13"]["question"])]
    assert mai[0].startswith("(a) Find the value") and mai[1].startswith("(b) Find the number") and any("tell me where I lost marks" in t for t in mai)
    assert any(t.startswith("Please write the Data analysis and Conclusion sections") for t in (i.text for i in extract_items(SPEC["ch-t13"]["question"])))
    assert [i.text[:3] for i in extract_items(SPEC["bi-t13"]["question"])] == ["(a)", "(b)", "(c)", "(d)"]


@pytest.mark.parametrize("group,cut", [("bi-t13", "\n\n(b)"), ("cs-t13", "\n\n(b)"), ("mai-t13", "**Part (b)")])
def test_a_reply_cut_to_part_a_leaves_the_other_parts_unaddressed(group, cut):
    text = SPEC[group]["response_text"]
    run = Run(group, texts={group: text[:text.index(cut)]})
    cov = {c.item_id: c for c in run.receipts[group].coverage}
    assert cov["i1"].addressed and cov["i1"].method == "part_label"
    assert not cov["i2"].addressed and "INT-REQ-004" in codes(run.receipts[group].findings)


@pytest.mark.parametrize("group", ["sp-t13", "ll-t13", "bi-t13", "mai-t13"])
def test_the_genuine_answers_address_every_item(group):
    rc = Run(group).receipts[group]
    assert all(c.addressed for c in rc.coverage) and "INT-REQ-004" not in codes(rc.findings)


# ------------------------------------------------------------------ altered and invented quotations of a supplied text


@pytest.mark.parametrize("group,original,altered,missing", [
    ("lit-t13", "could mean that she has been hurt", "could mean that shely has been hurt", "shely"),
    ("sp-t13", "sin pesticidas químicos", "sin pesticidasly químicos", "pesticidasly"),
])
def test_an_altered_quotation_of_a_supplied_text_is_int_req_003_naming_the_text(group, original, altered, missing):
    text = SPEC[group]["response_text"]
    assert original in text
    rc = Run(group, texts={group: text.replace(original, altered, 1)}).receipts[group]
    named = [f for f in errors(rc) if f.code == "INT-REQ-003" and missing in f.message]
    assert named and "altered quotation" in named[0].message


@pytest.mark.parametrize("group", ["bi-t13", "sp-t13", "lit-t13", "ch-t13"])
def test_an_invented_quotation_credited_to_the_text_under_analysis_is_int_req_003(group):
    rc = Run(group, texts={group: SPEC[group]["response_text"] + INVENTED}).receipts[group]
    assert any(f.code == "INT-REQ-003" and "the river carried every secret of the town" in f.message for f in errors(rc))


def test_a_quotation_of_the_request_is_neither_invented_nor_refuted():
    rc = Run("sp-t13").receipts["sp-t13"]  # the answer quotes the request's own statement ("toda")
    assert not by_code(rc.findings, "INT-REQ-003")


# ------------------------------------------------------------------ a possessive governs the quotation it introduces


LIT_SENTENCE = ('Its timetable is consistent with the History specialist\'s "Over the following weeks the barbed wire gave way to concrete": '
                '"By Wednesday they were bricking up the windows", and "By autumn there was nothing left to lean from" closes the window the aunt leaned from.')


def _lit_docs() -> dict:
    poem = SuppliedText(**SPEC["lit-p7c"]["supplied_texts"][0])
    peer = SuppliedText(document_id="peer:hi-p7c", title="history-specialist report", author="history-specialist", text=SPEC["hi-p7c"]["response_text"])
    return {poem.document_id: poem, peer.document_id: peer}


def test_the_possessive_credits_only_the_quotation_it_introduces():
    docs = _lit_docs()
    poem_id = SPEC["lit-p7c"]["supplied_texts"][0]["document_id"]
    assert attribute_excerpt("Over the following weeks the barbed wire gave way to concrete", ["peer:hi-p7c"], docs, sentence=LIT_SENTENCE) == ("peer:hi-p7c", [])
    for line in ("By Wednesday they were bricking up the windows", "By autumn there was nothing left to lean from"):
        assert attribute_excerpt(line, ["peer:hi-p7c"], docs, sentence=LIT_SENTENCE) == (poem_id, [])
    c2 = 'The History specialist writes "By Wednesday they were bricking up the windows".'
    doc, notes = attribute_excerpt("By Wednesday they were bricking up the windows", ["peer:hi-p7c"], docs, sentence=c2)
    assert doc == poem_id and notes and "attributes this quotation to peer:hi-p7c" in notes[0]


def test_the_genuine_lit_p7c_paragraph_carries_no_misattribution():
    rc = Run("p7c").receipts["lit-p7c"]
    bad = [f for f in rc.findings if "By Wednesday" in f.message or "By autumn" in f.message]
    assert bad == [] and not [sf for sf in rc.structural_findings if sf.code == "ES-SRC-008"]


def test_supplies_the_frame_credits_the_quotation_to_the_peer():
    sentence = 'The History specialist supplies the frame: the closure "dealt with the exit rather than the reasons people left".'
    credit = quotation_credit(sentence, sentence.index('"'), _lit_docs())
    assert credit is not None and credit.document_id == "peer:hi-p7c"


# ------------------------------------------------------------------ a credited clause ends at its line


def test_the_business_specialists_own_working_after_a_credited_quotation_is_not_a_misreported_peer_figure():
    run = Run("p7a")
    rc = run.receipts["bm-p7a"]
    assert not [f for f in by_code(rc.findings, "INT-REQ-014") if "13.125" in f.message or "0.55" in f.message], [f.message for f in by_code(rc.findings, "INT-REQ-014")]
    misreport = SPEC["bm-p7a"]["response_text"] + "\n\nThe Economics specialist gives an elasticity of about −0.76 for the market."
    rc2 = Run("p7a", texts={"bm-p7a": misreport}).receipts["bm-p7a"]
    assert any("0.76" in f.message for f in by_code(rc2.findings, "INT-REQ-014"))
