"""The decision table, the summary, verdict signing and the Worker's binding checks (PROTOCOL.md sections 8 and 9).

The golden expectations below are written by hand from the table's rows (they do not call the code to compute what they
expect), the vectors in ``integration/vectors/decision-table`` and ``verdict-binding`` must agree with them, and a
property test over every combination of statuses shows that a non-definitive status never yields ``deliver`` with the
summary ``formally_checked``, whatever the policy.
"""
from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path

import pytest
from hypothesis import given, settings as hsettings, strategies as st

from epinoic_logic.integration.delivery import (
    BindingContext, ClaimFields, DecisionInput, binding_problem, count_claims, decide, decision_input_of, sign_verdict,
    summarize, verify_verdict_signature,
)
from epinoic_logic.integration.protocol import ATTEMPTS, DEFINITIVE, FORMAL_VALUES, INCOMPLETE_STATUSES, NEGATIVE, OVERSEER_REFUSALS, POSITIVE

VECTORS = Path(__file__).resolve().parents[2] / "integration" / "vectors"


def _inp(claims=(), *, policy="verified-v1", revision_of=None, receipt_status="ACCEPTED", errors=(), state="AUDIT_PASSED",
         allowed=True, refusal=None, consolidation="CONSOLIDATED") -> DecisionInput:
    fields = tuple(ClaimFields(*c) for c in claims)
    counts = count_claims(fields)
    return DecisionInput(policy=policy, revision_of=revision_of, receipt_status=receipt_status, receipt_error_codes=tuple(errors),
                         overseer_state=state, delivery_allowed=allowed, overseer_refusal=refusal, consolidation_status=consolidation,
                         blocking=counts["blocking"], unavailable=counts["unavailable"], budget_skipped=counts["budget_skipped"])


M, S = "material", "supporting"

