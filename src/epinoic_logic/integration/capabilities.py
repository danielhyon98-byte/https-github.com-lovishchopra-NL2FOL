"""The capabilities document ``GET /v1/capabilities`` returns (``integration/PROTOCOL.md`` section 3, check 2).

Built once at start-up from the preflight facts and the self-test, re-stamped with ``issued_at`` on every request. It
carries no secret: key ids only, never keys. The flash router is reported (identity, version, rules digest, or absent
with the reason) but is never required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .preflight import Facts
from .protocol import (
    PROTOCOL, Capabilities, ChecksPortCaps, OverseerPortCaps, Ports, SelfTestReport, Signing, dump,
)
from .selftest import SelfTestOutcome

__all__ = ["build_capabilities", "utc_now"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_capabilities(facts: Facts, selftest: SelfTestOutcome, *, issued_at: Optional[str] = None) -> dict:
    hello = facts.overseer
    ports = Ports(
        specialist=facts.specialist,
        checks=ChecksPortCaps(version="1.0", modes=list(facts.modes), named_policies=list(facts.named_policies), stem=facts.stem),
        overseer=OverseerPortCaps(version="1.0", mode=hello.mode, auditor_version=hello.auditor_version, pack_digests=list(hello.pack_digests),
                                  replay_mode="process", inline_final_release=False, agents=hello.agents, profiles=list(hello.profiles)),
        translation=facts.translation,
        combinator=facts.combinator,
        router=facts.router_caps,
    )
    caps = Capabilities(
        schema="epinoic.integration.capabilities.v1", protocol=PROTOCOL, service_env=facts.settings.service_env,
        versions=facts.versions, build=facts.build,
        selftest=SelfTestReport(passed=selftest.passed, digests=list(selftest.binding_digests)),
        ports=ports, subject_map=facts.subject_map, policies=["verified-v1", "verified-v1-qualify"], limits=facts.limits,
        signing=Signing(verdict_alg="hmac-sha256", verdict_key_id=facts.keys.verdict_key_id, engine_key_id=facts.keys.engine_key_id),
        issued_at=issued_at or utc_now(),
    )
    return dump(caps)
