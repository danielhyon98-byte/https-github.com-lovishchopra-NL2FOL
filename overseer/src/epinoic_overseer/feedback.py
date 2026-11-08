"""Specialist feedback and revision, the overseer's side (design section 53).

The overseer gives the specialist that wrote an answer feedback on the flaws its checks discovered, and checks the
revision like any answer. Only the infrastructure writes feedback, and it writes it as data: :func:`build_revision_request`
reads the journal (an :class:`~epinoic_overseer.view.OverseerView`), the answer's journaled receipt, a signed task audit
that verifies and covers the answer, and the hub's own signed verdicts audits; it keeps only the allowlisted findings
(``channel.feedback.FEEDBACK_RULES``, ``feedback-rules/1``), renders each instruction from its code-owned template, signs
every flaw with the fault-signature rule (``repeats.occurrence_of``, ``fault-signature/1``) and the block under the
overseer ``feedback`` subkey (key id ``overseer-feedback``). The router names an answer and supplies no text; overseer
agents never write feedback (their verdicts stay advisory: an unresolved accusation of three kinds may appear, marked
advisory, in fixed text, never counted and never enough for a request on its own; a confirmed one acts only through the
auditor's own OVS-FID finding).

Bounded: at most ``WorkPlan.budgets['revision_rounds']`` rounds per answer's chain (default 2, hard maximum 3, 0
disables), one open revision request per answer, at most 12 flaws. A signature is fed back at most once; a fed-back fault
that comes back, a spent budget with flaws left, or a revision that was not delivered ESCALATES the chain
(:class:`RevisionEscalation`, OVS-FB-002, signed, for human review): nothing more is sent on it.

:func:`revision_outcome` classifies each fed-back flaw from the revision's receipt and a fresh task audit, never from the
specialist's words: ``fixed`` (its check ran again, the claim is still there and the flaw is gone), ``removed`` (the
claims it named are gone; allowed only where its rule says removal is the fix), ``evaded`` (gone because the statement was
weakened or changed: the revision's INT-REV-002 names it), ``persisted`` (the same signature, or the same code on the matched
claim) and ``not_rechecked`` (the revision was REJECTED, or its check could not run); it lists the flaws introduced, the
preservation findings and the claims lost, and decides the next step (``done``, ``revise_again``, ``escalated``).

:func:`check_revision_request` is the audit's ``feedback`` stage (OVS-FB-001). Advisory items rest on the block's
signature only (the auditor holds no verdicts audit): a stated limit. Feedback never changes a receipt, a signed result,
a status, a clearance or an audit; every block and record carries the scope statement.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from epinoic_logic.api.channel import (
    FEEDBACK_KEY_ID as _CHANNEL_FEEDBACK_KEY_ID, FEEDBACK_RULES, MAX_ADVISORY, MAX_FLAW_CLAIMS, MAX_FLAWS, MAX_MESSAGE_CHARS, MAX_QUOTED_TOTAL,
    REVISION_RULES, REVISION_SCOPE, RevisionClaim, RevisionFlaw, RevisionRequest, advisory_candidate, eligible_flaws, finding_digest, keep_list,
    match_claims, named_claim_ids, quote_text, render_instruction, render_revision_message, rendered_digest, revision_budget, revision_id_of,
    revision_signable_text, weakened, carries_quotation,
)
from epinoic_logic.api.integrity import IntegrityFinding
from epinoic_logic.api.ir import canonical_json, sha256_hex
from .codes import ovs_finding
from .keys import FEEDBACK_KEY_ID, KeyRing
from .repeats import content_form, fault_signature, figures_of, occurrence_of
from .view import RESPONSE_KINDS, OverseerView, Transfer

__all__ = [
    "RevisionIssueRecord", "FlawOutcome", "IntroducedFlaw", "RevisionOutcome", "RevisionEscalation", "BuildResult", "sign_revision", "verify_revision",
    "sign_record", "verify_record", "revision_chain", "advisory_items", "flaw_candidates", "build_revision_request", "revision_outcome",
    "escalation_for", "check_revision_request", "OUTCOME_CONTRACT", "ESCALATION_CONTRACT", "ISSUE_CONTRACT", "ESCALATION_REASONS",
]

assert FEEDBACK_KEY_ID == _CHANNEL_FEEDBACK_KEY_ID, "the channel and the overseer name the feedback key alike"

ISSUE_CONTRACT = "revision_issue/1.0"
OUTCOME_CONTRACT = "revision_outcome/1.0"
ESCALATION_CONTRACT = "revision_escalation/1.0"
ESCALATION_REASONS = ("budget_exhausted", "repeated_after_feedback", "revision_not_delivered")
_FROZEN = ConfigDict(extra="forbid", frozen=True)
_AGENT_KIND_RE = re.compile(r"^accusation #\d+ \(([a-z_]+)\)")
#: The quotation rules: a flaw of one whose claim is kept with no quotation at all was removed, not fixed.
_QUOTE_RULES = frozenset({"src.quote_not_found", "src.quote_form", "src.colleague_words"})
#: Preservation reasons that mean a statement was weakened or changed (a flaw that disappears with them is evaded).
_WEAKENING = ("is no longer stated", "is made approximate", "is turned into a range", "certainty of claims", "turned into an assertion")


# ============================================================================================ signing
def sign_revision(block: RevisionRequest, keyring: KeyRing) -> RevisionRequest:
    """``block`` signed under the overseer feedback subkey (HMAC-SHA256 over the canonical block without its signature fields)."""
    unsigned = block.model_copy(update={"signature": None, "signature_key_id": None})
    return unsigned.model_copy(update={"signature": keyring.mac("feedback", revision_signable_text(unsigned)), "signature_key_id": FEEDBACK_KEY_ID})


def verify_revision(block: Any, keyring: KeyRing) -> bool:
    """Whether ``block`` is a revision block signed under the overseer feedback subkey, unchanged since."""
    if not isinstance(block, RevisionRequest) or block.signature_key_id != FEEDBACK_KEY_ID or not block.signature:
        return False
    return keyring.mac_ok("feedback", revision_signable_text(block), block.signature)


def _record_text(record: BaseModel) -> str:
    data = record.model_dump(mode="json", exclude_none=True)
    for k in ("signature", "signature_key_id"):
        data.pop(k, None)
    return canonical_json(data)


def sign_record(record: BaseModel, keyring: KeyRing) -> Any:
    """A ledger record (issue, outcome, escalation) signed under the feedback subkey."""
    unsigned = record.model_copy(update={"signature": None, "signature_key_id": None})
    return unsigned.model_copy(update={"signature": keyring.mac("feedback", _record_text(unsigned)), "signature_key_id": FEEDBACK_KEY_ID})


def verify_record(record: Any, keyring: KeyRing) -> bool:
    if not isinstance(record, BaseModel) or getattr(record, "signature_key_id", None) != FEEDBACK_KEY_ID or not getattr(record, "signature", None):
        return False
    return keyring.mac_ok("feedback", _record_text(record), record.signature)


# ============================================================================================ ledger records
class RevisionIssueRecord(BaseModel):
    """An issued revision request, as the hub's revision ledger keeps it."""
    model_config = _FROZEN
    contract: Literal["revision_issue/1.0"] = ISSUE_CONTRACT
    revision_id: str
    task_id: str
    channel_uid: str
    agent_id: str
    request_message_id: str
    revises_message_id: str
    original_request_message_id: str
    round: int
    max_rounds: int
    flaw_signatures: list[str] = Field(default_factory=list)
    flaw_codes: list[str] = Field(default_factory=list)
    advisory: int = 0
    rendered_sha256: str
    receipt_status: str
    task_audit_id: str
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None


