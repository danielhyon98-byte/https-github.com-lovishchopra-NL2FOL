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

The translator merge (record version 2): the merged translator no longer delivers either adjudicated encoding (the
merged parsers issue other claim ids, the translator's own circularity gate rejects each recorded IR with E112, and
the engine withholds the verdict when it is delivered past the gate), so version 2 retires both entries, each with why
and the evidence of its retirement, which the harness re-derives before it accepts the record (a retirement the code no
longer supports refuses the record: the entry must be restored). The machinery tests below run on the version-1 record
rebuilt from the retired entries (which keep every field and the original evidence), exactly as before; the retirements
are pinned by the tests marked "version 2", which run on the version-2 record rebuilt from the shipped one.

The repair of the translator merge (record version 3, design decision 50): the overseer's rule grounded-transcription no
longer reads a grounding kind label as evidence, and r7's recorded translations are served to the merged claims on the
contained run's re-keyed pass, where the recorded proposal of ec-p7a g4.1 (served as g4.1@economics-specialist) is a
circular encoding the merged translator delivers as a success: version 3 adjudicates it, measured in that pass, with
evidence the harness re-derives from the recorded answer, its plan and the recorded proposal it embeds (the merged
parse, the pipeline's outcome, the overseer's rules, the engine). The two retirements embed the same sources, so the
merged parse (c7.3, s4.3) and the pipeline run on the recorded proposal are re-derived too, not read back from the JSON.

The second repair of the translator merge (record version 4): an adjudicated fault must be one the ENGINE shows (rule
engine-shown: the proof as recorded rests on premises restating the conclusion, at least one of them the writer's own,
and without the writer's-own ones the engine does not give ENTAILED). The version-3 entry did not meet it: rule
figure-transcription verifies T-q25 against the document supplied with the request, the only writer's-own restating
premise is C-g4.2, and without it the engine still gives ENTAILED (OVS-TRN-010). Version 4 retires it by a new kind of
retirement (``overseer_rules``: the corrected rules, re-derived, no longer read the encoding as circular; the replay must
give exactly OVS-TRN-010), and adjudicates the restatements of the task that rule grounded-transcription no longer reads
as transcriptions on a task_setting label alone (r7 lit-t13 p1-point in the genuine pass; mai-t13 m1.1 and m7.1 in the
re-keyed pass), each with evidence re-derived from its embedded sources. The version-3 record is rebuilt from the shipped
one and pinned as refused. The tests marked "version 3" ran on the shipped record (version 4), each asserting what it
asserted on version 3, on the version-4 re-keyed entry (m1.1) where it named the retired one.

The third repair of the translator merge (record version 5, design decision 55): rule figure-transcription is withdrawn
(no number match verifies a premise; the request can only refute one, rule same-quantity), and rule engine-shown, part two,
requires an adjudicated fault to rest on a restating premise a deterministic check SHOWS is not data (rule
data-standing). None of version 4's entries does: each result rests only on task_setting premises the translation
declares as task data and that no check verifies or refutes, so the engine shows only that a data conjunct needs its data
premise (the overseer grades each OVS-TRN-011, a warning). Version 5 retires all three by the overseer's rules, each
re-derived from its embedded sources, and re-derives p7a's retirement under the corrected rules (OVS-TRN-010 and
OVS-TRN-011). The version-4 record is rebuilt from the shipped one and pinned as refused; the version-4 entries are kept
for the tests of the entry machinery (the gate given them, the damages applied to the retired entry, which keeps every
field and its original evidence, re-derived before the record is accepted), each asserting what it asserted on version 4.

The fourth repair of the translator merge (record version 6, design decision 56): rule data-standing had read the Boolean
restating premises of those three entries as "undecided" on their kind labels alone (the translation declared them as
data throughout), which the review of the third repair found to be no evidence: p proves p under a label is the claim
assumed. The corrected rule shows them not to be data (uncheckable: no check reads a Boolean statement against the
request), so each entry's result rests on a premise shown not to be data and rule engine-shown grades it OVS-TRN-006.
Version 6 RESTORES the three entries with evidence re-derived from their embedded sources, keeping each one's version-5
retirement and its version-4 evidence (``superseded_retirement``, ``superseded_evidence``); the harness re-derives each
superseded retirement and requires that it no longer holds for that reason. The version-4 and version-5 records are
rebuilt from the shipped one and pinned as refused; the tests marked "version 3" to "version 5" keep every assertion on
the data they read (the version-4 entries as the gate saw them, the version-5 retirements as recorded) and assert on the
shipped record (version 6) what it now holds.
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

RECORD = json.loads(RC.ADJUDICATIONS_FILE.read_text(encoding="utf-8"))  # the shipped record (version 6)
CS = "r7/cs-t13/g11.3/OVS-TRN-006"
ESS = "r7/ess-t13/g4.3/OVS-TRN-006"
P7A = "r7/p7a/g4.1@economics-specialist/OVS-TRN-006"
LIT = "r7/lit-t13/p1-point/OVS-TRN-006"
M11 = "r7/mai-t13/m1.1/OVS-TRN-006"
M71 = "r7/mai-t13/m7.1/OVS-TRN-006"
_RETIREMENT = ("retired_in_version", "why_retired", "retirement_evidence")


def _retired_in(version: int) -> list[dict]:
    return [e for e in RECORD["retired"] if e["retired_in_version"] == version]


#: The version-1 record (the two adjudicated entries), rebuilt from the entries the shipped record retired in version 2,
#: which keep every field and the original evidence: the adjudication machinery is pinned on it exactly as before the merge.
V1 = {**{k: v for k, v in RECORD.items() if k not in ("entries", "retired", "changes")}, "version": 1,
      "entries": [{k: v for k, v in e.items() if k not in _RETIREMENT} for e in _retired_in(2)]}
#: The version-2 record (no entry, the two retirements), rebuilt from the shipped record: the version-2 tests run on it
#: exactly as they ran on the shipped version 2 (the retirements are the shipped ones, which also embed their sources).
V2 = {**{k: v for k, v in RECORD.items() if k not in ("entries", "retired", "changes")}, "version": 2, "entries": [],
      "retired": _retired_in(2), "changes": [c for c in RECORD["changes"] if c["version"] <= 2]}
#: The version-3 record (the entry r7/p7a/g4.1@economics-specialist, the two retirements), rebuilt from the shipped record
#: (the entry is the one version 4 retired, with every field and its original evidence): the corrected harness refuses it.
V3 = {**{k: v for k, v in RECORD.items() if k not in ("entries", "retired", "changes")}, "version": 3,
      "entries": [{k: v for k, v in e.items() if k not in _RETIREMENT} for e in _retired_in(4)], "retired": _retired_in(2),
      "changes": [c for c in RECORD["changes"] if c["version"] <= 3]}
#: The version-4 record (the entries r7/lit-t13/p1-point, r7/mai-t13/m1.1 and r7/mai-t13/m7.1 beside the retirements of
#: versions 2 and 4), rebuilt from the shipped record (the entries are the ones version 5 retired, with every field and their
#: original evidence): the corrected harness refuses it (rule engine-shown, part two).
def _restored_in(version: int) -> list[dict]:
    return [e for e in RECORD["entries"] if e.get("restored_in_version") == version]


def _as_in_version_4(e: dict) -> dict:
    """A restored entry as version 4 held it: its fields, with the evidence it carried then (``superseded_evidence``)."""
    old = e["superseded_evidence"]
    assert old["version"] == 4
    return {**{k: v for k, v in e.items() if k not in RC._RESTORED_FIELDS}, "evidence": old["evidence"], "why_genuine": old["why_genuine"]}


