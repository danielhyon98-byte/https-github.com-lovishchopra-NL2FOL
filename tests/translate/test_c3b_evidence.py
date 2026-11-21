"""Round-10 leftovers on the evidence family (rules argdiag-2):

* R10-CORE-BUG1-EVIDENCE (the supporting-claims part): EVD-LACK-001 charged c3 en-t16 p1-s01 for resting on 'supporting point p2:
  the auctioneer's language turns possessions into goods ...', a premise that restates one of the claim's own supporting claims, whose
  evidence is read on that claim. Such a premise lacks no evidence of the point's own.
* R10-STEM-H4-EVD-WORDING: EVD-LACK-001 said 'nothing in the supplied texts or the task supports it' when no text was searched for
  the premise's words; it now says that nothing the premise cites supports it, and that its words were not looked for."""
from __future__ import annotations

from types import SimpleNamespace

from epinoic_logic.translate.diag_evidence import _has_literal, _restates_supporting


def _claim(text: str, role: str = "point") -> SimpleNamespace:
    return SimpleNamespace(claim_text=text, claim_role=role)


SUPPORTING = (_claim("The auctioneer's language turns possessions into goods, and the narrator makes that trade audible."),
              _claim("The father's silence works in the opposite direction."))


def test_a_premise_restating_a_supporting_claim_rests_on_the_answers_own_claim():
    ctx = SimpleNamespace(supporting=SUPPORTING)
    p = SimpleNamespace(label="supporting point p2: the auctioneer's language turns possessions into goods and the narrator makes that trade audible",
                        expr=None, id="sup_p2")
    assert _restates_supporting(ctx, p, {})


def test_control_a_premise_no_supporting_claim_states_is_still_read():
    ctx = SimpleNamespace(supporting=SUPPORTING)
    for label in ("root tips contain meristematic tissue that divides continuously", "the auctioneer was paid by the bank"):
        assert not _restates_supporting(ctx, SimpleNamespace(label=label, expr=None, id="gk"), {}), label
    assert not _restates_supporting(SimpleNamespace(supporting=()), SimpleNamespace(label=SUPPORTING[0].claim_text, expr=None, id="x"), {})
    # a supporting FACT the writer states with no source is no argued point: a premise restating it still lacks evidence (e01)
    fact = SimpleNamespace(supporting=(_claim("Household borrowing fell sharply during 2023.", "evidence"),))
    assert not _restates_supporting(fact, SimpleNamespace(label="household borrowing fell sharply during 2023", expr=None, id="P_borrow"), {})


def test_the_literal_reader_finds_a_figure_and_only_a_figure():
    from epinoic_logic.api.ir import Problem
    p = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": "x", "sort": "Int"}, {"name": "b", "sort": "Bool"}],
                                "premises": [{"id": "A", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "4"}}},
                                             {"id": "B", "expr": {"op": "var", "name": "b"}}],
                                "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    assert _has_literal(p.premises[0].expr) and not _has_literal(p.premises[1].expr)
