"""Compose what the Overseer receives for one claim.

``compose_outcome`` derives a ``display_status`` deterministically and writes a
plain-language summary of what was checked, under which assumptions, and what
remains unverified. ``verify_claim`` is the convenience path
translate -> engine -> (review) -> compose.

Display rules (never relaxed):

* ``TRANSLATED``             -> the engine's status, provided the engine result is
  bound to exactly the translated problem; a missing or mis-bound result is
  ``INTERNAL_ERROR``, and so is a result that is not current-policy evidence (issued
  under other component versions, another build, schema or policy identity, or
  non-default validation limits: ``engine.provenance.stale_reasons``; verify the
  problem again). When the composer holds the signing key, a result whose
  signature does not verify is likewise rejected (``E501``). A definitive status
  that the engine marked vacuous (``E108``: no premise was used, or a COUNTEREXAMPLE
  over no premises) or an ENTAILED proof whose premises restate the conclusion
  (``E112``: circular, the claim was assumed, not derived) is displayed as
  ``INVALID_FORMALIZATION``, never as a verdict. So is a COUNTEREXAMPLE that only
  reassigns a figure the problem defines but never asserts (``E110``) or conclusion
  symbols no premise mentions (``E111``): the engine reports these codes only with
  source-linked evidence that a source asserts what the encoding left open (a symbol
  grounding verified in this process, which the translation layer creates from its
  :class:`~.contracts.CoverageNote`; the summary names the asserting spans). Without that
  evidence the engine reports the advisory ``W110``/``W111``: the source may leave the
  figure open on purpose (a definition, an arbitrary variable), so the counterexample
  stands as the verdict on the encoding and the summary carries the advisory coverage
  warning. The signed engine result decides; this layer never withholds or restores a
  verdict on its own reading.
* ``AMBIGUOUS_TRANSLATION``  -> ``AMBIGUOUS_TRANSLATION`` (the best-reading problem may
  have been verified for inspection, but an ambiguous claim is never displayed as
  a result).
* ``NOT_ELIGIBLE``           -> ``NOT_ELIGIBLE``
* ``UNSUPPORTED``            -> ``UNSUPPORTED``
* ``INVALID_FORMALIZATION``  -> ``INVALID_FORMALIZATION``
* ``TRANSLATION_FAILED``     -> ``INTERNAL_ERROR``

Release (``ReleaseAssessment``, :func:`assess_release`) is a separate record: whether the
claim's checks permit releasing the answer automatically. A formal ENTAILED never grants it on
its own: the engine's own release check must pass (``engine.release.release_check``: an
authenticated, bound, current result with a positive verdict, its evidence computed and no
unresolved dependency; so an unsigned result, or one this layer holds no key to verify, never
permits release), every relied-on premise must be established (its whole content: a premise whose
numeric content is a relation no record states as a given stays an unverified dependency whatever
its grounding label, however many of its figures a record states), no grounding check may fail, no
retry may have changed the claim beyond its source, and the required fidelity review must be
``faithful``, made with the evidence and bound to the current inputs (a changed source or
supporting claim makes it stale). The model's review never changes the display status.

Argument diagnosis (rules ``argdiag-2``): every outcome, NOT_ELIGIBLE included, carries the claim's
named diagnostics (``named_diagnostics``: the trusted engine result's own, merged with the claim
layer's, :mod:`.diag_core`) and the rules that did not finish (``diagnosis_incomplete``). They are
advisory and never change the display status; release (``release-v1`` on this tree, ``release-v2`` on the feature line) refuses a claim with a named
defect at warning or error by effective severity, so a capped warning still blocks it, and an info
diagnostic never blocks or permits anything on its own. The summary shows them in their own section,
directly after the verification lines, under "Argument diagnosis (advisory; the status above is
unchanged; rules argdiag-2)", or says "none found", "incomplete" or "not computed". For an ambiguous
translation the engine run is capped (``verify(..., severity_cap=("info", "ambiguous_translation"))``),
so its diagnostics have one severity in the signed result and in the outcome.

The summary always ends with the engine's scope statement verbatim.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from ..engine.errors import ADVISORY_CODES, NO_VERDICT_CODES, DiagnosticCode
from ..engine.provenance import stale_reasons, verify_signature
from ..engine.release import ReleaseCheck, release_check
from ..engine.results import SolverConfig, VerificationResult
from ..engine.runner import verify as engine_verify
from ..engine.statuses import DEFINITIVE, SCOPE_STATEMENT, VerificationStatus
from ..ir.canonical import problem_digest
from ..ir.schema import Problem
from ..named import NamedDiagnostic, blocking_release_lines, diagnosis_section, is_blocking, model_text, one_line, rules_state
from ..version import TRANSLATOR_VERSION
from .common import new_id, truncate, utc_now_rfc3339
from .contracts import (
    ClaimRecord,
    ClaimVerificationOutcome,
    CoverageNote,
    ReleaseAssessment,
    SemanticFidelityReview,
    SpecialistReport,
    StructuralFinding,
    TaskRecord,
    TranslationResult,
    TranslationStatus,
    sha256_text,
)
from .coverage import coverage_digest
from .diag_core import build_context, claim_diagnostics
from .pipeline import Translator
from .review import SemanticReviewer, review_currency

__all__ = ["compose_outcome", "display_status_for", "verify_claim", "assess_release", "outcome_diagnosis", "STATUS_MEANING", "SUMMARY_MAX_CHARS", "RELEASE_POLICY"]

#: The release rule's version (bump on any change to :func:`assess_release`). The argument diagnosis (rules argdiag-2)
#: makes the rule stricter only: a named defect on the claim (warning or error by effective severity) is unresolved, a
#: claim-layer diagnosis that did not finish is unresolved too (not computed is never read as none found), and the engine
#: release check's "named defect" reason is listed whenever the claim's own list names no blocking diagnostic. On the
#: integrated translator the label stays ``release-v1`` with the component versions, which the integration kit pins; the
#: feature line's ``release-v2`` ships with the version bump of the final integration (docs/ARGUMENT_DIAGNOSTICS.md, section 20).
RELEASE_POLICY = "release-v1"
#: The status that passes the formal check, per query kind.
_PASSING = {"entailment": VerificationStatus.ENTAILED, "consistency": VerificationStatus.CONSISTENT, "satisfiability": VerificationStatus.SATISFIABLE}

SUMMARY_MAX_CHARS = 4000
#: Longest diagnosis line of a summary (the record itself keeps the whole message).
_DIAGNOSIS_LINE_CHARS = 400
_LABEL_CHARS = 160
_DIAG_CHARS = 300
_MAX_LISTED = 8

STATUS_MEANING: dict[VerificationStatus, str] = {
    VerificationStatus.ENTAILED: (
        "the encoded conclusion follows from the encoded premises (the premises are consistent and no "
        "assignment satisfies them while falsifying the conclusion)"
    ),
    VerificationStatus.COUNTEREXAMPLE: (
        "the encoded conclusion does not follow from the encoded premises: an assignment satisfies every "
        "premise and falsifies the conclusion"
    ),
    VerificationStatus.INCONSISTENT_PREMISES: "the encoded premises contradict each other, so the conclusion was not tested",
    VerificationStatus.CONSISTENT: "the encoded statements can all hold together",
    VerificationStatus.SATISFIABLE: "the encoded statements can be satisfied together",
    VerificationStatus.UNSATISFIABLE: "the encoded statements cannot all hold together",
    VerificationStatus.UNKNOWN: "the solver could not decide the encoded problem; nothing was verified",
    VerificationStatus.TIMEOUT: "the solver stopped at its resource bound; nothing was verified",
    VerificationStatus.UNSUPPORTED: "the claim or its encoding needs constructs outside the supported formal language; nothing was verified",
    VerificationStatus.INVALID_FORMALIZATION: "no valid formal encoding of the claim was obtained; nothing was verified",
    VerificationStatus.AMBIGUOUS_TRANSLATION: "the claim admits materially different readings; nothing is verified until a reading is fixed",
    VerificationStatus.NOT_ELIGIBLE: "the claim is not a solver question under policy; it is routed to another check and nothing was verified",
    VerificationStatus.INTERNAL_ERROR: "the verification layer failed; nothing was verified",
}

_TRANSLATION_DISPLAY: dict[TranslationStatus, VerificationStatus] = {
    TranslationStatus.AMBIGUOUS_TRANSLATION: VerificationStatus.AMBIGUOUS_TRANSLATION,
    TranslationStatus.NOT_ELIGIBLE: VerificationStatus.NOT_ELIGIBLE,
    TranslationStatus.UNSUPPORTED: VerificationStatus.UNSUPPORTED,
    TranslationStatus.INVALID_FORMALIZATION: VerificationStatus.INVALID_FORMALIZATION,
    TranslationStatus.TRANSLATION_FAILED: VerificationStatus.INTERNAL_ERROR,
}


#: A translator release version ("0.3.0"): a record that names another one was made under that release's rules.
_RELEASE_VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?")


def translation_staleness(translation: TranslationResult) -> Optional[str]:
    """Why ``translation`` is not a record of the current translator, or ``None``. A record of another translator release
    ("0.3.0" where the current one is "0.4.0") was made under that release's rules (an earlier release recorded no claim
    text digest, grounding support, coverage or figure readings), so it is never displayed as a verdict (display
    INTERNAL_ERROR, release not permitted): translate and verify again. A record that names no release version (one a
    caller built in process) is read as it stands; the staleness of its claim text is :func:`compose_outcome`'s
    ``claim_text_sha256`` rule."""
    version = translation.translator_version
    if version != TRANSLATOR_VERSION and _RELEASE_VERSION_RE.fullmatch(version or ""):
        return (f"the translation was produced by translator release {version!r}, not the current {TRANSLATOR_VERSION!r} "
                "(a record of another release's rules): translate and verify again")
    return None


def _binding_problem(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> Optional[str]:
    """Why ``verification`` cannot be trusted for ``translation``; ``None`` when it binds.

    With ``signing_key`` the result must also carry a signature that verifies under
    that key (and, when ``key_id`` is given, name that key); a result whose status or
    content was altered after signing is rejected here rather than displayed.
    """
    if verification is None:
        return "no engine result was produced for the translated problem"
    problem = translation.problem
    if problem is None:
        return "an engine result was supplied but the translation carries no problem"
    stale_translation = translation_staleness(translation)
    if stale_translation is not None:
        return stale_translation
    if verification.claim_id != translation.claim_id or verification.request_id != translation.request_id:
        return "the engine result is for a different claim"
    if verification.problem_id != problem.problem_id or verification.binding.problem_digest != problem_digest(problem):
        return "the engine result is not bound to the translated problem (digest mismatch)"
    stale = stale_reasons(verification)
    if stale:
        return "the engine result is not current-policy evidence (" + "; ".join(stale) + "); verify the problem again under the current policy"
    if signing_key is not None:
        if not verification.signature:
            return f"the engine result is unsigned although a signing key is configured ({DiagnosticCode.SIGNATURE_INVALID.value})"
        if key_id is not None and verification.signature_key_id != key_id:
            return f"the engine result is signed with an unexpected key id ({DiagnosticCode.SIGNATURE_INVALID.value})"
        if not verify_signature(verification, signing_key):
            return f"the engine result's signature does not verify ({DiagnosticCode.SIGNATURE_INVALID.value})"
    return None


#: Engine diagnostics that make a definitive status no verdict on the claim (the engine's own list): a vacuous result (E108:
#: no premise used, or a COUNTEREXAMPLE over no premises), a counterexample that only reassigns a figure a source asserts
#: and the problem never asserts (E110) or conclusion symbols a source states and no premise mentions (E111), and a
#: circular proof whose premises restate the conclusion (E112: the claim was assumed, not derived).
_NO_VERDICT_CODES = NO_VERDICT_CODES
#: The coverage note that holds the evidence behind each coverage code (no verdict, or advisory).
_COVERAGE_KIND = {DiagnosticCode.UNASSERTED_FIGURE.value: "unasserted_definition", DiagnosticCode.UNENCODED_REASON.value: "unconstrained_symbol",
                  DiagnosticCode.UNASSERTED_FIGURE_ADVISORY.value: "unasserted_definition", DiagnosticCode.UNENCODED_REASON_ADVISORY.value: "unconstrained_symbol"}
_NO_VERDICT_NAMES = {DiagnosticCode.VACUOUS_RESULT.value: "Vacuous result", DiagnosticCode.UNASSERTED_FIGURE.value: "Unasserted figure",
                     DiagnosticCode.UNENCODED_REASON.value: "Unencoded reason", DiagnosticCode.CIRCULAR_PREMISES.value: "Circular encoding"}


def _coverage_notes(translation: Optional[TranslationResult], kind: str) -> list[CoverageNote]:
    """The translation's coverage notes of ``kind`` computed for exactly its problem's formulas."""
    if translation is None or translation.problem is None:
        return []
    digest = coverage_digest(translation.problem)
    return [n for n in translation.coverage if n.kind == kind and n.problem_digest == digest]


def _no_verdict_diagnostic(verification: VerificationResult, translation: Optional[TranslationResult] = None):
    """The engine diagnostic that makes this definitive status no verdict on the claim, or None. The engine decides: E110
    and E111 already carry source-linked evidence (the translation layer handed its coverage decision to the engine)."""
    if verification.status not in DEFINITIVE:
        return None
    return next((d for d in verification.diagnostics if d.code in _NO_VERDICT_CODES), None)


def _advisory_coverage(verification: VerificationResult) -> list:
    """The advisory coverage warnings (W110, W111) of a definitive status: the verdict on the encoding stands."""
    if verification.status not in DEFINITIVE:
        return []
    return [d for d in verification.diagnostics if d.code in ADVISORY_CODES]


def _is_vacuous(verification: VerificationResult, translation: Optional[TranslationResult] = None) -> bool:
    return _no_verdict_diagnostic(verification, translation) is not None


def display_status_for(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> VerificationStatus:
    """Deterministic display status for a translation plus optional engine result."""
    if translation.status is TranslationStatus.TRANSLATED:
        if _binding_problem(translation, verification, signing_key, key_id) is not None:
            return VerificationStatus.INTERNAL_ERROR
        assert verification is not None
        if _is_vacuous(verification, translation):
            return VerificationStatus.INVALID_FORMALIZATION
        return verification.status
    return _TRANSLATION_DISPLAY[translation.status]


# ----------------------------------------------------------------- summary text


def _label(problem: Problem, assertion_id: str) -> str:
    """An assertion's label as the summary shows it: model text on one line, its forgery words masked (``named.model_text``)."""
    for p in problem.premises:
        if p.id == assertion_id:
            return model_text(p.label or "(no label)", _LABEL_CHARS)
    if problem.conclusion is not None and problem.conclusion.id == assertion_id:
        return model_text(problem.conclusion.label or "(no label)", _LABEL_CHARS)
    return "(not in problem)"


