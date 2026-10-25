"""The delivery policy: a four-minute formal path, then an overseer-selected fallback above 90% accuracy, else withheld.

The founder's requirement (``docs/DELIVERY.md``): the Z3 logic code must translate an answer completely within four
minutes; if it does not, the overseer agents check the candidate outputs and the one with the highest accuracy is
delivered, but only when that accuracy is above 90%. This module decides, for ONE deliverable (a specialist answer, or
the consolidated response when several agents answered the same input), which of four things happens, and records why
in a signed :class:`DeliveryReceipt` (contract ``delivery_receipt/1.0``, key id ``overseer-delivery``):

* ``formally_checked``: within ``translation_budget_s`` (default 240 s, the founder's limit; an injectable monotonic
  clock measures it) every material eligible claim of the deliverable reached a definitive, clean outcome: translated
  (TRANSLATED, no ambiguity flag), the engine's display status the positive verdict of its query, and the release rule
  ``release-v1`` re-derived here from the journaled translation and signed result (the engine's release check under the
  auditor's verification key, every relied-on premise established so no premise authority is unresolved, no failed
  grounding check or partial reference, no retry that changed the claim, and a current ``faithful`` fidelity review made
  with the evidence); the receipt carries no error-level finding, every branch formal check of the report's own
  statements holds, the overseer's translation checks (``OVS-TRN-*``) name none of the deliverable's material claims, the
  task audit names it in no error, the consolidation allows its delivery and the transfer's clearance lets the router
  act (``policy.may_act``). Results prove properties of the encoding only.
* ``overseer_selected``: the formal path did not complete (the budget ran out, or a claim ended unresolved, refuted or
  not attempted). The overseer agents review the task through the package's runner, built from the exported knowledge
  pack, sized by the self-duplicating pool (``hub.review_pool``: one instance by default, two for a repeated fault, never
  past the maximum), and every verdict is validated exactly as in production (``validate_overseer_verdict``). For every
  candidate answer (every answer to the input the channel delivered; with duplicated instances the consolidation's
  groups order them) the policy computes an ACCURACY: the share of its material claims that the validated verdicts
  confirm accurate. A claim counts as accurate only when at least one counted verdict examined its transfer
  (``transfers_reviewed``) and pins down no fault on it, no counted verdict accuses it in a way a check confirmed or
  left unresolved, no deterministic check (an error-level receipt or task-audit finding) names it, and no signed engine
  result refutes it. A verdict that contradicts a signed engine result (an engine statement refuted, or an accusation
  refuted by a signed result) is rejected: none of its reviews counts. A claim refuted by a signed engine result
  (COUNTEREXAMPLE, INCONSISTENT_PREMISES, UNSATISFIABLE, displayed so; or an error-level check citing a signed result) is
  inaccurate; an unassessed claim is never accurate. The candidate with the highest accuracy is delivered only when that
  accuracy is ABOVE ``min_selected_accuracy`` (default 0.90, strictly greater; the founder's threshold is a floor an
  operator may raise, never lower); ties go to the consolidation's canonical choice. A candidate whose material claim a
  signed engine result refutes is never delivered while another candidate has none, and, stricter than the founder's
  rule, a candidate a deterministic check faults is never delivered while another candidate has no such fault. A
  candidate must also pass the integrity gates: delivered by the channel, not excluded by the consolidation (an
  error-level finding on its receipt or in the task audit, a clearance not passed, a repeated fault: the consolidation's
  own rule that an excluded answer is never delivered), a clearance the router may act on at the moment of selection,
  and a journaled payload that carries its envelope's digest. A translation that failed (invalid, unsupported,
  ambiguous, undecided, not attempted) is a warning on the receipt, never an exclusion: it is what the fallback is for.
* ``not_checked``: only when the operator configured ``on_overseer_timeout="deliver_canonical_not_checked"`` and the
  overseer stage could not establish any accuracy (its own ``overseer_budget_s`` ran out, it failed, or no overseer
  agent is configured): the consolidation's canonical answer, when it passes the integrity gates, labelled NOT CHECKED.
* ``withheld``: everything else, with the scores and the reasons. Never delivered as selected.

**Honest labels.** The mode travels in the signed receipt and in the delivered payload (:class:`DeliveredAnswer`,
contract ``delivered_answer/1.0``). Only ``formally_checked`` says so; every other label says it is NOT formally checked
and NOT verified. An overseer verdict is advisory: the selection is an advisory choice among checked candidates, never a
verification, and an agent's semantic assertion (``translation_unfaithful``, ``other``) only lowers a score.

**The fallback never edits.** The delivered payload is the journaled payload of the chosen answer, byte for byte (its
digest is the envelope's): no claim is edited, no number widened, no premise added, no difficult claim dropped, and
nothing is translated again (the external review's warning against repairing toward entailment).

**Timing.** :meth:`DeliveryPolicy.start` opens the formal stage when the deliverable's first answer reaches the hub;
:meth:`DeliverySession.install` puts a deadline-bound verifier on the channel (a claim not started before the deadline
gets no outcome, ``skipped_budget``; one that finishes after it is ``late``); :meth:`DeliverySession.decide` evaluates
the formal path, runs the fallback when needed, and records the time to decision, the translation (formal stage) time
and the overseer time on the receipt. The overseer stage has its own deadline: a provider call started after it is not
made, and a reply that arrives after it is not counted.

Trust rule: the policy decides from the journal, the signed task audits, the signed engine results and the validated
verdicts only; agent text is data and never reaches a label, a reason or a finding.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import inspect
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Callable, Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ..engine.provenance import signature_matches
from ..engine.release import POSITIVE_STATUS, release_check
from ..engine.statuses import SCOPE_STATEMENT, VerificationStatus as S, is_definitive
from ..integrity.contracts import payload_hash
from ..ir.canonical import canonical_json, sha256_hex
from ..translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, TaskRecord, TranslationStatus
from ..translate.eligibility import decide_eligibility
from ..translate.outcome import assess_release, display_status_for
from ..translate.pipeline import apply_subject_policy
from ..translate.providers.base import ProviderError
from ..translate.review import review_currency
from ..translate.subjects import resolve_profile
from .audit import verify_audit
from .codes import is_agent_code
from .consolidate import DELIVERABLE_STATUSES, ConsolidatedResponse, delivery_decision, material_claims, select_requests
from .keys import DELIVERY_KEY_ID, KeyRing
from .policy import MAX_PENDING_WAIT_MS, act_decision
from .pool import OverseerPool, PoolConfig
from .view import RESPONSE_KINDS, OverseerView, Transfer

__all__ = [
    "DELIVERY_CONTRACT", "DELIVERED_ANSWER_CONTRACT", "DELIVERY_POLICY_VERSION", "FOUNDER_TRANSLATION_BUDGET_S", "FOUNDER_MIN_SELECTED_ACCURACY",
    "DEFAULT_OVERSEER_BUDGET_S", "DELIVERY_MODES", "DeliveryMode", "REFUTING_STATUSES", "DELIVERY_SCOPE_SENTENCE", "DELIVERY_SCOPE_STATEMENT",
    "DeliveryConfig", "ClaimTiming", "TranslationStage", "DeadlineVerifier", "ClaimFormal", "BranchCheck", "FormalPath", "ClaimAccuracy",
    "CandidateAssessment", "VerdictStanding", "OverseerStage", "Fallback", "DeliveryReceipt", "DeliveredAnswer", "DeliveryDecision",
    "DeliverySession", "DeliveryPolicy", "sign_delivery_receipt", "verify_delivery_receipt", "delivery_receipt_digest", "verify_delivered_answer",
    "accuracy_above", "is_fallback_label_honest",
]

DELIVERY_CONTRACT = "delivery_receipt/1.0"
DELIVERED_ANSWER_CONTRACT = "delivered_answer/1.0"
#: The policy's version (bump on any change to the rules of this module).
DELIVERY_POLICY_VERSION = "delivery-v1"
#: The founder's translation budget: four minutes.
FOUNDER_TRANSLATION_BUDGET_S = 240.0
#: The founder's threshold: a selected answer's accuracy must be ABOVE it (a floor; an operator may only raise it).
FOUNDER_MIN_SELECTED_ACCURACY = 0.90
#: The overseer stage's own default budget (configurable; four minutes, like the translation budget).
DEFAULT_OVERSEER_BUDGET_S = 240.0
DeliveryMode = Literal["formally_checked", "overseer_selected", "not_checked", "withheld"]
DELIVERY_MODES: tuple[str, ...] = ("formally_checked", "overseer_selected", "not_checked", "withheld")
#: Display statuses by which a signed engine result says a claim's encoding does not hold.
REFUTING_STATUSES = frozenset({S.COUNTEREXAMPLE, S.INCONSISTENT_PREMISES, S.UNSATISFIABLE})
DELIVERY_SCOPE_SENTENCE = (
    "This delivery decision records which path decided the answer and why. FORMALLY CHECKED means that, within the "
    "translation budget, every material eligible claim was translated, decided positively by the engine as encoded and "
    "passed the release rule, and the transfer audit cleared the answer: it proves properties of the encodings only. An "
    "OVERSEER-SELECTED answer was chosen among the candidate answers by the overseer agents' validated review, which is "
    "advisory: it is not formally checked and not verified. A NOT CHECKED answer was delivered by the operator's "
    "configuration without any accuracy established. A WITHHELD answer is not delivered."
)
DELIVERY_SCOPE_STATEMENT = SCOPE_STATEMENT + " " + DELIVERY_SCOPE_SENTENCE
_PASSED = frozenset({"AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"})
_SIGNATURE_FIELDS = ("signature", "signature_key_id")
_REASON_CHARS = 600
_MAX_LISTED = 8
Clock = Callable[[], float]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cut(text: str, n: int = _REASON_CHARS) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _listed(items: Sequence[str], n: int = _MAX_LISTED) -> str:
    items = list(items)
    shown = ", ".join(items[:n])
    return shown + (f" and {len(items) - n} more" if len(items) > n else "")


def _accepts_task(fn: Any) -> bool:
    """Whether a verifier declares a ``task`` parameter (or ``**kwargs``): the channel's own rule (``bus._accepts_task``)."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "task" and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) or p.kind is p.VAR_KEYWORD for p in params)


