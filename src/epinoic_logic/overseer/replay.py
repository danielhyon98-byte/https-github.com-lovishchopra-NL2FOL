"""R1 replay: every stored engine result re-verified on a fresh engine, and the auditor's other deferred work.

* **Isolation.** The default mode is ``process``: a ``spawn`` worker process re-runs each stored problem under the
  channel's journaled ``solver_config`` (a local engine run; an external engine's result under its own), isolated from the process-wide Z3 memory parameter and from any patching of the hub
  process. ``inline`` runs in this process and exists for tests; only a ``process`` replay is accepted as independent
  by a FINAL audit, and the audit's coverage records which mode ran (``replay_mode``).
* **Keys.** The worker never holds a key: it returns the unsigned result, and the parent signs it under the auditor's
  run key (``overseer-run``) before storing it with origin ``replay``.
* **Limits.** A joint problem (problem id ``joint-*``) is replayed under ``JOINT_LIMITS``, every other problem under
  ``DEFAULT_LIMITS``, as the channel ran them; a replay that hits a shape limit is retried under ``JOINT_LIMITS``.
* **Bounds and sampling.** At most ``queue_bound`` jobs are outstanding. Beyond it, replay degrades to keyed
  deterministic sampling at ``sample_rate`` (at least 0.25): a job is kept when ``HMAC(sampling key, result_id)`` read
  as a fraction is below the rate; agents cannot predict it and the auditor can reproduce it. ``always`` jobs (results
  behind a definitive display status, results cited by error findings, results feeding a synthesis) are never sampled
  out. Sampled-out jobs are kept and replayed by the batch tier (:meth:`Replayer.drain` with ``include_sampled``).
* **Deferred work.** ``submit_task`` queues a deterministic callable (R2 re-derivation) that runs in a background
  thread in ``process`` mode and at drain time (or at once, with ``eager``) in ``inline`` mode.

What is compared is decided by :func:`compare`: ``status``, and the binding's ``problem_digest`` and
``config_digest``. Unsat cores, counterexample models and witnesses are not unique and are not compared.
:func:`classify` turns a definitive signed status the replay cannot reproduce (undecided, budget exceeded, versions
changed, no result) into ``OVS-AUDIT-005`` (cannot pass), never into the ``OVS-RES-008`` warning.
"""
from __future__ import annotations

import json
import multiprocessing
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from ..engine.provenance import sign_result
from ..engine.results import VerificationResult
from ..engine.statuses import VerificationStatus as S, is_definitive
from ..ir.canonical import canonical_json
from .checks import Replay
from .faithful import faithful
from .keys import RUN_KEY_ID, KeyRing

__all__ = ["ReplayJob", "ReplayOutcome", "Replayer", "compare", "classify", "replay_problem", "build_replay_job", "QUEUE_BOUND", "MIN_SAMPLE_RATE"]

QUEUE_BOUND = 256
MIN_SAMPLE_RATE = 0.25
_UNDECIDED = (S.TIMEOUT.value, S.UNKNOWN.value, S.INTERNAL_ERROR.value)
_LIMIT_CODES = ("E300", "E301", "E302", "E303", "E304", "E305", "E306")


@dataclass(frozen=True)
class ReplayJob:
    result_id: str
    problem_json: str
    config_json: str
    original_status: str
    problem_digest: str
    config_digest: str
    versions_digest: str
    always: bool = False
    seq: int = 0
    channel_uid: str = ""


@dataclass
class ReplayOutcome:
    job: ReplayJob
    result_json: Optional[str] = None  # the replay, signed under the auditor's run key
    error: Optional[str] = None
    budget_exceeded: bool = False
    finished_at: float = field(default_factory=time.monotonic)


