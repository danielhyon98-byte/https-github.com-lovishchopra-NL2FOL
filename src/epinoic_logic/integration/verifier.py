"""The checks port's claim verifier: cheapest-tier translation through the translator's own provider classes, bounded by
the call's budget (``integration/PROTOCOL.md`` section 5.3).

* :class:`BudgetedVerifier` wraps the channel's ``verify_claim_fn``: once the call's monotonic deadline has passed it
  returns ``None`` for the remaining claims (the channel then records no outcome for them), it caps the number of claims
  sent to a live provider at ``max_translated_claims``, and it records why each claim it did not verify has no outcome
  (``skipped_budget``, ``skipped_cap``, ``provider_unavailable``). Those claims become ``NOT_ATTEMPTED`` in the verdict:
  never success.
* :class:`PrefetchingProvider` serves first-attempt proposals from a cache filled in parallel (at most 4 in flight)
  before ``receive``; a request the prefetch did not foresee goes to the provider as usual. The cache is keyed by the
  exact first-attempt request, so a served proposal is the one the provider would have returned (non-interference:
  receipts are identical with the prefetch on and off).
* :class:`FixtureCorpus` is the fixture provider of the ``development`` and ``sim`` environments: a corpus in the arena
  round format (``specialists/<item>.json`` with the item's ``response_text``; ``translations/<item>.json``:
  ``{report_id, claims: {claim_id: object}, claim_text_sha256}``), each item found by the SHA-256 of its recorded answer
  and each fixture bound to its claim by claim id and claim-text digest. It serves exactly what
  ``scripts/arena/run_arena.py`` serves for the same item (``tests/integration/test_fixture_parity.py`` runs both on the
  corpus); like the arena's verifier it is called as ``fn(claim, report)``, so the outcomes equal the arena's. A live
  provider's verifier is task-aware (``fn(claim, report, task=...)``).
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

__all__ = ["VerifierLog", "BudgetedVerifier", "PrefetchingProvider", "FixtureCorpus", "RekeyingFixtureProvider", "rekeyed_fixture",
           "first_attempt_request", "claim_is_eligible"]


@dataclass
class VerifierLog:
    """Per call: which claims got no outcome, and why; how long translation took."""
    skipped: dict[str, str] = field(default_factory=dict)
    verified: set[str] = field(default_factory=set)
    translated_live: int = 0
    translation_ms: int = 0

    def reason(self, claim_id: str) -> Optional[str]:
        return self.skipped.get(claim_id)


def claim_is_eligible(claim: Any) -> bool:
    """Deterministic eligibility (the eligibility rules plus the subject policy; no model call), as the pipeline decides it."""
    from ..translate.eligibility import decide_eligibility
    from ..translate.pipeline import apply_subject_policy
    from ..translate.subjects import resolve_profile
    return bool(apply_subject_policy(decide_eligibility(claim), resolve_profile(claim.subject)).eligible)


class BudgetedVerifier:
    """The channel's verifier for one checks call (module docstring). ``inner(claim, report)`` (or with ``task=``) is the
    provider-backed verifier; ``live`` says whether it calls a paid provider (only then does the cap apply)."""

    def __init__(self, inner: Optional[Callable[..., Any]], *, deadline: float, cap: int, live: bool,
                 clock: Callable[[], float] = time.monotonic, task_aware: bool = False, log: Optional[VerifierLog] = None) -> None:
        self._inner = inner
        self._deadline = deadline
        self._cap = cap
        self._live = live
        self._clock = clock
        self._task_aware = task_aware
        self._lock = threading.Lock()
        self.log = log if log is not None else VerifierLog()

    def _skip(self, claim_id: str, reason: str) -> None:
        with self._lock:
            self.log.skipped.setdefault(claim_id, reason)

    def _call(self, claim: Any, report: Any, task: Any) -> Any:
        cid = claim.claim_id
        if self._clock() >= self._deadline:
            self._skip(cid, "skipped_budget")
            return None
        if self._inner is None:
            self._skip(cid, "provider_unavailable")
            return None
        if self._live and claim_is_eligible(claim):
            with self._lock:
                if self.log.translated_live >= self._cap:
                    self.log.skipped.setdefault(cid, "skipped_cap")
                    return None
                self.log.translated_live += 1
        started = self._clock()
        try:
            out = self._inner(claim, report, task=task) if (self._task_aware and task is not None) else self._inner(claim, report)
        finally:
            with self._lock:
                self.log.translation_ms += int(max(0.0, self._clock() - started) * 1000)
        if out is None:
            self._skip(cid, "provider_unavailable")
        else:
            with self._lock:
                self.log.verified.add(cid)
        return out

    def plain(self) -> Callable[[Any, Any], Any]:
        """``fn(claim, report)``: the arena's calling convention (the fixture corpus)."""
        def fn(claim: Any, report: Any) -> Any:
            return self._call(claim, report, None)
        return fn

    def with_task(self) -> Callable[..., Any]:
        """``fn(claim, report, task=...)``: the live providers' calling convention (the channel passes the task record)."""
        def fn(claim: Any, report: Any, task: Any = None) -> Any:
            return self._call(claim, report, task)
        return fn


