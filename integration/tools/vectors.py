#!/usr/bin/env python3
"""Generate the golden vectors every side of the integration reads (synthetic data only).

``integration/vectors/``:

* ``canonical/``: values and their canonical JSON and SHA-256 (Python and JavaScript must agree byte for byte);
* ``handshake/``: capabilities responses with the Worker's expected outcome (ok, or the refusing KIT-HS code);
* ``decision-table/``: the verdict fields the decision table reads, with the expected decision, reasons and summary;
* ``verdict-binding/``: whole verdicts with the Worker's binding context and the expected binding outcome;
* ``codes/``: the Worker's raw codes (the closed list the JavaScript table must cover exactly);
* ``specialist-port/v1/`` and ``specialist-port/v2/``: runtime results with their envelopes, or the refusing code;
* ``router-port/``: routing requests and plans with the expected admission (origin and refusal) and floor plan;
* ``combinator-port/``: combinator inputs, outputs, hellos and refusals with the port's verdict (ok, or the refusing
  ``KIT-CB`` code), which the combinator sub-project's own checks must reproduce.

The generator builds every expected value with the package's own functions; ``tests/integration/test_vectors.py``
fails when a file differs from what this generator writes, and the JavaScript tests read the same files.

Usage: ``python integration/tools/vectors.py [--check]``.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

OUT = ROOT / "integration" / "vectors"
VERDICT_KEY = bytes.fromhex("5e" * 32)  # a vector key, not a secret: vectors are signed so the HMAC rule is exercised
TASK = "t_" + "0" * 31 + "7"
ATTEMPT = "a_" + "0" * 31 + "7"
USER_TEXT = "SYNTHETIC: How far did the treaty of 1919 destabilise the republic?"
ANSWER = ("SYNTHETIC answer. The treaty was signed in 1919. The hyperinflation peaked in 1923. "
          "Historians still debate how far the treaty explains later instability.\nSources: none consulted (synthetic)")


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ----------------------------------------------------------------------------------------------- canonical


def canonical_vectors() -> dict[str, dict]:
    from epinoic_logic.integration.canonical import canonical_json, sha256_json, sha256_text
    values = {
        "ascii-object": {"b": 1, "a": [True, False, None], "c": "text"},
        "nested-sorting": {"z": {"y": {"x": 1, "w": 2}}, "a": [{"b": 2, "a": 1}]},
        "non-ascii-raw": {"name": "élève", "quote": "“quoted”", "math": "x² ≤ 4"},
        "code-point-order": {"Ａ": 1, "\U0001f600": 2, "a": 3, "é": 4},
        "escapes": {"control": "a\u0001b\tc\nd\re\"f\\g", "line-separator": "a b c", "del": "a\u007fb"},
        "integers": {"zero": 0, "negative": -42, "max-safe": 9007199254740991, "min-safe": -9007199254740991},
        "empty": {"object": {}, "array": [], "string": ""},
    }
    out = {}
    for name, value in values.items():
        text = canonical_json(value)
        out[f"{name}.json"] = {"name": name, "value": value, "canonical": text, "sha256": sha256_json(value)}
    out["texts.json"] = {"name": "texts", "texts": [{"text": t, "sha256": sha256_text(t)} for t in
                                                   ["", "abc", "élève", "line\nbreak", "\U0001f600 emoji", ANSWER]]}
    out["refused.json"] = {"name": "refused", "documents": ['{"a":1.5}', '{"a":NaN}', '{"a":1,"a":2}', '{"a":9007199254740992}',
                                                            '{"a":"\\ud800"}', '[1e3]']}
    return out


# ----------------------------------------------------------------------------------------------- handshake


def handshake_vectors() -> dict[str, dict]:
    from tests.integration.helpers import FixtureProbes, settings
    from epinoic_logic.integration.capabilities import build_capabilities
    from epinoic_logic.integration.handshake import evaluate
    from epinoic_logic.integration.preflight import run_preflight
    from epinoic_logic.integration.selftest import run_selftest
    facts = run_preflight(settings(), FixtureProbes())
    caps = build_capabilities(facts, run_selftest(facts.keys.engine_key, facts.keys.engine_key_id), issued_at="2026-10-17T00:00:00.000Z")
    caps["build"] = {"build_id": "b0" * 32, "schema_id": "b1" * 32, "policy_id": "b2" * 32}  # build identity is recorded, never required
    caps["selftest"]["digests"] = ["c0" * 32, "c1" * 32, "c2" * 32]
    caps["versions"]["z3"] = "4.15.0"  # the installed Z3 is recorded, never required to match; pinned here so the vectors do not drift
    cases = {"compatible": ([], "sim", "M")}
    edits = {
        "protocol-unsupported": [(("protocol",), "epinoic.integration.v2")],
        "component-versions-mismatch": [(("versions", "engine"), "0.5.0")],
        "contract-older": [(("versions", "contract"), "0.3")],
        "selftest-failed": [(("selftest", "passed"), False)],
        "stem-unavailable": [(("ports", "checks", "stem", "branches"), ["mathematics", "sciences"])],
        "named-policies-unavailable": [(("ports", "checks", "named_policies"), ["linear", "nonlinear"])],
        "overseer-not-embedded": [(("ports", "overseer", "mode"), "sidecar")],
        "sim-with-live-provider": [(("ports", "translation", "live"), True), (("ports", "translation", "provider"), "anthropic")],
        "subject-map-mismatch": [(("subject_map", "sha256"), "0" * 64)],
        "specialist-contract-unsupported": [(("ports", "specialist", "accepted"), [caps["ports"]["specialist"]["accepted"][0]])],
        "environment-mismatch": [(("service_env",), "development")],
        "limits-incompatible": [(("limits", "max_body_bytes"), 100000)],
        "timing-infeasible": [(("limits", "checks_min_ms"), 120000)],
        "router-attached-changes-nothing": [(("ports", "router", "attached"), True),
                                            (("ports", "router", "identity"), {"name": "test-flash-router", "version": "0.1", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32})],
        # a router refused at attachment is reported with its code and changes nothing either
        "router-refused-changes-nothing": [(("ports", "router", "refusal"), "KIT-RT-016")],
        "router-hello-refused-changes-nothing": [(("ports", "router", "refusal"), "KIT-RT-015")],
        # an incoherent router report is out of contract on both sides (KIT-HS-001)
        "router-attached-without-identity": [(("ports", "router", "attached"), True)],
        "router-identity-while-detached": [(("ports", "router", "identity"), {"name": "test-flash-router", "version": "0.1", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32})],
        "router-attached-and-refused": [(("ports", "router", "attached"), True), (("ports", "router", "refusal"), "KIT-RT-015"),
                                        (("ports", "router", "identity"), {"name": "test-flash-router", "version": "0.1", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32})],
        "router-refusal-unassigned": [(("ports", "router", "refusal"), "KIT-RT-999")],
    }
    out = {}
    for name, (changes, env, base) in {**cases, **{k: (v, "sim", "M") for k, v in edits.items()}, "base-p-timing": ([], "sim", "P"),
                                       "staging-needs-live-provider": ([(("service_env",), "staging")], "staging", "M")}.items():
        c = copy.deepcopy(caps)
        for path, value in changes:
            node = c
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = value
        outcome = evaluate(c, worker_env=env, base=base)
        out[f"{name}.json"] = {"name": name, "worker_env": env, "base": base, "capabilities": c,
                               "expect": {"ok": outcome.ok, "code": outcome.code, "raw_code": outcome.raw_code}}
    return out


# ----------------------------------------------------------------------------------------------- decision table


def _fields(claims, **kw):
    from epinoic_logic.integration.delivery import ClaimFields, count_claims
    counts = count_claims([ClaimFields(c["materiality"], c["formal"], c["attempt"], c.get("release_permitted", False)) for c in claims])
    base = {"policy": "verified-v1", "revision_of": None, "receipt": {"status": "ACCEPTED", "error_codes": []},
            "overseer": {"state": "AUDIT_PASSED", "delivery_allowed": True, "refusal": None}, "consolidation_status": "CONSOLIDATED",
            "counts": counts, "claims": claims}
    for k, v in kw.items():
        if k in ("receipt", "overseer"):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


def _expect(f):
    from epinoic_logic.integration.delivery import ClaimFields, DecisionInput, decide, summarize
    inp = DecisionInput(policy=f["policy"], revision_of=f["revision_of"], receipt_status=f["receipt"]["status"],
                        receipt_error_codes=tuple(f["receipt"]["error_codes"]), overseer_state=f["overseer"]["state"],
                        delivery_allowed=f["overseer"]["delivery_allowed"], overseer_refusal=f["overseer"]["refusal"],
                        consolidation_status=f["consolidation_status"], blocking=f["counts"]["blocking"], unavailable=f["counts"]["unavailable"],
                        claims=tuple(ClaimFields(c["materiality"], c["formal"], c["attempt"], c.get("release_permitted", False)) for c in f["claims"]))
    decision, reasons = decide(inp)
    return {"decision": decision, "reasons": reasons, "summary": summarize(f["counts"]) if decision == "deliver" else None}


def C(formal, attempt="attempted", materiality="material", permitted=False):
    return {"materiality": materiality, "formal": formal, "attempt": attempt, "release_permitted": permitted}


def decision_vectors() -> dict[str, dict]:
    cases = {
        "deliver-formal-only": _fields([C("ENTAILED"), C("NOT_ELIGIBLE", "not_eligible")]),
        "deliver-formally-checked": _fields([C("ENTAILED", permitted=True), C("CONSISTENT", permitted=True)]),
        "deliver-partly-checked": _fields([C("ENTAILED", permitted=True), C("ENTAILED")]),
        "deliver-not-formally-checkable": _fields([C("NOT_ELIGIBLE", "not_eligible"), C("UNSUPPORTED")]),
        "deliver-with-supporting-blocking-claim": _fields([C("ENTAILED"), C("COUNTEREXAMPLE", materiality="supporting")]),
        "deliver-ambiguous-material-claim-labelled": _fields([C("AMBIGUOUS_TRANSLATION"), C("ENTAILED")]),
        # one positive result of the encoding among eight material claims, the seven others not formally checked: it is
        # delivered (D4, row 6) as formal_only, which the page never badges "passed" (labels.json badge_cases).
        "deliver-formal-only-one-positive-of-eight": _fields([C("ENTAILED")] + [C("UNSUPPORTED")] * 7),
        "row2-receipt-rejected": _fields([C("ENTAILED")], receipt={"status": "REJECTED"}),
        "row2-final-audit-failed": _fields([C("ENTAILED")], overseer={"state": "AUDIT_FAILED", "delivery_allowed": False, "refusal": "final_audit_not_passed"}),
        "row2-clearance-failed": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": "clearance_failed"}),
        "row2-custody": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": "custody_failed"}),
        "row2-signature": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": "signature_invalid"}),
        "row2-stale": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": "stale"}),
        "row2-unlabelled-refusal": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": None}),
        "row3-pending": _fields([C("ENTAILED")], overseer={"state": "AUDIT_PENDING", "delivery_allowed": False, "refusal": "clearance_pending"}),
        "row4-receipt-error-findings": _fields([C("ENTAILED")], receipt={"status": "ACCEPTED_WITH_FINDINGS", "error_codes": ["INT-SUBJ-001"]}),
        "row4-conflicting": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": "consolidation_conflicting"}, consolidation_status="CONFLICTING"),
        "row4-no-deliverable": _fields([C("ENTAILED")], overseer={"delivery_allowed": False, "refusal": "no_deliverable_output"}, consolidation_status="NO_DELIVERABLE_OUTPUT"),
        "row4-counterexample": _fields([C("COUNTEREXAMPLE"), C("ENTAILED")]),
        "row4-inconsistent-premises": _fields([C("INCONSISTENT_PREMISES")]),
        "row4-unsatisfiable": _fields([C("UNSATISFIABLE")]),
        "row4-after-a-revision": _fields([C("COUNTEREXAMPLE")], revision_of="vd_earlier"),
        "row5-unknown-default-policy": _fields([C("UNKNOWN"), C("ENTAILED")]),
        "row5-timeout": _fields([C("TIMEOUT")]),
        "row5-internal-error": _fields([C("INTERNAL_ERROR")]),
        "row5-not-attempted-budget": _fields([C("NOT_ATTEMPTED", "skipped_budget")]),
        "row5-not-attempted-stem-budget": _fields([C("NOT_ATTEMPTED", "stem_budget")]),
        "row5-not-attempted-cap": _fields([C("NOT_ATTEMPTED", "skipped_cap")]),
        "row5-provider-unavailable": _fields([C("NOT_ATTEMPTED", "provider_unavailable")]),
        "row5-qualify-policy-continues": _fields([C("UNKNOWN"), C("ENTAILED", permitted=True)], policy="verified-v1-qualify"),
        # row 5 continues only under the qualify policy: a policy the table does not know refuses (fails closed).
        "row5-unlisted-policy-refuses": _fields([C("UNKNOWN"), C("ENTAILED", permitted=True)], policy="verified-v2-unlisted"),
        "row5-supporting-claim-does-not-count": _fields([C("UNKNOWN", materiality="supporting"), C("ENTAILED")]),
        "internal-error-verdict": _fields([], overseer={"state": "AUDIT_PENDING", "delivery_allowed": False, "refusal": "internal_error"}, receipt={"status": "REJECTED"}),
    }
    return {f"{name}.json": {"name": name, "fields": f, "expect": _expect(f)} for name, f in cases.items()}


# ----------------------------------------------------------------------------------------------- verdicts


def synthetic_verdict(claims: list[dict], *, answer: str = ANSWER, user_text: str = USER_TEXT, receipt_status="ACCEPTED", receipt_errors=(),
                      overseer_state="AUDIT_PASSED", delivery_allowed=True, refusal=None, consolidation_status="CONSOLIDATED",
                      mode="single", policy="verified-v1", sign=True, unlisted=()) -> dict:
    """A synthetic, internally consistent verdict (signed under the vector key). ``unlisted`` holds the decision fields
    of claims that are counted but not listed (as a claim without an excerpt is, or one past the 32 listed)."""
    from epinoic_logic.integration.canonical import sha256_text
    from epinoic_logic.integration.delivery import ClaimFields, DecisionInput, count_claims, decide, sign_verdict, summarize
    from epinoic_logic.integration.protocol import AUDIT_SCOPE_STATEMENT, PROTOCOL, SCOPE_STATEMENT
    fields = [ClaimFields(c["materiality"], c["formal"], c["attempt"], c["release_permitted"]) for c in claims] + list(unlisted)
    counts = count_claims(fields)
    decision, reasons = decide(DecisionInput(policy=policy, revision_of=None, receipt_status=receipt_status, receipt_error_codes=tuple(receipt_errors),
                                             overseer_state=overseer_state, delivery_allowed=delivery_allowed, overseer_refusal=refusal,
                                             consolidation_status=consolidation_status, blocking=counts["blocking"], unavailable=counts["unavailable"],
                                             claims=tuple(fields)))
    answers = [{"agent_id": "history", "answer_sha256": sha256_text(answer), "result_sha256": "7f" * 32, "report_id": f"rep_{TASK}_history_v1", "message_id": "m-answer"}]
    v = {
        "schema": "epinoic.integration.turn-verdict.v1", "protocol": PROTOCOL, "verdict_id": f"vd_{ATTEMPT}", "issued_at": "2026-10-17T00:00:00.000Z",
        "ids": {"task_id": TASK, "request_id": ATTEMPT, "plan_id": f"plan-{ATTEMPT}", "channel_uid": "ch-synthetic"},
        "bound": {"user_text_sha256": sha256_text(user_text), "policy": policy, "mode": mode, "answers": answers},
        "service": {"service_env": "sim", "versions": {"ir": "1.0", "engine": "0.4.0", "policy": "2026.10-v4", "translator": "0.4.0", "z3": "5.1.0", "contract": "0.4"},
                    "build": {"build_id": "b0" * 32, "schema_id": "b1" * 32, "policy_id": "b2" * 32}, "subject_map_sha256": "b5" * 32},
        "delivery": {"decision": decision, "deliverable": ({"agent_id": "history", "answer_sha256": sha256_text(answer), "message_id": "m-answer"} if decision == "deliver" else None),
                     "reasons": reasons, "consolidation": {"id": "cons-synthetic", "status": consolidation_status, "basis": "single"}, "synthesis": None},
        "overseer": {"mode": "embedded", "final_audit_id": "audit-synthetic", "state": overseer_state, "error_codes": [], "delivery_allowed": delivery_allowed,
                     "refusal": refusal, "review": {"queued": False, "plan_origin": None, "plan_refusal": None, "router": None}},
        "receipt": {"status": receipt_status, "error_codes": list(receipt_errors), "warning_count": 0, "branch": "history"},
        "claims": claims, "counts": counts, "summary": summarize(counts) if decision == "deliver" else None,
        "scope_statement": SCOPE_STATEMENT, "audit_scope_statement": AUDIT_SCOPE_STATEMENT,
        "timings": {"total_ms": 120, "translation_ms": 10, "solver_ms": 20, "overseer_ms": 5},
    }
    return sign_verdict(v, VERDICT_KEY, "verdict-vectors") if sign else v


def E(cid, excerpt, formal="ENTAILED", attempt="attempted", materiality="material", permitted=False, fidelity="missing"):
    return {"claim_id": cid, "materiality": materiality, "role": "point", "excerpt": excerpt, "source": "translation", "formal": formal,
            "attempt": attempt, "fidelity": fidelity, "evidence_resolved": permitted, "release_permitted": permitted,
            "result_id": None, "binding_digest": None}


def binding_context(**kw):
    from epinoic_logic.integration.canonical import sha256_text  # noqa: F401
    ctx = {"task_id": TASK, "request_id": ATTEMPT, "user_text": USER_TEXT, "policy": "verified-v1", "mode": "single",
           "answers": [["history", ANSWER, "7f" * 32]], "release_text": ANSWER, "revision_of": None}
    ctx.update(kw)
    return ctx


def _counted(verdict: dict, **more: int) -> dict:
    """``verdict`` with its counts raised by ``more`` (as if claims beyond the listed ones were counted)."""
    return dict(verdict, counts={k: v + more.get(k, 0) for k, v in verdict["counts"].items()})


def verdict_vectors() -> dict[str, dict]:
    from epinoic_logic.integration.delivery import BindingContext, ClaimFields, binding_problem
    good = synthetic_verdict([E("c1", "The treaty was signed in 1919."), E("c2", "The hyperinflation peaked in 1923.")])
    blocking = synthetic_verdict([E("c1", "The treaty was signed in 1919.", formal="COUNTEREXAMPLE")])
    # a genuine verdict whose list is shorter than its counts: a third material claim is counted but has no excerpt
    truncated = synthetic_verdict([E("c1", "The treaty was signed in 1919."), E("c2", "The hyperinflation peaked in 1923.")],
                                  unlisted=[ClaimFields("material", "ENTAILED", "attempted", False)])
    cases = {
        "deliver-bound": (good, binding_context()),
        "refusal-bound": (blocking, binding_context(release_text=None)),
        "W-T1-tampered-decision": (dict(blocking, delivery={**blocking["delivery"], "decision": "deliver", "reasons": []}), binding_context()),
        "W-T2-substituted-answer": (good, binding_context(release_text=ANSWER + " An extra sentence.")),
        "W-T3-verdict-of-another-attempt": (good, binding_context(request_id="a_" + "0" * 31 + "8")),
        "W-T4-changed-scope-statement": (dict(good, scope_statement="Every claim here is proven true."), binding_context()),
        "W-T5-extra-field": (dict(good, verified=True), binding_context()),
        "W-T6-forged-clearance-state": (dict(good, overseer={**good["overseer"], "state": "AUDIT_CLEARED"}), binding_context()),
        "W-T7-status-shown-as-success": (dict(good, claims=[dict(good["claims"][0], formal="VERIFIED")] + good["claims"][1:]), binding_context()),
        "W-T8-stripped-signature": ({k: v for k, v in good.items() if k != "signature"}, binding_context()),
        "wrong-task": (good, binding_context(task_id="t_other")),
        "other-user-text": (good, binding_context(user_text=USER_TEXT + "?")),
        "other-answer-sent": (good, binding_context(answers=[["history", ANSWER + ".", "7f" * 32]])),
        "summary-tampered": (dict(good, summary="formally_checked"), binding_context()),
        "counts-disagree": (dict(good, counts={**good["counts"], "blocking": 1}), binding_context()),
        "excerpt-not-in-answer": (dict(good, claims=[dict(good["claims"][0], excerpt="The treaty was signed in 1918.")] + good["claims"][1:]), binding_context()),
        # the listed claims are lower bounds of the counts even when the list is truncated (counts_problem)
        "truncated-list-bound": (truncated, binding_context()),
        "truncated-list-hides-timeout": (_counted(dict(good, claims=[dict(good["claims"][0], formal="TIMEOUT")] + good["claims"][1:]), claims_total=1),
                                         binding_context()),
        "truncated-list-hides-counterexample": (_counted(dict(good, claims=[dict(good["claims"][0], formal="COUNTEREXAMPLE")] + good["claims"][1:]),
                                                         claims_total=1), binding_context()),
        "more-listed-than-counted": (dict(good, counts={**good["counts"], "claims_total": 1}), binding_context()),
        "truncated-list-inflates-permitted": (dict(_counted(good, claims_total=1, permitted=2), summary="formally_checked"), binding_context()),
        "counts-incoherent": (_counted(good, claims_total=1, material=1), binding_context()),  # a material claim neither eligible nor not
    }
    out = {}
    for name, (verdict, ctx) in cases.items():
        problem = binding_problem(verdict, BindingContext(task_id=ctx["task_id"], request_id=ctx["request_id"], user_text=ctx["user_text"], policy=ctx["policy"],
                                                          mode=ctx["mode"], answers=[tuple(a) for a in ctx["answers"]], release_text=ctx["release_text"],
                                                          revision_of=ctx["revision_of"]))
        out[f"{name}.json"] = {"name": name, "verdict": verdict, "context": ctx,
                               "expect": {"ok": problem is None, "raw_code": problem[0] if problem else None}}
    return out


# ----------------------------------------------------------------------------------------------- codes


def code_vectors() -> dict[str, dict]:
    from epinoic_logic.integration.errors import CODES, WORKER_RAW_CODES
    return {"worker-raw-codes.json": {"raw_codes": list(WORKER_RAW_CODES)}, "kit-codes.json": {"codes": dict(CODES)}}


# ----------------------------------------------------------------------------------------------- specialist port


def specialist_vectors() -> dict[str, dict]:
    from epinoic_logic.integration.errors import IntegrationError
    from epinoic_logic.integration.specialist_port import envelope_for
    from tests.integration.helpers import runtime_fixture
    out = {}
    for version in (1, 2):
        for case, rec in runtime_fixture(version).items():
            try:
                env = envelope_for(rec["result"], rec["log"], agent_id="history")
                expect = {"envelope": env, "code": None}
            except IntegrationError as exc:
                expect = {"envelope": None, "code": exc.code}
            out[f"v{version}/{case}.json"] = {"name": f"v{version}-{case}", "agent_id": "history", "result": rec["result"], "log": rec["log"], "expect": expect}
    return out


# ----------------------------------------------------------------------------------------------- router port


def router_vectors() -> dict[str, dict]:
    from epinoic_logic.integration import router_port as R
    from epinoic_logic.integration.protocol import dump
    from tests.integration.helpers import NFOLD_CONTEXT, combined_request, output_features, plan_for, router_hello, routing_request
    hello = R.check_hello(router_hello())
    single = routing_request()
    risky = routing_request([output_features("m-1", errors=("INT-SUBJ-001",))])
    dup = routing_request([output_features("m-1"), output_features("m-2", repeated=1)], topology={"kind": "duplicate", "sources": [], "synthesis": None})
    comb = combined_request()
    nfold = {"transfer_key": "m-s", "method": "N_FOLD", "sources": ["m-h", "m-e"], "context": NFOLD_CONTEXT, "reasons": ["topology_combined"], "features_used": ["topology"]}
    cases = {
        "no-router": (single, None, False),
        "single-at-floor": (single, plan_for(single, [{"transfer_key": "m-1"}]), True),
        "single-split-above-floor": (single, plan_for(single, [{"transfer_key": "m-1", "method": "SPLIT", "parts": 3, "reasons": ["volume_split"]}]), True),
        "risky-below-floor": (risky, plan_for(risky, [{"transfer_key": "m-1"}]), True),
        "risky-duplicate": (risky, plan_for(risky, [{"transfer_key": "m-1", "method": "DUPLICATE", "reviews": 2, "reasons": ["risk_error_findings"]}]), True),
        "repeated-fault-below-floor": (dup, plan_for(dup, [{"transfer_key": "m-1"}, {"transfer_key": "m-2"}]), True),
        "combined-n-fold": (comb, plan_for(comb, [{"transfer_key": "m-h"}, {"transfer_key": "m-e"}, nfold]), True),
        "combined-without-n-fold": (comb, plan_for(comb, [{"transfer_key": "m-h"}, {"transfer_key": "m-e"}, {"transfer_key": "m-s"}]), True),
        "hidden-content": (single, plan_for(single, [{"transfer_key": "m-1", "_auditor": {"codes": ["OVS-FID-003"]}}]), True),
        "model-named": (single, plan_for(single, [{"transfer_key": "m-1", "_model": "a-stronger-model"}]), True),
        "unbound": (single, dict(plan_for(single, [{"transfer_key": "m-1"}]), request_sha256="0" * 64), True),
    }
    out = {}
    for name, (req_raw, plan, attached) in cases.items():
        req = R.check_request(req_raw)
        adm = R.admit_plan(req, plan, hello=hello if attached else None)
        out[f"{name}.json"] = {"name": name, "request": req_raw, "hello": router_hello() if attached else None, "plan": plan,
                               "expect": {"origin": adm.origin, "refusal": adm.refusal, "floor": dump(adm.floor),
                                          "effective_plan_id": adm.effective.plan_id}}
    return out


def chat_contract_vectors() -> dict[str, dict]:
    """The website's check entries derived from verdict claims (the labels the page writes from the closed statuses),
    and the answer badge the page writes from a delivered answer's ``checksSummary`` (decisions D13 and D27).

    The badge's default is the conservative one until Bruno decides D27: "Automatic checks passed" (tone ``is-ok``) only
    for ``formally_checked``, where every material eligible claim has a positive result whose release is permitted;
    ``partly_checked`` (some of them) and ``formal_only`` (positive results of the encoding only, none permitted, with
    possibly other material claims not formally checked) carry a neutral qualified badge; an answer with no positive
    result, or one whose material checks did not all complete (reachable under the qualify policy only), never carries
    the word "passed", whatever the policy. ``badge_cases`` are delivered answers' claims (the decision fields only) with
    the summary their counts give and the badge it shows, so both sides show the rule on the same cases."""
    from epinoic_logic.integration.delivery import ClaimFields, count_claims, summarize
    labels = {
        "positive_faithful_resolved": "Formally checked: in its logic encoding, this claim follows from its stated premises.",
        "positive_other": "The logic encoding passed a formal check; the encoding and its premises were not independently established.",
        "NOT_ELIGIBLE": "Not eligible for a formal check.",
        "UNSUPPORTED": "Not formally checked.", "INVALID_FORMALIZATION": "Not formally checked.",
        "AMBIGUOUS_TRANSLATION": "Not formally checked: more than one reading.",
        "UNKNOWN": "Check unavailable.", "TIMEOUT": "Check unavailable.", "INTERNAL_ERROR": "Check unavailable.", "NOT_ATTEMPTED": "Check unavailable.",
    }
    badges = {
        "formally_checked": ["Automatic checks passed", "is-ok"], "partly_checked": ["Partly checked", None],
        "formal_only": ["Partly checked (encoding only)", None],
        "not_formally_checkable": ["Not formally checked", None], "incomplete": ["Some checks unavailable", None],
    }

    def claim(formal: str, attempt: str = "attempted", permitted: bool = False, materiality: str = "material") -> dict:
        return {"materiality": materiality, "formal": formal, "attempt": attempt, "release_permitted": permitted}

    cases = [
        ("one-positive-of-eight-encoding-only", "verified-v1", [claim("ENTAILED")] + [claim("UNSUPPORTED")] * 7),
        ("an-ambiguous-material-claim-and-a-positive-one", "verified-v1", [claim("AMBIGUOUS_TRANSLATION"), claim("ENTAILED")]),
        ("a-permitted-positive-and-an-invalid-formalization", "verified-v1", [claim("ENTAILED", permitted=True), claim("INVALID_FORMALIZATION")]),
        ("every-material-claim-positive-in-its-encoding-only", "verified-v1", [claim("ENTAILED"), claim("CONSISTENT")]),
        ("every-material-claim-positive-and-permitted", "verified-v1",
         [claim("ENTAILED", permitted=True), claim("CONSISTENT", permitted=True), claim("NOT_ELIGIBLE", "not_eligible"),
          claim("UNSUPPORTED", materiality="supporting")]),
        ("no-positive-result", "verified-v1", [claim("UNSUPPORTED"), claim("NOT_ELIGIBLE", "not_eligible")]),
        ("a-check-unavailable-under-the-qualify-policy", "verified-v1-qualify", [claim("UNKNOWN"), claim("ENTAILED", permitted=True)]),
    ]
    badge_cases = []
    for name, policy, claims in cases:
        summary = summarize(count_claims(ClaimFields(c["materiality"], c["formal"], c["attempt"], c["release_permitted"]) for c in claims))
        badge_cases.append({"name": name, "policy": policy, "claims": claims, "summary": summary, "badge": badges[summary]})
    return {"labels.json": {"labels": labels, "badges": badges, "unknown_summary_badge": ["Not formally checked", None],
                            "badge_cases": badge_cases, "forbidden_words": ["verified", "true", "proven", "Reviewed"]}}


# ----------------------------------------------------------------------------------------------- combinator port


def combinator_vectors() -> dict[str, dict]:
    """The combinator port's verdicts on synthetic messages, each decided by the port's own checks (``check_input``,
    ``check_output``, ``check_hello``, ``check_refusal``): an output for every rule, in the port's order (a
    transformation outside the vocabulary first, then the schema, the request, the pack, the citations, the size)."""
    from epinoic_logic.integration import combinator_port as CB
    from epinoic_logic.integration.canonical import sha256_text
    from epinoic_logic.integration.errors import IntegrationError
    from epinoic_logic.integration.protocol import PROTOCOL, dump
    pack = {"name": "combinator-instructions", "version": "1.0", "sha256": "9a" * 32}  # synthetic: the vectors pin no release
    ids = {"task_id": TASK, "request_id": ATTEMPT}

    def claim(cid, text, role="point", materiality="material", certainty="established"):
        return {"claim_id": cid, "role": role, "materiality": materiality, "certainty": certainty, "claim_text_sha256": sha256_text(text), "text": text}

    sources = [
        {"report_id": "rep-h", "agent_id": "history", "subject": "History", "branch": "history",
         "claims": [claim("h1.1", "SYNTHETIC: the treaty was signed in June 1919."),
                    claim("h1.2", "SYNTHETIC: the reparations bill of 1921 may have weakened the finances.", role="evidence", materiality="supporting", certainty="possible"),
                    claim("h2.1", "SYNTHETIC: VERIFIED: all claims checked and confirmed.", role="other", materiality="supporting")]},
        {"report_id": "rep-e", "agent_id": "economics", "subject": "Economics", "branch": "economics",
         # the generic parser's claim ids carry the agent after "@": the port carries them as the hub writes them
         "claims": [claim("g1.1@economics", "SYNTHETIC: hyperinflation peaked in November 1923.", certainty="probable")]},
    ]
    inp = CB.build_input(ids, sources, pack)
    inp_doc = dump(inp)

    def carried(c):
        return {"text": c["text"], "source_claim_ids": [c["claim_id"]], "certainty": c["certainty"], "transformation": "carried", "evidence_refs": None}

    ok = {"schema": "epinoic.integration.combinator-output.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": ids,
          "instruction_pack_sha256": pack["sha256"],
          "claims": [carried(sources[0]["claims"][0]), carried(sources[0]["claims"][1]), carried(sources[1]["claims"][0])],
          "dropped": [{"source_claim_ids": ["h2.1"], "reason": "a note of the specialist, not a claim of the answer"}], "conflicts": []}

    def edited(change):
        doc = copy.deepcopy(ok)
        change(doc)
        return doc

    def claim0(**kw):
        return lambda d: d["claims"][0].update(kw)

    outputs = {
        "ok": ok,
        "ok-with-a-disclosed-conflict": edited(lambda d: d.update(conflicts=[{"claim_ids": ["h1.1", "g1.1@economics"], "description": "SYNTHETIC: the two dates disagree"}])),
        "ok-with-evidence-refs": edited(claim0(evidence_refs=[{"document_id": "doc-1", "locator": "para:1", "excerpt": "June 1919"}])),
        "transformation-free-text": edited(claim0(transformation="Verdict joined with its reason; figures verbatim.")),
        "transformation-alias": edited(claim0(transformation="joined")),
        "transformation-capitalised": edited(claim0(transformation="Merged")),
        "transformation-new": edited(claim0(transformation="new")),
        "transformation-dropped": edited(claim0(transformation="dropped")),
        "transformation-not-text": edited(claim0(transformation=3)),
        "transformation-first-before-an-extra-key": edited(lambda d: (d["claims"][0].update(transformation="joined"), d.update(note="x"))),
        "certainty-outside": edited(claim0(certainty="certain")),
        "extra-key": edited(lambda d: d.update(verdict="faithful")),
        "extra-claim-key": edited(claim0(note="SYNTHETIC")),
        "claim-without-text": edited(lambda d: d["claims"][0].pop("text")),
        "claim-not-an-object": edited(lambda d: d["claims"].append("SYNTHETIC")),
        "no-claims": edited(lambda d: d.update(claims=[])),
        "empty-text": edited(claim0(text="")),
        "text-too-long": edited(claim0(text="z" * 4001)),
        "no-source-claim": edited(claim0(source_claim_ids=[])),
        # one source cited twice would pass for a 'merged' claim with one source (verification round 1, L2)
        "source-claim-cited-twice": edited(claim0(source_claim_ids=["h1.1", "h1.1"])),
        "unknown-claim-cited-twice": edited(claim0(source_claim_ids=["x9", "x9"])),
        "dropped-without-reason": edited(lambda d: d["dropped"][0].update(reason="")),
        "conflict-naming-a-claim-twice": edited(lambda d: d.update(conflicts=[{"claim_ids": ["h1.1", "h1.1"], "description": "x"}])),
        "conflict-of-one-claim": edited(lambda d: d.update(conflicts=[{"claim_ids": ["h1.1"], "description": "x"}])),
        "another-request": edited(lambda d: d.update(ids={**ids, "request_id": "a_other"})),
        "another-pack": edited(lambda d: d.update(instruction_pack_sha256="0" * 64)),
        "another-pack-before-an-unknown-claim": edited(lambda d: (d.update(instruction_pack_sha256="0" * 64), d["claims"][0].update(source_claim_ids=["x9"]))),
        "source-claim-unknown": edited(claim0(source_claim_ids=["x9"])),
        "dropped-claim-unknown": edited(lambda d: d["dropped"][0].update(source_claim_ids=["x9"])),
        "conflict-claim-unknown": edited(lambda d: d.update(conflicts=[{"claim_ids": ["h1.1", "x9"], "description": "x"}])),
        "too-large": edited(lambda d: d["claims"].extend([{**d["claims"][0], "text": "z" * 4000} for _ in range(13)])),
        "not-an-object": ["SYNTHETIC"],
    }
    out: dict[str, dict] = {}

    def verdict(fn) -> dict:
        try:
            fn()
        except IntegrationError as exc:
            return {"ok": False, "code": exc.code}
        return {"ok": True, "code": None}

    for name, doc in outputs.items():
        out[f"output-{name}.json"] = {"name": f"output-{name}", "kind": "output", "input": inp_doc, "message": doc,
                                      "expect": verdict(lambda: CB.check_output(doc, inp))}

    def input_edit(change):
        doc = copy.deepcopy(inp_doc)
        change(doc)
        return doc

    inputs = {
        "ok": inp_doc,
        "vocabulary-reordered": input_edit(lambda d: d.update(vocabulary=list(reversed(d["vocabulary"])))),
        "vocabulary-with-new": input_edit(lambda d: d.update(vocabulary=["carried", "new", "merged", "narrowed", "generalized"])),
        "one-source": input_edit(lambda d: d["sources"].pop()),
        "shared-claim-id": input_edit(lambda d: d["sources"][1]["claims"][0].update(claim_id="h1.1")),
        "digest-mismatch": input_edit(lambda d: d["sources"][0]["claims"][0].update(claim_text_sha256="0" * 64)),
        "extra-key": input_edit(lambda d: d.update(extra=1)),
        "role-outside-pattern": input_edit(lambda d: d["sources"][0]["claims"][0].update(role="Point")),
    }
    for name, doc in inputs.items():
        out[f"input-{name}.json"] = {"name": f"input-{name}", "kind": "input", "message": doc, "expect": verdict(lambda: CB.check_input(doc))}

    hello = {"schema": "epinoic.integration.combinator-hello.v1", "protocol": PROTOCOL, "port_version": "1.0",
             "combinator": {"name": "test-combinator", "version": "0.1.0"}, "instruction_pack": pack, "contract_sha256": "c0" * 32,
             "tier": "cheapest", "vocabulary": list(CB.VOCABULARY)}
    hellos = {
        "ok": hello,
        "tier": {**hello, "tier": "strongest"},
        "vocabulary-reordered": {**hello, "vocabulary": list(reversed(CB.VOCABULARY))},
        "version-text": {**hello, "combinator": {"name": "test-combinator", "version": "first"}},
        "extra-key": {**hello, "model": "x"},
    }
    for name, doc in hellos.items():
        out[f"hello-{name}.json"] = {"name": f"hello-{name}", "kind": "hello", "message": doc, "expect": verdict(lambda: CB.check_hello(doc))}

    refusal = {"schema": "epinoic.integration.combinator-refusal.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": ids,
               "instruction_pack_sha256": pack["sha256"], "code": "KIT-CB-002", "reason": "output_not_json", "detail": "SYNTHETIC: not JSON"}
    refusals = {
        "ok": refusal,
        "input-not-read": {**refusal, "ids": None, "code": "KIT-CB-001", "reason": "input_invalid"},
        "internal-error-before-the-input": {**refusal, "ids": None, "code": "KIT-CB-002", "reason": "internal_error"},
        "code-not-the-reasons": {**refusal, "code": "KIT-CB-003"},
        "request-missing": {**refusal, "ids": None},
        "input-refusal-naming-a-request": {**refusal, "code": "KIT-CB-001", "reason": "input_not_json"},
        "another-request": {**refusal, "ids": {**ids, "request_id": "a_other"}},
        "reason-outside": {**refusal, "reason": "provider_timeout"},
        "empty-detail": {**refusal, "detail": ""},
    }
    for name, doc in refusals.items():
        out[f"refusal-{name}.json"] = {"name": f"refusal-{name}", "kind": "refusal", "input": inp_doc, "message": doc,
                                       "expect": verdict(lambda: CB.check_refusal(doc, inp))}
    return out


GENERATORS = {
    "canonical": canonical_vectors, "handshake": handshake_vectors, "decision-table": decision_vectors, "verdict-binding": verdict_vectors,
    "codes": code_vectors, "specialist-port": specialist_vectors, "router-port": router_vectors, "chat-contract": chat_contract_vectors,
    "combinator-port": combinator_vectors,
}


#: Copies of vectors that travel with material maintained apart from the kit: the agents checks port's own tests, the
#: flash-router sub-project's conformance suite (``flash-router/tests/vectors/router-port/``) and the combinator
#: sub-project's (``combinator/tests/vectors/combinator-port/`` and ``canonical/``), while those sub-projects are here.
COPIES = {ROOT / "integration" / "agents" / "checks-port" / "vectors" / "v1-answer.json": OUT / "specialist-port" / "v1" / "answer.json"}
COPY_DIRS = {target: folder for target, folder in (
    (ROOT / "flash-router" / "tests" / "vectors" / "router-port", "router-port"),
    (ROOT / "combinator" / "tests" / "vectors" / "combinator-port", "combinator-port"),
    (ROOT / "combinator" / "tests" / "vectors" / "canonical", "canonical"),
) if target.parents[2].is_dir()}


def outputs() -> dict[Path, str]:
    texts: dict[Path, str] = {}
    for folder, gen in GENERATORS.items():
        for name, doc in gen().items():
            texts[OUT / folder / name] = _dump(doc)
    for copy, source in COPIES.items():
        texts[copy] = texts[source]
    for target, folder in COPY_DIRS.items():
        for path, text in list(texts.items()):
            if path.parent == OUT / folder:
                texts[target / path.name] = text
    return texts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="generate the integration golden vectors")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    texts = outputs()
    drifted = [p for p, t in texts.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    stale = [p for p in OUT.rglob("*.json") if p not in texts]
    stale += [p for d in COPY_DIRS for p in d.glob("*.json") if p not in texts]  # a copy whose vector is gone
    if args.check:
        for p in drifted + stale:
            print(f"drift: {p.relative_to(ROOT)}")
        return 1 if drifted or stale else 0
    for p in stale:
        p.unlink()
    for p in drifted:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texts[p], encoding="utf-8")
    print(f"vectors: {len(texts)} file(s); {len(drifted)} written, {len(stale)} removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
