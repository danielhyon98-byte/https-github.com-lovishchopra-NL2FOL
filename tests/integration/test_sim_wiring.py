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


REPLY_PROBE = """
import { pathToFileURL } from "node:url";
const { replyFor, SUPPORTED_CONTRACTS } = await import(pathToFileURL(process.argv[2]).href);
const calls = [];
const copysOwnCallbacks = {
  generationResult: (o) => { calls.push(["generationResult", o]); return { built: "generation", ...o }; },
  failureResult: (o) => { calls.push(["failureResult", o]); return { built: "failure", ...o }; },
};
const v1 = replyFor("epinoic.specialist-runtime.v0.1.0", copysOwnCallbacks);
const out = { v1: [v1.generated("SYNTHETIC text"), v1.notGenerated("sim_no_answer")], calls_after_v1: calls.length };
const v2 = replyFor("epinoic.specialist-runtime.v0.2.0", copysOwnCallbacks);
out.v2 = [v2.generated("SYNTHETIC text"), v2.notGenerated("sim_no_answer")];
out.calls = calls;
out.thrown = [];
for (const [contract, callbacks] of [["epinoic.specialist-runtime.v0.3.0", copysOwnCallbacks], [undefined, copysOwnCallbacks],
                                     ["epinoic.specialist-runtime.v0.2.0", {}]]) {
  try { replyFor(contract, callbacks); out.thrown.push(null); } catch (e) { out.thrown.push(e.message); }
}
out.supported = SUPPORTED_CONTRACTS;
console.log(JSON.stringify(out));
"""


