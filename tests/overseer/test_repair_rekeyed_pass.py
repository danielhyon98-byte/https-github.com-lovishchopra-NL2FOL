"""The contained run's re-keyed pass (the repair of the translator merge, design decision 50).

A round recorded before the translator merge keys its translation fixtures by the claim ids of the parsers of that time
(``g1.2``). The arena serves a fixture only to the claim id it was recorded under, so the merged parsers' claims (the
STEM ids ``s``, ``m``, ``c``, the agent-qualified generic ids) receive none of the recorded model-proposed translations,
and the contained run used to check r7's STEM answers without them (finding (c) of the independent test of the staged
rebuild: the only run that served them was a supplementary test skipped by default). The contained run now replays such
a round a second time with its fixtures re-keyed to the claims the merged parse delivers (rule ``recorded-ids``,
``ovs_harness.rekey_translations``) and gates that pass like the genuine one: false alarms, the adjudicated faults of the
pass, replay agreement, non-interference, every audit verifying, and the gate ``recorded_translations_served_under_merged_ids``.

These tests build a one-task round (a Physics answer and one fixture recorded under its generic id); they need no
recorded round and call no model.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import run_contained as RC  # noqa: E402

ITEM = {"task_id": "ph-x", "subject": "Physics", "agent_id": "physics-specialist", "task_type": "structured_question", "supplied_texts": [],
        "question": "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.",
        "response_text": "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻².\n\nThe acceleration is therefore 5.0 m s⁻²."}
#: The generic parser's id of the quantitative claim "Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻²." (the merged sciences
#: parser delivers it as s1.2, with the same text).
RECORDED_ID, MERGED_ID = "g1.2", "s1.2"


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def R(value: str) -> dict:
    return {"op": "real", "value": value}


def fixture(*, circular: bool = False, claim_id: str = RECORDED_ID) -> dict:
    """The recorded proposal for the claim: the change in velocity and the time from the question, the specialist's
    a = dv / 4.0, and a = 5.0 as the conclusion; with ``circular`` the link is replaced by the conclusion restated under a
    ``supplied_text`` label alone (no source, nothing verified), which the merged translator delivers as a success."""
    concl = {"op": "eq", "left": V("a"), "right": R("5.0")}
    premises = [{"id": "P_dv", "expr": {"op": "eq", "left": V("dv"), "right": R("20")}, "label": "the speed rises by 20 m s-1", "grounding": {"kind": "task_setting"}}]
    if circular:
        premises.append({"id": "P_restated", "expr": concl, "label": "the acceleration is 5.0 m s-2", "grounding": {"kind": "supplied_text"}})
    else:
        premises.append({"id": "P_a", "expr": {"op": "eq", "left": V("a"), "right": {"op": "div", "left": V("dv"), "right": R("4.0")}},
                         "label": "a = dv / 4.0", "grounding": {"kind": "specialist_inference"}})
    problem = {"problem_id": "p-ph-x", "request_id": "req-ph-x", "claim_id": claim_id, "query": "entailment",
               "symbols": [{"name": "dv", "sort": "Real", "meaning": "the change in velocity"}, {"name": "a", "sort": "Real", "meaning": "the acceleration"}],
               "premises": premises, "conclusion": {"id": "C", "expr": concl, "label": "a = 5.0 m s-2"}}
    return {"problem": problem, "interpretation": {"reading": "a from the change in velocity over the time", "glossary": [], "ambiguity_flags": []},
            "ambiguous": False, "unsupported_reason": None}


def mini_round(root: Path, name: str = "rx", **kw) -> Path:
    rnd = Path(root) / name
    (rnd / "specialists").mkdir(parents=True)
    (rnd / "translations").mkdir()
    (rnd / "specialists" / "ph-x.json").write_text(json.dumps(ITEM), encoding="utf-8")
    key = kw.pop("key", RECORDED_ID)
    (rnd / "translations" / "ph-x.json").write_text(json.dumps({"report_id": "rep-ph-x-0", "claims": {key: fixture(claim_id=key, **kw)}}), encoding="utf-8")
    return rnd


def _tree(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_the_rule_recorded_ids_maps_the_generic_id_to_the_merged_stem_claim():
    plan = H.arena().group_plan([{**ITEM, "_path": Path("ph-x.json")}], "ph-x")
    d = H.recorded_delivery(ITEM, plan, {RECORDED_ID: fixture()})
    assert d.recorded_ids == {"s1.1": "g1.1", "s1.2": "g1.2", "s2.1": "g2.1"} and d.delivered_id(RECORDED_ID) == MERGED_ID
    o = d.outcomes[MERGED_ID]
    assert o.translation.status.value == "TRANSLATED" and o.verification.status.value == "ENTAILED" and o.display_status.value == "ENTAILED"
    assert o.translation.problem.claim_id == MERGED_ID


def test_the_re_keyed_pass_serves_the_recorded_fixture_to_the_merged_claim_and_audits_it(tmp_path):
    rnd = mini_round(tmp_path / "rounds")
    before = _tree(rnd)
    # control: the arena by its own rule serves nothing to the merged claim
    aud0 = H.new_auditor(H.keyring_for("arena"))
    try:
        rr0 = H.replay_round(H.copy_round(rnd, tmp_path / "plain"), aud0, genuine_only=True)
        assert rr0.results["translation_fixtures_matching_no_delivered_claim"]["count"] == 1
        assert not any(o.translation.provider is not None for c in rr0.channels for t in aud0.view(c.uid).transfers if t.receipt for o in t.receipt.outcomes)
    finally:
        aud0.close()
    rec = RC.run_rekeyed_contained("rx", rnd, tmp_path / "out")
    assert _tree(rnd) == before  # the recorded round is a read-only input
    assert (rec["fixtures"], rec["fixtures_rekeyed"], rec["fixtures_matching_no_delivered_claim"]) == (1, 1, 0)
    assert rec["translations"]["served_stem"] == {"s": 1} and rec["translations"]["checked"] >= 1
    assert rec["genuine"]["false_alarms"] == [] and rec["genuine"]["channels"] == 1
    assert rec["arena_unchanged_by_the_auditor"] and all(c["verifies"] for c in rec["channels"]) and rec["replay"]["disagreements"] == []


def _entry(rnd: Path) -> dict:
    """An adjudication of the circular fixture of the mini round, measured in its re-keyed pass (as the shipped record's
    r7 entry is), with the digests of the round's recorded answer and fixture."""
    from epinoic_logic.ir.canonical import sha256_hex
    answer = {k: ITEM[k] for k in ("task_id", "agent_id", "subject", "task_type", "question", "response_text", "supplied_texts")}
    fx = json.loads((rnd / "translations" / "ph-x.json").read_text())["claims"][RECORDED_ID]
    return {"id": f"rx/ph-x/{MERGED_ID}/OVS-TRN-006", "round": "rx", "pass": "rekeyed", "channel": "ph-x", "task_id": "ph-x", "agent_id": "physics-specialist",
            "claim_id": MERGED_ID, "recorded_claim_id": RECORDED_ID, "code": "OVS-TRN-006",
            "evidence": {"recorded_answer": answer, "recorded_answer_sha256": sha256_hex(RC.canonical_json_of(answer)),
                         "recorded_proposal": fx, "recorded_proposal_sha256": sha256_hex(RC.canonical_json_of(fx))}}


