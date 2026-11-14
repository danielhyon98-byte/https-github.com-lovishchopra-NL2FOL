"""The flash router operated as a separate sub-agent: the command-line runner (``python -m epinoic_flash_router_cli``,
the ``epinoic-flash-router`` script) over the router port. A routing request on standard input, the plan on standard
output, the same text as the in-process API (``epinoic_flash_router.port``), deterministic; ``--data`` runs it over an
edited copy of its data; a bad data directory (2), a request the router does not read (3) and a fault of the router's
own code (4) are distinct named exit statuses, never a plan and never a traceback, so a fault of the router never reads
as bad input (round 9's push check of c4f276c: every exception was exit 2 or 3)."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from epinoic_flash_router import contract, port, rules
from epinoic_flash_router_cli.__main__ import main as runner_main

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


_MAX = contract.MAX_SAFE_INTEGER


@pytest.mark.parametrize("op,stdin,reason", [
    ("plan", "[" * _DEEP, "the request is nested too deep to decode"),                # the finding's case: a nested JSON array
    ("pool-plan", "[" * _DEEP, "the request is nested too deep to decode"),
    ("plan", '{"a":' * _DEEP, "the request is nested too deep to decode"),           # a nested JSON object
    ("pool-plan", json.dumps({**POOL_REQUEST, "limits": {**POOL_REQUEST["limits"], "per_instance_quota": 0}}),
     f"limits.per_instance_quota is an integer from 1 to {_MAX}"),                     # a zero quota (the planner divided by it)
    ("pool-plan", json.dumps({**POOL_REQUEST, "port_version": "1.2",
                              "items": [{**POOL_REQUEST["items"][0], "features": {"transfers": 1, "chars": 1, "stem": False, "translations": 0}}]})
     .replace('"chars": 1,', '"chars": Infinity,'), "the request holds Infinity, which is not JSON"),  # a number out of range
    ("plan", json.dumps(_REPEATED_KEY),
     "the routing request names one transfer key twice: every transfer is one output of the request"),  # port rule 1
])
def test_an_input_the_runner_cannot_read_is_exit_3_with_its_reason_never_a_traceback(op, stdin, reason, monkeypatch):
    """The documented statuses are 0, 2, 3 and 4, with the reason on standard error and never a traceback: a request
    nested too deep to decode (RecursionError, which the runner did not catch: exit 1 with a traceback), a zero quota, a
    number out of range and a transfer key named twice are exit 3, the input's.

    Rewritten to a stricter rule in round 9's second fix pass (push check of c4f276c: the runner read every exception as
    bad input, so a fault of its own code looked like one): the same six inputs, the same exit 3 with nothing on standard
    output and exactly one line on standard error, which must now name the router's own refusal (RequestError, with the
    member and the rule) instead of whatever the planner happened to raise on the input (RecursionError,
    ZeroDivisionError, OverflowError, ValueError); and in process the request is refused with that reason, a
    ValueError, before anything is planned (a planner reached here fails the test). A fault of the router's own code is
    exit 4 (the tests below)."""
    proc = _run(op, stdin=stdin)
    assert (proc.returncode, proc.stdout) == (3, ""), proc.stderr[-2000:]
    assert proc.stderr == f"epinoic-flash-router: the input is not a request this router reads (RequestError: {reason})\n", proc.stderr[-2000:]

    def planned(*args, **kwargs):
        raise AssertionError("planned a request the router does not read")
    from epinoic_flash_router import planner, pool
    monkeypatch.setattr(planner, "_readings", planned)
    monkeypatch.setattr(pool, "_escalated", planned)
    with pytest.raises(port.RequestError) as exc:
        (port.plan if op == "plan" else port.pool_plan)(stdin)
    assert str(exc.value) == reason and isinstance(exc.value, ValueError)


def _in_process(argv: list[str], stdin: str, monkeypatch, capsys) -> tuple[int, str, str]:
    """The runner's ``main`` in this process (its standard input ``stdin``): its status, standard output and error."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    status = runner_main(argv)
    out, err = capsys.readouterr()
    return status, out, err


_FAILED = "epinoic-flash-router: the router failed {doing} ({name}): a fault in the router's own code, not in the input or the data\n"
#: Exceptions a fault of the router's own code raises (ValueError among them: only RequestError is the input's).
_FAULTS = (AttributeError, KeyError, TypeError, ValueError, IndexError, ZeroDivisionError, OverflowError, RecursionError, AssertionError)


