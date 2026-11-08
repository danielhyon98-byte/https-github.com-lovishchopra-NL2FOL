"""Public API of the translator, branches: the router hub (``RouterHub``: its auditor attachment and the result types of its overseer operations, the revision issue among them), the branch registry and the generic and English parsers' readings the overseer re-derives.

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'AuditorNotAttached': ('epinoic_logic.branches.hub', 'AuditorNotAttached'),
    'EnglishParserWrapper': ('epinoic_logic.branches.registry', '_EnglishParserWrapper'),
    'GENERIC_MARK_ALLOC': ('epinoic_logic.branches.generic_parser', '_MARK_ALLOC'),
    'GENERIC_MARK_CODE': ('epinoic_logic.branches.generic_parser', '_MARK_CODE'),
    'HubClosed': ('epinoic_logic.branches.hub', 'HubClosed'),
    'HubReview': ('epinoic_logic.branches.hub', 'HubReview'),
    'PoolReview': ('epinoic_logic.branches.hub', 'PoolReview'),
    'RevisionIssue': ('epinoic_logic.branches.hub', 'RevisionIssue'),
    'RouterHub': ('epinoic_logic.branches.hub', 'RouterHub'),
    'absent_mentions': ('epinoic_logic.branches.packs', '_absent_mentions'),
    'default_registry': ('epinoic_logic.branches', 'default_registry'),
    'quote_key': ('epinoic_logic.branches.packs', '_quote_key'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
