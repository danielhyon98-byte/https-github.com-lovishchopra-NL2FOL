"""Delivery helpers for the D9/D10 branch tests (decision D35): a recorded or varied answer through ``RouterHub`` with its request, subject,
agent, task type and supplied texts, as the arena harness delivers it, and the receipt read back."""
from __future__ import annotations

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from . import d9d10_texts as T

KEY = b"branches-d9d10-regression-key-0123"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

GEO = ("Geography", "geography-specialist")
SPB = ("Language B: Spanish", "language-b-spanish-specialist")

#: The eight recorded answers: (name, answer, request, subject, agent, task type, supplied documents).
RECORDED = {
    "c1/ge-t14": (T.GE_T14, T.GE_T14_Q, *GEO, "fieldwork_report", (T.GE_T14_DOC,)),
    "c1/sp-t14": (T.SP_T14, T.SP_T14_Q, *SPB, "reading_comprehension", (T.SP_T14_DOC,)),
    "c2/ge-p9c": (T.GE_P9C, T.GE_P9C_Q, *GEO, "structured_question", ()),
    "c2/ge-t15": (T.GE_T15, T.GE_T15_Q, *GEO, "structured_question", (T.GE_T15_DOC,)),
    "c2/sp-t15": (T.SP_T15, T.SP_T15_Q, *SPB, "writing_task", ()),
    "c3/ge-t16": (T.GE_T16, T.GE_T16_Q, *GEO, "essay", ()),
    "c3/sp-p10d": (T.SP_P10D, T.SP_P10D_Q, *SPB, "language_notes", (T.SP_P10D_DOC,)),
    "c3/sp-t16": (T.SP_T16, T.SP_T16_Q, *SPB, "marking_feedback", (T.SP_T16_DOC,)),
}


def supplied(docs) -> list[SuppliedText]:
    return [SuppliedText(document_id=d[0], title=d[1], author=d[2], text=d[3]) for d in docs]


def through_hub(text: str, question: str, subject: str, agent: str, task_type: str = "short_answer", docs=(), *, hub: RouterHub | None = None):
    """The receipt of ``text`` delivered as ``agent``'s answer to ``question`` (a fresh hub unless one is given)."""
    hub = hub or RouterHub(signing_key=KEY, config=CFG)
    texts = supplied(docs)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "dummy-combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent, question, texts)
    _reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")
    return rc


def recorded(name: str, text: str | None = None):
    """The receipt of a recorded answer (or of ``text`` in its place, a variant of it) delivered as it was recorded."""
    answer, question, subject, agent, task_type, docs = RECORDED[name]
    return through_hub(answer if text is None else text, question, subject, agent, task_type, docs)


def codes(rc, *severities: str) -> list[str]:
    sev = severities or ("error", "warning")
    return sorted({f.code for f in rc.findings if f.severity in sev})


def checks(rc, prefix: str = "") -> list[tuple[str, str]]:
    return [(fc.constraint_id, fc.formal_status) for fc in rc.formal_checks if fc.constraint_id.startswith(prefix)]


def failed(rc, code: str = "INT-SUBJ-001") -> list:
    return [f for f in rc.findings if f.code == code]


def report(subject: str, agent: str, text: str, *, task_type: str = "short_answer", docs=(), claims=None) -> SpecialistReport:
    """A report built directly (one claim per given text, or one claim holding the whole answer)."""
    claims = claims or [dict(claim_id="c1", claim_text=text, claim_role="point", materiality="material")]
    return SpecialistReport(report_id="rep-u", request_id="r", task_id="t", agent_id=agent, subject=subject, task_type=task_type, original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=supplied(docs),
                            claims=[ClaimRecord(request_id="r", task_id="t", report_id="rep-u", agent_id=agent, subject=subject, task_type=task_type, **c)
                                    for c in claims], created_at="2026-11-16T00:00:00Z")
