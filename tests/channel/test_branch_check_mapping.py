"""How the channel maps a branch formal check's engine status to the receipt (docs/STEM_DESIGN.md, section 11.2):
satisfied only for the expected status with a non-vacuous proof, failed for any other definitive status (inconsistent
premises only when the check counts them as a failure), undecided otherwise; INT-SUBJ-001 / -004 / -002 with the
check's claim ids; named policies; truncation; and a raising pack or check that never takes the receipt down."""
from __future__ import annotations

import pytest

from epinoic_logic.branches.base import BranchRegistry, FormalCheck, SubjectBranch
from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.channel import bus as bus_module
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, StructuralFinding, sha256_text

KEY = b"mapping-test-key-0123456789abcdefgh"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def _v(n):
    return {"op": "var", "name": n}


def _r(x):
    return {"op": "real", "value": str(x)}


def _eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def problem(query: str, premises: list[dict], conclusion=None, symbols=("x",)) -> Problem:
    return Problem.model_validate({
        "problem_id": "p", "request_id": "req-m", "claim_id": "rep:c", "query": query,
        "symbols": [{"name": s, "sort": "Real"} for s in symbols],
        "premises": [{"id": f"P{i}", "expr": e, "grounding": {"kind": "supplied_text", "verified": True}} for i, e in enumerate(premises)],
        **({"conclusion": {"id": "C", "expr": conclusion}} if conclusion is not None else {}),
    })


ENTAILED = problem("entailment", [_eq(_v("x"), _r(1))], _eq(_v("x"), _r(1)))
COUNTEREXAMPLE = problem("entailment", [_eq(_v("x"), _r(1))], _eq(_v("x"), _r(2)))
INCONSISTENT = problem("entailment", [_eq(_v("x"), _r(1)), _eq(_v("x"), _r(2))], _eq(_v("x"), _r(1)))
VACUOUS_ENTAILED = problem("entailment", [_eq(_v("x"), _r(1))], _eq(_v("x"), _v("x")))
SATISFIABLE = problem("satisfiability", [_eq(_v("x"), _r(1))])
VACUOUS_SATISFIABLE = problem("satisfiability", [])
UNSATISFIABLE = problem("satisfiability", [_eq(_v("x"), _r(1)), _eq(_v("x"), _r(2))])
NONLINEAR = problem("entailment", [_eq(_v("x"), _r(2)), _eq(_v("y"), _r(3))], _eq({"op": "mul", "args": [_v("x"), _v("y")]}, _r(6)), symbols=("x", "y"))


class _Pack:
    name = "mapping-test-pack"

    def __init__(self, formal=(), raise_in=None):
        self.formal, self.raise_in = list(formal), raise_in

    def checks(self, report, request_text=None):
        if self.raise_in == "checks":
            raise RuntimeError("secret detail")
        return [StructuralFinding(code="TEST-INFO-001", severity="info", message="ran")]

    def formal_checks(self, report):
        if self.raise_in == "formal":
            raise KeyError("secret detail")
        return list(self.formal)


def channel(*packs) -> TranslatorChannel:
    from epinoic_logic.branches.generic_parser import GenericTextParser
    branch = SubjectBranch(key="generic", display_name="test", profile_keys=("unknown",), parser_factory=lambda: GenericTextParser("specialist"), packs=tuple(packs))
    plan = WorkPlan(plan_id="plan-m", request_id="req-m", task_id="task-m", subject="Underwater Basket Weaving", task_type="short_answer", selected_agent_ids=["specialist"])
    return TranslatorChannel(plan, signing_key=KEY, config=CFG, registry=BranchRegistry([branch], default_key="generic"))


def report(text: str = "The value is 1.") -> SpecialistReport:
    return SpecialistReport(report_id="rep-m", request_id="req-m", task_id="task-m", agent_id="specialist", subject="Underwater Basket Weaving",
                            task_type="short_answer", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(request_id="req-m", task_id="task-m", report_id="rep-m", agent_id="specialist", subject="Underwater Basket Weaving",
                                                task_type="short_answer", claim_id="c1", claim_text=text, claim_role="quantitative")])


