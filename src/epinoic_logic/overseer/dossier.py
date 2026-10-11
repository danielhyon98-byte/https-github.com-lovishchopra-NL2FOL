"""The dossier: what an overseer agent reads. One JSON object for one task, issued to one agent under one knowledge pack.

:func:`build_dossier` turns an :class:`~epinoic_logic.overseer.view.OverseerView` (built from the JOURNAL, never from
live objects) into the dossier of design section 9.2:

* **Header.** ``dossier_version``, ``dossier_sha256``, ``verdict_contract``, ``agent_id``, ``pack``, ``mode``, ``lens``
  and ``task``. The agent copies ``verdict_contract`` (as ``contract``), ``pack``, ``agent_id``, ``task.task_id``,
  ``dossier_sha256`` and ``lens`` into its verdict; the intake checks them against its issue record. Two agents never
  receive the same digest, because the header differs; their ``transfers`` and ``results`` are identical in one mode.
* **Transfers**, in sequence order, each with its own pointer ``at`` (``/transfers/<i>``), so the agent never computes a
  pointer from ``seq``. Typed payloads stay JSON objects exactly as journaled, with the contract named beside them; a
  withheld response is ``{"withheld": {"response_sha256", "response_chars"}}``.
* **Results**: every result a receipt cites that the auditor's store retains, with ``signature_present`` and
  ``signature_key_id`` in place of the signature.
* **Links** say where to look (forwards and their deliveries, peer documents and the EARLIER forwards to the same
  recipient, synthesis citations and their deliveries). A link never states that two texts are equal, so blind mode
  does not leak a check's outcome.
* **Index**: every identifier with a ready pointer (a claim entry also names its ``report_id``).
* **Auditor** (informed mode only): the task audit's ``OVS-*`` findings. Blind mode carries no auditor finding and no
  signature-verification outcome; the receipts' own ``INT-*`` findings are part of each transfer in both modes.
* **Limits**: string fields over :data:`TRUNCATE_AT` characters are cut and end with :data:`TRUNCATION_MARKER`; each
  is listed with the digest and length of the full field, so a pointer stays valid and a quote must come from the
  visible part (:func:`visible_text`).

Redaction: the dossier never contains a key or a signature. Every ``signature`` member inside a payload, receipt or
problem is replaced by ``signature_present`` (a boolean); ``signature_key_id`` stays. Nothing the channel journaled
outside the envelope, the receipt, the raw text and the pool (call arguments, channel configuration, key ids of the
channel) is included.

:func:`resolve_pointer` resolves RFC 6901 pointers strictly (no ``-``, no leading zeros); :func:`dossier_digest` is the
sha256 of the canonical dossier without ``dossier_sha256``. The :class:`Dossier` model (every level ``extra="forbid"``)
is the contract a dossier validates against; ``dossier.schema.json`` of the pack is generated from it by the knowledge
stage. Agent text in the dossier is data: this module copies, hashes and cuts it, never interprets it.

Deviations from ``docs/OVERSEER_DESIGN.md`` section 9.2, listed as each stage requires:

* ``build_dossier`` takes ``audit=`` (the task audit whose findings informed mode shows); informed mode without one is
  refused (``ValueError``), never issued with an empty ``auditor`` section that would read as "no findings";
* ``results`` holds only results the store retains: a cited result that is evicted, never stored or of a degraded view
  is absent from ``results`` (its id stays in ``cited_result_ids`` and in the index, pointing at the citation), so the
  agent never sees a receipt's own copy presented as a signed result;
* document ids named only by a claim's ``source_refs`` (no supplied text) are indexed at their first occurrence;
* the index lists every occurrence of a message, receipt, report, claim and document (a forwarded report appears at
  its delivery and at its forward); a synthesis id is not indexed as a report (the design's index types have no
  synthesis type), but it resolves as an identifier because it occurs in the dossier;
* transfers whose journal entries are digest-only carry ``payload: null``; calls that raised before issuing anything
  are not transfers and are not listed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ir.canonical import canonical_json, sha256_hex
from .codes import is_agent_code
from .contracts import OverseerAudit
from .verdicts import (
    DOSSIER_VERSION, HEADER_ID_PATTERN, LENSES, MODES, SHA256_PATTERN, VERDICT_CONTRACT, Lens, Mode, PackIdentity,
)
from .view import OverseerView, Transfer, cited_results

__all__ = [
    "Dossier", "DossierTransfer", "DossierReceipt", "DossierResult", "DossierBinding", "DossierParty", "DossierPoolEntry", "DossierLinks",
    "ForwardLink", "PeerDocumentLink", "SynthesisCitation", "IndexEntry", "IndexType", "DossierAuditor", "DossierLimits", "TruncatedField",
    "DossierTask", "build_dossier", "resolve_pointer", "PointerError", "pointer_escape", "pointer_join", "dossier_digest", "verify_dossier_digest",
    "visible_text", "truncated_pointers", "dossier_identifiers", "dossier_json", "TRUNCATE_AT", "TRUNCATION_MARKER", "RECEIPT_FIELDS",
]

#: String fields longer than this are cut (design section 9.2).
TRUNCATE_AT = 20_000
#: Appended to a cut field; the visible part is the first :data:`TRUNCATE_AT` characters.
TRUNCATION_MARKER = "…[truncated]"
#: The receipt fields a dossier shows (the receipt's identifiers and direction are on the transfer itself).
RECEIPT_FIELDS = ("status", "findings", "coverage", "constraint_results", "outcomes", "structural_findings", "formal_checks", "formal_result_ids", "summary")
_TRUNCATED_SECTIONS = ("task", "transfers", "results", "links", "auditor")

IndexType = Literal["message", "receipt", "report", "claim", "synthesized_claim", "result", "document", "conflict"]
TransferKind = Literal["request", "response", "response_text", "relay_forward", "relay_report", "relay_synthesis"]

_FORBID = ConfigDict(extra="forbid", strict=True)


# ============================================================================================ the contract
class DossierParty(BaseModel):
    model_config = _FORBID
    agent_id: Optional[str] = None
    role: Optional[str] = None


class DossierReceipt(BaseModel):
    """The receipt as issued, minus its identifiers (on the transfer) and with signatures redacted."""
    model_config = _FORBID
    status: Optional[str] = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    constraint_results: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[dict[str, Any]] = Field(default_factory=list)
    structural_findings: list[dict[str, Any]] = Field(default_factory=list)
    formal_checks: list[dict[str, Any]] = Field(default_factory=list)
    formal_result_ids: list[str] = Field(default_factory=list)
    summary: str = ""


class DossierPoolEntry(BaseModel):
    model_config = _FORBID
    claim_id: str
    problem_digest: str
    ambiguous: bool
    agent_id: Optional[str] = None
    report_id: Optional[str] = None


class DossierTransfer(BaseModel):
    """One transfer. ``at`` is its own pointer; ``payload`` is the journaled payload (or the withheld record)."""
    model_config = _FORBID
    at: str = Field(pattern=r"^/transfers/(0|[1-9][0-9]*)$")
    seq: int = Field(ge=1)
    kind: TransferKind
    message_id: Optional[str] = None
    receipt_id: Optional[str] = None
    direction: Optional[str] = None
    sender: DossierParty
    recipient: DossierParty
    contract: Optional[str] = None
    in_reply_to: Optional[str] = None
    created_at: Optional[str] = None
    payload_sha256: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    raw_text: Optional[str] = None
    receipt: Optional[DossierReceipt] = None
    cited_result_ids: list[str] = Field(default_factory=list)
    pool_after: list[DossierPoolEntry] = Field(default_factory=list)


class DossierBinding(BaseModel):
    model_config = _FORBID
    problem_digest: str
    config_digest: str
    versions_digest: str
    binding_digest: str


class DossierResult(BaseModel):
    """A retained engine result: its status and binding, with signature presence only (never the signature)."""
    model_config = _FORBID
    status: str
    claim_id: str
    request_id: str
    problem_id: str
    query: Optional[str] = None
    binding: DossierBinding
    solver_config: dict[str, Any]
    premises_relied_on: list[str] = Field(default_factory=list)
    ungrounded_dependencies: list[str] = Field(default_factory=list)
    signature_present: bool
    signature_key_id: Optional[str] = None
    problem: Optional[dict[str, Any]] = None


class ForwardLink(BaseModel):
    model_config = _FORBID
    forward_message_id: Optional[str] = None
    report_id: Optional[str] = None
    delivering_message_id: Optional[str] = None


class PeerDocumentLink(BaseModel):
    model_config = _FORBID
    request_message_id: Optional[str] = None
    document_id: str
    earlier_forward_message_ids: list[str] = Field(default_factory=list)


class SynthesisCitation(BaseModel):
    model_config = _FORBID
    synthesis_message_id: Optional[str] = None
    report_id: str
    delivering_message_id: Optional[str] = None


class DossierLinks(BaseModel):
    model_config = _FORBID
    forwards: list[ForwardLink] = Field(default_factory=list)
    peer_documents: list[PeerDocumentLink] = Field(default_factory=list)
    synthesis_citations: list[SynthesisCitation] = Field(default_factory=list)


class IndexEntry(BaseModel):
    model_config = _FORBID
    type: IndexType
    id: str
    report_id: Optional[str] = None
    pointer: str


class DossierAuditor(BaseModel):
    model_config = _FORBID
    findings: list[dict[str, Any]] = Field(default_factory=list)


class TruncatedField(BaseModel):
    model_config = _FORBID
    pointer: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    chars: int = Field(ge=0)


class DossierLimits(BaseModel):
    model_config = _FORBID
    truncated_fields: list[TruncatedField] = Field(default_factory=list)


class DossierTask(BaseModel):
    model_config = _FORBID
    task_id: str
    request_id: str
    plan: Optional[dict[str, Any]] = None


class Dossier(BaseModel):
    """Dossier ``1.0``. Validate the JSON object with ``Dossier.model_validate(obj)``; the digest is computed over the
    JSON object itself (:func:`dossier_digest`), never over a re-serialised model."""
    model_config = _FORBID
    dossier_version: Literal["1.0"]
    dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    verdict_contract: Literal["overseer_verdict/1.0"]
    agent_id: str = Field(pattern=HEADER_ID_PATTERN)
    pack: PackIdentity
    mode: Mode
    lens: Lens
    task: DossierTask
    transfers: list[DossierTransfer]
    results: dict[str, DossierResult]
    links: DossierLinks
    index: list[IndexEntry]
    auditor: Optional[DossierAuditor] = None
    limits: DossierLimits

    @model_validator(mode="after")
    def _mode_and_auditor(self) -> "Dossier":
        if (self.mode == "informed") != (self.auditor is not None):
            raise ValueError("the auditor section is present exactly in informed mode")
        for i, t in enumerate(self.transfers):
            if t.at != f"/transfers/{i}":
                raise ValueError(f"transfer {i} carries the pointer {t.at!r}")
        return self


# ============================================================================================ pointers and digests
class PointerError(KeyError):
    """A JSON Pointer that does not resolve in the dossier."""


def pointer_escape(token: Any) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def pointer_join(*tokens: Any) -> str:
    return "".join("/" + pointer_escape(t) for t in tokens)


def _tokens(pointer: str) -> list[str]:
    if not isinstance(pointer, str):
        raise PointerError("a pointer is a string")
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PointerError(f"a pointer starts with '/': {pointer[:80]!r}")
    out = []
    for raw in pointer[1:].split("/"):
        i = 0
        while True:
            i = raw.find("~", i)
            if i < 0:
                break
            if i + 1 >= len(raw) or raw[i + 1] not in "01":
                raise PointerError(f"invalid escape in pointer token {raw[:80]!r}")
            i += 2
        out.append(raw.replace("~1", "/").replace("~0", "~"))
    return out


def resolve_pointer(doc: Any, pointer: str) -> Any:
    """The value at an RFC 6901 pointer. Arrays take a decimal index without leading zeros (``-`` never resolves);
    objects take an existing key. Raises :class:`PointerError` otherwise."""
    node = doc
    for tok in _tokens(pointer):
        if isinstance(node, dict):
            if tok not in node:
                raise PointerError(f"no member {tok[:80]!r} at {pointer[:200]!r}")
            node = node[tok]
        elif isinstance(node, list):
            if not tok.isdigit() or not tok.isascii() or (len(tok) > 1 and tok[0] == "0"):
                raise PointerError(f"array index {tok[:80]!r} is not a decimal index at {pointer[:200]!r}")
            i = int(tok)
            if i >= len(node):
                raise PointerError(f"array index {i} is out of range at {pointer[:200]!r}")
            node = node[i]
        else:
            raise PointerError(f"{pointer[:200]!r} descends into a scalar")
    return node


def dossier_digest(dossier: dict) -> str:
    """sha256 of the canonical dossier without its ``dossier_sha256`` member."""
    return sha256_hex(canonical_json({k: v for k, v in dossier.items() if k != "dossier_sha256"}))


def verify_dossier_digest(dossier: Any) -> bool:
    return isinstance(dossier, dict) and isinstance(dossier.get("dossier_sha256"), str) and dossier["dossier_sha256"] == dossier_digest(dossier)


def dossier_json(dossier: dict) -> str:
    """The dossier as canonical JSON (the form an intake stores and a digest is computed over)."""
    return canonical_json(dossier)


def truncated_pointers(dossier: dict) -> dict[str, dict]:
    """``pointer -> {sha256, chars}`` of every field the dossier cut."""
    out = {}
    for item in ((dossier.get("limits") or {}).get("truncated_fields") or []):
        if isinstance(item, dict) and isinstance(item.get("pointer"), str):
            out[item["pointer"]] = item
    return out


def visible_text(dossier: dict, pointer: str, value: Any) -> str:
    """The text a quote must come from: a string field's visible part (before the truncation marker of a cut field),
    or the canonical JSON of any other value."""
    if isinstance(value, str):
        if pointer in truncated_pointers(dossier) and value.endswith(TRUNCATION_MARKER):
            return value[: len(value) - len(TRUNCATION_MARKER)]
        return value
    return canonical_json(value)


def dossier_identifiers(dossier: dict) -> set[str]:
    """Every string that occurs as a value in the dossier body (task, transfers, results, links, index), plus the keys
    of ``results``: the identifiers an accusation may name (Dossier guide D1)."""
    out: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, str):
            if len(x) <= 256:
                out.add(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for section in ("task", "transfers", "results", "links", "index"):
        walk(dossier.get(section))
    out.update(k for k in (dossier.get("results") or {}) if isinstance(k, str))
    return out


# ============================================================================================ building
def _redact(x: Any) -> Any:
    """A deep copy with every ``signature`` member replaced by ``signature_present``."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k == "signature":
                out["signature_present"] = bool(v)
            else:
                out[k] = _redact(v)
        if "signature_key_id" in out and "signature_present" not in out:
            out["signature_present"] = False
        return out
    if isinstance(x, list):
        return [_redact(v) for v in x]
    return x


