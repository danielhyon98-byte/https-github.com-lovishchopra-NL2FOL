"""E2E B20: one claim, two encodings, opposite definitive answers. A branch formal check of a clause the claim states
fails while the translation of the whole claim is ENTAILED (ph-e1 s3.1 and s5.2, bi-e1 s4.1, cs-e1 c2.1/c2.2/c12.3 in the
end-to-end run): one of the two encodings misreads the claim, and the channel cannot tell which. The receipt names the
disagreement (INT-XENC-001, a warning, with both result ids); neither verdict is withdrawn (the check's INT-SUBJ-001 error
stays), and the response gate counts the claim, and the check, as unresolved.

The disagreement is built here on s01's kinetic-energy claim: its STEM arithmetic check finds "0.5 × 2.0 × 3.0² = 18 J"
false, and a translation that drops the ½ (E_k = m v²) entails 18 J. A translation that keeps the ½ agrees with the check
(both negative), and a correct answer with a faithful translation agrees with it (both positive): no finding."""
from __future__ import annotations

from epinoic_logic.channel.gate import assess_response

from ..argdiag_cases import load_case
from .dev_case_hub import run_case


def _g(kind: str) -> dict:
    return {"kind": kind, "source_refs": [], "certainty": "established"}


def _var(name: str) -> dict:
    return {"op": "var", "name": name}


def _real(value: str) -> dict:
    return {"op": "real", "value": value}


def kinetic_energy_proposal(*, keep_half: bool, stated: str) -> dict:
    """E_k from m = 2.0 kg and v² = 3.0 × 3.0, with or without the ½, concluding E_k = ``stated``."""
    energy = {"op": "mul", "args": ([_real("0.5")] if keep_half else []) + [_real("2.0"), _var("v2")]}
    return {
        "problem": {
            "ir_version": "1.0", "problem_id": "ke-s1.2", "request_id": "r", "claim_id": "s1.2", "query": "entailment",
            "symbols": [{"name": "v2", "sort": "Real", "meaning": "square of the trolley's speed (task: 3.0 m/s)", "grounding": _g("arithmetic_fact")},
                        {"name": "ek", "sort": "Real", "meaning": "kinetic energy in J", "grounding": _g("specialist_inference")}],
            "premises": [
                {"id": "p_v2", "expr": {"op": "eq", "left": _var("v2"), "right": {"op": "mul", "args": [_real("3.0"), _real("3.0")]}},
                 "label": "v squared = 3.0 x 3.0", "grounding": _g("arithmetic_fact"), "materiality": "material"},
                {"id": "p_ek", "expr": {"op": "eq", "left": _var("ek"), "right": energy},
                 "label": "E_k = 1/2 m v^2" if keep_half else "E_k = m v^2", "grounding": _g("rubric_rule"), "materiality": "material"},
            ],
            "conclusion": {"id": "c", "expr": {"op": "eq", "left": _var("ek"), "right": _real(stated)}, "label": f"E_k = {stated} J",
                           "grounding": None, "materiality": "material"},
        },
        "interpretation": {"reading": "the kinetic energy from the given mass and speed", "glossary": [], "ambiguity_flags": []},
        "ambiguous": False, "unsupported_reason": None,
    }


def _run(case_id: str, clause: str, proposal: dict):
    case = load_case(case_id)
    case["translations"] = [{"contains": clause, "proposal": proposal}]
    return run_case(case_id, case=case)


def _xenc(run):
    return [f for f in run.receipt.findings if f.code == "INT-XENC-001"]


def test_a_failed_check_against_an_entailed_translation_is_named_with_both_results():
    run = _run("s01_arith_slip", "0.5 × 2.0 × 3.0² = 18 J", kinetic_energy_proposal(keep_half=False, stated="18"))
    rc = run.receipt
    outcome = next(o for o in rc.outcomes if o.claim_id == "s1.2")
    assert outcome.display_status.value == "ENTAILED"
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False and "s1.2" in fc.claim_ids]
    assert failed
    found = _xenc(run)
    assert len(found) == 1 and found[0].severity == "warning" and found[0].claim_ids == ["s1.2"]
    assert found[0].formal_result_id == failed[0].formal_result_id
    assert found[0].related_result_ids == [outcome.verification.result_id]
    # neither verdict is withdrawn: the check's error stays, and so does the displayed status
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error" and f.claim_ids == ["s1.2"]]
    # the gate: the claim and the check are unresolved, never passed and never failed
    gate = assess_response(run.receipts, synthesis_required=False)
    claim = next(c for c in gate.checks if c.rule == "claim" and c.claim_ids == ["s1.2"])
    check = next(c for c in gate.checks if c.rule == "branch_check" and c.check.endswith(failed[0].constraint_id))
    assert claim.result == "unresolved" and check.result == "unresolved"
    assert gate.display_status != "VERIFIED" and all(gate.invariants().values())


def test_two_encodings_that_agree_on_a_negative_answer_give_none():
    run = _run("s01_arith_slip", "0.5 × 2.0 × 3.0² = 18 J", kinetic_energy_proposal(keep_half=True, stated="18"))
    outcome = next(o for o in run.receipt.outcomes if o.claim_id == "s1.2")
    assert outcome.display_status.value == "COUNTEREXAMPLE"
    assert not _xenc(run)                                       # the checks that hold cover other clauses of the claim
    gate = assess_response(run.receipts, synthesis_required=False)
    assert next(c for c in gate.checks if c.rule == "claim" and c.claim_ids == ["s1.2"]).result == "failed"
    assert gate.display_status == "WITHHELD"


def test_two_encodings_that_agree_on_a_positive_answer_give_none():
    run = _run("s00_control_ke", "0.5 × 2.0 × 3.0² = 9.0 J", kinetic_energy_proposal(keep_half=True, stated="9.0"))
    outcome = next(o for o in run.receipt.outcomes if o.claim_id == "s1.2")
    assert outcome.display_status.value == "ENTAILED"
    assert all(fc.satisfied is True for fc in run.receipt.formal_checks)
    assert not _xenc(run)


def test_the_e2e_disagreements_are_named_where_the_check_still_fails():
    run = run_case("e2e-B20-ph")
    rc = run.receipt
    entailed = {o.claim_id: o for o in rc.outcomes if o.display_status.value == "ENTAILED"}
    expected = {(fc.formal_result_id, cid) for fc in rc.formal_checks if fc.satisfied is False for cid in fc.claim_ids if cid in entailed}
    named = {(f.formal_result_id, f.claim_ids[0]) for f in _xenc(run)}
    assert named == expected                                    # every such pair named, and nothing else
    for f in _xenc(run):
        assert f.related_result_ids == [entailed[f.claim_ids[0]].verification.result_id]
