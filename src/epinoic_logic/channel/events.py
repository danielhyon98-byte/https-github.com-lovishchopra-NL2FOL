"""Channel events: one immutable record per channel call, for observers such as the Overseer.

A ``ChannelEvent`` is built inside the channel call, before anything is returned to the router,
from the channel's public state: the envelope as the log holds it, the receipt as issued, the
typed copy the channel keeps, the raw text a specialist sent, every engine result the call
produced (captured by :func:`~epinoic_logic.engine.sink.capture_results`), the cross-agent pool
after the call and what the call added to the channel's records. Every field is a string, an
integer, a boolean or a tuple, so one event can be shared by every observer: an observer that
tries to change it cannot affect another observer or the channel.

The channel never imports the overseer package; this module imports nothing from ``bus.py``
either. It duck-types the channel, so a channel without the observer hook can still be observed
by :func:`observe_call` (the Overseer's tests drive it by hand).

``snapshot_event`` reads only; it never changes the channel or the objects it returns. Canonical
JSON is the repository's (sorted keys, no whitespace, UTF-8), so a digest computed here equals
the digest the channel's own envelope check computes (``payload_hash``).

Deviations from ``docs/OVERSEER_DESIGN.md`` section 5.2, all additive:

* ``snapshot_event`` takes ``channel_uid`` and ``seq`` explicitly (the observation state that owns them is
  :class:`ObservationState`, kept beside a channel without the bus hook, or on it as ``_observation`` with it);
* extra fields: ``header_sha256`` (the header digest without the payload, so a payload edit and a header edit are
  told apart), ``channel_json`` (key id, solver configuration, branch, hooks configured; on every event),
  ``pool_before`` (the pool just before the call, for JOINT-004), ``transmitted_added``, ``recipients_added``,
  ``requests_added`` and ``log_added`` (what the call added, for RCPT-003 and the B1 sweep), ``captured_overflow``;
* ``plan_json`` is carried again on any event whose plan digest differs from the previous event's.
"""
from __future__ import annotations

import inspect
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, Sequence

from ..engine.sink import CapturedResult, capture_results
from ..ir.canonical import canonical_json, problem_digest, sha256_hex

__all__ = [
    "CapturedResult", "PoolEntry", "ChannelBefore", "ChannelEvent", "ObservationState", "EVENT_KINDS",
    "take_before", "snapshot_event", "call_record", "event_kind", "observe_call", "model_json", "header_digest",
    "OBSERVER_ERRORS_MAX",
]

#: The kinds of transfer a channel call can be.
EVENT_KINDS = ("request", "response", "response_text", "relay_forward", "relay_report", "relay_synthesis")
#: Bound of the per-channel list of observer failures.
OBSERVER_ERRORS_MAX = 64
_SIGNATURE_FIELDS = ("signature", "signature_key_id")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def model_json(obj: Any) -> str:
    """Canonical JSON of a pydantic model (``mode=json``, ``exclude_none``) or of a plain JSON value."""
    if hasattr(obj, "model_dump"):
        return canonical_json(obj.model_dump(mode="json", exclude_none=True))
    return canonical_json(obj)


def header_digest(envelope_dump: dict) -> str:
    """Digest of an envelope's header: every field except the payload and the two signature fields. A payload
    edit changes the payload hash, not this digest, so the two custody codes never double-count one edit."""
    data = {k: v for k, v in envelope_dump.items() if k not in ("payload",) + _SIGNATURE_FIELDS}
    return sha256_hex(canonical_json(data))


@dataclass(frozen=True)
class PoolEntry:
    """One formalized claim in the channel's cross-agent pool."""
    claim_id: str
    problem_digest: str
    ambiguous: bool
    agent_id: Optional[str]
    report_id: Optional[str]

    def to_dict(self) -> dict:
        return {"claim_id": self.claim_id, "problem_digest": self.problem_digest, "ambiguous": self.ambiguous, "agent_id": self.agent_id, "report_id": self.report_id}


