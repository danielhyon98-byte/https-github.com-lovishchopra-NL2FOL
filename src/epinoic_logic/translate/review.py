"""Advisory semantic-fidelity review.

A second model reads the claim, the problem and the translator's interpretation record and says whether the
encoding means what the claim says. It is shown the evidence the encoding must be faithful to: the original task
(when the caller holds the task record), the contents of the claim's supporting claims, the supplied texts, the
identity and digest of every input, the premise-to-source mapping with what deterministic code found (an excerpt
located, a figure stated, task authority validated or not), and how the source states each figure the problem
compares. A reviewer cannot check a translation against evidence it was never shown.

The review is bound to exactly those inputs and their versions (:class:`~.contracts.ReviewBinding`). A changed
source or supporting claim makes an earlier review stale even when the claim text is unchanged
(:func:`review_currency`), and a review made without the evidence is recorded as such. The verdict is **advisory
only**: it never changes a status and never counts as verification, and a second model agreeing with the first
does not establish truth (context document, section 1). Application code decides whether the required fidelity
check is satisfied (``outcome.assess_release``). Any problem reading the reviewer's output degrades the verdict to
``uncertain``, never to ``faithful``.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from ..ir.canonical import canonical_json, problem_digest, sha256_hex
from ..version import IR_VERSION
from . import prompts
from .common import new_id, truncate, utc_now_rfc3339
from .contracts import (
    ClaimRecord,
    Interpretation,
    PremiseSource,
    ProviderInfo,
    ReviewBinding,
    SemanticFidelityReview,
    SourceIdentity,
    SpecialistReport,
    SuppliedText,
    TaskRecord,
    TranslationResult,
)
from .grounding import support_of
from .parsing import ProviderOutputError, parse_json_object
from .providers.base import ProviderError, ReviewProvider, ReviewRequest

__all__ = ["SemanticReviewer", "parse_review_output", "VERDICTS", "review_binding", "review_currency", "build_review_request",
           "MAX_TEXT_CHARS_SHOWN", "MAX_TOTAL_CHARS_SHOWN"]

Verdict = Literal["faithful", "unfaithful", "uncertain"]
VERDICTS: frozenset[str] = frozenset({"faithful", "unfaithful", "uncertain"})
_MAX_ISSUES = 32
_MAX_ISSUE_CHARS = 1000
#: Characters of one supplied text shown to the reviewer, and of all of them together; a text cut to fit is named on
#: the review (``evidence_truncated``) and the outcome does not count such a review as approval.
MAX_TEXT_CHARS_SHOWN = 60_000
MAX_TOTAL_CHARS_SHOWN = 150_000


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


# ------------------------------------------------------------------ evidence and binding


def _supporting(claim: ClaimRecord, report: SpecialistReport) -> list[ClaimRecord]:
    ids = set(claim.supporting_claim_ids) - {claim.claim_id}
    return [c for c in report.claims if c.claim_id in ids]


def _record_sha(model: Any) -> str:
    return sha256_hex(canonical_json(model))


def review_binding(claim: ClaimRecord, translation: TranslationResult, report: Optional[SpecialistReport], task: Optional[TaskRecord] = None,
                   prompt_version: str = prompts.REVIEW_PROMPT_VERSION) -> ReviewBinding:
    """The binding of a review of ``translation`` to its inputs: the claim record, the problem and interpretation, every
    supporting claim and supplied text (each by the digest of its whole record), the task record and the versions."""
    if translation.problem is None:
        raise ValueError("a review binding requires a translation with a problem")
    interpretation = translation.interpretation or Interpretation(reading="no interpretation record was produced by the translator")
    fields: dict[str, Any] = dict(
        claim_id=claim.claim_id,
        claim_record_sha256=_record_sha(claim),
        translation_id=translation.translation_id,
        problem_digest=problem_digest(translation.problem),
        interpretation_sha256=_record_sha(interpretation),
        supporting_claims={c.claim_id: _record_sha(c) for c in (_supporting(claim, report) if report is not None else [])},
        supplied_texts={t.document_id: _record_sha(t) for t in (report.supplied_texts if report is not None else [])},
        task_sha256=task.text_sha256 if task is not None else None,
        response_sha256=report.response_sha256 if report is not None else None,
        translator_version=translation.translator_version,
        review_prompt_version=prompt_version,
        ir_version=IR_VERSION,
    )
    return ReviewBinding(**fields, digest=sha256_hex(canonical_json({k: v for k, v in fields.items()})))


def review_currency(review: SemanticFidelityReview, claim: ClaimRecord, translation: TranslationResult, report: Optional[SpecialistReport],
                    task: Optional[TaskRecord] = None) -> tuple[Literal["current", "stale", "unbound", "without_evidence"], list[str]]:
    """Whether ``review`` is bound to the current inputs: ``current``; ``stale`` with what changed (a supporting claim, a
    supplied text, the task, the claim record, the problem); ``unbound`` (the review records no binding, or the
    current report is not at hand to confirm it); ``without_evidence`` (the request carried no evidence)."""
    if review.binding is None:
        return "unbound", []
    if not review.evidence_supplied:
        return "without_evidence", []
    if report is None or translation.problem is None:
        return "unbound", []
    current = review_binding(claim, translation, report, task, review.binding.review_prompt_version)
    if current.digest == review.binding.digest:
        return "current", []
    old, new = review.binding, current
    changed: list[str] = []
    for name in ("claim_record_sha256", "translation_id", "problem_digest", "interpretation_sha256", "task_sha256", "response_sha256",
                 "translator_version", "ir_version"):
        if getattr(old, name) != getattr(new, name):
            changed.append(name.replace("_sha256", "").replace("_", " "))
    for label, a, b in (("supporting claim", old.supporting_claims, new.supporting_claims), ("supplied text", old.supplied_texts, new.supplied_texts)):
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                changed.append(f"{label} {key} " + ("added" if key not in a else "removed" if key not in b else "changed"))
    return "stale", changed or ["binding digest"]


def _shown_texts(texts: list[SuppliedText], referenced: set[str]) -> tuple[list[SuppliedText], list[str]]:
    """The supplied texts as shown to the reviewer: referenced ones first, each within :data:`MAX_TEXT_CHARS_SHOWN`
    and all within :data:`MAX_TOTAL_CHARS_SHOWN`; ``(texts, ids shown only in part)``."""
    ordered = sorted(texts, key=lambda t: t.document_id not in referenced)
    shown: list[SuppliedText] = []
    cut: list[str] = []
    budget = MAX_TOTAL_CHARS_SHOWN
    for t in ordered:
        room = min(MAX_TEXT_CHARS_SHOWN, max(budget, 0))
        if len(t.text) > room:
            cut.append(t.document_id)
            if room <= 0:
                continue
            shown.append(t.model_copy(update={"text": t.text[:room]}))
            budget -= room
        else:
            shown.append(t)
            budget -= len(t.text)
    return shown, cut


def build_review_request(claim: ClaimRecord, translation: TranslationResult, report: Optional[SpecialistReport], task: Optional[TaskRecord] = None,
                         prompt_version: str = prompts.REVIEW_PROMPT_VERSION) -> tuple[ReviewRequest, list[str]]:
    """The request for a review of ``translation``, with every piece of evidence the caller holds, and the supplied
    texts shown only in part."""
    if translation.problem is None:
        raise ValueError("semantic review requires a translation with a problem")
    problem = translation.problem
    interpretation = translation.interpretation or Interpretation(reading="no interpretation record was produced by the translator")
    binding = review_binding(claim, translation, report, task, prompt_version)
    if report is None:
        return ReviewRequest(claim=claim, problem=problem, interpretation=interpretation, binding=binding, prompt_version=prompt_version,
                             translation_diagnostics=[truncate(d, 500) for d in translation.diagnostics[:32]]), []
    supporting = _supporting(claim, report)
    referenced = {r.document_id for a in [*problem.premises, *([problem.conclusion] if problem.conclusion else [])] if a.grounding
                  for r in a.grounding.source_refs} | {r.document_id for r in claim.source_refs} | {r.document_id for c in supporting for r in c.source_refs}
    shown, cut = _shown_texts(list(report.supplied_texts), referenced)
    shown_len = {t.document_id: len(t.text) for t in shown}
    sources = [SourceIdentity(kind="claim", ident=claim.claim_id, sha256=_record_sha(claim), total_chars=len(claim.claim_text), shown_chars=len(claim.claim_text))]
    sources += [SourceIdentity(kind="supporting_claim", ident=c.claim_id, sha256=_record_sha(c), total_chars=len(c.claim_text), shown_chars=len(c.claim_text))
                for c in supporting]
    if task is not None:
        sources.append(SourceIdentity(kind="task", ident=task.task_id, sha256=task.text_sha256, provenance=f"issued by {task.issued_by}",
                                      total_chars=len(task.text), shown_chars=len(task.text)))
    sources += [SourceIdentity(kind="supplied_text", ident=t.document_id, sha256=_record_sha(t), title=t.title, provenance=t.provenance,
                               total_chars=len(t.text), shown_chars=shown_len.get(t.document_id, 0)) for t in report.supplied_texts]
    mapping: list[PremiseSource] = []
    for role, assertion in [*(("premise", p) for p in problem.premises), *((("conclusion", problem.conclusion),) if problem.conclusion else ())]:
        g = assertion.grounding
        checks = [c for c in translation.grounding_checks if c.target_id == assertion.id][:12]
        support = support_of(assertion.id, translation.grounding_checks)
        mapping.append(PremiseSource(assertion_id=assertion.id, role=role, label=assertion.label, grounding_kind=g.kind if g else None,  # type: ignore[arg-type]
                                     certainty=g.certainty if g else None, source_refs=list(g.source_refs) if g else [], verified=g.verified if g else None,
                                     support=support.support if support is not None else None, checks=checks))
    request = ReviewRequest(claim=claim, problem=problem, interpretation=interpretation, task=task, supporting_claims=supporting, supplied_texts=shown,
                            sources=sources, premise_sources=mapping, figure_readings=list(translation.figure_readings),
                            translation_diagnostics=[truncate(d, 500) for d in translation.diagnostics[:32]], binding=binding, prompt_version=prompt_version)
    return request, cut


class SemanticReviewer:
    """Runs an independent :class:`ReviewProvider` over a translation (advisory)."""

    def __init__(self, provider: ReviewProvider) -> None:
        self.provider = provider

    def review(self, claim: ClaimRecord, translation: TranslationResult, report: Optional[SpecialistReport] = None,
               task: Optional[TaskRecord] = None) -> SemanticFidelityReview:
        """Review ``translation`` of ``claim``. Requires ``translation.problem``.

        With ``report`` (and ``task`` when the caller holds the task record) the request carries the evidence the
        review must be judged against, and the review is bound to it; without them the review is recorded as made
        without evidence. Raises :class:`ValueError` when there is no problem to review or the inputs do not belong
        together. Provider failures and unreadable output become an ``uncertain`` verdict.
        """
        if translation.problem is None:
            raise ValueError("semantic review requires a translation with a problem")
        if translation.claim_id != claim.claim_id or translation.request_id != claim.request_id:
            raise ValueError("translation does not belong to the claim")
        if report is not None and (claim.report_id != report.report_id or claim.request_id != report.request_id):
            raise ValueError("claim does not belong to the report")
        if task is not None and (task.task_id != claim.task_id or task.request_id != claim.request_id):
            raise ValueError("task record does not belong to the claim's task and request")
        request, cut = build_review_request(claim, translation, report, task)
        evidence = report is not None
        try:
            response = self.provider.review(request)
        except ProviderError as exc:
            info = ProviderInfo(provider_name=self.provider.name, prompt_version=prompts.REVIEW_PROMPT_VERSION)
            return self._build(translation, "uncertain", [f"reviewer unavailable: {truncate(str(exc), 300)}"], info, request, evidence, cut)
        verdict, issues = parse_review_output(response.raw_text)
        return self._build(translation, verdict, issues, response.info, request, evidence, cut)

    @staticmethod
    def _build(translation: TranslationResult, verdict: Verdict, issues: list[str], info: ProviderInfo, request: ReviewRequest, evidence: bool,
               cut: list[str]) -> SemanticFidelityReview:
        return SemanticFidelityReview(
            review_id=new_id("rv"),
            translation_id=translation.translation_id,
            verdict=verdict,
            issues=issues,
            reviewer=info,
            advisory_only=True,
            created_at=utc_now_rfc3339(),
            binding=request.binding,
            evidence_supplied=evidence,
            evidence_truncated=list(cut),
        )