#: The version-4 record (the entries r7/lit-t13/p1-point, r7/mai-t13/m1.1 and r7/mai-t13/m7.1 beside the retirements of
#: versions 2 and 4), rebuilt from the shipped record: version 5 retired the three entries and version 6 restored them,
#: keeping the evidence version 4 gave each (``superseded_evidence``), so they are rebuilt from that (every field and their
#: original evidence). The corrected harness refuses it.
V4 = {**{k: v for k, v in RECORD.items() if k not in ("entries", "retired", "changes")}, "version": 4,
      "entries": [_as_in_version_4(e) for e in _restored_in(6)], "retired": _retired_in(2) + _retired_in(4),
      "changes": [c for c in RECORD["changes"] if c["version"] <= 4]}
#: The version-5 record (no entry; the retirements of versions 2 and 4 and the three of version 5), rebuilt from the
#: shipped record (the version-5 retirements as the restored entries keep them, ``superseded_retirement``, each with the
#: evidence its entry carried then): the corrected harness refuses it, each of its version-5 retirements no longer holding.
V5 = {**{k: v for k, v in RECORD.items() if k not in ("entries", "retired", "changes")}, "version": 5, "entries": [],
      "retired": _retired_in(2) + _retired_in(4) + [RC._superseded_as_retired(e) for e in _restored_in(6)],
      "changes": [c for c in RECORD["changes"] if c["version"] <= 5]}
_V1: dict = {}


@pytest.fixture(scope="module", autouse=True)
def _v1_record(tmp_path_factory):
    d = tmp_path_factory.mktemp("adjudications")
    p = d / "adjudicated_genuine_faults_v1.json"
    p.write_text(json.dumps(V1), encoding="utf-8")
    _V1["path"] = p
    p2 = d / "adjudicated_genuine_faults_v2.json"
    p2.write_text(json.dumps(V2), encoding="utf-8")
    _V1["v2"] = p2
    yield


def adjudications() -> dict:
    """The version-1 record as the harness loads it (format, fields, ids and every entry's engine evidence checked)."""
    return RC.load_adjudications(_V1["path"])


def trn006(claim: str = "g11.3", agent: str = "computer-science-specialist", *, claims=None, code: str = "OVS-TRN-006"):
    return ovs_finding(code, f"circular translation of claim {claim}", claim_ids=claims if claims is not None else [claim], message_ids=["m-1"],
                       report_ids=["rep-cs-t13-0"], agent_ids=[agent])


# ============================================================================================ the record
def test_the_record_adjudicates_exactly_the_two_engine_confirmed_circular_translations_and_not_bm_t13():
    a = adjudications()  # version 1, rebuilt from the retired entries
    assert a["format"] == "overseer-adjudicated-genuine-faults/1.0" and isinstance(a["version"], int)
    assert [(e["round"], e["channel"], e["claim_id"], e["code"], e["agent_id"]) for e in a["entries"]] == [
        ("r7", "cs-t13", "g11.3", "OVS-TRN-006", "computer-science-specialist"), ("r7", "ess-t13", "g4.3", "OVS-TRN-006", "ess-specialist")]
    assert not any(e["channel"] == "bm-t13" for e in a["entries"])  # redundant restatement: OVS-TRN-010, a warning, never adjudicated
    assert any("bm-t13 g2.1" in r for r in RECORD["rules"])
    for e in a["entries"]:
        assert e["why_genuine"] and e["evidence"]["how"] and e["evidence"]["without_restating_premises"]["status"] == "COUNTEREXAMPLE"


# ============================================================================================ version 2: the retirements
def test_version_2_retires_both_entries_with_evidence_the_harness_re_derives_and_adjudicates_none():
    # the version-2 record rebuilt from the shipped version 3 (every assertion as before; refused unless every retirement reproduces)
    a = RC.load_adjudications(_V1["v2"])
    assert a["version"] == 2 and a["entries"] == [] and [x["id"] for x in a["retired"]] == [CS, ESS]
    assert all(x["retired_in_version"] == 2 and "no longer delivers" in x["why_retired"] and "E112" in x["why_retired"] for x in a["retired"])
    assert not any(e["channel"] == "bm-t13" for e in RECORD["retired"]) and any("bm-t13 g2.1" in r for r in RECORD["rules"])
    merged = {e["id"]: e["retirement_evidence"] for e in V2["retired"]}
    assert merged[CS]["merged_parse"]["claim_id"] == "c7.3" and merged[ESS]["merged_parse"]["claim_id"] == "s4.3"
    assert merged[CS]["pipeline_on_the_recorded_proposal"]["translation_status"] == "INVALID_FORMALIZATION"
    assert merged[ESS]["pipeline_on_the_recorded_proposal"]["translation_status"] == "NOT_ELIGIBLE"
    for e in V2["retired"]:  # the version-2 retirements (version 4 states their kind, translator_withholds, and changes nothing else)
        ev = e["retirement_evidence"]
        assert ev["kind"] == "translator_withholds"
        assert ev["translator_rule"]["every_named_premise_is_the_writers_own"] and ev["pipeline_gate"] == {"status": "INVALID_FORMALIZATION", "diagnostic": "E112"}
        assert ev["engine_on_the_recorded_ir"]["status"] == "ENTAILED" and "E112" in ev["engine_on_the_recorded_ir"]["diagnostics"]
        assert not ev["pipeline_on_the_recorded_proposal"]["problem_delivered"] and not ev["pipeline_on_the_recorded_proposal"]["engine_run"]
        assert RC._evidence_faults(e) == [] and RC._retirement_faults(e) == []  # the original evidence and the retirement both reproduce
    # nothing but the retirement fields was added: the version-1 entries are the ones retired in version 2
    assert [{k: v for k, v in e.items() if k not in _RETIREMENT} for e in V2["retired"]] == V1["entries"]


@pytest.mark.parametrize("damage, why", [
    (lambda d: d["retired"][0].pop("why_retired"), "lacks"),
    (lambda d: d["retired"][0].update(retired_in_version=3), "names a version"),
    (lambda d: d["entries"].append({k: v for k, v in copy.deepcopy(d["retired"][0]).items() if k not in _RETIREMENT}), "used twice"),
    (lambda d: d["retired"][0]["evidence"]["without_restating_premises"].update(status="ENTAILED"), "does not reproduce"),
    (lambda d: d.update(retired={"not": "a list"}), "not a list"),
])
def test_version_2_a_record_whose_retirements_do_not_hold_is_refused(tmp_path, damage, why):
    doc = copy.deepcopy(V2)  # the version-2 record rebuilt from the shipped one (a retirement may name no later version)
    damage(doc)
    with pytest.raises(H.HarnessError, match=why):
        RC.load_adjudications(_write(tmp_path, doc))


@pytest.mark.parametrize("kind", ["task_setting", "rubric_rule"])
def test_version_2_a_retirement_the_translator_no_longer_supports_refuses_the_record(tmp_path, kind):
    """A retired encoding the translator would deliver again (its restating premise grounded in the task, or under another
    label the translator's own rule reads as a transcription, so that rule does not hold and its gate passes it) refuses
    the record: the entry must be restored. Record version 5 (rule data-standing): on the original input, a task_setting
    premise with no excerpt in an entry that embeds no request, the entry's evidence no longer certifies a fault either (the
    standing of that premise needs the request), and the loader names both; under ``rubric_rule`` (a source no check reads:
    shown not to be data without the request) the original evidence still reproduces, as the test asserted before."""
    from epinoic_logic.ir.canonical import problem_digest
    from epinoic_logic.ir.schema import Problem
    doc = copy.deepcopy(V2)
    e = doc["retired"][0]
    prob = e["translation"]["problem"]
    prob["premises"][0]["grounding"] = {"kind": kind, "source_refs": [], "certainty": "established"}
    e["translation"]["problem_sha256"] = problem_digest(Problem.model_validate(prob))
    if kind == "task_setting":
        assert RC._evidence_faults(e) == ["the restating premise(s) ['a_wc'] name the request as their source, so the entry must embed its sources to "
                                          "re-derive their standing (rule data-standing)"]
    else:
        assert RC._evidence_faults(e) == []  # the original evidence still reproduces (ENTAILED; COUNTEREXAMPLE without the premise)
    assert "no longer holds" in "; ".join(RC._retirement_faults(e)) and "would deliver" in "; ".join(RC._retirement_faults(e))
    with pytest.raises(H.HarnessError, match="restore the entry"):
        RC.load_adjudications(_write(tmp_path, doc))


