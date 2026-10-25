"""Regression tests for the translation-side findings of the 12 October 2026 external review (findings 1, 2, 4, 6, 7, 9).

Each section encodes the reviewer's acceptance criteria together with negative controls in which the rejected
conclusion really is wrong:

1. Exactness: the exact 1/3 vs 0.33 claim keeps its counterexample; a genuinely rounded claim uses exactly its stated
   tolerance; contradictory exact facts stay contradictory; a retry that weakens the claim cannot inherit its approval;
   every accepted semantic change is recorded apart from syntax repairs.
2. Premise authority (translation side): a model-chosen trusted kind confers nothing; the substituted 160 is an evidence
   failure and an unresolved dependency while the authentic 120 still supports 15; formal entailment stays separate
   from permission to release.
4. Reviewer context: the review request carries the original task, the supporting claims, the supplied texts, source
   identities and the premise-to-source mapping, bound to them; a changed source or supporting claim makes an earlier
   review stale although the claim text is unchanged; an unresolved fidelity check is unresolved approval.
6. Definitions and unconstrained variables: E110/E111 withhold a counterexample only with source-linked evidence of an
   omitted assertion; a definition or an arbitrary variable keeps its counterexample, with the engine's advisory
   W110/W111; no translator is told to add a premise because it would produce entailment. The coverage note, the signed
   engine result and the display are one decision (the translation layer hands its evidence to the engine as an
   application record on the symbols involved).
7. References: every reference is validated with its own outcome; an unknown second document is surfaced and prevents
   any aggregate label of complete verification.
9. Quantities: 20% read as 0.2 and as 1/5 agree through one recorded derivation; a symbol's declared reading (a
   dimensionless fraction, per cent, a unit) is respected.
"""
from __future__ import annotations

import json
from fractions import Fraction

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.runner import verify as engine_verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Grounding, Problem
from epinoic_logic.translate import prompts
from epinoic_logic.version import TRANSLATOR_VERSION
from epinoic_logic.translate.contracts import (
    ClaimRecord, EligibilityDecision, ProviderInfo, SpecialistReport, SuppliedText, TaskRecord, TranslationResult, TranslationStatus as T, sha256_text,
)
from epinoic_logic.translate.grounding import check_grounding, check_problem_grounding, grounding_support
from epinoic_logic.translate.outcome import assess_release, compose_outcome, display_status_for, verify_claim
from epinoic_logic.translate.pipeline import Translator, widen_rounded_literals
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.providers.rendering import render_review_user_prompt, render_translation_user_prompt
from epinoic_logic.translate.quantities import SourceText, declared_reading, figures_in, literal_matches, stated_exactness
from epinoic_logic.translate.review import SemanticReviewer, review_currency

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"review-2026-10-12-translate-key-0123456789"


def V(n):
    return {"op": "var", "name": n}


def R(v):
    return {"op": "real", "value": str(v)}


def I(v):
    return {"op": "int", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def output(problem, *, reading="read as stated", flags=None):
    return {"problem": problem, "interpretation": {"reading": reading, "glossary": [], "ambiguity_flags": flags or []}, "ambiguous": False,
            "unsupported_reason": None}


def make(claim_text, *, support=(), texts=(), role="quantitative", subject="Mathematics", kind="arithmetic", cid="c"):
    """A claim (with supporting claims ``support``: (id, text) pairs) and its report, with supplied texts ``texts``."""
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject=subject, task_type="calculation")
    supporting = [ClaimRecord(**ids, claim_id=sid, claim_text=stext, claim_role="evidence") for sid, stext in support]
    claim = ClaimRecord(**ids, claim_id=cid, claim_text=claim_text, claim_role=role, proposed_claim_kind=kind, supporting_claim_ids=[s.claim_id for s in supporting])
    body = " ".join([claim_text, *(s.claim_text for s in supporting)])
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, *supporting],
                              supplied_texts=[SuppliedText(document_id=d, text=t) for d, t in texts], created_at="2026-10-12T00:00:00Z")
    return claim, report


def problem(premises, conclusion=None, symbols=(("x", "Real", None),), query="entailment", cid="c"):
    data = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": cid, "query": query,
            "symbols": [{"name": n, "sort": s, **({"meaning": m} if m else {})} for n, s, m in symbols], "premises": premises}
    if conclusion is not None:
        data["conclusion"] = conclusion
    return data


def run(claim, report, responses, *, reviewer=None, task=None, max_attempts=2):
    provider = FixtureTranslationProvider({claim.claim_id: responses})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG, max_attempts=max_attempts), reviewer=reviewer, config=CFG,
                           signing_key=KEY, key_id="k", task=task)
    return outcome, provider


# =========================================================================== 1. exactness and stated precision

