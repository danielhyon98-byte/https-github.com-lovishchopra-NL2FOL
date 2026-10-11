"""History specialist adapter (heuristic parser, structural checks, engine fixtures).

The adapter instance is registered under ``agent_id`` ``history-specialist`` when
this module is imported; a conflicting registration raises, it is never swallowed.
"""
from __future__ import annotations

from ..base import register
from . import fixtures  # noqa: F401
from .parser import HistorySpecialistAdapter
from .structural import structural_checks

__all__ = ["HistorySpecialistAdapter", "ADAPTER", "structural_checks", "fixtures"]

#: The registered singleton (``agent_id`` ``history-specialist``).
ADAPTER = register(HistorySpecialistAdapter())
