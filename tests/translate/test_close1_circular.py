"""Close round 1, arena r7 lit-t13: a report's heading that restates the task question ("Task: Paper 1, SL: How does the
writer present ...?"), encoded as the task's statement restating itself, was refused as circular (E112) and named
ARG-CIRC-001 at warning: "the point is assumed, not derived". The claim offers no argument, so no circle is shown in it:
when every restating premise claims the task's authority (task_setting, rubric_rule), the claim gives no reason, and the
encoding grounds its point on the task too (or the claim only restates the task: a question, or the task's own words), the
refusal is an info record, as it already was for a bare fact restated from subject knowledge. A claim that gives a reason
for a point its premise only restates, and a point of the writer's own restated under the task's label (pinned in
tests/translate/test_argument_rules.py), stay a circle at warning. The status is unchanged (the refusal stands) and none
is releasable. Wording of this round's own."""
from __future__ import annotations

import json

from epinoic_logic.engine import SolverConfig
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, TaskRecord, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"close1-circular-test-key-0123456789abcdef"
IDS = dict(request_id="r", task_id="t", report_id="rep", agent_id="english-specialist", subject="English A: Literature",
           task_type="marking_feedback")
TASK = TaskRecord.of("t", "r", "My teacher set the guiding question 'How does the poet present the storm?'. Please mark my paragraph.")


def _outcome(claim_text: str, kind: str = "task_setting", task: "TaskRecord | None" = TASK, point_on_task: bool = True):
    # a point with a supporting line, as a report's heading has (so the claim is eligible for translation)
    sup = ClaimRecord(**IDS, claim_id="s1", claim_text="What the task wants: a close analysis of how the poet presents the storm.",
                      claim_role="evidence")
    claim = ClaimRecord(**IDS, claim_id="c", claim_text=claim_text, claim_role="point", supporting_claim_ids=["s1"])
    body = claim_text + "\n" + sup.claim_text
    report = SpecialistReport(**IDS, original_response=body, response_sha256=sha256_text(body), claims=[claim, sup], supplied_texts=[],
                              created_at="2026-10-24T00:00:00Z")
    meaning = "the task asks how the poet presents the storm"
    grounding = {"kind": kind, "source_refs": [], "certainty": "established"}
    point = {"grounding": grounding} if point_on_task else {}
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
               "symbols": [{"name": "q", "sort": "Bool", "meaning": meaning, **point}],
               "premises": [{"id": "A_q", "expr": {"op": "var", "name": "q"}, "label": claim_text, "grounding": grounding, "materiality": "material"}],
               "conclusion": {"id": "C_q", "expr": {"op": "var", "name": "q"}, "label": claim_text, **point, "materiality": "material"}}
    out = {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
           "unsupported_reason": None}
    translator = Translator(FixtureTranslationProvider({"c": json.dumps(out)}), config=CFG)
    return verify_claim(claim, report, translator, config=CFG, signing_key=KEY, key_id="k", task=task)


def _circ(o) -> list:
    return [d for d in (o.named_diagnostics or []) if d.code == "ARG-CIRC-001"]


def test_a_heading_that_restates_the_task_is_an_info_record_not_a_circle():
    o = _outcome("Task: How does the poet present the storm?")
    assert o.display_status.value == "INVALID_FORMALIZATION"          # the refusal stands
    [d] = _circ(o)
    assert d.severity == "info" and d.capped_from is None
    assert "the claim offers no reason" in d.message
    assert not o.release.permitted


def test_control_a_reason_given_for_a_point_its_task_premise_only_restates_is_still_a_circle():
    o = _outcome("The task asks how the poet presents the storm, because the task asks how the poet presents the storm.")
    assert o.display_status.value == "INVALID_FORMALIZATION"
    [d] = _circ(o)
    assert d.severity == "warning" and d.defect == "circular_reasoning"
    assert not o.release.permitted


def test_control_a_point_of_the_writers_own_restated_under_the_tasks_label_is_still_a_circle():
    # the point is the writer's (the encoding grounds it on nothing) and the task does not hold its words: a circle at warning
    o = _outcome("The storm stands for the speaker's grief.", point_on_task=False)
    [d] = _circ(o)
    assert d.severity == "warning"


def test_control_a_writers_own_restatement_with_no_reason_is_still_a_circle():
    o = _outcome("The task asks how the poet presents the storm.", kind="specialist_inference")
    [d] = _circ(o)
    assert d.severity == "warning"
