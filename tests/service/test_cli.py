"""CLI tests: JSON on stdout, one-line JSON errors on stderr, documented exit codes."""
from __future__ import annotations

import json

import pytest

import epinoic_logic.cli as cli
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import VerificationResult

from .conftest import KEY, KEY_ID, transitivity_problem


def run(capsys, *argv: str) -> tuple[int, str, str]:
    rc = cli.main(list(argv))
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_version_prints_component_versions_as_json(capsys):
    rc, out, err = run(capsys, "version")
    assert rc == 0 and err == ""
    body = json.loads(out)
    assert set(body) == {"ir_version", "engine_version", "policy_version", "translator_version", "z3_version"}
    assert body["ir_version"] == "1.0"


def test_verify_prints_a_result_json_with_status(tmp_path, capsys):
    path = tmp_path / "problem.json"
    path.write_text(json.dumps(transitivity_problem()), encoding="utf-8")
    rc, out, err = run(capsys, "verify", str(path))
    assert rc == 0 and err == ""
    body = json.loads(out)
    assert body["status"] == "ENTAILED" and body["claim_id"] == "c1"
    assert body["signature"] is None
    assert body["solver_config"]["timeout_ms"] == 2000


def test_verify_options_are_applied_and_signature_verifies(tmp_path, capsys):
    path = tmp_path / "problem.json"
    path.write_text(json.dumps(transitivity_problem()), encoding="utf-8")
    rc, out, _ = run(capsys, "verify", str(path), "--timeout-ms", "5000", "--rlimit", "1000000", "--signing-key-hex", KEY.hex(), "--key-id", KEY_ID)
    assert rc == 0
    body = json.loads(out)
    assert body["status"] == "ENTAILED"
    assert body["solver_config"] == {**body["solver_config"], "timeout_ms": 5000, "rlimit": 1000000}
    assert body["signature_key_id"] == KEY_ID
    assert verify_signature(VerificationResult.model_validate(body), KEY)


def test_verify_malformed_file_is_a_bound_invalid_formalization_result(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_bytes(b"{this is not json")
    rc, out, err = run(capsys, "verify", str(path))
    assert rc == 0 and err == ""
    body = json.loads(out)
    assert body["status"] == "INVALID_FORMALIZATION" and body["query"] is None
    assert body["diagnostics"][0]["code"] == "E100"


def test_verify_missing_file_is_a_usage_error_without_traceback(tmp_path, capsys):
    rc, out, err = run(capsys, "verify", str(tmp_path / "absent.json"))
    assert rc == 2 and out == ""
    assert json.loads(err)["error"].startswith("cannot read")
    assert "Traceback" not in err


@pytest.mark.parametrize("argv", [("--timeout-ms", "0"), ("--rlimit", "0"), ("--signing-key-hex", "zz")])
def test_verify_invalid_options_are_usage_errors(tmp_path, capsys, argv):
    path = tmp_path / "problem.json"
    path.write_text(json.dumps(transitivity_problem()), encoding="utf-8")
    rc, out, err = run(capsys, "verify", str(path), *argv)
    assert rc == 2 and out == "" and "error" in json.loads(err)


def test_unknown_command_and_missing_command_exit_2(capsys):
    assert cli.main(["frobnicate"]) == 2
    assert cli.main([]) == 2
    capsys.readouterr()


def test_check_report_exits_3_when_the_pipeline_is_unavailable(tmp_path, capsys, monkeypatch):
    real_import = cli.importlib.import_module

    def missing(name, *args, **kwargs):
        if name.startswith("epinoic_logic.translate.pipeline"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(cli.importlib, "import_module", missing)
    report = tmp_path / "report.json"
    fixtures = tmp_path / "fixtures.json"
    report.write_text("{}", encoding="utf-8")
    fixtures.write_text("{}", encoding="utf-8")
    rc, out, err = run(capsys, "check-report", str(report), "--fixtures", str(fixtures))
    assert rc == 3 and out == ""
    assert "not available" in json.loads(err)["error"]


def test_console_script_target_exists():
    assert callable(cli.main)


# --- named engine policy (end-to-end simulation of 16 October 2026, bug 8): the CLI takes a name, as POST /v1/verify does --

def _square_problem() -> dict:
    v = {"op": "var", "name": "x"}
    return {"problem_id": "sq", "request_id": "req1", "claim_id": "c-sq", "query": "satisfiability", "symbols": [{"name": "x", "sort": "Int"}],
            "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "mul", "args": [v, v]}, "right": {"op": "int", "value": "4"}}}]}


def test_verify_takes_a_named_policy_and_binds_it(tmp_path, capsys):
    from epinoic_logic.engine.policies import NONLINEAR_LIMITS, NONLINEAR_RLIMIT, named_policy_of
    path = tmp_path / "square.json"
    path.write_text(json.dumps(_square_problem()), encoding="utf-8")
    rc, out, err = run(capsys, "verify", str(path))
    assert rc == 0 and err == "" and json.loads(out)["status"] == "UNSUPPORTED", "the default policy is unchanged"
    rc, out, err = run(capsys, "verify", str(path), "--policy", "nonlinear", "--signing-key-hex", KEY.hex(), "--key-id", KEY_ID)
    assert rc == 0 and err == ""
    result = VerificationResult.model_validate(json.loads(out))
    assert result.status.value == "SATISFIABLE" and result.limits == NONLINEAR_LIMITS and named_policy_of(result.limits) == "nonlinear"
    assert result.solver_config.rlimit == NONLINEAR_RLIMIT and verify_signature(result, KEY)


@pytest.mark.parametrize("name", ["Nonlinear", "unbounded", "", "nonlinear "])
def test_verify_refuses_an_unknown_policy_with_a_json_error(tmp_path, capsys, name):
    path = tmp_path / "square.json"
    path.write_text(json.dumps(_square_problem()), encoding="utf-8")
    rc, out, err = run(capsys, "verify", str(path), "--policy", name)
    assert rc == cli.EXIT_USAGE and out == ""
    assert json.loads(err) == {"error": "--policy must be one of: joint, linear, nonlinear"}


def test_the_policy_help_names_exactly_the_named_policies_and_the_default():
    """The parser is built before any engine import (an integration profile's bootstrap runs first, and
    ``import epinoic_logic.cli`` needs no Z3), so the help writes the names out; they must be the engine's."""
    from epinoic_logic.engine.policies import LINEAR, NAMED_POLICIES
    assert cli.POLICY_NAMES_HELP == "|".join(sorted(NAMED_POLICIES)) and LINEAR == "linear"
    p_verify = cli.build_parser()._subparsers._group_actions[0].choices["verify"]
    policy = next(a for a in p_verify._actions if a.dest == "policy")
    assert policy.default is None and f"({cli.POLICY_NAMES_HELP}; default {LINEAR})" in policy.help
