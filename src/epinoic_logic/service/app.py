"""Authenticated HTTP boundary around the verification engine.

The service is the only way other components (the Overseer, the backend) reach the
solver. It enforces, in this order for every ``/v1`` request:

1. bearer authentication (constant-time comparison)            -> 401 ``E502``
2. a per-token token bucket                                     -> 429 ``E503``
3. the request-body size limit, checked before the body is read -> 413 ``E306``
4. strict JSON envelope parsing (no NaN, no duplicate keys,
   object only)                                                 -> 400 ``E100``
5. rejection of self-certification fields, at the top level and
   nested as ``grounding.verified: true`` inside the problem    -> 400 ``E505``
6. rejection of client-supplied ``config.memory_max_mb`` (the
   Z3 memory budget is process-global and server-controlled)    -> 400 ``E100``
7. rejection of any ``policy`` that is not exactly the name of an
   allowlisted engine policy (never raw limits)                 -> 400 ``E100``
8. bounded solver concurrency (non-blocking admission)          -> 503 ``E504``

Solver runs happen in a worker thread so the event loop stays responsive. Every
response carries ``X-Request-Id`` (echoed from the request when well formed,
otherwise generated). Error bodies are small JSON objects ``{code, message,
request_id}``; they never contain stack traces, exception text or the request
body. Logs record metadata only (request id, path, HTTP status, result status,
elapsed time) and never any payload content.

Endpoints
---------
``GET  /healthz``                       liveness; unauthenticated; component versions only
``POST /v1/verify``                     ``{problem, config?, policy?}`` -> signed ``VerificationResult``;
                                        ``policy`` names the engine policy the problem is
                                        decided under (``linear`` by default, ``nonlinear``
                                        or ``joint``: ``engine.policies.NAMED_POLICIES``),
                                        applied exactly as the in-process caller of that
                                        policy applies it (``engine.policies.named_policy``)
                                        and bound into the result (limits record and digest,
                                        configuration digest)
``POST /v1/results/verify-signature``   ``{result}`` -> ``{valid: bool, reason?}``
``POST /v1/results/release-check``      ``{result, problem?, policy?}`` -> ``{eligible: bool, reasons, current}``:
                                        the engine's current-policy release check
                                        (``engine.release.release_check``) under this
                                        service's key; ``policy`` names the required
                                        validation limits (``linear`` by default,
                                        ``nonlinear`` or ``joint``; the same allowlist)
``POST /v1/outcomes``                   ``{report, claim_id, fixture_responses, adapter_id?}``
                                        -> ``ClaimVerificationOutcome`` (fixture provider only;
                                        model providers are wired by configuration later)

An invalid or unsupported problem is NOT an HTTP error: it is a bound, signed result
with status ``INVALID_FORMALIZATION`` or ``UNSUPPORTED`` (HTTP 200), so callers
always receive an auditable record. HTTP errors are reserved for the envelope and
for admission control.

``config.produce_unsat_core`` is an output option only: the engine computes the unsat
core either way, so the dependency lists, the vacuity and circularity checks and the
release check of a result are the same whichever value a client sends.

A caller requests an engine policy by NAME only. ``nonlinear`` opens the nonlinear-term gate and
caps ``config.rlimit`` at ``NONLINEAR_RLIMIT`` (a lower ``rlimit`` is kept), as the channel's STEM
checks run; ``joint`` raises the shape bounds to the integrity layer's ``JOINT_LIMITS`` (no
nonlinear terms), as the cross-agent joint checks run. The same problem therefore gets the same
decision over HTTP as in the pipeline. Authentication, the rate limit, the body-size limit (which,
not the policy, bounds how large a problem can be sent), the per-call timeout and the concurrency
limit apply under every policy, and an unknown name is refused before anything is run.

Hardening (review round 8):

* a body holding a lone surrogate (a ``\\ud800`` escape: valid JSON, not Unicode text) is refused
  as 400 ``E100`` on every route, before any model sees it, so no later encoding can fail as a 500;
* ``config`` and the outcome route's ``report`` are validated strictly (``true`` is no timeout, ``"100"`` no
  integer, ``"yes"`` no boolean: 400 ``E100``), and
  ``config.model_completion`` is server-controlled like ``memory_max_mb`` (400 ``E100``): the engine
  always completes models, so a counterexample's values are always literals;
* ``POST /v1/outcomes`` takes the client's ``fixture_responses`` only when the service allows it
  (``ServiceSettings.allow_client_fixtures``, off by default): otherwise 403 ``E506`` before the
  body is read, since the client would act as the translation provider;
* ``adapter_id`` is looked up in a closed allowlist built when the app is created from the
  registered adapters: an unknown, overlong or ill-formed id is refused and no module is imported;
* every logged field passes :func:`_log_safe` (a filter on each logger of :data:`SAFE_LOGGERS`, the
  service's and the translation pipeline's): C0 and C1 controls, line separators, lone surrogates and
  the backslash are escaped and each field is cut to 128 characters, so a claim id cannot forge a log
  line.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import importlib
import json
import logging
import re
import threading
import time
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..engine.errors import DiagnosticCode
from ..engine.policies import LINEAR, NAMED_POLICIES, UnknownPolicyError, named_policy
from ..engine.provenance import FORM_BOUND, FORM_LEGACY, compute_versions, signature_form, z3_version
from ..engine.release import release_check
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify
from ..ir.canonical import strict_object_pairs
from ..ir.schema import Limits, Problem
from ..version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION
from .settings import ServiceSettings

__all__ = [
    "LOG_FIELD_MAX_CHARS",
    "SAFE_LOGGERS",
    "REQUEST_ID_HEADER",
    "SELF_CERTIFICATION_KEYS",
    "SERVER_CONTROLLED_CONFIG_KEYS",
    "HttpError",
    "TokenBucketLimiter",
    "RequestIdMiddleware",
    "create_app",
]

#: Each logged field is cut to this many characters (:func:`_log_safe`).
LOG_FIELD_MAX_CHARS = 128
log = logging.getLogger("epinoic_logic.service")


def _log_safe(value: Any, limit: int = LOG_FIELD_MAX_CHARS) -> str:
    """``value`` as one safe log field: every C0 and C1 control character, the line and paragraph separators, a lone
    surrogate and the backslash are escaped (``\\n``, ``\\x1b``, ``\\u2028``, ``\\\\``), and the field is cut to ``limit``
    characters of the original (the cut is marked). A logged claim id or path can then never start a new log line or
    imitate a field of another one."""
    text = value if isinstance(value, str) else str(value)
    head = text[:limit]
    out: list[str] = []
    for ch in head:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or 0x7F <= o <= 0x9F:
            out.append(f"\\x{o:02x}")
        elif o in (0x2028, 0x2029) or 0xD800 <= o <= 0xDFFF:
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)
    safe = "".join(out)
    return safe if len(text) <= limit else f"{safe}...(+{len(text) - limit} chars)"


class _SafeFields(logging.Filter):
    """Pass every argument of a service log record through :func:`_log_safe` (numbers stay numbers, for ``%d``)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(a if isinstance(a, (int, float)) else _log_safe(a) for a in args)
        elif isinstance(args, Mapping):
            record.args = {k: (a if isinstance(a, (int, float)) else _log_safe(a)) for k, a in args.items()}
        return True