# (name, input, expected decision, expected reasons): written by hand from the rows of the table.
GOLDEN = [
    ("row 7: a clean entailment delivers", _inp([(M, "ENTAILED", "attempted")]), "deliver", []),
    ("row 2: a REJECTED receipt", _inp([(M, "ENTAILED", "attempted")], receipt_status="REJECTED"), "refuse_integrity", ["KIT-DL-001"]),
    ("row 2: the FINAL audit failed", _inp([(M, "ENTAILED", "attempted")], state="AUDIT_FAILED", allowed=False, refusal="final_audit_not_passed"),
     "refuse_integrity", ["KIT-DL-005"]),
    ("row 2: a clearance failed", _inp([(M, "ENTAILED", "attempted")], allowed=False, refusal="clearance_failed"), "refuse_integrity", ["KIT-DL-003"]),
    ("row 2: custody", _inp([(M, "ENTAILED", "attempted")], allowed=False, refusal="custody_failed"), "refuse_integrity", ["KIT-DL-006"]),
    ("row 2: a refusal without a label fails closed", _inp([(M, "ENTAILED", "attempted")], allowed=False), "refuse_integrity", ["KIT-DL-006"]),
    ("row 2 wins over row 4", _inp([(M, "COUNTEREXAMPLE", "attempted")], receipt_status="REJECTED"), "refuse_integrity", ["KIT-DL-001"]),
    ("row 3: the clearance is pending", _inp([(M, "ENTAILED", "attempted")], state="AUDIT_PENDING", allowed=False, refusal="clearance_pending"),
     "refuse_incomplete", ["KIT-DL-004"]),
    ("row 4: error-level receipt findings", _inp([(M, "ENTAILED", "attempted")], receipt_status="ACCEPTED_WITH_FINDINGS", errors=["INT-SUBJ-001"]),
     "refuse_unresolved", ["KIT-DL-002"]),
    ("row 4: CONFLICTING", _inp([(M, "ENTAILED", "attempted")], allowed=False, refusal="consolidation_conflicting", consolidation="CONFLICTING"),
     "refuse_unresolved", ["KIT-DL-007"]),
    ("row 4: NO_DELIVERABLE_OUTPUT", _inp([], allowed=False, refusal="no_deliverable_output", consolidation="NO_DELIVERABLE_OUTPUT"),
     "refuse_unresolved", ["KIT-DL-008"]),
    ("row 4: a material counterexample", _inp([(M, "COUNTEREXAMPLE", "attempted"), (M, "ENTAILED", "attempted")]), "refuse_unresolved", ["KIT-DL-010"]),
    ("row 4: inconsistent premises", _inp([(M, "INCONSISTENT_PREMISES", "attempted")]), "refuse_unresolved", ["KIT-DL-010"]),
    ("row 4: unsatisfiable", _inp([(M, "UNSATISFIABLE", "attempted")]), "refuse_unresolved", ["KIT-DL-010"]),
    ("row 4 wins over row 5", _inp([(M, "COUNTEREXAMPLE", "attempted"), (M, "TIMEOUT", "attempted")]), "refuse_unresolved", ["KIT-DL-010"]),
    ("row 4 after a revision: exhausted", _inp([(M, "COUNTEREXAMPLE", "attempted")], revision_of="vd_x"), "refuse_unresolved", ["KIT-DL-010", "KIT-DL-020"]),
    ("row 4: no policy allows a revision in v1 (D5)", _inp([(M, "COUNTEREXAMPLE", "attempted")], policy="verified-v1-qualify"),
     "refuse_unresolved", ["KIT-DL-010"]),
    ("row 4: a SUPPORTING counterexample does not block", _inp([(S, "COUNTEREXAMPLE", "attempted"), (M, "ENTAILED", "attempted")]), "deliver", []),
    ("row 5: UNKNOWN under the default policy", _inp([(M, "UNKNOWN", "attempted")]), "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: TIMEOUT", _inp([(M, "TIMEOUT", "attempted")]), "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: INTERNAL_ERROR", _inp([(M, "INTERNAL_ERROR", "attempted")]), "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: the budget was spent", _inp([(M, "NOT_ATTEMPTED", "skipped_budget")]), "refuse_incomplete", ["KIT-DL-011", "KIT-DL-013"]),
    ("row 5: the STEM budget was spent", _inp([(M, "NOT_ATTEMPTED", "stem_budget")]), "refuse_incomplete", ["KIT-DL-011", "KIT-DL-013"]),
    ("row 5: the claim cap", _inp([(M, "NOT_ATTEMPTED", "skipped_cap")]), "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: the provider is unavailable", _inp([(M, "NOT_ATTEMPTED", "provider_unavailable")]), "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: the qualify policy continues", _inp([(M, "UNKNOWN", "attempted")], policy="verified-v1-qualify"), "deliver", []),
    ("row 5: a policy the table does not know refuses (fails closed)", _inp([(M, "UNKNOWN", "attempted")], policy="verified-v2-unlisted"),
     "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: an empty policy name refuses too", _inp([(M, "TIMEOUT", "attempted")], policy=""), "refuse_incomplete", ["KIT-DL-011"]),
    ("row 5: a supporting UNKNOWN does not count", _inp([(S, "UNKNOWN", "attempted"), (M, "ENTAILED", "attempted")]), "deliver", []),
    ("row 6: an ambiguous material claim continues", _inp([(M, "AMBIGUOUS_TRANSLATION", "attempted")]), "deliver", []),
    ("NOT_ELIGIBLE, UNSUPPORTED and INVALID_FORMALIZATION neither block nor leave the checks incomplete",
     _inp([(M, "NOT_ELIGIBLE", "not_eligible"), (M, "UNSUPPORTED", "attempted"), (M, "INVALID_FORMALIZATION", "attempted")]), "deliver", []),
    ("an internal-error verdict never delivers", _inp([(M, "ENTAILED", "attempted")], allowed=False, refusal="internal_error"),
     "refuse_incomplete", ["KIT-DL-900"]),
]


