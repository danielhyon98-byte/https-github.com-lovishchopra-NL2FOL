"""How a diagnosis is shown: its own section after the verification lines, never a success word, never a status change,
"none found" / "incomplete" / "not computed", at most six lines, and the scope statement last."""
from __future__ import annotations

import re

import pytest

from epinoic_logic.engine import argument as argument_module
from epinoic_logic.engine import sign_result
from epinoic_logic.engine.statuses import DEFINITIVE, SCOPE_STATEMENT, VerificationStatus as S
from epinoic_logic.named import SECTION_HEADING, SUCCESS_WORDS, named_diagnostic
from epinoic_logic.translate import diag_argument, diag_evidence
from epinoic_logic.translate.outcome import display_status_for

from .helpers import KEY, KEY_ID, R, V, eq, make_report, output, run_claim, speed_problem, stub_claim_rule, stub_engine

#: Nine distinct engine codes that name a pattern (none generic, so none is suppressed by another).
NINE = ("ARG-VAC-001", "ARG-CIRC-001", "ARG-CIRC-002", "ARG-CIRC-003", "ARG-REFUTE-001", "ARG-AC-001", "ARG-DA-001", "ARG-FD-001", "ARG-HG-001")


def _section(summary: str) -> list[str]:
    lines = summary.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("Argument diagnosis"))
    out = [lines[start]]
    for line in lines[start + 1:]:
        if not line.startswith("- "):
            break
        out.append(line)
    return out


def _speed(**kw):
    claim, report = make_report("The speed is 15 km/h.")
    return run_claim(claim, report, output(speed_problem(), **kw))


def test_nothing_found_reads_none_found_and_the_scope_statement_stays_last():
    out = _speed()
    assert "\nArgument diagnosis: none found (rules argdiag-2).\n" in out.summary
    assert out.summary.endswith(SCOPE_STATEMENT) and out.named_diagnostics == [] and out.diagnosis_incomplete == []
    assert "named_diagnostics" not in out.model_dump() and "diagnosis_incomplete" not in out.model_dump(mode="json")


def test_a_diagnosis_has_its_own_section_after_the_verification_lines_and_never_changes_the_status(monkeypatch):
    plain = _speed()
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), assertion_ids=("SPEED", "D")))
    named = _speed()
    assert named.display_status is plain.display_status is S.ENTAILED     # never displayed as more (or less) successful
    assert plain.release.permitted and not named.release.permitted        # ... and never more releasable
    lines = named.summary.split("\n")
    head = lines.index(SECTION_HEADING + ":")
    assert lines[head - 1].startswith("Engine result ") and lines[head + 1].startswith("- warning affirming_the_consequent [ARG-AC-001] on SPEED, D: ")
    assert named.summary.endswith(SCOPE_STATEMENT)
    assert [d.code for d in named.named_diagnostics] == ["ARG-AC-001"] and named.named_diagnostics == named.verification.named_diagnostics


def test_at_most_six_lines_are_shown(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(*((c, None) for c in NINE), assertion_ids=("SPEED",)))
    out = _speed()
    section = _section(out.summary)
    assert section[0] == SECTION_HEADING + ":" and len(section) == 7 and section[-1] == "- and 4 more"
    assert len(out.named_diagnostics) == 9                                   # the record keeps every one


def test_a_capped_line_says_so_and_still_blocks(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-HG-001", None), assertion_ids=("SPEED",)))
    out = _speed(flags=[{"code": "SCOPE", "message": "two readings", "alternatives": []}])
    assert out.display_status is S.AMBIGUOUS_TRANSLATION
    [line] = [x for x in _section(out.summary) if x.startswith("- ")]
    assert line.startswith("- info hasty_generalisation [ARG-HG-001] on SPEED: ")
    assert "on the translator's assumed reading" in line and line.endswith("(capped from warning: ambiguous_translation)")
    assert not out.release.permitted


def test_an_incomplete_diagnosis_names_the_rule_and_fires_nothing(monkeypatch):
    def broken(ctx):
        raise KeyError("secret detail")
    monkeypatch.setattr(diag_argument, "RULES", (broken,))
    out = _speed()
    [missing] = out.diagnosis_incomplete
    assert out.named_diagnostics == [] and missing.startswith("test_display.") and missing.endswith(".broken: KeyError")
    assert "Argument diagnosis incomplete (" in out.summary and "); no rule fired." in out.summary and "secret" not in out.summary


def test_no_engine_result_reads_not_computed_never_none_found():
    claim, report = make_report("The poem is sad.", role="interpretation", kind="interpretive", subject="English A: Literature", texts=())
    out = run_claim(claim, report, output(speed_problem()))
    assert out.display_status is S.NOT_ELIGIBLE
    assert "Argument diagnosis: not computed (no current engine result was diagnosed by these rules)." in out.summary
    assert "none found" not in out.summary


def test_a_claim_rule_runs_on_every_outcome_and_the_engine_layer_stays_not_computed(monkeypatch):
    monkeypatch.setattr(diag_argument, "RULES", (stub_claim_rule("ARG-EQ-001"),))
    claim, report = make_report("The poem is sad.", role="interpretation", kind="interpretive", subject="English A: Literature", texts=())
    out = run_claim(claim, report, output(speed_problem()))
    assert out.display_status is S.NOT_ELIGIBLE and [d.code for d in out.named_diagnostics] == ["ARG-EQ-001"]
    section = _section(out.summary)
    assert section[0] == SECTION_HEADING + ":" and section[-1] == "- engine layer not computed: no current engine result was diagnosed by these rules"


@pytest.mark.parametrize("stubbed", [False, True])
def test_the_section_never_holds_a_success_word(monkeypatch, stubbed):
    if stubbed:
        monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-LINK-001", None), ("ARG-FACT-001", None), assertion_ids=("SPEED",),
                                                                     message="the point needs a link no source states"))
    section = " ".join(_section(_speed().summary))
    assert not (set(re.findall(r"[a-z]+", section.casefold())) & set(SUCCESS_WORDS))


