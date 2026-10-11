"""English specialist structural codes: each one triggered by a crafted text, and clean text stays clean."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.english_specialist import structural
from epinoic_logic.adapters.english_specialist.structural import RULE_SOURCES, structural_checks
from epinoic_logic.adapters.sources import check_excerpt, strip_trailing_punctuation
from epinoic_logic.translate.contracts import SuppliedText

from .conftest import DOC_ID, TEXT, parse, supplied

# A body paragraph that breaks no working rule (two multi-word quotations, embedded, third person, one spelling).
CLEAN_SENTENCES = [
    "The setting conveys neglect.",
    'The lamp "stays unlit" in the hall, and the metaphor of darkness marks an absence that nobody repairs.',
    'The clock "ticks on" while nothing else moves, so time passes without being attended to.',
    "Effectively, the room is presented as abandoned rather than merely empty.",
    "Ultimately, the setting conveys neglect through what is left unlit and unheard.",
]
_FILLER = "The hall is described plainly and the description is allowed to stand without comment from the writer."
CLEAN = " ".join(CLEAN_SENTENCES[:3] + [_FILLER] * 12 + CLEAN_SENTENCES[3:])


def codes(findings):
    return sorted(f.code for f in findings)


def test_clean_paragraph_yields_no_findings():
    report = parse(CLEAN)
    assert 250 <= len(CLEAN.split()) <= 450
    assert structural_checks(report) == []


def test_every_finding_cites_a_working_rule_source():
    for code, source in RULE_SOURCES.items():
        assert source.endswith("(working rule, not an official IB rule)") and len(source) <= 200, code


def test_es_src_001_quotation_not_in_text():
    report = parse(CLEAN.replace('"ticks on"', '"ticks loudly"'))
    findings = [f for f in structural_checks(report) if f.code == "ES-SRC-001"]
    assert len(findings) == 1 and findings[0].severity == "error"
    assert findings[0].claim_ids == ["p1-q02"] and "ticks loudly" in findings[0].message
    assert findings[0].rule_source == RULE_SOURCES["ES-SRC-001"]
    assert "ES-SRC-005" not in codes(structural_checks(report))


def test_es_src_001_unknown_document_is_an_error():
    report = parse(CLEAN, texts=[supplied(TEXT, "doc-2")])
    # the parser attributes to the first text, so re-point one ref at a document that is not supplied
    claim = next(c for c in report.claims if c.claim_id == "p1-q01")
    tampered = report.model_copy(update={"claims": [
        c if c.claim_id != "p1-q01" else c.model_copy(update={"source_refs": [c.source_refs[0].model_copy(update={"document_id": "missing"})]})
        for c in report.claims
    ]})
    found = [f for f in structural_checks(tampered) if f.code == "ES-SRC-001"]
    assert len(found) == 1 and found[0].claim_ids == [claim.claim_id] and "not among the supplied texts" in found[0].message


@pytest.mark.parametrize(
    "citation",
    ["(l. 12)", "(ll. 3-4)", "Act 1.2.3", "Act I, scene ii, 45", "(1.2.3)", "line 12", "lines 3-5", "(p. 7)"],
)
def test_es_src_002_location_citation_without_locator_scheme(citation):
    text = CLEAN.replace("The setting conveys neglect.", f"The setting conveys neglect {citation}.")
    findings = [f for f in structural_checks(parse(text)) if f.code == "ES-SRC-002"]
    assert len(findings) == 1 and findings[0].severity == "error"
    assert findings[0].claim_ids == ["p1-point"] and citation in findings[0].message


def test_es_src_002_not_raised_when_a_supplied_text_has_a_locator_scheme():
    text = CLEAN.replace("The setting conveys neglect.", "The setting conveys neglect (l. 12).")
    report = parse(text, texts=[supplied(TEXT, DOC_ID, "line")])
    assert "ES-SRC-002" not in codes(structural_checks(report))


def test_es_src_002_raised_when_no_text_was_supplied_at_all():
    text = CLEAN.replace("The setting conveys neglect.", "The setting conveys neglect (l. 12).")
    found = [f for f in structural_checks(parse(text, texts=[])) if f.code == "ES-SRC-002"]
    assert len(found) == 1 and "no text was supplied" in found[0].message


def test_es_src_003_from_memory():
    text = CLEAN.replace("The setting conveys neglect.", "Quoting from memory, the setting conveys neglect.")
    found = [f for f in structural_checks(parse(text)) if f.code == "ES-SRC-003"]
    assert len(found) == 1 and found[0].severity == "warning" and found[0].claim_ids == ["p1-point"]


def test_es_src_004_quotations_with_no_supplied_text():
    found = [f for f in structural_checks(parse(CLEAN, texts=[])) if f.code == "ES-SRC-004"]
    assert len(found) == 1 and found[0].severity == "warning" and sorted(found[0].claim_ids) == ["p1-q01", "p1-q02"]
    assert "ES-SRC-001" not in codes(structural_checks(parse(CLEAN, texts=[])))


def test_es_src_005_joined_quotation_is_a_warning_not_an_error():
    text = CLEAN.replace('The lamp "stays unlit" in the hall', 'She notes that "The lamp stays unlit, the clock ticks on" in the hall')
    findings = structural_checks(parse(text))
    assert codes(findings) == ["ES-SRC-005"]
    [f] = findings
    assert f.severity == "warning" and f.claim_ids == ["p1-q01"] and "joins separate spans" in f.message
    assert f.rule_source == RULE_SOURCES["ES-SRC-005"]


def test_es_str_001_fewer_than_two_substantive_quotations():
    text = CLEAN.replace('"ticks on"', "ticks on")  # one multi-word quotation left
    found = [f for f in structural_checks(parse(text)) if f.code == "ES-STR-001"]
    assert len(found) == 1 and found[0].severity == "warning" and found[0].claim_ids == ["p1-point"]
    assert found[0].rule_source == "english_specialist/paragraphs.md P7 (working rule, not an official IB rule)"
    # single-word re-quotations do not count as strands
    text2 = text.replace("marks an absence", 'marks an "absence"')
    assert "ES-STR-001" in codes(structural_checks(parse(text2)))


def test_es_str_001_only_for_body_paragraphs():
    essay = "A thesis with no quotations at all. It previews the method.\n\n" + CLEAN + "\n\nUltimately, neglect is the condition. Nothing changes."
    assert "ES-STR-001" not in codes(structural_checks(parse(essay)))


def test_es_str_002_paragraph_length_outside_the_band():
    short = " ".join(CLEAN_SENTENCES)
    found = [f for f in structural_checks(parse(short)) if f.code == "ES-STR-002"]
    assert len(found) == 1 and found[0].severity == "info" and f"{len(short.split())} words" in found[0].message
    long_text = CLEAN + " " + " ".join([_FILLER] * 12)
    assert len(long_text.split()) > 450
    assert "ES-STR-002" in codes(structural_checks(parse(long_text)))


def test_es_sty_001_first_person_outside_quotations_only():
    text = CLEAN.replace("The setting conveys neglect.", "I think the setting conveys neglect, as we see.")
    found = [f for f in structural_checks(parse(text)) if f.code == "ES-STY-001"]
    assert len(found) == 1 and found[0].severity == "info" and "I" in found[0].message and "we" in found[0].message
    quoted = CLEAN.replace('"ticks on"', '"ticks on" with the pronoun "we"')
    assert "ES-STY-001" not in codes(structural_checks(parse(quoted)))


def test_es_sty_002_mixed_spelling_varieties():
    mixed = CLEAN.replace("marks an absence", "marks an absence the reader must analyse and recognize")  # -yse counts as -ise
    found = [f for f in structural_checks(parse(mixed)) if f.code == "ES-STY-002"]
    assert len(found) == 1 and found[0].severity == "info" and "analyse" in found[0].message and "recognize" in found[0].message
    one_variety = CLEAN.replace("marks an absence", "marks an absence the reader must recognize and emphasize")
    assert "ES-STY-002" not in codes(structural_checks(parse(one_variety)))
    false_friends = CLEAN.replace("marks an absence", "marks a surprise the reader must recognize, otherwise the size and the premise are lost")
    assert "ES-STY-002" not in codes(structural_checks(parse(false_friends)))


def test_es_sty_003_sentence_that_is_only_a_quotation():
    text = CLEAN.replace('The clock "ticks on" while nothing else moves, so time passes without being attended to.', '"The clock ticks on." Time passes without being attended to.')
    found = [f for f in structural_checks(parse(text)) if f.code == "ES-STY-003"]
    assert len(found) == 1 and found[0].severity == "warning" and found[0].claim_ids == ["p1-q02"]


def test_structural_checks_accept_pre_segmented_paragraphs():
    from epinoic_logic.adapters.english_specialist.parser import segment

    report = parse(CLEAN)
    assert structural_checks(report, segment(report.original_response)) == structural_checks(report)


def test_structural_checks_work_on_reports_not_made_by_this_parser():
    """Findings attribute to claims by text; a generic report with no sentence claims still gets paragraph findings."""
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

    text = "I believe the lamp is unlit. Nothing else."
    claim = ClaimRecord(request_id="r", task_id="t", report_id="p", agent_id="generic-structured", subject="English A: Literature",
                        task_type="essay", claim_id="c1", claim_text="The lamp is unlit.", claim_role="point")
    report = SpecialistReport(request_id="r", task_id="t", report_id="p", agent_id="generic-structured", subject="English A: Literature",
                              task_type="essay", original_response=text, response_sha256=sha256_text(text), claims=[claim], created_at="2026-10-11T00:00:00Z")
    found = {f.code: f for f in structural_checks(report)}
    assert set(found) == {"ES-STR-001", "ES-STR-002", "ES-STY-001"}
    assert found["ES-STY-001"].claim_ids == [] and found["ES-STR-001"].claim_ids == []


# ------------------------------------------------------------ source helpers


def test_strip_trailing_punctuation():
    assert strip_trailing_punctuation(' legitimate defense, ') == "legitimate defense"
    assert strip_trailing_punctuation("innocent.") == "innocent"
    assert strip_trailing_punctuation("...") == ""


@pytest.mark.parametrize(
    "excerpt,document_id,expected",
    [
        ("a measured dose of grey,", DOC_ID, "found"),
        ("“a measured dose of grey”", DOC_ID, "found"),
        ("The lamp stays unlit, the clock ticks on", DOC_ID, "found_joined"),
        ("a careful dose of grey", DOC_ID, "not_found"),
        ("a measured dose of grey", "missing", "no_document"),
        ("   ,.", DOC_ID, "empty"),
    ],
)
def test_check_excerpt_statuses(excerpt, document_id, expected):
    docs = {DOC_ID: supplied()}
    check = check_excerpt(excerpt, document_id, docs)
    assert check.status == expected and check.ok is (expected == "found")


def test_check_excerpt_with_no_texts():
    assert check_excerpt("anything", DOC_ID, {}).status == "no_texts"


def test_joined_fragments_require_two_multiword_fragments_in_order():
    docs = {DOC_ID: supplied()}
    assert check_excerpt("the clock ticks on, The lamp stays unlit", DOC_ID, docs).status == "not_found"  # wrong order
    assert check_excerpt("The lamp stays unlit, grey", DOC_ID, docs).status == "not_found"  # one-word fragment ignored
