"""Translator oversight: is every translation of a delivered claim valid IR, grounded, traced to what the specialist
said, not circular, and reported as its signed result has it?

The translator is an agent like any other: a provider PROPOSES an IR problem for each eligible claim
(``translate/pipeline.py``), and that proposal is untrusted data. Every translation crosses the channel inside an outcome
of the receipt of the report that carries its claim (``receipt.outcomes[i].translation``, with the engine result in
``verification``), so the journal already holds, for each one, the delivered claim text, the proposed IR, the
translation's validation outcome (its status, eligibility, grounding checks and diagnostics) and the cited result, which
the store holds signature-verified. This module re-checks them from the JOURNAL, never from live objects, and only by
the four means of trust rule TR1 (here: re-running this repository's deterministic rules on journaled inputs, and
comparing with the signed result the store holds). A translation is data: nothing in it is evaluated or followed.

Checks, per outcome of a DELIVERED report transfer (``response``, ``response_text``, ``relay_report``; a REJECTED transfer
delivered nothing, so its outcomes reached no one, as for the fidelity checks):

* **TRN-001** (error): the proposed IR, taken from the journaled receipt as JSON, fails re-validation as untrusted data:
  ``engine.validator.parse_and_validate`` (strict schema, then identifiers, sorts, the operator allowlist, policy and the
  default limits), its ``request_id`` and ``claim_id`` against the delivered claim, and the sorts the claim's subject
  profile permits (the pipeline's own rules, re-run).
* **TRN-002** (error): the translation's status, eligibility or engine run is not the image of its validation: a problem
  under a status that forbids one (or none under TRANSLATED / AMBIGUOUS_TRANSLATION), an engine result for a translation
  that carries no translated problem, ambiguity flags under TRANSLATED (ambiguity silently resolved), an eligibility
  decision that contradicts the status, for a translation recorded under this code's policy version an eligibility
  decision the deterministic policy does not re-derive from the delivered claim (a claim the policy rules out, forced
  into IR), and a problem with no provider or under another policy version from a translator not declared hand-built.
* **TRN-003** (error): the IR's grounding states more than the deterministic grounding check gives: a ``verified: true``
  on a symbol or assertion, or a grounding check marked verified, that the re-run of the translator's own check
  (``translate.grounding.check_problem_grounding``) against the delivered report's supplied texts does not reproduce.
* **TRN-004** (warning): a quotation grounding's excerpt (any source reference carrying an excerpt) does not occur in the
  supplied text it names, or names a document that is not supplied. The translator's own check reports it unverified
  and the engine result relies on it only as an ungrounded dependency, so the receipt discloses it; the auditor names it.
* **TRN-005** (warning): content of a translation (whoever proposed it) that the specialist's report never states: a quotation
  excerpt in the IR that occurs nowhere in the report (its response, its claims, their source excerpts) and in none of
  the texts supplied with it (rule ``supplied-text``: verbatim text of a supplied document is real text, not invented;
  whether using it is faithful to the claim is the overseer agents' question), or a number in the IR that none of the
  report's texts states in any spelling (task-setting premises may also take their numbers from the request the report
  answers). 0 and 1 are structural and always traced. A warning: a number may be spelled in a way the fixed spelling
  rules below do not read. The narrower question (content outside the claim and the claims it cites, the texts the
  translator was given as the claim; a quotation of a supplied text that none of them quotes counts as outside) is
  recorded per translation (``outside_cited_claims``), not reported: the adapters' citation links are incomplete, so
  it is no evidence of a fault, but it shows a reviewer where the translator went beyond the claim.
* **TRN-006** (error): circular translation: the conclusion's expression occurs verbatim among the premises (as a
  premise, or as a conjunct of one, a conjunction included), so an ENTAILED result rests on the claim assumed, not on the
  specialist's reasoning. Named rule ``grounded-transcription`` (review round 1, recorded r7 rounds): a premise that is
  a verified, traced transcription of a grounded fact (:func:`is_transcription`: a ``task_setting``, ``quotation``,
  ``supplied_text`` or ``arithmetic_fact`` grounding the deterministic check does not refute, and verifies for a
  quotation, whose numbers the texts state) is not the claim assumed: the claim only transcribes that fact, and the
  audit's coverage notes say so; an ``assumption``, a ``specialist_inference`` or an unverified grounding stays an error. (Harness-stage correction: a conclusion that is itself a conjunction, assumed verbatim, was
  missed when only the leaves of a premise's conjunction tree were compared; the tampering suite's T22g on the recorded
  r5 translations found it.)
* Named rule ``restatement-necessity`` (TRN-006 / **TRN-010**, after the recorded round r7): whether the result rests on
  the restatement is decided by the engine, never assumed. The IR with the restating premises removed (every premise in
  which the conclusion occurs and that is no grounded transcription; the rest of the IR unchanged) is run afresh as
  untrusted JSON through the engine's own validator, compiler and procedures (``engine.runner.verify``, default limits,
  the channel's journaled solver configuration with unsat cores) inside :meth:`CheckContext.auditor_run`, so the run is
  signed under the auditor's run key and stored (origin ``auditor_run``; memoised in the store by the reduced problem and
  the configuration). When that signed run is ENTAILED, the conclusion still follows from the other premises: the
  restatement is redundant and is **TRN-010** (a warning naming the premise and citing the run), which fails no
  transfer. Any other outcome is TRN-006 (an error, citing the run when there is one): COUNTEREXAMPLE (the conclusion
  follows only from itself: the result rests on the claim assumed), INCONSISTENT_PREMISES, an undecided status
  (UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, INTERNAL_ERROR), no signed run, or a failure of the run itself:
  uncertainty never resolves toward clearance. A restating premise is removed whole, never rewritten, so a conjunct it
  carries beside the conclusion is removed with it (conservative: an error stays an error when that conjunct was needed).
* **TRN-007** (error): the outcome's ``summary`` is not the deterministic statement (``translate.outcome.build_summary``)
  of the outcome's translation and the signed result the store holds, under any signing configuration the composer
  could have used (no key; the result's verification key with or without its key id). When the store evicted the
  result, the receipt's copy is used if its signature verifies and it is the content the store recorded (its
  tombstone digest); otherwise the check cannot run and the transfer cannot pass (AUDIT-005). The display status itself is
  RES-009, the receipt's copy of the result RES-006, its signature RES-003: one fault, one finding.

* **TRN-008** (warning, contained round c1): a translation displayed with a definitive status (ENTAILED, CONSISTENT) whose
  premises assert supporting claims of the same report (a premise whose id or label names a claim the claim cites)
  while those claims' own outcomes in the same receipt are not successful (COUNTEREXAMPLE, AMBIGUOUS_TRANSLATION, ...;
  a NOT_ELIGIBLE claim was never checked and is not counted): the definitive display rests on claims its own receipt
  does not establish, and the outcome summary's premise labels do not say so (rule ``sibling-status``).
* **TRN-009** (warning, contained round c1): the translations of one receipt encode the same fact inconsistently: one
  asserts it as a premise (a Boolean premise atom), another leaves it an unsupported conjunct of its own claim's
  conclusion (a Boolean conjunct no premise of that problem mentions), the two compared by the symbol meanings and
  premise labels (four content words or more in common, covering three quarters of the shorter: rule
  ``same-fact-premise``). The recorded History rounds asserted a from-memory fact as a premise of one claim and left it
  unsupported in the claim that states it, so the evidence claim was displayed COUNTEREXAMPLE.

What is NOT decided here, and is left to overseer agents (advisory, kind ``other``, human review): whether the IR says
what the claim says (a dropped condition, a flipped comparison or direction, an invented inference, an ambiguity resolved
in words, a claim that needs constructs the IR lacks). No check compares meanings.

**Who proposed it does not gate a check** (contained round c1). The pipeline records the provider
(``translation.provider``) for every proposal it took from a model; it records none only for a claim it ruled
ineligible before any provider call. The eligibility re-derivation runs on every translation recorded under this code's
policy version and the tracing on every translation that carries a problem, whoever proposed it: a removed
``ProviderInfo`` no longer hides a claim forced into IR or an invented number. A translation that carries a problem and
no provider is itself TRN-002 ("model-path translation without provider"), unless its ``translator_version`` is one
the auditor's operator declared hand-built (``TransferAuditor(hand_built_translators=...)``, recorded in every audit's
coverage): a fixture declares itself through configuration, never through a missing field. A problem recorded under a
policy version this code cannot re-derive is TRN-002 too, unless declared hand-built. The audit's translation record
says which checks ran (``checks_run``), so an accusation about a check that did not run is never refuted by it.

Number spelling rules for TRN-005 (fixed; any extension is a named rule with its own test): digits with optional
thousands separators and decimals; ``a/b`` fractions; number words (zero to twenty, the tens, hundred, thousand, dozen,
half, third, quarter, twice, double, triple, both, single, pair, and hyphenated tens-units); a scale word (hundred,
thousand, million, billion) multiplies the number before it; "per cent", "percent" or "%" adds the value divided by 100
and the number 100 itself. Named rules beyond these:

* ``fraction-words``: a numerator (a number word, digits, or "a"/"an" for one) followed by a denominator word (half or
  halves, third(s), quarter(s), fourth(s) to tenth(s), hundredth(s), thousandth(s)), hyphenated or not ("two-thirds",
  "a tenth", "three quarters"), states the fraction, its numerator and its denominator;
* ``month-names``: a capitalised month name or its usual abbreviation ("March", "Sept.") states its number 1 to 12;
* ``percent-as-fraction``: an IR number equal to 100 times a stated number (a stated fraction written as a percentage,
  "a tenth" as 10) is traced, as is a stated percentage written as a fraction (10 per cent as 0.1);
* ``date-encoding``: a whole number written as YYYYMM or YYYYMMDD of a stated year (with a valid month and day) is
  traced, and so are the divisors 100 and 10000 that extract a year or month from such an encoding, in a problem that
  uses one.

STEM readiness (rules for the STEM answers and the STEM translation guidance, which has the translator write every
numeral exactly with no exponent and substitute the stated values):

* ``scientific-notation``: a mantissa times a power of ten (``6.67 × 10⁻¹¹``, ``3.0 x 10^8``, ``1.6 \times 10^{-19}``,
  ``2.5*10**3``) and e-notation (``3.0e8``, ``6.67E-11``) state their exact value; a bare power of ten (``10⁻³``,
  ``10^-3``) states its value. The sign may be ASCII, U+2212 or a dash;
* ``vulgar-fractions``: a fraction character (``½``, ``¾``) states its value, and after a whole number the mixed number
  (``12½`` is 12.5);
* ``si-prefix-units``: a value stated with an SI-prefixed unit symbol (``k``, ``M``, ``G``, ``c``, ``m``, ``µ``, ``n``,
  ``p`` on m, g, s, L, N, J, W, Pa, Hz, V, A, mol, eV, C, Ω; with ``²`` or ``³`` the factor is squared or cubed) states
  its value in the unprefixed unit too (``15 cm`` also 0.15, ``2.5 km`` 2500, ``250 cm³`` 0.00025), and a mass in grams
  or kilograms states it in the other (``500 g`` also 0.5, ``3.2 kg`` 3200). No other conversion is read (minutes to
  seconds, degrees Celsius to kelvin, compound units): a translator that converts on its own is named, as a warning;
* ``stated-precision``: a decimal (``9.8``), or a whole number after ``≈`` or ``~``, states the ends of the interval its
  last digit gives (``9.75`` and ``9.85``; ``≈ 13`` gives ``12.5`` and ``13.5``), the half-unit reading a translator
  may encode for an approximate value. A tolerance stated in words ("within 2%") is not read.

Deviation from ``docs/OVERSEER_DESIGN.md`` (stage ``hook``, founder's requirement of translator oversight): these checks
extend the audit stage's live tier. Like L5 fidelity they run in the asynchronous tier for live transfers (the transfer
is AUDIT_PENDING until they have run) and directly in the batch tier.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterable, Iterator, Optional

from ...engine.results import VerificationResult
from ...engine.runner import verify
from ...engine.statuses import VerificationStatus
from ...engine.validator import parse_and_validate
from ...ir.canonical import canonical_json, problem_digest, sha256_hex
from ...ir.schema import DEFAULT_LIMITS, Problem
from ...translate import subjects
from ...translate.contracts import ClaimRecord, ClaimVerificationOutcome, SpecialistReport, TranslationResult, TranslationStatus
from ...translate.eligibility import decide_eligibility
from ...translate.grounding import check_problem_grounding, locate_quotation
from ...translate.outcome import build_summary, display_status_for
from ...translate.pipeline import apply_subject_policy
from ...version import POLICY_VERSION
from ..contracts import StoredResult
from ..view import REPORT_KINDS, OverseerView, Transfer
from . import CheckContext

__all__ = [
    "TranslationRecord", "translation_records", "check_translations", "circular_premises", "untraced_content", "grounding_faults", "status_faults",
    "sibling_status_faults", "same_fact_inconsistencies",
    "revalidate", "summary_matches", "ir_numbers", "text_numbers", "number_traced", "TRANSLATION_CHECKS", "TRANSLATED_STATUSES", "is_transcription",
    "TRANSCRIPTION_KINDS", "Necessity", "without_premises", "restatement_necessity", "NECESSITY_RULE",
]

#: The checks a translation record may list in ``checks_run``.
TRANSLATION_CHECKS = ("revalidate", "status", "eligibility", "grounding", "trace", "circular", "summary")
#: Translation statuses that carry a problem (and may carry an engine run).
TRANSLATED_STATUSES = frozenset({TranslationStatus.TRANSLATED, TranslationStatus.AMBIGUOUS_TRANSLATION})
_MAX_LISTED = 6


# ============================================================================================ the record
@dataclass(frozen=True)
class TranslationRecord:
    """One translation as the journal holds it: the delivered claim, the claims it cites, the proposed IR, the
    translation's own validation outcome, the auditor's re-validation, and the signed result the store holds."""
    seq: int
    message_id: Optional[str]
    receipt_id: Optional[str]
    report_id: str
    agent_id: str
    claim_id: str
    outcome_index: int
    claim_text: str
    cited_claims: tuple[tuple[str, str], ...]
    translation: TranslationResult
    problem_json: Optional[str]
    model_proposed: bool
    revalidation: str
    revalidation_detail: tuple[str, ...]
    result_id: Optional[str]
    result_status: Optional[str]
    signature_verified: Optional[bool]
    display_status: str
    result_sha256: Optional[str] = None
    checks_run: tuple[str, ...] = field(default_factory=tuple)
    outside_cited_claims: tuple[str, ...] = field(default_factory=tuple)

    @property
    def problem_digest(self) -> Optional[str]:
        p = self.translation.problem
        return problem_digest(p) if p is not None else None


# ============================================================================================ helpers
def _outcomes(t: Transfer) -> Iterator[tuple[int, ClaimVerificationOutcome, dict, ClaimRecord]]:
    """``(index, outcome, outcome dump, delivered claim)`` for every outcome of a delivered report transfer whose claim is
    in the delivered report (an outcome naming no delivered claim is RES-010's)."""
    if t.kind not in REPORT_KINDS or not t.delivered or t.digest_only or t.receipt is None or t.report is None:
        return
    claims = {c.claim_id: c for c in t.report.claims}
    dumps = (t.receipt_dump or {}).get("outcomes") or []
    for i, o in enumerate(t.receipt.outcomes):
        c = claims.get(o.claim_id)
        if c is None:
            continue
        dump = dumps[i] if i < len(dumps) and isinstance(dumps[i], dict) else {}
        yield i, o, dump, c


def _cited_claims(claim: ClaimRecord, report: SpecialistReport) -> list[ClaimRecord]:
    """The claims ``claim`` cites that the report carries: what the translator was given beside the claim."""
    wanted = [s for s in dict.fromkeys(claim.supporting_claim_ids) if s != claim.claim_id]
    by_id = {c.claim_id: c for c in report.claims}
    return [by_id[s] for s in wanted if s in by_id]


def _model_proposed(tr: TranslationResult) -> bool:
    return tr.provider is not None


def _problem_json(dump: dict, tr: Optional[TranslationResult] = None) -> Optional[str]:
    """The proposed IR as journaled (the receipt's JSON), or the parsed translation's problem when the dump lacks it."""
    prob = ((dump.get("translation") or {}) if isinstance(dump, dict) else {}).get("problem")
    if isinstance(prob, dict):
        return canonical_json(prob)
    if tr is not None and tr.problem is not None:
        return canonical_json(tr.problem.model_dump(mode="json", exclude_none=True))
    return None


def _listed(items: list[str]) -> str:
    shown = items[:_MAX_LISTED]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


# ============================================================================================ TRN-001
def revalidate(problem_json: Optional[str], claim: ClaimRecord) -> tuple[str, list[str]]:
    """``("valid" | "invalid" | "no_problem", reasons)``: the journaled IR re-validated as untrusted JSON with the engine's
    parser and validator (default limits), its ids against the claim, and the subject profile's sorts."""
    if problem_json is None:
        return "no_problem", []
    problem, outcome = parse_and_validate(problem_json)
    why = [f"{d.code}: {d.message[:160]}" + (f" at {d.path}" if d.path else "") for d in outcome.diagnostics]
    if problem is not None:
        if problem.request_id != claim.request_id or problem.claim_id != claim.claim_id:
            why.append(f"the problem names request {problem.request_id!r} and claim {problem.claim_id!r}, not the delivered claim's")
        profile = subjects.resolve_profile(claim.subject)
        bad = sorted({s.sort for s in problem.symbols if s.sort != "Bool" and s.sort not in profile.numeric_sorts})
        if bad:
            why.append(f"sort(s) {', '.join(bad)} are not permitted by subject profile {profile.key}")
    return ("invalid" if why or problem is None else "valid"), why


# ============================================================================================ TRN-002
def status_faults(o: ClaimVerificationOutcome, claim: ClaimRecord, *, model_proposed: Optional[bool] = None,
                  hand_built: bool = False) -> tuple[list[str], bool]:
    """``(faults, eligibility re-derived)``: where the translation's status, eligibility or engine run is not the image of
    its validation. The eligibility policy is deterministic and does not depend on who proposed the IR, so it is
    re-derived for EVERY translation recorded under this code's policy version (``model_proposed`` is accepted for
    callers of the earlier signature and no longer gates anything; contained round c1: a provider removed from a
    translation skipped the re-derivation). A translation that carries a problem but records no provider is a fault
    unless its translator was declared hand-built (``hand_built``): the pipeline records a provider for every proposal it
    took from a model and none only for a claim it ruled ineligible before any provider call; so is one carrying a
    problem under another policy version, whose eligibility this code cannot re-derive."""
    tr = o.translation
    why: list[str] = []
    translated = tr.status in TRANSLATED_STATUSES
    if translated and tr.problem is None:
        why.append(f"status {tr.status.value} carries no problem")
    if not translated and tr.problem is not None:
        why.append(f"status {tr.status.value} carries a problem (only TRANSLATED and AMBIGUOUS_TRANSLATION do)")
    if o.verification is not None and (not translated or tr.problem is None):
        why.append(f"an engine result is attached to a translation with status {tr.status.value} and {'a' if tr.problem is not None else 'no'} problem")
    flags = tr.interpretation.ambiguity_flags if tr.interpretation is not None else []
    if tr.status is TranslationStatus.TRANSLATED and flags:
        why.append(f"status TRANSLATED although the interpretation lists {len(flags)} ambiguity flag(s) ({', '.join(f.code for f in flags[:4])}): "
                   "the ambiguity was resolved silently")
    e = tr.eligibility
    if not e.eligible and tr.status is not TranslationStatus.NOT_ELIGIBLE:
        why.append(f"the eligibility decision says not eligible ({e.eligibility_class.value}) but the status is {tr.status.value}")
    if e.eligible and tr.status is TranslationStatus.NOT_ELIGIBLE:
        why.append(f"the status is NOT_ELIGIBLE but the eligibility decision says eligible ({e.eligibility_class.value})")
    if tr.problem is not None and tr.provider is None and not hand_built:
        why.append(f"model-path translation without provider: it carries a problem but records no provider, and its translator "
                   f"({tr.translator_version!r}) is not declared hand-built (the pipeline records a provider for every proposal it took from a model)")
    rederived = False
    if tr.policy_version == POLICY_VERSION and e.policy_version == POLICY_VERSION:
        rederived = True
        again = apply_subject_policy(decide_eligibility(claim, POLICY_VERSION), subjects.resolve_profile(claim.subject))
        if (again.eligibility_class, again.eligible) != (e.eligibility_class, e.eligible):
            what = (f"the eligibility policy re-derives {again.eligibility_class.value} ({'eligible' if again.eligible else 'not eligible'}) "
                    f"from the delivered claim; the translation records {e.eligibility_class.value} ({'eligible' if e.eligible else 'not eligible'})")
            if not again.eligible and tr.problem is not None:
                what += ": a claim the policy rules out was forced into IR"
            why.append(what)
    elif tr.problem is not None and not hand_built:
        why.append(f"the translation carries a problem under policy version {tr.policy_version!r} (eligibility {e.policy_version!r}), not this code's "
                   f"{POLICY_VERSION!r}: its eligibility cannot be re-derived")
    return why, rederived


# ============================================================================================ TRN-003 / TRN-004
def _targets(problem: Problem) -> Iterator[tuple[tuple[str, str], str, Any]]:
    """``((part, name), name, grounding)`` of every symbol and assertion: symbols and assertions may share a name."""
    for s in problem.symbols:
        yield ("symbol", s.name), s.name, s.grounding
    for p in problem.premises:
        yield ("assertion", p.id), p.id, p.grounding
    if problem.conclusion is not None:
        yield ("assertion", problem.conclusion.id), problem.conclusion.id, problem.conclusion.grounding


def grounding_faults(tr: TranslationResult, report: SpecialistReport) -> tuple[list[str], list[tuple[str, Optional[str], str]]]:
    """``(overstated, absent)``. ``overstated``: verifications the re-run of the grounding check does not reproduce
    (TRN-003). ``absent``: ``(target, document id, detail)`` for every excerpt the re-run does not find in the document it
    names (TRN-004)."""
    problem = tr.problem
    if problem is None:
        return [], []
    rerun, checks = check_problem_grounding(problem, list(report.supplied_texts))
    again = {key: g for key, _name, g in _targets(rerun)}
    overstated: list[str] = []
    for key, name, g in _targets(problem):
        if g is not None and g.verified is True and (again.get(key) is None or again[key].verified is not True):
            overstated.append(f"{name} is marked verified, the grounding check gives {again[key].verified if again.get(key) is not None else None}")
    verified_again = {(c.target_id, c.document_id) for c in checks if c.verified is True}
    for c in tr.grounding_checks:
        if c.verified is True and (c.target_id, c.document_id) not in verified_again:
            overstated.append(f"the grounding check of {c.target_id} against {c.document_id!r} is recorded as verified; the re-run does not verify it")
    absent = [(c.target_id, c.document_id, c.detail or c.method) for c in checks if c.verified is False]
    return list(dict.fromkeys(overstated)), absent


# ============================================================================================ TRN-005
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?:\s*/\s*(\d+))?")
_SCALES = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
          "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_OTHER_WORDS = {"hundred": 100, "thousand": 1000, "dozen": 12, "half": Fraction(1, 2), "third": Fraction(1, 3), "quarter": Fraction(1, 4),
                "twice": 2, "double": 2, "triple": 3, "both": 2, "single": 1, "pair": 2, "million": 10 ** 6, "billion": 10 ** 9}
