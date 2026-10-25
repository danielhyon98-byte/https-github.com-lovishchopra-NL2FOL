# translate — from specialist claims to IR

Flow for one claim: `eligibility.decide_eligibility` (deterministic rules by claim
role and proposed kind) → `subjects.resolve_profile` applies the IB subject policy
(a class the subject does not allow is downgraded to not eligible) → the
`Translator` in `pipeline.py` builds a `TranslationRequest` (claim, supporting
claims, supplied texts, eligibility, subject profile text) → a `TranslationProvider`
proposes JSON → `parsing.parse_json_object` (strict) → `Problem.model_validate` and
the engine validator → `grounding.check_problem_grounding` checks every source reference (an excerpt
located, a document and locator checked), keeps each reference's outcome (`GroundingCheck.ref_index`) and
the target's support (`complete`, `partial`, `failed`, `uncheckable`; only complete support verifies), and
validates the task authority a kind claims (see below) → coverage (`coverage.py`): two encoding shapes leave a
figure open, a premise that only defines an atom by a comparison of a figure no other premise mentions
(`b <-> (n = 17)` with `n` free) and a conclusion that compares symbols no premise mentions (`x < y` with `y`
free). Whether a source ASSERTS what the shape leaves open is read clause by clause from the source's grammar
(`assertion.py`, below), never from the presence of a numeral, in every source for both shapes: the claim, its
supporting claims, the supplied texts and the task record (a figure of a supplied text or of the task is
evidence about a free conclusion symbol only in a clause about that symbol: it names it, counts what describes
it, or shares the words that describe it; the answer's own figures may also link by their value when nothing
describes the symbol), and decided here and handed to the engine as
an application record (`apply_coverage_evidence`: a grounding verified in this process on exactly the symbols
involved, its references the asserting clauses; any other symbol of the shape carries no verified grounding).
The engine therefore reports `E110`/`E111` (no verdict) exactly when a source asserts it and the advisory
`W110`/`W111` otherwise (the counterexample stands as the verdict on the encoding): the coverage note
(`TranslationResult.coverage`), the signed result and the displayed status are one decision. An `E110`
output is INVALID_FORMALIZATION with the asserting clause, fed back once; no translator is told to add a
premise because adding it would produce entailment, only because a source asserts it, and the retry may add
only that: every premise it adds must follow from the earlier premises with the source-asserted atoms
asserted (the stated figure, the atom, a reformulation of the definition) or be established by a grounding
check (`precision.added_premise_support`); anything else makes the translation AMBIGUOUS_TRANSLATION
(`retry_added_premise`), never a verdict, and the release assessment names it → circularity: an
encoding whose premises restate its conclusion from the writer's own assertions (the engine's `E112`; an
`arithmetic_fact` no record validates, or a grounding a check refuted, counts as the writer's own) is
INVALID_FORMALIZATION, fed back once → stated precision and exactness (`precision.py`, read from the
wording by `quantities.py`, never from the solver): every figure the encoding compares is tied to the span
that states it (`TranslationResult.figure_readings`). A figure stated exactly ("exactly", "without
rounding") or given by the task is encoded with `eq` and never widened (an interval in its place is
rejected: "exactness: ..."); a figure stated as rounded (a rounding cue, or the result of a calculation
written before it that, computed as written by a closed arithmetic reader, the figure rounds: "−12.50 ÷
18.75 = −0.67"; an approximation word or sign is a cue only for the figure it is written against, so
"think about it", "almost certain", "about 2 people" or "x ≈ 1/3 so x = 0.33" state nothing about another
figure, and "without approximation" states exactness) must be encoded at exactly its stated tolerance when that tolerance changes the verdict
("stated precision: ...", fed back once with the bounds; a wider or narrower interval is rejected); a
calculation that gives its result exactly ("$2.00 − $0.40 = $1.60") states that result exactly; a figure
is such a result only when the calculation ENDS at its '=' and the figure ends the expression (the words
before the sign are units of the calculation's operands only when the unit table, a currency or a scale
word reads them; the calculation starts with an operand): in "If x = 1/3 then x = 0.33", "x = 1/3
implies x = 0.33", "x × 3 = 1.00", "HR = 72" or "= 3 − 1" the sign equates the figure with a variable,
a symbol or an expression that holds one, so only the figure's cues decide its exactness; a result
of a calculation the reader cannot compute is rounded only by the convention of written calculation, a
presumption that may explain a failure (the exact equality is rejected when the exact reading fails and
the stated reading gives another verdict) but never refutes a proof (one that needs the result exactly is
AMBIGUOUS_TRANSLATION); a decimal the claim writes with no cue whose reading decides the verdict makes the
translation AMBIGUOUS_TRANSLATION with both readings recorded → retries: an accepted attempt after a
rejected one is recorded in `TranslationResult.repairs`, a syntax repair or a semantic change with every
change listed; after a semantic rejection the new conclusion is compared with the earlier one read as its
source states it, and a weaker or incomparable conclusion is AMBIGUOUS_TRANSLATION (`retry_changed_claim`):
a retry that weakens the claim cannot inherit its approval → a conclusion label that states a figure its
expression does not check is recorded as a note (`label_beyond_expression`) and shown beside the label in
the outcome summary; the verdict is unchanged → status TRANSLATED, AMBIGUOUS_TRANSLATION, UNSUPPORTED,
INVALID_FORMALIZATION, NOT_ELIGIBLE or TRANSLATION_FAILED. `outcome.display_status_for` displays a
definitive result carrying `E108` (vacuous), `E110` (unasserted figure), `E111` (unencoded reason) or `E112`
(circular) as INVALID_FORMALIZATION, never as a verdict (the engine's `NO_VERDICT_CODES`; it reports
`E110`/`E111` only with the source evidence the coverage step handed over); the advisory `W110`/`W111` leave
the counterexample standing and the summary carries an "Advisory coverage warnings" line. A result that is
not current-policy evidence (another release's versions, build, schema or policy identity, or non-default
limits: `engine.provenance.stale_reasons`) is displayed INTERNAL_ERROR: verify the problem again. An
AMBIGUOUS_TRANSLATION's result is described as the translator's chosen encoding of one reading, run for
inspection.

