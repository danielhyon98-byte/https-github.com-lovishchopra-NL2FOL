"""Named diagnostics: the shared model of the argument diagnosis (rules ``argdiag-2``).

A named diagnostic says, in the closed vocabulary below, what is wrong with how an answer argues, cites or calculates,
as far as deterministic code can tell from the engine result, the IR, the grounding records and closed reference data.
It never says that a premise is true, that a translation is faithful or that an interpretation is right: like every
result it concerns the encoding and this code only (the scope statement stays last wherever it is shown).

Rules every diagnostic obeys:

* **Diagnostics only add.** A diagnostic never changes an engine status, a display status, a dependency list, a
  grounding check or an existing finding, and never turns a non-success into success. It may add a line, a record or a
  receipt finding, move a receipt from ACCEPTED to ACCEPTED_WITH_FINDINGS, or make a result NOT releasable: release
  reads the *effective* severity (:func:`effective_severity`), so a capped warning still blocks it.
* **One severity everywhere.** A cap (an ambiguous translation, a task that is not source-bound) is applied where the
  diagnostic is made and recorded in ``capped_from`` and ``cap_reason``, so the engine's signed copy, the outcome, the
  receipt and every reader see the same record.
* **The IR is data.** ``MissingLink.expr`` holds the missing step as an IR expression (validated against the IR schema,
  never evaluated); every other field is plain text, cut to its bound.
* **Absent is "not computed".** A result without ``argument_rules`` was not diagnosed; that never reads as "none found".

``NAMED_CODES`` is the complete table of the new codes (``ARG-*``, ``EVD-*``, ``ST-*`` and the channel codes
``INT-ARG-001``, ``INT-REQ-017`` and ``INT-XENC-001``, which exist only as receipt findings). ``DEFECT_OF_CODE`` gives
existing finding codes their canonical label. ``DEFECT_LABELS`` are the 28 canonical labels the corpus and the overseer
score against; the key ``defect`` is fixed.

This module imports neither z3 nor the engine package (a test pins this), so a deployment without the Z3 engine still
carries and reads the claim, report, STEM and channel diagnostics, and reads "not computed" for the engine layer.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, TypeAdapter, field_validator, model_serializer, model_validator

from .ir.canonical import canonical_json, sha256_hex
from .ir.schema import Expr
from .version import ARG_RULES_VERSION

__all__ = [
    "DEFECT_LABELS", "DefectLabel", "Severity", "Layer", "Derivation", "CapReason", "SEVERITY_RANK", "SEVERITIES",
    "LAYERS", "DERIVATIONS", "CAP_REASONS", "EvidenceSpan", "MissingLink", "NamedDiagnostic", "CodeSpec", "NAMED_CODES",
    "DEFECT_OF_CODE", "DEFECT_OF_CHECK_KIND", "ARG_RULES_VERSION", "MAX_PER_CLAIM", "MAX_PER_RECEIPT", "MAX_MESSAGE_CHARS",
    "MAX_EVIDENCE", "MAX_DERIVED_DIGESTS", "SECTION_HEADING", "SUCCESS_WORDS", "FORGERY_WORDS", "one_line", "model_text", "named_diagnostic", "cap", "apply_cap_rule",
    "effective_severity", "is_blocking", "blocking_release_lines", "CAPPED_RELEASE_LEAD", "merge", "ordered", "suppress_dominated", "bounded", "defect_of",
    "defect_of_check_kind", "from_finding", "finding_message", "display_line", "diagnosis_section", "rules_state",
    "incomplete_rules", "named_codes_manifest", "named_codes_digest", "summary_counts", "code_spec",
]

# ----------------------------------------------------------------------------------------------- the vocabulary

#: The 28 canonical defect labels, exactly as the corpus scores them (the order is part of the contract).
DEFECT_LABELS: tuple[str, ...] = (
    "leap_in_logic", "affirming_the_consequent", "denying_the_antecedent", "hasty_generalisation", "false_dilemma",
    "circular_reasoning", "equivocation", "causal_leap", "bare_assertion", "contradiction", "vacuous_argument",
    "lack_of_evidence", "unchecked_source", "source_mismatch", "altered_quotation", "invented_figure",
    "cherry_picked_data", "uncheckable_authority", "stem_wrong_formula", "stem_unit_error", "stem_dimension_error",
    "stem_arithmetic_slip", "stem_invalid_step", "stem_rounding_changes_conclusion", "stem_extrapolation",
    "stem_missing_working", "stem_contradictory_givens", "stem_symbol_conflict",
)
DefectLabel = Literal[
    "leap_in_logic", "affirming_the_consequent", "denying_the_antecedent", "hasty_generalisation", "false_dilemma",
    "circular_reasoning", "equivocation", "causal_leap", "bare_assertion", "contradiction", "vacuous_argument",
    "lack_of_evidence", "unchecked_source", "source_mismatch", "altered_quotation", "invented_figure",
    "cherry_picked_data", "uncheckable_authority", "stem_wrong_formula", "stem_unit_error", "stem_dimension_error",
    "stem_arithmetic_slip", "stem_invalid_step", "stem_rounding_changes_conclusion", "stem_extrapolation",
    "stem_missing_working", "stem_contradictory_givens", "stem_symbol_conflict",
]
Severity = Literal["error", "warning", "info"]
Layer = Literal["engine", "claim", "report", "stem", "channel"]
#: Where a diagnostic's evidence comes from (closed).
Derivation = Literal[
    "engine_status",      # restates the engine's own status or diagnostic (E108, E112, INCONSISTENT_PREMISES)
    "engine_recheck",     # derived engine runs over the same bound problem
    "ir_structure",       # a shape rule over the validated IR (expressions, recorded grounding kinds)
    "ir_glosses",         # a bounded token rule over the IR's own meanings and labels
    "grounding_record",   # GroundingCheck records made in this process
    "source_text",        # a bounded token rule over the claim, the request or a supplied text
    "claim_structure",    # claim roles and supporting_claim_ids of the report
    "stem_reference",     # the closed STEM reference data
    "stem_engine",        # a STEM check decided by the engine
    "request_reading",    # the request parser
]
CapReason = Literal["ambiguous_translation", "not_source_bound"]

SEVERITIES: tuple[str, ...] = ("info", "warning", "error")
SEVERITY_RANK: Mapping[str, int] = MappingProxyType({"info": 0, "warning": 1, "error": 2})
LAYERS: tuple[str, ...] = ("engine", "claim", "report", "stem", "channel")
DERIVATIONS: tuple[str, ...] = ("engine_status", "engine_recheck", "ir_structure", "ir_glosses", "grounding_record", "source_text",
                                "claim_structure", "stem_reference", "stem_engine", "request_reading")
CAP_REASONS: tuple[str, ...] = ("ambiguous_translation", "not_source_bound")

#: Bounds. A claim holds at most MAX_PER_CLAIM diagnostics and a receipt MAX_PER_RECEIPT; an overflow is counted where the
#: list is shown (an outcome's ``diagnosis_incomplete``, the receipt summary, an engine result's ``argument_rules``), never
#: dropped silently.
MAX_PER_CLAIM = 32
MAX_PER_RECEIPT = 256
MAX_MESSAGE_CHARS = 600
MAX_EVIDENCE = 8
MAX_DERIVED_DIGESTS = 24
_MAX_IDS = 128
_MAX_RELATED = 32
_MAX_LINK_PREMISES = 16
_MAX_EXPR_NODES = 2_000
_MAX_EXPR_DEPTH = 128

#: The heading of the diagnosis section of an outcome summary.
SECTION_HEADING = f"Argument diagnosis (advisory; the status above is unchanged; rules {ARG_RULES_VERSION})"
#: Words no message template, display line or heading of this release may contain: a diagnosis never reads as a success.
SUCCESS_WORDS: tuple[str, ...] = ("valid", "sound", "correct", "passed", "proves", "proven", "success")
#: What model text (a symbol's meaning, a premise's label, a claim) may not carry into a diagnostic message or a missing
#: link: the success words, and the words of a status or a summary section ("VERIFIED", "release permitted", "Argument
#: diagnosis ...: none found"). :func:`model_text` writes each as "[...]" (repair round 1, re-run review ADV-14).
FORGERY_WORDS: tuple[str, ...] = SUCCESS_WORDS + ("verified", "verifies", "permitted", "entailed", "none found", "argument diagnosis", "release")
_FORGERY_RE = re.compile(r"\b(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(FORGERY_WORDS, key=len, reverse=True)) + r")\b",
                         re.IGNORECASE)
#: Line breaks (every Unicode one), tabs and the other control characters: none may reach a display line.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def one_line(text: Any) -> str:
    """``text`` on one line: each run of line breaks, tabs and other control characters is one space. A display line built
    from it can never start a line of its own (re-run review ADV-10: a label that wrote "Release ...: permitted." as a
    summary line of its own)."""
    return _CONTROL_RE.sub(" ", str(text) if text is not None else "")


def model_text(text: Any, limit: Optional[int] = None) -> str:
    """Model text as a diagnostic message, a missing link or a summary line may show it: on one line (:func:`one_line`,
    every run of spaces one), each :data:`FORGERY_WORDS` word written "[...]" (re-run review ADV-14), and cut to ``limit``
    characters. The evidence spans of a diagnostic keep the text as written; only what is displayed is masked, so a gloss
    can never write a success word, a status or a summary line into a diagnosis."""
    s = _FORGERY_RE.sub("[...]", " ".join(one_line(text).split()))
    return s if limit is None or len(s) <= limit else s[: max(0, limit - 3)].rstrip() + "..."

_CODE_RE = re.compile(r"[A-Z]{2,5}-[A-Z]{2,8}-[0-9]{3}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_RULE_VERSION_RE = re.compile(r"argdiag-[0-9]{1,4}")
_INCOMPLETE = f"{ARG_RULES_VERSION}/incomplete:"
_REASON_RE = re.compile(r"[^a-z0-9_.:-]+")
_EXPR_ADAPTER: TypeAdapter = TypeAdapter(Expr)


def _rank(severity: str) -> int:
    return SEVERITY_RANK[severity]


def _drop_empty(data: Any, fields: Sequence[str]) -> Any:
    """Leave ``fields`` out of a dump while they are ``None`` or empty (records stay compact and old shapes unchanged)."""
    if isinstance(data, dict):
        for name in fields:
            if name in data and (data[name] is None or data[name] == [] or data[name] == ()):
                del data[name]
    return data


def _cut(text: Any, limit: int) -> str:
    s = str(text) if text is not None else ""
    return s if len(s) <= limit else s[: max(0, limit - 3)].rstrip() + "..."


# ----------------------------------------------------------------------------------------------- the records

class EvidenceSpan(BaseModel):
    """A span the diagnostic rests on, cut from its source (never paraphrased). ``start``/``end`` are character offsets
    into the named source when the span was located there."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_kind: Literal["claim", "supporting_claim", "supplied_text", "task", "answer", "premise_label", "symbol_meaning"]
    source_id: str = Field(max_length=200)
    start: Optional[int] = Field(default=None, ge=0)
    end: Optional[int] = Field(default=None, ge=0)
    text: str = Field(max_length=300)

    @model_validator(mode="after")
    def _span(self) -> "EvidenceSpan":
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("an evidence span ends before it starts")
        return self

    @model_serializer(mode="wrap")
    def _compact(self, handler: SerializerFunctionWrapHandler) -> Any:
        return _drop_empty(handler(self), ("start", "end"))


