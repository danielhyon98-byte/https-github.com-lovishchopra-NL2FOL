"""The twofold mode of a combined answer (``N_FOLD``; architecture step 3; design ``docs/OVERSEER_DESIGN.md`` section 52).

When a response combines N >= 2 specialists' answers (two subjects, say, joined by the combinator's synthesis), the
overseer reviews it in N + 1 parts instead of as one dossier:

1. **The layout** (:func:`combined_layout`, read from the JOURNAL view, never from live objects): the channel holds a
   delivered synthesis whose cited reports were delivered by N >= 2 distinct specialists. Source k owns the requests
   addressed to its specialist, the specialist's responses and the relays of its reports (a forward is owned by its
   recipient: it is part of what that specialist was given); the merged part owns the syntheses and every transfer no
   source owns. Each part's dossier holds its own transfers and every transfer they depend on (a response's request, a
   forward's delivery, a synthesis's cited deliveries), so every link of a part dossier resolves inside it.
2. **The source reviews, in parallel** (:func:`run_twofold`): one dossier per source (:func:`part_view`; a dossier with
   a ``review`` member: ``{"method": "N_FOLD", "role": "source", "source": k, "of": N}``) issued to the instances the
   pool plan assigns that source, and run at once (one thread per instance of a wave; an instance assigned two sources
   of one dossier, which the plan allows only when it has no instance to spare, reviews them in turn, since one agent
   holds one open issue per task). Every verdict goes through the verdict intake and is validated against the FULL
   journal and the signed results, as any verdict is.
3. **The temporary context** (:class:`TemporaryContext`): what validation accepted of the source reviews, as structured
   records: per source its specialist, its delivered report and message ids, how many verdicts were assessed, and each
   CONFIRMED fault as its accusation kind and the identifiers its confirming findings cover (the claims, reports,
   messages, documents and results it concerns), each claim pinned to the one report its confirming findings name (a
   revision keeps its claims' ids, so the id alone does not say which report's claim was faulty). Never an agent's prose
   (statements and notes are never copied), never an ``OVS`` code, a finding's text, a consolidation result or a fault
   label, and no refuted, unverifiable or unresolved accusation. What it does disclose, in both modes, is that a
   deterministic check confirmed each listed fault (its kind and identifiers). A BLIND merged review's context leaves out
   every fault whose kind only a signature verification, a replay or a custody comparison decides
   (:data:`BLIND_HIDDEN_KINDS`: a blind dossier never shows a signature-verification outcome or an auditor finding;
   architecture review after arena round 8), so a blind merged reviewer learns of a source's content faults only. It is
   **scoped** to the request (its channel, task and request; a dossier of any other channel, task or request is refused
   it), **bounded** (its canonical JSON at
   most the plan's bound, 65,536 bytes at the floor; past it the last records are cut and counted, ``omitted``, and the
   record says ``complete: false``), **recorded** in the signed verdicts audit of the review (its digest, size, bound,
   scope and every record), and **discarded** after the request (:meth:`TemporaryContext.discard`: its records and the
   confirming references validation used are dropped; a discarded context is refused by the intake and decides nothing).
4. **The merged review**: one dossier of the merged part (the synthesis and the source deliveries it cites, and
   whatever no source owns) with ``review: {"method": "N_FOLD", "role": "merged", "of": N}`` and the context as
   ``temporary_context``, issued to the instances the plan assigns the merged review. It asks whether the synthesis
   carries each source faithfully, keeps the flaws the source reviews found, adds no claim either source lacks, and
   keeps its certainty no stronger than its weakest source. A synthesized claim that cites a source claim the context
   lists as a confirmed fault is accused ``synthesis_carries_fault``, which validation decides by rule ``carried-fault``
   (:mod:`~epinoic_overseer.validate`): confirmed, citing the source fault's own confirming findings, when the journaled
   synthesis shows the claim cites it and the cited id is that report's claim (in the synthesis's ledger scope only the
   report the record names holds it: a revision keeps its claims' ids); refuted when the named synthesized claims cite
   none of the named source claims; unresolved (human review) when the context records no confirmed fault on what the
   claim cites, when the citation is another report's claim id or one two reports hold, or when the context is gone.
5. **The combination**: the source and merged verdicts are combined by the existing rule (``combine_verdicts``: no
   voting on facts), per part and over the whole, and the signed verdicts audit records the N_FOLD, each part's
   instances and outcome, the temporary context and its discard. Agents never gate clearance: ``OVS-AGENT-*`` findings
   change no clearance, and a confirmed accusation acts only through the auditor's own ``OVS-*`` finding.

Everything here reads journaled data as data: nothing of an agent's reply is evaluated or followed, and the context
carries only closed vocabularies and identifiers the dossiers already show. All instances are the pool's
``OverseerAgentRunner`` instances, built from its one loaded pack, on the cheapest tier.
"""
from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from epinoic_logic.api.ir import canonical_json, sha256_hex
from .verdicts import ACCUSATION_KINDS, ID_FIELDS, IDENTIFIER_PATTERN

