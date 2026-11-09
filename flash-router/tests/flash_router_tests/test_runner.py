"""The flash router operated as a separate sub-agent: the command-line runner (``python -m epinoic_flash_router_cli``,
the ``epinoic-flash-router`` script) over the router port. A routing request on standard input, the plan on standard
output, the same text as the in-process API (``epinoic_flash_router.port``), deterministic; ``--data`` runs it over an
edited copy of its data; a bad data directory and an unreadable request are named exit statuses, never a plan."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from epinoic_flash_router import port, rules

PROJECT = Path(__file__).resolve().parents[2]
POOL_REQUEST = {"schema": "epinoic.integration.pool-routing-request.v1", "protocol": "epinoic.integration.v1", "port_version": "1.1",
                "items": [{"item_id": f"d{i + 1}", "repeated_faults": 1 if i == 0 else 0, "risk_signals": [], "risk_records": [], "advised": False}
                          for i in range(10)],
                "limits": {"max_instances": 4, "per_instance_quota": 8, "profiles": ["standard"]}}


def _run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(PROJECT / "src"), "PATH": os.environ.get("PATH", "")}
    return subprocess.run([sys.executable, "-m", "epinoic_flash_router_cli", *args], input=stdin, capture_output=True, text=True, env=env,
                          timeout=60, cwd=PROJECT)


def test_the_runner_answers_exactly_what_the_in_process_api_answers():
    vector = json.loads((PROJECT / "tests" / "vectors" / "router-port" / "risky-duplicate.json").read_text(encoding="utf-8"))["request"]
    cases = [(("hello",), "", port.hello()), (("pool-hello",), "", port.pool_hello()),
             (("plan",), json.dumps(vector), port.plan(json.dumps(vector))),
             (("pool-plan",), json.dumps(POOL_REQUEST), port.pool_plan(json.dumps(POOL_REQUEST))),
             (("identity",), "", rules.canonical(port.IDENTITY))]
    for args, stdin, expected in cases:
        first, second = _run(*args, stdin=stdin), _run(*args, stdin=stdin)
        assert first.returncode == 0 and first.stderr == "", (args, first.stderr)
        assert first.stdout == second.stdout == expected, args


def test_the_runner_tries_an_edited_copy_of_the_data(tmp_path):
    dest = tmp_path / "data"
    shutil.copytree(rules.DATA_DIR, dest)
    path = dest / json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))["current"]["rules"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["pool"]["batch_size"] = 4
    path.write_text(json.dumps(doc), encoding="utf-8")
    released = json.loads(_run("pool-plan", stdin=json.dumps(POOL_REQUEST)).stdout)
    edited = json.loads(_run("pool-plan", "--data", str(dest), stdin=json.dumps(POOL_REQUEST)).stdout)
    assert (released["instances"], edited["instances"]) == (2, 3)
    assert edited["router"]["rules_sha256"] != released["router"]["rules_sha256"] == rules.RULES_SHA256
    assert json.loads(_run("identity", "--data", str(dest)).stdout)["rules_sha256"] == edited["router"]["rules_sha256"]


@pytest.mark.parametrize("args,stdin,status", [
    (("pool-plan", "--data", "/nonexistent/flash-router-data"), json.dumps(POOL_REQUEST), 2),
    (("pool-plan",), "not json", 3),
    (("pool-plan",), json.dumps({"items": "none"}), 3),
    (("plan",), json.dumps(POOL_REQUEST), 3),
])
def test_a_bad_data_directory_or_an_unreadable_request_is_a_named_exit_status_never_a_plan(args, stdin, status):
    proc = _run(*args, stdin=stdin)
    assert proc.returncode == status and proc.stdout == "" and proc.stderr.startswith("epinoic-flash-router:"), proc.stderr


_DEEP = 200_000  # far deeper than the interpreter's recursion limit: json raises RecursionError while decoding
_VECTOR = json.loads((PROJECT / "tests" / "vectors" / "router-port" / "risky-duplicate.json").read_text(encoding="utf-8"))["request"]
_REPEATED_KEY = {**_VECTOR, "outputs": _VECTOR["outputs"] * 2}  # one transfer key twice: out of the router port's contract


@pytest.mark.parametrize("op,stdin,named", [
    ("plan", "[" * _DEEP, "RecursionError"),                                         # the finding's case: a nested JSON array
    ("pool-plan", "[" * _DEEP, "RecursionError"),
    ("plan", '{"a":' * _DEEP, "RecursionError"),                                    # a nested JSON object
    ("pool-plan", json.dumps({**POOL_REQUEST, "limits": {**POOL_REQUEST["limits"], "per_instance_quota": 0}}), "ZeroDivisionError"),
    ("pool-plan", json.dumps({**POOL_REQUEST, "port_version": "1.2",
                              "items": [{**POOL_REQUEST["items"][0], "features": {"transfers": 1, "chars": 1, "stem": False, "translations": 0}}]})
     .replace('"chars": 1,', '"chars": Infinity,'), "OverflowError"),           # a number out of range (JSON's Infinity)
    ("plan", json.dumps(_REPEATED_KEY), "ValueError"),                               # one transfer key twice (port rule 1)
])
def test_an_input_the_runner_cannot_read_is_exit_3_with_its_reason_never_a_traceback(op, stdin, named):
    """The documented statuses are 0, 2 and 3, with the reason on standard error and never a traceback: a request nested
    too deep to decode (RecursionError, which the runner did not catch: exit 1 with a traceback), and every other exception
    a request makes the pure planner raise, is exit 3 naming its type."""
    proc = _run(op, stdin=stdin)
    assert (proc.returncode, proc.stdout) == (3, ""), proc.stderr[-2000:]
    assert proc.stderr == f"epinoic-flash-router: the input is not a request this router reads ({named})\n", proc.stderr[-2000:]


def test_a_data_directory_nested_too_deep_to_decode_is_exit_2_never_a_traceback(tmp_path):
    dest = tmp_path / "data"
    shutil.copytree(rules.DATA_DIR, dest)
    (dest / "MANIFEST.json").write_text("[" * _DEEP, encoding="utf-8")
    for args, stdin in ((("hello", "--data", str(dest)), ""), (("pool-plan", "--data", str(dest)), json.dumps(POOL_REQUEST))):
        proc = _run(*args, stdin=stdin)
        assert (proc.returncode, proc.stdout) == (2, ""), proc.stderr[-2000:]
        assert proc.stderr == "epinoic-flash-router: the data cannot be loaded (RecursionError)\n", proc.stderr[-2000:]


def test_the_runner_package_imports_nothing_but_argparse_sys_typing_and_the_router():
    allowed = {"__future__", "argparse", "sys", "typing", "epinoic_flash_router"}
    for p in sorted((PROJECT / "src" / "epinoic_flash_router_cli").glob("*.py")):
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*|\.)", line)
            if m and m.group(1) != ".":
                assert m.group(1) in allowed, (p.name, line)
