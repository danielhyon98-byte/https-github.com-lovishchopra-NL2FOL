"""Row 1 of the decision table on a truncated claim list (PROTOCOL.md section 5.4: ``counts`` cover every claim, the
list holds at most 32 and only claims with an excerpt): the listed claims are lower bounds of the counts whatever the
list's length, every count but ``claims_total`` is exact once every material claim is listed, and the counts must be the
counts of some list of claims. So a verdict whose listed material claim is TIMEOUT or COUNTEREXAMPLE but whose counts
say 0 is refused (kit_dl_030) on both sides, while every genuine verdict, truncated or not, passes."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from hypothesis import given, settings as hsettings, strategies as st

from epinoic_logic.integration.delivery import BindingContext, ClaimFields, binding_problem, count_claims, counts_problem
from epinoic_logic.integration.protocol import INCOMPLETE_STATUSES, NEGATIVE

ROOT = Path(__file__).resolve().parents[2]
DELIVER_BOUND = json.loads((ROOT / "integration" / "vectors" / "verdict-binding" / "deliver-bound.json").read_text(encoding="utf-8"))
FORMALS = ["ENTAILED", "CONSISTENT", "SATISFIABLE", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE", "UNKNOWN", "TIMEOUT",
           "UNSUPPORTED", "INVALID_FORMALIZATION", "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE", "INTERNAL_ERROR", "NOT_ATTEMPTED"]


def _ctx(c: dict) -> BindingContext:
    return BindingContext(task_id=c["task_id"], request_id=c["request_id"], user_text=c["user_text"], policy=c["policy"], mode=c["mode"],
                          answers=[tuple(a) for a in c["answers"]], release_text=c["release_text"], revision_of=c["revision_of"])


def _claim():
    def build(materiality, formal, attempt, permitted):
        if formal == "NOT_ELIGIBLE":
            attempt = "not_eligible"
        elif attempt == "not_eligible":
            attempt = "attempted"
        return ClaimFields(materiality, formal, attempt, permitted and formal in ("ENTAILED", "CONSISTENT", "SATISFIABLE"))
    return st.builds(build, st.sampled_from(["material", "supporting"]), st.sampled_from(FORMALS),
                     st.sampled_from(["attempted", "skipped_budget", "stem_budget", "provider_unavailable", "skipped_cap", "not_eligible"]),
                     st.booleans())


@hsettings(max_examples=400, deadline=None)
@given(st.lists(_claim(), max_size=40), st.data())
def test_every_genuine_list_passes_however_it_is_truncated(claims, data):
    """The service counts every claim and lists a part of them (material first, at most 32): never a counts problem."""
    listed = data.draw(st.lists(st.sampled_from(range(len(claims))), unique=True, max_size=min(32, len(claims)))) if claims else []
    assert counts_problem(count_claims(claims), count_claims(claims[i] for i in listed), len(listed)) is None


@hsettings(max_examples=400, deadline=None)
@given(st.lists(_claim(), min_size=1, max_size=40), st.data())
def test_a_listed_negative_or_incomplete_claim_can_never_be_counted_away(claims, data):
    listed = data.draw(st.lists(st.sampled_from(range(len(claims))), unique=True, min_size=1, max_size=min(32, len(claims))))
    shown = [claims[i] for i in listed]
    counts = count_claims(claims)
    if any(c.materiality == "material" and c.formal in NEGATIVE for c in shown):
        assert counts_problem({**counts, "blocking": 0}, count_claims(shown), len(shown)) is not None
    if any(c.materiality == "material" and c.attempt != "not_eligible" and c.formal in INCOMPLETE_STATUSES for c in shown):
        assert counts_problem({**counts, "unavailable": 0}, count_claims(shown), len(shown)) is not None


@pytest.mark.parametrize("formal", ["TIMEOUT", "UNKNOWN", "NOT_ATTEMPTED", "INTERNAL_ERROR", "COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "UNSATISFIABLE"])
@pytest.mark.parametrize("extra", [0, 1, 5])
def test_a_listed_material_non_result_with_counts_that_hide_it_is_refused(formal, extra):
    """The verifier's case: deliver-bound with claims[0] edited, its counts kept, claims_total raised as if truncated."""
    v = copy.deepcopy(DELIVER_BOUND["verdict"])
    v["claims"][0]["formal"] = formal
    v["counts"]["claims_total"] += extra
    assert binding_problem(v, _ctx(DELIVER_BOUND["context"]))[0] == "kit_dl_030"


def test_a_genuine_truncated_verdict_still_delivers():
    v = copy.deepcopy(DELIVER_BOUND["verdict"])
    for k in ("claims_total", "material", "eligible", "attempted", "definitive", "positive"):
        v["counts"][k] += 1  # one more positive material claim, counted but not listed (no excerpt)
    assert binding_problem(v, _ctx(DELIVER_BOUND["context"])) is None
    v["counts"]["claims_total"] += 40  # and forty supporting claims
    assert binding_problem(v, _ctx(DELIVER_BOUND["context"])) is None


def test_the_counts_must_be_the_counts_of_some_list():
    base = count_claims([ClaimFields("material", "ENTAILED", "attempted", False)])
    for broken in ({"permitted": 1, "positive": 0}, {"eligible": 0}, {"attempted": 3, "claims_total": 3, "material": 2, "eligible": 2},
                   {"definitive": 2, "claims_total": 3, "material": 2, "eligible": 2, "attempted": 2}, {"blocking": 2, "claims_total": 3},
                   {"unavailable": 1}):
        assert counts_problem({**base, **broken, "claims_total": max(base["claims_total"], broken.get("claims_total", 0)) + 5}, count_claims([]), 0), broken
