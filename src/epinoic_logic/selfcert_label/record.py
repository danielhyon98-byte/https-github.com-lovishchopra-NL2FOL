"""What a label result produces, and the required record (meaning-check design 2.5.6).

=================  =========================================================================================================
state              meaning
=================  =========================================================================================================
``named``          at least one span survived validation: INT-SELF-001 per sentence (place and family, never words); withheld
``none_named``     a valid label named nothing: no finding, and it allows nothing by itself (it is never shown as a pass)
``unavailable``    no valid label (``kind``: one of :data:`KINDS`): INT-SELF-002 with its kind; withheld, as an outage
``skipped``        the rule reader already refuses the answer, so no label was asked (the reader's own codes stand)
=================  =========================================================================================================

The record is ``{input key, label version and digest, model digest, raw reply, validated spans as offsets and category,
exemptions applied, canary outcome, state, attempts}``. Only offsets, categories and places survive validation; the quote
stays only inside the raw reply of the record, and no label text reaches a finding, a reason, a receipt message, a log or a
payload. Every record carries a ``seal``, the SHA-256 of the rest of it. :func:`revalidate` recomputes the validated result
from the stored raw replies (deterministically, no model), checks the seal, the writer and, when it is given, the configured
model's digest, and reports every field that does not match. Any failure of any kind is ``unavailable``, never ``none_named``.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .render import LABEL_VERSION, RenderError
from .validate import Validation, validate_reply

__all__ = ["STATES", "KINDS", "FINDING_STATES", "RECORD_SCHEMA", "LabelSpan", "LabelResult", "Revalidation",
           "result_from_attempts", "unavailable_result", "skipped_result", "revalidate", "FAULT_KIND", "NO_CALL_KINDS"]

RECORD_SCHEMA = "selfcert-label-record/1"
STATES = ("named", "none_named", "unavailable", "skipped")
KINDS = ("not-configured", "provider-error", "timeout", "budget", "malformed", "incomplete", "control", "oversized", "truncated",
         "label-failed", "not-recorded")
#: The states that give a receipt finding: a named self-certification, and a label that could not be had. The receipt codes
#: themselves are the caller's (``LabelResult.findings(codes)``): the channel names them where the overseer's code tables
#: register them (meaning-check design 3.1, owners R4 and R6), so this package names no receipt code of its own and a code
#: the translator names is never unknown to the overseer.
FINDING_STATES = ("named", "unavailable")
GATE_RULE = "self-certification-gate"
UNAVAILABLE_RULE = "meaning-label-unavailable"
#: A validation fault, as the unavailable kind it gives.
FAULT_KIND = {"oversized_reply": "oversized", "truncated": "truncated", "malformed": "malformed", "incomplete": "incomplete",
              "control": "control"}
#: Failures where no reply was had (an earlier reply's fault, if any, names the outcome instead).
NO_CALL_KINDS = frozenset({"not-configured", "budget", "not-recorded"})
#: The shape of a receipt code (family, area, three digits).
_CODE = re.compile(r"[A-Z]{2,7}-[A-Z]{2,10}-\d{3}")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()


@dataclass(frozen=True)
class LabelSpan:
    place: str
    family: str
    start: int
    end: int


@dataclass(frozen=True)
class LabelResult:
    state: str
    kind: Optional[str]
    spans: tuple[LabelSpan, ...]
    record: dict
    writer: str = "specialist"

    @property
    def withholds(self) -> bool:
        """Every state but ``none_named`` withholds the answer (``skipped``: the reader already refuses it)."""
        return self.state != "none_named"

    def findings(self, codes: Mapping[str, str]) -> list[dict]:
        """The receipt findings, with the caller's receipt code for each state of :data:`FINDING_STATES` (``codes``; the
        design's INT-SELF-001 and INT-SELF-002): one per named sentence, or one with its kind; places and families only.
        ``none_named`` and ``skipped`` give none. A missing or non-code entry for a state that gives a finding raises
        ``ValueError``: a finding is never made without its code, and never dropped for want of one."""
        what = "synthesis" if self.writer == "combinator" else "answer"
        code = None
        if self.state in FINDING_STATES:
            code = codes.get(self.state) if isinstance(codes, Mapping) else None
            if not (isinstance(code, str) and _CODE.fullmatch(code)):
                raise ValueError(f"no receipt code for the label state {self.state}")
        if self.state == "named":
            order: list[str] = []
            fams: dict[str, list[str]] = {}
            for sp in self.spans:
                if sp.place not in fams:
                    order.append(sp.place)
                    fams[sp.place] = []
                if sp.family not in fams[sp.place]:
                    fams[sp.place].append(sp.family)
            out = []
            for place in order:
                f = fams[place]
                fam = f"family {f[0]}" if len(f) == 1 else "families " + ", ".join(f)
                out.append({"code": code, "severity": "warning", "deterministic": False, "place": place,
                            "family": f[0], "families": list(f), "rule": GATE_RULE,
                            "message": f"{place} of the {what}: the meaning label names a self-certification ({fam}; label "
                                       f"{LABEL_VERSION}): never delivered (rule {GATE_RULE})"})
            return out
        if self.state == "unavailable":
            return [{"code": code, "severity": "warning", "deterministic": False, "kind": self.kind,
                     "rule": UNAVAILABLE_RULE,
                     "message": f"the {what} could not be read by the meaning label ({self.kind}; label {LABEL_VERSION}): "
                                f"withheld (rule {UNAVAILABLE_RULE})"}]
        return []


def seal_of(record: dict) -> str:
    """The SHA-256 of the record's canonical JSON without its ``seal`` (every field and every leaf of every attempt: the model
    digest, the writer, each stop reason and detail). It detects any change made to a stored record by anyone who does not
    recompute it; a deliberate forgery needs the journal's signature or chain (stage 2)."""
    body = {k: v for k, v in record.items() if k != "seal"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("ascii")).hexdigest()


