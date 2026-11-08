"""Public API of the translator, stem: the STEM front end: the shared document, its layout readings, the expression nodes and unit dimensions the overseer re-derives a STEM receipt from.

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'ANNOTATION_ONLY_LINEAR_RE': ('epinoic_logic.stem.layout', 'ANNOTATION_ONLY_LINEAR_RE'),
    'Abs': ('epinoic_logic.stem.nodes', 'Abs'),
    'BinOp': ('epinoic_logic.stem.nodes', 'BinOp'),
    'MARK_ALLOC': ('epinoic_logic.stem.layout', 'MARK_ALLOC'),
    'MARK_CODE': ('epinoic_logic.stem.layout', 'MARK_CODE'),
    'Neg': ('epinoic_logic.stem.nodes', 'Neg'),
    'Num': ('epinoic_logic.stem.nodes', 'Num'),
    'PART_LEAD_RE': ('epinoic_logic.stem.layout', 'PART_LEAD_RE'),
    'Pow': ('epinoic_logic.stem.nodes', 'Pow'),
    'Sym': ('epinoic_logic.stem.nodes', 'Sym'),
    'TABLE_SEPARATOR_RE': ('epinoic_logic.stem.layout', 'TABLE_SEPARATOR_RE'),
    'annotation_ranges': ('epinoic_logic.stem.layout', 'annotation_ranges'),
    'build_document': ('epinoic_logic.stem', 'build_document'),
    'parse_data_tables': ('epinoic_logic.stem.datatables', 'parse_data_tables'),
    'unit_dimension': ('epinoic_logic.stem.units', 'unit_dimension'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