@pytest.mark.parametrize("name,inp,decision,reasons", GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_rows(name, inp, decision, reasons):
    assert decide(inp) == (decision, reasons)


@hsettings(max_examples=300, deadline=None)
@given(policy=st.text(max_size=24), status=st.sampled_from(sorted(INCOMPLETE_STATUSES)))
def test_row_5_continues_only_under_the_qualify_policy(policy, status):
    """Whatever the policy string, a material eligible claim without a definitive result delivers only under
    verified-v1-qualify: verified-v1 and every policy the table does not know refuse (row 5 fails closed)."""
    attempt = "skipped_budget" if status == "NOT_ATTEMPTED" else "attempted"
    decision, reasons = decide(_inp([(M, status, attempt), (M, "ENTAILED", "attempted", True)], policy=policy))
    if policy == "verified-v1-qualify":
        assert decision == "deliver"
    else:
        assert decision == "refuse_incomplete" and "KIT-DL-011" in reasons, policy


def test_every_overseer_refusal_label_is_refused_and_named():
    for label in OVERSEER_REFUSALS:
        decision, reasons = decide(_inp([(M, "ENTAILED", "attempted")], allowed=False, refusal=label,
                                        state="AUDIT_PENDING" if label == "clearance_pending" else "AUDIT_PASSED"))
        assert decision != "deliver" and reasons, label


# ----------------------------------------------------------------------------------------------- summary


@pytest.mark.parametrize("claims,expected", [
    ([(M, "ENTAILED", "attempted", True)], "formally_checked"),
    ([(M, "ENTAILED", "attempted", True), (M, "NOT_ELIGIBLE", "not_eligible", False)], "formally_checked"),
    ([(M, "ENTAILED", "attempted", True), (M, "ENTAILED", "attempted", False)], "partly_checked"),
    ([(M, "ENTAILED", "attempted", False)], "formal_only"),
    ([(M, "NOT_ELIGIBLE", "not_eligible", False)], "not_formally_checkable"),
    ([(M, "UNSUPPORTED", "attempted", False)], "not_formally_checkable"),
    ([(M, "UNKNOWN", "attempted", False), (M, "ENTAILED", "attempted", True)], "incomplete"),
    ([(S, "ENTAILED", "attempted", True)], "not_formally_checkable"),
])
def test_summary_from_counts(claims, expected):
    assert summarize(count_claims(ClaimFields(*c) for c in claims)) == expected


def test_counts_cover_material_claims_and_exclude_not_eligible():
    counts = count_claims([ClaimFields(M, "ENTAILED", "attempted", True), ClaimFields(M, "NOT_ELIGIBLE", "not_eligible"),
                           ClaimFields(S, "COUNTEREXAMPLE", "attempted"), ClaimFields(M, "NOT_ATTEMPTED", "skipped_budget"),
                           ClaimFields(M, "COUNTEREXAMPLE", "attempted")])
    assert counts == {"claims_total": 5, "material": 4, "eligible": 3, "attempted": 2, "definitive": 2, "positive": 1, "permitted": 1,
                      "blocking": 1, "unavailable": 1, "budget_skipped": 1, "not_eligible": 1}


# ----------------------------------------------------------------------------------------------- property tests

_CLAIM = st.tuples(st.sampled_from([M, S]), st.sampled_from(FORMAL_VALUES), st.sampled_from(ATTEMPTS), st.booleans())


def _consistent(claim):
    """A claim as the service can produce it: NOT_ELIGIBLE exactly with attempt not_eligible; NOT_ATTEMPTED exactly with
    a skipped attempt; release permitted only for positive results."""
    materiality, formal, attempt, permitted = claim
    if formal == "NOT_ELIGIBLE":
        attempt = "not_eligible"
    elif formal == "NOT_ATTEMPTED":
        attempt = attempt if attempt not in ("attempted", "not_eligible") else "skipped_budget"
    elif attempt != "attempted":
        attempt = "attempted"
    return ClaimFields(materiality, formal, attempt, permitted and formal in POSITIVE)


@hsettings(max_examples=600, deadline=None)
@given(claims=st.lists(_CLAIM, min_size=0, max_size=6), policy=st.sampled_from(["verified-v1", "verified-v1-qualify"]))
def test_a_non_definitive_status_never_yields_formally_checked(claims, policy):
    fields = tuple(_consistent(c) for c in claims)
    counts = count_claims(fields)
    inp = DecisionInput(policy=policy, revision_of=None, receipt_status="ACCEPTED", receipt_error_codes=(), overseer_state="AUDIT_PASSED",
                        delivery_allowed=True, overseer_refusal=None, consolidation_status="CONSOLIDATED",
                        blocking=counts["blocking"], unavailable=counts["unavailable"], budget_skipped=counts["budget_skipped"])
    decision, reasons = decide(inp)
    material_eligible = [f for f in fields if f.materiality == M and f.attempt != "not_eligible"]
    if any(f.formal in NEGATIVE for f in fields if f.materiality == M):
        assert decision == "refuse_unresolved"
    if decision == "deliver":
        summary = summarize(counts)
        if any(f.formal in INCOMPLETE_STATUSES for f in material_eligible):
            assert policy == "verified-v1-qualify" and summary == "incomplete"
        if summary == "formally_checked":
            assert material_eligible and all(f.formal in DEFINITIVE and f.formal in POSITIVE and f.release_permitted for f in material_eligible)
    if policy == "verified-v1" and any(f.formal in INCOMPLETE_STATUSES for f in material_eligible) and decision != "refuse_unresolved":
        assert decision == "refuse_incomplete" and "KIT-DL-011" in reasons


def test_exhaustively_no_single_or_paired_non_definitive_claim_is_formally_checked():
    singles = [ClaimFields(m, f, a, p) for m in (M, S) for f in FORMAL_VALUES for a in ATTEMPTS for p in (False, True)]
    for pair in itertools.chain(((c,) for c in singles), itertools.product(singles[::7], repeat=2)):
        for policy in ("verified-v1", "verified-v1-qualify"):
            counts = count_claims(pair)
            decision, _ = decide(DecisionInput(policy, None, "ACCEPTED", (), "AUDIT_PASSED", True, None, "CONSOLIDATED",
                                               counts["blocking"], counts["unavailable"], counts["budget_skipped"]))
            if decision == "deliver" and summarize(counts) == "formally_checked":
                assert all(c.formal in POSITIVE for c in pair if c.materiality == M and c.attempt != "not_eligible"), pair


# ----------------------------------------------------------------------------------------------- vectors


def _load(folder):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((VECTORS / folder).glob("*.json"))]