def _sealed(record: dict) -> dict:
    record["seal"] = seal_of(record)
    return record


def _base_record(input_key: str, label_digest: str, model_digest: str, writer: str) -> dict:
    return {"record": RECORD_SCHEMA, "input_key": input_key, "label_version": LABEL_VERSION, "label_digest": label_digest,
            "model_digest": model_digest, "writer": writer}


def _chunk_outcome(attempts: list[dict]) -> tuple[str, Optional[str], list[dict]]:
    """(state, kind, final validations) of one chunk from its attempts in order."""
    if not attempts:
        return "unavailable", "label-failed", []
    last_attempt = max(a["attempt"] for a in attempts)
    final = [a for a in attempts if a["attempt"] == last_attempt]
    earlier = [a for a in attempts if a["attempt"] < last_attempt]

    def kind_of(a: dict) -> Optional[str]:
        if a.get("call_fault"):
            return a["call_fault"]
        v = a.get("validation") or {}
        return FAULT_KIND.get(v.get("fault")) if v.get("state") == "unavailable" else None

    states = []
    for a in final:
        v = a.get("validation")
        if v is None or a.get("call_fault"):
            k = kind_of(a) or "label-failed"
            if k in NO_CALL_KINDS or k == "provider-error" and a.get("detail") == "circuit-open":
                prior = [kind_of(e) for e in earlier if kind_of(e) and not e.get("call_fault")]
                if prior:
                    k = prior[-1]
            return "unavailable", k, []
        if v["state"] == "unavailable":
            return "unavailable", FAULT_KIND.get(v.get("fault"), "malformed"), []
        states.append(v)
    parts = [a.get("part") for a in final]
    if parts != [None] and sorted(p for p in parts if p is not None) != [0, 1]:
        return "unavailable", "label-failed", []  # a split chunk needs both halves
    state = "named" if any(v["state"] == "named" for v in states) else "none_named"
    return state, None, states


def _aggregate(attempts: list[dict], chunks: int, scope) -> tuple[str, Optional[str], list, list, dict]:
    by_chunk: dict[int, list[dict]] = {}
    for a in attempts:
        by_chunk.setdefault(a["chunk"], []).append(a)
    spans: list = []
    exemptions: list = []
    canary = {"positive": 0, "caught": 0, "negative_offered": 0, "negative_named": 0}
    named = False
    first_kind: Optional[str] = None
    for c in range(chunks):
        st, kind, finals = _chunk_outcome(by_chunk.get(c, []))
        for v in finals:
            spans.extend(v["spans"])
            exemptions.extend(v["exemptions"])
            for k in canary:
                canary[k] += v["canary"][k]
        if st == "named":
            named = True
        elif st == "unavailable" and first_kind is None:
            first_kind = kind
    if named:
        return "named", None, spans, exemptions, canary
    if first_kind is not None:
        return "unavailable", first_kind, [], exemptions, canary
    return "none_named", None, [], exemptions, canary


