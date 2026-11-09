"""Public API of the translator, ir: the IR 1.0 schema and its canonical digests (the overseer re-validates every problem it reads and binds every result to the digest of the exact problem).

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'ALLOWED_OPS': ('epinoic_logic.ir.schema', 'ALLOWED_OPS'),
    'Assertion': ('epinoic_logic.ir.schema', 'Assertion'),
    'DEFAULT_LIMITS': ('epinoic_logic.ir.schema', 'DEFAULT_LIMITS'),
    'Expr': ('epinoic_logic.ir.schema', 'Expr'),
    'IntConst': ('epinoic_logic.ir.schema', 'IntConst'),
    'Limits': ('epinoic_logic.ir.schema', 'Limits'),
    'Problem': ('epinoic_logic.ir.schema', 'Problem'),
    'RealConst': ('epinoic_logic.ir.schema', 'RealConst'),
    'SourceRef': ('epinoic_logic.ir.schema', 'SourceRef'),
    'canonical_json': ('epinoic_logic.ir.canonical', 'canonical_json'),
    'problem_digest': ('epinoic_logic.ir.canonical', 'problem_digest'),
    'sha256_hex': ('epinoic_logic.ir.canonical', 'sha256_hex'),
    'strict_object_pairs': ('epinoic_logic.ir.canonical', 'strict_object_pairs'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
