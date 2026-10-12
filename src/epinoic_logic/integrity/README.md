# integrity — communication between agents

Hallucination also enters between agents. The router hands a task to specialists;
specialists return immutable reports with stable claim ids; the combinator synthesizes
with a claim ledger; the Overseer decides from signed engine results. This package makes
every silent drop, rewrite, inflation, undisclosed contradiction, stale or forged result,
wrong-task report and tampered message VISIBLE as a specific finding carrying the
identifiers the Overseer needs.

## Entry point

`run_integrity_checks(plan, reports, synthesis, formalized, synthesized_conclusions,
prior_results, signing_key, config)` runs every applicable check and returns one
`IntegrityReport`. It never raises: a check that fails internally becomes an
`INT-INTERNAL-001` error finding naming the check. The report carries `report_sha256`
(digest of the rest of the report; `verify_report_digest`). `checks_run` lists what ran:
`handoff`, `ledger`, `formalization_binding`, `staleness`, `cross_report_consistency`,
`synthesis_entailment`, `required_formal_checks`, `conflict_disclosure`. The disclosure rule is
`check_conflict_disclosure(synthesis, conflicting_sets)` (`cross_check.py`), shared with the channel so the
Overseer's report and the synthesis receipt apply one rule.

## Findings

`IntegrityFinding` has one code per fault and one severity per code (one exception: INT-CONFLICT-005 is a warning
when the self-refuting formalization is the assumed reading of an AMBIGUOUS_TRANSLATION, an error otherwise; only the
channel, which knows the translation status, emits the warning). Besides `message`
(prose, truncated to 2000 characters) it carries the structured identifiers:
`claim_ids`, `message_ids`, `report_ids`, `agent_ids`, `document_ids`,
`formal_result_id` (the signed engine result that established a formal finding) and
`related_result_ids` (further engine runs consulted). Identifier lists are never
truncated. `IntegrityFinding.has_identifier()` is true for every finding the package
emits from `run_integrity_checks`.

| Check | Fault it exposes | Method |
| --- | --- | --- |
| Envelope (`envelope.py`) | replayed, re-headed or tampered messages; unsigned/forged envelopes; role impersonation; replies from the wrong party or across request/task boundaries; messages for another request | deterministic (payload hash, envelope digest, HMAC signature, message log) |
| Handoff (`handoff.py`) | a specialist answering the wrong task, an agent the router never selected, a selected agent that never reported, off-subject / wrong-level / wrong-type reports (the type planned for that agent, `agent_task_types`), wrong-task claims hidden inside a right-task report, citations outside the retrieval scope (reports, combinator and formalizations), late reports, unparseable timestamps, self-reported status | deterministic; timestamps compared as instants |
| Staleness (`handoff.py`) | a result reused for a changed representation, another configuration or other component versions; unsigned, forged or unverifiable results; inconsistent bindings; duplicate result ids; formalizations or results for claims no report contains | digest and signature comparison |
| Ledger (`ledger.py`) | material claims dropped without a meaningful record, orphaned synthesized claims, certainty inflated above the weakest source, evidence lost under any transformation, figures or dates (digits, words, scale words) that occur in none of the cited sources, carry another scale word, or are swapped or re-paired between events (and source figures dropped under an equivalence label or left out of a merge), quotations in a synthesized claim that occur in no supplied text or cited report, a reversed direction, a dropped negation or an approximate figure made exact, 'carried' claims whose text changed, ledger entries pointing nowhere, id collisions between reports and between the source and synthesis namespaces, student-facing text diverging from the ledger, conflicts "resolved" without a basis | deterministic accounting (figure sets, figure pairing, quotation location, lexical comparison) |
| Cross-report consistency (`cross_check.py`) | specialists contradicting each other under a shared glossary; a specialist claim refuting itself; glossary sort and meaning clashes; contradictions not disclosed in the synthesis | Z3 joint consistency; conflicting claims named claim-minimally (each claim of a core checked alone, the core minimised over claims by deletion) through an alias table |
| Synthesis entailment (`cross_check.py`) | the combinator stating more than the sources support, a synthesis that follows only through unverified inferences or through unproven specialist conclusions, paraphrases weaker than their source, partial formal coverage, invalid synthesized conclusions, required checks not performed | Z3 entailment of the synthesized conclusion from the union of source premises, re-run without ungrounded premises; reverse entailment for paraphrases |

