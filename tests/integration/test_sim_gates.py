"""The simulation gates (PROTOCOL.md section 14.5) on fixture records, the NOT RUN rule, and the simulation run on this tree.

Each gate is a pure function of the simulation's records (integration/sim/gates.py): these tests feed it records that
must PASS, records that must FAIL, and no material at all, which must be NOT RUN, never PASS. The last test runs
run_sim.py on this tree: the parts other work streams are still building are missing here, so every gate must be
reported NOT RUN with its reason, the exit status must be 1, and the reference harness must still run on the copy."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "integration" / "sim"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"kit_sim_{name}_t", SIM / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _module("gates")
C = _module("compare")
PROJ = {"status": "ACCEPTED", "finding_codes": [], "claim_statuses": [["h1.1", "ENTAILED"]], "result_digests": [["h1.1", "a", "b", None, "c"]],
        "formal_checks": [], "fixtures_served": ["h1.1"], "fixtures_unserved": []}


def test_every_gate_without_material_is_not_run_never_pass():
    results = [G.g_eq_arena(None, None, C.differences), G.g_eq_contained(None), G.g_fault(None), G.g_inv(None), G.g_hon(None),
               G.g_del(None, None), G.g_tamper(None), G.g_ovs(None)]
    assert [r["gate"] for r in results] == list(G.GATES)
    assert all(r["status"] == G.NOT_RUN and r["reason"] for r in results)
    assert G.exit_status(results) == 1
    with pytest.raises(ValueError):
        G.not_run("G-INV", "")


def test_g_eq_arena_passes_only_with_zero_differences_on_every_item():
    assert G.g_eq_arena({"s1/hi-s1": PROJ}, {"s1/hi-s1": dict(PROJ)}, C.differences)["status"] == G.PASS
    other = dict(PROJ, result_digests=[["h1.1", "a", "b", None, "different"]])
    r = G.g_eq_arena({"s1/hi-s1": PROJ}, {"s1/hi-s1": other}, C.differences)
    assert r["status"] == G.FAIL and r["cases"][0]["field"] == "result_digests"
    r = G.g_eq_arena({"s1/hi-s1": PROJ}, {"s1/hi-s1": PROJ, "s1/hi-s2": PROJ}, C.differences)
    assert r["status"] == G.FAIL and r["cases"][0]["field"] == "presence"
    assert G.g_eq_arena({}, {"s1/hi-s1": PROJ}, C.differences)["status"] == G.NOT_RUN


def test_g_eq_contained_needs_every_applicable_gate_and_equal_states():
    ok = {"exit_status": 0, "gates": {"G1": "PASS", "G2": "NOT RUN"}, "states_equal": True, "non_interference_equal": True}
    assert G.g_eq_contained(ok)["status"] == G.PASS
    assert G.g_eq_contained(dict(ok, states_equal=False))["status"] == G.FAIL
    assert G.g_eq_contained(dict(ok, gates={"G1": "FAIL"}))["status"] == G.FAIL
    assert G.g_eq_contained(dict(ok, gates={"G2": "NOT RUN"}))["status"] == G.NOT_RUN


def test_g_fault_refuses_what_the_arena_catches_and_never_labels_a_miss_checked():
    caught = {"case": "hi-s1:chronology_error", "caught_by_arena": True, "website_refused": True, "arena_codes": ["INT-CONFLICT-005"],
              "website_codes": ["INT-CONFLICT-005", "INT-REQ-007"]}
    miss = {"case": "hi-s1:altered_quotation", "caught_by_arena": False, "website_labelled_checked": False, "same_behaviour": True}
    assert G.g_fault([caught, miss])["status"] == G.PASS
    assert G.g_fault([dict(caught, website_refused=False)])["status"] == G.FAIL
    assert G.g_fault([dict(caught, website_codes=["INT-REQ-007"])])["status"] == G.FAIL
    assert G.g_fault([dict(miss, website_labelled_checked=True)])["status"] == G.FAIL


def test_g_inv_fails_on_a_broken_invariant_and_is_not_run_without_material_for_one():
    assert G.g_inv({"no_answer_stored_without_deliver": True, "replay_makes_no_call": True})["status"] == G.PASS
    assert G.g_inv({"no_answer_stored_without_deliver": False, "replay_makes_no_call": True})["status"] == G.FAIL
    assert G.g_inv({"no_answer_stored_without_deliver": True, "loopback_only": None})["status"] == G.NOT_RUN


@pytest.mark.parametrize("display,ok", [
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True,
      "labels": [{"formal": "ENTAILED", "text": "The logic encoding passed a formal check; the encoding and its premises were not independently established."}]}, True),
    ({"review": "passed", "simulated": True, "scope_statement_shown": True, "labels": []}, False),
    ({"review": "checks:integration.v1", "simulated": False, "scope_statement_shown": True, "labels": []}, False),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [{"formal": "ENTAILED", "text": "Verified."}]}, False),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [{"formal": "UNKNOWN", "text": "Formally checked: ..."}]}, False),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": False, "labels": [{"formal": "ENTAILED", "text": "Formally checked: ..."}]}, False),
    # the answer badge: "passed" only for formally_checked (one positive result of the encoding among unchecked claims is not)
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [],
      "badge": "Automatic checks passed (simulated)", "summary": "formally_checked"}, True),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [],
      "badge": "Partly checked (encoding only) (simulated)", "summary": "formal_only"}, True),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [],
      "badge": "Automatic checks passed (simulated)", "summary": "formal_only"}, False),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [],
      "badge": "Automatic checks passed", "summary": "partly_checked"}, False),
    ({"review": "checks:integration.v1", "simulated": True, "scope_statement_shown": True, "labels": [],
      "badge": "Verified (simulated)", "summary": "formally_checked"}, False),
])
def test_g_hon_labels_are_allowed_for_their_status(display, ok):
    assert G.g_hon([display])["status"] == (G.PASS if ok else G.FAIL)


def test_g_del_needs_a_passed_final_audit_for_every_delivery_and_a_reason_for_every_refusal():
    good = {"verdict_id": "vd_1", "delivery": {"decision": "deliver", "reasons": []}, "overseer": {"state": "AUDIT_PASSED", "delivery_allowed": True}}
    refused = {"verdict_id": "vd_2", "delivery": {"decision": "refuse_unresolved", "reasons": ["KIT-DL-010"]}, "overseer": {"state": "AUDIT_PASSED", "delivery_allowed": True}}
    assert G.g_del([good, refused], [{"item": "x", "decision": "deliver", "kit_derived": True}])["status"] == G.PASS
    assert G.g_del([good], None)["status"] == G.NOT_RUN
    assert G.g_del([dict(good, overseer={"state": "AUDIT_FAILED", "delivery_allowed": False})], [{}])["status"] == G.FAIL
    assert G.g_del([dict(refused, delivery={"decision": "refuse_unresolved", "reasons": []})], [{}])["status"] == G.FAIL


def test_g_tamper_needs_all_eight_cases_refused_as_expected():
    good = {c: {"expected": "kit_dl_030", "got": "kit_dl_030"} for c in G.TAMPER_CASES}
    assert G.g_tamper(good)["status"] == G.PASS
    assert G.g_tamper(dict(good, **{"W-T3": {"expected": "kit_dl_030", "got": None}}))["status"] == G.FAIL
    assert G.g_tamper({k: v for k, v in good.items() if k != "W-T8"})["status"] == G.NOT_RUN


def test_g_ovs_never_lets_the_review_change_a_clearance_or_a_delivery():
    p = {"kind": "fidelity_probe", "website_outcome": "flagged", "contained_outcome": "flagged", "clearance_changed": False, "delivery_changed": False}
    assert G.g_ovs([p])["status"] == G.PASS
    assert G.g_ovs([dict(p, delivery_changed=True)])["status"] == G.FAIL
    assert G.g_ovs([dict(p, website_outcome="clean")])["status"] == G.FAIL


def test_the_exit_status_is_zero_only_when_all_eight_gates_pass():
    passing = [{"gate": g, "status": G.PASS} for g in G.GATES]
    assert G.exit_status(passing) == 0
    assert G.exit_status(passing[:-1] + [{"gate": "G-OVS", "status": G.NOT_RUN}]) == 1
    assert G.exit_status(passing[:-1] + [{"gate": "G-OVS", "status": G.FAIL}]) == 1
    lines = G.summary_lines([{"gate": g, "status": G.PASS, "reason": "r", "denominator": 1} for g in G.GATES])
    assert sum(1 for line in lines if line.startswith("| G-")) == 8


def test_the_simulation_on_this_tree_reports_every_missing_part_as_not_run(tmp_path):
    proc = subprocess.run([sys.executable, str(SIM / "run_sim.py"), "--translator", str(ROOT), "--corpus", str(SIM / "corpus"), "--out", str(tmp_path / "out")],
                          capture_output=True, text=True, timeout=900)
    assert proc.returncode == 1, proc.stdout[-3000:] + proc.stderr[-2000:]
    results = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    statuses = {r["gate"]: r["status"] for r in results["gates"]}
    assert set(statuses) == set(G.GATES) and G.PASS not in statuses.values() and G.FAIL not in statuses.values()
    assert all(r["reason"] for r in results["gates"])
    # each website-path gate names the part that was missing: the service's own refusal (pre-build finding PB3-07)
    refusal = results["not_run"]["service"]
    assert refusal.startswith("the service refused to start: KIT-HS-007")
    for r in results["gates"]:
        if r["gate"] not in ("G-EQ-CONTAINED", "G-OVS"):
            assert refusal in r["reason"], r
    assert results["subchecks"]["arena:s1"]["functional"][0] == results["subchecks"]["arena:s1"]["functional"][1]
    assert results["subchecks"]["arena:s1"]["qualified"] is False
    tamper = results["subchecks"]["tamper_adapter"]
    if tamper is not None:  # Node.js present: the adapter refuses every website tampering case with its code
        assert all(v["got"] == v["expected"] for v in tamper.values())
    summary = (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")
    assert summary.count("| NOT RUN |") == 8 and "Not run, and why:" in summary
    # Repair 1: every run names the copy each path ran (no copy was given here)
    assert all(results[k] is None for k in ("specialist_copy", "specialist_commit", "specialist_contract", "agents_copy", "agents_commit",
                                            "agents_contract"))
    assert "- website path: no copy" in summary and "- agents path: no copy" in summary
    # Repair 2: a path that did not run says so on its "Copies" line, with its own reason (here the service's refusal)
    assert f"- website path: no copy, not run: {results['not_run']['website_path']}" in summary.splitlines()
    assert f"- agents path: no copy, not run: {results['not_run']['agents_path']}" in summary.splitlines()
