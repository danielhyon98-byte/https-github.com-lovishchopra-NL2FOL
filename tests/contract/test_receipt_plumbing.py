"""The diagnosis on the receipt: ``TransmissionReceipt.named_diagnostics``, one INT-ARG-001 per warning or error
diagnostic on a material claim (info never reaches the findings), the labels of existing codes (``DEFECT_OF_CODE``),
``FormalCheck.defect`` on INT-SUBJ-001, the report-level hook (once per delivered report) and the summary line."""
from __future__ import annotations

from epinoic_logic.branches.base import BranchRegistry, FormalCheck, SubjectBranch
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel import bus as bus_module
from epinoic_logic.engine import argument as argument_module
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.integrity.contracts import IntegrityFinding
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import diag_argument
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, StructuralFinding, SuppliedText, sha256_text

from .helpers import CFG, DOC, KEY, make_report, output, run_claim, speed_problem, stub_claim_rule, stub_engine

REQUEST = "Calculate the average speed of the car in km/h."
ANSWER = "The average speed of the car is 15 km/h."


def _receipt(*, materiality: str = "material", problem=None):
    claim, report = make_report(ANSWER, materiality=materiality)

    def verify_fn(c, r, task=None):
        return run_claim(c, r, output(problem or speed_problem()), task=task)

    plan = WorkPlan(plan_id="plan-ad", request_id="req-ad", task_id="task-ad", subject="Physics", task_type="calculation",
                    selected_agent_ids=["physics-specialist"], allowed_document_ids=["doc"])
    ch = TranslatorChannel(plan, signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    msg, _req, _rq = ch.request("router", "physics-specialist", REQUEST, [SuppliedText(document_id="doc", text=DOC)])
    _reply, rc = ch.respond(msg.message_id, report)
    return rc


def test_the_control_receipt_is_accepted_and_carries_no_diagnosis():
    rc = _receipt()
    assert rc.status is TransmissionStatus.ACCEPTED and rc.findings == [] and rc.named_diagnostics == []
    assert "named_diagnostics" not in rc.model_dump() and "named_diagnostics" not in rc.model_dump(mode="json", exclude_none=True)
    assert "Argument diagnosis: 0 named on 0 claim(s) (0 warning or error, 0 info; rules argdiag-2). " in rc.summary
    assert rc.summary.endswith("coverage is heuristic.")


def test_a_warning_on_a_material_claim_gives_exactly_one_int_arg_001_with_its_defect(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), assertion_ids=("SPEED",)))
    rc = _receipt()
    [outcome] = rc.outcomes
    arg = [f for f in rc.findings if f.code == "INT-ARG-001"]
    assert len(arg) == 1 and rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS
    f = arg[0]
    assert (f.severity, f.defect, f.claim_ids, f.formal_result_id) == ("warning", "affirming_the_consequent", ["c"], outcome.verification.result_id)
    assert f.message.startswith("affirming_the_consequent [ARG-AC-001]: ") and f.deterministic
    assert [d.code for d in rc.named_diagnostics] == ["ARG-AC-001"] and rc.named_diagnostics == outcome.named_diagnostics
    assert "Argument diagnosis: 1 named on 1 claim(s) (1 warning or error, 0 info; rules argdiag-2)" in rc.summary


def test_an_info_diagnostic_gives_no_finding_and_leaves_a_clean_receipt_accepted(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-LINK-001", None), assertion_ids=("SPEED",)))
    rc = _receipt()
    assert rc.status is TransmissionStatus.ACCEPTED and rc.findings == []
    assert [(d.code, d.severity) for d in rc.named_diagnostics] == [("ARG-LINK-001", "info")]


def test_a_capped_warning_is_shown_as_info_on_the_receipt_and_still_blocks_release(monkeypatch):
    from epinoic_logic.translate import diag_evidence
    monkeypatch.setattr(diag_evidence, "RULES", (stub_claim_rule("EVD-LACK-001"),))   # capped: the request is not source-bound
    rc = _receipt()
    [d] = rc.named_diagnostics
    assert (d.severity, d.capped_from) == ("info", "warning") and not any(f.code == "INT-ARG-001" for f in rc.findings)
    assert not rc.outcomes[0].release.permitted and "1 capped, still blocking release" in rc.summary


def test_a_supporting_claim_keeps_its_severity_but_gets_no_receipt_finding(monkeypatch):
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), assertion_ids=("SPEED",)))
    rc = _receipt(materiality="supporting")
    assert not any(f.code == "INT-ARG-001" for f in rc.findings)
    assert [(d.code, d.severity) for d in rc.named_diagnostics] == [("ARG-AC-001", "warning")]


