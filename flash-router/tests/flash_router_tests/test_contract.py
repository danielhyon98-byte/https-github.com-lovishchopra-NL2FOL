"""What the flash router reads of a request (``contract.py``), checked before it plans one, so that a request it cannot
read and a fault of its own code are told apart (round 9's push check of c4f276c: the runner mapped every exception to
exit 2 or 3, so a planner bug looked like bad input):

- each kind of request it does not read is refused with :class:`RequestError` (a ``ValueError``) and its exact reason,
  the member and the rule and never a value of the request, before anything is planned;
- any request, however it is mutated from one in contract, is planned or refused with a RequestError: the planners never
  raise on a request that passes the checks, and the runner answers it 0 or 3, never 4 (a fault of its own code);
- the checks are no stricter than the router port: every request the port accepts is planned, at pool port 1.2 too
  (with combined answers), and the service's (``test_conformance.py``) and the pool's at 1.1 (``test_pool.py``) as before.
"""
from __future__ import annotations

import copy
import io
import json
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from epinoic_logic.integration import router_pool as RP

from epinoic_flash_router import contract, planner, pool, port, rules
from epinoic_flash_router_cli.__main__ import main as runner_main

PROJECT = Path(__file__).resolve().parents[2]
VECTORS = sorted((PROJECT / "tests" / "vectors" / "router-port").glob("*.json"))
_MAX = contract.MAX_SAFE_INTEGER

#: The service's requests in contract: every router-port vector, and a combined answer with a supplied text.
SERVICE = [json.loads(p.read_text(encoding="utf-8"))["request"] for p in VECTORS]
_COMBINED = copy.deepcopy(next(r for r in SERVICE if r["topology"]["kind"] == "combined"))
_COMBINED["request"]["supplied_texts"] = [{"document_id": "doc-1", "sha256": "ab" * 32, "chars": 1200}]
SERVICE.append(_COMBINED)
_SINGLE = next(r for r in SERVICE if r["topology"]["kind"] == "single")


def _features(chars: int = 9000, stem: bool = False, translations: int = 1) -> dict:
    return {"transfers": 2, "chars": chars, "stem": stem, "translations": translations}


def _part(repeated: int = 0, signals: tuple = (), features: bool = True) -> dict:
    return {"repeated_faults": repeated, "risk_signals": list(signals), "risk_records": [], "features": _features() if features else None}


#: The overseer pool's requests in contract: a batch at pool port 1.1, and one at 1.2 with a combined answer.
POOL_11 = {"schema": "epinoic.integration.pool-routing-request.v1", "protocol": "epinoic.integration.v1", "port_version": "1.1",
           "items": [{"item_id": f"d{i + 1}", "repeated_faults": 1 if i == 0 else 0, "risk_signals": ["contradiction"] if i == 1 else [],
                      "risk_records": ["stem_method"] if i == 2 else [], "advised": i == 3} for i in range(5)],
           "limits": {"max_instances": 4, "per_instance_quota": 3, "profiles": ["standard"]}}
POOL_12 = {**copy.deepcopy(POOL_11), "port_version": "1.2"}
for _it in POOL_12["items"]:
    _it.update(features=_features(40000, stem=True, translations=0), sources=[], merged=None)
POOL_12["items"].append({"item_id": "d6", "repeated_faults": 0, "risk_signals": [], "risk_records": [], "advised": False,
                         "features": _features(90000, translations=2),
                         "sources": [_part(), _part(1, ("rejection",)), _part(features=False)], "merged": _part()})
BASES = [("plan", r) for r in SERVICE] + [("pool-plan", POOL_11), ("pool-plan", POOL_12)]


def _call(op: str, text):
    return (port.plan if op == "plan" else port.pool_plan)(text)


def test_the_requests_in_contract_are_planned():
    for op, request in BASES:
        assert json.loads(_call(op, json.dumps(request)))["origin"] == "router"


# ----------------------------------------------------------------------------------------------- each refusal, with its reason
def _edit(request: dict, path: tuple, value=None, *, delete: bool = False) -> dict:
    doc = copy.deepcopy(request)
    node = doc
    for k in path[:-1]:
        node = node[k]
    if delete:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return doc


