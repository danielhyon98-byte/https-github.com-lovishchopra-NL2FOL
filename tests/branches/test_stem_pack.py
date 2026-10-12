"""``StemPack``: ST findings with their codes and severities, formal checks with claim ids, named policies and failure
severities, check ids that match the parser's assumption text, and failures named, never raised (docs/STEM_DESIGN.md,
sections 8 and 11)."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.stem_specialist import CHECKS_ASSUMPTION, StemTextParser
from epinoic_logic.branches import stem_pack as stem_pack_module
from epinoic_logic.branches.base import FormalCheck, IntegrityPack
from epinoic_logic.branches.stem_pack import STEM_RULE_SOURCE, StemPack
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem.checks import CheckPlan, PlannedCheck
from epinoic_logic.stem.relations import ST_SEVERITY
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
OBSERVED = "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻²."
REQUEST = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."


def parsed(text: str, subject: str = "Physics", request_text=None, mode="sciences", rid="rep") -> SpecialistReport:
    return StemTextParser(mode=mode).parse_response(text, request_id="req", task_id="task", report_id=rid, subject=subject, task_type="short_answer",
                                                    request_text=request_text)


def structured(text: str, claims: list[dict], subject: str = "Physics") -> SpecialistReport:
    return SpecialistReport(report_id="rep-s", request_id="req", task_id="task", agent_id="physics-specialist", subject=subject, task_type="short_answer",
                            original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(request_id="req", task_id="task", report_id="rep-s", agent_id="physics-specialist", subject=subject,
                                                task_type="short_answer", **c) for c in claims])


def decide(fc: FormalCheck) -> str:
    return verify(fc.problem, policy_config(fc.policy, CFG), limits=policy_limits(fc.policy)).status.value


def test_the_pack_satisfies_the_integrity_pack_protocol():
    pack = StemPack("sciences")
    assert isinstance(pack, IntegrityPack) and pack.name == "stem-sciences"
    assert StemPack("mathematics").name == "stem-mathematics" and StemPack("computer_science").name == "stem-computer_science"
    with pytest.raises(ValueError):
        StemPack("history")


def test_the_observed_case_is_a_failing_arithmetic_check_on_its_claim():
    rep = parsed(OBSERVED, request_text=REQUEST)
    formal = StemPack("sciences").formal_checks_for(rep, REQUEST)
    eq = next(fc for fc in formal if fc.check_id == "stem-eq-1")
    assert eq.kind == "stem_arithmetic" and eq.claim_ids == ("s1.2",) and eq.policy == "linear"
    assert eq.failure_severity == "error" and eq.inconsistent_is_failure is False and eq.expected_if_sound == "ENTAILED"
    assert isinstance(eq.problem, Problem) and "(20 - 0)/4.0 = 6.0" in eq.description
    assert decide(eq) == "COUNTEREXAMPLE"
    res = next(fc for fc in formal if fc.check_id == "stem-res-1")
    assert set(res.claim_ids) == {"s1.2", "s1.3"} and decide(res) == "ENTAILED"
    assert StemPack("sciences").checks(rep, REQUEST) == []


def test_check_ids_match_the_parsers_assumption_text():
    for subject, text, req in [
        ("Physics", OBSERVED, REQUEST),
        ("Chemistry", "n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol", "Show that 36 g of water is 2.0 mol."),
        ("Mathematics: Analysis and Approaches", "$x^2 - 5x + 6 = 0 \\Rightarrow (x-2)(x-3) = 0$, so $x = 2$ or $x = 3$.", "Solve x^2 - 5x + 6 = 0."),
        ("Computer Science", "FF₁₆ = 15 × 16 + 15 = 255 and 1011₂ = 11.", None),
    ]:
        mode = {"Physics": "sciences", "Chemistry": "sciences", "Computer Science": "computer_science"}.get(subject, "mathematics")
        rep = parsed(text, subject, req, mode)
        pack = StemPack(mode)
        formal = pack.formal_checks_for(rep, req)
        built = {fc.check_id for fc in formal} | {f.message.split(":")[0] for f in pack.checks(rep, req) if f.message.startswith("stem-")}
        named = {cid.strip() for c in rep.claims for a in c.assumptions if a.startswith(CHECKS_ASSUMPTION) for cid in a[len(CHECKS_ASSUMPTION):].split(",")}
        assert named and named == built, (subject, named, built)
        for fc in formal:
            assert set(fc.claim_ids) <= {c.claim_id for c in rep.claims}


def test_nothing_on_a_bare_value_and_only_info_for_unchecked_code():
    rep = parsed("The speed is 15 m/s.")
    pack = StemPack("sciences")
    assert pack.checks(rep, "Calculate the speed.") == [] and pack.formal_checks_for(rep, "Calculate the speed.") == []
    code = parsed("```python\nprint(2 + 2)\n```", "Computer Science", mode="computer_science")
    found = StemPack("computer_science").checks(code, None)
    assert [(f.code, f.severity, f.claim_ids) for f in found] == [("ST-CODE-001", "info", ["c1.1"])]  # Computer Science claim ids start with 'c'
    assert found[0].rule_source == STEM_RULE_SOURCE


@pytest.mark.parametrize("subject,mode,text,code", [
    ("Mathematics: Analysis and Approaches", "mathematics", "f(x) = 3x^2 + 2x, so f'(x) = 6x + 1.", "ST-UNDEC-001"),
    ("Environmental Systems and Societies", "sciences", "Efficiency = 150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%.", "ST-UNIT-001"),
    ("Physics", "sciences", "Given v = 20 m s⁻¹ and t = 4.0 s, a = v/t = 5.0 m s⁻¹.", "ST-DIM-001"),
    ("Physics", "sciences", "E = hf = 6.63 × 10⁻³⁴ × f = 3.3 × 10⁻¹⁹ J", "ST-UNDEC-002"),
])
def test_st_findings_carry_their_code_severity_and_claims(subject, mode, text, code):
    rep = parsed(text, subject, None, mode)
    found = [f for f in StemPack(mode).checks(rep, None) if f.code == code]
    assert found, [f.code for f in StemPack(mode).checks(rep, None)]
    for f in found:
        assert f.severity == ST_SEVERITY[code] and f.severity != "error" and f.claim_ids and set(f.claim_ids) <= {c.claim_id for c in rep.claims}


def test_relay_form_builds_no_given_or_target_check():
    text = "n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol"
    req = "Show that 36 g of water is 2.0 mol."
    rep = parsed(text, "Chemistry", req)
    pack = StemPack("sciences")
    with_request = {fc.check_id for fc in pack.formal_checks_for(rep, req)}
    relay = {fc.check_id for fc in pack.formal_checks(rep)}
    assert "stem-tgt-1" in with_request and not any(i.startswith(("stem-tgt", "stem-giv")) for i in relay)
    tgt = next(fc for fc in pack.formal_checks_for(rep, req) if fc.check_id == "stem-tgt-1")
    assert tgt.failure_severity == "warning" and decide(tgt) in ("ENTAILED", "SATISFIABLE")


def test_a_structured_report_maps_statements_to_its_own_claims():
    text = "Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻²."
    rep = structured(text, [dict(claim_id="ph-1", claim_text="Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻².", claim_role="quantitative"),
                            dict(claim_id="ph-2", claim_text="The acceleration is therefore 6.0 m s⁻².", claim_role="quantitative")])
    formal = StemPack("sciences").formal_checks_for(rep, None)
    eq = next(fc for fc in formal if fc.check_id == "stem-eq-1")
    assert eq.claim_ids == ("ph-1",) and decide(eq) == "COUNTEREXAMPLE"
    res = next(fc for fc in formal if fc.check_id == "stem-res-1")
    assert set(res.claim_ids) == {"ph-1", "ph-2"}


def test_a_structured_claim_that_is_no_substring_is_mapped_by_mention():
    text = "a = (20 - 0)/4.0 = 6.0 m s⁻²"
    rep = structured(text, [dict(claim_id="x-1", claim_text="Result: a = (20 - 0)/4.0 = 6.0 m s⁻² (my working)", claim_role="quantitative")])
    eq = StemPack("sciences").formal_checks_for(rep, None)[0]
    assert eq.claim_ids == ("x-1",)


def test_an_injected_failure_is_st_internal_001_never_a_raise(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("injected")
    monkeypatch.setattr(stem_pack_module, "build_checks", boom)
    pack = StemPack("sciences")
    rep = parsed(OBSERVED, request_text=REQUEST, rid="rep-boom")
    found = pack.checks(rep, REQUEST)
    assert [(f.code, f.severity) for f in found] == [("ST-INTERNAL-001", "warning")]
    assert "RuntimeError" in found[0].message and "must not be read as passed" in found[0].message
    assert pack.formal_checks_for(rep, REQUEST) == []


def test_a_problem_the_ir_refuses_is_named_and_not_run(monkeypatch):
    bad = PlannedCheck(check_id="stem-eq-1", kind="stem_arithmetic", description="d", claim_ids=("s1.2",), problem={"problem_id": "x"},
                       expected_if_sound="ENTAILED", policy="linear", failure_severity="error")
    monkeypatch.setattr(stem_pack_module, "build_checks", lambda *a, **k: CheckPlan((bad,), ()))
    pack = StemPack("sciences")
    rep = parsed(OBSERVED, request_text=REQUEST, rid="rep-bad")
    assert pack.formal_checks_for(rep, REQUEST) == []
    found = pack.checks(rep, REQUEST)
    assert [(f.code, f.claim_ids) for f in found] == [("ST-INTERNAL-001", ["s1.2"])] and "stem-eq-1" in found[0].message


def test_a_warning_severity_and_a_nonlinear_policy_pass_through():
    rep = parsed("$x^2 - 5x + 6 = 0 \\Rightarrow (x-2)(x-3) = 0$", "Mathematics: Analysis and Approaches", None, "mathematics")
    alg = next(fc for fc in StemPack("mathematics").formal_checks_for(rep, None) if fc.kind == "stem_algebra")
    assert alg.policy == "nonlinear" and decide(alg) == "ENTAILED"
    # under the linear policy the same problem is refused, never decided
    assert verify(alg.problem, CFG).status.value == "UNSUPPORTED"


def test_results_are_memoised_per_report_and_request():
    pack = StemPack("sciences")
    rep = parsed(OBSERVED, request_text=REQUEST, rid="rep-memo")
    a = pack.formal_checks_for(rep, REQUEST)
    b = pack.formal_checks_for(rep, REQUEST)
    assert a == b and a is not b  # equal results, fresh lists (callers may extend them)
    assert [fc.check_id for fc in pack.formal_checks(rep)] == [fc.check_id for fc in a]  # this answer has no Given or target check


def test_statement_ids_in_descriptions_and_messages_name_the_reports_claims():
    rep = parsed("$4a = 20 \\Rightarrow a = 6$", "Mathematics: Analysis and Approaches", None, "mathematics")
    alg = next(fc for fc in StemPack("mathematics").formal_checks_for(rep, None) if fc.kind == "stem_algebra")
    assert alg.claim_ids == ("m1.1",) and "[claims m1.1]" in alg.description and "[claims s1.1]" not in alg.description
    undec = parsed("f(x) = 3x^2 + 2x, so f'(x) = 6x + 1.", "Mathematics: Analysis and Approaches", None, "mathematics")
    found = [f for f in StemPack("mathematics").checks(undec, None) if f.code == "ST-UNDEC-001"]
    assert found and all(f.claim_ids == ["m1.1"] and "s1.1" not in f.message for f in found)
