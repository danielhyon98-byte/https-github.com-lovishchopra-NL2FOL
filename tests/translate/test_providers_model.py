"""Model-backed providers with substituted clients: parsing, retries, error mapping. No network.

The live services are never contacted here; these providers remain 'untested live'.
An autouse fixture makes any socket connection attempt fail loudly.
"""
from __future__ import annotations

import json
import socket
import sys
from types import SimpleNamespace

import pytest

from epinoic_logic.translate import Translator, TranslationStatus
from epinoic_logic.translate.contracts import Interpretation
from epinoic_logic.translate.eligibility import decide_eligibility
from epinoic_logic.translate.prompts import load_prompt
from epinoic_logic.translate.providers import (
    AnthropicReviewProvider,
    AnthropicTranslationProvider,
    OpenAICompatibleReviewProvider,
    OpenAICompatibleTranslationProvider,
    ProviderConfigurationError,
    ProviderError,
    ReviewRequest,
    TranslationRequest,
)
from epinoic_logic.translate.providers.openai_compatible import chat_completions_url
from epinoic_logic.ir.schema import Problem

from .conftest import chain_problem, make_claim, provider_output

MODEL_ENV_VALUE = "fixture-model-id"
OUTPUT_JSON = json.dumps(provider_output(chain_problem()))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def translation_request() -> TranslationRequest:
    claim = make_claim(supporting_claim_ids=["c-ev"])
    return TranslationRequest(claim=claim, eligibility=decide_eligibility(claim), prompt_version="translate_v1", ir_version="1.0", subject_profile_text="profile text")


@pytest.fixture
def review_request() -> ReviewRequest:
    claim = make_claim(supporting_claim_ids=["c-ev"])
    return ReviewRequest(claim=claim, problem=Problem.model_validate(chain_problem()), interpretation=Interpretation(reading="r"))


# ----------------------------------------------------------------- Anthropic


