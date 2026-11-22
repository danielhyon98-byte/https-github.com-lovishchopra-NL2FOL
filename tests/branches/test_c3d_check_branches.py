"""Check round 10 of the c3d follow-up, branches lens, on the recorded D9/D10 answers (``d9d10_hub.recorded``), each expected value
fixed here:

1. Geography (c2/ge-p9c): a correct total of the request's two rainfall figures ("74 mm of rain in total (38 + 36)") was read as a
   misread request figure (geography-request-figure COUNTEREXAMPLE and INT-SUBJ-004). A total, and a figure a worked bracket follows
   a few words later, is derived, never a restated figure; a plain misread figure of the request is still named.
2. The answer quoting its own wording with the first letter's case changed ('Fix the agreement first. In short, "fix the agreement
   first".') is no invented quotation (INT-REQ-003): the own-wording reader matches case-insensitively, as its contract says.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import pytest

from . import d9d10_hub as H


def _new(name: str, extra: str):
    base = H.recorded(name)
    got = H.recorded(name, H.RECORDED[name][0] + "\n\n" + extra)
    before = {(f.code, f.message) for f in base.findings}
    checks = {(fc.constraint_id, fc.formal_status) for fc in base.formal_checks}
    return ([(f.code, f.severity) for f in got.findings if (f.code, f.message) not in before and f.severity in ("error", "warning")],
            [(fc.constraint_id, fc.formal_status) for fc in got.formal_checks if (fc.constraint_id, fc.formal_status) not in checks])


def test_a_correct_total_of_the_requests_figures_is_no_misread_figure():
    findings, checks = _new("c2/ge-p9c", "The two storms brought 74 mm of rain in total (38 + 36).")
    assert findings == []
    assert not [c for c in checks if c[0].startswith("geography-request-figure")], checks
    assert all(status == "ENTAILED" for _cid, status in checks), checks


@pytest.mark.parametrize("extra", ["The two storms brought 74 mm of rain altogether.", "The storms brought 74 mm of rain combined."])
def test_a_total_named_in_words_is_derived_too(extra):
    findings, checks = _new("c2/ge-p9c", extra)
    assert ("INT-SUBJ-004", "warning") not in findings and not [c for c in checks if c[0].startswith("geography-request-figure")], (findings, checks)


def test_control_a_misread_request_figure_is_still_named():
    findings, checks = _new("c2/ge-p9c", "Storm 1 brought 48 mm of rain.")
    assert ("INT-SUBJ-004", "warning") in findings
    assert ("geography-request-figure-1", "COUNTEREXAMPLE") in checks


@pytest.mark.parametrize("name, extra", [
    ("c3/sp-t16", 'Fix the agreement first. In short, "fix the agreement first".'),
    ("c2/ge-t15", 'Ostrel now depends more on imports. In short, "ostrel now depends more on imports".'),
    ("c2/ge-t15", 'Imports now matter more. In short, "Imports now matter more".'),
])
def test_the_answer_quoting_its_own_wording_in_another_case_is_no_invented_quotation(name, extra):
    findings, _checks = _new(name, extra)
    assert ("INT-REQ-003", "error") not in findings, findings


@pytest.mark.parametrize("name, extra", [
    ("c3/sp-t16", 'Fix the agreement first. In short, "fix the tenses before anything else".'),
    ("c2/ge-t15", 'Ostrel now depends more on imports. In short, "ostrel now exports most of its grain".'),
])
def test_control_a_quotation_the_answer_never_wrote_is_still_charged(name, extra):
    findings, _checks = _new(name, extra)
    assert ("INT-REQ-003", "error") in findings, findings


# 3. A worked difference after a labelled comparand with a possessive ("higher than Storm 1's (16.2 − 5.4)") is read like any worked
#    bracket; a word figure the answer credits to the request or the teacher ("You asked for about 1,500 words", "The question asks for a
#    model answer of about 800 words", "Your teacher set a limit of 350 words") is one the request states; a Spanish per cent change
#    with its from-to pair in brackets ("ha crecido un 36 % (de 212 a 268 vecinos)") is read like the pair after a comma.

@pytest.mark.parametrize("name, extra, wrong", [
    ("c2/ge-p9c", "Storm 2's peak discharge was 11.8 m³ s⁻¹ higher than Storm 1's (16.2 − 5.4).", True),
    ("c2/ge-p9c", "Storm 2's peak discharge was 10.8 m³ s⁻¹ higher than Storm 1's (16.2 − 5.4).", False),
    ("c1/ge-t14", "You asked for about 1,500 words for the two sections together.", True),
    ("c1/ge-t14", "You asked for about 900 words for the two sections together.", False),
    ("c3/ge-t16", "The question asks for a model answer of about 800 words.", True),
    ("c3/ge-t16", "The question asks for a model answer of about 500 words.", False),
    ("c3/sp-p10d", "Your teacher set a limit of 350 words.", True),
    ("c3/sp-p10d", "Your teacher set a limit of 250 words.", False),
    ("c1/sp-t14", "Desde 2015 la población ha crecido un 36 % (de 212 a 268 vecinos).", True),
    ("c1/sp-t14", "Desde 2015 la población ha crecido un 26 % (de 212 a 268 vecinos).", False),
])
def test_a_misstated_figure_is_named_and_the_right_one_is_free(name, extra, wrong):
    findings, checks = _new(name, extra)
    failed = [c for c in checks if c[1] == "COUNTEREXAMPLE"]
    if wrong:
        assert failed and any(code in ("INT-SUBJ-001", "INT-SUBJ-004") for code, _sev in findings), (findings, checks)
    else:
        assert not failed and not findings, (findings, checks)