EXACT_CLAIM = "If x is exactly 1/3, then x is exactly 0.33, without rounding."
TASK_GROUNDING = {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": "Let x equal exactly 1/3."}]}


def exact_case(conclusion_expr):
    claim, report = make(EXACT_CLAIM, support=[("support", "Let x equal exactly 1/3.")], texts=[("task", "Let x equal exactly 1/3.")])
    p = problem([{"id": "P", "expr": eq(V("x"), R("1/3")), "label": "Let x equal exactly 1/3.", "grounding": TASK_GROUNDING}],
                {"id": "C", "expr": conclusion_expr, "label": "x equals exactly 0.33, without rounding"})
    return claim, report, p


WIDENED = {"op": "and", "args": [{"op": "ge", "left": V("x"), "right": R("0.325")}, {"op": "lt", "left": V("x"), "right": R("0.335")}]}


def test_an_exact_false_claim_keeps_its_counterexample():
    claim, report, p = exact_case(eq(V("x"), R("0.33")))
    outcome, provider = run(claim, report, output(p))
    assert outcome.translation.status is T.TRANSLATED and len(provider.calls) == 1
    assert outcome.display_status is S.COUNTEREXAMPLE
    assert [(a.symbol, a.value) for a in outcome.verification.counterexample.assignments] == [("x", "1/3")]
    assert not any("stated precision" in d for d in outcome.translation.diagnostics)
    reading = next(r for r in outcome.translation.figure_readings if r.literal == "0.33")
    assert reading.exactness == "exact" and reading.source_kind == "claim" and reading.written == "0.33" and reading.encoded_as == "exact_equality"
    assert EXACT_CLAIM[reading.start:reading.end] == "0.33" and reading.cue == "exactly"
    assert outcome.release is not None and not outcome.release.permitted and outcome.release.formal_status is S.COUNTEREXAMPLE


def test_widening_an_exact_figure_is_rejected_as_a_weakening_and_never_entailed():
    claim, report, p = exact_case(WIDENED)
    assert engine_verify(Problem.model_validate(p), CFG).status is S.ENTAILED  # the weakened encoding would prove
    outcome, provider = run(claim, report, output(p))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION
    assert any("exactness" in d and "0.33" in d for d in outcome.translation.diagnostics)
    assert len(provider.calls) == 2 and any("exactness" in d for d in provider.calls[1].prior_diagnostics)
    assert outcome.verification is None


def test_the_reviewers_probe_retry_that_follows_the_old_widening_advice_no_longer_earns_entailed():
    """The provider's second answer is the widened encoding the old retry advice asked for. The exact first answer is
    now accepted (the wording states exactness), so the widened one is never needed; served alone after a syntax
    failure it is rejected as a weakening."""
    claim, report, p = exact_case(eq(V("x"), R("0.33")))
    widened = Problem.model_validate(p)
    widened, rounded = widen_rounded_literals(widened)
    assert rounded == ["0.33"]
    outcome, provider = run(claim, report, [output(p), output(widened.model_dump(mode="json", exclude_none=True))])
    assert outcome.display_status is S.COUNTEREXAMPLE and len(provider.calls) == 1
    outcome, provider = run(claim, report, ["not json", output(widened.model_dump(mode="json", exclude_none=True))])
    assert outcome.display_status is S.INVALID_FORMALIZATION and outcome.translation.status is T.INVALID_FORMALIZATION
    assert outcome.display_status is not S.ENTAILED


def test_contradictory_exact_facts_stay_contradictory_and_a_rounded_fact_does_not():
    text = "Constraint 1: x equals exactly 0.5. Constraint 2: x equals exactly 51/100."
    claim, report = make("The two exact constraints x = 0.5 and x = 51/100 are consistent.", support=[("support", text)], texts=[("task2", text)])
    p = problem([{"id": "P1", "expr": eq(V("x"), R("0.5")), "label": "x equals exactly 0.5"},
                 {"id": "P2", "expr": eq(V("x"), R("51/100")), "label": "x equals exactly 51/100"}], query="consistency")
    outcome, _ = run(claim, report, output(p))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.INCONSISTENT_PREMISES
    assert not any("stated precision" in d for d in outcome.translation.diagnostics)
    # negative control: the same figures where the source states the first one as rounded are consistent at its precision
    text = "Constraint 1: x is 0.5 to 1 decimal place. Constraint 2: x equals exactly 51/100."
    claim, report = make("The two constraints x ≈ 0.5 and x = 51/100 are consistent.", support=[("support", text)], texts=[("task2", text)])
    outcome, provider = run(claim, report, output(p))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("stated precision" in d for d in outcome.translation.diagnostics)
    assert "0.45" in provider.calls[1].prior_diagnostics[0] and "0.55" in provider.calls[1].prior_diagnostics[0]


def test_an_exact_fact_widened_over_two_premises_is_rejected_and_its_contradiction_is_not_hidden():
    text = "Constraint 1: x equals exactly 0.5. Constraint 2: x equals exactly 51/100."
    claim, report = make("The two exact constraints x = 0.5 and x = 51/100 are consistent.", support=[("support", text)], texts=[("task2", text)])
    split = problem([{"id": "P1a", "expr": {"op": "ge", "left": V("x"), "right": R("0.45")}}, {"id": "P1b", "expr": {"op": "lt", "left": V("x"), "right": R("0.55")}},
                     {"id": "P2", "expr": eq(V("x"), R("51/100"))}], query="consistency")
    assert engine_verify(Problem.model_validate(split), CFG).status is S.CONSISTENT  # the widening would hide the contradiction
    outcome, _ = run(claim, report, output(split))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("exactness" in d and "P1a+P1b" in d for d in outcome.translation.diagnostics)
    assert outcome.display_status is not S.CONSISTENT


def growth_problem(conclusion, meaning, numerator="8.43", denominator="7.03"):
    ratio = {"op": "sub", "left": {"op": "div", "left": R(numerator), "right": R(denominator)}, "right": R("1")}
    return problem([{"id": "G", "expr": eq(V("g"), {"op": "mul", "args": [ratio, R("100" if "per cent" in meaning else "1")]})}],
                   {"id": "C", "expr": conclusion}, symbols=(("g", "Real", meaning),))


def interval(name, lo, hi):
    return {"op": "and", "args": [{"op": "ge", "left": V(name), "right": R(lo)}, {"op": "lt", "left": V(name), "right": R(hi)}]}


@pytest.mark.parametrize("lo,hi,meaning,ok", [
    ("0.19905", "0.19915", "growth as a dimensionless fraction", True),   # 19.91% read at its stated precision, as a fraction
    ("19.905", "19.915", "growth in per cent", True),                     # the same, in per cent
    ("0.19", "0.21", "growth as a dimensionless fraction", False),        # wider than the stated precision
])
def test_a_percentage_read_at_its_stated_precision_in_either_unit(lo, hi, meaning, ok):
    # (8.43 / 7.03 - 1) x 100 = 19.9146...: the written result 19.91% rounds it to half a unit of its last place
    claim, report = make("Growth = (8.43 ÷ 7.03 − 1) × 100 = 19.91%.", subject="Economics")
    outcome, _ = run(claim, report, output(growth_problem(interval("g", lo, hi), meaning)))
    if ok:
        assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
        reading = next(r for r in outcome.translation.figure_readings if r.encoded_as == "interval")
        assert reading.exactness == "rounded" and (reading.lower, reading.upper) == (lo, hi)
        assert reading.calculated == "14000/703" and reading.by_convention is False  # the rounding is confirmed by the calculation as written
    else:
        assert outcome.translation.status is T.INVALID_FORMALIZATION and any("stated precision" in d for d in outcome.translation.diagnostics)


@pytest.mark.parametrize("meaning,literal", [("growth as a dimensionless fraction", "0.2"), ("growth in per cent", "20")])
def test_a_percentage_a_written_calculation_gives_exactly_is_exact_in_either_unit(meaning, literal):
    """(8.40 / 7.00 - 1) x 100 = 20 exactly: 20.00% is no rounded figure, so an interval in its place weakens the claim."""
    claim, report = make("Growth = (8.40 ÷ 7.00 − 1) × 100 = 20.00%.", subject="Economics")
    outcome, _ = run(claim, report, output(growth_problem(eq(V("g"), R(literal)), meaning, "8.40", "7.00")))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    [reading] = [r for r in outcome.translation.figure_readings if r.literal == literal]
    assert reading.exactness == "exact" and reading.calculated == "20" and reading.precision is None and reading.by_convention is False
    half = "0.00005" if literal == "0.2" else "0.005"
    lo, hi = (str(Fraction(literal) - Fraction(half)), str(Fraction(literal) + Fraction(half)))
    widened = growth_problem(interval("g", decimal(lo), decimal(hi)), meaning, "8.40", "7.00")
    outcome, _ = run(claim, report, output(widened))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("exactness" in d and "gives exactly this value" in d for d in outcome.translation.diagnostics)


def decimal(fraction_text):
    from decimal import Decimal
    f = Fraction(fraction_text)
    return format(Decimal(f.numerator) / Decimal(f.denominator), "f")


def test_a_domain_constraint_is_no_reading_of_an_exact_figure():
    claim, report = make("The share is exactly 0.5.", texts=[("doc", "The share is exactly 0.5.")])
    p = problem([{"id": "LO", "expr": {"op": "ge", "left": V("x"), "right": R("0")}}, {"id": "HI", "expr": {"op": "le", "left": V("x"), "right": R("1")}},
                 {"id": "S", "expr": eq(V("x"), R("0.5")), "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "The share is exactly 0.5."}]}}],
                {"id": "C", "expr": eq(V("x"), R("0.5"))})
    outcome, _ = run(claim, report, output(p))
    assert not any("exactness" in d for d in outcome.translation.diagnostics)
    assert outcome.translation.status is T.TRANSLATED


ROUNDED_CLAIM = "Since x = 1/3, x ≈ 0.33 to 2 decimal places."


def rounded_case(conclusion_expr):
    claim, report = make(ROUNDED_CLAIM, support=[("support", "Let x equal exactly 1/3.")], texts=[("task", "Let x equal exactly 1/3.")])
    p = problem([{"id": "P", "expr": eq(V("x"), R("1/3")), "label": "x is 1/3", "grounding": TASK_GROUNDING}],
                {"id": "C", "expr": conclusion_expr, "label": "x is 0.33 to 2 decimal places"})
    return claim, report, p


def test_a_genuinely_rounded_claim_uses_its_stated_tolerance_and_the_change_is_recorded():
    claim, report, exact = rounded_case(eq(V("x"), R("0.33")))
    _, _, stated = rounded_case(WIDENED)
    outcome, provider = run(claim, report, [output(exact), output(stated)])
    assert any("stated precision" in d and "'ge' 0.325 and 'lt' 0.335" in d for d in provider.calls[1].prior_diagnostics)
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    reading = next(r for r in outcome.translation.figure_readings if r.encoded_as == "interval")
    assert reading.exactness == "rounded" and (reading.lower, reading.upper) == ("0.325", "0.335") and reading.precision == "2 decimal places"
    [repair] = outcome.translation.repairs
    # the retry's conclusion is exactly the earlier conclusion read at the precision its source states
    assert repair.kind == "semantic" and repair.rejected_for == ["stated_precision"] and repair.conclusion == "unchanged" and repair.supported_by_source
    assert any("read at its stated precision" in c for c in repair.changes)
    # a syntax repair is recorded as such, apart from semantic changes
    outcome, _ = run(claim, report, ["not json", output(stated)])
    assert [(r.kind, r.conclusion) for r in outcome.translation.repairs] == [("syntax", "not_compared")]


def test_an_interval_wider_than_the_stated_precision_is_rejected():
    loose = {"op": "and", "args": [{"op": "ge", "left": V("x"), "right": R("0.3")}, {"op": "lt", "left": V("x"), "right": R("0.4")}]}
    claim, report, p = rounded_case(loose)
    outcome, _ = run(claim, report, output(p))
    assert outcome.translation.status is T.INVALID_FORMALIZATION
    assert any("stated precision" in d and "[0.3, 0.4)" in d and "[0.325, 0.335)" in d for d in outcome.translation.diagnostics)


def test_a_wrong_rounded_claim_still_fails_at_its_stated_precision():
    claim, report = make("Since x = 1/3, x ≈ 0.34 to 2 decimal places.", support=[("support", "Let x equal exactly 1/3.")], texts=[("task", "Let x equal exactly 1/3.")])
    p = problem([{"id": "P", "expr": eq(V("x"), R("1/3")), "grounding": TASK_GROUNDING}], {"id": "C", "expr": eq(V("x"), R("0.34"))})
    outcome, provider = run(claim, report, output(p))
    assert outcome.translation.status is T.TRANSLATED and len(provider.calls) == 1  # its precision does not change the verdict
    assert outcome.display_status is S.COUNTEREXAMPLE


def test_an_unstated_decimal_whose_reading_decides_the_verdict_is_ambiguous_not_a_verdict():
    claim, report = make("Since x = 1/3, x = 0.33.", support=[("support", "Let x equal exactly 1/3.")], texts=[("task", "Let x equal exactly 1/3.")])
    p = problem([{"id": "P", "expr": eq(V("x"), R("1/3")), "grounding": TASK_GROUNDING}], {"id": "C", "expr": eq(V("x"), R("0.33"))})
    outcome, provider = run(claim, report, output(p))
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and len(provider.calls) == 1
    assert outcome.display_status is S.AMBIGUOUS_TRANSLATION and outcome.display_status not in (S.ENTAILED, S.COUNTEREXAMPLE)
    flag = next(f for f in outcome.translation.interpretation.ambiguity_flags if f.code == "stated_precision")
    assert "COUNTEREXAMPLE" in flag.message and "ENTAILED" in flag.message


def test_a_given_task_figure_is_never_widened():
    text = "The price is $1.60 per litre."
    claim, report = make("At $1.60 per litre, 10 litres cost $16.", texts=[("doc", text)])
    p = problem([{"id": "T", "expr": eq(V("p"), R("1.60")), "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": text}]}}],
                {"id": "C", "expr": eq({"op": "mul", "args": [V("p"), R("10")]}, R("16"))}, symbols=(("p", "Real", "price in dollars per litre"),))
    outcome, _ = run(claim, report, output(p))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    widened = {"op": "and", "args": [{"op": "ge", "left": V("p"), "right": R("1.595")}, {"op": "lt", "left": V("p"), "right": R("1.605")}]}
    p["premises"][0]["expr"] = widened
    outcome, _ = run(claim, report, output(p))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("exactness" in d for d in outcome.translation.diagnostics)


