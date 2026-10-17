"""The Epinoic AI flash router: a separate, independent agent that plans how the overseer reviews each specialist output.

It talks to the translator's service only through the router port ``epinoic.integration.router-port.v1``
(``integration/PROTOCOL.md`` section 7a of the translator repository): :func:`epinoic_flash_router.port.hello` and
:func:`epinoic_flash_router.port.plan`, JSON text in and JSON text out. The service runs it in its own process, with
no key, secret or token in its environment, validates everything it answers as untrusted data and enforces its own
minimum-oversight floor whatever the plan says: this router can add oversight, never remove it.

Standard library only. Nothing here imports the translator, the engine or Z3, so this sub-project is edited, tested and
released on its own; its identity (name, version, the digests of its rules and of its cost model) changes whenever
its behaviour can.
"""
__version__ = "0.1.0"

__all__ = ["__version__"]
