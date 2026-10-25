"""Re-run review finding security-8: the command line signed with any non-empty key (one byte was enough) and took the
key only from the command line, where other users of the machine can read it. A key shorter than the service's floor is
now a usage error, and the key can come from a file or an environment variable."""
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


@pytest.fixture
def problem_file(tmp_path):
    path = tmp_path / "problem.json"
    path.write_text(json.dumps(transitivity_problem()), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("key_hex", ["00", "00" * 15, KEY.hex()[:30]])
def test_a_key_shorter_than_the_service_floor_is_refused(capsys, problem_file, key_hex: str):
    rc, out, err = run(capsys, "verify", problem_file, "--signing-key-hex", key_hex, "--key-id", "prod")
    assert rc == 2 and out == ""
    message = json.loads(err)["error"]
    assert f"at least {cli.MIN_SIGNING_KEY_BYTES} bytes" in message and key_hex not in message  # the key is never echoed


def test_the_floor_is_the_services_own():
    from epinoic_logic.service.settings import MIN_SIGNING_KEY_BYTES

    assert cli.MIN_SIGNING_KEY_BYTES == MIN_SIGNING_KEY_BYTES == 16


def test_a_key_at_the_floor_signs(capsys, problem_file):
    """Control: 16 bytes are accepted and the result verifies under the key."""
    key = bytes(range(16))
    rc, out, _ = run(capsys, "verify", problem_file, "--signing-key-hex", key.hex(), "--key-id", KEY_ID)
    assert rc == 0 and verify_signature(VerificationResult.model_validate(json.loads(out)), key)


def test_the_key_can_come_from_a_file(capsys, problem_file, tmp_path):
    key_file = tmp_path / "signing.key"
    key_file.write_text(KEY.hex() + "\n", encoding="ascii")
    rc, out, _ = run(capsys, "verify", problem_file, "--signing-key-file", str(key_file), "--key-id", KEY_ID)
    body = json.loads(out)
    assert rc == 0 and body["signature_key_id"] == KEY_ID and verify_signature(VerificationResult.model_validate(body), KEY)


def test_the_key_can_come_from_the_environment(capsys, problem_file, monkeypatch):
    monkeypatch.setenv(cli.SIGNING_KEY_ENV, KEY.hex())
    rc, out, _ = run(capsys, "verify", problem_file, "--signing-key-env", "--key-id", KEY_ID)
    assert rc == 0 and verify_signature(VerificationResult.model_validate(json.loads(out)), KEY)
    monkeypatch.setenv("MY_ENGINE_KEY", KEY.hex())
    rc, out, _ = run(capsys, "verify", problem_file, "--signing-key-env", "MY_ENGINE_KEY")
    assert rc == 0 and verify_signature(VerificationResult.model_validate(json.loads(out)), KEY)


def test_the_environment_is_read_only_when_asked(capsys, problem_file, monkeypatch):
    """Control: with no key option the result is unsigned, whatever the environment holds."""
    monkeypatch.setenv(cli.SIGNING_KEY_ENV, KEY.hex())
    rc, out, _ = run(capsys, "verify", problem_file)
    assert rc == 0 and json.loads(out)["signature"] is None


@pytest.mark.parametrize("case", ["two sources", "unset variable", "missing file", "binary file", "short key file"])
def test_key_source_errors_are_usage_errors(capsys, problem_file, tmp_path, monkeypatch, case: str):
    monkeypatch.delenv("NO_SUCH_ENGINE_KEY", raising=False)
    binary = tmp_path / "binary.key"
    binary.write_bytes(b"\xff\xfe" * 20)
    short = tmp_path / "short.key"
    short.write_text("00ff", encoding="ascii")
    argv = {
        "two sources": ["--signing-key-hex", KEY.hex(), "--signing-key-env"],
        "unset variable": ["--signing-key-env", "NO_SUCH_ENGINE_KEY"],
        "missing file": ["--signing-key-file", str(tmp_path / "absent.key")],
        "binary file": ["--signing-key-file", str(binary)],
        "short key file": ["--signing-key-file", str(short)],
    }[case]
    rc, out, err = run(capsys, "verify", problem_file, *argv)
    assert rc == 2 and out == "" and "error" in json.loads(err) and "Traceback" not in err


def test_check_report_refuses_a_short_key_too_and_signs_with_a_key_file(capsys, tmp_path):
    from .test_outcomes import maths_fixture, maths_report

    report = tmp_path / "report.json"
    report.write_text(json.dumps(maths_report().model_dump(mode="json")), encoding="utf-8")
    fixtures = tmp_path / "fixtures.json"
    fixtures.write_text(json.dumps(maths_fixture()), encoding="utf-8")
    rc, out, err = run(capsys, "check-report", str(report), "--fixtures", str(fixtures), "--adapter", "generic-structured", "--signing-key-hex", "00")
    assert rc == 2 and out == "" and "at least" in json.loads(err)["error"]
    key_file = tmp_path / "signing.key"
    key_file.write_text(KEY.hex(), encoding="ascii")
    rc, out, err = run(capsys, "check-report", str(report), "--fixtures", str(fixtures), "--adapter", "generic-structured", "--signing-key-file", str(key_file))
    assert rc == 0, err
    [outcome] = json.loads(out)
    assert verify_signature(VerificationResult.model_validate(outcome["verification"]), KEY)
