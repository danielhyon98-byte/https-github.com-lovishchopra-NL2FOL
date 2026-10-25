"""The Overseer's view of one channel: the transfers in sequence order, typed, linked, with their receipts,
pool snapshots and the results they cite.

* :meth:`OverseerView.from_journal` parses the JOURNAL entries, never the live objects; it is authoritative.
* :meth:`OverseerView.from_channel` is the degraded mode for a channel audited without hooks: it reads
  ``log.messages()``, the receipts and the typed copies AS THEY ARE NOW. With no reference copy, custody is
  not decidable (AUDIT-002), results are limited to the copies receipts carry, and the checks never accuse a
  transfer of custody faults (CUST-001/002/004, RCPT-001) from it.

Links resolved here:

* a response to the request it replies to (``in_reply_to``);
* a forward to the delivering response: the first delivered response event for that ``report_id``;
* a peer document (``peer:<task>`` in a later request) to the forward, by text equality with an earlier
  delivered forward to the same recipient (the PEER-003 link: ``TaskRequest`` carries no link field); the document's
  attribution (its ``author``, and a forwarded report id its ``peer:<id>`` names) must be that forward's report and
  agent, or the link records why not (PEER-002);
* a supplied text under ANY other id that presents a forwarded report (its author is the report's agent, its id is the
  report or agent id, its text is a near copy of the report's ``original_response`` (``near_copy``) or contains most of
  it (``contains_answer``, review round 3: an answer padded with background)) is linked the same way and held to the same
  byte identity (a containing text must carry the answer as one verbatim span); one presenting a delivered report never
  forwarded to that recipient is linked to no forward (PEER-002). A text an earlier delivered request supplied under the
  same id before the report existed is never linked to it (rule ``source-predates-answer``: the answer quotes its
  source, not the other way round), and the text test reads only the answer's OWN words, the 4-grams no text supplied
  (or user input stated) before the report's delivery carries (rule ``source-explained``: the same passage under another
  id, or a longer document containing it, resembles the source the answer copied, not the answer);
* a synthesis to the deliveries of the reports it cites;
* a result id to the stored result and its citation kinds.

Rule ``pinned-setup`` (review round 3): every rule reads the FIRST journaled plan (``plan_at``) and the first event's
solver configuration, key id and branch (``config_at``, ``key_id_at``); ``setup_changes`` names what a later event was
issued under instead, which the custody check reports (OVS-CUST-002).

Agent text in payloads is data: this module parses payloads only against the allowlisted contracts.
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..channel.contracts import TaskRequest, TransmissionReceipt
from ..channel.events import ChannelEvent, PoolEntry
from ..engine.results import SolverConfig
from ..engine.sink import CapturedResult
from ..integrity.contracts import Synthesis, WorkPlan
from ..translate.contracts import SpecialistReport
from .faithful import faithful
from .journal import ChannelJournal
from .store import ResultStore

__all__ = ["Transfer", "PeerLink", "OverseerView", "cited_results", "near_copy", "REPORT_KINDS", "RESPONSE_KINDS"]

#: Transfers that deliver a report into the channel's records.
REPORT_KINDS = ("response", "response_text", "relay_report")
RESPONSE_KINDS = ("response", "response_text")


@dataclass(frozen=True)
class PeerLink:
    """A ``peer:`` document of a request and the forward it is linked to by text equality (or none). ``misattributed``
    says why the document's attribution (its ``author``, or a report id its ``peer:<id>`` names) is not the linked
    forward's report and agent; None when it is (or the document states none)."""
    document_id: str
    forward_seq: Optional[int]
    forward_message_id: Optional[str]
    report_id: Optional[str]
    identical: bool
    misattributed: Optional[str] = None