class DuckStatusError(Exception):
    """Stands in for an SDK status error: carries ``status_code`` like the real classes."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status


def message(text: str = OUTPUT_JSON, *, input_tokens: int = 11, output_tokens: int = 22, stop_reason: str = "end_turn", blocks=None):
    content = blocks if blocks is not None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=content, usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens), stop_reason=stop_reason)


class FakeAnthropicClient:
    """Duck-typed ``client.messages.create``; each queued outcome is returned or raised in turn."""

    def __init__(self, *outcomes) -> None:
        self.calls: list[dict] = []
        self._outcomes = list(outcomes)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def anthropic_env(monkeypatch):
    monkeypatch.setenv("EPINOIC_ANTHROPIC_MODEL", MODEL_ENV_VALUE)


def test_anthropic_requires_model_env(monkeypatch):
    monkeypatch.delenv("EPINOIC_ANTHROPIC_MODEL", raising=False)
    with pytest.raises(ProviderConfigurationError) as exc:
        AnthropicTranslationProvider(client=FakeAnthropicClient())
    assert "EPINOIC_ANTHROPIC_MODEL" in str(exc.value) and isinstance(exc.value, ProviderError)


def test_anthropic_sdk_is_imported_lazily_and_absence_is_a_provider_error(monkeypatch, anthropic_env):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # makes `import anthropic` raise ImportError
    with pytest.raises(ProviderConfigurationError) as exc:
        AnthropicTranslationProvider()
    assert "not installed" in str(exc.value)
    AnthropicTranslationProvider(client=FakeAnthropicClient())  # injected client needs no SDK


def test_anthropic_propose_parses_text_and_binds_metadata(anthropic_env, translation_request):
    client = FakeAnthropicClient(message())
    provider = AnthropicTranslationProvider(client=client)
    response = provider.propose(translation_request)
    assert response.raw_text == OUTPUT_JSON
    info = response.info
    assert info.provider_name == "anthropic" and info.model_id == MODEL_ENV_VALUE and info.prompt_version == "translate_v1"
    assert info.input_tokens == 11 and info.output_tokens == 22 and info.attempts == 1 and info.temperature == 0.0
    assert info.latency_ms is not None and info.latency_ms >= 0
    params = client.calls[0]
    assert params["model"] == MODEL_ENV_VALUE and params["max_tokens"] == 4000 and params["temperature"] == 0
    assert params["system"] == load_prompt("translate_v1")
    assert params["messages"][0]["role"] == "user" and "<<<DATA claim>>>" in params["messages"][0]["content"]
    assert "<<<DATA subject_profile>>>" in params["messages"][0]["content"]


def test_anthropic_transient_error_is_retried_once(anthropic_env, translation_request):
    client = FakeAnthropicClient(DuckStatusError(529), message())
    response = AnthropicTranslationProvider(client=client).propose(translation_request)
    assert response.info.attempts == 2 and len(client.calls) == 2


def test_anthropic_non_transient_error_is_not_retried(anthropic_env, translation_request):
    client = FakeAnthropicClient(DuckStatusError(400), message())
    with pytest.raises(ProviderError) as exc:
        AnthropicTranslationProvider(client=client).propose(translation_request)
    assert exc.value.transient is False and len(client.calls) == 1 and "HTTP 400" in str(exc.value)


def test_anthropic_transient_errors_exhausted(anthropic_env, translation_request):
    client = FakeAnthropicClient(TimeoutError("slow"), DuckStatusError(503), message())
    with pytest.raises(ProviderError) as exc:
        AnthropicTranslationProvider(client=client).propose(translation_request)
    assert exc.value.transient is True and len(client.calls) == 2


def test_anthropic_real_sdk_exception_classes(anthropic_env, translation_request):
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    req = httpx2.Request("POST", "https://example.invalid/v1/messages")
    connection_error = anthropic.APIConnectionError(request=req)
    client = FakeAnthropicClient(connection_error, message())
    assert AnthropicTranslationProvider(client=client).propose(translation_request).info.attempts == 2
    bad_request = anthropic.BadRequestError("bad", response=httpx2.Response(400, request=req), body=None)
    client = FakeAnthropicClient(bad_request)
    with pytest.raises(ProviderError) as exc:
        AnthropicTranslationProvider(client=client).propose(translation_request)
    assert exc.value.transient is False and len(client.calls) == 1
    overloaded = anthropic.InternalServerError("busy", response=httpx2.Response(529, request=req), body=None)
    client = FakeAnthropicClient(overloaded, overloaded)
    with pytest.raises(ProviderError) as exc:
        AnthropicTranslationProvider(client=client).propose(translation_request)
    assert exc.value.transient is True and len(client.calls) == 2


def test_anthropic_empty_or_refused_response_is_provider_error(anthropic_env, translation_request):
    with pytest.raises(ProviderError) as exc:
        AnthropicTranslationProvider(client=FakeAnthropicClient(message(blocks=[SimpleNamespace(type="thinking", thinking="...")]))).propose(translation_request)
    assert "no text" in str(exc.value)
    with pytest.raises(ProviderError) as exc:
        AnthropicTranslationProvider(client=FakeAnthropicClient(message(stop_reason="refusal"))).propose(translation_request)
    assert "declined" in str(exc.value)


def test_anthropic_text_blocks_are_concatenated_and_dict_blocks_accepted(anthropic_env, translation_request):
    blocks = [{"type": "text", "text": "{\"a\":"}, {"type": "text", "text": "1}"}]
    response = AnthropicTranslationProvider(client=FakeAnthropicClient(message(blocks=blocks))).propose(translation_request)
    assert response.raw_text == "{\"a\":\n1}"


def test_anthropic_temperature_can_be_omitted(anthropic_env, translation_request):
    client = FakeAnthropicClient(message())
    response = AnthropicTranslationProvider(client=client, temperature=None).propose(translation_request)
    assert "temperature" not in client.calls[0] and response.info.temperature is None


def test_anthropic_explicit_model_id_overrides_env(monkeypatch, translation_request):
    monkeypatch.delenv("EPINOIC_ANTHROPIC_MODEL", raising=False)
    provider = AnthropicTranslationProvider(client=FakeAnthropicClient(message()), model_id="explicit-model")
    assert provider.propose(translation_request).info.model_id == "explicit-model"


def test_anthropic_review_provider(anthropic_env, review_request):
    client = FakeAnthropicClient(message('{"verdict": "faithful", "issues": []}'))
    response = AnthropicReviewProvider(client=client).review(review_request)
    assert json.loads(response.raw_text)["verdict"] == "faithful" and response.info.prompt_version == "review_v1"
    params = client.calls[0]
    assert params["system"] == load_prompt("review_v1") and params["max_tokens"] == 2000
    assert "<<<DATA problem>>>" in params["messages"][0]["content"]


def test_anthropic_through_translator(anthropic_env, english_claims, english_report):
    client = FakeAnthropicClient(message())
    result = Translator(AnthropicTranslationProvider(client=client)).translate(english_claims["c-point"], english_report)
    assert result.status is TranslationStatus.TRANSLATED and result.provider.provider_name == "anthropic"
    assert result.provider.model_id == MODEL_ENV_VALUE and result.provider.attempts == 1


def test_anthropic_failure_through_translator_is_translation_failed(anthropic_env, english_claims, english_report):
    client = FakeAnthropicClient(DuckStatusError(401))
    result = Translator(AnthropicTranslationProvider(client=client)).translate(english_claims["c-point"], english_report)
    assert result.status is TranslationStatus.TRANSLATION_FAILED and "HTTP 401" in result.diagnostics[-1]


# ------------------------------------------------------- OpenAI-compatible

BASE_URL = "https://llm.example.test"


@pytest.fixture
def openai_env(monkeypatch):
    monkeypatch.setenv("EPINOIC_OPENAI_BASE_URL", BASE_URL)
    monkeypatch.setenv("EPINOIC_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("EPINOIC_OPENAI_MODEL", "fixture-chat-model")


def completion(content=OUTPUT_JSON, usage=True):
    body = {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
    if usage:
        body["usage"] = {"prompt_tokens": 33, "completion_tokens": 44}
    return body


def mock_client(*outcomes):
    """``httpx.Client`` over a mock transport; outcomes are (status, json_body) tuples or exceptions to raise."""
    httpx = pytest.importorskip("httpx")
    queue = list(outcomes)
    seen: list = []

    def handler(request):
        seen.append(request)
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        status, body = outcome
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status, text="not json")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.seen = seen  # type: ignore[attr-defined]
    return client


def test_openai_requires_configuration(monkeypatch):
    for var in ("EPINOIC_OPENAI_BASE_URL", "EPINOIC_OPENAI_API_KEY", "EPINOIC_OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleTranslationProvider(client=mock_client())
    monkeypatch.setenv("EPINOIC_OPENAI_BASE_URL", BASE_URL)
    with pytest.raises(ProviderConfigurationError) as exc:
        OpenAICompatibleTranslationProvider(client=mock_client())
    assert "EPINOIC_OPENAI_MODEL" in str(exc.value)


def test_chat_completions_url_join():
    assert chat_completions_url("https://h.test") == "https://h.test/v1/chat/completions"
    assert chat_completions_url("https://h.test/") == "https://h.test/v1/chat/completions"
    assert chat_completions_url("https://h.test/v1") == "https://h.test/v1/chat/completions"
    assert chat_completions_url("https://h.test/v1/") == "https://h.test/v1/chat/completions"
    with pytest.raises(ProviderConfigurationError):
        chat_completions_url("  ")


def test_openai_propose_posts_expected_request_and_parses_content(openai_env, translation_request):
    client = mock_client((200, completion()))
    response = OpenAICompatibleTranslationProvider(client=client).propose(translation_request)
    assert response.raw_text == OUTPUT_JSON
    assert response.info.provider_name == "openai_compatible" and response.info.model_id == "fixture-chat-model"
    assert response.info.input_tokens == 33 and response.info.output_tokens == 44 and response.info.attempts == 1
    request = client.seen[0]
    assert str(request.url) == BASE_URL + "/v1/chat/completions" and request.method == "POST"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "fixture-chat-model" and body["temperature"] == 0 and "max_tokens" not in body
    assert body["messages"][0] == {"role": "system", "content": load_prompt("translate_v1")}
    assert body["messages"][1]["role"] == "user" and "<<<DATA claim>>>" in body["messages"][1]["content"]


def test_openai_missing_api_key_sends_no_authorization(monkeypatch, openai_env, translation_request):
    monkeypatch.delenv("EPINOIC_OPENAI_API_KEY")
    client = mock_client((200, completion()))
    OpenAICompatibleTranslationProvider(client=client).propose(translation_request)
    assert "authorization" not in client.seen[0].headers


def test_openai_5xx_is_retried_once(openai_env, translation_request):
    client = mock_client((503, {"error": "busy"}), (200, completion()))
    response = OpenAICompatibleTranslationProvider(client=client).propose(translation_request)
    assert response.info.attempts == 2 and len(client.seen) == 2


def test_openai_4xx_is_not_retried(openai_env, translation_request):
    client = mock_client((400, {"error": "bad"}), (200, completion()))
    with pytest.raises(ProviderError) as exc:
        OpenAICompatibleTranslationProvider(client=client).propose(translation_request)
    assert exc.value.transient is False and "HTTP 400" in str(exc.value) and len(client.seen) == 1


def test_openai_timeouts_exhaust_retry(openai_env, translation_request):
    httpx = pytest.importorskip("httpx")
    client = mock_client(httpx.ReadTimeout("slow"), httpx.ConnectError("down"), (200, completion()))
    with pytest.raises(ProviderError) as exc:
        OpenAICompatibleTranslationProvider(client=client).propose(translation_request)
    assert exc.value.transient is True and len(client.seen) == 2


def test_openai_rate_limit_then_success(openai_env, translation_request):
    client = mock_client((429, {"error": "slow down"}), (200, completion()))
    assert OpenAICompatibleTranslationProvider(client=client).propose(translation_request).info.attempts == 2


def test_openai_malformed_bodies_are_provider_errors(openai_env, translation_request):
    for body in ({"choices": []}, {"choices": [{"message": {"content": ""}}]}, {"nope": 1}, None):
        with pytest.raises(ProviderError):
            OpenAICompatibleTranslationProvider(client=mock_client((200, body))).propose(translation_request)


def test_openai_content_parts_are_joined_and_usage_optional(openai_env, translation_request):
    parts = [{"type": "text", "text": "{\"a\":"}, {"type": "image_url", "image_url": {}}, {"type": "text", "text": "1}"}]
    response = OpenAICompatibleTranslationProvider(client=mock_client((200, completion(parts, usage=False)))).propose(translation_request)
    assert response.raw_text == "{\"a\":\n1}" and response.info.input_tokens is None


def test_openai_review_provider(openai_env, review_request):
    client = mock_client((200, completion('{"verdict": "uncertain", "issues": ["vague"]}')))
    response = OpenAICompatibleReviewProvider(client=client).review(review_request)
    assert response.info.prompt_version == "review_v1"
    body = json.loads(client.seen[0].content)
    assert body["messages"][0]["content"] == load_prompt("review_v1") and "<<<DATA problem>>>" in body["messages"][1]["content"]


def test_openai_through_translator(openai_env, english_claims, english_report):
    result = Translator(OpenAICompatibleTranslationProvider(client=mock_client((200, completion())))).translate(english_claims["c-point"], english_report)
    assert result.status is TranslationStatus.TRANSLATED and result.provider.provider_name == "openai_compatible"
    failed = Translator(OpenAICompatibleTranslationProvider(client=mock_client((500, {}), (502, {})))).translate(english_claims["c-point"], english_report)
    assert failed.status is TranslationStatus.TRANSLATION_FAILED and "HTTP 502" in failed.diagnostics[-1]


def test_openai_httpx_is_imported_lazily(monkeypatch, openai_env):
    monkeypatch.setitem(sys.modules, "httpx", None)
    with pytest.raises(ProviderConfigurationError) as exc:
        OpenAICompatibleTranslationProvider()
    assert "httpx is not installed" in str(exc.value)
