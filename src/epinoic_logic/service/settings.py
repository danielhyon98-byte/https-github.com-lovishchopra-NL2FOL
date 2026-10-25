"""Service settings, read from the environment or constructed directly.

Every value is validated up front so that a misconfigured service refuses to
start instead of serving unauthenticated or unsigned results. The service fails
closed: a bearer token is mandatory, and a signing key is mandatory unless
``allow_unsigned_for_tests`` is set explicitly (it never is from the environment).

Environment variables (all prefixed ``EPINOIC_``):

``EPINOIC_SERVICE_TOKEN``     bearer token clients must present (required)
``EPINOIC_SIGNING_KEY``       HMAC-SHA256 key as hex text (required)
``EPINOIC_SIGNING_KEY_ID``    identifier bound into signed results (default ``default``)
``EPINOIC_MAX_BODY_BYTES``    request body limit (default 1_000_000)
``EPINOIC_MAX_CONCURRENCY``   simultaneous solver runs (default 4)
``EPINOIC_RATE_PER_MINUTE``   token-bucket capacity per bearer token (default 60)
``EPINOIC_ALLOW_CLIENT_FIXTURES`` ``1``/``true``/``yes`` lets ``POST /v1/outcomes`` take the client's
                              ``fixture_responses`` (default off: the client would act as the translation
                              provider; the route then answers 403 ``E506`` before reading the body)

Secrets are excluded from ``repr`` so that settings can appear in logs safely.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ENV_PREFIX = "EPINOIC_"
DEFAULT_MAX_BODY_BYTES = 1_000_000
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_RATE_PER_MINUTE = 60
MIN_TOKEN_LENGTH = 16
MIN_SIGNING_KEY_BYTES = 16
_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})
_FALSE_WORDS = frozenset({"0", "false", "no", "off"})

__all__ = [
    "ENV_PREFIX",
    "DEFAULT_MAX_BODY_BYTES",
    "DEFAULT_MAX_CONCURRENCY",
    "DEFAULT_RATE_PER_MINUTE",
    "MIN_TOKEN_LENGTH",
    "MIN_SIGNING_KEY_BYTES",
    "SettingsError",
    "ServiceSettings",
]


class SettingsError(ValueError):
    """The service configuration is missing or invalid. The message never contains secret values."""


class ServiceSettings(BaseModel):
    """Validated runtime configuration for the HTTP service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_token: str = Field(
        min_length=MIN_TOKEN_LENGTH,
        max_length=512,
        repr=False,
        description="bearer token required on every /v1 request; compared in constant time",
    )
    signing_key: Optional[bytes] = Field(
        default=None,
        repr=False,
        description="HMAC-SHA256 key for result signatures; None only when allow_unsigned_for_tests",
    )
    signing_key_id: str = Field(default="default", min_length=1, max_length=64)
    max_body_bytes: int = Field(default=DEFAULT_MAX_BODY_BYTES, ge=1024, le=50_000_000)
    max_concurrency: int = Field(default=DEFAULT_MAX_CONCURRENCY, ge=1, le=256)
    rate_per_minute: int = Field(default=DEFAULT_RATE_PER_MINUTE, ge=1, le=100_000)
    allow_unsigned_for_tests: bool = Field(
        default=False,
        description="permit running without a signing key; for tests only, never settable from the environment",
    )
    allow_client_fixtures: bool = Field(
        default=False,
        description=(
            "let POST /v1/outcomes take the client's fixture_responses as the translation provider's output; off by default, "
            "since any authenticated client would then choose what the translation says (403 E506 otherwise)"
        ),
    )

    @model_validator(mode="after")
    def _signing_policy(self) -> "ServiceSettings":
        if self.signing_key is None:
            if not self.allow_unsigned_for_tests:
                raise ValueError("a signing key is required unless allow_unsigned_for_tests is set")
        elif len(self.signing_key) < MIN_SIGNING_KEY_BYTES:
            raise ValueError(f"signing key must be at least {MIN_SIGNING_KEY_BYTES} bytes")
        return self

    @property
    def signs_results(self) -> bool:
        """True when results issued by this service carry an HMAC signature."""
        return self.signing_key is not None

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "ServiceSettings":
        """Build settings from ``env`` (default ``os.environ``).

        Raises :class:`SettingsError` naming the offending variable; the message never
        includes the variable's value.
        """
        source = os.environ if env is None else env
        token = source.get(f"{ENV_PREFIX}SERVICE_TOKEN")
        if not token:
            raise SettingsError(f"{ENV_PREFIX}SERVICE_TOKEN is required")
        key_hex = source.get(f"{ENV_PREFIX}SIGNING_KEY")
        if not key_hex:
            raise SettingsError(f"{ENV_PREFIX}SIGNING_KEY is required (hex text)")
        try:
            key = bytes.fromhex(key_hex.strip())
        except ValueError as exc:
            raise SettingsError(f"{ENV_PREFIX}SIGNING_KEY must be hex text") from exc
        values: dict[str, object] = {
            "service_token": token,
            "signing_key": key,
            "signing_key_id": source.get(f"{ENV_PREFIX}SIGNING_KEY_ID") or "default",
        }
        for name, var in (
            ("max_body_bytes", "MAX_BODY_BYTES"),
            ("max_concurrency", "MAX_CONCURRENCY"),
            ("rate_per_minute", "RATE_PER_MINUTE"),
        ):
            raw = source.get(f"{ENV_PREFIX}{var}")
            if raw is None or raw.strip() == "":
                continue
            try:
                values[name] = int(raw.strip(), 10)
            except ValueError as exc:
                raise SettingsError(f"{ENV_PREFIX}{var} must be an integer") from exc
        flag = source.get(f"{ENV_PREFIX}ALLOW_CLIENT_FIXTURES")
        if flag is not None and flag.strip() != "":
            word = flag.strip().lower()
            if word not in _TRUE_WORDS | _FALSE_WORDS:
                raise SettingsError(f"{ENV_PREFIX}ALLOW_CLIENT_FIXTURES must be one of: {', '.join(sorted(_TRUE_WORDS | _FALSE_WORDS))}")
            values["allow_client_fixtures"] = word in _TRUE_WORDS
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            fields = ", ".join(str(err["loc"][0]) if err.get("loc") else "settings" for err in exc.errors())
            raise SettingsError(f"invalid service settings: {fields}") from None
