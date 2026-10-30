"""The development cases (``tests/data/argdiag_dev_cases.json``) are well-formed data: canonical labels, resolvable
translation and peer sets, no path or session id, a closed provenance record, and only the development set."""
from __future__ import annotations

import json
import re

from epinoic_logic.named import DEFECT_LABELS

from .. import argdiag_cases as C

FAMILIES = {"formal", "evidence", "informal", "stem", "e2e"}


def test_the_file_is_the_development_set_in_its_format():
    doc = json.loads(C.CASES_PATH.read_text(encoding="utf-8"))
    assert doc["format"] == C.FILE_FORMAT and doc["case_format"] == C.CASE_FORMAT
    ids = C.case_ids()
    assert len(ids) == len(set(ids)) == 101
    assert not any("holdout" in i for i in ids)
    assert set(doc) == {"format", "case_format", "description", "translation_sets", "peer_sets", "cases"}


def test_every_case_is_self_contained_with_canonical_labels():
    for case in C.load_cases():
        assert case["case_format"] == C.CASE_FORMAT and case["family"] in FAMILIES
        assert case["expected_label"] == C.CONTROL or case["expected_label"] in DEFECT_LABELS, case["id"]
        assert all(label in DEFECT_LABELS for label in case["acceptable_labels"]), case["id"]
        assert isinstance(case["translations"], list) and all("proposal" in t for t in case["translations"])
        assert isinstance(case.get("peers", []), list)
        assert set(case["ids"]) >= {"task_id", "request_id", "report_id", "plan_id"} and case["modes"]
        assert "audit" not in case and "probe_file" not in case.get("origin", {})
    assert C.case_ids(controls_only=True) and C.case_ids(controls_only=False)
    assert set(C.case_ids(prefix="e2e-")) <= set(C.case_ids(family="e2e"))


ORIGIN_KEYS = {"source", "probe_id", "expected_by_audit", "bug", "task"}
ORIGIN_SOURCES = re.compile(r"argument audit, (formal|evidence|informal-stem) family|end-to-end run, item B\d{1,3}")
SHORT_ID = re.compile(r"[A-Za-z0-9-]{1,16}")
AUDIT_KEYS = {"flagged", "display", "release", "note", "named_by_any", "gap_premise", "point_status", "ideal", "predicted"}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def test_the_data_holds_no_path_or_session_id_and_its_provenance_is_closed():
    # No file path, home or scratch folder or session id enters the repository, and the provenance of a case is a closed
    # record: a free-text provenance field is where a path, a session id or the name of a tool that ran would leak.
    text = C.CASES_PATH.read_text(encoding="utf-8")
    for marker in ("/tmp/", "/home/", "/root/", "/Users/", "\\\\Users\\\\", "scratchpad", "file://", ".worktrees"):
        assert marker not in text, marker
    assert not re.search(r"session_[0-9A-Za-z]{12,}", text)
    for case in C.load_cases():
        origin = case["origin"]
        assert set(origin) <= ORIGIN_KEYS and ORIGIN_SOURCES.fullmatch(origin["source"]), case["id"]
        assert all(SHORT_ID.fullmatch(origin[k]) for k in ("probe_id", "bug", "task") if k in origin), case["id"]
        audit = origin.get("expected_by_audit", {})
        assert set(audit) <= AUDIT_KEYS and all(len(s) <= 160 for s in _strings(audit)), case["id"]


def test_a_case_resolves_its_recorded_translation_for_a_delivered_claim():
    case = C.load_case("f03_affirming_consequent")
    assert case["expected_label"] == "affirming_the_consequent" and case["family"] == "formal"
    proposal = C.proposal_for(case, "The cell must be a plant cell.")
    assert proposal is not None and proposal["problem"]["conclusion"]["expr"] == {"op": "var", "name": "plant"}
    assert C.proposal_for(case, "Nothing like this was said.") is None
    record = C.task_record(case)
    assert record.text == case["request"] and record.task_id == case["ids"]["task_id"]
    shared = [c for c in C.load_cases(C.case_ids(prefix="e2e-B")) if c["id"] in ("e2e-B2-cs", "e2e-B18-cs")]
    assert len(shared) == 2 and shared[0]["translations"] == shared[1]["translations"]       # one stored set, resolved for both
    edited = C.load_case("f03_affirming_consequent")
    edited["translations"].clear()
    assert C.load_case("f03_affirming_consequent")["translations"]                            # every load is a fresh copy
