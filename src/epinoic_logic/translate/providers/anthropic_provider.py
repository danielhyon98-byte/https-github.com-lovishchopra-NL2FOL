"""Providers backed by the Anthropic Messages API.

Status: **untested live in this repository**. The request/response handling is
covered by tests with a substituted client object; no network call is made in the
test suite. Behaviour against the real service must be confirmed in an
integration environment before production use.

Configuration
-------------
* ``EPINOIC_ANTHROPIC_MODEL`` (required): the model identifier to request. This
  module never hard-codes a model.
* API credentials are read by the SDK itself from its default environment
  variable; this module never touches them.

The SDK is imported lazily, so the rest of the package has no dependency on it.
Every failure, including a missing SDK or configuration, surfaces as
:class:`~epinoic_logic.translate.providers.base.ProviderError` (or its subclass
:class:`ProviderConfigurationError`); nothing else escapes ``propose``/``review``.
One retry is made on transient failures (connection or timeout errors, HTTP 408,
409, 429, 5xx and 529); the SDK's own retries are disabled so the count is exact.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any, Optional

from .. import prompts
from ..common import truncate
from ..contracts import ProviderInfo
from .base import ProviderConfigurationError, ProviderError, ProviderResponse, ReviewRequest, TranslationRequest
from .rendering import render_review_user_prompt, render_translation_user_prompt

ENV_MODEL = "EPINOIC_ANTHROPIC_MODEL"
PROVIDER_NAME = "anthropic"
TRANSLATION_MAX_TOKENS = 4000
REVIEW_MAX_TOKENS = 2000
DEFAULT_TIMEOUT_S = 120.0
_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


@lru_cache(maxsize=8)
def _system_prompt(name: str) -> str:
    return prompts.load_prompt(name)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {truncate(str(exc), 300)}"


def _is_transient(exc: BaseException) -> bool:
    """Classify an SDK (or duck-typed) exception as worth exactly one retry."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    try:
        import anthropic  # lazy: optional dependency
    except ImportError:
        return False
    return isinstance(exc, anthropic.APIConnectionError)  # includes APITimeoutError


def _block_text(block: Any) -> Optional[str]:
    if isinstance(block, dict):
        return block.get("text") if block.get("type") == "text" else None
    if getattr(block, "type", None) == "text":
        text = getattr(block, "text", None)
        return text if isinstance(text, str) else None
    return None


def _extract_text(message: Any) -> str:
    """Concatenate the text blocks of a Messages API response; raise when there are none."""
    if getattr(message, "stop_reason", None) == "refusal":
        raise ProviderError("the model declined to answer the request (stop_reason refusal)")
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        texts = [content]
    else:
        texts = [t for t in (_block_text(b) for b in (content or [])) if t]
    text = "\n".join(texts).strip()
    if not text:
        raise ProviderError("the response contained no text content")
    return text


