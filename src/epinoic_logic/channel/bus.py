"""The translator channel: every inter-agent message passes through here.

Router -> specialist: ``request`` makes the ask explicit (items, constraints, texts),
wraps it in a signed-hash envelope, checks it against the router's plan and logs it.

Specialist -> router: ``respond`` wraps the report in an envelope that must reply to
the request, then checks identity (same request/task, selected agent, in scope),
message integrity (replay, tampering), request fidelity (every required item
addressed; every constraint checked, formally where it is arithmetic), source
integrity (quotations against the supplied texts), and runs claim verification
through the injected translator. Nothing is delivered silently: the recipient gets a
``TransmissionReceipt`` and a REJECTED transmission is not delivered at all. Raw text
that the branch adapter cannot turn into a report, and a report whose payload does
not re-validate against the contract, are REJECTED with INT-REQ-009; the channel
never raises into the router.

Agent -> agent: ``relay`` carries a report or a synthesis between agents with the
same envelope and ledger checks, and cross-checks its formalized claims against
every claim already transmitted in the same request so contradictions between
agents are named, not reconciled. A synthesized claim that carries (or can be given)
a formal conclusion is checked for entailment by its formalized sources; when it
cannot be, the receipt says so instead of implying a check that nobody ran.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from pydantic import ValidationError

from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify
from ..engine.statuses import VerificationStatus as S, is_definitive
from ..integrity.contracts import AgentMessage, AgentRole, IntegrityFinding, Synthesis, SynthesizedClaim, WorkPlan, payload_hash
from ..integrity.cross_check import check_cross_report_consistency, check_paraphrase_coverage, check_synthesis_entailment
from ..integrity.envelope import MessageLog
from ..integrity.handoff import check_report_against_plan
from ..integrity.ledger import check_synthesis_ledger
from ..ir.canonical import sha256_hex
from ..ir.schema import Assertion, Problem
from ..translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, SuppliedText, sha256_text
from ..translate.grounding import check_claim_sources
from ..translate.contracts import StructuralFinding
from .contracts import Constraint, ConstraintResult, CoverageRecord, TaskRequest, TransmissionReceipt, TransmissionStatus
from .request_parser import LEVEL3_VERDICT_TERMS, count_paragraphs, count_words, extract_constraints, extract_items

VerifyClaimFn = Callable[[ClaimRecord, SpecialistReport], Optional[ClaimVerificationOutcome]]
#: Given a synthesized claim and the formalized problems of its cited sources, propose the
#: formal conclusion to test (an Assertion over the sources' shared glossary), or None.
FormalizeSynthesisFn = Callable[[SynthesizedClaim, list[Problem]], Optional[Assertion]]
ParseFn = Callable[..., SpecialistReport]

# Cues that state a position on degree (a claim such as "X was responsible for Y" is not one).
_VERDICT_CUE = re.compile(r"\b(therefore|thus|to a (?:large|great|limited|lesser|some|considerable) extent|to a degree|decisive|necessary (?:but|and) (?:not )?sufficient|outweigh(?:s|ed)?|on balance|more (?:significant|important|decisive) than|less (?:significant|important) than|holds for|does not hold|fails)\b", re.IGNORECASE)
_STOP = frozenset("the a an and or of to in on for with by is are was were be this that these those as at from it its how why what does do into their there which who whom not".split())
#: Error codes that stop delivery: identity, envelope, request binding, unparseable payload, ledger provenance.
_BLOCKING_PREFIXES = ("INT-HANDOFF", "INT-ENV", "INT-REQ-000", "INT-REQ-001", "INT-REQ-002", "INT-REQ-009", "INT-LEDGER-000", "INT-LEDGER-008")
_NOT_PERFORMED = "NOT performed on this channel: the combinator supplied no formal conclusion for this claim and no formalization hook is configured, so the router must not treat the content change as checked"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in _STOP}


def _is_blocking(findings) -> bool:
    """A transmission is withheld only for identity, envelope, request-binding, parse and
    ledger-provenance errors; a report delivered with findings counts as transmitted."""
    return any(f.severity == "error" and f.code.startswith(_BLOCKING_PREFIXES) for f in findings)


def _shape_reason(exc: BaseException) -> str:
    """Describe why parsing or validation failed without echoing the agent's text."""
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:6]:
            loc = ".".join(str(x) for x in e.get("loc", ()))
            parts.append(f"{loc or 'report'}: {e.get('type', 'invalid')}")
        more = len(exc.errors()) - 6
        return "; ".join(parts) + (f"; +{more} more" if more > 0 else "")
    return str(exc)[:300]


