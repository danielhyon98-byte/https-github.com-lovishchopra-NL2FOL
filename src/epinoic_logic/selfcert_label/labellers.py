"""Labellers: who answers a label request, and the policies around every call (meaning-check design 2.5.8; overseer-side 5.2).

* :class:`UnconfiguredLabeller` is the default (:func:`default_labeller`): every call is ``unavailable`` (``not-configured``),
  so an answer with no labeller is withheld, never delivered on the reader alone.
* :class:`ProviderLabeller` takes an INJECTED transport (a callable the deployment supplies). This package never imports a
  provider SDK and never opens a socket; the configured model is kept only as the SHA-256 of its identifier.
* :class:`RecordedLabeller` serves recorded replies by request key; an unrecorded key is ``unavailable`` (``not-recorded``).
* :class:`CachingLabeller` keeps an LRU of :data:`CACHE_SIZE` successes keyed on the rendered request; failures are never cached.
* :class:`BudgetedLabeller` makes no call once its call budget is spent (``budget``, with zero provider calls).
* :class:`CircuitBreakerLabeller`: :data:`BREAKER_FAILURES` consecutive provider failures pause calls for :data:`BREAKER_PAUSE_S`
  seconds; each call in a pause is a fast ``unavailable`` and :meth:`Labeller.health` reports ``degraded``. There is no
  reader-only degraded mode.

Every calling labeller makes at most one retry per chunk, with fresh canaries, each call inside
``min(15 s, deadline - now - 2 s)``. The labeller bounds each call itself (the call runs on a worker thread and is abandoned when
its timeout passes), and a reply that comes back after the timeout by the labeller's clock is ``timeout`` too: a transport that
ignores the timeout it is given cannot hold the label past it. A malformed, incomplete or control-failed reply is retried with a diagnostic block naming
the failure by its enum; a truncated or oversized reply is retried as the chunk's two halves; a timeout is retried only when the
deadline leaves the full timeout. Any exception in label code is ``unavailable`` (``label-failed``). Nothing here returns
``none_named`` except a fully validated reply that named nothing.
"""
from __future__ import annotations

import collections
import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .inputs import LabelInput, build_input, input_key
from .record import LabelResult, attempt_entry, result_from_attempts, skipped_result, unavailable_result
from .render import LABEL_VERSION, RenderError, RenderedRequest
from .scope import own_scope
from .validate import validate_reply

__all__ = ["Reply", "CallFailure", "Labeller", "UnconfiguredLabeller", "CallingLabeller", "ProviderLabeller", "RecordedLabeller",
           "CachingLabeller", "BudgetedLabeller", "CircuitBreakerLabeller", "CallBudget", "LabelHandle", "default_labeller",
           "model_digest", "LABEL_TIMEOUT_S", "DEADLINE_MARGIN_S", "CACHE_SIZE", "BREAKER_FAILURES", "BREAKER_PAUSE_S"]

LABEL_TIMEOUT_S = 15.0
DEADLINE_MARGIN_S = 2.0
DEFAULT_WAIT_S = 30.0
CACHE_SIZE = 4096
BREAKER_FAILURES = 5
BREAKER_PAUSE_S = 60.0
#: Failures after which no retry is made (nothing a retry could change).
_NO_RETRY = frozenset({"not-configured", "budget", "not-recorded"})


