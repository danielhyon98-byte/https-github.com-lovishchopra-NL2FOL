"""The flash router's own process (``integration/PROTOCOL.md`` section 7a, "Attachment").

The service never runs the flash router's code in its own process. For each call (the hello at start-up, one plan per
review) it starts ``python -I router_child.py`` from this file's path with an environment that holds no ``EPINOIC_``
variable (so no key, secret or token), writes one job to its standard input and reads the router's answer from its
standard output, within a time limit (``router_port.run_router``). Whatever the router's code does here (raise, exit,
hang, print, patch modules, read the environment) stays in this process: the service sees an answer text or an exit
status, and validates the text as untrusted data.

The job is one JSON object: ``paths`` (the service's import path, so the child imports exactly what the service would),
``module`` (``EPINOIC_FLASH_ROUTER``), ``op`` (``hello`` or ``plan``) and, for a plan, ``request`` (the routing request's
canonical JSON text). The answer is the text the router's function returned, written only by this runner: anything the
router itself writes to standard output goes to standard error, which the service discards.

Standard library only, and nothing from the translator is imported here, so the router's process holds exactly the
router and what the router itself imports. The exit statuses are the ``EXIT_*`` constants below; ``router_port`` maps
each one to a ``KIT-RT`` code (``EXIT_NO_FUNCTION`` to ``KIT-RT-015``, every other failure to ``KIT-RT-016``).
"""
from __future__ import annotations

import importlib
import json
import os
import sys

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
