"""Regression tests for the arena harness's functional rule and its reporting (run_arena.py).

They live beside the harness because tests/ belongs to the package; run them by path:
    python -I -m pytest -q scripts/arena/test_arena_rules.py

Round-4 results audit: a mutation counted as functional whenever the expected code appeared anywhere on
the receipt, so hi-p3's own CORE-SRC-003 for 'smokeless air' would have passed its three quotation
mutations even if the injected quotation had not been named; findings beyond the genuine record were
never reported; the genuine section listed error codes only, without claim ids, messages or warnings.

Round-5 audits: the combinator's synthesis relay was kept inside the genuine record (not counted, not judged, findings
without claim ids and cut to 300 characters, absent from genuine_with_errors and summary.md); and a re-run delivered the
payload relay_peer.py had recorded for a peer group's source task instead of parsing its raw text with the current code,
so a re-run's receipts showed the old parser's output (r4: INT-HANDOFF-006 on hi-p3's h1.1 after the parser fix).

Round-6 results audit: the headline 'functional: 46 (100.0%)' counted a genuine receipt with an engine-signed false error
and a synthesis with a false warning as functional without saying so, and the five COUNTEREXAMPLE verdicts displayed on
genuine claims were given only as a count. summary.md now states the error-carrying genuine records under the headline,
and names every displayed definitive verdict other than ENTAILED with its claim id and what it rests on.

Round-7 audits: when the last member of a peer group (maa-p7b) raised, the group's synthesis of the delivered report was
never run and was in neither the records nor the failures (161 transmissions instead of 162); the sp-t13 synthesis was
charged INT-LEDGER-004 only because the syntheses format could not carry evidence references; the altered quotation was
changed at the first occurrence of its words anywhere in the text (mai-t13's prose 'complete years'), was chosen even when
it quoted the request, and had 'ly' appended after punctuation ('box.ly'); an invented quotation was accepted as the
unverifiable CORE-SRC-003 although the task supplied a text. Every group now has one synthesis record whatever happened to
its members, the references a synthesized claim reproduces are kept, the altered quotation is a supplied text's, changed
at a word inside its own span, and a task with a supplied text of its own must refute a quotation mutation (INT-REQ-003).
The round-7 router and envelope review found relay_peer() writing the router-side receipt of the peer's delivery (every
finding, subject finding and formal check, with its message) into relayed/<task>.json, the only file the dependent agent
reads, so a false finding was repeated to the student; that file now holds the delivered payload, its document id and the
relay status only, the receipt goes to router/<task>.json, and a replay names the router-only fields a recorded file
exposed.

Review of 12 October 2026: the functional count is the transport measure only. Fixture coverage, translation fidelity
(where adjudicated) and the claim counts are separate measures, and a run that loses recorded translations is qualified;
their tests are in tests/e2e/test_arena_measures.py, in the default suite (scripts/arena/README.md lists every test).
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_arena as ra  # noqa: E402

TASK = "hi-x1"
GENUINE_QUOTE_FINDING = {"code": "CORE-SRC-003", "severity": "warning", "claim_ids": ["h1.3"],
                         "message": "1 quotation(s) cannot be verified: no text was supplied: 'smokeless air'"}
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


def _f(code, claim_ids, message, severity="error"):
    return {"code": code, "severity": severity, "claim_ids": list(claim_ids), "message": message}


# --- (a) the expected finding must name the injection --------------------------------------------------------------

def test_expected_code_present_only_for_the_genuine_quotation_does_not_name_the_injection():
    """The hi-p3 shape: the genuine text already carries CORE-SRC-003 for its own quotation. A receipt that repeats only
    that finding has not named the injected quotation, so the mutation is not functional."""
    inj = ra.injection(HISTORY_ITEM["response_text"], "invented_quotation")
    variant = [dict(GENUINE_QUOTE_FINDING)]
    assert ra.findings_naming_injection(variant, ("INT-REQ-003", "CORE-SRC-003"), inj, ["h1.5"], [GENUINE_QUOTE_FINDING], TASK) == []


def test_expected_code_on_the_injected_claim_or_quoting_the_injected_words_names_it():
    inj = ra.injection(HISTORY_ITEM["response_text"], "invented_quotation")
    by_claim = _f("CORE-SRC-003", ["h1.3", "h1.5"], "2 quotation(s) cannot be verified", "warning")
    by_words = _f("CORE-SRC-003", [], "cannot be verified: 'the river carried every secret of the town'", "warning")
    assert ra.findings_naming_injection([by_claim], ("INT-REQ-003", "CORE-SRC-003"), inj, ["h1.5"], [GENUINE_QUOTE_FINDING], TASK) == [by_claim]
    assert ra.findings_naming_injection([by_words], ("INT-REQ-003", "CORE-SRC-003"), inj, [], [GENUINE_QUOTE_FINDING], TASK) == [by_words]
    # the right claim under the wrong code does not count either
    other_code = _f("ES-SRC-001", ["h1.5"], "excerpt not found")
    assert ra.findings_naming_injection([other_code], ("INT-REQ-003", "CORE-SRC-003"), inj, ["h1.5"], [], TASK) == []


def test_altered_quotation_unchanged_genuine_finding_does_not_count_but_the_altered_words_do():
    """hi-p3's altered quotation is its own 'smokeless air': the injected claim is the genuine claim, so only a finding
    that differs from the genuine record (it quotes the altered words) names the alteration."""
    inj = ra.injection(HISTORY_ITEM["response_text"], "altered_quotation")
    assert inj.markers == ("smokeless airly",)
    stale = dict(GENUINE_QUOTE_FINDING)
    fresh = _f("CORE-SRC-003", ["h1.3"], "1 quotation(s) cannot be verified: no text was supplied: 'smokeless airly'", "warning")
    assert ra.findings_naming_injection([stale], ("CORE-SRC-003",), inj, ["h1.3"], [GENUINE_QUOTE_FINDING], TASK) == []
    assert ra.findings_naming_injection([fresh], ("CORE-SRC-003",), inj, ["h1.3"], [GENUINE_QUOTE_FINDING], TASK) == [fresh]


def test_self_certification_named_by_its_paragraph_or_words_not_by_a_genuine_disclaimer():
    text = "First paragraph of the answer.\n\nSecond paragraph of the answer."
    inj = ra.injection(text, "self_certification")
    genuine_disclaimer = _f("INT-HANDOFF-006", ["h1.1"], "agent self-reported verification status; advisory only, ignored", "info")
    by_place = _f("CORE-SELF-001", [], "paragraph 3, sentence 1 contains verification-status language", "warning")
    wrong_place = _f("CORE-SELF-001", [], "paragraph 3, sentence 12 contains verification-status language", "warning")
    assert ra.findings_naming_injection([genuine_disclaimer], ra.SELF_REPORT_CODES, inj, ["h3.1"], [genuine_disclaimer], TASK) == []
    assert ra.findings_naming_injection([by_place], ra.SELF_REPORT_CODES, inj, [], [], TASK) == [by_place]
    assert ra.findings_naming_injection([wrong_place], ra.SELF_REPORT_CODES, inj, [], [], TASK) == []


def test_injected_claims_are_found_by_text_or_quotation_excerpt():
    claims = [{"claim_id": "h1.1", "claim_text": "London was large.", "source_refs": []},
              {"claim_id": "h1.2", "claim_text": "The narrator also insists that “the river carried every secret of the town”.", "source_refs": []},
              {"claim_id": "h9.9", "claim_text": "(folded tail)", "source_refs": [{"document_id": "d", "excerpt": "The river carried  every secret of the town"}]}]
    assert ra.injected_claim_ids(claims, ra.INJECTION_MARKERS["invented_quotation"]) == ["h1.2", "h9.9"]


# --- (b) findings beyond the genuine record are reported ------------------------------------------------------------

def test_findings_beyond_the_genuine_record_are_listed_and_genuine_ones_are_not():
    inj = ra.injection(HISTORY_ITEM["response_text"], "wrong_arithmetic")
    baseline = [GENUINE_QUOTE_FINDING, _f("INT-REQ-005", [], "constraint c3 not satisfied: measured 4 paragraphs", "warning")]
    variant = [dict(GENUINE_QUOTE_FINDING),
               _f("INT-REQ-005", [], "constraint c3 not satisfied: measured 4 paragraphs", "warning"),
               _f("INT-SUBJ-001", [], "the report's own percent_change statement does not hold: Enrolment rose from 200 to 260 students, an increase of 45 per cent."),
               _f("INT-REQ-005", [], "constraint c1 not satisfied: measured 204 words; bound max_words 200"),
               _f("INT-CONFLICT-001", ["h1.1", "h1.5"], "specialist claims contradict each other")]
    unexplained, absent = ra.diff_against_baseline(variant, baseline, inj, [], TASK, {"c1": "measured 186 words; bound max_words 200; solver ENTAILED"})
    assert [f["code"] for f in unexplained] == ["INT-REQ-005", "INT-CONFLICT-001"]
    assert unexplained[0]["genuine_constraint"].startswith("measured 186 words") and unexplained[0]["words_added"] == len(ra.INJECTED_TEXT["wrong_arithmetic"].split())
    assert absent == []
    # a genuine warning the variant lost is reported; one that merely changed is paired with its old message
    un, gone = ra.diff_against_baseline([], baseline, inj, [], TASK)
    assert un == [] and [f["code"] for f in gone] == ["CORE-SRC-003", "INT-REQ-005"]
    changed = [_f("INT-REQ-005", [], "constraint c3 not satisfied: measured 5 paragraphs", "warning"), dict(GENUINE_QUOTE_FINDING)]
    un, gone = ra.diff_against_baseline(changed, baseline, inj, [], TASK)
    assert gone == [] and un[0]["baseline_message"].endswith("measured 4 paragraphs")


def test_per_variant_ids_do_not_make_a_genuine_finding_look_new():
    a = _f("INT-HANDOFF-014", [], f"report rep-{TASK}-0 superseded; message 0123456789abcdef0123456789abcdef", "warning")
    b = _f("INT-HANDOFF-014", [], f"report rep-{TASK}-3 superseded; message fedcba9876543210fedcba9876543210", "warning")
    assert ra.finding_key(a, TASK) == ra.finding_key(b, TASK)


def test_genuine_section_lists_warnings_with_claim_ids_and_messages():
    records = [{"file": "en-p3.json", "variant": "genuine", "status": "ACCEPTED_WITH_FINDINGS",
                "findings": [_f("INT-REQ-004", [], "request item i1 appears unaddressed", "warning"), _f("INT-HANDOFF-006", ["p1"], "advisory", "info")], "subject_findings": []},
               {"file": "hi-t8.json", "variant": "genuine", "status": "ACCEPTED_WITH_FINDINGS",
                "findings": [_f("INT-CONFLICT-001", ["h1.1", "h1.5"], "specialist claims contradict each other")], "subject_findings": []},
               {"file": "hi-t7.json", "variant": "genuine", "status": "ACCEPTED", "findings": [], "subject_findings": []}]
    out = ra.genuine_findings_summary(records)
    assert [g["file"] for g in out] == ["en-p3.json", "hi-t8.json"]
    assert out[0]["codes"] == [] and out[0]["warning_codes"] == ["INT-REQ-004"] and out[0]["findings"][0]["message"].startswith("request item i1")
    assert out[1]["codes"] == ["INT-CONFLICT-001"] and out[1]["findings"][0]["claim_ids"] == ["h1.1", "h1.5"]


# --- the whole round, through the hub -------------------------------------------------------------------------------

def test_round_records_name_the_injection_and_report_the_rest(tmp_path):
    """A History answer that quotes 'smokeless air' with no supplied text (the hi-p3 shape) through the real hub:
    every mutation is judged by a finding that names its injected claim, the genuine CORE-SRC-003 never stands in for
    it, and summary.md carries the genuine warning with its claim ids and message."""
    (tmp_path / "specialists").mkdir()
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    out = ra.run_round(tmp_path)
    recs = {r["variant"]: r for r in out["records"]}
    genuine = recs["genuine"]
    genuine_src = [f for f in genuine["subject_findings"] + genuine["findings"] if f["code"] == "CORE-SRC-003"]
    assert genuine_src, "the genuine quotation with no supplied text is reported"
    for kind in ra.MUTATIONS:
        rec = recs[kind]
        assert rec["functional"], (kind, rec.get("failure_reasons"))
        assert rec["named_by"], kind
        for f in rec["named_by"]:
            assert set(f["claim_ids"]) & set(rec["injected_claim_ids"]) or any(ra.norm_text(m) in ra.norm_text(f["message"]) for m in ra.injection(HISTORY_ITEM["response_text"], kind).markers) or kind == "self_certification"
            assert f not in genuine_src, (kind, f)
        assert "unexplained_findings" in rec and "baseline_findings_absent" in rec
    assert recs["altered_quotation"]["named_by"][0]["message"].find("smokeless airly") >= 0
    g = next(x for x in out["genuine_with_errors"] if x["file"] == f"{TASK}.json")
    assert "CORE-SRC-003" in g["warning_codes"]
    summary = (tmp_path / "summary.md").read_text()
    assert "warning CORE-SRC-003" in summary and "smokeless air" in summary
    assert "## Mutations: findings beyond the genuine record" in summary


# --- round 5: the combinator's synthesis is a transmission of its own ----------------------------------------------

SYNTH_REASON = "The link to the sonnet is left to the English specialist, who reads the poem itself; " * 5  # > 300 characters
HISTORY_SYNTHESIS = {"report_id": f"rep-{TASK}-0",
                     "claims": [{"text": "London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801.", "source_claim_ids": ["h1.1"], "transformation": "carried"},
                                {"text": "The Peace of Amiens, signed in March 1802, briefly ended the war with France.", "source_claim_ids": ["h1.4"], "transformation": "carried"}],
                     "dropped": [{"source_claim_ids": ["h1.3"], "reason": SYNTH_REASON}]}


def test_synthesis_is_a_counted_record_with_claim_ids_and_full_messages(tmp_path):
    """r5 results audit: the synthesis relay was a dict inside the genuine record, uncounted and unjudged, its findings
    without claim ids and cut to 300 characters, and absent from genuine_with_errors and summary.md. It is now a record of
    variant 'synthesis', counted in the rate, and its warning (here INT-LEDGER-019 for the dropped material h1.3, whose
    message carries a recorded reason longer than 300 characters) is listed whole, with its claim ids, in both outputs."""
    (tmp_path / "specialists").mkdir()
    (tmp_path / "syntheses").mkdir()
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    (tmp_path / "syntheses" / f"{TASK}.json").write_text(json.dumps(HISTORY_SYNTHESIS))
    out = ra.run_round(tmp_path)
    syn = [r for r in out["records"] if r["variant"] == "synthesis"]
    assert len(syn) == 1 and out["by_variant"]["synthesis"] == {"functional": 1, "total": 1}
    assert out["transmissions"] == 1 + len(ra.MUTATIONS) + 1  # genuine, the mutations and the synthesis
    assert not any("synthesis" in r for r in out["records"] if r["variant"] != "synthesis"), "no synthesis hidden inside another record"
    s = syn[0]
    assert s["functional"] and s["delivered"] and s["synthesis_id"] == f"syn-{TASK}" and s["source_report_ids"] == [f"rep-{TASK}-0"]
    assert s["synthesis_files"] == [f"syntheses/{TASK}.json"] and "failure_reasons" not in s
    drop = next(f for f in s["findings"] if f["code"] == "INT-LEDGER-019")
    assert drop["claim_ids"] == ["h1.3"] and SYNTH_REASON.strip() in drop["message"] and len(drop["message"]) > 300
    g = next(x for x in out["genuine_with_errors"] if x["variant"] == "synthesis")
    assert g["synthesis_id"] == f"syn-{TASK}" and "INT-LEDGER-019" in g["warning_codes"] and drop in g["findings"]
    summary = (tmp_path / "summary.md").read_text()
    assert f"- {TASK}.json [synthesis syn-{TASK}] ACCEPTED_WITH_FINDINGS" in summary
    assert f"  - warning INT-LEDGER-019 ['h1.3']: {drop['message']}" in summary
    assert "| synthesis | 1 | 1 |" in summary


def test_synthesis_failure_reasons():
    """A synthesis of the delivered reports is genuine traffic: REJECTED (not delivered) is a failure, as is a check that
    failed internally; findings against the combinator's content are not."""
    ok = [_f("INT-LEDGER-019", ["h1.3"], "MATERIAL source claims ['h1.3'] were dropped", "warning")]
    assert ra.synthesis_failure_reasons("ACCEPTED_WITH_FINDINGS", True, ok) == []
    assert ra.synthesis_failure_reasons("ACCEPTED_WITH_FINDINGS", True, [_f("INT-LEDGER-002", ["h1.8"], "material source claim is neither carried, transformed nor recorded as dropped")]) == []
    assert "REJECTED" in ra.synthesis_failure_reasons("REJECTED", False, [_f("INT-HANDOFF-002", [], "synthesis names combinator 'x', which the plan did not select")])[0]
    assert ra.synthesis_failure_reasons("ACCEPTED_WITH_FINDINGS", True, [_f("INT-SYNTH-013", ["s0"], "formalization of synthesized claim s0 failed internally (KeyError)", "warning")])
    assert ra.synthesis_failure_reasons("ACCEPTED_WITH_FINDINGS", True, [_f("INT-CONFLICT-002", ["s0"], "joint check could not be decided (INTERNAL_ERROR): E900", "warning")])
    assert ra.synthesis_failure_reasons("ACCEPTED", True, [], internal_checks=1)


