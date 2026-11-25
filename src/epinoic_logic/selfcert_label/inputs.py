"""``build_input``: one function renders the label request of an answer (meaning-check design 2.5.2 and 2.4 CC 2.2(3)).

The service's step 4 and the hub both call :func:`build_input` with the same raw text and the same router request, so both
render byte-identical requests and the second call hits the first's cache entry. The input key binds everything the rendering
depends on except the canary key: the label version, the writer, the context block, the raw text, and digests of the task text,
the supplied texts and the request's command terms (the placeholders and the exemptions read them).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Optional

from .canaries import key_fingerprint
from .render import LABEL_VERSION, RenderError, RenderedRequest, render_request
from .scope import Chunk, OwnScope, _supplied_bodies, _task_text, own_scope

__all__ = ["LabelInput", "build_input", "input_key"]


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()


def input_key(scope: OwnScope, request: Any) -> str:
    """The content key of one answer's label input (module docstring)."""
    facts = {
        "label_version": LABEL_VERSION,
        "writer": scope.writer,
        "context": scope.context_block,
        "text_sha256": _sha(scope.raw_text),
        "task_sha256": _sha(_task_text(request)),
        "supplied_sha256": [_sha(b) for b in _supplied_bodies(request)],
        "command_terms": list(scope.command_terms),
    }
    return _sha(json.dumps(facts, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True)
class LabelInput:
    """The label input of one answer. ``requests`` are the first attempt's rendered requests, one per chunk (none when the
    answer is ``oversized`` or the request could not be rendered, ``error``)."""
    input_key: str
    scope: OwnScope
    key_fingerprint: str
    requests: tuple[RenderedRequest, ...]
    oversized: bool
    error: Optional[str]
    _key: bytes = field(repr=False, compare=False)
    _prompt_path: Optional[pathlib.Path] = field(default=None, repr=False, compare=False)

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self.scope.chunks or (Chunk(0, (), None),)

    def render(self, chunk: int, *, attempt: int, part: Optional[int] = None, diagnostic: tuple[str, ...] = ()) -> RenderedRequest:
        """The request for ``chunk`` at ``attempt`` (a retry draws fresh canaries), or its half ``part`` after a truncation."""
        return render_request(self.scope, self.chunks[chunk], key=self._key, input_key=self.input_key, attempt=attempt, part=part,
                              diagnostic=diagnostic, prompt_path=self._prompt_path)

    @property
    def cache_key(self) -> str:
        """The rendered request(s) of the first attempt, as one key (the cache of successes is keyed on it)."""
        return _sha("\n".join(r.request_key for r in self.requests) + "|" + self.key_fingerprint)


def build_input(raw_text: str, request: Any = None, *, key: bytes, writer: str = "specialist",
                prompt_path: Optional[pathlib.Path] = None) -> LabelInput:
    """The label input of ``raw_text`` against the router's ``request`` (a dict or a request object): its own scope, its input
    key and its first attempt's rendered requests under the canary ``key``. Pure: the same inputs give byte-identical requests."""
    if not isinstance(key, (bytes, bytearray)) or not key:
        raise ValueError("a canary key is required")
    key = bytes(key)
    scope = own_scope(raw_text, request, writer=writer)
    ik = input_key(scope, request)
    fp = key_fingerprint(key)
    if scope.oversized:
        return LabelInput(ik, scope, fp, (), True, None, key, prompt_path)
    inp = LabelInput(ik, scope, fp, (), False, None, key, prompt_path)
    try:
        reqs = tuple(inp.render(c.index, attempt=0) for c in inp.chunks)
    except RenderError as e:
        return LabelInput(ik, scope, fp, (), False, str(e), key, prompt_path)
    return LabelInput(ik, scope, fp, reqs, False, None, key, prompt_path)
