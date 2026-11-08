"""The flash router's pool operation (``pool_hello``/``pool_plan``, pool port 1.1; the translator's
``integration/PROTOCOL.md`` section 7b), validated with the translator's own ``router_pool`` contract, as the overseer
validates it:

- the pool hello passes the version handshake and declares the ``pool-plan`` capability under this release's identity;
- every pool plan for generated batches is in contract (``check_pool_plan``), covers every dossier, gives every escalated
  dossier at least two distinct instances (the overseer's floor: it refuses any plan that does not) and never more
  instances than the pool's maximum;
- the released rules carry the overseer pool's planning decision (instance counts, assignment, capping, reasons);
- deterministic: the same request text gives the same plan text, in a fresh interpreter too;
- data-driven: the same planner over an edited copy of the data plans otherwise (more duplicates, other batch sizes),
  and a weakened copy plans below the floor, which only the overseer refuses (its tests).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from epinoic_logic.integration import router_pool as RP
from epinoic_logic.integration.errors import IntegrationError

from epinoic_flash_router import __version__, port, rules

PROJECT = Path(__file__).resolve().parents[2]
CLASSES = list(RP.POOL_RISK_CLASSES)


def _request(items: list[dict], *, max_instances: int = 4, quota: int = 8, profiles=("standard",)) -> RP.PoolRoutingRequest:
    return RP.build_pool_request(items, max_instances=max_instances, per_instance_quota=quota, profiles=profiles)


def _plan(req: RP.PoolRoutingRequest, router: port.FlashRouter | None = None) -> RP.PoolRoutingPlan:
    r = router or port.FlashRouter()
    hello = RP.check_pool_hello(r.pool_hello())
    return RP.check_pool_plan(r.pool_plan(RP.canonical_json(RP.dump(req))), req, hello=hello)


def _item(repeated: int = 0, signals=(), records=(), advised: bool = False) -> dict:
    return {"repeated_faults": repeated, "risk_signals": sorted(set(signals)), "risk_records": sorted(set(records)), "advised": advised}


def _wire(plan: RP.PoolRoutingPlan) -> dict:
    """The plan as its JSON document: a reason carries only the parameters its code takes."""
    data = RP.dump(plan)
    data["reasons"] = [{k: v for k, v in r.items() if v is not None} for r in data["reasons"]]
    return data


def _escalated(it: RP.PoolItemFeatures) -> bool:
    return bool(it.repeated_faults or it.risk_signals or it.advised)


# ----------------------------------------------------------------------------------------------- the handshake
def test_the_pool_hello_passes_the_version_handshake_and_names_this_release():
    h = RP.check_pool_hello(port.pool_hello())
    assert h.port_version == RP.POOL_PORT_VERSION and h.port_version in RP.POOL_PORT_VERSIONS
    assert RP.POOL_CAPABILITY in h.capabilities and set(h.methods) == set(RP.POOL_RUN_METHODS) and h.tier == "cheapest"
    assert RP.dump(h.router) == port.IDENTITY == {"name": "epinoic-flash-router", "version": __version__, "rules_sha256": rules.RULES_SHA256,
                                                  "cost_data_sha256": rules.COST_DATA_SHA256}
    assert port.pool_hello() == port.pool_hello()
    for version in ("1.0", "2.0"):
        with pytest.raises(IntegrationError, match=f"pool port version {version}") as exc:
            RP.check_pool_hello(port.pool_hello().replace('"port_version":"1.1"', f'"port_version":"{version}"'))
        assert exc.value.code == "KIT-RT-015"
    with pytest.raises(IntegrationError, match="capability"):
        RP.check_pool_hello(port.pool_hello().replace('"capabilities":["pool-plan"]', '"capabilities":["plan"]'))


# ----------------------------------------------------------------------------------------------- the released decision
@pytest.mark.parametrize("n,repeated,instances,capped,over,loads", [
    (1, 0, 1, False, False, [1]),
    (1, 1, 2, False, False, [1, 1]),
    (10, 0, 2, False, False, [5, 5]),
    (10, 3, 2, False, False, [7, 6]),
    (60, 0, 4, True, True, [15, 15, 15, 15]),
    (60, 10, 4, True, True, None),
])
def test_the_released_rules_carry_the_pools_planning_decision(n, repeated, instances, capped, over, loads):
    """The overseer pool's planner before step 2c, for 1, 10 and 60 dossiers with and without repeated faults."""
    plan = _plan(_request([_item(repeated=1 if i < repeated else 0) for i in range(n)]))
    assert (plan.instances, plan.capped, plan.over_quota) == (instances, capped, over)
    assert loads is None or plan.loads == loads
    assert plan.review_units == n + repeated and sum(plan.loads) == plan.review_units
    for i, a in enumerate(plan.assignments):
        assert len(a.instances) == (2 if i < repeated else 1) and a.method == ("DUPLICATE" if i < repeated else "IN_DEPTH")
    codes = [r.code for r in plan.reasons]
    assert codes[0] == "pool_baseline" and (("pool_capped" in codes) == capped) and (("pool_repeated_faults" in codes) == bool(repeated))