__all__ = [
    "CONTEXT_FORMAT", "CONTEXT_MAX_BYTES", "N_FOLD_MIN_PACK_MAJOR", "teaches_n_fold", "SourcePart", "CombinedLayout", "combined_layout", "part_view", "features_of", "part_reading",
    "pool_item", "ContextFault", "ContextSource", "ContextScope", "TemporaryContextRecord", "TemporaryContext", "TwofoldPart", "TwofoldReview",
    "run_twofold", "review_scope", "BLIND_HIDDEN_KINDS",
]

CONTEXT_FORMAT = "overseer-temporary-context/1.0"
#: The first pack MAJOR version that teaches the N_FOLD review (the ``review`` and ``temporary_context`` dossier members and
#: the kind ``synthesis_carries_fault``): pack 2.0. A part dossier is never issued under an older pack.
N_FOLD_MIN_PACK_MAJOR = 2
#: The temporary context's bound at the floor (the router port's ``CONTEXT_MAX_BYTES``).
CONTEXT_MAX_BYTES = 65536
#: The accusation kinds that only a signature verification, a replay or a custody comparison of the live objects with the
#: journal decides (their ``KIND_CHECKS``: OVS-RES-*, OVS-CUST-*, the receipt's digest and statement checks): a blind
#: dossier never shows such an outcome, so a blind merged review's temporary context leaves them out (step 3).
BLIND_HIDDEN_KINDS: frozenset[str] = frozenset({"result_unsigned_or_forged", "replay_differs", "result_from_other_problem", "result_out_of_task",
                                                "payload_altered", "receipt_altered"})
_STEM_BRANCHES = frozenset({"sciences", "mathematics", "computer_science"})
_REPORT_KINDS = ("response", "response_text", "relay_report")


# ============================================================================================ the layout
@dataclass(frozen=True)
class SourcePart:
    """One source of a combined answer: its position (1 to N), the specialist, the delivered reports the synthesis cites,
    the transfers it owns, and the transfers its dossier holds (its own and every transfer they depend on)."""
    index: int
    agent_id: str
    report_ids: tuple[str, ...]
    message_ids: tuple[str, ...]
    own_seqs: tuple[int, ...]
    seqs: tuple[int, ...]


@dataclass(frozen=True)
class CombinedLayout:
    """A combined answer as the journal shows it: its N >= 2 sources in the order their answers were first delivered, the
    syntheses, and the merged part (the syntheses and every transfer no source owns, with their dependencies)."""
    channel_uid: str
    task_id: str
    request_id: str
    sources: tuple[SourcePart, ...]
    synthesis_ids: tuple[str, ...]
    synthesis_message_ids: tuple[str, ...]
    merged_own: tuple[int, ...]
    merged_seqs: tuple[int, ...]

    @property
    def n(self) -> int:
        return len(self.sources)


def _closure(view: Any, seqs: Iterable[int]) -> tuple[int, ...]:
    out: set[int] = set()
    stack = list(seqs)
    while stack:
        s = stack.pop()
        if s in out or s not in view.by_seq:
            continue
        out.add(s)
        stack.extend(view.by_seq[s].depends_on)
    return tuple(sorted(out))


def _owner(t: Any) -> Optional[str]:
    """The specialist a transfer belongs to: a request's addressee, a response's sender, a forward's recipient (what it
    was given), any other relayed report's sender; ``None`` for a synthesis."""
    if t.kind == "request":
        return t.request.to_agent_id if t.request is not None else t.recipient_agent_id
    if t.kind in ("response", "response_text"):
        return t.sender_agent_id
    if t.kind == "relay_forward":
        return t.recipient_agent_id
    if t.kind == "relay_report":
        return t.sender_agent_id
    return None


