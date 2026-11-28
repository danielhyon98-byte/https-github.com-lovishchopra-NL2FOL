"""The meaning label's gate at release (meaning-check design 2.3, 2.5.6 and 2.5.7; stage 2a, interface (c)).

Every release path of the overseer reads one journaled label record in one way, AFTER its existing reads (the receipt's
self-report codes, the task audit's, and the rule reader on the payload as written):

* :func:`label_gate` reads the record a channel event carries (``ChannelEvent.label_json``) for exactly the text it labelled
  (``ChannelEvent.labelled_text``, whose SHA-256 the event records beside it), re-validates it with the labeller's own canary key
  and model digest (``Labeller.revalidate_record``; the labeller given, else the translator's default labeller looked up at the
  moment of the call), and returns a :class:`LabelReading`: ``named`` (the places and families of every sentence the validated
  label names), ``skipped`` (the rule reader already refuses the text, and its refusal reproduces now) or ``none_named``. It
  raises :class:`LabelUnavailable` on a missing record, a record or text that is not the journaled one, a record that does not
  re-validate, a record whose state is ``unavailable``, and a ``skipped`` record whose reader refusal does not reproduce (a
  ``skipped`` record is re-validated too when a labeller is configured; the unconfigured default re-validates nothing, and the
  reader's refusal, re-read at the gate, then decides alone: the text is refused either way). Any
  failure of the gate itself is :class:`LabelUnavailable` too: a failure always withholds, never reads as ``none_named``.
* A ``named`` or ``skipped`` reading refuses exactly as a reader hit does (rule ``self-certification-gate``, refusal
  ``not_deliverable``); :class:`LabelUnavailable` refuses as an outage (rule ``meaning-label-unavailable``, refusal
  ``selfcert_label_unavailable``, KIT-DL-014, no revision request). ``none_named`` allows nothing by itself: every other rule
  decides as before, and it is never shown to anyone as a pass.
* :func:`receipt_label` reads the label's receipt codes (INT-SELF-001, INT-SELF-002) beside the record, and :func:`label_refusal`
  combines both into the one refusal a path gives, with its reason named by place, family, state and kind, never by a word of the
  answer (and never by a word the label quoted).

Trust rule T17 (pack 2.3, ``01-role-and-trust.md``): the label is the one agent output that may act without a deterministic check,
and only to withhold. Nothing here releases, selects, labels, raises a status or changes an accuracy upward; the label never
reaches the IR, the compiler or the engine. Reached through the translator's public API only (``epinoic_logic.api.label``,
``epinoic_logic.api.adapters`` and ``epinoic_logic.api.ir``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "LabelUnavailable", "LabelReading", "label_gate", "receipt_label", "label_refusal", "label_member", "LABEL_RECEIPT_CODES",
    "NAMED_CODE", "UNAVAILABLE_CODE", "LABEL_AUDIT_CODE", "GATE_RULE", "UNAVAILABLE_RULE", "UNAVAILABLE_REASONS", "LABELLED_KINDS",
    "named_claim_ids", "labeller_of", "LabelRefusal",
]

#: The receipt code of a sentence the meaning label names (the channel's; warning, ``deterministic=False``).
NAMED_CODE = "INT-SELF-001"
#: The receipt code of an answer the meaning label could not read (the channel's; warning; its message gives the kind).
UNAVAILABLE_CODE = "INT-SELF-002"
#: Both, as the release paths read them on a receipt (any severity).
LABEL_RECEIPT_CODES: frozenset = frozenset({NAMED_CODE, UNAVAILABLE_CODE})
#: The auditor's code for a missing or non-revalidating record (error; ``checks/label.py``).
LABEL_AUDIT_CODE = "OVS-FID-010"
#: The rule a named (or reader-refused) label refuses under, as a reader hit does.
GATE_RULE = "self-certification-gate"
#: The rule an unavailable label refuses under (an outage, never a fault of the answer).
UNAVAILABLE_RULE = "meaning-label-unavailable"
#: Why a record gives no usable label at the gate (:class:`LabelUnavailable.reason`): a closed list of tokens.
UNAVAILABLE_REASONS = ("missing", "text-mismatch", "record-mismatch", "unreadable", "unavailable", "revalidation",
                       "skipped-not-reproduced", "gate-failed")
#: The transfer kinds whose events carry a label record (an answer, a relayed or forwarded report, a synthesis).
LABELLED_KINDS = ("response", "response_text", "relay_report", "relay_forward", "relay_synthesis")
#: The unavailable kinds a record may name (the label package's closed list; anything else reads as ``unknown``).
_RECORD_KINDS = ("not-configured", "provider-error", "timeout", "budget", "malformed", "incomplete", "control", "oversized", "truncated",
                 "label-failed", "not-recorded")
_KIND_RE = re.compile(r"\(([a-z][a-z-]{1,30});")
_PLACE_RE = re.compile(r"^(?:paragraph \d{1,6}, sentence \d{1,6}(?:, part \d{1,4})?|the paragraph before)$")
_FAMILY_RE = re.compile(r"^[A-Z]{2,12}$")
_MAX_PLACES = 64


class LabelUnavailable(Exception):
    """No usable meaning label for the text a release path would hand on: the answer is withheld as an outage (rule
    ``meaning-label-unavailable``). ``reason`` is one of :data:`UNAVAILABLE_REASONS`; ``kind`` is the record's own unavailable kind
    when its state is ``unavailable`` (one of the label package's kinds, else ``unknown``); ``mismatches`` names the fields of a
    record that does not re-validate. No word of the answer is ever carried."""

    def __init__(self, reason: str, *, kind: Optional[str] = None, mismatches: Sequence[str] = ()):
        self.reason = reason if reason in UNAVAILABLE_REASONS else "gate-failed"
        self.kind = kind
        self.mismatches = tuple(str(m) for m in mismatches if isinstance(m, str) and re.fullmatch(r"[a-z_-]{1,40}", m))[:12]
        super().__init__(self.describe())

    def describe(self) -> str:
        """The reason as a token, with the record's kind: ``unavailable: not-configured``, ``missing``, ``revalidation``."""
        if self.reason == "unavailable":
            return f"unavailable: {self.kind or 'unknown'}"
        return self.reason


@dataclass(frozen=True)
class LabelReading:
    """What a usable label record says of one text: ``state`` (``named``, ``skipped`` or ``none_named``), the places it names and
    the families at each place (``named`` only), and the writer it was read for. ``blocks``: a named or reader-refused text."""
    state: str
    places: tuple[str, ...] = ()
    families: tuple[tuple[str, ...], ...] = ()
    writer: str = "specialist"

    @property
    def blocks(self) -> bool:
        return self.state in ("named", "skipped")

    def where(self) -> str:
        """``paragraph 2, sentence 1, OUTCOME; ...`` (places and families only), at most eight places."""
        parts = [f"{p}, {'/'.join(f)}" if f else p for p, f in zip(self.places, self.families or ((),) * len(self.places))]
        shown = "; ".join(parts[:8])
        return shown + (f"; and {len(parts) - 8} more" if len(parts) > 8 else "")


def labeller_of(*given: Any) -> Any:
    """The first labeller given (an explicit argument, then the hub's or the channel's configured ``selfcert_labeller``), or None:
    the gate then asks the translator's default labeller at the moment of the call."""
    for lab in given:
        if lab is not None:
            return lab
    return None


def _sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _labeller(labeller: Any) -> Any:
    """The labeller given, else the translator's default labeller looked up NOW (interface (a): never bound at import)."""
    if labeller is not None:
        return labeller
    from epinoic_logic.api.label import default_labeller
    return default_labeller()


def _off(labeller: Any) -> bool:
    """Whether ``labeller`` is the unconfigured kind (``health() == 'off'``): it makes no label and re-validates none."""
    try:
        return labeller.health() == "off"
    except Exception:  # noqa: BLE001 - a labeller that cannot say is treated as configured (its re-validation decides)
        return False


def label_gate(event: Any, request: Any = None, *, labeller: Any = None) -> LabelReading:
    """The meaning label of the text ``event`` carries (module docstring). ``request`` is the router's record the label was read
    against; None reads the one journaled with the record (``ChannelEvent.label_request_json``). A record that re-validates only
    against another request is a mismatch. Raises :class:`LabelUnavailable`; never returns a reading for a record it could not
    re-validate."""
    try:
        record_json = getattr(event, "label_json", None)
        if not isinstance(record_json, str) or not record_json:
            raise LabelUnavailable("missing")
        recorded_digest = getattr(event, "label_sha256", None)
        if not isinstance(recorded_digest, str):
            # interface (c): the record is read only beside its digest; an event that carries a record with no digest is a record
            # the gate cannot bind (check round of stage 2a: an absent digest skipped this check)
            raise LabelUnavailable("missing")
        from epinoic_logic.api.ir import sha256_hex
        if recorded_digest != sha256_hex(record_json):
            raise LabelUnavailable("record-mismatch")
        from epinoic_logic.api.label import labelled_text
        text = labelled_text(event)
        if text is None:
            raise LabelUnavailable("text-mismatch" if isinstance(getattr(event, "labelled_text", None), str) else "missing")
        try:
            record = json.loads(record_json)
        except ValueError:
            raise LabelUnavailable("unreadable") from None
        if not isinstance(record, dict):
            raise LabelUnavailable("unreadable")
        state, writer = record.get("state"), record.get("writer")
        if writer not in ("specialist", "combinator"):
            raise LabelUnavailable("unreadable")
        if state == "unavailable":
            kind = record.get("kind")
            raise LabelUnavailable("unavailable", kind=kind if kind in _RECORD_KINDS else "unknown")
        if state not in ("named", "none_named", "skipped"):
            raise LabelUnavailable("unreadable")
        if request is None:
            rj = getattr(event, "label_request_json", None)
            if isinstance(rj, str) and rj:
                try:
                    request = json.loads(rj)
                except ValueError:
                    raise LabelUnavailable("unreadable") from None
        if state == "skipped":
            # the reader's refusal must reproduce now, on the same text, with the context of the same router's record
            from epinoic_logic.api.adapters import selfcert_context_for, selfcert_read
            if not selfcert_read(text, selfcert_context_for(request, writer=writer)).refuses():
                raise LabelUnavailable("skipped-not-reproduced")
        lab = _labeller(labeller)
        if state == "skipped" and _off(lab):
            # no labeller is configured (the production default re-validates nothing): the record says only that the rule reader
            # refuses the text, and that refusal was just re-read here; the text is refused by the reader whatever the record holds
            return LabelReading("skipped", writer=writer)
        rv = lab.revalidate_record(record, text, request)
        if not getattr(rv, "ok", False):
            raise LabelUnavailable("revalidation", mismatches=getattr(rv, "mismatches", ()) or ())
        if state == "skipped":
            return LabelReading("skipped", writer=writer)
        result = getattr(rv, "result", None)
        if result is None or getattr(result, "state", None) != state:
            raise LabelUnavailable("revalidation", mismatches=("state",))
        if state == "none_named":
            return LabelReading("none_named", writer=writer)
        places: list[str] = []
        families: dict[str, list[str]] = {}
        for sp in getattr(result, "spans", ()) or ():
            place, family = str(getattr(sp, "place", "")), str(getattr(sp, "family", ""))
            if not _PLACE_RE.match(place):
                place = "a sentence"
            if place not in families:
                if len(places) >= _MAX_PLACES:
                    continue
                places.append(place)
                families[place] = []
            if _FAMILY_RE.match(family) and family not in families[place]:
                families[place].append(family)
        if not places:
            raise LabelUnavailable("revalidation", mismatches=("spans",))  # a named record that names no place reads as no label
        return LabelReading("named", tuple(places), tuple(tuple(families[p]) for p in places), writer)
    except LabelUnavailable:
        raise
    except Exception:  # noqa: BLE001 - the gate that fails withholds (never none_named)
        raise LabelUnavailable("gate-failed") from None


def receipt_label(receipt: Any) -> tuple[Optional[str], tuple[str, ...]]:
    """``(state, unavailable kinds)`` of the label's codes on a transmission receipt (any severity): ``named`` for INT-SELF-001,
    ``unavailable`` for INT-SELF-002 (its kinds read from the message against the label package's closed list), None when the
    receipt carries neither. Reads a receipt object or its dump; never raises (an unreadable receipt reads as carrying none:
    the record decides)."""
    try:
        findings = list(getattr(receipt, "findings", None) or (receipt.get("findings") if isinstance(receipt, Mapping) else None) or [])
    except Exception:  # noqa: BLE001
        return None, ()
    named = unavailable = False
    kinds: list[str] = []
    for f in findings:
        code = f.get("code") if isinstance(f, Mapping) else getattr(f, "code", None)
        if code == UNAVAILABLE_CODE:
            unavailable = True
            msg = str((f.get("message") if isinstance(f, Mapping) else getattr(f, "message", "")) or "")
            m = _KIND_RE.search(msg)
            kinds.append(m.group(1) if m and m.group(1) in _RECORD_KINDS else "unknown")
        elif code == NAMED_CODE:
            named = True
    if named:
        return "named", tuple(dict.fromkeys(kinds))
    if unavailable:
        return "unavailable", tuple(dict.fromkeys(kinds))
    return None, ()


def named_claim_ids(receipt: Any) -> frozenset[str]:
    """The claim ids the label names on a transmission receipt (the INT-SELF-001 findings' ``claim_ids``): the claims whose success
    display is withheld (interface (d)) and that never count in an accuracy."""
    out: set[str] = set()
    try:
        for f in getattr(receipt, "findings", None) or ():
            if getattr(f, "code", None) == NAMED_CODE:
                out.update(str(c) for c in (getattr(f, "claim_ids", None) or ()))
    except Exception:  # noqa: BLE001
        return frozenset(out)
    return frozenset(out)


@dataclass(frozen=True)
class LabelRefusal:
    """The one label refusal a release path gives: ``kind`` ``named`` (rule self-certification-gate, ``not_deliverable``) or
    ``unavailable`` (rule meaning-label-unavailable, ``selfcert_label_unavailable``), what it is named by (places and families, or
    the unavailable reason and kind), and the reading or the exception behind it."""
    kind: str
    detail: str
    reading: Optional[LabelReading] = None
    unavailable: Optional[LabelUnavailable] = None

    @property
    def skipped(self) -> bool:
        """The record says the rule reader refuses the text (no label was asked): refused as the reader's own refusal."""
        return self.reading is not None and self.reading.state == "skipped"


def label_refusal(event: Any, receipt: Any = None, request: Any = None, *, labeller: Any = None) -> Optional[LabelRefusal]:
    """The label's refusal of the text ``event`` carries, or None (a usable ``none_named`` record and no label code on its receipt):

    * the record gives no usable label (:class:`LabelUnavailable`): ``unavailable``, named by its reason and kind;
    * the record names sentences: ``named``, by place and family; a ``skipped`` record (the reader refuses the text): ``named``, as
      the reader's refusal;
    * the receipt names a sentence (INT-SELF-001) that the record does not: ``named``; the receipt says the label could not read the
      answer (INT-SELF-002): ``unavailable``, by its kinds.

    Never raises: a failure here is ``unavailable`` (``gate-failed``)."""
    try:
        try:
            reading = label_gate(event, request, labeller=labeller)
        except LabelUnavailable as exc:
            return LabelRefusal("unavailable", exc.describe() + (f" ({', '.join(exc.mismatches)})" if exc.mismatches else ""), unavailable=exc)
        if reading.state == "named":
            return LabelRefusal("named", reading.where(), reading=reading)
        if reading.state == "skipped":
            return LabelRefusal("named", "label state skipped", reading=reading)
        state, kinds = receipt_label(receipt) if receipt is not None else (None, ())
        if state == "named":
            return LabelRefusal("named", f"named on its receipt ({NAMED_CODE})", reading=reading)
        if state == "unavailable":
            return LabelRefusal("unavailable", f"{UNAVAILABLE_CODE} on its receipt: {', '.join(kinds) or 'unknown'}", reading=reading)
        return None
    except Exception:  # noqa: BLE001 - fail closed
        exc = LabelUnavailable("gate-failed")
        return LabelRefusal("unavailable", exc.describe(), unavailable=exc)


def label_member(refusal: Optional[LabelRefusal], audit_codes: Sequence[str] = ()) -> dict:
    """The additive ``selfcert_label`` member of a delivery candidate (delivery-v2): its state, the places and families a named
    label gives, the record's unavailable kind and the code that names an unusable record, and counts. States, places, kinds,
    families, codes and counts only: never a word of the answer, never the label's output, never a success word (``none_named``
    is a state, and no reason or label cites it)."""
    if refusal is None:
        return {"state": "none_named", "counts": {"places": 0}}
    if refusal.kind == "named":
        r = refusal.reading
        if r is not None and r.state == "skipped":
            return {"state": "skipped", "rule": GATE_RULE, "counts": {"places": 0}}
        places = [p for p in (r.places if r is not None else ()) if _PLACE_RE.match(p)]
        fams = sorted({f for fs in (r.families if r is not None else ()) for f in fs if _FAMILY_RE.match(f)})
        out = {"state": "named", "rule": GATE_RULE, "places": places, "families": fams, "counts": {"places": len(places)}}
        if not places:
            out["code"] = NAMED_CODE
        return out
    exc = refusal.unavailable
    out: dict = {"state": "unavailable", "rule": UNAVAILABLE_RULE, "counts": {"places": 0}}
    if exc is not None and exc.reason == "unavailable":
        out["kind"] = exc.kind if exc.kind in _RECORD_KINDS else "label-failed"
        out["code"] = UNAVAILABLE_CODE
    elif exc is not None:
        out["code"] = LABEL_AUDIT_CODE
    else:
        out["code"] = UNAVAILABLE_CODE
    if LABEL_AUDIT_CODE in audit_codes:
        out["audit_code"] = LABEL_AUDIT_CODE
    return out
