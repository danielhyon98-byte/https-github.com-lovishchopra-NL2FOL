"""Re-run review findings over HTTP: security-1 (a forged signature holding non-ASCII text made both signature routes
answer 500 E900, because the check raised) and robustness-and-contracts-5 (a lone surrogate escape in a problem answered
INTERNAL_ERROR). In process only; nothing is deployed. (security-7, the key id under the signature, is tested in process:
this service already refuses any key id but its own.)"""
from __future__ import annotations

import pytest

from .conftest import AUTH, KEY_ID, transitivity_problem


@pytest.mark.parametrize("forged", ["é" * 64, "A" * 64, "0" * 63, "not a signature"])
def test_a_forged_signature_is_refused_not_an_internal_error(client, forged: str):
    signed = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    body = {**signed, "signature": forged}
    r = client.post("/v1/results/verify-signature", json={"result": body}, headers=AUTH)
    assert r.status_code == 200 and r.json()["valid"] is False
    r = client.post("/v1/results/release-check", json={"result": body, "problem": transitivity_problem()}, headers=AUTH)
    assert r.status_code == 200 and r.json()["eligible"] is False and any(why.startswith("unauthenticated") for why in r.json()["reasons"])


def test_the_genuine_signature_is_still_valid(client):
    """Control."""
    signed = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    assert signed["signature_key_id"] == KEY_ID
    assert client.post("/v1/results/verify-signature", json={"result": signed}, headers=AUTH).json() == {"valid": True}


def test_a_problem_holding_a_lone_surrogate_escape_is_an_invalid_formalization_over_http(client):
    """Re-run review finding robustness-and-contracts-5 over HTTP: a "\\ud83d" escape anywhere in the problem answered 200
    INTERNAL_ERROR (E900), raised while the rejection was being bound. Rewritten to the merged rule: the service refuses
    any body holding a lone surrogate escape at the envelope, 400 E100 before anything runs (robustness-and-contracts-6,
    on every route), so no result is built from it and nothing is INTERNAL_ERROR; the same payload in process is
    INVALID_FORMALIZATION (E100), bound and signed, never E900."""
    import json

    from epinoic_logic.engine import verify, verify_signature
    from epinoic_logic.engine.results import SolverConfig

    from .conftest import KEY

    payload = {**transitivity_problem(), "problem_id": "\ud83d"}
    body = json.dumps({"problem": payload})  # json.dumps writes the escape
    assert "\\ud83d" in body
    r = client.post("/v1/verify", content=body.encode("ascii"), headers={**AUTH, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["code"] == "E100" and "surrogate" in r.json()["message"], r.text
    assert "E900" not in r.text
    # in process, the same payload is a bound, signed INVALID_FORMALIZATION (E100), never INTERNAL_ERROR
    result = verify(payload, SolverConfig(memory_max_mb=None), signing_key=KEY, key_id=KEY_ID)
    assert result.status.value == "INVALID_FORMALIZATION" and [d.code for d in result.diagnostics][:1] == ["E100"]
    assert "E900" not in [d.code for d in result.diagnostics] and result.signature_key_id == KEY_ID and verify_signature(result, KEY)
    # control: the same problem without the escape is decided
    ok = client.post("/v1/verify", json={"problem": transitivity_problem()}, headers=AUTH).json()
    assert ok["status"] == "ENTAILED"
