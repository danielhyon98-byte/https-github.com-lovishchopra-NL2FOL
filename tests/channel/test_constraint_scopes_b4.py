"""E2E B4: a word bound is measured on the span the request sets it on (``Constraint.scope``), never on the whole answer
when the request names a part, each part, the answer proper or the paragraph it asks for.

The development cases e2e-B4-bm, -ec, -ps, -en and -hi are correct answers the end-to-end judge measured within their
bounds; before the scope existed each got a false INT-REQ-005 error (the whole answer was counted). The controls keep a
genuinely over-length part, a part over its own bound beside one within it, an over-length answer proper, a part the
answer does not label and an overall bound."""
from __future__ import annotations

import pytest

from epinoic_logic.channel.contracts import Constraint, ConstraintScope
from epinoic_logic.channel.request_parser import deliverable_blocks, extract_constraints, part_section_text

from ..argdiag_cases import load_case
from .dev_case_hub import run_case


def _bound(run, kind="max_words"):
    req = list(run.channel.requests.values())[-1]
    c = next(c for c in req.constraints if c.kind == kind)
    res = next(r for r in run.receipt.constraint_results if r.constraint_id == c.constraint_id)
    return c, res


def _no_word_error(run) -> bool:
    return not [f for f in run.receipt.findings if f.code == "INT-REQ-005" and f.severity == "error"]


# ------------------------------------------------------------------ the parser binds each bound to its scope

@pytest.mark.parametrize("text, kind, value, scope", [
    ("Please show working, and keep (e) under 150 words.", "max_words", "150", ConstraintScope(kind="part", parts=["e"])),
    ("(e) and (f) under 120 words each please.", "max_words", "120", ConstraintScope(kind="each_part", parts=["e", "f"])),
    ("Give me a plan first, then the essay, max 500 words for the answer.", "max_words", "500", ConstraintScope(kind="answer_proper")),
    ("Can you write ONE paragraph on the imagery? max 250 words.", "max_words", "250", ConstraintScope(kind="paragraph")),
    ("Answer (a) and (b), 400 words max.", "max_words", "400", None),
    ("Answer every part in no more than 500 words in total.", "max_words", "500", None),
])
def test_a_bound_is_bound_to_the_span_the_request_names(text, kind, value, scope):
    cons = [c for c in extract_constraints(text) if c.kind == kind]
    assert len(cons) == 1, cons
    assert cons[0].value == value
    got = cons[0].scope
    assert (got if got is None or got.kind != "whole" else None) == scope


def test_n_words_max_and_max_n_words_are_both_read():
    assert [c.value for c in extract_constraints("Keep it to 200 words max.") if c.kind == "max_words"] == ["200"]
    assert [c.value for c in extract_constraints("Write max 200 words.") if c.kind == "max_words"] == ["200"]


def test_a_constraint_without_a_scope_dumps_as_before():
    c = Constraint(constraint_id="c1", kind="max_words", value="300", text="max 300 words")
    assert "scope" not in c.model_dump(exclude_none=True)


# ------------------------------------------------------------------ the E2E cases: measured on their scope, no error

@pytest.mark.parametrize("case_id, kind, parts, where, measured", [
    ("e2e-B4-bm", "part", ["e"], "on part (e)", "141 words"),
    ("e2e-B4-ec", "each_part", ["e", "f"], "on each part: (e) 108, (f) 107 words", None),
    ("e2e-B4-ps", "answer_proper", [], "on the answer proper", "480 words"),
    ("e2e-B4-en", "paragraph", [], "on the paragraph the request asks for", "234 words"),
    ("e2e-B4-hi", "paragraph", [], "on the paragraph the request asks for", None),
])
def test_the_e2e_bounds_are_measured_on_their_scope(case_id, kind, parts, where, measured):
    run = run_case(case_id)
    c, res = _bound(run)
    assert c.scope is not None and c.scope.kind == kind and c.scope.parts == parts
    assert res.satisfied is True and res.method == "formal" and res.formal_status == "ENTAILED"
    assert where in res.detail
    if measured:
        assert f"measured {measured}" in res.detail
    assert _no_word_error(run)


