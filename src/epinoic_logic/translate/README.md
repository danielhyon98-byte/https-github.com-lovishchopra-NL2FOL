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
encoding whose premises restate its conclusion from the writer's own assertions (the engine's `E112`; a
premise no check in this process established counts as the writer's own whatever kind its grounding claims,
`engine.authority.assumed_grounding`, policy 2026.10-v5) is INVALID_FORMALIZATION, fed back once → stated precision and exactness (`precision.py`, read from the
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
verify → review → compose. A translation record this translator did not make is displayed INTERNAL_ERROR whatever
its status and never released (`translation_staleness`): one of another `translator_version`, or one bound to no claim
text (no `claim_text_sha256`, which every record of contract 0.2 and later carries), must be translated and verified
again (integration contract, section 9); the engine result verified for its problem is rejected with it, and the
summary and the release assessment say why. A report's notes are bounded by its contract (`contracts.NOTE_MAX_CHARS`
per assumption, assessment criterion or unresolved issue; `REPORT_NOTES_MAX_CHARS` for a report's notes together), so
an oversized report is refused (the channel's INT-REQ-009) instead of being held and copied into every receipt. A
report or claim that states no `course_level` (`None`) reads it as `"unknown"`, the same meaning, so a report re-read
from its delivered payload is the report delivered and its faithful forward is not refused as altered in transit.

Argument diagnosis (rules `argdiag-2`; the record and its rules are in `named.py`):
- `roles.py` records how each premise is marked, in `TranslationResult.premise_roles`:
  - the role: `fact`, `link`, `either_or`, `definition` or `figure_relation`;
  - the authority, read from the grounding check and never from the label: `established`,
    `unverified`, `refuted` or `writer_own`;
  - the marking: `translator_link`, `translator_rule`, `source_link`, `unmarked_link`,
    `label_conflict` or `fact`;
  - the writer's connective, when one is given.
- `diag_core.py` builds the context of one claim and runs the claim-layer rules
  (`diag_argument.RULES`, `diag_evidence.RULES`; `claim_diagnostics`). It also runs the
  report-layer rules once per delivered report (`report_diagnostics`).
  - Every rule is guarded: one that raises or returns anything else fires nothing and is named in
    `diagnosis_incomplete`.
  - Caps, the suppression of dominated generic diagnostics, ordering and the bounds apply in both
    entry points: 32 per claim and 256 per report.
  - `diag_evidence.RULES` and `REPORT_RULES` hold the evidence family: `EVD-SRC-001` (a needed fact premise whose
    text or task authority no check verified), `EVD-SRC-003` (its grounding check failed), `EVD-SRC-004` (the provider
    wrote its own `verified: true`, discarded; info), `EVD-LACK-001` (a needed fact premise that claims no source),
    `EVD-FIG-001` (a figure no supplied text or task record states, no written calculation's result, no from-memory
    label), `EVD-AUTH-001` (an unattributed authority or data cue), `EVD-CHERRY-001` (a period's own end values reverse
    the point; months and recoveries too), `EVD-SRC-005` (a task-authority premise the task material does not hold; a
    label that spells a task sentence's notation in words is none: `grounding.spells_notation`, which the grounding
    check also reads, so such a premise is validated by that sentence and never refuted by absent words), and the report rules `EVD-SRC-006` (a source credited
    with the opposite stance of what it states; warning, repair round 2), `EVD-SRC-002` and `EVD-LACK-002` (info: "not
    checked", never "false"). A premise whose every failed check is a form difference is no `EVD-SRC-003`. The
    source-bound warnings are warnings only when the request names supplied material as the basis of the answer
    (`source_bound`, `supplies_data_texts`), info with `capped_from` otherwise. The content stems of a supplied text are
    computed once per text (`_text_stems`), so the report rules cost one pass per claim and document.
  - `diag_argument.RULES` and `REPORT_RULES` hold the argument family's claim and report rules: `ARG-EQ-001` (the
    translation flagged one word read in two senses; never capped), the claim form of `ARG-CIRC-001` (the translation
    was refused as circular; info when it only restated a bare fact stated from subject knowledge with no reason) and
    `ARG-BARE-001` (a judgement the request asks to be reasoned, by its command term, "recommend" included, or by "with
    reasons", stands with no reason in its answer section; a judgement whose sentence quotes a supplied text is none).
    The pipeline's circularity refusal also reads a restatement in other terms (`runner.equivalent_premises`), and
    yields when the premises contradict each other (`runner.premises_inconsistent`: the engine then decides
    INCONSISTENT_PREMISES, consistency before entailment; repair round 2), and the answer texts it gives the grounding
    checks include the report's original response, so a figure derived in an earlier sentence grounds. The rules,
    the encoding flags (`UNLINKED_CONJUNCT`, `UNENCODED_REASON`, `PARTIAL_ENCODING`) and the precision readings of the
    same release are in `ARGUMENT_DIAGNOSTICS.md`; every label is described in `docs/ARGUMENT_DIAGNOSTICS.md`.
- `outcome.py` puts the trusted engine result's named diagnostics, merged with the claim layer's,
  into `ClaimVerificationOutcome.named_diagnostics`.
  - Only an engine result that binds, is current and has a verified signature counts as trusted.
    Without one, the engine layer is "not computed".
  - The summary shows them in a section after the verification lines, and the status is never
    changed.
  - `assess_release` (`release-v2`) lists "named defect on this claim: <codes>" by effective
    severity.
  - `verify_claim` passes `severity_cap=("info", "ambiguous_translation")` for an
    AMBIGUOUS_TRANSLATION.
- The translator's internal probes (`precision.py`, the figure probe in `pipeline.py`) pass
  `diagnose=False`, so their results are never release-eligible.

`providers/` holds the provider interface, a fixture provider for tests, and
Anthropic / OpenAI-compatible adapters (implemented, untested live). `prompts/`
holds versioned prompt texts; the version string is bound into each result. A
changed prompt is a new file and version: `translate_v3` (which marks the writer's own
links, `ARGUMENT_DIAGNOSTICS.md`) and `review_v2` are in use; `translate_v1`, `translate_v2` and
`review_v1` stay packaged unchanged.

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
never because its figures occur there. A located excerpt verifies a proposition only as a literal (an atom or its negation):
joined to the writer's own proposition with "and", "or", "if" or "iff" it stays unverified and the connective is named as
the writer's. A relayed specialist's report confers no authority (`peer_report`): it is recognised by its id (`peer:`,
`peer-`, `peer_`, `report:`), its author (an agent or a `<subject>-specialist`) or its provenance ("relayed", "peer"),
whatever its title (`is_peer_document`, repair round 2). The subject words that tell one entity or quantity from another
leave out units and scale words and split compounds and possessives, and two figures in one unseparated clause belong
to their own subjects. A figure grounds as derived only when the closed reader of written arithmetic gives it from the
answer's own calculation, exactly or rounded to its last place (`answer_derived_figures`). A figure stated for another year than the symbol's ("252 residents" in 2020 for the 2010 count) grounds
nothing. A figure written as a calculation's result or after "≈" states the half-unit enclosure of its last written place,
in superscript and caret notation alike. A figure the request states as a given, cited to a supplied document that does not
hold it, is re-checked against the task record (B23: "stated by the request, cited as <document>"); a figure inside the
request's question, condition, negation or answer requirement is no given. A form difference never verifies a
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

`parsing.py` reads provider text as data only: it refuses text over `MAX_PROVIDER_TEXT_BYTES` (64 KiB) before parsing
(`ProviderOutputTooLarge`, which the pipeline makes TRANSLATION_FAILED with no retry, "provider output too large": a retry
would ask for the same output again; "nesting is too deep" when its first 64 KiB already nest past `MAX_JSON_DEPTH`) and text
holding a lone surrogate, finds a Markdown fence with one linear scan (`strip_code_fences`; a run of backticks is one
step), and reports every grounding where the provider wrote `verified: true` (`asserted_verified_paths`, E505). The
pipeline records those E505 lines on a refused output too (`Translator._process` around `_process_object`: the refusal
keeps its own reason and the self-certification is added beside it; repair round 2).

**Repair round 3** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.2 and 9). Grounding (`grounding.py`): a figureless
task-authority premise with no excerpt is refuted, as before repair round 2, when a sentence the task states as a given
holds its words in another order or polarity (`_task_sentence_misread`), when the task only asks it or reports it as a
view (`_asserted_task_sentences`, `_asserted_roots`), and when it is an "if", "iff" or "or" no record states; a rule
premise is validated only by a stated sentence, never a question or a supposition. A quoted conjunction is stated
conjunct by conjunct, each with its own polarity and its distinguishing word (`_conjunction_in_spans`). An excerpt's figure
belongs to its own quantity, entity and period (`_subject_conflict`, `OPPOSED_QUALIFIERS`); a figure after "compared
with" to its own clause; a bound states the figure of a symbol that names it. `assignment_support` and `worked_results`
say how an assignment's figures are supported (date, stated, answer_stated, worked, not_in_answer, introduced), read by
EVD-FIG-001 and EVD-LACK-001. Peer document ids are normalised (`normalized_document_id`, `is_peer_id`). Eligibility
(`eligibility.py`, policy 2026.10-v5): a claim that states its own reason ("A, so B", "..., which shows that ...") is an
argument with no supporting claim. Claim rules: ARG-NS-003 (`diag_argument.unbridged_leap`); ARG-BARE-001 reads a report
that links nothing (`RANKING_WORDS`); EVD-CHERRY-001 reads a reversal after the window used; EVD-SRC-001 names a link that
rests on located excerpts stating no link (`_cites_words_not_the_link`). Known regression, found by measuring and left
for the next round: `quantities._DECL_UNIT_RE` now reads "in <unit>" before a parenthesis, so a meaning such as "peak
discharge in A (m³/s)" declares amperes and a correct quoted figure fails its grounding check (section 7 there).

**Repair round 4** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.2 and 10). Grounding (`grounding.py`): an "or" the task
states validates a disjunction premise, an exclusive one with a word of exclusion (`stated_rules.disjunction_shape`,
`stated_disjunction`; a near statement is unvalidated: `_disjunction_near_records`); a task sentence restated with its
pronoun resolved or in the passive states the premise (`_role_pattern`, `_active_order`); a conversion the task gives in an
instruction validates the premise that applies it (`relations.stated_conversion`); the count, total and mean of a stated
list, and an indexed lookup over it, ground their figures (`_list_aggregates_cached`, `_closing_list_gap`,
`_aggregate_source`, `_index_lookup`, `_position_in`); one sentence that states two quantities gives each its own figure
(`_subject_conflict`, `_period_conflict`); a premise cited only to a peer's report is unvalidated; author and provenance
labels are read as words for the peer test (`names_an_agent`, `AGENT_WORDS`); the answer's working is read once per text
and the records' figures once per value (`_calculation_steps`, `_records_state`). Eligibility: a pronoun conclusion
states its own reason (`adapters.markdown.states_own_reason`). Claim rules: ARG-NS-003 is no longer bridged by a sentence
that only names the two things (`diag_argument._states_connection`, `_capitalised_roots`). Outcome: the release
assessment lists capped diagnostics under their own line with no defect label (`named.blocking_release_lines`). Tests:
`tests/translate/test_repair_round4_*.py`.

**Repair round 5** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.1, 3.2 and 11). Grounding (`grounding.py`): an excerpt whose
clause contradicts the literal it is cited for (the opposite polarity, another figure, a planted checker note, no content
word) refutes it (`_literal_in_spans`, `content_in_excerpt`); an excerpt that gives several quantities their figures
grounds only the figure of a premise's own quantity (list items, comma-cut qualifiers, table cells: `_subject_conflict`,
`_table_cell`); a relayed agent's text is a peer document under "relay:", "rep-", an AI author or the router
(`is_peer_document`, `names_an_ai_system`). Stated rules (`stated_rules.py`): definitions ("defined as", "means", "is
called", a genus and its differentia) and closed enumerations are rules a record states (`_definition_readings`,
`stated_enumeration`); only negation words negate a stated list (`lexis.negation_words`). Quantities: a unit glossed in
parentheses is the declared unit (`declared_reading`); `stated_exactness` is cached. Precision (`precision.py`): a ratio
encoded cross-multiplied is a precision site (`_bound`, `_scaled`). Claim and report rules (`diag_argument.py`): two more
unbridged-leap shapes (`_leap_shape`: ranked, recommended), a linear sentence splitter (`_sentence_spans`), ARG-BARE-001
read only in the parts that ask for reasons (`_reason_parts`), and ARG-CIRC-003 for a claim whose reason clause restates
its point (`own_reason_circle`, report layer); the claim and report diagnoses read the record's task type as advisory.
Tests: `tests/translate/test_repair_round5_translate.py`.

