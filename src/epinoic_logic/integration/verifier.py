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
  corpus); like the arena's verifier (since round 8's clearance) it is task-aware, called as ``fn(claim, report,
  task=...)`` with the task record of the request (``BudgetedVerifier.with_task``), so the outcomes, and the digests of the
  encoded problems, equal the arena's. A live provider's verifier is task-aware too.
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
           "first_attempt_request", "claim_is_eligible", "qualification_tag", "other_id_form", "fixture_for_claim"]


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
        """``fn(claim, report)``: a verifier that takes no task record (the arena's calling convention before round 8's
        clearance; the fixture corpus now uses :meth:`with_task`, as the arena passes the task record)."""
        def fn(claim: Any, report: Any) -> Any:
            return self._call(claim, report, None)
        return fn

    def with_task(self) -> Callable[..., Any]:
        """``fn(claim, report, task=...)``: the live providers' and the fixture corpus's calling convention (the channel
        passes the task record, as it does to the arena's verifier)."""
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

    def __init__(self, index: Mapping[str, str], translations: Mapping[str, Mapping[str, Any]],
                 arena_request_ids: Optional[Mapping[str, str]] = None) -> None:
        self._index = dict(index)
        self._translations = {k: dict(v) for k, v in translations.items()}
        #: item -> the request id the arena gives it (``req-<group>``, the group being the item's declared group or its file
        #: name): the only request id under which a fixture of the item is served re-keyed (``RekeyingFixtureProvider``).
        self._arena_request_ids = dict(arena_request_ids or {})
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
        arena_ids: dict[str, str] = {}
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
                arena_ids[key] = f"req-{item.get('group') or sp.stem}"  # run_arena.group_plan's request id for this item
        return cls(index, translations, arena_ids)

    def item_for(self, answer_sha256: str) -> Optional[str]:
        return self._index.get(answer_sha256)

    def verifier_for(self, answer_sha256: str, *, config: Any, signing_key: bytes, key_id: Optional[str] = None,
                     prefetch: bool = False) -> tuple[Optional[Callable[..., Any]], Optional[Any]]:
        """``(fn(claim, report, task=...), provider)`` serving the item's fixtures exactly as ``run_arena.make_verify_fn``
        does, called as ``run_arena.make_verify_fn``'s verifier is: with the task record of the request, which the
        translator validates task-authority premises against (round 8's clearance; without it the encoded problems of an
        item whose fixtures carry task_setting or arithmetic_fact premises differed from the arena's, so the simulation's
        G-EQ-ARENA digests differed). Claim ids outside the fixtures get no outcome; a claim whose text changed is refused as
        stale; ``(None, None)`` when no item has this answer. A fixture recorded under the arena's request id of its item
        (``req-<item>``, or ``req-<group>``) is served under the request id of the claim being translated
        (:class:`RekeyingFixtureProvider`; a no-op in the arena, whose claims carry that id); a fixture recorded for
        another request is served as it is, and refused as the arena refuses it. A fixture recorded under the other form
        of the report's own claim id (:func:`other_id_form`: the hub qualifies a report's ids with its agent when a report
        of another agent on the task holds them, as the second of two instances of one specialist in duplicate mode does)
        serves that claim, its problem naming the delivered id (:func:`fixture_for_claim`) and bound to the claim text by
        the recorded id's digest, as the arena serves it (integration gate 3, handoff fixer: the second History instance's
        qualified claims got no fixture, so a duplicate-mode turn was refused as incomplete, KIT-DL-011)."""
        item = self._index.get(answer_sha256)
        doc = self._translations.get(item) if item is not None else None
        if not doc:
            return None, None
        from ..translate.outcome import verify_claim
        from ..translate.pipeline import Translator
        provider: Any = RekeyingFixtureProvider(doc["claims"], dict(doc["claim_text_sha256"]), arena_request_id=self._arena_request_ids.get(item))
        if prefetch:
            provider = PrefetchingProvider(provider)
        translator = Translator(provider)
        ids = frozenset(doc["claims"])

        def fn(claim: Any, report: Any, task: Any = None) -> Any:
            key = claim.claim_id if claim.claim_id in ids else None
            if key is None:
                other = other_id_form(claim.claim_id, qualification_tag(report))
                key = other if other is not None and other in ids else None
            if key is None:
                return None
            use = translator
            if key != claim.claim_id:
                use = Translator(RekeyingFixtureProvider({claim.claim_id: fixture_for_claim(doc["claims"][key], key, claim.claim_id)},
                                                         {claim.claim_id: doc["claim_text_sha256"][key]}, arena_request_id=self._arena_request_ids.get(item)))
            return verify_claim(claim, report, use, config=config, signing_key=signing_key, key_id=key_id, task=task)
        return fn, provider