def combined_layout(view: Any) -> Optional[CombinedLayout]:
    """The combined answer the journaled ``view`` holds, or ``None`` when it holds none: no delivered synthesis whose cited
    reports were delivered by at least two distinct specialists. Deterministic: the sources in the order of the first
    delivery of a cited report, each part's transfers in sequence order."""
    if getattr(view, "degraded", False):
        return None
    syntheses = [t for t in view.transfers if t.kind == "relay_synthesis" and t.delivered and t.synthesis is not None]
    if not syntheses:
        return None
    cited: dict[str, int] = {}
    for t in syntheses:
        for rid, seq in t.cited_delivery_seqs.items():
            if seq is not None:
                cited.setdefault(rid, seq)
    agents: dict[str, list[tuple[int, str]]] = {}
    for rid, seq in cited.items():
        d = view.by_seq.get(seq)
        agent = d.sender_agent_id if d is not None else None
        if agent:
            agents.setdefault(agent, []).append((seq, rid))
    if len(agents) < 2:
        return None
    order = sorted(agents, key=lambda a: min(s for s, _r in agents[a]))
    owned: dict[str, list[int]] = {a: [] for a in order}
    merged_own: list[int] = []
    for t in view.transfers:
        a = _owner(t)
        (owned[a] if a in owned else merged_own).append(t.seq)
    sources = []
    for k, a in enumerate(order, start=1):
        own = tuple(sorted(owned[a]))
        seqs = _closure(view, own)
        mids = tuple(view.by_seq[s].message_id for s in seqs if view.by_seq[s].message_id and view.by_seq[s].kind in _REPORT_KINDS
                     and view.by_seq[s].sender_agent_id == a)
        sources.append(SourcePart(index=k, agent_id=a, report_ids=tuple(r for _s, r in sorted(agents[a])), message_ids=mids, own_seqs=own, seqs=seqs))
    plan = view.plan
    return CombinedLayout(channel_uid=view.channel_uid, task_id=getattr(plan, "task_id", None) or view.task_id or "",
                          request_id=getattr(plan, "request_id", None) or view.request_id or "", sources=tuple(sources),
                          synthesis_ids=tuple(dict.fromkeys(t.synthesis.synthesis_id for t in syntheses)),
                          synthesis_message_ids=tuple(t.message_id for t in syntheses if t.message_id),
                          merged_own=tuple(sorted(merged_own)), merged_seqs=_closure(view, merged_own))


def part_view(view: Any, seqs: Sequence[int]) -> Any:
    """The view of one part: COPIES of the journaled transfers ``seqs`` (their links reset and re-derived inside the part,
    so the full view is never touched), the same channel, plans, configuration and result store."""
    from .view import OverseerView
    keep = set(seqs)
    copies = [dataclasses.replace(t, request_seq=None, delivering_seq=None, peer_links=[], cited_delivery_seqs={}, depends_on=[])
              for t in view.transfers if t.seq in keep]
    return OverseerView(channel_uid=view.channel_uid, task_id=view.task_id, request_id=view.request_id, transfers=copies, plans=dict(view.plans),
                        channel_info=dict(view.channel_info), store=view.store, journal=view.journal, degraded=False, channel=view.channel,
                        first_seq=view.first_seq)


class _Transfers:
    """A view-shaped list of transfers, for the readings that iterate ``view.transfers`` (``emitted.risk_reading``)."""

    def __init__(self, transfers: Sequence[Any]) -> None:
        self.transfers = list(transfers)


def features_of(transfers: Sequence[Any]) -> Any:
    """The size features of a dossier (or a part) the flash decision maker prices: its transfers, the characters of what
    a dossier shows of them (the journaled envelopes, receipts and raw texts), whether its content is STEM (a STEM branch's
    receipt, a STEM check or an ST code) and how many translations its receipts carry."""
    from .pool import PoolFeatures
    chars = translations = 0
    stem = False
    for t in transfers:
        ev = t.event
        chars += len(ev.envelope_json or "") + len(ev.receipt_json or "") + len(t.raw_text or "")
        rc = t.receipt_dump if isinstance(t.receipt_dump, dict) else {}
        translations += sum(1 for o in rc.get("outcomes") or () if isinstance(o, dict) and o.get("translation") is not None)
        if rc.get("branch") in _STEM_BRANCHES or any(isinstance(c, dict) and str(c.get("constraint_id", "")).startswith("stem-")
                                                     for c in rc.get("formal_checks") or ()) \
                or any(isinstance(f, dict) and str(f.get("code", "")).startswith("ST-") for k in ("findings", "structural_findings") for f in rc.get(k) or ()):
            stem = True
    return PoolFeatures(transfers=len(transfers), chars=min(chars, 1_000_000_000), stem=stem, translations=min(translations, 1_000_000))