@dataclass
class Transfer:
    seq: int
    index: int
    kind: str
    event: ChannelEvent
    message_id: Optional[str]
    receipt_id: Optional[str]
    status: Optional[str]
    delivered: bool
    envelope: Optional[dict]
    payload: Optional[dict]
    typed: Any = None
    typed_error: Optional[str] = None
    withheld: Optional[dict] = None
    receipt: Optional[TransmissionReceipt] = None
    receipt_dump: Optional[dict] = None
    receipt_error: Optional[str] = None
    raw_text: Optional[str] = None
    call: dict = field(default_factory=dict)
    captured: dict[str, CapturedResult] = field(default_factory=dict)
    digest_only: bool = False
    request_seq: Optional[int] = None
    delivering_seq: Optional[int] = None
    peer_links: list[PeerLink] = field(default_factory=list)
    cited_delivery_seqs: dict[str, Optional[int]] = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)

    @property
    def contract(self) -> Optional[str]:
        return (self.envelope or {}).get("contract")

    @property
    def sender_agent_id(self) -> Optional[str]:
        return (self.envelope or {}).get("sender_agent_id")

    @property
    def recipient_agent_id(self) -> Optional[str]:
        return (self.envelope or {}).get("recipient_agent_id")

    @property
    def in_reply_to(self) -> Optional[str]:
        return (self.envelope or {}).get("in_reply_to")

    @property
    def report(self) -> Optional[SpecialistReport]:
        return self.typed if isinstance(self.typed, SpecialistReport) else None

    @property
    def request(self) -> Optional[TaskRequest]:
        return self.typed if isinstance(self.typed, TaskRequest) else None

    @property
    def synthesis(self) -> Optional[Synthesis]:
        return self.typed if isinstance(self.typed, Synthesis) else None

    @property
    def report_id(self) -> Optional[str]:
        if self.payload is None and self.digest_only and self.event.typed_kind == "specialist_report":
            return self.event.typed_id  # a digest-only entry keeps the report id the channel held it under
        p = self.payload or {}
        rid = p.get("report_id")
        return rid if isinstance(rid, str) else None

    @property
    def pool_before(self) -> tuple[PoolEntry, ...]:
        return self.event.pool_before

    @property
    def pool_after(self) -> tuple[PoolEntry, ...]:
        return self.event.pool

    def ids(self) -> dict:
        """The identifiers every finding about this transfer carries."""
        agents = [a for a in (self.sender_agent_id, self.recipient_agent_id) if a]
        return dict(message_ids=[self.message_id] if self.message_id else [], agent_ids=agents,
                    report_ids=[self.report_id] if self.report_id else ([self.synthesis.synthesis_id] if self.synthesis else []))


def cited_results(receipt: TransmissionReceipt) -> list[tuple[str, str, str]]:
    """Every result id a receipt cites: ``(result_id, citation kind, JSON path)``."""
    out: list[tuple[str, str, str]] = []
    for i, o in enumerate(receipt.outcomes):
        if o.verification is not None:
            out.append((o.verification.result_id, "outcome", f"outcomes[{i}].verification"))
    for i, c in enumerate(receipt.constraint_results):
        if c.formal_result_id:
            out.append((c.formal_result_id, "constraint", f"constraint_results[{i}].formal_result_id"))
    for i, c in enumerate(receipt.formal_checks):
        if c.formal_result_id:
            out.append((c.formal_result_id, "branch_formal", f"formal_checks[{i}].formal_result_id"))
    for i, f in enumerate(receipt.findings):
        if f.formal_result_id:
            out.append((f.formal_result_id, "finding_formal", f"findings[{i}].formal_result_id"))
        for j, r in enumerate(f.related_result_ids):
            out.append((r, "finding_related", f"findings[{i}].related_result_ids[{j}]"))
    for i, r in enumerate(receipt.formal_result_ids):
        out.append((r, "receipt_formal", f"formal_result_ids[{i}]"))
    return out


