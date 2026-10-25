"""The cases of accuracy round 1 (``tests/data/accuracy_round1_cases.json``), run through the public pipeline and scored
(``tests/case_scoring.py``). Each false alarm on a correct answer the round removes has a clean control here, written for
the round in wording of its own, and a defective twin that stays named:

* DV2-03: a stated rule whose sentence holds a hedge in another conjunct or in a relative clause, or an affirming frame
  ("Nobody doubts that"), is the source's rule; a hedge in the consequence itself and a doubting frame still refute it.
* DIFF3-07: a generic rule written with 'when' ("When fuel duty rises, car journeys fall") is the source's rule and the
  answer that applies it is released; a hedged 'when' rule is named.
* DIFF3-01: an explanation whose reason is a cause phrase ('because of', 'due to', 'following', 'as a result of',
  'thanks to') is no bare assertion; a judgement with no reason still is.
* DIFF3-02: the bridging link stated in a quotation, or in the reason clause of the sentence that ends 'so ...', bridges
  the leap; a leap with no bridge is still named.
* DIFF3-03: a task fact stated with a phrasal verb ('brought ... down', 'went down') beside a verb of the other direction
  is stated by the task; the opposite direction is still refuted.
* DIFF3-04: a task fact restated with a synonym is the task's fact; a fact the task does not state is still named.
* DIFF3-05: a document's approving word about another subject is no stance on the claim's subject; the document's own
  opposite stance on it is still named.
* DIFF3-06: a fact from the writer's own knowledge, when the request asks for own knowledge, is an info record, never
  lack_of_evidence; an invented universal fact is still named.
* DV2-08: 'about 300 g' for a stated 260 g, encoded at its first significant digit, is ENTAILED and released.

The file holds no path or session id; nothing from a case is executed (proposals are JSON data)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from epinoic_logic.named import DEFECT_LABELS

from .. import case_scoring as S

DATA = Path(__file__).resolve().parent.parent / "data" / "accuracy_round1_cases.json"
DOC = json.loads(DATA.read_text(encoding="utf-8"))
CASES = DOC["cases"]
DEFECTS = [c for c in CASES if c["expected_label"] != "none"]
CONTROLS = [c for c in CASES if c["expected_label"] == "none"]
#: controls whose answer the round releases where the staged tree before it held it back (an assumed second reading, a rule
#: written with 'when' read as no rule): they are clean and released
RELEASED = {"acc1_rule_ok_later_conjunct_hedge", "acc1_rule_ok_relative_clause_hedge", "acc1_rule_ok_affirming_frame", "acc1_when_ok_generic_rule",
            "acc1_when_ok_rule_after_its_result", "acc1_precision_ok_about_300_g"}


def test_the_file_is_well_formed_and_holds_no_path_or_session_id():
    assert DOC["format"] == "argdiag-accuracy-cases/1" and DOC["case_format"] == S.CASE_FORMAT
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(DEFECTS) >= 9 and len(CONTROLS) >= 17
    for c in CASES:
        assert c["case_format"] == S.CASE_FORMAT and (c["expected_label"] == "none" or c["expected_label"] in DEFECT_LABELS), c["id"]
        assert c["origin"]["source"] == "accuracy round 1 own probe" and set(c["origin"]) <= {"source", "note"}
    assert RELEASED <= {c["id"] for c in CONTROLS}
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