_COMBINED_NO_SOURCES = _edit(_COMBINED, ("topology", "sources"), delete=True)
_OUTPUT = ("outputs", 0)
_ITEM = ("items", 0)
REFUSALS = [
    ("plan", [], "the routing request is a JSON object"),
    ("plan", _edit(_SINGLE, ("limits",), delete=True), "limits is a JSON object"),
    ("plan", _edit(_SINGLE, ("limits", "max_instances"), 0), f"limits.max_instances is an integer from 1 to {_MAX}"),
    ("plan", _edit(_SINGLE, ("limits", "profiles"), []), "limits.profiles is a list of at least one of standard, fast"),
    ("plan", _edit(_SINGLE, ("limits", "profiles"), ["turbo"]), "limits.profiles is a list of at least one of standard, fast"),
    ("plan", _edit(_SINGLE, ("ids", "task_id"), 7), "ids.task_id is a string"),
    ("plan", _edit(_SINGLE, ("outputs",), []), "outputs is a list of at least one output"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "transfer_key"), None), "outputs[0].transfer_key is a string"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "stem"), "yes"), "outputs[0].stem is true or false"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "size", "chars"), -1), f"outputs[0].size.chars is an integer from 0 to {_MAX}"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "size", "chars"), 1.5), f"outputs[0].size.chars is an integer from 0 to {_MAX}"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "size", "chars"), _MAX + 1), f"outputs[0].size.chars is an integer from 0 to {_MAX}"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "size", "words"), True), f"outputs[0].size.words is an integer from 0 to {_MAX}"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "claims"), delete=True), "outputs[0].claims is a JSON object"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "engine_statuses"), {"ENTAILED": "2"}),
     f"outputs[0].engine_statuses counts each status with an integer from 0 to {_MAX}"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "receipt", "status"), "PENDING"),
     "outputs[0].receipt.status is one of ACCEPTED, ACCEPTED_WITH_FINDINGS, REJECTED"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "receipt", "warning_codes"), [7]), "outputs[0].receipt.warning_codes is a list of strings"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "diagnostics"), "ARG-CIRCULAR-001"), "outputs[0].diagnostics is a list of strings"),
    ("plan", _edit(_SINGLE, (*_OUTPUT, "repeated_faults"), -1), f"outputs[0].repeated_faults is an integer from 0 to {_MAX}"),
    ("plan", _edit(_COMBINED, ("request", "supplied_texts", 0, "chars"), "1200"), f"request.supplied_texts[0].chars is an integer from 0 to {_MAX}"),
    ("plan", _edit(_SINGLE, ("topology", "kind"), "triple"), "topology.kind is one of single, duplicate, combined"),
    ("plan", _COMBINED_NO_SOURCES, "topology.sources is a list of strings"),
    ("plan", _edit(_SINGLE, ("ids", "task_id"), "\ud800"),
     "the routing request is not JSON data the router can digest (a value that is not JSON, or a string with a lone surrogate)"),
    ("pool-plan", "x", "the pool routing request is a JSON object"),
    ("pool-plan", _edit(POOL_11, ("port_version",), "1.0"), "port_version: this router reads pool port versions 1.1, 1.2"),
    ("pool-plan", _edit(POOL_11, ("items", 1, "item_id"), "d1"),
     "the pool routing request names one item_id twice: every dossier is one item of the batch"),
    ("pool-plan", _edit(POOL_11, ("limits", "per_instance_quota"), 0), f"limits.per_instance_quota is an integer from 1 to {_MAX}"),
    ("pool-plan", _edit(POOL_11, ("limits", "max_instances"), "4"), f"limits.max_instances is an integer from 1 to {_MAX}"),
    ("pool-plan", _edit(POOL_11, (*_ITEM, "risk_signals"), "contradiction"), "items[0].risk_signals is a list of strings"),
    ("pool-plan", _edit(POOL_11, (*_ITEM, "repeated_faults"), None), f"items[0].repeated_faults is an integer from 0 to {_MAX}"),
    ("pool-plan", _edit(POOL_11, (*_ITEM, "advised"), 1), "items[0].advised is true or false"),
    ("pool-plan", _edit(POOL_12, (*_ITEM, "features", "chars"), delete=True), f"items[0].features.chars is an integer from 0 to {_MAX}"),
    ("pool-plan", _edit(POOL_12, ("items", 5, "merged"), None), "items[5].merged is a JSON object"),
    ("pool-plan", _edit(POOL_12, ("items", 5, "sources"), "ab"), "items[5].sources is a list of parts"),
    ("pool-plan", _edit(POOL_12, ("items", 5, "sources", 1, "risk_signals"), None), "items[5].sources[1].risk_signals is a list of strings"),
    ("pool-plan", _edit(POOL_12, ("items", 5, "merged", "features", "stem"), 0), "items[5].merged.features.stem is true or false"),
]