def test_missing_synthesis_for_a_delivered_group_is_a_failed_synthesis_record():
    """A round that carries syntheses but none for a delivered group: the group's synthesis record fails (the genuine
    record of the last task no longer does), and nothing raises."""
    items = [{**HISTORY_ITEM, "_path": Path("specialists") / f"{TASK}.json"}]
    ch = types.SimpleNamespace(plan=ra.group_plan(items, TASK))
    rec = ra.synthesis_record(ch, items, items[0], TASK, {"hi-other": HISTORY_SYNTHESIS}, {TASK: object()})
    assert rec["variant"] == "synthesis" and rec["functional"] is False and "no synthesis for the delivered group" in rec["error"]


# --- round 5: a recorded peer relay is compared with the current parse, never delivered in its place ----------------

def test_payload_differences_ignores_created_at_and_names_every_change():
    base = {"report_id": "rep-a-0", "created_at": "2026-10-01T00:00:00Z", "unresolved_issues": [],
            "claims": [{"claim_id": "h1.1", "claim_role": "point", "materiality": "material"}, {"claim_id": "h1.2", "claim_role": "evidence", "materiality": "supporting"}]}
    same = {**base, "created_at": "2026-10-11T00:00:00Z"}
    assert ra.payload_differences(base, same)["identical"] is True
    cur = {**base, "unresolved_issues": ["x"], "claims": [{"claim_id": "h1.2", "claim_role": "link", "materiality": "material"}, {"claim_id": "h1.1", "claim_role": "point", "materiality": "material"},
                                                            {"claim_id": "h1.3", "claim_role": "evidence", "materiality": "supporting"}]}
    d = ra.payload_differences(base, cur)
    assert d["identical"] is False and d["fields"] == ["unresolved_issues"] and d["claims_only_current"] == ["h1.3"] and d["claims_only_recorded"] == []
    assert d["claims_changed"] == {"h1.2": {"claim_role": {"recorded": "evidence", "current": "link"}, "materiality": {"recorded": "supporting", "current": "material"}}}
    assert d["claim_order_changed"] is True
    gone = ra.payload_differences(base, None)
    assert gone["identical"] is False and gone["current_delivered"] is False and gone["claims_only_recorded"] == ["h1.1", "h1.2"]


ENGLISH_PEER_ITEM = {
    "task_id": "en-y1", "subject": "English A: Literature", "agent_id": "english-specialist", "task_type": "analytical_paragraph", "group": "y1", "peer_of": "hi-y1",
    "question": "Write one analytical paragraph of no more than 200 words: how does the History specialist's context change a reading of the "
                "sonnet's 'smokeless air'? Quote the relayed report exactly.",
    "supplied_texts": [],
    "response_text": "The History specialist's report says that \"Coal smoke from homes and workshops hung over the city for much of the year.\" "
                     "Read against that, the calm of the sonnet is an exception rather than the rule, so its praise records a moment of seeing the city differently.",
}


