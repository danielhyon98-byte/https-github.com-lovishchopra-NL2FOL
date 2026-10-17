#!/usr/bin/env python3
"""Generate every per-side copy of the kit's pinned data, and the JSON Schemas of the protocol messages.

Sources (edited by hand, reviewed): ``integration/COMPATIBILITY.json`` and ``integration/subject-map.json``.
Generated (never edited by hand; ``tests/integration/test_generated.py`` fails when any of them drifts):

* ``src/epinoic_logic/integration/compat.py``: the service's copy of both documents (standard library only);
* ``integration/website/src/verify/compat.js`` and ``integration/website/src/verify/subject-map.js``: the Worker's copies;
* ``integration/schemas/*.schema.json``: JSON Schemas of the protocol messages, from the pydantic models;
* ``integration/schemas/synthesis-vocabulary.v1.json``: the synthesis contract's closed vocabularies
  (``combinator_port.vocabulary_document``, from ``integrity.contracts``), and ``combinator-port.v1.json``: the combinator
  port's rules its schemas cannot state (``combinator_port.port_rules_document``);
* ``combinator/src/epinoic_combinator/contract/``: the combinator sub-project's copy of the published contract it validates
  every output against (the combinator-port schemas and the vocabulary, byte for byte; ``combinator_port.CONTRACT_FILES``),
  written only while the sub-project is in this repository.

The generator refuses to write when ``COMPATIBILITY.json`` pins a subject-map digest other than the subject map's own:
the pin is changed on purpose, never as a side effect.

Usage::

    python integration/tools/generate.py            # write every output
    python integration/tools/generate.py --check    # exit 1 and list the outputs that differ (writes nothing)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPAT_JSON = ROOT / "integration" / "COMPATIBILITY.json"
SUBJECT_MAP_JSON = ROOT / "integration" / "subject-map.json"
COMPAT_PY = ROOT / "src" / "epinoic_logic" / "integration" / "compat.py"
COMPAT_JS = ROOT / "integration" / "website" / "src" / "verify" / "compat.js"
SUBJECT_MAP_JS = ROOT / "integration" / "website" / "src" / "verify" / "subject-map.js"
SCHEMAS_DIR = ROOT / "integration" / "schemas"
COMBINATOR_CONTRACT = ROOT / "combinator" / "src" / "epinoic_combinator" / "contract"
VOCABULARY_JSON = SCHEMAS_DIR / "synthesis-vocabulary.v1.json"
PORT_RULES_JSON = SCHEMAS_DIR / "combinator-port.v1.json"

#: (schema file name, "module:Model"): every protocol message with a schema of its own.
SCHEMA_MODELS: tuple[tuple[str, str], ...] = (
    ("capabilities.v1.schema.json", "epinoic_logic.integration.protocol:Capabilities"),
    ("specialist-answer.v1.schema.json", "epinoic_logic.integration.protocol:SpecialistAnswer"),
    ("turn-check.v1.schema.json", "epinoic_logic.integration.protocol:TurnCheckRequest"),
    ("turn-verdict.v1.schema.json", "epinoic_logic.integration.protocol:TurnVerdict"),
    ("overseer-hello.v1.schema.json", "epinoic_logic.integration.overseer_port:OverseerHello"),
    ("overseer-clearance.v1.schema.json", "epinoic_logic.integration.overseer_port:ClearanceDecision"),
    ("overseer-final-audit.v1.schema.json", "epinoic_logic.integration.overseer_port:FinalAudit"),
    ("overseer-delivery.v1.schema.json", "epinoic_logic.integration.overseer_port:DeliveryDecision"),
    ("overseer-review-ticket.v1.schema.json", "epinoic_logic.integration.overseer_port:ReviewTicket"),
    ("combinator-input.v1.schema.json", "epinoic_logic.integration.combinator_port:CombinatorInput"),
    ("combinator-output.v1.schema.json", "epinoic_logic.integration.combinator_port:CombinatorOutput"),
    ("combinator-hello.v1.schema.json", "epinoic_logic.integration.combinator_port:CombinatorHello"),
    ("combinator-refusal.v1.schema.json", "epinoic_logic.integration.combinator_port:CombinatorRefusal"),
    ("router-hello.v1.schema.json", "epinoic_logic.integration.router_port:RouterHello"),
    ("routing-request.v1.schema.json", "epinoic_logic.integration.router_port:RoutingRequest"),
    ("routing-plan.v1.schema.json", "epinoic_logic.integration.router_port:RoutingPlan"),
)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load(path: Path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise SystemExit(f"{path.name}: repeated key {k!r}")
            out[k] = v
        return out
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def compat_texts() -> dict[Path, str]:
    compat, subject_map = _load(COMPAT_JSON), _load(SUBJECT_MAP_JSON)
    sm_digest, compat_digest = _sha256(subject_map), _sha256(compat)
    pinned = compat.get("subject_map", {}).get("sha256")
    if pinned != sm_digest:
        raise SystemExit(f"COMPATIBILITY.json pins subject map {pinned}, but subject-map.json has digest {sm_digest}: "
                         "change the pin on purpose, then generate again")
    if compat.get("subject_map", {}).get("version") != subject_map.get("version"):
        raise SystemExit("COMPATIBILITY.json and subject-map.json name different subject-map versions")
    py = (
        '"""GENERATED by integration/tools/generate.py from integration/COMPATIBILITY.json and integration/subject-map.json.\n\n'
        "Do not edit by hand: tests/integration/test_generated.py fails when this file differs from the generator's output.\n"
        "Standard library only (the bootstrap reads the accepted Z3 range from here before any engine import). Both\n"
        "documents are frozen: mappings are read-only and lists are tuples; :func:`thaw` gives a JSON copy.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "import json as _json\n"
        "from types import MappingProxyType as _MappingProxyType\n"
        "from typing import Any as _Any\n\n"
        '__all__ = ["COMPATIBILITY", "SUBJECT_MAP", "COMPATIBILITY_SHA256", "SUBJECT_MAP_SHA256", "thaw"]\n\n\n'
        "def _freeze(value: _Any) -> _Any:\n"
        "    if isinstance(value, dict):\n"
        "        return _MappingProxyType({k: _freeze(v) for k, v in value.items()})\n"
        "    if isinstance(value, list):\n"
        "        return tuple(_freeze(v) for v in value)\n"
        "    return value\n\n\n"
        "def thaw(value: _Any) -> _Any:\n"
        '    """A plain JSON copy (dicts and lists) of a frozen value."""\n'
        "    if isinstance(value, _MappingProxyType) or isinstance(value, dict):\n"
        "        return {k: thaw(v) for k, v in value.items()}\n"
        "    if isinstance(value, (tuple, list)):\n"
        "        return [thaw(v) for v in value]\n"
        "    return value\n\n\n"
        f"_COMPATIBILITY_JSON = {_canonical(compat)!r}\n"
        f"_SUBJECT_MAP_JSON = {_canonical(subject_map)!r}\n\n"
        "COMPATIBILITY = _freeze(_json.loads(_COMPATIBILITY_JSON))\n"
        "SUBJECT_MAP = _freeze(_json.loads(_SUBJECT_MAP_JSON))\n"
        f'COMPATIBILITY_SHA256 = "{compat_digest}"\n'
        f'SUBJECT_MAP_SHA256 = "{sm_digest}"\n'
    )
    js_head = ("// GENERATED by integration/tools/generate.py from integration/@SRC@. Do not edit by hand:\n"
               "// tests/integration/test_generated.py fails when this file differs from the generator's output.\n"
               "// Invariant: a deeply frozen copy of the reviewed JSON; the digest is SHA-256 of its canonical JSON.\n\n"
               "const deepFreeze = (value) => {\n"
               "  if (value !== null && typeof value === \"object\") {\n"
               "    for (const child of Object.values(value)) deepFreeze(child);\n"
               "    Object.freeze(value);\n"
               "  }\n"
               "  return value;\n"
               "};\n\n")
    compat_js = (js_head.replace("@SRC@", "COMPATIBILITY.json")
                 + f"export const COMPATIBILITY = deepFreeze({json.dumps(compat, indent=2, sort_keys=True, ensure_ascii=False)});\n\n"
                 + f'export const COMPATIBILITY_SHA256 = "{compat_digest}";\n')
    subject_js = (js_head.replace("@SRC@", "subject-map.json")
                  + f"export const SUBJECT_MAP = deepFreeze({json.dumps(subject_map, indent=2, sort_keys=True, ensure_ascii=False)});\n\n"
                  + f'export const SUBJECT_MAP_SHA256 = "{sm_digest}";\n')
    return {COMPAT_PY: py, COMPAT_JS: compat_js, SUBJECT_MAP_JS: subject_js}


