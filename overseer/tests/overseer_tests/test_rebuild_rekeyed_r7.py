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
adjudication record, which must list exactly these; since round-8 clearance c1 none, the translator withholding the two
encodings the fourth repair pinned, ``EXPECTED_WITHHELD``) and no other, no false alarm on any genuine transfer and every
adjudicated fault of the re-keyed pass raised (the contained run's rules, with the shipped adjudication record),
translations served on every STEM branch, each retired entry's claim given exactly the outcome its retirement states,
and each recorded fixture the round's own records show was written for another claim withheld from the re-keyed pass
(rule ``recorded-ids/2``, the second repair of the translator merge).

The repair of the translator merge (design decision 50) made this pass part of the contained run itself
(``run_contained.run_rekeyed_contained``, gated), so it no longer depends on this test, which still needs the recorded
round r7 (``EPINOIC_ARENA_ROUNDS``); it copies the round first and never writes to it. No model is called. Because those
tests skip without the round, round-8 clearance c1 changed what they pin (the translator's semantic circularity rule now
withholds mai-t13 m1.1 and m7.1, decisions 91 and 94) without any verification run noticing; the one test of this file
that needs no recorded round (``test_the_pins_of_this_file_agree_with_the_shipped_adjudication_record``) now ties the pins
to the shipped record, so a plain suite run fails when they drift apart again.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ovs_harness as H  # noqa: E402
import run_contained as RC  # noqa: E402

from epinoic_logic.branches import RouterHub  # noqa: E402
from epinoic_logic.translate.contracts import SpecialistReport  # noqa: E402

from .r7_support import STEM_BRANCHES, recorded_ids  # noqa: E402
from .conftest import withheld_as_circular_by_the_translator, without_the_translators_semantic_gate  # noqa: E402

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


@pytest.fixture(scope="module")
def rekeyed_past_the_gate(tmp_path_factory):
    """The same pass on the translator as it was before round-8 clearance c1: its SEMANTIC circularity rule off
    (``conftest.without_the_translators_semantic_gate``; its rule as written kept), everything else as shipped, the
    overseer's own rules included (its floor, decision 91, re-runs the translator's semantic rule itself). The patch is
    undone before the fixture yields: every finding and view is read while it holds, and no other test sees it."""
    if not HAS_R7:
        pytest.skip("the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
    copy = H.copy_round(ROUNDS / "r7", tmp_path_factory.mktemp("rekeyed_past_the_gate") / "rounds")
    H.rekey_translations(copy)
    auditor = H.new_auditor(H.keyring_for("arena"))
    with pytest.MonkeyPatch.context() as mp:
        without_the_translators_semantic_gate(mp)
        replay = H.replay_round(copy, auditor, genuine_only=True)
        audits = {c.key: auditor.audit(c.uid) for c in replay.channels}
        views = {c.key: auditor.view(c.uid) for c in replay.channels}
    yield replay, audits, views
    auditor.close()


def _withheld_as_circular(views) -> dict:
    """Each claim of the pass the translator withheld as circular (no problem, an E112 diagnostic), by (channel, claim):
    its outcome."""
    return {(key, o.claim_id): o for key, v in views.items() for t in v.transfers if t.receipt is not None for o in t.receipt.outcomes
            if o.translation.problem is None and any("E112" in d for d in o.translation.diagnostics)}


def _e112_premises(outcome) -> set:
    """The premises each E112 diagnostic of a withheld outcome names ("premise(s) a (kind), b (kind) restate ...")."""
    named = set()
    for d in outcome.translation.diagnostics:
        if "E112" in d and "premise(s) " in d:
            head = d.split("premise(s) ", 1)[1].split(" restate", 1)[0]
            named |= {part.split(" (", 1)[0].strip() for part in head.split(", ")}
    return named


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
#: Since round-8 clearance c1 these are the overseer's grade of the two encodings WHEN DELIVERED: the translator's pipeline
#: now withholds both itself (``EXPECTED_WITHHELD``), so on the shipped pipeline the overseer raises none of them
#: (``_expected_errors_on_the_shipped_pipeline``: decisions 46 and 91, a withheld translation gets no OVS-TRN finding), and
#: each is asserted on the same encodings delivered past the translator's semantic gate.
EXPECTED_ERRORS: dict = {("mai-t13", "OVS-TRN-006", ("m1.1",)): ("t_wants_value", "t_wants_euro"),
                         ("mai-t13", "OVS-TRN-006", ("m7.1",)): ("t_whole",)}
#: Round-8 clearance c1 (decisions 91 and 94, adjudication record version 8, kind ``translator_semantic``): the claims of this
#: pass the translator's pipeline withholds by its SEMANTIC circularity rule (``translate.restatement``; INVALID_FORMALIZATION
#: with E112 on the first attempt and on the fed-back retry: no problem, no engine run, no verdict displayed), beyond those it
#: withholds by its rule as written, which it withheld before c1 too, with exactly the premises each E112 names. They are the
#: two encodings ``EXPECTED_ERRORS`` pins (m1.1 also naming t_comp, the figure 12 written for "monthly", which the semantic
#: rule names on this replay, with the journaled task record; the record's own re-derivation on the recorded IR names only
#: the two Boolean premises, asserted in ``test_the_pins_of_this_file_agree_with_the_shipped_adjudication_record``) and
#: p7c h1.6 (the consequence the claim draws, restated by its assumption a_flow), which the translator delivered before c1
#: as AMBIGUOUS_TRANSLATION.
EXPECTED_WITHHELD: dict = {("mai-t13", "m1.1"): ("t_comp", "t_wants_euro", "t_wants_value"), ("mai-t13", "m7.1"): ("t_whole",),
                           ("p7c", "h1.6"): ("a_flow",)}
#: What the overseer's floor (decision 91: every premise the translator's semantic rule names restates the conclusion for the
#: overseer too, as the writer's own) adds to ``EXPECTED_ERRORS`` on the encodings delivered past the translator's semantic
#: gate: t_comp on m1.1, and an OVS-TRN-006 on p7c h1.6. Past the gate the overseer names, for each, exactly the premises
#: the translator's E112 names on the shipped pipeline (rule circularity-agreement).
EXPECTED_FLOOR_ERRORS: dict = {("mai-t13", "OVS-TRN-006", ("m1.1",)): ("t_comp",), ("p7c", "OVS-TRN-006", ("h1.6",)): ("a_flow",)}
#: The restatements under an undecided data grounding (OVS-TRN-011, warnings) on the same pass, pinned exactly, with the
#: premises each finding must name: p7a's four claims that restate a figure of the supplied table (doc-varenland) under a
#: supplied_text label with no excerpt, each figure read in the table for the quantity its premise names (rule
#: table-cells; the receipt lists each among the result's unverified dependencies; whether the table states it, for the
#: same quantity, is a meaning question). The fourth repair moved the two task restatements to EXPECTED_ERRORS.
EXPECTED_UNDECIDED = {("p7a", ("g4.1@economics-specialist",)): ("T-q25",), ("p7a", ("g4.2@economics-specialist",)): ("T-q25",),
                      ("p7a", ("g6.2@economics-specialist",)): ("T-q25",), ("p7a", ("g11.2@economics-specialist",)): ("T-pc25", "T-q25")}
#: The retirement record version 8 places on the genuine pass (this re-keyed pass withholds its fixture, rule recorded-ids/2).
LIT_P1_POINT = "r7/lit-t13/p1-point/OVS-TRN-006"
#: What the pipeline delivers for a claim it withholds as circular (``run_contained._pipeline_record``).
WITHHELD_RECORD = {"translation_status": "INVALID_FORMALIZATION", "problem_delivered": False, "engine_run": False,
                   "display_status": "INVALID_FORMALIZATION", "translation_diagnostic": "E112"}


def _expected_errors_on_the_shipped_pipeline() -> dict:
    """The error-level findings the overseer raises on this pass with the translator as shipped: ``EXPECTED_ERRORS`` but the
    claims the translator withholds (``EXPECTED_WITHHELD``), which get no OVS-TRN finding (decisions 46 and 91)."""
    return {k: v for k, v in EXPECTED_ERRORS.items() if (k[0], k[2][0]) not in EXPECTED_WITHHELD}


def _raw_retirement(retirement_id: str) -> dict:
    """The shipped record's retired entry as the file holds it (every field, its retirement evidence included)."""
    raw = json.loads(RC.ADJUDICATIONS_FILE.read_text(encoding="utf-8"))
    (x,) = [r for r in raw["retired"] if r["id"] == retirement_id]
    return x


def _record_premises(retirement_id: str) -> list:
    """The premises the shipped record's ``translator_semantic`` retirement states its rule names on the recorded IR."""
    return list(_raw_retirement(retirement_id)["retirement_evidence"]["translator_semantic_rule"]["premises"])


def _semantic_retirements_here(adjudications: dict) -> dict:
    """The shipped record's ``translator_semantic`` retirements of r7's re-keyed pass, by (channel, code, (merged claim,))."""
    return {(x["channel"], _raw_retirement(x["id"])["code"], (x["merged_claim_id"],)): x for x in adjudications["retired"]
            if x["round"] == "r7" and x["pass"] == "rekeyed" and x["kind"] == "translator_semantic"}


def test_the_pins_of_this_file_agree_with_the_shipped_adjudication_record():
    """Added after round-8 clearance c1 (the regression it left: ``f2329df``). This file's other tests need the recorded round
    r7 and skip without it, so when the clearance made the translator withhold mai-t13 m1.1 and m7.1 (record version 8) no
    verification run saw that this file still pinned both as raised. This test needs no recorded round: the errors pinned for
    the shipped pipeline must be exactly the shipped record's re-keyed r7 entries (none in version 8); every encoding
    ``EXPECTED_ERRORS`` grades that the translator withholds must be exactly a ``translator_semantic`` retirement of this
    pass, expecting the withheld pipeline run and no finding on replay, its stated premises those ``EXPECTED_ERRORS`` names
    and among those ``EXPECTED_WITHHELD`` pins, and the translator as it is must still name them on the recorded IR
    (``run_contained.semantic_rule_on``); and the retirements of this pass and of the genuine pass are those the replay
    test checks. With ``EXPECTED_WITHHELD`` empty (the expectation before this repair) the first assertion fails."""
    a = RC.load_adjudications()
    shipped = _expected_errors_on_the_shipped_pipeline()
    assert shipped == {}  # the translator withholds both encodings EXPECTED_ERRORS grades
    entries = [e for e in RC.entries_of_pass(a, "rekeyed") if e["round"] == "r7"]
    assert sorted((e["channel"], e["code"], (e["claim_id"],)) for e in entries) == sorted(shipped)
    semantic = _semantic_retirements_here(a)
    assert set(semantic) == set(EXPECTED_ERRORS) - set(shipped)
    for key, x in semantic.items():
        assert x["expected_findings_on_replay"] == [] and x["pipeline_on_the_recorded_proposal"] == {"claim_id": key[2][0], **WITHHELD_RECORD}, x["id"]
        premises = _record_premises(x["id"])
        assert set(premises) == set(EXPECTED_ERRORS[key]) and set(premises) <= set(EXPECTED_WITHHELD[(key[0], key[2][0])]), (x["id"], premises)
        rx = _raw_retirement(x["id"])
        assert RC.semantic_rule_on(rx, rx["retirement_evidence"]) == {"kind": "full", "premises": premises}, x["id"]
    assert [x["id"] for x in a["retired"] if x["pass"] != "rekeyed"] == [LIT_P1_POINT]
    assert len([x for x in a["retired"] if x["pass"] == "rekeyed"]) == 5


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
    m7.1 and, on the genuine pass, lit-t13 p1-point) is given exactly the outcome and the restatement codes it states.

    Rewritten after round-8 clearance c1 to a stricter rule, no assertion weakened or deleted: the clearance's translator
    withholds the two encodings ``EXPECTED_ERRORS`` pins (its semantic circularity rule, E112 at translation; decision 91),
    and record version 8 retires both (kind ``translator_semantic``, decision 94), but this test skips without the recorded
    round, so no verification run of the clearance executed it and it went on asserting both errors. A withheld translation
    gets no OVS-TRN finding (decisions 46 and 91; OVS-TRN-006's own definition), so the errors on the shipped pipeline are
    ``EXPECTED_ERRORS`` but the withheld claims (none now). This test asserts first that the translator withholds exactly
    ``EXPECTED_WITHHELD`` among the pinned claims (each by ``conftest.withheld_as_circular_by_the_translator``, its E112
    naming exactly the pinned premises on both attempts, and no OVS-TRN finding at any severity on it), then every earlier
    assertion on the shipped pipeline; the record now places one retirement (p1-point's) on the genuine pass and five on
    this one, two of them the pinned claims (asserted with the record's own outcome and codes). Every assertion it made on
    the two errors is made, unchanged but for the floor's added premise, on the same encodings delivered past the
    translator's semantic gate (``test_past_the_translators_semantic_gate_...``)."""
    _mapping, _replay, audits, views = rekeyed
    adjudications = RC.load_adjudications()
    entries = {"entries": [e for e in RC.entries_of_pass(adjudications, "rekeyed") if e["round"] == "r7"]}
    shipped = _expected_errors_on_the_shipped_pipeline()
    # the translator withholds each pinned claim of EXPECTED_WITHHELD as circular, naming exactly its premises, and the
    # overseer raises no OVS-TRN finding of any severity on it (rule circularity-agreement)
    withheld_now = _withheld_as_circular(views)
    for (key, cid), premises in EXPECTED_WITHHELD.items():
        o = withheld_now.get((key, cid))
        assert o is not None and withheld_as_circular_by_the_translator(o), (key, cid)
        assert _e112_premises(o) == set(premises), (key, cid, o.translation.diagnostics)
        assert [d.split(": ", 2)[:2] for d in o.translation.diagnostics if "E112" in d] == [["attempt 1", "E112"], ["attempt 2", "E112"]], o.translation.diagnostics
        assert [f.code for f in audits[key].report.findings if f.code.startswith("OVS-TRN") and cid in f.claim_ids] == [], (key, cid)
    errors = [(key, f) for key, a in audits.items() for f in a.report.findings if f.severity == "error"]
    assert {(key, f.code, tuple(f.claim_ids)) for key, f in errors} == set(shipped) and len(errors) == len(shipped)
    for key, f in errors:
        own = shipped[(key, f.code, tuple(f.claim_ids))]
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
    assert sorted((e["channel"], e["code"], (e["claim_id"],)) for e in entries["entries"]) == sorted(shipped)
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
    # at any severity: no OVS-TRN-001, -002, -003 or -007 at all; OVS-TRN-006 only on the pinned claims the translator
    # delivers (none since round-8 clearance c1); OVS-TRN-010 only on the claim whose adjudication record version 4 retired by
    # the overseer's corrected rules
    trn_any = Counter(f.code for a in audits.values() for f in a.report.findings if f.code.startswith("OVS-TRN"))
    assert not {c for c in trn_any if c in ("OVS-TRN-001", "OVS-TRN-002", "OVS-TRN-003", "OVS-TRN-007")}, trn_any
    assert trn_any["OVS-TRN-006"] == len(shipped) == 0, trn_any
    tr010 = [(key, f) for key, a in audits.items() for f in a.report.findings if f.code == "OVS-TRN-010"]
    assert [(key, f.claim_ids) for key, f in tr010] == [("p7a", ["g4.1@economics-specialist"])] and "C-g4.2" in tr010[0][1].message
    assert "relying on T-q25" in tr010[0][1].message
    # each retired entry's claim of this pass, delivered under its merged id, gets exactly the outcome its retirement states
    # and exactly the restatement codes its retirement expects on the replay (the gate's own reading, RESTATEMENT_CODES).
    # Record version 5 retired lit-t13 p1-point on the genuine pass, which this re-keyed pass does not replay (its fixture is
    # withheld here by rule recorded-ids/2, asserted below); record version 6 restored it there (and m1.1 and m7.1 here);
    # record version 8 (round-8 clearance c1) retires the three again by kind translator_semantic, so one retirement names
    # the genuine pass (p1-point's) and five name this one, among them exactly the two claims EXPECTED_ERRORS grades
    assert [x["id"] for x in adjudications["retired"] if x["pass"] != "rekeyed"] == [LIT_P1_POINT]
    retired_here = [x for x in adjudications["retired"] if x["pass"] == "rekeyed"]
    assert len(retired_here) == 5
    semantic = set(_semantic_retirements_here(adjudications))
    assert semantic == set(EXPECTED_ERRORS) - set(shipped) == {(k, c, (cid,)) for (k, c, (cid,)) in EXPECTED_ERRORS if (k, cid) in EXPECTED_WITHHELD}
    for x in retired_here:
        outcomes = [o for t in views[x["channel"]].transfers if t.receipt is not None and t.report is not None and t.report.agent_id == x["agent_id"]
                    for o in t.receipt.outcomes if o.claim_id == x["merged_claim_id"]]
        assert [RC._pipeline_record(o) for o in outcomes] == [x["pipeline_on_the_recorded_proposal"]], x["id"]
        named = sorted({f.code for f in audits[x["channel"]].report.findings if f.code in RC.RESTATEMENT_CODES and x["merged_claim_id"] in f.claim_ids
                        and (not f.agent_ids or x["agent_id"] in f.agent_ids)})
        assert named == list(x["expected_findings_on_replay"]), (x["id"], named)
        if x["kind"] == "translator_semantic":
            assert x["pipeline_on_the_recorded_proposal"] == {"claim_id": x["merged_claim_id"], **WITHHELD_RECORD} and named == [], x["id"]
    # every translation that reached a delivered claim was checked, and each one the translator withheld as circular
    # (E112) carries no OVS-TRN-006 or OVS-TRN-010 (rule circularity-agreement)
    checked = sum(len(a.translations) for a in audits.values())
    assert checked >= 150
    withheld = [(key, o.claim_id) for key, v in views.items() for t in v.transfers if t.receipt is not None for o in t.receipt.outcomes
                if o.translation.problem is None and any("E112" in d for d in o.translation.diagnostics)]
    named = {(key, cid) for key, a in audits.items() for f in a.report.findings if f.code in ("OVS-TRN-006", "OVS-TRN-010") for cid in f.claim_ids}
    assert not (set(withheld) & named)
    assert set(EXPECTED_WITHHELD) <= set(withheld)


@pytest.mark.timeout(1200)
def test_past_the_translators_semantic_gate_the_overseer_raises_the_pinned_faults_and_its_floor_on_the_same_encodings(rekeyed, rekeyed_past_the_gate):
    """Added after round-8 clearance c1 with the rewrite above: the assertions that test made on the two errors
    (``EXPECTED_ERRORS``, the fourth repair's), made on the same pass with the translator's semantic circularity rule off
    (``rekeyed_past_the_gate``: the translator as it was before c1, as a tampered or older translator would deliver), where
    m1.1 and m7.1 are delivered ENTAILED again with the pipeline run record version 7 recorded for them. The overseer then
    raises exactly ``EXPECTED_ERRORS`` and its floor (``EXPECTED_FLOOR_ERRORS``, decision 91), each OVS-TRN-006 citing the
    auditor's signed COUNTEREXAMPLE run, rules engine-shown and grounded-transcription, and naming exactly the premises the
    translator's E112 names when it withholds the encoding (rule circularity-agreement: the claims the semantic rule
    withholds on the shipped pipeline are exactly the claims graded here). Version 7's entries (the two pinned claims, kept
    whole by version 8) match exactly the two pinned errors; the floor's p7c h1.6 matches none (no record adjudicated it:
    the translator before c1 delivered it as AMBIGUOUS_TRANSLATION and the overseer before c1 did not grade it). Everything
    else the shipped test pins on the pass is unchanged past the gate."""
    _m, _r, _audits, views_now = rekeyed
    _replay, audits, views = rekeyed_past_the_gate
    # the translator's semantic rule withholds exactly EXPECTED_WITHHELD; its rule as written withholds the same claims both ways
    withheld_now, withheld_before = _withheld_as_circular(views_now), _withheld_as_circular(views)
    assert set(withheld_before) < set(withheld_now) and set(withheld_now) - set(withheld_before) == set(EXPECTED_WITHHELD)
    raw = json.loads(RC.ADJUDICATIONS_FILE.read_text(encoding="utf-8"))
    v7_entries = [{k: v for k, v in e.items() if k not in ("retired_in_version", "why_retired", "retirement_evidence")} for e in raw["retired"]
                  if e["retired_in_version"] == 8 and e["round"] == "r7" and e.get("pass", "genuine") == "rekeyed"]
    assert sorted((e["channel"], e["code"], (e["claim_id"],)) for e in v7_entries) == sorted(EXPECTED_ERRORS)
    for e in v7_entries:  # delivered past the gate exactly as record version 7 recorded the pipeline run
        outcomes = [o for t in views[e["channel"]].transfers if t.receipt is not None and t.report is not None and t.report.agent_id == e["agent_id"]
                    for o in t.receipt.outcomes if o.claim_id == e["claim_id"]]
        assert [RC._pipeline_record(o) for o in outcomes] == [e["evidence"]["pipeline_on_the_recorded_proposal"]], e["id"]
        assert outcomes[0].display_status.value == "ENTAILED", e["id"]
    expected = {k: EXPECTED_FLOOR_ERRORS.get(k, ()) + EXPECTED_ERRORS.get(k, ()) for k in set(EXPECTED_ERRORS) | set(EXPECTED_FLOOR_ERRORS)}
    errors = [(key, f) for key, a in audits.items() for f in a.report.findings if f.severity == "error"]
    assert {(key, f.code, tuple(f.claim_ids)) for key, f in errors} == set(expected) and len(errors) == len(expected)
    assert {(k, cid) for (k, _c, (cid,)) in expected} == set(EXPECTED_WITHHELD)
    for key, f in errors:
        k = (key, f.code, tuple(f.claim_ids))
        named = expected[k]
        assert set(named) == set(EXPECTED_WITHHELD[(key, f.claim_ids[0])]), (k, named)  # rule circularity-agreement
        assert all(pid in f.message for pid in named) and "COUNTEREXAMPLE" in f.message and "grounded-transcription" in f.message, f.message
        assert f.related_result_ids, f.message
        assert f"premise(s) {', '.join(named)}" in f.message and "engine-shown" in f.message, f.message
        assert f"names {', '.join(named)} on this IR" in f.message and "reached the receipt past that rule" in f.message and "circularity-agreement" in f.message, f.message
        if k in EXPECTED_ERRORS:  # the fourth repair's assertions, its premises now after the floor's
            own = EXPECTED_ERRORS[k]
            assert all(pid in f.message for pid in own) and f"restating premise(s) {', '.join(named)}" in f.message and ", ".join(own) in f.message, f.message
    undecided = [(key, f) for key, a in audits.items() for f in a.report.findings if f.code == "OVS-TRN-011"]
    assert {(key, tuple(f.claim_ids)) for key, f in undecided} == set(EXPECTED_UNDECIDED) and len(undecided) == len(EXPECTED_UNDECIDED)
    v7 = {"entries": v7_entries}
    false_alarms, raised = [], []
    for key, a in audits.items():
        fa, r = RC.classify_genuine_errors("r7", key, a.report.findings, v7, "rekeyed")
        false_alarms += fa
        raised += r
    assert sorted(x["entry"] for x in raised) == sorted(e["id"] for e in v7_entries)
    assert sorted((x["channel"], x["code"], tuple(x["claim_ids"])) for x in false_alarms) == sorted(set(EXPECTED_FLOOR_ERRORS) - set(EXPECTED_ERRORS))
    trn_any = Counter(f.code for a in audits.values() for f in a.report.findings if f.code.startswith("OVS-TRN"))
    assert not {c for c in trn_any if c in ("OVS-TRN-001", "OVS-TRN-002", "OVS-TRN-003", "OVS-TRN-007")}, trn_any
    assert trn_any["OVS-TRN-006"] == len(expected), trn_any
    tr010 = [(key, f) for key, a in audits.items() for f in a.report.findings if f.code == "OVS-TRN-010"]
    assert [(key, f.claim_ids) for key, f in tr010] == [("p7a", ["g4.1@economics-specialist"])] and "relying on T-q25" in tr010[0][1].message
    named = {(key, cid) for key, a in audits.items() for f in a.report.findings if f.code in ("OVS-TRN-006", "OVS-TRN-010") for cid in f.claim_ids}
    assert not (set(withheld_before) & named)


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
    from epinoic_overseer.export import export_pack
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