_WORD_RE = re.compile(r"\b(" + "|".join(sorted(set(_TENS) | set(_UNITS) | set(_OTHER_WORDS), key=len, reverse=True))
                      + r")(?:-(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r"))?\b", re.IGNORECASE)
_SCALE_AFTER_RE = re.compile(r"^\s+(hundred|thousand|million|billion)\b", re.IGNORECASE)
_PERCENT_RE = re.compile(r"(per\s*cent|percent|%)", re.IGNORECASE)
# fraction-words: a numerator (word, digits, a/an) and a denominator word, hyphenated or spaced
_DENOMINATORS = {"half": 2, "halves": 2, "third": 3, "thirds": 3, "quarter": 4, "quarters": 4, "fourth": 4, "fourths": 4, "fifth": 5, "fifths": 5,
                 "sixth": 6, "sixths": 6, "seventh": 7, "sevenths": 7, "eighth": 8, "eighths": 8, "ninth": 9, "ninths": 9, "tenth": 10, "tenths": 10,
                 "hundredth": 100, "hundredths": 100, "thousandth": 1000, "thousandths": 1000}
_FRACTION_RE = re.compile(r"\b(an?|\d+|" + "|".join(sorted(set(_TENS) | set(_UNITS), key=len, reverse=True)) + r")[\s-]+("
                          + "|".join(sorted(_DENOMINATORS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
# month-names: capitalised month names and their usual abbreviations
_MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6, "July": 7, "August": 8, "September": 9, "October": 10,
           "November": 11, "December": 12, "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10,
           "Nov": 11, "Dec": 12}
_MONTH_RE = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b")
#: date-encoding: the divisors that extract a year (YYYYMMDD // 10000, YYYYMM // 100) or a month from an encoded date.
DATE_DIVISORS = frozenset({Fraction(100), Fraction(10000)})
# scientific-notation (STEM answers; the STEM translation guidance tells the translator to expand it exactly): a mantissa
# times a power of ten, written with x, ×, ·, *, \times or \cdot and the exponent as ^E, ^{E}, **E or superscript digits,
# or as e-notation (3.0e8, 6.67E-11); and a bare power of ten (10⁻³, 10^-3). The sign may be ASCII, U+2212 or a dash.
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_EXP = r"(?:\^\s*\{?\s*([-+−–]?\s*\d{1,3})\s*\}?|\*\*\s*\(?\s*([-+−–]?\s*\d{1,3})\s*\)?|([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,3}))"
_SCI_TIMES_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:[×xX·*]|\\times|\\cdot)\s*10\s*" + _EXP)
_SCI_E_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[eE]\s?([-+−]?\d{1,3})(?![\w.])")
_POW10_RE = re.compile(r"(?<![\w.])10\s*" + _EXP)
#: vulgar-fractions: a fraction character (½, ¾, ...) alone or after a whole number ("12½" is 12.5).
_VULGAR = {"½": Fraction(1, 2), "⅓": Fraction(1, 3), "⅔": Fraction(2, 3), "¼": Fraction(1, 4), "¾": Fraction(3, 4), "⅕": Fraction(1, 5), "⅖": Fraction(2, 5),
           "⅗": Fraction(3, 5), "⅘": Fraction(4, 5), "⅙": Fraction(1, 6), "⅚": Fraction(5, 6), "⅛": Fraction(1, 8), "⅜": Fraction(3, 8), "⅝": Fraction(5, 8),
           "⅞": Fraction(7, 8)}
_VULGAR_RE = re.compile(r"(?:(?<![\w.])(\d+))?([" + "".join(_VULGAR) + r"])")
#: si-prefix-units: SI prefixes and the unit symbols they are read on (a value is also stated in the unprefixed unit).
_SI_PREFIXES = {"k": Fraction(10 ** 3), "M": Fraction(10 ** 6), "G": Fraction(10 ** 9), "c": Fraction(1, 10 ** 2), "m": Fraction(1, 10 ** 3),
                "µ": Fraction(1, 10 ** 6), "μ": Fraction(1, 10 ** 6), "n": Fraction(1, 10 ** 9), "p": Fraction(1, 10 ** 12)}
_SI_UNITS = ("mol", "Pa", "Hz", "eV", "m", "g", "s", "L", "N", "J", "W", "V", "A", "C", "Ω")
_SI_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(" + "|".join(re.escape(p) for p in _SI_PREFIXES) + r")?("
                         + "|".join(re.escape(u) for u in _SI_UNITS) + r")([²³])?(?![A-Za-zΩ])")
#: stated-precision: a decimal, or a whole number after an approximation sign.
_DECIMAL_STATED_RE = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?![\d])")
_APPROX_WHOLE_RE = re.compile(r"[≈~]\s*(\d+)(?![\d.,])")


