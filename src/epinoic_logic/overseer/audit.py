"""The transfer audit: the deterministic part of the Overseer.

* :func:`run_overseer_checks` is the pure function: given a view of one channel (and, optionally, the live channel,
  the replays and re-derivations done so far) it runs the live checks L1-L6 over every transfer, R2, the replay
  findings, and the batch checks B1-B5, and returns an :class:`AuditResult` whose ``report`` is an
  ``IntegrityReport`` of ``OVS-*`` findings. It never raises: a check that fails internally is AUDIT-001 and no
  PASSED state is possible.
* :class:`TransferAuditor` wraps it for live use: it journals every event (``on_event``), stores every captured
  result, runs the live tier for that transfer before the hub returns, queues the asynchronous tier (R1 replay, R2
  re-derivation), computes and journals each transfer's :class:`~epinoic_logic.overseer.contracts.TransferClearance`,
  re-checks custody when the router asks (``clearance``), and issues signed task audits (``audit``).
* :func:`sign_audit` / :func:`verify_audit`: HMAC-SHA256 under the audit subkey over the canonical audit without its
  signature fields; :func:`audit_envelope` carries an audit through a ``MessageLog`` as ``overseer_audit/1.0`` from
  the Overseer role, agent id ``overseer-auditor``, signed with ``sign_message`` under the audit key.

Clearance (design section 7): AUDIT_FAILED when any error-level ``OVS-*`` finding names the transfer or a transfer it
depends on (``OVS-AGENT-*`` excluded); AUDIT_PENDING when there is no error and an always-replay result or the
re-derivation of the transfer is outstanding; AUDIT_PASSED_WITH_FINDINGS with only warnings or infos; AUDIT_PASSED
with none. Clearance vouches for the receipt, not for the content: a transfer the channel correctly REJECTED audits
PASSED. Non-success is never shown as success: a pending, failed or degraded audit is never presented as passed.

Deviations from the design text, listed as each stage requires:

* the journal records a late attachment (first observed event after 1) as its start, not as a gap;
* sticky live findings: a custody or receipt fault seen at any clearance stays in later audits even if the live object
  was put back;
* INT-HANDOFF-007 is excluded from B4 before a synthesis exists (see ``checks/divergence.py``);
* the shadow (B5) re-issues a parsed raw text as the delivered report (see ``checks/shadow.py``);
* L5 fidelity runs in the asynchronous tier for live transfers (the design's remedy for a missed synchronous budget:
  delivered reports with 100 KB receipts took up to 10 ms in L5 alone); the transfer is AUDIT_PENDING until it has run,
  and the batch tier runs it directly.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional

from ..channel.events import ChannelEvent
from ..engine.results import VerificationResult
from ..engine.statuses import VerificationStatus as S, is_definitive
from ..integrity.contracts import AgentMessage, AgentRole, IntegrityFinding, IntegrityReport, payload_hash, report_digest, sign_message, verify_report_digest
from ..ir.canonical import canonical_json, sha256_hex
from .checks import CheckContext, Rederived, Replay
from .checks import custody, fidelity, formal, joint, peer, receipts, results, synthesis, translation
from .checks.divergence import check_divergence
from .checks.shadow import run_shadow
from .codes import is_agent_code, ovs_finding
from .faithful import faithful
from .contracts import (
    AUDIT_SCOPE_STATEMENT, AUDITOR_VERSION, CLEARANCE_STATES, AuditCoverage, ClearanceState, Divergence, JournalHead, OverseerAudit, TransferClearance,
    TranslationAudit,
)
from .journal import ChannelJournal, JournalSealed, JournalSet
from .keys import AUDIT_KEY_ID, RUN_KEY_ID, KeyRing
from .replay import Replayer, ReplayJob, classify as classify_replay, compare as compare_replay
from .store import ResultStore
from .view import OverseerView, Transfer, cited_results

__all__ = [
    "run_overseer_checks", "AuditResult", "TransferAuditor", "sign_audit", "verify_audit", "audit_envelope", "audit_signable_text",
    "transfer_states", "ALWAYS_REPLAY_CODES", "AUDITOR_AGENT_ID", "AUDIT_CONTRACT",
]

AUDITOR_AGENT_ID = "overseer-auditor"
AUDIT_CONTRACT = "overseer_audit/1.0"
#: Error findings whose results are never sampled out of live replay.
ALWAYS_REPLAY_CODES = frozenset({"INT-CONFLICT-001", "INT-CONFLICT-005", "INT-SUBJ-001", "INT-REQ-005", "INT-REQ-007"})
_SIGNATURE_FIELDS = ("signature", "signature_key_id")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================================ signing
def audit_signable_text(audit: OverseerAudit) -> str:
    data = audit.model_dump(mode="json", exclude_none=True)
    for f in _SIGNATURE_FIELDS:
        data.pop(f, None)
    return canonical_json(data)


def sign_audit(audit: OverseerAudit, keyring: KeyRing) -> OverseerAudit:
    """The audit signed under the audit subkey (key id ``overseer-audit``); the report digest is set first."""
    rep = audit.report.model_copy(deep=True)
    rep.report_sha256 = report_digest(rep)
    unsigned = audit.model_copy(update={"report": rep, "signature": None, "signature_key_id": None})
    mac = hmac.new(keyring.subkey("audit"), audit_signable_text(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    return unsigned.model_copy(update={"signature": mac, "signature_key_id": AUDIT_KEY_ID})


def verify_audit(audit: OverseerAudit, keyring: KeyRing) -> bool:
    """True only when the audit is signed under the audit key, unchanged since, and its report digest holds."""
    if not audit.signature or audit.signature_key_id != AUDIT_KEY_ID:
        return False
    expected = hmac.new(keyring.subkey("audit"), audit_signable_text(audit).encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, audit.signature) and verify_report_digest(audit.report)


def audit_envelope(audit: OverseerAudit, keyring: KeyRing, *, recipient_role: AgentRole = AgentRole.ROUTER, recipient_agent_id: Optional[str] = None,
                   in_reply_to: Optional[str] = None) -> AgentMessage:
    """The audit as an ``overseer_audit/1.0`` envelope from the Overseer, signed with ``sign_message`` under the audit key."""
    payload = json.loads(canonical_json(audit.model_dump(mode="json", exclude_none=True)))
    msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=audit.request_id or "unknown", task_id=audit.task_id or "unknown", sender_agent_id=AUDITOR_AGENT_ID,
                       sender_role=AgentRole.OVERSEER, recipient_role=recipient_role, recipient_agent_id=recipient_agent_id, contract=AUDIT_CONTRACT,
                       payload=payload, payload_sha256=payload_hash(payload), in_reply_to=in_reply_to,
                       created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    return sign_message(msg, keyring.subkey("audit"), AUDIT_KEY_ID)


# ============================================================================================ the pure function
@dataclass
class AuditResult:
    report: IntegrityReport
    coverage: AuditCoverage
    divergences: list[Divergence]
    findings: list[tuple[int, IntegrityFinding]]
    transfer_states: dict[str, ClearanceState]
    task_state: ClearanceState
    auditor_result_ids: list[str]
    cited_result_ids: list[str]
    translations: list[TranslationAudit] = field(default_factory=list)


def _sort_key(item: tuple[int, IntegrityFinding]) -> tuple:
    seq, f = item
    return (seq, f.code, tuple(sorted(f.message_ids)), tuple(sorted(f.claim_ids)), tuple(sorted(f.report_ids)), f.message)


def _dedupe(findings: Iterable[tuple[int, IntegrityFinding]]) -> list[tuple[int, IntegrityFinding]]:
    out: dict[tuple, tuple[int, IntegrityFinding]] = {}
    for seq, f in findings:
        key = (seq, f.code, f.message, tuple(f.message_ids), tuple(f.claim_ids), tuple(f.report_ids), f.formal_result_id)
        out.setdefault(key, (seq, f))
    return sorted(out.values(), key=_sort_key)


def _dependency_ids(view: OverseerView, t: Transfer) -> set[str]:
    ids = {t.message_id} if t.message_id else set()
    for s in t.depends_on:
        d = view.by_seq.get(s)
        if d is not None and d.message_id:
            ids.add(d.message_id)
    return ids


def transfer_states(view: OverseerView, findings: list[tuple[int, IntegrityFinding]], pending: Optional[dict[str, set[str]]] = None) -> tuple[dict[str, ClearanceState], ClearanceState]:
    """Per-transfer clearance states and the task state. ``OVS-AGENT-*`` findings never change a clearance."""
    pending = pending or {}
    relevant = [(s, f) for s, f in findings if not is_agent_code(f.code)]
    task_level_failure = any(f.severity == "error" for _s, f in relevant)  # any error fails the task, named transfer or not
    internal_unnamed = any(f.code == "OVS-AUDIT-001" and not f.message_ids for _s, f in relevant)
    chain_break_seq = min((s for s, f in relevant if f.code == "OVS-CUST-005"), default=None)
    states: dict[str, ClearanceState] = {}
    for t in view.transfers:
        if not t.message_id:
            continue
        names = _dependency_ids(view, t)
        mine = [f for _s, f in relevant if set(f.message_ids) & names]
        if internal_unnamed or any(f.severity == "error" for f in mine) or (chain_break_seq is not None and t.seq >= chain_break_seq):
            states[t.message_id] = "AUDIT_FAILED"
        elif pending.get(t.message_id):
            states[t.message_id] = "AUDIT_PENDING"
        elif mine:
            states[t.message_id] = "AUDIT_PASSED_WITH_FINDINGS"
        else:
            states[t.message_id] = "AUDIT_PASSED"
    if task_level_failure or "AUDIT_FAILED" in states.values():
        task: ClearanceState = "AUDIT_FAILED"
    elif any(pending.values()) or "AUDIT_PENDING" in states.values():
        task = "AUDIT_PENDING"
    elif relevant:
        task = "AUDIT_PASSED_WITH_FINDINGS"
    else:
        task = "AUDIT_PASSED"
    return states, task


def live_transfer_checks(ctx: CheckContext, t: Transfer, *, dependencies: bool = True, at_issue: bool = False) -> None:
    """L1-L6 for one transfer (and L1 custody of the transfers it depends on). ``at_issue``: the event was snapshotted a
    moment ago, so the transfer's own live envelope, typed copy and receipt are by construction the journaled ones and
    are not re-compared (its dependencies are; ``clearance`` and the batch tier compare everything)."""
    if t.receipt_error is not None:
        ctx.ovs(t.seq, "OVS-AUDIT-001", f"the journaled receipt of {t.kind} {t.message_id} could not be parsed against the receipt contract ({t.receipt_error}); "
                "the receipt checks did not run and the transfer cannot pass", **t.ids())
    if t.delivered and t.typed is None and t.withheld is None and t.payload is not None and not t.digest_only:
        ctx.ovs(t.seq, "OVS-AUDIT-001", f"the delivered payload of {t.kind} {t.message_id} could not be parsed against its contract ({t.typed_error}); "
                "the content checks did not run and the transfer cannot pass", **t.ids())
    ctx.guard("custody", "custody", lambda: (custody.check_issue_consistency(ctx, t), None if at_issue else custody.check_custody(ctx, t), custody.check_raw_text(ctx, t)), transfer=t)
    if dependencies:
        for s in t.depends_on:
            d = ctx.view.by_seq.get(s)
            if d is not None:
                ctx.guard("custody", "custody of a dependency", lambda d=d: custody.check_custody(ctx, d), transfer=d)
    ctx.guard("receipts", "receipts", lambda: (None if at_issue else receipts.check_receipt_custody(ctx, t), receipts.check_status(ctx, t), receipts.check_delivery(ctx, t),
                                               receipts.check_identifiers(ctx, t), receipts.check_summary(ctx, t)), transfer=t)
    ctx.guard("results", "results", lambda: (results.store_captured(ctx, t), results.check_results(ctx, t)), transfer=t)
    ctx.guard("formal", "formal status", lambda: formal.check_formal_status(ctx, t), transfer=t)
    if not at_issue:  # at issue, L5 and the translation checks run in the asynchronous tier (the transfer is PENDING until they have)
        ctx.guard("fidelity", "fidelity", lambda: fidelity.check_fidelity(ctx, t), transfer=t)
        run_translation_checks(ctx, t)
    ctx.guard("peer", "peer", lambda: (peer.check_forward(ctx, t), peer.check_peer_documents(ctx, t)), transfer=t)
    ctx.guard("synthesis", "synthesis citations", lambda: synthesis.check_synthesis_citations(ctx, t), transfer=t)
    ctx.guard("joint", "pool", lambda: joint.check_pool(ctx, t), transfer=t)


def run_translation_checks(ctx: CheckContext, t: Transfer) -> None:
    """Translator oversight (TRN-001..007) for one transfer; the records it returns are kept on the context."""
    records = ctx.guard("translation", "translation", lambda: translation.check_translations(ctx, t), transfer=t)
    for r in records or []:
        ctx.translations.append(r)


def translation_audits(records: Iterable[Any], findings: list[tuple[int, IntegrityFinding]]) -> list[TranslationAudit]:
    """The audit's record of every translation checked, with the ``OVS-*`` codes (agent codes excluded) that name the
    translation's claim on its transfer. One record per (event, outcome), in sequence order."""
    from ..translate.contracts import sha256_text
    seen: dict[tuple[int, int], Any] = {}
    for r in records:
        seen.setdefault((r.seq, r.outcome_index), r)
    out: list[TranslationAudit] = []
    for (_seq, _i), r in sorted(seen.items()):
        codes = sorted({f.code for _s, f in findings if not is_agent_code(f.code) and r.message_id in f.message_ids and r.claim_id in f.claim_ids})
        tr = r.translation
        flags = tr.interpretation.ambiguity_flags if tr.interpretation is not None else []
        out.append(TranslationAudit(
            seq=r.seq, message_id=r.message_id, receipt_id=r.receipt_id, report_id=r.report_id, agent_id=r.agent_id, claim_id=r.claim_id,
            outcome_index=r.outcome_index, claim_text=r.claim_text, claim_text_sha256=sha256_text(r.claim_text), cited_claim_ids=[c for c, _t in r.cited_claims],
            translation_id=tr.translation_id, translation_status=tr.status.value, eligibility_class=tr.eligibility.eligibility_class.value,
            eligible=tr.eligibility.eligible, model_proposed=r.model_proposed, provider_name=tr.provider.provider_name if tr.provider is not None else None,
            prompt_version=tr.provider.prompt_version if tr.provider is not None else None, translator_version=tr.translator_version,
            policy_version=tr.policy_version, problem_json=r.problem_json, problem_digest=r.problem_digest, ambiguity_flags=[f.code for f in flags],
            grounding_unverified=sorted({c.target_id for c in tr.grounding_checks if c.verified is False}), diagnostics=list(tr.diagnostics),
            revalidation=r.revalidation, revalidation_detail=list(r.revalidation_detail), result_id=r.result_id, result_status=r.result_status,
            result_sha256=r.result_sha256, signature_verified=r.signature_verified, display_status=r.display_status, checks_run=list(r.checks_run),
            outside_cited_claims=list(r.outside_cited_claims), codes=codes))
    return out