def _parse_typed(kind: str, payload: Optional[dict]) -> tuple[Any, Optional[str], Optional[dict]]:
    """(typed payload, parse error, withheld record) for an allowlisted contract."""
    if payload is None:
        return None, "no payload", None
    try:
        if kind == "request":
            return faithful(TaskRequest, payload), None, None
        if kind == "relay_synthesis":
            return faithful(Synthesis, payload), None, None
        if "original_response" not in payload and "response_sha256" in payload and "response_chars" in payload:
            return None, None, {k: payload.get(k) for k in ("report_id", "agent_id", "request_id", "task_id", "response_sha256", "response_chars")}
        return faithful(SpecialistReport, payload), None, None
    except Exception as exc:
        return None, f"{type(exc).__name__}", None


class OverseerView:
    """The transfers of one channel as the auditor reads them."""

    def __init__(self, *, channel_uid: str, task_id: str, request_id: str, transfers: list[Transfer], plans: dict[int, WorkPlan],
                 channel_info: dict[int, dict], store: Optional[ResultStore], journal: Optional[ChannelJournal], degraded: bool,
                 channel: Any = None, gaps: Iterable[tuple[int, int]] = (), raised: Iterable[Transfer] = (), first_seq: int = 1,
                 clearance_records: Iterable[dict] = ()) -> None:
        self.channel_uid = channel_uid
        self.task_id = task_id
        self.request_id = request_id
        self.transfers = transfers
        self.plans = plans
        self.channel_info = channel_info
        self.store = store
        self.journal = journal
        self.degraded = degraded
        self.channel = channel
        self.gaps = list(gaps)
        self.raised = list(raised)
        self.first_seq = first_seq
        self.clearance_records = list(clearance_records)
        self.first_plan_sha256: Optional[str] = next((x.event.plan_sha256 for x in sorted(list(transfers) + list(raised), key=lambda x: x.seq)), None)
        self.by_message: dict[str, Transfer] = {t.message_id: t for t in transfers if t.message_id}
        self.by_seq: dict[int, Transfer] = {t.seq: t for t in transfers}
        self._link()

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_journal(cls, journal: ChannelJournal, store: Optional[ResultStore] = None, channel: Any = None) -> "OverseerView":
        transfers: list[Transfer] = []
        raised: list[Transfer] = []
        plans: dict[int, WorkPlan] = {}
        info: dict[int, dict] = {}
        clearance_records: list[dict] = []
        first_seq = None
        task_id = journal.task_id
        request_id = ""
        for entry in journal.entries():
            if entry.kind == "clearance" and entry.record_json:
                try:
                    clearance_records.append(json.loads(entry.record_json))
                except Exception:
                    pass
                continue
            ev = entry.event
            if ev is None:
                continue
            first_seq = ev.seq if first_seq is None else first_seq
            request_id = ev.request_id or request_id
            if ev.plan_json:
                try:
                    plans[ev.seq] = faithful(WorkPlan, json.loads(ev.plan_json))
                except Exception:
                    pass
            if ev.channel_json:
                try:
                    info[ev.seq] = json.loads(ev.channel_json)
                except Exception:
                    pass
            t = cls._transfer_from_event(entry.index, ev)
            (raised if ev.raised is not None and ev.receipt_json is None and ev.message_id is None else transfers).append(t)
        return cls(channel_uid=journal.channel_uid, task_id=task_id, request_id=request_id, transfers=transfers, plans=plans, channel_info=info,
                   store=store, journal=journal, degraded=False, channel=channel, gaps=journal.gaps(), raised=raised, first_seq=first_seq or 1,
                   clearance_records=clearance_records)

    @staticmethod
    def _transfer_from_event(index: int, ev: ChannelEvent) -> Transfer:
        envelope = json.loads(ev.envelope_json) if ev.envelope_json else None
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        typed, err, withheld = _parse_typed(ev.kind, payload)
        receipt = None
        receipt_dump = None
        receipt_error = None
        if ev.receipt_json:
            receipt_dump = json.loads(ev.receipt_json)
            try:
                receipt = faithful(TransmissionReceipt, receipt_dump)
            except Exception as exc:
                receipt, receipt_error = None, f"{type(exc).__name__}: {str(exc)[:200]}"
        try:
            call = json.loads(ev.call_json) if ev.call_json else {}
        except Exception:
            call = {}
        return Transfer(seq=ev.seq, index=index, kind=ev.kind, event=ev, message_id=ev.message_id, receipt_id=ev.receipt_id, status=ev.status,
                        delivered=ev.delivered, envelope=envelope, payload=payload, typed=typed, typed_error=err, withheld=withheld, receipt=receipt,
                        receipt_dump=receipt_dump, receipt_error=receipt_error, raw_text=ev.raw_text, call=call, captured={c.result_id: c for c in ev.captured},
                        digest_only=ev.digest_only)

    @classmethod
    def from_channel(cls, channel: Any, store: Optional[ResultStore] = None, channel_uid: Optional[str] = None) -> "OverseerView":
        """Degraded view of a channel audited without hooks: built from the live log, receipts and typed copies."""
        from ..channel.events import ChannelBefore, observation_state, snapshot_event
        uid = channel_uid or getattr(channel, "channel_uid", None) or observation_state(channel).channel_uid
        receipts = {r.message_id: r for r in list(getattr(channel, "receipts", []) or [])}
        transfers: list[Transfer] = []
        plan = getattr(channel, "plan", None)
        empty = ChannelBefore(n_receipts=0, n_log=0, n_conflicts=0, forward_counts=(), superseded=(), transmitted=(), recipients=(), requests=(), pool=())
        msgs = list(channel.log.messages()) if hasattr(channel.log, "messages") else list(getattr(channel.log, "_by_id", {}).values())
        for seq, msg in enumerate(msgs, start=1):
            rc = receipts.get(msg.message_id)
            kind = _kind_of(msg)
            ev = snapshot_event(_FrozenReceiptChannel(channel, rc), kind, channel_uid=uid, seq=seq, before=empty, call={"method": "unknown"},
                                returned=(None, rc) if rc is not None else None)
            t = cls._transfer_from_event(seq, ev)
            transfers.append(t)
        plans = {1: plan} if plan is not None else {}
        info = {1: json.loads(transfers[0].event.channel_json)} if transfers and transfers[0].event.channel_json else {}
        return cls(channel_uid=uid, task_id=getattr(plan, "task_id", ""), request_id=getattr(plan, "request_id", ""), transfers=transfers, plans=plans,
                   channel_info=info, store=store, journal=None, degraded=True, channel=channel)

    # ------------------------------------------------------------------ links
    def _link(self) -> None:
        self._first_delivery: dict[str, int] = {}
        self._forwards: list[Transfer] = []
        self._doc_first: dict[tuple[str, str], int] = {}  # (document id, text digest) -> first delivered request supplying it
        # (seq of a delivered request, word 4-grams of its user input and of every text it supplied): what a later answer
        # may have copied from its sources (rule ``source-explained``)
        self._sources: list[tuple[int, frozenset]] = []
        self._own_cache: dict[tuple[str, int, str], frozenset] = {}
        for t in self.transfers:
            self._link_one(t)

    def _own_shingles(self, report_id: Optional[str], payload: dict) -> Optional[frozenset]:
        """Rule ``source-explained``: the word 4-grams of the report's ``original_response`` that no text a delivered
        request supplied (or user input it stated) before the report's first delivery carries. Only these are the answer's
        own words: a later text that resembles the answer only where the answer copied an earlier source (the same
        passage under another document id, a longer document containing it) resembles the SOURCE, and is never taken to
        present the answer. None when the payload holds no answer."""
        orig = payload.get("original_response")
        if not isinstance(orig, str):
            return None
        first = self._first_delivery.get(report_id or "")
        key = (report_id or "", first if first is not None else -1, _text_key(orig))
        own = self._own_cache.get(key)
        if own is None:
            sa = set(_shingles(orig))
            if first is not None:
                for seq, sh in self._sources:
                    if seq < first:
                        sa -= sh
            own = self._own_cache[key] = frozenset(sa)
        return own

    def _predates(self, doc: Any, report_id: Optional[str]) -> bool:
        """Rule ``source-predates-answer``: True when an earlier delivered request of the task supplied this document id
        with this exact text before ``report_id`` was first delivered (the report's own request included). Such a text
        existed before the answer, so an answer resembling it copied the source, not the other way round: it is never
        linked to that report by author, id or near-copy text."""
        first = self._doc_first.get((doc.document_id, _text_key(doc.text)))
        delivered = self._first_delivery.get(report_id or "")
        return first is not None and delivered is not None and first < delivered

    def _link_one(self, t: Transfer) -> None:
        if t.kind in ("response", "response_text"):
            req = self.by_message.get(t.in_reply_to or "")
            t.request_seq = req.seq if req is not None and req.seq < t.seq else None
            if t.request_seq is not None:
                t.depends_on.append(t.request_seq)
        if t.kind in REPORT_KINDS and t.delivered and t.report_id and t.report_id not in self._first_delivery and (t.report is not None or t.digest_only):
            # a digest-only delivery is registered too, so the forwards and syntheses that depend on it fail with it
            self._first_delivery[t.report_id] = t.seq
        if t.kind == "relay_forward":
            t.delivering_seq = self._first_delivery.get(t.report_id or "")
            if t.delivering_seq is not None:
                t.depends_on.append(t.delivering_seq)
            self._forwards.append(t)
        if t.kind == "request" and t.request is not None:
            for doc in t.request.supplied_texts:
                is_peer = doc.document_id.startswith("peer:")
                cands = [f for f in self._forwards if f.delivered and f.seq < t.seq and f.recipient_agent_id == t.request.to_agent_id]
                same_text = [f for f in reversed(cands) if (f.payload or {}).get("original_response") == doc.text]
                # the text decides the link; among forwards of the same text, the one the document's attribution names
                match = next((f for f in same_text if _attribution_mismatch(doc, f, self._forwards) is None), None) or (same_text[0] if same_text else None)
                if match is not None:
                    t.peer_links.append(PeerLink(doc.document_id, match.seq, match.message_id, match.report_id, True,
                                                 misattributed=_attribution_mismatch(doc, match, self._forwards)))
                    t.depends_on.append(match.seq)
                elif is_peer:
                    last = cands[-1] if cands else None
                    t.peer_links.append(PeerLink(doc.document_id, last.seq if last else None, last.message_id if last else None,
                                                 last.report_id if last else None, False))
                else:
                    # a document under any other id that PRESENTS a forwarded report (its author is that report's agent, its id
                    # names the report or the agent, or its text is a near copy of the report's original_response) is held to
                    # the same byte identity and attribution as a ``peer:`` document; one presenting a delivered report that
                    # was never forwarded to this recipient is linked to no forward (PEER-002)
                    shown = next((f for f in reversed(cands) if not self._predates(doc, f.report_id)
                                  and _presents(doc, f.payload or {}, f.report_id, own=self._own_shingles(f.report_id, f.payload or {}))), None)
                    if shown is not None:
                        t.peer_links.append(PeerLink(doc.document_id, shown.seq, shown.message_id, shown.report_id, _faithful_presentation(doc, shown.payload or {}),
                                                     misattributed=_attribution_mismatch(doc, shown, self._forwards)))
                        t.depends_on.append(shown.seq)
                        continue
                    delivered = next((d for d in reversed(self.transfers) if d.seq < t.seq and d.kind in REPORT_KINDS and d.delivered
                                      and not self._predates(doc, d.report_id)
                                      and _presents(doc, d.payload or {}, d.report_id, own=self._own_shingles(d.report_id, d.payload or {}))), None)
                    if delivered is not None:
                        t.peer_links.append(PeerLink(doc.document_id, None, None, delivered.report_id, False))
            if t.delivered:
                seen = set(_shingles(t.request.user_input or ""))
                for doc in t.request.supplied_texts:
                    self._doc_first.setdefault((doc.document_id, _text_key(doc.text)), t.seq)
                    seen |= _shingles(doc.text)
                self._sources.append((t.seq, frozenset(seen)))
        if t.kind == "relay_synthesis" and t.synthesis is not None:
            for rid in t.synthesis.source_report_ids:
                seq = self._first_delivery.get(rid)
                t.cited_delivery_seqs[rid] = seq if seq is not None and seq < t.seq else None
                if seq is not None:
                    t.depends_on.append(seq)
                    t.depends_on.extend(f.seq for f in self._forwards if f.report_id == rid and f.seq < t.seq)
        t.depends_on = sorted(set(t.depends_on))

    def extend(self, entry) -> Optional[Transfer]:
        """Add one journal entry appended after this view was built (the live tier's incremental view)."""
        if entry.kind == "clearance" and entry.record_json:
            try:
                self.clearance_records.append(json.loads(entry.record_json))
            except Exception:
                pass
            return None
        if entry.kind == "gap" and entry.record_json:
            try:
                r = json.loads(entry.record_json)
                self.gaps.append((int(r["missing_from"]), int(r["missing_to"])))
            except Exception:
                pass
            return None
        ev = entry.event
        if ev is None:
            return None
        if ev.plan_json:
            try:
                self.plans[ev.seq] = faithful(WorkPlan, json.loads(ev.plan_json))
            except Exception:
                pass
        if ev.channel_json:
            try:
                self.channel_info[ev.seq] = json.loads(ev.channel_json)
            except Exception:
                pass
        if not self.request_id:
            self.request_id = ev.request_id
        if not self.transfers and not self.raised:
            self.first_seq = ev.seq
            self.first_plan_sha256 = ev.plan_sha256
        t = self._transfer_from_event(entry.index, ev)
        if ev.raised is not None and ev.receipt_json is None and ev.message_id is None:
            self.raised.append(t)
            return t
        self.transfers.append(t)
        if t.message_id:
            self.by_message[t.message_id] = t
        self.by_seq[t.seq] = t
        self._link_one(t)
        return t

    # ------------------------------------------------------------------ queries
    def plan_at(self, seq: int) -> Optional[WorkPlan]:
        """The plan every rule applies at ``seq``: the FIRST journaled plan (rule ``pinned-setup``). A plan the channel
        holds later (the router's own plan object mutated, or ``ch.plan`` replaced) is never adopted as the baseline:
        the event that carries it is a custody fault (:meth:`setup_changes`, OVS-CUST-002)."""
        return self.plan

    @property
    def plan(self) -> Optional[WorkPlan]:
        return self.plans[min(self.plans)] if self.plans else None

    def info_at(self, seq: int) -> dict:
        """The channel's journaled description at ``seq`` (the latest at or before it). Its hook flags may change during a
        task; its solver configuration, engine key id and branch are pinned to the first event (:meth:`config_at`,
        :meth:`key_id_at`)."""
        best: dict = {}
        for s in sorted(self.channel_info):
            if s <= seq:
                best = self.channel_info[s]
        return best or (self.channel_info[min(self.channel_info)] if self.channel_info else {})

    @property
    def pinned_info(self) -> dict:
        """The first journaled channel description: the solver configuration, key id and branch every event is held to."""
        return self.channel_info[min(self.channel_info)] if self.channel_info else {}

    def config_at(self, seq: int) -> SolverConfig:
        """The channel's solver configuration as journaled at its FIRST event (rule ``pinned-setup``): a configuration
        swapped in later is never the reference a result is checked or replayed against."""
        cfg = self.pinned_info.get("config")
        try:
            return faithful(SolverConfig, cfg) if cfg else SolverConfig()
        except Exception:
            return SolverConfig()

    def key_id_at(self, seq: int) -> Optional[str]:
        return self.pinned_info.get("key_id")

    def setup_changes(self, t: "Transfer") -> list[str]:
        """What of the channel's pinned setup the event of ``t`` was issued under a different value of (rule
        ``pinned-setup``): the work plan (its digest against the first event's), the solver configuration, the engine
        key id or the branch (against the first journaled channel description). Empty when none changed."""
        out: list[str] = []
        first = self.first_plan_sha256
        if first is not None and t.event.plan_sha256 and t.event.plan_sha256 != first:
            out.append(f"the work plan (digest {t.event.plan_sha256[:12]}, where the first event journaled {first[:12]})")
        pinned = self.pinned_info
        if pinned and t.event.channel_json:
            try:
                now = json.loads(t.event.channel_json)
            except Exception:
                now = {}
            for key, label in (("config", "the solver configuration"), ("key_id", "the engine key id"), ("branch", "the branch")):
                if now.get(key) != pinned.get(key):
                    diff = ""
                    if key == "config" and isinstance(now.get(key), dict) and isinstance(pinned.get(key), dict):
                        diff = f" (fields {sorted(k for k in set(now[key]) | set(pinned[key]) if now[key].get(k) != pinned[key].get(k))})"
                    out.append(label + diff)
        return out

    def first_delivery(self, report_id: str, before_seq: Optional[int] = None) -> Optional[Transfer]:
        for t in self.transfers:
            if before_seq is not None and t.seq >= before_seq:
                break
            if t.kind in REPORT_KINDS and t.delivered and t.report_id == report_id and t.report is not None:
                return t
        return None

    def transmitted_before(self, seq: int) -> dict[str, Transfer]:
        """report_id -> its first delivery before ``seq``, in delivery order (the channel's ``transmitted_reports``)."""
        out: dict[str, Transfer] = {}
        for t in self.transfers:
            if t.seq >= seq:
                break
            if t.kind in REPORT_KINDS and t.delivered and t.report is not None and t.report_id not in out:
                out[t.report_id] = t
        return out

    def requests_before(self, seq: int) -> list[Transfer]:
        return [t for t in self.transfers if t.kind == "request" and t.seq < seq and t.delivered and t.request is not None]

    def previous(self, seq: int) -> Optional[Transfer]:
        prev = None
        for t in self.transfers:
            if t.seq >= seq:
                break
            prev = t
        return prev

    def outcome_problem(self, claim_id: str, problem_digest: str, upto_seq: Optional[int] = None):
        """The pooled problem of ``claim_id`` with digest ``problem_digest``, from the journaled outcomes."""
        from ..ir.canonical import problem_digest as _pd
        for t in self.transfers:
            if upto_seq is not None and t.seq > upto_seq:
                break
            if t.receipt is None:
                continue
            for o in t.receipt.outcomes:
                p = o.translation.problem
                if o.claim_id == claim_id and p is not None and _pd(p) == problem_digest:
                    return p
        return None

    def transfers_for(self, seqs: Iterable[int]) -> list[Transfer]:
        return [self.by_seq[s] for s in seqs if s in self.by_seq]


