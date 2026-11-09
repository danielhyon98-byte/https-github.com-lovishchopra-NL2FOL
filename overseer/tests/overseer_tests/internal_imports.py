"""The translator modules this sub-project's tests and harness scripts still import directly: one explicit, documented
allowlist (architecture review after arena round 8).

The package itself (``src/epinoic_overseer``) reaches the translator only through its public API
(``epinoic_logic.api``) and the integration protocol's modules (:data:`PROTOCOL_MODULES`), with no exception. The tests
and the harness scripts use the same two doors wherever the public API offers what they need; this allowlist names every
other import of a translator module they make, file by file, with why it is direct. ``test_subproject_layout.py`` scans
``tests/`` and ``scripts/`` against it: an import it does not list fails, an entry no file still makes fails (remove it),
and the number of entries never exceeds :data:`CEILING`, which may only be lowered. So the debt can only go down: a name
the translator adds to its public API is moved there (and its entry removed), never added here again.

Each module's category says why its imports are direct:

* ``patch``: a module or a private hook a tampering case, a non-interference test or the harness patches or drives (the
  public API resolves a name when it is imported and adds no copy, so a patch must name the internal module);
* ``drift``: the translator's own source a test holds the overseer's tables or readers to (it compares, never calls
  through);
* ``missing``: a name the public API does not export yet; the translator's public API is to add it (``docs/PUBLIC_API.md``),
  and then the import moves to ``epinoic_logic.api``;
* ``fixture``: the translator's test providers and pipeline, which the tests and the harness run as production runs them;
* ``service``: a module of the checks service (not of the protocol) whose own result a test compares with the adapter's.

The copies of the translator's test material that this suite keeps byte for byte equal to the originals
(:data:`COPIED_FILES`; ``test_the_copied_test_material_is_the_translators``) import what the originals import and are
not scanned: editing their imports would break that equality.
"""
from __future__ import annotations

#: The integration protocol's modules the overseer may import (the package, its tests and its scripts): the overseer
#: port contract, the protocol's vocabulary, its errors, its canonical JSON and the router port's pool operation. The
#: service's implementation modules (turn, routes, settings, runtime, selftest, ...) are not the protocol.
PROTOCOL_MODULES: tuple[str, ...] = ("canonical", "errors", "overseer_port", "protocol", "router_pool")

#: The categories of :data:`ALLOWED` (module docstring).
CATEGORIES: tuple[str, ...] = ("patch", "drift", "missing", "fixture", "service")

#: The Python copies of the translator's test material, kept byte for byte equal to the originals (not scanned).
COPIED_FILES: tuple[str, ...] = ("tests/overseer_tests/c1_texts.py", "tests/overseer_tests/core_hostile.py", "tests/overseer_tests/growth.py",
                                 "tests/overseer_tests/r7_support.py", "tests/overseer_tests/timing.py")

