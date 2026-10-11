"""Deterministic eligibility decisions.

Which claims the solver may be asked about is a POLICY decision made by code, not
by the specialist agent (whose self-reported eligibility is advisory) and not by
the translator model. The rules key on the claim's role, the agent-proposed kind
and simple lexical cues. They are versioned through ``POLICY_VERSION``.

Summary of the rules (applied in this order; the first match decides):

1. kind ``rubric_judgment``       -> NOT_ELIGIBLE_RUBRIC_JUDGMENT, route ``subject_evaluator``
2. kind ``factual``               -> NOT_ELIGIBLE_FACTUAL, route ``evidence_service``
3. role point | thesis | link     -> PROPOSITIONAL_ARGUMENT when supporting claims exist,
                                     else NOT_ELIGIBLE_OTHER ("no supporting claims")
4. role structural | quantitative -> ARITHMETIC_CONSTRAINT | QUANTITATIVE_CLAIM when the
                                     text has numerals or comparatives, else NOT_ELIGIBLE_OTHER
5. role interpretation | effect | device (standalone) -> NOT_ELIGIBLE_INTERPRETIVE, route ``subject_evaluator``
6. role evidence                  -> NOT_ELIGIBLE_FACTUAL, route ``evidence_service`` (grounding checks it)
7. role other: by kind            -> formal_logic: PROPOSITIONAL_ARGUMENT; arithmetic: QUANTITATIVE_CLAIM
                                     (with cues); interpretive: NOT_ELIGIBLE_INTERPRETIVE; unknown: NOT_ELIGIBLE_OTHER
"""
from __future__ import annotations

import re
from typing import Optional

from ..version import POLICY_VERSION
from .contracts import ClaimRecord, EligibilityClass, EligibilityDecision

ARGUMENT_ROLES = frozenset({"point", "thesis", "link"})
COUNT_ROLES = frozenset({"structural", "quantitative"})
INTERPRETIVE_ROLES = frozenset({"interpretation", "effect", "device"})

_NUMERAL_RE = re.compile(r"\d")
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


def has_numeral(text: str) -> bool:
    """True when ``text`` contains a digit or a spelled-out number word."""
    return bool(_NUMERAL_RE.search(text) or _NUMBER_WORD_RE.search(text))


def has_comparative(text: str) -> bool:
    """True when ``text`` contains a comparative or threshold cue."""
    return bool(_COMPARATIVE_RE.search(text))


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
    if claim.supporting_claim_ids:
        reasons.append(
            f"role {claim.claim_role} with {len(claim.supporting_claim_ids)} supporting claim(s): "
            "argument structure (evidence -> inference -> point) can be encoded"
        )
        return _decision(EligibilityClass.PROPOSITIONAL_ARGUMENT, True, reasons, pv)
    reasons.append("no supporting claims")
    return _decision(EligibilityClass.NOT_ELIGIBLE_OTHER, False, reasons, pv, "unresolved")


def _count_role(claim: ClaimRecord, reasons: list[str], pv: str) -> EligibilityDecision:
    numeral, comparative = has_numeral(claim.claim_text), has_comparative(claim.claim_text)
    if not (numeral or comparative):
        reasons.append("no numerals or comparatives in claim text")
        return _decision(EligibilityClass.NOT_ELIGIBLE_OTHER, False, reasons, pv, "unresolved")
    cues = ", ".join(c for c, present in (("numerals", numeral), ("comparatives", comparative)) if present)
    reasons.append(f"role {claim.claim_role} with {cues} in the text")
    cls = EligibilityClass.ARITHMETIC_CONSTRAINT if claim.claim_role == "structural" else EligibilityClass.QUANTITATIVE_CLAIM
    return _decision(cls, True, reasons, pv)


def _other_role(claim: ClaimRecord, reasons: list[str], pv: str) -> EligibilityDecision:
    kind = claim.proposed_claim_kind
    if kind == "formal_logic":
        reasons.append("role other with proposed kind formal_logic")
        return _decision(EligibilityClass.PROPOSITIONAL_ARGUMENT, True, reasons, pv)
    if kind == "arithmetic":
        if has_numeral(claim.claim_text) or has_comparative(claim.claim_text):
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
    if role in INTERPRETIVE_ROLES:
        reasons.append(f"standalone {role} claim: literary interpretation is not a solver question")
        return _decision(EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE, False, reasons, policy_version, "subject_evaluator")
    if role == "evidence":
        reasons.append("evidence claims are checked by deterministic grounding against the supplied text, not by the solver")
        return _decision(EligibilityClass.NOT_ELIGIBLE_FACTUAL, False, reasons, policy_version, "evidence_service")
    return _other_role(claim, reasons, policy_version)
