"""Gate G1 and the "(connected in phase 2: ...)" marks after the overseer's split (architecture lenses after arena round
8, readiness kit): ``integration/readiness/check.py`` looks for the overseer the way the service imports it, the package
``epinoic_overseer`` and its port adapter ``epinoic_overseer.port`` on the import path of a process run from the kit
(``check.py`` ``_py``), so an overseer installed as a package (as after its split, ``overseer/README.md``) is found as
well as the sub-project ``overseer/``; and the mark, which tells a session that a BLOCKER row is the expected state of a
pre-build commit, is given only to a kit whose contract line predates 0.5. On a 0.5 kit a missing overseer is a defect
of the commit, and the row says so.

Before the fix: a tree without ``overseer/`` and the overseer installed gave a false "G1 overseer package BLOCKER ...
(connected in phase 2: ...)" although the service starts with the installed port; and with no overseer at all a 0.5
kit's rows carried the pre-build mark (G1, and ``KIT-HS-007`` at start-up).

Each case runs ``check.py`` under a fresh interpreter in a virtual environment of its own (no pip, none of this
interpreter's site packages), where an overseer is "installed" only through a ``.pth`` file naming its directory, as an
install puts a package on the path; the kits are minimal trees holding what G1 reads."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "integration" / "readiness" / "check.py"
MARK = "connected in phase 2"
PACKAGE_MARK = "(connected in phase 2: the rebuilt overseer and its port adapter)"
ADAPTER_MARK = " (connected in phase 2: the overseer port adapter)"


def _kit(root: Path, *, contract: Optional[str] = "0.5", named: bool = True, subproject: Optional[str] = None) -> Path:
    """A kit tree with what G1 reads: the contract line (``None``: a contract without one), the engine's named policies
    (or none), the STEM branches and the protocol. ``subproject``: ``"port"`` puts the overseer sub-project with its port
    adapter at ``overseer/src/epinoic_overseer/``, ``"package"`` the package without the adapter, ``None`` no overseer."""
    (root / "docs").mkdir(parents=True)
    line = f"- **Contract version:** {contract} (2026-10-31).\n" if contract is not None else "- no version line\n"
    (root / "docs" / "integration-contract.md").write_text("# Integration contract\n\n" + line, encoding="utf-8")
    engine = root / "src" / "epinoic_logic" / "engine"
    engine.mkdir(parents=True)
    (engine / "policies.py").write_text("NAMED_POLICIES = {}\n\n\ndef named_policy(name, config):\n    return None\n" if named else "LIMITS = {}\n",
                                        encoding="utf-8")
    branches = root / "src" / "epinoic_logic" / "branches"
    branches.mkdir(parents=True)
    (branches / "registry.py").write_text('BRANCHES = ("sciences", "mathematics", "computer_science")\n', encoding="utf-8")
    (root / "integration").mkdir()
    (root / "integration" / "COMPATIBILITY.json").write_text('{"protocol": "epinoic.integration.v1"}\n', encoding="utf-8")
    if subproject is not None:
        _overseer(root / "overseer" / "src", port=subproject == "port")
        (root / "overseer" / "pyproject.toml").write_text('[project]\nname = "epinoic-overseer"\nversion = "8.8.8"\n', encoding="utf-8")
    return root


def _overseer(where: Path, *, port: bool = True) -> Path:
    """An overseer package at ``where/epinoic_overseer`` that refuses to be run: the readiness check locates it and its
    port adapter, as the service would import them, and never runs its code (its version is read from the text)."""
    package = where / "epinoic_overseer"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "9.9.9"\nraise SystemExit("the readiness check never runs the overseer\'s code")\n',
                                         encoding="utf-8")
    if port:
        (package / "port.py").write_text('raise SystemExit("the readiness check never runs the port adapter")\n', encoding="utf-8")
    return where


def _python(base: Path, installed: Optional[Path] = None) -> str:
    """A fresh interpreter (``python -m venv --without-pip``): none of this interpreter's packages, so an overseer is on
    its import path only when ``installed`` names a directory holding one (a ``.pth`` file in its site packages)."""
    venv = base / "venv"
    made = subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], capture_output=True, text=True, timeout=120)
    if made.returncode != 0:
        pytest.skip(f"no virtual environment can be created here: {made.stderr.strip()[-200:]}")
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if installed is not None:
        purelib = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], capture_output=True,
                                 text=True, timeout=60, check=True).stdout.strip()
        Path(purelib).mkdir(parents=True, exist_ok=True)
        (Path(purelib) / "epinoic_overseer_test_install.pth").write_text(f"{installed}\n", encoding="utf-8")
    return str(python)


def _g1(python: str, kit: Path, cwd: Path) -> tuple[int, dict, str]:
    out = subprocess.run([python, "-I", str(CHECK), "--g1", str(kit)], capture_output=True, text=True, timeout=120, cwd=str(cwd))
    rows = {line.split("  ")[0].strip(): line for line in out.stdout.splitlines()}
    return out.returncode, rows, out.stdout + out.stderr


# ----------------------------------------------------------------------------------------------- G1 finds an installed overseer


def test_g1_finds_an_overseer_installed_as_a_package_outside_the_kit(tmp_path):
    """The split: no ``overseer/`` in the kit, the overseer installed. G1 finds it where the service imports it, says it is
    installed outside the kit with the version its code states, and passes; no row carries the pre-build mark."""
    kit = _kit(tmp_path / "kit")
    site = _overseer(tmp_path / "site")
    code, rows, out = _g1(_python(tmp_path / "with-overseer", installed=site), kit, tmp_path)
    assert code == 0, out
    row = rows["G1 overseer package"]
    assert "  PASS  " in row and f"{(site / 'epinoic_overseer').resolve().as_posix()}/" in row, out
    assert "(installed: epinoic-overseer 9.9.9, outside the kit; attached through the overseer port)" in row, out
    assert MARK not in out and "never runs" not in out, out


def test_g1_on_this_interpreter_finds_its_installed_overseer_on_a_tree_without_overseer(tmp_path):
    """The finding's own reproduction: a translator tree with ``overseer/`` removed, run with an interpreter in which the
    overseer is installed (as the documented install does, ``pip install -e ./overseer``). Before the fix G1 printed
    "BLOCKER overseer/src/epinoic_overseer/ absent (connected in phase 2: ...)" although the service starts with the
    installed port adapter."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_") and k != "PYTHONPATH"}
    probe = subprocess.run([sys.executable, "-c", "import importlib.util; s = importlib.util.find_spec('epinoic_overseer'); print(s.origin if s else '')"],
                           capture_output=True, text=True, timeout=60, env=env, cwd=str(tmp_path))
    if not probe.stdout.strip():
        pytest.skip("the overseer is not installed in this interpreter (only on the test session's path): the fresh-interpreter cases cover it")
    kit = _kit(tmp_path / "kit")
    code, rows, out = _g1(sys.executable, kit, tmp_path)
    assert code == 0 and "  PASS  " in rows["G1 overseer package"], out
    assert f"{Path(probe.stdout.strip()).resolve().parent.as_posix()}/ (installed: epinoic-overseer " in rows["G1 overseer package"], out
    assert MARK not in out, out