def _grounding_note(problem: Problem, assertion_id: str) -> str:
    for p in problem.premises:
        if p.id == assertion_id:
            g = p.grounding
            if g is None:
                return "no grounding"
            note = f"{g.kind}, {g.certainty}"
            if g.verified is False:
                note += "; grounding check failed"
            return note
    return "not in problem"


def _listed(items: list[str]) -> str:
    shown = items[:_MAX_LISTED]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def _eligibility_lines(translation: TranslationResult) -> list[str]:
    e = translation.eligibility
    state = "eligible for the formal check" if e.eligible else f"not eligible; routed to {e.route_to or 'unresolved'}"
    reasons = _listed([truncate(r, _DIAG_CHARS) for r in e.reasons]) if e.reasons else "none recorded"
    return [f"Eligibility ({e.policy_version}): {e.eligibility_class.value}, {state}. Reasons: {reasons}."]


def _checked_lines(translation: TranslationResult) -> list[str]:
    problem = translation.problem
    if problem is None:
        return ["Checked: nothing was submitted to the solver."]
    text = (
        f"Checked: {problem.query} query over {len(problem.symbols)} symbol(s) and {len(problem.premises)} premise(s)"
    )
    if problem.conclusion is not None:
        text += f"; conclusion '{problem.conclusion.id}': {model_text(problem.conclusion.label or '(no label)', _LABEL_CHARS)}"
    lines = [text + "."]
    # the label is shown beside the verdict, so a figure it states that the expression does not check is named with it
    lines += [f"Note: the {truncate(d, _DIAG_CHARS)}." for d in translation.diagnostics if d.startswith("conclusion label states figure(s)")][:1]
    return lines