def _exponent(*groups: Optional[str]) -> Optional[int]:
    for g in groups:
        if g:
            t = g.translate(_SUPERSCRIPTS).replace("−", "-").replace("–", "-").replace(" ", "")
            try:
                e = int(t)
            except ValueError:
                return None
            return e if abs(e) <= 400 else None
    return None


def _scientific_numbers(text: str) -> set[Fraction]:
    """Named rule ``scientific-notation``: every value a text states in scientific notation (and every bare power of
    ten), exactly; and rule ``vulgar-fractions``."""
    out: set[Fraction] = set()
    for m in _SCI_TIMES_RE.finditer(text):
        e = _exponent(m.group(2), m.group(3), m.group(4))
        if e is not None:
            out.add(Fraction(m.group(1)) * Fraction(10) ** e)
    for m in _SCI_E_RE.finditer(text):
        e = _exponent(m.group(2))
        if e is not None:
            out.add(Fraction(m.group(1)) * Fraction(10) ** e)
    for m in _POW10_RE.finditer(text):
        e = _exponent(m.group(1), m.group(2), m.group(3))
        if e is not None:
            out.add(Fraction(10) ** e)
    for m in _VULGAR_RE.finditer(text):
        frac = _VULGAR[m.group(2)]
        out.add(frac)
        if m.group(1):
            out.add(Fraction(int(m.group(1))) + frac)
    return out


