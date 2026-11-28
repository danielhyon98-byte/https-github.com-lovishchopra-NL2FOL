"""Fakes for tests and offline runs (meaning-check design 3.4). Never for production: the preflight refuses them outside
development and ``sim`` (stage 2), and they are never used to MEASURE the label (that would measure the reader).

* :class:`ReaderBackedLabeller`, the faithful fake: it answers the real rendered request with a schema-valid reply that names
  every canary and every span the rule reader hits, verbatim, with the category mapped from the reader's family. The union of
  the reader and this label therefore equals the reader, and existing tests keep their meaning.
* :class:`ScriptedLabeller`: replies scripted by a test, with helpers to build them from the rendered request.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable, Optional, Sequence, Union

from .. import selfcert
from .anchor import locate, visible_map
from .labellers import CallFailure, CallingLabeller, Reply, model_digest
from .render import RenderedRequest
from .validate import SCHEMA_ID

__all__ = ["ReaderBackedLabeller", "ScriptedLabeller", "reader_backed_reply", "reply_json", "canary_spans", "id_of",
           "FAMILY_CATEGORY", "TEST_KEY"]

#: The fixed canary key of the test suite (never a deployment secret).
TEST_KEY = b"selfcert-label fixed test key (tests only)"
#: The reader's families as label categories (DEFECT: a denial of a fault is an outcome claim; PROVENANCE: how it was checked).
FAMILY_CATEGORY = {"CHECK": "CHECK", "OUTCOME": "OUTCOME", "AGREE": "AGREE", "QUALITY": "QUALITY", "SRCEVAL": "SRCEVAL",
                   "CONFIDENCE": "CONFIDENCE", "SCORE": "SCORE", "STATUS": "STATUS", "APPROVE": "APPROVE", "ASSURE": "ASSURE",
                   "COMPLY": "COMPLY", "FIDELITY": "FIDELITY", "MARK": "MARK", "DEFECT": "OUTCOME", "PROVENANCE": "CHECK",
                   "DIRECTIVE": "DIRECTIVE"}
_FORBIDDEN_RE = re.compile(r"⟦[^⟦⟧]{0,40}⟧|[‹›〚〛]+")


def _blocks(user_text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lines = user_text.split("\n")
    for k, line in enumerate(lines):
        if line.startswith("<<<DATA ") and k + 1 < len(lines):
            name = line[len("<<<DATA "):].split(" ", 1)[0]
            out[name] = json.loads(lines[k + 1])
    return out


def _forbidden(text: str) -> tuple[tuple[int, int], ...]:
    return tuple((m.start(), m.end()) for m in _FORBIDDEN_RE.finditer(text))


def _quote_for(text: str, a: int, b: int) -> Optional[str]:
    """A verbatim quote of ``text[a:b]`` that does not touch a placeholder or substitute and is located in ``text``."""
    forb = _forbidden(text)
    vm = visible_map(text, forb)
    frags: list[tuple[int, int]] = []
    pos = a
    for fa, fb in forb:
        if fb <= a or fa >= b:
            continue
        if fa > pos:
            frags.append((pos, fa))
        pos = max(pos, fb)
    if pos < b:
        frags.append((pos, b))
    frags.sort(key=lambda f: f[1] - f[0], reverse=True)
    for fa, fb in frags:
        q = text[fa:fb].strip()[:300].strip()
        if q and locate(q, vm) is not None:
            return q
    for fa, fb in [(0, len(text))]:
        q = text[fa:fb].strip()[:300].strip()
        if q and not forb and locate(q, vm) is not None:
            return q
    return None


def _add(gated: dict, iid: str, quote: Optional[str], cat: str) -> None:
    if quote is None:
        return
    spans = gated.setdefault(iid, [])
    if (quote, cat) not in spans and len(spans) < 8:
        spans.append((quote, cat))


def _rendered_range(seg, a: int, b: int) -> Optional[tuple[int, int]]:
    """The rendered offsets of ``seg`` whose original characters overlap the original span ``[a, b)`` (None when none do)."""
    first = last = None
    for i, (oa, ob) in enumerate(seg.origin):
        if oa < b and ob > a:
            if first is None:
                first = i
            last = i
    return None if first is None else (first, last + 1)


def reader_backed_reply(req: RenderedRequest) -> str:
    """The faithful fake's reply to ``req`` (module docstring). The answer is read as the rule reader reads it: its whole raw
    text, line breaks and paragraphs kept, in the reader's context of the request (``req.scope``), and each hit is mapped back
    to the ids of this request by its original offsets. Reading the rendered sentences joined by spaces instead lost the line
    structure: a tick at the end of a marking line ("Model: ... 15 m/s ✔") or a tick-bullet list line read as a MARK verdict
    the reader does not refuse (check round of stage 2a). Each canary is read alone, as it is rendered."""
    scope = req.scope
    blocks = None
    if scope is not None:
        ctx = scope.ctx
    else:  # a request rendered without its scope (none is, in this package): its context block, read as the reader would
        blocks = _blocks(req.user_text)
        cblock = blocks.get("context") or {}
        ctx = selfcert.Context(writer=cblock.get("writer") or "specialist", marking=bool(cblock.get("marking")),
                               known_sources=tuple(cblock.get("known_sources") or ()),
                               truth_item=bool(cblock.get("truth_item")))
    gated: dict[str, list[tuple[str, str]]] = {}
    for it in req.items:
        if it.segment is None:  # a canary: an ordinary paragraph of one sentence
            for h in selfcert.read(it.text, ctx).hits:
                _add(gated, it.id, _quote_for(it.text, h.start, h.end), FAMILY_CATEGORY.get(h.family, "CHECK"))
    if scope is not None:
        mine = [(it.id, scope.segments[it.segment]) for it in req.items if it.segment is not None]
        for h in selfcert.read(scope.raw_text, ctx).hits:
            cat = FAMILY_CATEGORY.get(h.family, "CHECK")
            for iid, seg in mine:
                if seg.end <= h.start or seg.start >= h.end:
                    continue
                rng = _rendered_range(seg, h.start, h.end)
                if rng is not None:
                    _add(gated, iid, _quote_for(seg.text, rng[0], rng[1]), cat)
        return reply_json(req, gated, canaries=False)
    canary_ids = {it.id for it in req.items if it.segment is None}
    for para in (blocks.get("answer") or {}).get("paragraphs", []):
        sentences = [s for s in (para.get("sentences") or []) if s.get("id") not in canary_ids]
        if not sentences:
            continue
        joined = ""
        starts = []
        for s in sentences:
            if joined:
                joined += "\n"  # one unit per line: the rendering cut the paragraph at its lines and sentences
            starts.append(len(joined))
            joined += s["text"]
        for h in selfcert.read(joined, ctx).hits:
            cat = FAMILY_CATEGORY.get(h.family, "CHECK")
            for s, st in zip(sentences, starts):
                a, b = max(h.start, st), min(h.end, st + len(s["text"]))
                if a < b:
                    _add(gated, s["id"], _quote_for(s["text"], a - st, b - st), cat)
    return reply_json(req, gated, canaries=False)


def reply_json(req: RenderedRequest, gated: Optional[dict] = None, *, canaries: bool = True, drop: Iterable[str] = (),
               extra: Sequence[dict] = (), order: Optional[Sequence[str]] = None) -> str:
    """A reply to ``req``: every id ``none`` except those in ``gated`` (id -> [(quote, category)]); with ``canaries`` every
    positive canary is gated with its own text; ``drop`` leaves ids out; ``extra`` appends raw verdicts."""
    gated = dict(gated or {})
    if canaries:
        for cid, spans in canary_spans(req).items():
            gated.setdefault(cid, spans)
    dropped = set(drop)
    verdicts = []
    for iid in (order or req.ids):
        if iid in dropped:
            continue
        spans = gated.get(iid)
        if spans:
            verdicts.append({"id": iid, "v": "gated", "spans": [{"quote": q, "category": c} for q, c in spans]})
        else:
            verdicts.append({"id": iid, "v": "none", "spans": []})  # the frozen prompt's reply form
    verdicts.extend(extra)
    return json.dumps({"schema": SCHEMA_ID, "verdicts": verdicts}, ensure_ascii=False)


def canary_spans(req: RenderedRequest) -> dict[str, list[tuple[str, str]]]:
    """Each positive canary id of ``req`` with a span quoting it whole."""
    return {it.id: [(it.text, "CHECK")] for it in req.items if it.canary is not None and it.canary.positive}


def id_of(req: RenderedRequest, segment: int) -> str:
    for it in req.items:
        if it.segment == segment:
            return it.id
    raise KeyError(segment)


class ReaderBackedLabeller(CallingLabeller):
    """The faithful fake (module docstring). Its reply is a function of the rendered request alone, so every instance with the
    same canary key shares calls and cached successes (the shared submission of the labellers module)."""

    def __init__(self, *, key: bytes = TEST_KEY, clock=None, prompt_path=None):
        super().__init__(lambda req, timeout: Reply(reader_backed_reply(req), "end_turn"), key=key,
                         model_digest=model_digest("fake:reader-backed"), clock=clock, prompt_path=prompt_path)

    @property
    def share_scope(self) -> object:
        return ("reader-backed",)


Script = Union[Callable[[RenderedRequest, int], Any], Sequence[Any]]


class ScriptedLabeller(CallingLabeller):
    """Replies scripted by a test: ``script`` is a callable ``(request, call number) -> str | Reply`` (it may raise
    :class:`CallFailure` or ``TimeoutError``), or a sequence of such values (an exception instance is raised). ``requests``
    keeps every rendered request it was asked."""

    def __init__(self, script: Script, *, key: bytes = TEST_KEY, clock=None, prompt_path=None):
        self.requests: list[RenderedRequest] = []
        self._script = script

        def caller(req: RenderedRequest, timeout: float) -> Reply:
            n = len(self.requests)
            self.requests.append(req)
            if callable(self._script):
                out = self._script(req, n)
            else:
                if n >= len(self._script):
                    raise CallFailure("provider-error", "script-exhausted")
                out = self._script[n]
            if isinstance(out, BaseException):
                raise out
            if isinstance(out, Reply):
                return out
            return Reply(str(out), "end_turn")
        super().__init__(caller, key=key, model_digest=model_digest("fake:scripted"), clock=clock, prompt_path=prompt_path)