def replay_findings(ctx: CheckContext, replays: dict[str, Replay]) -> None:
    """RES-007 / RES-008 from replays; each names the transfers citing the result and cites the replay run."""
    for rid in sorted(replays):
        r = replays[rid]
        code = classify_replay(r)
        rec = ctx.store.get(rid)
        seq = getattr(rec, "event_seq", 0) or 0
        if r.replay_result_id and r.replay_result_id not in ctx.auditor_result_ids:
            ctx.auditor_result_ids.append(r.replay_result_id)
        if code is None:
            continue
        cites = ctx.store.citations(rid)
        mids = []
        for c in cites:
            t = ctx.view.by_seq.get(c.event_seq)
            if t is not None and t.message_id and t.message_id not in mids:
                mids.append(t.message_id)
        if not mids:
            t = ctx.view.by_seq.get(seq)
            if t is not None and t.message_id:
                mids.append(t.message_id)
        if code == "OVS-RES-007":
            why = []
            if not r.problem_digest_ok:
                why.append("another problem digest")
            if not r.config_digest_ok:
                why.append("another config digest")
            if r.replay_status != r.original_status:
                why.append(f"status {r.replay_status} where the signed result states {r.original_status}")
            msg = f"replay of result {rid} on a fresh engine gives {', '.join(why)}"
        else:
            why = "budget exceeded" if r.budget_exceeded else (r.error or ("component versions changed" if r.versions_changed else f"{r.original_status} vs replay {r.replay_status}"))
            msg = f"replay of result {rid} is inconclusive ({why}); not an accusation"
        ctx.ovs(seq, code, msg, message_ids=mids, formal_result_id=rid, related_result_ids=[r.replay_result_id] if r.replay_result_id else [])