#: Every logger of the package that logs a value taken from a request: the service's own and the translation pipeline's
#: (``translation <id> claim=<claim id> ...``, reached through ``POST /v1/outcomes``). A logger's filter applies to the records
#: logged through it, so each one carries the filter itself; ``logging.getLogger`` returns the same logger object the
#: pipeline module creates on import.
SAFE_LOGGERS: tuple[str, ...] = ("epinoic_logic.service", "epinoic_logic.translate.pipeline")
for _name in SAFE_LOGGERS:
    _logger = logging.getLogger(_name)
    if not any(isinstance(f, _SafeFields) for f in _logger.filters):
        _logger.addFilter(_SafeFields())

REQUEST_ID_HEADER = "X-Request-Id"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")  # applied with fullmatch: a trailing newline is no part of an id
#: The form an ``adapter_id`` must have before the allowlist is even consulted.
_ADAPTER_ID_RE = re.compile(r"[a-z0-9_.-]{1,64}")

#: Keys a client might use to assert a verification verdict about its own payload.
#: They are refused outright (400 ``E505``): status comes only from the engine.
SELF_CERTIFICATION_KEYS: frozenset[str] = frozenset({
    "advisory_verification_status", "verified", "self_certified", "status",
})
#: Solver options a client may not set: ``memory_max_mb`` is process-global, so one request could affect every other;
#: ``model_completion`` would let a client obtain signed counterexamples whose values are symbol names, not literals
#: (the engine always completes models, so the option has no effect on evidence and is not the client's to send).
SERVER_CONTROLLED_CONFIG_KEYS: frozenset[str] = frozenset({"memory_max_mb", "model_completion"})
_VERIFY_ENVELOPE_KEYS = frozenset({"problem", "config", "policy"})
_SIGNATURE_ENVELOPE_KEYS = frozenset({"result"})
_RELEASE_ENVELOPE_KEYS = frozenset({"result", "problem", "policy"})
#: Engine policies a request may name (``POST /v1/verify``: decide under it; ``POST /v1/results/release-check``: require
#: it): the pack policies and the integrity layer's joint limits, ``engine.policies.NAMED_POLICIES``. One allowlist for
#: both routes, so a result decided under a policy over HTTP is current for a receiver that names the same policy.
RELEASE_POLICIES: Mapping[str, Limits] = NAMED_POLICIES
_OUTCOME_ENVELOPE_KEYS = frozenset({"report", "claim_id", "fixture_responses", "adapter_id"})