@needs_node
def test_the_runtime_reply_takes_the_copys_own_contract(tmp_path):
    """runtime-reply.mjs: v0.1.0 gets the objects the drivers always returned, byte for byte, and never calls the copy's
    builders; v0.2.0 gets what the copy's own synthetic callbacks module builds (generationResult with the text,
    failureResult with provider_error); any other contract, or a v0.2.0 copy without those builders, throws."""
    probe = tmp_path / "probe.mjs"
    probe.write_text(REPLY_PROBE, encoding="utf-8")
    r = subprocess.run([NODE, str(probe), str(SIM / "runtime-reply.mjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["v1"] == [{"status": "completed", "output": {"text": "SYNTHETIC text", "finishReason": "stop"}, "usage": None, "providerEvidence": None},
                         {"status": "failed", "error": {"code": "sim_no_answer"}, "usage": None, "providerEvidence": None}]
    assert out["calls_after_v1"] == 0
    assert out["v2"] == [{"built": "generation", "text": "SYNTHETIC text"}, {"built": "failure", "code": "provider_error"}]
    assert out["calls"] == [["generationResult", {"text": "SYNTHETIC text"}], ["failureResult", {"code": "provider_error"}]]
    assert len(out["thrown"]) == 3 and all(m and "unsupported runtime contract" in m for m in out["thrown"]), out["thrown"]
    assert out["supported"] == ["epinoic.specialist-runtime.v0.1.0", "epinoic.specialist-runtime.v0.2.0"]
    for driver in ("website-driver.mjs", "agents-driver.mjs"):
        text = (SIM / driver).read_text(encoding="utf-8")
        assert 'from "./runtime-reply.mjs"' in text and '"specialist-runtime/src/constants.js"' in text, driver
        assert '"specialist-runtime/fixtures/synthetic/callbacks.js"' in text and "runtime_contract: RUNTIME_CONTRACT_VERSION" in text, driver
        assert 'finishReason: "stop"' not in text, f"{driver} replies through runtime-reply.mjs only"


def test_the_wiring_record_ran_the_pinned_runtime_and_harness():
    """The last wiring run (integration/sim/TESTED.json) ran the website path on the retrained runtime at its pin and the
    agents path on the harness at its pin (COMPATIBILITY.json agents_pins)."""
    rec = json.loads((SIM / "TESTED.json").read_text(encoding="utf-8"))
    pins = json.loads((ROOT / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))["agents_pins"]
    assert rec["specialist_commit"] == pins["runtime"]["commit"] and rec["specialist_contract"] == pins["runtime"]["contract"]
    assert rec["agents_commit"] == pins["harness"]["commit"]
    assert "integration/sim/runtime-reply.mjs" in rec["files"] and "integration/sim/runtime-reply.mjs" in RS.WIRING_FILES


def test_every_run_names_the_copy_each_path_ran(tmp_path):
    """Repair 1: results.json and summary.md of every run name the copy each path ran (its .kit-archive-commit and its
    RUNTIME_CONTRACT_VERSION), so the readiness row "simulation runtime copy" can tell whether the website path ran the
    runtime pin or the harness (the default without --specialist)."""
    v1, v2 = "epinoic.specialist-runtime.v0.1.0", "epinoic.specialist-runtime.v0.2.0"

    def copy(name: str, commit: str, contract: str) -> str:
        d = tmp_path / name
        (d / "specialist-runtime" / "src").mkdir(parents=True)
        (d / "specialist-runtime" / "src" / "constants.js").write_text(f'export const RUNTIME_CONTRACT_VERSION = "{contract}";\n', encoding="utf-8")
        (d / ".kit-archive-commit").write_text(commit + "\n", encoding="utf-8")
        return str(d)
    runtime, harness = copy("runtime", "a" * 40, v2), copy("harness", "b" * 40, v1)
    both = RS.copies(runtime, harness)
    assert both == {"specialist_copy": "--specialist", "specialist_commit": "a" * 40, "specialist_contract": v2,
                    "agents_copy": "--agents", "agents_commit": "b" * 40, "agents_contract": v1}
    assert RS.copies(None, harness) == dict(both, specialist_copy="--agents", specialist_commit="b" * 40, specialist_contract=v1)
    assert RS.copies(runtime, None) == dict(both, agents_copy=None, agents_commit=None, agents_contract=None)
    assert RS.copies(None, None) == {k: None for k in both}
    lines = RS.copy_lines(both)
    assert lines[1].startswith("Copies (") and lines[2:] == [f"- website path: --specialist {'a' * 40} ({v2})", f"- agents path: --agents {'b' * 40} ({v1})"]
    assert RS.copy_lines(RS.copies(None, None))[2:] == ["- website path: no copy", "- agents path: no copy"]
    bare = tmp_path / "bare"
    bare.mkdir()
    assert RS.copy_lines(RS.copies(str(bare), None))[2] == "- website path: --specialist (no .kit-archive-commit) (no RUNTIME_CONTRACT_VERSION)"
    assert not any("| NOT RUN |" in line for line in lines), "gate statuses stay in the gate table"
    source = (SIM / "run_sim.py").read_text(encoding="utf-8")
    assert "**copies(args.specialist, args.agents)" in source and "lines += copy_lines(results)" in source


def test_the_copies_lines_say_when_a_path_did_not_run(tmp_path):
    """Repair 2: the copy fields are written before the service starts, so they name the copy each path was GIVEN. The
    summary's "Copies" lines say "given", and a path that did not run carries its own not-run reason there (a refused
    service on a pre-build commit, a driver that stopped): a copy given to a path that did not run is never shown as run.
    A path that ran keeps the line it had."""
    v1, v2 = "epinoic.specialist-runtime.v0.1.0", "epinoic.specialist-runtime.v0.2.0"
    given = {"specialist_copy": "--specialist", "specialist_commit": "a" * 40, "specialist_contract": v2,
             "agents_copy": "--agents", "agents_commit": "b" * 40, "agents_contract": v1}
    refused = "the service refused to start: KIT-HS-007 overseer_unavailable: x"
    lines = RS.copy_lines(dict(given, not_run={"service": refused, "website_path": refused, "agents_path": refused}))
    assert lines[1] == "Copies (the archive copy each path was given: its .kit-archive-commit and RUNTIME_CONTRACT_VERSION):"
    assert lines[2] == f"- website path: --specialist {'a' * 40} ({v2}), not run: {refused}"
    assert lines[3] == f"- agents path: --agents {'b' * 40} ({v1}), not run: {refused}"
    stopped = "not runnable: unsupported runtime contract epinoic.specialist-runtime.v0.9.0"
    lines = RS.copy_lines(dict(given, not_run={"website_path": stopped, "contained": "scripts/overseer/run_contained.py is not on this tree"}))
    assert lines[2].endswith(f", not run: {stopped}") and lines[3] == f"- agents path: --agents {'b' * 40} ({v1})", lines
    assert RS.copy_lines(dict(given, not_run={}))[2:] == [f"- website path: --specialist {'a' * 40} ({v2})", f"- agents path: --agents {'b' * 40} ({v1})"]
    assert RS.copy_lines({"not_run": {"agents_path": "no agents copy (--agents)"}})[3] == "- agents path: no copy, not run: no agents copy (--agents)"
    assert "ran:" not in "\n".join(RS.copy_lines(given)) and "each path ran" not in (SIM / "run_sim.py").read_text(encoding="utf-8")