def test_a_label_only_restatement_served_on_the_re_keyed_pass_is_a_false_alarm_unless_adjudicated_for_that_pass(tmp_path):
    """The re-keyed pass grades its genuine transfers as the genuine pass does: the merged translator delivers the recorded
    proposal's label-only restatement as a success, the overseer raises OVS-TRN-006, and the error is a false alarm unless
    an entry of the RE-KEYED pass adjudicates it (a genuine-pass entry does not)."""
    rnd = mini_round(tmp_path / "rounds", circular=True)
    rec = RC.run_rekeyed_contained("rx", rnd, tmp_path / "out1")
    assert [(f["code"], f["claim_ids"]) for f in rec["genuine"]["false_alarms"]] == [("OVS-TRN-006", [MERGED_ID])]
    e = _entry(rnd)
    rec2 = RC.run_rekeyed_contained("rx", rnd, tmp_path / "out2", adjudications={"entries": [e], "retired": []})
    assert rec2["genuine"]["false_alarms"] == [] and [r["entry"] for r in rec2["genuine"]["adjudicated_raised"]] == [e["id"]]
    assert rec2["adjudication_evidence"][e["id"]].startswith("the round's recorded answer and fixture are")
    genuine_pass_entry = {**e, "pass": "genuine"}
    rec3 = RC.run_rekeyed_contained("rx", rnd, tmp_path / "out3", adjudications={"entries": [genuine_pass_entry], "retired": []})
    assert len(rec3["genuine"]["false_alarms"]) == 1 and rec3["genuine"]["adjudicated_raised"] == []


