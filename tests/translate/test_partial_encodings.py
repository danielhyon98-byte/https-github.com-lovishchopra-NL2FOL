"""Encodings that leave part of the claim out (``translate/pipeline.py``, the B21 end-to-end item and the UNENCODED_REASON guard).

* UNLINKED_CONJUNCT (B8) is not ported onto the integrated translator: an encoding with an unlinked conjunct keeps its
  COUNTEREXAMPLE there (its own tests/e2e/test_arena_deliveries.py), so the B8 receipt test is not ported
  (docs/ARGUMENT_DIAGNOSTICS.md, "Port onto the integrated translator"); a linked part that does not follow still keeps
  its counterexample (tested below).
* UNENCODED_REASON (its guard): no premise mentions the point (the f01 shape) and the claim's own text gives a reason
  clause that no premise encodes: the translation left the claim's stated reason out. f01 ("because of the Treaty" is a
  cause phrase, not a reason clause) keeps its COUNTEREXAMPLE and its ARG-NS-001 warning.
* PARTIAL_ENCODING (B21): an ENTAILED encoding of only one clause of a claim split at "but" (or "however", "although",
  "while", "whereas", ";"), the other clause's content words mostly absent from every label and meaning: a partial
  encoding is never shown as the whole claim.

Each flag moves the display toward "nothing verified", never toward success.
"""
from __future__ import annotations

from functools import lru_cache

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S

from ..argdiag_hub import run_case
from ..contract.helpers import make_report, output, run_claim


@lru_cache(maxsize=None)
def _delivered(case_id: str, mode: str = "text"):
    return run_case(case_id, mode)


def _flags(out) -> list[str]:
    interp = out.translation.interpretation
    return [f.code for f in interp.ambiguity_flags] if interp is not None else []


def test_f01_keeps_its_counterexample_and_its_warning():
    [out] = [o for o in _delivered("f01_non_sequitur").outcomes.values()]
    assert out.display_status is S.COUNTEREXAMPLE and _flags(out) == []
    assert [(d.code, d.severity) for d in out.named_diagnostics if d.code == "ARG-NS-001"] == [("ARG-NS-001", "warning")]


def _bool_problem(premises: list[dict], conclusion: dict, symbols: dict[str, str]) -> dict:
    return {"ir_version": "1.0", "problem_id": "p-c", "request_id": "req-ad", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": n, "sort": "Bool", "meaning": m} for n, m in symbols.items()], "premises": premises,
            "conclusion": {"id": "C", "expr": conclusion, "label": "the point"}}


def _v(name: str) -> dict:
    return {"op": "var", "name": name}


def test_a_linked_part_that_does_not_follow_keeps_the_counterexample():
    """The counterexample falsifies the linked part too, so it is a verdict on the claim: no UNLINKED_CONJUNCT."""
    claim, report = make_report("The treaty was signed and it was resented, so the war followed.", role="point", kind="formal_logic",
                                support=(("s1", "The treaty was signed in 1919."),), texts=(), subject="History")
    problem = _bool_problem([{"id": "e", "expr": _v("signed"), "label": "the treaty was signed", "grounding": {"kind": "specialist_inference"}}],
                            {"op": "and", "args": [_v("resented"), _v("war")]},
                            {"signed": "the treaty was signed", "resented": "the treaty was resented", "war": "the war followed"})
    problem["premises"].append({"id": "l", "expr": {"op": "implies", "left": _v("signed"), "right": _v("war")}, "label": "if signed then war",
                                "grounding": {"kind": "specialist_inference"}})
    problem["conclusion"]["expr"] = {"op": "and", "args": [_v("war"), _v("resented"), {"op": "not", "arg": _v("signed")}]}
    out = run_claim(claim, report, output(problem))
    assert out.display_status is S.COUNTEREXAMPLE and "UNLINKED_CONJUNCT" not in _flags(out)


REASON_CLAIM = "The treaty was the main cause of the war, because the reparations bankrupted Germany."


def _reason_problem(*, encode_reason: bool) -> dict:
    if encode_reason:
        prem = [{"id": "e", "expr": _v("bankrupt"), "label": "the reparations bankrupted Germany", "grounding": {"kind": "specialist_inference"}}]
        syms = {"bankrupt": "the reparations bankrupted Germany", "main": "the treaty was the main cause of the war"}
    else:
        prem = [{"id": "e", "expr": _v("signed"), "label": "the treaty was signed in 1919", "grounding": {"kind": "specialist_inference"}}]
        syms = {"signed": "the treaty was signed in 1919", "main": "the treaty was the main cause of the war"}
    return _bool_problem(prem, _v("main"), syms)


def _reason_claim():
    return make_report(REASON_CLAIM, role="point", kind="formal_logic", support=(("s1", "The treaty was signed in 1919."),), texts=(), subject="History")


