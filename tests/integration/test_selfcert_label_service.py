"""The meaning label in the checks service (meaning-check design 2.5.1 item 1, 2.5.6 to 2.5.9, 3.3; stage 2a, owner R5).

Every label here is scripted, made by the faithful fake the suite installs (``tests/conftest.py``), or the production default
(tests marked ``real_labeller``). No provider is called and no connection is opened. Expected values are fixed here:

* contract 0.10's protocol: the refusal ``selfcert_label_unavailable``, decision-table row 3b (``refuse_incomplete``,
  KIT-DL-014, before row 4), a named label as ``not_deliverable`` (KIT-DL-006), the codes KIT-HS-017 to 019;
* T18 for ``claims.claim_entries``: a claim the label names whose engine result would be a success is listed NOT_ELIGIBLE with
  ``withheld_self_report``; REFUTED (COUNTEREXAMPLE) and UNKNOWN are unchanged;
* T21: the hosted preflight refuses no labeller, a fake and a model digest without an acceptance record, 3 of 3, each with its
  own code; the simulation stays ready with the unconfigured default, which is ``UnconfiguredLabeller``;
* the handshake member and T12's hello part (a circuit breaker on a fake clock: ok, degraded, ok again);
* the service turn: step 4 submits the label and the hub joins it (one call), T16 (byte-identical requests at step 4 and at the
  hub on every genuine answer of the recorded rounds), the label guard (T3, T4, T5 through the service), and T1 through the
  service on the answers of the hub's T1 (0 delivered; KIT-DL-014 for each answer the reader passes, KIT-DL-006 kept for each
  it refuses);
* the daily INT-SELF-002 counts and the 2% alarm (counts only); the recorded labels of a fixture corpus, served by request key
  (an unrecorded key withholds as ``not-recorded``).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from epinoic_logic.integration import label as LBL
from epinoic_logic.integration.capabilities import build_capabilities
from epinoic_logic.integration.checks_port import check_request
from epinoic_logic.integration.claims import claim_entries
from epinoic_logic.integration.compat import SUBJECT_MAP
from epinoic_logic.integration.delivery import (
    BindingContext, DecisionInput, binding_problem, count_claims, decide, verify_verdict_signature,
)
from epinoic_logic.integration.errors import DELIVERY_CODES, HANDSHAKE_CODES, WORKER_RAW_CODES, IntegrationError
from epinoic_logic.integration.handshake import evaluate
from epinoic_logic.integration.overseer_port import check_delivery
from epinoic_logic.integration.preflight import run_preflight
from epinoic_logic.integration.protocol import INTEGRATION_CONTRACT_VERSION, OVERSEER_REFUSALS, PROTOCOL, SelfcertLabelCaps
from epinoic_logic.integration.runtime import build_runtime
from epinoic_logic.integration.selftest import run_selftest
from epinoic_logic.integration.settings import IntegrationSettings
from epinoic_logic.integration.turn import TurnChecker
from epinoic_logic.integration.verifier import FixtureCorpus
from epinoic_logic.selfcert_label import (
    LABEL_VERSION, CallFailure, CircuitBreakerLabeller, UnconfiguredLabeller, build_input, clear_shared_calls, label_digest,
    shared_calls_state,
)
from epinoic_logic.selfcert_label import labellers as L
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, reader_backed_reply, reply_json
from tests.integration.helpers import (
    VERDICT_KEY_HEX, FixtureProbes, RealPort, RecordingPort, answer_envelope, settings, turn_request,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "integration" / "sim" / "corpus" / "synthetic" / "s1"
ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
NAMED = "The hyperinflation peaked in 1923, four years after the treaty was signed."
#: The settings of a hosted (staging) service that pass every part of the preflight before the meaning label.
HOSTED = {"PROFILE": "integration", "SERVICE_ENV": "staging", "TRANSLATION_PROVIDER": "anthropic", "ANTHROPIC_MODEL": "configured-model-id"}


def _item(name: str) -> dict:
    return json.loads((CORPUS / "specialists" / f"{name}.json").read_text(encoding="utf-8"))


def _gate(sentence: str, category: str = "OUTCOME"):
    def script(req, n):
        return reply_json(req, {it.id: [(sentence, category)] for it in req.items if it.canary is None and it.text == sentence})
    return script


def _runtime(port=None, *, labeller=None, **env):
    port = port or RecordingPort()
    rt = build_runtime(settings(FIXTURE_DIR=str(CORPUS), **env), probes=FixtureProbes(port))
    if labeller is not None:
        c = rt.checker
        rt.checker = TurnChecker(c.cfg, port=c.port, corpus=c.corpus, router=c.router, evidence_tap=c.tap, labeller=labeller)
    return rt, port


def _run(rt, name="hi-s1", *, answer=None):
    item = _item(name)
    text = item["response_text"] if answer is None else answer
    env = answer_envelope(1, agent_id="history", answer=text, slug="history")
    req = check_request(turn_request([env], user_text=item["question"]), rt.request_limits, service_env="sim")
    verdict = rt.checker.check(req)
    assert verify_verdict_signature(verdict, bytes.fromhex(VERDICT_KEY_HEX))
    release = text if verdict["delivery"]["decision"] == "deliver" else None
    ctx = BindingContext(task_id=req.ids.task_id, request_id=req.ids.request_id, user_text=req.task.user_text, policy=req.policy,
                         mode=req.mode, answers=[(env["agent_id"], text, env["result_sha256"])], release_text=release)
    assert binding_problem(verdict, ctx) is None, "the Worker re-derives the same decision from the verdict"
    return verdict


# ============================================================================================ protocol, contract 0.10
def test_contract_0_10_names_the_refusal_the_codes_and_the_handshake_member():
    assert INTEGRATION_CONTRACT_VERSION == "0.10"
    assert "selfcert_label_unavailable" in OVERSEER_REFUSALS and OVERSEER_REFUSALS[-1] == "selfcert_label_unavailable"
    assert DELIVERY_CODES["KIT-DL-014"] == "selfcert_label_unavailable" and "kit_dl_014" in WORKER_RAW_CODES
    assert [HANDSHAKE_CODES[f"KIT-HS-0{n}"] for n in (17, 18, 19)] == [
        "selfcert_label_unconfigured", "selfcert_label_not_admitted", "selfcert_label_unaccepted"]
    caps = SelfcertLabelCaps(version=LABEL_VERSION, label_digest="d0" * 32, required=True, labeller="provider", model_digest="d1" * 32,
                             state="degraded")
    assert caps.state == "degraded"
    for bad in ({"state": "passed"}, {"model_digest": "a-model-name"}, {"labeller": "live"}, {"required": False}, {"version": "label-1"}):
        with pytest.raises(Exception):
            SelfcertLabelCaps(**{**caps.model_dump(), **bad})


def _inp(**kw) -> DecisionInput:
    base = dict(policy="verified-v1", revision_of=None, receipt_status="ACCEPTED_WITH_FINDINGS", receipt_error_codes=(), overseer_state="AUDIT_PASSED",
                delivery_allowed=False, overseer_refusal="selfcert_label_unavailable", consolidation_status="NO_DELIVERABLE_OUTPUT", blocking=0,
                unavailable=0, budget_skipped=0)
    base.update(kw)
    return DecisionInput(**base)


@pytest.mark.parametrize("kw,expected", [
    ({}, ("refuse_incomplete", ["KIT-DL-014"])),
    # row 3b comes before row 4 and row 5: an answer the label did not read is an outage, never a revision request
    ({"receipt_error_codes": ("INT-SUBJ-001",), "blocking": 1, "unavailable": 2, "budget_skipped": 1}, ("refuse_incomplete", ["KIT-DL-014"])),
    ({"policy": "verified-v1-qualify"}, ("refuse_incomplete", ["KIT-DL-014"])),
    # row 2 (integrity) and row 3 (pending) come first
    ({"receipt_status": "REJECTED"}, ("refuse_integrity", ["KIT-DL-001"])),
    ({"overseer_state": "AUDIT_FAILED"}, ("refuse_integrity", ["KIT-DL-005"])),
    ({"overseer_state": "AUDIT_PENDING"}, ("refuse_incomplete", ["KIT-DL-004"])),
    # a label that names a self-certification refuses as a reader hit does
    ({"overseer_refusal": "not_deliverable"}, ("refuse_integrity", ["KIT-DL-006"])),
])
def test_row_3b_refuses_an_unread_answer_as_an_outage(kw, expected):
    decision, reasons = decide(_inp(**kw))
    assert (decision, reasons) == expected


def test_the_overseer_port_accepts_the_label_refusal():
    raw = {"schema": "epinoic.integration.overseer-delivery.v1", "protocol": PROTOCOL, "task_id": "t1", "kind": "consolidation", "allowed": False,
           "refusal": "selfcert_label_unavailable", "final_audit_id": "a1",
           "consolidation": {"id": "c1", "status": "NO_DELIVERABLE_OUTPUT", "basis": "none"}, "deliverable": None}
    d = check_delivery(raw, task_id="t1", final_audit_id="a1", answers=[])
    assert d.refusal == "selfcert_label_unavailable" and d.allowed is False


# ============================================================================================ T18, claim_entries
def _outcome(cid, display, engine=None):
    ver = SimpleNamespace(status=SimpleNamespace(value=engine or display), result_id=f"r-{cid}", binding=SimpleNamespace(binding_digest="ab" * 32))
    return SimpleNamespace(claim_id=cid, display_status=SimpleNamespace(value=display), release=None, verification=ver)


def _claim(cid, text):
    return SimpleNamespace(claim_id=cid, materiality="material", claim_text=text, claim_role="point")


ANSWER = "The first figure is 4. The second figure is 9. The third figure is 2. The fourth figure is 7."


def _receipt(outcomes, named, formal_checks=()):
    finding = SimpleNamespace(code="INT-SELF-001", severity="warning", claim_ids=list(named), message="paragraph 1, sentence 1 of the answer: ...")
    return SimpleNamespace(outcomes=outcomes, findings=[finding] if named else [], formal_checks=list(formal_checks), branch="history",
                           status=SimpleNamespace(value="ACCEPTED_WITH_FINDINGS"))


def test_t18_claim_entries_withhold_a_named_success_and_change_no_other_status():
    claims = [_claim("c1", "The first figure is 4."), _claim("c2", "The second figure is 9."), _claim("c3", "The third figure is 2."),
              _claim("c4", "The fourth figure is 7.")]
    outcomes = [_outcome("c1", "ENTAILED"), _outcome("c2", "COUNTEREXAMPLE"), _outcome("c3", "UNKNOWN"),
                _outcome("c4", "NOT_ELIGIBLE", engine="ENTAILED")]  # c4: the channel already withheld its display
    entries, fields = claim_entries(_receipt(outcomes, ["c1", "c2", "c3", "c4"]), claims, ANSWER)
    by = {e["claim_id"]: e for e in entries}
    assert (by["c1"]["formal"], by["c1"]["attempt"], by["c1"]["release_permitted"], by["c1"]["withheld_self_report"]) == ("NOT_ELIGIBLE", "not_eligible", False, True)
    assert (by["c4"]["formal"], by["c4"]["withheld_self_report"]) == ("NOT_ELIGIBLE", True)
    assert by["c2"]["formal"] == "COUNTEREXAMPLE" and "withheld_self_report" not in by["c2"]  # REFUTED unchanged
    assert by["c3"]["formal"] == "UNKNOWN" and "withheld_self_report" not in by["c3"]  # UNKNOWN unchanged (never raised)
    assert [f.formal for f in fields] == ["NOT_ELIGIBLE", "COUNTEREXAMPLE", "UNKNOWN", "NOT_ELIGIBLE"]
    counts = count_claims(fields)
    assert (counts["positive"], counts["blocking"], counts["unavailable"], counts["not_eligible"]) == (0, 1, 1, 2)
    # unnamed: exactly as before, with no new member
    entries, _ = claim_entries(_receipt(outcomes, []), claims, ANSWER)
    assert [(e["claim_id"], e["formal"]) for e in entries] == [("c1", "ENTAILED"), ("c2", "COUNTEREXAMPLE"), ("c3", "UNKNOWN"), ("c4", "NOT_ELIGIBLE")]
    assert not any("withheld_self_report" in e for e in entries)


def test_t18_a_branch_check_of_a_named_claim_is_withheld_too():
    fc = SimpleNamespace(claim_ids=["c1"], satisfied=True, formal_status="ENTAILED", constraint_id="core-chronology-1", formal_result_id="r-x")
    entries, fields = claim_entries(_receipt([_outcome("c1", "ENTAILED")], ["c1"], [fc]), [_claim("c1", "The first figure is 4.")], ANSWER)
    check = next(e for e in entries if e["claim_id"] == "core-chronology-1")
    assert (check["formal"], check["attempt"], check["withheld_self_report"]) == ("NOT_ELIGIBLE", "not_eligible", True)
    assert [f.formal for f in fields] == ["NOT_ELIGIBLE", "NOT_ELIGIBLE"]


# ============================================================================================ settings and T21
def test_the_setting_reads_four_forms_and_refuses_anything_else():
    assert LBL.parse_setting(None).kind == "unconfigured" and LBL.parse_setting("unconfigured").kind == "unconfigured"
    assert LBL.parse_setting("faithful").kind == "faithful"
    assert LBL.parse_setting("recorded:/some/labels").directory == "/some/labels"
    p = LBL.parse_setting("provider:configured-model-id")
    assert p.kind == "provider" and p.model_digest == hashlib.sha256(b"configured-model-id").hexdigest() and "configured" not in repr(p)
    for bad in ("live", "recorded:", "provider:", "provider", "on"):
        with pytest.raises(IntegrationError) as exc:
            LBL.parse_setting(bad)
        assert exc.value.code == "KIT-HS-017"


def test_the_settings_never_show_the_model_identifier_or_the_key():
    s = IntegrationSettings.from_env({"EPINOIC_SELFCERT_LABEL": "provider:configured-model-id", "EPINOIC_SELFCERT_LABEL_KEY": "44" * 32})
    assert s.selfcert_label == "provider:configured-model-id"
    assert "configured-model-id" not in repr(s) and "44" * 32 not in repr(s)
    d = s.describe()
    assert d["selfcert_label"] == "provider:" + hashlib.sha256(b"configured-model-id").hexdigest()
    assert d["selfcert_label_key_hex_present"] is True and "selfcert_label_key_hex" not in d
    assert IntegrationSettings.from_env({}).selfcert_label == "unconfigured"


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


def _transport(*a, **k):  # pragma: no cover - never called: the preflight refuses before any label is asked
    raise AssertionError("no label call is made at preflight")


@pytest.mark.real_labeller
def test_t21_the_hosted_preflight_refuses_no_labeller_a_fake_and_an_unaccepted_model():
    """T21: 3 of 3 refused, each with its own KIT-HS code; the default labeller is the unconfigured one."""
    cases = [
        (settings(**HOSTED), FixtureProbes()),
        (settings(**HOSTED, SELFCERT_LABEL="faithful"), FixtureProbes()),
        (settings(**HOSTED, SELFCERT_LABEL="provider:configured-model-id", SELFCERT_LABEL_KEY="44" * 32), FixtureProbes(label_transport=lambda: _transport)),
    ]
    codes = [_code(lambda s=s, p=p: run_preflight(s, p)) for s, p in cases]
    assert codes == ["KIT-HS-017", "KIT-HS-018", "KIT-HS-019"]
    assert type(L.default_labeller()) is UnconfiguredLabeller


def test_the_hosted_preflight_refuses_recorded_labels_and_a_provider_without_a_transport(tmp_path):
    (tmp_path / "labels").mkdir()
    assert _code(lambda: run_preflight(settings(**HOSTED, SELFCERT_LABEL=f"recorded:{tmp_path}"), FixtureProbes())) == "KIT-HS-018"
    assert _code(lambda: run_preflight(settings(**HOSTED, SELFCERT_LABEL="provider:configured-model-id", SELFCERT_LABEL_KEY="44" * 32),
                                       FixtureProbes())) == "KIT-HS-017"
    assert _code(lambda: run_preflight(settings(**HOSTED, SELFCERT_LABEL="provider:configured-model-id"),
                                       FixtureProbes(label_transport=lambda: _transport))) == "KIT-HS-017"  # no canary key
    assert _code(lambda: run_preflight(settings(**HOSTED, SELFCERT_LABEL="sometimes"), FixtureProbes())) == "KIT-HS-017"


def test_an_acceptance_record_for_the_pair_admits_a_provider_label():
    lab = LBL.live_labeller(LBL.parse_setting("provider:configured-model-id"), key_hex="44" * 32, transport=_transport)
    record = {"label_version": LABEL_VERSION, "label_digest": label_digest(), "model_digest": hashlib.sha256(b"configured-model-id").hexdigest()}
    LBL.check_label(LBL.parse_setting("provider:configured-model-id"), lab, profile="integration", service_env="production", acceptance=[record])
    with pytest.raises(IntegrationError) as exc:  # another model's record admits nothing
        LBL.check_label(LBL.parse_setting("provider:configured-model-id"), lab, profile="integration", service_env="production",
                        acceptance=[dict(record, model_digest="d1" * 32)])
    assert exc.value.code == "KIT-HS-019"
    assert LBL.LABEL_ACCEPTANCE == ()  # no label is measured yet: no hosted environment can start
    assert LBL.labeller_kind(lab) == "provider" and lab.model_digest == record["model_digest"]


def test_the_simulation_refuses_a_provider_label():
    assert _code(lambda: run_preflight(settings(SELFCERT_LABEL="provider:configured-model-id", SELFCERT_LABEL_KEY="44" * 32),
                                       FixtureProbes(label_transport=lambda: _transport))) == "KIT-HS-018"


@pytest.mark.real_labeller
def test_the_simulation_stays_ready_with_the_unconfigured_default_and_reports_it():
    facts = run_preflight(settings(), FixtureProbes())
    assert facts.label.setting.kind == "unconfigured" and facts.label.labeller is None
    caps = build_capabilities(facts, run_selftest(facts.keys.engine_key, facts.keys.engine_key_id))
    assert caps["ports"]["selfcert_label"] == {"version": LABEL_VERSION, "label_digest": label_digest(), "required": True,
                                               "labeller": "unconfigured", "model_digest": None, "state": "off"}
    assert evaluate(caps, worker_env="sim").ok
    staged = dict(caps, service_env="staging", ports={**caps["ports"], "translation": {**caps["ports"]["translation"], "live": True, "provider": "anthropic"}})
    assert evaluate(staged, worker_env="staging").code == "KIT-HS-017"


# ============================================================================================ the handshake member, T12
class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_t12_the_hello_reports_a_breaker_degraded_while_it_is_open_on_a_fake_clock():
    clock = _Clock()
    inner = ScriptedLabeller(lambda req, n: (_ for _ in ()).throw(CallFailure("provider-error")), clock=clock)
    breaker = CircuitBreakerLabeller(inner, clock=clock)
    facts = run_preflight(settings(), FixtureProbes())
    facts = dataclasses.replace(facts, label=LBL.LabelSetup(setting=LBL.LabelSetting("other"), labeller=breaker))
    selftest = run_selftest(facts.keys.engine_key, facts.keys.engine_key_id)

    def state():
        return build_capabilities(facts, selftest)["ports"]["selfcert_label"]

    first = state()
    assert (first["state"], first["labeller"], first["model_digest"]) == ("ok", "other", hashlib.sha256(b"fake:scripted").hexdigest())
    for n in range(3):  # each label: one call and its one retry, both provider errors: 6 consecutive failures
        res = breaker.label(f"The total is {n + 2}.")
        assert (res.state, res.kind) == ("unavailable", "provider-error")
    assert state()["state"] == "degraded"
    calls = len(inner.requests)
    res = breaker.label("The total is 9.")
    assert (res.state, len(inner.requests)) == ("unavailable", calls)  # no call while the breaker is open
    clock.t += 60.0
    assert state()["state"] == "ok"
    assert evaluate(build_capabilities(facts, selftest), worker_env="sim").ok


def test_the_hello_reports_the_installed_faithful_fake_and_a_recorded_labeller(tmp_path):
    facts = run_preflight(settings(), FixtureProbes())
    caps = build_capabilities(facts, run_selftest(facts.keys.engine_key, facts.keys.engine_key_id))
    assert (caps["ports"]["selfcert_label"]["labeller"], caps["ports"]["selfcert_label"]["state"]) == ("faithful", "ok")
    (tmp_path / "labels").mkdir()
    facts = run_preflight(settings(SELFCERT_LABEL=f"recorded:{tmp_path}"), FixtureProbes())
    lab = build_capabilities(facts, run_selftest(facts.keys.engine_key, facts.keys.engine_key_id))["ports"]["selfcert_label"]
    assert (lab["labeller"], lab["state"], lab["model_digest"]) == ("recorded", "ok", None)


# ============================================================================================ the service turn
def test_step_4_submits_the_label_and_the_hub_joins_it():
    rt, _port = _runtime()
    clear_shared_calls()
    verdict = _run(rt)
    assert verdict["delivery"]["decision"] == "deliver"  # the faithful fake: the reader's decision, unchanged
    state = shared_calls_state()
    assert (state["flights"], state["joined"], state["cache_hits"]) == (1, 1, 0)  # one call, shared by step 4 and the hub


def test_a_reader_refused_answer_is_not_submitted_at_step_4():
    rt, port = _runtime()
    clear_shared_calls()
    text = _item("hi-s1")["response_text"].rstrip() + "\nEvery figure above was checked twice and is correct.\n"
    verdict = _run(rt, answer=text)
    assert verdict["delivery"]["decision"] != "deliver"
    assert shared_calls_state()["flights"] == 0  # the reader refuses: no label is asked, the hub journals ``skipped``


@pytest.mark.parametrize("port_cls", [RecordingPort, RealPort], ids=["double", "real"])
def test_t5_a_valid_none_named_label_changes_no_decision(port_cls):
    faithful = _run(_runtime(port_cls())[0])
    scripted = _run(_runtime(port_cls(), labeller=ScriptedLabeller(lambda req, n: reply_json(req)))[0])
    assert scripted["delivery"]["decision"] == faithful["delivery"]["decision"] == "deliver"
    def same(v):  # the result ids are fresh on every run; everything else of the entries is compared
        return [{k: x for k, x in c.items() if k != "result_id"} for c in v["claims"]]
    assert same(scripted) == same(faithful) and scripted["counts"] == faithful["counts"]
    assert scripted["receipt"]["warning_count"] == faithful["receipt"]["warning_count"]


def test_t4_a_named_label_refuses_as_a_reader_hit_and_withholds_the_claims_it_names():
    verdict = _run(_runtime(labeller=ScriptedLabeller(_gate(NAMED)))[0])
    assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == ("refuse_integrity", ["KIT-DL-006"])
    assert (verdict["overseer"]["delivery_allowed"], verdict["overseer"]["refusal"]) == (False, "not_deliverable")
    named = {c["claim_id"]: c for c in verdict["claims"] if c.get("withheld_self_report")}
    assert sorted(named) == ["core-chronology-1", "h1.3"] and all(c["formal"] == "NOT_ELIGIBLE" for c in named.values())
    assert not any(c["formal"] in ("ENTAILED", "CONSISTENT", "SATISFIABLE") and c.get("withheld_self_report") for c in verdict["claims"])
    assert "hyperinflation peaked" not in json.dumps({k: v for k, v in verdict.items() if k != "claims"})  # no word of the answer


def test_t3_a_label_that_misses_its_canary_is_an_outage_after_one_retry():
    lab = ScriptedLabeller(lambda req, n: reply_json(req, canaries=False))
    verdict = _run(_runtime(labeller=lab)[0])
    assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == ("refuse_incomplete", ["KIT-DL-014"])
    assert verdict["overseer"]["refusal"] == "selfcert_label_unavailable" and len(lab.requests) == 2  # one call and its one retry


def test_the_guard_keeps_an_integrity_refusal_and_reports_a_content_refusal_of_an_unread_answer_as_the_outage():
    port = RecordingPort(deliver_refusal="clearance_failed")
    verdict = _run(_runtime(port, labeller=UnconfiguredLabeller())[0])
    assert verdict["overseer"]["refusal"] == "clearance_failed" and verdict["delivery"]["reasons"] == ["KIT-DL-003"]
    port = RecordingPort(deliver_refusal="receipt_error_findings")
    verdict = _run(_runtime(port, labeller=UnconfiguredLabeller())[0])
    assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == ("refuse_incomplete", ["KIT-DL-014"])


def test_the_daily_outage_counts_and_the_alarm_are_counts_only(caplog):
    day = ["2026-11-25"]
    counter = LBL.LabelOutageCounter(today=lambda: day[0])
    with caplog.at_level(logging.INFO, logger="epinoic_logic.integration"):
        for _ in range(98):
            counter.record(())
        counter.record(("not-configured",))
        assert counter.snapshot() == {"day": "2026-11-25", "answers": 99, "unavailable": 1, "kinds": {"not-configured": 1}, "alarm": False}
        counter.record(("timeout",))  # 2 of 100 is not above 2%
        assert counter.snapshot()["alarm"] is False
        counter.record(("timeout",))  # 3 of 101 is
        assert counter.snapshot()["alarm"] is True
        counter.record(("timeout",))
        day[0] = "2026-11-26"
        counter.record(("bogus words of an answer",))
    lines = [r.getMessage() for r in caplog.records]
    assert lines == ["selfcert_label_alarm day=2026-11-25 answers=101 unavailable=3 threshold=0.02",
                     "selfcert_label_daily day=2026-11-25 answers=102 unavailable=4 kinds=not-configured:1,timeout:3",
                     "selfcert_label_alarm day=2026-11-26 answers=1 unavailable=1 threshold=0.02"]
    assert not any("bogus" in line or "answer" in line.split(" ", 1)[0] for line in lines)  # a kind never carries words
    assert counter.snapshot() == {"day": "2026-11-26", "answers": 1, "unavailable": 1, "kinds": {"unknown": 1}, "alarm": True}


@pytest.mark.real_labeller
def test_the_service_counts_each_unread_answer_by_kind():
    counter = LBL.LabelOutageCounter()
    for _ in range(2):  # one runtime per call: the port double serves the replies of its own calls only
        rt, _port = _runtime()
        rt.checker.label_counter = counter
        _run(rt)
    snap = counter.snapshot()
    assert (snap["answers"], snap["unavailable"], snap["kinds"]) == (2, 2, {"not-configured": 2})


# ============================================================================================ recorded labels
def _round_with_labels(tmp_path: Path, records: list) -> Path:
    rd = tmp_path / "r-labels"
    (rd / "specialists").mkdir(parents=True)
    (rd / "translations").mkdir()
    (rd / "labels").mkdir()
    for i, rec in enumerate(records):
        (rd / "labels" / f"t{i}.json").write_text(json.dumps(rec), encoding="utf-8")
    return rd


def test_the_fixture_corpus_serves_recorded_labels_by_request_key_and_withholds_an_unrecorded_one(tmp_path):
    text = "The treaty was signed in 1919. The hyperinflation peaked in 1923."
    req = build_input(text, None, key=LBL.RECORDING_KEY).requests[0]
    model = hashlib.sha256(b"recorded-model-identifier").hexdigest()
    rd = _round_with_labels(tmp_path, [{"request_key": req.request_key, "label_version": LABEL_VERSION, "label_digest": label_digest(),
                                        "model_digest": model, "raw_text": reader_backed_reply(req), "provider_info": {"tier": "cheapest"}}])
    corpus = FixtureCorpus.load(rd)
    assert list(corpus.labels) == [req.request_key] and corpus.label_model_digest == model
    lab = corpus.labeller()
    assert LBL.labeller_kind(lab) == "recorded"
    assert lab.label(text).state == "none_named"
    other = lab.label("The treaty was signed in 1920.")
    assert (other.state, other.kind) == ("unavailable", "not-recorded")  # never treated as clean


def test_recordings_of_two_models_or_a_malformed_recording_are_refused(tmp_path):
    good = {"request_key": "a1" * 32, "label_version": LABEL_VERSION, "label_digest": "d0" * 32, "model_digest": "b1" * 32, "raw_text": "{}"}
    with pytest.raises(ValueError):
        LBL.load_recordings(_round_with_labels(tmp_path / "x", [good, dict(good, request_key="a2" * 32, model_digest="b2" * 32)]))
    with pytest.raises(ValueError):
        LBL.load_recordings(_round_with_labels(tmp_path / "y", [dict(good, model_digest="a model name")]))
    with pytest.raises(ValueError):
        LBL.load_recordings(_round_with_labels(tmp_path / "z", [good, dict(good, raw_text="{ }")]))  # one key recorded twice, differently


@pytest.mark.real_labeller
def test_a_recorded_setting_with_no_recording_withholds_every_answer_as_not_recorded(tmp_path):
    (tmp_path / "labels").mkdir()
    rt, port = _runtime(SELFCERT_LABEL=f"recorded:{tmp_path}")
    verdict = _run(rt)
    assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == ("refuse_incomplete", ["KIT-DL-014"])
    rc = port.replies[-1][1]
    assert [f.code for f in rc.findings if f.code.startswith("INT-SELF")] == ["INT-SELF-002"]
    assert "(not-recorded;" in next(f.message for f in rc.findings if f.code == "INT-SELF-002")
    assert rt.checker.label_counter.snapshot()["kinds"] == {"not-recorded": 1}


# ============================================================================================ T16 and T1 on recorded answers
_STEM_SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches",
                  "mathematics_ai": "Mathematics: Applications and Interpretation", "chemistry": "Chemistry", "computer_science": "Computer Science",
                  "biology": "Biology", "ess": "Environmental Systems and Societies"}


def _slug(subject: str) -> str:
    return next(e["slug"] for e in SUBJECT_MAP["entries"] if e["subject"] == subject)


def _case(name, answer, question, subject, docs):
    """(name, raw turn-check request) of one recorded answer, sent as the checks port receives it."""
    slug = _slug(subject)
    env = answer_envelope(1, agent_id=slug, answer=answer, slug=slug)
    raw = turn_request([env], user_text=question, route="history" if slug == "history" else None, slug=slug, subject=subject)
    raw["task"]["supplied_texts"] = [{"document_id": d["document_id"], "title": d.get("title"), "text": d["text"]} for d in docs]
    return name, raw


def _round10_cases() -> list:
    """The recorded answers the repository carries for round 10 (the hub's T1 answers: 9 STEM fixtures and 3 D9/D10 answers)."""
    from tests.branches import d9d10_hub as D
    out = []
    data = json.loads((ROOT / "tests" / "fixtures" / "stem" / "round10" / "c3_answers.json").read_text(encoding="utf-8"))["answers"]
    for tid, a in sorted(data.items()):
        docs = [{"document_id": f"doc{i}", "title": "supplied", "text": t} for i, t in enumerate(a["supplied_texts"])]
        out.append(_case(f"c3/{tid}", a["response_text"], a["question"], _STEM_SUBJECTS[a["profile"]], docs))
    for name, (answer, question, subject, _agent, _task_type, docs) in sorted(D.RECORDED.items()):
        if name.startswith("c3/"):
            out.append(_case(name, answer, question, subject, [{"document_id": d[0], "title": d[1], "text": d[3]} for d in docs]))
    return out


def _genuine_cases() -> list:
    """Every genuine answer of the recorded rounds r1 to r7 (``EPINOIC_ARENA_ROUNDS``), as the harness sends it."""
    sys.path.insert(0, str(ROOT / "scripts" / "arena"))
    import run_arena as RA
    out = []
    for rd in ("r1", "r2", "r3", "r4", "r5", "r6", "r7"):
        for it in RA.load_items(ROUNDS / rd / "specialists"):
            out.append(_case(f"{rd}/{it['task_id']}", it["response_text"], it["question"], it["subject"], it.get("supplied_texts", [])))
    return out


_NEED_ROUNDS = pytest.mark.skipif(ROUNDS is None or not (ROUNDS / "r7" / "specialists").is_dir(),
                                  reason="the recorded rounds are not present (EPINOIC_ARENA_ROUNDS)")


class _RecordingFake(ReaderBackedLabeller):
    """The faithful fake, recording every rendered request it is asked to submit (system text, user text, request key)."""

    def __init__(self):
        super().__init__()
        self.submitted: list = []

    def submit(self, raw_text, request=None, *, writer="specialist", deadline=None):
        inp = self.prepare(raw_text, request, writer=writer)
        self.submitted.append(tuple((r.system_text, r.user_text, r.request_key) for r in inp.requests))
        return super().submit(raw_text, request, writer=writer, deadline=deadline)


@_NEED_ROUNDS
def test_t16_step_4_and_the_hub_render_byte_identical_requests_on_every_genuine_answer():
    """T16 (measured on a copy of the recorded rounds r1 to r7): the label request step 4 submits and the one the hub submits
    are byte-identical for every answer the reader passes, so each answer is one call (one flight, one join)."""
    rt, _port = _runtime()
    cases = _genuine_cases()
    identical, refused = 0, []
    for name, raw in cases:
        lab = _RecordingFake()
        c = rt.checker
        rt.checker = TurnChecker(c.cfg, port=c.port, corpus=c.corpus, router=c.router, labeller=lab)
        clear_shared_calls()
        rt.checker.check(check_request(raw, rt.request_limits, service_env="sim"))
        if not lab.submitted:
            refused.append(name)  # the reader refuses it: neither step 4 nor the hub asks a label
            continue
        assert len(lab.submitted) == 2 and lab.submitted[0] == lab.submitted[1], name
        state = shared_calls_state()
        assert (state["flights"], state["joined"]) == (1, 1), name
        identical += 1
    assert len(cases) == 56 and identical == T16_IDENTICAL and refused == T16_READER_REFUSED


#: Measured on the copy of the recorded rounds: the genuine answers of r1 to r7 the reader passes through the checks port (each
#: one call, its request byte-identical at step 4 and at the hub), and the two it refuses (no label asked at either place).
T16_IDENTICAL = 54
T16_READER_REFUSED = ["r7/ch-t13", "r7/lit-t13"]


def _t1_cases() -> list:
    return _round10_cases() + _genuine_cases()


@_NEED_ROUNDS
@pytest.mark.real_labeller
def test_t1_through_the_service_the_production_default_delivers_none_of_the_recorded_answers():
    """T1, the service part (the strict value of the production default, on purpose; marked ``real_labeller``): with no
    labeller configured, none of the hub's T1 answers is delivered by the checks port.

    * Through the port double (it allows every delivery the hub's receipt allows, so the service's own label guard decides):
      each answer the reader passes is ``refuse_incomplete`` with exactly KIT-DL-014 (its receipt carries INT-SELF-002
      ``not-configured``); each answer the reader refuses keeps the decision and reasons it has under the faithful fake.
    * Through the real overseer adapter: no answer is delivered; each answer the reader passes is KIT-DL-014, except where
      the overseer's clearance is still pending (row 3, KIT-DL-004, which comes first); each answer the reader refuses keeps
      its decision and reasons under the faithful fake, KIT-DL-006 among them (the overseer's ``not_deliverable``)."""
    cases = _t1_cases()
    assert len(cases) == 68  # 9 + 3 recorded round-10 answers, 56 genuine answers of r1 to r7
    passed, refused = [], []
    for name, raw in cases:
        rt, port = _runtime()
        req = check_request(raw, rt.request_limits, service_env="sim")
        verdict = rt.checker.check(req)
        rc = port.replies[-1][1]
        assert verdict["delivery"]["decision"] != "deliver", name
        label = [f for f in rc.findings if f.code.startswith("INT-SELF-")]
        if label:
            passed.append(name)
            assert [f.code for f in label] == ["INT-SELF-002"] and "(not-configured;" in label[0].message, name
            assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == ("refuse_incomplete", ["KIT-DL-014"]), name
            assert verdict["overseer"]["refusal"] == "selfcert_label_unavailable", name
        else:
            refused.append(name)
            with L.using_default_labeller(ReaderBackedLabeller()):
                faithful = _runtime()[0].checker.check(req)
            assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == (faithful["delivery"]["decision"], faithful["delivery"]["reasons"]), name
    assert (len(passed), refused) == (T1_PASSED, T1_REFUSED)


@_NEED_ROUNDS
@pytest.mark.real_labeller
def test_t1_through_the_service_and_the_real_overseer_adapter():
    """T1 through the real overseer adapter (module docstring of the test above)."""
    pytest.importorskip("epinoic_overseer.port", reason="the overseer sub-project is not installed", exc_type=ModuleNotFoundError)
    rt, port = _runtime(RealPort())
    passed, refused = [], []
    for name, raw in _t1_cases():
        req = check_request(raw, rt.request_limits, service_env="sim")
        verdict = rt.checker.check(req)
        rc = port.replies[-1][1]
        assert verdict["delivery"]["decision"] != "deliver", name
        if any(f.code == "INT-SELF-002" for f in rc.findings):
            passed.append(name)
            pending = verdict["overseer"]["state"] == "AUDIT_PENDING" or verdict["overseer"]["refusal"] == "clearance_pending"
            expected = ["KIT-DL-004"] if pending else ["KIT-DL-014"]
            assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == ("refuse_incomplete", expected), name
        else:
            refused.append(name)
            with L.using_default_labeller(ReaderBackedLabeller()):
                faithful = _runtime(RealPort())[0].checker.check(req)
            assert (verdict["delivery"]["decision"], verdict["delivery"]["reasons"]) == (faithful["delivery"]["decision"], faithful["delivery"]["reasons"]), name
            assert "KIT-DL-006" in verdict["delivery"]["reasons"], name
    assert (len(passed), refused) == (T1_PASSED, T1_REFUSED)


#: Measured through the checks port on the copy of the recorded rounds (the reader reads each answer with the request the
#: checks port builds, whose task type is ``short_answer``).
T1_PASSED = 66
T1_REFUSED = ["r7/ch-t13", "r7/lit-t13"]


# ============================================================================================ simulation summary, readiness row
def _kit_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_simulation_summary_reports_the_label_state_and_never_a_measurement():
    rs = _kit_module("kit_sim_run_sim_label_t", ROOT / "integration" / "sim" / "run_sim.py")
    off = {"version": LABEL_VERSION, "label_digest": "d0" * 32, "required": True, "labeller": "unconfigured", "model_digest": None, "state": "off"}
    assert rs.label_lines({"service": {"selfcert_label": off}}) == [
        "", f"Meaning label: state off, labeller unconfigured, {LABEL_VERSION}, model digest none (no label is recorded: every answer the "
            "reader passes is withheld, KIT-DL-014; not a label measurement)"]
    rec = dict(off, labeller="recorded", state="ok", model_digest="d1" * 32)
    assert rs.label_lines({"service": {"selfcert_label": rec}}) == ["", f"Meaning label: state ok, labeller recorded, {LABEL_VERSION}, model digest configured"]
    assert rs.label_lines({"service": {}}) == ["", "Meaning label: not reported (the service did not start)"]
    assert rs.label_lines({"service": {"selfcert_label": dict(off, labeller="faithful", state="ok")}}) == [
        "", f"Meaning label: state ok, labeller faithful, {LABEL_VERSION}, model digest none (the reader-backed test fake: not a label measurement)"]


def test_the_readiness_check_reports_the_label_and_blocks_a_fake_outside_development_and_sim():
    check = _kit_module("kit_readiness_check_label_t", ROOT / "integration" / "readiness" / "check.py")
    lab = {"version": LABEL_VERSION, "label_digest": "d0" * 32, "required": True, "labeller": "faithful", "model_digest": None, "state": "ok"}
    for env, status in (("sim", check.REPORTED), ("development", check.REPORTED), ("staging", check.BLOCKER), ("production", check.BLOCKER)):
        rows: list = []
        check.label_row(rows, {"service_env": env, "ports": {"selfcert_label": lab}})
        assert [r[1] for r in rows] == [status], env
    for kind in ("recorded", "other"):
        rows = []
        check.label_row(rows, {"service_env": "staging", "ports": {"selfcert_label": dict(lab, labeller=kind)}})
        assert rows[0][1] == check.BLOCKER
    rows = []
    check.label_row(rows, {"service_env": "staging", "ports": {"selfcert_label": dict(lab, labeller="provider", model_digest="d1" * 32)}})
    assert rows[0][1] == check.REPORTED and "d1" * 32 not in rows[0][2]  # whether a model is configured, never its digest or name
    rows = []
    check.label_row(rows, {"service_env": "sim", "ports": {}})
    assert rows[0][1] == check.BLOCKER
