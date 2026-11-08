"""The flash decision maker (``decision.py``; rules D1 to D7 of ``rules-3.json``; architecture step 3).

- on minimal inputs it chooses each method where, and only where, it is the cheapest that keeps accuracy: the in-depth
  examination method (one instance examines the whole response) when one review is called for and the response fits one
  instance; independent duplicates when risk calls for agreement; the work split into the fewest parts that fit when it
  does not fit; duplicates in parts under both; N_FOLD for a combined answer; and when nothing keeps accuracy (the pool
  cannot divide one dossier, or the cap allows fewer reviews than risk calls for) the nearest method, disclosed;
- every candidate is priced from the cost data and recorded with whether it keeps accuracy and why it was or was not
  chosen, with closed reason codes;
- risk only escalates: more reviews called for never gives fewer reviews, and a size change never removes a review;
- the decision is code: the same inputs give the same record (in the pool plan too), and nothing it is given is changed.
"""
from __future__ import annotations

import copy
import json

import pytest

from epinoic_logic.integration import router_pool as RP

from epinoic_flash_router import decision as D
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
