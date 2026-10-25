"""Result sink: capture every engine run made inside a scope.

The Overseer audit must see every signed result a transfer produced, not only the ones
that survive onto a receipt (claim outcomes do; request constraints, branch formal checks,
cross-report and synthesis runs are reduced to ids). :func:`verify` calls :func:`emit`
once per result, after signing; a caller that wants the results opens
:func:`capture_results` around the work and reads ``capture.items`` afterwards.

* A ``ContextVar`` holds the tuple of active captures; :func:`emit` appends to every one
  of them, so nested scopes each see the runs made inside them.
* With no capture active, :func:`emit` costs one ``ContextVar.get`` and does nothing.
* Each result is serialised to canonical JSON AT EMIT TIME. A string is immutable, so a
  later mutation of the live result object (a status rewritten, a signature stripped)
  can never reach the capture; the store needs the serialised form anyway.
* :func:`emit` never raises; the runner also calls it inside ``try/except``.
* ``ContextVar`` values are per thread and per asyncio task, and ``asyncio.to_thread``
  copies the context, so a service call lands in its caller's capture and parallel
  channels never mix their results.

Nothing here changes a result: the runner returns exactly what it returned before.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from ..ir.canonical import canonical_json, sha256_hex

__all__ = ["CapturedResult", "ResultCapture", "capture_results", "emit", "capture_active", "MAX_CAPTURED"]

#: Most results one capture keeps; beyond it further results are counted in ``overflow`` and the
#: auditor reports the lost coverage (it never treats an uncaptured run as captured).
MAX_CAPTURED = 65_536


@dataclass(frozen=True)
class CapturedResult:
    """One engine run as it was returned by ``verify``: canonical JSON strings and their digests.

    ``problem_json`` is the problem that was actually validated and compiled (the demoted problem on
    the raw path), ``None`` when the payload never parsed into a problem."""
    result_id: str
    key_id: Optional[str]
    result_json: str
    result_sha256: str
    problem_json: Optional[str]
    problem_digest: Optional[str]

    def to_dict(self) -> dict:
        return {"result_id": self.result_id, "key_id": self.key_id, "result_json": self.result_json, "result_sha256": self.result_sha256,
                "problem_json": self.problem_json, "problem_digest": self.problem_digest}


class ResultCapture:
    """The runs emitted while one :func:`capture_results` scope was active, in emit order."""

    __slots__ = ("_items", "_lock", "overflow", "max_items")

    def __init__(self, max_items: int = MAX_CAPTURED) -> None:
        self._items: list[CapturedResult] = []
        self._lock = threading.Lock()
        self.overflow = 0
        self.max_items = max_items

    @property
    def items(self) -> list[CapturedResult]:
        """A copy of the captured results (the capture itself is append-only)."""
        with self._lock:
            return list(self._items)

    def _append(self, item: CapturedResult) -> None:
        with self._lock:
            if len(self._items) >= self.max_items:
                self.overflow += 1
                return
            self._items.append(item)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


_ACTIVE: ContextVar[tuple[ResultCapture, ...]] = ContextVar("epinoic_result_captures", default=())


def capture_active() -> bool:
    return bool(_ACTIVE.get())


@contextmanager
def capture_results(max_items: int = MAX_CAPTURED) -> Iterator[ResultCapture]:
    """Capture every engine result emitted in this context (and in contexts copied from it)."""
    cap = ResultCapture(max_items=max_items)
    token = _ACTIVE.set(_ACTIVE.get() + (cap,))
    try:
        yield cap
    finally:
        _ACTIVE.reset(token)


def _serialise(result: Any, problem: Any) -> CapturedResult:
    data = result.model_dump(mode="json", exclude_none=True)
    result_json = canonical_json(data)
    problem_json: Optional[str] = None
    problem_dig: Optional[str] = None
    if problem is not None:
        problem_json = canonical_json(problem)
        problem_dig = sha256_hex(problem_json)
    return CapturedResult(result_id=str(data.get("result_id", "")), key_id=data.get("signature_key_id"), result_json=result_json,
                          result_sha256=sha256_hex(result_json), problem_json=problem_json, problem_digest=problem_dig)


def emit(result: Any, problem: Any = None) -> None:
    """Record ``result`` (and the problem it was decided on) in every active capture. Never raises."""
    try:
        captures = _ACTIVE.get()
        if not captures:
            return
        item = _serialise(result, problem)
        for cap in captures:
            cap._append(item)
    except Exception:  # the sink must never change what verify() returns or raise into the engine
        return
