"""The Worker's handshake rules, mirrored in Python (``integration/PROTOCOL.md`` section 3, check 4).

The Worker (``integration/website/src/verify/verification.js``) accepts a capabilities response only when it is less
than 60 s old, matches the pinned compatibility set and reports a passed self-test. This module states the same rules
over the same golden vectors (``integration/vectors/handshake/``), so both sides refuse the same responses with the same
code. The flash router is reported, never required: its absence changes nothing here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import ValidationError

from .compat import COMPATIBILITY
from .protocol import PROTOCOL, Capabilities, dump

__all__ = ["HandshakeOutcome", "evaluate"]


@dataclass(frozen=True)
class HandshakeOutcome:
    ok: bool
    code: Optional[str]
    detail: str
    router: Optional[dict] = None

    @property
    def raw_code(self) -> Optional[str]:
        """The Worker's stored raw code for this outcome (``kit_hs_mismatch`` for every refused response)."""
        return None if self.ok else "kit_hs_mismatch"


def _refuse(code: str, detail: str, router: Optional[dict] = None) -> HandshakeOutcome:
    return HandshakeOutcome(False, code, detail, router)


def evaluate(raw: Any, *, worker_env: str, base: str = "M") -> HandshakeOutcome:
    """Evaluate one capabilities response as the Worker of environment ``worker_env`` on website base ``base`` would."""
    if not isinstance(raw, dict) or raw.get("protocol") != PROTOCOL or raw.get("schema") != "epinoic.integration.capabilities.v1":
        return _refuse("KIT-HS-001", "not an epinoic.integration.v1 capabilities response")
    try:
        caps = Capabilities.model_validate(raw)
    except ValidationError as exc:
        return _refuse("KIT-HS-001", f"the capabilities response does not validate ({exc.error_count()} error(s))")
    router = dump(caps.ports.router)
    accepted = COMPATIBILITY["components"]
    for name in ("ir", "engine", "policy", "translator", "contract"):
        if getattr(caps.versions, name) not in accepted[name]:
            return _refuse("KIT-HS-002", f"{name} version {getattr(caps.versions, name)} is not accepted", router)
    if not caps.selftest.passed:
        return _refuse("KIT-HS-004", "the service's self-test did not pass", router)
    if sorted(caps.ports.checks.stem.branches) != sorted(COMPATIBILITY["stem_branches"]):
        return _refuse("KIT-HS-005", "the STEM branches are not all present", router)
    if sorted(caps.ports.checks.named_policies) != sorted(COMPATIBILITY["named_policies"]):
        return _refuse("KIT-HS-006", "the named policies are not linear, nonlinear and joint", router)
    ov = caps.ports.overseer
    if ov.mode not in COMPATIBILITY["overseer"]["modes"] or ov.replay_mode != "process" or ov.inline_final_release:
        return _refuse("KIT-HS-007", "the overseer is not the admitted embedded mode", router)
    live_required = worker_env in ("staging", "production")
    if live_required and not caps.ports.translation.live:
        return _refuse("KIT-HS-009", "a hosted environment requires a live translation provider", router)
    if not live_required and caps.ports.translation.live and worker_env == "sim":
        return _refuse("KIT-HS-009", "the sim environment requires the fixture provider", router)
    if caps.subject_map.sha256 != COMPATIBILITY["subject_map"]["sha256"]:
        return _refuse("KIT-HS-010", "the subject maps differ", router)
    pairs = sorted((p.result, p.runtime) for p in caps.ports.specialist.accepted)
    if pairs != sorted((p["result"], p["runtime"]) for p in COMPATIBILITY["specialist_pairs"]):
        return _refuse("KIT-HS-011", "the accepted specialist contracts differ", router)
    if caps.service_env != worker_env:
        return _refuse("KIT-HS-012", "the service's environment label is not the Worker's", router)
    lim = COMPATIBILITY["limits"]
    if (caps.limits.max_body_bytes < lim["worker_max_request_bytes"] or caps.limits.max_answer_bytes < lim["max_answer_bytes"]
            or "single" not in caps.ports.checks.modes):
        return _refuse("KIT-HS-013", "the service's limits cannot carry the Worker's largest request", router)
    timing = COMPATIBILITY["timing"]
    b = timing["bases"].get(base)
    if b is None or b["specialist_ceiling_ms"] + caps.limits.checks_min_ms + b["checks_tail_ms"] + timing["completion_reserve_ms"] > b["deadline_ms"]:
        return _refuse("KIT-HS-016", "the timing invariant fails for this base's deadline", router)
    return HandshakeOutcome(True, None, "compatible", router)
