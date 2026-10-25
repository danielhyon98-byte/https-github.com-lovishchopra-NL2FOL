"""The result store: put and verify, duplicates, eviction and tombstones, local and external key ids, and faithful
re-parsing of results serialised with ``exclude_none``."""
from __future__ import annotations

import json

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.provenance import sign_result
from epinoic_logic.engine.sink import CapturedResult, capture_results
from epinoic_logic.ir.canonical import canonical_json, sha256_hex
from epinoic_logic.overseer import EngineKey, KeyRing, ResultStore
from epinoic_logic.overseer.contracts import Citation, ResultTombstone, StoredResult
from epinoic_logic.overseer.faithful import faithful
from epinoic_logic.engine.results import VerificationResult
from epinoic_logic.translate.contracts import SpecialistReport

from .conftest import CFG, KEY, OTHER_KEY, SECRET, english_report, int_problem, make_keyring


def _captured(key=KEY, key_id="t", cfg=CFG, value=5):
    with capture_results() as cap:
        verify(int_problem("c1", "x", value, op="gt", bound=3), cfg, signing_key=key, key_id=key_id)
    return cap.items[0]


def _put(store, c, uid="ch-1", seq=1, origin="captured"):
    return store.put(c, channel_uid=uid, task_id="task-ovs", request_id="req-ovs", event_seq=seq, origin=origin)


def test_put_verifies_the_signature_and_records_the_origin():
    store = ResultStore(make_keyring())
    out = _put(store, _captured())
    assert out.new and out.conflict is None
    rec = store.get(out.stored.result_id)
    assert isinstance(rec, StoredResult) and rec.signature_ok_at_put and rec.key_status == "local" and rec.origin == "captured"
    assert rec.status == "ENTAILED" and store.parsed(rec.result_id).status.value == "ENTAILED"


def test_result_with_dropped_none_fields_still_verifies_after_storage():
    """``memory_max_mb=None`` is dropped by ``exclude_none``; a naive re-parse restores 512 and breaks the signature."""
    c = _captured(cfg=SolverConfig(timeout_ms=3000, memory_max_mb=None))
    assert "memory_max_mb" not in json.loads(c.result_json)["solver_config"]
    naive = VerificationResult.model_validate(json.loads(c.result_json))
    assert naive.solver_config.memory_max_mb == 512  # the hazard
    store = ResultStore(make_keyring())
    rec = _put(store, c).stored
    assert rec.signature_ok_at_put
    assert canonical_json(store.parsed(rec.result_id).model_dump(mode="json", exclude_none=True)) == c.result_json


def test_faithful_restores_course_level_none_in_reports():
    rep = english_report().model_copy(update={"course_level": None})
    dump = rep.model_dump(mode="json", exclude_none=True)
    assert "course_level" not in dump
    assert SpecialistReport.model_validate(dump).course_level == "unknown"
    again = faithful(SpecialistReport, dump)
    assert again.course_level is None and again.model_dump(mode="json", exclude_none=True) == dump


def test_unsigned_wrong_key_and_undeclared_key_ids_are_recorded_not_trusted():
    store = ResultStore(make_keyring())
    unsigned = _put(store, _captured(key=None, key_id=None)).stored
    assert not unsigned.signature_ok_at_put and unsigned.signature_reason == "unsigned"
    wrong = _put(store, _captured(key=OTHER_KEY, key_id="t")).stored
    assert not wrong.signature_ok_at_put and "does not verify" in wrong.signature_reason
    undeclared = _put(store, _captured(key=KEY, key_id="mystery")).stored
    assert not undeclared.signature_ok_at_put and "undeclared" in undeclared.signature_reason and undeclared.key_status == "unknown"


def test_external_key_ids_verify_and_are_marked_external():
    kr = KeyRing({"t": EngineKey(KEY), "remote": EngineKey(OTHER_KEY, scope="external")}, SECRET)
    store = ResultStore(kr)
    rec = _put(store, _captured(key=OTHER_KEY, key_id="remote"), origin="external").stored
    assert rec.signature_ok_at_put and rec.key_status == "external" and rec.origin == "external"


def test_same_content_is_idempotent_and_a_second_content_is_a_conflict():
    store = ResultStore(make_keyring())
    c = _captured()
    first = _put(store, c)
    again = _put(store, c, uid="ch-1", seq=1)
    assert first.new and not again.new and again.conflict is None
    res = faithful(VerificationResult, json.loads(c.result_json))
    altered = sign_result(res.model_copy(update={"diagnostics": []} | {"reason_unknown": "edited"}), KEY, "t")
    js = canonical_json(altered.model_dump(mode="json", exclude_none=True))
    out = _put(store, CapturedResult(c.result_id, "t", js, sha256_hex(js), c.problem_json, c.problem_digest), seq=2)
    assert out.conflict == (c.result_sha256, sha256_hex(js))
    assert store.get(c.result_id).result_sha256 == c.result_sha256  # the first content is kept
    assert store.contents(c.result_id) == {c.result_sha256, sha256_hex(js)}


def test_per_channel_bound_evicts_oldest_and_leaves_tombstones():
    store = ResultStore(make_keyring(), max_results=2)
    ids = [_put(store, _captured(value=5 + i), seq=i + 1).stored.result_id for i in range(3)]
    oldest = store.get(ids[0])
    assert isinstance(oldest, ResultTombstone) and oldest.signature_ok_at_put and oldest.status == "ENTAILED"
    assert store.live(ids[0]) is None and store.parsed(ids[0]) is None and store.is_tombstoned(ids[0])
    assert isinstance(store.get(ids[2]), StoredResult) and store.evictions == 1
    # membership survives eviction: the same id offered again with other content is still a conflict
    assert store.index(ids[0])[0][1] == "ch-1"


def test_global_bound_evicts_sealed_channels_first():
    probe = ResultStore(make_keyring())
    one = _put(probe, _captured()).stored.size()
    store = ResultStore(make_keyring(), global_max_bytes=int(one * 2.5))
    a = _put(store, _captured(value=6), uid="sealed").stored.result_id
    store.seal_channel("sealed")
    b = _put(store, _captured(value=7), uid="open").stored.result_id
    c = _put(store, _captured(value=8), uid="open").stored.result_id
    assert isinstance(store.get(a), ResultTombstone)
    assert isinstance(store.get(b), StoredResult) and isinstance(store.get(c), StoredResult)


def test_citations_digest_and_memo():
    store = ResultStore(make_keyring())
    rid = _put(store, _captured()).stored.result_id
    store.cite(rid, Citation(event_seq=1, kind="outcome", path="outcomes[0].verification"))
    store.cite(rid, Citation(event_seq=1, kind="outcome", path="outcomes[0].verification"))
    assert len(store.citations(rid)) == 1
    assert store.digest([rid, "missing"]) == store.digest(["missing", rid, rid])
    store.memo_put("k", (1, 2))
    assert store.memo_get("k") == (1, 2) and store.memo_get("absent") is None


def test_digest_only_capture_is_not_stored():
    store = ResultStore(make_keyring())
    c = _captured()
    out = _put(store, CapturedResult(c.result_id, c.key_id, "", c.result_sha256, None, c.problem_digest))
    assert out.stored is None and out.parse_error