def test_a_retry_that_weakens_the_conclusion_does_not_inherit_the_claims_approval():
    claim, report = make("x exceeds 5 and y exceeds 3.", texts=[("doc", "x is 9 and y is 4.")])
    facts = [{"id": "X", "expr": eq(V("x"), I(9)), "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "x is 9"}]}},
             {"id": "Y", "expr": eq(V("y"), I(4)), "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "y is 4"}]}}]
    both = {"op": "and", "args": [{"op": "gt", "left": V("x"), "right": I(5)}, {"op": "gt", "left": V("y"), "right": I(3)}]}
    circular = problem([*facts, {"id": "A", "expr": both, "grounding": {"kind": "assumption"}}], {"id": "C", "expr": both},
                       symbols=(("x", "Int", None), ("y", "Int", None)))
    weaker = problem(facts, {"id": "C", "expr": {"op": "gt", "left": V("x"), "right": I(5)}}, symbols=(("x", "Int", None), ("y", "Int", None)))
    kept = problem(facts, {"id": "C", "expr": both}, symbols=(("x", "Int", None), ("y", "Int", None)))
    outcome, provider = run(claim, report, [output(circular), output(weaker)])
    assert any("E112" in d for d in provider.calls[1].prior_diagnostics)
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.display_status is S.AMBIGUOUS_TRANSLATION
    assert outcome.verification.status is S.ENTAILED  # the weakened encoding would prove: it is not shown as the claim's verdict
    [repair] = outcome.translation.repairs
    assert repair.kind == "semantic" and repair.conclusion == "weaker" and not repair.supported_by_source
    assert any(f.code == "retry_changed_claim" for f in outcome.translation.interpretation.ambiguity_flags)
    assert not outcome.release.permitted and any("retry changed the claim" in u for u in outcome.release.unresolved)
    # a form failure between the rejection for meaning and the accepted attempt does not let the weakening through
    outcome, _ = run(claim, report, [output(circular), "not json", output(weaker)], max_attempts=3)
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.translation.repairs[0].after_attempt == 1
    # control: the retry that keeps the claim and fixes only what was named is a translation of the claim
    outcome, _ = run(claim, report, [output(circular), output(kept)])
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    [repair] = outcome.translation.repairs
    assert repair.conclusion == "unchanged" and any("premise A removed" in c for c in repair.changes)


PRICE_PROOF = problem([{"id": "P", "expr": eq(V("p"), R("1.60"))}], {"id": "C", "expr": eq({"op": "mul", "args": [V("p"), R("100")]}, R("160"))},
                      symbols=(("p", "Real", None),))


def test_a_written_calculation_that_gives_its_result_exactly_states_it_exactly():
    """1.90 - 0.30 = 1.60 exactly: the result is no rounded figure. Its proof stands with the figure read exactly, and an
    interval in its place is rejected as a weakening (never the source of a pass)."""
    claim, report = make("The price paid is 1.90 − 0.30 = 1.60, so 100 litres cost 160.")
    outcome, provider = run(claim, report, output(PRICE_PROOF))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED and len(provider.calls) == 1
    [reading] = [r for r in outcome.translation.figure_readings if r.literal == "1.60"]
    assert reading.exactness == "exact" and reading.calculated == "8/5"
    widened = problem([{"id": "P", "expr": interval("p", "1.595", "1.605")}], PRICE_PROOF["conclusion"], symbols=(("p", "Real", None),))
    outcome, _ = run(claim, report, output(widened))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("exactness" in d for d in outcome.translation.diagnostics)
    # negative control: a false conclusion from the exact calculation keeps its counterexample
    wrong = problem([{"id": "P", "expr": eq(V("p"), R("1.60"))}], {"id": "C", "expr": eq({"op": "mul", "args": [V("p"), R("100")]}, R("161"))},
                    symbols=(("p", "Real", None),))
    claim, report = make("The price paid is 1.90 − 0.30 = 1.60, so 100 litres cost 161.")
    outcome, _ = run(claim, report, output(wrong))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE


def test_a_written_calculation_its_result_rounds_is_rounded_and_a_proof_that_needs_it_exactly_is_rejected():
    """100 / 3 = 33.33 is rounded (the calculation gives 33.333...): a proof that three shares total 99.99 rests on
    reading the rounded figure exactly, so it is rejected; read at its stated precision the claim's counterexample is the
    verdict (three shares total 100)."""
    claim, report = make("The share is 100 ÷ 3 = 33.33, so three shares total 99.99.")
    exact_share = problem([{"id": "S", "expr": eq(V("s"), R("33.33"))}, {"id": "T", "expr": eq(V("t"), {"op": "mul", "args": [R("3"), V("s")]})}],
                          {"id": "C", "expr": eq(V("t"), R("99.99"))}, symbols=(("s", "Real", None), ("t", "Real", None)))
    assert engine_verify(Problem.model_validate(exact_share), CFG).status is S.ENTAILED  # the proof as encoded
    outcome, _ = run(claim, report, output(exact_share))
    assert outcome.translation.status is T.INVALID_FORMALIZATION
    assert any("stated precision" in d and "gives 100/3" in d for d in outcome.translation.diagnostics)
    stated = problem([{"id": "S", "expr": interval("s", "33.325", "33.335")}, {"id": "T", "expr": eq(V("t"), {"op": "mul", "args": [R("3"), V("s")]})}],
                     {"id": "C", "expr": eq(V("t"), R("99.99"))}, symbols=(("s", "Real", None), ("t", "Real", None)))
    outcome, _ = run(claim, report, [output(exact_share), output(stated)])
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE
    assert outcome.translation.repairs[0].kind == "semantic" and outcome.translation.repairs[0].conclusion == "unchanged"


def test_the_calculation_convention_explains_a_failure_but_never_refutes_a_proof_on_its_own():
    """A result written after a calculation the reader cannot compute (a power, a root) is presumed rounded. The
    presumption may explain a failure (an exact reading that is inconsistent while the stated one is not), but a proof
    that needs the written result exactly is not shown as verified (ambiguous), since the result may be exact; an
    explicit rounding cue refutes such a proof and an exactness cue keeps it."""
    claim, report = make("The price paid is 2³ × 0.2 = 1.60, so 100 litres cost 160.")
    outcome, provider = run(claim, report, output(PRICE_PROOF))
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and len(provider.calls) == 1  # the proof needs 1.60 exactly
    flag = next(f for f in outcome.translation.interpretation.ambiguity_flags if f.code == "stated_precision")
    assert "result of a calculation" in flag.message and outcome.display_status is not S.ENTAILED
    [reading] = [r for r in outcome.translation.figure_readings if r.literal == "1.60"]
    assert reading.exactness == "rounded" and reading.by_convention is True and reading.calculated is None
    # the presumption explains a failure: 2.67 read exactly contradicts r x 3 = 8, read to its last place it does not
    claim, report = make("The rate is 2³ ÷ 3 = 2.67, which exceeds 2.6.")
    rate = problem([{"id": "R3", "expr": eq({"op": "mul", "args": [V("r"), R("3")]}, R("8"))}, {"id": "R", "expr": eq(V("r"), R("2.67"))}],
                   {"id": "C", "expr": {"op": "gt", "left": V("r"), "right": R("2.6")}}, symbols=(("r", "Real", None),))
    assert engine_verify(Problem.model_validate(rate), CFG).status is S.INCONSISTENT_PREMISES
    outcome, _ = run(claim, report, output(rate))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("stated precision" in d for d in outcome.translation.diagnostics)
    # with an explicit rounding cue the proof that needs 1.60 exactly is rejected for its stated precision
    claim, report = make("The price paid is about 1.60, so 100 litres cost 160.")
    outcome, _ = run(claim, report, output(PRICE_PROOF))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("stated precision" in d for d in outcome.translation.diagnostics)
    # stated exactly, the proof stands
    claim, report = make("The price paid is exactly 1.60, so 100 litres cost 160.")
    outcome, _ = run(claim, report, output(PRICE_PROOF))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED


def test_the_r7_calculation_results_are_read_as_rounded_by_the_convention_of_written_calculation():
    text = "PED = −12.50 ÷ 18.75 = −0.67"
    figures = {f.written: stated_exactness(f, text) for f in figures_in(SourceText("claim", "g2.1", text))}
    # the rounding is now confirmed by the calculation as written (-2/3), no longer only presumed
    assert figures["−0.67"].kind == "rounded" and figures["−0.67"].half_width == Fraction(1, 200)
    assert figures["−0.67"].computed == Fraction(-2, 3) and not figures["−0.67"].by_convention
    assert figures["−12.50"].kind == "unstated"
    exact = "x is exactly 0.33, without rounding"
    assert {f.written: stated_exactness(f, exact).kind for f in figures_in(SourceText("claim", "c", exact))} == {"0.33": "exact"}
    # a calculation the reader cannot compute stays a presumption of the convention
    root = "So √2 × 3 = 4.24"
    ex = {f.written: stated_exactness(f, root) for f in figures_in(SourceText("claim", "c", root))}["4.24"]
    assert ex.kind == "rounded" and ex.by_convention and ex.computed is None and ex.half_width == Fraction(1, 200)
    # an arithmetic slip (1.90 - 0.30 = 1.61) is recorded, and the figure is neither exact nor confirmed rounded
    slip = "So 1.90 − 0.30 = 1.61 here"
    ex = {f.written: stated_exactness(f, slip) for f in figures_in(SourceText("claim", "c", slip))}["1.61"]
    assert ex.kind == "rounded" and ex.by_convention and ex.computed == Fraction(8, 5) and "does not round" in ex.describe()


@pytest.mark.parametrize("left,value", [
    (" $1.90 − $0.40 ", Fraction(3, 2)),                     # currency marks
    (" shelf price $1.60 + $0.40 ", Fraction(2)),             # prose before the calculation
    (" 1,200 ÷ 4,200 × 100 ", Fraction(200, 7)),             # thousands commas
    (" 15 million litres × (1 − 0.1675) ", Fraction(12487500)),  # a scale word and a unit word
    ("−12.50 ÷ 18.75 ", Fraction(-2, 3)),                    # a leading minus sign
    ("120 km ÷ 1.5 h ", Fraction(80)),                       # unit words dropped
    ("1.6 x 100 ", Fraction(160)),                           # x between operands
    ("20% × 50 ", Fraction(10)),                             # a per cent sign
    ("In 2025 output 4,200 − 3,000 ", Fraction(1200)),       # the tail after prose that holds a year
    ("costs 3 more than 2 + 1 ", Fraction(3)),
])
def test_the_closed_calculation_reader_computes_written_arithmetic(left, value):
    from epinoic_logic.translate.quantities import written_calculation_value
    assert written_calculation_value(left) == value


@pytest.mark.parametrize("left", [
    "v2 − 0.5 ",        # glued to an identifier
    "√2 × 3 ",          # a root it does not read
    "2^10 ",            # a power it does not read
    "2(3 + 4) ",        # implicit multiplication: no tail is cut from the numeral it is glued to
    "1 ÷ 0 ",           # division by zero
    "3 ",               # one numeral is no calculation
    "1 + 2) × 3 ",      # unbalanced
    "1,2345 + 1 ",      # a malformed thousands group
    "3x + 2 ",          # a letter glued to a numeral is a variable: an equation, not a calculation
    "x " * 400,         # too long
    "(" * 40 + "1 + 1" + ")" * 40,  # too deep
])
def test_the_closed_calculation_reader_declines_what_it_does_not_read(left):
    from epinoic_logic.translate.quantities import written_calculation_value
    assert written_calculation_value(left) is None


# =========================================================================== 2. premise authority (translation side)

DOC = "Distance 120 km over 8 hours."
#: The same supplied text stating the relation itself as a given (repair 2 of the integration: only a record that states a
#: relation verifies it; its figures occurring in a record never do).
DOC_STATED = "Distance 120 km over 8 hours. Use speed = d / 8."


def speed_case(distance, speed, *, doc=DOC):
    claim, report = make(f"The speed is {speed} km/h.", support=[("support", DOC)], texts=[("doc", doc)], subject="Physics")
    p = problem([{"id": "D", "expr": eq(V("d"), R(distance)), "label": f"Distance is {distance} km", "grounding": {"kind": "arithmetic_fact"}},
                 {"id": "SPEED", "expr": eq(V("speed"), {"op": "div", "left": V("d"), "right": R(8)}), "grounding": {"kind": "arithmetic_fact"}}],
                {"id": "C", "expr": eq(V("speed"), R(speed))}, symbols=(("d", "Real", None), ("speed", "Real", None)))
    return claim, report, p


@pytest.mark.parametrize("kind", ["arithmetic_fact", "task_setting", "rubric_rule"])
def test_a_substituted_figure_under_any_trusted_kind_is_an_evidence_failure_and_an_unresolved_dependency(kind):
    claim, report, p = speed_case(160, 20)
    for premise in p["premises"]:
        premise["grounding"] = {"kind": kind}
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}}))
    outcome, _ = run(claim, report, output(p), reviewer=reviewer)
    assert outcome.display_status is S.ENTAILED  # formal entailment of the encoding, reported as such
    assert "D" in outcome.verification.ungrounded_dependencies
    failed = [c for c in outcome.translation.grounding_checks if c.target_id == "D" and c.verified is False]
    assert failed and failed[0].method == "numeric_in_task" and "160" in failed[0].detail and "doc" in failed[0].detail
    assert outcome.release is not None and not outcome.release.permitted and not outcome.release.evidence_resolved
    assert any("ungrounded dependencies" in u and "D" in u for u in outcome.release.unresolved)
    assert "Release (release-v2): NOT permitted" in outcome.summary  # the policy pin moves with each release (argdiag-1: release-v2)


