"""Corrections after the round-7 simulation: adjudicated genuine faults in the contained harness.

Recorded "genuine" transfers are real cheap-tier outputs and can carry real faults. The contained run
(``scripts/overseer/run_contained.py``) reads a versioned, evidenced record of them
(``scripts/overseer/adjudicated_genuine_faults.json``) and changes three things, each pinned here:

* a false alarm is an error-level finding on a genuine transfer that matches NO adjudicated entry exactly (round, channel,
  claim, code, agent): an unadjudicated error is still a false alarm;
* the new gate ``adjudicated_genuine_faults_raised``: every adjudicated entry of a round the run replayed must be raised as
  an error on its genuine transfer; a missing one FAILS the run (stricter, never looser);
* on an arena fault variant, an extra error matching an adjudicated entry for the same claim of the same task is not a
  disagreement with the receipt; every other extra error still is.

The record itself is refused unless its format, fields and ids hold and every entry's engine evidence reproduces (the
embedded IR, its restating premises, ENTAILED as recorded, COUNTEREXAMPLE without them). These tests need no recorded
round: the record embeds the IR it adjudicates.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import run_contained as RC  # noqa: E402

from epinoic_logic.engine import SolverConfig, verify  # noqa: E402
from epinoic_logic.ir.canonical import canonical_json  # noqa: E402
from epinoic_logic.overseer.codes import ovs_finding  # noqa: E402

RECORD = json.loads(RC.ADJUDICATIONS_FILE.read_text(encoding="utf-8"))
CS = "r7/cs-t13/g11.3/OVS-TRN-006"
ESS = "r7/ess-t13/g4.3/OVS-TRN-006"


def adjudications() -> dict:
    return RC.load_adjudications()


def trn006(claim: str = "g11.3", agent: str = "computer-science-specialist", *, claims=None, code: str = "OVS-TRN-006"):
    return ovs_finding(code, f"circular translation of claim {claim}", claim_ids=claims if claims is not None else [claim], message_ids=["m-1"],
                       report_ids=["rep-cs-t13-0"], agent_ids=[agent])


# ============================================================================================ the record
def test_the_record_adjudicates_exactly_the_two_engine_confirmed_circular_translations_and_not_bm_t13():
    a = adjudications()
    assert a["format"] == "overseer-adjudicated-genuine-faults/1.0" and isinstance(a["version"], int)
    assert [(e["round"], e["channel"], e["claim_id"], e["code"], e["agent_id"]) for e in a["entries"]] == [
        ("r7", "cs-t13", "g11.3", "OVS-TRN-006", "computer-science-specialist"), ("r7", "ess-t13", "g4.3", "OVS-TRN-006", "ess-specialist")]
    assert not any(e["channel"] == "bm-t13" for e in a["entries"])  # redundant restatement: OVS-TRN-010, a warning, never adjudicated
    assert any("bm-t13 g2.1" in r for r in RECORD["rules"])
    for e in a["entries"]:
        assert e["why_genuine"] and e["evidence"]["how"] and e["evidence"]["without_restating_premises"]["status"] == "COUNTEREXAMPLE"


@pytest.mark.parametrize("entry_id", [CS, ESS])
def test_each_entry_s_evidence_reproduces_with_the_engine(entry_id):
    e = next(x for x in RECORD["entries"] if x["id"] == entry_id)
    prob = e["translation"]["problem"]
    restating = e["evidence"]["restating_premises"]
    assert verify(canonical_json(prob), SolverConfig()).status.value == "ENTAILED"
    reduced = {**prob, "premises": [p for p in prob["premises"] if p["id"] not in restating]}
    r = verify(canonical_json(reduced), SolverConfig())
    assert r.status.value == "COUNTEREXAMPLE" and {a.symbol: a.value for a in r.counterexample.assignments} == e["evidence"]["without_restating_premises"]["counterexample"]
    assert RC._evidence_faults(e) == []


def _write(tmp_path, doc) -> Path:
    p = tmp_path / "adj.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


@pytest.mark.parametrize("damage, why", [
    (lambda d: d.update(format="something-else/1.0"), "format"),
    (lambda d: d["entries"].append(copy.deepcopy(d["entries"][0])), "used twice"),
    (lambda d: d["entries"][0].pop("why_genuine"), "lacks"),
    (lambda d: d["entries"][0].update(code="OVS-NOPE-001"), "unknown code"),
    (lambda d: d["entries"][0]["evidence"]["without_restating_premises"].update(status="ENTAILED"), "does not reproduce"),
    (lambda d: d["entries"][0]["translation"]["problem"]["premises"].append(
        {"id": "a_more", "expr": {"op": "var", "name": "wc"}, "grounding": {"kind": "specialist_inference"}}), "does not reproduce"),
    (lambda d: d["entries"][0]["translation"].update(problem_sha256="0" * 64), "does not reproduce"),
])
def test_a_record_whose_entries_do_not_hold_is_refused(tmp_path, damage, why):
    doc = copy.deepcopy(RECORD)
    damage(doc)
    with pytest.raises(H.HarnessError, match=why):
        RC.load_adjudications(_write(tmp_path, doc))


def test_an_entry_adjudicating_a_redundant_restatement_is_refused(tmp_path):
    """Adjudicating bm-t13 g2.1 as circular would turn a redundant restatement into a 'genuine fault': refused, because
    without the restating premise the engine still gives ENTAILED."""
    from .test_corrections_trn_necessity import bm_problem
    doc = copy.deepcopy(RECORD)
    e = doc["entries"][0]
    p = bm_problem()
    from epinoic_logic.ir.canonical import problem_digest
    from epinoic_logic.ir.schema import Problem
    e.update(id="r7/bm-t13/g2.1/OVS-TRN-006", channel="bm-t13", task_id="bm-t13", claim_id="g2.1", agent_id="business-management-specialist")
    e["translation"] = {"source": "translations/bm-t13.json", "problem_sha256": problem_digest(Problem.model_validate(p)), "problem": p}
    e["evidence"] = {"restating_premises": ["d_contrib_val"], "as_recorded": {"status": "ENTAILED"}, "without_restating_premises": {"status": "ENTAILED"},
                     "how": "engine"}
    with pytest.raises(H.HarnessError, match="redundant restatement"):
        RC.load_adjudications(_write(tmp_path, doc))


# ============================================================================================ matching
def test_an_exact_match_names_the_round_channel_claim_code_and_agent():
    e = next(x for x in RECORD["entries"] if x["id"] == CS)
    assert RC.finding_matches_entry(e, "r7", "cs-t13", trn006())
    assert RC.finding_matches_entry(e, "r7", "cs-t13::invented_quotation", trn006())  # a fault variant of the same task
    assert not RC.finding_matches_entry(e, "r6", "cs-t13", trn006())                    # another round
    assert not RC.finding_matches_entry(e, "r7", "ess-t13", trn006())                   # another channel
    assert not RC.finding_matches_entry(e, "r7", "cs-t13", trn006("g11.2"))             # another claim
    assert not RC.finding_matches_entry(e, "r7", "cs-t13", trn006(claims=["g11.3", "g11.2"]))  # not the claim alone
    assert not RC.finding_matches_entry(e, "r7", "cs-t13", trn006(code="OVS-TRN-001"))  # another code
    assert not RC.finding_matches_entry(e, "r7", "cs-t13", trn006(agent="history-specialist"))  # another agent
    assert not RC.finding_matches_entry(e, "r7", "cs-t13", trn006(code="OVS-TRN-010"))  # a warning is never the adjudicated error


def test_genuine_errors_an_adjudicated_fault_is_raised_and_an_unadjudicated_error_is_a_false_alarm():
    a = adjudications()
    other = ovs_finding("OVS-FID-001", "claim g3.1 is not in the response", claim_ids=["g3.1"], message_ids=["m-1"], agent_ids=["computer-science-specialist"])
    warning = ovs_finding("OVS-TRN-005", "an untraced number", claim_ids=["g11.3"], message_ids=["m-1"], agent_ids=["computer-science-specialist"])
    false_alarms, raised = RC.classify_genuine_errors("r7", "cs-t13", [trn006(), other, warning], a)
    assert [x["entry"] for x in raised] == [CS]
    assert [(x["code"], x["claim_ids"]) for x in false_alarms] == [("OVS-FID-001", ["g3.1"])]  # the unadjudicated error still counts
    false_alarms, raised = RC.classify_genuine_errors("r7", "cs-t13", [trn006("g11.2")], a)  # the same code on another claim
    assert raised == [] and [x["claim_ids"] for x in false_alarms] == [["g11.2"]]
    false_alarms, raised = RC.classify_genuine_errors("r7", "cs-t13", [trn006()], None)  # no record: every error is a false alarm
    assert raised == [] and len(false_alarms) == 1


def test_mutation_errors_only_the_adjudicated_claim_s_error_is_no_disagreement():
    a = adjudications()
    other = ovs_finding("OVS-TRN-001", "invalid IR", claim_ids=["g2.1"], message_ids=["m-2"], agent_ids=["computer-science-specialist"])
    errors, adjudicated = RC.classify_mutation_errors("r7", "cs-t13::self_certification", [trn006(), other], a)
    assert adjudicated == [CS] and errors == ["OVS-TRN-001"]
    errors, adjudicated = RC.classify_mutation_errors("r7", "bm-t13::self_certification", [trn006()], a)  # another task's variant
    assert adjudicated == [] and errors == ["OVS-TRN-006"]


# ============================================================================================ the gates
def _round(*, raised=(), false_alarms=(), mutations=(), evidence=None, claims_findings=None) -> dict:
    return {"genuine": {"false_alarms": list(false_alarms), "adjudicated_raised": [{"entry": i, "channel": i.split("/")[1], "code": "OVS-TRN-006",
                                                                                     "claim_ids": [i.split("/")[2]], "message": ""} for i in raised],
                        "claims_findings": claims_findings or {}},
            "mutations": list(mutations), "replay": {"disagreements": [], "results_replayed": 1}, "arena_unchanged_by_the_auditor": True,
            "channels": [{"verifies": True}], "reviews": [{"system_text_is_the_pack": True, "probes": {"p": {"ok": True}}, "clearances_unchanged": True}],
            "adjudication_evidence": evidence or {}}


def _result(rounds: dict) -> dict:
    return {"rounds": rounds, "adjudications": adjudications(), "pack": {"source": "x"}}


def test_every_adjudicated_fault_raised_passes_and_no_false_alarm_counts_it():
    g = RC.gates(_result({"r7": _round(raised=[CS, ESS])}))
    assert g["adjudicated_genuine_faults_raised"]["ok"] and g["adjudicated_genuine_faults_raised"]["value"] == 2 == g["adjudicated_genuine_faults_raised"]["of"]
    assert g["no_false_alarm_on_genuine_transfers"]["ok"] and g["no_false_alarm_on_genuine_transfers"]["value"] == 0


def test_a_missing_adjudicated_fault_fails_the_run_and_says_what_the_genuine_channel_shows():
    g = RC.gates(_result({"r7": _round(raised=[CS], claims_findings={"ess-t13|g4.3": ["OVS-TRN-010 (warning)"]},
                                       evidence={ESS: "the round's recorded translation is the adjudicated IR"})}))
    gate = g["adjudicated_genuine_faults_raised"]
    assert not gate["ok"] and gate["value"] == 1 and gate["of"] == 2
    (m,) = gate["missing"]
    assert m["entry"] == ESS and m["genuine_channel_shows"] == ["OVS-TRN-010 (warning)"] and "adjudicated IR" in m["recorded_translation"]


def test_an_unadjudicated_error_on_a_genuine_transfer_fails_the_false_alarm_gate():
    fa = {"channel": "bm-t13", "code": "OVS-TRN-006", "claim_ids": ["g2.1"], "message": "circular"}
    g = RC.gates(_result({"r7": _round(raised=[CS, ESS], false_alarms=[fa])}))
    assert not g["no_false_alarm_on_genuine_transfers"]["ok"] and g["no_false_alarm_on_genuine_transfers"]["value"] == 1
    assert g["adjudicated_genuine_faults_raised"]["ok"]


def test_entries_of_rounds_not_run_are_listed_never_counted_raised():
    g = RC.gates(_result({"r3": _round()}))
    gate = g["adjudicated_genuine_faults_raised"]
    assert gate["ok"] and gate["of"] == 0 and set(gate["not_run"]) == {CS, ESS}


def test_with_no_round_the_adjudication_gate_is_not_measured():
    g = RC.gates({"rounds": {}, "adjudications": adjudications(), "pack": {}})
    assert not g["adjudicated_genuine_faults_raised"]["ok"] and "NOT MEASURED" in g["adjudicated_genuine_faults_raised"]["state"]


def test_a_variant_disagrees_only_through_unadjudicated_errors():
    agree = {"receipt_named_it": True, "overseer_agrees_with_receipt": True}
    disagree = {"receipt_named_it": True, "overseer_agrees_with_receipt": False}
    assert RC.gates(_result({"r7": _round(raised=[CS, ESS], mutations=[agree])}))["arena_faults_named_by_receipts_and_confirmed"]["ok"]
    assert not RC.gates(_result({"r7": _round(raised=[CS, ESS], mutations=[agree, disagree])}))["arena_faults_named_by_receipts_and_confirmed"]["ok"]


def test_the_recorded_translation_must_be_the_adjudicated_ir(tmp_path):
    e = next(x for x in RECORD["entries"] if x["id"] == CS)
    rnd = tmp_path / "r7"
    (rnd / "translations").mkdir(parents=True)
    (rnd / "translations" / "cs-t13.json").write_text(json.dumps({"report_id": "rep", "claims": {"g11.3": {"problem": e["translation"]["problem"]}}}))
    assert RC.recorded_translation_matches(rnd, e) is None
    other = copy.deepcopy(e["translation"]["problem"])
    other["premises"][0]["label"] = "something else"
    (rnd / "translations" / "cs-t13.json").write_text(json.dumps({"report_id": "rep", "claims": {"g11.3": {"problem": other}}}))
    assert "digest differs" in RC.recorded_translation_matches(rnd, e)
    assert "no recorded translation" in RC.recorded_translation_matches(tmp_path / "nowhere", e)
