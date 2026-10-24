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
* **TRN-006** (error): circular translation: the conclusion, or part of it, is restated by premises the writer supplied
  itself, so an ENTAILED result rests on the claim assumed, not on the specialist's reasoning. Named rules decide which
  premises restate it, which of them are the writer's own, and when a restatement of part of it counts
  (:func:`restatement`):

  - ``circularity-agreement`` (the translator merge, design decision 46, as amended by decision 49): a premise restates
    the conclusion by the translator's own definition (``engine.runner.circular_premises``: the conclusion, or each of
    its conjuncts, is the premise or one of its conjuncts) or by the earlier verbatim reading (:func:`circular_premises`:
    the conclusion's expression is a node of the premise's conjunction tree), and the overseer is NEVER LOOSER than the
    translator: every grounding the translator's rule reads as the writer's own (``engine.runner.assumed_grounding`` on
    the grounding as the deterministic check re-derives it) is the writer's own here too. A translation the translator
    withheld as circular itself (its pipeline's INVALID_FORMALIZATION with ``E112``, no problem delivered) gets no
    finding here (the audit's coverage notes say so).
  - ``semantic-restatement`` (the second repair of the translator merge, decision 51): the conclusion is taken apart
    into its conjuncts with negation pushed inward (:func:`nnf_conjuncts`: ``not (a or b)`` gives ``not a`` and ``not
    b``); a conjunct that holds under every assignment (read by the engine's own compiler) needs no premise, so a
    tautology conjoined to the conclusion never keeps the rest from being restated as a whole. A premise restates a
    conjunct as written (the readings above, or the conjunct is the premise or one of its conjuncts) or in another form
    (:class:`_Readings`, bounded solver checks on the IR as data): the conjunct follows from the premise alone by its
    Boolean structure, comparisons and symbols opaque atoms (``e or e``, ``true implies e``, ``not not e``,
    ``b and (b implies e)``, a reversed comparison, ``x + 0 = 5`` for ``x = 5``), or the premise (or its part about the
    conjunct's symbols) is equivalent to the conjunct by the order of numbers with every arithmetic term opaque
    (``q >= 105 and q <= 105`` for ``q = 105``), or, rule ``arithmetic-restatement`` (STEM repair 12, decision 72), it is
    equivalent to the conjunct by the arithmetic of the conjunct's own symbols, each number exact and every arithmetic of
    numbers alone one opaque value: the conjunct rewritten, its terms moved across or both sides scaled (``contrib - 2.00 = 0``
    and ``2 * contrib = 4.00`` for ``contrib = 2.00``, ``2 * x + 3 = 7`` for ``x = 2``). A check its bounds leave undecided
    counts as a restatement. Arithmetic of numbers alone is never read as one: a premise that gives a conjunct only by the
    computation it writes on numbers (a line of working, ``a = (20 - 0) / 4.0`` beside ``a = 5.0``), or that entails it
    without being equivalent to it (``x = 5`` beside ``x > 3``), is a derivation the engine checks. Before rule
    ``arithmetic-restatement`` every arithmetic term was opaque, so a premise that restated the conclusion with its terms
    moved across or scaled restated nothing: the result rested on the claim assumed with no finding, and a
    ``translation_circular`` accusation of it was refuted.
  - ``grounded-transcription`` (review round 1; restored by the repair of the translator merge, decision 49; made exact
    by rule ``data-standing``, the third repair, decision 55): a restating premise is a transcription of a grounded fact,
    not the claim assumed, ONLY on a deterministic check the overseer re-derives (:func:`premise_standing` gives
    ``transcription``): its grounding is a ``quotation``, ``supplied_text``, ``arithmetic_fact`` or ``task_setting`` the
    deterministic grounding check VERIFIES on the report's supplied texts (a located excerpt that states the premise's
    figures), every figure it states is stated by the report's texts (a task setting's also by the request's), and the
    excerpt states none of them only as a target the answer must derive (rule ``same-quantity``: a "show that" target is
    never data) or only where its document does not state it as a statement (rule ``statement-context``, decision 57: in a
    yes/no question, under a negation, as one of alternatives, inside a claim the answer must examine, as a requirement on
    the answer or a limit's value the premise's statement does not name). Nothing else: no kind label and no number match. Decision 55 WITHDREW rule ``figure-transcription`` (the
    second repair's, decision 51), which took a ``task_setting`` or ``supplied_text`` premise with no excerpt, stating
    only figures, as a transcription when each figure occurred anywhere in the request: "the count is 80" passed beside
    "write no more than 80 words", and a "show that" target passed as the claim's own result. Every other restating
    premise is the writer's own for the overseer, and rule ``data-standing`` records what a deterministic check SHOWS of
    it (:data:`STANDINGS`): ``own_kind`` (no grounding, ``assumption``, ``specialist_inference``, ``general_knowledge``, or
    an ``arithmetic_fact`` or ``quotation`` no check verified: never looser than the translator), ``refuted`` (the
    grounding check refutes it; its excerpt states a figure only as a target; or, with no excerpt, its held source
    refutes it by rule ``same-quantity`` (:func:`figure_refutation`: a figure stated nowhere there, only as a target, only
    for another quantity, or only as a bound the premise states as a value; rule ``frequency-words`` reads "monthly" as
    12), or the translation itself declares what it states the writer's own), ``uncheckable`` (a ``rubric_rule``,
    ``knowledge_document`` or ``library_source``, sources no check verifies a premise against, or a ``supplied_text``
    with no excerpt naming no document supplied with the request; and, the fourth repair, decision 56, a ``task_setting``
    or ``supplied_text`` with no excerpt whose content no check READS in its held source: Boolean content (whatever the
    translation declares of its symbols and its conclusion), anything but the values of quantities (:func:`value_atoms`:
    a relation, arithmetic, a negation), a structural figure (0 or 1), or a figure the source states only bare, for a
    premise whose statement names no quantity, or otherwise than the premise states it: on any of these the kind label
    is the only evidence that the source states it, and a label is no evidence) and ``undecided`` (a ``task_setting`` or
    ``supplied_text`` with no excerpt whose whole content is values of quantities that rule ``same-quantity`` READS in its
    held source, :func:`figure_reading`: each figure stated there for the quantity the premise's own statement names, as
    the premise states it, in a table in the row the statement names, rule ``table-cells``, and, the fifth repair, decision
    57, as a statement, rule ``statement-context`` (:func:`figure_context`: not in a yes/no or embedded question, under a
    negation before the figure in its clause or one after it negating what the premise says, as one of alternatives,
    inside a claim the answer must examine, or as a requirement on the answer or the value of a limit or target, unless the premise's statement
    names a requirement or a limit; the request's constraint texts state requirements; data in an instruction, a
    supposition, a wh-question's presupposition and a negated bound are statements): data presented as given there,
    which no check verifies as a transcription, for a number match is no evidence, and none refutes; whether the source
    states it, for the same quantity, is a meaning question for overseer agents, Inspection I78). The first three are
    SHOWN not to be data (:data:`SHOWN_STANDINGS`). The kind is IR data proposed by a model, never evidence on its own, a
    ``task_setting`` label included: decision 56 corrected the third repair, which read Boolean content and figures it
    could not read in the source as ``undecided`` on the label alone, so "p proves p" under a ``task_setting`` label was
    graded a warning and cleared. This is stricter than the translator, whose rule delivers a restatement
    grounded ``task_setting``, ``supplied_text``, ``rubric_rule``, ``knowledge_document`` or ``library_source`` on the
    label alone and reads a restatement only as written: such an encoding reaches the receipt displayed ENTAILED, and the
    overseer grades it here.
  - ``receipt-disclosure`` (the second repair, decision 51): when the conclusion is NOT restated as a whole (a conjunct
    is derived from other premises, or left open), a writer's-own premise restating part of it under an ENTAILED result
    is graded by what the receipt discloses about it. The engine lists it among the result's ungrounded or unverified
    dependencies (``engine.runner.is_ungrounded`` or ``is_unverified``) and the outcome summary names it: no finding, a
    coverage note (the receipt does not present that part as established). It is a ``task_setting``, ``rubric_rule`` or
    ``arithmetic_fact`` no check verified, which the receipt presents as given with the task: graded by rule
    ``engine-shown`` on that part (below). So conjoining a verified fact to the conclusion never hides an assumed premise.

  The rule holds when every conjunct of the conclusion that needs a premise is restated by some premise and at least one
  restating premise is the writer's own (so whenever the translator's rule holds, and whenever the conclusion's
  expression occurs verbatim in such a premise); the translation is then graded by rules ``restatement-necessity`` and
  ``engine-shown`` below. When every restating premise is a transcription, it is a transcription check: no finding, a
  coverage note. (Harness-stage correction, kept: a conclusion that is itself a conjunction, assumed verbatim, was
  missed when only the leaves of a premise's conjunction tree were compared.)
* Named rule ``restatement-necessity`` (TRN-006 / **TRN-010**, after the recorded round r7): whether the result rests on
  restating premises is decided by the engine, never assumed. The IR with those premises removed (the rest of the IR
  unchanged) is run afresh as untrusted JSON through the engine's own validator, compiler and procedures
  (``engine.runner.verify``, default limits, the channel's journaled solver configuration with unsat cores) inside
  :meth:`CheckContext.auditor_run`, so the run is signed under the auditor's run key and stored (origin
  ``auditor_run``; memoised in the store by the reduced problem and the configuration). A run "gives ENTAILED" only when
  its signed status is ENTAILED with no diagnostic that withholds the verdict; any other outcome (COUNTEREXAMPLE,
  INCONSISTENT_PREMISES, an undecided status, no signed run, a failure of the run itself) counts as the result resting
  on the removed premises: uncertainty never resolves toward clearance. A restating premise is removed whole, never
  rewritten, so a conjunct it carries beside the conclusion is removed with it (conservative).
* Named rule ``engine-shown`` (TRN-006 / TRN-010 / **TRN-011**, the third repair, decision 55;
  :func:`engine_shown_grade`): a restatement is graded by what the engine SHOWS, never beyond "a data conjunct needs its
  data premise". Of the writer's-own restating premises graded (every one when the conclusion is restated as a whole;
  the undisclosed ones when only part is), S are those a check shows are not data (``own_kind``, ``refuted``,
  ``uncheckable``: the writer's own by kind, refuted, or presented as data on a label alone) and U those whose whole
  content rule ``same-quantity`` reads as their held source's data but that no check verifies as a transcription
  (``undecided``, decision 56):

  1. the run without all of them gives ENTAILED: **TRN-010** (a warning: a redundant restatement; for a part restated,
     a coverage note);
  2. else S is not empty and the run without S alone does not give ENTAILED: **TRN-006** (an error: the result rests on
     the claim assumed);
  3. else the result rests only on U, which shows only that a data conjunct needs its data premise, not that the claim
     was assumed: **TRN-011** (a warning) naming U, whether the receipt lists a premise of U among the result's
     unverified dependencies (a ``supplied_text``) or presents it as given with the task (a ``task_setting``): either way
     no check decides whether its source states it. S, if any, adds nothing beside U: TRN-010 (a note for a part
     restated). TRN-011 leaves a ``translation_circular`` accusation of the claim unresolved (no check decides it):
     whether the request states the premise, for the same quantity, is a meaning question for overseer agents.
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
  ``p`` on m, g, s, L, N, J, W, Pa, Hz, V, A, mol, eV, C, Ω; with ``²`` or ``³``, or an ASCII ``2`` or ``3`` written right after
  the unit as supplied texts write it (``cm3``, ``dm3``, ``m2``), the factor is squared or cubed) states
  its value in the unprefixed unit too (``15 cm`` also 0.15, ``2.5 km`` 2500, ``250 cm³`` 0.00025), and a mass in grams
  or kilograms states it in the other (``500 g`` also 0.5, ``3.2 kg`` 3200). No other conversion is read (minutes to
  seconds, degrees Celsius to kelvin, compound units): a translator that converts on its own is named, as a warning;
* ``excerpt-prefix-units`` (STEM repair 1): a quotation's located excerpt states each of its figures written with a unit
  symbol in the same unit with no prefix or under a prefix in steps of a thousand (k, M, G, m, µ, n, p), a length, area or
  volume in metres also in centimetres, a volume in litres too (ASCII exponents included, a litre a cubic decimetre: "50.0
  cm3 of thiosulfate" states 0.0000500 m³, 0.0500 dm³ and 50.0 mL, never 0.500 dL), so a premise that encodes the excerpt's figure
  converted that way is grounded for TRN-004 and is a verified transcription for TRN-006: a conversion is never the claim
  assumed. The rule reads the located excerpt only, for those two checks: TRN-005 still names a number the report states in
  no spelling its rules read (a conversion the translator made itself, other than into the unit without the prefix, stays
  a warning: Inspection I91);
* ``stated-precision``: a decimal (``9.8``), or a whole number after ``≈`` or ``~``, states the ends of the interval its
  last digit gives (``9.75`` and ``9.85``; ``≈ 13`` gives ``12.5`` and ``13.5``), the half-unit reading a translator
  may encode for an approximate value. A tolerance stated in words ("within 2%") is not read.
* ``stem-exact-scale`` (STEM completion, decision 60): in a STEM answer (a report the sciences, mathematics or computer
  science branch reads) rule ``percent-as-fraction`` is not applied. A STEM answer states many numbers (its marks, its
  part numbers, its working), so a number 100 times or a hundredth of any of them is traced by chance: a monthly rate the
  answer writes ``0.036/12 = 0.003`` encoded as 0.03 was traced by the "3 marks" of a heading. A percentage the answer
  writes with its sign is still read as both numbers (``3.6%`` states 3.6 and 0.036, as above), and a number is traced as
  the answer states it under the STEM readings; a factor of 100 the translator applied on its own is named, as a warning,
  like any conversion of its own.
* ``decimal-ratio`` (STEM completion, decision 60): a ratio with a decimal on either side (``0.036/12``, ``9.81/2``,
  ``6/2.5``) states its quotient and both sides, as ``a/b`` does for whole numbers. Before it, the digit rule read only
  the decimal before the slash, so a translation that divides by the stated 12 of ``0.036/12`` was named for a 12 the
  answer states. A side the slash joins inside a longer numeral (a date ``12/03/2024``, a decimal denominator the digit
  rule reads only in part) is read as before.
* ``table-units`` (STEM repair 2): in a STEM answer, a figure of a supplied table carries the unit its column's header
  names ("Dissolved oxygen (mg dm-3)"), and a figure the answer writes with a compound unit ("0.10 mol dm⁻³") carries that
  unit; such a figure is also stated in the same unit with no prefix: every prefixed atom without its prefix (grams as
  grams: 9.6 mg dm⁻³ is 9.6 g m⁻³) and the coherent SI unit with the mass in kilograms (0.0096 kg m⁻³). For TRN-005 a
  table figure counts when the answer states the figure itself; for TRN-004 and the transcription standing of TRN-006 a
  located excerpt that is (part of) a table row states each of its cells so. A conversion into any other unit stays a
  number the answer does not state (a warning), and a wrong conversion keeps both codes. Before it, a translation that
  wrote the table's 9.6 mg dm⁻³ as 0.0096 (kg m⁻³), which Inspection I91 calls the answer's own number, was OVS-TRN-004 and
  OVS-TRN-005.

Deviation from ``docs/OVERSEER_DESIGN.md`` (stage ``hook``, founder's requirement of translator oversight): these checks
extend the audit stage's live tier. Like L5 fidelity they run in the asynchronous tier for live transfers (the transfer
is AUDIT_PENDING until they have run) and directly in the batch tier.
"""
from __future__ import annotations

import bisect
import functools
import json
import re
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any, Iterable, Iterator, Optional

from ...engine.results import VerificationResult
from ...engine.runner import _canonical as _translator_canonical
from ...engine.runner import _conjuncts as _translator_conjuncts
from ...engine.runner import assumed_grounding, is_ungrounded, is_unverified, verify
from ...engine.runner import circular_premises as translator_circular_premises
from ...engine.statuses import VerificationStatus
from ...engine.validator import parse_and_validate
from ...integrity.contracts import MESSAGE_MAX_CHARS
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
    "TRANSCRIPTION_KINDS", "Necessity", "without_premises", "restatement_necessity", "NECESSITY_RULE", "Restatement", "restatement", "AGREEMENT_RULE",
    "withheld_as_circular", "VERIFIED_TRANSCRIPTION_KINDS", "TRANSCRIPTION_RULE", "transcription_fault", "FIGURE_TRANSCRIPTION_KINDS", "FIGURE_RULE",
    "SEMANTIC_RULE", "DISCLOSURE_RULE", "RESTATEMENT_WAYS", "SEMANTIC_WAYS", "RESTATEMENT_RLIMIT", "RESTATEMENT_TIMEOUT_MS", "nnf_conjuncts",
    "disclosed_by_the_receipt", "premise_standing", "Standing", "STANDINGS", "SHOWN_STANDINGS", "TRANSCRIPTION", "OWN_KIND", "REFUTED", "UNCHECKABLE",
    "UNDECIDED", "target_spans", "figure_refutation", "same_quantity_marker", "engine_shown_grade", "engine_shown_codes", "SAME_QUANTITY_RULE",
    "STANDING_RULE", "ENGINE_SHOWN_RULE", "FREQUENCY_RULE", "HELD_SOURCE_KINDS", "UNREAD_SOURCE_KINDS", "WRITER_OWN_KINDS", "GRADE_CIRCULAR",
    "GRADE_REDUNDANT", "GRADE_UNDECIDED", "GRADE_NOTE_REDUNDANT", "FREQUENCY_MARKER", "figure_reading", "FigureReading", "FIGURE_REFUTED", "FIGURE_READ",
    "FIGURE_UNREAD", "value_atoms", "TABLE_RULE", "CONTEXT_RULE", "CONTEXTS", "CONTEXT_STATEMENT", "CONTEXT_QUESTION", "CONTEXT_NEGATION",
    "CONTEXT_ALTERNATIVE", "CONTEXT_EXAMINED", "CONTEXT_REQUIREMENT", "CONTEXT_LIMIT", "CONTEXT_WORDS", "figure_context", "figure_negates",
    "EXCERPT_UNITS_RULE", "overseer_grounding",
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


def _named(ids: list[str]) -> str:
    """The premise ids a finding names: the first ``_MAX_LISTED`` and how many more, never a silent cut."""
    more = len(ids) - _MAX_LISTED
    return ", ".join(ids[:_MAX_LISTED]) + (f" and {more} more" if more > 0 else "")


def fit_reasons(head: str, label: str, items: list[str], cap: int = MESSAGE_MAX_CHARS) -> str:
    """A finding's message as ``head`` (its evidence: what is restated, the auditor's signed run and the rules) followed
    by ``label`` and as many whole ``items`` (each premise's reason) as fit within ``cap``, the number left out stated
    (they are in full in the finding's audit note). The cap truncates a message at its end, so the evidence comes first
    and is never cut by the length of the reasons (rule engine-shown: the recorded r7 task m1.1 names five premises,
    whose reasons once pushed the signed run and the rule past the cap)."""
    if not items:
        return head
    left_out = lambda n: f"; and for {n} more premise(s), in the audit notes"  # noqa: E731
    text, kept = f"{head}; {label}: ", 0
    for i, item in enumerate(items):
        piece = ("; " if kept else "") + item
        room = cap if i == len(items) - 1 else cap - len(left_out(len(items) - i))
        if len(text) + len(piece) > room:
            break
        text, kept = text + piece, kept + 1
    if kept == 0:
        return f"{head}; {label}: in the audit notes"
    return text if kept == len(items) else text + left_out(len(items) - kept)


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


#: Named rule ``excerpt-prefix-units`` (STEM repair 1): a quotation's located excerpt also states each of its figures with an
#: SI-prefixed unit in the same unit with no prefix or under a prefix in steps of a thousand (k, M, G, m, µ, n, p), a length,
#: area or volume in metres also in centimetres, and a volume in litres too, a litre a cubic decimetre ("50.0 cm3" states
#: 0.0000500 m³, 0.0500 dm³ and 50.0 mL, never 0.500 dL). Read for TRN-004 and the transcription standing of TRN-006 only:
#: TRN-005 still names a number the answer does not state in a spelling its rules read (Inspection I91: a conversion the
#: translator made itself is a warning, never the claim assumed).
EXCERPT_UNITS_RULE = "excerpt-prefix-units"
#: the prefixes a figure may be written with (rule ``si-prefix-units``'s, and d for dm³)
_WRITTEN_PREFIXES = {"": Fraction(1), "k": Fraction(10 ** 3), "M": Fraction(10 ** 6), "G": Fraction(10 ** 9), "d": Fraction(1, 10),
                     "c": Fraction(1, 10 ** 2), "m": Fraction(1, 10 ** 3), "µ": Fraction(1, 10 ** 6), "μ": Fraction(1, 10 ** 6),
                     "n": Fraction(1, 10 ** 9), "p": Fraction(1, 10 ** 12)}
#: the units a figure may be converted into: no prefix or a prefix in steps of a thousand; c on the metre only (cm, cm², cm³)
_TARGET_PREFIXES = tuple(dict.fromkeys(f for p, f in _WRITTEN_PREFIXES.items() if p not in ("c", "d")))
#: the unit symbols the rule reads (those of rule ``si-prefix-units``)
_CONVERSION_UNITS = ("mol", "Pa", "Hz", "eV", "m", "g", "s", "L", "N", "J", "W", "V", "A", "C", "Ω")
_CONVERSION_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(" + "|".join(re.escape(p) for p in _WRITTEN_PREFIXES if p) + r")?("
                                 + "|".join(re.escape(u) for u in _CONVERSION_UNITS) + r")([²³]|[23](?![\d.,]))?(?![A-Za-zΩ\d])")


def _excerpt_conversions(text: str) -> set[Fraction]:
    """Rule ``excerpt-prefix-units``: every figure of ``text`` written with a unit symbol, in that unit with no prefix and under
    each prefix in steps of a thousand (squared or cubed with the unit), a length, area or volume in metres also under c, a
    volume also in litres under those prefixes (a litre is a cubic decimetre). Exact table factors; nothing else is read."""
    out: set[Fraction] = set()
    for m in _CONVERSION_UNIT_RE.finditer(text or ""):
        value, prefix, unit, power = Fraction(m.group(1)), m.group(2) or "", m.group(3), m.group(4)
        exp = 2 if power in ("²", "2") else 3 if power in ("³", "3") else 1
        if unit == "L":
            exp, si = 3, value * _WRITTEN_PREFIXES[prefix] / 1000  # a litre is a cubic decimetre: the figure in m³
        else:
            si = value * _WRITTEN_PREFIXES[prefix] ** exp
        targets = _TARGET_PREFIXES + ((_WRITTEN_PREFIXES["c"],) if unit in ("m", "L") else ())
        out.update(si / f ** exp for f in targets)
        if unit in ("m", "L") and exp == 3:
            out.update(si * 1000 / f for f in _TARGET_PREFIXES)  # the volume in litres, millilitres, ...
    return out


#: Named rule ``table-units`` (STEM repair 2, module docstring): a compound unit's atoms (an SI prefix, a unit symbol, an exponent)
TABLE_UNITS_RULE = "table-units"
_ATOM_RE = re.compile(r"^(µ|μ|[kMGcmnpd])?(mol|Pa|Hz|eV|m|g|s|L|N|J|W|V|A|C|Ω)(⁻?[¹²³]|-?[123])?$")
_SUPERSCRIPT_EXP = {"¹": 1, "²": 2, "³": 3, "⁻¹": -1, "⁻²": -2, "⁻³": -3}
_COMPOUND_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)[ \t]?((?:(?:µ|μ|[kMGcmnpd])?(?:mol|Pa|Hz|eV|m|g|s|L|N|J|W|V|A|C|Ω)(?:⁻?[¹²³]|-?[123])?"
                          r"(?:[ \t]*(?:/|·|per)[ \t]*|[ \t]+)?){2,4})")


def _atom_exponent(text: Optional[str]) -> int:
    if not text:
        return 1
    if text in _SUPERSCRIPT_EXP:
        return _SUPERSCRIPT_EXP[text]
    return int(text)


@functools.lru_cache(maxsize=256)
def unprefixed_factors(unit_text: str) -> frozenset[Fraction]:
    """Rule ``table-units``: the factors that turn a value written in ``unit_text`` into the same unit with no prefix (each prefixed
    atom without its prefix, grams as grams) and into the coherent SI unit (the mass in kilograms). Atoms are separated by spaces,
    ``/``, ``·`` or "per" (which inverts what follows); an atom this table does not read ("counts", "minute", "h") keeps its factor 1.
    Empty when no atom carries a prefix and no gram is turned into kilograms. Exact table factors only."""
    toks = re.split(r"[ \t]+|(?<=\S)(?=/)|(?<=/)(?=\S)|·", (unit_text or "").strip())
    toks = [t for t in toks if t]
    if not toks or len(toks) > 8:
        return frozenset()
    plain, coherent, prefixed, grams, invert = Fraction(1), Fraction(1), False, False, False
    for t in toks:
        if t in ("/", "per"):
            invert = True
            continue
        m = _ATOM_RE.match(t)
        sign = -1 if invert else 1
        invert = False
        if m is None:
            continue  # an atom of no SI prefix ('counts', 'minute', 'h'): unchanged
        prefix, atom, exp = m.group(1) or "", m.group(2), _atom_exponent(m.group(3)) * sign
        f = _WRITTEN_PREFIXES.get(prefix, Fraction(1))
        if prefix:
            prefixed = True
        plain *= f ** exp
        if atom == "g":
            grams = True
            coherent *= (f / 1000) ** exp  # a mass in kilograms
        elif atom == "L":
            coherent *= (f / 1000) ** exp  # a litre is a cubic decimetre: the volume in cubic metres
            plain *= Fraction(1)
        else:
            coherent *= f ** exp
    if not prefixed and not grams:
        return frozenset()
    return frozenset(x for x in (plain, coherent) if x != 1)


def _compound_conversions(text: str) -> set[Fraction]:
    """Rule ``table-units``: every figure ``text`` writes with a compound unit, in that unit with no prefix and in the coherent SI unit."""
    out: set[Fraction] = set()
    for m in _COMPOUND_RE.finditer(text or ""):
        value = Fraction(m.group(1))
        out.update(value * f for f in unprefixed_factors(m.group(2).strip()))
    return out


def _table_rows(text: str) -> list[tuple[str, list[tuple[str, Optional[Fraction], str]]]]:
    """Rule ``table-units``: each row of each supplied pipe table, as its line and its cells ``(text, number, column unit)``."""
    from ...stem.datatables import parse_data_tables  # the STEM front end's own table reader (the same reading)
    out: list[tuple[str, list[tuple[str, Optional[Fraction], str]]]] = []
    for table in parse_data_tables((text,)):
        units = [c.unit_text for c in table.columns]
        for row in table.rows:
            cells = [(t, num.value if num is not None else None, units[j] if j < len(units) else "") for j, (t, num) in enumerate(row)]
            out.append((" | ".join(t for t, _v, _u in cells), cells))
    return out


def _table_conversions(text: str, stated: Optional[set[Fraction]] = None, excerpt: Optional[str] = None) -> set[Fraction]:
    """Rule ``table-units``: the cells of the supplied tables of ``text`` in their column's unit with no prefix and in the coherent SI
    unit: of the row ``excerpt`` is (part of), or every cell whose figure ``stated`` holds."""
    out: set[Fraction] = set()
    want = " ".join(excerpt.replace("|", " | ").split()) if excerpt else None
    for line, cells in _table_rows(text):
        if want is not None and want not in " ".join(line.replace("|", " | ").split()):
            continue
        for _t, v, unit in cells:
            if v is None or not unit or (stated is not None and v not in stated):
                continue
            out.update(v * f for f in unprefixed_factors(unit))
    return out


@functools.lru_cache(maxsize=512)
def stem_subject(subject: Optional[str]) -> bool:
    """Whether ``subject`` is one a STEM branch reads (rule ``table-units`` applies to STEM answers only)."""
    try:
        from ...branches import default_registry
        branch, _profile = default_registry().for_subject(subject)
    except Exception:
        return False
    return getattr(branch, "key", None) in STEM_BRANCH_KEYS


def _excerpt_states_in_base_units(problem: Problem, report: SpecialistReport, target_id: str, missing: list[str]) -> bool:
    """Rule ``excerpt-prefix-units``: every figure ``missing`` that the translator's ``figures_in_excerpt`` check found absent
    from the excerpt of assertion ``target_id`` is a figure of that located excerpt converted between SI prefixes of its unit
    (:func:`_excerpt_conversions`), so the excerpt states it: a conversion is no grounding fault and no unverified
    restatement (TRN-005 still names one the report does not state). Any other figure keeps the translator's verdict."""
    assertion = next((a for a in list(problem.premises) + ([problem.conclusion] if problem.conclusion is not None else []) if a.id == target_id), None)
    if assertion is None or assertion.grounding is None or not missing:
        return False
    docs = {d.document_id: d.text for d in report.supplied_texts}
    stated: set[Fraction] = set()
    stem = stem_subject(report.subject)
    for ref in assertion.grounding.source_refs:
        text = docs.get(ref.document_id)
        if not ref.excerpt or not text or locate_quotation(ref.excerpt, text, document_id=ref.document_id) is None:
            continue
        stated |= _excerpt_conversions(ref.excerpt)
        if stem:  # rule table-units: a compound unit after a figure, and a table row's cells in their column's unit
            stated |= _compound_conversions(ref.excerpt) | _table_conversions(text, excerpt=ref.excerpt)
    try:
        values = [Fraction(f.replace(",", "")) for f in missing]
    except (ValueError, ZeroDivisionError):
        return False
    return bool(stated) and all(v in stated or -v in stated for v in values)


_MISSING_FIGURES_RE = re.compile(r"does not state the premise's figures \[(?P<f>[^\]]*)\]")


def _missing_figures(detail: Optional[str]) -> list[str]:
    m = _MISSING_FIGURES_RE.search(detail or "")
    return [x.strip().strip("'\"") for x in m.group("f").split(",") if x.strip()] if m else []


def overseer_grounding(problem: Problem, report: SpecialistReport) -> tuple[Problem, list, set[str]]:
    """The translator's deterministic grounding check re-run on the report's supplied texts (``translate.grounding``), then
    rule ``excerpt-prefix-units``: ``(re-grounded problem, checks, accepted)``, where ``accepted`` names the assertions whose
    only failed check was ``figures_in_excerpt`` and whose missing figures the located excerpt states under another SI prefix
    of the same unit; their grounding is verified for the overseer (never looser than the translator, whose own rule reads
    every quotation as a transcription)."""
    rerun, checks = check_problem_grounding(problem, list(report.supplied_texts))
    failed: dict[str, list] = {}
    for c in checks:
        if c.verified is False:
            failed.setdefault(c.target_id, []).append(c)
    accepted: set[str] = set()
    for target, cs in failed.items():
        if all(c.method == "figures_in_excerpt" for c in cs) and all(_excerpt_states_in_base_units(problem, report, target, _missing_figures(c.detail)) for c in cs):
            accepted.add(target)
    if not accepted:
        return rerun, checks, accepted

    def fix(a):
        if a is None or a.id not in accepted or a.grounding is None:
            return a
        return a.model_copy(update={"grounding": a.grounding.model_copy(update={"verified": True})})
    rerun = rerun.model_copy(update={"premises": [fix(a) for a in rerun.premises], "conclusion": fix(rerun.conclusion)})
    return rerun, checks, accepted


def grounding_faults(tr: TranslationResult, report: SpecialistReport) -> tuple[list[str], list[tuple[str, Optional[str], str]]]:
    """``(overstated, absent)``. ``overstated``: verifications the re-run of the grounding check does not reproduce
    (TRN-003). ``absent``: ``(target, document id, detail)`` for every excerpt the re-run does not find in the document it
    names, or that does not state the figures of its assertion (TRN-004), but for a figure the located excerpt states in
    the unit without its prefix (rule ``excerpt-prefix-units``)."""
    problem = tr.problem
    if problem is None:
        return [], []
    rerun, checks = check_problem_grounding(problem, list(report.supplied_texts))
    _again, _checks, accepted = overseer_grounding(problem, report)
    again = {key: g for key, _name, g in _targets(rerun)}
    overstated: list[str] = []
    for key, name, g in _targets(problem):
        if g is not None and g.verified is True and (again.get(key) is None or again[key].verified is not True):
            overstated.append(f"{name} is marked verified, the grounding check gives {again[key].verified if again.get(key) is not None else None}")
    verified_again = {(c.target_id, c.document_id) for c in checks if c.verified is True}
    for c in tr.grounding_checks:
        if c.verified is True and (c.target_id, c.document_id) not in verified_again:
            overstated.append(f"the grounding check of {c.target_id} against {c.document_id!r} is recorded as verified; the re-run does not verify it")
    absent = [(c.target_id, c.document_id, c.detail or c.method) for c in checks if c.verified is False and c.target_id not in accepted]
    return list(dict.fromkeys(overstated)), absent


# ============================================================================================ TRN-005
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?:\s*/\s*(\d+))?")
#: Rule ``decimal-ratio`` (module docstring): a ratio with a decimal on either side, neither side part of a longer numeral.
_DECIMAL_RATIO_RE = re.compile(r"(?<![\w.,/])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\w/]|[.,]\d)")
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
                         + "|".join(re.escape(u) for u in _SI_UNITS) + r")([²³]|[23](?![\d.,]))?(?![A-Za-zΩ\d])")
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
        exp = 2 if power in ("²", "2") else 3 if power in ("³", "3") else 1
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
    # rule frequency-words (decision 55): a frequency adverb states its number of periods a year ("monthly" is 12)
    for m in _FREQUENCY_RE.finditer(text or ""):
        out.add(Fraction(_FREQUENCY_WORDS[m.group(1).lower()]))
    if _PERCENT_RE.search(text or ""):
        out.add(Fraction(100))
    for m in _DECIMAL_RATIO_RE.finditer(text or ""):  # rule decimal-ratio
        a, b = m.group(1), m.group(2)
        if "." in a or "." in b:
            num, den = Fraction(a), Fraction(b)
            out.update((num, den) if den == 0 else (num, den, num / den))
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


def number_traced(value: Fraction, known: set[Fraction], *, date_encoded: bool = False, exact_scale: bool = False) -> bool:
    """Whether ``value`` is stated by the texts whose numbers are ``known``: 0 and 1 always; the value itself; a stated
    percentage written as a fraction or a stated fraction written as a percentage (``percent-as-fraction``, not applied
    with ``exact_scale``: rule ``stem-exact-scale``); a date encoding of a stated year, and, in a problem that uses one
    (``date_encoded``), the divisors 100 and 10000 (``date-encoding``)."""
    v = abs(value)
    return (v in (0, 1) or v in known or (not exact_scale and (v * 100 in known or v / 100 in known)) or _date_encoding(v, known)
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
                     supplied_texts: Iterable[str] = (), *, exact_scale: bool = False) -> list[tuple[str, str]]:
    """``(target, description)`` for each quotation excerpt and number of the IR that ``scope_texts`` never state (a
    quotation may also come verbatim from ``supplied_texts``, rule ``supplied-text``; a task-setting premise may also take
    its numbers from ``request_texts``). ``exact_scale``: the report is a STEM answer (rules ``stem-exact-scale`` and
    ``table-units``)."""
    texts = [t for t in scope_texts if t]
    supplied_texts = [t for t in supplied_texts if t]
    quotable = texts + supplied_texts
    out: list[tuple[str, str]] = []
    for _key, name, g in _targets(problem):
        for ex in _excerpts(g):
            if not any(locate_quotation(ex, text) is not None for text in quotable):
                out.append((name, f"{name} quotes {ex[:80]!r}"))
    known = set().union(*(text_numbers(t) for t in texts)) if texts else set()
    if exact_scale and known:
        # rule table-units (STEM repair 2): a figure written with a compound unit, and a supplied table's figure the answer states,
        # in the same unit with no prefix and in the coherent SI unit
        known = known | set().union(*(_compound_conversions(t) for t in texts))
        known = known | set().union(*(_table_conversions(t, stated=known) for t in supplied_texts if t and "|" in t))
    task_known = set().union(*(text_numbers(t) for t in request_texts if t)) if request_texts else set()
    numbers = list(_assertion_numbers(problem_obj))
    date_encoded = any(_date_encoding(abs(v), known | (task_known if kind == "task_setting" else set())) for _a, kind, v in numbers)
    for aid, kind, v in numbers:
        if not number_traced(v, known | task_known if kind == "task_setting" else known, date_encoded=date_encoded, exact_scale=exact_scale):
            out.append((aid, f"{aid} uses the number {v}"))
    return list(dict.fromkeys(out))


#: The branches that read STEM answers (rule ``stem-exact-scale``).
STEM_BRANCH_KEYS = frozenset({"sciences", "mathematics", "computer_science"})


def stem_report(ctx: Any, t: Any) -> bool:
    """Whether the report of ``t`` is a STEM answer: the branch the auditor's registry gives the agent's subject under the
    journaled plan (as R2 chooses the branch whose packs it re-runs) is a STEM branch."""
    rep = getattr(t, "report", None)
    if rep is None:
        return False
    plan = ctx.view.plan_at(t.seq)
    subject = plan.agent_subjects.get(rep.agent_id, plan.subject) if plan is not None else rep.subject
    registry = getattr(ctx, "registry", None)
    if registry is None:
        from ...branches import default_registry
        registry = default_registry()
    try:
        branch, _profile = registry.for_subject(subject)
    except Exception:
        return False
    return getattr(branch, "key", None) in STEM_BRANCH_KEYS


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


#: Grounding kinds a restating premise may transcribe the conclusion from without being circular (rule
#: ``grounded-transcription``), on the one evidence :func:`premise_standing` accepts: the deterministic grounding check
#: VERIFIED a located excerpt that states the premise's figures (decisions 49 and 55). A ``rubric_rule``,
#: ``knowledge_document`` or ``library_source`` is never one: no check verifies a premise against those sources, so the
#: kind label alone would be the only evidence.
TRANSCRIPTION_KINDS = frozenset({"task_setting", "quotation", "supplied_text", "arithmetic_fact"})
#: Of those, the kinds whose premise needs the deterministic grounding check's verification (a located excerpt of a
#: supplied text that states the premise's figures): a quotation and a supplied text (review round 1) and an arithmetic
#: fact (the translator's own rule, ``engine.runner.assumed_grounding``). Since decision 55 a ``task_setting`` needs it too.
VERIFIED_TRANSCRIPTION_KINDS = frozenset({"quotation", "supplied_text", "arithmetic_fact"})
#: The kinds whose premise, with no located excerpt, names a source the overseer HOLDS from the journaled request
#: (rule ``same-quantity``, decision 55): a ``task_setting`` the request (its input, its constraints and the texts supplied
#: with it), a ``supplied_text`` the documents supplied with the request that its source references name. Such a premise
#: is never a transcription (no number match is evidence); the held source can only REFUTE it. (The name is the second
#: repair's, whose rule ``figure-transcription`` verified such a premise by its figures alone; decision 55 withdrew it.)
FIGURE_TRANSCRIPTION_KINDS = frozenset({"task_setting", "supplied_text"})
HELD_SOURCE_KINDS = FIGURE_TRANSCRIPTION_KINDS
#: Grounding kinds that name a source no deterministic check verifies a premise against (never a transcription).
UNREAD_SOURCE_KINDS = frozenset({"rubric_rule", "knowledge_document", "library_source"})
#: Grounding kinds that present a premise as the writer's own reasoning (``engine.runner.UNGROUNDED_KINDS``).
WRITER_OWN_KINDS = frozenset({"assumption", "specialist_inference", "general_knowledge"})
#: The rule that keeps the overseer's circularity check never looser than the translator's own (``E112``).
AGREEMENT_RULE = "circularity-agreement"
#: The rule that admits a restating premise as a transcription only on a deterministic check's verification.
TRANSCRIPTION_RULE = "grounded-transcription"
#: The second repair's rule that verified a no-excerpt premise by its figures alone (decision 51). WITHDRAWN by decision 55
#: (the third repair): a number match is no evidence, so it verifies nothing; the name is kept for the record.
FIGURE_RULE = "figure-transcription"
#: The rule that reads what the request (or a named supplied document) states of a no-excerpt premise's figures: it can
#: refute the premise as the source's statement, never verify it (decision 55).
SAME_QUANTITY_RULE = "same-quantity"
#: The rule that classifies every restating premise by what a deterministic check shows of it (:data:`STANDINGS`).
STANDING_RULE = "data-standing"
#: The rule that grades a restatement by what the ENGINE shows beyond "a data conjunct needs its data premise".
ENGINE_SHOWN_RULE = "engine-shown"
#: Rule ``frequency-words``: a frequency adverb states its number of periods a year (decision 55: "compounded monthly"
#: states 12). Read by :func:`text_numbers` too.
FREQUENCY_RULE = "frequency-words"
#: The rule that reads a premise as restating a conjunct of the conclusion in another form (decision 51).
SEMANTIC_RULE = "semantic-restatement"
#: The rule that grades a writer's-own premise restating only PART of the conclusion by what the receipt discloses about
#: it (decision 51).
DISCLOSURE_RULE = "receipt-disclosure"
#: Fixed resource bounds of one solver check of rule ``semantic-restatement`` and of the validity check of a conjunct:
#: an ``rlimit`` (deterministic), with a wall timeout as a safety net. The readings are propositional, or linear over
#: opaque terms, so a check decides well within them; one these bounds leave undecided counts as a restatement
#: (uncertainty never resolves toward clearance), and rule ``restatement-necessity`` grades it.
RESTATEMENT_RLIMIT = 4_000_000
RESTATEMENT_TIMEOUT_MS = 2_000

#: The standings of a restating premise (rule ``data-standing``, decision 55), by what a deterministic check SHOWS of it:
#: ``transcription`` (a located excerpt the grounding check verified: a check of the claim against its source);
#: ``own_kind`` (the writer's own by its grounding: none, ``assumption``, ``specialist_inference``,
#: ``general_knowledge``, an ``arithmetic_fact`` or ``quotation`` no check verified); ``refuted`` (a check refutes it as
#: its source's statement: a failed grounding check, a figure its held source states nowhere, only as the target the
#: answer must show, or only for another quantity, and content the translation itself declares the writer's own);
#: ``uncheckable`` (it names no source the overseer holds: a ``rubric_rule``, ``knowledge_document`` or
#: ``library_source``, a ``supplied_text`` naming no document supplied with the request; or, decision 56, a
#: ``task_setting`` or ``supplied_text`` with no located excerpt whose content no check reads in its held source: Boolean
#: content, anything but values of quantities, a structural figure, a figure stated there only bare or otherwise than the
#: premise states it, so the kind label is the only evidence; decision 57: or stated there only where the source asks,
#: denies, offers alternatives, puts up for examination, requires or limits it, rule ``statement-context``); ``undecided`` (a ``task_setting``
#: or ``supplied_text`` with no located excerpt whose whole content rule ``same-quantity`` READS in its held source as the
#: source's data, for the quantity the premise names, stated there as a statement, and that no check refutes or verifies
#: as a transcription). The first is no
#: restatement fault; the next three are SHOWN not to be data (the last of them: not shown to be data by anything but a
#: label); the last is data presented as given, read so by a check, and is neither.
TRANSCRIPTION = "transcription"
OWN_KIND = "own_kind"
REFUTED = "refuted"
UNCHECKABLE = "uncheckable"
UNDECIDED = "undecided"
STANDINGS = (TRANSCRIPTION, OWN_KIND, REFUTED, UNCHECKABLE, UNDECIDED)
SHOWN_STANDINGS = frozenset({OWN_KIND, REFUTED, UNCHECKABLE})


@dataclass(frozen=True)
class Standing:
    """What a deterministic check shows of one restating premise (rule ``data-standing``): ``kind`` is one of
    :data:`STANDINGS` and ``reason`` says why (empty for a transcription)."""
    kind: str
    reason: str = ""

    @property
    def shown(self) -> bool:
        """Shown NOT to be data (the writer's own by kind, refuted, or naming no source the overseer holds)."""
        return self.kind in SHOWN_STANDINGS


def _regrounded(problem: Problem, report: SpecialistReport) -> Problem:
    """``problem`` with every grounding's ``verified`` as the deterministic grounding check gives it on the report's
    supplied texts (the translator's own check, re-run; the IR's own flags are never trusted), with rule
    ``excerpt-prefix-units`` (:func:`overseer_grounding`)."""
    rerun, _checks, _accepted = overseer_grounding(problem, report)
    return rerun


def _bool_symbols(expr: Any, sorts: Optional[dict[str, str]]) -> list[str]:
    """What a premise (JSON) states beyond figures: its symbols that are not declared ``Int`` or ``Real`` (a Boolean
    symbol, or one not declared) and its truth constants. A figure cannot verify any of them."""
    out: list[str] = []
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("op") == "var":
                name = str(node.get("name"))
                if (sorts or {}).get(name) not in ("Int", "Real") and name not in out:
                    out.append(name)
                continue
            if node.get("op") == "bool":
                if "true/false" not in out:
                    out.append("true/false")
                continue
            stack.extend(v for k, v in node.items() if k != "value")
        elif isinstance(node, list):
            stack.extend(node)
    return out


def _numeric_symbols(expr: Any, sorts: Optional[dict[str, str]]) -> list[str]:
    """The ``Int`` and ``Real`` symbols a premise (JSON) names, in first-seen order."""
    out: list[str] = []
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("op") == "var":
                name = str(node.get("name"))
                if (sorts or {}).get(name) in ("Int", "Real") and name not in out:
                    out.append(name)
                continue
            stack.extend(v for k, v in node.items() if k != "value")
        elif isinstance(node, list):
            stack.extend(node)
    return out


def _literal(node: Any) -> Optional[Fraction]:
    """The value of a numeric literal of the IR (JSON): ``int``, ``real``, or ``neg`` of one; None for anything else."""
    if isinstance(node, dict):
        if node.get("op") in ("int", "real") and isinstance(node.get("value"), str):
            try:
                return Fraction(node["value"])
            except (ValueError, ZeroDivisionError):
                return None
        if node.get("op") == "neg":
            inner = _literal(node.get("arg"))
            return -inner if inner is not None else None
    return None


_ATOM_FLIP = {"eq": "eq", "lt": "gt", "le": "ge", "gt": "lt", "ge": "le"}


def value_atoms(expr: Any, sorts: Optional[dict[str, str]]) -> Optional[list[tuple[str, str, Fraction]]]:
    """Rule ``data-standing`` (the fourth repair of the translator merge, decision 56): a premise's whole content as the
    VALUES of quantities, ``(symbol, comparison, figure)`` for each of its conjuncts (negation pushed inward,
    :func:`nnf_conjuncts`; the constant true states nothing): a comparison ``eq``, ``lt``, ``le``, ``gt`` or ``ge`` of one
    ``Int`` or ``Real`` symbol with one figure, either way round (``105 eq q`` is ``q eq 105``). None when a conjunct is
    anything else (a Boolean symbol, a negated or ``ne`` comparison, arithmetic, a comparison of two symbols, a
    disjunction): content that no figure a source states can be read as. Data only, nothing is evaluated."""
    out: list[tuple[str, str, Fraction]] = []
    for c in nnf_conjuncts(expr):
        if c.get("op") == "bool" and c.get("value") is True:
            continue
        op = c.get("op")
        if op not in _ATOM_FLIP:
            return None
        for sym, num, rel in ((c.get("left"), c.get("right"), op), (c.get("right"), c.get("left"), _ATOM_FLIP[op])):
            name = sym.get("name") if isinstance(sym, dict) and sym.get("op") == "var" else None
            val = _literal(num)
            if name is not None and (sorts or {}).get(str(name)) in ("Int", "Real") and val is not None:
                out.append((str(name), rel, val))
                break
        else:
            return None
    return out or None


def _held_sources(g: Any, request_texts: Iterable[str], request_documents: Iterable[Any]) -> tuple[Optional[list[str]], str]:
    """``(texts, where)``: the texts of the journaled request a premise grounded ``g`` (a ``task_setting`` or
    ``supplied_text`` with no excerpt) names as its source, and how to name them; ``(None, why)`` when the grounding names
    nothing the request holds (the premise is then ``uncheckable``)."""
    docs = {d.document_id: d for d in request_documents}
    if g.kind == "task_setting":
        return ([x for x in request_texts if x] + [d.text for d in docs.values() if d.text],
                "the request (its input, its constraints and the texts supplied with it)")
    named = list(dict.fromkeys(r.document_id for r in g.source_refs))
    if not named:
        return None, (f"its {g.kind} grounding is not verified: it carries no located excerpt and names no document supplied with the request, so it "
                      "names no source a check could read; the kind label alone is IR data, not evidence")
    missing = [n for n in named if n not in docs]
    if missing:
        return None, (f"its {g.kind} grounding is not verified: it carries no located excerpt and names {', '.join(missing[:3])}, which is not among "
                      "the texts supplied with the request, so it names no source a check could read; the kind label alone is IR data, not evidence")
    return [docs[n].text for n in named if docs[n].text], f"the document(s) {', '.join(named[:3])} supplied with the request"


#: Kept for callers of the second repair's name.
_figure_sources = _held_sources

# ---------------------------------------------------------------------------- rule same-quantity (decision 55)
#: A target the answer must derive: "show that", "prove that", "verify that", "confirm that", "demonstrate that".
_TARGET_CUE_RE = re.compile(r"\b(?:show|prove|verify|confirm|demonstrate)\s+that\b", re.IGNORECASE)
#: The end of the cue's sentence: a full stop, question or exclamation mark before a space, a quote or bracket, or the
#: text's end (a decimal point is followed by a digit), or a line break.
_TARGET_END_RE = re.compile(r"[.?!](?=\s|$|[\"'”’)\]])|\n")
#: A bracketed part of a target sentence: data written beside the target ("(M = 40.0 g mol⁻¹)") or a mark annotation ("[3]").
_BRACKETED_RE = re.compile(r"\([^()\n]*\)|\[[^\[\]\n]*\]")
#: The copula before a stated target value ("... is 8 m", "x = 5", "≈ 8.0 h").
_COPULA_RE = re.compile(r"\s(?:is|are|was|were|equals|becomes)\s|[=≈≃]")


def target_spans(text: str) -> list[tuple[int, int]]:
    """Rule ``same-quantity``: the character spans of ``text`` that state a TARGET the answer must derive. After a cue
    ("show that", "prove that", "verify that", "confirm that", "demonstrate that") the target is what the sentence states
    after its last copula ("is", "are", "equals", "=", "≈"; the whole clause after the cue when it has none), up to the end
    of the sentence, less any part in brackets or parentheses (data written beside the target, as the STEM request reader
    reads it: "Show that 36 g of water is 2.0 mol (M = 18 g mol⁻¹)" targets 2.0 mol, not 36 g or 18). Positions index
    ``text``; nothing is evaluated."""
    out: list[tuple[int, int]] = []
    text = text or ""
    for m in _TARGET_CUE_RE.finditer(text):
        e = _TARGET_END_RE.search(text, m.end())
        end = e.start() if e else len(text)
        brackets = [(b.start(), b.end()) for b in _BRACKETED_RE.finditer(text, m.end(), end)]
        clause = list(text[m.end():end])
        for a, b in brackets:
            for i in range(a - m.end(), b - m.end()):
                clause[i] = " "
        cops = list(_COPULA_RE.finditer("".join(clause)))
        start = m.end() + (cops[-1].end() if cops else 0)
        pos = start
        for a, b in brackets:
            if b <= start:
                continue
            if a > pos:
                out.append((pos, a))
            pos = max(pos, b)
        if end > pos:
            out.append((pos, end))
    return out


def _blank(text: str, spans: Iterable[tuple[int, int]]) -> str:
    """``text`` with the characters of ``spans`` replaced by spaces (positions kept)."""
    chars = list(text)
    for a, b in spans:
        for i in range(max(0, a), min(len(chars), b)):
            chars[i] = " "
    return "".join(chars)


_FREQUENCY_WORDS = {"annually": 1, "yearly": 1, "semi-annually": 2, "semiannually": 2, "half-yearly": 2, "biannually": 2, "quarterly": 4,
                    "monthly": 12, "fortnightly": 26, "weekly": 52, "daily": 365}
_FREQUENCY_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(w) for w in _FREQUENCY_WORDS), key=len, reverse=True)) + r")\b", re.IGNORECASE)
#: The quantity a frequency adverb states (rule ``frequency-words``): a number of periods a year. A premise's statement names
#: it with any of these words ("the number of compounding periods a year", "12 times a year", "compounded monthly").
FREQUENCY_MARKER = "frequency"
_FREQUENCY_QUANTITY = frozenset(("period", "time", "compounding", "compound", "compounded", "payment", "instalment", "installment", "year", "annum",
                                 "annual", "frequency", "month", "quarter", "week", "fortnight", "day") + tuple(_FREQUENCY_WORDS))
