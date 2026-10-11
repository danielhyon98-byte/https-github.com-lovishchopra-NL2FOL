"""Regression tests for the round-4 overseer findings assigned to the shared pre-segmentation
helpers, the English parser and the generic parser (results-audit, communication-fidelity and
adversarial-live reports): a quoted colleague's from-memory label is quotation, not a note; only
a sentence whose core is empty is a note, and trailing appositive or concessive labels are
clauses; disclaimers ("should be checked", "have not been verified") are notes, never
self-certifications; self-certifications outside the old vocabulary are named on every branch;
"Read together, ..." and a closing claim over the paragraph's evidence are links; single-quoted
quotations whose words carry an apostrophe are read, checked and attributed; brace-like text is
scanned in linear time; a CR-only paragraph break is a paragraph break; and a quotation located in
no text, in a sentence that names several texts, is credited by the sentence's own wording.

The texts are the genuine round-4 specialist answers (tests/adapters/data/r4_specialists.json)."""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.english_specialist import parser as en_parser
from epinoic_logic.adapters.english_specialist.parser import parse_response, segment
from epinoic_logic.adapters.english_specialist.structural import structural_checks
from epinoic_logic.adapters.history_specialist import sentences as hi_sentences
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.channel.request_parser import count_answer_words, count_words
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

DATA = json.loads((Path(__file__).parent / "data" / "r4_specialists.json").read_text(encoding="utf-8"))
EN_P3, HI_P3, HI_T7, HI_T8, EN_T7, EN_T8 = (DATA[k] for k in ("en-p3", "hi-p3", "hi-t7", "hi-t8", "en-t7", "en-t8"))
KEY = b"round4-english-fixer-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
PEER = SuppliedText(document_id="peer:hi-p3", title="history-specialist report rep-hi-p3-0 relayed through the hub", author="history-specialist",
                    text=HI_P3["response_text"])
EN_P3_LAST = ('The poem never mentions the war, so this reading rests on the History specialist\'s context, whose "dates and figures" are, in its own words, '
              '"from memory and should be checked before they are cited".')
HI_P3_LABEL = "The dates and figures in this paragraph are from memory and should be checked before they are cited."


def docs_of(item: dict) -> list[SuppliedText]:
    return [SuppliedText(**d) for d in item["supplied_texts"]]


def english(text: str, item: dict = EN_P3, extra=(PEER,)) -> SpecialistReport:
    return parse_response(text, request_id="r", task_id=item["task_id"], report_id="rep", task_type=item["task_type"], supplied_texts=[*docs_of(item), *extra])


def history(text: str, docs=()) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", subject="History", task_type="short_answer", supplied_texts=list(docs))


def generic(text: str, docs=()) -> SpecialistReport:
    return GenericTextParser("economics-specialist").parse_response(text, request_id="r", task_id="t", report_id="rep", subject="Economics", task_type="short_answer", supplied_texts=list(docs))


def claim_with(report: SpecialistReport, fragment: str):
    return next(c for c in report.claims if fragment in c.claim_text)


def through_hub(item: dict, text: str, *, extra_docs=(), report_id: str = "rep-x"):
    docs = [*docs_of(item), *extra_docs]
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id=f"plan-{item['task_id']}", request_id=f"req-{item['task_id']}", task_id=item["task_id"], subject=item["subject"],
                                task_type=item["task_type"], selected_agent_ids=[item["agent_id"], "dummy-combinator"], allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch(item["task_id"], item["agent_id"], item["question"], docs)
    reply, receipt = hub.receive(item["task_id"], m.message_id, text, agent_id=item["agent_id"], report_id=report_id)
    return ch, reply, receipt


def codes(receipt) -> set[str]:
    return {f.code for f in receipt.findings} | {f.code for f in receipt.structural_findings}


# ------------------------------------------------------------ results-audit major / communication-fidelity major: notes and labels


