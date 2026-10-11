"""HI-CHR-001 structural proxy: pairs dates only inside one clause of the 'came after' pattern."""
from __future__ import annotations

from epinoic_logic.adapters.history_specialist import HistorySpecialistAdapter, fixtures, structural_checks
from epinoic_logic.adapters.history_specialist.parser import chronology_findings_in

CLEAN_SENTENCE = (
    "The last majority government, Hermann Müller's grand coalition, broke apart in March 1930 over the deficit in the "
    "unemployment insurance fund, a dispute the Depression had created, and his successor Heinrich Brüning governed by "
    "emergency decree under Article 48 after the Reichstag rejected his budget in July 1930."
)


def test_clean_multi_clause_sentence_is_not_a_chronology_violation():
    assert chronology_findings_in(CLEAN_SENTENCE) is None
    report = HistorySpecialistAdapter().parse_response(fixtures.EXAMPLE1_FULL_ESSAY, request_id="r", task_id="t", report_id="rep-full")
    assert "HI-CHR-001" not in {f.code for f in structural_checks(report)}


def test_true_violation_in_one_clause_is_still_caught():
    bad = "The vote fell in November 1931, which came only after the breakthrough of July 1932."
    assert chronology_findings_in(bad) == (1931 * 12 + 11, 1932 * 12 + 7)
    ok = "The vote fell in November 1932, which came only after the breakthrough of July 1932."
    assert chronology_findings_in(ok) is None
    # a clause boundary between the dates and the phrase stops the pairing
    assert chronology_findings_in("Prices rose in March 1930; the budget fell after the vote of July 1930.") is None
    assert chronology_findings_in("The fall came only after the Depression had made the party the largest in Germany.") is None