# ------------------------------------------------------------------ controls: a bound the scope breaks still fails

def _with_answer(case_id: str, edit) -> dict:
    case = load_case(case_id)
    case["answer"] = edit(case["answer"])
    return case


PADDING = (" The loan also commits the owners to monthly repayments for five years, whatever happens to sales at the new site,"
           " and a bank may ask for security over the existing shop's equipment, so a bad first year at the university would"
           " put the original business at risk as well as the new one. That risk falls on owners who have little cash to spare.")


def test_a_genuinely_over_length_part_still_gives_INT_REQ_005():
    case = _with_answer("e2e-B4-bm", lambda a: a.rstrip() + PADDING)
    assert len(part_section_text(case["answer"], "e").split()) > 150
    run = run_case("e2e-B4-bm", case=case)
    c, res = _bound(run)
    assert c.scope.kind == "part" and res.satisfied is False and res.formal_status == "COUNTEREXAMPLE"
    errors = [f for f in run.receipt.findings if f.code == "INT-REQ-005" and f.severity == "error"]
    assert errors and "on part (e)" in res.detail


def test_each_part_is_measured_on_its_own():
    anchor = "cutting consumption towards Q*."
    case = _with_answer("e2e-B4-ec", lambda a: a.replace(anchor, anchor + PADDING * 2))
    assert len(part_section_text(case["answer"], "f").split()) > 120
    run = run_case("e2e-B4-ec", case=case)
    c, res = _bound(run)
    assert c.scope.kind == "each_part" and res.satisfied is False
    assert "(e) 108" in res.detail                                     # (e) is still within its own bound
    assert [f for f in run.receipt.findings if f.code == "INT-REQ-005" and f.severity == "error"]


def test_an_over_length_answer_proper_still_fails_with_the_plan_left_out():
    case = _with_answer("e2e-B4-ps", lambda a: a.rstrip() + "\n\n" + ("This conclusion restates the evaluation in other words. " * 8).strip())
    run = run_case("e2e-B4-ps", case=case)
    c, res = _bound(run)
    assert c.scope.kind == "answer_proper" and res.satisfied is False and "on the answer proper" in res.detail


def test_a_part_the_answer_does_not_label_is_never_measured_on_another_span():
    case = _with_answer("e2e-B4-bm", lambda a: a.replace("**(e) [4]**\n", "").rstrip() + PADDING * 3)
    assert part_section_text(case["answer"], "e") is None
    run = run_case("e2e-B4-bm", case=case)
    c, res = _bound(run)
    assert c.scope.kind == "part" and res.satisfied is None and res.method == "not_checkable"
    assert "cannot be measured on its scope" in res.detail
    warns = [f for f in run.receipt.findings if f.code == "INT-REQ-005" and f.severity == "warning"]
    assert warns                                                        # said so, never read as a pass


def test_an_unlabelled_part_within_a_short_whole_answer_is_decided_by_the_whole():
    case = load_case("e2e-B4-bm")
    case["request"] = case["request"].replace("keep (e) under 150 words", "keep (f) under 2000 words")
    run = run_case("e2e-B4-bm", case=case)
    c, res = _bound(run)
    assert c.scope.parts == ["f"] and part_section_text(case["answer"], "f") is None
    assert res.satisfied is True and "the whole decides the bound" in res.detail   # (f) lies within the whole answer


def test_the_paragraph_scope_leaves_out_side_answers_and_meta_text():
    case = load_case("e2e-B4-en")
    blocks = deliverable_blocks(case["answer"], case["request"])
    assert len(blocks) == 4 and not [b for b in blocks if b.startswith("It is a metaphor")]   # the answer to "quick question"
    case = load_case("e2e-B4-ps")
    blocks = deliverable_blocks(case["answer"], case["request"])
    assert not [b for b in blocks if b.startswith(("On your 30% figure", "Next step"))]       # side answer and footer
