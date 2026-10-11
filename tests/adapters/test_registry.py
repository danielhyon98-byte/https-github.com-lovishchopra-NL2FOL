"""Adapter registry and protocol."""
from __future__ import annotations

import importlib

import pytest

from epinoic_logic import adapters
from epinoic_logic.adapters import EnglishSpecialistAdapter, GenericStructuredAdapter, get_adapter, register, registered_ids
from epinoic_logic.adapters.base import REGISTRY, SpecialistAdapter


def test_built_in_adapters_are_registered_on_import():
    # Other specialist packages may register more ids; these two are always present.
    assert {"english-specialist", "generic-structured"} <= set(registered_ids())
    assert registered_ids() == sorted(registered_ids())
    assert isinstance(get_adapter("english-specialist"), EnglishSpecialistAdapter)
    assert isinstance(get_adapter("generic-structured"), GenericStructuredAdapter)


def test_registered_adapters_satisfy_the_protocol():
    for adapter in REGISTRY.values():
        assert isinstance(adapter, SpecialistAdapter)
        assert callable(adapter.parse_response) and callable(adapter.structural_checks)


def test_unknown_adapter_raises_key_error():
    with pytest.raises(KeyError):
        get_adapter("nobody")


def test_register_rejects_conflicts_and_bad_ids():
    existing = get_adapter("generic-structured")
    assert register(existing) is existing  # idempotent for the same object

    class Impostor:
        agent_id = "generic-structured"

        def parse_response(self, text, **kw):  # pragma: no cover - never called
            raise NotImplementedError

        def structural_checks(self, report):  # pragma: no cover - never called
            return []

    with pytest.raises(ValueError):
        register(Impostor())

    class Nameless:
        agent_id = ""

    with pytest.raises(ValueError):
        register(Nameless())  # type: ignore[arg-type]
    assert get_adapter("generic-structured") is existing


def test_service_style_lookup_by_module_path_works():
    """The service and CLI import ``epinoic_logic.adapters.<id with underscores>`` as a fallback."""
    for agent_id in ("english-specialist", "generic-structured"):
        module = importlib.import_module(f"epinoic_logic.adapters.{agent_id.replace('-', '_')}")
        assert module.ADAPTER is get_adapter(agent_id)
    assert adapters.AdapterError is importlib.import_module("epinoic_logic.adapters.base").AdapterError
