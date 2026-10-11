"""Shared fixtures for the Overseer audit tests: test keys, synthetic tasks, and the manual observation helper.

``observe(channel, auditor)`` drives :func:`~epinoic_logic.channel.events.observe_call` (which opens
``capture_results`` and builds the event with ``snapshot_event``) around the channel's four entry points, so the
auditor sees every transfer without any hook in ``bus.py``. Keys are test constants; there is no network and no model
call: claim outcomes come from fixed problems verified by the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.channel.events import observation_state, observe_call
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.overseer import EngineKey, KeyRing, TransferAuditor
from epinoic_logic.translate.contracts import (
    ClaimRecord, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText, TranslationResult, TranslationStatus, sha256_text,
)
from epinoic_logic.translate.outcome import compose_outcome

KEY = b"overseer-test-engine-key-0123456789abcdef"
OTHER_KEY = b"some-other-engine-key-0123456789abcdef!"
SECRET = b"overseer-test-secret-0123456789abcdef-0123"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
ENGINE_IDS = ("hub", "channel", "default", "integrity", "t")

EXTRACT = ("The mill wheel turned all night. 'We work until the bell,' the foreman said, 'and then we sleep.' "
           "The children counted every hour in coal, and the town grew rich on their silence.")
DOC = SuppliedText(document_id="doc-mill", title="Mill extract", author="Anonymous", text=EXTRACT)
EN_INPUT = "Analyse how the writer presents work in the extract. Use quotations from the extract. Write no more than 80 words."
HI_INPUT = "Explain the significance of the Factory Act of 1833. Write no more than 120 words."
EN_TEXT = ('The writer presents work as endless: the foreman\'s words "We work until the bell" make labour the measure of time, '
           'and the children "counted every hour in coal", so time itself is paid in fuel.')
EN_CLAIMS = [
    dict(claim_id="en-point", claim_text="The writer presents work as endless", claim_role="point", materiality="material"),
    dict(claim_id="en-ev1", claim_text="We work until the bell", claim_role="evidence", materiality="supporting",
         source_refs=[SourceRef(document_id="doc-mill", excerpt="We work until the bell")]),
    dict(claim_id="en-ev2", claim_text="counted every hour in coal", claim_role="evidence", materiality="supporting",
         source_refs=[SourceRef(document_id="doc-mill", excerpt="counted every hour in coal")]),
    dict(claim_id="en-an", claim_text="time itself is paid in fuel", claim_role="interpretation", materiality="supporting"),
]
HI_TEXT = ("The Factory Act of 1833 banned the employment of children under nine in textile mills. "
           "The Ten Hours Act of 1847 followed the Factory Act of 1833. "
           "On balance, the Act mattered most because it established inspection.")
EN_SUBJECT = "English A: Literature"


def make_keyring(**extra) -> KeyRing:
    keys: dict[str, Any] = {k: EngineKey(KEY) for k in ENGINE_IDS}
    keys.update(extra)
    return KeyRing(keys, SECRET)


def make_auditor(**kw) -> TransferAuditor:
    opts = dict(replay_mode="inline", eager=True, shadow="always")
    opts.update(kw)
    keyring = opts.pop("keyring", None) or make_keyring()
    return TransferAuditor(keyring, **opts)


class Observed:
    """A channel whose four entry points are driven through ``observe_call`` by hand (no bus hook). Every other
    attribute is the channel's own."""

    def __init__(self, channel: TranslatorChannel, observers):
        self.__dict__["channel"] = channel
        self.__dict__["observers"] = list(observers)
        self.__dict__["state"] = observation_state(channel)

    def _call(self, name: str, a: tuple, k: dict):
        return observe_call(self.channel, name, a, k, self.observers, state=self.state)

    def request(self, *a, **k):
        return self._call("request", a, k)

    def respond(self, *a, **k):
        return self._call("respond", a, k)

    def respond_text(self, *a, **k):
        return self._call("respond_text", a, k)

    def relay(self, *a, **k):
        return self._call("relay", a, k)

    @property
    def uid(self) -> str:
        return self.state.channel_uid

    def __getattr__(self, name):
        return getattr(self.channel, name)


def observe(channel: TranslatorChannel, auditor: TransferAuditor) -> Observed:
    return Observed(channel, [auditor.observer_for(channel)])


