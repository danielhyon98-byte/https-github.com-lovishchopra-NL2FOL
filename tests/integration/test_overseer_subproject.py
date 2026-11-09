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

The translator's suite runs where the overseer is not installed (architecture review after arena round 8): a test here
that imports the overseer skips, with ``tests/overseer_attach.py``'s reason, where it is not installed, and a test that
reads the sub-project's files skips where ``overseer/`` is not in the checkout (after the split); what only the
translator states is asserted first, whatever the overseer's state.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import tomllib
from pathlib import Path

import pytest

from epinoic_logic.integration.overseer_port import PINNED_PACK_DIGESTS
from tests.overseer_attach import REASON, overseer

ROOT = Path(__file__).resolve().parents[2]
TRANSLATOR = ROOT / "src" / "epinoic_logic"
OVERSEER = ROOT / "overseer"
#: Why a test that reads the overseer sub-project's files is skipped where the checkout has none (after the split).
NO_SUBPROJECT = "the overseer sub-project (overseer/) is not in this checkout: it was split off into a repository of its own"
#: The translator modules the overseer package may import: the public API and the integration protocol's explicit modules
#: (the overseer port's contract, the vocabulary, its errors, its canonical JSON, the router port's pool operation), never
#: the service's implementation (turn, routes, settings, runtime, selftest): architecture review after arena round 8.
OVERSEER_DOORS = re.compile(r"^epinoic_logic\.api(\.[a-z_]+)?$|^epinoic_logic\.integration\.(canonical|errors|overseer_port|protocol|router_pool)$")
#: The names the overseer's tests and harness imported from translator modules because the public API did not export
#: them (the overseer's ``internal_imports`` category ``missing``), which API 1.1 exports: area -> (public name, internal
#: module the overseer imported it from).
ADDED_IN_1_1 = {
    "ir": tuple(("epinoic_logic.ir.schema", n) for n in ("SourceRef", "Assertion", "IntConst", "RealConst", "Limits", "ALLOWED_OPS")),
    "integrity": (("epinoic_logic.integrity.contracts", "LedgerEntry"), ("epinoic_logic.integrity.contracts", "SynthesizedClaim"),
                  ("epinoic_logic.integrity.contracts", "ConflictRecord"), ("epinoic_logic.integrity.envelope", "ROLE_CONTRACTS"),
                  ("epinoic_logic.integrity.cross_check", "at_stated_precision")),
    "translate": tuple(("epinoic_logic.translate.contracts", n) for n in ("EligibilityClass", "EligibilityDecision", "ProviderInfo", "StructuralFinding")),
    "channel": (("epinoic_logic.channel.contracts", "ConstraintResult"), ("epinoic_logic.channel.contracts", "CoverageRecord"),
                ("epinoic_logic.channel.request_parser", "answer_parts"), ("epinoic_logic.channel.request_parser", "count_answer_words")),
    "branches": (("epinoic_logic.branches.base", "BranchRegistry"), ("epinoic_logic.branches.base", "FormalCheck"),
                 ("epinoic_logic.branches.base", "SubjectBranch"), ("epinoic_logic.branches.packs", "EnglishPack")),
    "adapters": (("epinoic_logic.adapters.markdown", "truncate_claim_text"),),
    "stem": (("epinoic_logic.stem", "clear_document_cache"),),
    "engine": (("epinoic_logic.engine.statuses", "DEFINITIVE"),),
}


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
    """Rewritten to a stricter rule after arena round 8's architecture review (the overseer fixer's handoff, item 3): the
    integration protocol is its explicit modules, the overseer port's contract, the protocol's vocabulary, its errors, its
    canonical JSON and the router port's pool operation, never the service's implementation (turn, routes, settings,
    runtime, selftest, ...), as the overseer's own guard holds (``internal_imports.PROTOCOL_MODULES``); before, any module of
    ``epinoic_logic.integration`` passed."""
    package = OVERSEER / "src" / "epinoic_overseer"
    if not package.is_dir():
        pytest.skip(NO_SUBPROJECT)
    allowed = OVERSEER_DOORS
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