#: internal module -> (category, why, {imported name ("" for the module itself) -> the files, relative to the sub-project,
#: that may import it}).
ALLOWED: dict[str, tuple[str, str, dict[str, tuple[str, ...]]]] = {
    'epinoic_logic': ('drift', "the translator package itself: its location, for the scans that hold the overseer's tables to the translator's sources", {
        '': (
            'tests/overseer_tests/test_flash_router_pool.py', 'tests/overseer_tests/test_integration_codes.py',
            'tests/overseer_tests/test_knowledge_drift.py', 'tests/overseer_tests/test_knowledge_export.py',
            'tests/overseer_tests/test_review1_audit_tier.py', 'tests/overseer_tests/test_stem_completion.py',
            'tests/overseer_tests/test_subproject_layout.py',
        ),
        'named': ('tests/overseer_tests/test_integration_codes.py',),
    }),
    'epinoic_logic.adapters.english_specialist.parser': ('drift', "the English parser's own label pattern, compared with the overseer's reader", {
        'FEEDBACK_LABEL_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py',),
    }),
    'epinoic_logic.adapters.fixtures_multi_subject': ('fixture', "the translator's multi-subject fixture reports", {
        'by_name': ('tests/overseer_tests/test_review2_content_checks.py',),
    }),
    'epinoic_logic.adapters.stem_specialist.parser': ('drift', "the STEM parser's own structure-head pattern, compared with the overseer's reader", {
        '_STRUCTURE_HEAD_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py', 'tests/overseer_tests/test_c1_push_check_round4.py'),
    }),
    'epinoic_logic.branches': ('patch', "the hub module, patched by the harness's tampering cases", {
        'hub': ('scripts/ovs_harness.py',),
    }),
    'epinoic_logic.branches.generic_parser': ('drift', "the generic parser and its private lead patterns, compared with the overseer's readers", {
        'GenericTextParser': ('scripts/ovs_harness.py', 'tests/overseer_tests/test_corrections_stem_ready.py'),
        '_ASSUMPTION_LEAD_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py',),
        '_DIAGRAM_LINE_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py',),
        '_MEASURE_LEAD_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py',),
        '_RESULT_LEAD_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py',),
        '_WHY_LEAD_RE': ('tests/overseer_tests/test_c1_push_check_non_material.py',),
    }),
    'epinoic_logic.branches.hub': ('patch', 'the hub module, patched by the hub-wiring tests', {
        '': ('tests/overseer_tests/test_hook_hub.py',),
    }),
    'epinoic_logic.branches.registry': ('drift', "the registered branches, compared with the overseer's tables", {
        'BRANCHES': ('tests/overseer_tests/test_corrections_stem_ready.py',),
        'CORE': ('tests/overseer_tests/test_corrections_stem_ready.py',),
    }),
    'epinoic_logic.branches.stem_pack': ('patch', 'the STEM pack, patched by the tampering case T23bq', {
        'StemPack': ('scripts/tamper.py',),
    }),
    'epinoic_logic.channel': ('patch', "the channel's modules, patched by tampering and non-interference tests", {
        'bus': (
            'tests/overseer_tests/test_c1_name_substitution.py', 'tests/overseer_tests/test_gate4_shadow_budget.py',
            'tests/overseer_tests/test_review3_audit_tier.py',
        ),
        'contracts': ('tests/overseer_tests/test_knowledge_drift.py',),
        'events': ('tests/overseer_tests/test_gate4_shadow_budget.py',),
    }),
    'epinoic_logic.channel.bus': ('patch', 'the channel module and its private hooks, patched by tampering cases', {
        '': (
            'scripts/tamper.py', 'tests/overseer_tests/test_audit_custody_receipts.py', 'tests/overseer_tests/test_audit_peer_synthesis.py',
            'tests/overseer_tests/test_audit_results_formal.py', 'tests/overseer_tests/test_audit_signed_report.py',
            'tests/overseer_tests/test_c1_handoff_bidi_audit.py', 'tests/overseer_tests/test_c1_handoff_bounds.py',
            'tests/overseer_tests/test_clearance_c1_overseer.py', 'tests/overseer_tests/test_gate1_overseer_fixes.py',
            'tests/overseer_tests/test_knowledge_drift.py', 'tests/overseer_tests/test_protocol_validate.py',
            'tests/overseer_tests/test_r7_stage2_detection.py', 'tests/overseer_tests/test_r8_architecture_review.py',
            'tests/overseer_tests/test_rebuild_merged_translator.py', 'tests/overseer_tests/test_review1_audit_tier.py',
            'tests/overseer_tests/test_review1_content_checks.py',
        ),
        '_now': ('tests/overseer_tests/test_review2_audit_tier.py',),
        '_observed': ('tests/overseer_tests/test_review2_audit_tier.py',),
        'extract_items': ('tests/overseer_tests/test_review2_audit_tier.py',),
    }),
    'epinoic_logic.channel.events': ('patch', "the observer hook's internals, driven by the non-interference and journal tests", {
        'OBSERVER_ERRORS_MAX': ('tests/overseer_tests/test_hook_noninterference.py',),
        'ObservationState': ('tests/overseer_tests/test_audit_journal.py', 'tests/overseer_tests/test_audit_sink.py'),
        'event_kind': ('tests/overseer_tests/test_second_translator_merge.py',),
        'observe_call': (
            'tests/overseer_tests/conftest.py', 'tests/overseer_tests/test_audit_journal.py', 'tests/overseer_tests/test_audit_sink.py',
            'tests/overseer_tests/test_hook_equivalence.py',
        ),
        'take_before': ('tests/overseer_tests/test_audit_sink.py',),
    }),
    'epinoic_logic.engine': ('patch', "the engine's sink and error modules, patched or read by tests", {
        'errors': ('tests/overseer_tests/test_integration_codes.py',),
        'sink': ('scripts/tamper.py', 'tests/overseer_tests/test_review1_audit_tier.py', 'tests/overseer_tests/test_review1_content_checks.py'),
    }),
    'epinoic_logic.engine.policies': ('drift', "the named engine policies and their limits, compared with the overseer's replay rules", {
        'NAMED_POLICIES': ('tests/overseer_tests/test_integration_codes.py',),
        'NONLINEAR_LIMITS': ('tests/overseer_tests/test_rebuild_merged_translator.py', 'tests/overseer_tests/test_second_translator_merge.py'),
        'UnknownPolicyError': ('tests/overseer_tests/test_integration_codes.py',),
        'named_policy': ('tests/overseer_tests/test_integration_codes.py',),
        'policy_limits': (
            'tests/overseer_tests/stem_decide.py', 'tests/overseer_tests/test_stem_completion.py', 'tests/overseer_tests/test_stem_repair2.py',
            'tests/overseer_tests/test_stem_repair3.py', 'tests/overseer_tests/test_stem_repair4.py', 'tests/overseer_tests/test_stem_repair5.py',
        ),
    }),
    'epinoic_logic.engine.provenance': ('patch', 'the binding computation, used by tampering cases to forge a result', {
        'compute_binding': ('tests/overseer_tests/test_review2_audit_tier.py',),
    }),
    'epinoic_logic.engine.sink': ('patch', 'the result sink, used by tampering cases to emit a forged result', {
        'capture_active': ('tests/overseer_tests/test_audit_sink.py', 'tests/overseer_tests/test_hook_noninterference.py'),
        'emit': (
            'scripts/tamper.py', 'tests/overseer_tests/test_audit_replay.py', 'tests/overseer_tests/test_audit_results_formal.py',
            'tests/overseer_tests/test_audit_sink.py', 'tests/overseer_tests/test_review2_audit_tier.py',
        ),
    }),
    'epinoic_logic.engine.statuses': ('drift', "the definitive statuses, compared with the overseer's tables", {
        'DEFINITIVE': ('tests/overseer_tests/test_integration_codes.py', 'tests/overseer_tests/test_knowledge_drift.py'),
    }),
    'epinoic_logic.integration.delivery': ('service', "the kit's delivery module, compared with the overseer's delivery policy", {
        'ClaimFields': ('tests/overseer_tests/test_c1_push_check_round6.py',),
        'FORMAL_LABEL_RULE': ('tests/overseer_tests/test_c1_push_check_round6.py',),
        'count_claims': ('tests/overseer_tests/test_c1_push_check_round6.py',),
        'summarize': ('tests/overseer_tests/test_c1_push_check_round6.py',),
    }),
    'epinoic_logic.integration.turn': ('service', "the service's turn helpers, compared with the port adapter's", {
        'hub_agent_id': ('tests/overseer_tests/test_port_adapter.py',),
        'receipt_sha256': ('tests/overseer_tests/test_port_adapter.py',),
    }),
    'epinoic_logic.integrity': ('patch', 'the integrity package\'s modules, imported whole: the joint check, whose verify a test patches, and the contract models a drift test reads', {
        'contracts': ('tests/overseer_tests/test_knowledge_drift.py',),
        'cross_check': ('tests/overseer_tests/test_review3_audit_tier.py',),
    }),
    'epinoic_logic.integrity.ledger': ('drift', "the ledger's own readers, compared with the overseer's", {
        'figure_pairing_differences': (
            'tests/overseer_tests/test_review1_content_checks.py', 'tests/overseer_tests/test_review2_content_checks.py',
            'tests/overseer_tests/test_review3_content_checks.py',
        ),
        'meaning_differences': ('tests/overseer_tests/test_repair3_same_quantity.py',),
        'meaning_inversions': ('tests/overseer_tests/test_review2_content_checks.py',),
        'substituted_names': ('tests/overseer_tests/test_c1_name_substitution.py',),
        'text_outside_claims': ('tests/overseer_tests/test_review3_content_checks.py',),
    }),
    'epinoic_logic.ir': ('drift', "the IR schema module, compared with the pack's schema text", {
        'schema': ('tests/overseer_tests/test_knowledge_drift.py',),
    }),
    'epinoic_logic.named': ('drift', "the named-diagnostic module, compared with the overseer's code tables", {
        '': ('tests/overseer_tests/test_knowledge_drift.py',),
    }),
    'epinoic_logic.stem.checks': ('patch', 'the STEM checks module, patched by tampering cases and run to re-derive a check', {
        '': ('scripts/tamper.py', 'tests/overseer_tests/test_stem_repair12.py'),
        'build_checks': (
            'tests/overseer_tests/stem_decide.py', 'tests/overseer_tests/test_stem_completion.py', 'tests/overseer_tests/test_stem_repair12.py',
            'tests/overseer_tests/test_stem_repair2.py', 'tests/overseer_tests/test_stem_repair3.py', 'tests/overseer_tests/test_stem_repair4.py',
            'tests/overseer_tests/test_stem_repair5.py', 'tests/overseer_tests/test_stem_repair8.py',
        ),
    }),
    'epinoic_logic.stem.numbers': ('drift', "the STEM number reader, compared with the overseer's", {
        'scan_number': ('tests/overseer_tests/test_stem_completion.py',),
    }),
    'epinoic_logic.stem.relations': ('drift', "the ST codes' severities, compared with the overseer's tables", {
        'ST_SEVERITY': ('tests/overseer_tests/test_integration_codes.py', 'tests/overseer_tests/test_stem_completion.py'),
    }),
    'epinoic_logic.stem.tolerance': ('drift', "the tolerance rule, compared with the pack's statement of it", {
        'SHORT_RULE': ('tests/overseer_tests/test_stem_completion.py',),
        'TAU_APPROX': ('tests/overseer_tests/test_stem_completion.py',),
        'TAU_EQUAL': ('tests/overseer_tests/test_stem_completion.py',),
        'half_width': ('tests/overseer_tests/test_stem_completion.py',),
        'tau_for': ('tests/overseer_tests/test_stem_completion.py',),
    }),
    'epinoic_logic.translate': ('drift', "the translation contracts module, compared with the pack's schema text", {
        'contracts': ('tests/overseer_tests/test_knowledge_drift.py',),
    }),
    'epinoic_logic.translate.outcome': ('fixture', "the translator's claim verification, run as production runs it", {
        'verify_claim': (
            'scripts/ovs_harness.py', 'scripts/tamper.py', 'tests/overseer_tests/delivery_support.py',
            'tests/overseer_tests/test_c1_handoff_shadow.py', 'tests/overseer_tests/test_corrections_stem_ready.py',
            'tests/overseer_tests/test_corrections_trn_necessity.py', 'tests/overseer_tests/test_delivery_overseer_fixes.py',
            'tests/overseer_tests/test_rebuild_merged_translator.py', 'tests/overseer_tests/test_repair3_same_quantity.py',
            'tests/overseer_tests/test_translation_agents.py', 'tests/overseer_tests/test_translation_oversight.py',
        ),
    }),
    'epinoic_logic.translate.pipeline': ('fixture', 'the translation pipeline, run as production runs it', {
        'Translator': (
            'scripts/ovs_harness.py', 'scripts/run_contained.py', 'scripts/tamper.py', 'tests/overseer_tests/conftest.py',
            'tests/overseer_tests/delivery_support.py', 'tests/overseer_tests/test_c1_handoff_shadow.py',
            'tests/overseer_tests/test_clearance_c1_overseer.py', 'tests/overseer_tests/test_corrections_adjudicated_faults.py',
            'tests/overseer_tests/test_corrections_stem_ready.py', 'tests/overseer_tests/test_corrections_trn_necessity.py',
            'tests/overseer_tests/test_delivery_overseer_fixes.py', 'tests/overseer_tests/test_rebuild_merged_translator.py',
            'tests/overseer_tests/test_repair3_same_quantity.py', 'tests/overseer_tests/test_translation_agents.py',
            'tests/overseer_tests/test_translation_oversight.py',
        ),
        '_Rejected': (
            'scripts/run_contained.py', 'tests/overseer_tests/test_clearance_c1_overseer.py',
            'tests/overseer_tests/test_corrections_adjudicated_faults.py', 'tests/overseer_tests/test_rebuild_merged_translator.py',
        ),
    }),
    'epinoic_logic.translate.providers': ('fixture', "the translator's providers: fixture and adapter classes the runner tests drive", {
        'AnthropicTranslationProvider': ('tests/overseer_tests/test_knowledge_runner.py',),
        'CompletionProvider': ('tests/overseer_tests/test_knowledge_runner.py',),
        'FixtureCompletionProvider': (
            'scripts/run_contained.py', 'scripts/tamper.py', 'tests/overseer_tests/test_knowledge_pack.py',
            'tests/overseer_tests/test_knowledge_runner.py',
        ),
        'OpenAICompatibleTranslationProvider': ('tests/overseer_tests/test_knowledge_runner.py',),
        'data_block': ('tests/overseer_tests/test_knowledge_runner.py',),
    }),
    'epinoic_logic.translate.providers.fixture': ('fixture', "the translator's fixture providers", {
        'FixtureReviewProvider': ('tests/overseer_tests/delivery_support.py', 'tests/overseer_tests/test_delivery_overseer_fixes.py'),
        'FixtureTranslationProvider': (
            'scripts/ovs_harness.py', 'scripts/tamper.py', 'tests/overseer_tests/delivery_support.py',
            'tests/overseer_tests/test_c1_handoff_shadow.py', 'tests/overseer_tests/test_corrections_stem_ready.py',
            'tests/overseer_tests/test_corrections_trn_necessity.py', 'tests/overseer_tests/test_delivery_overseer_fixes.py',
            'tests/overseer_tests/test_rebuild_merged_translator.py', 'tests/overseer_tests/test_repair3_same_quantity.py',
            'tests/overseer_tests/test_translation_agents.py', 'tests/overseer_tests/test_translation_oversight.py',
        ),
        'dossier_digest_of': ('tests/overseer_tests/test_knowledge_runner.py',),
    }),
    'epinoic_logic.translate.review': ('fixture', "the translator's semantic reviewer, run as production runs it", {
        'SemanticReviewer': ('tests/overseer_tests/delivery_support.py', 'tests/overseer_tests/test_delivery_overseer_fixes.py'),
    }),
    'epinoic_logic.translate.subjects': ('drift', "the subject profiles' text, compared with the pack's statement of them", {
        'PROFILES': ('tests/overseer_tests/test_stem_completion.py',),
        'STEM_ENCODING_GUIDANCE': (
            'tests/overseer_tests/test_rebuild_merged_translator.py', 'tests/overseer_tests/test_repair5_stem_pack.py',
            'tests/overseer_tests/test_stem_completion.py',
        ),
        'prompt_profile_text': ('tests/overseer_tests/test_stem_completion.py',),
    }),
}

#: The number of (file, module, name) imports :data:`ALLOWED` lists, at most: it may only be lowered. 255 at the review;
#: 177 since the translator's public API 1.1 added the 26 names of the ``missing`` category and their 78 imports moved onto
#: it (the handoff fixer of the same review), which left that category empty.
CEILING = 177
