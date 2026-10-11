"""Replaceable model providers for the translation layer.

Importing this package never imports a vendor SDK: the Anthropic and
OpenAI-compatible providers load their HTTP dependencies lazily on construction,
so the fixture provider and the pipeline work in a minimal install.
"""
from .anthropic_provider import AnthropicReviewProvider, AnthropicTranslationProvider  # noqa: F401
from .base import (  # noqa: F401
    ProviderConfigurationError,
    ProviderError,
    ProviderResponse,
    ReviewProvider,
    ReviewRequest,
    TranslationProvider,
    TranslationRequest,
)
from .fixture import FixtureReviewProvider, FixtureTranslationProvider  # noqa: F401
from .openai_compatible import OpenAICompatibleReviewProvider, OpenAICompatibleTranslationProvider  # noqa: F401
from .rendering import data_block, render_review_user_prompt, render_translation_user_prompt  # noqa: F401

__all__ = [
    "ProviderError",
    "ProviderConfigurationError",
    "ProviderResponse",
    "TranslationRequest",
    "TranslationProvider",
    "ReviewRequest",
    "ReviewProvider",
    "FixtureTranslationProvider",
    "FixtureReviewProvider",
    "AnthropicTranslationProvider",
    "AnthropicReviewProvider",
    "OpenAICompatibleTranslationProvider",
    "OpenAICompatibleReviewProvider",
    "data_block",
    "render_translation_user_prompt",
    "render_review_user_prompt",
]