def test_a_sentence_quoting_the_peers_from_memory_label_is_quotation_not_a_note():
    assert EN_P3["response_text"].endswith(EN_P3_LAST)
    assert md.split_note_clauses(EN_P3_LAST) == (EN_P3_LAST, []) and not md.is_note_sentence(EN_P3_LAST)
    # the whole answer counts toward the word bound: 287 words, none set aside as note or meta-text
    assert count_answer_words(EN_P3["response_text"]) == (287, 0) == (count_words(EN_P3["response_text"]), 0)
    rep = english(EN_P3["response_text"])
    last = claim_with(rep, "The poem never mentions the war")
    assert last.claim_role == "interpretation" and not any("label" in a for a in last.assumptions)


def test_en_p3_lengthened_past_its_word_bound_is_measured_in_full_and_named():
    extra = " The sonnet's present tense holds the city in one suspended instant that the reader shares before smoke returns again."  # 19 words
    text = EN_P3["response_text"] + extra
    assert count_words(text) == 306
    _ch, reply, receipt = through_hub(EN_P3, text, extra_docs=[PEER])
    [c1] = [c for c in receipt.constraint_results if c.constraint_id == "c1"]
    assert c1.satisfied is False and "measured 306 words" in c1.detail and "excluded" not in c1.detail
    assert any(f.code == "INT-REQ-005" and f.severity == "error" for f in receipt.findings) and reply is not None


@pytest.mark.parametrize("sentence, core, note", [
    ("Registered unemployment reached about 6.1 million in February 1932, a figure I give from memory.",
     "Registered unemployment reached about 6.1 million in February 1932.", "a figure I give from memory"),
    ("The Danatbank closed on 13 July 1931, though this date is from memory.", "The Danatbank closed on 13 July 1931.", "though this date is from memory"),
    ("Unemployment peaked at 6.1 million in February 1932 from memory.", "Unemployment peaked at 6.1 million in February 1932.", "from memory"),
    ("Two developments of the years before framed it; dates other than the poem's own are from memory, so check your notes.",
     "Two developments of the years before framed it.", "dates other than the poem's own are from memory, so check your notes"),
])
def test_trailing_and_concessive_labels_are_clauses_and_the_substance_is_kept(sentence, core, note):
    assert md.split_note_clauses(sentence) == (core, [note])
    answer, notes = count_answer_words(sentence)
    assert answer == count_words(core) and notes == count_words(sentence) - count_words(core)


@pytest.mark.parametrize("sentence", [
    "The collapse of the Danatbank in July 1931 is illustrative of how the slump became a banking crisis.",
    "The speaker recalls the scene from memory, which explains why the city seems held still.",
    'Wordsworth wrote the sonnet from memory of a single morning, so the city is first animated when it "doth, like a garment, wear" the morning\'s beauty.',
    "Wordsworth wrote the poem from memory.",
])
def test_a_label_word_inside_a_substantive_sentence_does_not_make_it_a_note(sentence):
    core, notes = md.split_note_clauses(sentence)
    assert core == sentence and notes == [] and not md.is_note_sentence(sentence)


@pytest.mark.parametrize("sentence", [
    HI_P3_LABEL,
    "Dates and figures are from memory; verify them against your notes before use.",
    "Dates other than the poem's own are from memory, so check your notes.",
    "The dates in this paragraph have not been checked.",
    "This answer has not been verified against the statistical yearbooks.",
    "The figures in this answer must be verified before use.",
    "These figures are yet to be verified.",
    "The quotation above is quoted from memory and should be checked.",
    "These examples are illustrative.",
    "Figures, from memory.",
    "From memory, verify these dates before use.",
    "Syllabus version and level were not stated.",
])
def test_labels_and_disclaimers_are_still_notes(sentence):
    assert md.is_note_sentence(sentence) and md.split_note_clauses(sentence) == ("", [sentence])


