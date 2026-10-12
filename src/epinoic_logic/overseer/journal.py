"""The channel journal: an append-only, hash-chained, HMAC'd record of every transfer as it was issued.

One journal per channel INSTANCE (``channel_uid``); the task id is an attribute, because several channels
may share a task id (the arena re-keys ``hub.channels`` by hand, and a task may be reopened).

* ``entry_hash = sha256(canonical(entry without entry_hash and mac))``, ``mac = HMAC(journal key, entry_hash)``,
  and each entry's ``prev_hash`` is the previous entry's hash; the genesis ``prev_hash`` is
  ``sha256("epinoic-overseer-journal/v1|" + channel_uid)``.
* ``append`` runs under a lock. Event sequence numbers must be contiguous: a missing number means a transfer
  was not journaled, and the journal records the gap itself (a ``gap`` entry) before the next event, so the
  audit reports it (CUST-003) instead of passing over it.
* Clearance decisions are journaled as ``clearance`` entries, so every clearance is part of the chain.
* :meth:`ChannelJournal.verify_chain` recomputes hashes, links, MACs and the entry index, and reports the FIRST
  break (CUST-005); everything after it is unverifiable.
* Bounds: past ``max_entries`` EVENT entries or ``max_bytes`` of event content per channel, events are journaled
  digest-only (content strings replaced by their digests, raw text dropped): custody is still decidable by
  digest, the content is no longer recoverable, and the coverage loss is reported once (AUDIT-002). A digest-only
  transfer is never treated as checkable: the audit fails it (AUDIT-005, error, live and batch), so a transfer
  whose receipt and results the auditor no longer holds never clears. The auditor's own records (clearance, gap,
  seal) do not count towards ``max_entries`` or ``max_bytes`` (so the router's clearance calls never use up the
  event budget); they have their own bound, ``max_records``, past which a record is journaled as its digest only.
  :class:`JournalSet` bounds the total across journals and evicts sealed journals least-recently-used first;
  an evicted journal keeps its head hash.
* A sealed journal accepts no further entries. Sealing happens on a FINAL task audit, on ``close_task`` and
  when the channel is garbage-collected (the auditor's weakref finalizer).

Deviations from the design: a gap is recorded as its own ``gap`` entry (so the chain verifies and the sweep reports
CUST-003, not CUST-005); a journal opened on a channel's event N > 1 starts there (``start_at``: TR6, the audit covers
only what was journaled since attachment) instead of recording 1..N-1 as a gap.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional

from ..channel.events import ChannelEvent
from ..ir.canonical import canonical_json, sha256_hex
from .contracts import JournalEntry
from .keys import KeyRing

__all__ = ["ChannelJournal", "JournalSet", "ChainBreak", "JournalSealed", "GENESIS_PREFIX", "MAX_ENTRIES", "MAX_BYTES", "MAX_RECORDS", "GLOBAL_MAX_BYTES"]

GENESIS_PREFIX = "epinoic-overseer-journal/v1|"
#: Event entries per channel journaled with their content (the auditor's own records are not counted).
MAX_ENTRIES = 4096
#: Characters of event content per channel journaled in full.
MAX_BYTES = 64 * 1024 * 1024
#: The auditor's own records (clearance, gap, seal) per channel journaled in full; later ones are journaled as their digest.
MAX_RECORDS = 65536
GLOBAL_MAX_BYTES = 256 * 1024 * 1024
_RECORD_KINDS = frozenset({"clearance", "gap", "seal"})


class JournalSealed(RuntimeError):
    """Raised by ``append`` on a sealed journal."""


@dataclass(frozen=True)
class ChainBreak:
    """The first point where the chain does not verify. ``index`` is the 1-based entry index."""
    index: int
    reason: str


def genesis_hash(channel_uid: str) -> str:
    return sha256_hex(GENESIS_PREFIX + channel_uid)


def entry_hash_of(body: dict) -> str:
    return sha256_hex(canonical_json(body))


class ChannelJournal:
    """The journal of one channel instance."""

    def __init__(self, channel_uid: str, task_id: str, keyring: KeyRing, *, max_entries: int = MAX_ENTRIES, max_bytes: int = MAX_BYTES,
                 on_size: Optional[Callable[["ChannelJournal", int], None]] = None, max_records: int = MAX_RECORDS) -> None:
        self.channel_uid = channel_uid
        self.task_id = task_id
        self._keyring = keyring
        self._entries: list[JournalEntry] = []
        self._lock = threading.RLock()
        self._last_event_seq = 0
        self._bytes = 0
        self._event_entries = 0
        self._event_bytes = 0
        self._records = 0
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.max_records = max_records
        self.sealed = False
        self.evicted = False
        self.digest_only_entries = 0
        self.coverage_notes: list[str] = []
        self._head = (0, genesis_hash(channel_uid))
        self._on_size = on_size
        self.start_seq = 1
        #: Set by the auditor: ``live_custody(message_id) -> [codes]`` re-checks the live channel's custody of a journaled
        #: transfer and the transfers it depends on (the release gate calls it). Not part of the chain.
        self.live_custody: Optional[Callable[[str], list[str]]] = None

    def start_at(self, seq: int) -> None:
        """The auditor attached after the channel's first ``seq - 1`` events: the journal starts there (TR6: the audit
        covers only the transfers journaled since attachment). Only an empty journal can be started late."""
        with self._lock:
            if self._entries:
                raise ValueError("only an empty journal can be started late")
            self.start_seq = max(1, int(seq))
            self._last_event_seq = self.start_seq - 1

    # ------------------------------------------------------------------ appending
    def _make(self, kind: str, event: Optional[ChannelEvent], record_json: Optional[str]) -> JournalEntry:
        index = len(self._entries) + 1
        prev = self._entries[-1].entry_hash if self._entries else genesis_hash(self.channel_uid)
        body = {"index": index, "channel_uid": self.channel_uid, "kind": kind, "event": event.to_dict() if event is not None else None,
                "record_json": record_json, "prev_hash": prev}
        h = entry_hash_of(body)
        entry = JournalEntry(index=index, channel_uid=self.channel_uid, kind=kind, event=event, record_json=record_json, prev_hash=prev,
                             entry_hash=h, mac=self._keyring.mac("journal", h))
        self._entries.append(entry)
        self._head = (index, h)
        size = entry.size()
        self._bytes += size
        if self._on_size is not None:
            try:
                self._on_size(self, size)
            except Exception:
                pass
        return entry

    def append(self, event: ChannelEvent) -> JournalEntry:
        """Journal one event. A missing sequence number is recorded as a ``gap`` entry first; a repeated or
        backwards sequence number, an event of another channel, or a sealed journal is refused (ValueError /
        JournalSealed), never silently accepted."""
        with self._lock:
            if self.sealed:
                raise JournalSealed(f"journal of channel {self.channel_uid} is sealed")
            if event.channel_uid != self.channel_uid:
                raise ValueError(f"event of channel {event.channel_uid!r} offered to the journal of {self.channel_uid!r}")
            if event.seq <= self._last_event_seq:
                raise ValueError(f"event sequence {event.seq} is not after {self._last_event_seq}: replayed or reordered event")
            if event.seq > self._last_event_seq + 1:
                missing = (self._last_event_seq + 1, event.seq - 1)
                self._records += 1
                self._make("gap", None, canonical_json({"missing_from": missing[0], "missing_to": missing[1]}))
            size = event.content_size()
            if self._event_entries >= self.max_entries or self._event_bytes + size > self.max_bytes:
                if not event.digest_only:
                    event = event.as_digest_only()
                    self.digest_only_entries += 1
                    if not self.coverage_notes:
                        self.coverage_notes.append(f"journal bound reached ({self.max_entries} event entries / {self.max_bytes} bytes of event content): "
                                                   "later events are digest-only and cannot pass the audit")
            else:
                self._event_bytes += size
            self._last_event_seq = event.seq
            self._event_entries += 1
            return self._make(event.kind, event, None)

    def append_record(self, kind: str, record: dict) -> JournalEntry:
        """Journal one of the auditor's own records (a clearance decision, a seal)."""
        if kind not in _RECORD_KINDS:
            raise ValueError(f"unknown journal record kind {kind!r}")
        with self._lock:
            if self.sealed:
                raise JournalSealed(f"journal of channel {self.channel_uid} is sealed")
            return self._record(kind, canonical_json(record))

    def _record(self, kind: str, record_json: str) -> JournalEntry:
        """One of the auditor's records; past ``max_records`` it is journaled as its digest (the chain still covers it)."""
        self._records += 1
        if self._records > self.max_records:
            record_json = canonical_json({"digest_only": True, "record_sha256": sha256_hex(record_json)})
        return self._make(kind, None, record_json)

    def seal(self, reason: str) -> None:
        with self._lock:
            if self.sealed:
                return
            self._make("seal", None, canonical_json({"reason": reason}))
            self.sealed = True

    def evict_content(self) -> None:
        """Drop the entries (global bound); the head hash stays and the loss is reported by every later audit."""
        with self._lock:
            self._entries = []
            self.evicted = True
            self._bytes = 0
            self._event_bytes = 0
            self.coverage_notes.append("journal evicted under the global bound; only its head hash remains")

    # ------------------------------------------------------------------ reading
    @property
    def size_bytes(self) -> int:
        return self._bytes

    @property
    def last_event_seq(self) -> int:
        return self._last_event_seq

    def entries(self) -> tuple[JournalEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def events(self) -> list[ChannelEvent]:
        return [e.event for e in self.entries() if e.event is not None]

    def head(self) -> tuple[int, str]:
        with self._lock:
            return self._head

    def gaps(self) -> list[tuple[int, int]]:
        out = []
        for e in self.entries():
            if e.kind == "gap" and e.record_json:
                try:
                    r = json.loads(e.record_json)
                    out.append((int(r["missing_from"]), int(r["missing_to"])))
                except Exception:
                    continue
        return out

    def verify_chain(self) -> Optional[ChainBreak]:
        """Recompute every entry's hash, link, MAC and index; the first break, or None when the chain verifies.
        Event sequence numbers must increase, with any gap recorded by a ``gap`` entry."""
        entries = self.entries()
        prev = genesis_hash(self.channel_uid)
        last_seq = self.start_seq - 1
        for pos, e in enumerate(entries, start=1):
            if e.index != pos:
                return ChainBreak(pos, f"entry index {e.index} at position {pos}")
            if e.channel_uid != self.channel_uid:
                return ChainBreak(pos, "entry belongs to another channel")
            if e.prev_hash != prev:
                return ChainBreak(pos, "link to the previous entry broken (prev_hash)")
            if entry_hash_of(e.body()) != e.entry_hash:
                return ChainBreak(pos, "entry content does not match its hash")
            if not self._keyring.mac_ok("journal", e.entry_hash, e.mac):
                return ChainBreak(pos, "entry MAC does not verify under the journal key")
            if e.event is not None:
                if e.event.channel_uid != self.channel_uid:
                    return ChainBreak(pos, "event belongs to another channel")
                if e.event.seq <= last_seq:
                    return ChainBreak(pos, f"event sequence {e.event.seq} is not after {last_seq}")
                if e.event.seq != last_seq + 1:
                    gap = entries[pos - 2] if pos >= 2 else None
                    if gap is None or gap.kind != "gap":
                        return ChainBreak(pos, f"event sequence jumps from {last_seq} to {e.event.seq} with no recorded gap")
                last_seq = e.event.seq
            prev = e.entry_hash
        if entries and not self.evicted and (entries[-1].index, entries[-1].entry_hash) != self._head:
            return ChainBreak(len(entries), "the last entry is not the journal head")
        return None


class JournalSet:
    """Every journal of an auditor, with the global content bound: sealed journals are evicted least-recently-used
    first; an evicted journal keeps its head hash (and the auditor keeps its signed audits)."""

    def __init__(self, keyring: KeyRing, *, global_max_bytes: int = GLOBAL_MAX_BYTES, max_entries: int = MAX_ENTRIES, max_bytes: int = MAX_BYTES,
                 max_records: int = MAX_RECORDS) -> None:
        self._keyring = keyring
        self._journals: "OrderedDict[str, ChannelJournal]" = OrderedDict()
        self._lock = threading.RLock()
        self.global_max_bytes = global_max_bytes
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.max_records = max_records
        self._total = 0

    def create(self, channel_uid: str, task_id: str) -> ChannelJournal:
        with self._lock:
            j = self._journals.get(channel_uid)
            if j is None:
                j = ChannelJournal(channel_uid, task_id, self._keyring, max_entries=self.max_entries, max_bytes=self.max_bytes, on_size=self._grew,
                                   max_records=self.max_records)
                self._journals[channel_uid] = j
            self._journals.move_to_end(channel_uid)
            return j

    def get(self, channel_uid: str) -> Optional[ChannelJournal]:
        with self._lock:
            j = self._journals.get(channel_uid)
            if j is not None:
                self._journals.move_to_end(channel_uid)
            return j

    def all(self) -> list[ChannelJournal]:
        with self._lock:
            return list(self._journals.values())

    @property
    def total_bytes(self) -> int:
        return self._total

    def _grew(self, journal: ChannelJournal, size: int) -> None:
        with self._lock:
            self._total += size
            if self._total <= self.global_max_bytes:
                return
            for uid, j in list(self._journals.items()):  # least recently used first
                if self._total <= self.global_max_bytes:
                    break
                if j is journal or not j.sealed or j.evicted:
                    continue
                self._total -= j.size_bytes
                j.evict_content()