def _unit_numbers(text: str) -> set[Fraction]:
    """Named rule ``si-prefix-units`` (module docstring): a value with an SI-prefixed unit symbol in the unprefixed unit,
    and a mass in grams or kilograms in the other."""
    out: set[Fraction] = set()
    for m in _SI_UNIT_RE.finditer(text):
        value, prefix, unit, power = Fraction(m.group(1)), m.group(2), m.group(3), m.group(4)
        exp = 2 if power == "²" else 3 if power == "³" else 1
        if prefix:
            out.add(value * _SI_PREFIXES[prefix] ** exp)
            if unit == "g" and prefix != "k":
                out.add(value * _SI_PREFIXES[prefix] / 1000)  # milligrams, micrograms ... in kilograms
        if unit == "g" and exp == 1:
            out.add(value * 1000 if prefix == "k" else value / 1000 if not prefix else value)
    return out


def _precision_numbers(text: str) -> set[Fraction]:
    """Named rule ``stated-precision`` (module docstring): the ends of the interval a stated decimal's last digit gives,
    and of a whole number after ``≈`` or ``~``."""
    out: set[Fraction] = set()
    for m in _DECIMAL_STATED_RE.finditer(text):
        value = Fraction(f"{m.group(1)}.{m.group(2)}")
        half = Fraction(1, 2 * 10 ** len(m.group(2)))
        out.update({value - half, value + half})
    for m in _APPROX_WHOLE_RE.finditer(text):
        value = Fraction(int(m.group(1)))
        out.update({value - Fraction(1, 2), value + Fraction(1, 2)})
    return out


def _fraction_words(text: str) -> set[Fraction]:
    out: set[Fraction] = set()
    for m in _FRACTION_RE.finditer(text):
        num_word, den_word = m.group(1).lower(), m.group(2).lower()
        if num_word in ("a", "an"):
            num = 1
        elif num_word.isdigit():
            num = int(num_word)
        else:
            num = _TENS.get(num_word, _UNITS.get(num_word))
            if num is None:
                continue
        den = _DENOMINATORS[den_word]
        out.update({Fraction(num, den), Fraction(num), Fraction(den)})
    return out


def text_numbers(text: str) -> set[Fraction]:
    """Every number ``text`` states under the fixed spelling rules (module docstring)."""
    out: set[Fraction] = set()
    if text:
        out |= _fraction_words(text)
        out.update(Fraction(_MONTHS[m.group(1)]) for m in _MONTH_RE.finditer(text))
        out |= _scientific_numbers(text)
        out |= _unit_numbers(text)
        out |= _precision_numbers(text)
    for m in _NUM_RE.finditer(text or ""):
        whole, dec, denom = m.group(1).replace(",", ""), m.group(2), m.group(3)
        value = Fraction(int(whole)) + (Fraction(int(dec), 10 ** len(dec)) if dec else 0)
        out.add(value)
        if denom and int(denom) != 0 and not dec:
            out.add(Fraction(int(whole), int(denom)))
            out.add(Fraction(int(denom)))
        tail = text[m.end():]
        sc = _SCALE_AFTER_RE.match(tail)
        if sc:
            out.add(value * _SCALES[sc.group(1).lower()])
        if _PERCENT_RE.match(tail.lstrip()[:8]) or tail.startswith("%"):
            out.add(value / 100)
    for m in _WORD_RE.finditer(text or ""):
        w, unit = m.group(1).lower(), (m.group(2) or "").lower()
        base = _TENS.get(w, _UNITS.get(w, _OTHER_WORDS.get(w)))
        if base is None:
            continue
        value = Fraction(base) + (Fraction(_UNITS[unit]) if unit and w in _TENS else 0)
        out.add(value)
        sc = _SCALE_AFTER_RE.match(text[m.end():])
        if sc:
            out.add(value * _SCALES[sc.group(1).lower()])
    if _PERCENT_RE.search(text or ""):
        out.add(Fraction(100))
    return out