class FlawOutcome(BaseModel):
    """What became of one fed-back flaw in the revision."""
    model_config = _FROZEN
    flaw_id: str
    code: str
    rule: str
    severity: str
    basis: str
    signature: str
    bucket: Literal["fixed", "removed", "evaded", "persisted", "not_rechecked"]
    removal_ok: bool
    removal_allowed: Optional[bool] = None
    claim_ids: list[str] = Field(default_factory=list)
    matched_claim_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class IntroducedFlaw(BaseModel):
    """An allowlisted flaw of the revision that the answer it revises did not carry."""
    model_config = _FROZEN
    code: str
    rule: str
    severity: str
    signature: str
    claim_ids: list[str] = Field(default_factory=list)


class RevisionOutcome(BaseModel):
    """The signed outcome of one revision (``revision_outcome/1.0``). Decided from the revision's receipt, the fresh task
    audit and the repeat report, never from the specialist's words; it changes no receipt, status or clearance."""
    model_config = _FROZEN
    contract: Literal["revision_outcome/1.0"] = OUTCOME_CONTRACT
    outcome_id: str
    revision_id: str
    task_id: str
    channel_uid: str
    agent_id: str
    revision_request_message_id: str
    revises_message_id: str
    revised_message_id: str
    revised_report_id: Optional[str] = None
    receipt_status: Optional[str] = None
    round: int
    max_rounds: int
    flaws: list[FlawOutcome] = Field(default_factory=list)
    advisory: list[str] = Field(default_factory=list, description="flaw ids of advisory items: never counted")
    introduced: list[IntroducedFlaw] = Field(default_factory=list)
    preservation: list[str] = Field(default_factory=list, description="the revision's INT-REV-002 reasons, as its receipt states them")
    claims_lost: list[str] = Field(default_factory=list)
    repeat_signatures: list[str] = Field(default_factory=list)
    next: Literal["done", "revise_again", "escalated"]
    escalation_reason: Optional[str] = None
    task_audit_id: str
    scope_statement: str = REVISION_SCOPE
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None

    def counts(self) -> dict[str, int]:
        out = {b: 0 for b in ("fixed", "removed", "evaded", "persisted", "not_rechecked")}
        for f in self.flaws:
            out[f.bucket] += 1
        return out