def test_decision_table_vectors_agree_with_the_table():
    vectors = _load("decision-table")
    assert len(vectors) >= 30
    for v in vectors:
        f = v["fields"]
        fields = tuple(ClaimFields(c["materiality"], c["formal"], c["attempt"], c["release_permitted"]) for c in f["claims"])
        inp = DecisionInput(f["policy"], f["revision_of"], f["receipt"]["status"], tuple(f["receipt"]["error_codes"]), f["overseer"]["state"],
                            f["overseer"]["delivery_allowed"], f["overseer"]["refusal"], f["consolidation_status"],
                            f["counts"]["blocking"], f["counts"]["unavailable"], f["counts"]["budget_skipped"])
        decision, reasons = decide(inp)
        assert {"decision": decision, "reasons": reasons, "summary": summarize(f["counts"]) if decision == "deliver" else None} == v["expect"], v["name"]
        assert count_claims(fields) == f["counts"], v["name"]


def test_decision_table_vectors_match_the_hand_written_rows():
    by_name = {v["name"]: v["expect"] for v in _load("decision-table")}
    assert by_name["row4-counterexample"]["decision"] == "refuse_unresolved"
    assert by_name["row5-not-attempted-budget"]["reasons"] == ["KIT-DL-011", "KIT-DL-013"]
    assert by_name["row5-qualify-policy-continues"] == {"decision": "deliver", "reasons": [], "summary": "incomplete"}
    assert by_name["deliver-formally-checked"]["summary"] == "formally_checked"
    assert by_name["internal-error-verdict"] == {"decision": "refuse_incomplete", "reasons": ["KIT-DL-900"], "summary": None}


# ----------------------------------------------------------------------------------------------- signing


def _good_verdict():
    return json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["verdict"]


KEY = bytes.fromhex("5e" * 32)


