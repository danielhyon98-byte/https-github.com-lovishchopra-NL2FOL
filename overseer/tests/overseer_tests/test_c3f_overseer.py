"""Follow-up c3f, overseer items.

1. The replay worker never outlived its parent: a parent killed with SIGKILL runs no ``atexit`` and never sends the
   ``None`` that ends the worker's loop, and the worker holds its jobs queue's write end itself, so ``jobs.get()`` never
   saw end of file. The spawned worker, and the resource tracker whose pipe it keeps open, stayed alive and idle (16
   such processes had piled up from killed test runs). The worker now watches its parent's sentinel and exits.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import epinoic_logic.api as translator_api
import epinoic_overseer

_PROC = Path("/proc")
_linux = pytest.mark.skipif(not (_PROC / "self" / "stat").exists() or not hasattr(signal, "SIGKILL"),
                            reason="reads the process table from /proc and kills with SIGKILL (Linux)")

#: How long the orphaned worker and its resource tracker may take to exit once their parent is killed.
_EXIT_WITHIN_S = 10.0

_PARENT = textwrap.dedent("""
    import json, sys, time
    sys.path[:0] = {paths!r}
    from overseer_tests.conftest import CFG, int_problem, make_keyring
    from epinoic_logic.api.engine import verify
    from epinoic_logic.api.ir import canonical_json
    from epinoic_overseer import Replayer, ReplayJob

    if __name__ == "__main__":
        p = int_problem("c1", "x", 5, op="gt", bound=3)
        res = verify(p, CFG)
        job = ReplayJob(result_id="warm", problem_json=canonical_json(p), config_json=canonical_json(CFG.model_dump(mode="json")),
                        original_status="ENTAILED", problem_digest=res.binding.problem_digest, config_digest=res.binding.config_digest,
                        versions_digest=res.binding.versions_digest, always=True)
        rp = Replayer(make_keyring(), mode="process")
        rp.submit(job)
        rp.drain(timeout_s=90)  # the worker has run a job, so it is idle on its queue
        out = rp.outcomes()["warm"]
        print(json.dumps({{"worker": rp._proc.pid, "ok": bool(out.result_json)}}), flush=True)
        time.sleep(600)
""")


def _stat(pid: int) -> tuple[str, int] | None:
    """(state, parent pid) of a live process; None once it is gone."""
    try:
        raw = (_PROC / str(pid) / "stat").read_text()
    except OSError:
        return None
    fields = raw.rsplit(")", 1)[1].split()
    return fields[0], int(fields[1])


def _descendants(root: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for entry in _PROC.iterdir():
        if entry.name.isdigit():
            st = _stat(int(entry.name))
            if st is not None:
                children.setdefault(st[1], []).append(int(entry.name))
    found: set[int] = set()
    todo = [root]
    while todo:
        for kid in children.get(todo.pop(), ()):
            if kid not in found:
                found.add(kid)
                todo.append(kid)
    return found


def _running(pids: set[int]) -> set[int]:
    """The pids still running (a zombie has exited and only waits to be reaped)."""
    return {pid for pid in pids if (st := _stat(pid)) is not None and st[0] not in ("Z", "X")}


@_linux
@pytest.mark.timeout(150)
def test_the_replay_worker_and_its_resource_tracker_exit_when_their_parent_is_killed():
    paths = [str(Path(epinoic_overseer.__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1]),
             str(Path(translator_api.__file__).resolve().parents[2])]
    parent = subprocess.Popen([sys.executable, "-I", "-c", _PARENT.format(paths=paths)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    family: set[int] = set()
    try:
        line = parent.stdout.readline()
        assert line, f"the throwaway parent ended before its worker was ready (exit {parent.poll()})"
        info = json.loads(line)
        assert info["ok"], "the warm-up replay did not run"
        family = _descendants(parent.pid)
        assert info["worker"] in family and len(family) >= 2  # the spawned worker and the resource tracker
        assert _running(family) == family

        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=30)
        deadline = time.monotonic() + _EXIT_WITHIN_S
        while _running(family) and time.monotonic() < deadline:
            time.sleep(0.05)
        left = _running(family)
        assert not left, f"processes of the killed parent still running after {_EXIT_WITHIN_S} s: {sorted(left)}"
    finally:
        for pid in [parent.pid, *_running(family)]:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            parent.wait(timeout=10)
        except Exception:
            pass
        if parent.stdout is not None:
            parent.stdout.close()
