"""Regression tests for the arena harness's functional rule and its reporting (run_arena.py).

They live beside the harness because tests/ belongs to the package; run them by path:
    python -I -m pytest -q scripts/arena/test_arena_rules.py

Round-4 results audit: a mutation counted as functional whenever the expected code appeared anywhere on
the receipt, so hi-p3's own CORE-SRC-003 for 'smokeless air' would have passed its three quotation
mutations even if the injected quotation had not been named; findings beyond the genuine record were
never reported; the genuine section listed error codes only, without claim ids, messages or warnings.
"""
from __future__ import annotations

import json
import sys
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
