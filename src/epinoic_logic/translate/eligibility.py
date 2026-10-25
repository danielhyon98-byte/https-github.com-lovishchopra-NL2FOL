"""Deterministic eligibility decisions.

Which claims the solver may be asked about is a POLICY decision made by code, not
by the specialist agent (whose self-reported eligibility is advisory) and not by
the translator model. The rules key on the claim's role, the agent-proposed kind
and simple lexical cues. They are versioned through ``POLICY_VERSION``.

Summary of the rules (applied in this order; the first match decides):

1. kind ``rubric_judgment``       -> NOT_ELIGIBLE_RUBRIC_JUDGMENT, route ``subject_evaluator``
2. kind ``factual``               -> NOT_ELIGIBLE_FACTUAL, route ``evidence_service``
3. role point | thesis | link     -> PROPOSITIONAL_ARGUMENT when supporting claims other than the
                                     claim itself exist (a self-reference is discarded and recorded),
                                     else NOT_ELIGIBLE_OTHER ("no supporting claims")
4. role structural | quantitative -> ARITHMETIC_CONSTRAINT | QUANTITATIVE_CLAIM when the
                                     text has numerals or comparatives (mark annotations "[2]", part and list
                                     labels "(a)", "(iii)" and named items "Paper 1", "Table 1" are not figures:
                                     ``figure_text``), or (subject profiles that allow QUANTITATIVE_CLAIM only) a
                                     mathematical relation sign between operands (=, ≠, <, >, ≤, ≥, ≈: "F = ma") or a
                                     superscript or subscript digit ("x²", "v₀"), else NOT_ELIGIBLE_OTHER
5. role interpretation | effect | device | analysis | perspective | value | limitation (standalone)
                                  -> NOT_ELIGIBLE_INTERPRETIVE, route ``subject_evaluator``
6. role evidence | counter_evidence | origin | purpose | content
                                  -> QUANTITATIVE_CLAIM when the text carries two or more related dates/figures or a
                                     comparative (exact consistency is checkable; truth is not), else NOT_ELIGIBLE_FACTUAL,
                                     route ``evidence_service`` (a single date or figure has nothing to be checked against:
                                     its only encoding would restate it)
7. role other: by kind            -> formal_logic: PROPOSITIONAL_ARGUMENT; arithmetic: QUANTITATIVE_CLAIM
                                     (with cues); interpretive: NOT_ELIGIBLE_INTERPRETIVE; unknown: NOT_ELIGIBLE_OTHER

An argument in one sentence (repair round 3, ADV3-01). A claim of an argument role with no supporting claims (rule 3), or
of an interpretive or factual role (rules 5 and 6, before their routing), whose own text draws a conclusion from a reason
it states itself (``adapters.markdown.states_own_reason``: "Graphite is not a metal, so graphite does not conduct
electricity"; "Since households borrowed less, the rate rise reduced spending"; "Demand fell because prices rose") is a
PROPOSITIONAL_ARGUMENT: its reason and its point are both in its text, so the argument can be encoded, and the writer's
step from one to the other is diagnosed like any other. A quantitative or structural claim keeps rule 4, except in a
subject profile that allows no quantitative claims, where a figured sentence that argues is read as the argument; a note
(role other) keeps rule 7.
"""
from __future__ import annotations

import re
from typing import Optional

from ..version import POLICY_VERSION
from .contracts import ClaimRecord, EligibilityClass, EligibilityDecision
from .subjects import resolve_profile

ARGUMENT_ROLES = frozenset({"point", "thesis", "link", "judgement"})           # a judgement is an argued position on degree
COUNT_ROLES = frozenset({"structural", "quantitative"})
INTERPRETIVE_ROLES = frozenset({"interpretation", "effect", "device", "analysis", "perspective", "value", "limitation"})
FACTUAL_ROLES = frozenset({"evidence", "counter_evidence", "origin", "purpose", "content"})  # checked by grounding/evidence, not the solver

