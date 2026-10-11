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
`synthesis_entailment`, `required_formal_checks`, `conflict_disclosure`.

## Findings

`IntegrityFinding` has one code per fault and one severity per code. Besides `message`
(prose, truncated to 2000 characters) it carries the structured identifiers:
`claim_ids`, `message_ids`, `report_ids`, `agent_ids`, `document_ids`,
`formal_result_id` (the signed engine result that established a formal finding) and
`related_result_ids` (further engine runs consulted). Identifier lists are never
truncated. `IntegrityFinding.has_identifier()` is true for every finding the package
emits from `run_integrity_checks`.

| Check | Fault it exposes | Method |
| --- | --- | --- |
| Envelope (`envelope.py`) | replayed, re-headed or tampered messages; unsigned/forged envelopes; role impersonation; replies from the wrong party or across request/task boundaries; messages for another request | deterministic (payload hash, envelope digest, HMAC signature, message log) |
| Handoff (`handoff.py`) | a specialist answering the wrong task, an agent the router never selected, a selected agent that never reported, off-subject / wrong-level / wrong-type reports, wrong-task claims hidden inside a right-task report, citations outside the retrieval scope (reports, combinator and formalizations), late reports, unparseable timestamps, self-reported status | deterministic; timestamps compared as instants |
| Staleness (`handoff.py`) | a result reused for a changed representation, another configuration or other component versions; unsigned, forged or unverifiable results; inconsistent bindings; duplicate result ids; formalizations or results for claims no report contains | digest and signature comparison |
| Ledger (`ledger.py`) | material claims dropped without a meaningful record, orphaned synthesized claims, certainty inflated above the weakest source, evidence lost under any transformation, 'carried' claims whose text changed, ledger entries pointing nowhere, id collisions between reports and between the source and synthesis namespaces, student-facing text diverging from the ledger, conflicts "resolved" without a basis | deterministic accounting |
| Cross-report consistency (`cross_check.py`) | specialists contradicting each other under a shared glossary; a specialist claim refuting itself; glossary sort and meaning clashes; contradictions not disclosed in the synthesis | Z3 joint consistency; conflicting claims named from the unsat core through an alias table |
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
| INT-ENV-008 | error | envelope header does not match the payload it carries (`bind_payload`) |
| INT-ENV-009 | error | message belongs to another request than the log (`MessageLog(request_id=...)`) |
| INT-ENV-010 | error | reply from a role/agent the replied-to message was not addressed to |
| INT-ENV-011 | error | idempotency key reused with a different payload |
| INT-HANDOFF-001 | error | report answers another request/task than the plan |
| INT-HANDOFF-002 | error | agent not selected by the router |
| INT-HANDOFF-003 | error | report subject differs from the subject the plan assigns that agent (`agent_subjects`, else the plan's subject) |
| INT-HANDOFF-004 | error | citation outside the retrieval scope (report claims or supplied texts, synthesized evidence refs, or formalized grounding) |
| INT-HANDOFF-005 | warning | report created after the plan deadline (instants compared) |
| INT-HANDOFF-006 | info | agent self-reported a verification status or eligibility; advisory, ignored |
| INT-HANDOFF-007 | error | a selected agent delivered no report; the synthesis is incomplete |
| INT-HANDOFF-008 | error | `created_at` / `deadline_at` is not an RFC 3339 timestamp with an explicit offset |
| INT-HANDOFF-009 | warning | the same agent delivered several reports for one task |
| INT-HANDOFF-010 | warning | report task_type differs from the plan |
| INT-HANDOFF-011 | error | report course_level differs from the plan (both set and not 'unknown') |
| INT-HANDOFF-012 | error | a claim's provenance (request, task, agent, subject, task_type, level) differs from its report |
| INT-HANDOFF-013 | error | the router forwarded a report that was never delivered on this channel, or whose payload differs from the delivered one (altered in transit); the forward is not transmitted |
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
| INT-LEDGER-022 | info | supporting source claim neither carried, transformed nor recorded as dropped |
| INT-CONFLICT-001 | error | specialist claims contradict each other (two or more claims named from the core) |
| INT-CONFLICT-002 | error | formal contradiction not disclosed: no conflict record names at least two of the conflicting claims, and the records together do not name them all (synthesized ids are mapped to their sources) |
| INT-CONFLICT-003 | error | conflict marked resolved without a meaningful basis |
| INT-CONFLICT-004 | warning | joint consistency undecided (timeout/unknown) or contradiction unattributable |
| INT-CONFLICT-005 | error | one specialist claim is internally inconsistent (its own assertions refute each other); no disclosure demanded |
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
| INT-SYNTH-012 | warning | material narrowed/paraphrased claim without a formal conclusion |
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
synthesized ids in a record stand for their `source_claim_ids`. A single-claim core is
INT-CONFLICT-005 and demands no disclosure (a `ConflictRecord` needs two distinct ids).

**Envelopes.** `payload_sha256` is integrity only: a consistently forged envelope passes
it. Authenticity comes from `sign_message`/`verify_message` (HMAC over the canonical
envelope without the signature fields) and a `MessageLog(signing_key=...)`. A reused
message id is compared by `envelope_digest` (header and payload hash), so a changed header
is INT-ENV-002, not a replay. `bind_payload(msg, model)` compares the header with the
parsed contract inside.

**Scope.** `WorkPlan.allowed_document_ids` empty means unrestricted. When set, it applies to
report claims and supplied texts, to synthesized `evidence_refs`, and to the
`grounding.source_refs` of formalized problems.

**Timestamps.** `created_at`/`deadline_at` on `AgentMessage`, `Synthesis` and `WorkPlan` must
be RFC 3339 with an explicit offset or `Z` (validated at the contract boundary); report
timestamps are parsed with `parse_rfc3339` and compared as instants, an unparseable one is
INT-HANDOFF-008. `payload_hash` rejects NaN/Infinity. `WorkPlan.plan_sha256` (`seal_plan`)
and `IntegrityReport.report_sha256` give transit integrity.
