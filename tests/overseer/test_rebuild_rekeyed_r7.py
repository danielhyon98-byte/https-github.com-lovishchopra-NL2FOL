"""The Overseer on the recorded round-7 translations served under the merged translator's claim ids.

Round r7 was recorded before the translator merge: every STEM answer went through the generic parser (claim ids
``g4.2``), and the generic parser's ids were not yet qualified by the agent. The merged parsers deliver the same claims as
``s4.2``, ``m4.2`` or ``c4.2`` on the STEM branches (the texts are equal: ``tests/stem/test_merge_round7.py``) and as
``g4.2@agent`` on the generic branch, so the arena, by its own rule, serves none of the 200 recorded fixtures keyed by the
earlier ids (``translation_fixtures_matching_no_delivered_claim``), and the contained run checks r7's STEM answers without
their model-proposed translations.

This test is the measurement with pytest: each recorded fixture is re-keyed to the delivered claim the recording gives
that id (rule ``recorded-ids``, ``ovs_harness.rekey_translations``: the id before the "@" on the generic branch; the
generic parser's id at the same place, the texts asserted equal, on a STEM branch; it agrees with
``tests/channel/r7_support.recorded_ids`` on every report), its problem's claim and request ids are the delivered
claim's, and the genuine pass of the round is replayed through hubs that carry the transfer auditor, so every recorded
translation that reaches a delivered claim goes through the merged translator's real pipeline (its gates included) and
the overseer's translation checks. Asserted: exactly the error-level findings pinned in this file (independent of the
adjudication record, which must list exactly these) and no other, no false alarm on any genuine transfer and every
adjudicated fault of the re-keyed pass raised (the contained run's rules, with the shipped adjudication record),
translations served on every STEM branch, each retired entry's claim given exactly the outcome its retirement states,
and each recorded fixture the round's own records show was written for another claim withheld from the re-keyed pass
(rule ``recorded-ids/2``, the second repair of the translator merge).

The repair of the translator merge (design decision 50) made this pass part of the contained run itself
(``run_contained.run_rekeyed_contained``, gated), so it no longer depends on this test, which still needs the recorded
round r7 (``EPINOIC_ARENA_ROUNDS``); it copies the round first and never writes to it. No model is called.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "overseer"))

import ovs_harness as H  # noqa: E402
import run_contained as RC  # noqa: E402

from epinoic_logic.branches import RouterHub  # noqa: E402
from epinoic_logic.translate.contracts import SpecialistReport  # noqa: E402

from ..channel.r7_support import STEM_BRANCHES, recorded_ids  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
HAS_R7 = ROUNDS is not None and (ROUNDS / "r7" / "specialists").is_dir() and (ROUNDS / "r7" / "translations").is_dir()


def rekey_translations(round_copy: Path) -> dict[str, dict]:
    """Rule ``recorded-ids`` on a round copy (``ovs_harness.rekey_translations``, which the contained run's re-keyed pass
    uses), after checking on every delivered report that the harness's map of delivered to recorded ids is the test
    support's (``tests/channel/r7_support.recorded_ids``)."""
    A = H.arena()
    items = A.load_items(round_copy / "specialists")
    for it in items:
        if (round_copy / "translations" / f"{it['_path'].stem}.json").exists():
            report, _rc = H.deliver_recorded_answer(items, it)
            assert H.recorded_claim_ids(report) == recorded_ids(report), it["task_id"]
    return H.rekey_translations(round_copy)


