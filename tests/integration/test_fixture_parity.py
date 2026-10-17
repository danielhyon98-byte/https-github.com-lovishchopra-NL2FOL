"""Fixture-verifier parity (PROTOCOL.md section 14.1): on the synthetic corpus, the simulation's fixture verifier and
``run_arena.run_round`` serve exactly the same fixtures to the same claims, leave the same ones unserved and reach the
same receipt statuses, finding codes, claim statuses and branch formal checks. The arena runs on a fresh copy of the
corpus round; nothing is written into the kit."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "integration" / "sim" / "corpus" / "synthetic" / "s1"
ARENA = ROOT / "scripts" / "arena"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def arena_run(tmp_path_factory):
    sys.path.insert(0, str(ARENA))
    import run_arena as ra
    copy = tmp_path_factory.mktemp("parity") / "s1"
    shutil.copytree(CORPUS, copy)
    out = ra.run_round(copy)
    return ra, copy, out


def test_the_corpus_is_served_identically_by_the_fixture_verifier_and_the_arena(arena_run):
    ra, copy, out = arena_run
    fv = _module("kit_sim_fixture_verifier", ROOT / "integration" / "sim" / "fixture_verifier.py")
    compare = _module("kit_sim_compare", ROOT / "integration" / "sim" / "compare.py")
    corpus = fv.load_corpus(copy)
    records = [r for r in out["records"] if r.get("variant") == "genuine"]
    items = ra.load_items(copy / "specialists")
    assert len(records) == len(items) == 6
    fields = ("status", "finding_codes", "claim_statuses", "formal_checks", "fixtures_served", "fixtures_unserved")
    for item in items:
        stem = item["_path"].stem
        fixture_ids = json.loads((copy / "translations" / f"{stem}.json").read_text(encoding="utf-8"))["claims"].keys()
        record = next(r for r in records if r["file"] == f"{stem}.json")
        plan = ra.group_plan(items, ra.group_of(item))
        _reply, rc = fv.deliver_genuine(corpus, item, plan, config=ra.CFG, signing_key=ra.KEY, supplied=ra.supplied(item))
        ours = compare.receipt_projection(rc.model_dump(mode="json"), fixture_ids=fixture_ids)
        theirs = compare.record_projection(record, fixture_ids=fixture_ids)
        assert {f: ours[f] for f in fields} == {f: theirs[f] for f in fields}, stem
        assert ours["fixtures_served"], f"{stem}: the corpus item's fixtures are served"


def test_the_arena_round_on_the_synthetic_corpus_is_functional_and_unqualified(arena_run):
    _ra, _copy, out = arena_run
    genuine = [r for r in out["records"] if r.get("variant") == "genuine"]
    assert all(r.get("functional") for r in genuine), [r.get("failure_reasons") or r.get("error") for r in genuine if not r.get("functional")]
    assert not out.get("qualified"), out.get("qualifications")


def test_items_the_fixture_verifier_cannot_replay_alone_are_refused_by_name():
    fv = _module("kit_sim_fixture_verifier2", ROOT / "integration" / "sim" / "fixture_verifier.py")
    assert fv.unsupported_item({"task_id": "x", "peer_of": "y"})
    assert fv.unsupported_item({"task_id": "x", "group": "g"})
    assert fv.unsupported_item({"task_id": "x"}) is None


def test_the_website_path_and_the_arena_bind_the_same_encodings(arena_run, tmp_path):
    """G-EQ's digest comparison across request ids: the checks port's call (request id = the attempt id) and the arena's
    genuine pass (request id req-<item>) encode the same problems; once the problem's request id is normalised, the
    problem, configuration, limits and binding digests of every result are equal."""
    ra, copy, _out = arena_run
    from epinoic_logic.integration.checks_port import check_request
    from epinoic_logic.integration.runtime import build_runtime
    from tests.integration.helpers import FixtureProbes, answer_envelope, settings, turn_request
    fv = _module("kit_sim_fixture_verifier3", ROOT / "integration" / "sim" / "fixture_verifier.py")
    compare = _module("kit_sim_compare3", ROOT / "integration" / "sim" / "compare.py")
    rt = build_runtime(settings(FIXTURE_DIR=str(copy), SIM_EVIDENCE_DIR=str(tmp_path / "ev")), probes=FixtureProbes())
    corpus = fv.load_corpus(copy)
    items = {it["_path"].stem: it for it in ra.load_items(copy / "specialists")}
    for stem in ("hi-s1", "hi-s2", "hi-s3"):
        item = items[stem]
        req = check_request(turn_request([answer_envelope(1, answer=item["response_text"])], user_text=item["question"],
                                         request_id=f"a_{stem}_00000001"), rt.request_limits, service_env="sim")
        rt.checker.check(req)
        evidence = json.loads((tmp_path / "ev" / f"a_{stem}_00000001.json").read_text(encoding="utf-8"))
        website = [r for r in evidence["receipts"] if r and r["direction"] == "specialist_to_router"][-1]
        _reply, rc = fv.deliver_genuine(corpus, item, ra.group_plan(list(items.values()), ra.group_of(item)), config=ra.CFG, signing_key=ra.KEY)
        ours = sorted(d for d in (compare.result_digests(o) for o in website["outcomes"]) if d)
        theirs = sorted(d for d in (compare.result_digests(o) for o in rc.model_dump(mode="json")["outcomes"]) if d)
        assert ours and ours == theirs, stem
        raw_ours = sorted(d for d in (compare.result_digests(o, normalize_request_id=False) for o in website["outcomes"]) if d)
        raw_theirs = sorted(d for d in (compare.result_digests(o, normalize_request_id=False) for o in rc.model_dump(mode="json")["outcomes"]) if d)
        assert raw_ours != raw_theirs  # the raw digests differ only by the request id the problem carries


def test_a_fixture_recorded_for_another_request_is_refused_on_both_paths(arena_run, tmp_path):
    """The arena gives an item the request id req-<item> (req-<group> for a grouped one) and refuses a fixture recorded
    under another one (an adversarial variant reusing another item's fixture). The checks port re-keys a fixture only
    from its item's arena request id, so it refuses the same fixture the same way; a fixture recorded under the item's
    own arena request id is re-keyed to the call's request id and served, as before."""
    ra, _copy, _out = arena_run
    from epinoic_logic.integration.checks_port import check_request
    from epinoic_logic.integration.runtime import build_runtime
    from epinoic_logic.integration.verifier import FixtureCorpus, rekeyed_fixture
    from tests.integration.helpers import FixtureProbes, answer_envelope, settings, turn_request
    variant = tmp_path / "s1"
    (variant / "specialists").mkdir(parents=True)
    (variant / "translations").mkdir()
    for d in ("specialists", "translations"):  # hi-s1 under another name: its fixtures still carry req-hi-s1
        shutil.copyfile(CORPUS / d / "hi-s1.json", variant / d / "hi-s1-variant.json")
    out = ra.run_round(variant)
    [record] = [r for r in out["records"] if r.get("variant") == "genuine"]
    arena_statuses = {o["claim_id"]: o["display_status"] for o in record["outcomes"]}
    assert arena_statuses.get("h1.1") == "INVALID_FORMALIZATION", arena_statuses
    rt = build_runtime(settings(FIXTURE_DIR=str(variant), SIM_EVIDENCE_DIR=str(tmp_path / "ev")), probes=FixtureProbes())
    item = json.loads((variant / "specialists" / "hi-s1-variant.json").read_text(encoding="utf-8"))
    req = check_request(turn_request([answer_envelope(1, answer=item["response_text"])], user_text=item["question"], request_id="a_variant_00000001"),
                        rt.request_limits, service_env="sim")
    rt.checker.check(req)
    evidence = json.loads((tmp_path / "ev" / "a_variant_00000001.json").read_text(encoding="utf-8"))
    website = [r for r in evidence["receipts"] if r and r["direction"] == "specialist_to_router"][-1]
    ours = {o["claim_id"]: o["display_status"] for o in website["outcomes"]}
    assert ours.get("h1.1") == arena_statuses["h1.1"] and ours == arena_statuses, (ours, arena_statuses)
    # the rule itself, and the arena request ids the corpus derives
    fixture = {"problem": {"request_id": "req-hi-s1", "claim_id": "h1.1"}}
    assert json.loads(rekeyed_fixture(fixture, "a_x", only_from="req-hi-s1"))["problem"]["request_id"] == "a_x"
    assert json.loads(rekeyed_fixture(fixture, "a_x", only_from="req-hi-s1-variant"))["problem"]["request_id"] == "req-hi-s1"
    assert FixtureCorpus.load(variant)._arena_request_ids == {"hi-s1-variant": "req-hi-s1-variant"}
    assert FixtureCorpus.load(CORPUS)._arena_request_ids["hi-s1"] == "req-hi-s1"