def test_history_parser_keeps_dated_evidence_with_a_trailing_or_concessive_label():
    text = HI_T8["response_text"].replace(
        "The turning point was 1930.",
        "Registered unemployment reached about 6.1 million in February 1932, a figure I give from memory. "
        "The Danatbank closed on 13 July 1931, though this date is from memory. "
        "The collapse of the Danatbank in July 1931 is illustrative of how the slump became a banking crisis. The turning point was 1930.")
    rep = history(text)
    for fragment, label in (("a figure I give from memory", "a figure I give from memory"), ("though this date is from memory", "though this date is from memory")):
        c = claim_with(rep, fragment)
        assert c.claim_role == "evidence" and any(f"('{label}')" in a for a in c.assumptions), (c.claim_role, c.assumptions)
    assert claim_with(rep, "is illustrative of how").claim_role != "other"
    rep_generic = generic(text)
    for fragment in ("a figure I give from memory", "though this date is from memory", "is illustrative of how"):
        assert claim_with(rep_generic, fragment).claim_role != "other"


def test_english_analysis_about_memory_keeps_its_role_and_raises_no_es_src_003():
    base = EN_T7["response_text"]
    theme = base.replace("The turn deepens the opening's silence rather than overturning it.",
                         "The speaker recalls the scene from memory, which explains why the city seems held still. The turn deepens the opening's silence rather than overturning it.")
    rep = english(theme, EN_T7, extra=())
    assert claim_with(rep, "recalls the scene from memory").claim_role == "interpretation"
    assert "ES-SRC-003" not in {f.code for f in structural_checks(rep)}
    point = base.replace("The city is first animated when it", "Wordsworth wrote the sonnet from memory of a single morning, so the city is first animated when it")
    rep2 = english(point, EN_T7, extra=())
    c = claim_with(rep2, "from memory of a single morning")
    assert c.claim_role == "point" and c.materiality == "material"
    # the sentence's only quotation is located in doc-wb, and "[quotation]" (the placeholder) is not a quotation word
    assert "ES-SRC-003" not in {f.code for f in structural_checks(rep2)}
    # a genuine disclosure is still named
    own = base.replace("The city is first animated when it", "As I recall, the city is first animated when it")
    assert "ES-SRC-003" in {f.code for f in structural_checks(english(own, EN_T7, extra=()))}


# ------------------------------------------------------------ results-audit / communication-fidelity / adversarial-live minors: disclaimers


@pytest.mark.parametrize("sentence", [
    HI_P3_LABEL,
    "The dates in this paragraph have not been checked.",
    "This answer has not been verified against the statistical yearbooks.",
    "The figures in this paragraph must be verified before use.",
    "Dates and figures are from memory; verify them against your notes before use.",
    "I have not checked these dates.",
])
def test_a_disclaimer_is_never_a_self_certification(sentence):
    assert not md.is_self_certification(sentence)
    rep = history(HI_T8["response_text"] + " " + sentence)
    c = claim_with(rep, sentence[:30])
    assert c.claim_role == "other" and c.advisory_verification_status is None


def test_hi_p3_delivery_records_its_label_as_a_note_with_no_self_report():
    rep = history(HI_P3["response_text"])
    label = claim_with(rep, HI_P3_LABEL)
    assert label.claim_role == "other" and label.advisory_verification_status is None and label.materiality == "supporting"
    assert not any("certif" in issue for issue in rep.unresolved_issues)
    _ch, reply, receipt = through_hub(HI_P3, HI_P3["response_text"])
    assert reply is not None and "INT-HANDOFF-006" not in codes(receipt) and "CORE-SELF-001" not in codes(receipt)
    assert not any("certif" in issue for issue in reply.payload["unresolved_issues"])
    assert not any(c.get("advisory_verification_status") for c in reply.payload["claims"])


# ------------------------------------------------------------ communication-fidelity major / adversarial-live major: self-certification


