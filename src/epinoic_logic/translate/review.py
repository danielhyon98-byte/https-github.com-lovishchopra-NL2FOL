"""Advisory semantic-fidelity review.

A second model reads the claim, the problem and the translator's interpretation
record and says whether the encoding means what the claim says. The verdict is
recorded next to the engine result and is **advisory only**: it never changes a
status, never counts as verification, and a second model agreeing with the first
does not establish truth (context document, section 1). Any problem reading the
reviewer's output degrades the verdict to ``uncertain``, never to ``faithful``.
"""
from __future__ import annotations

from typing import Any, Literal

from . import prompts
from .common import new_id, truncate, utc_now_rfc3339
from .contracts import ClaimRecord, Interpretation, ProviderInfo, SemanticFidelityReview, TranslationResult
from .parsing import ProviderOutputError, parse_json_object
from .providers.base import ProviderError, ReviewProvider, ReviewRequest

__all__ = ["SemanticReviewer", "parse_review_output", "VERDICTS"]

Verdict = Literal["faithful", "unfaithful", "uncertain"]
VERDICTS: frozenset[str] = frozenset({"faithful", "unfaithful", "uncertain"})
_MAX_ISSUES = 32
_MAX_ISSUE_CHARS = 1000


def _issues_from(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        text = item if isinstance(item, str) else str(item)
        text = text.strip()
        if text:
            out.append(truncate(text, _MAX_ISSUE_CHARS))
        if len(out) >= _MAX_ISSUES:
            break
    return out


def parse_review_output(raw_text: str) -> tuple[Verdict, list[str]]:
    """Parse reviewer text into ``(verdict, issues)``.

    The verdict must be one of ``faithful``, ``unfaithful`` or ``uncertain``;
    anything else, or unparseable output, yields ``uncertain`` with the problem
    recorded as an issue. Issues are coerced to a bounded list of strings.
    """
    try:
        obj = parse_json_object(raw_text)
    except ProviderOutputError as exc:
        return "uncertain", [f"reviewer output could not be parsed: {truncate(str(exc), 300)}"]
    issues = _issues_from(obj.get("issues"))
    verdict = obj.get("verdict")
    if not isinstance(verdict, str) or verdict.strip().lower() not in VERDICTS:
        issues.append("reviewer verdict missing or not one of faithful/unfaithful/uncertain")
        return "uncertain", issues
    return verdict.strip().lower(), issues  # type: ignore[return-value]


class SemanticReviewer:
    """Runs an independent :class:`ReviewProvider` over a translation (advisory)."""

    def __init__(self, provider: ReviewProvider) -> None:
        self.provider = provider

    def review(self, claim: ClaimRecord, translation: TranslationResult) -> SemanticFidelityReview:
        """Review ``translation`` of ``claim``. Requires ``translation.problem``.

        Raises :class:`ValueError` when there is no problem to review. Provider
        failures and unreadable output become an ``uncertain`` verdict.
        """
        if translation.problem is None:
            raise ValueError("semantic review requires a translation with a problem")
        if translation.claim_id != claim.claim_id or translation.request_id != claim.request_id:
            raise ValueError("translation does not belong to the claim")
        interpretation = translation.interpretation or Interpretation(
            reading="no interpretation record was produced by the translator"
        )
        request = ReviewRequest(claim=claim, problem=translation.problem, interpretation=interpretation)
        try:
            response = self.provider.review(request)
        except ProviderError as exc:
            info = ProviderInfo(provider_name=self.provider.name, prompt_version=prompts.REVIEW_PROMPT_VERSION)
            return self._build(translation, "uncertain", [f"reviewer unavailable: {truncate(str(exc), 300)}"], info)
        verdict, issues = parse_review_output(response.raw_text)
        return self._build(translation, verdict, issues, response.info)

    @staticmethod
    def _build(translation: TranslationResult, verdict: Verdict, issues: list[str], info: ProviderInfo) -> SemanticFidelityReview:
        return SemanticFidelityReview(
            review_id=new_id("rv"),
            translation_id=translation.translation_id,
            verdict=verdict,
            issues=issues,
            reviewer=info,
            advisory_only=True,
            created_at=utc_now_rfc3339(),
        )