@pytest.mark.timeout(900)
def test_the_contained_run_replays_the_re_keyed_pass_and_gates_it(tmp_path):
    """``run_contained`` runs the re-keyed pass exactly for a round whose fixtures the current parse does not serve (rx),
    never for one whose fixtures are keyed by the merged ids already (ry), and the gate says so."""
    root = tmp_path / "rounds"
    mini_round(root, "rx")
    mini_round(root, "ry", key=MERGED_ID)
    r = RC.run_contained(tmp_path / "out", rounds_root=root, rounds=("rx", "ry"), tamper=False)
    rx, ry = r["rounds"]["rx"], r["rounds"]["ry"]
    assert rx["fixtures_matching_no_delivered_claim"] == 1 and rx["rekeyed"]["fixtures_rekeyed"] == 1 and rx["rekeyed"]["translations"]["served_stem"] == {"s": 1}
    assert ry["fixtures_matching_no_delivered_claim"] == 0 and "rekeyed" not in ry
    gate = r["gates"]["recorded_translations_served_under_merged_ids"]
    assert gate["ok"] and gate["rounds"]["rx"]["fixtures_rekeyed"] == 1 and gate["rounds"]["ry"] == {"fixtures_matching_no_delivered_claim": 0}
    assert r["gates"]["no_false_alarm_on_genuine_transfers"]["ok"] and r["gates"]["every_task_audit_verifies"]["ok"]
    assert r["gates"]["arena_unchanged_by_the_auditor"]["ok"] and r["gates"]["replay_agreement_on_definitive_results"]["ok"]
    assert "re-keyed pass (rule recorded-ids" in (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")


# ============================================================================================ rule recorded-ids/2
def _round_with(root: Path, fx: dict, *, claims_file: Optional[dict] = None, name: str = "rz") -> Path:
    rnd = Path(root) / name
    (rnd / "specialists").mkdir(parents=True)
    (rnd / "translations").mkdir()
    (rnd / "specialists" / "ph-x.json").write_text(json.dumps(ITEM), encoding="utf-8")
    (rnd / "translations" / "ph-x.json").write_text(json.dumps({"report_id": "rep-ph-x-0", "claims": {RECORDED_ID: fx}}), encoding="utf-8")
    if claims_file is not None:
        (rnd / "work").mkdir()
        (rnd / "work" / "ph-x.claims.json").write_text(json.dumps(claims_file), encoding="utf-8")
    return rnd


def _labelled(label: str) -> dict:
    fx = fixture()
    fx["problem"]["conclusion"]["label"] = label
    return fx


@pytest.mark.parametrize("label, withheld", [
    ("(a) [2]", True),                                              # written for a mark line the parse of that time issued as a claim
    ("The trolley starts from rest, so u = 0.", True),             # written for the claim before it (the ids moved)
    ("Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻² (M1).", False),  # the claim itself, a mark annotation aside
    ("a = 5.0 m s-2", False),                                      # a paraphrase: nothing shows another claim
])
def test_rule_recorded_ids_2_serves_a_recorded_fixture_only_to_the_claim_it_was_written_for(tmp_path, label, withheld):
    """The second repair of the translator merge: an id is a position in the parse of its time, and a parse that changed
    since moves every later id to another claim (round 7's physics answers: "(d) [1]" was g4.1, so by position its
    fixture reached the half-life sentence now issued as s4.1). A fixture whose conclusion label (the claim text the
    translator was given) is a mark line, or the text of ANOTHER delivered claim, is withheld with why; one whose label
    is the claim's, or names no other claim, is served."""
    rnd = _round_with(tmp_path / "rounds", _labelled(label))
    m = H.rekey_translations(H.copy_round(rnd, tmp_path / "copy"))["ph-x"]
    if withheld:
        assert m["fixtures"] == 0 and m["rekeyed"] == 0 and m["withheld"][RECORDED_ID]["would_be_served_to"] == MERGED_ID and m["withheld"][RECORDED_ID]["why"]
        written = json.loads((tmp_path / "copy" / "rz" / "translations" / "ph-x.json").read_text())
        assert written["claims"] == {} and written["withheld"][RECORDED_ID]["fixture"]["problem"]["conclusion"]["label"] == label
    else:
        assert m["fixtures"] == 1 and m["moved"] == {RECORDED_ID: MERGED_ID} and m["withheld"] == {}


@pytest.mark.parametrize("recorded_text, withheld", [("(a) [2]", True), ("Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻².", False)])
def test_rule_recorded_ids_2_reads_the_claim_text_the_round_records_before_the_label(tmp_path, recorded_text, withheld):
    """When the round records the claims the translator was given (``work/<task>.claims.json``) or a relay of the report,
    that record decides, whatever the label says: the label here is the delivered claim's own text."""
    claims = {"report_id": "rep-ph-x-0", "claims": [{"claim_id": RECORDED_ID, "text": recorded_text}]}
    rnd = _round_with(tmp_path / "rounds", _labelled("Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻²."), claims_file=claims)
    m = H.rekey_translations(H.copy_round(rnd, tmp_path / "copy"))["ph-x"]
    assert (RECORDED_ID in m["withheld"]) is withheld
    if withheld:
        assert "work/ph-x.claims.json records the claim g1.2 as '(a) [2]'" in m["withheld"][RECORDED_ID]["why"]


def test_rule_recorded_ids_2_a_withheld_fixture_reaches_no_claim_on_the_re_keyed_pass(tmp_path):
    """On the re-keyed pass a withheld fixture is served to no claim (it is not in the translations the arena reads), the
    pass reports it, and the overseer raises nothing on the claim it would have reached."""
    rnd = _round_with(tmp_path / "rounds", _labelled("(a) [2]"), name="rx")
    rec = RC.run_rekeyed_contained("rx", rnd, tmp_path / "out")
    assert rec["fixtures_withheld"] == 1 and rec["withheld"] == {"ph-x": {RECORDED_ID: {"would_be_served_to": MERGED_ID, "why": rec["withheld"]["ph-x"][RECORDED_ID]["why"]}}}
    assert rec["translations"]["served_stem"] == {} and rec["genuine"]["false_alarms"] == []


# ============================================================================================ round-7 material kept in the repository
R7_DATA = Path(__file__).resolve().parents[1] / "channel" / "data"
#: The recorded tasks whose translation fixtures the repository keeps (``tests/channel/data/r7_translations.json``), with
#: the members of their groups (a peer-dependent agent answers after its peer).
R7_TASKS = ("cs-t13", "ph-t13", "ph-p7b", "maa-p7b", "ec-t13", "ec-p7a", "bm-p7a", "hi-t13")


def r7_material_round(root: Path) -> Path:
    """A round directory built from the round-7 material the repository keeps (the recorded answers, identical to the
    recorded round's, and the recorded fixtures of six tasks under their pre-merge ids)."""
    material = json.loads((R7_DATA / "r7_material.json").read_text(encoding="utf-8"))
    translations = json.loads((R7_DATA / "r7_translations.json").read_text(encoding="utf-8"))
    rnd = Path(root) / "r7"
    (rnd / "specialists").mkdir(parents=True)
    (rnd / "translations").mkdir()
    for tid in R7_TASKS:
        (rnd / "specialists" / f"{tid}.json").write_text(json.dumps(material["specialists"][tid]), encoding="utf-8")
        if tid in translations:
            (rnd / "translations" / f"{tid}.json").write_text(json.dumps(translations[tid]), encoding="utf-8")
    return rnd


@pytest.mark.timeout(900)
def test_the_re_keyed_pass_serves_round_7_s_recorded_stem_translations_kept_in_the_repository(tmp_path):
    """Finding (c) of the independent test: the only run that served r7's recorded STEM model translations was skipped
    by default. On the round-7 material the repository keeps, the re-keyed pass serves the recorded fixtures of the
    computer science answer to the merged c claims, through the merged translator's real pipeline, and the overseer
    raises no false alarm on them.

    Rewritten in the second repair of the translator merge (rule recorded-ids/2; the same assertions, and more): the four
    recorded physics fixtures this material keeps were written for the mark lines "(a) [2]", "(c) [1]" and "(d) [1]",
    which the parse of that time issued as claims and the merged parse no longer does, so by position each would be
    served to the NEXT claim ("32 h is 4 half-lives, so C = ... = 100 counts min-1" would receive "marks = 1"). They are
    withheld, each with why; the staged counts (17 served, 16 re-keyed, 4 to the s claims) included those four."""
    rnd = r7_material_round(tmp_path / "rounds")
    rec = RC.run_rekeyed_contained("r7", rnd, tmp_path / "out", adjudications=RC.load_adjudications())
    assert (rec["fixtures"], rec["fixtures_rekeyed"], rec["fixtures_matching_no_delivered_claim"]) == (13, 12, 0)
    assert rec["fixtures_withheld"] == 4 and rec["correspondence_rule"] == "recorded-ids/2"
    assert {stem: {rid: w["would_be_served_to"] for rid, w in ws.items()} for stem, ws in rec["withheld"].items()} == {
        "ph-p7b": {"g1.1": "s1.1", "g4.1": "s4.1"}, "ph-t13": {"g1.1": "s1.1", "g3.1": "s3.1"}}
    assert all("is a mark or part line" in w["why"] for ws in rec["withheld"].values() for w in ws.values())
    assert rec["rekeyed_by_branch"] == {"computer_science": 8, "economics": 4}
    assert rec["translations"]["checked"] == 13 and rec["translations"]["served_stem"] == {"c": 7}, rec["translations"]
    assert rec["genuine"]["false_alarms"] == [] and rec["genuine"]["adjudicated_raised"] == []
    assert not [c for c in rec["translations"]["trn_codes_on_genuine"] if c.endswith("(error)")]
    assert rec["arena_unchanged_by_the_auditor"] and all(c["verifies"] for c in rec["channels"]) and rec["replay"]["disagreements"] == []
    assert rec["functional"] == rec["transmissions"]