def test_the_authentic_120_still_supports_15_and_release_needs_a_faithful_current_review():
    """The authentic 120 still entails 15, its distance established by the supplied text. Rewritten to a stricter rule
    (repair 2 of the integration, verifier finding 2): the relation speed = d / 8 is the translation's own, and the 8 of
    "120 km over 8 hours" occurring in the text is no evidence for it (it was what let an invented speed = d * 8 pass), so
    no check establishes it: it is an unverified dependency and release stays refused even with a faithful review. With
    the relation stated by the supplied text every relied-on premise is established, and release then needs a faithful,
    current review exactly as before."""
    claim, report, p = speed_case(120, 15)
    faithful = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}}))
    outcome, _ = run(claim, report, output(p), reviewer=faithful)
    assert outcome.display_status is S.ENTAILED
    assert outcome.verification.ungrounded_dependencies == [] and outcome.verification.unverified_dependencies == ["SPEED"]
    checks = {(c.target_id, c.method): c for c in outcome.translation.grounding_checks}
    assert checks[("D", "numeric_in_task")].verified is True and "120 km" in checks[("D", "numeric_in_task")].detail
    relation = checks[("SPEED", "relation_in_source")]
    assert relation.verified is None and "no record states the premise's relation" in relation.detail and "8 hours" in relation.detail
    assert not any(c.target_id == "SPEED" and c.verified is True for c in outcome.translation.grounding_checks)
    assert not outcome.release.permitted and not outcome.release.evidence_resolved and outcome.release.fidelity == "faithful"
    assert any("SPEED" in u for u in outcome.release.unresolved)
    assert "Unverified relations" in outcome.summary
    # the relation stated by the supplied text: every premise established, and release needs a faithful current review
    claim, report, p = speed_case(120, 15, doc=DOC_STATED)
    outcome, _ = run(claim, report, output(p))
    assert outcome.display_status is S.ENTAILED
    assert outcome.verification.ungrounded_dependencies == [] and outcome.verification.unverified_dependencies == []
    checks = {(c.target_id, c.method): c for c in outcome.translation.grounding_checks}
    assert checks[("D", "numeric_in_task")].verified is True and "120 km" in checks[("D", "numeric_in_task")].detail
    assert checks[("SPEED", "relation_in_source")].verified is True and "'speed = d / 8'" in checks[("SPEED", "relation_in_source")].detail
    assert outcome.release.evidence_resolved and not outcome.release.permitted and outcome.release.fidelity == "missing"
    outcome, _ = run(claim, report, output(p), reviewer=faithful)
    assert outcome.release.permitted and outcome.release.fidelity == "faithful" and outcome.release.unresolved == []
    uncertain = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "uncertain", "issues": ["vague"]}}))
    outcome, _ = run(claim, report, output(p), reviewer=uncertain)
    assert not outcome.release.permitted and outcome.display_status is S.ENTAILED  # the review never changes the formal status


