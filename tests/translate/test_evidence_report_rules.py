"""The report rules of the evidence family (``translate.diag_evidence.REPORT_RULES``, argdiag-1). They read the delivered
claims and the request once per report, so they name what a claim with no translation (a concluding sentence the generic
parser leaves NOT_ELIGIBLE in text mode) still shows: an attribution to a supplied document the document's words do not
support (EVD-SRC-002) and a change in a quantity no figure and no supplied text supports (EVD-LACK-002). Both are info
only: a paraphrase cannot be checked deterministically, so they say "not checked", never "false"."""
from __future__ import annotations

import pytest

from epinoic_logic.translate.common import utc_now_rfc3339
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TaskRecord, sha256_text
from epinoic_logic.translate.diag_core import report_diagnostics

from .. import argdiag_cases as C
from ..evidence_support import assert_message_hygiene, deliver, diagnostics


def _report_level(rc, code):
    return [d for d in diagnostics(rc, code) if d.layer == "report"]


# ------------------------------------------------------------------------------------------------------- positives

def test_text_mode_e01_names_the_unsupported_change_in_borrowing():
    _case, rc = deliver("e01_lack_of_evidence", "text")
    [d] = _report_level(rc, "EVD-LACK-002")
    assert d.severity == "info" and d.defect == "lack_of_evidence" and "Household borrowing" in d.message and "fell" in d.message
    assert "does not say it is false" in d.message
    assert_message_hygiene([d])


@pytest.mark.parametrize("case_id", ["e04a_source_mismatch_paraphrase", "e08b_self_certified_premise_provider"])
@pytest.mark.parametrize("delivery", ["text", "report"])
def test_an_attribution_the_named_document_does_not_support_is_recorded_as_not_checked(case_id, delivery):
    _case, rc = deliver(case_id, delivery)
    found = _report_level(rc, "EVD-SRC-002")
    assert found and all(d.severity == "info" and d.defect == "unchecked_source" for d in found)
    assert all("source-a" in d.message and "was not checked" in d.message for d in found)
    assert_message_hygiene(found)


# ------------------------------------------------------------------------------------------------------- controls

@pytest.mark.parametrize("delivery", ["text", "report"])
def test_an_attribution_beside_located_quotations_is_exempt(delivery):
    _case, rc = deliver("c02_control_history_quotes", delivery)
    assert _report_level(rc, "EVD-SRC-002") == []


@pytest.mark.parametrize("case_id", ["c01_control_econ_table", "i02c_control_rct_cause"])
@pytest.mark.parametrize("delivery", ["text", "report"])
def test_a_change_stated_with_figures_or_about_the_texts_subject_is_exempt(case_id, delivery):
    _case, rc = deliver(case_id, delivery)
    assert _report_level(rc, "EVD-LACK-002") == []


def _report(claims: list[str], texts: list[SuppliedText]) -> SpecialistReport:
    answer = " ".join(claims)
    records = [ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="psychology-specialist", subject="Psychology", task_type="short_answer",
                           claim_id=f"k{i}", claim_text=text, claim_role="analysis", proposed_claim_kind="unknown", materiality="material")
               for i, text in enumerate(claims)]
    return SpecialistReport(report_id="rep", request_id="r", task_id="t", agent_id="psychology-specialist", subject="Psychology", task_type="short_answer",
                            original_response=answer, response_sha256=sha256_text(answer), supplied_texts=texts, claims=records, created_at=utc_now_rfc3339())


STUDY = SuppliedText(document_id="study-1", title="Study summary", author=None,
                     text="Study summary: participants who heard the verb 'smashed' gave higher speed estimates than those who heard 'hit'.")
TASK = TaskRecord.of("t", "r", "Using the study summary, explain how leading questions may affect eyewitness testimony.")


def test_a_trend_verb_inside_quotation_marks_is_no_stated_change():
    rep = _report(['Answers should avoid "dropped" as a description of the speed estimates.'], [STUDY])
    assert [d.code for d in report_diagnostics(rep, TASK).diagnostics if d.code == "EVD-LACK-002"] == []


def test_the_same_verb_stating_a_change_of_an_unsupported_quantity_is_recorded():
    rep = _report(["Memory accuracy dropped sharply afterwards."], [STUDY])
    [d] = [d for d in report_diagnostics(rep, TASK).diagnostics if d.code == "EVD-LACK-002"]
    assert d.claim_ids == ["k0"] and d.severity == "info"


def test_with_no_supplied_text_the_change_rule_does_not_apply():
    rep = _report(["Memory accuracy dropped sharply afterwards."], [])
    assert [d for d in report_diagnostics(rep, TASK).diagnostics if d.code == "EVD-LACK-002"] == []


def test_an_attribution_whose_content_the_document_holds_is_not_recorded():
    rep = _report(["The study shows that participants who heard 'smashed' gave higher speed estimates."], [STUDY])
    assert [d for d in report_diagnostics(rep, TASK).diagnostics if d.code == "EVD-SRC-002"] == []
    rep = _report(["The study shows that participants remembered broken glass that was never there."], [STUDY])
    [d] = [d for d in report_diagnostics(rep, TASK).diagnostics if d.code == "EVD-SRC-002"]
    assert d.severity == "info" and "study-1" in d.message