def test_version_2_the_gate_lists_the_retired_entries_and_counts_none_as_raised():
    a = RC.load_adjudications(_V1["v2"])
    gate = RC.adjudication_gate({"rounds": {"r7": _round()}, "adjudications": a})
    assert gate["ok"] and gate["of"] == 0 and gate["value"] == 0 and gate["missing"] == [] and gate["retired"] == [CS, ESS] and gate["record_version"] == 2
    false_alarms, raised = RC.classify_genuine_errors("r7", "cs-t13", [trn006()], a)  # a retired entry never absorbs an error
    assert raised == [] and len(false_alarms) == 1


@pytest.mark.parametrize("entry_id", [CS, ESS])
def test_each_entry_s_evidence_reproduces_with_the_engine(entry_id):
    e = next(x for x in V1["entries"] if x["id"] == entry_id)
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
    doc = copy.deepcopy(V1)
    damage(doc)
    with pytest.raises(H.HarnessError, match=why):
        RC.load_adjudications(_write(tmp_path, doc))


def test_an_entry_adjudicating_a_redundant_restatement_is_refused(tmp_path):
    """Adjudicating bm-t13 g2.1 as circular would turn a redundant restatement into a 'genuine fault': refused, because
    without the restating premise the engine still gives ENTAILED."""
    from .test_corrections_trn_necessity import bm_problem
    doc = copy.deepcopy(V1)
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
    e = next(x for x in V1["entries"] if x["id"] == CS)
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
    e = next(x for x in V1["entries"] if x["id"] == CS)
    rnd = tmp_path / "r7"
    (rnd / "translations").mkdir(parents=True)
    (rnd / "translations" / "cs-t13.json").write_text(json.dumps({"report_id": "rep", "claims": {"g11.3": {"problem": e["translation"]["problem"]}}}))
    assert RC.recorded_translation_matches(rnd, e) is None
    other = copy.deepcopy(e["translation"]["problem"])
    other["premises"][0]["label"] = "something else"
    (rnd / "translations" / "cs-t13.json").write_text(json.dumps({"report_id": "rep", "claims": {"g11.3": {"problem": other}}}))
    assert "digest differs" in RC.recorded_translation_matches(rnd, e)
    assert "no recorded translation" in RC.recorded_translation_matches(tmp_path / "nowhere", e)


# ============================================================================================ version 3: the repair of the translator merge
def _entry(entry_id: str) -> dict:
    """A version-4 entry, as version 6 keeps it (every field and its original evidence, ``superseded_evidence``)."""
    return next(e for e in V4["entries"] if e["id"] == entry_id)


def _retired(entry_id: str) -> dict:
    """A retired entry of the shipped record, or a version-5 retirement as the restored entry keeps it."""
    return next(e for e in RECORD["retired"] + V5["retired"] if e["id"] == entry_id)


def _restored(entry_id: str) -> dict:
    return next(e for e in RECORD["entries"] if e["id"] == entry_id)


def test_version_3_the_record_version_3_is_refused_its_entry_is_not_one_the_engine_shows(tmp_path):
    """The second repair of the translator merge (finding (c) of its independent test): version 3 adjudicated
    r7/p7a/g4.1@economics-specialist as circular, but the engine does not show it. The second repair read T-q25 as a
    transcription (rule figure-transcription); record version 5 (the third repair) withdrew that rule, so T-q25 is
    undecided data and C-g4.2 the only restating premise a check shows is not data, and without C-g4.2 the engine still
    gives ENTAILED relying on T-q25 (rule engine-shown, part two). The corrected harness refuses the version-3 record,
    rebuilt from the shipped one, for that reason; versions 4 and 5 retire the entry (below)."""
    e = V3["entries"][0]
    assert e["id"] == P7A and e["evidence"]["restating_premises"] == ["T-q25", "C-g4.2"]
    faults = "; ".join(RC._evidence_faults(e))
    # record version 5 (rule same-quantity withdrew figure-transcription): T-q25 is no transcription but undecided data, so
    # the rules name both restating premises the writer's own as the entry did; the entry is refused because only C-g4.2 is
    # SHOWN not to be data, and without it the engine still gives ENTAILED (it was refused in version 4 for the reading)
    assert ("rule engine-shown grades the restatement ['OVS-TRN-010', 'OVS-TRN-011'], not OVS-TRN-006: the run without the shown premises ['C-g4.2'] "
            "(keeping ['T-q25']) gives ENTAILED") in faults
    with pytest.raises(H.HarnessError, match="does not reproduce"):
        RC.load_adjudications(_write(tmp_path, V3))
    # and with the reading the corrected rules give (both the writer's own; C-g4.2 shown, T-q25 undecided) it is still no
    # fault the engine shows: without C-g4.2 the engine still gives ENTAILED, relying on T-q25 alone
    rules = _retired(P7A)["retirement_evidence"]["overseer_rules"]
    corrected = copy.deepcopy(e)
    corrected["evidence"].update(restating_premises=rules["own"], transcriptions=rules["transcriptions"], why_own=rules["why_own"],
                                 shown_premises=rules["shown"], undecided_premises=rules["undecided"], without_shown_premises={"status": "ENTAILED"})
    faults = RC._evidence_faults(corrected)
    assert faults == ["rule engine-shown grades the restatement ['OVS-TRN-010', 'OVS-TRN-011'], not OVS-TRN-006: the run without the shown premises "
                      "['C-g4.2'] (keeping ['T-q25']) gives ENTAILED, so the result does not rest on a premise shown not to be data"]