_NUMERAL_RE = re.compile(r"\d")
#: Superscript and subscript digits (``x²``, ``v₀``), which ``\d`` does not match: numerals for rule 4 in quantitative profiles.
_SCRIPT_DIGIT_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]")
#: A mathematical relation sign between two operands ('F = ma', 'x ≤ 3', 'E ≈ hf'); '==' and arrows are not relations here.
_RELATION_RE = re.compile(r"[\w)\]}²³¹⁰⁴-⁹₀-₉′]\s*(?:<=|>=|=|≠|<|>|≤|≥|≈)(?![=<>])\s*[\w(\[{√±−+-]")
_NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand", "dozen", "half", "third", "quarter", "twice", "double", "triple", "both",
    "single", "pair",
)
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)
_COMPARATIVE_CUES = (
    "more than", "fewer than", "less than", "greater than", "at least", "at most", "no more than",
    "no fewer than", "no less than", "exceeds", "exceed", "below", "above", "under", "over",
    "longer than", "shorter than", "larger than", "smaller than", "higher than", "lower than",
    "equal to", "equals", "exactly", "maximum", "minimum", "within", "between", "as many as",
    "as few as", "too long", "too short", "too many", "too few", "the same number",
)
_COMPARATIVE_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _COMPARATIVE_CUES) + r")\b", re.IGNORECASE)


def has_numeral(text: str, *, scripts: bool = False) -> bool:
    """True when ``text`` contains a digit or a spelled-out number word; with ``scripts``, a superscript
    or subscript digit counts too (rule 4 in profiles that allow quantitative claims)."""
    return bool(_NUMERAL_RE.search(text) or _NUMBER_WORD_RE.search(text) or (scripts and _SCRIPT_DIGIT_RE.search(text)))


#: Numerals that are no figure of the claim: a mark annotation ("[2]", "[1 spare]", "[2 marks]"), a part or list label
#: ("(a)", "(iii)", "(3)", "2." opening a line) and a named item ("Paper 1", "Table 1", "part (b)", "question 3", "Section A").
_MARK_ANNOTATION_RE = re.compile(r"\[\s*\d+(?:\s*(?:marks?|spare))*\s*\]", re.IGNORECASE)
_LABEL_RE = re.compile(r"(?<!\w)\((?:[a-h]|i{1,3}|iv|vi{0,3}|ix|x|\d{1,2})\)|(?m:^\s*(?:\d{1,2}|[a-h])[.)](?=\s))", re.IGNORECASE)
_NAMED_ITEM_RE = re.compile(r"\b(?:paper|section|part|question|unit|topic|criterion|item|step|table|figure|diagram|paragraph|stanza|page|appendix|source)"
                            r"\s+\(?(?:\d{1,3}|[a-h]|i{1,3}|iv|vi{0,3}|ix|x)\)?(?![\w.]\d)", re.IGNORECASE)


def figure_text(text: str) -> str:
    """``text`` without the numerals that are no figure of the claim (mark annotations, part and list labels, named
    items: :data:`_MARK_ANNOTATION_RE`, :data:`_LABEL_RE`, :data:`_NAMED_ITEM_RE`): what the numeric cues are read on, so
    a mark heading "(a) [2]" or "Paper 1 is the unseen-text paper" is no quantitative claim."""
    return _NAMED_ITEM_RE.sub(" ", _LABEL_RE.sub(" ", _MARK_ANNOTATION_RE.sub(" ", text)))


def _figure_count(text: str) -> int:
    """Figures and dates of ``text`` (numerals and number words), labels and annotations aside."""
    t = figure_text(text)
    return len(re.findall(r"\d+(?:[.,]\d+)*", t)) + len(_NUMBER_WORD_RE.findall(t))


def has_comparative(text: str) -> bool:
    """True when ``text`` contains a comparative or threshold cue."""
    return bool(_COMPARATIVE_RE.search(text))


