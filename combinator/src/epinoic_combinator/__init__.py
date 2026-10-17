"""Epinoic AI combinator: a separate agent that combines the specialists' answers to one request into one synthesis.

The combinator is its own sub-project (``combinator/`` of the translator repository, package ``epinoic_combinator``,
its own ``pyproject.toml``, version, instructions, tests and release). It needs nothing but the Python standard library
at run time and never imports the translator, the engine or Z3. It meets the translator only through the integration
protocol's combinator port (``epinoic.integration.combinator-port.v1``) and the published synthesis contract, a copy of
which travels with the package (``contract/``, written by the translator's ``integration/tools/generate.py``).

* :mod:`.pack`: the combinator agent's instructions (package data, pinned by digest) and their identity;
* :mod:`.export`: ``python -m epinoic_combinator.export --out <dir>`` writes those instructions for a workflow or a
  provider to use;
* :mod:`.runner`: runs the agent as a sub-agent on the cheapest tier through a provider interface (:mod:`.providers`:
  the interface and deterministic fakes; no live provider is in this release) and validates every output against the
  published contract (:mod:`.contract`) before it leaves: an output out of contract is a named refusal, never an
  exception;
* :mod:`.port`: what the translator's service attaches, ``hello()`` and ``combine(input_json)``.

A check here is a contract check, never a faithfulness check: the translator's hub stays the independent checker of
every synthesis, and nothing the combinator says about its own work is trusted.
"""
from __future__ import annotations

__all__ = ["NAME", "__version__"]

NAME = "epinoic-combinator"
__version__ = "0.1.1"
