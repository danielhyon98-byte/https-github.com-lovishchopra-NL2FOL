"""The simulation's wiring (integration/sim/README.md): the drivers' prerequisites, how run_sim.py turns the drivers'
records and the evidence tap into each gate's material, the NOT RUN reasons a missing part gives (pre-build finding
PB3-07: a gate names the part that was missing, never a guess), the test-double rule (a double of the overseer port
audits nothing, so every gate is NOT RUN under it), the service log (a file, never an unread pipe), the fault round
(only the service loads it), and the record of the last wiring run (integration/sim/TESTED.json), which names the files
it ran so a change to any of them needs a new run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.integration.helpers import env as sim_env

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "integration" / "sim"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"kit_sim_{name}_w", SIM / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G, C, RS, F = _module("gates"), _module("compare"), _module("run_sim"), _module("faults")
PROJ = {"status": "ACCEPTED", "finding_codes": [], "claim_statuses": [["h1.1", "ENTAILED"]], "result_digests": [], "formal_checks": [],
        "fixtures_served": ["h1.1"], "fixtures_unserved": []}


@needs_node
@pytest.mark.parametrize("driver", ["website-driver.mjs", "agents-driver.mjs"])
def test_a_driver_without_its_prerequisites_exits_3_and_names_them(driver, tmp_path):
    r = subprocess.run([NODE, str(SIM / driver), "--out", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and r.stderr.startswith("not runnable: missing"), r.stderr
    assert not any(tmp_path.iterdir()), "nothing is written by a driver that cannot run"


def test_g_eq_arena_compares_every_call_and_names_the_items_whose_path_was_not_run():
    other = dict(PROJ, status="REJECTED")
    assert G.g_eq_arena({"s1/hi-s1": [PROJ, dict(PROJ)]}, {"s1/hi-s1": PROJ}, C.differences)["status"] == G.PASS
    r = G.g_eq_arena({"s1/hi-s1": [PROJ, other]}, {"s1/hi-s1": PROJ}, C.differences)
    assert r["status"] == G.FAIL and r["cases"][0]["call"] == 1 and r["cases"][0]["field"] == "status"
    unrun = {"s1/ph-s1": "the agents path was not run: no agents copy (--agents)"}
    r = G.g_eq_arena({"s1/hi-s1": [PROJ]}, {"s1/hi-s1": PROJ, "s1/ph-s1": PROJ}, C.differences, unrun)
    assert r["status"] == G.NOT_RUN and "s1/ph-s1 (the agents path was not run: no agents copy (--agents))" in r["reason"]
    r = G.g_eq_arena({"s1/hi-s1": [PROJ]}, {"s1/hi-s1": PROJ, "s1/hi-s2": PROJ}, C.differences, unrun)
    assert r["status"] == G.FAIL and r["cases"][0]["field"] == "presence", "a path that ran must have evidence for every item"


def test_g_del_compares_the_kit_derived_decision_unless_the_overseer_refused_the_delivery():
    good = {"verdict_id": "vd_1", "delivery": {"decision": "deliver", "reasons": []}, "overseer": {"state": "AUDIT_PASSED", "delivery_allowed": True}}
    same = {"item": "s1/hi-s1", "decision": "deliver", "website_decision": "deliver", "overseer_allowed": True, "kit_derived": True}
    assert G.g_del([good], [same])["status"] == G.PASS
    r = G.g_del([good], [dict(same, decision="refuse_unresolved")])
    assert r["status"] == G.FAIL and r["cases"] == ["s1/hi-s1"]
    assert G.g_del([good], [dict(same, decision="deliver", website_decision="refuse_integrity", overseer_allowed=False)])["status"] == G.PASS


def test_under_a_test_double_every_gate_is_not_run_and_what_it_computed_is_a_sub_check():
    computed = [G._gate(g, G.PASS if i % 2 else G.FAIL, "r", 3, ["case"]) for i, g in enumerate(G.GATES)]
    sub: dict = {}
    out = RS.with_test_double(computed, "kit_overseer_test_double", sub, G)
    assert [g["status"] for g in out] == [G.NOT_RUN] * 8 and G.exit_status(out) == 1
    assert all("the overseer port is a test double (kit_overseer_test_double)" in g["reason"] for g in out)
    assert [s["status"] for s in sub["gates_with_test_double"]] == [g["status"] for g in computed]
    assert set(sub["gate_cases_with_test_double"]) == {g["gate"] for g in computed if g["status"] == G.FAIL}


def _evidence(dirpath: Path, request_id: str, codes: list[str], status: str = "ACCEPTED_WITH_FINDINGS") -> None:
    receipt = {"direction": "specialist_to_router", "status": status, "findings": [{"code": c} for c in codes], "structural_findings": [],
               "outcomes": [{"claim_id": "h1.1", "display_status": "ENTAILED", "translation": {"status": "TRANSLATED"}}], "formal_checks": []}
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / f"{request_id}.json").write_text(json.dumps({"request_id": request_id, "receipts": [{"direction": "router_to_specialist"}, receipt]}))


def test_the_gates_material_is_read_from_the_drivers_records_and_the_evidence_tap(tmp_path):
    corpus = tmp_path / "s1"
    (corpus / "translations").mkdir(parents=True)
    (corpus / "translations" / "hi-s1.json").write_text(json.dumps({"claims": {"h1.1": {}}}))
    ev = tmp_path / "evidence"
    _evidence(ev, "a_genuine_1", ["HI-SRC-004"])
    _evidence(ev, "a_fault_1", ["CORE-SRC-003"])
    verdict = {"ids": {"request_id": "a_genuine_1"}, "delivery": {"decision": "deliver"}, "overseer": {"delivery_allowed": True}}
    website = {"turns": [
        {"user": "u1", "action": "send", "item": "hi-s1", "stored": {"attempt_id": "a_genuine_1"}},
        {"user": "u2", "action": "tamper:W-T1-tampered-decision", "item": "hi-s1", "stored": {"attempt_id": "a_genuine_1"}},
        {"user": "sim-faults", "action": "fault:invented_quotation", "item": "hi-s1", "fault_case": "hi-s1:invented_quotation", "stored": {"attempt_id": "a_fault_1"}},
    ], "faults": [{"case": "hi-s1:invented_quotation", "website_refused": False, "website_labelled_checked": False}],
        "verdicts": [verdict], "displays": [{"review": "checks:integration.v1"}], "invariants": {"loopback_only": True}, "tamper": {"W-T1": {}}}
    reference = {"mutations": [{"item": "hi-s1", "kind": "invented_quotation", "named_by": ["CORE-SRC-003"], "codes": ["CORE-SRC-003"],
                                "status": "ACCEPTED_WITH_FINDINGS"}],
                 "decisions": {"s1/hi-s1": {"decision": "deliver", "reasons": [], "kit_derived": True}}}
    m = RS.collect(website, None, ev, [corpus], reference, C)
    assert list(m["projections"]) == ["s1/hi-s1"] and len(m["projections"]["s1/hi-s1"]) == 1, "only genuine single-mode calls are compared"
    assert m["projections"]["s1/hi-s1"][0]["finding_codes"] == ["HI-SRC-004"] and m["projections"]["s1/hi-s1"][0]["fixtures_served"] == ["h1.1"]
    [fault] = m["faults"]
    assert fault == {"case": "hi-s1:invented_quotation", "caught_by_arena": True, "arena_codes": ["CORE-SRC-003"], "website_refused": False,
                     "website_codes": ["CORE-SRC-003"], "website_labelled_checked": False, "same_behaviour": True}
    assert G.g_fault(m["faults"])["status"] == G.FAIL, "a mutation the arena names must not be delivered"
    assert m["rederived"] == [{"item": "s1/hi-s1", "path": "website", "decision": "deliver", "website_decision": "deliver", "overseer_allowed": True,
                               "kit_derived": True}]
    assert m["invariants"] == {"loopback_only": True} and m["tamper"] == {"W-T1": {}} and m["displays"]


def test_the_fault_round_is_for_the_service_only_and_leaves_out_a_text_two_fixture_sets_would_claim(tmp_path):
    src = tmp_path / "ref" / "s1"
    for item, doc in (("hi-s1", {"claims": {"a": 1}}), ("hi-s2", {"claims": {"b": 2}})):
        (src / "specialists").mkdir(parents=True, exist_ok=True)
        (src / "translations").mkdir(parents=True, exist_ok=True)
        (src / "specialists" / f"{item}.json").write_text(json.dumps({"task_id": item, "response_text": f"genuine {item}"}))
        (src / "translations" / f"{item}.json").write_text(json.dumps(doc))
    cases = [{"case": "hi-s1:k1", "item": "hi-s1", "kind": "k1", "text": "mutated one", "round": "s1"},
             {"case": "hi-s2:k1", "item": "hi-s2", "kind": "k1", "text": "genuine hi-s1", "round": "s1"}]
    out = F.write_fault_round(cases, {"s1": src}, tmp_path / "service")
    assert out["written"] == ["hi-s1:k1"] and [s["case"] for s in out["skipped"]] == ["hi-s2:k1"]
    case_round = tmp_path / "service" / "sim-fault-hi-s1~k1"
    written = json.loads((case_round / "specialists" / "hi-s1.json").read_text())
    assert written["response_text"] == "mutated one", "the item keeps its own name, so its arena request id req-hi-s1"
    assert (case_round / "translations" / "hi-s1.json").read_text() == (src / "translations" / "hi-s1.json").read_text()
    assert [p.name for p in (tmp_path / "service").iterdir()] == ["sim-fault-hi-s1~k1"]
    assert not any(p.name.startswith("sim-fault") for p in (tmp_path / "ref").iterdir()), "the reference copy never holds a fault round"


def test_the_service_log_is_a_file_so_a_refusal_line_is_read_back(tmp_path):
    env = dict(RS.service_env(ROOT, tmp_path / "corpus", tmp_path / "evidence"), EPINOIC_PROFILE="integration-smi")
    proc, line = RS.start_service(env, RS._free_port(), tmp_path / "service.log")
    assert proc is None and "KIT-HS-012" in line and (tmp_path / "service.log").exists()


def test_the_simulation_service_raises_only_its_own_rate_and_attaches_a_double_only_on_request(tmp_path):
    env = RS.service_env(ROOT, tmp_path, tmp_path / "ev")
    assert env["EPINOIC_RATE_PER_MINUTE"] == RS.SIM_RATE_PER_MINUTE and "EPINOIC_OVERSEER_PORT" not in env
    assert env["EPINOIC_PROFILE"] == "integration-sim" and env["EPINOIC_TRANSLATION_PROVIDER"] == "fixture"
    double = RS.service_env(ROOT, tmp_path, tmp_path / "ev", test_port="kit_overseer_test_double", test_path=str(tmp_path))
    assert double["EPINOIC_OVERSEER_PORT"] == "kit_overseer_test_double" and str(tmp_path) in double["PYTHONPATH"]
    assert set(sim_env()) - set(env) == set(), "the simulation sets every variable the integration tests set"


def test_the_record_of_the_last_wiring_run_names_the_files_it_ran():
    rec = json.loads((SIM / "TESTED.json").read_text(encoding="utf-8"))
    assert rec["schema"] == "epinoic.integration.sim-wiring-record.v1" and "TEST DOUBLE" in rec["note"]
    assert set(rec["files"]) == set(RS.WIRING_FILES)
    for path, digest in rec["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, (
            f"{path} changed after the last wiring run: run integration/sim/run_sim.py with the test double and --record-wiring "
            "(integration/sim/README.md)")
    assert [g["gate"] for g in rec["computed"]] == list(G.GATES)
    assert rec["agents_commit"] and rec["website_export"].startswith("UNREVIEWED SIMULATION COPY")