@pytest.mark.parametrize("fault", _FAULTS, ids=lambda f: f.__name__)
def test_a_fault_of_the_router_s_own_code_planning_a_request_it_reads_is_exit_4_never_3(fault, monkeypatch, capsys):
    """Round 9's push check of c4f276c: the runner mapped every exception to exit 2 or 3, so a planner bug looked like bad
    input. A request the router reads (it passed the checks) that the planner then fails on is exit 4, named by its
    exception type only, with nothing on standard output; the same request with the planner intact is planned (exit 0)."""
    def bug(*args, **kwargs):
        raise fault("a fault in the router's own code")
    for op, stdin, target in (("plan", json.dumps(_VECTOR), "plan_for"), ("pool-plan", json.dumps(POOL_REQUEST), "pool_plan_for")):
        status, out, _err = _in_process([op], stdin, monkeypatch, capsys)
        assert (status, json.loads(out)["origin"]) == (0, "router"), "the request is one the router reads"
        with monkeypatch.context() as m:
            m.setattr(port, target, bug)
            status, out, err = _in_process([op], stdin, m, capsys)
        assert (status, out) == (4, ""), err
        assert err == _FAILED.format(doing="planning a request it reads", name=fault.__name__)


@pytest.mark.parametrize("fault", [f for f in _FAULTS if not issubclass(f, (ValueError, RecursionError))], ids=lambda f: f.__name__)
def test_a_fault_of_the_router_s_own_code_loading_or_answering_is_exit_4_never_2(fault, monkeypatch, capsys):
    """The loader refuses bad data with ValueError (its own refusals and JSON's), a file it cannot read is an OSError and a
    file nested too deep a RecursionError: those are exit 2, the data's. Any other exception while the router is imported
    and loads its data, or while it writes a hello or its identity, is a fault of its own code: exit 4, never 2."""
    def bug(*args, **kwargs):
        raise fault("a fault in the router's own code")
    with monkeypatch.context() as m:
        m.setattr(port.FlashRouter, "__init__", bug)
        status, out, err = _in_process(["pool-plan"], json.dumps(POOL_REQUEST), m, capsys)
    assert (status, out, err) == (4, "", _FAILED.format(doing="loading its code or its data", name=fault.__name__))
    for op, method in (("hello", "hello"), ("pool-hello", "pool_hello")):
        with monkeypatch.context() as m:
            m.setattr(port.FlashRouter, method, bug)
            status, out, err = _in_process([op], "", m, capsys)
        assert (status, out, err) == (4, "", _FAILED.format(doing=f"writing its {op}", name=fault.__name__))


def test_a_planner_bug_in_a_copy_of_the_router_is_exit_4_with_no_traceback_and_its_input_checks_still_hold(tmp_path):
    """The same in a process of its own, with a real fault edited into a copy of the router's planner (a member read as an
    attribute): exit 4 and one named line on standard error, no traceback; the copy still refuses an input it does not
    read with exit 3 (the checks run before the planner) and still answers its hello."""
    src = tmp_path / "src"
    shutil.copytree(PROJECT / "src" / "epinoic_flash_router", src / "epinoic_flash_router", ignore=shutil.ignore_patterns("__pycache__"))
    planner_py = src / "epinoic_flash_router" / "planner.py"
    text = planner_py.read_text(encoding="utf-8")
    sound = 'profile = "standard" if "standard" in limits["profiles"] else limits["profiles"][0]'
    assert text.count(sound) == 1
    planner_py.write_text(text.replace(sound, "profile = limits.profile  # the fault: a JSON object has no attribute"), encoding="utf-8")
    env = {"PYTHONPATH": os.pathsep.join([str(src), str(PROJECT / "src")]), "PATH": os.environ.get("PATH", "")}

    def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "epinoic_flash_router_cli", *args], input=stdin, capture_output=True, text=True, env=env,
                              timeout=60, cwd=PROJECT)
    proc = run("plan", stdin=json.dumps(_VECTOR))
    assert (proc.returncode, proc.stdout) == (4, ""), proc.stderr[-2000:]
    assert proc.stderr == _FAILED.format(doing="planning a request it reads", name="AttributeError") and "Traceback" not in proc.stderr
    refused = run("plan", stdin=json.dumps({**_VECTOR, "limits": {**_VECTOR["limits"], "profiles": []}}))
    assert (refused.returncode, refused.stdout) == (3, "")
    assert refused.stderr == ("epinoic-flash-router: the input is not a request this router reads (RequestError: limits.profiles is a list "
                              "of at least one of standard, fast)\n")
    assert run("hello").returncode == 0 and run("pool-plan", stdin=json.dumps(POOL_REQUEST)).returncode == 0


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
