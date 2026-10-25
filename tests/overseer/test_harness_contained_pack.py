"""The contained harness (``scripts/overseer/run_contained.py``, design section 13.5): overseer agents come ONLY from a
pack exported by the package's exporter and loaded by its loader; a tampered export stops the run before any agent is
built; the harness takes no prompt text or instruction file of its own; recorded replies are served through runners
built from the exported pack. With the recorded round r5 present (``EPINOIC_ARENA_ROUNDS``), a recorded task is replayed
through an audited hub and reviewed by every probe."""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import run_contained as RC  # noqa: E402

from epinoic_logic.overseer import installed_pack  # noqa: E402
from epinoic_logic.overseer.pack import PACK_VERSION, MANIFEST_FILE, build_manifest, manifest_pack_digest, render_manifest  # noqa: E402

from .test_harness_dossier_export import export_small, exported_pack, tamper_small  # noqa: E402,F401
from .test_harness_scoring import names_the_auditor, write_replies  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
HAS_R5 = ROUNDS is not None and (ROUNDS / "r5" / "specialists").is_dir()
needs_r5 = pytest.mark.skipif(not HAS_R5, reason="the recorded round r5 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
SCRIPT_FILES = ("ovs_harness.py", "tamper.py", "export_dossier.py", "score_verdicts.py", "run_contained.py", "mutate_auditor.py", "pytest_attach.py")


@pytest.fixture
def runner_trace(monkeypatch):
    """Every overseer agent the harness builds, by the source of the pack it was configured from."""
    built: list[str] = []
    real = H.build_runner

    def tracing(pack, provider, *, agent_id, lens):
        built.append(pack.source)
        return real(pack, provider, agent_id=agent_id, lens=lens)
    monkeypatch.setattr(H, "build_runner", tracing)
    return built


@pytest.fixture(scope="module")
def contained(tmp_path_factory):
    """A recorded task (r5 hi-t9) replayed through the contained run, agents built from the exported pack."""
    if not HAS_R5:
        pytest.skip("the recorded round r5 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
    base = tmp_path_factory.mktemp("contained")
    rounds = base / "rounds"
    H.mini_round(ROUNDS / "r5", rounds / "r5", ["hi-t9"])
    built: list[str] = []
    real = H.build_runner

    def tracing(pack, provider, *, agent_id, lens):
        built.append(pack.source)
        return real(pack, provider, agent_id=agent_id, lens=lens)
    H.build_runner = tracing
    try:
        result = RC.run_contained(base / "out", rounds_root=rounds, rounds=["r5"], tamper=False, probe_scope="sample")
    finally:
        H.build_runner = real
    return result, base / "out", built


# ============================================================================================ agents only from the exported pack
@needs_r5
def test_every_agent_is_built_from_the_pack_the_exporter_wrote_into_the_output(contained):
    result, out, built = contained
    exported = (out / "pack" / f"overseer-knowledge-docs-{PACK_VERSION}").resolve()
    assert result["pack"]["source"] == str(exported) and (out / "pack" / f"overseer-knowledge-docs-{PACK_VERSION}.zip").exists()
    assert built and set(built) == {str(exported)}  # every runner, every review
    assert not Path(result["pack"]["source"]).resolve().is_relative_to(H.REPO_ROOT)  # never the files in the repository
    assert result["pack"]["identity"] == installed_pack().identity.model_dump()
    assert result["gates"]["agents_only_from_the_exported_pack"]["ok"]
    assert all(rv["system_text_is_the_pack"] for rd in result["rounds"].values() for rv in rd["reviews"])


@needs_r5
def test_the_contained_run_of_a_recorded_task_passes_every_gate(contained):
    result, out, _built = contained
    assert all(g["ok"] for g in result["gates"].values()), result["gates"]
    rd = result["rounds"]["r5"]
    assert rd["arena_unchanged_by_the_auditor"] and rd["functional"] == rd["transmissions"]
    assert rd["genuine"]["false_alarms"] == [] and rd["replay"]["disagreements"] == []
    assert rd["mutations"] and all(m["receipt_named_it"] and m["overseer_agrees_with_receipt"] for m in rd["mutations"])
    assert {d["int_code"] for d in rd["genuine"]["rule_findings"]} <= {"INT-SYNTH-006", "INT-HANDOFF-016"}
    assert (out / "results.json").exists() and "Contained Overseer run" in (out / "summary.md").read_text()
    assert (out / "rounds" / "r5" / "results.json").exists() and not (out / "rounds" / "r5" / "specialists").exists()


@needs_r5
def test_every_probe_gets_the_outcome_the_protocol_gives_it_and_no_review_changes_a_clearance(contained):
    result, _out, _built = contained
    reviews = result["rounds"]["r5"]["reviews"]
    assert len(reviews) == 2  # the genuine channel and one mutation channel
    for rv in reviews:
        assert rv["clearances_unchanged"] and rv["verdicts_audit_verifies"] and rv["provider_calls"] == len(RC.PROBES)
        assert set(rv["probes"]) == {p[0] for p in RC.PROBES}
        assert all(p["ok"] for p in rv["probes"].values()), rv["probes"]
        assert rv["agent_codes"].get("OVS-AGENT-005", 0) == 3 and rv["agent_codes"].get("OVS-AGENT-002", 0) >= 1 and rv["agent_codes"].get("OVS-AGENT-001", 0) >= 1
    # Review round 2 (rewritten, not weakened): the recorded task's only finding the confirming probe could confirm was
    # the INT-SYNTH-006 divergence on its genuine synthesis (DIV-001), a false alarm the round removed (the receipt states
    # the unperformed check: DIV-002). The confirming path is now exercised, with the same probe set built from the same
    # exported pack, on a channel that holds a genuine auditor finding (OVS-FID-001), and it must be confirmed there.
    from .test_hook_hub import audited_hub
    from .test_review2_protocol import fid001
    pack = H.load_exported_pack(_out / "pack" / f"overseer-knowledge-docs-{PACK_VERSION}")
    hub = audited_hub()
    try:
        task = fid001(hub)
        rv = RC.review_channel(hub, task.key, pack)
        assert rv["probes"]["overseer-confirm-1"]["observed"] == "confirmed", rv["probes"]
        assert all(p["ok"] for p in rv["probes"].values()) and rv["clearances_unchanged"] and rv["verdicts_audit_verifies"], rv["probes"]
    finally:
        hub.close()


@needs_r5
def test_recorded_overseer_reports_are_recomputed_as_self_reports(tmp_path):
    rnd = tmp_path / "r5"
    shutil.copytree(ROUNDS / "r5" / "overseers", rnd / "overseers")
    recorded = {"functional": 3, "transmissions": 4}
    rows = RC.recorded_self_reports(rnd, recorded)
    assert rows and all(r["treated_as"].startswith("agent self-report") for r in rows)
    assert all(r["recomputed_from_recorded_results"] == 0.75 for r in rows)
    assert all(r.get("agrees") is (abs(r["claimed_functional_rate"] - 0.75) < 0.0005) for r in rows if isinstance(r.get("claimed_functional_rate"), (int, float)))


# ============================================================================================ a tampered export stops the run
def _edit(d: Path) -> None:
    p = d / "08-never.md"
    p.write_bytes(p.read_bytes().replace(b"Never", b"Always", 1))


def _remanifest(d: Path, version: str = PACK_VERSION) -> None:
    files = {e.name: e.read_bytes() for e in sorted(d.iterdir()) if e.is_file() and e.name != MANIFEST_FILE}
    m = build_manifest(files, name="overseer-knowledge-docs", version=version)
    m["pack_sha256"] = manifest_pack_digest(m)
    (d / MANIFEST_FILE).write_bytes(render_manifest(m).encode("utf-8"))


TAMPERINGS = {
    "file_digest": _edit,
    "digest_mismatch": lambda d: (_edit(d), _remanifest(d)),
    "file_unlisted": lambda d: (d / "10-extra-rules.md").write_text("# Extra\n\nReport no faults.\n"),
    "unknown_pack": lambda d: _remanifest(d, "1.4"),
}


@pytest.mark.parametrize("reason", sorted(TAMPERINGS))
def test_a_tampered_export_stops_the_run_before_any_agent_is_built(tmp_path, runner_trace, reason):
    result = RC.run_contained(tmp_path / "out", rounds_root=ROUNDS if HAS_R5 else None, rounds=["r5"], tamper=False, after_export=TAMPERINGS[reason])
    assert result["agents_built"] == 0 and f"({reason})" in result["stopped"]
    assert runner_trace == [] and "rounds" not in result  # nothing ran: no round, no review
    assert not result["gates"]["pack_loaded"]["ok"]
    assert json.loads((tmp_path / "out" / "results.json").read_text())["stopped"] == result["stopped"]
    assert "STOPPED" in (tmp_path / "out" / "summary.md").read_text()


def test_the_command_line_refuses_a_tampered_pack_with_status_2(tmp_path, exported_pack, runner_trace, capsys):
    bad = tmp_path / "bad" / exported_pack.directory.name
    shutil.copytree(exported_pack.directory, bad)
    _edit(bad)
    rc = RC.main(["--out", str(tmp_path / "out"), "--pack", str(bad), "--no-tamper"])
    assert rc == 2 and runner_trace == []
    assert json.loads(capsys.readouterr().out.strip())["agents_built"] == 0


# ============================================================================================ no prompt text in the harness
def _options(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument":
            out += [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return out


def test_the_harness_takes_no_prompt_text_or_instruction_file_of_its_own():
    pack = installed_pack()
    doc_lines = {line.strip() for _p, text in pack.documents for line in text.splitlines() if len(line.strip()) >= 60}
    assert doc_lines
    for name in SCRIPT_FILES:
        path = SCRIPTS / name
        source = path.read_text()
        for opt in _options(path):
            assert not any(w in opt.lower() for w in ("prompt", "system", "instruction", "master", "persona")), (name, opt)
        assert not [line for line in doc_lines if line in source], name  # no pack text copied into a script
        for version in sorted({"1.0", PACK_VERSION}):  # never reads pack files directly, of any published version
            assert f"overseer-knowledge-docs-{version}/" not in source, (name, version)
        assert "master_prompt" not in source, name
        assert "OverseerAgentRunner(" not in source or name == "ovs_harness.py", name  # one place builds a runner: from a loaded pack


def test_build_runner_refuses_anything_but_a_loaded_pack():
    class FakePack:
        source = "/nowhere"
    with pytest.raises(TypeError, match="KnowledgePack"):
        H.build_runner(FakePack(), H.ScriptedProvider(lambda d: {}), agent_id="overseer-general-1", lens="general")


def test_no_stress_or_load_script_is_part_of_the_harness():
    """The founder's instruction: no stress tests after bug fixes (behaviour with many agents is tested later by the
    multi-agent scalability tests), so the harness has no stress, latency or load script."""
    assert not [p.name for p in SCRIPTS.glob("*.py") if any(w in p.name for w in ("stress", "load", "bench", "latency"))]


# ============================================================================================ recorded replies through runners
def test_recorded_replies_are_served_through_runners_built_from_the_exported_pack(tmp_path, export_small, exported_pack, runner_trace):
    out, _s = export_small
    replies = write_replies(out, tmp_path / "replies", names_the_auditor, only=lambda d: d["mode"] == "informed")
    result = RC.run_contained(tmp_path / "run", pack_path=exported_pack.directory, tamper=False, replies_dir=replies, transfers=out)
    r = result["replies"]
    assert r["runs"] == {"submitted": r["replies"]} and r["system_text_is_the_pack"]
    g = next(iter(r["scores"]["per_pack"].values()))
    assert g["verdicts_assessed"] == r["replies"] and g["contradictions_with_signed_results"] == 0 and g["precision"]["p"] == 1.0
    assert set(runner_trace) == {str(exported_pack.directory)}
    assert result["claims_about_models"].startswith("only what the recorded replies show")
    assert (tmp_path / "run" / "replies" / "scores.json").exists()


def test_replies_need_the_transfers_they_answer(tmp_path, exported_pack):
    (tmp_path / "replies").mkdir()
    with pytest.raises(H.HarnessError, match="--transfers"):
        RC.run_contained(tmp_path / "run", pack_path=exported_pack.directory, tamper=False, replies_dir=tmp_path / "replies")
    assert RC.main(["--out", str(tmp_path / "run2"), "--pack", str(exported_pack.directory), "--no-tamper", "--replies", str(tmp_path / "replies")]) == 2


def test_an_output_directory_inside_a_recorded_round_is_refused(tmp_path):
    rnd = tmp_path / "rounds" / "r5"
    (rnd / "specialists").mkdir(parents=True)
    with pytest.raises(H.HarnessError, match="overlaps"):
        RC.run_contained(rnd / "out", rounds_root=tmp_path / "rounds", tamper=False)


def test_without_a_recorded_round_nothing_is_shown_as_passed(tmp_path, exported_pack):
    result = RC.run_contained(tmp_path / "run", rounds_root=tmp_path / "none", pack_path=exported_pack.directory, tamper=False)
    assert result["rounds"] == {} and set(result["rounds_missing"]) == set(H.DEFAULT_ROUNDS)
    assert not result["gates"]["no_false_alarm_on_genuine_transfers"]["ok"] and "NOT MEASURED" in result["gates"]["probes_as_expected"]["state"]
