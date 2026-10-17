"""The checks port's processing of one call (PROTOCOL.md section 5.2): the TurnChecker on the synthetic corpus, through
the real hub, the real branch parsers, the real fixture translations, the real engine and the real STEM front end.

The overseer is reached through ``RecordingPort``, the TEST DOUBLE of the overseer port (tests/integration/helpers.py):
the real embedded adapter is connected in phase 2, which runs these tests against it as well. What these tests show is
the TurnChecker's own contract: its normative order, its budget, that every refusal names its first failing condition,
that a non-success is never shown as success, and that the review routing never changes a decision.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import time
from pathlib import Path

import pytest

from epinoic_logic.integration.checks_port import check_request
from epinoic_logic.integration.delivery import BindingContext, binding_problem, verify_verdict_signature
from epinoic_logic.integration.evidence_tap import EvidenceTap
from epinoic_logic.integration.protocol import POSITIVE, SCOPE_STATEMENT, AUDIT_SCOPE_STATEMENT
from epinoic_logic.integration.runtime import build_runtime
from epinoic_logic.integration.turn import TurnChecker
from epinoic_logic.integration.verifier import FixtureCorpus
from tests.integration.helpers import (
    VERDICT_KEY_HEX, FixtureProbes, RecordingPort, answer_envelope, hello, settings, turn_request, write_router_module,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "integration" / "sim" / "corpus" / "synthetic" / "s1"
ROUTES = {"History": ("history", "history"), "Physics": (None, "physics"), "English A: Literature": ("english", "english-a-literature")}


def _item(name: str) -> dict:
    return json.loads((CORPUS / "specialists" / f"{name}.json").read_text(encoding="utf-8"))


def _checker(port=None, *, corpus_dir=CORPUS, clock=None, **env):
    port = port or RecordingPort()
    rt = build_runtime(settings(FIXTURE_DIR=str(corpus_dir), **env), probes=FixtureProbes(port))
    if clock is not None:
        c = rt.checker
        rt.checker = TurnChecker(c.cfg, port=c.port, corpus=c.corpus, router=c.router, evidence_tap=c.tap, clock=clock)
    return rt, port


def _request(rt, names, *, mode="single", answers=None, policy="verified-v1", budget_ms=30000):
    first = _item(names[0])
    route, slug = ROUTES[first["subject"]]
    if mode == "duplicate":
        agent_ids = [f"{slug}@a", f"{slug}@b"]
    else:
        agent_ids = [slug]
    texts = answers if answers is not None else [_item(n)["response_text"] for n in names]
    envs = [answer_envelope(1, agent_id=a, answer=t, slug=slug) for a, t in zip(agent_ids, texts)]
    raw = turn_request(envs, mode=mode, user_text=first["question"], policy=policy, budget_ms=budget_ms, route=route, slug=slug, subject=first["subject"])
    return check_request(raw, rt.request_limits, service_env="sim"), envs


def _ctx(req, envs, verdict, texts):
    release = None
    if verdict["delivery"]["decision"] == "deliver":
        chosen = verdict["delivery"]["deliverable"]["agent_id"]
        release = next(t for e, t in zip(envs, texts) if e["agent_id"] == chosen)
    return BindingContext(task_id=req.ids.task_id, request_id=req.ids.request_id, user_text=req.task.user_text, policy=req.policy, mode=req.mode,
                          answers=[(e["agent_id"], t, e["result_sha256"]) for e, t in zip(envs, texts)], release_text=release)


def _run(names, *, port=None, mode="single", answers=None, clock=None, corpus_dir=CORPUS, policy="verified-v1", **env):
    rt, port = _checker(port, clock=clock, corpus_dir=corpus_dir, **env)
    req, envs = _request(rt, names, mode=mode, answers=answers, policy=policy)
    verdict = rt.checker.check(req)
    texts = answers if answers is not None else [_item(n)["response_text"] for n in names]
    assert verify_verdict_signature(verdict, bytes.fromhex(VERDICT_KEY_HEX))
    assert binding_problem(verdict, _ctx(req, envs, verdict, texts)) is None, "the Worker re-derives the same decision from the verdict"
    assert verdict["scope_statement"] == SCOPE_STATEMENT and verdict["audit_scope_statement"] == AUDIT_SCOPE_STATEMENT
    return verdict, port


def _claims(verdict) -> dict:
    return {c["claim_id"]: c for c in verdict["claims"]}


def _never_shown_as_success(verdict) -> None:
    for c in verdict["claims"]:
        if c["formal"] not in POSITIVE:
            assert not c["release_permitted"], c
    if verdict["summary"] == "formally_checked":
        assert verdict["counts"]["unavailable"] == 0 and verdict["counts"]["permitted"] == verdict["counts"]["eligible"]


# ----------------------------------------------------------------------------------------------- single mode


def test_single_clean_answer_is_delivered_with_the_formal_results_of_its_encoding_only():
    verdict, port = _run(["hi-s1"])
    assert verdict["delivery"]["decision"] == "deliver" and verdict["delivery"]["reasons"] == []
    assert verdict["summary"] == "formal_only"  # positive results, but no semantic-fidelity review permits release
    claims = _claims(verdict)
    assert claims["h1.1"]["formal"] == "ENTAILED" and claims["h1.1"]["materiality"] == "material" and claims["h1.1"]["source"] == "translation"
    assert claims["h1.1"]["excerpt"] in _item("hi-s1")["response_text"] and not claims["h1.1"]["release_permitted"]
    assert claims["h1.2"]["formal"] == "NOT_ELIGIBLE" and claims["h1.4"]["formal"] == "NOT_ELIGIBLE"
    assert verdict["receipt"]["status"] == "ACCEPTED" and verdict["receipt"]["branch"] == "history"
    assert port.calls == ["new_hub", "clearance", "clearance", "close", "deliver"]  # dispatch clearance, response clearance, FINAL, delivery
    assert verdict["overseer"]["review"] == {"queued": False, "plan_origin": None, "plan_refusal": None, "router": None}
    _never_shown_as_success(verdict)


def test_an_error_level_receipt_finding_refuses_unresolved():
    verdict, _ = _run(["hi-s2"])
    assert verdict["delivery"]["decision"] == "refuse_unresolved" and verdict["delivery"]["reasons"] == ["KIT-DL-002"]
    assert "INT-CONFLICT-005" in verdict["receipt"]["error_codes"] and verdict["summary"] is None
    assert verdict["delivery"]["deliverable"] is None
    assert _claims(verdict)["h1.3"]["formal"] == "COUNTEREXAMPLE"
    _never_shown_as_success(verdict)


def test_a_rejected_answer_is_an_integrity_refusal():
    verdict, port = _run(["hi-s1"], answers=[" "])
    assert verdict["receipt"]["status"] == "REJECTED"
    assert verdict["delivery"]["decision"] == "refuse_integrity" and "KIT-DL-001" in verdict["delivery"]["reasons"]
    assert "deliver" in port.calls and port.calls.count("clearance") == 1  # a REJECTED response is not cleared for acting


def test_the_stem_check_holds_on_a_correct_step_and_refutes_a_wrong_one():
    good, _ = _run(["ph-s1"])
    assert good["delivery"]["decision"] == "deliver" and good["receipt"]["branch"] == "sciences"
    stem = [c for c in good["claims"] if c["source"] == "stem"]
    assert stem and all(c["formal"] == "ENTAILED" for c in stem)
    bad, _ = _run(["ph-s2"])
    assert bad["delivery"]["decision"] == "refuse_unresolved" and "INT-SUBJ-001" in bad["receipt"]["error_codes"]
    assert any(c["source"] == "stem" and c["formal"] == "COUNTEREXAMPLE" for c in bad["claims"])


def test_an_english_interpretive_answer_labels_its_interpretations_not_eligible():
    verdict, _ = _run(["en-s1"])
    claims = _claims(verdict)
    assert claims["p1-s02"]["formal"] == "NOT_ELIGIBLE" and claims["p1-s03"]["formal"] == "NOT_ELIGIBLE"
    assert claims["p1-point"]["formal"] == "ENTAILED" and not claims["p1-point"]["release_permitted"]
    _never_shown_as_success(verdict)


def test_an_answer_without_translations_is_never_shown_as_checked():
    text = "The Treaty of Versailles (1919) imposed reparations and territorial losses on Germany.\nHistorians still debate how far it, rather than the 1923 hyperinflation, explains later instability."
    verdict, _ = _run(["hi-s1"], answers=[text])
    assert verdict["delivery"]["decision"] == "refuse_incomplete" and "KIT-DL-011" in verdict["delivery"]["reasons"]
    skipped = [c for c in verdict["claims"] if c["formal"] == "NOT_ATTEMPTED"]
    assert skipped and all(c["attempt"] == "provider_unavailable" for c in skipped)
    _never_shown_as_success(verdict)


def test_a_provider_failure_is_internal_error_and_refuses_incomplete(tmp_path):
    corpus = tmp_path / "s1"
    (corpus / "specialists").mkdir(parents=True)
    (corpus / "translations").mkdir()
    (corpus / "specialists" / "hi-s1.json").write_text((CORPUS / "specialists" / "hi-s1.json").read_text(encoding="utf-8"), encoding="utf-8")
    tr = json.loads((CORPUS / "translations" / "hi-s1.json").read_text(encoding="utf-8"))
    tr["claim_text_sha256"]["h1.1"] = "0" * 64  # a stale fixture: the provider refuses it, the pipeline records TRANSLATION_FAILED
    (corpus / "translations" / "hi-s1.json").write_text(json.dumps(tr), encoding="utf-8")
    verdict, _ = _run(["hi-s1"], corpus_dir=corpus)
    assert _claims(verdict)["h1.1"]["formal"] == "INTERNAL_ERROR"
    assert verdict["delivery"]["decision"] == "refuse_incomplete" and verdict["delivery"]["reasons"] == ["KIT-DL-011"]
    _never_shown_as_success(verdict)


# ----------------------------------------------------------------------------------------------- budget


class FlippingClock:
    """A monotonic clock that jumps past every deadline once ``flip()`` is called."""

    def __init__(self) -> None:
        self.offset = 0.0

    def __call__(self) -> float:
        return time.monotonic() + self.offset

    def flip(self) -> None:
        self.offset = 10_000.0


def test_the_budget_spent_before_the_checks_leaves_every_eligible_claim_not_attempted():
    clock = FlippingClock()
    port = RecordingPort()
    original = port.new_hub

    def new_hub(**kw):
        hub = original(**kw)
        clock.flip()  # the budget is spent once the hub exists: every claim the verifier sees is past the deadline
        return hub
    port.new_hub = new_hub
    verdict, _ = _run(["hi-s1"], port=port, clock=clock)
    assert verdict["delivery"]["decision"] == "refuse_incomplete" and verdict["delivery"]["reasons"] == ["KIT-DL-011", "KIT-DL-013"]
    claims = _claims(verdict)
    assert claims["h1.1"]["formal"] == "NOT_ATTEMPTED" and claims["h1.1"]["attempt"] == "skipped_budget"
    _never_shown_as_success(verdict)


def test_the_budget_spent_half_way_skips_the_rest(tmp_path):
    clock = FlippingClock()

    class HalfCorpus(FixtureCorpus):
        def verifier_for(self, *a, **kw):
            fn, provider = super().verifier_for(*a, **kw)
            if fn is None:
                return fn, provider

            def once(claim, report):
                out = fn(claim, report)
                clock.flip()  # the first claim is verified, then the budget is spent
                return out
            return once, provider

    rt, port = _checker(clock=clock)
    rt.checker = TurnChecker(rt.checker.cfg, port=rt.checker.port, corpus=HalfCorpus.load(CORPUS), router=rt.checker.router, clock=clock)
    req, envs = _request(rt, ["hi-s1"])
    verdict = rt.checker.check(req)
    statuses = {c["claim_id"]: (c["formal"], c["attempt"]) for c in verdict["claims"] if c["source"] == "translation"}
    attempted = [k for k, (f, a) in statuses.items() if a == "attempted"]
    skipped = [k for k, (f, a) in statuses.items() if a == "skipped_budget"]
    assert len(attempted) == 1 and skipped, statuses
    assert all(statuses[k][0] == "NOT_ATTEMPTED" for k in skipped)
    material_skipped = any(_claims(verdict)[k]["materiality"] == "material" for k in skipped)
    if material_skipped:
        assert verdict["delivery"]["decision"] == "refuse_incomplete" and "KIT-DL-013" in verdict["delivery"]["reasons"]
    else:  # only a supporting claim was skipped: it does not make the material checks incomplete, but it is labelled so
        assert verdict["delivery"]["decision"] == "deliver" and verdict["summary"] != "formally_checked"
    _never_shown_as_success(verdict)


def test_a_stem_report_cut_by_its_budget_is_stem_budget_and_refuses_incomplete():
    clock = FlippingClock()
    port = RecordingPort()
    original = port.clearance

    def clearance(hub, task_id, message_id, receipt, *, wait_ms):
        out = original(hub, task_id, message_id, receipt, wait_ms=wait_ms)
        if receipt.direction == "router_to_specialist":
            clock.flip()  # spent after the dispatch: the STEM checks of the response get no budget
        return out
    port.clearance = clearance
    verdict, _ = _run(["ph-s1"], port=port, clock=clock)
    stem = [c for c in verdict["claims"] if c["source"] == "stem"]
    assert stem and all(c["formal"] == "NOT_ATTEMPTED" and c["attempt"] == "stem_budget" for c in stem)
    assert verdict["delivery"]["decision"] == "refuse_incomplete" and "KIT-DL-013" in verdict["delivery"]["reasons"]


# ----------------------------------------------------------------------------------------------- the overseer's decisions


@pytest.mark.parametrize("kw,decision,reasons", [
    ({"clearance_state": "AUDIT_PENDING"}, "refuse_incomplete", ["KIT-DL-004"]),
    ({"clearance_state": "AUDIT_FAILED"}, "refuse_integrity", ["KIT-DL-003"]),
    ({"final_state": "AUDIT_FAILED", "final_codes": ["OVS-FID-003"], "deliver_refusal": "final_audit_not_passed"}, "refuse_integrity", ["KIT-DL-005"]),
    ({"deliver_refusal": "custody_failed"}, "refuse_integrity", ["KIT-DL-006"]),
    ({"deliver_refusal": "signature_invalid"}, "refuse_integrity", ["KIT-DL-006"]),
])
def test_every_overseer_refusal_names_its_first_failing_condition(kw, decision, reasons):
    verdict, port = _run(["hi-s1"], port=RecordingPort(**kw))
    assert verdict["delivery"]["decision"] == decision and verdict["delivery"]["reasons"] == reasons
    assert verdict["delivery"]["deliverable"] is None and verdict["summary"] is None
    assert "close" in port.calls  # the FINAL audit seals the journal on every path


def test_an_out_of_contract_overseer_message_is_never_acted_on():
    class AgentCodePort(RecordingPort):
        def clearance(self, hub, task_id, message_id, receipt, *, wait_ms):
            msg = super().clearance(hub, task_id, message_id, receipt, wait_ms=wait_ms)
            return dict(msg, error_codes=["OVS-AGENT-001"])  # an agent code never affects a clearance (KIT-OP-008)
    verdict, _ = _run(["hi-s1"], port=AgentCodePort())
    assert verdict["delivery"]["decision"] == "refuse_incomplete" and verdict["delivery"]["reasons"] == ["KIT-DL-900"]


@pytest.mark.parametrize("op", ["new_hub", "clearance", "close", "deliver"])
def test_an_unexpected_exception_yields_a_signed_internal_error_verdict(op):
    verdict, _ = _run(["hi-s1"], port=RecordingPort(fail_on=op))
    assert verdict["delivery"] == {"decision": "refuse_incomplete", "deliverable": None, "reasons": ["KIT-DL-900"], "consolidation": None, "synthesis": None}
    assert verdict["overseer"]["refusal"] == "internal_error" and verdict["claims"] == [] and verdict["summary"] is None


# ----------------------------------------------------------------------------------------------- duplicate mode


def test_duplicate_mode_with_identical_answers_delivers_the_representative():
    verdict, port = _run(["hi-s1", "hi-s1"], mode="duplicate")
    assert verdict["delivery"]["decision"] == "deliver" and verdict["delivery"]["deliverable"]["agent_id"] == "history@a"
    assert [a["agent_id"] for a in verdict["bound"]["answers"]] == ["history@a", "history@b"]
    assert port.calls == ["new_hub", "clearance", "clearance", "clearance", "clearance", "close", "deliver"]
    assert verdict["delivery"]["consolidation"]["basis"] == "identical_text"


def test_duplicate_mode_with_conflicting_answers_refuses_unresolved():
    verdict, _ = _run(["hi-s1", "hi-s3"], mode="duplicate", port=RecordingPort(deliver_refusal="consolidation_conflicting"))
    assert verdict["delivery"]["decision"] == "refuse_unresolved" and verdict["delivery"]["reasons"] == ["KIT-DL-007"]
    assert verdict["delivery"]["consolidation"]["status"] == "CONFLICTING"


def test_duplicate_mode_delivers_the_answer_the_overseer_chose():
    verdict, _ = _run(["hi-s1", "hi-s3"], mode="duplicate", port=RecordingPort(representative=1))
    assert verdict["delivery"]["deliverable"]["agent_id"] == "history@b"
    assert all(c["excerpt"] in _item("hi-s3")["response_text"] for c in verdict["claims"])


def test_combined_mode_is_not_offered_before_a_combinator_is_connected():
    rt, _ = _checker()
    assert "combined" not in rt.request_limits.modes
    assert rt.capabilities()["ports"]["combinator"]["available"] is False


# ----------------------------------------------------------------------------------------------- review routing


def test_the_review_runs_the_floor_plan_when_no_router_is_attached():
    port = RecordingPort(hello_message=hello(agents="async"))
    verdict, _ = _run(["hi-s2"], port=port, OVERSEER_AGENTS="async")
    assert verdict["overseer"]["review"] == {"queued": True, "plan_origin": "floor", "plan_refusal": None, "router": None}
    [admission] = port.reviewed
    assert admission.origin == "floor" and admission.effective.transfers[0].method == "DUPLICATE"  # error findings escalate to 2 reviews
    assert port.calls[-2:] == ["repeats", "review"]


def test_a_below_floor_router_plan_is_refused_by_name_and_the_floor_runs(tmp_path, monkeypatch):
    body = ("    req = json.loads(request_json)\n"
            "    ts = [{'transfer_key': o['transfer_key'], 'method': 'IN_DEPTH', 'reviews': 1, 'parts': 1, 'instances': 1, 'profile': 'standard',\n"
            "           'tier': 'cheapest', 'sources': [], 'context': None, 'reasons': ['cost_cheapest'], 'features_used': ['size'],\n"
            "           'estimated_cost': {'tokens': 1000, 'seconds': 10}} for o in req['outputs']]\n"
            "    digest = hashlib.sha256(json.dumps(req, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()\n"
            "    return json.dumps({'schema': 'epinoic.integration.routing-plan.v1', 'protocol': 'epinoic.integration.v1', 'port_version': '1.0',\n"
            "                       'origin': 'router', 'plan_id': 'plan-cheap', 'ids': req['ids'], 'request_sha256': digest, 'router': IDENTITY,\n"
            "                       'transfers': ts, 'totals': {'instances': len(ts), 'estimated_cost': {'tokens': 1000 * len(ts), 'seconds': 10 * len(ts)}}})\n")
    name = write_router_module(tmp_path, monkeypatch, "cheap_router_for_turns", plan_body=body)
    port = RecordingPort(hello_message=hello(agents="async"))
    verdict, _ = _run(["hi-s2"], port=port, OVERSEER_AGENTS="async", FLASH_ROUTER=name)
    review = verdict["overseer"]["review"]
    assert review["plan_origin"] == "floor" and review["plan_refusal"] == "KIT-RT-020" and review["router"]["name"] == "test-flash-router"
    assert port.reviewed[0].effective.transfers[0].reviews >= 2


def test_a_router_plan_at_the_floor_is_admitted_and_the_review_never_changes_the_decision(tmp_path, monkeypatch):
    name = write_router_module(tmp_path, monkeypatch, "floor_router_for_turns")
    with_review, port = _run(["hi-s1"], port=RecordingPort(hello_message=hello(agents="async")), OVERSEER_AGENTS="async", FLASH_ROUTER=name)
    without, _ = _run(["hi-s1"])
    assert with_review["overseer"]["review"]["plan_origin"] == "router" and with_review["overseer"]["review"]["plan_refusal"] is None
    def stable(delivery):  # message ids are minted per call
        d = dict(delivery)
        d["deliverable"] = {k: v for k, v in (d["deliverable"] or {}).items() if k != "message_id"}
        return d
    assert stable(with_review["delivery"]) == stable(without["delivery"])
    def claims(v):  # result ids are minted per call; everything else is the same
        return [{k: x for k, x in c.items() if k != "result_id"} for c in v["claims"]]
    assert claims(with_review) == claims(without) and with_review["counts"] == without["counts"] and with_review["summary"] == without["summary"]


# ----------------------------------------------------------------------------------------------- evidence tap


def test_the_evidence_tap_records_the_call_in_the_sim_profile_only(tmp_path):
    verdict, _ = _run(["hi-s1"], SIM_EVIDENCE_DIR=str(tmp_path / "ev"))
    files = list((tmp_path / "ev").glob("*.json"))
    assert len(files) == 1
    evidence = json.loads(files[0].read_text(encoding="utf-8"))
    assert evidence["verdict"]["verdict_id"] == verdict["verdict_id"] and len(evidence["receipts"]) == 2
    assert [p["op"] for p in evidence["port"]] == ["clearance", "clearance", "close", "deliver"]
    with pytest.raises(Exception) as exc:
        EvidenceTap(str(tmp_path / "x"), profile="integration", host="127.0.0.1")
    assert getattr(exc.value, "code", None) == "KIT-HS-012"
    with pytest.raises(Exception) as exc:
        EvidenceTap(str(tmp_path / "x"), profile="integration-sim", host="0.0.0.0")
    assert getattr(exc.value, "code", None) == "KIT-HS-012"


# ----------------------------------------------------------------------------------------------- prefetch non-interference


def _load_compare():
    spec = importlib.util.spec_from_file_location("kit_sim_compare", ROOT / "integration" / "sim" / "compare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("name", ["hi-s1", "hi-s2", "ph-s1"])
def test_prefetch_does_not_change_the_receipts(name):
    from epinoic_logic.branches import RouterHub, default_registry
    from epinoic_logic.integrity import WorkPlan
    from epinoic_logic.translate.contracts import sha256_text
    from epinoic_logic.integration.runtime import solver_config_for
    from epinoic_logic.integration.verifier import first_attempt_request
    compare = _load_compare()
    corpus = FixtureCorpus.load(CORPUS)
    item = _item(name)
    cfg = solver_config_for("integration-sim")
    key = b"prefetch-key-0123456789abcdef0123456789"
    receipts, hits = [], []
    for prefetch in (False, True):
        fn, provider = corpus.verifier_for(sha256_text(item["response_text"]), config=cfg, signing_key=key, prefetch=prefetch)
        if prefetch:
            branch, _ = default_registry().for_subject(item["subject"])
            report = branch.parser().parse_response(item["response_text"], request_id=f"req-{name}", task_id=name, report_id=f"rep-{name}",
                                                    subject=item["subject"], task_type=item["task_type"], supplied_texts=[], agent_id=item["agent_id"])
            from epinoic_logic.translate.prompts import TRANSLATE_PROMPT_VERSION as PROMPT_VERSION
            provider.prefetch([first_attempt_request(c, report, prompt_version=PROMPT_VERSION) for c in report.claims], deadline=time.monotonic() + 60)
        hub = RouterHub(signing_key=key, config=cfg, verify_claim_fn=fn)
        hub.open_task(WorkPlan(plan_id=f"plan-{name}", request_id=f"req-{name}", task_id=name, subject=item["subject"], task_type=item["task_type"],
                               selected_agent_ids=[item["agent_id"]]))
        msg, _req, _rc = hub.dispatch(name, item["agent_id"], item["question"], [])
        _reply, rc = hub.receive(name, msg.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{name}")
        receipts.append(compare.receipt_projection(rc.model_dump(mode="json")))
        hits.append(getattr(provider, "hits", 0))
    assert receipts[0] == receipts[1]
    assert hits[1] > 0, "the prefetched proposals were served (the cache key is the pipeline's first-attempt request)"