# ----------------------------------------------------------------------------------------------- the mark only before phase 2


def test_g1_on_a_0_5_kit_without_any_overseer_names_a_defect_never_the_pre_build_mark(tmp_path):
    """No overseer in the kit and none installed: on a kit whose contract line is 0.5 the row is a BLOCKER that names a
    defect of the commit, never "(connected in phase 2: ...)"; so are the named policies missing there, and a contract
    without a version line is no known pre-build state either."""
    python = _python(tmp_path / "bare")
    code, rows, out = _g1(python, _kit(tmp_path / "kit"), tmp_path)
    assert code == 1, out
    assert "  BLOCKER  " in rows["G1 overseer package"] and "a defect of this commit: its contract line is 0.5" in rows["G1 overseer package"], out
    assert "neither overseer/src/epinoic_overseer/ nor an installed package" in rows["G1 overseer package"], out
    assert [name for name, line in rows.items() if "  BLOCKER  " in line] == ["G1 overseer package"], out
    assert MARK not in out, out
    code, rows, out = _g1(python, _kit(tmp_path / "kit-no-policies", named=False), tmp_path)
    assert code == 1 and "  BLOCKER  " in rows["G1 named policies (contract 0.3)"] and "absent (a defect of this commit" in rows["G1 named policies (contract 0.3)"], out
    assert MARK not in out, out
    code, rows, out = _g1(python, _kit(tmp_path / "kit-no-line", contract=None, named=False), tmp_path)
    assert code == 1 and "contract absent" in rows["G1 contract 0.5"], out
    assert MARK not in out, out


