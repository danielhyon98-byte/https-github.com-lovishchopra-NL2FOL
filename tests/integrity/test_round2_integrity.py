"""Integrity checks added after the round-2 arena: figure and date fidelity between a
synthesized claim and its cited sources (INT-LEDGER-023 / INT-LEDGER-024), the conflict
disclosure rule shared by the Overseer report and the channel, and per-agent task types
on the work plan (INT-HANDOFF-010)."""
from __future__ import annotations

import pytest

from epinoic_logic.integrity import (
    ConflictRecord, Synthesis, SynthesizedClaim, WorkPlan, check_conflict_disclosure, check_report_against_plan, check_synthesis_ledger,
)
from epinoic_logic.integrity.contracts import plan_digest
from epinoic_logic.integrity.ledger import figure_tokens
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

REQ, TASK = "req-l", "task-l"
TRANSFORMATIONS = ["carried", "paraphrased", "merged", "narrowed", "generalized"]


def report(agent, subject, claims, report_id=None, task_type="short_answer"):
    rid = report_id or f"rep-{agent}"
    text = " ".join(c["claim_text"] for c in claims)
    return SpecialistReport(report_id=rid, request_id=REQ, task_id=TASK, agent_id=agent, subject=subject, task_type=task_type, original_response=text,
                            response_sha256=sha256_text(text), created_at="2026-10-11T10:00:00Z",
                            claims=[ClaimRecord(request_id=REQ, task_id=TASK, report_id=rid, agent_id=agent, subject=subject, task_type=task_type, **c) for c in claims])


def history():
    return report("history-specialist", "History", [
        dict(claim_id="h1.1", claim_text="The sonnet was printed in January 1818 in The Examiner.", claim_role="evidence"),
        dict(claim_id="h1.5", claim_text="Wheat had cost 80 shillings a quarter in 1815, and some 9,000 banks failed later.", claim_role="evidence"),
    ])


def synthesis(claims, conflicts=(), reports=("rep-history-specialist",)):
    text = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-1", request_id=REQ, task_id=TASK, combinator_agent_id="combinator", source_report_ids=list(reports),
                     claims=list(claims), conflicts=list(conflicts), text=text, text_sha256=sha256_text(text), created_at="2026-10-11T10:05:00Z")


# ------------------------------------------------------------ figures and dates


@pytest.mark.parametrize("transformation", TRANSFORMATIONS)
@pytest.mark.parametrize("source,text,token", [
    ("h1.5", "Wheat had cost 60 shillings a quarter in 1815, and some 9,000 banks failed later.", "60"),
    ("h1.5", "Wheat had cost 80 shillings a quarter in 1815, and some 8,000 banks failed later.", "8000"),
    ("h1.1", "The sonnet was printed in January 1819 in The Examiner.", "1819"),
    ("h1.1", "The sonnet was printed in March 1818 in The Examiner.", "march 1818"),
])
def test_a_changed_figure_or_date_is_named_under_every_transformation(transformation, source, text, token):
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text=text, certainty="probable", source_claim_ids=[source], transformation=transformation)])
    changed = [f for f in check_synthesis_ledger([history()], syn) if f.code == "INT-LEDGER-023"]
    assert len(changed) == 1 and changed[0].severity == "error"
    assert f"'{token}'" in changed[0].message and changed[0].claim_ids == ["s-1", source] and changed[0].agent_ids == ["combinator"]


def test_faithful_and_merged_claims_introduce_no_figures():
    rep = history()
    faithful = synthesis([SynthesizedClaim(claim_id="s-1", text=rep.claims[1].claim_text, certainty="probable", source_claim_ids=["h1.5"], transformation="carried")])
    assert not [f for f in check_synthesis_ledger([rep], faithful) if f.code in ("INT-LEDGER-023", "INT-LEDGER-024")]
    merged = synthesis([SynthesizedClaim(claim_id="s-1", text="Printed in January 1818, when wheat cost 80 shillings a quarter in 1815 and 9,000 banks would fail.", certainty="probable",
                                         source_claim_ids=["h1.1", "h1.5"], transformation="merged")])
    assert not [f for f in check_synthesis_ledger([rep], merged) if f.code == "INT-LEDGER-023"]


