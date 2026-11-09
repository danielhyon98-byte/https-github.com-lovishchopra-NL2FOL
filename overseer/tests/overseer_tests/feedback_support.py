"""Shared material for the specialist-feedback tests (design section 53): an audited hub with an English answer carrying
an invented quotation, a Physics answer with a wrong arithmetic step, and the helpers that ask for a revision and deliver
one. Every transfer crosses the hub's channel with the transfer auditor attached; no model is called."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.api.ir import SourceRef

from .conftest import CFG, DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, KEY, english_report, make_auditor, make_plan

INVENTED = dict(claim_id="en-ev3", claim_text='The foreman says "we never rest at all".', claim_role="evidence", materiality="supporting",
                source_refs=[SourceRef(document_id="doc-mill", excerpt="we never rest at all")])
BAD_EN = EN_TEXT + ' The foreman says "we never rest at all".'
PH_QUESTION = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
PH_BAD = ("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². "
          "The acceleration is therefore 6.0 m s⁻².")
PH_GOOD = ("The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻². "
           "The acceleration is therefore 5.0 m s⁻².")


@dataclass
class HubCase:
    hub: RouterHub
    auditor: Any
    task_id: str
    agent: str
    m: Any
    a: Any
    rc: Any

    @property
    def uid(self) -> str:
        return self.hub.channels[self.task_id].channel_uid

    def ask(self, answer_message_id: Optional[str] = None):
        return self.hub.request_revision(self.task_id, answer_message_id or self.a.message_id)

    def deliver(self, issue, payload, *, report_id: str):
        """The router delivers the specialist's revision in reply to the revision request, under a new report id."""
        if isinstance(payload, str):
            return self.hub.receive(self.task_id, issue.message.message_id, payload, agent_id=self.agent, report_id=report_id)
        return self.hub.receive(self.task_id, issue.message.message_id, payload)

    def close(self) -> None:
        self.hub.close()


def english_case(text: str = BAD_EN, claims=None, *, budget: Optional[int] = None, plan: Optional[WorkPlan] = None, verify=None) -> HubCase:
    aud = make_auditor()
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=aud, verify_claim_fn=verify)
    plan = plan or make_plan(**({"budgets": {"revision_rounds": budget}} if budget is not None else {}))
    hub.open_task(plan)
    m, _req, _rq = hub.dispatch(plan.task_id, "english-specialist", EN_INPUT, [DOC])
    a, rc = hub.receive(plan.task_id, m.message_id, english_report(text, EN_CLAIMS + [INVENTED] if claims is None else claims, report_id="rep-en-1"))
    return HubCase(hub, aud, plan.task_id, "english-specialist", m, a, rc)


def physics_case(text: str = PH_BAD, *, budget: Optional[int] = None) -> HubCase:
    aud = make_auditor()
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=aud)
    plan = WorkPlan(plan_id="plan-ph", request_id="req-ph", task_id="task-ph", subject="Physics", task_type="short_answer",
                    selected_agent_ids=["physics-specialist"], **({"budgets": {"revision_rounds": budget}} if budget is not None else {}))
    hub.open_task(plan)
    m, _req, _rq = hub.dispatch("task-ph", "physics-specialist", PH_QUESTION, [])
    a, rc = hub.receive("task-ph", m.message_id, text, agent_id="physics-specialist", report_id="rep-ph-1")
    return HubCase(hub, aud, "task-ph", "physics-specialist", m, a, rc)


def en_report(text: str, claims, report_id: str):
    return english_report(text, claims, report_id=report_id)


def codes_of_audit(audit) -> set[str]:
    return {f.code for f in audit.report.findings}
