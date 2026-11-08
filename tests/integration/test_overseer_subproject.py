"""The overseer as a separate sub-project (``overseer/``, package ``epinoic_overseer``; architecture step 2 of phase 2),
seen from the translator:

- the translator never imports it: no module of ``epinoic_logic`` imports ``epinoic_overseer`` (it is attached through
  ``RouterHub(auditor=...)``, whose overseer operations the attached auditor carries out, and through the overseer port
  the service loads by name, ``EPINOIC_OVERSEER_PORT``); there is no shim at the old path;
- the overseer reaches the translator only through the translator's documented public API (``epinoic_logic.api``,
  ``docs/PUBLIC_API.md``, generated from the package) and the integration protocol (``epinoic_logic.integration``);
- the service pins the overseer's knowledge pack (pre-build NOTES item 33) to the overseer's installed pack;
- the repository's documented test command (``python -m pytest -q`` at the root) runs both suites, the translator's and
  the overseer's own; the translator's package no longer ships the overseer or its pack.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import tomllib
from pathlib import Path

from epinoic_logic.integration.overseer_port import PINNED_PACK_DIGESTS

ROOT = Path(__file__).resolve().parents[2]
TRANSLATOR = ROOT / "src" / "epinoic_logic"
OVERSEER = ROOT / "overseer"


def _imports(path: Path) -> list[tuple[int, str, ast.AST]]:
    out = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.append((node.level, node.module or "", node))
        elif isinstance(node, ast.Import):
            out.extend((0, a.name, node) for a in node.names)
    return out


def _absolute(p: Path, level: int, mod: str) -> str:
    """The module a (possibly relative) import in the translator's file ``p`` names."""
    if not level:
        return mod
    parts = ["epinoic_logic", *p.relative_to(TRANSLATOR).with_suffix("").parts]
    base = parts[:-1] if parts[-1] != "__init__" else parts[:-1]
    base = base[: len(base) - (level - 1)] if level > 1 else base
    return ".".join(base + ([mod] if mod else []))


def test_the_translator_never_imports_the_overseer():
    for p in sorted(TRANSLATOR.rglob("*.py")):
        for level, mod, _node in _imports(p):
            name = _absolute(p, level, mod)
            assert not name.startswith("epinoic_overseer") and not re.match(r"^epinoic_logic\.overseer(\.|$)", name), f"{p.relative_to(ROOT)}: {name}"
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"import_module\(\s*['\"]epinoic_overseer", text), p
    assert not (TRANSLATOR / "overseer").exists() and importlib.util.find_spec("epinoic_logic.overseer") is None, "no shim at the old path"


def test_the_overseer_reaches_the_translator_only_through_the_public_api_and_the_protocol():
    allowed = re.compile(r"^epinoic_logic\.(api|integration)(\.|$)")
    package = OVERSEER / "src" / "epinoic_overseer"
    used = set()
    for p in sorted(package.rglob("*.py")):
        for level, mod, _node in _imports(p):
            if not level and mod.split(".")[0] == "epinoic_logic":
                assert allowed.match(mod), f"{p.relative_to(ROOT)} imports a translator internal: {mod}"
                used.add(mod.split(".")[1])
    assert used == {"api", "integration"}


def test_the_public_api_document_is_the_generated_one_and_every_name_resolves():
    import epinoic_logic.api as api
    assert (ROOT / "docs" / "PUBLIC_API.md").read_text(encoding="utf-8") == api.markdown()
    table = api.exports_table()
    assert set(table) == set(api.AREAS) and sum(len(t) for t in table.values()) >= 180
    for area, names in table.items():
        module = importlib.import_module(f"epinoic_logic.api.{area}")
        assert sorted(module.__all__) == sorted(names) and set(dir(module)) == set(names)
        for name in names:
            getattr(module, name)  # resolves (AttributeError otherwise)
    try:
        importlib.import_module("epinoic_logic.api.engine").not_a_public_name
    except AttributeError as exc:
        assert "not part of the public API" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unlisted name resolved")


def test_the_public_api_resolves_when_imported_so_a_patch_of_the_translator_is_seen():
    """The API adds no copy: an import through it at call time sees the translator's module as it is then."""
    import epinoic_logic.channel.bus as bus
    from epinoic_logic.api.channel import DETAIL_MAX
    assert DETAIL_MAX == bus._DETAIL_MAX
    original = bus._DETAIL_MAX
    try:
        bus._DETAIL_MAX = original + 1
        from epinoic_logic.api.channel import DETAIL_MAX as patched
        assert patched == original + 1
    finally:
        bus._DETAIL_MAX = original


def test_the_service_pins_the_overseers_installed_pack():
    from epinoic_overseer.pack import installed_pack
    assert PINNED_PACK_DIGESTS == frozenset({installed_pack().identity.sha256})


def test_the_documented_test_command_runs_both_suites_and_the_translator_ships_no_overseer():
    # architecture step 2c: the documented command runs the flash-router sub-project's suite too (founder's instruction);
    # the pin stays an exact list, rewritten to the three suites
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests", "overseer/tests", "flash-router/tests"]
    assert not [p for p in root["tool"]["setuptools"]["package-data"]["epinoic_logic"] if "overseer" in p]
    sub = tomllib.loads((OVERSEER / "pyproject.toml").read_text(encoding="utf-8"))
    import epinoic_overseer
    assert sub["project"]["name"] == "epinoic-overseer" and sub["project"]["version"] == epinoic_overseer.__version__
    assert sub["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m pytest -q" in readme and "overseer/tests" in readme and "flash-router/tests" in readme


def test_the_arena_harness_attaches_the_overseer_only_in_its_delivery_pass():
    """``scripts/arena/run_arena.py`` is the integration harness of the whole repository: it imports the overseer only
    inside the functions of its delivery pass (the overseer's delivery policy on a hub of its own), never at import."""
    p = ROOT / "scripts" / "arena" / "run_arena.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [n for n in top if any((getattr(n, "module", "") or "").startswith("epinoic_overseer") or a.name.startswith("epinoic_overseer") for a in n.names)]
    users = {fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
             for n in ast.walk(fn) if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("epinoic_overseer")}
    assert users and users <= {"_delivery_auditor", "delivery_record", "delivery_pass"}, users
