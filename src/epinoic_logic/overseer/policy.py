"""Router policy: when the router may act on a transfer, and when it may release a synthesis to the student.

The router reads two things before it acts: the channel's receipt (what the channel checked) and the Overseer's
clearance (whether the receipt is the exact, unaltered image of what was checked, and whether the results it cites are
signed engine runs of the problems they name). This module turns them into a decision. It decides nothing about the
content: a transfer the channel REJECTED audits PASSED and is still never acted on.

* :func:`may_act` (``act_decision`` gives the reason): true only when ALL of these hold (design section 7):

  - the receipt is a receipt, and its status is not REJECTED;
  - the clearance is a :class:`~epinoic_logic.overseer.contracts.TransferClearance` for that receipt's message and
    receipt id;
  - the clearance state is ``AUDIT_PASSED`` or ``AUDIT_PASSED_WITH_FINDINGS``;
  - the clearance was issued for THAT receipt's digest: the canonical digest of the receipt object the router is
    about to act on equals the journaled ``receipt_sha256`` (and the ``presented_receipt_sha256`` when the router
    presented one). A receipt edited after its clearance is never acted on.

  ``AUDIT_PENDING`` and ``AUDIT_FAILED`` are never treated as passed (non-success is never shown as success). The
  clearance must also be the latest the auditor journaling its channel issued for the message (the auditor passed, or
  the live one registered for the channel), no later task audit may mark the transfer other than passed, and custody is
  re-checked at the decision (review round 3: a held clearance is never better than the auditor's current word; a
  clearance built outside the auditor, or naming a channel no auditor journals, is refused).

* **Bounded PENDING wait** (:func:`check_before_acting`): the router asks for a clearance immediately before acting;
  on ``AUDIT_PENDING`` it may wait once, at most :data:`MAX_PENDING_WAIT_MS` (250 ms) of replay, and a transfer still
  pending after that is HELD for the batch audit (``hold=True``), never acted on. :func:`bounded_wait_ms` clamps any
  requested wait to that bound; the hub's ``clearance`` applies it too.

* :func:`may_release` (``release_decision`` gives the reason) gates the student-facing synthesis. It requires a
  ``final=True`` task audit that verifies under the audit key, is the latest task audit of its channel and is superseded
  by none, covers the channel as it stands (no transfer was journaled after the audit's journal head, and the journal
  chain verifies), has state ``AUDIT_PASSED`` or ``AUDIT_PASSED_WITH_FINDINGS``, and includes the synthesis transfer,
  whose own state is passed and whose journaled receipt digest equals the receipt presented. The synthesis receipt
  itself must not be REJECTED, and must carry no error-level finding: an audit vouches for the receipt, not for the
  content, so a synthesis the channel itself says miscommunicates its sources (INT-LEDGER-023, say) is never released
  (the reason names the codes; release then needs a new synthesis, never the agent's or the router's word). Custody is
  re-checked at release: the synthesis message (and every transfer it depends on) in the live channel's log must still
  be the journaled payload and header (the auditor attaches the probe to the journal), and the message the router is
  about to release, when given, must carry the journaled payload digest.

Agent verdicts play no part here: ``OVS-AGENT-*`` findings never change a clearance (decision 16), and no function of
this module reads a verdict. Every function returns False (or a refusing decision) instead of raising on a malformed
input.

Deviations from ``docs/OVERSEER_DESIGN.md`` section 7, listed as each stage requires:

* ``may_release`` takes the channel's task audits (``audits``, as ``TransferAuditor.audits`` lists them) and its
  journal (``journal``) as required keyword arguments: "latest, superseded by none" and "journal head equal to the
  channel's current head" cannot be decided from the audit alone. "Current head" is read as "no EVENT entry after the
  audit's head": the auditor journals its own clearance decisions and the seal after the audit it issued, and those
  records change no transfer;
* ``may_release`` also requires the synthesis transfer's own state to be passed and the presented synthesis receipt to
  carry the journaled receipt digest (the router releases the receipt it holds, so that copy is the one checked);
* ``may_release`` refuses a synthesis receipt with any error-level finding, and re-checks custody at release through
  the probe the auditor attaches to the journal (``ChannelJournal.live_custody``), and the released message when given
  (review round 1);
* the decisions carry a ``reason`` (:class:`PolicyDecision`); ``may_act`` and ``may_release`` return its ``allowed``;
* ``may_release`` refuses a FINAL audit whose replays ran inline (its OVS-AUDIT-002: replay independence not
  established, decision 20) unless the audit's signed coverage records that the operator configured inline release
  (``TransferAuditor(inline_final_release=True)``; contained round c1: a warning alone let such an audit release).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from ..channel.contracts import TransmissionStatus
from ..channel.events import model_json
from ..ir.canonical import sha256_hex
from .audit import INLINE_FINAL_MESSAGE, verify_audit
from .contracts import OverseerAudit, TransferClearance

__all__ = [
    "MAX_PENDING_WAIT_MS", "ACTABLE_STATES", "PolicyDecision", "receipt_digest", "bounded_wait_ms", "act_decision", "may_act",
    "check_before_acting", "release_decision", "may_release",
]

#: The longest the router waits for outstanding replay before a PENDING transfer is held for the batch audit.
MAX_PENDING_WAIT_MS = 250
#: The only clearance states the router may act on.
ACTABLE_STATES = frozenset({"AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS"})
_AFTER_AUDIT_RECORDS = frozenset({"clearance", "seal"})


@dataclass(frozen=True)
class PolicyDecision:
    """The router's decision about one transfer or one release. ``allowed`` is the only field that permits anything;
    ``hold`` means the transfer is held for the batch audit (still PENDING after the bounded wait)."""
    allowed: bool
    reason: str
    state: Optional[str] = None
    hold: bool = False
    clearance: Optional[TransferClearance] = None


def receipt_digest(receipt: Any) -> Optional[str]:
    """The digest the journal keeps for a receipt: sha256 of its canonical JSON (``mode=json``, ``exclude_none``).
    None when the object cannot be serialised as a receipt."""
    try:
        if not hasattr(receipt, "model_dump"):
            return None
        return sha256_hex(model_json(receipt))
    except Exception:
        return None


def bounded_wait_ms(wait_ms: Any) -> int:
    """``wait_ms`` clamped to ``[0, MAX_PENDING_WAIT_MS]`` (anything that is not a finite number waits 0 ms)."""
    try:
        w = float(wait_ms)
    except (TypeError, ValueError):
        return 0
    if w != w or w <= 0:  # NaN or not positive
        return 0
    return int(min(w, MAX_PENDING_WAIT_MS))


def _status_value(receipt: Any) -> Optional[str]:
    status = getattr(receipt, "status", None)
    return getattr(status, "value", status) if status is not None else None


def act_decision(receipt: Any, clearance: Any, *, auditor: Any = None) -> PolicyDecision:
    """Whether the router may act on ``receipt`` given ``clearance`` (module docstring), with the reason. The clearance
    must also still be the word of the auditor that journals its channel (``auditor``, or the live auditor registered
    for ``clearance.channel_uid``; ``TransferAuditor.clearance_current``): the latest clearance it journaled for the
    message, not contradicted by a later task audit, with custody re-checked now. A clearance held across an edit or a
    failing audit, built by router code, or naming a channel no auditor journals is refused (review round 3)."""
    if not isinstance(clearance, TransferClearance):
        return PolicyDecision(False, "no clearance: the Overseer's clearance is required before acting")
    state = clearance.state
    mid, rid = getattr(receipt, "message_id", None), getattr(receipt, "receipt_id", None)
    if not isinstance(mid, str) or not isinstance(rid, str) or _status_value(receipt) is None:
        return PolicyDecision(False, "not a receipt", state, clearance=clearance)
    if _status_value(receipt) == TransmissionStatus.REJECTED.value:
        return PolicyDecision(False, "the channel REJECTED this transfer: it was not delivered and is never acted on", state, clearance=clearance)
    if clearance.message_id != mid or clearance.receipt_id != rid:
        return PolicyDecision(False, "the clearance was issued for another transfer or receipt", state, clearance=clearance)
    if state not in ACTABLE_STATES:
        return PolicyDecision(False, f"clearance state {state}: not passed", state, hold=state == "AUDIT_PENDING", clearance=clearance)
    digest = receipt_digest(receipt)
    if digest is None or clearance.receipt_sha256 is None or digest != clearance.receipt_sha256:
        return PolicyDecision(False, "the receipt differs from the receipt the clearance was issued for (edited after issue or after clearance)",
                              state, clearance=clearance)
    if clearance.presented_receipt_sha256 is not None and digest != clearance.presented_receipt_sha256:
        return PolicyDecision(False, "the receipt differs from the receipt presented for clearance", state, clearance=clearance)
    if auditor is None:
        from .audit import auditor_for_channel
        auditor = auditor_for_channel(clearance.channel_uid)
        if auditor is None:
            return PolicyDecision(False, "no auditor of this process journals the clearance's channel: the clearance cannot be the auditor's word", state,
                                  clearance=clearance)
    try:
        why = auditor.clearance_current(clearance)
    except Exception as exc:
        why = f"the clearance could not be re-checked with the auditor ({type(exc).__name__})"
    if why is not None:
        return PolicyDecision(False, why, state, clearance=clearance)
    return PolicyDecision(True, "ok", state, clearance=clearance)


def may_act(receipt: Any, clearance: Any, *, auditor: Any = None) -> bool:
    """True only when the router may act on ``receipt`` (see :func:`act_decision`)."""
    return act_decision(receipt, clearance, auditor=auditor).allowed


def check_before_acting(hub: Any, task_key: Any, receipt: Any, *, wait_ms: int = MAX_PENDING_WAIT_MS) -> PolicyDecision:
    """Ask ``hub`` for the clearance of ``receipt``'s transfer, presenting the receipt the router holds; on PENDING wait
    once, at most :data:`MAX_PENDING_WAIT_MS`; then decide. A transfer still pending is held (``hold=True``), never
    acted on. ``hub`` is anything with ``clearance(task_key, message_id, *, receipt, wait_ms)``."""
    mid = getattr(receipt, "message_id", None)
    if not isinstance(mid, str):
        return PolicyDecision(False, "not a receipt")
    wait = bounded_wait_ms(wait_ms)
    try:
        clearance_fn: Callable[..., Any] = hub.clearance
        clr = clearance_fn(task_key, mid, receipt=receipt, wait_ms=0)
        if isinstance(clr, TransferClearance) and clr.state == "AUDIT_PENDING" and wait > 0:
            clr = clearance_fn(task_key, mid, receipt=receipt, wait_ms=wait)
    except Exception as exc:  # no auditor, an unknown task: never acted on
        return PolicyDecision(False, f"no clearance could be obtained ({type(exc).__name__})")
    decision = act_decision(receipt, clr, auditor=getattr(hub, "auditor", None))
    if isinstance(clr, TransferClearance) and clr.state == "AUDIT_PENDING":
        return PolicyDecision(False, f"still AUDIT_PENDING after waiting at most {wait} ms: held for the batch audit", clr.state, hold=True, clearance=clr)
    return decision


# ============================================================================================ release
def _journal_covers(audit: OverseerAudit, journal: Any) -> Optional[str]:
    """None when the journal verifies and no event was journaled after the audit's head; else why not."""
    head = audit.journal_head
    if head is None:
        return "the audit names no journal head"
    try:
        if journal.channel_uid != audit.channel_uid:
            return "the journal belongs to another channel"
        if journal.verify_chain() is not None:
            return "the journal chain does not verify"
        entries = journal.entries()
    except Exception:
        return "the journal cannot be read"
    if getattr(journal, "evicted", False):
        return "the journal was evicted: the audit cannot be compared with it"
    if head.index < 1 or head.index > len(entries) or entries[head.index - 1].entry_hash != head.entry_hash:
        return "the audit's journal head is not an entry of this journal"
    later = [e for e in entries[head.index:] if e.event is not None or e.kind not in _AFTER_AUDIT_RECORDS]
    if later:
        return f"{len(later)} journal entr{'y' if len(later) == 1 else 'ies'} (transfers or gaps) after the audit: it does not cover the channel as it stands"
    return None


