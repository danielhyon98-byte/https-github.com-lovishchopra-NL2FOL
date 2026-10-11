"""Providers for any server exposing the OpenAI-style ``/v1/chat/completions`` API
(self-hosted open-weight models, gateways, compatible vendors).

Status: **untested live in this repository**. Tests exercise the request and
response handling through an ``httpx`` mock transport; no network call is made.

Configuration (environment variables, all read at construction time)
--------------------------------------------------------------------
* ``EPINOIC_OPENAI_BASE_URL`` (required): server base URL. ``/v1/chat/completions``
  is appended (a trailing ``/v1`` is not duplicated).
* ``EPINOIC_OPENAI_MODEL`` (required): model identifier sent in the request body.
* ``EPINOIC_OPENAI_API_KEY`` (optional): sent as a bearer token when present.

Requests use temperature 0 and a 60 second timeout. One retry is made on
timeouts, transport errors and HTTP 408/429/5xx. Everything else surfaces as
:class:`~epinoic_logic.translate.providers.base.ProviderError`.
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

ENV_BASE_URL = "EPINOIC_OPENAI_BASE_URL"
ENV_API_KEY = "EPINOIC_OPENAI_API_KEY"
ENV_MODEL = "EPINOIC_OPENAI_MODEL"
PROVIDER_NAME = "openai_compatible"
DEFAULT_TIMEOUT_S = 60.0
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
_TRANSIENT_STATUS = frozenset({408, 429})


@lru_cache(maxsize=8)
def _system_prompt(name: str) -> str:
    return prompts.load_prompt(name)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {truncate(str(exc), 300)}"


def _is_transient_exception(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    try:
        import httpx  # lazy: optional dependency
    except ImportError:
        return False
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _is_transient_status(status: int) -> bool:
    return status >= 500 or status in _TRANSIENT_STATUS


def chat_completions_url(base_url: str) -> str:
    """Join ``base_url`` with the chat-completions path without duplicating ``/v1``."""
    base = base_url.strip().rstrip("/")
    if not base:
        raise ProviderConfigurationError(f"{ENV_BASE_URL} is empty")
    if base.endswith("/v1"):
        return base + CHAT_COMPLETIONS_PATH[len("/v1"):]
    return base + CHAT_COMPLETIONS_PATH


def _extract_content(data: Any) -> str:
    """Return ``choices[0].message.content`` as text; raise when the shape is wrong."""
    if not isinstance(data, dict):
        raise ProviderError("chat completion response is not a JSON object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError("chat completion response has no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderError("chat completion choice has no message")
    content = message.get("content")
    if isinstance(content, list):  # some servers return content parts
        parts = [p.get("text") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = "\n".join(t for t in parts if isinstance(t, str))
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("chat completion message has no text content")
    return content.strip()


def _usage_int(data: dict[str, Any], field: str) -> Optional[int]:
    usage = data.get("usage")
    value = usage.get(field) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class _OpenAICompatibleBase:
    """Shared HTTP handling for the translation and review providers."""

    name = PROVIDER_NAME

    def __init__(
        self,
        client: Any = None,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: Optional[float] = 0.0,
        max_tokens: Optional[int] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = 1,
    ) -> None:
        """Create the provider.

        ``client`` may be any object exposing ``post(url, json=..., headers=..., timeout=...)``
        returning a response with ``status_code`` and ``json()`` (an ``httpx.Client``
        with a mock transport in tests); when omitted ``httpx`` is imported lazily.
        """
        base = base_url if base_url is not None else os.environ.get(ENV_BASE_URL, "")
        model = (model_id if model_id is not None else os.environ.get(ENV_MODEL, "")).strip()
        key = api_key if api_key is not None else os.environ.get(ENV_API_KEY, "")
        if not base.strip():
            raise ProviderConfigurationError(f"{ENV_BASE_URL} is not set")
        if not model:
            raise ProviderConfigurationError(f"{ENV_MODEL} is not set")
        if max_retries < 0:
            raise ProviderConfigurationError("max_retries must be >= 0")
        self.url = chat_completions_url(base)
        self.model_id = model
        self._api_key = key.strip() or None
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._client = client if client is not None else self._make_client()

    def _make_client(self) -> Any:
        try:
            import httpx  # lazy: optional dependency
        except ImportError as exc:
            raise ProviderConfigurationError("httpx is not installed; install the 'providers' extra") from exc
        return httpx.Client(timeout=self._timeout_s)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _body(self, system: str, user: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if self._max_tokens is not None:
            body["max_tokens"] = self._max_tokens
        return body

    def _complete(self, system: str, user: str, prompt_version: str) -> ProviderResponse:
        body = self._body(system, user)
        headers = self._headers()
        attempts_allowed = self._max_retries + 1
        for attempt in range(1, attempts_allowed + 1):
            started = time.perf_counter()
            try:
                response = self._client.post(self.url, json=body, headers=headers, timeout=self._timeout_s)
            except Exception as exc:
                transient = _is_transient_exception(exc)
                if transient and attempt < attempts_allowed:
                    continue
                raise ProviderError(f"chat completion request failed: {_describe(exc)}", transient=transient) from exc
            latency_ms = (time.perf_counter() - started) * 1000.0
            status = getattr(response, "status_code", None)
            if not isinstance(status, int):
                raise ProviderError("chat completion response has no status code")
            if status >= 400:
                transient = _is_transient_status(status)
                if transient and attempt < attempts_allowed:
                    continue
                raise ProviderError(f"chat completion request returned HTTP {status}", transient=transient)
            try:
                data = response.json()
            except Exception as exc:
                raise ProviderError(f"chat completion response is not JSON: {_describe(exc)}") from exc
            text = _extract_content(data)
            info = ProviderInfo(
                provider_name=self.name,
                model_id=self.model_id,
                prompt_version=prompt_version,
                temperature=self._temperature,
                input_tokens=_usage_int(data, "prompt_tokens"),
                output_tokens=_usage_int(data, "completion_tokens"),
                latency_ms=round(latency_ms, 3),
                attempts=attempt,
            )
            return ProviderResponse(raw_text=text, info=info)
        raise ProviderError("chat completion request failed: no attempt was made", transient=False)  # pragma: no cover


class OpenAICompatibleTranslationProvider(_OpenAICompatibleBase):
    """Translation provider for OpenAI-compatible chat-completion servers. Untested live in this repository.

    System message: the packaged prompt named by ``request.prompt_version``; user
    message: :func:`~epinoic_logic.translate.providers.rendering.render_translation_user_prompt`.
    """

    def propose(self, request: TranslationRequest) -> ProviderResponse:
        """Ask the server for a formalization proposal; raw text is returned unparsed."""
        try:
            system = _system_prompt(request.prompt_version)
        except (FileNotFoundError, ValueError) as exc:
            raise ProviderConfigurationError(f"translation prompt {request.prompt_version!r} is not available: {exc}") from exc
        return self._complete(system, render_translation_user_prompt(request), request.prompt_version)


class OpenAICompatibleReviewProvider(_OpenAICompatibleBase):
    """Semantic-fidelity review provider for OpenAI-compatible servers. Untested live in this repository."""

    def review(self, request: ReviewRequest) -> ProviderResponse:
        """Ask the server whether the formalization is faithful; raw text is returned unparsed."""
        try:
            system = _system_prompt(prompts.REVIEW_PROMPT_VERSION)
        except (FileNotFoundError, ValueError) as exc:
            raise ProviderConfigurationError(f"review prompt is not available: {exc}") from exc
        return self._complete(system, render_review_user_prompt(request), prompts.REVIEW_PROMPT_VERSION)
