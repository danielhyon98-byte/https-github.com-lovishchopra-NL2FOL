"""Close round 2 of the argument-diagnosis regression review, DIFF-06: the open precision of a trailing-zero whole number for
a count. "The library lent about 400 books" for a stated 380, encoded with real bounds [350, 450) on ``to_real`` of the
count, was AMBIGUOUS_TRANSLATION (``stated_precision``) and not releasable, because the open-precision reading also read
"about 400" at half a unit of its last written digit; the committed base, and the same claim encoded over Int, showed it
ENTAILED. For a count that reading is the exact count, which the approximation word denies, so a term that takes only whole
values is read at its first significant digit alone (``precision._takes_whole_values``). A ratio or a measured quantity
keeps both readings: "about 100%" for a growth of 55% is still never shown entailed.

Wording of this round's own; each positive was checked to fail on the tree before the round."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.precision import _takes_whole_values
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from ..argdiag_hub import CFG, KEY
from ..contract.helpers import make_report

TEXT = "In 2024 the library lent 380 books."


def _count_problem(lo: str, hi: str, *, real: bool, cast: bool = True) -> dict:
    g = {"kind": "quotation", "source_refs": [{"document_id": "doc-lib", "excerpt": "In 2024 the library lent 380 books"}]}
    term = {"op": "to_real", "arg": {"op": "var", "name": "n"}} if cast else {"op": "var", "name": "n"}
    lit = (lambda v: {"op": "real", "value": v}) if real else (lambda v: {"op": "int", "value": v})
    return {"problem": {
        "ir_version": "1.0", "problem_id": "p-lib", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "n", "sort": "Int", "meaning": "books the library lent in 2024 (count)", "grounding": g}],
        "premises": [{"id": "ev1", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": "380"}},
                      "label": "In 2024 the library lent 380 books", "grounding": g}],
        "conclusion": {"id": "concl", "label": "the library lent about 400 books",
                       "expr": {"op": "and", "args": [{"op": "ge", "left": term, "right": lit(lo)}, {"op": "lt", "left": term, "right": lit(hi)}]}}},
        "interpretation": {"reading": "the count at the precision of its first significant digit", "glossary": [], "ambiguity_flags": []},
        "ambiguous": False, "unsupported_reason": None}


def _verify(problem: dict):
    claim, report = make_report("The library lent about 400 books in 2024.", role="quantitative", kind="arithmetic",
                                texts=(("doc-lib", TEXT),), subject="Geography")
    translator = Translator(FixtureTranslationProvider({claim.claim_id: json.dumps(problem)}), config=CFG)
    reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": "faithful", "issues": []}}))
    return verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="t")


def _flags(out) -> list[str]:
    interp = out.translation.interpretation
    return [f.code for f in interp.ambiguity_flags] if interp is not None else []


def test_about_400_for_a_count_of_380_compared_over_reals_is_entailed_and_releasable():
    out = _verify(_count_problem("350", "450", real=True))
    assert "stated_precision" not in _flags(out)
    assert out.display_status is S.ENTAILED and out.release.permitted


def test_control_the_same_count_compared_over_int_is_decided_the_same_way():
    out = _verify(_count_problem("350", "450", real=False, cast=False))
    assert out.display_status is S.ENTAILED and out.release.permitted


@pytest.mark.parametrize("term, symbols, whole", [
    ({"op": "var", "name": "n"}, {"n": "Int"}, True),
    ({"op": "to_real", "arg": {"op": "sub", "left": {"op": "var", "name": "n"}, "right": {"op": "var", "name": "m"}}}, {"n": "Int", "m": "Int"}, True),
    ({"op": "add", "args": [{"op": "var", "name": "n"}, {"op": "int", "value": "2"}]}, {"n": "Int"}, True),
    ({"op": "var", "name": "x"}, {"x": "Real"}, False),
    ({"op": "div", "left": {"op": "to_real", "arg": {"op": "var", "name": "n"}}, "right": {"op": "real", "value": "400"}}, {"n": "Int"}, False),
    ({"op": "add", "args": [{"op": "var", "name": "n"}, {"op": "real", "value": "0.5"}]}, {"n": "Int"}, False),
])
def test_a_term_takes_whole_values_only_when_every_part_of_it_does(term, symbols, whole):
    assert _takes_whole_values(term, {k: SimpleNamespace(sort=v) for k, v in symbols.items()}) is whole


GROWTH = "In 2014 Eastham had 500 shops. In 2024 Eastham had 760 shops."


def _growth_problem(lo: str, hi: str) -> dict:
    g = lambda excerpt: {"kind": "quotation", "source_refs": [{"document_id": "doc-shops", "excerpt": excerpt}]}
    growth = {"op": "div", "left": {"op": "to_real", "arg": {"op": "sub", "left": {"op": "var", "name": "b"}, "right": {"op": "var", "name": "a"}}},
              "right": {"op": "real", "value": "500"}}
    return {"problem": {
        "ir_version": "1.0", "problem_id": "p-shops", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Int", "meaning": "shops in Eastham in 2014 (count)", "grounding": g("In 2014 Eastham had 500 shops")},
                    {"name": "b", "sort": "Int", "meaning": "shops in Eastham in 2024 (count)", "grounding": g("In 2024 Eastham had 760 shops")}],
        "premises": [{"id": "ev1", "expr": {"op": "eq", "left": {"op": "var", "name": "a"}, "right": {"op": "int", "value": "500"}},
                      "label": "In 2014 Eastham had 500 shops", "grounding": g("In 2014 Eastham had 500 shops")},
                     {"id": "ev2", "expr": {"op": "eq", "left": {"op": "var", "name": "b"}, "right": {"op": "int", "value": "760"}},
                      "label": "In 2024 Eastham had 760 shops", "grounding": g("In 2024 Eastham had 760 shops")}],
        "conclusion": {"id": "concl", "label": "the number of shops grew by about 100%",
                       "expr": {"op": "and", "args": [{"op": "ge", "left": growth, "right": {"op": "real", "value": lo}},
                                                      {"op": "lt", "left": growth, "right": {"op": "real", "value": hi}}]}}},
        "interpretation": {"reading": "growth as a fraction of the 2014 count", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
        "unsupported_reason": None}


def test_control_a_ratio_keeps_both_readings_of_its_open_precision():
    # 52% growth claimed as "about 100%": a ratio is no count, so its last-digit reading stays and the claim is never entailed
    claim, report = make_report("The number of shops in Eastham grew by about 100% between 2014 and 2024.", role="quantitative",
                                kind="arithmetic", texts=(("doc-shops", GROWTH),), subject="Geography")
    translator = Translator(FixtureTranslationProvider({claim.claim_id: json.dumps(_growth_problem("0.5", "1.5"))}), config=CFG)
    reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": "faithful", "issues": []}}))
    out = verify_claim(claim, report, translator, reviewer=reviewer, config=CFG, signing_key=KEY, key_id="t")
    assert out.display_status is S.AMBIGUOUS_TRANSLATION and "stated_precision" in _flags(out)
    assert not out.release.permitted