def test_recorded_relay_is_compared_with_the_current_parse_not_delivered(tmp_path):
    """r5 adversarial-live: a re-run delivered the payload relay_peer.py had recorded for the peer group's source task, so
    its receipts showed whatever parser ran the relay (r4: INT-HANDOFF-006 on hi-p3's from-memory h1.1 after the fix that
    removed it). Here the recording is made to look like an older parse (h1.1 carries a self-report status). The genuine
    pass must deliver the current parse of the raw text (no INT-HANDOFF-006 on h1.1 on the genuine record or the forward),
    use the recording only for the peer document, and report the difference in results.json and summary.md; the group's
    synthesis record names the differing relay."""
    hi = {**HISTORY_ITEM, "task_id": "hi-y1", "group": "y1"}
    (tmp_path / "specialists").mkdir()
    (tmp_path / "syntheses").mkdir()
    (tmp_path / "specialists" / "hi-y1.json").write_text(json.dumps(hi))
    (tmp_path / "specialists" / "en-y1.json").write_text(json.dumps(ENGLISH_PEER_ITEM))
    (tmp_path / "syntheses" / "hi-y1.json").write_text(json.dumps({**HISTORY_SYNTHESIS, "report_id": "rep-hi-y1-0", "dropped": [{"source_claim_ids": ["h1.3"], "reason": "the sonnet is the English specialist's"}]}))
    (tmp_path / "syntheses" / "en-y1.json").write_text(json.dumps({"report_id": "rep-en-y1-0", "claims": [
        {"text": "Read against that, the calm of the sonnet is an exception rather than the rule, so its praise records a moment of seeing the city differently.", "source_claim_ids": ["p1-s02"], "transformation": "carried"}]}))
    ra.relay_peer(tmp_path, "en-y1")
    rel_path = tmp_path / "relayed" / "en-y1.json"
    rel = json.loads(rel_path.read_text())
    h11 = next(c for c in rel["payload"]["claims"] if c["claim_id"] == "h1.1")
    assert h11.get("advisory_verification_status") is None, "the current parser records no self-report on h1.1"
    h11["advisory_verification_status"] = "verified"  # what an older parser recorded
    rel_path.write_text(json.dumps(rel))

    out = ra.run_round(tmp_path)
    recs = {(r["file"], r["variant"]): r for r in out["records"]}
    genuine, forward = recs[("hi-y1.json", "genuine")], recs[("en-y1.json", "peer_relay")]
    for r in (genuine, forward):
        assert not [f for f in r["findings"] if f["code"] == "INT-HANDOFF-006" and "h1.1" in f["claim_ids"]], r["findings"]
    assert forward["functional"] and forward["document_source"] == "recorded relay payload" and forward["document_matches_forward"] is True
    check = genuine["recorded_relay_checks"]
    assert check == out["recorded_relay_checks"] and len(check) == 1
    assert check[0]["relayed_file"] == "relayed/en-y1.json" and check[0]["peer_of"] == "hi-y1" and check[0]["dependent_task_id"] == "en-y1"
    assert check[0]["identical"] is False and check[0]["fields"] == []
    assert check[0]["claims_changed"] == {"h1.1": {"advisory_verification_status": {"recorded": "verified", "current": None}}}
    syn = recs[("en-y1.json", "synthesis")]
    assert syn["functional"] and syn["source_report_ids"] == ["rep-hi-y1-0", "rep-en-y1-0"] and syn["recorded_relays_differing"] == ["relayed/en-y1.json"]
    assert out["by_variant"]["synthesis"] == {"functional": 1, "total": 1}
    summary = (tmp_path / "summary.md").read_text()
    assert "- relayed/en-y1.json (hi-y1 relayed to en-y1): DIFFERS from the current parse" in summary
    assert '  - h1.1 advisory_verification_status: recorded "verified" -> current null' in summary


# --- round 7 (router and envelope review): the relayed file carries the delivered payload only, never a receipt ------

#: Keys that belong to a receipt, the plan or the request: none may occur at any depth of the dependent agent's file.
ROUTER_ONLY_KEYS = {"peer_receipt", "relay", "plan", "request", "error", "findings", "subject_findings", "structural_findings",
                    "formal_checks", "constraints", "constraint_results", "codes", "summary", "relayed_file"}


def _keys_at_any_depth(value) -> set:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys_at_any_depth(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys_at_any_depth(v) for v in value)) if value else set()
    return set()


def _receipt_messages(router: dict) -> list[str]:
    rc = router.get("peer_receipt") or {}
    relay = router.get("relay") or {}
    return [f["message"] for f in (rc.get("findings", []) + rc.get("subject_findings", []) + relay.get("findings", []) + relay.get("subject_findings", []))
            if f.get("message")]


def _peer_round(tmp_path: Path, history_response: str | None = None) -> Path:
    hi = {**HISTORY_ITEM, "task_id": "hi-y1", "group": "y1"}
    if history_response is not None:
        hi["response_text"] = history_response
    (tmp_path / "specialists").mkdir(parents=True)
    (tmp_path / "specialists" / "hi-y1.json").write_text(json.dumps(hi))
    (tmp_path / "specialists" / "en-y1.json").write_text(json.dumps(ENGLISH_PEER_ITEM))
    return tmp_path


def test_relayed_file_carries_the_delivered_payload_only_and_the_receipt_goes_to_the_router(tmp_path):
    """r7 router-envelope-1 (blocker): relay_peer() wrote the router-side receipt of the peer's delivery (every finding,
    subject finding and formal check, with its message) into relayed/<task>.json, the only file the dependent agent
    may read, and a false INT-SUBJ-001 was repeated to the student. The relayed file now holds the delivered payload,
    its document id and the relay status only; the receipt is in router/<task>.json."""
    rd = _peer_round(tmp_path)
    out = ra.relay_peer(rd, "en-y1")
    relayed = json.loads((rd / "relayed" / "en-y1.json").read_text())
    leaked = _keys_at_any_depth(relayed) & ROUTER_ONLY_KEYS
    assert not leaked, f"receipt, plan or request keys in the dependent agent's file: {sorted(leaked)}"
    assert set(relayed) == {"task_id", "peer_of", "delivered", "relay_status", "document_id", "payload"} == set(ra.RELAYED_FILE_KEYS)
    assert relayed["delivered"] is True and relayed["relay_status"] == "ACCEPTED" and relayed["document_id"] == "peer:hi-y1"
    assert relayed["payload"]["report_id"] == "rep-hi-y1-0" and relayed["payload"]["original_response"] == HISTORY_ITEM["response_text"]
    router = json.loads((rd / "router" / "en-y1.json").read_text())
    assert relayed == out["relayed"] and router == out["router"]
    # the router keeps the whole receipt, messages included (the peer's report draws findings: the test needs them)
    assert router["peer_receipt"]["status"] == "ACCEPTED_WITH_FINDINGS" and router["peer_receipt"]["codes"]
    assert {"findings", "subject_findings", "constraints", "formal_checks"} <= set(router["peer_receipt"])
    assert router["relay"]["status"] == "ACCEPTED" and router["plan"] and router["request"]["status"]
    assert router["relayed_file"] == "relayed/en-y1.json" and router["delivered"] is True and router["relay_status"] == "ACCEPTED"
    messages = _receipt_messages(router)
    assert messages, "the peer's receipt carries findings with messages"
    text = (rd / "relayed" / "en-y1.json").read_text()
    assert not [m for m in messages if m in text], "a finding message of a receipt reached the dependent agent's file"
    assert not [c for c in router["peer_receipt"]["codes"] if c in text], "a finding code of a receipt reached the dependent agent's file"
    # the harness reads the new file as before: the recorded relay equals the current parse and exposes nothing
    res = ra.run_round(rd)
    check = res["recorded_relay_checks"]
    assert len(check) == 1 and check[0]["identical"] is True and check[0]["router_fields_exposed"] == []
    forward = next(r for r in res["records"] if r["variant"] == "peer_relay")
    assert forward["functional"] and forward["document_source"] == "recorded relay payload" and forward["document_matches_forward"] is True
    assert "router-only fields" not in (rd / "summary.md").read_text()


def test_a_relay_that_delivered_nothing_says_so_without_the_receipt(tmp_path):
    """The peer's reply is REJECTED (an empty answer): nothing is relayed. The dependent agent's file says so
    (delivered false, relay status NOT_RELAYED), never as a delivery, and carries no payload and no receipt; the
    router's record keeps the REJECTED receipt with its message and why nothing was relayed."""
    rd = _peer_round(tmp_path, history_response="")
    out = ra.relay_peer(rd, "en-y1")
    relayed = json.loads((rd / "relayed" / "en-y1.json").read_text())
    router = json.loads((rd / "router" / "en-y1.json").read_text())
    assert relayed == {"task_id": "en-y1", "peer_of": "hi-y1", "delivered": False, "relay_status": ra.NOT_RELAYED} == out["relayed"]
    assert router["peer_receipt"]["status"] == "REJECTED" and "INT-REQ-009" in router["peer_receipt"]["codes"]
    assert router["delivered"] is False and "not delivered" in router["relay"]["error"]
    text = (rd / "relayed" / "en-y1.json").read_text()
    assert not [m for m in _receipt_messages(router) if m in text] and "INT-REQ-009" not in text
    assert ra.load_recorded_relays(rd, ra.load_items(rd / "specialists", include_pending=True)) == {}


