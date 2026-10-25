"""The B26 sweep beyond the IR (identifiers and literals matched whole, ``fullmatch``): a structured report's
``created_at`` with a trailing newline is no RFC 3339 timestamp, as ``x\\n`` is no IR symbol."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.base import AdapterError

from .test_generic import document, parse


@pytest.mark.parametrize("stamp", ["2026-10-17T00:00:00Z\n", "2026-10-17T00:00:00+01:00\n", "2026-10-17T00:00:00Z junk"])
def test_a_timestamp_with_anything_after_it_is_refused(stamp):
    with pytest.raises(AdapterError, match="created_at is not an RFC 3339 timestamp"):
        parse(document(created_at=stamp))


@pytest.mark.parametrize("stamp", ["2026-10-17T00:00:00Z", "2026-10-17T00:00:00.123+01:00"])
def test_control_a_whole_timestamp_is_kept(stamp):
    assert parse(document(created_at=stamp)).created_at == stamp