def test_signature_round_trip_and_tampering():
    v = _good_verdict()
    assert verify_verdict_signature(v, KEY)
    resigned = sign_verdict(v, KEY, "verdict-vectors")
    assert resigned == v
    tampered = copy.deepcopy(v)
    tampered["delivery"]["reasons"] = ["KIT-DL-011"]
    assert not verify_verdict_signature(tampered, KEY)
    assert not verify_verdict_signature(v, bytes.fromhex("5f" * 32))
    assert not verify_verdict_signature({k: x for k, x in v.items() if k != "signature"}, KEY)
    assert not verify_verdict_signature(dict(v, signature={"alg": "none", "key_id": "x", "value": "0" * 64}), KEY)


def test_the_verdict_key_must_be_at_least_32_bytes():
    with pytest.raises(ValueError):
        sign_verdict(_good_verdict(), b"short", "k")


# ----------------------------------------------------------------------------------------------- binding (row 1)


def _ctx(c):
    return BindingContext(task_id=c["task_id"], request_id=c["request_id"], user_text=c["user_text"], policy=c["policy"], mode=c["mode"],
                          answers=[tuple(a) for a in c["answers"]], release_text=c["release_text"], revision_of=c["revision_of"])


def test_verdict_binding_vectors():
    vectors = _load("verdict-binding")
    names = {v["name"] for v in vectors}
    assert {f"W-T{i}" for i in range(1, 9)} <= {n.split("-", 2)[0] + "-" + n.split("-", 2)[1] for n in names if n.startswith("W-T")}
    for v in vectors:
        problem = binding_problem(v["verdict"], _ctx(v["context"]))
        assert {"ok": problem is None, "raw_code": problem[0] if problem else None} == v["expect"], v["name"]


@pytest.mark.parametrize("name", ["W-T1-tampered-decision", "W-T2-substituted-answer", "W-T3-verdict-of-another-attempt",
                                  "W-T4-changed-scope-statement", "W-T5-extra-field", "W-T6-forged-clearance-state",
                                  "W-T7-status-shown-as-success", "W-T8-stripped-signature"])
def test_each_website_tampering_case_is_refused(name):
    v = json.loads((VECTORS / "verdict-binding" / f"{name}.json").read_text(encoding="utf-8"))
    problem = binding_problem(v["verdict"], _ctx(v["context"]))
    assert problem is not None and problem[0] in ("kit_dl_030", "verifier_malformed")


def test_a_bound_delivered_verdict_and_a_bound_refusal_pass_the_binding_checks():
    for name in ("deliver-bound", "refusal-bound"):
        v = json.loads((VECTORS / "verdict-binding" / f"{name}.json").read_text(encoding="utf-8"))
        assert binding_problem(v["verdict"], _ctx(v["context"])) is None


def test_the_worker_re_derives_the_decision_from_the_verdicts_own_fields():
    v = _good_verdict()
    inp = decision_input_of(v)
    assert decide(inp) == (v["delivery"]["decision"], v["delivery"]["reasons"])
    blocked = copy.deepcopy(v)
    blocked["claims"][0]["formal"] = "COUNTEREXAMPLE"
    blocked["counts"] = count_claims(ClaimFields(c["materiality"], c["formal"], c["attempt"], c["release_permitted"]) for c in blocked["claims"])
    ctx = _ctx(json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["context"])
    assert binding_problem(blocked, ctx) == ("kit_dl_030", "the decision does not follow from the verdict's own fields")


def test_not_a_verdict_is_malformed():
    ctx = _ctx(json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["context"])
    assert binding_problem([], ctx)[0] == "verifier_malformed"
    assert binding_problem({"schema": "x"}, ctx)[0] == "verifier_malformed"


# ----------------------------------------------------------------------------------------------- the counts decide (V3-M1)