def _verification_lines(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
) -> list[str]:
    lines: list[str] = []
    problem = translation.problem
    if verification is None or problem is None:
        return lines
    binding_issue = _binding_problem(translation, verification, signing_key, key_id)
    if binding_issue is not None:
        lines.append(f"Engine result rejected: {binding_issue}.")
        return lines
    if translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION:
        lines.append(
            f"The translator's chosen encoding (one reading of an ambiguous claim) was run for inspection and returned {verification.status.value}; "
            "because the claim is ambiguous this is not displayed as a result."
        )
    vacuous = _no_verdict_diagnostic(verification, translation)
    if vacuous is not None:
        what = _NO_VERDICT_NAMES.get(vacuous.code, "No verdict")
        lines.append(
            f"{what}: the engine returned {verification.status.value} but {truncate(vacuous.message, _DIAG_CHARS * 2)} "
            f"({vacuous.code}); it is displayed as INVALID_FORMALIZATION, not as a verdict."
        )
        evidence = [e for n in _coverage_notes(translation, _COVERAGE_KIND.get(vacuous.code, "")) if n.source_asserted for e in n.evidence]
        if evidence:
            lines.append("The source asserts what the encoding left open: " + _listed([truncate(e, _DIAG_CHARS) for e in evidence]) + ".")
    if verification.premises_relied_on:
        lines.append("Premises relied on: " + _listed([f"{pid} ({_label(problem, pid)})" for pid in verification.premises_relied_on]) + ".")
    elif verification.status in DEFINITIVE:
        lines.append("Premises relied on: none recorded.")
    if verification.ungrounded_dependencies:
        lines.append(
            "Ungrounded dependencies (relied on but not established by the supplied material): "
            + _listed([f"{pid} ({_grounding_note(problem, pid)})" for pid in verification.ungrounded_dependencies])
            + "."
        )
    if verification.unverified_dependencies:
        lines.append(
            "Unverified dependencies (asserted by the translation, checked by no procedure): "
            + _listed([f"{pid} ({_grounding_note(problem, pid)})" for pid in verification.unverified_dependencies])
            + "."
        )
    if verification.premises_relied_on and not verification.ungrounded_dependencies and not verification.unverified_dependencies:
        lines.append("Ungrounded dependencies: none; unverified dependencies: none.")
    if verification.counterexample is not None:
        lines.append("Counterexample: " + _listed([f"{a.symbol}={a.value}" for a in verification.counterexample.assignments]) + ".")
    advisory = _advisory_coverage(verification)
    if advisory:
        lines.append(f"Advisory coverage warnings (the {verification.status.value} stands as the verdict on the encoding; no source statement "
                     "asserts what it leaves open, which the question may leave open on purpose, and if a source does, the translation omitted it): "
                     + _listed([f"{d.code}: {truncate(d.message, _DIAG_CHARS * 2)}" for d in advisory]) + ".")
    if verification.witness_model:
        lines.append("Witness assignment: " + _listed([f"{a.symbol}={a.value}" for a in verification.witness_model]) + ".")
    if verification.status not in DEFINITIVE and verification.diagnostics:
        lines.append("Engine diagnostics: " + _listed([f"{d.code}: {truncate(d.message, _DIAG_CHARS)}" for d in verification.diagnostics]) + ".")
    if verification.signature and signing_key is not None:
        lines.append(f"Engine result {verification.result_id} is signed (key {verification.signature_key_id}) and its signature was verified by this layer.")
    elif verification.signature:
        lines.append(
            f"Engine result {verification.result_id} carries a signature (key {verification.signature_key_id}) that this layer did not verify; "
            "the Overseer must verify it before relying on the result."
        )
    else:
        lines.append(f"Engine result {verification.result_id} is unsigned.")
    return lines


