"""The start-up preflight (``integration/PROTOCOL.md`` section 3, check 1): every required part, checked in a fixed order
before the service binds a socket. The first missing part refuses with its ``KIT-HS`` code (one line, no secret, exit
status 2 in ``__main__``). Z3 itself is checked earlier, by the standard-library bootstrap (``KIT-HS-003``).

Order: the profile (012), the component versions (002), the STEM branches and the ``nonlinear`` policy (005), the named
policies of contract 0.3 (006), the credentials (008), the overseer port and its pinned pack (007), the translation
provider (009), the subject map (010), the specialist contracts (011), the environment (012), the limits (013) and the
timing figures (016). The flash router and the combinator are never required: they are reported, not refused.

Each part is read by a probe method (:class:`Probes`); tests replace one probe at a time to show that each part, and only
that part, gives its code. The probes for parts that other work streams are still building (the named policies, the
overseer port adapter) look for the real interfaces and refuse when they are absent: nothing here stands in for them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .compat import COMPATIBILITY, SUBJECT_MAP, SUBJECT_MAP_SHA256
from .errors import IntegrationError
from .overseer_port import OverseerHello, OverseerPort, load_port
from .protocol import (
    INTEGRATION_CONTRACT_VERSION, BuildIdentity, CombinatorPortCaps, ComponentVersions, RouterPortCaps, ServiceLimits,
    SpecialistPair, SpecialistPortCaps, StemCaps, SubjectMapRef, TranslationCaps,
)
from .router_port import FLOOR_REF, RouterAttachment, attach_router
from .settings import INTEGRATION_PROFILES, LOOPBACK_HOSTS, IntegrationSettings

__all__ = ["Keys", "Facts", "Probes", "run_preflight", "MIN_KEY_BYTES", "MIN_TOKEN_CHARS"]

MIN_KEY_BYTES = 32
MIN_TOKEN_CHARS = 16
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_STEM_BRANCHES = tuple(COMPATIBILITY["stem_branches"])
_NAMED_POLICIES = tuple(COMPATIBILITY["named_policies"])


@dataclass(frozen=True)
class Keys:
    service_token: str = field(repr=False)
    engine_key: bytes = field(repr=False)
    engine_key_id: str = "default"
    verdict_key: bytes = field(default=b"", repr=False)
    verdict_key_id: str = "verdict"
    overseer_secret: bytes = field(default=b"", repr=False)


@dataclass(frozen=True)
class Facts:
    settings: IntegrationSettings
    versions: ComponentVersions
    build: BuildIdentity
    stem: StemCaps
    named_policies: tuple[str, ...]
    keys: Keys
    overseer: OverseerHello
    overseer_port: Any = field(repr=False)
    translation: TranslationCaps = None  # type: ignore[assignment]
    subject_map: SubjectMapRef = None  # type: ignore[assignment]
    specialist: SpecialistPortCaps = None  # type: ignore[assignment]
    limits: ServiceLimits = None  # type: ignore[assignment]
    rate_per_minute: int = 60
    router: RouterAttachment = None  # type: ignore[assignment]
    router_caps: RouterPortCaps = None  # type: ignore[assignment]
    combinator: CombinatorPortCaps = None  # type: ignore[assignment]
    modes: tuple[str, ...] = ("single",)


def _hex_key(value: Optional[str], name: str, code: str) -> bytes:
    if not value:
        raise IntegrationError(code, f"{name} is not set")
    try:
        key = bytes.fromhex(value)
    except ValueError:
        raise IntegrationError(code, f"{name} is not hex text") from None
    if len(key) < MIN_KEY_BYTES:
        raise IntegrationError(code, f"{name} is shorter than {MIN_KEY_BYTES} bytes")
    return key


def _int(value: str, name: str, code: str) -> int:
    try:
        return int(str(value).strip(), 10)
    except ValueError:
        raise IntegrationError(code, f"{name} is not an integer") from None


class Probes:
    """Reads each required part from the code and the configuration. Every method returns its facts or raises
    :class:`IntegrationError` with its code."""

    def versions(self) -> tuple[ComponentVersions, BuildIdentity]:
        from ..engine.provenance import compute_versions
        from ..version import TRANSLATOR_VERSION
        v = compute_versions()
        versions = ComponentVersions(ir=v.ir_version, engine=v.engine_version, policy=v.policy_version, translator=TRANSLATOR_VERSION,
                                     z3=v.z3_version, contract=INTEGRATION_CONTRACT_VERSION)
        accepted = COMPATIBILITY["components"]
        for name in ("ir", "engine", "policy", "translator", "contract"):
            if getattr(versions, name) not in accepted[name]:
                raise IntegrationError("KIT-HS-002", f"{name} version {getattr(versions, name)} is not in COMPATIBILITY.json")
        return versions, BuildIdentity(build_id=v.build_id, schema_id=v.schema_id, policy_id=v.policy_id)

    def stem(self) -> StemCaps:
        try:
            from ..branches.registry import default_registry
            from ..branches.stem_pack import StemPack
            from ..channel.bus import STEM_CHECK_BUDGET_S
            from ..engine.policies import PACK_POLICIES
            from ..stem import checks as _stem_checks  # noqa: F401 - the STEM front end must import
        except Exception as exc:  # noqa: BLE001
            raise IntegrationError("KIT-HS-005", f"the STEM front end cannot be imported ({type(exc).__name__})") from None
        reg = default_registry()
        for key in _STEM_BRANCHES:
            if key not in reg.keys():
                raise IntegrationError("KIT-HS-005", f"the STEM branch {key} is missing")
            branch = reg.get(key)
            if not any(isinstance(p, StemPack) for p in branch.packs) or branch.hub_hooks is None:
                raise IntegrationError("KIT-HS-005", f"the STEM branch {key} has no STEM pack or hooks")
        if "nonlinear" not in PACK_POLICIES:
            raise IntegrationError("KIT-HS-005", "the nonlinear policy of the STEM checks is missing")
        return StemCaps(branches=list(_STEM_BRANCHES), report_budget_max_s=int(STEM_CHECK_BUDGET_S))

    def named_policies(self) -> tuple[str, ...]:
        from ..engine import policies
        table = getattr(policies, "NAMED_POLICIES", None)
        resolver = getattr(policies, "named_policy", None)
        if table is None or not callable(resolver) or sorted(table) != sorted(_NAMED_POLICIES):
            raise IntegrationError("KIT-HS-006", "the engine has no named-policy allowlist (linear, nonlinear, joint): its contract is older than 0.3")
        return tuple(sorted(table))

    def overseer(self, settings: IntegrationSettings, keys: Keys) -> tuple[OverseerHello, OverseerPort]:
        # load_port validates the hello once and returns it with the port: every failure in there is KIT-HS-007.
        return load_port(settings.overseer_port, {
            "engine_key": keys.engine_key, "engine_key_id": keys.engine_key_id, "overseer_secret": keys.overseer_secret,
            "replay_mode": "process", "agents": settings.overseer_agents,
        })

    def subject_map(self) -> SubjectMapRef:
        from .canonical import sha256_json
        from .compat import thaw
        from ..branches import RouterHub
        if sha256_json(thaw(SUBJECT_MAP)) != SUBJECT_MAP_SHA256 or SUBJECT_MAP_SHA256 != COMPATIBILITY["subject_map"]["sha256"]:
            raise IntegrationError("KIT-HS-010", "the subject map is not the one COMPATIBILITY.json pins")
        hub = RouterHub(signing_key=b"subject-map-probe-key-not-a-secret")
        for e in SUBJECT_MAP["entries"]:
            if hub.branch_for(e["subject"]) != e["branch"]:
                raise IntegrationError("KIT-HS-010", f"the subject {e['subject']!r} routes to another branch than the map says")
        return SubjectMapRef(version=SUBJECT_MAP["version"], sha256=SUBJECT_MAP_SHA256)

    def specialist_contracts(self) -> SpecialistPortCaps:
        pairs = COMPATIBILITY.get("specialist_pairs") or ()
        known = {("epinoic.specialist-turn-result.v1", "epinoic.specialist-runtime.v0.1.0"),
                 ("epinoic.specialist-turn-result.v2", "epinoic.specialist-runtime.v0.2.0")}
        if not pairs or any((p["result"], p["runtime"]) not in known for p in pairs):
            raise IntegrationError("KIT-HS-011", "the accepted specialist pairs are not the known runtime contracts")
        return SpecialistPortCaps(version="1.0", accepted=[SpecialistPair(result=p["result"], runtime=p["runtime"], log=p["log"]) for p in pairs])

    def router(self, settings: IntegrationSettings) -> RouterAttachment:
        # The hosted profile holds real keys: it starts a router only where the router's process cannot read them
        # (router_child.boundary_problem). The loopback simulation runs with ephemeral test keys and attaches it anyway.
        return attach_router(settings.flash_router, require_secret_boundary=settings.profile == "integration")

    def combinator(self, settings: IntegrationSettings) -> CombinatorPortCaps:
        # The combinator's v1 implementation (a provider call with a pinned instruction pack) is connected in phase 2;
        # until then the port reports itself unavailable and the checks port omits the mode "combined".
        return CombinatorPortCaps(version="1.0", available=False, instruction_pack=None)


def _provider(settings: IntegrationSettings) -> TranslationCaps:
    provider = settings.translation_provider
    if provider not in ("fixture", "anthropic", "openai_compatible"):
        raise IntegrationError("KIT-HS-009", "EPINOIC_TRANSLATION_PROVIDER is not fixture, anthropic or openai_compatible")
    live = provider != "fixture"
    if settings.profile == "integration-sim" and live:
        raise IntegrationError("KIT-HS-009", "the sim profile translates with the fixture provider only")
    if settings.profile == "integration" and settings.service_env in ("staging", "production") and not live:
        raise IntegrationError("KIT-HS-009", "a hosted environment translates with a live provider of the cheapest tier")
    if provider == "anthropic" and not settings.anthropic_model_set:
        raise IntegrationError("KIT-HS-009", "EPINOIC_ANTHROPIC_MODEL is not set (the owner sets the cheapest tier's model id)")
    if provider == "openai_compatible" and not settings.openai_model_set:
        raise IntegrationError("KIT-HS-009", "EPINOIC_OPENAI_MODEL and EPINOIC_OPENAI_BASE_URL are not both set")
    return TranslationCaps(provider=provider, tier="cheapest", live=live, reviewer="none")


def _environment(settings: IntegrationSettings) -> None:
    env = settings.service_env
    if env not in ("development", "staging", "production", "sim"):
        raise IntegrationError("KIT-HS-012", "EPINOIC_SERVICE_ENV is not development, staging, production or sim")
    if settings.profile == "integration-sim":
        if env != "sim":
            raise IntegrationError("KIT-HS-012", "the sim profile runs only as the sim environment")
        if settings.host not in LOOPBACK_HOSTS:
            raise IntegrationError("KIT-HS-012", "the sim profile binds a loopback address only")
    elif env == "sim":
        raise IntegrationError("KIT-HS-012", "the sim environment runs only under the integration-sim profile")
    if settings.evidence_dir is not None and settings.profile != "integration-sim":
        raise IntegrationError("KIT-HS-012", "the evidence tap is configured outside the integration-sim profile")


def run_preflight(settings: IntegrationSettings, probes: Optional[Probes] = None) -> Facts:
    p = probes if probes is not None else Probes()
    if settings.profile not in INTEGRATION_PROFILES:
        raise IntegrationError("KIT-HS-012", "the integration entry point runs only under the integration or integration-sim profile")
    versions, build = p.versions()
    stem = p.stem()
    named = p.named_policies()
    # Credentials (008), before the overseer port, whose connection needs the engine key and the overseer secret.
    if not settings.service_token or len(settings.service_token) < MIN_TOKEN_CHARS:
        raise IntegrationError("KIT-HS-008", f"EPINOIC_SERVICE_TOKEN is missing or shorter than {MIN_TOKEN_CHARS} characters")
    engine_key = _hex_key(settings.signing_key_hex, "EPINOIC_SIGNING_KEY", "KIT-HS-008")
    verdict_key = _hex_key(settings.verdict_key_hex, "EPINOIC_VERDICT_KEY", "KIT-HS-008")
    if verdict_key == engine_key:
        raise IntegrationError("KIT-HS-008", "the verdict key equals the engine signing key")
    for name, kid in (("EPINOIC_SIGNING_KEY_ID", settings.signing_key_id), ("EPINOIC_VERDICT_KEY_ID", settings.verdict_key_id)):
        if not _KEY_ID_RE.match(kid):
            raise IntegrationError("KIT-HS-008", f"{name} is not a key id")
    overseer_secret = _hex_key(settings.overseer_secret_hex, "EPINOIC_OVERSEER_SECRET", "KIT-HS-007")
    if overseer_secret in (engine_key, verdict_key):
        raise IntegrationError("KIT-HS-007", "the overseer secret equals an engine or verdict key")
    keys = Keys(service_token=settings.service_token, engine_key=engine_key, engine_key_id=settings.signing_key_id,
                verdict_key=verdict_key, verdict_key_id=settings.verdict_key_id, overseer_secret=overseer_secret)
    hello, port = p.overseer(settings, keys)
    translation = _provider(settings)
    subject_map = p.subject_map()
    specialist = p.specialist_contracts()
    _environment(settings)
    body = _int(settings.max_body_bytes, "EPINOIC_MAX_BODY_BYTES", "KIT-HS-013")
    slots = _int(settings.max_concurrency, "EPINOIC_MAX_CONCURRENCY", "KIT-HS-013")
    rate = _int(settings.rate_per_minute, "EPINOIC_RATE_PER_MINUTE", "KIT-HS-013")
    lim = COMPATIBILITY["limits"]
    if not lim["worker_max_request_bytes"] <= body <= 50_000_000 or not 1 <= slots <= 256 or not 1 <= rate <= 100_000:
        raise IntegrationError("KIT-HS-013", "the body limit cannot carry the Worker's largest request, or the slots or rate are out of range")
    cmin = _int(settings.checks_min_ms, "EPINOIC_CHECKS_MIN_MS", "KIT-HS-016")
    cmax = _int(settings.checks_max_ms, "EPINOIC_CHECKS_MAX_MS", "KIT-HS-016")
    timing = COMPATIBILITY["timing"]
    base_m = timing["bases"]["M"]
    if not 1000 <= cmin <= cmax <= 600_000:
        raise IntegrationError("KIT-HS-016", "the checks budget range is empty or outside 1 s to 10 min")
    if base_m["specialist_ceiling_ms"] + cmin + base_m["checks_tail_ms"] + timing["completion_reserve_ms"] > base_m["deadline_ms"]:
        raise IntegrationError("KIT-HS-016", "the smallest checks budget does not fit base M's deadline")
    limits = ServiceLimits(max_body_bytes=body, max_answer_bytes=lim["max_answer_bytes"], max_answers=lim["max_answers"],
                           max_translated_claims=lim["max_translated_claims"], checks_min_ms=cmin, checks_max_ms=cmax, turn_slots=slots)
    router = p.router(settings)
    router_caps = RouterPortCaps(version="1.0", required=False, attached=router.attached,
                                 identity=router.hello.router if router.hello is not None else None, refusal=router.refusal, floor=FLOOR_REF)
    combinator = p.combinator(settings)
    modes = ("single", "duplicate") + (("combined",) if combinator.available else ())
    return Facts(settings=settings, versions=versions, build=build, stem=stem, named_policies=named, keys=keys, overseer=hello,
                 overseer_port=port, translation=translation, subject_map=subject_map, specialist=specialist, limits=limits,
                 rate_per_minute=rate, router=router, router_caps=router_caps, combinator=combinator, modes=modes)
