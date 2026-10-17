"""The integration protocol ``epinoic.integration.v1``: the service side of the Z3 layer that sits ON TOP of the
specialist agents and their APIs (``integration/PROTOCOL.md``; the kit is ``integration/`` at the repository root).

Ports: the specialist port (the runtime's answer, wrapped and never changed), the checks port (required: Z3 and STEM
run on every answer before delivery), the overseer port (the overseer as a separate sub-project), the combinator port
(combined answers) and the flash-router port (how the overseer reviews; advisory, under a minimum-oversight floor).

This package imports nothing from the engine at import time: ``python -m epinoic_logic.integration serve`` checks for
Z3 with the standard library first (``KIT-HS-003 z3_unavailable``, exit status 2, no traceback) and only then imports the
engine. Results prove properties of the encoding only; a non-success is never shown as success.
"""
PROTOCOL = "epinoic.integration.v1"

__all__ = ["PROTOCOL"]
