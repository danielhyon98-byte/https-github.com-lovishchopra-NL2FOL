"""The claim and report layers of the argument family (``translate/diag_argument.py``, rules argdiag-1): ARG-EQ-001 (the
translation flagged one word read in two senses), the claim form of ARG-CIRC-001 (the translation refused as circular)
and ARG-BARE-001 (a judgement the request asks to be reasoned stands with no reason in its answer section), each with a
positive case and clean controls."""
from __future__ import annotations

from functools import lru_cache

import pytest

from epinoic_logic.named import is_blocking
from epinoic_logic.translate import diag_argument
from epinoic_logic.translate.contracts import TaskRecord
from epinoic_logic.translate.diag_core import report_diagnostics

from ..argdiag_hub import run_case
from ..contract.helpers import make_report, output, run_claim, speed_problem


@lru_cache(maxsize=None)
def _delivered(case_id: str, mode: str):
    return run_case(case_id, mode)


def _receipt_codes(case_id: str, mode: str, code: str) -> list:
    return [d for d in _delivered(case_id, mode).receipt.named_diagnostics if d.code == code]


# ----------------------------------------------------------------------------------------------- ARG-EQ-001

@pytest.mark.parametrize("mode", ["report", "text"])
def test_i03b_the_flagged_equivocation_is_eq_001_and_is_not_capped(mode):
    [out] = [o for o in _delivered("i03b_equivocation_flagged", mode).outcomes.values() if o.translation.problem is not None]
    [d] = [x for x in out.named_diagnostics if x.code == "ARG-EQ-001"]
    assert (d.severity, d.layer, d.defect, d.capped_from) == ("warning", "claim", "equivocation", None)
    assert "EQUIVOCATION: \"'theory' means a scientific theory in the first premise" in d.message
    assert out.display_status.value == "AMBIGUOUS_TRANSLATION"        # the display is the translation's, unchanged
    assert [f for f in _delivered("i03b_equivocation_flagged", mode).receipt.findings if f.code == "INT-ARG-001" and f.defect == "equivocation"]


@pytest.mark.parametrize("code", ["SENSE_SPLIT", "two-senses", "Equivocation"])
def test_every_equivocation_flag_code_names_eq_001(code):
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem(), flags=[{"code": code, "message": "'speed' read as average and as instantaneous", "alternatives": []}]))
    assert [d.code for d in out.named_diagnostics if d.code == "ARG-EQ-001"] == ["ARG-EQ-001"]


def test_another_ambiguity_flag_code_gives_no_eq_001():
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem(), flags=[{"code": "SCOPE", "message": "two readings of 'all'", "alternatives": []}]))
    assert out.display_status.value == "AMBIGUOUS_TRANSLATION" and not [d for d in out.named_diagnostics if d.code == "ARG-EQ-001"]


# ----------------------------------------------------------------------------------------------- ARG-CIRC-001, claim form

def test_f06_the_refused_circular_translation_names_circ_001_with_the_restating_premise():
    [out] = [o for o in _delivered("f06_circular_direct", "text").outcomes.values()]
    assert out.translation.status.value == "INVALID_FORMALIZATION"
    [d] = [x for x in out.named_diagnostics if x.code == "ARG-CIRC-001"]
    assert (d.layer, d.assertion_ids, d.severity) == ("claim", ["s_restate"], "warning")
    assert "no check in this process established them (whatever their label)" in d.message


def _restating_claim(text: str, kind: str, task=None):
    claim, report = make_report(text, role="point", kind="formal_logic", support=(("s1", "The poem appeared in a radical weekly."),), texts=(),
                                subject="History")
    year = {"op": "eq", "left": {"op": "var", "name": "yr"}, "right": {"op": "int", "value": "1817"}}
    problem = {"ir_version": "1.0", "problem_id": "p-c", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
               "symbols": [{"name": "yr", "sort": "Int", "meaning": "the year the sonnet was written"}],
               "premises": [{"id": "p_yr", "expr": year, "label": "the sonnet was written in 1817", "grounding": {"kind": kind}}],
               "conclusion": {"id": "C", "expr": year, "label": "the sonnet was written in 1817"}}
    return run_claim(claim, report, output(problem), task=task)


def test_a_bare_factual_sentence_refused_as_circular_is_an_info_record_and_no_finding():
    out = _restating_claim("Shelley's sonnet was written in 1817.", "general_knowledge")
    assert out.translation.status.value == "INVALID_FORMALIZATION"
    assert any(": E112: circular: premise(s) p_yr (general_knowledge) restate" in t for t in out.translation.diagnostics)
    [d] = [x for x in out.named_diagnostics if x.code == "ARG-CIRC-001"]
    assert d.severity == "info" and not is_blocking(d)


@pytest.mark.parametrize("text, kind", [("Shelley's sonnet was written in 1817 because it was written in 1817.", "general_knowledge"),
                                        ("Shelley's sonnet was written in 1817.", "specialist_inference"),
                                        ("Shelley's sonnet was written in 1817.", "assumption")])