@pytest.mark.parametrize("transformation", ["carried", "paraphrased"])
def test_a_source_figure_dropped_under_an_equivalence_label_is_a_warning(transformation):
    syn = synthesis([SynthesizedClaim(claim_id="s-1", text="Wheat was dear in 1815 and many banks failed later.", certainty="probable", source_claim_ids=["h1.5"], transformation=transformation)])
    dropped = [f for f in check_synthesis_ledger([history()], syn) if f.code == "INT-LEDGER-024"]
    assert dropped and dropped[0].severity == "warning" and "'80'" in dropped[0].message and "'9000'" in dropped[0].message and "'1815'" not in dropped[0].message
    narrowed = synthesis([SynthesizedClaim(claim_id="s-1", text="Wheat was dear in 1815.", certainty="probable", source_claim_ids=["h1.5"], transformation="narrowed")])
    assert not [f for f in check_synthesis_ledger([history()], narrowed) if f.code == "INT-LEDGER-024"]  # narrowing removes content by definition


def test_figure_tokens_cover_numerals_thousands_and_month_years_only():
    assert figure_tokens("Some 9,000 banks failed between 1930 and 1933; prices fell 25.5 per cent in January 1931.") == {"9000", "1930", "1933", "25.5", "1931", "january 1931"}
    assert figure_tokens("1. The 1930s were hard; the 19th century ended.") == set()


# ------------------------------------------------------------ conflict disclosure


def test_conflict_disclosure_is_one_shared_rule():
    sets = [(frozenset({"ph-1", "ma-1"}), "res-1")]
    bare = synthesis([SynthesizedClaim(claim_id="s-1", text="The speed is 15 m/s.", source_claim_ids=["ph-1"], transformation="carried")])
    f = check_conflict_disclosure(bare, sets)
    assert [x.code for x in f] == ["INT-CONFLICT-002"] and set(f[0].claim_ids) == {"ph-1", "ma-1"} and f[0].formal_result_id == "res-1" and not f[0].deterministic
    named = synthesis(bare.claims, conflicts=[ConflictRecord(conflict_id="cf", claim_ids=["ph-1", "ma-1"], description="the specialists disagree")])
    assert check_conflict_disclosure(named, sets) == []
    via_synthesized = synthesis(bare.claims, conflicts=[ConflictRecord(conflict_id="cf", claim_ids=["s-1", "ma-1"], description="s-1 stands for ph-1")])
    assert check_conflict_disclosure(via_synthesized, sets) == []
    assert check_conflict_disclosure(bare, [(frozenset({"ph-1"}), "r")]) == []  # a single-claim core demands no disclosure
    assert len(check_conflict_disclosure(bare, sets + sets)) == 1  # the same conflicting set is reported once


# ------------------------------------------------------------ per-agent task types


def test_plan_task_types_per_agent():
    plan = WorkPlan(plan_id="p", request_id=REQ, task_id=TASK, subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist", "maths-specialist"],
                    agent_task_types={"physics-specialist": "essay"})
    essay = report("physics-specialist", "Physics", [dict(claim_id="p-1", claim_text="x", claim_role="other")], task_type="essay")
    assert not [f for f in check_report_against_plan(plan, essay) if f.code == "INT-HANDOFF-010"]
    short = report("physics-specialist", "Physics", [dict(claim_id="p-2", claim_text="x", claim_role="other")], task_type="short_answer")
    f = [x for x in check_report_against_plan(plan, short) if x.code == "INT-HANDOFF-010"]
    assert f and "'essay'" in f[0].message and "physics-specialist" in f[0].message
    maths = report("maths-specialist", "Physics", [dict(claim_id="m-1", claim_text="x", claim_role="other")], task_type="short_answer")
    assert not [x for x in check_report_against_plan(plan, maths) if x.code == "INT-HANDOFF-010"]
    base = dict(plan_id="p", request_id=REQ, task_id=TASK, subject="Physics", task_type="short_answer", selected_agent_ids=["a"])
    assert plan_digest(WorkPlan(**base)) == plan_digest(WorkPlan(**base, agent_task_types={})) != plan_digest(WorkPlan(**base, agent_task_types={"a": "essay"}))
    with pytest.raises(ValueError, match="agent_task_types"):
        WorkPlan(**base, agent_task_types={"a": " "})
    with pytest.raises(ValueError, match="did not select"):
        WorkPlan(**base, agent_task_types={"b": "essay"})
