"""Deterministic validation of one label reply (meaning-check design 2.5.4; separate-call design 4.1).

Pure and linear in the reply's length. In order:

1. **Size and stop reason.** A reply over :data:`MAX_REPLY_BYTES` is ``oversized_reply``; a stop for the token cap is
   ``truncated`` (the labeller then splits the chunk).
2. **Strict JSON.** At most one code fence is stripped. Duplicate keys, nesting deeper than :data:`MAX_DEPTH` and non-finite
   numbers make the reply ``malformed`` (the depth is counted in one pass before parsing, so a deep reply never recurses).
3. **Shape** (``schema.json``, enforced by hand). A missing, duplicate or misordered id is ``incomplete``; an unknown key, value
   or category, a span on ``none`` (whose form is ``"spans": []``, as the frozen prompt asks, or no list), a span count of a
   ``gated`` verdict outside 1 to 8, or a quote outside 1 to 300 characters is ``malformed``.
4. **Canaries.** Every positive canary must be ``gated`` with a located span, or the reply fails ``control``. The negative
   canary's verdict is recorded for drift only. Then every canary is removed.
5. **Anchoring** under the reader's visible form (:mod:`.anchor`); offsets are mapped back to the original text. A span that
   cannot be located on own text, or that names an id the request did not hold, makes the reply ``malformed``, unless another
   span of the same reply survives and blocks. Exemptions never count toward that rule, in either direction.
6. **Exemptions** (:mod:`.exempt`), each recorded. A quote that occurs more than once in its sentence is exempt only when every
   occurrence is (at most :data:`MAX_OCCURRENCES` are read; more keep the span); otherwise it is kept at the first occurrence
   that is not exempt.
7. **Only offsets survive**: (segment, start, end, category). The quote stays only in the raw reply.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from .anchor import locate, locate_all, visible_map
from .exempt import decide
from .render import RenderedRequest
from .scope import OwnScope

__all__ = ["Validation", "ValidSpan", "Exempted", "validate_reply", "parse_reply", "CATEGORIES", "MAX_REPLY_BYTES",
           "MAX_DEPTH", "SCHEMA_ID", "TRUNCATED_STOPS"]

SCHEMA_ID = "selfcert-label/1"
MAX_REPLY_BYTES = 32 * 1024
MAX_DEPTH = 6
MAX_SPANS = 8
MAX_QUOTE = 300
#: Occurrences of one quote in its sentence read for exemptions; beyond this the span stays named.
MAX_OCCURRENCES = 8
#: The reader's families plus DIRECTIVE (decision L4).
CATEGORIES = ("CHECK", "OUTCOME", "AGREE", "QUALITY", "SRCEVAL", "CONFIDENCE", "SCORE", "STATUS", "APPROVE", "ASSURE",
              "COMPLY", "FIDELITY", "MARK", "DIRECTIVE")
#: Provider stop reasons that mean the token cap was reached.
TRUNCATED_STOPS = frozenset({"max_tokens", "length", "max_output_tokens", "token_limit"})
_ID_RE = re.compile(r"s[1-9][0-9]{0,5}")


@dataclass(frozen=True)
class ValidSpan:
    segment: int
    start: int
    end: int
    category: str


@dataclass(frozen=True)
class Exempted:
    exemption: str
    segment: int
    start: int
    end: int
    category: str


@dataclass(frozen=True)
class Validation:
    state: str                     # named | none_named | unavailable
    fault: Optional[str]           # None | oversized_reply | truncated | malformed | incomplete | control
    notes: tuple[str, ...]
    spans: tuple[ValidSpan, ...]
    exemptions: tuple[Exempted, ...]
    canary_positive: int
    canary_caught: int
    negative_offered: int
    negative_named: int

    def as_dict(self) -> dict:
        return {"state": self.state, "fault": self.fault, "notes": list(self.notes),
                "spans": [[s.segment, s.start, s.end, s.category] for s in self.spans],
                "exemptions": [[e.exemption, e.segment, e.start, e.end, e.category] for e in self.exemptions],
                "canary": {"positive": self.canary_positive, "caught": self.canary_caught,
                           "negative_offered": self.negative_offered, "negative_named": self.negative_named}}


class _Malformed(ValueError):
    def __init__(self, note: str):
        super().__init__(note)
        self.note = note


def _no_duplicates(pairs: list) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise _Malformed("duplicate-key")
        out[k] = v
    return out


def _reject_constant(_name: str) -> Any:
    raise _Malformed("non-finite")


def _finite_float(s: str) -> float:
    v = float(s)
    if not math.isfinite(v):
        raise _Malformed("non-finite")
    return v


def _int(s: str) -> int:
    if len(s) > 64:
        raise _Malformed("number")
    return int(s)


def _strip_fence(s: str) -> str:
    t = s.strip()
    if not t.startswith("```"):
        return t
    nl = t.find("\n")
    if nl < 0 or t[3:nl].strip().lower() not in ("", "json") or not t.endswith("```") or len(t) < nl + 4:
        raise _Malformed("fence")
    return t[nl + 1:-3].strip()


_DEPTH_TOKENS_RE = re.compile(r'["\\\[\]{}]')


def _depth(s: str) -> int:
    """The deepest nesting of brackets outside strings, in one left-to-right scan that tracks the string state (an escape skips
    the character after it), so the scan is linear in the reply's length whatever the reply holds (attack round 16: a regular
    expression for whole strings rescanned an unterminated string of escaped quotes from every quote, quadratic)."""
    depth = best = 0
    in_string = False
    skip = -1
    for m in _DEPTH_TOKENS_RE.finditer(s):
        i = m.start()
        if i == skip:
            continue
        c = m.group(0)
        if in_string:
            if c == "\\":
                skip = i + 1
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c in "[{":
            depth += 1
            if depth > best:
                best = depth
                if best > MAX_DEPTH:
                    return best
        elif c in "]}":
            depth -= 1
    return best


def parse_reply(raw: Any) -> Any:
    """The reply parsed strictly (step 2), or :class:`_Malformed` raised with its note."""
    if not isinstance(raw, str):
        raise _Malformed("not-text")
    body = _strip_fence(raw)
    if _depth(body) > MAX_DEPTH:
        raise _Malformed("depth")
    try:
        return json.loads(body, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant, parse_float=_finite_float,
                          parse_int=_int)
    except _Malformed:
        raise
    except (ValueError, RecursionError) as e:
        raise _Malformed("not-json") from e


def _shape(obj: Any) -> list[dict]:
    """The verdicts, each checked for shape (step 3, the malformed half)."""
    if not isinstance(obj, dict) or set(obj) != {"schema", "verdicts"}:
        raise _Malformed("shape")
    if obj["schema"] != SCHEMA_ID or not isinstance(obj["verdicts"], list):
        raise _Malformed("shape")
    out = []
    for v in obj["verdicts"]:
        if not isinstance(v, dict) or not set(v) <= {"id", "v", "spans"} or "id" not in v or "v" not in v:
            raise _Malformed("shape")
        if not isinstance(v["id"], str) or not _ID_RE.fullmatch(v["id"]):
            raise _Malformed("unknown-value")
        if v["v"] not in ("none", "gated"):
            raise _Malformed("unknown-value")
        if v["v"] == "none":
            # the frozen prompt's form is ``"spans": []``; an absent list is the same verdict. A span on "none" is malformed.
            if "spans" in v and v["spans"] != []:
                raise _Malformed("span-count")
        else:
            spans = v.get("spans")
            if not isinstance(spans, list) or not 1 <= len(spans) <= MAX_SPANS:
                raise _Malformed("span-count")
            for sp in spans:
                if not isinstance(sp, dict) or set(sp) != {"quote", "category"}:
                    raise _Malformed("shape")
                if not isinstance(sp["quote"], str) or not 1 <= len(sp["quote"]) <= MAX_QUOTE:
                    raise _Malformed("quote-length")
                if sp["category"] not in CATEGORIES:
                    raise _Malformed("unknown-value")
        out.append(v)
    return out


def _unavailable(fault: str, notes, req: RenderedRequest) -> Validation:
    return Validation("unavailable", fault, tuple(notes), (), (), len(req.positive_canary_ids), 0,
                      len(req.negative_canary_ids), 0)


def validate_reply(raw: Any, stop_reason: Optional[str], req: RenderedRequest, scope: OwnScope) -> Validation:
    """Validate the reply ``raw`` to the rendered request ``req`` of ``scope`` (module docstring). Never raises."""
    try:
        return _validate(raw, stop_reason, req, scope)
    except Exception:  # noqa: BLE001 - fail closed: label code that fails is unavailable, never none_named
        return _unavailable("malformed", ("label-failed",), req)


def _validate(raw: Any, stop_reason: Optional[str], req: RenderedRequest, scope: OwnScope) -> Validation:
    if not isinstance(raw, str):
        return _unavailable("malformed", ("not-text",), req)
    if len(raw) > MAX_REPLY_BYTES or len(raw.encode("utf-8", "surrogatepass")) > MAX_REPLY_BYTES:
        return _unavailable("oversized_reply", ("size",), req)
    if isinstance(stop_reason, str) and stop_reason.strip().lower() in TRUNCATED_STOPS:
        return _unavailable("truncated", ("stop",), req)
    try:
        verdicts = _shape(parse_reply(raw))
    except _Malformed as e:
        return _unavailable("malformed", (e.note,), req)

    expected = req.ids
    items = {it.id: it for it in req.items}
    got = [v["id"] for v in verdicts]
    known = [g for g in got if g in items]
    extra_gated = [v for v in verdicts if v["id"] not in items and v["v"] == "gated"]
    extra_none = [v for v in verdicts if v["id"] not in items and v["v"] == "none"]
    if len(set(got)) != len(got):
        return _unavailable("incomplete", ("duplicate-id",), req)
    if set(known) != set(expected):
        return _unavailable("incomplete", ("missing-id",), req)
    if extra_none:
        return _unavailable("incomplete", ("extra-id",), req)
    if known != list(expected):
        return _unavailable("incomplete", ("order",), req)
    by_id = {v["id"]: v for v in verdicts}

    # step 4: canaries
    pos_ids, neg_ids = req.positive_canary_ids, req.negative_canary_ids
    caught = 0
    for cid in pos_ids:
        v = by_id[cid]
        if v["v"] == "gated":
            vm = visible_map(items[cid].text)
            if any(locate(sp["quote"], vm) is not None for sp in v["spans"]):
                caught += 1
    neg_named = 0
    for cid in neg_ids:
        v = by_id[cid]
        if v["v"] == "gated":
            vm = visible_map(items[cid].text)
            if any(locate(sp["quote"], vm) is not None for sp in v["spans"]):
                neg_named += 1
    if caught != len(pos_ids):
        return Validation("unavailable", "control", ("canary-missed",), (), (), len(pos_ids), caught, len(neg_ids), neg_named)

    # steps 5 and 6: anchoring and exemptions, on own text only
    unlocated = len(extra_gated)
    survivors: list = []
    exempted: list = []
    seen = set()
    maps: dict[int, Any] = {}
    segs = scope.segments
    for iid in expected:
        it = items[iid]
        if it.segment is None:
            continue
        v = by_id[iid]
        if v["v"] != "gated":
            continue
        seg = segs[it.segment]
        vm = maps.get(seg.index)
        if vm is None:
            vm = maps[seg.index] = visible_map(seg.text, seg.forbidden)
        prev = segs[seg.index - 1] if seg.index > 0 else None
        nxt = segs[seg.index + 1] if seg.index + 1 < len(segs) else None
        for sp in v["spans"]:
            locs = locate_all(sp["quote"], vm, MAX_OCCURRENCES + 1)
            if not locs:
                unlocated += 1
                continue
            cat = sp["category"]
            # an exemption frees a span only where the claim lies: every occurrence of the quote must be exempt, or the span
            # stays named at the first occurrence that is not (more occurrences than can be read: doubt keeps the span)
            a, b = locs[0]
            ex: Optional[str] = None
            if len(locs) <= MAX_OCCURRENCES:
                for la, lb in locs:
                    e = decide(seg, la, lb, cat, scope, prev=prev, nxt=nxt)
                    if e is None:
                        a, b, ex = la, lb, None
                        break
                    if ex is None:
                        ex = e
            oa, ob = seg.original_span(a, b)
            key = (seg.index, oa, ob, cat)
            if key in seen:
                continue
            seen.add(key)
            if ex is not None:
                exempted.append(Exempted(ex, seg.index, oa, ob, cat))
            else:
                survivors.append(ValidSpan(seg.index, oa, ob, cat))
    notes = ("unlocated",) if unlocated else ()
    if survivors:
        state, fault = "named", None
    elif unlocated:
        state, fault = "unavailable", "malformed"
    else:
        state, fault = "none_named", None
    return Validation(state, fault, notes, tuple(survivors), tuple(exempted), len(pos_ids), caught, len(neg_ids), neg_named)