def accuracy_above(accurate: int, total: int, threshold: float) -> bool:
    """``accurate / total > threshold``, decided exactly (no floating-point comparison: 9 of 10 is 0.90, never above it).
    An answer with no material claim has no accuracy and is never above any threshold."""
    if total <= 0:
        return False
    return Fraction(accurate, total) > Fraction(str(threshold))


# ============================================================================================ configuration
class DeliveryConfig(BaseModel):
    """The policy's fixed configuration. ``min_selected_accuracy`` is the founder's threshold (0.90) or a stricter one;
    a selected answer must be strictly above it. ``on_overseer_timeout`` says what happens when the overseer stage
    establishes no accuracy (its budget ran out, it failed, or no overseer agent is configured): ``withhold`` (the
    default) or ``deliver_canonical_not_checked`` (the consolidation's canonical answer, labelled NOT CHECKED)."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    translation_budget_s: float = Field(default=FOUNDER_TRANSLATION_BUDGET_S, gt=0, le=3600)
    overseer_budget_s: float = Field(default=DEFAULT_OVERSEER_BUDGET_S, gt=0, le=3600)
    min_selected_accuracy: float = Field(default=FOUNDER_MIN_SELECTED_ACCURACY, ge=FOUNDER_MIN_SELECTED_ACCURACY, lt=1.0)
    on_overseer_timeout: Literal["withhold", "deliver_canonical_not_checked"] = "withhold"
    clearance_wait_ms: int = Field(default=MAX_PENDING_WAIT_MS, ge=0, le=MAX_PENDING_WAIT_MS)


# ============================================================================================ the formal stage's clock
@dataclass(frozen=True)
class ClaimTiming:
    """One call of the deadline-bound verifier: when it started and finished on the policy's clock (seconds since the
    stage started) and what came of it."""
    report_id: str
    claim_id: str
    state: Literal["verified", "no_outcome", "skipped_budget", "late", "raised"]
    started_s: float
    finished_s: float


class TranslationStage:
    """The formal stage of one deliverable: its start and deadline on the policy's monotonic clock, and every call of the
    deadline-bound verifier. Thread-safe."""

    def __init__(self, clock: Clock, budget_s: float) -> None:
        self.clock = clock
        self.started_at = float(clock())
        self.budget_s = float(budget_s)
        self.deadline = self.started_at + self.budget_s
        self._lock = threading.Lock()
        self._timings: list[ClaimTiming] = []

    def elapsed(self, at: Optional[float] = None) -> float:
        return (float(self.clock()) if at is None else at) - self.started_at

    def record(self, report_id: str, claim_id: str, state: str, started: float, finished: float) -> None:
        with self._lock:
            self._timings.append(ClaimTiming(report_id=report_id, claim_id=claim_id, state=state,  # type: ignore[arg-type]
                                             started_s=round(started - self.started_at, 6), finished_s=round(finished - self.started_at, 6)))

    @property
    def timings(self) -> tuple[ClaimTiming, ...]:
        with self._lock:
            return tuple(self._timings)

    def of(self, report_id: Optional[str], claim_id: str) -> Optional[ClaimTiming]:
        last = None
        for t in self.timings:
            if t.claim_id == claim_id and (report_id is None or t.report_id == report_id):
                last = t
        return last

    def labels(self, state: str) -> list[str]:
        return [f"{t.report_id}#{t.claim_id}" for t in self.timings if t.state == state]


class DeadlineVerifier:
    """The channel's claim verifier for one deliverable, bound to the formal stage's deadline: a claim whose verification
    would start at or after the deadline is not started (no outcome: ``skipped_budget``, so the claim is NOT_ATTEMPTED and
    never a success); one that finishes after it is ``late`` (its outcome stays on the receipt, but the formal path is out
    of budget). The inner verifier is called as the channel would call it: with ``task=`` only when it declares a
    ``task`` parameter."""

    def __init__(self, inner: Optional[Callable[..., Any]], stage: TranslationStage) -> None:
        self._inner = inner
        self._stage = stage
        self._task_aware = inner is not None and _accepts_task(inner)

    @property
    def inner(self) -> Optional[Callable[..., Any]]:
        return self._inner

    def __call__(self, claim: Any, report: Any, task: Any = None) -> Optional[ClaimVerificationOutcome]:
        stage = self._stage
        rid, cid = str(getattr(report, "report_id", "")), str(getattr(claim, "claim_id", ""))
        started = float(stage.clock())
        if started >= stage.deadline:
            stage.record(rid, cid, "skipped_budget", started, started)
            return None
        if self._inner is None:
            stage.record(rid, cid, "no_outcome", started, started)
            return None
        try:
            out = self._inner(claim, report, task=task) if (self._task_aware and task is not None) else self._inner(claim, report)
        except Exception:
            stage.record(rid, cid, "raised", started, float(stage.clock()))
            raise
        finished = float(stage.clock())
        state = "late" if finished > stage.deadline else ("verified" if out is not None else "no_outcome")
        stage.record(rid, cid, state, started, finished)
        return out


class _OverseerClock:
    """The overseer stage's deadline, read by every instance's provider wrapper at call time."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.deadline: Optional[float] = None
        self.started_at: Optional[float] = None
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def open(self, budget_s: float) -> None:
        with self._lock:
            self.started_at = float(self.clock())
            self.deadline = self.started_at + float(budget_s)
            self.calls = []

    def close(self) -> list[dict]:
        with self._lock:
            calls, self.calls = self.calls, []
            self.deadline = None
            return calls

    def record(self, agent_id: str, state: str, started: float, finished: float) -> None:
        with self._lock:
            base = self.started_at or 0.0
            self.calls.append({"agent_id": agent_id, "state": state, "started_s": round(started - base, 6), "finished_s": round(finished - base, 6)})


class _StageProvider:
    """One overseer instance's completion provider inside the overseer stage's deadline: a call started at or after the
    deadline is not made, and a reply that arrives after it is not counted; both reach the runner as a provider failure,
    which records no review (never a verdict)."""

    def __init__(self, inner: Any, stage: _OverseerClock, agent_id: str) -> None:
        if not callable(getattr(inner, "complete", None)):
            raise TypeError("an overseer provider must implement complete(system, user, *, prompt_version)")
        self._inner = inner
        self._stage = stage
        self._agent_id = agent_id
        name = getattr(inner, "name", None)
        self.name = name if isinstance(name, str) else "provider"

    def complete(self, system: str, user: str, *, prompt_version: str) -> Any:
        st = self._stage
        started = float(st.clock())
        if st.deadline is None or started >= st.deadline:
            st.record(self._agent_id, "skipped_budget", started, started)
            raise ProviderError("the overseer stage's budget was spent before this instance ran: no review")
        try:
            resp = self._inner.complete(system, user, prompt_version=prompt_version)
        except BaseException:
            st.record(self._agent_id, "provider_error", started, float(st.clock()))
            raise
        finished = float(st.clock())
        if finished > st.deadline:
            st.record(self._agent_id, "late", started, finished)
            raise ProviderError("the reply arrived after the overseer stage's budget: it is not counted")
        st.record(self._agent_id, "in_time", started, finished)
        return resp


# ============================================================================================ the records
_FROZEN = ConfigDict(extra="forbid", frozen=True)
ClaimFormalOutcome = Literal["clean", "refuted", "unresolved", "not_attempted", "skipped_budget", "late", "not_eligible"]


class ClaimFormal(BaseModel):
    """One material claim of the deliverable on the formal path."""
    model_config = _FROZEN
    claim_id: str
    role: str
    eligible: bool
    outcome: ClaimFormalOutcome
    translation_status: Optional[str] = None
    display_status: Optional[str] = None
    result_id: Optional[str] = None
    finished_s: Optional[float] = None
    reasons: list[str] = Field(default_factory=list)


class BranchCheck(BaseModel):
    """One branch formal check of the report's own statements (a STEM check, an arithmetic or chronology check)."""
    model_config = _FROZEN
    constraint_id: str
    satisfied: Optional[bool]
    formal_status: Optional[str] = None
    result_id: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list)


class FormalPath(BaseModel):
    """What the formal path found for the deliverable, and why it is or is not complete."""
    model_config = _FROZEN
    complete: bool
    within_budget: bool
    budget_s: float
    translation_s: float
    deliverable_message_id: Optional[str] = None
    deliverable_receipt_id: Optional[str] = None
    receipt_status: Optional[str] = None
    receipt_error_codes: list[str] = Field(default_factory=list)
    consolidation_status: Optional[str] = None
    clearance: Optional[str] = None
    claims: list[ClaimFormal] = Field(default_factory=list)
    branch_checks: list[BranchCheck] = Field(default_factory=list)
    skipped_claims: list[str] = Field(default_factory=list, description="report#claim the deadline left unstarted (NOT_ATTEMPTED)")
    late_claims: list[str] = Field(default_factory=list, description="report#claim whose verification finished after the deadline")
    reasons: list[str] = Field(default_factory=list)


ClaimAssessmentValue = Literal["accurate", "inaccurate", "contested", "unassessed"]


class ClaimAccuracy(BaseModel):
    """One material claim of a candidate: the overseer's assessment and its evidence (the policy's own text, never an
    agent's)."""
    model_config = _FROZEN
    claim_id: str
    assessment: ClaimAssessmentValue
    refuted_by_signed_result: bool = False
    faulted_by_check: bool = False
    evidence: list[str] = Field(default_factory=list)


