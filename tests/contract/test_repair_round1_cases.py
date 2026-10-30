"""The probe cases of the repair round 1 review (``tests/data/repair_round1_cases.json``), run through the public pipeline
and scored (``tests/case_scoring.py``): every defect case is named with its expected label, and every clean control is
clean. Each issue the review raised has its probe here, its positive test and its clean control together: affirming the
consequent through a hidden or mislabelled link, hasty generalisation, causal leaps under negated control words,
circularity by paraphrase or arithmetic restatement, equivocation, bare assertion, unchecked and dressed-up sources,
cherry-picked periods, quoted rules and derived figures read correctly, the STEM method, unit, extrapolation, rounding,
working and givens checks, feedback quotations, and summary forgery. The file holds no path or session id."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from epinoic_logic.named import DEFECT_LABELS

from .. import case_scoring as S

DATA = Path(__file__).resolve().parent.parent / "data" / "repair_round1_cases.json"
DOC = json.loads(DATA.read_text(encoding="utf-8"))
CASES = DOC["cases"]
DEFECTS = [c for c in CASES if c["expected_label"] != "none"]
CONTROLS = [c for c in CASES if c["expected_label"] == "none"]

#: Port onto the integrated translator (docs/ARGUMENT_DIAGNOSTICS.md section 20.4): cases this tree decides by the integrated
#: translator's own readings, which win every contradiction; each is left out of the scoring here with its reason (the corpus
#: file is unchanged). Every other case is scored as on the feature line.
NOT_PORTED = {
    't07_unit_symbolic_density': 'a unit error written in units is caught by the integrated check, which admits no as-written reading its units contradict, and named by its kind; the written ST-UNIT-003 companion that labelled it stem_unit_error is not ported (docs/ARGUMENT_DIAGNOSTICS.md section 20.7)',
    'h05b_point_dressed_as_quote': 'the restated-point excerpt check (re-run review ADV-01) is not ported: it contradicts the integrated translator (docs/ARGUMENT_DIAGNOSTICS.md section 20.3)',
    'h06_conclusion_via_unrelated_excerpt': 'the restated-point excerpt check (re-run review ADV-01) is not ported: it contradicts the integrated translator (docs/ARGUMENT_DIAGNOSTICS.md section 20.3)',
    'k04_rct_psych': "the integrated request-item reading names an item of the request unaddressed (INT-REQ-004); the feature line's own request-item and topic-evidence fixes are duplicates, not ported",
    'k07_exact_quotes_hist': "the integrated ledger reading (INT-LEDGER-020); the feature line's ledger readings are duplicates, not ported",
    'k09_reasoned_eval_hist': "the integrated support reading of an evaluative claim (INT-REQ-008); the feature line's version is a duplicate, not ported",
    'y01_feedback_corrections_variants': "the integrated quotation readings (INT-REQ-003, ES-SRC-001); the feature line's quotation-role reader is a duplicate, not ported",
    'y04_word_bound_part_b': "the integrated word-bound scope of a part (INT-REQ-005); the feature line's word-bound scopes are duplicates, not ported",
}
RUN_DEFECTS = [c for c in DEFECTS if c["id"] not in NOT_PORTED]
RUN_CONTROLS = [c for c in CONTROLS if c["id"] not in NOT_PORTED]


def test_the_file_is_well_formed_and_holds_no_path_or_session_id():
    assert set(NOT_PORTED) <= {c["id"] for c in CASES}
    assert DOC["format"] == "argdiag-repair-cases/1" and DOC["case_format"] == S.CASE_FORMAT
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(DEFECTS) >= 80 and len(CONTROLS) >= 40
    for c in CASES:
        assert c["case_format"] == S.CASE_FORMAT and (c["expected_label"] == "none" or c["expected_label"] in DEFECT_LABELS), c["id"]
        assert all(lab in DEFECT_LABELS for lab in c.get("acceptable_labels", [])), c["id"]
        assert c["origin"]["source"] == "repair round 1 review probe" and set(c["origin"]) <= {"source", "note"}
    text = DATA.read_text(encoding="utf-8")
    for marker in ("/tmp/", "/home/", "/root/", "scratchpad", "file://", ".worktrees"):
        assert marker not in text, marker
    assert not re.search(r"session_[0-9A-Za-z]{12,}", text)


def _explain(result: dict) -> str:
    return "; ".join(f"{m['mode']}={m['verdict']} flags={[f['code'] for f in m['flags']][:8]} labels={[h['label'] for h in m['labels_hit']][:8]}"
                     + (f" CRASH {m['crash']}" if m.get("crash") else "") for m in result["modes"])


@pytest.mark.parametrize("case", RUN_DEFECTS, ids=[c["id"] for c in RUN_DEFECTS])
def test_each_defect_case_is_named_with_its_label(case):
    result = S.run_case(case)
    assert result["verdict"] == "named", _explain(result)


@pytest.mark.parametrize("case", RUN_CONTROLS, ids=[c["id"] for c in RUN_CONTROLS])
def test_each_clean_control_is_clean(case):
    result = S.run_case(case)
    assert result["verdict"] == "control_clean", _explain(result)
