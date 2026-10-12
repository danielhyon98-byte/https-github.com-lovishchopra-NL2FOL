"""Regression tests for the round-6 overseer findings assigned to the shared pre-segmentation helpers
(adapters/markdown.py), the English parser and the generic parser (results-audit, communication-fidelity and
adversarial-live reports):

* en-p5's closing note on the peer's figures ('That account marks its figures as "from memory", so they are reported
  unverified.') is a note (role ``other``): a received report's labelling or verification status is a provenance note,
  the quoted label read as the label it is. It is never the link: the closing-link rule skips notes, caveats on the
  reading's grounds and a colleague's reported view, so the paragraph's conclusion (p1-s11) is the material link, and
  the recorded p5 group synthesis, which drops the note with a reason, carries no INT-LEDGER-019 / INT-LEDGER-002;
* notes about the answer's items or a received report ("Quotations are from the supplied extract", "The word count is
  approximate.") are notes on every branch, so an English answer made only of notes gets INT-REQ-012;
* self-certifications whose subject names the source of the items ("Each quotation of the History specialist above is
  exact.", "Every figure taken from the History specialist has been reproduced exactly.") and compliance self-reports
  ("The paragraph is under the word limit.", "The answer meets every constraint in the request.", "Word count: 258.")
  are roled ``other`` with the advisory status on the English, History and generic parsers and reach the router named;
* the English splitter cuts after "?" and "!" and after the pronoun "I" (en-t12 "Who made the eyes but I?");
* a sentence reporting a colleague's statement ("The History specialist states that ...") is the colleague's view on
  the English branch too: role ``perspective``, certainty capped, the attribution recorded;
* a fence of prose keeps its body in the shared pre-segmentation, so the channel's word count reads an answer wrapped
  in a fence (the r1-adv code-fence answer) instead of reporting "no answer" once its "Word count" line is a note.

The texts are the genuine round-6 specialist answers and the recorded p5 syntheses (tests/adapters/data/r6_specialists.json)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.english_specialist.parser import parse_response, segment, split_sentences
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.channel.request_parser import count_answer_words, count_paragraphs, count_words
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

DATA = json.loads((Path(__file__).parent / "data" / "r6_specialists.json").read_text(encoding="utf-8"))
EN_P5, HI_P5, EN_T11, EN_T12, HI_T11 = (DATA[k] for k in ("en-p5", "hi-p5", "en-t11", "en-t12", "hi-t11"))
KEY = b"round6-english-fixer-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
P5_NOTE = 'That account marks its figures as "from memory", so they are reported unverified.'
P5_CONCLUSION = "The poem's \"world-wide welcome\" names no origin, so its universal welcome can be read as an ideal that the country's law contradicted."
T12_ANCHOR = "rather than dissent."
T11_ANCHOR = "its responsibility was real but partial."


def docs_of(item: dict) -> list[SuppliedText]:
    return [SuppliedText(**d) for d in item["supplied_texts"]]


def peer_doc() -> SuppliedText:
    return SuppliedText(document_id="peer:hi-p5", title="history-specialist report relayed through the hub", author="history-specialist", text=HI_P5["response_text"])


def english(text: str, item: dict = EN_P5) -> SpecialistReport:
    docs = docs_of(item) + ([peer_doc()] if item is EN_P5 else [])
    return parse_response(text, request_id="r", task_id=item["task_id"], report_id="rep", task_type=item["task_type"], supplied_texts=docs)


def history(text: str) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", subject="History", task_type="short_answer", supplied_texts=[])


def generic(text: str) -> SpecialistReport:
    return GenericTextParser("economics-specialist").parse_response(text, request_id="r", task_id="t", report_id="rep", subject="Economics", task_type="short_answer", supplied_texts=[])


def claim(report: SpecialistReport, text: str):
    return next(c for c in report.claims if c.claim_text == text)


def codes(receipt) -> set[str]:
    return {f.code for f in receipt.findings} | {f.code for f in receipt.structural_findings}


def through_hub(item: dict, text: str, *, report_id: str = "rep-x"):
    docs = docs_of(item)
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{item['task_id']}", request_id=f"req-{item['task_id']}", task_id=item["task_id"], subject=item["subject"],
                                task_type=item["task_type"], selected_agent_ids=[item["agent_id"], "dummy-combinator"], allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch(item["task_id"], item["agent_id"], item["question"], docs)
    reply, receipt = hub.receive(item["task_id"], m.message_id, text, agent_id=item["agent_id"], report_id=report_id)
    return ch, reply, receipt


def p5_exchange(en_text: str = EN_P5["response_text"]):
    """The p5 peer exchange as the arena runs it: hi-p5 delivered, forwarded by the router to the English specialist,
    en-p5 received with the relayed report supplied as peer:hi-p5. Returns (channel, history reply, english reply, receipt)."""
    plan = WorkPlan(plan_id="plan-p5", request_id="req-p5", task_id="p5", subject=EN_P5["subject"], task_type=EN_P5["task_type"],
                    selected_agent_ids=["history-specialist", "english-specialist", "dummy-combinator"], allowed_document_ids=["doc-nc", "peer:hi-p5"],
                    agent_subjects={"history-specialist": "History"}, agent_task_types={"history-specialist": HI_P5["task_type"]})
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(plan)
    hm, _, _ = hub.dispatch("p5", "history-specialist", HI_P5["question"], [])
    hrep, _hrc = hub.receive("p5", hm.message_id, HI_P5["response_text"], agent_id="history-specialist", report_id="rep-hi-p5-0")
    fwd, _frc = ch.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(hrep.payload), in_reply_to=hrep.message_id)
    peer = SuppliedText(document_id="peer:hi-p5", title="history-specialist report relayed through the hub", author="history-specialist", text=fwd.payload["original_response"])
    em, _, _ = hub.dispatch("p5", "english-specialist", EN_P5["question"], [*docs_of(EN_P5), peer])
    erep, erc = hub.receive("p5", em.message_id, en_text, agent_id="english-specialist", report_id="rep-en-p5-0")
    return ch, hrep, erep, erc


def p5_synthesis(ch, replies: dict, *, keep_dropped: bool = True, drop_claims: tuple[str, ...] = ()) -> Synthesis:
    """The recorded p5 group synthesis, built as the harness builds it (one claim list per member, prefixed by task id)."""
    claims, ledger = [], []
    for tid in ("hi-p5", "en-p5"):
        syn, reply = DATA[f"syn-{tid}"], replies[tid]
        for i, c in enumerate(syn["claims"]):
            if any(x in drop_claims for x in c["source_claim_ids"]):
                continue
            claims.append(SynthesizedClaim(claim_id=f"{tid}-s{i}", text=c["text"], certainty=c.get("certainty", "established"),
                                           source_claim_ids=c["source_claim_ids"], transformation=c.get("transformation", "paraphrased")))
        if keep_dropped:
            ledger += [LedgerEntry(source_claim_ids=d["source_claim_ids"], transformation="dropped", reason=d.get("reason")) for d in syn.get("dropped", [])]
    body = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-p5", request_id=ch.plan.request_id, task_id=ch.plan.task_id, combinator_agent_id="dummy-combinator",
                     source_report_ids=[replies["hi-p5"].payload["report_id"], replies["en-p5"].payload["report_id"]], claims=claims, ledger=ledger,
                     text=body, text_sha256=sha256_text(body), created_at="2026-10-11T15:00:00Z")


def assert_self_report(report: SpecialistReport, sentence: str) -> None:
    c = claim(report, sentence)
    assert c.claim_role == "other" and c.materiality == "supporting" and c.advisory_verification_status and c.source_refs == [], (report.agent_id, c.claim_role)


# ------------------------------------------------------------ results-audit / communication-fidelity / adversarial-live majors: en-p5's closing note


def test_en_p5_closing_note_is_other_and_the_conclusion_is_the_material_link():
    assert P5_NOTE in EN_P5["response_text"] and P5_CONCLUSION in EN_P5["response_text"]
    rep = english(EN_P5["response_text"])
    note = claim(rep, P5_NOTE)
    assert (note.claim_id, note.claim_role, note.materiality, note.supporting_claim_ids, note.advisory_verification_status) == ("p1-s13", "other", "supporting", [], None)
    link = claim(rep, P5_CONCLUSION)
    assert (link.claim_id, link.claim_role, link.materiality) == ("p1-s11", "link", "material")
    assert [c.claim_id for c in rep.claims if c.claim_role == "link"] == ["p1-s11"]
    point = next(c for c in rep.claims if c.claim_role == "point")
    assert point.claim_id in link.supporting_claim_ids and "p1-s13" not in link.supporting_claim_ids
    # the quoted label is still delivered and checked, but supports nothing
    label = next(c for c in rep.claims if c.claim_role == "evidence" and c.claim_text == '"from memory"')
    assert label.source_refs and label.parent_claim_id is None
    assert label.claim_id not in point.supporting_claim_ids and label.claim_id not in link.supporting_claim_ids
    # the caveat before the note stays supporting: a caveat on the reading's grounds is never the link
    assert claim(rep, next(s for s in split_sentences(EN_P5["response_text"]) if s.startswith("The reading stays plausible"))).claim_role == "interpretation"


@pytest.mark.parametrize("note", [
    P5_NOTE,
    "That account labels its figures from memory, so they are reported unverified.",
    "The History specialist's figures are from memory, so they are reported unverified.",
    "The History specialist's figures are from memory, so I report them unverified.",
    "That account gives its figures from memory.",
    'Its figures are marked "from memory".',
    "The figures above come from the History specialist's paragraph, not from the poem.",
    "Quotations are from the supplied extract; check them before use.",
    "The word count is approximate.",
])
def test_notes_about_a_received_report_or_the_answers_items_are_notes_and_never_the_link(note):
    assert md.is_note_sentence(note) and not md.is_self_certification(note)
    rep = english(EN_P5["response_text"].replace(P5_NOTE, note))
    c = claim(rep, note)
    assert c.claim_role == "other" and c.materiality == "supporting" and c.advisory_verification_status is None
    assert [x.claim_id for x in rep.claims if x.claim_role == "link"] == ["p1-s11"]
    for rep in (history(HI_T11["response_text"].replace(T11_ANCHOR, T11_ANCHOR + " " + note, 1)), generic(HI_T11["response_text"] + " " + note)):
        assert claim(rep, note).claim_role == "other", rep.agent_id
    assert count_answer_words(note) == (0, count_words(note))


def test_the_note_stays_a_note_when_a_sentence_follows_it():
    rep = english(EN_P5["response_text"] + " The poem therefore welcomes every arrival.")
    assert claim(rep, P5_NOTE).claim_role == "other"


@pytest.mark.parametrize("sentence", [
    "The census figures are approximate.",
    "The figures are from the 1851 census.",
    "That account marks a turning point in the poem.",
    "Its figures are striking.",
    "The History specialist's figures show that immigration rose.",
    "The quotations come from the poem's final stanza, where the speaker hesitates.",
    "That account presents its figures as evidence of decline.",
    "The History specialist gives the figures from the 1880 census.",
    "Its figures are illustrative of the poem's method of address.",
])
def test_substantive_sentences_of_the_same_shapes_are_not_notes(sentence):
    assert not md.is_provenance_note(sentence) and not md.is_note_sentence(sentence)


def test_the_recorded_p5_group_synthesis_carries_no_ledger_warning_for_the_note():
    ch, hrep, erep, _erc = p5_exchange()
    syn = p5_synthesis(ch, {"hi-p5": hrep, "en-p5": erep})
    assert any("p1-s13" in e.source_claim_ids for e in syn.ledger)
    _rel, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert not [f for f in rr.findings if f.code in ("INT-LEDGER-019", "INT-LEDGER-002")], [(f.code, f.claim_ids) for f in rr.findings]


def test_a_synthesis_that_leaves_the_note_out_without_a_record_is_not_named_but_one_that_drops_the_conclusion_is():
    ch, hrep, erep, _erc = p5_exchange()
    silent = p5_synthesis(ch, {"hi-p5": hrep, "en-p5": erep}, keep_dropped=False)
    _rel, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, silent)
    assert not [f for f in rr.findings if f.severity in ("error", "warning") and "p1-s13" in f.claim_ids]
    ch, hrep, erep, _erc = p5_exchange()
    no_conclusion = p5_synthesis(ch, {"hi-p5": hrep, "en-p5": erep}, drop_claims=("p1-s11",))
    _rel, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, no_conclusion)
    assert any(f.code == "INT-LEDGER-002" and f.severity == "error" and "p1-s11" in f.claim_ids for f in rr.findings)


@pytest.mark.parametrize("closing, role", [
    ("The reading stays plausible: the poem never mentions the war.", "interpretation"),
    ("This reading rests on the historical context, so it is offered tentatively.", "interpretation"),
    ("The poem never mentions the war, so the link cannot be proved.", "interpretation"),
    ("The date comes from the History specialist, not the poem, so it is offered tentatively.", "interpretation"),
])
def test_a_closing_caveat_is_never_the_link_and_the_conclusion_before_it_is(closing, role):
    text = ('The city is held still at dawn. The houses "seem asleep" and the river "glideth at his own sweet will". '
            f"The verb therefore keeps the city still. {closing}")
    [para] = segment(text)
    assert [s.role for s in para.sentences] == ["point", "interpretation", "link", role]


@pytest.mark.parametrize("conclusion", [
    "The sonnet never names an origin, so its universal welcome can be read as an ideal that the country's law contradicted.",
    "The poem nowhere states who may enter, so its universal welcome stands as an ideal that the country's law contradicted.",
    "The welcome is therefore the statue's, not the poem's alone, an ideal that the country's law contradicted.",
])
def test_a_conclusion_drawn_from_what_the_poem_leaves_unsaid_is_still_the_link(conclusion):
    """Fixer self-check on the closing-link rule: what the poem leaves unsaid, or a possessive "not the poem's", is not a
    caveat on the reading's grounds, so en-p5's conclusion rephrased that way is still the material link (and the note
    after it is not)."""
    rep = english(EN_P5["response_text"].replace(P5_CONCLUSION, conclusion))
    assert [(c.claim_id, c.claim_text) for c in rep.claims if c.claim_role == "link"] == [("p1-s11", conclusion)]
    assert claim(rep, P5_NOTE).claim_role == "other"


# ------------------------------------------------------------ adversarial-live major: an English answer made only of notes


@pytest.mark.parametrize("text", [
    "Quotations are from the supplied extract; check them before use.\n\nThe word count is approximate.\n\nSyllabus level was not stated.",
    "Quotations follow the 1633 spelling of the supplied text. The paragraph is under the word limit. Syllabus level was not stated.",
])
def test_an_english_answer_made_only_of_notes_carries_no_answer(text):
    _ch, reply, receipt = through_hub(EN_T12, text)
    assert not [c for c in reply.payload["claims"] if c["materiality"] == "material"]
    assert any(f.code == "INT-REQ-012" and f.severity == "error" for f in receipt.findings)


# ------------------------------------------------------------ communication-fidelity major: a subject that names the source of the items

SOURCED_SELF_CERTIFICATIONS = [
    "Each quotation of the History specialist above is exact.",
    "All quotations from the History specialist above are accurate.",
    "The quotations of the poem above are exact.",
    "My quotations of both texts are exact.",
    "The quotations from the History report have all been verified against it.",
    "Every figure taken from the History specialist has been reproduced exactly.",
    "The figures quoted from the History specialist are exact.",
    "The History specialist's words are quoted above exactly as delivered.",
]


@pytest.mark.parametrize("sentence", SOURCED_SELF_CERTIFICATIONS)
def test_self_certifications_naming_the_source_of_the_items_are_other_on_every_parser(sentence):
    assert md.is_self_certification(sentence) and md.is_note_sentence(sentence)
    assert_self_report(english(EN_P5["response_text"] + " " + sentence), sentence)
    assert_self_report(history(HI_T11["response_text"].replace(T11_ANCHOR, T11_ANCHOR + " " + sentence, 1)), sentence)
    assert_self_report(generic(HI_T11["response_text"] + " " + sentence), sentence)


@pytest.mark.parametrize("sentence", SOURCED_SELF_CERTIFICATIONS[:4])
def test_self_certifications_naming_the_source_reach_the_router_named(sentence):
    _ch, _hrep, erep, erc = p5_exchange(EN_P5["response_text"] + " " + sentence)
    [c] = [c for c in erep.payload["claims"] if c["claim_text"] == sentence]
    assert c["claim_role"] == "other" and c["advisory_verification_status"]
    assert any(f.code == "INT-HANDOFF-006" and c["claim_id"] in f.claim_ids for f in erc.findings)
    assert any(f.code == "ES-META-001" and c["claim_id"] in f.claim_ids for f in erc.structural_findings)


# ------------------------------------------------------------ adversarial-live major: compliance self-reports

COMPLIANCE_SELF_REPORTS = [
    "The paragraph is under the word limit.",
    "This paragraph stays within the 300-word limit and answers every part of the question.",
    "The answer meets every constraint in the request.",
    "Both request items are addressed above.",
    "This response complies with the router's instructions.",
    "Every quotation is reproduced exactly as it appears in the extract.",
    "All quotations follow the 1633 spelling of the supplied text.",
    "Word count: 258.",
]


@pytest.mark.parametrize("sentence", COMPLIANCE_SELF_REPORTS)
def test_compliance_self_reports_are_other_with_the_advisory_status_on_every_parser(sentence):
    assert md.is_self_certification(sentence) and md.is_note_sentence(sentence)
    assert_self_report(english(EN_T12["response_text"].replace(T12_ANCHOR, T12_ANCHOR + " " + sentence, 1), EN_T12), sentence)
    assert_self_report(history(HI_T11["response_text"].replace(T11_ANCHOR, T11_ANCHOR + " " + sentence, 1)), sentence)
    assert_self_report(generic(HI_T11["response_text"].replace(T11_ANCHOR, T11_ANCHOR + " " + sentence, 1)), sentence)


@pytest.mark.parametrize("sentence", COMPLIANCE_SELF_REPORTS)
def test_compliance_self_reports_reach_the_router_named_on_both_branches(sentence):
    for item, anchor, extra in ((EN_T12, T12_ANCHOR, "ES-META-001"), (HI_T11, T11_ANCHOR, None)):
        _ch, reply, receipt = through_hub(item, item["response_text"].replace(anchor, anchor + " " + sentence, 1))
        [c] = [c for c in reply.payload["claims"] if c["claim_text"] == sentence]
        assert c["claim_role"] == "other" and c["materiality"] == "supporting" and c["advisory_verification_status"], (item["task_id"], c["claim_role"])
        assert any(f.code == "INT-HANDOFF-006" and c["claim_id"] in f.claim_ids for f in receipt.findings), item["task_id"]
        if extra:
            assert extra in codes(receipt)


def test_a_word_count_line_under_an_english_paragraph_is_its_own_self_report():
    # the English splitter cuts before a figure, so the line under the paragraph is not glued to its last sentence
    rep = english(EN_T12["response_text"].replace(T12_ANCHOR, T12_ANCHOR + "\n258 words.", 1), EN_T12)
    assert_self_report(rep, "258 words.")
    assert split_sentences("See l. 4 and p. 12 of c. 1900, No. 5 here. 1882 alone brought more.") == [
        "See l. 4 and p. 12 of c. 1900, No. 5 here.", "1882 alone brought more."]


@pytest.mark.parametrize("sentence", [
    "258 words.", "(about 250 words)", "Words: 312", "The word count is 298.", "The paragraph has 320 words.",
    "Quotations follow the 1633 spelling of the supplied text.", "The essay addresses every part of the question.",
    "All parts of the question have been answered.",
])
def test_word_count_lines_and_further_compliance_shapes_are_self_reports(sentence):
    assert md.is_self_certification(sentence)


@pytest.mark.parametrize("sentence", [
    # arguments and source criticism of the same shapes
    "The poem answers every question the speaker asks.",
    "The speaker stays within the limits of decorum.",
    "The paragraph argues that the sonnet stays within its form.",
    "This paragraph answers the question by weighing two strands.",
    "All the constraints are satisfied.",
    "Both conditions were met by 1871.",
    "The demands of the Chartists were met in part by 1867.",
    "The figures of the History specialist are accurate.",
    "The figures from the History report are reliable because they come from the census.",
    "The census figures are reproduced exactly in Mitchell's tables.",
    "Every quotation from the poem is carefully chosen.",
    "The quotations from the poem are exact in their rhythm.",
    "The speech runs to 258 words.",
    "The paragraph should stay within the word limit.",
    "The answer is not under the word limit.",
    "The History specialist's figures show that immigration rose.",
    # a figure of the poem quoting another, and a repetition placed in the text (fixer self-check)
    "The speaker's words are quoted exactly by Love.",
    "The speaker's words are reproduced exactly in the final line.",
])
def test_argument_sentences_of_the_same_shapes_are_not_self_reports(sentence):
    assert not md.is_self_certification(sentence)


@pytest.mark.parametrize("text", [
    "The paragraph " + "comfortably " * 2000 + "is under the word limit",
    "Each quotation of the " + "History specialist of the " * 900 + "poem above",
    "That account marks its " + "very " * 2000 + "figures",
    "Quotations " + "from the supplied extract " * 900,
    "Word count: " + "1" * 5000 + " words words",
])
def test_the_new_rules_read_pathological_text_in_linear_time(text):
    start = time.perf_counter()
    md.is_self_certification(text)
    md.is_note_sentence(text)
    md.is_provenance_note(text)
    assert time.perf_counter() - start < 2.0


# ------------------------------------------------------------ communication-fidelity minor: "?", "!" and the pronoun "I" end a sentence


def test_a_sentence_ending_in_the_pronoun_i_or_a_question_mark_ends_there():
    assert split_sentences("Who made the eyes but I? The question is rhetorical.") == ["Who made the eyes but I?", "The question is rhetorical."]
    assert split_sentences('He asks "Who made the eyes but I?" The modal "cannot" matters.') == ['He asks "Who made the eyes but I?"', 'The modal "cannot" matters.']
    assert split_sentences("No one speaks but I. The point stands.") == ["No one speaks but I.", "The point stands."]
    assert split_sentences('The only speaker is her "I". The point stands.') == ['The only speaker is her "I".', "The point stands."]
    assert split_sentences("Wow! The point stands.") == ["Wow!", "The point stands."]
    # initials, listed abbreviations and a run of initials with "I." stay inside the sentence
    assert split_sentences("As I. A. Richards argued, the point stands. Next.") == ["As I. A. Richards argued, the point stands.", "Next."]
    assert split_sentences("J. I. Packer wrote it. Next.") == ["J. I. Packer wrote it.", "Next."]
    assert split_sentences("T. S. Eliot wrote it. The key word is plain.") == ["T. S. Eliot wrote it.", "The key word is plain."]
    assert split_sentences("See l. 4 of the poem. The key word is plain.") == ["See l. 4 of the poem.", "The key word is plain."]


def test_en_t12_delivers_the_question_and_the_modal_sentence_as_two_claims():
    rep = english(EN_T12["response_text"], EN_T12)
    question = next(c for c in rep.claims if c.claim_role != "evidence" and "Who made the eyes but I?" in c.claim_text)
    assert question.claim_id == "p3-s02" and question.claim_text.endswith('as the short question "Who made the eyes but I?"')
    modal = next(c for c in rep.claims if c.claim_text.startswith('The modal "cannot" presents refusal as incapacity'))
    assert modal.claim_id == "p3-s03" and modal.claim_role == "interpretation"


def test_a_self_certification_after_the_question_demotes_only_itself():
    sc = "Every quotation in this paragraph has been checked against the poem."
    text = EN_T12["response_text"].replace('"Who made the eyes but I?" The modal', f'"Who made the eyes but I?" {sc} The modal')
    rep = english(text, EN_T12)
    assert_self_report(rep, sc)
    question = next(c for c in rep.claims if c.claim_role != "evidence" and "Who made the eyes but I?" in c.claim_text)
    assert question.claim_role == "interpretation" and question.advisory_verification_status is None
    _ch, _reply, receipt = through_hub(EN_T12, text)
    sc_id = claim(rep, sc).claim_id
    where = {f.message.split(" contains")[0] for f in receipt.structural_findings if f.code == "CORE-SELF-001"}
    meta = [f for f in receipt.structural_findings if f.code == "ES-META-001" and sc_id in f.claim_ids]
    assert meta and where == {"paragraph 3, sentence 3"} and meta[0].message.startswith("paragraph 3, sentence 3 ")


# ------------------------------------------------------------ communication-fidelity minor: a colleague's reported view on the English branch


def test_a_colleagues_reported_statement_is_a_perspective_on_the_english_branch():
    rep = english(EN_P5["response_text"])
    c = claim(rep, next(s for s in split_sentences(EN_P5["response_text"]) if s.startswith("The History specialist states that")))
    assert (c.claim_id, c.claim_role, c.materiality, c.certainty) == ("p1-s10", "perspective", "supporting", "probable")
    assert any("attributes this view to a peer specialist" in a for a in c.assumptions)
    assert all(r.document_id == "peer:hi-p5" for r in rep.claims if r.claim_id in c.supporting_claim_ids for r in r.source_refs)
    point = next(x for x in rep.claims if x.claim_role == "point")
    assert point.claim_text.startswith("Lazarus replaces")


@pytest.mark.parametrize("sentence, attributed", [
    ('The History specialist states that "Hostility toward one group was already written into law".', True),
    ("The History specialist's reading places the poem in 1883.", True),
    ("Read against the History specialist's account, the welcome sounds ironic.", False),
    ("The welcome, bearing out the History specialist's claim, is spoken into a divided country.", False),
    ("The History specialist's figures are from memory.", False),
])
def test_peer_attribution_is_decided_by_the_sentences_subject(sentence, attributed):
    assert md.is_peer_attribution(sentence) is attributed


# ------------------------------------------------------------ harness regression: a fence of prose is the answer in the channel's word count


def test_a_fence_of_prose_keeps_its_body_and_a_code_or_receipt_fence_does_not():
    prose = ("García Márquez separates the two judgements, so that the court and the town grant the twins innocence. "
             "The extract keeps their guilt physically and morally visible, and the reader is left to weigh both.")
    text = f"```text\n{prose}\n```\n\n**Word count: 34**"
    assert md.strip_markup(text).strip().startswith("García Márquez separates")
    answer, notes = count_answer_words(text)
    assert answer == count_words(prose) and notes == 3 and count_paragraphs(text) == 1
    assert md.strip_markup('```json\n{"receipt_id": "4be1c0", "status": "ACCEPTED"}\n```').strip() == ""
    assert md.strip_markup("```\nfooter\n```").strip() == ""
    assert md.strip_markup("```python\n" + "x = 1. y = 2. " * 10 + "\n```").strip() == ""