def part_reading(view: Any, own: Sequence[int], seqs: Sequence[int], repeated_messages: Mapping[str, int]) -> Any:
    """One part of a combined answer as the pool reads it: the repeated faults and the risk signals and records of its
    OWN transfers, and the size of its dossier."""
    from .emitted import risk_reading
    from .pool import PoolPart
    mine = [view.by_seq[s] for s in own if s in view.by_seq]
    signals, records = risk_reading(_Transfers(mine))
    repeated = sum(repeated_messages.get(t.message_id, 0) for t in mine if t.message_id)
    return PoolPart(repeated_faults=repeated, risk_signals=signals, risk_records=records,
                    features=features_of([view.by_seq[s] for s in seqs if s in view.by_seq]))


def pool_item(view: Any, key: str, repeated_faults: int, repeated_messages: Mapping[str, int]) -> tuple[Any, Optional[CombinedLayout]]:
    """The pool's item for one task (``hub.review_pool``): its whole-task reading as before, its size and, for a combined
    answer, its parts; with the layout the review then runs."""
    from .emitted import risk_reading
    from .pool import PoolItem
    signals, records = risk_reading(view)
    layout = combined_layout(view)
    kw: dict[str, Any] = dict(key=key, repeated_faults=repeated_faults, risk_signals=signals, risk_records=records, features=features_of(view.transfers))
    if layout is not None:
        kw.update(sources=tuple(part_reading(view, p.own_seqs, p.seqs, repeated_messages) for p in layout.sources),
                  merged=part_reading(view, layout.merged_own, layout.merged_seqs, repeated_messages))
    return PoolItem(**kw), layout


# ============================================================================================ the temporary context
_ID = Field(pattern=IDENTIFIER_PATTERN)
_IDS = Field(default_factory=list, max_length=64)


class ContextFault(BaseModel):
    """One fault a source review confirmed: its accusation kind (closed) and the identifiers its confirming findings
    cover. No text of any agent and no finding code."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: str
    claim_ids: list[str] = _IDS
    report_ids: list[str] = _IDS
    message_ids: list[str] = _IDS
    document_ids: list[str] = _IDS
    result_ids: list[str] = _IDS


class ContextSource(BaseModel):
    """One source of the combined answer in the context: its position, its specialist, its delivered reports and messages,
    the verdicts validation assessed on it, and the faults they confirmed."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: int = Field(ge=1, le=16)
    agent_id: str
    report_ids: list[str] = _IDS
    message_ids: list[str] = _IDS
    reviewed: int = Field(ge=0, le=64)
    confirmed: list[ContextFault] = Field(default_factory=list, max_length=4096)


class ContextScope(BaseModel):
    """The request the context belongs to (the channel is kept apart, on the live object)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str
    request_id: str


class TemporaryContextRecord(BaseModel):
    """The temporary context as a merged-review dossier shows it (``temporary_context``) and the signed audit records it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: str = Field(pattern=r"^overseer-temporary-context/1\.0$")
    scope: ContextScope
    max_bytes: int = Field(ge=1, le=CONTEXT_MAX_BYTES)
    bytes: int = Field(ge=0)
    sources: list[ContextSource] = Field(default_factory=list, max_length=16)
    omitted: int = Field(ge=0)
    complete: bool
    discard: str = Field(pattern=r"^after_request$")
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _pinned_reports(acc: Any, claim_ids: Sequence[str]) -> dict[str, str]:
    """``claim id -> the one report`` a confirmed accusation's fault on that claim is pinned to: of the reports carrying the
    claim in the source review's dossier (``claim_report_ids``), those its confirming findings name (all of them when the
    findings name no report), when exactly one remains. A specialist's revision keeps its claims' ids, so a claim id alone
    does not say which report's claim was confirmed faulty; a claim with no one report is pinned to none, and confirms no
    carried fault (rule ``carried-fault``)."""
    out: dict[str, str] = {}
    for c in claim_ids:
        found = {r for ref in acc.confirming if not ref.claim_ids or c in ref.claim_ids for r in ref.report_ids}
        reps = [r for r in dict.fromkeys(acc.claim_report_ids.get(c) or []) if r and (not found or r in found)]
        if len(reps) == 1:
            out[c] = reps[0]
    return out