#: Words after a figure that name no quantity (the figure is then bare: "8 of the 10", "Paper 1 in May").
_MARKER_SKIP = frozenset(("a an the of in on at to for and or but is are was were be been by with from as than that this these those it its each every "
                          "more less into over under up down out about between after before if so not no nor until while per which who when where").split())
_CURRENCY_BEFORE = {"$": "dollar", "€": "euro", "£": "pound", "¥": "yen"}
_MARKER_SYNONYMS = {"%": "percent", "per cent": "percent", "pct": "percent", "€": "euro", "eur": "euro", "$": "dollar", "usd": "dollar", "£": "pound",
                    "gbp": "pound", "yr": "year", "yrs": "year", "annum": "year", "hr": "hour", "hrs": "hour", "mins": "minute", "min": "minute",
                    "sec": "second", "secs": "second", "wk": "week", "wks": "week", "mo": "month", "mos": "month"}
_MARKER_TOKEN_RE = re.compile(r"\s{0,3}([A-Za-zµμΩ°][A-Za-z0-9µμΩ°³²¹⁰⁴⁵⁶⁷⁸⁹⁻⁺^\-]*)")
#: An ASCII exponent in a unit marker ("cm3", "dm-3", "s^-1"), written as the STEM unit reader reads it ("cm³", "dm⁻³").
_ASCII_EXPONENT_RE = re.compile(r"(?<=[A-Za-z])\^?(-?)(\d)$")
_TO_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
_SCALE_WORD_RE = re.compile(r"\s+(hundred|thousand|million|billion)\b", re.IGNORECASE)
_PERCENT_AFTER_RE = re.compile(r"\s{0,2}(?:%|per\s*cent\b|percent\b)", re.IGNORECASE)
#: Phrases that state a figure as a BOUND, not as a value ("no more than 80 words", "first exceeds 6000 euros").
_BOUND_BEFORE = ("no more than", "not more than", "at most", "up to", "maximum of", "max of", "a maximum of", "under", "below", "less than", "fewer than",
                 "lower than", "at least", "no less than", "no fewer than", "not less than", "minimum of", "a minimum of", "min of", "more than", "over",
                 "above", "exceeds", "exceed", "exceeding", "greater than", "higher than", "within", "beyond", "not exceeding", "not to exceed")
