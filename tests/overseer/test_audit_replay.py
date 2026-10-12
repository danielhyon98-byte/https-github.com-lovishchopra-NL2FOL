"""R1 replay on a fresh engine: agreement, RES-007 and RES-008, keyed sampling with always-replay classes and AUDIT-003,
the isolated worker process, and the insider who re-signs a rewritten status (T11)."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.provenance import sign_result
from epinoic_logic.engine.sink import capture_results, emit
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.canonical import canonical_json
from epinoic_logic.overseer import EngineKey, KeyRing, Replayer, ReplayJob
from epinoic_logic.overseer.checks import Replay
from epinoic_logic.overseer.replay import classify, compare, replay_problem
from epinoic_logic.translate.outcome import compose_outcome

from .conftest import CFG, KEY, OTHER_KEY, SECRET, findings, int_problem, make_auditor, make_keyring, run_task, translation_for


_BINDINGS: dict = {}


def _job(rid="r1", status="ENTAILED", always=False, problem=None, cfg=CFG):
    p = problem or int_problem("c1", "x", 5, op="gt", bound=3)
    key = canonical_json(p) + canonical_json(cfg.model_dump(mode="json"))
    if key not in _BINDINGS:
        _BINDINGS[key] = verify(p, cfg)
    res = _BINDINGS[key]
    return ReplayJob(result_id=rid, problem_json=canonical_json(p), config_json=canonical_json(cfg.model_dump(mode="json")), original_status=status,
                     problem_digest=res.binding.problem_digest, config_digest=res.binding.config_digest, versions_digest=res.binding.versions_digest, always=always)


def _replay(**kw) -> Replay:
    base = dict(result_id="r", replay_result_id="rr", original_status="ENTAILED", replay_status="ENTAILED", problem_digest_ok=True, config_digest_ok=True,
                versions_changed=False, budget_exceeded=False)
    base.update(kw)
    return Replay(**base)


def test_classification_of_replays():
    assert classify(_replay()) is None
    assert classify(_replay(replay_status="COUNTEREXAMPLE")) == "OVS-RES-007"
    assert classify(_replay(problem_digest_ok=False)) == "OVS-RES-007"
    assert classify(_replay(config_digest_ok=False)) == "OVS-RES-007"
    # review round 2 (rewritten more strictly): a DEFINITIVE signed status the replay cannot reproduce (undecided, versions
    # changed, budget exceeded) is OVS-AUDIT-005 (error, cannot pass), no longer the RES-008 warning; RES-008 stays for an
    # original that was itself undecided
    assert classify(_replay(replay_status="TIMEOUT")) == "OVS-AUDIT-005"
    assert classify(_replay(original_status="UNKNOWN", replay_status="ENTAILED")) == "OVS-RES-008"
    assert classify(_replay(versions_changed=True, replay_status="COUNTEREXAMPLE")) == "OVS-AUDIT-005"
    assert classify(_replay(versions_changed=True)) is None
    assert classify(_replay(replay_status=None, replay_result_id=None, budget_exceeded=True)) == "OVS-AUDIT-005"
    assert classify(_replay(original_status="TIMEOUT", replay_status=None, replay_result_id=None, budget_exceeded=True)) == "OVS-RES-008"
    assert classify(_replay(original_status="TIMEOUT", replay_status="TIMEOUT")) is None


def test_replay_problem_reproduces_status_and_binding():
    job = _job()
    out = json.loads(replay_problem(job.problem_json, job.config_json))
    assert out["status"] == "ENTAILED" and out["binding"]["problem_digest"] == job.problem_digest and out["binding"]["config_digest"] == job.config_digest
    assert "signature" not in out  # the worker never signs


def test_inline_replayer_signs_replays_under_the_run_key():
    kr = make_keyring()
    rp = Replayer(kr, mode="inline")
    rp.submit(_job())
    assert rp.pending() == {"r1"}
    rp.drain()
    o = rp.outcomes()["r1"]
    data = json.loads(o.result_json)
    assert data["signature_key_id"] == "overseer-run"
    from epinoic_logic.overseer.faithful import faithful
    from epinoic_logic.engine.results import VerificationResult
    assert kr.verify_result(faithful(VerificationResult, data)) == (True, "ok")
    r = compare(o.job, faithful(VerificationResult, data))
    assert classify(r) is None and r.replay_status == "ENTAILED"


def test_keyed_sampling_is_reproducible_and_spares_always_jobs():
    def run():
        rp = Replayer(make_keyring(), mode="inline", queue_bound=2, sample_rate=0.25)
        verdicts = [rp.submit(_job(rid=f"r{i}")) for i in range(60)]
        always = rp.submit(_job(rid="must", always=True))
        return rp, verdicts, always
    rp1, v1, a1 = run()
    rp2, v2, a2 = run()
    assert v1 == v2 and a1 == a2 == "queued"
    assert v1[:2] == ["queued", "queued"] and "sampled_out" in v1
    kr = make_keyring()
    for i, v in enumerate(v1[2:], start=2):
        assert (v == "queued") == (kr.sample_fraction(f"r{i}") < 0.25)
    sampled = rp1.sampled_out()
    rp1.drain(include_sampled=True)
    assert sampled and sampled <= set(rp1.outcomes()) and not rp1.sampled_out()
    with pytest.raises(ValueError):
        Replayer(make_keyring(), mode="inline", sample_rate=0.1)


def test_a_sampled_out_result_is_promoted_when_it_becomes_always():
    rp = Replayer(make_keyring(), mode="inline", queue_bound=0, sample_rate=0.25)
    kr = make_keyring()
    rid = next(f"x{i}" for i in range(100) if kr.sample_fraction(f"x{i}") >= 0.25)
    assert rp.submit(_job(rid=rid)) == "sampled_out"
    assert rp.submit(_job(rid=rid, always=True)) == "queued"
    rp.drain()
    assert rid in rp.outcomes()


def test_process_mode_replays_in_an_isolated_worker():
    rp = Replayer(make_keyring(), mode="process")
    try:
        rp.submit(_job(rid="p1"))
        rp.submit(_job(rid="p2", problem=int_problem("c2", "y", 1, op="gt", bound=3)))
        rp.drain(timeout_s=60)
        outs = rp.outcomes()
        assert set(outs) == {"p1", "p2"} and all(o.result_json for o in outs.values())
        assert json.loads(outs["p2"].result_json)["status"] == "COUNTEREXAMPLE"
        assert rp._proc is not None and rp._proc.pid != __import__("os").getpid()
    finally:
        rp.close()


def test_control_task_replays_agree(auditor):
    task = run_task(auditor)
    audit = task.audit()
    assert audit.coverage.results_replayed > 0 and audit.coverage.replay_mode == "inline"
    assert not findings(audit, "OVS-RES-007") and not findings(audit, "OVS-RES-008")


def _external_ring():
    return KeyRing({"hub": EngineKey(KEY), "channel": EngineKey(KEY), "integrity": EngineKey(KEY), "t": EngineKey(KEY),
                    "remote": EngineKey(OTHER_KEY, scope="external")}, SECRET)


def test_t11_insider_resigns_a_rewritten_status_with_an_external_engine_key():
    """The forged result's signature verifies (the insider holds the external engine's key); only replay exposes it."""
    auditor = make_auditor(keyring=_external_ring())
    try:
        problem = int_problem("en-point", "work_hours", 12, op="gt", bound=8)
        honest = verify(problem, CFG, signing_key=OTHER_KEY, key_id="remote")
        forged = sign_result(honest.model_copy(update={"status": S.COUNTEREXAMPLE, "signature": None, "signature_key_id": None}), OTHER_KEY, "remote")

        def transform(_out, claim, report):
            return compose_outcome(claim, translation_for(claim, report, problem), forged, signing_key=OTHER_KEY, key_id="remote")
        from .conftest import problems_fn, new_channel, english_report, DOC, EN_INPUT
        ch = new_channel(auditor)
        ch.channel.verify_claim_fn = problems_fn({"en-point": problem}, transform=transform)
        m, _r, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        ch.respond(m.message_id, english_report())
        audit = auditor.audit(ch.uid)
        f = findings(audit, "OVS-RES-007")
        assert f and f[0].formal_result_id == forged.result_id and f[0].related_result_ids
        assert "COUNTEREXAMPLE" in f[0].message
        assert not findings(audit, "OVS-RES-003")  # the signature is genuine
        assert audit.transfer_states[_r_mid(audit, ch)] == "AUDIT_FAILED"
    finally:
        auditor.close()


def _r_mid(audit, ch):
    return ch.channel.receipts[-1].message_id


def test_t11_insider_emitting_a_forged_local_result_into_the_capture():
    """Even a forged result that reached the capture (an insider calling the sink) is exposed by replay."""
    auditor = make_auditor()
    try:
        problem = int_problem("en-point", "work_hours", 12, op="gt", bound=8)

        def transform(out, claim, report):
            forged = sign_result(out.verification.model_copy(update={"status": S.COUNTEREXAMPLE, "result_id": "forged-1", "signature": None, "signature_key_id": None}), KEY, "t")
            emit(forged, problem)
            return compose_outcome(claim, translation_for(claim, report, problem), forged, signing_key=KEY, key_id="t")
        from .conftest import problems_fn, new_channel, english_report, DOC, EN_INPUT
        ch = new_channel(auditor)
        ch.channel.verify_claim_fn = problems_fn({"en-point": problem}, transform=transform)
        m, _r, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        ch.respond(m.message_id, english_report())
        audit = auditor.audit(ch.uid)
        assert [f.formal_result_id for f in findings(audit, "OVS-RES-007")] == ["forged-1"]
    finally:
        auditor.close()


class _AlwaysOutRing(KeyRing):
    """Every non-always job beyond the bound is sampled out (the keyed fraction itself is tested above)."""
    __slots__ = ()

    def sample_fraction(self, result_id: str) -> float:
        return 0.99


def test_t17_overflow_samples_live_replay_and_the_batch_replays_everything():
    ring = _AlwaysOutRing({k: EngineKey(KEY) for k in ("hub", "channel", "default", "integrity", "t")}, SECRET)
    auditor = make_auditor(eager=False, queue_bound=1, keyring=ring)
    try:
        task = run_task(auditor)
        st = auditor._channels[task.uid]
        assert st.sampled_live > 0
        audit = task.audit()
        f = findings(audit, "OVS-AUDIT-003")
        assert f and f[0].severity == "info" and "of" in f[0].message
        assert audit.coverage.results_replayed == len(st.replay_jobs)
        assert audit.coverage.results_sampled_out == st.sampled_live
        assert not findings(audit, "OVS-RES-007")
    finally:
        auditor.close()


def test_pending_until_async_work_has_run():
    auditor = make_auditor(eager=False)
    try:
        task = run_task(auditor, synthesis=False)
        clr = auditor.clearance(task.uid, task.mids["rep_en"])
        assert clr.state == "AUDIT_PENDING" and clr.pending_result_ids
        assert any(k.startswith(("r2|", "l5|")) for k in clr.pending_result_ids)
        clr2 = auditor.clearance(task.uid, task.mids["rep_en"], wait_ms=5000)
        assert clr2.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and not clr2.pending_result_ids
    finally:
        auditor.close()


def test_the_default_process_mode_end_to_end():
    """Replays in the spawned worker, R2 and L5 in the background thread; PENDING until they finish; a FINAL audit in
    process mode is accepted as independent (no AUDIT-002 about inline replay)."""
    auditor = make_auditor(replay_mode="process", eager=False)
    try:
        task = run_task(auditor)
        first = auditor.clearance(task.uid, task.mids["rep_en"])
        assert first.state in ("AUDIT_PENDING", "AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")
        settled = auditor.clearance(task.uid, task.mids["rep_en"], wait_ms=30000)
        assert settled.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and not settled.pending_result_ids
        audit = task.audit(final=True)
        assert audit.coverage.replay_mode == "process" and audit.coverage.results_replayed > 0
        assert not [f for f in audit.report.findings if f.code == "OVS-AUDIT-002"]
        assert not [f for f in audit.report.findings if f.severity == "error"]
        replays = [auditor.store.get(r) for r in audit.report.formal_result_ids]
        assert any(r is not None and r.origin == "replay" and r.key_id == "overseer-run" and r.signature_ok_at_put for r in replays)
    finally:
        auditor.close()