## Finding codes

| Code | Severity | Meaning |
| --- | --- | --- |
| INT-ENV-001 | warning | duplicate message id with identical envelope and payload (replay) |
| INT-ENV-002 | error | message id reused with a different payload or a changed envelope header |
| INT-ENV-003 | error | `in_reply_to` references an unknown message |
| INT-ENV-004 | error | reply crosses request/task boundaries |
| INT-ENV-005 | warning | idempotency key reused by another message with the same payload (retry) |
| INT-ENV-006 | error | envelope unsigned or signature invalid (log constructed with `signing_key`) |
| INT-ENV-007 | error | sender role may not issue this contract (`ROLE_CONTRACTS`), e.g. a specialist sending `verification_result/1.0` |
| | | `specialist_report_forward/1.0` is the router's contract for handing a delivered report to another agent unchanged; only a router may send it, and the channel checks the payload against the delivery (INT-HANDOFF-013) |
| INT-ENV-008 | error | envelope header does not match the payload it carries (`bind_payload`): request/task differ, or the sender is not the agent the payload claims to come from (`agent_id` of a report, `combinator_agent_id` of a synthesis); the channel runs it on every response and relay except the router's forward, so a specialist cannot relay a colleague's report under its own name |
| INT-ENV-009 | error | message belongs to another request than the log (`MessageLog(request_id=...)`) |
| INT-ENV-010 | error | reply from a role/agent the replied-to message was not addressed to |
| INT-ENV-011 | error | idempotency key reused with a different payload |
| INT-HANDOFF-001 | error | report answers another request/task than the plan |
| INT-HANDOFF-002 | error | agent not selected by the router: the report's agent, a raw-text sender (decided before parsing), the sender or recipient of a relay in a specialist or combinator role, or a synthesis's combinator (the router and the Overseer, Verifier, Retrieval and Gate roles are infrastructure parties and need no selection) |
| INT-HANDOFF-003 | error | report subject differs from the subject the plan assigns that agent (`agent_subjects`, else the plan's subject) |
| INT-HANDOFF-004 | error | citation outside the retrieval scope (report claims or supplied texts, synthesized evidence refs, or formalized grounding) |
| INT-HANDOFF-005 | warning | report created after the plan deadline (instants compared) |
| INT-HANDOFF-006 | info | agent self-reported a verification status or eligibility; advisory, ignored |
| INT-HANDOFF-007 | error | a selected agent delivered no report; the synthesis is incomplete |
| INT-HANDOFF-008 | error | `created_at` / `deadline_at` is not an RFC 3339 timestamp with an explicit offset |
| INT-HANDOFF-009 | warning | the same agent delivered several reports for one task |
| INT-HANDOFF-010 | warning | report task_type differs from the type the plan sets for that agent (`agent_task_types`, else the plan's task_type) |
| INT-HANDOFF-011 | error | report course_level differs from the plan (both set and not 'unknown') |
| INT-HANDOFF-012 | error | a claim's provenance (request, task, agent, subject, task_type, level) differs from its report; on the channel also a claim whose `report_id` or `request_id` differs from its report, decided on the raw payload before contract validation and naming the claim and the fields (never a bare INT-REQ-009 value error) |
| INT-HANDOFF-013 | error | the router forwarded a report that was never delivered on this channel, or whose payload differs from the delivered one (altered in transit); the forward is not transmitted |
| INT-HANDOFF-014 | warning | a superseded report (INT-HANDOFF-009) remains in circulation: raised on the supersession naming the router's forwards of it and the reports that quote it as a peer document (whose excerpts are re-checked: one that occurred in the superseded text and not in the current one "no longer occurs", one located in neither "was never located in the superseded report either"; identifier lists are deduplicated), on a synthesis that cites it (an id collision with its successor is explained as a supersession, not blamed on the combinator), and on a router forward of it |
| INT-HANDOFF-015 | error | a report id reused with DIFFERENT content (a re-delivery with a changed response or changed claims, or a forged copy under a known id; the message names the fields that differ); the first delivery is kept, the later one is not delivered. The same content again, whatever its `created_at` (a re-parsed retransmission of the same answer), is INT-ENV-001 |
| INT-HANDOFF-016 | warning | synthesis timestamped before a report it cites |
| INT-HANDOFF-017 | warning | synthesis created after the plan deadline |
| INT-STALE-001 | error | result produced for a different representation of the claim |
| INT-STALE-002 | error | result unsigned or signature invalid |
| INT-STALE-003 | error | result ids do not match the claim being decided |
| INT-STALE-004 | error | stored result has no current (valid) formalization: unverifiable evidence |
| INT-STALE-005 | error | result produced under a different solver configuration or component versions |
| INT-STALE-006 | error | signature not verified: no verification key configured |
| INT-STALE-007 | error | result binding internally inconsistent (binding/config/versions digests) |
| INT-STALE-008 | error | one result id shared by several stored results |
| INT-STALE-009 | error | formalization does not belong to this claim/request (map key, claim_id, request_id); excluded from joint checks |
| INT-STALE-010 | error | formalization or stored result for a claim no specialist report contains |
| INT-STALE-011 | error | (channel) a claim outcome whose translation does not bind to the claim as transmitted: claim id, request, report, or `TranslationResult.claim_text_sha256` of another text; stale, neither delivered nor pooled |
| INT-LEDGER-000 | error | synthesis cites reports that were not provided |
| INT-LEDGER-001 | error | unknown source claim cited by a synthesized claim, ledger entry or conflict record |
| INT-LEDGER-002 | error | material source claim neither carried, transformed nor recorded as dropped (or unaccountable because its id collides) |
| INT-LEDGER-003 | error | certainty inflated above the weakest source |
| INT-LEDGER-004 | error | evidence references of material sources not preserved (every transformation) |
| INT-LEDGER-005 | error | synthesized claim without any source |
| INT-LEDGER-006 | error | source dropped without a meaningful reason (placeholders and whitespace do not count) |
| INT-LEDGER-008 | error | report or synthesis belongs to another request/task |
| INT-LEDGER-009 | error | present claim marked 'dropped' |
| INT-LEDGER-010 | warning | 'carried' claim with changed text or with more than one source |
| INT-LEDGER-011 | info | material content produced by merged/generalized/narrowed: formal check required |
| INT-LEDGER-012 | error | ledger entry points to a synthesized claim that does not exist or does not cite the source; sources not accounted |
| INT-LEDGER-013 | error | one report id used by several reports |
| INT-LEDGER-014 | error | one claim id appears in several reports |
| INT-LEDGER-015 | error | synthesized claim reuses a source claim id |
| INT-LEDGER-016 | warning | synthesized claim cites a source from a report absent from `source_report_ids` |
| INT-LEDGER-017 | warning | synthesized claim text absent from the student-facing text |
| INT-LEDGER-018 | warning | numeric literal in the student-facing text that occurs in no claim |
| INT-LEDGER-019 | warning | material source claim dropped (reason recorded) |
| INT-LEDGER-020 | warning | evidence excerpt differs from the source's under the same (document, locator) |
| INT-LEDGER-021 | warning | material sources became a 'supporting' synthesized claim |
| INT-LEDGER-022 | info | supporting source claim neither carried, transformed nor recorded as dropped; a claim roled `other` (a from-memory label, a self-report, a task note) is not content and is not counted |
| INT-LEDGER-023 | error | a synthesized claim states figures or dates (numerals, thousands separators removed; figures written in words: "a million", "two million", "half a million", "two hundred and sixty", "thirteen per cent", "two-thirds", "a tenth" after a qualifier or before "of"; month-year tokens; a figure in scientific notation, `3.0e8`, `6.67 × 10⁻¹¹`, `1.2*10**6`, is ONE figure read exactly by the STEM number scanner, whose spellings are its exact decimal value and its mantissa-exponent form, so `3.0e8`, `3.0 × 10⁸` and `300000000` meet and `6.67 × 10⁻¹¹` is never 6.67 and 10; one beyond the scanner's bounds, an exponent over 99, is no figure) that occur in none of its cited sources under any spelling ("a million" meets "1 million" and "1,000,000"), states a source's numeral with another scale word ("6.1 billion" where the sources say "6.1 million"; a numeral the sources state without a scale word is not held to one), or re-pairs figures or dates between events relative to its cited sources (`figure_pairing_differences`: two same-kind figures exchanged between their event words, a figure moved onto an event the sources pair only with another figure while it left every event of its own, a quantity dated to another month or year, a `from X to Y` reversed), whatever the transformation label: a changed, introduced, rescaled, swapped or re-paired figure or date. One finding per synthesized claim, naming every kind |
| INT-LEDGER-024 | warning | figures or dates of the cited sources do not appear in a 'carried' or 'paraphrased' synthesized claim (content dropped under an equivalence label), or in a 'merged' or 'generalized' one (content of the sources left out of the combined claim; 'narrowed' removes content by definition and is exempt) |
| INT-LEDGER-025 | error | a quotation in a synthesized claim occurs, in no recognised form (exact, normalised, elided, a form difference, a long elision), in any supplied text of the reports in scope, any of their responses, its cited source claims or (on the channel) the requests' texts: an altered or invented quotation |
| INT-LEDGER-026 | warning | a synthesized claim may say something other than its cited sources, by a lexical comparison: a fall where every source states a rise (or the reverse), a negation dropped or added under 'carried' / 'paraphrased', or a figure the sources give as approximate ("roughly 60") stated as exact ("exactly 60"); not formally checked |
| INT-CONFLICT-001 | error | specialist claims contradict each other: a claim-minimal set of two or more claims, each of which the contradiction needs (each claim of the unsat core is first checked alone; the set is minimised by deletion, in claim-id order, up to 16 claims; a larger core is named as found and says so). Once named, the set is set aside and the rest re-checked, so one contradiction never hides another (at most 8 per check) |
| INT-CONFLICT-002 | error | formal contradiction not disclosed: no conflict record names at least two of the conflicting claims, and the records together do not name them all (synthesized ids are mapped to their sources). Raised by `run_integrity_checks` and, on the channel, on a synthesis receipt after a joint check over the formalized claims in the ledger scope plus the contradictions already named on the channel |
| INT-CONFLICT-003 | error | conflict marked resolved without a meaningful basis |
| INT-CONFLICT-004 | warning | joint consistency undecided (timeout/unknown) or contradiction unattributable |
| INT-CONFLICT-005 | error / warning | one specialist claim is internally inconsistent (its own assertions, its pooled conclusion included, refute each other), found whether the unsat core used its own premises or another claim's identical copies; its self-refuting conclusion (or the whole claim, when its premises alone conflict) is set aside and the rest re-checked. No disclosure demanded. A warning when the claim's formalization is the assumed reading of an AMBIGUOUS_TRANSLATION (`assumed_readings`, passed by the channel): the refutation is the translator's reading, not the specialist's statement |
| INT-GLOSSARY-001 | error | symbol declared with different sorts in two claims (both named); joint check withheld |
| INT-GLOSSARY-002 | info | no formalized claims to cross-check |
| INT-GLOSSARY-003 | error | synthesized conclusion uses a symbol no source defines |
| INT-GLOSSARY-004 | error | joint problem could not be built (names the claims and the reason) |
| INT-GLOSSARY-005 | warning | symbol glossed with different meanings across claims; joint check still runs |
| INT-GLOSSARY-006 | error | joint problem breaches the joint limits (E3xx) |
| INT-GLOSSARY-007 | error | a source formalization is invalid inside the joint problem (named via the alias table) |
| INT-SYNTH-001 | error | synthesized claim not entailed by its cited sources (or refuted by the formalized ones) |
| INT-SYNTH-002 | info | synthesized claim follows only via unverified inferences/assumptions in the sources (confirmed by a re-run without them) |
| INT-SYNTH-003 | warning | synthesis entailment undecided |
| INT-SYNTH-004 | warning | formal conclusion given for a claim not in the synthesis |
| INT-SYNTH-005 | warning | synthesized claim has no formalized sources |
| INT-SYNTH-006 | error | material merged/generalized claim without a formal conclusion: the required check was not performed |
| INT-SYNTH-007 | warning | 'carried'/'paraphrased' claim strictly weaker than its source (reverse entailment) |
| INT-SYNTH-008 | warning | synthesis rests on pooled specialist conclusions that are not established (no ENTAILED result supplied) |
| INT-SYNTH-009 | warning | not entailed by the formalized subset of the cited sources (some sources unformalized) |
| INT-SYNTH-010 | error | synthesized conclusion is not a valid formalization (e.g. mixes Int and Real) |
| INT-SYNTH-011 | info | partial formal coverage: k of n cited sources formalized |
| INT-SYNTH-012 | warning | material narrowed/paraphrased claim without a formal conclusion (also raised on the channel's synthesis receipt when no formal conclusion was checked there) |
| INT-INTERNAL-001 | error | an integrity check failed internally; its findings are missing |

## Design notes

**Alias table.** Joint problems never embed raw claim ids in assertion ids. Each pooled
problem gets an alias (`c0`, `c1`, ...) and a `JointMap` records which claim and original
assertion every joint id stands for. Any claim id the contracts accept (uuid hex, `#`,
spaces, `::`, 128 characters) can be pooled; unsat cores and validator diagnostic paths are
mapped back through the table, never by parsing strings. `claim_ids_from_core(core, jmap)`
does the mapping; the old one-argument form is a deprecated fallback.

**Pooled conclusions.** Each entailment source's own conclusion is pooled as a premise (a
specialist's asserted point is something others may contradict). It is given a forced
grounding of kind `specialist_inference`, so it is never silent evidence: a synthesis that
rests on it is INT-SYNTH-008 unless `prior_results` holds an ENTAILED result for that
exact source formalization.

**Reliance.** When a proof uses ungrounded premises, the entailment is re-run without
every ungrounded premise. If the claim still follows, no finding. Otherwise it is re-run
without only the pooled conclusions: ENTAILED means the claim rests on source inferences
(INT-SYNTH-002); anything else means it rests on unproven conclusions (INT-SYNTH-008).

**Shared glossary.** Symbols with the same name across claims denote the same thing. A
sort clash is an error naming both claims and withholds the joint check; a meaning clash
(different `meaning` gloss, same sort) is a warning and the check runs. The unsat core is
always requested whatever the caller's `SolverConfig` says.

**Disclosure.** A contradiction counts as disclosed only when some conflict record names at
least two of the conflicting claims and the qualifying records together name them all;
synthesized ids in a record stand for their `source_claim_ids`. A self-refuting claim is
INT-CONFLICT-005 and demands no disclosure (a `ConflictRecord` needs two distinct ids).

**Claim-minimal attribution.** An unsat core is a set of assertions, and two claims may carry
identical premises (one report restating its figures in two claims), so the core can use an
innocent claim's copies: the r4 hi-t8 point h1.1 was once named in a conflict that lived wholly
inside h1.5. `check_cross_report_consistency` (and the entailment path) therefore checks each
claim of a core of several claims alone; a claim that refutes itself is INT-CONFLICT-005 and its
self-refuting conclusion is set aside before the rest is re-checked; a contradiction that remains
is minimised over claims by deletion, so INT-CONFLICT-001 names a claim only when the
contradiction needs it, whatever the pooling order. The extra engine runs are cited in each
finding's `related_result_ids` (and `run_integrity_checks` lists them in `formal_result_ids`).

**Envelopes.** `payload_sha256` is integrity only: a consistently forged envelope passes
it. Authenticity comes from `sign_message`/`verify_message` (HMAC over the canonical
envelope without the signature fields) and a `MessageLog(signing_key=...)`. A reused
message id is compared by `envelope_digest` (header and payload hash), so a changed header
is INT-ENV-002, not a replay. `bind_payload(msg, model)` compares the header with the
parsed contract inside.

**Plan per agent.** `WorkPlan.agent_subjects` and `WorkPlan.agent_task_types` name a selected agent's own
subject and task type when they differ from the plan's; both must name selected agents, and a plan without
them keeps the digest it always had (`plan_digest` omits empty mappings).

**Scientific notation (STEM).** Figures with an exponent are read through `stem.numbers.scan_number`
(`ledger._scientific_figures`); figures with no exponent are read exactly as before. The pairing reader
treats a superscript exponent (`10⁻¹⁹`) as no day of a month: `'¹⁹'.isdigit()` is true but it is no
ASCII numeral, and before this a synthesis carrying one raised out of the ledger.

**Figure pairing.** A combinator that swaps two dates or two figures between events uses the same
tokens as its sources, so INT-LEDGER-023 compares the pairing as well as the token set
(`figure_pairing_differences`). Figures written in words are read as digits first ("roughly a
tenth" pairs like "about 13 per cent"; findings show the words with the value compared). Each
figure of a clause (sentence ends, punctuation and the subordinating words split clauses; "and"
does not, since it joins the items of one dated statement; a clause that is nothing but a date is
not cut from its event by a comma: "On 27 October, the day ..., a second message added" keeps 27
with its event) is paired with the figures within four tokens and with the event words within four
tokens that have no nearer figure of the same kind ("announced on 22 October and in force from 24
October": 'force' belongs to 24 only), light-stemmed, unit and function words excluded. Four shapes
are decided on the sources' own statements: an exchange (A stands with P and B with Q where the
sources state B with P and A with Q; A and B of one kind: years, days of a month, or quantities, so
a seat count is never "exchanged" with the year it was won), a one-sided re-pairing (A stands with
P, which the sources pair only with B, the synthesis does not state B with P, and A has left every
event the sources state it with: "The turning point was 1932" where the sources say 1930 and state
1932 as the counter-case), a dated quantity (`<q> ... in [<month>] <year>`) the sources date to
another month or year, compared at the resolution both sides state, and a `from X to Y` the sources
state reversed. A new pairing the sources do not contradict (a merge dating one source's figure
with another's year; a figure the sources state with no event word) is not reported.
`light_stem` (-s, -es, -ed, -ing, then a trailing e) is shared with the channel's request-echo and
coverage tests.

**Scope.** `WorkPlan.allowed_document_ids` empty means unrestricted. When set, it applies to
report claims and supplied texts, to synthesized `evidence_refs`, and to the
`grounding.source_refs` of formalized problems.

**Timestamps.** `created_at`/`deadline_at` on `AgentMessage`, `Synthesis` and `WorkPlan` must
be RFC 3339 with an explicit offset or `Z` (validated at the contract boundary); report
timestamps are parsed with `parse_rfc3339` and compared as instants, an unparseable one is
INT-HANDOFF-008. `payload_hash` rejects NaN/Infinity. `WorkPlan.plan_sha256` (`seal_plan`)
and `IntegrityReport.report_sha256` give transit integrity.
