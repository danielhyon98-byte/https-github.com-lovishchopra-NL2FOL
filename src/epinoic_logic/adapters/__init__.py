"""Specialist adapters: agent output -> immutable reports -> structural findings.

Importing this package registers the built-in adapters:

* ``generic-structured`` (:mod:`generic_structured`): the integration contract for
  every specialist that emits structured JSON reports;
* ``english-specialist`` (:mod:`english_specialist`): the worked example that parses
  analytical prose and applies the agent's own working rules;
* ``history-specialist`` (:mod:`history_specialist`): the History pack's heuristic
  parser and structural checks.

Look adapters up with :func:`get_adapter`; see :mod:`base` for the protocol.
"""
from __future__ import annotations

from . import english_specialist, generic_structured, history_specialist  # noqa: F401  (registration on import)
from .base import REGISTRY, AdapterError, SpecialistAdapter, get_adapter, register, registered_ids
from .english_specialist import EnglishSpecialistAdapter
from .generic_structured import GenericStructuredAdapter
from .history_specialist import HistorySpecialistAdapter

__all__ = [
    "AdapterError", "SpecialistAdapter", "REGISTRY", "register", "get_adapter", "registered_ids",
    "GenericStructuredAdapter", "EnglishSpecialistAdapter", "HistorySpecialistAdapter",
]
