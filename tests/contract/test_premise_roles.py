"""Premise roles (``translate.roles``): every shape and kind, the writer's marked link, an unmarked link and a label that
claims an authority no check gave the relation; and the record the translator writes."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Assertion
from epinoic_logic.translate.contracts import GroundingCheck, PremiseRole, TranslationStatus
from epinoic_logic.translate.roles import authority_of, premise_role, premise_roles, role_of

from .helpers import R, V, eq, implies, make_report, output, run_claim, speed_problem, writer_link_problem


def A(expr: dict, grounding=None, aid: str = "p1") -> Assertion:
    return Assertion.model_validate({"id": aid, "expr": expr, **({"grounding": grounding} if grounding is not None else {})})


@pytest.mark.parametrize("expr, role", [
    (V("a"), "fact"),
    ({"op": "not", "arg": V("a")}, "fact"),
    (eq(V("d"), R(120)), "fact"),                                                     # an assignment of a stated figure
    ({"op": "and", "args": [V("a"), V("b")]}, "fact"),
    (implies(V("a"), V("b")), "link"),
    ({"op": "iff", "left": V("b"), "right": eq(V("n"), R(17))}, "definition"),
    ({"op": "iff", "left": {"op": "and", "args": [V("a"), V("b")]}, "right": {"op": "or", "args": [V("c"), V("d")]}}, "link"),
    ({"op": "or", "args": [V("a"), V("b")]}, "either_or"),
    (eq(V("speed"), {"op": "div", "left": V("d"), "right": R(8)}), "figure_relation"),
    ({"op": "ne", "left": V("x"), "right": R(5)}, "figure_relation"),
    ({"op": "le", "left": V("words"), "right": V("limit")}, "figure_relation"),
])
def test_the_role_is_read_from_the_expression(expr, role):
    assert role_of(A(expr).expr) == role


@pytest.mark.parametrize("grounding, refuted, authority", [
    ({"kind": "task_setting", "verified": True}, False, "established"),
    ({"kind": "quotation", "verified": True}, False, "established"),
    ({"kind": "general_knowledge", "verified": True}, False, "writer_own"),         # the writer's own kind never gains authority
    (None, False, "writer_own"),
    ({"kind": "specialist_inference"}, False, "writer_own"),
    ({"kind": "assumption"}, False, "writer_own"),
    ({"kind": "task_setting"}, False, "unverified"),
    ({"kind": "supplied_text"}, False, "unverified"),
    ({"kind": "arithmetic_fact", "verified": False}, False, "refuted"),
    ({"kind": "task_setting"}, True, "refuted"),
])
def test_the_authority_is_read_from_the_check_never_from_the_label(grounding, refuted, authority):
    assert authority_of(A(V("a"), grounding).grounding, refuted) == authority


@pytest.mark.parametrize("grounding, marked, connective", [
    ({"kind": "specialist_inference", "note": "link: which shows"}, "translator_link", "which shows"),
    ({"kind": "specialist_inference"}, "unmarked_link", None),
    ({"kind": "assumption"}, "unmarked_link", None),
    (None, "unmarked_link", None),
    ({"kind": "general_knowledge", "note": "rule"}, "translator_rule", None),
    ({"kind": "task_setting"}, "label_conflict", None),
    ({"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": "a means b"}]}, "label_conflict", None),
    ({"kind": "rubric_rule", "verified": True}, "source_link", None),
])
def test_a_link_is_marked_by_its_kind_and_its_check(grounding, marked, connective):
    role = premise_role(A(implies(V("a"), V("b")), grounding))
    assert (role.role, role.marked, role.connective) == ("link", marked, connective)


def test_a_fact_is_marked_fact_whatever_its_kind():
    for grounding in ({"kind": "specialist_inference", "note": "link: so"}, {"kind": "task_setting"}, None):
        assert premise_role(A(V("a"), grounding)).marked == "fact"


def test_premise_roles_follow_premise_order_and_read_refuting_checks():
    problem = writer_link_problem(fact_verified=False)
    check = GroundingCheck(target_id="e", kind="task_setting", method="numeric_in_task", verified=False, detail="refuted")
    roles = premise_roles(problem, [check])
    assert [(r.assertion_id, r.role, r.authority, r.marked) for r in roles] == [("e", "fact", "refuted", "fact"),
                                                                                ("l_so", "link", "writer_own", "translator_link")]
    assert premise_roles(None) == []
    assert set(roles[0].model_dump()) == {"assertion_id", "role", "authority", "marked", "kind"}       # empty fields left out
    assert PremiseRole.model_validate(roles[1].model_dump()) == roles[1]


def test_the_translator_writes_the_roles_into_the_record_and_an_empty_record_leaves_them_out():
    claim, report = make_report("The average speed of the car is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    assert [(r.assertion_id, r.role, r.authority, r.marked) for r in out.translation.premise_roles] == [
        ("D", "fact", "established", "fact"), ("SPEED", "figure_relation", "established", "source_link")]
    assert out.translation.asserted_verified == [] and "asserted_verified" not in out.translation.model_dump()
    poem, poem_report = make_report("The poem is sad.", role="interpretation", kind="interpretive", subject="English A: Literature", texts=())
    not_eligible = run_claim(poem, poem_report, output(speed_problem()))
    assert not_eligible.translation.status is TranslationStatus.NOT_ELIGIBLE
    assert "premise_roles" not in not_eligible.translation.model_dump() and "premise_roles" not in not_eligible.translation.model_dump(mode="json")