#: The kinds that claim the task's authority (``translate.grounding.TASK_AUTHORITY_KINDS``).
_TASK_KINDS = frozenset({"arithmetic_fact", "task_setting", "rubric_rule"})


def _unvalidated_authority(translation: TranslationResult) -> list[str]:
    """Premises whose kind claims the task's authority and that no record available to the translation layer validates:
    a figure no record states or contradicts, or a relation no record states (its figures occurring in a record never
    validate it)."""
    return sorted({c.target_id for c in translation.grounding_checks if c.verified is None and c.target_id not in _validated(translation)
                   and (c.method == "numeric_in_task" or (c.method == "relation_in_source" and c.kind in _TASK_KINDS))})


def _validated(translation: TranslationResult) -> set[str]:
    """Premises a later check of the same target validated (a relation an excerpt did not state but the task does)."""
    return {c.target_id for c in translation.grounding_checks if c.verified is True and c.method in ("numeric_in_task", "relation_in_source")}


def _unverified_relations(translation: TranslationResult) -> list[str]:
    """Premises whose numeric content is a relation that no record states (whatever their kind)."""
    validated = _validated(translation)
    return sorted({c.target_id for c in translation.grounding_checks if c.method == "relation_in_source" and c.verified is None and c.target_id not in validated})


def _grounding_lines(translation: TranslationResult) -> list[str]:
    lines: list[str] = []
    failed = [c for c in translation.grounding_checks if c.verified is False]
    if failed:
        lines.append("Failed grounding checks: " + _listed([f"{c.target_id}: {truncate(c.detail or c.method, _DIAG_CHARS)}" for c in failed]) + ".")
    unvalidated = _unvalidated_authority(translation)
    if unvalidated:
        lines.append("Unvalidated task authority (a kind that claims the task's authority, which no supplied text or task record available here "
                     "validates; it is not treated as a task fact): " + _listed(unvalidated) + ".")
    relations = _unverified_relations(translation)
    if relations:
        lines.append("Unverified relations (no record states the relation; figures a record states are no evidence for the relation that combines "
                     "them, so it is the translation's own, whatever its kind): " + _listed(relations) + ".")
    return lines