#: Word shingle length and the containment (both ways) at which a supplied text is a near copy of a report's answer.
_SHINGLE = 4
NEAR_COPY = 0.6


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = text.casefold().split()
    if len(words) < _SHINGLE:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + _SHINGLE]) for i in range(len(words) - _SHINGLE + 1)}


def near_copy(a: str, b: str) -> bool:
    """True when ``a`` and ``b`` are near copies of each other: at least :data:`NEAR_COPY` of each one's word 4-grams occur
    in the other (a changed figure or word keeps both high; an extract the answer merely quotes keeps the answer's low)."""
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return False
    common = len(sa & sb)
    return common / len(sa) >= NEAR_COPY and common / len(sb) >= NEAR_COPY


def contains_answer(text: str, answer: str) -> bool:
    """True when ``text`` CONTAINS most of ``answer``: at least :data:`NEAR_COPY` of the answer's word 4-grams occur in
    the text, however much other prose surrounds them (rule ``contains-answer``: a forwarded answer padded with
    background, or introduced by "the history specialist wrote:", is still that answer)."""
    sa = _shingles(answer)
    if not sa:
        return False
    return len(sa & _shingles(text)) / len(sa) >= NEAR_COPY


def _text_key(text: str) -> str:
    from ..ir.canonical import sha256_hex
    return sha256_hex(text or "")


