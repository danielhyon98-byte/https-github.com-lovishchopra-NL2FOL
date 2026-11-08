"""Public API of the translator, channel: the translator channel: its receipts and requests, the events it journals for an attached observer, and the channel's own deterministic rules the overseer re-derives on the journaled payload (the payload contract, the blocking codes, bidirectional controls, word bounds, the deliverable a receipt may withhold).

Part of :mod:`epinoic_logic.api` (``docs/PUBLIC_API.md``). Each name resolves to the internal module and attribute
listed below when it is imported; the internal name may differ (a name that is private inside the translator has a
public name here). Changing or removing a name here is a breaking change for every attached component.
"""
from __future__ import annotations

from ._lazy import exports

#: public name -> (internal module, attribute; None: the module itself)
EXPORTS: dict[str, tuple[str, str | None]] = {
    'BLOCKING_PREFIXES': ('epinoic_logic.channel.bus', '_BLOCKING_PREFIXES'),
    'CLAIM_OUT_OF_SCOPE': ('epinoic_logic.channel.bus', 'CLAIM_OUT_OF_SCOPE'),
    'ChannelBefore': ('epinoic_logic.channel.events', 'ChannelBefore'),
    'ChannelEvent': ('epinoic_logic.channel.events', 'ChannelEvent'),
    'Constraint': ('epinoic_logic.channel.contracts', 'Constraint'),
    'DECLINED_BOUND_PREFIX': ('epinoic_logic.channel.bus', 'DECLINED_BOUND_PREFIX'),
    'DETAIL_MAX': ('epinoic_logic.channel.bus', '_DETAIL_MAX'),
    'FOLDED_TAIL_RE': ('epinoic_logic.channel.bus', '_FOLDED_TAIL_RE'),
    'PoolEntry': ('epinoic_logic.channel.events', 'PoolEntry'),
    'RequestItem': ('epinoic_logic.channel.contracts', 'RequestItem'),
    'SCOPE_TAIL': ('epinoic_logic.channel.bus', '_SCOPE_TAIL'),
    'STEM_CHECK_BUDGET_S': ('epinoic_logic.channel.bus', 'STEM_CHECK_BUDGET_S'),
    'TaskRequest': ('epinoic_logic.channel.contracts', 'TaskRequest'),
    'TranslatorChannel': ('epinoic_logic.channel.bus', 'TranslatorChannel'),
    'TransmissionReceipt': ('epinoic_logic.channel.contracts', 'TransmissionReceipt'),
    'TransmissionStatus': ('epinoic_logic.channel.contracts', 'TransmissionStatus'),
    'about_band': ('epinoic_logic.channel.request_parser', 'about_band'),
    'bidi_control_message': ('epinoic_logic.channel.bus', 'bidi_control_message'),
    'bound_word_measure': ('epinoic_logic.channel.request_parser', 'bound_word_measure'),
    'channel_pool': ('epinoic_logic.channel.events', '_pool'),
    'check_result_statement': ('epinoic_logic.channel.bus', 'check_result_statement'),
    'coerce_payload': ('epinoic_logic.channel.bus', '_coerce_payload'),
    'count_paragraphs': ('epinoic_logic.channel.request_parser', 'count_paragraphs'),
    'extract_constraints': ('epinoic_logic.channel.request_parser', 'extract_constraints'),
    'fit_summary': ('epinoic_logic.channel.bus', '_fit_summary'),
    'header_digest': ('epinoic_logic.channel.events', 'header_digest'),
    'ids_held_by_other_agents': ('epinoic_logic.channel.bus', 'ids_held_by_other_agents'),
    'located': ('epinoic_logic.channel.bus', '_located'),
    'material_claims': ('epinoic_logic.channel.bus', '_material_claims'),
    'measure_answer_words': ('epinoic_logic.channel.request_parser', 'measure_answer_words'),
    'model_json': ('epinoic_logic.channel.events', 'model_json'),
    'needs_qualified_ids': ('epinoic_logic.channel.bus', 'needs_qualified_ids'),
    'observation_state': ('epinoic_logic.channel.events', 'observation_state'),
    'per_part_bound': ('epinoic_logic.channel.request_parser', 'per_part_bound'),
    'report_bidi_findings': ('epinoic_logic.channel.bus', 'report_bidi_findings'),
    'snapshot_event': ('epinoic_logic.channel.events', 'snapshot_event'),
    'withheld_deliverable': ('epinoic_logic.channel.bus', 'withheld_deliverable'),
    'word_bound_severity': ('epinoic_logic.channel.request_parser', 'word_bound_severity'),
}

__all__, __getattr__, __dir__ = exports(__name__, EXPORTS)