def run_overseer_checks(view: OverseerView, *, keyring: KeyRing, store: ResultStore, live: Any = None, registry: Any = None,
                        replays: Optional[dict[str, Replay]] = None, rederived: Optional[dict[int, Rederived]] = None, presented: Optional[dict[str, Any]] = None,
                        batch: bool = True, shadow: bool = True, replay_mode: str = "none", pending: Optional[dict[str, set[str]]] = None,
                        extra_findings: Iterable[tuple[int, IntegrityFinding]] = (), sampled: tuple[int, int] = (0, 0)) -> AuditResult:
    """Run every check over ``view``; never raises."""
    ctx = CheckContext(view=view, keyring=keyring, store=store, live=live, registry=registry, presented=dict(presented or {}))
    ctx.coverage.replay_mode = replay_mode
    ctx.coverage.degraded = view.degraded
    try:
        _run_all(ctx, replays or {}, rederived, batch=batch, shadow=shadow)
    except Exception as exc:  # belt and braces: the guards should have caught it
        ctx.ovs(0, "OVS-AUDIT-001", f"the audit failed internally ({type(exc).__name__}: {str(exc)[:300]}); no PASSED state is possible")
    if sampled[1] and sampled[0] < sampled[1]:
        ctx.ovs(0, "OVS-AUDIT-003", f"live replay was sampled: {sampled[0]} of {sampled[1]} results replayed live; the batch tier replayed the rest")
    findings = _dedupe(list(ctx.findings) + list(extra_findings))
    states, task = transfer_states(view, findings, pending)
    plan = view.plan
    cited = sorted(ctx.cited_result_ids)
    formal_ids = list(dict.fromkeys(list(ctx.auditor_result_ids) + [f.formal_result_id for _s, f in findings if f.formal_result_id]
                                    + [r for _s, f in findings for r in f.related_result_ids] + cited))
    report = IntegrityReport(report_id=uuid.uuid4().hex, request_id=getattr(plan, "request_id", view.request_id) or view.request_id or "unknown",
                             task_id=getattr(plan, "task_id", view.task_id) or view.task_id or "unknown", checks_run=list(ctx.checks_run),
                             findings=[f for _s, f in findings], formal_result_ids=formal_ids, created_at=_now())
    report.report_sha256 = report_digest(report)
    cov = ctx.coverage
    cov.transfers = len(view.transfers)
    cov.results_cited = len(cited)
    cov.notes = list(dict.fromkeys(cov.notes + ctx.notes))
    captured = {c.result_id for t in view.transfers for c in t.event.captured}
    cov.captured_uncited = sorted(captured - set(cited))
    return AuditResult(report=report, coverage=cov, divergences=getattr(ctx, "_divergences", []), findings=findings, transfer_states=states, task_state=task,
                       auditor_result_ids=list(ctx.auditor_result_ids), cited_result_ids=cited, translations=_safe_translation_audits(ctx, findings))


