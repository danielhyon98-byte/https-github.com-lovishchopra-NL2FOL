"""Public API of the translator, translate: the translation layer: claim and report contracts, eligibility, subject profiles, grounding checks, the outcome and its summary, the strict JSON parser, the provider interface (for overseer-agent providers) and the semantic-review currency rule.

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'BLOCK_CLOSE': ('epinoic_logic.translate.providers.rendering', 'BLOCK_CLOSE'),
    'BLOCK_OPEN': ('epinoic_logic.translate.providers.rendering', 'BLOCK_OPEN'),
    'ClaimRecord': ('epinoic_logic.translate.contracts', 'ClaimRecord'),
    'ClaimVerificationOutcome': ('epinoic_logic.translate.contracts', 'ClaimVerificationOutcome'),
    'EligibilityClass': ('epinoic_logic.translate.contracts', 'EligibilityClass'),
    'EligibilityDecision': ('epinoic_logic.translate.contracts', 'EligibilityDecision'),
    'ProviderError': ('epinoic_logic.translate.providers.base', 'ProviderError'),
    'ProviderInfo': ('epinoic_logic.translate.contracts', 'ProviderInfo'),
    'ProviderOutputError': ('epinoic_logic.translate.parsing', 'ProviderOutputError'),
    'ProviderResponse': ('epinoic_logic.translate.providers.base', 'ProviderResponse'),
    'SpecialistReport': ('epinoic_logic.translate.contracts', 'SpecialistReport'),
    'StructuralFinding': ('epinoic_logic.translate.contracts', 'StructuralFinding'),
    'SuppliedText': ('epinoic_logic.translate.contracts', 'SuppliedText'),
    'TASK_AUTHORITY_KINDS': ('epinoic_logic.translate.grounding', 'TASK_AUTHORITY_KINDS'),
    'TaskRecord': ('epinoic_logic.translate.contracts', 'TaskRecord'),
    'TranslationResult': ('epinoic_logic.translate.contracts', 'TranslationResult'),
    'TranslationStatus': ('epinoic_logic.translate.contracts', 'TranslationStatus'),
    'apply_subject_policy': ('epinoic_logic.translate.pipeline', 'apply_subject_policy'),
    'assess_release': ('epinoic_logic.translate.outcome', 'assess_release'),
    'binding_problem': ('epinoic_logic.translate.outcome', '_binding_problem'),
    'build_summary': ('epinoic_logic.translate.outcome', 'build_summary'),
    'check_assertion': ('epinoic_logic.translate.grounding', '_check_assertion'),
    'check_claim_sources': ('epinoic_logic.translate.grounding', 'check_claim_sources'),
    'check_problem_grounding': ('epinoic_logic.translate.grounding', 'check_problem_grounding'),
    'compose_outcome': ('epinoic_logic.translate.outcome', 'compose_outcome'),
    'decide_eligibility': ('epinoic_logic.translate.eligibility', 'decide_eligibility'),
    'display_status_for': ('epinoic_logic.translate.outcome', 'display_status_for'),
    'locate_quotation': ('epinoic_logic.translate.grounding', 'locate_quotation'),
    'outcome_diagnosis': ('epinoic_logic.translate.outcome', 'outcome_diagnosis'),
    'parse_json_object': ('epinoic_logic.translate.parsing', 'parse_json_object'),
    'report_diagnostics': ('epinoic_logic.translate.diag_core', 'report_diagnostics'),
    'resolve_profile': ('epinoic_logic.translate.subjects', 'resolve_profile'),
    'review_currency': ('epinoic_logic.translate.review', 'review_currency'),
    'semantic_restatement': ('epinoic_logic.translate.restatement', 'semantic_restatement'),
    'sha256_text': ('epinoic_logic.translate.contracts', 'sha256_text'),
    'subjects': ('epinoic_logic.translate.subjects', None),
    'truncate': ('epinoic_logic.translate.common', 'truncate'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
