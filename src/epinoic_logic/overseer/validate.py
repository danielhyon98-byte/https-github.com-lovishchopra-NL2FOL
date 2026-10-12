"""Validation of an overseer agent's verdict: what each accusation is worth, decided only by deterministic checks and
signed engine results.

:func:`validate_overseer_verdict` takes the verdict envelope the intake signed, the view, the result store, the task
audit and (optionally) the live :class:`~epinoic_logic.overseer.audit.TransferAuditor`, and returns a
:class:`VerdictAssessment`, emitted as a signed ``OverseerAudit`` of scope ``verdicts``.

**Binding.** It first re-checks the intake's binding, so a verdict that reached it by another path is still AGENT-005:
the envelope is an ``overseer_verdict/1.0`` envelope from the Overseer role to ``overseer-auditor``, its payload digest
holds, it is signed under the intake key and it is the envelope the intake accepted; the payload validates against the
contract; ``agent_id``, ``task_id``, ``dossier_sha256``, ``lens`` and ``pack`` equal the issue record, and the pack is
one the intake accepts. The assessment records the verdict's pack identity.

**Each accusation** then goes through these steps (design section 9.5):

1. **Resolve** against the dossier the agent was issued: every identifier occurs in the dossier, every evidence pointer
   resolves (RFC 6901), every quote occurs in the visible text of the field its pointer names. Anything else is
   **unverifiable** (AGENT-002).
2. **Look up** in the verified task audit (and, with an auditor, in its latest signed task audit when that is newer):
   a finding of a mapped code (``KIND_CHECKS``) that names the accusation's identifiers **confirms** it (AGENT-003),
   citing that finding.
3. **Targeted re-run** (with an auditor): the named results that were not decisively replayed (sampled out, pending,
   never queued) are replayed through the auditor's replayer, and the checks are re-run on the journal with full
   coverage (the live channel for custody, the shadow channel when the kind needs it). When this yields a matching
   finding the auditor issues a new signed task audit (``supersedes`` names the previous one) that contains it under
   its own ``OVS-*`` code, and the accusation is **confirmed** citing that audit's finding. A signed audit is never
   edited.
4. **Refuted** (AGENT-001): the mapped checks ran with full coverage on the named identifiers and found nothing.
   ``refuted_by`` is ``signed_result`` when the decisive evidence was a verified signed result or a replay, and
   ``deterministic_check`` otherwise.
5. **Unresolved** (AGENT-004, human review): a kind no check decides (``translation_unfaithful``, ``other``); or a
   check that could not decide (coverage lost, a result evicted or not decisively replayed, a degraded or digest-only
   journal, a peer link by text equality only, claims no engine check compares, no live channel for a custody check,
   the shadow not run, a translation check that did not run on the named claim's translation).

Every **engine statement** is compared with the stored result: a different status, or an unknown result id asserted as
existing, is AGENT-001 (``signed_result`` when the stored result's signature verifies); a pointer that does not
resolve or does not hold the asserted status is AGENT-002.

**Authority.** The agent's words decide nothing. ``OVS-AGENT-*`` findings never change a transfer's clearance
(decision 16): the ``verdicts`` audit copies the task audit's state and transfer states unchanged. A confirmed
accusation acts only through the confirming ``OVS-*`` finding, which the auditor itself decided. Agent text (the
statements and notes) is never copied into a finding, never evaluated and never followed.

Deviations from ``docs/OVERSEER_DESIGN.md`` section 9.5, listed as each stage requires:

* **Resolve** is stricter than "none of the identifiers resolves": ONE identifier that occurs nowhere in the dossier
  makes the accusation unverifiable (the pack's Evidence rule E13 and its Examples §21, the wrong-verdicts table: "an invented identifier is
  unverifiable"); an accusation with no identifier at all is unverifiable too (E1);
* **Matching** is stricter than "names at least one identifier": the finding must share an identifier with the
  accusation, AND where both name claims, results or documents they must share one of those (a finding about claim c3
  does not confirm an accusation about claim c5 of the same transfer); receipt ids are matched through their message
  ids; ``figure_changed`` is confirmed by OVS-SYN-002 only when that finding names INT-LEDGER-023;
* the targeted re-run is ONE re-run per verdict (every check on the journal, the named results force-replayed), whose
  findings are then filtered to the mapped codes and the named identifiers; a new task audit is issued only when it
  yields a confirming finding, through ``TransferAuditor.audit`` (so the auditor records it, journals the recomputed
  clearances and every later clearance includes it); a re-run finding the issued audit does not reproduce leaves the
  accusation unresolved, never confirmed;
* with an auditor, the look-up also consults the auditor's latest signed task audit when it is newer than the one given
  (an earlier verdict's re-run, a later batch audit), so a second agent naming the same fault is confirmed by the audit
  the first one caused and no further audit is issued; a task audit that does not verify is never used, and its state is
  never carried into the ``verdicts`` audit;
* without an auditor, the given task audit is the only evidence: an accusation it does not confirm is refuted only when
  that audit is a verified batch task audit with full coverage for the kind, and never for the live-custody kinds;
* the transfers an accusation involves are its named messages and receipts AND every transfer that carries one of its
  claims, reports, documents or results or cites one of its results: if the evidence does not cover every one of them
  (a transfer issued after the given task audit), or the view is degraded or digest-only, or an ``OVS-AUDIT-001``, an
  ``OVS-AUDIT-002`` or an ``OVS-AUDIT-005`` naming one of them (or none) is present, the accusation is unresolved;
* an AGENT-001 refuted by a signed result cites that result (``formal_result_id``) and, for a replay, the signed replay;
* the ``verdicts`` audit names the task audit (and the superseding one) and the assessment digest in its coverage notes
  (``OverseerAudit`` has no field for them); its ``supersedes`` is None (verdicts of different agents do not
  supersede each other);
* translator oversight (design section 18): an accusation of a translation kind must name a claim; it is refuted only
  when, for every named claim, the evidence records a checked translation of it (on the named transfers and reports)
  on which every check the kind needs ran (:data:`TRANSLATION_CHECKS_NEEDED`: the eligibility re-derivation and the
  tracing run only on model-proposed translations under this code's policy version, so an accusation about a
  hand-built translation is unresolved, never refuted by a check that did not run); a ``receipt_altered`` accusation
  naming a claim whose outcome summary was not re-checked (its result not retained) is unresolved too.
"""
from __future__ import annotations

import hmac
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..engine.results import VerificationResult
from ..integrity.contracts import AgentMessage, IntegrityFinding, IntegrityReport, report_digest
from ..ir.canonical import canonical_json, sha256_hex
from .audit import run_overseer_checks, sign_audit, verify_audit
from .checks import Replay
from .codes import ovs_finding
from .contracts import AuditCoverage, ClearanceState, OverseerAudit, StoredResult
from .dossier import PointerError, dossier_identifiers, resolve_pointer, typed_identifiers, visible_text
from .faithful import faithful
from .intake import VerdictIntake
from .keys import INTAKE_KEY_ID, KeyRing
from .replay import ReplayJob, build_replay_job, classify, compare
from .store import ResultStore
from .verdicts import ID_FIELDS, KIND_CHECKS, KIND_CODE_QUALIFIERS, TRANSLATION_KINDS, UNCHECKED_KINDS, AgentVerdict, PackIdentity, accusation_identifiers
from .view import OverseerView

__all__ = [
    "validate_overseer_verdict", "VerdictAssessment", "AccusationAssessment", "EngineStatementAssessment", "FindingRef", "OUTCOME_CODES",
    "Outcome", "RefutedBy", "build_verdicts_audit", "assessment_digest", "finding_matches", "RESULT_KINDS", "LIVE_KINDS", "SHADOW_KINDS",
    "TRANSLATION_CHECKS_NEEDED", "RemainderAssessment", "coverage_split", "agent_label",
]

