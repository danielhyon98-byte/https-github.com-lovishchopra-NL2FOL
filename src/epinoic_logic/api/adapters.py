"""Public API of the translator, adapters: the specialist adapters' readings the overseer re-derives: the English parser's segmentation, the Markdown readers (quotations, JSON blocks, self-certification labels), the one self-certification reader (``selfcert``, with the thin names of ``self_report``) and the excerpt check against supplied sources.

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'BARE_NOTE_LEAD_RE': ('epinoic_logic.adapters.markdown', 'BARE_NOTE_LEAD_RE'),
    'MAX_CLAIM_TEXT_CHARS': ('epinoic_logic.adapters.markdown', 'MAX_CLAIM_TEXT_CHARS'),
    'META_NARRATION_RE': ('epinoic_logic.adapters.english_specialist.parser', 'META_NARRATION_RE'),
    'PARAGRAPH_SPLIT_RE': ('epinoic_logic.adapters.english_specialist.parser', '_PARAGRAPH_SPLIT_RE'),
    'TAIL_CLAIM_ID': ('epinoic_logic.adapters.english_specialist.parser', 'TAIL_CLAIM_ID'),
    'check_excerpt': ('epinoic_logic.adapters.sources', 'check_excerpt'),
    'find_json_spans': ('epinoic_logic.adapters.markdown', 'find_json_spans'),
    'find_quotation_spans': ('epinoic_logic.adapters.markdown', 'find_quotation_spans'),
    'is_json_block': ('epinoic_logic.adapters.markdown', 'is_json_block'),
    'is_meta_sentence': ('epinoic_logic.adapters.english_specialist.parser', 'is_meta_sentence'),
    'is_self_certification': ('epinoic_logic.adapters.markdown', 'is_self_certification'),
    'claim_is_self_report': ('epinoic_logic.adapters.self_report', 'claim_is_self_report'),
    'is_self_report': ('epinoic_logic.adapters.self_report', 'is_self_report'),
    'label_self_report': ('epinoic_logic.adapters.self_report', 'label_self_report'),
    'label_on_content': ('epinoic_logic.adapters.self_report', 'label_on_content'),
    'mask_outside_quotations': ('epinoic_logic.adapters.self_report', 'mask_outside_quotations'),
    'report_field_self_reports': ('epinoic_logic.adapters.self_report', 'report_field_self_reports'),
    'quotation_only': ('epinoic_logic.adapters.self_report', 'quotation_only'),
    'not_a_self_report': ('epinoic_logic.adapters.self_report', 'not_a_self_report'),
    'reading_form': ('epinoic_logic.adapters.self_report', 'reading_form'),
    'self_report_spots': ('epinoic_logic.adapters.self_report', 'self_report_spots'),
    'template_form': ('epinoic_logic.adapters.self_report', 'template_form'),
    'mask_quotations': ('epinoic_logic.adapters.markdown', 'mask_quotations'),
    'blank_model_marks': ('epinoic_logic.adapters.self_report', 'blank_model_marks'),
    # the one self-certification reader (round-10 hold remedy c3b, rules selfcert-1; API 1.2)
    'selfcert_read': ('epinoic_logic.selfcert', 'read'),
    'SelfCertContext': ('epinoic_logic.selfcert', 'Context'),
    'SelfCertReading': ('epinoic_logic.selfcert', 'Reading'),
    'self_certification_spots': ('epinoic_logic.selfcert', 'text_spots'),
    'report_self_certification_spots': ('epinoic_logic.selfcert', 'report_spots'),
    'payload_self_certification_spots': ('epinoic_logic.selfcert', 'payload_spots'),
    'unread_text_runs': ('epinoic_logic.selfcert', 'unread_text_runs'),
    'wholly_self_certification': ('epinoic_logic.selfcert', 'wholly_self_certification'),
    # the reader's fold table (confusables and folds), which the overseer's lead reader shares (round-10 hold remedy c3b; API 1.2)
    'selfcert_fold_table': ('epinoic_logic.selfcert.normalise', 'fold_table'),
    'selfcert_context_for': ('epinoic_logic.selfcert', 'context_for'),
    'SELFCERT_RULES': ('epinoic_logic.selfcert', 'SELFCERT_RULES'),
    'SELFCERT_UNREAD_RULE': ('epinoic_logic.selfcert', 'UNREAD_RULE'),
    'selfcert_rules_digest': ('epinoic_logic.selfcert', 'rules_digest'),
    'model_mark_ranges': ('epinoic_logic.adapters.self_report', 'model_mark_ranges'),
    'opens_note_paragraph': ('epinoic_logic.adapters.markdown', 'opens_note_paragraph'),
    'OWN_TEXT_RULE': ('epinoic_logic.adapters.own_text', 'OWN_TEXT_RULE'),
    'own_model_spans': ('epinoic_logic.adapters.own_text', 'own_model_spans'),
    'own_text_spans': ('epinoic_logic.adapters.own_text', 'own_text_spans'),
    # the one reader's decision that a quoted span is the writer's own (a model, a frame, an own correction and the wording it
    # replaces), with the supplied texts in view (c3d: the auditor's OVS-FID-004 reads what the parser and the channel read; API 1.3)
    'own_model_words': ('epinoic_logic.adapters.sources', 'own_model_words'),
    # the halves of the answer's own corrections read by role against the supplied texts: the replaced half of a correction that
    # restores a text's exact wording is free, a corrected half that presents a text's wording altered is a quotation (c3f: the
    # auditor's OVS-FID-004 reads what the English parser and the channel read; API 1.4)
    'correction_reading': ('epinoic_logic.adapters.own_text', 'correction_reading'),
    'CORRECTION_FREE': ('epinoic_logic.adapters.own_text', 'CORRECTION_FREE'),
    'CORRECTION_QUOTATION': ('epinoic_logic.adapters.own_text', 'CORRECTION_QUOTATION'),
    'segment': ('epinoic_logic.adapters.english_specialist.parser', 'segment'),
    'self_cert_vocabulary': ('epinoic_logic.adapters.markdown', 'self_cert_vocabulary'),
    'split_sentences': ('epinoic_logic.adapters.english_specialist.parser', 'split_sentences'),
    'truncate_claim_text': ('epinoic_logic.adapters.markdown', 'truncate_claim_text'),
    'verification_label': ('epinoic_logic.adapters.markdown', 'verification_label'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