def test_a_restatement_offered_as_a_reason_or_by_the_writers_step_is_circular(text, kind):
    out = _restating_claim(text, kind)
    [d] = [x for x in out.named_diagnostics if x.code == "ARG-CIRC-001"]
    assert d.severity == "warning"


def test_a_translation_refused_for_another_reason_gives_no_circ_001():
    claim, report = make_report("The speed is 15 km/h.")
    bad = speed_problem()
    bad["conclusion"]["expr"] = {"op": "eq", "left": {"op": "var", "name": "undeclared"}, "right": {"op": "real", "value": "15"}}
    out = run_claim(claim, report, output(bad))
    assert out.translation.status.value == "INVALID_FORMALIZATION" and not [d for d in out.named_diagnostics if d.code == "ARG-CIRC-001"]


# ----------------------------------------------------------------------------------------------- ARG-BARE-001

@pytest.mark.parametrize("case_id, mode", [("i01_bare_assertion", "report"), ("i01_bare_assertion", "text"),
                                           ("i01b_bare_assertion_with_degree", "report"), ("i01b_bare_assertion_with_degree", "text")])
def test_i01_and_i01b_bare_assertion_in_both_modes(case_id, mode):
    run = _delivered(case_id, mode)
    [d] = _receipt_codes(case_id, mode, "ARG-BARE-001")
    assert (d.severity, d.layer, d.defect, d.derivation) == ("warning", "report", "bare_assertion", "claim_structure")
    assert d.claim_ids == [run.report.claims[0].claim_id] and "the request asks for reasons" in d.message
    # it needs no outcome: i01b's only claim is never translated
    if case_id.startswith("i01b"):
        assert not run.outcomes


def test_a_material_bare_assertion_gets_its_receipt_finding():
    findings = [f for f in _delivered("i01b_bare_assertion_with_degree", "report").receipt.findings if f.code == "INT-ARG-001"]
    assert [(f.severity, f.defect) for f in findings] == [("warning", "bare_assertion")]


@pytest.mark.parametrize("case_id, mode", [("i01c_control_reasoned_evaluation", "report"), ("i01c_control_reasoned_evaluation", "text"),
                                           ("c03_true_dichotomy", "text"), ("f06_circular_direct", "text"), ("i00_control_valid_rule", "report"),
                                           ("i00_control_valid_rule", "text"), ("c02_control_history_quotes", "text"), ("c04_quoted_transcription", "text")])
def test_a_reasoned_or_supported_answer_gives_no_bare_assertion(case_id, mode):
    assert _receipt_codes(case_id, mode, "ARG-BARE-001") == []


def test_a_request_that_asks_for_no_reasons_gives_no_bare_assertion():
    run = _delivered("i01_bare_assertion", "report")
    from epinoic_logic.translate.contracts import TaskRecord
    task = TaskRecord.of("t", "r", "State the claim made about the minimum wage.")
    items = [type("Item", (), {"item_id": "i1", "text": "State the claim made about the minimum wage.", "command_term": "state", "level": None})()]
    assert [d for d in report_diagnostics(run.report, task, (), items=items).diagnostics if d.code == "ARG-BARE-001"] == []


def test_a_note_in_a_report_with_no_material_claim_is_no_bare_assertion():
    """When no claim is material, a judgement-like claim counts as the answer's assertion, but a note never does."""
    run = _delivered("i01_bare_assertion", "text")
    note = run.report.claims[0].model_copy(update={"claim_role": "other", "materiality": "supporting"})
    report = run.report.model_copy(update={"claims": [note]})
    items = [type("Item", (), {"item_id": "i1", "text": "Evaluate the claim.", "command_term": "evaluate", "level": None})()]
    assert [d for d in report_diagnostics(report, None, (), items=items).diagnostics if d.code == "ARG-BARE-001"] == []


def test_the_reason_connectives_ignore_quoted_words_and_because_of():
    assert diag_argument.has_reason_connective("Prices rose, so demand fell.")
    assert diag_argument.has_reason_connective("Demand fell because prices rose.")
    assert not diag_argument.has_reason_connective("Demand fell because of the war.")
    assert not diag_argument.has_reason_connective('The poem says "so it goes" and ends.')
    assert diag_argument.has_reason_connective("As Source A shows, the treaty was resented.")


def test_the_rules_are_registered_in_their_layers():
    # repair round 5 (ADV5-15 c) registered one more report rule, ``own_reason_circle`` (ARG-CIRC-003 on a claim no engine
    # result decides); the registration is still pinned exactly, in order
    assert diag_argument.RULES == (diag_argument.equivocation_flag, diag_argument.circular_refusal, diag_argument.unbridged_leap)
    assert diag_argument.REPORT_RULES == (diag_argument.bare_assertion, diag_argument.own_reason_circle)
    for case_id, mode, code in [("i01_bare_assertion", "text", "ARG-BARE-001"), ("i03b_equivocation_flagged", "report", "ARG-EQ-001")]:
        assert [d.layer for d in _delivered(case_id, mode).receipt.named_diagnostics if d.code == code and is_blocking(d)] in (["report"], ["claim"])
