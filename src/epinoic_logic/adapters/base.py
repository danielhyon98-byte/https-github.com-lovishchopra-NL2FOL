"""Specialist adapter protocol and registry.

An adapter is the boundary between one subject-specialist agent and the
verification layer. It does two deterministic things:

* ``parse_response`` turns the agent's raw output into an immutable
  :class:`~epinoic_logic.translate.contracts.SpecialistReport` (original text plus
  its SHA-256, the supplied texts, and claim records with stable ids and roles).
* ``structural_checks`` runs code-only checks over a report and returns
  :class:`~epinoic_logic.translate.contracts.StructuralFinding` records (source
  integrity, claim-link integrity, structural working rules of the agent).

Adapters never decide verification status and never call a model. Anything an
adapter extracts from agent text is a proposal: claim roles, links and certainty
are advisory inputs to the deterministic eligibility policy, which ignores agent
self-reports.

Adapters are registered by ``agent_id`` so the service and the CLI can look them
up by name (``get_adapter``). Registration is explicit; importing
:mod:`epinoic_logic.adapters` registers the built-in adapters.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..translate.contracts import SpecialistReport, StructuralFinding, SuppliedText

__all__ = ["AdapterError", "SpecialistAdapter", "REGISTRY", "register", "get_adapter", "registered_ids"]


class AdapterError(ValueError):
    """The agent output could not be turned into a report.

    Messages describe the shape problem only; they never carry the agent text.
    """


@runtime_checkable
class SpecialistAdapter(Protocol):
    """What every specialist adapter provides."""

    agent_id: str

    def parse_response(
        self,
        text: str,
        *,
        request_id: str,
        task_id: str,
        report_id: str,
        subject: str,
        task_type: str,
        supplied_texts: list[SuppliedText],
        course_level: str = "unknown",
        agent_version: Optional[str] = None,
    ) -> SpecialistReport:
        """Build an immutable report from the agent's raw output ``text``."""
        ...

    def structural_checks(self, report: SpecialistReport) -> list[StructuralFinding]:
        """Deterministic findings over ``report`` (never solver results)."""
        ...


REGISTRY: dict[str, SpecialistAdapter] = {}


def register(adapter: SpecialistAdapter) -> SpecialistAdapter:
    """Register ``adapter`` under its ``agent_id`` and return it.

    Re-registering the same id with a different object raises ``ValueError`` so a
    stray import can never silently swap an adapter.
    """
    agent_id = getattr(adapter, "agent_id", None)
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("adapter must carry a non-empty string agent_id")
    existing = REGISTRY.get(agent_id)
    if existing is not None and existing is not adapter:
        raise ValueError(f"an adapter is already registered for agent_id {agent_id!r}")
    REGISTRY[agent_id] = adapter
    return adapter


def get_adapter(agent_id: str) -> SpecialistAdapter:
    """Return the adapter registered for ``agent_id``; ``KeyError`` when unknown."""
    try:
        return REGISTRY[agent_id]
    except KeyError:
        raise KeyError(f"no adapter registered for agent_id {agent_id!r}") from None


def registered_ids() -> list[str]:
    """Registered agent ids, sorted."""
    return sorted(REGISTRY)
