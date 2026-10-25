"""Close round 1 of the argument-diagnosis regression review, the stated-rule reader (ADV6-01, ADV6-09):

* ADV6-01: a rule whose two sides an excerpt states was verified as "if A then B" whatever its sentence did to it. A hedge
  or another mood in the consequence ("may", "tends to", "would"), an alternative ("or"), a part of the condition the
  premise drops, a frame before the rule (a reported view, a denial, a doubt, a question, a scope limit), a restriction
  after it ("but only when", "unless") and an attribution tag ("..., some critics argue") each keep the source from stating
  the premise's rule: the located excerpt now refutes the premise (``relation_in_source`` False, ``source_mismatch``) and
  a record sentence of it validates no task-authority rule. Plain rules stay verified and the answers that apply them stay
  releasable.
* ADV6-09: the month "May" written inside a task sentence is no modal, so the task fact "... in May" is validated, and a
  rule whose sentence the excerpt cuts before its restriction is refuted for that restriction.

Every case is written for this round in wording of its own; nothing from a case is executed."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.quantities import SourceText
from epinoic_logic.translate.stated_rules import stated_rule

from ..evidence_support import deliver, diagnostics, outcome

A = "the central bank of Country Q raised interest rates in 2025"
B = "household borrowing in Country Q fell in 2025"


def _problem(excerpt: str, *, consequent: str = B, antecedent: str = A, kind: str = "quotation", doc: str = "ext") -> Problem:
    refs = [{"document_id": doc, "excerpt": excerpt}] if excerpt else []
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool", "meaning": antecedent}, {"name": "b", "sort": "Bool", "meaning": consequent}],
        "premises": [{"id": "t1", "expr": {"op": "var", "name": "a"}, "label": antecedent, "grounding": {"kind": "task_setting"}},
                     {"id": "q1", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}},
                      "label": "if the central bank raises interest rates, household borrowing falls",
                      "grounding": {"kind": kind, "source_refs": refs}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}, "label": consequent}})


def _rule_check(text: str, excerpt: str, **kw):
    task = TaskRecord.of("t", "r", "Using the extract, explain whether household borrowing in Country Q fell in 2025. "
                                   "The central bank of Country Q raised interest rates in 2025.")
    grounded, checks = check_problem_grounding(_problem(excerpt, **kw), [SuppliedText(document_id="ext", title="Extract", text=text)], task=task)
    q1 = next(p for p in grounded.premises if p.id == "q1")
    rel = [c for c in checks if c.target_id == "q1" and c.method == "relation_in_source"]
    return q1.grounding.verified, rel


QUALIFIED = [
    # a hedge or another mood in the consequence
    ("If the central bank raises interest rates, household borrowing may fall.", "If the central bank raises interest rates, household borrowing may fall", "hedged"),
    ("If the central bank raises interest rates, household borrowing tends to fall.", "If the central bank raises interest rates, household borrowing tends to fall", "hedged"),
    ("If the central bank raised interest rates, household borrowing would fall.", "If the central bank raised interest rates, household borrowing would fall", "hedged"),
    ("If the central bank raises interest rates, household borrowing usually falls.", "If the central bank raises interest rates, household borrowing usually falls", "hedged"),
    # an alternative in the consequence
    ("If the central bank raises interest rates, household borrowing falls or saving rises.",
     "If the central bank raises interest rates, household borrowing falls or saving rises", "alternative"),
    # a part of the condition the premise drops
    ("If the central bank raises interest rates and house prices are stable, household borrowing falls.",
     "If the central bank raises interest rates and house prices are stable, household borrowing falls", "condition"),
    # a frame before the rule (outside the excerpt)
    ("Many commentators claim that if the central bank raises interest rates, household borrowing falls.",
     "if the central bank raises interest rates, household borrowing falls", "framed"),
    ("It is false that if the central bank raises interest rates, household borrowing falls.",
     "if the central bank raises interest rates, household borrowing falls", "framed"),
    ("Researchers dispute whether, if the central bank raises interest rates, household borrowing falls.",
     "if the central bank raises interest rates, household borrowing falls", "framed"),
    ("Is it the case that if the central bank raises interest rates, household borrowing falls?",
     "if the central bank raises interest rates, household borrowing falls", "question"),
    ("In some countries, if the central bank raises interest rates, household borrowing falls.",
     "if the central bank raises interest rates, household borrowing falls", "limited"),
    # after the rule: a restriction the excerpt cuts off, an attribution tag
    ("If the central bank raises interest rates, household borrowing falls, but only when wages are flat.",
     "If the central bank raises interest rates, household borrowing falls", "restricted"),
    ("If the central bank raises interest rates, household borrowing falls unless credit is subsidised.",
     "If the central bank raises interest rates, household borrowing falls", "restricted"),
    ("If the central bank raises interest rates, household borrowing falls, some critics argue.",
     "If the central bank raises interest rates, household borrowing falls", "credited"),
]


@pytest.mark.parametrize("text, excerpt, why", QUALIFIED, ids=[f"{w}-{i}" for i, (_t, _e, w) in enumerate(QUALIFIED)])
def test_a_qualified_rule_refutes_the_premise_that_encodes_it_plainly(text, excerpt, why):
    verified, rel = _rule_check(text, excerpt)
    assert verified is False
    [check] = rel
    assert check.verified is False and why in check.detail and "does not ground this premise" in check.detail


PLAIN = [
    ("If the central bank raises interest rates, household borrowing falls.", "If the central bank raises interest rates, household borrowing falls"),
    ("Whenever the central bank raises interest rates, household borrowing falls.", "Whenever the central bank raises interest rates, household borrowing falls"),
    # a reason after the rule, an endorsing credit, a negation in another clause of the sentence: still the source's own rule
    ("If the central bank raises interest rates, household borrowing falls, because loans cost more.",
     "If the central bank raises interest rates, household borrowing falls"),
    ("If the central bank raises interest rates, household borrowing falls, as the report argues.",
     "If the central bank raises interest rates, household borrowing falls"),
    ("Wages did not change in 2024, and if the central bank raises interest rates, household borrowing falls.",
     "if the central bank raises interest rates, household borrowing falls"),
    ("The report shows that if the central bank raises interest rates, household borrowing falls.",
     "if the central bank raises interest rates, household borrowing falls"),
]


@pytest.mark.parametrize("text, excerpt", PLAIN)
def test_control_a_plain_rule_stays_verified(text, excerpt):
    verified, rel = _rule_check(text, excerpt)
    assert verified is True and [c.verified for c in rel] == [True]


def test_control_a_hedge_the_consequents_own_meaning_states_is_the_premises_own():
    verified, rel = _rule_check("If the central bank raises interest rates, household borrowing may fall.",
                                "If the central bank raises interest rates, household borrowing may fall",
                                consequent="household borrowing in Country Q may fall in 2025")
    assert verified is True and [c.verified for c in rel] == [True]


def test_a_restriction_the_premise_leaves_out_is_named_and_one_it_writes_is_its_own():
    text = "If the central bank raises interest rates, household borrowing falls except among pensioners."
    verified, rel = _rule_check(text, text[:-1])
    assert verified is False and "restricted" in rel[0].detail
    # control: the consequent's own meaning writes the restriction, so the premise encodes the rule with it
    verified, rel = _rule_check(text, text[:-1], consequent="household borrowing in Country Q fell in 2025 except among pensioners")
    assert verified is True and [c.verified for c in rel] == [True]


def test_control_the_month_may_in_a_consequence_is_no_hedge():
    src = SourceText("supplied_text", "ext", "If the frost is late, the orchards flower in May.")
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool", "meaning": "the frost is late"}, {"name": "b", "sort": "Bool", "meaning": "the orchards flower in May"}],
        "premises": [{"id": "q1", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    syms = {s.name: s for s in problem.symbols}
    rule = stated_rule(problem.premises[0].expr, syms, src, (0, len(src.text) - 1))
    assert rule is not None and rule.qualifier is None


def test_a_framed_rule_in_a_supplied_text_validates_no_task_authority_rule():
    # a task_setting rule premise with no excerpt is read against the records: a framed sentence states no rule
    task = TaskRecord.of("t", "r", "Explain whether household borrowing in Country Q fell in 2025.")
    framed = SuppliedText(document_id="ext", title="Extract", text="Some analysts claim that if the central bank raises interest rates, household borrowing falls.")
    plain = SuppliedText(document_id="ext", title="Extract", text="If the central bank raises interest rates, household borrowing falls.")
    for doc, expected in ((framed, False), (plain, True)):
        grounded, _checks = check_problem_grounding(_problem("", kind="task_setting"), [doc], task=task)
        q1 = next(p for p in grounded.premises if p.id == "q1")
        assert (q1.grounding.verified is True) is expected, doc.text


# ------------------------------------------------------------------------------------------------- end to end, and ADV6-09

def _case(case_id: str, extract: str, excerpt: str, fact: str, a_meaning: str, b_meaning: str, rule_label: str, conclusion: str) -> dict:
    request = f"Using the extract, explain whether {b_meaning}. {fact} [3 marks]"
    answer = f'The extract says "{excerpt}". {fact[:-1]}, so {conclusion}.'
    return {
        "case_format": "argdiag-corpus/1", "id": case_id, "family": "evidence", "expected_label": "none", "acceptable_labels": [],
        "title": case_id, "subject": "Biology", "task_type": "source_analysis", "agent_id": "biology-specialist",
        "request": request, "answer": answer,
        "supplied_texts": [{"document_id": "ext", "title": "Extract", "text": extract}],
        "ids": {"task_id": f"task-{case_id}", "request_id": f"req-{case_id}", "report_id": "rep-1", "plan_id": f"plan-{case_id}"},
        "modes": [{"name": "text", "delivery": "text", "synthesis": "none"}], "report_claims": [],
        "translations": [{"contains": f"so {conclusion}", "proposal": {
            "problem": {"ir_version": "1.0", "problem_id": "p", "request_id": "x", "claim_id": "x", "query": "entailment",
                        "symbols": [{"name": "a", "sort": "Bool", "meaning": a_meaning, "grounding": {"kind": "task_setting", "source_refs": []}},
                                    {"name": "b", "sort": "Bool", "meaning": b_meaning, "grounding": {"kind": "specialist_inference", "source_refs": []}}],
                        "premises": [{"id": "t1", "expr": {"op": "var", "name": "a"}, "label": a_meaning, "materiality": "material",
                                      "grounding": {"kind": "task_setting", "source_refs": [], "certainty": "established"}},
                                     {"id": "q1", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}},
                                      "label": rule_label, "materiality": "material",
                                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": "ext", "excerpt": excerpt}],
                                                    "certainty": "established"}}],
                        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}, "label": b_meaning, "materiality": "material",
                                       "grounding": {"kind": "specialist_inference", "source_refs": []}}},
            "interpretation": {"reading": "probe", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}}],
        "fidelity_review": "faithful"}


MEADOW = dict(fact="The meadow was cut for hay in May.", a_meaning="the meadow was cut for hay in May",
              b_meaning="ground-nesting birds in the meadow lost their nests in May",
              rule_label="if a meadow is cut for hay, ground-nesting birds lose their nests",
              conclusion="ground-nesting birds in the meadow lost their nests in May")


def _delivered(extract: str, excerpt: str):
    case = _case("close1-meadow", extract, excerpt, **MEADOW)
    _case_, rc = deliver(case, "text")
    [o] = [o for o in rc.outcomes if o.translation.problem is not None]
    return rc, o


def test_control_a_task_fact_dated_in_may_is_validated_and_the_plain_rule_released():
    rc, o = _delivered("If a meadow is cut for hay, ground-nesting birds lose their nests.",
                       "If a meadow is cut for hay, ground-nesting birds lose their nests")
    checks = {c.target_id: c for c in o.translation.grounding_checks if c.method in ("content_in_task", "relation_in_source")}
    assert checks["t1"].verified is True and checks["q1"].verified is True
    assert o.release.permitted
    assert not [d for d in diagnostics(rc, prefix="EVD-") if d.severity in ("warning", "error")]


def test_a_rule_cut_before_its_restriction_is_named_source_mismatch_and_not_released():
    rc, o = _delivered("If a meadow is cut for hay, ground-nesting birds lose their nests, but only when the cut comes before July.",
                       "If a meadow is cut for hay, ground-nesting birds lose their nests")
    checks = {c.target_id: c for c in o.translation.grounding_checks if c.method in ("content_in_task", "relation_in_source")}
    assert checks["t1"].verified is True and checks["q1"].verified is False
    assert not o.release.permitted
    assert any(d.defect == "source_mismatch" and d.severity == "warning" for d in diagnostics(rc, "EVD-SRC-003"))
    assert outcome(rc, o.claim_id).display_status.value == "ENTAILED"   # the engine's verdict on the encoding is unchanged
