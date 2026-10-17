"""Configuration of the integration profiles, read from the environment by name (``integration/PROTOCOL.md`` section 3).

Profiles: ``engine`` (the default of ``epinoic-logic serve``: today's service exactly, no new route), ``integration``
(the checks port on a hosted environment) and ``integration-sim`` (the local simulation on a loopback bind, with the
fixture translation provider and the evidence tap). This module only READS the variables; every rule is applied by
``preflight`` in its fixed order, so a refusal always names the first missing part with its ``KIT-HS`` code.

Environment variables (names only; values are never logged, printed or returned, and secrets are kept out of ``repr``):

==================================  =====================================================================================
``EPINOIC_PROFILE``                 ``engine`` | ``integration`` | ``integration-sim``
``EPINOIC_SERVICE_ENV``             ``development`` | ``staging`` | ``production`` | ``sim`` (the handshake compares it)
``EPINOIC_SERVICE_TOKEN``           bearer token of the Worker (at least 16 characters)
``EPINOIC_SIGNING_KEY``             engine signing key, hex, at least 32 bytes; ``EPINOIC_SIGNING_KEY_ID`` (``default``)
``EPINOIC_VERDICT_KEY``             verdict key, hex, at least 32 bytes, distinct; ``EPINOIC_VERDICT_KEY_ID`` (``verdict``)
``EPINOIC_OVERSEER_SECRET``         overseer secret, hex, at least 32 bytes, distinct from both keys
``EPINOIC_OVERSEER_PORT``           the overseer port adapter module (default ``epinoic_overseer.port``)
``EPINOIC_OVERSEER_AGENTS``         ``off`` (default) | ``async``: the asynchronous overseer-agent review
``EPINOIC_FLASH_ROUTER``            the flash-router module (default ``epinoic_flash_router.port``; ``none`` for none)
``EPINOIC_COMBINATOR``              ``none`` (default): no combinator is connected, so the mode ``combined`` is omitted
``EPINOIC_TRANSLATION_PROVIDER``    ``fixture`` | ``anthropic`` | ``openai_compatible`` (the cheapest tier)
``EPINOIC_FIXTURE_DIR``             the fixture provider's translations (arena round format)
``EPINOIC_CHECKS_MIN_MS``           smallest checks budget accepted (default 3000)
``EPINOIC_CHECKS_MAX_MS``           largest checks budget accepted (default 65000)
``EPINOIC_MAX_BODY_BYTES``          request body limit (default 1000000)
``EPINOIC_MAX_CONCURRENCY``         turn-check slots (default 4)
``EPINOIC_RATE_PER_MINUTE``         per-token rate (default 60)
``EPINOIC_SIM_EVIDENCE_DIR``        the evidence tap's directory (``integration-sim`` only)
==================================  =====================================================================================

A model identifier is never set here: it is read by the provider classes from their own variables
(``EPINOIC_ANTHROPIC_MODEL``; ``EPINOIC_OPENAI_MODEL`` with ``EPINOIC_OPENAI_BASE_URL``) and set by the owner.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

__all__ = ["PROFILES", "INTEGRATION_PROFILES", "IntegrationSettings", "LOOPBACK_HOSTS"]

PROFILES = ("engine", "integration", "integration-sim")
INTEGRATION_PROFILES = ("integration", "integration-sim")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_SECRET_NAMES = ("service_token", "signing_key_hex", "verdict_key_hex", "overseer_secret_hex")


@dataclass(frozen=True)
class IntegrationSettings:
    profile: str
    service_env: str
    host: str
    service_token: Optional[str] = field(default=None, repr=False)
    signing_key_hex: Optional[str] = field(default=None, repr=False)
    signing_key_id: str = "default"
    verdict_key_hex: Optional[str] = field(default=None, repr=False)
    verdict_key_id: str = "verdict"
    overseer_secret_hex: Optional[str] = field(default=None, repr=False)
    overseer_port: str = "epinoic_overseer.port"
    overseer_agents: str = "off"
    flash_router: str = "epinoic_flash_router.port"
    combinator: str = "none"
    translation_provider: Optional[str] = None
    fixture_dir: Optional[str] = None
    checks_min_ms: str = "3000"
    checks_max_ms: str = "65000"
    max_body_bytes: str = "1000000"
    max_concurrency: str = "4"
    rate_per_minute: str = "60"
    evidence_dir: Optional[str] = None
    anthropic_model_set: bool = False
    openai_model_set: bool = False

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, *, host: str = "127.0.0.1") -> "IntegrationSettings":
        e = os.environ if env is None else env

        def get(name: str, default: Optional[str] = None) -> Optional[str]:
            value = e.get(f"EPINOIC_{name}")
            return default if value is None or value.strip() == "" else value.strip()

        profile = get("PROFILE", "integration") or "integration"
        return cls(
            profile=profile,
            service_env=get("SERVICE_ENV", "sim" if profile == "integration-sim" else "development") or "",
            host=host,
            service_token=get("SERVICE_TOKEN"),
            signing_key_hex=get("SIGNING_KEY"),
            signing_key_id=get("SIGNING_KEY_ID", "default") or "default",
            verdict_key_hex=get("VERDICT_KEY"),
            verdict_key_id=get("VERDICT_KEY_ID", "verdict") or "verdict",
            overseer_secret_hex=get("OVERSEER_SECRET"),
            overseer_port=get("OVERSEER_PORT", "epinoic_overseer.port") or "",
            overseer_agents=get("OVERSEER_AGENTS", "off") or "off",
            flash_router=get("FLASH_ROUTER", "epinoic_flash_router.port") or "none",
            combinator=get("COMBINATOR", "none") or "none",
            translation_provider=get("TRANSLATION_PROVIDER", "fixture" if profile == "integration-sim" else None),
            fixture_dir=get("FIXTURE_DIR"),
            checks_min_ms=get("CHECKS_MIN_MS", "3000") or "3000",
            checks_max_ms=get("CHECKS_MAX_MS", "65000") or "65000",
            max_body_bytes=get("MAX_BODY_BYTES", "1000000") or "1000000",
            max_concurrency=get("MAX_CONCURRENCY", "4") or "4",
            rate_per_minute=get("RATE_PER_MINUTE", "60") or "60",
            evidence_dir=get("SIM_EVIDENCE_DIR"),
            anthropic_model_set=bool(get("ANTHROPIC_MODEL")),
            openai_model_set=bool(get("OPENAI_MODEL")) and bool(get("OPENAI_BASE_URL")),
        )

    def describe(self) -> dict:
        """Settings for an operator: names and non-secret values only (each secret as present or absent)."""
        out = {k: v for k, v in self.__dict__.items() if k not in _SECRET_NAMES}
        out.update({f"{k}_present": getattr(self, k) is not None for k in _SECRET_NAMES})
        return out