class CandidateAssessment(BaseModel):
    """One candidate answer: its integrity gates, its faults and its accuracy, with the evidence."""
    model_config = _FROZEN
    message_id: str
    receipt_id: Optional[str] = None
    agent_id: Optional[str] = None
    report_id: Optional[str] = None
    seq: int
    group_id: Optional[str] = None
    canonical: bool = False
    canonical_rank: int
    deliverable: bool
    integrity_reasons: list[str] = Field(default_factory=list)
    refuted: bool
    faulted: bool
    answer_level_faults: list[str] = Field(default_factory=list)
    material_claims: int
    accurate: int
    accuracy: float
    accuracy_fraction: str
    above_threshold: bool
    reviewed_by: list[str] = Field(default_factory=list, description="the agents whose counted verdicts examined this transfer")
    claims: list[ClaimAccuracy] = Field(default_factory=list)


class VerdictStanding(BaseModel):
    """Whether one validated verdict counts for accuracy (a verdict contradicting a signed engine result does not)."""
    model_config = _FROZEN
    agent_id: str
    intake_message_id: Optional[str] = None
    valid: bool
    counted: bool
    transfers_reviewed: int = 0
    accusations: int = 0
    reasons: list[str] = Field(default_factory=list)


class OverseerStage(BaseModel):
    """The overseer stage of the fallback: whether it ran, its deadline and what its instances did."""
    model_config = _FROZEN
    configured: bool
    ran: bool
    timed_out: bool = False
    error: Optional[str] = None
    budget_s: float
    started_at_s: Optional[float] = None
    elapsed_s: Optional[float] = None
    plan_id: Optional[str] = None
    instances: list[str] = Field(default_factory=list)
    plan_reasons: list[str] = Field(default_factory=list)
    runs: list[dict] = Field(default_factory=list)
    provider_calls: list[dict] = Field(default_factory=list)
    verdicts: list[VerdictStanding] = Field(default_factory=list)
    verdicts_audit_id: Optional[str] = None
    task_audit_id: Optional[str] = None


class Fallback(BaseModel):
    """Why the formal path did not complete, the overseer stage, every candidate and the selection."""
    model_config = _FROZEN
    why: list[str] = Field(default_factory=list)
    overseer: OverseerStage
    candidates: list[CandidateAssessment] = Field(default_factory=list)
    non_candidates: list[str] = Field(default_factory=list, description="answers the channel never delivered (message id: why)")
    chosen_message_id: Optional[str] = None
    min_selected_accuracy: float
    selection: list[str] = Field(default_factory=list)


class DeliveryReceipt(BaseModel):
    """``delivery_receipt/1.0``: the signed record of one delivery decision. Produced only by :class:`DeliveryPolicy`,
    signed under the overseer's ``delivery`` subkey (key id ``overseer-delivery``). Frozen; any edit no longer verifies."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: Literal["delivery_receipt/1.0"] = DELIVERY_CONTRACT
    receipt_id: str
    policy_version: str = DELIVERY_POLICY_VERSION
    task_id: str
    request_id: str
    channel_uid: str
    user_input_sha256: Optional[str] = None
    request_message_ids: list[str] = Field(default_factory=list)
    mode: DeliveryMode
    delivered: bool
    label: str
    delivered_message_id: Optional[str] = None
    delivered_receipt_id: Optional[str] = None
    delivered_agent_id: Optional[str] = None
    delivered_report_id: Optional[str] = None
    delivered_payload_sha256: Optional[str] = None
    translation_budget_s: float
    overseer_budget_s: float
    min_selected_accuracy: float
    time_to_decision_s: float
    translation_s: float
    overseer_s: Optional[float] = None
    formal: FormalPath
    fallback: Optional[Fallback] = None
    consolidation_id: Optional[str] = None
    consolidation_status: Optional[str] = None
    task_audit_id: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    scope_statement: str = DELIVERY_SCOPE_STATEMENT
    created_at: str
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None


class DeliveredAnswer(BaseModel):
    """``delivered_answer/1.0``: what the router hands on. ``payload`` is the chosen answer's journaled payload, byte for
    byte (``payload_sha256`` is its envelope digest); the mode and label are the receipt's, which names this digest. An
    answer the formal path did not decide also carries, from the signed receipt, why the formal path did not complete
    (``formal_reasons``), the selection evidence (``selection``) and the chosen candidate's accuracy (``accuracy_fraction``,
    for ``overseer_selected``): the policy's own text, never an agent's."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: Literal["delivered_answer/1.0"] = DELIVERED_ANSWER_CONTRACT
    mode: DeliveryMode
    label: str
    message_id: str
    report_id: Optional[str] = None
    agent_id: Optional[str] = None
    payload: dict
    payload_sha256: str
    delivery_receipt_id: str
    formal_reasons: list[str] = Field(default_factory=list)
    selection: list[str] = Field(default_factory=list)
    accuracy_fraction: Optional[str] = None


@dataclass(frozen=True)
class DeliveryDecision:
    """What :meth:`DeliverySession.decide` returns. ``delivered`` is the only field that permits handing anything on;
    ``answer`` is None unless an answer is delivered."""
    mode: str
    delivered: bool
    message_id: Optional[str]
    label: str
    receipt: DeliveryReceipt
    answer: Optional[DeliveredAnswer] = None
    consolidation: Optional[ConsolidatedResponse] = None
    review: Any = None


# ============================================================================================ signing
def _signable(rec: DeliveryReceipt) -> str:
    data = rec.model_dump(mode="json", exclude_none=True)
    for f in _SIGNATURE_FIELDS:
        data.pop(f, None)
    return canonical_json(data)


def delivery_receipt_digest(rec: DeliveryReceipt) -> str:
    return sha256_hex(_signable(rec))