class RevisionEscalation(BaseModel):
    """The signed escalation of a revision chain (``revision_escalation/1.0``, OVS-FB-002): final for the chain, for human
    review; the pool reviews the task with at least two overseer instances."""
    model_config = _FROZEN
    contract: Literal["revision_escalation/1.0"] = ESCALATION_CONTRACT
    escalation_id: str
    task_id: str
    channel_uid: str
    agent_id: str
    chain_message_ids: list[str] = Field(default_factory=list)
    rounds_used: int
    max_rounds: int
    remaining_signatures: list[str] = Field(default_factory=list)
    remaining_codes: list[str] = Field(default_factory=list)
    reason: Literal["budget_exhausted", "repeated_after_feedback", "revision_not_delivered"]
    finding: IntegrityFinding
    scope_statement: str = REVISION_SCOPE
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None


def _digest_id(prefix: str, record: BaseModel, id_field: str) -> str:
    data = record.model_dump(mode="json", exclude_none=True)
    for k in (id_field, "signature", "signature_key_id"):
        data.pop(k, None)
    return f"{prefix}-" + sha256_hex(canonical_json(data))[:24]


# ============================================================================================ the chain
def revision_chain(view: OverseerView, answer: Transfer) -> list[tuple[Transfer, RevisionRequest]]:
    """The revision requests of the chain ``answer`` belongs to, earliest first: ``(request transfer, block)`` for the
    request ``answer`` replies to when it carries a block, the request the answer it revises replied to, and so on."""
    out: list[tuple[Transfer, RevisionRequest]] = []
    seen: set[int] = set()
    t: Optional[Transfer] = answer
    while t is not None and t.seq not in seen:
        seen.add(t.seq)
        req = view.by_message.get(t.in_reply_to or "")
        block = req.request.revision if req is not None and req.request is not None else None
        if block is None:
            break
        out.append((req, block))
        t = view.by_message.get(block.revises_message_id)
    return list(reversed(out))


def _original_request(view: OverseerView, answer: Transfer, chain: Sequence[tuple[Transfer, RevisionRequest]]) -> Optional[Transfer]:
    mid = chain[0][1].original_request_message_id if chain else answer.in_reply_to
    t = view.by_message.get(mid or "")
    return t if t is not None and t.kind == "request" and t.request is not None and t.request.revision is None else None


# ============================================================================================ flaws
def _as_finding(c: Any) -> IntegrityFinding:
    f = c.finding
    if isinstance(f, IntegrityFinding):
        return f
    return IntegrityFinding(code=f.code, severity=f.severity, message=getattr(f, "message", "") or "", claim_ids=list(getattr(f, "claim_ids", []) or []))


def _signature(view: OverseerView, answer: Transfer, c: Any) -> str:
    """A flaw's fault signature (``fault-signature/1``): the repeat rule's occurrence of its finding; an advisory item is
    signed over its claims' content with its rule."""
    if c.basis == "advisory":
        report = answer.report
        texts = [x.claim_text for x in (report.claims if report is not None else []) if x.claim_id in set(c.claim_ids)]
        anchor = " | ".join(sorted({content_form(t) for t in texts}))
        return fault_signature(f"{c.code}/{c.rule}", "claim", anchor, figures_of(" ".join(texts)))
    return occurrence_of(view, answer, _as_finding(c), "audit" if c.source == "audit" else "receipt").signature