def ir_numbers(expr: Any) -> list[Fraction]:
    """The numeric constants of an expression (JSON), in first-seen order, iteratively."""
    out: list[Fraction] = []
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("op") in ("int", "real") and isinstance(node.get("value"), str):
                try:
                    v = Fraction(node["value"])
                except (ValueError, ZeroDivisionError):
                    continue
                if v not in out:
                    out.append(v)
                continue
            stack.extend(reversed([v for k, v in node.items() if k != "value"]))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return out


def _date_encoding(v: Fraction, known: set[Fraction]) -> bool:
    """Named rule ``date-encoding``: a whole number written as YYYYMM or YYYYMMDD (a month or a day of a stated year, as
    translators encode dates for ordering) is traced when its year is stated and its month and day are valid."""
    if v.denominator != 1 or v < 0:
        return False
    digits = str(v.numerator)
    if len(digits) not in (6, 8):
        return False
    year, month = int(digits[:4]), int(digits[4:6])
    day = int(digits[6:8]) if len(digits) == 8 else 1
    return 1000 <= year <= 2999 and 1 <= month <= 12 and 1 <= day <= 31 and Fraction(year) in known


def number_traced(value: Fraction, known: set[Fraction], *, date_encoded: bool = False) -> bool:
    """Whether ``value`` is stated by the texts whose numbers are ``known``: 0 and 1 always; the value itself; a stated
    percentage written as a fraction or a stated fraction written as a percentage (``percent-as-fraction``); a date
    encoding of a stated year, and, in a problem that uses one (``date_encoded``), the divisors 100 and 10000
    (``date-encoding``)."""
    v = abs(value)
    return (v in (0, 1) or v in known or v * 100 in known or v / 100 in known or _date_encoding(v, known)
            or (date_encoded and v in DATE_DIVISORS))


def _excerpts(grounding: Any) -> list[str]:
    if grounding is None:
        return []
    return [r.excerpt for r in grounding.source_refs if r.excerpt and r.excerpt.strip()]


def _assertion_numbers(problem_obj: Optional[dict]) -> Iterator[tuple[str, Optional[str], Fraction]]:
    """``(assertion id, grounding kind, number)`` for every number of every premise and of the conclusion."""
    assertions = list((problem_obj or {}).get("premises") or [])
    if isinstance((problem_obj or {}).get("conclusion"), dict):
        assertions.append(problem_obj["conclusion"])
    for a in assertions:
        if not isinstance(a, dict):
            continue
        kind = (a.get("grounding") or {}).get("kind") if isinstance(a.get("grounding"), dict) else None
        for v in ir_numbers(a.get("expr")):
            yield str(a.get("id")), kind, v


def untraced_content(problem: Problem, problem_obj: Optional[dict], scope_texts: list[str], request_texts: list[str],
                     supplied_texts: Iterable[str] = ()) -> list[tuple[str, str]]:
    """``(target, description)`` for each quotation excerpt and number of the IR that ``scope_texts`` never state (a
    quotation may also come verbatim from ``supplied_texts``, rule ``supplied-text``; a task-setting premise may also take
    its numbers from ``request_texts``)."""
    texts = [t for t in scope_texts if t]
    quotable = texts + [t for t in supplied_texts if t]
    out: list[tuple[str, str]] = []
    for _key, name, g in _targets(problem):
        for ex in _excerpts(g):
            if not any(locate_quotation(ex, text) is not None for text in quotable):
                out.append((name, f"{name} quotes {ex[:80]!r}"))
    known = set().union(*(text_numbers(t) for t in texts)) if texts else set()
    task_known = set().union(*(text_numbers(t) for t in request_texts if t)) if request_texts else set()
    numbers = list(_assertion_numbers(problem_obj))
    date_encoded = any(_date_encoding(abs(v), known | (task_known if kind == "task_setting" else set())) for _a, kind, v in numbers)
    for aid, kind, v in numbers:
        if not number_traced(v, known | task_known if kind == "task_setting" else known, date_encoded=date_encoded):
            out.append((aid, f"{aid} uses the number {v}"))
    return list(dict.fromkeys(out))


def report_scope(report: SpecialistReport) -> list[str]:
    """What the specialist said: its original response, every delivered claim and every source excerpt it gives."""
    return [report.original_response] + [c.claim_text for c in report.claims] + [r.excerpt for c in report.claims for r in c.source_refs if r.excerpt]


def cited_scope(claim: ClaimRecord, cited: list[ClaimRecord]) -> list[str]:
    """The claim and the claims it cites, with their source excerpts: what the translator was given as the claim."""
    return [claim.claim_text] + [c.claim_text for c in cited] + [r.excerpt for c in [claim, *cited] for r in c.source_refs if r.excerpt]


# ============================================================================================ TRN-006
def _conjuncts(expr: Any) -> list[Any]:
    """Every node of ``expr``'s conjunction tree: the expression itself, each ``and`` node inside it and each conjunct.
    (A conclusion that is itself a conjunction, assumed verbatim as a premise or as a conjunct of one, is circular too:
    the harness's tampering suite found that comparing only the leaves missed it.)"""
    out, stack = [], [expr]
    while stack:
        node = stack.pop()
        out.append(node)
        if isinstance(node, dict) and node.get("op") == "and" and isinstance(node.get("args"), list):
            stack.extend(reversed(node["args"]))
    return out


def circular_premises(problem_obj: Optional[dict]) -> list[str]:
    """The ids of the premises in which the conclusion's expression occurs verbatim (the premise itself or one of its
    conjuncts). Compared as canonical JSON."""
    if not isinstance(problem_obj, dict) or not isinstance(problem_obj.get("conclusion"), dict):
        return []
    target = canonical_json(problem_obj["conclusion"].get("expr"))
    out = []
    for p in problem_obj.get("premises") or []:
        if isinstance(p, dict) and any(canonical_json(x) == target for x in _conjuncts(p.get("expr"))):
            out.append(str(p.get("id")))
    return out


#: Grounding kinds a premise may transcribe the conclusion from without being circular, once verified and traced.
TRANSCRIPTION_KINDS = frozenset({"task_setting", "quotation", "supplied_text", "arithmetic_fact"})


def is_transcription(premise_id: str, problem: Optional[Problem], problem_obj: Optional[dict], report: SpecialistReport, request_texts: list[str]) -> bool:
    """Rule ``grounded-transcription`` for TRN-006: a premise identical to the conclusion is a transcription of a grounded
    fact, not the claim assumed, when its grounding kind is ``task_setting``, ``quotation``, ``supplied_text`` or
    ``arithmetic_fact``; the deterministic grounding check re-run on the report's supplied texts does not refute it (and
    verifies it, for a quotation or supplied text); and every number in it is stated by the report's texts (a task-setting
    premise also by the request's). An ``assumption``, a ``specialist_inference`` or an unverified grounding stays circular."""
    if problem is None or not isinstance(problem_obj, dict):
        return False
    prem = next((p for p in problem_obj.get("premises") or [] if isinstance(p, dict) and str(p.get("id")) == premise_id), None)
    g = prem.get("grounding") if isinstance(prem, dict) else None
    kind = g.get("kind") if isinstance(g, dict) else None
    if kind not in TRANSCRIPTION_KINDS:
        return False
    rerun, _checks = check_problem_grounding(problem, list(report.supplied_texts))
    again = next((p.grounding for p in rerun.premises if p.id == premise_id), None)
    verified = again.verified if again is not None else None
    if verified is False or (kind in ("quotation", "supplied_text") and verified is not True):
        return False
    known = set().union(*(text_numbers(x) for x in report_scope(report) if x)) if report_scope(report) else set()
    if kind == "task_setting":
        known |= set().union(*(text_numbers(x) for x in request_texts if x)) if request_texts else set()
    return all(number_traced(v, known) for v in ir_numbers(prem.get("expr")))


