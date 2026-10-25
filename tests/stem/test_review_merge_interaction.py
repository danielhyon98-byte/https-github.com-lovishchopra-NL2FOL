"""The two STEM review branches together: a genuine one-line answer addresses its item.

The checks review (S2, S5, S7) pins one-line answers such as ``1/2 = 0.50`` to "Calculate 1/2 exactly, without rounding."
as clean receipts. The channel review (S3) stopped computing command words from counting as evidence on their own, so on
the merged tree those answers were left with INT-REQ-004 (the item read as unaddressed). The cause was the STEM topic
evidence, which credited neither the item's own expression written in the claim, nor the kind of equation a claim states
("quadratic"), nor an operation the item names in words and the claim writes in notation ("the absolute value" and
``|−2|``). Each is now evidence; unrelated arithmetic still addresses nothing.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem.hub_hooks import STEM_HOOKS, _equation_degree, _expression_runs, _writes_expression
from epinoic_logic.stem import build_document

KEY = b"stem-review-merge-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
MAA = "Mathematics: Analysis and Approaches"


def send(subject: str, ask: str, answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=["spec"]))
    m, _req, rq = hub.dispatch("t", "spec", ask)
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED
    reply, rc = hub.receive("t", m.message_id, answer, agent_id="spec", report_id="r")
    assert reply is not None
    return rc


def coverage(rc) -> dict[str, bool]:
    return {c.item_id: c.addressed for c in rc.coverage}


GENUINE = [
    ("Calculate 1/2 exactly, without rounding.", "1/2 = 0.50"),
    ("Calculate 1/2 exactly, without rounding.", "1/2 = 50/100"),
    ("Solve the quadratic equation.", "x² = 4 ⇒ x = -2 or x = 2"),
    ("Solve the quadratic equation.", "x² = 4 ⇒ x = ±2"),
    ("Solve the quadratic equation.", "x² = 4\nx = -2 or x = 2"),
    ("Calculate the absolute value of negative two.", "|-2| = 2"),
    ("Calculate the absolute value of negative two.", "$|-2| = 2$"),
]


@pytest.mark.parametrize("ask,answer", GENUINE)
def test_a_genuine_one_line_answer_addresses_its_item(ask, answer):
    rc = send(MAA, ask, answer)
    assert coverage(rc) == {"i1": True}, [f.message[:120] for f in rc.findings]
    assert not [f for f in rc.findings if f.code == "INT-REQ-004"]
    assert rc.status is TransmissionStatus.ACCEPTED


UNRELATED = [
    ("Calculate 1/2 exactly, without rounding.", "2 + 2 = 4."),
    ("Calculate 1/2 exactly, without rounding.", "3/4 = 0.75"),
    ("Solve the quadratic equation.", "2 + 2 = 4."),
    ("Solve the quadratic equation.", "2x + 1 = 5 ⇒ x = 2"),   # a linear equation is no answer about a quadratic
    ("Calculate the absolute value of negative two.", "2 + 2 = 4."),
    ("Simplify 2³ × 2⁴ and evaluate it.", "2 + 2 = 4."),
]


@pytest.mark.parametrize("ask,answer", UNRELATED)
def test_unrelated_arithmetic_still_leaves_the_item_unaddressed(ask, answer):
    rc = send(MAA, ask, answer)
    assert coverage(rc) == {"i1": False}
    assert "INT-REQ-004" in [f.code for f in rc.findings]


def test_the_item_expression_evidence_is_token_for_token_and_only_for_notation_items():
    item = "Calculate 1/2 exactly, without rounding."
    assert _expression_runs(item) == [(("NUM", 1), ("OP", "/"), ("NUM", 2))]
    assert _writes_expression("1/2 = 0.50", _expression_runs(item))
    assert not _writes_expression("2 + 2 = 4", _expression_runs(item))
    assert not _writes_expression("2/1 = 2", _expression_runs(item))            # the same figures in another expression
    assert STEM_HOOKS.topic_evidence(item, "1/2 = 0.50", "1/2 = 0.50", None, "mathematics_aa", notation_only=True)
    assert not STEM_HOOKS.topic_evidence(item, "2 + 2 = 4", "2 + 2 = 4", None, "mathematics_aa", notation_only=True)
    # an item that names a topic in words is not read through its expression: its topic words decide
    assert not STEM_HOOKS.topic_evidence("Calculate the acceleration of 1/2.", "1/2 = 0.50", "1/2 = 0.50", None, "physics")
    # a sign, a lone figure, prose words and units set apart write no expression
    assert _expression_runs("The temperature fell to −5 degrees.") == []
    assert _expression_runs("It took 4 s.") == []
    assert _expression_runs("Simplify √50.") and _expression_runs("Find 2³ × 2⁴.")


def test_the_degree_of_an_equation_in_one_unknown():
    def degree(text: str):
        doc = build_document(text, None, "mathematics_aa")
        rel = [r for r in doc.relations if r.op == "=" and r.left is not None][0]
        return _equation_degree(rel.left.node, rel.right.node)
    assert degree("x² = 4") == 2
    assert degree("2x + 3 = 7") == 1
    assert degree("x³ − x = 0") == 3
    assert degree("x = 2") is None              # a value stated for a symbol is no equation to solve
    assert degree("2 + 2 = 4") is None          # no unknown
    assert degree("x² + y = 4") is None         # two unknowns


def test_notation_words_are_lent_only_by_the_notation():
    terms = STEM_HOOKS.coverage_terms("|-2| = 2", "|-2| = 2", None, "mathematics_aa")
    assert {"absolute", "modulus"} <= terms
    assert "absolute" not in STEM_HOOKS.coverage_terms("2 + 2 = 4", "2 + 2 = 4", None, "mathematics_aa")
    assert "quadratic" in STEM_HOOKS.coverage_terms("x² = 4 ⇒ x = ±2", "x² = 4 ⇒ x = ±2", None, "mathematics_aa")
    assert "quadratic" not in STEM_HOOKS.coverage_terms("2x + 1 = 5 ⇒ x = 2", "2x + 1 = 5 ⇒ x = 2", None, "mathematics_aa")