def result_from_attempts(inp, attempts: list[dict], *, label_digest: str, model_digest: str) -> LabelResult:
    """The result and record of one answer from its attempts (each with its stored validation)."""
    scope = inp.scope
    state, kind, spans, exemptions, canary = _aggregate(attempts, len(inp.chunks), scope)
    segs = scope.segments
    label_spans = tuple(sorted({LabelSpan(segs[s].place, cat, a, b) for s, a, b, cat in spans}, key=lambda x: (x.start, x.end)))
    rec = _base_record(inp.input_key, label_digest, model_digest, scope.writer)
    rec.update({
        "state": state, "kind": kind,
        "spans": [{"start": s.start, "end": s.end, "category": s.family, "place": s.place} for s in label_spans],
        "exemptions": [{"exemption": e, "start": a, "end": b, "category": cat, "place": segs[s].place}
                       for e, s, a, b, cat in exemptions],
        "canary": canary,
        "attempts": attempts,
    })
    return LabelResult(state, kind, label_spans, _sealed(rec), scope.writer)


def unavailable_result(input_key: str, kind: str, *, writer: str, label_digest: str, model_digest: str,
                       attempts: Optional[list] = None) -> LabelResult:
    if kind not in KINDS:
        kind = "label-failed"
    rec = _base_record(input_key, label_digest, model_digest, writer)
    rec.update({"state": "unavailable", "kind": kind, "spans": [], "exemptions": [],
                "canary": {"positive": 0, "caught": 0, "negative_offered": 0, "negative_named": 0}, "attempts": list(attempts or [])})
    return LabelResult("unavailable", kind, (), _sealed(rec), writer)


def skipped_result(input_key: str, *, writer: str, label_digest: str, model_digest: str, reason: str = "reader-refused") -> LabelResult:
    rec = _base_record(input_key, label_digest, model_digest, writer)
    rec.update({"state": "skipped", "kind": None, "reason": reason, "spans": [], "exemptions": [],
                "canary": {"positive": 0, "caught": 0, "negative_offered": 0, "negative_named": 0}, "attempts": []})
    return LabelResult("skipped", None, (), _sealed(rec), writer)


def attempt_entry(req, *, raw: Optional[str] = None, stop_reason: Optional[str] = None, call_fault: Optional[str] = None,
                  detail: Optional[str] = None, validation: Optional[Validation] = None, chunk: int, attempt: int,
                  part: Optional[int] = None, diagnostic: tuple = ()) -> dict:
    """One attempt of the record: what was asked (its request key), what came back (the raw reply and its digest, or the
    call's failure kind) and its validation (offsets and categories only)."""
    return {"chunk": chunk, "part": part, "attempt": attempt, "diagnostic": list(diagnostic),
            "request_key": req.request_key if req is not None else None,
            "raw_reply": raw, "raw_sha256": _sha(raw) if isinstance(raw, str) else None,
            "stop_reason": stop_reason if isinstance(stop_reason, str) else None,
            "call_fault": call_fault, "detail": detail,
            "validation": validation.as_dict() if validation is not None else None}


@dataclass(frozen=True)
class Revalidation:
    ok: bool
    mismatches: tuple[str, ...]
    result: Optional[LabelResult]


