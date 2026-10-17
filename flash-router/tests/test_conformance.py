"""The flash router's own conformance suite (``integration/router-port/CONFORMANCE.md`` of the translator repository,
items 1 to 6), over the router-port vectors' requests (``tests/vectors/router-port/``, copied from the kit by its
vector generator) and over generated requests, validated with the service's own router port.

1. the hello is in contract and the identity is stable, and changes when the rules or the cost model change;
2. every plan round-trips through ``check_plan`` exactly;
3. every plan is ADOPTED by the service's admission: origin ``router``, no refusal, never below the floor;
4. a plan carries only the request's own data (closed vocabularies, its transfer keys and digests, the identity);
5. it is bounded (instances per transfer, ``instances = reviews x parts``, totals that add up, integer costs);
6. it is deterministic (the same request text gives the same plan text, in a fresh interpreter too);
and the router is independent of the Z3 infrastructure: it runs with nothing but its own ``src/`` on the path.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from epinoic_logic.integration import router_port as R

from epinoic_flash_router import __version__, port, rules

canonical_json = R.canonical_json  # the service's canonical form, as the router port uses it

PROJECT = Path(__file__).resolve().parents[1]
VECTORS = sorted((PROJECT / "tests" / "vectors" / "router-port").glob("*.json"))
HELLO = R.check_hello(json.loads(port.hello()))


def _requests() -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text(encoding="utf-8"))["request"]) for p in VECTORS]


def _plan(raw_request: dict) -> tuple[R.RoutingRequest, str]:
    req = R.check_request(raw_request)
    return req, port.plan(canonical_json(R.dump(req)))


def test_the_vectors_are_present():
    assert len(VECTORS) >= 10, "run the translator's integration/tools/vectors.py: it copies the router-port vectors here"


# ----------------------------------------------------------------------------------------------- 1. hello


def test_1_the_hello_is_in_contract_and_names_this_release():
    h = HELLO
    assert h.router.name == "epinoic-flash-router" and h.router.version == __version__
    assert h.router.rules_sha256 == rules.rules_sha256() and h.router.cost_data_sha256 == rules.cost_data_sha256()
    assert set(h.methods) == set(R.METHODS) and h.tier == "cheapest" and h.deterministic is True
    assert port.hello() == port.hello(), "the identity is stable for a release"
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__, "the release's version is the package's"


def test_1_the_identity_changes_when_the_rules_or_the_cost_model_change():
    assert rules.rules_sha256(rules.RULES + "8. an extra rule\n") != rules.RULES_SHA256
    assert rules.rules_sha256(parameters={**rules.PARAMETERS, "split_words": 901}) != rules.RULES_SHA256
    assert rules.cost_data_sha256({**rules.COST_MODEL, "seconds_per_instance": 31}) != rules.COST_DATA_SHA256


# ----------------------------------------------------------------------------------------------- 2 to 5 on the vectors


@pytest.mark.parametrize("name,raw", _requests(), ids=[n for n, _ in _requests()])
def test_2_to_5_every_vector_request_is_planned_in_contract_and_adopted(name, raw):
    req, text = _plan(raw)
    plan = R.check_plan(text, req, hello=HELLO)                              # 2: in contract
    assert R.dump(plan) == json.loads(text), "no field dropped, none added"   # 2: an exact round trip
    adm = R.admit_plan(req, json.loads(text), hello=HELLO)
    assert (adm.origin, adm.refusal) == ("router", None), adm.detail          # 3: adopted
    assert R.below_floor(plan, R.floor_plan(req)) is None                     # 3: at or above the floor
    _only_its_own_data(req, plan)                                             # 4
    _bounded(req, plan)                                                       # 5


def _only_its_own_data(req: R.RoutingRequest, plan: R.RoutingPlan) -> None:
    assert [t.transfer_key for t in plan.transfers] == [o.transfer_key for o in req.outputs]
    assert plan.ids == req.ids and plan.request_sha256 == R.request_digest(req) and plan.router == HELLO.router
    for t in plan.transfers:
        assert set(t.reasons) <= set(R.REASON_CODES) and set(t.features_used) <= set(R.FEATURE_NAMES)
        assert t.tier == "cheapest"
    text = json.dumps(R.dump(plan))
    assert "OVS-" not in text and '"model' not in text


def _bounded(req: R.RoutingRequest, plan: R.RoutingPlan) -> None:
    cap = min(req.limits.max_instances, R.HARD_MAX_INSTANCES)
    for t in plan.transfers:
        assert t.instances <= cap and t.instances == t.reviews * t.parts
        assert isinstance(t.estimated_cost.tokens, int) and isinstance(t.estimated_cost.seconds, int)
    assert plan.totals.instances == sum(t.instances for t in plan.transfers)
    assert plan.totals.estimated_cost.tokens == sum(t.estimated_cost.tokens for t in plan.transfers)


# ----------------------------------------------------------------------------------------------- 3 on generated requests


def _output(key: str, *, role: str = "answer", agent_id: str = "history", subject: str = "History", sig: dict) -> dict:
    stem = sig["stem"]
    return {"transfer_key": key, "role": role, "agent_id": agent_id, "subject": subject, "branch": "sciences" if stem else "history", "stem": stem,
            "size": {"chars": sig["words"] * 6, "words": sig["words"], "paragraphs": 3},
            "claims": {"total": 6, "material": 4, "eligible": 3, "translated": 2}, "engine_statuses": sig["statuses"],
            "receipt": {"status": sig["status"], "error_codes": list(sig["errors"]), "warning_codes": list(sig["warnings"])},
            "diagnostics": list(sig["diagnostics"]), "unverified_dependencies": sig["unverified"], "peer_relays": 0,
            "repeated_faults": sig["repeated"]}


_SIG = st.fixed_dictionaries({
    "stem": st.booleans(), "words": st.integers(0, 20000),
    "status": st.sampled_from(["ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED"]),
    "errors": st.sampled_from([(), ("INT-SUBJ-001",), ("INT-LEDGER-004", "INT-REQ-003")]),
    "warnings": st.sampled_from([(), ("INT-SUBJ-002",), ("INT-REQ-010",)]),
    "statuses": st.dictionaries(st.sampled_from(["ENTAILED", "COUNTEREXAMPLE", "UNSATISFIABLE", "UNKNOWN", "TIMEOUT", "NOT_ATTEMPTED",
                                                 "NOT_ELIGIBLE", "INTERNAL_ERROR"]), st.integers(0, 3), max_size=4),
    "diagnostics": st.sampled_from([(), ("ARG-CIRCULAR-001",)]), "unverified": st.integers(0, 3), "repeated": st.integers(0, 2),
})


def _request(sigs: list[dict], kind: str, max_instances: int, profiles: list[str]) -> dict:
    if kind == "combined":
        outs = [_output(f"m-{i}", agent_id=a, subject="History", sig=s) for i, (s, a) in enumerate(zip(sigs[:-1], ["history", "english-a-literature", "physics"]))]
        outs.append(_output("m-s", role="synthesis", agent_id="synthesis", sig=sigs[-1]))
        topology = {"kind": "combined", "sources": [o["transfer_key"] for o in outs[:-1]], "synthesis": "m-s"}
    elif kind == "duplicate":
        outs = [_output("m-a", sig=sigs[0]), _output("m-b", sig=sigs[1])]
        topology = {"kind": "duplicate", "sources": [], "synthesis": None}
    else:
        outs = [_output("m-1", sig=sigs[0])]
        topology = {"kind": "single", "sources": [], "synthesis": None}
    return {"schema": "epinoic.integration.routing-request.v1", "protocol": "epinoic.integration.v1", "port_version": "1.0",
            "ids": {"task_id": "t_" + "0" * 31 + "1", "request_id": "a_" + "0" * 31 + "1"},
            "request": {"subjects": ["History"], "stem": any(o["stem"] for o in outs), "task_type": "short_answer", "course_level": "unknown",
                        "items": [], "constraints": [], "supplied_texts": [], "user_text_sha256": "d4" * 32},
            "outputs": outs, "topology": topology, "limits": {"max_instances": max_instances, "profiles": profiles}}


@settings(max_examples=250, deadline=None)
@given(st.lists(_SIG, min_size=3, max_size=4), st.sampled_from(["single", "duplicate", "combined"]), st.integers(2, 64),
       st.sampled_from([["standard"], ["standard", "fast"], ["fast"]]))
def test_3_every_generated_request_is_planned_at_or_above_the_floor(sigs, kind, max_instances, profiles):
    req, text = _plan(_request(sigs, kind, max_instances, profiles))
    adm = R.admit_plan(req, json.loads(text), hello=HELLO)
    assert (adm.origin, adm.refusal) == ("router", None), adm.detail
    _only_its_own_data(req, adm.effective)
    _bounded(req, adm.effective)


_QUIET = {"stem": False, "words": 300, "status": "ACCEPTED", "errors": (), "warnings": (), "statuses": {"ENTAILED": 2},
          "diagnostics": (), "unverified": 0, "repeated": 0}


def _single_entry(sig: dict, max_instances: int = 8) -> R.TransferPlan:
    req, text = _plan(_request([sig], "single", max_instances, ["standard"]))
    return R.check_plan(text, req, hello=HELLO).transfers[0]


def test_the_router_adds_oversight_the_floor_does_not_ask_for():
    quiet = _single_entry(_QUIET)
    assert (quiet.method, quiet.reviews, quiet.reasons[0]) == ("IN_DEPTH", 1, "baseline_single_review")
    escalated = _single_entry({**_QUIET, "unverified": 1})  # the floor reads no unverified dependency: 1 review there
    assert (escalated.method, escalated.reviews) == ("DUPLICATE", 2) and "risk_unverified_dependencies" in escalated.reasons
    both = _single_entry({**_QUIET, "unverified": 1, "errors": ("INT-SUBJ-001",)})
    assert (both.method, both.reviews) == ("DUPLICATE", 3) and {"risk_error_findings", "risk_unverified_dependencies"} <= set(both.reasons)
    assert _single_entry({**_QUIET, "diagnostics": ("ARG-CIRCULAR-001",)}).reviews == 2
    long = _single_entry({**_QUIET, "words": 4000})
    assert (long.method, long.parts, long.reviews, long.instances) == ("SPLIT", 5, 1, 5) and "volume_split" in long.reasons
    assert _single_entry({**_QUIET, "words": 40000}, max_instances=3).parts == 3  # never more parts than instances allowed
    assert _single_entry({**_QUIET, "unverified": 1, "errors": ("INT-SUBJ-001",)}, max_instances=2).reviews == 2  # capped, never below the floor


# ----------------------------------------------------------------------------------------------- 6. determinism


def test_6_the_same_request_text_gives_the_same_plan_text_in_a_fresh_interpreter_too():
    raw = _requests()[0][1]
    text = canonical_json(R.dump(R.check_request(raw)))
    assert port.plan(text) == port.plan(text) == port.plan(copy.deepcopy(text))
    code = "import sys; from epinoic_flash_router import port; sys.stdout.write(port.plan(sys.stdin.read()))"
    outs = set()
    for seed in ("1", "2"):
        env = {"PYTHONHASHSEED": seed, "PYTHONPATH": str(PROJECT / "src"), "PATH": os.environ.get("PATH", "")}
        proc = subprocess.run([sys.executable, "-c", code], input=text, capture_output=True, text=True, env=env, timeout=60, cwd=PROJECT)
        assert proc.returncode == 0, proc.stderr
        outs.add(proc.stdout)
    assert outs == {port.plan(text)}


# ----------------------------------------------------------------------------------------------- independence


def test_the_router_runs_with_nothing_but_its_own_package_on_the_path():
    """No translator, no engine, no Z3: the router's process holds the standard library and this package only."""
    code = ("import sys; sys.path[:] = [p for p in sys.path if 'site-packages' not in p and 'dist-packages' not in p]\n"
            f"sys.path.insert(0, {str(PROJECT / 'src')!r})\n"
            "from epinoic_flash_router import port\n"
            "port.plan(sys.stdin.read()); port.hello()\n"
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('epinoic_logic', 'z3', 'pydantic'))\n"
            "print(','.join(bad))")
    text = canonical_json(R.dump(R.check_request(_requests()[0][1])))
    proc = subprocess.run([sys.executable, "-I", "-c", code], input=text, capture_output=True, text=True, timeout=60, cwd=PROJECT)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


def test_the_package_imports_nothing_but_json_hashlib_typing_and_itself():
    """Pure: no network, no clock, no randomness, no process, no file, and nothing of the translator or Z3."""
    allowed = {"__future__", "json", "hashlib", "typing", "epinoic_flash_router"}
    for p in sorted((PROJECT / "src" / "epinoic_flash_router").glob("*.py")):
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*|\.)", line)
            if m and m.group(1) != ".":
                assert m.group(1) in allowed, (p.name, line)
