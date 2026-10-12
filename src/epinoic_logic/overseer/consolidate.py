"""Consolidation: ONE consolidated response for the router when several agents answer the same input.

When the router sends one user input to several agents (duplicated instances of one specialist, or several
specialists), the infrastructure, never an agent, consolidates their answers into one :class:`ConsolidatedResponse`
(contract ``consolidated_response/1.0``), signed under the overseer's ``consolidation`` subkey (key id
``overseer-consolidation``). Design ``docs/OVERSEER_DESIGN.md`` section 19. :func:`consolidate` reads only the journal
(an :class:`~epinoic_logic.overseer.view.OverseerView`), the signed task audit and the result store:

1. **The answers.** The accepted requests carrying the input (equal ``user_input_sha256``) and every ``response`` or
   ``response_text`` transfer replying to one of them, in journal order.
2. **Exclusion.** An answer is excluded, never grouped, when it was not delivered (REJECTED, withheld, content not
   retained), when its receipt or the task audit carries an error-level finding naming it (``INT-*`` on the receipt,
   ``OVS-*`` in the audit), when its transfer's clearance in the audit is not passed (failed, pending, or not covered),
   or when it repeats a fault (``OVS-REP-001``, :mod:`~epinoic_logic.overseer.repeats`). Each exclusion names the codes
   and the signed results the findings cite (``OVS-CONS-001``).
3. **Grouping, deterministic.** First by identical normalised text: ``original_response`` under the fidelity
   normalisation (``checks.normalise``; no case folding). Then level-1 groups whose MATERIAL claims (materiality
   ``material``, role not ``other``) have equal keys are merged only when the engine confirms them: the key of a claim
   is its content form (``repeats.content_form``) with its figures and dates (``repeats.figures_of``) and its quoted
   phrases (``repeats.quotations_of``), and the key of an answer is the sorted list of its material claims' keys
   (rule ``material-claim-key/2``). The whole answer must also state the same figures and dates
   (:func:`answer_facts`, over its ``original_response``): groups whose supporting claims or unclaimed prose differ in a
   figure or a date stay apart, with an advisory note naming the difference (``OVS-CONS-003``), so they are disclosed as
   a conflict, never presented as one answer. The merge check pools the formalized material claims (TRANSLATED or
   AMBIGUOUS_TRANSLATION outcomes on the receipts) of every member, each renamed so that two agents' claim ids never
   collide, and runs ``check_cross_report_consistency`` as an auditor run (unsigned, then signed under
   ``overseer-run`` and stored, as the auditor's own runs are). Only a definitive CONSISTENT over a pool holding at least
   one formalized claim of every level-1 group merges them (basis ``same_material_claims``). Anything else (a
   contradiction, an undecided or unbuildable check, a group with no formalized material claim) keeps the groups apart
   and is recorded as an advisory note (``OVS-CONS-003``): semantic sameness the engine cannot decide never merges groups.
4. **Canonical representative.** For each group, the earliest member whose receipt is fully clean (status ACCEPTED,
   which by the channel's status rule means no finding, no error or warning structural finding and no undecided
   outcome, and audit clearance AUDIT_PASSED). When no member is fully clean the earliest member is the representative
   and the group says so (``canonical_clean`` false); it is never presented as clean.
5. **Conflicts, disclosed.** Two or more groups are never reduced to one: every pair of groups is a conflict, its
   relation decided by the engine over the two representatives' formalized material claims (``contradiction``,
   ``consistent``, ``undecided``, or ``not_checked`` when either has none; at most :data:`MAX_CONFLICT_CHECKS` pairs are
   run). An excluded answer whose receipt names a contradiction (INT-CONFLICT-001) with a group member's report is a
   conflict too. Every conflict is ``OVS-CONS-002``.
6. **Status.** ``NO_DELIVERABLE_OUTPUT`` (every answer excluded), ``CONFLICTING`` (two or more groups, or a conflict:
   ``deliverable_message_id`` is null and the router discloses the groups), ``CONSOLIDATED`` (one group, its
   representative fully clean, nothing excluded, repeated or advisory) or ``CONSOLIDATED_WITH_FINDINGS`` (one group
   otherwise). Non-success is never shown as success.

The router delivers a consolidated answer only through :func:`delivery_decision`: the response must verify under the
consolidation key, its status must be deliverable, and the message must be its ``deliverable_message_id``; an excluded or
repeated answer is never delivered. :func:`check_consolidation` re-verifies a response and recomputes it from the journal
(``OVS-CONS-004`` when the signature fails or the recomputation differs: a tampered or stale consolidation).

Trust rule: the consolidation decides nothing about truth. Results prove properties of the encoding only; a group shows
that answers have the same recorded text, or the same material claims with the same figures, dates and quotations that
the engine finds mutually consistent, never that any answer is true. Overseer agents may review a consolidation
(advisory, informed dossiers only); their verdicts never change it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ..engine.provenance import sign_result
from ..engine.results import VerificationResult
from ..engine.sink import CapturedResult, capture_results
from ..engine.statuses import SCOPE_STATEMENT, VerificationStatus as S
from ..integrity.contracts import AgentMessage, AgentRole, IntegrityFinding, payload_hash, sign_message, verify_message
from ..integrity.cross_check import check_cross_report_consistency
from ..ir.canonical import canonical_json, problem_digest, sha256_hex
from ..ir.schema import Problem
from .checks import normalise
from .codes import is_agent_code, ovs_finding
from .contracts import JournalHead, OverseerAudit
from .faithful import faithful
from .keys import CONSOLIDATION_KEY_ID, RUN_KEY_ID, KeyRing
from .repeats import SIGNATURE_RULE, RepeatRecord, RepeatReport, content_form, detect_repeats, figures_of, quotations_of
from .store import ResultStore
from .view import RESPONSE_KINDS, OverseerView, Transfer

__all__ = [
    "CONSOLIDATED_CONTRACT", "CONSOLIDATED_CONTRACT_NAME", "CONSOLIDATOR_AGENT_ID", "CONSOLIDATION_RULES", "CONSOLIDATION_SCOPE_SENTENCE",
    "CONSOLIDATION_SCOPE_STATEMENT", "CONSOLIDATION_STATUSES", "DELIVERABLE_STATUSES", "MAX_CONFLICT_CHECKS", "ConsolidationStatus", "GroupBasis",
    "Relation", "EngineCheck", "ConsolidatedMember", "ConsolidatedGroup", "ExcludedOutput", "GroupConflict", "AdvisoryNote", "ConsolidatedResponse",
    "ConsolidationDecision", "consolidate", "sign_consolidated", "verify_consolidated", "consolidation_signable_text", "consolidation_envelope",
    "delivery_decision", "may_deliver", "check_consolidation", "consolidation_digest", "material_claims", "claims_key", "answer_facts", "select_requests",
]

CONSOLIDATED_CONTRACT = "consolidated_response/1.0"
CONSOLIDATED_CONTRACT_NAME = "consolidated_response"
#: The agent id a consolidated response travels under (the Overseer role; never an agent's).
CONSOLIDATOR_AGENT_ID = "overseer-consolidator"
#: The named rules a consolidation applies, recorded in every response.
CONSOLIDATION_RULES = ("fidelity-normalisation", "material-claim-key/2", SIGNATURE_RULE)
CONSOLIDATION_SCOPE_SENTENCE = (
    "This consolidation groups the recorded answers to one input by their normalised text and by their material claims, "
    "figures, dates and quotations as the engine checked their encodings. It does not show that any answer is true or that "
    "two answers mean the same beyond these rules."
)
CONSOLIDATION_SCOPE_STATEMENT = SCOPE_STATEMENT + " " + CONSOLIDATION_SCOPE_SENTENCE

ConsolidationStatus = Literal["CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS", "CONFLICTING", "NO_DELIVERABLE_OUTPUT"]
CONSOLIDATION_STATUSES: tuple[str, ...] = ("CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS", "CONFLICTING", "NO_DELIVERABLE_OUTPUT")
#: The only statuses whose representative the router may deliver.
DELIVERABLE_STATUSES = frozenset({"CONSOLIDATED", "CONSOLIDATED_WITH_FINDINGS"})
GroupBasis = Literal["single", "identical_text", "same_material_claims"]
Relation = Literal["contradiction", "consistent", "undecided", "not_checked"]
#: The most pairs of groups whose relation the engine decides in one consolidation (the rest are ``not_checked``).
MAX_CONFLICT_CHECKS = 64
_PASSED = frozenset({"AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"})
_FORMALIZED = frozenset({"TRANSLATED", "AMBIGUOUS_TRANSLATION"})
_SIGNATURE_FIELDS = ("signature", "signature_key_id")
_VOLATILE_FIELDS = ("consolidation_id", "created_at", "signature", "signature_key_id")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================================ the contract
_FROZEN = ConfigDict(extra="forbid", frozen=True)


class EngineCheck(BaseModel):
    """One engine run of the consolidation (an auditor run, signed under ``overseer-run``): a merge check of groups with
    the same material-claim key, or the relation of two groups. ``claims`` names the pooled claims as
    ``<message_id>#<claim_id>``."""
    model_config = _FROZEN
    purpose: Literal["merge", "conflict"]
    relation: Relation
    result_id: Optional[str] = None
    status: Optional[str] = None
    key_id: Optional[str] = None
    claims: list[str] = Field(default_factory=list)
    codes: list[str] = Field(default_factory=list, description="the INT codes the check raised (conflicts, glossary faults)")
    detail: str = ""