def _service_verdict(listed_claims, unlisted_fields, *, policy="verified-v1"):
    """A verdict as the service makes it: decided over EVERY claim (the listed ones and those counted but not listed, as
    a claim without a verbatim excerpt or one past the 32 listed is), with its counts over every claim."""
    v = copy.deepcopy(_good_verdict())
    fields = [ClaimFields(c["materiality"], c["formal"], c["attempt"], c["release_permitted"]) for c in listed_claims] + list(unlisted_fields)
    counts = count_claims(fields)
    decision, reasons = decide(DecisionInput(policy=policy, revision_of=None, receipt_status="ACCEPTED", receipt_error_codes=(),
                                             overseer_state="AUDIT_PASSED", delivery_allowed=True, overseer_refusal=None,
                                             consolidation_status="CONSOLIDATED", blocking=counts["blocking"], unavailable=counts["unavailable"],
                                             budget_skipped=counts["budget_skipped"]))
    v["bound"]["policy"] = policy
    v["claims"] = listed_claims
    v["counts"] = counts
    v["delivery"] = {**v["delivery"], "decision": decision, "reasons": reasons,
                     "deliverable": v["delivery"]["deliverable"] if decision == "deliver" else None}
    v["summary"] = summarize(counts) if decision == "deliver" else None
    return sign_verdict(v, KEY, "verdict-vectors")


def test_an_unlisted_budget_skipped_material_claim_gives_the_worker_the_service_s_decision():
    """V3-M1: the service decided refuse_incomplete [KIT-DL-011, KIT-DL-013] over every claim; the budget-skipped material
    claim has no verbatim excerpt, so the verdict counts it but does not list it. The Worker re-derives the same decision
    from the counts, so the genuine verdict passes the binding checks (before the fix it was refused as kit_dl_030)."""
    base = _good_verdict()
    listed = [dict(base["claims"][0], formal="ENTAILED", attempt="attempted", release_permitted=False, evidence_resolved=False)]
    v = _service_verdict(listed, [ClaimFields(M, "NOT_ATTEMPTED", "skipped_budget", False)])
    assert v["delivery"]["decision"] == "refuse_incomplete" and v["delivery"]["reasons"] == ["KIT-DL-011", "KIT-DL-013"]
    assert v["counts"]["budget_skipped"] == 1 and len(v["claims"]) == 1 and v["counts"]["claims_total"] == 2
    ctx = _ctx(dict(json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["context"], release_text=None))
    assert binding_problem(v, ctx) is None
    dropped = copy.deepcopy(v)
    dropped["delivery"]["reasons"] = ["KIT-DL-011"]  # a verdict that drops the budget reason no longer follows from its counts
    assert binding_problem(dropped, ctx) == ("kit_dl_030", "the decision does not follow from the verdict's own fields")


@hsettings(max_examples=400, deadline=None)
@given(claims=st.lists(_CLAIM, min_size=1, max_size=8), listed=st.integers(min_value=0, max_value=8),
       policy=st.sampled_from(["verified-v1", "verified-v1-qualify"]))
def test_whatever_part_of_the_claims_is_listed_the_worker_re_derives_the_service_s_decision(claims, listed, policy):
    """The decision depends on the counts only: for every split of the claims into listed and counted-only ones, the
    service's verdict passes the Worker's binding checks (the decision, the reasons, the summary)."""
    fields = [_consistent(c) for c in claims]
    shown = fields[:listed]
    base = _good_verdict()["claims"][0]
    listed_claims = [dict(base, materiality=f.materiality, formal=f.formal, attempt=f.attempt, release_permitted=f.release_permitted,
                          evidence_resolved=f.release_permitted, fidelity="missing") for f in shown]
    v = _service_verdict(listed_claims, fields[listed:], policy=policy)
    ctx = _ctx(dict(json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["context"], policy=policy,
                    release_text=None if v["delivery"]["decision"] != "deliver" else
                    json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["context"]["release_text"]))
    assert binding_problem(v, ctx) is None, (v["delivery"], v["counts"])


def test_the_decision_input_carries_no_claim_list():
    """Every row reads the counts: the decision input has no list of claims to read (so nothing can be decided from the
    capped list)."""
    from dataclasses import fields as dc_fields
    names = {f.name for f in dc_fields(DecisionInput)}
    assert "claims" not in names and {"blocking", "unavailable", "budget_skipped"} <= names
