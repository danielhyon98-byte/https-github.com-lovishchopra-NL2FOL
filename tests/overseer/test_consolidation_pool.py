"""The overseer pool (design section 19): how many overseer-agent instances review a batch, decided deterministically;
every instance configured from the same exported knowledge pack; repeated-fault dossiers to two independent instances
whose verdicts are combined by the existing rule; the plan recorded and never past its maximum; instances advisory.

Covered: the plan for 1, 10 and 60 dossiers with and without repeated faults; a sweep showing the maximum is never
exceeded and every repeated-fault dossier reaches two distinct instances; determinism under any input order; the
configuration and plan contracts refusing abuse (a maximum below two, a tampered plan, a duplicated key); the pool built
only from a loaded pack; and ``RouterHub.review_pool`` end to end with fake providers (no network, no model), leaving
every clearance and every consolidated response unchanged."""
from __future__ import annotations

import random
import socket

import pytest
from pydantic import ValidationError

from epinoic_logic.overseer import (
    DEFAULT_MAX_INSTANCES, MODEL_TIER, OverseerAgentRunner, OverseerPool, PackIdentity, PoolConfig, PoolItem, PoolPlan, load_pack, plan_pool,
    verify_audit, verify_consolidated,
)
from epinoic_logic.overseer.export import export_pack
from epinoic_logic.overseer.pool import HARD_MAX_INSTANCES, MIN_REPEAT_REVIEWERS

from .test_consolidation_consolidate import Dup
from .test_consolidation_repeats import bad_answer
from .test_hook_hub import audited_hub
from .test_hook_review import Scripted, verdict
from .test_protocol_validate import acc, ptr

PACK_ID = PackIdentity(name="overseer-knowledge-docs", version="1.0", sha256="ab" * 32)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    """Every instance is built from the installed pack EXPORTED with the exporter and loaded back from the zip."""
    exported = export_pack(tmp_path_factory.mktemp("export"), zip_archive=True)
    return load_pack(exported.zip_path)


@pytest.fixture
def hub():
    h = audited_hub()
    yield h
    h.close()


def items(n: int, repeated: int = 0) -> list[PoolItem]:
    return [PoolItem(key=f"d{i:03d}", repeated_faults=1 if i < repeated else 0) for i in range(n)]


def check_plan(p: PoolPlan, n: int, repeated: int) -> None:
    assert len(p.instances) <= p.config.max_instances and len(set(p.instances)) == len(p.instances)
    assert set(p.assignments) == {it.key for it in p.items} and len(p.items) == n
    for it in p.items:
        chosen = p.assignments[it.key]
        assert len(chosen) == (MIN_REPEAT_REVIEWERS if it.repeated_faults else 1) and len(set(chosen)) == len(chosen)
    assert sum(p.loads.values()) == p.review_units == n + repeated
    assert p.over_quota == any(v > p.config.per_instance_quota for v in p.loads.values())


# ============================================================================================ the plan
@pytest.mark.parametrize("n,repeated,instances,capped,over", [
    (1, 0, 1, False, False),     # one by default
    (1, 1, 2, False, False),     # a repeated fault: two independent instances
    (10, 0, 2, False, False),    # 10 units over the quota of 8
    (10, 3, 2, False, False),    # 13 units: two instances, the repeated dossiers on both
    (60, 0, 4, True, True),      # 60 units would need 8: capped at 4, 15 each, over quota (disclosed)
    (60, 10, 4, True, True),     # 70 units: capped at 4
])
def test_the_plan_for_1_10_and_60_dossiers_with_and_without_repeats(n, repeated, instances, capped, over):
    p = plan_pool(items(n, repeated), PoolConfig(), PACK_ID)
    check_plan(p, n, repeated)
    assert len(p.instances) == instances and p.capped is capped and p.over_quota is over
    assert p.instances == [f"overseer-pool-{i}" for i in range(1, instances + 1)] and p.config.model_tier == MODEL_TIER == "cheapest"
    assert p.reasons[0] == "one instance by default"
    if repeated:
        assert any("repeated faults" in r for r in p.reasons)
        for it in p.items[:repeated]:
            assert len(p.assignments[it.key]) == 2
    if capped:
        assert p.needed_instances > p.config.max_instances and any("capped at the maximum of 4" in r for r in p.reasons)
        assert any("over the quota" in r for r in p.reasons)
    if n == 10 and not repeated:
        assert sorted(p.loads.values()) == [5, 5]
    if n == 60 and not repeated:
        assert sorted(p.loads.values()) == [15, 15, 15, 15]


