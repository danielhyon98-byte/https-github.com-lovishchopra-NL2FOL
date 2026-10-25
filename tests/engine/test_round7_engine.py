"""Engine verdicts found vacuous by the round-7 overseers: a COUNTEREXAMPLE over no premises (r7 ec-t13 g5.3, displayed to
the router as "the claim does not follow" although nothing it rests on was encoded) is vacuous (E108); a COUNTEREXAMPLE
that only reassigns figures the conclusion compares and no premise states is no verdict (E111) when a source states the
figures (since the external review of 2026-10-12, otherwise the advisory W111 and the COUNTEREXAMPLE stands); an ENTAILED
proof whose premises restate the conclusion from memory (r7 hi-t13 h1.4) is circular (E112). Each no-verdict case is
displayed as INVALID_FORMALIZATION. A Bool point that no premise links to stays the non sequitur COUNTEREXAMPLE."""
from __future__ import annotations

import json
from pathlib import Path

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import circular_premises, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem

TR = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_translations.json").read_text())
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def fixture(task: str, cid: str) -> Problem:
    return Problem.model_validate(TR[task]["claims"][cid]["problem"])


def V(n):
    return {"op": "var", "name": n}


def codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def test_a_counterexample_over_no_premises_is_vacuous():
    p = fixture("ec-t13", "g5.3")
    assert p.premises == []
    r = verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E108"] and "no premises" in r.diagnostics[0].message


def _figures_problem(figure_grounding=None) -> Problem:
    g = {} if figure_grounding is None else {"grounding": figure_grounding}
    return Problem.model_validate({"problem_id": "f", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "rising", "sort": "Bool"}, {"name": "v22", "sort": "Real", **g}, {"name": "v25", "sort": "Real", **g}],
                                   "premises": [{"id": "P", "expr": V("rising"), "grounding": {"kind": "supplied_text"}}],
                                   "conclusion": {"id": "C", "expr": {"op": "gt", "left": V("v25"), "right": V("v22")}}})


def test_a_counterexample_on_figures_no_premise_states_is_an_unencoded_reason():
    """Rewritten for the external review of 2026-10-12 (E110/E111 withheld valid counterexamples). The figures v22 and v25
    are compared by the conclusion and constrained by no premise. With source-linked evidence that a source states them
    (their groundings verified by a check in this process) the counterexample is no verdict: E111, as this test asserted
    before. Without it, the same underdetermination is the advisory W111 and the COUNTEREXAMPLE stands: formula shape
    alone cannot establish that the source supplied the missing figures."""
    stated = {"kind": "supplied_text", "verified": True, "source_refs": [{"document_id": "table", "excerpt": "2022: 4.1; 2025: 3.8"}]}
    r = verify(_figures_problem(stated), CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E111"] and "v22" in r.diagnostics[0].message
    advisory = verify(_figures_problem(), CFG)
    assert advisory.status is S.COUNTEREXAMPLE and codes(advisory) == ["W111"] and "v22" in advisory.diagnostics[0].message
    assert advisory.counterexample is not None


def test_a_bool_point_no_premise_links_to_stays_the_non_sequitur_verdict():
    p = Problem.model_validate({"problem_id": "n", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": "e1", "sort": "Bool"}, {"name": "point", "sort": "Bool"}],
                                "premises": [{"id": "E", "expr": V("e1"), "grounding": {"kind": "supplied_text"}}],
                                "conclusion": {"id": "C", "expr": V("point")}})
    r = verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == []


def test_a_proof_from_premises_that_restate_the_conclusion_from_memory_is_circular():
    p = fixture("hi-t13", "h1.4")
    r = verify(p, CFG)
    assert r.status is S.ENTAILED and codes(r) == ["E112"]
    assert set(circular_premises(p)) == set(r.premises_relied_on)


def _ph_t13_task():
    from epinoic_logic.translate.contracts import TaskRecord
    material = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text())
    return TaskRecord.of("ph-t13", "req-ph-t13", material["specialists"]["ph-t13"]["question"])


def test_a_restated_task_setting_the_task_record_validates_is_a_transcription_not_a_circle():
    """Rewritten to the stricter rule of policy 2026.10-v5 (issue 1: only a check in this process confers authority), test
    (i). The premise mk1 ('part (a) carries 2 marks, as printed in the question') restates the conclusion. Checked
    against the task record as the router issued it (the question states "[2]"), it is verified: a transcription of the
    task, so there is no E112."""
    from epinoic_logic.translate.grounding import check_problem_grounding

    grounded, _checks = check_problem_grounding(fixture("ph-t13", "g1.1"), [], task=_ph_t13_task())
    assert grounded.premises[0].grounding.verified is True
    r = verify(grounded, CFG)
    assert r.status is S.ENTAILED and codes(r) == []


def test_a_restated_task_setting_with_only_its_label_is_a_circle():
    """Rewritten to the stricter rule of policy 2026.10-v5 (issue 1), test (ii). The same problem label-only (no check
    verified mk1: verified None) restates its conclusion with nothing but its own premise behind it, so it is circular
    (E112). Before, the task_setting label alone made it a 'transcription' and p proves p cleared."""
    p = fixture("ph-t13", "g1.1")
    assert p.premises[0].grounding.verified is None
    r = verify(p, CFG)
    assert r.status is S.ENTAILED and codes(r) == ["E112"] and "mk1" in r.diagnostics[0].message
