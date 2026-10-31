"""Versioned contracts between subject-specialist agents, the translator, the
verification engine and the Overseer.

Principles (Epinoic AI architecture, sections 4, 5 and 11 of the context document):
- The ORIGINAL specialist response is immutable; its hash is carried everywhere.
- Claims have stable ids. A materially changed claim is a NEW claim record linked to
  its source, never a rewrite under the same id.
- Agent-supplied confidence, eligibility and verification status are ADVISORY. They
  are recorded for audit and never trusted. The Overseer takes status only from
  signed engine results.
- Three correctness dimensions are kept separate: structural (deterministic code),
  semantic fidelity (advisory review), formal validity (engine). Permission to release
  an answer is a fourth record (``ReleaseAssessment``) that application code derives
  from the other three; a formal ENTAILED never grants it on its own.
- Authority over a premise comes only from application-created records: a supplied
  text, the task record (``TaskRecord``) or a derivation code checked. A grounding kind
  the translator proposes ("arithmetic_fact", "task_setting", "rubric_rule") claims
  that authority; it stays unchecked until code validates it against those records.
"""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from ..engine.results import VerificationResult
from ..engine.statuses import VerificationStatus
from ..ir.schema import Certainty, Grounding, GroundingKind, Problem, SourceRef
from ..named import DefectLabel, NamedDiagnostic


def _drop_empty(data, fields: tuple[str, ...]):
    """Leave ``fields`` out of a dump while they are ``None`` or empty: fields added with the argument diagnosis, so a record
    of an earlier release (and a record that carries none of them) dumps exactly as before."""
    if isinstance(data, dict):
        for name in fields:
            if name in data and (data[name] is None or data[name] == []):
                del data[name]
    return data

ClaimRole = Literal[
    # shared
    "thesis", "point", "evidence", "link", "structural", "quantitative", "other",
    # English (Device -> Interpretation -> Effect)
    "device", "interpretation", "effect",
    # History and other argued subjects (Claim -> Evidence -> Analysis -> Judgement -> Link)
    "analysis", "judgement", "counter_evidence", "perspective",
    # source operation (Origin, Purpose, Content -> Value, Limitation)
    "origin", "purpose", "content", "value", "limitation",
]
ProposedClaimKind = Literal[
    "formal_logic", "arithmetic", "factual", "interpretive", "rubric_judgment", "unknown",
]
LocatorScheme = Literal["none", "line", "paragraph", "page", "act_scene_line", "custom"]


class SuppliedText(BaseModel):
    """A text supplied with the task (an extract, poem, passage). Untrusted input."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=500)
    author: Optional[str] = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=400_000)
    locator_scheme: LocatorScheme = Field(
        default="none",
        description=(
            "how locations in this text may be cited; callers opt in to a scheme. The default 'none' means no "
            "page, line or act citation can be checked against this text, so citations are reported as unverifiable"
        ),
    )
    provenance: Optional[str] = Field(default=None, max_length=1000, description="where the text came from; e.g. 'supplied by student'")


class TaskRecord(BaseModel):
    """The task as the router issued it: an application-created, immutable record. Beside the supplied texts it is the
    only source that can confer task authority on a premise (a figure or setting the task states), and it is the
    original task a fidelity reviewer is shown. ``text_sha256`` must be the sha256 of ``text``."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=400_000)
    text_sha256: str = Field(min_length=64, max_length=64)
    issued_by: str = Field(default="router", max_length=64)

    @model_validator(mode="after")
    def _digest(self) -> "TaskRecord":
        if sha256_text(self.text) != self.text_sha256:
            raise ValueError("text_sha256 does not match the task text; a task record is immutable")
        return self

    @classmethod
    def of(cls, task_id: str, request_id: str, text: str, issued_by: str = "router") -> "TaskRecord":
        """A task record with its digest computed."""
        return cls(task_id=task_id, request_id=request_id, text=text, text_sha256=sha256_text(text), issued_by=issued_by)


