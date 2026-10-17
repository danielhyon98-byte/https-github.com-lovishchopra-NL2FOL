"""What keeps the service's keys out of the flash router's reach (PROTOCOL.md section 7a, "A fault boundary, not a
sandbox"; router-port/CONFORMANCE.md).

The router's process holds no EPINOIC_ variable of its own, but it runs as the service's user, and on Linux a process of
the same user can read another one's start environment through /proc/<pid>/environ (verification finding V2-M1: an
edited router read EPINOIC_VERDICT_KEY there). So before it starts any router process the service marks itself
non-dumpable; when Linux refuses, it starts none (KIT-RT-016). The mark does not help against a router running as root
or with CAP_SYS_PTRACE, so the hosted profile attaches a router only where neither holds; the loopback simulation and
check.py --router, which hold ephemeral test keys at most, attach it anyway.

The end-to-end test runs a stand-in service as an unprivileged user (this test's own user, or uid 65534 when the test runs
as root) with synthetic EPINOIC_ variables in its start environment, through the kit's own launcher and runner, and a
router that tries to read them: without the mark it can (the control), with it it cannot.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from epinoic_logic.integration import router_child as C
from epinoic_logic.integration import router_port as R
from epinoic_logic.integration.preflight import run_preflight
from tests.integration.helpers import FixtureProbes, routing_request, settings, write_router_module

SRC = str(Path(__file__).resolve().parents[2] / "src")
LINUX = sys.platform.startswith("linux")
linux_only = pytest.mark.skipif(not LINUX, reason="the non-dumpable mark is Linux's; elsewhere the service makes no secret claim (PROTOCOL.md 7a)")

PROBE_ROUTER = '''import json, os


def _names(data):
    return sorted({x.split(b"=", 1)[0].decode() for x in data.split(b"\\0") if x.startswith(b"EPINOIC_")})


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as exc:
        return "denied:" + type(exc).__name__


def hello():
    environ = _read("/proc/%d/environ" % os.getppid())
    try:  # opening the memory file is the access check itself (PTRACE_MODE_ATTACH)
        open("/proc/%d/mem" % os.getppid(), "rb").close()
        mem = "opened"
    except OSError as exc:
        mem = "denied:" + type(exc).__name__
    return json.dumps({"own": sorted(k for k in os.environ if k.startswith("EPINOIC_")),
                       "parent": _names(environ) if isinstance(environ, bytes) else environ, "mem": mem})


def plan(request_json):
    return "{}"
'''

PROBE_SERVICE = '''import importlib.util, sys
probe_dir, mode = sys.argv[1], sys.argv[2]
sys.path.insert(0, probe_dir)  # the router's module, on the path the router's process receives
spec = importlib.util.spec_from_file_location("kit_router_child_copy", probe_dir + "/router_child.py")
child = importlib.util.module_from_spec(spec)
spec.loader.exec_module(child)
if mode == "unmarked":
    child.protect_service = lambda: False  # the control: what a router reads when the service is not marked
sys.stdout.write(child.launch("probe_environ_router", "hello", None, 30.0))
'''

SECRETS = {"EPINOIC_SIGNING_KEY": "SYNTHETIC-not-a-secret-engine-key", "EPINOIC_VERDICT_KEY": "SYNTHETIC-not-a-secret-verdict-key",
           "EPINOIC_SERVICE_TOKEN": "SYNTHETIC-not-a-secret-token"}


def _dumpable_in_a_fresh_service(tmp_path: Path, name: str) -> list:
    code = ("import ctypes, json\n"
            "from epinoic_logic.integration import router_port as R\n"
            "prctl = ctypes.CDLL(None).prctl\n"
            "before = prctl(3, 0, 0, 0, 0)\n"
            f"att = R.attach_router({name!r})\n"
            "print(json.dumps([before, att.attached, prctl(3, 0, 0, 0, 0)]))\n")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), SRC])}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@linux_only
def test_the_service_marks_itself_non_dumpable_before_it_starts_a_router_process(tmp_path, monkeypatch):
    name = write_router_module(tmp_path, monkeypatch, "dumpable_probe_router")
    assert _dumpable_in_a_fresh_service(tmp_path, name) == [1, True, 0]


@linux_only
def test_when_linux_does_not_mark_the_service_no_router_process_starts(tmp_path, monkeypatch):
    marker = tmp_path / "started.txt"
    name = write_router_module(tmp_path, monkeypatch, "unmarked_service_router",
                               hello_body=f"    open({str(marker)!r}, 'w').write('started')\n    return json.dumps(HELLO)\n")
    monkeypatch.setattr(C, "_prctl", lambda option, arg=0: -1)
    att = R.attach_router(name)
    assert (att.attached, att.refusal) == (False, "KIT-RT-016") and "non-dumpable" in att.detail, att
    assert not marker.exists(), "the router's process never started"
    # an attached router is asked for a plan only once the service is marked again: the floor runs otherwise
    monkeypatch.setattr(C, "_prctl", lambda option, arg=0: 0)
    att = R.attach_router(name)
    assert att.attached
    monkeypatch.setattr(C, "_prctl", lambda option, arg=0: -1)
    req = R.check_request(routing_request())
    adm = R.route(req, att)
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-016") and adm.effective == R.floor_plan(req)


def _unprivileged_run() -> dict:
    """Popen arguments that run a process as an unprivileged user: none when this test already runs as one, else uid and
    gid 65534 (root only). Skips when that user cannot even start this interpreter here."""
    if os.geteuid() != 0:
        return {}
    kw = {"user": 65534, "group": 65534, "extra_groups": []}
    exe = os.path.realpath(sys.executable)
    probe = subprocess.run([exe, "-I", "-c", "print('ok')"], capture_output=True, text=True, timeout=60, cwd="/", env={"PATH": os.environ.get("PATH", "")}, **kw)
    if probe.stdout.strip() != "ok":
        pytest.skip("an unprivileged user cannot start this interpreter here, so the same-user case cannot be run")
    return kw


@linux_only
def test_a_router_of_the_services_own_unprivileged_user_cannot_read_the_services_start_environment():
    kw = _unprivileged_run()
    probe_dir = tempfile.mkdtemp(prefix="kit-router-secret-boundary-", dir="/tmp")
    try:
        os.chmod(probe_dir, 0o755)
        for name, text in (("probe_environ_router.py", PROBE_ROUTER), ("probe_service.py", PROBE_SERVICE)):
            Path(probe_dir, name).write_text(text, encoding="utf-8")
        shutil.copyfile(C.__file__, Path(probe_dir, "router_child.py"))
        for p in Path(probe_dir).iterdir():
            os.chmod(p, 0o644)
        seen = {}
        for mode in ("unmarked", "marked"):
            out = subprocess.run([os.path.realpath(sys.executable), "-I", str(Path(probe_dir, "probe_service.py")), probe_dir, mode],
                                 capture_output=True, text=True, timeout=120, cwd=probe_dir,
                                 env={"PATH": os.environ.get("PATH", ""), **SECRETS}, **kw)
            assert out.returncode == 0, out.stderr
            seen[mode] = json.loads(out.stdout)
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    # the control: an unmarked service's start environment is readable by a router of its user (the path of V2-M1)
    assert seen["unmarked"]["own"] == [] and set(SECRETS) <= set(seen["unmarked"]["parent"]), seen
    assert seen["unmarked"]["mem"] == "opened", seen
    # the service the kit runs: nothing of it is readable, and the router's own environment holds no EPINOIC_ variable
    assert seen["marked"] == {"own": [], "parent": "denied:PermissionError", "mem": "denied:PermissionError"}, seen


def test_the_hosted_profile_attaches_a_router_only_where_its_process_cannot_read_the_keys(tmp_path, monkeypatch):
    name = write_router_module(tmp_path, monkeypatch, "hosted_profile_router")
    hosted = settings(PROFILE="integration", SERVICE_ENV="development", FLASH_ROUTER=name)
    monkeypatch.setattr(C, "boundary_problem", lambda: "the service runs as root, so its router would run as root too")
    facts = run_preflight(hosted, FixtureProbes())
    assert (facts.router_caps.attached, facts.router_caps.refusal, facts.router_caps.identity) == (False, "KIT-RT-016", None)
    assert "runs as root" in facts.router.detail and "floor plan runs" in facts.router.detail
    monkeypatch.setattr(C, "boundary_problem", lambda: None)
    facts = run_preflight(hosted, FixtureProbes())
    assert facts.router_caps.attached is True and facts.router_caps.refusal is None
    # the loopback simulation (ephemeral test keys) attaches it whatever the boundary, as check.py --router does
    monkeypatch.setattr(C, "boundary_problem", lambda: "the service holds CAP_SYS_PTRACE, so its router could read it")
    assert run_preflight(settings(FLASH_ROUTER=name), FixtureProbes()).router_caps.attached is True
    assert R.attach_router(name).attached and not R.attach_router(name, require_secret_boundary=True).attached


def test_the_boundary_holds_only_on_linux_for_a_service_that_is_neither_root_nor_holds_cap_sys_ptrace(monkeypatch):
    monkeypatch.setattr(C.sys, "platform", "linux")
    monkeypatch.setattr(C.os, "geteuid", lambda: 0)
    monkeypatch.setattr(C.os, "getuid", lambda: 0)
    assert "root" in C.boundary_problem()
    monkeypatch.setattr(C.os, "geteuid", lambda: 10001)
    monkeypatch.setattr(C.os, "getuid", lambda: 10001)
    monkeypatch.setattr(C, "_capabilities", lambda: {"CapPrm": 0, "CapEff": 0, "CapAmb": 0})
    assert C.boundary_problem() is None
    for name in ("CapPrm", "CapEff", "CapAmb"):
        monkeypatch.setattr(C, "_capabilities", lambda name=name: {"CapPrm": 0, "CapEff": 0, "CapAmb": 0, name: 1 << 19})
        assert "CAP_SYS_PTRACE" in C.boundary_problem(), name
    monkeypatch.setattr(C, "_capabilities", lambda: {"CapPrm": 0, "CapEff": (1 << 19) - 1, "CapAmb": 1 << 20})
    assert C.boundary_problem() is None, "only CAP_SYS_PTRACE matters"
    monkeypatch.setattr(C, "_capabilities", lambda: None)
    assert "cannot be read" in C.boundary_problem()
    monkeypatch.setattr(C.sys, "platform", "darwin")
    assert "only Linux" in C.boundary_problem()
    assert C.protect_service() is False, "nothing is marked on a system without prctl"


@linux_only
def test_the_capabilities_of_this_process_are_read_from_proc():
    caps = C._capabilities()
    assert caps is not None and set(caps) == {"CapPrm", "CapEff", "CapAmb"} and all(isinstance(v, int) for v in caps.values())