def advisory_items(verdicts_audits: Sequence[Any], keyring: KeyRing, answer: Transfer) -> list[Any]:
    """The advisory candidates of an answer: every OVS-AGENT-004 (an accusation neither confirmed nor refuted) of a
    VERIFIED verdicts-scope audit naming the answer, whose kind (read from the infrastructure's own ``accusation #n
    (kind)`` text, never from the agent's words) is quotation_absent, figure_changed or self_certification_as_content and
    which names the answer's claims; at most three, in a fixed order. Refuted, unverifiable and invalid accusations,
    translation_unfaithful and other never appear."""
    from .audit import verify_audit
    report = answer.report
    own = [c.claim_id for c in (report.claims if report is not None else [])]
    out: list[Any] = []
    for a in verdicts_audits:
        if getattr(a, "scope", None) != "verdicts" or not verify_audit(a, keyring):
            continue
        for f in a.report.findings:
            if f.code != "OVS-AGENT-004" or answer.message_id not in f.message_ids:
                continue
            m = _AGENT_KIND_RE.match(f.message or "")
            claims = [c for c in own if c in set(f.claim_ids)]
            cand = advisory_candidate(m.group(1), claims, f"{a.audit_id}#{finding_digest(f)}", f) if m else None
            if cand is not None:
                out.append(cand)
    out.sort(key=lambda c: c.sort_key())
    return out[:MAX_ADVISORY]


def flaw_candidates(view: OverseerView, answer: Transfer, original: Transfer, task_audit: Any, *, advisory: Sequence[Any] = ()) -> list[tuple[Any, str]]:
    """``(candidate, signature)`` of every allowlisted flaw of ``answer`` (``channel.feedback.eligible_flaws`` over its
    journaled receipt, the task audit's OVS-FID findings naming it, and ``advisory``)."""
    audit_findings = [f for f in task_audit.report.findings if answer.message_id in f.message_ids] if task_audit is not None else []
    cands = eligible_flaws(answer.receipt, answer.report, original.request, audit_findings=audit_findings,
                           audit_id=getattr(task_audit, "audit_id", None), advisory=advisory)
    return [(c, _signature(view, answer, c)) for c in cands]


# ============================================================================================ building a request
class BuildResult(BaseModel):
    """What :func:`build_revision_request` decided: a signed block, or why none (``reason``) and, for a chain that must
    end, the escalation reason."""
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    reason: str
    block: Optional[RevisionRequest] = None
    round: int = 0
    max_rounds: int = 0
    escalation_reason: Optional[str] = None
    remaining_signatures: list[str] = Field(default_factory=list)
    remaining_codes: list[str] = Field(default_factory=list)
    chain_message_ids: list[str] = Field(default_factory=list)
    original_request_message_id: Optional[str] = None


def _flaw(i: int, c: Any, sig: str, own: Mapping[str, Any], limit: int) -> RevisionFlaw:
    params = dict(c.params)
    claims = [RevisionClaim(claim_id=cid, text=quote_text(own[cid].claim_text, limit)) for cid in c.claim_ids[:MAX_FLAW_CLAIMS] if cid in own]
    return RevisionFlaw(flaw_id=f"f{i}", code=c.code, severity=c.severity, flaw_class=c.flaw_class, basis=c.basis, rule=c.rule, params=params,
                        instruction=render_instruction(c.rule, params), removal_ok=c.removal_ok, claims=claims, evidence=list(c.evidence), signature=sig)


def _assemble(selected: Sequence[tuple[Any, str]], *, own: Mapping[str, Any], base: dict, original: Any, report: Any, limits: Mapping[str, int]) -> RevisionRequest:
    flaws = [_flaw(i, c, sig, own, limits.get(sig, 600)) for i, (c, sig) in enumerate(selected, start=1)]
    named, fidelity = named_claim_ids(flaws)
    block = RevisionRequest(**base, flaws=flaws, must_not_change=keep_list(original, report, named, fidelity), rendered_sha256="0" * 64)
    return block.model_copy(update={"rendered_sha256": rendered_digest(block)})


