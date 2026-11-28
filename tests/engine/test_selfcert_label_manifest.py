"""The meaning label in the policy identity (POLICY_VERSION 2026.11-v9; meaning-check design 2.5.9, the KIT step of stage 2a).

``engine.identity.policy_manifest()`` carries ``selfcert_meaning_label``: the label's version, its ``label_digest()`` and
``required: true``. The entry is identity data only: the label never reaches the IR, the compiler or the solver, and the model
(configuration) is not part of it. A change of the label's version or digest is another policy, so every result signed under the
other one is stale; the version and the digest are pinned together in tests/selfcert_label/test_identity.py (T17)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import epinoic_logic.selfcert_label as L
from epinoic_logic.engine import identity as identity_mod
from epinoic_logic.version import POLICY_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_the_policy_manifest_binds_the_meaning_label():
    manifest = identity_mod.policy_manifest()
    assert POLICY_VERSION == "2026.11-v9" and manifest["policy_version"] == "2026.11-v9"
    assert manifest["selfcert_meaning_label"] == {"version": "selfcert-label-2", "digest": L.label_digest(), "required": True}
    assert manifest["selfcert_meaning_label"]["version"] == L.LABEL_VERSION
    # exactly these three members: no model, no labeller kind, no key (configuration is never part of the policy)
    assert set(manifest["selfcert_meaning_label"]) == {"version", "digest", "required"}


def test_another_label_digest_is_another_policy(monkeypatch: pytest.MonkeyPatch):
    current = identity_mod.policy_id.__wrapped__()
    monkeypatch.setattr(L, "label_digest", lambda *a, **k: "0" * 64)
    assert identity_mod.policy_manifest()["selfcert_meaning_label"]["digest"] == "0" * 64
    assert identity_mod.policy_id.__wrapped__() != current


def test_another_label_version_is_another_policy(monkeypatch: pytest.MonkeyPatch):
    current = identity_mod.policy_id.__wrapped__()
    monkeypatch.setattr(L, "LABEL_VERSION", "selfcert-label-0")
    assert identity_mod.policy_manifest()["selfcert_meaning_label"]["version"] == "selfcert-label-0"
    assert identity_mod.policy_id.__wrapped__() != current


def test_the_label_is_required_in_the_policy(monkeypatch: pytest.MonkeyPatch):
    """``required`` is a constant of the policy, never read from configuration: no environment variable or labeller turns it
    off, and the policy identity is the same whatever labeller is installed."""
    current = identity_mod.policy_id.__wrapped__()
    for name in ("EPINOIC_SELFCERT_LABEL", "EPINOIC_ARENA_LABELLER"):
        monkeypatch.setenv(name, "unconfigured")
    previous = L.set_default_labeller(None)  # the production default (UnconfiguredLabeller)
    try:
        assert identity_mod.policy_manifest()["selfcert_meaning_label"]["required"] is True
        assert identity_mod.policy_id.__wrapped__() == current
    finally:
        L.set_default_labeller(previous)
    assert identity_mod.policy_id.__wrapped__() == current


def test_the_engine_reads_only_the_labels_version_and_digest():
    """design 2.5.10: the label never reaches the IR, the compiler or Z3. Of the engine, only the policy identity imports the
    label package, and only its version and digest; no other engine or IR module names it."""
    users = []
    for tree in (ROOT / "src" / "epinoic_logic" / "engine", ROOT / "src" / "epinoic_logic" / "ir"):
        for p in tree.rglob("*.py"):
            if "selfcert_label" in p.read_text(encoding="utf-8"):
                users.append(p.relative_to(ROOT).as_posix())
    assert users == ["src/epinoic_logic/engine/identity.py"]
    imported = set()
    for node in ast.walk(ast.parse((ROOT / users[0]).read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and "selfcert_label" in node.module:
            imported |= {a.name for a in node.names}
    assert imported == {"LABEL_VERSION", "label_digest"}