class ConsolidatedMember(BaseModel):
    """One answer in a group."""
    model_config = _FROZEN
    message_id: str
    receipt_id: Optional[str] = None
    agent_id: Optional[str] = None
    report_id: Optional[str] = None
    seq: int
    receipt_status: str
    clearance: str
    clean: bool = Field(description="status ACCEPTED and clearance AUDIT_PASSED: no finding of any severity")
    finding_codes: list[str] = Field(default_factory=list, description="the warning and info codes on its receipt and in the audit")
    text_sha256: str = Field(description="sha256 of its original_response under the fidelity normalisation")
    claims_key_sha256: Optional[str] = Field(default=None, description="digest of its material-claim key; null when it has no material claim")
    material_claims: int = 0


class ConsolidatedGroup(BaseModel):
    """Equivalent answers: which agents gave them, and the representative the router may deliver."""
    model_config = _FROZEN
    group_id: str
    basis: GroupBasis
    members: list[ConsolidatedMember]
    agent_ids: list[str]
    canonical_message_id: str
    canonical_agent_id: Optional[str] = None
    canonical_report_id: Optional[str] = None
    canonical_clean: bool
    canonical_basis: Literal["earliest_fully_clean", "earliest_with_findings"]
    merge_check: Optional[EngineCheck] = None