def test_a_condition_another_finding_states_gets_no_second_finding(monkeypatch):
    inconsistent = speed_problem()
    inconsistent["premises"].append({"id": "D2", "expr": {"op": "eq", "left": {"op": "var", "name": "d"}, "right": {"op": "real", "value": "121"}}})
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-CONTRA-001", None), assertion_ids=("D", "D2")))
    rc = _receipt(problem=inconsistent)
    codes = [f.code for f in rc.findings]
    assert "INT-REQ-007" in codes and "INT-ARG-001" not in codes
    req7 = next(f for f in rc.findings if f.code == "INT-REQ-007")
    assert req7.defect == "contradiction"                                     # labelled through DEFECT_OF_CODE
    named = {(d.code, d.layer) for d in rc.named_diagnostics}
    assert ("ARG-CONTRA-001", "engine") in named and ("INT-REQ-007", "channel") in named


def test_the_bus_labels_existing_codes_and_leaves_an_unmapped_one_alone():
    labelled = bus_module.TranslatorChannel._labelled(IntegrityFinding(code="INT-REQ-003", severity="error", message="x (an altered quotation)"))
    assert labelled.defect == "altered_quotation"
    plain = IntegrityFinding(code="INT-REQ-004", severity="warning", message="request item i1 appears unaddressed")
    assert bus_module.TranslatorChannel._labelled(plain) is plain and plain.defect is None
    sf = bus_module.TranslatorChannel._labelled(StructuralFinding(code="ST-DIM-001", severity="warning", message="dimensions differ"))
    assert sf.defect == "stem_dimension_error"
    own = StructuralFinding(code="ST-REF-001", severity="warning", message="m", defect="stem_wrong_formula")
    assert bus_module.TranslatorChannel._labelled(own) is own
    assert "defect" not in plain.model_dump() and "defect" not in StructuralFinding(code="X-Y-001", severity="info", message="m").model_dump()


# ----------------------------------------------------------------------------------------- branch formal checks


