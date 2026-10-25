"""Release and the argument diagnosis: rule 8 (no named defect by effective severity: a capped warning still blocks),
rule 9 (the diagnosis was computed by these rules), the release assessment ``release-v2``, and a load-bearing premise
that is the writer's own or unsupported never releases, whatever the diagnosis says (an info record never permits)."""
from __future__ import annotations

from epinoic_logic.engine import argument as argument_module
from epinoic_logic.engine import verify
from epinoic_logic.engine.release import release_check
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate import outcome as outcome_module
from epinoic_logic.translate.outcome import RELEASE_POLICY

from .helpers import CFG, KEY, KEY_ID, established_problem, make_report, output, run_claim, speed_problem, stub_engine, writer_link_problem


def _check(problem, **kw):
    return release_check(verify(problem, CFG, signing_key=KEY, key_id=KEY_ID, **kw), problem, signing_key=KEY, key_id=KEY_ID)


def test_the_control_is_eligible_and_an_undiagnosed_result_is_refused_by_rule_9():
    problem = established_problem()
    assert _check(problem).eligible                                     # control: established premises, diagnosis complete
    off = _check(problem, diagnose=False)
    assert not off.eligible and off.reasons == ("argument diagnosis not computed: the result carries no argument_rules "
                                                "(verify the problem with the argdiag-2 diagnosis)",)


def test_a_named_warning_is_refused_by_rule_8_and_so_is_the_same_warning_capped(monkeypatch):
    problem = established_problem()
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), assertion_ids=("l",)))
    warned = _check(problem)
    assert not warned.eligible and warned.reasons == ("named defect: ARG-AC-001 (affirming_the_consequent)",)
    capped = _check(problem, severity_cap=("info", "ambiguous_translation"))
    # stricter since repair round 4 (INFO-NAMED-DEFECTS-ON-CONTROLS): the capped warning still blocks, under a line that names
    # its cap and no defect label, since what is shown at info accuses nothing
    assert not capped.eligible and capped.reasons == ("capped diagnostic, shown at info and still blocking release (it names no defect): "
                                                      "ARG-AC-001 (capped from warning: ambiguous_translation)",)
    assert not any("named defect" in r or "affirming_the_consequent" in r for r in capped.reasons)


def test_an_info_record_alone_never_blocks_and_never_permits(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-LINK-001", None), assertion_ids=("l",)))
    assert _check(established_problem()).eligible
    link = _check(writer_link_problem())                               # the writer's own link: rule 7 refuses, the info adds nothing
    assert not link.eligible and link.reasons == ("unresolved dependencies (ungrounded): l_so",)


def test_an_incomplete_diagnosis_or_other_rules_are_refused(monkeypatch):
    problem = established_problem()
    monkeypatch.setattr(argument_module, "diagnose", lambda *a, **k: ([], "argdiag-2/incomplete:budget"))
    check = _check(problem)
    assert not check.eligible and check.reasons[0].startswith("argument diagnosis incomplete (budget)")
    r = verify(problem, CFG, signing_key=KEY, key_id=KEY_ID).model_copy(update={"argument_rules": "argdiag-0"})
    other = release_check(r, problem, signing_key=KEY, key_id=KEY_ID)
    assert not other.eligible and any(w.startswith("argument diagnosis by other rules") for w in other.reasons)


def test_a_load_bearing_writer_assumed_or_unsupported_premise_is_never_released():
    link = _check(writer_link_problem())
    assert not link.eligible and "unresolved dependencies (ungrounded): l_so" in link.reasons
    unsupported = _check(writer_link_problem(link_kind="task_setting", fact_verified=False))
    assert not unsupported.eligible and any("authority not validated" in w and "e" in w and "l_so" in w for w in unsupported.reasons)


def test_release_v2_names_a_defect_on_the_claim_by_effective_severity(monkeypatch):
    assert RELEASE_POLICY == "release-v2"
    claim, report = make_report("The speed is 15 km/h.")
    control = run_claim(claim, report, output(speed_problem()))
    assert control.release.permitted and control.release.policy == "release-v2" and control.release.unresolved == []
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), assertion_ids=("SPEED",)))
    warned = run_claim(claim, report, output(speed_problem()))
    assert warned.display_status is S.ENTAILED                        # the status is unchanged ...
    assert not warned.release.permitted                               # ... and release refuses
    assert "named defect on this claim: ARG-AC-001 (affirming_the_consequent)" in warned.release.unresolved
    assert not any(u.startswith("engine release check: named defect") for u in warned.release.unresolved)  # stated once


def test_a_capped_claim_layer_warning_still_blocks_release(monkeypatch):
    from epinoic_logic.translate import diag_evidence
    from .helpers import stub_claim_rule
    monkeypatch.setattr(diag_evidence, "RULES", (stub_claim_rule("EVD-SRC-001"),))   # warn/info: capped outside a source-bound task
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    [d] = out.named_diagnostics
    assert (d.severity, d.capped_from, d.cap_reason) == ("info", "warning", "not_source_bound")
    # stricter since repair round 4 (INFO-NAMED-DEFECTS-ON-CONTROLS): still blocking, under a line that names the cap and no defect
    assert not out.release.permitted and ("capped diagnostic, shown at info and still blocking release (it names no defect): EVD-SRC-001 "
                                          "(capped from warning: not_source_bound)") in out.release.unresolved
    assert not any(u.startswith("named defect") or "unchecked_source" in u for u in out.release.unresolved)
    monkeypatch.setattr(diag_evidence, "RULES", (stub_claim_rule("EVD-SRC-004"),))   # info by the table: never blocks
    assert run_claim(claim, report, output(speed_problem())).release.permitted


def test_the_writer_link_through_the_translator_is_marked_and_not_released():
    claim, report = make_report("The evidence holds, so the point holds.", role="point", kind="formal_logic", texts=(), subject="History",
                                support=(("s1", "The evidence holds."),))
    problem = writer_link_problem().model_dump(mode="json", exclude_none=True)
    problem["premises"][0]["grounding"] = {"kind": "task_setting"}                    # the translator cannot certify it
    out = run_claim(claim, report, output(problem))
    roles = {r.assertion_id: r for r in out.translation.premise_roles}
    assert (roles["l_so"].role, roles["l_so"].authority, roles["l_so"].marked, roles["l_so"].connective) == ("link", "writer_own", "translator_link", "so")
    assert (roles["e"].role, roles["e"].authority) == ("fact", "unverified")
    assert out.display_status is S.ENTAILED and not out.release.permitted
    assert out.verification.ungrounded_dependencies == ["l_so"] and out.verification.unverified_dependencies == ["e"]
    assert any("ungrounded dependencies" in u and "l_so" in u for u in out.release.unresolved)
    assert any("unverified dependencies" in u and "e" in u for u in out.release.unresolved)


def test_assess_release_without_diagnostics_is_unchanged_from_release_v1_rules(monkeypatch):
    # the keyword defaults to no diagnostics: a caller that passes none sees exactly the earlier rules
    claim, report = make_report("The speed is 15 km/h.")
    out = run_claim(claim, report, output(speed_problem()))
    again = outcome_module.assess_release(out.translation, out.verification, out.semantic_review, out.structural_findings, out.display_status,
                                          ("current", []), release_check(out.verification, out.translation.problem, signing_key=KEY, key_id=KEY_ID))
    assert again.permitted and again.unresolved == []
