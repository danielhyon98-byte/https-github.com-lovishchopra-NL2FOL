"""Lazy resolution of the public API's names (PEP 562).

Each public module of :mod:`epinoic_logic.api` maps its public names to the internal module and attribute that implement
them. A name is resolved when it is imported (``from epinoic_logic.api.engine import verify``), every time it is imported,
so an import inside a function sees exactly what an import of the internal module would see at that moment. Nothing is
copied or cached here.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Mapping, Optional

__all__ = ["exports"]


def exports(module_name: str, table: Mapping[str, tuple[str, Optional[str]]]) -> tuple[list[str], Callable[[str], Any], Callable[[], list[str]]]:
    """``(__all__, __getattr__, __dir__)`` for the public module ``module_name`` exporting ``table``
    (public name -> (internal module, attribute); attribute None exports the internal module itself)."""
    names = sorted(table)

    def __getattr__(name: str) -> Any:
        try:
            internal, attribute = table[name]
        except KeyError:
            raise AttributeError(f"module {module_name!r} has no attribute {name!r} (not part of the public API)") from None
        module = importlib.import_module(internal)
        return module if attribute is None else getattr(module, attribute)

    def __dir__() -> list[str]:
        return list(names)

    return names, __getattr__, __dir__