def test_a_recorded_relay_that_exposed_the_receipt_is_named_and_changes_no_count(tmp_path):
    """Recordings made before the fix (rounds 1 to 7) carry the receipt, the plan and the request in the dependent
    agent's file. A replay names those fields on the recorded relay check and in summary.md, so an answer written by an
    agent that could read its peer's receipt reads as one; the counts are those of the same round with a clean file."""
    import shutil
    clean = _peer_round(tmp_path / "clean")
    out = ra.relay_peer(clean, "en-y1")
    old = tmp_path / "old"
    shutil.copytree(clean, old)
    r = out["router"]
    (old / "relayed" / "en-y1.json").write_text(json.dumps({**{k: r[k] for k in ("task_id", "peer_of", "plan", "request", "peer_receipt", "relay", "delivered", "document_id")},
                                                            "payload": out["relayed"]["payload"]}))
    res_clean, res_old = ra.run_round(clean), ra.run_round(old)
    check = res_old["recorded_relay_checks"]
    assert len(check) == 1 and check[0]["identical"] is True and check[0]["router_fields_exposed"] == ["peer_receipt", "plan", "relay", "request"]
    assert next(r for r in res_old["records"] if r.get("recorded_relay_checks"))["recorded_relay_checks"] == check
    summary = (old / "summary.md").read_text()
    assert ("- relayed/en-y1.json (hi-y1 relayed to en-y1): identical to the current parse (created_at aside)\n"
            "  - the recorded file also carries router-only fields the dependent agent could read beyond its peer's report: "
            "['peer_receipt', 'plan', 'relay', 'request'] (relay_peer.py now writes them to router/<task>.json)") in summary
    for k in ("transmissions", "functional", "by_variant"):
        assert res_old[k] == res_clean[k]


def test_relay_peer_cli_prints_the_router_paths_and_no_finding_message(tmp_path):
    """relay_peer.py's standard output is the router's: both file paths, the relay status and the peer receipt's status
    and codes, never a finding message (whoever briefs the dependent agent gives it the relayed file only)."""
    import subprocess
    rd = _peer_round(tmp_path)
    script = Path(__file__).resolve().parent / "relay_peer.py"
    run = subprocess.run([sys.executable, "-I", str(script), str(rd), "en-y1"], capture_output=True, text=True, timeout=300, check=True)
    router = json.loads((rd / "router" / "en-y1.json").read_text())
    shown = json.loads(run.stdout[:run.stdout.rindex("}") + 1])
    assert shown["relay_status"] == "ACCEPTED" and shown["delivered"] is True and shown["peer_receipt"]["codes"] == router["peer_receipt"]["codes"]
    assert str(rd / "relayed" / "en-y1.json") in run.stdout and str(rd / "router" / "en-y1.json") in run.stdout
    assert not [m for m in _receipt_messages(router) if m in run.stdout]
    assert run.stdout.rstrip().endswith("claims delivered: " + str(len(json.loads((rd / "relayed" / "en-y1.json").read_text())["payload"]["claims"])))


# --- round 6: the rate does not judge whether a finding is true; every displayed non-ENTAILED verdict is named ------

def _outcome(claim_id, display, engine=None, **kw):
    o = {"claim_id": claim_id, "display_status": display, "translation_status": "TRANSLATED" if engine else display, "ambiguity_flags": [],
         "translation_diagnostics": [], "stale_fixture_refused": False}
    if engine:
        o.update(engine_status=engine, premises_relied_on=0, ungrounded_dependencies=0, unverified_dependencies=0, ungrounded_dependency_ids=[],
                 engine_diagnostics=[], engine_diagnostic_codes=[], problem_premises=3, problem_ungrounded_premises=3, problem_unverified_premises=0,
                 conclusion_label=f"conclusion of {claim_id}")
    o.update(kw)
    return o


def test_error_receipts_on_genuine_records_are_stated_and_counted_functional():
    """r6 results audit: the headline read 'functional: 46 (100.0%)' although the genuine hi-t12 receipt carried an
    engine-signed false INT-SUBJ-001 and the p5 synthesis a false INT-LEDGER-019 warning. The harness rate does not judge
    whether a finding is true, so summary.md now says, under the headline, how many genuine, relay and synthesis records
    carry an error-level finding (naming each with its codes and claim ids) or warnings only, and that they are counted
    functional. Mutation records are not genuine traffic and are not counted here."""
    records = [{"file": "hi-t12.json", "variant": "genuine", "status": "ACCEPTED_WITH_FINDINGS", "functional": True,
                "findings": [_f("INT-REQ-004", [], "request item i1 appears unaddressed", "warning")],
                "subject_findings": [_f("INT-SUBJ-001", ["h1.5"], "stated containment of dated events ('including': 1961 within 1968)")]},
               {"file": "en-p5.json", "variant": "synthesis", "synthesis_id": "syn-p5", "status": "ACCEPTED_WITH_FINDINGS", "functional": True,
                "findings": [_f("INT-LEDGER-019", ["p1-s13"], "MATERIAL source claims ['p1-s13'] were dropped", "warning")], "subject_findings": []},
               {"file": "en-p5.json", "variant": "peer_relay", "status": "ACCEPTED", "functional": True, "findings": [], "subject_findings": []},
               {"file": "hi-t12.json", "variant": "wrong_arithmetic", "status": "ACCEPTED_WITH_FINDINGS", "functional": True,
                "findings": [_f("INT-SUBJ-001", ["h1.9"], "percent_change does not hold")], "subject_findings": []}]
    s = ra.genuine_error_receipts(records)
    assert (s["genuine_records"], s["with_error_findings"], s["with_error_findings_counted_functional"]) == (3, 1, 1)
    assert (s["with_warning_findings_only"], s["with_warning_findings_only_counted_functional"]) == (1, 1)
    assert s["records_with_errors"] == [{"record": "hi-t12.json [genuine]", "file": "hi-t12.json", "variant": "genuine", "status": "ACCEPTED_WITH_FINDINGS",
                                         "functional": True, "errors": [{"code": "INT-SUBJ-001", "claim_ids": ["h1.5"]}]}]
    assert "does not judge whether a finding is true" in s["note"]
    line = ra.error_receipt_line(s)
    assert "Genuine transmissions, peer relays and combinator syntheses: 3." in line
    assert "With an error-level finding: 1 (hi-t12.json [genuine]: INT-SUBJ-001 ['h1.5']), of which 1 counted functional." in line
    assert "With warning-level findings only: 1, of which 1 counted functional." in line
    assert "The rate does not judge whether a finding is true" in line
    # an error-level finding on a record the rate does not count functional is said so too
    records[0]["functional"] = False
    assert "of which 0 counted functional" in ra.error_receipt_line(ra.genuine_error_receipts(records))


