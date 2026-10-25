"""Repair round 3, INV-6 over HTTP: the service names the key id of a record signed in an earlier build's form as not
attested, even when the record is relabelled to the service's own key id, and still answers a bare ``{"valid": true}`` for
a result it signed in the current form. In process only; nothing is deployed."""
from __future__ import annotations

import json
from pathlib import Path

from .conftest import AUTH, KEY_ID, make_client, make_settings, transitivity_problem

DATA = Path(__file__).parents[1] / "engine" / "data"
NOT_ATTESTED = {"valid": True, "key_id_attested": False,
                "reason": "signed in an earlier build's form, which does not cover the key id: the key id is not attested"}


def test_a_legacy_record_relabelled_to_the_service_key_id_is_reported_as_not_attesting_it():
    entry = json.loads((DATA / "release_0_3_0_signed_results.json").read_text())["trusted_kind_chain"]
    client = make_client(make_settings(signing_key=b"upgrade-test-key-0123456789abcdef", signing_key_id="service-id"))
    relabelled = {**entry["result"], "signature_key_id": "service-id"}
    assert client.post("/v1/results/verify-signature", json={"result": relabelled}, headers=AUTH).json() == NOT_ATTESTED
    check = client.post("/v1/results/release-check", json={"result": relabelled, "problem": entry["problem"]}, headers=AUTH).json()
    assert check["eligible"] is False and any(why.startswith("key id not attested") for why in check["reasons"])


def test_control_a_current_result_of_the_service_is_simply_valid(client):
    signed = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    assert signed["signature_key_id"] == KEY_ID
    assert client.post("/v1/results/verify-signature", json={"result": signed}, headers=AUTH).json() == {"valid": True}
