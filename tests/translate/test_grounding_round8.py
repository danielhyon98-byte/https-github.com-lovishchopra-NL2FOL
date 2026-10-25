"""Review round 8, grounding:

* fidelity-1: a located excerpt verifies an assignment only for the quantity its clause is about. "In 2020 Lowtown had 252
  residents" (whole or trimmed to "Lowtown had 252 residents") states 252 for 2020, so a premise that gives the 2010
  count 252 is refuted, named in the check's detail, and the engine lists it as an ungrounded dependency; the 2020
  premise grounded by the same excerpt stays verified.
* security-2: a relayed specialist's report (a ``peer:`` document, or an author ``<subject>-specialist``) confers no
  authority. A premise whose only support is another agent's figure is unchecked (``peer_report``), the engine lists it as a
  dependency no check established,
  and the release is refused although the review is faithful; the same words in a primary supplied text verify it and the
  release is permitted.
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.grounding import PEER_REPORT, check_problem_grounding
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"grounding-round8-test-key-0123456789"

# ------------------------------------------------------------------------------------------------ fidelity-1

TOWN = SuppliedText(document_id="doc-town", title=None, author=None, text="In 2010 Lowtown had 200 residents. In 2020 Lowtown had 252 residents.")


def _lowtown(excerpt: str) -> Problem:
    ref = {"kind": "quotation", "certainty": "established", "source_refs": [{"document_id": "doc-town", "excerpt": excerpt}]}
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "pr5", "request_id": "req", "claim_id": "g1.1", "query": "entailment",
        "symbols": [{"name": "p2010", "sort": "Int", "meaning": "Lowtown residents in 2010 (count)"},
                    {"name": "p2020", "sort": "Int", "meaning": "Lowtown residents in 2020 (count)"}],
        "premises": [{"id": "ev1", "expr": {"op": "eq", "left": {"op": "var", "name": "p2010"}, "right": {"op": "int", "value": "252"}},
                      "label": "In 2010 Lowtown had 252 residents", "grounding": ref},
                     {"id": "ev2", "expr": {"op": "eq", "left": {"op": "var", "name": "p2020"}, "right": {"op": "int", "value": "252"}},
                      "label": "In 2020 Lowtown had 252 residents", "grounding": ref}],
        "conclusion": {"id": "concl", "expr": {"op": "eq", "left": {"op": "var", "name": "p2010"}, "right": {"op": "var", "name": "p2020"}},
                       "label": "Lowtown had the same number of residents in 2020 as in 2010"}})


@pytest.mark.parametrize("excerpt", ["In 2020 Lowtown had 252 residents", "Lowtown had 252 residents"])
def test_another_years_figure_does_not_ground_the_premise(excerpt):
    grounded, checks = check_problem_grounding(_lowtown(excerpt), [TOWN])
    verdicts = {p.id: p.grounding.verified for p in grounded.premises}
    assert verdicts == {"ev1": False, "ev2": True}
    [failed] = [c for c in checks if c.target_id == "ev1" and c.method == "figures_in_excerpt"]
    assert failed.verified is False and "stated for 2020" in failed.detail and "not for 2010" in failed.detail
    r = verify(grounded, CFG)
    assert r.status is S.ENTAILED and r.ungrounded_dependencies == ["ev1"]     # the false claim's premise is no established fact


def test_the_years_own_figure_grounds_it():
    problem = _lowtown("In 2010 Lowtown had 200 residents")
    data = problem.model_dump(mode="json")
    data["premises"][0]["expr"]["right"]["value"] = "200"
    grounded, _checks = check_problem_grounding(Problem.model_validate(data), [TOWN])
    assert grounded.premises[0].grounding.verified is True


# ------------------------------------------------------------------------------------------------ security-2

PEER_TEXT = "Maths specialist report: the price index rose to 5000 by November 1923."


def _outcome(document_id: str, author: str):
    supplied = [SuppliedText(document_id=document_id, author=author, text=PEER_TEXT)]
    text = "The price index rose to 5000, so it exceeded 1000."
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="generic-structured", subject="History", task_type="essay")
    claim = ClaimRecord(**ids, claim_id="k1", claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        source_refs=[{"document_id": document_id, "excerpt": "the price index rose to 5000"}])
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim], supplied_texts=supplied,
                              created_at="2026-10-11T00:00:00Z")
    p = {"op": "var", "name": "p"}
    problem = {"problem_id": "k1-p", "request_id": "r", "claim_id": "k1", "query": "entailment",
               "symbols": [{"name": "p", "sort": "Int", "meaning": "the price index in November 1923"}],
               "premises": [{"id": "P1", "expr": {"op": "eq", "left": p, "right": {"op": "int", "value": "5000"}}, "label": "the price index rose to 5000",
                             "grounding": {"kind": "quotation", "source_refs": [{"document_id": document_id, "excerpt": "the price index rose to 5000"}]}}],
               "conclusion": {"id": "C", "expr": {"op": "gt", "left": p, "right": {"op": "int", "value": "1000"}}, "label": "it exceeded 1000"}}
    proposal = {"k1": {"problem": problem, "interpretation": {"reading": "p = 5000 entails p > 1000", "glossary": [{"symbol": "p", "meaning": "the price index"}],
                                                              "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}}
    reviewer = SemanticReviewer(FixtureReviewProvider({"k1": {"verdict": "faithful", "issues": []}}))
    return verify_claim(claim, report, Translator(FixtureTranslationProvider(proposal)), reviewer, config=CFG, signing_key=KEY, key_id="kid")


@pytest.mark.parametrize("document_id, author", [("peer:maa-e1a", "maths-specialist"), ("doc-relay", "maths-specialist"), ("peer:maa-e1a", None)])
def test_a_premise_grounded_only_in_a_peer_report_is_unverified_and_not_released(document_id, author):
    o = _outcome(document_id, author)
    [check] = [c for c in o.translation.grounding_checks if c.target_id == "P1" and c.ref_index == 0]
    assert check.verified is None and PEER_REPORT in check.detail
    v = o.verification
    assert v is not None and v.status is S.ENTAILED and "P1" in [*v.ungrounded_dependencies, *v.unverified_dependencies]
    assert not o.release.permitted and any("P1" in u for u in o.release.unresolved)


def test_the_same_words_in_a_primary_text_verify_and_release():
    o = _outcome("doc-src", "Reichsbank")
    assert o.verification is not None and o.verification.status is S.ENTAILED
    assert o.verification.unverified_dependencies == [] and o.verification.ungrounded_dependencies == []
    assert o.release.permitted