def _body_bytes(body: Mapping[str, Any]) -> int:
    """The context's size: the UTF-8 bytes of the canonical JSON of its record without ``bytes`` and ``context_sha256``."""
    return len(canonical_json({k: v for k, v in body.items() if k not in ("bytes", "context_sha256")}).encode("utf-8"))


class TemporaryContext:
    """The live temporary context of one combined answer's N_FOLD review (module docstring, step 3). Built only from
    validated assessments; holds, beside the shown record, the confirming finding references validation needs (rule
    ``carried-fault``), and drops both when it is discarded."""

    def __init__(self, *, channel_uid: str, record: dict, refs: dict[tuple[str, str], list[Any]]) -> None:
        self.channel_uid = channel_uid
        self._record = record
        self._refs = refs
        self.digest: str = record["context_sha256"]
        self.discarded = False

    @property
    def record(self) -> dict:
        """The shown record (a copy); ``{}`` once discarded."""
        return json.loads(canonical_json(self._record)) if not self.discarded else {}

    @property
    def scope(self) -> tuple[str, str, str]:
        return (self.channel_uid, self._record["scope"]["task_id"], self._record["scope"]["request_id"])

    def faulted(self) -> dict[tuple[str, str], list[Any]]:
        """``(report_id, claim_id) -> confirming finding references`` of every confirmed source fault the record shows
        (empty once discarded)."""
        return {} if self.discarded else {k: list(v) for k, v in self._refs.items()}

    def verifies(self) -> bool:
        """The record still hashes to its digest (an edited record decides nothing)."""
        if self.discarded:
            return False
        body = {k: v for k, v in self._record.items() if k not in ("context_sha256",)}
        return sha256_hex(canonical_json(body)) == self.digest

    def discard(self) -> None:
        """Discard the context after the request: its records and references are dropped; its digest stays for the audit."""
        self._record = {}
        self._refs = {}
        self.discarded = True

    @classmethod
    def build(cls, layout: CombinedLayout, assessments: Mapping[int, Sequence[Any]], *, max_bytes: int = CONTEXT_MAX_BYTES,
              mode: str = "informed") -> "TemporaryContext":
        """The context of ``layout`` from the validated assessments of each source review (``source index -> assessments``):
        only valid assessments, only confirmed accusations, each as its kind and the identifiers its confirming findings
        cover, with the report each claim is pinned to (:func:`_pinned_reports`), deduplicated, in source order then kind
        and identifier order; cut from the end to the bound. In ``blind`` mode no fault of a kind in
        :data:`BLIND_HIDDEN_KINDS` is shown (nor decides anything through the context)."""
        if not 1 <= int(max_bytes) <= CONTEXT_MAX_BYTES:
            raise ValueError(f"the temporary context's bound is 1 to {CONTEXT_MAX_BYTES} bytes")
        if mode not in ("blind", "informed"):
            raise ValueError(f"unknown review mode {mode!r}")
        hidden = BLIND_HIDDEN_KINDS if mode == "blind" else frozenset()
        sources: list[dict] = []
        flat: list[tuple[int, dict, dict[tuple[str, str], list[Any]]]] = []  # (source, shown record, its confirming references)
        for part in layout.sources:
            valid = [a for a in assessments.get(part.index, ()) if getattr(a, "valid", False)]
            faults: dict[str, tuple[dict, dict[tuple[str, str], list[Any]]]] = {}
            for va in valid:
                for acc in va.accusations:
                    if acc.outcome != "confirmed" or acc.kind not in ACCUSATION_KINDS or acc.kind in hidden:
                        continue
                    ids = acc.covered_identifiers if acc.covered_identifiers and any(acc.covered_identifiers.values()) else acc.identifiers
                    rec = {"kind": acc.kind, **{k: sorted(dict.fromkeys(ids.get(k, []))) for k in ID_FIELDS if k != "receipt_ids"}}
                    pins = _pinned_reports(acc, rec["claim_ids"])
                    rec["report_ids"] = sorted(set(rec["report_ids"]) | set(pins.values()))
                    key = canonical_json(rec)
                    _shown, rec_refs = faults.setdefault(key, (rec, {}))
                    for c in rec["claim_ids"]:
                        bucket = rec_refs.setdefault((pins.get(c, ""), c), [])  # "" (no one report): it confirms no carried fault
                        for ref in acc.confirming:
                            if ref not in bucket:
                                bucket.append(ref)
            sources.append({"source": part.index, "agent_id": part.agent_id, "report_ids": list(part.report_ids), "message_ids": list(part.message_ids),
                            "reviewed": len(valid), "confirmed": []})
            for key in sorted(faults):
                flat.append((part.index, faults[key][0], faults[key][1]))
        body: dict[str, Any] = {"format": CONTEXT_FORMAT, "scope": {"task_id": layout.task_id, "request_id": layout.request_id}, "max_bytes": int(max_bytes),
                                "sources": sources, "omitted": 0, "complete": True, "discard": "after_request"}
        kept = list(flat)
        while True:
            for s in sources:
                s["confirmed"] = [f for idx, f, _r in kept if idx == s["source"]]
            body["omitted"] = len(flat) - len(kept)
            body["complete"] = not body["omitted"]
            body["bytes"] = _body_bytes(body)
            if body["bytes"] <= max_bytes or not kept:
                break
            kept.pop()
        if body["bytes"] > max_bytes:  # even the sources' own entries exceed the bound: no source entry is shown
            body["sources"] = []
            body["omitted"] = len(flat)
            body["complete"] = False
            body["bytes"] = _body_bytes(body)
            kept = []
            if body["bytes"] > max_bytes:  # a context is never larger than its bound (the floor's 65,536 always holds the empty record)
                raise ValueError(f"the temporary context's bound of {max_bytes} bytes cannot hold its empty record ({body['bytes']} bytes)")
        refs: dict[tuple[str, str], list[Any]] = {}
        for _idx, _rec, rec_refs in kept:  # only what the record shows decides anything (rule carried-fault)
            for pair, xs in rec_refs.items():
                bucket = refs.setdefault(pair, [])
                bucket.extend(x for x in xs if x not in bucket)
        digest = sha256_hex(canonical_json(body))
        record = {**body, "context_sha256": digest}
        TemporaryContextRecord.model_validate(record)
        return cls(channel_uid=layout.channel_uid, record=record, refs=refs)