def build_replay_job(view: Any, store: Any, rid: str, *, always: bool, seq: int, channel_uid: str) -> Optional[ReplayJob]:
    """The replay job of engine result ``rid`` of this channel, or None when no content or no problem is held for it.

    Content comes from :func:`~epinoic_logic.overseer.checks.results.replay_source` (the live store record, else the
    journaled capture, so an eviction inside the result's own event never drops its replay). A local engine run is
    replayed under the channel's JOURNALED configuration (``replay_config``), never under a budget the result itself
    names; the comparison keeps the result's own config digest, so a result signed under another configuration
    replays with another config digest (RES-007)."""
    from .checks.results import replay_config, replay_source
    src = replay_source(view, store, rid)
    if src is None:
        return None
    result_json, problem_json, ev_seq, origin = src
    if not problem_json:
        return None
    try:
        res = faithful(VerificationResult, json.loads(result_json))
    except Exception:
        return None
    cfg = replay_config(view, res, ev_seq or seq, origin)
    return ReplayJob(result_id=rid, problem_json=problem_json, config_json=canonical_json(cfg.model_dump(mode="json")), original_status=res.status.value,
                     problem_digest=res.binding.problem_digest, config_digest=res.binding.config_digest, versions_digest=res.binding.versions_digest,
                     always=always, seq=seq, channel_uid=channel_uid)


def replay_problem(problem_json: str, config_json: str) -> str:
    """Re-verify one stored problem on this process's engine, unsigned; returns the result JSON. Runs in the worker."""
    from ..engine.results import SolverConfig
    from ..engine.runner import verify
    from ..integrity.cross_check import JOINT_LIMITS
    from ..ir.schema import DEFAULT_LIMITS, Problem
    problem = faithful(Problem, json.loads(problem_json))
    cfg = faithful(SolverConfig, json.loads(config_json))
    limits = JOINT_LIMITS if problem.problem_id.startswith("joint-") else DEFAULT_LIMITS
    res = verify(problem, cfg, limits)
    if limits is DEFAULT_LIMITS and any(d.code in _LIMIT_CODES for d in res.diagnostics):
        res = verify(problem, cfg, JOINT_LIMITS)
    return canonical_json(res.model_dump(mode="json", exclude_none=True))


def _worker_main(jobs: Any, results: Any) -> None:  # pragma: no cover - runs in the spawned process
    while True:
        item = jobs.get()
        if item is None:
            return
        jid, problem_json, config_json = item
        try:
            results.put((jid, replay_problem(problem_json, config_json), None))
        except Exception as exc:
            results.put((jid, None, f"{type(exc).__name__}"))


def compare(job: ReplayJob, replayed: Optional[VerificationResult], *, budget_exceeded: bool = False, error: Optional[str] = None) -> Replay:
    if replayed is None:
        return Replay(result_id=job.result_id, replay_result_id=None, original_status=job.original_status, replay_status=None, problem_digest_ok=True,
                      config_digest_ok=True, versions_changed=False, budget_exceeded=budget_exceeded or error is None, error=error)
    b = replayed.binding
    return Replay(result_id=job.result_id, replay_result_id=replayed.result_id, original_status=job.original_status, replay_status=replayed.status.value,
                  problem_digest_ok=b.problem_digest == job.problem_digest, config_digest_ok=b.config_digest == job.config_digest,
                  versions_changed=b.versions_digest != job.versions_digest, budget_exceeded=budget_exceeded, error=error)


def classify(r: Replay) -> Optional[str]:
    """``OVS-RES-007``, ``OVS-AUDIT-005``, ``OVS-RES-008`` or None (the replay agrees).

    A DEFINITIVE signed status that the replay cannot reproduce (no replay result, budget exceeded, an error, component
    versions changed, or an undecided replay) is ``OVS-AUDIT-005``: it was never re-verified, so it cannot pass (a
    re-signed status with a tiny budget or other versions must not clear as merely inconclusive). ``OVS-RES-008`` (a
    warning) is kept for an original that was itself undecided."""
    definitive = r.original_status not in _UNDECIDED
    if r.replay_status is None or r.budget_exceeded or r.error:
        return "OVS-AUDIT-005" if definitive else "OVS-RES-008"
    if r.versions_changed:
        if r.replay_status == r.original_status and r.problem_digest_ok and r.config_digest_ok:
            return None
        return "OVS-AUDIT-005" if definitive else "OVS-RES-008"
    if not r.problem_digest_ok or not r.config_digest_ok:
        return "OVS-RES-007"
    if r.replay_status == r.original_status:
        return None
    if r.original_status in _UNDECIDED:
        return "OVS-RES-008"
    if r.replay_status in _UNDECIDED:
        return "OVS-AUDIT-005"
    return "OVS-RES-007"