def schema_texts() -> dict[Path, str]:
    sys.path.insert(0, str(ROOT / "src"))
    out: dict[Path, str] = {}
    for name, ref in SCHEMA_MODELS:
        module, _, attr = ref.partition(":")
        model = getattr(importlib.import_module(module), attr)
        schema = model.model_json_schema(by_alias=True)
        out[SCHEMAS_DIR / name] = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    combinator_port = importlib.import_module("epinoic_logic.integration.combinator_port")
    out[VOCABULARY_JSON] = json.dumps(combinator_port.vocabulary_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out[PORT_RULES_JSON] = json.dumps(combinator_port.port_rules_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if COMBINATOR_CONTRACT.parent.is_dir():  # the sub-project's copy of the published contract (absent after a split)
        for name in combinator_port.CONTRACT_FILES:
            out[COMBINATOR_CONTRACT / name] = out[SCHEMAS_DIR / name]
    return out


def outputs(*, schemas: bool = True) -> dict[Path, str]:
    texts = compat_texts()
    if schemas:
        texts.update(schema_texts())
    return texts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when any output differs from the generator's (writes nothing)")
    ap.add_argument("--no-schemas", action="store_true", help="only the compatibility copies (used before the models import)")
    args = ap.parse_args(argv)
    texts = compat_texts()
    if not args.check:  # the models read compat.py, so it is written before the schemas are generated from them
        for path, text in texts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if not args.no_schemas:
        texts.update(schema_texts())
    drifted = [p for p, t in texts.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    if args.check:
        for p in drifted:
            print(f"drift: {p.relative_to(ROOT)}")
        return 1 if drifted else 0
    for path in drifted:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(texts[path], encoding="utf-8")
    stale = sorted(p.name for p in SCHEMAS_DIR.glob("*.schema.json") if not args.no_schemas and SCHEMAS_DIR / p.name not in texts)
    for name in stale:
        print(f"note: {name} is not generated any more; remove it on purpose")
    print(f"generated {len(texts)} file(s); {len(drifted)} changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