def test_a_trusted_kind_stays_unchecked_until_a_record_validates_it():
    """Without the task record the limit and the count are unvalidated (never trusted: release is blocked and the summary
    says so); the task record validates the limit and refutes the paragraph's own count as a task fact."""
    claim, report = make("The paragraph runs to 320 words, under the 350-word limit.", role="structural", subject="English A: Literature")
    p = problem([{"id": "W", "expr": eq(V("words"), I(320)), "grounding": {"kind": "arithmetic_fact"}},
                 {"id": "L", "expr": eq(V("limit"), I(350)), "grounding": {"kind": "task_setting"}}],
                {"id": "C", "expr": {"op": "le", "left": V("words"), "right": V("limit")}}, symbols=(("words", "Int", None), ("limit", "Int", None)))
    faithful = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}}))
    outcome, _ = run(claim, report, output(p), reviewer=faithful)
    unvalidated = {c.target_id for c in outcome.translation.grounding_checks if c.method == "numeric_in_task" and c.verified is None}
    assert unvalidated == {"L", "W"} and outcome.display_status is S.ENTAILED
    # integration of the review fixes: the signed engine result lists exactly what the translation layer left unvalidated
    assert outcome.verification.unverified_dependencies == ["W", "L"] and outcome.verification.ungrounded_dependencies == []
    assert not outcome.release.permitted and any("task authority unvalidated" in u and "L, W" in u for u in outcome.release.unresolved)
    assert "Unvalidated task authority" in outcome.summary
    task = TaskRecord.of("t", "r", "Write an analytical paragraph of at most 350 words.")
    outcome, provider = run(claim, report, output(p), task=task, reviewer=faithful)
    assert outcome.verification.ungrounded_dependencies == ["W"]  # the task states the limit; the paragraph's own count is not a task fact
    assert outcome.verification.unverified_dependencies == []    # the validated limit is established, in the signed result too
    assert not outcome.release.permitted
    assert outcome.translation.task_sha256 == task.text_sha256
    assert "<<<DATA task>>>" in render_translation_user_prompt(provider.calls[0])
    with pytest.raises(ValueError, match="task record"):
        Translator(FixtureTranslationProvider({})).translate(claim, report, task=TaskRecord.of("other", "r", "x"))


