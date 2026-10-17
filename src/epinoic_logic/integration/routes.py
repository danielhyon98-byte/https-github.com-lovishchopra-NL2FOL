"""The two routes of the integration profiles (``integration/PROTOCOL.md`` sections 3 and 5).

``GET /v1/capabilities`` and ``POST /v1/turns/check`` are installed only when the service runs under an integration
profile; the ``engine`` profile exposes no new route. Both routes go through the service's existing gates unchanged:
bearer authentication (401 E502), the per-token rate limit (429 E503), the body-size limit read before the body
(413 E306), strict JSON with a closed key set (400 E100), self-certification refusal (400 E505) and non-blocking
concurrency (503 E504). A request that passes them and is out of contract is answered 400 with its ``KIT-REQ`` code.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .checks_port import check_request
from .errors import IntegrationError

__all__ = ["TURN_CHECK_KEYS", "install_routes"]

log = logging.getLogger("epinoic_logic.integration")

#: The top-level keys of ``epinoic.integration.turn-check.v1``.
TURN_CHECK_KEYS = frozenset({"schema", "protocol", "mode", "ids", "task", "answers", "policy", "budget_ms", "revision_of"})
_REQUIRED = frozenset({"schema", "protocol", "mode", "ids", "task", "answers", "policy", "budget_ms"})


def install_routes(app: FastAPI, runtime: Any, *, admit: Callable[[Request], str], read_body: Any, parse_envelope: Any,
                   guarded: Any, solver_slot: Any, request_id: Callable[[Request], str]) -> None:
    cfg = app.state.settings

    async def get_capabilities(request: Request) -> JSONResponse:
        admit(request)
        return JSONResponse(runtime.capabilities())

    async def post_turn_check(request: Request) -> JSONResponse:
        admit(request)
        body = await read_body(request, cfg.max_body_bytes)
        envelope = parse_envelope(body, TURN_CHECK_KEYS, _REQUIRED)
        try:
            req = check_request(envelope, runtime.request_limits, service_env=runtime.facts.settings.service_env)
        except IntegrationError as exc:
            log.info("request_id=%s path=%s refused=%s", request_id(request), request.url.path, exc.code)
            return JSONResponse(status_code=400, content={"code": exc.code, "message": exc.name, "request_id": request_id(request)})
        async with solver_slot(app.state.semaphore):
            verdict = await asyncio.to_thread(runtime.checker.check, req)
        log.info("request_id=%s path=%s decision=%s", request_id(request), request.url.path, verdict["delivery"]["decision"])
        return JSONResponse(verdict)

    app.add_api_route("/v1/capabilities", guarded(get_capabilities), methods=["GET"])
    app.add_api_route("/v1/turns/check", guarded(post_turn_check), methods=["POST"])