@dataclass(frozen=True)
class ChannelBefore:
    """The small snapshot taken before a call, so the event can state what the call added."""
    n_receipts: int
    n_log: int
    n_conflicts: int
    forward_counts: tuple[tuple[str, int], ...]
    superseded: tuple[tuple[str, str], ...]
    transmitted: tuple[str, ...]
    recipients: tuple[tuple[str, tuple[str, ...]], ...]
    requests: tuple[str, ...]
    pool: tuple[PoolEntry, ...]


@dataclass(frozen=True)
class ChannelEvent:
    """Everything one channel call issued, as canonical JSON strings, digests and tuples.

    ``plan_json`` is carried on the first event of a channel and again on any event whose plan digest differs
    from the previous one; ``channel_json`` (key id, solver configuration, branch, hooks configured) on every
    event. ``envelope_json``/``receipt_json`` are ``None`` when the call raised before issuing them. With
    ``digest_only`` the content strings were dropped by a bounded journal and only their digests remain."""
    channel_uid: str
    seq: int
    kind: str
    task_id: str
    request_id: str
    plan_sha256: str
    plan_json: Optional[str]
    channel_json: Optional[str]
    message_id: Optional[str]
    receipt_id: Optional[str]
    status: Optional[str]
    delivered: bool
    returned_message: bool
    envelope_json: Optional[str]
    envelope_digest: Optional[str]
    header_sha256: Optional[str]
    payload_sha256: Optional[str]
    receipt_json: Optional[str]
    receipt_sha256: Optional[str]
    typed_kind: Optional[str]
    typed_id: Optional[str]
    typed_copy_sha256: Optional[str]
    raw_text: Optional[str]
    raw_text_sha256: Optional[str]
    call_json: str
    captured: tuple[CapturedResult, ...]
    captured_overflow: int
    pool_before: tuple[PoolEntry, ...]
    pool: tuple[PoolEntry, ...]
    conflicts_added: tuple[tuple[tuple[str, ...], Optional[str]], ...]
    forwards_added: tuple[tuple[str, str, str], ...]
    superseded_added: tuple[tuple[str, str], ...]
    transmitted_added: tuple[str, ...]
    recipients_added: tuple[tuple[str, str], ...]
    requests_added: tuple[str, ...]
    log_added: tuple[str, ...]
    raised: Optional[str]
    created_at: str
    monotonic_ns: int
    digest_only: bool = False

    def to_dict(self) -> dict:
        """The event as plain JSON values (the journal hashes this)."""
        return {
            "channel_uid": self.channel_uid, "seq": self.seq, "kind": self.kind, "task_id": self.task_id, "request_id": self.request_id,
            "plan_sha256": self.plan_sha256, "plan_json": self.plan_json, "channel_json": self.channel_json,
            "message_id": self.message_id, "receipt_id": self.receipt_id, "status": self.status, "delivered": self.delivered,
            "returned_message": self.returned_message, "envelope_json": self.envelope_json, "envelope_digest": self.envelope_digest,
            "header_sha256": self.header_sha256, "payload_sha256": self.payload_sha256, "receipt_json": self.receipt_json,
            "receipt_sha256": self.receipt_sha256, "typed_kind": self.typed_kind, "typed_id": self.typed_id,
            "typed_copy_sha256": self.typed_copy_sha256, "raw_text": self.raw_text, "raw_text_sha256": self.raw_text_sha256,
            "call_json": self.call_json, "captured": [c.to_dict() for c in self.captured], "captured_overflow": self.captured_overflow,
            "pool_before": [p.to_dict() for p in self.pool_before], "pool": [p.to_dict() for p in self.pool],
            "conflicts_added": [[list(c), r] for c, r in self.conflicts_added], "forwards_added": [list(f) for f in self.forwards_added],
            "superseded_added": [list(s) for s in self.superseded_added], "transmitted_added": list(self.transmitted_added),
            "recipients_added": [list(r) for r in self.recipients_added], "requests_added": list(self.requests_added),
            "log_added": list(self.log_added), "raised": self.raised, "created_at": self.created_at, "monotonic_ns": self.monotonic_ns,
            "digest_only": self.digest_only,
        }

    def content_size(self) -> int:
        """Characters of retained content (what a bounded journal counts)."""
        n = 0
        for s in (self.plan_json, self.channel_json, self.envelope_json, self.receipt_json, self.raw_text, self.call_json):
            n += len(s) if s else 0
        for c in self.captured:
            n += len(c.result_json) + len(c.problem_json or "")
        return n

    def as_digest_only(self) -> "ChannelEvent":
        """This event with its content strings dropped: custody stays decidable by digest, the content is gone."""
        from dataclasses import replace
        return replace(self, plan_json=None, envelope_json=None, receipt_json=None, raw_text=None,
                       captured=tuple(CapturedResult(result_id=c.result_id, key_id=c.key_id, result_json="", result_sha256=c.result_sha256,
                                                     problem_json=None, problem_digest=c.problem_digest) for c in self.captured),
                       digest_only=True)