def has_relation_sign(text: str) -> bool:
    """True when ``text`` states a mathematical relation between two operands (``F = ma``, ``x ≤ 3``)."""
    return bool(_RELATION_RE.search(text))


def _decision(
    cls: EligibilityClass,
    eligible: bool,
    reasons: list[str],
    policy_version: str,
    route_to: Optional[str] = None,
) -> EligibilityDecision:
    return EligibilityDecision(
        eligibility_class=cls,
        eligible=eligible,
        decided_by="deterministic",
        reasons=reasons,
        route_to=None if eligible else route_to,
        policy_version=policy_version,
    )


def _by_kind_first(claim: ClaimRecord, reasons: list[str], pv: str) -> Optional[EligibilityDecision]:
    if claim.proposed_claim_kind == "rubric_judgment":
        reasons.append("proposed kind rubric_judgment: subjective criterion judgement is not a solver question")
        return _decision(EligibilityClass.NOT_ELIGIBLE_RUBRIC_JUDGMENT, False, reasons, pv, "subject_evaluator")
    if claim.proposed_claim_kind == "factual":
        reasons.append("proposed kind factual: truth about the world or the text is checked by evidence, not by the solver")
        return _decision(EligibilityClass.NOT_ELIGIBLE_FACTUAL, False, reasons, pv, "evidence_service")
    return None


def _argument_role(claim: ClaimRecord, reasons: list[str], pv: str) -> EligibilityDecision:
    supports = [s for s in claim.supporting_claim_ids if s != claim.claim_id]
    if len(supports) != len(claim.supporting_claim_ids):
        reasons.append("self-reference in supporting_claim_ids was discarded: a claim cannot support itself")
    if supports:
        reasons.append(
            f"role {claim.claim_role} with {len(supports)} supporting claim(s): "
            "argument structure (evidence -> inference -> point) can be encoded"
        )
        return _decision(EligibilityClass.PROPOSITIONAL_ARGUMENT, True, reasons, pv)
    own = _own_reason(claim, reasons, pv)
    if own is not None:
        return own
    reasons.append("no supporting claims" + (" other than itself" if claim.supporting_claim_ids else ""))
    return _decision(EligibilityClass.NOT_ELIGIBLE_OTHER, False, reasons, pv, "unresolved")


def _own_reason(claim: ClaimRecord, reasons: list[str], pv: str = POLICY_VERSION) -> Optional[EligibilityDecision]:
    """PROPOSITIONAL_ARGUMENT when the claim's own text draws a conclusion from a reason it states (module docstring)."""
    from ..adapters.markdown import states_own_reason
    connective = states_own_reason(claim.claim_text or "")
    if connective is None:
        return None
    reasons.append(f"role {claim.claim_role}: the claim states its own reason ('{connective}' joins a reason and the conclusion drawn from it), "
                   "so it is an argument in one sentence and can be encoded")
    return _decision(EligibilityClass.PROPOSITIONAL_ARGUMENT, True, reasons, pv)


def _count_role(claim: ClaimRecord, reasons: list[str], pv: str) -> EligibilityDecision:
    text = figure_text(claim.claim_text)
    numeral, comparative = has_numeral(text), has_comparative(text)
    relation = False
    if not (numeral or comparative) and resolve_profile(claim.subject).allows(EligibilityClass.QUANTITATIVE_CLAIM):
        numeral = has_numeral(text, scripts=True)
        relation = not numeral and has_relation_sign(text)
    if not (numeral or comparative or relation):
        reasons.append("no numerals or comparatives in claim text" + (" (mark annotations, part labels and named items are not figures)" if text != claim.claim_text else ""))
        return _decision(EligibilityClass.NOT_ELIGIBLE_OTHER, False, reasons, pv, "unresolved")
    if not resolve_profile(claim.subject).allows(EligibilityClass.QUANTITATIVE_CLAIM):
        # a profile with no quantitative claims reads a figured sentence that argues as the argument it is ("Attendance rose in
        # 2020, so the breakfast club caused attendance to rise"), not as a quantity it would refuse (repair round 3, ADV3-01)
        own = _own_reason(claim, reasons, pv)
        if own is not None:
            return own
    cues = ", ".join(c for c, present in (("numerals", numeral), ("comparatives", comparative), ("a mathematical relation sign", relation)) if present)
    reasons.append(f"role {claim.claim_role} with {cues} in the text")
    cls = EligibilityClass.ARITHMETIC_CONSTRAINT if claim.claim_role == "structural" else EligibilityClass.QUANTITATIVE_CLAIM
    return _decision(cls, True, reasons, pv)