def first_attempt_request(claim: Any, report: Any, *, prompt_version: str, task: Any = None) -> Any:
    """The first-attempt ``TranslationRequest`` the pipeline builds for ``claim`` (``translate.pipeline.Translator``):
    ``None`` for a claim that is not eligible, which the pipeline never sends to a provider."""
    from ..translate import subjects
    from ..translate.eligibility import decide_eligibility
    from ..translate.pipeline import apply_subject_policy
    from ..translate.providers.base import TranslationRequest
    from ..version import IR_VERSION
    profile = subjects.resolve_profile(claim.subject)
    eligibility = apply_subject_policy(decide_eligibility(claim), profile)
    if not eligibility.eligible:
        return None
    supporting_ids = set(claim.supporting_claim_ids) - {claim.claim_id}
    supporting = [c for c in report.claims if c.claim_id in supporting_ids]
    return TranslationRequest(claim=claim, supporting_claims=supporting, supplied_texts=list(report.supplied_texts), eligibility=eligibility,
                              prompt_version=prompt_version, ir_version=IR_VERSION, subject_profile_text=subjects.prompt_profile_text(profile),
                              task=task, prior_diagnostics=[])


class PrefetchingProvider:
    """A translation provider that answers first-attempt requests from a cache filled in parallel before ``receive``."""

    def __init__(self, inner: Any, *, max_in_flight: int = 4) -> None:
        self.inner = inner
        self.name = getattr(inner, "name", "provider")
        self._max = max(1, int(max_in_flight))
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.hits = 0

    @staticmethod
    def _key(request: Any) -> str:
        return request.model_dump_json()

    def prefetch(self, requests: list[Any], *, deadline: float, clock: Callable[[], float] = time.monotonic) -> int:
        """Propose ``requests`` (first attempts only) in parallel; returns how many were cached. A provider error is not
        cached: the pipeline meets it again on demand and records it as it always does."""
        todo = [r for r in requests if r is not None and not r.prior_diagnostics]
        if not todo or clock() >= deadline:
            return 0

        def one(req: Any) -> None:
            if clock() >= deadline:
                return
            try:
                resp = self.inner.propose(req)
            except Exception:  # noqa: BLE001 - the on-demand call reports it
                return
            with self._lock:
                self._cache[self._key(req)] = resp

        with ThreadPoolExecutor(max_workers=self._max) as pool:
            list(pool.map(one, todo))
        return len(self._cache)

    def propose(self, request: Any) -> Any:
        if not request.prior_diagnostics:
            with self._lock:
                cached = self._cache.pop(self._key(request), None)
            if cached is not None:
                self.hits += 1
                return cached
        return self.inner.propose(request)


