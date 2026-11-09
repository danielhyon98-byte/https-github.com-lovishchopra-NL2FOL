"""The flash decision maker (``decision.py``; rules D1 to D7 of ``rules-3.json``; architecture step 3).

- on minimal inputs it chooses each method where, and only where, it is the cheapest that keeps accuracy: the in-depth
  examination method (one instance examines the whole response) when one review is called for and the response fits one
  instance; independent duplicates when risk calls for agreement; the work split into the fewest parts that fit when it
  does not fit; duplicates in parts under both; N_FOLD for a combined answer; and when nothing keeps accuracy (the pool
  cannot divide one dossier, or the cap allows fewer reviews than risk calls for) the nearest method, disclosed;
- every candidate is priced from the cost data and recorded with whether it keeps accuracy and why it was or was not
  chosen, with closed reason codes;
- risk only escalates: more reviews called for never gives fewer reviews, and a size change never removes a review;
- the decision is code: the same inputs give the same record (in the pool plan too), and nothing it is given is changed;
- the service's combined answer (port rule 5, rules/4): its merged review, which reads the synthesis and every source
  whole and is never divided, is fit-checked like the pool's and recorded ``over_budget`` when one instance cannot read it
  whole; its N_FOLD record carries each source's own decision and the merged review's, and the plan is built from it.
"""
from __future__ import annotations

import copy
import json

import pytest
from hypothesis import given, settings, strategies as st

from epinoic_logic.integration import router_pool as RP
from epinoic_logic.integration import router_port as R

from epinoic_flash_router import decision as D
from epinoic_flash_router import planner as P
from epinoic_flash_router import port, rules

#: A cost model with round numbers (the released file's shape): every composition's system text, 4 characters a token,
#: an output budget of 1,000 tokens and an instance budget of 10,000.
COST = {"chars_per_token": 4, "output_tokens": 1000, "instance_budget_tokens": 10000, "seconds_per_call": 30,
        "system_text_chars": {"core": 8000, "core+stem": 12000, "core+translations": 10000, "core+stem+translations": 14000},
        "dossier": {"base_chars": 1000, "chars_per_answer_char": 3, "chars_per_translation": 400}}
#: One call of the core with an empty read: 2,000 system + 1,000 output = 3,000 tokens; the read room is 7,000 tokens.
ROOM_CHARS = (10000 - 2000 - 1000) * 4


def _decide(**kw):
    base = dict(reviews=1, chars=4000, stem=False, translations=False, cost=COST, cap=8, max_parts=16)
    base.update(kw)
    return D.decide(**base)


def _cand(rec: dict, method: str, parts: int = 1) -> dict:
    return next(c for c in rec["candidates"] if c["method"] == method and c["parts"] == parts)


# ----------------------------------------------------------------------------------------------- each method on minimal inputs
def test_in_depth_is_chosen_when_one_review_is_called_for_and_the_response_fits():
    rec = _decide()
    assert (rec["approach"], rec["method"], rec["reviews"], rec["parts"], rec["instances"], rec["calls"]) == ("in_depth", "IN_DEPTH", 1, 1, 1, 1)
    assert rec["need_tokens"] == 2000 + 1000 + 1000 and rec["fits"] is True and rec["reasons"] == ["in_depth_cheapest"]
    assert rec["estimated_cost"] == {"tokens": 4000, "seconds": 30}
    # the duplicate keeps accuracy too, but costs twice the calls: the in-depth examination is the cheapest that keeps it
    dup = _cand(rec, "DUPLICATE")
    assert dup["keeps_accuracy"] and dup["why"] == "costlier" and dup["tokens"] == 2 * 4000 and _cand(rec, "IN_DEPTH")["why"] == "chosen"


def test_duplicates_are_chosen_when_risk_calls_for_agreement():
    rec = _decide(reviews=2, reasons=("agreement_risk",))
    assert (rec["approach"], rec["method"], rec["reviews"], rec["instances"]) == ("duplication", "DUPLICATE", 2, 2)
    assert rec["reasons"] == ["agreement_risk"] and rec["estimated_cost"] == {"tokens": 8000, "seconds": 60}
    one = _cand(rec, "IN_DEPTH")
    assert not one["keeps_accuracy"] and one["why"] == "agreement_needed"
    # three reviews called for (a signal and an escalation together): three duplicates, never fewer
    three = _decide(reviews=3, reasons=("agreement_risk", "agreement_escalation"))
    assert (three["method"], three["reviews"], three["reasons"]) == ("DUPLICATE", 3, ["agreement_risk", "agreement_escalation"])


