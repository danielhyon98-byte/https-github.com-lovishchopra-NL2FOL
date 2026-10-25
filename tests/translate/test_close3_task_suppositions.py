"""Close round 3, DV2-04: a task that tells the student to adopt a supposition ("Assume that X.", "Suppose X.", "Imagine
that X.") made a correct answer that takes X as given raise EVD-SRC-001 (unchecked_source) and INT-ARG-001 at warning: the
task-fact reader leaves a supposition unvalidated (it states X only as the answer's scenario), and EVD-SRC-001 read that as
a premise resting on a label alone. The committed base names nothing on the same input. EVD-SRC-001, a reading no close
round had narrowed, is narrowed by a plain restriction: a task-authority premise that restates a supposition the task sets
(one sentence that opens with a supposition holds every content root of the premise, with its polarity) is not named. Its
grounding record is unchanged (the authority stays unvalidated, so the answer is still not releasable on it, as on the
base). A hedged, conditional or reported task sentence, and a supposition of something else than the premise, still make
the premise unchecked_source.

Each positive case was checked to fail on the tree before the round; the wording is this round's own; nothing from a case
is executed."""
from __future__ import annotations

import pytest

from ..evidence_support import deliver, diagnostics

EXTRACT = "When a city adds bus lanes, journey times on its buses fall."
FACT = "the city of Harlow will add bus lanes next spring"
POINT = "journey times on Harlow's buses will fall next spring"
ASK = " Using the extract, explain the effect on bus journeys. [3 marks]"


def _case(case_id: str, request: str, *, fact: str = FACT, subject: str = "Geography", task_type: str = "data_response") -> dict:
    answer = (f"{fact[0].upper() + fact[1:]}, and the extract says \"When a city adds bus lanes, journey times on its buses fall\", "
              f"so {POINT}.")
    g = lambda kind, refs=(): {"kind": kind, "source_refs": [{"document_id": "ext", "excerpt": e} for e in refs], "certainty": "established"}
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "x", "claim_id": "x", "query": "entailment",
               "symbols": [{"name": "a", "sort": "Bool", "meaning": fact, "grounding": g("task_setting")},
                           {"name": "b", "sort": "Bool", "meaning": POINT, "grounding": g("specialist_inference")}],
               "premises": [{"id": "t1", "expr": {"op": "var", "name": "a"}, "label": fact, "materiality": "material", "grounding": g("task_setting")},
                            {"id": "q1", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}},
                             "label": "when a city adds bus lanes, journey times on its buses fall", "materiality": "material",
                             "grounding": g("quotation", [EXTRACT[:-1]])}],
               "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}, "label": POINT, "materiality": "material", "grounding": g("specialist_inference")}}
    agent = {"Geography": "geography-specialist", "Economics": "economics-specialist", "History": "history-specialist"}[subject]
    return {"case_format": "argdiag-corpus/1", "id": case_id, "family": "evidence", "expected_label": "none", "acceptable_labels": [],
            "title": case_id, "subject": subject, "task_type": task_type, "agent_id": agent, "request": request, "answer": answer,
            "supplied_texts": [{"document_id": "ext", "title": "Extract", "text": EXTRACT}],
            "ids": {"task_id": f"task-{case_id}", "request_id": f"req-{case_id}", "report_id": "rep-1", "plan_id": f"plan-{case_id}"},
            "modes": [{"name": "text", "delivery": "text", "synthesis": "none"}], "report_claims": [],
            "translations": [{"contains": f"so {POINT}", "proposal": {"problem": problem,
                              "interpretation": {"reading": "probe", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
                              "unsupported_reason": None}}],
            "fidelity_review": "faithful"}


def _named(rc, code: str) -> list:
    return [d for d in diagnostics(rc, code) if d.severity in ("warning", "error")]


def _unchecked(rc) -> list:
    """The unchecked_source diagnostics shown at warning or error (EVD-SRC-001, or EVD-SRC-005 when the task material holds
    none of the premise's words: a reported view's words are no statement of the task's)."""
    return [d for d in diagnostics(rc, prefix="EVD-SRC-") if d.defect == "unchecked_source" and d.severity in ("warning", "error")]


def _int_arg(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-ARG-001"]


@pytest.mark.parametrize("request_text", [
    "Assume that the city of Harlow will add bus lanes next spring." + ASK,
    "Suppose the city of Harlow will add bus lanes next spring." + ASK,
    "Imagine that the city of Harlow will add bus lanes next spring." + ASK,
    "Assuming that the city of Harlow will add bus lanes next spring, answer the question." + ASK,
])
def test_correct_work_that_takes_the_tasks_supposition_as_given_is_not_named_unchecked_source(request_text):
    _case_, rc = deliver(_case("close3-supposed", request_text), "text")
    assert not _unchecked(rc) and not _int_arg(rc), [(d.code, d.severity) for d in diagnostics(rc)]
    [o] = [o for o in rc.outcomes if o.translation.problem is not None]
    # the grounding record is unchanged: the supposition is not validated as a task fact, so release stays refused, as on the base
    assert not o.release.permitted
    assert [c.verified for c in o.translation.grounding_checks if c.target_id == "t1"] == [None]


def test_the_same_holds_in_another_subject_and_task_type():
    request = "Suppose the city of Harlow will add bus lanes next spring." + ASK
    _case_, rc = deliver(_case("close3-supposed-econ", request, subject="Economics", task_type="source_analysis"), "text")
    assert not _unchecked(rc) and not _int_arg(rc)


@pytest.mark.parametrize("request_text", [
    "The city of Harlow may add bus lanes next spring." + ASK,                         # a hedge states nothing as given
    "If the city of Harlow adds bus lanes next spring, fares will rise." + ASK,        # a condition sets no scenario for X
    "Commuters believe that the city of Harlow will add bus lanes next spring." + ASK, # a reported view
    "Assume that fares in Harlow will rise next spring." + ASK,                         # a supposition of something else
])
def test_control_a_task_that_does_not_set_the_premise_still_names_it_unchecked_source(request_text):
    _case_, rc = deliver(_case("close3-not-supposed", request_text), "text")
    assert _unchecked(rc), [(d.code, d.severity) for d in diagnostics(rc)]


def test_control_a_supposition_of_the_opposite_polarity_does_not_cover_the_premise():
    request = "Assume that the city of Harlow will not add bus lanes next spring." + ASK
    _case_, rc = deliver(_case("close3-supposed-negated", request), "text")
    assert _unchecked(rc)
