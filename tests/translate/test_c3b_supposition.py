"""Round-10 leftover R10-CORE-MAA-T15-M5.3: c2 maa-t15 m5.3 ("at x = 0, g(0) = 3 and h(3) = 1 = 0 + 1") was encoded with the
premise 'x = 0' on the report-wide x, glossed "the free real variable of the functions g and h", and displayed ENTAILED. The claim
only supposes x = 0; the encoding asserts it as a fact of the report. The fidelity flag ``supposition_as_fact`` names it, so the
outcome is no verdict on the claim (AMBIGUOUS_TRANSLATION)."""
from __future__ import annotations

from epinoic_logic.api.ir import Problem
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.contracts import ClaimRecord
from epinoic_logic.translate.fidelity import supposition_as_fact

from tests.channel.c2_core_support import C2, deliver

IDS = dict(request_id="r", task_id="t", report_id="rep", agent_id="mathematics-aa-specialist", subject="Mathematics: Analysis and Approaches",
           task_type="short_answer")


def _problem(meaning: str, kind: str = "specialist_inference") -> Problem:
    return Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "m5.3", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": meaning}, {"name": "gx", "sort": "Real", "meaning": "g(x) = 2x + 3"}],
        "premises": [{"id": "q5-x0", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0"}},
                      "grounding": {"kind": kind}},
                     {"id": "q2-gx", "expr": {"op": "eq", "left": {"op": "var", "name": "gx"},
                                              "right": {"op": "add", "args": [{"op": "mul", "args": [{"op": "real", "value": "2"}, {"op": "var", "name": "x"}]},
                                                                              {"op": "real", "value": "3"}]}}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "var", "name": "gx"}, "right": {"op": "real", "value": "3"}}}})


def test_the_recorded_m5_3_is_named_and_not_displayed_as_a_verdict():
    hub, _ch, _reply, rc = deliver("maa-t15", translations=C2["translations"]["maa-t15"])
    hub.close()
    [o] = [o for o in rc.outcomes if o.claim_id == "m5.3"]
    assert o.display_status is S.AMBIGUOUS_TRANSLATION, o.display_status
    assert "supposition_as_fact" in [f.code for f in o.translation.interpretation.ambiguity_flags]


def test_a_supposed_value_fixed_on_a_free_variable_is_flagged_and_controls_are_not():
    claim = ClaimRecord(**IDS, claim_id="m5.3", claim_text="At x = 0, g(0) = 3.")
    assert supposition_as_fact(_problem("the free real variable of the functions g and h"), claim) is not None
    # controls: a symbol of the claim's own, a premise a source states, a claim that supposes nothing, another value
    assert supposition_as_fact(_problem("the x-coordinate of the stationary point"), claim) is None
    assert supposition_as_fact(_problem("the free real variable", kind="task_setting"), claim) is None
    assert supposition_as_fact(_problem("the free real variable"), ClaimRecord(**IDS, claim_id="m5.3", claim_text="g(0) = 3.")) is None
    assert supposition_as_fact(_problem("the free real variable"), ClaimRecord(**IDS, claim_id="m5.3", claim_text="At x = 2, g(2) = 7.")) is None