def _presents(doc: Any, payload: dict, report_id: Optional[str], *, own: Optional[frozenset] = None) -> bool:
    """Whether a supplied text presents the report ``payload``: its author is the report's agent, its id is the report id
    or the agent id, or its text contains most of the answer's OWN words (``own``: the 4-grams of its
    ``original_response`` that no earlier source carries, rule ``source-explained``; all of them when not given): a near
    copy of the answer, or the answer padded with other prose (``contains-answer``). An answer made only of its sources'
    words is never presented by text."""
    agent = payload.get("agent_id")
    author = (getattr(doc, "author", None) or "").strip()
    if agent and author == agent:
        return True
    if doc.document_id in {x for x in (report_id, agent) if x}:
        return True
    orig = payload.get("original_response")
    if not isinstance(orig, str):
        return False
    words = own if own is not None else frozenset(_shingles(orig))
    return bool(words) and len(words & _doc_shingles(doc.text)) / len(words) >= NEAR_COPY


@functools.lru_cache(maxsize=64)
def _doc_shingles(text: str) -> frozenset:
    """The word 4-grams of a supplied text, cached: one document is compared with every earlier report of the task."""
    return frozenset(_shingles(text))


def _faithful_presentation(doc: Any, payload: dict) -> bool:
    """Whether a supplied text that presents a forwarded report carries its answer byte for byte: the whole text, or,
    for a text that contains the answer among other prose, the answer as one verbatim span."""
    orig = payload.get("original_response")
    if not isinstance(orig, str) or not orig:
        return False
    return doc.text == orig or (orig in doc.text and not near_copy(doc.text, orig) and contains_answer(doc.text, orig))


