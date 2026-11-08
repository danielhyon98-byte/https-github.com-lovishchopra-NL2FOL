"""Public API of the translator, named: the named defects (argument and evidence diagnostics): codes, severities, caps and their order.

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'MAX_PER_RECEIPT': ('epinoic_logic.named', 'MAX_PER_RECEIPT'),
    'NAMED_CODES': ('epinoic_logic.named', 'NAMED_CODES'),
    'defect_of': ('epinoic_logic.named', 'defect_of'),
    'effective_severity': ('epinoic_logic.named', 'effective_severity'),
    'from_finding': ('epinoic_logic.named', 'from_finding'),
    'ordered': ('epinoic_logic.named', 'ordered'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
