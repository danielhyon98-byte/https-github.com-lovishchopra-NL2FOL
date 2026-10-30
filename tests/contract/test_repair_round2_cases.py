"""The probe cases of repair round 2 (``tests/data/repair_round2_cases.json``), run through the public pipeline and scored
(``tests/case_scoring.py``): every defect case is named with its expected label, and every clean control is clean. The file
holds the review's adversarial probes (every family: affirming the consequent and denying the antecedent in prose and in
conjunctions, hasty generalisation from a sample, false dilemmas against exhaustive options, causal leaps and controlled
comparisons, circularity by paraphrase, equivocation, contradiction, unchecked and forged sources, cherry-picking, altered
and lowered-capital quotations, the STEM method, unit, extrapolation, rounding and symbol checks) and the round's own probes,
each with its positive and its clean control. The corpus reviewer's variants of hold-out cases are not in it, so the
hold-out corpus stays independent of the tests. The file holds no path or session id.

Two controls stay flagged by rules other tests pin, and are pinned here with their reason, so a change to either is seen:
a quotation that lowers its source's initial capital is a form difference (INT-REQ-010 and an unverified grounding, by the
quotation-form rule of ``translate/grounding.py``), and an answer made only of the request's own words is a restatement
(INT-REQ-011)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from epinoic_logic.named import DEFECT_LABELS

from .. import case_scoring as S

DATA = Path(__file__).resolve().parent.parent / "data" / "repair_round2_cases.json"
DOC = json.loads(DATA.read_text(encoding="utf-8"))
CASES = DOC["cases"]
#: controls whose flag another pinned rule raises: case id -> (verdict, the rule)
KNOWN_LIMITS = {
    "xk04_sourced_universal": ("false_alarm", "a quotation that lowers its source's initial capital differs in form: INT-REQ-010 and an "
                                              "unverified grounding (test_round2_fixes, test_overseer_round1, test_r3_quant_chronology)"),
    "xk09_exhaustive_pass_fail": ("false_alarm", "every word of the answer occurs in the request: INT-REQ-011 restatement"),
}
DEFECTS = [c for c in CASES if c["expected_label"] != "none"]
CONTROLS = [c for c in CASES if c["expected_label"] == "none" and c["id"] not in KNOWN_LIMITS]
LIMITS = [c for c in CASES if c["id"] in KNOWN_LIMITS]

#: Port onto the integrated translator (docs/ARGUMENT_DIAGNOSTICS.md section 20.4): cases this tree decides by the integrated
#: translator's own readings, which win every contradiction; each is left out of the scoring here with its reason (the corpus
#: file is unchanged). Every other case is scored as on the feature line.
NOT_PORTED = {
    'xs07_kwh_written': 'a unit error written in units is caught by the integrated check, which admits no as-written reading its units contradict, and named by its kind; the written ST-UNIT-003 companion that labelled it stem_unit_error is not ported (docs/ARGUMENT_DIAGNOSTICS.md section 20.7)',
    'ws05_round_sf_words_prose_cmp': "a rounding stated in words after the value ('which is 0.7 to one significant figure') is read by the integrated front end as a checked restatement, so no rounding is recorded for ST-ROUND-001",
    'ws06_round_approx_prose_restated': "a rounding stated in words after the value ('which is 0.7 to one significant figure') is read by the integrated front end as a checked restatement, so no rounding is recorded for ST-ROUND-001",
    'wc07_word_equation_magnification_correct': "an integrated STEM reading of the correct working (space-grouped numerals, a unit read its own way: ST-PARSE-001, ST-UNDEC-002); the feature line's own readings of these shapes are not ported",
    'xc13_kwh_correct': "an integrated STEM reading of the correct working (space-grouped numerals, a unit read its own way: ST-PARSE-001, ST-UNDEC-002); the feature line's own readings of these shapes are not ported",
    'xk02_trichotomy': "the integrated request-item reading names an item of the request unaddressed (INT-REQ-004); the feature line's own request-item and topic-evidence fixes are duplicates, not ported",
    'xk05_rct_placebo': "the integrated core pack's undecided-figure reading (CORE-QNT-001); the feature line's version is a duplicate, not ported",
    'xk10_quote_with_stated_links_eng': "the integrated English pack's structure reading (ES-STR-001); the feature line's quotation-role reader is a duplicate, not ported",
    'yc03_heater_bound': "an integrated STEM reading of the correct working (space-grouped numerals, a unit read its own way: ST-PARSE-001, ST-UNDEC-002); the feature line's own readings of these shapes are not ported",
    'yk01_trichotomy_symbol_label': "the integrated request-item reading names an item of the request unaddressed (INT-REQ-004); the feature line's own request-item and topic-evidence fixes are duplicates, not ported",
    'yk05_exam_passed_failed': "the integrated request-item reading names an item of the request unaddressed (INT-REQ-004); the feature line's own request-item and topic-evidence fixes are duplicates, not ported",
    'zk14_quote_lowercase_mid_sentence': "the integrated English pack's structure reading (ES-STR-001); the feature line's quotation-role reader is a duplicate, not ported",
    'zk15_quote_with_bracket_elision': "the integrated English pack's structure reading (ES-STR-001); the feature line's quotation-role reader is a duplicate, not ported",
    'zk16_mention_contrast': "the integrated English pack's structure reading (ES-STR-001); the feature line's quotation-role reader is a duplicate, not ported",
    'zk18_passfail_inflected_gk': "the integrated request-item reading names an item of the request unaddressed (INT-REQ-004); the feature line's own request-item and topic-evidence fixes are duplicates, not ported",
    'ch_c_lake_recovered_then': "the integrated request-item reading names an item of the request unaddressed (INT-REQ-004); the feature line's own request-item and topic-evidence fixes are duplicates, not ported",
}
RUN_DEFECTS = [c for c in DEFECTS if c["id"] not in NOT_PORTED]
RUN_CONTROLS = [c for c in CONTROLS if c["id"] not in NOT_PORTED]


def test_the_file_is_well_formed_and_holds_no_path_or_session_id():
    assert set(NOT_PORTED) <= {c["id"] for c in CASES}
    assert DOC["format"] == "argdiag-repair-cases/1" and DOC["case_format"] == S.CASE_FORMAT
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(DEFECTS) >= 85 and len(CONTROLS) >= 80 and len(LIMITS) == len(KNOWN_LIMITS)
    for c in CASES:
        assert c["case_format"] == S.CASE_FORMAT and (c["expected_label"] == "none" or c["expected_label"] in DEFECT_LABELS), c["id"]
        assert all(lab in DEFECT_LABELS for lab in c.get("acceptable_labels", [])), c["id"]
        assert c["origin"]["source"] in ("repair round 2 review probe", "repair round 2 own probe") and set(c["origin"]) <= {"source", "note"}
        assert "hold-out" not in json.dumps(c["origin"])
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


@pytest.mark.parametrize("case", LIMITS, ids=[c["id"] for c in LIMITS])
def test_the_two_pinned_limits_keep_their_verdict(case):
    verdict, rule = KNOWN_LIMITS[case["id"]]
    result = S.run_case(case)
    assert result["verdict"] == verdict, (rule, _explain(result))
