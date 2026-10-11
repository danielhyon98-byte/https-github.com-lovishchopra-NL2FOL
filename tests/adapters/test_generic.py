"""Generic structured adapter: parsing contract and subject-neutral structural checks."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.adapters import GenericStructuredAdapter, get_adapter
from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.translate.contracts import sha256_text

from .conftest import DOC_ID, IDS, TEXT, supplied

RESPONSE = 'The yard is "a measured dose of grey" and the speaker stays silent.'


def document(**overrides):
    doc = {
        "original_response": RESPONSE,
        "claims": [
            {"claim_id": "e1", "claim_text": '"a measured dose of grey"', "claim_role": "evidence",
             "source_refs": [{"document_id": DOC_ID, "excerpt": "a measured dose of grey"}]},
            {"claim_id": "p1", "claim_text": "The setting conveys neglect.", "claim_role": "point", "supporting_claim_ids": ["e1"]},
        ],
    }
    doc.update(overrides)
    return doc


def parse(doc, **kw):
    kwargs = dict(IDS, subject="English A: Literature", task_type="analytical_paragraph", supplied_texts=[supplied()])
    kwargs.update(kw)
    return GenericStructuredAdapter().parse_response(json.dumps(doc), **kwargs)


def test_hash_is_computed_and_fields_are_filled_from_the_caller():
    report = parse(document())
    assert report.response_sha256 == sha256_text(RESPONSE)
    assert (report.request_id, report.task_id, report.report_id) == (IDS["request_id"], IDS["task_id"], IDS["report_id"])
    assert report.agent_id == "generic-structured" and report.subject == "English A: Literature" and report.task_type == "analytical_paragraph"
    assert report.supplied_texts[0].document_id == DOC_ID and report.created_at
    for claim in report.claims:
        assert (claim.request_id, claim.report_id, claim.agent_id, claim.subject) == (IDS["request_id"], IDS["report_id"], "generic-structured", "English A: Literature")


def test_present_hash_must_match():
    assert parse(document(response_sha256=sha256_text(RESPONSE))).response_sha256 == sha256_text(RESPONSE)
    with pytest.raises(AdapterError, match="immutable"):
        parse(document(response_sha256="0" * 64))


def test_wrapper_and_explicit_fields_are_accepted():
    report = parse({"report": document(agent_id="my-specialist", subject="History", course_level="HL", agent_version="2.1")})
    assert report.agent_id == "my-specialist" and report.subject == "History" and report.course_level == "HL" and report.agent_version == "2.1"
    assert report.claims[0].agent_id == "my-specialist" and report.claims[0].subject == "History"


def test_identity_mismatch_is_rejected():
    for field in ("request_id", "task_id", "report_id"):
        with pytest.raises(AdapterError, match=field):
            parse(document(**{field: "someone-else"}))


@pytest.mark.parametrize("text", ["not json", "[1, 2]", '"a string"', json.dumps({"claims": []}), json.dumps({"original_response": ""})])
def test_malformed_documents_are_rejected_without_echoing_them(text):
    with pytest.raises(AdapterError) as info:
        GenericStructuredAdapter().parse_response(text, **IDS, subject="S", task_type="T", supplied_texts=[])
    assert "not json" not in str(info.value) and "a string" not in str(info.value)


def test_contract_violation_names_the_location_only():
    doc = document()
    doc["claims"][0]["claim_role"] = "sonnet"
    with pytest.raises(AdapterError) as info:
        parse(doc)
    assert "claims.0.claim_role" in str(info.value) and "sonnet" not in str(info.value)


def test_document_supplied_texts_take_precedence_when_present():
    doc = document(supplied_texts=[{"document_id": "doc-2", "text": "Another text.", "locator_scheme": "none"}])
    report = parse(doc)
    assert [t.document_id for t in report.supplied_texts] == ["doc-2"]


def test_gen_src_001_for_an_excerpt_not_in_the_text():
    doc = document()
    doc["claims"].append({"claim_id": "e2", "claim_text": '"a careful dose of grey"', "claim_role": "evidence",
                          "source_refs": [{"document_id": DOC_ID, "excerpt": "a careful dose of grey"}]})
    doc["claims"].append({"claim_id": "e3", "claim_text": '"nothing moves"', "claim_role": "evidence",
                          "source_refs": [{"document_id": "ghost-doc", "excerpt": "nothing moves"}]})
    findings = GenericStructuredAdapter().structural_checks(parse(doc))
    src = {f.claim_ids[0]: f for f in findings if f.code == "GEN-SRC-001"}
    assert set(src) == {"e2", "e3"} and all(f.severity == "error" for f in src.values())
    assert "not found" in src["e2"].message and "not among the supplied texts" in src["e3"].message
    assert not [f for f in findings if f.code == "GEN-SRC-001" and "e1" in f.claim_ids]


def test_gen_src_002_for_a_joined_quotation():
    doc = document()
    doc["claims"][0]["source_refs"] = [{"document_id": DOC_ID, "excerpt": "The lamp stays unlit, the clock ticks on"}]
    findings = GenericStructuredAdapter().structural_checks(parse(doc))
    assert [f.code for f in findings] == ["GEN-SRC-002"] and findings[0].severity == "warning"


def test_normalized_quotation_passes():
    doc = document()
    doc["claims"][0]["source_refs"] = [{"document_id": DOC_ID, "excerpt": "“a  measured dose of grey”"}]
    assert GenericStructuredAdapter().structural_checks(parse(doc)) == []


def test_gen_str_001_for_unknown_supporting_and_parent_ids():
    doc = document()
    doc["claims"][1]["supporting_claim_ids"] = ["e1", "ghost"]
    doc["claims"][0]["parent_claim_id"] = "nobody"
    findings = {f.claim_ids[0]: f for f in GenericStructuredAdapter().structural_checks(parse(doc)) if f.code == "GEN-STR-001"}
    assert set(findings) == {"p1", "e1"}
    assert "ghost" in findings["p1"].message and "nobody" in findings["e1"].message and findings["p1"].severity == "error"


def test_gen_dup_001_for_duplicate_claim_text():
    doc = document()
    doc["claims"].append({"claim_id": "p2", "claim_text": "the setting   conveys neglect.", "claim_role": "point"})
    findings = [f for f in GenericStructuredAdapter().structural_checks(parse(doc)) if f.code == "GEN-DUP-001"]
    assert len(findings) == 1 and findings[0].severity == "info" and sorted(findings[0].claim_ids) == ["p1", "p2"]


def test_clean_report_has_no_findings_and_registry_serves_the_same_adapter():
    report = parse(document())
    assert GenericStructuredAdapter().structural_checks(report) == []
    assert get_adapter("generic-structured").structural_checks(report) == []