@pytest.mark.parametrize("op,request_doc,reason", REFUSALS, ids=[r for _, _, r in REFUSALS])
def test_a_request_the_router_does_not_read_is_refused_with_its_reason_before_anything_is_planned(op, request_doc, reason, monkeypatch):
    def planned(*args, **kwargs):
        raise AssertionError("planned a request the router does not read")
    monkeypatch.setattr(planner, "_readings", planned)
    monkeypatch.setattr(pool, "_escalated", planned)
    with pytest.raises(contract.RequestError) as exc:
        _call(op, json.dumps(request_doc))
    assert str(exc.value) == reason and isinstance(exc.value, ValueError)


@pytest.mark.parametrize("text,reason", [
    (b"\xff\xfe\x00", "the request is not JSON text"),
    (42, "the request is not JSON text"),
    ('{"a": 1,}', "the request is not JSON text (line 1, column 8)"),  # the trailing comma's column
    ('{"a": NaN}', "the request holds NaN, which is not JSON"),
    ('[-Infinity]', "the request holds -Infinity, which is not JSON"),
    ('{"limits": {}, "limits": {}}', "the request names one member twice in one object"),
    ("[" * 100_000, "the request is nested too deep to decode"),
])
def test_text_that_is_not_json_the_router_reads_is_refused_with_its_reason(text, reason):
    for op in ("plan", "pool-plan"):
        with pytest.raises(contract.RequestError) as exc:
            _call(op, text)
        assert str(exc.value) == reason


