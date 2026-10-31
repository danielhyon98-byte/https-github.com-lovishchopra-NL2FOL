"""Integration gate, round 1: the command line's signing key (security-8) and adapter loading (security-6, CLI half).

* ``--signing-key-hex 00`` signed results under any key id with a one-byte key, below the service's minimum of 16 bytes,
  and the key could come only from argv, where the process list shows it.
* ``_load_adapter`` imported ``epinoic_logic.adapters.<text>`` for any ``--adapter`` text before it refused the id.
"""
from __future__ import annotations

import json
import sys

import pytest

from epinoic_logic import cli


def _problem(tmp_path):
    p = {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
         "symbols": [{"name": "x", "sort": "Int"}], "premises": [{"id": "P", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "3"}}}],
         "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "2"}}}}
    path = tmp_path / "p.json"
    path.write_text(json.dumps(p), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("hexkey", ["00", "00" * 15])
def test_a_signing_key_shorter_than_the_service_minimum_is_refused(tmp_path, capsys, hexkey):
    rc = cli.main(["verify", _problem(tmp_path), "--signing-key-hex", hexkey, "--key-id", "prod"])
    captured = capsys.readouterr()
    shown = captured.out + captured.err
    assert rc == 2 and "at least 16 bytes" in shown and "signature_key_id" not in shown


def test_a_key_from_a_file_or_the_environment_signs(tmp_path, capsys, monkeypatch):
    key = "11" * 32
    path = tmp_path / "key.hex"
    path.write_text(key + "\n", encoding="utf-8")
    assert cli.main(["verify", _problem(tmp_path), "--signing-key-file", str(path), "--key-id", "k1"]) == 0
    assert json.loads(capsys.readouterr().out)["signature_key_id"] == "k1"
    monkeypatch.setenv("EPINOIC_SIGNING_KEY", key)
    assert cli.main(["verify", _problem(tmp_path), "--key-id", "k2"]) == 0
    assert json.loads(capsys.readouterr().out)["signature_key_id"] == "k2"
    assert cli.main(["verify", _problem(tmp_path), "--signing-key-file", str(path), "--signing-key-hex", key]) == 2  # one source only


@pytest.mark.parametrize("adapter_id", ["stem_specialist.parser", "english_specialist.fixtures", "../../os", "generic_structured"])
def test_an_adapter_id_outside_the_allowlist_imports_nothing(adapter_id):
    before = set(sys.modules)
    with pytest.raises(cli.CliError):
        cli._load_adapter(adapter_id)
    assert not [m for m in set(sys.modules) - before if m.startswith("epinoic_logic.adapters.")]


def test_an_allowed_adapter_still_loads():
    assert cli._load_adapter("generic-structured") is not None
