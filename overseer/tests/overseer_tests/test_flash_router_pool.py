"""The overseer pool's planning decision in the flash router, behind the overseer's minimum-oversight floor
(architecture step 2c; design section 51; ``floor.py``; the router: ``flash-router/``).

- with the router attached, the plan for every recorded transfer of r2, r3, r4, r5 and r7 (each channel alone, and each
  round's genuine and full batches) is the plan the overseer's own planner made before the decision moved, recorded on
  the base commit (``data/recorded_pool_plans.json``), and it records the router's identity, version and rules digest;
- the router absent: the floor plan runs, keeps every recorded escalation, and is recorded as the floor's;
- the version handshake: a router that speaks another pool port version, lacks the capability or names another identity
  in its plan is refused with a named code and the floor runs;
- editing a rule in a scratch copy of the router's data file changes the plan without any change to the translator or the
  overseer; a deliberately weakened data file cannot lower oversight below the floor (a named refusal, recorded in the
  signed audit, and the floor plan runs);
- determinism, the escalation advisor (escalation only, off by default) and the overseer never importing the router.
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import shutil
from pathlib import Path

import pytest

import epinoic_logic
import epinoic_overseer
from epinoic_logic.integration import router_pool as RP
from epinoic_overseer import OverseerPool, PackIdentity, PoolConfig, PoolItem, PoolPlan, plan_pool, verify_audit
from epinoic_overseer.floor import POOL_FLOOR_NAME, POOL_FLOOR_RULES_SHA256, admission_note, below_floor, floor_reviewers
from epinoic_overseer.pool import MIN_REPEAT_REVIEWERS

from .flash_router_support import attach, attach_in_process, flash_router_src, require_flash_router

DATA = Path(__file__).resolve().parent / "data" / "recorded_pool_plans.json"
OVERSEER_SRC = Path(epinoic_overseer.__file__).resolve().parent
TRANSLATOR_SRC = Path(epinoic_logic.__file__).resolve().parent
PACK_ID = PackIdentity(name="overseer-knowledge-docs", version="1.0", sha256="ab" * 32)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


@pytest.fixture(scope="module")
def recorded() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def router():
    """The released router, attached as a deployment attaches it: by module name, in its own process."""
    att = attach()
    assert att.attached and not att.in_process, att.detail
    return att


def _manifest() -> dict:
    return json.loads((flash_router_src() / "epinoic_flash_router" / "data" / "MANIFEST.json").read_text(encoding="utf-8"))


def _items(n: int, *, repeated: int = 0, risky: int = 0, records: int = 0) -> list[PoolItem]:
    out = []
    for i in range(n):
        kw = {}
        if i < repeated:
            kw["repeated_faults"] = 1
        elif i < repeated + risky:
            kw["risk_signals"] = ("named_defect",)
        elif i < repeated + risky + records:
            kw["risk_records"] = ("writer_assumption",)
        out.append(PoolItem(key=f"t{i:03d}", **kw))
    return out


def _scratch_router(tmp_path: Path, monkeypatch, edit) -> str:
    """A scratch copy of the router package whose current rules file ``edit`` changes; first on the import path, so the
    router's own process imports it. Returns the module name to attach."""
    src = flash_router_src() / "epinoic_flash_router"
    dest = tmp_path / "src" / "epinoic_flash_router"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    rules_file = dest / "data" / json.loads((dest / "data" / "MANIFEST.json").read_text(encoding="utf-8"))["current"]["rules"]
    doc = json.loads(rules_file.read_text(encoding="utf-8"))
    edit(doc)
    rules_file.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    return "epinoic_flash_router.port"