Handler = Callable[[Request], Awaitable[JSONResponse]]


class HttpError(Exception):
    """An HTTP-level rejection with a stable diagnostic code and a safe message."""

    def __init__(self, status_code: int, code: DiagnosticCode, message: str, headers: Optional[Mapping[str, str]] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers or {})


class TokenBucketLimiter:
    """Per-key token bucket: ``rate_per_minute`` capacity, refilled continuously.

    ``clock`` is a monotonic seconds source; tests may replace it. Thread-safe.
    """

    def __init__(self, rate_per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        if rate_per_minute < 1:
            raise ValueError("rate_per_minute must be positive")
        self.capacity = float(rate_per_minute)
        self.refill_per_second = rate_per_minute / 60.0
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def try_acquire(self, key: str) -> bool:
        """Consume one token for ``key`` if available; return whether the request is admitted."""
        now = self.clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + max(0.0, now - last) * self.refill_per_second)
            admitted = tokens >= 1.0
            if admitted:
                tokens -= 1.0
            self._buckets[key] = (tokens, now)
            return admitted


class RequestIdMiddleware:
    """Pure ASGI middleware: attach a request id to the scope and echo it on every response.

    A well-formed incoming ``X-Request-Id`` (1-128 chars of ``[A-Za-z0-9._:-]``) is
    echoed; anything else is replaced by a generated id so log lines cannot be
    forged or broken by header content.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, REQUEST_ID_HEADER.lower())
        request_id = incoming if incoming and _REQUEST_ID_RE.fullmatch(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = [(k, v) for (k, v) in message.get("headers", []) if k.lower() != REQUEST_ID_HEADER.lower().encode()]
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_id)


def _header(scope: Mapping[str, Any], name: str) -> Optional[str]:
    target = name.encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == target:
            try:
                return value.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or uuid.uuid4().hex)


def _error_response(request: Request, status_code: int, code: DiagnosticCode, message: str, headers: Optional[Mapping[str, str]] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code.value, "message": message, "request_id": _request_id(request)},
        headers=dict(headers or {}),
    )


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name!r} is not allowed")


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- per-request checks -------------------------------------------------------------

def _authenticate(request: Request, settings: ServiceSettings) -> str:
    """Return the presented bearer token after a constant-time comparison; raise 401 otherwise."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HttpError(401, DiagnosticCode.UNAUTHENTICATED, "bearer token required", {"WWW-Authenticate": "Bearer"})
    if not hmac.compare_digest(token.encode("utf-8"), settings.service_token.encode("utf-8")):
        raise HttpError(401, DiagnosticCode.UNAUTHENTICATED, "invalid bearer token", {"WWW-Authenticate": "Bearer"})
    return token


def _rate_limit(limiter: TokenBucketLimiter, token: str) -> None:
    if not limiter.try_acquire(_token_key(token)):
        raise HttpError(429, DiagnosticCode.RATE_LIMITED, "rate limit exceeded for this token", {"Retry-After": "1"})


