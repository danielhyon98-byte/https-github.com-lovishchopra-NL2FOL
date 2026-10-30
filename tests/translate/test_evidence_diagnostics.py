"""The claim rules of the evidence family (``translate.diag_evidence.RULES``, argdiag-1): each names its defect on its
development case, and the clean controls carry no evidence warning in any mode. Every diagnostic only adds: it leaves the
display status, the dependency lists and the grounding checks as they were, and can only make a result less releasable."""
from __future__ import annotations

import copy

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.diag_evidence import (
    REPORT_RULES, RULES, SOURCE_BOUND_CUES, evd_cherry_001, source_bound, supplies_data_texts,
)
from epinoic_logic.translate.contracts import SuppliedText

from .. import argdiag_cases as C
from ..evidence_support import assert_message_hygiene, blocking, deliver, diagnostics, outcome

MODES = ("report", "text")


def _named(case_id: str, code: str, delivery: str = "report"):
    _case, rc = deliver(case_id, delivery)
    found = diagnostics(rc, code)
    assert found, (case_id, delivery, sorted({d.code for d in diagnostics(rc)}))
    assert_message_hygiene(found)
    return rc, found


# ------------------------------------------------------------------------------------------------------- positives

def test_e01_a_load_bearing_fact_with_no_source_is_lack_of_evidence():
    rc, [d] = _named("e01_lack_of_evidence", "EVD-LACK-001")
    assert d.defect == "lack_of_evidence" and d.severity == "warning" and d.assertion_ids == ["P_borrow"]
    assert outcome(rc, "e3").display_status is S.ENTAILED   # the diagnosis never changes the display
    assert "P_borrow" in outcome(rc, "e3").verification.ungrounded_dependencies


@pytest.mark.parametrize("delivery", MODES)
def test_e02_a_figure_no_supplied_text_states_is_an_invented_figure(delivery):
    _rc, found = _named("e02_invented_figure", "EVD-FIG-001", delivery)
    [d] = found
    assert d.defect == "invented_figure" and d.severity == "warning" and d.assertion_ids == ["P_growth"] and "4.8" in d.message


@pytest.mark.parametrize("case_id, premise", [("e05a_appeal_to_authority_anonymous", "P_auth"), ("e07_data_claim_no_data", "P_share")])
def test_an_unattributed_authority_or_data_cue_is_an_uncheckable_authority(case_id, premise):
    _rc, [d] = _named(case_id, "EVD-AUTH-001")
    assert d.defect == "uncheckable_authority" and d.severity == "warning" and premise in d.assertion_ids


@pytest.mark.parametrize("case_id", ["e06a_cherry_picked_trend", "e06b_cherry_picked_trend_table_encoding"])
@pytest.mark.parametrize("delivery", MODES)
def test_a_period_trend_drawn_from_inner_years_is_cherry_picked_data(case_id, delivery):
    _rc, [d] = _named(case_id, "EVD-CHERRY-001", delivery)
    assert d.defect == "cherry_picked_data" and d.severity == "warning"
    assert "5 for 2019" in d.message and "9 for 2023" in d.message and "rose" in d.message   # the omitted end values are named


@pytest.mark.parametrize("case_id", ["e03_altered_quotation", "e04b_source_mismatch_misattributed"])
def test_a_point_entailed_through_a_refuted_grounding_is_a_source_mismatch(case_id):
    _rc, found = _named(case_id, "EVD-SRC-003")
    assert all(d.defect == "source_mismatch" and d.severity == "warning" for d in found)


# ------------------------------------------------------------------------------------------------------- controls

# Ported onto the integrated translator: c01 and c01b are left out (not ported): their year-led table entries ("2022: 6.4%.
# 2023: 3.9%.") are refuted by this tree's year-of-figure grounding rule (docs/ARGUMENT_DIAGNOSTICS.md, section 20, defect P-1),
# so EVD-SRC-003 names their premises on this tree.
CONTROLS = ["c02_control_history_quotes", "c03_control_psych_study",
            "c04_control_english_quote", "i00_control_valid_rule", "i02c_control_rct_cause", "s04c_control_rounding"]


@pytest.mark.parametrize("case_id", CONTROLS)
def test_the_clean_controls_carry_no_evidence_warning_in_any_mode(case_id):
    case = C.load_case(case_id)
    for mode in case["modes"]:
        _case, rc = deliver(case, mode["delivery"])
        evd = diagnostics(rc, prefix="EVD-")
        assert blocking(evd) == [], (case_id, mode["name"], [(d.code, d.severity, d.message[:120]) for d in evd])


