"""The flash router's own process (``integration/PROTOCOL.md`` section 7a, "Attachment"): the runner the service starts
for every call (:func:`main`), and the service's side of that process boundary (:func:`launch`, which
``router_port.run_router`` calls).

The service never runs the flash router's code in its own process. For each call (the hello at start-up, one plan per
review) :func:`launch` starts ``python -I router_child.py`` from this file's path with an environment that holds only the
variables of :data:`CHILD_ENV_NAMES` (no ``EPINOIC_`` variable, so no key, secret or token is in the router's own
environment), writes one job to its standard input and reads the router's answer from its standard output, within a
time limit. Whatever the router's code raises, however it exits, whatever it prints and whichever kit module it patches
stays in its process: the service sees an answer text or an exit status, and validates the text as untrusted data.

**A fault boundary, not a sandbox.** The router's process runs as the service's user, so it can do what that user can
do: read the files that user can read, signal that user's processes, use the network. What keeps the service's keys out
of its reach is :func:`protect_service`: before it starts any router process, the service marks itself non-dumpable on
Linux (``prctl(PR_SET_DUMPABLE, 0)``), so a router that runs without root and without ``CAP_SYS_PTRACE`` can read neither
the service's environment nor its memory (``/proc/<pid>/environ``, ``/proc/<pid>/mem``, ``ptrace``). When Linux refuses,
no router process is started (``KIT-RT-016``). That protection does not hold for a service that runs as root or with
``CAP_SYS_PTRACE`` (its router gets the same power), on another system, or for secrets kept in files or in other
processes of the same user (:func:`boundary_problem`). So the hosted profile attaches a router only where it holds
(``router_port.attach_router(..., require_secret_boundary=True)``), and a router is installed only as code trusted with
the service's user (decision D28).

The job is one JSON object: ``paths`` (the service's import path, so the child imports exactly what the service would),
``module`` (``EPINOIC_FLASH_ROUTER``), ``op`` (``hello`` or ``plan``) and, for a plan, ``request`` (the routing request's
canonical JSON text). The answer is the text the router's function returned, written only by this runner: anything the
router itself writes to standard output goes to standard error, which the service discards.

Standard library only, and nothing from the translator is imported here (the service side imports what it needs inside
its functions), so this file runs on its own and the router's process holds exactly the runner, the router and what the
router itself imports. The exit statuses are the ``EXIT_*`` constants below; :func:`launch` maps each one to a ``KIT-RT``
code (``EXIT_NO_FUNCTION`` to ``KIT-RT-015``, every other failure to ``KIT-RT-016``).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from typing import Optional

EXIT_OK = 0
#: The job could not be read (a defect of the service side, never of the router).
EXIT_JOB = 2
#: The router module cannot be imported.
EXIT_IMPORT = 3
#: The router module exposes no callable ``hello`` or ``plan``.
EXIT_NO_FUNCTION = 4
#: ``hello()`` or ``plan()`` raised (any exception: ``SystemExit`` and ``KeyboardInterrupt`` included).
EXIT_RAISED = 5
#: The router returned something other than a ``str`` of UTF-8 text.
EXIT_NOT_TEXT = 6
#: The router's answer is larger than the service reads.
EXIT_TOO_LARGE = 7

MAX_JOB_BYTES = 4 * 1024 * 1024
MAX_ANSWER_BYTES = 1024 * 1024
#: The only environment variables the router's process gets (names, never values; no ``EPINOIC_`` variable is among them).
CHILD_ENV_NAMES: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT")

_PR_GET_DUMPABLE = 3
_PR_SET_DUMPABLE = 4
#: The capability that lets a process read a non-dumpable process of its own user (``/proc/<pid>/environ``, ``ptrace``).
_CAP_SYS_PTRACE = 19


class RouterFailure(Exception):
    """A router call that produced no answer to validate: the router could not be started, raised, exited, did not
    answer in time, or answered too much. ``code`` is ``KIT-RT-016`` (``KIT-RT-015`` for a module without the two
    functions); ``detail`` never carries anything the router wrote."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


_FAILURES = {
    EXIT_JOB: ("KIT-RT-016", "the router's process could not read its job"),
    EXIT_IMPORT: ("KIT-RT-016", "the router module is not importable in its process"),
    EXIT_NO_FUNCTION: ("KIT-RT-015", "the router module exposes no hello() and plan(request_json)"),
    EXIT_RAISED: ("KIT-RT-016", "the router raised"),
    EXIT_NOT_TEXT: ("KIT-RT-016", "the router answered with something other than text"),
    EXIT_TOO_LARGE: ("KIT-RT-016", f"the router's answer is larger than {MAX_ANSWER_BYTES} bytes"),
}