def teaches_n_fold(pack: Any) -> bool:
    """Whether ``pack`` (a ``PackIdentity``) teaches the N_FOLD review: its MAJOR version is :data:`N_FOLD_MIN_PACK_MAJOR`
    or later (the pack version pattern is ``MAJOR.MINOR``)."""
    try:
        return int(str(pack.version).split(".", 1)[0]) >= N_FOLD_MIN_PACK_MAJOR
    except (AttributeError, ValueError):
        return False


def review_scope(role: str, n: int, source: Optional[int] = None) -> dict:
    """The ``review`` member of a part dossier."""
    out: dict[str, Any] = {"method": "N_FOLD", "role": role, "of": int(n)}
    if role == "source":
        out["source"] = int(source)  # type: ignore[arg-type]
    return out


# ============================================================================================ the execution
@dataclass(frozen=True)
class TwofoldPart:
    """What one part's review did: the part (``source`` k or ``merged``), its instances, its runs and assessments, and
    their combination."""
    role: str
    index: int
    agent_ids: tuple[str, ...]
    runs: tuple[Any, ...]
    assessments: tuple[Any, ...]
    combined: Optional[Any]
    refused: tuple[tuple[str, str], ...]
    runner_errors: tuple[tuple[str, str], ...]
    dossier_sha256: tuple[str, ...]


@dataclass(frozen=True)
class TwofoldReview:
    """The N_FOLD review of one combined answer: its layout, each source's review, the temporary context as recorded (its
    record and digest; the live context is discarded), the merged review, and the carried faults it confirmed."""
    layout: CombinedLayout
    sources: tuple[TwofoldPart, ...]
    merged: TwofoldPart
    context_record: dict
    context_sha256: str
    context_discarded: bool
    carried: tuple[dict, ...]


def _run_wave(jobs: Sequence[tuple[Any, dict]], intake: Any, *, parallel: bool) -> list[tuple[Optional[Any], Optional[str]]]:
    """Run ``(runner, dossier)`` jobs, at once when ``parallel`` (one thread per job), each result ``(run, error type)`` in
    job order. A runner that raises is recorded as no review."""
    def one(job: tuple[Any, dict]) -> tuple[Optional[Any], Optional[str]]:
        r, d = job
        try:
            return r.run(d, intake), None
        except Exception as exc:  # noqa: BLE001 - a broken runner never breaks the review; it is no review
            return None, type(exc).__name__
    if not jobs:
        return []
    if not parallel or len(jobs) == 1:
        return [one(j) for j in jobs]
    with ThreadPoolExecutor(max_workers=min(len(jobs), 16), thread_name_prefix="overseer-n-fold") as pool:
        return list(pool.map(one, jobs))