def test_a_kit_that_predates_phase_2_keeps_its_marks(tmp_path):
    """A pre-build commit keeps the mark for the parts phase 2 connects: after the contract 0.3 merge (line 0.4, named
    policies) the overseer package alone; before it (line 0.2, no named policies) the contract line, the overseer
    package and the named policies, as before the fix. With the overseer installed, a pre-build kit's G1 passes too."""
    python = _python(tmp_path / "bare")
    code, rows, out = _g1(python, _kit(tmp_path / "kit-04", contract="0.4"), tmp_path)
    assert code == 1 and "  BLOCKER  " in rows["G1 overseer package"] and PACKAGE_MARK in rows["G1 overseer package"], out
    # after the contract 0.3 merge an older contract line is a defect (unchanged): the line's row carries no mark
    assert [name for name, line in rows.items() if "  BLOCKER  " in line] == ["G1 contract 0.5", "G1 overseer package"], out
    assert MARK not in rows["G1 contract 0.5"], out
    code, rows, out = _g1(python, _kit(tmp_path / "kit-02", contract="0.2", named=False), tmp_path)
    blockers = [line for line in rows.values() if "  BLOCKER  " in line]
    assert code == 1 and len(blockers) == 3 and all(f"({MARK}: " in line for line in blockers), out
    assert "contract 0.2 (connected in phase 2: contract 0.3 merge, then the line says 0.5)" in rows["G1 contract 0.5"], out
    installed = _python(tmp_path / "with-overseer", installed=_overseer(tmp_path / "site"))
    code, rows, out = _g1(installed, _kit(tmp_path / "kit-04-installed", contract="0.4"), tmp_path)
    assert "  PASS  " in rows["G1 overseer package"] and "installed: epinoic-overseer 9.9.9" in rows["G1 overseer package"], out


def test_g1_finds_the_sub_project_on_the_service_s_path_as_before(tmp_path):
    """The kit's own sub-project ``overseer/src/epinoic_overseer/`` is still found, relative to the kit, with the
    sub-project's version, under an interpreter where nothing is installed."""
    code, rows, out = _g1(_python(tmp_path / "bare"), _kit(tmp_path / "kit", subproject="port"), tmp_path)
    assert code == 0, out
    assert "overseer/src/epinoic_overseer/ (epinoic-overseer 8.8.8, a sub-project of its own; attached through the overseer port)" in rows["G1 overseer package"], out