class Replayer:
    def __init__(self, keyring: KeyRing, *, mode: Literal["process", "inline"] = "process", queue_bound: int = QUEUE_BOUND, sample_rate: float = MIN_SAMPLE_RATE,
                 eager: bool = False, job_budget_s: float = 30.0) -> None:
        if mode not in ("process", "inline"):
            raise ValueError("replay mode must be 'process' or 'inline'")
        if not (MIN_SAMPLE_RATE <= sample_rate <= 1.0):
            raise ValueError(f"the sampling rate must be at least {MIN_SAMPLE_RATE}")
        self.mode = mode
        self.queue_bound = queue_bound
        self.sample_rate = sample_rate
        self.eager = eager
        self.job_budget_s = job_budget_s
        self._keyring = keyring
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._queued: list[ReplayJob] = []          # inline mode: waiting to run
        self._sampled_out: dict[str, ReplayJob] = {}
        self._inflight: dict[str, tuple[ReplayJob, float]] = {}  # process mode
        self._done: dict[str, ReplayOutcome] = {}
        self._known: set[str] = set()
        self._tasks: list[tuple[str, Callable[[], Any]]] = []
        self._task_results: dict[str, Any] = {}
        self._task_errors: dict[str, str] = {}
        self._ctx = None
        self._proc = None
        self._jobs_q = None
        self._results_q = None
        self._collector: Optional[threading.Thread] = None
        self._task_thread: Optional[threading.Thread] = None
        self._task_signal = threading.Event()
        self._closed = False
        self.submitted = 0
        self.sampled_out_total = 0

    # ------------------------------------------------------------------ replay jobs
    def submit(self, job: ReplayJob) -> str:
        """``queued``, ``sampled_out`` or ``known`` (already submitted)."""
        with self._lock:
            if job.result_id in self._known:
                if job.always and job.result_id in self._sampled_out:  # promoted: a sampled-out result is now always-replay
                    self._sampled_out.pop(job.result_id)
                    self._enqueue(job)
                    return "queued"
                return "known"
            self._known.add(job.result_id)
            self.submitted += 1
            outstanding = len(self._queued) + len(self._inflight)
            if not job.always and outstanding >= self.queue_bound and self._keyring.sample_fraction(job.result_id) >= self.sample_rate:
                self._sampled_out[job.result_id] = job
                self.sampled_out_total += 1
                return "sampled_out"
            self._enqueue(job)
        if self.mode == "inline" and self.eager:
            self.drain()
        return "queued"

    def _enqueue(self, job: ReplayJob) -> None:
        if self.mode == "inline":
            self._queued.append(job)
            return
        self._ensure_worker()
        self._inflight[job.result_id] = (job, time.monotonic())
        self._jobs_q.put((job.result_id, job.problem_json, job.config_json))

    def _ensure_worker(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            return
        self._ctx = multiprocessing.get_context("spawn")
        self._jobs_q = self._ctx.Queue()
        self._results_q = self._ctx.Queue()
        self._proc = self._ctx.Process(target=_worker_main, args=(self._jobs_q, self._results_q), daemon=True, name="overseer-replay")
        self._proc.start()
        self._collector = threading.Thread(target=self._collect, name="overseer-replay-collector", daemon=True)
        self._collector.start()

    def _collect(self) -> None:
        q = self._results_q
        while True:
            try:
                item = q.get()
            except (EOFError, OSError):
                return
            if item is None:
                return
            jid, result_json, error = item
            with self._cond:
                pair = self._inflight.pop(jid, None)
                if pair is not None:
                    self._done[jid] = self._finish(pair[0], result_json, error)
                self._cond.notify_all()

    def _finish(self, job: ReplayJob, result_json: Optional[str], error: Optional[str], budget_exceeded: bool = False) -> ReplayOutcome:
        if result_json is None:
            return ReplayOutcome(job=job, error=error, budget_exceeded=budget_exceeded)
        try:
            res = faithful(VerificationResult, json.loads(result_json))
            signed = sign_result(res, self._keyring.subkey("runs"), RUN_KEY_ID)
            return ReplayOutcome(job=job, result_json=canonical_json(signed.model_dump(mode="json", exclude_none=True)))
        except Exception as exc:
            return ReplayOutcome(job=job, error=f"{type(exc).__name__}")

    def drain(self, timeout_s: Optional[float] = None, *, include_sampled: bool = False) -> None:
        """Run (inline) or wait for (process) every outstanding job; with ``include_sampled`` the sampled-out jobs are
        replayed too. In process mode a job not finished within the timeout (default: its budget) is recorded as
        budget exceeded (RES-008), never as agreeing."""
        with self._lock:
            if include_sampled and self._sampled_out:
                for job in list(self._sampled_out.values()):
                    self._enqueue(job)
                self._sampled_out.clear()
            todo = list(self._queued)
            self._queued.clear()
        for job in todo:  # inline mode
            try:
                out = self._finish(job, replay_problem(job.problem_json, job.config_json), None)
            except Exception as exc:
                out = ReplayOutcome(job=job, error=f"{type(exc).__name__}")
            with self._lock:
                self._done[job.result_id] = out
        self._run_tasks()
        if self.mode != "process":
            return
        deadline = time.monotonic() + (timeout_s if timeout_s is not None else self.job_budget_s)
        with self._cond:
            while self._inflight and time.monotonic() < deadline:
                self._cond.wait(timeout=max(0.0, min(0.05, deadline - time.monotonic())))
            if timeout_s is None:
                for jid, (job, started) in list(self._inflight.items()):
                    if time.monotonic() - started >= self.job_budget_s:
                        self._inflight.pop(jid)
                        self._done[jid] = ReplayOutcome(job=job, budget_exceeded=True)

    def outcomes(self) -> dict[str, ReplayOutcome]:
        with self._lock:
            return dict(self._done)

    def pending(self) -> set[str]:
        with self._lock:
            return {j.result_id for j in self._queued} | set(self._inflight)

    def sampled_out(self) -> set[str]:
        with self._lock:
            return set(self._sampled_out)

    # ------------------------------------------------------------------ deferred deterministic tasks
    def submit_task(self, key: str, fn: Callable[[], Any]) -> None:
        with self._lock:
            if key in self._task_results or any(k == key for k, _ in self._tasks):
                return
            self._tasks.append((key, fn))
        if self.mode == "inline" and self.eager:
            self._run_tasks()
        elif self.mode == "process":
            self._ensure_task_thread()
            self._task_signal.set()

    def _ensure_task_thread(self) -> None:
        if self._task_thread is not None and self._task_thread.is_alive():
            return
        self._task_thread = threading.Thread(target=self._task_loop, name="overseer-rederive", daemon=True)
        self._task_thread.start()

    def _task_loop(self) -> None:
        while not self._closed:
            self._task_signal.wait(timeout=0.5)
            self._task_signal.clear()
            self._run_tasks()

    def _run_tasks(self) -> None:
        while True:
            with self._lock:
                if not self._tasks:
                    return
                key, fn = self._tasks.pop(0)
            try:
                value = fn()
                with self._cond:
                    self._task_results[key] = value
                    self._cond.notify_all()
            except Exception as exc:
                with self._cond:
                    self._task_errors[key] = f"{type(exc).__name__}: {str(exc)[:200]}"
                    self._task_results[key] = None
                    self._cond.notify_all()

    def task_result(self, key: str) -> tuple[bool, Any, Optional[str]]:
        """(done, value, error)."""
        with self._lock:
            if key in self._task_results:
                return True, self._task_results[key], self._task_errors.get(key)
            return False, None, None

    def tasks_pending(self) -> set[str]:
        with self._lock:
            return {k for k, _ in self._tasks}

    def wait_tasks(self, timeout_s: float) -> None:
        if self.mode == "inline":
            self._run_tasks()
            return
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while self._tasks and time.monotonic() < deadline:
                self._cond.wait(timeout=max(0.0, min(0.05, deadline - time.monotonic())))

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        self._closed = True
        self._task_signal.set()
        if self._proc is not None:
            try:
                self._jobs_q.put(None)
                self._proc.join(timeout=5)
            except Exception:
                pass
            if self._proc.is_alive():
                self._proc.terminate()
            try:
                self._results_q.put(None)
            except Exception:
                pass
            self._proc = None

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass
