"""The shared diagnosis modules work without the engine: importing ``epinoic_logic.named`` and ``epinoic_logic.lexis``
pulls in neither z3 nor the engine package (whose ``__init__`` imports z3 eagerly), and they still build, cap, read and
display diagnostics when z3 cannot be imported at all. So a deployment without the Z3 engine carries the claim, report,
STEM and channel layers and reads "not computed" for the engine layer."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import epinoic_logic

SRC = str(Path(epinoic_logic.__file__).resolve().parent.parent)

_PROBE = r"""
import json, sys
blocked = "--block" in sys.argv
if blocked:
    class _NoZ3:
        def find_spec(self, name, path=None, target=None):
            if name == "z3" or name.startswith("z3."):
                raise ImportError("z3 is not installed here")
            return None
    sys.meta_path.insert(0, _NoZ3())
import epinoic_logic.named as N
import epinoic_logic.lexis as L
d = N.named_diagnostic("ARG-AC-001", assertion_ids=["l_so"], derivation="ir_structure", message="the converse of a stated rule")
capped = N.cap([d], "info", "ambiguous_translation")[0]
again = N.NamedDiagnostic.model_validate_json(capped.model_dump_json())
print(json.dumps({
    "z3": "z3" in sys.modules,
    "engine": sorted(m for m in sys.modules if m.startswith("epinoic_logic.engine")),
    "effective": N.effective_severity(again),
    "section": N.diagnosis_section([again], engine_state="not_computed"),
    "stems": list(L.content_stems("The source is unreliable")),
    "rules": N.rules_state(None)[0],
}))
"""


def _run(*args: str) -> dict:
    env = {**os.environ, "PYTHONPATH": SRC}
    out = subprocess.run([sys.executable, "-c", _PROBE, *args], capture_output=True, text=True, env=env, timeout=120, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_importing_named_and_lexis_loads_neither_z3_nor_the_engine():
    got = _run()
    assert got["z3"] is False and got["engine"] == []
    assert got["effective"] == "warning" and got["rules"] == "not_computed"


def test_the_shared_modules_work_where_z3_cannot_be_imported():
    got = _run("--block")
    assert got["z3"] is False and got["engine"] == []
    assert got["section"][0].startswith("Argument diagnosis (advisory; the status above is unchanged; rules argdiag-2)")
    assert any("engine layer not computed" in line for line in got["section"])
    assert got["stems"] == ["source", "rely"]
