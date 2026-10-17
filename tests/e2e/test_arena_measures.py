"""The arena harness reports its measures separately (``scripts/arena/run_arena.py``; review of 12 October 2026, section 5).

The review: the harness's functional count is a transport measure; a replay that serves 24 of 224 recorded translations
must not be read as a translation regression; recorded translations that match no delivered claim must be counted and
shown, never hidden; a run that loses expected translations must fail or be visibly qualified; extracted, eligible,
attempted, completed, faithful and approved claims must be counted separately; transport, translation fidelity and
fixture coverage are never merged into one rate. Each test below encodes one of those rules, with a control where the
rule must not fire (a fully served, digest-bound round is not qualified; transport does not move when translations are
lost; an approval is not faithfulness).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402

from epinoic_logic.branches import default_registry  # noqa: E402
from epinoic_logic.translate.contracts import sha256_text  # noqa: E402

TASK = "hi-x1"
HISTORY_ITEM = {
    "task_id": TASK, "subject": "History", "agent_id": "history-specialist", "task_type": "short_answer",
    "question": "In one paragraph of no more than 200 words, outline the historical context of London in 1802 for a student "
                "reading a sonnet written that year, with dated evidence labelled from memory.",
    "supplied_texts": [],
    "response_text": "London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
                     "Coal smoke from homes and workshops hung over the city for much of the year. "
                     "Against this background, the \"smokeless air\" of the sonnet stands out as an exception to the city's ordinary condition. "
                     "The Peace of Amiens, signed in March 1802, briefly ended the war with France.",
}
_GK = {"kind": "general_knowledge", "certainty": "probable", "note": "stated from memory"}


def _fixture(claim_id: str) -> dict:
    """A translation of a History claim of HISTORY_ITEM (its verdict does not matter to these tests)."""
    return {"problem": {"ir_version": "1.0", "problem_id": f"{TASK}-{claim_id}", "request_id": f"req-{TASK}", "claim_id": claim_id, "query": "entailment",
                        "symbols": [{"name": "largest_city", "sort": "Bool", "meaning": "London in 1802 was the largest city in Europe", "grounding": _GK},
                                    {"name": "near_million", "sort": "Bool", "meaning": "London had close to a million inhabitants in 1801", "grounding": _GK}],
                        "premises": [{"id": "pr_largest", "expr": {"op": "var", "name": "largest_city"}, "label": "London in 1802 was the largest city in Europe",
                                      "grounding": _GK, "materiality": "material"}],
                        "conclusion": {"id": "concl", "expr": {"op": "and", "args": [{"op": "var", "name": "largest_city"}, {"op": "var", "name": "near_million"}]},
                                       "label": "London was the largest city in Europe, with close to a million inhabitants."}},
            "interpretation": {"reading": "The census figure is not among the premises.",
                               "glossary": [{"symbol": "largest_city", "meaning": "largest city in Europe", "grounding": None},
                                            {"symbol": "near_million", "meaning": "close to a million inhabitants", "grounding": None}]},
            "ambiguous": False, "unsupported_reason": None}


def _claims(item: dict = HISTORY_ITEM):
    """The claims the hub delivers for ``item`` (the branch's own parser), by id."""
    branch, _ = default_registry().for_subject(item["subject"])
    report = branch.parser().parse_response(item["response_text"], request_id=f"req-{item['task_id']}", task_id=item["task_id"], report_id=f"rep-{item['task_id']}-0",
                                            subject=item["subject"], task_type=item["task_type"], supplied_texts=[], agent_id=item["agent_id"])
    return {c.claim_id: c for c in report.claims}


def _round(tmp_path: Path, translations: dict | None, adjudications=None) -> dict:
    (tmp_path / "specialists").mkdir(parents=True)
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    if translations is not None:
        (tmp_path / "translations").mkdir()
        (tmp_path / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", **translations}))
    if adjudications is not None:
        (tmp_path / "adjudications").mkdir()
        (tmp_path / "adjudications" / "translation_fidelity.json").write_text(json.dumps(adjudications))
    return ra.run_round(tmp_path)


def _outcome(claim_id, display, translation="TRANSLATED", eligible=True, **kw):
    return {"claim_id": claim_id, "display_status": display, "translation_status": translation, "stale_fixture_refused": False, "eligible": eligible, **kw}


def _f(code, claim_ids, severity="error"):
    return {"code": code, "severity": severity, "claim_ids": list(claim_ids), "message": f"{code} on {claim_ids}"}


# --- the claim counts: each stage counted on its own ---------------------------------------------------------------------


def test_each_claim_stage_is_counted_on_its_own_and_approval_is_neither_completion_nor_faithfulness():
    """extracted, eligible, attempted, completed and approved are separate lists with their own rule: an ambiguous or
    withheld translation is attempted but not completed; INCONSISTENT_PREMISES is completed but not approved; ENTAILED with
    an error-level finding on the claim is not approved; NOT_ELIGIBLE is neither eligible nor attempted."""
    claims = list(_claims().values())
    assert [c.claim_id for c in claims] == ["h1.1", "h1.2", "h1.3", "h1.4"]
    outcomes = [_outcome("h1.1", "ENTAILED", ungrounded_dependencies=2),
                _outcome("h1.2", "NOT_ELIGIBLE", "NOT_ELIGIBLE", eligible=False),
                _outcome("h1.3", "ENTAILED")]
    m = ra.claim_measures(claims, outcomes, [_f("INT-REQ-007", ["h1.3"])])
    assert m["extracted"] == ["h1.1", "h1.2", "h1.3", "h1.4"]
    assert m["eligible"] == ["h1.1", "h1.3"] and m["attempted"] == ["h1.1", "h1.3"] and m["completed"] == ["h1.1", "h1.3"]
    assert m["approved"] == ["h1.1"], "an ENTAILED claim with an error-level finding on it is not approved"
    assert m["approved_resting_on_ungrounded_premises"] == ["h1.1"] and m["eligible_not_attempted"] == [] and m["eligibility_disagreements"] == []
    # attempted but not completed: ambiguous, rejected at translation (E112), refused as stale, dropped by the channel
    outcomes = [_outcome("h1.1", "AMBIGUOUS_TRANSLATION", "AMBIGUOUS_TRANSLATION"),
                _outcome("h1.3", "INVALID_FORMALIZATION", "INVALID_FORMALIZATION", translation_diagnostics=["attempt 1: E112: circular"])]
    m = ra.claim_measures(claims, outcomes, [])
    assert m["attempted"] == ["h1.1", "h1.3"] and m["completed"] == [] and m["approved"] == []
    stale = {**_outcome("h1.1", "INTERNAL_ERROR", "TRANSLATION_FAILED"), "stale_fixture_refused": True}
    m = ra.claim_measures(claims, [stale], [_f("INT-STALE-011", ["h1.3"])])
    assert m["attempted"] == ["h1.1", "h1.3"] and m["completed"] == [] and m["approved"] == []
    # a definitive verdict other than ENTAILED is completed, never approved
    m = ra.claim_measures(claims, [_outcome("h1.1", "INCONSISTENT_PREMISES"), _outcome("h1.3", "COUNTEREXAMPLE")], [])
    assert m["completed"] == ["h1.1", "h1.3"] and m["approved"] == []
    # an eligible claim with no recorded translation is eligible, not attempted
    m = ra.claim_measures(claims, [_outcome("h1.1", "ENTAILED")], [])
    assert m["eligible_not_attempted"] == ["h1.3"]


def test_release_is_counted_apart_from_approval_and_every_unresolved_dependency_is_named():
    """Integration of the review fixes (finding 2 with section 5): formal entailment and permission to release are kept
    apart in the counts too. An approved claim (displayed ENTAILED, no error on the receipt) whose proof relies on a premise
    no check validated is named among the approvals resting on an unresolved dependency even when nothing is ungrounded;
    only an outcome whose release assessment permits release counts as release permitted, never one with an error-level
    finding on the claim, never a record without an assessment, and a passing CONSISTENT check can be permitted without
    being 'approved' (which is ENTAILED only)."""
    claims = list(_claims().values())
    outcomes = [_outcome("h1.1", "ENTAILED", ungrounded_dependencies=0, unverified_dependencies=2, release_permitted=False),
                _outcome("h1.3", "ENTAILED", ungrounded_dependencies=0, unverified_dependencies=0, release_permitted=True),
                _outcome("h1.4", "CONSISTENT", release_permitted=True)]
    m = ra.claim_measures(claims, outcomes, [])
    assert m["approved"] == ["h1.1", "h1.3"] and m["approved_resting_on_ungrounded_premises"] == []
    assert m["approved_resting_on_unresolved_dependencies"] == ["h1.1"]
    assert m["release_permitted"] == ["h1.3", "h1.4"]
    # an error-level finding on the claim withholds it from both counts; a record without an assessment is never permitted
    m = ra.claim_measures(claims, [outcomes[0], outcomes[1], _outcome("h1.4", "ENTAILED")], [_f("INT-REQ-007", ["h1.3"])])
    assert m["approved"] == ["h1.1", "h1.4"] and m["release_permitted"] == []


def test_a_replay_permits_no_release_and_says_why_on_each_outcome(tmp_path):
    """A replay calls no fidelity reviewer, so the release assessment of every outcome is unresolved (and says so), and
    the round's release-permitted count is zero whatever the formal status; the summary prints the count beside the
    approvals, and the transport measure does not move."""
    out = _round(tmp_path / "rel", {"claims": {"h1.1": _fixture("h1.1")}})
    [genuine] = [r for r in out["records"] if r["variant"] == "genuine"]
    [o] = [o for o in genuine["outcomes"] if o["claim_id"] == "h1.1"]
    assert o["release_permitted"] is False and any("fidelity review" in u for u in o["release_unresolved"]), o
    cl = out["metrics"]["claims"]
    assert cl["release_permitted"] == 0 and cl["release_permitted"] <= cl["completed"]
    assert cl["approved_resting_on_ungrounded_premises"] <= cl["approved_resting_on_unresolved_dependencies"] <= cl["approved"]
    assert out["functional"] == out["transmissions"]
    summary = (tmp_path / "rel" / "summary.md").read_text()
    assert "release permitted by the release assessment (the application's rule, apart from the formal status) 0." in summary


def test_the_pipelines_own_eligibility_decides_and_a_disagreement_with_the_harness_is_named():
    claims = list(_claims().values())
    m = ra.claim_measures(claims, [_outcome("h1.2", "ENTAILED", eligible=True)], [])
    assert "h1.2" in m["eligible"] and m["eligibility_disagreements"] == ["h1.2"]


# --- fixture coverage: every recorded translation is served or lost with its reason --------------------------------------


def test_every_recorded_translation_is_served_or_lost_with_a_reason():
    claims = list(_claims().values())
    recorded = {cid: _fixture(cid) for cid in ("h1.1", "h1.2", "h1.3", "h1.4", "g9.9")}
    outcomes = [_outcome("h1.1", "COUNTEREXAMPLE"), _outcome("h1.2", "NOT_ELIGIBLE", "NOT_ELIGIBLE", eligible=False),
                {**_outcome("h1.3", "INTERNAL_ERROR", "TRANSLATION_FAILED"), "stale_fixture_refused": True}]
    cov = ra.fixture_coverage(recorded, {"h1.1": "a" * 64}, claims, outcomes, [_f("INT-STALE-011", ["h1.4"])])
    assert cov["recorded"] == 5 and cov["served"] == ["h1.1"] and cov["lost_count"] == 4
    assert cov["lost"] == {"matching_no_delivered_claim": ["g9.9"], "refused_stale": ["h1.3"], "not_eligible": ["h1.2"], "dropped_by_channel": ["h1.4"]}
    assert cov["served_with_recorded_digest"] == ["h1.1"] and cov["served_by_claim_id_only"] == []
    assert cov["translation_sha256"]["h1.1"] == ra.fixture_sha256(recorded["h1.1"]) == ra.fixture_sha256(json.loads(json.dumps(recorded["h1.1"])))
    cov = ra.fixture_coverage({"h1.1": "{}", "h1.3": "{}"}, {}, claims, [], [_f("INT-REQ-006", ["h1.1"], "warning")])
    assert cov["lost"] == {"failed_internally": ["h1.1"], "no_outcome": ["h1.3"]} and cov["served"] == []
    # a translations file whose report was never delivered loses every fixture, by name
    rc = ra.round_fixture_coverage([{"file": "hi-x1.json", "variant": "genuine", "functional": False, "error": "ValueError"}], {"hi-x1": {"claims": recorded}})
    assert (rc["recorded"], rc["served"], rc["lost"]) == (5, 0, 5) and rc["lost_by_reason"] == {"report_not_delivered": 5}


def test_a_replay_that_loses_recorded_translations_is_qualified_in_the_title_and_results_and_transport_does_not_move(tmp_path):
    """Through the hub: h1.1's translation is served, h1.2's claim is not eligible, g9.9 matches no delivered claim. The
    unserved translations are counted in the title and the Measures section (never only at the bottom), the run is
    qualified in results.json, and the transport measure is exactly that of the same round without the lost
    translations (control): coverage and transport are separate measures."""
    out = _round(tmp_path / "lost", {"claims": {"h1.1": _fixture("h1.1"), "h1.2": _fixture("h1.2"), "g9.9": _fixture("h1.1")}})
    control = _round(tmp_path / "served", {"claims": {"h1.1": _fixture("h1.1")}})
    m, mc = out["metrics"], control["metrics"]
    assert m["transport"] == mc["transport"] and out["functional"] == control["functional"] == out["transmissions"]
    cov = m["fixture_coverage"]
    assert (cov["recorded"], cov["served"], cov["lost"]) == (3, 1, 2) and cov["lost_by_reason"] == {"matching_no_delivered_claim": 1, "not_eligible": 1}
    genuine = next(r for r in out["records"] if r["variant"] == "genuine")
    assert genuine["fixture_coverage"]["served"] == ["h1.1"] and genuine["fixture_coverage"]["lost"] == {"matching_no_delivered_claim": ["g9.9"], "not_eligible": ["h1.2"]}
    assert out["qualified"] is True and [q["code"] for q in out["qualifications"]] == ["TRANSLATIONS_LOST", "FIXTURES_UNBOUND"]
    assert "2 of 3 recorded translations were not served in this run" in out["qualifications"][0]["message"]
    lines = (tmp_path / "lost" / "summary.md").read_text().split("\n")
    assert lines[0] == f"# Arena lost (QUALIFIED: 2 of 3 recorded translations not served; 1 served by claim id only)"
    measures = lines[lines.index("## Measures (each on its own denominator; none is combined with another into one rate)"):]
    cov_line = next(x for x in measures if x.startswith("- Fixture coverage"))
    assert "1 of 3 served; NOT SERVED: 2 (1 match no delivered claim id; 1 claim not eligible under the current policy)" in cov_line
    assert any(x.startswith("- QUALIFIED (TRANSLATIONS_LOST): 2 of 3 recorded translations were not served") for x in measures)
    assert lines.index("## Measures (each on its own denominator; none is combined with another into one rate)") < lines.index("| variant | functional | total |")
    # the claim counts of the same run, each its own figure
    cl = m["claims"]
    assert (cl["extracted"], cl["eligible"], cl["attempted"], cl["eligible_not_attempted"]) == (4, 2, 1, 1) and cl["faithful"] is None
    assert cl["completed"] <= cl["attempted"] and cl["approved"] <= cl["completed"]


def test_a_round_whose_translations_are_all_served_and_bound_is_not_qualified(tmp_path):
    """Control: with the claim-text digest recorded and every translation served, nothing is lost, nothing is bound by
    claim id only, the title carries no qualification and --fail-on-qualification exits 0."""
    digest = sha256_text(_claims()["h1.1"].claim_text)
    out = _round(tmp_path / "bound", {"claims": {"h1.1": _fixture("h1.1")}, "claim_text_sha256": {"h1.1": digest}})
    cov = out["metrics"]["fixture_coverage"]
    assert (cov["recorded"], cov["served"], cov["lost"], cov["served_with_recorded_digest"], cov["served_by_claim_id_only"]) == (1, 1, 0, 1, 0)
    assert out["qualified"] is False and out["qualifications"] == []
    assert (tmp_path / "bound" / "summary.md").read_text().split("\n")[0] == "# Arena bound"
    assert ra.main([str(tmp_path / "bound"), "--fail-on-qualification"]) == 0


def test_a_stale_translation_is_lost_not_served_and_the_strict_run_fails(tmp_path, capsys):
    """A recorded digest that does not match the delivered claim text: the provider refuses the fixture, so it is lost as
    stale, the claim is attempted but not completed, and --fail-on-qualification exits 1 (without the flag, 0)."""
    out = _round(tmp_path / "stale", {"claims": {"h1.1": _fixture("h1.1")}, "claim_text_sha256": {"h1.1": "0" * 64}})
    cov = out["metrics"]["fixture_coverage"]
    assert cov["served"] == 0 and cov["lost_by_reason"] == {"refused_stale": 1}
    cl = out["metrics"]["claims"]
    assert (cl["attempted"], cl["completed"], cl["approved"]) == (1, 0, 0)
    assert ra.main([str(tmp_path / "stale")]) == 0
    assert ra.main([str(tmp_path / "stale"), "--fail-on-qualification"]) == 1
    assert "FAILED: the run is qualified (--fail-on-qualification): TRANSLATIONS_LOST" in capsys.readouterr().out


def test_a_round_without_recorded_translations_says_so_and_is_not_qualified(tmp_path):
    out = _round(tmp_path / "none", None)
    assert out["metrics"]["fixture_coverage"]["recorded"] == 0 and out["qualified"] is False
    summary = (tmp_path / "none" / "summary.md").read_text()
    assert "- Fixture coverage (recorded translations served in this run): no translation is recorded for this round" in summary
    assert "- Translation fidelity (faithful translations where adjudicated): not adjudicated" in summary


# --- translation fidelity: only where adjudicated, only for what this run served -----------------------------------------


def test_fidelity_counts_only_adjudications_of_translations_this_run_served_and_an_approval_can_be_unfaithful(tmp_path):
    """An adjudication applies only to a translation this run served whose digests match; one of an unserved translation
    or of a claim with no recorded translation is listed as not applicable (and qualifies the run), never counted."""
    fixture = _fixture("h1.1")
    judgments = {"adjudicator": "translation-fidelity lens (test)", "judgments": [
        {"file": f"{TASK}.json", "claim_id": "h1.1", "verdict": "U", "cause": "B", "translation_sha256": ra.fixture_sha256(fixture)},
        {"file": f"{TASK}.json", "claim_id": "g9.9", "verdict": "faithful"},
        {"task_id": TASK, "claim_id": "h1.3", "verdict": "faithful"}]}
    out = _round(tmp_path / "adj", {"claims": {"h1.1": fixture, "g9.9": _fixture("h1.1")}}, judgments)
    fid = out["metrics"]["translation_fidelity"]
    assert (fid["recorded"], fid["adjudicated"], fid["faithful"], fid["unfaithful"], fid["rate"]) == (3, 1, 0, 1, 0.0)
    assert fid["applied"] == [{"file": f"{TASK}.json", "claim_id": "h1.1", "verdict": "unfaithful", "binding": "translation_only", "cause": "B"}]
    reasons = sorted(n["reason"] for n in fid["not_applied"])
    assert reasons[0].startswith("no translation is recorded for this claim") and "match no" not in reasons[0]
    assert reasons[1].startswith("the recorded translation was not served in this run (matching_no_delivered_claim")
    assert out["metrics"]["claims"]["faithful"] == {"faithful": 0, "adjudicated": 1}
    assert "ADJUDICATIONS_NOT_APPLIED" in [q["code"] for q in out["qualifications"]]
    summary = (tmp_path / "adj" / "summary.md").read_text()
    assert ("- Translation fidelity (faithful translations where adjudicated): 0 of 1 adjudicated translations served in this run were judged faithful (0.0%); "
            "3 adjudications recorded by translation-fidelity lens (test), 2 not applicable to this run; bound by: 1 translation only.") in summary
    # an approval and an adjudicated unfaithful translation of the same claim: a false approval, counted as such
    records = [{"file": f"{TASK}.json", "variant": "genuine", "claim_measures": {"extracted": ["h1.1"], "eligible": ["h1.1"], "attempted": ["h1.1"], "completed": ["h1.1"],
                                                                             "approved": ["h1.1"], "approved_resting_on_ungrounded_premises": [], "eligible_not_attempted": [],
                                                                             "eligibility_disagreements": []}}]
    cl = ra.round_claim_measures(records, {"status": "adjudicated", "verdicts": {f"{TASK}.json h1.1": "unfaithful"}})
    assert cl["approved"] == 1 and cl["faithful"] == {"faithful": 0, "adjudicated": 1} and cl["approved_adjudicated_unfaithful"] == [f"{TASK}.json h1.1"]


def test_an_adjudication_of_another_translation_or_claim_text_is_not_applied(tmp_path):
    fixture = _fixture("h1.1")
    text_digest = sha256_text(_claims()["h1.1"].claim_text)
    out = _round(tmp_path / "bound", {"claims": {"h1.1": fixture}}, [
        {"file": f"{TASK}.json", "claim_id": "h1.1", "verdict": "faithful", "translation_sha256": "f" * 64}])
    fid = out["metrics"]["translation_fidelity"]
    assert fid["adjudicated"] == 0 and fid["status"] == "no adjudication applies to this run"
    assert "digest mismatch" in fid["not_applied"][0]["reason"] and fid["not_applied"][0]["reason"].startswith("the translation served")
    out = _round(tmp_path / "both", {"claims": {"h1.1": fixture}}, [
        {"file": f"{TASK}.json", "claim_id": "h1.1", "verdict": "faithful", "translation_sha256": ra.fixture_sha256(fixture), "claim_text_sha256": text_digest}])
    fid = out["metrics"]["translation_fidelity"]
    assert (fid["adjudicated"], fid["faithful"], fid["bindings"]) == (1, 1, {"translation_and_claim_text": 1})
    out = _round(tmp_path / "text", {"claims": {"h1.1": fixture}}, [
        {"file": f"{TASK}.json", "claim_id": "h1.1", "verdict": "faithful", "claim_text_sha256": "e" * 64}])
    assert out["metrics"]["translation_fidelity"]["adjudicated"] == 0 and "claim text" in out["metrics"]["translation_fidelity"]["not_applied"][0]["reason"]
    # a file named without its extension is the same file
    out = _round(tmp_path / "stem", {"claims": {"h1.1": fixture}}, [{"file": TASK, "claim_id": "h1.1", "verdict": "unfaithful", "claim_text_sha256": text_digest}])
    fid = out["metrics"]["translation_fidelity"]
    assert (fid["adjudicated"], fid["unfaithful"], fid["bindings"]) == (1, 1, {"claim_text_only": 1})


def test_judgments_are_frozen_with_the_translations_they_judged(tmp_path):
    """bind_adjudications.py records, beside each judgment, the digest of the fixture judged (and the claim-text digest when
    the translations file records one); the harness then applies the judgment to that translation only. Changing the
    fixture afterwards leaves the judgment unapplied: an explicit re-judgment is needed, never a silent carry-over."""
    import bind_adjudications as ba
    fixture = _fixture("h1.1")
    digest = sha256_text(_claims()["h1.1"].claim_text)
    rd = tmp_path / "bind"
    (rd / "specialists").mkdir(parents=True)
    (rd / "translations").mkdir()
    (rd / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    (rd / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", "claims": {"h1.1": fixture}, "claim_text_sha256": {"h1.1": digest}}))
    judged = tmp_path / "judgments.json"
    judged.write_text(json.dumps([{"task": TASK, "claim_id": "h1.1", "verdict": "F"}, {"task": TASK, "claim_id": "h1.3", "verdict": "U", "cause": "D"}]))
    assert ba.main([str(rd), str(judged), "--adjudicator", "test lens"]) == 0
    written = json.loads((rd / "adjudications" / "translation_fidelity.json").read_text())
    assert written["judgments"][0] == {"file": f"{TASK}.json", "claim_id": "h1.1", "verdict": "faithful", "translation_sha256": ra.fixture_sha256(fixture),
                                       "claim_text_sha256": digest}
    assert written["judgments"][1] == {"file": f"{TASK}.json", "claim_id": "h1.3", "verdict": "unfaithful", "cause": "D"}
    assert written["without_a_recorded_fixture"] == [f"{TASK} h1.3"] and ba.main([str(rd), str(judged)]) == 2, "an existing file is kept without --force"
    fid = ra.run_round(rd)["metrics"]["translation_fidelity"]
    assert (fid["adjudicated"], fid["faithful"], fid["bindings"]) == (1, 1, {"translation_and_claim_text": 1})
    # the fixture is changed after it was judged: the judgment no longer applies
    changed = {**fixture, "interpretation": {**fixture["interpretation"], "reading": "Another reading."}}
    (rd / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", "claims": {"h1.1": changed}, "claim_text_sha256": {"h1.1": digest}}))
    fid = ra.run_round(rd)["metrics"]["translation_fidelity"]
    assert fid["adjudicated"] == 0 and any("digest mismatch" in n["reason"] for n in fid["not_applied"])


def test_malformed_conflicting_and_ambiguous_adjudications_are_never_counted():
    recorded = {"h1.1": _fixture("h1.1")}
    records = [{"file": "a.json", "task_id": "t", "variant": "genuine", "fixture_coverage": {"served": ["h1.1"], "lost": {}}, "fixture_claim_text_sha256": {}},
               {"file": "b.json", "task_id": "t", "variant": "genuine", "fixture_coverage": {"served": ["h1.1"], "lost": {}}, "fixture_claim_text_sha256": {}}]
    adj = {"source": "x", "adjudicator": None, "judgments": [
        {"file": "a.json", "claim_id": "h1.1", "verdict": "probably"},          # malformed verdict
        {"task_id": "t", "claim_id": "h1.1", "verdict": "faithful"},            # task id carried by two records
        {"file": "b.json", "claim_id": "h1.1", "verdict": "faithful"},          # conflicting verdicts on one translation
        {"file": "b.json", "claim_id": "h1.1", "verdict": "unfaithful"}]}
    fid = ra.adjudicate(adj, records, {"a": {"claims": recorded}, "b": {"claims": recorded}})
    assert fid["adjudicated"] == 0 and fid["rate"] is None and len(fid["not_applied"]) == 4
    assert ra.adjudicate(None, records, {})["status"] == "not adjudicated"


# --- the Measures section: one line per measure, each with its own denominator ---------------------------------------------


def test_the_measures_section_keeps_every_measure_on_its_own_line_with_its_own_denominator(tmp_path):
    out = _round(tmp_path / "r", {"claims": {"h1.1": _fixture("h1.1"), "g9.9": _fixture("h1.1")}})
    lines = ra.measure_lines(out["metrics"])
    heads = [x.split(" (")[0].split(":")[0] for x in lines if x.startswith("- ")]
    assert heads[:6] == ["- Transport", "- Fixture coverage", "- Translation fidelity", "- Claims", "- Latency", "- Cost"]
    t = out["metrics"]["transport"]
    transport = next(x for x in lines if x.startswith("- Transport"))
    assert transport.startswith(f"- Transport (functional transmissions): {t['functional']} of {t['transmissions']} (100.0%)")
    assert "it does not judge whether a finding is true, whether a translation is faithful or whether an answer is better" in transport
    assert "served" not in transport and "faithful translations" not in transport, "transport carries no coverage or fidelity figure"
    assert t["genuine_traffic"]["total"] + t["injected_faults"]["total"] == t["transmissions"]
    assert set(out["metrics"]) >= {"transport", "fixture_coverage", "translation_fidelity", "claims", "latency", "cost", "qualifications"}
    summary = (tmp_path / "r" / "summary.md").read_text().split("\n")
    assert summary[2].startswith(f"Transmissions: {out['transmissions']}; functional: {out['functional']} (100.0%). This is the transport measure only")


def test_percentile_is_nearest_rank():
    assert ra._percentile([5.0], 0.95) == 5.0
    assert ra._percentile(list(map(float, range(1, 21))), 0.95) == 19.0 and ra._percentile(list(map(float, range(1, 21))), 0.5) == 10.0


@pytest.mark.parametrize("value", [{"b": 1, "a": [1, 2]}, '{"a": [1, 2], "b": 1}'])
def test_fixture_digest_is_stable(value):
    assert len(ra.fixture_sha256(value)) == 64 and ra.fixture_sha256(value) == ra.fixture_sha256(value)
