"""Translation regressions from the round-7 arena fixers' hand-off (owner: core).

* fidelity-1: a quotation grounding was verified when the excerpt held the premise's figure about another quantity (the
  2020 population given to ``p2010``), so a false claim was ENTAILED with every premise established.
* fidelity-2: an approximate whole number ("about 100%") was read at the integer trailing-zero tolerance of its first
  significant digit ([50%, 150%)), so 55% growth was ENTAILED as "about 100%" and the faithful encoding was refused.
* fidelity-3: after a stated-precision rejection, a retry that encoded exactly the stated interval was flagged as a
  weaker claim and shown AMBIGUOUS_TRANSLATION.
* correctness-5: a translation record of an earlier translator release was trusted and its result permitted release.
* security-2: a premise grounded only in a relayed peer specialist's report had full source authority.
* robustness-and-contracts-4: provider output holding a lone surrogate made ``Translator.translate`` raise.
* fidelity-5: a partial encoding the translator's own reading admits ("... is not encoded") was displayed ENTAILED.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.branches import default_registry
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TranslationStatus as T, sha256_text
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.outcome import compose_outcome, translation_staleness, verify_claim
from epinoic_logic.translate.parsing import ProviderOutputError, parse_json_object
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.quantities import _figures, stated_exactness, tolerance_bounds
from epinoic_logic.translate.review import SemanticReviewer

KEY = b"r7-core-translate-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
CID = "g1.1@geography-specialist"


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def R(v):
    return {"op": "real", "value": str(v)}


def q(excerpt: str) -> dict:
    return {"kind": "quotation", "source_refs": [{"document_id": "doc-town", "excerpt": excerpt}], "certainty": "established"}


def geography(task: str, census: str, answer: str):
    """The report the Geography branch parses from ``answer`` with the census as its supplied text, and its first claim."""
    branch, _profile = default_registry().for_subject("Geography")
    texts = [SuppliedText(document_id="doc-town", title="Census", text=census)]
    report = branch.parser().parse_response(answer, request_id=f"req-{task}", task_id=task, report_id=f"rep-{task}", subject="Geography",
                                            task_type="structured_question", supplied_texts=texts, agent_id="geography-specialist")
    claim = next(c for c in report.claims if c.claim_id == CID)
    return claim, report


def output(problem: dict, reading: str = "as stated") -> dict:
    return {"problem": problem, "interpretation": {"reading": reading, "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}


def run(claim, report, *outputs, reviewer=None):
    provider = FixtureTranslationProvider({claim.claim_id: [json.dumps(o) for o in outputs] if len(outputs) > 1 else json.dumps(outputs[0])})
    return verify_claim(claim, report, Translator(provider, config=CFG), reviewer, config=CFG, signing_key=KEY, key_id="k")


# ------------------------------------------------------------------ fidelity-1: a figure of another year grounds nothing


CENSUS_5 = "In 2010 Lowtown had 200 residents. In 2020 Lowtown had 252 residents."


def _same_population(excerpt_2010: str) -> dict:
    return {"ir_version": "1.0", "problem_id": "pr5", "request_id": "req-pr-5", "claim_id": CID, "query": "entailment",
            "symbols": [{"name": "p2010", "sort": "Int", "meaning": "Lowtown residents in 2010 (count)"},
                        {"name": "p2020", "sort": "Int", "meaning": "Lowtown residents in 2020 (count)"}],
            "premises": [{"id": "ev1", "expr": {"op": "eq", "left": V("p2010"), "right": I(252)}, "label": "In 2010 Lowtown had 252 residents", "grounding": q(excerpt_2010)},
                         {"id": "ev2", "expr": {"op": "eq", "left": V("p2020"), "right": I(252)}, "label": "In 2020 Lowtown had 252 residents",
                          "grounding": q("In 2020 Lowtown had 252 residents")}],
            "conclusion": {"id": "concl", "expr": {"op": "eq", "left": V("p2010"), "right": V("p2020")}, "label": "the same number of residents in both years"}}


@pytest.mark.parametrize("excerpt", ["In 2020 Lowtown had 252 residents", "Lowtown had 252 residents"])
def test_a_figure_stated_for_another_year_does_not_ground_the_premise(excerpt):
    problem = Problem.model_validate(_same_population(excerpt))
    checked, checks = check_problem_grounding(problem, [SuppliedText(document_id="doc-town", text=CENSUS_5)])
    ev1 = next(p for p in checked.premises if p.id == "ev1")
    ev2 = next(p for p in checked.premises if p.id == "ev2")
    assert ev1.grounding.verified is False and ev2.grounding.verified is True
    refuted = [c for c in checks if c.target_id == "ev1" and c.method == "figures_in_excerpt"]
    assert refuted and refuted[0].verified is False and "2020" in refuted[0].detail and "2010" in refuted[0].detail


def test_the_false_claim_rests_on_an_ungrounded_premise_and_is_never_released():
    claim, report = geography("pr-5", CENSUS_5, "(a) Lowtown had the same number of residents in 2020 as in 2010: 252 in both years.\n")
    faithful = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": "faithful", "issues": []}}))
    outcome = run(claim, report, output(_same_population("In 2020 Lowtown had 252 residents")), reviewer=faithful)
    assert "ev1" in outcome.verification.ungrounded_dependencies
    assert outcome.release.permitted is False and any("ev1" in u for u in outcome.release.unresolved)


def test_a_figure_of_the_year_the_symbol_names_still_grounds_it():
    problem = Problem.model_validate({**_same_population("In 2010 Lowtown had 200 residents"),
                                      "premises": [{"id": "ev1", "expr": {"op": "eq", "left": V("p2010"), "right": I(200)}, "grounding": q("In 2010 Lowtown had 200 residents")}]})
    checked, _checks = check_problem_grounding(problem, [SuppliedText(document_id="doc-town", text=CENSUS_5)])
    assert checked.premises[0].grounding.verified is True


# ------------------------------------------------------------------ fidelity-2: "about 100%" is read at its last written digit


@pytest.mark.parametrize("text,lo,hi", [("prices rose by about 100%", 99.5, 100.5), ("about 10 times", 9.5, 10.5), ("about 1000 people came", 999.5, 1000.5),
                                        ("grew by about 30%", 29.5, 30.5), ("about 24 people", 23.5, 24.5)])
def test_an_approximate_whole_number_is_read_at_half_a_unit_of_its_last_written_digit(text, lo, hi):
    f = _figures("claim", "c", text)[0]
    bounds = tolerance_bounds(f.value, stated_exactness(f, text))
    assert (float(bounds[0]), float(bounds[1])) == (lo, hi)


def test_a_decimal_keeps_half_a_unit_of_its_last_decimal_place():
    f = _figures("claim", "c", "about 3.5 kg")[0]
    bounds = tolerance_bounds(f.value, stated_exactness(f, "about 3.5 kg"))
    assert (float(bounds[0]), float(bounds[1])) == (3.45, 3.55)


CENSUS_2 = "In 2010 Lowtown had 200 residents. In 2020 Lowtown had 310 residents."
ANSWER_2 = "(a) The population of Lowtown grew by about 100% between 2010 and 2020, so it roughly doubled.\n"


def _growth(lo: str, hi: str) -> dict:
    growth = {"op": "div", "left": {"op": "to_real", "arg": {"op": "sub", "left": V("p2020"), "right": V("p2010")}}, "right": R(200)}
    return {"ir_version": "1.0", "problem_id": "pr2", "request_id": "req-pr-2", "claim_id": CID, "query": "entailment",
            "symbols": [{"name": "p2010", "sort": "Int", "meaning": "Lowtown residents in 2010 (count)"},
                        {"name": "p2020", "sort": "Int", "meaning": "Lowtown residents in 2020 (count)"}],
            "premises": [{"id": "ev1", "expr": {"op": "eq", "left": V("p2010"), "right": I(200)}, "grounding": q("In 2010 Lowtown had 200 residents")},
                         {"id": "ev2", "expr": {"op": "eq", "left": V("p2020"), "right": I(310)}, "grounding": q("In 2020 Lowtown had 310 residents")}],
            "conclusion": {"id": "concl", "expr": {"op": "and", "args": [{"op": "ge", "left": growth, "right": R(lo)}, {"op": "lt", "left": growth, "right": R(hi)}]},
                           "label": "the population grew by about 100%"}}


def test_55_percent_growth_is_not_entailed_as_about_100_percent():
    claim, report = geography("pr-2", CENSUS_2, ANSWER_2)
    wide = run(claim, report, output(_growth("0.5", "1.5")))
    assert wide.display_status is not S.ENTAILED and wide.translation.status is T.INVALID_FORMALIZATION
    assert any("stated precision" in d for d in wide.translation.diagnostics)
    narrow = run(claim, report, output(_growth("0.995", "1.005")))
    assert narrow.translation.status is T.TRANSLATED and narrow.display_status is S.COUNTEREXAMPLE


# ------------------------------------------------------------------ fidelity-3: a retry encoding the stated interval keeps the claim


CENSUS_4 = "In 2020 Lowtown had 300 residents. Of these, 100 were children."
ANSWER_4 = "(a) Children made up 0.33 of the residents of Lowtown in 2020, to 2 decimal places.\n"


def _share(lo: str) -> dict:
    share = {"op": "div", "left": {"op": "to_real", "arg": V("kids")}, "right": R(300)}
    return {"ir_version": "1.0", "problem_id": "pr4", "request_id": "req-pr-4", "claim_id": CID, "query": "entailment",
            "symbols": [{"name": "kids", "sort": "Int", "meaning": "children in Lowtown in 2020 (count)"}],
            "premises": [{"id": "ev2", "expr": {"op": "eq", "left": V("kids"), "right": I(100)}, "grounding": q("Of these, 100 were children")}],
            "conclusion": {"id": "concl", "expr": {"op": "and", "args": [{"op": "ge", "left": share, "right": R(lo)}, {"op": "lt", "left": share, "right": R("0.335")}]},
                           "label": "children made up 0.33 of the residents, to 2 decimal places"}}


def test_a_retry_that_encodes_exactly_the_stated_interval_keeps_the_claim():
    claim, report = geography("pr-4", CENSUS_4, ANSWER_4)
    control = run(claim, report, output(_share("0.325")))
    assert control.display_status is S.ENTAILED
    retried = run(claim, report, output(_share("0.33")), output(_share("0.325")))
    assert retried.display_status is S.ENTAILED and retried.translation.status is T.TRANSLATED
    assert retried.translation.repairs and retried.translation.repairs[0].conclusion == "unchanged"
    first = next(d for d in retried.translation.diagnostics if "stated precision" in d)
    assert "0.33 (the interval's midpoint 0.3325)" in first


# ------------------------------------------------------------------ correctness-5: a record of an earlier release is stale


def test_a_translation_of_an_earlier_translator_release_is_never_displayed_as_a_verdict():
    claim, report = geography("pr-4", CENSUS_4, ANSWER_4)
    faithful = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": "faithful", "issues": []}}))
    current = run(claim, report, output(_share("0.325")), reviewer=faithful)
    assert current.display_status is S.ENTAILED and translation_staleness(current.translation) is None
    old = current.translation.model_copy(update={"translator_version": "0.3.0", "claim_text_sha256": None, "grounding_support": [], "figure_readings": [], "coverage": []})
    assert "0.3.0" in translation_staleness(old)
    result = verify(old.problem, CFG, signing_key=KEY, key_id="k")
    outcome = compose_outcome(claim, old, result, faithful.review(claim, old, report=report), signing_key=KEY, key_id="k", report=report)
    assert outcome.display_status is S.INTERNAL_ERROR and outcome.release.permitted is False
    assert "translate and verify again" in outcome.summary


# ------------------------------------------------------------------ security-2: a peer report is no source


@pytest.mark.parametrize("docid,author,peer", [("peer:maa-e1a", "maths-specialist", True), ("doc-src", "Reichsbank", False)])
def test_a_premise_grounded_only_in_a_peer_report_is_never_established(docid, author, peer):
    text = "The price index rose to 5000, so it exceeded 1000."
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="generic-structured", subject="History", task_type="essay")
    claim = ClaimRecord(**ids, claim_id="k1", claim_text=text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        source_refs=[{"document_id": docid, "excerpt": "the price index rose to 5000"}])
    supplied = [SuppliedText(document_id=docid, author=author, text="Maths specialist report: the price index rose to 5000 by November 1923.")]
    report = SpecialistReport(**ids, original_response=text, response_sha256=sha256_text(text), claims=[claim], supplied_texts=supplied, created_at="2026-10-11T00:00:00Z")
    problem = {"problem_id": "k1-p", "request_id": "r", "claim_id": "k1", "query": "entailment", "symbols": [{"name": "p", "sort": "Int", "meaning": "the price index in November 1923"}],
               "premises": [{"id": "P1", "expr": {"op": "eq", "left": V("p"), "right": I(5000)}, "label": "the price index rose to 5000",
                             "grounding": {"kind": "quotation", "source_refs": [{"document_id": docid, "excerpt": "the price index rose to 5000"}]}}],
               "conclusion": {"id": "C", "expr": {"op": "gt", "left": V("p"), "right": I(1000)}, "label": "it exceeded 1000"}}
    faithful = SemanticReviewer(FixtureReviewProvider({"k1": {"verdict": "faithful", "issues": []}}))
    outcome = verify_claim(claim, report, Translator(FixtureTranslationProvider({"k1": json.dumps(output(problem))})), faithful, config=CFG, signing_key=KEY, key_id="k")
    assert outcome.verification.status is S.ENTAILED
    if peer:
        assert "P1" in outcome.verification.ungrounded_dependencies and outcome.release.permitted is False
        assert any(c.detail and c.detail.startswith("peer_report") and c.verified is None for c in outcome.translation.grounding_checks)
    else:
        assert outcome.verification.ungrounded_dependencies == [] and outcome.release.permitted is True


def test_a_peer_report_validates_no_task_authority():
    peer = SuppliedText(document_id="peer:t1", author="physics-specialist", text="The distance is 120 km.")
    problem = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "d", "sort": "Int", "meaning": "the distance in km"}],
                                      "premises": [{"id": "D", "expr": {"op": "eq", "left": V("d"), "right": I(120)}, "grounding": {"kind": "arithmetic_fact"}}],
                                      "conclusion": {"id": "C", "expr": {"op": "gt", "left": V("d"), "right": I(100)}}})
    checked, _checks = check_problem_grounding(problem, [peer])
    assert checked.premises[0].grounding.verified is not True
    primary = peer.model_copy(update={"document_id": "doc-1", "author": None})
    checked, _checks = check_problem_grounding(problem, [primary])
    assert checked.premises[0].grounding.verified is True


# ------------------------------------------------------------------ robustness-and-contracts-4: a lone surrogate in provider output


@pytest.mark.parametrize("raw", ['{"problem": "\ud83d"}', '{"problem": "\\ud83d"}', '{"\\ud800": 1}', '```json\n{"a": "\\udfff"}\n```'])
def test_provider_output_with_a_lone_surrogate_is_refused_and_never_raises(raw):
    with pytest.raises(ProviderOutputError):
        parse_json_object(raw)


def test_a_surrogate_in_provider_output_is_an_invalid_formalization():
    claim, report = geography("pr-4", CENSUS_4, ANSWER_4)
    outcome = run(claim, report, '{"problem": "\ud83d"}')
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION


# ------------------------------------------------------------------ fidelity-5: a partial encoding is no verdict on the claim


def test_a_reading_that_says_part_of_the_claim_is_not_encoded_is_ambiguous():
    claim, report = geography("pr-4", CENSUS_4, ANSWER_4)
    partial = run(claim, report, output(_share("0.325"), reading="share of children; the comparison with 2010 is an interpretation and is not encoded"))
    assert partial.translation.status is T.AMBIGUOUS_TRANSLATION and partial.display_status is S.AMBIGUOUS_TRANSLATION
    flags = [f.code for f in partial.translation.interpretation.ambiguity_flags]
    assert flags == ["partial_encoding"]
    # control: the same encoding with a reading that leaves nothing out is a verdict
    whole = run(claim, report, output(_share("0.325"), reading="share of children, encoded whole"))
    assert whole.display_status is S.ENTAILED


def test_a_figure_of_the_claim_no_literal_encodes_is_named_in_a_note():
    claim, report = geography("pr-4", CENSUS_4, "(a) Children made up 0.33 of the residents of Lowtown in 2020, to 2 decimal places, against 0.41 before.\n")
    outcome = run(claim, report, output(_share("0.325")))
    assert any(d.startswith("part of the claim only") and "'0.41'" in d for d in outcome.translation.diagnostics)