def _ambiguity_lines(translation: TranslationResult) -> list[str]:
    if translation.status is not TranslationStatus.AMBIGUOUS_TRANSLATION or translation.interpretation is None:
        return []
    flags = translation.interpretation.ambiguity_flags
    if not flags:
        return ["Ambiguity: the provider marked the claim ambiguous without listing specific flags."]
    return ["Ambiguity: " + _listed([
        f"{f.code}: {model_text(f.message, _DIAG_CHARS)}" + (f" (alternatives: {' | '.join(model_text(a, 80) for a in f.alternatives)})" if f.alternatives else "")
        for f in flags
    ]) + "."]


def _translation_diagnostic_lines(translation: TranslationResult) -> list[str]:
    if translation.status in (TranslationStatus.TRANSLATED, TranslationStatus.AMBIGUOUS_TRANSLATION, TranslationStatus.NOT_ELIGIBLE):
        return []
    if not translation.diagnostics:
        return []
    return ["Translation diagnostics: " + _listed([truncate(d, _DIAG_CHARS) for d in translation.diagnostics]) + "."]


def _structural_lines(structural: list[StructuralFinding]) -> list[str]:
    errors = [f for f in structural if f.severity == "error"]
    warnings = [f for f in structural if f.severity == "warning"]
    infos = [f for f in structural if f.severity == "info"]
    text = f"Structural findings (deterministic, not solver results): {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} informational."
    if errors:
        text += " Errors: " + _listed([f"{f.code}: {truncate(f.message, _DIAG_CHARS)}" for f in errors]) + "."
    return [text]


def _review_lines(review: Optional[SemanticFidelityReview], currency: Optional[tuple[str, list[str]]] = None) -> list[str]:
    if review is None:
        return []
    text = f"Advisory semantic-fidelity review: {review.verdict} (advisory only; not a verification)."
    if review.issues:
        text += " Issues: " + _listed([model_text(i, _DIAG_CHARS) for i in review.issues]) + "."
    if currency is not None:
        state, changed = currency
        if state == "stale":
            text += f" The review is STALE: it was made for other inputs ({_listed(changed)}), so it does not count for the current claim."
        elif state == "unbound":
            text += " The review is not confirmed against the current inputs (no binding, or the report is not at hand)."
        elif state == "without_evidence":
            text += " The review was made without the supporting claims, task and supplied texts, so it cannot count as an approval."
    if review.evidence_truncated:
        text += f" Supplied text(s) shown to the reviewer only in part: {', '.join(review.evidence_truncated[:6])}."
    return [text]


def _repair_lines(translation: TranslationResult) -> list[str]:
    semantic = [r for r in translation.repairs if r.kind == "semantic"]
    if not semantic:
        return []
    return ["Semantic changes on retry (recorded apart from syntax repairs): " + _listed([
        f"attempt {r.attempt} after {r.after_attempt} ({', '.join(r.rejected_for)}): conclusion {r.conclusion}; " + "; ".join(model_text(c, 160) for c in r.changes[1:4])
        for r in semantic]) + "."]


def _release_lines(release: Optional[ReleaseAssessment]) -> list[str]:
    if release is None:
        return []
    if release.permitted:
        return [f"Release ({release.policy}): permitted on this claim's checks (formal status {release.formal_status.value}, the engine's release check "
                "passed, evidence resolved, fidelity review faithful and current)."]
    return [f"Release ({release.policy}): NOT permitted; formal status {release.formal_status.value} is reported separately. Unresolved: "
            + _listed([truncate(u, _DIAG_CHARS) for u in release.unresolved]) + "."]