def _problem(stated: str) -> Problem:
    return Problem.model_validate({
        "problem_id": "p", "request_id": "req-m", "claim_id": "rep:c", "query": "entailment", "symbols": [{"name": "x", "sort": "Real"}],
        "premises": [{"id": "P0", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "1"}},
                      "grounding": {"kind": "supplied_text", "verified": True}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": stated}}}})


class _Pack:
    name = "contract-test-pack"

    def __init__(self, formal):
        self.formal = list(formal)

    def checks(self, report, request_text=None):
        return []

    def formal_checks(self, report):
        return list(self.formal)


def _branch_receipt(*checks: FormalCheck):
    from epinoic_logic.branches.generic_parser import GenericTextParser
    branch = SubjectBranch(key="generic", display_name="test", profile_keys=("unknown",), parser_factory=lambda: GenericTextParser("specialist"),
                           packs=(_Pack(checks),))
    plan = WorkPlan(plan_id="plan-m", request_id="req-m", task_id="task-m", subject="Underwater Basket Weaving", task_type="short_answer",
                    selected_agent_ids=["specialist"])
    ch = TranslatorChannel(plan, signing_key=KEY, config=CFG, registry=BranchRegistry([branch], default_key="generic"))
    text = "The value is 1."
    report = SpecialistReport(report_id="rep-m", request_id="req-m", task_id="task-m", agent_id="specialist", subject="Underwater Basket Weaving",
                              task_type="short_answer", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-17T00:00:00Z",
                              claims=[ClaimRecord(request_id="req-m", task_id="task-m", report_id="rep-m", agent_id="specialist", subject="Underwater Basket Weaving",
                                                  task_type="short_answer", claim_id="c1", claim_text=text, claim_role="quantitative")])
    msg, _r, _q = ch.request("router", "specialist", "State the value.")
    _reply, rc = ch.respond(msg.message_id, report)
    return rc


def test_formal_check_defect_reaches_int_subj_001_before_the_kind_label():
    rc = _branch_receipt(
        FormalCheck(check_id="t-own", kind="stem_arithmetic", description="d", problem=_problem("2"), claim_ids=("c1",), defect="stem_unit_error"),
        FormalCheck(check_id="t-kind", kind="stem_conversion", description="d", problem=_problem("3"), claim_ids=("c1",)),
        FormalCheck(check_id="t-none", kind="stem_comparison", description="d", problem=_problem("4"), claim_ids=("c1",)),
        FormalCheck(check_id="t-bad", kind="stem_algebra", description="d", problem=_problem("5"), claim_ids=("c1",), defect="not_a_label"),
    )
    subj = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    by_check = {next(c.constraint_id for c in rc.formal_checks if c.formal_result_id == f.formal_result_id): f.defect for f in subj}
    assert by_check == {"t-own": "stem_unit_error", "t-kind": "stem_unit_error", "t-none": None, "t-bad": "stem_invalid_step"}
    assert not any(f.code == "INT-ARG-001" for f in rc.findings)             # an existing finding is not reported twice
    named = sorted((d.code, d.defect) for d in rc.named_diagnostics)
    assert named == [("INT-SUBJ-001", "stem_invalid_step"), ("INT-SUBJ-001", "stem_unit_error"), ("INT-SUBJ-001", "stem_unit_error")]


def test_the_branch_checks_run_without_the_argument_diagnosis(monkeypatch):
    seen = []
    real = bus_module.verify

    def spy(*a, **k):
        seen.append(k.get("diagnose", True))
        return real(*a, **k)

    monkeypatch.setattr(bus_module, "verify", spy)
    _branch_receipt(FormalCheck(check_id="t-1", kind="stem_arithmetic", description="d", problem=_problem("1"), claim_ids=("c1",)))
    assert seen == [False]


# ----------------------------------------------------------------------------------------- the report-level hook


def test_the_report_level_hook_runs_once_per_delivered_report(monkeypatch):
    calls = []

    def bare(rctx):
        calls.append((rctx.report.report_id, len(rctx.outcomes), [i.text for i in rctx.items], rctx.task.text if rctx.task else None))
        return [stub_claim_rule("ARG-BARE-001", layer="report")(rctx)[0].model_copy(update={"claim_ids": ["c"]})]

    monkeypatch.setattr(diag_argument, "REPORT_RULES", (bare,))
    rc = _receipt()
    assert calls == [("rep-ad", 1, [REQUEST], REQUEST)]
    arg = [f for f in rc.findings if f.code == "INT-ARG-001"]
    assert len(arg) == 1 and arg[0].defect == "bare_assertion" and arg[0].formal_result_id is None
    assert [d.code for d in rc.named_diagnostics] == ["ARG-BARE-001"] and rc.outcomes[0].named_diagnostics == []


def test_a_failing_report_rule_is_named_on_the_receipt_and_fires_nothing(monkeypatch):
    def broken(rctx):
        raise ValueError("secret detail")

    monkeypatch.setattr(diag_argument, "REPORT_RULES", (broken,))
    rc = _receipt()
    assert rc.status is TransmissionStatus.ACCEPTED and rc.named_diagnostics == []
    assert "report rules incomplete: test_receipt_plumbing." in rc.summary and "secret" not in rc.summary


def test_the_receipt_the_outcome_and_the_translation_record_round_trip_with_their_diagnosis(monkeypatch):
    from epinoic_logic.channel.contracts import TransmissionReceipt
    from epinoic_logic.engine import verify_signature
    from epinoic_logic.translate.contracts import ClaimVerificationOutcome, TranslationResult
    monkeypatch.setattr(argument_module, "diagnose", stub_engine(("ARG-AC-001", None), ("ARG-LINK-001", None), assertion_ids=("SPEED",)))
    monkeypatch.setattr(diag_argument, "RULES", (stub_claim_rule("ARG-EQ-001"),))
    rc = _receipt()
    [outcome] = rc.outcomes
    assert {d.code for d in rc.named_diagnostics} == {"ARG-AC-001", "ARG-EQ-001", "ARG-LINK-001"}
    assert sorted(f.defect for f in rc.findings if f.code == "INT-ARG-001") == ["affirming_the_consequent", "equivocation"]
    text = rc.model_dump_json()
    again = TransmissionReceipt.model_validate_json(text)
    assert again == rc and again.model_dump_json() == text
    o = ClaimVerificationOutcome.model_validate_json(outcome.model_dump_json())
    assert o == outcome and o.named_diagnostics == outcome.named_diagnostics and o.verification.argument_rules == "argdiag-2"
    assert verify_signature(o.verification, KEY)                               # the signed engine result survives the trip
    t = TranslationResult.model_validate_json(outcome.translation.model_dump_json())
    assert t == outcome.translation and t.premise_roles and t.premise_roles == outcome.translation.premise_roles