def _envelope_field(t: Transfer, name: str) -> Any:
    return (t.envelope or {}).get(name)


def _receipt(t: Transfer) -> Optional[dict]:
    dump = t.receipt_dump
    if not isinstance(dump, dict):
        return None
    out: dict[str, Any] = {}
    for k in RECEIPT_FIELDS:
        default: Any = "" if k == "summary" else ([] if k != "status" else None)
        out[k] = _redact(copy.deepcopy(dump.get(k, default)))
    return out


def _payload(t: Transfer) -> Optional[dict]:
    if t.withheld is not None:
        return {"withheld": {"response_sha256": t.withheld.get("response_sha256"), "response_chars": t.withheld.get("response_chars")}}
    if isinstance(t.payload, dict):
        return _redact(copy.deepcopy(t.payload))
    return None


def _cited(t: Transfer) -> list[str]:
    if t.receipt is None:
        return []
    return list(dict.fromkeys(rid for rid, _k, _p in cited_results(t.receipt)))


def _result_entry(view: OverseerView, rid: str) -> Optional[dict]:
    store = view.store
    if store is None:
        return None
    rec = store.live(rid)
    if rec is None:
        return None
    res = store.parsed(rid)
    if res is None:
        return None
    b = res.binding
    entry: dict[str, Any] = {
        "status": getattr(res.status, "value", res.status), "claim_id": res.claim_id, "request_id": res.request_id, "problem_id": res.problem_id,
        "query": getattr(res.query, "value", res.query),
        "binding": {"problem_digest": b.problem_digest, "config_digest": b.config_digest, "versions_digest": b.versions_digest, "binding_digest": b.binding_digest},
        "solver_config": json.loads(canonical_json(res.solver_config.model_dump(mode="json", exclude_none=True))),
        "premises_relied_on": list(res.premises_relied_on), "ungrounded_dependencies": list(res.ungrounded_dependencies),
        "signature_present": bool(res.signature), "signature_key_id": res.signature_key_id,
    }
    if rec.problem_json:
        try:
            entry["problem"] = _redact(json.loads(rec.problem_json))
        except Exception:
            pass
    return entry


