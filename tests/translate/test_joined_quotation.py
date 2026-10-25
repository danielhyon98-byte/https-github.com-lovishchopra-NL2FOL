"""A located excerpt verifies a proposition only as a literal (an atom or its negation). A premise that joins what the
excerpt states to the writer's own proposition with "and", "or", "if" or "iff" is verified by no span: its grounding stays
unverified, a ``relation_in_source`` check names the connective as the writer's, and a proof that restates the conclusion
through it is circular (f07). A verified atomic quotation beside the writer's links (c04-quote) is untouched."""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TranslationStatus as T
from epinoic_logic.translate.grounding import check_problem_grounding

from ..evidence_support import deliver, outcome

POEM = SuppliedText(document_id="doc-house", title="The House at Night", author="Anonymous",
                    text="When the lamps go out the walls close in each night,\nand every door I try is locked from the other side.")
REF = [{"document_id": "doc-house", "excerpt": "the walls close in each night"}]


def _problem(expr: dict, *, conclusion: dict | None = None) -> Problem:
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "walls", "sort": "Bool", "meaning": "the poem says the walls close in each night"},
                    {"name": "trapped", "sort": "Bool", "meaning": "the speaker feels trapped"}],
        "premises": [{"id": "Q", "expr": expr, "label": "the line shows the speaker feels trapped",
                      "grounding": {"kind": "quotation", "certainty": "established", "source_refs": REF}}],
        "conclusion": conclusion or {"id": "C", "expr": {"op": "var", "name": "trapped"}}})


def test_f07_the_joined_quotation_is_refused_as_circular():
    _case, rc = deliver("f07_circular_joined_quote", "text")
    o = outcome(rc, "p1-point")
    assert o.translation.status is T.INVALID_FORMALIZATION and o.display_status is not S.ENTAILED
    assert any("E112" in d and "circular" in d for d in o.translation.diagnostics)
    joined = [c for c in o.translation.grounding_checks if c.target_id == "ev_line_shows" and c.method == "relation_in_source"]
    assert joined and all(c.verified is None for c in joined)
    assert "the connective 'and'" in joined[0].detail and "is the writer's own" in joined[0].detail
    assert not o.release.permitted


def test_c04_a_verified_atomic_quotation_beside_the_writers_links_is_untouched():
    _case, rc = deliver("c04_quoted_transcription", "text")
    o = outcome(rc, "p1-point")
    assert o.translation.status is T.TRANSLATED and o.display_status is S.ENTAILED
    assert "E112" not in {d.code for d in o.verification.diagnostics}
    assert o.verification.unverified_dependencies == []    # the quoted atom is verified; only the writer's links are its own


@pytest.mark.parametrize("op", ["and", "or", "implies", "iff"])
def test_a_compound_proposition_is_not_verified_by_its_located_excerpt(op):
    walls, trapped = {"op": "var", "name": "walls"}, {"op": "var", "name": "trapped"}
    expr = {"op": op, "args": [walls, trapped]} if op in ("and", "or") else {"op": op, "left": walls, "right": trapped}
    grounded, checks = check_problem_grounding(_problem(expr), [POEM])
    assert grounded.premises[0].grounding.verified is None
    [c] = [c for c in checks if c.target_id == "Q" and c.method == "relation_in_source"]
    assert c.verified is None and "is the writer's own" in c.detail


@pytest.mark.parametrize("expr", [{"op": "var", "name": "walls"}])
def test_a_literal_keeps_the_span_rule(expr):
    grounded, checks = check_problem_grounding(_problem(expr, conclusion={"id": "C", "expr": {"op": "var", "name": "trapped"}}), [POEM])
    assert grounded.premises[0].grounding.verified is True
    assert not [c for c in checks if c.target_id == "Q" and c.method == "relation_in_source"]


def test_a_negated_literal_keeps_the_span_rule_and_is_refuted_by_an_excerpt_that_states_the_atom():
    # Rewritten to a stricter rule in repair round 5 (ADV5-02): this case was a parameter of the test above and expected
    # verified=True, although its excerpt ("the walls close in each night") states the atom that the premise denies. A
    # literal is still read by the span rule (no relation_in_source check), and the excerpt now refutes it.
    grounded, checks = check_problem_grounding(_problem({"op": "not", "arg": {"op": "var", "name": "walls"}},
                                                        conclusion={"id": "C", "expr": {"op": "var", "name": "trapped"}}), [POEM])
    assert grounded.premises[0].grounding.verified is False
    assert not [c for c in checks if c.target_id == "Q" and c.method == "relation_in_source"]
    [c] = [c for c in checks if c.target_id == "Q" and c.method == "content_in_excerpt"]
    assert c.verified is False and "opposite polarity" in c.detail and "the negation of" in c.detail


def test_restating_the_point_through_a_joined_quotation_is_e112_and_through_a_verified_atom_is_not():
    cfg = SolverConfig(timeout_ms=4000, memory_max_mb=None)
    joined = _problem({"op": "and", "args": [{"op": "var", "name": "walls"}, {"op": "var", "name": "trapped"}]})
    grounded, _checks = check_problem_grounding(joined, [POEM])
    assert "E112" in {d.code for d in verify(grounded, cfg).diagnostics}
    atom = _problem({"op": "var", "name": "walls"}, conclusion={"id": "C", "expr": {"op": "var", "name": "walls"}})
    grounded, _checks = check_problem_grounding(atom, [POEM])
    assert grounded.premises[0].grounding.verified is True
    assert "E112" not in {d.code for d in verify(grounded, cfg).diagnostics}   # a verified quotation restated is a transcription
