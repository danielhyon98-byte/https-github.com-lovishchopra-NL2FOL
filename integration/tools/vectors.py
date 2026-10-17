#!/usr/bin/env python3
"""Generate the golden vectors every side of the integration reads (synthetic data only).

``integration/vectors/``:

* ``canonical/``: values and their canonical JSON and SHA-256 (Python and JavaScript must agree byte for byte);
* ``handshake/``: capabilities responses with the Worker's expected outcome (ok, or the refusing KIT-HS code);
* ``decision-table/``: the verdict fields the decision table reads, with the expected decision, reasons and summary;
* ``verdict-binding/``: whole verdicts with the Worker's binding context and the expected binding outcome;
* ``codes/``: the Worker's raw codes (the closed list the JavaScript table must cover exactly);
* ``specialist-port/v1/`` and ``specialist-port/v2/``: runtime results with their envelopes, or the refusing code;
* ``router-port/``: routing requests and plans with the expected admission (origin and refusal) and floor plan.

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
        "row5-supporting-claim-does-not-count": _fields([C("UNKNOWN", materiality="supporting"), C("ENTAILED")]),
        "internal-error-verdict": _fields([], overseer={"state": "AUDIT_PENDING", "delivery_allowed": False, "refusal": "internal_error"}, receipt={"status": "REJECTED"}),
    }
    return {f"{name}.json": {"name": name, "fields": f, "expect": _expect(f)} for name, f in cases.items()}


# ----------------------------------------------------------------------------------------------- verdicts


def synthetic_verdict(claims: list[dict], *, answer: str = ANSWER, user_text: str = USER_TEXT, receipt_status="ACCEPTED", receipt_errors=(),
                      overseer_state="AUDIT_PASSED", delivery_allowed=True, refusal=None, consolidation_status="CONSOLIDATED",
                      mode="single", policy="verified-v1", sign=True) -> dict:
    """A synthetic, internally consistent verdict (signed under the vector key)."""
    from epinoic_logic.integration.canonical import sha256_text
    from epinoic_logic.integration.delivery import ClaimFields, DecisionInput, count_claims, decide, sign_verdict, summarize
    from epinoic_logic.integration.protocol import AUDIT_SCOPE_STATEMENT, PROTOCOL, SCOPE_STATEMENT
    fields = [ClaimFields(c["materiality"], c["formal"], c["attempt"], c["release_permitted"]) for c in claims]
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


def verdict_vectors() -> dict[str, dict]:
    from epinoic_logic.integration.delivery import BindingContext, binding_problem
    good = synthetic_verdict([E("c1", "The treaty was signed in 1919."), E("c2", "The hyperinflation peaked in 1923.")])
    blocking = synthetic_verdict([E("c1", "The treaty was signed in 1919.", formal="COUNTEREXAMPLE")])
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
    """The website's check entries derived from verdict claims (the labels the page writes from the closed statuses)."""
    labels = {
        "positive_faithful_resolved": "Formally checked: in its logic encoding, this claim follows from its stated premises.",
        "positive_other": "The logic encoding passed a formal check; the encoding and its premises were not independently established.",
        "NOT_ELIGIBLE": "Not eligible for a formal check.",
        "UNSUPPORTED": "Not formally checked.", "INVALID_FORMALIZATION": "Not formally checked.",
        "AMBIGUOUS_TRANSLATION": "Not formally checked: more than one reading.",
        "UNKNOWN": "Check unavailable.", "TIMEOUT": "Check unavailable.", "INTERNAL_ERROR": "Check unavailable.", "NOT_ATTEMPTED": "Check unavailable.",
    }
    return {"labels.json": {"labels": labels, "forbidden_words": ["verified", "true", "proven", "Reviewed"]}}


GENERATORS = {
    "canonical": canonical_vectors, "handshake": handshake_vectors, "decision-table": decision_vectors, "verdict-binding": verdict_vectors,
    "codes": code_vectors, "specialist-port": specialist_vectors, "router-port": router_vectors, "chat-contract": chat_contract_vectors,
}


#: Copies of vectors that travel with kit material for another repository (the agents checks port's own tests).
COPIES = {ROOT / "integration" / "agents" / "checks-port" / "vectors" / "v1-answer.json": OUT / "specialist-port" / "v1" / "answer.json"}


def outputs() -> dict[Path, str]:
    texts: dict[Path, str] = {}
    for folder, gen in GENERATORS.items():
        for name, doc in gen().items():
            texts[OUT / folder / name] = _dump(doc)
    for copy, source in COPIES.items():
        texts[copy] = texts[source]
    return texts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="generate the integration golden vectors")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    texts = outputs()
    drifted = [p for p, t in texts.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    stale = [p for p in OUT.rglob("*.json") if p not in texts]  # copies live outside OUT and are never stale here
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
