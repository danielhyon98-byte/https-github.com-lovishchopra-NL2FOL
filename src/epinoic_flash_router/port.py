"""The router port of the flash router (``epinoic.integration.router-port.v1``): what the translator's service calls.

* :func:`hello` returns one ``epinoic.integration.router-hello.v1`` document (JSON text): the router's identity (name,
  version, the digests of its rules and of its cost model), the methods it plans, the profiles it knows, the cheapest
  tier and ``deterministic: true``.
* :func:`plan` takes one ``epinoic.integration.routing-request.v1`` document (JSON text) and returns one
  ``epinoic.integration.routing-plan.v1`` document (JSON text).

The service attaches this module with ``EPINOIC_FLASH_ROUTER=epinoic_flash_router.port`` and calls it in a process of
its own, with a time limit and an environment that holds no key, secret or token. Everything returned is validated
there as untrusted data, and a plan below the service's minimum-oversight floor is refused (``KIT-RT-020``) while the
floor runs. Standard library only.
"""
from __future__ import annotations

import json

from . import __version__
from .planner import plan_for
from .rules import COST_DATA_SHA256, RULES_SHA256, canonical

__all__ = ["NAME", "IDENTITY", "hello", "plan"]

NAME = "epinoic-flash-router"
IDENTITY = {"name": NAME, "version": __version__, "rules_sha256": RULES_SHA256, "cost_data_sha256": COST_DATA_SHA256}
_HELLO = {
    "schema": "epinoic.integration.router-hello.v1", "protocol": "epinoic.integration.v1", "port_version": "1.0",
    "router": IDENTITY, "methods": ["IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"], "profiles": ["standard", "fast"],
    "tier": "cheapest", "deterministic": True,
}


def hello() -> str:
    """This router's hello (``router-hello.v1``), as canonical JSON text."""
    return canonical(_HELLO)


def plan(request_json: str) -> str:
    """The plan (``routing-plan.v1``) for one routing request, as canonical JSON text. The same request text always
    gives the same plan text."""
    return canonical(plan_for(json.loads(request_json), identity=IDENTITY))
