"""T24 (meaning-check design 3.3): the invariant every receipt and delivery receipt must keep, whatever the label said.

:func:`check_t24` reads one produced record and returns its violations (an empty tuple when it keeps the invariant):

1. **No label-derived text contains a success word.** A string is label-derived when it carries a label marker (an
   ``INT-SELF-`` code, the meaning label's rules and words, the label version or record schema, ``KIT-DL-014``, ``OVS-FID-010``,
   a ``label_json`` or ``selfcert_label`` field) or lies under a ``selfcert_label`` member. The success words are the
   repository's forgery vocabulary (:data:`epinoic_logic.named.FORGERY_WORDS`) and the pass words of the label (``clean``,
   ``approved``, ``none named`` ...): a label never speaks for an answer, and ``none_named`` is never shown as a pass.
2. **No label field reaches a Problem.** No IR problem inside the record carries a label marker.
3. **No status is raised.** A transmission receipt that carries a label finding is never ``ACCEPTED``; a claim named by
   INT-SELF-001, or displayed with ``withheld_self_report``, never shows a success status (ENTAILED, CONSISTENT, SATISFIABLE); a
   delivery candidate the label withholds is never deliverable and never delivered; a ``selfcert_label`` member holds states,
   places, kinds, families and counts only, never words.
4. **A delivered payload equals the specialist's bytes.** A delivered answer's payload digest is its payload's, the digest of the
   specialist's journaled payload when the caller knows it, and the digest its delivery receipt names when the caller gives it;
   no payload carries a label record or a label field.

A channel event is read for the payload rule only: its journaled envelope and receipt never carry the label record (the record
itself lives in ``label_json`` beside them, never inside).

The test suite applies it to every receipt, delivery receipt, delivered answer and channel event it produces, through one
session-level hook in ``tests/conftest.py``; a test that builds a violating record on purpose carries the marker
:data:`T24_EXPECTED_VIOLATION` and asserts that this function detects it. Pure and read-only; it never raises on odd input (an
unreadable record is itself a violation).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator, Optional

__all__ = ["check_t24", "T24_EXPECTED_VIOLATION", "LABEL_MARKERS", "T24_SUCCESS_WORDS"]

#: The pytest marker of a test that builds a violating record on purpose (and asserts that :func:`check_t24` detects it).
T24_EXPECTED_VIOLATION = "t24_expected_violation"

#: Substrings that make a string label-derived (ASCII, so they survive JSON escaping).
LABEL_MARKERS = ("INT-SELF-", "meaning label", "meaning-label", "Meaning label", "selfcert_label", "selfcert-label", "KIT-DL-014",
                 "OVS-FID-010", "label_json", "labelled_text", "withheld_self_report")
_SUCCESS_DISPLAY = frozenset({"ENTAILED", "CONSISTENT", "SATISFIABLE"})
_WITHHOLDING_STATES = frozenset({"named", "unavailable", "skipped"})
_STATES = frozenset({"named", "none_named", "unavailable", "skipped"})
_PLACE = re.compile(r"(?:paragraph \d+, sentence \d+(?:, part \d+)?|the paragraph before)")
#: Identifiers a member may hold beside its states and places: receipt codes, digests and the label's version and schemas.
_TOKEN = re.compile(r"(?:[A-Z]{2,7}-[A-Z]{2,10}-\d{3}|[0-9a-f]{16,64}|selfcert-label-\d+|selfcert-label(?:-record)?/\d+)")


def _member_words() -> frozenset:
    """The closed set of words a ``selfcert_label`` member may hold: the states, the unavailable kinds, the label's categories
    and the reader's families, the writers and the label's rule names."""
    from .fakes import FAMILY_CATEGORY
    from .record import GATE_RULE, KINDS, UNAVAILABLE_RULE
    from .validate import CATEGORIES
    return frozenset(_STATES | set(KINDS) | set(CATEGORIES) | set(FAMILY_CATEGORY) | {"specialist", "combinator", GATE_RULE,
                                                                                       UNAVAILABLE_RULE, "reader-refused"})


def _member_token(v: str) -> bool:
    return v in _member_words() or bool(_PLACE.fullmatch(v) or _TOKEN.fullmatch(v))
_WORD = re.compile(r"[a-z]+(?:_[a-z]+)*")


def _success_words() -> tuple[str, ...]:
    """The repository's forgery vocabulary and the label's own pass words. This is a vocabulary for what the PACKAGE writes
    (a finding, a reason, a member), never a reader of an answer: the one reader of the self-certification class stays
    ``epinoic_logic.selfcert`` (tests/selfcert/test_one_reader.py), so the words are kept here, not as a module-level set."""
    label_pass_words = ("pass", "passes", "clean", "approved", "accepted", "confirmed", "certified", "cleared", "ok", "okay",
                        "successful", "succeeded", "none_named", "none named", "nothing named", "no self-certification")
    try:
        from ..named import FORGERY_WORDS
        base = tuple(FORGERY_WORDS)
    except Exception:  # noqa: BLE001 - the vocabulary as it stands in named.py
        base = ("valid", "sound", "correct", "passed", "proves", "proven", "success", "verified", "verifies", "permitted",
                "entailed", "none found", "argument diagnosis", "release")
    return tuple(dict.fromkeys(base + label_pass_words))


T24_SUCCESS_WORDS = _success_words()
_SINGLE = frozenset(w for w in T24_SUCCESS_WORDS if " " not in w)
_PHRASES = tuple(w for w in T24_SUCCESS_WORDS if " " in w)


def _success_in(text: str) -> list[str]:
    low = text.casefold()
    found = [w for w in _WORD.findall(low) if w in _SINGLE]
    found += [p for p in _PHRASES if re.search(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])", low)]
    return list(dict.fromkeys(found))


def _marked(text: str) -> bool:
    return any(m in text for m in LABEL_MARKERS)


def _as_data(obj: Any) -> Any:
    """The record as plain JSON values (a pydantic model, a dataclass with ``to_dict``, a mapping or a JSON string)."""
    if isinstance(obj, (dict, list)):
        return obj
    if isinstance(obj, str):
        return json.loads(obj)
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"not a record: {type(obj).__name__}")


def _walk(data: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    stack = [(path, data)]
    while stack:
        p, v = stack.pop()
        yield p, v
        if isinstance(v, dict):
            stack.extend((p + (k,), x) for k, x in v.items())
        elif isinstance(v, list):
            stack.extend((p + (i,), x) for i, x in enumerate(v))


def _kind(data: Any) -> str:
    if not isinstance(data, dict):
        return "other"
    contract = data.get("contract")
    if contract == "delivery_receipt/1.0" or (isinstance(contract, str) and contract.startswith("delivery_receipt/")):
        return "delivery"
    if isinstance(contract, str) and contract.startswith("delivered_answer/"):
        return "delivered_answer"
    if "receipt_id" in data and "direction" in data and "findings" in data:
        return "transmission"
    if "channel_uid" in data and "seq" in data and "envelope_json" in data:
        return "event"
    return "other"


def _is_problem(v: Any) -> bool:
    return isinstance(v, dict) and "ir_version" in v and "problem_id" in v and "query" in v


def _member_violations(member: Any, where: str) -> list[str]:
    """A ``selfcert_label`` member (delivery-v2): states, places, kinds, families, codes, digests and counts only, never words."""
    out: list[str] = []
    for p, v in _walk(member):
        if isinstance(v, str):
            if not _member_token(v):
                out.append(f"{where}: the selfcert_label member carries words, not a state, place, kind or count "
                           f"(at {'/'.join(map(str, p)) or 'the member'})")
        elif not isinstance(v, (dict, list, int, float, bool)) and v is not None:
            out.append(f"{where}: the selfcert_label member holds a value that is not JSON data")
    return out


def check_t24(receipt: Any, *, specialist_payload_sha256: Optional[Any] = None,
              delivery_receipt: Any = None) -> tuple[str, ...]:
    """The T24 violations of one receipt, delivery receipt, delivered answer or channel event (module docstring); an empty
    tuple when it keeps the invariant. ``specialist_payload_sha256`` (a digest, or a collection of digests) is the digest of the
    specialist's journaled payload of a delivered answer's message, when the caller knows it; ``delivery_receipt`` the receipt
    a delivered answer names."""
    try:
        if hasattr(receipt, "envelope_json") and hasattr(receipt, "channel_uid") and not isinstance(receipt, dict):
            # a channel event: only its journaled envelope and receipt are read (the payload rule)
            return _event({"envelope_json": getattr(receipt, "envelope_json", None),
                           "receipt_json": getattr(receipt, "receipt_json", None)})
        dump_json = getattr(receipt, "model_dump_json", None)
        if callable(dump_json) and not isinstance(receipt, dict):
            # the fast path: a record with no label marker anywhere holds nothing a label could have changed (only a delivered
            # answer is read further, for its payload)
            if not _marked(dump_json()) and not str(getattr(receipt, "contract", "")).startswith("delivered_answer/"):
                return ()
        data = _as_data(receipt)
        blob = json.dumps(data, ensure_ascii=True, sort_keys=True, default=str)
    except Exception as e:  # noqa: BLE001 - an unreadable record is itself a violation
        return (f"T24: the record could not be read ({type(e).__name__})",)
    kind = _kind(data)
    out: list[str] = []
    if kind == "delivered_answer":
        out += _delivered_answer(data, specialist_payload_sha256, delivery_receipt)
    if kind == "event":
        return _event(data)
    if not _marked(blob):
        return tuple(out)  # no label-derived content anywhere: nothing a label could have changed
    # 1. label-derived text carries no success word; 2. no label marker inside a Problem; member shape
    for p, v in _walk(data):
        if _is_problem(v):
            pj = json.dumps(v, ensure_ascii=True, sort_keys=True, default=str)
            if _marked(pj):
                out.append(f"{kind}: a label field or label text reached a Problem (at {'/'.join(map(str, p))})")
        if isinstance(v, dict) and "selfcert_label" in v:
            out += _member_violations(v["selfcert_label"], kind)
        if isinstance(v, str):
            in_member = "selfcert_label" in p
            if in_member and _member_token(v) and (v not in _SINGLE or (p and p[-1] == "state" and v in _STATES)):
                continue  # a state (data of a signed receipt, under its own key), place, kind, family or code
            if in_member or _marked(v):
                words = _success_in(v)
                if words:
                    out.append(f"{kind}: label-derived text carries a success word {words} (at {'/'.join(map(str, p))})")
    # 3. no status raised
    if kind == "transmission":
        out += _transmission(data)
    elif kind == "delivery":
        out += _delivery(data)
    if kind == "delivered_answer" and _marked(json.dumps(data.get("payload"), ensure_ascii=True, default=str)):
        out.append("delivered_answer: a label field or label text reached the delivered payload")
    return tuple(dict.fromkeys(out))


def _event(data: dict) -> tuple[str, ...]:
    out = []
    for name in ("envelope_json", "receipt_json"):
        v = data.get(name)
        if isinstance(v, str) and ("selfcert-label-record/" in v or '"label_json"' in v or '"labelled_text' in v):
            out.append(f"event: the label record reached the journaled {name.split('_')[0]} (it belongs in label_json only)")
    return tuple(out)


def _transmission(data: dict) -> list[str]:
    out: list[str] = []
    findings = [f for f in data.get("findings") or [] if isinstance(f, dict)]
    label = [f for f in findings if isinstance(f.get("code"), str) and f["code"].startswith("INT-SELF-")]
    if label and data.get("status") == "ACCEPTED":
        out.append("transmission: a receipt with a label finding is shown ACCEPTED (its status was raised above its findings)")
    named_claims = {c for f in label if f.get("code") == "INT-SELF-001" for c in (f.get("claim_ids") or [])}
    for o in data.get("outcomes") or []:
        if not isinstance(o, dict):
            continue
        shown = o.get("display_status")
        if shown in _SUCCESS_DISPLAY and (o.get("claim_id") in named_claims or o.get("withheld_self_report") is True):
            out.append(f"transmission: claim {o.get('claim_id')} named by the label shows the success status {shown}")
    return out


def _delivery(data: dict) -> list[str]:
    out: list[str] = []
    fallback = data.get("fallback") if isinstance(data.get("fallback"), dict) else {}
    delivered = data.get("delivered_message_id") if data.get("delivered") else None
    for c in fallback.get("candidates") or []:
        if not isinstance(c, dict):
            continue
        member = c.get("selfcert_label")
        state = member.get("state") if isinstance(member, dict) else None
        reasons = [r for r in c.get("integrity_reasons") or [] if isinstance(r, str)]
        withheld = state in _WITHHOLDING_STATES or any(("INT-SELF-" in r or "meaning-label" in r or "meaning label" in r
                                                        or "OVS-FID-010" in r or "KIT-DL-014" in r) for r in reasons)
        if not withheld:
            continue
        if c.get("deliverable") is True:
            out.append(f"delivery: candidate {c.get('message_id')} withheld by the label is shown deliverable")
        if delivered is not None and c.get("message_id") == delivered:
            out.append(f"delivery: candidate {c.get('message_id')} withheld by the label was delivered")
    return out


def _delivered_answer(data: dict, specialist: Any, rec: Any) -> list[str]:
    out: list[str] = []
    payload = data.get("payload")
    digest = data.get("payload_sha256")
    try:
        from ..integrity.contracts import payload_hash
        actual = payload_hash(payload) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        actual = None
    if actual is None or actual != digest:
        out.append("delivered_answer: the delivered payload is not the payload its digest names")
    if specialist is not None:
        known = {specialist} if isinstance(specialist, str) else set(specialist)
        if known and digest not in known:
            out.append("delivered_answer: the delivered payload differs from the specialist's journaled bytes")
    if rec is not None:
        try:
            rd = _as_data(rec)
        except Exception:  # noqa: BLE001
            rd = None
        if not isinstance(rd, dict) or rd.get("delivered_payload_sha256") != digest:
            out.append("delivered_answer: the delivered payload is not the one its delivery receipt names")
    return out
