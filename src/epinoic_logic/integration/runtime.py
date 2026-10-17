"""The integration service's runtime: the preflight facts, the passed self-test, the capabilities and the TurnChecker.

``build_runtime`` runs the preflight (every required part, ``KIT-HS`` codes) and the self-test (``KIT-HS-004``), then
builds the checks port. It is called only after the standard-library bootstrap has found Z3 (``KIT-HS-003``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .capabilities import build_capabilities
from .checks_port import RequestLimits
from .evidence_tap import EvidenceTap
from .preflight import Facts, Probes, run_preflight
from .protocol import dump
from .selftest import SelfTestOutcome, require_selftest
from .settings import IntegrationSettings
from .turn import CheckerConfig, TurnChecker
from .verifier import FixtureCorpus, PrefetchingProvider

__all__ = ["IntegrationRuntime", "build_runtime", "solver_config_for", "live_verifier", "PROVIDER_TIMEOUT_S"]

#: Per-call timeout of a live cheapest-tier provider (proposed; the provider classes' own default is 120 s).
PROVIDER_TIMEOUT_S = 20.0


def solver_config_for(profile: str) -> Any:
    """The solver configuration of a profile. The sim profile decides exactly as the arena harness does (its
    ``SolverConfig(timeout_ms=4000, memory_max_mb=None)``), so the equivalence gates compare like with like; the hosted
    profile keeps the engine's default (2000 ms per call, 512 MB per verification)."""
    from ..engine.results import SolverConfig
    if profile == "integration-sim":
        return SolverConfig(timeout_ms=4000, memory_max_mb=None)
    return SolverConfig()


def live_verifier(provider: str, *, config: Any, signing_key: bytes, key_id: str) -> Callable[..., Any]:
    """A task-aware verifier over a live cheapest-tier provider (the translator's own provider classes; the model id is
    the owner's configuration). Untested live: no provider call is evidenced anywhere."""
    from ..translate.outcome import verify_claim
    from ..translate.pipeline import Translator
    if provider == "anthropic":
        from ..translate.providers.anthropic_provider import AnthropicTranslationProvider as Provider
    elif provider == "openai_compatible":
        from ..translate.providers.openai_compatible import OpenAICompatibleTranslationProvider as Provider  # type: ignore[no-redef]
    else:
        raise ValueError("not a live provider")
    translator = Translator(PrefetchingProvider(Provider(timeout_s=PROVIDER_TIMEOUT_S)))

    def fn(claim: Any, report: Any, task: Any = None) -> Any:
        return verify_claim(claim, report, translator, config=config, signing_key=signing_key, key_id=key_id, task=task)
    return fn


@dataclass
class IntegrationRuntime:
    facts: Facts
    selftest: SelfTestOutcome
    checker: TurnChecker
    request_limits: RequestLimits

    def capabilities(self) -> dict:
        return build_capabilities(self.facts, self.selftest)


def build_runtime(settings: IntegrationSettings, *, probes: Optional[Probes] = None) -> IntegrationRuntime:
    facts = run_preflight(settings, probes)
    selftest = require_selftest(facts.keys.engine_key, facts.keys.engine_key_id)
    config = solver_config_for(settings.profile)
    corpus = None
    if facts.translation.provider == "fixture" and settings.fixture_dir:
        corpus = FixtureCorpus.load(settings.fixture_dir)
    live = (live_verifier(facts.translation.provider, config=config, signing_key=facts.keys.engine_key, key_id=facts.keys.engine_key_id)
            if facts.translation.live else None)
    tap = EvidenceTap(settings.evidence_dir, profile=settings.profile, host=settings.host) if settings.evidence_dir else None
    checker = TurnChecker(
        CheckerConfig(service_env=settings.service_env, versions=dump(facts.versions), build=dump(facts.build),
                      subject_map_sha256=facts.subject_map.sha256, overseer_mode=facts.overseer.mode,
                      engine_key=facts.keys.engine_key, engine_key_id=facts.keys.engine_key_id,
                      verdict_key=facts.keys.verdict_key, verdict_key_id=facts.keys.verdict_key_id, solver_config=config,
                      max_translated_claims=facts.limits.max_translated_claims, live_provider=facts.translation.live,
                      review_async=facts.overseer.agents == "async", review_profiles=tuple(facts.overseer.profiles)),
        port=facts.overseer_port, corpus=corpus, live_verifier=live, router=facts.router, evidence_tap=tap)
    limits = RequestLimits(modes=facts.modes, max_body_bytes=facts.limits.max_body_bytes, checks_min_ms=facts.limits.checks_min_ms,
                           checks_max_ms=facts.limits.checks_max_ms)
    return IntegrationRuntime(facts=facts, selftest=selftest, checker=checker, request_limits=limits)