#: The rule that decides, by the auditor's own signed engine run, whether a restating premise is load-bearing.
NECESSITY_RULE = "restatement-necessity"
#: Diagnostics an ENTAILED run may carry and still count as the conclusion following: only the engine's trust note on
#: an untrusted payload (E505, a ``verified`` flag discarded). Any other (E108 vacuous: no premise was used, a verdict the
#: engine never displays; and every diagnostic a later engine adds to withhold a verdict) keeps the translation circular.
NECESSITY_BENIGN_DIAGNOSTICS = frozenset({"E505"})


@dataclass(frozen=True)
class Necessity:
    """The auditor's signed engine run on a translation's IR with its restating premises removed (rule
    ``restatement-necessity``). ``status`` is the signed run's status (None when no signed run exists); ``reason`` says
    why there is none. :attr:`follows` (the signed run is ENTAILED, with no diagnostic that withholds the verdict) makes
    the restatement redundant (TRN-010); anything else keeps the translation circular (TRN-006): uncertainty never
    resolves toward clearance."""
    removed: tuple[str, ...]
    status: Optional[str] = None
    result_id: Optional[str] = None
    relied_on: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    reason: str = ""

    @property
    def follows(self) -> bool:
        return (self.result_id is not None and self.status == VerificationStatus.ENTAILED.value
                and all(c in NECESSITY_BENIGN_DIAGNOSTICS for c in self.diagnostics))

    def describe(self) -> str:
        if self.result_id is None:
            return f"could not be decided ({self.reason or 'no signed run'})"
        if self.follows:
            return "still gives ENTAILED" + (f", relying on {', '.join(self.relied_on[:8])}" if self.relied_on else "")
        if self.status == VerificationStatus.ENTAILED.value:
            return f"gives ENTAILED with {', '.join(self.diagnostics)}, a verdict the engine withholds ({self.reason})"
        if self.status == VerificationStatus.COUNTEREXAMPLE.value:
            return "gives COUNTEREXAMPLE: the conclusion follows only from the premise(s) restating it"
        if self.status == VerificationStatus.INCONSISTENT_PREMISES.value:
            return "gives INCONSISTENT_PREMISES: no entailment is established without the restatement"
        return f"could not be decided ({self.status}{': ' + self.reason if self.reason else ''})"


def without_premises(problem_obj: dict, premise_ids: Iterable[str]) -> dict:
    """The IR ``problem_obj`` with the premises ``premise_ids`` removed, everything else unchanged (a deep copy through
    JSON: data, never evaluated)."""
    drop = set(premise_ids)
    out = json.loads(json.dumps(problem_obj))
    out["premises"] = [p for p in (out.get("premises") or []) if not (isinstance(p, dict) and str(p.get("id")) in drop)]
    return out


def _engine_verify(raw: str, config: Any) -> VerificationResult:
    """One engine run of an untrusted IR text: the engine's own validator (default limits), compiler and procedures."""
    return verify(raw, config, DEFAULT_LIMITS)


def restatement_necessity(ctx: CheckContext, t: Transfer, problem_obj: Optional[dict], removed: list[str]) -> Necessity:
    """Rule ``restatement-necessity``: the auditor's own engine run on ``problem_obj`` with the premises ``removed``
    (those restating the conclusion), as untrusted JSON through the engine's validator, compiler and procedures, under the
    channel's journaled solver configuration with unsat cores, signed under the auditor's run key and stored
    (:meth:`CheckContext.auditor_run`). Memoised in the store by the reduced problem and the configuration, so every audit
    of the channel cites the same run. Never raises: a failure is a Necessity with no signed run (TRN-006 stands)."""
    gone = tuple(dict.fromkeys(removed))
    if not isinstance(problem_obj, dict) or not gone:
        return Necessity(removed=gone, reason="no problem to re-run")
    try:
        raw = canonical_json(without_premises(problem_obj, gone))
        cfg = ctx.view.config_at(t.seq).model_copy(update={"produce_unsat_core": True})
        memo_key = "N6|" + sha256_hex(canonical_json([sha256_hex(raw), cfg.model_dump(mode="json")]))
    except Exception as exc:
        return Necessity(removed=gone, reason=f"the problem without the restating premise(s) could not be built ({type(exc).__name__})")
    memo = ctx.store.memo_get(memo_key)
    if memo is None:
        try:
            _out, run_ids = ctx.auditor_run(lambda: _engine_verify(raw, cfg), seq=t.seq)
        except Exception as exc:
            return Necessity(removed=gone, reason=f"the engine run failed ({type(exc).__name__})")
        rec = ctx.store.get(run_ids[-1]) if len(run_ids) == 1 else None
        signed = ctx.store.parsed(run_ids[-1]) if rec is not None else None
        if rec is None or signed is None or getattr(rec, "origin", None) != "auditor_run" or not getattr(rec, "signature_ok_at_put", False):
            reason = "no signed auditor run was stored" if len(run_ids) != 1 else "the auditor run is not held signed in the store"
            return Necessity(removed=gone, reason=reason)
        memo = {"result_id": signed.result_id, "status": signed.status.value, "relied_on": list(signed.premises_relied_on),
                "diagnostics": list(dict.fromkeys(d.code for d in signed.diagnostics)), "run_ids": list(run_ids),
                "reason": "; ".join(f"{d.code}: {d.message[:120]}" for d in signed.diagnostics if d.code not in NECESSITY_BENIGN_DIAGNOSTICS)[:400]}
        ctx.store.memo_put(memo_key, memo)
    else:
        for rid in memo.get("run_ids", []):
            if rid not in ctx.auditor_result_ids:
                ctx.auditor_result_ids.append(rid)
    return Necessity(removed=gone, status=memo["status"], result_id=memo["result_id"], relied_on=tuple(memo["relied_on"]),
                     diagnostics=tuple(memo["diagnostics"]), reason=memo.get("reason", ""))


# ============================================================================================ TRN-007
def summary_matches(o: ClaimVerificationOutcome, claim: ClaimRecord, verification: Optional[VerificationResult], keyring: Any) -> bool:
    """Whether the outcome's summary is ``build_summary`` of its translation and ``verification`` (the stored signed
    result) under some signing configuration the composer could have used."""
    tr = o.translation
    options: list[tuple[Optional[bytes], Optional[str]]] = [(None, None)]
    kid = verification.signature_key_id if verification is not None else None
    key = keyring.verification_key(kid) if kid else None
    if key:
        options += [(key, None), (key, kid)]
    for k, k_id in options:
        try:
            display = display_status_for(tr, verification, k, k_id)
            if build_summary(claim, tr, verification, o.semantic_review, list(o.structural_findings), display, k, k_id) == o.summary:
                return True
        except Exception:
            continue
    return False


# ============================================================================================ TRN-008 / TRN-009
#: Display statuses that state a definitive success, and the one that means "never checked".
_DEFINITIVE = frozenset({"ENTAILED", "CONSISTENT"})
_UNCHECKED_DISPLAY = frozenset({"NOT_ELIGIBLE"})
_ALNUM = "a-z0-9"


def _id_forms(claim_id: str) -> list[str]:
    """The spellings of a claim id a premise id or label may carry ("p2-point" -> "p2_point", "h1.6" -> "h1_6", "h16").
    Every id scheme the parsers use is read: the English and History ids above, the generic parser's ``g4.2`` and its
    agent-qualified ``g4.2@economics-specialist`` (an IR identifier cannot carry ``@``, so the id before it is spelled), and
    the STEM parsers' ``s1.2``, ``m1.2``, ``c1.2`` and ``s.tail`` (rule ``claim-id-schemes``)."""
    out: list[str] = []
    for c in dict.fromkeys([claim_id.casefold(), claim_id.casefold().split("@", 1)[0]]):
        out += [c, c.replace("-", "_"), c.replace(".", "_"), c.replace("-", "").replace(".", ""), c.replace(".", "")]
    return [f for f in dict.fromkeys(out) if f]


def _names_claim(text: str, claim_id: str) -> bool:
    t = (text or "").casefold()
    return any(re.search(rf"(?<![{_ALNUM}]){re.escape(f)}(?![{_ALNUM}])", t) for f in _id_forms(claim_id) if len(f) >= 2)