def test_version_6_restores_the_task_restatements_version_5_retired_with_evidence_the_harness_re_derives():
    """Rewritten from ``test_version_5_retires_the_task_restatements_version_4_adjudicated_with_evidence_the_harness_re_derives``
    (record version 6, the fourth repair of the translator merge, decision 56). Every assertion that test made on the
    version-5 retirements and on the version-4 evidence they kept is made on them as the restored entries keep them
    (``superseded_retirement``, ``superseded_evidence``): the parse issues the recorded claim under the entry's id; the
    translator's real pipeline delivers the recorded proposal with an engine run (TRANSLATED and displayed ENTAILED for
    m1.1 and m7.1; AMBIGUOUS_TRANSLATION for p1-point) because its own rule reads the restating premises' task_setting
    labels as transcriptions; version 4's reading of the overseer's rules is the one recorded; the engine's proof rests on
    the restating premises alone, and without them it gives COUNTEREXAMPLE; that evidence still reproduces but for the
    superseded reading of the standings; and the recorded retirement reads every restating premise undecided and grades the
    restatement OVS-TRN-011. Two assertions pinned the fault the review of the third repair found and are reversed: the
    retirement no longer reproduces (the corrected rules show the Boolean premises are not data, and rule engine-shown
    grades the restatement OVS-TRN-006: the entry must be restored), and the entry is no longer refused (restored, its
    evidence re-derived from the same sources, it reproduces; its version-4 evidence alone is still refused)."""
    a = RC.load_adjudications()
    assert a["version"] == 6 and [x["id"] for x in a["entries"]] == [LIT, M11, M71] and [x["id"] for x in a["retired"]] == [CS, ESS, P7A]
    m11 = _retired(M11)  # the version-5 retirement, as the restored entry keeps it (every field and its original evidence)
    assert (m11["round"], m11["pass"], m11["channel"], m11["task_id"], m11["agent_id"], m11["claim_id"], m11["recorded_claim_id"], m11["code"]) == (
        "r7", "rekeyed", "mai-t13", "mai-t13", "mathematics-ai-specialist", "m1.1", "g2.1", "OVS-TRN-006")
    ev = m11["evidence"]  # the original evidence (version 4's reading of the overseer's rules, as recorded)
    assert ev["restating_premises"] == ["t_comp", "t_wants_value", "t_wants_euro"] and ev["transcriptions"] == ["t_years", "t_rate_pct"]
    assert set(ev["why_own"]) == {"t_comp", "t_wants_value", "t_wants_euro"} and all("not verified" in why for why in ev["why_own"].values())
    assert "figure-transcription" in ev["why_own"]["t_comp"] and "states more than figures" in ev["why_own"]["t_wants_value"]
    assert ev["translator_rule"] == {"circular_premises": ["t_years", "t_comp", "t_rate_pct", "t_wants_value", "t_wants_euro"],
                                     "every_named_premise_is_the_writers_own": False}
    assert ev["pipeline_on_the_recorded_proposal"] == {"claim_id": "m1.1", "translation_status": "TRANSLATED", "problem_delivered": True, "engine_run": True,
                                                       "display_status": "ENTAILED", "result_status": "ENTAILED", "result_diagnostics": []}
    assert all(ev["grounding_checks"][pid]["method"] == "not_checkable" and ev["grounding_checks"][pid]["verified"] is None for pid in ev["restating_premises"])
    assert ev["as_recorded"] == {"status": "ENTAILED", "premises_relied_on": ["t_years", "t_comp", "t_rate_pct", "t_wants_value", "t_wants_euro"]}
    assert ev["without_restating_premises"]["status"] == "COUNTEREXAMPLE"
    shown_of = {LIT: (["A_p1_point"], []), M11: (["t_wants_value", "t_wants_euro"], ["t_years", "t_comp", "t_rate_pct"]), M71: (["t_whole"], ["t_threshold"])}
    for entry_id in (LIT, M11, M71):
        e = _retired(entry_id)
        ev = e["evidence"]
        prob = e["translation"]["problem"]
        reduced = {**prob, "premises": [p for p in prob["premises"] if p["id"] not in ev["restating_premises"]]}
        r = verify(canonical_json(reduced), SolverConfig())
        assert r.status.value == "COUNTEREXAMPLE" and {x.symbol: x.value for x in r.counterexample.assignments} == ev["without_restating_premises"]["counterexample"]
        core = set(ev["as_recorded"]["premises_relied_on"])
        assert core <= set(ev["restating_premises"]) | set(ev["transcriptions"]) and core & set(ev["restating_premises"])  # rule engine-shown, part one
        # the original evidence reproduces but for the superseded reading of the standings
        assert RC._evidence_faults(e, rules_superseded=True) == [] and RC._same_sources_faults(e) == []
        rev = e["retirement_evidence"]
        rules = rev["overseer_rules"]
        assert e["retired_in_version"] == 5 and rev["kind"] == "overseer_rules" and rev["pass"] == e["pass"]
        assert rules["transcriptions"] == [] and rules["shown"] == [] and rules["undecided"] == rules["own"] and set(rules["standings"].values()) == {"undecided"}
        assert sorted(rules["own"]) == sorted(set(ev["restating_premises"]) | set(ev["transcriptions"]))  # the same premises restate the conclusion
        assert rev["grade"] == [["OVS-TRN-011", rules["own"], rules["own"]]] and rev["expected_findings_on_replay"] == ["OVS-TRN-011"]
        assert {x["status"] for x in rev["engine_runs"]} == {"COUNTEREXAMPLE"}
        # reversed (the fault the review found): the version-5 retirement no longer reproduces; the corrected rules grade the
        # restatement OVS-TRN-006, so the entry must be restored
        rf = "; ".join(RC._retirement_faults(e))
        assert "rule engine-shown grades the restatement OVS-TRN-006" in rf and "the entry must be restored" in rf, rf
        # restored: the entry's evidence, re-derived from the same sources, reproduces, and so does its restoration
        restored = _restored(entry_id)
        rv = restored["evidence"]
        assert restored["restored_in_version"] == 6 and restored["superseded_retirement"]["retired_in_version"] == 5 and restored["superseded_evidence"]["version"] == 4
        assert RC._evidence_faults(restored) == [] and RC._restoration_faults(restored, 6) == []
        assert (rv["shown_premises"], rv["undecided_premises"]) == shown_of[entry_id]
        assert {rv["standings"][pid] for pid in rv["shown_premises"]} == {"uncheckable"} and all("Boolean content" in rv["why_own"][pid] for pid in rv["shown_premises"])
        assert all(rv["standings"][pid] == "undecided" for pid in rv["undecided_premises"])
        assert rv["without_shown_premises"]["status"] == "COUNTEREXAMPLE" and rv["grade"] == [["OVS-TRN-006", rv["shown_premises"], rv["shown_premises"]]]
        assert all(rv[f] == ev[f] and rv[f + "_sha256"] == ev[f + "_sha256"] for f in ("recorded_answer", "recorded_plan", "recorded_proposal"))
        # as version 4 recorded it, the entry is still refused: its evidence states a reading the corrected rules do not give
        as_v4 = "; ".join(RC._evidence_faults(_as_in_version_4(restored)))
        assert "the record does not state which restating premises a check shows are not data" in as_v4, as_v4
    lit = _retired(LIT)
    assert lit["pass"] == "genuine" and lit["evidence"]["pipeline_on_the_recorded_proposal"]["display_status"] == "AMBIGUOUS_TRANSLATION"
    assert lit["evidence"]["restating_premises"] == ["A_p1_point"] and lit["evidence"]["as_recorded"]["premises_relied_on"] == ["A_p1_point"]
    # "compounded monthly" states 12 periods a year (rule frequency-words): t_comp is undecided, not refuted as a figure stated nowhere
    assert "stated nowhere" not in _retired(M11)["retirement_evidence"]["overseer_rules"]["why_own"]["t_comp"]
    assert _restored(M11)["evidence"]["standings"]["t_comp"] == "undecided" and "stated nowhere" not in _restored(M11)["evidence"]["why_own"]["t_comp"]


def test_version_6_a_restoration_the_harness_cannot_re_derive_is_refused(tmp_path):
    """Record version 6: an entry is restored only with evidence. A restored entry that drops its superseded retirement,
    names a version the record is not, or keeps a retirement embedding other sources than its evidence is refused; and so
    is a restoration whose superseded retirement still holds (the entry stays retired: here the p7a retirement, which the
    corrected rules still uphold, presented as superseded)."""
    for damage, why in ((lambda e: e.pop("superseded_retirement"), "lacks superseded_retirement"),
                        (lambda e: e.update(restored_in_version=7), "names a version this record is not"),
                        (lambda e: e["superseded_retirement"].update(retired_in_version=6), "no version before the restoration")):
        doc = copy.deepcopy(RECORD)
        damage(next(x for x in doc["entries"] if x["id"] == M71))
        with pytest.raises(H.HarnessError, match=why):
            RC.load_adjudications(_write(tmp_path, doc))
    doc = copy.deepcopy(RECORD)
    sup = next(x for x in doc["entries"] if x["id"] == M71)["superseded_retirement"]["retirement_evidence"]
    sup["recorded_answer"]["question"] = sup["recorded_answer"]["question"] + " "
    _rehash(sup, "recorded_answer")
    with pytest.raises(H.HarnessError, match="does not reproduce"):
        RC.load_adjudications(_write(tmp_path, doc))
    p7a = copy.deepcopy(_retired(P7A))
    holding = {**{k: v for k, v in p7a.items() if k not in _RETIREMENT}, "restored_in_version": 6, "why_restored": "x",
               "superseded_retirement": {k: p7a[k] for k in _RETIREMENT}, "superseded_evidence": {"version": 3, "evidence": p7a["evidence"], "why_genuine": "x"}}
    assert RC._retirement_faults(RC._superseded_as_retired(holding)) == []  # that retirement still holds
    assert any("it still reproduces, so the entry stays retired" in f for f in RC._restoration_faults(holding, 6))