def _other_role(claim: ClaimRecord, reasons: list[str], pv: str) -> EligibilityDecision:
    kind = claim.proposed_claim_kind
    if kind == "formal_logic":
        reasons.append("role other with proposed kind formal_logic")
        return _decision(EligibilityClass.PROPOSITIONAL_ARGUMENT, True, reasons, pv)
    if kind == "arithmetic":
        if has_numeral(figure_text(claim.claim_text)) or has_comparative(figure_text(claim.claim_text)):
            reasons.append("role other with proposed kind arithmetic and numeric cues in the text")
            return _decision(EligibilityClass.QUANTITATIVE_CLAIM, True, reasons, pv)
        reasons.append("proposed kind arithmetic but no numerals or comparatives in claim text")
        return _decision(EligibilityClass.NOT_ELIGIBLE_OTHER, False, reasons, pv, "unresolved")
    if kind == "interpretive":
        reasons.append("role other with proposed kind interpretive")
        return _decision(EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE, False, reasons, pv, "subject_evaluator")
    reasons.append("no deterministic rule matched (role other, kind unknown)")
    return _decision(EligibilityClass.NOT_ELIGIBLE_OTHER, False, reasons, pv, "unresolved")


def decide_eligibility(claim: ClaimRecord, policy_version: str = POLICY_VERSION) -> EligibilityDecision:
    """Decide deterministically whether and how ``claim`` may be formalized.

    The agent's ``advisory_verification_eligibility`` is never used; when present it
    is recorded in ``reasons`` as ignored so the audit trail shows it was seen.
    """
    reasons: list[str] = []
    if claim.advisory_verification_eligibility is not None:
        reasons.append(
            f"agent-reported eligibility ({claim.advisory_verification_eligibility}) is advisory and was not used"
        )
    decided = _by_kind_first(claim, reasons, policy_version)
    if decided is not None:
        return decided
    role = claim.claim_role
    if role in ARGUMENT_ROLES:
        return _argument_role(claim, reasons, policy_version)
    if role in COUNT_ROLES:
        return _count_role(claim, reasons, policy_version)
    if role in INTERPRETIVE_ROLES or role in FACTUAL_ROLES:
        own = _own_reason(claim, reasons, policy_version)
        if own is not None:
            return own
    if role in INTERPRETIVE_ROLES:
        reasons.append(f"standalone {role} claim: interpretation, analysis or evaluation is not a solver question")
        return _decision(EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE, False, reasons, policy_version, "subject_evaluator")
    if role in FACTUAL_ROLES:
        if role in ("evidence", "counter_evidence") and (_figure_count(claim.claim_text) >= 2 or has_comparative(figure_text(claim.claim_text))):
            reasons.append(f"{role} with related dates or figures: the stated quantities can be checked for exact consistency; their truth is checked by evidence")
            return _decision(EligibilityClass.QUANTITATIVE_CLAIM, True, reasons, policy_version)
        if role in ("evidence", "counter_evidence") and _figure_count(claim.claim_text) == 1:
            reasons.append(f"{role} with a single date or figure: nothing to check it against but its own statement, so its only encoding would restate it")
        reasons.append(f"{role} claims are checked by deterministic grounding or the evidence service, not by the solver")
        return _decision(EligibilityClass.NOT_ELIGIBLE_FACTUAL, False, reasons, policy_version, "evidence_service")
    return _other_role(claim, reasons, policy_version)
