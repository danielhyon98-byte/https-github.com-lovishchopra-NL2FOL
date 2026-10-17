"""Closed codes and the canonical JSON of the integration protocol."""
from __future__ import annotations

import json
import re

import pytest
from hypothesis import given, settings, strategies as st

from epinoic_logic.integration import canonical as C
from epinoic_logic.integration.errors import (
    CODES, COMBINATOR_PORT_CODES, DELIVERY_CODES, HANDSHAKE_CODES, OVERSEER_PORT_CODES, REQUEST_CODES, ROUTER_PORT_CODES,
    WORKER_RAW_CODES, IntegrationError, code_line,
)
from epinoic_logic.ir.canonical import canonical_json as ir_canonical_json


def test_handshake_codes_are_exactly_001_to_016():
    assert sorted(HANDSHAKE_CODES) == [f"KIT-HS-{n:03d}" for n in range(1, 17)]
    assert HANDSHAKE_CODES["KIT-HS-003"] == "z3_unavailable"
    assert HANDSHAKE_CODES["KIT-HS-007"] == "overseer_unavailable"


def test_every_code_is_unique_well_formed_and_named():
    families = [HANDSHAKE_CODES, REQUEST_CODES, DELIVERY_CODES, OVERSEER_PORT_CODES, COMBINATOR_PORT_CODES, ROUTER_PORT_CODES]
    assert sum(len(f) for f in families) == len(CODES)
    for code, name in CODES.items():
        assert re.fullmatch(r"KIT-(HS|REQ|DL|OP|CB|RT)-[0-9]{3}", code), code
        assert re.fullmatch(r"[a-z][a-z0-9_]{2,63}", name), name
    assert ROUTER_PORT_CODES["KIT-RT-020"] == "below_floor"


def test_integration_error_names_its_code_and_refuses_unknown_codes():
    e = IntegrationError("KIT-HS-006", "detail")
    assert e.line() == "KIT-HS-006 named_policies_unavailable" == code_line("KIT-HS-006")
    assert str(e).startswith(e.line())
    with pytest.raises(ValueError):
        IntegrationError("KIT-HS-999")


def test_worker_raw_codes_are_closed_and_website_shaped():
    assert len(set(WORKER_RAW_CODES)) == len(WORKER_RAW_CODES)
    for code in WORKER_RAW_CODES:
        assert re.fullmatch(r"[a-z0-9_]{1,64}", code)
    assert {f"kit_dl_{c[-3:]}" for c in DELIVERY_CODES} <= set(WORKER_RAW_CODES)


@pytest.mark.parametrize("text", [
    '{"a":1.5}', '{"a":NaN}', '{"a":Infinity}', '{"a":1,"a":2}', '[1e3]', '{"a":"\\ud800"}', '{"\\udc00":1}', '"x', '{"a":9007199254740992}',
])
def test_strict_parsing_refuses_floats_constants_duplicates_lone_surrogates_and_unsafe_integers(text):
    with pytest.raises(C.CanonicalError):
        C.loads_strict(text)


def test_strict_parsing_refuses_non_utf8_and_deep_nesting():
    with pytest.raises(C.CanonicalError):
        C.loads_strict(b"\xff\xfe{}")
    with pytest.raises(C.CanonicalError):
        C.loads_strict("[" * 100 + "]" * 100)


def test_canonical_form_sorts_by_code_point_and_matches_the_ir_canonical_form():
    value = {"b": [1, "é", {"z": None, "a": True}], "a": "x y\n", "\U0001f600": 1, "Ａ": 2}
    text = C.canonical_json(value)
    assert text == ir_canonical_json(value)
    assert text.index('"Ａ"') < text.index('"\U0001f600"')  # code-point order, not UTF-16 order
    assert C.sha256_json(value) == C.sha256_text(text)


json_scalars = st.one_of(st.none(), st.booleans(), st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1),
                         st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=12))
json_values = st.recursive(json_scalars, lambda children: st.one_of(st.lists(children, max_size=4),
                                                                    st.dictionaries(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=6), children, max_size=4)),
                           max_leaves=20)


@settings(max_examples=200, deadline=None)
@given(json_values)
def test_canonical_round_trip_property(value):
    text = C.canonical_json(value)
    assert C.loads_strict(text) == value
    assert C.canonical_json(C.loads_strict(text)) == text
    assert text == ir_canonical_json(value)
    assert json.loads(text) == value