**Close round 1** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.1, 3.2 and 12). Stated rules (`stated_rules.py`): a rule the
record states only hedged, framed or denied, as a question, restricted, limited by an opening phrase, with an "or" in its
consequence or a part of its condition the premise drops is not the source's own (`rule_qualifier`, `StatedRule.qualifier`);
its excerpt refutes the premise that encodes it plainly (`relation_in_source` False) and a record sentence of it validates
no task-authority rule. Grounding (`grounding.py`): a task sentence of another time, tense or direction of change does not
state a premise and refutes it when it states the conflict (`_task_conflict`, `content_in_task`); the month "May" is no
modal (`_suspending_tokens`); an excerpt of the words a literal quotes or names is no placeholder (`_names_words`); another figure
of the same value, or of the opposite part, is no other figure for a premise's quantity (`_subject_conflict`). Claim rules
(`diag_argument.py`): a heading that only restates the task is an info record of ARG-CIRC-001, not a circle
(`circular_refusal`, `_restates_task_words`). Tests: `tests/translate/test_close1_*.py`.

**Close round 2** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.2, 7 and 13). Grounding (`grounding.py`): a figureless task
premise that shares an atom with the point is never validated by a task sentence (`_literals_in_task`): the stricter
reading of repair round 4 (ADV4-06) also validated a proposition the task quotes for the student to weigh ("'X.' Discuss."),
so 'X, as the question states; therefore X' cleared; it is reverted to the committed base's reading, under the round's
convergence rule, and such a premise is left to the circularity rules (E112). Precision (`precision.py`): the open
precision of a trailing-zero whole number ("about 300") is not read at its last digit for a term that takes only whole
values (`_takes_whole_values`: Int symbols, integer literals and their sums, differences, products, negations, integer
quotients and remainders, perhaps cast to a real), since that reading is the exact count the approximation word denies;
the same count compared over Int or over `to_real` is decided the same way, and a ratio keeps both readings. Left by the
round: a plainly stated source rule with a qualifier word elsewhere in its sentence is still refuted by `rule_qualifier`
(DIFF-01), and an excerpt that negates a rule's consequence leaves the premise unvalidated (DIFF-03); section 7 there gives
the reasons. Tests: `tests/translate/test_close2_task_proposition.py`, `tests/translate/test_close2_precision_counts.py`.

**Close round 3** (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.2, 7 and 14). Claim rules (`diag_evidence.py`): EVD-SRC-001 does
not name a task-authority premise that restates a supposition the task sets ("Assume that ...", "Suppose ...", "Imagine
that ...": one task sentence whose opening is a supposition, by `assertion.sentence_cue_at`, holds every content root of the
premise with its polarity; `_supposed_by_task`, `_task_suppositions`), DV2-04: correct work that takes the supposition as
given was named `unchecked_source` at warning where the committed base names nothing. A plain restriction of the rule's
trigger set; the grounding record is unchanged, so the answer stays not releasable on the supposed premise. The translator
version is 0.5.1 and the rules `argdiag-2` (`version.py`), so a translation record of an earlier round of this release reads
as stale. Left, with the reasons in section 7 there: a plainly stated source rule with a qualifier word elsewhere in its
sentence (`rule_qualifier`, DV2-03) and "about 300 g" for 260 g (the open precision, DV2-08). Tests:
`tests/translate/test_close3_task_suppositions.py`.