SELF_CERTIFICATIONS = [
    "I have checked each of these dates and figures against the official statistics, and every one of them is correct.",
    "All of these figures have been verified against the Statistisches Reichsamt yearbooks.",
    "The figures here are accurate and can be relied upon.",
    "The figures here are correct to the nearest tenth.",
    "Each of these claims has been confirmed by the verification engine.",
    "Z3 proved the argument above.",
    "The hub has already accepted this paragraph.",
    "No errors were found in this paragraph.",
    "Every quotation above appears verbatim in the sonnet.",
    "I have checked each line against the text.",
    "I verified each figure before writing.",
]


@pytest.mark.parametrize("sentence", SELF_CERTIFICATIONS)
def test_self_certifications_outside_the_old_vocabulary_are_named_on_every_branch(sentence):
    assert md.is_self_certification(sentence) and md.is_note_sentence(sentence)
    for rep in (history(HI_T8["response_text"] + " " + sentence), english(EN_T7["response_text"] + " " + sentence, EN_T7, extra=()),
                generic(HI_T8["response_text"] + " " + sentence)):
        c = claim_with(rep, sentence[:30])
        assert c.claim_role == "other" and c.materiality == "supporting" and c.advisory_verification_status, (rep.agent_id, c.claim_role)


def test_history_self_certification_reaches_the_router_as_an_advisory_self_report():
    sentence = SELF_CERTIFICATIONS[0]
    _ch, reply, receipt = through_hub(HI_T8, HI_T8["response_text"] + " " + sentence)
    [c] = [c for c in reply.payload["claims"] if c["claim_text"] == sentence]
    assert c["claim_role"] == "other" and c["materiality"] == "supporting" and c["advisory_verification_status"]
    assert any(f.code == "INT-HANDOFF-006" and c["claim_id"] in f.claim_ids for f in receipt.findings)
    _ch, _reply, receipt2 = through_hub(HI_T8, HI_T8["response_text"] + " " + SELF_CERTIFICATIONS[1])
    assert "CORE-SELF-001" in codes(receipt2)  # "all of these figures have been verified" is in the pack's own vocabulary too


@pytest.mark.parametrize("sentence", [
    "This paragraph argues that the court is correct to uphold the thesis.",
    "Every figure in the sculpture is exact and the sneer is cold.",
    "Every date given above was checked against the 1929 census.",
    "In May 1930 the figures were checked by the board.",
    "The engine of the economy was confirmed as heavy industry.",
    "Each of these historians argues that the slump was decisive.",
    "We have seen that the city is held still.",
])
def test_argument_sentences_stay_arguments(sentence):
    assert not md.is_self_certification(sentence)


# ------------------------------------------------------------ communication-fidelity minor: links


def test_read_together_closes_en_p3_as_a_material_link_and_dropping_it_is_named():
    rep = english(EN_P3["response_text"])
    link = claim_with(rep, "Read together, the clear air")
    assert link.claim_id == "p1-s08" and link.claim_role == "link" and link.materiality == "material"
    ch, reply, _receipt = through_hub(EN_P3, EN_P3["response_text"], extra_docs=[PEER], report_id="rep-en-p3")
    point = next(c for c in reply.payload["claims"] if c["claim_role"] == "point")
    claims = [SynthesizedClaim(claim_id="s0", text=point["claim_text"], certainty="probable", source_claim_ids=[point["claim_id"]], transformation="carried")]
    body = claims[0].text
    syn = Synthesis(synthesis_id="syn-p3", request_id=ch.plan.request_id, task_id=ch.plan.task_id, combinator_agent_id="dummy-combinator", source_report_ids=["rep-en-p3"],
                    claims=claims, text=body, text_sha256=sha256_text(body), created_at="2026-10-11T15:00:00Z")
    _rel, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    assert any(f.code == "INT-LEDGER-002" and f.severity == "error" and "p1-s08" in f.claim_ids for f in rr.findings)


