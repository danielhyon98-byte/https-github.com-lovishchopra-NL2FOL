"""The result store: every signed result the auditor saw, by id, with its origin, bounds and tombstones.

* ``put`` verifies the signature with the key ring and records the outcome (``signature_ok_at_put``).
* The index maps ``result_id`` to every ``(sha256, channel_uid, seq, origin)`` it was seen with; a second
  content under one id is reported (RES-006) and the FIRST content is kept.
* The full ``result_json`` is kept while the result is live: the SMT-LIB binding text is inside the signed
  text, and stripping it would break verification.
* Bounds: ``max_results`` and ``max_bytes`` per channel, ``global_max_bytes`` in total. Eviction takes sealed
  channels first, least-recently-used; an evicted result leaves a :class:`ResultTombstone`, so membership,
  origin and duplicate checks (RES-001, RES-005, RES-006) still decide, and RES-003 uses the verification
  recorded at put. An evicted id whose content is needed later is RES-002 (warning) when it is still decided on a
  receipt's copy or replayed from the journal's capture, else OVS-AUDIT-005 (it cannot pass); never an accusation.
* ``memo``: the auditor's own computations keyed by their inputs' digests (joint checks, replays,
  re-derivations), so the same journal and store give the same report on every audit.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from ..engine.results import VerificationResult
from ..engine.sink import CapturedResult
from ..ir.canonical import canonical_json, sha256_hex
from .faithful import faithful
from .contracts import Citation, ResultTombstone, StoredResult
from .keys import KeyRing

__all__ = ["ResultStore", "PutOutcome", "MAX_RESULTS_PER_CHANNEL", "MAX_BYTES_PER_CHANNEL", "GLOBAL_MAX_BYTES"]

MAX_RESULTS_PER_CHANNEL = 8192
MAX_BYTES_PER_CHANNEL = 32 * 1024 * 1024
GLOBAL_MAX_BYTES = 256 * 1024 * 1024
_PARSED_CACHE = 1024
_MEMO_MAX = 4096

Origin = Literal["captured", "external", "auditor_run", "replay"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PutOutcome:
    """What ``put`` did: the record now held for the id, whether this content was new, and the conflicting
    contents when the id was already held with other content (RES-006)."""
    stored: Optional[StoredResult]
    new: bool
    conflict: Optional[tuple[str, str]]  # (held sha256, offered sha256)
    parse_error: Optional[str] = None


class ResultStore:
    def __init__(self, keyring: KeyRing, *, max_results: int = MAX_RESULTS_PER_CHANNEL, max_bytes: int = MAX_BYTES_PER_CHANNEL,
                 global_max_bytes: int = GLOBAL_MAX_BYTES) -> None:
        self._keyring = keyring
        self._lock = threading.RLock()
        self._live: dict[str, StoredResult] = {}
        self._index: dict[str, list[tuple[str, str, int, str]]] = {}
        self._tombstones: dict[str, ResultTombstone] = {}
        self._by_channel: dict[str, "OrderedDict[str, None]"] = {}
        self._channel_bytes: dict[str, int] = {}
        self._channel_lru: "OrderedDict[str, None]" = OrderedDict()
        self._sealed: set[str] = set()
        self._citations: dict[str, list[Citation]] = {}
        self._parsed: "OrderedDict[str, VerificationResult]" = OrderedDict()
        self._memo: "OrderedDict[str, Any]" = OrderedDict()
        self._total = 0
        self.max_results = max_results
        self.max_bytes = max_bytes
        self.global_max_bytes = global_max_bytes
        self.evictions = 0

    # ------------------------------------------------------------------ writing
    def put(self, captured: CapturedResult, *, channel_uid: str, task_id: str, request_id: str, event_seq: int, origin: Origin) -> PutOutcome:
        """Store one result (signature verified now). Idempotent for the same content; a different content under a held
        id is recorded in the index and reported, and never replaces the first."""
        with self._lock:
            if not captured.result_json:
                return PutOutcome(stored=None, new=False, conflict=None, parse_error="no content (digest-only capture)")
            try:
                data = json.loads(captured.result_json)
                result = faithful(VerificationResult, data)
            except Exception as exc:
                return PutOutcome(stored=None, new=False, conflict=None, parse_error=f"{type(exc).__name__}")
            rid = result.result_id
            sha = sha256_hex(captured.result_json)
            entries = self._index.setdefault(rid, [])
            if (sha, channel_uid, event_seq, origin) not in entries:
                entries.append((sha, channel_uid, event_seq, origin))
            held = self._live.get(rid)
            tomb = self._tombstones.get(rid)
            held_sha = held.result_sha256 if held is not None else (tomb.result_sha256 if tomb is not None else None)
            if held_sha is not None:
                return PutOutcome(stored=held, new=False, conflict=(held_sha, sha) if held_sha != sha else None)
            ok, reason = self._keyring.verify_result(result)
            rec = StoredResult(result_id=rid, channel_uid=channel_uid, task_id=task_id, request_id=request_id, event_seq=event_seq, origin=origin,
                               result_json=captured.result_json, result_sha256=sha, problem_json=captured.problem_json, problem_digest=captured.problem_digest,
                               key_id=result.signature_key_id, key_status=self._keyring.key_status(result.signature_key_id) if result.signature else "unknown",
                               signature_ok_at_put=ok, signature_reason=reason, status=result.status.value, binding_digest=result.binding.binding_digest,
                               captured_at=_now())
            self._live[rid] = rec
            self._remember_parsed(rid, result)
            chan = self._by_channel.setdefault(channel_uid, OrderedDict())
            chan[rid] = None
            self._channel_bytes[channel_uid] = self._channel_bytes.get(channel_uid, 0) + rec.size()
            self._total += rec.size()
            self._channel_lru[channel_uid] = None
            self._channel_lru.move_to_end(channel_uid)
            self._enforce(channel_uid)
            return PutOutcome(stored=self._live.get(rid), new=True, conflict=None)

    def cite(self, result_id: str, citation: Citation) -> None:
        with self._lock:
            lst = self._citations.setdefault(result_id, [])
            if citation not in lst:
                lst.append(citation)

    def seal_channel(self, channel_uid: str) -> None:
        with self._lock:
            self._sealed.add(channel_uid)

    # ------------------------------------------------------------------ bounds
    def _evict(self, rid: str) -> None:
        rec = self._live.pop(rid, None)
        if rec is None:
            return
        self._tombstones[rid] = ResultTombstone(result_id=rid, result_sha256=rec.result_sha256, status=rec.status, binding_digest=rec.binding_digest,
                                                channel_uid=rec.channel_uid, task_id=rec.task_id, event_seq=rec.event_seq, key_id=rec.key_id,
                                                signature_ok_at_put=rec.signature_ok_at_put, origin=rec.origin)
        self._parsed.pop(rid, None)
        chan = self._by_channel.get(rec.channel_uid)
        if chan is not None:
            chan.pop(rid, None)
        self._channel_bytes[rec.channel_uid] = self._channel_bytes.get(rec.channel_uid, 0) - rec.size()
        self._total -= rec.size()
        self.evictions += 1

    def _enforce(self, channel_uid: str) -> None:
        chan = self._by_channel.get(channel_uid, OrderedDict())
        while chan and (len(chan) > self.max_results or self._channel_bytes.get(channel_uid, 0) > self.max_bytes):
            self._evict(next(iter(chan)))
        if self._total <= self.global_max_bytes:
            return
        order = [u for u in self._channel_lru if u in self._sealed] + [u for u in self._channel_lru if u not in self._sealed and u != channel_uid] + [channel_uid]
        for uid in order:
            c = self._by_channel.get(uid)
            while c and self._total > self.global_max_bytes:
                self._evict(next(iter(c)))
            if self._total <= self.global_max_bytes:
                break

    # ------------------------------------------------------------------ reading
    def get(self, result_id: Optional[str]) -> Union[StoredResult, ResultTombstone, None]:
        if not result_id:
            return None
        with self._lock:
            return self._live.get(result_id) or self._tombstones.get(result_id)

    def live(self, result_id: Optional[str]) -> Optional[StoredResult]:
        with self._lock:
            return self._live.get(result_id or "")

    def is_tombstoned(self, result_id: str) -> bool:
        with self._lock:
            return result_id in self._tombstones

    def index(self, result_id: str) -> list[tuple[str, str, int, str]]:
        with self._lock:
            return list(self._index.get(result_id, []))

    def contents(self, result_id: str) -> set[str]:
        """Every distinct content digest seen under ``result_id``."""
        return {e[0] for e in self.index(result_id)}

    def citations(self, result_id: str) -> list[Citation]:
        with self._lock:
            return list(self._citations.get(result_id, []))

    def results_of(self, channel_uid: str) -> list[StoredResult]:
        with self._lock:
            return [r for r in self._live.values() if r.channel_uid == channel_uid]

    def ids_of(self, channel_uid: str) -> list[str]:
        with self._lock:
            live = [r.result_id for r in self._live.values() if r.channel_uid == channel_uid]
            dead = [t.result_id for t in self._tombstones.values() if t.channel_uid == channel_uid]
            return live + dead

    def _remember_parsed(self, rid: str, result: VerificationResult) -> None:
        self._parsed[rid] = result
        self._parsed.move_to_end(rid)
        while len(self._parsed) > _PARSED_CACHE:
            self._parsed.popitem(last=False)

    def parsed(self, result_id: Optional[str]) -> Optional[VerificationResult]:
        """The stored result as a model, READ-ONLY (cached; the stored JSON stays the authority: every digest and
        signature decision is taken on it, and a cached model that was changed is re-parsed from it)."""
        with self._lock:
            rec = self._live.get(result_id or "")
            if rec is None:
                return None
            cached = self._parsed.get(rec.result_id)
            if cached is None:
                cached = faithful(VerificationResult, json.loads(rec.result_json))
                self._remember_parsed(rec.result_id, cached)
            return cached

    def digest(self, result_ids) -> str:
        """sha256 over the sorted ``(result_id, result_sha256)`` pairs of the given ids (``-`` for an id held nowhere)."""
        pairs = []
        for rid in sorted(set(result_ids)):
            rec = self.get(rid)
            pairs.append([rid, rec.result_sha256 if rec is not None else "-"])
        return sha256_hex(canonical_json(pairs))

    @property
    def total_bytes(self) -> int:
        return self._total

    # ------------------------------------------------------------------ memo
    def memo_get(self, key: str) -> Any:
        with self._lock:
            v = self._memo.get(key)
            if v is not None:
                self._memo.move_to_end(key)
            return v

    def memo_put(self, key: str, value: Any) -> None:
        with self._lock:
            self._memo[key] = value
            self._memo.move_to_end(key)
            while len(self._memo) > _MEMO_MAX:
                self._memo.popitem(last=False)