def test_version_6_the_records_versions_4_and_5_are_refused(tmp_path):
    """Rewritten from ``test_version_5_the_record_version_4_is_refused_its_entries_are_not_faults_the_engine_shows``:
    the corrected harness still refuses the version-4 record, rebuilt from the shipped one (the same assertion), and names
    for each entry why: its evidence states the second repair's reading of the overseer's rules (rule
    figure-transcription's reasons, and for m1.1 and m7.1 figure premises read as transcriptions), not the corrected
    rules', and it does not state which premises a check shows are not data. (The test asserted the third repair's
    reason, that no premise was shown not to be data, which decision 56 withdrew: each entry's Boolean premises are.) The
    version-5 record, rebuilt the same way, is refused too: each of its version-5 retirements no longer holds."""
    for e in V4["entries"]:
        faults = "; ".join(RC._evidence_faults(e))
        assert "the reasons the overseer's rule gives are not the record's" in faults, faults
        assert "the record does not state which restating premises a check shows are not data" in faults, faults
    with pytest.raises(H.HarnessError, match="does not reproduce"):
        RC.load_adjudications(_write(tmp_path, V4))
    with pytest.raises(H.HarnessError, match="grades the restatement OVS-TRN-006.*restore the entry"):
        RC.load_adjudications(_write(tmp_path, V5))


def _v3_damaged(tmp_path, damage) -> Path:
    doc = copy.deepcopy(RECORD)
    damage(doc)
    return _write(tmp_path, doc)


def _rehash(src: dict, field: str) -> None:
    from epinoic_logic.ir.canonical import sha256_hex
    src[field + "_sha256"] = sha256_hex(RC.canonical_json_of(src[field]))


def _m11(doc) -> dict:
    """The entry m1.1 of ``doc``: an entry of version 4, retired (with every field and its original evidence) in version 5,
    restored in version 6 (its evidence re-derived from the same sources; its retirement and its version-4 evidence kept)."""
    return next(e for e in doc["entries"] + doc["retired"] if e["id"] == M11)


def _answer_with_text(doc, new_text):
    ev = _m11(doc)["evidence"]
    ev["recorded_answer"]["response_text"] = new_text
    _rehash(ev, "recorded_answer")


def _question_stating_twelve(doc):
    """The recorded question restated with "12 times a year" for "monthly" in the entry's evidence: version 4 refused it
    because rule figure-transcription then verified t_comp (comp = 12); in version 5 (that rule withdrawn) it is refused
    because the retirement no longer embeds the sources the entry's evidence embeds (a retirement re-derived from other
    sources says nothing of the entry); in version 6 because the superseded retirement no longer embeds them (and the
    reasons the rules give change)."""
    ev = _m11(doc)["evidence"]
    q = ev["recorded_answer"]["question"]
    assert "monthly" in q
    ev["recorded_answer"]["question"] = q.replace("monthly", "monthly (12 times a year)", 1)
    _rehash(ev, "recorded_answer")


@pytest.mark.parametrize("damage, why", [
    (lambda d: _m11(d).pop("recorded_claim_id"), "lacks"),
    (lambda d: _m11(d)["evidence"].pop("recorded_plan"), "lacks"),
    (lambda d: _m11(d).update({"pass": "elsewhere"}), "names a pass"),
    (lambda d: _m11(d)["evidence"]["recorded_answer"].update(response_text="changed"), "SHA-256"),
    (lambda d: _answer_with_text(d, _m11(d)["evidence"]["recorded_answer"]["response_text"].replace("to the nearest euro.", "to the nearest cent.", 1)),
     "does not reproduce"),
    (lambda d: _m11(d)["evidence"].update(restating_premises=["t_wants_value", "t_wants_euro"]), "does not reproduce"),
    (lambda d: _m11(d)["evidence"]["pipeline_on_the_recorded_proposal"].update(display_status="INVALID_FORMALIZATION"), "does not reproduce"),
    (lambda d: _m11(d)["evidence"]["translator_rule"].update(every_named_premise_is_the_writers_own=True), "does not reproduce"),
    (lambda d: _m11(d).update(claim_id="g2.1"), "does not reproduce"),
    (_question_stating_twelve, "does not reproduce"),
    # rule engine-shown (record version 4): the core the record states, and the transcriptions, are re-derived too
    (lambda d: _m11(d)["evidence"]["as_recorded"].update(premises_relied_on=["t_comp"]), "does not reproduce"),
    (lambda d: _m11(d)["evidence"].update(transcriptions=["t_years"]), "does not reproduce"),
])
def test_version_3_an_entry_whose_re_derived_evidence_does_not_hold_is_refused(tmp_path, damage, why):
    """Each damage is applied to the entry m1.1 as the shipped record keeps it (version 5: retired, with its fields and its
    original evidence; version 6: restored, its evidence re-derived): everything is re-derived before the record is
    accepted (its pass and the fields a re-keyed entry needs, the core of the proof as recorded, the premises restating
    the conclusion and the translator's own rule, the sources it and its superseded retirement embed); every damage
    refuses the record."""
    assert _m11(RECORD)["restored_in_version"] == 6
    with pytest.raises(H.HarnessError, match=why):
        RC.load_adjudications(_v3_damaged(tmp_path, damage))


def test_version_4_an_entry_whose_proof_does_not_rest_on_the_restatement_is_refused(tmp_path):
    """Rule engine-shown: an entry whose proof as recorded rests on a premise that restates nothing (here the genuine
    link of the synthetic point beside the writer's restatement) is no fault the engine shows, even when removing the
    restating premise breaks the proof."""
    from epinoic_logic.ir.canonical import problem_digest
    from epinoic_logic.ir.schema import Problem
    doc = copy.deepcopy(V1)
    e = doc["entries"][0]
    prob = e["translation"]["problem"]
    prob["symbols"].append({"name": "wc_link", "sort": "Bool"})
    prob["premises"] = [{"id": "a_wc", "expr": {"op": "var", "name": "wc_link"}, "grounding": {"kind": "specialist_inference"}},
                        {"id": "l_wc", "expr": {"op": "implies", "left": {"op": "var", "name": "wc_link"}, "right": {"op": "var", "name": "wc"}},
                         "grounding": {"kind": "specialist_inference"}}]
    e["translation"]["problem_sha256"] = problem_digest(Problem.model_validate(prob))
    e["evidence"]["restating_premises"] = []
    with pytest.raises(H.HarnessError, match="does not reproduce"):
        RC.load_adjudications(_write(tmp_path, doc))


def _retired_proposal_delivered(doc):
    """The retired cs-t13 proposal with its restating premise grounded task_setting: the merged pipeline now delivers it."""
    ev = doc["retired"][0]["retirement_evidence"]
    for prem in ev["recorded_proposal"]["problem"]["premises"]:
        prem["grounding"] = {"kind": "task_setting", "source_refs": [], "certainty": "established"}
    _rehash(ev, "recorded_proposal")