def test_risk_records_weigh_two_units_and_signals_go_to_two_instances():
    plan = _plan(_request([_item(records=["writer_assumption"]), _item()], quota=2))
    assert (plan.review_units, plan.instances) == (3, 2)
    assert [r.code for r in plan.reasons] == ["pool_baseline", "pool_volume", "pool_risk_records"]
    risky = _plan(_request([_item(signals=["named_defect"])]))
    assert risky.assignments[0].instances == [1, 2] and risky.reasons[-1].classes == ["named_defect"]
    advised = _plan(_request([_item(), _item(advised=True)]))
    assert advised.assignments[1].instances == [1, 2] and [r.code for r in advised.reasons] == ["pool_baseline", "pool_advised"]


def test_an_empty_batch_plans_no_instance():
    plan = _plan(_request([]))
    assert (plan.instances, plan.assignments, plan.loads, [r.code for r in plan.reasons]) == (0, [], [], ["pool_empty"])


_ITEM = st.fixed_dictionaries({
    "repeated_faults": st.integers(0, 2), "advised": st.booleans(),
    "risk_signals": st.lists(st.sampled_from(CLASSES), max_size=3, unique=True).map(sorted),
    "risk_records": st.lists(st.sampled_from(["writer_assumption", "unchecked_source", "stem_method"]), max_size=2, unique=True).map(sorted),
})


@settings(max_examples=200, deadline=None)
@given(st.lists(_ITEM, max_size=60), st.integers(2, 64), st.integers(1, 20), st.sampled_from([("standard",), ("standard", "fast"), ("fast",)]))
def test_every_generated_batch_is_planned_in_contract_and_at_or_above_the_floor(items, max_instances, quota, profiles):
    req = _request(items, max_instances=max_instances, quota=quota, profiles=profiles)
    plan = _plan(req)
    assert [a.item_id for a in plan.assignments] == [it.item_id for it in req.items]
    assert plan.instances <= max_instances and plan.profile == ("standard" if "standard" in profiles else profiles[0])
    for it, a in zip(req.items, plan.assignments):
        assert len(set(a.instances)) >= (2 if _escalated(it) else 1), "the overseer's floor"
    assert _wire(plan) == json.loads(port.pool_plan(RP.canonical_json(RP.dump(req)))), "an exact round trip"


# ----------------------------------------------------------------------------------------------- determinism
def test_the_same_request_text_gives_the_same_plan_text_in_a_fresh_interpreter_too():
    req = _request([_item(repeated=1), _item(signals=["contradiction"]), _item(records=["stem_method"])] + [_item() for _ in range(9)], quota=3)
    text = RP.canonical_json(RP.dump(req))
    assert port.pool_plan(text) == port.pool_plan(text)
    code = "import sys; from epinoic_flash_router import port; sys.stdout.write(port.pool_plan(sys.stdin.read()))"
    outs = set()
    for seed in ("1", "2"):
        env = {"PYTHONHASHSEED": seed, "PYTHONPATH": str(PROJECT / "src"), "PATH": os.environ.get("PATH", "")}
        proc = subprocess.run([sys.executable, "-c", code], input=text, capture_output=True, text=True, env=env, timeout=60, cwd=PROJECT)
        assert proc.returncode == 0, proc.stderr
        outs.add(proc.stdout)
    assert outs == {port.pool_plan(text)}


# ----------------------------------------------------------------------------------------------- data-driven
def _copy_data(tmp_path: Path, edit) -> str:
    dest = tmp_path / "data"
    shutil.copytree(Path(rules.DATA_DIR), dest)
    manifest = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    path = dest / manifest["current"]["rules"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    edit(doc)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    return str(dest)


def test_an_edited_copy_of_the_data_plans_otherwise_and_names_its_own_digest(tmp_path):
    req = _request([_item(repeated=1)] + [_item() for _ in range(9)])
    released = _plan(req)

    def retune(doc):
        doc["pool"].update(batch_size=4, escalated_reviewers=3)
    edited = port.FlashRouter(_copy_data(tmp_path, retune))
    plan = _plan(req, edited)
    assert edited.identity["rules_sha256"] != rules.RULES_SHA256 and plan.router.rules_sha256 == edited.identity["rules_sha256"]
    assert (released.instances, len(released.assignments[0].instances)) == (2, 2)
    assert (plan.instances, len(plan.assignments[0].instances)) == (3, 3), "a smaller batch and an extra duplicate"


def test_a_weakened_copy_plans_below_the_floor_which_is_the_overseers_to_refuse(tmp_path):
    def weaken(doc):
        doc["pool"]["escalated_reviewers"] = 1
    weak = port.FlashRouter(_copy_data(tmp_path, weaken))
    req = _request([_item(repeated=1), _item(signals=["rejection"])])
    plan = _plan(req, weak)  # in contract: the contract holds no floor
    assert [len(a.instances) for a in plan.assignments] == [1, 1], "below the floor: the overseer refuses it (KIT-RT-020) and runs its floor plan"


def test_the_port_rules_read_their_signals_and_features_from_the_data(tmp_path):
    def drop_stem_undecided(doc):
        doc["signals"]["stem_undecided_codes"] = []
        doc["features"]["port"] = ["receipt"]
    edited = port.FlashRouter(_copy_data(tmp_path, drop_stem_undecided))
    vector = json.loads((PROJECT / "tests" / "vectors" / "router-port" / "single-at-floor.json").read_text(encoding="utf-8"))["request"]
    plan = json.loads(edited.plan(json.dumps(vector)))
    assert all(t["features_used"] == ["receipt"] for t in plan["transfers"]) and plan["router"] == edited.identity