# ----------------------------------------------------------------------------------------------- the recorded plans
def test_with_the_router_attached_every_recorded_plan_is_the_planners_plan(recorded, router):
    """Every recorded transfer (268 channels) and every recorded batch (genuine and all, per round): the router's plan,
    admitted by the overseer, IS the planner's plan as recorded before the move (every field, the plan id included), and
    it names the router, its version and its rules digest."""
    config = PoolConfig.model_validate(recorded["config"])
    pack = PackIdentity.model_validate(recorded["pack"])
    assert config == PoolConfig() and pack.version == "1.5", "the recorded plans were made with the default pool and pack 1.5"
    current = _manifest()["files"][_manifest()["current"]["rules"]]["sha256"]
    compared = 0
    for rnd, data in sorted(recorded["rounds"].items()):
        cases = [([c["item"]], {**c["plan"], "config": recorded["config"], "pack": recorded["pack"], "items": [c["item"]]}, c["sha256"], c["key"])
                 for c in data["channels"]]
        for batch in ("batch_genuine", "batch_all"):
            b = data[batch]
            cases.append((b["plan"]["items"], {**b["plan"], "config": recorded["config"], "pack": recorded["pack"]}, b["sha256"], f"{rnd}/{batch}"))
        for items, expected, digest, name in cases:
            assert _sha(expected) == digest, f"{name}: the recorded plan is rebuilt exactly"
            plan = plan_pool([PoolItem.model_validate(it) for it in items], config, pack, router=router)
            a = plan.admission
            assert (a.origin, a.refusal) == ("router", None), (name, a.detail)
            got = plan.model_dump(mode="json", exclude={"admission"})
            assert got == expected, name
            assert a.router.name == "epinoic-flash-router" and a.router.rules_sha256 == current and a.router == router.identity
            assert a.floor.name == POOL_FLOOR_NAME and a.floor.rules_sha256 == POOL_FLOOR_RULES_SHA256
            compared += 1
    assert compared == 268 + 2 * 5


def test_the_router_absent_runs_the_floor_plan_which_keeps_every_recorded_escalation(recorded):
    """No router attached: every plan is the minimum-oversight floor plan (origin floor, no refusal, no router), every
    escalated dossier still reaches two independent instances, and for every recorded channel the floor plan is the
    recorded plan except where the recorded plan rests on what is the router's to choose (the weight of risk records)."""
    config, pack = PoolConfig.model_validate(recorded["config"]), PackIdentity.model_validate(recorded["pack"])
    differ, records_only = [], []
    for rnd, data in sorted(recorded["rounds"].items()):
        for c in data["channels"]:
            item = PoolItem.model_validate(c["item"])
            if not item.escalated and item.risk_records:
                records_only.append(c["key"])
            plan = plan_pool([item], config, pack)
            assert (plan.admission.origin, plan.admission.refusal, plan.admission.router) == ("floor", None, None)
            assert len(plan.assignments[item.key]) == floor_reviewers(item) and below_floor(plan.assignments, [item]) is None
            expected = {**c["plan"], "config": recorded["config"], "pack": recorded["pack"], "items": [c["item"]]}
            if plan.model_dump(mode="json", exclude={"admission"}) != expected:
                differ.append(c["key"])
                assert not item.escalated and item.risk_records, c["key"]
        for batch in ("batch_genuine", "batch_all"):
            items = [PoolItem.model_validate(it) for it in data[batch]["plan"]["items"]]
            plan = plan_pool(items, config, pack)
            assert plan.admission.origin == "floor" and below_floor(plan.assignments, items) is None
            assert {k: len(v) for k, v in plan.assignments.items()} == {it.key: floor_reviewers(it) for it in items}
            assert len(plan.instances) == (2 if any(it.escalated for it in items) else 1)
    assert differ == records_only, differ  # exactly the recorded channels whose task carries risk records only


