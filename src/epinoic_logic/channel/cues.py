"""Cue phrases shared by the channel and the subject parsers.

The channel decides whether a report states a position on degree (INT-REQ-008) from the
same phrases the History parser uses to role a sentence as a judgement, so the two never
disagree about what a verdict looks like. This module has no imports, so any adapter can
import it without a cycle: ``from epinoic_logic.channel.cues import VERDICT_CUES``.
"""
from __future__ import annotations

#: Phrases that state a position on degree or a weighing of factors, lower-cased, matched on word boundaries
#: (``verdict_cue_regex``) or by substring on a lower-cased sentence. A bare claim ("X was responsible for Y") is not one.
#: Inflections are spelled out so a plain substring test works without stemming.
VERDICT_CUES: tuple[str, ...] = (
    "therefore", "thus",
    "to a large extent", "to a great extent", "to a limited extent", "to a lesser extent", "to some extent", "to a considerable extent",
    "to a degree",
    "decisive",
    "necessary but not sufficient", "necessary but sufficient", "necessary and sufficient", "necessary and not sufficient",
    "outweigh", "outweighs", "outweighed", "outweighing",
    "on balance",
    "more significant than", "more important than", "more decisive than",
    "less significant than", "less important than",
    "matters most", "mattered most",
    "the most significant", "the most important", "the most decisive",
    "by the criteria", "by the criterion", "by this criterion", "by that criterion",
    "weighed by", "weighs more", "weighed against", "carries the greater weight", "carry the greater weight",
    "holds for", "does not hold", "fails",
)


def verdict_cue_regex() -> str:
    """A regular-expression alternation of :data:`VERDICT_CUES`, longest phrase first, for use between ``\\b``."""
    import re  # local: the module stays import-free for its consumers
    return "|".join(re.escape(c) for c in sorted(VERDICT_CUES, key=len, reverse=True))
