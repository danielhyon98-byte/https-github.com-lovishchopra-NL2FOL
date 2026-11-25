"""Fixtures of the label package's tests. Every label here is scripted or made by the faithful fake: no provider is called and
no connection is opened. The prompt author's ``prompt.md`` is read as opaque data; tests whose expected values must not move
when that file is edited render with a fixed test prompt instead (``test_prompt``)."""
from __future__ import annotations

import pathlib

import pytest

from epinoic_logic.selfcert_label.fakes import TEST_KEY

#: The receipt codes a caller gives ``LabelResult.findings`` (the design's codes; the channel names them in stage 2, where the
#: overseer's code tables register them).
CODES = {"named": "INT-SELF-001", "unavailable": "INT-SELF-002"}

#: The fixed system text of the golden values (never the frozen prompt, which the prompt author owns).
TEST_PROMPT = "Fixed system text of the selfcert-label test suite.\n"


@pytest.fixture
def test_prompt(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "prompt.md"
    p.write_text(TEST_PROMPT, encoding="utf-8")
    return p


@pytest.fixture
def key() -> bytes:
    return TEST_KEY