def make_plan(**over) -> WorkPlan:
    base = dict(plan_id="plan-ovs", request_id="req-ovs", task_id="task-ovs", subject=EN_SUBJECT, task_type="analytical_paragraph",
                selected_agent_ids=["english-specialist", "history-specialist", "combinator"], allowed_document_ids=["doc-mill", "peer:en"],
                agent_subjects={"history-specialist": "History"}, agent_task_types={"history-specialist": "short_answer"})
    base.update(over)
    return WorkPlan(**base)


def english_report(text: str = EN_TEXT, claims=None, *, report_id: str = "rep-en-1", agent: str = "english-specialist", request_id: str = "req-ovs",
                   task_id: str = "task-ovs", docs=(DOC,), created_at: str = "2026-10-11T11:00:00Z") -> SpecialistReport:
    claims = EN_CLAIMS if claims is None else claims
    return SpecialistReport(report_id=report_id, request_id=request_id, task_id=task_id, agent_id=agent, subject=EN_SUBJECT, task_type="analytical_paragraph",
                            original_response=text, response_sha256=sha256_text(text), supplied_texts=list(docs), created_at=created_at,
                            claims=[ClaimRecord(request_id=request_id, task_id=task_id, report_id=report_id, agent_id=agent, subject=EN_SUBJECT,
                                                task_type="analytical_paragraph", **c) for c in claims])


def int_problem(claim_id: str, symbol: str, value: int, *, op: str = "gt", bound: int = 0, request_id: str = "req-ovs", problem_id: Optional[str] = None) -> Problem:
    """``symbol = value`` (grounded) entails ``symbol <op> bound``."""
    V = {"op": "var", "name": symbol}
    return Problem.model_validate({
        "problem_id": problem_id or f"p-{claim_id}", "request_id": request_id, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": symbol, "sort": "Int", "meaning": f"the {symbol} the claim states"}],
        "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": V, "right": {"op": "int", "value": str(value)}}, "label": f"{symbol} is {value}",
                      "grounding": {"kind": "arithmetic_fact"}}],
        "conclusion": {"id": "C", "expr": {"op": op, "left": V, "right": {"op": "int", "value": str(bound)}}, "label": f"{symbol} {op} {bound}"},
    })


def translation_for(claim: ClaimRecord, report: SpecialistReport, problem: Optional[Problem], *, status=TranslationStatus.TRANSLATED,
                    text_digest: Optional[str] = "auto") -> TranslationResult:
    return TranslationResult(
        translation_id=f"tr-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=report.report_id, status=status,
        eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="test"),
        claim_text_sha256=sha256_text(claim.claim_text) if text_digest == "auto" else text_digest,
        problem=problem, translator_version="test", policy_version="test", created_at="2026-10-11T11:00:00Z")


def outcome_for(claim: ClaimRecord, report: SpecialistReport, problem: Problem, *, key: bytes = KEY, key_id: str = "t"):
    """A genuine outcome: the problem verified by the engine (inside the channel call, so captured) and composed."""
    tr = translation_for(claim, report, problem)
    ver = verify(problem, CFG, signing_key=key, key_id=key_id)
    return compose_outcome(claim, tr, ver, signing_key=key, key_id=key_id)


def problems_fn(problems: dict[str, Problem], *, transform: Optional[Callable] = None):
    """A ``verify_claim_fn`` serving genuine outcomes for the claim ids in ``problems``; ``transform(outcome, claim,
    report)`` may tamper with the outcome before the channel sees it."""
    def fn(claim, report):
        p = problems.get(claim.claim_id)
        if p is None:
            return None
        out = outcome_for(claim, report, p)
        return transform(out, claim, report) if transform is not None else out
    return fn


@dataclass
class Task:
    ch: Observed
    auditor: TransferAuditor
    mids: dict[str, str] = field(default_factory=dict)
    receipts: dict[str, Any] = field(default_factory=dict)
    messages: dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.ch.uid

    def audit(self, **kw):
        return self.auditor.audit(self.uid, **kw)

    def codes(self, audit=None) -> list[str]:
        a = audit or self.audit()
        return sorted({f.code for f in a.report.findings})

    def errors(self, audit=None) -> list:
        a = audit or self.audit()
        return [f for f in a.report.findings if f.severity == "error"]


def new_channel(auditor: TransferAuditor, plan: Optional[WorkPlan] = None, *, verify_claim_fn=None, key_id: str = "hub", config: SolverConfig = CFG, **kw) -> Observed:
    ch = TranslatorChannel(plan or make_plan(), signing_key=KEY, key_id=key_id, verify_claim_fn=verify_claim_fn, config=config, **kw)
    return observe(ch, auditor)