def _safe_translation_audits(ctx: CheckContext, findings: list[tuple[int, IntegrityFinding]]) -> list[TranslationAudit]:
    try:
        return translation_audits(ctx.translations, findings)
    except Exception:  # the records are bookkeeping; a failure here never hides a finding or passes anything
        return []


def _run_all(ctx: CheckContext, replays: dict[str, Replay], rederived: Optional[dict[int, Rederived]], *, batch: bool, shadow: bool) -> None:
    view = ctx.view
    if view.degraded:
        ctx.ovs(0, "OVS-AUDIT-002", "degraded view: the channel was audited without a journal, so custody (CUST-001/002/004, RCPT-001) is not decidable and results are limited to the copies receipts carry")
    if view.journal is not None:
        if view.journal.digest_only_entries:
            ctx.coverage.digest_only_entries = view.journal.digest_only_entries
        for note in view.journal.coverage_notes:
            ctx.ovs(0, "OVS-AUDIT-002", f"audit coverage lost: {note}")
    for t in view.transfers:
        live_transfer_checks(ctx, t, dependencies=False)
    # R2: re-derivation (deterministic; reuse what the live tier computed)
    ctx.ran("formal")
    for t in view.transfers:
        if t.kind not in formal.R2_KINDS:
            continue
        red = (rederived or {}).get(t.seq)
        if red is None:
            red = ctx.guard("formal", "re-derivation (R2)", lambda t=t: formal.rederive(ctx, t), transfer=t)
        if red is None:
            continue
        ctx.rederived[t.seq] = red
        if red.error:
            ctx.ovs(t.seq, "OVS-AUDIT-001", f"re-derivation of {t.kind} {t.message_id} failed internally ({red.error})", **t.ids())
        for f in red.findings:
            ctx.add(t.seq, f)
        ctx.guard("formal", "branch satisfied (R2)", lambda t=t: formal.check_branch_satisfied(ctx, t), transfer=t)
    # R1: replays
    if replays:
        ctx.ran("replay")
        ctx.coverage.results_replayed = len(replays)
        ctx.guard("replay", "replay findings", lambda: replay_findings(ctx, replays))
    if not batch:
        return
    # B1 sweep
    ctx.guard("custody", "journal chain (B1)", lambda: custody.check_chain(ctx))
    ctx.guard("custody", "log sweep (B1)", lambda: custody.sweep_log(ctx))
    if ctx.live is not None:
        ctx.guard("joint", "live pool (B1)", lambda: joint.check_live_pool(ctx))
    # B3 then B2 (B2's disclosure check runs against B3's contradictions as well)
    jo = ctx.guard("joint", "independent joint (B3)", lambda: joint.independent_joint(ctx))
    auditor_sets = [(claims, rid) for claims, rid, _rel, code in (jo.sets if jo is not None else []) if code == "INT-CONFLICT-001"]
    for t in view.transfers:
        if t.kind == "relay_synthesis":
            ctx.guard("synthesis", "ledger re-check (B2)", lambda t=t: synthesis.recheck_ledger(ctx, t), transfer=t)
            ctx.guard("synthesis", "conflict disclosure (B2)", lambda t=t: synthesis.recheck_disclosure(ctx, t, auditor_sets), transfer=t)
    divs = ctx.guard("divergence", "rule divergence (B4)", lambda: check_divergence(ctx))
    ctx._divergences = list(divs or [])  # type: ignore[attr-defined]
    if shadow:
        state = ctx.guard("shadow", "shadow channel (B5)", lambda: run_shadow(ctx))
        ctx.coverage.shadow_run = state if state in ("run", "skipped") else "not_run"
    else:
        ctx.coverage.shadow_run = "not_run"


# ============================================================================================ live auditor
@dataclass
class _ChannelState:
    uid: str
    journal: ChannelJournal
    view: OverseerView
    channel_ref: Any = None
    registry: Any = None
    sticky: list[tuple[int, IntegrityFinding]] = field(default_factory=list)
    event_findings: dict[int, list[IntegrityFinding]] = field(default_factory=dict)
    replay_jobs: dict[str, ReplayJob] = field(default_factory=dict)
    always: dict[int, set[str]] = field(default_factory=dict)  # seq -> always-replay result ids
    r2_keys: dict[int, str] = field(default_factory=dict)
    l5_keys: dict[int, str] = field(default_factory=dict)
    replay_cache: dict[str, tuple[Any, Replay]] = field(default_factory=dict)
    clearances: dict[str, TransferClearance] = field(default_factory=dict)
    audits: list[OverseerAudit] = field(default_factory=list)
    sampled_total: int = 0
    sampled_live: int = 0

    def live(self) -> Any:
        return self.channel_ref() if self.channel_ref is not None else None