def test_pool_port_1_2_without_the_decision_maker_s_data_is_refused_with_its_reason(tmp_path):
    dest = tmp_path / "data-0.2.0"
    shutil.copytree(Path(rules.DATA_DIR), dest)
    manifest = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["current"] = {"rules": "rules-2.json", "cost_data": "cost-data-2.json"}
    (dest / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    old = port.FlashRouter(str(dest))
    assert json.loads(old.pool_plan(json.dumps(POOL_11)))["port_version"] == "1.1"
    with pytest.raises(contract.RequestError) as exc:
        old.pool_plan(json.dumps(POOL_12))
    assert str(exc.value) == "pool port 1.2 needs the flash decision maker's data (rules/3): this data directory plans pool port 1.1 only"


# ----------------------------------------------------------------------------------------------- any request: planned or refused
_LEAVES = st.one_of(
    st.none(), st.booleans(), st.integers(-3, 70), st.sampled_from([_MAX, _MAX + 1, -_MAX - 1, 10**30, 10**4000]),
    st.floats(allow_nan=True, allow_infinity=True),
    st.sampled_from(["", "x", "\ud800", "standard", "fast", "turbo", "single", "duplicate", "combined", "REJECTED", "ACCEPTED", "1.1", "1.2",
                     "1.0", "d1", "m-1", "m-s", "ENTAILED", "COUNTEREXAMPLE"]),
)
_KEYS = st.sampled_from(["chars", "words", "stem", "translations", "translated", "repeated_faults", "risk_signals", "risk_records", "status",
                         "kind", "sources", "synthesis", "features", "merged", "advised", "profiles", "x"])
_VALUES = st.recursive(_LEAVES, lambda inner: st.lists(inner, max_size=3) | st.dictionaries(_KEYS, inner, max_size=3), max_leaves=6)


def _paths(doc, prefix: tuple = ()):
    yield prefix
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from _paths(v, prefix + (k,))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from _paths(v, prefix + (i,))


@st.composite
def _mutated(draw) -> tuple[str, object]:
    """A request in contract with one to three of its members replaced, removed, added to, repeated or emptied."""
    op, base = draw(st.sampled_from(BASES))
    doc: object = copy.deepcopy(base)
    for _ in range(draw(st.integers(1, 3))):
        path = draw(st.sampled_from(list(_paths(doc))))
        action = draw(st.sampled_from(("replace", "replace", "delete", "add", "repeat", "empty")))
        value = draw(_VALUES)
        if not path:
            doc = value if action == "replace" else doc
            continue
        parent = doc
        for k in path[:-1]:
            parent = parent[k]
        k = path[-1]
        if action == "replace":
            parent[k] = value
        elif action == "delete":
            del parent[k]
        elif action == "add" and isinstance(parent[k], dict):
            parent[k][draw(_KEYS)] = value
        elif action == "add" and isinstance(parent[k], list):
            parent[k].append(value)
        elif action == "repeat" and isinstance(parent, list):
            parent.append(copy.deepcopy(parent[k]))
        elif action == "empty" and isinstance(parent[k], (dict, list)):
            parent[k] = type(parent[k])()
    return op, doc


@settings(max_examples=600, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_mutated())
def test_any_request_is_planned_or_refused_with_its_reason_and_never_reads_as_a_fault_of_the_router(case):
    """The property the runner's exit statuses rest on: whatever request it is given, the router plans it or refuses it
    with a RequestError (exit 3); nothing a request holds makes the planners raise (exit 4 is the router's own fault)."""
    op, doc = case
    text = json.dumps(doc)  # NaN and Infinity under JSON's names for them, a lone surrogate escaped
    try:
        plan = json.loads(_call(op, text))
    except contract.RequestError as exc:
        assert str(exc) and type(exc) is contract.RequestError
        expected = 3
    else:
        assert plan["origin"] == "router" and plan["schema"] in ("epinoic.integration.routing-plan.v1", "epinoic.integration.pool-routing-plan.v1")
        expected = 0
    stdin, out, err = sys.stdin, io.StringIO(), io.StringIO()
    try:
        sys.stdin = io.StringIO(text)
        with redirect_stdout(out), redirect_stderr(err):
            status = runner_main([op])
    finally:
        sys.stdin = stdin
    assert status == expected, err.getvalue()
    assert (out.getvalue() == "") == (status == 3) and (err.getvalue() == "") == (status == 0)


# ----------------------------------------------------------------------------------------------- no stricter than the port
_CLASSES = list(RP.POOL_RISK_CLASSES)
_SIZE = st.one_of(st.none(), st.fixed_dictionaries({"transfers": st.integers(0, 50), "chars": st.sampled_from([0, 9000, 300_000, 525_000, 900_000]),
                                                     "stem": st.booleans(), "translations": st.integers(0, 4)}))
_SIGNALS = st.lists(st.sampled_from(_CLASSES), max_size=2, unique=True).map(sorted)
_PART = st.fixed_dictionaries({"repeated_faults": st.integers(0, 2), "risk_signals": _SIGNALS, "risk_records": _SIGNALS, "features": _SIZE})
_ITEM_12 = st.fixed_dictionaries({"repeated_faults": st.integers(0, 2), "risk_signals": _SIGNALS, "risk_records": _SIGNALS, "advised": st.booleans(),
                                  "features": _SIZE},
                                 optional={"sources": st.lists(_PART, min_size=2, max_size=5)}).map(
    lambda it: {**it, "merged": {"repeated_faults": 0, "risk_signals": [], "risk_records": [], "features": None}} if it.get("sources") else it)


@settings(max_examples=150, deadline=None)
@given(st.lists(_ITEM_12, max_size=12), st.integers(2, 64), st.integers(1, 20), st.sampled_from([("standard",), ("standard", "fast"), ("fast",)]))
def test_every_pool_port_1_2_request_the_port_accepts_is_planned(items, max_instances, quota, profiles):
    req = RP.build_pool_request(items, max_instances=max_instances, per_instance_quota=quota, profiles=profiles, port_version="1.2")
    hello = RP.check_pool_hello(port.pool_hello())
    plan = RP.check_pool_plan(port.pool_plan(RP.canonical_json(RP.dump(req))), req, hello=hello)
    assert [a.item_id for a in plan.assignments] == [it.item_id for it in req.items]