def _waves(assignments: Sequence[tuple[int, Sequence[str]]]) -> list[list[tuple[int, str]]]:
    """Split ``(source, agent ids)`` assignments into waves in which no agent appears twice (one open issue per agent and
    task): wave w holds each agent's w-th assignment, in source order."""
    waves: list[list[tuple[int, str]]] = []
    seen: dict[str, int] = {}
    for k, agents in assignments:
        for a in agents:
            w = seen.get(a, 0)
            seen[a] = w + 1
            while len(waves) <= w:
                waves.append([])
            waves[w].append((k, a))
    return waves


def run_twofold(*, layout: CombinedLayout, view: Any, plan_twofold: Any, runners: Mapping[str, Any], intake: Any, mode: str, task_audit: Any,
                consolidations: Sequence[Any], validate: Any, combine: Any, parallel: bool = True) -> TwofoldReview:
    """Run the N_FOLD review of ``layout`` (module docstring, steps 2 to 5) with the pool plan's ``plan_twofold``
    (``sources``: the agent ids of each source review; ``merged``: of the merged review; ``context_max_bytes``) and the
    ``runners`` by agent id. ``validate(message, temporary_context)`` validates one accepted verdict envelope against the
    full journal; ``combine(assessments)`` combines. The temporary context is discarded before this returns."""
    if len(plan_twofold.sources) != layout.n:
        raise ValueError("the plan's N_FOLD names another number of sources than the combined answer holds")
    informed = mode == "informed"
    source_parts: list[TwofoldPart] = []
    by_source: dict[int, list[Any]] = {}
    source_runs: dict[int, list[Any]] = {p.index: [] for p in layout.sources}
    refused: dict[int, list[tuple[str, str]]] = {p.index: [] for p in layout.sources}
    errors: dict[int, list[tuple[str, str]]] = {p.index: [] for p in layout.sources}
    digests: dict[int, list[str]] = {p.index: [] for p in layout.sources}
    views = {p.index: part_view(view, p.seqs) for p in layout.sources}
    part_msgs = {p.index: {view.by_seq[s].message_id for s in p.seqs if view.by_seq[s].message_id} for p in layout.sources}
    from .intake import IntakeRefused
    # 1. the source reviews: every dossier of a wave issued before any of its agents runs; the wave runs at once
    for wave in _waves([(p.index, list(agents)) for p, agents in zip(layout.sources, plan_twofold.sources)]):
        jobs: list[tuple[Any, dict]] = []
        idx: list[int] = []
        for k, agent_id in wave:
            r = runners[agent_id]
            try:
                d = intake.issue(views[k], agent_id=r.agent_id, lens=r.lens, mode=mode, pack=r.identity, audit=task_audit if informed else None,
                                 consolidations=[c for c in consolidations if _within(c, part_msgs[k])] if informed else (),
                                 review=review_scope("source", layout.n, k))
            except IntakeRefused as exc:
                refused[k].append((r.agent_id, exc.reason))
                continue
            jobs.append((r, d))
            idx.append(k)
            digests[k].append(d["dossier_sha256"])
        for k, (job, (run, err)) in zip(idx, zip(jobs, _run_wave(jobs, intake, parallel=parallel))):
            if err is not None:
                errors[k].append((job[0].agent_id, err))
            elif run is not None:
                source_runs[k].append(run)
    # 2. validation of every source verdict against the full journal and the signed results, in source and agent order
    for p in layout.sources:
        by_source[p.index] = []
        for run in sorted(source_runs[p.index], key=lambda x: x.agent_id):
            if run.status != "submitted" or not run.message_id:
                continue
            accepted = intake.accepted(run.message_id)
            if accepted is not None:
                by_source[p.index].append(validate(accepted.message, None))
        source_parts.append(TwofoldPart(role="source", index=p.index, agent_ids=tuple(plan_twofold.sources[p.index - 1]),
                                        runs=tuple(sorted(source_runs[p.index], key=lambda x: x.agent_id)), assessments=tuple(by_source[p.index]),
                                        combined=combine(by_source[p.index]) if by_source[p.index] else None, refused=tuple(refused[p.index]),
                                        runner_errors=tuple(errors[p.index]), dossier_sha256=tuple(digests[p.index])))
    # 3. the temporary context of what validation accepted, scoped, bounded
    ctx = TemporaryContext.build(layout, by_source, max_bytes=int(plan_twofold.context_max_bytes), mode=mode)
    record = ctx.record
    try:
        merged_part, carried = _merged_review(layout=layout, view=view, plan_twofold=plan_twofold, runners=runners, intake=intake, mode=mode,
                                              task_audit=task_audit, consolidations=consolidations, validate=validate, combine=combine,
                                              parallel=parallel, ctx=ctx)
    finally:
        # 5. the context is discarded after the request, whatever happened in the merged review: nothing of it outlives this
        # review but its record in the signed audit
        ctx.discard()
    return TwofoldReview(layout=layout, sources=tuple(source_parts), merged=merged_part, context_record=record, context_sha256=ctx.digest,
                         context_discarded=ctx.discarded, carried=tuple(carried))


