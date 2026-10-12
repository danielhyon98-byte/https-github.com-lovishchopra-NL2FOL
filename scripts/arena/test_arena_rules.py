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
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

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
    assert o["display_status"] == o["engine_status"] == "COUNTEREXAMPLE" and o["engine_diagnostic_codes"] == []
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