def _diagnosis_lines(named: Sequence[NamedDiagnostic], engine_state: str, incomplete: Sequence[str], *, room: Optional[int] = None) -> list[str]:
    """The diagnosis section (``named.diagnosis_section``), each line cut to its summary length. It says nothing about the
    status, which it never changes. Blocking diagnostics (warning or error by effective severity) are listed before the
    info records, each group in its own order, so a section shortened for length never hides a warning behind a record.

    ``room`` is what the summary's other lines leave (:func:`build_summary`): the advisory section never displaces a line
    the summary shows without it (failed grounding checks, structural findings, the review). It is fitted by showing
    fewer lines ("- and N more"; the outcome's ``named_diagnostics`` keeps every one), then shorter ones; the heading,
    the count and a note that the diagnosis is incomplete always stay, and only when even they do not fit is the summary
    cut as before."""
    items = list(named)
    shown = [d for d in items if is_blocking(d)] + [d for d in items if not is_blocking(d)]

    def section(max_lines: int, line_chars: int) -> list[str]:
        return [truncate(line, line_chars) for line in diagnosis_section(shown, engine_state=engine_state, incomplete=list(incomplete), max_lines=max_lines)]

    full = section(6, _DIAGNOSIS_LINE_CHARS)
    if room is None or len("\n".join(full)) <= room:
        return full
    for line_chars in (_DIAGNOSIS_LINE_CHARS, _FITTED_LINE_CHARS):
        for max_lines in range(6, 0, -1):
            candidate = section(max_lines, line_chars)
            if len("\n".join(candidate)) <= room:
                return candidate
    return section(1, _FITTED_LINE_CHARS)


#: The length diagnosis lines are cut to when the section must also be shortened line by line to fit (:func:`_diagnosis_lines`).
_FITTED_LINE_CHARS = 160


