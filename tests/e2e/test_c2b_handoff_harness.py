"""Round-9 clearance, second fix pass (c2b), handoff fixer: the altered quotation of the request's own words.

The parsers' rule quoted-label (the core owner's handoff 2) reads a quoted phrase introduced as a label or a definition as a
mention: maa-t15's 'Let E be "at least one blue" and F be "both blue".' no longer draws the unverifiable CORE-SRC-003. The
arena's altered_quotation mutation alters that phrase, and the channel refutes the alteration against the request's words
(INT-REQ-003, error: "the request holds all of its words but 'onely' (an altered quotation)", the rule of round-8 clearance c1,
ps-t14), but the harness expected only CORE-SRC-003 for a task with no supplied text, so c2's record turned into a miss (187 of
188). The expectation now reads the request as the text a quotation can alter: with no supplied text, an altered quotation whose
every word the request holds is expected INT-REQ-003 (stricter than the unverifiable CORE-SRC-003); every other case keeps its
expectation (``scripts/arena/test_arena_rules.py`` pins those).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402

C2 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "c2_core_material.json").read_text(encoding="utf-8"))["specialists"]


def test_an_altered_quotation_of_the_requests_words_is_expected_refuted():
    for kind, e in (("altered_quotation", "INT-REQ-003"),):
        assert ra.quotation_expectation(kind, e, own_texts=False, any_text=False, request_words=True) == "INT-REQ-003"
        assert ra.quotation_expectation(kind, e, own_texts=False, any_text=False) == "CORE-SRC-003"  # unchanged without it
    # an invented quotation is never the request's alteration; a peer text keeps mutate's expectation
    assert ra.quotation_expectation("invented_quotation", "INT-REQ-003|CORE-SRC-003", own_texts=False, any_text=False, request_words=True) == "CORE-SRC-003"
    assert ra.quotation_expectation("altered_quotation", "INT-REQ-003", own_texts=False, any_text=True, request_words=True) == "INT-REQ-003"
    it = C2["maa-t15"]
    assert ra.alters_request_words(it["response_text"], it["question"], ra.supplied(it))
    # control: a quotation whose words the request does not hold
    assert not ra.alters_request_words('The model says "the counters were drawn with replacement each time".', it["question"])


def test_a_contained_round_names_the_altered_label_by_the_requests_refutation(tmp_path):
    (tmp_path / "specialists").mkdir()
    it = dict(C2["maa-t15"])
    (tmp_path / "specialists" / "maa-t15.json").write_text(json.dumps(it, ensure_ascii=False), encoding="utf-8")
    out = ra.run_round(tmp_path, without_overseer=True)
    rec = next(r for r in out["records"] if r["variant"] == "altered_quotation")
    assert rec["expected"] == "INT-REQ-003" and rec["functional"], (rec.get("failure_reasons"), rec["expected"])
    assert [f["code"] for f in rec["named_by"]] == ["INT-REQ-003"] and "at least onely blue" in rec["named_by"][0]["message"]
    genuine = next(r for r in out["records"] if r["variant"] == "genuine")
    assert not [f for f in genuine["subject_findings"] if f["code"] == "CORE-SRC-003"], "the quoted labels are mentions (rule quoted-label)"
