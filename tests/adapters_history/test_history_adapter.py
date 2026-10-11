"""History specialist adapter on the pack's own Example 1 and the corpus mutations, and the
History fixtures through the real engine and the hub."""
import json
from pathlib import Path

from epinoic_logic.adapters.history_specialist import HistorySpecialistAdapter, fixtures, structural_checks
from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
CORPUS = Path(__file__).resolve().parents[2] / "docs" / "qa_corpus" / "history"
KEY = b"history-test-key-0123456789abcdef"


def mutation(name: str) -> str:
    return json.loads((CORPUS / "mutations" / f"{name}.json").read_text())["text"]


def parse(text: str, rid="rep"):
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid)


def test_body1_roles_follow_the_claim_evidence_analysis_judgement_link_operation():
    rep = parse(fixtures.EXAMPLE1_BODY1)
    roles = [c.claim_role for c in rep.claims]
    assert roles[0] == "point" and roles.count("evidence") >= 2 and "counter_evidence" in roles and "judgement" in roles
    point = rep.claims[0]
    assert set(point.supporting_claim_ids) == {c.claim_id for c in rep.claims[1:]}
    assert all(c.certainty in ("established", "probable", "possible") for c in rep.claims)


def test_structural_checks_on_genuine_and_mutated_paragraphs():
    clean = {f.code for f in structural_checks(parse(fixtures.EXAMPLE1_BODY1))}
    assert "HI-STR-001" not in clean and "HI-SRC-002" not in clean and "HI-SRC-003" not in clean
    assert "HI-SRC-004" in clean  # figures from memory without a label in the paragraph itself
    assert "HI-STR-001" in {f.code for f in structural_checks(parse(mutation("missing_judgement"), "m1"))}
    assert "HI-SRC-002" in {f.code for f in structural_checks(parse(mutation("proves_wording"), "m2"))}
    assert "HI-SRC-003" in {f.code for f in structural_checks(parse(mutation("invented_historian"), "m3"))}


def test_history_fixtures_through_the_engine():
    r = verify(Problem.model_validate(fixtures.FIGURE_CONSISTENCY["problem"]), CFG)
    assert r.status.value == "ENTAILED" and set(r.ungrounded_dependencies) == set(r.premises_relied_on) and r.premises_relied_on  # every figure is from memory
    assert verify(Problem.model_validate(fixtures.CHRONOLOGY_OK["problem"]), CFG).status.value == "ENTAILED"
    bad = verify(Problem.model_validate(fixtures.CHRONOLOGY_ERROR["problem"]), CFG)
    assert bad.status.value == "COUNTEREXAMPLE"
    chain = verify(Problem.model_validate(fixtures.ARGUMENT_CHAIN["problem"]), CFG)
    assert chain.status.value == "ENTAILED" and {"A1", "A2", "J3"} <= set(chain.ungrounded_dependencies)
    contra = verify(Problem.model_validate(fixtures.CONTRADICTORY_FIGURES["problem"]), CFG)
    assert contra.status.value == "INCONSISTENT_PREMISES" and sorted(contra.unsat_core.premise_ids) == ["V32A", "V32B"]
    inflated = verify(Problem.model_validate(fixtures.INFLATED_VS_LIBRARY["problem"]), CFG)
    assert inflated.status.value == "INCONSISTENT_PREMISES" and sorted(inflated.unsat_core.premise_ids) == ["LIB", "REPORT"]


def test_history_paragraph_travels_router_to_specialist_and_back_through_the_hub():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="essay", selected_agent_ids=["history-specialist"]))
    m, req, _ = hub.dispatch("t", "history-specialist", fixtures.QUESTION)
    assert req.items[0].command_term == "to what extent" and req.items[0].level == 3
    _, receipt = hub.receive("t", m.message_id, fixtures.EXAMPLE1_BODY1, agent_id="history-specialist", report_id="rep-h1")
    assert receipt.branch == "history" and receipt.status is not TransmissionStatus.REJECTED
    assert not any(f.code == "INT-REQ-008" for f in receipt.findings)          # the paragraph carries a judgement
    assert not receipt.errors
    assert any(sf.code == "HI-SRC-004" for sf in receipt.structural_findings)  # figures from memory surfaced to the router
    m2, _, _ = hub.dispatch("t", "history-specialist", fixtures.QUESTION)
    _, r2 = hub.receive("t", m2.message_id, mutation("missing_judgement"), agent_id="history-specialist", report_id="rep-h2")
    # The counter-case and its weighing are gone (subject pack HI-STR-001); the link still states a degree,
    # so the coarser channel rule INT-REQ-008 does not fire here.
    assert any(sf.code == "HI-STR-001" for sf in r2.structural_findings)
    sentences = fixtures.EXAMPLE1_BODY1.split(". ")
    no_verdict_at_all = ". ".join(sentences[:4]) + "."  # claim + evidence + mechanism only
    m4, _, _ = hub.dispatch("t", "history-specialist", fixtures.QUESTION)
    _, r4 = hub.receive("t", m4.message_id, no_verdict_at_all, agent_id="history-specialist", report_id="rep-h4")
    assert any(f.code == "INT-REQ-008" for f in r4.findings)
    m3, _, _ = hub.dispatch("t", "history-specialist", fixtures.QUESTION)
    _, r3 = hub.receive("t", m3.message_id, mutation("self_certification"), agent_id="history-specialist", report_id="rep-h3")
    assert r3.status is not TransmissionStatus.REJECTED and {f.code for f in r3.errors} == set()
