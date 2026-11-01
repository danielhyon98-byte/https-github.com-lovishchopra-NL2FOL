"""Integration gate 2, the class sweep in the engine and the IR (engine/, ir/): every entry point that takes text or a raw
payload is fed the standard hostile inputs (``tests/core_hostile.py``), and hostile payloads (deep nesting, unclosed
nesting, oversize identifiers and literals, thousands of premises), under a CPU-time bound per call. Each is refused, or
decided, in bounded time; nothing raises. No instance of the class was found in these packages: the validator walks the IR
iteratively and checks every limit before compiling, and a raw payload is parsed with a bounded strict parser.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine.runner import verify
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.engine.validator import parse_and_validate
from epinoic_logic.ir.canonical import canonical_json, sha256_hex, strict_object_pairs

from ..core_hostile import N, SHAPES, one, sweep

_BASE = {"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "consistency", "symbols": [{"name": "x", "sort": "Int"}],
         "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "0"}}}]}

HOSTILE_PAYLOADS = {
    "nested arrays": "[" * N + "]" * N,
    "nested objects": '{"a":' * N + "1" + "}" * N,
    "unclosed nesting": "[" * N,
    "an oversize note": json.dumps({**_BASE, "notes": "(" * N}),
    "a deep expression": json.dumps({**_BASE, "premises": [{"id": "P1", "expr": json.loads('{"op": "not", "arg": ' * 900 + '{"op": "bool", "value": true}' + "}" * 900)}]}),
    "thousands of premises": json.dumps({**_BASE, "premises": [{"id": f"P{i}", "expr": _BASE["premises"][0]["expr"]} for i in range(5_000)]}),
    "an oversize identifier": json.dumps({**_BASE, "problem_id": "x" * N}),
    "an oversize literal": json.dumps({**_BASE, "premises": [{"id": "P1", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "9" * N}}}]}),
}


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_engine_entry_points(shape):
    def entries(text: str):
        yield "verify(text)", lambda: verify(text)
        yield "verify(bytes)", lambda: verify(text.encode("utf-8", "surrogatepass"))
        yield "parse_and_validate", lambda: parse_and_validate(text)
        yield "verify(notes)", lambda: verify(json.dumps({**_BASE, "notes": text[:4_000]}))
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("name", tuple(HOSTILE_PAYLOADS))
def test_hostile_payloads_are_refused_in_bounded_time_and_never_raise(name):
    raw = HOSTILE_PAYLOADS[name]
    slow = sweep(lambda _text: [(name, (lambda: verify(raw)))], texts={"payloads": ""})
    assert not slow
    result = verify(raw)
    assert result.status in (S.INVALID_FORMALIZATION, S.UNSUPPORTED), (name, result.status)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_ir_canonical(shape):
    def entries(text: str):
        yield "canonical_json", lambda: canonical_json({"text": text, "list": [text, {"k": text}]})
        yield "sha256_hex", lambda: sha256_hex(text)
        yield "strict_object_pairs", lambda: strict_object_pairs([("a", text), ("b", text)])
    assert not sweep(entries, texts=one(shape))