Outcome = Literal["confirmed", "refuted", "unverifiable", "unresolved"]
RefutedBy = Literal["signed_result", "deterministic_check"]
OUTCOME_CODES: dict[str, str] = {"confirmed": "OVS-AGENT-003", "refuted": "OVS-AGENT-001", "unverifiable": "OVS-AGENT-002", "unresolved": "OVS-AGENT-004"}
#: Kinds whose decisive evidence is a signed result (its signature, binding, status or replay).
RESULT_KINDS = frozenset({"result_unsigned_or_forged", "result_from_other_problem", "result_out_of_task", "formal_status_wrong", "replay_differs"})
#: Kinds decided (in part) by comparing LIVE objects with the journal: they need the live channel to be refuted.
LIVE_KINDS = frozenset({"payload_altered", "receipt_altered"})
#: Kinds decided (in part) by the shadow channel (RCPT-004, RCPT-008).
SHADOW_KINDS = frozenset({"finding_missing", "receipt_status_wrong"})
#: The translation checks (``checks_run`` of a translation record) that must have run on a named claim's translation
#: before an accusation of the kind can be refuted.
TRANSLATION_CHECKS_NEEDED: dict[str, tuple[str, ...]] = {
    "translation_invalid": ("revalidate", "status", "eligibility"),
    "translation_ungrounded": ("grounding", "trace"),
    "translation_circular": ("circular",),
    "receipt_altered": ("summary",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================================ the assessment contract
class FindingRef(BaseModel):
    """A finding of a signed audit: the audit, its position in the report and its identifiers."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    audit_id: Optional[str] = None
    index: int
    code: str
    severity: str
    message_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    formal_result_id: Optional[str] = None
    related_result_ids: list[str] = Field(default_factory=list)


class AccusationAssessment(BaseModel):
    """What one accusation is worth. ``reasons`` is the validator's own text; the agent's statement is never copied."""
    model_config = ConfigDict(extra="forbid")
    accusation_id: str
    kind: str
    claimed_severity: str
    outcome: Outcome
    code: str
    checks: list[str] = Field(default_factory=list)
    identifiers: dict[str, list[str]] = Field(default_factory=dict)
    unresolved_identifiers: dict[str, list[str]] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    refuted_by: Optional[RefutedBy] = None
    confirming: list[FindingRef] = Field(default_factory=list)
    first_seq: Optional[int] = None
    decided_by_rerun: bool = False
    #: Each named claim id -> the reports it was resolved to (claim ids are unique only within a report).
    claim_report_ids: dict[str, list[str]] = Field(default_factory=dict)
    #: The accusation's position in its verdict (findings name accusations by position, never by the agent's id).
    position: int = 0
    #: For a confirmed accusation: the identifiers its confirming findings cover (AGENT-003 names only these).
    covered_identifiers: dict[str, list[str]] = Field(default_factory=dict)
    #: The named transfers and claims no confirming finding covers, assessed on their own (refuted, unresolved).
    remainder: Optional["RemainderAssessment"] = None
    #: Resolution faults recorded beside a contradiction with a signed result (an extra AGENT-002).
    faults: list[str] = Field(default_factory=list)


class RemainderAssessment(BaseModel):
    """The part of a confirmed accusation that its confirming findings do not cover (named transfers and claims of no
    confirming finding), assessed on its own: a true accusation padded with clean transfers is confirmed only for what
    the findings cover, and the rest is refuted or goes to human review."""
    model_config = ConfigDict(extra="forbid")
    identifiers: dict[str, list[str]] = Field(default_factory=dict)
    outcome: Outcome
    code: str
    refuted_by: Optional[RefutedBy] = None
    reasons: list[str] = Field(default_factory=list)


AccusationAssessment.model_rebuild()


class EngineStatementAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str
    asserted_status: str
    pointer: str
    outcome: Literal["agrees", "refuted", "unverifiable", "undecided"]
    code: Optional[str] = None
    stored_status: Optional[str] = None
    signature_verified: Optional[bool] = None
    refuted_by: Optional[RefutedBy] = None
    reason: str = ""
    #: The statement's position in its verdict, and whether its result id is one of this dossier's (only then is the id
    #: shown in a finding; any other id is agent text and is shown as a digest).
    position: int = 0
    known_result: bool = False
    #: A pointer fault recorded beside a contradiction with a signed result (an extra AGENT-002).
    pointer_fault: Optional[str] = None


class VerdictAssessment(BaseModel):
    """The assessment of one verdict. ``valid`` is False for a verdict that fails the binding re-check (AGENT-005);
    then no accusation is assessed. ``audit`` is the signed ``verdicts``-scope audit that carries ``findings``."""
    model_config = ConfigDict(extra="forbid")
    assessment_id: str
    intake_message_id: Optional[str] = None
    verdict_id: Optional[str] = None
    agent_id: str
    task_id: str
    request_id: str = ""
    channel_uid: str
    lens: Optional[str] = None
    mode: Optional[str] = None
    pack: Optional[PackIdentity] = None
    dossier_sha256: Optional[str] = None
    valid: bool
    invalid_reason: Optional[str] = None
    task_audit_id: Optional[str] = None
    superseding_audit_id: Optional[str] = None
    transfers_reviewed: list[str] = Field(default_factory=list)
    accusations: list[AccusationAssessment] = Field(default_factory=list)
    engine_statements: list[EngineStatementAssessment] = Field(default_factory=list)
    findings: list[IntegrityFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    created_at: str
    audit: Optional[OverseerAudit] = None

    def outcome_of(self, accusation_id: str) -> Optional[AccusationAssessment]:
        return next((a for a in self.accusations if a.accusation_id == accusation_id), None)


def assessment_digest(assessment: BaseModel) -> str:
    """sha256 of the canonical assessment without its signed audit (the audit carries this digest)."""
    data = assessment.model_dump(mode="json", exclude={"audit"}, exclude_none=True)
    return sha256_hex(canonical_json(data))


# ============================================================================================ matching
def finding_matches(kind: str, ids: dict[str, list[str]], f: IntegrityFinding, receipt_to_message: Optional[dict[str, str]] = None,
                    claim_reports: Optional[dict[str, list[str]]] = None) -> bool:
    """Whether ``f`` confirms an accusation of ``kind`` naming ``ids`` (see the module docstring for the rule).

    Claim ids are unique only within a report, so claims are compared as ``(report_id, claim_id)`` pairs whenever both
    sides say which report: the accusation through ``claim_reports`` (the reports its claims resolved to in the
    dossier) and the finding through its ``report_ids``. Where both name messages (receipts mapped to their messages),
    reports, claims, documents or results, they must share one of each: a finding about message M1 and report R1 never
    confirms an accusation about message M2 and report R2."""
    if f.code not in KIND_CHECKS.get(kind, ()):
        return False
    qual = KIND_CODE_QUALIFIERS.get((kind, f.code))
    if qual and not any(q in f.message for q in qual):
        return False
    r2m = receipt_to_message or {}
    msgs = (set(ids.get("message_ids", ())) | {r2m[r] for r in ids.get("receipt_ids", ()) if r in r2m}, set(f.message_ids))
    f_results = ({f.formal_result_id} if f.formal_result_id else set()) | set(f.related_result_ids)
    if claim_reports and f.report_ids and f.claim_ids:
        acc_pairs = {(r, c) for c in ids.get("claim_ids", ()) for r in (claim_reports.get(c) or [""])}
        claims = (acc_pairs, {(r, c) for r in f.report_ids for c in f.claim_ids})
    else:
        claims = (set(ids.get("claim_ids", ())), set(f.claim_ids))
    docs = (set(ids.get("document_ids", ())), set(f.document_ids))
    results = (set(ids.get("result_ids", ())), f_results)
    reports = (set(ids.get("report_ids", ())), set(f.report_ids))
    pairs = [msgs, claims, reports, docs, results]
    if not any(a & b for a, b in pairs):
        return False
    for a, b in (msgs, reports, claims, docs, results):
        if a and b and not (a & b):
            return False
    return True


def _claim_pairs(ids: dict[str, list[str]], claim_reports: Optional[dict[str, list[str]]]) -> set[tuple[str, str]]:
    return {(r, c) for c in ids.get("claim_ids", ()) for r in ((claim_reports or {}).get(c) or [""])}


def coverage_split(ids: dict[str, list[str]], findings: Iterable[Any], receipt_to_message: Optional[dict[str, str]] = None,
                   claim_reports: Optional[dict[str, list[str]]] = None, report_of_message: Optional[dict[str, set[str]]] = None,
                   messages_of_claim: Optional[dict[tuple[str, str], set[str]]] = None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """``(covered, remainder)``: the accusation's named transfers (messages, receipts mapped to them) and ``(report,
    claim)`` pairs that the union of its matching findings covers, and those it does not. A named message is covered when
    a finding names it, names a report it delivers, or names a claim it carries; a named claim when a finding names it
    (under the same report, when both say which). Other identifier lists are kept on the covered side only where a
    finding names them too. The remainder is empty when the findings cover everything the accusation names."""
    r2m = receipt_to_message or {}
    findings = list(findings)
    f_msgs = {m for f in findings for m in f.message_ids}
    f_reports = {r for f in findings for r in f.report_ids}
    f_pairs: set[tuple[str, str]] = set()
    for f in findings:
        f_pairs |= {(r, c) for r in (f.report_ids or [""]) for c in f.claim_ids}
    f_claims = {c for _r, c in f_pairs}

    def pair_covered(r: str, c: str) -> bool:
        return (r, c) in f_pairs or ("", c) in f_pairs or (r == "" and c in f_claims)

    covered_claims, rest_claims = [], []
    covered_pairs: set[tuple[str, str]] = set()
    for c in dict.fromkeys(ids.get("claim_ids", ())):
        reps = (claim_reports or {}).get(c) or [""]
        hit = [(r, c) for r in reps if pair_covered(r, c)]
        (covered_claims if hit else rest_claims).append(c)
        covered_pairs.update(hit)
    carried_by: dict[str, set[str]] = {}
    for pair in covered_pairs:
        for m in (messages_of_claim or {}).get(pair, set()) | (messages_of_claim or {}).get(("", pair[1]), set()):
            carried_by.setdefault(m, set()).add(pair[1])

    def msg_covered(m: str) -> bool:
        return m in f_msgs or bool((report_of_message or {}).get(m, set()) & f_reports) or m in carried_by

    named_msgs = list(dict.fromkeys(list(ids.get("message_ids", ())) + [r2m[r] for r in ids.get("receipt_ids", ()) if r in r2m]))
    rest_msgs = [m for m in named_msgs if not msg_covered(m)]
    f_docs = {d for f in findings for d in f.document_ids}
    f_results = {x for f in findings for x in ([f.formal_result_id] if f.formal_result_id else []) + list(f.related_result_ids)}
    covered = {
        "message_ids": [m for m in ids.get("message_ids", ()) if m not in rest_msgs],
        "receipt_ids": [r for r in ids.get("receipt_ids", ()) if r2m.get(r) not in rest_msgs],
        "claim_ids": covered_claims,
        "report_ids": [r for r in ids.get("report_ids", ()) if r in f_reports or any(r in ((claim_reports or {}).get(c) or []) for c in covered_claims)],
        "document_ids": [d for d in ids.get("document_ids", ()) if d in f_docs],
        "result_ids": [x for x in ids.get("result_ids", ()) if x in f_results],
    }
    remainder = {"message_ids": rest_msgs, "receipt_ids": [], "claim_ids": rest_claims,
                 "report_ids": sorted({r for c in rest_claims for r in ((claim_reports or {}).get(c) or []) if r}), "result_ids": [], "document_ids": []}
    if not rest_msgs and not rest_claims:
        remainder = {}
    return covered, remainder


def agent_label(text: str) -> str:
    """An agent-chosen identifier as a finding shows it: a short digest, never the text (a verdict id, an accusation id or
    an engine statement's result id that is not one of the dossier's could carry instructions)."""
    return "sha256:" + sha256_hex(text)[:12]


def _ref(audit_id: Optional[str], index: int, f: IntegrityFinding) -> FindingRef:
    return FindingRef(audit_id=audit_id, index=index, code=f.code, severity=f.severity, message_ids=list(f.message_ids), claim_ids=list(f.claim_ids),
                      report_ids=list(f.report_ids), document_ids=list(f.document_ids), formal_result_id=f.formal_result_id,
                      related_result_ids=list(f.related_result_ids))


# ============================================================================================ evidence bases
@dataclass
class _Base:
    """What a set of checks ran over and found: the given task audit, or the targeted re-run."""
    source: str
    audit_id: Optional[str]
    findings: list[IntegrityFinding]
    covered_messages: Optional[set[str]]
    shadow_ran: bool
    live_checked: bool
    degraded: bool
    replay_agrees: set[str]
    pooled_claims: set[str]
    replays: dict[str, Replay] = field(default_factory=dict)
    translations: list = field(default_factory=list)


def _pooled(view: OverseerView) -> set[str]:
    return {e.claim_id for e in view.transfers[-1].pool_after} if view.transfers else set()


def _replayable(store: ResultStore, channel_uid: str, seqs: set[int]) -> set[str]:
    """Engine results of this channel that a batch audit covering the events ``seqs`` replayed."""
    return {r.result_id for r in store.results_of(channel_uid) if r.origin in ("captured", "external") and r.problem_json and r.event_seq in seqs}


def _replay_job(view: Any, store: ResultStore, rid: str, channel_uid: str, seq: int) -> Optional[ReplayJob]:
    """The replay job of an engine result of this channel, built exactly as the auditor builds it (``build_replay_job``:
    the store's or the journal's copy, under the channel's journaled configuration)."""
    rec = store.get(rid)
    if rec is None or rec.origin not in ("captured", "external") or rec.channel_uid != channel_uid:
        return None
    return build_replay_job(view, store, rid, always=True, seq=getattr(rec, "event_seq", 0) or seq, channel_uid=channel_uid)


def _replays_of(auditor: Any, channel_uid: str) -> dict[str, Replay]:
    out: dict[str, Replay] = {}
    for rid, o in auditor.replayer.outcomes().items():
        if o.job.channel_uid != channel_uid:
            continue
        replayed = None
        if o.result_json:
            try:
                replayed = faithful(VerificationResult, json.loads(o.result_json))
            except Exception:
                replayed = None
        out[rid] = compare(o.job, replayed, budget_exceeded=o.budget_exceeded, error=o.error)
    return out


# ============================================================================================ the validator
@dataclass
class _Ctx:
    view: OverseerView
    store: ResultStore
    keyring: KeyRing
    intake: VerdictIntake
    auditor: Any
    live: Any
    registry: Any
    replay_timeout_s: float
    verdict: AgentVerdict
    dossier: dict
    ident: set[str]
    receipt_to_message: dict[str, str]
    seq_of_message: dict[str, int]
    seq_of_index: dict[int, int]
    index_pointers: dict[str, list[str]]
    cited_by_message: dict[str, list[str]]
    message_of_index: dict[int, str]
    task_audit: Optional[OverseerAudit]
    notes: list[str] = field(default_factory=list)
    typed: dict[str, set[str]] = field(default_factory=dict)
    claim_entries: dict[str, list[tuple[Optional[str], Optional[str]]]] = field(default_factory=dict)
    _rerun: Optional[_Base] = None
    _rerun_done: bool = False

    # ------------------------------------------------------------------ identifiers
    def named_messages(self, ids: dict[str, list[str]]) -> set[str]:
        return set(ids["message_ids"]) | {self.receipt_to_message[r] for r in ids["receipt_ids"] if r in self.receipt_to_message}

    def named_transfers(self, ids: dict[str, list[str]]) -> set[str]:
        """Every transfer the accusation involves: the named messages and receipts, the transfers that carry a named claim,
        report or document, and the transfers that carry or cite a named result."""
        out = set(self.named_messages(ids))
        for name in ("claim_ids", "report_ids", "document_ids", "result_ids"):
            for i in ids[name]:
                for p in self.index_pointers.get(i, []):
                    if p.startswith("/transfers/"):
                        tok = p.split("/")[2]
                        mid = self.message_of_index.get(int(tok)) if tok.isdigit() else None
                        if mid:
                            out.add(mid)
        for rid in ids["result_ids"]:
            out.update(m for m, cited in self.cited_by_message.items() if rid in cited)
        return out

    def claim_reports(self, ids: dict[str, list[str]]) -> dict[str, list[str]]:
        """Each named claim id -> the reports it belongs to in the dossier: those of its entries the accusation's named
        reports select, else those on its named transfers, else every report carrying it."""
        msgs = self.named_messages(ids)
        named = set(ids.get("report_ids", ()))
        out: dict[str, list[str]] = {}
        for cid in ids.get("claim_ids", ()):
            entries = self.claim_entries.get(cid, [])
            cands = [e for e in entries if e[0] in named] or [e for e in entries if e[1] in msgs] or entries
            out[cid] = sorted({r for r, _m in cands if r})
        return out

    def target_results(self, ids: dict[str, list[str]]) -> list[str]:
        """The named results, or (none named) every result the named transfers cite."""
        if ids["result_ids"]:
            return list(ids["result_ids"])
        out: list[str] = []
        for mid in sorted(self.named_messages(ids)):
            out.extend(r for r in self.cited_by_message.get(mid, []) if r not in out)
        return out

    def first_seq(self, ids: dict[str, list[str]], pointers: Iterable[str]) -> Optional[int]:
        seqs = [self.seq_of_message[m] for m in self.named_messages(ids) if m in self.seq_of_message]
        for p in list(pointers) + [q for name in ("claim_ids", "report_ids", "document_ids", "result_ids") for i in ids[name] for q in self.index_pointers.get(i, [])]:
            s = _transfer_seq(p, self.seq_of_index)
            if s is not None:
                seqs.append(s)
        return min(seqs) if seqs else None

    # ------------------------------------------------------------------ bases
    def audit_base(self, a: Optional[OverseerAudit] = None) -> Optional[_Base]:
        a = a if a is not None else self.task_audit
        if a is None:
            return None
        agrees: set[str] = set()
        if a.scope == "task" and a.mode == "batch" and a.coverage.results_replay_pending == 0:
            bad = {f.formal_result_id for f in a.report.findings if f.code in ("OVS-RES-007", "OVS-RES-008", "OVS-RES-002") and f.formal_result_id}
            covered = {t.seq for t in self.view.transfers if t.message_id in set(a.message_ids)}
            agrees = _replayable(self.store, self.view.channel_uid, covered) - bad
        return _Base(source="task_audit", audit_id=a.audit_id, findings=list(a.report.findings), covered_messages=set(a.message_ids),
                     shadow_ran=a.coverage.shadow_run == "run", live_checked=False, degraded=a.coverage.degraded or a.scope != "task" or a.mode != "batch",
                     replay_agrees=agrees, pooled_claims=_pooled(self.view), translations=list(a.translations))

    def rerun(self, forced: Iterable[str], need_shadow: bool) -> Optional[_Base]:
        """The targeted re-run (once per verdict): force-replay ``forced`` results, then every check on the journal."""
        if self._rerun_done:
            return self._rerun
        self._rerun_done = True
        auditor = self.auditor
        uid = self.view.channel_uid
        try:
            journal = self.view.journal if self.view.journal is not None else auditor.journal(uid)
        except Exception:
            self.notes.append("the auditor holds no journal of this channel; no targeted re-run")
            return None
        outcomes = auditor.replayer.outcomes()
        submitted = []
        for rid in dict.fromkeys(forced):
            o = outcomes.get(rid)
            if o is not None:
                continue  # replayed already (decisively or not: the replayer runs a job once)
            job = _replay_job(self.view, self.store, rid, uid, 0)
            if job is not None and auditor.replayer.submit(job) in ("queued", "known"):
                submitted.append(rid)
        if submitted:
            auditor.replayer.drain(timeout_s=self.replay_timeout_s)
            self.notes.append(f"targeted re-run replayed {len(submitted)} named result(s) not replayed before")
        replays = _replays_of(auditor, uid)
        fresh = OverseerView.from_journal(journal, self.store)
        result = run_overseer_checks(fresh, keyring=self.keyring, store=self.store, live=self.live, registry=self.registry, replays=replays,
                                     batch=True, shadow=need_shadow, replay_mode=getattr(auditor, "replay_mode", "none"))
        self._rerun = _Base(source="rerun", audit_id=None, findings=[f for _s, f in result.findings], covered_messages=None,
                            shadow_ran=result.coverage.shadow_run == "run", live_checked=self.live is not None, degraded=result.coverage.degraded,
                            replay_agrees={rid for rid, r in replays.items() if classify(r) is None}, pooled_claims=_pooled(fresh), replays=replays,
                            translations=list(result.translations))
        return self._rerun


def _transfer_seq(pointer: str, seq_of_index: dict[int, int]) -> Optional[int]:
    if not pointer.startswith("/transfers/"):
        return None
    tok = pointer.split("/")[2]
    return seq_of_index.get(int(tok)) if tok.isdigit() else None


def _coverage_gap(kind: str, ids: dict[str, list[str]], base: _Base, ctx: _Ctx) -> Optional[str]:
    """None when the mapped checks ran with full coverage on the named identifiers; otherwise why they could not decide."""
    if base.degraded:
        return "the evidence is not a full batch audit of the journal (degraded view, or a live or transfer-scope audit)"
    msgs = ctx.named_transfers(ids)
    for f in base.findings:
        if f.code == "OVS-AUDIT-001":
            return "an audit check failed internally, so the checks did not all run"
        if f.code in ("OVS-AUDIT-002", "OVS-AUDIT-005") and (not f.message_ids or set(f.message_ids) & msgs):
            return "audit coverage was lost for the named transfers"
    if base.covered_messages is not None and msgs - base.covered_messages:
        return "the audit does not cover every named transfer"
    for mid in msgs:
        t = ctx.view.by_message.get(mid)
        if t is not None and t.digest_only:
            return "a named transfer is held digest-only in the journal"
    if kind in LIVE_KINDS and not base.live_checked:
        return "custody of the live objects was not re-checked (no live channel), so the custody checks could not decide"
    targets = ctx.target_results(ids)
    if kind == "replay_differs":
        if not targets:
            return "no result is named or cited by the named transfers"
        missing = [r for r in targets if r not in base.replay_agrees]
        if missing:
            return f"{len(missing)} named result(s) were not replayed decisively (not replayable, inconclusive, or not retained)"
    if kind in RESULT_KINDS:
        for f in base.findings:
            if f.code == "OVS-RES-002" and ((f.formal_result_id in targets) or set(f.related_result_ids) & set(targets)):
                return "a named result is not retained, so its content cannot be checked"
    if kind in ("contradiction_unnamed", "false_conflict") and any(f.code == "OVS-JOINT-002" for f in base.findings):
        return "the independent joint check was undecided, not buildable or over its limits"
    if kind == "contradiction_unnamed":
        claims = set(ids["claim_ids"])
        if not claims:
            return "no claim is named, so no engine check can compare claims"
        if claims - base.pooled_claims:
            return "a named claim is not formalized, so no engine check compares it with the others"
    if kind == "peer_document_altered":
        docs = set(ids["document_ids"])
        if any(f.code == "OVS-PEER-003" and ((set(f.document_ids) & docs) or (set(f.message_ids) & msgs)) for f in base.findings):
            return "the peer document is linked to its forward by text equality only"
    if kind in SHADOW_KINDS and not base.shadow_ran:
        return "the shadow channel did not run, so RCPT-004 and RCPT-008 were not decided"
    if kind in TRANSLATION_KINDS or (kind == "receipt_altered" and ids["claim_ids"]):
        gap = _translation_gap(kind, ids, base, ctx)
        if gap is not None:
            return gap
    return None


def _translation_gap(kind: str, ids: dict[str, list[str]], base: _Base, ctx: _Ctx) -> Optional[str]:
    """None when every check the kind needs ran on a checked translation of every named claim (on the named transfers and
    reports); otherwise why the translation checks could not decide."""
    claims = list(dict.fromkeys(ids["claim_ids"]))
    if not claims:
        return "no claim is named, so no translation check can be tied to the accusation"
    reports = set(ids["report_ids"])
    msgs = ctx.named_messages(ids)
    need = TRANSLATION_CHECKS_NEEDED.get(kind, ())
    for c in claims:
        recs = [r for r in base.translations if r.claim_id == c and (not reports or r.report_id in reports) and (not msgs or r.message_id in msgs)]
        if not recs:
            if kind == "receipt_altered":
                continue  # a claim without a translation: the receipt checks alone decide
            return f"no checked translation of claim {c} is on the named transfers (not translated, not delivered, or not named there)"
        for r in recs:
            missing = [x for x in need if x not in r.checks_run]
            if missing:
                return (f"the {', '.join(missing)} check(s) did not run on the translation of claim {c} (not model-proposed, recorded under "
                        "another policy version, no problem, or its result not retained), so the translation checks could not decide")
    return None


def _refuted_by(kind: str, ids: dict[str, list[str]], ctx: _Ctx) -> RefutedBy:
    if kind == "replay_differs":
        return "signed_result"
    if kind in RESULT_KINDS:
        for rid in ctx.target_results(ids):
            rec = ctx.store.get(rid)
            if rec is not None and rec.signature_ok_at_put:
                return "signed_result"
    return "deterministic_check"


def _resolve(acc, ctx: _Ctx) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    ids = accusation_identifiers(acc)
    # each list resolves against identifiers of its own type (the dossier index): a status word or a free text value that
    # happens to occur in the dossier is not a message id
    unresolved = {name: [i for i in ids[name] if i not in ctx.typed.get(name, ctx.ident)] for name in ID_FIELDS}
    unresolved = {k: v for k, v in unresolved.items() if v}
    faults: list[str] = []
    if not any(ids[name] for name in ID_FIELDS):
        faults.append("the accusation names no identifier (Evidence rule E1)")
    for name, vals in unresolved.items():
        faults.append(f"{len(vals)} identifier(s) in {name} are not {name[:-4].replace('_', ' ')} identifiers of the dossier (Evidence rule E3)")
    for k, ev in enumerate(acc.evidence):
        try:
            value = resolve_pointer(ctx.dossier, ev.pointer)
        except PointerError:
            faults.append(f"evidence {k}: the pointer does not resolve in the dossier (Evidence rule E5)")
            continue
        if ev.quote is not None and ev.quote not in visible_text(ctx.dossier, ev.pointer, value):
            faults.append(f"evidence {k}: the quote is not in the visible text of the field its pointer names (Evidence rule E6, E7)")
    return ids, unresolved, faults


def _accusation_finding(agent_id: str, verdict_ref: str, a: AccusationAssessment, ids: dict[str, list[str]], ctx: _Ctx,
                        deciding: tuple[Optional[str], list[str]] = (None, [])) -> IntegrityFinding:
    """The AGENT finding for one accusation. ``verdict_ref`` is the infrastructure's reference to the verdict (its intake
    message id); the accusation is named by its position in the verdict, never by the agent-chosen accusation id, so no
    agent text reaches a signed finding."""
    resolved = {k: [i for i in v if i not in a.unresolved_identifiers.get(k, [])] for k, v in ids.items()}
    if a.outcome == "confirmed" and a.covered_identifiers:
        resolved = {k: list(a.covered_identifiers.get(k, [])) for k in ids}  # AGENT-003 names only what the findings cover
    msgs = sorted(ctx.named_messages(resolved))
    base = f"accusation #{a.position + 1} ({a.kind}) of the verdict in intake message {verdict_ref} by agent {agent_id!r}"
    formal = None
    related: list[str] = []
    if a.outcome == "confirmed":
        refs = ", ".join(f"{r.code} in audit {r.audit_id}" for r in a.confirming[:6])
        text = f"{base} is confirmed by {refs}; the router acts on that finding, never on the agent's words"
        if a.remainder is not None:
            text += " (confirmed only for the transfers and claims those findings cover; the rest is assessed apart)"
        formal = next((r.formal_result_id for r in a.confirming if r.formal_result_id), None)
        related = [x for r in a.confirming for x in ([r.formal_result_id] if r.formal_result_id else []) + r.related_result_ids]
    elif a.outcome == "refuted":
        text = (f"{base} is refuted ({a.refuted_by}): the checks {', '.join(a.checks)} ran with full coverage on the named identifiers and found nothing; "
                "recorded against the agent")
        formal, related = deciding[0], list(deciding[1]) + list(resolved.get("result_ids", []))
    elif a.outcome == "unverifiable":
        text = f"{base} is unverifiable: " + "; ".join(a.reasons[:6])
    else:
        text = f"{base} is unresolved and goes to human review: " + "; ".join(a.reasons[:4])
    return ovs_finding(a.code, text, claim_ids=resolved.get("claim_ids", []), message_ids=msgs, report_ids=resolved.get("report_ids", []),
                       agent_ids=[agent_id], document_ids=resolved.get("document_ids", []), formal_result_id=formal, related_result_ids=related)


def _extra_accusation_findings(agent_id: str, verdict_ref: str, a: AccusationAssessment, ctx: _Ctx) -> list[IntegrityFinding]:
    """The remainder of a partly covered confirmation (AGENT-001 or AGENT-004 naming only the uncovered transfers and
    claims), and the resolution faults recorded beside a contradiction with a signed result (AGENT-002)."""
    out: list[IntegrityFinding] = []
    base = f"accusation #{a.position + 1} ({a.kind}) of the verdict in intake message {verdict_ref} by agent {agent_id!r}"
    r = a.remainder
    if r is not None:
        ids = {k: list(r.identifiers.get(k, [])) for k in ID_FIELDS}
        if r.outcome == "refuted":
            text = (f"{base} also names transfers or claims that no confirming finding covers; for those the checks ran with full coverage and found nothing "
                    f"({r.refuted_by}): recorded against the agent")
        else:
            text = f"{base} also names transfers or claims that no confirming finding covers, and no check decides them: " + "; ".join(r.reasons[:4])
        out.append(ovs_finding(r.code, text, claim_ids=ids.get("claim_ids", []), message_ids=sorted(ctx.named_messages(ids)), report_ids=ids.get("report_ids", []),
                               agent_ids=[agent_id]))
    if a.faults:
        out.append(ovs_finding("OVS-AGENT-002", f"{base} also carries identifiers or evidence that do not resolve: " + "; ".join(a.faults[:6]), agent_ids=[agent_id]))
    return out


def _engine_statement(es, ctx: _Ctx, position: int = 0) -> EngineStatementAssessment:
    """Assess one engine statement. A status asserted against a stored result of THIS channel is compared first: a
    mismatch is a contradiction (AGENT-001, ``signed_result`` when the signature verifies) whatever the pointer says, and
    a pointer that is not the result's status field is recorded beside it (``pointer_fault``, an extra AGENT-002)."""
    rid = es.result_id
    rec = ctx.store.get(rid)
    in_dossier = rid in (ctx.dossier.get("results") or {})
    base = dict(result_id=rid, asserted_status=es.asserted_status, pointer=es.pointer, position=position, known_result=in_dossier)
    if rec is None:
        if not in_dossier:
            return EngineStatementAssessment(**base, outcome="refuted", code="OVS-AGENT-001", refuted_by="signed_result",
                                             reason="no engine result with this id exists in the store or the dossier")
        return EngineStatementAssessment(**base, outcome="undecided", code="OVS-AGENT-004", reason="the result is no longer retained")
    same_channel = getattr(rec, "channel_uid", None) == ctx.view.channel_uid
    stored = rec.status
    verified = bool(rec.signature_ok_at_put)
    if isinstance(rec, StoredResult):
        parsed = ctx.store.parsed(rid)
        verified = verified and parsed is not None and ctx.keyring.verify_result(parsed)[0]
    points = _points_at_status_of(ctx.dossier, es.pointer, rid)
    if same_channel and es.asserted_status != stored:
        fault = None if points else (f"the pointer is not the status field of the result (Evidence rule E10: /results/<result_id>/status)")
        if not in_dossier:
            fault = (fault + "; " if fault else "") + "the result is not one of this dossier's results (Evidence rule E3)"
        return EngineStatementAssessment(**base, outcome="refuted", code="OVS-AGENT-001", stored_status=stored, signature_verified=verified,
                                         refuted_by="signed_result" if verified else "deterministic_check",
                                         reason=f"the stored result's status is {stored}", pointer_fault=fault)
    if not in_dossier or not same_channel:
        return EngineStatementAssessment(**base, outcome="unverifiable", code="OVS-AGENT-002",
                                         reason="the result is not one of this dossier's results (Evidence rule E1, E3: identifiers come from the dossier)")
    if not points:
        return EngineStatementAssessment(**base, outcome="unverifiable", code="OVS-AGENT-002",
                                         reason="the pointer is not the status field of the result (Evidence rule E10: /results/<result_id>/status)")
    try:
        value = resolve_pointer(ctx.dossier, es.pointer)
    except PointerError:
        return EngineStatementAssessment(**base, outcome="unverifiable", code="OVS-AGENT-002", stored_status=stored, signature_verified=verified,
                                         reason="the pointer does not resolve in the dossier (Evidence rule E10)")
    if value != es.asserted_status:
        return EngineStatementAssessment(**base, outcome="unverifiable", code="OVS-AGENT-002", stored_status=stored, signature_verified=verified,
                                         reason="the field the pointer names does not hold the asserted status (Evidence rule E10)")
    return EngineStatementAssessment(**base, outcome="agrees", stored_status=stored, signature_verified=verified,
                                     reason="" if verified else "the stored result's signature does not verify; the status is the journaled one")


def _points_at_status_of(dossier: dict, pointer: str, rid: str) -> bool:
    """The pointer names the ``status`` field of the result ``rid``: ``/results/<rid>/status``, or a ``status`` member of
    an object of the dossier whose ``result_id`` is ``rid`` (a receipt's copy of the result)."""
    from .dossier import pointer_join
    if pointer == pointer_join("results", rid, "status"):
        return True
    if not pointer.endswith("/status"):
        return False
    try:
        parent = resolve_pointer(dossier, pointer[: -len("/status")])
    except PointerError:
        return False
    return isinstance(parent, dict) and parent.get("result_id") == rid


def _engine_statement_finding(agent_id: str, verdict_ref: str, e: EngineStatementAssessment) -> list[IntegrityFinding]:
    """The AGENT finding(s) for one engine statement. The result id is shown only when it is one of this dossier's results;
    any other id is agent text and is shown as a digest (it could carry instructions)."""
    shown = e.result_id if e.known_result else f"<unknown result {agent_label(e.result_id)}>"
    base = f"engine statement #{e.position + 1} on result {shown} in the verdict of intake message {verdict_ref} by agent {agent_id!r}"
    if e.outcome == "refuted":
        text = f"{base} asserts {e.asserted_status}, refuted ({e.refuted_by}): {e.reason}"
    elif e.outcome == "unverifiable":
        text = f"{base} is unverifiable: {e.reason}"
    else:
        text = f"{base} could not be decided: {e.reason}"
    out = [ovs_finding(e.code, text, agent_ids=[agent_id], formal_result_id=e.result_id if e.outcome == "refuted" and e.stored_status else None)]
    if e.pointer_fault:
        out.append(ovs_finding("OVS-AGENT-002", f"{base} also does not resolve as written: {e.pointer_fault}", agent_ids=[agent_id]))
    return out


def _invalid(message: Any, *, view: OverseerView, reason: str, detail: str, verdict: Optional[AgentVerdict] = None, notes: Iterable[str] = ()) -> VerdictAssessment:
    agent = getattr(message, "sender_agent_id", None) or (verdict.agent_id if verdict is not None else "unknown")
    task = getattr(message, "task_id", None) or (verdict.task_id if verdict is not None else view.task_id or "unknown")
    mid = getattr(message, "message_id", None)
    f = ovs_finding("OVS-AGENT-005", f"the verdict envelope {mid!r} of agent {agent!r} fails the binding re-check ({reason}): {detail}; it is discarded",
                    agent_ids=[agent], message_ids=[mid] if isinstance(mid, str) else [])
    return VerdictAssessment(assessment_id=uuid.uuid4().hex, intake_message_id=mid if isinstance(mid, str) else None,
                             verdict_id=verdict.verdict_id if verdict is not None else None, agent_id=str(agent), task_id=str(task), channel_uid=view.channel_uid,
                             pack=verdict.pack if verdict is not None else None, valid=False, invalid_reason=reason, findings=[f], notes=list(notes),
                             created_at=_now())


def _same_keys(a: KeyRing, b: KeyRing) -> bool:
    return a is b or all(hmac.compare_digest(a.subkey(label), b.subkey(label)) for label in ("audit", "intake", "runs"))


def validate_overseer_verdict(message: AgentMessage, view: OverseerView, store: ResultStore, task_audit: Optional[OverseerAudit], auditor: Any = None, *,
                              intake: VerdictIntake, live: Any = None, registry: Any = None, replay_timeout_s: float = 30.0) -> VerdictAssessment:
    """Assess one verdict envelope (see the module docstring). Never obeys the verdict; raises only on caller errors
    (a view, audit or auditor that belongs to another channel or key configuration)."""
    keyring = intake.keyring
    if auditor is not None and not _same_keys(auditor.keyring, keyring):
        raise ValueError("the auditor and the intake are configured with different overseer secrets")
    if task_audit is not None and task_audit.channel_uid != view.channel_uid:
        raise ValueError("the task audit belongs to another channel than the view")
    if live is None:
        live = getattr(view, "channel", None)
    if registry is None:
        registry = getattr(live, "registry", None) or getattr(auditor, "registry", None)
    # ------------------------------------------------------------------ binding re-check
    audit_ok = task_audit is not None and verify_audit(task_audit, keyring) and task_audit.scope in ("task", "transfer")

    def invalid(reason: str, detail: str, verdict: Optional[AgentVerdict] = None) -> VerdictAssessment:
        a = _invalid(message, view=view, reason=reason, detail=detail, verdict=verdict)
        a.task_audit_id = task_audit.audit_id if task_audit is not None else None
        reference = task_audit if audit_ok else None
        a.audit = build_verdicts_audit(reference=reference, channel_uid=view.channel_uid, task_id=a.task_id, request_id=view.request_id,
                                       findings=list(a.findings), keyring=keyring, message_ids=list(reference.message_ids) if reference is not None else [],
                                       notes=_audit_notes(task_audit, None, [a], assessment_digest(a)))
        return a

    ok, why = intake.check_message(message)
    if not ok:
        return invalid(why, "the envelope is not the one the intake signed and accepted")
    try:
        verdict = AgentVerdict.model_validate(message.payload)
    except ValidationError:
        return invalid("schema", "the payload does not validate against overseer_verdict/1.0")
    accepted = intake.accepted(message.message_id)
    issue = accepted.issue
    for name, reason in (("agent_id", "agent_mismatch"), ("task_id", "task_mismatch"), ("dossier_sha256", "dossier_mismatch"), ("lens", "lens_mismatch")):
        if getattr(verdict, name) != getattr(issue, name):
            return invalid(reason, f"the verdict's {name} differs from the issue record", verdict)
    if message.sender_agent_id != issue.agent_id:
        return invalid("agent_mismatch", "the envelope's sender is not the agent the dossier was issued to", verdict)
    if verdict.pack not in intake.accepted_packs:
        return invalid("pack_unknown", "the verdict names a pack the intake does not accept", verdict)
    if verdict.pack != issue.pack:
        return invalid("pack_mismatch", "the verdict names another pack than its dossier's", verdict)
    if issue.channel_uid != view.channel_uid:
        raise ValueError("the view belongs to another channel than the dossier the verdict answers")
    # ------------------------------------------------------------------ context
    dossier = intake.dossier_for(issue)
    notes: list[str] = []
    if task_audit is not None and not audit_ok:
        notes.append("the task audit does not verify under the audit key (or is not a task or transfer audit); it was not used")
    r2m, seq_m, seq_i, cited_m, mid_i = {}, {}, {}, {}, {}
    for i, tr in enumerate(dossier.get("transfers") or []):
        seq_i[i] = tr.get("seq")
        if tr.get("message_id"):
            mid_i[i] = tr["message_id"]
            seq_m[tr["message_id"]] = tr.get("seq")
            cited_m[tr["message_id"]] = list(tr.get("cited_result_ids") or [])
            if tr.get("receipt_id"):
                r2m[tr["receipt_id"]] = tr["message_id"]
    index_pointers: dict[str, list[str]] = {}
    typed = typed_identifiers(dossier)
    claim_entries: dict[str, list[tuple[Optional[str], Optional[str]]]] = {}
    messages_of_claim: dict[tuple[str, str], set[str]] = {}
    report_of_message: dict[str, set[str]] = {}
    for e in dossier.get("index") or []:
        index_pointers.setdefault(e.get("id"), []).append(e.get("pointer"))
        p = e.get("pointer") or ""
        tok = p.split("/")[2] if p.startswith("/transfers/") and len(p.split("/")) > 2 else ""
        e_mid = mid_i.get(int(tok)) if tok.isdigit() else None
        if e.get("type") in ("claim", "synthesized_claim"):
            claim_entries.setdefault(e.get("id"), []).append((e.get("report_id"), e_mid))
            if e_mid:
                messages_of_claim.setdefault((e.get("report_id") or "", e.get("id")), set()).add(e_mid)
                messages_of_claim.setdefault(("", e.get("id")), set()).add(e_mid)
        elif e.get("type") == "report" and e_mid:
            report_of_message.setdefault(e_mid, set()).add(e.get("id"))
    latest: Optional[OverseerAudit] = None
    if auditor is not None:
        try:
            auditor.journal(view.channel_uid)
            tasks = [x for x in auditor.audits(view.channel_uid) if x.scope == "task"]
        except Exception:
            notes.append("the auditor does not observe this channel; no targeted re-run is possible")
            auditor, tasks = None, []
        if tasks and (not audit_ok or tasks[-1].audit_id != task_audit.audit_id) and verify_audit(tasks[-1], keyring):
            latest = tasks[-1]  # a newer task audit than the one given (an earlier verdict's re-run, or a later batch audit)
            notes.append(f"the auditor's latest task audit {latest.audit_id} was consulted too")
    ctx = _Ctx(view=view, store=store, keyring=keyring, intake=intake, auditor=auditor, live=live, registry=registry, replay_timeout_s=replay_timeout_s,
               verdict=verdict, dossier=dossier, ident=dossier_identifiers(dossier), receipt_to_message=r2m, seq_of_message=seq_m, seq_of_index=seq_i,
               index_pointers=index_pointers, cited_by_message=cited_m, message_of_index=mid_i, task_audit=task_audit if audit_ok else None, notes=notes,
               typed=typed, claim_entries=claim_entries)
    given = ctx.audit_base()
    lookups = [b for b in (given, ctx.audit_base(latest) if latest is not None else None) if b is not None]
    # ------------------------------------------------------------------ accusations: resolve and look up
    results: list[AccusationAssessment] = []
    idmap: dict[str, dict[str, list[str]]] = {}
    crmap: dict[str, dict[str, list[str]]] = {}
    pending: list[AccusationAssessment] = []
    faulted: dict[str, list[str]] = {}  # key -> resolution faults of a result accusation assessed on its resolved identifiers
    remainders: dict[str, AccusationAssessment] = {}  # parent accusation id -> the provisional assessment of its uncovered part

    def split_off(a: AccusationAssessment, ids: dict[str, list[str]], matched: list[IntegrityFinding]) -> None:
        """Confirm ``a`` only for what ``matched`` covers; queue the uncovered remainder as a pending assessment of its own."""
        covered, rest = coverage_split(ids, matched, r2m, crmap[a.accusation_id], report_of_message, messages_of_claim)
        a.covered_identifiers = covered
        if not rest:
            return
        key = a.accusation_id + "\u0000remainder"
        rem_crep = {c: v for c, v in crmap[a.accusation_id].items() if c in rest["claim_ids"]}
        idmap[key], crmap[key] = rest, rem_crep
        rem = AccusationAssessment(accusation_id=key, kind=a.kind, claimed_severity=a.claimed_severity, outcome="unresolved", code=OUTCOME_CODES["unresolved"],
                                   checks=list(a.checks), identifiers=rest, claim_report_ids=rem_crep, position=a.position)
        remainders[a.accusation_id] = rem
        pending.append(rem)

    for pos, acc in enumerate(verdict.accusations):
        ids, unresolved, faults = _resolve(acc, ctx)
        idmap[acc.accusation_id] = ids
        crep = ctx.claim_reports(ids)
        crmap[acc.accusation_id] = crep
        checks = list(KIND_CHECKS.get(acc.kind, ()))
        common = dict(accusation_id=acc.accusation_id, kind=acc.kind, claimed_severity=acc.claimed_severity, checks=checks, identifiers=ids,
                      unresolved_identifiers=unresolved, first_seq=ctx.first_seq(ids, [e.pointer for e in acc.evidence]), claim_report_ids=crep, position=pos)
        if faults:
            resolved_ids = {k: [i for i in v if i not in unresolved.get(k, [])] for k, v in ids.items()}
            if acc.kind in RESULT_KINDS and any(resolved_ids.get(n) for n in ID_FIELDS):
                # a contradiction with a signed result is never hidden behind an invented identifier or a bad pointer: the
                # named results that DO resolve are assessed; only a refutation by a signed result stands (with an AGENT-002)
                a = AccusationAssessment(**common, outcome="unverifiable", code=OUTCOME_CODES["unverifiable"], reasons=faults)
                idmap[acc.accusation_id] = resolved_ids
                crmap[acc.accusation_id] = ctx.claim_reports(resolved_ids)
                faulted[acc.accusation_id] = faults
                results.append(a)
                pending.append(a)
                continue
            results.append(AccusationAssessment(**common, outcome="unverifiable", code=OUTCOME_CODES["unverifiable"], reasons=faults))
            continue
        if acc.kind in UNCHECKED_KINDS:
            why = ("kind translation_unfaithful is decided by no check: whether an IR says what its claim says is a question of meaning, "
                   "advisory only; human review") if acc.kind == "translation_unfaithful" else f"kind {acc.kind} is decided by no check; human review"
            results.append(AccusationAssessment(**common, outcome="unresolved", code=OUTCOME_CODES["unresolved"], reasons=[why]))
            continue
        matched_pairs = [(b, i, f) for b in lookups for i, f in enumerate(b.findings) if finding_matches(acc.kind, ids, f, r2m, crep)]
        if matched_pairs:
            a = AccusationAssessment(**common, outcome="confirmed", code=OUTCOME_CODES["confirmed"], confirming=[_ref(b.audit_id, i, f) for b, i, f in matched_pairs],
                                     reasons=["confirmed by a finding of the task audit"])
            results.append(a)
            split_off(a, ids, [f for _b, _i, f in matched_pairs])
            continue
        a = AccusationAssessment(**common, outcome="unresolved", code=OUTCOME_CODES["unresolved"])
        results.append(a)
        pending.append(a)
    # ------------------------------------------------------------------ targeted re-run, refutation
    superseding: Optional[OverseerAudit] = None
    deciding: dict[str, tuple[Optional[str], list[str]]] = {}
    if pending:
        base = given
        if auditor is not None:
            forced = [r for a in pending if a.kind == "replay_differs" for r in ctx.target_results(idmap[a.accusation_id])]
            base = ctx.rerun(forced, need_shadow=any(a.kind in SHADOW_KINDS for a in pending)) or given
        to_confirm: list[AccusationAssessment] = []
        for a in pending:
            ids = idmap[a.accusation_id]
            is_faulted = a.accusation_id in faulted
            if base is None:
                a.reasons = (a.reasons if is_faulted else []) + ["no verified task audit and no auditor to re-run the checks"]
                continue
            matched = [f for f in base.findings if finding_matches(a.kind, ids, f, r2m, crmap[a.accusation_id])]
            if is_faulted and matched:
                continue  # an accusation with invented identifiers is never confirmed: it stays unverifiable
            if matched and base.source == "rerun":
                to_confirm.append(a)
                continue
            if matched:  # cannot happen for the given audit (looked up above); kept for safety
                a.outcome, a.code = "confirmed", OUTCOME_CODES["confirmed"]
                a.confirming = [_ref(base.audit_id, i, f) for i, f in enumerate(base.findings) if finding_matches(a.kind, ids, f, r2m, crmap[a.accusation_id])]
                continue
            gap = _coverage_gap(a.kind, ids, base, ctx)
            if gap is None:
                refuted_by = _refuted_by(a.kind, ids, ctx)
                if is_faulted and refuted_by != "signed_result":
                    continue  # only a contradiction with a signed result stands beside the resolution faults
                a.outcome, a.code = "refuted", OUTCOME_CODES["refuted"]
                a.refuted_by = refuted_by
                if a.refuted_by == "signed_result":
                    targets = ctx.target_results(ids)
                    replays = [base.replays[r].replay_result_id for r in targets if r in base.replays and base.replays[r].replay_result_id]
                    deciding[a.accusation_id] = (targets[0] if targets else None, replays)
                a.decided_by_rerun = base.source == "rerun"
                a.reasons = [f"the checks ran with full coverage on the named identifiers ({base.source}) and found nothing"]
                if is_faulted:
                    a.faults = list(faulted[a.accusation_id])
                    a.reasons.append("the accusation's other identifiers or evidence do not resolve (recorded as OVS-AGENT-002)")
            elif not is_faulted:
                a.reasons = [gap]
                a.decided_by_rerun = base.source == "rerun"
        if to_confirm:
            prior = latest if latest is not None else (task_audit if audit_ok else None)
            prior_final = bool(prior.final) if prior is not None else False
            superseding = auditor.audit(view.channel_uid, final=prior_final, shadow=True)
            ok_new = verify_audit(superseding, keyring)
            if prior is not None and superseding.supersedes != prior.audit_id:
                notes.append(f"the new task audit supersedes {superseding.supersedes!r}, not {prior.audit_id!r}")
            for a in to_confirm:
                ids = idmap[a.accusation_id]
                matched_new = [(i, f) for i, f in enumerate(superseding.report.findings) if finding_matches(a.kind, ids, f, r2m, crmap[a.accusation_id])] if ok_new else []
                a.decided_by_rerun = True
                if matched_new:
                    a.outcome, a.code, a.confirming = "confirmed", OUTCOME_CODES["confirmed"], [_ref(superseding.audit_id, i, f) for i, f in matched_new]
                    a.reasons = ["confirmed by the targeted re-run; the auditor issued a new signed task audit containing the finding"]
                    a.covered_identifiers, _rest = coverage_split(ids, [f for _i, f in matched_new], r2m, crmap[a.accusation_id], report_of_message, messages_of_claim)
                else:
                    a.reasons = ["the targeted re-run found a matching finding but the auditor's signed task audit does not reproduce it"]
    # the uncovered remainder of each partly covered confirmation: confirmed by the re-run (then the whole accusation is),
    # or kept beside the confirmation as refuted or unresolved (it never rides on another transfer's finding)
    for a in results:
        rem = remainders.get(a.accusation_id)
        if rem is None:
            continue
        if rem.outcome == "confirmed":
            a.confirming = list(a.confirming) + list(rem.confirming)
            a.covered_identifiers = {k: list(dict.fromkeys(list(a.covered_identifiers.get(k, [])) + list(rem.covered_identifiers.get(k, []) or rem.identifiers.get(k, []))))
                                     for k in ID_FIELDS}
            continue
        a.remainder = RemainderAssessment(identifiers=rem.identifiers, outcome=rem.outcome, code=rem.code, refuted_by=rem.refuted_by, reasons=list(rem.reasons))
    # ------------------------------------------------------------------ engine statements, findings, signed audit
    statements = [_engine_statement(es, ctx, k) for k, es in enumerate(verdict.engine_statements)]
    vref = message.message_id
    findings = []
    for a in results:
        findings.append(_accusation_finding(verdict.agent_id, vref, a, a.identifiers if a.accusation_id not in faulted else idmap[a.accusation_id], ctx,
                                            deciding.get(a.accusation_id, (None, []))))
        findings += _extra_accusation_findings(verdict.agent_id, vref, a, ctx)
    for e in statements:
        if e.code is not None:
            findings += _engine_statement_finding(verdict.agent_id, vref, e)
    assessment = VerdictAssessment(
        assessment_id=uuid.uuid4().hex, intake_message_id=message.message_id, verdict_id=verdict.verdict_id, agent_id=verdict.agent_id,
        task_id=verdict.task_id, request_id=issue.request_id, channel_uid=view.channel_uid, lens=verdict.lens, mode=issue.mode, pack=verdict.pack,
        dossier_sha256=verdict.dossier_sha256, valid=True, task_audit_id=task_audit.audit_id if task_audit is not None else None,
        superseding_audit_id=superseding.audit_id if superseding is not None else None, transfers_reviewed=list(verdict.transfers_reviewed),
        accusations=results, engine_statements=statements, findings=findings, notes=notes, created_at=_now())
    reference = superseding if superseding is not None else (latest if latest is not None else (task_audit if audit_ok else None))
    assessment.audit = build_verdicts_audit(reference=reference, channel_uid=view.channel_uid, task_id=assessment.task_id, request_id=assessment.request_id,
                                            findings=findings, keyring=keyring, message_ids=[m for m in seq_m],
                                            notes=_audit_notes(task_audit, superseding, [assessment], assessment_digest(assessment)))
    return assessment


def _audit_notes(task_audit: Optional[OverseerAudit], superseding: Optional[OverseerAudit], assessments: list, digest: str) -> list[str]:
    notes = []
    if task_audit is not None:
        notes.append(f"references task audit {task_audit.audit_id}")
    else:
        notes.append("no task audit was given: transfer states are not stated by this audit")
    if superseding is not None:
        notes.append(f"targeted re-run issued task audit {superseding.audit_id}, superseding {superseding.supersedes}")
    for a in assessments:
        pk = f"{a.pack.name} {a.pack.version} {a.pack.sha256}" if a.pack is not None else "none"
        vref = agent_label(a.verdict_id) if a.verdict_id else "none"
        notes.append(f"verdict {vref} (intake message {a.intake_message_id}) of agent {a.agent_id} (valid {a.valid}) under pack {pk}")
    notes.append(f"assessment sha256 {digest}")
    notes.append("OVS-AGENT-* findings never change a transfer's clearance; an agent's verdict is advisory and decides nothing")
    return notes


def build_verdicts_audit(*, reference: Optional[OverseerAudit], channel_uid: str, task_id: str, request_id: str, findings: list[IntegrityFinding],
                         keyring: KeyRing, message_ids: list[str], notes: list[str]) -> OverseerAudit:
    """A signed audit of scope ``verdicts`` carrying ``OVS-AGENT-*`` findings. Its state and transfer states are copied
    unchanged from ``reference`` (the task audit the verdicts were assessed against): agent findings never change a
    clearance. Without a reference task audit the state is AUDIT_PENDING and no transfer state is stated."""
    state: ClearanceState = reference.state if reference is not None else "AUDIT_PENDING"
    states = dict(reference.transfer_states) if reference is not None else {}
    formal = list(dict.fromkeys([f.formal_result_id for f in findings if f.formal_result_id] + [r for f in findings for r in f.related_result_ids]))
    report = IntegrityReport(report_id=uuid.uuid4().hex, request_id=request_id or "unknown", task_id=task_id or "unknown", checks_run=["verdicts"],
                             findings=list(findings), formal_result_ids=formal, created_at=_now())
    report.report_sha256 = report_digest(report)
    audit = OverseerAudit(audit_id=uuid.uuid4().hex, supersedes=None, scope="verdicts", mode="batch", final=False, state=state, task_id=task_id or "unknown",
                          request_id=request_id or "unknown", channel_uid=channel_uid, message_ids=list(message_ids), transfer_states=states,
                          journal_head=reference.journal_head if reference is not None else None,
                          store_digest=reference.store_digest if reference is not None else sha256_hex(""), report=report,
                          coverage=AuditCoverage(transfers=len(message_ids), notes=list(notes)), key_ids_used=[INTAKE_KEY_ID], created_at=_now())
    return sign_audit(audit, keyring)