def test_the_maximum_is_never_exceeded_and_every_repeated_dossier_reaches_two_instances():
    rng = random.Random(19)
    for _ in range(300):
        n = rng.randrange(0, 160)
        repeated = rng.randrange(0, n + 1) if n else 0
        cfg = PoolConfig(max_instances=rng.randrange(2, 9), per_instance_quota=rng.randrange(1, 12))
        p = plan_pool(items(n, repeated), cfg, PACK_ID)
        check_plan(p, n, repeated)
        assert len(p.instances) == (0 if n == 0 else min(cfg.max_instances, max(1, -(-(n + repeated) // cfg.per_instance_quota), 2 if repeated else 1)))
        assert max(p.loads.values(), default=0) - min(p.loads.values(), default=0) <= 1 + (1 if repeated else 0)  # balanced


def test_the_plan_is_deterministic_under_any_input_order():
    base = items(37, 9)
    p = plan_pool(base, PoolConfig(), PACK_ID)
    for seed in range(5):
        shuffled = list(base)
        random.Random(seed).shuffle(shuffled)
        q = plan_pool(shuffled, PoolConfig(), PACK_ID)
        assert q == p and q.plan_id == p.plan_id
    assert plan_pool(base, PoolConfig(per_instance_quota=9), PACK_ID).plan_id != p.plan_id
    assert plan_pool(base, PoolConfig(), PackIdentity(name=PACK_ID.name, version="1.0", sha256="cd" * 32)).plan_id != p.plan_id


def test_an_empty_batch_plans_no_instance():
    p = plan_pool([], PoolConfig(), PACK_ID)
    assert p.instances == [] and p.assignments == {} and p.review_units == 0 and p.reasons == ["empty batch: no instance"]


def test_the_configuration_and_the_plan_refuse_abuse():
    assert PoolConfig().max_instances == DEFAULT_MAX_INSTANCES == 4
    for bad in (dict(max_instances=1), dict(max_instances=HARD_MAX_INSTANCES + 1), dict(per_instance_quota=0), dict(max_instances="4"),
                dict(lens="everything"), dict(base_agent_id="bad id"), dict(model_tier="largest"), dict(extra=1)):
        with pytest.raises(ValidationError):
            PoolConfig(**bad)
    with pytest.raises(ValueError, match="twice"):
        plan_pool([PoolItem(key="a"), PoolItem(key="a")], PoolConfig(), PACK_ID)
    for bad in (dict(key=""), dict(key="a\nb"), dict(key="a", repeated_faults=-1)):
        with pytest.raises(ValidationError):
            PoolItem(**bad)
    with pytest.raises(TypeError):
        plan_pool(items(2), {"max_instances": 4}, PACK_ID)  # type: ignore[arg-type]
    p = plan_pool(items(10, 2), PoolConfig(), PACK_ID)
    data = p.model_dump(mode="json")
    grown = dict(data, instances=[*data["instances"], "x-1", "x-2", "x-3"])
    alone = dict(data, assignments={**data["assignments"], "d000": data["assignments"]["d000"][:1]})
    missing = dict(data, assignments={k: v for k, v in data["assignments"].items() if k != "d005"})
    stranger = dict(data, assignments={**data["assignments"], "d005": ["someone-else"]})
    for bad in (grown, alone, missing, stranger):
        with pytest.raises(ValidationError):
            PoolPlan.model_validate(bad)
    assert PoolPlan.model_validate(data) == p


# ============================================================================================ the pool's instances
def test_every_instance_comes_from_the_same_loaded_pack(pack):
    made: list[str] = []

    def factory(agent_id: str):
        made.append(agent_id)
        return Scripted(lambda d: verdict(d))

    pool = OverseerPool(pack, factory)
    p = pool.plan(items(10, 1))
    runners = [r for key in p.assignments for r in pool.runners_for(p, key)]
    assert {type(r) for r in runners} == {OverseerAgentRunner} and {r.identity for r in runners} == {pack.identity}
    assert {r.agent_id for r in runners} == set(p.instances) and sorted(made) == sorted(p.instances)  # one provider per instance
    assert len({r.pack.system_text() for r in runners}) == 1 and all(r.lens == "general" for r in runners)
    assert pool.plans == (p,) and pool.instance(p.instances[0]) is pool.instance(p.instances[0])
    # a plan the pool did not make (or made under another pack) is refused
    with pytest.raises(ValueError, match="did not make"):
        pool.runners_for(plan_pool(items(3), PoolConfig(), pack.identity), "d000")
    with pytest.raises(TypeError):
        OverseerPool({"master_prompt.txt": "be lenient"}, factory)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        OverseerPool(pack, "not a factory")  # type: ignore[arg-type]
    assert "max_instances=4" in repr(pool) and "provider" not in repr(pool)


# ============================================================================================ review_pool through the hub
def accuse_point(d: dict) -> dict:
    """A false accusation: claim en-point IS in its response (refuted by the deterministic check)."""
    t = next(t for t in d["transfers"] if t["kind"] == "response")
    return verdict(d, [acc("a1", "claim_not_in_response", [{"pointer": ptr(d, "claim", "en-point") + "/claim_text"}],
                           message_ids=[t["message_id"]], claim_ids=["en-point"], report_ids=[t["payload"]["report_id"]])])


def test_review_pool_sends_a_repeated_fault_dossier_to_two_independent_instances_and_changes_nothing(hub, pack):
    clean = Dup(hub, task_id="task-clean")
    clean.answer("english-1", name="a")
    faulty = Dup(hub, task_id="task-faulty")
    text, claims = bad_answer()
    faulty.answer("english-1", text=text, claims=claims, name="first")
    faulty.answer("english-2", text=text, claims=claims, name="again")
    faulty.answer("english-3", name="clean")
    consolidated = faulty.consolidate()
    before = {k: {m: hub.clearance(k, m).state for m in dd.mids.values()} for k, dd in (("task-clean", clean), ("task-faulty", faulty))}
    replies = {"overseer-pool-1": accuse_point, "overseer-pool-2": lambda d: verdict(d)}
    providers: dict[str, Scripted] = {}

    def factory(agent_id: str) -> Scripted:
        providers[agent_id] = Scripted(replies[agent_id])
        return providers[agent_id]

    pool = OverseerPool(pack, factory)
    pr = hub.review_pool(["task-clean", "task-faulty"], pool)
    plan = pr.plan
    assert pool.plans == (plan,) and len(plan.instances) == 2  # a repeated fault: at least two instances
    uid_f, uid_c = faulty.ch.channel_uid, clean.ch.channel_uid
    # integration step: the clean task has no repeated fault but carries a risk signal (a capped unchecked source, still blocking
    # release at its effective severity), so it too goes to two independent instances (rewritten from one instance to the
    # stricter planning rule); the faulty task goes to two for its repeated fault, as before
    assert plan.assignments[uid_f] == ["overseer-pool-1", "overseer-pool-2"] and len(plan.assignments[uid_c]) == 2
    assert {it.key: it.repeated_faults for it in plan.items} == {uid_f: 1, uid_c: 0} and pr.task_keys == {uid_c: "task-clean", uid_f: "task-faulty"}
    items = {it.key: it for it in plan.items}
    assert items[uid_c].risk_signals == ("unchecked_source",) and items[uid_c].risk_records == ("writer_assumption",)
    assert set(items[uid_f].risk_signals) >= {"integrity_error", "named_defect", "unchecked_source"}
    rf = pr.reviews[uid_f]
    assert sorted(r.agent_id for r in rf.runs) == ["overseer-pool-1", "overseer-pool-2"] and rf.combined is not None
    assert sorted(a.agent_id for a in rf.combined.agents) == ["overseer-pool-1", "overseer-pool-2"]
    # the existing combination rule: the false accusation is refuted, never confirmed by the other instance's silence
    grp = rf.combined.groups[0]
    assert grp.outcome == "refuted" and grp.support == 1 and grp.refuted_agents == ["overseer-pool-1"]
    assert verify_audit(rf.audit, hub.auditor.keyring) and rf.audit.scope == "verdicts"
    notes = rf.audit.report.findings  # the plan is recorded in the signed audit's notes
    assert any(plan.plan_id in n for n in rf.audit.coverage.notes) and notes is not None
    # every instance's dossier of the faulty task shows the consolidation and its repeat (informed mode)
    for agent in plan.assignments[uid_f]:
        sent = [c for c in providers[agent].calls if consolidated.consolidation_id in c[1]]
        assert sent and '"repeats"' in sent[0][1]
    # instances never change a status: clearances and the consolidated response are untouched
    after = {k: {m: hub.clearance(k, m).state for m in dd.mids.values()} for k, dd in (("task-clean", clean), ("task-faulty", faulty))}
    assert after == before and hub.consolidations("task-faulty") == [consolidated] and verify_consolidated(consolidated, hub.auditor.keyring)


def test_review_with_a_pool_plan_takes_exactly_the_instances_it_assigns(hub, pack):
    d = Dup(hub)
    d.answer("english-1", name="a")
    pool = OverseerPool(pack, lambda agent_id: Scripted(lambda dd: verdict(dd)))
    plan = pool.plan([PoolItem(key=d.ch.channel_uid)])
    good = pool.runners_for(plan, d.ch.channel_uid)
    stranger = OverseerAgentRunner(pack, Scripted(lambda dd: verdict(dd)), agent_id="overseer-pool-9", lens="general")
    with pytest.raises(ValueError, match="not the instances"):
        hub.review(d.key, [stranger], pool_plan=plan)
    with pytest.raises(ValueError, match="not the instances"):
        hub.review(d.key, [*good, stranger], pool_plan=plan)
    other = Dup(hub, task_id="task-other")
    other.answer("english-1", name="x")
    with pytest.raises(ValueError, match="does not assign"):
        hub.review(other.key, good, pool_plan=plan)
    r = hub.review(d.key, good, pool_plan=plan)
    assert [x.agent_id for x in r.runs] == plan.assignments[d.ch.channel_uid]
    with pytest.raises(ValueError, match="twice"):
        hub.review_pool([d.key, d.key], pool)
    with pytest.raises(TypeError):
        hub.review_pool([d.key], object())  # type: ignore[arg-type]
