"""Round-7 hand-off (security-1) on the integration side: ``verify_verdict_signature`` is total on untrusted input.

``hmac.compare_digest(str, str)`` raises ``TypeError`` ("comparing strings with non-ASCII characters is not supported")
for a forged signature value holding a non-ASCII or surrogate character, so a forged verdict could raise into its
receiver instead of being refused. A signature value that is not 64 lowercase hex characters now never matches and never
raises (the engine's ``provenance.signature_matches`` rule, kept in ``delivery.py``, which never imports the engine)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from epinoic_logic.integration.delivery import verify_verdict_signature

VECTORS = Path(__file__).resolve().parents[2] / "integration" / "vectors"
KEY = bytes.fromhex("5e" * 32)


def _good_verdict():
    return json.loads((VECTORS / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))["verdict"]


@pytest.mark.parametrize("value", ["é" * 64, "\ud83d" * 64, "\udc00" + "0" * 63, "ü", "A" * 64, "0" * 65, ""],
                         ids=["latin", "lone-high-surrogate", "lone-low-surrogate", "short-non-ascii", "upper-hex", "long", "empty"])
def test_a_forged_signature_value_reads_false_and_never_raises(value):
    v = _good_verdict()
    assert verify_verdict_signature(v, KEY)  # control: the vector's genuine signature verifies
    forged = copy.deepcopy(v)
    forged["signature"]["value"] = value
    assert verify_verdict_signature(forged, KEY) is False


def test_the_genuine_signature_written_in_upper_case_is_not_the_signature():
    v = _good_verdict()
    forged = copy.deepcopy(v)
    forged["signature"]["value"] = v["signature"]["value"].upper()
    assert v["signature"]["value"] != forged["signature"]["value"] and verify_verdict_signature(forged, KEY) is False