def _merged_review(*, layout: CombinedLayout, view: Any, plan_twofold: Any, runners: Mapping[str, Any], intake: Any, mode: str, task_audit: Any,
                   consolidations: Sequence[Any], validate: Any, combine: Any, parallel: bool, ctx: TemporaryContext) -> tuple[TwofoldPart, list[dict]]:
    """Step 4 of :func:`run_twofold`: the merged review with the temporary context ``ctx``, and the carried faults it confirmed."""
    from .intake import IntakeRefused
    informed = mode == "informed"
    merged_view = part_view(view, layout.merged_seqs)
    merged_msgs = {view.by_seq[s].message_id for s in layout.merged_seqs if view.by_seq[s].message_id}
    jobs = []
    m_refused: list[tuple[str, str]] = []
    m_errors: list[tuple[str, str]] = []
    m_digests: list[str] = []
    for agent_id in plan_twofold.merged:
        r = runners[agent_id]
        try:
            d = intake.issue(merged_view, agent_id=r.agent_id, lens=r.lens, mode=mode, pack=r.identity, audit=task_audit if informed else None,
                             consolidations=[c for c in consolidations if _within(c, merged_msgs)] if informed else (),
                             review=review_scope("merged", layout.n), temporary_context=ctx)
        except IntakeRefused as exc:
            m_refused.append((r.agent_id, exc.reason))
            continue
        jobs.append((r, d))
        m_digests.append(d["dossier_sha256"])
    m_runs = []
    for job, (run, err) in zip(jobs, _run_wave(jobs, intake, parallel=parallel)):
        if err is not None:
            m_errors.append((job[0].agent_id, err))
        elif run is not None:
            m_runs.append(run)
    m_assessments = []
    for run in sorted(m_runs, key=lambda x: x.agent_id):
        if run.status != "submitted" or not run.message_id:
            continue
        accepted = intake.accepted(run.message_id)
        if accepted is not None:
            m_assessments.append(validate(accepted.message, ctx))
    carried = []
    for va in m_assessments:
        for acc in va.accusations:
            if acc.kind == "synthesis_carries_fault" and acc.outcome == "confirmed":
                carried.append({"agent_id": va.agent_id, "claim_ids": list(acc.covered_identifiers.get("claim_ids", []) or acc.identifiers.get("claim_ids", [])),
                                "report_ids": list(acc.covered_identifiers.get("report_ids", []) or acc.identifiers.get("report_ids", []))})
    merged_part = TwofoldPart(role="merged", index=0, agent_ids=tuple(plan_twofold.merged), runs=tuple(sorted(m_runs, key=lambda x: x.agent_id)),
                              assessments=tuple(m_assessments), combined=combine(m_assessments) if m_assessments else None, refused=tuple(m_refused),
                              runner_errors=tuple(m_errors), dossier_sha256=tuple(m_digests))
    return merged_part, carried


def _within(consolidation: Any, messages: set) -> bool:
    """A consolidated response is shown in a part dossier only when every answer it groups or excludes is in the part."""
    mids = set(getattr(consolidation, "request_message_ids", ()) or ())
    for g in getattr(consolidation, "groups", ()) or ():
        mids |= {m.message_id for m in g.members}
    for e in getattr(consolidation, "excluded", ()) or ():
        mids.add(e.message_id)
    answers = mids - set(getattr(consolidation, "request_message_ids", ()) or ())
    return bool(answers) and answers <= messages