#: The display statuses that read as success (a passing verdict for some query).
SUCCESS = {S.ENTAILED, S.CONSISTENT, S.SATISFIABLE}


def _contradictory() -> dict:
    problem = speed_problem()
    problem["premises"].append({"id": "D2", "expr": eq(V("d"), R(100)), "label": "Distance is 100 km", "grounding": {"kind": "arithmetic_fact"}})
    return problem


def _rest_of_summary(out) -> list[str]:
    """The summary without the diagnosis section and the release line, with the (fresh) engine result id masked."""
    rest, in_section = [], False
    for line in out.summary.split("\n"):
        if line.startswith("Argument diagnosis"):
            in_section = True
            continue
        if in_section and line.startswith("- "):
            continue
        in_section = False
        if not line.startswith("Release ("):
            rest.append(line.replace(out.verification.result_id, "<result>"))
    return rest


@pytest.mark.parametrize("text, build, status", [
    ("The speed is 15 km/h.", speed_problem, S.ENTAILED),
    ("The speed is 16 km/h.", lambda: speed_problem(speed=16), S.COUNTEREXAMPLE),
    ("The speed is 15 km/h.", _contradictory, S.INCONSISTENT_PREMISES),
])
def test_a_result_with_diagnostics_is_displayed_exactly_as_the_same_result_without_them(monkeypatch, text, build, status):
    claim, report = make_report(text)
    # The control is the same result WITHOUT diagnostics: the engine stage and the claim rules name nothing (the stubs of the
    # Contract step). Since the rules were written they name real defects on these problems (ARG-REFUTE-001 on the 16 km/h
    # counterexample, ARG-CONTRA-001 on the contradiction), so the control states the stubs explicitly; every assertion
    # below is unchanged.
    monkeypatch.setattr(argument_module, "diagnose", stub_engine())
    monkeypatch.setattr(diag_argument, "RULES", ())
    monkeypatch.setattr(diag_evidence, "RULES", ())
    plain = run_claim(claim, report, output(build()))
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), ("ARG-LINK-001", None), assertion_ids=("SPEED",)))
    monkeypatch.setattr(diag_argument, "RULES", (stub_claim_rule("ARG-EQ-001"),))
    named = run_claim(claim, report, output(build()))
    assert plain.display_status is named.display_status is status                  # never more (or less) successful
    assert {d.code for d in named.named_diagnostics} == {"ARG-AC-001", "ARG-EQ-001", "ARG-LINK-001"}
    assert _rest_of_summary(named) == _rest_of_summary(plain)                       # nothing outside the section moves
    added = set(named.release.unresolved) - set(plain.release.unresolved)
    assert set(plain.release.unresolved) <= set(named.release.unresolved) and not named.release.permitted
    assert len(added) == 1 and next(iter(added)).startswith("named defect on this claim: ")
    assert plain.release.permitted is (status is S.ENTAILED)                         # the control alone was releasable


@pytest.mark.parametrize("status", list(S))
def test_the_display_rule_reads_no_diagnosis_for_any_status(status):
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    diagnostics = [named_diagnostic(code, assertion_ids=["SPEED"], derivation="ir_structure", message="m")
                   for code in ("ARG-AC-001", "ARG-REFUTE-001", "ARG-LINK-001")]
    plain = sign_result(out.verification.model_copy(update={"status": status, "named_diagnostics": None}), KEY, KEY_ID)
    named = sign_result(out.verification.model_copy(update={"status": status, "named_diagnostics": diagnostics}), KEY, KEY_ID)
    shown = display_status_for(out.translation, plain, KEY, KEY_ID)
    assert display_status_for(out.translation, named, KEY, KEY_ID) is shown
    if status not in SUCCESS:
        assert shown not in SUCCESS                                                   # a non-success is never shown as success
    assert status in DEFINITIVE or shown not in SUCCESS
