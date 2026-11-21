"""The expectation tables of the self-certification gate after the round-10 hold remedy c3b, asserted whole: every entry of
``EXPECTED`` (147 entries flipped to the stricter value, each marked in the table), every entry of ``MARKING_EXPECTED`` in a marking
context (the router's plan only) and every entry of ``EXPECTED_UNREAD`` (an unread run, rule unread-text, never a self-certification)."""
from __future__ import annotations

import pytest

from epinoic_logic.api.adapters import SelfCertContext, selfcert_read, unread_text_runs

from .self_report_expectations import EXPECTED, EXPECTED_UNREAD, MARKING_EXPECTED, expected_self_report


@pytest.mark.parametrize("text", sorted(EXPECTED), ids=lambda t: t[:60])
def test_every_entry_of_the_table_is_read_as_fixed(text):
    expected_self_report(text)


@pytest.mark.parametrize("text", sorted(MARKING_EXPECTED), ids=lambda t: t[:60])
def test_a_marking_entry_is_a_self_certification_by_default_and_content_in_a_marking_task(text):
    assert EXPECTED[" ".join(text.split())] is True and selfcert_read(text).self_certifies() is True
    assert expected_self_report(text, SelfCertContext(marking=True)) is False


@pytest.mark.parametrize("text", EXPECTED_UNREAD, ids=lambda t: repr(t[:40]))
def test_an_unread_entry_is_an_unread_run_never_a_self_certification(text):
    reading = selfcert_read(text)
    assert reading.unread and not reading.hits and reading.refuses()
    assert unread_text_runs(text)