def _plan(view: OverseerView) -> Optional[dict]:
    for t in view.transfers:
        if t.event.plan_json:
            try:
                return json.loads(t.event.plan_json)
            except Exception:
                return None
    plan = view.plan
    return plan.model_dump(mode="json", exclude_none=True) if plan is not None else None


def _links(view: OverseerView) -> dict:
    forwards, peers, cites = [], [], []
    for t in view.transfers:
        if t.kind == "relay_forward":
            d = view.by_seq.get(t.delivering_seq) if t.delivering_seq is not None else None
            forwards.append({"forward_message_id": t.message_id, "report_id": t.report_id, "delivering_message_id": d.message_id if d is not None else None})
        elif t.kind == "request" and t.request is not None:
            for doc in t.request.supplied_texts:
                if not doc.document_id.startswith("peer:"):
                    continue
                earlier = [f.message_id for f in view.transfers
                           if f.kind == "relay_forward" and f.seq < t.seq and f.message_id and f.recipient_agent_id == t.request.to_agent_id]
                peers.append({"request_message_id": t.message_id, "document_id": doc.document_id, "earlier_forward_message_ids": earlier})
        elif t.kind == "relay_synthesis" and t.synthesis is not None:
            for rid in t.synthesis.source_report_ids:
                seq = t.cited_delivery_seqs.get(rid)
                d = view.by_seq.get(seq) if seq is not None else None
                cites.append({"synthesis_message_id": t.message_id, "report_id": rid, "delivering_message_id": d.message_id if d is not None else None})
    return {"forwards": forwards, "peer_documents": peers, "synthesis_citations": cites}