@pytest.fixture(scope="module")
def rekeyed(tmp_path_factory):
    if not HAS_R7:
        pytest.skip("the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
    copy = H.copy_round(ROUNDS / "r7", tmp_path_factory.mktemp("rekeyed") / "rounds")
    mapping = rekey_translations(copy)
    auditor = H.new_auditor(H.keyring_for("arena"))
    replay = H.replay_round(copy, auditor, genuine_only=True)
    audits = {c.key: auditor.audit(c.uid) for c in replay.channels}
    views = {c.key: auditor.view(c.uid) for c in replay.channels}
    yield mapping, replay, audits, views
    auditor.close()


@pytest.mark.timeout(1200)
def test_the_recorded_r7_translations_reach_the_merged_claims_on_every_stem_branch(rekeyed):
    mapping, replay, _audits, views = rekeyed
    stem_files = {stem for stem, m in mapping.items() if m["branch"] in STEM_BRANCHES}
    assert stem_files and all(mapping[s]["rekeyed"] > 0 for s in stem_files)
    assert sum(m["rekeyed"] for m in mapping.values()) >= 150
    assert replay.results["functional"] == replay.results["transmissions"]
    served: Counter = Counter()  # translations a provider proposed for claims with STEM ids (s: sciences, m: mathematics, c: computer science)
    for v in views.values():
        for t in v.transfers:
            if t.receipt is None or t.report is None:
                continue
            for o in t.receipt.outcomes:
                if o.translation.provider is not None and o.claim_id[:1] in ("s", "m", "c") and "@" not in o.claim_id:
                    served[o.claim_id[:1]] += 1
    assert served["s"] and served["m"] and served["c"], served


#: The error-level findings the overseer raises on r7's recorded translations served under the merged ids, pinned HERE,
#: independent of the adjudication record (the second repair of the translator merge restored the strictness of this test:
#: the first repair had derived the expected errors from the record, which an edit could silence). The second repair
#: pinned two (the restatements of the task m1.1 and m7.1, as OVS-TRN-006); the third repair (decision 55, rule
#: engine-shown) made them OVS-TRN-011 warnings, reading their Boolean task settings as undecided on labels alone; the
#: fourth repair (decision 56: content only a label presents as data is shown not to be data) pins both as OVS-TRN-006
#: again, each naming exactly the Boolean premises the result rests on (the figure premises, undecided, kept in the run).
EXPECTED_ERRORS: dict = {("mai-t13", "OVS-TRN-006", ("m1.1",)): ("t_wants_value", "t_wants_euro"),
                         ("mai-t13", "OVS-TRN-006", ("m7.1",)): ("t_whole",)}
#: The restatements under an undecided data grounding (OVS-TRN-011, warnings) on the same pass, pinned exactly, with the
#: premises each finding must name: p7a's four claims that restate a figure of the supplied table (doc-varenland) under a
#: supplied_text label with no excerpt, each figure read in the table for the quantity its premise names (rule
#: table-cells; the receipt lists each among the result's unverified dependencies; whether the table states it, for the
#: same quantity, is a meaning question). The fourth repair moved the two task restatements to EXPECTED_ERRORS.
EXPECTED_UNDECIDED = {("p7a", ("g4.1@economics-specialist",)): ("T-q25",), ("p7a", ("g4.2@economics-specialist",)): ("T-q25",),
                      ("p7a", ("g6.2@economics-specialist",)): ("T-q25",), ("p7a", ("g11.2@economics-specialist",)): ("T-pc25", "T-q25")}


@pytest.mark.timeout(1200)
def test_the_overseer_raises_exactly_the_engine_shown_faults_on_the_recorded_translations_served_under_the_merged_ids(rekeyed):
    """Rewritten in the second repair of the translator merge (renamed from ``test_the_overseer_raises_no_false_alarm_and_
    every_adjudicated_fault_on_...``, itself from ``test_the_overseer_raises_no_error_on_...``). The first repair loosened
    the original "no error at all" to "the errors are the record's entries". This version pins the errors themselves
    (``EXPECTED_ERRORS``: none in the third repair; since the fourth, the two re-keyed mai-t13 restatements, each naming
    exactly the Boolean task premises the result rests on) and no other error-level finding on
    any genuine transfer; the shipped record's re-keyed entries for r7 must be exactly these (so neither the code nor the
    record can drift silently), with no false alarm under the contained run's rule; the restatements under an undecided
    data grounding are exactly ``EXPECTED_UNDECIDED`` (OVS-TRN-011, each naming its premises, citing the auditor's signed
    COUNTEREXAMPLE run and rule engine-shown); and the retired r7 p7a g4.1@economics-specialist gets OVS-TRN-010 naming
    C-g4.2 (its restatement redundant beside T-q25) and OVS-TRN-011 naming T-q25, the undecided data premise the result
    then rests on. Each retirement of this pass (five in record version 5; three in record version 6, which restored m1.1,
    m7.1 and, on the genuine pass, lit-t13 p1-point) is given exactly the outcome and the restatement codes it states."""
    _mapping, _replay, audits, views = rekeyed
    adjudications = RC.load_adjudications()
    entries = {"entries": [e for e in RC.entries_of_pass(adjudications, "rekeyed") if e["round"] == "r7"]}
    errors = [(key, f) for key, a in audits.items() for f in a.report.findings if f.severity == "error"]
    assert {(key, f.code, tuple(f.claim_ids)) for key, f in errors} == set(EXPECTED_ERRORS) and len(errors) == len(EXPECTED_ERRORS)
    for key, f in errors:
        own = EXPECTED_ERRORS[(key, f.code, tuple(f.claim_ids))]
        assert all(pid in f.message for pid in own) and "COUNTEREXAMPLE" in f.message and "grounded-transcription" in f.message, f.message
        assert f.related_result_ids, f.message
        assert f"restating premise(s) {', '.join(own)}" in f.message and "engine-shown" in f.message, f.message
    undecided = [(key, f) for key, a in audits.items() for f in a.report.findings if f.code == "OVS-TRN-011"]
    assert {(key, tuple(f.claim_ids)) for key, f in undecided} == set(EXPECTED_UNDECIDED) and len(undecided) == len(EXPECTED_UNDECIDED)
    for key, f in undecided:
        named = EXPECTED_UNDECIDED[(key, tuple(f.claim_ids))]
        assert f.severity == "warning" and f"premise(s) {', '.join(named)} restate" in f.message, f.message
        assert "COUNTEREXAMPLE" in f.message and "engine-shown" in f.message and "a data conjunct needs its data premise" in f.message, f.message
        assert f.related_result_ids, f.message
    assert sorted((e["channel"], e["code"], (e["claim_id"],)) for e in entries["entries"]) == sorted(EXPECTED_ERRORS)
    false_alarms, raised = [], []
    for key, a in audits.items():
        fa, r = RC.classify_genuine_errors("r7", key, a.report.findings, entries, "rekeyed")
        false_alarms += fa
        raised += r
    assert false_alarms == [] and sorted(x["entry"] for x in raised) == sorted(e["id"] for e in entries["entries"])
    # STEM repair 4: matched in the pass the entries name; offered as genuine-pass errors they are false alarms
    for key, a in audits.items():
        fa, r = RC.classify_genuine_errors("r7", key, a.report.findings, entries, "genuine")
        assert r == [] and len(fa) == sum(1 for f in a.report.findings if f.severity == "error" and f.code not in RC.GENUINE_EXCLUDED)
    # at any severity: no OVS-TRN-001, -002, -003 or -007 at all; OVS-TRN-006 only on the pinned claims (m1.1, m7.1); OVS-TRN-010
    # only on the claim whose adjudication record version 4 retired by the overseer's corrected rules
    trn_any = Counter(f.code for a in audits.values() for f in a.report.findings if f.code.startswith("OVS-TRN"))
    assert not {c for c in trn_any if c in ("OVS-TRN-001", "OVS-TRN-002", "OVS-TRN-003", "OVS-TRN-007")}, trn_any
    assert trn_any["OVS-TRN-006"] == len(EXPECTED_ERRORS), trn_any
    tr010 = [(key, f) for key, a in audits.items() for f in a.report.findings if f.code == "OVS-TRN-010"]
    assert [(key, f.claim_ids) for key, f in tr010] == [("p7a", ["g4.1@economics-specialist"])] and "C-g4.2" in tr010[0][1].message
    assert "relying on T-q25" in tr010[0][1].message
    # each retired entry's claim of this pass, delivered under its merged id, gets exactly the outcome its retirement states
    # and exactly the restatement codes its retirement expects on the replay (the gate's own reading, RESTATEMENT_CODES).
    # Record version 5 retired lit-t13 p1-point on the genuine pass, which this re-keyed pass does not replay (its fixture is
    # withheld here by rule recorded-ids/2, asserted below); record version 6 restored it there (and m1.1 and m7.1 here),
    # so no retirement names the genuine pass and three name this one
    assert [x["id"] for x in adjudications["retired"] if x["pass"] != "rekeyed"] == []
    retired_here = [x for x in adjudications["retired"] if x["pass"] == "rekeyed"]
    assert len(retired_here) == 3
    for x in retired_here:
        outcomes = [o for t in views[x["channel"]].transfers if t.receipt is not None and t.report is not None and t.report.agent_id == x["agent_id"]
                    for o in t.receipt.outcomes if o.claim_id == x["merged_claim_id"]]
        assert [RC._pipeline_record(o) for o in outcomes] == [x["pipeline_on_the_recorded_proposal"]], x["id"]
        named = sorted({f.code for f in audits[x["channel"]].report.findings if f.code in RC.RESTATEMENT_CODES and x["merged_claim_id"] in f.claim_ids
                        and (not f.agent_ids or x["agent_id"] in f.agent_ids)})
        assert named == list(x["expected_findings_on_replay"]), (x["id"], named)
    # every translation that reached a delivered claim was checked, and each one the translator withheld as circular
    # (E112) carries no OVS-TRN-006 or OVS-TRN-010 (rule circularity-agreement)
    checked = sum(len(a.translations) for a in audits.values())
    assert checked >= 150
    withheld = [(key, o.claim_id) for key, v in views.items() for t in v.transfers if t.receipt is not None for o in t.receipt.outcomes
                if o.translation.problem is None and any("E112" in d for d in o.translation.diagnostics)]
    named = {(key, cid) for key, a in audits.items() for f in a.report.findings if f.code in ("OVS-TRN-006", "OVS-TRN-010") for cid in f.claim_ids}
    assert not (set(withheld) & named)


@pytest.mark.timeout(1200)
def test_rule_recorded_ids_2_withholds_every_recorded_fixture_the_round_shows_was_written_for_another_claim(rekeyed):
    """The second repair of the translator merge: by position, r7's physics answers' fixtures reach the next claim (the
    parse of that time issued the mark lines "(a) [2]" ... as claims), so the re-keyed pass withholds each fixture the
    round's records (the recorded relay of ph-p7b's report, the work/ claims files) or its own conclusion label show was
    written for another claim: "(d) [1]" never reaches the half-life sentence s4.1, and lit-t13's heading never reaches
    p1-point."""
    mapping, _replay, _audits, _views = rekeyed
    withheld = {stem: m["withheld"] for stem, m in mapping.items() if m.get("withheld")}
    assert withheld["ph-p7b"]["g4.1"]["would_be_served_to"] == "s4.1" and "relayed/maa-p7b.json records the claim g4.1 as '(d) [1]'" in withheld["ph-p7b"]["g4.1"]["why"]
    assert withheld["lit-t13"]["p1-point"]["would_be_served_to"] == "p1-point" and "p1-s01" in withheld["lit-t13"]["p1-point"]["why"]
    assert sum(len(w) for w in withheld.values()) >= 20


@pytest.mark.skipif(not HAS_R7, reason="the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
@pytest.mark.timeout(1200)
def test_the_re_keyed_pass_shows_the_probe_agents_the_recorded_stem_translations(tmp_path):
    """Finding (d) of the re-test of the fourth repair: the contained run reviewed only the genuine pass with its probe
    agents, where r7's STEM claims carry no recorded translation, so no agent was shown one. Its re-keyed pass now reviews
    every genuine channel too: on r7 ch-t13 (the chemistry parser's ``s`` ids) the STEM probe is shown a recorded STEM
    translation and accuses it, unresolved (AGENT-004, human review), every probe gets its outcome and no review changes a
    clearance; the gate holds, and fails for a pass whose reviews were not run."""
    from epinoic_logic.overseer.export import export_pack
    pack = H.load_exported_pack(export_pack(tmp_path / "pack").directory)
    rounds = tmp_path / "rounds"
    H.mini_round(ROUNDS / "r7", rounds / "r7", ["ch-t13"])
    rk = RC.run_rekeyed_contained("r7", rounds / "r7", tmp_path / "out", pack=pack)
    assert rk["translations"]["served_stem"] and rk["genuine"]["false_alarms"] == []
    assert rk["reviews"] and all(not rv.get("error") and rv["clearances_unchanged"] and all(p["ok"] for p in rv["probes"].values()) for rv in rk["reviews"])
    reviewed = [rv["stem_translation_reviewed"] for rv in rk["reviews"] if rv["stem_translation_reviewed"]]
    assert reviewed and all(c[:1] == "s" and c[1:2].isdigit() for c in reviewed)
    assert [rv["probes"]["overseer-stem-1"]["observed"] for rv in rk["reviews"] if rv["stem_translation_reviewed"]] == ["unresolved"] * len(reviewed)
    assert RC.stem_review_gate([rk])["ok"] and RC.stem_review_gate([rk])["passes_serving_stem"] == 1
    assert not RC.stem_review_gate([{**rk, "reviews": []}])["ok"]  # a pass serving STEM translations no agent was shown fails

