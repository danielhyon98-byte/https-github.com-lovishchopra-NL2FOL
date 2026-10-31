"""The diagnosis section of a claim summary never displaces a line the summary shows without it.

The summary is bounded (``outcome.SUMMARY_MAX_CHARS``) and is cut at its end. The diagnosis section stands right after the
verification lines, so a full section (a heading and six lines of up to 400 characters) used to push the failed grounding
checks and the structural findings out of the bounded summary: the English example's ES-SRC-001 error was no longer
named in it. The section now gets the room the other lines leave: fewer lines ("- and N more"), then shorter ones, with
blocking diagnostics (warning or error by effective severity) listed before the info records. The record itself
(``named_diagnostics``) always keeps every diagnostic.
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine import argument as argument_module
from epinoic_logic.engine.statuses import SCOPE_STATEMENT
from epinoic_logic.named import SECTION_HEADING, named_diagnostic
from epinoic_logic.translate.contracts import StructuralFinding
from epinoic_logic.translate.outcome import SUMMARY_MAX_CHARS, build_summary

from ..contract.helpers import make_report, output, run_claim, speed_problem
from ..contract.test_display import NINE, _section

LONG = "x" * 520


def _named(n: int, *, severity=None, message: str = LONG):
    return [named_diagnostic(code, severity=severity, claim_ids=["c"], assertion_ids=["SPEED"], derivation="ir_structure", message=message)
            for code in NINE[:n]]


def _speed_outcome():
    claim, report = make_report("The speed is 15 km/h.")
    return run_claim(claim, report, output(speed_problem()))


def _summary(named, structural):
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    return build_summary(claim, out.translation, out.verification, out.semantic_review, structural, out.display_status, release=out.release,
                         named=named, engine_state="complete")


def _structural(n: int) -> list[StructuralFinding]:
    return [StructuralFinding(code="ES-SRC-001", severity="error", message=f"quotation {i} not found in the supplied text: " + "q" * 300,
                              claim_ids=["c"], rule_source="source integrity", deterministic=True) for i in range(n)]


def test_a_full_section_never_pushes_the_structural_findings_out_of_the_summary():
    structural = _structural(6)
    summary = _summary(_named(9), structural)
    assert len(summary) <= SUMMARY_MAX_CHARS and summary.endswith(SCOPE_STATEMENT)
    assert "[summary truncated]" not in summary
    assert "ES-SRC-001" in summary and "6 error(s)" in summary          # the structural line is shown whole
    section = _section(summary)
    assert section[0] == SECTION_HEADING + ":" and section[-1].startswith("- and ") and len(section) < 8


def test_a_blocking_diagnostic_is_shown_before_the_info_records():
    named = [named_diagnostic("ARG-LINK-001", claim_ids=["c"], assertion_ids=["L1"], derivation="engine_recheck", message=LONG),
             named_diagnostic("ARG-FACT-001", claim_ids=["c"], assertion_ids=["E1"], derivation="engine_recheck", message=LONG),
             named_diagnostic("EVD-SRC-003", claim_ids=["c"], assertion_ids=["E2"], derivation="grounding_record", message="the check failed")]
    section = _section(_summary(named, _structural(6)))
    assert section[1].startswith("- warning source_mismatch [EVD-SRC-003]")   # never hidden behind the records


def test_control_a_section_that_fits_is_unchanged(monkeypatch):
    """Control: nine short diagnostics and no long lines below them give exactly the contract's display (the heading, five
    lines and "- and 4 more"), in the order the record holds them."""
    from ..contract.helpers import stub_engine
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(*((c, None) for c in NINE), assertion_ids=("SPEED",)))
    out = _speed_outcome()
    section = _section(out.summary)
    assert section[0] == SECTION_HEADING + ":" and len(section) == 7 and section[-1] == "- and 4 more"
    assert [line.split("[")[1].split("]")[0] for line in section[1:-1]] == list(NINE[:5])
    assert len(out.named_diagnostics) == 9


@pytest.mark.parametrize("structural", [0, 3])
def test_control_the_section_without_diagnostics_reads_as_before(structural):
    summary = _summary([], _structural(structural))
    assert "\nArgument diagnosis: none found (rules argdiag-2).\n" in summary and summary.endswith(SCOPE_STATEMENT)