class FixtureCorpus:
    """Fixture translations for the ``development`` and ``sim`` environments (module docstring).

    ``index`` maps the SHA-256 of an answer text to its item; ``translations`` holds each item's fixtures in the arena's
    format with a claim-text digest for every claim (a fixture bound by claim id only is refused at load time, as the
    arena qualifies such a run with FIXTURES_UNBOUND)."""

    def __init__(self, index: Mapping[str, str], translations: Mapping[str, Mapping[str, Any]]) -> None:
        self._index = dict(index)
        self._translations = {k: dict(v) for k, v in translations.items()}
        for item, doc in self._translations.items():
            claims, digests = doc.get("claims") or {}, doc.get("claim_text_sha256") or {}
            if not isinstance(claims, dict) or set(digests) != set(claims):
                raise ValueError(f"translations of {item!r} bind fixtures by claim id only; every fixture needs its claim-text digest")

    @classmethod
    def load(cls, directory: str | Path) -> "FixtureCorpus":
        """A corpus directory: one arena round (``specialists/`` and ``translations/``) or a folder of rounds (items are
        then named ``<round>/<item>``). Items without a translations file serve nothing; two items with one answer text
        and different fixtures are refused (the answer digest must name one item)."""
        d = Path(directory)
        if (d / "specialists").is_dir():
            rounds = [(d, "")]
        else:
            rounds = [(p, f"{p.name}/") for p in sorted(d.iterdir()) if (p / "specialists").is_dir()] if d.is_dir() else []
        if not rounds:
            raise ValueError("the fixture corpus holds no arena round (no specialists/ directory)")
        from .canonical import sha256_text
        index: dict[str, str] = {}
        translations: dict[str, Mapping[str, Any]] = {}
        for rd, prefix in rounds:
            for sp in sorted((rd / "specialists").glob("*.json")):
                tp = rd / "translations" / sp.name
                if not tp.exists():
                    continue
                try:  # read exactly as run_arena.py reads a round (json.loads), so both serve the same fixtures
                    item = json.loads(sp.read_text(encoding="utf-8"))
                    doc = json.loads(tp.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise ValueError(f"corpus item {prefix}{sp.stem} is not readable JSON ({type(exc).__name__})") from None
                key = prefix + sp.stem
                digest = sha256_text(item["response_text"])
                if digest in index and translations[index[digest]] != doc:
                    raise ValueError(f"corpus items {index[digest]} and {key} share one answer text with different fixtures")
                index.setdefault(digest, key)
                translations[key] = doc
        return cls(index, translations)

    def item_for(self, answer_sha256: str) -> Optional[str]:
        return self._index.get(answer_sha256)

    def verifier_for(self, answer_sha256: str, *, config: Any, signing_key: bytes, key_id: Optional[str] = None,
                     prefetch: bool = False) -> tuple[Optional[Callable[[Any, Any], Any]], Optional[Any]]:
        """``(fn(claim, report), provider)`` serving the item's fixtures exactly as ``run_arena.make_verify_fn`` does
        (claim ids outside the fixtures get no outcome; a claim whose text changed is refused as stale), or
        ``(None, None)`` when no item has this answer. A fixture is authored for its item, not for one request: it is
        served under the request id of the claim being translated (:class:`RekeyingFixtureProvider`), which is a no-op
        when the ids already match, as they do in the arena."""
        item = self._index.get(answer_sha256)
        doc = self._translations.get(item) if item is not None else None
        if not doc:
            return None, None
        from ..translate.outcome import verify_claim
        from ..translate.pipeline import Translator
        provider: Any = RekeyingFixtureProvider(doc["claims"], dict(doc["claim_text_sha256"]))
        if prefetch:
            provider = PrefetchingProvider(provider)
        translator = Translator(provider)
        ids = frozenset(doc["claims"])

        def fn(claim: Any, report: Any) -> Any:
            if claim.claim_id not in ids:
                return None
            return verify_claim(claim, report, translator, config=config, signing_key=signing_key, key_id=key_id)
        return fn, provider


def rekeyed_fixture(obj: Any, request_id: str) -> str:
    """A fixture's JSON text with ``problem.request_id`` set to ``request_id`` (nothing else changes; a fixture without a
    problem, or one that is not a JSON object, is served as it is and the pipeline judges it as before)."""
    text = obj if isinstance(obj, str) else json.dumps(obj)
    try:
        data = json.loads(text)
    except ValueError:
        return text
    problem = data.get("problem") if isinstance(data, dict) else None
    if isinstance(problem, dict) and problem.get("request_id") != request_id:
        data = {**data, "problem": {**problem, "request_id": request_id}}
        return json.dumps(data)
    return text


class RekeyingFixtureProvider:
    """The fixture provider of one corpus item, serving each fixture under the request id of the claim it is asked for
    (a website-path call's request id is the website's attempt id; the arena's is ``req-<item>``). One
    ``FixtureTranslationProvider`` per request id keeps its per-claim attempt counters and its stale-fixture refusal."""

    def __init__(self, claims: Mapping[str, Any], claim_text_sha256: Mapping[str, str]) -> None:
        from ..translate.providers.fixture import FixtureTranslationProvider
        self._cls = FixtureTranslationProvider
        self.name = FixtureTranslationProvider.name
        self._claims = dict(claims)
        self._digests = dict(claim_text_sha256)
        self._by_request: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _for(self, request_id: str) -> Any:
        with self._lock:
            p = self._by_request.get(request_id)
            if p is None:
                p = self._cls({cid: rekeyed_fixture(obj, request_id) for cid, obj in self._claims.items()}, claim_text_sha256=self._digests)
                self._by_request[request_id] = p
            return p

    def propose(self, request: Any) -> Any:
        return self._for(request.claim.request_id).propose(request)
