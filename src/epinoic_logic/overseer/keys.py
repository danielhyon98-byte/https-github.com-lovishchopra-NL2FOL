"""Keys of the Overseer: engine keys for verification only, and one overseer secret.

* **Engine keys** are declared by key id, each ``local`` (the engine path in this process signs under it)
  or ``external`` (results signed elsewhere and verified at citation time). The auditor holds them to
  VERIFY engine results and never signs with one (trust rule TR5).
* **The overseer secret** is one configured secret; it must be at least 32 bytes and must differ from
  every engine key (checked at construction). Labelled subkeys are derived from it with HMAC-SHA256:
  ``journal`` (journal entry MACs), ``audit`` (signed audits), ``runs`` (the auditor's own engine runs,
  key id ``overseer-run``), ``sampling`` (keyed replay sampling) and ``intake`` (verdict envelopes). One
  secret to provision, with domain separation between every use.

No key ever appears in a repr, a dossier, a verdict, a report or a log message.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal, Mapping, Optional, Union

from ..engine.provenance import verify_signature
from ..engine.results import VerificationResult

__all__ = ["EngineKey", "KeyRing", "KeyStatus", "SUBKEY_LABELS", "RUN_KEY_ID", "AUDIT_KEY_ID", "INTAKE_KEY_ID", "MIN_SECRET_BYTES", "AUDITOR_KEY_IDS"]

SUBKEY_LABELS = ("journal", "audit", "runs", "sampling", "intake")
RUN_KEY_ID = "overseer-run"
AUDIT_KEY_ID = "overseer-audit"
INTAKE_KEY_ID = "overseer-intake"
AUDITOR_KEY_IDS = frozenset({RUN_KEY_ID, AUDIT_KEY_ID, INTAKE_KEY_ID})
MIN_SECRET_BYTES = 32
KeyStatus = Literal["local", "external", "auditor", "unknown"]


@dataclass(frozen=True)
class EngineKey:
    """An engine key declared under one key id. ``secret`` may be ``None``: the key id is declared but no secret
    is configured (results under it are reported AUDIT-004, never passed)."""
    secret: Optional[bytes]
    scope: Literal["local", "external"] = "local"

    def __repr__(self) -> str:  # never print a secret
        return f"EngineKey(scope={self.scope!r}, configured={self.secret is not None})"


def _derive(secret: bytes, label: str) -> bytes:
    return hmac.new(secret, f"epinoic-overseer/{label}/v1".encode("utf-8"), hashlib.sha256).digest()


class KeyRing:
    """Engine keys by key id (verification only) and the overseer secret's derived subkeys."""

    __slots__ = ("_engine", "_sub")

    def __init__(self, engine_keys: Mapping[str, Union[EngineKey, bytes, None]], overseer_secret: bytes) -> None:
        if not isinstance(overseer_secret, (bytes, bytearray)) or len(overseer_secret) < MIN_SECRET_BYTES:
            raise ValueError(f"the overseer secret must be at least {MIN_SECRET_BYTES} bytes")
        engine: dict[str, EngineKey] = {}
        for kid, k in dict(engine_keys).items():
            if not isinstance(kid, str) or not kid:
                raise ValueError("engine key ids must be non-empty strings")
            if kid in AUDITOR_KEY_IDS:
                raise ValueError(f"key id {kid!r} is reserved for the Overseer's own signatures")
            ek = k if isinstance(k, EngineKey) else EngineKey(secret=bytes(k) if k is not None else None)
            if ek.secret is not None and len(ek.secret) == 0:
                raise ValueError(f"engine key {kid!r} is empty")
            engine[kid] = ek
        secret = bytes(overseer_secret)
        for kid, ek in engine.items():
            if ek.secret is not None and hmac.compare_digest(ek.secret, secret):
                raise ValueError(f"the overseer secret must differ from every engine key (it equals the key of {kid!r})")
        sub = {label: _derive(secret, label) for label in SUBKEY_LABELS}
        for kid, ek in engine.items():
            if ek.secret is not None and any(hmac.compare_digest(ek.secret, s) for s in sub.values()):
                raise ValueError(f"engine key {kid!r} equals an overseer subkey")
        self._engine = engine
        self._sub = sub

    def __repr__(self) -> str:
        return f"KeyRing(engine_key_ids={sorted(self._engine)}, subkeys={list(SUBKEY_LABELS)})"

    def __reduce__(self):  # never pickled into a worker process or a log
        raise TypeError("a KeyRing is not serialisable")

    # ------------------------------------------------------------------ engine keys (verification only)
    @property
    def engine_key_ids(self) -> list[str]:
        return sorted(self._engine)

    def is_declared(self, key_id: Optional[str]) -> bool:
        return key_id is not None and key_id in self._engine

    def key_status(self, key_id: Optional[str]) -> KeyStatus:
        if key_id == RUN_KEY_ID:
            return "auditor"
        ek = self._engine.get(key_id or "")
        return ek.scope if ek is not None else "unknown"

    def has_secret(self, key_id: Optional[str]) -> bool:
        if key_id == RUN_KEY_ID:
            return True
        ek = self._engine.get(key_id or "")
        return ek is not None and ek.secret is not None

    def verification_key(self, key_id: Optional[str]) -> Optional[bytes]:
        """The secret to VERIFY a result signed under ``key_id`` (an engine key, or the runs subkey for
        ``overseer-run``). Never pass it as a signing key: the auditor signs only under its own subkeys."""
        if key_id == RUN_KEY_ID:
            return self._sub["runs"]
        ek = self._engine.get(key_id or "")
        return ek.secret if ek is not None else None

    def verify_result(self, result: VerificationResult) -> tuple[bool, str]:
        """``(signature ok, reason)`` for an engine or auditor result: unsigned, undeclared key id, declared without a
        secret, or HMAC mismatch."""
        if not result.signature:
            return False, "unsigned"
        kid = result.signature_key_id
        if kid != RUN_KEY_ID and not self.is_declared(kid):
            return False, f"signed under the undeclared key id {kid!r}"
        key = self.verification_key(kid)
        if key is None:
            return False, f"no verification key is configured for the declared key id {kid!r}"
        if not verify_signature(result, key):
            return False, f"the signature does not verify under key id {kid!r}"
        return True, "ok"

    # ------------------------------------------------------------------ the Overseer's own subkeys
    def subkey(self, label: str) -> bytes:
        if label not in self._sub:
            raise KeyError(f"unknown subkey label {label!r}")
        return self._sub[label]

    def mac(self, label: str, text: str) -> str:
        return hmac.new(self.subkey(label), text.encode("utf-8", errors="surrogatepass"), hashlib.sha256).hexdigest()

    def mac_ok(self, label: str, text: str, mac: Optional[str]) -> bool:
        return isinstance(mac, str) and hmac.compare_digest(self.mac(label, text), mac)

    def sample_fraction(self, result_id: str) -> float:
        """``HMAC(sampling key, result_id)`` read as a fraction in [0, 1): reproducible by the auditor, unpredictable
        to anyone without the key."""
        digest = hmac.new(self._sub["sampling"], result_id.encode("utf-8", errors="surrogatepass"), hashlib.sha256).digest()
        return int.from_bytes(digest[:8], "big") / float(1 << 64)