def test_the_work_is_split_into_the_fewest_parts_that_fit_when_the_response_does_not_fit():
    chars = 3 * ROOM_CHARS  # three instances' worth of reading: two parts are too few, three fit exactly
    rec = _decide(chars=chars)
    assert (rec["approach"], rec["method"], rec["reviews"], rec["parts"], rec["instances"]) == ("duplication", "SPLIT", 1, 3, 3)
    assert rec["fits"] is False and rec["reasons"] == ["split_to_fit"]
    assert all(D.call_tokens(2000, -(-chars // 3), COST) <= 10000 for _ in (0,)) and D.call_tokens(2000, -(-chars // 2), COST) > 10000
    assert _cand(rec, "IN_DEPTH")["why"] == "exceeds_budget" and _cand(rec, "DUPLICATE")["why"] == "exceeds_budget"
    assert _cand(rec, "SPLIT", 3)["keeps_accuracy"] and _cand(rec, "SPLIT", 3)["why"] == "chosen"


def test_duplicates_in_parts_when_risk_calls_for_agreement_and_the_response_does_not_fit():
    rec = _decide(chars=2 * ROOM_CHARS, reviews=2, reasons=("agreement_risk",))
    assert (rec["method"], rec["reviews"], rec["parts"], rec["instances"], rec["calls"]) == ("DUPLICATE", 2, 2, 4, 4)
    assert rec["reasons"] == ["agreement_risk", "split_to_fit"]


def test_a_combined_answer_is_n_fold_with_each_part_recorded():
    src1, src2 = _decide(chars=4000), _decide(chars=8000, reviews=2, reasons=("agreement_risk",))
    merged = _decide(chars=6000)
    whole = _decide(chars=18000)
    rec = D.n_fold_decision(sources=[src1, src2], merged=merged, whole=whole, cost=COST)
    assert (rec["approach"], rec["method"], rec["parts"], rec["reviews"]) == ("duplication", "N_FOLD", 2, 1)
    assert rec["instances"] == 1 + 2 and rec["calls"] == 1 + 2 + 1 and "combined_n_fold" in rec["reasons"]
    tokens = src1["estimated_cost"]["tokens"] + src2["estimated_cost"]["tokens"] + merged["estimated_cost"]["tokens"]
    assert rec["estimated_cost"] == {"tokens": tokens, "seconds": 4 * 30}
    n_fold, *refused = rec["candidates"]
    assert n_fold["method"] == "N_FOLD" and n_fold["keeps_accuracy"] and n_fold["why"] == "chosen"
    assert refused and all(not c["keeps_accuracy"] and c["why"] == "combined_needs_n_fold" for c in refused)


def test_a_dossier_the_pool_cannot_divide_and_no_instance_reads_whole_is_disclosed_never_shortened():
    rec = _decide(chars=2 * ROOM_CHARS, methods=("IN_DEPTH", "DUPLICATE"))
    assert rec["fits"] is False and rec["reasons"] == ["over_budget"] and (rec["method"], rec["parts"]) == ("IN_DEPTH", 1)
    assert not any(c["keeps_accuracy"] for c in rec["candidates"]) and rec["need_tokens"] > rec["budget_tokens"]
    # with agreement called for, the disclosed decision still gives every review
    agreed = _decide(chars=2 * ROOM_CHARS, reviews=2, methods=("IN_DEPTH", "DUPLICATE"), reasons=("agreement_risk",))
    assert (agreed["method"], agreed["reviews"]) == ("DUPLICATE", 2) and agreed["reasons"] == ["agreement_risk", "over_budget"]


def test_an_unmeasured_size_is_recorded_and_the_fit_not_assessed():
    rec = _decide(chars=None)
    assert (rec["method"], rec["fits"], rec["need_tokens"], rec["estimated_cost"]["tokens"]) == ("IN_DEPTH", None, None, None)
    assert rec["reasons"] == ["in_depth_cheapest", "size_not_measured"]


def test_a_cap_below_the_reviews_risk_calls_for_gives_the_most_reviews_it_allows():
    rec = _decide(reviews=3, cap=2, reasons=("agreement_risk",))
    assert (rec["method"], rec["reviews"]) == ("DUPLICATE", 2) and not any(c["keeps_accuracy"] for c in rec["candidates"])
    assert _cand(rec, "DUPLICATE")["why"] == "chosen" and _cand(rec, "IN_DEPTH")["why"] == "agreement_needed"


def test_the_composition_the_content_needs_prices_every_call():
    plain, stem = _decide(), _decide(stem=True)
    both = _decide(stem=True, translations=True)
    assert plain["need_tokens"] < stem["need_tokens"] < both["need_tokens"]
    assert [D.composition_key(s, t) for s, t in ((False, False), (True, False), (False, True), (True, True))] == list(COST["system_text_chars"])
    assert D.port_dossier_chars(100, 50, 2, COST) == 1000 + 300 + 50 + 800


# ----------------------------------------------------------------------------------------------- risk only escalates
@pytest.mark.parametrize("chars", [None, 0, 4000, ROOM_CHARS, 2 * ROOM_CHARS, 3 * ROOM_CHARS, 40 * ROOM_CHARS])
@pytest.mark.parametrize("methods", [("IN_DEPTH", "DUPLICATE", "SPLIT"), ("IN_DEPTH", "DUPLICATE")])
def test_more_reviews_called_for_never_gives_fewer_reviews(chars, methods):
    got = [_decide(chars=chars, reviews=r, methods=methods)["reviews"] for r in (1, 2, 3, 4)]
    assert got == sorted(got) and all(g >= min(r, 8) for g, r in zip(got, (1, 2, 3, 4)))


# ----------------------------------------------------------------------------------------------- the pool plan's decisions
def _pool(items: list[dict], max_instances: int = 4) -> RP.AnyPoolPlan:
    req = RP.build_pool_request(items, max_instances=max_instances, per_instance_quota=8)
    r = port.FlashRouter()
    return RP.check_pool_plan(r.pool_plan(RP.canonical_json(RP.dump(req))), req, hello=RP.check_pool_hello(r.pool_hello()))


def _features(chars: int, stem: bool = False, translations: int = 0) -> dict:
    return {"transfers": 3, "chars": chars, "stem": stem, "translations": translations}


def _pool_item(*, signals=(), advised=False, chars=20000, sources=None, merged=None) -> dict:
    it = {"repeated_faults": 0, "risk_signals": sorted(signals), "risk_records": [], "advised": advised, "features": _features(chars)}
    if sources is not None:
        it.update(sources=sources, merged=merged)
    return it


def _part(*, signals=(), chars=10000) -> dict:
    return {"repeated_faults": 0, "risk_signals": sorted(signals), "risk_records": [], "features": _features(chars)}


def test_the_pool_plan_records_the_flash_decision_for_each_method_on_minimal_inputs():
    plan = _pool([_pool_item(), _pool_item(signals=("integrity_error",)), _pool_item(advised=True),
                  _pool_item(sources=[_part(), _part(signals=("rejection",))], merged=_part())])
    assert plan.port_version == "1.2"
    a, b, c, n = plan.assignments
    assert (a.method, a.decision.approach, a.decision.reasons) == ("IN_DEPTH", "in_depth", ["in_depth_cheapest"])
    assert (b.method, b.decision.approach, len(b.instances), b.decision.reasons) == ("DUPLICATE", "duplication", 2, ["agreement_risk"])
    assert (c.method, len(c.instances), c.decision.reasons) == ("DUPLICATE", 2, ["agreement_advised"])
    assert (n.method, n.decision.approach, "combined_n_fold" in n.decision.reasons) == ("N_FOLD", "duplication", True)
    assert [len(s.instances) for s in n.sources] == [1, 2] and len(n.instances) == 1 and n.context.max_bytes == 65536
    assert [p.part for p in n.decision.parts] == ["source", "source", "merged"] and n.decision.candidates[0].method == "N_FOLD"
    cost = rules.COST_MODEL
    one = D.call_tokens(D.system_tokens(False, False, cost), 20000, cost)
    assert a.decision.need_tokens == one and a.decision.estimated_cost.tokens == one and b.decision.estimated_cost.tokens == 2 * one
    assert plan.estimated_cost.tokens == sum(x.decision.estimated_cost.tokens for x in plan.assignments)


def test_the_decision_is_code_the_same_inputs_give_the_same_record_and_nothing_given_is_changed():
    cost = copy.deepcopy(rules.COST_MODEL)
    kw = dict(reviews=2, chars=900000, stem=True, translations=True, cost=cost, cap=8, max_parts=16, reasons=("agreement_risk",))
    first = D.decide(**kw)
    assert all(D.decide(**kw) == first for _ in range(3)) and cost == rules.COST_MODEL
    items = [_pool_item(signals=("named_defect",), chars=700000), _pool_item(sources=[_part(), _part()], merged=_part())]
    snapshot = json.dumps(items, sort_keys=True)
    plans = {RP.canonical_json(RP.dump(_pool(items))) for _ in range(3)}
    assert len(plans) == 1 and json.dumps(items, sort_keys=True) == snapshot


# ----------------------------------------------------------------------------------------------- the service's combined answer
def _port_output(key: str, *, role: str = "answer", chars: int, translated: int = 0, stem: bool = False, rejected: bool = False) -> dict:
    return {"transfer_key": key, "role": role, "agent_id": "history" if role == "answer" else "synthesis", "subject": "History",
            "branch": "history", "stem": stem, "size": {"chars": chars, "words": chars // 6, "paragraphs": 3},
            "claims": {"total": 6, "material": 4, "eligible": 3, "translated": translated}, "engine_statuses": {"ENTAILED": 2},
            "receipt": {"status": "REJECTED" if rejected else "ACCEPTED", "error_codes": [], "warning_codes": []},
            "diagnostics": [], "unverified_dependencies": 0, "peer_relays": 0, "repeated_faults": 0}


def _combined(source_chars: list[int], synthesis_chars: int = 6000, *, synthesis_rejected: bool = False, max_instances: int = 8,
              translated: int = 0, stem: bool = False) -> dict:
    outs = [_port_output(f"m-{k}", chars=c, translated=translated, stem=stem) for k, c in enumerate(source_chars, start=1)]
    outs.append(_port_output("m-s", role="synthesis", chars=synthesis_chars, rejected=synthesis_rejected))
    return {"schema": "epinoic.integration.routing-request.v1", "protocol": "epinoic.integration.v1", "port_version": "1.0",
            "ids": {"task_id": "t_" + "0" * 31 + "1", "request_id": "a_" + "0" * 31 + "1"},
            "request": {"subjects": ["History"], "stem": stem, "task_type": "short_answer", "course_level": "unknown",
                        "items": [], "constraints": [], "supplied_texts": [], "user_text_sha256": "d4" * 32},
            "outputs": outs, "topology": {"kind": "combined", "sources": [o["transfer_key"] for o in outs[:-1]], "synthesis": "m-s"},
            "limits": {"max_instances": max_instances, "profiles": ["standard"]}}


def _service_plan(raw: dict) -> tuple[R.RoutingRequest, dict, list[dict]]:
    req = R.check_request(raw)
    text = R.canonical_json(R.dump(req))
    return req, json.loads(port.plan(text)), P.transfer_decisions(json.loads(text))


def test_the_port_s_n_fold_merged_review_is_fit_checked_and_disclosed_over_budget_never_shortened():
    """The finding's case (architecture lenses after arena round 8): a combined answer of three 150,000-character sources.
    Each source fits one instance whole; the merged review reads the synthesis and every source whole (port rule 7), above
    the instance budget. Before rules/4 the port priced it with no fit test and no decision; now it is decided as the pool
    decides one (D4, D6): never divided, recorded fits false with over_budget, and the plan's numbers are the record's."""
    req, plan, records = _service_plan(_combined([150_000] * 3))
    cost = rules.COST_MODEL
    budget = cost["instance_budget_tokens"]
    *sources, synthesis = records
    for rec, entry in zip(sources, plan["transfers"]):
        assert rec["transfer_key"] == entry["transfer_key"] and (rec["method"], rec["parts"]) == (entry["method"], entry["parts"]) == ("IN_DEPTH", 1)
        assert rec["fits"] is True and rec["reasons"] == ["in_depth_cheapest"]
    need = D.call_tokens(D.system_tokens(False, False, cost), D.port_dossier_chars(6000 + 3 * 150_000, 0, 0, cost), cost)
    assert need > budget, "one instance cannot read the merged review whole"
    merged = synthesis["part_decisions"][-1]
    assert (merged["part"], merged["transfer_key"], merged["method"], merged["parts"]) == ("merged", "m-s", "IN_DEPTH", 1)
    assert (merged["need_tokens"], merged["fits"], merged["reasons"]) == (need, False, ["over_budget"])
    assert (synthesis["transfer_key"], synthesis["method"], synthesis["approach"], synthesis["fits"]) == ("m-s", "N_FOLD", "duplication", False)
    assert synthesis["reasons"] == ["combined_n_fold", "over_budget"] and synthesis["budget_tokens"] == budget
    assert [(p["part"], p["transfer_key"]) for p in synthesis["part_decisions"]] == [("source", "m-1"), ("source", "m-2"), ("source", "m-3"), ("merged", "m-s")]
    n_fold, *refused = synthesis["candidates"]
    assert n_fold["method"] == "N_FOLD" and refused and all(c["why"] == "combined_needs_n_fold" for c in refused)
    entry = plan["transfers"][-1]
    assert (entry["method"], entry["reviews"], entry["parts"], entry["instances"]) == ("N_FOLD", 1, 1, 1)
    assert entry["estimated_cost"] == {"tokens": need, "seconds": cost["seconds_per_call"]}, "one call reading the merged review whole"
    adm = R.admit_plan(req, plan, hello=R.check_hello(json.loads(port.hello())))
    assert (adm.origin, adm.refusal) == ("router", None), adm.detail
    # router port 1.0's closed reasons have no code for it: the record is where it is disclosed until the port adds one
    # (then this router carries it into the plan, and this assertion is rewritten to the stricter rule)
    assert "over_budget" not in R.REASON_CODES and "over_budget" not in entry["reasons"]


def test_the_port_s_n_fold_record_carries_each_source_s_own_decision_and_the_merged_review_s():
    """A combined answer whose merged review fits, with a risk signal on the synthesis: the merged review is duplicated
    (agreement), each source's part is the decision its own entry is planned by, and the N_FOLD record's estimated cost is
    the plan's total (the sources' entries and the merged review's)."""
    _req, plan, records = _service_plan(_combined([20_000, 40_000], synthesis_chars=8000, synthesis_rejected=True))
    synthesis = records[-1]
    merged = synthesis["part_decisions"][-1]
    assert (merged["method"], merged["reviews"], merged["fits"], merged["reasons"]) == ("DUPLICATE", 2, True, ["agreement_risk"])
    assert (synthesis["method"], synthesis["reviews"], synthesis["fits"], synthesis["reasons"]) == ("N_FOLD", 2, True, ["agreement_risk", "combined_n_fold"])
    assert [(p["transfer_key"], p["method"], p["reviews"], p["parts"]) for p in synthesis["part_decisions"][:-1]] == \
        [(t["transfer_key"], t["method"], t["reviews"], t["parts"]) for t in plan["transfers"][:-1]]
    assert [r["transfer_key"] for r in records] == [t["transfer_key"] for t in plan["transfers"]]
    assert plan["transfers"][-1]["estimated_cost"]["tokens"] == 2 * merged["need_tokens"]
    assert synthesis["estimated_cost"] == plan["totals"]["estimated_cost"]


@settings(max_examples=120, deadline=None)
@given(st.lists(st.sampled_from([0, 6000, 60_000, 150_000, 260_000, 400_000]), min_size=2, max_size=16),
       st.sampled_from([0, 6000, 400_000]), st.booleans(), st.sampled_from([2, 3, 8, 64]), st.sampled_from([0, 2]), st.booleans())
def test_every_port_n_fold_is_decided_by_the_fit_rule_and_its_plan_is_the_record_s(source_chars, synthesis_chars, rejected, max_instances,
                                                                                    translated, stem):
    req, plan, records = _service_plan(_combined(source_chars, synthesis_chars, synthesis_rejected=rejected, max_instances=max_instances,
                                                 translated=translated, stem=stem))
    budget = rules.COST_MODEL["instance_budget_tokens"]
    synthesis, entry = records[-1], plan["transfers"][-1]
    merged = synthesis["part_decisions"][-1]
    assert merged["parts"] == 1 and merged["method"] in P.MERGED_METHODS, "a merged review is never divided"
    assert ("over_budget" in merged["reasons"]) == (merged["fits"] is False) == (merged["need_tokens"] > budget)
    assert synthesis["fits"] is all(p["fits"] for p in synthesis["part_decisions"])
    assert ("over_budget" in synthesis["reasons"]) == any("over_budget" in p["reasons"] for p in synthesis["part_decisions"])
    assert entry["estimated_cost"]["tokens"] == entry["reviews"] * merged["need_tokens"] and merged["reviews"] == entry["reviews"]
    for rec, t in zip(records[:-1], plan["transfers"][:-1]):
        assert (rec["method"], rec["reviews"], rec["parts"]) == (t["method"], t["reviews"], t["parts"])
    adm = R.admit_plan(req, plan, hello=R.check_hello(json.loads(port.hello())))
    assert (adm.origin, adm.refusal) == ("router", None), adm.detail


def test_the_decision_records_need_the_decision_maker_s_data(tmp_path):
    import shutil
    from pathlib import Path
    dest = tmp_path / "data-0.2.0"
    shutil.copytree(Path(rules.DATA_DIR), dest)
    manifest = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["current"] = {"rules": "rules-2.json", "cost_data": "cost-data-2.json"}
    (dest / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="rules/2"):
        P.transfer_decisions(_combined([1000, 1000]), data=rules.DataSet(str(dest)))


def _hostile_combined(n: int, *, repeated_synthesis: bool) -> dict:
    """A request out of the router port's contract (which holds at most 17 outputs and 16 sources): ``n - 1`` sources and
    one synthesis, or the synthesis's key repeated ``n`` times."""
    req = _combined([100] * (n - 1), 100)
    if repeated_synthesis:
        req["outputs"] = [req["outputs"][-1]] * n + req["outputs"][:-1]
    return req


def test_a_routing_request_naming_one_transfer_key_twice_is_refused_at_once():
    """Port rule 1 (every transfer one entry), as the router port's check_request refuses it: a request repeating the
    synthesis's key 16,000 times over 15,999 sources was planned once per repetition, each reading every source (149 s
    measured with 0.3.0's planner); it is refused at once."""
    import time
    hostile = _hostile_combined(16_000, repeated_synthesis=True)
    for call in (lambda: port.plan(json.dumps(hostile)), lambda: P.transfer_decisions(hostile)):
        t = time.perf_counter()
        with pytest.raises(ValueError, match="names one transfer key twice"):
            call()
        assert time.perf_counter() - t < 20, "refused in about 0.2 s; the bound is a wide margin"


def test_a_combined_answer_of_many_sources_is_decided_in_one_pass():
    """One synthesis over 15,999 sources (far out of contract): the N_FOLD record is made once, in one pass over the
    sources (about 0.7 s measured), and its plan entry is the merged review's."""
    import time
    hostile = _hostile_combined(16_000, repeated_synthesis=False)
    t = time.perf_counter()
    plan = json.loads(port.plan(json.dumps(hostile)))
    records = P.transfer_decisions(hostile)
    assert time.perf_counter() - t < 30, "about 1.5 s for both; the bound is a wide margin"
    assert plan["transfers"][-1]["method"] == "N_FOLD" and records[-1]["method"] == "N_FOLD"
    assert len(records[-1]["part_decisions"]) == 16_000 and records[-1]["part_decisions"][-1]["part"] == "merged"