def sibling_status_faults(outcomes: list[tuple[ClaimVerificationOutcome, ClaimRecord]]) -> list[tuple[str, list[tuple[str, str]]]]:
    """Rule ``sibling-status`` (TRN-008): ``(claim id, [(supporting claim id, its display status)])`` for each outcome
    displayed ENTAILED or CONSISTENT whose problem has a premise naming (by id or label) a claim the claim cites, while that
    claim's own outcome in the same receipt is neither a definitive success nor NOT_ELIGIBLE."""
    status = {c.claim_id: o.display_status.value for o, c in outcomes}
    out: list[tuple[str, list[tuple[str, str]]]] = []
    for o, claim in outcomes:
        p = o.translation.problem
        if o.display_status.value not in _DEFINITIVE or p is None:
            continue
        bad = []
        for sib in dict.fromkeys(claim.supporting_claim_ids):
            if sib == claim.claim_id or sib not in status or status[sib] in _DEFINITIVE or status[sib] in _UNCHECKED_DISPLAY:
                continue
            if any(_names_claim(pr.id, sib) or _names_claim(getattr(pr, "label", None) or "", sib) for pr in p.premises):
                bad.append((sib, status[sib]))
        if bad:
            out.append((claim.claim_id, bad))
    return out


_STOP = frozenset(("the a an and or of to in on for with by is are was were be been being this that these those as at from it its into their there "
                   "which who whom not had has have having than then when while but so also such very more most less about over under after before "
                   "his her they them he she we our your").split())


