"""Authenticated HTTP boundary around the verification engine.

The service is the only way other components (the Overseer, the backend) reach the
solver. It enforces, in this order for every ``/v1`` request:

1. bearer authentication (constant-time comparison)            -> 401 ``E502``
2. a per-token token bucket                                     -> 429 ``E503``
3. the request-body size limit, checked before the body is read -> 413 ``E306``
4. strict JSON envelope parsing (no NaN, object only)           -> 400 ``E100``
5. rejection of self-certification fields                       -> 400 ``E505``
6. bounded solver concurrency (non-blocking admission)          -> 503 ``E504``

Solver runs happen in a worker thread so the event loop stays responsive. Every
response carries ``X-Request-Id`` (echoed from the request when well formed,
otherwise generated). Error bodies are small JSON objects ``{code, message,
request_id}``; they never contain stack traces, exception text or the request
body. Logs record metadata only (request id, path, HTTP status, result status,
elapsed time) and never any payload content.

Endpoints
---------
``GET  /healthz``                       liveness; unauthenticated; component versions only
``POST /v1/verify``                     ``{problem, config?}`` -> signed ``VerificationResult``
``POST /v1/results/verify-signature``   ``{result}`` -> ``{valid: bool, reason?}``
``POST /v1/outcomes``                   ``{report, claim_id, fixture_responses, adapter_id?}``
                                        -> ``ClaimVerificationOutcome`` (fixture provider only;
                                        model providers are wired by configuration later)

An invalid or unsupported problem is NOT an HTTP error: it is a bound, signed result
with status ``INVALID_FORMALIZATION`` or ``UNSUPPORTED`` (HTTP 200), so callers
always receive an auditable record. HTTP errors are reserved for the envelope and
for admission control.
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
from ..engine.provenance import verify_signature, z3_version
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify
from ..ir.schema import DEFAULT_LIMITS
from ..version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION
from .settings import ServiceSettings

__all__ = [
    "REQUEST_ID_HEADER",
    "SELF_CERTIFICATION_KEYS",
    "HttpError",
    "TokenBucketLimiter",
    "RequestIdMiddleware",
    "create_app",
]

log = logging.getLogger("epinoic_logic.service")

REQUEST_ID_HEADER = "X-Request-Id"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

#: Keys a client might use to assert a verification verdict about its own payload.
#: They are refused outright (400 ``E505``): status comes only from the engine.
SELF_CERTIFICATION_KEYS: frozenset[str] = frozenset({
    "advisory_verification_status", "verified", "self_certified", "status",
})
_VERIFY_ENVELOPE_KEYS = frozenset({"problem", "config"})
_SIGNATURE_ENVELOPE_KEYS = frozenset({"result"})
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
        request_id = incoming if incoming and _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
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
        obj = json.loads(text, parse_constant=_reject_constant)
    except RecursionError:
        raise HttpError(400, DiagnosticCode.TOO_DEEP, "request body nesting is too deep") from None
    except ValueError:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "request body is not valid JSON") from None
    if not isinstance(obj, dict):
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "request body must be a JSON object")
    _reject_self_certification(obj, "request body")
    unknown = sorted(set(obj) - allowed_keys)
    if unknown:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"unexpected key(s) in request body: {', '.join(unknown)}")
    missing = sorted(required_keys - set(obj))
    if missing:
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"missing key(s) in request body: {', '.join(missing)}")
    return obj


def _reject_self_certification(obj: Mapping[str, Any], where: str) -> None:
    found = sorted(SELF_CERTIFICATION_KEYS & set(obj))
    if found:
        raise HttpError(
            400, DiagnosticCode.SELF_CERTIFICATION_REJECTED,
            f"self-certification field(s) are not accepted in the {where}: {', '.join(found)}; "
            "verification status is issued only by the engine",
        )


def _parse_config(raw: Any) -> SolverConfig:
    if raw is None:
        return SolverConfig()
    if not isinstance(raw, dict):
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'config' must be a JSON object")
    try:
        return SolverConfig.model_validate(raw)
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in err.get("loc", ())) or "config" for err in exc.errors())
        raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, f"'config' is invalid at: {fields}") from None


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
        config = _parse_config(envelope.get("config"))
        async with _solver_slot(app.state.semaphore):
            result: VerificationResult = await asyncio.to_thread(
                verify, problem, config, DEFAULT_LIMITS, cfg.signing_key, cfg.signing_key_id,
            )
        log.info(
            "request_id=%s path=%s result_status=%s claim_id=%s result_id=%s",
            _request_id(request), request.url.path, result.status.value, result.claim_id, result.result_id,
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
        if verify_signature(result, cfg.signing_key):
            return JSONResponse({"valid": True})
        return JSONResponse({"valid": False, "reason": "signature does not match the result content"})

    async def post_outcomes(request: Request) -> JSONResponse:
        admit(request)
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
            report = contracts.SpecialistReport.model_validate(envelope["report"])
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
            if not isinstance(adapter_id, str):
                raise HttpError(400, DiagnosticCode.SCHEMA_VIOLATION, "'adapter_id' must be a string")
            try:
                importlib.import_module("epinoic_logic.adapters")
                adapters_base = importlib.import_module("epinoic_logic.adapters.base")
            except ImportError:
                raise HttpError(501, DiagnosticCode.INTERNAL, "specialist adapters are not available in this build") from None
            try:
                adapter = adapters_base.get_adapter(adapter_id)
            except (KeyError, LookupError, ValueError):
                # The registry may be populated only when the adapter's own module is imported.
                with contextlib.suppress(ImportError):
                    importlib.import_module(f"epinoic_logic.adapters.{adapter_id.replace('-', '_')}")
                try:
                    adapter = adapters_base.get_adapter(adapter_id)
                except (KeyError, LookupError, ValueError):
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
    app.add_api_route("/v1/outcomes", _guarded(post_outcomes), methods=["POST"])
    return app