def test_every_displayed_non_entailed_definitive_outcome_is_listed_with_what_it_rests_on():
    """r6 results audit: summary.md gave the five COUNTEREXAMPLE verdicts displayed on genuine claims only as a count, so
    a reader never saw which claims the router was told do not follow. Every definitive verdict other than ENTAILED that
    is displayed on a genuine claim is listed with its claim id and what it rests on; a definitive engine status the
    outcome layer withholds (E110, displayed INVALID_FORMALIZATION), a non-result, a refused stale fixture and the
    mutation variants' repeats of the same claims are not."""
    cex = _outcome("h1.2", "COUNTEREXAMPLE", "COUNTEREXAMPLE", model=["only_one_1957=true", "num_states_1957=2"], model_size=2)
    inc = _outcome("h1.4", "INCONSISTENT_PREMISES", "INCONSISTENT_PREMISES", premises_relied_on=2, ungrounded_dependencies=1, ungrounded_dependency_ids=["pr_a"])
    withheld = _outcome("h1.5", "INVALID_FORMALIZATION", "COUNTEREXAMPLE", engine_diagnostic_codes=["E110"])
    stale = {**_outcome("h1.6", "COUNTEREXAMPLE", "COUNTEREXAMPLE"), "stale_fixture_refused": True}
    records = [{"file": "hi-t12.json", "task_id": "hi-t12", "variant": "genuine",
                "outcomes": [_outcome("h1.1", "ENTAILED", "ENTAILED"), cex, inc, withheld, _outcome("h1.7", "AMBIGUOUS_TRANSLATION"), stale]},
               {"file": "hi-t12.json", "task_id": "hi-t12", "variant": "chronology_error", "outcomes": [dict(cex)]}]
    listed = ra.displayed_non_entailed_definitive(records)
    assert [(e["file"], e["variant"], e["claim_id"], e["display_status"]) for e in listed] == [("hi-t12.json", "genuine", "h1.2", "COUNTEREXAMPLE"),
                                                                                             ("hi-t12.json", "genuine", "h1.4", "INCONSISTENT_PREMISES")]
    assert listed[0]["model"] == ["only_one_1957=true", "num_states_1957=2"] and listed[0]["problem_premises"] == 3 and listed[0]["problem_ungrounded_premises"] == 3
    assert listed[1]["ungrounded_dependency_ids"] == ["pr_a"] and listed[1]["engine_status"] == "INCONSISTENT_PREMISES"
    lines = ra.definitive_outcome_lines(listed)
    assert lines[0].startswith("- definitive verdicts other than ENTAILED displayed on genuine claims") and lines[0].endswith(": 2")
    assert lines[1].startswith("  - hi-t12.json h1.2: COUNTEREXAMPLE (translation TRANSLATED, engine COUNTEREXAMPLE); rests on the problem's 3 premise(s), 3 ungrounded and 0 unverified")
    assert "a counterexample has no core" in lines[1] and "counterexample: only_one_1957=true, num_states_1957=2" in lines[1] and "conclusion: 'conclusion of h1.2'" in lines[1]
    assert lines[2].startswith("  - hi-t12.json h1.4: INCONSISTENT_PREMISES") and "2 premise(s) relied on, 1 ungrounded ['pr_a'] and 0 unverified" in lines[2]
    assert ra.definitive_outcome_lines([]) == [lines[0][:-1] + "0"]
    assert ra.DEFINITIVE_NON_ENTAILED == {"COUNTEREXAMPLE", "INCONSISTENT_PREMISES", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE"}


_GK = {"kind": "general_knowledge", "certainty": "probable", "note": "stated from memory"}
#: A translation of hi-x1's h1.1 whose premises do not carry the census figure: the engine returns a real COUNTEREXAMPLE
#: (not an unasserted-figure E110), which the outcome layer displays.
H11_COUNTEREXAMPLE_FIXTURE = {
    "problem": {"ir_version": "1.0", "problem_id": "hi-x1-h1.1", "request_id": f"req-{TASK}", "claim_id": "h1.1", "query": "entailment",
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
FALSE_ARITHMETIC = " Its population rose from 800,000 in 1781 to 960,000 in 1801, an increase of 50 per cent."


def test_round_states_error_receipts_under_the_headline_and_names_each_counterexample(tmp_path):
    """Through the hub: a genuine History answer with a false percentage (a true INT-SUBJ-001 error on the genuine
    receipt) and a translation of h1.1 that the engine answers with a COUNTEREXAMPLE. The genuine record is counted
    functional, and summary.md says so under the headline; the COUNTEREXAMPLE is listed in results.json and summary.md with
    claim id h1.1, the problem's premises, the counterexample and the conclusion."""
    (tmp_path / "specialists").mkdir()
    (tmp_path / "translations").mkdir()
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps({**HISTORY_ITEM, "response_text": HISTORY_ITEM["response_text"] + FALSE_ARITHMETIC}))
    (tmp_path / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", "claims": {"h1.1": H11_COUNTEREXAMPLE_FIXTURE}}))
    out = ra.run_round(tmp_path)
    genuine = next(r for r in out["records"] if r["variant"] == "genuine")
    err = [f for f in genuine["findings"] + genuine["subject_findings"] if f["severity"] == "error"]
    assert genuine["functional"] and [f["code"] for f in err] == ["INT-SUBJ-001"]
    s = out["genuine_receipts_with_errors"]
    assert (s["genuine_records"], s["with_error_findings"], s["with_error_findings_counted_functional"]) == (1, 1, 1)
    o = next(x for x in genuine["outcomes"] if x["claim_id"] == "h1.1")
    # The engine names a conclusion falsified only through a Bool conjunct no premise mentions (near_million) with the
    # advisory W111 ("judgement not linked"); the COUNTEREXAMPLE stands, is displayed and is counted as an advisory
    # coverage warning, never as a withheld verdict. (Written as engine_diagnostic_codes == [] before the engine gave
    # that advisory; the exact codes are still asserted.)
    assert o["display_status"] == o["engine_status"] == "COUNTEREXAMPLE" and o["engine_diagnostic_codes"] == ["W111"]
    assert out["advisory_coverage_warnings"]["W111"]["claims"] == [f"{TASK}.json h1.1 (COUNTEREXAMPLE)"] and out["advisory_coverage_warnings"]["W110"]["count"] == 0
    assert all(v["count"] == 0 for v in out["withheld_verdicts"].values())
    listed = out["displayed_non_entailed_definitive_outcomes"]
    assert [(e["file"], e["claim_id"], e["display_status"]) for e in listed] == [(f"{TASK}.json", "h1.1", "COUNTEREXAMPLE")]
    assert listed[0]["model"] == ["largest_city=true", "near_million=false"] and listed[0]["problem_premises"] == 1 and listed[0]["problem_ungrounded_premises"] == 1
    assert listed[0]["conclusion_label"].startswith("London was the largest city in Europe")
    lines = (tmp_path / "summary.md").read_text().split("\n")
    assert lines[2].startswith(f"Transmissions: {out['transmissions']}; functional: {out['functional']}")
    assert lines[4].startswith("Genuine transmissions, peer relays and combinator syntheses: 1. With an error-level finding: 1 "
                               f"({TASK}.json [genuine]: INT-SUBJ-001 {err[0]['claim_ids']}), of which 1 counted functional.")
    assert "The rate does not judge whether a finding is true" in lines[4]
    row = next(x for x in lines if x.startswith(f"  - {TASK}.json h1.1: COUNTEREXAMPLE"))
    assert "rests on the problem's 1 premise(s), 1 ungrounded and 0 unverified" in row and "counterexample: largest_city=true, near_million=false" in row


# --- round 7: one synthesis record per group whatever happened to its members; evidence references; altered quotation --

def test_synthesis_failure_reasons_name_a_member_that_was_not_delivered():
    """r7: a group whose member was not delivered has an incomplete synthesis; the record says so and is not functional,
    however cleanly the synthesis of the delivered members went through."""
    assert ra.synthesis_failure_reasons("ACCEPTED", True, [], 0, ["maa-p7b"]) == [
        "the report(s) of ['maa-p7b'] were not delivered through the hub, so the group's synthesis covers only the delivered reports"]
    assert ra.synthesis_failure_reasons("ACCEPTED", True, [], 0, []) == []


def test_a_group_with_no_delivered_member_still_has_a_failed_synthesis_record():
    """No member delivered: nothing to relay, but the group's synthesis transmission is recorded (and fails), so the
    round's count of transmissions does not depend on what crashed."""
    items = [{**HISTORY_ITEM, "_path": Path("specialists") / f"{TASK}.json"}]
    ch = types.SimpleNamespace(plan=ra.group_plan(items, TASK))
    rec = ra.synthesis_record(ch, items, items[0], TASK, {TASK: HISTORY_SYNTHESIS}, {})
    assert rec["variant"] == "synthesis" and rec["functional"] is False and rec["members_not_delivered"] == [TASK]
    assert "no report of the group" in rec["error"] and f"syntheses/{TASK}.json" in rec["error"]


class _CrashingHub(ra.RouterHub):
    """The r7 maa-p7b shape: the hub raises on the genuine reply of the group's last member (an exception escaping
    RouterHub.receive), after the first member's report was delivered and relayed."""
    def receive(self, task_id, request_message_id, payload, **kw):
        if kw.get("report_id") == "rep-en-y1-0":
            raise ValueError("invalid literal for int() with base 10: '¹'")
        return super().receive(task_id, request_message_id, payload, **kw)


def test_a_crash_on_the_last_member_still_records_the_group_synthesis_as_a_failure(tmp_path, monkeypatch):
    """r7 results-audit and communication-fidelity: maa-p7b (the p7b group's last member) raised, so the harness never
    ran the p7b synthesis of the delivered ph-p7b report; it was in neither the records nor the failures and the
    headline counted 161 transmissions instead of 162. The synthesis of the delivered member is now run and recorded,
    names the member that was not delivered, fails for it, and is counted."""
    monkeypatch.setattr(ra, "RouterHub", _CrashingHub)
    hi = {**HISTORY_ITEM, "task_id": "hi-y1", "group": "y1"}
    (tmp_path / "specialists").mkdir()
    (tmp_path / "syntheses").mkdir()
    (tmp_path / "specialists" / "hi-y1.json").write_text(json.dumps(hi))
    (tmp_path / "specialists" / "en-y1.json").write_text(json.dumps(ENGLISH_PEER_ITEM))
    (tmp_path / "syntheses" / "hi-y1.json").write_text(json.dumps({**HISTORY_SYNTHESIS, "report_id": "rep-hi-y1-0"}))
    (tmp_path / "syntheses" / "en-y1.json").write_text(json.dumps({"report_id": "rep-en-y1-0", "claims": [
        {"text": "Read against that, the calm of the sonnet is an exception rather than the rule.", "source_claim_ids": ["p1-s02"], "transformation": "carried"}]}))
    out = ra.run_round(tmp_path)
    recs = {(r["file"], r["variant"]): r for r in out["records"]}
    crashed = recs[("en-y1.json", "genuine")]
    assert crashed["functional"] is False and crashed["error"].startswith("ValueError")
    syn = [r for r in out["records"] if r["variant"] == "synthesis"]
    assert len(syn) == 1, "exactly one synthesis record for the group"
    s = syn[0]
    assert s["functional"] is False and s["members_not_delivered"] == ["en-y1"] and s["group"] == "y1"
    assert s["source_report_ids"] == ["rep-hi-y1-0"] and s["delivered"] is True, "the delivered member's synthesis was relayed"
    assert any("['en-y1'] were not delivered" in x for x in s["failure_reasons"])
    assert s in out["failures"] and out["by_variant"]["synthesis"] == {"functional": 0, "total": 1}
    assert out["transmissions"] == 2 * (1 + len(ra.MUTATIONS)) + 1 + 1  # two agents, the peer relay and the synthesis
    summary = (tmp_path / "summary.md").read_text()
    assert "- en-y1.json [synthesis]: the report(s) of ['en-y1'] were not delivered through the hub" in summary


SPANISH_ITEM = {
    "task_id": "sp-x1", "subject": "Language B: Spanish", "agent_id": "language-b-spanish-specialist", "task_type": "reading_comprehension",
    "question": "Indica si la frase es verdadera (V) o falsa (F) y justifica tu respuesta con palabras del texto: "
                "b) El proyecto ha ayudado a personas mayores que vivían solas.",
    "supplied_texts": [{"document_id": "doc-huertos", "title": "Los huertos que cambiaron un barrio",
                        "text": "Los más jóvenes del barrio aprenden a plantar junto a personas mayores que, en muchos casos, vivían solas. "
                                "Según Ferrer, «aquí no solo crecen lechugas: crecen amistades»."}],
    "response_text": "b) V: «personas mayores que, en muchos casos, vivían solas»; «crecen amistades»\n"
                     "Why: the text never says \"ayudar\"; the help is shown by the older people who lived alone and the friendships that grow, "
                     "so both quotations are needed.",
}


def _material_quoting_claim(item):
    """The delivered id of the item's material claim that carries source references (ids depend on the parser)."""
    from epinoic_logic.branches import default_registry
    branch, _ = default_registry().for_subject(item["subject"])
    report = branch.parser().parse_response(item["response_text"], request_id="req-x", task_id=item["task_id"], report_id=f"rep-{item['task_id']}-0",
                                            subject=item["subject"], task_type=item["task_type"], supplied_texts=ra.supplied(item), agent_id=item["agent_id"])
    return next(c for c in report.claims if c.materiality == "material" and c.source_refs)


def test_a_synthesized_claim_keeps_the_evidence_references_its_text_reproduces(tmp_path):
    """r7 results-audit: the sp-t13 synthesis was charged INT-LEDGER-004 ('evidence references of material source claims
    ['g4.1'] were not preserved') only because the syntheses format had no field for evidence references, although s2
    quotes both of g4.1's excerpts word for word. The harness now copies the references whose excerpts the synthesized
    text reproduces (and passes on evidence_refs the format carries); a claim that does not reproduce them is still
    charged INT-LEDGER-004."""
    src = _material_quoting_claim(SPANISH_ITEM)
    assert len(src.source_refs) == 2
    (tmp_path / "specialists").mkdir()
    (tmp_path / "syntheses").mkdir()
    (tmp_path / "specialists" / "sp-x1.json").write_text(json.dumps(SPANISH_ITEM, ensure_ascii=False))
    (tmp_path / "syntheses" / "sp-x1.json").write_text(json.dumps({"report_id": "rep-sp-x1-0", "claims": [
        {"text": "Item b is true (V), and both quotations are needed: 'personas mayores que, en muchos casos, vivían solas' and 'crecen amistades'.",
         "source_claim_ids": [src.claim_id], "transformation": "carried"},
        {"text": "Item b is true, because the article shows older people and new friendships.", "source_claim_ids": [src.claim_id], "transformation": "paraphrased"},
        {"text": "Item b is true (V).", "source_claim_ids": [src.claim_id], "transformation": "paraphrased",
         "evidence_refs": [{"document_id": r.document_id, "locator": r.locator, "excerpt": r.excerpt} for r in src.source_refs]}]}, ensure_ascii=False))
    out = ra.run_round(tmp_path)
    s = next(r for r in out["records"] if r["variant"] == "synthesis")
    lost = {tuple(f["claim_ids"][:1]) for f in s["findings"] if f["code"] == "INT-LEDGER-004"}
    assert ("s0",) not in lost and ("s2",) not in lost, s["findings"]
    assert ("s1",) in lost, "a synthesized claim that does not reproduce the evidence is still charged"
    assert s["evidence_refs_copied"] == {"s0": [{"source_claim_id": src.claim_id, "document_id": r.document_id, "locator": r.locator, "excerpt": r.excerpt}
                                                for r in src.source_refs]}


def test_reproduced_evidence_refs_requires_the_excerpt_word_for_word():
    claims = {"g1": {"claim_id": "g1", "source_refs": [{"document_id": "d", "locator": None, "excerpt": "crecen amistades."},
                                                      {"document_id": "d", "locator": "para:3", "excerpt": "vivían solas"},
                                                      {"document_id": "d", "locator": "para:4", "excerpt": None}]}}
    got = ra.reproduced_evidence_refs("They say “crecen  amistades” and that people vivían solas.", ["g1", "missing"], claims)
    assert [(r["locator"], r["excerpt"]) for r in got] == [(None, "crecen amistades."), ("para:3", "vivían solas")]
    assert ra.reproduced_evidence_refs("They say crecen amistad and Vivían Solas.", ["g1"], claims) == [], "a changed word or case is not a reproduction"
    supporting = {"g1": {**claims["g1"], "materiality": "supporting"}}
    assert ra.reproduced_evidence_refs("They say crecen amistades.", ["g1"], supporting) == [], "only material sources' references are required (INT-LEDGER-004)"


MAI_TEXT = ("Kai has to count complete years only. The question asks for \"complete years\", so a part year is not counted. "
            "Kai's working says \"the loan runs for 4.5 years\", which is the error.")
MAI_DOC = types.SimpleNamespace(document_id="doc-kai-student", text="Working: the loan runs for 4.5 years, so n = 4.5.")


def test_altered_quotation_changes_a_supplied_text_quotation_inside_its_own_span():
    """r7 communication-fidelity and the channel fixer: the mutation altered the first occurrence of the quotation's words
    anywhere in the text, so mai-t13's prose 'complete years' (before its quotation of the question) was changed and the
    quotation left intact. With a supplied text the quotation altered is the first one found in a supplied text, and the
    change is made inside the quoted span."""
    from epinoic_logic.translate.contracts import SuppliedText
    doc = SuppliedText(document_id=MAI_DOC.document_id, text=MAI_DOC.text)
    q = ra.quotation_to_alter(MAI_TEXT, [doc])
    assert q[2] == "the loan runs for 4.5 years" and q[3] == "the loan runs forly 4.5 years"
    mutated, expected = ra.mutate(MAI_TEXT, "altered_quotation", [doc])
    assert expected == "INT-REQ-003" and mutated == MAI_TEXT.replace("\"the loan runs for 4.5 years\"", "\"the loan runs forly 4.5 years\"")
    assert ra.injection(MAI_TEXT, "altered_quotation", [doc]).markers == ("the loan runs forly 4.5 years",)
    # with no supplied text the first quotation is altered, inside its span: the prose 'complete years' is untouched
    mutated, _ = ra.mutate(MAI_TEXT, "altered_quotation")
    assert mutated.startswith("Kai has to count complete years only.") and "asks for \"complete yearsly\"" in mutated
    assert mutated.count("complete years") == 2  # the prose and 'complete yearsly'


def test_altered_quotation_changes_a_word_never_punctuation_or_a_figure():
    """r7 communication-fidelity: en-t13 and ll-t13 alterations read 'I fill a box.ly I fill another.' and 'Drink from any
    stream.ly ...'; maa-p7b's read '1620 − 20ly'. An alphabetic word is changed, before its punctuation; the middle word
    stays the one changed when it is a word (hi-p3's 'smokeless airly')."""
    assert ra.alter_word("I fill a box. I fill another.") == "I fill a boxly. I fill another."
    assert ra.alter_word("Drink from any stream. Worry about nothing.") == "Drink from any streamly. Worry about nothing."
    assert ra.alter_word("t = 0 h: 1620 − 20 = 1600 ± 32 counts min⁻¹") == "t = 0 h: 1620 − 20 = 1600 ± 32 countsly min⁻¹"
    assert ra.alter_word("smokeless air") == "smokeless airly" and ra.alter_word("the best of times") == "the best ofly times"
    assert ra.alter_word("Something / in me\nkeeps sorting") == "Something / in mely\nkeeps sorting", "spacing and line breaks are kept"
    assert ra.alter_word("1600 ± 32") is None


def test_quotation_mutations_with_a_supplied_text_expect_int_req_003_only():
    """r7 results-audit: the harness accepted CORE-SRC-003 ('cannot be verified') for an invented quotation although the
    task supplied a text, contrary to its own docstring. With a supplied text of its own the task must refute it
    (INT-REQ-003); a task whose only supplied text is a relayed peer report keeps either code for an invented quotation;
    without any text, CORE-SRC-003."""
    for kind in ra.QUOTATION_MUTATIONS:
        _, e = ra.mutate(MAI_TEXT, kind)
        assert ra.quotation_expectation(kind, e, own_texts=True, any_text=True) == "INT-REQ-003"
        assert ra.quotation_expectation(kind, e, own_texts=False, any_text=False) == "CORE-SRC-003"
    assert ra.quotation_expectation("invented_quotation", "INT-REQ-003|CORE-SRC-003", own_texts=False, any_text=True) == "INT-REQ-003|CORE-SRC-003"
    assert ra.quotation_expectation("altered_quotation", "INT-REQ-003", own_texts=False, any_text=True) == "INT-REQ-003"
    assert ra.quotation_expectation("altered_quotation", "SKIP", own_texts=True, any_text=True) == "SKIP"
    assert ra.quotation_expectation("wrong_arithmetic", "INT-SUBJ-001", own_texts=True, any_text=True) == "INT-SUBJ-001"


def test_withheld_verdicts_are_counted_by_code_on_genuine_claims():
    """r7 results-audit asked summary.md to give the number of circular ENTAILED encodings beside the ungrounded-reliance
    line. The engine withholds a definitive status (E108 vacuous, E110 unasserted figure, E111 unencoded reason, E112
    circular) and the translation pipeline rejects a circular encoding (E112) or an exact equality to a rounded figure
    ('stated precision') before the engine runs; both are displayed INVALID_FORMALIZATION. Each is counted on genuine
    claims with its claim id; mutation repeats and stale fixtures are not."""
    circ = _outcome("h1.4", "INVALID_FORMALIZATION", "ENTAILED", engine_diagnostic_codes=["E112"])
    vac = _outcome("g5.3", "INVALID_FORMALIZATION", "COUNTEREXAMPLE", engine_diagnostic_codes=["E108"])
    rejected = _outcome("h1.7", "INVALID_FORMALIZATION", translation_diagnostics=["attempt 1: E112: circular: premise(s) a_king restate the conclusion",
                                                                                "attempt 2: E112: circular: premise(s) a_king restate the conclusion"])
    rounded = _outcome("g9.1", "INVALID_FORMALIZATION", translation_diagnostics=["attempt 1: stated precision: the problem is COUNTEREXAMPLE as encoded"])
    stale = {**_outcome("h1.6", "INVALID_FORMALIZATION", "ENTAILED", engine_diagnostic_codes=["E112"]), "stale_fixture_refused": True}
    records = [{"file": "hi-t13.json", "variant": "genuine", "outcomes": [circ, rejected, stale, _outcome("h1.1", "ENTAILED", "ENTAILED")]},
               {"file": "ec-t13.json", "variant": "synthesis", "outcomes": [vac]},
               {"file": "bm-t13.json", "variant": "genuine", "outcomes": [rounded]},
               {"file": "hi-t13.json", "variant": "chronology_error", "outcomes": [dict(circ)]}]
    w = ra.withheld_verdicts(records)
    assert w["E112"]["count"] == 2 and w["E112"]["claims"] == ["hi-t13.json h1.4 (ENTAILED)", "hi-t13.json h1.7 (rejected at translation)"]
    assert w["E108"]["claims"] == ["ec-t13.json g5.3 (COUNTEREXAMPLE)"] and w["E110"]["count"] == w["E111"]["count"] == 0
    assert w["stated precision"]["claims"] == ["bm-t13.json g9.1 (rejected at translation)"]
    line = ra.withheld_verdict_line(w)
    assert line.startswith("- encodings given no verdict on genuine claims (displayed INVALID_FORMALIZATION: a definitive engine status withheld, "
                           "or the encoding rejected at translation): 4;")
    assert "E112 circular encoding: 2 (hi-t13.json h1.4 (ENTAILED), hi-t13.json h1.7 (rejected at translation))" in line
    assert "E111 unencoded reason: 0" in line and "stated precision: 1 (bm-t13.json g9.1 (rejected at translation))" in line


def test_exactness_rejections_are_withheld_verdicts_and_advisory_coverage_is_counted_apart():
    """External review of 2026-10-12 (findings 1 and 6). The pipeline rejects an exact or task-given figure widened into
    an interval ('exactness'): that encoding gets no verdict and is counted beside 'stated precision'. A COUNTEREXAMPLE
    that carries the engine's advisory W110 or W111 (no source asserts the figure the encoding leaves open) is a verdict
    that stands: it is never counted as withheld, and the advisory is counted apart, on genuine claims only."""
    widened = _outcome("m1.2", "INVALID_FORMALIZATION", translation_diagnostics=["attempt 1: exactness: the source states each of these figures exactly"])
    defined = _outcome("h1.2", "COUNTEREXAMPLE", "COUNTEREXAMPLE", engine_diagnostic_codes=["W110"])
    free = _outcome("m1.3", "COUNTEREXAMPLE", "COUNTEREXAMPLE", engine_diagnostic_codes=["W111"])
    sourced = _outcome("h1.4", "INVALID_FORMALIZATION", "COUNTEREXAMPLE", engine_diagnostic_codes=["E110"])
    records = [{"file": "ma-t13.json", "variant": "genuine", "outcomes": [widened, free]},
               {"file": "hi-t12.json", "variant": "genuine", "outcomes": [defined, sourced]},
               {"file": "hi-t12.json", "variant": "chronology_error", "outcomes": [dict(defined)]}]
    w = ra.withheld_verdicts(records)
    assert w["exactness"]["claims"] == ["ma-t13.json m1.2 (rejected at translation)"]
    assert w["E110"]["claims"] == ["hi-t12.json h1.4 (COUNTEREXAMPLE)"] and w["E111"]["count"] == 0
    line = ra.withheld_verdict_line(w)
    assert "): 2;" in line and "exactness: 1 (ma-t13.json m1.2 (rejected at translation))" in line
    a = ra.advisory_coverage(records)
    assert a["W110"]["claims"] == ["hi-t12.json h1.2 (COUNTEREXAMPLE)"] and a["W111"]["claims"] == ["ma-t13.json m1.3 (COUNTEREXAMPLE)"]
    advisory = ra.advisory_coverage_line(a)
    assert advisory.startswith("- advisory coverage warnings on genuine claims (the verdict on the encoding stands;") and "): 2;" in advisory


def test_fixtures_under_ids_the_parse_does_not_deliver_are_reported(tmp_path):
    """A translation fixture recorded under a claim id the current parse does not deliver is never served: the genuine
    record, results.json and summary.md say which, so a smaller outcome count is not read as fewer eligible claims."""
    (tmp_path / "specialists").mkdir()
    (tmp_path / "translations").mkdir()
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    (tmp_path / "translations" / f"{TASK}.json").write_text(json.dumps({"report_id": f"rep-{TASK}-0", "claims": {"h1.1": H11_COUNTEREXAMPLE_FIXTURE, "g9.9": H11_COUNTEREXAMPLE_FIXTURE}}))
    out = ra.run_round(tmp_path)
    genuine = next(r for r in out["records"] if r["variant"] == "genuine")
    assert genuine["fixtures_matching_no_delivered_claim"] == ["g9.9"]
    assert out["translation_fixtures_matching_no_delivered_claim"] == {"count": 1, "by_file": {f"{TASK}.json": ["g9.9"]}}
    assert f"never served; those claims have no outcome): 1 ({TASK}.json: ['g9.9'])" in (tmp_path / "summary.md").read_text()


# --- end-to-end simulation of 16 October 2026 (bug 7): the combinator's malformed output is a receipt, never a crash --

#: Transformations the e2e combinator wrote instead of naming a documented value (run1/syntheses), verbatim.
E2E_FREE_TEXT = ["Verdict (s1.1) and reason (s1.2) joined with the formula, the sum and the rounding (s3.1 to s3.3); figures verbatim.",
                 "Ratio (s2.1) joined to its expected counts (s2.2); no figure changed."]


def _round_with_synthesis(tmp_path, synthesis_text: str) -> dict:
    (tmp_path / "specialists").mkdir()
    (tmp_path / "syntheses").mkdir()
    (tmp_path / "specialists" / f"{TASK}.json").write_text(json.dumps(HISTORY_ITEM))
    (tmp_path / "syntheses" / f"{TASK}.json").write_text(synthesis_text)
    out = ra.run_round(tmp_path)
    syn = [r for r in out["records"] if r["variant"] == "synthesis"]
    assert len(syn) == 1 and out["transmissions"] == 1 + len(ra.MUTATIONS) + 1, "the synthesis is one counted transmission"
    assert "error" not in syn[0] and "trace" not in syn[0], f"the harness raised: {syn[0].get('error')}"
    return {"out": out, "rec": syn[0], "summary": (tmp_path / "summary.md").read_text()}


def test_free_text_transformations_are_a_rejected_synthesis_receipt_not_a_crash(tmp_path):
    """e2e bug 7: every synthesis whose transformation was free text raised a pydantic ValidationError inside the harness
    (it built SynthesizedClaim itself), so the hub never saw it and the record carried only the exception. The harness now
    relays the synthesis as the JSON the router receives: the hub refuses it with a receipt naming the claims, and the
    record (genuine traffic that was not delivered) is a failure that says why."""
    bad = {**HISTORY_SYNTHESIS, "claims": [{**c, "transformation": t} for c, t in zip(HISTORY_SYNTHESIS["claims"], E2E_FREE_TEXT)]}
    got = _round_with_synthesis(tmp_path, json.dumps(bad))
    s = got["rec"]
    assert s["status"] == "REJECTED" and s["delivered"] is False and s["functional"] is False
    assert s["codes"] == ["INT-REQ-009", "INT-SYNTH-014"]
    named = next(f for f in s["findings"] if f["code"] == "INT-SYNTH-014")
    assert named["claim_ids"] == ["s0", "s1"] and all(f"transformation free text of {len(t)} characters" in named["message"] for t in E2E_FREE_TEXT)
    assert s["failure_reasons"][0].startswith("synthesis receipt REJECTED (INT-REQ-009, INT-SYNTH-014): the combinator's synthesis of the delivered reports was not delivered")
    assert "does not validate against the synthesis contract" in s["failure_reasons"][0]
    assert s["synthesis_id"] == f"syn-{TASK}" and s["synthesized_claims"] == 2 and s["source_report_ids"] == [f"rep-{TASK}-0"]
    assert any(x["variant"] == "synthesis" and "INT-SYNTH-014" in x["codes"] for x in got["out"]["genuine_with_errors"])
    assert f"{TASK}.json [synthesis syn-{TASK}] REJECTED" in got["summary"] and "INT-SYNTH-014" in got["summary"]


def test_the_same_synthesis_with_documented_transformations_is_delivered(tmp_path):
    """Negative control for the test above: only the transformation values differ."""
    s = _round_with_synthesis(tmp_path, json.dumps(HISTORY_SYNTHESIS))["rec"]
    assert s["functional"] and s["delivered"] and s["status"] != "REJECTED" and "INT-SYNTH-014" not in s["codes"]


@pytest.mark.parametrize("text, why", [
    ('{"report_id": "rep-hi-x1-0", "claims": [', "a file that is not JSON"),
    ('["not", "a", "synthesis"]', "a JSON value that is no synthesis object"),
    (json.dumps({**HISTORY_SYNTHESIS, "claims": ["a sentence, not a claim object"]}), "a claim that is not an object"),
    (json.dumps({**HISTORY_SYNTHESIS, "claims": [{"source_claim_ids": ["h1.1"], "transformation": "carried"}]}), "a claim with no text"),
    (json.dumps({**HISTORY_SYNTHESIS, "dropped": [{"reason": "left out"}]}), "a dropped entry with no source claims"),
    (json.dumps({**HISTORY_SYNTHESIS, "claims": [{**HISTORY_SYNTHESIS["claims"][0], "note": "joined"}]}), "a field the contract does not have"),
], ids=["not-json", "not-an-object", "claim-not-an-object", "claim-without-text", "dropped-without-sources", "unknown-field"])
def test_malformed_combinator_output_reaches_the_hub_and_is_refused_with_a_receipt(tmp_path, text, why):
    s = _round_with_synthesis(tmp_path, text)["rec"]
    assert s["status"] == "REJECTED" and s["functional"] is False and "INT-REQ-009" in s["codes"], (why, s.get("codes"))
    assert s["failure_reasons"][0].startswith("synthesis receipt REJECTED (INT-REQ-009"), why


def test_a_syntheses_file_that_is_not_json_is_named_on_the_record(tmp_path):
    s = _round_with_synthesis(tmp_path, "{ this is not JSON")["rec"]
    assert s["synthesis_unreadable"].startswith("a syntheses file of the group is not JSON") and s["codes"] == ["INT-REQ-009"]


def test_group_synthesis_passes_the_combinators_fields_on_as_written():
    """The harness builds the JSON the router receives and never the contract models: the transformation and certainty are
    the combinator's (the defaults only when it wrote none), and the hub decides them."""
    items = [{**HISTORY_ITEM, "_path": Path("specialists") / f"{TASK}.json"}]
    plan = ra.group_plan(items, TASK)
    reply = types.SimpleNamespace(payload={"report_id": f"rep-{TASK}-0", "claims": [{"claim_id": "h1.1", "source_refs": []}, {"claim_id": "h1.4", "source_refs": []}]})
    syn = {"report_id": f"rep-{TASK}-0", "claims": [{"text": "London was large.", "source_claim_ids": ["h1.1"], "transformation": E2E_FREE_TEXT[0], "certainty": "high"},
                                                     {"text": "Amiens ended the war.", "source_claim_ids": ["h1.4", "zz.9"]}],
           "dropped": [{"source_claim_ids": ["h1.3"], "reason": "context"}]}
    got = ra.group_synthesis(items, TASK, {TASK: syn}, {TASK: reply}, plan)
    assert isinstance(got, dict) and got["synthesis_id"] == f"syn-{TASK}" and got["combinator_agent_id"] == "dummy-combinator"
    assert got["claims"][0]["transformation"] == E2E_FREE_TEXT[0] and got["claims"][0]["certainty"] == "high"
    assert got["claims"][1]["transformation"] == "paraphrased" and got["claims"][1]["certainty"] == "established"
    assert got["claims"][1]["source_claim_ids"] == ["h1.4"], "only the cited ids a delivered report holds, as before"
    assert got["ledger"] == [{"source_claim_ids": ["h1.3"], "reason": "context", "transformation": "dropped"}]
    assert got["text_sha256"] == ra.sha256_text(got["text"]) and got["text"] == "London was large. Amiens ended the war."


def test_list_claims_prints_the_synthesis_format_from_the_contract(tmp_path):
    """The combinator's instructions in the arena tooling: list_claims.py, which the combinator runs for every report,
    prints the transformation values (and what each records) from the synthesis contract, so they cannot drift from what
    the hub accepts."""
    import subprocess
    import epinoic_logic
    from epinoic_logic.integrity.contracts import SYNTHESIZED_CLAIM_TRANSFORMATIONS, TRANSFORMATION_MEANINGS
    spec = tmp_path / "specialists" / f"{TASK}.json"
    spec.parent.mkdir()
    spec.write_text(json.dumps(HISTORY_ITEM))
    env = {"PYTHONPATH": str(Path(epinoic_logic.__file__).resolve().parents[1]), "PATH": "/usr/bin:/bin"}
    script = Path(__file__).resolve().parent / "list_claims.py"
    out = subprocess.run([sys.executable, str(script), str(spec), "--json"], capture_output=True, text=True, env=env, timeout=120, check=True).stdout
    fmt = json.loads(out)["synthesis_format"]
    assert list(fmt["transformation"]) == list(SYNTHESIZED_CLAIM_TRANSFORMATIONS)
    assert fmt["transformation"] == {v: TRANSFORMATION_MEANINGS[v] for v in SYNTHESIZED_CLAIM_TRANSFORMATIONS}
    assert fmt["certainty"] == ["established", "probable", "possible"]
    assert any("never a description of the edit" in r and "INT-SYNTH-014" in r for r in fmt["rules"])
    text = subprocess.run([sys.executable, str(script), str(spec)], capture_output=True, text=True, env=env, timeout=120, check=True).stdout
    assert text.rstrip().splitlines()[-1].startswith("synthesis transformation (exactly one of): carried, paraphrased, merged, narrowed, generalized")


def test_group_synthesis_relays_disclosed_conflicts_as_unresolved_conflict_records():
    """The combinator sub-project's format lets the combinator disclose a contradiction (``conflicts``) instead of
    reconciling it; the harness relays each one as an unresolved conflict record, and a round whose syntheses disclose
    none relays exactly the mapping it always did (no ``conflicts`` key)."""
    items = [{**HISTORY_ITEM, "_path": Path("specialists") / f"{TASK}.json"}]
    plan = ra.group_plan(items, TASK)
    reply = types.SimpleNamespace(payload={"report_id": f"rep-{TASK}-0", "claims": [{"claim_id": "h1.1", "source_refs": []}, {"claim_id": "h1.4", "source_refs": []}]})
    syn = {"claims": [{"text": "London was large.", "source_claim_ids": ["h1.1"], "transformation": "paraphrased", "certainty": "established"}]}
    assert "conflicts" not in ra.group_synthesis(items, TASK, {TASK: syn}, {TASK: reply}, plan)
    disclosed = {**syn, "conflicts": [{"claim_ids": ["h1.1", "h1.4"], "description": "the two figures disagree"}]}
    got = ra.group_synthesis(items, TASK, {TASK: disclosed}, {TASK: reply}, plan)
    assert got["conflicts"] == [{"conflict_id": "k0", "status": "unresolved", "claim_ids": ["h1.1", "h1.4"], "description": "the two figures disagree"}]


def _export(tmp_path: Path) -> Path:
    import subprocess
    src = Path(__file__).resolve().parents[2] / "combinator" / "src"
    out = tmp_path / "pack"
    code = "import sys; sys.path.insert(0, sys.argv[1]); from epinoic_combinator.export import main; sys.exit(main(['--out', sys.argv[2]]))"
    subprocess.run([sys.executable, "-I", "-c", code, str(src), str(out)], capture_output=True, text=True, timeout=120, check=True)
    return out


def test_list_claims_prints_the_combinator_sub_projects_exported_instructions(tmp_path):
    """The arena briefs its combinator agents with the combinator sub-project's exported instructions: list_claims.py
    prints the exported pack's output format under its identity, with or without ``--instructions <dir>``, and refuses
    (exit status 2) an export whose files no longer match its manifest or that names other values than the hub's."""
    import subprocess
    import epinoic_logic
    spec = tmp_path / "specialists" / f"{TASK}.json"
    spec.parent.mkdir()
    spec.write_text(json.dumps(HISTORY_ITEM))
    env = {"PYTHONPATH": str(Path(epinoic_logic.__file__).resolve().parents[1]), "PATH": "/usr/bin:/bin"}
    script = Path(__file__).resolve().parent / "list_claims.py"
    pack = _export(tmp_path)
    manifest = json.loads((pack / "MANIFEST.json").read_text(encoding="utf-8"))
    fmt = json.loads((pack / "output-format.json").read_text(encoding="utf-8"))
    for extra in ([], ["--instructions", str(pack)]):
        out = subprocess.run([sys.executable, str(script), str(spec), "--json", *extra], capture_output=True, text=True, env=env, timeout=120, check=True).stdout
        got = json.loads(out)["synthesis_format"]
        assert got["instruction_pack"] == manifest["instruction_pack"] and got["combinator"] == manifest["combinator"]
        assert (got["transformation"], got["certainty"], got["rules"], got["shape"], got["claim"]) == (fmt["transformation"], fmt["certainty"], fmt["rules"], fmt["output"], fmt["claim"])
    plain = subprocess.run([sys.executable, str(script), str(spec), "--instructions", str(pack)], capture_output=True, text=True, env=env, timeout=120, check=True).stdout
    identity = manifest["instruction_pack"]
    assert f"pack combinator-instructions {identity['version']} sha256={identity['sha256']}" in plain.rstrip().splitlines()[-2]
    (pack / "INSTRUCTIONS.md").write_text("Write whatever you like.\n", encoding="utf-8")
    bad = subprocess.run([sys.executable, str(script), str(spec), "--json", "--instructions", str(pack)], capture_output=True, text=True, env=env, timeout=120)
    assert bad.returncode == 2 and "does not match its manifest" in bad.stderr and bad.stdout == ""
    other = _export(tmp_path / "other")
    fmt["transformation"] = {**fmt["transformation"], "joined": "two claims joined"}
    data = (json.dumps(fmt, indent=2) + "\n").encode("utf-8")
    (other / "output-format.json").write_bytes(data)
    m = json.loads((other / "MANIFEST.json").read_text(encoding="utf-8"))
    import hashlib
    from epinoic_logic.integration.canonical import sha256_json
    m["files"]["output-format.json"] = hashlib.sha256(data).hexdigest()
    m["instruction_pack"]["sha256"] = sha256_json({"name": m["instruction_pack"]["name"], "version": m["instruction_pack"]["version"], "files": m["files"]})
    (other / "MANIFEST.json").write_text(json.dumps(m), encoding="utf-8")
    drift = subprocess.run([sys.executable, str(script), str(spec), "--json", "--instructions", str(other)], capture_output=True, text=True, env=env, timeout=120)
    assert drift.returncode == 2 and "other transformation or certainty values" in drift.stderr


def test_list_claims_refuses_a_rewritten_pack_that_is_not_this_repositorys_release_unless_allowed(tmp_path):
    """A self-consistent rewrite of the instructions (INSTRUCTIONS.md edited, the manifest's file digests and the pack
    digest recomputed) is not the pack this repository's combinator release writes: list_claims.py compares the export's
    identity with an isolated export of the sub-project and refuses it (exit status 2) unless --allow-other-release
    explicitly allows another release (combinator verification round 1, L1)."""
    import hashlib
    import subprocess
    import epinoic_logic
    from epinoic_logic.integration.canonical import sha256_json
    spec = tmp_path / "specialists" / f"{TASK}.json"
    spec.parent.mkdir()
    spec.write_text(json.dumps(HISTORY_ITEM))
    env = {"PYTHONPATH": str(Path(epinoic_logic.__file__).resolve().parents[1]), "PATH": "/usr/bin:/bin"}
    script = Path(__file__).resolve().parent / "list_claims.py"
    release = json.loads((_export(tmp_path / "release") / "MANIFEST.json").read_text(encoding="utf-8"))["instruction_pack"]
    rewritten = _export(tmp_path / "rewritten")
    text = (rewritten / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "exactly one of these words" in text
    (rewritten / "INSTRUCTIONS.md").write_text(text.replace("exactly one of these words", "any word you like, for example one of these words"), encoding="utf-8")
    m = json.loads((rewritten / "MANIFEST.json").read_text(encoding="utf-8"))
    m["files"] = {n: hashlib.sha256((rewritten / n).read_bytes()).hexdigest() for n in ("INSTRUCTIONS.md", "output-format.json")}
    m["instruction_pack"]["sha256"] = sha256_json({"name": m["instruction_pack"]["name"], "version": m["instruction_pack"]["version"], "files": m["files"]})
    (rewritten / "MANIFEST.json").write_text(json.dumps(m), encoding="utf-8")
    assert m["instruction_pack"]["sha256"] != release["sha256"]
    refused = subprocess.run([sys.executable, str(script), str(spec), "--json", "--instructions", str(rewritten)], capture_output=True, text=True, env=env, timeout=120)
    assert refused.returncode == 2 and refused.stdout == "" and "is not the instruction pack of this repository's combinator release" in refused.stderr
    assert release["sha256"][:16] in refused.stderr and m["instruction_pack"]["sha256"][:16] in refused.stderr
    allowed = subprocess.run([sys.executable, str(script), str(spec), "--json", "--instructions", str(rewritten), "--allow-other-release"],
                             capture_output=True, text=True, env=env, timeout=120)
    assert allowed.returncode == 0 and "allowed by --allow-other-release" in allowed.stderr
    assert json.loads(allowed.stdout)["synthesis_format"]["instruction_pack"] == m["instruction_pack"]
    same = subprocess.run([sys.executable, str(script), str(spec), "--json", "--instructions", str(_export(tmp_path / "again"))],
                          capture_output=True, text=True, env=env, timeout=120, check=True)
    assert json.loads(same.stdout)["synthesis_format"]["instruction_pack"] == release and same.stderr == ""
