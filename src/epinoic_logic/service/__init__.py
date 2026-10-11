"""Authenticated HTTP service boundary around the verification engine.

``create_app`` builds the FastAPI application; ``ServiceSettings`` holds its
validated configuration (see :mod:`epinoic_logic.service.settings` for the
environment variables). The service never exposes the solver without a bearer
token, signs every result it issues, rejects client-asserted verification status,
and bounds body size, concurrency and request rate.
"""
from .settings import ServiceSettings, SettingsError  # noqa: F401
from .app import REQUEST_ID_HEADER, SELF_CERTIFICATION_KEYS, TokenBucketLimiter, create_app  # noqa: F401

__all__ = [
    "ServiceSettings",
    "SettingsError",
    "REQUEST_ID_HEADER",
    "SELF_CERTIFICATION_KEYS",
    "TokenBucketLimiter",
    "create_app",
]
