"""Translation pipeline: one specialist claim -> one ``TranslationResult``.

Order of operations (each step is deterministic code except the provider call):

1. **Eligibility** (``eligibility.decide_eligibility``): policy decides whether the
   claim is a solver question at all. The agent's self-report is ignored.
2. **Subject policy** (``subjects``): the IB subject profile may narrow the
   decision further. A class the profile does not allow (for example a
   QUANTITATIVE_CLAIM in a literature course) is downgraded to
   ``NOT_ELIGIBLE_OTHER`` with the reason recorded. An ineligible claim never
   reaches a provider.
3. **Provider** (``providers``): the model proposes a formalization as JSON text.
   The text is untrusted data. It is parsed with a strict JSON parser, validated
   against the IR schema, checked by the engine validator (identifiers, sorts,
   policy allowlist, limits), and its ``request_id``/``claim_id`` must match the
   claim. Schema and validity failures are fed back once as ``prior_diagnostics``;
   policy (``UNSUPPORTED``) and identity failures are not retried.
4. **Grounding** (``grounding``): every source reference is checked (an excerpt located, a document and
   locator checked) and keeps its own outcome; only complete support verifies a grounding. Figures are typed
   quantities (``20%`` states ``0.2`` and ``1/5`` alike), and a figure stated as rounded ("x is 0.33 to 2 decimal
   places") states the interval of its tolerance, so a premise that transcribes it exactly (``x = 0.33``) or at exactly
   that interval (``0.325 <= x < 0.335``) is grounded by it, and a wider or narrower interval is not. A premise whose kind claims the task's authority
   (``arithmetic_fact``, ``task_setting``, ``rubric_rule``) is validated against the supplied texts and the task
   record: the model's label confers nothing. A check confers authority only on the premise's WHOLE numeric
   content (``relations``): an assignment (each symbol compared with a literal) by records that state each figure
   so that it establishes that comparison, and any other numeric content (a relation that combines symbols, such
   as ``speed = d / 8``) only by a record that states that same formula as a given; figures occurring in a record
   are never evidence for the relation that combines them. A validated premise is ``verified=True``
   (established); a refuted one (the task record was given and states no such figure, or a record states a
   conflicting figure: 120 km where the premise says 160 km) is ``verified=False``, an evidence failure the engine
   lists as an ungrounded dependency; one no record validates or refutes (a model-invented relation among them,
   whatever its kind) stays ``verified=None``, which the engine lists as an unverified dependency and the outcome
   as unvalidated task authority or an unverified relation (release blocked). ``verified`` is set by code only.
4b. **Coverage** (``coverage``): two encoding shapes leave a figure open: a premise that only defines an atom by a
   comparison of a figure no other premise mentions (``b <-> (n = 17)`` with ``n`` free), and a conclusion that
   compares symbols no premise mentions (``x < y`` with ``y`` free). Whether a source ASSERTS what the shape leaves
   open (the claim, a supporting claim, a supplied text or the task states it in a sentence that does not define
   or suppose; a figure of a supplied text or of the task in a clause about the symbol) is decided here from every
   source and handed to the engine as an application record
   (``coverage.apply_coverage_evidence``: a grounding verified in this process on exactly the symbols involved,
   its references the asserting spans). The engine then reports ``E110``/``E111`` (no verdict) exactly when a
   source asserts it, and the advisory ``W110``/``W111`` (the COUNTEREXAMPLE stands as the verdict on the
   encoding) otherwise, so the signed result, this decision and the displayed status agree. Whether a source
   asserts a figure is read clause by clause (``assertion``), and only a clause the reader POSITIVELY recognises
   as the writer's own statement asserts it: a figure mentioned in a question, a condition ("if", "when n equals
   17", "n = 17 ⇒ b"), a supposition or hypothesis, a definition ("exactly when", "b ⟺ n = 17"), a possibility or
   hedge ("could", "probably"), reported speech ("according to rumour"), a claim to test, a negation, a
   quantification ("for any", "in some cases") or a disjunction is not asserted, and neither is one in a
   construction the reader does not recognise (the counterexample then stands with the advisory warning); an
   asserted figure is evidence only when it states
   what the definition compares ("more than 17" asserts no ``n = 17``) and is about the encoding's symbols (a figure
   that counts something else, "I checked 3 values", is not). An ``E110`` output is INVALID_FORMALIZATION with the
   source evidence (fed back once: assert what the source states). A translator is never told to add a premise
   because adding it would produce entailment, only because a source asserts it, and the retry may add only that
   (step 4e).
4c. **Circularity** (``engine.runner.circular_premises``): a conclusion that is itself a premise, or each of whose
   conjuncts is one, where those premises are the writer's own (no check in this process established them, whatever
   kind their grounding claims: ``engine.authority.assumed_grounding``, policy 2026.10-v5), is assumed, not derived:
   INVALID_FORMALIZATION with that diagnostic (fed back once). A restated premise that a check verified against the
   task record or a supplied text is a transcription.
4d. **Stated precision and exactness** (``precision``): every figure the encoding compares is tied to the source span
   that states it and read from the WORDING: exact ("exactly", "without rounding": never widened; an interval in
   its place is rejected as a weakening), given (a task figure: never widened), rounded (a rounding cue or a figure
   stated as the result of a written calculation: an exact equality in its place is rejected only when its stated
   tolerance changes the verdict, and the retry must give exactly that tolerance), or unstated (when the two
   readings give different verdicts the translation is AMBIGUOUS_TRANSLATION). The solver never decides that a
   figure was rounded. Every reading is recorded (``TranslationResult.figure_readings``).
4e. **Retries**: an accepted attempt that follows a rejected one is recorded (``TranslationResult.repairs``): a
   syntax repair, or a semantic change with every change listed. After a semantic rejection the new conclusion is
   compared with the earlier conclusion read as its source states it; a conclusion that is weaker or incomparable
   does not inherit the claim's approval: the translation is AMBIGUOUS_TRANSLATION, never a verdict. After a
   rejection for an unasserted figure (the only rejection that asks for a premise), every premise the retry adds must
   be what that rejection's source evidence asserts: it follows from the earlier premises with the source-asserted
   atoms asserted (the stated figure, the atom, or a reformulation of the definition), or a check in this process
   established it. A retry that adds anything else earned its verdict with a premise no source asserts: the
   translation is AMBIGUOUS_TRANSLATION (flag ``retry_added_premise``), never a verdict.
5. **Status**: ``TRANSLATED``, or ``AMBIGUOUS_TRANSLATION`` when the provider
   flagged ambiguity, ``UNSUPPORTED`` when it declined or the validator rejected a
   construct by policy, ``INVALID_FORMALIZATION`` when no valid encoding was
   obtained, ``TRANSLATION_FAILED`` when the provider failed or its output exceeds the provider-text bound
   (``parsing.MAX_PROVIDER_TEXT_BYTES``, 64 KiB, refused before parsing and not retried), ``NOT_ELIGIBLE``
   from steps 1 and 2.

Nothing in this module evaluates model output; the problem is data all the way
to the engine. Logs carry identifiers and statuses only, never claim or student text.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional, Sequence

from pydantic import ValidationError

from .. import lexis
from ..engine.argument import gloss
from ..engine.errors import DiagnosticCode
from ..engine.results import SolverConfig
from ..engine.runner import (assumed_grounding, circular_premises, conclusion_valid_alone, equivalent_premises, premises_inconsistent,
                             unasserted_figure_definitions, verify as engine_verify)
from ..engine.statuses import VerificationStatus
from ..engine.validator import validate_problem
from ..ir.schema import DEFAULT_LIMITS, Limits, Problem
from ..version import IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION
from . import prompts, subjects
from .common import new_id, truncate, utc_now_rfc3339
from .contracts import (
    AmbiguityFlag,
    ClaimRecord,
    CoverageNote,
    EligibilityClass,
    EligibilityDecision,
    FigureReading,
    GroundingCheck,
    GroundingSupport,
    Interpretation,
    ProviderInfo,
    RepairRecord,
    SpecialistReport,
    TaskRecord,
    TranslationResult,
    TranslationStatus,
    sha256_text,
)
from .coverage import apply_coverage_evidence, assess_definitions, assess_unconstrained
from .diag_argument import REASON_CONNECTIVES, mask_quotations
from .eligibility import decide_eligibility
from .grounding import check_problem_grounding, grounding_support
from .parsing import ProviderOutputError, ProviderOutputTooLarge, asserted_verified_paths, parse_json_object
from .precision import added_premise_support, compare_conclusions, decide_precision, premise_changes, read_sites, reference_reading
from .providers.base import ProviderError, TranslationProvider, TranslationRequest
from .quantities import SourceText
from .roles import premise_roles as _premise_roles
from .subjects import SubjectProfile

__all__ = ["Translator", "apply_subject_policy", "REQUIRED_OUTPUT_KEYS", "SEMANTIC_REASONS", "source_texts", "widen_rounded_literals"]

logger = logging.getLogger(__name__)

REQUIRED_OUTPUT_KEYS: tuple[str, ...] = ("problem", "interpretation", "ambiguous", "unsupported_reason")
_MAX_DIAGNOSTIC_CHARS = 500
#: An ambiguity flag's statement that a figure is encoded as stated ("literal equality to 15 is encoded").
_ENCODED_CLAIM_RE = re.compile(r"\b(?:literal\s+)?equalit(?:y|ies)\b[^.;]*\b(?:is|are)\s+encoded\b|\bencoded\s+as\s+(?:a\s+)?literal\s+equalit", re.IGNORECASE)
_MAX_SCHEMA_ERRORS = 12


def apply_subject_policy(eligibility: EligibilityDecision, profile: SubjectProfile) -> EligibilityDecision:
    """Narrow an eligibility decision by the subject profile.

    An eligible class the profile does not allow becomes ``NOT_ELIGIBLE_OTHER``
    (not eligible, routed per :func:`subjects.route_for`) with the original reasons
    kept and the downgrade reason appended. Everything else is returned unchanged.
    """
    if not eligibility.eligible or profile.allows(eligibility.eligibility_class):
        return eligibility
    downgraded = EligibilityClass.NOT_ELIGIBLE_OTHER
    return EligibilityDecision(
        eligibility_class=downgraded,
        eligible=False,
        decided_by="deterministic",
        reasons=[
            *eligibility.reasons,
            f"class {eligibility.eligibility_class.value} not allowed for subject profile {profile.key}",
        ],
        route_to=subjects.route_for(downgraded),
        policy_version=eligibility.policy_version,
    )


#: Rejections of a VALID problem for its meaning: the retry changes what is encoded (a semantic change, compared with
#: the earlier conclusion). Every other rejection is of the output's form (a syntax repair).
SEMANTIC_REASONS = frozenset({"stated_precision", "exactness", "circular", "unasserted_figure"})


class _Rejected(Exception):
    """Internal: an attempt produced output the pipeline cannot accept. ``problem`` is the valid problem a semantic
    rejection was about (``reason`` names the rule); a form rejection carries none."""

    def __init__(self, status: TranslationStatus, diagnostics: list[str], retryable: bool, *, reason: str = "form",
                 problem: Optional[Problem] = None, coverage: Optional[list[CoverageNote]] = None,
                 readings: Optional[list[FigureReading]] = None, checks: Optional[list[GroundingCheck]] = None) -> None:
        super().__init__(diagnostics[0] if diagnostics else status.value)
        self.status = status
        self.diagnostics = diagnostics
        self.retryable = retryable
        self.reason = reason
        self.problem = problem
        self.coverage = list(coverage or [])
        self.readings = list(readings or [])
        self.checks = list(checks or [])


@dataclass
class _Accepted:
    status: TranslationStatus
    problem: Problem
    interpretation: Interpretation
    grounding_checks: list[GroundingCheck]
    notes: list[str] = field(default_factory=list)
    readings: list[FigureReading] = field(default_factory=list)
    coverage: list[CoverageNote] = field(default_factory=list)
    support: list[GroundingSupport] = field(default_factory=list)
    roles: list = field(default_factory=list)
    asserted_verified: list[str] = field(default_factory=list)


def _half_unit(value: str) -> Optional[tuple[str, str]]:
    """``(lower, upper)`` bounds of a decimal literal written to n places: within half a unit of its last place."""
    from decimal import Decimal
    if "." not in value or "/" in value:
        return None
    places = len(value.split(".", 1)[1])
    d = Decimal(value)
    half = Decimal(5).scaleb(-(places + 1))
    return format(d - half, "f"), format(d + half, "f")


_LABEL_FIGURE_RE = re.compile(r"(?<![\w.])[-\u2212]?\d(?:[\d,]*\d)?(?:\.\d+)?(?![\w])")


def _fraction(text: str) -> Optional[Fraction]:
    try:
        return Fraction(text.replace(",", "").replace("\u2212", "-"))
    except (ValueError, ZeroDivisionError):
        return None


def label_beyond_expression(problem: Problem) -> list[str]:
    """A note when the conclusion's label states a figure that its expression does not check: neither a literal of the
    conclusion (to its stated precision, or as a percentage of it) nor a figure of the glosses of the symbols it uses. The
    receipt shows the label beside the verdict, so a label that states more than the expression checks is named; the
    verdict is unchanged (the label is not compiled)."""
    concl = problem.conclusion
    if concl is None or not concl.label:
        return []
    expr = concl.expr.model_dump(mode="json", exclude_none=True)
    literals: list[Fraction] = []
    names: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            if node.get("op") in ("int", "real") and isinstance(node.get("value"), str):
                v = _fraction(node["value"])
                if v is not None:
                    literals.append(abs(v))
            if node.get("op") == "var" and isinstance(node.get("name"), str):
                names.add(node["name"])
            for x in node.values():
                walk(x)
    walk(expr)
    glossed = " ".join(sym.meaning or "" for sym in problem.symbols if sym.name in names)
    gloss_values = {abs(v) for v in (_fraction(m) for m in _LABEL_FIGURE_RE.findall(glossed)) if v is not None}

    def checked(text: str) -> bool:
        v = _fraction(text)
        if v is None:
            return True
        v = abs(v)
        if v in gloss_values:
            return True
        bounds = _half_unit(text.replace(",", "").replace("\u2212", "-").lstrip("-"))
        for lit in literals:
            for scaled in (lit, lit * 100, lit / 100):
                if scaled == v or (bounds is not None and Fraction(bounds[0]) <= scaled < Fraction(bounds[1])):
                    return True
        return False
    missing = [f for f in dict.fromkeys(_LABEL_FIGURE_RE.findall(concl.label)) if not checked(f)]
    if not missing:
        return []
    return [truncate(f"conclusion label states figure(s) {missing[:6]} that its expression does not check (no literal of the conclusion "
                     "and no gloss of its symbols states them): the label may say more than the verdict shows", _MAX_DIAGNOSTIC_CHARS)]


def widen_rounded_literals(problem: Problem) -> tuple[Optional[Problem], list[str]]:
    """``(problem with every equality to a decimal literal widened to its stated precision, the literals widened)``; ``(None,
    [])`` when the problem has no such equality. ``x = 0.67`` becomes ``x >= 0.665 and x < 0.675``."""
    data = problem.model_dump(mode="json", exclude_none=True)
    found: list[str] = []

    def lit(node) -> Optional[str]:
        return node.get("value") if isinstance(node, dict) and node.get("op") == "real" and isinstance(node.get("value"), str) and "." in node["value"] else None

    def walk(node):
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        node = {k: walk(v) for k, v in node.items()}
        if node.get("op") == "eq":
            left, right = node.get("left"), node.get("right")
            value, other = (lit(right), left) if lit(right) is not None and lit(left) is None else ((lit(left), right) if lit(left) is not None and lit(right) is None else (None, None))
            bounds = _half_unit(value) if value is not None else None
            if bounds is not None:
                found.append(value)
                return {"op": "and", "args": [{"op": "ge", "left": other, "right": {"op": "real", "value": bounds[0]}},
                                              {"op": "lt", "left": other, "right": {"op": "real", "value": bounds[1]}}]}
        return node
    data["premises"] = walk(data.get("premises", []))
    if data.get("conclusion") is not None:
        data["conclusion"] = walk(data["conclusion"])
    if not found:
        return None, []
    try:
        return Problem.model_validate(data), list(dict.fromkeys(found))
    except (ValidationError, ValueError):
        return None, []


def _expr_names(node) -> set[str]:
    """The symbol names an expression dict mentions (iterative)."""
    out: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("op") == "var" and isinstance(n.get("name"), str):
                out.add(n["name"])
                continue
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return out


def _conjunct_dicts(node: dict) -> list[dict]:
    """The "and" conjuncts of an expression dict, nested conjunctions flattened."""
    out: list[dict] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict) and n.get("op") == "and":
            stack.extend(reversed(n.get("args") or []))
        else:
            out.append(n)
    return out


#: Reason connectives whose reason FOLLOWS them ("X because Y", "since Y, X"); with every other connective of
#: ``diag_argument.REASON_CONNECTIVES`` the reason precedes it ("Y, so X").
_REASON_AFTER = frozenset({("because",), ("since",), ("given", "that"), ("due", "to", "the", "fact", "that"), ("as", "shown", "by"), ("as", "seen", "in"),
                           ("as", "demonstrated", "by"), ("as", "evidenced", "by")})
#: Words that split a claim into clauses for the partial-encoding rule (and ";").
_CLAUSE_SPLIT_WORDS = frozenset({"but", "however", "although", "while", "whereas"})
_SENTENCE_END = frozenset(".!?;")


def _boundaries(text: str) -> list[int]:
    """Character offsets that end a clause: ".", "!", "?" and ";" (a "." between digits is a decimal point)."""
    n = len(text)
    return [k for k, ch in enumerate(text) if ch in _SENTENCE_END and not (ch == "." and 0 < k < n - 1 and text[k - 1].isdigit() and text[k + 1].isdigit())]


def _encoded_stem_sets(problem: Problem) -> list[set[str]]:
    """The content stems of each premise label and of each meaning of a symbol a premise uses."""
    used: set[str] = set()
    for p in problem.premises:
        used |= _expr_names(p.expr.model_dump(mode="json", exclude_none=True))
    texts = [p.label or "" for p in problem.premises] + [s.meaning or "" for s in problem.symbols if s.name in used]
    return [set(lexis.content_stems(t)) for t in texts if t.strip()]


def _unencoded_reason(text: str, problem: Problem) -> Optional[str]:
    """The claim's first reason clause that shares fewer than two content stems with every premise label and every meaning
    of a symbol the premises use, or None. A clause is read on the side of its connective where the reason stands, up to
    the clause's end; "because of" is a cause phrase, never a reason clause. Quotations are masked."""
    masked = mask_quotations(text or "")
    spans = lexis.token_spans(masked)
    toks = tuple(t for _s, _e, t in spans)
    ends = _boundaries(masked)
    encoded = _encoded_stem_sets(problem)
    for i, cue in lexis.find_cues(toks, REASON_CONNECTIVES):
        if cue == ("because",) and i + 1 < len(toks) and toks[i + 1] == "of":
            continue
        at = spans[i][0]
        if cue in _REASON_AFTER:
            stop = next((e for e in ends if e > at), len(masked))
            part = [k for k in range(i + len(cue), len(spans)) if spans[k][0] < stop]
        else:
            start = max((e for e in ends if e < at), default=-1)
            part = [k for k in range(0, i) if spans[k][0] > start]
        if not part:
            continue
        stems = set(lexis.content_stems([toks[k] for k in part]))
        if len(stems) < 2:
            continue
        if all(len(stems & e) < 2 for e in encoded):
            return truncate(" ".join(text[spans[part[0]][0]:spans[part[-1]][1]].split()), 300)
    return None


