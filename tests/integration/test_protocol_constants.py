"""Every constant the protocol carries verbatim is pinned to its source."""
from __future__ import annotations

from epinoic_logic.engine.statuses import DEFINITIVE as ENGINE_DEFINITIVE
from epinoic_logic.engine.statuses import SCOPE_STATEMENT as ENGINE_SCOPE
from epinoic_logic.engine.statuses import VerificationStatus
from epinoic_logic.integration import protocol as P
from epinoic_logic.integration.router_port import FEATURE_NAMES, REASON_CODES
from tests.integration.helpers import runtime_fixture


def test_scope_statement_is_the_engines_verbatim():
    assert P.SCOPE_STATEMENT == ENGINE_SCOPE


def test_the_thirteen_statuses_and_the_definitive_six_are_the_engines():
    assert P.STATUSES == tuple(s.value for s in VerificationStatus)
    assert P.DEFINITIVE == frozenset(s.value for s in ENGINE_DEFINITIVE)
    assert P.POSITIVE | P.NEGATIVE == P.DEFINITIVE and not P.POSITIVE & P.NEGATIVE
    assert P.NOT_ATTEMPTED not in P.STATUSES and P.NOT_ATTEMPTED in P.INCOMPLETE_STATUSES
    assert not P.INCOMPLETE_STATUSES & P.DEFINITIVE


def test_the_gate_disclaimer_is_the_runtimes_verbatim_in_both_runtime_versions():
    assert runtime_fixture(1)["answer"]["result"]["gate"]["disclaimer"] == P.GATE_DISCLAIMER
    assert runtime_fixture(2)["answer"]["result"]["gate"]["disclaimer"] == P.GATE_DISCLAIMER


def test_the_audit_scope_sentence_is_the_designs_tr6_text():
    # The overseer package (phase 2) carries the same sentence as AUDIT_SCOPE_SENTENCE; the port refuses an audit without it.
    assert P.AUDIT_SCOPE_STATEMENT.startswith("This audit covers only the transfers journaled since the auditor was attached")
    assert P.AUDIT_SCOPE_STATEMENT.endswith("It does not show that any claim is true or any reading correct.")


def test_closed_router_vocabularies_carry_no_free_text():
    for word in REASON_CODES + FEATURE_NAMES:
        assert word.replace("_", "").isalpha() and word == word.lower()
