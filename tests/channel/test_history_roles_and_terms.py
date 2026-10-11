"""History-pack driven behaviour: claim roles of the Claim-Evidence-Analysis-Judgement-Link
operation, the three-source grounding kinds, and command-term levels on request items."""
from epinoic_logic.channel import TranslatorChannel, detect_command_term, extract_items
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, EligibilityClass, SpecialistReport, sha256_text
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.subjects import resolve_profile

CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def claim(role, text, report_id="rep", **kw):
    return ClaimRecord(request_id="r", task_id="t", report_id=report_id, agent_id="history-specialist", subject="History", task_type="essay", claim_id=f"c-{role}", claim_text=text, claim_role=role, **kw)


def test_history_roles_eligibility():
    assert decide_eligibility(claim("judgement", "The claim holds for the early period but not after 1936", supporting_claim_ids=["c-evidence", "c-counter_evidence"])).eligibility_class is EligibilityClass.PROPOSITIONAL_ARGUMENT
    assert decide_eligibility(claim("analysis", "The mechanism was that the Depression destroyed the security of moderate voters")).eligibility_class is EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE
    assert decide_eligibility(claim("perspective", "Structuralist historians argue the Depression activated older flaws")).eligibility_class is EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE
    dated = decide_eligibility(claim("evidence", "Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932"))
    assert dated.eligibility_class is EligibilityClass.QUANTITATIVE_CLAIM and dated.eligible
    undated = decide_eligibility(claim("origin", "A speech by a party leader to recruits"))
    assert undated.eligibility_class is EligibilityClass.NOT_ELIGIBLE_FACTUAL and undated.route_to == "evidence_service"
    assert decide_eligibility(claim("value", "Valuable for what officials believed")).eligibility_class is EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE


def test_history_profile_allows_exact_date_and_figure_consistency():
    p = resolve_profile("History HL")
    assert p.allows(EligibilityClass.QUANTITATIVE_CLAIM) and not p.argument_only
    assert "historically accurate" in p.cannot_check
    assert resolve_profile("Philosophy").argument_only


def test_general_knowledge_is_an_ungrounded_dependency():
    problem = Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "u1928", "sort": "Real"}, {"name": "u1932", "sort": "Real"}],
        "premises": [
            {"id": "F1", "expr": {"op": "eq", "left": {"op": "var", "name": "u1928"}, "right": {"op": "real", "value": "1400000"}}, "grounding": {"kind": "general_knowledge", "certainty": "probable"}},
            {"id": "F2", "expr": {"op": "eq", "left": {"op": "var", "name": "u1932"}, "right": {"op": "real", "value": "6000000"}}, "grounding": {"kind": "library_source", "source_refs": [{"document_id": "lib-textbook", "locator": "ch.4"}]}},
        ],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "u1932"}, "right": {"op": "mul", "args": [{"op": "real", "value": "4"}, {"op": "var", "name": "u1928"}]}}},
    })
    r = verify(problem, CFG)
    assert r.status.value == "ENTAILED" and r.ungrounded_dependencies == ["F1"]


def test_command_terms_detected_with_levels():
    assert detect_command_term("To what extent was the Great Depression responsible for the Nazi rise to power?") == ("to what extent", 3)
    assert detect_command_term("Compare and contrast the two sources.") == ("compare and contrast", 2)
    assert detect_command_term("Define inflation.") == ("define", 1)
    assert detect_command_term("Analyse how the writer presents justice.") == ("analyse", 3)
    items = extract_items("Evaluate the role of the elite in January 1933. Outline two economic factors.")
    assert [(i.command_term, i.level) for i in items] == [("evaluate", 3), ("outline", 2)]


def test_level3_item_without_judgement_is_flagged_on_the_channel():
    plan = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["history-specialist"])
    ch = TranslatorChannel(plan, signing_key=b"k" * 32, config=CFG)
    msg, req, _ = ch.request("router", "history-specialist", "To what extent was the Great Depression responsible for the Nazi Party's rise to power by January 1933?")
    assert req.items[0].level == 3
    text = "Unemployment rose from 1.4 million in 1928 to six million by 1932. The Nazi vote rose from 2.6 per cent to 37.3 per cent."
    rep = SpecialistReport(report_id="rep", request_id="r", task_id="t", agent_id="history-specialist", subject="History", task_type="essay", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T13:00:00Z",
                           claims=[claim("evidence", "Unemployment rose from 1.4 million in 1928 to six million by 1932")])
    _, receipt = ch.respond(msg.message_id, rep)
    assert any(f.code == "INT-REQ-008" for f in receipt.findings)
    with_judgement = SpecialistReport(report_id="rep2", request_id="r", task_id="t", agent_id="history-specialist", subject="History", task_type="essay", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T13:00:00Z",
                                      claims=[claim("evidence", "Unemployment rose from 1.4 million in 1928 to six million by 1932", report_id="rep2"),
                                              claim("judgement", "The Depression was necessary but not sufficient", report_id="rep2", supporting_claim_ids=["c-evidence"])])
    msg2, _, _ = ch.request("router", "history-specialist", "To what extent was the Great Depression responsible?")
    _, receipt2 = ch.respond(msg2.message_id, with_judgement)
    assert not any(f.code == "INT-REQ-008" for f in receipt2.findings)
