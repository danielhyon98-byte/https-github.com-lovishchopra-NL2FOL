"""STEM specialist adapter: ``StemTextParser`` (claims from answers that mix equations and prose).

Used by the ``sciences``, ``mathematics`` and ``computer_science`` branches
(``branches.registry``). The parser and ``branches.stem_pack.StemPack`` read one shared
``stem.document.StemDocument`` per answer, request and profile (docs/STEM_DESIGN.md, section 9).
"""
from __future__ import annotations

from .parser import CHECKS_ASSUMPTION, ID_PREFIXES, MODE_PROFILES, TAIL_CLAIM_ID, StemTextParser, claim_id_for, stem_profile_key

__all__ = ["CHECKS_ASSUMPTION", "ID_PREFIXES", "MODE_PROFILES", "StemTextParser", "TAIL_CLAIM_ID", "claim_id_for", "stem_profile_key"]