_BOUND_BEFORE_RE = re.compile(r"(?:^|\W)(" + "|".join(sorted((re.escape(p).replace(r"\ ", r"\s+") for p in _BOUND_BEFORE), key=len, reverse=True))
                              + r")\s+(?:a\s+|an\s+|the\s+)?[$€£¥]?\s*$", re.IGNORECASE)
#: Words of a premise's own statement that name a bound: a premise that names one may state a bound's figure as a value
#: ("the threshold is 6000 euros", "the word limit is 80 words").
_BOUND_WORDS_RE = re.compile(r"\b(?:limit|limits|maximum|minimum|max|min|cap|ceiling|floor|threshold|bound|bounds|at\s+most|at\s+least|no\s+more\s+than|"
                             r"no\s+fewer\s+than|no\s+less\s+than|up\s+to|exceed|exceeds|exceeding|above|below|under|over|more\s+than|less\s+than|"
                             r"fewer\s+than|within)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------- rule statement-context (decision 57)
#: Rule ``statement-context`` (the fifth repair of the translator merge, decision 57): the context of each place a source
#: states a figure. Only a STATEMENT states the figure as the source's own statement of its quantity. A figure in a
#: yes/no question ("Does the extract mention 3 workers?", "Explain whether ...", a yes/no clause of a wh-question: "How
#: many workers does it mention, or is it 3?"), under a negation ("does not mention 3 workers", "fails to mention 3
#: workers", "It is false that ..."), as one of alternatives ("3 or 4 workers", "Which is right, 3 workers or 4
#: workers?"), inside a claim the answer must examine ("Evaluate the claim that ...", a sentence or a quotation followed
#: by "Discuss." or "To what extent do you agree?"), or in a requirement on the answer (what the answer must do or meet:
#: "Your answer should be 80 words long", "Write 80 words", "Use 3 quotations", "in no more than 350 words") is not: the
#: source asks, denies, offers alternatives, puts up for examination or requires it; nor is the value of a limit or target
#: set on a quantity ("The word limit is 80 words", "an inflation target of 2 per cent"), which is the limit's value, not
#: the quantity's. A requirement or a limit is read only for a premise whose own statement names a requirement or a limit
#: ("the word limit is 80 words"), never for the quantity it is set on ("the answer has 80 words"). A negation reaches the
#: figure when it stands before it in its clause ("does not mention 3 workers"), or when, after it, it negates what the
#: premise's own statement says ("3 workers are not mentioned" for "the extract mentions 3 workers"; "the background of
#: 20 counts min⁻¹ has no uncertainty" negates nothing a premise about the background states).
#: Statements include data written in an instruction ("Find the value of the investment after 5 years", "Use g = 9.8"), a
#: supposition ("If the car travels 8 m", "Assume ..."), what a wh-question presupposes ("How does the temperature, from
#: 20 °C to 60 °C, affect ...?", "To what extent ... between 1959 and 1961?") and a negated bound ("does not exceed 5 m"
#: states a bound). Data only: nothing is evaluated.
CONTEXT_RULE = "statement-context"
CONTEXT_STATEMENT = "statement"
CONTEXT_QUESTION = "question"
CONTEXT_NEGATION = "negation"
CONTEXT_ALTERNATIVE = "alternative"
CONTEXT_EXAMINED = "examined"
CONTEXT_REQUIREMENT = "requirement"
CONTEXT_LIMIT = "limit"
CONTEXTS = (CONTEXT_STATEMENT, CONTEXT_QUESTION, CONTEXT_NEGATION, CONTEXT_ALTERNATIVE, CONTEXT_EXAMINED, CONTEXT_REQUIREMENT, CONTEXT_LIMIT)
#: How a message names each context that is not a statement.
CONTEXT_WORDS = {CONTEXT_QUESTION: "in a yes/no question", CONTEXT_NEGATION: "under a negation", CONTEXT_ALTERNATIVE: "as one of alternatives",
                 CONTEXT_EXAMINED: "inside a claim the answer must examine", CONTEXT_REQUIREMENT: "as a requirement on the answer",
                 CONTEXT_LIMIT: "as the value of a limit or target set on a quantity"}

_NUMBER_WORDS_ALT = "|".join(sorted(set(_TENS) | set(_UNITS) | {"hundred", "thousand", "dozen"}, key=len, reverse=True))
#: The end of a sentence (as for a target: a full stop, question or exclamation mark before a space, a quote or bracket,
#: or the text's end; or a line break).
_SENTENCE_END_RE = _TARGET_END_RE
#: Labels, quotes and discourse words before a sentence's first word ("(a)", "[3]", "Q2.", "Please", "So,").
_SENTENCE_LEAD_RE = re.compile(r"(?:\s+|[\"'‘’“”«»¿¡*•]+|[-–—]\s|\[[^\]\n]{0,16}\]|\([^)\n]{0,6}\)|(?:\d{1,3}|[a-z]|[ivx]{1,4})[.)](?=\s)"
                               r"|(?:Q|Question|Part|Task|Step)\s*\d{1,3}[a-z]?\s*[.:)](?=\s)"
                               r"|(?:please|so|and|but|then|now|also|finally|next|lastly|well|ok|okay|first|second|third)\b,?)+", re.IGNORECASE)
#: Within a sentence, what bounds a figure's clause for a negation: a semicolon, a colon, a bracket, a dash, "but", or a
#: comma before a conjunction or a relative word.
_SEGMENT_RE = re.compile(r"[;:()\[\]—]|\s–\s|,\s*(?=(?:but|and|or|while|whereas|although|though|because|since|so|yet|which|who|whom|whose|where|when|"
                         r"unless|except|however)\b)|\bbut\b", re.IGNORECASE)
#: A negator: a negative word, or a verb or a frame that denies what follows it ("fails to mention", "denies that", "It is
#: false that"); never a verb whose object is a count of its own ("omits 3 rows" states the 3 rows it omits).
_NEGATOR_RE = re.compile(r"\b(?:not|never|no|none|neither|nor|nobody|nothing|nowhere|without|cannot|fail(?:s|ed|ing)?\s+to|neglect(?:s|ed|ing)?\s+to|"
                         r"refus(?:e|es|ed|ing)\s+to|den(?:y|ies|ied|ying)\s+that|(?:false|untrue|incorrect|mistaken)\s+that)\b|n['’]t\b", re.IGNORECASE)
#: A negator that only negates a bound right before a figure ("no more than 80", "does not exceed 5 m", "never exceeds
#: 6000 euros"): the figure is then stated as a bound, which rule same-quantity reads as one.
_NEGATED_BOUND_RE = re.compile(r"(?:not|no|never|cannot|n['’]t)\s+(?:(?:be|go|rise|fall|get|to)\s+)?(?:(?:more|less|fewer|greater|higher|lower|bigger|"
                               r"larger|smaller|longer|shorter|later|earlier|older|younger|sooner)\s+than|over|under|above|below|beyond|exceed(?:s|ing|ed)?|"
                               r"surpass(?:es|ing)?)\s+(?:a\s+|an\s+|the\s+)?[$€£¥]?\s*(?=\d|(?:" + _NUMBER_WORDS_ALT + r")\b)", re.IGNORECASE)
#: An embedded yes/no question before a figure: "whether", or "if" after a verb of asking or deciding.
_EMBEDDED_QUESTION_RE = re.compile(r"\bwhether\b|\b(?:ask|asks|asked|asking|determine|decide|check|see|know|say|state|explain|discuss|evaluate|assess|"
                                   r"establish|investigate|examine|tell|judge|confirm|wonder|question|verify|show|find\s+out|work\s+out)\s+if\b", re.IGNORECASE)
#: The words a wh-question opens with (English, Spanish, French), after any preposition ("To what extent", "In what ways").
_WH_WORDS = frozenset(("what which who whom whose when where why how qué quién quiénes cuál cuáles cuándo dónde cómo cuánto cuánta cuántos cuántas "
                       "que qui quel quelle quels quelles quand où pourquoi comment combien").split())
_QUESTION_SKIP = frozenset("to in by for from at on with of under over within during after before since until apart and but so then por".split())
#: A claim the answer must examine: "the claim that ...", "the view that ...", "(dis)agree that ...".
_EXAMINED_RE = re.compile(r"\b(?:the|this|that|a|an)\s+(?:claim|view|statement|argument|assertion|suggestion|hypothesis|contention|proposition|idea|"
                          r"opinion|interpretation|thesis|belief|notion)\s+that\b|\b(?:agree|disagree)\s+(?:with\s+the\s+view\s+)?that\b", re.IGNORECASE)
_CLAIM_NOUN = (r"(?:view|views|claim|claims|statement|statements|quotation|quote|assertion|argument|proposition|idea|opinion|interpretation|"
               r"judgement|judgment|contention|hypothesis|suggestion|thesis|verdict)")
_CLAIM_REF = r"(?:this|that|the|these|those)\s+" + _CLAIM_NOUN
#: A sentence that puts the sentence (or the quotation) before it up for the answer to examine: "Discuss.", "Discuss this
#: view.", "Discuss with reference to two works.", "Do you agree?", "To what extent do you agree?", "How far is this view
#: valid?", "Evaluate this claim.", "Is this statement justified?". A sentence that gives the answer a topic ("Discuss the
#: role of the workers.") is none.
_EXAMINE_PROMPT_RE = re.compile(
    r"(?:(?:critically\s+)?(?:discuss|evaluate|assess|examine|comment(?:\s+on)?)(?:\s+" + _CLAIM_REF + r")?"
    r"(?:\s*,?\s+(?:with\s+reference\s+to|in\s+relation\s+to|referring\s+to|in\s+the\s+light\s+of|drawing\s+on)\b.*)?"
    r"|(?:(?:to\s+what\s+extent|how\s+far)\s+(?:do|would|does|did|can)\s+you\s+(?:agree|disagree)|(?:do|would)\s+you\s+(?:agree|disagree)|"
    r"(?:to\s+what\s+extent|how\s+far)\s+(?:is|was|are|were|does|do|can|could)\s+" + _CLAIM_REF + r"|(?:is|was|are|were)\s+" + _CLAIM_REF
    + r"\s+(?:valid|justified|correct|accurate|true|fair|convincing|supported|reasonable|persuasive|right)|how\s+(?:valid|justified|accurate|"
    r"convincing|fair|true|far\s+true)\s+(?:is|was|are|were)\s+" + _CLAIM_REF + r")\b.*)", re.IGNORECASE | re.DOTALL)
#: A sentence that opens with an instruction to examine what follows it: "Discuss: ...", "Evaluate: ...".
_EXAMINE_LEAD_RE = re.compile(r"(?:critically\s+)?(?:discuss|evaluate|assess|examine)\s*:", re.IGNORECASE)
#: Opening and closing quotation marks, for a quotation an examination prompt follows.
_QUOTE_PAIRS = (("“", "”"), ("«", "»"), ('"', '"'))
#: A number of rule statement-context's reading of alternatives (digits, a currency sign before them, or number words).
_ALT_NUM_RE = re.compile(r"(?<![\w.])(?:[$€£¥]\s*)?(?:\d+(?:,\d{3})*(?:\.\d+)?|(?:" + _NUMBER_WORDS_ALT + r")\b)", re.IGNORECASE)
#: What joins two alternatives: up to three words of the first (its unit or noun), "or", and an article before the second
#: ("3 or 4", "3 workers or 4 workers", "1833 or 1834"); after a comma, only "or" with a hedge ("3 workers, or perhaps 4"):
#: ", or" alone restates the same quantity another way ("$0.30 per litre, or $31.50 million per year"), which states both.
_ALT_WORDS = r"(?:\s*(?:%|per\s+cent|[^\W\d_][\w'’°-]*)){0,3}"
_ALT_HEDGE = r"(?:else|perhaps|maybe|possibly|even|about|around|roughly|approximately)\s+"
_ALT_OR_RE = re.compile(_ALT_WORDS + r"\s+or\s+(?:" + _ALT_HEDGE + r")?(?:a\s+|an\s+|the\s+)?[$€£¥]?\s*", re.IGNORECASE)
_ALT_OR_HEDGED_RE = re.compile(_ALT_WORDS + r"\s*,\s*or\s+" + _ALT_HEDGE + r"(?:a\s+|an\s+|the\s+)?[$€£¥]?\s*", re.IGNORECASE)
#: "either" before the first alternative: then ", or" joins alternatives too ("either 3 workers, or 4").
_ALT_EITHER_RE = re.compile(r"\beither\s+(?:a\s+|an\s+|the\s+)?$", re.IGNORECASE)
_ALT_OR_EITHER_RE = re.compile(_ALT_WORDS + r"\s*,?\s+or\s+(?:" + _ALT_HEDGE + r")?(?:a\s+|an\s+|the\s+)?[$€£¥]?\s*", re.IGNORECASE)
#: Auxiliary verbs a yes/no question opens with.
_AUXILIARIES = frozenset("""is are was were am do does did can could will would should shall has have had may might must isn't aren't wasn't
    weren't don't doesn't didn't can't couldn't won't wouldn't shouldn't hasn't haven't hadn't""".split())
#: A yes/no clause after a comma in a question ("..., is it 3?", "..., or are there 4?").
_TAG_CLAUSE_RE = re.compile(r",\s*(?:or\s+)?(?:is|was|are|were|does|do|did|has|have|had|can|could|will|would)\s+(?:it|there|that|this|he|she|they)\b",
                            re.IGNORECASE)
_CLAUSE_LEAD_SKIP = frozenset("and or but so then yet".split())
#: Verbs of an instruction (base forms; never a verb of supposition such as assume, suppose, consider, take, let).
_INSTRUCTION_VERBS = frozenset("""aim analyse analyze annotate answer apply argue assess calculate choose cite classify comment compare complete
    compose compute construct contrast copy create deduce define demonstrate derive describe design determine develop discuss distinguish draft draw
    edit ensure estimate evaluate examine explain explore express find formulate give highlight identify illustrate include indicate interpret
    investigate justify keep label limit list make mention name note offer outline pick plan plot predict present produce prove provide quote rank
    read recommend refer relate reply respond restrict review rewrite select show sketch solve spend state suggest summarise summarize support
    trace translate try underline use verify write""".split())
#: Words that open a leading adverbial before an instruction ("In one paragraph of 200 words, outline ...", "For that
#: student, write ...", "Using the data, find ...", "If ..., find ...").
_LEADING_ADVERBIAL = frozenset("in for using with on by as based from after before given when if once to without within following".split())
#: What may stand between an instruction's verb and the figure that counts its object ("Write no more than 80 words",
#: "Use 3 quotations", "Answer in about 250 words", "Write an 80-word answer").
_FILLER = (r"(?:a|an|your|in|to|of|for|with|using|within|between|about|around|approximately|roughly|exactly|precisely|only|just|some|up|at|least|most|"
           r"no|not|more|less|fewer|than|under|over|below|above|maximum|minimum|max|min|total|and|or|each|it|this|them)")
_FILLER_ONLY_RE = re.compile(r"(?:\s+" + _FILLER + r"\b)*\s*", re.IGNORECASE)
_BOUND_ALT = "|".join(sorted((re.escape(p).replace(r"\ ", r"\s+") for p in _BOUND_BEFORE), key=len, reverse=True))
_APPROX_ALT = r"about|around|approximately|roughly|exactly|precisely|only|just|some|up\s+to"
#: Units of the answer's own length and precision, read right after a figure ("80 words", "an 80-word answer", "3
#: significant figures", "2 d.p.").
_LENGTH_UNIT_RE = re.compile(r"\s*(?:-\s*)?(?:words?|pages?|characters?)\b", re.IGNORECASE)
_PRECISION_UNIT_RE = re.compile(r"\s*(?:significant\s+fig(?:ure)?s?|sig\.?\s*figs?|s\.\s?f\.?|sf\b|decimal\s+places?|d\.\s?p\.?|dp\b)", re.IGNORECASE)
#: What a figure of the answer's length or precision is stated with in an instruction: "in (no more than) 350 words", "a
#: paragraph of (no more than) 200 words", "(no more than / about) 80 words", "to 3 significant figures", "limit your answer
#: to 80 words".
_SIZE_TAIL = r"(?:(?:" + _BOUND_ALT + r"|" + _APPROX_ALT + r")\s+)?(?:a\s+|an\s+)?$"
_LENGTH_BEFORE_RE = re.compile(r"(?:\b(?:in|within)\s+" + _SIZE_TAIL + r"|\b(?:paragraph|response|answer|essay|commentary|summary|piece|reply|account|"
                               r"explanation|analysis|outline|description)s?\s+of\s+" + _SIZE_TAIL + r"|\b(?:limit|keep|restrict|cap|reduce|cut|shorten|trim)"
                               r"\b[^.?!\n]{0,40}\bto\s+" + _SIZE_TAIL + r"|(?:\b(?:" + _BOUND_ALT + r"|" + _APPROX_ALT + r")\s+$)|\b(?:an?)\s+$)", re.IGNORECASE)
_PRECISION_BEFORE_RE = re.compile(r"\bto\s+(?:within\s+)?$|\b(?:in|with)\s+$", re.IGNORECASE)
#: Who an obligation is set on when it is a requirement on the answer.
_ANSWER_SUBJECT_RE = re.compile(r"\b(?:your|you|answers?|responses?|repl(?:y|ies)|essays?|paragraphs?|commentar(?:y|ies)|summar(?:y|ies)|submissions?|"
                                r"students?|candidates?)\b", re.IGNORECASE)
_OBLIGATION_RE = re.compile(r"\b(?:should|must|shall|ought\s+to|needs?\s+to|has\s+to|have\s+to|(?:is|are)\s+(?:to|required\s+to|expected\s+to|supposed\s+to|"
                            r"limited\s+to|restricted\s+to)|will\s+need\s+to|(?-i:may)|can|cannot)\b|\b(?:can|mustn|shouldn)['’]t\b", re.IGNORECASE)
#: What an answer may be required to do with a figure after an obligation ("should be 80 words long", "must contain 3
#: quotations", "may use up to 3 sources").
_PREDICATE_RE = re.compile(r"\s+(?:not\s+|never\s+)?(?:be|have|contain|include|use|write|give|quote|cite|provide|make|offer|present|list|name|identify|"
                           r"refer\s+to|run\s+to|exceed|total|stay|remain|fit|consist\s+of|number|answer|respond|reply|discuss|mention|cover|address|"
                           r"explain|describe|state|show|find|calculate|determine|reach)\b", re.IGNORECASE)
#: A limit set on a quantity: "the word limit is 80 words", "a limit of 80", "Maximum 80 words", "an 80-word limit", "80
#: words maximum", "limited to 80 words".
_LIMIT_NOUN = r"(?:limit|limits|maximum|minimum|max|min|cap|ceiling|quota|allowance|requirement|requirements|target)"
_LIMIT_BEFORE_RE = re.compile(r"(?:\b" + _LIMIT_NOUN + r"\.?(?:\s+(?:for|on|of)\s+(?:the\s+|each\s+|your\s+|this\s+|every\s+)?[\w-]+)?\s*(?:is|are|was|were|:|=|"
                              r"of|at|set\s+at)?|\b(?:limited|restricted|capped)\s+to)" + r"(?:\s+" + _FILLER + r"\b)*\s*$", re.IGNORECASE)
_LIMIT_AFTER_RE = re.compile(r"\s*(?:-\s*)?(?:words?\s*)?" + _LIMIT_NOUN + r"\b", re.IGNORECASE)
#: Words of a premise's own statement that name a requirement or a limit: such a premise may state a requirement's figure
#: ("the word limit is 80 words", "the answer must have at most 80 words", "the required length is 80 words").
_REQUIREMENT_NAME_RE = re.compile(r"\b(?:limit|limits|maximum|minimum|max|min|cap|ceiling|quota|allowance|requirement|requirements|required|requires|require|"
                                  r"must|should|shall|needs?\s+to|allowed|permitted|target|specified|stipulated|asks|asked|instructed|prescribed|demanded)\b",
                                  re.IGNORECASE)


#: A figure that counts things after an instruction's verb: a plural noun after it, maybe after one adjective ("3 reasons",
#: "2 decimal places", "3 consecutive integers"), or an "N-word" compound ("an 80-word answer"); never a measure (a unit
#: the STEM unit reader reads, a currency or a calendar span) or an operand ("Calculate 5% of 300", "Solve 3x + 2 = 8").
_COUNTED_AFTER_RE = re.compile(r"\s+(?:[a-z]+\s+)?([a-z]{3,}s)\b", re.IGNORECASE)
_HYPHEN_COUNT_RE = re.compile(r"\s*-\s*[a-z]{3,}\b", re.IGNORECASE)
_MEASURE_WORDS = frozenset("year week month decade century centurie euro dollar pound cent penny pence franc rupee peso yuan percent".split())


def _counts_things(text: str, end: int) -> bool:
    m = _COUNTED_AFTER_RE.match(text, end)
    if m is None:
        return bool(_HYPHEN_COUNT_RE.match(text, end))
    noun = m.group(1)
    return _unit_dim(noun) is None and _norm_marker(noun) not in _MEASURE_WORDS and noun.casefold()[:-1] not in _MEASURE_WORDS


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """The sentences of ``text``: ``(start, end, mark)`` with ``mark`` the end mark ('.', '?', '!', or '' for a line break
    or the text's end); the mark itself belongs to no sentence."""
    out: list[tuple[int, int, str]] = []
    pos = 0
    for m in _SENTENCE_END_RE.finditer(text):
        out.append((pos, m.start(), m.group(0) if m.group(0) != "\n" else ""))
        pos = m.end()
    if pos < len(text):
        out.append((pos, len(text), ""))
    return out


_WORD_TOKEN_RE = re.compile(r"[^\W\d_][\w'’-]*")


def _lead_end(text: str, start: int, end: int) -> int:
    """Where a sentence's first word starts: after its labels, quotes and discourse words."""
    m = _SENTENCE_LEAD_RE.match(text, start, end)
    return m.end() if m else start


def _first_word(text: str, start: int, end: int) -> tuple[str, int, int]:
    m = _WORD_TOKEN_RE.search(text, start, end)
    return (m.group(0).casefold(), m.start(), m.end()) if m else ("", end, end)


_THEN_VERB_RE = re.compile(r"(?:,|;|\band\b|\bthen\b)\s*(?:then\s+)?([^\W\d_][\w'’-]*)", re.IGNORECASE)


def _instruction_starts(text: str, s: int, e: int) -> list[int]:
    """The positions in the sentence ``[s, e)`` where an instruction's verb starts: its first word, or the first word after
    a leading adverbial's comma ("In one paragraph of 200 words, outline ..."), when that word is a verb of
    :data:`_INSTRUCTION_VERBS`; then any such verb after a comma, a semicolon, "and" or "then" within the instruction.
    Empty for a sentence that is no instruction."""
    i = _lead_end(text, s, e)
    word, a, b = _first_word(text, i, e)
    starts: list[int] = []
    if word in _INSTRUCTION_VERBS:
        starts.append(a)
    elif word in _LEADING_ADVERBIAL:
        comma = text.find(",", b, e)
        if comma != -1:
            w2, a2, _b2 = _first_word(text, comma + 1, e)
            if w2 in _INSTRUCTION_VERBS and not text[comma + 1:a2].strip():
                starts.append(a2)
    if not starts:
        return []
    for m in _THEN_VERB_RE.finditer(text, starts[0], e):
        if m.group(1).casefold() in _INSTRUCTION_VERBS:
            starts.append(m.start(1))
    return sorted(set(starts))


def _scope_start(text: str, s: int, start: int) -> int:
    """Where the part of the sentence that holds the figure starts: after the last semicolon or colon before it."""
    scope = s
    for m in re.finditer(r"[;:]", text[s:start]):
        scope = s + m.end()
    return scope


def _question_kind(text: str, scope: int, figure_start: int) -> str:
    """'wh' when the question that holds the figure opens with a wh-word (after any preposition: "To what extent", "In
    what ways"); 'yes/no' otherwise."""
    i = _lead_end(text, scope, figure_start)
    for m in _WORD_TOKEN_RE.finditer(text, i, figure_start + 1):
        w = m.group(0).casefold()
        if w in _QUESTION_SKIP:
            continue
        return "wh" if w in _WH_WORDS else "yes/no"
    return "yes/no"


def _clause(text: str, s: int, e: int, start: int, end: int) -> tuple[int, int]:
    """The clause of the sentence ``[s, e)`` that holds the figure at ``[start, end)``, bounded by :data:`_SEGMENT_RE`."""
    a, b = s, e
    for m in _SEGMENT_RE.finditer(text, s, e):
        if m.end() <= start:
            a = m.end()
        elif m.start() >= end:
            b = m.start()
            break
    return a, b


def _negated(text: str, a: int, b: int) -> Optional[str]:
    """The negator of ``text[a:b]`` that negates more than a bound right before a figure (None when none does)."""
    for m in _NEGATOR_RE.finditer(text, a, b):
        if _NEGATED_BOUND_RE.match(text, m.start()):
            continue
        return m.group(0)
    return None


#: Words a negation's predicate starts with that say nothing of it ("are not mentioned", "has no uncertainty").
_NEGATION_SKIP = frozenset("be been being is are was were am do does did have has had a an the any at all only yet ever quite so as very entirely "
                           "fully really always one of more than".split())


def _stem(word: str) -> str:
    """A word reduced for comparing predicates: case folded, a plural, past or -ing ending dropped ("mentioned" and
    "mentions" are "mention")."""
    w = word.casefold().strip("'’")
    for suf in ("ings", "ing", "ied", "ies", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def _negated_words(text: str, a: int, b: int) -> tuple[str, ...]:
    """What the negators of ``text[a:b]`` negate: the first content word after each (stemmed), a negated bound aside."""
    out: list[str] = []
    for m in _NEGATOR_RE.finditer(text, a, b):
        if _NEGATED_BOUND_RE.match(text, m.start()):
            continue
        for w in _WORD_TOKEN_RE.finditer(text, m.end(), b):
            if w.group(0).casefold() in _NEGATION_SKIP:
                continue
            out.append(_stem(w.group(0)))
            break
    return tuple(dict.fromkeys(out))


def _alternative(text: str, a: int, b: int, start: int, end: int) -> bool:
    """Whether the figure at ``[start, end)`` is one of alternatives in its sentence ``[a, b)``: joined by "or" to another
    number, with at most three words of the first between them ("3 or 4", "3 workers or 4 workers", "either 3 or 4", "3
    workers, or perhaps 4"). The source then states neither as the quantity's value."""
    nums = [(m.start(), m.end()) for m in _ALT_NUM_RE.finditer(text, a, b)]  # within the figure's sentence: "3 workers, or perhaps 4"
    for (s1, e1), (s2, e2) in zip(nums, nums[1:]):
        either = bool(_ALT_EITHER_RE.search(text[max(a, s1 - 12):s1]))
        joined = (_ALT_OR_RE.fullmatch(text, e1, s2) or _ALT_OR_HEDGED_RE.fullmatch(text, e1, s2)
                  or (either and _ALT_OR_EITHER_RE.fullmatch(text, e1, s2)))
        if joined and any(x < end and start < y for x, y in ((s1, e1), (s2, e2))):
            return True
    return False


def _clause_question(text: str, s: int, a: int, start: int) -> bool:
    """Whether the figure at ``start`` stands in a yes/no clause of a question: its clause (from ``a``, a clause after the
    sentence's start at ``s``) opens with an auxiliary verb ("..., or is it 3?", "... — does it name 3?"), or a comma before
    it opens one ("..., is it 3?")."""
    if a > s:
        for m in _WORD_TOKEN_RE.finditer(text, _lead_end(text, a, start), start):
            w = m.group(0).casefold()
            if w in _CLAUSE_LEAD_SKIP:
                continue
            if w in _AUXILIARIES:
                return True
            break
    return bool(_TAG_CLAUSE_RE.search(text, s, start))


def _is_prompt(text: str, s: int, e: int) -> bool:
    """Whether the sentence ``[s, e)`` is an examination prompt (:data:`_EXAMINE_PROMPT_RE`)."""
    i = _lead_end(text, s, e)
    body = text[i:e].strip().rstrip("\"'”’»)").strip()
    return bool(body) and bool(_EXAMINE_PROMPT_RE.fullmatch(body))


_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")


def _next_sentence(spans: list[tuple[int, int, str]], i: int, text: str) -> Optional[tuple[int, int, str]]:
    """The sentence after ``spans[i]`` in its paragraph (None when a blank line comes first)."""
    end = spans[i][1]
    for sp in spans[i + 1:]:
        body = text[sp[0]:sp[1]]
        lead = len(body) - len(body.lstrip())
        if _BLANK_LINE_RE.search(text, end, sp[0] + lead):
            return None
        if body.strip(" \t\n\"'”’»"):
            return sp
    return None


def _examined_by_prompt(text: str, spans: list[tuple[int, int, str]], i: int, start: int) -> bool:
    """Whether the figure at ``start``, in the sentence ``spans[i]``, is put up for examination by a prompt that follows:
    its sentence opens with "Discuss:" or "Evaluate:"; the next sentence of its paragraph is a prompt ("The extract
    mentions 3 workers. To what extent do you agree?"); or it stands in a quotation that a prompt follows ('"... 3 workers
    ..." Discuss.')."""
    s, e, _mark = spans[i]
    if _EXAMINE_LEAD_RE.match(text, _lead_end(text, s, e)):
        return True
    nxt = _next_sentence(spans, i, text)
    if nxt is not None and _is_prompt(text, nxt[0], nxt[1]):
        return True
    para = max((m.end() for m in _BLANK_LINE_RE.finditer(text, 0, start)), default=0)
    for opener, closer in _QUOTE_PAIRS:
        o = text.rfind(opener, para, start)
        if o == -1:
            continue
        if opener == closer:
            if text.count(opener, para, start) % 2 == 0:
                continue
        elif text.rfind(closer, o, start) != -1:
            continue
        c = text.find(closer, start)
        if c == -1 or _BLANK_LINE_RE.search(text, start, c):
            continue
        j = bisect.bisect_right([sp[0] for sp in spans], c) - 1
        k = j if j >= 0 and spans[j][0] <= c < spans[j][1] else j
        for sp in spans[max(k, 0):max(k, 0) + 2]:
            a2 = max(sp[0], c + 1)
            if a2 < sp[1] and text[a2:sp[1]].strip(" \t.,;:") and _is_prompt(text, a2, sp[1]):
                return True
    return False


def _size_of_answer(before: str, after: str) -> bool:
    """Whether a figure states the answer's length ("in no more than 350 words", "a paragraph of 200 words", "about 250
    words", "an 80-word answer", "limit your answer to 80 words") or precision ("to 3 significant figures")."""
    return ((bool(_LENGTH_UNIT_RE.match(after)) and bool(_LENGTH_BEFORE_RE.search(before)))
            or (bool(_PRECISION_UNIT_RE.match(after)) and bool(_PRECISION_BEFORE_RE.search(before))))


def _limit(text: str, s: int, e: int, start: int, end: int) -> bool:
    """Whether the figure at ``[start, end)`` of the sentence ``[s, e)`` is stated as the value of a limit or target set on a
    quantity ("the word limit is 80 words", "a limit of 80", "Maximum 80 words", "an 80-word limit", "limited to 80
    words", "its target of 2 per cent")."""
    return bool(_LIMIT_BEFORE_RE.search(text[s:start]) or _LIMIT_AFTER_RE.match(text[end:e]))


def _requirement(text: str, s: int, e: int, start: int, end: int) -> bool:
    """Whether the figure at ``[start, end)`` of the sentence ``[s, e)`` is stated as a requirement on the answer: in an
    instruction, the count of the instruction's object or the answer's length or precision; or what an obligation set on
    the answer (or its writer) requires."""
    before, after = text[s:start], text[end:e]
    instruction = _instruction_starts(text, s, e)
    starts = [p for p in instruction if p < start]
    if starts:
        verb_end = _WORD_TOKEN_RE.match(text, starts[-1]).end()
        if _FILLER_ONLY_RE.fullmatch(text, verb_end, start) and _counts_things(text, end):
            return True  # the figure counts the instruction's object: "Give 3 reasons", "Write 80 words"
    if instruction and _size_of_answer(before, after):
        return True  # the answer's length or precision: "in no more than 350 words", "In one paragraph of 200 words, outline"
    subject = _ANSWER_SUBJECT_RE.search(before)
    if subject:
        for ob in _OBLIGATION_RE.finditer(before, subject.end()):
            pm = _PREDICATE_RE.match(before, ob.end())
            tail = pm.end() if pm else ob.end()
            if not _FILLER_ONLY_RE.fullmatch(before, tail):
                continue
            verb = pm.group(0).split()[-1].casefold() if pm else ""
            if verb == "be" or not pm or _counts_things(text, end):
                return True  # "Your answer should be 80 words long", "must contain 3 quotations"
        if _OBLIGATION_RE.search(before, subject.end()) and _size_of_answer(before, after):
            return True
    return False


def _context_in(text: str, spans: list[tuple[int, int, str]], start: int, end: int) -> tuple[str, str, tuple[str, ...]]:
    """:func:`figure_context` with the sentences of ``text`` given, and what a negation after the figure in its clause
    negates (:func:`_negated_words`)."""
    i = bisect.bisect_right([sp[0] for sp in spans], start) - 1
    if i < 0:
        return CONTEXT_STATEMENT, "", ()
    s, e, mark = spans[i]
    if not s <= start < max(e, start + 1):
        return CONTEXT_STATEMENT, "", ()
    e = max(e, end)
    sentence = " ".join(text[s:e].split())
    phrase = sentence if len(sentence) <= 120 else sentence[:117] + "..."
    scope = _scope_start(text, s, start)
    a, b = _clause(text, s, e, start, end)
    after = _negated_words(text, end, b)
    # a question's own part of its sentence starts after the last semicolon or colon before its question mark: "The extract
    # mentions 3 workers; which of them speaks?" states 3 workers, and asks only which of them speaks
    if mark == "?" and start >= _scope_start(text, s, e) and (_question_kind(text, scope, start) == "yes/no" or _clause_question(text, scope, a, start)):
        return CONTEXT_QUESTION, phrase, after
    if _EMBEDDED_QUESTION_RE.search(text, scope, start):
        return CONTEXT_QUESTION, phrase, after
    if _negated(text, a, start) is not None:
        return CONTEXT_NEGATION, phrase, after
    if _alternative(text, s, e, start, end):
        return CONTEXT_ALTERNATIVE, phrase, after
    if _EXAMINED_RE.search(text, scope, start) or _examined_by_prompt(text, spans, i, start):
        return CONTEXT_EXAMINED, phrase, after
    if _requirement(text, s, e, start, end):
        return CONTEXT_REQUIREMENT, phrase, after
    if _limit(text, s, e, start, end):
        return CONTEXT_LIMIT, phrase, after
    return CONTEXT_STATEMENT, (phrase if after else ""), after


def figure_context(text: str, start: int, end: int) -> tuple[str, str]:
    """Rule ``statement-context``: ``(context, phrase)`` of the figure written at ``[start, end)`` of ``text``: one of
    :data:`CONTEXTS`, read in this order (a yes/no question, a yes/no clause of a question or an embedded question; a
    negation before the figure in its clause; one of alternatives joined by "or"; a claim the answer must examine, named
    as one or put up by a prompt that follows it; a requirement on the answer; the value of a limit; else a statement),
    and its sentence (empty for a statement). Data only: nothing is evaluated."""
    text = text or ""
    context, phrase, _after = _context_in(text, _sentence_spans(text), start, end)
    return context, phrase


def figure_negates(text: str, start: int, end: int) -> tuple[str, ...]:
    """Rule ``statement-context``: what a negation AFTER the figure written at ``[start, end)`` of ``text``, in its clause,
    negates (stemmed words; a negated bound aside). A premise whose own statement says one of them is not stated so."""
    text = text or ""
    return _context_in(text, _sentence_spans(text), start, end)[2]


@dataclass(frozen=True)
class _Occurrence:
    """One place where a text states a figure: its position, the values it states, the quantity it names (a unit or a
    counted noun, normalised; None for a bare figure) and whether it states it as a bound. A figure written in a cell of
    a table (rule ``table-cells``) also names the quantity of its column (``quantity``: the column header's unit and
    words; ``column``: the header as written) and the row its first cell names (``row``)."""
    start: int
    end: int
    values: frozenset
    marker: Optional[str]
    bound: bool
    quantity: frozenset = frozenset()
    column: Optional[str] = None
    row: Optional[str] = None
    #: Rule ``statement-context``: how the text states the figure (:data:`CONTEXTS`), the sentence that shows it, and what
    #: a negation after the figure in its clause negates (stemmed words: a premise saying one is not stated so).
    context: str = CONTEXT_STATEMENT
    phrase: str = ""
    negates: tuple = ()

    @property
    def bare(self) -> bool:
        """Stated with no quantity a check reads: no marker after it and no table column."""
        return self.marker is None and not self.quantity

    def names(self) -> list[str]:
        """The quantity names this occurrence states its figure with: its marker, then its column's unit and words."""
        return ([self.marker] if self.marker is not None else []) + sorted(self.quantity)


#: Rule ``table-cells`` (the fourth repair of the translator merge, decision 56): a figure written in a cell of a table
#: (two or more consecutive lines of the same number, two or more, of cells separated by ``|``; the first line is the
#: header, and a Markdown rule line such as ``|---|---|`` is skipped) is stated for the quantity its column's header names
#: (the header's unit, in its last brackets or after its last ``/``, and the header's words) in the row its first cell
#: names. Without it every table cell is a bare figure, which names no quantity, so no check could read a table's data.
TABLE_RULE = "table-cells"
_TABLE_RULE_LINE_RE = re.compile(r"\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?")
_HEADER_UNIT_RE = re.compile(r"\(([^()]*)\)\s*$|/\s*([^/()]+?)\s*$")
_SCALE_LEAD_RE = re.compile(r"^(?:hundred|thousand|million|billion)s?\s+", re.IGNORECASE)


@dataclass(frozen=True)
class _Cell:
    """A data cell of a table (rule ``table-cells``): its span, its column's quantity names and header, and its row's
    label (the row's first cell; None for a cell of the first column)."""
    start: int
    end: int
    quantity: frozenset
    column: str
    row: Optional[str]


def _row_cells(offset: int, line: str) -> Optional[list[tuple[int, int, str]]]:
    """The cells of one table line (``|`` separated; a leading or trailing ``|`` opens or closes the row): ``(start, end,
    text)`` with positions in the whole text, or None for a line of fewer than two cells."""
    if "|" not in line:
        return None
    parts = line.split("|")
    cells: list[tuple[int, int, str]] = []
    pos = 0
    for i, part in enumerate(parts):
        a = pos
        pos += len(part) + 1
        text = part.strip()
        if not text and i in (0, len(parts) - 1):
            continue
        lead = len(part) - len(part.lstrip())
        cells.append((offset + a + lead, offset + a + lead + len(text), text))
    return cells if len(cells) >= 2 else None


def _header_quantity(header: str) -> frozenset:
    """The quantity names a column header gives (rule ``table-cells``): its words that may name a quantity, and its unit
    (the text in its last brackets, or after its last ``/``) read as a figure's marker is read: a currency sign as its
    currency, a scale word skipped ("(million litres per year)" names litres)."""
    names = set(_statement_words(header))
    m = _HEADER_UNIT_RE.search(header)
    unit_text = ((m.group(1) or m.group(2) or "") if m else "").strip()
    unit_text = _SCALE_LEAD_RE.sub("", unit_text)
    if unit_text[:1] in _CURRENCY_BEFORE:
        names.add(_CURRENCY_BEFORE[unit_text[:1]])
    elif unit_text:
        pm = _PERCENT_AFTER_RE.match(" " + unit_text)
        tm = _MARKER_TOKEN_RE.match(" " + unit_text)
        if pm:
            names.add("%")
        elif tm and tm.group(1).strip("'’-"):
            names.add(tm.group(1).strip("'’-"))
    return frozenset(n for n in names if n)


def _table_cells(text: str) -> list[_Cell]:
    """Every data cell of every table written in ``text`` (rule ``table-cells``), with its column's quantity and its row's
    label. Data only: nothing is evaluated."""
    lines: list[tuple[int, str]] = []
    pos = 0
    for line in (text or "").split("\n"):
        lines.append((pos, line))
        pos += len(line) + 1
    out: list[_Cell] = []
    i = 0
    while i < len(lines):
        header = _row_cells(*lines[i])
        if header is None:
            i += 1
            continue
        rows: list[list[tuple[int, int, str]]] = []
        j = i + 1
        while j < len(lines):
            if _TABLE_RULE_LINE_RE.fullmatch(lines[j][1].strip()):
                j += 1
                continue
            cells = _row_cells(*lines[j])
            if cells is None or len(cells) != len(header):
                break
            rows.append(cells)
            j += 1
        if not rows:
            i += 1
            continue
        quantities = [_header_quantity(h[2]) for h in header]
        for cells in rows:
            label = cells[0][2]
            for k, (a, b, _t) in enumerate(cells):
                out.append(_Cell(a, b, quantities[k], header[k][2], label if k > 0 else None))
        i = j
    return out


def _norm_marker(raw: str) -> str:
    t = " ".join(raw.strip().split()).strip(".,;:'\"").casefold()
    t = _MARKER_SYNONYMS.get(t, t)
    if t.endswith("s") and len(t) > 3 and not t.endswith("ss"):
        t = t[:-1]
    return _MARKER_SYNONYMS.get(t, t)


def _unit_dim(raw: str) -> Any:
    """The physical dimension of a unit marker as the STEM unit reader reads it (None when it reads none; an ASCII
    exponent is read as a superscript: "cm3" as "cm³")."""
    try:
        from ...stem.units import unit_dimension
        t = raw.strip()
        dim = unit_dimension(t)
        if dim is None:
            m = _ASCII_EXPONENT_RE.search(t)
            if m:
                dim = unit_dimension(t[:m.start()] + (m.group(1) + m.group(2)).translate(_TO_SUPERSCRIPT))
        return dim
    except Exception:
        return None


def same_quantity_marker(a: Optional[str], b: Optional[str]) -> bool:
    """Whether two quantity markers name the same quantity: the same physical dimension when the STEM unit reader reads
    both (``m`` and ``metres``; ``8 s`` is not ``8 m``), else the same word once normalised (case, a plural ``s``, the
    synonyms of per cent, the currencies and the time words)."""
    if a is None or b is None:
        return False
    if FREQUENCY_MARKER in (a, b):
        # a frequency adverb states a number of periods a year (rule frequency-words): the premise names that quantity
        # when it names periods, times, compoundings or payments, or a year, a month, a quarter, a week or a day
        other = b if a == FREQUENCY_MARKER else a
        return other == FREQUENCY_MARKER or _norm_marker(other) in _FREQUENCY_QUANTITY or other.casefold() in _FREQUENCY_QUANTITY
    da, db = _unit_dim(a), _unit_dim(b)
    if da is not None and db is not None:
        return da.same_physical(db)
    return _norm_marker(a) == _norm_marker(b)


def _occurrences(text: str) -> list[_Occurrence]:
    """:func:`_read_occurrences` (memoised per text; a new list each call)."""
    return list(_read_occurrences(text or ""))


@functools.lru_cache(maxsize=512)
def _read_occurrences(text: str) -> tuple[_Occurrence, ...]:
    return tuple(_occurrences_of(text))


def _occurrences_of(text: str) -> list[_Occurrence]:
    """Every place ``text`` states a figure in digits, in number words or as a frequency adverb (rule
    ``frequency-words``), with the quantity it names (:class:`_Occurrence`). Figures stated in other spellings
    (fractions in words, month names, scientific notation, prefixed units) are read by :func:`text_numbers` only. A figure
    in a data cell of a table (rule ``table-cells``) names its column's quantity and its row, and reads no marker beyond
    its cell (the next cell or line is not its unit). Each other figure carries how its sentence states it (rule
    ``statement-context``, :func:`figure_context`); a table's cells are its statements."""
    out: list[_Occurrence] = []
    if not text:
        return out
    cells = _table_cells(text)
    spans = _sentence_spans(text)

    def cell_at(start: int, end: int) -> Optional[_Cell]:
        return next((c for c in cells if c.start <= start and end <= c.end), None) if cells else None

    def occurrence(start: int, end: int, values: set, marker: Optional[str], after: int, bound: bool) -> _Occurrence:
        c = cell_at(start, end)
        if c is None:
            context, phrase, negates = _context_in(text, spans, start, end)  # rule statement-context
            return _Occurrence(start, end, frozenset(values), marker, bound, context=context, phrase=phrase, negates=negates)
        if marker is not None and after > c.end:
            marker = None  # rule table-cells: what follows a cell's figure beyond its cell is another cell or line
        return _Occurrence(start, end, frozenset(values), marker, bound, quantity=c.quantity, column=c.column, row=c.row)

    def marker_after(pos: int) -> tuple[Optional[str], int]:
        pm = _PERCENT_AFTER_RE.match(text, pos)
        if pm:
            return "%", pm.end()
        tm = _MARKER_TOKEN_RE.match(text, pos)
        if not tm:
            return None, pos
        raw = tm.group(1).strip("'’-")
        if not raw or raw.casefold() in _MARKER_SKIP or not any(ch.isalpha() or ch in "°Ωµμ" for ch in raw):
            return None, pos
        return raw, tm.end()

    def bound_before(start: int) -> bool:
        return bool(_BOUND_BEFORE_RE.search(text[max(0, start - 40):start]))

    def currency_before(start: int) -> Optional[str]:
        j = start - 1
        while j >= 0 and text[j] == " ":
            j -= 1
        return _CURRENCY_BEFORE.get(text[j]) if j >= 0 else None

    for m in _NUM_RE.finditer(text):
        whole, dec, denom = m.group(1).replace(",", ""), m.group(2), m.group(3)
        value = Fraction(int(whole)) + (Fraction(int(dec), 10 ** len(dec)) if dec else 0)
        values = {value}
        if denom and int(denom) != 0 and not dec:
            values |= {Fraction(int(whole), int(denom)), Fraction(int(denom))}
        pos = m.end()
        sc = _SCALE_WORD_RE.match(text, pos)
        if sc:
            values.add(value * _SCALES[sc.group(1).lower()])
            pos = sc.end()
        marker, _after = marker_after(pos)
        if marker == "%" and not (cell_at(m.start(), m.end()) and _after > cell_at(m.start(), m.end()).end):
            values.add(value / 100)
        cur = currency_before(m.start())
        out.append(occurrence(m.start(), m.end(), values, marker, _after, bound_before(m.start())) if not cur else
                   occurrence(m.start(), m.end(), values, cur, m.end(), bound_before(m.start())))
    for m in _WORD_RE.finditer(text):
        w, unit = m.group(1).lower(), (m.group(2) or "").lower()
        base = _TENS.get(w, _UNITS.get(w, _OTHER_WORDS.get(w)))
        if base is None:
            continue
        value = Fraction(base) + (Fraction(_UNITS[unit]) if unit and w in _TENS else 0)
        values = {value}
        pos = m.end()
        sc = _SCALE_WORD_RE.match(text, pos)
        if sc:
            values.add(value * _SCALES[sc.group(1).lower()])
            pos = sc.end()
        marker, _after = marker_after(pos)
        if marker == "%" and not (cell_at(m.start(), m.end()) and _after > cell_at(m.start(), m.end()).end):
            values.add(value / 100)
        out.append(occurrence(m.start(), m.end(), values, marker, _after, bound_before(m.start())))
    for m in _FREQUENCY_RE.finditer(text):
        w = m.group(1).lower()
        out.append(occurrence(m.start(), m.end(), {Fraction(_FREQUENCY_WORDS[w])}, FREQUENCY_MARKER, m.end(), False))
    return out


def _states(occ: _Occurrence, v: Fraction) -> bool:
    return v in occ.values or v * 100 in occ.values or (v != 0 and v / 100 in occ.values)


def _premise_statement(premise: Any, problem: Optional[Problem]) -> str:
    """A premise's own statement in words: its ``label`` and the ``meaning`` of every symbol it names."""
    names = set()
    try:
        names = set(_expr_symbols(premise.expr.model_dump(mode="json", exclude_none=True)))
    except Exception:
        pass
    meanings = [s.meaning for s in (problem.symbols if problem is not None else []) if s.name in names and s.meaning]
    return " ; ".join([premise.label or ""] + meanings)


def _figure_relations(expr: Any) -> dict[Fraction, set[str]]:
    """figure -> the comparison operators that relate it in a premise (JSON)."""
    out: dict[Fraction, set[str]] = {}
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("op") in _COMPARE_OPS:
                for side in (node.get("left"), node.get("right")):
                    if isinstance(side, dict) and side.get("op") in ("int", "real"):
                        try:
                            out.setdefault(abs(Fraction(side["value"])), set()).add(node["op"])
                        except (ValueError, ZeroDivisionError, KeyError, TypeError):
                            pass
            stack.extend(v for k, v in node.items() if k != "value")
        elif isinstance(node, list):
            stack.extend(node)
    return out


#: The three readings of a figure of a premise with no located excerpt against its held source (:func:`figure_reading`).
FIGURE_REFUTED = "refuted"
FIGURE_READ = "read"
FIGURE_UNREAD = "unread"


@dataclass(frozen=True)
class FigureReading:
    """What rule ``same-quantity`` reads of one figure of a no-excerpt premise in its held source: ``kind`` is
    :data:`FIGURE_REFUTED` (the source refutes it as its statement of the premise's quantity), :data:`FIGURE_READ` (the
    source states it for the quantity the premise names, as the premise states it: data, though not a transcription, for
    no excerpt was located) or :data:`FIGURE_UNREAD` (neither: a number match only, which is no evidence); ``reason`` says
    why. ``context`` is set when rule ``statement-context`` kept the figure unread: the source states it for the premise's
    quantity, as the premise states it, only in that context (:data:`CONTEXTS`)."""
    kind: str
    reason: str
    context: Optional[str] = None


def _names_quantity(o: _Occurrence, own: list[str]) -> bool:
    """Whether the occurrence ``o`` states its figure for a quantity the premise's statement names (``own``)."""
    return any(same_quantity_marker(m, w) for m in o.names() for w in own)


def _unstated(o: _Occurrence, statement: str) -> Optional[str]:
    """Rule ``statement-context``: None when the occurrence ``o`` states its figure as its source's own statement, for a
    premise whose own statement is ``statement``; else the context that keeps it from doing so (:data:`CONTEXTS`). A
    statement states it, unless a negation after the figure in its clause negates what the premise's statement says ("3
    workers are not mentioned" for "the extract mentions 3 workers"); a requirement or a limit states it only for a premise
    whose statement names a requirement or a limit (their value: "the word limit is 80 words"), never for the quantity it is
    set on ("the answer has 80 words"); a yes/no question, a negation before the figure, one of alternatives and a claim the
    answer must examine never state it."""
    if o.context in (CONTEXT_REQUIREMENT, CONTEXT_LIMIT) and not _REQUIREMENT_NAME_RE.search(statement or ""):
        return o.context
    if o.context in (CONTEXT_QUESTION, CONTEXT_NEGATION, CONTEXT_ALTERNATIVE, CONTEXT_EXAMINED):
        return o.context
    if o.negates and set(o.negates) & {_stem(w) for w in _statement_words(statement or "")}:
        return CONTEXT_NEGATION
    return None


def _stated(o: _Occurrence, statement: str) -> bool:
    """Whether the occurrence ``o`` states its figure as its source's own statement, for a premise whose own statement is
    ``statement`` (:func:`_unstated` gives no context that keeps it from doing so)."""
    return _unstated(o, statement) is None


def _context_extra(ctx: str, o: _Occurrence) -> str:
    """What a message adds to a context that keeps a figure from being its source's statement."""
    if ctx in (CONTEXT_REQUIREMENT, CONTEXT_LIMIT):
        return (", which states only what the quantity must meet, while the premise states the value of the quantity it is set on (its statement names no "
                "requirement or limit)")
    if ctx == CONTEXT_NEGATION and o.context == CONTEXT_STATEMENT:
        return f", which negates what the premise states ({', '.join(o.negates[:3])})"
    if ctx == CONTEXT_ALTERNATIVE:
        return ", which states neither alternative as the quantity's value"
    return ""


def _as_the_premise_states(o: _Occurrence, relations: Optional[set[str]], statement: str) -> bool:
    """Whether the occurrence ``o`` states its figure as the premise relates it (``relations``: the comparisons that relate
    the figure in the premise): a value (``eq``) as a value, or as a bound when the premise's statement names one ("the
    threshold is 6000 euros" for "first exceeds 6000 euros"); a bound (``lt``, ``le``, ``gt``, ``ge``) only as a bound. The
    value of a limit (rule ``statement-context``: "the word limit is 80 words") is a bound and the limit's value, so it is
    either (and, by :func:`_unstated`, read only for a premise naming a limit or a requirement). A figure the premise
    negates (``ne``) or both equates and bounds is never read as its source's statement."""
    rel = set(relations or ())
    if not rel or rel <= {"eq"}:
        return not o.bound or bool(_BOUND_WORDS_RE.search(statement or ""))
    if rel <= {"lt", "le", "gt", "ge"}:
        return o.bound or o.context == CONTEXT_LIMIT
    return False


def _row_named(row: Optional[str], statement: str) -> bool:
    """Rule ``table-cells``: whether a premise's statement names the row a table cell stands in (its first cell: the
    figures it states, or else its words). A cell outside a table, or in a table's first column, has no row to name."""
    if not row:
        return True
    figures = text_numbers(row)
    if figures:
        return figures <= text_numbers(statement or "")
    words = {_norm_marker(w) for w in _statement_words(row)}
    return bool(words) and words <= {_norm_marker(w) for w in _statement_words(statement or "")}


def _fig(v: Fraction) -> str:
    """A figure as a message writes it: a whole number, a terminating decimal (``3.6``), else a fraction (``1/3``)."""
    if v.denominator == 1:
        return str(v.numerator)
    d = v.denominator
    for f in (2, 5):
        while d % f == 0:
            d //= f
    if d == 1:
        return format(float(v), "f").rstrip("0").rstrip(".") if abs(v) >= Fraction(1, 10 ** 6) else str(v)
    return str(v)


def _said(v: Fraction, o: _Occurrence) -> str:
    if o.column is not None:
        return f"{_fig(v)} in the table column '{o.column[:60]}'" + (f" (row {o.row[:30]})" if o.row else "")
    return f"{_fig(v)} periods a year (a frequency word)" if o.marker == FREQUENCY_MARKER else f"{_fig(v)} {o.marker}"


def figure_reading(v: Fraction, texts: list[str], statement: str, relations: Optional[set[str]] = None, *,
                   where: str = "the request", required: Iterable[str] = ()) -> FigureReading:
    """Rule ``same-quantity`` on one figure ``v`` of a premise with no located excerpt, read against its held source
    ``texts``. It REFUTES the premise as the source's statement of the quantity the premise names (in order):

    1. ``v`` is stated nowhere in ``texts`` (every spelling rule of :func:`text_numbers`, rule ``frequency-words``
       included: "monthly" states 12);
    2. ``v`` is stated only as a TARGET the answer must derive (:func:`target_spans`: "Show that the distance is 8 m");
    3. every other place that states ``v`` names a quantity (a unit or a counted noun: "80 words", "8 seconds"; a table
       column's header, rule ``table-cells``) that the premise's own ``statement`` (its label and its symbols' meanings)
       does not name: the quantities it states ``v`` with, or, when it states ``v`` with none, any quantity its words
       name (:func:`_statement_words`; the claim's own count assumed beside a word limit; a distance beside a time). A
       place that states ``v`` bare, and a statement that names nothing (no label, no symbol meaning), leave no quantity
       to compare, so this never refutes them;
    4. every such place that names the premise's quantity states ``v`` as a BOUND ("no more than 80 words", "exceeds 6000
       euros") while the premise states ``v`` as a value (``relations`` only ``eq``) and its statement names no bound
       ("the paragraph has 80 words" for a word limit; "the threshold is 6000 euros" names one).

    Otherwise it READS ``v`` as the source's data (the fourth repair, decision 56: the positive reading rule
    ``data-standing`` needs) only when some place outside a target states ``v`` for a quantity the premise's statement
    names, as the premise states it (:func:`_as_the_premise_states`: a value as a value, a bound as a bound), and, in a
    table, in the row the statement names (:func:`_row_named`), and (decision 57, rule ``statement-context``) as a
    statement (:func:`_unstated`: not in a yes/no question, under a negation, as one of alternatives, inside a claim the
    answer must examine, or as a requirement on the answer or a limit's value the premise's statement does not name; a
    text in ``required``, a constraint the request parser recorded, states requirements). Any other figure is UNREAD: stated only bare, for a
    premise whose statement names no quantity, otherwise than the premise states it, or only where the source does not
    state it as a statement (``context`` names that context). That is a number match only, which is no evidence. 0 and 1
    are structural (as for the number trace): never refuted and never read as data."""
    v = abs(v)
    if v in (0, 1):
        return FigureReading(FIGURE_UNREAD, f"its figure {_fig(v)} is structural (0 or 1), which no check reads as data")
    known = set().union(*(text_numbers(t) for t in texts)) if texts else set()
    date_encoded = _date_encoding(v, known)
    if not number_traced(v, known, date_encoded=date_encoded):
        return FigureReading(FIGURE_REFUTED, f"its figure {_fig(v)} is stated nowhere in {where} (rule {SAME_QUANTITY_RULE})")
    free_texts = [_blank(t, target_spans(t)) for t in texts]
    free_known = set().union(*(text_numbers(t) for t in free_texts)) if free_texts else set()
    if not number_traced(v, free_known, date_encoded=date_encoded):
        return FigureReading(FIGURE_REFUTED, f"its figure {_fig(v)} is stated in {where} only as the target the answer must derive (a 'show that' target is "
                                             f"never data: rule {SAME_QUANTITY_RULE})")
    # rule statement-context: a text in ``required`` (a constraint the request parser recorded on the answer, its words
    # copied from the request) states each of its figures as a requirement on the answer, whatever it reads like alone
    req = {t for t in required if t}
    occs = [(_as_required(o, texts[i]) if texts[i] in req else o) for i, t in enumerate(free_texts) for o in _occurrences(t) if _states(o, v)]
    return _reading(v, occs, free_texts, statement, relations, where=where)


def _as_required(o: _Occurrence, text: str) -> _Occurrence:
    """``o`` read as a requirement on the answer (a figure of a constraint text), unless it is already no statement."""
    if o.context not in (CONTEXT_STATEMENT, CONTEXT_LIMIT):
        return o
    phrase = " ".join(text.split())
    return replace(o, context=CONTEXT_REQUIREMENT, phrase=(phrase if len(phrase) <= 100 else phrase[:97] + "...") + ", a constraint on the answer")


def _reading(v: Fraction, occs: list[_Occurrence], texts: list[str], statement: str, relations: Optional[set[str]], *, where: str) -> FigureReading:
    """Steps 3 and 4 of :func:`figure_reading` and its positive reading, on ``occs``: the places (of ``texts``, outside any
    target) that state the figure ``v``."""
    v = abs(v)
    # the quantity the premise's own statement names: the markers it states ``v`` with; when it states ``v`` with none, the
    # words it names (a symbol's meaning "the hours the claim states" names hours)
    own = [o.marker for o in _occurrences(statement) if _states(o, v) and o.marker is not None] or _statement_words(statement)
    bare = not occs or any(o.bare for o in occs)
    same = [o for o in occs if own and _names_quantity(o, own)]
    if not bare and own:
        if not same:
            said = sorted({_said(v, o) for o in occs})
            return FigureReading(FIGURE_REFUTED, f"its figure {_fig(v)} is stated in {where} only as {' / '.join(said[:3])}, a quantity the premise's own "
                                                 f"statement (its label and its symbols' meanings) does not name: another quantity's number (rule "
                                                 f"{SAME_QUANTITY_RULE})")
        if relations is not None and relations <= {"eq"} and all(o.bound for o in same) and not _BOUND_WORDS_RE.search(statement or ""):
            return FigureReading(FIGURE_REFUTED, f"its figure {_fig(v)} is stated in {where} only as a bound ('{_bound_phrase(texts, same[0])}'), while the "
                                                 f"premise states it as the value of its quantity and names no bound: a limit is not the quantity's value "
                                                 f"(rule {SAME_QUANTITY_RULE})")
    so = [o for o in same if _as_the_premise_states(o, relations, statement) and _row_named(o.row, statement)]
    fit = [o for o in so if _stated(o, statement)]
    if fit:
        return FigureReading(FIGURE_READ, f"its figure {_fig(v)} is stated in {where} as {_said(v, fit[0])}, a quantity the premise's own statement "
                                          f"names, as the premise states it (rule {SAME_QUANTITY_RULE}" + (f", rule {TABLE_RULE}" if fit[0].column else "") + ")")
    if so:
        # rule statement-context: stated for the quantity, as the premise states it, but only where the source asks, denies,
        # offers alternatives, puts up for examination, requires it or sets a limit, never as its statement of the quantity's value
        o = so[0]
        ctx = _unstated(o, statement) or CONTEXT_NEGATION
        return FigureReading(FIGURE_UNREAD, f"its figure {_fig(v)} is stated in {where} for the quantity the premise names only {CONTEXT_WORDS[ctx]} "
                                            f"('{o.phrase[:100]}'){_context_extra(ctx, o)}: never {where}'s statement of its value (rules "
                                            f"{SAME_QUANTITY_RULE} and {CONTEXT_RULE})", context=ctx)
    if not own:
        why = (f"its figure {_fig(v)} is stated in {where}, but the premise's own statement (its label and its symbols' meanings) names no quantity to read "
               "it for")
    elif not same:
        others = sorted({_said(v, o) for o in occs if not o.bare})
        why = (f"its figure {_fig(v)} is stated in {where} only bare, with no quantity a check reads beside it" if not others else
               f"its figure {_fig(v)} is stated in {where} only bare or as {' / '.join(others[:3])}, a quantity the premise's own statement does not name")
    elif any(_as_the_premise_states(o, relations, statement) for o in same):
        why = f"its figure {_fig(v)} is stated in {where} for the quantity the premise names only in a table row its statement does not name (rule {TABLE_RULE})"
    else:
        why = f"its figure {_fig(v)} is stated in {where} for the quantity the premise names only otherwise than the premise states it (a bound for a value or a value for a bound)"
    return FigureReading(FIGURE_UNREAD, f"{why} (rule {SAME_QUANTITY_RULE})")


def figure_refutation(v: Fraction, texts: list[str], statement: str, relations: Optional[set[str]] = None, *, where: str = "the request") -> Optional[str]:
    """Rule ``same-quantity``: why the source ``texts`` refute a no-excerpt premise's figure ``v`` as their statement of the
    quantity the premise names (None when they do not; a figure the source does not refute is not verified by that: a
    number match is no evidence). The refutations of :func:`figure_reading`, in its order: a figure stated nowhere; only
    as a target; only for another quantity; only as a bound while the premise states a value and names no bound. 0 and 1
    are structural (as for the number trace) and never refuted."""
    r = figure_reading(v, texts, statement, relations, where=where)
    return r.reason if r.kind == FIGURE_REFUTED else None


_STATEMENT_WORD_RE = re.compile(r"(?<![\w])(in\s+)?([A-Za-zµμΩ°][A-Za-z0-9µμΩ°³²¹⁰⁴⁵⁶⁷⁸⁹⁻⁺^\-]*)")


def _statement_words(statement: str) -> list[str]:
    """The words of a premise's statement that may name a quantity (a unit or a counted noun): every word of two letters or
    more that names something (not an article, preposition or other function word), and a one-letter unit only after
    "in" ("distance in m"), so a one-letter symbol name is never read as a unit."""
    out: list[str] = []
    for m in _STATEMENT_WORD_RE.finditer(statement or ""):
        w = m.group(2).strip("'’-")
        if not w or w.casefold() in _MARKER_SKIP or (len(w) < 2 and not m.group(1)):
            continue
        if w not in out:
            out.append(w)
    return out


def _bound_phrase(texts: list[str], occ: _Occurrence) -> str:
    for t in texts:
        if occ.end <= len(t) and t[occ.start:occ.end].strip():
            m = _BOUND_BEFORE_RE.search(t[max(0, occ.start - 40):occ.start])
            if m:
                return f"{m.group(1)} {t[occ.start:occ.end]}"
    return "a bound"


def _declared_own(names: Iterable[str], problem: Optional[Problem]) -> list[str]:
    """The symbols among ``names`` that the translation itself DECLARES the writer's own: a ``symbols`` entry grounded
    ``assumption``, ``specialist_inference`` or ``general_knowledge``."""
    syms = {s.name: s for s in (problem.symbols if problem is not None else [])}
    return [n for n in names if n in syms and syms[n].grounding is not None and syms[n].grounding.kind in WRITER_OWN_KINDS]


def _undeclared_data(names: Iterable[str], problem: Optional[Problem]) -> list[str]:
    """The symbols among ``names`` that the translation does not declare as data: no ``symbols`` entry, no grounding, or
    a writer's-own kind (for Boolean content, whose source no check can read)."""
    syms = {s.name: s for s in (problem.symbols if problem is not None else [])}
    return [n for n in names if n not in syms or syms[n].grounding is None or syms[n].grounding.kind in WRITER_OWN_KINDS]


def premise_standing(premise: Any, report: SpecialistReport, request_texts: Iterable[str] = (), sorts: Optional[dict[str, str]] = None,
                     request_documents: Iterable[Any] = (), problem: Optional[Problem] = None, *, request_constraints: Iterable[str] = ()) -> Standing:
    """Rule ``data-standing`` (decision 55, corrected by decision 56) on one restating premise ``premise`` as re-grounded
    by :func:`_regrounded` (its ``verified`` the deterministic grounding check's): what a deterministic check SHOWS of it
    (:data:`STANDINGS`).

    * ``transcription``, the only evidence that clears a restatement (rule ``grounded-transcription``): a ``quotation``,
      ``supplied_text``, ``arithmetic_fact`` or ``task_setting`` whose located excerpt the grounding check VERIFIED (the
      excerpt states the premise's figures), every figure stated by the report's texts (a task setting's also by the
      request's), and no figure stated by the excerpt only as a target the answer must derive. Nothing else: no kind
      label, and no number match (decision 55 withdrew rule ``figure-transcription``, which took a no-excerpt premise's
      figures found anywhere in the request as a transcription).
    * ``own_kind``: no grounding; ``assumption``, ``specialist_inference`` or ``general_knowledge``; an ``arithmetic_fact``
      or ``quotation`` no check verified (``engine.runner.assumed_grounding``: never looser than the translator).
    * ``refuted``: the grounding check refutes it (``verified`` false); a located excerpt states one of its figures only
      as a target, or (decision 57, rule ``statement-context``) only where its document does not state it as a statement
      (:func:`_excerpt_misreadings`); or, with no excerpt, its held source refutes it (rule ``same-quantity``, :func:`figure_refutation`: a
      figure stated nowhere there, only as a target, only for another quantity, or only as a bound the premise states as
      a value), or the translation itself does not present what it states as data: a figure whose symbol it grounds as
      the writer's own (``assumption``, ``specialist_inference``, ``general_knowledge``), or Boolean content (which no
      check can read against a source, so the translation's own declarations are the only deterministic evidence, read
      only toward the writer's own) whose symbols it grounds as the writer's own or not at all, or that restates a
      conclusion it grounds as the writer's own or not at all.
    * ``uncheckable``: a ``rubric_rule``, ``knowledge_document`` or ``library_source`` (sources no check reads), or a
      ``supplied_text`` with no excerpt naming no document supplied with the request; and (decision 56) a
      ``task_setting`` or ``supplied_text`` with no excerpt that its held source does not refute but whose content no
      check READS there: Boolean content, whatever the translation declares of its symbols and its conclusion (no check
      reads a Boolean statement against a source); content that is not the values of quantities (:func:`value_atoms`: a
      relation between quantities, arithmetic, a negation, a disjunction); a structural figure (0 or 1); or a figure its
      held source states only bare, for a premise whose statement names no quantity, otherwise than the premise states
      it, or in a table row the statement does not name (:func:`figure_reading`: a number match only); and (decision 57,
      rule ``statement-context``) a figure its held source states for the premise's quantity only in a yes/no question,
      under a negation, as one of alternatives, inside a claim the answer must examine, or as a requirement on the answer
      or a limit's value the premise's statement does not name (:func:`figure_context`). On each the kind
      label is the only evidence that the source states it, and a label is IR data, not evidence: "p proves p" under a
      ``task_setting`` or ``supplied_text`` label is the claim assumed.
    * ``undecided``: a ``task_setting`` or ``supplied_text`` with no excerpt whose whole content is the values of
      quantities, each figure READ in its held source by rule ``same-quantity`` (:func:`figure_reading`: stated there for
      the quantity the premise's own statement names, as the premise states it, a value as a value and a bound as a
      bound, and in a table in the row the statement names, rule ``table-cells``, as a statement, rule
      ``statement-context``), and refuted by none. It is data
      presented as given there, but no check verifies it as the source's statement (no located excerpt: a number match is
      no evidence of a transcription). Whether the source states it, for the same quantity, is a meaning question for
      overseer agents (Inspection I77, I78).

    ``sorts`` maps the problem's symbols to their sorts and ``problem`` is the re-grounded problem (its symbols' and its
    conclusion's declared groundings)."""
    g = getattr(premise, "grounding", None)
    if g is None:
        return Standing(OWN_KIND, "it has no grounding")
    if g.kind in WRITER_OWN_KINDS:
        return Standing(OWN_KIND, f"its grounding kind {g.kind} is the writer's own")
    if g.kind in UNREAD_SOURCE_KINDS:
        return Standing(UNCHECKABLE, f"its grounding kind {g.kind} names a source no deterministic check verifies a premise against, so the kind label is "
                                     "the only evidence (IR data, not evidence)")
    if g.verified is False:
        return Standing(REFUTED, f"the deterministic grounding check refutes its {g.kind} grounding")
    if assumed_grounding(g):
        return Standing(OWN_KIND, f"its {g.kind} grounding is not verified by the deterministic grounding check (no excerpt located in a supplied text "
                                  "that states its figures): the kind label alone is IR data, not evidence")
    if g.kind not in TRANSCRIPTION_KINDS:
        return Standing(OWN_KIND, f"its grounding kind {g.kind} is the writer's own")
    try:
        expr = premise.expr.model_dump(mode="json", exclude_none=True)
    except Exception:
        return Standing(OWN_KIND, "its figures cannot be read")
    figures = ir_numbers(expr)
    unverified = f"its {g.kind} grounding is not verified (no located excerpt)"
    if g.verified is True:
        # a located excerpt the deterministic grounding check verified (it states the premise's figures): every figure
        # stated by the report's texts (a task setting's also by the request's), and not only as a target in the excerpt
        texts = [x for x in report_scope(report) if x] + ([x for x in request_texts if x] if g.kind == "task_setting" else [])
        known: set[Fraction] = set().union(*(text_numbers(x) for x in texts)) if texts else set()
        untraced = [v for v in figures if not number_traced(v, known)]
        if untraced:
            where = "the report's texts or the request" if g.kind == "task_setting" else "the report's texts"
            return Standing(REFUTED, f"its figure(s) {', '.join(str(v) for v in untraced[:4])} are stated nowhere in {where}, so it is not traced to its source")
        targeted = _excerpt_targets(g, report, figures)
        if targeted:
            return Standing(REFUTED, f"its excerpt states its figure(s) {', '.join(str(v) for v in targeted[:4])} only as the target the answer must derive "
                                     f"(a 'show that' target is never data: rule {SAME_QUANTITY_RULE})")
        # decision 57 (rule statement-context): the located excerpt must state each figure as its source's own statement,
        # not merely contain its digits inside a question, a negation, a claim to examine or a requirement
        misread = _excerpt_misreadings(g, report, figures, _premise_statement(premise, problem))
        if misread:
            more = f"; and {len(misread) - 1} more figure(s) so" if len(misread) > 1 else ""
            return Standing(REFUTED, f"its {g.kind} excerpt is located and states its figure(s), but not as its source's own statement: {misread[0]}{more}")
        return Standing(TRANSCRIPTION)
    if g.kind not in HELD_SOURCE_KINDS:
        return Standing(OWN_KIND, f"its {g.kind} grounding is not verified by the deterministic grounding check (no excerpt located in a supplied text that "
                                  "states its figures): the kind label alone is IR data, not evidence")
    texts, where = _held_sources(g, request_texts, request_documents)
    if texts is None:
        return Standing(UNCHECKABLE, where)
    words = [w for w in _bool_symbols(expr, sorts) if w != "true/false"]
    numeric = _numeric_symbols(expr, sorts)
    # the translation's own declarations, read only toward the writer's own (never toward data): a figure whose symbol
    # the glossary grounds as the writer's own; Boolean content (no check reads it against a source) whose symbols the
    # translation grounds as the writer's own or not at all, or restating a conclusion it grounds so
    own_declared = _declared_own(numeric + words, problem)
    if own_declared:
        return Standing(REFUTED, f"{unverified}, and the translation itself declares {', '.join(own_declared[:4])} the writer's own (its symbol's "
                                 f"grounding), so a premise presenting it as given in {where} restates the writer's own content (rule {STANDING_RULE})")
    if words:
        undeclared = _undeclared_data(words, problem)
        if undeclared:
            return Standing(REFUTED, f"{unverified}, and it states {', '.join(undeclared[:4])}, which the translation itself does not ground as data (no "
                                     f"symbol grounding): Boolean content, which no check reads against a source, presented as given in {where} while "
                                     f"the translation does not present it as data (rule {STANDING_RULE})")
        concl = problem.conclusion if problem is not None else None
        ckind = concl.grounding.kind if concl is not None and concl.grounding is not None else None
        if ckind is None or ckind in WRITER_OWN_KINDS:
            own_phrase = f"as the writer's own ({ckind})" if ckind else "nowhere (no grounding)"
            return Standing(REFUTED, f"{unverified}, and it states {', '.join(words[:4])} while the translation itself grounds its conclusion "
                                     f"{own_phrase}: Boolean content of the claim presented as given in {where} while the translation does not "
                                     f"present the claim as data (rule {STANDING_RULE})")
    statement = _premise_statement(premise, problem)
    relations = _figure_relations(expr)
    readings: list[tuple[Fraction, FigureReading]] = []
    for v in figures:
        r = figure_reading(v, texts, statement, relations.get(abs(v)), where=where, required=request_constraints if g.kind == "task_setting" else ())
        if r.kind == FIGURE_REFUTED:
            return Standing(REFUTED, f"{unverified}, and {r.reason}")
        readings.append((v, r))
    # rule data-standing (the fourth repair, decision 56): presented as data but not refuted, a premise is UNDECIDED only
    # when a deterministic check READS its whole content in its held source; content no check reads there is presented as
    # data on the kind label alone, which is IR data, not evidence (p proves p under a label is the claim assumed)
    label_only = (f"the kind label is then the only evidence that {where} states it, and a kind label is IR data, not evidence (rule "
                  f"{STANDING_RULE})")
    if words:
        return Standing(UNCHECKABLE, f"{unverified}: it states {', '.join(words[:4])} (Boolean content), which the translation declares as data "
                                     f"throughout (its symbols and its conclusion grounded, none as the writer's own), but no deterministic check reads "
                                     f"Boolean content against {where}: {label_only}")
    atoms = value_atoms(expr, sorts)
    if atoms is None:
        return Standing(UNCHECKABLE, f"{unverified}: what it states is not the values of quantities (each a comparison of one Int or Real symbol with one "
                                     f"figure), so no deterministic check reads it against {where}: {label_only}")
    structural = sorted({abs(v) for _n, _op, v in atoms if abs(v) in (0, 1)})
    if structural and len(structural) == len({abs(v) for _n, _op, v in atoms}):
        return Standing(UNCHECKABLE, f"{unverified}: it states no figure other than 0 or 1 (structural figures, never read as data), so no deterministic "
                                     f"check reads it against {where}: {label_only}")
    if structural:
        return Standing(UNCHECKABLE, f"{unverified}: it states the structural figure(s) {', '.join(str(v) for v in structural)} (0 or 1, never read as "
                                     f"data) as the value of a quantity, so no deterministic check reads all of it against {where}: {label_only}")
    unread = [r for _v, r in readings if r.kind != FIGURE_READ]
    if unread:
        return Standing(UNCHECKABLE, f"{unverified}: {unread[0].reason}, and a number match is no evidence: {label_only}")
    read = "; ".join(r.reason for _v, r in readings if abs(_v) not in (0, 1))
    return Standing(UNDECIDED, f"{unverified}: {read}. So read it is data presented as given there, but a number match is no evidence of a "
                               f"transcription: no deterministic check verifies it (no excerpt was located) and none refutes it (rule {STANDING_RULE}; the "
                               "kind label alone is IR data, not evidence)")


def _excerpt_targets(g: Any, report: SpecialistReport, figures: list[Fraction]) -> list[Fraction]:
    """The figures among ``figures`` (other than 0 and 1) that every located excerpt of ``g`` states only inside a target
    of its document (:func:`target_spans`)."""
    docs = {d.document_id: d.text for d in report.supplied_texts}
    hits: dict[Fraction, list[bool]] = {}
    for r in g.source_refs:
        text = docs.get(r.document_id)
        if not r.excerpt or not text:
            continue
        m = locate_quotation(r.excerpt, text, document_id=r.document_id)
        if m is None:
            continue
        spans = target_spans(text)
        span_text = text[m.start:m.end]
        for v in figures:
            if abs(v) in (0, 1):
                continue
            inside = [o for o in _occurrences(span_text) if _states(o, abs(v))]
            if not inside:
                continue
            free = [o for o in inside if not any(a <= m.start + o.start and m.start + o.end <= b for a, b in spans)]
            hits.setdefault(abs(v), []).append(not free)
    return [v for v, flags in hits.items() if flags and all(flags)]


def _excerpt_misreadings(g: Any, report: SpecialistReport, figures: list[Fraction], statement: str) -> list[str]:
    """Rule ``statement-context`` on the located excerpts of ``g`` (decision 57): one reason per figure (other than 0 and
    1) that every located excerpt stating it (outside a target, :func:`_excerpt_targets`) states only in a yes/no
    question, under a negation, as one of alternatives, inside a claim the answer must examine, or as a requirement the
    premise's own ``statement`` does not name. The context is read in the excerpt's document (an excerpt may cut its sentence: "mention
    3 workers" from "The extract does not mention 3 workers"). Which quantity the excerpt states a figure for is not read
    here (decision 49: the located excerpt is the evidence; rule same-quantity reads only the word after a figure, and
    excerpts name their quantity before it, "PED = -0.67", "Pc = $1.90 per litre")."""
    docs = {d.document_id: d.text for d in report.supplied_texts}
    out: list[str] = []
    for v in dict.fromkeys(abs(x) for x in figures):
        if v in (0, 1):
            continue
        verdicts: list[Optional[_Occurrence]] = []  # per located excerpt stating v: None when it states v as a statement
        for r in g.source_refs:
            text = docs.get(r.document_id)
            if not r.excerpt or not text:
                continue
            m = locate_quotation(r.excerpt, text, document_id=r.document_id)
            if m is None:
                continue
            spans = target_spans(text)
            occs = [o for o in _occurrences(text) if m.start <= o.start and o.end <= m.end and _states(o, v)
                    and not any(a <= o.start and o.end <= b for a, b in spans)]
            if occs:
                verdicts.append(None if any(_stated(o, statement) for o in occs) else occs[0])
        if verdicts and all(o is not None for o in verdicts):
            o = verdicts[0]
            ctx = _unstated(o, statement) or CONTEXT_NEGATION
            out.append(f"its figure {_fig(v)} is stated in its excerpt only {CONTEXT_WORDS[ctx]} ('{o.phrase[:100]}'){_context_extra(ctx, o)}: never its "
                       f"source's statement of its value (rule {CONTEXT_RULE})")
    return out


def transcription_fault(premise: Any, report: SpecialistReport, request_texts: Iterable[str] = (), sorts: Optional[dict[str, str]] = None,
                        request_documents: Iterable[Any] = (), problem: Optional[Problem] = None, *, request_constraints: Iterable[str] = ()) -> Optional[str]:
    """Rule ``grounded-transcription`` on one premise as re-grounded by :func:`_regrounded`: None when it is a
    transcription (:func:`premise_standing`), else why it is the writer's own for the overseer (shown or undecided)."""
    st = premise_standing(premise, report, request_texts, sorts, request_documents, problem, request_constraints=request_constraints)
    return None if st.kind == TRANSCRIPTION else st.reason


def is_transcription(premise_id: str, problem: Optional[Problem], problem_obj: Optional[dict], report: SpecialistReport, request_texts: list[str],
                     request_documents: Iterable[Any] = (), *, request_constraints: Iterable[str] = ()) -> bool:
    """Rule ``grounded-transcription``: whether the premise ``premise_id`` of ``problem``, re-grounded on the report's
    supplied texts, is a transcription a deterministic check verified (:func:`premise_standing`). ``problem_obj`` is kept
    for callers of the earlier signature."""
    if problem is None:
        return False
    again_problem = _regrounded(problem, report)
    again = next((p for p in again_problem.premises if p.id == premise_id), None)
    sorts = {s.name: s.sort for s in problem.symbols}
    return again is not None and premise_standing(again, report, request_texts, sorts, request_documents, again_problem,
                                                  request_constraints=request_constraints).kind == TRANSCRIPTION


def disclosed_by_the_receipt(grounding: Any) -> bool:
    """Rule ``receipt-disclosure``: whether a result relying on a premise grounded ``grounding`` (as the deterministic
    grounding check re-derives it) discloses that premise as not established: the engine lists it among the result's
    ungrounded dependencies (``engine.runner.is_ungrounded``: no grounding, an inferential kind, a failed check, a
    quotation no check verified) or its unverified dependencies (``engine.runner.is_unverified``: a supplied text,
    knowledge document or library source no check verified), and the outcome summary names it. A ``task_setting``,
    ``rubric_rule`` or ``arithmetic_fact`` that no check verified is in neither list: the receipt presents it as given
    with the task."""
    return is_ungrounded(grounding) or is_unverified(grounding)


# ---------------------------------------------------------------------------- rule semantic-restatement
def nnf_conjuncts(expr: Any) -> list[dict]:
    """The conjuncts of ``expr`` (IR JSON) with negation pushed inward through ``not``, ``and``, ``or`` and ``implies``,
    so a conjunction hidden under a negation is exposed (``not (not a or not b)`` gives ``a`` and ``b``; ``not (a implies
    b)`` gives ``a`` and ``not b``); every other node is one conjunct (negated when it sits under an odd number of
    ``not``). Left to right, iteratively, without duplicates (compared as canonical JSON). Data only, nothing is
    evaluated."""
    out: list[dict] = []
    seen: set[str] = set()
    stack: list[tuple[Any, bool]] = [(expr, False)]
    while stack:
        node, neg = stack.pop()
        op = node.get("op") if isinstance(node, dict) else None
        if op == "not" and isinstance(node.get("arg"), dict):
            stack.append((node["arg"], not neg))
            continue
        if (op == "and" and not neg) or (op == "or" and neg):
            stack.extend((a, neg) for a in reversed(node.get("args") or []))
            continue
        if op == "implies" and neg and isinstance(node.get("left"), dict) and isinstance(node.get("right"), dict):
            stack.append((node["right"], True))
            stack.append((node["left"], False))
            continue
        item = {"op": "not", "arg": node} if neg else node
        key = canonical_json(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _expr_symbols(expr: Any) -> frozenset[str]:
    names: set[str] = set()
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("op") == "var":
                names.add(str(node.get("name")))
                continue
            stack.extend(v for k, v in node.items() if k != "value")
        elif isinstance(node, list):
            stack.extend(node)
    return frozenset(names)


_COMPARE_OPS = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
_COMPARE_FLIP = {"gt": "lt", "ge": "le"}
_BOOLEAN_OPS = frozenset({"bool", "not", "and", "or", "implies", "iff"}) | _COMPARE_OPS


#: Numbers in the normal form of :func:`_canon_term`: the identity elements of a sum and of a product.
_ZERO = {"op": "num", "value": "0/1"}
_ONE = {"op": "num", "value": "1/1"}


def _canon_term(node: Any) -> Any:
    """A term in the normal form both readings compare: numbers as exact fractions (``105``, ``105.0`` and ``210/2``
    alike); the terms of a sum or a product flattened and in a fixed order (``a + b`` and ``b + a`` alike); an identity
    element beside a symbol dropped (``x + 0``, ``x * 1``, ``x - 0``, ``x / 1`` and ``-(-x)`` are ``x``, which they are
    for every value: the second repair of the translator merge, so that a premise ``x + 0 = 5`` restates ``x = 5`` as
    ``e or e`` restates ``e``); and a conversion to a real the term it converts (it keeps the value). A normalisation,
    never an evaluation: ``2 + 3`` stays a sum and ``1 * 10`` a product (a computation on numbers alone is the working the
    engine checks, never dropped, even when one of its numbers is 0 or 1)."""
    if isinstance(node, list):
        return [_canon_term(x) for x in node]
    if not isinstance(node, dict):
        return node
    op = node.get("op")
    if op in ("int", "real") and isinstance(node.get("value"), str):
        try:
            v = Fraction(node["value"])
            return {"op": "num", "value": f"{v.numerator}/{v.denominator}"}
        except (ValueError, ZeroDivisionError):
            return node
    if op in ("add", "mul") and isinstance(node.get("args"), list):
        flat: list[Any] = []
        for a in node["args"]:
            ca = _canon_term(a)
            if isinstance(ca, dict) and ca.get("op") == op and isinstance(ca.get("args"), list):
                flat.extend(ca["args"])
            else:
                flat.append(ca)
        if any(_expr_symbols(a) for a in flat):
            identity = _ZERO if op == "add" else _ONE
            flat = [a for a in flat if a != identity] or [identity]
        if len(flat) == 1:
            return flat[0]
        return {"op": op, "args": sorted(flat, key=canonical_json)}
    if op in ("sub", "div", "idiv") and isinstance(node.get("left"), dict) and isinstance(node.get("right"), dict):
        left, right = _canon_term(node["left"]), _canon_term(node["right"])
        if right == (_ZERO if op == "sub" else _ONE) and _expr_symbols(left):
            return left
        return {**{k: _canon_term(v) for k, v in node.items()}, "left": left, "right": right}
    if op == "neg" and isinstance(node.get("arg"), dict):
        arg = _canon_term(node["arg"])
        if isinstance(arg, dict) and arg.get("op") == "neg" and isinstance(arg.get("arg"), dict) and _expr_symbols(arg):
            return arg["arg"]
        return {"op": "neg", "arg": arg}
    if op == "to_real" and isinstance(node.get("arg"), dict):
        return _canon_term(node["arg"])
    return {k: _canon_term(v) for k, v in node.items()}


def _atom_key(node: dict) -> str:
    """The atom a leaf of the Boolean structure stands for: a Boolean symbol, or a comparison with ``gt``/``ge`` written
    as the reversed ``lt``/``le``, the sides of ``eq`` in a fixed order, and its terms in the normal form of
    :func:`_canon_term`."""
    op = node.get("op")
    if op == "var":
        return "v:" + str(node.get("name"))
    if op in _COMPARE_OPS:
        left, right = _canon_term(node.get("left")), _canon_term(node.get("right"))
        if op in _COMPARE_FLIP:
            op, left, right = _COMPARE_FLIP[op], right, left
        if op in ("eq", "ne"):
            left, right = sorted((left, right), key=canonical_json)
        return "c:" + canonical_json({"op": op, "left": left, "right": right})
    return "x:" + canonical_json(_canon_term(node))


class _Readings:
    """Rule ``semantic-restatement`` on one problem (as re-grounded): whether a premise restates a conjunct of the
    conclusion in another form than as written. Two readings, each a bounded solver check on terms built from the IR as
    data (nothing is evaluated), in a solver context of its own:

    * **Boolean**: the conjunct follows from the premise ALONE by its Boolean structure (``not``, ``and``, ``or``,
      ``implies``, ``iff``, a Boolean ``ite``, true and false), each Boolean symbol and each comparison an opaque atom
      (:func:`_atom_key`: ``gt`` as the reversed ``lt``, ``ge`` as the reversed ``le``, ``ne`` as not ``eq``, the sides of
      ``eq`` in a fixed order, its terms in the normal form of :func:`_canon_term`: numbers exact, the terms of a sum or a
      product in a fixed order, an identity element beside a symbol dropped). So ``e or e``, ``true implies e``,
      ``not not e``, ``(e and b) or (e and c)`` and ``b and (b implies e)`` restate ``e``, ``105 = q25`` restates
      ``q25 = 105``, and ``x + 0 = 5`` restates ``x = 5``.
    * **Order**: the conjunct is EQUIVALENT to the premise, to one of its conjuncts (:func:`nnf_conjuncts`), or to the
      conjunction of its conjuncts that mention only the conjunct's symbols, read with the order of the numbers (each
      symbol of its declared sort, numbers exact) but with every arithmetic term (a sum, a difference, a product, a
      quotient, a remainder, the negation of a symbol, a conditional term) one opaque value per normal form and every
      comparison of numbers alone an opaque atom. So ``q >= 105 and q <= 105`` restates ``q = 105`` and ``not (x < 3)``
      restates ``x >= 3``; but a line of working (``a = (20 - 0) / 4.0`` beside ``a = 5.0``, ``R * (1/4.0 + 1/6.0) = 1``
      beside ``R = 2.4``) and a definition by a comparison of numbers (``y12 iff (136 >= 133 and 136 <= 144)`` beside
      ``y12``) restate nothing: an arithmetic step is a derivation the engine checks, never a restatement. Nor does
      ``x = 5`` restate ``x > 3`` (it entails it, it is not equivalent to it: a derivation).
    * **Arithmetic** (rule ``arithmetic-restatement``, STEM repair 12): as the order reading, but the arithmetic of the
      conjunct's symbols read exactly as the engine's compiler reads it (:meth:`_arith`); arithmetic of numbers alone stays
      one opaque value per normal form and a comparison of numbers alone an opaque atom. So ``contrib - 2.00 = 0``,
      ``2 * contrib = 4.00`` and ``2 * x + 3 = 7`` restate ``contrib = 2.00``, ``contrib = 2.00`` and ``x = 2``, while the
      line of working and the definition by a comparison of numbers above still restate nothing. Measured on every recorded
      round's translations (339 problems), it reads none of their premises as a restatement; reading the arithmetic of
      numbers too would read two lines of working (r7 ec-t13 g2.3, mai-t13 g5.3), which decision 51 measured.

    A premise that contradicts itself restates nothing (the engine's consistency check reports it). :meth:`valid` reads a
    conjunct with the engine's own compiler (full arithmetic) to tell whether it holds under every assignment."""

    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        self.sorts = {s.name: s.sort for s in problem.symbols}
        self._ctx: Any = None
        self._atoms: dict[tuple[str, str], Any] = {}
        self._values: dict[str, Any] = {}
        self._compiled: Any = None
        self._memo: dict[tuple[str, str], Optional[str]] = {}

    # ---------------------------------------------------------------- solver plumbing
    def _context(self) -> Any:
        import z3
        if self._ctx is None:
            self._ctx = z3.Context()
        return self._ctx

    @staticmethod
    def _decide(ctx: Any, *assertions: Any) -> Optional[bool]:
        """True when the assertions are unsatisfiable, False when satisfiable, None when the bounds leave it undecided."""
        import z3
        s = z3.Solver(ctx=ctx)
        s.set("rlimit", RESTATEMENT_RLIMIT)
        s.set("timeout", RESTATEMENT_TIMEOUT_MS)
        for a in assertions:
            s.add(a)
        r = s.check()
        return True if r == z3.unsat else False if r == z3.sat else None

    def _is_boolean(self, node: Any) -> bool:
        op = node.get("op") if isinstance(node, dict) else None
        if op in _BOOLEAN_OPS:
            return True
        if op == "var":
            return self.sorts.get(str(node.get("name"))) == "Bool"
        if op == "ite":
            return self._is_boolean(node.get("then"))
        return False

    def _atom(self, mode: str, key: str) -> Any:
        import z3
        if (mode, key) not in self._atoms:
            self._atoms[(mode, key)] = z3.Bool(f"{mode[0]}{len(self._atoms)}", self._context())
        return self._atoms[(mode, key)]

    def _formula(self, node: Any, mode: str) -> Any:
        """The Boolean structure of ``node`` over the atoms of ``mode`` (``boolean`` or ``order``)."""
        import z3
        ctx = self._context()
        op = node.get("op") if isinstance(node, dict) else None
        if op == "bool":
            return z3.BoolVal(bool(node.get("value")), ctx)
        if op == "not":
            return z3.Not(self._formula(node.get("arg"), mode), ctx)
        if op in ("and", "or"):
            kids = [self._formula(a, mode) for a in node.get("args") or []]
            if len(kids) < 2:
                return kids[0] if kids else z3.BoolVal(op == "and", ctx)
            return z3.And(*kids) if op == "and" else z3.Or(*kids)
        if op == "implies":
            return z3.Implies(self._formula(node.get("left"), mode), self._formula(node.get("right"), mode), ctx)
        if op == "iff":
            return self._formula(node.get("left"), mode) == self._formula(node.get("right"), mode)
        if op == "ite" and self._is_boolean(node):
            return z3.If(self._formula(node.get("cond"), mode), self._formula(node.get("then"), mode), self._formula(node.get("otherwise"), mode), ctx)
        if op == "ne":
            return z3.Not(self._formula({"op": "eq", "left": node.get("left"), "right": node.get("right")}, mode), ctx)
        if op in _COMPARE_OPS and mode in ("order", "arithmetic") and _expr_symbols(node):
            read = self._value if mode == "order" else self._arith
            left, right = read(node.get("left")), read(node.get("right"))
            return {"eq": lambda: left == right, "lt": lambda: left < right, "le": lambda: left <= right, "gt": lambda: left > right,
                    "ge": lambda: left >= right}[op]()
        return self._atom(mode, _atom_key(node if isinstance(node, dict) else {"op": "?", "value": repr(node)}))

    def _sort_of(self, node: Any) -> str:
        """The numeric sort of an arithmetic term (``Int`` unless a ``Real`` symbol or number, a quotient or a conversion
        makes it ``Real``)."""
        op = node.get("op") if isinstance(node, dict) else None
        if op == "var":
            return "Int" if self.sorts.get(str(node.get("name"))) == "Int" else "Real"
        if op == "int" or op in ("idiv", "mod"):
            return "Int"
        if op in ("real", "div", "to_real"):
            return "Real"
        kids = [node.get(k) for k in ("arg", "left", "right", "then", "otherwise") if isinstance(node.get(k), dict)] + list(node.get("args") or [])
        return "Real" if any(self._sort_of(k) == "Real" for k in kids) else "Int"

    def _value(self, node: Any) -> Any:
        """A numeric term of the order reading: a symbol of its declared sort, a number exactly, the negation of a number,
        a symbol or number converted to a real, a term whose normal form is a symbol (``x + 0``, ``x * 1``: that symbol);
        any other arithmetic term one opaque value per normal form (:func:`_canon_term`)."""
        import z3
        ctx = self._context()
        op = node.get("op") if isinstance(node, dict) else None
        if op in ("int", "real") and isinstance(node.get("value"), str):
            v = Fraction(node["value"])
            return z3.IntVal(v.numerator, ctx) if op == "int" and v.denominator == 1 else z3.Q(v.numerator, v.denominator, ctx)
        if op == "neg" and isinstance(node.get("arg"), dict) and node["arg"].get("op") in ("int", "real"):
            return -self._value(node["arg"])
        if op == "to_real" and isinstance(node.get("arg"), dict) and node["arg"].get("op") in ("var", "int", "real"):
            return z3.ToReal(self._value(node["arg"]))
        if op != "var":
            canon = _canon_term(node)
            if isinstance(canon, dict) and canon.get("op") == "var":
                return self._value(canon)  # x + 0, x * 1, to_real(x): the symbol itself (_canon_term)
        if op == "var":
            key, sort = "v:" + str(node.get("name")), self._sort_of(node)
        else:
            key, sort = "t:" + canonical_json(canon), self._sort_of(node)
        if key not in self._values:
            make = z3.Int if sort == "Int" else z3.Real
            self._values[key] = make(f"n{len(self._values)}", ctx)
        return self._values[key]

    def _arith(self, node: Any) -> Any:
        """A numeric term of the arithmetic reading (rule ``arithmetic-restatement``, STEM repair 12): the arithmetic of the conjunct's
        symbols read exactly as the engine reads it (sums, differences, negations, products, a quotient, an integer quotient or a remainder
        by a number, a conversion to a real, a conditional term), each symbol of its declared sort and each number exact; a term of numbers
        alone (``(20 - 0) / 4.0``) one opaque value per normal form, as in the order reading: the working the engine checks is never
        evaluated here. Anything else (a quotient by a symbol, which the IR policy refuses) one opaque value per normal form."""
        import z3
        op = node.get("op") if isinstance(node, dict) else None
        if op in ("int", "real", "var") or not _expr_symbols(node):
            return self._value(node)
        if op == "add" and isinstance(node.get("args"), list) and node["args"]:
            out = None
            for a in node["args"]:
                v = self._arith(a)
                out = v if out is None else out + v
            return out
        if op == "mul" and isinstance(node.get("args"), list) and node["args"]:
            out = None
            for a in node["args"]:
                v = self._arith(a)
                out = v if out is None else out * v
            return out
        if op == "sub" and isinstance(node.get("left"), dict) and isinstance(node.get("right"), dict):
            return self._arith(node["left"]) - self._arith(node["right"])
        if op == "neg" and isinstance(node.get("arg"), dict):
            return -self._arith(node["arg"])
        if op == "to_real" and isinstance(node.get("arg"), dict):
            v = self._arith(node["arg"])
            return z3.ToReal(v) if z3.is_int(v) else v
        if op in ("div", "idiv", "mod") and isinstance(node.get("left"), dict) and _literal(node.get("right")) not in (None, 0):
            left, d = self._arith(node["left"]), _literal(node["right"])
            if op == "div":
                return (z3.ToReal(left) if z3.is_int(left) else left) / z3.Q(d.numerator, d.denominator, self._context())
            if z3.is_int(left) and d.denominator == 1:
                k = z3.IntVal(d.numerator, self._context())
                return left / k if op == "idiv" else left % k
        if op == "ite" and isinstance(node.get("cond"), dict) and isinstance(node.get("then"), dict) and isinstance(node.get("otherwise"), dict):
            then, other = self._arith(node["then"]), self._arith(node["otherwise"])
            if z3.is_int(then) != z3.is_int(other):
                then, other = (z3.ToReal(then) if z3.is_int(then) else then), (z3.ToReal(other) if z3.is_int(other) else other)
            return z3.If(self._formula(node["cond"], "arithmetic"), then, other, self._context())
        return self._value(node)

    # ---------------------------------------------------------------- the readings
    def boolean(self, premise: dict, conjunct: dict) -> Optional[bool]:
        """Whether ``conjunct`` follows from ``premise`` alone by Boolean structure (None when undecided)."""
        import z3
        try:
            p, c = self._formula(premise, "boolean"), self._formula(conjunct, "boolean")
            alone = self._decide(self._context(), p)
            if alone is not False:
                return None if alone is None else False  # a premise that contradicts itself restates nothing
            return self._decide(self._context(), p, z3.Not(c, self._context()))
        except Exception:
            return None

    def order(self, candidate: dict, conjunct: dict) -> Optional[bool]:
        """Whether ``candidate`` is equivalent to ``conjunct`` in the order reading (None when undecided)."""
        import z3
        try:
            a, c = self._formula(candidate, "order"), self._formula(conjunct, "order")
            alone = self._decide(self._context(), a)
            if alone is not False:
                return None if alone is None else False
            return self._decide(self._context(), z3.Not(a == c, self._context()))
        except Exception:
            return None

    def arithmetic(self, candidate: dict, conjunct: dict) -> Optional[bool]:
        """Whether ``candidate`` is equivalent to ``conjunct`` in the arithmetic reading (rule ``arithmetic-restatement``, STEM repair 12:
        :meth:`_arith`; None when undecided)."""
        import z3
        try:
            a, c = self._formula(candidate, "arithmetic"), self._formula(conjunct, "arithmetic")
            alone = self._decide(self._context(), a)
            if alone is not False:
                return None if alone is None else False
            return self._decide(self._context(), z3.Not(a == c, self._context()))
        except Exception:
            return None

    def valid(self, conjunct: dict) -> Optional[bool]:
        """Whether ``conjunct`` holds under every assignment of the problem's symbols, read by the engine's own compiler
        (full arithmetic): such a conjunct needs no premise. None when undecided or not compiled."""
        import z3
        try:
            if self._compiled is None:
                from ...engine.compiler import compile_problem
                try:
                    self._compiled = compile_problem(self.problem)
                except Exception:
                    self._compiled = False
            if self._compiled is False:
                return None
            from ...engine.compiler import compile_expr
            term = compile_expr(_expr_adapter().validate_python(conjunct), self._compiled.symbols, self._compiled.ctx)
            return self._decide(self._compiled.ctx, z3.Not(term))
        except Exception:
            return None

    def restates(self, premise: dict, parts: list[dict], conjunct: dict) -> Optional[str]:
        """How ``premise`` (with its conjuncts ``parts``) restates ``conjunct`` in another form: ``"boolean"``,
        ``"order"``, ``"undecided"`` (a bound was reached: read as a restatement), or None."""
        key = (canonical_json(premise), canonical_json(conjunct))
        if key not in self._memo:
            self._memo[key] = self._restates(premise, parts, conjunct)
        return self._memo[key]

    def _restates(self, premise: dict, parts: list[dict], conjunct: dict) -> Optional[str]:
        c_syms = _expr_symbols(conjunct)
        if c_syms and not (c_syms & _expr_symbols(premise)):
            return None
        undecided = False
        b = self.boolean(premise, conjunct)
        if b is True:
            return "boolean"
        undecided = undecided or b is None
        candidates = [premise] + [q for q in parts if canonical_json(q) != canonical_json(premise)]
        inside = [q for q in parts if _expr_symbols(q) <= c_syms]
        if 1 < len(inside) < len(parts):
            candidates.append({"op": "and", "args": inside})
        for cand in candidates:
            if c_syms and not (_expr_symbols(cand) & c_syms):
                continue
            o = self.order(cand, conjunct)
            if o is True:
                return "order"
            undecided = undecided or o is None
        # rule arithmetic-restatement (STEM repair 12): the conjunct rewritten by the arithmetic of its own symbols (terms moved across,
        # both sides scaled: 'contrib - 2.00 eq 0', '2 * contrib eq 4.00' for 'contrib eq 2.00'); before, the order reading kept every
        # arithmetic term opaque, so such a premise restated nothing, carried an ENTAILED result with no finding, and a translation_circular
        # accusation of it was refuted
        for cand in candidates:
            if not (_expr_symbols(cand) & c_syms) or not self._has_symbol_arithmetic(cand, conjunct):
                continue
            o = self.arithmetic(cand, conjunct)
            if o is True:
                return "arithmetic"
            undecided = undecided or o is None
        return "undecided" if undecided else None

    @staticmethod
    def _has_symbol_arithmetic(*nodes: Any) -> bool:
        """Whether one of ``nodes`` (IR JSON) holds an arithmetic term over a symbol (a sum, difference, negation, product, quotient or
        conditional term with a symbol in it), the only content the arithmetic reading reads beyond the order reading."""
        stack = list(nodes)
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("op") in ("add", "sub", "mul", "neg", "div", "idiv", "mod", "ite") and _expr_symbols(node):
                    return True
                stack.extend(v for k, v in node.items() if k != "value")
            elif isinstance(node, list):
                stack.extend(node)
        return False


_EXPR_ADAPTER: Any = None


def _expr_adapter() -> Any:
    """The pydantic validator of one IR expression (the schema's own ``Expr``): an expression built from IR JSON is
    validated as data before the engine's compiler sees it."""
    global _EXPR_ADAPTER
    if _EXPR_ADAPTER is None:
        from pydantic import TypeAdapter
        from ...ir.schema import Expr
        _EXPR_ADAPTER = TypeAdapter(Expr)
    return _EXPR_ADAPTER


#: How a premise restates a conjunct of the conclusion, as findings and notes name it; the last three are rule
#: ``semantic-restatement``'s.
RESTATEMENT_WAYS = {"syntactic": "as written", "verbatim": "the whole conclusion as written",
                    "boolean": "in another form: its Boolean structure alone gives it",
                    "order": "in another form: equivalent once the order of numbers is read (no arithmetic evaluated)",
                    "arithmetic": "in another form: equivalent by the arithmetic of its own symbols (terms moved across, both sides scaled; arithmetic of "
                                  "numbers alone, the working the engine checks, not evaluated)",
                    "undecided": "possibly in another form: the bounded check was undecided, read as a restatement"}
#: The ways of rule ``semantic-restatement`` (a restatement in another form than as written).
SEMANTIC_WAYS = frozenset({"boolean", "order", "arithmetic", "undecided"})


@dataclass(frozen=True)
class Restatement:
    """Which premises of a translation restate its conclusion, and which of them are the writer's own (rules
    ``circularity-agreement``, ``semantic-restatement``, ``grounded-transcription`` and ``receipt-disclosure``, module
    docstring).

    ``named`` are the premises the translator's rule names (``engine.runner.circular_premises``: one per conjunct of the
    conclusion; empty when the conclusion is not restated by its definition) and ``translator_holds`` its own decision on
    the re-grounded IR (every named premise is the writer's own by ``assumed_grounding``: the translator would have
    withheld the encoding).

    The conclusion is restated AS A WHOLE when every one of its conjuncts that needs a premise (a conjunct that holds
    under every assignment needs none) is restated by some premise, the writer's own or a transcription, as written or in
    another form (always so when ``translator_holds``). Then ``holds`` is true when at least one restating premise is the
    writer's own: ``own`` are those (what the necessity run removes) and ``grounded`` the restating premises a
    deterministic check verified (when ``holds`` is false, every restating premise is one: a transcription check).

    When the conclusion is NOT restated as a whole (some conjunct is derived from other premises, or left open),
    ``partial_own`` are the writer's-own premises restating some of its conjuncts that the receipt does not disclose as
    unestablished (rule ``receipt-disclosure``: a task setting, rubric rule or arithmetic fact no check verified), which
    the necessity run grades, and ``disclosed_own`` those the receipt discloses as ungrounded or unverified dependencies
    (no finding). ``why_own`` gives the reason for each writer's-own premise, ``how`` how each restating premise of
    ``own``, ``grounded``, ``partial_own`` and ``disclosed_own`` restates (keys of ``RESTATEMENT_WAYS``).

    Rule ``data-standing`` (decision 55, corrected by decision 56): ``standings`` gives each restating premise's standing
    (:data:`STANDINGS`); ``shown`` are the writer's-own premises (of ``own``, ``partial_own`` and ``disclosed_own``) that a
    check SHOWS are not data (``own_kind``, ``refuted``, ``uncheckable``: a premise presented as data on a kind label alone
    is one) and ``undecided`` those whose whole content rule ``same-quantity`` reads as their held source's data but that
    no check verifies or refutes, ``undecided_disclosed`` those of them the receipt discloses (the engine lists them among the result's
    unverified dependencies: a ``supplied_text``; a ``task_setting`` is presented as given with the task: recorded, and
    named in the finding, but it does not change the grade). Rule ``engine-shown`` grades a restatement by the shown ones
    (:func:`engine_shown_grade`)."""
    named: tuple[str, ...] = ()
    holds: bool = False
    own: tuple[str, ...] = ()
    grounded: tuple[str, ...] = ()
    translator_holds: bool = False
    why_own: tuple[tuple[str, str], ...] = ()
    partial_own: tuple[str, ...] = ()
    how: tuple[tuple[str, tuple[str, ...]], ...] = ()
    disclosed_own: tuple[str, ...] = ()
    standings: tuple[tuple[str, str], ...] = ()
    shown: tuple[str, ...] = ()
    undecided: tuple[str, ...] = ()
    undecided_disclosed: tuple[str, ...] = ()


def restatement(problem: Optional[Problem], report: SpecialistReport, request_texts: Iterable[str] = (), problem_obj: Optional[dict] = None,
                request_documents: Iterable[Any] = (), *, request_constraints: Iterable[str] = ()) -> Restatement:
    """Rules ``circularity-agreement``, ``semantic-restatement``, ``grounded-transcription`` and ``receipt-disclosure``
    on ``problem`` re-grounded against ``report``. ``request_texts`` are the journaled request's input and constraint
    texts and ``request_documents`` the texts supplied with it (rules ``data-standing`` and ``same-quantity``);
    ``request_constraints`` are the constraint texts among them, each figure of which states a requirement on the answer
    (rule ``statement-context``); ``problem_obj`` is the IR as journaled JSON, for the verbatim reading (else dumped from
    ``problem``). Deterministic: the syntactic readings, then the bounded solver checks of rule ``semantic-restatement``."""
    if problem is None or problem.query != "entailment" or problem.conclusion is None:
        return Restatement()
    req = list(request_texts)
    docs = list(request_documents or ())
    grounded = _regrounded(problem, report)
    by_id = {pr.id: pr for pr in grounded.premises}
    named = tuple(translator_circular_premises(grounded))
    translator_holds = bool(named) and all(assumed_grounding(by_id[pid].grounding) for pid in named if pid in by_id)
    readings = _Readings(grounded)
    conclusion = grounded.conclusion.model_dump(mode="json", exclude_none=True)["expr"]
    # a conjunct that holds under every assignment needs no premise (a proof that uses none is vacuous, E108): it is never
    # needed, so a tautology conjoined to the conclusion cannot keep the rest of it from being restated as a whole
    needed = {canonical_json(n): n for n in nnf_conjuncts(conclusion) if readings.valid(n) is not True}
    translator_parts = [(_translator_canonical(c), c.model_dump(mode="json", exclude_none=True)) for c in _translator_conjuncts(grounded.conclusion.expr)]
    obj = problem_obj if isinstance(problem_obj, dict) else json.loads(problem.model_dump_json(exclude_none=True))
    verbatim = {pid for pid in circular_premises(obj) if pid in by_id}  # the earlier verbatim reading (harness-stage correction)
    restates: dict[str, set[str]] = {}
    ways: dict[str, list[str]] = {}
    for pr in grounded.premises:
        p_expr = pr.model_dump(mode="json", exclude_none=True)["expr"]
        p_parts = nnf_conjuncts(p_expr)
        hit: set[str] = set()
        how: list[str] = []
        # the translator's definition: the conclusion, or each of its "and" conjuncts, is the premise or one of its conjuncts
        forms = {_translator_canonical(pr.expr)} | {_translator_canonical(c) for c in _translator_conjuncts(pr.expr)}
        for tkey, part in translator_parts:
            if tkey in forms:
                got = {canonical_json(n) for n in nnf_conjuncts(part)} & set(needed)
                if got - hit:
                    hit |= got
                    how.append("syntactic")
        if pr.id in verbatim and set(needed) - hit:
            hit |= set(needed)
            how.append("verbatim")
        same = {canonical_json(q) for q in p_parts} & set(needed)
        if same - hit:
            hit |= same
            how.append("syntactic")
        for key, node in needed.items():
            if key in hit:
                continue
            way = readings.restates(p_expr, p_parts, node)
            if way is not None:
                hit.add(key)
                how.append(way)
        if hit:
            restates[pr.id] = hit
            ways[pr.id] = list(dict.fromkeys(how))
    if not restates:
        return Restatement(named=named, translator_holds=translator_holds)
    order = [pr.id for pr in grounded.premises if pr.id in restates]
    sorts = {s.name: s.sort for s in grounded.symbols}
    # rule data-standing (decision 55): what a deterministic check shows of each restating premise
    standing = {pid: premise_standing(by_id[pid], report, req, sorts, docs, grounded, request_constraints=tuple(request_constraints)) for pid in order}
    why = {pid: (None if standing[pid].kind == TRANSCRIPTION else standing[pid].reason) for pid in order}
    own = tuple(pid for pid in order if why[pid] is not None)
    how_all = tuple((pid, tuple(ways[pid])) for pid in order)
    standings = tuple((pid, standing[pid].kind) for pid in order)
    shown = tuple(pid for pid in own if standing[pid].shown)
    undecided = tuple(pid for pid in own if standing[pid].kind == UNDECIDED)
    undecided_disclosed = tuple(pid for pid in undecided if disclosed_by_the_receipt(by_id[pid].grounding))
    whole = (bool(needed) and set().union(*restates.values()) >= set(needed)) or translator_holds
    if whole:
        return Restatement(named=named, holds=bool(own), own=own, grounded=tuple(pid for pid in order if why[pid] is None), translator_holds=translator_holds,
                           why_own=tuple((pid, why[pid]) for pid in own), how=how_all, standings=standings, shown=shown, undecided=undecided,
                           undecided_disclosed=undecided_disclosed)
    if not own:
        # restated in part by transcriptions only: they are its evidence, the rest is derived (nothing to grade)
        return Restatement(named=named, translator_holds=translator_holds)
    # the conclusion is not restated as a whole: its unrestated conjuncts are derived (or left open). A writer's-own premise
    # restating one of the others is graded by what the receipt discloses about it (rule receipt-disclosure)
    undisclosed = tuple(pid for pid in own if not disclosed_by_the_receipt(by_id[pid].grounding))
    return Restatement(named=named, translator_holds=translator_holds, why_own=tuple((pid, why[pid]) for pid in own), partial_own=undisclosed,
                       disclosed_own=tuple(pid for pid in own if pid not in undisclosed), how=tuple((pid, h) for pid, h in how_all if pid in own),
                       standings=standings, shown=shown, undecided=undecided, undecided_disclosed=undecided_disclosed)


def withheld_as_circular(o: ClaimVerificationOutcome) -> Optional[str]:
    """How the translator itself withheld a circular encoding of the outcome (rule ``circularity-agreement``): its
    pipeline rejected it (INVALID_FORMALIZATION with ``E112``, no problem carried), or its engine marked the ENTAILED
    proof circular (``E112`` on the result, displayed INVALID_FORMALIZATION). None otherwise."""
    tr = o.translation
    if tr.problem is None and tr.status is TranslationStatus.INVALID_FORMALIZATION and any("E112" in d for d in tr.diagnostics):
        return "the translator's pipeline rejected the encoding as circular (E112: INVALID_FORMALIZATION, no problem carried)"
    ver = o.verification
    if ver is not None and any(d.code == "E112" for d in ver.diagnostics):
        return f"the engine marked the proof circular (E112) and the outcome is displayed {o.display_status.value}"
    return None


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

    def describe(self, part: bool = False) -> str:
        if self.result_id is None:
            return f"could not be decided ({self.reason or 'no signed run'})"
        if self.follows:
            return "still gives ENTAILED" + (f", relying on {', '.join(self.relied_on[:8])}" if self.relied_on else "")
        if self.status == VerificationStatus.ENTAILED.value:
            return f"gives ENTAILED with {', '.join(self.diagnostics)}, a verdict the engine withholds ({self.reason})"
        if self.status == VerificationStatus.COUNTEREXAMPLE.value:
            return ("gives COUNTEREXAMPLE: the conclusion does not follow without the premise(s) restating part of it" if part
                    else "gives COUNTEREXAMPLE: the conclusion follows only from the premise(s) restating it")
        if self.status == VerificationStatus.INCONSISTENT_PREMISES.value:
            return "gives INCONSISTENT_PREMISES: no entailment is established without the restatement"
        return f"could not be decided ({self.status}{': ' + self.reason if self.reason else ''})"


#: The decisions rule ``engine-shown`` can give a restatement (:func:`engine_shown_grade`).
GRADE_CIRCULAR = "OVS-TRN-006"
GRADE_REDUNDANT = "OVS-TRN-010"
GRADE_UNDECIDED = "OVS-TRN-011"
GRADE_NOTE_REDUNDANT = "note:redundant"


def engine_shown_grade(rs: "Restatement", partial: bool, follows: Any) -> list[tuple[str, list[str], list[str]]]:
    """Rule ``engine-shown`` (decision 55), the grade of a delivered restatement as ``(decision, premises named, premises
    removed in the engine run that decides it)`` for each decision, in order. ``rs`` is the restatement
    (:func:`restatement`), ``partial`` whether only part of the conclusion is restated under an ENTAILED result (rule
    ``receipt-disclosure``), and ``follows(premise_ids)`` whether the engine run on the problem without those premises
    gives ENTAILED with no diagnostic that withholds it (the auditor's signed run in an audit, a plain engine run in the
    harness's re-derivation). Let R be the writer's-own restating premises graded (every one when the conclusion is
    restated as a whole; those the receipt does not disclose when only part is: rule ``receipt-disclosure``), S those a
    check SHOWS are not data (``own_kind``, ``refuted``, ``uncheckable``: a label alone is never data) and U those whose
    whole content rule ``same-quantity`` reads as their held source's data but no check verifies or refutes
    (``undecided``; R is S and U):

    1. the run without R gives ENTAILED: the result does not rest on the restatement: OVS-TRN-010 (a coverage note for a
       part restated);
    2. else S is not empty and the run without S (keeping U) does not give ENTAILED: OVS-TRN-006, the claim assumed;
    3. else S, if any, adds nothing beside U (OVS-TRN-010, a note for a part restated), and the result rests only on U
       (the run without R does not give ENTAILED), which shows only that a data conjunct needs its data premise:
       OVS-TRN-011 naming U. Whether the receipt lists a premise of U among the result's unverified dependencies (a
       supplied text) or presents it as given with the task (a task setting) changes nothing here: either way no check
       decides whether the source states it, so the accusation of it stays open.

    "p proves p" whose premise only a label presents as data is in S (decision 56), so it is OVS-TRN-006 by step 2: a
    result resting on it is the claim assumed, never a warning that clears."""
    circ = list(rs.own) if rs.holds else (list(rs.partial_own) if partial else [])
    if not circ:
        return []
    shown_c = [pid for pid in circ if pid in rs.shown]
    undecided_c = [pid for pid in circ if pid not in rs.shown]
    if follows(circ):
        return [(GRADE_NOTE_REDUNDANT if partial else GRADE_REDUNDANT, circ, circ)]
    if shown_c and not follows(shown_c):
        return [(GRADE_CIRCULAR, shown_c, shown_c)]
    out: list[tuple[str, list[str], list[str]]] = []
    if shown_c:
        out.append((GRADE_NOTE_REDUNDANT if partial else GRADE_REDUNDANT, shown_c, shown_c))
    out.append((GRADE_UNDECIDED, undecided_c, circ))
    return out


def engine_shown_codes(rs: "Restatement", partial: bool, follows: Any) -> list[str]:
    """The ``OVS-TRN`` codes rule ``engine-shown`` gives (:func:`engine_shown_grade`), sorted."""
    return sorted({d for d, _named, _removed in engine_shown_grade(rs, partial, follows) if d.startswith("OVS-")})


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


def _request_constraints(view: OverseerView, t: Transfer) -> list[str]:
    """The texts of the constraints the journaled request ``t`` answers sets on the answer (the request parser's records,
    their words copied from the request): rule ``statement-context`` reads each figure they state as a requirement on the
    answer, as their own sentence in the request states it."""
    req = view.by_seq.get(t.request_seq) if t.request_seq is not None else None
    r = req.request if req is not None else None
    return [c.text for c in r.constraints if getattr(c, "text", None)] if r is not None else []


def _request_documents(view: OverseerView, t: Transfer) -> list[Any]:
    """The texts supplied with the journaled request ``t`` answers (rule ``same-quantity``: the request, not the report, is
    the source a premise grounded in the task or a supplied text with no excerpt names, and it can only refute it)."""
    req = view.by_seq.get(t.request_seq) if t.request_seq is not None else None
    r = req.request if req is not None else None
    return list(r.supplied_texts) if r is not None else []


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
        # rule circularity-agreement: an encoding the translator itself withheld as circular (E112) leaves the circular
        # check nothing delivered to examine, so it is not listed as run: an accusation of it is never refuted by a check
        # that agrees with it (the validator says the translator withheld it)
        ran = ["revalidate", "status", "grounding"] + ([] if tr.problem is None and withheld_as_circular(o) else ["circular"])
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
            exact = stem_report(ctx, t)  # rule stem-exact-scale
            invented = untraced_content(tr.problem, problem_obj, report_scope(report), request_texts, supplied, exact_scale=exact)
            outside = untraced_content(tr.problem, problem_obj, cited_scope(claim, _cited_claims(claim, report)), request_texts, exact_scale=exact)
            outside_cited = tuple(dict.fromkeys(name for name, _d in outside))
            if invented:
                ctx.ovs(t.seq, "OVS-TRN-005", f"the IR proposed for claim {claim.claim_id} ({path}.translation) carries content the specialist's report never "
                        f"states (in no claim and nowhere in its response): {_listed([d for _n, d in invented])}", claim_ids=cid, formal_result_id=rid, **ids)
            # TRN-006 and TRN-010 (rules circularity-agreement, semantic-restatement, grounded-transcription and
            # receipt-disclosure: the premises restating the conclusion, or part of it, as written or in another form, that
            # are the writer's own for the overseer, never looser than the translator's E112 and never trusting a grounding
            # no deterministic check verified) graded by rule restatement-necessity (the auditor's own signed engine run
            # without them decides whether the result rests on them)
            problem_obj6 = json.loads(problem_json) if problem_json else None
            rs = restatement(tr.problem, report, request_texts, problem_obj6, request_documents=_request_documents(ctx.view, t),
                             request_constraints=_request_constraints(ctx.view, t))
            entailed = o.verification is not None and o.verification.status is VerificationStatus.ENTAILED
            partial = not rs.holds and bool(rs.partial_own) and entailed
            circ = list(rs.own) if rs.holds else (list(rs.partial_own) if partial else [])
            transcribed = list(rs.grounded) if not rs.holds else []
            ways = {pid: how for pid, how in rs.how}

            def in_form(pids: list[str]) -> str:
                forms = [f"{pid} " + "; ".join(RESTATEMENT_WAYS[w] for w in ways[pid] if w in SEMANTIC_WAYS) for pid in pids[:4]
                         if any(w in SEMANTIC_WAYS for w in ways.get(pid, ()))]
                return f" (rule {SEMANTIC_RULE}: {'; '.join(forms)})" if forms else ""
            if circ:
                # rule engine-shown (decision 55, engine_shown_grade): the grade follows what the auditor's own signed engine
                # runs SHOW. A restating premise a check shows is not data (the writer's own by kind, refuted by its source or by
                # the translation's own declarations, naming no source the overseer holds, or, decision 56, presented as data on
                # a kind label alone: content no check reads in its source) carries the claim assumed when the result rests on
                # it (OVS-TRN-006); one whose whole content rule same-quantity reads as its source's data, which no check
                # verifies or refutes (undecided), shows, when the result rests on it, only that a data conjunct needs its data
                # premise (OVS-TRN-011, whatever the receipt says of it: no check decides whether its source states it). The
                # runs are memoised in the store, so asking again for a run of the same reduced problem cites the same signed run.
                undecided_c = [pid for pid in circ if pid in rs.undecided]
                reasons_of = {pid: why for pid, why in rs.why_own}
                if rs.translator_holds:
                    whose = (f"the translator's own circularity rule (E112) holds on this IR as re-grounded here, so it reached the receipt past that rule "
                             f"(rule {AGREEMENT_RULE})")
                elif partial:
                    whose = (f"the translator's circularity rule (E112) reads only a conclusion every conjunct of which is restated as written by the writer's "
                             f"own premises, so it delivered this encoding (rules {DISCLOSURE_RULE} and {TRANSCRIPTION_RULE})")
                else:
                    whose = (f"the translator's rule (E112) reads a restating premise grounded in the task or a text as a transcription on its label alone, "
                             f"reads a restatement only as written, and passes a conclusion part of which a verified premise restates; no deterministic "
                             f"check verified the premise(s) named here (rules {TRANSCRIPTION_RULE} and {SEMANTIC_RULE})")

                def run_without(pids: list[str], obj=problem_obj6) -> Necessity:
                    return restatement_necessity(ctx, t, obj, pids)
                for decision, named_ids, removed in engine_shown_grade(rs, partial, lambda pids: run_without(pids).follows):
                    nec = run_without(removed)
                    shown = _named(named_ids)
                    runs = [nec.result_id] if nec.result_id else []
                    # each premise's reason: in full in the audit note, and in the finding after its evidence (fit_reasons), so
                    # the message cap never cuts the auditor's signed run or the rule
                    reason_items = [f"{pid}: {reasons_of[pid]}" for pid in named_ids if pid in reasons_of]
                    reasons = "; ".join(reason_items)
                    if decision == GRADE_NOTE_REDUNDANT:
                        # part of the conclusion is restated under a grounding no check verified, but the result does not
                        # rest on it: the other premises derive that part too (no finding)
                        ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: premise(s) {shown} state part of the conclusion"
                                 f"{in_form(named_ids)} under a grounding no check verified ({reasons}); the auditor's run {nec.result_id} without them "
                                 f"{nec.describe()}: the result does not rest on them (rule {NECESSITY_RULE}: no finding)")
                    elif decision == GRADE_REDUNDANT:
                        own = set(o.verification.premises_relied_on) if o.verification is not None else set()
                        core_note = (f"; the outcome's own signed result relied only on the restatement ({', '.join(sorted(own)[:6])}) in place of the "
                                     "derivation" if own and own <= set(named_ids) else "")
                        ctx.ovs(t.seq, "OVS-TRN-010", fit_reasons(
                            f"redundant restatement in the translation of claim {claim.claim_id} ({path}.translation): premise(s) {shown} restate the "
                            f"conclusion{in_form(named_ids)} and are the writer's own, but the auditor's own signed engine run on the problem without them "
                            f"{nec.describe()} (rule {NECESSITY_RULE}): the result does not rest on the claim assumed, and the restating premise(s) add "
                            f"nothing{core_note}", "why each is the writer's own", reason_items),
                            claim_ids=cid, formal_result_id=rid, related_result_ids=runs, **ids)
                        ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: premise(s) {shown} restate the conclusion; the "
                                 f"auditor's run {nec.result_id or '(none)'} without them {nec.describe()}: redundant restatement (OVS-TRN-010); {whose}"
                                 + (f"; why each is the writer's own: {reasons}" if reasons else ""))
                    elif decision == GRADE_CIRCULAR:
                        kept = (f"; the premise(s) {', '.join(undecided_c[:4])}, presented as data that no check verifies or refutes, were kept in that run"
                                if undecided_c else "")
                        if partial:
                            what = (f"part of its conclusion is restated by premise(s) {shown}{in_form(named_ids)} that a deterministic check shows are not "
                                    f"data and that the receipt presents as given with the task, not as an ungrounded or unverified dependency (rules "
                                    f"{DISCLOSURE_RULE} and {STANDING_RULE})")
                            rests = "so the displayed result rests on that part of the claim assumed under a label, not on the specialist's reasoning"
                        else:
                            beside = (f", beside the transcription(s) {', '.join(rs.grounded[:4])}{' and more' if len(rs.grounded) > 4 else ''} a "
                                      "deterministic check verified" if rs.grounded else "")
                            what = (f"its conclusion is restated as a whole (each of its conjuncts by a premise), and the restating premise(s) {shown}"
                                    f"{in_form(named_ids)} are the writer's own, as a deterministic check shows{beside}")
                            rests = "so the engine result rests on the claim assumed, not on the specialist's reasoning"
                        ctx.ovs(t.seq, "OVS-TRN-006", fit_reasons(
                            f"circular translation of claim {claim.claim_id} ({path}.translation): {what}, and the auditor's own signed engine run on the "
                            f"problem without them {nec.describe(partial)} (rules {NECESSITY_RULE} and {ENGINE_SHOWN_RULE}){kept}, {rests}; {whose}",
                            "what a check shows of each", reason_items),
                            claim_ids=cid, formal_result_id=rid, related_result_ids=runs, **ids)
                        ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: premise(s) {shown} restate "
                                 + ("part of " if partial else "") + f"the conclusion; the auditor's run {nec.result_id or '(none)'} without them "
                                 f"{nec.describe(partial)}: circular (OVS-TRN-006); {whose}" + (f"; what a check shows of each: {reasons}" if reasons else ""))
                    else:  # GRADE_UNDECIDED
                        listed = [pid for pid in named_ids if pid in rs.undecided_disclosed]
                        given = [pid for pid in named_ids if pid not in rs.undecided_disclosed]
                        how_shown = "; ".join(x for x in (
                            f"the receipt lists {', '.join(listed[:6])} among the result's unverified dependencies" if listed else "",
                            f"the receipt presents {', '.join(given[:6])} as given with the task" if given else "") if x)
                        ctx.ovs(t.seq, "OVS-TRN-011", fit_reasons(
                            f"restatement under an undecided data grounding in the translation of claim {claim.claim_id} ({path}.translation): premise(s) "
                            f"{shown} restate " + ("part of " if partial else "") + f"the conclusion{in_form(named_ids)} as data the request or a supplied "
                            f"text holds, each figure read there for the quantity the premise names (rule {SAME_QUANTITY_RULE}), which no deterministic "
                            f"check verifies as a transcription (no located excerpt) or refutes ({how_shown}), and the auditor's own signed engine run on the "
                            f"problem without them {nec.describe(partial)} (rule {NECESSITY_RULE}): that shows only that a data conjunct needs its data "
                            f"premise, not that the claim was assumed (rule {ENGINE_SHOWN_RULE}); whether the source states it, for the same quantity, is "
                            "a meaning question for overseer agents (Inspection I77, I78)", "why no check decides", reason_items),
                            claim_ids=cid, formal_result_id=rid, related_result_ids=runs, **ids)
                        ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: premise(s) {shown} restate "
                                 + ("part of " if partial else "") + f"the conclusion as undecided data; the auditor's run {nec.result_id or '(none)'} "
                                 f"without them {nec.describe(partial)}: OVS-TRN-011 (rule {ENGINE_SHOWN_RULE}); {whose}"
                                 + (f"; why no check decides: {reasons}" if reasons else ""))
            if rs.disclosed_own and not rs.holds and entailed:
                shown_d = ", ".join(rs.disclosed_own[:6])
                ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: premise(s) {shown_d} state part of the conclusion"
                         f"{in_form(list(rs.disclosed_own))} as the writer's own, and the receipt discloses each as an ungrounded or unverified dependency "
                         f"while the rest of the conclusion is derived (rule {DISCLOSURE_RULE}: no finding; whether the part assumed is the claim's point "
                         "rather than a fact it states is a meaning question for overseer agents)")
            if transcribed:
                ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id} transcribes a grounded fact: premise(s) {', '.join(transcribed[:6])} "
                         f"restate the conclusion{in_form(transcribed)} under a grounding a deterministic check verified against the request or a located "
                         f"excerpt (rule {TRANSCRIPTION_RULE}: not circular; the result tests transcription only)")
        else:
            withheld = withheld_as_circular(o)
            if withheld:
                ctx.note(f"translation of claim {claim.claim_id} on {t.kind} {t.message_id}: {withheld} (rule {AGREEMENT_RULE}: no OVS-TRN-006 or OVS-TRN-010)")
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