def test_a_stated_reason_the_translation_left_out_is_unencoded_reason():
    claim, report = _reason_claim()
    out = run_claim(claim, report, output(_reason_problem(encode_reason=False)))
    assert out.display_status is S.AMBIGUOUS_TRANSLATION and "UNENCODED_REASON" in _flags(out)
    [flag] = [f for f in out.translation.interpretation.ambiguity_flags if f.code == "UNENCODED_REASON"]
    assert "'the reparations bankrupted Germany'" in flag.message
    assert out.verification.status is S.COUNTEREXAMPLE
    ns = [d for d in out.named_diagnostics if d.code == "ARG-NS-001"]
    assert ns and ns[0].severity == "info" and ns[0].capped_from == "warning"     # capped on the assumed reading, still blocking


def test_an_encoded_reason_keeps_the_non_sequitur_counterexample():
    claim, report = _reason_claim()
    out = run_claim(claim, report, output(_reason_problem(encode_reason=True)))
    assert out.display_status is S.COUNTEREXAMPLE and "UNENCODED_REASON" not in _flags(out)
    assert [(d.code, d.severity) for d in out.named_diagnostics if d.code == "ARG-NS-001"] == [("ARG-NS-001", "warning")]


G41 = "Your 0.92 and 0.62 are correct as ratios, but the dependency ratio is conventionally given per 100 people of working age."
TABLE = ("Indicator | 1990 | 2024\nAged 0–14 (millions) | 4.3 | 5.9\nAged 15–64 (millions) | 5.0 | 11.0\n"
         "Aged 65 and over (millions) | 0.3 | 0.9")


def _ratio_problem(*, both_clauses: bool) -> dict:
    def fig(name: str, value: str, excerpt: str) -> tuple[dict, dict]:
        g = {"kind": "arithmetic_fact", "source_refs": [{"document_id": "doc-selvaria", "excerpt": excerpt}]}
        return ({"name": name, "sort": "Real", "meaning": f"population {name.replace('_', ' ')} (millions)", "grounding": g},
                {"id": f"fp_{name}", "expr": {"op": "eq", "left": _v(name), "right": {"op": "real", "value": value}},
                 "label": f"the table gives {name.replace('_', ' ')} as {value}", "grounding": g})
    figures = [fig("kids_1990", "4.3", "Aged 0–14 (millions) | 4.3 | 5.9"), fig("old_1990", "0.3", "Aged 65 and over (millions) | 0.3 | 0.9")]
    # the working-age figure (5.0 million) is the constant divisor, so the relation stays linear
    ratio_def = {"op": "eq", "left": _v("ratio_1990"), "right": {"op": "div", "left": {"op": "add", "args": [_v("kids_1990"), _v("old_1990")]},
                                                                 "right": {"op": "real", "value": "5.0"}}}
    symbols = [s for s, _p in figures] + [{"name": "ratio_1990", "sort": "Real", "meaning": "the student's 1990 ratio: (aged 0-14 + aged 65 and over) / aged 15-64"}]
    premises = [p for _s, p in figures] + [{"id": "def_ratio", "expr": ratio_def, "label": "the ratio is (aged 0-14 + aged 65 and over) / 5.0",
                                           "grounding": {"kind": "specialist_inference"}}]
    conclusion = {"op": "eq", "left": _v("ratio_1990"), "right": {"op": "real", "value": "0.92"}}
    if both_clauses:
        symbols.append({"name": "per_100", "sort": "Bool", "meaning": "the dependency ratio is conventionally given per 100 people of working age"})
        premises.append({"id": "conv", "expr": _v("per_100"), "label": "the dependency ratio is conventionally given per 100 people of working age",
                         "grounding": {"kind": "general_knowledge", "note": "rule"}})
        conclusion = {"op": "and", "args": [conclusion, _v("per_100")]}
    return {"ir_version": "1.0", "problem_id": "p-g41", "request_id": "req-ad", "claim_id": "c", "query": "entailment", "symbols": symbols,
            "premises": premises, "conclusion": {"id": "C", "expr": conclusion, "label": "0.92 is correct as a ratio"}}


def _g41():
    return make_report(G41, role="quantitative", kind="arithmetic", texts=(("doc-selvaria", TABLE),), subject="Geography")


def test_both_clauses_encoded_stays_translated():
    claim, report = _g41()
    out = run_claim(claim, report, output(_ratio_problem(both_clauses=True)))
    assert out.translation.status.value == "TRANSLATED" and "PARTIAL_ENCODING" not in _flags(out)
    assert out.display_status is S.ENTAILED


def test_a_one_clause_claim_is_never_a_partial_encoding():
    claim, report = make_report("Your 0.92 is correct as a ratio.", role="quantitative", kind="arithmetic", texts=(("doc-selvaria", TABLE),), subject="Geography")
    out = run_claim(claim, report, output(_ratio_problem(both_clauses=False)))
    assert "PARTIAL_ENCODING" not in _flags(out) and out.display_status is S.ENTAILED