@pytest.mark.parametrize("damage, why", [
    (lambda d: d["retired"][0]["retirement_evidence"]["merged_parse"].update(claim_id="c7.4"), "merged parse"),
    (lambda d: d["retired"][1]["retirement_evidence"]["merged_parse"].update(eligible=True), "merged parse"),
    (lambda d: d["retired"][0]["retirement_evidence"]["pipeline_on_the_recorded_proposal"].update(translation_status="TRANSLATED"), "pipeline on the recorded proposal"),
    (lambda d: d["retired"][1]["retirement_evidence"].pop("recorded_answer"), "cannot be re-derived"),
    (_retired_proposal_delivered, "restore the entry"),
])
def test_version_3_a_retirement_whose_merged_parse_or_pipeline_run_does_not_reproduce_is_refused(tmp_path, damage, why):
    """Finding (c) of the independent test: the merged parse ids (c7.3, s4.3) and the pipeline run on the recorded
    proposal were read back from the JSON, never re-derived. They are re-derived now, from the sources the retirement
    embeds, before the record is accepted (on the shipped record, version 4)."""
    with pytest.raises(H.HarnessError, match=why):
        RC.load_adjudications(_v3_damaged(tmp_path, damage))


# ============================================================================================ version 4: a retirement by the overseer's rules
def test_version_4_retires_the_p7a_entry_by_the_overseer_s_corrected_rules_with_evidence_the_harness_re_derives():
    """The retirement re-derives, from the sources it embeds: the merged parse (g4.1 issued as g4.1@economics-specialist)
    and the pipeline's run (delivered, ENTAILED); the overseer's corrected rules; and the engine without C-g4.2 (ENTAILED
    relying on T-q25 alone): never OVS-TRN-006 on the replay. The entry's original evidence still reproduces apart from the
    overseer reading the retirement supersedes. Record version 5 (the third repair) re-derives it under rule same-quantity:
    T-q25 is no transcription (rule figure-transcription withdrawn) but undecided data the receipt lists among the result's
    unverified dependencies, C-g4.2 alone is shown not to be data, and rule engine-shown gives OVS-TRN-010 for C-g4.2 (as
    in version 4) and OVS-TRN-011 for T-q25, on which the result then rests. Version 4's reading is kept, as recorded,
    under ``retirement_evidence_v4``: every assertion the test made on it holds there."""
    x = _retired(P7A)
    ev, v4 = x["retirement_evidence"], x["retirement_evidence_v4"]
    assert x["retired_in_version"] == 4 and ev["kind"] == "overseer_rules" and "figure-transcription" in x["why_retired"]
    assert v4["overseer_rules"]["own"] == ["C-g4.2"] and v4["overseer_rules"]["transcriptions"] == ["T-q25"] and v4["superseded_in_version"] == 5
    assert v4["engine_without_own"] == {"status": "ENTAILED", "premises_relied_on": ["T-q25"], "diagnostics": []}
    assert v4["expected_findings_on_replay"] == ["OVS-TRN-010"]
    rules = ev["overseer_rules"]
    assert rules["own"] == ["T-q25", "C-g4.2"] and rules["transcriptions"] == [] and rules["shown"] == ["C-g4.2"] and rules["undecided"] == ["T-q25"]
    assert rules["undecided_disclosed"] == ["T-q25"] and rules["standings"] == {"T-q25": "undecided", "C-g4.2": "own_kind"}
    assert {"without": ["C-g4.2"], "status": "ENTAILED", "premises_relied_on": ["T-q25"], "diagnostics": []} in ev["engine_runs"]
    assert ev["grade"] == [["OVS-TRN-010", ["C-g4.2"], ["C-g4.2"]], ["OVS-TRN-011", ["T-q25"], ["T-q25", "C-g4.2"]]]
    assert ev["expected_findings_on_replay"] == ["OVS-TRN-010", "OVS-TRN-011"] and ev["merged_parse"]["claim_id"] == "g4.1@economics-specialist"
    assert ev["pipeline_on_the_recorded_proposal"]["problem_delivered"] and ev["pipeline_on_the_recorded_proposal"]["display_status"] == "ENTAILED"
    assert "2025 | 1.90 | 105 | 0.40" in next(t["text"] for t in ev["recorded_answer"]["supplied_texts"] if t["document_id"] == "doc-varenland")
    assert RC._evidence_faults(x, rules_superseded=True) == [] and RC._retirement_faults(x) == [] and RC._same_sources_faults(x) == []
    # record version 6 (decision 56): the same standings and grade; T-q25's reason is now rule same-quantity's reading of the
    # table (rule table-cells), stated exactly (version 5's reasons kept under why_own_v5)
    assert "rule table-cells" in rules["why_own"]["T-q25"] and "Quantity sold (million litres per year)" in rules["why_own"]["T-q25"]
    assert "rule table-cells" not in rules["why_own_v5"]["T-q25"] and "Record version 6" in x["why_retired"]
    a = RC.load_adjudications()
    (s,) = [r for r in a["retired"] if r["id"] == P7A]
    assert s["kind"] == "overseer_rules" and s["expected_findings_on_replay"] == ["OVS-TRN-010", "OVS-TRN-011"] and s["recorded_claim_id"] == "g4.1"


def _doc_without_105(doc):
    """The supplied table no longer states 105: T-q25's figure is then stated nowhere in the document it names (rule
    same-quantity refutes it), so the corrected rules read the encoding as circular again and the retirement must not
    hold (in version 4: rule figure-transcription no longer verified T-q25)."""
    ev = next(x for x in doc["retired"] if x["id"] == P7A)["retirement_evidence"]
    for t in ev["recorded_answer"]["supplied_texts"]:
        t["text"] = t["text"].replace("105", "106")
    _rehash(ev, "recorded_answer")


@pytest.mark.parametrize("damage, why", [
    (_doc_without_105, "restore the entry"),
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"].update(kind="something-else"), "restore the entry"),
    # the engine evidence the retirement rests on misstated (version 4 stated it as engine_without_own; version 5 under
    # engine_runs, every run rule engine-shown's grade rests on)
    (lambda d: next(r for r in next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"]["engine_runs"] if r["without"] == ["C-g4.2"])
     .update(premises_relied_on=["C-g4.2"]), "restore the entry"),
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"].update(expected_findings_on_replay=[]), "restore the entry"),
    # the overseer's reading misstated (version 4's damage named both restating premises the writer's own, the reading
    # version 5's rules give; version 5's names only C-g4.2, the reading the withdrawn rule gave)
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"]["overseer_rules"].update(own=["C-g4.2"]), "restore the entry"),
    # version 5: the codes the replay expects are exactly the grade's
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"].update(expected_findings_on_replay=["OVS-TRN-010"]), "restore the entry"),
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"]["overseer_rules"].update(undecided=[]), "restore the entry"),
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"].update(
        grade=[["OVS-TRN-010", ["C-g4.2"], ["C-g4.2"]]]), "restore the entry"),
    # version 6: the reasons the retirement states are the rules' own, exactly
    (lambda d: next(x for x in d["retired"] if x["id"] == P7A)["retirement_evidence"]["overseer_rules"]["why_own"].update({"T-q25": "a label"}),
     "restore the entry"),
])
def test_version_4_a_retirement_by_the_overseer_s_rules_that_does_not_reproduce_is_refused(tmp_path, damage, why):
    with pytest.raises(H.HarnessError, match=why):
        RC.load_adjudications(_v3_damaged(tmp_path, damage))


