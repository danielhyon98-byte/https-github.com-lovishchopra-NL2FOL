"""B25: the core pack sends the worked equations ('=' chains) of the non-STEM branches through the STEM chain checker, so a
worked line of Business, Economics, Geography or Psychology is decided by the engine under the STEM tolerance rule
instead of being named CORE-QNT-001 'not decided'; a derived figure a supplied text states word for word ('fell by 30%'
in i02c's extract) is a transcription and gets no CORE-QNT-001. PS-SRC-001: a study attribution whose author and year a
supplied text names is grounded by that text (c03-psych), while a named study in no text (e05b) still fires.
"""
from __future__ import annotations

import pytest

from ..stem.argdiag_hub import deliver, findings, structural
from .. import argdiag_cases as C


def _core_stem(rc) -> list:
    return [c for c in rc.formal_checks if c.constraint_id.startswith("core-stem-")]


def _worked_undecided(rc) -> list:
    return [f for f in structural(rc, "CORE-QNT-001") if "worked arithmetic" in f.message]


@pytest.mark.parametrize("case_id", ["e2e-B23-bm", "e2e-B13-ec", "e2e-B21-ge", "e2e-B13-ps"])
def test_correct_worked_lines_are_decided_with_no_core_qnt_001(case_id):
    rc = deliver(case_id)
    checks = _core_stem(rc)
    assert checks and all(c.satisfied is True for c in checks), [(c.constraint_id, c.formal_status) for c in checks]
    assert all(c.claim_ids for c in checks)
    assert _worked_undecided(rc) == [], [f.message[:120] for f in _worked_undecided(rc)]
    # rewritten to the stricter rule of repair round 2: no INT-SUBJ-001 of any kind on these correct answers (before, only the
    # stem_ ones were excluded; the subject reading of a figure no longer charges a correct line's figure to another quantity)
    assert not findings(rc, "INT-SUBJ-001"), [f.message[:120] for f in findings(rc, "INT-SUBJ-001")]


def test_a_wrong_worked_business_line_is_int_subj_001():
    case = C.load_case("e2e-B23-bm")
    wrong = case["answer"].replace("= $8,100 ÷ $2.70\n= 3,000 cakes per month", "= $8,100 ÷ $2.70\n= 3,300 cakes per month", 1)
    rc = deliver(case, answer=wrong)
    [f] = [f for f in findings(rc, "INT-SUBJ-001") if f.severity == "error"]
    assert "8,100 ÷ 2.70 = 3,300" in f.message and f.defect == "stem_arithmetic_slip" and f.claim_ids
    assert [c.constraint_id for c in _core_stem(rc) if c.satisfied is False] and not _worked_undecided(rc)


def test_control_rates_per_thousand_divided_by_ten_read_as_per_cent_as_written():
    # the STEM SI-unit companion is not built on a general branch: '(31 − 11) ÷ 10 = 2.0%' is a rate per 1,000 in per cent
    rc = deliver("e2e-B21-ge")
    assert not [c for c in rc.formal_checks if c.constraint_id.startswith("core-stem-") and c.constraint_id.endswith("u")]


def test_a_figure_the_extract_states_word_for_word_is_a_transcription():
    assert structural(deliver("i02c_control_rct_cause"), "CORE-QNT-001") == []


def test_control_an_invented_figure_is_still_named_undecided():
    assert structural(deliver("e02_invented_figure"), "CORE-QNT-001")


def test_a_study_named_in_the_supplied_text_is_grounded():
    assert structural(deliver("c03_control_psych_study"), "PS-SRC-001") == []


def test_control_a_named_study_in_no_text_still_fires():
    [f] = structural(deliver("e05b_appeal_to_authority_named_study"), "PS-SRC-001")
    assert f.defect == "uncheckable_authority" and "Hartley (2015)" in f.message
    case = C.load_case("c03_control_psych_study")
    other = case["answer"].replace("Loftus and Palmer (1974)", "Loftus and Palmer (1975)")   # the year the text does not give
    assert structural(deliver(case, answer=other), "PS-SRC-001")