def _revenue_case(answer_claim: str) -> dict:
    """A constructed Business data response: the extract states 120 units, $8 each and the $900 target; the claim gives the
    revenue either as its written calculation over those figures or as a bare figure."""
    case = copy.deepcopy(C.load_case("e02_invented_figure"))
    case["id"] = "calculated-figure"
    case["request"] = "Using the extract, explain whether the firm met its revenue target. [2 marks]"
    case["supplied_texts"] = [{"document_id": "extract-1", "title": "Extract",
                               "text": "Extract: The firm sold 120 units at $8 each in May and had set a revenue target of $900."}]
    case["answer"] = f"The firm sold 120 units at $8 each. {answer_claim}"
    case["report_claims"] = [
        {"claim_id": "k1", "text": "The firm sold 120 units at $8 each.", "role": "evidence", "kind": "arithmetic",
         "source_refs": [{"document_id": "extract-1", "excerpt": "sold 120 units at $8 each"}]},
        {"claim_id": "k2", "text": answer_claim, "role": "point", "kind": "arithmetic", "supporting": ["k1"]}]
    case["translations"] = [{"claim_id": "k2", "proposal": {
        "problem": {"ir_version": "1.0", "problem_id": "p-revenue", "request_id": "r", "claim_id": "k2", "query": "entailment",
                    "symbols": [{"name": "revenue", "sort": "Real", "meaning": "the firm's revenue in May ($)"},
                                {"name": "target", "sort": "Real", "meaning": "the firm's revenue target ($)"}],
                    "premises": [{"id": "P_rev", "expr": {"op": "eq", "left": {"op": "var", "name": "revenue"}, "right": {"op": "real", "value": "960"}},
                                  "label": "revenue was $960", "grounding": {"kind": "specialist_inference", "certainty": "established"}},
                                 {"id": "P_target", "expr": {"op": "eq", "left": {"op": "var", "name": "target"}, "right": {"op": "real", "value": "900"}},
                                  "label": "the target was $900",
                                  "grounding": {"kind": "quotation", "certainty": "established",
                                                "source_refs": [{"document_id": "extract-1", "excerpt": "a revenue target of $900"}]}}],
                    "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "revenue"}, "right": {"op": "var", "name": "target"}},
                                   "label": "revenue exceeded the target"}},
        "interpretation": {"reading": "revenue as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}}]
    return case


def test_a_figure_the_answer_calculates_from_the_extracts_figures_is_no_invented_figure():
    _case, rc = deliver(_revenue_case("Its revenue was 120 × $8 = $960, so it exceeded the target."), "report")
    assert outcome(rc, "k2").display_status is S.ENTAILED
    assert diagnostics(rc, "EVD-FIG-001") == []


def test_the_same_figure_stated_bare_is_named_an_invented_figure():
    _case, rc = deliver(_revenue_case("Its revenue was $960, so it exceeded the target."), "report")
    [d] = diagnostics(rc, "EVD-FIG-001")
    assert d.assertion_ids == ["P_rev"] and d.severity == "warning"


def test_a_calculation_over_an_unstated_operand_still_introduces_its_result():
    case = _revenue_case("Its revenue was 130 × $8 = $1,040, so it exceeded the target.")
    case["translations"][0]["proposal"]["problem"]["premises"][0]["expr"]["right"]["value"] = "1040"
    _case, rc = deliver(case, "report")
    [d] = diagnostics(rc, "EVD-FIG-001")
    assert d.assertion_ids == ["P_rev"] and "1040" in d.message     # 130 units occur in no record, so $1,040 is the answer's own


# ------------------------------------------------------------------------------------------------------- the readings

@pytest.mark.parametrize("request_text", [
    "Using the extract, explain how the rise affected spending. [4 marks]", "Using Table 2, describe the trend.", "Using Source A and your own knowledge, explain.",
    "With reference to Source B, assess the claim.", "According to the text, why did prices rise?", "What does Source A suggest about the treaty?",
    "What does the extract reveal about the speaker?", "How does the poet present the sea in this extract?", "Refer to the data and explain.",
    "Explain, from the table, what happened to output."])
def test_a_request_naming_supplied_material_is_source_bound(request_text):
    assert source_bound(request_text)


@pytest.mark.parametrize("request_text", [
    "Explain why E. coli is classified as a prokaryote.", "A box rests on a table and the forces on it are balanced. Explain whether it accelerates.",
    "Evaluate the claim that raising the minimum wage increases unemployment.", "Explain what economists refer to as a supply shock.", "", None])
def test_a_request_with_no_named_material_is_not_source_bound(request_text):
    assert not source_bound(request_text)


def test_the_cue_tables_and_rule_order_are_pinned():
    assert len(SOURCE_BOUND_CUES) == len(set(SOURCE_BOUND_CUES)) and "using the extract" in SOURCE_BOUND_CUES
    # repair round 1: EVD-SRC-005 (a task-authority label the task material refutes) runs after EVD-SRC-003, before EVD-SRC-001
    assert [r.__name__ for r in RULES] == ["evd_src_003", "evd_src_005", "evd_src_001", "evd_auth_001", "evd_fig_001", "evd_cherry_001", "evd_lack_001",
                                           "evd_src_004"]
    # repair round 2: EVD-SRC-006 (a paraphrase crediting a document with the opposite stance) runs first
    assert [r.__name__ for r in REPORT_RULES] == ["evd_src_006", "evd_src_002", "evd_lack_002"]


def test_a_data_text_is_a_table_or_a_text_with_figures():
    class R:
        def __init__(self, texts):
            self.supplied_texts = texts
    table = SuppliedText(document_id="table-2", title="Table 2", author=None, text="Unemployment rate (%).")
    figures = SuppliedText(document_id="extract-1", title="Extract", author=None, text="Output grew by 2.5% and prices by 3.1% in 2023.")
    prose = SuppliedText(document_id="poem", title="The Sea", author="A Poet", text="The grey sea and the long black land, 1850.")
    assert supplies_data_texts(R([table])) and supplies_data_texts(R([figures])) and not supplies_data_texts(R([prose])) and not supplies_data_texts(R([]))


def test_cherry_picking_needs_a_decided_result():
    class Ctx:
        verification = None
    assert evd_cherry_001(Ctx()) == ()