@pytest.mark.parametrize("lead", ["Read together", "Taken together", "Together", "In this light", "Read against the treaty"])
def test_link_leads_open_a_link_inside_a_body_paragraph(lead):
    text = (f'The city is held still. The houses "seem asleep" and the river "glideth at his own sweet will". {lead}, the stillness reads as rest. '
            "The reader shares the pause.")
    [para] = segment(text)
    assert [s.role for s in para.sentences][2] == "link"


def test_a_closing_claim_over_the_evidence_is_the_link_of_a_single_paragraph_answer_only():
    body = ('The city is held still. The houses "seem asleep" and the river "glideth at his own sweet will". '
            "The calm and the sleeping houses suggest that the poem captures a suspended morning.")
    [para] = segment(body)
    assert [s.role for s in para.sentences] == ["point", "interpretation", "link"]
    two = segment("Wordsworth stills the city in one morning.\n\n" + body + "\n\nThe river, too, is calm and the reader rests.")
    assert [s.role for s in two[1].sentences][-1] == "interpretation"  # several paragraphs: no closing-claim rule


# ------------------------------------------------------------ adversarial-live major: single marks with apostrophes


@pytest.mark.parametrize("text, inners", [
    ("says 'I don't mean to say that I know' and", ["I don't mean to say that I know"]),
    ("The cry 'Ne'er saw I, never felt, a calm so shallow' would undo the turn.", ["Ne'er saw I, never felt, a calm so shallow"]),
    ("Even the aside 'Scrooge's name was good upon 'Change' treats commerce as a court of record.", ["Scrooge's name was good upon 'Change"]),
    ("Brüning told the cabinet 'we can't pay and we won't pay' in June 1931.", ["we can't pay and we won't pay"]),
    ("‘I don’t know what a door-nail is’, he admits.", ["I don’t know what a door-nail is"]),
    ("He spoke of 'the Brothers' and 'the sisters of mercy' together.", ["the Brothers", "the sisters of mercy"]),
    ("'Change is the law of life,' he said.", ["Change is the law of life,"]),
    ("the twins' fear wasn't the 'point' of it", []),
    ("The workers' demands and the employers' response met in 1930.", []),
])
def test_single_marks_are_paired_by_context(text, inners):
    assert [inner for _a, _b, inner in md.find_quotation_spans(text)] == inners


@pytest.mark.parametrize("item, original, altered", [
    (EN_T8, "The word \"whatever\" overstates the certainty", "The narrator later admits 'I don't know what a door-nail is', which undercuts the proof. The word \"whatever\" overstates the certainty"),
    (EN_T8, "The word \"whatever\" overstates the certainty", "Even the aside 'Scrooge's name was good upon the Exchange' treats commerce as a court of record. The word \"whatever\" overstates the certainty"),
    (EN_T7, "The turn deepens the opening's silence rather than overturning it.", "The cry 'Ne'er saw I, never felt, a calm so shallow' would undo the turn. The turn deepens the opening's silence rather than overturning it."),
])
def test_an_invented_or_altered_single_quoted_quotation_with_an_apostrophe_is_refuted(item, original, altered):
    assert original in item["response_text"]
    _ch, reply, receipt = through_hub(item, item["response_text"].replace(original, altered))
    quoted = re.search(r"'(.+?)'(?= would| treats|,)", altered).group(1)
    [c] = [c for c in reply.payload["claims"] if c["claim_role"] == "evidence" and any(r.get("excerpt") == quoted for r in c["source_refs"])]
    assert any(f.code == "INT-REQ-003" and f.severity == "error" and c["claim_id"] in f.claim_ids for f in receipt.findings)
    sentence_claims = [x["claim_id"] for x in reply.payload["claims"] if quoted in x["claim_text"] and x["claim_role"] != "evidence"]
    assert not any(f.code == "ES-STY-001" and set(f.claim_ids) & set(sentence_claims) for f in receipt.structural_findings)  # the quoted "I" is not the writer's


