"""What this release of the overseer needs of the translator, checked when the package is imported.

The overseer depends on the translator only through its public API (``epinoic_logic.api``) and the integration
protocol's modules. Its distribution pin (``epinoic-logic`` in ``pyproject.toml``) cannot tell two translator builds of
one version apart, so a translator that lacks a name this release imports would otherwise surface as a bare
``ImportError`` (or ``AttributeError``) from deep inside the package. :func:`check_translator_api` runs first, before any
module of the package imports the translator, and refuses such a translator with one clear error naming every missing
name (:class:`TranslatorIncompatible`):

* every public name this release imports (:data:`REQUIRED_API`, ``area -> names``) must be listed by the translator's
  public module of that area (its ``EXPORTS``), which only reads a small table and resolves nothing;
* every integration-protocol name it imports (:data:`REQUIRED_PROTOCOL`) must be defined by that protocol module;
* when the translator's public API states its version (``epinoic_logic.api.API_VERSION``, ``MAJOR.MINOR``), its MAJOR
  must be :data:`API_MAJOR`: a new MAJOR changes or removes names, and this release was not built against it. A
  translator that states no version is held to the names alone.

``test_subproject_layout.py`` keeps both lists equal to what the package's modules import. Nothing here evaluates
anything: it compares names.
"""
from __future__ import annotations

import importlib
from typing import Mapping, Optional

__all__ = ["API_MAJOR", "REQUIRED_API", "REQUIRED_PROTOCOL", "TranslatorIncompatible", "missing_translator_names", "check_translator_api"]

#: The MAJOR version of the translator's public API this release speaks, once the API states one.
API_MAJOR = 1

REQUIRED_API: dict[str, tuple[str, ...]] = {
    'adapters': (
        'BARE_NOTE_LEAD_RE', 'MAX_CLAIM_TEXT_CHARS', 'META_NARRATION_RE', 'PARAGRAPH_SPLIT_RE', 'TAIL_CLAIM_ID', 'check_excerpt', 'find_json_spans',
        'find_quotation_spans', 'is_json_block', 'is_meta_sentence', 'is_self_certification', 'mask_quotations', 'opens_note_paragraph', 'segment',
        'self_cert_vocabulary', 'split_sentences', 'verification_label',
    ),
    'branches': (
        'AuditorNotAttached', 'EnglishParserWrapper', 'GENERIC_MARK_ALLOC', 'GENERIC_MARK_CODE', 'HubReview', 'PoolReview', 'RevisionIssue',
        'RouterHub', 'absent_mentions', 'default_registry', 'quote_key',
    ),
    'channel': (
        'BLOCKING_PREFIXES', 'CLAIM_OUT_OF_SCOPE', 'ChannelBefore', 'ChannelEvent', 'Constraint', 'DECLINED_BOUND_PREFIX', 'DETAIL_MAX',
        'FEEDBACK_KEY_ID', 'FEEDBACK_RULES', 'FOLDED_TAIL_RE', 'MAX_ADVISORY', 'MAX_FLAWS', 'MAX_FLAW_CLAIMS', 'MAX_MESSAGE_CHARS',
        'MAX_QUOTED_TOTAL', 'PoolEntry', 'REVISION_RULES', 'REVISION_SCOPE', 'RequestItem', 'RevisionClaim', 'RevisionFlaw', 'RevisionRequest',
        'SCOPE_TAIL', 'STEM_CHECK_BUDGET_S', 'TaskRequest', 'TranslatorChannel', 'TransmissionReceipt', 'TransmissionStatus', 'about_band',
        'advisory_candidate', 'bidi_control_message', 'bound_word_measure', 'carries_quotation', 'channel_pool', 'check_result_statement',
        'coerce_payload', 'count_paragraphs', 'eligible_flaws', 'extract_constraints', 'finding_digest', 'fit_summary', 'header_digest',
        'ids_held_by_other_agents', 'keep_list', 'located', 'match_claims', 'material_claims', 'measure_answer_words', 'model_json',
        'named_claim_ids', 'needs_qualified_ids', 'observation_state', 'per_part_bound', 'quote_text', 'render_instruction',
        'render_revision_message', 'rendered_digest', 'report_bidi_findings', 'revision_budget', 'revision_id_of', 'revision_signable_text',
        'snapshot_event', 'subject_error_groups', 'weakened', 'withheld_deliverable', 'word_bound_severity',
    ),
    'engine': (
        'CapturedResult', 'PACK_POLICIES', 'POLICY_VERSION', 'POSITIVE_STATUS', 'SCOPE_STATEMENT', 'SolverConfig', 'TASK_GIVEN_KINDS',
        'VerificationResult', 'VerificationStatus', 'assumed_grounding', 'binding_inconsistencies', 'canonical_expr', 'capture_results',
        'circular_premises', 'compile_expr', 'compile_problem', 'compute_versions', 'conclusion_valid_alone', 'config_digest', 'conjuncts',
        'is_definitive', 'is_ungrounded', 'is_unverified', 'parse_and_validate', 'policy_config', 'premises_inconsistent', 'release_check',
        'sign_result', 'signature_matches', 'verify', 'verify_signature',
    ),
    'integrity': (
        'AgentMessage', 'AgentRole', 'IntegrityFinding', 'IntegrityReport', 'JOINT_LIMITS', 'MESSAGE_MAX_CHARS', 'MessageLog', 'PRECISION_LIMITS',
        'Synthesis', 'WorkPlan', 'allowed_sender_roles', 'bind_payload', 'check_conflict_disclosure', 'check_cross_report_consistency',
        'check_report_against_plan', 'check_synthesis_ledger', 'figure_spellings', 'joint_problem', 'parse_rfc3339', 'payload_hash',
        'rename_candidates_apart', 'report_digest', 'run_integrity_checks', 'sign_message', 'split_by_gloss', 'verify_message',
        'verify_report_digest', 'words_as_digits',
    ),
    'ir': (
        'DEFAULT_LIMITS', 'Expr', 'Problem', 'canonical_json', 'problem_digest', 'sha256_hex', 'strict_object_pairs',
    ),
    'named': (
        'MAX_PER_RECEIPT', 'NAMED_CODES', 'defect_of', 'effective_severity', 'from_finding', 'ordered',
    ),
    'stem': (
        'ANNOTATION_ONLY_LINEAR_RE', 'Abs', 'BinOp', 'MARK_ALLOC', 'MARK_CODE', 'Neg', 'Num', 'PART_LEAD_RE', 'Pow', 'Sym', 'TABLE_SEPARATOR_RE',
        'annotation_ranges', 'build_document', 'parse_data_tables', 'unit_dimension',
    ),
    'translate': (
        'BLOCK_CLOSE', 'BLOCK_OPEN', 'ClaimRecord', 'ClaimVerificationOutcome', 'ProviderError', 'ProviderOutputError', 'ProviderResponse',
        'SpecialistReport', 'SuppliedText', 'TASK_AUTHORITY_KINDS', 'TaskRecord', 'TranslationResult', 'TranslationStatus', 'apply_subject_policy',
        'assess_release', 'binding_problem', 'build_summary', 'check_assertion', 'check_claim_sources', 'check_problem_grounding',
        'compose_outcome', 'decide_eligibility', 'display_status_for', 'locate_quotation', 'outcome_diagnosis', 'parse_json_object',
        'previous_lines', 'report_diagnostics', 'resolve_profile', 'review_currency', 'semantic_restatement', 'sha256_text', 'subjects', 'truncate',
    ),
}
REQUIRED_PROTOCOL: dict[str, tuple[str, ...]] = {
    'canonical': (
        'sha256_text',
    ),
    'errors': (
        'IntegrationError',
    ),
    'overseer_port': (
        'AUDIT_KEY_ID', 'MAX_PENDING_WAIT_MS', 'PORT_VERSION',
    ),
    'protocol': (
        'AUDIT_SCOPE_STATEMENT', 'OVERSEER_REFUSALS', 'PROTOCOL', 'RouterIdentity', 'SCOPE_STATEMENT',
    ),
    'router_pool': (
        'POOL_RISK_CLASSES', 'PoolRouterAttachment', 'ask_pool_router', 'attach_pool_router', 'build_pool_request', 'check_pool_plan', 'item_id',
        'pool_request_digest',
    ),
}