def _index(transfers: list[dict], results: dict[str, dict]) -> list[dict]:
    entries: list[dict] = []
    seen: set[tuple] = set()
    supplied: set[str] = set()
    sourced: list[tuple[str, str]] = []

    def add(kind: str, ident: Any, pointer: str, report_id: Optional[str] = None) -> None:
        if not isinstance(ident, str) or not ident:
            return
        key = (kind, ident, report_id, pointer)
        if key in seen:
            return
        seen.add(key)
        e = {"type": kind, "id": ident, "pointer": pointer}
        if report_id is not None:
            e["report_id"] = report_id
        entries.append(e)

    for tr in transfers:
        at = tr["at"]
        add("message", tr.get("message_id"), at)
        if tr.get("receipt_id"):
            add("receipt", tr["receipt_id"], at + "/receipt" if tr.get("receipt") is not None else at)
        p = tr.get("payload")
        if not isinstance(p, dict):
            continue
        for j, doc in enumerate(p.get("supplied_texts") or []):
            if isinstance(doc, dict) and isinstance(doc.get("document_id"), str):
                add("document", doc["document_id"], f"{at}/payload/supplied_texts/{j}")
                supplied.add(doc["document_id"])
        if tr["kind"] == "relay_synthesis":
            sid = p.get("synthesis_id") if isinstance(p.get("synthesis_id"), str) else None
            for j, c in enumerate(p.get("claims") or []):
                if isinstance(c, dict):
                    add("synthesized_claim", c.get("claim_id"), f"{at}/payload/claims/{j}", report_id=sid)
            for j, c in enumerate(p.get("conflicts") or []):
                if isinstance(c, dict):
                    add("conflict", c.get("conflict_id"), f"{at}/payload/conflicts/{j}")
            continue
        rid = p.get("report_id") if isinstance(p.get("report_id"), str) else None
        if rid is not None and "withheld" not in p:
            add("report", rid, f"{at}/payload")
        for j, c in enumerate(p.get("claims") or []):
            if not isinstance(c, dict):
                continue
            add("claim", c.get("claim_id"), f"{at}/payload/claims/{j}", report_id=rid)
            for k, ref in enumerate(c.get("source_refs") or []):
                if isinstance(ref, dict) and isinstance(ref.get("document_id"), str):
                    sourced.append((ref["document_id"], f"{at}/payload/claims/{j}/source_refs/{k}/document_id"))
    for doc_id, pointer in sourced:
        if doc_id not in supplied:
            supplied.add(doc_id)
            add("document", doc_id, pointer)
    for rid in results:
        add("result", rid, pointer_join("results", rid))
    absent: set[str] = set()
    for tr in transfers:  # a cited result the store does not retain: its first citation
        for j, rid in enumerate(tr.get("cited_result_ids") or []):
            if rid not in results and rid not in absent:
                absent.add(rid)
                add("result", rid, f"{tr['at']}/cited_result_ids/{j}")
    return entries