def release_decision(synthesis_receipt: Any, task_audit: Any, keyring: Any, *, audits: Sequence[Any], journal: Any, message: Any = None) -> PolicyDecision:
    """Whether the student-facing synthesis carried by ``synthesis_receipt`` may be released (module docstring).
    ``message``: the synthesis envelope the router is about to release (its payload is what the student reads)."""
    if not isinstance(task_audit, OverseerAudit):
        return PolicyDecision(False, "no task audit")
    state = task_audit.state
    if task_audit.scope != "task":
        return PolicyDecision(False, f"a {task_audit.scope}-scope audit is not a task audit", state)
    if not task_audit.final:
        return PolicyDecision(False, "the task audit is not FINAL", state)
    try:
        signed = verify_audit(task_audit, keyring)
    except Exception:
        signed = False
    if not signed:
        return PolicyDecision(False, "the task audit does not verify under the audit key", state)
    try:
        task_audits = [a for a in audits if isinstance(a, OverseerAudit) and a.scope == "task" and a.channel_uid == task_audit.channel_uid]
    except TypeError:
        return PolicyDecision(False, "the channel's audits were not given", state)
    if not task_audits or task_audits[-1].audit_id != task_audit.audit_id:
        return PolicyDecision(False, "the task audit is not the latest task audit of its channel", state)
    if any(a.supersedes == task_audit.audit_id for a in task_audits):
        return PolicyDecision(False, "the task audit was superseded", state)
    if state not in ACTABLE_STATES:
        return PolicyDecision(False, f"task audit state {state}: not passed", state)
    try:
        inline = any(f.code == "OVS-AUDIT-002" and f.message == INLINE_FINAL_MESSAGE for f in task_audit.report.findings)
        inline_ok = task_audit.coverage.inline_final_release is True
    except AttributeError:
        return PolicyDecision(False, "the task audit cannot be read", state)
    if inline and not inline_ok:
        return PolicyDecision(False, "the FINAL audit's replays ran inline (OVS-AUDIT-002): replay independence is not established, and inline release "
                                     "was not configured by the operator (decision 20: process mode is the only mode a FINAL audit accepts as independent)", state)
    mid = getattr(synthesis_receipt, "message_id", None)
    if not isinstance(mid, str) or _status_value(synthesis_receipt) is None:
        return PolicyDecision(False, "not a receipt", state)
    if _status_value(synthesis_receipt) == TransmissionStatus.REJECTED.value:
        return PolicyDecision(False, "the channel REJECTED the synthesis: it was not delivered", state)
    try:
        errors = sorted({f.code for f in synthesis_receipt.findings if getattr(f, "severity", None) == "error"})
    except (AttributeError, TypeError):
        return PolicyDecision(False, "not a receipt", state)
    if errors:
        return PolicyDecision(False, f"the synthesis receipt carries error-level findings {errors}: the channel says the synthesis miscommunicates what it "
                                     "presents, so it is not released (a corrected synthesis is needed)", state)
    if mid not in task_audit.message_ids:
        return PolicyDecision(False, "the task audit does not include the synthesis transfer", state)
    if task_audit.transfer_states.get(mid) not in ACTABLE_STATES:
        return PolicyDecision(False, f"the synthesis transfer's state is {task_audit.transfer_states.get(mid)}: not passed", state)
    why = _journal_covers(task_audit, journal)
    if why is not None:
        return PolicyDecision(False, why, state)
    event = next((e.event for e in journal.entries() if e.event is not None and e.event.message_id == mid), None)
    if event is None or event.kind != "relay_synthesis":
        return PolicyDecision(False, "the transfer is not a journaled synthesis", state)
    digest = receipt_digest(synthesis_receipt)
    if digest is None or digest != event.receipt_sha256:
        return PolicyDecision(False, "the synthesis receipt differs from the journaled receipt", state)
    if message is not None:
        try:
            from ..ir.canonical import canonical_json
            if getattr(message, "message_id", None) != mid or sha256_hex(canonical_json(message.payload)) != event.payload_sha256:
                return PolicyDecision(False, "the synthesis message to be released is not the journaled synthesis (payload digest)", state)
        except Exception:
            return PolicyDecision(False, "the synthesis message to be released cannot be compared with the journal", state)
    probe = getattr(journal, "live_custody", None)
    if callable(probe):
        try:
            faults = probe(mid)
        except Exception as exc:
            return PolicyDecision(False, f"custody of the synthesis could not be re-checked at release ({type(exc).__name__})", state)
        if faults:
            return PolicyDecision(False, f"custody re-checked at release: {sorted(set(faults))} (the synthesis or a transfer it depends on was altered after the audit)", state)
    return PolicyDecision(True, "ok", state)


def may_release(synthesis_receipt: Any, task_audit: Any, keyring: Any, *, audits: Sequence[Any], journal: Any, message: Any = None) -> bool:
    """True only when the synthesis may be released to the student (see :func:`release_decision`)."""
    return release_decision(synthesis_receipt, task_audit, keyring, audits=audits, journal=journal, message=message).allowed
