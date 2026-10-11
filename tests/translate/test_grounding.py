"""Deterministic quotation grounding: verbatim, normalized, elided, miss, wrong document."""
from __future__ import annotations

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.grounding import check_claim_sources, check_problem_grounding, find_quotation, locate_quotation

from .conftest import DOC_ID, TEXT, chain_problem, make_claim

DOCS = [SuppliedText(document_id=DOC_ID, text=TEXT, locator_scheme="none")]


def test_verbatim_match_offsets_refer_to_original_text():
    m = locate_quotation("The lamp stays unlit", TEXT)
    assert m is not None and m.method == "verbatim_match" and not m.elided
    assert TEXT[m.start:m.end] == "The lamp stays unlit"
    assert find_quotation("the clock ticks on", TEXT) == (TEXT.index("the clock ticks on"), TEXT.index("the clock ticks on") + len("the clock ticks on"), "the clock ticks on")


def test_normalized_match_curly_quotes_and_whitespace():
    outer = locate_quotation("“a measured dose of grey”", TEXT)  # outer quotation marks are stripped first
    assert outer is not None and outer.method == "verbatim_match" and TEXT[outer.start:outer.end] == "a measured dose of grey"
    curly = locate_quotation("yard is “a measured dose of grey” and", TEXT)  # internal curly quotes vs straight in the text
    assert curly is not None and curly.method == "normalized_match"
    assert TEXT[curly.start:curly.end] == 'yard is "a measured dose of grey" and'
    spaced = locate_quotation("lamp   stays\n unlit", TEXT)
    assert spaced is not None and spaced.method == "normalized_match" and TEXT[spaced.start:spaced.end] == "lamp stays unlit"


def test_case_change_is_a_miss():
    assert locate_quotation("The Lamp stays unlit", TEXT) is None
    assert locate_quotation("the lamp stays lit", TEXT) is None


def test_elided_quotation_matches_fragments_in_order():
    m = locate_quotation("The lamp ... ticks on", TEXT)
    assert m is not None and m.elided and m.method == "normalized_match"
    assert TEXT[m.start:m.end].startswith("The lamp") and TEXT[m.start:m.end].endswith("ticks on")
    assert locate_quotation("ticks on ... The lamp", TEXT) is None  # wrong order


def test_problem_grounding_sets_verified_only_by_code():
    data = chain_problem()
    data["premises"][1]["grounding"] = {"kind": "specialist_inference", "certainty": "probable", "verified": True}  # model lied
    problem = Problem.model_validate(data)
    checked, checks = check_problem_grounding(problem, DOCS)
    by_target = {(c.target_id, c.kind): c for c in checks}
    assert by_target[("E1", "quotation")].verified is True and by_target[("E1", "quotation")].method == "verbatim_match"
    assert by_target[("q", "quotation")].verified is True
    assert by_target[("L1", "specialist_inference")].method == "not_checkable" and by_target[("L1", "specialist_inference")].verified is None
    assert checked.premises[0].grounding.verified is True
    assert checked.premises[1].grounding.verified is None  # the model's True was discarded
    assert problem.premises[1].grounding.verified is True  # input untouched


def test_missing_excerpt_is_unverified():
    problem = Problem.model_validate(chain_problem(excerpt="The lamp burns brightly"))
    checked, checks = check_problem_grounding(problem, DOCS)
    failed = [c for c in checks if c.verified is False]
    assert {c.target_id for c in failed} == {"q", "E1"}
    assert all("not found" in (c.detail or "") for c in failed)
    assert checked.premises[0].grounding.verified is False


def test_wrong_document_is_unverified():
    problem = Problem.model_validate(chain_problem(document_id="doc-999"))
    _, checks = check_problem_grounding(problem, DOCS)
    failed = [c for c in checks if c.verified is False]
    assert failed and all("not among the supplied texts" in (c.detail or "") for c in failed)
    assert {c.document_id for c in failed} == {"doc-999"}


def test_claim_source_refs_checked_against_texts():
    claim = make_claim(
        "c-ev", '"The lamp stays unlit"', "evidence",
        source_refs=[
            {"document_id": DOC_ID, "excerpt": "The lamp stays unlit"},
            {"document_id": DOC_ID, "locator": "l. 12"},
            {"document_id": "doc-x"},
        ],
    )
    checks = check_claim_sources(claim, DOCS)
    assert [c.verified for c in checks] == [True, False, False]
    assert "no locator scheme" in checks[1].detail and "not among the supplied texts" in checks[2].detail