def _uncovered_clause(text: str, problem: Problem) -> Optional[tuple[str, str]]:
    """``(the dropped clause, the rest)`` when a clause of the claim (split at "but", "however", "although", "while",
    "whereas" or ";", quotations masked) has at least three content stems that occur in no label or meaning of the
    encoding (the conclusion's label, every symbol meaning, every premise label), they are at least two thirds of its
    content stems, and another clause shares content with the encoding; else None."""
    masked = mask_quotations(text or "")
    spans = lexis.token_spans(masked)
    cuts = sorted({s for s, _e, t in spans if t in _CLAUSE_SPLIT_WORDS} | {k for k, ch in enumerate(masked) if ch == ";"})
    if not cuts:
        return None
    edges = [0, *cuts, len(masked)]
    pieces = [(edges[k], edges[k + 1]) for k in range(len(edges) - 1) if masked[edges[k]:edges[k + 1]].strip()]
    if len(pieces) < 2:
        return None
    texts = [(problem.conclusion.label or "") if problem.conclusion is not None else ""] + [s.meaning or "" for s in problem.symbols] + [p.label or "" for p in problem.premises]
    encoded: set[str] = set()
    for t in texts:
        encoded |= set(lexis.content_stems(t))
    stems = [set(lexis.content_stems(masked[a:b])) for a, b in pieces]
    for k, (a, b) in enumerate(pieces):
        missing = stems[k] - encoded
        others = [j for j in range(len(pieces)) if j != k]
        if len(missing) >= 3 and 3 * len(missing) >= 2 * len(stems[k]) and any(stems[j] & encoded for j in others):
            dropped = " ".join(text[a:b].split()).strip(" ,;")
            kept = " ".join(" ".join(text[x:y].split()).strip(" ,;") for j, (x, y) in enumerate(pieces) if j != k)
            return truncate(dropped, 300), truncate(kept, 300)
    return None


