"""The kit's manifests are fresh (PROTOCOL.md section 14.1: "a test fails when integration/MANIFEST.sha256 does not match the
files"), and the playbook's own check (`sha256sum -c --quiet integration/MANIFEST.sha256`) passes from the root."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_manifests_match_the_files():
    proc = subprocess.run([sys.executable, str(ROOT / "integration" / "tools" / "manifest.py"), "--check"], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr + "\nrun: python integration/tools/manifest.py"


def test_sha256sum_checks_the_manifest_from_the_repository_root():
    tool = shutil.which("sha256sum")
    if tool is None:
        import pytest
        pytest.skip("sha256sum is not installed here: the Python check above covers the same digests")
    for manifest in ("integration/MANIFEST.sha256", "integration/sim/corpus/MANIFEST.sha256"):
        proc = subprocess.run([tool, "-c", "--quiet", manifest], cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_kit_file_is_listed():
    listed = {line.split("  ", 1)[1].strip() for line in (ROOT / "integration" / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()}
    for tree in ("integration", "src/epinoic_logic/integration"):
        for p in (ROOT / tree).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            if p == ROOT / "integration" / "MANIFEST.sha256":
                continue  # the manifest does not list itself
            assert p.relative_to(ROOT).as_posix() in listed, p
