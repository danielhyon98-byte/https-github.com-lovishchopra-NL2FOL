"""Generated copies and pins: compat.py, the Worker's compat.js and subject-map.js, and the JSON Schemas never drift
from their reviewed sources; the subject map routes every subject to the branch it names."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from epinoic_logic.integration import compat
from epinoic_logic.integration.canonical import loads_strict, sha256_json

ROOT = Path(__file__).resolve().parents[2]


def _generator():
    spec = importlib.util.spec_from_file_location("kit_generate", ROOT / "integration" / "tools" / "generate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_generated_file_equals_the_generators_output():
    gen = _generator()
    drifted = [str(p.relative_to(ROOT)) for p, text in gen.outputs().items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    assert drifted == [], f"run python integration/tools/generate.py: {drifted}"


def test_the_compatibility_copy_is_the_reviewed_json():
    raw = loads_strict((ROOT / "integration" / "COMPATIBILITY.json").read_bytes())
    assert compat.thaw(compat.COMPATIBILITY) == raw
    assert compat.COMPATIBILITY_SHA256 == sha256_json(raw)
    assert raw["protocol"] == "epinoic.integration.v1"


def test_the_subject_map_digest_is_pinned_and_every_branch_is_the_hubs():
    raw = loads_strict((ROOT / "integration" / "subject-map.json").read_bytes())
    assert compat.SUBJECT_MAP_SHA256 == sha256_json(raw) == compat.COMPATIBILITY["subject_map"]["sha256"]
    from epinoic_logic.branches import RouterHub
    hub = RouterHub(signing_key=b"test-key-not-a-secret-0123456789")
    for e in raw["entries"]:
        assert hub.branch_for(e["subject"]) == e["branch"], e["slug"]
    stem = {e["branch"] for e in raw["entries"]} & set(compat.COMPATIBILITY["stem_branches"])
    assert stem == set(compat.COMPATIBILITY["stem_branches"])


def test_compat_module_is_standard_library_only_and_frozen():
    import subprocess
    code = ("import sys; sys.modules['z3']=None; sys.modules['pydantic']=None; import epinoic_logic.integration.compat as c, "
            "epinoic_logic.integration.errors, epinoic_logic.integration.bootstrap; "
            "print(c.COMPATIBILITY['protocol'])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={**__import__('os').environ})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "epinoic.integration.v1"
    try:
        compat.COMPATIBILITY["protocol"] = "x"  # type: ignore[index]
    except TypeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("the compatibility set is mutable")