def source_texts(claim: ClaimRecord, supporting: list[ClaimRecord], report: SpecialistReport, task: Optional[TaskRecord] = None) -> list[SourceText]:
    """The texts a figure of ``claim``'s encoding may be stated by, in the order they are consulted: the claim, its
    supporting claims, the supplied texts, the task record."""
    out = [SourceText("claim", claim.claim_id, claim.claim_text)]
    out += [SourceText("supporting_claim", c.claim_id, c.claim_text) for c in supporting]
    out += [SourceText("supplied_text", t.document_id, t.text) for t in report.supplied_texts]
    if task is not None:
        out.append(SourceText("task", task.task_id, task.text))
    return out


def _format_validation_error(exc: ValidationError, what: str) -> str:
    lines = []
    for err in exc.errors()[:_MAX_SCHEMA_ERRORS]:
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = str(err.get("msg", "invalid"))
        lines.append(f"{loc or '<root>'}: {msg}")
    more = exc.error_count() - len(lines)
    text = f"{what} does not match the schema: " + "; ".join(lines)
    if more > 0:
        text += f"; and {more} more"
    return truncate(text, _MAX_DIAGNOSTIC_CHARS * 2)


class Translator:
    """Turns one claim of a specialist report into a :class:`TranslationResult`.

    ``provider`` is any :class:`~epinoic_logic.translate.providers.base.TranslationProvider`.
    ``max_attempts`` bounds provider calls per claim (default 2: one retry with the
    previous attempt's diagnostics). ``limits`` are the IR shape limits enforced by
    the engine validator before anything is accepted. ``config`` bounds the solver run
    that decides whether a conclusion fails only on a figure the problem defines but
    never asserts (run only when such a definition is present).
    """

    def __init__(
        self,
        provider: TranslationProvider,
        policy_version: str = POLICY_VERSION,
        max_attempts: int = 2,
        prompt_version: str = prompts.TRANSLATE_PROMPT_VERSION,
        limits: Limits = DEFAULT_LIMITS,
        config: SolverConfig = SolverConfig(),
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.provider = provider
        self.policy_version = policy_version
        self.max_attempts = max_attempts
        self.prompt_version = prompt_version
        self.limits = limits
        self.config = config

    # ------------------------------------------------------------------ public

    def translate(self, claim: ClaimRecord, report: SpecialistReport, task: Optional[TaskRecord] = None) -> TranslationResult:
        """Translate ``claim`` (which must belong to ``report``) into a bound result.

        ``task`` is the task record as the router issued it (it must belong to the claim's task and request): a source
        of the task's authority beside the supplied texts. Never raises for provider or model-output problems; those
        become statuses.
        """
        if claim.report_id != report.report_id or claim.request_id != report.request_id:
            raise ValueError("claim does not belong to the report")
        if task is not None and (task.task_id != claim.task_id or task.request_id != claim.request_id):
            raise ValueError("task record does not belong to the claim's task and request")
        profile = subjects.resolve_profile(claim.subject)
        eligibility = apply_subject_policy(decide_eligibility(claim, self.policy_version), profile)
        if not eligibility.eligible:
            result = self._result(claim, TranslationStatus.NOT_ELIGIBLE, eligibility, diagnostics=list(eligibility.reasons), task=task)
            self._log(result, attempts=0)
            return result

        supporting_ids = set(claim.supporting_claim_ids) - {claim.claim_id}  # a claim never supports itself
        supporting = [c for c in report.claims if c.claim_id in supporting_ids]
        base = dict(
            claim=claim,
            supporting_claims=supporting,
            supplied_texts=list(report.supplied_texts),
            eligibility=eligibility,
            prompt_version=self.prompt_version,
            ir_version=IR_VERSION,
            subject_profile_text=subjects.prompt_profile_text(profile),
            task=task,
        )
        sources = source_texts(claim, supporting, report, task)

        prior: list[str] = []
        collected: list[str] = []
        attempts = 0
        last_rejection: Optional[tuple[int, _Rejected]] = None
        semantic_prior: Optional[tuple[int, _Rejected]] = None
        semantic_all: list[tuple[int, _Rejected]] = []
        while attempts < self.max_attempts:
            attempts += 1
            request = TranslationRequest(**base, prior_diagnostics=list(prior))
            try:
                response = self.provider.propose(request)
            except ProviderError as exc:
                info = ProviderInfo(provider_name=self.provider.name, prompt_version=self.prompt_version, attempts=attempts)
                collected.append(f"attempt {attempts}: provider error: {truncate(str(exc), _MAX_DIAGNOSTIC_CHARS)}")
                result = self._result(claim, TranslationStatus.TRANSLATION_FAILED, eligibility, provider=info, diagnostics=collected, task=task)
                self._log(result, attempts=attempts)
                return result
            info = response.info.model_copy(update={"attempts": attempts})
            try:
                accepted = self._process(response.raw_text, claim, report, profile, attempts, task, sources)
            except _Rejected as rejected:
                collected.extend(rejected.diagnostics)
                last_rejection = (attempts, rejected)
                if rejected.problem is not None and rejected.reason in SEMANTIC_REASONS:
                    semantic_prior = (attempts, rejected)
                    semantic_all.append((attempts, rejected))
                if rejected.retryable and attempts < self.max_attempts:
                    prior = list(rejected.diagnostics)
                    continue
                result = self._result(claim, rejected.status, eligibility, provider=info, diagnostics=collected, task=task,
                                      grounding_checks=rejected.checks, figure_readings=rejected.readings, coverage=rejected.coverage,
                                      grounding_support=grounding_support(rejected.checks))
                self._log(result, attempts=attempts)
                return result
            repairs: list[RepairRecord] = []
            status, interpretation, notes = accepted.status, accepted.interpretation, list(accepted.notes)
            if last_rejection is not None:
                repair, flag = self._repair(last_rejection, semantic_prior, attempts, accepted, sources, semantic_all)
                repairs.append(repair)
                if flag is not None:
                    interpretation = interpretation.model_copy(update={"ambiguity_flags": [*interpretation.ambiguity_flags, flag]})
                    status = TranslationStatus.AMBIGUOUS_TRANSLATION
                    notes.append(truncate(f"retry changed the claim: {flag.message}", _MAX_DIAGNOSTIC_CHARS * 2))
            result = self._result(
                claim,
                status,
                eligibility,
                problem=accepted.problem,
                interpretation=interpretation,
                grounding_checks=accepted.grounding_checks,
                provider=info,
                diagnostics=collected + notes,
                task=task,
                figure_readings=accepted.readings,
                repairs=repairs,
                coverage=accepted.coverage,
                grounding_support=accepted.support,
                premise_roles=accepted.roles,
                asserted_verified=accepted.asserted_verified,
            )
            self._log(result, attempts=attempts)
            return result
        raise AssertionError("unreachable: attempt loop exited without a result")  # pragma: no cover

    def _repair(self, last: tuple[int, "_Rejected"], semantic: Optional[tuple[int, "_Rejected"]], attempt: int, accepted: "_Accepted",
                sources: list[SourceText], semantic_all: Sequence[tuple[int, "_Rejected"]] = ()) -> tuple[RepairRecord, Optional[AmbiguityFlag]]:
        """The record of an accepted retry, and the ambiguity flag when it changed the claim or added a premise no source
        asserts (see step 4e). A retry after a rejection for meaning is compared with that problem even when a later
        attempt failed only in form, and the premises it adds are checked against EVERY earlier rejection for an
        unasserted figure, so a later rejection of another kind cannot hide what an E110 asked for."""
        last_attempt, last_rejected = last
        if semantic is None:
            return RepairRecord(attempt=attempt, after_attempt=last_attempt, kind="syntax", rejected_for=[last_rejected.reason],
                                changes=["the output's form was repaired: the earlier attempt was not a valid problem under the schema, the validator or the subject profile"]), None
        # the latest attempt rejected for its meaning is the reference, even when a form failure came after it
        last_attempt, rejected = semantic
        before = rejected.problem
        assert before is not None
        reference = reference_reading(before, read_sites(before, sources))
        relation = compare_conclusions(reference, accepted.problem, self.config)
        changes = [f"conclusion {relation} compared with attempt {last_attempt}'s conclusion read as its source states it"]
        changes += premise_changes(before, accepted.problem)
        re_read = [r for r in accepted.readings if r.encoded_as == "interval" and r.exactness == "rounded"]
        changes += [f"figure {r.written or r.literal} ({r.source_kind} {r.source_id}, characters {r.start}-{r.end}) read at its stated precision "
                    f"[{r.lower}, {r.upper})" for r in re_read]
        keeps = relation in ("unchanged", "equivalent", "stronger")
        history = list(semantic_all) or [semantic]
        reasons = list(dict.fromkeys(r.reason for _a, r in history))
        unsupported: list[str] = []
        figure_rejections = [(a, r) for a, r in history if r.reason == "unasserted_figure" and r.problem is not None]
        for figure_attempt, figure_rejected in figure_rejections:
            # The rejection asked for the premise its source evidence names, and for nothing else: every added premise must
            # be that (or follow from it with the earlier premises), or be established by a check in this process.
            asserted = [n for n in figure_rejected.coverage if n.kind == "unasserted_definition" and n.source_asserted]
            atoms = [n.symbols[0] for n in asserted if n.symbols]
            for premise, supported, why in added_premise_support(figure_rejected.problem, accepted.problem, atoms, self.config):  # type: ignore[arg-type]
                changes.append(f"premise {premise.id} {why}" + (f" (after attempt {figure_attempt})" if len(figure_rejections) > 1 else ""))
                if not supported:
                    unsupported.append(premise.id)
        unsupported = list(dict.fromkeys(unsupported))
        supported_by_source = keeps and not unsupported and all(r in ("stated_precision", "exactness", "unasserted_figure") for r in reasons)
        record = RepairRecord(attempt=attempt, after_attempt=last_attempt, kind="semantic", rejected_for=reasons, conclusion=relation,  # type: ignore[arg-type]
                              changes=[truncate(c, 400) for c in changes][:24], supported_by_source=supported_by_source)
        old_label = (before.conclusion.label if before.conclusion is not None and before.conclusion.label else "(no label)")
        new_label = (accepted.problem.conclusion.label if accepted.problem.conclusion is not None and accepted.problem.conclusion.label else "(no label)")
        if not keeps:
            flag = AmbiguityFlag(
                code="retry_changed_claim",
                message=truncate(f"(deterministic) attempt {attempt}'s conclusion is {relation} relative to attempt {last_attempt}'s conclusion read as its "
                                 f"source states it, after a rejection for {rejected.reason}: a retry that weakens or replaces the claim cannot inherit its "
                                 "approval, so neither encoding is shown as a verdict", 2000),
                alternatives=[truncate(f"attempt {last_attempt}: {old_label}", 200), truncate(f"attempt {attempt}: {new_label}", 200)],
            )
            return record, flag
        if unsupported:
            evidence = "; ".join(e for _a, r in figure_rejections for n in r.coverage if n.source_asserted for e in n.evidence[:2]) or "none"
            after = ", ".join(str(a) for a, _r in figure_rejections)
            flag = AmbiguityFlag(
                code="retry_added_premise",
                message=truncate(f"(deterministic) attempt {attempt} added premise(s) {', '.join(unsupported[:8])} that the rejection of attempt {after} for "
                                 f"an unasserted figure does not support: the source evidence asserts only {evidence}. A retry may add only what the source "
                                 "asserts; a verdict earned with any other premise is not the claim's, so neither encoding is shown as a verdict", 2000),
                alternatives=[truncate(f"attempt {last_attempt}: {old_label}", 200), truncate(f"attempt {attempt}: {new_label}", 200)],
            )
            return record, flag
        return record, None

    # ----------------------------------------------------------------- private

    def _process(
        self,
        raw_text: str,
        claim: ClaimRecord,
        report: SpecialistReport,
        profile: SubjectProfile,
        attempt: int,
        task: Optional[TaskRecord] = None,
        sources: Optional[list[SourceText]] = None,
    ) -> _Accepted:
        """Parse, validate, policy-check and ground one provider output."""
        tag = f"attempt {attempt}"
        try:
            obj = parse_json_object(raw_text)
        except ProviderOutputTooLarge as exc:
            # refused before it is parsed (parsing.MAX_PROVIDER_TEXT_BYTES): the provider failed to produce a usable output, and
            # a retry asks it for the same thing again, so none is made
            raise _Rejected(TranslationStatus.TRANSLATION_FAILED, [f"{tag}: {exc}"], retryable=False) from None
        except ProviderOutputError as exc:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {exc}"], retryable=True) from None
        asserted = list(asserted_verified_paths(obj))[:256]
        try:
            return self._process_object(obj, asserted, tag, claim, report, profile, task, sources)
        except _Rejected as exc:
            # a refused output that certified itself is named as such too: the refusal keeps its own reason, and the
            # provider's verification claim is recorded beside it (E505), never silently lost with the output (repair
            # round 2, ADV2 probe zx01: forged verification and result fields on a proposal the parser refuses)
            exc.diagnostics.extend(truncate(f"{tag}: {DiagnosticCode.SELF_CERTIFICATION_REJECTED.value}: the translation asserted verified=true at "
                                            f"{path}; discarded: only checks set it", _MAX_DIAGNOSTIC_CHARS) for path in asserted)
            raise

    def _process_object(self, obj: dict, asserted: list[str], tag: str, claim: ClaimRecord, report: SpecialistReport, profile: SubjectProfile,
                        task: Optional[TaskRecord], sources: Optional[list[SourceText]]) -> _Accepted:
        """:meth:`_process` once the output is parsed: validate, policy-check and ground the object (``asserted``: the paths
        where it wrote ``verified: true``, recorded and discarded)."""
        missing = [k for k in REQUIRED_OUTPUT_KEYS if k not in obj]
        if missing:
            raise _Rejected(
                TranslationStatus.INVALID_FORMALIZATION,
                [f"{tag}: output is missing required key(s): {', '.join(missing)}"],
                retryable=True,
            )

        raw_problem = obj["problem"]
        if raw_problem is None:
            reason = obj.get("unsupported_reason")
            text = reason.strip() if isinstance(reason, str) and reason.strip() else "no unsupported_reason was given"
            raise _Rejected(
                TranslationStatus.UNSUPPORTED,
                [f"{tag}: provider declined to encode the claim: {truncate(text, _MAX_DIAGNOSTIC_CHARS)}"],
                retryable=False,
            )
        if not isinstance(raw_problem, dict):
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: problem must be a JSON object or null"], retryable=True)
        try:
            problem = Problem.model_validate(raw_problem)
        except ValidationError as exc:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {_format_validation_error(exc, 'problem')}"], retryable=True) from None
        except RecursionError:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: problem nesting is too deep to validate"], retryable=False) from None

        if problem.request_id != claim.request_id or problem.claim_id != claim.claim_id:
            raise _Rejected(
                TranslationStatus.INVALID_FORMALIZATION,
                [f"{tag}: problem request_id/claim_id do not match the claim being translated"],
                retryable=False,
            )

        outcome = validate_problem(problem, self.limits)
        if not outcome.ok:
            diagnostics = [
                f"{tag}: {d.code}: {truncate(d.message, _MAX_DIAGNOSTIC_CHARS)}" + (f" at {d.path}" if d.path else "")
                for d in outcome.diagnostics
            ]
            if outcome.status is VerificationStatus.UNSUPPORTED:
                raise _Rejected(TranslationStatus.UNSUPPORTED, diagnostics, retryable=False)
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, diagnostics, retryable=True)

        disallowed = sorted({s.sort for s in problem.symbols if s.sort != "Bool" and s.sort not in profile.numeric_sorts})
        if disallowed:
            raise _Rejected(
                TranslationStatus.INVALID_FORMALIZATION,
                [f"{tag}: sort(s) {', '.join(disallowed)} are not permitted by subject profile {profile.key}; use Bool"
                 + (f" or {', '.join(sorted(profile.numeric_sorts))}" if profile.numeric_sorts else "")],
                retryable=True,
            )

        # the answer's own written calculations: the claim, its supporting claims, then the whole answer (a figure the answer derives
        # in another sentence, '$2.50 − $0.50 = $2.00', is its working wherever the parser cut the claims; repair round 2,
        # FA-SUPPORTED-BM-DERIVED)
        answer = [claim.claim_text] + [c.claim_text for c in report.claims if c.claim_id in set(claim.supporting_claim_ids) - {claim.claim_id}]
        if report.original_response and report.original_response not in answer:
            answer.append(report.original_response)
        grounded, checks = check_problem_grounding(problem, report.supplied_texts, task=task, answer_texts=answer)
        if sources is None:
            sources = source_texts(claim, [c for c in report.claims if c.claim_id in set(claim.supporting_claim_ids) - {claim.claim_id}], report, task)

        try:
            interpretation = Interpretation.model_validate(obj["interpretation"])
        except ValidationError as exc:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: {_format_validation_error(exc, 'interpretation')}"], retryable=True) from None
        except RecursionError:
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: interpretation nesting is too deep to validate"], retryable=False) from None

        ambiguous = obj["ambiguous"]
        if not isinstance(ambiguous, bool):
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [f"{tag}: ambiguous must be a JSON boolean"], retryable=True)

        notes: list[str] = []
        failed = [c for c in checks if c.verified is False]
        if failed:
            notes.append(
                f"{len(failed)} grounding check(s) failed: " + ", ".join(sorted({c.target_id for c in failed}))
            )
        # Coverage (step 4b): whether a source asserts what an under-determined shape leaves open, decided from the sources
        # and handed to the engine as an application record on the symbols involved, so the engine's E110/E111 (no
        # verdict) or W110/W111 (advisory) is this decision.
        coverage = self._coverage(grounded, sources)
        grounded, evidence_checks = apply_coverage_evidence(grounded, coverage)
        checks = checks + evidence_checks
        notes += self._stated_figures(grounded, tag, interpretation, coverage, checks)
        notes += label_beyond_expression(grounded)
        self._circularity(grounded, tag, checks)
        readings = read_sites(grounded, sources)
        decision = decide_precision(grounded, readings, self.config, tag)
        if decision.reject is not None:
            reason, diagnostic = decision.reject
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [diagnostic], retryable=True, reason=reason, problem=grounded,
                            coverage=coverage, readings=decision.readings, checks=checks)
        if decision.ambiguity is not None:
            interpretation = interpretation.model_copy(update={"ambiguity_flags": [*interpretation.ambiguity_flags, decision.ambiguity]})
            notes.append(truncate(f"stated precision unresolved: {decision.ambiguity.message}", _MAX_DIAGNOSTIC_CHARS * 2))
        encoding = self._encoding_flags(grounded, claim)
        if encoding:
            interpretation = interpretation.model_copy(update={"ambiguity_flags": [*interpretation.ambiguity_flags, *encoding]})
            notes += [truncate(f"{f.code}: {f.message}", _MAX_DIAGNOSTIC_CHARS * 2) for f in encoding]
        status = TranslationStatus.AMBIGUOUS_TRANSLATION if (ambiguous or interpretation.ambiguity_flags) else TranslationStatus.TRANSLATED
        if ambiguous and not interpretation.ambiguity_flags:
            notes.append("provider marked the claim ambiguous without listing ambiguity flags")
        notes += [truncate(f"{DiagnosticCode.SELF_CERTIFICATION_REJECTED.value}: the translation asserted verified=true at {path}; discarded: only checks set it",
                           _MAX_DIAGNOSTIC_CHARS) for path in asserted]
        return _Accepted(status=status, problem=grounded, interpretation=interpretation, grounding_checks=checks, notes=notes,
                         readings=decision.readings, coverage=coverage, support=grounding_support(checks),
                         roles=_premise_roles(grounded, checks), asserted_verified=asserted)

    @staticmethod
    def _coverage(problem: Problem, sources: list[SourceText]) -> list[CoverageNote]:
        """Coverage notes for the two under-determined shapes (see :mod:`.coverage`): every unasserted figure definition
        and the free conclusion symbols, each against every source (the claim, its supporting claims, the supplied texts,
        the task record)."""
        defs = unasserted_figure_definitions(problem)
        coverage = assess_definitions(problem, defs, sources) if defs else []
        unconstrained = assess_unconstrained(problem, sources)
        if unconstrained is not None:
            coverage.append(unconstrained)
        return coverage

    def _stated_figures(self, problem: Problem, tag: str, interpretation: Optional[Interpretation] = None,
                        coverage: Sequence[CoverageNote] = (), checks: Optional[list[GroundingCheck]] = None) -> list[str]:
        """A premise that only defines an atom by a comparison of a figure no premise mentions asserts nothing. The coverage
        notes say whether a source ASSERTS such a figure, and :func:`.coverage.apply_coverage_evidence` has handed that
        decision to the engine. When the conclusion fails only on such a figure and a source asserts it, the engine reports
        ``E110`` and the output is rejected as INVALID_FORMALIZATION with the source evidence, fed back once: the
        translation omitted what the source states. Without such evidence the definition may be the question's own (a
        definition, a supposition): the engine reports the advisory ``W110``, the counterexample stands, and the note is
        an advisory coverage warning. A translator is never told to add a premise because adding it would produce
        entailment. When neither code is reported the engine's verdict does not turn on the unasserted definitions, and
        they are recorded as a note; an ambiguity flag that says a figure "is encoded" (a literal equality) while the
        premise stating it only defines it is named too: the flag does not match the IR."""
        defs = unasserted_figure_definitions(problem)
        if not defs:
            return []
        notes: list[str] = []
        named_coverage = False
        if problem.query == "entailment" and problem.conclusion is not None:
            probe = self._probe(problem)
            by_code = {d.code: d for d in probe.diagnostics}
            model = ", ".join(f"{a.symbol}={a.value}" for a in (probe.counterexample.assignments if probe.counterexample else [])[:8])
            diag = by_code.get(DiagnosticCode.UNASSERTED_FIGURE.value)
            if diag is not None:
                asserted = [n for n in coverage if n.kind == "unasserted_definition" and n.source_asserted]
                evidence = "; ".join(e for n in asserted for e in n.evidence[:2]) or truncate(diag.message, _MAX_DIAGNOSTIC_CHARS)
                named = ", ".join(f"{n.assertion_ids[0]} ({', '.join(n.symbols)})" for n in asserted[:6]) or (diag.path or "the definition")
                raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [truncate(
                    f"{tag}: {DiagnosticCode.UNASSERTED_FIGURE.value}: unasserted figure: premise(s) {named} define an atom by a comparison of a figure "
                    f"that no premise asserts, and the counterexample only reassigns it ({model}); the source asserts that figure: {evidence}. Encode "
                    "what the source states (the stated figure, or the atom, asserted as a premise grounded in that source). Add nothing the source "
                    "does not state", _MAX_DIAGNOSTIC_CHARS * 3)], retryable=True, reason="unasserted_figure", problem=problem, coverage=list(coverage),
                    checks=checks)
            if DiagnosticCode.UNASSERTED_FIGURE_ADVISORY.value in by_code:
                named_coverage = True
                notes.append(truncate(f"coverage (advisory, {DiagnosticCode.UNASSERTED_FIGURE_ADVISORY.value}): the counterexample ({model}) only reassigns "
                                      "a figure that premise(s) " + ", ".join(n.assertion_ids[0] for n in coverage if n.kind == "unasserted_definition")
                                      + " define but no premise asserts; no source sentence asserts it, so the counterexample stands as the verdict on the "
                                      "encoding and rests on that open figure (a definition or supposition the question leaves open)", _MAX_DIAGNOSTIC_CHARS * 2))
        if not named_coverage:
            named = ", ".join(f"{d.premise_id} ({d.atom} over {', '.join(d.figures)})" for d in defs[:8]) + (f" and {len(defs) - 8} more" if len(defs) > 8 else "")
            notes.append(truncate(f"unasserted figure definition(s): premise(s) {named} define an atom by a figure that no premise asserts or constrains, "
                                  "so the figure their labels state is not encoded as stated; the engine verdict does not rest on them", _MAX_DIAGNOSTIC_CHARS * 2))
        flags = [f for f in (interpretation.ambiguity_flags if interpretation is not None else ()) if _ENCODED_CLAIM_RE.search(f.message)]
        if flags:
            notes.append(truncate(f"ambiguity flag(s) {sorted({f.code for f in flags})} say a stated figure is encoded (a literal equality), but premise(s) "
                                  f"{', '.join(d.premise_id for d in defs[:8])} only define it: no premise asserts it, so the flag does not match the IR", _MAX_DIAGNOSTIC_CHARS * 2))
        return notes

    def _probe(self, problem: Problem):
        """The engine's answer for ``problem`` as an internal probe: no argument diagnosis, never release-eligible. Every
        probe of this module goes through here."""
        return engine_verify(problem, self.config, diagnose=False)  # an internal probe: no argument diagnosis

    def _probe_status(self, problem: Problem, conclusion: Optional[dict] = None) -> Optional[VerificationStatus]:
        """The status of ``problem`` (with ``conclusion`` in place of its own, when given), or None when the rewritten
        problem is not valid."""
        if conclusion is not None:
            data = problem.model_dump(mode="json", exclude_none=True)
            data["conclusion"] = {**data["conclusion"], "expr": conclusion}
            try:
                problem = Problem.model_validate(data)
            except (ValidationError, ValueError):
                return None
        return self._probe(problem).status

    def _encoding_flags(self, problem: Problem, claim: ClaimRecord) -> list[AmbiguityFlag]:
        """The flags of an encoding that leaves part of the claim out (B8, B21), each an ambiguity: the engine still runs
        for inspection, but the claim is never shown as decided by a part the encoding does not link to its reasons.

        * ``UNLINKED_CONJUNCT``: some conjuncts of the conclusion share no symbol with any premise while others do; the
          problem is a COUNTEREXAMPLE and the linked part is ENTAILED. The counterexample only falsifies a judgement the
          encoding gave no reason, so it is no verdict on the claim as written.
        * ``UNENCODED_REASON``: no premise mentions the conclusion (the non sequitur shape) and the problem is a
          COUNTEREXAMPLE, but the claim's own text gives a reason clause (a reason connective, never "because of") that
          shares fewer than two content words with every premise label and symbol meaning: the translation left the
          claim's stated reason out. A claim whose reason is encoded, or that gives none, keeps its counterexample.
        * ``PARTIAL_ENCODING``: the problem is ENTAILED, but a clause of the claim (split at "but", "however",
          "although", "while", "whereas" or ";", quotations masked) has at least three content words that occur in no
          label or meaning of the encoding, and they are at least two thirds of its content words: the encoding covers
          only the rest, and a partial encoding is never shown as the whole claim.

        A problem the precondition does not fit is never probed; every probe passes ``diagnose=False``."""
        if problem.query != "entailment" or problem.conclusion is None:
            return []
        concl = problem.conclusion.expr.model_dump(mode="json", exclude_none=True)
        meanings = {s.name: (s.meaning or "") for s in problem.symbols}
        premise_vars: set[str] = set()
        for p in problem.premises:
            premise_vars |= _expr_names(p.expr.model_dump(mode="json", exclude_none=True))
        parts = _conjunct_dicts(concl)
        linked = [c for c in parts if _expr_names(c) & premise_vars]
        unlinked = [c for c in parts if not (_expr_names(c) & premise_vars)]
        cache: dict[str, Optional[VerificationStatus]] = {}

        def full() -> Optional[VerificationStatus]:
            if "full" not in cache:
                cache["full"] = self._probe_status(problem)
            return cache["full"]

        flags: list[AmbiguityFlag] = []
        if linked and unlinked:
            if full() is VerificationStatus.COUNTEREXAMPLE and self._probe_status(problem, linked[0] if len(linked) == 1 else {"op": "and", "args": linked}) is VerificationStatus.ENTAILED:
                shown = "; ".join(truncate(gloss(c, meanings), 160) for c in unlinked[:4])
                flags.append(AmbiguityFlag(
                    code="UNLINKED_CONJUNCT",
                    message=truncate(f"(deterministic) the conjunct(s) '{shown}' share no symbol with any premise: the encoding gives them no reason, "
                                     "so it cannot decide the claim as written. The rest of the point follows from the encoded premises, and the "
                                     "counterexample falsifies only the unlinked part, so it is not shown as a verdict", 2000),
                    alternatives=[truncate(f"the unlinked judgement(s) encoded from the claim's stated reasons: {shown}", 200),
                                  "only the linked part of the point: ENTAILED"]))
        elif unlinked and problem.premises:
            clause = _unencoded_reason(claim.claim_text, problem)
            if clause is not None and full() is VerificationStatus.COUNTEREXAMPLE:
                flags.append(AmbiguityFlag(
                    code="UNENCODED_REASON",
                    message=truncate(f"(deterministic) the claim gives a reason ('{clause}') that no premise encodes (it shares fewer than two content "
                                     "words with every premise label and symbol meaning), and no premise mentions the point: the translation left "
                                     "the claim's own reason out, so its counterexample is no verdict on the claim as written", 2000),
                    alternatives=[truncate(f"the claim with its stated reason encoded: {clause}", 200), "the encoding as given: COUNTEREXAMPLE"]))
        covered = _uncovered_clause(claim.claim_text, problem)
        if covered is not None and not flags and full() is VerificationStatus.ENTAILED:
            dropped, kept = covered
            flags.append(AmbiguityFlag(
                code="PARTIAL_ENCODING",
                message=truncate(f"(deterministic) the encoding covers only part of the claim: the clause '{dropped}' has content words that occur in "
                                 f"no label or meaning of the encoding, so the encoding covers only: '{kept}'. A partial encoding is never shown as "
                                 "the whole claim", 2000),
                alternatives=[truncate(f"the whole claim, with '{dropped}' encoded", 200), truncate(f"the encoded part only: {kept}", 200)]))
        return flags

    @staticmethod
    def _circularity(problem: Problem, tag: str, checks: Optional[list[GroundingCheck]] = None) -> None:
        """Reject a problem whose conclusion (or each of its conjuncts) is asserted by premises the writer supplies itself:
        the solver would prove the claim from the claim (the engine's ``E112``). The rule is the engine's authority rule
        (``engine.authority.assumed_grounding``): a restating premise that no check in this process established is the
        writer's own, whatever its label. Premises that contradict each other (``engine.runner.premises_inconsistent``) are
        no circle: the engine names the contradiction first (consistency before entailment); neither is a conclusion that
        holds with no premise at all (``engine.runner.conclusion_valid_alone``): it is vacuous, and the engine names that."""
        if problem.query != "entailment" or problem.conclusion is None:
            return
        restating = circular_premises(problem)
        by_id = {pr.id: pr for pr in problem.premises}
        if not restating or not all(assumed_grounding(by_id[pid].grounding) for pid in restating if pid in by_id):
            # beyond the normal form: a premise of the writer's own equivalent to the conclusion under every assignment
            # ("2 x dt = 82" for "dt = 41"; the engine's E112 reads it the same way: repair round 2, fidelity-4 variant)
            equivalent = equivalent_premises(problem)
            if not equivalent or premises_inconsistent(problem) or conclusion_valid_alone(problem):
                return
            named = ", ".join(f"{pid} ({by_id[pid].grounding.kind if pid in by_id and by_id[pid].grounding is not None else 'none'})" for pid in equivalent[:8])
            raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [
                f"{tag}: {DiagnosticCode.CIRCULAR_PREMISES.value}: circular: premise(s) {named} restate the conclusion in other terms (the "
                "solver finds each equivalent to the conclusion under every assignment), and no check in this process established them, so "
                "the claim would be proved from itself; encode what the claim rests on (its evidence and its stated links), or return "
                "problem null when it states a bare fact with no relation to check"], retryable=True, reason="circular", problem=problem, checks=checks)
        if premises_inconsistent(problem):
            # premises that contradict each other prove nothing: the engine decides INCONSISTENT_PREMISES first (consistency
            # before entailment), so the contradiction is named, not hidden behind a circularity refusal (repair round 2)
            return
        if conclusion_valid_alone(problem):
            # a conclusion that holds whatever the premises say is vacuous, not circular: the engine names it (E108, ARG-VAC-001)
            # rather than this refusal hiding it (repair round 3, tf_z19)
            return
        # each restating premise with the kind its grounding claims ("none" without one): the record the claim rules read
        named = ", ".join(f"{pid} ({by_id[pid].grounding.kind if pid in by_id and by_id[pid].grounding is not None else 'none'})" for pid in restating[:8])
        raise _Rejected(TranslationStatus.INVALID_FORMALIZATION, [
            f"{tag}: {DiagnosticCode.CIRCULAR_PREMISES.value}: circular: premise(s) {named} restate the conclusion "
            "(it, or each of its conjuncts), and no check in this process established them (whatever their label), so the claim would be proved "
            "from itself; encode what the claim rests on (its evidence and its stated links), or return problem null when it states a bare fact "
            "with no relation to check"], retryable=True, reason="circular", problem=problem, checks=checks)

    def _result(
        self,
        claim: ClaimRecord,
        status: TranslationStatus,
        eligibility: EligibilityDecision,
        *,
        problem: Optional[Problem] = None,
        interpretation: Optional[Interpretation] = None,
        grounding_checks: Optional[list[GroundingCheck]] = None,
        provider: Optional[ProviderInfo] = None,
        diagnostics: Optional[list[str]] = None,
        task: Optional[TaskRecord] = None,
        figure_readings: Optional[list[FigureReading]] = None,
        repairs: Optional[list[RepairRecord]] = None,
        coverage: Optional[list[CoverageNote]] = None,
        grounding_support: Optional[list[GroundingSupport]] = None,
        premise_roles: Optional[list] = None,
        asserted_verified: Optional[list[str]] = None,
    ) -> TranslationResult:
        return TranslationResult(
            translation_id=new_id("tr"),
            claim_id=claim.claim_id,
            request_id=claim.request_id,
            report_id=claim.report_id,
            status=status,
            eligibility=eligibility,
            claim_text_sha256=sha256_text(claim.claim_text),
            problem=problem,
            interpretation=interpretation,
            grounding_checks=list(grounding_checks or []),
            provider=provider,
            translator_version=TRANSLATOR_VERSION,
            policy_version=self.policy_version,
            diagnostics=list(diagnostics or []),
            created_at=utc_now_rfc3339(),
            grounding_support=list(grounding_support or []),
            figure_readings=list(figure_readings or []),
            repairs=list(repairs or []),
            coverage=list(coverage or []),
            task_sha256=task.text_sha256 if task is not None else None,
            premise_roles=list(premise_roles or []),
            asserted_verified=list(asserted_verified or []),
        )

    @staticmethod
    def _log(result: TranslationResult, *, attempts: int) -> None:
        # Identifiers and statuses only: never claim text, excerpts or diagnostics.
        logger.info(
            "translation %s claim=%s status=%s class=%s attempts=%d",
            result.translation_id,
            result.claim_id,
            result.status.value,
            result.eligibility.eligibility_class.value,
            attempts,
        )