def test_a_restated_trusted_kind_is_a_transcription_only_when_the_task_states_it():
    claim, report = make("The limit is 350 words.", role="structural", subject="English A: Literature")
    p = problem([{"id": "L", "expr": eq(V("limit"), I(350)), "grounding": {"kind": "task_setting"}}], {"id": "C", "expr": eq(V("limit"), I(350))},
                symbols=(("limit", "Int", None),))
    outcome, _ = run(claim, report, output(p), task=TaskRecord.of("t", "r", "Keep the answer within 350 words."))
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED  # a transcription of the task
    outcome, _ = run(claim, report, output(p), task=TaskRecord.of("t", "r", "Keep the answer within 400 words."))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and any("E112" in d for d in outcome.translation.diagnostics)  # assumed, not given
    # Rewritten to the stricter rule of policy 2026.10-v5 (issue 1): with no task record no check validated the restating
    # premise, so it is the writer's own and the restatement is circular (refused, E112), never shown as ENTAILED. Before,
    # the label alone made it a transcription, displayed ENTAILED and only kept from release.
    outcome, _ = run(claim, report, output(p))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is not S.ENTAILED
    assert any("E112" in d for d in outcome.translation.diagnostics) and not outcome.release.permitted


# =========================================================================== 4. reviewer context and binding


def test_the_review_request_carries_the_evidence_and_the_review_is_bound_to_it():
    claim, report, p = speed_case(160, 20)
    review_provider = FixtureReviewProvider({"c": {"verdict": "uncertain", "issues": []}})
    task = TaskRecord.of("t", "r", "A car travels 120 km in 8 hours. Find its speed.")
    outcome, _ = run(claim, report, output(p), reviewer=SemanticReviewer(review_provider), task=task)
    [request] = review_provider.calls
    prompt = render_review_user_prompt(request)
    assert DOC in prompt and "120 km in 8 hours" in prompt and "160" in prompt
    assert [c.claim_id for c in request.supporting_claims] == ["support"] and request.supporting_claims[0].claim_text == DOC
    assert {(s.kind, s.ident) for s in request.sources} == {("claim", "c"), ("supporting_claim", "support"), ("task", "t"), ("supplied_text", "doc")}
    mapping = {m.assertion_id: m for m in request.premise_sources}
    assert mapping["D"].grounding_kind == "arithmetic_fact" and mapping["D"].verified is False
    assert any(c.method == "numeric_in_task" and c.verified is False for c in mapping["D"].checks)
    for label in ("supporting_claims", "task", "supplied_texts", "source_identities", "premise_sources", "problem", "interpretation"):
        assert f"<<<DATA {label}>>>" in prompt
    review = outcome.semantic_review
    assert review.evidence_supplied and review.binding is not None and review.binding.task_sha256 == task.text_sha256
    assert review.binding.supporting_claims.keys() == {"support"} and review.binding.supplied_texts.keys() == {"doc"}
    assert review.reviewer.prompt_version == prompts.REVIEW_PROMPT_VERSION == "review_v2"


def test_a_changed_supporting_claim_or_source_makes_an_earlier_review_stale_with_the_claim_text_unchanged():
    """(Repair 2 of the integration: the supplied text states the relation, so the current review is all release waits
    for; with the translation's own relation release would be refused whatever the review.)"""
    claim, report, p = speed_case(120, 15, doc=DOC_STATED)
    faithful = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}}))
    outcome, _ = run(claim, report, output(p), reviewer=faithful)
    review, translation = outcome.semantic_review, outcome.translation
    assert review_currency(review, claim, translation, report) == ("current", [])
    changed_support = report.claims[1].model_copy(update={"claim_text": "Distance 160 km over 8 hours."})
    body = report.original_response
    report2 = SpecialistReport(**{**report.model_dump(), "claims": [claim, changed_support], "response_sha256": sha256_text(body), "original_response": body})
    state, changed = review_currency(review, claim, translation, report2)
    assert state == "stale" and changed == ["supporting claim support changed"]
    report3 = report.model_copy(update={"supplied_texts": [SuppliedText(document_id="doc", text="Distance 160 km over 8 hours.")]})
    assert review_currency(review, claim, translation, report3) == ("stale", ["supplied text doc changed"])
    stale = compose_outcome(claim, translation, outcome.verification, review, signing_key=KEY, key_id="k", report=report3)
    assert stale.display_status is S.ENTAILED and not stale.release.permitted and stale.release.fidelity == "stale"
    assert "STALE" in stale.summary
    current = compose_outcome(claim, translation, outcome.verification, review, signing_key=KEY, key_id="k", report=report)
    assert current.release.permitted


def test_a_review_without_the_evidence_never_counts_as_approval():
    claim, report, p = speed_case(120, 15)
    outcome, _ = run(claim, report, output(p))
    review = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}})).review(claim, outcome.translation)
    assert not review.evidence_supplied
    composed = compose_outcome(claim, outcome.translation, outcome.verification, review, signing_key=KEY, key_id="k", report=report)
    assert not composed.release.permitted and composed.release.fidelity == "without_evidence"
    assert "do not call the encoding faithful on the claim text alone" in render_review_user_prompt(_bare_request(claim, outcome.translation))


def _bare_request(claim, translation):
    from epinoic_logic.translate.review import build_review_request
    return build_review_request(claim, translation, None)[0]


def test_the_review_prompt_judges_premises_against_their_sources():
    text = prompts.load_prompt(prompts.REVIEW_PROMPT_VERSION)
    for needle in ("160 where the text says 120", "premise_sources", "figure_readings", "never widened", "only defined", "no longer counts"):
        assert needle in text, needle
    assert prompts.load_prompt("review_v1").startswith("# Epinoic semantic-fidelity reviewer — system instructions (review_v1)")


# =========================================================================== 6. definitions and unconstrained variables


def test_a_faithful_definition_keeps_its_counterexample_and_no_premise_is_requested():
    support = "Define b to hold iff n equals 17; this definition does not assert b."
    claim, report = make("Therefore b necessarily holds.", support=[("d", support)], role="point", kind="formal_logic")
    p = problem([{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "label": support, "grounding": {"kind": "supplied_text"}}],
                {"id": "C", "expr": V("b"), "label": "b necessarily holds"}, symbols=(("b", "Bool", None), ("n", "Int", None)))
    outcome, provider = run(claim, report, output(p))
    assert len(provider.calls) == 1 and outcome.translation.status is T.TRANSLATED
    # integration of the review fixes: the signed engine result carries the translation layer's coverage decision, so the
    # advisory is the engine's own W110 (E110 is reserved for a figure a source asserts); the rule is unchanged
    codes = [d.code for d in outcome.verification.diagnostics]
    assert outcome.verification.status is S.COUNTEREXAMPLE and "W110" in codes and "E110" not in codes
    assert outcome.display_status is S.COUNTEREXAMPLE
    assert "Advisory coverage warnings" in outcome.summary and "W110" in outcome.summary
    note = next(n for n in outcome.translation.coverage if n.kind == "unasserted_definition")
    assert not note.source_asserted and note.evidence == [] and note.source_refs == [] and note.evidence_symbols == []
    assert all(s.grounding is None or s.grounding.verified is not True for s in outcome.translation.problem.symbols)  # no coverage evidence handed over
    assert not any("does not rest on them" in d for d in outcome.translation.diagnostics)  # here the verdict does rest on it