def test_the_isolation_guard_admits_only_the_public_api_and_the_protocols_modules():
    """Controls of :data:`OVERSEER_DOORS` (the stricter rule after arena round 8; before, ``^epinoic_logic\\.(api|integration)``
    admitted every module of the service)."""
    for door in ("epinoic_logic.api", "epinoic_logic.api.engine", "epinoic_logic.api.channel", "epinoic_logic.integration.protocol",
                 "epinoic_logic.integration.overseer_port", "epinoic_logic.integration.router_pool", "epinoic_logic.integration.errors",
                 "epinoic_logic.integration.canonical"):
        assert OVERSEER_DOORS.match(door), door
    for internal in ("epinoic_logic.integration", "epinoic_logic.integration.turn", "epinoic_logic.integration.selftest",
                     "epinoic_logic.integration.routes", "epinoic_logic.integration.settings", "epinoic_logic.integration.runtime",
                     "epinoic_logic.integration.router_port", "epinoic_logic.channel.bus", "epinoic_logic.api.engine.x", "epinoic_logic.apiary"):
        assert not OVERSEER_DOORS.match(internal), internal


def test_the_public_api_states_its_version_and_exports_the_names_the_overseer_imported_directly():
    """The overseer fixer's handoff after arena round 8 (items 1 and 2): the public API states its version (MAJOR.MINOR;
    MAJOR 1, the one the overseer speaks: ``epinoic_overseer.compat.API_MAJOR``), the generated document states it, and
    API 1.1 exports each name the overseer's tests and harness imported from the translator's internal modules because
    the API did not offer it, resolving to the very object the overseer imported."""
    import epinoic_logic.api as api
    assert re.fullmatch(r"[0-9]+\.[0-9]+", api.API_VERSION) and api.API_VERSION.split(".")[0] == "1" and "API_VERSION" in api.__all__
    assert tuple(int(x) for x in api.API_VERSION.split(".")) >= (1, 1)
    assert f"API version: {api.API_VERSION} " in api.markdown()
    table = api.exports_table()
    for area, names in ADDED_IN_1_1.items():
        module = importlib.import_module(f"epinoic_logic.api.{area}")
        for internal, name in names:
            assert name in table[area], (area, name)
            assert getattr(module, name) is getattr(importlib.import_module(internal), name), (area, name)
    assert sum(len(n) for n in ADDED_IN_1_1.values()) == 26
    compat = pytest.importorskip("epinoic_overseer.compat", reason=REASON)  # the overseer's own check, where it is installed
    assert int(api.API_VERSION.split(".")[0]) == compat.API_MAJOR and compat.missing_translator_names() == []


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
    installed_pack = overseer().installed_pack  # the package's public export (epinoic_overseer.pack); skips where it is not installed
    assert PINNED_PACK_DIGESTS == frozenset({installed_pack().identity.sha256})


def test_the_documented_test_command_runs_both_suites_and_the_translator_ships_no_overseer():
    # architecture step 2c: the documented command runs the flash-router sub-project's suite too (founder's instruction);
    # the pin stays an exact list, rewritten to the three suites
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests", "overseer/tests", "flash-router/tests"]
    assert not [p for p in root["tool"]["setuptools"]["package-data"]["epinoic_logic"] if "overseer" in p]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m pytest -q" in readme and "overseer/tests" in readme and "flash-router/tests" in readme
    # the sub-project's half: its files where the checkout has them, its version where it is installed (moved after the
    # translator's own assertions, which hold whatever the overseer's state; architecture review after arena round 8)
    if not OVERSEER.is_dir():
        pytest.skip(NO_SUBPROJECT)
    sub = tomllib.loads((OVERSEER / "pyproject.toml").read_text(encoding="utf-8"))
    assert sub["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    epinoic_overseer = overseer()
    assert sub["project"]["name"] == "epinoic-overseer" and sub["project"]["version"] == epinoic_overseer.__version__


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
