"""The c3e follow-up, overseer paths (expected values fixed here).

Version discipline of eligibility rule 0 (push check of the c3 clearance fixes, its version item): the translator's one
self-certification reader states its rules (``SELFCERT_RULES``) and moves them with every change to the rule's code. The overseer
calls that reader through the public API and keeps no rules of its own, so its code must never name a rules version the reader no
longer states: two docstrings named ``selfcert-1`` after the reader moved on. The overseer's source names the rules by their
constant, never by a version string.
"""
from __future__ import annotations

import re
from pathlib import Path

import epinoic_overseer
from epinoic_logic.api.adapters import SELFCERT_RULES

OVERSEER_SRC = Path(epinoic_overseer.__file__).resolve().parent
_RULES_VERSION_RE = re.compile(r"\bselfcert-\d+\b")


def test_the_overseer_source_names_no_selfcert_rules_version():
    named = sorted({(p.relative_to(OVERSEER_SRC).as_posix(), m.group(0)) for p in OVERSEER_SRC.rglob("*.py")
                    for m in _RULES_VERSION_RE.finditer(p.read_text(encoding="utf-8"))})
    assert named == [], (SELFCERT_RULES, named)


def test_the_rules_constant_is_read_through_the_public_api():
    # the reader states its rules; the overseer reads them where it needs them, never a copy
    assert _RULES_VERSION_RE.fullmatch(SELFCERT_RULES), SELFCERT_RULES
