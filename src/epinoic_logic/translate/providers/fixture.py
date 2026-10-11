"""Fixture providers: deterministic, network-free stand-ins for model providers.

Fixtures are keyed by ``claim_id``. They exist so the whole pipeline (eligibility,
parsing, schema validation, policy validation, grounding, engine, outcome) can be
exercised in tests and in the service without any model call. A fixture never
decides anything: its text passes through exactly the same untrusted-data path as
a model's text.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Union

from ...ir.canonical import strict_object_pairs
from .. import prompts
from ..contracts import ProviderInfo, sha256_text
from .base import ProviderError, ProviderResponse, ReviewRequest, TranslationRequest

FixtureValue = Union[str, dict, list, ProviderError]
"""Raw JSON text, a JSON-serialisable dict, a ``ProviderError`` to raise, or a list
of those served in order on successive attempts (the last entry repeats)."""

FIXTURE_NAME = "fixture"


def _as_text(value: object, claim_id: str) -> str:
    if isinstance(value, ProviderError):
        raise value
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    raise ProviderError(f"fixture value for claim {claim_id!r} must be text, a dict or a list of those")


class _FixtureBase:
    """Shared bookkeeping: per-claim attempt counters and a record of every call."""

    name = FIXTURE_NAME

    def __init__(self, responses: Mapping[str, FixtureValue]) -> None:
        self._responses: dict[str, FixtureValue] = dict(responses)
        self._served: dict[str, int] = {}

    def _next_text(self, claim_id: str) -> str:
        if claim_id not in self._responses:
            raise ProviderError(f"fixture has no response for claim {claim_id!r}")
        value = self._responses[claim_id]
        served = self._served.get(claim_id, 0)
        self._served[claim_id] = served + 1
        if isinstance(value, list):
            if not value:
                raise ProviderError(f"fixture response list for claim {claim_id!r} is empty")
            value = value[min(served, len(value) - 1)]
        return _as_text(value, claim_id)

    def served(self, claim_id: str) -> int:
        """How many times a response was requested for ``claim_id``."""
        return self._served.get(claim_id, 0)


class FixtureTranslationProvider(_FixtureBase):
    """Translation provider that replays canned JSON keyed by ``claim_id``.

    ``responses[claim_id]`` is raw JSON text, a dict (serialised to JSON), a
    ``ProviderError`` instance (raised when reached), or a list of such values that
    are served on successive attempts; once the list is exhausted its last entry is
    repeated. A claim with no entry raises :class:`ProviderError`, which the pipeline
    maps to ``TRANSLATION_FAILED``. Every request is kept in ``calls`` for assertions.
    """

    def __init__(self, responses: Mapping[str, FixtureValue], *, claim_text_sha256: Optional[Mapping[str, str]] = None) -> None:
        super().__init__(responses)
        self.calls: list[TranslationRequest] = []
        #: claim_id -> sha256 of the claim text each fixture was produced for. When known, a request for the same
        #: claim id with another text is refused (``ProviderError``), so a canned formalization is never attached to
        #: a re-stated claim whose wording changed; a fixture without a digest is served by claim id as before.
        self.claim_text_sha256: dict[str, str] = dict(claim_text_sha256 or {})

    def propose(self, request: TranslationRequest) -> ProviderResponse:
        """Return the next canned response for ``request.claim.claim_id``."""
        self.calls.append(request)
        claim_id = request.claim.claim_id
        expected = self.claim_text_sha256.get(claim_id)
        if expected is not None and expected != sha256_text(request.claim.claim_text):
            raise ProviderError(f"fixture for claim {claim_id!r} was produced for a different claim text (stale fixture); it is not served for the current text")
        text = self._next_text(claim_id)
        info = ProviderInfo(
            provider_name=FIXTURE_NAME,
            model_id=FIXTURE_NAME,
            prompt_version=request.prompt_version,
            temperature=0.0,
            attempts=1,
        )
        return ProviderResponse(raw_text=text, info=info)


class FixtureReviewProvider(_FixtureBase):
    """Review provider that replays canned ``{"verdict": ..., "issues": [...]}`` JSON
    keyed by ``claim_id``. Same value forms and attempt semantics as
    :class:`FixtureTranslationProvider`.
    """

    def __init__(self, responses: Mapping[str, FixtureValue]) -> None:
        super().__init__(responses)
        self.calls: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> ProviderResponse:
        """Return the next canned review for ``request.claim.claim_id``."""
        self.calls.append(request)
        text = self._next_text(request.claim.claim_id)
        info = ProviderInfo(
            provider_name=FIXTURE_NAME,
            model_id=FIXTURE_NAME,
            prompt_version=prompts.REVIEW_PROMPT_VERSION,
            temperature=0.0,
            attempts=1,
        )
        return ProviderResponse(raw_text=text, info=info)


@dataclass(frozen=True)
class CompletionCall:
    """One call a :class:`FixtureCompletionProvider` received, exactly as given."""
    system: str
    user: str
    prompt_version: str


_DATA_OPEN_RE = re.compile(r"^<<<DATA ([A-Za-z0-9_.-]+)>>>$")


def dossier_digest_of(user: str) -> Optional[str]:
    """The ``dossier_sha256`` of the dossier in a completion's user text: the JSON inside the ``dossier`` data block, or
    the whole text when it is a bare JSON object. The text is parsed as JSON data only (duplicate keys refused); nothing
    in it is evaluated. ``None`` when there is no dossier or no digest."""
    if not isinstance(user, str):
        return None
    lines = user.split("\n")
    body = user
    if lines and _DATA_OPEN_RE.match(lines[0]):
        label = _DATA_OPEN_RE.match(lines[0]).group(1)
        if label != "dossier" or len(lines) < 3 or lines[-1] != f"<<<END {label}>>>":
            return None
        body = "\n".join(lines[1:-1])
    try:
        obj = json.loads(body, object_pairs_hook=strict_object_pairs)
    except (ValueError, RecursionError):
        return None
    digest = obj.get("dossier_sha256") if isinstance(obj, dict) else None
    return digest if isinstance(digest, str) else None


class FixtureCompletionProvider:
    """Completion provider (:class:`~epinoic_logic.translate.providers.base.CompletionProvider`) that serves canned
    replies, for tests and contained runs: no network, no model.

    ``replies`` is either a mapping from a dossier digest to a reply (the digest is read from the ``dossier`` data block
    of the user text, or from a bare dossier JSON), or a sequence of replies served in order, one per call. A reply is
    raw text, a dict (serialised to JSON) or a :class:`ProviderError` instance, which is raised when reached. A call with
    no reply left (an unknown digest, an exhausted sequence) raises ``ProviderError``. Every call is recorded in
    ``calls`` exactly as received. A canned reply never decides anything: it enters the verdict intake as untrusted text,
    exactly like a model's reply.
    """

    name = FIXTURE_NAME

    def __init__(self, replies: Union[Mapping[str, FixtureValue], Sequence[FixtureValue]], *, model_id: str = FIXTURE_NAME) -> None:
        if isinstance(replies, Mapping):
            self._by_digest: Optional[dict[str, FixtureValue]] = dict(replies)
            self._in_order: list[FixtureValue] = []
        elif isinstance(replies, (str, bytes)) or not isinstance(replies, Sequence):
            raise TypeError("replies must be a mapping from dossier digest to reply, or a sequence of replies")
        else:
            self._by_digest = None
            self._in_order = list(replies)
        self.model_id = model_id
        self.calls: list[CompletionCall] = []
        self._next = 0
        self._lock = threading.Lock()

    @property
    def keyed(self) -> bool:
        """True when replies are keyed by dossier digest, False when they are served in order."""
        return self._by_digest is not None

    def remaining(self) -> int:
        """Replies not yet served (in-order mode); keyed replies may be served any number of times."""
        with self._lock:
            return len(self._in_order) - self._next if self._by_digest is None else len(self._by_digest)

    def _reply(self, user: str) -> FixtureValue:
        if self._by_digest is not None:
            digest = dossier_digest_of(user)
            if digest is None:
                raise ProviderError("fixture completion: the user text carries no dossier digest")
            if digest not in self._by_digest:
                raise ProviderError(f"fixture completion has no reply for dossier {digest[:16]}")
            return self._by_digest[digest]
        if self._next >= len(self._in_order):
            raise ProviderError("fixture completion has no reply left")
        value = self._in_order[self._next]
        self._next += 1
        return value

    def complete(self, system: str, user: str, *, prompt_version: str) -> ProviderResponse:
        """Record the call and return the next canned reply (raw text, never parsed here)."""
        with self._lock:
            self.calls.append(CompletionCall(system=system, user=user, prompt_version=prompt_version))
            value = self._reply(user)
        if isinstance(value, list):
            raise ProviderError("fixture completion: a reply is text, a dict or a ProviderError, not a list")
        text = _as_text(value, "completion")
        info = ProviderInfo(provider_name=FIXTURE_NAME, model_id=self.model_id, prompt_version=prompt_version, temperature=0.0, attempts=1)
        return ProviderResponse(raw_text=text, info=info)