def sign_delivery_receipt(rec: DeliveryReceipt, keyring: KeyRing) -> DeliveryReceipt:
    """The receipt signed under the delivery subkey (key id ``overseer-delivery``)."""
    unsigned = rec.model_copy(update={"signature": None, "signature_key_id": None})
    mac = hmac.new(keyring.subkey("delivery"), _signable(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    return unsigned.model_copy(update={"signature": mac, "signature_key_id": DELIVERY_KEY_ID})


def verify_delivery_receipt(rec: Any, keyring: KeyRing) -> bool:
    """True only for a delivery receipt signed under the delivery key and unchanged since. Never raises."""
    if not isinstance(rec, DeliveryReceipt) or not rec.signature or rec.signature_key_id != DELIVERY_KEY_ID:
        return False
    try:
        expected = hmac.new(keyring.subkey("delivery"), _signable(rec).encode("utf-8"), hashlib.sha256).hexdigest()
    except Exception:
        return False
    return signature_matches(expected, rec.signature)


def verify_delivered_answer(answer: Any, rec: Any, keyring: KeyRing) -> bool:
    """True only when ``answer`` is the payload ``rec`` (a verifying delivery receipt that delivered something) names:
    the same message, mode, label and evidence (the formal path's reasons, the selection, the chosen accuracy), and a
    payload whose digest is the one the receipt records."""
    if not isinstance(answer, DeliveredAnswer) or not verify_delivery_receipt(rec, keyring) or not rec.delivered:
        return False
    try:
        digest = payload_hash(answer.payload)
    except Exception:
        return False
    return (answer.delivery_receipt_id == rec.receipt_id and answer.message_id == rec.delivered_message_id and answer.mode == rec.mode
            and answer.label == rec.label and digest == answer.payload_sha256 == rec.delivered_payload_sha256
            and (answer.formal_reasons, answer.selection, answer.accuracy_fraction) == _evidence_of(rec))


def _evidence_of(rec: DeliveryReceipt) -> tuple[list[str], list[str], Optional[str]]:
    """What a delivered answer carries from its receipt: the formal path's reasons (none when it decided), the
    selection evidence and the chosen candidate's accuracy."""
    if rec.mode == "formally_checked":
        return [], [], None
    fb = rec.fallback
    chosen = next((c for c in fb.candidates if c.message_id == fb.chosen_message_id), None) if fb is not None else None
    return (list(rec.formal.reasons), list(fb.selection) if fb is not None else [],
            chosen.accuracy_fraction if (chosen is not None and rec.mode == "overseer_selected") else None)


#: Phrases a label of a mode other than ``formally_checked`` may carry only negated.
_CLAIMS_OF_CHECKING = ("formally checked", "verified")


def is_fallback_label_honest(mode: str, label: str) -> bool:
    """True when ``label`` claims verification only for ``formally_checked``: every other label says "not formally
    checked" and "not verified" and never states either phrase un-negated."""
    low = label.lower()
    if mode == "formally_checked":
        return low.startswith("formally checked")
    for phrase in _CLAIMS_OF_CHECKING:
        if low.count(phrase) != low.count("not " + phrase) or ("not " + phrase) not in low:
            return False
    return True


# ============================================================================================ formal path
def _eligible(claim: ClaimRecord) -> bool:
    """Deterministic eligibility (the eligibility rules and the subject policy; no model), as the pipeline decides it."""
    try:
        return bool(apply_subject_policy(decide_eligibility(claim), resolve_profile(claim.subject)).eligible)
    except Exception:
        return True  # unknown is never "not eligible": the claim must be decided


def _task_record(view: OverseerView, t: Transfer) -> Optional[TaskRecord]:
    """The task record of the journaled request ``t`` answers, as the channel builds it."""
    rt = view.by_seq.get(t.request_seq) if t.request_seq is not None else None
    req = rt.request if rt is not None else None
    if req is None or not req.user_input:
        return None
    try:
        return TaskRecord.of(req.task_id, req.request_id, req.user_input)
    except Exception:
        return None


def _rederive(claim: ClaimRecord, o: ClaimVerificationOutcome, report: SpecialistReport, task: Optional[TaskRecord], keyring: KeyRing):
    """``(display, release, authentic)`` re-derived as the composer derives them (``translate.outcome.compose_outcome``),
    from the journaled translation and signed result, under the auditor's verification key for the result's key id: the
    stored ``display_status`` and ``release`` fields are never trusted."""
    tr, ver, review = o.translation, o.verification, o.semantic_review
    kid = ver.signature_key_id if ver is not None else None
    key = keyring.verification_key(kid) if kid else None
    authentic = False
    if ver is not None:
        try:
            authentic = bool(keyring.verify_result(ver)[0])
        except Exception:
            authentic = False
    if key is not None:
        display = display_status_for(tr, ver, key, kid)
    else:  # a result under a key id the auditor holds no key for cannot be authenticated: never displayed as a verdict
        display = display_status_for(tr, ver)
        if ver is not None and tr.status is TranslationStatus.TRANSLATED:
            display = S.INTERNAL_ERROR
    trusted = ver if display is not S.INTERNAL_ERROR else None
    engine_check = (release_check(trusted, tr.problem, signing_key=key, key_id=kid) if trusted is not None and tr.problem is not None else None)
    state = None
    if review is not None:
        bound_task = review.binding.task_sha256 if review.binding is not None else None
        tk = task if (task is not None and bound_task is not None and bound_task == task.text_sha256) else None
        try:
            state = review_currency(review, claim, tr, report, tk)
        except Exception:
            state = ("unbound", [])
    release = assess_release(tr, trusted, review, list(o.structural_findings), display, state, engine_check)
    return display, release, authentic


def _error_findings_naming(receipt: Any, report_id: Optional[str], claim_id: str) -> list[Any]:
    out = []
    for f in list(getattr(receipt, "findings", []) or []):
        if f.severity == "error" and claim_id in f.claim_ids and (not f.report_ids or report_id in f.report_ids):
            out.append(f)
    for sf in list(getattr(receipt, "structural_findings", []) or []):
        if sf.severity == "error" and claim_id in sf.claim_ids:
            out.append(sf)
    return out


def _answer_level_errors(receipt: Any, material_ids: Iterable[str] = ()) -> list[str]:
    """Error-level receipt findings that name no material claim: a fault of the answer as a whole (a word limit, no
    answer) or of a supporting claim (an invented quotation in the evidence). They fault the answer as delivered."""
    mats = set(material_ids)
    codes = [f.code for f in list(getattr(receipt, "findings", []) or []) if f.severity == "error" and not (set(f.claim_ids) & mats)]
    codes += [sf.code for sf in list(getattr(receipt, "structural_findings", []) or []) if sf.severity == "error" and not (set(sf.claim_ids) & mats)]
    return sorted(set(codes))


def _audit_findings_naming(audit: Any, message_id: str) -> list[Any]:
    if audit is None:
        return []
    return [f for f in audit.report.findings if not is_agent_code(f.code) and message_id in f.message_ids]


def _formal_claims(t: Transfer, view: OverseerView, keyring: KeyRing, stage: TranslationStage) -> tuple[list[ClaimFormal], list[BranchCheck]]:
    report, receipt = t.report, t.receipt
    assert report is not None and receipt is not None
    task = _task_record(view, t)
    outcomes = {o.claim_id: o for o in receipt.outcomes}
    claims: list[ClaimFormal] = []
    for c in material_claims(report):
        o = outcomes.get(c.claim_id)
        timing = stage.of(report.report_id, c.claim_id)
        finished = timing.finished_s if timing is not None else None
        errors = _error_findings_naming(receipt, report.report_id, c.claim_id)
        err_reasons = [f"the receipt names it in an error-level finding ({f.code})" for f in errors]
        if o is None or o.translation.status is TranslationStatus.NOT_ELIGIBLE:
            eligible = _eligible(c) if o is None else False
            if not eligible:
                claims.append(ClaimFormal(claim_id=c.claim_id, role=c.claim_role, eligible=False, outcome="not_eligible", reasons=err_reasons
                                          or ["not eligible for the formal check under the subject policy (deterministic eligibility)"]))
                continue
            if timing is not None and timing.state == "skipped_budget":
                claims.append(ClaimFormal(claim_id=c.claim_id, role=c.claim_role, eligible=True, outcome="skipped_budget", finished_s=finished,
                                          reasons=[f"not started: the translation budget was spent at {timing.started_s:g} s (NOT_ATTEMPTED)"] + err_reasons))
            else:
                why = {"no_outcome": "the verifier produced no outcome (no translation was served)",
                       "raised": "the verification failed internally"}.get(timing.state if timing is not None else "", "no translation outcome reached the receipt")
                claims.append(ClaimFormal(claim_id=c.claim_id, role=c.claim_role, eligible=True, outcome="not_attempted", finished_s=finished,
                                          reasons=[f"{why} (NOT_ATTEMPTED)"] + err_reasons))
            continue
        display, release, authentic = _rederive(c, o, report, task, keyring)
        ver = o.verification
        base = dict(claim_id=c.claim_id, role=c.claim_role, eligible=True, translation_status=o.translation.status.value, display_status=display.value,
                    result_id=ver.result_id if ver is not None else None, finished_s=finished)
        if display in REFUTING_STATUSES and authentic and ver is not None and ver.status is display:
            claims.append(ClaimFormal(**base, outcome="refuted", reasons=[f"the signed engine result {ver.result_id} is {display.value}: the claim's "
                                                                             "encoding does not hold as stated"] + err_reasons))
            continue
        reasons: list[str] = []
        if o.translation.status is not TranslationStatus.TRANSLATED:
            reasons.append(f"translation {o.translation.status.value}")
        interp = o.translation.interpretation
        if interp is not None and interp.ambiguity_flags:
            reasons.append("the translation carries ambiguity flags: " + _listed([a.code for a in interp.ambiguity_flags]))
        if not is_definitive(display):
            reasons.append(f"display status {display.value}: no definitive verdict")
        if not release.permitted:
            reasons += [f"release rule {release.policy}: {_cut(u, 300)}" for u in release.unresolved]
        reasons += err_reasons
        if timing is not None and timing.state == "late":
            claims.append(ClaimFormal(**base, outcome="late", reasons=[f"its verification finished at {timing.finished_s:g} s, after the "
                                                                          f"{stage.budget_s:g} s budget"] + reasons))
            continue
        claims.append(ClaimFormal(**base, outcome="unresolved" if reasons else "clean", reasons=reasons))
    checks = [BranchCheck(constraint_id=fc.constraint_id, satisfied=fc.satisfied, formal_status=fc.formal_status, result_id=fc.formal_result_id,
                          claim_ids=list(fc.claim_ids)) for fc in receipt.formal_checks]
    return claims, checks


# ============================================================================================ the fallback's assessment
def _verdict_standing(va: Any) -> VerdictStanding:
    """Whether a validated verdict counts for accuracy: valid, and contradicting no signed engine result. A verdict whose
    engine statement is refuted, or whose accusation (or its remainder) a signed result refutes, is rejected whole."""
    reasons: list[str] = []
    if not va.valid:
        reasons.append(f"invalid verdict ({va.invalid_reason or 'binding'}): OVS-AGENT-005")
    for e in va.engine_statements:
        if e.outcome == "refuted":
            reasons.append(f"engine statement #{e.position + 1} contradicts the stored result ({e.refuted_by or 'refuted'}): OVS-AGENT-001")
    for a in va.accusations:
        if a.outcome == "refuted" and a.refuted_by == "signed_result":
            reasons.append(f"accusation #{a.position + 1} ({a.kind}) is refuted by a signed engine result: OVS-AGENT-001")
        if a.remainder is not None and a.remainder.outcome == "refuted" and a.remainder.refuted_by == "signed_result":
            reasons.append(f"part of accusation #{a.position + 1} ({a.kind}) is refuted by a signed engine result: OVS-AGENT-001")
    counted = va.valid and not reasons
    if counted:
        reasons.append("valid and contradicts no signed engine result: counted")
    else:
        reasons.append("rejected: none of its reviews counts for accuracy")
    return VerdictStanding(agent_id=va.agent_id, intake_message_id=va.intake_message_id, valid=bool(va.valid), counted=counted,
                           transfers_reviewed=len(va.transfers_reviewed), accusations=len(va.accusations), reasons=reasons)


def _touches(ids: Mapping[str, Sequence[str]], claim_reports: Mapping[str, Sequence[str]], t: Transfer, claim_id: str) -> bool:
    """Whether an accusation's identifiers name the claim ``claim_id`` of transfer ``t`` (conservatively: an accusation
    naming the transfer or its report and no claim names every claim of it)."""
    claims = list(ids.get("claim_ids", ()) or ())
    names_transfer = (t.message_id in (ids.get("message_ids") or ()) or (t.receipt_id is not None and t.receipt_id in (ids.get("receipt_ids") or ()))
                      or (t.report_id is not None and t.report_id in (ids.get("report_ids") or ())))
    if claims:
        if claim_id not in claims:
            return False
        reps = list(claim_reports.get(claim_id) or ())
        if reps:
            return t.report_id in reps
        return names_transfer or not any(ids.get(k) for k in ("message_ids", "receipt_ids", "report_ids"))
    return names_transfer


def _signed_refutation(view: OverseerView, result_id: Optional[str]) -> bool:
    """Whether ``result_id`` names a signed engine result of this channel's store whose signature verified when it was
    stored and whose status is definitive: an error-level check citing it is a refutation by a signed engine result (a
    STEM check that does not hold, INT-SUBJ-001; premises that contradict each other, INT-REQ-007)."""
    if not result_id or view.store is None:
        return False
    rec = view.store.get(result_id)
    if rec is None or not getattr(rec, "signature_ok_at_put", False):
        return False
    try:
        return is_definitive(S(rec.status))
    except ValueError:
        return False


def _assess_claim(t: Transfer, c: ClaimRecord, *, reviewed_by: list[str], counted: list[Any], all_assessed: list[Any], audit: Any,
                  keyring: KeyRing, view: OverseerView) -> ClaimAccuracy:
    report, receipt = t.report, t.receipt
    assert report is not None and receipt is not None
    evidence: list[str] = []
    refuted = False
    faulted = False
    # signed engine results: the claim's displayed verdict, and error-level checks citing a signed result
    o = next((x for x in receipt.outcomes if x.claim_id == c.claim_id), None)
    if o is not None and o.verification is not None:
        display, _release, authentic = _rederive(c, o, report, _task_record(view, t), keyring)
        if display in REFUTING_STATUSES and authentic and o.verification.status is display:
            refuted = True
            evidence.append(f"refuted by the signed engine result {o.verification.result_id} ({display.value})")
    for f in _error_findings_naming(receipt, report.report_id, c.claim_id):
        if _signed_refutation(view, getattr(f, "formal_result_id", None)):
            refuted = True
            evidence.append(f"refuted by the signed engine result {f.formal_result_id} behind the receipt's {f.code} (error)")
        else:
            faulted = True
            evidence.append(f"faulted by a deterministic check: the receipt's {f.code} (error)")
    for f in _audit_findings_naming(audit, t.message_id or ""):
        if f.severity == "error" and c.claim_id in f.claim_ids and (not f.report_ids or report.report_id in f.report_ids):
            faulted = True
            evidence.append(f"faulted by the transfer audit: {f.code} (error)")
    # validated accusations (every assessed verdict: a check's confirmation stands whoever accused; only counted verdicts
    # contest a claim, so a rejected verdict lowers no score by its unresolved words)
    contested = False
    for va in all_assessed:
        is_counted = va in counted
        for a in va.accusations:
            if a.outcome == "confirmed":
                cov = a.covered_identifiers or a.identifiers
                if _touches(cov, a.claim_report_ids, t, c.claim_id):
                    faulted = True
                    evidence.append(f"an accusation of agent {va.agent_id} ({a.kind}) is confirmed by the check's finding "
                                    + _listed([r.code for r in a.confirming]))
                elif a.remainder is not None and a.remainder.outcome in ("unresolved", "unverifiable") and is_counted \
                        and _touches(a.remainder.identifiers, a.claim_report_ids, t, c.claim_id):
                    contested = True
                    evidence.append(f"part of an accusation of agent {va.agent_id} ({a.kind}) is unresolved (human review)")
            elif a.outcome in ("unresolved", "unverifiable") and is_counted and _touches(a.identifiers, a.claim_report_ids, t, c.claim_id):
                contested = True
                evidence.append(f"an accusation of agent {va.agent_id} ({a.kind}) is {a.outcome} ({a.code}): not confirmed accurate")
    if refuted or faulted:
        return ClaimAccuracy(claim_id=c.claim_id, assessment="inaccurate", refuted_by_signed_result=refuted, faulted_by_check=faulted, evidence=evidence)
    if contested:
        return ClaimAccuracy(claim_id=c.claim_id, assessment="contested", evidence=evidence)
    if not reviewed_by:
        return ClaimAccuracy(claim_id=c.claim_id, assessment="unassessed", evidence=evidence + ["no counted overseer verdict examined this transfer"])
    support = []
    if o is not None and o.verification is not None and o.display_status in (S.ENTAILED, S.CONSISTENT, S.SATISFIABLE):
        support.append(f"its encoding's signed engine result {o.verification.result_id} is {o.display_status.value} (encoding only)")
    return ClaimAccuracy(claim_id=c.claim_id, assessment="accurate", evidence=[
        f"examined by the counted verdict(s) of {_listed(reviewed_by)}: no fault pinned down on it, no check names it in an error, no signed "
        "engine result refutes it (advisory review, not a verification)"] + support)


# ============================================================================================ the session and the policy
class DeliverySession:
    """The delivery of one deliverable: its formal stage (started when the deliverable's first answer reaches the hub)
    and its decision. Built by :meth:`DeliveryPolicy.start`."""

    def __init__(self, policy: "DeliveryPolicy", hub: Any, task_key: Any) -> None:
        self.policy = policy
        self.hub = hub
        self.task_key = task_key
        self.channel = hub.channel_for(task_key)
        self.stage = TranslationStage(policy.clock, policy.config.translation_budget_s)
        self._previous: Optional[Callable[..., Any]] = None
        self._installed = False
        self._decision: Optional[DeliveryDecision] = None
        self._lock = threading.Lock()

    @property
    def started_at(self) -> float:
        return self.stage.started_at

    @property
    def deadline(self) -> float:
        return self.stage.deadline

    def verifier(self, inner: Optional[Callable[..., Any]] = None) -> DeadlineVerifier:
        """A deadline-bound verifier around ``inner`` (by default the channel's current verifier)."""
        return DeadlineVerifier(inner if inner is not None else self.channel.verify_claim_fn, self.stage)

    def install(self, inner: Optional[Callable[..., Any]] = None) -> DeadlineVerifier:
        """Put the deadline-bound verifier on the channel (``restore`` puts the previous one back)."""
        with self._lock:
            current = self.channel.verify_claim_fn
            if isinstance(current, DeadlineVerifier):
                current = current.inner
            if not self._installed:
                self._previous = current
            fn = DeadlineVerifier(inner if inner is not None else current, self.stage)
            self.channel.verify_claim_fn = fn
            self._installed = True
            return fn

    def restore(self) -> None:
        with self._lock:
            if self._installed:
                self.channel.verify_claim_fn = self._previous
                self._installed = False

    def decide(self, *, request_message_ids: Optional[Sequence[str]] = None, user_input_sha256: Optional[str] = None,
               receipts: Optional[Mapping[str, Any]] = None) -> DeliveryDecision:
        """The decision for this deliverable (module docstring). ``receipts`` maps an answer's message id to the receipt
        object the router holds (the clearance compares that copy with the journal); by default the channel's own. A
        session decides once; a second call returns the same decision. Never raises for the content of the transfers."""
        with self._lock:  # held across the decision: a concurrent second call waits and returns the same decision
            if self._decision is None:
                self._decision = self.policy._decide(self, request_message_ids=request_message_ids, user_input_sha256=user_input_sha256,
                                                     receipts=receipts)
            self.restore_unlocked()
            return self._decision

    def restore_unlocked(self) -> None:
        if self._installed:
            self.channel.verify_claim_fn = self._previous
            self._installed = False


class DeliveryPolicy:
    """The delivery policy (module docstring).

    ``pack`` (a :class:`~epinoic_logic.overseer.pack.KnowledgePack` loaded by ``load_pack``, normally the exported pack)
    and ``provider_factory`` (``agent_id -> completion provider``) configure the overseer agents of the fallback: the
    policy builds ONE :class:`~epinoic_logic.overseer.pool.OverseerPool` from them, each instance's provider wrapped by
    the overseer stage's deadline. Without them the fallback has no overseer agent, so no accuracy is ever established.
    ``clock`` is a monotonic clock (``time.monotonic`` by default; tests inject a fake one)."""

    def __init__(self, *, config: Optional[DeliveryConfig] = None, clock: Clock = time.monotonic, pack: Any = None,
                 provider_factory: Optional[Callable[[str], Any]] = None, pool_config: Optional[PoolConfig] = None) -> None:
        self.config = config if config is not None else DeliveryConfig()
        if not isinstance(self.config, DeliveryConfig):
            raise TypeError("config must be a DeliveryConfig")
        self.config = DeliveryConfig.model_validate(self.config.model_dump())  # a config built around validation is refused
        if not callable(clock):
            raise TypeError("clock must be a callable returning monotonic seconds")
        self.clock = clock
        self._overseer_clock = _OverseerClock(clock)
        self._lock = threading.RLock()
        self.pool: Optional[OverseerPool] = None
        if (pack is None) != (provider_factory is None):
            raise ValueError("the overseer agents need both a loaded knowledge pack and a provider factory (or neither)")
        if pack is not None:
            if not callable(provider_factory):
                raise TypeError("provider_factory must be callable: agent_id -> completion provider")
            factory = provider_factory
            stage = self._overseer_clock

            def wrapped(agent_id: str) -> _StageProvider:
                return _StageProvider(factory(agent_id), stage, agent_id)
            self.pool = OverseerPool(pack, wrapped, config=pool_config)

    def __repr__(self) -> str:
        c = self.config
        return (f"DeliveryPolicy(translation_budget_s={c.translation_budget_s:g}, overseer_budget_s={c.overseer_budget_s:g}, "
                f"min_selected_accuracy={c.min_selected_accuracy:g}, overseer={'configured' if self.pool is not None else 'none'})")

    def start(self, hub: Any, task_key: Any) -> DeliverySession:
        """Open the formal stage of one deliverable on the hub's task ``task_key`` (call it when the first answer reaches
        the hub). The hub must carry the transfer auditor: nothing is delivered without the transfer audit."""
        if getattr(hub, "auditor", None) is None:
            from ..branches.hub import AuditorNotAttached
            raise AuditorNotAttached("the delivery policy decides only on a hub with the transfer auditor attached")
        return DeliverySession(self, hub, task_key)

    # ------------------------------------------------------------------ the decision
    def _decide(self, session: DeliverySession, *, request_message_ids, user_input_sha256, receipts) -> DeliveryDecision:
        # no policy-wide lock here: one deliverable's decision never waits for another's (a lock held across the formal
        # path would count the wait for another deliverable's overseer stage as this one's translation time); only the
        # overseer stage, whose deadline the instances' providers share, is serialised (``_fallback``)
        try:
            return self._decide_unlocked(session, request_message_ids=request_message_ids, user_input_sha256=user_input_sha256, receipts=receipts)
        except Exception as exc:  # the policy never delivers on its own failure
            return self._failed(session, exc)

    def _failed(self, session: DeliverySession, exc: BaseException) -> DeliveryDecision:
        end = float(self.clock())
        why = f"the delivery policy failed internally ({type(exc).__name__}); nothing is delivered"
        formal = FormalPath(complete=False, within_budget=end <= session.deadline, budget_s=self.config.translation_budget_s,
                            translation_s=round(end - session.started_at, 6), reasons=[why])
        rec = self._receipt(session, mode="withheld", label=self._label("withheld", kind="internal"), formal=formal, fallback=None, reasons=[why],
                            end=end, overseer_s=None)
        return DeliveryDecision(mode="withheld", delivered=False, message_id=None, label=rec.label, receipt=rec)

    def _decide_unlocked(self, session: DeliverySession, *, request_message_ids, user_input_sha256, receipts) -> DeliveryDecision:
        hub, cfg = session.hub, self.config
        auditor = hub.auditor
        keyring: KeyRing = auditor.keyring
        uid = session.channel.channel_uid
        receipts = dict(receipts or {})
        stage = session.stage
        view = auditor.view(uid)
        # ---------------------------------------------------------------- the input and its answers
        try:
            digest, requests = select_requests(view, request_message_ids=request_message_ids, user_input_sha256=user_input_sha256)
        except ValueError as exc:
            end = float(self.clock())
            why = f"no deliverable: {_cut(str(exc), 300)}"
            formal = FormalPath(complete=False, within_budget=end <= stage.deadline, budget_s=stage.budget_s, translation_s=round(end - stage.started_at, 6),
                                reasons=[why])
            rec = self._receipt(session, mode="withheld", label=self._label("withheld", kind="no_input"), formal=formal, fallback=None, reasons=[why],
                                end=end, overseer_s=None)
            return DeliveryDecision(mode="withheld", delivered=False, message_id=None, label=rec.label, receipt=rec)
        req_ids = [t.message_id for t in requests if t.message_id]
        answers = [t for t in view.transfers if t.kind in RESPONSE_KINDS and t.message_id and t.in_reply_to in set(req_ids)]
        consolidation: Optional[ConsolidatedResponse] = None
        cons_error: Optional[str] = None
        if answers:
            try:
                consolidation = hub.consolidate(session.task_key, request_message_ids=req_ids)
            except Exception as exc:
                cons_error = f"the answers could not be consolidated ({type(exc).__name__}: {_cut(str(exc), 200)})"
        view = auditor.view(uid)
        answers = [view.by_message.get(t.message_id or "", t) for t in answers]
        audit = self._latest_task_audit(auditor, uid, keyring)
        # ---------------------------------------------------------------- the formal path
        formal, deliverable = self._formal(session, view, answers, consolidation, cons_error, audit, receipts, keyring)
        end_formal = float(self.clock())
        within = end_formal <= stage.deadline and not formal.skipped_claims and not formal.late_claims
        reasons_budget: list[str] = []
        if end_formal > stage.deadline:
            reasons_budget.append(f"the formal stage took {end_formal - stage.started_at:g} s, past the {stage.budget_s:g} s translation budget")
        if formal.skipped_claims:
            reasons_budget.append(f"the translation budget ran out before claim(s) {_listed(formal.skipped_claims)} were started (NOT_ATTEMPTED)")
        if formal.late_claims:
            reasons_budget.append(f"claim(s) {_listed(formal.late_claims)} finished after the {stage.budget_s:g} s budget")
        formal = formal.model_copy(update={"within_budget": within, "translation_s": round(end_formal - stage.started_at, 6),
                                           "complete": formal.complete and within, "reasons": [*reasons_budget, *formal.reasons]})
        if formal.complete and deliverable is not None:
            answer_t = deliverable
            label = self._label("formally_checked", formal=formal)
            rec = self._receipt(session, mode="formally_checked", label=label, formal=formal, fallback=None, end=float(self.clock()), overseer_s=None,
                                reasons=["the formal path completed within the budget: every material eligible claim is clean"], consolidation=consolidation,
                                audit=audit, digest=digest, req_ids=req_ids, delivered=answer_t)
            return self._delivered(rec, answer_t, consolidation, None)
        # ---------------------------------------------------------------- the fallback
        why = list(formal.reasons) or ["the formal path did not complete"]
        return self._fallback(session, view, answers, consolidation, audit, receipts, keyring, formal, why, digest, req_ids)

    @staticmethod
    def _latest_task_audit(auditor: Any, uid: str, keyring: KeyRing) -> Any:
        audits = [a for a in auditor.audits(uid) if a.scope == "task" and verify_audit(a, keyring)]
        return audits[-1] if audits else None

    def _clearance(self, session: DeliverySession, t: Transfer, receipts: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """``(state, refusal)``: the transfer's clearance at this moment and why the router may not act on it (None when it
        may). The receipt checked is the router's copy when given, else the channel's."""
        rc = receipts.get(t.message_id or "")
        if rc is None:
            rc = next((r for r in session.channel.receipts if r.message_id == t.message_id), None)
        if rc is None:
            return None, "no receipt of the answer is held"
        try:
            cl = session.hub.clearance(session.task_key, t.message_id, receipt=rc, wait_ms=self.config.clearance_wait_ms)
            dec = act_decision(rc, cl, auditor=session.hub.auditor)
        except Exception as exc:
            return None, f"the clearance could not be obtained ({type(exc).__name__})"
        return cl.state, (None if dec.allowed else f"the router may not act on it: {_cut(dec.reason, 300)}")

    def _formal(self, session: DeliverySession, view: OverseerView, answers: list[Transfer], consolidation: Optional[ConsolidatedResponse],
                cons_error: Optional[str], audit: Any, receipts: Mapping[str, Any], keyring: KeyRing) -> tuple[FormalPath, Optional[Transfer]]:
        stage = session.stage
        base = dict(complete=False, within_budget=True, budget_s=stage.budget_s, translation_s=0.0, skipped_claims=stage.labels("skipped_budget"),
                    late_claims=stage.labels("late"), consolidation_status=consolidation.status if consolidation is not None else None)
        if not answers:
            return FormalPath(**base, reasons=["no answer to the input reached the hub"]), None
        reasons: list[str] = []
        if cons_error:
            reasons.append(cons_error)
        deliverable: Optional[Transfer] = None
        if consolidation is not None:
            if consolidation.status in DELIVERABLE_STATUSES and consolidation.deliverable_message_id:
                deliverable = view.by_message.get(consolidation.deliverable_message_id)
                dec = delivery_decision(consolidation, keyring, hub=session.hub)
                if not dec.allowed:
                    reasons.append(f"the consolidation does not allow the delivery: {_cut(dec.reason, 300)}")
            else:
                what = {"CONFLICTING": "the answers conflict and are disclosed, never chosen", "NO_DELIVERABLE_OUTPUT": "every answer is excluded"}
                reasons.append(f"the consolidation is {consolidation.status}: {what.get(consolidation.status, 'no deliverable answer')}")
                for e in consolidation.excluded:
                    reasons.append(f"answer {e.message_id} ({e.agent_id}) is excluded: {_cut('; '.join(e.reasons), 300)}")
        if deliverable is None:
            return FormalPath(**base, reasons=reasons or ["no deliverable answer"]), None
        t = deliverable
        rec = t.receipt
        if t.report is None or rec is None or t.status == "REJECTED":
            return FormalPath(**base, deliverable_message_id=t.message_id, receipt_status=t.status, reasons=reasons + ["the deliverable was not delivered"]), None
        claims, checks = _formal_claims(t, view, keyring, stage)
        errors = sorted({f.code for f in rec.findings if f.severity == "error"} | {sf.code for sf in rec.structural_findings if sf.severity == "error"})
        if errors:
            reasons.append(f"the deliverable's receipt carries error-level findings: {_listed(errors)}")
        for c in claims:
            if c.outcome not in ("clean", "not_eligible"):
                reasons.append(f"claim {c.claim_id}: {c.outcome}" + (f" ({_cut('; '.join(c.reasons), 400)})" if c.reasons else ""))
        if not any(c.eligible for c in claims):
            reasons.append("the deliverable has no material eligible claim: nothing was formally checked")
        for fc in checks:
            if fc.satisfied is not True:
                reasons.append(f"branch formal check {fc.constraint_id} " + ("does not hold" if fc.satisfied is False else "is undecided"))
        named = _audit_findings_naming(audit, t.message_id or "")
        mats = {c.claim_id for c in material_claims(t.report)}
        trn = sorted({f.code for f in named if f.code.startswith("OVS-TRN-") and set(f.claim_ids) & mats})
        if trn:
            reasons.append(f"the overseer's translation checks name its material claims: {_listed(trn)}")
        ovs_errors = sorted({f.code for f in named if f.severity == "error"})
        if ovs_errors:
            reasons.append(f"the task audit names it in error-level findings: {_listed(ovs_errors)}")
        if audit is None:
            reasons.append("no verified task audit covers the deliverable")
        state, refusal = self._clearance(session, t, receipts)
        if refusal:
            reasons.append(f"clearance {state}: {refusal}")
        path = FormalPath(**{**base, "complete": not reasons}, deliverable_message_id=t.message_id, deliverable_receipt_id=t.receipt_id, receipt_status=t.status,
                          receipt_error_codes=errors, clearance=state, claims=claims, branch_checks=checks, reasons=reasons)
        return path, t

    # ------------------------------------------------------------------ the fallback
    def _fallback(self, session: DeliverySession, view: OverseerView, answers: list[Transfer], consolidation: Optional[ConsolidatedResponse], audit: Any,
                  receipts: Mapping[str, Any], keyring: KeyRing, formal: FormalPath, why: list[str], digest: str, req_ids: list[str]) -> DeliveryDecision:
        cfg = self.config
        candidates = [t for t in answers if t.report is not None and t.receipt is not None and t.status != "REJECTED" and t.delivered]
        non_candidates = [f"{t.message_id}: " + ("REJECTED by the channel" if t.status == "REJECTED" else "no delivered report") for t in answers
                          if t not in candidates]
        rank = self._canonical_ranks(candidates, consolidation)
        stage = OverseerStage(configured=self.pool is not None, ran=False, budget_s=cfg.overseer_budget_s)
        review = None
        overseer_s: Optional[float] = None
        assessed: list[Any] = []
        if not candidates:
            fb = Fallback(why=why, overseer=stage, non_candidates=non_candidates, min_selected_accuracy=cfg.min_selected_accuracy,
                          selection=["no candidate: no answer to the input was delivered by the channel"])
            return self._withhold(session, formal, fb, consolidation, audit, digest, req_ids, ["no candidate answer was delivered"], None, kind="no_candidate")
        if self.pool is None:
            stage = stage.model_copy(update={"error": "no overseer agent is configured (no knowledge pack and provider factory)"})
        else:
            oc = self._overseer_clock
            with self._lock:  # one overseer stage at a time: its deadline is opened only once the lock is held
                oc.open(cfg.overseer_budget_s)
                start = float(oc.started_at or self.clock())
                error = None
                try:
                    review = session.hub.review_pool([session.task_key], self.pool)
                except Exception as exc:
                    error = f"the overseer review failed ({type(exc).__name__}: {_cut(str(exc), 200)})"
                end = float(self.clock())
                calls = oc.close()
            overseer_s = round(end - start, 6)
            timed_out = end > start + cfg.overseer_budget_s or any(c["state"] in ("skipped_budget", "late") for c in calls)
            hr = review.reviews.get(session.channel.channel_uid) if review is not None else None
            standings: list[VerdictStanding] = []
            if hr is not None:
                assessed = list(hr.assessments)
                standings = [_verdict_standing(va) for va in assessed]
            stage = OverseerStage(configured=True, ran=review is not None, timed_out=timed_out, error=error, budget_s=cfg.overseer_budget_s,
                                  started_at_s=round(start - session.started_at, 6), elapsed_s=overseer_s,
                                  plan_id=review.plan.plan_id if review is not None else None, instances=list(review.plan.instances) if review is not None else [],
                                  plan_reasons=list(review.plan.reasons) if review is not None else [],
                                  runs=[{"agent_id": r.agent_id, "status": r.status, "reason": r.reason} for r in (hr.runs if hr is not None else ())],
                                  provider_calls=calls, verdicts=standings, verdicts_audit_id=hr.audit.audit_id if hr is not None else None,
                                  task_audit_id=hr.task_audit.audit_id if hr is not None else None)
        audit = self._latest_task_audit(session.hub.auditor, session.channel.channel_uid, keyring) or audit
        view = session.hub.auditor.view(session.channel.channel_uid)
        candidates = [view.by_message.get(t.message_id or "", t) for t in candidates]
        counted = [va for va, st in zip(assessed, stage.verdicts) if st.counted]
        assessments = self._assess(session, view, candidates, consolidation, counted, assessed, audit, receipts, keyring, rank)
        established = stage.ran and not stage.timed_out and stage.error is None
        if not established:
            what = ("the overseer stage ran out of its budget" if stage.timed_out else (stage.error or "the overseer stage did not run"))
            kind = "timed_out" if stage.timed_out else ("not_configured" if not stage.configured else "error")
            return self._no_accuracy(session, formal, why, stage, assessments, non_candidates, consolidation, audit, digest, req_ids, review, overseer_s, what,
                                     kind)
        chosen, selection, kind = self._select(assessments)
        fb = Fallback(why=why, overseer=stage, candidates=assessments, non_candidates=non_candidates, chosen_message_id=chosen.message_id if chosen else None,
                      min_selected_accuracy=cfg.min_selected_accuracy, selection=selection)
        if chosen is None:
            return self._withhold(session, formal, fb, consolidation, audit, digest, req_ids, selection, review, overseer_s=overseer_s, kind=kind)
        t = view.by_message[chosen.message_id]
        label = self._label("overseer_selected", formal=formal, chosen=chosen)
        rec = self._receipt(session, mode="overseer_selected", label=label, formal=formal, fallback=fb, end=float(self.clock()), overseer_s=overseer_s,
                            reasons=[f"the formal path did not complete; the overseer agents' validated review selected answer {chosen.message_id} "
                                     f"({chosen.accuracy_fraction} material claims accurate, above {cfg.min_selected_accuracy:g})"],
                            consolidation=consolidation, audit=audit, digest=digest, req_ids=req_ids, delivered=t)
        return self._delivered(rec, t, consolidation, review)

    @staticmethod
    def _canonical_ranks(candidates: list[Transfer], consolidation: Optional[ConsolidatedResponse]) -> dict[str, tuple[int, int, int, Optional[str], bool]]:
        """``message id -> (rank, ..., group id, canonical)``: the consolidation's canonical choice first (its deliverable
        answer), then each group's representative in the consolidation's group order, then the other members, then
        answers in no group; journal order within each."""
        out: dict[str, tuple[int, int, int, Optional[str], bool]] = {}
        if consolidation is not None:
            for gi, g in enumerate(consolidation.groups):
                for m in g.members:
                    canonical = m.message_id == g.canonical_message_id
                    tier = 0 if (canonical and m.message_id == consolidation.deliverable_message_id) else (1 if canonical else 2)
                    out[m.message_id] = (tier, gi, m.seq, g.group_id, canonical)
        n = len(consolidation.groups) if consolidation is not None else 0
        for t in candidates:
            out.setdefault(t.message_id or "", (3, n, t.seq, None, False))
        return out

    def _integrity(self, session: DeliverySession, t: Transfer, consolidation: Optional[ConsolidatedResponse], receipts: Mapping[str, Any]) -> list[str]:
        """Why ``t`` may not be delivered whatever its accuracy (empty when it may): the consolidation excludes it (an
        error-level finding on its receipt or in the task audit, a clearance not passed, a repeated fault), or the
        router may not act on its clearance now; its payload digest must be its envelope's."""
        out: list[str] = []
        if consolidation is not None:
            ex = next((e for e in consolidation.excluded if e.message_id == t.message_id), None)
            if ex is not None and ex.repeated:
                out.append("it repeats a fault of an earlier answer (OVS-REP-001): never delivered")
            if ex is not None:
                out.append(f"the consolidation excludes it ({_cut('; '.join(ex.reasons), 300)}"
                           + (f"; codes {_listed(ex.codes)}" if ex.codes else "") + "): an excluded answer is never delivered")
        state, refusal = self._clearance(session, t, receipts)
        if refusal:
            out.append(f"clearance {state}: {refusal}")
        try:
            if t.payload is None or t.envelope is None or payload_hash(t.payload) != t.envelope.get("payload_sha256"):
                out.append("its journaled payload does not carry its envelope's digest")
        except Exception:
            out.append("its journaled payload cannot be digested")
        return out

    def _assess(self, session: DeliverySession, view: OverseerView, candidates: list[Transfer], consolidation: Optional[ConsolidatedResponse],
                counted: list[Any], assessed: list[Any], audit: Any, receipts: Mapping[str, Any], keyring: KeyRing,
                rank: Mapping[str, tuple]) -> list[CandidateAssessment]:
        thr = self.config.min_selected_accuracy
        out: list[CandidateAssessment] = []
        order = sorted(candidates, key=lambda t: rank.get(t.message_id or "", (9, 0, t.seq, None, False))[:3])
        for pos, t in enumerate(order):
            assert t.report is not None and t.receipt is not None
            reviewed_by = sorted({va.agent_id for va in counted if t.message_id in va.transfers_reviewed})
            mats = material_claims(t.report)
            claims = [_assess_claim(t, c, reviewed_by=reviewed_by, counted=counted, all_assessed=assessed, audit=audit, keyring=keyring, view=view) for c in mats]
            accurate = sum(1 for c in claims if c.assessment == "accurate")
            total = len(claims)
            answer_level = _answer_level_errors(t.receipt, [c.claim_id for c in mats])
            refuted = any(c.refuted_by_signed_result for c in claims)
            faulted = refuted or any(c.faulted_by_check for c in claims) or bool(answer_level)
            integrity = self._integrity(session, t, consolidation, receipts)
            r = rank.get(t.message_id or "", (9, 0, t.seq, None, False))
            out.append(CandidateAssessment(
                message_id=t.message_id or "", receipt_id=t.receipt_id, agent_id=t.sender_agent_id, report_id=t.report_id, seq=t.seq, group_id=r[3],
                canonical=bool(r[4]), canonical_rank=pos, deliverable=not integrity, integrity_reasons=integrity, refuted=refuted, faulted=faulted,
                answer_level_faults=answer_level, material_claims=total, accurate=accurate, accuracy=round(accurate / total, 6) if total else 0.0,
                accuracy_fraction=f"{accurate}/{total}", above_threshold=accuracy_above(accurate, total, thr), reviewed_by=reviewed_by, claims=claims))
        return out

    def _select(self, cands: list[CandidateAssessment]) -> tuple[Optional[CandidateAssessment], list[str], str]:
        """The deterministic selection (module docstring): integrity gates, the refutation rule, the stricter fault rule,
        then the highest accuracy, ties to the canonical rank; delivered only above the threshold."""
        thr = self.config.min_selected_accuracy
        notes: list[str] = [f"{c.message_id} ({c.agent_id}): accuracy {c.accuracy_fraction}" + (" (refuted by a signed engine result)" if c.refuted else "")
                            + (" (faulted by a deterministic check)" if c.faulted and not c.refuted else "")
                            + ("" if c.deliverable else f" (not deliverable: {_cut('; '.join(c.integrity_reasons), 300)})") for c in cands]
        pool = [c for c in cands if c.deliverable]
        if any(not c.refuted for c in cands):
            dropped = [c.message_id for c in pool if c.refuted]
            pool = [c for c in pool if not c.refuted]
            if dropped:
                notes.append(f"never delivered while another candidate has no refuted claim: {_listed(dropped)} (a signed engine result refutes a material claim)")
        if any(not c.faulted for c in cands):
            dropped = [c.message_id for c in pool if c.faulted]
            pool = [c for c in pool if not c.faulted]
            if dropped:
                notes.append(f"never delivered while another candidate has no fault a deterministic check names: {_listed(dropped)}")
        if not pool:
            notes.append("no candidate is acceptable: withheld")
            return None, notes, "no_acceptable"
        best = sorted(pool, key=lambda c: (-Fraction(c.accurate, c.material_claims) if c.material_claims else 0, c.canonical_rank))[0]
        ties = [c.message_id for c in pool if c is not best and c.material_claims and best.material_claims
                and Fraction(c.accurate, c.material_claims) == Fraction(best.accurate, best.material_claims)]
        if ties:
            notes.append(f"tie at {best.accuracy_fraction} with {_listed(ties)}: broken by the consolidation's canonical choice")
        if not best.above_threshold:
            notes.append(f"the best acceptable candidate {best.message_id} has accuracy {best.accuracy_fraction}, not above {thr:g}: withheld, never "
                         "delivered as selected")
            return None, notes, "below_threshold"
        notes.append(f"selected {best.message_id} ({best.agent_id}): accuracy {best.accuracy_fraction}, above {thr:g}")
        return best, notes, ""

    def _no_accuracy(self, session, formal, why, stage, assessments, non_candidates, consolidation, audit, digest, req_ids, review, overseer_s,
                     what: str, kind: str) -> DeliveryDecision:
        cfg = self.config
        selection = [f"{what}: no accuracy above {cfg.min_selected_accuracy:g} has been established"]
        chosen = None
        if cfg.on_overseer_timeout == "deliver_canonical_not_checked":
            canonical = consolidation.deliverable_message_id if (consolidation is not None and consolidation.status in DELIVERABLE_STATUSES) else None
            cand = next((c for c in assessments if c.message_id == canonical), None) if canonical else None
            if cand is None:
                selection.append("the operator's configuration delivers the consolidation's canonical answer, but there is none "
                                 f"(consolidation {consolidation.status if consolidation is not None else 'missing'}): withheld")
            elif not cand.deliverable:
                selection.append(f"the canonical answer {cand.message_id} is not deliverable ({_cut('; '.join(cand.integrity_reasons), 300)}): withheld")
            elif cand.refuted and any(not c.refuted for c in assessments):
                selection.append(f"the canonical answer {cand.message_id} has a material claim a signed engine result refutes while another candidate has "
                                 "none: withheld")
            elif cand.faulted and any(not c.faulted for c in assessments):
                selection.append(f"the canonical answer {cand.message_id} carries a fault a deterministic check names while another candidate has none: "
                                 "withheld")
            else:
                chosen = cand
                selection.append(f"delivered by the operator's configuration (on_overseer_timeout=deliver_canonical_not_checked): the consolidation's "
                                 f"canonical answer {cand.message_id}, labelled NOT CHECKED")
        fb = Fallback(why=why, overseer=stage, candidates=assessments, non_candidates=non_candidates, chosen_message_id=chosen.message_id if chosen else None,
                      min_selected_accuracy=cfg.min_selected_accuracy, selection=selection)
        if chosen is None:
            return self._withhold(session, formal, fb, consolidation, audit, digest, req_ids, selection, review, overseer_s=overseer_s, kind="no_accuracy")
        view = session.hub.auditor.view(session.channel.channel_uid)
        t = view.by_message[chosen.message_id]
        label = self._label("not_checked", formal=formal, kind=kind)
        rec = self._receipt(session, mode="not_checked", label=label, formal=formal, fallback=fb, end=float(self.clock()), overseer_s=overseer_s,
                            reasons=selection, consolidation=consolidation, audit=audit, digest=digest, req_ids=req_ids, delivered=t)
        return self._delivered(rec, t, consolidation, review)

    def _withhold(self, session, formal, fb, consolidation, audit, digest, req_ids, reasons, review, *, overseer_s=None, kind: str = "") -> DeliveryDecision:
        label = self._label("withheld", formal=formal, kind=kind)
        rec = self._receipt(session, mode="withheld", label=label, formal=formal, fallback=fb, end=float(self.clock()), overseer_s=overseer_s,
                            reasons=list(reasons), consolidation=consolidation, audit=audit, digest=digest, req_ids=req_ids)
        return DeliveryDecision(mode="withheld", delivered=False, message_id=None, label=label, receipt=rec, consolidation=consolidation, review=review)

    # ------------------------------------------------------------------ labels, receipts, payloads
    #: The withheld labels' fixed wording, per cause (the receipt's ``reasons`` and ``fallback`` carry the details).
    _WITHHELD_WHY = {
        "no_input": "no input with an answer to deliver was found",
        "no_candidate": "no candidate answer was delivered by the channel",
        "no_accuracy": "the overseer stage established no accuracy",
        "no_acceptable": "no candidate passes the integrity gates and the refutation rules",
        "below_threshold": "no acceptable candidate's validated accuracy is above the threshold",
        "internal": "the delivery policy failed internally",
    }
    #: The not_checked label's fixed wording, per cause.
    _NO_ACCURACY_WHY = {"timed_out": "the overseer stage ran out of its budget", "error": "the overseer stage failed",
                        "not_configured": "no overseer agent is configured"}

    def _label(self, mode: str, *, formal: Optional[FormalPath] = None, chosen: Optional[CandidateAssessment] = None, kind: str = "") -> str:
        """The label the delivered payload carries: a fixed template with figures only (never reason or agent text). Only
        ``formally_checked`` claims a check; every other label says it is not formally checked and not verified
        (:func:`is_fallback_label_honest`)."""
        cfg = self.config
        if mode == "formally_checked":
            n = sum(1 for c in (formal.claims if formal else []) if c.eligible)
            return (f"FORMALLY CHECKED within the {cfg.translation_budget_s:g} s translation budget: each of the {n} material eligible claim(s) was "
                    "translated, decided positively by the engine as encoded and passed the release rule, and the transfer audit cleared the answer. "
                    "This proves properties of the encodings only.")
        if mode == "overseer_selected" and chosen is not None:
            return (f"OVERSEER-SELECTED (not formally checked, not verified): the formal path did not complete; the overseer agents' validated "
                    f"review gives {chosen.accuracy_fraction} material claims accurate, above the {cfg.min_selected_accuracy:g} threshold. The "
                    "selection is advisory; the delivery receipt gives the reasons and the evidence.")
        if mode == "not_checked":
            return (f"NOT CHECKED (not formally checked, not verified, no accuracy established): {self._NO_ACCURACY_WHY.get(kind, 'no accuracy was established')}; "
                    "delivered as the consolidation's canonical answer by the operator's configuration.")
        return (f"WITHHELD (not formally checked, not verified): no answer is delivered; {self._WITHHELD_WHY.get(kind, 'the formal path did not complete')}. "
                "The delivery receipt gives the scores and the reasons.")

    def _receipt(self, session: DeliverySession, *, mode: str, label: str, formal: FormalPath, fallback: Optional[Fallback], end: float,
                 overseer_s: Optional[float], reasons: Sequence[str], consolidation: Optional[ConsolidatedResponse] = None, audit: Any = None,
                 digest: Optional[str] = None, req_ids: Sequence[str] = (), delivered: Optional[Transfer] = None) -> DeliveryReceipt:
        cfg = self.config
        ch = session.channel
        plan = ch.plan
        payload_sha = None
        if delivered is not None and delivered.payload is not None:
            payload_sha = payload_hash(delivered.payload)
        rec = DeliveryReceipt(
            receipt_id=uuid.uuid4().hex, task_id=plan.task_id, request_id=plan.request_id, channel_uid=ch.channel_uid, user_input_sha256=digest,
            request_message_ids=list(req_ids), mode=mode, delivered=delivered is not None, label=label,  # type: ignore[arg-type]
            delivered_message_id=delivered.message_id if delivered is not None else None, delivered_receipt_id=delivered.receipt_id if delivered is not None else None,
            delivered_agent_id=delivered.sender_agent_id if delivered is not None else None, delivered_report_id=delivered.report_id if delivered is not None else None,
            delivered_payload_sha256=payload_sha, translation_budget_s=cfg.translation_budget_s, overseer_budget_s=cfg.overseer_budget_s,
            min_selected_accuracy=cfg.min_selected_accuracy, time_to_decision_s=round(end - session.started_at, 6), translation_s=formal.translation_s,
            overseer_s=overseer_s, formal=formal, fallback=fallback, consolidation_id=consolidation.consolidation_id if consolidation is not None else None,
            consolidation_status=consolidation.status if consolidation is not None else None, task_audit_id=audit.audit_id if audit is not None else None,
            reasons=[_cut(r) for r in reasons], created_at=_now())
        return sign_delivery_receipt(rec, session.hub.auditor.keyring)

    @staticmethod
    def _delivered(rec: DeliveryReceipt, t: Transfer, consolidation: Optional[ConsolidatedResponse], review: Any) -> DeliveryDecision:
        payload = copy.deepcopy(t.payload)
        reasons, selection, accuracy = _evidence_of(rec)
        answer = DeliveredAnswer(mode=rec.mode, label=rec.label, message_id=t.message_id or "", report_id=t.report_id, agent_id=t.sender_agent_id,
                                 payload=payload, payload_sha256=payload_hash(payload), delivery_receipt_id=rec.receipt_id, formal_reasons=reasons,
                                 selection=selection, accuracy_fraction=accuracy)
        return DeliveryDecision(mode=rec.mode, delivered=True, message_id=t.message_id, label=rec.label, receipt=rec, answer=answer,
                                consolidation=consolidation, review=review)