# --------------------------------------------------------------------------------------------- snapshots
def _pool(channel: Any) -> tuple[PoolEntry, ...]:
    formalized = getattr(channel, "formalized", None) or {}
    by = getattr(channel, "formalized_by", None) or {}
    amb = getattr(channel, "ambiguous_pooled", None) or set()
    out = []
    for cid, prob in list(formalized.items()):
        owner = by.get(cid) or (None, None)
        try:
            dig = problem_digest(prob)
        except Exception:
            dig = "unavailable"
        out.append(PoolEntry(claim_id=str(cid), problem_digest=dig, ambiguous=cid in amb, agent_id=owner[0], report_id=owner[1]))
    return tuple(out)


def _log_messages(channel: Any) -> tuple:
    log = getattr(channel, "log", None)
    if log is None:
        return ()
    msgs = getattr(log, "messages", None)
    if callable(msgs):
        return tuple(msgs())
    return tuple(getattr(log, "_by_id", {}).values())


def take_before(channel: Any) -> ChannelBefore:
    """The pre-call snapshot: counts and keys of what a call may append to, and the pool."""
    forwards = getattr(channel, "forwards", None) or {}
    recipients = getattr(channel, "report_recipients", None) or {}
    return ChannelBefore(
        n_receipts=len(getattr(channel, "receipts", ()) or ()),
        n_log=len(_log_messages(channel)),
        n_conflicts=len(getattr(channel, "conflicts_seen", ()) or ()),
        forward_counts=tuple((rid, len(v)) for rid, v in forwards.items()),
        superseded=tuple((getattr(channel, "superseded", None) or {}).items()),
        transmitted=tuple(getattr(channel, "transmitted_reports", None) or {}),
        recipients=tuple((rid, tuple(sorted(v))) for rid, v in recipients.items()),
        requests=tuple(getattr(channel, "requests", None) or {}),
        pool=_pool(channel),
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return f"<{type(value).__name__}>"


#: Arguments already carried by the envelope or the raw text; the call record leaves them out.
_IN_ENVELOPE = {"request": ("user_input", "supplied_texts"), "respond": ("report",), "respond_text": ("text",), "relay": ("payload_obj",)}


def call_record(channel: Any, method: str, args: tuple, kwargs: dict) -> dict:
    """The call's arguments that the envelope does not carry (supplied-text overrides, items and constraints given,
    relay parties, ``in_reply_to``), as JSON values. A relay records the payload's type."""
    out: dict[str, Any] = {"method": method}
    try:
        sig = inspect.signature(getattr(channel, method))
        bound = sig.bind_partial(*args, **kwargs)
        arguments = dict(bound.arguments)
    except Exception:
        arguments = {f"arg{i}": a for i, a in enumerate(args)}
        arguments.update(kwargs)
    skip = _IN_ENVELOPE.get(method, ())
    for name, value in arguments.items():
        if name in skip:
            continue
        out[name] = _jsonable(value)
    if method == "relay":
        payload = arguments.get("payload_obj")
        out["payload_type"] = type(payload).__name__ if payload is not None else None
    if method == "request":
        out["user_input_sha256_given"] = sha256_hex(arguments.get("user_input") or "")
    return out


def event_kind(method: str, args: tuple, kwargs: dict, channel: Any = None) -> str:
    """``request``, ``response``, ``response_text`` or, for a relay, ``relay_forward`` (a report forwarded by the
    router), ``relay_report`` (any other report) or ``relay_synthesis``."""
    if method in ("request", "respond_text"):
        return "request" if method == "request" else "response_text"
    if method == "respond":
        return "response"
    if method == "relay":
        try:
            bound = inspect.signature(getattr(channel, method)).bind_partial(*args, **kwargs).arguments if channel is not None else {}
        except Exception:
            bound = {}
        payload = bound.get("payload_obj", args[4] if len(args) > 4 else kwargs.get("payload_obj"))
        role = bound.get("from_role", args[1] if len(args) > 1 else kwargs.get("from_role"))
        if payload is not None and type(payload).__name__ == "Synthesis":
            return "relay_synthesis"
        role_value = getattr(role, "value", role)
        return "relay_forward" if role_value == "router" else "relay_report"
    return method


def _typed_copy(channel: Any, kind: str, message_id: Optional[str], envelope: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if kind == "request":
        req = (getattr(channel, "requests", None) or {}).get(message_id) if message_id else None
        return "task_request", message_id, (sha256_hex(model_json(req)) if req is not None else None)
    if kind == "relay_synthesis":
        sid = envelope.payload.get("synthesis_id") if envelope is not None and isinstance(envelope.payload, dict) else None
        return "synthesis", sid, None
    rid = envelope.payload.get("report_id") if envelope is not None and isinstance(envelope.payload, dict) else None
    held = (getattr(channel, "transmitted_reports", None) or {}).get(rid) if isinstance(rid, str) else None
    return "specialist_report", rid, (sha256_hex(model_json(held)) if held is not None else None)


def _channel_json(channel: Any) -> Optional[str]:
    try:
        cfg = getattr(channel, "config", None)
        branch = getattr(channel, "branch", None)
        return canonical_json({
            "key_id": getattr(channel, "key_id", None),
            "config": cfg.model_dump(mode="json") if cfg is not None and hasattr(cfg, "model_dump") else None,
            "branch": getattr(branch, "key", None),
            "formalize_synthesis_hook": getattr(channel, "formalize_synthesis_fn", None) is not None,
            "verify_claim_fn": getattr(channel, "verify_claim_fn", None) is not None,
        })
    except Exception:
        return None


def snapshot_event(channel: Any, kind: str, *, channel_uid: str, seq: int, before: ChannelBefore, call: dict, returned: Any = None,
                   raw_text: Optional[str] = None, captured: Sequence[CapturedResult] = (), captured_overflow: int = 0,
                   raised: Optional[str] = None, previous_plan_sha256: Optional[str] = None) -> ChannelEvent:
    """Build the event of one call from the channel's public state and ``log.messages()``. Reads only."""
    plan = getattr(channel, "plan", None)
    plan_dump = plan.model_dump(mode="json", exclude_none=True) if plan is not None else {}
    plan_sha = sha256_hex(canonical_json(plan_dump))
    receipt = None
    if raised is None:
        if isinstance(returned, tuple) and returned and hasattr(returned[-1], "receipt_id"):
            receipt = returned[-1]
        else:
            receipts = getattr(channel, "receipts", None) or []
            if len(receipts) > before.n_receipts:
                receipt = receipts[-1]
    returned_message = bool(isinstance(returned, tuple) and returned and returned[0] is not None and raised is None)
    message_id = receipt.message_id if receipt is not None else None
    log = getattr(channel, "log", None)
    envelope = log.get(message_id) if (log is not None and message_id) else None
    env_dump = envelope.model_dump(mode="json", exclude_none=True) if envelope is not None else None
    envelope_json = canonical_json(env_dump) if env_dump is not None else None
    env_digest = None
    if env_dump is not None:
        signable = {k: v for k, v in env_dump.items() if k not in _SIGNATURE_FIELDS}
        env_digest = sha256_hex(canonical_json(signable))
    payload_sha = sha256_hex(canonical_json(envelope.payload)) if envelope is not None else None
    receipt_json = model_json(receipt) if receipt is not None else None
    typed_kind, typed_id, typed_sha = _typed_copy(channel, kind, message_id, envelope) if envelope is not None else (None, None, None)
    status = getattr(getattr(receipt, "status", None), "value", None) if receipt is not None else None
    # what the call added to the channel's records
    conflicts = list(getattr(channel, "conflicts_seen", ()) or ())[before.n_conflicts:]
    forwards = getattr(channel, "forwards", None) or {}
    counts = dict(before.forward_counts)
    forwards_added = tuple((rid, str(rec[0]), str(rec[1])) for rid, recs in forwards.items() for rec in list(recs)[counts.get(rid, 0):])
    sup_before = dict(before.superseded)
    superseded_added = tuple((old, new) for old, new in (getattr(channel, "superseded", None) or {}).items() if sup_before.get(old) != new)
    transmitted_before = set(before.transmitted)
    transmitted_added = tuple(rid for rid in (getattr(channel, "transmitted_reports", None) or {}) if rid not in transmitted_before)
    rec_before = {rid: set(v) for rid, v in before.recipients}
    recipients_added = tuple((rid, key) for rid, keys in (getattr(channel, "report_recipients", None) or {}).items() for key in sorted(keys) if key not in rec_before.get(rid, set()))
    req_before = set(before.requests)
    requests_added = tuple(mid for mid in (getattr(channel, "requests", None) or {}) if mid not in req_before)
    log_added = tuple(m.message_id for m in _log_messages(channel)[before.n_log:])
    call_out = dict(call)
    if kind == "request" and envelope is not None and isinstance(envelope.payload, dict):
        if call_out.get("user_input_sha256_given") == envelope.payload.get("user_input_sha256"):
            call_out.pop("user_input_sha256_given", None)
    include_plan = seq == 1 or previous_plan_sha256 is None or previous_plan_sha256 != plan_sha
    return ChannelEvent(
        channel_uid=channel_uid, seq=seq, kind=kind,
        task_id=str(plan_dump.get("task_id", "")), request_id=str(plan_dump.get("request_id", "")),
        plan_sha256=plan_sha, plan_json=canonical_json(plan_dump) if include_plan else None, channel_json=_channel_json(channel),
        message_id=message_id, receipt_id=getattr(receipt, "receipt_id", None), status=status,
        delivered=status is not None and status != "REJECTED", returned_message=returned_message,
        envelope_json=envelope_json, envelope_digest=env_digest, header_sha256=header_digest(env_dump) if env_dump is not None else None,
        payload_sha256=payload_sha, receipt_json=receipt_json, receipt_sha256=sha256_hex(receipt_json) if receipt_json is not None else None,
        typed_kind=typed_kind, typed_id=typed_id, typed_copy_sha256=typed_sha,
        raw_text=raw_text, raw_text_sha256=sha256_hex(raw_text) if raw_text is not None else None,
        call_json=canonical_json(_jsonable(call_out)), captured=tuple(captured), captured_overflow=captured_overflow,
        pool_before=before.pool, pool=_pool(channel),
        conflicts_added=tuple((tuple(sorted(c)), r) for c, r in conflicts),
        forwards_added=forwards_added, superseded_added=superseded_added, transmitted_added=transmitted_added,
        recipients_added=recipients_added, requests_added=requests_added, log_added=log_added,
        raised=raised, created_at=_now(), monotonic_ns=time.monotonic_ns(),
    )


# --------------------------------------------------------------------------------------------- observation
@dataclass
class ObservationState:
    """Per-channel observation counters: the channel instance id, the event counter (from 1), the call depth (a
    nested call such as ``respond_text`` -> ``respond`` emits one event) and a bounded list of observer failures
    ``(seq, observer name, exception type)``. A channel is single-threaded by contract, as today."""
    channel_uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    seq: int = 0
    depth: int = 0
    last_plan_sha256: Optional[str] = None
    observer_errors: list[tuple[int, str, str]] = field(default_factory=list)


_STATES: "weakref.WeakKeyDictionary[Any, ObservationState]" = weakref.WeakKeyDictionary()


def observation_state(channel: Any) -> ObservationState:
    """The channel's own ``_observation`` state when it has one (the bus hook), else one kept beside it."""
    st = getattr(channel, "_observation", None)
    if isinstance(st, ObservationState):
        return st
    try:
        st = _STATES.get(channel)
        if st is None:
            st = ObservationState()
            _STATES[channel] = st
        return st
    except TypeError:  # not weak-referenceable: a fresh state each time would break the sequence, so refuse loudly
        raise TypeError("channel cannot be observed: it is not weak-referenceable and carries no _observation state")


def observe_call(channel: Any, method: str, args: tuple, kwargs: dict, observers: Sequence[Callable[[ChannelEvent], None]],
                 state: Optional[ObservationState] = None) -> Any:
    """Call ``channel.<method>(*args, **kwargs)`` and, at depth 1, emit one event to every observer.

    The method body runs unchanged inside a result capture; the event is built before anything is returned; each
    observer runs inside ``try/except`` (a failure is recorded, bounded, and never reaches the caller); a method
    that raised emits a ``raised`` event and its exception is re-raised unchanged. With no observers the method is
    called straight through."""
    fn = getattr(channel, method)
    if not observers:
        return fn(*args, **kwargs)
    st = state or observation_state(channel)
    st.depth += 1
    try:
        if st.depth > 1:
            return fn(*args, **kwargs)
        before = take_before(channel)
        call = call_record(channel, method, args, kwargs)
        kind = event_kind(method, args, kwargs, channel)
        raw_text = None
        if method == "respond_text":
            try:
                raw_text = inspect.signature(fn).bind_partial(*args, **kwargs).arguments.get("text")
            except Exception:
                raw_text = args[1] if len(args) > 1 else kwargs.get("text")
        raised: Optional[Exception] = None
        returned = None
        with capture_results() as cap:
            try:
                returned = fn(*args, **kwargs)
            except Exception as exc:  # recorded, then re-raised unchanged
                raised = exc
        st.seq += 1
        try:
            event = snapshot_event(channel, kind, channel_uid=st.channel_uid, seq=st.seq, before=before, call=call, returned=returned,
                                   raw_text=raw_text if isinstance(raw_text, str) else None, captured=cap.items, captured_overflow=cap.overflow,
                                   raised=type(raised).__name__ if raised is not None else None, previous_plan_sha256=st.last_plan_sha256)
            st.last_plan_sha256 = event.plan_sha256
        except Exception as exc:  # an event that cannot be built is an observer-side failure; the call's outcome stands
            event = None
            _record_error(st, st.seq, "snapshot_event", exc)
        if event is not None:
            for obs in observers:
                try:
                    obs(event)
                except Exception as exc:
                    _record_error(st, st.seq, getattr(obs, "__qualname__", type(obs).__name__), exc)
        if raised is not None:
            raise raised
        return returned
    finally:
        st.depth -= 1


def _record_error(st: ObservationState, seq: int, who: str, exc: BaseException) -> None:
    if len(st.observer_errors) < OBSERVER_ERRORS_MAX:
        st.observer_errors.append((seq, str(who)[:200], type(exc).__name__))