def test_a_definition_of_a_figure_the_source_asserts_is_rejected_with_the_source_evidence():
    support = "In 1960 seventeen African states became independent."
    claim, report = make("The decisive year was 1960.", support=[("h1", support)], role="point", subject="History", kind="formal_logic")
    p = problem([{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "label": "seventeen states in 1960", "grounding": {"kind": "general_knowledge"}}],
                {"id": "C", "expr": V("b"), "label": "the decisive year was 1960"}, symbols=(("b", "Bool", None), ("n", "Int", None)))
    outcome, provider = run(claim, report, output(p))
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION
    diag = next(d for d in provider.calls[1].prior_diagnostics if "E110" in d)
    assert "the source asserts that figure" in diag and "seventeen" in diag and "Add nothing the source does not state" in diag
    assert "ENTAILED" not in diag  # the reason given is the source, never that entailment would follow
    note = next(n for n in outcome.translation.coverage if n.kind == "unasserted_definition")
    assert note.source_asserted and any("seventeen" in e for e in note.evidence)


def test_an_intentionally_unconstrained_variable_keeps_its_counterexample():
    claim, report = make("Given x = 5, x is less than y for an arbitrary integer y.", subject="Mathematics")
    p = problem([{"id": "P", "expr": eq(V("x"), I(5)), "label": "x equals 5; y is an arbitrary integer.", "grounding": {"kind": "task_setting"}}],
                {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}}, symbols=(("x", "Int", None), ("y", "Int", None)))
    outcome, _ = run(claim, report, output(p))
    # integration of the review fixes: the advisory is the engine's own W111 (E111 is reserved for a value a source states)
    codes = [d.code for d in outcome.verification.diagnostics]
    assert outcome.verification.status is S.COUNTEREXAMPLE and "W111" in codes and "E111" not in codes
    assert {a.symbol: a.value for a in outcome.verification.counterexample.assignments}["x"] == "5"
    assert outcome.display_status is S.COUNTEREXAMPLE and "Advisory coverage warnings" in outcome.summary and "W111" in outcome.summary
    note = next(n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol")
    assert not note.source_asserted and note.evidence_symbols == []


def test_an_omitted_stated_figure_makes_the_unconstrained_counterexample_no_verdict():
    claim, report = make("Since x = 5 and y = 9, x is less than y.", subject="Mathematics")
    p = problem([{"id": "P", "expr": eq(V("x"), I(5)), "grounding": {"kind": "task_setting"}}],
                {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}}, symbols=(("x", "Int", None), ("y", "Int", None)))
    outcome, _ = run(claim, report, output(p))
    assert outcome.verification.status is S.COUNTEREXAMPLE and "E111" in [d.code for d in outcome.verification.diagnostics]
    assert outcome.display_status is S.INVALID_FORMALIZATION
    note = next(n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol")
    assert note.source_asserted and any("'9'" in e for e in note.evidence)
    assert "The source asserts what the encoding left open" in outcome.summary


DEF_EXPR = {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}
COVERAGE_CASES = {
    # name: (claim text, supporting claim text or None, premises, conclusion, symbols, source asserts what the encoding leaves open)
    "definition, not asserted": ("Therefore b necessarily holds.", "Define b to hold iff n equals 17; this definition does not assert b.",
                                 [{"id": "D", "expr": DEF_EXPR, "grounding": {"kind": "supplied_text"}}], {"id": "C", "expr": V("b")},
                                 (("b", "Bool", None), ("n", "Int", None)), False),
    "definition, asserted": ("The decisive year was 1960.", "In 1960 seventeen African states became independent.",
                             [{"id": "D", "expr": DEF_EXPR, "grounding": {"kind": "general_knowledge"}}], {"id": "C", "expr": V("b")},
                             (("b", "Bool", None), ("n", "Int", None)), True),
    "free symbol, left open": ("Given x = 5, x is less than y for an arbitrary integer y.", None,
                               [{"id": "P", "expr": eq(V("x"), I(5)), "grounding": {"kind": "task_setting"}}],
                               {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}}, (("x", "Int", None), ("y", "Int", None)), False),
    "free symbol, stated": ("Since x = 5 and y = 9, x is less than y.", None,
                            [{"id": "P", "expr": eq(V("x"), I(5)), "grounding": {"kind": "task_setting"}}],
                            {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}}, (("x", "Int", None), ("y", "Int", None)), True),
}


@pytest.mark.parametrize("name", list(COVERAGE_CASES))
def test_the_coverage_note_the_signed_result_and_the_display_are_one_decision(name):
    """Integration of the review fixes (finding 6, engine and translation sides): the translation layer's coverage note,
    the signed engine result and the displayed status are one decision. A source that asserts what the encoding leaves
    open gives a note with source_asserted, a verified application record on exactly the symbols involved (references:
    the asserting spans), the engine's no-verdict E110/E111 and INVALID_FORMALIZATION; a source that leaves it open gives
    the advisory W110/W111, no record, and the COUNTEREXAMPLE stands. The same problem sent as a payload cannot carry the
    record (E505), so it gets the advisory."""
    from epinoic_logic.translate.coverage import apply_coverage_evidence
    from epinoic_logic.translate.pipeline import source_texts

    text, support, premises, conclusion, symbols, asserted = COVERAGE_CASES[name]
    claim, report = make(text, support=[("s", support)] if support else (), role="point" if support else "quantitative",
                         subject="History" if "1960" in text else "Mathematics", kind="formal_logic" if support else "arithmetic")
    prob = Problem.model_validate(problem(premises, conclusion, symbols=symbols))
    notes = Translator._coverage(prob, source_texts(claim, [c for c in report.claims if c.claim_id != claim.claim_id], report))
    assert len(notes) == 1 and notes[0].source_asserted is asserted
    with_record, checks = apply_coverage_evidence(prob, notes)
    stated = {s.name for s in with_record.symbols if s.grounding is not None and s.grounding.verified is True}
    assert stated == (set(notes[0].evidence_symbols) if asserted else set())
    if asserted:
        assert stated and all(r.document_id in ("c", "s") for s in with_record.symbols if s.name in stated for r in s.grounding.source_refs)
        assert all(c.method == "asserts_figure" and c.verified is True for c in checks)
    result = engine_verify(with_record, CFG, signing_key=KEY, key_id="k")
    codes = [d.code for d in result.diagnostics]
    no_verdict, advisory = ("E110", "W110") if notes[0].kind == "unasserted_definition" else ("E111", "W111")
    assert result.status is S.COUNTEREXAMPLE
    assert codes == ([no_verdict] if asserted else [advisory]), codes
    # a record as this translator makes it (version and claim-text digest): any other is displayed INTERNAL_ERROR (re-run review correctness-5)
    tr = TranslationResult(translation_id="tr", request_id="r", report_id="rep", claim_id="c", status=T.TRANSLATED, problem=with_record, coverage=notes,
                           eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True, decided_by="deterministic", policy_version="p"),
                           claim_text_sha256=sha256_text(claim.claim_text), translator_version=TRANSLATOR_VERSION, policy_version="p", created_at="2026-10-12T00:00:00Z")
    assert display_status_for(tr, result, KEY, "k") is (S.INVALID_FORMALIZATION if asserted else S.COUNTEREXAMPLE)
    payload = engine_verify(json.loads(with_record.model_dump_json(exclude_none=True)), CFG, signing_key=KEY, key_id="k")
    assert advisory in [d.code for d in payload.diagnostics] and no_verdict not in [d.code for d in payload.diagnostics]
    assert ("E505" in [d.code for d in payload.diagnostics]) is asserted