def run(*checks: FormalCheck, packs=None):
    ch = channel(*(packs or [_Pack(checks)]))
    m, _, _ = ch.request("router", "specialist", "State the value.")
    _, rc = ch.respond(m.message_id, report())
    return rc


def check(p: Problem, expected: str, **kw) -> FormalCheck:
    return FormalCheck(check_id=kw.pop("check_id", "t-1"), kind=kw.pop("kind", "test_kind"), description=kw.pop("description", "test check"), problem=p,
                       expected_if_sound=expected, **kw)


@pytest.mark.parametrize("p,expected,satisfied,code", [
    (ENTAILED, "ENTAILED", True, None),
    (COUNTEREXAMPLE, "ENTAILED", False, "INT-SUBJ-001"),
    (INCONSISTENT, "ENTAILED", False, "INT-SUBJ-001"),          # inconsistent_is_failure defaults to True (every pre-STEM check)
    (VACUOUS_ENTAILED, "ENTAILED", None, "INT-SUBJ-002"),       # recorded behaviour change 2: E108 is undecided, not ok
    (SATISFIABLE, "SATISFIABLE", True, None),
    (UNSATISFIABLE, "SATISFIABLE", False, "INT-SUBJ-001"),
    (VACUOUS_SATISFIABLE, "SATISFIABLE", None, "INT-SUBJ-002"),
    (UNSATISFIABLE, "UNSATISFIABLE", True, None),
    (SATISFIABLE, "UNSATISFIABLE", False, "INT-SUBJ-001"),       # recorded behaviour change 3: SATISFIABLE where UNSATISFIABLE is expected fails
    (NONLINEAR, "ENTAILED", None, "INT-SUBJ-002"),              # UNSUPPORTED under the linear policy: undecided, never success
])
def test_status_mapping_table(p, expected, satisfied, code):
    rc = run(check(p, expected, claim_ids=("c1",)))
    cr = next(c for c in rc.formal_checks if c.constraint_id == "t-1")
    assert cr.satisfied is satisfied and cr.method == "formal" and cr.formal_result_id
    subj = [f for f in rc.findings if f.code.startswith("INT-SUBJ")]
    if code is None:
        assert subj == []
    else:
        assert [f.code for f in subj] == [code] and subj[0].claim_ids == ["c1"] and subj[0].formal_result_id == cr.formal_result_id
    assert rc.status is not TransmissionStatus.REJECTED


def test_inconsistent_premises_are_undecided_when_the_check_says_so():
    rc = run(check(INCONSISTENT, "ENTAILED", inconsistent_is_failure=False))
    cr = rc.formal_checks[0]
    assert cr.satisfied is None and cr.formal_status == "INCONSISTENT_PREMISES"
    f = next(f for f in rc.findings if f.code == "INT-SUBJ-002")
    assert "inconsistent premises are undecided for this check" in f.message


def test_a_warning_severity_failure_is_int_subj_004():
    rc = run(check(COUNTEREXAMPLE, "ENTAILED", failure_severity="warning", claim_ids=("c1",)))
    assert [(f.code, f.severity, f.claim_ids) for f in rc.findings if f.code.startswith("INT-SUBJ")] == [("INT-SUBJ-004", "warning", ["c1"])]
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS and not rc.errors


def test_the_nonlinear_policy_reaches_the_engine_and_is_recorded():
    rc = run(check(NONLINEAR, "ENTAILED", policy="nonlinear"))
    assert rc.formal_checks[0].satisfied is True and rc.formal_checks[0].formal_status == "ENTAILED"


def test_an_unknown_policy_is_never_run_under_another_one():
    rc = run(check(ENTAILED, "ENTAILED", policy="Linear", claim_ids=("c1",)))
    cr = rc.formal_checks[0]
    assert cr.satisfied is None and cr.formal_result_id is None and "unknown pack policy" in cr.detail
    f = next(f for f in rc.findings if f.code == "INT-SUBJ-002")
    assert "unknown policy" in f.message and f.claim_ids == ["c1"]


def test_a_long_description_is_truncated_and_never_raises():
    rc = run(check(COUNTEREXAMPLE, "ENTAILED", description="x" * 5000))
    cr = rc.formal_checks[0]
    assert len(cr.detail) <= 2000 and cr.detail.endswith("...") and cr.satisfied is False
    f = next(f for f in rc.findings if f.code == "INT-SUBJ-001")
    assert len(f.message) <= 2000