def _attribution_mismatch(doc: Any, forward: Transfer, forwards: list[Transfer]) -> Optional[str]:
    """Why a peer document's attribution is not the forward it is linked to: its ``author`` is not the forwarded report's
    agent, or its id ``peer:<x>`` names a forwarded report id other than the linked one. None when it agrees (or the
    document names neither)."""
    agent = (forward.payload or {}).get("agent_id")
    author = (getattr(doc, "author", None) or "").strip()
    if author and agent and author != agent:
        return f"its author is {author!r} but the forwarded report {forward.report_id} is agent {agent!r}'s"
    named = doc.document_id[len("peer:"):] if doc.document_id.startswith("peer:") else ""
    if named and named != forward.report_id and any(f.report_id == named for f in forwards):
        return f"its id names report {named!r} but its text is the forwarded report {forward.report_id}"
    return None


class _FrozenReceiptChannel:
    """Adapter so ``snapshot_event`` can describe one logged message of a live channel in the degraded view."""

    def __init__(self, channel: Any, receipt: Any) -> None:
        self._ch = channel
        self.receipts = [receipt] if receipt is not None else []
        self.plan = channel.plan
        self.log = channel.log
        self.requests = channel.requests
        self.transmitted_reports = channel.transmitted_reports
        self.key_id = getattr(channel, "key_id", None)
        self.config = getattr(channel, "config", None)
        self.branch = getattr(channel, "branch", None)
        self.formalize_synthesis_fn = getattr(channel, "formalize_synthesis_fn", None)
        self.verify_claim_fn = getattr(channel, "verify_claim_fn", None)
        self.formalized = {}
        self.formalized_by = {}
        self.ambiguous_pooled = set()


def _kind_of(msg: Any) -> str:
    contract = (msg.contract or "").split("/", 1)[0]
    role = getattr(msg.sender_role, "value", msg.sender_role)
    rrole = getattr(msg.recipient_role, "value", msg.recipient_role)
    if contract == "task_request":
        return "request"
    if contract == "specialist_report_forward":
        return "relay_forward"
    if contract == "synthesis":
        return "relay_synthesis"
    if contract == "specialist_report":
        if role == "specialist" and rrole == "router" and msg.in_reply_to:
            return "response"
        return "relay_report"
    return contract or "unknown"
