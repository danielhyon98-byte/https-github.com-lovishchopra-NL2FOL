"""What the kit can rehearse of the rollback without a website export (integration/rollback/ROLLBACK.md): a service
rolled back to an incompatible version is refused by the Worker's handshake rules and never answers unchecked; a
detached flash router leaves the floor plan running; the engine profile serves exactly the routes it served before
the kit (the pre-kit route table is pinned here from the base commit)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from epinoic_logic.integration import router_port as R
from epinoic_logic.integration.handshake import evaluate
from epinoic_logic.service import ServiceSettings, create_app
from tests.integration.helpers import routing_request

ROOT = Path(__file__).resolve().parents[2]
COMPATIBLE = json.loads((ROOT / "integration" / "vectors" / "handshake" / "compatible.json").read_text(encoding="utf-8"))["capabilities"]
#: The engine profile's routes at the commit the kit was built on (no integration route among them).
ENGINE_ROUTES = [("/healthz", ("GET",)), ("/v1/outcomes", ("POST",)), ("/v1/results/release-check", ("POST",)),
                 ("/v1/results/verify-signature", ("POST",)), ("/v1/verify", ("POST",))]


@pytest.mark.parametrize("component,version", [("engine", "0.3.0"), ("ir", "0.9"), ("policy", "2026.09-v3"), ("translator", "0.3.1"), ("contract", "0.2")])
def test_a_service_rolled_back_to_an_incompatible_version_is_refused_by_the_worker(component, version):
    caps = copy.deepcopy(COMPATIBLE)
    caps["versions"][component] = version
    out = evaluate(caps, worker_env="sim")
    assert not out.ok and out.code == "KIT-HS-002" and out.raw_code == "kit_hs_mismatch"


def test_a_service_without_a_passing_selftest_or_the_overseer_is_refused():
    for path, value, code in ((("selftest", "passed"), False, "KIT-HS-004"), (("ports", "overseer", "mode"), "sidecar", "KIT-HS-007")):
        caps = copy.deepcopy(COMPATIBLE)
        node = caps
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        out = evaluate(caps, worker_env="sim")
        assert (out.ok, out.code, out.raw_code) == (False, code, "kit_hs_mismatch")


def test_a_detached_router_leaves_the_floor_running():
    att = R.attach_router("none")
    adm = R.route(R.check_request(routing_request()), att)
    assert not att.attached and adm.origin == "floor" and adm.refusal is None and adm.effective.plan_id == adm.floor.plan_id


def test_the_engine_profile_serves_exactly_its_pre_kit_routes():
    app = create_app(ServiceSettings(service_token="t" * 32, signing_key=b"k" * 32))
    routes = sorted((r.path, tuple(sorted(getattr(r, "methods", None) or []))) for r in app.routes)
    assert routes == ENGINE_ROUTES
