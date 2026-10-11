"""English specialist parser: segmentation, roles, supporting ids, excerpts, immutability."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import EnglishSpecialistAdapter
from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.adapters.english_specialist import parser
from epinoic_logic.translate.contracts import sha256_text

from .conftest import DOC_ID, TEXT, by_id, by_role, parse, supplied

PARAGRAPH = (
    "The setting conveys neglect. "
    'The lamp "stays unlit," and the metaphor of darkness marks an absence. '
    "Nothing in the hall is attended to. "
    "Effectively, the room is presented as abandoned. "
    'The noun "hall" is ordinarily a place of passage; here nobody passes. '
    "Thus the setting conveys neglect."
)


def test_roles_follow_the_documented_rules():
    report = parse(PARAGRAPH)
    roles = {c.claim_id: c.claim_role for c in report.claims}
    assert roles["p1-point"] == "point"
    assert roles["p1-s02"] == "device"            # 'metaphor'
    assert roles["p1-s03"] == "interpretation"    # no device vocabulary, no signpost
    assert roles["p1-s04"] == "link"              # 'Effectively,'
    assert roles["p1-s05"] == "device"            # 'noun'
    assert roles["p1-s06"] == "link"              # 'Thus'
    assert roles["p1-q01"] == "evidence" and roles["p1-q02"] == "evidence"
    assert by_id(report, "p1-point").claim_text == "The setting conveys neglect."


def test_supporting_ids_wire_point_links_and_sentences():
    report = parse(PARAGRAPH)
    point = by_id(report, "p1-point")
    assert point.supporting_claim_ids == ["p1-q01", "p1-s02", "p1-s03", "p1-q02", "p1-s05"]
    assert point.parent_claim_id is None and point.materiality == "material"
    device = by_id(report, "p1-s02")
    assert device.supporting_claim_ids == ["p1-q01"] and device.parent_claim_id == "p1-point"
    assert by_id(report, "p1-s03").supporting_claim_ids == [] and by_id(report, "p1-s05").supporting_claim_ids == ["p1-q02"]
    for link_id in ("p1-s04", "p1-s06"):
        link = by_id(report, link_id)
        assert link.supporting_claim_ids[0] == "p1-point" and set(point.supporting_claim_ids) <= set(link.supporting_claim_ids)
        assert link.parent_claim_id == "p1-point" and link.materiality == "material"
    for evidence in by_role(report, "evidence"):
        assert evidence.parent_claim_id == "p1-point" and evidence.proposed_claim_kind == "factual"
    known = {c.claim_id for c in report.claims}
    assert all(set(c.supporting_claim_ids) <= known for c in report.claims)


def test_excerpts_drop_sentence_punctuation_but_claim_text_keeps_the_span():
    report = parse(PARAGRAPH)
    q1 = by_id(report, "p1-q01")
    assert q1.claim_text == '"stays unlit,"'
    assert [(r.document_id, r.excerpt) for r in q1.source_refs] == [(DOC_ID, "stays unlit")]
    assert by_id(report, "p1-q02").source_refs[0].excerpt == "hall"


def test_quotation_is_attributed_to_the_document_that_contains_it():
    other = supplied("A different text with a lonely lantern.", "doc-2")
    report = parse('The "lonely lantern" and the "clock ticks on" differ; "nowhere words" fall back.', [other, supplied()])
    refs = {c.claim_text: c.source_refs[0].document_id for c in by_role(report, "evidence")}
    assert refs['"lonely lantern"'] == "doc-2"
    assert refs['"clock ticks on"'] == DOC_ID
    assert refs['"nowhere words"'] == "doc-2"  # first supplied text when none contains it


def test_repeated_quotation_in_a_paragraph_is_one_evidence_claim():
    report = parse('The lamp "stays unlit" at first. The phrase "stays unlit" returns, and the verb "stays" matters.')
    evidence = by_role(report, "evidence")
    assert [c.claim_text for c in evidence] == ['"stays unlit"', '"stays"']
    assert by_id(report, "p1-s02").supporting_claim_ids == ["p1-q01", "p1-q02"]


def test_curly_quotation_marks_are_quotations_too():
    report = parse("The yard is “a measured dose of grey” and still.")
    assert [c.source_refs[0].excerpt for c in by_role(report, "evidence")] == ["a measured dose of grey"]


def test_multi_paragraph_answer_has_thesis_bodies_and_conclusion():
    essay = "\n\n".join([
        "The poem presents neglect as a settled condition. Its method is the unlit lamp.",
        PARAGRAPH,
        'The clock "ticks on" without anyone to hear it. The verb "ticks" is mechanical. Hence time itself is unattended.',
        "Ultimately, neglect is presented as the poem's settled condition. Nothing changes.",
    ])
    paragraphs = parser.segment(essay)
    assert [p.kind for p in paragraphs] == ["thesis", "body", "body", "conclusion"]
    report = parse(essay)
    thesis = by_role(report, "thesis")
    assert [c.claim_id for c in thesis] == ["p1-s01", "p1-s02"]
    assert all(c.supporting_claim_ids == ["p2-point", "p3-point"] for c in thesis)
    conclusion = [c for c in report.claims if c.claim_id.startswith("p4-")]
    assert conclusion and all(c.claim_role == "link" and c.supporting_claim_ids == ["p2-point", "p3-point"] for c in conclusion)
    assert by_id(report, "p3-point").claim_text.startswith("The clock")
    assert by_id(report, "p3-q01").source_refs[0].excerpt == "ticks on"


def test_two_paragraphs_are_thesis_and_body_without_a_conclusion():
    paragraphs = parser.segment("A thesis paragraph here.\n\n" + PARAGRAPH)
    assert [p.kind for p in paragraphs] == ["thesis", "body"]


def test_last_paragraph_without_a_signpost_stays_a_body_paragraph():
    paragraphs = parser.segment("Thesis.\n\n" + PARAGRAPH + "\n\nThe clock ticks. It is loud.")
    assert [p.kind for p in paragraphs] == ["thesis", "body", "body"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The citation (l. 12) is given. Next sentence here.", ["The citation (l. 12) is given.", "Next sentence here."]),
        ("Mr. Smith said so. He left.", ["Mr. Smith said so.", "He left."]),
        ('It ends with a quote "like this." Then "another one," she said.', ['It ends with a quote "like this."', 'Then "another one," she said.']),
        ("Is it so? Yes! It is.", ["Is it so?", "Yes!", "It is."]),
        ("No split before lowercase. e.g. this stays. Done.", ["No split before lowercase. e.g. this stays.", "Done."]),
        ("One sentence without a terminator", ["One sentence without a terminator"]),
    ],
)
def test_sentence_splitting(text, expected):
    assert parser.split_sentences(text) == expected


def test_report_is_immutable_and_hashed_over_the_verbatim_text():
    report = parse(PARAGRAPH)
    assert report.original_response == PARAGRAPH
    assert report.response_sha256 == sha256_text(PARAGRAPH)
    assert report.agent_id == "english-specialist" and report.subject == "English A: Literature"
    assert report.supplied_texts[0].document_id == DOC_ID
    assert any("parser proposals" in a for a in report.assumptions)


def test_parse_is_deterministic():
    a, b = parse(PARAGRAPH), parse(PARAGRAPH)
    strip = lambda r: r.model_dump(mode="json", exclude={"created_at"})  # noqa: E731
    assert strip(a) == strip(b)


def test_no_supplied_text_leaves_evidence_without_refs_and_records_the_gap():
    report = parse(PARAGRAPH, texts=[])
    assert all(c.source_refs == [] for c in by_role(report, "evidence"))
    assert report.unresolved_issues and "no supplied text" in report.unresolved_issues[0]


@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_empty_answer_is_rejected(text):
    with pytest.raises(AdapterError):
        parse(text)


def test_adapter_class_delegates_and_defaults_the_subject():
    adapter = EnglishSpecialistAdapter()
    report = adapter.parse_response(PARAGRAPH, request_id="r", task_id="t", report_id="p", task_type="analytical_paragraph", supplied_texts=[supplied()])
    assert adapter.agent_id == "english-specialist" and report.subject == parser.DEFAULT_SUBJECT
    assert {c.claim_role for c in report.claims} == {"point", "evidence", "device", "interpretation", "link"}
    assert isinstance(adapter.structural_checks(report), list)


def test_quotation_count_and_word_count_helpers():
    [para] = parser.segment(PARAGRAPH)
    assert para.word_count == len(PARAGRAPH.split())
    assert [q.excerpt for q in para.quotations] == ["stays unlit", "hall"]
    assert para.quotations[0].words == 2 and para.quotations[1].words == 1
    assert "[quotation]" in parser.strip_quotations(PARAGRAPH) and '"' not in parser.strip_quotations(PARAGRAPH)
