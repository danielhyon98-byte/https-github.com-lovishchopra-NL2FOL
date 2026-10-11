"""Fixture providers: deterministic, network-free stand-ins for model providers.

Fixtures are keyed by ``claim_id``. They exist so the whole pipeline (eligibility,
parsing, schema validation, policy validation, grounding, engine, outcome) can be
exercised in tests and in the service without any model call. A fixture never
decides anything: its text passes through exactly the same untrusted-data path as
a model's text.
"""
from __future__ import annotations

import json
from typing import Mapping, Optional, Union

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
