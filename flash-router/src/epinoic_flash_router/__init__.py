"""The Epinoic AI flash router: a separate, independent agent that plans how the overseer reviews each specialist output
and each overseer-pool batch. It is the oversight planner's decision maker, not the translator's ``RouterHub`` (which
carries messages between agents) and not the website's subject routing (which picks a specialist).

It talks to the translator's checks service and to the overseer pool only through the router port
``epinoic.integration.router-port.v1`` (``integration/PROTOCOL.md`` sections 7a and 7b of the translator repository):
:mod:`epinoic_flash_router.port` (``hello``/``plan`` for the service, ``pool_hello``/``pool_plan`` for the pool), JSON text
in and JSON text out. Both callers run it in its own process, with no key, secret or token in that process's environment,
validate everything it answers as untrusted data and enforce their own minimum-oversight floor whatever the plan says:
this router can add oversight, never remove it. That process runs as the caller's user (a fault boundary, not a
sandbox: PROTOCOL.md section 7a), so this code is installed only as code trusted with that user.

Its rules (the features it reads, the thresholds, the method table, the batch sizes) and its cost data are versioned
data files with digests (``data/``, :mod:`epinoic_flash_router.rules`): the router is edited, re-tuned and released by
changing them, without touching the translator, the engine, the STEM support or the overseer. Standard library only;
nothing here imports the translator, the engine, Z3 or the overseer. Its identity (name, version, the digests of its
rules and of its cost data) changes whenever its behaviour can.
"""
__version__ = "0.4.0"

__all__ = ["__version__"]