def test_a_hand_made_translation_without_source_assessment_keeps_e110_and_e111_counterexamples():
    """The reviewer's engine probe: no source-linked evidence exists, so the counterexamples stand. (Integration of the
    review fixes: the engine names these shapes with the advisory W110/W111 when no evidence exists, and the no-verdict
    E110/E111 never appear without it; the counterexamples stand as before.)"""
    base = {"problem_id": "p1", "request_id": "r1", "claim_id": "c1", "query": "entailment"}
    p_def = Problem.model_validate({**base, "symbols": [{"name": "b", "sort": "Bool"}, {"name": "n", "sort": "Int"}],
                                    "premises": [{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "grounding": {"kind": "task_setting"}}],
                                    "conclusion": {"id": "C", "expr": V("b")}})
    p_free = Problem.model_validate({**base, "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}],
                                     "premises": [{"id": "P", "expr": eq(V("x"), I(5)), "grounding": {"kind": "task_setting"}}],
                                     "conclusion": {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}}})
    for prob, code, withheld in ((p_def, "W110", "E110"), (p_free, "W111", "E111")):
        result = engine_verify(prob, CFG, signing_key=KEY, key_id="k")
        # a record as this translator makes it (version and claim-text digest): any other is displayed INTERNAL_ERROR (re-run review correctness-5)
        tr = TranslationResult(translation_id="tr", request_id="r1", report_id="rep1", claim_id="c1", status=T.TRANSLATED, problem=prob,
                               eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True, decided_by="deterministic", policy_version="p"),
                               claim_text_sha256=sha256_text("the claim c1"), translator_version=TRANSLATOR_VERSION, policy_version="p",
                               created_at="2026-10-12T00:00:00Z")
        codes = [d.code for d in result.diagnostics]
        assert result.status is S.COUNTEREXAMPLE and code in codes and withheld not in codes
        assert display_status_for(tr, result, KEY, "k") is S.COUNTEREXAMPLE


# =========================================================================== 7. reference lists


def test_every_reference_is_validated_and_an_unknown_document_prevents_complete_verification():
    docs = {"doc": SuppliedText(document_id="doc", text=DOC)}
    mixed = Grounding(kind="supplied_text", source_refs=[{"document_id": "doc", "excerpt": DOC}, {"document_id": "nonexistent", "locator": "page 9"}])
    checked, checks = check_grounding("P", mixed, docs)
    assert checked.verified is False
    assert [(c.ref_index, c.verified) for c in checks] == [(0, True), (1, False)]
    assert "never supplied" in checks[1].detail and checks[1].document_id == "nonexistent"
    [support] = grounding_support(checks)
    assert (support.support, support.located, support.refuted, support.references) == ("partial", 1, 1, 2)


@pytest.mark.parametrize("refs,level,verified", [
    ([{"document_id": "doc", "excerpt": "Distance 120 km"}, {"document_id": "doc", "excerpt": "8 hours"}], "complete", True),
    ([{"document_id": "doc", "excerpt": "Distance 120 km"}, {"document_id": "doc"}], "partial", None),
    ([{"document_id": "nonexistent"}], "failed", False),
    ([{"document_id": "doc", "excerpt": "Distance 999 km"}], "failed", False),
    ([{"document_id": "doc"}], "uncheckable", None),
])
def test_reference_support_levels_are_distinguished(refs, level, verified):
    checked, checks = check_grounding("P", Grounding(kind="supplied_text", source_refs=refs), {"doc": SuppliedText(document_id="doc", text=DOC)})
    assert checked.verified is verified and grounding_support(checks)[0].support == level


def test_partial_reference_support_through_the_pipeline_blocks_release():
    claim, report, p = speed_case(120, 15)
    p["premises"][0]["grounding"] = {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "Distance 120 km"}, {"document_id": "ghost"}]}
    faithful = SemanticReviewer(FixtureReviewProvider({"c": {"verdict": "faithful", "issues": []}}))
    outcome, _ = run(claim, report, output(p), reviewer=faithful)
    support = {s.target_id: s.support for s in outcome.translation.grounding_support}
    assert support["D"] == "partial" and "D" in outcome.verification.ungrounded_dependencies
    assert not outcome.release.permitted and any("references not all located" in u for u in outcome.release.unresolved)


# =========================================================================== 9. typed quantities


def percent_problem(literal, meaning="The dimensionless tax rate, 0.2 means 20 percent"):
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "consistency",
                                   "symbols": [{"name": "tax_rate", "sort": "Real", "meaning": meaning}],
                                   "premises": [{"id": "P", "expr": eq(V("tax_rate"), R(literal)), "label": "The tax rate is 20%.",
                                                 "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "task", "excerpt": "The tax rate is 20%."}]}}]})


TAX = [SuppliedText(document_id="task", text="The tax rate is 20%.")]


@pytest.mark.parametrize("literal", ["0.2", "1/5", "0.20"])
def test_decimal_and_rational_spellings_of_twenty_per_cent_agree(literal):
    checked, checks = check_problem_grounding(percent_problem(literal), TAX)
    assert checked.premises[0].grounding.verified is True
    figures = next(c for c in checks if c.method == "figures_in_excerpt")
    assert figures.verified is True and "20% = 20 x 0.01 = 0.2 (dimensionless)" in figures.detail


@pytest.mark.parametrize("literal,meaning,verified", [
    ("20", "The dimensionless tax rate, 0.2 means 20 percent", False),  # the per-cent number for a dimensionless symbol
    ("20", "tax rate in per cent", True),
    ("0.2", "tax rate in per cent", False),                             # the fraction for a symbol declared in per cent
    ("0.25", "The dimensionless tax rate", False),                      # a different value
    ("20", None, True),                                                 # no declared reading: as written
])
def test_a_declared_reading_is_respected(literal, meaning, verified):
    checked, checks = check_problem_grounding(percent_problem(literal, meaning), TAX)
    assert checked.premises[0].grounding.verified is verified
    if not verified and literal == "20":
        assert any("declared a dimensionless fraction" in (c.detail or "") for c in checks)


def test_equivalent_unit_representations_and_scale_words():
    hours = [f for f in figures_in(SourceText("supplied_text", "d", "The trip took 2 hours and cost $13 billion."))]
    minutes, why = literal_matches(Fraction(120), hours, declared_reading("duration in minutes"))
    assert minutes and "120" in minutes[0].derivation
    wrong, why = literal_matches(Fraction(2), hours, declared_reading("duration in minutes"))
    assert not wrong and any("declared unit" in w for w in why)
    billions, _ = literal_matches(Fraction(13_000_000_000), hours)
    assert billions and "13 x 1,000,000,000" in billions[0].derivation
    words = figures_in(SourceText("claim", "c", "two-thirds of the seats went to seventeen states"))
    assert {f.value for f in words} == {Fraction(2, 3), Fraction(17)}


def test_the_translation_prompt_states_exactness_authority_and_definitions():
    text = prompts.load_prompt(prompts.TRANSLATE_PROMPT_VERSION)
    for needle in ("states EXACTLY", "Never widen it to an interval", "choosing one confers", "Never add a premise the source does not state",
                   "never choose a reading because it makes", "dimensionless fraction", "A retry that weakens the conclusion"):
        assert needle in text, needle
    assert "the rounded figures were encoded as exact equalities" not in text
    # every rule the round-7 test pins on the earlier prompt holds for the prompt in use as well
    for needle in ("Stated precision", "half a unit of its last stated place", "Symbol names are shared across ALL claims", "marks_a",
                   "the ten kinds", "general_knowledge", "knowledge_document", "library_source", "A figure that only the report states is NOT an arithmetic",
                   '"A, so B"', "never encode", "superlative over a finite set", "solution set"):
        assert needle in text, needle
    assert "otherwise flag the ambiguity and encode the literal comparison" not in text
