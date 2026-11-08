"""Public API of the translator, engine: the Z3 engine: verification, validation, compilation, named policies, provenance (signing and checking results), the release check, statuses and the scope statement, and the engine's version constants (the overseer re-runs every result it is shown on a fresh engine).

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'CapturedResult': ('epinoic_logic.engine.sink', 'CapturedResult'),
    'PACK_POLICIES': ('epinoic_logic.engine.policies', 'PACK_POLICIES'),
    'POLICY_VERSION': ('epinoic_logic.version', 'POLICY_VERSION'),
    'POSITIVE_STATUS': ('epinoic_logic.engine.release', 'POSITIVE_STATUS'),
    'SCOPE_STATEMENT': ('epinoic_logic.engine.statuses', 'SCOPE_STATEMENT'),
    'SolverConfig': ('epinoic_logic.engine.results', 'SolverConfig'),
    'TASK_GIVEN_KINDS': ('epinoic_logic.engine.authority', 'TASK_GIVEN_KINDS'),
    'VerificationResult': ('epinoic_logic.engine.results', 'VerificationResult'),
    'VerificationStatus': ('epinoic_logic.engine.statuses', 'VerificationStatus'),
    'assumed_grounding': ('epinoic_logic.engine.runner', 'assumed_grounding'),
    'binding_inconsistencies': ('epinoic_logic.engine.provenance', 'binding_inconsistencies'),
    'canonical_expr': ('epinoic_logic.engine.runner', '_canonical'),
    'capture_results': ('epinoic_logic.engine.sink', 'capture_results'),
    'circular_premises': ('epinoic_logic.engine.runner', 'circular_premises'),
    'compile_expr': ('epinoic_logic.engine.compiler', 'compile_expr'),
    'compile_problem': ('epinoic_logic.engine.compiler', 'compile_problem'),
    'compute_versions': ('epinoic_logic.engine.provenance', 'compute_versions'),
    'conclusion_valid_alone': ('epinoic_logic.engine.runner', 'conclusion_valid_alone'),
    'config_digest': ('epinoic_logic.engine.provenance', 'config_digest'),
    'conjuncts': ('epinoic_logic.engine.runner', '_conjuncts'),
    'is_definitive': ('epinoic_logic.engine.statuses', 'is_definitive'),
    'is_ungrounded': ('epinoic_logic.engine.runner', 'is_ungrounded'),
    'is_unverified': ('epinoic_logic.engine.runner', 'is_unverified'),
    'parse_and_validate': ('epinoic_logic.engine.validator', 'parse_and_validate'),
    'policy_config': ('epinoic_logic.engine.policies', 'policy_config'),
    'premises_inconsistent': ('epinoic_logic.engine.runner', 'premises_inconsistent'),
    'release_check': ('epinoic_logic.engine.release', 'release_check'),
    'sign_result': ('epinoic_logic.engine.provenance', 'sign_result'),
    'signature_matches': ('epinoic_logic.engine.provenance', 'signature_matches'),
    'verify': ('epinoic_logic.engine.runner', 'verify'),
    'verify_signature': ('epinoic_logic.engine.provenance', 'verify_signature'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
