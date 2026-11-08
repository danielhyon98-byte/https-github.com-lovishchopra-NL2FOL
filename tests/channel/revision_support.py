"""Shared material for the revision-request tests: an English task whose answer carries an invented quotation, and a
revision block built from the answer's receipt exactly as the overseer's builder builds it (``channel.feedback``), with
a placeholder signature: the channel never verifies a block's signature (the transfer auditor does, OVS-FB-001)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.channel import feedback as fb
from epinoic_logic.channel.contracts import RevisionClaim, RevisionFlaw, RevisionRequest
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

KEY = b"revision-test-engine-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
EXTRACT = ("The mill wheel turned all night. 'We work until the bell,' the foreman said, 'and then we sleep.' "
           "The children counted every hour in coal, and the town grew rich on their silence. In 1833 the mill employed 42% of the town.")
DOC = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous", text=EXTRACT)
QUESTION = "Analyse how the writer presents work in the extract. Use quotations from the extract. Write no more than 120 words."
SUBJECT = "English A: Literature"
GOOD_TEXT = ('The writer presents work as endless: the foreman\'s words "We work until the bell" make labour the measure of time, '
             'and the children "counted every hour in coal". In 1833 the mill employed 42% of the town.')
GOOD_CLAIMS = [
    dict(claim_id="p1", claim_text="The writer presents work as endless", claim_role="point"),
    dict(claim_id="e1", claim_text='The foreman\'s words "We work until the bell" make labour the measure of time', claim_role="evidence",
         materiality="supporting", source_refs=[SourceRef(document_id="doc-mill", excerpt="We work until the bell")]),
    dict(claim_id="e2", claim_text='The children "counted every hour in coal"', claim_role="evidence", materiality="supporting",
         source_refs=[SourceRef(document_id="doc-mill", excerpt="counted every hour in coal")]),
    dict(claim_id="f1", claim_text="In 1833 the mill employed 42% of the town.", claim_role="evidence", materiality="supporting"),
]
INVENTED = dict(claim_id="e3", claim_text='The foreman says "we never rest at all".', claim_role="evidence", materiality="supporting",
                source_refs=[SourceRef(document_id="doc-mill", excerpt="we never rest at all")])
BAD_TEXT = GOOD_TEXT + ' The foreman says "we never rest at all".'


def plan(**over) -> WorkPlan:
    base = dict(plan_id="plan-rev", request_id="req-rev", task_id="task-rev", subject=SUBJECT, task_type="analytical_paragraph",
                selected_agent_ids=["english-specialist", "history-specialist", "combinator"], allowed_document_ids=["doc-mill", "peer:en"],
                agent_subjects={"history-specialist": "History"})
    base.update(over)
    return WorkPlan(**base)


def report(text: str, claims: list[dict], *, report_id: str = "rep-1", agent: str = "english-specialist", docs=(DOC,), subject: str = SUBJECT,
           task_type: str = "analytical_paragraph") -> SpecialistReport:
    return SpecialistReport(report_id=report_id, request_id="req-rev", task_id="task-rev", agent_id=agent, subject=subject, task_type=task_type,
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=list(docs), created_at="2026-11-08T10:00:00Z",
                            claims=[ClaimRecord(request_id="req-rev", task_id="task-rev", report_id=report_id, agent_id=agent, subject=subject,
                                                task_type=task_type, **c) for c in claims])


@dataclass
class Case:
    ch: TranslatorChannel
    m: Any          # the original request's envelope
    req: Any        # the original request
    a: Any          # the answer's envelope (None when REJECTED)
    rc: Any         # the answer's receipt
    rep: SpecialistReport


def answer(text: str = BAD_TEXT, claims: Optional[list[dict]] = None, *, ch: Optional[TranslatorChannel] = None, report_id: str = "rep-1",
           question: str = QUESTION, docs=(DOC,), report_docs=None, **plan_over) -> Case:
    ch = ch or TranslatorChannel(plan(**plan_over), signing_key=KEY, key_id="hub", config=CFG)
    m, req, _rq = ch.request("router", "english-specialist", question, list(docs))
    rep = report(text, GOOD_CLAIMS + [INVENTED] if claims is None else claims, report_id=report_id, docs=docs if report_docs is None else report_docs)
    a, rc = ch.respond(m.message_id, rep)
    return Case(ch, m, req, a, rc, rep)


def answer_message_id(case: Case) -> str:
    return case.a.message_id if case.a is not None else case.rc.message_id


def flaws_for(case: Case, candidates=None, *, signature: str = "a" * 64) -> list[RevisionFlaw]:
    """The flaws the overseer's builder would feed back for ``case`` (every candidate, a placeholder signature)."""
    cands = fb.eligible_flaws(case.rc, case.rep, case.req) if candidates is None else candidates
    own = {c.claim_id: c for c in case.rep.claims}
    out = []
    for i, c in enumerate(cands[:12], start=1):
        out.append(RevisionFlaw(flaw_id=f"f{i}", code=c.code, severity=c.severity, flaw_class=c.flaw_class, basis=c.basis, rule=c.rule,
                                params=dict(c.params), instruction=fb.render_instruction(c.rule, dict(c.params)), removal_ok=c.removal_ok,
                                claims=[RevisionClaim(claim_id=cid, text=fb.quote_text(own[cid].claim_text)) for cid in c.claim_ids[:4]],
                                evidence=list(c.evidence), signature=signature if i == 1 else f"{i:064x}"))
    return out


def block_for(case: Case, *, flaws=None, round: int = 1, max_rounds: int = 2, original: Optional[str] = None, rerender: bool = True,
              **over) -> RevisionRequest:
    """A bound revision block for the answer of ``case`` (a placeholder signature under the feedback key id); ``over``
    replaces any field, and the rendered digest is recomputed unless ``rerender`` is False."""
    flaws = flaws_for(case) if flaws is None else flaws
    named, fidelity = fb.named_claim_ids(flaws)
    base = dict(revision_id="rev-" + "0" * 24, task_id=case.req.task_id, request_id=case.req.request_id, plan_id=case.req.plan_id,
                to_agent_id="english-specialist", revises_message_id=answer_message_id(case), revises_report_id=case.rep.report_id,
                revises_receipt_id=case.rc.receipt_id, original_request_message_id=original or case.m.message_id, round=round, max_rounds=max_rounds,
                flaws=flaws, must_not_change=fb.keep_list(case.req, case.rep, named, fidelity), rules=list(fb.REVISION_RULES), task_audit_id="audit-test",
                rendered_sha256="0" * 64, scope_statement=fb.REVISION_SCOPE, signature="1" * 64, signature_key_id="overseer-feedback")
    base.update(over)
    block = RevisionRequest(**base)
    return block.model_copy(update={"rendered_sha256": fb.rendered_digest(block)}) if rerender and "rendered_sha256" not in over else block


def issue(case: Case, block, *, sender: str = "router", to: str = "english-specialist", question: Optional[str] = None, docs=None, items=None,
          constraints=None):
    """Re-issue the original request with ``block`` (the hub's ``request_revision`` does exactly this)."""
    return case.ch.request(sender, to, case.req.user_input if question is None else question, list(case.req.supplied_texts) if docs is None else list(docs),
                           items=list(case.req.items) if items is None else items, constraints=list(case.req.constraints) if constraints is None else constraints,
                           revision=block)


def codes(receipt) -> list[str]:
    return sorted(f.code for f in receipt.findings)