def _truncate(dossier: dict) -> list[dict]:
    cut: list[dict] = []

    def walk(x: Any, pointer: str) -> Any:
        if isinstance(x, str):
            if len(x) > TRUNCATE_AT:
                cut.append({"pointer": pointer, "sha256": hashlib.sha256(x.encode("utf-8", errors="surrogatepass")).hexdigest(), "chars": len(x)})
                return x[:TRUNCATE_AT] + TRUNCATION_MARKER
            return x
        if isinstance(x, dict):
            return {k: walk(v, pointer + "/" + pointer_escape(k)) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v, f"{pointer}/{i}") for i, v in enumerate(x)]
        return x

    for section in _TRUNCATED_SECTIONS:
        if section in dossier:
            dossier[section] = walk(dossier[section], "/" + section)
    return cut


def build_dossier(view: OverseerView, *, mode: str, lens: str, agent_id: str, pack: PackIdentity, audit: Optional[OverseerAudit] = None) -> dict:
    """The dossier of ``view`` for one agent under one pack, as a JSON object (validated against :class:`Dossier`).

    ``mode`` is ``blind`` (no auditor finding) or ``informed`` (the ``OVS-*`` findings of ``audit``, which is then
    required). The view must be built from a journal: a degraded view has no reference copy and is refused."""
    if mode not in MODES:
        raise ValueError(f"unknown dossier mode {mode!r}")
    if lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r}")
    if not isinstance(pack, PackIdentity):
        raise TypeError("pack must be a PackIdentity")
    if view.degraded:
        raise ValueError("a dossier is built only from a journaled view; a degraded view has no reference copy")
    if mode == "informed" and audit is None:
        raise ValueError("informed mode needs the task audit whose findings the dossier shows")
    if audit is not None and audit.channel_uid != view.channel_uid:
        raise ValueError("the audit belongs to another channel than the view")
    transfers: list[dict] = []
    results: dict[str, dict] = {}
    for i, t in enumerate(view.transfers):
        tr: dict[str, Any] = {
            "at": f"/transfers/{i}", "seq": t.seq, "kind": t.kind, "message_id": t.message_id, "receipt_id": t.receipt_id,
            "direction": (t.receipt_dump or {}).get("direction") if isinstance(t.receipt_dump, dict) else None,
            "sender": {"agent_id": _envelope_field(t, "sender_agent_id"), "role": _envelope_field(t, "sender_role")},
            "recipient": {"agent_id": _envelope_field(t, "recipient_agent_id"), "role": _envelope_field(t, "recipient_role")},
            "contract": t.contract, "in_reply_to": t.in_reply_to, "created_at": _envelope_field(t, "created_at"),
            "payload_sha256": t.event.payload_sha256, "payload": _payload(t),
        }
        if t.raw_text is not None:
            tr["raw_text"] = t.raw_text
        tr["receipt"] = _receipt(t)
        tr["cited_result_ids"] = _cited(t)
        tr["pool_after"] = [e.to_dict() for e in t.pool_after]
        transfers.append(tr)
        for rid in tr["cited_result_ids"]:
            if rid not in results:
                entry = _result_entry(view, rid)
                if entry is not None:
                    results[rid] = entry
    plan = _plan(view)
    task_id = (plan or {}).get("task_id") or view.task_id or ""
    request_id = (plan or {}).get("request_id") or view.request_id or ""
    dossier: dict[str, Any] = {
        "dossier_version": DOSSIER_VERSION, "dossier_sha256": "", "verdict_contract": VERDICT_CONTRACT, "agent_id": agent_id,
        "pack": pack.model_dump(mode="json"), "mode": mode, "lens": lens,
        "task": {"task_id": task_id, "request_id": request_id, "plan": plan},
        "transfers": transfers, "results": results, "links": _links(view), "index": _index(transfers, results),
    }
    if mode == "informed":
        dossier["auditor"] = {"findings": [f.model_dump(mode="json", exclude_none=True) for f in audit.report.findings if not is_agent_code(f.code)]}
    dossier["limits"] = {"truncated_fields": _truncate(dossier)}
    dossier = json.loads(canonical_json(dossier))  # plain JSON values only (no tuples, no model objects)
    dossier["dossier_sha256"] = dossier_digest(dossier)
    Dossier.model_validate(dossier)
    return dossier