`widen_rounded_literals` remains as a helper that reads EVERY decimal equality of a problem as its
half-unit interval; it is no longer a decision rule (it ignores the wording).

Rules added for the round-7 arena hand-off:

- A relayed peer specialist's report (`grounding.is_peer_document`: a document id `peer:<task>`, or an author
  `<subject>-specialist`) is evidence of what that agent said, never a source: an excerpt located in it leaves the
  grounding unverified (`verified = None`, detail `peer_report: ...`), so a premise it supports stays an unverified
  dependency and the release check refuses it; a peer report confers no task authority either.
- A figures or verbatim check verifies a premise only when the excerpt's figure is about the premise's quantity: when
  the figure's asserting clause names years and none of them is a year the symbol's name or meaning names ("In 2020
  Lowtown had 252 residents" for `p2010`), the match is refused as another year's figure (rule same-quantity,
  conflicting qualifier).
- An approximation cue with no stated precision on a whole number ("about 100%") reads the figure at half a unit of
  its last written digit ([99.5, 100.5]), never at its first significant digit ([50, 150)), so a 55% growth is not
  "about 100%" and a faithful narrow encoding is accepted. After a stated-precision rejection the reference reading
  used to judge a retry is rebounded to the demanded bounds (`precision.reference_reading`), so a retry that encodes
  exactly the demanded interval is no weakened claim (`retry_changed_claim`); the rejection names the figure as
  written ("0.33 (the interval's midpoint 0.3325)").
- A partial encoding is never a silent verdict: a claim figure no literal of the problem encodes, and a clause whose
  figures the conclusion checks none of, are recorded as notes ("part of the claim only: ..."), and when the
  translator's own reading says part of the claim is not encoded the translation is AMBIGUOUS_TRANSLATION with the
  flag `partial_encoding` (code numerals, such as a binary string, are not claim figures).
- A translation record of another translator release ("0.3.0" where the current one differs) is stale
  (`outcome.translation_staleness`): displayed INTERNAL_ERROR, release not permitted, "translate and verify again".
  A record a caller built in process with no release version is read as it stands.
- Provider output holding a lone UTF-16 surrogate is a `ProviderOutputError` (`parsing.parse_json_object`), so the
  translation is INVALID_FORMALIZATION and nothing raises (POST `/v1/outcomes` answers it).