def _fit(body: str, tail: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """Join ``body`` and ``tail`` within ``limit`` characters, cutting the body, never the tail."""
    sep = "\n"
    if len(body) + len(sep) + len(tail) <= limit:
        return body + sep + tail
    room = limit - len(sep) - len(tail)
    marker = " [summary truncated]"
    if room <= len(marker):
        return tail[:limit]
    return body[: room - len(marker)].rstrip() + marker + sep + tail


def build_summary(
    claim: ClaimRecord,
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    review: Optional[SemanticFidelityReview],
    structural: list[StructuralFinding],
    display: VerificationStatus,
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
    release: Optional[ReleaseAssessment] = None,
    review_state: Optional[tuple[str, list[str]]] = None,
    named: Sequence[NamedDiagnostic] = (),
    engine_state: str = "not_computed",
    incomplete: Sequence[str] = (),
) -> str:
    """Deterministic plain-language summary; ends with ``SCOPE_STATEMENT`` verbatim. The release line comes third, so a
    long summary is cut elsewhere. The argument diagnosis section follows the verification lines; ``engine_state`` is
    ``named.rules_state`` of the trusted engine result (``not_computed`` without one). Every line is one line
    (``named.one_line``) and the model text it shows (labels, ambiguity flags, review issues, retry changes) has its
    forgery words masked (``named.model_text``), so no model text can write a status, a release line or a section."""
    lines: list[str] = [
        f"Claim {claim.claim_id} (role {claim.claim_role}, subject {claim.subject}): "
        f"translation {translation.status.value}; display status {display.value}.",
        f"Status meaning: {STATUS_MEANING[display]}.",
    ]
    lines += _release_lines(release)
    lines += _eligibility_lines(translation)
    lines += _checked_lines(translation)
    lines += _verification_lines(translation, verification, signing_key, key_id)
    if translation.status is TranslationStatus.TRANSLATED and verification is None:
        lines.append("Engine result rejected: no engine result was produced for the translated problem.")
    after: list[str] = []
    after += _grounding_lines(translation)
    after += _ambiguity_lines(translation)
    after += _repair_lines(translation)
    after += _translation_diagnostic_lines(translation)
    after += _structural_lines(structural)
    after += _review_lines(review, review_state)
    # the advisory section gets the room the other lines leave: it is fitted into it, so it never pushes them out
    # every line is one line: no label, meaning, note or message interpolated into it can start a summary line of its own
    lines = [one_line(line) for line in lines]
    after = [one_line(line) for line in after]
    others = len("\n".join(lines + after)) + 1 + len(SCOPE_STATEMENT)
    section = [one_line(line) for line in _diagnosis_lines(named, engine_state, incomplete, room=SUMMARY_MAX_CHARS - others - 1)]
    return _fit("\n".join(lines + section + after), SCOPE_STATEMENT)


def assess_release(
    translation: TranslationResult,
    verification: Optional[VerificationResult],
    review: Optional[SemanticFidelityReview],
    structural: list[StructuralFinding],
    display: VerificationStatus,
    review_state: Optional[tuple[str, list[str]]] = None,
    engine_check: Optional[ReleaseCheck] = None,
    named_diagnostics: Sequence[NamedDiagnostic] = (),
    diagnosis_incomplete: Sequence[str] = (),
) -> ReleaseAssessment:
    """Whether this claim's checks permit releasing the answer automatically (see :class:`~.contracts.ReleaseAssessment`).
    Deterministic; the formal status is reported, never upgraded or downgraded, and anything unresolved is listed.

    ``engine_check`` is the engine's own release check of ``verification`` (``engine.release.release_check``, under the
    composer's key): release needs it to pass. Its reasons that this assessment does not state in its own terms
    (authentication, binding, currency, missing dependency evidence) are listed here; without it a passing formal check
    cannot permit release, since nothing confirmed that the result is authentic and current.

    ``named_diagnostics`` are the claim's named diagnostics (every layer): any whose effective severity is warning or error
    is unresolved, so a capped warning still blocks release; info never blocks. Those shown at warning or error are listed
    as "named defect on this claim: <code> (<defect>)", the capped ones, shown at info, under their own line with their cap
    and no defect label (:func:`~epinoic_logic.named.blocking_release_lines`).
    ``diagnosis_incomplete`` names the diagnosis rules that did not finish (a rule that raised, an overflow, an incomplete
    engine stage): any is unresolved, since a diagnosis that was not computed is never read as "none found"."""
    unresolved: list[str] = []
    problem = translation.problem
    passing = _PASSING.get(problem.query) if problem is not None else None
    formal_ok = translation.status is TranslationStatus.TRANSLATED and passing is not None and display is passing
    if translation.status is not TranslationStatus.TRANSLATED:
        unresolved.append(f"translation {translation.status.value}: no encoding was accepted as the claim's")
    elif not formal_ok:
        unresolved.append(f"formal check: display status {display.value}, not {passing.value if passing else 'a passing status'} for the "
                          f"{problem.query if problem else 'unknown'} query")
    evidence_ok = True
    if verification is not None and formal_ok:
        if verification.ungrounded_dependencies:
            evidence_ok = False
            unresolved.append("ungrounded dependencies (relied on, not established by the supplied material or the task): " + ", ".join(verification.ungrounded_dependencies[:8]))
        if verification.unverified_dependencies:
            evidence_ok = False
            unresolved.append("unverified dependencies (asserted, checked by no procedure): " + ", ".join(verification.unverified_dependencies[:8]))
    if formal_ok:
        if engine_check is None:
            unresolved.append("the engine's release check was not run on this result")
        elif not engine_check.eligible:
            # what the formal status and the dependency lists above already state is not repeated
            # the engine's "named defect" is stated below only when the claim's own list names a blocking diagnostic
            claim_names = any(is_blocking(d) for d in named_diagnostics)
            stated = ("no positive verdict", "no verdict on the claim", "unresolved dependencies") + (("named defect", "capped diagnostic") if claim_names else ())
            extra = [r for r in engine_check.reasons if not r.startswith(stated)]
            if extra:
                unresolved.append("engine release check: " + "; ".join(extra[:4]))
    failed = sorted({c.target_id for c in translation.grounding_checks if c.verified is False})
    if failed:
        evidence_ok = False
        unresolved.append("failed grounding checks: " + ", ".join(failed[:8]))
    unvalidated = _unvalidated_authority(translation)
    if unvalidated:
        evidence_ok = False
        unresolved.append("task authority unvalidated (a trusted kind no supplied text or task record validates): " + ", ".join(unvalidated[:8]))
    partial = [s.target_id for s in translation.grounding_support if s.support in ("partial", "failed")]
    if partial:
        evidence_ok = False
        unresolved.append("references not all located: " + ", ".join(partial[:8]))
    changed = [r for r in translation.repairs if r.kind == "semantic" and r.conclusion not in ("unchanged", "equivalent", "stronger")]
    if changed:
        unresolved.append("a retry changed the claim: " + ", ".join(f"attempt {r.attempt} ({r.conclusion})" for r in changed))
    added = [r for r in translation.repairs if r.kind == "semantic" and "unasserted_figure" in r.rejected_for and not r.supported_by_source and r not in changed]
    if added:
        unresolved.append("a retry added premises no source asserts: " + ", ".join(f"attempt {r.attempt}" for r in added))
    errors = [f.code for f in structural if f.severity == "error"]
    if errors:
        unresolved.append("structural errors: " + ", ".join(sorted(set(errors))[:8]))
    unresolved.extend(blocking_release_lines(named_diagnostics, "named defect on this claim", 8))
    if diagnosis_incomplete:
        unresolved.append("argument diagnosis incomplete (not computed is never read as none found): " + "; ".join(list(diagnosis_incomplete)[:4]))
    if review is None:
        fidelity = "missing"
        unresolved.append("no semantic-fidelity review: translation fidelity is unresolved")
    else:
        state = review_state[0] if review_state is not None else "unbound"
        if state == "stale":
            fidelity = "stale"
            unresolved.append("the fidelity review is stale: " + ", ".join((review_state or ("", []))[1][:6]))
        elif state == "unbound":
            fidelity = "unbound"
            unresolved.append("the fidelity review is not confirmed against the current inputs")
        elif state == "without_evidence":
            fidelity = "without_evidence"
            unresolved.append("the fidelity review was made without the evidence (supporting claims, task, supplied texts)")
        elif review.evidence_truncated:
            fidelity = review.verdict
            unresolved.append("the fidelity reviewer saw supplied text(s) only in part: " + ", ".join(review.evidence_truncated[:6]))
        else:
            fidelity = review.verdict
            if review.verdict != "faithful":
                unresolved.append(f"the fidelity review is {review.verdict}")
    return ReleaseAssessment(permitted=not unresolved, formal_status=display, formal_check_passed=formal_ok, evidence_resolved=evidence_ok and formal_ok,
                             fidelity=fidelity, unresolved=[truncate(u, 500) for u in unresolved], policy=RELEASE_POLICY)  # type: ignore[arg-type]


# -------------------------------------------------------------------- compose


def compose_outcome(
    claim: ClaimRecord,
    translation: TranslationResult,
    verification: Optional[VerificationResult] = None,
    review: Optional[SemanticFidelityReview] = None,
    structural: Iterable[StructuralFinding] = (),
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
    report: Optional[SpecialistReport] = None,
    task: Optional[TaskRecord] = None,
) -> ClaimVerificationOutcome:
    """Assemble the Overseer-facing outcome for one claim.

    ``verification`` is used only when it binds to the translated problem (same
    claim, same problem id and digest) and, when ``signing_key`` is given, carries a
    signature that verifies under it; anything else is displayed as
    ``INTERNAL_ERROR`` and explained in the summary. Agent self-reports play no part.
    A translation that carries ``claim_text_sha256`` must have been produced for this
    claim's exact text; otherwise it is stale and ``ValueError`` is raised rather than
    displaying it under another text. With ``report`` (and ``task``) a review's binding is
    checked against the current inputs: a review made for another version of a supporting
    claim or supplied text is stale and does not count toward release.
    """
    if translation.claim_id != claim.claim_id or translation.request_id != claim.request_id:
        raise ValueError("translation does not belong to the claim")
    if translation.claim_text_sha256 is not None and translation.claim_text_sha256 != sha256_text(claim.claim_text):
        raise ValueError("translation was produced for a different text of this claim (stale translation); it is not displayed under the current text")
    if review is not None and review.translation_id != translation.translation_id:
        raise ValueError("review does not belong to the translation")
    findings = list(structural)
    display = display_status_for(translation, verification, signing_key, key_id)
    review_state = review_currency(review, claim, translation, report, task) if review is not None else None
    trusted = verification if display is not VerificationStatus.INTERNAL_ERROR else None
    engine_check = (release_check(trusted, translation.problem, signing_key=signing_key, key_id=key_id)
                    if trusted is not None and translation.problem is not None else None)
    named, incomplete, engine_state = outcome_diagnosis(claim, translation, verification, display, signing_key, key_id, report, task)
    release = assess_release(translation, trusted, review, findings, display, review_state, engine_check, named, incomplete)
    summary = build_summary(claim, translation, verification, review, findings, display, signing_key, key_id, release, review_state,
                            named=named, engine_state=engine_state, incomplete=incomplete)
    return ClaimVerificationOutcome(
        outcome_id=new_id("oc"),
        request_id=claim.request_id,
        report_id=claim.report_id,
        claim_id=claim.claim_id,
        translation=translation,
        verification=verification,
        semantic_review=review,
        structural_findings=findings,
        display_status=display,
        summary=summary,
        created_at=utc_now_rfc3339(),
        release=release,
        named_diagnostics=named,
        diagnosis_incomplete=incomplete,
    )


def outcome_diagnosis(claim: ClaimRecord, translation: TranslationResult, verification: Optional[VerificationResult], display: VerificationStatus,
                      signing_key: Optional[bytes] = None, key_id: Optional[str] = None, report: Optional[SpecialistReport] = None,
                      task: Optional[TaskRecord] = None) -> tuple[list[NamedDiagnostic], list[str], str]:
    """``(named diagnostics, incomplete rules, engine state)`` of one claim, as :func:`compose_outcome` derives them (a reader
    that re-derives an outcome, such as the Overseer's translation and delivery checks, calls this). Only an engine result
    that binds to the translated problem, is current and (with the key) carries a signature that verifies contributes its
    diagnostics; anything else is "not computed" for the engine layer. Deterministic; never raises: a failure is recorded
    as incomplete and names nothing."""
    trusted = (verification if verification is not None and translation.problem is not None
               and _binding_problem(translation, verification, signing_key, key_id) is None else None)
    try:
        ctx, missing = build_context(claim, translation, display, verification=trusted, report=report, task=task)
        diagnosis = claim_diagnostics(ctx, missing)
    except Exception as exc:  # noqa: BLE001 - the diagnosis only adds; its failure is named, never raised
        return [], [f"diag_core: {type(exc).__name__}"], rules_state(trusted.argument_rules)[0] if trusted is not None else "not_computed"
    engine_state = rules_state(trusted.argument_rules)[0] if trusted is not None else "not_computed"
    return list(diagnosis.diagnostics), list(diagnosis.incomplete), engine_state


def verify_claim(
    claim: ClaimRecord,
    report: SpecialistReport,
    translator: Translator,
    reviewer: Optional[SemanticReviewer] = None,
    structural: Iterable[StructuralFinding] = (),
    config: SolverConfig = SolverConfig(),
    signing_key: Optional[bytes] = None,
    key_id: Optional[str] = None,
    task: Optional[TaskRecord] = None,
) -> ClaimVerificationOutcome:
    """Translate, verify with the engine, optionally review, and compose the outcome.

    The engine runs only for ``TRANSLATED`` and ``AMBIGUOUS_TRANSLATION`` results
    that carry a problem. For an ambiguous claim the best-reading problem is still
    verified so reviewers can inspect it, but the display status stays
    ``AMBIGUOUS_TRANSLATION``, and the engine's argument diagnosis is capped at info
    on that assumed reading (``capped_from`` keeps the uncapped severity, which
    release still reads). The reviewer, when given, runs whenever a problem exists,
    with the report's evidence (and ``task``, the task record, when the caller holds it).
    """
    translation = translator.translate(claim, report, task=task)
    verification: Optional[VerificationResult] = None
    if translation.problem is not None and translation.status in (
        TranslationStatus.TRANSLATED,
        TranslationStatus.AMBIGUOUS_TRANSLATION,
    ):
        cap = ("info", "ambiguous_translation") if translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION else None
        verification = engine_verify(translation.problem, config, signing_key=signing_key, key_id=key_id, severity_cap=cap)
    review: Optional[SemanticFidelityReview] = None
    if reviewer is not None and translation.problem is not None:
        review = reviewer.review(claim, translation, report=report, task=task)
    return compose_outcome(claim, translation, verification, review, structural, signing_key=signing_key, key_id=key_id, report=report, task=task)