async def _read_body(request: Request, max_bytes: int) -> bytes:
    """Read the body without ever buffering more than ``max_bytes`` (+ one chunk)."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
        except ValueError:
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "invalid Content-Length header") from None
        if length > max_bytes:
            raise HttpError(413, DiagnosticCode.PAYLOAD_TOO_LARGE, f"request body exceeds {max_bytes} bytes")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HttpError(413, DiagnosticCode.PAYLOAD_TOO_LARGE, f"request body exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_envelope(body: bytes, allowed_keys: frozenset[str], required_keys: frozenset[str]) -> dict[str, Any]:
    """Parse the request body as a strict JSON object with a closed key set."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "request body is not UTF-8") from None
    try:
        obj = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=strict_object_pairs)
    except RecursionError:
        raise HttpError(400, DiagnosticCode.TOO_DEEP, "request body nesting is too deep") from None
    except ValueError:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "request body is not valid JSON (or repeats a key)") from None
    if not isinstance(obj, dict):
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "request body must be a JSON object")
    if _holds_lone_surrogate(obj):
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "request body holds a lone surrogate escape: it is not valid Unicode text")
    _reject_self_certification(obj, "request body")
    unknown = sorted(set(obj) - allowed_keys)
    if unknown:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"unexpected key(s) in request body: {', '.join(unknown)}")
    missing = sorted(required_keys - set(obj))
    if missing:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"missing key(s) in request body: {', '.join(missing)}")
    return obj


def _holds_lone_surrogate(obj: Any) -> bool:
    """Whether any key or string value of the parsed body holds a lone surrogate (JSON accepts ``"\\ud800"``; Unicode text
    cannot hold it, and every later UTF-8 encoding of it would raise). An iterative walk, bounded by the parsed body."""
    stack: list[Any] = [obj]
    while stack:
        node = stack.pop()
        items: list[Any] = []
        if isinstance(node, dict):
            items = [*node.keys(), *node.values()]
        elif isinstance(node, list):
            items = node
        elif isinstance(node, str):
            try:
                node.encode("utf-8")
            except UnicodeEncodeError:
                return True
            continue
        stack.extend(i for i in items if isinstance(i, (dict, list, str)))
    return False


def _reject_self_certification(obj: Mapping[str, Any], where: str) -> None:
    found = sorted(SELF_CERTIFICATION_KEYS & set(obj))
    if found:
        raise HttpError(
            400, DiagnosticCode.SELF_CERTIFICATION_REJECTED,
            f"self-certification field(s) are not accepted in the {where}: {', '.join(found)}; "
            "verification status is issued only by the engine",
        )


def _asserted_verified_paths(obj: Any, limit: int = 8) -> list[str]:
    """Paths of every nested ``"verified": true`` in ``obj`` (iterative walk; bounded output)."""
    found: list[str] = []
    stack: list[tuple[Any, str]] = [(obj, "problem")]
    while stack and len(found) < limit:
        node, path = stack.pop()
        if isinstance(node, dict):
            if node.get("verified") is True:
                found.append(f"{path}.verified")
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    stack.append((value, f"{path}.{key}"))
        elif isinstance(node, list):
            for i, value in enumerate(node):
                if isinstance(value, (dict, list)):
                    stack.append((value, f"{path}[{i}]"))
    return sorted(found)


def _reject_nested_self_certification(problem: Mapping[str, Any]) -> None:
    """A client may not assert that a grounding was verified: only deterministic checks set it."""
    paths = _asserted_verified_paths(problem)
    if paths:
        raise HttpError(
            400, DiagnosticCode.SELF_CERTIFICATION_REJECTED,
            f"self-certification is not accepted in the problem: grounding.verified=true at {', '.join(paths)}; "
            "grounding is verified only by deterministic checks, never asserted by the caller",
        )


def _parse_config(raw: Any) -> SolverConfig:
    if raw is None:
        return SolverConfig()
    if not isinstance(raw, dict):
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'config' must be a JSON object")
    reserved = sorted(SERVER_CONTROLLED_CONFIG_KEYS & set(raw))
    if reserved:
        raise HttpError(
            400, DiagnosticCode.SCHEMA_VIOLATION,
            f"'config' option(s) {', '.join(reserved)} are server-controlled and cannot be set by clients",
        )
    try:
        return SolverConfig.model_validate(raw, strict=True)  # strict: true is no timeout and "100" no integer
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in err.get("loc", ())) or "config" for err in exc.errors())
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"'config' is invalid at: {fields}") from None


