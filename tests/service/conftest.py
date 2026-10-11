"""Shared fixtures for the service-boundary tests. No network: everything runs in-process."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from epinoic_logic.service import ServiceSettings, create_app

TOKEN = "test-service-token-0123456789abcdef"
KEY = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
KEY_ID = "test-key-1"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def V(name: str) -> dict[str, Any]:
    return {"op": "var", "name": name}


def I(v: int) -> dict[str, Any]:
    return {"op": "int", "value": str(v)}


def cmp(op: str, left: Any, right: Any) -> dict[str, Any]:
    return {"op": op, "left": left, "right": right}


def transitivity_problem(**overrides: Any) -> dict[str, Any]:
    """x>y, y>z |= x>z over Int: ENTAILED."""
    data = {
        "problem_id": "p1",
        "request_id": "req1",
        "claim_id": "c1",
        "query": "entailment",
        "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}, {"name": "z", "sort": "Int"}],
        "premises": [{"id": "P1", "expr": cmp("gt", V("x"), V("y"))}, {"id": "P2", "expr": cmp("gt", V("y"), V("z"))}],
        "conclusion": {"id": "C", "expr": cmp("gt", V("x"), V("z"))},
    }
    data.update(overrides)
    return data


def nonlinear_problem() -> dict[str, Any]:
    """x*y = 6 over Int: a product of two variables is outside policy v1 -> UNSUPPORTED (E201)."""
    return {
        "problem_id": "p2",
        "request_id": "req1",
        "claim_id": "c2",
        "query": "satisfiability",
        "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}],
        "premises": [{"id": "P1", "expr": cmp("eq", {"op": "mul", "args": [V("x"), V("y")]}, I(6))}],
    }


def make_settings(**overrides: Any) -> ServiceSettings:
    values: dict[str, Any] = dict(service_token=TOKEN, signing_key=KEY, signing_key_id=KEY_ID)
    values.update(overrides)
    return ServiceSettings(**values)


def make_client(settings: ServiceSettings | None = None, **app_kwargs: Any) -> TestClient:
    app = create_app(settings or make_settings(), **app_kwargs)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return make_client()