def _rekeyed_round(*, raised=(), false_alarms=(), retired=None) -> dict:
    return {"genuine": {"false_alarms": list(false_alarms), "adjudicated_raised": [{"entry": i, "channel": _entry(i)["channel"], "code": "OVS-TRN-006",
                                                                                     "claim_ids": [_entry(i)["claim_id"]], "message": ""} for i in raised],
                        "claims_findings": {}},
            "replay": {"disagreements": [], "results_replayed": 1}, "arena_unchanged_by_the_auditor": True, "channels": [{"verifies": True}],
            "fixtures_rekeyed": 1, "translations": {"checked": 1, "served_stem": {"m": 2}}, "adjudication_evidence": {},
            "retired_on_replay": retired if retired is not None else _confirmed()}


def _confirmed() -> dict:
    a = RC.load_adjudications()
    return {x["id"]: {"claim_id": x["merged_claim_id"], "pipeline": x["pipeline_on_the_recorded_proposal"], "trn_findings": list(x["expected_findings_on_replay"]),
                      "sources_match": True} for x in a["retired"]}


def _v3_result(rounds: dict) -> dict:
    """The run's result with the shipped record (version 5) loaded."""
    return {"rounds": rounds, "adjudications": RC.load_adjudications(), "pack": {"source": "x"}}


def _v4_adjudications() -> dict:
    """The record as the gate saw version 4: the shipped record loaded, with the version-4 entries (kept by version 5 as
    retired entries, every field intact) and only the retirements version 4 had (the entry machinery is pinned on it)."""
    a = RC.load_adjudications()
    return {**a, "version": 4, "entries": list(V4["entries"]), "retired": [x for x in a["retired"] if x["id"] not in (LIT, M11, M71)]}


def _v4_result(rounds: dict) -> dict:
    return {"rounds": rounds, "adjudications": _v4_adjudications(), "pack": {"source": "x"}}


def test_version_3_the_gate_measures_the_re_keyed_entry_and_confirms_each_retirement_on_the_replay():
    rd = _round(raised=[LIT])
    rd["fixtures_matching_no_delivered_claim"] = 1
    rd["rekeyed"] = _rekeyed_round(raised=[M11, M71])
    g = RC.gates(_v4_result({"r7": rd}))
    gate = g["adjudicated_genuine_faults_raised"]
    assert gate["ok"] and gate["value"] == 3 == gate["of"] and gate["retired_confirmed_on_replay"] == 3 == gate["retired_of"]
    assert g["no_false_alarm_on_genuine_transfers"]["ok"] and g["recorded_translations_served_under_merged_ids"]["ok"]
    # record version 6 (shipped): the three restored entries raised on the passes they name (p1-point on the genuine pass,
    # m1.1 and m7.1 on the re-keyed pass), and the three retirements confirmed on the re-keyed pass (record version 5 had no
    # entry and six retirements; its three task restatements were the retirements version 6 restored)
    rd6 = _round(raised=[LIT])
    rd6["fixtures_matching_no_delivered_claim"] = 1
    rd6["rekeyed"] = _rekeyed_round(raised=[M11, M71], retired=_confirmed())
    g6 = RC.gates(_v3_result({"r7": rd6}))
    gate6 = g6["adjudicated_genuine_faults_raised"]
    assert gate6["ok"] and gate6["value"] == 3 == gate6["of"] and gate6["retired_confirmed_on_replay"] == 3 == gate6["retired_of"]
    assert gate6["record_version"] == 6 and sorted(_confirmed()) == sorted([CS, ESS, P7A])
    assert g6["no_false_alarm_on_genuine_transfers"]["ok"] and g6["recorded_translations_served_under_merged_ids"]["ok"]


def test_version_3_the_gate_fails_when_the_re_keyed_entry_is_not_raised_or_its_pass_did_not_run():
    rd = _round(raised=[LIT])
    rd["fixtures_matching_no_delivered_claim"] = 1
    rd["rekeyed"] = _rekeyed_round()
    gate = RC.gates(_v4_result({"r7": rd}))["adjudicated_genuine_faults_raised"]
    assert not gate["ok"] and gate["of"] == 3 and gate["value"] == 1 and [m["pass"] for m in gate["missing"]] == ["rekeyed", "rekeyed"]
    g = RC.gates(_v4_result({"r7": {**_round(raised=[LIT]), "fixtures_matching_no_delivered_claim": 1}}))  # the re-keyed pass did not run
    assert not g["adjudicated_genuine_faults_raised"]["ok"] and "ran no rekeyed pass" in g["adjudicated_genuine_faults_raised"]["missing"][0]["genuine_channel_shows"]
    assert not g["recorded_translations_served_under_merged_ids"]["ok"]  # nor may the pass be skipped silently
    rd2 = _round()  # the genuine-pass entry not raised
    rd2["fixtures_matching_no_delivered_claim"] = 1
    rd2["rekeyed"] = _rekeyed_round(raised=[M11, M71])
    gate = RC.gates(_v4_result({"r7": rd2}))["adjudicated_genuine_faults_raised"]
    assert not gate["ok"] and [m["entry"] for m in gate["missing"]] == [LIT] and gate["missing"][0]["pass"] == "genuine"
    # record version 6 (shipped): a retirement is never counted confirmed on a pass the round did not run (listed, not
    # measured), an entry of a pass the round did not run fails the gate, and an entry its pass did not raise fails it too
    g6 = RC.gates(_v3_result({"r7": {**_round(raised=[LIT]), "fixtures_matching_no_delivered_claim": 1}}))
    gate6 = g6["adjudicated_genuine_faults_raised"]
    assert gate6["retired_confirmed_on_replay"] == 0 and sorted(gate6["retired_not_measured"]) == sorted([CS, ESS, P7A])
    assert not gate6["ok"] and sorted(m["entry"] for m in gate6["missing"]) == sorted([M11, M71]) and not g6["recorded_translations_served_under_merged_ids"]["ok"]
    rd7 = {**_round(), "fixtures_matching_no_delivered_claim": 1, "rekeyed": _rekeyed_round(raised=[M11, M71])}  # the genuine pass did not raise p1-point
    gate7 = RC.gates(_v3_result({"r7": rd7}))["adjudicated_genuine_faults_raised"]
    assert not gate7["ok"] and [m["entry"] for m in gate7["missing"]] == [LIT] and gate7["missing"][0]["pass"] == "genuine"


@pytest.mark.parametrize("change", [
    lambda obs: obs[CS].update(pipeline={**obs[CS]["pipeline"], "translation_status": "TRANSLATED", "problem_delivered": True}),
    lambda obs: obs[ESS].update(trn_findings=["OVS-TRN-006"]),
    lambda obs: obs[CS].update(sources_match=False),
    lambda obs: obs.pop(ESS),
    # a retirement by the overseer's rules is confirmed only by exactly the redundant restatement it expects
    lambda obs: obs[P7A].update(trn_findings=[]),
    lambda obs: obs[P7A].update(trn_findings=["OVS-TRN-006"]),
    lambda obs: obs[P7A].update(trn_findings=["OVS-TRN-006", "OVS-TRN-010"]),
])
def test_version_3_a_retirement_the_replay_does_not_confirm_fails_the_gate(change):
    """A translator that delivers a retired encoding again fails the gate on the replay, even when the record was not
    updated; so do an overseer finding on the retired claim other than the ones its retirement expects (none, or exactly
    the codes rule engine-shown gives for a retirement by the overseer's rules: OVS-TRN-010 and OVS-TRN-011 for p7a since
    record version 5, OVS-TRN-010 alone in version 4), a round whose recorded sources are not the embedded ones, and a
    retired claim the replay never delivered (on the version-4 entries and retirements, as before)."""
    obs = _confirmed()
    change(obs)
    rd = _round(raised=[LIT])
    rd["fixtures_matching_no_delivered_claim"] = 1
    rd["rekeyed"] = _rekeyed_round(raised=[M11, M71], retired=obs)
    gate = RC.gates(_v4_result({"r7": rd}))["adjudicated_genuine_faults_raised"]
    assert not gate["ok"] and gate["retired_unconfirmed"] and gate["value"] == 3