def _parse_policy(envelope: Mapping[str, Any]) -> str:
    """The engine policy a request names (``linear`` when absent): exactly one of ``NAMED_POLICIES``, by exact type and
    spelling. Anything else (another name, a case or whitespace variant, null, a number, an object of limits) is 400
    E100 naming the known policies, and nothing is run; the refused value is never echoed."""
    policy = envelope.get("policy", LINEAR)
    if type(policy) is not str or policy not in NAMED_POLICIES:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"'policy' must be one of: {', '.join(sorted(NAMED_POLICIES))}")
    return policy


@contextlib.asynccontextmanager
async def _solver_slot(semaphore: asyncio.Semaphore) -> AsyncIterator[None]:
    """Admit a solver run only when a slot is free right now; never queue."""
    if semaphore.locked():
        raise HttpError(503, DiagnosticCode.CONCURRENCY_LIMITED, "verification capacity is exhausted; retry later", {"Retry-After": "1"})
    await semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


def _guarded(handler: Handler) -> Handler:
    """Turn ``HttpError`` into its JSON response and anything else into a bare 500."""

    async def wrapped(request: Request) -> JSONResponse:
        started = time.perf_counter()
        try:
            response = await handler(request)
        except HttpError as exc:
            response = _error_response(request, exc.status_code, exc.code, exc.message, exc.headers)
        except Exception as exc:  # noqa: BLE001 - boundary: never leak internals
            log.warning(
                "request_id=%s path=%s unhandled error type=%s",
                _request_id(request), request.url.path, type(exc).__name__,
            )
            response = _error_response(request, 500, DiagnosticCode.INTERNAL, "internal error")
        log.info(
            "request_id=%s path=%s http_status=%d elapsed_ms=%.1f",
            _request_id(request), request.url.path, response.status_code, (time.perf_counter() - started) * 1000.0,
        )
        return response

    return wrapped


# --- application --------------------------------------------------------------------

def _registered_adapter_ids() -> frozenset[str]:
    """The closed allowlist of ``adapter_id`` values: the adapters the package registers when it is imported. Built once,
    when the app is created; an empty set when the adapters cannot be imported (the route then answers 501)."""
    try:
        importlib.import_module("epinoic_logic.adapters")
        base = importlib.import_module("epinoic_logic.adapters.base")
        return frozenset(i for i in base.registered_ids() if isinstance(i, str) and _ADAPTER_ID_RE.fullmatch(i))
    except Exception:  # noqa: BLE001 - a broken adapters package leaves the allowlist empty; the solver routes stay up
        return frozenset()


def _versions() -> dict[str, str]:
    return {
        "ir_version": IR_VERSION,
        "engine_version": ENGINE_VERSION,
        "policy_version": POLICY_VERSION,
        "translator_version": TRANSLATOR_VERSION,
        "z3_version": z3_version(),
    }