def test_the_floor_plan_holds_the_floor_and_never_grows_past_the_maximum():
    rng = random.Random(52)
    for _ in range(200):
        n = rng.randrange(0, 40)
        items = _items(n, repeated=rng.randrange(0, n + 1) if n else 0)
        items = [it.model_copy(update={"risk_signals": ("contradiction",)}) if rng.random() < 0.2 and not it.repeated_faults else it for it in items]
        cfg = PoolConfig(max_instances=rng.randrange(2, 9), per_instance_quota=rng.randrange(1, 12))
        p = plan_pool(items, cfg, PACK_ID)
        assert p.admission.origin == "floor" and below_floor(p.assignments, items) is None
        assert len(p.instances) <= cfg.max_instances and len(p.instances) == (0 if not items else 2 if any(it.escalated for it in items) else 1)
        assert sum(p.loads.values()) == p.review_units == sum(floor_reviewers(it) for it in items)
        assert p.over_quota == any(v > cfg.per_instance_quota for v in p.loads.values()) and not p.capped


# ----------------------------------------------------------------------------------------------- the version handshake
def _write_router(tmp_path: Path, monkeypatch, name: str, *, hello_changes: dict | None = None, plan_changes: dict | None = None,
                  pool_functions: bool = True) -> str:
    """A router module wrapping the released router's pool functions, with its pool hello or its plans changed."""
    require_flash_router()
    body = ["import json", "from epinoic_flash_router import port as _p",
            "def hello():\n    return _p.hello()", "def plan(request_json):\n    return _p.plan(request_json)"]
    if pool_functions:
        body.append("def pool_hello():\n    h = json.loads(_p.pool_hello())\n    h.update(" + repr(hello_changes or {}) + ")\n    return json.dumps(h)")
        body.append("def pool_plan(request_json):\n    p = json.loads(_p.pool_plan(request_json))\n    p.update(" + repr(plan_changes or {}) + ")\n    return json.dumps(p)")
    (tmp_path / f"{name}.py").write_text("\n".join(body) + "\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def test_the_released_router_says_its_version_capability_and_identity(router):
    h = router.hello
    m = _manifest()
    assert (h.port_version, h.capabilities, h.tier, h.deterministic) == (RP.POOL_PORT_VERSION, ["pool-plan"], "cheapest", True)
    assert h.router.name == "epinoic-flash-router" and h.router.rules_sha256 == m["files"][m["current"]["rules"]]["sha256"]
    assert h.router.cost_data_sha256 == m["files"][m["current"]["cost_data"]]["sha256"]
    import tomllib
    meta = tomllib.loads((flash_router_src().parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert h.router.version == meta["version"], "the identity's version is the router project's release"


@pytest.mark.parametrize("name,changes,detail", [
    ("pool_router_speaks_1_0", {"port_version": "1.0"}, "pool port version 1.0"),
    ("pool_router_speaks_2_0", {"port_version": "2.0"}, "pool port version 2.0"),
    ("pool_router_without_capability", {"capabilities": ["something-else"]}, "pool-plan capability"),
    ("pool_router_named_as_floor", {"router": {"name": "minimum-oversight-floor", "version": "1", "rules_sha256": "a1" * 32,
                                               "cost_data_sha256": "b2" * 32}}, "reserved identity"),
])
def test_a_router_failing_the_version_handshake_is_refused_and_the_floor_runs(tmp_path, monkeypatch, name, changes, detail):
    module = _write_router(tmp_path, monkeypatch, name, hello_changes=changes)
    att = attach(module)
    assert not att.attached and att.refusal == "KIT-RT-015" and detail in att.detail, att.detail
    plan = plan_pool(_items(4, risky=1), PoolConfig(), PACK_ID, router=att)
    assert (plan.admission.origin, plan.admission.refusal) == ("floor", "KIT-RT-015")
    assert plan.assignments["t000"] == ["overseer-pool-1", "overseer-pool-2"]


def test_a_router_without_the_pool_capability_is_not_attached_to_the_pool(tmp_path, monkeypatch):
    """A router module with the service's hello() and plan() only: attached by capability, so not for the pool."""
    module = _write_router(tmp_path, monkeypatch, "service_only_router", pool_functions=False)
    att = attach(module)
    assert att.refusal == "KIT-RT-015" and "pool's capability" in att.detail
    plan = plan_pool(_items(2), PoolConfig(), PACK_ID, router=module)  # the pool's own attach path: the module's name
    assert (plan.admission.origin, plan.admission.refusal) == ("floor", "KIT-RT-015")


def test_a_plan_naming_another_identity_than_its_hello_is_refused(tmp_path, monkeypatch):
    other = {"name": "epinoic-flash-router", "version": "9.9.9", "rules_sha256": "c3" * 32, "cost_data_sha256": "d4" * 32}
    att = attach(_write_router(tmp_path, monkeypatch, "pool_router_other_identity", plan_changes={"router": other}))
    assert att.attached, att.detail
    plan = plan_pool(_items(3, risky=1), PoolConfig(), PACK_ID, router=att)
    assert (plan.admission.origin, plan.admission.refusal) == ("floor", "KIT-RT-003")
    assert plan.admission.router == att.identity  # the attached router's identity is recorded with its refusal


def test_a_failing_router_is_refused_and_the_floor_runs(tmp_path, monkeypatch):
    att = attach(_write_router(tmp_path, monkeypatch, "pool_router_bad_answer", plan_changes={"instances": "many"}))
    plan = plan_pool(_items(3, repeated=1), PoolConfig(), PACK_ID, router=att)
    assert plan.admission.origin == "floor" and plan.admission.refusal in ("KIT-RT-008", "KIT-RT-001")
    broken = RP.attach_pool_router_in_process(lambda: attach_in_process().hello.model_dump_json(by_alias=True), lambda text: 1 / 0)
    assert broken.attached
    plan = plan_pool(_items(3, repeated=1), PoolConfig(), PACK_ID, router=broken)
    assert (plan.admission.origin, plan.admission.refusal) == ("floor", "KIT-RT-016") and "ZeroDivisionError" in plan.admission.detail


# ----------------------------------------------------------------------------------------------- data files: edited, weakened
def test_editing_a_rule_in_a_scratch_copy_of_the_data_file_changes_the_plan_and_nothing_else(tmp_path, monkeypatch, router):
    """batch_size 4 in a scratch copy of the router's rules file: ten plain dossiers are spread over three instances
    instead of two, the plan names the scratch rules digest, and the translator's and the overseer's code are untouched."""
    before = (_tree_digest(TRANSLATOR_SRC), _tree_digest(OVERSEER_SRC))
    items = _items(10)
    released = plan_pool(items, PoolConfig(), PACK_ID, router=router)
    assert released.admission.origin == "router" and len(released.instances) == 2

    def edit(doc):
        doc["pool"]["batch_size"] = 4
    att = attach(_scratch_router(tmp_path, monkeypatch, edit))
    assert att.attached and att.identity.rules_sha256 != router.identity.rules_sha256, att.detail
    edited = plan_pool(items, PoolConfig(), PACK_ID, router=att)
    assert (edited.admission.origin, edited.admission.refusal) == ("router", None), edited.admission.detail
    assert len(edited.instances) == 3 and edited.reasons[1] == "10 review units exceed the per-instance quota of 4: 3 instances needed"
    assert edited.admission.router.rules_sha256 == att.identity.rules_sha256 != released.admission.router.rules_sha256
    assert edited.plan_id != released.plan_id
    assert (_tree_digest(TRANSLATOR_SRC), _tree_digest(OVERSEER_SRC)) == before, "no translator or overseer code changed"


def test_a_deliberately_weakened_data_file_cannot_lower_oversight_below_the_floor(tmp_path, monkeypatch):
    """escalated_reviewers 1, batch_size 1000 and record_weight 1 in a scratch copy: for a batch with escalated dossiers
    the router plans one instance per dossier, the overseer refuses it (KIT-RT-020, recorded with the router's identity)
    and the floor plan runs; for a batch with no escalated dossier its cheaper plan is at the floor, and runs."""
    def weaken(doc):
        doc["pool"].update(escalated_reviewers=1, batch_size=1000, record_weight=1)
    att = attach(_scratch_router(tmp_path, monkeypatch, weaken))
    assert att.attached, att.detail
    risky = _items(12, repeated=2, risky=3)
    plan = plan_pool(risky, PoolConfig(), PACK_ID, router=att)
    a = plan.admission
    assert (a.origin, a.refusal) == ("floor", "KIT-RT-020") and "below the minimum-oversight floor" in a.detail
    assert a.router == att.identity and "KIT-RT-020" in admission_note(plan)
    for it in risky:
        assert len(plan.assignments[it.key]) == (MIN_REPEAT_REVIEWERS if it.escalated else 1)
    plain = plan_pool(_items(12), PoolConfig(), PACK_ID, router=att)
    assert (plain.admission.origin, len(plain.instances)) == ("router", 1)  # a cost choice above the floor: one instance
    assert plain.over_quota and below_floor(plain.assignments, _items(12)) is None


def test_the_refusal_is_recorded_in_the_signed_verdicts_audit_of_the_review_that_runs_the_floor_plan(tmp_path, monkeypatch):
    from .test_consolidation_repeats import bad_answer
    from .test_consolidation_consolidate import Dup
    from .test_hook_hub import audited_hub
    from .test_hook_review import Scripted, verdict
    from epinoic_overseer import load_pack
    from epinoic_overseer.export import export_pack

    def weaken(doc):
        doc["pool"]["escalated_reviewers"] = 1
    att = attach(_scratch_router(tmp_path / "router", monkeypatch, weaken))
    pack = load_pack(export_pack(tmp_path / "export", zip_archive=True).zip_path)
    hub = audited_hub()
    try:
        faulty = Dup(hub, task_id="task-faulty")
        text, claims = bad_answer()
        faulty.answer("english-1", text=text, claims=claims, name="first")
        faulty.answer("english-2", text=text, claims=claims, name="again")
        pool = OverseerPool(pack, lambda agent_id: Scripted(lambda d: verdict(d)), router=att)
        pr = hub.review_pool(["task-faulty"], pool)
        uid = faulty.ch.channel_uid
        assert pr.plan.admission.refusal == "KIT-RT-020" and len(pr.plan.assignments[uid]) == 2
        review = pr.reviews[uid]
        assert verify_audit(review.audit, hub.auditor.keyring)
        notes = " ".join(review.audit.coverage.notes)
        assert "KIT-RT-020" in notes and att.identity.rules_sha256 in notes and POOL_FLOOR_NAME in notes
    finally:
        hub.close()


def test_the_signed_verdicts_audit_names_the_router_that_planned_the_review(tmp_path, router):
    from .test_consolidation_consolidate import Dup
    from .test_hook_hub import audited_hub
    from .test_hook_review import Scripted, verdict
    from epinoic_overseer import load_pack
    from epinoic_overseer.export import export_pack
    pack = load_pack(export_pack(tmp_path / "export", zip_archive=True).zip_path)
    hub = audited_hub()
    try:
        d = Dup(hub)
        d.answer("english-1", name="a")
        pool = OverseerPool(pack, lambda agent_id: Scripted(lambda dd: verdict(dd)), router=router)
        assert "epinoic-flash-router" in repr(pool)
        pr = hub.review_pool([d.key], pool)
        assert pr.plan.admission.origin == "router"
        notes = " ".join(pr.reviews[d.ch.channel_uid].audit.coverage.notes)
        assert f"planned by the flash router epinoic-flash-router {router.identity.version} (rules sha256 {router.identity.rules_sha256}" in notes
    finally:
        hub.close()


# ----------------------------------------------------------------------------------------------- determinism
def test_the_same_batch_gives_the_same_plan_in_any_order_and_from_any_router_process(router):
    items = _items(40, repeated=5, risky=7, records=6)
    p = plan_pool(items, PoolConfig(), PACK_ID, router=router)
    again = attach()  # another attachment: another process per plan
    for seed in range(4):
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        q = plan_pool(shuffled, PoolConfig(), PACK_ID, router=again if seed % 2 else router)
        assert q == p and q.plan_id == p.plan_id and q.admission == p.admission
    inproc = plan_pool(items, PoolConfig(), PACK_ID, router=attach_in_process())
    assert inproc.model_dump(exclude={"admission"}) == p.model_dump(exclude={"admission"})


# ----------------------------------------------------------------------------------------------- the escalation advisor
def test_the_escalation_advisor_only_escalates_and_is_off_by_default(router):
    items = _items(6, risky=1)
    plain = plan_pool(items, PoolConfig(), PACK_ID, router=router)
    assert plain.admission.advised == () and len(plain.assignments["t003"]) == 1
    for r in (router, None):
        up = plan_pool(items, PoolConfig(), PACK_ID, router=r, advisor=lambda its: ["t003", "not-in-this-batch", 7])
        assert up.admission.advised == ("t003",) and len(up.assignments["t003"]) == 2 and len(up.assignments["t000"]) == 2
        assert "ignored" in up.admission.detail and any("escalation advisor" in x for x in up.reasons)
        silent = plan_pool(items, PoolConfig(), PACK_ID, router=r, advisor=lambda its: [])  # it cannot lower: the risky one keeps two
        assert len(silent.assignments["t000"]) == 2 and silent.admission.advised == ()
        broken = plan_pool(items, PoolConfig(), PACK_ID, router=r, advisor=lambda its: 1 / 0)
        assert "failed (ZeroDivisionError)" in broken.admission.detail and len(broken.assignments["t000"]) == 2
    from epinoic_overseer import load_pack
    with pytest.raises(TypeError, match="advisor"):
        OverseerPool(load_pack(), lambda agent_id: None, advisor="lenient")  # type: ignore[arg-type]


def test_a_router_that_ignores_the_advisors_escalation_is_refused(tmp_path, monkeypatch):
    """A router that plans the advised dossier IN_DEPTH (ignoring the escalation) is below the floor the advisor raised."""
    module = _scratch_router(tmp_path, monkeypatch, lambda doc: None)
    # the scratch router's pool planner, edited to ignore "advised" (a router edited badly, not only its data)
    pool_py = tmp_path / "src" / "epinoic_flash_router" / "pool.py"
    pool_py.write_text(pool_py.read_text(encoding="utf-8").replace('or item.get("advised")', "or False")
                       .replace('it.get("advised") and', "False and"), encoding="utf-8")
    att = attach(module)
    plan = plan_pool(_items(3), PoolConfig(), PACK_ID, router=att, advisor=lambda its: ["t001"])
    assert (plan.admission.origin, plan.admission.refusal) == ("floor", "KIT-RT-020") and len(plan.assignments["t001"]) == 2


# ----------------------------------------------------------------------------------------------- independence
def test_neither_the_overseer_nor_the_translator_imports_the_router():
    for root in (OVERSEER_SRC, TRANSLATOR_SRC):
        for p in root.rglob("*.py"):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                assert not any(n.split(".")[0].startswith("epinoic_flash_router") for n in names), p


def test_a_plan_record_round_trips_with_its_admission(router):
    p = plan_pool(_items(9, repeated=1, records=2), PoolConfig(per_instance_quota=3), PACK_ID, router=router)
    assert PoolPlan.model_validate(p.model_dump(mode="json")) == p
    data = p.model_dump(mode="json")
    data["admission"] = {**data["admission"], "refusal": "not a code"}
    with pytest.raises(ValueError):
        PoolPlan.model_validate(data)