@pytest.mark.parametrize("change, raised_genuine, raised_rekeyed", [
    # the three changes the version-5 test made to the retirements of m1.1 (two) and m7.1, which version 6 restored: their
    # counterpart is the restored entry its pass does not raise (the corrected rules no longer reading it as circular)
    (None, [LIT], [M71]),
    (None, [LIT], [M11]),
    (None, [LIT], []),
    # the change it made to the retirement of p1-point: the restored entry not raised on the genuine pass
    (None, [], [M11, M71]),
    # the changes it made to p7a's retirement and to a retirement's sources, applied as before
    (lambda obs: obs[P7A].update(trn_findings=["OVS-TRN-010"]), [LIT], [M11, M71]),   # version 4's expectation: T-q25 not reported
    (lambda obs: obs[P7A].update(trn_findings=["OVS-TRN-006", "OVS-TRN-010", "OVS-TRN-011"]), [LIT], [M11, M71]),
    (lambda obs: obs[ESS].update(sources_match=False), [LIT], [M11, M71]),
])
def test_version_6_a_retirement_or_entry_the_replay_does_not_confirm_fails_the_gate(change, raised_genuine, raised_rekeyed):
    """Rewritten from ``test_version_5_a_retirement_the_replay_does_not_confirm_fails_the_gate`` (seven cases, seven here).
    Record version 6: each retirement is confirmed only by exactly the codes it expects on the replay (OVS-TRN-010 and
    OVS-TRN-011 for p7a; none for the two the translator withholds), on the pass it names, with the sources it embeds; and
    each restored entry must be raised on its pass (p1-point on the genuine pass, m1.1 and m7.1 on the re-keyed pass).
    The test changed the retirements of p1-point, m1.1 and m7.1, which version 6 restored, so their cases are now the
    restored entry not raised; anything else fails the gate too."""
    obs = _confirmed()
    if change is not None:
        change(obs)
    rd = {**_round(raised=raised_genuine), "fixtures_matching_no_delivered_claim": 1}
    rd["rekeyed"] = _rekeyed_round(raised=raised_rekeyed, retired=obs)
    gate = RC.gates(_v3_result({"r7": rd}))["adjudicated_genuine_faults_raised"]
    assert not gate["ok"] and gate["of"] == 3
    assert bool(gate["retired_unconfirmed"]) is (change is not None) and bool(gate["missing"]) is (change is None)


def test_version_3_a_re_keyed_entry_absorbs_only_errors_of_its_own_pass():
    a = _v4_adjudications()
    f = trn006("m1.1", "mathematics-ai-specialist")
    false_alarms, raised = RC.classify_genuine_errors("r7", "mai-t13", [f], {"entries": RC.entries_of_pass(a, "rekeyed")}, "rekeyed")
    assert [x["entry"] for x in raised] == [M11] and false_alarms == []
    false_alarms, raised = RC.classify_genuine_errors("r7", "mai-t13", [f], {"entries": RC.entries_of_pass(a, "genuine")})
    assert raised == [] and len(false_alarms) == 1  # on the genuine pass the same error would be a false alarm
    g = trn006("p1-point", "english-a-literature-specialist")
    false_alarms, raised = RC.classify_genuine_errors("r7", "lit-t13", [g], {"entries": RC.entries_of_pass(a, "genuine")})
    assert [x["entry"] for x in raised] == [LIT] and false_alarms == []
    false_alarms, raised = RC.classify_genuine_errors("r7", "lit-t13", [g], {"entries": RC.entries_of_pass(a, "rekeyed")}, "rekeyed")
    assert raised == [] and len(false_alarms) == 1  # and the genuine-pass entry absorbs nothing on the re-keyed pass
    # STEM repair 4: the matching itself names the pass, so neither entry absorbs an error of the other pass even when the whole
    # record (both passes' entries) is offered
    for channel, finding, entry_id, own_pass in (("mai-t13", f, M11, "rekeyed"), ("lit-t13", g, LIT, "genuine")):
        for pass_name in RC.PASSES:
            false_alarms, raised = RC.classify_genuine_errors("r7", channel, [finding], a, pass_name)
            assert ([x["entry"] for x in raised], len(false_alarms)) == (([entry_id], 0) if pass_name == own_pass else ([], 1))
            assert all(x["pass"] == pass_name for x in raised)
    # record version 6 (shipped): the restored entries absorb exactly the errors of their own pass, as in version 4 (version
    # 5, with no entry, absorbed neither: each was a false alarm)
    a6 = RC.load_adjudications()
    for channel, finding, entry_id, own_pass in (("mai-t13", f, M11, "rekeyed"), ("lit-t13", g, LIT, "genuine")):
        for pass_name in RC.PASSES:
            false_alarms, raised = RC.classify_genuine_errors("r7", channel, [finding], {"entries": RC.entries_of_pass(a6, pass_name)}, pass_name)
            assert ([x["entry"] for x in raised], len(false_alarms)) == (([entry_id], 0) if pass_name == own_pass else ([], 1))
            false_alarms, raised = RC.classify_genuine_errors("r7", channel, [finding], a6, pass_name)
            assert ([x["entry"] for x in raised], len(false_alarms)) == (([entry_id], 0) if pass_name == own_pass else ([], 1))


def test_stem_repair_4_an_entry_matches_and_is_raised_only_in_the_pass_it_names():
    """STEM repair 4 (the independent test: adjudication_gate pooled the entry ids raised in both passes, and finding_matches_entry
    ignored the pass): the gate requires each entry raised in the pass it names. Moving the lit-t13 raise from the genuine pass to
    the re-keyed pass, or a re-keyed entry's raise to the genuine pass, fails the gate, naming the entry and its pass."""
    a6 = RC.load_adjudications()
    by_pass = {p: [e["id"] for e in RC.entries_of_pass(a6, p) if e["round"] == "r7"] for p in RC.PASSES}
    assert by_pass == {"genuine": [LIT], "rekeyed": [M11, M71]}

    def gate(genuine, rekeyed):
        rd = {**_round(raised=genuine), "fixtures_matching_no_delivered_claim": 1}
        rd["rekeyed"] = _rekeyed_round(raised=rekeyed)
        return RC.gates(_v3_result({"r7": rd}))["adjudicated_genuine_faults_raised"]

    ok = gate([LIT], [M11, M71])
    assert ok["ok"] and ok["missing"] == []
    moved = gate([], [LIT, M11, M71])  # the tester's case: the genuine entry raised only on the re-keyed pass
    assert not moved["ok"] and [(m["entry"], m["pass"]) for m in moved["missing"]] == [(LIT, "genuine")]
    moved = gate([LIT, M11], [M71])  # a re-keyed entry raised only on the genuine pass
    assert not moved["ok"] and [(m["entry"], m["pass"]) for m in moved["missing"]] == [(M11, "rekeyed")]
    e = next(x for x in a6["entries"] if x["id"] == LIT)
    g = trn006("p1-point", "english-a-literature-specialist")
    assert RC.finding_matches_entry(e, "r7", "lit-t13", g) and RC.finding_matches_entry(e, "r7", "lit-t13", g, "genuine")
    assert not RC.finding_matches_entry(e, "r7", "lit-t13", g, "rekeyed")
    e = next(x for x in a6["entries"] if x["id"] == M11)
    f = trn006("m1.1", "mathematics-ai-specialist")
    assert RC.finding_matches_entry(e, "r7", "mai-t13", f, "rekeyed") and not RC.finding_matches_entry(e, "r7", "mai-t13", f)
    with pytest.raises(ValueError):
        RC.finding_matches_entry(e, "r7", "mai-t13", f, "other")