class ClaimRecord(BaseModel):
    """One claim extracted from a specialist report. Input to the translator."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    report_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    agent_version: Optional[str] = Field(default=None, max_length=64)
    subject: str = Field(min_length=1, max_length=128, description="e.g. 'English A: Language and Literature'")
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128, description="e.g. 'analytical_paragraph', 'essay', 'outline'")
    claim_id: str = Field(min_length=1, max_length=128)
    claim_text: str = Field(min_length=1, max_length=4000)
    claim_role: ClaimRole = "other"
    proposed_claim_kind: ProposedClaimKind = Field(default="unknown", description="agent-proposed; advisory")
    materiality: Literal["material", "supporting"] = "material"
    certainty: Certainty = Field(default="established", description="agent-stated certainty; advisory")
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=32)
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    assessment_criteria: list[str] = Field(default_factory=list, max_length=32)
    supporting_claim_ids: list[str] = Field(default_factory=list, max_length=512, description="a paragraph's point legitimately supports every claim in it, so the bound equals the report's claim limit")
    parent_claim_id: Optional[str] = Field(default=None, max_length=128)
    advisory_verification_eligibility: Optional[bool] = Field(default=None, description="agent self-report; never trusted")
    advisory_verification_status: Optional[str] = Field(default=None, max_length=64, description="agent self-report; ignored, recorded for audit")


def sha256_text(text: str) -> str:
    """sha256 of ``text`` as UTF-8. A lone UTF-16 surrogate (a truncated emoji arriving as ``"\\ud83d"`` in an agent's
    JSON) is not valid Unicode and has no UTF-8 form; it is encoded with ``surrogatepass`` so hashing agent text can never
    raise (valid text hashes exactly as before). The channel rejects such text before parsing (INT-REQ-009)."""
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


class SpecialistReport(BaseModel):
    """Immutable structured report from a subject specialist."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    agent_version: Optional[str] = Field(default=None, max_length=64)
    subject: str = Field(min_length=1, max_length=128)
    course_level: Optional[Literal["SL", "HL", "unknown"]] = "unknown"
    task_type: str = Field(min_length=1, max_length=128)
    original_response: str = Field(min_length=1, max_length=400_000)
    response_sha256: str = Field(min_length=64, max_length=64)
    supplied_texts: list[SuppliedText] = Field(default_factory=list, max_length=16)
    claims: list[ClaimRecord] = Field(default_factory=list, max_length=512)
    assumptions: list[str] = Field(default_factory=list, max_length=64)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=64)
    created_at: str = Field(description="RFC 3339 UTC timestamp")

    @model_validator(mode="after")
    def _immutable(self) -> "SpecialistReport":
        if sha256_text(self.original_response) != self.response_sha256:
            raise ValueError("response_sha256 does not match original_response; reports are immutable")
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate claim_id in report")
        for c in self.claims:
            if c.report_id != self.report_id or c.request_id != self.request_id:
                raise ValueError(f"claim {c.claim_id} does not belong to this report")
        return self


class EligibilityClass(str, Enum):
    PROPOSITIONAL_ARGUMENT = "PROPOSITIONAL_ARGUMENT"      # argument structure: evidence -> inference -> point
    ARITHMETIC_CONSTRAINT = "ARITHMETIC_CONSTRAINT"        # counts, lengths, marks, thresholds
    QUANTITATIVE_CLAIM = "QUANTITATIVE_CLAIM"              # exact numeric claim with given values
    NOT_ELIGIBLE_INTERPRETIVE = "NOT_ELIGIBLE_INTERPRETIVE"  # literary/historical interpretation as a truth claim
    NOT_ELIGIBLE_FACTUAL = "NOT_ELIGIBLE_FACTUAL"          # world or text fact: route to evidence service
    NOT_ELIGIBLE_RUBRIC_JUDGMENT = "NOT_ELIGIBLE_RUBRIC_JUDGMENT"  # subjective criterion judgement
    NOT_ELIGIBLE_OTHER = "NOT_ELIGIBLE_OTHER"


class EligibilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    eligibility_class: EligibilityClass
    eligible: bool
    decided_by: Literal["deterministic", "model", "hybrid"]
    reasons: list[str] = Field(default_factory=list)
    route_to: Optional[str] = Field(default=None, description="for ineligible claims: 'evidence_service', 'subject_evaluator', 'unresolved'")
    policy_version: str


class GroundingCheck(BaseModel):
    """Result of a DETERMINISTIC grounding check on a symbol or premise.

    One check per source reference (``ref_index`` is its position in ``source_refs``): an excerpt is located
    (``verbatim_match``, ``normalized_match``), a reference without an excerpt has its document and locator checked
    (``locator_exists``). Further checks on the same target: ``figures_in_excerpt`` (the located excerpt states the
    premise's figures, as typed quantities, each so that it establishes its comparison), ``numeric_in_task`` (a premise
    whose kind claims task authority states figures a supplied text or the task record states), ``relation_in_source``
    (a premise whose numeric content is a relation, not an assignment of stated figures: whether a record states that
    relation itself as a given; its figures occurring in a record never verify it), ``asserts_figure`` (on a symbol an under-determined encoding
    leaves open: whether a source clause asserts its figure; this coverage check alone decides the symbol's
    ``verified`` flag, which is what the engine reads as coverage evidence), ``content_in_excerpt`` (a premise that
    restates the point: whether its located excerpt states the point's words, beyond their attribution; refuted when it
    does not), ``content_in_task`` (a figureless task-authority premise that cites no excerpt: whether one asserted
    sentence of the task record states each of its literals, with its polarity), ``not_checkable`` (a kind with no
    reference)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_id: str = Field(description="symbol name or assertion id")
    kind: GroundingKind
    method: Literal["verbatim_match", "normalized_match", "locator_exists", "numeric_in_task", "figures_in_excerpt", "relation_in_source", "asserts_figure",
                    "content_in_excerpt", "content_in_task", "not_checkable"]
    verified: Optional[bool] = None
    document_id: Optional[str] = None
    detail: Optional[str] = Field(default=None, max_length=2000)
    ref_index: Optional[int] = Field(default=None, ge=0, description="the source reference this check is about (its position in source_refs)")


GroundingSupportLevel = Literal["complete", "partial", "failed", "uncheckable"]


class GroundingSupport(BaseModel):
    """What a target's references establish together, from its per-reference checks: ``complete`` (every reference
    located), ``partial`` (some located, some not: a missing document, an unlocatable excerpt, a reference that locates
    nothing), ``failed`` (none located, at least one refuted), ``uncheckable`` (none located, none refuted). Only
    ``complete`` support verifies a grounding; a reference to an unknown document is never hidden by another one that
    was found. Locating words in a text does not establish that they support the encoded proposition: that is the
    fidelity review's question."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_id: str
    references: int = Field(ge=0)
    located: int = Field(ge=0)
    refuted: int = Field(ge=0)
    unchecked: int = Field(ge=0)
    support: GroundingSupportLevel


