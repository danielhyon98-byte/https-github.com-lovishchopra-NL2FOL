"""The tampering suite of the contained harness (``scripts/overseer/tamper.py``, design section 13.4): every case T1 to
T22 on the synthetic task, with the exact code, severity and identifiers the design states; the untampered controls;
the transfer records the suite writes; the mutation gate (``mutate_auditor.py``); the pytest plugin that attaches an
auditor to every channel (``pytest_attach.py``); and, when the recorded rounds are present (``EPINOIC_ARENA_ROUNDS``
names the directory that holds r5), cases on the recorded r5 tasks replayed from a copy that is never written to.

Abuse cases: an output directory inside a recorded round or the sources, an unknown case, a transfer record whose
signed audit was edited or whose events belong to another channel, and the TRN-006 recall gap the suite found on the
recorded translations (a conclusion that is itself a conjunction, assumed verbatim)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer import KIND_CHECKS, OVS_CODES  # noqa: E402
from epinoic_logic.overseer.checks.translation import circular_premises  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
HAS_R5 = ROUNDS is not None and (ROUNDS / "r5" / "specialists").is_dir()
needs_r5 = pytest.mark.skipif(not HAS_R5, reason="the recorded round r5 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")

#: Design section 13.4: the codes each tampering must raise (naming the injection). An empty list is a control.
DESIGN_CODES = {
    "T1": ["OVS-CUST-001"], "T1b": ["OVS-CUST-004"], "T2": ["OVS-RCPT-001"], "T2b": ["OVS-RCPT-002"], "T2c.summary": ["OVS-RCPT-001"],
    "T2c.scope": ["OVS-RCPT-007"], "T2d": ["OVS-RCPT-006"], "T3": ["OVS-RES-004"], "T3b": ["OVS-RES-005"], "T3c": ["OVS-RES-010"],
    "T3c.nodigest": ["OVS-RES-005"], "T4": ["OVS-RES-003", "OVS-RES-009"], "T4b": ["OVS-RES-003"], "T4c": ["OVS-RES-001"], "T5": ["OVS-RCPT-001"],
    "T5b": ["OVS-FORM-001", "OVS-FORM-002"], "T5c": ["OVS-FORM-003"], "T5d": ["OVS-FORM-004"], "T6": [], "T6b": ["OVS-SYN-002"], "T6c": ["OVS-CUST-001"],
    "T7": [], "T7b": ["OVS-PEER-002"], "T7c": ["OVS-PEER-002"], "T8": ["OVS-FID-009"], "T8b": ["OVS-FID-005"], "T8c": [], "T9": ["OVS-FID-002"],
    "T9b": ["OVS-FID-004"], "T10": ["OVS-JOINT-001", "OVS-SYN-003"], "T10b.disclosed": [], "T10b.named": [], "T10c": ["OVS-JOINT-003"],
    "T11": ["OVS-RES-007"], "T11.external": ["OVS-RES-007"], "T12": ["OVS-CUST-005"], "T13": ["OVS-CUST-003"], "T14": [], "T15": ["OVS-CUST-006"],
    "T15b": ["OVS-CUST-006"], "T17": ["OVS-AUDIT-003"], "T18": ["OVS-DIV-001"], "T18.clock": ["OVS-DIV-002"], "T19": ["OVS-JOINT-004", "OVS-RCPT-004"],
    "T16d": ["OVS-FID-001"], "T22a": ["OVS-TRN-001"], "T22b": ["OVS-TRN-002"], "T22c": ["OVS-TRN-002"], "T22d": ["OVS-TRN-003"], "T22e": ["OVS-TRN-004"],
    "T22f": ["OVS-TRN-005"], "T22g": ["OVS-TRN-006"], "T22h": ["OVS-TRN-007"],
}
#: The agent, pack and runner cases: the reasons (or AGENT codes) they must produce.
DESIGN_REASONS = {
    "T16a": ["OVS-AGENT-005"], "T16b": ["OVS-AGENT-001"], "T16c": ["OVS-AGENT-002"], "T16e": ["pack_unknown", "pack_mismatch"],
    "T20a": ["file_digest"], "T20b": ["digest_mismatch"], "T20c": ["file_unlisted"], "T20d": ["unknown_pack"], "T21": ["agent_mismatch", "pack_mismatch"],
}
MEANING = ("T22-premise", "T22-condition", "T22-direction", "T22-comparison")


@pytest.fixture(scope="session")
def synthetic_suite(tmp_path_factory):
    """The whole suite on the synthetic task, once per session: (manifest, output directory)."""
    out = tmp_path_factory.mktemp("tamper-synthetic")
    m = T.run_suite(out, targets=("synthetic",))
    return m, out


def entries(m: dict, *, target: str = "synthetic") -> dict[str, dict]:
    return {e["case"]: e for e in m["faults"] if e["target"] in (target, "pack")}


# ============================================================================================ the cases
def test_every_case_of_the_design_ran_on_the_synthetic_task_and_passed(synthetic_suite):
    m, _out = synthetic_suite
    got = entries(m)
    for name in list(DESIGN_CODES) + list(DESIGN_REASONS) + list(MEANING):
        assert name in got, name
        e = got[name]
        assert not e["skipped"] and not e["error"], (name, e["skipped"], e["error"])
        assert e["passed"], (name, [c for c in e["checks"] if not c["ok"]], e["naming"])
    assert {c.name for c in T.CASES} >= {"T1", "T1b", "T2", "T2b", "T2c", "T2d", "T3", "T3b", "T3c", "T4", "T4b", "T4c", "T5", "T5b", "T5c", "T5d", "T6", "T6b",
                                          "T6c", "T7", "T7b", "T7c", "T8", "T8b", "T8c", "T9", "T9b", "T10", "T10b", "T10c", "T11", "T12", "T13", "T14", "T15",
                                          "T16", "T17", "T18", "T19", "T20", "T21", "T22"}


@pytest.mark.parametrize("name", sorted(DESIGN_CODES))
def test_each_tampering_raises_exactly_the_designed_codes_naming_the_injection(synthetic_suite, name):
    m, out = synthetic_suite
    e = entries(m)[name]
    expected = DESIGN_CODES[name]
    if not expected:
        assert e["expected_none"] and e["class"] in ("control", "lifecycle") and e["passed"]
        return
    assert e["expected_codes"] == expected
    assert all(e["naming"][c] for c in expected), e["naming"]
    assert e["detected"] and e["audit_verifies"] and e["control_ok"] is True
    assert set(expected) <= set(e["observed_codes"])
    rec = H.load_record(out / e["record"])
    for code in expected:  # the exact severity of the code table, and identifiers on every finding
        found = [f for f in rec.audit.report.findings if f.code == code]
        assert found and all(f.severity == OVS_CODES[code][0] for f in found)
    if any(OVS_CODES[c][0] == "error" for c in expected) and e["transfer_state"] is not None:
        assert e["transfer_state"] == "AUDIT_FAILED"  # a tampered transfer is never PASSED
    if e["transfer_state"] is not None:
        assert e["transfer_state"] != "AUDIT_PASSED"


@pytest.mark.parametrize("name", sorted(DESIGN_REASONS))
def test_agent_pack_and_runner_cases_give_the_designed_reasons(synthetic_suite, name):
    m, _out = synthetic_suite
    e = entries(m)[name]
    assert e["expected_reasons"] == DESIGN_REASONS[name] and e["passed"]
    if name.startswith("T20") or name == "T21" or name == "T16e":
        assert e["observed_reasons"] == DESIGN_REASONS[name]


def test_t16d_a_planted_instruction_leaves_the_auditor_unaffected_and_is_a_scored_injection(synthetic_suite):
    m, _out = synthetic_suite
    e = entries(m)["T16d"]
    assert e["injection"] and e["class"] == "claim_not_in_response" and e["passed"]
    assert any("auditor is unaffected" in c["check"] and c["ok"] for c in e["checks"])
    assert any("never in its configuration" in c["check"] and c["ok"] for c in e["checks"])


def test_meaning_faults_of_a_translation_are_decided_by_no_check_and_an_agent_accusation_stays_unresolved(synthetic_suite):
    m, _out = synthetic_suite
    for name in MEANING:
        e = entries(m)[name]
        assert e["class"] == "translation_unfaithful" and e["agent_only"] and e["expected_codes"] == []
        assert "agent outcome: unresolved" in e["observed_reasons"] and e["passed"]
        assert not [c for c in e["observed_codes"] if c.startswith("OVS-TRN") and OVS_CODES[c][0] == "error"]


def test_translator_faults_cover_the_founders_list(synthetic_suite):
    """An added premise (with an invented number: TRN-005; without: a meaning fault), a dropped condition, a flipped
    comparison, an excerpt absent from the supplied text (TRN-004) and a forced encoding reported as unambiguous
    (TRN-002) are all in the suite."""
    m, _out = synthetic_suite
    got = entries(m)
    assert got["T22f"]["expected_codes"] == ["OVS-TRN-005"] and got["T22e"]["expected_codes"] == ["OVS-TRN-004"]
    assert got["T22b"]["expected_codes"] == ["OVS-TRN-002"] and "unambiguous" in got["T22b"]["description"]
    for name in ("T22-premise", "T22-condition", "T22-comparison", "T22-direction"):
        assert got[name]["passed"]


def test_classes_are_kinds_or_named_classes_and_faults_carry_identifiers(synthetic_suite):
    m, _out = synthetic_suite
    for e in m["faults"]:
        assert e["class"] in KIND_CHECKS or e["class"] in T.NON_KIND_CLASSES, e["class"]
        if e["expected_codes"] and e["class"] in KIND_CHECKS and e["case"] not in ("T12", "T17"):
            assert e["injected"], e["fault_id"]
        for code in e["expected_codes"]:
            assert code in OVS_CODES
        if e["class"] in KIND_CHECKS and e["expected_codes"]:
            assert set(e["expected_codes"]) & set(KIND_CHECKS[e["class"]]), e["fault_id"]


def test_the_gates_hold_and_the_summary_names_every_fault(synthetic_suite):
    m, out = synthetic_suite
    assert all(g["ok"] for g in m["gates"].values()), m["gates"]
    assert m["gates"]["auditor_recall_on_tampering_classes"]["value"] == 1.0
    assert m["controls"] == {"synthetic": []}
    text = (out / "summary.md").read_text()
    assert all(e["fault_id"] in text for e in m["faults"])
    assert json.loads((out / "manifest.json").read_text())["format"] == T.SUITE_FORMAT


def test_agents_of_the_suite_are_built_from_the_exported_pack(synthetic_suite):
    m, out = synthetic_suite
    assert Path(m["pack_dir"]).resolve().is_relative_to((out / "pack").resolve())
    assert m["pack"]["name"] == "overseer-knowledge-docs"


# ============================================================================================ transfer records
def test_records_load_verify_and_rebuild_the_same_transfers(synthetic_suite):
    m, out = synthetic_suite
    e = entries(m)["T3"]
    rec = H.load_record(out / e["record"])
    aud, uid = H.rebuild(rec.events, rec.keyring)
    try:
        assert uid == rec.record["channel_uid"]
        assert [t.message_id for t in aud.view(uid).transfers if t.message_id] == rec.audit.message_ids
    finally:
        aud.close()


def test_a_record_whose_signed_audit_was_edited_is_refused(synthetic_suite, tmp_path):
    import shutil
    m, out = synthetic_suite
    e = entries(m)["T1"]
    d = tmp_path / "rec"
    shutil.copytree(out / e["record"], d)
    audit = json.loads((d / "audit.json").read_text())
    audit["state"] = "AUDIT_PASSED"
    (d / "audit.json").write_text(json.dumps(audit))
    with pytest.raises(H.HarnessError, match="does not verify"):
        H.load_record(d)


def test_a_record_whose_events_belong_to_another_channel_is_refused(synthetic_suite, tmp_path):
    import shutil
    m, out = synthetic_suite
    a, b = entries(m)["T1"], entries(m)["T3"]
    d = tmp_path / "rec"
    shutil.copytree(out / a["record"], d)
    shutil.copy(out / b["record"] / "events.jsonl", d / "events.jsonl")
    with pytest.raises(H.HarnessError, match="do not belong"):
        H.load_record(d)


def test_event_records_round_trip_field_for_field(synthetic_suite):
    m, out = synthetic_suite
    rec = H.load_record(out / entries(m)["T1"]["record"])
    for ev in rec.events:
        assert H.event_from_record(H.event_record(ev)) == ev


# ============================================================================================ guards
def test_an_output_directory_inside_a_round_or_the_sources_is_refused(tmp_path):
    rnd = tmp_path / "rounds" / "r5"
    (rnd / "specialists").mkdir(parents=True)
    with pytest.raises(H.HarnessError, match="overlaps"):
        T.run_suite(rnd / "out", rounds_root=tmp_path / "rounds", cases=["T1"], targets=("synthetic",))
    with pytest.raises(H.HarnessError, match="overlaps"):
        T.run_suite(tmp_path / "rounds", rounds_root=tmp_path / "rounds", cases=["T1"], targets=("synthetic",))
    with pytest.raises(H.HarnessError, match="repository's sources"):
        H.check_output_dir(H.REPO_ROOT / "src" / "harness-out")


def test_an_unknown_case_is_refused(tmp_path):
    with pytest.raises(H.HarnessError, match="unknown case"):
        T.run_suite(tmp_path / "x", cases=["T99"], targets=("synthetic",))


def test_patched_restores_every_attribute_including_static_methods():
    from epinoic_logic.channel import TranslatorChannel
    raw = TranslatorChannel.__dict__["_stale_translation"]
    with H.patched((TranslatorChannel, "_stale_translation", staticmethod(lambda *a, **k: None)), (H, "HARNESS_SECRET", b"x")):
        assert TranslatorChannel._stale_translation(None, None, None) is None
    assert TranslatorChannel.__dict__["_stale_translation"] is raw and isinstance(raw, staticmethod)
    assert H.HARNESS_SECRET.startswith(b"overseer-harness")


def test_targets_missing_from_disk_are_recorded_as_not_run(tmp_path):
    m = T.run_suite(tmp_path / "out", rounds_root=tmp_path / "no-rounds", cases=["T1"])
    assert set(m["targets_skipped"]) == {"r5/p4", "r5/hi-t9"}
    assert [e["target"] for e in m["faults"] if e["case"] == "T1"] == ["synthetic"]


def test_the_command_line_writes_the_manifest_and_reports_the_gates(tmp_path, capsys):
    rc = T.main(["--out", str(tmp_path / "cli"), "--targets", "synthetic", "--cases", "T4b,T7c"])
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and all(printed["gates"].values())
    m = json.loads((tmp_path / "cli" / "manifest.json").read_text())
    assert {e["case"] for e in m["faults"]} == {"control", "T4b", "T7c"}


# ============================================================================================ TRN-006: the gap the suite found
def test_trn006_a_conjunction_conclusion_assumed_verbatim_is_circular():
    a, b = {"op": "var", "name": "a"}, {"op": "var", "name": "b"}
    both = {"op": "and", "args": [a, b]}
    p = {"conclusion": {"id": "C", "expr": both}, "premises": [{"id": "P1", "expr": a}, {"id": "P2", "expr": b}]}
    assert circular_premises(p) == []  # the conjuncts stated separately: not verbatim
    p["premises"].append({"id": "P_assumed", "expr": json.loads(json.dumps(both))})
    assert circular_premises(p) == ["P_assumed"]
    p["premises"].append({"id": "P_inside", "expr": {"op": "and", "args": [{"op": "var", "name": "c"}, json.loads(json.dumps(both))]}})
    assert circular_premises(p) == ["P_assumed", "P_inside"]
    q = {"conclusion": {"id": "C", "expr": both}, "premises": [{"id": "P", "expr": {"op": "and", "args": [a, b, {"op": "var", "name": "c"}]}}]}
    assert circular_premises(q) == []  # a wider conjunction is not the conclusion verbatim


# ============================================================================================ the mutation gate
def test_the_mutation_gate_kills_a_disabled_check_and_reports_an_untested_one(tmp_path, monkeypatch):
    import mutate_auditor as M
    r = M.run_mutation(tmp_path / "mut", modules=["peer", "divergence"])
    assert r["gate"]["ok"] and r["modules"]["peer"]["state"] == "TESTED" and r["modules"]["divergence"]["state"] == "TESTED"
    assert {k["case"] for k in r["modules"]["peer"]["killed"]} == {"T7b", "T7c"}
    # a mutant whose disabling no case notices is UNTESTED
    monkeypatch.setitem(M.MUTANTS, "peer", [(M.peer, "check_forward", M._none)])
    r2 = M.run_mutation(tmp_path / "mut2", modules=["peer"])
    assert not r2["gate"]["ok"] and r2["gate"]["untested"] == ["peer"]


def test_every_check_module_has_a_mutant_and_tagged_cases():
    import mutate_auditor as M
    for module in M.MUTANTS:
        assert M.cases_of(module), module


# ============================================================================================ the pytest plugin
def test_the_attach_plugin_adds_an_auditor_to_every_new_channel_and_restores_the_class():
    import pytest_attach as P
    from epinoic_logic.channel import TranslatorChannel
    if P._original_init is not None:
        pytest.skip("the plugin is already active in this session")
    before = TranslatorChannel.__init__
    P.pytest_configure(None)
    try:
        ch = TranslatorChannel(T.make_plan(), signing_key=T.KEY)
        assert len(ch.observers) == 1 and "TransferAuditor" in ch.observers[0].__qualname__
        ch.request("router", "english-specialist", T.EN_INPUT, [T.DOC])
        s = P.summary()
        assert s["channels_attached"] >= 1 and s["transfers_journaled"] >= 1 and s["auditor_observer_failures"] == 0 and s["attach_errors"] == 0
    finally:
        P.pytest_unconfigure(None)
    assert TranslatorChannel.__init__ is before
    assert TranslatorChannel(T.make_plan(), signing_key=T.KEY).observers == ()


# ============================================================================================ the recorded r5 tasks (when present)
def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@needs_r5
def test_cases_on_the_recorded_r5_tasks_detect_and_never_write_the_round(tmp_path):
    before = _tree_digest(ROUNDS / "r5")
    m = T.run_suite(tmp_path / "out", rounds_root=ROUNDS, cases=["T1", "T3", "T22"], targets=("r5/hi-t9",), pack_dir=None)
    after = _tree_digest(ROUNDS / "r5")
    assert before == after  # the recorded round is a read-only input
    got = {e["case"]: e for e in m["faults"] if e["target"] == "r5/hi-t9"}
    assert got["control"]["passed"] and m["controls"]["r5/hi-t9"] == []
    for name in ("T1", "T3", "T22a", "T22b", "T22g", "T22h"):
        assert got[name]["passed"] and got[name]["detected"], (name, got[name]["naming"], got[name]["checks"])
    assert all(g["ok"] for g in m["gates"].values())