def model_digest(model_id: str) -> str:
    """The SHA-256 of a configured model identifier: the only form in which a model is ever recorded."""
    return hashlib.sha256(str(model_id).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reply:
    text: str
    stop_reason: Optional[str] = "end_turn"


def _bounded(caller: "Caller", req: RenderedRequest, timeout: float) -> "Reply":
    """``caller(req, timeout)`` bounded by ``timeout`` seconds of real time: the call runs on a daemon thread, and a call still
    running when the bound passes is abandoned and raises ``TimeoutError`` (its late reply is never read). The labeller bounds
    the call itself, so a transport that ignores the timeout it is given cannot hold the label past it (attack round 16)."""
    box: dict = {}

    def run() -> None:
        try:
            box["reply"] = caller(req, timeout)
        except BaseException as e:  # noqa: BLE001 - carried to the calling thread
            box["error"] = e
    worker = threading.Thread(target=run, name="selfcert-label-call", daemon=True)
    worker.start()
    worker.join(max(0.0, timeout))
    if worker.is_alive():
        raise TimeoutError("label call exceeded its timeout")
    if "error" in box:
        raise box["error"]
    return box.get("reply")


class CallFailure(Exception):
    """A call that returned no reply: ``kind`` is an unavailable kind (provider-error, timeout, budget, not-recorded, ...)."""

    def __init__(self, kind: str, detail: Optional[str] = None):
        super().__init__(kind)
        self.kind = kind
        self.detail = detail


#: A caller answers one rendered request within a timeout (seconds), or raises CallFailure.
Caller = Callable[[RenderedRequest, float], Reply]


def _label_digest() -> str:
    from . import label_digest
    return label_digest()


class LabelHandle:
    """A submitted label request; :meth:`Labeller.result` computes it once."""

    def __init__(self, labeller: "Labeller", raw_text: str, request: Any, writer: str, deadline: Optional[float]):
        self._args = (raw_text, request, writer, deadline)
        self._labeller = labeller
        self._result: Optional[LabelResult] = None
        self._lock = threading.Lock()

    def result(self) -> LabelResult:
        with self._lock:
            if self._result is None:
                raw_text, request, writer, deadline = self._args
                self._result = self._labeller.label(raw_text, request, writer=writer, deadline=deadline)
            return self._result


class Labeller:
    """The labeller interface: :meth:`label` (or :meth:`submit` then :meth:`result`) gives one answer's :class:`LabelResult`."""
    model_digest: str = ""

    def label(self, raw_text: str, request: Any = None, *, writer: str = "specialist",
              deadline: Optional[float] = None) -> LabelResult:
        try:
            return self._label(raw_text, request, writer=writer, deadline=deadline)
        except Exception:  # noqa: BLE001 - fail closed: label code that fails is unavailable, never none_named
            return self._failed(raw_text, request, writer, "label-failed")

    def _label(self, raw_text: str, request: Any, *, writer: str, deadline: Optional[float]) -> LabelResult:
        raise NotImplementedError

    def _failed(self, raw_text: str, request: Any, writer: str, kind: str, attempts: Optional[list] = None) -> LabelResult:
        try:
            scope = own_scope(raw_text, request, writer=writer)
            ik = input_key(scope, request)
            w = scope.writer
        except Exception:  # noqa: BLE001
            ik, w = "", "specialist" if writer != "combinator" else "combinator"
        try:
            digest = _label_digest()
        except Exception:  # noqa: BLE001
            digest = ""
        return unavailable_result(ik, kind, writer=w, label_digest=digest, model_digest=self.model_digest, attempts=attempts)

    def skipped(self, raw_text: str, request: Any = None, *, writer: str = "specialist") -> LabelResult:
        """The record for an answer the rule reader already refuses (no label asked). Input that cannot be read is
        ``unavailable`` (``label-failed``)."""
        try:
            scope = own_scope(raw_text, request, writer=writer)
        except Exception:  # noqa: BLE001 - fail closed
            return self._failed(raw_text, request, writer, "label-failed")
        return skipped_result(input_key(scope, request), writer=scope.writer, label_digest=_label_digest(),
                              model_digest=self.model_digest)

    def submit(self, raw_text: str, request: Any = None, *, writer: str = "specialist",
               deadline: Optional[float] = None) -> LabelHandle:
        return LabelHandle(self, raw_text, request, writer, deadline)

    def result(self, handle: LabelHandle) -> LabelResult:
        return handle.result()

    def health(self) -> str:
        """``ok``, ``degraded`` (a circuit breaker is open) or ``off`` (no labeller configured)."""
        return "ok"


class UnconfiguredLabeller(Labeller):
    """The default: every call is unavailable (not-configured); no call of any kind is made."""

    def _label(self, raw_text, request, *, writer, deadline):
        return self._failed(raw_text, request, writer, "not-configured")

    def health(self) -> str:
        return "off"


def default_labeller() -> Labeller:
    return UnconfiguredLabeller()


class CallingLabeller(Labeller):
    """A labeller that renders requests and calls ``caller`` for each (module docstring for the retry and deadline rules).
    ``key`` is the canary key; ``clock`` a monotonic clock in seconds (injected in tests)."""

    def __init__(self, caller: Caller, *, key: bytes, model_digest: str, clock: Optional[Callable[[], float]] = None,
                 timeout_s: float = LABEL_TIMEOUT_S, prompt_path=None):
        if not isinstance(key, (bytes, bytearray)) or not key:
            raise ValueError("a canary key is required")
        self.caller = caller
        self._key = bytes(key)
        self.model_digest = model_digest
        self.clock = clock or time.monotonic
        self.timeout_s = float(timeout_s)
        self.prompt_path = prompt_path
        self.calls = 0

    def _derived(self, caller: Caller) -> dict:
        return {"key": self._key, "model_digest": self.model_digest, "clock": self.clock, "timeout_s": self.timeout_s,
                "prompt_path": self.prompt_path}

    def prepare(self, raw_text: str, request: Any = None, *, writer: str = "specialist") -> LabelInput:
        return build_input(raw_text, request, key=self._key, writer=writer, prompt_path=self.prompt_path)

    def _label(self, raw_text, request, *, writer, deadline):
        return self.label_input(self.prepare(raw_text, request, writer=writer), deadline=deadline)

    def label_input(self, inp: LabelInput, *, deadline: Optional[float] = None) -> LabelResult:
        try:
            return self._label_input(inp, deadline)
        except Exception:  # noqa: BLE001 - fail closed
            return unavailable_result(inp.input_key, "label-failed", writer=inp.scope.writer, label_digest=_label_digest(),
                                      model_digest=self.model_digest)

    def _label_input(self, inp: LabelInput, deadline: Optional[float]) -> LabelResult:
        digest = _label_digest()
        if inp.oversized:
            return unavailable_result(inp.input_key, "oversized", writer=inp.scope.writer, label_digest=digest,
                                      model_digest=self.model_digest)
        if inp.error is not None:
            return unavailable_result(inp.input_key, "label-failed", writer=inp.scope.writer, label_digest=digest,
                                      model_digest=self.model_digest)
        if deadline is None:
            deadline = self.clock() + DEFAULT_WAIT_S
        attempts: list[dict] = []
        for c in range(len(inp.chunks)):
            ok = self._chunk(inp, c, deadline, attempts)
            if not ok:
                break  # this answer is withheld already; no further call is spent on it
        return result_from_attempts(inp, attempts, label_digest=digest, model_digest=self.model_digest)

    def _call(self, inp: LabelInput, req: RenderedRequest, timeout: float, attempts: list, *, chunk: int, attempt: int,
              part: Optional[int], diagnostic: tuple) -> tuple[Optional[str], Optional[str]]:
        """Make one call and record it: (failure kind, validation fault) — both None on a valid reply."""
        try:
            self.calls += 1
            started = self.clock()
            reply = _bounded(self.caller, req, timeout)
            if self.clock() - started > timeout:
                # a reply after the call's timeout (so after min(15 s, deadline - now - 2 s)) is never used: the transport
                # ignored the bound it was given (attack round 16)
                attempts.append(attempt_entry(req, call_fault="timeout", detail="late", chunk=chunk, attempt=attempt, part=part,
                                              diagnostic=diagnostic))
                return "timeout", None
            if not isinstance(reply, Reply):
                reply = Reply(str(reply)) if isinstance(reply, str) else Reply("", None)
        except CallFailure as f:
            kind = f.kind if f.kind in ("provider-error", "timeout", "budget", "not-recorded", "not-configured") else "provider-error"
            attempts.append(attempt_entry(req, call_fault=kind, detail=f.detail, chunk=chunk, attempt=attempt, part=part,
                                          diagnostic=diagnostic))
            return kind, None
        except TimeoutError:
            attempts.append(attempt_entry(req, call_fault="timeout", chunk=chunk, attempt=attempt, part=part, diagnostic=diagnostic))
            return "timeout", None
        except Exception:  # noqa: BLE001 - a transport that fails is a provider error
            attempts.append(attempt_entry(req, call_fault="provider-error", chunk=chunk, attempt=attempt, part=part,
                                          diagnostic=diagnostic))
            return "provider-error", None
        v = validate_reply(reply.text, reply.stop_reason, req, inp.scope)
        attempts.append(attempt_entry(req, raw=reply.text, stop_reason=reply.stop_reason, validation=v, chunk=chunk, attempt=attempt,
                                      part=part, diagnostic=diagnostic))
        if v.state == "unavailable":
            return None, v.fault or "malformed"
        return None, None

    def _timeout(self, deadline: float) -> float:
        return min(self.timeout_s, deadline - self.clock() - DEADLINE_MARGIN_S)

    def _chunk(self, inp: LabelInput, c: int, deadline: float, attempts: list) -> bool:
        """Label chunk ``c`` (at most one retry); True when the chunk has a valid label."""
        timeout = self._timeout(deadline)
        if timeout <= 0:
            attempts.append(attempt_entry(None, call_fault="timeout", detail="deadline", chunk=c, attempt=0))
            return False
        req = inp.requests[c] if c < len(inp.requests) else inp.render(c, attempt=0)
        kind, fault = self._call(inp, req, timeout, attempts, chunk=c, attempt=0, part=None, diagnostic=())
        if kind is None and fault is None:
            return True
        if kind in _NO_RETRY or (kind == "provider-error" and attempts[-1].get("detail") == "circuit-open"):
            return False
        timeout = self._timeout(deadline)
        if timeout <= 0 or (kind == "timeout" and timeout < self.timeout_s):
            return False
        if fault in ("truncated", "oversized_reply") and sum(len(idx) for _pn, idx in inp.chunks[c].paragraphs) >= 2:
            for part in (0, 1):
                timeout = self._timeout(deadline)
                if timeout <= 0:
                    attempts.append(attempt_entry(None, call_fault="timeout", detail="deadline", chunk=c, attempt=1, part=part))
                    return False
                try:
                    preq = inp.render(c, attempt=1, part=part)
                except RenderError:
                    attempts.append(attempt_entry(None, call_fault="provider-error", detail="render", chunk=c, attempt=1, part=part))
                    return False
                k2, f2 = self._call(inp, preq, timeout, attempts, chunk=c, attempt=1, part=part, diagnostic=())
                if k2 is not None or f2 is not None:
                    return False
            return True
        diagnostic = (fault,) if fault else ((kind,) if kind else ())
        try:
            rreq = inp.render(c, attempt=1, diagnostic=diagnostic)
        except RenderError:
            return False
        k2, f2 = self._call(inp, rreq, timeout, attempts, chunk=c, attempt=1, part=None, diagnostic=diagnostic)
        return k2 is None and f2 is None


class ProviderLabeller(CallingLabeller):
    """A labeller over an injected ``transport(system_text, user_text, *, max_tokens, timeout_s)`` that returns the reply text
    and its stop reason (a :class:`Reply`, a ``(text, stop_reason)`` pair, or an object with ``text`` and ``stop_reason``). The
    transport is the deployment's: this class never imports a provider SDK or opens a connection. ``model_id`` is hashed at once
    and not kept. A ``TimeoutError`` is ``timeout``; any other exception, or an empty reply, is ``provider-error``."""

    def __init__(self, transport: Callable[..., Any], *, key: bytes, model_id: str, clock=None, timeout_s: float = LABEL_TIMEOUT_S,
                 prompt_path=None):
        def caller(req: RenderedRequest, timeout: float) -> Reply:
            out = transport(req.system_text, req.user_text, max_tokens=req.max_tokens, timeout_s=timeout)
            if isinstance(out, Reply):
                text, stop = out.text, out.stop_reason
            elif isinstance(out, tuple) and len(out) == 2:
                text, stop = out
            else:
                text, stop = getattr(out, "text", None), getattr(out, "stop_reason", None)
            if not isinstance(text, str) or not text.strip():
                raise CallFailure("provider-error", "missing")
            return Reply(text, stop if isinstance(stop, str) else None)
        super().__init__(caller, key=key, model_digest=model_digest(model_id), clock=clock, timeout_s=timeout_s,
                         prompt_path=prompt_path)


class RecordedLabeller(CallingLabeller):
    """Serves recorded replies by request key: ``recordings[request_key] = {"raw_text", "stop_reason", "model_digest"}`` (the
    round format of design 3.4). An unrecorded key, a recording that names no model, a recording of another model, or one of
    another label version is ``unavailable`` (``not-recorded``): withheld and counted, never treated as clean."""

    def __init__(self, recordings: Mapping[str, Mapping[str, Any]], *, key: bytes, model_digest: str, clock=None, prompt_path=None):
        def caller(req: RenderedRequest, timeout: float) -> Reply:
            rec = recordings.get(req.request_key)
            if not isinstance(rec, Mapping):
                raise CallFailure("not-recorded")
            # every recording names its model (design 3.4, 2.4 O5): one with no model digest, or another model's, is never
            # served as a label of the configured model (attack round 16)
            if rec.get("model_digest") != model_digest:
                raise CallFailure("not-recorded", "model")
            if rec.get("label_version", LABEL_VERSION) != LABEL_VERSION:
                raise CallFailure("not-recorded", "version")
            text = rec.get("raw_text")
            if not isinstance(text, str):
                raise CallFailure("not-recorded")
            stop = rec.get("stop_reason", "end_turn")
            return Reply(text, stop if isinstance(stop, str) else None)
        super().__init__(caller, key=key, model_digest=model_digest, clock=clock, prompt_path=prompt_path)


class CachingLabeller(Labeller):
    """An LRU of successes (``named`` and ``none_named``) keyed on the rendered request; failures are never cached, so the next
    turn tries again."""

    def __init__(self, inner: Labeller, maxsize: int = CACHE_SIZE):
        self.inner = inner
        self.model_digest = inner.model_digest
        self.maxsize = int(maxsize)
        self._cache: "collections.OrderedDict[str, LabelResult]" = collections.OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0

    def _label(self, raw_text, request, *, writer, deadline):
        if not isinstance(self.inner, CallingLabeller):
            return self.inner.label(raw_text, request, writer=writer, deadline=deadline)  # nothing to cache (never a success)
        inp = self.inner.prepare(raw_text, request, writer=writer)
        key = inp.cache_key
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                self.hits += 1
                return hit
        res = self.inner.label_input(inp, deadline=deadline)
        if res.state in ("named", "none_named"):
            with self._lock:
                self._cache[key] = res
                self._cache.move_to_end(key)
                while len(self._cache) > self.maxsize:
                    self._cache.popitem(last=False)
        return res

    def __len__(self) -> int:
        return len(self._cache)

    def health(self) -> str:
        return self.inner.health()


class CallBudget:
    """A count of calls that may still be made (shared between labellers when the cap is shared)."""

    def __init__(self, calls: int):
        self.remaining = max(0, int(calls))
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


class BudgetedLabeller(CallingLabeller):
    """``inner`` with a call budget: once it is spent, every call is ``unavailable`` (``budget``) and no call is made."""

    def __init__(self, inner: CallingLabeller, budget: "CallBudget | int"):
        self.budget = budget if isinstance(budget, CallBudget) else CallBudget(budget)
        self.inner = inner
        inner_caller = inner.caller

        def caller(req: RenderedRequest, timeout: float) -> Reply:
            if not self.budget.take():
                raise CallFailure("budget")
            inner.calls += 1
            return inner_caller(req, timeout)
        super().__init__(caller, **inner._derived(caller))

    def health(self) -> str:
        return self.inner.health()


class CircuitBreakerLabeller(CallingLabeller):
    """``inner`` behind a circuit breaker: after ``failures`` consecutive provider failures (provider-error or timeout, a call cut
    off at its timeout or a late reply included) no call is made for ``pause_s`` seconds; each call then is a fast
    ``unavailable`` (provider-error, detail ``circuit-open``) and :meth:`health` is ``degraded``. A reply of any kind in time
    closes the count."""

    def __init__(self, inner: CallingLabeller, *, failures: int = BREAKER_FAILURES, pause_s: float = BREAKER_PAUSE_S,
                 clock: Optional[Callable[[], float]] = None):
        self.inner = inner
        self.failures = int(failures)
        self.pause_s = float(pause_s)
        self._clock = clock or inner.clock
        self.consecutive = 0
        self.open_until: Optional[float] = None
        self._lock = threading.Lock()
        inner_caller = inner.caller

        def caller(req: RenderedRequest, timeout: float) -> Reply:
            with self._lock:
                if self.open_until is not None:
                    if self._clock() < self.open_until:
                        raise CallFailure("provider-error", "circuit-open")
                    self.open_until = None
                    self.consecutive = 0
            try:
                inner.calls += 1
                started = self._clock()
                reply = _bounded(inner_caller, req, timeout)  # a call cut off at its timeout counts as a failure here too
                if self._clock() - started > timeout:
                    raise TimeoutError("late reply")  # and so does a late reply
            except CallFailure as f:
                if f.kind in ("provider-error", "timeout"):
                    self._failed_once()
                raise
            except TimeoutError:
                self._failed_once()
                raise
            except Exception:
                self._failed_once()
                raise
            with self._lock:
                self.consecutive = 0
            return reply
        derived = inner._derived(caller)
        derived["clock"] = inner.clock
        super().__init__(caller, **derived)

    def _failed_once(self) -> None:
        with self._lock:
            self.consecutive += 1
            if self.consecutive >= self.failures:
                self.open_until = self._clock() + self.pause_s

    def health(self) -> str:
        with self._lock:
            if self.open_until is not None and self._clock() < self.open_until:
                return "degraded"
        return self.inner.health()
