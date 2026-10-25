"""The cases of accuracy round 2 (``tests/data/accuracy_round2_cases.json``), run through the public pipeline and scored
(``tests/case_scoring.py``). Each false alarm or miss of round 1's readings that round 2 removes has a clean control here,
written for the round in wording of its own, beside a defective twin that stays named:

* V1I-01 (EVD-SRC-006): a document whose approving clause names only the stance's holder, or that speaks of the claim's
  subject in a sentence of its own with no listed stance word, is no opposite stance; a document whose every statement
  about it approves, or that approves of it by an object pronoun ("welcomed it"), is still named.
* V1I-02 and V1-RESTATE-SUSPENDED (EVD-SRC-001, EVD-SRC-005): a task fact stated with a phrasal verb the closed lists do
  not hold, or restated with a synonym of its verb, raises no warning (the restatement is recorded at info, still
  unvalidated); the opposite direction is still refuted, and a premise that states as done what the task says was only
  expected is still named unchecked_source.
* V1I-03 and V1-BARE-CIRCULAR (ARG-CIRC-003): a cause phrase that only restates the point is a circle; a cause phrase that
  names a cause is clean.
* V1I-05: a source rule applied to the place the question names ("in County W") is the source's rule, and the answer is
  released as on the committed base.
* V1I-07 (ARG-NS-003): a "so" sentence whose reason states a step of the writer's own is no unbridged leap; the reason itself
  joined to the conclusion by "so" is still named.
* EVD-AUTH-001: an authority cue that introduces a quotation located in the supplied text names the source's authority;
  an appeal to unnamed experts is still named.
* V1I-04, V1-STEM-GIV-FA and V1I-06 (STEM): a conclusion drawn from the value before its rounding, a value from subject
  knowledge (a boiling point, the speed of sound) and a converted Geography sum are clean; a conclusion drawn from the rounded
  value, a miscopied given and a Geography sum of kilometres and metres are named.

The file holds no path or session id; nothing from a case is executed (proposals are JSON data)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from epinoic_logic.named import DEFECT_LABELS

from .. import case_scoring as S

DATA = Path(__file__).resolve().parent.parent / "data" / "accuracy_round2_cases.json"
DOC = json.loads(DATA.read_text(encoding="utf-8"))
CASES = DOC["cases"]
DEFECTS = [c for c in CASES if c["expected_label"] != "none"]
CONTROLS = [c for c in CASES if c["expected_label"] == "none"]
#: controls the staged tree before the round held back and the committed base releases: clean and released
RELEASED = {"acc2_rule_ok_instance_place"}
#: controls whose task-authority premise restates the task's words: recorded at info by the code named, never charged, and
#: still not releasable on the unvalidated premise
RECORDED = {"acc2_task_ok_short_synonym": "EVD-SRC-001"}


def test_the_file_is_well_formed_and_holds_no_path_or_session_id():
    assert DOC["format"] == "argdiag-accuracy-cases/1" and DOC["case_format"] == S.CASE_FORMAT
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(DEFECTS) >= 10 and len(CONTROLS) >= 12
    for c in CASES:
        assert c["case_format"] == S.CASE_FORMAT and (c["expected_label"] == "none" or c["expected_label"] in DEFECT_LABELS), c["id"]
        assert all(label in DEFECT_LABELS for label in c.get("acceptable_labels", [])), c["id"]
        assert c["origin"]["source"] == "accuracy round 2 own probe" and set(c["origin"]) <= {"source", "note"}
    assert RELEASED <= {c["id"] for c in CONTROLS} and set(RECORDED) <= {c["id"] for c in CONTROLS}
    text = DATA.read_text(encoding="utf-8")
    for marker in ("/tmp/", "/home/", "/root/", "scratchpad", "file://", ".worktrees"):
        assert marker not in text, marker
    assert not re.search(r"session_[0-9A-Za-z]{12,}", text)


def _explain(result: dict) -> str:
    return "; ".join(f"{m['mode']}={m['verdict']} flags={[f['code'] for f in m['flags']][:8]} labels={[h['label'] for h in m['labels_hit']][:8]}"
                     + (f" CRASH {m['crash']}" if m.get("crash") else "") for m in result["modes"])


@pytest.mark.parametrize("case", DEFECTS, ids=[c["id"] for c in DEFECTS])
def test_each_defective_twin_is_named_with_its_label(case):
    result = S.run_case(case)
    assert result["verdict"] == "named", _explain(result)


@pytest.mark.parametrize("case", CONTROLS, ids=[c["id"] for c in CONTROLS])
def test_each_correct_answer_is_clean(case):
    result = S.run_case(case)
    assert result["verdict"] == "control_clean", _explain(result)
    if case["id"] in RELEASED:
        assert all(m["not_releasable"] is False for m in result["modes"]), _explain(result)
    if case["id"] in RECORDED:
        code = RECORDED[case["id"]]
        for m in result["modes"]:
            hits = [h for h in m["labels_hit"] if h["code"] == code]
            assert hits and all(h["severity"] == "info" for h in hits), _explain(result)
            assert m["not_releasable"] is True, _explain(result)