class TransferAuditor:
    """The live Overseer auditor. One instance may observe many channels; every channel gets its own journal."""

    def __init__(self, keyring: KeyRing, *, replay_mode: Literal["process", "inline"] = "process", store: Optional[ResultStore] = None,
                 journals: Optional[JournalSet] = None, queue_bound: int = 256, sample_rate: float = 0.25, eager: bool = False,
                 shadow: Literal["always", "sampled", "off"] = "sampled", shadow_sample_rate: float = 0.10, registry: Any = None) -> None:
        self.keyring = keyring
        self.store = store or ResultStore(keyring)
        self.journals = journals or JournalSet(keyring)
        self.replayer = Replayer(keyring, mode=replay_mode, queue_bound=queue_bound, sample_rate=sample_rate, eager=eager)
        self.replay_mode = replay_mode
        self.shadow = shadow
        self.shadow_sample_rate = shadow_sample_rate
        self.registry = registry
        self._channels: dict[str, _ChannelState] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ attachment
    def observer_for(self, channel: Any):
        """The observer callable for ``channel``: it journals the channel's events and keeps a weak reference to the
        live channel for the custody checks. When the channel is garbage-collected its journal is sealed."""
        ref = weakref.ref(channel)
        registry = getattr(channel, "registry", None)

        def observe(event: ChannelEvent) -> None:
            self.on_event(event, channel=ref(), registry=registry)

        observe.__qualname__ = "TransferAuditor.observe"
        return observe

    def _state(self, event: ChannelEvent, channel: Any, registry: Any) -> _ChannelState:
        st = self._channels.get(event.channel_uid)
        if st is None:
            journal = self.journals.create(event.channel_uid, event.task_id)
            if not journal.entries() and event.seq > 1:
                journal.start_at(event.seq)
            view = OverseerView(channel_uid=event.channel_uid, task_id=event.task_id, request_id=event.request_id, transfers=[], plans={}, channel_info={},
                                store=self.store, journal=journal, degraded=False, first_seq=event.seq)
            st = _ChannelState(uid=event.channel_uid, journal=journal, view=view, registry=registry or self.registry)
            self._channels[event.channel_uid] = st
            if channel is not None:
                try:
                    weakref.finalize(channel, self._channel_gone, event.channel_uid)
                except TypeError:
                    pass
        if channel is not None:
            st.channel_ref = weakref.ref(channel)
            st.view.channel = None  # the view never holds the live channel strongly
        if registry is not None:
            st.registry = registry
        return st

    def _channel_gone(self, uid: str) -> None:
        try:
            self.seal(uid, "channel garbage-collected")
        except Exception:
            pass

    def channel_uids(self, task_id: Optional[str] = None) -> list[str]:
        with self._lock:
            return [u for u, st in self._channels.items() if task_id is None or st.journal.task_id == task_id]

    def journal(self, channel_uid: str) -> ChannelJournal:
        return self._channels[channel_uid].journal

    # ------------------------------------------------------------------ live tier
    def __call__(self, event: ChannelEvent) -> None:
        self.on_event(event)

    def on_event(self, event: ChannelEvent, *, channel: Any = None, registry: Any = None) -> Optional[TransferClearance]:
        """Journal one event, store its captured results, run L1-L6 for it, queue R1/R2, and journal its clearance.
        Never raises into the channel: an internal failure is recorded and the transfer cannot pass."""
        with self._lock:
            try:
                st = self._state(event, channel, registry)
            except Exception:
                return None
            try:
                entry = st.journal.append(event)
            except (ValueError, JournalSealed) as exc:
                code = "OVS-CUST-003"
                st.sticky.append((event.seq, ovs_finding(code, f"event {event.seq} ({event.kind}) of channel {event.channel_uid} could not be journaled ({type(exc).__name__}: {str(exc)[:200]})",
                                                         message_ids=[event.message_id] if event.message_id else [])))
                return None
            try:
                t = st.view.extend(entry)
                if t is None or st.view.by_seq.get(t.seq) is not t:
                    return None  # a call that raised before issuing anything: journaled, swept by B1
                ctx = self._ctx(st)
                live_transfer_checks(ctx, t, dependencies=True, at_issue=True)
                st.event_findings[t.seq] = [f for _s, f in ctx.findings]
                self._queue_async(st, t)
                return self._issue_clearance(st, t, final=False)
            except Exception as exc:
                st.sticky.append((event.seq, ovs_finding("OVS-AUDIT-001", f"the live audit of event {event.seq} failed internally ({type(exc).__name__}: {str(exc)[:200]})",
                                                         message_ids=[event.message_id] if event.message_id else [])))
                try:
                    t = st.view.by_seq.get(event.seq)
                    return self._issue_clearance(st, t, final=False) if t is not None else None
                except Exception:
                    return None

    def _ctx(self, st: _ChannelState) -> CheckContext:
        return CheckContext(view=st.view, keyring=self.keyring, store=self.store, live=st.live(), registry=st.registry)

    def _always_ids(self, st: _ChannelState, t: Transfer) -> set[str]:
        out: set[str] = set()
        rc = t.receipt
        if rc is None:
            return out
        for o in rc.outcomes:
            if o.verification is not None and is_definitive(o.display_status):
                out.add(o.verification.result_id)
        for f in rc.findings:
            if f.severity == "error" and f.code in ALWAYS_REPLAY_CODES and f.formal_result_id:
                out.add(f.formal_result_id)
        if t.kind == "relay_synthesis":
            out.update(r for r, _k, _p in cited_results(rc))
            if t.synthesis is not None:
                sources = {s for sc in t.synthesis.claims for s in sc.source_claim_ids}
                for prev in st.view.transfers:
                    if prev.seq >= t.seq or prev.receipt is None:
                        continue
                    for o in prev.receipt.outcomes:
                        if o.claim_id in sources and o.verification is not None:
                            out.add(o.verification.result_id)
        return out

    def _queue_async(self, st: _ChannelState, t: Transfer) -> None:
        always = self._always_ids(st, t)
        st.always[t.seq] = always
        candidates = [c.result_id for c in t.event.captured]
        if t.receipt is not None:  # results signed by a declared external engine are stored when first cited
            candidates += [rid for rid, _k, _p in cited_results(t.receipt)]
        for rid in dict.fromkeys(candidates):
            if rid in st.replay_jobs:
                continue
            rec = self.store.live(rid)
            if rec is None or not rec.problem_json or rec.origin not in ("captured", "external") or rec.channel_uid != st.uid:
                continue
            res = self.store.parsed(rid)
            if res is None:
                continue
            job = ReplayJob(result_id=rid, problem_json=rec.problem_json, config_json=canonical_json(res.solver_config.model_dump(mode="json")),
                            original_status=res.status.value, problem_digest=res.binding.problem_digest, config_digest=res.binding.config_digest,
                            versions_digest=res.binding.versions_digest, always=rid in always, seq=t.seq, channel_uid=st.uid)
            st.replay_jobs[rid] = job
            st.sampled_total += 1
            if self.replayer.submit(job) == "sampled_out":
                st.sampled_live += 1
        for rid in always:  # promotes a result sampled out earlier (a synthesis now relies on it)
            job = st.replay_jobs.get(rid)
            if job is not None and not job.always:
                promoted = ReplayJob(**{**job.__dict__, "always": True})
                st.replay_jobs[rid] = promoted
                self.replayer.submit(promoted)
        if t.kind in formal.R2_KINDS and t.delivered and t.report is not None:
            key = f"r2|{st.uid}|{t.seq}"
            st.r2_keys[t.seq] = key
            ctx = self._ctx(st)
            self.replayer.submit_task(key, lambda ctx=ctx, t=t: formal.rederive(ctx, t))
            key5 = f"l5|{st.uid}|{t.seq}"
            st.l5_keys[t.seq] = key5
            ctx5 = self._ctx(st)

            def run_l5(ctx5=ctx5, t=t):
                ctx5.guard("fidelity", "fidelity", lambda: fidelity.check_fidelity(ctx5, t), transfer=t)
                run_translation_checks(ctx5, t)
                return list(ctx5.findings)
            self.replayer.submit_task(key5, run_l5)

    def _replays(self, st: _ChannelState) -> dict[str, Replay]:
        out: dict[str, Replay] = {}
        outcomes = self.replayer.outcomes()
        for rid in st.replay_jobs:
            o = outcomes.get(rid)
            if o is None:
                continue
            cached = st.replay_cache.get(rid)
            if cached is not None and cached[0] is o:
                out[rid] = cached[1]
                continue
            replayed = None
            if o.result_json:
                try:
                    replayed = faithful(VerificationResult, json.loads(o.result_json))
                except Exception:
                    replayed = None
                from ..engine.sink import CapturedResult
                rec = self.store.put(CapturedResult(result_id=replayed.result_id if replayed else rid + "-replay", key_id=RUN_KEY_ID, result_json=o.result_json,
                                                    result_sha256=sha256_hex(o.result_json), problem_json=o.job.problem_json, problem_digest=None),
                                     channel_uid=st.uid, task_id=st.journal.task_id, request_id=st.view.request_id, event_seq=o.job.seq, origin="replay") if replayed else None
            out[rid] = compare_replay(o.job, replayed, budget_exceeded=o.budget_exceeded, error=o.error)
            st.replay_cache[rid] = (o, out[rid])
        return out

    def _rederived(self, st: _ChannelState) -> dict[int, Rederived]:
        out: dict[int, Rederived] = {}
        for seq, key in st.r2_keys.items():
            done, value, err = self.replayer.task_result(key)
            if done and (value is not None or err):
                out[seq] = value if value is not None else Rederived(seq=seq, error=err)
        return out

    def _pending(self, st: _ChannelState) -> dict[str, set[str]]:
        pend_ids = self.replayer.pending() | self.replayer.sampled_out()
        done = self.replayer.outcomes()
        out: dict[str, set[str]] = {}
        for t in st.view.transfers:
            if not t.message_id:
                continue
            p = {rid for rid in st.always.get(t.seq, set()) if rid in st.replay_jobs and rid not in done}
            p |= {rid for rid in st.always.get(t.seq, set()) if rid in pend_ids}
            if t.seq in st.r2_keys and not self.replayer.task_result(st.r2_keys[t.seq])[0]:
                p.add(st.r2_keys[t.seq])
            if t.seq in st.l5_keys and not self.replayer.task_result(st.l5_keys[t.seq])[0]:
                p.add(st.l5_keys[t.seq])
            if p:
                out[t.message_id] = p
        return out

    def _async_findings(self, st: _ChannelState) -> list[tuple[int, IntegrityFinding]]:
        ctx = self._ctx(st)
        replays = self._replays(st)
        if replays:
            replay_findings(ctx, replays)
        for seq, red in self._rederived(st).items():
            t = st.view.by_seq.get(seq)
            if t is None:
                continue
            ctx.rederived[seq] = red
            if red.error:
                ctx.ovs(seq, "OVS-AUDIT-001", f"re-derivation of {t.kind} {t.message_id} failed internally ({red.error})", **t.ids())
            for f in red.findings:
                ctx.add(seq, f)
            formal.check_branch_satisfied(ctx, t)
        for seq, key in st.l5_keys.items():
            done, value, err = self.replayer.task_result(key)
            if done:
                ctx.findings.extend(value or [])
                if err:
                    t = st.view.by_seq.get(seq)
                    ctx.ovs(seq, "OVS-AUDIT-001", f"the fidelity checks of event {seq} failed internally ({err})", **(t.ids() if t is not None else {}))
        return list(ctx.findings)

    def _all_live_findings(self, st: _ChannelState) -> list[tuple[int, IntegrityFinding]]:
        out = [(seq, f) for seq, fs in st.event_findings.items() for f in fs]
        out += list(st.sticky)
        out += self._async_findings(st)
        return _dedupe(out)

    def _issue_clearance(self, st: _ChannelState, t: Transfer, *, final: bool, presented_sha: Optional[str] = None, audit_id: Optional[str] = None,
                         findings: Optional[list[tuple[int, IntegrityFinding]]] = None, pending: Optional[dict[str, set[str]]] = None) -> TransferClearance:
        findings = findings if findings is not None else self._all_live_findings(st)
        pending = pending if pending is not None else self._pending(st)
        states, _task = transfer_states(st.view, findings, pending)
        state = states.get(t.message_id or "", "AUDIT_FAILED")
        names = _dependency_ids(st.view, t)
        codes = sorted({f.code for _s, f in findings if set(f.message_ids) & names and not is_agent_code(f.code)})
        clr = TransferClearance(clearance_id=uuid.uuid4().hex, message_id=t.message_id or "", receipt_id=t.receipt_id, receipt_sha256=t.event.receipt_sha256,
                                presented_receipt_sha256=presented_sha, task_id=st.journal.task_id, channel_uid=st.uid, seq=t.seq, state=state, final=final,
                                codes=codes, finding_count=sum(1 for _s, f in findings if set(f.message_ids) & names and not is_agent_code(f.code)),
                                audit_id=audit_id, pending_result_ids=sorted((pending or {}).get(t.message_id or "", set())), created_at=_now())
        st.clearances[clr.message_id] = clr
        try:
            st.journal.append_record("clearance", clr.model_dump(mode="json"))
        except JournalSealed:
            pass
        return clr

    def clearance(self, channel_uid: str, message_id: str, *, receipt: Any = None, wait_ms: int = 0) -> TransferClearance:
        """The router's check immediately before acting on a transfer: re-runs L1 for the message and its dependencies
        against the live channel, compares the presented receipt (or the channel's) with the journal, waits up to
        ``wait_ms`` for outstanding replay, and journals the result."""
        with self._lock:
            st = self._channels.get(channel_uid)
            if st is None:
                raise KeyError(f"no journal for channel {channel_uid!r}")
            t = st.view.by_message.get(message_id)
            if t is None:
                f = ovs_finding("OVS-CUST-003", f"message {message_id} was never journaled on channel {channel_uid}: the router is about to act on a transfer written around the channel", message_ids=[message_id])
                st.sticky.append((0, f))
                clr = TransferClearance(clearance_id=uuid.uuid4().hex, message_id=message_id, task_id=st.journal.task_id, channel_uid=channel_uid, state="AUDIT_FAILED",
                                        codes=["OVS-CUST-003"], finding_count=1, created_at=_now())
                try:
                    st.journal.append_record("clearance", clr.model_dump(mode="json"))
                except JournalSealed:
                    pass
                return clr
        if wait_ms > 0:
            self.replayer.drain(timeout_s=wait_ms / 1000.0)
            self.replayer.wait_tasks(timeout_s=wait_ms / 1000.0)
        with self._lock:
            ctx = self._ctx(st)
            for s in [t.seq] + list(t.depends_on):
                d = st.view.by_seq.get(s)
                if d is not None:
                    ctx.guard("custody", "custody (clearance)", lambda d=d: custody.check_custody(ctx, d), transfer=d)
                    ctx.guard("receipts", "receipt (clearance)", lambda d=d: receipts.check_receipt_custody(ctx, d), transfer=d)
            presented_sha = None
            if receipt is not None:
                presented_sha = ctx.guard("receipts", "presented receipt", lambda: receipts.check_presented_receipt(ctx, t, receipt), transfer=t)
            ctx.guard("joint", "live pool (clearance)", lambda: joint.check_live_pool(ctx))
            for item in ctx.findings:
                if item not in st.sticky:
                    st.sticky.append(item)
            return self._issue_clearance(st, t, final=False, presented_sha=presented_sha)

    def drain(self, timeout_s: Optional[float] = None) -> None:
        """Finish outstanding replays and re-derivations (inline: run them; process: wait for the worker)."""
        self.replayer.drain(timeout_s=timeout_s)
        self.replayer.wait_tasks(timeout_s=timeout_s if timeout_s is not None else 30.0)

    # ------------------------------------------------------------------ batch tier
    def view(self, channel_uid: str) -> OverseerView:
        st = self._channels[channel_uid]
        return OverseerView.from_journal(st.journal, self.store)

    def translations(self, channel_uid: str) -> list:
        """Every translation of a delivered claim on the channel, as the journal holds it (translator oversight): the
        claim and the claims it cites, the proposed IR, the translation's own validation outcome, the auditor's
        re-validation and the signed result the store holds, with the translation checks that applied to it
        (:class:`~epinoic_logic.overseer.checks.translation.TranslationRecord`). Read-only: nothing is journaled."""
        view = self.view(channel_uid)
        with self._lock:
            ctx = CheckContext(view=view, keyring=self.keyring, store=self.store, registry=self._channels[channel_uid].registry)
        out: list = []
        for t in view.transfers:
            out.extend(translation.check_translations(ctx, t))
        return out

    def _shadow_for(self, st: _ChannelState, has_findings: bool, override: Optional[bool]) -> bool:
        if override is not None:
            return override
        if self.shadow == "always":
            return True
        if self.shadow == "off":
            return False
        return has_findings or self.keyring.sample_fraction("shadow|" + st.uid) < self.shadow_sample_rate

    def audit(self, channel_uid: str, *, final: bool = False, shadow: Optional[bool] = None) -> OverseerAudit:
        """The signed task audit (scope ``task``, mode ``batch``): every remaining replay (sampled-out included), R2,
        and B1-B5 over the journal. A FINAL audit seals the journal; a later audit of the same scope names the previous
        one in ``supersedes``."""
        with self._lock:
            st = self._channels[channel_uid]
        self.replayer.drain(include_sampled=True)
        self.replayer.wait_tasks(timeout_s=60.0)
        with self._lock:
            # results feeding a synthesis that were never queued (e.g. promoted late) are queued now
            replays = self._replays(st)
            missing = [j for rid, j in st.replay_jobs.items() if rid not in replays]
        if missing:
            for j in missing:
                self.replayer.submit(j)
            self.replayer.drain(include_sampled=True)
        with self._lock:
            replays = self._replays(st)
            rederived = self._rederived(st)
            view = OverseerView.from_journal(st.journal, self.store)
            live = st.live()
            sticky = list(st.sticky)
            live_findings = [(seq, f) for seq, fs in st.event_findings.items() for f in fs]
            has_findings = any(True for _ in live_findings) or bool(sticky)
            do_shadow = self._shadow_for(st, has_findings, shadow)
            pending = {}
            if self.replay_mode == "process":
                outstanding = self.replayer.pending()
                pending = {mid: ids & outstanding for mid, ids in self._pending(st).items() if ids & outstanding}
            result = run_overseer_checks(view, keyring=self.keyring, store=self.store, live=live, registry=st.registry, replays=replays, rederived=rederived,
                                         batch=True, shadow=do_shadow, replay_mode=self.replay_mode, pending=pending, extra_findings=sticky,
                                         sampled=(st.sampled_total - st.sampled_live, st.sampled_total) if st.sampled_live else (0, 0))
            cov = result.coverage
            cov.results_sampled_out = st.sampled_live
            cov.results_replay_pending = sum(len(v) for v in pending.values())
            findings = list(result.findings)
            if final and self.replay_mode != "process":
                f = ovs_finding("OVS-AUDIT-002", "this FINAL audit's replays ran inline, not in an isolated worker process: replay independence is not established")
                findings.append((0, f))
                result.report.findings.append(f)
                result.report.report_sha256 = report_digest(result.report)
                states, task = transfer_states(view, findings, pending)
                result.transfer_states, result.task_state = states, task
            prev = next((a for a in reversed(st.audits) if a.scope == "task"), None)
            head = st.journal.head()
            audit = OverseerAudit(audit_id=uuid.uuid4().hex, supersedes=prev.audit_id if prev is not None else None, scope="task", mode="batch", final=final,
                                  state=result.task_state, task_id=st.journal.task_id, request_id=result.report.request_id, channel_uid=st.uid,
                                  message_ids=[t.message_id for t in view.transfers if t.message_id], transfer_states=result.transfer_states,
                                  journal_head=JournalHead(index=head[0], entry_hash=head[1]), store_digest=self.store.digest(result.cited_result_ids),
                                  report=result.report, coverage=cov, divergences=result.divergences, translations=result.translations,
                                  key_ids_used=self._key_ids(view), created_at=_now())
            audit = sign_audit(audit, self.keyring)
            st.audits.append(audit)
            for t in view.transfers:
                if t.message_id and t.message_id in result.transfer_states:
                    self._issue_clearance(st, t, final=final, audit_id=audit.audit_id, findings=findings, pending=pending)
            if final:
                self.seal(channel_uid, "final task audit")
            return audit

    def _key_ids(self, view: OverseerView) -> list[str]:
        out = set()
        for t in view.transfers:
            for c in t.event.captured:
                if c.key_id:
                    out.add(c.key_id)
            if t.receipt is not None:
                out.update(o.verification.signature_key_id for o in t.receipt.outcomes if o.verification is not None and o.verification.signature_key_id)
        return sorted(out)

    def audits(self, channel_uid: str) -> list[OverseerAudit]:
        return list(self._channels[channel_uid].audits)

    def transfer_audit(self, channel_uid: str, message_id: str) -> OverseerAudit:
        """A signed audit of one transfer (scope ``transfer``, mode ``live``) from the live tier's findings."""
        with self._lock:
            st = self._channels[channel_uid]
            t = st.view.by_message[message_id]
            findings = self._all_live_findings(st)
            pending = self._pending(st)
            states, _task = transfer_states(st.view, findings, pending)
            names = _dependency_ids(st.view, t)
            mine = [(s, f) for s, f in findings if set(f.message_ids) & names]
            plan = st.view.plan
            report = IntegrityReport(report_id=uuid.uuid4().hex, request_id=getattr(plan, "request_id", st.view.request_id) or "unknown",
                                     task_id=getattr(plan, "task_id", st.journal.task_id) or "unknown", checks_run=["custody", "receipts", "results", "formal", "fidelity", "translation", "peer", "synthesis", "joint"],
                                     findings=[f for _s, f in mine], formal_result_ids=sorted({f.formal_result_id for _s, f in mine if f.formal_result_id}), created_at=_now())
            report.report_sha256 = report_digest(report)
            prev = next((a for a in reversed(st.audits) if a.scope == "transfer" and message_id in a.message_ids), None)
            head = st.journal.head()
            audit = OverseerAudit(audit_id=uuid.uuid4().hex, supersedes=prev.audit_id if prev else None, scope="transfer", mode="live", final=False,
                                  state=states.get(message_id, "AUDIT_FAILED"), task_id=st.journal.task_id, request_id=report.request_id, channel_uid=st.uid,
                                  message_ids=[message_id], transfer_states={message_id: states.get(message_id, "AUDIT_FAILED")},
                                  journal_head=JournalHead(index=head[0], entry_hash=head[1]),
                                  store_digest=self.store.digest([r for r, _k, _p in (cited_results(t.receipt) if t.receipt else [])]),
                                  report=report, coverage=AuditCoverage(transfers=1, replay_mode=self.replay_mode), created_at=_now())
            audit = sign_audit(audit, self.keyring)
            st.audits.append(audit)
            return audit

    # ------------------------------------------------------------------ lifecycle
    def seal(self, channel_uid: str, reason: str) -> None:
        with self._lock:
            st = self._channels.get(channel_uid)
            if st is None:
                return
            st.journal.seal(reason)
            self.store.seal_channel(channel_uid)

    def close(self) -> None:
        self.replayer.close()