class TranslatorChannel:
    """One channel per router task. Keeps the message log, the requests, and every
    formalized claim transmitted so far (for cross-agent consistency)."""

    def __init__(self, plan: WorkPlan, *, signing_key: bytes, key_id: str = "channel",
                 verify_claim_fn: Optional[VerifyClaimFn] = None, config: SolverConfig = SolverConfig(), registry=None,
                 formalize_synthesis_fn: Optional[FormalizeSynthesisFn] = None) -> None:
        if not signing_key:
            raise ValueError("a signing key is required")
        if registry is None:
            from ..branches import default_registry
            registry = default_registry()
        self.registry = registry
        self.branch, self.profile = registry.for_subject(plan.subject)
        # An agent the plan assigns another subject (a History specialist consulted on a Literature task) is served by
        # that subject's branch: its requests carry that subject, its raw text is parsed by that branch's adapter and its
        # reports run through that branch's packs. Everything else on the channel (ledger, pool, hand-off) is shared.
        self._agent_branches = {aid: registry.for_subject(subj) for aid, subj in plan.agent_subjects.items()}
        self.plan = plan
        self.key = signing_key
        self.key_id = key_id
        self.verify_claim_fn = verify_claim_fn
        self.formalize_synthesis_fn = formalize_synthesis_fn
        self.config = config
        self.log = MessageLog()
        self.requests: dict[str, TaskRequest] = {}          # message_id -> request
        self.formalized: dict[str, Problem] = {}            # claim_id -> problem (shared glossary pool)
        self.formalized_by: dict[str, tuple[str, str]] = {}  # claim_id -> (agent_id, report_id) that contributed it
        self.transmitted_reports: dict[str, SpecialistReport] = {}
        self.receipts: list[TransmissionReceipt] = []
        self._seen_payloads: dict[str, str] = {}             # payload hash -> first message id

    def _branch_for(self, agent_id: Optional[str]):
        """(branch, profile) serving ``agent_id``: its own subject's branch when the plan assigns one, else the task's."""
        return self._agent_branches.get(agent_id or "", (self.branch, self.profile))

    def _subject_for(self, agent_id: Optional[str]) -> str:
        return self.plan.agent_subjects.get(agent_id or "", self.plan.subject)

    # ------------------------------------------------------------------ requests
    def request(self, from_agent_id: str, to_agent_id: str, user_input: str, supplied_texts: list[SuppliedText] = (),
                *, items=None, constraints=None) -> tuple[Optional[AgentMessage], TaskRequest, TransmissionReceipt]:
        req = TaskRequest(
            request_id=self.plan.request_id, task_id=self.plan.task_id, plan_id=self.plan.plan_id,
            from_agent_id=from_agent_id, to_agent_id=to_agent_id, subject=self._subject_for(to_agent_id), course_level=self.plan.course_level,
            task_type=self.plan.task_type, user_input=user_input, user_input_sha256=sha256_hex(user_input),
            items=list(items) if items is not None else extract_items(user_input),
            constraints=list(constraints) if constraints is not None else extract_constraints(user_input),
            supplied_texts=list(supplied_texts), created_at=_now(),
        )
        findings: list[IntegrityFinding] = []
        if to_agent_id not in self.plan.selected_agent_ids:
            findings.append(IntegrityFinding(code="INT-HANDOFF-002", severity="error", message=f"router addressed {to_agent_id}, which the plan did not select"))
        if self.plan.allowed_document_ids:
            outside = sorted({t.document_id for t in supplied_texts if t.document_id not in set(self.plan.allowed_document_ids)})
            if outside:
                findings.append(IntegrityFinding(code="INT-HANDOFF-004", severity="error", message=f"request carries documents outside the retrieval scope: {outside}"))
        payload = req.model_dump(mode="json", exclude_none=True)
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=req.request_id, task_id=req.task_id, sender_agent_id=from_agent_id,
                           sender_role=AgentRole.ROUTER, recipient_role=AgentRole.SPECIALIST, recipient_agent_id=to_agent_id,
                           contract="task_request/1.0", payload=payload, payload_sha256=payload_hash(payload), created_at=req.created_at)
        findings += self.log.accept(msg)
        status = TransmissionStatus.REJECTED if any(f.severity == "error" for f in findings) else TransmissionStatus.ACCEPTED
        if status is not TransmissionStatus.REJECTED:
            self.requests[msg.message_id] = req
        receipt = self._receipt(msg.message_id, "router_to_specialist", status, findings, summary=self._summary_request(req, findings, status))
        return (msg if status is not TransmissionStatus.REJECTED else None), req, receipt

    # ----------------------------------------------------------------- responses
    def respond_text(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, supplied_texts: Optional[list[SuppliedText]] = None,
                     agent_version: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        """Parse a specialist's raw text with the branch's adapter, then run ``respond``.

        Text the adapter cannot turn into a valid report (empty, over the contract
        limits, malformed) yields a REJECTED receipt with INT-REQ-009; nothing raises."""
        req = self.requests.get(request_message_id)
        texts = supplied_texts if supplied_texts is not None else (req.supplied_texts if req else [])
        branch, _profile = self._branch_for(agent_id)
        parser = branch.parser()
        try:
            report = parser.parse_response(text, request_id=self.plan.request_id, task_id=self.plan.task_id, report_id=report_id, subject=self._subject_for(agent_id),
                                           task_type=self.plan.task_type, supplied_texts=list(texts), course_level=self.plan.course_level or "unknown", agent_version=agent_version, agent_id=agent_id)
        except Exception as exc:  # adapter and contract errors become a rejection, never an exception out of the hub
            return self._unparseable(request_message_id, text, agent_id=agent_id, report_id=report_id, exc=exc, branch_key=branch.key)
        return self.respond(request_message_id, report)

    def _unparseable(self, request_message_id: str, text: str, *, agent_id: str, report_id: str, exc: BaseException, branch_key: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        branch_key = branch_key or self.branch.key
        payload = {"report_id": report_id, "agent_id": agent_id, "request_id": self.plan.request_id, "task_id": self.plan.task_id,
                   "response_sha256": sha256_text(text), "response_chars": len(text), "parse_error": type(exc).__name__}
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=self.plan.request_id, task_id=self.plan.task_id, sender_agent_id=agent_id,
                           sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0",
                           payload=payload, payload_sha256=payload_hash(payload), in_reply_to=request_message_id, created_at=_now())
        findings = self.log.accept(msg)
        findings.append(IntegrityFinding(code="INT-REQ-009", severity="error",
                                         message=f"response could not be parsed into a report by branch {branch_key}: {type(exc).__name__}: {_shape_reason(exc)}",
                                         report_ids=[report_id], agent_ids=[agent_id], message_ids=[msg.message_id]))
        return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=branch_key)

    def _revalidate(self, report: SpecialistReport, payload: dict) -> list[IntegrityFinding]:
        """The payload delivered to the recipient must re-validate against the contract;
        a report built around validation (model_copy) is caught here, not downstream."""
        try:
            SpecialistReport.model_validate(payload)
        except ValidationError as exc:
            return [IntegrityFinding(code="INT-REQ-009", severity="error", message=f"report payload does not re-validate against the specialist_report contract and is not delivered: {_shape_reason(exc)}",
                                     report_ids=[report.report_id], agent_ids=[report.agent_id])]
        return []

    def _branch_checks(self, report: SpecialistReport, req: Optional[TaskRequest], findings: list[IntegrityFinding], covered: frozenset[str] = frozenset()) -> tuple[list[StructuralFinding], list[ConstraintResult], list[str]]:
        """Run the branch's integrity packs. ``covered`` names the claims whose unfound
        quotation the channel already reported (INT-REQ-003): the packs' own grounding
        errors for those claims are kept in the receipt's structural findings but not
        escalated again, so one unverified excerpt yields one error finding."""
        branch, _profile = self._branch_for(report.agent_id)
        structural, formal = branch.run_packs(report, req.user_input if req else None)
        if covered:
            structural = [sf for sf in structural if not (sf.code == "CORE-SRC-001" and sf.claim_ids and set(sf.claim_ids) <= covered)]
        results: list[ConstraintResult] = []
        ids: list[str] = []
        for fc in formal:
            res = verify(fc.problem, self.config, signing_key=self.key, key_id=self.key_id)
            ids.append(res.result_id)
            sat = True if res.status.value == fc.expected_if_sound else (False if res.status in (S.COUNTEREXAMPLE, S.INCONSISTENT_PREMISES, S.UNSATISFIABLE) else None)
            results.append(ConstraintResult(constraint_id=fc.check_id, satisfied=sat, method="formal", detail=f"{fc.kind}: {fc.description}; solver {res.status.value}", formal_result_id=res.result_id, formal_status=res.status.value))
            if sat is False:
                findings.append(IntegrityFinding(code="INT-SUBJ-001", severity="error", message=f"the report's own {fc.kind} statement does not hold: {fc.description}", formal_result_id=res.result_id, deterministic=False))
            elif sat is None:
                findings.append(IntegrityFinding(code="INT-SUBJ-002", severity="warning", message=f"{fc.kind} check undecided ({res.status.value}): {fc.description}", formal_result_id=res.result_id, deterministic=False))
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for sf in structural:
            if sf.severity != "error":
                continue
            key = (sf.code, tuple(sorted(sf.claim_ids)))
            if key in seen:
                continue
            seen.add(key)
            if sf.code.endswith("-SRC-001") and sf.claim_ids and set(sf.claim_ids) <= covered:
                continue  # the same unfound excerpt is already an INT-REQ-003 error naming the branch rule
            findings.append(IntegrityFinding(code="INT-SUBJ-003", severity="error", message=f"[{branch.key}] {sf.code}: {sf.message}", claim_ids=list(sf.claim_ids)))
        return structural, results, ids

    @staticmethod
    def _name_branch_rules(findings: list[IntegrityFinding], structural: list[StructuralFinding]) -> list[IntegrityFinding]:
        """INT-REQ-003 names the branch rule(s) that cover the same unverified excerpt."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.code == "INT-REQ-003" and f.claim_ids:
                rules = sorted({sf.code for sf in structural if sf.code.endswith("-SRC-001") and set(f.claim_ids) & set(sf.claim_ids)})
                if rules:
                    f = f.model_copy(update={"message": f.message + f" (branch rules: {', '.join(rules)})"})
            out.append(f)
        return out

    def respond(self, request_message_id: str, report: SpecialistReport) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        req = self.requests.get(request_message_id)
        findings: list[IntegrityFinding] = []
        payload = report.model_dump(mode="json", exclude_none=True)
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=report.request_id, task_id=report.task_id, sender_agent_id=report.agent_id,
                           sender_role=AgentRole.SPECIALIST, recipient_role=AgentRole.ROUTER, contract="specialist_report/1.0",
                           payload=payload, payload_sha256=payload_hash(payload), in_reply_to=request_message_id, created_at=_now())
        findings += self.log.accept(msg)
        findings += self._dedupe(msg)
        findings += self._revalidate(report, payload)
        bk = self._branch_for(report.agent_id)[0].key
        if req is None:
            findings.append(IntegrityFinding(code="INT-REQ-000", severity="error", message="response does not reply to any accepted request on this channel", message_ids=[msg.message_id, request_message_id]))
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        if any(f.code == "INT-REQ-009" for f in findings):
            return self._finish(msg, "specialist_to_router", findings, [], [], [], branch_key=bk)
        if report.agent_id != req.to_agent_id:
            findings.append(IntegrityFinding(code="INT-REQ-001", severity="error", message=f"response came from {report.agent_id} but the request was addressed to {req.to_agent_id}"))
        findings += check_report_against_plan(self.plan, report)
        supplied = req.supplied_texts or report.supplied_texts
        report_docs = {t.document_id for t in report.supplied_texts}
        req_docs = {t.document_id for t in req.supplied_texts}
        if req_docs and report_docs and not report_docs <= req_docs:
            findings.append(IntegrityFinding(code="INT-REQ-002", severity="error", message=f"response cites texts that were not in the request: {sorted(report_docs - req_docs)}"))
        covered: set[str] = set()
        for c in report.claims:
            for g in check_claim_sources(c, supplied):
                if g.verified is False:
                    findings.append(IntegrityFinding(code="INT-REQ-003", severity="error", message=f"quotation cited by claim {c.claim_id} was not found in the supplied text", claim_ids=[c.claim_id]))
                    covered.add(c.claim_id)
        coverage = self._coverage(req, report)
        for cov in coverage:
            if not cov.addressed:
                item = next(i for i in req.items if i.item_id == cov.item_id)
                findings.append(IntegrityFinding(code="INT-REQ-004", severity="warning" if item.required else "info", message=f"request item {cov.item_id} appears unaddressed: {item.text[:120]!r} (heuristic)", claim_ids=[]))
        # Command terms C6: evaluate / discuss / to what extent / assess / examine / justify / recommend need a
        # judgement or position on degree. A judgement-role claim counts; so does a point, thesis or link that
        # states a position (verdict cue); a bare claim does not. A claim roled 'other' (a note, a self-report) never counts.
        verdict_present = any(c.claim_role == "judgement" or (c.claim_role in ("point", "thesis", "link") and _VERDICT_CUE.search(c.claim_text)) for c in report.claims)
        for item in req.items:
            if item.level == 3 and item.command_term in LEVEL3_VERDICT_TERMS and not verdict_present:
                findings.append(IntegrityFinding(code="INT-REQ-008", severity="warning", message=f"item {item.item_id} uses the command term {item.command_term!r}, which requires a judgement or position on degree; no judgement/point claim was found (command terms C6)", claim_ids=[]))
        constraint_results, formal_ids = self._constraints(req, report)
        structural, branch_formal, branch_ids = self._branch_checks(report, req, findings, frozenset(covered))
        findings = self._name_branch_rules(findings, structural)
        formal_ids = list(formal_ids) + branch_ids
        for cr in constraint_results:
            if cr.satisfied is False:
                findings.append(IntegrityFinding(code="INT-REQ-005", severity="error", message=f"constraint {cr.constraint_id} not satisfied: {cr.detail}", formal_result_id=cr.formal_result_id, deterministic=cr.method != "formal"))
        self._supersession(report, findings)
        outcomes = self._verify_claims(report, findings)
        if not _is_blocking(findings):  # delivered <=> transmitted: a synthesis may cite any report the router received
            self.transmitted_reports[report.report_id] = report
        return self._finish(msg, "specialist_to_router", findings, coverage, constraint_results, outcomes, formal_ids, structural=structural, branch_formal=branch_formal, branch_key=bk)

    # --------------------------------------------------------------- agent relay
    def relay(self, from_agent_id: str, from_role: AgentRole, to_agent_id: str, to_role: AgentRole,
              payload_obj: Union[SpecialistReport, Synthesis], in_reply_to: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        findings: list[IntegrityFinding] = []
        payload = payload_obj.model_dump(mode="json", exclude_none=True)
        forward = isinstance(payload_obj, SpecialistReport) and from_role is AgentRole.ROUTER
        contract = ("specialist_report_forward/1.0" if forward else "specialist_report/1.0") if isinstance(payload_obj, SpecialistReport) else "synthesis/1.0"
        msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=payload_obj.request_id, task_id=payload_obj.task_id, sender_agent_id=from_agent_id,
                           sender_role=from_role, recipient_role=to_role, recipient_agent_id=to_agent_id, contract=contract,
                           payload=payload, payload_sha256=payload_hash(payload), in_reply_to=in_reply_to, created_at=_now())
        findings += self.log.accept(msg)
        findings += self._dedupe(msg)
        if payload_obj.request_id != self.plan.request_id or payload_obj.task_id != self.plan.task_id:
            findings.append(IntegrityFinding(code="INT-HANDOFF-001", severity="error", message="relayed payload belongs to another request/task", message_ids=[msg.message_id]))
        outcomes: list[ClaimVerificationOutcome] = []
        structural: list[StructuralFinding] = []
        branch_formal: list[ConstraintResult] = []
        branch_ids: list[str] = []
        bk = self._branch_for(payload_obj.agent_id)[0].key if isinstance(payload_obj, SpecialistReport) else self.branch.key
        if isinstance(payload_obj, SpecialistReport):
            findings += self._revalidate(payload_obj, payload)
            if any(f.code == "INT-REQ-009" for f in findings):
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            if forward:
                # The router may only pass on a report exactly as it was delivered on this channel: same report id,
                # same payload digest. Anything else is a report altered in transit or never received.
                held = self.transmitted_reports.get(payload_obj.report_id)
                if held is None:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"router forwarded report {payload_obj.report_id!r}, which was never delivered on this channel", report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id]))
                elif payload_hash(held.model_dump(mode="json", exclude_none=True)) != msg.payload_sha256:
                    findings.append(IntegrityFinding(code="INT-HANDOFF-013", severity="error", message=f"router forwarded report {payload_obj.report_id!r} with a payload that differs from the one delivered on this channel (altered in transit)", report_ids=[payload_obj.report_id], agent_ids=[from_agent_id, to_agent_id], message_ids=[msg.message_id]))
                if _is_blocking(findings):
                    return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
                # The delivered report was already parsed, checked and pooled on arrival; a faithful forward re-runs
                # the hand-off checks (plan scope, self-reports) but not the subject packs and verification.
                findings += check_report_against_plan(self.plan, payload_obj)
                return self._finish(msg, "agent_to_agent", findings, [], [], [], branch_key=bk)
            findings += check_report_against_plan(self.plan, payload_obj)
            structural, branch_formal, branch_ids = self._branch_checks(payload_obj, None, findings)
            self._supersession(payload_obj, findings)
            outcomes = self._verify_claims(payload_obj, findings)
            if not _is_blocking(findings):
                self.transmitted_reports[payload_obj.report_id] = payload_obj
        else:
            findings += check_synthesis_ledger(list(self.transmitted_reports.values()), payload_obj)
            ent_findings, ent_ids, checked = self._synthesis_entailment(payload_obj)
            findings += ent_findings
            branch_ids += ent_ids
            findings = self._state_synthesis_checks(findings, checked)
        return self._finish(msg, "agent_to_agent", findings, [], [], outcomes, branch_ids, structural=structural, branch_formal=branch_formal, branch_key=bk)

    def _synthesis_entailment(self, synthesis: Synthesis) -> tuple[list[IntegrityFinding], list[str], dict[str, Optional[str]]]:
        """For each synthesized claim with formalized sources: obtain a formal conclusion
        (the combinator's ``formal_conclusion`` or the channel's hook) and decide, with
        the engine, whether it follows from the sources it cites. Returns the findings,
        the signed result ids, and per claim the result id of the check or None when
        none could be run."""
        out: list[IntegrityFinding] = []
        ids: list[str] = []
        checked: dict[str, Optional[str]] = {}
        for sc in synthesis.claims:
            sources = [self.formalized[s] for s in sc.source_claim_ids if s in self.formalized]
            if not sources:
                continue
            unformalized = [s for s in sc.source_claim_ids if s not in self.formalized]
            concl = sc.formal_conclusion
            if concl is None and self.formalize_synthesis_fn is not None:
                try:
                    concl = self.formalize_synthesis_fn(sc, sources)
                except Exception as exc:  # the channel never drops a message because a hook crashed
                    out.append(IntegrityFinding(code="INT-SYNTH-013", severity="warning", message=f"formalization of synthesized claim {sc.claim_id} failed internally ({type(exc).__name__}); its entailment was not checked", claim_ids=[sc.claim_id]))
            if concl is None:
                checked[sc.claim_id] = None
                continue
            res, f = check_synthesis_entailment(sources, concl, request_id=self.plan.request_id, synthesized_claim_id=sc.claim_id, config=self.config, signing_key=self.key, unformalized_source_ids=unformalized)
            out += self._with_report_ids(f)
            if res is not None:
                ids.append(res.result_id)
                ids.extend(rid for x in f for rid in x.related_result_ids)
            checked[sc.claim_id] = res.result_id if res is not None else None
            if sc.transformation in ("carried", "paraphrased") and len(sources) == 1 and not unformalized:
                res2, f2 = check_paraphrase_coverage(sources[0], concl, request_id=self.plan.request_id, synthesized_claim_id=sc.claim_id, config=self.config, signing_key=self.key)
                out += f2
                if res2 is not None:
                    ids.append(res2.result_id)
        return out, ids, checked

    @staticmethod
    def _state_synthesis_checks(findings: list[IntegrityFinding], checked: dict[str, Optional[str]]) -> list[IntegrityFinding]:
        """The ledger's INT-LEDGER-011 says a formal check is required; the receipt must
        say whether this channel performed it."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.code == "INT-LEDGER-011" and f.claim_ids:
                rid = checked.get(f.claim_ids[0])
                if rid:
                    f = f.model_copy(update={"message": f.message.replace("check required", f"check performed on this channel (formal result {rid})"), "formal_result_id": rid})
                else:
                    f = f.model_copy(update={"message": f.message.replace("check required", "check " + _NOT_PERFORMED)})
            out.append(f)
        return out

    # ------------------------------------------------------------------ internals
    def _dedupe(self, msg: AgentMessage) -> list[IntegrityFinding]:
        role = getattr(msg.recipient_role, "value", str(msg.recipient_role))
        key = f"{msg.payload_sha256}|{role}|{msg.recipient_agent_id or ''}"  # the same report forwarded to another recipient is a hand-off, not a replay
        first = self._seen_payloads.get(key)
        if first is not None:
            return [IntegrityFinding(code="INT-ENV-001", severity="warning", message="identical payload already transmitted to this recipient on this channel (replay or duplicate delivery)", message_ids=[msg.message_id, first])]
        self._seen_payloads[key] = msg.message_id
        return []

    def _coverage(self, req: TaskRequest, report: SpecialistReport) -> list[CoverageRecord]:
        out: list[CoverageRecord] = []
        for item in req.items:
            it = _terms(item.text)
            hits = [c.claim_id for c in report.claims if it and len(it & _terms(c.claim_text)) >= max(1, min(2, len(it) // 3))]
            out.append(CoverageRecord(item_id=item.item_id, addressed=bool(hits) or not it, addressed_by_claim_ids=hits, method="lexical_heuristic"))
        return out

    def _constraints(self, req: TaskRequest, report: SpecialistReport) -> tuple[list[ConstraintResult], list[str]]:
        results: list[ConstraintResult] = []
        formal_ids: list[str] = []
        words = count_words(report.original_response)
        paras = count_paragraphs(report.original_response)
        for c in req.constraints:
            if c.kind in ("max_words", "min_words", "max_paragraphs", "min_paragraphs") and c.value is not None:
                measured = words if c.kind.endswith("words") else paras
                res = self._formal_bound(req, c, measured)
                formal_ids.append(res.result_id)
                sat = True if res.status is S.ENTAILED else False if res.status is S.COUNTEREXAMPLE else None
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=sat, method="formal",
                                                detail=f"measured {measured} {'words' if c.kind.endswith('words') else 'paragraphs'}; bound {c.kind} {c.value}; solver {res.status.value}",
                                                formal_result_id=res.result_id, formal_status=res.status.value))
            elif c.kind == "must_cite_supplied_text":
                cited = any(cl.source_refs for cl in report.claims)
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=cited, method="deterministic", detail="at least one claim carries a source reference" if cited else "no claim carries a source reference"))
            else:
                results.append(ConstraintResult(constraint_id=c.constraint_id, satisfied=None, method="not_checkable", detail="constraint kind not checkable by code"))
        return results, formal_ids

    def _formal_bound(self, req: TaskRequest, c: Constraint, measured: int) -> VerificationResult:
        """Encode 'measured <op> bound' as an IR entailment so the check is a signed, bound result."""
        op = {"max_words": "le", "min_words": "ge", "max_paragraphs": "le", "min_paragraphs": "ge"}[c.kind]
        problem = Problem.model_validate({
            "problem_id": f"constraint-{c.constraint_id}-{uuid.uuid4().hex[:8]}", "request_id": req.request_id, "claim_id": f"constraint:{c.constraint_id}", "query": "entailment",
            "symbols": [{"name": "n", "sort": "Int", "meaning": f"measured count for {c.kind}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "premises": [{"id": "MEASURED", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": str(measured)}}, "label": f"response has {measured}", "grounding": {"kind": "supplied_text", "verified": True}}],
            "conclusion": {"id": "BOUND", "expr": {"op": op, "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": c.value}}, "label": c.text, "grounding": {"kind": "task_setting", "verified": True}},
        })
        return verify(problem, self.config, signing_key=self.key, key_id=self.key_id)

    def _supersession(self, report: SpecialistReport, findings: list[IntegrityFinding]) -> None:
        """An agent that re-states claim ids it already transmitted on this task
        supersedes its earlier statements: the router is told (INT-HANDOFF-009) and the
        earlier formalizations of those claims leave the cross-agent pool, so a later
        report is cross-checked only on what it formalizes now."""
        incoming = {c.claim_id for c in report.claims}
        earlier = sorted({r.report_id for r in self.transmitted_reports.values()
                          if r.agent_id == report.agent_id and r.report_id != report.report_id and incoming & {c.claim_id for c in r.claims}})
        stale = sorted(cid for cid in incoming if cid in self.formalized_by and self.formalized_by[cid][0] == report.agent_id and self.formalized_by[cid][1] != report.report_id)
        if earlier:
            overlap = sorted(incoming & {c.claim_id for r in self.transmitted_reports.values() if r.report_id in earlier for c in r.claims})
            findings.append(IntegrityFinding(code="INT-HANDOFF-009", severity="warning",
                                             message=f"agent {report.agent_id} delivered a further report for this task re-stating claims {overlap[:8]} of its earlier report(s) {earlier}; the later report supersedes them and their earlier formalizations leave the cross-agent pool",
                                             agent_ids=[report.agent_id], report_ids=[report.report_id] + earlier, claim_ids=overlap))
        for cid in stale:
            self.formalized.pop(cid, None)
            self.formalized_by.pop(cid, None)

    def _with_report_ids(self, findings: list[IntegrityFinding]) -> list[IntegrityFinding]:
        """Cross-agent findings name the reports whose formalizations they concern."""
        out: list[IntegrityFinding] = []
        for f in findings:
            if f.claim_ids and not f.report_ids:
                rids = sorted({self.formalized_by[cid][1] for cid in f.claim_ids if cid in self.formalized_by})
                if rids:
                    f = f.model_copy(update={"report_ids": rids, "agent_ids": sorted(set(f.agent_ids) | {self.formalized_by[cid][0] for cid in f.claim_ids if cid in self.formalized_by})})
            out.append(f)
        return out

    def _verify_claims(self, report: SpecialistReport, findings: list[IntegrityFinding]) -> list[ClaimVerificationOutcome]:
        outcomes: list[ClaimVerificationOutcome] = []
        if self.verify_claim_fn is None:
            return outcomes
        contributed = 0
        for c in report.claims:
            try:
                out = self.verify_claim_fn(c, report)
            except Exception as exc:  # the channel never drops a message because verification crashed
                findings.append(IntegrityFinding(code="INT-REQ-006", severity="warning", message=f"claim verification failed internally for {c.claim_id}: {type(exc).__name__}", claim_ids=[c.claim_id]))
                continue
            if out is None:
                continue
            outcomes.append(out)
            if out.translation.problem is not None:
                self.formalized[c.claim_id] = out.translation.problem
                self.formalized_by[c.claim_id] = (report.agent_id, report.report_id)
                contributed += 1
            if out.verification is not None and out.verification.status is S.INCONSISTENT_PREMISES:
                findings.append(IntegrityFinding(code="INT-REQ-007", severity="error", message=f"claim {c.claim_id} rests on premises that contradict each other", claim_ids=[c.claim_id], formal_result_id=out.verification.result_id, deterministic=False))
        if contributed and len(self.formalized) >= 2:  # only a report that formalized something can be party to a conflict
            res, f = check_cross_report_consistency(list(self.formalized.values()), request_id=self.plan.request_id, config=self.config, signing_key=self.key)
            findings.extend(self._with_report_ids(f))
        return outcomes

    def _finish(self, msg: AgentMessage, direction: str, findings, coverage, constraint_results, outcomes, formal_ids=(), *, structural=(), branch_formal=(), branch_key: Optional[str] = None) -> tuple[Optional[AgentMessage], TransmissionReceipt]:
        structural = list(structural)
        branch_key = branch_key or self.branch.key
        blocking = _is_blocking(findings)
        subject_flag = any(sf.severity in ("error", "warning") for sf in structural)
        if blocking:
            status = TransmissionStatus.REJECTED
        elif findings or subject_flag or any(o.verification is not None and not is_definitive(o.verification.status) for o in outcomes):
            status = TransmissionStatus.ACCEPTED_WITH_FINDINGS
        else:
            status = TransmissionStatus.ACCEPTED
        ids = list(formal_ids) + [o.verification.result_id for o in outcomes if o.verification is not None] + [f.formal_result_id for f in findings if f.formal_result_id]
        receipt = self._receipt(msg.message_id, direction, status, findings, coverage=coverage, constraint_results=constraint_results, outcomes=outcomes,
                                formal_ids=sorted(set(ids)), structural=structural, branch_formal=branch_formal, branch_key=branch_key,
                                summary=self._summary_response(status, findings, coverage, constraint_results, outcomes, structural, branch_formal, branch_key))
        return (msg if status is not TransmissionStatus.REJECTED else None), receipt

    def _receipt(self, message_id: str, direction: str, status: TransmissionStatus, findings, *, coverage=(), constraint_results=(), outcomes=(), formal_ids=(), structural=(), branch_formal=(), summary: str, branch_key: Optional[str] = None) -> TransmissionReceipt:
        r = TransmissionReceipt(receipt_id=uuid.uuid4().hex, message_id=message_id, request_id=self.plan.request_id, task_id=self.plan.task_id, direction=direction,
                                status=status, findings=list(findings), coverage=list(coverage), constraint_results=list(constraint_results), outcomes=list(outcomes),
                                branch=branch_key or self.branch.key, structural_findings=list(structural), formal_checks=list(branch_formal),
                                formal_result_ids=list(formal_ids), summary=summary, created_at=_now())
        self.receipts.append(r)
        return r

    @staticmethod
    def _summary_request(req: TaskRequest, findings, status) -> str:
        return (f"Request {status.value}: {len(req.items)} item(s) extracted, {len(req.constraints)} constraint(s) ({', '.join(c.kind for c in req.constraints) or 'none'}), "
                f"{len(req.supplied_texts)} supplied text(s); findings: {', '.join(f.code for f in findings) or 'none'}.")

    @staticmethod
    def _summary_response(status, findings, coverage, constraint_results, outcomes, structural=(), branch_formal=(), branch="generic") -> str:
        covered = sum(1 for c in coverage if c.addressed)
        verdicts = {}
        for o in outcomes:
            verdicts[o.display_status.value] = verdicts.get(o.display_status.value, 0) + 1
        bf = ", ".join(f"{c.constraint_id}={'ok' if c.satisfied else 'FAILED' if c.satisfied is False else 'undecided'}" for c in branch_formal) or "none"
        histogram: dict[str, int] = {}
        for sf in structural:
            histogram[sf.code] = histogram.get(sf.code, 0) + 1
        subject = ", ".join(f"{code} x{n}" for code, n in sorted(histogram.items())) or "none"
        return (f"Transmission {status.value} via branch {branch}. Items addressed (heuristic): {covered}/{len(coverage)}. Request constraints: "
                + (", ".join(f"{c.constraint_id}={'ok' if c.satisfied else 'FAILED' if c.satisfied is False else 'unchecked'}" for c in constraint_results) or "none")
                + f". Report's own formal checks: {bf}. Subject findings: {subject}. Claim outcomes: {verdicts or 'none'}. "
                f"Findings: {', '.join(sorted({f.code for f in findings})) or 'none'}. "
                "Formal results concern only the encoded checks under their premises; coverage is heuristic.")
