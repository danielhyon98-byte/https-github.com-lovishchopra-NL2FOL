"""The agents changes A3 and A5 (integration/agents/PATCH-PLAN.md), built in the kit as anchored replacements
(integration/agents/patches/agents-A3-A5.json) and applied by integration/agents/apply-agents.mjs: it writes only into
an archive copy of the commit the anchors were written for, every anchor must occur exactly once or nothing is written,
and the record of the test on that copy (integration/agents/TESTED.json) names the current patch and applier. The
synthetic copies here hold each anchor once between filler lines; the agents repository itself is never touched."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "integration" / "agents"
DOC = json.loads((AGENTS / "patches" / "agents-A3-A5.json").read_text(encoding="utf-8"))
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def _copy(root: Path, *, commit: str = DOC["agents_commit"], duplicate: str | None = None, drop: str | None = None) -> dict[str, str]:
    files: dict[str, list[str]] = {}
    for r in DOC["replacements"]:
        if r["id"] != drop:
            files.setdefault(r["file"], []).append(r["anchor"])
        if r["id"] == duplicate:
            files[r["file"]].append(r["anchor"])
    texts = {}
    for f, anchors in files.items():
        body = "".join(f"# SYNTHETIC filler {i}\n{a}{'' if a.endswith(chr(10)) else chr(10)}" for i, a in enumerate(anchors))
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text(body, encoding="utf-8")
        texts[f] = body
    if commit is not None:
        (root / ".kit-archive-commit").write_text(commit + "\n", encoding="utf-8")
    return texts


def _apply(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, str(AGENTS / "apply-agents.mjs"), "--target", str(root), *extra], capture_output=True, text=True, timeout=60)


def _unchanged(root: Path, texts: dict[str, str]) -> bool:
    return all((root / f).read_text(encoding="utf-8") == t for f, t in texts.items())


@needs_node
def test_the_applier_writes_only_into_an_archive_copy_of_the_anchors_commit(tmp_path):
    texts = _copy(tmp_path / "checkout", commit=None)
    r = _apply(tmp_path / "checkout")
    assert r.returncode == 1 and "not an archive copy" in r.stderr and _unchanged(tmp_path / "checkout", texts)
    texts = _copy(tmp_path / "other", commit="0" * 40)
    r = _apply(tmp_path / "other")
    assert r.returncode == 1 and "the copy is of" in r.stderr and _unchanged(tmp_path / "other", texts)


@needs_node
@pytest.mark.parametrize("case", ["duplicate", "drop"])
def test_an_anchor_found_twice_or_not_at_all_writes_nothing(tmp_path, case):
    rid = "A5-2" if case == "duplicate" else "A3-7"
    texts = _copy(tmp_path, **{case: rid})
    r = _apply(tmp_path)
    expected = "anchor not unique" if case == "duplicate" else "anchor not found"
    assert r.returncode == 1 and expected in r.stderr, r.stderr
    assert _unchanged(tmp_path, texts)


@needs_node
def test_check_writes_nothing_and_apply_replaces_every_anchor_once(tmp_path):
    texts = _copy(tmp_path)
    r = _apply(tmp_path, "--check")
    assert r.returncode == 0 and f"{len(DOC['replacements'])} anchor(s) found exactly once" in r.stdout and _unchanged(tmp_path, texts)
    r = _apply(tmp_path, "--patch", str(tmp_path / "agents.diff"))
    assert r.returncode == 0, r.stderr
    for rep in DOC["replacements"]:
        text = (tmp_path / rep["file"]).read_text(encoding="utf-8")
        assert rep["replace"] in text, rep["id"]
        if rep["anchor"] not in rep["replace"]:
            assert rep["anchor"] not in text, rep["id"]
    diff = (tmp_path / "agents.diff").read_text(encoding="utf-8")
    assert all(f"--- a/{f}" in diff and f"+++ b/{f}" in diff for f in texts)
    again = _apply(tmp_path, "--check")
    assert again.returncode == 1 and "anchor not found" in again.stderr, "an applied copy is not patched twice"


def test_the_replacements_carry_the_decided_behaviour():
    by = {r["id"]: r for r in DOC["replacements"]}
    # A3: the simulation mode only; the delivered reply's claims; its id and digest forwarded
    assert '"simulation_only"' in by["A3-4"]["replace"] and "return 2" in by["A3-4"]["replace"]
    assert "transmitted_reports" in by["A3-7"]["anchor"] and "transmitted_reports" not in by["A3-7"]["replace"]
    assert all(k in by["A3-8"]["replace"] for k in ("message_id", "payload_sha256", "signature_key_id", "signed"))
    # A5 (decision D18): advisory by default; every Z3 error finding blocks unless the run asks for the old behaviour
    assert "A.adjudicator || 'advisory'" in by["A5-1"]["replace"]
    assert "ADJUDICATOR === 'authoritative' ? Math.max(0, z3Blocks.length - artefacts) : z3Blocks.length" in by["A5-2"]["replace"]
    assert 'opt.adjudicator ?? "advisory"' in by["A5-5"]["replace"]
    assert 'ADJUDICATOR === "authoritative" ? z3.length - artefacts : z3.length' in by["A5-6"]["replace"]
    for r in DOC["replacements"]:
        for text in (r["anchor"], r["replace"]):
            assert not re.search(r"claude-(opus|haiku|sonnet)|\b(Opus|Haiku|Sonnet|Fable) [0-9]", text), r["id"]
            assert not re.search(r"[0-9a-f]{32,}", text), r["id"]


def test_the_record_of_the_test_on_the_archive_copy_names_the_current_patch_and_applier():
    rec = json.loads((AGENTS / "TESTED.json").read_text(encoding="utf-8"))
    assert rec["agents_commit"] == DOC["agents_commit"]
    for path, digest in rec["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, (
            f"{path} changed after the test on the archive copy: re-run it (PATCH-PLAN.md, 'Applying A3 and A5') and update TESTED.json")
    assert set(rec["files"]) == {"integration/agents/patches/agents-A3-A5.json", "integration/agents/apply-agents.mjs"}