def test_a_correct_single_quoted_quotation_with_an_aphetic_form_is_found_and_an_altered_peer_quotation_is_refuted():
    text = EN_T8["response_text"].replace("The word \"whatever\" overstates the certainty",
                                          "Even the aside 'Scrooge's name was good upon 'Change' treats commerce as a court of record. The word \"whatever\" overstates the certainty")
    _ch, reply, receipt = through_hub(EN_T8, text)
    [c] = [c for c in reply.payload["claims"] if c["claim_role"] == "evidence" and any(r.get("excerpt") == "Scrooge's name was good upon 'Change" for r in c["source_refs"])]
    assert c["source_refs"][0]["document_id"] == "doc-cc" and not any(c["claim_id"] in f.claim_ids for f in receipt.findings if f.code == "INT-REQ-003")
    altered = EN_P3["response_text"].replace("The History specialist describes", "The History specialist says the smokeless air 'stands out as an exception to the city's usual condition'. The History specialist describes")
    _ch, reply2, receipt2 = through_hub(EN_P3, altered, extra_docs=[PEER])
    refuted = [f for f in receipt2.findings if f.code == "INT-REQ-003"]
    [bad] = [c for c in reply2.payload["claims"] if any(r.get("excerpt") == "stands out as an exception to the city's usual condition" for r in c["source_refs"])]
    assert [f.claim_ids for f in refuted] == [[bad["claim_id"]]] and bad["source_refs"][0]["document_id"] == "peer:hi-p3"


def test_an_invented_single_quoted_quotation_with_no_supplied_text_is_unverifiable_on_the_history_branch():
    text = HI_T8["response_text"].replace("The turning point was 1930.", "Brüning told the cabinet 'we can't pay and we won't pay' in June 1931. The turning point was 1930.")
    [f] = [x for x in CorePack().checks(history(text)) if x.code == "CORE-SRC-003"]
    assert "we can't pay and we won't pay" in f.message


# ------------------------------------------------------------ adversarial-live major: brace-like text in linear time


def _reference_json_spans(text: str) -> list[tuple[int, int]]:
    """The pre-round-4 per-opener scan (quadratic), kept here as the specification the linear pass must match."""
    def end_of(start: int) -> int:
        depth, i, n, in_string = 0, start, min(len(text), start + 60_000), False
        while i < n:
            ch = text[i]
            if in_string:
                if ch == "\\":
                    i += 2
                    continue
                if ch == '"':
                    in_string = False
                elif ch == "\n":
                    return -1
            elif ch == '"':
                in_string = True
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    return i + 1
                if depth < 0:
                    return -1
            elif ch == "\n" and re.match(r"\n[ \t]*\n", text[i:]):
                return -1
            i += 1
        return -1

    def is_span(span: str) -> bool:
        s = span.strip()
        if len(s) < 4 or s[0] not in "{[" or s[-1] not in "}]":
            return False
        try:
            parsed = json.loads(s)
        except (ValueError, RecursionError):
            parsed = None
        if isinstance(parsed, dict):
            return True
        if isinstance(parsed, list):
            return any(isinstance(item, dict) for item in parsed)
        return s[1:].lstrip()[:1] == '"' and bool(md.JSON_KEY_RE.search(s))

    spans, i = [], 0
    while i < len(text):
        if text[i] in "{[":
            end = end_of(i)
            if end > i and is_span(text[i:end]):
                spans.append((i, end))
                i = end
                continue
        i += 1
    return spans


def test_json_spans_are_found_as_before_on_random_brace_like_text():
    rng = random.Random(20261011)
    alphabet = ["{", "}", "[", "]", '"', "\\", "\n", "\n\n", " ", "a", ":", ",", "1", '"k": ', '{"status": "OK"}', '[{"a": 1}]', "text. ", '"x"']
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        assert md.find_json_spans(text) == _reference_json_spans(text), repr(text)