# --------------------------------------------------------------------------------------------- the service's side


def _prctl(option: int, arg: int = 0) -> int:
    """``prctl(option, arg, 0, 0, 0)`` of the calling process (Linux)."""
    import ctypes

    fn = ctypes.CDLL(None, use_errno=True).prctl
    fn.restype = ctypes.c_int
    fn.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
    return int(fn(option, arg, 0, 0, 0))


def protect_service() -> bool:
    """Mark the calling (service) process non-dumpable before a router process starts, so that a router running as the
    service's user, without root and without ``CAP_SYS_PTRACE``, cannot read the service's environment or memory.

    Returns ``True`` once the process is marked (Linux; the call is repeated before every router process and is
    idempotent) and ``False`` on a system without ``prctl``, where nothing is marked. Raises :class:`RouterFailure`
    ``KIT-RT-016`` when Linux does not mark it: then no router process is started."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        marked = _prctl(_PR_SET_DUMPABLE, 0) == 0 and _prctl(_PR_GET_DUMPABLE) == 0
    except (OSError, AttributeError, ImportError, TypeError, ValueError):  # no ctypes, no prctl symbol
        marked = False
    if not marked:
        raise RouterFailure("KIT-RT-016", "the service could not mark itself non-dumpable, so no router process is started")
    return True


def _capabilities() -> Optional[dict[str, int]]:
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    caps = {}
    for line in lines:
        name, _, value = line.partition(":")
        if name in ("CapPrm", "CapEff", "CapAmb"):
            try:
                caps[name] = int(value.strip(), 16)
            except ValueError:
                return None
    return caps if len(caps) == 3 else None


def boundary_problem() -> Optional[str]:
    """Why a router process started by this service could read the service's environment or memory even once the service
    is marked non-dumpable, or ``None`` when it could not: Linux, a service that is not root, and no ``CAP_SYS_PTRACE`` in
    its permitted, effective or ambient capabilities. (Files and other processes of the same user are outside what this
    reads: keep the secrets in the service's own environment only.)"""
    if not sys.platform.startswith("linux"):
        return "only Linux hides a non-dumpable service's environment from a process of the same user"
    if os.geteuid() == 0 or os.getuid() == 0:
        return "the service runs as root, so its router would run as root too"
    caps = _capabilities()
    if caps is None:
        return "the service's capabilities cannot be read"
    if any((value >> _CAP_SYS_PTRACE) & 1 for value in caps.values()):
        return "the service holds CAP_SYS_PTRACE, so its router could read it"
    return None


def child_env() -> dict[str, str]:
    """The router's whole environment: the variables of :data:`CHILD_ENV_NAMES` that the service has, nothing else."""
    return {name: os.environ[name] for name in CHILD_ENV_NAMES if name in os.environ}


def _cwd() -> str:
    try:
        return os.getcwd()
    except OSError:  # the service's working directory is gone: run the router from this file's directory
        return os.path.dirname(os.path.abspath(__file__))


def import_paths() -> list[str]:
    """The service's own import path, so the router's process imports exactly the modules the service would."""
    return [_cwd() if p == "" else p for p in sys.path if isinstance(p, str)]


def _kill(proc) -> None:  # noqa: ANN001 - a subprocess.Popen
    import signal
    import subprocess

    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)  # the router's own children go with it (it runs in its own session)
        else:  # pragma: no cover - the service runs on POSIX
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - a process killed with SIGKILL is reaped at once
        pass


