"""The auditor's self-certification detector (FID-009): a thin call into the one reader (round-10 hold remedy c3b).

Before c3b this module held its own token rules and closed lexicon (a subject of the answer's own items, a checking or accuracy
predicate, negation and modal vetoes), read beside the translator's reader. Two readers drifted: each push check found sentences
one named and the other freed. The one reader (``epinoic_logic.selfcert``, rules ``selfcert-1``, through the public API) reads the
class by meaning; :func:`flags_self_certification` keeps its name and signature because ``overseer/scripts/mutate_auditor.py``
mutates it, and FID-009 and FID-005 now never disagree. The rule only ever yields a warning (FID-009), never an error.
"""
from __future__ import annotations

import re

__all__ = ["flags_self_certification", "sentences"]

_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n(?=\s*(?:[-*•]|\d{1,2}[.)])\s)")


def sentences(text: str) -> list[str]:
    return [s for s in _SENT_RE.split(text or "") if s and s.strip()]


def flags_self_certification(sentence: str, ctx=None) -> bool:
    """True when the one reader names ``sentence`` a self-certification (``selfcert.is_self_certification``), read in ``ctx`` (the
    context of the router's journaled request, ``selfcert.context_for``; None: the strict default), as FID-005 reads it."""
    from epinoic_logic.api.adapters import is_self_report
    return bool(is_self_report(sentence, ctx))