def test_bracket_match_ends_agrees_with_the_history_splitters_scan():
    rng = random.Random(7)
    alphabet = ["{", "}", "[", "]", '"', "\\", "\n", " ", "a", '"k": ', '{"s": "OK"}', '[{"a": 1}]']
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        ends = md.bracket_match_ends(text)
        assert all(ends[i] == hi_sentences._balanced_end(text, i) for i, ch in enumerate(text) if ch in "{["), repr(text)


@pytest.mark.parametrize("label, text", [
    ("5,000 nested braces", "{" * 5000 + ' The city "seem asleep" ' + "}" * 5000),
    ("2,000 unclosed braces", 'Wordsworth\'s "seem asleep" makes the calm a perception. ' + "{ " * 2000),
    ("1,000 unclosed JSON fragments", " ".join('{"a": 1, "b": [' for _ in range(1000)) + " The turning point was 1930."),
    ("5,000 nested arrays around an object", "[" * 5000 + "{}" + "]" * 5000),
    ("a keyed object nested 3,000 deep", '{"a": ' * 3000 + "1" + "}" * 3000),
])
def test_brace_like_text_is_scanned_in_linear_time(label, text):
    started = time.perf_counter()
    md.find_json_spans(text)
    md.find_json_spans(text + " ")  # a second, uncached text
    md.bracket_match_ends(text)
    md.find_quotation_spans(text)
    md.is_json_block(text)
    rep = parse_response(text, request_id="r", task_id="t", report_id="rep", task_type="analytical_paragraph", supplied_texts=docs_of(EN_T7))
    structural_checks(rep)
    assert time.perf_counter() - started < 1.0, label


# ------------------------------------------------------------ adversarial-live minor: CR-only paragraph breaks


@pytest.mark.parametrize("item", [EN_T8, EN_T7])
@pytest.mark.parametrize("newline", ["\r", "\r\n"])
def test_a_cr_only_or_crlf_paragraph_break_is_a_paragraph_break(item, newline):
    lf = english(item["response_text"], item, extra=())
    other = english(item["response_text"].replace("\n", newline), item, extra=())
    assert [(c.claim_id, c.claim_role, c.materiality) for c in other.claims] == [(c.claim_id, c.claim_role, c.materiality) for c in lf.claims]
    assert len([c for c in lf.claims if c.materiality == "material"]) == 4


# ------------------------------------------------------------ attribution: a quotation found nowhere, in a sentence naming several texts


def test_an_altered_peer_quotation_in_a_sentence_naming_the_poet_is_credited_to_the_peer():
    sentence = "Wordsworth's clear morning and the History specialist's \"lull rather than a peace\" belong together."
    rep = english("Wordsworth stills the city in one morning. " + sentence + " The calm is the poem's own.")
    [c] = [c for c in rep.claims if c.claim_role == "evidence" and c.claim_text == '"lull rather than a peace"']
    assert [r.document_id for r in c.source_refs] == ["peer:hi-p3"]
    rep_generic = generic("Wordsworth stills the city in one morning. " + sentence, docs=[*docs_of(EN_P3), PEER])
    assert [r.document_id for c in rep_generic.claims for r in c.source_refs] == ["peer:hi-p3"]
    text = EN_P3["response_text"].replace("Read together,", sentence + " Read together,")
    _ch, reply, receipt = through_hub(EN_P3, text, extra_docs=[PEER])
    [bad] = [c for c in reply.payload["claims"] if any(r.get("excerpt") == "lull rather than a peace" for r in c["source_refs"])]
    assert any(f.code == "INT-REQ-003" and bad["claim_id"] in f.claim_ids for f in receipt.findings)
    assert "CORE-SRC-003" not in codes(receipt)


def test_link_leads_are_exported_beside_the_link_signposts_and_do_not_make_a_conclusion():
    assert "Read together" in en_parser.LINK_LEADS and "Read together" not in en_parser.LINK_SIGNPOSTS
    # en-t7's last block opens with "Together," and stays a body paragraph with its own point (the conclusion rule is unchanged)
    assert [p.kind for p in segment(EN_T7["response_text"])] == ["thesis", "body", "body", "body"]