def revalidate(record: Any, raw_text: str, request: Any = None, *, key: bytes, label_digest: Optional[str] = None,
               model_digest: Optional[str] = None, prompt_path=None) -> Revalidation:
    """Recompute the validated result of ``record`` from its stored raw replies and compare every field. A record that does not
    re-validate is reported with the fields that differ (the auditor's OVS-FID-010 in stage 2); it is never read as clean.

    ``model_digest`` is the configured model's digest the record must name (the accepted (label digest, model digest) pair of
    design 2.5.9); stage 2's auditor always passes it. The record's ``seal`` must match its content, so a change to any field
    (the model digest, the writer, a stop reason, a detail) is reported even where the recomputation would not see it, and a
    writer outside ``specialist`` and ``combinator`` is reported (attack round 16)."""
    from . import label_digest as current_digest
    from .inputs import build_input
    mismatches: list[str] = []
    try:
        if not isinstance(record, dict) or record.get("record") != RECORD_SCHEMA:
            return Revalidation(False, ("record",), None)
        if record.get("seal") != seal_of(record):
            mismatches.append("seal")
        if model_digest is not None and record.get("model_digest") != model_digest:
            mismatches.append("model_digest")
        writer = record.get("writer")
        if writer not in ("specialist", "combinator"):
            return Revalidation(False, tuple(dict.fromkeys(mismatches + ["writer"])), None)
        inp = build_input(raw_text, request, key=key, writer=writer, prompt_path=prompt_path)
        if record.get("input_key") != inp.input_key:
            mismatches.append("input_key")
        if record.get("label_version") != LABEL_VERSION:
            mismatches.append("label_version")
        digest = label_digest if label_digest is not None else current_digest()
        if record.get("label_digest") != digest:
            mismatches.append("label_digest")
        state = record.get("state")
        if state == "skipped":
            from .. import selfcert
            if not selfcert.read(raw_text, inp.scope.ctx).refuses():
                mismatches.append("state")
            mm = tuple(dict.fromkeys(mismatches))
            return Revalidation(not mm, mm, None)
        attempts = record.get("attempts")
        if not isinstance(attempts, list):
            return Revalidation(False, tuple(mismatches + ["attempts"]), None)
        if inp.oversized:
            ok = state == "unavailable" and record.get("kind") == "oversized" and not attempts
            mm = tuple(dict.fromkeys(mismatches + ([] if ok else ["state"])))
            return Revalidation(not mm, mm, None)
        recomputed: list[dict] = []
        for a in attempts:
            if not isinstance(a, dict) or not isinstance(a.get("chunk"), int) or not isinstance(a.get("attempt"), int):
                return Revalidation(False, tuple(mismatches + ["attempts"]), None)
            if not 0 <= a["chunk"] < len(inp.chunks) or a["attempt"] not in (0, 1) or a.get("part") not in (None, 0, 1):
                return Revalidation(False, tuple(mismatches + ["attempts"]), None)
            raw = a.get("raw_reply")
            try:
                req = inp.render(a["chunk"], attempt=a["attempt"], part=a.get("part"), diagnostic=tuple(a.get("diagnostic") or ()))
            except RenderError:
                return Revalidation(False, tuple(mismatches + ["render"]), None)
            if a.get("request_key") is not None and a.get("request_key") != req.request_key:
                mismatches.append("request_key")
            if raw is None:
                if not a.get("call_fault") or a["call_fault"] not in KINDS:
                    mismatches.append("attempts")
                recomputed.append(dict(a))
                continue
            if a.get("raw_sha256") != _sha(raw):
                mismatches.append("raw_sha256")
            v = validate_reply(raw, a.get("stop_reason"), req, inp.scope)
            if a.get("validation") != v.as_dict():
                mismatches.append("validation")
            recomputed.append(dict(a, validation=v.as_dict()))
        # a retry follows only a failure, and only one retry per chunk
        for c in {a["chunk"] for a in recomputed}:
            ch = [a for a in recomputed if a["chunk"] == c]
            first = [a for a in ch if a["attempt"] == 0]
            if len(first) != 1:
                mismatches.append("attempts")
                continue
            f = first[0]
            if len(ch) > 1 and not (f.get("call_fault") or (f.get("validation") or {}).get("state") == "unavailable"):
                mismatches.append("attempts")
        result = result_from_attempts(inp, recomputed, label_digest=record.get("label_digest", ""),
                                      model_digest=record.get("model_digest", ""))
        for name in ("state", "kind", "spans", "exemptions", "canary"):
            if record.get(name) != result.record.get(name):
                mismatches.append(name)
        mm = tuple(dict.fromkeys(mismatches))
        return Revalidation(not mm, mm, result)
    except Exception:  # noqa: BLE001 - a record that cannot be re-validated does not re-validate
        return Revalidation(False, tuple(dict.fromkeys(mismatches + ["revalidation-failed"])), None)
