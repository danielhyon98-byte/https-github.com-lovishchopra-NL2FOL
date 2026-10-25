"""Stated precision in the translator (``translate/precision.py``): the end-to-end items B22 and the precision half of B16,
and the review findings on approximate whole numbers and on retries after a stated-precision rejection.

* B22: an interval tied to a stated figure only because the figure's stated interval contains it (s7.2 encodes "2.3 ×
  10⁶" as [2,294,000, 2,298,000), narrower than its 2 significant figures state) is rejected when the probe at the stated
  interval changes the verdict; the stated interval itself is accepted.
* B16 (precision half): an interval equal to the stated one except for the closure of one end is accepted when the probe
  at the stated closure gives the same verdict (h1.2), and rejected when it does not.
* A whole number with trailing zeros and a bare approximation word ("about 100%") states its precision openly: half a
  unit of its last written digit or of its first significant digit. Neither reading is forced: an encoding at either is
  accepted, and when the two readings disagree the translation is AMBIGUOUS_TRANSLATION, never a verdict.
* A retry that encodes exactly the interval a stated-precision rejection asked for keeps the claim, and the rejection
  names the figure as written.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from .. import argdiag_cases as C
from ..argdiag_hub import CFG, KEY, run_case
from ..contract.helpers import make_report


@lru_cache(maxsize=None)
def _delivered(case_id: str):
    return run_case(case_id, "text")


def _verify(claim, report, *proposals: dict):
    responses = [json.dumps(p, ensure_ascii=False) for p in proposals]
    translator = Translator(FixtureTranslationProvider({claim.claim_id: responses if len(responses) > 1 else responses[0]}), config=CFG)
    reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": "faithful", "issues": []}}))
    return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="t")


def _precision_rejections(out) -> list[str]:
    return [d for d in out.translation.diagnostics if ": stated precision: " in d]


def _flags(out) -> list[str]:
    interp = out.translation.interpretation
    return [f.code for f in interp.ambiguity_flags] if interp is not None else []


# ----------------------------------------------------------------------------------------------- B22

S72 = "the estimate of 2.3 × 10⁶ J kg⁻¹ comes out higher"


def test_b22_an_interval_narrower_than_the_stated_figure_is_rejected_with_the_stated_bounds():
    out = _delivered("e2e-B22-ph").outcome(S72)
    assert out.display_status is S.INVALID_FORMALIZATION
    text = _precision_rejections(out)[0]                                       # the recorded proposal is served again on the retry
    assert text.startswith("attempt 1: stated precision: ")
    assert "2.3 × 10⁶ J kg⁻¹ in est is encoded as [2294000, 2298000)" in text
    assert "[2250000, 2350000) ('ge' 2250000 and 'lt' 2350000)" in text
    assert "it is ENTAILED as encoded but COUNTEREXAMPLE at the stated interval" in text


def test_b22_the_stated_interval_is_accepted():
    run = _delivered("e2e-B22-ph")
    claim = run.claim(S72)
    proposal = C.proposal_for(C.load_case("e2e-B22-ph"), claim.claim_text, claim.claim_id)
    proposal["problem"]["claim_id"], proposal["problem"]["request_id"] = claim.claim_id, claim.request_id
    [est] = [p for p in proposal["problem"]["premises"] if p["id"] == "est"]
    est["expr"]["args"][0]["right"]["value"], est["expr"]["args"][1]["right"]["value"] = "2250000", "2350000"
    out = _verify(claim, run.report, proposal)
    assert _precision_rejections(out) == [] and out.translation.status.value != "INVALID_FORMALIZATION"
    assert out.verification is not None and out.verification.status is S.COUNTEREXAMPLE   # at 2 s.f. "higher than 2.26" is not established


# ----------------------------------------------------------------------------------------------- B16, precision half

def test_b16_h1_2_the_closure_variant_of_the_stated_interval_is_decided():
    out = _delivered("e2e-B16-hi").outcome("The textbook table shows prices rising fastest in the autumn of 1923")
    assert out.display_status is S.ENTAILED and _precision_rejections(out) == []


SHARE_TEXT = "Milltown had 300 residents in 2021. Of these, 100 were children."


def _share_problem(lo: str, hi: str, *, closed_hi: bool, kids: int = 100, residents: int = 300) -> dict:
    share = {"op": "div", "left": {"op": "to_real", "arg": {"op": "var", "name": "kids"}}, "right": {"op": "real", "value": str(residents)}}
    g = lambda excerpt: {"kind": "quotation", "source_refs": [{"document_id": "doc-mill", "excerpt": excerpt}]}
    return {"problem": {
        "ir_version": "1.0", "problem_id": "p-share", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "kids", "sort": "Int", "meaning": "children in Milltown in 2021 (count)", "grounding": g(f"Of these, {kids} were children")}],
        "premises": [{"id": "ev", "expr": {"op": "eq", "left": {"op": "var", "name": "kids"}, "right": {"op": "int", "value": str(kids)}},
                      "label": f"{kids} were children", "grounding": g(f"Of these, {kids} were children")}],
        "conclusion": {"id": "concl", "label": "children made up 0.33 of the residents, to 2 decimal places",
                       "expr": {"op": "and", "args": [{"op": "ge", "left": share, "right": {"op": "real", "value": lo}},
                                                      {"op": "le" if closed_hi else "lt", "left": share, "right": {"op": "real", "value": hi}}]}}},
        "interpretation": {"reading": "the share at its stated precision", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}


def _share_claim(text: str = SHARE_TEXT):
    return make_report("Children made up 0.33 of the residents of Milltown in 2021, to 2 decimal places.", role="quantitative", kind="arithmetic",
                       texts=(("doc-mill", text),), subject="Geography")


def test_a_closure_variant_that_changes_no_verdict_is_accepted():
    claim, report = _share_claim()
    out = _verify(claim, report, _share_problem("0.325", "0.335", closed_hi=True))
    assert _precision_rejections(out) == [] and out.display_status is S.ENTAILED


def test_a_closure_variant_that_changes_the_verdict_is_rejected():
    # 67 of 200 is exactly 0.335: inside the closed variant, outside the stated [0.325, 0.335)
    claim, report = _share_claim("Milltown had 200 residents in 2021. Of these, 67 were children.")
    out = _verify(claim, report, _share_problem("0.325", "0.335", closed_hi=True, kids=67, residents=200))
    text = _precision_rejections(out)[0]
    assert out.display_status is S.INVALID_FORMALIZATION and "ENTAILED as encoded but COUNTEREXAMPLE at the stated interval" in text


# ----------------------------------------------------------------------------------------------- open precision of a trailing-zero whole number

GROWTH_TEXT = "In 2011 Milltown had 400 residents. In 2021 Milltown had {after} residents."


def _growth_problem(lo: str, hi: str, after: int) -> dict:
    growth = {"op": "div", "left": {"op": "to_real", "arg": {"op": "sub", "left": {"op": "var", "name": "after"}, "right": {"op": "var", "name": "before"}}},
              "right": {"op": "real", "value": "400"}}
    g = lambda excerpt: {"kind": "quotation", "source_refs": [{"document_id": "doc-mill", "excerpt": excerpt}]}
    return {"problem": {
        "ir_version": "1.0", "problem_id": "p-growth", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "before", "sort": "Int", "meaning": "Milltown residents in 2011 (count)", "grounding": g("In 2011 Milltown had 400 residents")},
                    {"name": "after", "sort": "Int", "meaning": "Milltown residents in 2021 (count)", "grounding": g(f"In 2021 Milltown had {after} residents")}],
        "premises": [{"id": "ev1", "expr": {"op": "eq", "left": {"op": "var", "name": "before"}, "right": {"op": "int", "value": "400"}},
                      "label": "In 2011 Milltown had 400 residents", "grounding": g("In 2011 Milltown had 400 residents")},
                     {"id": "ev2", "expr": {"op": "eq", "left": {"op": "var", "name": "after"}, "right": {"op": "int", "value": str(after)}},
                      "label": f"In 2021 Milltown had {after} residents", "grounding": g(f"In 2021 Milltown had {after} residents")}],
        "conclusion": {"id": "concl", "label": "the population grew by about 100%",
                       "expr": {"op": "and", "args": [{"op": "ge", "left": growth, "right": {"op": "real", "value": lo}},
                                                      {"op": "lt", "left": growth, "right": {"op": "real", "value": hi}}]}}},
        "interpretation": {"reading": "growth as a fraction of the 2011 population", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
        "unsupported_reason": None}


def _growth_claim(after: int, figure: str = "100%"):
    return make_report(f"The population of Milltown grew by about {figure} between 2011 and 2021.", role="quantitative", kind="arithmetic",
                       texts=(("doc-mill", GROWTH_TEXT.format(after=after)),), subject="Geography")


@pytest.mark.parametrize("lo, hi", [("0.5", "1.5"), ("0.995", "1.005")])
def test_about_100_percent_for_55_percent_growth_is_never_shown_entailed(lo, hi):
    claim, report = _growth_claim(620)
    out = _verify(claim, report, _growth_problem(lo, hi, 620))
    assert _precision_rejections(out) == []                                  # neither reading is rejected ...
    assert out.display_status is S.AMBIGUOUS_TRANSLATION and "stated_precision" in _flags(out)   # ... and neither is forced
    [flag] = [f for f in out.translation.interpretation.ambiguity_flags if f.code == "stated_precision"]
    assert "half a unit of its last written digit or of its first significant digit" in flag.message


def test_about_100_percent_for_a_doubling_is_decided_at_the_last_written_digit():
    claim, report = _growth_claim(801)
    out = _verify(claim, report, _growth_problem("0.995", "1.005", 801))
    assert _precision_rejections(out) == [] and out.display_status is S.ENTAILED and "stated_precision" not in _flags(out)


def test_a_figure_without_trailing_zeros_keeps_the_one_stated_interval():
    claim, report = _growth_claim(820, figure="105%")
    wide = _verify(claim, report, _growth_problem("0.5", "1.5", 820))
    assert wide.display_status is S.INVALID_FORMALIZATION and _precision_rejections(wide)
    stated = _verify(claim, report, _growth_problem("1.045", "1.055", 820))
    assert _precision_rejections(stated) == [] and stated.display_status is S.ENTAILED


def test_the_recorded_about_30_percent_claim_is_no_longer_refused():
    out = _delivered("e2e-B8-ps").outcome("Your 30% is correct only for the reverse statement")
    assert _precision_rejections(out) == [] and out.translation.status.value != "INVALID_FORMALIZATION"
    assert out.verification is not None and out.verification.status is S.ENTAILED


# ----------------------------------------------------------------------------------------------- the retry after a rejection

def test_a_retry_that_encodes_the_stated_interval_keeps_the_claim():
    claim, report = _share_claim()
    out = _verify(claim, report, _share_problem("0.33", "0.335", closed_hi=False), _share_problem("0.325", "0.335", closed_hi=False))
    [text] = _precision_rejections(out)
    assert text.startswith("attempt 1: stated precision: ") and "0.33 in concl is encoded as [0.33, 0.335)" in text
    assert "0.3325" not in text                                              # the figure as written, never the interval's midpoint
    assert out.display_status is S.ENTAILED and "retry_changed_claim" not in _flags(out)
    [repair] = out.translation.repairs
    assert (repair.kind, repair.conclusion, repair.supported_by_source) == ("semantic", "unchanged", True)


def test_the_stated_interval_alone_is_entailed():
    claim, report = _share_claim()
    out = _verify(claim, report, _share_problem("0.325", "0.335", closed_hi=False))
    assert out.display_status is S.ENTAILED and out.translation.repairs == []


def test_a_retry_that_weakens_the_claim_still_cannot_inherit_its_approval():
    claim, report = _share_claim()
    out = _verify(claim, report, _share_problem("0.33", "0.335", closed_hi=False), _share_problem("0.2", "0.5", closed_hi=False))
    assert out.display_status is not S.ENTAILED