class TranslatorIncompatible(ImportError):
    """The installed translator does not offer what this release of the overseer imports."""


def missing_translator_names(api: Optional[Mapping[str, tuple[str, ...]]] = None,
                             protocol: Optional[Mapping[str, tuple[str, ...]]] = None) -> list[str]:
    """Every required name the installed translator does not offer (``api.<area>.<name>`` or
    ``integration.<module>.<name>``), and a public API version of another MAJOR, each as one line; empty when it offers
    them all."""
    out: list[str] = []
    try:
        root = importlib.import_module("epinoic_logic.api")
    except ImportError as exc:
        return [f"the translator's public API (epinoic_logic.api) cannot be imported: {type(exc).__name__}"]
    version = getattr(root, "API_VERSION", None)
    if version is not None:
        major = str(version).split(".", 1)[0]
        if not major.isdigit() or int(major) != API_MAJOR:
            out.append(f"the translator's public API is version {version!s}; this release speaks version {API_MAJOR}.x")
    for area, names in sorted((api if api is not None else REQUIRED_API).items()):
        try:
            exported = set(getattr(importlib.import_module(f"epinoic_logic.api.{area}"), "EXPORTS", {}) or {})
        except ImportError:
            out.append(f"api.{area} (the whole public module)")
            continue
        out += [f"api.{area}.{n}" for n in names if n not in exported]
    for module, names in sorted((protocol if protocol is not None else REQUIRED_PROTOCOL).items()):
        try:
            mod = importlib.import_module(f"epinoic_logic.integration.{module}")
        except ImportError:
            out.append(f"integration.{module} (the whole protocol module)")
            continue
        out += [f"integration.{module}.{n}" for n in names if not hasattr(mod, n)]
    return out


def check_translator_api() -> None:
    """Raise :class:`TranslatorIncompatible` naming every missing name (module docstring); return when the installed
    translator offers everything this release imports."""
    missing = missing_translator_names()
    if missing:
        from . import __version__
        shown = "; ".join(missing[:24]) + (f"; and {len(missing) - 24} more" if len(missing) > 24 else "")
        raise TranslatorIncompatible(
            f"epinoic-overseer {__version__} needs names the installed translator (epinoic-logic) does not offer through its public API "
            f"and the integration protocol: {shown}. Install the translator release this overseer release was built against.")
