"""Engine regressions from the round-7 arena fixers' hand-off (owner: core).

* correctness-1: E111 was computed only when the E110/W110 check returned nothing, so a counterexample with the W110
  shape on a figure a source states was signed COUNTEREXAMPLE. E110/E111 now take precedence over W110/W111.
* fidelity-4: circular_premises compared canonical JSON only, so a restatement rewritten trivially ('41 = dt',
  'dt <= 41 and dt >= 41', 'not not (a and b)', '(a and b) <-> true', operands reordered) escaped E112.
* fidelity-6: a COUNTEREXAMPLE falsified only through Bool conclusion conjuncts no premise mentions was the verdict with
  no coverage diagnostic; it now carries the advisory W111 ('judgement not linked').
* robustness-and-contracts-5: verify() gave INTERNAL_ERROR E900 for malformed payloads (None, a list, an int, a lone
  surrogate in a text or dict payload, a huge integer value); they are INVALID_FORMALIZATION E100.
* security-1: a non-ASCII forged signature raised TypeError in verify_signature and release_check.
* security-5: a genuine signed result failed verification after an exclude_none round trip (memory_max_mb None re-parsed
  as the default); receivers now read dumps with the faithful ``engine.results.parse_result``.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.provenance import signature_matches, verify_signature
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.results import VerificationResult, parse_result
from epinoic_logic.engine.runner import circular_premises, verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import DEFAULT_LIMITS, Problem
from epinoic_logic.translate.contracts import EligibilityDecision, TranslationResult
from epinoic_logic.translate.outcome import display_status_for
from epinoic_logic.version import POLICY_VERSION, TRANSLATOR_VERSION

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"r7-core-engine-key-0123456789abcdef"
KEY_ID = "r7-core"
SI = {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def codes(r) -> list[str]:
    return [d.code for d in r.diagnostics]


def translated(problem: Problem) -> TranslationResult:
    return TranslationResult(translation_id="tr", request_id=problem.request_id, report_id="rep1", claim_id=problem.claim_id, status="TRANSLATED",
                             eligibility=EligibilityDecision(eligibility_class="PROPOSITIONAL_ARGUMENT", eligible=True, decided_by="deterministic",
                                                             policy_version=POLICY_VERSION),
                             problem=problem, translator_version=TRANSLATOR_VERSION, policy_version=POLICY_VERSION, created_at="2026-10-12T00:00:00Z")


# ------------------------------------------------------------------ correctness-1: E111 over W110


def _stated_figure(with_definition: bool) -> Problem:
    syms = [{"name": "x", "sort": "Int"},
            {"name": "y", "sort": "Int", "grounding": {"kind": "supplied_text", "verified": True, "source_refs": [{"document_id": "doc", "excerpt": "y = 9"}]}}]
    prem = [{"id": "P2", "expr": {"op": "eq", "left": V("x"), "right": I(5)}, "label": "x is 5"}]
    concl = {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}}
    if with_definition:  # the shape that gave the advisory W110 and, before the fix, hid E111
        syms += [{"name": "b", "sort": "Bool"}, {"name": "n", "sort": "Int"}]
        prem.append({"id": "D", "expr": {"op": "iff", "left": V("b"), "right": {"op": "eq", "left": V("n"), "right": I(17)}}, "label": "b means n is 17"})
        concl = {"id": "C", "expr": {"op": "or", "args": [V("b"), {"op": "lt", "left": V("x"), "right": V("y")}]}}
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": syms, "premises": prem, "conclusion": concl})


@pytest.mark.parametrize("with_definition", [False, True])
def test_a_counterexample_on_a_source_stated_figure_is_e111_whatever_the_w110_shape(with_definition):
    p = _stated_figure(with_definition)
    r = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["E111"] and "y" in r.diagnostics[0].message
    assert display_status_for(translated(p), r, KEY, KEY_ID) is S.INVALID_FORMALIZATION


# ------------------------------------------------------------------ fidelity-4: E112 on rewritten restatements


def _one_premise(pexpr, cexpr, syms) -> Problem:
    return Problem.model_validate({"problem_id": "c", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s, "grounding": SI} for n, s in syms],
                                   "premises": [{"id": "p1", "expr": pexpr, "grounding": SI}], "conclusion": {"id": "C", "expr": cexpr}})


DT = V("dt")
AB = {"op": "and", "args": [V("a"), V("b")]}
RESTATED = {
    "operands swapped": ({"op": "eq", "left": I(41), "right": DT}, {"op": "eq", "left": DT, "right": I(41)}, [("dt", "Int")]),
    "a pair of bounds": ({"op": "and", "args": [{"op": "le", "left": DT, "right": I(41)}, {"op": "ge", "left": DT, "right": I(41)}]},
                         {"op": "eq", "left": DT, "right": I(41)}, [("dt", "Int")]),
    "double negation": ({"op": "not", "arg": {"op": "not", "arg": AB}}, AB, [("a", "Bool"), ("b", "Bool")]),
    "iff true": ({"op": "iff", "left": AB, "right": {"op": "bool", "value": True}}, AB, [("a", "Bool"), ("b", "Bool")]),
    "conjuncts reordered": ({"op": "and", "args": [V("b"), V("a")]}, AB, [("a", "Bool"), ("b", "Bool")]),
    "comparison flipped": ({"op": "lt", "left": I(3), "right": DT}, {"op": "gt", "left": DT, "right": I(3)}, [("dt", "Int")]),
}


@pytest.mark.parametrize("name", sorted(RESTATED))
def test_a_trivially_rewritten_restatement_is_circular(name):
    p = _one_premise(*RESTATED[name])
    r = verify(p, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.ENTAILED and codes(r) == ["E112"] and circular_premises(p) == ["p1"]
    assert display_status_for(translated(p), r, KEY, KEY_ID) is S.INVALID_FORMALIZATION


def test_a_premise_that_entails_a_weaker_conclusion_is_no_circle():
    p = _one_premise({"op": "eq", "left": DT, "right": I(41)}, {"op": "gt", "left": DT, "right": I(40)}, [("dt", "Int")])
    r = verify(p, CFG)
    assert r.status is S.ENTAILED and codes(r) == [] and circular_premises(p) == []


# ------------------------------------------------------------------ fidelity-6: Bool judgement not linked


def test_a_counterexample_only_through_an_unmentioned_bool_conjunct_carries_w111():
    p = Problem.model_validate({"problem_id": "b", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": "a", "sort": "Bool"}, {"name": "j", "sort": "Bool"}],
                                "premises": [{"id": "E", "expr": V("a"), "grounding": {"kind": "supplied_text"}}],
                                "conclusion": {"id": "C", "expr": {"op": "and", "args": [V("a"), V("j")]}}})
    r = verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == ["W111"] and "judgement not linked" in r.diagnostics[0].message and "j" in r.diagnostics[0].message
    assert r.counterexample is not None  # advisory only: the counterexample stands


# ------------------------------------------------------------------ robustness-and-contracts-5: malformed payloads


BASE = {"problem_id": "p1", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "x", "sort": "Real"}],
        "premises": [{"id": "P", "expr": {"op": "eq", "left": V("x"), "right": {"op": "real", "value": "2"}}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("x"), "right": {"op": "real", "value": "2"}}}}


@pytest.mark.parametrize("raw", [
    json.dumps(BASE)[:-1] + ',"notes":"\ud83d"}',
    {**BASE, "notes": "\ud83d"},
    [BASE], None, 5,
    {**BASE, "notes": 10 ** 5000},
], ids=["surrogate-text", "surrogate-dict", "list", "none", "int", "huge-int"])
def test_a_malformed_payload_is_an_invalid_formalization_never_an_internal_error(raw):
    r = verify(raw, CFG, signing_key=KEY, key_id=KEY_ID)
    assert r.status is S.INVALID_FORMALIZATION and codes(r) == ["E100"]
    assert r.signature and verify_signature(r, KEY)


def test_a_well_formed_payload_is_unchanged():
    assert verify(json.dumps(BASE), CFG).status is S.ENTAILED


# ------------------------------------------------------------------ security-1 and security-5: signatures


def _signed() -> VerificationResult:
    r = verify(json.dumps(BASE), CFG, DEFAULT_LIMITS, KEY, KEY_ID)
    assert r.status is S.ENTAILED and verify_signature(r, KEY)
    return r


@pytest.mark.parametrize("forged", ["é" * 64, "\ud83d" * 64, "A" * 64, "0" * 63, "0" * 65, ""])
def test_a_forged_signature_of_any_text_is_false_and_release_check_never_raises(forged):
    r = _signed().model_copy(update={"signature": forged})
    assert verify_signature(r, KEY) is False
    check = release_check(r, signing_key=KEY, key_id=KEY_ID)
    assert check.eligible is False
    assert signature_matches("a" * 64, forged) is False


def test_a_signed_result_verifies_after_an_exclude_none_round_trip():
    """The receivers' faithful parse (``parse_result``, used by the service routes) reads a dump without
    ``memory_max_mb`` as ``None``; a plain ``model_validate`` still reads the default (the hazard the Overseer's store
    documents and parses around), so every receiver of a dump uses ``parse_result``."""
    r = _signed()
    assert r.solver_config.memory_max_mb is None
    lean = r.model_dump(mode="json", exclude_none=True)
    again = parse_result(lean)
    assert again.solver_config.memory_max_mb is None and verify_signature(again, KEY)
    assert verify_signature(parse_result(r.model_dump(mode="json")), KEY)
    assert not verify_signature(VerificationResult.model_validate(lean), KEY)  # the hazard parse_result removes
    # control: a result whose config states the limit keeps it
    capped = verify(json.dumps(BASE), SolverConfig(timeout_ms=4000, memory_max_mb=256), DEFAULT_LIMITS, KEY, KEY_ID)
    back = parse_result(capped.model_dump(mode="json", exclude_none=True))
    assert back.solver_config.memory_max_mb == 256 and verify_signature(back, KEY)
    with pytest.raises(ValidationError):
        parse_result({"solver_config": {}})