def test_a_stem_failure_shows_the_computed_and_stated_values():
    p = problem("entailment", [_eq(_v("c"), _r(5)), _eq(_v("r"), _r(6))], _eq(_v("c"), _v("r")), symbols=("c", "r"))
    rc = run(check(p, "ENTAILED", kind="stem_arithmetic"))
    f = next(f for f in rc.findings if f.code == "INT-SUBJ-001")
    assert "c = 5" in f.message and "r = 6" in f.message
    plain = run(check(p, "ENTAILED", kind="percent_change"))
    assert "engine counterexample" not in next(f for f in plain.findings if f.code == "INT-SUBJ-001").message


def test_an_exception_while_deciding_one_check_makes_it_alone_undecided(monkeypatch):
    real = bus_module.verify

    def flaky(problem, *a, **k):
        if problem.problem_id == "boom":
            raise RuntimeError("secret detail")
        return real(problem, *a, **k)

    monkeypatch.setattr(bus_module, "verify", flaky)
    boom = ENTAILED.model_copy(update={"problem_id": "boom"})
    rc = run(check(boom, "ENTAILED", check_id="t-boom"), check(COUNTEREXAMPLE, "ENTAILED", check_id="t-2"))
    by = {c.constraint_id: c for c in rc.formal_checks}
    assert by["t-boom"].satisfied is None and by["t-2"].satisfied is False
    assert any(f.code == "INT-SUBJ-002" and "internal" in f.message and "secret" not in f.message for f in rc.findings)


@pytest.mark.parametrize("stage", ["checks", "formal"])
def test_a_raising_pack_is_br_internal_001_and_the_other_packs_still_run(stage):
    rc = run(packs=[_Pack(raise_in=stage), _Pack([check(COUNTEREXAMPLE, "ENTAILED", check_id="t-2")])])
    br = [s for s in rc.structural_findings if s.code == "BR-INTERNAL-001"]
    assert len(br) == 1 and br[0].severity == "warning" and "mapping-test-pack" in br[0].message and "secret" not in br[0].message
    assert "must not treat the pack as passed" in br[0].message
    assert any(c.constraint_id == "t-2" and c.satisfied is False for c in rc.formal_checks)
    assert rc.status is TransmissionStatus.ACCEPTED_WITH_FINDINGS


def test_formal_checks_for_is_preferred_and_receives_the_request():
    seen = {}

    class Pack(_Pack):
        def formal_checks_for(self, report, request_text):
            seen["request"] = request_text
            return [check(ENTAILED, "ENTAILED", check_id="t-for")]

    rc = run(packs=[Pack()])
    assert seen["request"] == "State the value." and [c.constraint_id for c in rc.formal_checks] == ["t-for"]


def test_existing_checks_keep_their_messages():
    rc = run(check(COUNTEREXAMPLE, "ENTAILED", kind="percent_change", description="report's own arithmetic: x"))
    f = next(f for f in rc.findings if f.code == "INT-SUBJ-001")
    assert f.message == "the report's own percent_change statement does not hold: report's own arithmetic: x"
    assert rc.formal_checks[0].detail == "percent_change: report's own arithmetic: x; solver COUNTEREXAMPLE"


def test_the_stem_check_budget_degrades_to_undecided_never_success(monkeypatch):
    monkeypatch.setattr(bus_module, "STEM_CHECK_BUDGET_S", -1.0)  # already spent before the first check
    rc = run(check(ENTAILED, "ENTAILED", kind="stem_arithmetic", check_id="stem-eq-1", claim_ids=("c1",)), check(COUNTEREXAMPLE, "ENTAILED", check_id="t-2"))
    by = {c.constraint_id: c for c in rc.formal_checks}
    assert by["stem-eq-1"].satisfied is None and by["stem-eq-1"].formal_result_id is None and "check budget" in by["stem-eq-1"].detail
    assert by["t-2"].satisfied is False  # other packs' checks are not budgeted
    f = next(f for f in rc.findings if f.code == "INT-SUBJ-002")
    assert "check budget" in f.message and f.claim_ids == ["c1"]
