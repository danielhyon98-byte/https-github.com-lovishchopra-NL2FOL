"""The bootstrap refuses to start without Z3 before any engine import: exactly ``KIT-HS-003 z3_unavailable``, exit
status 2, no traceback. The CLI imports the engine lazily, so ``epinoic-logic serve`` reaches the bootstrap too."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from epinoic_logic.integration import bootstrap

SRC = str(Path(__file__).resolve().parents[2] / "src")


def _env(**extra: str) -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if not k.startswith("EPINOIC_")}
    e["PYTHONPATH"] = SRC + os.pathsep + e.get("PYTHONPATH", "")
    e.update(extra)
    return e


def _run(code_or_args, env):
    args = [sys.executable, "-c", code_or_args] if isinstance(code_or_args, str) else code_or_args
    return subprocess.run(args, capture_output=True, text=True, env=env, timeout=120)


def test_module_entry_with_z3_hidden_prints_only_the_refusal_and_exits_2():
    code = ("import sys, runpy; sys.modules['z3'] = None; "
            "sys.argv = ['epinoic_logic.integration', 'serve', '--host', '127.0.0.1', '--port', '0']; "
            "runpy.run_module('epinoic_logic.integration', run_name='__main__')")
    out = _run(code, _env(EPINOIC_PROFILE="integration-sim"))
    assert out.returncode == 2
    assert (out.stdout + out.stderr).strip() == "KIT-HS-003 z3_unavailable"
    assert "Traceback" not in out.stdout + out.stderr


def _hiding_dir(tmp_path: Path) -> str:
    d = tmp_path / "hide" / "z3"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("raise ImportError('z3 hidden by the test')\n")
    return str(tmp_path / "hide")


def test_module_entry_with_a_z3_that_cannot_be_imported(tmp_path):
    env = _env(EPINOIC_PROFILE="integration-sim")
    env["PYTHONPATH"] = _hiding_dir(tmp_path) + os.pathsep + env["PYTHONPATH"]
    out = _run([sys.executable, "-m", "epinoic_logic.integration", "serve", "--host", "127.0.0.1", "--port", "0"], env)
    assert out.returncode == 2
    assert (out.stdout + out.stderr).strip() == "KIT-HS-003 z3_unavailable"
    assert "Traceback" not in out.stdout + out.stderr


def test_epinoic_logic_serve_under_an_integration_profile_reaches_the_bootstrap(tmp_path):
    """The console script when it is installed next to this interpreter; otherwise its exact entry point
    (``epinoic_logic.cli:main``), which is what the console script calls."""
    env = _env(EPINOIC_PROFILE="integration")
    env["PYTHONPATH"] = _hiding_dir(tmp_path) + os.pathsep + env["PYTHONPATH"]
    script = shutil.which("epinoic-logic", path=str(Path(sys.executable).parent))
    args = [script, "serve", "--host", "127.0.0.1", "--port", "0"] if script else [
        sys.executable, "-c", "import sys; from epinoic_logic.cli import main; sys.exit(main(['serve', '--host', '127.0.0.1', '--port', '0']))"]
    out = _run(args, env)
    assert out.returncode == 2
    assert (out.stdout + out.stderr).strip() == "KIT-HS-003 z3_unavailable"
    assert "Traceback" not in out.stdout + out.stderr


def test_import_of_the_cli_and_the_integration_package_needs_no_z3():
    code = ("import sys; sys.modules['z3'] = None; import epinoic_logic.cli, epinoic_logic.integration, epinoic_logic.integration.bootstrap; "
            "print('engine' in ' '.join(m for m in sys.modules if m.startswith('epinoic_logic.engine')))")
    out = _run(code, _env())
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_the_bootstrap_accepts_the_installed_z3_and_refuses_a_version_outside_the_range(monkeypatch):
    assert bootstrap.z3_problem() is None
    monkeypatch.setattr(bootstrap.importlib.metadata, "version", lambda name: "4.8.0")
    assert "outside the accepted range" in bootstrap.z3_problem()
    monkeypatch.setattr(bootstrap.importlib.metadata, "version", lambda name: "6.0.0")
    assert "outside the accepted range" in bootstrap.z3_problem()


def test_require_z3_prints_one_line_and_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "z3_problem", lambda: "hidden")
    with pytest.raises(SystemExit) as exc:
        bootstrap.require_z3()
    assert exc.value.code == 2
    assert capsys.readouterr().err == "KIT-HS-003 z3_unavailable\n"


def test_version_tuple_reads_leading_numeric_components():
    assert bootstrap.version_tuple("5.1.0.0") == (5, 1, 0, 0)
    assert bootstrap.version_tuple("4.13") == (4, 13)
    assert bootstrap.version_tuple("4.13.0.post1") == (4, 13, 0)


@pytest.mark.parametrize("profile", ["Integration", "integration_sim", "integrations", "prod"])
def test_a_misspelled_profile_is_refused_by_name_and_never_starts_the_plain_service(tmp_path, profile):
    """V3-L6: ``epinoic-logic serve`` with an EPINOIC_PROFILE that is not engine, integration or integration-sim prints one
    line, KIT-HS-012 environment_mismatch, and exits 2, before anything is imported or bound: it never starts the engine
    service in place of the checks service, and with Z3 hidden it still names the profile, never a traceback."""
    env = _env(EPINOIC_PROFILE=profile)
    env["PYTHONPATH"] = _hiding_dir(tmp_path) + os.pathsep + env["PYTHONPATH"]
    script = shutil.which("epinoic-logic", path=str(Path(sys.executable).parent))
    args = [script, "serve", "--host", "127.0.0.1", "--port", "0"] if script else [
        sys.executable, "-c", "import sys; from epinoic_logic.cli import main; sys.exit(main(['serve', '--host', '127.0.0.1', '--port', '0']))"]
    out = _run(args, env)
    assert out.returncode == 2
    assert (out.stdout + out.stderr).strip() == "KIT-HS-012 environment_mismatch: EPINOIC_PROFILE is not engine, integration or integration-sim"
    assert "Traceback" not in out.stdout + out.stderr


def test_the_engine_profile_and_an_unset_profile_still_start_the_engine_service(monkeypatch, capsys):
    """The default profile is unchanged: unset, empty or ``engine`` reaches the engine service's own settings (missing
    here, so its own one-line settings error), never a KIT code and never the integration service."""
    import json as _json

    import epinoic_logic.cli as cli
    for value in (None, "", "engine", " engine "):
        if value is None:
            monkeypatch.delenv("EPINOIC_PROFILE", raising=False)
        else:
            monkeypatch.setenv("EPINOIC_PROFILE", value)
        for name in ("EPINOIC_SERVICE_TOKEN", "EPINOIC_SIGNING_KEY"):
            monkeypatch.delenv(name, raising=False)
        code = cli.main(["serve", "--host", "127.0.0.1", "--port", "0"])
        err = capsys.readouterr().err.strip()
        assert code == cli.EXIT_USAGE and "KIT-" not in err, (value, err)
        assert "error" in _json.loads(err.splitlines()[-1]), err  # the engine service's own settings error, one JSON line
