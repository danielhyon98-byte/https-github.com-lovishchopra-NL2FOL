"""The flash router is a separate, independent agent (PROTOCOL.md section 7a, "Attachment"; router-port/CONFORMANCE.md,
"What the service guarantees whatever the router does"): it runs in its own process, so whatever its CODE does (not only
what it returns) the service is unaffected. Its process holds no EPINOIC_ variable; it cannot lower the floor by patching
the kit; a router that raises (SystemExit and KeyboardInterrupt included), exits, kills itself, hangs, prints, answers
too much or answers with anything but JSON text is refused with KIT-RT-016 and the floor runs; a plan id or a router
name that names a model family is refused (KIT-RT-009, hello KIT-RT-015)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from epinoic_logic.integration import router_port as R
from epinoic_logic.integration.errors import IntegrationError
from tests.integration.helpers import output_features, plan_for, router_hello, routing_request, write_router_module

HELLO = R.check_hello(router_hello())
RISKY = routing_request([output_features("m-1", errors=("INT-SUBJ-001",))])

# A plan of one IN_DEPTH review for every transfer: below the floor for a risky transfer.
CHEAP = ("    req = json.loads(request_json)\n"
         "    ts = [{'transfer_key': o['transfer_key'], 'method': 'IN_DEPTH', 'reviews': 1, 'parts': 1, 'instances': 1, 'profile': 'standard',\n"
         "           'tier': 'cheapest', 'sources': [], 'context': None, 'reasons': ['cost_cheapest'], 'features_used': ['size'],\n"
         "           'estimated_cost': {'tokens': 1, 'seconds': 1}} for o in req['outputs']]\n"
         "    digest = hashlib.sha256(json.dumps(req, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()\n"
         "    return json.dumps({'schema': 'epinoic.integration.routing-plan.v1', 'protocol': 'epinoic.integration.v1', 'port_version': '1.0',\n"
         "                       'origin': 'router', 'plan_id': _plan_id(digest), 'ids': req['ids'], 'request_sha256': digest, 'router': IDENTITY,\n"
         "                       'transfers': ts, 'totals': {'instances': len(ts), 'estimated_cost': {'tokens': len(ts), 'seconds': len(ts)}}})\n")


def _attach(tmp_path, monkeypatch, name, **kw) -> R.RouterAttachment:
    att = R.attach_router(write_router_module(tmp_path, monkeypatch, name, **kw))
    assert att.attached, att
    return att


def _alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")  # a zombie waiting for its reaper is not running


# ----------------------------------------------------------------------------------------------- the router's own process


def test_the_router_runs_in_its_own_process_and_sees_no_epinoic_variable(tmp_path, monkeypatch):
    for name in ("EPINOIC_SIGNING_KEY", "EPINOIC_VERDICT_KEY", "EPINOIC_OVERSEER_SECRET", "EPINOIC_SERVICE_TOKEN"):
        monkeypatch.setenv(name, "SYNTHETIC-not-a-secret-" + name)
    epilogue = ("def _plan_id(digest):\n"
                "    seen = sum(1 for k in os.environ if k.startswith('EPINOIC_'))\n"
                "    return f'plan-env-{seen}-pid-{os.getpid()}'\n")
    att = _attach(tmp_path, monkeypatch, "env_router_for_isolation", epilogue=epilogue)
    adm = R.route(R.check_request(routing_request()), att)
    assert (adm.origin, adm.refusal) == ("router", None), adm.detail
    _, env, seen, _, pid = adm.effective.plan_id.split("-")
    assert (env, seen) == ("env", "0"), "no EPINOIC_ variable reaches the router's process"
    assert int(pid) != os.getpid(), "the router never runs in the service's process"
    assert set(R._child_env()) <= set(R.CHILD_ENV_NAMES) and not any(n.startswith("EPINOIC_") for n in R.CHILD_ENV_NAMES)


def test_a_router_cannot_lower_the_floor_by_patching_the_kit(tmp_path, monkeypatch):
    epilogue = ("from epinoic_logic.integration import router_port as _kit\n"
                "_kit.below_floor = lambda plan, floor: None\n"
                "_kit.floor_plan = None\n")
    original = (R.below_floor, R.floor_plan)
    att = _attach(tmp_path, monkeypatch, "patching_router_for_isolation", plan_body=CHEAP, epilogue=epilogue)
    adm = R.route(R.check_request(RISKY), att)
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-020"), "the patch ran in the router's process only"
    assert adm.effective.transfers[0].reviews == 2
    assert (R.below_floor, R.floor_plan) == original


@pytest.mark.parametrize("body", [
    "    raise SystemExit(3)\n",
    "    raise KeyboardInterrupt()\n",
    "    os._exit(9)\n",
    "    import signal\n    os.kill(os.getpid(), signal.SIGKILL)\n",
    "    sys.exit(0)\n",
])
def test_a_router_that_exits_or_is_interrupted_never_reaches_the_service(tmp_path, monkeypatch, body):
    att = _attach(tmp_path, monkeypatch, f"exiting_router_{abs(hash(body)) % 10**8}", plan_body=body)
    req = R.check_request(RISKY)
    adm = R.route(req, att)
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-016") and adm.effective == R.floor_plan(req)


def test_a_slow_router_is_cut_at_its_time_limit_and_its_children_go_with_it(tmp_path, monkeypatch):
    marker = tmp_path / "pids.txt"
    body = ("    import subprocess\n"
            f"    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"    open({str(marker)!r}, 'w').write(f'{{os.getpid()}} {{child.pid}}')\n"
            "    time.sleep(60)\n")
    att = _attach(tmp_path, monkeypatch, "slow_router_for_isolation", plan_body=body)
    started = time.monotonic()
    adm = R.route(R.check_request(RISKY), att, timeout_s=1.0)
    took = time.monotonic() - started
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-016") and "did not answer within 1000 ms" in adm.detail
    assert took < 8.0, f"the wait is bounded by the time limit ({took:.1f} s)"
    if Path("/proc").is_dir() and marker.exists():
        pids = [int(x) for x in marker.read_text().split()]
        deadline = time.monotonic() + 5
        while any(_alive(p) for p in pids) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not any(_alive(p) for p in pids), "the router and the processes it started are killed"


def test_no_time_left_means_the_router_is_not_asked(tmp_path, monkeypatch):
    marker = tmp_path / "asked.txt"
    body = f"    open({str(marker)!r}, 'w').write('asked')\n    return 'never used'\n"
    att = _attach(tmp_path, monkeypatch, "unasked_router_for_isolation", plan_body=body)
    for left in (0, 0.0, -1.0):
        adm = R.route(R.check_request(RISKY), att, timeout_s=left)
        assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-016") and "no time was left" in adm.detail
    assert not marker.exists()


def test_what_a_router_prints_never_enters_its_answer(tmp_path, monkeypatch):
    epilogue = "print('noise at import')\nsys.stdout.write('more noise')\nos.write(1, b'raw noise')\n"
    plan_body = "    print('noise while planning')\n    os.write(1, b'{\"not\": \"the answer\"}')\n" + CHEAP
    att = _attach(tmp_path, monkeypatch, "noisy_router_for_isolation", plan_body=plan_body, epilogue=epilogue)
    adm = R.route(R.check_request(routing_request()), att)
    assert (adm.origin, adm.refusal) == ("router", None), adm.detail


def test_an_answer_larger_than_the_service_reads_is_a_failed_router(tmp_path, monkeypatch):
    body = f"    return 'x' * {R.MAX_ANSWER_BYTES + 1}\n"
    att = _attach(tmp_path, monkeypatch, "large_router_for_isolation", plan_body=body)
    adm = R.route(R.check_request(routing_request()), att)
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-016") and "larger than" in adm.detail


@pytest.mark.parametrize("hello_body,epilogue,code", [
    ("    return 'not json'\n", "", "KIT-RT-016"),
    ("    return HELLO\n", "", "KIT-RT-016"),  # a dict, not JSON text
    ("    raise RuntimeError('hello bug')\n", "", "KIT-RT-016"),
    ("    raise SystemExit(1)\n", "", "KIT-RT-016"),
    ("    time.sleep(60)\n", "", "KIT-RT-016"),
    ("    return json.dumps(dict(HELLO, tier='premium'))\n", "", "KIT-RT-015"),
    ("    return json.dumps(HELLO)\n", "del plan\n", "KIT-RT-015"),
    ("    return json.dumps(HELLO)\n", "raise SystemExit('broken at import')\n", "KIT-RT-016"),
])
def test_a_router_whose_hello_fails_is_detached_with_its_code(tmp_path, monkeypatch, hello_body, epilogue, code):
    name = write_router_module(tmp_path, monkeypatch, f"hello_router_{abs(hash((hello_body, epilogue))) % 10**8}", hello_body=hello_body,
                               epilogue=epilogue)
    att = R.attach_router(name, timeout_s=2.0)
    assert not att.attached and att.refusal == code, att
    assert R.route(R.check_request(routing_request()), att).origin == "floor"


def test_an_in_process_plan_function_is_also_contained():
    """route() never lets a plan function's exception through (SystemExit included); only an operator's interrupt."""
    def exits(text, timeout_s):
        raise SystemExit(1)

    def interrupted(text, timeout_s):
        raise KeyboardInterrupt

    req = R.check_request(routing_request())
    adm = R.route(req, R.RouterAttachment(HELLO, exits, None, ""))
    assert (adm.origin, adm.refusal) == ("floor", "KIT-RT-016")
    assert R.route(req, R.RouterAttachment(HELLO, lambda text, t: 42, None, "")).refusal == "KIT-RT-016"
    assert R.route(req, R.RouterAttachment(HELLO, lambda text, t: json.dumps({}), None, "")).refusal == "KIT-RT-001"
    with pytest.raises(KeyboardInterrupt):
        R.route(req, R.RouterAttachment(HELLO, interrupted, None, ""))


# ----------------------------------------------------------------------------------------------- no model named (L2)


@pytest.mark.parametrize("plan_id", ["claude-x-model-1", "plan-gpt-4o", "plan.Gemini.2", "llama3-plan", "plan:opus", "mistral", "plan-qwen2"])
def test_a_plan_id_that_names_a_model_family_is_refused(plan_id):
    raw_req = routing_request()
    plan = plan_for(raw_req, [{"transfer_key": "m-1"}])
    plan["plan_id"] = plan_id
    with pytest.raises(IntegrationError) as exc:
        R.check_plan(plan, R.check_request(raw_req), hello=HELLO)
    assert exc.value.code == "KIT-RT-009"


@pytest.mark.parametrize("plan_id", ["plan-router-test", "plan-cheap", "plan-0123abcd", "floorplan-gptx", "plan-opusculum"])
def test_ordinary_plan_ids_are_admitted(plan_id):
    raw_req = routing_request()
    plan = plan_for(raw_req, [{"transfer_key": "m-1"}])
    plan["plan_id"] = plan_id
    assert R.check_plan(plan, R.check_request(raw_req), hello=HELLO).plan_id == plan_id


@pytest.mark.parametrize("name", ["claude-model", "gpt-router", "router-sonnet", "haiku"])
def test_a_router_name_that_names_a_model_family_is_refused(name):
    ident = {"name": name, "version": "1", "rules_sha256": "a1" * 32, "cost_data_sha256": "b2" * 32}
    with pytest.raises(IntegrationError) as exc:
        R.check_hello(router_hello(router=ident))
    assert exc.value.code == "KIT-RT-015"
    raw_req = routing_request()
    with pytest.raises(IntegrationError) as exc:
        R.check_plan(plan_for(raw_req, [{"transfer_key": "m-1"}], identity=ident), R.check_request(raw_req), hello=HELLO)
    assert exc.value.code == "KIT-RT-009"