def _check_expr(value: Any) -> Optional[dict]:
    """``value`` as a validated IR expression (canonical dump), refusing anything else. Size and depth are bounded before
    the schema reads it, so a hostile record cannot exhaust the validator. Nothing is evaluated."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("missing_link.expr must be an IR expression object")
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_EXPR_NODES or depth > _MAX_EXPR_DEPTH:
            raise ValueError("missing_link.expr is too large or too deep")
        children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
        for child in children:
            if isinstance(child, (dict, list)):
                stack.append((child, depth + 1))
    try:
        expr = _EXPR_ADAPTER.validate_python(value)
    except RecursionError:
        raise ValueError("missing_link.expr is nested too deeply") from None
    return expr.model_dump(mode="json", exclude_none=True)


class MissingLink(BaseModel):
    """The step the proof needs and no source or rule states: the writer's own link, or a bridge no premise states.
    ``premise_ids`` are the writer's premises standing in for it ([] for a bridge); ``antecedent``, ``consequent`` and
    ``text`` are rendered from the symbols' meanings ("if <antecedent> then <consequent>", or "either ... or ..., and
    nothing else"); ``expr`` is the step as IR data, validated against the IR schema and never evaluated."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    premise_ids: list[str] = Field(default_factory=list, max_length=_MAX_LINK_PREMISES)
    antecedent: str = Field(max_length=300)
    consequent: str = Field(max_length=300)
    text: str = Field(max_length=600)
    expr: Optional[dict] = None

    @field_validator("premise_ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        if any(not isinstance(x, str) or not x or len(x) > 128 for x in v):
            raise ValueError("premise ids are 1 to 128 characters")
        return v

    @field_validator("expr", mode="before")
    @classmethod
    def _expr(cls, v: Any) -> Optional[dict]:
        return _check_expr(v)

    @model_serializer(mode="wrap")
    def _compact(self, handler: SerializerFunctionWrapHandler) -> Any:
        return _drop_empty(handler(self), ("premise_ids", "expr"))


class NamedDiagnostic(BaseModel):
    """One named diagnostic (module docstring). Frozen; a dump leaves out empty optional fields.

    ``code`` is a key of :data:`NAMED_CODES` (never a receipt-only channel code), or an existing finding code given a
    label by :data:`DEFECT_OF_CODE` or by its pack (a finding turned into a diagnostic, :func:`from_finding`). A
    ``NAMED_CODES`` code carries its table's ``defect``, a ``layer`` the table allows and a ``severity`` (and
    ``capped_from``) no higher than the table's maximum. ``capped_from`` is set exactly when a cap lowered the
    severity, together with ``cap_reason``; release reads the higher of the two (:func:`effective_severity`)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str = Field(min_length=9, max_length=18)
    defect: DefectLabel
    severity: Severity
    capped_from: Optional[Severity] = None
    cap_reason: Optional[CapReason] = None
    layer: Layer
    claim_ids: list[str] = Field(default_factory=list, max_length=64)
    assertion_ids: list[str] = Field(default_factory=list, max_length=_MAX_IDS)
    missing_link: Optional[MissingLink] = None
    evidence: list[EvidenceSpan] = Field(default_factory=list, max_length=MAX_EVIDENCE)
    derivation: Derivation
    derived_problem_digests: list[str] = Field(default_factory=list, max_length=MAX_DERIVED_DIGESTS)
    related_result_ids: list[str] = Field(default_factory=list, max_length=_MAX_RELATED)
    rule_version: str = Field(default=ARG_RULES_VERSION, max_length=16)
    message: str = Field(max_length=MAX_MESSAGE_CHARS)

    @field_validator("claim_ids", "assertion_ids", "related_result_ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        if any(not isinstance(x, str) or not x or len(x) > 128 for x in v):
            raise ValueError("identifiers are 1 to 128 characters")
        return v

    @field_validator("derived_problem_digests")
    @classmethod
    def _digests(cls, v: list[str]) -> list[str]:
        if any(not isinstance(x, str) or not _HEX64_RE.fullmatch(x) for x in v):
            raise ValueError("a derived problem digest is a sha256 hex digest")
        return v

    @field_validator("rule_version")
    @classmethod
    def _rules(cls, v: str) -> str:
        if not _RULE_VERSION_RE.fullmatch(v):
            raise ValueError(f"invalid rule version {v!r}")
        return v

    @model_validator(mode="after")
    def _table(self) -> "NamedDiagnostic":
        if not _CODE_RE.fullmatch(self.code):
            raise ValueError(f"invalid diagnostic code {self.code!r}")
        spec = NAMED_CODES.get(self.code)
        if spec is not None:
            if spec.finding_only:
                raise ValueError(f"{self.code} exists only as a receipt finding, never as a named diagnostic")
            if spec.defect != self.defect:
                raise ValueError(f"{self.code} names {spec.defect}, not {self.defect}")
            if self.layer not in spec.layers:
                raise ValueError(f"{self.code} is not a {self.layer}-layer code")
            top = _rank(spec.max_severity)
            if _rank(self.severity) > top or (self.capped_from is not None and _rank(self.capped_from) > top):
                raise ValueError(f"{self.code} is at most {spec.max_severity}")
        elif self.code.split("-", 1)[0] in _NEW_FAMILIES:
            raise ValueError(f"unknown named code {self.code!r}")
        if (self.capped_from is None) != (self.cap_reason is None):
            raise ValueError("capped_from and cap_reason are set together")
        if self.capped_from is not None and _rank(self.capped_from) <= _rank(self.severity):
            raise ValueError("capped_from must be above the capped severity")
        return self

    @model_serializer(mode="wrap")
    def _compact(self, handler: SerializerFunctionWrapHandler) -> Any:
        return _drop_empty(handler(self), ("capped_from", "cap_reason", "claim_ids", "assertion_ids", "missing_link", "evidence",
                                           "derived_problem_digests", "related_result_ids"))


# ----------------------------------------------------------------------------------------------- the code table

@dataclass(frozen=True)
class CodeSpec:
    """One row of :data:`NAMED_CODES`.

    ``max_severity`` bounds every severity of the code; ``layer`` is its default layer and ``layers`` the layers it may
    be made in; ``owner`` the step that implements the rule (``contract``, ``a``, ``b``, ``c``, ``d``); ``precedence``
    the order of display and of evaluation (lower first); ``family`` groups codes for :func:`suppress_dominated`, where a
    ``generic`` warning gives way to a more specific one on the same assertions; ``warning_scope`` says when a warning is
    shown as one (``source_bound``: only in a source-bound task, otherwise capped at info with ``not_source_bound``;
    ``source_bound_or_data``: also when the report supplies data texts); ``capped_on_ambiguous`` whether the cap of an
    ambiguous translation applies (the equivocation codes are exempt: the ambiguity is the defect); ``finding_only`` for
    the channel codes that exist only as receipt findings; ``stated_by`` the existing finding that already states the
    condition on a receipt, so no INT-ARG-001 is added for it."""
    code: str
    defect: Optional[str]
    max_severity: str
    layer: str
    owner: str
    precedence: int
    meaning: str
    layers: tuple[str, ...] = ()
    family: str = "argument"
    generic: bool = False
    warning_scope: str = "always"
    capped_on_ambiguous: bool = False
    finding_only: bool = False
    stated_by: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.layers:
            object.__setattr__(self, "layers", (self.layer,))


def _arg(code: str, defect: str, sev: str, prec: int, meaning: str, *, layer: str = "engine", layers: tuple[str, ...] = (), generic: bool = False,
         ambiguous_cap: bool = True, stated_by: Optional[str] = None) -> CodeSpec:
    return CodeSpec(code=code, defect=defect, max_severity=sev, layer=layer, owner="b", precedence=prec, meaning=meaning, layers=layers,
                    family="argument", generic=generic, capped_on_ambiguous=ambiguous_cap, stated_by=stated_by)


def _evd(code: str, defect: str, sev: str, prec: int, meaning: str, *, layer: str = "claim", scope: str = "always") -> CodeSpec:
    return CodeSpec(code=code, defect=defect, max_severity=sev, layer=layer, owner="a", precedence=prec, meaning=meaning, family="evidence",
                    warning_scope=scope, capped_on_ambiguous=True)


def _st(code: str, defect: str, sev: str, prec: int, meaning: str) -> CodeSpec:
    return CodeSpec(code=code, defect=defect, max_severity=sev, layer="stem", owner="c", precedence=prec, meaning=meaning, family="stem")


def _int(code: str, sev: str, owner: str, prec: int, meaning: str) -> CodeSpec:
    return CodeSpec(code=code, defect=None, max_severity=sev, layer="channel", owner=owner, precedence=prec, meaning=meaning, family="channel",
                    finding_only=True)


_TABLE: tuple[CodeSpec, ...] = (
    # ---- engine layer (engine.argument; signed with the result)
    _arg("ARG-CONTRA-001", "contradiction", "error", 10, "the encoded premises contradict each other; the conflicting premises are named",
         stated_by="INT-REQ-007"),
    _arg("ARG-VAC-001", "vacuous_argument", "warning", 20, "vacuous: the point holds whatever the premises say (E108)"),
    _arg("ARG-CIRC-001", "circular_reasoning", "warning", 30,
         "circular: premises no check established restate the point (E112 on the result, or the translation refused as circular)",
         layers=("engine", "claim")),
    _arg("ARG-CIRC-002", "circular_reasoning", "warning", 31,
         "circular: the point is equivalent to one premise no check established, without restating it symbol for symbol"),
    _arg("ARG-CIRC-003", "circular_reasoning", "warning", 32,
         "circular by paraphrase: the writer's link derives the point from a fact whose gloss only restates the point's gloss "
         "(report layer: a claim's own reason clause only restates its point, read where no encoding was decided)", layers=("engine", "report")),
    _arg("ARG-REFUTE-001", "contradiction", "warning", 40, "the premises a check verified entail the negation of the point: the stated evidence refutes it"),
    _arg("ARG-AC-001", "affirming_the_consequent", "warning", 50,
         "affirming the consequent: from 'if P then Q' and Q the point concludes P, or the writer's link Q -> P stands beside P -> Q"),
    _arg("ARG-DA-001", "denying_the_antecedent", "warning", 51,
         "denying the antecedent: from 'if P then Q' and not P the point concludes not Q, or the writer's link not P -> not Q stands beside P -> Q"),
    _arg("ARG-FD-001", "false_dilemma", "warning", 52,
         "false dilemma: the proof needs the writer's either/or, which is no tautology and whose options are not complementary"),
    _arg("ARG-HG-001", "hasty_generalisation", "warning", 53, "hasty generalisation: a universal point drawn from instance facts through the writer's own link"),
    _arg("ARG-CL-001", "causal_leap", "warning", 54, "causal leap: the writer's link reads a cause into a sequence in time, and nothing in the problem states a control"),
    _arg("ARG-EQ-002", "equivocation", "warning", 55, "equivocation: the missing bridge joins two senses of one head noun", ambiguous_cap=False),
    _arg("ARG-EQ-003", "equivocation", "warning", 56,
         "equivocation: a link gives the bare generic sense of a word that the symbol's meaning qualifies", ambiguous_cap=False),
    _arg("ARG-NS-001", "leap_in_logic", "warning", 60, "the point does not follow, and no premise mentions any symbol of the point: no reason given touches it",
         generic=True),
    _arg("ARG-NS-002", "leap_in_logic", "warning", 61,
         "the point does not follow; one bridge from a stated fact to the antecedent of a stated conditional would make it follow, and that bridge is the missing link",
         generic=True),
    _arg("ARG-INV-001", "leap_in_logic", "warning", 62, "the point does not follow from its encoded reasons, which mention it; no more specific pattern is named",
         generic=True),
    _arg("ARG-NS-003", "leap_in_logic", "warning", 63,
         "the point follows only through the writer's link from a reason that shares no word with it, joined in the answer only by a connective and "
         "stated nowhere: an unbridged leap, given with its missing link", layer="claim", generic=True),
    _arg("ARG-PART-001", "leap_in_logic", "info", 70,
         "the falsified parts of the point use only symbols no premise mentions while the rest follows: the unlinked judgement is named"),
    _arg("ARG-LINK-001", "leap_in_logic", "info", 80,
         "the point does not follow from the premises a check verified; it follows only with the writer's own link(s), each given as the missing link"),
    _arg("ARG-FACT-001", "lack_of_evidence", "info", 81, "the proof also needs fact premises that no check established; they are listed for the evidence rules"),
    _arg("ARG-LINK-002", "unchecked_source", "info", 82,
         "the point follows with a rule the writer states from subject knowledge (marked as stated, so no missing link), which no check established"),
    # ---- claim and report layers, argument (translate.diag_argument)
    _arg("ARG-EQ-001", "equivocation", "warning", 57, "equivocation: the translation flagged one word read in two senses", layer="claim", ambiguous_cap=False),
    _arg("ARG-BARE-001", "bare_assertion", "warning", 90,
         "bare assertion: a judgement the request asks to be reasoned stands with no reason in its answer section", layer="report"),
    # ---- claim and report layers, evidence (translate.diag_evidence)
    _evd("EVD-SRC-003", "source_mismatch", "warning", 100, "source mismatch: the point rests on a premise whose grounding check failed"),
    _evd("EVD-SRC-005", "unchecked_source", "warning", 109,
         "unchecked task authority: a needed premise claims the task's authority with no excerpt, and the task material does not hold it"),
    _evd("EVD-SRC-001", "unchecked_source", "warning", 101, "unchecked source: a needed fact premise claims a text or task authority that no check verified",
         scope="source_bound"),
    _evd("EVD-AUTH-001", "uncheckable_authority", "warning", 102,
         "uncheckable authority: a needed premise leans on an unattributed authority or data cue, and no check verified it"),
    _evd("EVD-FIG-001", "invented_figure", "warning", 103,
         "invented figure: a needed figure occurs in no supplied text and not in the task record, and no written calculation over stated figures gives it",
         scope="source_bound_or_data"),
    _evd("EVD-CHERRY-001", "cherry_picked_data", "warning", 104,
         "cherry-picked data: the point's direction over a stated period fails with the period's own endpoint values, which the encoding leaves out"),
    _evd("EVD-LACK-001", "lack_of_evidence", "warning", 105, "lack of evidence: a needed fact premise claims no source and no check verified it", scope="source_bound"),
    _evd("EVD-SRC-004", "unchecked_source", "info", 106,
         "the provider wrote its own verification flag on a grounding; the flag was discarded because only checks set it"),
    _evd("EVD-SRC-002", "unchecked_source", "info", 107,
         "attribution not checked: a claim attributes content to a supplied document whose words do not locate it; never shown as false", layer="report"),
    _evd("EVD-LACK-002", "lack_of_evidence", "info", 108,
         "lack of evidence: a claim states a change in a quantity with no figure, and its subject occurs in no supplied text and not in the request",
         layer="report"),
    _evd("EVD-SRC-006", "source_mismatch", "warning", 110,
         "source mismatch: a claim credits a supplied document with one stance on what it is about, and the document states only the opposite stance",
         layer="report"),
    # ---- STEM layer (stem pack findings with a defect, or engine-decided STEM checks)
    _st("ST-REF-001", "stem_wrong_formula", "warning", 200,
        "wrong formula: the answer's law for a quantity with a fixed reference identity has another dimension than the data-booklet formula, which is named"),
    _st("ST-REF-002", "stem_wrong_formula", "warning", 209,
        "wrong formula: the answer's law has exactly the variables of the data-booklet laws for its quantity and differs from each of them as a function"),
    _st("ST-UNIT-003", "stem_unit_error", "warning", 201,
        "unit error: the working uses the bare numbers of non-SI bindings while the result carries an SI unit; the as-written reading holds and the SI reading fails"),
    _st("ST-STEP-001", "stem_invalid_step", "warning", 202,
        "invalid step: applying the stated operation to the previous line does not give the next line (an identity check decided by the engine)"),
    _st("ST-STEP-003", "stem_invalid_step", "warning", 212,
        "invalid step: a rewrite inside a chain is no identity: its two sides differ at a sample point of the unknown (rational enclosures)"),
    _st("ST-STEP-002", "stem_invalid_step", "info", 203,
        "a solving step that is not reversible under the stated domain guards changes the solution set (decided by the engine)"),
    _st("ST-ROUND-001", "stem_rounding_changes_conclusion", "warning", 204,
        "rounding changes the conclusion: the same comparison with the unrounded chain value has the opposite truth"),
    _st("ST-RANGE-001", "stem_extrapolation", "warning", 205,
        "extrapolation: a stated model is evaluated outside the range of the request's data series, with no caveat"),
    _st("ST-WORK-001", "stem_missing_working", "warning", 206,
        "missing working: the request asks for working and the answer gives a result with no formula, substitution or working line"),
    _st("ST-GIVEN-003", "stem_contradictory_givens", "warning", 210,
        "contradictory givens: a probability stated outside [0, 1], or events treated as mutually exclusive or independent against the request's figures"),
    _st("ST-GIVEN-004", "stem_contradictory_givens", "warning", 211,
        "contradictory givens: the stated values fix every variable of a law of uniform motion, or the request's counts of two sets, and the law fails"),
    _st("ST-GIVEN-002", "stem_contradictory_givens", "warning", 207,
        "contradictory givens: a symbol of a Given or Data statement is bound again to another value in the same part, and the second value is used"),
    _st("ST-SCOPE-002", "stem_symbol_conflict", "warning", 208,
        "symbol conflict: one symbol is bound to two different quantities in one part, and a later substitution uses one of them"),
    # ---- channel codes (receipt findings only)
    _int("INT-ARG-001", "error", "contract", 300, "the receipt finding for a warning or error named diagnostic on a material claim; it carries the diagnostic's defect"),
    _int("INT-REQ-017", "warning", "d", 301, "the answer hands a system check result to the reader as subject content"),
    _int("INT-XENC-001", "warning", "d", 302, "two encodings of one claim reach opposite definitive answers"),
)

#: The complete code table, read-only.
NAMED_CODES: Mapping[str, CodeSpec] = MappingProxyType({s.code: s for s in _TABLE})
#: Code families whose codes must all be in :data:`NAMED_CODES` (the new vocabulary is closed).
_NEW_FAMILIES = frozenset({"ARG", "EVD"})


def code_spec(code: str) -> Optional[CodeSpec]:
    """The table row of ``code``, or None for a code outside :data:`NAMED_CODES`."""
    return NAMED_CODES.get(code)


# ----------------------------------------------------------------------------------------------- labels of existing codes

#: ``(check-kind regex, label or None)`` for INT-SUBJ-001 and INT-SUBJ-004 when the FormalCheck carries no ``defect`` of
#: its own. First full match wins; None means the kind names no defect.
DEFECT_OF_CHECK_KIND: tuple[tuple[str, Optional[str]], ...] = (
    (r"stem_conversion", "stem_unit_error"),
    (r"stem_algebra", "stem_invalid_step"),
    (r"stem_given", "stem_contradictory_givens"),
    (r"stem_comparison|stem_target|stem_balance", None),
    (r"stem_[a-z_]+|arithmetic|percentage|pair_direction|[a-z_]*arith[a-z_]*", "stem_arithmetic_slip"),
)

#: ``(code regex, message regex or None, label or None)`` for EXISTING finding codes. First matching row wins (the code
#: regex must match the whole code; the message regex is searched); None means the code names no defect.
DEFECT_OF_CODE: tuple[tuple[str, Optional[str], Optional[str]], ...] = (
    (r"INT-REQ-007", None, "contradiction"),
    (r"INT-CONFLICT-00[15]", None, "contradiction"),   # INT-CONFLICT-004 stays unlabelled: a translation fault
    (r"INT-REQ-003", r"\baltered\b", "altered_quotation"),
    (r"INT-REQ-003", None, "source_mismatch"),
    (r"(?:ES|CORE|GEN)-SRC-001", r"\baltered\b", "altered_quotation"),
    (r"(?:ES|CORE|GEN)-SRC-001", None, "source_mismatch"),
    (r"CORE-SRC-005|ES-SRC-008|INT-LEDGER-025|INT-REQ-015", None, "source_mismatch"),
    # repair round 4 (ADV4-12): a figure stated for a year that the named data table states otherwise
    (r"CORE-SRC-007", r"\bfor no year\b", "invented_figure"),
    (r"CORE-SRC-007", None, "source_mismatch"),
    (r"CORE-SRC-003|CORE-SELF-001", None, "unchecked_source"),
    (r"CORE-SRC-002|HI-SRC-004", None, "lack_of_evidence"),
    (r"PS-SRC-001|HI-SRC-003", None, "uncheckable_authority"),
    (r"ST-DIM-00[12]", None, "stem_dimension_error"),
    (r"ST-SCOPE-001", None, "stem_symbol_conflict"),
    *((r"INT-SUBJ-00[14]", rf"\bown (?:{kinds}) statement\b", label) for kinds, label in DEFECT_OF_CHECK_KIND),
    (r"INT-SUBJ-00[14]", None, None),
)
_CODE_ROWS = tuple((re.compile(c), re.compile(m) if m else None, lab) for c, m, lab in DEFECT_OF_CODE)
_KIND_ROWS = tuple((re.compile(k), lab) for k, lab in DEFECT_OF_CHECK_KIND)


def defect_of(code: str, message: Optional[str] = "") -> Optional[str]:
    """The canonical label :data:`DEFECT_OF_CODE` gives an existing finding code (and its message); None when no row
    labels it. Never raises."""
    if not isinstance(code, str):
        return None
    text = message if isinstance(message, str) else ""
    for crx, mrx, label in _CODE_ROWS:
        if crx.fullmatch(code) and (mrx is None or mrx.search(text)):
            return label
    return None


def defect_of_check_kind(kind: Optional[str]) -> Optional[str]:
    """The label of an INT-SUBJ-001 / INT-SUBJ-004 finding by its FormalCheck kind (:data:`DEFECT_OF_CHECK_KIND`)."""
    if not isinstance(kind, str):
        return None
    for rx, label in _KIND_ROWS:
        if rx.fullmatch(kind):
            return label
    return None


# ----------------------------------------------------------------------------------------------- helpers

def named_diagnostic(code: str, *, severity: Optional[str] = None, layer: Optional[str] = None, **fields: Any) -> NamedDiagnostic:
    """A diagnostic of ``code``: the ``defect`` and the default layer come from the table, and the severity is the table's
    maximum, or ``severity`` when that is lower (a requested severity is lowered to the maximum, never raised). Raises
    ``ValueError`` for a code outside the table or a receipt-only channel code."""
    spec = NAMED_CODES.get(code)
    if spec is None or spec.finding_only or spec.defect is None:
        raise ValueError(f"{code!r} is not a named-diagnostic code")
    sev = spec.max_severity
    if severity is not None:
        if severity not in SEVERITY_RANK:
            raise ValueError(f"unknown severity {severity!r}")
        if _rank(severity) < _rank(sev):
            sev = severity
    if "message" in fields:
        fields["message"] = _cut(" ".join(one_line(fields["message"]).split()), MAX_MESSAGE_CHARS)
    return NamedDiagnostic(code=code, defect=spec.defect, severity=sev, layer=layer or spec.layer, **fields)


def effective_severity(d: NamedDiagnostic) -> str:
    """The higher of ``severity`` and ``capped_from``: what release, the response gate and suppression read."""
    if d.capped_from is not None and _rank(d.capped_from) > _rank(d.severity):
        return d.capped_from
    return d.severity


def is_blocking(d: NamedDiagnostic) -> bool:
    """True for a diagnostic whose effective severity is warning or error: it blocks release and leaves a claim unresolved."""
    return _rank(effective_severity(d)) >= _rank("warning")


#: The lead of the release line for capped diagnostics (:func:`blocking_release_lines`).
CAPPED_RELEASE_LEAD = "capped diagnostic, shown at info and still blocking release (it names no defect)"


def blocking_release_lines(diags: Iterable[NamedDiagnostic], named_lead: str, limit: int) -> list[str]:
    """The release lines of the blocking diagnostics (:func:`is_blocking`): those shown at warning or error under
    ``named_lead`` with their defect labels ("named defect on this claim: ARG-AC-001 (affirming_the_consequent)"), and the
    capped ones, shown at info, under :data:`CAPPED_RELEASE_LEAD` with their cap and no defect label ("EVD-LACK-001 (capped
    from warning: not_source_bound)"): a cap changes what is shown, never what is permitted, so a capped diagnostic still
    blocks, and its line accuses nothing, as its displayed severity does not (repair round 4,
    INFO-NAMED-DEFECTS-ON-CONTROLS). At most ``limit`` codes per line, the rest counted."""
    blocking = [d for d in diags if is_blocking(d)]
    shown = list(dict.fromkeys(f"{d.code} ({d.defect})" for d in blocking if _rank(d.severity) >= _rank("warning")))
    capped = list(dict.fromkeys(f"{d.code} (capped from {d.capped_from}: {d.cap_reason})" for d in blocking if _rank(d.severity) < _rank("warning")))
    out: list[str] = []
    for lead, items in ((named_lead, shown), (CAPPED_RELEASE_LEAD, capped)):
        if items:
            out.append(f"{lead}: " + ", ".join(items[:limit]) + (f" and {len(items) - limit} more" if len(items) > limit else ""))
    return out


_ASSUMED_READING = "on the translator's assumed reading"


def cap(diags: Iterable[NamedDiagnostic], level: str, reason: str) -> list[NamedDiagnostic]:
    """Lower every severity above ``level`` to ``level``, recording ``capped_from`` (the severity before the first cap)
    and ``cap_reason``; a diagnostic at or below ``level`` is returned unchanged. An ambiguous-translation cap adds "on
    the translator's assumed reading" to the message."""
    if level not in SEVERITY_RANK:
        raise ValueError(f"unknown severity {level!r}")
    if reason not in CAP_REASONS:
        raise ValueError(f"unknown cap reason {reason!r}")
    out: list[NamedDiagnostic] = []
    for d in diags:
        if _rank(d.severity) <= _rank(level):
            out.append(d)
            continue
        message = d.message
        if reason == "ambiguous_translation" and _ASSUMED_READING not in message:
            suffix = f" ({_ASSUMED_READING})"
            message = _cut(message, MAX_MESSAGE_CHARS - len(suffix)) + suffix
        data = d.model_dump(mode="python")
        data.update(severity=level, capped_from=d.capped_from or d.severity, cap_reason=d.cap_reason or reason, message=message)
        out.append(NamedDiagnostic.model_validate(data))
    return out


def apply_cap_rule(diags: Iterable[NamedDiagnostic], reason: str, *, source_bound: bool = False, data_texts: bool = False) -> list[NamedDiagnostic]:
    """Apply the contract's cap ``reason`` at info to the diagnostics it covers, leaving the others unchanged:

    * ``ambiguous_translation``: every code whose row says ``capped_on_ambiguous`` (every ARG-* and EVD-* code except
      the equivocation codes, whose defect is the ambiguity itself);
    * ``not_source_bound``: every code whose ``warning_scope`` does not hold (``source_bound`` unless ``source_bound``;
      ``source_bound_or_data`` unless ``source_bound`` or ``data_texts``).
    """
    if reason not in CAP_REASONS:
        raise ValueError(f"unknown cap reason {reason!r}")
    out: list[NamedDiagnostic] = []
    for d in diags:
        spec = NAMED_CODES.get(d.code)
        if spec is None:
            covered = False
        elif reason == "ambiguous_translation":
            covered = spec.capped_on_ambiguous
        else:
            covered = (spec.warning_scope == "source_bound" and not source_bound) or (spec.warning_scope == "source_bound_or_data" and not (source_bound or data_texts))
        out.extend(cap([d], "info", reason) if covered else [d])
    return out


def _key(d: NamedDiagnostic) -> tuple:
    return (d.code, tuple(sorted(d.claim_ids)), tuple(sorted(d.assertion_ids)))


def merge(*lists: Iterable[NamedDiagnostic]) -> list[NamedDiagnostic]:
    """One diagnostic per ``(code, claim_ids, assertion_ids)``, keeping the highest effective severity (the first such on a
    tie), in order of first appearance. Deterministic."""
    best: dict[tuple, NamedDiagnostic] = {}
    for seq in lists:
        for d in seq or ():
            k = _key(d)
            held = best.get(k)
            if held is None or _rank(effective_severity(d)) > _rank(effective_severity(held)):
                best[k] = d
    return list(best.values())


def _precedence(code: str) -> int:
    spec = NAMED_CODES.get(code)
    return spec.precedence if spec is not None else 900


def ordered(diags: Iterable[NamedDiagnostic]) -> list[NamedDiagnostic]:
    """Sorted by claim, then code precedence, then assertion ids (then code, effective severity and message, so the order
    is total and deterministic)."""
    return sorted(diags, key=lambda d: (tuple(sorted(d.claim_ids)), _precedence(d.code), tuple(d.assertion_ids), d.code,
                                       -_rank(effective_severity(d)), d.message))


def suppress_dominated(diags: Iterable[NamedDiagnostic]) -> list[NamedDiagnostic]:
    """Leave out a generic warning (``CodeSpec.generic``) when a more specific warning or error of the same family stands
    on the same claims and on every assertion the generic one names (ARG-HG-001 suppresses ARG-NS-001 on f09). Severities
    are read as effective severities; info records are always kept."""
    items = list(diags)
    out: list[NamedDiagnostic] = []
    for d in items:
        spec = NAMED_CODES.get(d.code)
        if spec is not None and spec.generic and is_blocking(d):
            mine = set(d.assertion_ids)
            claims = tuple(sorted(d.claim_ids))
            dominated = any(
                e is not d and is_blocking(e) and (es := NAMED_CODES.get(e.code)) is not None and es.family == spec.family and not es.generic
                and tuple(sorted(e.claim_ids)) == claims and mine <= set(e.assertion_ids)
                for e in items)
            if dominated:
                continue
        out.append(d)
    return out


def bounded(diags: Sequence[NamedDiagnostic], limit: int = MAX_PER_CLAIM) -> tuple[list[NamedDiagnostic], int]:
    """``(the first limit diagnostics of the ordered list, how many were left out)``; the caller records the overflow."""
    items = ordered(diags)
    return items[:limit], max(0, len(items) - limit)


def finding_message(d: NamedDiagnostic) -> str:
    """The message of the INT-ARG-001 receipt finding for ``d``: ``"<defect> [<code>]: <message>"``."""
    return f"{d.defect} [{d.code}]: {d.message}"


def from_finding(finding: Any, layer: Optional[str] = None, *, derivation: Optional[str] = None) -> Optional[NamedDiagnostic]:
    """A named diagnostic for a structural or integrity finding that carries a ``defect`` (None when it carries none, or
    when its code exists only as a receipt finding). The code, label, severity (lowered to the table's maximum for a
    ``NAMED_CODES`` code), claims and message are the finding's; ``layer`` defaults to ``stem`` for ST-* codes,
    ``channel`` for an integrity finding (it has ``message_ids``) and ``report`` otherwise. Never raises."""
    try:
        defect = getattr(finding, "defect", None)
        code = getattr(finding, "code", None)
        if not defect or not isinstance(code, str) or defect not in DEFECT_LABELS:
            return None
        spec = NAMED_CODES.get(code)
        if spec is not None and spec.finding_only:
            return None
        severity = getattr(finding, "severity", "warning")
        if spec is not None and _rank(severity) > _rank(spec.max_severity):
            severity = spec.max_severity
        if layer is None:
            layer = "stem" if code.startswith("ST-") else "channel" if hasattr(finding, "message_ids") else "report"
        if spec is not None and layer not in spec.layers:
            layer = spec.layer
        result_id = getattr(finding, "formal_result_id", None)
        related = [r for r in ([result_id] if result_id else []) + list(getattr(finding, "related_result_ids", []) or []) if isinstance(r, str) and r][:_MAX_RELATED]
        if derivation is None:
            derivation = ("stem_engine" if code.startswith(("INT-SUBJ", "ST-")) else "engine_status") if result_id else ("stem_reference" if code.startswith("ST-") else "source_text")
        return NamedDiagnostic(code=code, defect=defect, severity=severity, layer=layer, claim_ids=list(getattr(finding, "claim_ids", []) or [])[:64],
                               derivation=derivation, related_result_ids=list(dict.fromkeys(related)),
                               message=_cut(" ".join(one_line(getattr(finding, "message", "")).split()), MAX_MESSAGE_CHARS))
    except Exception:  # noqa: BLE001 - a finding that cannot be named is left as it is, never lost and never raised
        return None


# ----------------------------------------------------------------------------------------------- display

def display_line(d: NamedDiagnostic) -> str:
    """One display line: ``- <severity> <defect> [<code>] on <ids>: <message>``, then the missing link when the message
    does not give it, and ``(capped from <severity>: <reason>)`` for a capped diagnostic."""
    ids = [one_line(i) for i in (d.assertion_ids or d.claim_ids)]
    message = one_line(d.message).rstrip()
    if message and message[-1] not in ".!?":
        message += "."
    text = f"- {d.severity} {d.defect} [{d.code}]" + (f" on {', '.join(ids[:8])}" + (" ..." if len(ids) > 8 else "") if ids else "") + f": {message}"
    if d.missing_link is not None and d.missing_link.text and d.missing_link.text not in d.message:
        text += f" Missing link: {one_line(d.missing_link.text).rstrip('.')}."
    if d.capped_from is not None:
        text += f" (capped from {d.capped_from}: {d.cap_reason})"
    return text


def rules_state(argument_rules: Optional[str]) -> tuple[str, Optional[str]]:
    """How a result's diagnosis stands: ``("complete", None)`` for this build's rules, ``("incomplete", reason)``,
    ``("other", value)`` for another rule version, ``("not_computed", None)`` when absent (never "none found")."""
    if argument_rules is None:
        return "not_computed", None
    if argument_rules == ARG_RULES_VERSION:
        return "complete", None
    if argument_rules.startswith(_INCOMPLETE):
        return "incomplete", argument_rules[len(_INCOMPLETE):] or "unknown"
    return "other", argument_rules


def incomplete_rules(reason: str) -> str:
    """The ``argument_rules`` value of a diagnosis that did not finish: ``argdiag-2/incomplete:<reason>`` (the reason
    lower-cased and reduced to ``[a-z0-9_.:-]``, at most 64 characters)."""
    token = _REASON_RE.sub("_", str(reason).casefold()).strip("_")[:64] or "unknown"
    return _INCOMPLETE + token


def diagnosis_section(diags: Sequence[NamedDiagnostic], *, engine_state: str = "complete", incomplete: Sequence[str] = (),
                      max_lines: int = 6) -> list[str]:
    """The lines of the diagnosis section of a summary; the status above it is never changed by them.

    ``engine_state`` is :func:`rules_state` of the engine result (``complete``, ``incomplete``, ``other`` or
    ``not_computed``); ``incomplete`` names every rule or layer that did not finish (the engine's reason included).

    * With diagnostics: :data:`SECTION_HEADING` and at most ``max_lines`` lines under it, "and N more" when they do not
      all fit, the last line saying when the diagnosis is incomplete or the engine layer was not computed.
    * Without: "Argument diagnosis incomplete (<reasons>); no rule fired.", "Argument diagnosis: not computed (...)."
      when no current engine result was diagnosed, else "Argument diagnosis: none found (rules argdiag-2)."
    """
    reasons = [str(r) for r in incomplete if r]
    if engine_state == "incomplete" and not any(r.startswith("engine") for r in reasons):
        reasons.insert(0, "engine diagnosis incomplete")
    listed = "; ".join(_cut(r, 120) for r in reasons[:4]) + ("; and more" if len(reasons) > 4 else "")
    items = list(diags)
    if not items:
        if reasons:
            return [f"Argument diagnosis incomplete ({listed}); no rule fired."]
        if engine_state in ("not_computed", "other"):
            return ["Argument diagnosis: not computed (no current engine result was diagnosed by these rules)."]
        return [f"Argument diagnosis: none found (rules {ARG_RULES_VERSION})."]
    note = None
    if reasons:
        note = f"incomplete ({listed}): a rule that did not finish fired nothing"
    elif engine_state in ("not_computed", "other"):
        note = "engine layer not computed: no current engine result was diagnosed by these rules"
    room = max(1, max_lines - (1 if note else 0))
    shown = items if len(items) <= room else items[: room - 1]
    lines = [SECTION_HEADING + ":"] + [display_line(d) for d in shown]
    if len(shown) < len(items):
        lines.append(f"- and {len(items) - len(shown)} more")
    if note:
        lines.append(f"- {note}")
    return lines


def summary_counts(diags: Sequence[NamedDiagnostic]) -> dict[str, int]:
    """Counts for a receipt summary: named, claims, warning or error (as shown), info (as shown), capped, blocking."""
    claims = {c for d in diags for c in d.claim_ids}
    return {"named": len(diags), "claims": len(claims), "warning_or_error": sum(1 for d in diags if d.severity != "info"),
            "info": sum(1 for d in diags if d.severity == "info"), "capped": sum(1 for d in diags if d.capped_from is not None),
            "blocking": sum(1 for d in diags if is_blocking(d))}


# ----------------------------------------------------------------------------------------------- the table as data

def named_codes_manifest() -> dict[str, Any]:
    """The code table, the label vocabulary and the label rows of existing codes, as data (bound into the policy identity
    by :func:`named_codes_digest`)."""
    return {
        "rules": ARG_RULES_VERSION,
        "labels": list(DEFECT_LABELS),
        "codes": [{**asdict(s), "layers": list(s.layers)} for s in sorted(_TABLE, key=lambda s: s.code)],
        "defect_of_code": [list(r) for r in DEFECT_OF_CODE],
        "defect_of_check_kind": [list(r) for r in DEFECT_OF_CHECK_KIND],
        "bounds": {"per_claim": MAX_PER_CLAIM, "per_receipt": MAX_PER_RECEIPT, "message": MAX_MESSAGE_CHARS, "evidence": MAX_EVIDENCE,
                   "derived_digests": MAX_DERIVED_DIGESTS},
    }


def named_codes_digest() -> str:
    """sha256 of :func:`named_codes_manifest` (canonical JSON)."""
    return sha256_hex(canonical_json(named_codes_manifest()))
