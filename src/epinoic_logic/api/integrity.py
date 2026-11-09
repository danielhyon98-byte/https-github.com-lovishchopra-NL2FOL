"""Public API of the translator, integrity: the integrity layer: agent messages and their signatures, work plans, syntheses, the claim ledger and the cross-agent checks (the overseer re-runs them on what was journaled).

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'AgentMessage': ('epinoic_logic.integrity.contracts', 'AgentMessage'),
    'AgentRole': ('epinoic_logic.integrity.contracts', 'AgentRole'),
    'ConflictRecord': ('epinoic_logic.integrity.contracts', 'ConflictRecord'),
    'IntegrityFinding': ('epinoic_logic.integrity.contracts', 'IntegrityFinding'),
    'IntegrityReport': ('epinoic_logic.integrity.contracts', 'IntegrityReport'),
    'JOINT_LIMITS': ('epinoic_logic.integrity.cross_check', 'JOINT_LIMITS'),
    'LedgerEntry': ('epinoic_logic.integrity.contracts', 'LedgerEntry'),
    'MESSAGE_MAX_CHARS': ('epinoic_logic.integrity.contracts', 'MESSAGE_MAX_CHARS'),
    'MessageLog': ('epinoic_logic.integrity.envelope', 'MessageLog'),
    'PRECISION_LIMITS': ('epinoic_logic.integrity.cross_check', 'PRECISION_LIMITS'),
    'ROLE_CONTRACTS': ('epinoic_logic.integrity.envelope', 'ROLE_CONTRACTS'),
    'Synthesis': ('epinoic_logic.integrity.contracts', 'Synthesis'),
    'SynthesizedClaim': ('epinoic_logic.integrity.contracts', 'SynthesizedClaim'),
    'WorkPlan': ('epinoic_logic.integrity.contracts', 'WorkPlan'),
    'allowed_sender_roles': ('epinoic_logic.integrity.envelope', 'allowed_sender_roles'),
    'at_stated_precision': ('epinoic_logic.integrity.cross_check', 'at_stated_precision'),
    'bind_payload': ('epinoic_logic.integrity.envelope', 'bind_payload'),
    'check_conflict_disclosure': ('epinoic_logic.integrity.cross_check', 'check_conflict_disclosure'),
    'check_cross_report_consistency': ('epinoic_logic.integrity.cross_check', 'check_cross_report_consistency'),
    'check_report_against_plan': ('epinoic_logic.integrity.handoff', 'check_report_against_plan'),
    'check_synthesis_ledger': ('epinoic_logic.integrity.ledger', 'check_synthesis_ledger'),
    'figure_spellings': ('epinoic_logic.integrity.ledger', 'figure_spellings'),
    'joint_problem': ('epinoic_logic.integrity.cross_check', 'joint_problem'),
    'parse_rfc3339': ('epinoic_logic.integrity.contracts', 'parse_rfc3339'),
    'payload_hash': ('epinoic_logic.integrity.contracts', 'payload_hash'),
    'rename_candidates_apart': ('epinoic_logic.integrity.cross_check', 'rename_candidates_apart'),
    'report_digest': ('epinoic_logic.integrity.contracts', 'report_digest'),
    'run_integrity_checks': ('epinoic_logic.integrity', 'run_integrity_checks'),
    'sign_message': ('epinoic_logic.integrity.contracts', 'sign_message'),
    'split_by_gloss': ('epinoic_logic.integrity.cross_check', 'split_by_gloss'),
    'verify_message': ('epinoic_logic.integrity.contracts', 'verify_message'),
    'verify_report_digest': ('epinoic_logic.integrity.contracts', 'verify_report_digest'),
    'words_as_digits': ('epinoic_logic.integrity.ledger', '_words_as_digits'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