class AmbiguityFlag(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str = Field(max_length=2000)
    alternatives: list[str] = Field(default_factory=list, max_length=8)


class AtomGloss(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str
    meaning: str = Field(max_length=1000)
    grounding: Optional[Grounding] = None


class Interpretation(BaseModel):
    """Human-readable record of how the translator read the claim. Shown to the
    Overseer and reviewers so the reading can be challenged."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    reading: str = Field(max_length=4000)
    glossary: list[AtomGloss] = Field(default_factory=list)
    ambiguity_flags: list[AmbiguityFlag] = Field(default_factory=list)


class ProviderInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_name: str
    model_id: Optional[str] = None
    prompt_version: Optional[str] = None
    temperature: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    attempts: int = 1


class FigureReading(BaseModel):
    """How a figure of the encoding is stated by its source, tied to the span it rests on.

    ``literal`` is the IR literal (or the midpoint of an interval the encoding gives); ``source_*`` and ``start``-``end``
    name the span of the source text that states it (``source_kind`` ``none``: no source states it). ``exactness``
    comes from the wording, never from the solver: ``exact`` (an exactness cue: "exactly", "without rounding", or a
    written calculation that gives exactly the figure), ``rounded`` (a rounding cue, or a figure stated as the result of
    a written calculation; ``lower``/``upper`` are the values it states, ``mode`` its rounding direction), ``unstated``
    (no cue), ``given`` (a figure of a supplied text or the task, read exactly as given), ``conflicting``. For a figure
    stated as the result of a written calculation, ``calculated`` is the exact value of that calculation as written
    (when the translation layer's closed arithmetic reader computes it) and ``by_convention`` is true when the rounded
    reading rests only on the convention of written calculation (a presumption: no cue, no computed value it rounds).
    ``derivation`` says how the literal equals the stated figure (``20% = 20 x 1/100 = 1/5``). ``encoded_as`` is how
    the encoding states it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    literal: str
    assertion_ids: list[str] = Field(default_factory=list)
    source_kind: Literal["claim", "supporting_claim", "supplied_text", "task", "none"]
    source_id: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
    written: Optional[str] = None
    exactness: Literal["exact", "rounded", "unstated", "given", "conflicting", "unsourced"]
    cue: Optional[str] = Field(default=None, max_length=300)
    mode: Literal["nearest", "down", "up"] = "nearest"
    precision: Optional[str] = None
    lower: Optional[str] = Field(default=None, description="exact rational: the least value the rounded figure states")
    upper: Optional[str] = Field(default=None, description="exact rational: the greatest value the rounded figure states")
    unit: Optional[str] = None
    derivation: Optional[str] = Field(default=None, max_length=500)
    encoded_as: Literal["exact_equality", "interval", "other"] = "other"
    calculated: Optional[str] = Field(default=None, max_length=200, description="exact rational: the value of the written calculation")
    by_convention: bool = False


class RepairRecord(BaseModel):
    """One accepted attempt that follows a rejected one. ``kind`` ``syntax``: the earlier output was not a valid problem
    (JSON, schema, validator, subject sorts) and the retry repaired its form. ``semantic``: the earlier problem was valid
    but rejected for its meaning (stated precision, exactness, circularity, an unasserted figure), so the retry changed
    what is encoded; ``changes`` lists every change (the conclusion's relation to the earlier one, premises added or
    removed, figures re-read at their stated precision) and ``conclusion`` classifies it. A retry whose conclusion is
    not at least as strong as the earlier conclusion read as the source states it does not inherit the claim's
    approval: the translation is AMBIGUOUS_TRANSLATION, never a verdict. After a rejection for an unasserted figure,
    ``changes`` also says for every added premise whether it is supported (it follows from the rejected attempt's
    premises with the source-asserted atoms asserted, or a check established it); an unsupported one makes the
    translation AMBIGUOUS_TRANSLATION (flag ``retry_added_premise``)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt: int = Field(ge=1)
    after_attempt: int = Field(ge=1)
    kind: Literal["syntax", "semantic"]
    rejected_for: list[str] = Field(default_factory=list)
    conclusion: Literal["unchanged", "equivalent", "stronger", "weaker", "incomparable", "not_compared"] = "not_compared"
    changes: list[str] = Field(default_factory=list)
    supported_by_source: bool = Field(default=False, description="every change is what the source states: a figure read at its stated precision, or "
                                                                  "(after an unasserted figure) the figure or atom the source asserts")


class CoverageNote(BaseModel):
    """Whether the source asserts what an under-determined encoding leaves open, bound to the problem it assesses.

    ``unasserted_definition``: a premise defines an atom by a comparison of a figure no premise asserts (the engine's
    E110 shape). ``unconstrained_symbol``: the conclusion compares symbols no premise mentions (the E111 shape).
    ``source_asserted`` is True only with source-linked ``evidence`` (clauses of the claim, a supporting claim, a supplied
    text or the task that assert the figure: state it as a fact, establishing the comparison the encoding defines,
    about the encoding's symbols; :mod:`.assertion`) that the encoding omitted it: then the engine's counterexample is
    no verdict on the claim. Otherwise the open figure may be the question's own (a definition, a condition, a
    question, an arbitrary variable) and the counterexample stands, with this note as an advisory coverage warning
    whose ``detail`` names each mention passed over and the construction that decided it.

    The note is the translation layer's record; the engine's signed result carries the same decision. The pipeline
    hands the evidence to the engine as an application record on the symbols the counterexample turns on
    (:func:`~.coverage.apply_coverage_evidence`: the grounding of each symbol in ``evidence_symbols`` is verified with
    ``source_refs``, the spans that assert it), so the engine reports ``E110``/``E111`` exactly when this note is
    ``source_asserted`` and the advisory ``W110``/``W111`` otherwise."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["unasserted_definition", "unconstrained_symbol"]
    problem_digest: str
    assertion_ids: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    source_asserted: bool
    evidence: list[str] = Field(default_factory=list)
    detail: str = Field(max_length=2000)
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=16,
                                         description="the spans that assert what the encoding left open (document_id: the claim, supporting claim, supplied text or task)")
    evidence_symbols: list[str] = Field(default_factory=list, description="the symbols the evidence is attached to for the engine (the figures, or the free symbols)")


class TranslationStatus(str, Enum):
    TRANSLATED = "TRANSLATED"
    AMBIGUOUS_TRANSLATION = "AMBIGUOUS_TRANSLATION"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_FORMALIZATION = "INVALID_FORMALIZATION"
    TRANSLATION_FAILED = "TRANSLATION_FAILED"


class StructuralFinding(BaseModel):
    """A deterministic structural or source-integrity finding (not a solver result)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    severity: Literal["error", "warning", "info"]
    message: str = Field(max_length=2000)
    claim_ids: list[str] = Field(default_factory=list)
    rule_source: Optional[str] = Field(default=None, max_length=200, description="e.g. 'english_specialist/paragraphs.md P7' (working rule, not an official IB rule)")
    deterministic: bool = True
    defect: Optional[DefectLabel] = Field(default=None, description=(
        "the canonical defect label the finding names (named.DEFECT_LABELS), set by its pack or by the channel through "
        "named.DEFECT_OF_CODE; left out of every dump while None"))

    @model_serializer(mode="wrap")
    def _omit_absent_defect(self, handler: SerializerFunctionWrapHandler):
        return _drop_empty(handler(self), ("defect",))


PremiseRoleKind = Literal["fact", "link", "either_or", "definition", "figure_relation"]
PremiseAuthority = Literal["established", "unverified", "refuted", "writer_own"]
PremiseMarking = Literal["translator_link", "translator_rule", "fact", "unmarked_link", "label_conflict", "source_link"]


class PremiseRole(BaseModel):
    """How the translation marks one premise (``roles.premise_roles``), recorded at translation time.

    ``role`` is read from the expression, never from the label: ``link`` (an implication, or a biconditional of
    propositions), ``either_or`` (a disjunction), ``definition`` (a biconditional with an atom on one side), ``figure_relation``
    (a numeric relation that combines symbols), ``fact`` (everything else: atoms, negations, assignments, conjunctions).
    ``authority`` is read from ``verified`` and the kind: ``established`` (a check in this process verified it),
    ``refuted`` (a check failed), ``writer_own`` (no grounding, or an assumption, specialist inference or general knowledge),
    ``unverified`` (a task or source kind no check verified). ``marked`` says how the translation marked a link-shaped
    premise: ``translator_link`` (``specialist_inference`` with a ``link: <connective>`` note: the writer's own step, marked
    as such), ``translator_rule`` (``general_knowledge``: a rule stated from subject knowledge), ``source_link`` (a check
    verified the relation against a source), ``label_conflict`` (its kind claims a text or task authority while no check
    verified the relation), ``unmarked_link`` (any other kind, unverified: the writer's link, not marked); every
    other premise is ``fact``. ``connective`` is the connective of a ``link:`` note."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    assertion_id: str
    role: PremiseRoleKind
    authority: PremiseAuthority
    marked: PremiseMarking
    kind: Optional[GroundingKind] = None
    connective: Optional[str] = Field(default=None, max_length=80)

    @model_serializer(mode="wrap")
    def _compact(self, handler: SerializerFunctionWrapHandler):
        return _drop_empty(handler(self), ("kind", "connective"))


class TranslationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation_id: str
    claim_id: str
    request_id: str
    report_id: str
    status: TranslationStatus
    eligibility: EligibilityDecision
    claim_text_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64, description=(
        "sha256 of the claim_text this translation was produced for (set by the translator). A translation is bound to the "
        "text it read, not only to (request_id, claim_id): the outcome composer and the channel reject one attached to a "
        "claim whose text differs, so a stale translation is never displayed under another text"))
    problem: Optional[Problem] = None
    interpretation: Optional[Interpretation] = None
    grounding_checks: list[GroundingCheck] = Field(default_factory=list)
    provider: Optional[ProviderInfo] = None
    translator_version: str
    policy_version: str
    diagnostics: list[str] = Field(default_factory=list)
    created_at: str
    grounding_support: list[GroundingSupport] = Field(default_factory=list, description="per target with references: complete, partial, failed or uncheckable support")
    figure_readings: list[FigureReading] = Field(default_factory=list, description="how each compared figure is stated by its source (exactness, precision, unit), tied to its span")
    repairs: list[RepairRecord] = Field(default_factory=list, description="accepted retries: syntax repairs and semantic changes, recorded separately")
    coverage: list[CoverageNote] = Field(default_factory=list, description="whether the source asserts what an under-determined encoding leaves open")
    task_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64, description="sha256 of the task record the translation was validated against, when one was given")
    premise_roles: list[PremiseRole] = Field(default_factory=list, description=(
        "how the translation marks each premise of its problem (roles.premise_roles): the record that tells the writer's own "
        "links from stated rules and checked facts; left out of every dump while empty"))
    asserted_verified: list[str] = Field(default_factory=list, max_length=256, description=(
        "the paths where the provider's JSON wrote a 'verified' key (parsing.asserted_verified_paths): discarded, because only "
        "checks set it; left out of every dump while empty"))

    @model_serializer(mode="wrap")
    def _omit_new_empty(self, handler: SerializerFunctionWrapHandler):
        return _drop_empty(handler(self), ("premise_roles", "asserted_verified"))


class SourceIdentity(BaseModel):
    """One input a fidelity reviewer is shown, by identity and digest: the task record, a supplied text, a supporting
    claim or the claim itself. ``shown_chars`` is less than ``total_chars`` when only part of a supplied text was shown."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["task", "supplied_text", "supporting_claim", "claim"]
    ident: str
    sha256: str = Field(min_length=64, max_length=64)
    title: Optional[str] = None
    provenance: Optional[str] = None
    total_chars: int = Field(ge=0)
    shown_chars: int = Field(ge=0)


class PremiseSource(BaseModel):
    """Premise-to-source mapping for a fidelity reviewer: what each assertion of the encoding cites, and what the
    deterministic checks found (located, figures stated, task authority validated) with the support level."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    assertion_id: str
    role: Literal["premise", "conclusion"]
    label: Optional[str] = None
    grounding_kind: Optional[str] = None
    certainty: Optional[str] = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    verified: Optional[bool] = None
    support: Optional[GroundingSupportLevel] = None
    checks: list[GroundingCheck] = Field(default_factory=list)


class ReviewBinding(BaseModel):
    """The exact inputs a fidelity review saw, and their versions. ``digest`` is the sha256 of the canonical JSON of every
    other field. A review is current only while the digest recomputed from the current claim, translation, supporting
    claims, supplied texts and task equals it: a changed source or supporting claim makes an earlier review stale even
    when the claim text is unchanged."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim_id: str
    claim_record_sha256: str
    translation_id: str
    problem_digest: str
    interpretation_sha256: str
    supporting_claims: dict[str, str] = Field(default_factory=dict, description="claim_id -> sha256 of the canonical claim record")
    supplied_texts: dict[str, str] = Field(default_factory=dict, description="document_id -> sha256 of the canonical supplied text record")
    task_sha256: Optional[str] = None
    response_sha256: Optional[str] = None
    translator_version: str
    review_prompt_version: str
    ir_version: str
    digest: str = Field(min_length=64, max_length=64)


class SemanticFidelityReview(BaseModel):
    """Advisory review of whether the formalization matches the claim's meaning.
    Produced by an independent reviewer (model or human). Never a verification."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    review_id: str
    translation_id: str
    verdict: Literal["faithful", "unfaithful", "uncertain"]
    issues: list[str] = Field(default_factory=list)
    reviewer: ProviderInfo
    advisory_only: Literal[True] = True
    created_at: str
    binding: Optional[ReviewBinding] = Field(default=None, description="the inputs the review saw; None for a review made without them")
    evidence_supplied: bool = Field(default=False, description="the request carried the original task (when known), the supporting claims, the supplied texts and the premise-to-source mapping")
    evidence_truncated: list[str] = Field(default_factory=list, description="supplied texts shown to the reviewer only in part")


class ReleaseAssessment(BaseModel):
    """Whether this claim's checks permit releasing the answer automatically, kept apart from the formal status.

    Application code (``outcome.assess_release``) derives it deterministically: the formal check must pass for the
    query (ENTAILED, CONSISTENT, SATISFIABLE) on a TRANSLATED claim, every premise the result relies on must be
    established (no ungrounded or unverified dependency, no failed grounding check, no partial reference support),
    no retry may have changed the claim beyond what its source states, no structural error may stand, and the
    required fidelity review must be ``faithful``, bound to the current inputs and made with the evidence. Anything
    unresolved is listed and the answer is not released on this claim's strength. A formal ENTAILED alone never
    grants release; the model's review never replaces the formal check."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    permitted: bool
    formal_status: VerificationStatus
    formal_check_passed: bool
    evidence_resolved: bool
    fidelity: Literal["faithful", "unfaithful", "uncertain", "missing", "stale", "unbound", "without_evidence"]
    unresolved: list[str] = Field(default_factory=list)
    policy: str = "release-v1"


class ClaimVerificationOutcome(BaseModel):
    """What the verification layer hands to the Overseer for one claim.

    ``display_status`` is derived deterministically: a non-TRANSLATED translation
    maps to its own status; otherwise it is the engine's status. The Overseer must
    verify ``verification.signature`` before trusting it.
    """
    model_config = ConfigDict(extra="forbid")
    outcome_id: str
    request_id: str
    report_id: str
    claim_id: str
    translation: TranslationResult
    verification: Optional[VerificationResult] = None
    semantic_review: Optional[SemanticFidelityReview] = None
    structural_findings: list[StructuralFinding] = Field(default_factory=list)
    display_status: VerificationStatus
    summary: str = Field(max_length=4000, description="plain-language statement of what was checked, under which assumptions, and what remains unverified")
    created_at: str
    release: Optional[ReleaseAssessment] = Field(default=None, description="permission to release, separate from the formal status (set by compose_outcome)")
    named_diagnostics: list[NamedDiagnostic] = Field(default_factory=list, description=(
        "the argument diagnosis of this claim (rules argdiag-2): the trusted engine result's diagnostics merged with the claim "
        "layer's; advisory, they never change display_status, and release refuses any whose effective severity is warning or "
        "error. Left out of every dump while empty"))
    diagnosis_incomplete: list[str] = Field(default_factory=list, description=(
        "every rule or layer of the diagnosis that raised, ran out of budget or overflowed its bound, named: what it would "
        "have found is not known, never 'none found'. Left out of every dump while empty"))

    @model_serializer(mode="wrap")
    def _omit_new_empty(self, handler: SerializerFunctionWrapHandler):
        return _drop_empty(handler(self), ("named_diagnostics", "diagnosis_incomplete"))