_NOTES = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("kit_readiness_check_split", sys.argv[1])
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
print(json.dumps([check._phase2_note(Path(kit), line) for kit, line in json.loads(sys.argv[2])]))
"""


def _notes(python: str, cases: list[tuple[Path, str]], cwd: Path) -> list[str]:
    out = subprocess.run([python, "-I", "-c", _NOTES, str(CHECK), json.dumps([(str(k), line) for k, line in cases])],
                         capture_output=True, text=True, timeout=120, cwd=str(cwd))
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_start_up_refusal_is_marked_only_on_a_pre_build_kit_whose_adapter_is_absent_where_the_service_imports_it(tmp_path):
    """``_phase2_note`` (the service preflight, start-up and simulation rows): ``KIT-HS-007`` is marked only on a kit that
    predates phase 2 and only when the port adapter is absent where the service imports it (the sub-project's, or an
    installed overseer's); ``KIT-HS-006`` only on a kit before the contract 0.3 merge. A 0.5 kit's refusal is never
    marked. Before the fix a 0.5 kit with no overseer printed "KIT-HS-007 ... (connected in phase 2: the overseer port
    adapter)" at start-up."""
    hs7, hs6 = "KIT-HS-007 overseer_unavailable: the overseer port adapter 'epinoic_overseer.port' cannot be imported", "KIT-HS-006 named_policies_unavailable: x"
    kits = {
        "0.5": _kit(tmp_path / "k05"), "0.5-no-policies": _kit(tmp_path / "k05n", named=False), "0.4": _kit(tmp_path / "k04", contract="0.4"),
        "0.4-adapter": _kit(tmp_path / "k04a", contract="0.4", subproject="port"),
        "0.4-package-only": _kit(tmp_path / "k04p", contract="0.4", subproject="package"),
        "0.2": _kit(tmp_path / "k02", contract="0.2", named=False),
    }
    bare = _python(tmp_path / "bare")
    assert _notes(bare, [(kits["0.5"], hs7), (kits["0.5-no-policies"], hs6), (kits["0.4"], hs7), (kits["0.4-adapter"], hs7),
                         (kits["0.4-package-only"], hs7), (kits["0.2"], hs6), (kits["0.4"], "KIT-HS-005 something else")], tmp_path) == [
        "", "", ADAPTER_MARK, "", ADAPTER_MARK,
        " (connected in phase 2: the named policies of contract 0.3; then KIT-HS-007 until the overseer port adapter)", ""]
    installed = _python(tmp_path / "with-overseer", installed=_overseer(tmp_path / "site"))
    assert _notes(installed, [(kits["0.4"], hs7), (kits["0.5"], hs7)], tmp_path) == ["", ""]  # the installed adapter is found
    without_port = _python(tmp_path / "with-package-only", installed=_overseer(tmp_path / "site-package-only", port=False))
    assert _notes(without_port, [(kits["0.4"], hs7), (kits["0.5"], hs7)], tmp_path) == [ADAPTER_MARK, ""]


def test_the_probe_locates_the_overseer_without_running_it_or_the_directory_it_is_run_from(tmp_path):
    """The probe G1 and the marks rest on locates the package and its adapter (``find_spec``, then the import system's
    path finder in the package's own locations) and imports neither: the stub overseer above exits if it is run. It runs
    with ``-P``, so a module in the directory check.py is run from (here a ``json.py`` that would leave a trace) is
    never imported in its place."""
    spec = importlib.util.spec_from_file_location("kit_readiness_check_probe", CHECK)
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    probe = check._OVERSEER_PROBE
    assert "find_spec(\"epinoic_overseer\")" in probe and "PathFinder.find_spec(\"epinoic_overseer.port\"" in probe
    assert "import_module" not in probe and "__import__" not in probe and "exec(" not in probe
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    trace = tmp_path / "planted-module-ran"
    (cwd / "json.py").write_text(f"open({str(trace)!r}, 'w').close()\nraise SystemExit(3)\n", encoding="utf-8")
    code, rows, out = _g1(_python(tmp_path / "with-overseer", installed=_overseer(tmp_path / "site")), _kit(tmp_path / "kit"), cwd)
    assert code == 0 and "  PASS  " in rows["G1 overseer package"], out
    assert not trace.exists(), "the probe imported a module of the directory it was run from"