def _usage_int(message: Any, field: str) -> Optional[int]:
    usage = getattr(message, "usage", None)
    if usage is None and isinstance(message, dict):
        usage = message.get("usage")
    value = getattr(usage, field, None) if not isinstance(usage, dict) else usage.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class _AnthropicBase:
    """Shared client handling for the translation and review providers."""

    name = PROVIDER_NAME
    _max_tokens: int = TRANSLATION_MAX_TOKENS

    def __init__(
        self,
        client: Any = None,
        *,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = 0.0,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = 1,
    ) -> None:
        """Create the provider.

        ``client`` may be any object exposing ``messages.create(**params)`` (used by
        tests); when omitted the SDK is imported and a client built with its own
        retries disabled. ``temperature`` is sent when not ``None`` (default ``0``);
        pass ``None`` for models that reject sampling parameters.
        """
        model = (model_id or os.environ.get(ENV_MODEL, "")).strip()
        if not model:
            raise ProviderConfigurationError(f"{ENV_MODEL} is not set; the Anthropic provider needs a model identifier")
        if max_retries < 0:
            raise ProviderConfigurationError("max_retries must be >= 0")
        self.model_id = model
        self._temperature = temperature
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        if max_tokens is not None:
            self._max_tokens = max_tokens
        self._client = client if client is not None else self._make_client()

    def _make_client(self) -> Any:
        try:
            import anthropic  # lazy: optional dependency
        except ImportError as exc:
            raise ProviderConfigurationError(
                "the anthropic SDK is not installed; install the 'providers' extra"
            ) from exc
        try:
            return anthropic.Anthropic(max_retries=0, timeout=self._timeout_s)
        except Exception as exc:  # missing credentials, bad environment
            raise ProviderConfigurationError(f"could not create the Anthropic client: {_describe(exc)}") from exc

    def _params(self, system: str, user: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self._temperature is not None:
            params["temperature"] = self._temperature
        return params

    def _complete(self, system: str, user: str, prompt_version: str) -> ProviderResponse:
        params = self._params(system, user)
        attempts_allowed = self._max_retries + 1
        for attempt in range(1, attempts_allowed + 1):
            started = time.perf_counter()
            try:
                message = self._client.messages.create(**params)
            except Exception as exc:  # every SDK failure becomes a ProviderError
                transient = _is_transient(exc)
                if transient and attempt < attempts_allowed:
                    continue
                raise ProviderError(f"Anthropic request failed: {_describe(exc)}", transient=transient) from exc
            latency_ms = (time.perf_counter() - started) * 1000.0
            text = _extract_text(message)
            info = ProviderInfo(
                provider_name=self.name,
                model_id=self.model_id,
                prompt_version=prompt_version,
                temperature=self._temperature,
                input_tokens=_usage_int(message, "input_tokens"),
                output_tokens=_usage_int(message, "output_tokens"),
                latency_ms=round(latency_ms, 3),
                attempts=attempt,
            )
            return ProviderResponse(raw_text=text, info=info)
        raise ProviderError("Anthropic request failed: no attempt was made", transient=False)  # pragma: no cover


class AnthropicTranslationProvider(_AnthropicBase):
    """Translation provider on the Anthropic Messages API. Untested live in this repository.

    System prompt: the packaged prompt named by ``request.prompt_version`` (the
    pipeline default is ``translate_v1``). User prompt:
    :func:`~epinoic_logic.translate.providers.rendering.render_translation_user_prompt`.
    ``max_tokens`` 4000, temperature 0 unless configured otherwise.
    """

    _max_tokens = TRANSLATION_MAX_TOKENS

    def propose(self, request: TranslationRequest) -> ProviderResponse:
        """Ask the model for a formalization proposal; raw text is returned unparsed."""
        try:
            system = _system_prompt(request.prompt_version)
        except (FileNotFoundError, ValueError) as exc:
            raise ProviderConfigurationError(f"translation prompt {request.prompt_version!r} is not available: {exc}") from exc
        user = render_translation_user_prompt(request)
        return self._complete(system, user, request.prompt_version)


class AnthropicReviewProvider(_AnthropicBase):
    """Semantic-fidelity review provider on the Anthropic Messages API. Untested live in this repository.

    System prompt ``review_v1``; user prompt
    :func:`~epinoic_logic.translate.providers.rendering.render_review_user_prompt`.
    """

    _max_tokens = REVIEW_MAX_TOKENS

    def review(self, request: ReviewRequest) -> ProviderResponse:
        """Ask the model whether the formalization is faithful; raw text is returned unparsed."""
        try:
            system = _system_prompt(prompts.REVIEW_PROMPT_VERSION)
        except (FileNotFoundError, ValueError) as exc:
            raise ProviderConfigurationError(f"review prompt is not available: {exc}") from exc
        user = render_review_user_prompt(request)
        return self._complete(system, user, prompts.REVIEW_PROMPT_VERSION)
