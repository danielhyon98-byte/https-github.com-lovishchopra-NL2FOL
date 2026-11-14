"""The router port of the flash router (``epinoic.integration.router-port.v1``): the in-process API, JSON text in and
JSON text out, deterministic (the same request and the same data give the same plan text).

For the translator's checks service (``integration/PROTOCOL.md`` section 7a):

* :func:`hello` returns one ``epinoic.integration.router-hello.v1`` document: the router's identity (name, version, the
  digests of its rules and of its cost data), the methods it plans, the profiles it knows, the cheapest tier and
  ``deterministic: true``;
* :func:`plan` takes one ``epinoic.integration.routing-request.v1`` document and returns one
  ``epinoic.integration.routing-plan.v1`` document.

For the overseer pool (section 7b, pool port 1.2 since 0.3.0, 1.1 still answered), which attaches the router by this
capability:

* :func:`pool_hello` returns one ``epinoic.integration.pool-router-hello.v1`` document: the same identity, the capability
  ``pool-plan``, the pool port version (1.2 with the flash decision maker's data, 1.1 over a rules/2 data directory), the
  methods a pool dossier may be reviewed by (``N_FOLD`` for a combined answer at 1.2), the profiles, the cheapest tier;
* :func:`pool_plan` takes one ``epinoic.integration.pool-routing-request.v1`` document and returns one
  ``epinoic.integration.pool-routing-plan.v1`` document of the request's own version (at 1.2 with every dossier's
  decision record and N_FOLD for every combined answer).

The service attaches this module with ``EPINOIC_FLASH_ROUTER=epinoic_flash_router.port``, the overseer pool by naming it
(``OverseerPool(..., router="epinoic_flash_router.port")``); both run it in a process of its own, with a time limit and
an environment that holds no key, secret or token, validate everything it answers as untrusted data, and run their own
minimum-oversight floor whenever its plan is out of contract or below that floor. :class:`FlashRouter` is the same API
over another data directory (a re-tuned copy being tried). Standard library only.

A request this router does not read (not JSON text, or a member the planners read out of the type or range the router
port gives it: :mod:`epinoic_flash_router.contract`) is refused with :class:`RequestError` (a ``ValueError``) naming the
member and the rule, before anything is planned. Any other exception :func:`plan` or :func:`pool_plan` raises is a fault
of the router's own code, never of the request: the runner (``python -m epinoic_flash_router_cli``) reports the first as
exit status 3 and the second as exit status 4.
"""
from __future__ import annotations

from typing import Optional

from . import __version__
from .contract import RequestError, decode
from .planner import plan_for
from .pool import pool_plan_for
from .rules import DEFAULT, DataSet, canonical

__all__ = ["NAME", "IDENTITY", "FlashRouter", "RequestError", "hello", "plan", "pool_hello", "pool_plan"]

NAME = "epinoic-flash-router"
_PROTOCOL = "epinoic.integration.v1"


class FlashRouter:
    """The flash router over one data directory (the package's own by default): the four operations of the router port,
    JSON text in and JSON text out. Pure: everything it reads was loaded with its data."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data: DataSet = DEFAULT if data_dir is None else DataSet(data_dir)
        self.identity: dict[str, str] = {"name": NAME, "version": __version__, "rules_sha256": self.data.rules_sha256,
                                         "cost_data_sha256": self.data.cost_data_sha256}

    def hello(self) -> str:
        """The service's hello (``router-hello.v1``)."""
        return canonical({"schema": "epinoic.integration.router-hello.v1", "protocol": _PROTOCOL, "port_version": "1.0",
                          "router": dict(self.identity), "methods": ["IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"],
                          "profiles": ["standard", "fast"], "tier": "cheapest", "deterministic": True})

    def plan(self, request_json: str) -> str:
        """The service's plan (``routing-plan.v1``) for one routing request. :class:`RequestError` when the text is not a
        request this router reads."""
        return canonical(plan_for(decode(request_json), identity=self.identity, data=self.data))

    def pool_hello(self) -> str:
        """The overseer pool's hello (``pool-router-hello.v1``): the ``pool-plan`` capability at pool port 1.2 (N_FOLD for a
        combined answer, a decision record for every dossier) when the data carry the flash decision maker, else at 1.1."""
        v12 = self.data.decision is not None
        return canonical({"schema": "epinoic.integration.pool-router-hello.v1", "protocol": _PROTOCOL, "port_version": "1.2" if v12 else "1.1",
                          "router": dict(self.identity), "capabilities": ["pool-plan"],
                          "methods": ["IN_DEPTH", "DUPLICATE", "N_FOLD"] if v12 else ["IN_DEPTH", "DUPLICATE"],
                          "profiles": ["standard", "fast"], "tier": "cheapest", "deterministic": True})

    def pool_plan(self, request_json: str) -> str:
        """The overseer pool's plan (``pool-routing-plan.v1``) for one batch. :class:`RequestError` when the text is not a
        request this router reads."""
        return canonical(pool_plan_for(decode(request_json), identity=self.identity, data=self.data))


_ROUTER = FlashRouter()
#: This release's identity: its name, its version and the digests of its current rules and cost data.
IDENTITY: dict[str, str] = dict(_ROUTER.identity)


def hello() -> str:
    """This router's hello (``router-hello.v1``), as canonical JSON text."""
    return _ROUTER.hello()


def plan(request_json: str) -> str:
    """The plan (``routing-plan.v1``) for one routing request, as canonical JSON text. The same request text always gives
    the same plan text. :class:`RequestError` (a ``ValueError``) when the text is not a request this router reads."""
    return _ROUTER.plan(request_json)


def pool_hello() -> str:
    """This router's pool hello (``pool-router-hello.v1``), as canonical JSON text."""
    return _ROUTER.pool_hello()


def pool_plan(request_json: str) -> str:
    """The pool plan (``pool-routing-plan.v1``) for one overseer-pool batch, as canonical JSON text. The same request text
    always gives the same plan text. :class:`RequestError` (a ``ValueError``) when the text is not a request this router
    reads."""
    return _ROUTER.pool_plan(request_json)