def launch(module: str, op: str, request_json: Optional[str], timeout_s: float) -> str:
    """One call of the flash router (``op`` ``hello`` or ``plan``) in its own process, waiting at most ``timeout_s``.

    Returns the text the router's function returned. Raises :class:`RouterFailure` for everything else: the service
    could not mark itself non-dumpable (:func:`protect_service`), the process could not start, the module cannot be
    imported or lacks the function, the function raised (``SystemExit`` and ``KeyboardInterrupt`` included) or returned
    a non-text value, the answer is not UTF-8 or larger than :data:`MAX_ANSWER_BYTES`, or no answer came within
    ``timeout_s`` (the process and its children are then killed). The process gets ``python -I`` (no user site, no
    ``PYTHON*`` variable, no current directory on its path), the service's import path, and only the variables of
    :data:`CHILD_ENV_NAMES`: no ``EPINOIC_`` variable reaches it."""
    import subprocess
    import threading
    import time

    protect_service()
    job = json.dumps({"paths": import_paths(), "module": module, "op": op, "request": request_json}).encode("utf-8")
    deadline = time.monotonic() + max(0.0, timeout_s)
    try:
        proc = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=child_env(), cwd=_cwd(), close_fds=True,
                                start_new_session=os.name == "posix")
    except OSError as exc:
        raise RouterFailure("KIT-RT-016", f"the router's process could not be started ({type(exc).__name__})") from None
    out = bytearray()
    state = {"too_large": False}

    def feed() -> None:
        try:
            proc.stdin.write(job)  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass

    def drain() -> None:
        try:
            while True:
                chunk = proc.stdout.read1(65536)  # type: ignore[union-attr]
                if not chunk:
                    return
                if len(out) + len(chunk) > MAX_ANSWER_BYTES:
                    state["too_large"] = True
                    return
                out.extend(chunk)
        except (OSError, ValueError):
            return

    writer = threading.Thread(target=feed, name="flash-router-feed", daemon=True)
    reader = threading.Thread(target=drain, name="flash-router-drain", daemon=True)
    writer.start()
    reader.start()
    reader.join(max(0.0, deadline - time.monotonic()))
    status: Optional[int] = None
    if not reader.is_alive() and not state["too_large"]:
        try:
            status = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            status = None
    if status is None:
        _kill(proc)
    reader.join(1.0)
    writer.join(1.0)
    for stream in (proc.stdout, proc.stdin):
        try:
            if stream is not None:
                stream.close()
        except OSError:  # pragma: no cover
            pass
    if state["too_large"]:
        raise RouterFailure("KIT-RT-016", f"the router's answer is larger than {MAX_ANSWER_BYTES} bytes")
    if status is None:
        raise RouterFailure("KIT-RT-016", f"the router did not answer within {int(max(0.0, timeout_s) * 1000)} ms")
    if status != EXIT_OK:
        code, detail = _FAILURES.get(status, ("KIT-RT-016", f"the router's process exited with status {status}"))
        raise RouterFailure(code, f"{detail} ({op})")
    try:
        return bytes(out).decode("utf-8")
    except UnicodeDecodeError:
        raise RouterFailure("KIT-RT-016", "the router's answer is not UTF-8 text") from None


# --------------------------------------------------------------------------------------------- the router's process


def _exit(status: int) -> None:
    os._exit(status)  # no atexit handler of the router runs, and nothing it buffered is flushed into the answer


def main() -> None:
    try:
        answer_fd = os.dup(1)
        os.dup2(2, 1)  # whatever the router prints goes to standard error, never into the answer
    except OSError:
        _exit(EXIT_JOB)
    try:
        raw = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
        if len(raw) > MAX_JOB_BYTES:
            _exit(EXIT_JOB)
        job = json.loads(raw.decode("utf-8"))
        paths, module_name, op, request = job["paths"], job["module"], job["op"], job.get("request")
        if (not isinstance(paths, list) or not all(isinstance(p, str) for p in paths) or not isinstance(module_name, str)
                or op not in ("hello", "plan") or (op == "plan" and not isinstance(request, str))):
            _exit(EXIT_JOB)
    except BaseException:  # noqa: BLE001 - a malformed job is the service's defect: one exit status, no traceback
        _exit(EXIT_JOB)
    sys.path[:] = paths
    try:
        module = importlib.import_module(module_name)
    except BaseException:  # noqa: BLE001 - SystemExit or KeyboardInterrupt at import time included
        _exit(EXIT_IMPORT)
    try:  # a router exposes both functions, whichever one this call needs
        fn = getattr(module, op, None)
        usable = callable(getattr(module, "hello", None)) and callable(getattr(module, "plan", None))
    except BaseException:  # noqa: BLE001
        usable = False
    if not usable:
        _exit(EXIT_NO_FUNCTION)
    try:
        answer = fn() if op == "hello" else fn(request)  # type: ignore[misc]
    except BaseException:  # noqa: BLE001 - whatever the router raises, the service only sees this status
        _exit(EXIT_RAISED)
    if not isinstance(answer, str):
        _exit(EXIT_NOT_TEXT)
    try:
        data = answer.encode("utf-8")
    except UnicodeEncodeError:
        _exit(EXIT_NOT_TEXT)
    if len(data) > MAX_ANSWER_BYTES:
        _exit(EXIT_TOO_LARGE)
    view = memoryview(data)
    try:
        while view:
            view = view[os.write(answer_fd, view):]
    except OSError:
        _exit(EXIT_JOB)
    _exit(EXIT_OK)


if __name__ == "__main__":
    main()
