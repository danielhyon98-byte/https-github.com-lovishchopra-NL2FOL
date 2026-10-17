"""The website patch material of the kit (integration/website/PATCH-PLAN.md), checked without the website: every block
names an anchor of ANCHORS.md; the applier refuses a target that is not a disposable export and a target whose anchors
differ, writing nothing; no W*.patch file is published (decision D20); RESULT.sha256 lists exactly what a full apply
touches, and the files the applier copies are byte-identical to the ones RESULT.sha256 was computed with (so a kit edit
after the last tested run fails here until the patch set is tested again)."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEBSITE = ROOT / "integration" / "website"
NODE = shutil.which("node")
VECTOR_FOLDERS = ("canonical", "handshake", "decision-table", "verdict-binding", "chat-contract", "codes", "specialist-port")


def _blocks() -> list[dict]:
    out = []
    for p in sorted((WEBSITE / "blocks" / "M").glob("*.block")):
        head, body = p.read_text(encoding="utf-8").split("\n---\n", 1)
        meta = dict(line.split(": ", 1) for line in head.split("\n"))
        out.append({"name": p.stem, "step": meta["kit-block"], "file": meta["file"], "anchor": meta["anchor"], "mode": meta["mode"], "body": body})
    return out


def _anchors() -> dict[tuple[str, str], int]:
    table = {}
    for line in (WEBSITE / "ANCHORS.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `") or line.startswith("| `File"):
            continue
        cells = [c.strip() for c in line.strip("|").split(" | ")]
        table[(cells[0].strip("`"), cells[1].strip("`").replace("\\|", "|"))] = int(cells[2])
    return table


def test_every_block_names_an_anchor_of_the_table_with_a_known_mode():
    table = _anchors()
    blocks = _blocks()
    assert len(blocks) >= 30
    for b in blocks:
        assert (b["file"], b["anchor"]) in table, b["name"]
        assert b["mode"] in ("replace", "replace-line", "before-line", "after-line"), b["name"]
        assert b["step"] in ("W1", "W2", "W3", "W4", "W6"), b["name"]
    assert set(table.values()) <= {1, 3}
    assert not any(b["step"] in ("W0", "W5") for b in blocks), "the patch set never contains W0 (docs) or W5 (migrations)"


def test_no_patch_file_is_published_while_the_translator_repository_is_public():
    assert not list(WEBSITE.rglob("W*.patch"))


def _expected_touched() -> set[str]:
    files = {f"src/verify/{p.name}" for p in (WEBSITE / "src" / "verify").glob("*.js")}
    for d in ("tests", "tests-website"):
        files |= {f"tests/{p.name}" for p in (WEBSITE / d).glob("*.js")}
    for folder in VECTOR_FOLDERS:
        base = ROOT / "integration" / "vectors" / folder
        files |= {f"tests/fixtures/kit/{folder}/{p.relative_to(base).as_posix()}" for p in base.rglob("*.json")}
    files |= {b["file"] for b in _blocks()}
    return files


def _copy_sources() -> dict[str, Path]:
    out = {f"src/verify/{p.name}": p for p in (WEBSITE / "src" / "verify").glob("*.js")}
    for d in ("tests", "tests-website"):
        out.update({f"tests/{p.name}": p for p in (WEBSITE / d).glob("*.js")})
    for folder in VECTOR_FOLDERS:
        base = ROOT / "integration" / "vectors" / folder
        out.update({f"tests/fixtures/kit/{folder}/{p.relative_to(base).as_posix()}": p for p in base.rglob("*.json")})
    return out


def test_result_lists_exactly_what_a_full_apply_touches_and_the_copied_files_are_the_tested_ones():
    lines = (WEBSITE / "patches" / "M" / "RESULT.sha256").read_text(encoding="utf-8").splitlines()
    result = {line[66:]: line[:64] for line in lines}
    assert set(result) == _expected_touched()
    for rel, src in _copy_sources().items():
        assert result[rel] == hashlib.sha256(src.read_bytes()).hexdigest(), f"{rel} changed since the patch set was tested: test it again"
    assert (WEBSITE / "patches" / "M" / "BASE").read_text().strip() == "2cd318208980e5b236d16b4281dfc0560a7b9610"


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_applier_refuses_a_target_that_is_not_a_disposable_export(tmp_path):
    proc = subprocess.run([NODE, str(WEBSITE / "apply.mjs"), "--base", "M", "--target", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1 and "not a disposable export" in proc.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_applier_refuses_missing_anchors_and_writes_nothing(tmp_path):
    (tmp_path / "UNREVIEWED-SIMULATION-COPY.txt").write_text("test\n")
    (tmp_path / "src" / "chat").mkdir(parents=True)
    (tmp_path / "src" / "chat" / "turn.js").write_text("// 1. Route renamed\n")
    proc = subprocess.run([NODE, str(WEBSITE / "apply.mjs"), "--base", "M", "--target", str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
    assert "anchor not found: src/chat/turn.js: // 1. Route." in proc.stderr
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == ["UNREVIEWED-SIMULATION-COPY.txt", "src/chat/turn.js"]
    assert (tmp_path / "src" / "chat" / "turn.js").read_text() == "// 1. Route renamed\n"
