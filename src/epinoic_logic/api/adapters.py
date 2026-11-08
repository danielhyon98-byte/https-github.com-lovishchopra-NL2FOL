"""Public API of the translator, adapters: the specialist adapters' readings the overseer re-derives: the English parser's segmentation, the Markdown readers (quotations, JSON blocks, self-certification labels) and the excerpt check against supplied sources.

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
    'mask_quotations': ('epinoic_logic.adapters.markdown', 'mask_quotations'),
    'opens_note_paragraph': ('epinoic_logic.adapters.markdown', 'opens_note_paragraph'),
    'segment': ('epinoic_logic.adapters.english_specialist.parser', 'segment'),
    'self_cert_vocabulary': ('epinoic_logic.adapters.markdown', 'self_cert_vocabulary'),
    'split_sentences': ('epinoic_logic.adapters.english_specialist.parser', 'split_sentences'),
    'verification_label': ('epinoic_logic.adapters.markdown', 'verification_label'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