Assertion (`assertion.py`). Mentioning a figure is not asserting it. A figure supports a coverage finding only
when (1) its clause asserts it: no question, instruction or supposition opening the sentence, and no
condition (including "when" read as a condition: "When n equals 17, b holds"; "when" after a time expression
or with a past-tense verb relates a fact: "in 1960, when seventeen African states became independent"),
supposition or hypothesis, claim put forward to be tested, example, definition, possibility, obligation,
intention, hedge, attribution (reported speech), negation, quantification or disjunction governs its coordinate
unit (a biconditional connective, "iff", "exactly when", "⟺" or "<->", governs the two clauses it joins; a
symbolic implication, "⇒", "→" or "=>", is a condition), it is no end of a range or option of a disjunction,
and the reader POSITIVELY recognises its clause as the writer's own statement: every symbol and closed-class
word in it is one an assertion may hold (no quantifier, modal, hedge, frequency adverb, logical sign or
unrecognised subordinator), a label before a colon presents what follows as given ("Given:", "Data:"), no verb
of report, estimate or judgement takes the figure as its content, and the words before the figure's clause
are recognised frame elements (connectives, factual subordinators such as "since" and "given", relative
pronouns, factive frames such as "We are told that" or "It turned out that", time and place adverbials, whole
clauses ending at a recognised boundary, a raising verb of fact before "to be": "n turned out to be 17", "n is
known to be 17"); (2) what it
states establishes the comparison the encoding defines ("more than 17" establishes no `n = 17`; "nearly
790,000" establishes `n < 790000`); (3) it is about the encoding's symbols: its clause names them as a formula
does, or shares the words that describe them (meanings, names, the definition's label, the source's own
clauses that name them), and it does not count something else ("I checked 3 values"). Whatever the reader
does not recognise is no evidence, so the counterexample stands with the advisory ("Rumour has it n is 17",
"In this scenario n is 17", "Claim to test: n is 17", "n is 17 in some cases", "n = 17 ⇒ b" and "b ⟺ n = 17"
all keep W110/W111); the coverage note's detail names, for each mention passed over, the construction that
decided it (`unrecognised` with the word or sign it did not recognise). The reader is lexical, so its errors
are conservative: a genuine statement in a construction it does not recognise is read as unasserted (the
counterexample stands with the warning), and the one shape it can still misread as asserted is an unknown
verb of report or opinion before a bare clause ("Pupils opine growth was 17"), which is why the E110 retry
is also checked as above. Scope: a sentence ends at a full stop before a capital or before a lower-case symbol
that opens a statement ("Define b. n = 17." is two sentences, so the instruction does not govern n = 17), never
after an abbreviation ("e.g.", "i.e.") or before a lower-case word that continues the sentence ("Suppose b
holds. then n = 17."); a question opened by a clause that presents a fact ("Given x = 5 and y = 9, is x <
y?") governs only what follows that clause, so the given is asserted; the frames that name the task ("In this
problem", "In this question") present its given, while a hypothetical frame ("In this scenario") stays
unrecognised; the numeral of a precision cue is no end of a range ("0.33 to 2 decimal places" states 0.33).
It is linear in an untrusted text (`tests/translate/test_coverage_assertion.py`,
`tests/translate/test_positive_assertion_reader.py`, `tests/translate/test_record_coverage_and_rounded_givens.py`).

Typed quantities (`quantities.py`). Figures of source text are read with the bounded STEM number scanner
and a closed table of number words into exact values with their unit (percent, per mille, percentage
point, currency, a STEM-table unit), scale word and written precision. An IR literal corresponds to a
stated figure as written or after ONE recorded derivation (`20% = 20 x 0.01 = 0.2 (dimensionless)`, a
scale word, a unit conversion to the unit the symbol's meaning declares); `0.2` and `1/5` agree, and a
symbol declared a dimensionless fraction, in per cent, or in a unit admits only the consistent
derivation (`tax_rate = 20` against "20%" for a dimensionless rate is a mismatch). A figure stated as
rounded (a rounding cue: "x is 0.33 to 2 decimal places", "about 0.33", "0.33 (3 s.f.)") also states the
interval of its tolerance (`quantities.stated_intervals`), so a premise that transcribes a rounded given exactly
(`x = 0.33`) or at exactly its stated tolerance (`x >= 0.325 and x < 0.335`, both ends from that one figure)
is grounded by it, with the derivation recorded; a wider, narrower or shifted interval is not what the record
states, and an exact or given figure (no cue) states no interval, so an interval in its place stays
unestablished (and the precision step rejects it). A supplied text is
untrusted and may be long, so the reader stays linear in it: cues, figures, sentences, clauses and the
cue that governs a figure are found through indexes (a coverage map, bisection, the cues near the figure),
never by rescanning what was already read, and the coverage check reads each clause once
(`tests/translate/test_quantities_linear_time.py`).

Task authority. `arithmetic_fact`, `task_setting` and `rubric_rule` claim the task's authority; only the
supplied texts and the task record (`contracts.TaskRecord`, passed as `Translator.translate(...,
task=...)` / `verify_claim(..., task=...)`) confer it. A check confers it only on the premise's WHOLE
numeric content (`relations.py`): an assignment (each symbol compared with a literal: `distance = 120`,
`n > 15`) is validated when the records state each figure so that it establishes that comparison
(`numeric_in_task`; "more than 120" validates no `distance = 120`, and a figure the record negates in its own predicate, "the distance is not 120", validates nothing); any other numeric content, a relation
that combines symbols (`speed = distance / 8`, `c = 3 + 2 * k`), is validated only when a record states that
same formula as a given (`relation_in_source`; a closed formula reader compares the stated formula's
structure with the premise's, symbols and figures alike, and evaluates nothing; a formula in a question,
a condition or a claim to test is no given). The figures of a relation occurring in a record are no evidence
for the relation that combines them. A premise of such a kind is validated, refuted (the task record was
given and no record states the figure, or the records state another figure of the same unit: 120 km where
the premise says 160 km; `verified=False`, an evidence failure the engine lists as an ungrounded dependency)
or unvalidated (`verified=None` with a `numeric_in_task` or `relation_in_source` check whose `verified` is
None: never trusted by this layer; the engine lists it as an unverified dependency, since no kind is exempt
there either: `engine.authority`). A model-invented relation therefore stays an unverified dependency and
blocks release whatever its grounding label, also when a located excerpt supports its quotation, and the
outcome summary lists it under "Unverified relations".

Release (`outcome.assess_release`, `ClaimVerificationOutcome.release`). Formal entailment is kept apart
from permission to release the answer: release needs the passing formal status for the query, the engine's
own release check of the signed result (`engine.release.release_check` under the composer's key:
authenticated, bound, current, a positive verdict on the claim, its evidence computed, no unresolved
dependency; without the key release is never permitted), every relied-on premise established, no failed
grounding check, no partial reference support, no unvalidated task authority, no retry that changed the
claim, no structural error, and a `faithful` fidelity review made with the evidence and bound to the current
inputs. Each unresolved item is listed; the formal status is never changed by it. No component of the
channel or hub releases answers automatically today: the assessment is reported on every outcome and in its
summary for the application that does.

Eligibility counts figures on `eligibility.figure_text`: mark annotations ("[2]", "[2 marks]"), part
labels ("(a)", "(iii)", "Part (b)") and named items ("Paper 1") are not figures, so a heading is not
a quantitative claim. Evidence is a QUANTITATIVE_CLAIM only with two related figures or a
comparative; a single date or figure is not (its only encoding would restate it).

`review.py` runs an independent, advisory semantic-fidelity review. Its request carries the evidence the
encoding must be faithful to: the original task (when the caller holds the task record), the supporting
claims' contents, the supplied texts (a very long text is shown in part and named), every input's identity
and digest, the premise-to-source mapping with the deterministic checks, and the figure readings. The review
is bound to those inputs and their versions (`ReviewBinding`); `review_currency` says whether a review is
current, stale (a supporting claim, supplied text, task or problem changed, even with the claim text
unchanged), unbound, or made without evidence. `outcome.py` composes the Overseer-facing
`ClaimVerificationOutcome` (display status derived from the signed engine result; release assessment kept
separate; summary ends with the scope statement) and offers `verify_claim` as the one-call path translate →
verify → review → compose.

`providers/` holds the provider interface, a fixture provider for tests, and
Anthropic / OpenAI-compatible adapters (implemented, untested live). `prompts/`
holds versioned prompt texts; the version string is bound into each result. A
changed prompt is a new file and version: `translate_v2` and `review_v2` are in
use; `translate_v1` and `review_v1` stay packaged unchanged.

The completion entry point `providers.base.CompletionProvider` (`complete(system, user, *,
prompt_version) -> ProviderResponse`) is the public form of the `_complete` the vendor adapters
already use: the caller supplies both texts and the provider adds nothing, while retries,
timeouts, `ProviderInfo` (which records `prompt_version`) and `ProviderError` are reused
unchanged. Both vendor adapters implement it; `propose` and `review` are unchanged. The overseer
agent runner (`epinoic_logic.overseer.runner`) calls it with a knowledge pack's system text and one
dossier, and its reply is untrusted data parsed only by the verdict intake.
`FixtureCompletionProvider` serves canned replies keyed by dossier digest or in order, raises a
canned `ProviderError` and records every call; no live provider is claimed.

`grounding.py` locates a quotation in tiers (verbatim; typographic normalisation, with
quote marks folded, every dash variant read as one dash with the spaces on both sides of it dropped, in the text and
the excerpt alike, so `like - just as I -` typed for the poem's `like—just as I—` is the same quotation, and verse line
breaks written as slashes; an elision within the window; then the form-difference tier: an initial capital, a line-break
mark, the text's own double speech mark at a line or stanza start or end left out of a quotation that runs across the
break, with ` / `, ` // ` or no break mark (every stanza of 'The Man He Killed' opens with one: "omits the text's own
speech mark at a line or stanza start or end"), diacritics folded with NFKD and combining marks dropped, a long
elision). An elision mark written in the academic form, in brackets or
parentheses (`[...]`, `[…]`, `[ . . . ]`, `(...)`), is read as the same ellipsis in every tier (`unbracket_elisions`), so
a correct elided quotation is never reported as invented. A located excerpt verifies a premise only when it states the premise's whole content:
an assignment's figures, each stated so that it establishes the comparison (the figures of its literals as typed quantities, fractions included;
0, ±1, 10, 100 and 1000 aside unless the premise assigns one): a premise `it1 = 3` grounded in "scores = [12, 19, 23" is not verified
(`GroundingCheck.method` `figures_in_excerpt`), while `0.325 <= x < 0.335` grounded in "x is 0.33 to 2 decimal places" is (the
interval that rounded figure states, its derivation in the check's detail); a relation only when the located span states that same formula as a given (`relation_in_source`),
never because its figures occur there. A form difference never verifies a
grounding but is reported as one ("differs in form", the channel's INT-REQ-010), never as an
invented quotation; accents encoded differently (precomposed against combining) are the same
letters and a normalised match. Each supplied text's normalised forms and offset maps are
built once and cached per `(document_id, sha256 of the text)` in a bounded LRU
(`TextForms`, `text_forms`), and every locating answer is memoised per excerpt and text, so
a parse and its checks never locate one excerpt in one document twice; the caches are
thread-safe and `clear_grounding_caches()` empties them. Hashing agent text never raises: `contracts.sha256_text`
(like `ir.canonical.sha256_hex` and the grounding cache's `text_sha256`) encodes a lone UTF-16 surrogate with
`surrogatepass`, so valid text hashes exactly as before and the channel can refuse such text (INT-REQ-009) instead of
raising.

**Overseen like every other agent.** Every translation this package proposes reaches the router inside a receipt
outcome, and the Overseer re-checks it from its journal as untrusted data (`epinoic_logic.overseer.checks.translation`,
codes `OVS-TRN-001` to `OVS-TRN-009`): the IR re-validated with the engine's validator, the status and eligibility
re-derived, the quotation groundings re-run against the supplied texts, every quotation and number traced to the
specialist's report, a conclusion found among its own premises flagged as circular, the outcome summary regenerated from
the signed result, and two receipt-level warnings (a definitive display resting on unsuccessful sibling claims; one fact
a premise in one translation and unsupported in another). No check depends on who proposed the IR: a problem this
pipeline produced always records its provider, and one that records none is reported unless the operator declared its
translator hand-built. The signed task audit records each translation (claim text, proposed IR, validation outcome, signed
result). Nothing in this package changed for it: the checks only read what the pipeline already records.