class ExcludedOutput(BaseModel):
    """An answer kept out of every group, with the codes and the signed results that exclude it."""
    model_config = _FROZEN
    message_id: str
    receipt_id: Optional[str] = None
    agent_id: Optional[str] = None
    report_id: Optional[str] = None
    seq: int
    receipt_status: Optional[str] = None
    clearance: Optional[str] = None
    codes: list[str] = Field(default_factory=list)
    result_ids: list[str] = Field(default_factory=list)
    repeated: bool = False
    repeat_signatures: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class GroupConflict(BaseModel):
    """Answers to the one input that cannot be reduced to one: disclosed, never resolved by choosing."""
    model_config = _FROZEN
    conflict_id: str
    group_ids: list[str]
    excluded_message_id: Optional[str] = None
    relation: Relation
    check: Optional[EngineCheck] = None
    channel_code: Optional[str] = None
    channel_result_id: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list)


class AdvisoryNote(BaseModel):
    """Groups the lexical rule calls the same that the engine did not confirm: kept apart (advisory, never merged)."""
    model_config = _FROZEN
    note_id: str
    group_ids: list[str]
    message_ids: list[str]
    reason: str


class ConsolidatedResponse(BaseModel):
    """``consolidated_response/1.0``: produced only by :func:`consolidate`, signed under the consolidation key. Frozen;
    any edit of a copy (``model_copy``, or a nested list changed in place) no longer verifies."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: Literal["consolidated_response/1.0"] = CONSOLIDATED_CONTRACT
    consolidation_id: str
    task_id: str
    request_id: str
    channel_uid: str
    user_input_sha256: str
    request_message_ids: list[str]
    status: ConsolidationStatus
    deliverable_message_id: Optional[str] = None
    answers: int = 0
    groups: list[ConsolidatedGroup] = Field(default_factory=list)
    excluded: list[ExcludedOutput] = Field(default_factory=list)
    conflicts: list[GroupConflict] = Field(default_factory=list)
    advisory: list[AdvisoryNote] = Field(default_factory=list)
    repeats: list[RepeatRecord] = Field(default_factory=list, description="repeated faults among these answers")
    repeat_counts: dict[str, int] = Field(default_factory=dict, description="repeated faults per agent in the whole task so far")
    findings: list[IntegrityFinding] = Field(default_factory=list)
    task_audit_id: str
    journal_head: Optional[JournalHead] = None
    engine_result_ids: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=lambda: list(CONSOLIDATION_RULES))
    scope_statement: str = CONSOLIDATION_SCOPE_STATEMENT
    created_at: str
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None

    def group(self, group_id: str) -> Optional[ConsolidatedGroup]:
        return next((g for g in self.groups if g.group_id == group_id), None)

    def group_of(self, message_id: str) -> Optional[ConsolidatedGroup]:
        return next((g for g in self.groups if any(m.message_id == message_id for m in g.members)), None)

    def excluded_message_ids(self) -> list[str]:
        return [e.message_id for e in self.excluded]


# ============================================================================================ signing
def consolidation_signable_text(resp: ConsolidatedResponse) -> str:
    data = resp.model_dump(mode="json", exclude_none=True)
    for f in _SIGNATURE_FIELDS:
        data.pop(f, None)
    return canonical_json(data)


def sign_consolidated(resp: ConsolidatedResponse, keyring: KeyRing) -> ConsolidatedResponse:
    """The response signed under the consolidation subkey (key id ``overseer-consolidation``)."""
    unsigned = resp.model_copy(update={"signature": None, "signature_key_id": None})
    mac = hmac.new(keyring.subkey("consolidation"), consolidation_signable_text(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    return unsigned.model_copy(update={"signature": mac, "signature_key_id": CONSOLIDATION_KEY_ID})


def verify_consolidated(resp: Any, keyring: KeyRing) -> bool:
    """True only when ``resp`` is a consolidated response signed under the consolidation key and unchanged since."""
    if not isinstance(resp, ConsolidatedResponse) or not resp.signature or resp.signature_key_id != CONSOLIDATION_KEY_ID:
        return False
    try:
        text = consolidation_signable_text(resp)
    except Exception:
        return False
    expected = hmac.new(keyring.subkey("consolidation"), text.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, resp.signature)


def consolidation_digest(resp: ConsolidatedResponse) -> str:
    return sha256_hex(consolidation_signable_text(resp))


def consolidation_envelope(resp: ConsolidatedResponse, keyring: KeyRing, *, recipient_role: AgentRole = AgentRole.ROUTER,
                           recipient_agent_id: Optional[str] = None, in_reply_to: Optional[str] = None) -> AgentMessage:
    """The response as a ``consolidated_response/1.0`` envelope from the Overseer role (agent id
    :data:`CONSOLIDATOR_AGENT_ID`), signed with ``sign_message`` under the consolidation key. ``ROLE_CONTRACTS`` lets no
    other role send this contract."""
    if not verify_consolidated(resp, keyring):
        raise ValueError("only a consolidated response signed under the consolidation key travels as consolidated_response/1.0")
    payload = json.loads(canonical_json(resp.model_dump(mode="json", exclude_none=True)))
    msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=resp.request_id or "unknown", task_id=resp.task_id or "unknown", sender_agent_id=CONSOLIDATOR_AGENT_ID,
                       sender_role=AgentRole.OVERSEER, recipient_role=recipient_role, recipient_agent_id=recipient_agent_id, contract=CONSOLIDATED_CONTRACT,
                       payload=payload, payload_sha256=payload_hash(payload), in_reply_to=in_reply_to,
                       created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    return sign_message(msg, keyring.subkey("consolidation"), CONSOLIDATION_KEY_ID)


def envelope_verifies(msg: Any, keyring: KeyRing) -> bool:
    """True when ``msg`` is a consolidated-response envelope signed under the consolidation key whose payload is a
    signed consolidated response."""
    if not isinstance(msg, AgentMessage) or msg.contract != CONSOLIDATED_CONTRACT or msg.sender_role is not AgentRole.OVERSEER:
        return False
    if msg.signature_key_id != CONSOLIDATION_KEY_ID or not verify_message(msg, keyring.subkey("consolidation")):
        return False
    try:
        resp = faithful(ConsolidatedResponse, msg.payload)
    except Exception:
        return False
    return verify_consolidated(resp, keyring)


# ============================================================================================ the router's decision
@dataclass(frozen=True)
class ConsolidationDecision:
    """Whether the router may deliver an answer through a consolidated response. ``allowed`` is the only field that
    permits anything."""
    allowed: bool
    reason: str
    status: Optional[str] = None
    message_id: Optional[str] = None


def delivery_decision(resp: Any, keyring: KeyRing, *, message_id: Optional[str] = None) -> ConsolidationDecision:
    """The router may deliver ``message_id`` (or, when None, the response's deliverable answer) only when the response
    verifies under the consolidation key, its status is CONSOLIDATED or CONSOLIDATED_WITH_FINDINGS, and the message is
    its deliverable answer. An excluded or repeated answer, a member that is not the representative, a CONFLICTING or
    NO_DELIVERABLE_OUTPUT response and an unsigned or edited response are never delivered. Never raises."""
    if not isinstance(resp, ConsolidatedResponse):
        return ConsolidationDecision(False, "not a consolidated response")
    try:
        signed = verify_consolidated(resp, keyring)
    except Exception:
        signed = False
    if not signed:
        return ConsolidationDecision(False, "the consolidated response does not verify under the consolidation key (unsigned or edited)", resp.status)
    if resp.status not in DELIVERABLE_STATUSES or not resp.deliverable_message_id:
        what = "the answers conflict and are disclosed, not chosen" if resp.status == "CONFLICTING" else "no answer may be delivered"
        return ConsolidationDecision(False, f"status {resp.status}: {what}", resp.status)
    target = message_id if message_id is not None else resp.deliverable_message_id
    if target != resp.deliverable_message_id:
        if any(e.message_id == target for e in resp.excluded):
            ex = next(e for e in resp.excluded if e.message_id == target)
            why = "it repeats a fault" if ex.repeated else f"it is excluded ({', '.join(ex.codes) or '; '.join(ex.reasons)})"
            return ConsolidationDecision(False, f"answer {target} is never delivered: {why}", resp.status, target)
        return ConsolidationDecision(False, f"answer {target} is not the consolidated response's deliverable answer", resp.status, target)
    return ConsolidationDecision(True, "ok", resp.status, target)


def may_deliver(resp: Any, keyring: KeyRing, *, message_id: Optional[str] = None) -> bool:
    return delivery_decision(resp, keyring, message_id=message_id).allowed


# ============================================================================================ claims and keys
def material_claims(report: Any) -> list[Any]:
    """The claims that carry the answer: materiality ``material`` and a role other than ``other`` (a note)."""
    if report is None:
        return []
    return [c for c in report.claims if c.materiality == "material" and c.claim_role != "other"]


def _claim_key(c: Any) -> list:
    return [content_form(c.claim_text), list(figures_of(c.claim_text)), list(quotations_of(c))]


def claims_key(report: Any) -> Optional[list]:
    """The material-claim key of an answer (rule ``material-claim-key/2``, with :func:`answer_facts`): the sorted keys of its material claims;
    None when it has none."""
    mats = material_claims(report)
    if not mats:
        return None
    return sorted((_claim_key(c) for c in mats), key=canonical_json)


def answer_facts(report: Any) -> tuple[str, ...]:
    """What the whole answer states beyond its material claims (rule ``material-claim-key/2``): the figures and dates of
    its ``original_response`` (``repeats.figures_of``, list numbering removed). Two answers whose material claims agree
    but whose supporting claims or unclaimed prose state another figure or date are never presented as one answer. (A
    quotation one answer adds as supporting evidence is not a difference: each quotation is checked against the
    supplied texts on its own receipt, and an altered one excludes its answer.)"""
    from .checks import strip_list_markers
    return figures_of(strip_list_markers(getattr(report, "original_response", "") or ""))


def _formalized(t: Transfer) -> list[tuple[str, Problem, bool]]:
    """``(label, problem, ambiguous)`` for every formalized material claim of an answer (from its journaled receipt)."""
    report = t.report
    if report is None or t.receipt is None:
        return []
    mats = {c.claim_id for c in material_claims(report)}
    out = []
    for o in t.receipt.outcomes:
        tr = o.translation
        if o.claim_id in mats and tr.problem is not None and getattr(tr.status, "value", tr.status) in _FORMALIZED:
            out.append((f"{t.message_id}#{o.claim_id}", tr.problem, getattr(tr.status, "value", tr.status) == "AMBIGUOUS_TRANSLATION"))
    return out


# ============================================================================================ engine runs
def _signed_run(fn: Callable[[], Any], *, view: OverseerView, keyring: KeyRing, store: ResultStore, seq: int) -> tuple[Any, list[str]]:
    """Run engine work UNSIGNED inside a capture, then sign every captured run under the auditor's run key and store it
    (origin ``auditor_run``), exactly as the auditor's own runs: an engine result and an Overseer run never confuse."""
    with capture_results() as cap:
        out = fn()
    ids: list[str] = []
    key = keyring.subkey("runs")
    for c in cap.items:
        try:
            res = faithful(VerificationResult, json.loads(c.result_json))
            signed = sign_result(res.model_copy(update={"signature": None, "signature_key_id": None}), key, RUN_KEY_ID)
            js = canonical_json(signed.model_dump(mode="json", exclude_none=True))
            store.put(CapturedResult(result_id=signed.result_id, key_id=RUN_KEY_ID, result_json=js, result_sha256=sha256_hex(js), problem_json=c.problem_json,
                                     problem_digest=c.problem_digest), channel_uid=view.channel_uid, task_id=view.task_id, request_id=view.request_id,
                      event_seq=seq, origin="auditor_run")
            ids.append(signed.result_id)
        except Exception:
            continue
    return out, ids


def _engine_check(purpose: str, items: list[tuple[str, Problem, bool]], *, view: OverseerView, keyring: KeyRing, store: ResultStore, seq: int,
                  run_ids: list[str]) -> EngineCheck:
    labels = [lab for lab, _p, _a in items]
    if not items:
        return EngineCheck(purpose=purpose, relation="not_checked", claims=[], detail="no formalized material claim to check")  # type: ignore[arg-type]
    renamed: list[Problem] = []
    assumed: set[str] = set()
    for i, (_lab, p, amb) in enumerate(items):
        cid = f"k{i + 1}"
        renamed.append(p.model_copy(update={"claim_id": cid}))
        if amb:
            assumed.add(cid)
    plan = view.plan_at(seq)
    request_id = (plan.request_id if plan is not None else None) or view.request_id or "unknown"
    cfg = view.config_at(seq)
    memo_key = "CONS|" + sha256_hex(canonical_json([[problem_digest(p) for p in renamed], cfg.model_dump(mode="json"), sorted(assumed), request_id]))
    memo = store.memo_get(memo_key)
    if memo is None:
        def run():
            return check_cross_report_consistency(renamed, request_id=request_id, config=cfg, signing_key=None, assumed_readings=frozenset(assumed))
        (res, findings), ids = _signed_run(run, view=view, keyring=keyring, store=store, seq=seq)
        memo = (res.result_id if res is not None else None, res.status.value if res is not None else None, sorted({f.code for f in findings}), ids)
        store.memo_put(memo_key, memo)
    result_id, status, codes, ids = memo
    for rid in ids:
        if rid not in run_ids:
            run_ids.append(rid)
    if status == S.CONSISTENT.value:
        relation, detail = "consistent", "the engine finds the pooled encodings jointly consistent"
    elif status == S.INCONSISTENT_PREMISES.value:
        relation, detail = "contradiction", "the engine finds the pooled encodings contradictory"
    elif status is None:
        relation, detail = "undecided", f"the joint problem could not be built ({', '.join(codes) or 'no detail'})"
    else:
        relation, detail = "undecided", f"the engine returned {status}"
    return EngineCheck(purpose=purpose, relation=relation, result_id=result_id, status=status, key_id=RUN_KEY_ID if result_id else None,  # type: ignore[arg-type]
                       claims=labels, codes=list(codes), detail=detail)


# ============================================================================================ selection
def select_requests(view: OverseerView, *, request_message_ids: Optional[Sequence[str]] = None, user_input_sha256: Optional[str] = None) -> tuple[str, list[Transfer]]:
    """The accepted requests carrying one input, and that input's digest. ``request_message_ids`` must name accepted
    requests of this channel carrying the same input; ``user_input_sha256`` selects every accepted request carrying it;
    with neither, the channel's accepted requests must all carry one input. ``ValueError`` otherwise."""
    accepted = [t for t in view.transfers if t.kind == "request" and t.status != "REJECTED" and t.request is not None and t.message_id]
    if request_message_ids is not None:
        ids = list(dict.fromkeys(request_message_ids))
        if not ids:
            raise ValueError("no request named")
        by_mid = {t.message_id: t for t in accepted}
        missing = [m for m in ids if m not in by_mid]
        if missing:
            raise ValueError(f"not accepted requests of this channel: {missing[:8]}")
        chosen = sorted((by_mid[m] for m in ids), key=lambda t: t.seq)
    elif user_input_sha256 is not None:
        chosen = [t for t in accepted if t.request.user_input_sha256 == user_input_sha256]
        if not chosen:
            raise ValueError("no accepted request of this channel carries that input")
    else:
        digests = sorted({t.request.user_input_sha256 for t in accepted})
        if not digests:
            raise ValueError("the channel has no accepted request: there is nothing to consolidate")
        if len(digests) > 1:
            raise ValueError(f"the channel's requests carry {len(digests)} different inputs: name the input (user_input_sha256) or the requests")
        chosen = accepted
    digests = {t.request.user_input_sha256 for t in chosen}
    if len(digests) != 1:
        raise ValueError("a consolidation is of answers to ONE input: the requests named carry different inputs")
    return next(iter(digests)), chosen


# ============================================================================================ the consolidation
def _audit_findings_for(audit: OverseerAudit, ids: set[str]) -> list[IntegrityFinding]:
    return [f for f in audit.report.findings if not is_agent_code(f.code) and set(f.message_ids) & ids]


def _result_ids(findings: Iterable[IntegrityFinding], t: Transfer) -> list[str]:
    out: list[str] = []
    for f in findings:
        out += [f.formal_result_id] if f.formal_result_id else []
        out += list(f.related_result_ids)
        if t.receipt is not None and f.claim_ids:
            named = set(f.claim_ids)
            out += [o.verification.result_id for o in t.receipt.outcomes if o.claim_id in named and o.verification is not None]
    return list(dict.fromkeys(r for r in out if r))


def _gid(prefix: str, parts: Any) -> str:
    return f"{prefix}-" + sha256_hex(canonical_json(parts))[:16]


@dataclass
class _Answer:
    t: Transfer
    state: str
    member: Optional[ConsolidatedMember] = None
    text_key: str = ""
    claims_key: Optional[str] = None
    formalized: tuple = ()
    facts: tuple = ()


def consolidate(view: OverseerView, *, keyring: KeyRing, store: ResultStore, audit: OverseerAudit, request_message_ids: Optional[Sequence[str]] = None,
                user_input_sha256: Optional[str] = None, prior_views: Sequence[OverseerView] = (), prior_audits: Optional[Mapping[str, OverseerAudit]] = None,
                repeats: Optional[RepeatReport] = None) -> ConsolidatedResponse:
    """The signed consolidated response to one input of the channel ``view`` reads (module docstring).

    ``audit`` is the channel's signed task audit (it must verify, belong to the channel and cover its transfers: an answer
    the audit does not cover is excluded, never passed). ``prior_views`` and ``prior_audits`` are earlier channels of the
    same task (a reopened task), whose answers count for repeated faults. ``repeats`` may be given when the caller already
    detected them over the same views and audits. ``ValueError`` when the inputs cannot be consolidated."""
    from .audit import verify_audit
    if view.degraded:
        raise ValueError("a consolidation reads only a journaled view; a degraded view has no reference copy")
    if not isinstance(audit, OverseerAudit) or audit.scope != "task" or audit.channel_uid != view.channel_uid:
        raise ValueError("a consolidation needs the channel's own task audit")
    if not verify_audit(audit, keyring):
        raise ValueError("the task audit does not verify under the audit key: nothing is consolidated on it")
    digest, requests = select_requests(view, request_message_ids=request_message_ids, user_input_sha256=user_input_sha256)
    req_ids = [t.message_id for t in requests]
    answers = [t for t in view.transfers if t.kind in RESPONSE_KINDS and t.message_id and t.in_reply_to in set(req_ids)]
    audits = {view.channel_uid: audit, **{k: v for k, v in (prior_audits or {}).items()}}
    if repeats is None:
        repeats = detect_repeats([*prior_views, view], audits, keyring=keyring)
    elif view.channel_uid not in repeats.channel_uids or repeats.task_id != view.task_id:
        raise ValueError("the repeat report does not cover this channel")
    last_seq = view.transfers[-1].seq if view.transfers else 0
    run_ids: list[str] = []
    findings: list[IntegrityFinding] = []
    excluded: list[ExcludedOutput] = []
    eligible: list[_Answer] = []
    for t in answers:
        state = audit.transfer_states.get(t.message_id or "", "")
        rec = t.receipt
        receipt_errors = [f for f in (rec.findings if rec is not None else []) if f.severity == "error"]
        own_ids = {t.message_id} | ({t.in_reply_to} if t.in_reply_to else set())
        audit_named = _audit_findings_for(audit, own_ids)
        audit_errors = [f for f in audit_named if f.severity == "error"]
        reps = repeats.for_message(t.message_id or "")
        reasons: list[str] = []
        if t.status == "REJECTED" or not t.delivered:
            reasons.append("not delivered: the channel REJECTED it")
        if t.withheld is not None or t.report is None:
            reasons.append("no delivered report: the text was withheld or its content is not retained")
        if receipt_errors:
            reasons.append("its receipt carries error-level findings")
        if audit_errors:
            reasons.append("the task audit names it in error-level findings")
        if state not in _PASSED:
            reasons.append(f"its clearance is {state or 'not covered by the task audit'}: not passed")
        if reps:
            reasons.append(f"it repeats {len(reps)} fault(s) of earlier answers (OVS-REP-001)")
        agent = t.sender_agent_id
        if reasons:
            codes = sorted({f.code for f in receipt_errors} | {f.code for f in audit_errors} | ({"OVS-REP-001"} if reps else set()))
            rids = _result_ids([*receipt_errors, *audit_errors], t)
            for r in reps:
                rids += [x for x in r.result_ids if x not in rids]
            ex = ExcludedOutput(message_id=t.message_id or "", receipt_id=t.receipt_id, agent_id=agent, report_id=t.report_id, seq=t.seq, receipt_status=t.status,
                                clearance=state or None, codes=codes, result_ids=rids, repeated=bool(reps), repeat_signatures=sorted({r.signature for r in reps}),
                                reasons=reasons)
            excluded.append(ex)
            findings.append(ovs_finding("OVS-CONS-001", f"answer {t.message_id} of agent {agent} is excluded from the consolidated response ({'; '.join(reasons)}; codes {codes})",
                                        message_ids=[t.message_id], agent_ids=[agent], report_ids=[t.report_id], related_result_ids=rids))
            continue
        report = t.report
        clean = t.status == "ACCEPTED" and state == "AUDIT_PASSED"
        codes = sorted({f.code for f in (rec.findings if rec is not None else [])} | {f.code for f in audit_named}
                       | {sf.code for sf in (rec.structural_findings if rec is not None else []) if sf.severity in ("error", "warning")})
        key = claims_key(report)
        key_digest = sha256_hex(canonical_json(key)) if key is not None else None
        text_key = sha256_hex(normalise(report.original_response))
        member = ConsolidatedMember(message_id=t.message_id or "", receipt_id=t.receipt_id, agent_id=agent, report_id=t.report_id, seq=t.seq,
                                    receipt_status=t.status or "", clearance=state, clean=clean, finding_codes=codes, text_sha256=text_key,
                                    claims_key_sha256=key_digest, material_claims=len(material_claims(report)))
        eligible.append(_Answer(t=t, state=state, member=member, text_key=text_key, claims_key=key_digest, formalized=tuple(_formalized(t)),
                                facts=answer_facts(report)))
    # ---------------------------------------------------------------- level 1: identical normalised text
    level1: list[list[_Answer]] = []
    by_text: dict[str, list[_Answer]] = {}
    for a in eligible:
        if a.text_key not in by_text:
            by_text[a.text_key] = []
            level1.append(by_text[a.text_key])
        by_text[a.text_key].append(a)
    # ---------------------------------------------------------------- level 2: the same material claims, engine-confirmed
    def l1_key(g: list[_Answer]) -> Optional[str]:
        keys = {a.claims_key for a in g}
        return next(iter(keys)) if len(keys) == 1 else None

    clusters: list[list[list[_Answer]]] = []
    by_key: dict[str, list[list[_Answer]]] = {}
    for g in level1:
        k = l1_key(g)
        if k is None:
            clusters.append([g])
            continue
        if k not in by_key:
            by_key[k] = []
            clusters.append(by_key[k])
        by_key[k].append(g)
    advisory: list[AdvisoryNote] = []
    final: list[tuple[list[_Answer], str, Optional[EngineCheck]]] = []
    # rule material-claim-key/2: groups with the same material claims whose whole answers state other figures, dates or
    # quotations (in a supporting claim, or in prose no claim carries) stay apart, and the difference is named
    split: list[list[list[_Answer]]] = []
    for cluster in clusters:
        parts: dict[tuple, list[list[_Answer]]] = {}
        for g in cluster:
            parts.setdefault(g[0].facts, []).append(g)
        if len(parts) > 1:
            figs = sorted({x for k in parts for x in k} - set.intersection(*(set(k) for k in parts)), key=lambda x: (len(x), x))
            mids = [a.t.message_id or "" for g in cluster for a in g]
            what = f"figures or dates {figs[:8]}"
            advisory.append(AdvisoryNote(note_id=_gid("adv", sorted(mids) + ["facts"]), group_ids=[], message_ids=mids,
                                         reason=f"same material claims under the lexical rule, kept apart: the answers state different {what}"))
            findings.append(ovs_finding("OVS-CONS-003", f"answers {mids[:8]} have the same material-claim key but state different {what}: kept apart (never presented as one answer)",
                                        message_ids=mids, agent_ids=[a.t.sender_agent_id for g in cluster for a in g]))
        split.extend(parts.values())
    clusters = split
    for cluster in clusters:
        if len(cluster) == 1:
            g = cluster[0]
            final.append((g, "single" if len(g) == 1 else "identical_text", None))
            continue
        items = [it for g in cluster for a in g for it in a.formalized]
        covered = all(any(a.formalized for a in g) for g in cluster)
        check = _engine_check("merge", items, view=view, keyring=keyring, store=store, seq=last_seq, run_ids=run_ids)
        if covered and check.relation == "consistent":
            merged = sorted((a for g in cluster for a in g), key=lambda a: a.t.seq)
            final.append((merged, "same_material_claims", check))
            continue
        for g in cluster:
            final.append((g, "single" if len(g) == 1 else "identical_text", None))
        if not covered:
            why = "at least one of them has no formalized material claim, so the engine could not check them all"
        else:
            why = f"the engine did not confirm them mutually consistent ({check.relation}: {check.detail})"
        mids = [a.t.message_id or "" for g in cluster for a in g]
        advisory.append(AdvisoryNote(note_id=_gid("adv", sorted(mids)), group_ids=[], message_ids=mids,
                                     reason=f"same material claims, figures, dates and quotations under the lexical rule, kept apart: {why}"))
        findings.append(ovs_finding("OVS-CONS-003", f"answers {mids[:8]} have the same material-claim key but are kept apart: {why} (advisory; never merged)",
                                    message_ids=mids, agent_ids=[a.t.sender_agent_id for g in cluster for a in g], formal_result_id=check.result_id))
    final.sort(key=lambda x: min(a.t.seq for a in x[0]))
    groups: list[ConsolidatedGroup] = []
    group_of_mid: dict[str, str] = {}
    canon: dict[str, _Answer] = {}
    for members, basis, check in final:
        members = sorted(members, key=lambda a: a.t.seq)
        gid = _gid("grp", sorted(a.t.message_id or "" for a in members))
        clean = [a for a in members if a.member is not None and a.member.clean]
        rep = clean[0] if clean else members[0]
        agents = list(dict.fromkeys(a.t.sender_agent_id for a in members if a.t.sender_agent_id))
        groups.append(ConsolidatedGroup(group_id=gid, basis=basis, members=[a.member for a in members if a.member is not None], agent_ids=agents,  # type: ignore[arg-type]
                                        canonical_message_id=rep.t.message_id or "", canonical_agent_id=rep.t.sender_agent_id, canonical_report_id=rep.t.report_id,
                                        canonical_clean=bool(clean), canonical_basis="earliest_fully_clean" if clean else "earliest_with_findings", merge_check=check))
        canon[gid] = rep
        for a in members:
            group_of_mid[a.t.message_id or ""] = gid
    # advisory notes name the groups their answers ended in
    advisory = [n.model_copy(update={"group_ids": list(dict.fromkeys(group_of_mid[m] for m in n.message_ids if m in group_of_mid))}) for n in advisory]
    # ---------------------------------------------------------------- conflicts, disclosed
    conflicts: list[GroupConflict] = []
    pairs = [(i, j) for i in range(len(groups)) for j in range(i + 1, len(groups))]
    for n, (i, j) in enumerate(pairs):
        gi, gj = groups[i], groups[j]
        if n < MAX_CONFLICT_CHECKS:
            a, b = canon[gi.group_id], canon[gj.group_id]
            if a.formalized and b.formalized:
                check = _engine_check("conflict", list(a.formalized) + list(b.formalized), view=view, keyring=keyring, store=store, seq=last_seq, run_ids=run_ids)
            else:
                check = EngineCheck(purpose="conflict", relation="not_checked", claims=[x[0] for x in (*a.formalized, *b.formalized)],
                                    detail="a representative has no formalized material claim")
        else:
            check = EngineCheck(purpose="conflict", relation="not_checked", detail=f"over the limit of {MAX_CONFLICT_CHECKS} engine-checked pairs")
        conflicts.append(GroupConflict(conflict_id=_gid("cfl", [gi.group_id, gj.group_id]), group_ids=[gi.group_id, gj.group_id], relation=check.relation, check=check))
    report_group = {m.report_id: g.group_id for g in groups for m in g.members if m.report_id}
    for ex in excluded:
        t = view.by_message.get(ex.message_id)
        if t is None or t.receipt is None:
            continue
        for f in t.receipt.findings:
            if f.code != "INT-CONFLICT-001":
                continue
            hit = sorted({report_group[r] for r in f.report_ids if r in report_group})
            if hit:
                conflicts.append(GroupConflict(conflict_id=_gid("cfl", [hit, ex.message_id, sorted(f.claim_ids)]), group_ids=hit, excluded_message_id=ex.message_id,
                                               relation="contradiction", channel_code=f.code, channel_result_id=f.formal_result_id, claim_ids=list(f.claim_ids)))
    for c in conflicts:
        mids = [canon[g].t.message_id for g in c.group_ids if g in canon] + ([c.excluded_message_id] if c.excluded_message_id else [])
        rid = c.check.result_id if c.check is not None else c.channel_result_id
        findings.append(ovs_finding("OVS-CONS-002", f"answers to one input conflict ({c.relation}; groups {c.group_ids}"
                                    + (f"; excluded answer {c.excluded_message_id} names {c.channel_code}" if c.excluded_message_id else "")
                                    + "): disclosed, none chosen", message_ids=mids, claim_ids=c.claim_ids, formal_result_id=rid))
    # ---------------------------------------------------------------- repeats and status
    answer_ids = {t.message_id for t in answers}
    reps = [r for r in repeats.repeats if r.message_id in answer_ids]
    findings += [f for f in repeats.findings if f.message_ids and f.message_ids[0] in answer_ids]
    if not groups:
        status: str = "NO_DELIVERABLE_OUTPUT"
    elif len(groups) > 1 or conflicts:
        status = "CONFLICTING"
    elif groups[0].canonical_clean and not excluded and not advisory and not reps:
        status = "CONSOLIDATED"
    else:
        status = "CONSOLIDATED_WITH_FINDINGS"
    deliverable = groups[0].canonical_message_id if status in DELIVERABLE_STATUSES else None
    head = view.journal.head() if view.journal is not None else None
    plan = view.plan
    resp = ConsolidatedResponse(consolidation_id=uuid.uuid4().hex, task_id=view.task_id, request_id=(plan.request_id if plan is not None else None) or view.request_id or "",
                                channel_uid=view.channel_uid, user_input_sha256=digest, request_message_ids=req_ids, status=status,  # type: ignore[arg-type]
                                deliverable_message_id=deliverable, answers=len(answers), groups=groups, excluded=excluded, conflicts=conflicts, advisory=advisory,
                                repeats=reps, repeat_counts=dict(repeats.counts), findings=findings, task_audit_id=audit.audit_id,
                                journal_head=JournalHead(index=head[0], entry_hash=head[1]) if head is not None else None, engine_result_ids=run_ids, created_at=_now())
    return sign_consolidated(resp, keyring)


# ============================================================================================ re-checking a response
def _comparable(resp: ConsolidatedResponse) -> dict:
    data = resp.model_dump(mode="json", exclude_none=True)
    for f in _VOLATILE_FIELDS:
        data.pop(f, None)
    return data


def check_consolidation(resp: Any, view: OverseerView, *, keyring: KeyRing, store: ResultStore, audit: OverseerAudit, prior_views: Sequence[OverseerView] = (),
                        prior_audits: Optional[Mapping[str, OverseerAudit]] = None) -> list[IntegrityFinding]:
    """``OVS-CONS-004`` findings for a consolidated response that does not verify under the consolidation key, or that a
    recomputation from the journal (the same requests, the same task audit) does not reproduce (the differing fields are
    named). An empty list means the response is the infrastructure's own and current. Never raises."""
    if not isinstance(resp, ConsolidatedResponse):
        return [ovs_finding("OVS-CONS-004", "not a consolidated response")]
    ids = dict(message_ids=[resp.deliverable_message_id] if resp.deliverable_message_id else [])
    if not verify_consolidated(resp, keyring):
        return [ovs_finding("OVS-CONS-004", f"consolidated response {resp.consolidation_id} does not verify under the consolidation key: unsigned or edited after issue", **ids)]
    if resp.channel_uid != view.channel_uid or resp.task_audit_id != getattr(audit, "audit_id", None):
        return [ovs_finding("OVS-CONS-004", f"consolidated response {resp.consolidation_id} belongs to another channel or task audit than the one given", **ids)]
    try:
        again = consolidate(view, keyring=keyring, store=store, audit=audit, request_message_ids=resp.request_message_ids, prior_views=prior_views,
                            prior_audits=prior_audits)
    except Exception as exc:
        return [ovs_finding("OVS-CONS-004", f"consolidated response {resp.consolidation_id} cannot be recomputed from the journal ({type(exc).__name__})", **ids)]
    a, b = _comparable(resp), _comparable(again)
    differ = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    if differ:
        return [ovs_finding("OVS-CONS-004", f"consolidated response {resp.consolidation_id} is not reproduced by a recomputation from the journal (fields {differ} differ): "
                            "stale or produced otherwise", **ids)]
    return []
