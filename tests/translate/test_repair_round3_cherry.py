"""Repair round 3, evidence family: a sub-window read as the period's trend when the data after it run back
(V3-CHERRY-ESS-UNNAMED). EVD-CHERRY-001 used to fire only when the period's own end values contradict the stated direction;
a rise read from 2012-2013 (3.4 to 5.0) for "recovered over 2012-2020", when the series falls back to 3.8 by 2020, kept a
rising pair of end values (3.4 to 3.8) and was never named. The rule now also names a window that stops before the
period's end when the period's end value runs back against the direction from the window's last value. The control: the
same window, with a series that keeps rising after it."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S

from ..evidence_support import assert_message_hygiene, deliver, diagnostics, outcome
from .test_repair_round2_evidence import _trend_case

MODES = ("report", "text")
FALLS_BACK = "Table 3: the firm's annual sales (units). 2012: 3.4. 2013: 5.0. 2014: 4.6. 2016: 4.2. 2018: 4.0. 2020: 3.8."
KEEPS_RISING = "Table 3: the firm's annual sales (units). 2012: 3.4. 2013: 5.0. 2014: 5.2. 2016: 5.3. 2018: 5.5. 2020: 5.6."
WINDOW = "Sales recovered from 3.4 in 2012 to 5.0 in 2013."


@pytest.mark.parametrize("delivery", MODES)
def test_a_window_whose_rise_the_later_data_undo_is_cherry_picked_data(delivery):
    case = _trend_case(table=FALLS_BACK, period="between 2012 and 2020", evidence=WINDOW, verb="recovered",
                       points=[("s12", "3.4", "2012"), ("s13", "5.0", "2013")])
    _case, rc = deliver(case, delivery)
    [d] = diagnostics(rc, "EVD-CHERRY-001")
    assert d.defect == "cherry_picked_data" and d.severity == "warning"
    assert "5 for 2013" in d.message and "3.8 for 2020" in d.message and "falls back" in d.message
    assert_message_hygiene([d])
    assert outcome(rc, d.claim_ids[0]).display_status is S.ENTAILED   # the diagnosis never changes the display


@pytest.mark.parametrize("delivery", MODES)
def test_a_window_whose_rise_the_later_data_continue_is_clean(delivery):
    case = _trend_case(table=KEEPS_RISING, period="between 2012 and 2020", evidence=WINDOW, verb="recovered",
                       points=[("s12", "3.4", "2012"), ("s13", "5.0", "2013")])
    _case, rc = deliver(case, delivery)
    assert diagnostics(rc, "EVD-CHERRY-001") == []


def test_a_fall_read_from_a_window_that_the_later_data_undo_is_named_too():
    table = "Table 3: the firm's annual sales (units). 2012: 5.0. 2013: 3.4. 2014: 3.9. 2016: 4.3. 2018: 4.6. 2020: 4.8."
    case = _trend_case(table=table, period="between 2012 and 2020", evidence="Sales fell from 5.0 in 2012 to 3.4 in 2013.", verb="fell",
                       points=[("s12", "5.0", "2012"), ("s13", "3.4", "2013")], rising=False)
    _case, rc = deliver(case, "report")
    [d] = diagnostics(rc, "EVD-CHERRY-001")
    assert "climbs back" in d.message and "4.8 for 2020" in d.message
