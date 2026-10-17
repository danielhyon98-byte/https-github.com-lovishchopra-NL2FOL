"""The checks port's processing of one call: ``TurnChecker`` (``integration/PROTOCOL.md`` section 5.2, normative order).

One call uses one fresh hub from the overseer port (``new_hub``: a ``RouterHub`` with a ``TransferAuditor`` attached,
``replay_mode="process"``):

1. the request was validated by :func:`~epinoic_logic.integration.checks_port.check_request` (KIT-REQ codes);
2. build and seal a ``WorkPlan`` (subject from the subject map, the answers' agent ids, ``deadline_at``);
3. open the task and dispatch the student's message to each agent; the clearance of each dispatch receipt is checked
   before acting (a REJECTED dispatch is an integrity failure);
4. prefetch translations (live providers only; :class:`~epinoic_logic.integration.verifier.PrefetchingProvider`);
5. receive each answer as raw text (the branch parser extracts the claims; the STEM front end runs with
   ``min(STEM_CHECK_BUDGET_S, budget left)``); the clearance of each response receipt is checked before acting;
6. (combined mode only) the combinator port's synthesis, relayed through the hub: not offered until a combinator is
   connected (the capabilities omit the mode ``combined``);
7. ``close``: the FINAL audit, signed under ``overseer-audit``;
8. ``deliver``: consolidation and ``delivery_decision`` (single, duplicate), or ``release_decision`` (combined);
9. per-claim entries of the deliverable, the counts and the decision table under the named policy: the decision is
   made here and nothing after this step changes it;
10. when the asynchronous overseer-agent review is enabled: build the flash router's request, ask the router (in its own
    process) for a plan within what is left of the budget and at most ``router_timeout_s``, admit the plan against the
    minimum-oversight floor (or run the floor), and hand the review to the overseer port, which queues it. Any failure
    here (the router, the port's ``repeats`` or ``review``, an out-of-contract ticket) leaves the review unqueued
    (``queued: false``), is recorded in the evidence, and changes neither the decision nor its reasons. Then sign the
    verdict with the verdict key;
11. ``integration-sim`` only: write the call's evidence to the evidence tap.

Budget: one monotonic deadline covers steps 3 to 9; once it has passed the verifier returns ``None`` for the remaining
claims, which become NOT_ATTEMPTED (``skipped_budget``); STEM checks left over become NOT_ATTEMPTED (``stem_budget``).
The router of step 10 only gets what is left of that deadline, so the review never makes a call later than its budget.
An unexpected exception yields a signed verdict whose decision is ``refuse_incomplete`` with reason KIT-DL-900: never
``deliver``. The overseer is reached only through the port; every message it returns is validated before it is used.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from .capabilities import utc_now
from .claims import claim_entries
from .delivery import DecisionInput, count_claims, decide, sign_verdict, summarize
from .errors import IntegrationError
from .evidence_tap import EvidenceTap
from .overseer_port import (
    MAX_PENDING_WAIT_MS, check_clearance, check_delivery, check_final_audit, check_review_ticket,
)
from .protocol import AUDIT_SCOPE_STATEMENT, PROTOCOL, SCOPE_STATEMENT, TurnCheckRequest, dump
from .router_port import PLAN_TIMEOUT_S, RouterAttachment, route
from .routing_features import OutputRecord, build_routing_request
from .verifier import BudgetedVerifier, FixtureCorpus, VerifierLog

__all__ = ["CheckerConfig", "TurnChecker", "receipt_sha256", "report_id_for"]


def receipt_sha256(receipt: Any) -> str:
    """The digest the overseer journals for a receipt: SHA-256 of its canonical JSON (``mode=json``, nulls left out)."""
    from ..ir.canonical import canonical_json, sha256_hex
    return sha256_hex(canonical_json(receipt))


def report_id_for(task_id: str, agent_id: str, n: int = 1) -> str:
    """``rep_<turnId>_<agent>_v<n>`` (PROTOCOL.md section 2): at most 128 characters, ``@`` written as ``-``."""
    return f"rep_{task_id}_{agent_id.replace('@', '-')}_v{n}"[:128]


@dataclass(frozen=True)
class CheckerConfig:
    service_env: str
    versions: Mapping[str, Any]
    build: Mapping[str, Any]
    subject_map_sha256: str
    overseer_mode: str
    engine_key: bytes
    engine_key_id: str
    verdict_key: bytes
    verdict_key_id: str
    solver_config: Any
    max_translated_claims: int
    live_provider: bool
    review_async: bool
    review_profiles: Sequence[str] = ("standard",)
    review_max_instances: int = 4
    prefetch: bool = True
    #: The longest the review waits for the flash router's plan (never longer than what is left of the call's budget).
    router_timeout_s: float = PLAN_TIMEOUT_S


class TurnChecker:
    def __init__(self, config: CheckerConfig, *, port: Any, corpus: Optional[FixtureCorpus] = None,
                 live_verifier: Optional[Callable[..., Any]] = None, router: Optional[RouterAttachment] = None,
                 evidence_tap: Optional[EvidenceTap] = None, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], str] = utc_now) -> None:
        self.cfg = config
        self.port = port
        self.corpus = corpus
        self.live_verifier = live_verifier
        self.router = router
        self.tap = evidence_tap
        self.clock = clock
        self.wall = wall

    # ------------------------------------------------------------------------------------------------- public

    def check(self, req: TurnCheckRequest) -> dict:
        """The signed verdict of one validated request. Never raises."""
        started = self.clock()
        evidence: dict[str, Any] = {"request_id": req.ids.request_id, "receipts": [], "port": []}
        try:
            verdict = self._check(req, started, evidence)
        except Exception as exc:  # noqa: BLE001 - an unexpected failure never delivers
            evidence["internal_error"] = {"type": type(exc).__name__, "code": getattr(exc, "code", None), "trace": traceback.format_exc()[-1500:]}
            verdict = self._internal_error(req, started)
        evidence["verdict"] = verdict
        if self.tap is not None:
            try:
                self.tap.write(req.ids.request_id, evidence)
            except Exception:  # noqa: BLE001 - the tap never changes the verdict
                pass
        return verdict

    # ------------------------------------------------------------------------------------------------- steps

    def _verifier(self, req: TurnCheckRequest, deadline: float, log: VerifierLog) -> Any:
        if self.cfg.live_provider:
            return BudgetedVerifier(self.live_verifier, deadline=deadline, cap=self.cfg.max_translated_claims, live=True,
                                    clock=self.clock, task_aware=True, log=log).with_task()
        by_agent: dict[str, Any] = {}
        if self.corpus is not None:
            for a in req.answers:
                fn, _provider = self.corpus.verifier_for(a.answer_sha256, config=self.cfg.solver_config, signing_key=self.cfg.engine_key,
                                                         key_id=self.cfg.engine_key_id, prefetch=False)
                if fn is not None:
                    by_agent[a.agent_id] = fn

        def inner(claim: Any, report: Any) -> Any:
            fn = by_agent.get(report.agent_id)
            return fn(claim, report) if fn is not None else None
        return BudgetedVerifier(inner, deadline=deadline, cap=self.cfg.max_translated_claims, live=False, clock=self.clock, log=log).plain()

    def _plan(self, req: TurnCheckRequest, deadline_wall: str) -> Any:
        from ..integrity.contracts import WorkPlan, seal_plan
        from .compat import SUBJECT_MAP
        subjects = {e["slug"]: e["subject"] for e in SUBJECT_MAP["entries"]}
        agent_subjects = {a.agent_id: subjects[a.agent_id] for a in req.answers} if req.mode == "combined" else {}
        plan = WorkPlan(plan_id=f"plan-{req.ids.request_id}"[:128], request_id=req.ids.request_id, task_id=req.ids.task_id,
                        subject=req.task.subject, course_level=req.task.course_level, task_type=req.task.task_type,
                        selected_agent_ids=[a.agent_id for a in req.answers], agent_subjects=agent_subjects, deadline_at=deadline_wall)
        return seal_plan(plan)

    def _clear(self, hub: Any, task_id: str, receipt: Any, evidence: dict) -> Any:
        raw = self.port.clearance(hub, task_id, receipt.message_id, receipt, wait_ms=MAX_PENDING_WAIT_MS)
        evidence["port"].append({"op": "clearance", "message": dict(raw) if isinstance(raw, Mapping) else None})
        return check_clearance(raw, task_id=task_id, message_id=receipt.message_id, receipt_sha256=receipt_sha256(receipt))

    def _check(self, req: TurnCheckRequest, started: float, evidence: dict) -> dict:
        from ..channel.bus import STEM_CHECK_BUDGET_S
        from ..channel.contracts import TransmissionStatus
        from ..translate.contracts import SpecialistReport, SuppliedText

        cfg, task_id = self.cfg, req.ids.task_id
        deadline = started + req.budget_ms / 1000.0
        deadline_wall = (datetime.now(timezone.utc) + timedelta(milliseconds=req.budget_ms)).strftime("%Y-%m-%dT%H:%M:%SZ")
        log = VerifierLog()
        plan = self._plan(req, deadline_wall)
        overseer_ms = 0.0

        def timed(fn: Callable[[], Any]) -> Any:
            nonlocal overseer_ms
            t = self.clock()
            try:
                return fn()
            finally:
                overseer_ms += self.clock() - t

        hub = timed(lambda: self.port.new_hub(signing_key=cfg.engine_key, key_id=cfg.engine_key_id,
                                              verify_claim_fn=self._verifier(req, deadline, log), config=cfg.solver_config))
        channel = hub.open_task(plan)
        supplied = [SuppliedText(document_id=t.document_id, title=t.title, text=t.text) for t in req.task.supplied_texts]

        # 3. Dispatch, with a clearance before acting on each dispatch receipt.
        dispatched: list[tuple[Any, Any, Any]] = []
        for a in req.answers:
            msg, task_request, rc = hub.dispatch(task_id, a.agent_id, req.task.user_text, supplied)
            evidence["receipts"].append(dump_model(rc))
            if msg is None or rc.status is TransmissionStatus.REJECTED:
                return self._early(req, started, hub, rc, plan, evidence, refusal=None, overseer_ms_ref=lambda: overseer_ms, timed=timed)
            c = timed(lambda: self._clear(hub, task_id, rc, evidence))
            if not c.may_act:
                return self._early(req, started, hub, rc, plan, evidence, refusal="clearance_pending" if c.state == "AUDIT_PENDING" else "clearance_failed",
                                   overseer_ms_ref=lambda: overseer_ms, timed=timed)
            dispatched.append((a, msg, task_request))

        # 5. Receive each answer as raw text; the STEM checks get what is left of the budget (at most the module budget).
        received: list[tuple[Any, Any, Any]] = []
        for n, (a, msg, task_request) in enumerate(dispatched, start=1):
            channel.stem_budget_s = min(STEM_CHECK_BUDGET_S, max(0.0, deadline - self.clock()))
            reply, rc = hub.receive(task_id, msg.message_id, a.answer, agent_id=a.agent_id, report_id=report_id_for(task_id, a.agent_id))
            evidence["receipts"].append(dump_model(rc))
            if rc.status is not TransmissionStatus.REJECTED:
                c = timed(lambda: self._clear(hub, task_id, rc, evidence))
                if not c.may_act:
                    return self._early(req, started, hub, rc, plan, evidence, refusal="clearance_pending" if c.state == "AUDIT_PENDING" else "clearance_failed",
                                       overseer_ms_ref=lambda: overseer_ms, timed=timed)
            received.append((a, reply, rc))

        # 6. Combined mode is never offered before a combinator is connected (the request validation refuses it).
        if req.mode == "combined":  # pragma: no cover - refused by check_request while the capabilities omit it
            raise IntegrationError("KIT-REQ-002", "the combined mode needs a connected combinator")

        # 7. The FINAL audit.
        raw_final = timed(lambda: self.port.close(hub, task_id))
        evidence["port"].append({"op": "close", "message": dict(raw_final) if isinstance(raw_final, Mapping) else None})
        final = check_final_audit(raw_final, task_id=task_id)

        # 8. Delivery through the overseer's delivery rule.
        answers = [(a.agent_id, reply.message_id if reply is not None else rc.message_id, a.answer_sha256) for a, reply, rc in received]
        raw_delivery = timed(lambda: self.port.deliver(hub, task_id, mode=req.mode))
        evidence["port"].append({"op": "deliver", "message": dict(raw_delivery) if isinstance(raw_delivery, Mapping) else None})
        delivery = check_delivery(raw_delivery, task_id=task_id, final_audit_id=final.audit_id, answers=answers)

        # 9. Entries of the deliverable (the representative in duplicate mode), counts and the decision table.
        chosen = received[0]
        if delivery.deliverable is not None:
            chosen = next((r for r in received if r[0].agent_id == delivery.deliverable.agent_id), received[0])
        a, reply, rc = chosen
        claims = SpecialistReport.model_validate(reply.payload).claims if reply is not None else []
        entries, fields = claim_entries(rc, claims, a.answer, log)
        counts = count_claims(fields)
        inp = DecisionInput(policy=req.policy, revision_of=req.revision_of, receipt_status=rc.status.value,
                            receipt_error_codes=tuple(sorted({f.code for f in rc.findings if f.severity == "error"})),
                            overseer_state=final.state, delivery_allowed=delivery.allowed, overseer_refusal=delivery.refusal,
                            consolidation_status=delivery.consolidation.status if delivery.consolidation is not None else None,
                            blocking=counts["blocking"], unavailable=counts["unavailable"],
                            claims=tuple(fields))
        decision, reasons = decide(inp)

        # 10. The asynchronous review (never a release condition, never a change of the decision), then the signature.
        review = self._review(req, hub, task_id, received, dispatched[0][2], evidence, timed, deadline)
        verdict = self._assemble(req, started, plan, final.audit_id, final.channel_uid, received, rc, entries, counts, decision, reasons,
                                 deliverable=delivery.deliverable, consolidation=delivery.consolidation, final_state=final.state,
                                 final_codes=list(final.error_codes), delivery_allowed=delivery.allowed, refusal=delivery.refusal,
                                 review=review, log=log, overseer_ms=overseer_ms)
        return sign_verdict(verdict, cfg.verdict_key, cfg.verdict_key_id)

    def _review(self, req: TurnCheckRequest, hub: Any, task_id: str, received: Sequence[tuple[Any, Any, Any]], task_request: Any,
                evidence: dict, timed: Callable[[Callable[[], Any]], Any], deadline: float) -> dict:
        """Queue the asynchronous overseer-agent review under the admitted routing plan (step 10). ``task_request`` is
        the request record the dispatch returned (the hub's public return value, never channel internals).

        The decision is already made and this never changes it: the router gets at most ``min(router_timeout_s, what is
        left of the budget)`` and runs in its own process; every failure (the router, ``repeats``, ``review``, the
        ticket) leaves the review unqueued (``queued: false``), recorded in the evidence, and is never raised."""
        if not self.cfg.review_async:
            return {"queued": False, "plan_origin": None, "plan_refusal": None, "router": None}
        attached = self.router is not None and self.router.attached
        review: dict = {"queued": False, "plan_origin": None, "plan_refusal": None,
                        "router": dump(self.router.hello.router) if attached else None}  # type: ignore[union-attr]
        try:
            from ..translate.contracts import SpecialistReport
            repeats = timed(lambda: self.port.repeats(hub, task_id)) or {}
            outputs = []
            for a, reply, rc in received:
                key = reply.message_id if reply is not None else rc.message_id
                claims = SpecialistReport.model_validate(reply.payload).claims if reply is not None else []
                outputs.append(OutputRecord(transfer_key=key, role="answer", agent_id=a.agent_id, subject=req.task.subject, receipt=rc, claims=claims,
                                            text=a.answer, repeated_faults=int(repeats.get(key, 0)), peer_relays=0, diagnostics=()))
            topology = {"kind": req.mode, "sources": [], "synthesis": None}
            request = build_routing_request(task_id=task_id, request_id=req.ids.request_id, task_request=task_request, subjects=[req.task.subject],
                                            outputs=outputs, topology=topology, max_instances=self.cfg.review_max_instances,
                                            profiles=self.cfg.review_profiles)
            admission = route(request, self.router, timeout_s=min(self.cfg.router_timeout_s, max(0.0, deadline - self.clock())))
            evidence["admission"] = admission.record()
            review.update(plan_origin=admission.origin, plan_refusal=admission.refusal,
                          router=dump(admission.router) if admission.router is not None else None)
            raw_ticket = timed(lambda: self.port.review(hub, task_id, admission))
            ticket = check_review_ticket(raw_ticket, task_id=task_id, origin=admission.origin, plan_id=admission.effective.plan_id,
                                         refusal=admission.refusal)
            review["queued"] = ticket.queued
        except Exception as exc:  # noqa: BLE001 - the review never changes the decision: a failure leaves it unqueued
            code = getattr(exc, "code", None)
            evidence["review_error"] = {"type": type(exc).__name__, "code": code if isinstance(code, str) else None}
            review["queued"] = False
        return review

    def _early(self, req: TurnCheckRequest, started: float, hub: Any, rc: Any, plan: Any, evidence: dict, *, refusal: Optional[str],
               overseer_ms_ref: Callable[[], float], timed: Callable[[Callable[[], Any]], Any]) -> dict:
        """A dispatch REJECTED or a clearance not passed: close the task (the FINAL audit still seals the journal) and
        refuse. The deliverable is none; the receipt section is the failing receipt."""
        raw_final = timed(lambda: self.port.close(hub, req.ids.task_id))
        evidence["port"].append({"op": "close", "message": dict(raw_final) if isinstance(raw_final, Mapping) else None})
        final = check_final_audit(raw_final, task_id=req.ids.task_id)
        inp = DecisionInput(policy=req.policy, revision_of=req.revision_of, receipt_status=rc.status.value,
                            receipt_error_codes=tuple(sorted({f.code for f in rc.findings if f.severity == "error"})),
                            overseer_state=final.state, delivery_allowed=False, overseer_refusal=refusal, consolidation_status=None,
                            blocking=0, unavailable=0, claims=())
        decision, reasons = decide(inp)
        received = [(a, None, rc) for a in req.answers]
        verdict = self._assemble(req, started, plan, final.audit_id, final.channel_uid, received, rc, [], count_claims([]), decision, reasons,
                                 deliverable=None, consolidation=None, final_state=final.state, final_codes=list(final.error_codes),
                                 delivery_allowed=False, refusal=refusal,
                                 review={"queued": False, "plan_origin": None, "plan_refusal": None, "router": None},
                                 log=VerifierLog(), overseer_ms=overseer_ms_ref())
        return sign_verdict(verdict, self.cfg.verdict_key, self.cfg.verdict_key_id)

    def _assemble(self, req: TurnCheckRequest, started: float, plan: Any, audit_id: str, channel_uid: str, received: Sequence[tuple[Any, Any, Any]],
                  rc: Any, entries: list[dict], counts: Mapping[str, int], decision: str, reasons: list[str], *, deliverable: Any,
                  consolidation: Any, final_state: str, final_codes: list[str], delivery_allowed: bool, refusal: Optional[str],
                  review: dict, log: VerifierLog, overseer_ms: float) -> dict:
        cfg = self.cfg
        solver_ms = 0
        for o in getattr(rc, "outcomes", []) or []:
            if o.verification is not None:
                solver_ms += int(sum(t.ms for t in o.verification.timings))
        bound = [{"agent_id": a.agent_id, "answer_sha256": a.answer_sha256, "result_sha256": a.result_sha256,
                  "report_id": report_id_for(req.ids.task_id, a.agent_id),
                  "message_id": (reply.message_id if reply is not None else r.message_id)} for a, reply, r in received]
        summary = summarize(counts) if decision == "deliver" else None
        return {
            "schema": "epinoic.integration.turn-verdict.v1", "protocol": PROTOCOL,
            "verdict_id": f"vd_{req.ids.request_id}"[:128], "issued_at": self.wall(),
            "ids": {"task_id": req.ids.task_id, "request_id": req.ids.request_id, "plan_id": plan.plan_id, "channel_uid": channel_uid},
            "bound": {"user_text_sha256": req.task.user_text_sha256, "policy": req.policy, "mode": req.mode, "answers": bound},
            "service": {"service_env": cfg.service_env, "versions": dict(cfg.versions), "build": dict(cfg.build), "subject_map_sha256": cfg.subject_map_sha256},
            "delivery": {"decision": decision,
                         "deliverable": ({"agent_id": deliverable.agent_id, "answer_sha256": deliverable.answer_sha256, "message_id": deliverable.message_id}
                                         if deliverable is not None and decision == "deliver" else None),
                         "reasons": reasons,
                         "consolidation": ({"id": consolidation.id, "status": consolidation.status, "basis": consolidation.basis} if consolidation is not None else None),
                         "synthesis": None},
            "overseer": {"mode": cfg.overseer_mode, "final_audit_id": audit_id, "state": final_state,
                         "error_codes": sorted(set(c for c in final_codes if c.startswith("OVS-") and not c.startswith("OVS-AGENT-"))),
                         "delivery_allowed": delivery_allowed, "refusal": refusal, "review": review},
            "receipt": {"status": rc.status.value, "error_codes": sorted({f.code for f in rc.findings if f.severity == "error"}),
                        "warning_count": sum(1 for f in rc.findings if f.severity == "warning"), "branch": rc.branch or "generic"},
            "claims": entries, "counts": dict(counts), "summary": summary,
            "scope_statement": SCOPE_STATEMENT, "audit_scope_statement": AUDIT_SCOPE_STATEMENT,
            "timings": {"total_ms": int(max(0.0, self.clock() - started) * 1000), "translation_ms": log.translation_ms,
                        "solver_ms": solver_ms, "overseer_ms": int(overseer_ms * 1000)},
        }

    def _internal_error(self, req: TurnCheckRequest, started: float) -> dict:
        """The verdict after an unexpected exception: ``refuse_incomplete`` with KIT-DL-900, never ``deliver``."""
        cfg = self.cfg
        verdict = {
            "schema": "epinoic.integration.turn-verdict.v1", "protocol": PROTOCOL,
            "verdict_id": f"vd_{req.ids.request_id}"[:128], "issued_at": self.wall(),
            "ids": {"task_id": req.ids.task_id, "request_id": req.ids.request_id, "plan_id": f"plan-{req.ids.request_id}"[:128], "channel_uid": "none"},
            "bound": {"user_text_sha256": req.task.user_text_sha256, "policy": req.policy, "mode": req.mode,
                      "answers": [{"agent_id": a.agent_id, "answer_sha256": a.answer_sha256, "result_sha256": a.result_sha256,
                                   "report_id": report_id_for(req.ids.task_id, a.agent_id), "message_id": "none"} for a in req.answers]},
            "service": {"service_env": cfg.service_env, "versions": dict(cfg.versions), "build": dict(cfg.build), "subject_map_sha256": cfg.subject_map_sha256},
            "delivery": {"decision": "refuse_incomplete", "deliverable": None, "reasons": ["KIT-DL-900"], "consolidation": None, "synthesis": None},
            "overseer": {"mode": cfg.overseer_mode, "final_audit_id": "none", "state": "AUDIT_PENDING", "error_codes": [],
                         "delivery_allowed": False, "refusal": "internal_error",
                         "review": {"queued": False, "plan_origin": None, "plan_refusal": None, "router": None}},
            "receipt": {"status": "REJECTED", "error_codes": [], "warning_count": 0, "branch": "generic"},
            "claims": [], "counts": count_claims([]), "summary": None,
            "scope_statement": SCOPE_STATEMENT, "audit_scope_statement": AUDIT_SCOPE_STATEMENT,
            "timings": {"total_ms": int(max(0.0, self.clock() - started) * 1000), "translation_ms": 0, "solver_ms": 0, "overseer_ms": 0},
        }
        return sign_verdict(verdict, cfg.verdict_key, cfg.verdict_key_id)


def dump_model(model: Any) -> Any:
    try:
        return model.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return None