def _content(text: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", (text or "").casefold()) if len(w) >= 3 and w not in _STOP)


def _same_fact(a: frozenset[str], b: frozenset[str]) -> bool:
    common = a & b
    return len(common) >= 4 and len(common) >= 0.75 * min(len(a), len(b))


def _var(expr: Any) -> Optional[str]:
    return expr.get("name") if isinstance(expr, dict) and expr.get("op") == "var" and isinstance(expr.get("name"), str) else None


def _vars_in(expr: Any) -> set[str]:
    out: set[str] = set()
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("op") == "var" and isinstance(node.get("name"), str):
                out.add(node["name"])
            stack.extend(v for k, v in node.items() if k != "name")
        elif isinstance(node, list):
            stack.extend(node)
    return out


def same_fact_inconsistencies(problems: list[tuple[str, Optional[dict]]]) -> list[tuple[str, str, str, str]]:
    """Rule ``same-fact-premise`` (TRN-009): ``(asserting claim id, premise id, leaving claim id, symbol)`` where one
    translation of the receipt asserts a fact as a Boolean premise atom and another leaves the same fact (by meaning and
    label) an unsupported Boolean conjunct of its own conclusion."""
    asserted: list[tuple[str, str, frozenset[str]]] = []
    unsupported: list[tuple[str, str, frozenset[str]]] = []
    for cid, prob in problems:
        if not isinstance(prob, dict):
            continue
        meaning = {s.get("name"): s.get("meaning") or "" for s in prob.get("symbols") or [] if isinstance(s, dict)}
        premises = [p for p in prob.get("premises") or [] if isinstance(p, dict)]
        in_premises: set[str] = set().union(*(_vars_in(p.get("expr")) for p in premises)) if premises else set()
        for p in premises:
            atoms = [_var(x) for x in (_conjuncts(p.get("expr")) if isinstance(p.get("expr"), dict) else [])]
            for name in (a for a in atoms if a):
                words = _content(meaning.get(name, "")) | _content(p.get("label") or "")
                if words:
                    asserted.append((cid, str(p.get("id")), words))
        concl = prob.get("conclusion")
        if isinstance(concl, dict):
            for x in _conjuncts(concl.get("expr")):
                name = _var(x)
                if name and name not in in_premises:
                    words = _content(meaning.get(name, ""))
                    if words:
                        unsupported.append((cid, name, words))
    out: list[tuple[str, str, str, str]] = []
    for a_cid, pid, a_words in asserted:
        for u_cid, name, u_words in unsupported:
            if a_cid != u_cid and _same_fact(a_words, u_words):
                out.append((a_cid, pid, u_cid, name))
    return list(dict.fromkeys(out))


def _receipt_level(ctx: CheckContext, t: Transfer) -> None:
    """TRN-008 and TRN-009 over the outcomes of one delivered report transfer."""
    items = list(_outcomes(t))
    if not items:
        return
    ids = t.ids()
    pairs = [(o, claim) for _i, o, _d, claim in items]
    for cid, bad in sibling_status_faults(pairs):
        shown = ", ".join(f"{s} ({st})" for s, st in bad)
        o = next(o for o, c in pairs if c.claim_id == cid)
        ctx.ovs(t.seq, "OVS-TRN-008", f"the translation of claim {cid} is displayed {o.display_status.value}, and its premises assert supporting claims "
                f"{shown} whose own outcomes in this receipt are not successful: the definitive display rests on claims its own receipt does not "
                "establish (the summary labels them only 'checked in its own problem')", claim_ids=[cid] + [s for s, _st in bad],
                formal_result_id=o.verification.result_id if o.verification is not None else None, **ids)
    probs = [(claim.claim_id, json.loads(_problem_json(dump, o.translation)) if _problem_json(dump, o.translation) else None) for _i, o, dump, claim in items]
    found = same_fact_inconsistencies(probs)
    by_pair: dict[tuple[str, str], list[str]] = {}
    for a_cid, pid, u_cid, name in found:
        by_pair.setdefault((a_cid, u_cid), []).append(f"{a_cid}'s premise {pid} asserts what {u_cid} leaves unsupported ({name})")
    for (a_cid, u_cid), what in by_pair.items():
        ctx.ovs(t.seq, "OVS-TRN-009", f"the translations of this receipt encode the same fact inconsistently: {_listed(what)}; the fact is a premise in one "
                f"problem and an unsupported conjunct in the check of the claim that states it (a from-memory fact needs one encoding)",
                claim_ids=[a_cid, u_cid], **ids)


# ============================================================================================ records and checks
def _request_texts(view: OverseerView, t: Transfer) -> list[str]:
    req = view.by_seq.get(t.request_seq) if t.request_seq is not None else None
    r = req.request if req is not None else None
    if r is None:
        return []
    return [r.user_input] + [c.text for c in r.constraints if getattr(c, "text", None)]


def _stored(ctx_store: Any, rid: Optional[str]) -> tuple[Optional[VerificationResult], Optional[bool]]:
    if not rid or ctx_store is None:
        return None, None
    rec = ctx_store.get(rid)
    if not isinstance(rec, StoredResult):
        return None, None
    return ctx_store.parsed(rid), bool(rec.signature_ok_at_put)


def _verified_copy(ctx: CheckContext, ver: Optional[VerificationResult]) -> Optional[VerificationResult]:
    """The receipt's copy of a result no longer held in full: usable when its signature verifies and, if the store kept a
    tombstone, it is byte-identical to the content recorded then."""
    if ver is None:
        return None
    try:
        ok, _why = ctx.keyring.verify_result(ver)
    except Exception:
        return None
    if not ok:
        return None
    rec = ctx.store.get(ver.result_id)
    if rec is not None and getattr(rec, "result_sha256", None) != sha256_hex(canonical_json(ver.model_dump(mode="json", exclude_none=True))):
        return None
    return ver


def _stored_sha256(ctx_store: Any, rid: Optional[str]) -> Optional[str]:
    rec = ctx_store.get(rid) if rid and ctx_store is not None else None
    return rec.result_sha256 if isinstance(rec, StoredResult) else None


def _record(view: OverseerView, store: Any, t: Transfer, i: int, o: ClaimVerificationOutcome, dump: dict, claim: ClaimRecord,
            checks_run: Iterable[str], revalidation: tuple[str, list[str]], outside_cited: Iterable[str] = ()) -> TranslationRecord:
    rid = o.verification.result_id if o.verification is not None else None
    stored, sig_ok = _stored(store, rid)
    report = t.report
    return TranslationRecord(
        seq=t.seq, message_id=t.message_id, receipt_id=t.receipt_id, report_id=report.report_id, agent_id=report.agent_id, claim_id=claim.claim_id,
        outcome_index=i, claim_text=claim.claim_text, cited_claims=tuple((c.claim_id, c.claim_text) for c in _cited_claims(claim, report)),
        translation=o.translation, problem_json=_problem_json(dump, o.translation), model_proposed=_model_proposed(o.translation), revalidation=revalidation[0],
        revalidation_detail=tuple(revalidation[1]), result_id=rid, result_status=getattr(stored.status, "value", None) if stored is not None else None,
        signature_verified=sig_ok, display_status=o.display_status.value, checks_run=tuple(c for c in TRANSLATION_CHECKS if c in set(checks_run)),
        outside_cited_claims=tuple(outside_cited),
        result_sha256=_stored_sha256(store, rid))


def check_translations(ctx: CheckContext, t: Transfer) -> list[TranslationRecord]:
    """TRN-001..007 for every outcome of ``t`` (see the module docstring); returns the translation records."""
    records: list[TranslationRecord] = []
    report = t.report
    for i, o, dump, claim in _outcomes(t):
        tr = o.translation
        ids = t.ids()
        rid = o.verification.result_id if o.verification is not None else None
        cid = [claim.claim_id]
        path = f"outcomes[{i}]"
        hand_built = tr.provider is None and tr.translator_version in ctx.hand_built_translators
        ran = ["revalidate", "status", "grounding", "circular"]
        outside_cited: tuple[str, ...] = ()
        problem_json = _problem_json(dump, tr)
        # TRN-001
        reval = revalidate(problem_json, claim)
        if reval[0] == "invalid":
            ctx.ovs(t.seq, "OVS-TRN-001", f"the IR proposed for claim {claim.claim_id} ({path}.translation.problem, translation {tr.translation_id}) fails "
                    f"re-validation as untrusted data: {_listed(reval[1])}", claim_ids=cid, formal_result_id=rid, **ids)
        # TRN-002
        faults, rederived = status_faults(o, claim, hand_built=hand_built)
        if rederived:
            ran.append("eligibility")
        if faults:
            ctx.ovs(t.seq, "OVS-TRN-002", f"the translation of claim {claim.claim_id} ({path}.translation, {tr.translation_id}) is not the image of its "
                    f"validation: {_listed(faults)}", claim_ids=cid, formal_result_id=rid, **ids)
        # TRN-003 / TRN-004
        if tr.problem is not None:
            overstated, absent = grounding_faults(tr, report)
            if overstated:
                ctx.ovs(t.seq, "OVS-TRN-003", f"the IR of claim {claim.claim_id} ({path}.translation) states more grounding than the deterministic grounding "
                        f"check gives: {_listed(overstated)}", claim_ids=cid, formal_result_id=rid, **ids)
            if absent:
                docs = sorted({d for _n, d, _x in absent if d})
                ctx.ovs(t.seq, "OVS-TRN-004", f"the IR of claim {claim.claim_id} ({path}.translation) carries quotation groundings the supplied texts do not "
                        f"bear out: {_listed([f'{n} ({d}): {x}' for n, d, x in absent])}; the result relies on them only as ungrounded dependencies",
                        claim_ids=cid, document_ids=docs, formal_result_id=rid, **ids)
            # TRN-005 (a deterministic comparison of the IR with the report: run for every translation that carries a problem,
            # whoever proposed it; contained round c1: a provider-less translation with an invented number was never traced)
            ran.append("trace")
            problem_obj = json.loads(problem_json) if problem_json else None
            request_texts = _request_texts(ctx.view, t)
            supplied = [d.text for d in report.supplied_texts]
            invented = untraced_content(tr.problem, problem_obj, report_scope(report), request_texts, supplied)
            outside = untraced_content(tr.problem, problem_obj, cited_scope(claim, _cited_claims(claim, report)), request_texts)
            outside_cited = tuple(dict.fromkeys(name for name, _d in outside))
            if invented:
                ctx.ovs(t.seq, "OVS-TRN-005", f"the IR proposed for claim {claim.claim_id} ({path}.translation) carries content the specialist's report never "
                        f"states (in no claim and nowhere in its response): {_listed([d for _n, d in invented])}", claim_ids=cid, formal_result_id=rid, **ids)
            # TRN-006 (a premise identical to the conclusion that is a verified, traced transcription of a grounded fact is
            # a transcription, not the claim assumed) and TRN-010 (rule restatement-necessity: the auditor's own signed
            # engine run without the restating premises decides whether the result rests on them)
            problem_obj6 = json.loads(problem_json) if problem_json else None
            circ = circular_premises(problem_obj6)
            transcribed = [p for p in circ if is_transcription(p, tr.problem, problem_obj6, report, _request_texts(ctx.view, t))]
            circ = [p for p in circ if p not in transcribed]
            if circ:
                nec = restatement_necessity(ctx, t, problem_obj6, circ)
                shown = ", ".join(circ[:6])
                runs = [nec.result_id] if nec.result_id else []
                if nec.follows:
                    own = set(o.verification.premises_relied_on) if o.verification is not None else set()
                    core_note = (f"; the outcome's own signed result relied only on the restatement ({', '.join(sorted(own)[:6])}) in place of the derivation"
                                 if own and own <= set(circ) else "")
                    ctx.ovs(t.seq, "OVS-TRN-010", f"redundant restatement in the translation of claim {claim.claim_id} ({path}.translation): premise(s) {shown} "
                            f"restate the conclusion, but the auditor's own signed engine run on the problem without them {nec.describe()} (rule {NECESSITY_RULE}): "
                            f"the result does not rest on the claim assumed, and the restating premise(s) add nothing{core_note}",
                            claim_ids=cid, formal_result_id=rid, related_result_ids=runs, **ids)
                else:
                    ctx.ovs(t.seq, "OVS-TRN-006", f"circular translation of claim {claim.claim_id} ({path}.translation): its conclusion occurs verbatim in "
                            f"premise(s) {shown}, and the auditor's own signed engine run on the problem without them {nec.describe()} (rule {NECESSITY_RULE}), "
                            "so the engine result rests on the claim assumed, not on the specialist's reasoning",
                            claim_ids=cid, formal_result_id=rid, related_result_ids=runs, **ids)
                ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: premise(s) {shown} restate the conclusion; the auditor's run "
                         f"{nec.result_id or '(none)'} without them {nec.describe()}: " + ("redundant restatement (OVS-TRN-010)" if nec.follows else "circular (OVS-TRN-006)"))
            if transcribed:
                ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id} transcribes a grounded fact: premise(s) {', '.join(transcribed[:6])} "
                         "state the conclusion verbatim under a verified grounding whose figures the texts state (not circular; the result tests transcription only)")
        # TRN-007 (against the stored result; when it was evicted, against the receipt's copy once its signature verifies
        # and it is the content the store recorded; a check the delivered transfer needs never silently goes unrun)
        stored, _sig = _stored(ctx.store, rid)
        if rid is not None and stored is None:
            stored = _verified_copy(ctx, o.verification)
            if stored is None and not ctx.view.degraded and ctx.store.get(rid) is not None:
                ctx.ovs(t.seq, "OVS-AUDIT-005", f"the summary of outcome {path} (claim {claim.claim_id}) cannot be re-checked: result {rid} was evicted from the "
                        "store and the receipt's copy is not the verified content the store recorded; the transfer cannot pass", claim_ids=cid, formal_result_id=rid, **ids)
        if rid is None or stored is not None:
            ran.append("summary")
            if not summary_matches(o, claim, stored, ctx.keyring):
                ctx.ovs(t.seq, "OVS-TRN-007", f"the summary of outcome {path} (claim {claim.claim_id}) is not the deterministic statement of its translation "
                        + (f"and the signed result {rid}" if rid else "with no engine result") + ": it states something the translation and the signed result do not",
                        claim_ids=cid, formal_result_id=rid, **ids)
        records.append(_record(ctx.view, ctx.store, t, i, o, dump, claim, ran, reval, outside_cited if "trace" in ran else ()))
    _receipt_level(ctx, t)
    return records


def translation_records(view: OverseerView, store: Any = None) -> list[TranslationRecord]:
    """Every translation of a delivered claim in ``view`` as the journal holds it (no check is run; ``checks_run`` is
    empty and ``revalidation`` is the re-validation outcome)."""
    out: list[TranslationRecord] = []
    for t in view.transfers:
        for i, o, dump, claim in _outcomes(t):
            out.append(_record(view, store if store is not None else view.store, t, i, o, dump, claim, (), revalidate(_problem_json(dump, o.translation), claim)))
    return out