def create_app(settings: Optional[ServiceSettings] = None, *, clock: Callable[[], float] = time.monotonic) -> FastAPI:
    """Build the FastAPI application. ``settings`` defaults to :meth:`ServiceSettings.from_env`.

    The returned app exposes ``app.state.settings``, ``app.state.semaphore`` and
    ``app.state.rate_limiter`` for tests and operators. Interactive API docs are
    disabled: this is an internal service.
    """
    cfg = settings if settings is not None else ServiceSettings.from_env()
    app = FastAPI(title="Epinoic logic verification service", version=ENGINE_VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = cfg
    app.state.semaphore = asyncio.Semaphore(cfg.max_concurrency)
    app.state.rate_limiter = TokenBucketLimiter(cfg.rate_per_minute, clock)
    app.state.adapter_ids = _registered_adapter_ids()
    app.add_middleware(RequestIdMiddleware)

    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.warning("request_id=%s path=%s unhandled error type=%s", _request_id(request), request.url.path, type(exc).__name__)
        return _error_response(request, 500, DiagnosticCode.INTERNAL, "internal error")

    app.add_exception_handler(Exception, _unhandled)

    def admit(request: Request) -> str:
        token = _authenticate(request, cfg)
        _rate_limit(app.state.rate_limiter, token)
        return token

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        """Liveness probe. Unauthenticated; reports component versions and nothing else."""
        return JSONResponse({"ok": True, "versions": _versions()})

    async def post_verify(request: Request) -> JSONResponse:
        admit(request)
        body = await _read_body(request, cfg.max_body_bytes)
        envelope = _parse_envelope(body, _VERIFY_ENVELOPE_KEYS, frozenset({"problem"}))
        problem = envelope["problem"]
        if not isinstance(problem, dict):
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'problem' must be a JSON object")
        _reject_self_certification(problem, "problem")
        _reject_nested_self_certification(problem)
        config = _parse_config(envelope.get("config"))
        policy = _parse_policy(envelope)
        try:
            limits, config = named_policy(policy, config)
        except UnknownPolicyError:  # unreachable after _parse_policy; a problem is never run under another policy
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"'policy' must be one of: {', '.join(sorted(NAMED_POLICIES))}") from None
        async with _solver_slot(app.state.semaphore):
            result: VerificationResult = await asyncio.to_thread(
                verify, problem, config, limits, cfg.signing_key, cfg.signing_key_id,
            )
        log.info(
            "request_id=%s path=%s policy=%s result_status=%s claim_id=%s result_id=%s",
            _request_id(request), request.url.path, policy, result.status.value, result.claim_id, result.result_id,
        )
        return JSONResponse(result.model_dump(mode="json"))

    async def post_verify_signature(request: Request) -> JSONResponse:
        admit(request)
        body = await _read_body(request, cfg.max_body_bytes)
        envelope = _parse_envelope(body, _SIGNATURE_ENVELOPE_KEYS, _SIGNATURE_ENVELOPE_KEYS)
        raw = envelope["result"]
        if not isinstance(raw, dict):
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'result' must be a JSON object")
        try:
            result = VerificationResult.model_validate(raw)
        except ValidationError:
            return JSONResponse({"valid": False, "reason": "result does not match the VerificationResult schema"})
        if cfg.signing_key is None:
            return JSONResponse({"valid": False, "reason": "this service has no signing key"})
        if not result.signature:
            return JSONResponse({"valid": False, "reason": "result is unsigned"})
        if result.signature_key_id != cfg.signing_key_id:
            return JSONResponse({"valid": False, "reason": "unknown signature key id"})
        form = signature_form(result, cfg.signing_key)
        if form == FORM_BOUND:
            return JSONResponse({"valid": True})
        if form == FORM_LEGACY:
            # a record of an earlier build: signed with this service's key over its content, never over the key id it names
            # (repair round 3, INV-6), so the id is reported as not attested
            return JSONResponse({"valid": True, "key_id_attested": False,
                                 "reason": "signed in an earlier build's form, which does not cover the key id: the key id is not attested"})
        return JSONResponse({"valid": False, "reason": "signature does not match the result content"})

    async def post_release_check(request: Request) -> JSONResponse:
        admit(request)
        body = await _read_body(request, cfg.max_body_bytes)
        envelope = _parse_envelope(body, _RELEASE_ENVELOPE_KEYS, frozenset({"result"}))
        raw = envelope["result"]
        if not isinstance(raw, dict):
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'result' must be a JSON object")
        policy = _parse_policy(envelope)
        current = compute_versions().model_dump(mode="json")
        try:
            result = VerificationResult.model_validate(raw)
        except ValidationError:
            return JSONResponse({"eligible": False, "reasons": ["result does not match the VerificationResult schema"], "current": current})
        problem: Optional[Problem] = None
        if envelope.get("problem") is not None:
            if not isinstance(envelope["problem"], dict):
                raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'problem' must be a JSON object")
            try:
                problem = Problem.model_validate(envelope["problem"])
            except ValidationError:
                return JSONResponse({"eligible": False, "reasons": ["problem does not match the Problem schema"], "current": current})
        check = release_check(result, problem, signing_key=cfg.signing_key, key_id=cfg.signing_key_id, required_limits=RELEASE_POLICIES[policy])
        log.info("request_id=%s path=%s release_eligible=%s result_id=%s", _request_id(request), request.url.path, check.eligible, result.result_id)
        return JSONResponse({**check.as_dict(), "current": current})

    async def post_outcomes(request: Request) -> JSONResponse:
        admit(request)
        if not cfg.allow_client_fixtures:
            raise HttpError(403, DiagnosticCode.CLIENT_FIXTURES_DISABLED,
                            "client fixtures disabled: this service does not take a client's fixture_responses as the translation provider")
        body = await _read_body(request, cfg.max_body_bytes)
        envelope = _parse_envelope(body, _OUTCOME_ENVELOPE_KEYS, frozenset({"report", "claim_id", "fixture_responses"}))
        # The translation layer is imported lazily so the solver routes stay available even
        # when the pipeline (built by another work stream) is missing or broken.
        try:
            contracts = importlib.import_module("epinoic_logic.translate.contracts")
            pipeline = importlib.import_module("epinoic_logic.translate.pipeline")
            outcome_mod = importlib.import_module("epinoic_logic.translate.outcome")
            fixture_mod = importlib.import_module("epinoic_logic.translate.providers.fixture")
        except ImportError:
            raise HttpError(501, DiagnosticCode.INTERNAL, "the claim outcome pipeline is not available in this build") from None
        if not isinstance(envelope["report"], dict):
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'report' must be a JSON object")
        try:
            # strict, as the IR is: "yes" is no boolean and "1" no integer (the body is JSON, so strings stay valid for
            # enumerations and literals)
            report = contracts.SpecialistReport.model_validate_json(json.dumps(envelope["report"]), strict=True)
        except ValidationError:
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'report' does not match the SpecialistReport contract") from None
        claim_id = envelope["claim_id"]
        if not isinstance(claim_id, str):
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'claim_id' must be a string")
        claim = next((c for c in report.claims if c.claim_id == claim_id), None)
        if claim is None:
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'claim_id' is not a claim of the report")
        fixture_responses = envelope["fixture_responses"]
        if not isinstance(fixture_responses, dict):
            raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'fixture_responses' must be an object keyed by claim_id")
        structural: list[Any] = []
        adapter_id = envelope.get("adapter_id")
        if adapter_id is not None:
            # The allowlist is closed and was built when the app was created: an id is checked before anything is
            # imported, so a request can never make the service probe or import a module by name.
            if type(adapter_id) is not str or not _ADAPTER_ID_RE.fullmatch(adapter_id):
                raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'adapter_id' must be a registered adapter id ([a-z0-9_.-], at most 64 characters)")
            if not app.state.adapter_ids:
                raise HttpError(501, DiagnosticCode.INTERNAL, "specialist adapters are not available in this build")
            if adapter_id not in app.state.adapter_ids:
                raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "unknown adapter_id")
            try:
                adapters_base = importlib.import_module("epinoic_logic.adapters.base")  # already imported when the allowlist was built
                adapter = adapters_base.get_adapter(adapter_id)
            except (ImportError, KeyError, LookupError, ValueError):
                raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "unknown adapter_id") from None
            structural = list(adapter.structural_checks(report))

        def run() -> Any:
            translator = pipeline.Translator(fixture_mod.FixtureTranslationProvider(fixture_responses))
            return outcome_mod.verify_claim(
                claim, report, translator, structural=structural, config=SolverConfig(),
                signing_key=cfg.signing_key, key_id=cfg.signing_key_id,
            )

        async with _solver_slot(app.state.semaphore):
            outcome = await asyncio.to_thread(run)
        log.info(
            "request_id=%s path=%s display_status=%s claim_id=%s outcome_id=%s",
            _request_id(request), request.url.path, outcome.display_status.value, claim_id, outcome.outcome_id,
        )
        return JSONResponse(outcome.model_dump(mode="json"))

    app.add_api_route("/v1/verify", _guarded(post_verify), methods=["POST"])
    app.add_api_route("/v1/results/verify-signature", _guarded(post_verify_signature), methods=["POST"])
    app.add_api_route("/v1/results/release-check", _guarded(post_release_check), methods=["POST"])
    app.add_api_route("/v1/outcomes", _guarded(post_outcomes), methods=["POST"])
    return app