def build_revision_request(view: OverseerView, answer_message_id: str, *, task_audit: Any, keyring: KeyRing, verdicts_audits: Sequence[Any] = (),
                           escalated: Sequence[str] = ()) -> BuildResult:
    """The signed revision request for the answer ``answer_message_id`` of the channel ``view`` reads, or why none
    (module docstring). ``task_audit`` is the signed task audit covering the answer; ``verdicts_audits`` the hub's copies
    of the signed verdicts audits of the channel; ``escalated`` the message ids of chains already escalated."""
    answer = view.by_message.get(answer_message_id)
    if answer is None or answer.kind not in RESPONSE_KINDS or answer.report is None or answer.receipt is None:
        return BuildResult(reason="not_an_answer")
    chain = revision_chain(view, answer)
    original = _original_request(view, answer, chain)
    if original is None:
        return BuildResult(reason="not_an_answer")
    chain_ids = [x for req, b in chain for x in (b.revises_message_id, req.message_id) if x] + [answer.message_id]
    ids = dict(chain_message_ids=chain_ids, original_request_message_id=original.message_id)
    plan = view.plan_at(answer.seq) or view.plan
    budget = chain[-1][1].max_rounds if chain else revision_budget(plan)
    rnd = len(chain) + 1
    if budget == 0:
        return BuildResult(reason="disabled", round=rnd, **ids)
    if set(chain_ids) & set(escalated):
        return BuildResult(reason="escalated", round=rnd, max_rounds=budget, **ids)
    if chain and (answer.status == "REJECTED" or not answer.delivered):
        return BuildResult(reason="revision_not_delivered", round=rnd, max_rounds=budget, escalation_reason="revision_not_delivered", **ids)
    advisory = advisory_items(verdicts_audits, keyring, answer)
    cands = flaw_candidates(view, answer, original, task_audit, advisory=advisory)
    returned = _returned(view, answer, chain, cands)
    returned_errors = [(c, s) for c, s in returned if c.severity == "error"]
    remaining = [(c, s) for c, s in cands if (c, s) not in returned]  # a fed-back flaw is never sent again
    actionable = [(c, s) for c, s in remaining if c.basis != "advisory"]
    left = sorted({s for _c, s in returned + actionable}), sorted({c.code for c, _s in returned + actionable})
    if returned_errors:
        return BuildResult(reason="repeated_after_feedback", round=rnd, max_rounds=budget, escalation_reason="repeated_after_feedback",
                           remaining_signatures=left[0], remaining_codes=left[1], **ids)
    if rnd > budget and (actionable or returned):
        return BuildResult(reason="budget_exhausted", round=rnd, max_rounds=budget, escalation_reason="budget_exhausted",
                           remaining_signatures=left[0], remaining_codes=left[1], **ids)
    if not actionable:
        return BuildResult(reason="no_actionable_flaw", round=rnd, max_rounds=budget, **ids)
    advisory_kept = [(c, s) for c, s in remaining if c.basis == "advisory"][:MAX_ADVISORY]
    selected = (actionable[:MAX_FLAWS] + advisory_kept)[:MAX_FLAWS]
    report = answer.report
    own = {c.claim_id: c for c in report.claims}
    base = dict(revision_id="rev-" + "0" * 24, task_id=original.request.task_id, request_id=original.request.request_id, plan_id=original.request.plan_id,
                to_agent_id=answer.sender_agent_id or report.agent_id, revises_message_id=answer.message_id, revises_report_id=report.report_id,
                revises_receipt_id=answer.receipt.receipt_id, original_request_message_id=original.message_id, round=rnd, max_rounds=budget,
                rules=list(REVISION_RULES), task_audit_id=task_audit.audit_id,
                verdicts_audit_ids=sorted({c.evidence[0].ref.split("#", 1)[0] for c, _s in advisory_kept})[:16], scope_statement=REVISION_SCOPE)
    limits: dict[str, int] = {}
    block = _assemble(selected, own=own, base=base, original=original.request, report=report, limits=limits)
    for _ in range(256):  # fit the bounds: cut the longest quotation by a quarter, then drop the last flaw (deterministic)
        quoted = sum(len(c.text) for f in block.flaws for c in f.claims)
        if len(render_revision_message(block)) <= MAX_MESSAGE_CHARS and quoted <= MAX_QUOTED_TOTAL:
            break
        longest = max(((len(c.text), f.signature) for f in block.flaws for c in f.claims if len(c.text) > 120), default=None)
        if longest is not None:
            limits[longest[1]] = max(120, (longest[0] * 3) // 4)
        elif sum(1 for c, _s in selected if c.basis != "advisory") > 1 or any(c.basis == "advisory" for c, _s in selected):
            selected = selected[:-1]
        else:
            break
        block = _assemble(selected, own=own, base=base, original=original.request, report=report, limits=limits)
    block = block.model_copy(update={"revision_id": revision_id_of(block)})
    return BuildResult(reason="issued", block=sign_revision(block, keyring), round=rnd, max_rounds=budget, **ids)


def _returned(view: OverseerView, answer: Transfer, chain: Sequence[tuple[Transfer, RevisionRequest]], cands: Sequence[tuple[Any, str]]) -> list[tuple[Any, str]]:
    """The candidates of a revision that carry again a flaw its chain fed back: a signature fed back in any round, or the
    same code on the claim that a flaw of the last round named, as matched in the revision (a reworded error persists)."""
    if not chain:
        return []
    fed = {f.signature for _req, b in chain for f in b.flaws if f.basis != "advisory"}
    last = chain[-1][1]
    prev = view.by_message.get(last.revises_message_id)
    match = match_claims(list(prev.report.claims), list(answer.report.claims)) if prev is not None and prev.report is not None else {}
    out: list[tuple[Any, str]] = []
    for c, s in cands:
        if c.basis == "advisory":
            continue
        if s in fed or any(c.code == f.code and (set(c.claim_ids) & {match.get(x.claim_id) for x in f.claims} if f.claims else _same_claimless(f, c))
                           for f in last.flaws if f.basis != "advisory"):
            out.append((c, s))
    return out


def issue_record(block: RevisionRequest, *, channel_uid: str, request_message_id: str, receipt_status: str, keyring: KeyRing) -> RevisionIssueRecord:
    rec = RevisionIssueRecord(revision_id=block.revision_id, task_id=block.task_id, channel_uid=channel_uid, agent_id=block.to_agent_id,
                              request_message_id=request_message_id, revises_message_id=block.revises_message_id,
                              original_request_message_id=block.original_request_message_id, round=block.round, max_rounds=block.max_rounds,
                              flaw_signatures=[f.signature for f in block.flaws], flaw_codes=[f.code for f in block.flaws],
                              advisory=sum(f.basis == "advisory" for f in block.flaws), rendered_sha256=block.rendered_sha256, receipt_status=receipt_status,
                              task_audit_id=block.task_audit_id)
    return sign_record(rec, keyring)


def escalation_for(*, task_id: str, channel_uid: str, agent_id: str, chain_message_ids: Sequence[str], rounds_used: int, max_rounds: int,
                   remaining_signatures: Sequence[str], remaining_codes: Sequence[str], reason: str, keyring: KeyRing) -> RevisionEscalation:
    """The signed escalation of a chain (OVS-FB-002, warning, outside the task audit)."""
    what = {"budget_exhausted": f"the budget of {max_rounds} revision round(s) is spent with flaws left",
            "repeated_after_feedback": "a fault fed back to the specialist came back in its revision",
            "revision_not_delivered": "the revision was not delivered (REJECTED)"}[reason]
    finding = ovs_finding("OVS-FB-002", f"revision chain of agent {agent_id} on task {task_id} escalated for human review: {what}; codes {sorted(set(remaining_codes))}; "
                          "nothing more is sent to the specialist on this chain, and the pool reviews the task with at least two overseer instances",
                          message_ids=list(chain_message_ids), agent_ids=[agent_id])
    rec = RevisionEscalation(escalation_id="esc-" + "0" * 24, task_id=task_id, channel_uid=channel_uid, agent_id=agent_id, chain_message_ids=list(chain_message_ids),
                             rounds_used=rounds_used, max_rounds=max_rounds, remaining_signatures=sorted(set(remaining_signatures)),
                             remaining_codes=sorted(set(remaining_codes)), reason=reason, finding=finding)  # type: ignore[arg-type]
    rec = rec.model_copy(update={"escalation_id": _digest_id("esc", rec, "escalation_id")})
    return sign_record(rec, keyring)


# ============================================================================================ the outcome of a revision
def _bucket_reason(bucket: str) -> str:
    return {"fixed": "its check ran again on the revision, the claims it named are still there, and the flaw is gone",
            "removed": "the claims it named are gone from the revision", "evaded": "it is gone, but the revision weakened or changed the statement (INT-REV-002)",
            "persisted": "the revision carries it again (the same signature, or the same code on the matched claim)",
            "not_rechecked": "the revision was not delivered, or its check could not run"}[bucket]


def _same_claimless(f: RevisionFlaw, c: Any) -> bool:
    """Whether the revision's candidate ``c`` is the claimless flaw ``f`` again: the same code and rule, about the same item,
    limit or command term (a word count measured anew is the same flaw)."""
    params = dict(c.params)
    return c.code == f.code and c.rule == f.rule and all(params.get(k) == v for k, v in f.params.items() if k in ("item", "limit", "term"))


def revision_outcome(view: OverseerView, revised_message_id: str, *, task_audit: Any, keyring: KeyRing, repeats: Any = None) -> RevisionOutcome:
    """The signed outcome of the revision ``revised_message_id`` (module docstring). ``ValueError`` when it replies to no
    revision request of the channel."""
    revised = view.by_message.get(revised_message_id)
    if revised is None or revised.kind not in RESPONSE_KINDS:
        raise ValueError("not an answer of this channel")
    req = view.by_message.get(revised.in_reply_to or "")
    block = req.request.revision if req is not None and req.request is not None else None
    if block is None:
        raise ValueError("the answer replies to no revision request: it is no revision")
    answer = view.by_message.get(block.revises_message_id)
    chain = revision_chain(view, revised)
    original = _original_request(view, revised, chain)
    fed = [f for f in block.flaws if f.basis != "advisory"]
    advisory = [f.flaw_id for f in block.flaws if f.basis == "advisory"]
    base = dict(outcome_id="out-" + "0" * 24, revision_id=block.revision_id, task_id=block.task_id, channel_uid=view.channel_uid, agent_id=block.to_agent_id,
                revision_request_message_id=req.message_id, revises_message_id=block.revises_message_id, revised_message_id=revised_message_id,
                revised_report_id=revised.report_id, receipt_status=revised.status, round=block.round, max_rounds=block.max_rounds,
                advisory=advisory, task_audit_id=getattr(task_audit, "audit_id", "none"))
    delivered = revised.status != "REJECTED" and revised.delivered and revised.report is not None and revised.receipt is not None
    if not delivered or original is None or answer is None or answer.report is None:
        flaws = [FlawOutcome(flaw_id=f.flaw_id, code=f.code, rule=f.rule, severity=f.severity, basis=f.basis, signature=f.signature, bucket="not_rechecked",
                             removal_ok=f.removal_ok, claim_ids=[c.claim_id for c in f.claims], reason=_bucket_reason("not_rechecked")) for f in fed]
        out = RevisionOutcome(**base, flaws=flaws, next="escalated", escalation_reason="revision_not_delivered")
        return sign_record(out.model_copy(update={"outcome_id": _digest_id("out", out, "outcome_id")}), keyring)
    new = flaw_candidates(view, revised, original, task_audit)
    new = [(c, s) for c, s in new if c.basis != "advisory"]
    new_sigs = {s for _c, s in new}
    old_report, new_report = answer.report, revised.report
    match = match_claims(list(old_report.claims), list(new_report.claims))
    rc = revised.receipt
    preservation = [(f.message, set(f.claim_ids)) for f in rc.findings if f.code == "INT-REV-002"]
    weakened_ids = {cid for msg, ids in preservation if any(w in msg for w in _WEAKENING) for cid in ids}
    internal = any(f.code == "INT-INTERNAL-001" for f in rc.findings)
    state = getattr(task_audit, "transfer_states", {}).get(revised_message_id, "") if task_audit is not None else ""
    outcomes: list[FlawOutcome] = []
    persisted_sigs: set[str] = set()
    for f in fed:
        claims = [c.claim_id for c in f.claims]
        matched = sorted({match[c] for c in claims if match.get(c)})
        same_code = [s for c, s in new if c.code == f.code and (set(c.claim_ids) & set(matched) if claims else _same_claimless(f, c))]
        removal_allowed = None
        old_by, new_by = {c.claim_id: c for c in old_report.claims}, {c.claim_id: c for c in new_report.claims}
        pairs = [(old_by[c], new_by[match[c]]) for c in claims if c in old_by and match.get(c) in new_by]
        unquoted = f.rule in _QUOTE_RULES and pairs and not any(carries_quotation(n) for _o, n in pairs)
        if (f.basis in ("channel", "engine") and internal) or (f.basis == "audit" and state in ("", "AUDIT_PENDING")):
            bucket = "not_rechecked"
        elif f.signature in new_sigs:
            bucket = "persisted"
        elif claims and not matched:
            bucket, removal_allowed = "removed", f.removal_ok
        elif same_code:
            bucket = "persisted"
        elif (set(claims) | set(matched)) & weakened_ids or any(weakened(o, n) for o, n in pairs):
            bucket = "evaded"
        elif unquoted:
            bucket, removal_allowed = "removed", f.removal_ok  # the quotation (the flagged content) is gone, the claim kept
        else:
            bucket = "fixed"
        if bucket == "persisted":
            persisted_sigs.update([f.signature, *same_code])
        outcomes.append(FlawOutcome(flaw_id=f.flaw_id, code=f.code, rule=f.rule, severity=f.severity, basis=f.basis, signature=f.signature, bucket=bucket,
                                    removal_ok=f.removal_ok, removal_allowed=removal_allowed, claim_ids=claims, matched_claim_ids=matched,
                                    reason=_bucket_reason(bucket)))
    old_sigs = {s for _c, s in flaw_candidates(view, answer, original, task_audit)}
    introduced = [IntroducedFlaw(code=c.code, rule=c.rule, severity=c.severity, signature=s, claim_ids=list(c.claim_ids))
                  for c, s in new if s not in old_sigs and s not in persisted_sigs]
    material_old = [c for c in old_report.claims if c.claim_role != "other"]
    lost = [c.claim_id for c in material_old if match.get(c.claim_id) is None]
    reps = [r.signature for r in (repeats.for_message(revised_message_id) if repeats is not None else [])]
    persisted = [o for o in outcomes if o.bucket == "persisted"]
    if [o for o in persisted if o.severity == "error"] or reps:
        nxt, why = "escalated", "repeated_after_feedback"  # a fed-back error came back: the chain ends at once
    elif (introduced or persisted) and block.round >= block.max_rounds:
        nxt, why = "escalated", "budget_exhausted"
    elif introduced:
        nxt, why = "revise_again", None  # only new flaws, within the budget
    else:
        nxt, why = "done", None  # nothing left to send: a persisted warning is never sent again
    out = RevisionOutcome(**base, flaws=outcomes, introduced=introduced, preservation=[m for m, _ids in preservation], claims_lost=lost,
                          repeat_signatures=sorted(set(reps)), next=nxt, escalation_reason=why)
    return sign_record(out.model_copy(update={"outcome_id": _digest_id("out", out, "outcome_id")}), keyring)


# ============================================================================================ the audit's feedback stage (OVS-FB-001)
def check_revision_request(view: OverseerView, t: Transfer, keyring: KeyRing, task_audits: Sequence[Any] = ()) -> list[str]:
    """Why the revision request ``t`` does not verify or bind (OVS-FB-001); empty when it does. The block must verify under
    the feedback key; bind to the journaled answer it revises (its author, report, receipt, request and chain); carry the
    digest of the message it renders and the id of its own content; keep the keep list the channel's rule gives; and every
    flaw must be one the journal (the answer's journaled receipt) or the auditor's own signed task audit holds, signed by
    the fault-signature rule. Advisory items rest on the signature alone (the auditor holds no verdicts audit)."""
    from .audit import verify_audit
    req = t.request
    block = req.revision if req is not None else None
    if block is None:
        return []
    out: list[str] = []
    if not verify_revision(block, keyring):
        out.append("the block does not verify under the overseer feedback key")
    answer = view.by_message.get(block.revises_message_id)
    if answer is None or answer.kind not in RESPONSE_KINDS or answer.seq >= t.seq:
        return out + ["the block names no journaled answer issued before the request"]
    if t.in_reply_to != block.revises_message_id:
        out.append("the request does not reply to the answer its block revises")
    if req.to_agent_id != block.to_agent_id or answer.sender_agent_id != block.to_agent_id:
        out.append("the request is not addressed to the author of the answer its block revises")
    if answer.report_id != block.revises_report_id or answer.receipt_id != block.revises_receipt_id:
        out.append("the block names another report or receipt than the journaled answer's")
    chain = revision_chain(view, answer)
    original = _original_request(view, answer, chain)
    if original is None or original.message_id != block.original_request_message_id or block.round != len(chain) + 1:
        out.append("the block's original request or round is not the journaled chain's")
    try:
        if rendered_digest(block) != block.rendered_sha256:
            out.append("the rendered digest is not the digest of the message the block renders")
        if revision_id_of(block) != block.revision_id:
            out.append("the revision id is not the digest of the block's content")
    except Exception as exc:
        out.append(f"the block cannot be rendered ({type(exc).__name__})")
    report = answer.report
    if report is None or answer.receipt is None or original is None:
        return out + ["the revised answer carries no journaled report or receipt"]
    if block.must_not_change != keep_list(original.request, report, *named_claim_ids(block)):
        out.append("the keep list is not the channel's keep list of the original request and the answer")
    audits = {a.audit_id: a for a in task_audits if getattr(a, "scope", None) == "task" and a.channel_uid == view.channel_uid and verify_audit(a, keyring)}
    audit = audits.get(block.task_audit_id)
    if audit is None:
        out.append("the block names no signed task audit of this channel the auditor issued")
    held = {(c.code, c.rule, c.params, c.claim_ids[:MAX_FLAW_CLAIMS], s) for c, s in flaw_candidates(view, answer, original, audit)} if audit is not None else set()
    for f in block.flaws:
        if f.basis == "advisory":
            continue  # advisory items rest on the block's signature (stated limit)
        key = (f.code, f.rule, tuple(sorted(f.params.items())), tuple(c.claim_id for c in f.claims), f.signature)
        if audit is not None and key not in held:
            out.append(f"flaw {f.flaw_id} ({f.code}) is no finding the journal or the auditor's own signed task audit holds, signed by the fault-signature rule")
        if f.rule not in FEEDBACK_RULES:
            out.append(f"flaw {f.flaw_id} names a rule outside the allowlist")
    return out