def run_task(auditor: TransferAuditor, *, en_problems: Optional[dict] = None, hi_problems: Optional[dict] = None, synthesis: bool = True,
             peer: bool = True, en_report: Optional[SpecialistReport] = None, synthesis_obj: Optional[Synthesis] = None, plan: Optional[WorkPlan] = None,
             conflicts: tuple = (), before_synthesis: Optional[Callable[["Task"], None]] = None) -> Task:
    """The synthetic task: an English request and structured report, a forward of it to the History specialist, a
    History request carrying the forwarded report as ``peer:en``, the History raw text (parsed by the History branch),
    and a synthesis by the combinator. Every transfer crosses the observed channel."""
    en_problems = {"en-point": int_problem("en-point", "work_hours", 12, op="gt", bound=8)} if en_problems is None else en_problems
    hi_problems = {"h1.1": int_problem("h1.1", "min_age", 9, op="ge", bound=9)} if hi_problems is None else hi_problems
    ch = new_channel(auditor, plan)
    task = Task(ch=ch, auditor=auditor)
    ch.channel.verify_claim_fn = problems_fn(en_problems)
    m, _req, rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    task.mids["req_en"], task.receipts["req_en"] = m.message_id, rq
    report = en_report or english_report()
    reply, rc = ch.respond(m.message_id, report)
    task.mids["rep_en"], task.receipts["rep_en"], task.messages["rep_en"] = rc.message_id, rc, reply
    texts = []
    if peer and reply is not None:
        fwd, rf = ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload), in_reply_to=reply.message_id)
        task.mids["fwd"], task.receipts["fwd"] = rf.message_id, rf
        texts = [SuppliedText(document_id="peer:en", title="English specialist report", author="english-specialist", text=report.original_response)]
    ch.channel.verify_claim_fn = problems_fn(hi_problems)
    m2, _req2, rq2 = ch.request("router", "history-specialist", HI_INPUT, texts)
    task.mids["req_hi"], task.receipts["req_hi"] = m2.message_id, rq2
    reply2, rc2 = ch.respond_text(m2.message_id, HI_TEXT, agent_id="history-specialist", report_id="rep-hi-1")
    task.mids["rep_hi"], task.receipts["rep_hi"], task.messages["rep_hi"] = rc2.message_id, rc2, reply2
    if before_synthesis is not None:
        before_synthesis(task)
    if synthesis:
        syn = synthesis_obj or default_synthesis(conflicts=conflicts)
        ms, rs = ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
        task.mids["syn"], task.receipts["syn"], task.messages["syn"] = rs.message_id, rs, ms
    return task


def now_rfc3339() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_synthesis(*, conflicts: tuple = (), claims=None, ledger=None, text: Optional[str] = None, created_at: Optional[str] = None,
                      source_report_ids=("rep-en-1", "rep-hi-1")) -> Synthesis:
    """The combinator's synthesis of the synthetic task: every material claim carried, the supporting ones dropped with
    reasons. ``created_at`` defaults to now, so it never precedes the reports it cites."""
    from epinoic_logic.integrity.contracts import ConflictRecord
    claims = claims if claims is not None else [
        SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried"),
        SynthesizedClaim(claim_id="s2", text="The Factory Act of 1833 banned the employment of children under nine in textile mills.", source_claim_ids=["h1.1"], transformation="carried"),
        SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried"),
    ]
    ledger = ledger if ledger is not None else [
        LedgerEntry(source_claim_ids=["en-ev1", "en-ev2", "en-an"], transformation="dropped", reason="supporting evidence summarised by the carried point"),
        LedgerEntry(source_claim_ids=["h1.2"], transformation="dropped", reason="supporting detail beyond the synthesis's scope"),
    ]
    created_at = created_at or now_rfc3339()
    text = text or " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-1", request_id="req-ovs", task_id="task-ovs", combinator_agent_id="combinator", source_report_ids=list(source_report_ids),
                     claims=claims, ledger=ledger, conflicts=[ConflictRecord(**c) for c in conflicts], text=text, text_sha256=sha256_text(text), created_at=created_at)


@pytest.fixture
def auditor():
    a = make_auditor()
    yield a
    a.close()


@pytest.fixture
def keyring() -> KeyRing:
    return make_keyring()


def codes_of(audit) -> set[str]:
    return {f.code for f in audit.report.findings}


def findings(audit, code: str) -> list:
    return [f for f in audit.report.findings if f.code == code]


def ovs_errors(audit, *, allow=("OVS-DIV-001",)) -> list:
    return [f for f in audit.report.findings if f.severity == "error" and f.code not in allow]