def qualification_tag(report: Any) -> Optional[str]:
    """The tag the hub qualifies ``report``'s claim ids with when a report of another agent on the task holds them
    (``generic_parser.agent_claim_tag`` of its agent), or None when its branch's parser never qualifies its ids on that
    account (only a parser offering ``accepts_qualify_ids`` is asked to: ``channel.bus.needs_qualified_ids``). The arena's
    ``run_arena.qualification_tag``, read from the delivered report."""
    from ..branches import default_registry
    from ..branches.generic_parser import agent_claim_tag
    branch, _profile = default_registry().for_subject(report.subject)
    if getattr(branch.parser(), "accepts_qualify_ids", False) is not True:
        return None
    return agent_claim_tag(report.agent_id)


def other_id_form(claim_id: Any, tag: Optional[str]) -> Optional[str]:
    """The other form the hub's rule gives one claim id of a report whose ids it may qualify with ``tag``: 's1.2' for
    's1.2@physics-specialist' and the reverse; None without a tag, or for an id qualified with another tag (another agent's
    claim). The arena's ``run_arena.other_id_form``."""
    if not tag or not isinstance(claim_id, str):
        return None
    suffix = "@" + tag
    if claim_id.endswith(suffix):
        base = claim_id[:-len(suffix)]
        return base if base and "@" not in base else None
    return None if "@" in claim_id else claim_id + suffix


def fixture_for_claim(value: Any, recorded_id: str, claim_id: str) -> str:
    """The recorded translation ``value`` (an object, or text) as served to the delivered claim ``claim_id``, the other form
    of its recorded id: a copy whose problem names ``claim_id`` where it named ``recorded_id``, nothing else changed (data
    only, read by the pipeline's own reader; nothing is evaluated). A text that is no JSON object, or a problem naming
    another claim, is served as recorded, so the pipeline decides it as it would under the recorded id. The arena's
    ``run_arena.fixture_for_claim``."""
    from ..translate.parsing import ProviderOutputError, parse_json_object
    if isinstance(value, str):
        try:
            obj = parse_json_object(value)
        except ProviderOutputError:
            return value
    elif isinstance(value, dict):
        obj = json.loads(json.dumps(value))
    else:
        return json.dumps(value)
    problem = obj.get("problem")
    if isinstance(problem, dict) and problem.get("claim_id") == recorded_id:
        problem["claim_id"] = claim_id
    return json.dumps(obj)


def rekeyed_fixture(obj: Any, request_id: str, *, only_from: Optional[str] = None) -> str:
    """A fixture's JSON text with ``problem.request_id`` set to ``request_id`` (nothing else changes; a fixture without a
    problem, or one that is not a JSON object, is served as it is and the pipeline judges it as before). With
    ``only_from``, only a fixture recorded under that request id is re-keyed: any other is served as it is, so the
    pipeline refuses a fixture of another request exactly as the arena does."""
    text = obj if isinstance(obj, str) else json.dumps(obj)
    try:
        data = json.loads(text)
    except ValueError:
        return text
    problem = data.get("problem") if isinstance(data, dict) else None
    if isinstance(problem, dict) and only_from is not None and problem.get("request_id") != only_from:
        return text
    if isinstance(problem, dict) and problem.get("request_id") != request_id:
        data = {**data, "problem": {**problem, "request_id": request_id}}
        return json.dumps(data)
    return text


class RekeyingFixtureProvider:
    """The fixture provider of one corpus item, serving each fixture under the request id of the claim it is asked for
    (a website-path call's request id is the website's attempt id; the arena's is ``req-<item>``). Only a fixture
    recorded under ``arena_request_id``, the request id the arena gives the item, is re-keyed: one recorded for another
    request (an adversarial variant reusing another item's fixture, say) is served as it is and refused by the pipeline,
    as the arena refuses it. One ``FixtureTranslationProvider`` per request id keeps its per-claim attempt counters and
    its stale-fixture refusal."""

    def __init__(self, claims: Mapping[str, Any], claim_text_sha256: Mapping[str, str], *, arena_request_id: Optional[str] = None) -> None:
        from ..translate.providers.fixture import FixtureTranslationProvider
        self._cls = FixtureTranslationProvider
        self.name = FixtureTranslationProvider.name
        self._claims = dict(claims)
        self._digests = dict(claim_text_sha256)
        self._arena_request_id = arena_request_id
        self._by_request: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _for(self, request_id: str) -> Any:
        with self._lock:
            p = self._by_request.get(request_id)
            if p is None:
                p = self._cls({cid: rekeyed_fixture(obj, request_id, only_from=self._arena_request_id) for cid, obj in self._claims.items()},
                              claim_text_sha256=self._digests)
                self._by_request[request_id] = p
            return p

    def propose(self, request: Any) -> Any:
        return self._for(request.claim.request_id).propose(request)
